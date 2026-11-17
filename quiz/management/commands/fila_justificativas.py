"""
Relatório da fila de justificativas por IA — somente leitura.

Mostra quantas questões liberadas estão sem justificativa, quantas são elegíveis
para geração automática, quais estão barradas por defeito estrutural e qual a
ordem de ataque (demo → respondidas → restantes).

Uso:
    python manage.py fila_justificativas
    python manage.py fila_justificativas --limite 40
    python manage.py fila_justificativas --categoria "Direito Constitucional"
    python manage.py fila_justificativas --csv output/fila_justificativas.csv
    python manage.py fila_justificativas --incluir_pendentes
"""
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from quiz.models import Categoria, Questao
from quiz.justificativas_fila import (
    exportar_csv,
    selecionar,
    sem_justificativa,
    resumo,
)


class Command(BaseCommand):
    help = 'Relatório (somente leitura) da fila de justificativas por IA'

    def add_arguments(self, parser):
        parser.add_argument('--categoria', type=str, default='',
                            help='Filtrar por nome de categoria')
        parser.add_argument('--limite', type=int, default=20,
                            help='Quantas questões mostrar da fila (default 20)')
        parser.add_argument('--csv', type=str, default='',
                            help='Exportar a fila completa (elegíveis) para CSV')
        parser.add_argument('--incluir_pendentes', action='store_true',
                            help='Incluir questões ainda não aprovadas')
        parser.add_argument('--incluir_inelegiveis', action='store_true',
                            help='Mostrar também as questões barradas por defeito')

    def handle(self, *args, **opts):
        qs = sem_justificativa(incluir_pendentes=opts['incluir_pendentes'])

        if opts['categoria']:
            try:
                cat = Categoria.objects.get(nome__iexact=opts['categoria'])
            except Categoria.DoesNotExist:
                raise CommandError(f'Categoria "{opts["categoria"]}" não encontrada')
            qs = qs.filter(categoria=cat)

        dados = resumo(qs)
        com_justificativa = (
            Questao.objects.filter(revisada=True, rejeitada_definitiva=False)
            .exclude(Q(justificativa__isnull=True) | Q(justificativa=''))
            .count()
        )

        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('FILA DE JUSTIFICATIVAS'))
        self.stdout.write(f'  Liberadas com justificativa .... {com_justificativa}')
        self.stdout.write(
            f'  Sem justificativa ............. {dados["total_sem_justificativa"]}'
        )
        self.stdout.write(
            self.style.SUCCESS(f'  Elegíveis para IA ............ {dados["elegiveis"]}')
        )
        self.stdout.write(
            self.style.WARNING(f'  Barradas (defeito) ........... {dados["inelegiveis"]}')
        )
        self.stdout.write(
            f'  Da demo pública .............. {dados["demo_sem_justificativa"]}'
            f' de {dados["demo_total"]}'
        )
        self.stdout.write(
            f'  Já respondidas por alguém ..... {dados["respondidas_sem_justificativa"]}'
        )

        if dados['motivos']:
            self.stdout.write('')
            self.stdout.write('Motivos de bloqueio:')
            for motivo, n in dados['motivos'].most_common():
                self.stdout.write(f'  {n:>5}  {motivo}')

        if dados['elegiveis_por_categoria']:
            self.stdout.write('')
            self.stdout.write('Elegíveis por categoria (top 10):')
            for nome, n in dados['elegiveis_por_categoria'].most_common(10):
                self.stdout.write(f'  {n:>5}  {nome}')

        fila = selecionar(
            qs,
            limite=opts['limite'],
            incluir_inelegiveis=opts['incluir_inelegiveis'],
        )
        if fila:
            self.stdout.write('')
            self.stdout.write(self.style.HTTP_INFO('Próximas da fila:'))
            for item in fila:
                q = item['questao']
                if item['demo']:
                    marca = 'DEMO'
                elif item['respostas']:
                    marca = f'{item["respostas"]} resp.'
                else:
                    marca = 'nova'
                bloqueio = (' — bloqueada: ' + ', '.join(item['motivos'])
                            if item['motivos'] else '')
                self.stdout.write(
                    f'  Q#{q.id} [{marca}] {q.categoria.nome[:28]}: '
                    f'{(q.texto or "")[:60]}…{bloqueio}'
                )

        if dados['exemplos_inelegiveis']:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Exemplos barrados (corrigir antes):'))
            for ex in dados['exemplos_inelegiveis']:
                self.stdout.write(
                    f'  Q#{ex["id"]} [{ex["categoria"][:24]}] '
                    f'{", ".join(ex["motivos"])} — {ex["texto"]}…'
                )

        if opts['csv']:
            itens = selecionar(qs, incluir_inelegiveis=opts['incluir_inelegiveis'])
            caminho = exportar_csv(itens, opts['csv'])
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(f'CSV com {len(itens)} linhas: {caminho}'))

        self.stdout.write('')
        if dados['elegiveis']:
            self.stdout.write(
                'Próximo passo: python manage.py gerar_justificativas_ia '
                f'--limit {min(dados["elegiveis"], 50)}'
            )
        else:
            self.stdout.write('Nada elegível no momento — corrija os itens barrados.')
