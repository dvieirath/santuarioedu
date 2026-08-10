"""
Detecta questoes com justificativa em formato ANTIGO/SIMPLES (nao segue
padrao SantuarioEdu com marcadores 🔍/⚠️/🧠) e:

1. Apaga a justificativa
2. Marca revisada=False (volta pra fila de revisao)

Motivo: importar_pdf_questoes --com_justificativa antigo gerava
justificativas simples (2-4 paragrafos), quebrando o padrao visual
das questoes originais.

Fluxo pos-cleanup:
    python manage.py gerar_justificativas_ia --somente_pendentes --limit 100
    (gera no padrao correto, com marcadores)

Uso:
    python manage.py limpar_justificativas_fora_padrao --dry_run
    python manage.py limpar_justificativas_fora_padrao
    python manage.py limpar_justificativas_fora_padrao --manter_revisada  # nao volta pra pendente
"""
from django.core.management.base import BaseCommand
from django.db import connections

from quiz.models import Questao


def _reconectar_db():
    for conn in connections.all():
        try:
            conn.close_if_unusable_or_obsolete()
            conn.ensure_connection()
        except Exception:
            try: conn.close()
            except Exception: pass


# Marcadores do padrao SantuarioEdu — questoes SEM esses estao fora do padrao
MARCADORES_PADRAO = ['🔍', '⚠️', '🧠', '📚', '🎯', '💡']


class Command(BaseCommand):
    help = 'Limpa justificativas fora do padrao SantuarioEdu (sem marcadores 🔍/⚠️/🧠)'

    def add_arguments(self, parser):
        parser.add_argument('--dry_run', action='store_true')
        parser.add_argument('--manter_revisada', action='store_true',
                            help='So apaga a justificativa, sem voltar pra pendente')
        parser.add_argument('--min_chars', type=int, default=50,
                            help='Ignora justificativas < N chars (default 50)')

    def handle(self, *args, **opts):
        dry_run = opts['dry_run']
        manter_revisada = opts['manter_revisada']
        min_chars = opts['min_chars']

        _reconectar_db()

        # Busca todas com justificativa nao-vazia
        qs = (Questao.objects
              .exclude(justificativa__isnull=True)
              .exclude(justificativa=''))

        total = qs.count()
        self.stdout.write(self.style.HTTP_INFO(
            f'\n═══ Analisando {total} questoes com justificativa ═══\n'
        ))

        # Itera e categoriza
        fora_padrao_ids = []
        curtas_ids = []
        no_padrao = 0

        for q in qs.iterator(chunk_size=200):
            just = q.justificativa or ''
            if len(just) < min_chars:
                curtas_ids.append(q.id)
                continue
            tem_marcador = any(m in just for m in MARCADORES_PADRAO)
            if tem_marcador:
                no_padrao += 1
            else:
                fora_padrao_ids.append(q.id)

        self.stdout.write(f'  ✓ No padrao SantuarioEdu (com marcadores 🔍/⚠️/🧠): {no_padrao}')
        self.stdout.write(self.style.WARNING(
            f'  ⚠ Fora do padrao (sem marcadores): {len(fora_padrao_ids)}'
        ))
        self.stdout.write(f'  ⊘ Curtas (< {min_chars} chars): {len(curtas_ids)}')

        alvos = fora_padrao_ids + curtas_ids

        if not alvos:
            self.stdout.write(self.style.SUCCESS(
                '\n✓ Nenhuma questao pra limpar. BD ja esta no padrao.'
            ))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'\n[DRY RUN] Seriam limpas {len(alvos)} questoes '
                f'(justificativa=null{"" if manter_revisada else ", revisada=False"})'
            ))
            return

        # Executa em batches pra evitar timeout
        BATCH = 500
        limpas = 0
        for i in range(0, len(alvos), BATCH):
            _reconectar_db()
            batch = alvos[i:i+BATCH]
            update_kwargs = {'justificativa': ''}
            if not manter_revisada:
                update_kwargs['revisada'] = False
            n = Questao.objects.filter(id__in=batch).update(**update_kwargs)
            limpas += n
            self.stdout.write(f'  → Lote {min(i+BATCH, len(alvos))}/{len(alvos)}: {limpas} limpas')

        self.stdout.write('\n' + '═' * 60)
        self.stdout.write(self.style.SUCCESS(
            f'✓ {limpas} justificativas apagadas'
        ))
        if not manter_revisada:
            self.stdout.write(self.style.SUCCESS(
                f'✓ {limpas} questoes voltaram pra revisada=False (fila de aprovacao)'
            ))

        self.stdout.write(self.style.HTTP_INFO(
            '\nProximo passo — gerar novas no padrao correto:\n'
            '  python manage.py gerar_justificativas_ia --somente_pendentes --limit 100\n'
            '\nDepois revisar em /admin-revisao/'
        ))
