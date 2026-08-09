"""Adaptador para o site da FGV Conhecimento (conhecimento.fgv.br/concursos/<slug>).

Diferente do Cebraspe, a pagina da FGV e renderizada no servidor (da pra ler
com requests puro), mas os arquivos vem agrupados em blocos
`paragraph--type--texto-data`. Dentro de cada bloco os paragrafos formam uma
mini-arvore por indentacao, por exemplo:

    <p><strong>Prova Objetiva</strong></p>                              (titulo do bloco)
    <p><strong>Nivel Superior</strong></p>                              (sub-titulo, sem link)
    <p class="Indent1"><strong>Auditor-Fiscal ... (Manha)</strong></p>  (sub-titulo, sem link)
    <p class="Indent2"><a href="...tipo-1.pdf">Tipo 1</a></p>           (arquivo)
    <p class="Indent2"><a href="...tipo-2.pdf">Tipo 2</a></p>           (arquivo)
    <p class="Indent1"><strong>Auditor-Fiscal ... (Tarde)</strong></p>  (sub-titulo, sem link)
    <p class="Indent2"><a href="...tipo-1.pdf">Tipo 1</a></p>           (arquivo)
    ...

Ou, no caso mais simples (a maioria), o bloco tem um unico paragrafo que ja
e o proprio link:

    <p><a href="...">Gabarito Oficial Definitivo da Prova Objetiva</a></p>

Por isso percorremos os paragrafos em ordem, guardamos o ultimo "sub-titulo"
visto (linha em negrito sem link) e usamos ele + o titulo do bloco pra
identificar de forma unica cada arquivo -- sem isso, arquivos diferentes
(ex.: "Tipo 1" do turno da manha x "Tipo 1" do turno da tarde) teriam o
mesmo nome e um acabaria "sumindo" (achando que ja tinha sido baixado).
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from .base import SESSION, Documento, classificar

_URL_CONCURSO = "https://conhecimento.fgv.br/concursos/{slug}"


def buscar_documentos(slug_ou_url: str) -> tuple[str, list[Documento]]:
    """Retorna (nome do concurso, lista de provas/gabaritos) para um concurso da FGV.

    Aceita tanto o slug (ex.: 'rfb22', da URL conhecimento.fgv.br/concursos/rfb22)
    quanto a URL completa.
    """
    url = slug_ou_url if slug_ou_url.startswith("http") else _URL_CONCURSO.format(slug=slug_ou_url)
    resposta = SESSION.get(url, timeout=30)
    resposta.raise_for_status()
    soup = BeautifulSoup(resposta.text, "html.parser")

    titulo_pagina = soup.find("h1")
    nome_concurso = titulo_pagina.get_text(strip=True) if titulo_pagina else url

    documentos: list[Documento] = []
    for grupo in soup.select(".paragraph--type--texto-data"):
        campo_titulo = grupo.select_one(".field--name-field-td-texto")
        if not campo_titulo:
            continue
        paragrafos = campo_titulo.find_all("p")
        if not paragrafos:
            continue

        titulo_bloco = paragrafos[0].get_text(" ", strip=True)
        tipo = classificar(titulo_bloco)
        if not tipo:
            continue  # bloco que nao e prova nem gabarito (comunicado, resultado, etc.)

        campo_data = grupo.select_one(".field--name-field-td-data time")
        data = campo_data.get_text(strip=True) if campo_data else None

        sub_titulo: str | None = None
        for p in paragrafos:
            link = p.find("a", href=True)
            if link is None:
                texto_p = p.get_text(" ", strip=True)
                if texto_p and texto_p != titulo_bloco:
                    sub_titulo = texto_p
                continue

            href = link["href"]
            if not href.lower().split("?", 1)[0].endswith(".pdf"):
                continue

            texto_link = link.get_text(strip=True)
            ja_presente = {titulo_bloco.lower(), (sub_titulo or "").lower()}
            partes = [data, titulo_bloco, sub_titulo]
            if texto_link and texto_link.lower() not in ja_presente:
                partes.append(texto_link)
            titulo_completo = " - ".join(p for p in partes if p)
            documentos.append(Documento(titulo=titulo_completo, url=href, tipo=tipo))

    return nome_concurso, documentos
