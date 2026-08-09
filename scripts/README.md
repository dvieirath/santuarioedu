# Scripts

Utilitários fora do fluxo Django principal.

## Estrutura

- **`baixar_provas_concursos/`** — pipeline de baixar+importar provas oficiais (Cebraspe/FGV) do manifesto.json
- **`manutencao/`** — scripts de fix/check pontuais (imagens, sidebars, questões corrompidas)
- **`dados/`** — importações manuais one-off (ENEM 1999, PF Agente 2025)
- **`testes/`** — smoke tests de conectividade IA (Groq)

Scripts de manutenção geralmente rodam UMA vez pra corrigir estado. Não fazem parte do fluxo normal.

Para tarefas recorrentes, prefira `manage.py` command em `quiz/management/commands/`.
