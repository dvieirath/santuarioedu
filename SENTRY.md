# Sentry — Guia rápido

Sentry captura erros e crashes em produção. Sem ele, quando algo quebra
você só descobre pelos usuários reclamando. Free tier: 5k eventos/mês.

## Setup (5 minutos)

1. Crie conta grátis em <https://sentry.io/signup/>
2. Novo projeto → escolha **Django** → nome livre (ex.: `santuarioedu`)
3. Copie o **DSN** que aparece na tela (formato:
   `https://xxxxxxxx@oXXXX.ingest.sentry.io/YYYYYY`)
4. Cole no `.env`:
   ```
   SENTRY_DSN=https://xxxxxxxx@oXXXX.ingest.sentry.io/YYYYYY
   SENTRY_ENV=development     # ou "production" quando fizer deploy
   SENTRY_TRACES_RATE=0.1     # 10% das requisições (performance monitoring)
   ```
5. Reinicie o servidor. Sentry ativa automaticamente (o código já existe em
   [prf_master/settings.py:20-36](prf_master/settings.py#L20)).

## Como testar se está funcionando

Trigger um erro proposital:

```python
python manage.py shell -c "raise ValueError('sentry test')"
```

Em ~30s o erro aparece no dashboard do Sentry. Delete depois.

## LGPD

O código já configura `send_default_pii=False` — Sentry não envia
email/username/IP dos usuários para o servidor Sentry, respeitando LGPD.
Você recebe stack traces + variáveis locais, mas dados pessoais são
mascarados.

## Recomendação para produção

- `SENTRY_ENV=production`
- `SENTRY_TRACES_RATE=0.05` (5% em vez de 10% — economiza cota)
- Configure alertas no dashboard Sentry para receber email quando algum
  erro novo aparecer (Alerts → New Alert Rule)
