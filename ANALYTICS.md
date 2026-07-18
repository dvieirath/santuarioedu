# Analytics — Guia curto

Sem analytics você não sabe:
- Quantas pessoas visitam a landing
- Quantos vão do `/planos/` até clicar em "Assinar"
- Onde os usuários abandonam o funil
- Quais páginas dão erro

O código já suporta **Plausible** (recomendado) e **Google Analytics 4**.

## Opção A — Plausible (recomendado)

**Vantagens**: cookieless (não precisa cookie banner), LGPD-friendly,
dashboard limpo, ~1KB de script (não impacta performance).
**Custo**: US$ 9/mês para até 10k pageviews (não tem free tier permanente,
mas tem trial 30 dias).

Setup (2 min):
1. Cadastre em <https://plausible.io/register>
2. Adicione seu site (URL: `santuarioedu.com.br`)
3. Cole no `.env`:
   ```
   PLAUSIBLE_DOMAIN=santuarioedu.com.br
   ```
4. Reinicie. Pronto — o partial [analytics.html](quiz/templates/includes/analytics.html)
   injeta o script automaticamente na landing e no dashboard.

## Opção B — Google Analytics 4 (grátis)

**Vantagens**: grátis, ecossistema Google, integração com Ads/Search Console.
**Desvantagem**: usa cookies, requer opt-in explícito no cookie banner.

Setup (5 min):
1. <https://analytics.google.com> → Admin → Criar propriedade → Web
2. Copie o **Measurement ID** (formato `G-XXXXXXXXXX`)
3. Cole no `.env`:
   ```
   GA_MEASUREMENT_ID=G-XXXXXXXXXX
   ```
4. Reinicie. O partial só ativa GA quando o usuário aceita "Análise de uso"
   no cookie banner (respeita LGPD).

## O que trackear além de pageviews?

Eventos custom que valem ouro no funnel:

```javascript
// Em planos.html — quando clicam Assinar
if (window.plausible)  plausible('Assinar', { props: { plano: 'pro' } });
if (window.gtag)       gtag('event', 'begin_checkout', { plano: 'pro' });

// Em pagamento_retorno.html sucesso
if (window.plausible)  plausible('Pagamento aprovado');
if (window.gtag)       gtag('event', 'purchase', { value: 14.90, currency: 'BRL' });

// Em cadastro concluído
if (window.plausible)  plausible('Cadastro');
if (window.gtag)       gtag('event', 'sign_up');
```

## Qual escolher?

- **Só quer saber quem entra e por onde sai** → Plausible (10x mais fácil)
- **Precisa integração com Google Ads / Search Console** → GA4
- **Nunca vai gastar em marketing** → Plausible
- **Vai fazer campanha paga** → GA4 obrigatório
