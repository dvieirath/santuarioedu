"""
Baixa PDFs de provas oficiais de concursos publicos a partir de URLs
configuraveis em JSON. Provas aplicadas sao atos administrativos publicos
(Lei de Acesso a Informacao), publicadas em areas abertas dos sites das
bancas.

Uso:
    # Baixa tudo do config default
    python manage.py baixar_provas_oficiais

    # Config custom
    python manage.py baixar_provas_oficiais --config data/minhas_provas.json

    # So mostra o plano sem baixar
    python manage.py baixar_provas_oficiais --dry_run

    # Filtra por banca
    python manage.py baixar_provas_oficiais --filtro Cebraspe

    # Pasta destino diferente
    python manage.py baixar_provas_oficiais --pasta pdfs_prov/

Depois de baixar, rode:
    python manage.py importar_pdf_questoes --pasta pdfs/ --categoria "Direito > Direito Constitucional"
"""
import hashlib
import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Baixa PDFs de provas oficiais listadas em JSON de configuracao'

    def add_arguments(self, parser):
        parser.add_argument('--config', type=str,
                            default='data/provas_oficiais_urls.json',
                            help='Caminho pro JSON com lista de provas')
        parser.add_argument('--pasta', type=str, default='pdfs/',
                            help='Pasta destino dos PDFs')
        parser.add_argument('--filtro', type=str, default='',
                            help='Filtra provas por banca (ex: Cebraspe) ou nome parcial')
        parser.add_argument('--dry_run', action='store_true',
                            help='Mostra o plano sem baixar')
        parser.add_argument('--force', action='store_true',
                            help='Rebaixa arquivos que ja existem')
        parser.add_argument('--timeout', type=int, default=60,
                            help='Timeout em segundos por download (default 60)')

    def handle(self, *args, **opts):
        try:
            import requests
        except ImportError:
            raise CommandError(
                'Requer requests: pip install requests'
            )

        config_path = opts['config']
        if not os.path.exists(config_path):
            raise CommandError(f'Config nao encontrado: {config_path}\n'
                             f'Copie o template de data/provas_oficiais_urls.json')

        with open(config_path, 'r', encoding='utf-8') as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError as e:
                raise CommandError(f'JSON invalido: {e}')

        provas = config.get('provas', [])
        if not provas:
            raise CommandError('Config nao tem lista "provas"')

        # Aplica filtro
        filtro = opts['filtro'].lower().strip()
        if filtro:
            provas = [p for p in provas if
                     filtro in p.get('banca', '').lower() or
                     filtro in p.get('nome', '').lower()]

        # Cria pasta destino
        pasta = Path(opts['pasta'])
        if not opts['dry_run']:
            pasta.mkdir(parents=True, exist_ok=True)

        self.stdout.write(self.style.HTTP_INFO(
            f'\n═══ {len(provas)} provas a processar ═══\n'
        ))

        baixadas = 0
        ja_existentes = 0
        erros = 0
        total_kb = 0

        for i, prova in enumerate(provas, 1):
            nome = prova.get('nome', '')
            banca = prova.get('banca', '')
            ano = prova.get('ano', '')
            url = prova.get('url', '')
            arquivo_local = prova.get('arquivo_local', '')

            if not url or not arquivo_local:
                self.stdout.write(self.style.WARNING(
                    f'[{i}/{len(provas)}] ⊘ {nome}: sem url ou arquivo_local'
                ))
                erros += 1
                continue

            destino = pasta / arquivo_local

            # Ja existe?
            if destino.exists() and not opts['force']:
                kb = destino.stat().st_size / 1024
                self.stdout.write(
                    f'[{i}/{len(provas)}] = {arquivo_local} ({kb:.0f} KB) — ja existe'
                )
                ja_existentes += 1
                continue

            if opts['dry_run']:
                self.stdout.write(
                    f'[{i}/{len(provas)}] ↓ [DRY] {arquivo_local} ({banca}/{ano})'
                )
                self.stdout.write(f'    URL: {url}')
                continue

            # Baixa
            self.stdout.write(
                f'[{i}/{len(provas)}] ↓ {arquivo_local} ({banca}/{ano})...',
                ending=' '
            )
            self.stdout.flush()

            try:
                headers = {
                    # User-agent generico pra evitar bloqueio simples de bots
                    'User-Agent': 'Mozilla/5.0 (SantuarioEdu - importacao de provas publicas)',
                }
                r = requests.get(url, headers=headers, timeout=opts['timeout'], stream=True)
                r.raise_for_status()

                # Valida content-type — deve ser PDF
                ctype = r.headers.get('Content-Type', '').lower()
                if 'pdf' not in ctype and 'octet-stream' not in ctype:
                    self.stdout.write(self.style.WARNING(
                        f'⚠ Content-Type suspeito: {ctype}'
                    ))

                # Salva em chunks pra nao estourar memoria
                bytes_baixados = 0
                with open(destino, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            bytes_baixados += len(chunk)

                kb = bytes_baixados / 1024
                total_kb += kb
                self.stdout.write(self.style.SUCCESS(f'✓ {kb:.0f} KB'))
                baixadas += 1

                # Se muito pequeno (< 10 KB), pode ser pagina de erro HTML
                if kb < 10:
                    self.stdout.write(self.style.WARNING(
                        f'    ⚠ Arquivo muito pequeno — pode ser pagina de erro. '
                        f'Verifique manualmente.'
                    ))

            except requests.exceptions.Timeout:
                self.stdout.write(self.style.ERROR(f'✗ Timeout apos {opts["timeout"]}s'))
                erros += 1
                if destino.exists():
                    destino.unlink()
            except requests.exceptions.HTTPError as e:
                self.stdout.write(self.style.ERROR(f'✗ HTTP {e.response.status_code}'))
                erros += 1
                if destino.exists():
                    destino.unlink()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ {type(e).__name__}: {e}'))
                erros += 1
                if destino.exists():
                    destino.unlink()

        # Resumo
        self.stdout.write('\n' + '═' * 70)
        self.stdout.write(self.style.SUCCESS(
            f'✓ {baixadas} baixadas ({total_kb / 1024:.1f} MB)'
        ))
        if ja_existentes:
            self.stdout.write(f'= {ja_existentes} ja existiam (use --force pra rebaixar)')
        if erros:
            self.stdout.write(self.style.ERROR(f'✗ {erros} erros'))

        if baixadas > 0 and not opts['dry_run']:
            self.stdout.write(self.style.HTTP_INFO(
                f'\nProximo passo:\n'
                f'  python manage.py importar_pdf_questoes '
                f'--pasta {pasta}/ --categoria "Direito > Direito Constitucional"'
            ))
