# Como aumentar o banco de questões com IA

## Comando principal

```bash
python manage.py gerar_questoes_ia \
  --categoria "Direito Constitucional" \
  --qtd 100 \
  --banca "Cebraspe" \
  --tipo ME
```

## Argumentos

| Flag | Default | Descrição |
|---|---|---|
| `--categoria` | obrigatório | Nome exato da categoria (ex: "Direito Administrativo") |
| `--qtd` | 10 | Quantas questões gerar no total |
| `--batch` | 5 | Quantas por chamada à IA (5 é ideal) |
| `--banca` | Cebraspe | Banca a imitar: Cebraspe, FGV, FCC, Vunesp, IBFC, etc. |
| `--tipo` | ME | `ME` (múltipla escolha) ou `CE` (certo/errado) |
| `--assunto` | — | Sub-tópico específico (ex: "Princípios da Administração") |
| `--model` | gemini-3.1-flash-lite | Modelo Gemini |
| `--delay` | 2.0 | Segundos entre chamadas (evita rate-limit) |

## Exemplos práticos

### Volume rápido para PRF
```bash
# Direito Constitucional (100 questões)
python manage.py gerar_questoes_ia --categoria "Direito Constitucional" --qtd 100 --delay 3

# Direito Administrativo (100 questões)
python manage.py gerar_questoes_ia --categoria "Direito Administrativo" --qtd 100 --delay 3

# Português (100 questões)
python manage.py gerar_questoes_ia --categoria "Língua Portuguesa" --qtd 100 --delay 3

# Raciocínio Lógico (50 questões)
python manage.py gerar_questoes_ia --categoria "Raciocínio Lógico e Matemática" --qtd 50

# Informática (50 questões)
python manage.py gerar_questoes_ia --categoria "Informática" --qtd 50
```

### Cebraspe (certo/errado) — padrão PF/PRF
```bash
python manage.py gerar_questoes_ia --categoria "Direito Penal" --qtd 50 --tipo CE
```

### Focar em sub-tópico
```bash
python manage.py gerar_questoes_ia \
  --categoria "Direito Constitucional" \
  --assunto "Direitos Fundamentais" \
  --qtd 30
```

### Imitar bancas diferentes
```bash
# FGV (estilo TJ-DF)
python manage.py gerar_questoes_ia --categoria "Direito Civil" --qtd 30 --banca "FGV"

# FCC
python manage.py gerar_questoes_ia --categoria "Direito Tributário" --qtd 30 --banca "FCC"
```

---

## Fluxo de revisão

1. **Gere** com o comando acima — questões entram com `revisada=False`
2. **Usuários NÃO veem** essas questões ainda (filtro no sorteio)
3. **Acesse** `/admin/quiz/questao/?revisada__exact=0&gerada_por_ia__exact=1`
4. **Revise** cada questão (texto, gabarito, justificativa)
5. **Selecione** as boas → action **"✓ Aprovar (marcar como revisada)"**
6. As reprovadas → action **"✗ Reprovar e excluir"**

---

## Limites da cota gratuita Gemini

Modelo `gemini-3.1-flash-lite` no free tier:
- **15 RPM** (requests por minuto)
- **1500 requisições/dia** aproximadamente

Com `batch=5`, cada chamada gera 5 questões → **7500 questões/dia teóricas** (na prática 3000-5000 considerando falhas).

**Dica:** rode em background à noite, com `--delay 4`:
```bash
nohup python manage.py gerar_questoes_ia --categoria "X" --qtd 500 --delay 4 > log.txt &
```

---

## Recomendações de qualidade

- **Não gere 1000 de uma vez.** Faça lotes de 50-100, revise, depois mais.
- **Varie as bancas.** Use diferentes valores em `--banca` para diversidade de estilo.
- **Use `--assunto`.** Resulta em questões mais focadas e menos repetitivas.
- **Modelos diferentes.** Tente `--model gemini-3.5-flash` para qualidade superior (consome mais cota).
- **Revise sempre.** Mesmo questões de aparência boa podem ter erros sutis de base legal.

---

## Comandos úteis pós-geração

```bash
# Quantas pendentes de revisão
python manage.py shell -c "from quiz.models import Questao; print(Questao.objects.filter(revisada=False, gerada_por_ia=True).count())"

# Aprovar todas geradas por IA de uma categoria de uma vez (cuidado!)
python manage.py shell -c "from quiz.models import Questao, Categoria; c=Categoria.objects.get(nome='Direito Constitucional'); n=Questao.objects.filter(categoria=c, gerada_por_ia=True).update(revisada=True); print(f'{n} aprovadas')"

# Excluir todas as IA não-revisadas (limpa testes)
python manage.py shell -c "from quiz.models import Questao; n,_=Questao.objects.filter(gerada_por_ia=True, revisada=False).delete(); print(n)"
```
