# Notificações de admin

O sistema notifica você automaticamente quando algo importante acontece:

| Evento | Nível | Canais |
|---|---|---|
| Exception 500 não-tratada | **alta** | Discord + Telegram + Email |
| `LogSistema` nível `CRITICO` | **crítica** (`@here` no Discord) | Discord + Telegram + Email |
| `LogSistema` nível `ERRO` | **alta** | Discord + Telegram + Email |
| Novo `TicketSuporte` criado | **média** | Discord + Telegram |
| Log `INFO`/`AVISO` | (não notifica) | só grava em BD |

**Anti-spam**: notificação com mesmo título só sai 1× a cada 5 minutos.
Envio é **assíncrono** (thread separada) — nunca bloqueia o request original.

## Setup — escolha 1 ou mais canais

### Opção A — Discord (recomendado, mais rápido)

1. Abra o servidor Discord onde você quer receber alertas
2. **Configurações do canal** → **Integrações** → **Webhooks** → **Novo webhook**
3. Nomeie (ex.: "SantuarioEdu Alerts") + copie a URL
4. No `.env`:
   ```
   NOTIFY_DISCORD_WEBHOOK=https://discord.com/api/webhooks/12345.../abcdef...
   ```

### Opção B — Telegram

1. No app do Telegram, fale com [@BotFather](https://t.me/BotFather)
2. `/newbot` → escolha nome → copie o **token** (`123456:ABC-DEF...`)
3. Envie `/start` pro seu novo bot no Telegram
4. Abra `https://api.telegram.org/bot<TOKEN>/getUpdates` no navegador
5. Ache seu `chat.id` no JSON (ex.: `123456789`)
6. No `.env`:
   ```
   NOTIFY_TELEGRAM_TOKEN=123456:ABC-DEF...
   NOTIFY_TELEGRAM_CHAT_ID=123456789
   ```

### Opção C — Email (fallback)

Só recebe alertas de nível `alta` e `critica`. Requer SMTP já configurado
(ver [EMAIL_TRANSACIONAL.md](EMAIL_TRANSACIONAL.md)).

```
ADMIN_EMAIL=seu@email.pessoal.com
```

## Testar

```bash
python manage.py shell -c "
from quiz.notifications import notificar_admin
notificar_admin('media', 'Teste de notificação', 'Se você recebeu, tá funcionando!')
"
```

Você deve receber a mensagem em **até 5 segundos** nos canais configurados.

## Formato da mensagem

**Discord** (embed colorido):
```
🚨 500 em /pagamento/webhook/

Traceback (most recent call last):
  File ".../views.py", line 6789, in mp_webhook
    ...
KeyError: 'external_reference'

Footer: POST /pagamento/webhook/ · user=anônimo
```

**Telegram** (Markdown):
```
🚨 *500 em /pagamento/webhook/*

Traceback (most recent call last):
  ...
```

## Uso manual (dentro de views/tasks)

Você pode disparar notificações do seu próprio código:

```python
from quiz.notifications import notificar_admin

# Baixa relevância — sempre entra
notificar_admin('info', 'Backup diário concluído', '2.3 GB, 3.4s')

# Média — merece atenção
notificar_admin('media', 'Quota Groq em 85%',
                'Provider está próximo do limite diário')

# Alta — problema imediato
notificar_admin('alta', 'Pagamento MP falhou',
                'payment_id=abc, user=X, error=Y')

# Crítica — @here no Discord (dispara notificação urgente)
notificar_admin('critica', 'Banco de dados fora do ar',
                'psycopg.OperationalError: connection refused')
```

## Como saber que canais estão ativos

```bash
python manage.py shell -c "
from django.conf import settings
print('Discord:', 'ok' if settings.NOTIFY_DISCORD_WEBHOOK else 'não configurado')
print('Telegram:', 'ok' if settings.NOTIFY_TELEGRAM_TOKEN and settings.NOTIFY_TELEGRAM_CHAT_ID else 'não configurado')
print('Admin email:', settings.ADMIN_EMAIL or 'não configurado')
"
```
