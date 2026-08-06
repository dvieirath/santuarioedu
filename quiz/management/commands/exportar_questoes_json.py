"""
Exporta questoes do BD local no formato JSON aceito por `importar_questoes`.
Fecha o ciclo local -> prod: dump aqui, git push, roda importar no Railway.

Idempotente em prod: dedup via texto_hash faz skip do que ja existe.

Formato de saida (compativel com importar_questoes):
[
  {
    "categoria_path": "Direito > Direito Constitucional > Principios Fundamentais",
    "banca": "TJ-AP",
    "ano": 2023,
    "tipo": "ME",
    "texto": "Enunciado completo...",
    "assunto": "...",
    "alternativas": [
      {"texto": "A", "correta": false},
      {"texto": "B", "correta": true}
    ]
  }
]

Uso:
    python manage.py exportar_questoes_json data/dump_local.json
    python manage.py exportar_questoes_json data/dump_ofic.json --apenas_oficiais
    python manage.py exportar_questoes_json data/dump.json --apenas_revisadas
"""
import json
import os
from django.core.management.base import BaseCommand

from quiz.models import Questao


class Command(BaseCommand):
    help = 'Exporta questoes do BD em JSON compativel com importar_questoes'

    def add_arguments(self, parser):
        parser.add_argument('arquivo_saida', type=str,
                            help='Caminho do JSON de saida')
        parser.add_argument('--apenas_oficiais', action='store_true',
                            help='Exporta so questoes nao-IA (gerada_por_ia=False)')
        parser.add_argument('--apenas_revisadas', action='store_true',
                            help='Exporta so questoes revisada=True')
        parser.add_argument('--categoria_raiz', type=str, default=None,
                            help='Filtra por disciplina raiz (ex: "Direito")')

    def handle(self, *args, **opts):
        saida = opts['arquivo_saida']
        apenas_ofic = opts['apenas_oficiais']
        apenas_rev = opts['apenas_revisadas']
        cat_raiz = opts['categoria_raiz']

        qs = Questao.objects.select_related('categoria').prefetch_related('alternativa_set')

        if apenas_ofic:
            qs = qs.filter(gerada_por_ia=False)
        if apenas_rev:
            qs = qs.filter(revisada=True)
        if cat_raiz:
            from quiz.models import Categoria
            raiz = Categoria.objects.filter(nome__iexact=cat_raiz, parent__isnull=True).first()
            if raiz:
                qs = qs.filter(categoria_id__in=raiz.subarvore_ids())
            else:
                self.stdout.write(self.style.ERROR(f'Categoria raiz "{cat_raiz}" nao existe'))
                return

        total = qs.count()
        self.stdout.write(self.style.HTTP_INFO(
            f'\n═══ Exportando {total} questoes para {saida} ═══'
        ))

        # Cache: id -> path completo
        path_cache = {}

        def _path_de(cat):
            if cat.id in path_cache:
                return path_cache[cat.id]
            partes = [cat.nome]
            p = cat.parent
            while p:
                partes.append(p.nome)
                p = p.parent
            path = ' > '.join(reversed(partes))
            path_cache[cat.id] = path
            return path

        dump = []
        exportadas = 0
        sem_alt = 0
        for q in qs.iterator(chunk_size=200):
            if not q.categoria_id:
                continue
            path = _path_de(q.categoria)
            alts = list(q.alternativa_set.all())
            item = {
                'categoria_path': path,
                'tipo':           q.tipo,
                'texto':          q.texto,
            }
            if q.banca:
                item['banca'] = q.banca
            if q.ano:
                item['ano'] = q.ano
            if q.assunto:
                item['assunto'] = q.assunto

            if q.tipo == 'CE':
                # Detecta qual alternativa (Certo/Errado) esta marcada correta
                correta_c = any(
                    a.correta and a.texto.strip().lower() in ('certo', 'c', 'verdadeiro', 'v')
                    for a in alts
                )
                item['resposta_ce'] = 'C' if correta_c else 'E'
            else:
                if not alts:
                    sem_alt += 1
                    continue
                item['alternativas'] = [
                    {'texto': a.texto, 'correta': a.correta}
                    for a in alts
                ]

            dump.append(item)
            exportadas += 1

        # Cria pasta se nao existir
        pasta = os.path.dirname(saida)
        if pasta and not os.path.exists(pasta):
            os.makedirs(pasta, exist_ok=True)

        with open(saida, 'w', encoding='utf-8') as f:
            json.dump(dump, f, ensure_ascii=False, indent=2)

        tamanho_kb = os.path.getsize(saida) / 1024
        self.stdout.write('\n' + '═' * 70)
        self.stdout.write(self.style.SUCCESS(
            f'✓ {exportadas} questoes exportadas ({tamanho_kb:.1f} KB)'
        ))
        if sem_alt:
            self.stdout.write(self.style.WARNING(
                f'⊘ {sem_alt} pulados por nao ter alternativas'
            ))
        self.stdout.write(f'\nArquivo: {saida}')
        self.stdout.write(self.style.HTTP_INFO(
            '\nPara importar no Railway:\n'
            f'  railway run python manage.py importar_questoes {saida} --revisada'
        ))
