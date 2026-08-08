"""
Importa em massa TODAS as pastas de provas em provas_pdf/materia_prima/
que ainda nao foram processadas pro BD.

Detecta pastas com PDFs mas sem questoes correspondentes no BD.
Roda importar_pdf_questoes pra cada uma com --auto_categoria.
Faz retry com wait se cota IA esgotar.

Uso:
    python manage.py importar_todas_pastas_pendentes
    python manage.py importar_todas_pastas_pendentes --dry_run
    python manage.py importar_todas_pastas_pendentes --wait_ia 900  # segs pra esperar apos 429
"""
import os
import time
import subprocess
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connections

from quiz.models import Questao, Categoria


MATERIA_PRIMA_DIR = 'provas_pdf/materia_prima'


def _reconectar_db():
    for conn in connections.all():
        try:
            conn.close_if_unusable_or_obsolete()
            conn.ensure_connection()
        except Exception:
            try: conn.close()
            except Exception: pass


# Slug -> (banca, ano) — banca default Cebraspe (script paralelo eh 96% Cebraspe)
def _detectar_ano(slug):
    """Extrai ano de slug tipo INSS_22 -> 2022, PC_RO_22 -> 2022."""
    parts = slug.split('_')
    for p in parts:
        if p.isdigit() and len(p) == 2:
            n = int(p)
            return 2000 + n if n <= 30 else 1900 + n
        elif p.isdigit() and len(p) == 4:
            return int(p)
    return None


class Command(BaseCommand):
    help = 'Importa em massa todas as pastas de provas com PDFs pendentes'

    def add_arguments(self, parser):
        parser.add_argument('--dry_run', action='store_true')
        parser.add_argument('--wait_ia', type=int, default=900,
                            help='Segundos pra esperar apos 429 IA (default 15min)')
        parser.add_argument('--limit', type=int, default=None,
                            help='Processar apenas N pastas (debug)')
        parser.add_argument('--pular', type=str, default='',
                            help='Comma-separated: slugs pra pular (ex: SEE_PE_22,rfb22)')

    def handle(self, *args, **opts):
        dry_run = opts['dry_run']
        wait_ia = opts['wait_ia']
        limit = opts['limit']
        pular = set(s.strip() for s in opts['pular'].split(',') if s.strip())

        if not os.path.isdir(MATERIA_PRIMA_DIR):
            self.stdout.write(self.style.ERROR(
                f'Pasta {MATERIA_PRIMA_DIR} nao existe'
            ))
            return

        # Lista pastas com PDFs
        pendentes = []
        for pasta in sorted(os.listdir(MATERIA_PRIMA_DIR)):
            caminho = os.path.join(MATERIA_PRIMA_DIR, pasta)
            if not os.path.isdir(caminho):
                continue
            if pasta in pular:
                continue

            # Conta PDFs
            n_pdfs = sum(1 for f in os.listdir(caminho)
                         if f.lower().endswith('.pdf'))
            if n_pdfs == 0:
                continue

            # Ve se ja tem questoes desse slug no BD
            cat_nome = f'Prova {pasta}'
            n_bd = Questao.objects.filter(categoria__nome=cat_nome).count()

            pendentes.append({
                'slug':      pasta,
                'caminho':   caminho,
                'n_pdfs':    n_pdfs,
                'n_bd':      n_bd,
                'processar': n_bd == 0,
                'ano':       _detectar_ano(pasta),
            })

        # Mostra o plano
        total_processar = sum(1 for p in pendentes if p['processar'])
        self.stdout.write(self.style.HTTP_INFO(
            f'\n═══ {len(pendentes)} pastas encontradas · {total_processar} pendentes ═══\n'
        ))
        for p in pendentes:
            marker = '⏳ FALTA' if p['processar'] else '✓ ja no BD'
            self.stdout.write(
                f'  {marker:12s} {p["slug"]:35s} PDFs={p["n_pdfs"]:3d}  BD={p["n_bd"]}'
            )

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\n[DRY RUN] Rode sem --dry_run pra processar.'
            ))
            return

        pra_processar = [p for p in pendentes if p['processar']]
        if limit:
            pra_processar = pra_processar[:limit]

        self.stdout.write(self.style.HTTP_INFO(
            f'\n═══ Processando {len(pra_processar)} pastas ═══\n'
        ))

        total_criadas = 0
        for i, p in enumerate(pra_processar, 1):
            _reconectar_db()
            self.stdout.write('\n' + '━' * 60)
            self.stdout.write(self.style.SUCCESS(
                f'[{i}/{len(pra_processar)}] {p["slug"]} ({p["n_pdfs"]} PDFs)'
            ))
            self.stdout.write('━' * 60)

            antes = Questao.objects.count()

            # Chama importar_pdf_questoes via call_command
            try:
                call_command(
                    'importar_pdf_questoes',
                    pasta=p['caminho'],
                    categoria=f'Prova {p["slug"]}',
                    auto_categoria=True,
                    banca='Cebraspe',  # 96% das provas sao Cebraspe
                    ano=p['ano'] or 2023,
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Erro processando {p["slug"]}: {e}'))
                # Se 429, espera
                if '429' in str(e) or 'quota' in str(e).lower():
                    self.stdout.write(self.style.WARNING(
                        f'Cota IA esgotada. Esperando {wait_ia}s...'
                    ))
                    time.sleep(wait_ia)
                    _reconectar_db()
                continue

            depois = Questao.objects.count()
            criadas = depois - antes
            total_criadas += criadas
            self.stdout.write(self.style.SUCCESS(
                f'  → {criadas} questoes criadas (total ate agora: {total_criadas})'
            ))

            # Pequena pausa entre pastas (evita rate limit)
            time.sleep(2)

        self.stdout.write('\n' + '═' * 60)
        self.stdout.write(self.style.SUCCESS(
            f'✓ {total_criadas} questoes NOVAS importadas de {len(pra_processar)} pastas'
        ))
        self.stdout.write(
            f'\nProximo passo: python manage.py reclassificar_por_tema'
        )
