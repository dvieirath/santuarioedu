"""Infraestrutura comum: download de PDFs, mesclagem e pareamento prova/gabarito.

Este modulo nao depende de nenhuma banca especifica. Cada banca tem seu
proprio adaptador (ex: bancas/cebraspe.py) que sabe onde encontrar os
documentos e devolve uma lista de `Documento` para ca.
"""
from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import requests
from pypdf import PdfReader, PdfWriter

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 "
    "SantuarioEdu-BaixadorDeProvas/1.0 (uso pessoal, provas e gabaritos publicos)"
)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


@dataclass
class Documento:
    """Um PDF encontrado na pagina do concurso."""

    titulo: str  # texto/descricao do link, ex: "PROVA OBJETIVA - ITENS DE 9 A 120"
    url: str  # link direto para o PDF
    tipo: str  # "prova" ou "gabarito"


# ---------------------------------------------------------------------------
# Classificacao e pareamento (prova <-> gabarito) a partir do titulo do link
# ---------------------------------------------------------------------------

_PALAVRAS_GABARITO = ["GABARITO", "PADRAO DE RESPOSTA", "RESPOSTA OFICIAL", "RESPOSTAS OFICIAIS"]
_PALAVRAS_PROVA = ["PROVA", "CADERNO DE QUESTOES", "CADERNO DE PROVA"]

# Palavras "de ruido" removidas na hora de comparar titulos de prova x gabarito,
# para sobrar so a parte que realmente identifica qual prova/turno/cargo e.
_RUIDO = [
    "GABARITO", "PROVA", "OBJETIVA", "DISCURSIVA", "DEFINITIVO", "PRELIMINAR",
    "OFICIAL", "OFICIAIS", "PADRAO", "RESPOSTA", "RESPOSTAS", "CADERNO",
    "QUESTOES", "DE",
]

# Titulos que COMECAM com uma dessas palavras nunca sao a prova/gabarito em
# si, mesmo que mencionem "prova" ou "gabarito" no meio do texto -- sao
# comunicados, resultados de recurso, editais etc. que falam SOBRE a prova.
# Ex.: "Resultado Definitivo da Prova Discursiva" (nota dos candidatos, nao
# o PDF da prova) ou "Comunicado - Prova Objetiva Final ..." (aviso).
_PREFIXOS_IGNORADOS = [
    "COMUNICADO", "RESULTADO", "EDITAL", "RELACAO", "ESPELHO", "HOMOLOGACAO",
    "ORIENTACAO", "CRONOGRAMA", "CONVOCACAO", "RETIFICACAO", "JUSTIFICATIVA",
    "JUSTIFICATIVAS",
]


def normalizar(texto: str) -> str:
    """Maiusculas, sem acento, so letras/numeros/espaco."""
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    texto = texto.upper()
    texto = re.sub(r"[^A-Z0-9 ]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def classificar(titulo: str) -> str | None:
    """Decide se um titulo de link e 'prova', 'gabarito' ou nenhum dos dois.

    Usa fronteira de palavra (\\b) e nao "contem a substring", senao titulos
    como "Resultado Final de Aprovados" seriam classificados como prova so
    porque "PROVA" aparece dentro de "APROVADOS".
    """
    n = normalizar(titulo)
    if any(n.startswith(prefixo) for prefixo in _PREFIXOS_IGNORADOS):
        return None
    for palavra in _PALAVRAS_GABARITO:
        if re.search(rf"\b{re.escape(palavra)}\b", n):
            return "gabarito"
    for palavra in _PALAVRAS_PROVA:
        if re.search(rf"\b{re.escape(palavra)}\b", n):
            return "prova"
    return None


def _chave_pareamento(titulo: str) -> str:
    n = normalizar(titulo)
    for palavra in _RUIDO:
        n = re.sub(rf"\b{re.escape(palavra)}\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


def parear(documentos: list[Documento], limiar: float = 0.5) -> list[tuple[Documento, Documento | None]]:
    """Para cada prova, acha o gabarito mais parecido (por similaridade de texto).

    Prefere gabarito "definitivo" a "preliminar" em caso de empate tecnico.
    Um gabarito so e usado uma vez. Provas sem par voltam com gabarito=None.
    """
    provas = [d for d in documentos if d.tipo == "prova"]
    gabaritos = [d for d in documentos if d.tipo == "gabarito"]
    usados: set[str] = set()
    pares: list[tuple[Documento, Documento | None]] = []

    for prova in provas:
        chave_prova = _chave_pareamento(prova.titulo)
        melhor: Documento | None = None
        melhor_score = 0.0
        for gabarito in gabaritos:
            if gabarito.url in usados:
                continue
            score = SequenceMatcher(None, chave_prova, _chave_pareamento(gabarito.titulo)).ratio()
            if "DEFINITIVO" in normalizar(gabarito.titulo):
                score += 0.02
            if score > melhor_score:
                melhor, melhor_score = gabarito, score
        if melhor is not None and melhor_score >= limiar:
            usados.add(melhor.url)
            pares.append((prova, melhor))
        else:
            pares.append((prova, None))

    return pares


# ---------------------------------------------------------------------------
# Download e mesclagem de PDFs
# ---------------------------------------------------------------------------

def baixar_pdf(url: str, destino: Path, pausa: float = 1.0) -> Path:
    """Baixa um PDF, pulando se o arquivo ja existir (idempotente)."""
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    resposta = SESSION.get(url, timeout=60)
    resposta.raise_for_status()
    destino.write_bytes(resposta.content)
    time.sleep(pausa)
    return destino


def mesclar_pdfs(caminhos: list[Path], saida: Path) -> Path:
    """Junta paginas de varios PDFs (na ordem dada) em um unico arquivo."""
    writer = PdfWriter()
    for caminho in caminhos:
        try:
            leitor = PdfReader(str(caminho))
            for pagina in leitor.pages:
                writer.add_page(pagina)
        except Exception as exc:  # PDF corrompido, protegido, etc.
            raise RuntimeError(f"Falha ao ler '{caminho.name}': {exc}") from exc
    saida.parent.mkdir(parents=True, exist_ok=True)
    with open(saida, "wb") as arquivo:
        writer.write(arquivo)
    return saida


def nome_arquivo_seguro(*partes: str, limite: int = 150) -> str:
    """Vira um nome de arquivo valido no Windows a partir de textos livres.

    Se o nome tiver que ser cortado (titulos longos, ex. FGV que as vezes
    junta cargo + turno + tipo de caderno no titulo), acrescenta um sufixo
    curto derivado do texto original inteiro, para dois documentos diferentes
    que só se distinguem no final do titulo nao acabarem colidindo no mesmo
    nome de arquivo (e um "sumindo" por parecer que ja foi baixado).
    """
    texto_original = " ".join(p for p in partes if p)
    texto = unicodedata.normalize("NFKD", texto_original).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^A-Za-z0-9]+", "_", texto).strip("_")
    texto = re.sub(r"_+", "_", texto)
    if not texto:
        return "documento"
    if len(texto) <= limite:
        return texto
    sufixo = hashlib.sha1(texto_original.encode("utf-8")).hexdigest()[:8]
    return f"{texto[: limite - len(sufixo) - 1]}_{sufixo}"
