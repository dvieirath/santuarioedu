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


# ── Trial PRO 7 dias APÓS confirmação de e-mail ──────────────────────────────
# Requer que o allauth mande e-mail de confirmação e usuário clique no link.
# Evita bots criando contas fake pra gastar sua cota de IA.
try:
    from allauth.account.signals import email_confirmed

    @receiver(email_confirmed)
    def conceder_trial_ao_confirmar(request, email_address, **kwargs):
        """Concede PRO 7d na PRIMEIRA confirmacao de email.
        NAO sobrescreve plano pago vigente (nem PRO nem Premium ativos), nem
        concede trial 2x quando user confirma email secundario do allauth."""
        from datetime import timedelta
        from django.utils import timezone as _tz
        from .models import PlanoUsuario

        user = email_address.user
        if not user:
            return

        existente = PlanoUsuario.objects.filter(usuario=user).first()

        # Guard 1: NAO sobrescreve assinatura paga vigente (PRO ou Premium).
        # Bug anterior checkava so 'premium' — user PRO 30d que confirmava
        # email secundario perdia dias que ja pagou.
        if existente and existente.plano in ('pro', 'premium') and existente.ativo:
            if not existente.expirado:
                return

        # Guard 2: NAO concede trial 2x pro mesmo user (email primario ja
        # confirmado ou trial ja usado).
        if existente and existente.plano != 'gratuito':
            # ja teve algum plano (mesmo expirado); trial ja foi usado
            return

        PlanoUsuario.objects.update_or_create(
            usuario=user,
            defaults={
                'plano': 'pro',
                'ativo': True,
                'expira_em': _tz.now() + timedelta(days=7),
            },
        )
        LogSistema.objects.create(
            nivel='INFO', origem='auth',
            mensagem=f'Trial PRO 7d concedido a {user.username} após confirmar email',
            usuario=user,
        )
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
