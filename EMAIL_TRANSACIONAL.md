# Email transacional (Resend)

Sem email o app não consegue:
- Confirmar cadastro (allauth espera confirmação por link)
- Resetar senha ("esqueci minha senha")
- Enviar relatórios semanais que o usuário pediu
- Notificar sobre pagamento aprovado

## Recomendação: Resend

Por quê Resend em vez de SendGrid/AWS SES/Postmark:
- **Grátis 100 emails/dia** (SendGrid dá 100/dia mas exige cartão pra ativar)
- **Setup em 5 minutos** vs. AWS SES que exige sair de sandbox
- **DX moderna**: dashboard limpo, logs claros, templates
- **DKIM/SPF automático** com um único DNS record

## Setup (5 minutos)

1. Cadastre-se em <https://resend.com/signup>
2. **Adicione seu domínio** em Domains → Add Domain → `santuarioedu.com.br`.
   Só possível **quando você tiver o domínio real**. Enquanto isso, use o
   domínio de teste `onboarding@resend.dev` (só recebe teu próprio email).
3. Cole os 3 records DNS que o Resend fornece (MX, TXT/SPF, TXT/DKIM) no
   painel do registrador do seu domínio. Aguarde propagação (~10min).
4. Vá em **API Keys** → Create → copie a chave (`re_XXXX...`).
5. Adicione no `.env`:
   ```
   EMAIL_HOST=smtp.resend.com
   EMAIL_HOST_USER=resend
   EMAIL_HOST_PASSWORD=re_xxxxxxxxxxxx     # sua API key do Resend
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_USE_SSL=False
   DEFAULT_FROM_EMAIL=SantuarioEdu <noreply@santuarioedu.com.br>
   ```
6. Reinicie o servidor. O Django detecta `EMAIL_HOST` preenchido e ativa
   SMTP automaticamente (código em [prf_master/settings.py:251-264](prf_master/settings.py#L251)).

## Testar o envio

```bash
python manage.py shell -c "
from django.core.mail import send_mail
send_mail(
  'Teste SantuarioEdu',
  'Este é um teste do email transacional.',
  None,  # usa DEFAULT_FROM_EMAIL
  ['seu-email-real@gmail.com'],
  fail_silently=False,
)
print('Enviado. Verifique caixa de entrada + spam.')
"
```

## Sem domínio ainda?

Em dev, deixe `EMAIL_HOST=` vazio no `.env`. O Django cai no **console
backend** — os emails aparecem no terminal onde o `runserver` está rodando.
Bom pra desenvolver sem precisar de API real:

```
Content-Type: text/plain; charset="utf-8"
From: SantuarioEdu <noreply@...>
To: usuario@teste.com
Subject: [SantuarioEdu] Confirme seu email
...
Clique aqui pra confirmar: http://127.0.0.1:8000/accounts/confirm-email/xxxxx/
```

## Alternativas se não quiser Resend

| Serviço | Free tier | Nota |
|---------|-----------|------|
| **Resend** (recomendado) | 100/dia · 3k/mês | DX ótima, setup 5min |
| Postmark | 100/mês | Foco em transacional, docs limpas |
| Mailgun | 100/dia por 3 meses | Depois é pago |
| SendGrid | 100/dia | Exige cartão pra criar |
| AWS SES | 62k/mês (se sair do sandbox) | Complexo pra sair do sandbox |
| Brevo (ex-Sendinblue) | 300/dia | BR-friendly, tem PT |
| Gmail SMTP | ~500/dia | Não recomendado (bloqueia sem aviso) |

Todos usam SMTP — trocar entre eles é só mudar `EMAIL_HOST` e
`EMAIL_HOST_PASSWORD` no `.env`.

## LGPD

- Sempre inclua **opt-out** em emails de marketing (link "cancelar
  inscrição"). Emails transacionais (confirmação, recuperação de senha,
  fatura) NÃO precisam de opt-out.
- Registre `PreferenciasNotificacao` do usuário — o app já tem esse
  modelo, respeite a escolha antes de enviar digest/lembretes.
