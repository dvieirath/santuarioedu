"""
Sugere vídeos do YouTube para os temas das questões liberadas, usando a cota
gratuita da YouTube Data API. Os vídeos entram como candidatos NÃO aprovados:
alguém da equipe confere e aprova no admin (Vídeos relacionados).

    python manage.py buscar_videos_youtube                    # mostra o plano, sem gastar cota
    python manage.py buscar_videos_youtube --aplicar --limite 40
    python manage.py buscar_videos_youtube --so categorias    # só um vídeo geral por categoria

Precisa de YOUTUBE_API_KEY no .env. Cada busca gasta 101 das 10 mil unidades
diárias gratuitas (cerca de 98 buscas por dia).

Ordem das buscas:
  1. categorias com questão liberada e sem vídeo geral (nem candidato);
  2. assuntos sem vídeo próprio, do que tem mais questões para o que tem menos
     (a partir de --minimo_questoes).
Termo buscado há menos de 30 dias não é repetido (output/videos_youtube/buscas.json).
"""
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from quiz import videos as v
from quiz.models import Categoria, Questao, VideoAula

DIAS_SEM_REPETIR = 30


class Command(BaseCommand):
    help = 'Sugere vídeos do YouTube (candidatos a aprovar) para os temas das questões'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true',
                            help='Faz as buscas e grava os candidatos (sem isto só mostra o plano)')
        parser.add_argument('--limite', type=int, default=40,
                            help='Máximo de buscas nesta execução (padrão 40, cerca de 4 mil unidades)')
        parser.add_argument('--so', choices=('categorias', 'assuntos'), default=None,
                            help='Buscar só vídeos gerais de categoria ou só de assunto')
        parser.add_argument('--minimo_questoes', type=int, default=3,
                            help='Assunto precisa ter ao menos N questões liberadas sem vídeo')
        parser.add_argument('--por_busca', type=int, default=3,
                            help='Candidatos guardados por busca')
        parser.add_argument('--repetir', action='store_true',
                            help='Buscar de novo termos já buscados nos últimos 30 dias')

    # ── cobertura e alvos ──
    def _alvos(self, opts):
        pais = v.mapa_de_pais()
        nomes = dict(Categoria.objects.values_list('id', 'nome'))
        por_categoria = defaultdict(list)
        for video in VideoAula.objects.all():
            por_categoria[video.categoria_id].append(video)

        sem_geral = Counter()
        sem_assunto = Counter()
        texto_assunto = {}
        cobertura = Counter()
        for _qid, cat_id, assunto in Questao.objects.filter(
                revisada=True, rejeitada_definitiva=False).values_list('id', 'categoria_id', 'assunto'):
            cadeia = v.cadeia_categorias(cat_id, pais)
            candidatos = [x for c in cadeia for x in por_categoria.get(c, ())]
            a_norm = v.normalizar(assunto)
            aprovados = v.escolher([x for x in candidatos if x.aprovado], cadeia, a_norm)
            todos = v.escolher(candidatos, cadeia, a_norm)
            cobertura['com_video_aprovado' if aprovados else
                      'so_candidato' if todos else 'sem_video'] += 1
            if not any(not x.assunto_norm for x in candidatos):
                sem_geral[cat_id] += 1
            if a_norm and not any(x.assunto_norm and x.assunto_norm in a_norm for x in candidatos):
                chave = (cat_id, a_norm)
                sem_assunto[chave] += 1
                texto_assunto.setdefault(chave, ' '.join(assunto.split()))

        alvos = []
        if opts['so'] != 'assuntos':
            for cat_id, n in sem_geral.most_common():
                alvos.append({'tipo': 'categoria', 'categoria_id': cat_id, 'assunto': '',
                              'questoes': n, 'termo': f'{nomes.get(cat_id, "")} aula concurso'})
        if opts['so'] != 'categorias':
            for (cat_id, a_norm), n in sem_assunto.most_common():
                if n < opts['minimo_questoes']:
                    break
                assunto = texto_assunto[(cat_id, a_norm)]
                nome = nomes.get(cat_id, '')
                termo = assunto if v.normalizar(nome) in a_norm else f'{assunto} {nome}'
                alvos.append({'tipo': 'assunto', 'categoria_id': cat_id, 'assunto': assunto,
                              'questoes': n, 'termo': f'{termo} aula'})
        return alvos, dict(cobertura)

    # ── execução ──
    def handle(self, *args, **opts):
        base = Path(settings.BASE_DIR) / 'output' / 'videos_youtube'
        arquivo_buscas = base / 'buscas.json'
        try:
            buscas = json.loads(arquivo_buscas.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            buscas = {}
        corte = (date.today() - timedelta(days=DIAS_SEM_REPETIR)).isoformat()

        alvos, cobertura = self._alvos(opts)
        if not opts['repetir']:
            alvos = [a for a in alvos if buscas.get(v.normalizar(a['termo']), '') < corte]
        plano = alvos[:max(0, opts['limite'])]

        self.stdout.write('Questões liberadas: ' + ', '.join(
            f'{n} {k.replace("_", " ")}' for k, n in sorted(cobertura.items())))
        self.stdout.write(f'Buscas possíveis: {len(alvos)}. Nesta execução: {len(plano)} '
                          f'(cerca de {len(plano) * 101} das 10.000 unidades diárias).')
        for a in plano[:15]:
            self.stdout.write(f'  {a["questoes"]:4d} questões  [{a["tipo"]}]  {a["termo"]}')
        if len(plano) > 15:
            self.stdout.write(f'  ... e mais {len(plano) - 15}')

        if not opts['aplicar']:
            self.stdout.write(self.style.WARNING('Simulação: nenhuma busca feita. Use --aplicar.'))
            return
        chave = getattr(settings, 'YOUTUBE_API_KEY', '')
        if not chave:
            raise CommandError('Falta YOUTUBE_API_KEY no .env (chave gratuita da YouTube Data API v3).')

        base.mkdir(parents=True, exist_ok=True)
        criados, feitas, erros, parou = [], 0, [], ''
        for alvo in plano:
            try:
                achados = v.buscar_na_api(alvo['termo'], chave, quantos=opts['por_busca'])
            except v.CotaEsgotada as e:
                parou = str(e)
                break
            except v.ErroYouTube as e:
                erros.append({'termo': alvo['termo'], 'erro': str(e)[:300]})
                if len(erros) >= 3 and not feitas:
                    parou = f'três erros seguidos, último: {e}'
                    break
                continue
            feitas += 1
            buscas[v.normalizar(alvo['termo'])] = date.today().isoformat()
            arquivo_buscas.write_text(json.dumps(buscas, ensure_ascii=False, indent=1), encoding='utf-8')
            for item in achados:
                video, novo = VideoAula.objects.get_or_create(
                    youtube_id=item['youtube_id'], categoria_id=alvo['categoria_id'],
                    assunto_norm=v.normalizar(alvo['assunto']),
                    defaults={'titulo': item['titulo'], 'canal': item['canal'],
                              'duracao_segundos': item['duracao_segundos'],
                              'assunto': alvo['assunto'], 'aprovado': False,
                              'origem': VideoAula.ORIGEM_YOUTUBE, 'busca': alvo['termo'][:255]})
                if novo:
                    criados.append(video.id)

        carimbo = timezone.localtime().strftime('%Y%m%d_%H%M%S')
        relatorio = {
            'quando': carimbo, 'buscas_feitas': feitas, 'unidades_estimadas': feitas * 101,
            'candidatos_criados': criados, 'erros': erros, 'parou_por': parou,
            'cobertura_antes': cobertura, 'cobertura_depois': self._alvos(opts)[1],
            'termos': [a['termo'] for a in plano[:feitas + len(erros)]],
        }
        destino = base / f'relatorio_{carimbo}.json'
        destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=1), encoding='utf-8')
        if parou:
            self.stdout.write(self.style.WARNING(f'Parou: {parou}'))
        self.stdout.write(self.style.SUCCESS(
            f'{feitas} buscas, {len(criados)} candidatos novos (não aprovados). '
            f'Aprove em /admin/quiz/videoaula/?aprovado__exact=0'))
        self.stdout.write(f'Relatório: {destino.relative_to(settings.BASE_DIR)}')
