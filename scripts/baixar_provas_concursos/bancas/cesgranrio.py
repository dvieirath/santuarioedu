"""Adaptador para a Fundação Cesgranrio (cesgranrio.org.br).

A página de cada concurso (ex.: https://www.cesgranrio.org.br/concurso/banco-do-brasil-bb-01-2022/)
lista os PDFs em três blocos, e os nomes enganam:

  Provas:              "PROVA A – AGENTE COMERCIAL – GABARITO 1" ... "GABARITO 5"
                       São os CADERNOS de questões. "GABARITO n" é o número da
                       versão do caderno (mesmas questões, ordem diferente).
  Gabaritos:           um PDF por prova, com as respostas das cinco versões.
                       É o gabarito PRELIMINAR.
  Gabaritos Alterados: publicado depois dos recursos. É o DEFINITIVO. Nem toda
                       prova tem; quando não tem, vale o preliminar.

As pastas do servidor também não ajudam: no concurso de 2021 os cadernos estão
em .../gabarito/ e os gabaritos em .../provas/; no de 2022 é o contrário. Por
isso a classificação usa o texto do link e não a URL.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .base import SESSION, Documento, baixar_pdf, normalizar

_PAGINA = "https://www.cesgranrio.org.br/concurso/{slug}/"
_RE_LINK = re.compile(
    r'<a[^>]+href="([^"]+storage\.ashx\?file=pdf/[^"]+\.pdf)"[^>]*>(.*?)</a>',
    re.S | re.I,
)
_RE_TITULO = re.compile(r"<title>(.*?)</title>", re.S | re.I)
_RE_VERSAO_CADERNO = re.compile(r"\bGABARITO (\d)$")
_RE_LETRA_PROVA = re.compile(r"\bPROVA ([A-Z])\b")


@dataclass
class ProvaCesgranrio:
    """Uma prova do concurso, com seus cadernos e gabaritos."""

    chave: str                      # "PROVA A", "TECNOLOGIA", ...
    titulo: str                     # texto do link do caderno, sem o "GABARITO n"
    cadernos: dict[int, str] = field(default_factory=dict)   # versão -> URL
    gabarito_preliminar: str | None = None
    gabarito_definitivo: str | None = None

    @property
    def gabarito(self) -> str | None:
        """URL do gabarito que vale: o definitivo, se houver; senão o preliminar."""
        return self.gabarito_definitivo or self.gabarito_preliminar


def _limpar(texto: str) -> str:
    texto = html.unescape(re.sub(r"<[^>]+>", " ", texto))
    return re.sub(r"\s+", " ", texto).strip()


def _chave(*textos: str) -> str:
    """Identifica a prova a que um link se refere.

    "PROVA A - ESCRITURARIO ..." -> "PROVA A"; provas sem letra usam o cargo
    (ex.: "TECNOLOGIA"). Recebe texto do link e nome do arquivo, porque alguns
    links dizem só "Gabaritos Alterados".
    """
    n = normalizar(" ".join(textos))
    letra = _RE_LETRA_PROVA.search(n)
    if letra:
        return f"PROVA {letra.group(1)}"
    if "TECNOLOGIA" in n:
        return "TECNOLOGIA"
    n = re.sub(r"\b(GABARITOS?|ALTERAD[OA]S?|PROVAS?|CADERNO|PDF|EM \d.*)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip() or "PROVA"


def interpretar_pagina(conteudo_html: str) -> tuple[str, list[ProvaCesgranrio]]:
    """Extrai (nome do concurso, provas) do HTML da página do concurso."""
    titulo = _RE_TITULO.search(conteudo_html)
    nome_concurso = _limpar(titulo.group(1)).split("|")[0].strip() if titulo else "Cesgranrio"

    provas: dict[str, ProvaCesgranrio] = {}
    for url, miolo in _RE_LINK.findall(conteudo_html):
        url = html.unescape(url).strip()
        texto = _limpar(miolo)
        arquivo = url.split("file=", 1)[-1]
        rotulo = normalizar(texto)
        if not re.search(r"\b(PROVA|GABARITO)", normalizar(texto + " " + arquivo)):
            continue  # edital, comunicado, resultado etc.

        versao = _RE_VERSAO_CADERNO.search(rotulo)
        chave = _chave(texto, Path(arquivo).name)
        prova = provas.setdefault(chave, ProvaCesgranrio(chave=chave, titulo=""))

        if versao:
            prova.cadernos[int(versao.group(1))] = url
            if not prova.titulo:
                prova.titulo = re.sub(r"\s*[–-]\s*GABARITO \d$", "", texto, flags=re.I).strip()
        elif "ALTERAD" in normalizar(texto + " " + arquivo):
            prova.gabarito_definitivo = url
        else:
            prova.gabarito_preliminar = url

    completas = [p for p in provas.values() if p.cadernos]
    for prova in completas:
        prova.titulo = prova.titulo or prova.chave
    return nome_concurso, sorted(completas, key=lambda p: p.chave)


def listar_provas(slug: str) -> tuple[str, list[ProvaCesgranrio]]:
    """Busca a página do concurso e devolve (nome, provas)."""
    resposta = SESSION.get(_PAGINA.format(slug=slug), timeout=40)
    resposta.raise_for_status()
    return interpretar_pagina(resposta.text)


def buscar_documentos(slug: str) -> tuple[str, list[Documento]]:
    """Mesma interface dos outros adaptadores: um caderno e um gabarito por prova."""
    nome, provas = listar_provas(slug)
    documentos: list[Documento] = []
    for prova in provas:
        versao = min(prova.cadernos)
        documentos.append(Documento(titulo=f"PROVA {prova.titulo}", url=prova.cadernos[versao], tipo="prova"))
        if prova.gabarito:
            definitivo = " DEFINITIVO" if prova.gabarito_definitivo else ""
            documentos.append(
                Documento(titulo=f"GABARITO{definitivo} {prova.titulo}", url=prova.gabarito, tipo="gabarito")
            )
    return nome, documentos


def _baixar_conferindo(url: str, destino: Path) -> Path:
    caminho = baixar_pdf(url, destino)
    if not caminho.read_bytes()[:5].startswith(b"%PDF"):
        caminho.unlink()
        raise RuntimeError(f"O servidor não devolveu um PDF para {url}")
    return caminho


def baixar_concurso(slug: str, pasta: Path, versao: int = 1, conferencia: int | None = None) -> list[dict]:
    """Baixa, para cada prova, um caderno e os gabaritos. Grava um manifesto.

    Só baixa a versão pedida do caderno (as outras têm as mesmas questões em
    outra ordem). Com `conferencia`, baixa também essa segunda versão: o
    importador a usa para conferir, questão a questão, que o texto e a
    resposta batem nas duas. Arquivo que já existe não é baixado de novo.
    """
    nome_concurso, provas = listar_provas(slug)
    pasta.mkdir(parents=True, exist_ok=True)
    manifesto = []
    for prova in provas:
        base = normalizar(prova.chave).replace(" ", "_")
        versao_usada = versao if versao in prova.cadernos else min(prova.cadernos)
        item = {
            "banca": "Cesgranrio",
            "concurso": nome_concurso,
            "slug": slug,
            "chave": prova.chave,
            "titulo": prova.titulo,
            "versao_caderno": versao_usada,
            "caderno": None,
            "versao_conferencia": None,
            "caderno_conferencia": None,
            "gabarito_preliminar": None,
            "gabarito_definitivo": None,
            "urls": asdict(prova),
        }
        item["caderno"] = str(_baixar_conferindo(
            prova.cadernos[versao_usada], pasta / f"{base}_caderno{versao_usada}.pdf"))
        if conferencia and conferencia != versao_usada and conferencia in prova.cadernos:
            item["versao_conferencia"] = conferencia
            item["caderno_conferencia"] = str(_baixar_conferindo(
                prova.cadernos[conferencia], pasta / f"{base}_caderno{conferencia}.pdf"))
        if prova.gabarito_preliminar:
            item["gabarito_preliminar"] = str(_baixar_conferindo(
                prova.gabarito_preliminar, pasta / f"{base}_gabarito_preliminar.pdf"))
        if prova.gabarito_definitivo:
            item["gabarito_definitivo"] = str(_baixar_conferindo(
                prova.gabarito_definitivo, pasta / f"{base}_gabarito_definitivo.pdf"))
        manifesto.append(item)

    (pasta / "manifesto_cesgranrio.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifesto
