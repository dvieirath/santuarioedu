# Pivot: de "Concurseiros" para "Estudos com IA"

## Motivação

Reduzir risco legal (CDC Art. 37 — propaganda enganosa se prometer aprovação)
e ampliar mercado além de concurseiros.

## Nova narrativa

| Antes | Depois |
|---|---|
| "Prepare-se para concursos com IA" | **"Estude com inteligência"** |
| "Estude o essencial. Seja aprovado." | **"Aprenda mais em menos tempo"** |
| "Plataforma para concursos" | **"Plataforma de estudos com IA"** |
| "IA treinada para concursos" | **"IA que analisa seus erros e propõe caminhos"** |
| "Modo Prova Real" (sidebar) | **"Cronometrado"** |
| "Simulados por Edital" (sidebar) | **"Prontos"** (mantém funcionalidade) |
| "Concurso de interesse" (perfil) | **"Objetivo de estudo"** |
| "Quando espera fazer a prova?" | **"Você tem uma data-alvo?"** |
| "Seja aprovado" (passo 3 onboarding) | **"Evolua com dados"** |

## O que **NÃO** mudou

- Nome "SantuarioEdu" (já era neutro)
- Categorias, banca, ano das questões (metadados técnicos)
- Recursos técnicos (simulados, IA, revisão espaçada continuam iguais)
- Preços, planos, cupons, indicação
- Legal/segurança/deploy — tudo intacto

## Arquivos atualizados

- `templates/landing.html` — hero, features, "como funciona", footer
- `templates/faq.html` — 3 primeiras perguntas + Prova Real
- `templates/legal/termos.html` — descrição da plataforma + limitação de responsabilidade
- `templates/legal/privacidade.html` — "concurso de interesse" → "objetivo de estudo"
- `templates/quiz/onboarding_concurso.html` — títulos das 3 telas
- `templates/quiz/includes/sidebar.html` — labels "Prova real" → "Cronometrado", "Por edital" → "Prontos"
- `templates/quiz_qual_concurso.html` — título/OG
- `static/quiz/manifest.json` — description
- `static/quiz/og-image.svg` — headline

## O que ainda pode virar (opcional, próximas iterações)

- Renomear model `ConcursoPreferido` → `ObjetivoEstudo` (migration + rename)
- Renomear rota `/qual-concurso/` → `/perfil-de-estudo/`
- Reescrever perguntas do quiz lead magnet (hoje ainda focadas em cargo público)
- Adicionar tags à categoria: `["vestibular", "concurso", "graduação"]`
- Simplificar EDITAIS_OFICIAIS pra "Modelos de Prova" (com bancas anonimizadas)

## Impacto legal

- ✅ Elimina afirmação de resultado ("seja aprovado" → "evolua")
- ✅ Não menciona propaganda enganosa
- ✅ Termos agora falam de "apoio ao aprendizado", não promessa
- ✅ Disclaimer "Não garantimos aprovação" saiu da landing (não precisa mais afirmar isso porque não vendemos aprovação)
