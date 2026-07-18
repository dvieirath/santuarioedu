# IA — Multi-provider com fallback

A partir desta versão, o SantuarioEdu usa uma **camada unificada** de IA que tenta
múltiplos providers em ordem. Se um falha (quota, indisponível), o próximo é tentado.

## Providers suportados

| Provider | Custo | Quota free | Velocidade | Qualidade PT-BR |
|---|---|---|---|---|
| **Groq** | R$ 0 | 30 req/min, 14400/dia | ⚡⚡⚡ MUITO rápido | Excelente |
| **Gemini** | R$ 0 | 1500/dia | ⚡⚡ rápido | Excelente |

## Setup rápido

### 1. Pegar uma chave do Groq

1. Vai em **https://console.groq.com/keys**
2. Cadastra com e-mail (sem cartão)
3. **Create API Key** → cola o `gsk_...`

### 2. Configurar no `.env`

```env
AI_PROVIDER_ORDER=groq,gemini    # ordem de fallback

GROQ_API_KEY=gsk_xxxxxxxxx        # sua chave Groq
GROQ_MODEL=llama-3.3-70b-versatile   # modelo padrão

GEMINI_API_KEY=AIzaSyxxx          # backup (opcional)
GEMINI_MODEL=gemini-3.1-flash-lite
```

### 3. Testar (sem rodar Django)

```bash
python testar_groq.py
```

Deve responder em ~1 segundo com uma frase sobre a CF/88.

## Como funciona internamente

```python
from quiz.ai_provider import gerar_conteudo, gerar_json

# Texto simples
resposta = gerar_conteudo('Explique a Lei 9.503/97')

# JSON estruturado
questoes = gerar_json('Liste 3 perguntas sobre constitucional em JSON')
```

### Fluxo

1. Lê `AI_PROVIDER_ORDER` (`groq,gemini` por padrão)
2. Para cada provider na ordem:
   - Verifica se tem chave configurada
   - Verifica se não está em cooldown (60s após 429)
   - Tenta gerar resposta
   - Se quota esgota (429), marca cooldown e tenta o próximo
   - Se falha técnica, loga e tenta o próximo
3. Se TODOS falharem, levanta `AIError`

### Cooldown automático

Quando um provider retorna 429 (quota esgotada), ele entra em "cooldown" por 60 segundos.
Durante esse tempo, é pulado automaticamente. Após 60s volta a ser considerado.

## Modelos disponíveis

### Groq (recomendados)

| Modelo | Tamanho | Velocidade | Uso ideal |
|---|---|---|---|
| `llama-3.3-70b-versatile` | 70B | rápido | **default** — melhor qualidade |
| `llama-3.1-8b-instant` | 8B | super rápido | respostas curtas |
| `mixtral-8x7b-32768` | 47B | rápido | contexto longo (32k tokens) |
| `gemma2-9b-it` | 9B | rápido | alternativa |

### Gemini

| Modelo | Uso |
|---|---|
| `gemini-3.1-flash-lite` | **default** — mais barato/rápido |
| `gemini-3.5-flash` | qualidade superior, mais caro |
| `gemini-3.1-pro-preview` | máxima qualidade (lento) |

## Funções no `ai_provider.py`

| Função | Uso |
|---|---|
| `gerar_conteudo(prompt, json_mode=False, max_tokens=2048, temperature=0.7)` | retorna string |
| `gerar_json(prompt, **kwargs)` | retorna dict (já parseado) |
| `listar_providers_disponiveis()` | diagnóstico — quais providers prontos |

## Quotas detalhadas

### Groq Free Tier
- 30 requests/minuto
- 14.400 requests/dia
- Sem limite mensal
- Total: ~432.000 requests/mês

### Gemini Free Tier
- 15 requests/minuto
- 1.500 requests/dia
- Modelo flash: 1M tokens/dia

### Estratégia recomendada
- **Groq** como principal (10x mais quota)
- **Gemini** como fallback (caso Groq caia)

## Migração do código antigo

Antes:
```python
import google.generativeai as genai
genai.configure(api_key=settings.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.1-flash-lite')
resp = model.generate_content(prompt)
texto = resp.text
```

Depois:
```python
from quiz.ai_provider import gerar_conteudo
texto = gerar_conteudo(prompt)
```

Ou (compatibilidade total):
```python
from quiz.ai_service import _call_ia
resp = _call_ia(prompt)   # tem .text como antes
```

## Troubleshooting

| Sintoma | Causa | Solução |
|---|---|---|
| "Todos os providers falharam" | Nenhuma chave configurada | Configurar GROQ_API_KEY no .env |
| Sempre vai pro Gemini | GROQ_API_KEY vazia | Configurar chave |
| Latência alta | Modelo grande | Trocar pra `llama-3.1-8b-instant` |
| JSON inválido | Modelo não respeitou formato | Usar `gerar_json()` ao invés de parsear manual |

## Limites legais

- Conteúdo gerado pela IA tem **disclaimer obrigatório** em todas as páginas
- Banner em `includes/disclaimer_ia.html`
- Aviso no chat Tutor IA
- Termos de Uso já cobrem "IA pode errar"
