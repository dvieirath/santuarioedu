# Deploy no Railway — SantuarioEdu

Passo-a-passo pra colocar no ar em ~30 min. Custo estimado: **US$5-10/mês** com
Postgres + Redis inclusos.

## 1. Preparo local (5 min)

**Gerar SECRET_KEY nova** (a atual `django-insecure-*` vai barrar boot):
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
Copie a saída — vai usar em Env Vars do Railway.

**Commit dos arquivos de deploy:**
```bash
git add railway.json Procfile .python-version prf_master/views.py
git commit -m "deploy: Railway config + health check universal"
git push
```

## 2. Criar projeto no Railway (5 min)

1. Entre em [railway.app](https://railway.app) → login com GitHub
2. **New Project** → **Deploy from GitHub repo** → escolha `projeto_prf`
3. Railway detecta Django/Python automaticamente e faz o primeiro build (vai falhar por falta de env vars — normal)

## 3. Adicionar plugins (2 min)

Dentro do projeto:
1. **+ New** → **Database** → **Add PostgreSQL** — cria com `DATABASE_URL` já injetada
2. **+ New** → **Database** → **Add Redis** — cria com `REDIS_URL` injetada

## 4. Configurar Env Vars (10 min)

Clique no service `web` → aba **Variables** → cole todas de uma vez em **Raw Editor**:

```env
SECRET_KEY=<cole a chave gerada no passo 1>
DEBUG=False
ALLOWED_HOSTS=santuarioedu.com.br,www.santuarioedu.com.br,.up.railway.app
SITE_URL=https://santuarioedu.com.br

# Cache aponta pra Redis que o Railway já provisionou
CACHE_URL=${{Redis.REDIS_URL}}

# IA
AI_PROVIDER_ORDER=groq,gemini
GROQ_API_KEY=<sua chave>
GEMINI_API_KEY=<sua chave>
AI_TIMEOUT_SECONDS=30

# Mercado Pago (ROTACIONE antes de colar — as antigas vazaram no chat)
MP_ACCESS_TOKEN=<APP_USR-novo>
MP_PUBLIC_KEY=<APP_USR-novo>
MP_WEBHOOK_SECRET=<gere no dashboard MP>

# Notificações admin
NOTIFY_DISCORD_WEBHOOK=<crie webhook novo, o antigo foi deletado>
ADMIN_EMAIL=davivieiradesouza4@gmail.com

# SMTP (ex.: Gmail com senha de app)
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=<seu@gmail.com>
EMAIL_HOST_PASSWORD=<senha-de-app-de-16-chars>
DEFAULT_FROM_EMAIL=SantuarioEdu <noreply@santuarioedu.com.br>

# Sentry (opcional mas recomendado — grátis 5k/mês)
SENTRY_DSN=
SENTRY_ENV=production
```

**Deploy dispara automaticamente** após salvar. Acompanhe em **Deployments**.

## 5. Domínio próprio (5 min)

1. No service `web` → **Settings** → **Networking** → **Custom Domain**
2. Cole `santuarioedu.com.br` e `www.santuarioedu.com.br`
3. Railway mostra o CNAME/A. Vá no painel do seu registrador de DNS e adicione:
   - `@` → A record apontando pro IP do Railway
   - `www` → CNAME apontando pro `xxx.up.railway.app`
4. SSL é automático (Let's Encrypt) — leva 1-2 min

## 6. Criar superuser (2 min)

Aba **web** → **Settings** → **Deploy** → **Run Command** (ou via CLI):
```bash
railway run python manage.py createsuperuser
```

## 7. Configurar webhook Mercado Pago (2 min)

1. [mercadopago.com.br/developers](https://www.mercadopago.com.br/developers)
2. Sua aplicação → **Webhooks** → **Configurar notificações**
3. URL: `https://santuarioedu.com.br/pagamento/webhook/`
4. Eventos: `payment`
5. Copie o **Secret** → cole em `MP_WEBHOOK_SECRET` no Railway → redeploy

## 8. Validação pós-deploy

```bash
# Health check
curl https://santuarioedu.com.br/health/
# Deve retornar: {"status":"ok","db":true,"cache":true,"version":"..."}

# SEO
curl https://santuarioedu.com.br/robots.txt
curl https://santuarioedu.com.br/sitemap.xml
```

Se algum retornar erro, veja **Logs** no Railway.

## Comandos úteis (Railway CLI)

```bash
npm i -g @railway/cli
railway login
railway link  # dentro do repo local

railway logs           # tail dos logs em tempo real
railway run <cmd>      # roda comando com envs de prod (útil pra shell)
railway variables      # lista envs
railway open           # abre dashboard
```

## Troubleshooting

- **Build falha "no module named X"** → falta no `requirements.txt`
- **"DisallowedHost"** → adicione o domínio em `ALLOWED_HOSTS`
- **500 no primeiro acesso** → checar logs; provável falta de env var
- **Estáticos 404** → confirme `whitenoise` no MIDDLEWARE (já está) + rodou `collectstatic` no build
- **Webhook MP 401** → `MP_WEBHOOK_SECRET` não bate. Copie do dashboard MP novamente.

## Custo estimado mensal

| Recurso | Uso MVP | Custo |
|---|---|---|
| Web service | ~256MB RAM, 0.2 vCPU | US$3-5 |
| PostgreSQL | 500MB | US$1-2 |
| Redis | 50MB | US$1 |
| **Total** | | **US$5-8/mês** |

Escala automática — se o app crescer, cobra proporcionalmente. Alerta de gastos
em **Project Settings → Usage Limits**.
