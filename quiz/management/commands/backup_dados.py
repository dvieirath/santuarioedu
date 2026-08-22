"""
Backup rápido dos dados críticos do banco em JSON.

Uso:
    python manage.py backup_dados                 # cria em backups/
    python manage.py backup_dados --dir /path     # destino custom
    python manage.py backup_dados --manter 10     # limita histórico

Em produção, agende via cron/celery beat pra rodar diariamente.
"""
import os
from datetime import datetime
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Faz dump dos dados críticos em JSON para backup'

    APPS_CRITICOS = [
        'quiz.Questao', 'quiz.Alternativa', 'quiz.Categoria',
        'quiz.RespostaUsuario', 'quiz.Simulado', 'quiz.RespostaSimulado',
        'quiz.MetaEstudo', 'quiz.Perfil',
        'quiz.TicketSuporte', 'quiz.RespostaTicket',
        'quiz.LogSistema',
        'auth.User', 'auth.Group',
    ]

    def add_arguments(self, parser):
        parser.add_argument('--dir', default='backups', help='Pasta destino')
        parser.add_argument('--manter', type=int, default=7,
                            help='Quantos backups manter (mais antigos são deletados)')

    def handle(self, *args, **opts):
        dest = Path(opts['dir'])
        dest.mkdir(exist_ok=True)

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        arquivo = dest / f'backup_{ts}.json'

        self.stdout.write(f'▶ Dumping para {arquivo}…')

        with open(arquivo, 'w', encoding='utf-8') as f:
            call_command(
                'dumpdata',
                *self.APPS_CRITICOS,
                indent=2, stdout=f, format='json',
                natural_foreign=True, natural_primary=True,
            )

        tamanho_kb = arquivo.stat().st_size // 1024
        self.stdout.write(self.style.SUCCESS(f'✓ {tamanho_kb} KB salvos'))

        # Rotação — mantém só os N mais recentes
        backups = sorted(dest.glob('backup_*.json'), reverse=True)
        if len(backups) > opts['manter']:
            for antigo in backups[opts['manter']:]:
                antigo.unlink()
                self.stdout.write(f'  🗑  Removido antigo: {antigo.name}')

        self.stdout.write(
            self.style.HTTP_INFO(
                f'\nRestaurar depois:\n'
                f'  python manage.py loaddata {arquivo}'
            )
        )
