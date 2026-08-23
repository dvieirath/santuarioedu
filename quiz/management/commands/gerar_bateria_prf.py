"""
Orquestrador de geração em massa de questões PRF-style via IA.

Percorre as categorias relevantes ao edital PRF e chama `gerar_questoes_ia`
pra cada uma, alternando entre CE (60%) e ME (40%) — proporcao tipica da
banca Cebraspe. Aplica --com_texto_apoio 0.2 (20% com texto de apoio embutido).

Uso:
    # Primeira bateria: 50 por categoria = ~700 questoes
    python manage.py gerar_bateria_prf --qtd 50

    # Rodada maior: 100 por categoria = ~1400 questoes
    python manage.py gerar_bateria_prf --qtd 100

    # Ate bater o teto (1000 por categoria)
    python manage.py gerar_bateria_prf --ate_teto 1000

    # So uma banca especifica (default: mescla Cebraspe/FGV/FCC)
    python manage.py gerar_bateria_prf --qtd 50 --banca Cebraspe

    # Dry-run: mostra plano sem executar
    python manage.py gerar_bateria_prf --qtd 50 --dry_run
"""
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from quiz.models import Categoria, Questao


# Categorias que fazem parte do edital PRF atual (2021+).
# Se voce quer adicionar/remover, edite aqui.
CATEGORIAS_PRF = [
    'Prova PRF',
    'Língua Portuguesa',
    'Direito Constitucional',
    'Direito Administrativo',
    'Direito Penal',
    'Direito Processual Penal',
    'Legislação de Trânsito',
    'Ética no Serviço Público',
    'Raciocínio Lógico e Matemática',
    'Informática',
    'Atualidades',
    'Administração Pública',
    'Conhecimentos Gerais',
    'Segurança Pública',
]

# Bancas historicas que aplicaram PRF — pra variar estilo entre chamadas
BANCAS_PRF = ['Cebraspe', 'CESPE', 'FGV', 'FCC']


class Command(BaseCommand):
    help = 'Gera bateria de questões PRF-style em massa (14 categorias × CE+ME)'

    def add_arguments(self, parser):
        parser.add_argument('--qtd', type=int, default=50,
                            help='Quantas questoes por categoria (default 50)')
        parser.add_argument('--ate_teto', type=int, default=0,
                            help='Se >0: gera ate cada categoria bater esse teto (ex: 1000)')
        parser.add_argument('--banca', type=str, default='',
                            help='Fixa a banca (default: rotaciona Cebraspe/CESPE/FGV/FCC)')
        parser.add_argument('--pct_ce', type=float, default=0.6,
                            help='Fracao de CE (default 0.6 = 60%%). Resto vira ME.')
        parser.add_argument('--pct_apoio', type=float, default=0.2,
                            help='Fracao com texto de apoio embutido (default 0.2)')
        parser.add_argument('--batch', type=int, default=5,
                            help='Questoes por chamada IA (default 5)')
        parser.add_argument('--delay', type=float, default=2.0,
                            help='Segundos entre chamadas IA (default 2)')
        parser.add_argument('--pular', type=str, default='',
                            help='Categorias a pular (comma-separated)')
        parser.add_argument('--somente', type=str, default='',
                            help='So essas categorias (comma-separated)')
        parser.add_argument('--dry_run', action='store_true')

    def handle(self, *args, **opts):
        cats_lista = CATEGORIAS_PRF[:]
        if opts['somente']:
            filtro = [c.strip() for c in opts['somente'].split(',')]
            cats_lista = [c for c in cats_lista if c in filtro]
        if opts['pular']:
            pular = [c.strip() for c in opts['pular'].split(',')]
            cats_lista = [c for c in cats_lista if c not in pular]

        # Valida categorias (accent-insensitive pra evitar duplicatas orfas
        # tipo "Língua Portuguesa" raiz vs "Português" sob Linguagens)
        import unicodedata
        def _norm(s):
            return ''.join(
                c for c in unicodedata.normalize('NFD', (s or '').lower())
                if unicodedata.category(c) != 'Mn'
            )
        cats_existentes = {_norm(c.nome): c for c in Categoria.objects.all()}
        plano = []
        for nome in cats_lista:
            match = cats_existentes.get(_norm(nome))
            if not match:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠ Categoria "{nome}" nao existe — sera criada no primeiro run'
                ))
                atual = 0
            else:
                # Usa o nome CANONICO do banco pra evitar criar duplicata
                nome_canonico = match.nome
                if nome_canonico != nome:
                    self.stdout.write(f'  ✎ Usando categoria existente {nome_canonico!r} (em vez de {nome!r})')
                    nome = nome_canonico
                atual = match.questao_set.count()

            if opts['ate_teto']:
                gerar = max(0, opts['ate_teto'] - atual)
            else:
                gerar = opts['qtd']

            if gerar <= 0:
                continue

            n_ce = int(gerar * opts['pct_ce'])
            n_me = gerar - n_ce
            plano.append({'nome': nome, 'atual': atual, 'ce': n_ce, 'me': n_me})

        # Exibe plano
        self.stdout.write(self.style.HTTP_INFO('\nPLANO DE GERACAO:'))
        self.stdout.write(f'{"Categoria":<38} {"Atual":>7} {"CE":>5} {"ME":>5} {"Total":>7}')
        self.stdout.write('=' * 66)
        total_gerar = 0
        for p in plano:
            total = p['ce'] + p['me']
            total_gerar += total
            self.stdout.write(
                f'{p["nome"][:38]:<38} {p["atual"]:>7} {p["ce"]:>5} {p["me"]:>5} {total:>7}'
            )
        self.stdout.write('=' * 66)
        self.stdout.write(f'{"TOTAL":<38} {"":>7} {"":>5} {"":>5} {total_gerar:>7}\n')

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING('[DRY-RUN] Nada foi gerado.'))
            return

        if not plano:
            self.stdout.write(self.style.SUCCESS('Nada a gerar — todas as categorias ja atingiram o teto.'))
            return

        # Executa
        criadas_total = 0
        for idx, p in enumerate(plano, 1):
            self.stdout.write(self.style.HTTP_INFO(
                f'\n[{idx}/{len(plano)}] {p["nome"]} (CE:{p["ce"]} + ME:{p["me"]})'
            ))

            # Rotaciona banca se nao fixada
            for tipo, n in [('CE', p['ce']), ('ME', p['me'])]:
                if n <= 0:
                    continue
                banca = opts['banca'] or BANCAS_PRF[idx % len(BANCAS_PRF)]
                # Contagem "antes" — accent-insensitive lookup
                cat_atual = Categoria.objects.filter(nome__iexact=p['nome']).first()
                antes = cat_atual.questao_set.count() if cat_atual else 0
                try:
                    call_command(
                        'gerar_questoes_ia',
                        categoria=p['nome'],
                        qtd=n,
                        batch=opts['batch'],
                        banca=banca,
                        tipo=tipo,
                        delay=opts['delay'],
                        com_texto_apoio=opts['pct_apoio'],
                        criar_se_necessario=True,
                    )
                except SystemExit:
                    pass  # gerar_questoes_ia levanta SystemExit em erros CommandError
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'    Erro ao gerar {tipo} p/ {p["nome"]}: {type(e).__name__}: {str(e)[:80]}'
                    ))
                # Contagem depois (aproximada — pode ter dedup)
                cat_atual = Categoria.objects.filter(nome__iexact=p['nome']).first()
                if cat_atual:
                    depois = cat_atual.questao_set.count()
                    criadas_total += (depois - antes)

                if opts['delay']:
                    time.sleep(opts['delay'])

        self.stdout.write(self.style.SUCCESS(
            f'\n{"=" * 66}\nBATERIA CONCLUIDA: ~{criadas_total} questoes criadas.'
        ))
        self.stdout.write('Proximo passo: gerar justificativas em bulk')
        self.stdout.write('  python manage.py gerar_justificativas_ia --somente_pendentes --limit 500')
