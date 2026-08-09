"""Adaptador para o Cebraspe (cebraspe.org.br), via API publica do site.

A pagina de cada concurso (ex.: https://www.cebraspe.org.br/concursos/PRF_21)
e uma SPA que busca os dados em:
  https://apis.cebraspe.org.br/cebraspe/eventos/{slug}
e a lista de todos os concursos em:
  https://apis.cebraspe.org.br/cebraspe/eventos/tipo/concursos/

Essas rotas sao as mesmas que o site usa para montar a pagina publica --
nao e um acesso a nada privado, so evitamos ter que renderizar JavaScript.
"""
from __future__ import annotations

from .base import SESSION, Documento, classificar

_API_EVENTO = "https://apis.cebraspe.org.br/cebraspe/eventos/{slug}"
_API_LISTA = "https://apis.cebraspe.org.br/cebraspe/eventos/tipo/concursos/"
_CDN_ARQUIVOS = "https://cdn.cebraspe.org.br/concursos/{slug}/arquivos/{arquivo}"


def listar_concursos() -> list[dict]:
    """Lista todos os concursos do Cebraspe (novos, abertos, em andamento, encerrados)."""
    resposta = SESSION.get(_API_LISTA, timeout=30)
    resposta.raise_for_status()
    concursos = []
    for fase in resposta.json():
        for evento in fase.get("eventos") or []:
            concursos.append(
                {
                    "nome": evento.get("eventoNomeAbreviado") or evento.get("eventoURL"),
                    "slug": evento.get("eventoURL"),
                    "status": evento.get("eventoStatus") or fase.get("faseEvento"),
                    "ano": evento.get("eventoAno"),
                }
            )
    return concursos


def buscar_slug_por_nome(termo: str) -> list[dict]:
    """Procura concursos cujo nome ou slug contenha `termo` (sem acento, case-insensitive)."""
    termo_norm = termo.strip().lower()
    return [
        c
        for c in listar_concursos()
        if termo_norm in (c["nome"] or "").lower() or termo_norm in (c["slug"] or "").lower()
    ]


def buscar_documentos(slug: str) -> tuple[str, list[Documento]]:
    """Retorna (nome do concurso, lista de provas/gabaritos) para um slug do Cebraspe.

    O slug e o identificador usado na URL do concurso (ex.: 'PRF_21', 'PF_25').
    Use `buscar_slug_por_nome` se voce nao souber o slug exato.
    """
    resposta = SESSION.get(_API_EVENTO.format(slug=slug), timeout=30)
    resposta.raise_for_status()
    dados = resposta.json()
    nome_concurso = dados.get("eventoNomeCompleto") or dados.get("eventoNomeAbreviado") or slug

    documentos: list[Documento] = []
    for item in dados.get("arquivosGabarito") or []:
        titulo = (item.get("descricaoArquivo") or "").strip()
        arquivo = item.get("nomeArquivo")
        if not arquivo or not titulo:
            continue
        tipo = classificar(titulo)
        if not tipo:
            continue  # documento nessa secao que nao e prova nem gabarito
        url = _CDN_ARQUIVOS.format(slug=slug, arquivo=arquivo)
        documentos.append(Documento(titulo=titulo, url=url, tipo=tipo))
    return nome_concurso, documentos
