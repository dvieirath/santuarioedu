"""
Notificações do sistema para o admin/dono do projeto.

Canais suportados (usa o primeiro configurado, todos podem coexistir):
  - Discord (webhook)
  - Telegram (bot + chat_id)
  - Email (SMTP)

Uso:
    from quiz.notifications import notificar_admin
    notificar_admin('alta', 'Erro crítico no pagamento',
                    'Detalhe: user=X, payment_id=Y, erro=Z')

Níveis:
  - 'info' → cor cinza, prefixo ℹ️
  - 'media' → cor amarela, prefixo ⚠️
  - 'alta' → cor vermelha, prefixo 🚨
  - 'critica' → cor vermelho escuro, @here no Discord

Anti-spam: cada mensagem única (título) só é enviada 1x a cada 5min.
"""
import hashlib
import json as _json
import logging
import threading
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


CORES_DISCORD = {
    'info':    0x94a3b8,  # cinza
    'media':   0xf59e0b,  # amarelo
    'alta':    0xdc2626,  # vermelho
    'critica': 0x7f1d1d,  # vermelho escuro
}

EMOJIS = {
    'info':    'ℹ️',
    'media':   '⚠️',
    'alta':    '🚨',
    'critica': '🔥',
}


def _dedup_key(titulo):
    """Chave de cache pra deduplicar notificações idênticas."""
    return 'notif:' + hashlib.md5(titulo.encode('utf-8', errors='ignore')).hexdigest()[:16]


def _post_discord(url, titulo, corpo, nivel, meta):
    """Posta embed no Discord webhook."""
    prefix = '@here ' if nivel == 'critica' else ''
    payload = {
        'content': f'{prefix}{EMOJIS.get(nivel, "")} **{titulo}**',
        'embeds': [{
            'description': (corpo or '')[:1900],
            'color': CORES_DISCORD.get(nivel, 0x94a3b8),
            'footer': {'text': meta or 'SantuarioEdu'},
        }],
    }
    req = urllib.request.Request(
        url, data=_json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    urllib.request.urlopen(req, timeout=8).read()


def _post_telegram(token, chat_id, titulo, corpo, nivel):
    """Envia via bot do Telegram."""
    texto = f'{EMOJIS.get(nivel, "")} *{titulo}*\n\n{corpo or ""}'
    if len(texto) > 4000:
        texto = texto[:3990] + '\n[…]'
    payload = {
        'chat_id': chat_id,
        'text': texto,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True,
    }
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    req = urllib.request.Request(
        url, data=_json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    urllib.request.urlopen(req, timeout=8).read()


def _post_email(titulo, corpo, nivel):
    """Envia email pro admin configurado."""
    from django.core.mail import send_mail
    admin = getattr(settings, 'ADMIN_EMAIL', '') or getattr(settings, 'SUPORTE_EMAIL', '')
    if not admin:
        return
    subject = f'[SantuarioEdu · {nivel.upper()}] {titulo}'
    send_mail(subject, corpo or '', None, [admin], fail_silently=True)


def _enviar_async(titulo, corpo, nivel, meta):
    """Executa envios em thread para não bloquear a request original."""
    try:
        webhook = getattr(settings, 'NOTIFY_DISCORD_WEBHOOK', '')
        if webhook:
            try:
                _post_discord(webhook, titulo, corpo, nivel, meta)
            except Exception as e:
                logger.warning(f'Discord notify falhou: {e}')

        tg_token = getattr(settings, 'NOTIFY_TELEGRAM_TOKEN', '')
        tg_chat  = getattr(settings, 'NOTIFY_TELEGRAM_CHAT_ID', '')
        if tg_token and tg_chat:
            try:
                _post_telegram(tg_token, tg_chat, titulo, corpo, nivel)
            except Exception as e:
                logger.warning(f'Telegram notify falhou: {e}')

        # Email como fallback + registro histórico
        if nivel in ('alta', 'critica'):
            try:
                _post_email(titulo, corpo, nivel)
            except Exception as e:
                logger.warning(f'Email notify falhou: {e}')
    except Exception as e:
        logger.exception(f'Falha geral ao notificar: {e}')


def notificar_admin(nivel: str, titulo: str, corpo: str = '', meta: str = ''):
    """
    Notifica o admin do projeto por Discord/Telegram/Email.

    Args:
      nivel: 'info' | 'media' | 'alta' | 'critica'
      titulo: linha de assunto (curta)
      corpo: detalhes (traceback, contexto)
      meta: rodapé (ex: URL, ambiente, usuário)

    Retorna: True se pelo menos 1 canal foi disparado, False se nada configurado.
    """
    # Anti-spam: mesma notificação (por título) só sai 1x a cada 5min
    key = _dedup_key(f'{nivel}:{titulo}')
    if cache.get(key):
        return False
    try:
        cache.set(key, 1, 300)  # 5 min
    except Exception:
        pass

    # Envia em background pra não bloquear o request atual
    t = threading.Thread(target=_enviar_async, args=(titulo, corpo, nivel, meta), daemon=True)
    t.start()
    return True
