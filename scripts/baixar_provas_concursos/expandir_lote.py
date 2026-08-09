#!/usr/bin/env python3
"""Baixa (SEM mesclar) prova+gabarito de MAIS concursos e ACRESCENTA ao
manifesto.json existente (sem reescrever do zero, pra nao invalidar os
indices que import_progresso.json ja marcou como concluidos).
"""
from __future__ import annotations

import json
from pathlib import Path

from bancas import cebraspe
from bancas.base import baixar_pdf, parear

RAIZ = Path(__file__).resolve().parent.parent.parent / "provas_pdf" / "materia_prima"
MANIFESTO = RAIZ / "manifesto.json"

# Proxima leva: PF_21 e PRF_21 tem prioridade (tema do projeto). Demais
# ordenados por vagas (proxy de concorrencia/candidatos), 2021+, encerrados.
NOVOS_CONCURSOS_CEBRASPE = [
    "PF_21",
    "PRF_21",
    "IBGE_21_PSS_APM",
    "PC_PB_21",
    "SESAU_AL_21",
    "PM_AL_21",
    "PETROBRAS_21_NS",
    "IBAMA_21",
    "PC_AL_21",
    "SERPRO_21",
    "TCE_SC_21_AUDITOR",
    "CBM_AL_21",
    "SEED_PR_20_PROFESSOR",
    "PM_TO_20_QPPM",
    "PC_DF_20_AGENTE",
    "SEE_PE_22",
    "IBGE_21_PSS_SCQ",
    "PREF_JOINVILLE_22",
    "PETROBRAS_23_NM",
    "ICMBIO_24",
    "ME_20_PSS",
    "DEPEN_20",
    "PC_DF_19_ESCRIVAO",
    "PREF_JOINVILLE_SC_23",
    "IBGE_21_PSS_APT",
    "SEED_SE_25_PROFESSOR",
    "SERIS_AL_21",
    "BANRISUL_22",
    "FUB_25",
    "DATAPREV_23",
]


def ano_do_slug(slug: str) -> int | None:
    for parte in slug.split("_"):
        if parte.isdigit() and len(parte) == 2:
            return 2000 + int(parte)
    return None


def processar_cebraspe(slug: str, manifesto: list[dict], caminhos_existentes: set[str]) -> int:
    print(f"\n=== Cebraspe: {slug} ===")
    try:
        nome, docs = cebraspe.buscar_documentos(slug)
    except Exception as exc:
        print(f"  [ERRO] {exc}")
        return 0
    pares = parear(docs)
    ano = ano_do_slug(slug)
    pasta = RAIZ / slug
    adicionados = 0
    for prova, gabarito in pares:
        if gabarito is None:
            print(f"  [PULA] sem gabarito: {prova.titulo}")
            continue
        # compara pelo CAMINHO LOCAL de destino, que e o que fica gravado no
        # manifesto -- comparar com a URL remota (tipo diferente) nunca bate
        # e deixa passar duplicata toda vez que o script roda de novo.
        caminho_prova = str(pasta / Path(prova.url).name)
        if caminho_prova in caminhos_existentes:
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
        caminhos_existentes.add(caminho_prova)
        adicionados += 1
    return adicionados


def main() -> None:
    manifesto = json.loads(MANIFESTO.read_text(encoding="utf-8")) if MANIFESTO.exists() else []
    caminhos_existentes = {m["prova"] for m in manifesto}
    tamanho_inicial = len(manifesto)

    total_novo = 0
    for slug in NOVOS_CONCURSOS_CEBRASPE:
        total_novo += processar_cebraspe(slug, manifesto, caminhos_existentes)

    MANIFESTO.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n\n{total_novo} novos pares adicionados (manifesto: {tamanho_inicial} -> {len(manifesto)})")


if __name__ == "__main__":
    main()
