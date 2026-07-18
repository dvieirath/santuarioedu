"""
Camada de integração com Mercado Pago (Checkout Pro).

Fluxo:
    1. Usuário clica "Assinar PRO" → view chama criar_preference(user, 'pro')
    2. Redirecionamos o navegador pra preference.init_point (checkout hospedado)
    3. Usuário paga (PIX / cartão / boleto)
    4. MP redireciona de volta pra back_url e envia webhook pra notification_url
    5. Webhook confirma o payment e ativa o PlanoUsuario

Configuração:
    settings.MP_ACCESS_TOKEN — TEST-xxx em dev, APP_USR-xxx em prod
    settings.SITE_URL         — URL pública (ngrok em dev, dominio real em prod)

Docs: https://www.mercadopago.com.br/developers/pt/docs/checkout-pro
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import PagamentoMP, PlanoUsuario

logger = logging.getLogger(__name__)

# Metadados de cada plano vendido — usado no título do checkout
PLANO_DISPLAY = {
    'pro':     {'nome': 'PRO',     'valor_centavos': 1490},
    'premium': {'nome': 'Premium', 'valor_centavos': 2990},
}


class CheckoutError(Exception):
    """Erro genérico ao criar preference / consultar payment."""


def _client():
    """Instancia o SDK. Levanta CheckoutError se credenciais não configuradas."""
    token = getattr(settings, 'MP_ACCESS_TOKEN', '') or ''
    if not token:
        raise CheckoutError('MP_ACCESS_TOKEN não configurado no settings')
    import mercadopago as _mp
    return _mp.SDK(token)


def criar_preference(user, plano_alvo: str) -> dict:
    """
    Cria uma preference no MP e persiste o PagamentoMP em status='pending'.
    Retorna {'preference_id', 'init_point', 'pagamento_id'}.
    """
    if plano_alvo not in PLANO_DISPLAY:
        raise CheckoutError(f'Plano inválido: {plano_alvo}')

    meta = PLANO_DISPLAY[plano_alvo]
    valor_reais = meta['valor_centavos'] / 100

    site = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
    back_urls = {
        'success': f'{site}/pagamento/sucesso/',
        'failure': f'{site}/pagamento/falha/',
        'pending': f'{site}/pagamento/pendente/',
    }

    # Persiste o registro em pending ANTES de chamar o MP.
    # Se o MP falhar, temos o audit trail e não perdemos requisição do usuário.
    pagamento = PagamentoMP.objects.create(
        usuario=user,
        plano_alvo=plano_alvo,
        valor_centavos=meta['valor_centavos'],
        status='pending',
    )

    # auto_return exige back_urls públicos HTTPS. Se estamos em dev com localhost,
    # o MP rejeita com erro 400 invalid_auto_return.
    site_publico = site.startswith('https://') and not any(
        h in site for h in ('localhost', '127.0.0.1')
    )

    payload = {
        'items': [{
            'title':       f'SantuarioEdu — Plano {meta["nome"]} (30 dias)',
            'description': f'Assinatura mensal do plano {meta["nome"]}',
            'quantity':    1,
            'currency_id': 'BRL',
            'unit_price':  valor_reais,
        }],
        'payer': {
            'email': user.email or '',
            'name':  (user.first_name or user.username)[:50],
        },
        'back_urls':     back_urls,
        # external_reference amarra o payment ao nosso PagamentoMP.id
        'external_reference': str(pagamento.id),
        'statement_descriptor': 'SANTUARIOEDU',
        'metadata': {
            'user_id':    user.id,
            'plano':      plano_alvo,
            'pagamento_id': pagamento.id,
        },
    }

    # notification_url e auto_return exigem URL pública HTTPS.
    # Em dev com localhost/127.0.0.1 o MP rejeita — deixamos vazio nesses casos
    # (ativação de plano feita manualmente ou via ngrok).
    if site_publico:
        payload['auto_return']      = 'approved'
        payload['notification_url'] = f'{site}/pagamento/webhook/'

    try:
        sdk = _client()
        resp = sdk.preference().create(payload)
    except Exception as e:
        logger.exception('MP: erro criando preference')
        pagamento.status = 'rejected'
        pagamento.payload_raw = {'erro': str(e)[:500]}
        pagamento.save(update_fields=['status', 'payload_raw'])
        raise CheckoutError(f'Falha ao criar checkout: {e}')

    if resp.get('status') not in (200, 201):
        logger.error('MP: preference response %s / %s', resp.get('status'), resp.get('response'))
        pagamento.status = 'rejected'
        pagamento.payload_raw = resp.get('response')
        pagamento.save(update_fields=['status', 'payload_raw'])
        raise CheckoutError(f'MP retornou {resp.get("status")}')

    data = resp['response']
    pagamento.preference_id = data.get('id', '')
    pagamento.save(update_fields=['preference_id'])

    return {
        'preference_id': data.get('id'),
        'init_point':    data.get('init_point'),  # URL para redirect (produção)
        'sandbox_init':  data.get('sandbox_init_point'),  # sandbox
        'pagamento_id':  pagamento.id,
    }


def consultar_payment(payment_id: str) -> dict:
    """Consulta status de um pagamento no MP. Retorna dict do payment ou None."""
    try:
        sdk = _client()
        resp = sdk.payment().get(payment_id)
    except Exception as e:
        logger.exception('MP: erro consultando payment %s', payment_id)
        raise CheckoutError(str(e))

    if resp.get('status') not in (200, 201):
        return None
    return resp['response']


def processar_pagamento_aprovado(pagamento: PagamentoMP) -> None:
    """
    Atualiza o PlanoUsuario para refletir o pagamento aprovado.
    Idempotente — chamar múltiplas vezes não vai duplicar acesso.
    """
    from django.contrib.auth import get_user_model
    user = pagamento.usuario

    plano_obj, _ = PlanoUsuario.objects.get_or_create(
        usuario=user, defaults={'plano': 'gratuito'}
    )

    # 30 dias de acesso a partir de agora.
    # Se o usuário renovar antes do vencimento, adiciona ao invés de resetar.
    agora = timezone.now()
    if plano_obj.expira_em and plano_obj.expira_em > agora and plano_obj.plano == pagamento.plano_alvo:
        nova_expira = plano_obj.expira_em + timedelta(days=30)
    else:
        nova_expira = agora + timedelta(days=30)

    plano_obj.plano     = pagamento.plano_alvo
    plano_obj.ativo     = True
    plano_obj.expira_em = nova_expira
    plano_obj.save(update_fields=['plano', 'ativo', 'expira_em'])

    logger.info('Plano %s ativado para %s até %s (pagamento %s)',
                pagamento.plano_alvo, user.username, nova_expira.isoformat(), pagamento.id)
