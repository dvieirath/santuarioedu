"""
Valida integridade das questoes ME (multipla escolha):
- Deve ter EXATAMENTE 1 alternativa correta
- Deve ter >= 2 alternativas no total

Casos violados por default sao MARCADOS revisada=False (some do quiz).
Reversivel: user pode revisar no admin e reaprovar.

Uso:
    python manage.py validar_integridade_questoes                # apenas reporta
    python manage.py validar_integridade_questoes --fix          # marca revisada=False
    python manage.py validar_integridade_questoes --fix --deletar # deleta (irreversivel)

Filtros:
    --apenas_revisadas   so verifica revisada=True (foco no que ta em uso)
    --detalhado          mostra texto completo das quebradas
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from quiz.models import Questao, Alternativa


class Command(BaseCommand):
    help = 'Valida integridade das questoes ME (exatamente 1 correta)'

    def add_arguments(self, parser):
        parser.add_argument('--fix', action='store_true',
                            help='Marca questoes bugadas como revisada=False')
        parser.add_argument('--deletar', action='store_true',
                            help='DELETA questoes bugadas (irreversivel). Requer --fix.')
        parser.add_argument('--apenas_revisadas', action='store_true',
                            help='So verifica questoes com revisada=True')
        parser.add_argument('--detalhado', action='store_true',
                            help='Mostra texto completo das questoes com problema')

    def handle(self, *args, **opts):
        fix = opts['fix']
        deletar = opts['deletar'] and fix
        apenas_rev = opts['apenas_revisadas']
        detalhado = opts['detalhado']

        qs = Questao.objects.filter(tipo='ME')
        if apenas_rev:
            qs = qs.filter(revisada=True)

        # Anota contagem de alternativas totais e corretas
        qs = qs.annotate(
            total_alt=Count('alternativa'),
            total_corretas=Count('alternativa', filter=Q(alternativa__correta=True)),
        )

        # Casos invalidos:
        # - 0 corretas OU > 1 correta
        # - < 2 alternativas totais
        bugadas = list(qs.exclude(total_corretas=1) | qs.filter(total_alt__lt=2))
        # dedup se caiu nos dois filtros
        bugadas = list({q.id: q for q in bugadas}.values())

        total = qs.count()
        self.stdout.write(self.style.HTTP_INFO(
            f'\n═══ Validando {total} questoes ME '
            f'{"(apenas revisadas)" if apenas_rev else "(todas)"} ═══\n'
        ))

        if not bugadas:
            self.stdout.write(self.style.SUCCESS('✓ Todas as questoes ME estao integras'))
            return

        # Agrupa por tipo de defeito
        sem_correta = [q for q in bugadas if q.total_corretas == 0]
        multi_corretas = [q for q in bugadas if q.total_corretas > 1]
        poucas_alt = [q for q in bugadas if q.total_alt < 2]

        self.stdout.write(self.style.ERROR(
            f'✗ {len(bugadas)} questoes com defeito ({len(bugadas) / total * 100:.1f}%)'
        ))
        self.stdout.write(f'  • {len(sem_correta)} sem correta marcada')
        self.stdout.write(f'  • {len(multi_corretas)} com > 1 correta')
        self.stdout.write(f'  • {len(poucas_alt)} com < 2 alternativas')
        self.stdout.write('')

        if detalhado:
            for q in bugadas[:20]:  # cap em 20 pra nao poluir
                self.stdout.write(f'  ID {q.id} [{q.categoria.nome if q.categoria else "?"}] '
                                  f'{q.total_corretas} corretas de {q.total_alt}')
                self.stdout.write(f'    texto: {q.texto[:100]}...')
                if q.revisada:
                    self.stdout.write(self.style.WARNING(f'    ⚠ REVISADA=True (em uso no quiz)'))
                self.stdout.write('')
            if len(bugadas) > 20:
                self.stdout.write(f'  ... e mais {len(bugadas) - 20} questoes')

        if not fix:
            self.stdout.write(self.style.WARNING(
                '\nModo somente-leitura. Rode com --fix pra marcar revisada=False '
                'ou --fix --deletar pra remover.'
            ))
            return

        ids = [q.id for q in bugadas]
        if deletar:
            n = Questao.objects.filter(id__in=ids).delete()[0]
            self.stdout.write(self.style.SUCCESS(f'\n✓ {n} questoes DELETADAS'))
        else:
            n = Questao.objects.filter(id__in=ids).update(revisada=False)
            self.stdout.write(self.style.SUCCESS(
                f'\n✓ {n} questoes marcadas revisada=False (sumiram do quiz, '
                'podem ser revisadas no admin depois)'
            ))
