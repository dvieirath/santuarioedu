"""
Descarta, sem IA e sem custo, as questões pendentes geradas por IA que têm
defeito comprovável (ver `quiz/triagem_pendentes.py`).

    python manage.py triar_pendentes_ia              # só simula e gera relatório
    python manage.py triar_pendentes_ia --aplicar    # faz backup e descarta

Descartar aqui é marcar `rejeitada_definitiva=True` com o motivo. A questão não
é apagada: o relatório lista os ids e dá para desfazer pelo painel ou pelo
backup.
"""
import json
import shutil
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from quiz.models import Questao
from quiz.triagem_pendentes import PREFIXO_MOTIVO, motivo_de_rejeicao, pendentes_de_ia


class Command(BaseCommand):
    help = 'Descarta sem IA as pendentes de IA com defeito comprovável'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true',
                            help='Grava no banco (sem isto, só simula)')
        parser.add_argument('--sem_backup', action='store_true',
                            help='Não copiar o SQLite antes de aplicar')

    def handle(self, *args, **opts):
        carimbo = timezone.localtime().strftime('%Y%m%d_%H%M%S')
        base = Path(settings.BASE_DIR)
        pasta = base / 'output' / f'triagem_pendentes_ia_{carimbo}'
        pasta.mkdir(parents=True, exist_ok=True)

        grupos = defaultdict(list)
        total = 0
        for q in pendentes_de_ia():
            total += 1
            motivo = motivo_de_rejeicao(q, list(q.alternativa_set.all()))
            if motivo:
                grupos[motivo].append(q)
        descartar = sum(len(v) for v in grupos.values())

        relatorio = {
            'quando': carimbo,
            'aplicado': bool(opts['aplicar']),
            'pendentes_de_ia_antes': total,
            'descartadas': descartar,
            'seguem_para_conferencia': total - descartar,
            'por_motivo': {m: len(qs) for m, qs in grupos.items()},
            'questoes': [
                {'id': q.id, 'tipo': q.tipo, 'categoria': q.categoria.nome,
                 'motivo': m, 'texto': (q.texto or '')[:300]}
                for m, qs in grupos.items() for q in qs
            ],
        }

        self.stdout.write(f'Pendentes de IA: {total}')
        for motivo, qs in sorted(grupos.items(), key=lambda kv: -len(kv[1])):
            self.stdout.write(f'  {len(qs):5d}  {motivo}')
        self.stdout.write(f'  {descartar:5d}  TOTAL a descartar')
        self.stdout.write(f'  {total - descartar:5d}  seguem para conferência de gabarito')

        if opts['aplicar'] and descartar:
            banco = Path(settings.DATABASES['default']['NAME'])
            if not opts['sem_backup'] and banco.exists():
                destino = base / 'backups' / f'antes_triagem_pendentes_ia_{carimbo}.sqlite3'
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(banco, destino)
                relatorio['backup'] = str(destino.relative_to(base))
                self.stdout.write(f'Backup: {relatorio["backup"]}')
            with transaction.atomic():
                for motivo, qs in grupos.items():
                    Questao.objects.filter(
                        id__in=[q.id for q in qs], revisada=False,
                    ).update(rejeitada_definitiva=True,
                             motivo_rejeicao=PREFIXO_MOTIVO + motivo)
            relatorio['pendentes_de_ia_depois'] = pendentes_de_ia().count()
            self.stdout.write(self.style.SUCCESS(
                f'{descartar} descartadas. Restam {relatorio["pendentes_de_ia_depois"]} pendentes de IA.'))
        elif not opts['aplicar']:
            self.stdout.write(self.style.WARNING('Simulação. Use --aplicar para gravar.'))

        (pasta / 'relatorio.json').write_text(
            json.dumps(relatorio, ensure_ascii=False, indent=1), encoding='utf-8')
        self.stdout.write(f'Relatório: {(pasta / "relatorio.json").relative_to(base)}')
