> Estado atual: consulte [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md) para publicação. O acesso está gratuito; referências a preços, cotas Free/PRO e comandos antigos abaixo são históricas e precisam de revisão.

# SantuarioEdu

Plataforma web brasileira de preparação para concursos públicos com foco em **aprendizado adaptativo apoiado por IA**. Cobre desde questões geradas por IA até simulados multiplayer em tempo real, revisão espaçada, gamificação e materiais de apoio contextuais.

- **Stack:** Django 6 · Python 3.14 · PostgreSQL (prod) / SQLite (dev) · Groq + Gemini · Tailwind CSS
- **Deploy:** Railway (web) · Railpack builder · Whitenoise + Gunicorn
- **Repositório:** privado — este README documenta o projeto completo para o dono

---

## Sumário

- [Visão geral](#visão-geral)
- [Diferenciais](#diferenciais)
- [Stack técnica](#stack-técnica)
- [Arquitetura](#arquitetura)
- [Features por área](#features-por-área)
- [Modelos de dados](#modelos-de-dados-principais)
- [Comandos de gerenciamento](#comandos-de-gerenciamento)
- [Setup local](#setup-local)
- [Deploy Railway](#deploy-railway)
- [Provedores de IA](#provedores-de-ia)
- [Rotas principais](#rotas-principais)
- [Roadmap / dívidas técnicas](#roadmap--dívidas-técnicas)

---

## Visão geral

SantuarioEdu é uma plataforma **agnóstica de concurso** — atualmente com foco maior em PRF (Polícia Rodoviária Federal), mas construída para servir qualquer concurso público brasileiro. O usuário cadastra um `ConcursoPreferido`, e toda a IA e recomendação se adaptam ao contexto (banca esperada, edital, tempo até a prova).

**Meta operacional:** 1.000 questões por tema, mescladas entre extração de provas oficiais e geração por IA no estilo das principais bancas (Cebraspe, CESPE, FGV, FCC, FUNCAB, FUNRIO, INEP).

## Diferenciais

Comparado a Qconcursos, TEC, Gran Cursos, Estratégia:

- **IA em todas as camadas:** geração de questões, justificativas, tutor de dúvidas, análise pós-simulado, predição de tópicos, plano de estudos dinâmico
- **Multiplayer em tempo real:** Duelo 1v1 + Simulado Coletivo (até 20 jogadores)
- **Gamificação temática:** ranks PRF (Cadete → Diretor PRF), XP, streaks, conquistas
- **SRS SM-2 integrado** a questões erradas e flashcards
- **Extração de provas antigas via visão computacional** (Gemini File API + PyMuPDF)
- **Materiais de apoio gerados por IA:** resumos, mapas mentais, timelines de leis, comparativos entre bancas, glossário
- **Custo variável baixo:** free tier Groq/Gemini + Railway barato → permite preço muito mais agressivo (~R$14,90/mês vs R$50-200/mês dos concorrentes)

## Stack técnica

| Camada | Tecnologia |
|---|---|
| Backend | Django 6.0 + Python 3.14 |
| Banco | PostgreSQL (prod, via `dj-database-url`) · SQLite (dev) |
| Frontend | Templates Django + Tailwind CDN + Material Symbols + Chart.js + Mermaid.js |
| IA | Groq (Llama 3.3 70B) principal + Gemini (2.0/3.x Flash) fallback |
| Auth | django-allauth (username + email + Google OAuth) |
| Segurança | django-csp · django-axes (brute-force) · django-ratelimit · Sentry |
| Notificações | Discord webhook · Telegram · Email SMTP · Web Push |
| Pagamento | Mercado Pago (checkout + webhook) |
| Deploy | Railway (Railpack) · Gunicorn · Whitenoise |
| Extração de PDF | pypdf (texto) · PyMuPDF (imagens + layout) · Gemini File API (visão) |

## Arquitetura

```
prf_master/                Config Django
├── settings.py            Env vars via python-decouple; CSP, Axes, allauth
├── urls.py                Roteamento raiz
├── middleware.py          Security headers + Rate limit + Notify 500
├── views.py               Health check + páginas de erro custom
└── wsgi.py                Entry point Gunicorn

quiz/                      App principal
├── models.py              ~60 models (Questao, Simulado, Duelo, XP, IA cache…)
├── views.py               ~8000 linhas (single-file; roadmap: split em módulos)
├── urls.py                ~160 rotas nomeadas
├── ai_service.py          Wrapper de alto nível (tutor, resumo, mapa mental…)
├── ai_provider.py         Camada unificada Groq → Gemini fallback
├── ai_metrics.py          Registra latência, tokens, quota por provider
├── auditoria.py           Detecção de defeitos em questões (flags graves)
├── signals_audit.py       Logs de login/logout/signup em LogSistema
├── limits.py              Cotas Free/PRO/Premium
├── notifications.py       Discord/Telegram/Email/Push helpers
├── prompts_justificativa.py  Prompt canônico da justificativa padronizada
├── management/commands/   ~20 comandos (importar PDF, gerar IA, auditar, etc)
├── migrations/            0040+ migrações
├── static/quiz/           SW.js, favicon, CSS
├── static/js/             marked.min.js, mermaid.min.js, chart.min.js (self-hosted)
└── templates/quiz/        Painel, quiz, simulado, dashboard, IA, admin-revisao...
```

**Middleware chain** (ordem, `settings.py:MIDDLEWARE`):

1. `csp.middleware.CSPMiddleware` — Content Security Policy strict
2. `SecurityHeadersMiddleware` — Permissions-Policy, COEP, COOP, CORP
3. `RatelimitMiddleware` — Converte `Ratelimited` (403) em 429 amigável
4. `NotifyExceptionMiddleware` — Notifica admin ao capturar 500 (Discord/Telegram)
5. `AllauthAccountMiddleware`
6. Middleware padrão do Django

## Features por área

### 📚 Estudar (praticar)

- **Escolher tema** — grid de categorias com progresso
- **Aleatórias** — feed misturado de todas as categorias
- **Questão do dia** — 1 questão difícil, diária, pontuação
- **Por assunto** — filtro fino dentro de uma categoria
- **Modo Desafio** — 10 questões × 30s cada, ranking

### 🔄 Revisar

- **Flashcards** — pergunta/resposta com dificuldade percebida
- **Caderno de erros** — só questões que o usuário errou
- **Revisão Espaçada (SRS SM-2)** — algoritmo de espaçamento clássico

### 🎯 Simulados

- **Prontos** — montagem por edital
- **Personalizado** — filtros (categoria, ano, banca)
- **Preditivo** — IA seleciona o que provavelmente cai
- **Cronometrado** (Prova Real) — 5h, 50 questões
- **Coletivo** — sala com até 20 jogadores, tempo real
- **Duelo 1v1** — sala privada por código

### 🤖 IA & Análises

**Assistentes IA:**
- **Coach IA conversacional** (`/coach/`) — chat 1-a-1 estilo WhatsApp com contexto do concurso
- **Coach anotações** (`/coach/anotacoes/`) — caderneta pessoal com mensagens salvas
- **Análise semanal automática** — coach envia resumo domingo (cron)
- **Meta-lembretes IA** — coach proativo se streak em risco / prova próxima / ausência
- **Resumos** — resumo Markdown por disciplina (5-8 conceitos, macetes)
- **Mapas mentais** — Mermaid `mindmap` renderizado no browser
- **Meu Edital** (`/meu-edital/`) — user cola edital, IA extrai disciplinas + gera cronograma personalizado
- **Análise IA aprofundada** (edital comentado, tendências, comparativo, estratégia) por concurso
- **Análise da banca** — insight sobre padrão da banca do concurso preferido
- **Análise dos erros** — pattern-recognition dos erros do usuário
- **Previsão de tópicos** — % de probabilidade por categoria
- **Plano de estudos IA** — cronograma sob medida

**Hub de Preparação** (`/preparacao/<slug>/`) — 8 blocos por concurso:
1. Dias pra prova + total questões + materiais
2. Análise de incidência (% por disciplina, real-time)
3. Priorização inteligente (gaps × incidência)
4. Sub-tópicos mais cobrados
5. Análise da banca (estilo, pegadinhas, tempo)
6. Cronograma personalizado (horas/dia × disciplina)
7. Materiais de estudo por disciplina
8. Análises IA aprofundadas (edital, tendências, etc)

**Intelligence adicional:**
- **Curva de Esquecimento** (`/curva-esquecimento/`) — retenção estimada por disciplina (Ebbinghaus + SM-2)
- **Progresso do Edital Vivo** (`/progresso-edital-vivo/`) — checklist automatizado dos tópicos do Meu Edital
- **Análise Detalhada Simulado** (`/simulado/<id>/analise/`) — stats por disciplina, tempo médio, comparativo
- **Simulado sob Medida IA** (`/simulado/sob-medida/`) — IA identifica gaps e monta simulado 20q personalizado

**Materiais de apoio:**
- **Timelines de leis** — evolução histórica com alterações datadas
- **Comparativo entre bancas** — como cada banca aborda cada tema
- **Glossário** — termos técnicos com definição + exemplo de uso

**Meu desempenho:**
- Estatísticas de incidência (charts) · Análise por subtema · Relatório semanal · Progresso do edital · Mapa do conhecimento · XP & nível · Você vs. plataforma

### 📅 Plano & Metas

- Plano de estudos manual + Plano dinâmico (recalcula com base em desempenho)
- Metas semanais + Metas avançadas (mensais)

### 👥 Social

- Grupos de estudo com feed de atividade (conquistas, simulados, streaks dos membros)
- Ranking global · Ranking por concurso preferido (`/ranking-concurso/<slug>/`)
- Compartilhar progresso · Share individual de conquistas (`/conquista/<codigo>/compartilhar/`)
- Perfil público (`/u/<username>/`) — página compartilhável em redes sociais
- Sistema de convite/referral com XP bônus pra convidador + convidado

### 🎨 Retention & Gamification

- **26 conquistas** desbloqueáveis (5 raridades: comum → lendária)
- **Streak** diário + streak freezes (Duolingo-style)
- **Trial badge** countdown adaptativo (verde → amber → rose urgente)
- **Onboarding checklist** primeiros 7 dias com XP progressivo
- **Confetti + micro-interações** ao subir de nível / desbloquear conquista
- **Modo intensivo** por disciplina (`/intensivo/<cat_id>/`) — sessão pomodoro-style 15-90min

### 🌐 Marketing & Aquisição

- **Landing pages SEO por concurso** (`/concurso/<slug>/`) — 7 concursos indexáveis
- **Guest Quiz Mode** (`/testar/`) — demo 3 questões sem cadastro
- **Modal upgrade contextual** quando user free bate limite
- **Página /sobre/** institucional com missão + valores + números reais
- Sitemap.xml dinâmico + Schema.org + Open Graph em todas as landings

### ⚙️ Conta

- Planos (Freemium: Gratuito, PRO, Premium)
- Pagamentos via Mercado Pago
- Notificações (in-app, push, discord)
- Suporte via tickets
- FAQ · Termos · Privacidade

### 🔧 Admin

- **Dashboard do fundador** (`/admin-status/`) — snapshot de saúde do sistema (users, questões, atividade, imports em andamento, erros)
- **Métricas de negócio** (`/admin-metricas/`) — receita, conversão, planos
- Painel de revisão de questões (`/admin-revisao/`) — fluxo humano rápido
- Django Admin completo

### 📱 Mobile & PWA

- **PWA instalável** — 1 clique no browser, sem loja de app
- **Service Worker v8** com cache dedicado de questões
- **Modo offline robusto** — até 50 páginas cacheadas pra estudar sem net
- **Push notifications** para lembretes de revisão
- **Nav mobile hamburger** responsiva

## Modelos de dados principais

| Modelo | Uso |
|---|---|
| `Categoria` | Disciplina (Português, Direito Constitucional, etc.) |
| `Questao` | Questão de prova (ME ou CE) com `banca`, `ano`, `gerada_por_ia`, `imagem` |
| `Alternativa` | Alternativas de uma questão |
| `RespostaUsuario` | Histórico de respostas por usuário |
| `Simulado` | Sessão de simulado (normal ou prova real) |
| `Duelo`, `SimuladoColetivo` | Multiplayer |
| `Flashcard`, `RevisaoEspacada` | SRS |
| `NivelUsuario` | XP + rank |
| `MetaEstudo`, `MetaAvancada`, `PlanoEstudoDinamico` | Metas |
| `ResumoIA`, `MapaMental` | Cache IA por categoria |
| `TimelineLei`, `ComparativoBanca`, `TermoGlossario` | Materiais de apoio |
| `ExplicacaoIA`, `RelatorioSimuladoIA`, `PrevisaoTopico` | Cache IA por contexto |
| `PlanoUsuario`, `CupomDesconto`, `PagamentoMP` | Monetização |
| `LogSistema` | Auditoria (login, erro, IA slow, etc) |
| `TicketSuporte`, `RespostaTicket` | Suporte |
| `Notificacao`, `PushSubscription` | Alertas |
| `ConcursoPreferido` | Contexto do usuário (concurso alvo, horas/dia) |

## Comandos de gerenciamento

Rodar com `python manage.py <nome>`:

| Comando | Função |
|---|---|
| `importar_pdf_questoes` | Extrai questões de PDFs via pypdf + IA (Groq/Gemini) |
| `reextrair_com_visao` | Reprocessa PDFs via Gemini File API para capturar texto de apoio + descrever figuras |
| `extrair_imagens_pdf` | PyMuPDF extrai imagens raster embutidas e associa a questões por fuzzy match |
| `gerar_questoes_ia` | Gera N questões inéditas de uma categoria via IA |
| `gerar_bateria_prf` | Orquestrador: gera bateria de questões nas 14 categorias PRF |
| `gerar_justificativas_ia` | Popula justificativas em massa nas questões sem elas |
| `gerar_lote_completo` | Fluxo end-to-end (gerar + revisar + justificar) |
| `auditar_questoes` | Detecta defeitos, aplica auto-fix seguros, reverte aprovações com problemas graves |
| `validar_questoes_auto` | Aprovação automática por heurística (staff-only) |
| `corrigir_rejeitadas` | Reprocessa questões rejeitadas com `motivo_rejeicao` |
| `revisar_questoes` | Interface CLI de revisão |
| `enviar_lembretes` | Push/email para usuários com streak em risco |
| `enviar_digest_semanal` | Relatório semanal por email |
| `backup_dados` | Dump JSON para backup |
| `importar_todas_pastas_pendentes` | Import batch de PDFs em `provas_pdf/materia_prima/*/` que ainda não foram para o BD |
| `importar_questoes` | Import de arquivo JSON com questões (formato interno da app) |
| `exportar_questoes_json` | Export do BD → JSON no formato aceito por `importar_questoes` |
| `reclassificar_por_tema` | Reclassifica questões com categoria=nome de prova em temas corretos (keywords + IA fallback) |
| `validar_integridade_questoes` | Detecta ME sem correta / com 2 corretas / com <2 alternativas; opção `--fix` marca revisada=False |
| `gerar_materiais_ia_concurso` | Gera resumos + mapas mentais IA por disciplina de um concurso |
| `gerar_analise_ia_concurso` | Gera 4 análises IA por concurso (edital, tendências, comparativo, estratégia) |
| `enviar_lembretes_ia_coach` | Coach envia lembretes proativos (streak/prova/ausência) via IA |
| `analise_semanal_coach` | Coach gera análise semanal automática domingos (cron) |
| `repor_streak_freezes` | Reset semanal do saldo de streak freezes (cron: `0 6 * * 1`) |

**Scripts fora do fluxo Django:**

| Localização | Função |
|---|---|
| `scripts/baixar_provas_concursos/` | Baixador de PDFs Cebraspe/FGV + importador em série via manifesto.json |
| `scripts/baixar_provas_concursos/loop_importar.py` | Wrapper que roda importar_manifesto em loop com retry pra cota IA |
| `scripts/manutencao/` | Fix/check pontuais (imagens, sidebars, questões corrompidas) |
| `scripts/dados/` | Importações manuais one-off (ENEM 1999, PF Agente 2025) |

## Setup local

```bash
# Requisitos: Python 3.14+, git
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows PowerShell

pip install -r requirements.txt

# Configura variáveis
cp .env.example .env
# Edita .env: SECRET_KEY, GROQ_API_KEY, GEMINI_API_KEY, etc.

# Banco (SQLite por default em dev)
python manage.py migrate

# Superuser
python manage.py createsuperuser

# Rodar
python manage.py runserver 8000
```

Acesse: `http://localhost:8000/`

**Endpoints úteis em dev:**
- `/admin/` — Django Admin
- `/admin-revisao/` — Painel de revisão de questões (staff)
- `/dashboard/` — Painel do usuário
- `/health/` — Health check JSON

## Deploy Railway

1. Novo projeto no Railway → **Deploy from GitHub repo**
2. **+ New → Database → PostgreSQL** (URL injetada como `${{Postgres.DATABASE_URL}}`)
3. Variáveis de ambiente essenciais (aba **Variables**):

```
SECRET_KEY=<gere com python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DEBUG=False
ALLOWED_HOSTS=web-production-XXX.up.railway.app,healthcheck.railway.app,.up.railway.app
DJANGO_ALLOWED_HOSTS=<mesmo valor de ALLOWED_HOSTS>
CSRF_TRUSTED_ORIGINS=https://web-production-XXX.up.railway.app
DATABASE_URL=${{Postgres.DATABASE_PUBLIC_URL}}
SITE_URL=https://web-production-XXX.up.railway.app

# IA
AI_PROVIDER_ORDER=groq,gemini
GROQ_API_KEY=<https://console.groq.com/keys>
GEMINI_API_KEY=<https://aistudio.google.com/app/apikey>
AI_TIMEOUT_SECONDS=30

# Superuser inicial (opcional)
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=<seu-email>
DJANGO_SUPERUSER_PASSWORD=<senha forte>

# Mercado Pago
MP_ACCESS_TOKEN=<APP_USR-...>
MP_PUBLIC_KEY=<APP_USR-...>
MP_WEBHOOK_SECRET=<gerado no dashboard MP>

# Notificações
NOTIFY_DISCORD_WEBHOOK=<url do webhook>
ADMIN_EMAIL=<seu@email>

# Email SMTP (nota fiscal, confirmação de conta)
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=<seu@gmail.com>
EMAIL_HOST_PASSWORD=<senha de app 16 chars>
DEFAULT_FROM_EMAIL=SantuarioEdu <noreply@santuarioedu.com.br>

# Sentry (recomendado)
SENTRY_DSN=
SENTRY_ENV=production
```

**Procfile** (auto-detectado pela Railway):
```
release: python manage.py migrate --noinput && python manage.py axes_reset && (python manage.py createsuperuser --noinput || true)
web: gunicorn prf_master.wsgi --bind 0.0.0.0:$PORT --workers 3 --threads 2 --timeout 60 --access-logfile - --error-logfile -
```

**Domínio:** Settings → Networking → **Generate Domain** (ou custom domain com CNAME).

**Google OAuth (opcional):**
1. Console.cloud.google.com → OAuth 2.0 Client → adicionar authorized redirect URI `https://<domínio>/accounts/google/login/callback/`
2. No BD prod: `Site.objects.filter(id=1).update(domain='<domínio>')` para o allauth montar o redirect correto

## Provedores de IA

Camada `ai_provider.py` orquestra:

**Groq (principal):** `llama-3.3-70b-versatile`, ~30 req/min, 100k tokens/dia grátis, muito rápido (~2s por chamada).

**Gemini (fallback):** `gemini-3.5-flash` ou `gemini-3.1-flash-lite`, 1500 req/dia grátis, ~10s por chamada. Também usado para **multimodal** (Gemini File API — leitura de PDF com imagens/layout).

**Comportamento:**
- Tenta Groq primeiro; se `429` (quota), marca cooldown 60s e cai pro Gemini
- Cap diário por usuário (Free: 3 chamadas IA/dia, PRO: 30, Premium: 100)
- Latência > 15s aciona alerta admin com dedup 30min
- Prompt injection blocklist (`ignore previous`, `you are now`, etc.)
- Todo prompt tem limite de 15k chars

**Registro de métricas:** `AiMetric` (ok/falha, tokens, latência, provider) — visível em `/admin-metricas/`.

## Rotas principais

Prefixadas em `quiz/urls.py`:

```
/                          Home / landing
/dashboard/                Painel do usuário
/estudar/                  Escolher categoria
/quiz/[<cat>/]             Iniciar quiz
/questao-do-dia/           Questão diária
/modo-desafio/             10q × 30s

/simulado/*                Simulados (edital, personalizado, preditivo, prova real)
/coletivo/*                Simulado multiplayer
/duelo/*                   1v1

/flashcards/               SRS
/caderno-erros/            Errores acumulados
/revisao-srs/              Revisão espaçada

# IA & Análises
/resumos/[<cat>/]          Resumos por disciplina
/mapas/[<cat>/]            Mapas mentais Mermaid
/analise-banca/            Insight IA
/plano-estudos-ia/         Plano gerado IA
/previsao-topicos/         Cache PrevisaoTopico

# Materiais de apoio (agnóstico de concurso)
/estatisticas/             Charts de incidência
/timelines/[<slug>/]       Timeline de leis
/comparativo/[<cat>/]      Comparativo por banca
/glossario/                Glossário buscável

# Social
/grupos/[<id>/]            Grupos de estudo
/ranking/                  Ranking global

# Conta
/perfil/                   Perfil + config
/planos/                   Assinatura
/pagamento/*               Checkout MP + webhook

# Admin (staff)
/admin-revisao/            Painel de revisão de questões
/admin-metricas/           Métricas plataforma
/admin/                    Django Admin

# Auth
/accounts/login/           Allauth
/accounts/signup/          Cadastro (username + email + senha)
/accounts/logout/
/accounts/google/*         OAuth (quando configurado)

# API auxiliar
/api/search/               Busca global
/api/proxima-acao/         Sugestão dinâmica
/api/notificacoes/count/   Badge notif
/api/admin/revisao/*       Endpoints do painel de revisão
```

## Segurança

- **CSP strict:** `default-src 'self'`; scripts self + tailwind CDN + jsdelivr CDN
- **HSTS 1 ano** + preload em produção
- **Cookies:** `HttpOnly`, `Secure`, `SameSite=Lax`
- **CSRF_TRUSTED_ORIGINS** obrigatório em prod (Django 4+)
- **django-axes:** 5 tentativas falhas → lockout 1h por (user, ip)
- **Rate limit** por rota em endpoints de IA (django-ratelimit)
- **Prompt injection blocklist** no `ai_provider.gerar_conteudo`
- **Cap diário de IA por usuário** (defense em profundidade)
- **NotifyExceptionMiddleware** — todo 500 vira notificação Discord/Telegram
- **Sentry** captura exceções em prod (se `SENTRY_DSN` setado)

## Roadmap / dívidas técnicas

**Curto prazo:**
- [ ] Migrar `google.generativeai` → `google.genai` (deprecation warning)
- [ ] Adicionar S3/R2/Cloudflare para imagens (media/ é ephemeral no Railway)
- [ ] Configurar dominio próprio + Google OAuth funcional
- [ ] Split `quiz/views.py` (~8k linhas) em módulos por área

**Médio prazo:**
- [ ] Áudio-resumos (TTS Gemini/Google Cloud) — estudo hands-free
- [ ] Simulados temáticos progressivos (nível 1-5 por disciplina)
- [ ] Redação/Discursiva com correção IA (se edital tiver)
- [ ] Podcast semanal automatizado (novidades legislativas)

**Longo prazo:**
- [ ] Mobile app (React Native ou Flutter) reusando API
- [ ] Análise preditiva de nota (ML sobre RespostaUsuario × banca × ano)
- [ ] Videoaulas curadas com anotações por tempo
- [ ] Sistema de afiliados / cupons de indicação

**Bugs conhecidos:**
- Service Worker antigo pode servir cache stale em prod — bump `CACHE_VERSION` invalida (feito na v5)
- Extração de imagens de PDFs de bancas com layout vetorial retorna baixa taxa (~15%); melhor via Gemini Vision render+crop no futuro

## Estrutura de commits

O projeto usa mensagens em português curtas seguindo prefixos:

- `feat:` nova feature
- `fix:` correção de bug
- `chore:` manutenção (dependências, deploy, sw)
- `refactor:` mudança sem alterar comportamento
- `perf:` melhoria de performance
- `docs:` documentação

## Contato

**Autor:** Davi Vieira de Souza — davivieiradesouza4@gmail.com  
**Repositório:** privado, uso pessoal
