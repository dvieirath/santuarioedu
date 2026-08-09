#!/usr/bin/env python3
"""Le provas_pdf/materia_prima/manifesto.json e roda
`manage.py importar_pdf_questoes` (extracao via IA) pra cada par prova+gabarito,
sequencialmente. Loga tudo em provas_pdf/materia_prima/import_log.txt e
grava progresso em provas_pdf/materia_prima/import_progresso.json (pra dar
pra checar de fora sem esperar o processo terminar).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent.parent
MANIFESTO = RAIZ_PROJETO / "provas_pdf" / "materia_prima" / "manifesto.json"
LOG = RAIZ_PROJETO / "provas_pdf" / "materia_prima" / "import_log.txt"
PROGRESSO = RAIZ_PROJETO / "provas_pdf" / "materia_prima" / "import_progresso.json"
PYTHON = RAIZ_PROJETO / "venv" / "Scripts" / "python.exe"


def carregar_progresso() -> dict:
    if PROGRESSO.exists():
        return json.loads(PROGRESSO.read_text(encoding="utf-8"))
    return {"concluidos_idx": [], "resultados": []}


def salvar_progresso(progresso: dict) -> None:
    PROGRESSO.write_text(json.dumps(progresso, ensure_ascii=False, indent=2), encoding="utf-8")


# Prompt de teste do MESMO tamanho de um chunk real -- um prompt de 20 tokens
# passa mesmo quando a cota diaria nao aguenta mais nenhuma chamada de
# verdade (Groq TPD e por token, nao por request), entao o teste tem que
# gastar uma quantidade de tokens parecida com a extracao real.
_TEXTO_TESTE = ("lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod "
                "tempor incididunt ut labore et dolore magna aliqua ") * 60


def cota_esgotada() -> bool:
    """Chamada de IA do MESMO tamanho de uma chamada real, pra confirmar se
    a cota diaria (Groq + Gemini) realmente acabou."""
    checagem = subprocess.run(
        [str(PYTHON), "-c",
         "import django, os\n"
         "os.environ.setdefault('DJANGO_SETTINGS_MODULE','prf_master.settings')\n"
         "django.setup()\n"
         "from quiz.ai_provider import gerar_json, AIError\n"
         "texto = " + repr(_TEXTO_TESTE) + "\n"
         "prompt = 'Extraia questoes deste texto: ' + texto + ' Responda em JSON: {\"questoes\": []}'\n"
         "try:\n"
         "    gerar_json(prompt, max_tokens=4096, temperature=0.2)\n"
         "    print('QUOTA_OK')\n"
         "except AIError as e:\n"
         "    print('QUOTA_ESGOTADA:', e)\n"],
        cwd=str(RAIZ_PROJETO), capture_output=True, text=True, timeout=60,
        encoding="utf-8", errors="replace",
    )
    return "QUOTA_ESGOTADA" in checagem.stdout


def main() -> bool:
    """Roda o lote. Retorna True se terminou tudo, False se pausou por cota."""
    manifesto = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    progresso = carregar_progresso()
    ja_feitos = set(progresso["concluidos_idx"])

    with open(LOG, "a", encoding="utf-8") as log:
        log.write(f"\n\n{'=' * 70}\nInicio da importacao: {time.ctime()}\n{'=' * 70}\n")

        for idx, item in enumerate(manifesto):
            if idx in ja_feitos:
                continue

            # Fallback categoria = "Prova <slug>" (bucket temporario)
            # + --auto_categoria: IA classifica cada questao em disciplina
            # real (Direito Const, Matematica, Fisica, etc). Depois passa
            # pelo reclassificar_por_tema pra pegar as que a IA nao fechou.
            categoria = f"Prova {item['slug']}"
            cmd = [
                str(PYTHON), "manage.py", "importar_pdf_questoes",
                "--arquivo", item["prova"],
                "--gabarito", item["gabarito"],
                "--banca", item["banca"],
                "--categoria", categoria,
                "--auto_categoria",  # <-- fix: IA classifica cada questao por assunto
            ]
            if item.get("ano"):
                cmd += ["--ano", str(item["ano"])]

            cabecalho = f"\n[{idx + 1}/{len(manifesto)}] {item['slug']} :: {item['titulo'][:80]}"
            print(cabecalho)
            log.write(cabecalho + "\n")
            log.flush()

            try:
                resultado = subprocess.run(
                    cmd, cwd=str(RAIZ_PROJETO), capture_output=True, text=True,
                    timeout=1800, encoding="utf-8", errors="replace",
                )
                log.write(resultado.stdout[-4000:])
                if resultado.returncode != 0:
                    log.write(f"\n[ERRO retcode={resultado.returncode}]\n{resultado.stderr[-2000:]}\n")
                    status = "erro"
                elif "Nenhuma questao extraida deste PDF" in resultado.stdout:
                    status = "vazio"
                else:
                    status = "ok"
            except subprocess.TimeoutExpired:
                log.write("\n[TIMEOUT apos 30min]\n")
                status = "timeout"
            except Exception as exc:
                log.write(f"\n[EXCECAO] {exc}\n")
                status = "excecao"

            log.flush()

            # Zero questoes extraidas quase sempre e cota esgotada, nao PDF
            # ruim. Confirma ANTES de marcar como concluido -- se for cota,
            # este item fica pendente pra retomar depois (nao grava).
            if status == "vazio":
                log.write("  [VERIFICANDO] 0 questoes — checando cota da IA...\n")
                log.flush()
                if cota_esgotada():
                    log.write(
                        "\n[PAUSADO] Cota diaria da IA esgotada (Groq + Gemini). "
                        "Este item NAO foi marcado como concluido. "
                        "Rode de novo mais tarde pra continuar de onde parou.\n"
                    )
                    log.write(f"\nFIM (pausado por cota): {time.ctime()}\n")
                    print("\n[PAUSADO] Cota da IA esgotada.")
                    return False
                log.write("  [OK] Nao e cota — PDF realmente sem questoes extraiveis.\n")

            progresso["concluidos_idx"].append(idx)
            progresso["resultados"].append({"idx": idx, "slug": item["slug"], "titulo": item["titulo"], "status": status})
            salvar_progresso(progresso)

        log.write(f"\n\nFIM: {time.ctime()}\n")

    print("\nImportacao em lote concluida. Veja o log em:", LOG)
    return True


if __name__ == "__main__":
    main()
