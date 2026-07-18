# Pipeline de conteúdo — geração e validação de questões

Como criar questões novas com qualidade consistente, sustentando o cap
diário da IA.

## Fluxo de 3 passos

```
1. gerar_questoes_ia       → gera enunciado + alternativas + assunto (sem justif)
2. gerar_justificativas_ia → gera justificativa no formato SantuarioEdu (6 blocos)
3. auditar_questoes --fix  → normaliza formatação + reverte aprovações com problemas
4. validar_questoes_auto   → aprova em bulk quem passa em heurísticas
5. /admin-revisao/         → revisão humana das restantes (com filtros por problema)
```

### Por que dividir em 2 passos (geração + justificativa)?

- **Consistência**: o prompt de justificativa é centralizado em
  [prompts_justificativa.py](quiz/prompts_justificativa.py) — sempre sai
  no formato SantuarioEdu (🔍 Por que · ⚠️ Armadilhas · 🧠 Conceito · 🎯 Testa · 📚 Aprofundar · 💡 Padrão).
- **Robustez**: gerar questão + justificativa no mesmo prompt = JSON gigante,
  fácil truncar. Separando, cada request é menor e mais estável.
- **Iteração**: se descobrir que quer mudar o formato da justificativa,
  edita **um** arquivo e regenera com `--regenerar --formato_antigo`.
- **Economia**: se o modelo falhar na geração da justificativa, você não
  perde a questão inteira — só reagenda o passo 2.

## Comandos

### Passo 1 — gerar questões

```bash
# Padrão: 10 questões, banca Cebraspe, múltipla escolha
python manage.py gerar_questoes_ia --categoria "Direito Penal" --qtd 30

# Certo/Errado
python manage.py gerar_questoes_ia --categoria "Direito Constitucional" --qtd 50 --tipo CE

# Foco em sub-tema
python manage.py gerar_questoes_ia --categoria "Direito Penal" --qtd 20 --assunto "Prisão em flagrante"

# Categoria nova
python manage.py gerar_questoes_ia --categoria "Direito Empresarial" --qtd 20 --criar-se-necessario
```

Consumo típico: ~5-10 requests por batch de 8 questões (Groq).

### Passo 2 — gerar justificativas

```bash
# Pega até 20 questões sem justificativa (padrão)
python manage.py gerar_justificativas_ia

# Muito conteúdo pendente? Rode em lotes de 100 respeitando quota diária
python manage.py gerar_justificativas_ia --limit 100

# Só uma categoria
python manage.py gerar_justificativas_ia --limit 50 --categoria "Direito Penal"

# Ver quantas serão processadas antes de rodar
python manage.py gerar_justificativas_ia --dry_run

# Regenerar formato antigo (só quem NÃO tem 🔍 no texto)
python manage.py gerar_justificativas_ia --regenerar --formato_antigo --limit 100
```

Consumo típico: ~1 request por questão, ~2000 tokens output cada.
Custo diário Groq free: ~50 justificativas antes de estourar.

### Passo 3 — auditar problemas de qualidade

```bash
# Só relatório (não altera nada)
python manage.py auditar_questoes

# Aplicar fixes seguros (espaços, aspas, escapes literais)
python manage.py auditar_questoes --fix

# + reverter aprovações que ainda ficaram com defeitos graves
python manage.py auditar_questoes --fix --reverter-aprovadas

# Auditar só uma categoria
python manage.py auditar_questoes --categoria "Direito Penal"
```

### Passo 4 — validar automaticamente

```bash
# Dry-run: mostra quantas seriam aprovadas sem tocar em nada
python manage.py validar_questoes_auto --dry-run

# Aprova de verdade (só quem passa em TODAS as regras)
python manage.py validar_questoes_auto
```

### Passo 5 — revisão humana

Acesse [/admin-revisao/](http://127.0.0.1:8000/admin-revisao/) e use os
filtros do dropdown "Problema":

- **Sem problemas detectados** → prontas pra aprovar (tecla `A`)
- **Enunciado incompleto** → reprovar pra IA refazer (tecla `R`)
- **Cita imagem inexistente** → rejeitar em massa
- **Sem gabarito** → editar no admin Django
- **Sem justificativa** → deixar por último, rodar passo 2

Atalhos: `A` aprovar · `R` reprovar · `X` excluir · `B` bulk approve · `→` próxima.

## Cronograma sustentável (banco de 0 → 2000 questões)

Assumindo que você quer chegar a **2000 questões aprovadas** e a IA free
tier cobre ~150 chamadas/dia por provider:

| Dia | Ação | Novas questões prontas |
|---|---|---:|
| 1 | 200Q em 5 categorias + gerar justif. 150 | ~150 aprovadas |
| 2 | Auditar + reverter + validar auto. Gerar mais 150 justif | +150 |
| 3-5 | Repetir passo 2 diário | +450 |
| 6 | Se tudo aprovado, gerar +300Q em disciplinas remanescentes | — |
| 7-10 | Ciclo justif+valid diário | +600 |
| Total ~10 dias | Sustentável, sem custo | **~1500 aprovadas** |

## Monitoramento

Antes de qualquer geração pesada, acesse `/admin-metricas/` e veja "Uso
de IA hoje" — se Groq estiver amarelo/vermelho, deixe pra amanhã ou
aceite que vai cair no fallback Gemini (mais lento e às vezes bloqueia
por copyright).

## Custos estimados no free tier

- **0-500 questões**: cabe tranquilo no Groq (100k tokens/dia)
- **500-1500 questões**: precisa espalhar em 5-10 dias
- **1500+**: valia US$5/mês Groq Dev Tier (10x quota)
