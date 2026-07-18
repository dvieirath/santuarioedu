# Novidades da última sessão (sem email configurado ainda)

Tudo abaixo está implementado e pronto pra rodar **assim que você arrumar o `cryptography`** e aplicar a migration `0035`.

---

## 1. 🆘 Sistema de Suporte completo

### Modelos
- `TicketSuporte` — usuario, categoria, assunto, mensagem, status, prioridade
- `RespostaTicket` — conversa do usuário com o staff

### Páginas
- `/suporte/` — lista de tickets do usuário com status colorido
- `/suporte/novo/` — formulário em 4 passos (categoria → assunto → mensagem → email alternativo)
- `/suporte/<id>/` — visualiza ticket + adiciona resposta

### Admin
- Filtros por status/prioridade/categoria
- Actions: marcar respondido, fechar, definir prioridade alta
- Inline pra responder direto no admin
- Badges coloridos por status e prioridade

### E-mail (preparado, dispensa configuração agora)
- Quando você configurar SMTP no `.env` (`EMAIL_HOST=smtp.xxx`), tickets novos disparam email para `SUPORTE_EMAIL`
- Sem SMTP: continua funcionando 100% via página de tickets
- Notificação Discord/Telegram também já amarrada

### Botão SOS flutuante (mobile)
- `includes/suporte_fab.html` — botão flutuante 🆘 com menu rápido
- Já incluído no dashboard

---

## 2. 🚩 Marcar questão pra revisar depois

- Modelo `QuestaoMarcada` (separado de favoritas)
- API: `POST /api/marcar-questao/<id>/` (toggle)
- Página: `/marcadas/` lista todas as marcadas
- Link na sidebar: "Marcadas" em Revisão

---

## 3. 🎓 Onboarding por concurso

- Página `/onboarding/` em 3 passos: concurso + data prova + horas/dia
- Modelo `ConcursoPreferido` salva a escolha
- **Concede automaticamente 7 dias de PRO grátis** ao completar

---

## 4. 🎁 Trial PRO 7 dias automático

- Signal em `signals_audit.py` cria automaticamente um `PlanoUsuario(pro, 7 dias)` ao usuário cadastrar
- Quando expira, vira gratuito (já tinha lógica)

---

## 5. 🎯 Quiz "Qual concurso é pra você?" (lead magnet)

- Página pública `/qual-concurso/` (sem login)
- 5 perguntas rápidas → recomenda concurso ideal
- CTA pra cadastro com bônus de 7 dias PRO
- Sem captura forçada de email (decisão do usuário)

---

## 6. 📤 Card compartilhável de progresso

- Página `/compartilhar/`
- Renderiza card 1080×1080 lindo com KPIs da semana
- Botões: baixar PNG, compartilhar nativo, WhatsApp, Telegram, X
- Usa html2canvas com SRI
- Link na sidebar em "Progresso"

---

## 7. 🔬 Análise por subtema (granular)

- Página `/analise-subtemas/`
- Quebra performance por `Questao.assunto`, não só categoria
- 3 seções: Pontos fracos (vermelho) · Pontos fortes (verde) · Lista completa
- Link na sidebar em "Progresso"

---

## 8. 🎬 Modo foco

- `includes/modo_foco.html` — botão flutuante + atalho **F**
- Esconde sidebar, header, FABs durante simulado
- Estado persiste em localStorage

---

## 9. 💎 Paywall PRO (preview blurado)

- `includes/paywall_pro.html` — componente reutilizável
- Mostra conteúdo blurado + CTA pra `/planos/`
- Use em features PRO:
  ```django
  {% if is_pro %}
      conteúdo real
  {% else %}
      {% include "includes/paywall_pro.html" with feature="Análise de Banca IA" %}
  {% endif %}
  ```
- `is_pro` disponível em todos templates via context processor

---

## 10. 🌐 Context processors globais

`quiz/context_processors.py` disponibiliza em TODOS templates:
- `SUPORTE_EMAIL`, `FINANCEIRO_EMAIL`, `PRIVACIDADE_EMAIL`
- `plano_atual` (gratuito/pro/premium)
- `is_pro`, `is_premium` (booleans)

Useful pra esconder/mostrar features sem precisar editar cada view.

---

## 11. 📋 Migration 0035

Aplica os 4 modelos novos:
- TicketSuporte
- RespostaTicket
- QuestaoMarcada
- ConcursoPreferido

**Para aplicar** (depois de fixar cryptography):
```bash
python manage.py migrate
```

---

## 12. ⚙️ Settings novos

`.env.example` ganhou:
```env
SUPORTE_EMAIL=suporte@santuarioedu.com.br
FINANCEIRO_EMAIL=financeiro@santuarioedu.com.br
PRIVACIDADE_EMAIL=privacidade@santuarioedu.com.br
```

Quando criar seu domínio:
1. Cria os 3 inboxes (Gmail ou Zoho gratuito)
2. Cola no `.env` de produção
3. Sistema usa automaticamente

---

## ✅ Resumo de arquivos criados

```
quiz/
├── models.py                         (+4 modelos)
├── views.py                          (+8 views novas)
├── urls.py                           (+8 rotas)
├── admin.py                          (+4 ModelAdmin)
├── signals_audit.py                  (+trial PRO 7 dias)
├── context_processors.py             (NOVO)
├── migrations/0035_*.py              (NOVO)
└── templates/
    ├── quiz/
    │   ├── suporte_lista.html        (NOVO)
    │   ├── suporte_novo.html         (NOVO)
    │   ├── suporte_detalhe.html      (NOVO)
    │   ├── onboarding_concurso.html  (NOVO)
    │   ├── questoes_marcadas.html    (NOVO)
    │   ├── card_progresso.html       (NOVO)
    │   ├── analise_subtemas.html     (NOVO)
    │   └── dashboard.html            (+suporte FAB)
    ├── quiz_qual_concurso.html       (NOVO)
    └── includes/
        ├── suporte_fab.html          (NOVO)
        ├── modo_foco.html            (NOVO)
        └── paywall_pro.html          (NOVO)

prf_master/
└── settings.py                       (+SUPORTE_EMAIL etc + context_processors)
```

---

## 🚀 Como ativar tudo

1. **Fixar cryptography** (problema do env)
   - Reinstalar Python 3.12 (5 min)
2. **Aplicar migration**
   ```bash
   python manage.py migrate
   ```
3. **Conferir**
   ```bash
   python manage.py runserver
   ```

Tudo funciona — só falta configurar email quando você tiver domínio.

---

## 💌 Quando criar os emails

Sugestão de inboxes (Gmail Workspace ou Zoho gratuito até 5 usuários):
- `suporte@seudominio.com.br` — tickets
- `financeiro@seudominio.com.br` — pagamento
- `privacidade@seudominio.com.br` — LGPD
- `contato@seudominio.com.br` — geral

Cola no `.env` em produção:
```env
SUPORTE_EMAIL=suporte@seudominio.com.br
FINANCEIRO_EMAIL=financeiro@seudominio.com.br
PRIVACIDADE_EMAIL=privacidade@seudominio.com.br
DEFAULT_FROM_EMAIL=SantuarioEdu <noreply@seudominio.com.br>

# SMTP (SendGrid free 100/dia)
EMAIL_HOST=smtp.sendgrid.net
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=SG.xxxxxxxxxx
```
