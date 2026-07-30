"""
Signal handlers de emails transacionais.

Signals de auditoria/seguranca ficam em signals_audit.py.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.dispatch import receiver
from django.template.loader import render_to_string

from allauth.account.signals import email_confirmed

logger = logging.getLogger(__name__)


@receiver(email_confirmed)
def enviar_welcome_email(request, email_address, **kwargs):
    """Dispara welcome email quando usuario confirma email pela 1a vez.

    O sinal email_confirmed do allauth dispara sempre que um EmailAddress
    passa de unverified -> verified. Como email_verification eh mandatory
    na aplicacao, isso equivale ao "primeiro login efetivo" do usuario.
    """
    user = email_address.user
    if not user or not user.email:
        return

    nome = (user.first_name or user.username or 'estudante').strip()
    site_url = getattr(settings, 'SITE_URL', 'https://santuarioedu.com.br').rstrip('/')

    contexto = {
        'nome': nome,
        'site_url': site_url,
        'url_onboarding': f'{site_url}/onboarding/',
        'url_estudar':    f'{site_url}/estudar/',
        'url_perfil':     f'{site_url}/perfil/',
        'suporte_email':  getattr(settings, 'SUPORTE_EMAIL', 'suporte@santuarioedu.com.br'),
    }

    try:
        assunto  = f'Bem-vindo(a) ao SantuarioEdu, {nome}! 🎁 7 dias PRO grátis liberados'
        corpo_txt  = render_to_string('emails/welcome.txt', contexto)
        corpo_html = render_to_string('emails/welcome.html', contexto)

        msg = EmailMultiAlternatives(
            subject     = assunto,
            body        = corpo_txt,
            from_email  = getattr(settings, 'DEFAULT_FROM_EMAIL',
                                  'SantuarioEdu <noreply@santuarioedu.com.br>'),
            to          = [user.email],
        )
        msg.attach_alternative(corpo_html, 'text/html')
        msg.send(fail_silently=False)
        logger.info(f'Welcome email enviado para {user.email}')
    except Exception as e:
        # Nunca deixa a falha do welcome bloquear o fluxo de confirmacao de email
        logger.error(f'Falha ao enviar welcome email para {user.email}: {e}')
