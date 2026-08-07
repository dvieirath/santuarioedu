"""
Signal handlers de emails transacionais.

Signals de auditoria/seguranca ficam em signals_audit.py.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.dispatch import receiver
from django.template.loader import render_to_string

from allauth.account.signals import email_confirmed, user_signed_up

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


@receiver(user_signed_up)
def processar_referral_no_signup(request, user, **kwargs):
    """
    Processa referral no momento do cadastro (allauth user_signed_up).
    Requer que o ?ref=<codigo> esteja na session (colocado pela middleware
    de captura em quiz/middleware.py) OU cookie 'ref_code'.

    Cria Referencia + entrega XP pra ambos. Idempotente: OneToOneField
    em `convidado` garante que so acontece uma vez por usuario.
    """
    try:
        codigo = None
        if request:
            codigo = request.session.get('ref_code') or request.COOKIES.get('ref_code')
        if not codigo:
            return

        from django.contrib.auth import get_user_model
        from quiz.models import Referencia, NivelUsuario

        User = get_user_model()
        try:
            convidador = User.objects.get(username=codigo)
        except User.DoesNotExist:
            return

        # Nao pode auto-convidar
        if convidador.id == user.id:
            return

        # Cria referencia (unica por convidado)
        ref, criada = Referencia.objects.get_or_create(
            convidado=user,
            defaults={'convidador': convidador},
        )
        if not criada:
            return  # ja tinha registro

        # Entrega XP
        nivel_convidador, _ = NivelUsuario.objects.get_or_create(usuario=convidador)
        nivel_convidador.adicionar_xp(ref.xp_convidador)

        nivel_convidado, _ = NivelUsuario.objects.get_or_create(usuario=user)
        nivel_convidado.adicionar_xp(ref.xp_convidado)

        # Limpa session
        if request:
            request.session.pop('ref_code', None)

        logger.info(f'Referral: {convidador.username} -> {user.username} '
                    f'(+{ref.xp_convidador}/+{ref.xp_convidado} XP)')
    except Exception as e:
        logger.error(f'Falha processar referral: {e}')
