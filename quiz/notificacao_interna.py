"""
Notificações internas para o dono do projeto.

Quando algo importante acontece (novo usuário, nova venda, erro crítico),
envia mensagem para o Discord ou Telegram que você configurar no .env.

Setup:
  Discord:
    1. No seu servidor → Configurações do Canal → Integrações → Webhooks
    2. Criar Webhook → copiar URL
    3. .env: NOTIFY_DISCORD_WEBHOOK=https://discord.com/api/webhooks/...

  Telegram:
    1. Falar com @BotFather → /newbot → copiar token
    2. Falar com seu bot → mandar qualquer msg → pegar chat_id em
       https://api.telegram.org/bot<TOKEN>/getUpdates
    3. .env: NOTIFY_TELEGRAM_TOKEN=... e NOTIFY_TELEGRAM_CHAT_ID=...
"""
import json
import logging
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def notificar(titulo, mensagem='', cor=0x002046):
    """Envia notificação para Discord/Telegram (o que estiver configurado).
    Roda sem bloquear o fluxo principal — falha silenciosa.
    """
    _enviar_discord(titulo, mensagem, cor)
    _enviar_telegram(titulo, mensagem)


def _enviar_discord(titulo, mensagem, cor):
    url = getattr(settings, 'NOTIFY_DISCORD_WEBHOOK', '')
    if not url:
        return
    try:
        payload = {
            'embeds': [{
                'title': titulo[:256],
                'description': (mensagem or '')[:2000],
                'color': cor,
                'footer': {'text': 'SantuarioEdu'},
            }]
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logger.warning(f'Falha ao notificar Discord: {e}')


def _enviar_telegram(titulo, mensagem):
    token = getattr(settings, 'NOTIFY_TELEGRAM_TOKEN', '')
    chat = getattr(settings, 'NOTIFY_TELEGRAM_CHAT_ID', '')
    if not token or not chat:
        return
    try:
        texto = f'*{titulo}*\n\n{mensagem}' if mensagem else f'*{titulo}*'
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        payload = json.dumps({
            'chat_id': chat, 'text': texto, 'parse_mode': 'Markdown'
        }).encode('utf-8')
        req = urllib.request.Request(
            url, data=payload, headers={'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logger.warning(f'Falha ao notificar Telegram: {e}')
