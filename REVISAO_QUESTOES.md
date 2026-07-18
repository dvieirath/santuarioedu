# Ciclo de Revisão Humana das Questões

Toda questão gerada pela IA passa por você antes de ser publicada.
Quando você reprovar com motivo, a IA tenta corrigir baseado no seu feedback.

## Os 4 estados de uma questão

```
              ┌─────────────┐
              │ IA gera     │
              └──────┬──────┘
                     ▼
              ┌─────────────┐
              │  PENDENTE   │  ← aguardando você revisar
              └──┬──────────┘
                 │
       ┌─────────┼─────────────┐
       ▼         ▼             ▼
   ┌────────┐ ┌───────────┐ ┌─────────────┐
   │APROVADA│ │EM CORREÇÃO│ │ REJEITADA   │
   │  ✓     │ │  🤖       │ │ definitiva  │
   │visível │ │ + motivo  │ │  ⛔         │
   └────────┘ └─────┬─────┘ └─────────────┘
                    │
                    ▼ IA reescreve
                    │
                    └──► volta para PENDENTE
                         (com tentativas+1)
                         até max 3 tentativas
```

## Como usar no dia-a-dia

### 1. Geração (uma vez por categoria)

```bash
# Gera lote padrão PRF (690 questões em ~30min)
python manage.py gerar_lote_completo --preset prf

# Ou gera uma categoria específica
python manage.py gerar_questoes_ia --categoria "Direito Constitucional" --qtd 100
```

Todas entram como **PENDENTE** (`revisada=False`, `motivo_rejeicao=''`).

### 2. Revisão pelo admin

Acesse: **`/admin/quiz/questao/?revisada__exact=0&gerada_por_ia__exact=1&motivo_rejeicao__exact=`**

Para cada questão você tem 4 ações no menu suspenso:

| Ação | Resultado |
|---|---|
| **✓ Aprovar** | Vira `aprovada`, visível aos usuários |
| **✗ Reprovar (motivo padrão)** | Marca para IA refazer com prompt genérico |
| **⛔ Rejeitar DEFINITIVAMENTE** | Descarta de vez, não tenta mais |
| **🤖 Reprocessar agora pela IA** | Aciona correção imediata (precisa ter motivo) |

### 3. Reprovação com motivo específico (melhor resultado)

Em vez de usar a action genérica, **edite a questão** e preencha o campo
**"Motivo da rejeição"** com instruções claras:

> Exemplos de motivo bem escrito:
> - "A alternativa B também está correta, ambígua. Refaça com gabarito único."
> - "Justificativa não cita o artigo da CF/88. Acrescente a base legal."
> - "Enunciado muito longo e confuso. Simplifique mantendo o conteúdo."
> - "Tema fora do edital do INSS — troque por algo de Direito Previdenciário."

Salve. A questão fica em **EM CORREÇÃO** (status azul).

### 4. Processar as reprovadas

Quando tiver várias com motivo, rode:

```bash
# Processa até 20 questões (default)
python manage.py corrigir_rejeitadas

# Quantas processar nesta rodada
python manage.py corrigir_rejeitadas --limit 50

# IDs específicos
python manage.py corrigir_rejeitadas --ids 123,124,125

# Limite de tentativas (default 3)
python manage.py corrigir_rejeitadas --max_tentativas 3
```

A IA recebe:
- Texto original da questão
- Alternativas + gabarito originais
- **Seu motivo** (instruções de correção)

E retorna uma versão corrigida que **volta automaticamente para PENDENTE** com tentativas+1.

### 5. Após 3 tentativas

Se a IA falhar 3 vezes seguidas no mesmo motivo, a questão é marcada como
**rejeitada definitiva** e não tenta mais. Você pode:
- Editar manualmente
- Excluir definitivamente
- Mudar `rejeitada_definitiva=False` se quiser dar nova chance

## Filtros úteis no admin

| URL | Mostra |
|---|---|
| `/admin/quiz/questao/?revisada__exact=1` | Apenas aprovadas (visíveis aos usuários) |
| `/admin/quiz/questao/?revisada__exact=0&gerada_por_ia__exact=1&motivo_rejeicao__exact=` | **Pendentes** (aguardando sua revisão) |
| `/admin/quiz/questao/?revisada__exact=0` + filtro com motivo preenchido | Em correção |
| `/admin/quiz/questao/?rejeitada_definitiva__exact=1` | Rejeitadas definitivas |

## Métricas

```bash
python manage.py shell -c "
from quiz.models import Questao
print(f'Aprovadas:           {Questao.objects.filter(revisada=True).count()}')
print(f'Pendentes:           {Questao.objects.filter(revisada=False, motivo_rejeicao=\"\", rejeitada_definitiva=False).count()}')
print(f'Em correção:         {Questao.objects.exclude(motivo_rejeicao=\"\").filter(revisada=False, rejeitada_definitiva=False).count()}')
print(f'Rejeitadas:          {Questao.objects.filter(rejeitada_definitiva=True).count()}')
"
```

## Workflow recomendado

```
1. python manage.py gerar_lote_completo --preset prf    (gera 690)
2. Admin → revisa em lotes de 20-30                     (3-4 horas total)
3. Aprovadas → publicadas automaticamente
4. Reprovadas com motivo → entram na fila
5. python manage.py corrigir_rejeitadas                 (IA refaz)
6. Volta ao passo 2 com as corrigidas
7. Após 3 tentativas, rejeitadas definitivas são descartadas
```
