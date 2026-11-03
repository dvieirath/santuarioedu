> Documento histórico. Para o estado atual e comandos revisados, consulte [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md). Preços, planos, backups e instruções abaixo não foram revalidados e não devem ser usados como roteiro atual.

# Checklist de Deploy — SantuarioEdu

## 1. Antes de fazer o push

- [ ] Confirmar que `.env` está no `.gitignore`
- [ ] Verificar que `.env.example` está atualizado e commitado
- [ ] Rodar `python manage.py check --deploy` e revisar warnings
- [ ] Garantir que `requirements.txt` está atualizado: `pip freeze > requirements.txt`
- [ ] Definir `DEBUG=False` em produção (no `.env` do servidor)
- [ ] Configurar `ALLOWED_HOSTS` com o domínio real

---

## 2. Variáveis de ambiente em produção

Copie todas estas variáveis para o painel de Environment Variables da sua plataforma de deploy:

### Obrigatórias
```
SECRET_KEY=                    # Use python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
DEBUG=False
ALLOWED_HOSTS=seudominio.com.br,www.seudominio.com.br
GEMINI_API_KEY=                # API key do Gemini (com IP do servidor restringido)
DATABASE_URL=                  # PostgreSQL — fornecido pela plataforma
```

### E-mail (recomendado SendGrid)
```
EMAIL_HOST=smtp.sendgrid.net
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=SG.xxxxxxxxxx     # Sua API key SendGrid
EMAIL_PORT=587
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=SantuarioEdu <noreply@seudominio.com.br>
```

### Sentry (monitoramento de erros)
```
SENTRY_DSN=https://xxxxxxx@oXXXX.ingest.sentry.io/YYYY
SENTRY_ENV=production
SENTRY_TRACES_RATE=0.1
```

### PWA / Push (mantém os que já estão)
```
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUB=mailto:contato@seudominio.com.br
```

---

## 3. Google OAuth — Configuração para produção

Hoje o OAuth aponta para `localhost`. Quando subir, ajustar em
https://console.cloud.google.com/apis/credentials

1. Clique no **OAuth 2.0 Client ID** existente
2. Em **Authorized redirect URIs**, adicione:
   - `https://seudominio.com.br/accounts/google/login/callback/`
   - `https://www.seudominio.com.br/accounts/google/login/callback/`
3. Em **Authorized JavaScript origins**, adicione:
   - `https://seudominio.com.br`
   - `https://www.seudominio.com.br`
4. **Save**

Mantenha o `http://localhost:8000/accounts/google/login/callback/` para continuar testando localmente.

---

## 4. Configurar a aplicação social no Django Admin

Após o primeiro deploy:
1. Acesse `/admin/`
2. Vá em **Sites** → edite o `example.com` → mude para `seudominio.com.br`
3. Vá em **Social applications** → adicione:
   - Provider: **Google**
   - Name: `Google SantuarioEdu`
   - Client ID: (do Google Cloud)
   - Secret key: (do Google Cloud)
   - Sites: adicione o seu site

---

## 5. E-mail transacional

Recomendação: **SendGrid** (free 100 emails/dia)

1. Cadastre-se em https://sendgrid.com
2. Vá em **Settings → Sender Authentication** → autentique seu domínio
3. Settings → API Keys → Create API Key (com permissão "Mail Send")
4. Copie a key para `EMAIL_HOST_PASSWORD` no `.env` de produção

Alternativas:
- **Mailgun:** free 100 emails/dia, requer cartão
- **AWS SES:** $0.10 por 1000 emails, melhor escala
- **Gmail:** free mas só 500/dia e cai em spam

---

## 6. Sentry — Monitoramento de erros

1. Crie conta grátis em https://sentry.io (5k erros/mês free)
2. Crie um projeto **Django**
3. Copie o **DSN** (formato: `https://xxx@oXXX.ingest.sentry.io/YYY`)
4. Cole em `SENTRY_DSN` no `.env` de produção
5. Faça o primeiro deploy e teste forçando um erro

---

## 7. Banco de dados PostgreSQL

Para Railway/Render: clique em "Add PostgreSQL" no painel, eles geram a `DATABASE_URL` automaticamente.

Para usar a URL no Django, adicione ao `requirements.txt`:
```
psycopg[binary]==3.2.3
dj-database-url==2.2.0
```

E em `settings.py`:
```python
import dj_database_url
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default=f'sqlite:///{BASE_DIR}/db.sqlite3'),
        conn_max_age=600,
        ssl_require=not DEBUG,
    )
}
```

---

## 8. Servir arquivos estáticos

Adicionar `whitenoise` ao `requirements.txt`:
```
whitenoise==6.8.2
gunicorn==23.0.0
```

E em `settings.py`:
```python
# Adicionar logo após o SecurityMiddleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    # ... resto
]

STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```

Antes do deploy, rodar:
```bash
python manage.py collectstatic --noinput
```

---

## 9. Procfile (Railway/Render/Heroku)

Criar arquivo `Procfile` na raiz:
```
release: python manage.py migrate
web: gunicorn prf_master.wsgi --workers 3 --timeout 60
```

---

## 10. Domínio

1. Comprar domínio (registro.br, ~R$ 40/ano para .com.br)
2. Apontar DNS para a plataforma:
   - Railway/Render: copiar o CNAME do painel
   - DigitalOcean: criar registro A para o IP do droplet
3. Configurar HTTPS:
   - Railway/Render: automático (Let's Encrypt)
   - VPS: usar Caddy ou certbot

---

## 11. Teste final em produção

- [ ] Acessar `https://seudominio.com.br/` → ver landing
- [ ] Criar conta nova → confirmar e-mail real chegando
- [ ] Login com Google funcionando
- [ ] `/health/` retornando 200
- [ ] Rodar um simulado → ver resultado
- [ ] Usar IA (Tutor/Resumo) → ver resposta
- [ ] Forçar erro 500 → ver no Sentry
- [ ] Política de privacidade + Termos acessíveis
- [ ] Banner de cookies aparece

---

## 12. Pós-deploy

- [ ] Configurar Google Search Console
- [ ] Submeter sitemap.xml (se gerar)
- [ ] Google Analytics (opcional)
- [ ] Backups automáticos do banco (Railway/Render = automático)
