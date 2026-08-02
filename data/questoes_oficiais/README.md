# Questões Oficiais - Formato de Importação

Arquivos JSON com questões oficiais de provas de concurso público, prontos pra importação via management command.

## Comando

```powershell
railway run python manage.py importar_questoes data/questoes_oficiais/arquivo.json
# ou local:
python manage.py importar_questoes data/questoes_oficiais/arquivo.json
```

**Flags úteis:**
- `--dry_run`: preview sem salvar (validação)
- `--revisada`: marca como já aprovadas (pula fila de revisão)

## Arquivos disponíveis

| Arquivo | Origem | Questões | Gabarito |
|---|---|---|---|
| `prova_analista_fgv_tjrs_2025.json` | TJ-RS Analista Adm — FGV 2025 | 10 | Oficial (Edital nº 37/2025) |
| `simulado_pm_direito_const.json` | Simulado PM (CIASC, TJMG, IPM-SP, TJ-CE, PCSC) | 6 | Confirmado no PDF |

**Total: 16 questões oficiais** com gabarito 100% verificado.

## Formato do JSON

```json
{
  "_meta": {"fonte": "...", "gabarito": "..."},
  "questoes": [
    {
      "categoria_path": "Direito > Direito Constitucional > Subtopico",
      "banca": "FGV",
      "ano": 2025,
      "tipo": "ME",
      "assunto": "Sub-tema específico",
      "texto": "Enunciado completo...",
      "alternativas": [
        {"texto": "A", "correta": false},
        {"texto": "B", "correta": true}
      ]
    },
    {
      "categoria_path": "Direito > Direito Constitucional",
      "banca": "Cebraspe",
      "ano": 2018,
      "tipo": "CE",
      "texto": "Enunciado...",
      "resposta_ce": "C"
    }
  ]
}
```

## Segurança e dedup

- `texto_hash` (SHA-256 do enunciado normalizado) é auto-calculado no `save()` do model
- Rodar o comando várias vezes com o mesmo arquivo NÃO duplica questões
- Dedup é global (mesmo entre bancas/anos diferentes)

## Expandindo com mais provas

Pra adicionar mais questões:
1. Baixe PDFs oficiais dos sites das bancas (Cebraspe, FGV, FCC, VUNESP, etc.)
2. Extraia via `importar_pdf_questoes` (usa IA Gemini Vision), OU
3. Crie manualmente novo JSON seguindo o formato acima

Ambas as abordagens aproveitam o dedup automático.
