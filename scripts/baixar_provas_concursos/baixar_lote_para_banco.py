#!/usr/bin/env python3
"""Baixa (SEM mesclar) prova+gabarito de uma lista curada de concursos
grandes/recentes, prontos pra alimentar `manage.py importar_pdf_questoes`
(que exige prova e gabarito como arquivos SEPARADOS, nao mesclados).

Saida: provas_pdf/materia_prima/<slug>/<arquivo>.pdf (nomes originais da banca)
       + um manifesto JSON listando cada par (prova, gabarito, banca, ano, slug)
"""
from __future__ import annotations

import json
from pathlib import Path

from bancas import cebraspe, fgv
from bancas.base import baixar_pdf, parear

RAIZ = Path(__file__).resolve().parent.parent.parent / "provas_pdf" / "materia_prima"

CONCURSOS_CEBRASPE = [
    "SEE_PE_22_EDUCACAO_BASICA",
    "INSS_22",
    "SEDUC_RECIFE_23_PROFESSOR",
    "TELEBRAS_25",
    "PETROBRAS_23_NTJ",
    "MTE_25",
    "SERPRO_23",
    "PC_RO_22",
]
CONCURSOS_FGV = [
    "rfb22",
]


def processar_cebraspe(slug: str, manifesto: list[dict]) -> None:
    print(f"\n=== Cebraspe: {slug} ===")
    try:
        nome, docs = cebraspe.buscar_documentos(slug)
    except Exception as exc:
        print(f"  [ERRO] {exc}")
        return
    pares = parear(docs)
    ano = None
    for parte in slug.split("_"):
        if parte.isdigit() and len(parte) == 2:
            ano = 2000 + int(parte)
    pasta = RAIZ / slug
    for prova, gabarito in pares:
        if gabarito is None:
            print(f"  [PULA] sem gabarito: {prova.titulo}")
            continue
        try:
            cp = baixar_pdf(prova.url, pasta / Path(prova.url).name)
            cg = baixar_pdf(gabarito.url, pasta / Path(gabarito.url).name)
        except Exception as exc:
            print(f"  [ERRO] baixando '{prova.titulo}': {exc}")
            continue
        print(f"  OK: {cp.name}  +  {cg.name}")
        manifesto.append(
            {
                "banca": "Cebraspe",
                "concurso": nome,
                "slug": slug,
                "ano": ano,
                "titulo": prova.titulo,
                "prova": str(cp),
                "gabarito": str(cg),
            }
        )


def processar_fgv(slug: str, manifesto: list[dict], ano_min: int = 2022) -> None:
    print(f"\n=== FGV: {slug} ===")
    try:
        nome, docs = fgv.buscar_documentos(slug)
    except Exception as exc:
        print(f"  [ERRO] {exc}")
        return
    pares = parear(docs)
    pasta = RAIZ / slug
    for prova, gabarito in pares:
        if gabarito is None:
            continue
        # so pega a prova objetiva "principal" (evita os N tipos de caderno repetidos)
        if "TIPO 2" in prova.titulo.upper() or "TIPO 3" in prova.titulo.upper() or "TIPO 4" in prova.titulo.upper():
            continue
        # tenta achar o ano no titulo (formato dd/mm/aaaa no comeco)
        ano = None
        primeira_parte = prova.titulo.split(" - ")[0]
        if "/" in primeira_parte:
            try:
                ano = int(primeira_parte.split("/")[-1])
            except ValueError:
                pass
        if ano and ano < ano_min:
            continue
        try:
            cp = baixar_pdf(prova.url, pasta / Path(prova.url).name)
            cg = baixar_pdf(gabarito.url, pasta / Path(gabarito.url).name)
        except Exception as exc:
            print(f"  [ERRO] baixando '{prova.titulo}': {exc}")
            continue
        print(f"  OK: {cp.name}  +  {cg.name}")
        manifesto.append(
            {
                "banca": "FGV",
                "concurso": nome,
                "slug": slug,
                "ano": ano,
                "titulo": prova.titulo,
                "prova": str(cp),
                "gabarito": str(cg),
            }
        )


def main() -> None:
    manifesto: list[dict] = []
    for slug in CONCURSOS_CEBRASPE:
        processar_cebraspe(slug, manifesto)
    for slug in CONCURSOS_FGV:
        processar_fgv(slug, manifesto)

    caminho_manifesto = RAIZ / "manifesto.json"
    RAIZ.mkdir(parents=True, exist_ok=True)
    caminho_manifesto.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n\n{len(manifesto)} pares prova+gabarito baixados.")
    print(f"Manifesto: {caminho_manifesto}")


if __name__ == "__main__":
    main()
