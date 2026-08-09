#!/usr/bin/env python3
"""Baixa provas e gabaritos oficiais de concursos publicos e salva um PDF
mesclado (prova + gabarito) por prova, com nome legivel, em uma pasta local.

Exemplos:

  # Achar o "slug" (identificador na URL) de um concurso pelo nome
  python baixar_provas.py buscar PRF

  # Baixar e mesclar tudo de um ou mais concursos do Cebraspe
  python baixar_provas.py cebraspe PRF_21
  python baixar_provas.py cebraspe PRF_21 PF_25 --saida "D:\\provas"

  # FGV: passe o slug da URL (conhecimento.fgv.br/concursos/<slug>) ou a URL inteira
  python baixar_provas.py fgv rfb22

  # Outras bancas sem adaptador dedicado: passe a URL da pagina de provas/gabaritos
  python baixar_provas.py generico "https://www.exemplo.com.br/concurso/xyz" --nome "TRT SP 2024"

Por padrao os PDFs mesclados vao para ~/Downloads/provas_concursos/<slug>/.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bancas import cebraspe, fgv, generico
from bancas.base import Documento, baixar_pdf, mesclar_pdfs, nome_arquivo_seguro, parear

PASTA_SAIDA_PADRAO = Path.home() / "Downloads" / "provas_concursos"


def processar_documentos(
    nome_concurso: str,
    slug_ou_id: str,
    documentos: list[Documento],
    pasta_saida: Path,
) -> None:
    if not documentos:
        print(f"  Nenhuma prova/gabarito encontrado para '{nome_concurso}'.")
        return

    pares = parear(documentos)
    pasta_concurso = pasta_saida / nome_arquivo_seguro(slug_ou_id)
    pasta_bruta = pasta_concurso / "_baixados"

    print(f"  {nome_concurso}: {len(pares)} prova(s) encontrada(s).")
    for prova, gabarito in pares:
        try:
            caminho_prova = baixar_pdf(prova.url, pasta_bruta / Path(prova.url).name)
        except Exception as exc:
            print(f"    [ERRO] nao baixou a prova '{prova.titulo}': {exc}")
            continue

        caminhos = [caminho_prova]
        sufixo = "COM_GABARITO"
        if gabarito is not None:
            try:
                caminho_gabarito = baixar_pdf(gabarito.url, pasta_bruta / Path(gabarito.url).name)
                caminhos.append(caminho_gabarito)
            except Exception as exc:
                print(f"    [AVISO] baixou a prova mas nao o gabarito '{gabarito.titulo}': {exc}")
                sufixo = "SEM_GABARITO"
        else:
            sufixo = "SEM_GABARITO"
            print(f"    [AVISO] nao achei gabarito para '{prova.titulo}' (salvando so a prova)")

        nome_final = nome_arquivo_seguro(nome_concurso, prova.titulo, sufixo) + ".pdf"
        destino = pasta_concurso / nome_final
        if destino.exists():
            print(f"    ja existe: {destino.name}")
            continue
        try:
            mesclar_pdfs(caminhos, destino)
            print(f"    OK: {destino.name}")
        except Exception as exc:
            print(f"    [ERRO] falha ao mesclar '{prova.titulo}': {exc}")


def cmd_buscar(args: argparse.Namespace) -> None:
    achados = cebraspe.buscar_slug_por_nome(args.termo)
    if not achados:
        print(f"Nenhum concurso do Cebraspe encontrado para '{args.termo}'.")
        return
    print(f"{len(achados)} concurso(s) encontrado(s):\n")
    for c in achados:
        print(f"  {c['slug']:<28} {c['nome']}  [{c['status']}, {c['ano']}]")
    print("\nUse o valor da coluna da esquerda (slug) com: python baixar_provas.py cebraspe <slug>")


def cmd_cebraspe(args: argparse.Namespace) -> None:
    pasta_saida = Path(args.saida) if args.saida else PASTA_SAIDA_PADRAO
    for slug in args.slugs:
        print(f"\n=== Cebraspe: {slug} ===")
        try:
            nome, documentos = cebraspe.buscar_documentos(slug)
        except Exception as exc:
            print(f"  [ERRO] nao consegui buscar dados de '{slug}': {exc}")
            continue
        processar_documentos(nome, slug, documentos, pasta_saida)
    print(f"\nArquivos salvos em: {pasta_saida}")


def cmd_fgv(args: argparse.Namespace) -> None:
    pasta_saida = Path(args.saida) if args.saida else PASTA_SAIDA_PADRAO
    for slug in args.slugs:
        print(f"\n=== FGV: {slug} ===")
        try:
            nome, documentos = fgv.buscar_documentos(slug)
        except Exception as exc:
            print(f"  [ERRO] nao consegui buscar dados de '{slug}': {exc}")
            continue
        processar_documentos(nome, slug, documentos, pasta_saida)
    print(f"\nArquivos salvos em: {pasta_saida}")


def cmd_generico(args: argparse.Namespace) -> None:
    pasta_saida = Path(args.saida) if args.saida else PASTA_SAIDA_PADRAO
    print(f"\n=== Pagina: {args.url} ===")
    try:
        nome, documentos = generico.buscar_documentos(args.url)
    except Exception as exc:
        print(f"  [ERRO] nao consegui abrir '{args.url}': {exc}")
        sys.exit(1)
    nome_concurso = args.nome or nome
    identificador = args.nome or nome
    processar_documentos(nome_concurso, identificador, documentos, pasta_saida)
    print(f"\nArquivos salvos em: {pasta_saida}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)

    p_buscar = sub.add_parser("buscar", help="acha o slug de um concurso do Cebraspe pelo nome")
    p_buscar.add_argument("termo", help='ex.: "PRF", "policia federal"')
    p_buscar.set_defaults(func=cmd_buscar)

    p_cebraspe = sub.add_parser("cebraspe", help="baixa provas/gabaritos de um ou mais concursos do Cebraspe")
    p_cebraspe.add_argument("slugs", nargs="+", help="slug(s) do concurso, ex.: PRF_21")
    p_cebraspe.add_argument("--saida", help=f"pasta de destino (padrao: {PASTA_SAIDA_PADRAO})")
    p_cebraspe.set_defaults(func=cmd_cebraspe)

    p_fgv = sub.add_parser("fgv", help="baixa provas/gabaritos de um ou mais concursos da FGV")
    p_fgv.add_argument("slugs", nargs="+", help="slug(s) do concurso, ex.: rfb22 (de conhecimento.fgv.br/concursos/rfb22)")
    p_fgv.add_argument("--saida", help=f"pasta de destino (padrao: {PASTA_SAIDA_PADRAO})")
    p_fgv.set_defaults(func=cmd_fgv)

    p_generico = sub.add_parser("generico", help="baixa provas/gabaritos de outra banca a partir de uma URL")
    p_generico.add_argument("url", help="URL da pagina do concurso que lista os PDFs de prova/gabarito")
    p_generico.add_argument("--nome", help="nome do concurso, usado nos nomes de arquivo (opcional)")
    p_generico.add_argument("--saida", help=f"pasta de destino (padrao: {PASTA_SAIDA_PADRAO})")
    p_generico.set_defaults(func=cmd_generico)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
