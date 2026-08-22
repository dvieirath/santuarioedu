"""
Auditoria de eventos sensíveis de segurança.

Conecta signals do Django/allauth para registrar em LogSistema:
- login bem-sucedido
- login falho
- logout
- mudança de senha
- novo usuário criado
- bloqueio pelo django-axes
"""
from django.contrib.auth.signals import (
    user_logged_in, user_logged_out, user_login_failed,
)
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import LogSistema


def _client_ip(request):
    """Extrai IP real do request, considerando proxies."""
    if not request:
        return ''
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _user_agent(request):
    if not request:
        return ''
    return (request.META.get('HTTP_USER_AGENT', '') or '')[:300]


# ── Login bem-sucedido ───────────────────────────────────────────────────────
@receiver(user_logged_in)
def log_login_sucesso(sender, request, user, **kwargs):
    LogSistema.objects.create(
        nivel='INFO',
        origem='auth',
        mensagem=f'Login bem-sucedido: {user.username}',
        usuario=user,
        detalhe=f'IP={_client_ip(request)}\nUA={_user_agent(request)}',
    )


# ── Logout ───────────────────────────────────────────────────────────────────
@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    if user is None:
        return
    LogSistema.objects.create(
        nivel='INFO',
        origem='auth',
        mensagem=f'Logout: {user.username}',
        usuario=user,
        detalhe=f'IP={_client_ip(request)}',
    )


# ── Login falho ──────────────────────────────────────────────────────────────
@receiver(user_login_failed)
def log_login_falho(sender, credentials, request=None, **kwargs):
    username = (credentials or {}).get('username') or (credentials or {}).get('login') or '?'
    LogSistema.objects.create(
        nivel='AVISO',
        origem='auth',
        mensagem=f'Tentativa de login falhou: {username}',
        detalhe=f'IP={_client_ip(request)}\nUA={_user_agent(request)}',
    )


# ── Novo usuário criado ──────────────────────────────────────────────────────
@receiver(post_save, sender=get_user_model())
def log_usuario_criado(sender, instance, created, **kwargs):
    if not created:
        return
    LogSistema.objects.create(
        nivel='INFO',
        origem='auth',
        mensagem=f'Novo usuário criado: {instance.username}',
        usuario=instance,
        detalhe=f'email={instance.email or "(sem email)"}\nis_staff={instance.is_staff}',
    )
    # ── Não concede trial PRO na criação — só após e-mail confirmado ──
    # Trial é aplicado no signal de email_confirmed (allauth) mais abaixo.
    # Notifica dono do projeto (Discord/Telegram)
    try:
        from .notificacao_interna import notificar
        notificar(
            titulo=f'🎉 Novo cadastro · {instance.username}',
            mensagem=f'Email: {instance.email or "(sem email)"}',
            cor=0x86f8c8,
        )
    except Exception:
        pass


# Signal de trial PRO 7d removido — app 100% gratuita.
# (Antes: conceder_trial_ao_confirmar concedia PRO temporario apos allauth
#  confirmar email. Sem uso agora que nao ha plano pago.)


# ── Notifica user quando staff responde ticket ──────────────────────────────
try:
    from .models import RespostaTicket

    @receiver(post_save, sender=RespostaTicket)
    def notificar_user_resposta_ticket(sender, instance, created, **kwargs):
        """Quando staff responde um ticket: (1) atualiza status pra 'respondido';
        (2) envia email pro user. Antes usuario descobria resposta so se acaso
        reabrir /suporte/ — jornada muda depois de aberta."""
        if not created or not instance.eh_staff:
            return

        ticket = instance.ticket

        # 1. Atualiza status do ticket
        if ticket.status != 'respondido':
            ticket.status = 'respondido'
            ticket.save(update_fields=['status', 'atualizado_em'])

        # 2. Email pro user (se tiver email + backend real)
        user = ticket.usuario
        destinatario = ticket.email_contato or user.email
        if not destinatario:
            return

        try:
            from django.conf import settings as _s
            from django.core.mail import send_mail
            _backend = getattr(_s, 'EMAIL_BACKEND', '')
            if not _backend or 'console' in _backend or 'dummy' in _backend:
                return
            site_url = getattr(_s, 'SITE_URL', 'https://santuarioedu.com.br').rstrip('/')
            nome = user.first_name or user.username or 'estudante'
            send_mail(
                subject=f'Resposta ao seu ticket #{ticket.id} — SantuarioEdu',
                message=(
                    f'Ola, {nome}!\n\n'
                    f'Voce recebeu uma resposta no ticket #{ticket.id} ({ticket.assunto}):\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
                    f'{instance.mensagem[:800]}\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'Responda ou veja o ticket completo em:\n'
                    f'{site_url}/suporte/{ticket.id}/\n\n'
                    f'-- Equipe SantuarioEdu'
                ),
                from_email=_s.DEFAULT_FROM_EMAIL,
                recipient_list=[destinatario],
                fail_silently=True,
            )
        except Exception:
            pass
except ImportError:
    pass


# ── Notifica admin quando log ERRO/CRITICO é criado ─────────────────────────
@receiver(post_save, sender=LogSistema)
def notifica_log_grave(sender, instance, created, **kwargs):
    """Dispara Discord/Telegram/Email quando aparece log ERRO ou CRITICO."""
    if not created or instance.nivel not in ('ERRO', 'CRITICO'):
        return
    try:
        from .notifications import notificar_admin
        nivel_map = {'ERRO': 'alta', 'CRITICO': 'critica'}
        who = instance.usuario.username if instance.usuario_id else 'sistema'
        meta = f'{instance.origem} · {who} · #{instance.id}'
        notificar_admin(
            nivel_map[instance.nivel],
            titulo=instance.mensagem[:120],
            corpo=(instance.detalhe or '')[:1500],
            meta=meta,
        )
    except Exception:
        pass  # nunca quebra o fluxo original por causa de notify


# ── Notifica quando novo ticket de suporte é criado ─────────────────────────
try:
    from .models import TicketSuporte

    @receiver(post_save, sender=TicketSuporte)
    def notifica_novo_ticket(sender, instance, created, **kwargs):
        if not created:
            return
        try:
            from .notifications import notificar_admin
            user = instance.usuario.username if instance.usuario_id else 'anônimo'
            cat = getattr(instance, 'get_categoria_display', lambda: instance.categoria)()
            titulo_ticket = getattr(instance, 'titulo', '') or getattr(instance, 'assunto', '')
            notificar_admin(
                'media',
                titulo=f'Novo ticket #{instance.id}: {titulo_ticket[:80]}',
                corpo=(
                    f'Categoria: {cat}\n'
                    f'Usuário: {user}\n'
                    f'Email: {instance.email_contato or "—"}\n\n'
                    f'{(getattr(instance, "descricao", "") or "")[:1000]}'
                ),
                meta=f'/admin/quiz/ticketsuporte/{instance.id}/change/',
            )
        except Exception:
            pass
except ImportError:
    pass
