# Novidades desta sessão (sem custo)

Tudo abaixo foi adicionado **sem nenhuma cobrança** — funciona localmente e no deploy.

## 1. Sistema de cupons de desconto

**Modelos novos:** `CupomDesconto`, `UsoCupom`
**Admin:** `/admin/quiz/cupomdesconto/` — criar, ativar/desativar
**Endpoint público:** `POST /cupom/aplicar/`
**Já incluído** na página `/planos/`

**Como usar quando lançar:**
1. Cria cupom no admin (ex: `WELCOME50`, plano `pro`, 30 dias, max 100 usos)
2. Usuário vai em `/planos/`, digita o código, ganha o plano

## 2. Programa de indicação

**Modelos:** `CodigoIndicacao`, `Indicacao`
**Página:** `/indique/` (link na sidebar em "Conta → Indique e Ganhe")
**URL com tracking:** `?ref=ABC123` — middleware captura em qualquer página
**Bônus:** 30 dias de PRO grátis quando o indicado vira pagante

**Como funciona:**
- Cada usuário tem um código único (gerado automaticamente)
- Compartilha link → middleware grava na sessão
- Quando indicado faz login pela 1ª vez, cria `Indicacao(status=pendente)`
- Admin pode marcar como `convertida` quando confirmar pagamento
- Action no admin aplica bônus automaticamente

## 3. Schema.org markup (SEO)

Adicionado em `landing.html` + `faq.html`:
- `EducationalOrganization`
- `WebSite` com SearchAction
- `Product` com Offers (Free/PRO/Premium)
- `FAQPage` com Q&A

Resultado: Google passa a mostrar rich snippets (preço, faixa estrelas, FAQ accordion).

## 4. Onboarding tour (5 telas)

`includes/onboarding_tour.html` — incluído no dashboard.

- Aparece automaticamente no primeiro acesso
- 5 telas guiando o usuário (Praticar / Simulados / IA / Hábito)
- Skippable
- Estado salvo em `localStorage`

## 5. Pomodoro flutuante

`includes/pomodoro_widget.html` — botão no canto inferior direito.

- 25min foco / 5min pausa / 15min pausa longa (a cada 4 sessões)
- Estado persiste em localStorage (sobrevive a recarga)
- Notificação do navegador ao terminar sessão
- Atalho: tecla **`P`**

## 6. Atalhos de teclado globais

`includes/atalhos_teclado.html` — modal com **`?`**

- `?` — abre o menu de atalhos
- `P` — toggle Pomodoro
- `G D` — Dashboard
- `G P` — Praticar
- `G R` — Revisão SRS
- `G Q` — Questão do dia
- `G U` — Perfil
- `1-5` — marcar alternativa A/B/C/D/E (em tela de questão)
- `→ / J` — próxima questão
- `← / K` — anterior

## 7. Dashboard de métricas pro admin

`/admin-metricas/` — restrito a superuser

KPIs em tempo real:
- **Usuários:** total, novos 7d/30d, ativos 7d
- **Receita:** pagantes, taxa de conversão (meta 3-5%), distribuição por plano
- **Engajamento:** respostas totais e 7d, simulados totais e 7d
- **Conteúdo:** total/aprovadas/pendentes
- **Indicações:** cliques, cadastros, convertidos
- **Top categorias** dos últimos 30 dias
- **Últimos eventos** do `LogSistema`

## 8. Webhook interno (Discord/Telegram)

`quiz/notificacao_interna.py` + integrado em `signals_audit.py`

Quando algo importante acontece, manda notificação pra você:
- Novo cadastro → Discord/Telegram
- (Quando integrar pagamento) → Nova venda
- (Errors do Sentry) → Pode plugar webhook lá também

**Setup:** edite `.env`:
```
NOTIFY_DISCORD_WEBHOOK=https://discord.com/api/webhooks/...
# ou
NOTIFY_TELEGRAM_TOKEN=...
NOTIFY_TELEGRAM_CHAT_ID=...
```

## 9. Suite de testes automatizada

**22 testes passando** em `quiz/tests/`:

- `test_paginas_publicas.py` — landing, FAQ, legal, health, robots, sitemap, 404, headers de segurança
- `test_auth_e_acesso.py` — exigência de login + **IDOR** (Bob não acessa dados da Alice) + cupons
- `test_indicacao.py` — código único, contagem de cliques, página

Rodar: `python manage.py test quiz.tests`

## 10. GitHub Actions CI

`.github/workflows/ci.yml` — roda em cada push:

- **Job test:** `python manage.py check` + `migrate` + `test`
- **Job security:** Bandit + pip-audit (não bloqueia o build, só relata)

Resultado: cada commit é validado automaticamente quando você subir pro GitHub.

## 11. Email digest semanal

Comando: `python manage.py enviar_digest_semanal`

- HTML bonito com KPIs do usuário (questões/acerto/simulados/streak)
- Assunto adaptativo ("🔥 Você arrebentou" vs "😴 Que tal voltar?")
- Filtro: só envia para quem teve atividade nos últimos 14 dias
- Opção `--dry_run` pra testar
- Opção `--user joao` pra mandar só pra um

**Quando deployar:** agendar cron no Render/Railway pra rodar toda segunda às 9h.

---

## Resumo dos arquivos criados/modificados

```
quiz/
├── models.py                          (+CupomDesconto, UsoCupom, CodigoIndicacao, Indicacao)
├── views.py                           (+aplicar_cupom, indique_amigos, metricas_negocio)
├── urls.py                            (+3 rotas)
├── admin.py                           (+5 ModelAdmin novos)
├── signals_audit.py                   (+indicação no login + Discord/Telegram)
├── notificacao_interna.py             (NEW)
├── migrations/0033_*.py               (NEW)
├── tests/                             (NEW — 22 testes)
│   ├── test_paginas_publicas.py
│   ├── test_auth_e_acesso.py
│   └── test_indicacao.py
├── management/commands/
│   └── enviar_digest_semanal.py       (NEW)
└── templates/
    ├── landing.html                   (+Schema.org JSON-LD)
    ├── faq.html                       (+Schema.org FAQPage)
    ├── quiz/
    │   ├── dashboard.html             (+inclui onboarding+pomodoro+atalhos)
    │   ├── indique_amigos.html        (NEW)
    │   └── admin_metricas.html        (NEW)
    └── includes/
        ├── onboarding_tour.html       (NEW)
        ├── pomodoro_widget.html       (NEW)
        └── atalhos_teclado.html       (NEW)

prf_master/
├── middleware.py                      (+CapturaIndicacaoMiddleware)
└── settings.py                        (+NOTIFY_*, middleware)

.github/workflows/
└── ci.yml                             (NEW)

.env / .env.example                    (+vars NOTIFY_* e LIMIT_*)
```

---

## Próximas ações sugeridas

Quando voltar de revisar as questões:

1. **Testar o tour** — acesse o dashboard pela 1ª vez (limpa o localStorage)
2. **Testar Pomodoro** — clica no botão flutuante
3. **Testar atalhos** — aperta `?`
4. **Acessar `/admin-metricas/`** — vê os KPIs do negócio
5. **Acessar `/indique/`** — copia teu link de indicação

**Pra subir tudo pro GitHub:** já tem `Procfile`, `runtime.txt`, `build.sh`, `requirements.txt`, `.gitignore`, `.env.example`, `DEPLOY_CHECKLIST.md` prontos.
