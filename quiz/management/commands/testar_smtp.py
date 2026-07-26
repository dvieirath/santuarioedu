"""
Testa envio de email SMTP configurado no settings.
Uso:
    python manage.py testar_smtp <email_destino>

Ex:
    python manage.py testar_smtp davivieiradesouza4@gmail.com
"""
import traceback
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail


class Command(BaseCommand):
    help = 'Testa envio de 1 email SMTP e mostra diagnostico completo'

    def add_arguments(self, parser):
        parser.add_argument('destino', type=str,
                            help='Email de destino do teste')

    def handle(self, *args, **opts):
        dest = opts['destino']

        self.stdout.write('=' * 60)
        self.stdout.write('CONFIGURACAO SMTP ATUAL:')
        self.stdout.write(f'  EMAIL_BACKEND:      {settings.EMAIL_BACKEND}')
        self.stdout.write(f'  EMAIL_HOST:         {settings.EMAIL_HOST or "(vazio)"}')
        self.stdout.write(f'  EMAIL_PORT:         {settings.EMAIL_PORT}')
        self.stdout.write(f'  EMAIL_HOST_USER:    {settings.EMAIL_HOST_USER or "(vazio)"}')
        self.stdout.write(f'  EMAIL_HOST_PASSWORD:{"*** setada ***" if settings.EMAIL_HOST_PASSWORD else "(VAZIA!)"}')
        self.stdout.write(f'  EMAIL_USE_TLS:      {settings.EMAIL_USE_TLS}')
        self.stdout.write(f'  EMAIL_USE_SSL:      {settings.EMAIL_USE_SSL}')
        self.stdout.write(f'  DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}')
        self.stdout.write('=' * 60)

        if 'console' in settings.EMAIL_BACKEND.lower():
            self.stdout.write(self.style.WARNING(
                '\n⚠ Backend eh CONSOLE — EMAIL_HOST nao configurado ou vazio.\n'
                'Confirma que EMAIL_HOST=smtp-relay.brevo.com esta no Railway → Variables.\n'
            ))

        self.stdout.write(f'\nEnviando email de teste para: {dest}')
        self.stdout.write('Aguarde ~5s...\n')

        try:
            resp = send_mail(
                subject='[Teste SantuarioEdu] SMTP funcionando',
                message=(
                    'Se voce esta lendo esse email, o SMTP do teu SantuarioEdu esta OK.\n\n'
                    'Backend: {}\n'
                    'Host: {}\n'
                    'From: {}\n'
                ).format(settings.EMAIL_BACKEND, settings.EMAIL_HOST, settings.DEFAULT_FROM_EMAIL),
                from_email=None,
                recipient_list=[dest],
                fail_silently=False,
            )
            if resp == 1:
                self.stdout.write(self.style.SUCCESS(
                    '\n✓ Django aceitou e enviou pro SMTP com sucesso.\n'
                    'Se o email nao chegar no inbox de destino:\n'
                    '  1. Confere spam/lixo eletronico\n'
                    '  2. No Brevo → Senders → confirma que sender esta "Verified"\n'
                    '  3. No Brevo → Statistics → Logs — ve se aparece a tentativa\n'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'\n⚠ send_mail retornou {resp} (esperado 1). '
                    'Django nao levantou exception, mas SMTP pode ter rejeitado silenciosamente.'
                ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f'\n✗ FALHOU: {type(e).__name__}: {e}\n'
            ))
            self.stdout.write('Traceback completo:\n')
            traceback.print_exc()
