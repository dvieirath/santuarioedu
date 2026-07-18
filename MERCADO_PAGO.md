# Mercado Pago — Guia de configuração

Este guia cobre o setup mínimo para aceitar pagamentos via **Checkout Pro** do
Mercado Pago (PIX, cartão de crédito, boleto). O código já está integrado.
Você só precisa configurar credenciais e webhook.

## 1. Credenciais

1. Cadastre-se em <https://www.mercadopago.com.br/developers>.
2. Menu "Suas integrações" → **Criar aplicação** (nome livre, ex.: "SantuarioEdu").
3. Em "Credenciais de teste":
   - Copie o **Access Token de TESTE** (`TEST-xxxxxxxx-...`)
   - (Opcional) Copie a **Public Key de TESTE** (`TEST-xxxxxxxx-...`)
4. Cole no `.env` da aplicação:
   ```
   MP_ACCESS_TOKEN=TEST-xxxxxxxxxxxxxxxx-...
   MP_PUBLIC_KEY=TEST-xxxxxxxxxxxxxxxx-...
   SITE_URL=http://127.0.0.1:8000
   ```

## 2. Webhook (dev via ngrok)

O Mercado Pago **precisa** de uma URL pública HTTPS para enviar notificações
de pagamento aprovado. Em dev, use **ngrok** (grátis):

```bash
# 1. Baixe em https://ngrok.com/download e cadastre-se
ngrok http 8000

# 2. Copie a URL https gerada (ex.: https://abc123.ngrok-free.app)
#    e cole no .env:
SITE_URL=https://abc123.ngrok-free.app
```

Depois, no painel do MP → **Sua aplicação → Webhooks** → adicione:
- URL: `https://abc123.ngrok-free.app/pagamento/webhook/`
- Eventos: `Pagamento`

## 3. Testar o fluxo

1. Reinicie o servidor: `python manage.py runserver`
2. Acesse `/planos/` autenticado e clique em "Assinar PRO"
3. O MP abre o checkout. Use um **cartão de teste**:

   | Cartão      | Número              | CVV | Validade | Status         |
   |-------------|---------------------|-----|----------|----------------|
   | Aprovado    | 5031 4332 1540 6351 | 123 | 11/30    | approved       |
   | Pendente    | 5031 4332 1540 6351 | 123 | 11/30    | in_process (*) |
   | Rejeitado   | 4235 6477 2802 5682 | 123 | 11/30    | rejected       |

   (*) Para forçar `in_process`: use o titular **APRO** para aprovado, **OTHE**
   para pendente, **CONT** para em análise. Lista completa em:
   <https://www.mercadopago.com.br/developers/pt/docs/checkout-pro/additional-content/your-integrations/test/cards>

4. Após aprovar, você é redirecionado para `/pagamento/sucesso/` e o webhook
   ativa seu plano automaticamente. Verifique em `/minha-assinatura/`.

## 4. Produção

Quando o app estiver no ar:

1. No painel MP → "Credenciais de produção" → copie **Access Token** (`APP_USR-*`).
2. No `.env` de produção:
   ```
   MP_ACCESS_TOKEN=APP_USR-xxxxxxxxxxxx-...
   SITE_URL=https://santuarioedu.com.br
   ```
3. Registre o webhook de produção no MP:
   `https://santuarioedu.com.br/pagamento/webhook/`
4. Se estiver usando Render/Railway, o SSL é automático.

## 5. Referências

- Checkout Pro: <https://www.mercadopago.com.br/developers/pt/docs/checkout-pro>
- Webhooks: <https://www.mercadopago.com.br/developers/pt/docs/your-integrations/notifications/webhooks>
- Cartões de teste: <https://www.mercadopago.com.br/developers/pt/docs/checkout-pro/additional-content/your-integrations/test/cards>

## Arquitetura interna

```
Usuário clica "Assinar PRO" em /planos/
    │
    ▼
POST /api/checkout/mp/  { plano: 'pro' }        (views.iniciar_checkout_mp)
    │
    ▼
mercadopago_service.criar_preference()
    - Cria PagamentoMP(status='pending', preference_id=…)
    - Retorna init_point (URL do checkout hospedado do MP)
    │
    ▼
Frontend redireciona para init_point
    │
    ▼
Usuário paga no ambiente MP (PIX / cartão / boleto)
    │
    ├──> MP redireciona para back_url:
    │     /pagamento/sucesso|falha|pendente/  (views.pagamento_*)
    │
    └──> MP envia POST para notification_url:
          /pagamento/webhook/  (views.mp_webhook)
          - Consulta o payment atual no MP
          - Atualiza PagamentoMP.status
          - Se 'approved': mercadopago_service.processar_pagamento_aprovado()
            → PlanoUsuario ativado por 30 dias (idempotente)
```

Ambos back_url e webhook são idempotentes. Se o webhook não chegar (raro), o
usuário vê a página de sucesso e no próximo login/refresh o admin pode
reprocessar consultando `PagamentoMP` no `/admin/`.
