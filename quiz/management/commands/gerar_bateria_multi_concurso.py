"""
Orquestra geracao em massa de questoes para MULTIPLOS concursos em paralelo.

Diferente do gerar_bateria_prf (dedicado ao edital PRF), este comando rotaciona
entre concursos configurados em CONCURSO_DISCIPLINAS (preparacao.py), gerando
uma cota por concurso × disciplina × tipo (CE/ME). Ideal pra alimentar
plataforma multi-concurso sem gastar toda quota em uma so materia.

Ordem de rotacao: intercalado entre concursos pra maximizar quota diaria
por provider. Se um concurso esgota, o proximo compensa.

Uso:
    # Padrao — 30 questoes por (concurso, disciplina) em 4 concursos = ~840
    python manage.py gerar_bateria_multi_concurso

    # Ate cada (concurso, disciplina) bater 200 questoes
    python manage.py gerar_bateria_multi_concurso --ate_teto 200

    # So determinados concursos
    python manage.py gerar_bateria_multi_concurso --concursos prf,inss

    # Batch maior (menos chamadas, mais tokens por chamada)
    python manage.py gerar_bateria_multi_concurso --qtd 30 --batch 10

    # Dry-run
    python manage.py gerar_bateria_multi_concurso --dry_run
"""
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand

from quiz.models import Categoria, Questao
from quiz.preparacao import CONCURSO_DISCIPLINAS, _match_categoria


# Concursos default: pega dos mais focados PRF/INSS/PF/TJDF (edital 2024-2025 quente)
CONCURSOS_DEFAULT = ['prf', 'inss', 'pf', 'tjdf']

# Bancas por concurso — rotaciona pra dar variedade estilistica
BANCAS_POR_CONCURSO = {
    'prf':    ['Cebraspe', 'CESPE', 'FGV'],
    'inss':   ['Cebraspe', 'CESGRANRIO'],
    'pf':     ['Cebraspe'],
    'tjdf':   ['Cebraspe', 'FGV', 'IADES'],
    'trf':    ['Cebraspe', 'FGV', 'CESGRANRIO'],
    'camara': ['FGV', 'Cebraspe'],
    'enem':   ['INEP'],
}


class Command(BaseCommand):
    help = 'Gera questoes IA em massa para multiplos concursos em rotacao'

    def add_arguments(self, parser):
        parser.add_argument('--qtd', type=int, default=30,
                            help='Quantas questoes por (concurso, disciplina) (default 30)')
        parser.add_argument('--ate_teto', type=int, default=0,
                            help='Se >0: gera ate cada disc bater esse teto no concurso')
        parser.add_argument('--concursos', type=str, default='',
                            help='Slugs (comma-separated). Default: ' + ','.join(CONCURSOS_DEFAULT))
        parser.add_argument('--pct_ce', type=float, default=0.6,
                            help='Fracao CE (default 0.6 = 60%%). Resto ME.')
        parser.add_argument('--batch', type=int, default=5,
                            help='Questoes por chamada IA (default 5)')
        parser.add_argument('--delay', type=float, default=1.0,
                            help='Segundos entre chamadas (default 1)')
        parser.add_argument('--pct_apoio', type=float, default=0.15,
                            help='Fracao com texto de apoio (default 0.15)')
        parser.add_argument('--dry_run', action='store_true')

    def handle(self, *args, **opts):
        concursos = [c.strip().lower() for c in
                     (opts['concursos'] or ','.join(CONCURSOS_DEFAULT)).split(',') if c.strip()]

        # Valida concursos
        invalidos = [c for c in concursos if c not in CONCURSO_DISCIPLINAS]
        if invalidos:
            self.stderr.write(self.style.ERROR(
                f'Concursos invalidos: {invalidos}. '
                f'Validos: {sorted(CONCURSO_DISCIPLINAS.keys())}'
            ))
            return

        # Monta o plano intercalado: (concurso, disciplina, ce, me) ...
        # Rotaciona: prf-disc1, inss-disc1, pf-disc1, ..., prf-disc2, ...
        plano = []
        max_discs = max(len(CONCURSO_DISCIPLINAS[c]) for c in concursos)
        for i in range(max_discs):
            for concurso in concursos:
                discs = CONCURSO_DISCIPLINAS[concurso]
                if i >= len(discs):
                    continue
                disc = discs[i]
                cats = _match_categoria(disc)
                atual = 0
                if cats:
                    ids = set()
                    for c in cats:
                        ids.update(c.subarvore_ids())
                    atual = Questao.objects.filter(categoria_id__in=ids).count()
                if opts['ate_teto']:
                    gerar = max(0, opts['ate_teto'] - atual)
                else:
                    gerar = opts['qtd']
                if gerar <= 0:
                    continue
                n_ce = int(gerar * opts['pct_ce'])
                n_me = gerar - n_ce
                plano.append({
                    'concurso': concurso,
                    'disciplina': disc,
                    'atual': atual,
                    'ce': n_ce,
                    'me': n_me,
                })

        # Exibe plano
        self.stdout.write(self.style.HTTP_INFO('\nPLANO DE GERACAO MULTI-CONCURSO:'))
        self.stdout.write(f'{"Concurso":<8} {"Disciplina":<32} {"Atual":>6} {"CE":>5} {"ME":>5}')
        self.stdout.write('=' * 62)
        total_gerar = 0
        for p in plano:
            total = p['ce'] + p['me']
            total_gerar += total
            self.stdout.write(
                f'{p["concurso"]:<8} {p["disciplina"][:32]:<32} {p["atual"]:>6} {p["ce"]:>5} {p["me"]:>5}'
            )
        self.stdout.write('=' * 62)
        self.stdout.write(f'TOTAL: {total_gerar} questoes em {len(plano)} pares (concurso,disc)\n')

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING('[DRY-RUN] Nada foi gerado.'))
            return
        if not plano:
            self.stdout.write(self.style.SUCCESS('Nada a gerar — tetos atingidos.'))
            return

        # Executa
        criadas_total = 0
        for idx, p in enumerate(plano, 1):
            concurso = p['concurso']
            disc = p['disciplina']
            bancas = BANCAS_POR_CONCURSO.get(concurso, ['Cebraspe'])
            self.stdout.write(self.style.HTTP_INFO(
                f'\n[{idx}/{len(plano)}] {concurso.upper()} × {disc} (CE:{p["ce"]} + ME:{p["me"]})'
            ))

            for tipo, n in [('CE', p['ce']), ('ME', p['me'])]:
                if n <= 0:
                    continue
                banca = bancas[idx % len(bancas)]
                # Contagem antes (accent-insensitive)
                antes = Questao.objects.filter(categoria__nome__iexact=disc).count()
                try:
                    call_command(
                        'gerar_questoes_ia',
                        categoria=disc,
                        qtd=n,
                        batch=opts['batch'],
                        banca=banca,
                        tipo=tipo,
                        delay=opts['delay'],
                        com_texto_apoio=opts['pct_apoio'],
                        criar_se_necessario=True,
                    )
                except SystemExit:
                    pass
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'    Erro {tipo} p/ {concurso}×{disc}: {type(e).__name__}: {str(e)[:80]}'
                    ))
                depois = Questao.objects.filter(categoria__nome__iexact=disc).count()
                criadas_total += (depois - antes)
                if opts['delay']:
                    time.sleep(opts['delay'])

        self.stdout.write(self.style.SUCCESS(
            f'\n{"=" * 62}\n'
            f'BATERIA MULTI-CONCURSO CONCLUIDA: ~{criadas_total} questoes criadas em '
            f'{len(concursos)} concursos ({",".join(concursos)}).\n'
            f'Proximo passo: gerar justificativas\n'
            f'  python manage.py gerar_justificativas_ia --somente_pendentes --somente_ia --limit 1000'
        ))
