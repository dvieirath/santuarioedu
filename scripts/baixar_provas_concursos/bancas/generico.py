"""Adaptador generico para outras bancas (FGV, FCC, Vunesp, IBFC, AOCP, etc.).

Nao ha um adaptador dedicado por banca (cada site organiza as coisas de um
jeito). Este modulo faz o "melhor esforco": abre a URL que voce passar,
procura links para .pdf cujo texto pareca ser de prova ou gabarito, e tenta
parear cada prova com seu gabarito.

Limitacoes:
- Funciona apenas com paginas onde os links de PDF ja vem prontos no HTML.
  Se o site monta a lista via JavaScript (como o proprio Cebraspe faz),
  este adaptador nao vai encontrar nada -- nesse caso e preciso um adaptador
  especifico (veja bancas/cebraspe.py como exemplo de como foi resolvido).
- Passe a URL da pagina especifica do concurso/prova (a que lista os PDFs),
  nao a home do site da banca.
"""
from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import SESSION, Documento, classificar


def buscar_documentos(url_pagina: str) -> tuple[str, list[Documento]]:
    resposta = SESSION.get(url_pagina, timeout=30)
    resposta.raise_for_status()
    soup = BeautifulSoup(resposta.text, "html.parser")

    titulo_el = soup.find("h1") or soup.find("title")
    nome = titulo_el.get_text(strip=True) if titulo_el else url_pagina

    documentos: list[Documento] = []
    vistos: set[str] = set()
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not href.lower().split("?", 1)[0].endswith(".pdf"):
            continue
        titulo = link.get_text(strip=True) or href.rsplit("/", 1)[-1]
        tipo = classificar(titulo)
        if not tipo:
            continue
        url_abs = urljoin(url_pagina, href)
        if url_abs in vistos:
            continue
        vistos.add(url_abs)
        documentos.append(Documento(titulo=titulo, url=url_abs, tipo=tipo))
    return nome, documentos
