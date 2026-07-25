"""
Migra arquivos da pasta local media/ pro Cloudflare R2 (S3-compat).

Roda 1x depois que R2 estiver configurado em prod. Depois desse envio,
todo upload novo ja vai direto pro R2 (via django-storages).

Uso:
    # Envia tudo em media/ preservando estrutura
    python manage.py migrar_media_para_r2

    # Dry-run (lista o que enviaria, sem fazer)
    python manage.py migrar_media_para_r2 --dry_run

    # Ignora arquivos que ja estao no bucket (nao re-envia)
    python manage.py migrar_media_para_r2 --pular_existentes
"""
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Migra arquivos media/ locais pro bucket S3/R2 configurado'

    def add_arguments(self, parser):
        parser.add_argument('--dry_run', action='store_true')
        parser.add_argument('--pular_existentes', action='store_true',
                            help='Nao re-envia arquivos ja presentes no bucket')

    def handle(self, *args, **opts):
        # Confirma que S3 esta configurado
        if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_STORAGE_BUCKET_NAME:
            raise CommandError(
                'AWS_ACCESS_KEY_ID / AWS_STORAGE_BUCKET_NAME nao configurados. '
                'Configure primeiro em Railway → Variables.'
            )

        try:
            import boto3
            from botocore.client import Config as _BotoConfig
        except ImportError:
            raise CommandError(
                'boto3 nao instalado. Rode: pip install boto3'
            )

        # Cliente S3 apontando pro R2
        client = boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            config=_BotoConfig(
                signature_version=settings.AWS_S3_SIGNATURE_VERSION,
                s3={'addressing_style': settings.AWS_S3_ADDRESSING_STYLE},
            ),
        )

        # media/ local
        media_root = Path(settings.BASE_DIR) / 'media'
        if not media_root.exists():
            self.stdout.write(self.style.WARNING(
                f'Pasta {media_root} nao existe. Nada a migrar.'
            ))
            return

        # Lista arquivos ja no bucket (pra evitar re-upload)
        existentes = set()
        if opts['pular_existentes']:
            self.stdout.write('Listando objetos ja no bucket...')
            paginator = client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=settings.AWS_STORAGE_BUCKET_NAME):
                for obj in page.get('Contents', []) or []:
                    existentes.add(obj['Key'])
            self.stdout.write(f'  {len(existentes)} objetos ja no bucket')

        # Percorre media/ local
        arquivos = [p for p in media_root.rglob('*') if p.is_file()]
        self.stdout.write(self.style.HTTP_INFO(
            f'\n{len(arquivos)} arquivo(s) encontrados em {media_root}\n'
        ))

        if opts['dry_run']:
            for p in arquivos[:20]:
                key = str(p.relative_to(media_root)).replace(os.sep, '/')
                self.stdout.write(f'  → {key}  ({p.stat().st_size} bytes)')
            if len(arquivos) > 20:
                self.stdout.write(f'  ... e mais {len(arquivos) - 20}')
            self.stdout.write(self.style.WARNING('\n[DRY-RUN] Nada enviado.'))
            return

        # Envia
        enviados = 0
        pulados = 0
        erros = 0
        for i, p in enumerate(arquivos, 1):
            key = str(p.relative_to(media_root)).replace(os.sep, '/')
            if key in existentes:
                pulados += 1
                continue

            # Detecta content-type basico
            ext = p.suffix.lower()
            content_type = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp',
                '.pdf': 'application/pdf',
                '.txt': 'text/plain', '.md': 'text/markdown',
            }.get(ext, 'application/octet-stream')

            try:
                with open(p, 'rb') as f:
                    client.put_object(
                        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                        Key=key,
                        Body=f,
                        ContentType=content_type,
                        ACL='public-read',
                    )
                enviados += 1
                if enviados % 10 == 0 or enviados == 1:
                    self.stdout.write(f'  [{i}/{len(arquivos)}] {key}')
            except Exception as e:
                erros += 1
                self.stdout.write(self.style.ERROR(
                    f'  ERRO {key}: {type(e).__name__}: {str(e)[:100]}'
                ))

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(
            f'ENVIADOS: {enviados}  ·  PULADOS: {pulados}  ·  ERROS: {erros}'
        ))
        if enviados:
            self.stdout.write(
                f'\nURL publica no formato: {settings.MEDIA_URL}<caminho-do-arquivo>'
            )
