"""
Leitura de cadernos de prova e gabaritos da Fundação Cesgranrio.

Não usa IA: o caderno é lido com a posição de cada trecho na página, o que
permite ordenar as duas colunas, reconstruir parágrafos, tirar a hifenização
de fim de linha e saber em que questão cai cada figura. O gabarito oficial dá,
para cada número de questão, a disciplina e a letra correta.

Fluxo:
    paginas  = extrair_paginas('caderno.pdf')
    gabarito = ler_gabarito(texto_do_pdf('gabarito.pdf'))[1]   # versão do caderno
    questoes = montar_questoes(paginas, gabarito)

Cada questão sai com:
    problemas  motivos para NÃO importar (anulada, figura na área da questão,
               alternativas incompletas, texto solto). Lista vazia = pronta.
    avisos     pontos para conferir depois de importar (código ou tabela com
               quebras de linha preservadas, texto de apoio de faixa).

A posição das linhas é calculada aqui, a partir dos operadores de texto do PDF
(Tm, Td, TD, T*). A posição que o pypdf informa serve para os cadernos de 2023,
em que cada linha tem posição absoluta, mas sai errada nos de 2021, que usam
deslocamento relativo entre linhas.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Faixas da página (pontos; origem embaixo, à esquerda) que são cabeçalho e
# rodapé nos cadernos da Cesgranrio.
_Y_RODAPE = 60.0
_Y_CABECALHO = 775.0
_TOLERANCIA_LINHA = 2.5        # trechos com y até esta distância são a mesma linha
_RECUO_MINIMO = 5.0            # deslocamento em x que indica recuo de parágrafo
_FOLGA_PARAGRAFO = 2.5         # espaço extra entre linhas que indica novo bloco
_FOLGA_ALTERNATIVA = 1.6       # idem, para saber onde termina a alternativa (E)
_ALTURA_MINIMA_FIGURA = 20.0   # ignora traços e enfeites
_LINHA_CHEIA = 0.75            # fração da linha mais longa que conta como "cheia"
_PONTOS_POR_ESPACO = 3.5       # recuo em pontos equivalente a um espaço (código)

_RE_ALTERNATIVA = re.compile(r"^\(([A-E])\)\s*(.*)$", re.S)
_RE_SO_DIGITOS = re.compile(r"^\d{1,3}$")
_RE_RESPOSTA = re.compile(r"(\d{1,3})\s*-\s*(Anulada|[A-E])\b", re.I)
_RE_VERSAO = re.compile(r"^\s*GABARITO\s+(\d)\s*$", re.I)
_RE_MARCADOR_LISTA = re.compile(r"^(\d{1,4}\)|[a-z]\)|[IVX]{1,5}\s*[-–.)]|[-–—•]\s)")
_RE_FAIXA_QUESTOES = re.compile(
    r"quest(?:ão|ões|ao|oes|ions?)\s*(?:de\s*)?(?:n[oº°]s?\.?\s*)?(\d{1,3})\s*(?:a|e|to|and|-|–)\s*(\d{1,3})",
    re.I,
)
_RE_PALAVRA = re.compile(r"[A-Za-zÀ-ÿ]+(?:-[A-Za-zÀ-ÿ]+)*")
_RE_FIM_PALAVRA = re.compile(r"([A-Za-zÀ-ÿ]+)-$")
_RE_INICIO_PALAVRA = re.compile(r"^([A-Za-zÀ-ÿ]+)")

_RE_DESTAQUE = re.compile(
    r"destac|sublinhad|negrit|grifad|\bbold\b|boldfaced|highlighted|underlined", re.I)
# Cita figura, gráfico ou tabela como material da questão. A Cesgranrio escreve
# o nome com maiúscula ("a Tabela a seguir", "na Figura"). Desenho vetorial e
# tabela não vêm como imagem, então o texto é a única pista.
_RE_EXIBICAO = re.compile(
    r"\b(?:[AaOo]s?|[Nn][ao]s?|[Dd][ao]s?|[Uu]ma?|[Pp]el[ao]s?|[Àà]s?|"
    r"[DdNn]?[Ee]ss[ae]s?|[DdNn]?[Ee]st[ae]s?)\s+"
    r"(?:Figura|Gráfico|Diagrama|Imagem|Ilustração|Esquema|Tabela|Quadro)s?\b"
    r"|\b(?:figura|gr[aá]fico|diagrama|ilustra[cç][aã]o|esquema)s?\s+(?:a seguir|abaixo|acima|ao lado)\b"
)
# Sobrescritos que são ordinais: entram logo depois do número a que pertencem.
_ORDINAIS = {"o": "º", "a": "ª", "os": "ºs", "as": "ªs",
             "th": "th", "st": "st", "nd": "nd", "rd": "rd"}
_TOLERANCIA_ORDINAL = 14.0     # distância máxima (pontos) entre o ordinal e o número

_TITULOS_DE_BLOCO = {"CONHECIMENTOSBASICOS", "CONHECIMENTOSESPECIFICOS"}
_LIXO = {"RASCUNHO"}
# Pronomes que vêm depois de hífen verdadeiro ("tornou-se"). Só é usado quando
# não há vocabulário para decidir.
_CLITICOS = {"se", "me", "te", "lhe", "lhes", "lo", "la", "los", "las", "nos", "vos"}


def normalizar(texto):
    """Maiúsculas, sem acento, só letras, números e espaço simples."""
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    texto = re.sub(r"[^A-Za-z0-9 ]", " ", texto.upper())
    return re.sub(r"\s+", " ", texto).strip()


def _compacto(texto):
    """Normalizado e sem espaços: títulos com espaçamento entre letras
    ("LÍNGU A INGLESA") comparam igual."""
    return normalizar(texto).replace(" ", "")


def vocabulario_de(textos):
    """Conjunto de palavras (minúsculas) para decidir hífen de fim de linha."""
    palavras = set()
    for texto in textos:
        palavras.update(p.lower() for p in _RE_PALAVRA.findall(texto or ""))
    return palavras


# ── Modelo ──────────────────────────────────────────────────────────────────

@dataclass
class Linha:
    texto: str
    x: float
    y: float
    pagina: int = 1
    coluna: int = 0
    hifen_mole: bool = False     # termina em hífen de translineação (trecho separado)
    marcador: str = ""           # número de parágrafo impresso na margem
    pendencia_formula: bool = False   # sobrescrito/subscrito que não deu para encaixar
    negrito_total: bool = False       # a linha inteira está em negrito


@dataclass
class Figura:
    pagina: int
    coluna: int
    y_base: float
    y_topo: float


@dataclass
class Pagina:
    numero: int
    linhas: list = field(default_factory=list)     # já ordenadas: coluna 0, depois 1
    figuras: list = field(default_factory=list)
    hifen_separado: bool = False                   # viu hífen de translineação à parte


@dataclass
class QuestaoExtraida:
    numero: int
    disciplina: str = ""                 # cabeçalho do gabarito, normalizado
    enunciado: str = ""
    alternativas: list = field(default_factory=list)   # [(letra, texto)]
    correta: str | None = None           # letra, ou None se anulada
    texto_apoio: str = ""
    pagina: int = 0
    problemas: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    texto_solto: str = ""                # o que sobrou antes do número da questão

    @property
    def texto_completo(self):
        """Enunciado como vai para o banco: texto de apoio (se houver) e pergunta."""
        if self.texto_apoio:
            return f"{self.texto_apoio}\n\n{self.enunciado}"
        return self.enunciado


class _Juncao:
    """Como desfazer a quebra de fim de linha neste documento."""

    def __init__(self, hifen_separado=True, vocabulario=None):
        # Com hífen de translineação em trecho separado (cadernos de 2023), um
        # hífen dentro do texto no fim da linha é da própria palavra.
        self.hifen_separado = hifen_separado
        self.vocabulario = vocabulario or set()

    def hifen_e_da_palavra(self, antes, depois):
        """`antes` termina em "-"; decide se o hífen fica ("tornou-se") ou sai ("pa-rágrafo")."""
        if self.hifen_separado:
            return True
        a = _RE_FIM_PALAVRA.search(antes)
        d = _RE_INICIO_PALAVRA.match(depois)
        if not a or not d:
            return True          # "-" depois de número ou símbolo: não é translineação
        junto = (a.group(1) + d.group(1)).lower()
        com_hifen = f"{a.group(1)}-{d.group(1)}".lower()
        if junto in self.vocabulario:
            return False
        if com_hifen in self.vocabulario:
            return True
        return d.group(1).lower() in _CLITICOS and not a.group(1).lower().endswith("s")


# ── Página: de trechos posicionados para linhas ordenadas ───────────────────

def _coluna(x, meio):
    return 0 if x < meio else 1


def _largura_estimada(texto, tamanho):
    """Largura aproximada de `texto` em pontos (métrica da Arial, por classe de letra)."""
    total = 0.0
    for ch in texto:
        if ch == "*":
            continue
        if ch == " ":
            total += 0.278
        elif ch.isdigit():
            total += 0.556
        elif ch in "ijl":
            total += 0.222
        elif ch in "ftI":
            total += 0.278
        elif ch == "r":
            total += 0.333
        elif ch in "mM":
            total += 0.833
        elif ch in "wW":
            total += 0.80
        elif ch.isupper():
            total += 0.68
        elif ch.islower():
            total += 0.52
        elif ch in ",.;:!|'":
            total += 0.278
        elif ch in "-()[]\"“”":
            total += 0.333
        else:
            total += 0.556
    return total * tamanho


def _texto_item(item):
    return "".join(t for t, _ in item["pecas"]).strip()


def _curto(grupo):
    return len(grupo["itens"]) <= 3 and all(len(_texto_item(i)) <= 3 for i in grupo["itens"])


def _colado(anterior, parte):
    """O trecho `parte` começa encostado no fim de `anterior`? (número ou sigla
    desenhados em pedaços: "2" + "022)", "A" + "TUALIDADES")"""
    texto = _texto_item(anterior)
    if len(texto) > 4:
        return False
    fim_estimado = anterior["x"] + _largura_estimada(texto, anterior["tam"])
    return parte["x"] - fim_estimado <= 0.18 * anterior["tam"]


def _posicao_apos_numero(texto, inicios, x):
    """Índice em `texto` logo depois do número (ou do "n" de "nº") mais próximo de x."""
    melhor = None
    for achado in re.finditer(r"\d+|\b[nN]\b", texto):
        indice = achado.end()
        partida = max((p for p in inicios if p[0] <= indice), key=lambda p: p[0], default=None)
        if partida is None:
            continue
        estimado = partida[1] + _largura_estimada(texto[partida[0]:indice], partida[2])
        distancia = abs(estimado - x)
        if distancia <= _TOLERANCIA_ORDINAL and (melhor is None or distancia < melhor[0]):
            melhor = (distancia, indice)
    return melhor[1] if melhor else None


def montar_linhas(trechos, numero_pagina=1, largura=595.3):
    """Transforma os trechos de uma página em linhas ordenadas.

    Cada trecho é (x, y, texto), (x, y, texto, negrito, tamanho) ou, ainda,
    (x, y, texto, negrito, tamanho, formula, colar): `formula` avisa que o
    trecho tem expoente ou índice não resolvido; `colar`, que ele começa com
    um ordinal que pertence ao número no fim do trecho anterior.

    - trecho com posição None continua o trecho anterior;
    - hífen isolado no fim da linha (posicionado na margem direita) é
      translineação;
    - número isolado à esquerda do texto, na mesma altura de uma linha, é
      marcador de parágrafo;
    - negrito no meio de uma linha de texto normal é destaque: vira **assim**;
    - trecho curto um pouco acima ou abaixo de uma linha é sobrescrito ou
      subscrito. Ordinal ("1" + "o") é encaixado depois do número; o resto
      (expoente, índice) marca a linha com `pendencia_formula`;
    - cabeçalho e rodapé são descartados.
    Devolve (linhas, viu_hifen_separado).
    """
    meio = largura / 2
    itens = []
    for trecho in trechos:
        x, y, texto = trecho[0], trecho[1], trecho[2]
        negrito = bool(trecho[3]) if len(trecho) > 3 else False
        tamanho = float(trecho[4]) if len(trecho) > 4 and trecho[4] else 10.0
        formula = bool(trecho[5]) if len(trecho) > 5 else False
        colar = bool(trecho[6]) if len(trecho) > 6 else False
        texto = texto.replace("\n", " ")
        if not texto.strip():
            continue
        if x is None:
            if itens:
                itens[-1]["pecas"].append((texto, negrito))
                itens[-1]["formula"] = itens[-1]["formula"] or formula
            continue
        itens.append({"x": x, "y": y, "pecas": [(texto, negrito)], "tam": tamanho,
                      "formula": formula, "colar": colar})

    itens = [i for i in itens if _Y_RODAPE <= i["y"] <= _Y_CABECALHO]

    grupos = []
    for item in sorted(itens, key=lambda i: (_coluna(i["x"], meio), -i["y"], i["x"])):
        col = _coluna(item["x"], meio)
        if grupos and grupos[-1]["col"] == col and abs(grupos[-1]["y"] - item["y"]) <= _TOLERANCIA_LINHA:
            grupos[-1]["itens"].append(item)
        else:
            grupos.append({"col": col, "y": item["y"], "itens": [item], "extras": []})

    # sobrescritos e subscritos: grupo curto logo acima/abaixo de uma linha de texto
    restantes = []
    for grupo in grupos:
        alvo = None
        tipo = ""
        if _curto(grupo):
            x_grupo = min(i["x"] for i in grupo["itens"])
            for outro in grupos:
                if outro is grupo or outro["col"] != grupo["col"] or _curto(outro):
                    continue
                desnivel = grupo["y"] - outro["y"]
                dentro = x_grupo > min(i["x"] for i in outro["itens"]) + 3
                if dentro and (2.0 < desnivel <= 7.5 or -5.5 <= desnivel < -2.0):
                    alvo, tipo = outro, ("sobre" if desnivel > 0 else "sub")
                    break
        if alvo is None:
            restantes.append(grupo)
        else:
            alvo["extras"].extend((i["x"], _texto_item(i), tipo) for i in grupo["itens"])
    grupos = restantes

    linhas = []
    viu_hifen_separado = False
    for grupo in grupos:
        partes = sorted(grupo["itens"], key=lambda i: i["x"])
        hifen = False
        marcador = ""
        if len(partes) > 1 and _texto_item(partes[-1]) == "-":
            hifen = viu_hifen_separado = True
            partes = partes[:-1]
        so_digitos = all(_RE_SO_DIGITOS.match(_texto_item(p)) for p in partes)
        if not so_digitos:
            # números soltos à esquerda do texto (às vezes impressos duas vezes)
            n_margem = 0
            while n_margem < len(partes) and _RE_SO_DIGITOS.match(_texto_item(partes[n_margem])):
                n_margem += 1
            if 0 < n_margem < len(partes) \
                    and partes[n_margem]["x"] - partes[n_margem - 1]["x"] > 12:
                marcador = _texto_item(partes[0])
                partes = partes[n_margem:]

        inicios = []        # (índice no texto, x, tamanho) de cada parte
        negrito_total = False
        if so_digitos:
            # número de questão desenhado algarismo por algarismo: "5" "8" -> "58"
            texto = "".join(_texto_item(p) for p in partes)
        else:
            planas = [(t, n) for p in partes for t, n in p["pecas"]]
            tem_negrito = any(n and re.search(r"\w", t) for t, n in planas)
            misto = tem_negrito and any(not n and re.search(r"\w", t) for t, n in planas)
            negrito_total = tem_negrito and not misto
            texto = ""
            anterior = None
            for parte in partes:
                pedaco = ""
                for t, negrito in parte["pecas"]:
                    if misto and negrito and t.strip():
                        a, b = len(t) - len(t.lstrip()), len(t.rstrip())
                        t = t[:a] + "**" + t[a:b] + "**" + t[b:]
                    pedaco += t
                if parte["colar"] and re.search(r"[\dnN]\s*$", texto):
                    texto = texto.rstrip()            # ordinal: "20" + "th century"
                elif parte["colar"]:
                    parte["formula"] = True
                elif texto and not texto.endswith(" ") and not pedaco.startswith(" ") \
                        and not _colado(anterior, parte):
                    texto += " "
                inicios.append((len(texto), parte["x"], parte["tam"]))
                texto += pedaco
                anterior = parte

        pendencia = any(p["formula"] for p in partes)
        for x_extra, t_extra, tipo in sorted(grupo["extras"], key=lambda e: -e[0]):
            ordinal = _ORDINAIS.get(t_extra.lower()) if tipo == "sobre" else None
            indice = _posicao_apos_numero(texto, inicios, x_extra) if ordinal else None
            if indice is None:
                pendencia = True
            else:
                texto = texto[:indice] + ordinal + texto[indice:]

        texto = re.sub(r"\*\*(\s*)\*\*", r"\1", texto)            # negritos vizinhos
        texto = re.sub(r"^\*\*(\([A-E]\))\*\*", r"\1", texto.strip())   # rótulo da alternativa
        texto = re.sub(r"[ \t]+", " ", texto).strip()
        if not texto:
            continue
        linhas.append(Linha(texto=texto, x=partes[0]["x"], y=grupo["y"], pagina=numero_pagina,
                            coluna=grupo["col"], hifen_mole=hifen, marcador=marcador,
                            pendencia_formula=pendencia, negrito_total=negrito_total))

    # marcador que ficou sozinho numa linha: prende à linha de texto ao lado
    for solto in [l for l in linhas if _RE_SO_DIGITOS.match(l.texto)]:
        vizinhas = [l for l in linhas if l is not solto and l.coluna == solto.coluna
                    and abs(l.y - solto.y) <= 4.0 and l.x - solto.x > 12
                    and not _RE_SO_DIGITOS.match(l.texto)]
        if vizinhas:
            alvo = min(vizinhas, key=lambda l: abs(l.y - solto.y))
            if not alvo.marcador:
                alvo.marcador = solto.texto
            linhas.remove(solto)
    return linhas, viu_hifen_separado


class _Rastreador:
    """Acompanha a posição do texto pelos operadores do PDF.

    Guarda só a matriz de linha (onde a linha de texto começa), que é o que
    interessa para ordenar e agrupar. O avanço dos caracteres dentro da linha
    não é calculado.
    """

    def __init__(self):
        self.matriz = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        self.entrelinha = 0.0
        self.corpo = 1.0            # tamanho dado no operador Tf
        self.pendente = None        # (x, y, tamanho) do primeiro texto desde o último trecho
        self.pedacos = []           # (texto, tamanho, x, y) de cada operador de texto do trecho

    def _mover(self, tx, ty):
        a, b, c, d, e, f = self.matriz
        self.matriz = [a, b, c, d, tx * a + ty * c + e, tx * b + ty * d + f]

    def operador(self, nome, argumentos, cm):
        try:
            if nome == "BT":
                self.matriz = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
            elif nome == "Tm":
                self.matriz = [float(v) for v in argumentos[:6]]
            elif nome == "Td":
                self._mover(float(argumentos[0]), float(argumentos[1]))
            elif nome == "TD":
                self.entrelinha = -float(argumentos[1])
                self._mover(float(argumentos[0]), float(argumentos[1]))
            elif nome == "TL":
                self.entrelinha = float(argumentos[0])
            elif nome == "Tf":
                self.corpo = float(argumentos[1])
            elif nome == "T*":
                self._mover(0.0, -self.entrelinha)
            if nome in ("'", '"'):
                self._mover(0.0, -self.entrelinha)
            if nome in ("Tj", "TJ", "'", '"'):
                e, f = self.matriz[4], self.matriz[5]
                x = e * cm[0] + f * cm[2] + cm[4]
                y = e * cm[1] + f * cm[3] + cm[5]
                tamanho = abs(self.matriz[0] * self.corpo) or 10.0
                if self.pendente is None:
                    self.pendente = (x, y, tamanho)
                operando = argumentos[2] if nome == '"' else argumentos[0]
                self.pedacos.append((_texto_do_operando(operando), tamanho, x, y))
        except (TypeError, ValueError, IndexError):
            pass

    def posicao_do_trecho(self):
        """Devolve (posição, pedaços) do trecho que acabou e zera para o próximo."""
        posicao, self.pendente = self.pendente, None
        pedacos, self.pedacos = self.pedacos, []
        return posicao, pedacos


def _texto_do_operando(operando):
    """Texto aproximado de um operando de Tj/TJ (fontes de um byte por letra).

    Serve só para localizar, dentro do trecho já decodificado pelo pypdf, onde
    fica um pedaço em expoente ou índice.
    """
    itens = operando if isinstance(operando, (list, tuple)) else [operando]
    partes = []
    for item in itens:
        bruto = getattr(item, "original_bytes", None)
        if bruto is None:
            if isinstance(item, (int, float)) or not isinstance(item, (str, bytes)):
                continue
            bruto = item if isinstance(item, bytes) else str(item).encode("latin-1", "ignore")
        partes.append(bruto.decode("cp1252", "ignore"))
    return "".join(partes)


def _desniveis(texto, pedacos):
    """Trata expoentes e índices que vieram dentro de um mesmo trecho.

    `pedacos`: (texto, tamanho, x, y) de cada operador do trecho, em ordem.
    Pedaço menor que o corpo do texto e deslocado na vertical é sobrescrito
    ou subscrito. Ordinal depois de número vira "º"/"ª" (ou "th"); qualquer
    outro caso é fórmula e fica pendente.

    Devolve (texto, formula_pendente, colar, y_base). `colar`: o trecho começa
    com ordinal que pertence ao número do trecho anterior. `y_base`: altura da
    linha de base, ou None se não mudou.
    """
    uteis = [p for p in pedacos if p[0].strip()]
    if len(uteis) < 2:
        return texto, False, False, None
    peso = {}
    for t, tamanho, _x, _y in uteis:
        peso[round(tamanho, 1)] = peso.get(round(tamanho, 1), 0) + len(t.strip())
    corpo = max(peso, key=peso.get)
    base = [p for p in uteis if round(p[1], 1) == corpo]

    def desnivel(pedaco):
        if pedaco[1] >= 0.85 * corpo:
            return 0.0
        referencia = min(base, key=lambda b: abs(b[2] - pedaco[2]))
        dy = pedaco[3] - referencia[3]
        return dy if 2.0 < abs(dy) <= 7.5 else 0.0

    if not any(desnivel(p) for p in uteis):
        return texto, False, False, None

    y_base = base[0][3] if desnivel(uteis[0]) else None
    saida = texto
    cursor = 0
    colar = False
    for indice, pedaco in enumerate(uteis):
        alvo = pedaco[0].strip()
        posicao = saida.find(alvo, cursor)
        if posicao < 0:
            return texto, True, False, y_base
        dy = desnivel(pedaco)
        if not dy:
            cursor = posicao + len(alvo)
            continue
        ordinal = _ORDINAIS.get(alvo.lower()) if dy > 0 else None
        antes = saida[:posicao].rstrip()
        if ordinal and antes and (antes[-1].isdigit() or antes[-1] in "nN"):
            saida = antes + ordinal + saida[posicao + len(alvo):]
            cursor = len(antes) + len(ordinal)
        elif ordinal and not antes and indice == 0:
            saida = ordinal + saida[posicao + len(alvo):]
            cursor = len(ordinal)
            colar = True
        else:
            return texto, True, False, y_base
    return saida, False, colar, y_base


def extrair_paginas(caminho_pdf):
    """Lê o PDF do caderno e devolve as páginas com linhas ordenadas e figuras."""
    from pypdf import PdfReader

    leitor = PdfReader(str(caminho_pdf))
    paginas = []
    for indice, page in enumerate(leitor.pages, 1):
        largura = float(page.mediabox.width)
        trechos = []
        desenhos = []
        rastreador = _Rastreador()

        def ao_ler_texto(texto, _cm, _tm, fonte, _tamanho):
            negrito = "Bold" in str((fonte or {}).get("/BaseFont", ""))
            posicao, pedacos = rastreador.posicao_do_trecho()
            texto, formula, colar, y_base = _desniveis(texto, pedacos)
            if posicao is None:
                trechos.append((None, None, texto, negrito, None, formula, False))
            else:
                y = posicao[1] if y_base is None else y_base
                trechos.append((posicao[0], y, texto, negrito, posicao[2], formula, colar))

        def antes_do_operador(operador, argumentos, cm, _tm):
            nome = operador.decode("latin-1") if isinstance(operador, bytes) else str(operador)
            rastreador.operador(nome, argumentos, cm)
            if nome == "Do" and argumentos:
                desenhos.append((str(argumentos[0]), [float(v) for v in cm]))

        page.extract_text(visitor_text=ao_ler_texto, visitor_operand_before=antes_do_operador)

        objetos = (page.get("/Resources") or {}).get("/XObject") or {}
        figuras = []
        for nome, cm in desenhos:
            ref = objetos.get(nome)
            objeto = ref.get_object() if ref is not None else None
            if objeto is None or str(objeto.get("/Subtype")) != "/Image":
                continue
            altura = abs(cm[3])
            if altura < _ALTURA_MINIMA_FIGURA:
                continue
            base = min(cm[5], cm[5] + cm[3])
            if not (_Y_RODAPE <= base <= _Y_CABECALHO):
                continue
            figuras.append(Figura(pagina=indice, coluna=_coluna(cm[4], largura / 2),
                                  y_base=base, y_topo=base + altura))
        linhas, hifen_separado = montar_linhas(trechos, indice, largura)
        paginas.append(Pagina(numero=indice, linhas=linhas, figuras=figuras,
                              hifen_separado=hifen_separado))
    return paginas


def texto_do_pdf(caminho_pdf):
    """Texto corrido de um PDF (usado para o gabarito)."""
    from pypdf import PdfReader

    leitor = PdfReader(str(caminho_pdf))
    return "\n".join((p.extract_text() or "") for p in leitor.pages)


# ── Gabarito ────────────────────────────────────────────────────────────────

def ler_gabarito(texto):
    """Lê o gabarito oficial.

    Devolve {versao: {numero: {'letra': 'A'..'E' ou None (anulada),
                               'disciplina': 'LINGUA PORTUGUESA'}}}.
    """
    versoes = {}
    atual = None
    disciplina = ""
    for bruta in texto.splitlines():
        linha = bruta.strip()
        if not linha:
            continue
        versao = _RE_VERSAO.match(linha)
        if versao:
            atual = versoes.setdefault(int(versao.group(1)), {})
            disciplina = ""
            continue
        if atual is None:
            continue
        respostas = _RE_RESPOSTA.findall(linha)
        if respostas:
            for numero, valor in respostas:
                letra = None if valor.lower() == "anulada" else valor.upper()
                atual[int(numero)] = {"letra": letra, "disciplina": disciplina}
            continue
        nome = normalizar(linha)
        if _compacto(linha) in _TITULOS_DE_BLOCO \
                or re.search(r"\b(EDITAL|SELECAO EXTERNA|BANCO DO BRASIL)\b", nome):
            continue
        disciplina = nome
    return versoes


# ── Texto: de linhas para parágrafos ────────────────────────────────────────

def _pedacos(linhas):
    """Texto de cada linha. Linha toda em negrito, dentro de um bloco com texto
    normal, é destaque e sai como **assim** (a pontuação final fica de fora)."""
    destacar = any(l.negrito_total for l in linhas) and not all(l.negrito_total for l in linhas)
    saida = []
    for linha in linhas:
        texto = linha.texto.strip()
        if destacar and linha.negrito_total and texto:
            partes = re.match(r"^(.*?)([\s.,;:!?”\")]*)$", texto, re.S)
            texto = f"**{partes.group(1)}**{partes.group(2)}" if partes.group(1) else texto
        saida.append(texto)
    return saida


def _acabamento(texto):
    """Une destaques vizinhos e tira o espaço antes de pontuação."""
    texto = re.sub(r"\*\*(\s*)\*\*", r"\1", texto)
    texto = re.sub(r"(?<=[\w”\"*)]) ([,.;:!?])(?=\s|$)", r"\1", texto)
    texto = re.sub(r"(?<=\w)- \*\*(?=\w)", "-**", texto)     # "Automatiza- **se**"
    return re.sub(r"[ \t]+", " ", texto).strip()


def _juntar(linhas, juncao):
    """Une linhas de texto corrido, desfazendo a quebra de fim de linha."""
    texto = ""
    anterior = None
    for linha, pedaco in zip(linhas, _pedacos(linhas)):
        if anterior is None:
            texto = pedaco
        elif anterior.hifen_mole:
            texto = texto.rstrip() + pedaco                  # translineação: sem hífen
        elif texto.endswith("-") and pedaco.startswith("-") and pedaco[1:2].isalpha():
            texto = texto + pedaco[1:]                       # hífen repetido na linha de baixo
        elif texto.endswith("-") and pedaco[:1].isalpha():
            if juncao.hifen_e_da_palavra(texto, pedaco):
                texto = texto + pedaco                       # hífen da própria palavra
            else:
                texto = texto[:-1] + pedaco
        else:
            texto = texto + " " + pedaco
        anterior = linha
    return _acabamento(texto)


def _tem_translineacao(linhas, juncao):
    for linha in linhas[:-1]:
        if linha.hifen_mole:
            return True
        if not juncao.hifen_separado and linha.texto.rstrip().endswith("-"):
            return True
    return False


def bloco_para_texto(linhas, juncao, largura_ref=0, primeira_e_rotulo=False):
    """Texto de um bloco de linhas. Devolve (texto, estruturado).

    Texto corrido é reunido em um parágrafo. Bloco estruturado (código, lista,
    tabela) mantém as quebras de linha e o recuo: é o caso quando alguma linha
    que não é a última fica bem mais curta que a largura da coluna, sem
    hifenização que indique texto corrido.
    """
    if len(linhas) <= 1:
        return _juntar(linhas, juncao), False
    limite = _LINHA_CHEIA * largura_ref
    curtas = [l for l in linhas[:-1] if len(l.texto) < limite]
    if not curtas or _tem_translineacao(linhas, juncao):
        return _juntar(linhas, juncao), False

    referencia = linhas[1:] if primeira_e_rotulo else linhas
    margem = min(l.x for l in referencia)
    saida = []
    for i, (linha, pedaco) in enumerate(zip(linhas, _pedacos(linhas))):
        recuo = 0 if (primeira_e_rotulo and i == 0) else max(0.0, linha.x - margem)
        saida.append(" " * int(round(recuo / _PONTOS_POR_ESPACO)) + pedaco)
    return "\n".join(saida), True


def _espacamento_normal(linhas):
    difs = sorted(
        a.y - b.y for a, b in zip(linhas, linhas[1:])
        if a.pagina == b.pagina and a.coluna == b.coluna and 0 < a.y - b.y < 40
    )
    return difs[len(difs) // 2] if difs else 12.5


def separar_blocos(linhas):
    """Agrupa linhas em blocos (parágrafos).

    Novo bloco quando: a linha traz marcador de parágrafo, começa recuada em
    relação à margem da coluna, vem depois de linha muito deslocada (título
    centralizado), há espaço maior que o normal antes dela, ou ela começa com
    marcador de lista.
    """
    if not linhas:
        return []
    normal = _espacamento_normal(linhas)
    margem = {}
    for linha in linhas:
        chave = (linha.pagina, linha.coluna)
        margem[chave] = min(margem.get(chave, linha.x), linha.x)

    blocos = [[linhas[0]]]
    for anterior, linha in zip(linhas, linhas[1:]):
        mesma_coluna = (anterior.pagina, anterior.coluna) == (linha.pagina, linha.coluna)
        recuo = linha.x - margem[(linha.pagina, linha.coluna)]
        recuo_anterior = anterior.x - margem[(anterior.pagina, anterior.coluna)]
        salto = (anterior.y - linha.y) if mesma_coluna else 0.0
        if linha.marcador:
            quebra = True
        elif recuo > _RECUO_MINIMO and abs(recuo - recuo_anterior) < 1.5:
            quebra = salto > normal + _FOLGA_PARAGRAFO      # bloco todo recuado
        elif recuo > _RECUO_MINIMO and recuo_anterior <= _RECUO_MINIMO:
            quebra = True
        elif salto > normal + _FOLGA_PARAGRAFO:
            quebra = True
        else:
            quebra = bool(_RE_MARCADOR_LISTA.match(linha.texto))
        if quebra:
            blocos.append([linha])
        else:
            blocos[-1].append(linha)
    return blocos


def paragrafos(linhas, juncao=None, numerar=False, largura_ref=0):
    """Texto dos blocos de `linhas`. Devolve (lista de textos, houve_estruturado).

    Com `numerar`, o marcador de parágrafo da margem vira o prefixo "[n] ".
    """
    juncao = juncao or _Juncao()
    textos = []
    estruturado = False
    for bloco in separar_blocos(linhas):
        texto, e = bloco_para_texto(bloco, juncao, largura_ref)
        if not texto:
            continue
        estruturado = estruturado or e
        if numerar and bloco[0].marcador:
            texto = f"[{bloco[0].marcador}] {texto}"
        textos.append(texto)
    return textos, estruturado


# ── Questões ────────────────────────────────────────────────────────────────

def _eh_lixo(texto):
    """Marca de página sem conteúdo: "RASCUNHO", às vezes repetido na linha."""
    compacto = _compacto(texto)
    return bool(compacto) and any(compacto == palavra * (len(compacto) // len(palavra))
                                  for palavra in _LIXO)


def _marcar_cabecalhos(linhas, disciplinas):
    """Índices das linhas que são título de disciplina ou de bloco.

    O título pode vir em duas ou três linhas ("ATUALIDADES" / "DO MERCADO
    FINANCEIRO") e com espaços entre letras.
    """
    alvos = {d.replace(" ", "") for d in disciplinas} | _TITULOS_DE_BLOCO
    marcados = set()
    for i in range(len(linhas)):
        if i in marcados:
            continue
        for tamanho in (1, 2, 3):
            grupo = linhas[i:i + tamanho]
            if len(grupo) < tamanho:
                break
            if "".join(_compacto(l.texto) for l in grupo) in alvos:
                marcados.update(range(i, i + tamanho))
                break
    return marcados


def montar_questoes(paginas, gabarito, vocabulario=None):
    """Monta as questões do caderno usando o gabarito da mesma versão.

    `gabarito`: {numero: {'letra', 'disciplina'}} (uma versão de `ler_gabarito`).
    `vocabulario`: palavras conhecidas, para decidir hífen de fim de linha nos
    cadernos em que a translineação não vem em trecho separado.
    """
    disciplinas = {dados["disciplina"] for dados in gabarito.values() if dados["disciplina"]}
    linhas = [l for p in paginas for l in p.linhas]
    figuras = [f for p in paginas for f in p.figuras]
    total = max(gabarito) if gabarito else 0
    cabecalhos = _marcar_cabecalhos(linhas, disciplinas)
    lixo = {i for i, l in enumerate(linhas) if _eh_lixo(l.texto)}

    palavras = set(vocabulario or ())
    palavras |= vocabulario_de(l.texto for l in linhas if not l.texto.rstrip().endswith("-"))
    juncao = _Juncao(hifen_separado=any(p.hifen_separado for p in paginas), vocabulario=palavras)

    # 1. localizar o início de cada questão, em ordem
    inicios = {}
    posicao = 0
    for numero in range(1, total + 1):
        for i in range(posicao, len(linhas)):
            if linhas[i].texto != str(numero) or linhas[i].marcador:
                continue
            tem_a = False
            for l in linhas[i + 1:i + 140]:
                if l.texto.startswith("(A)"):
                    tem_a = True
                    break
                if l.texto == str(numero + 1) and not l.marcador:
                    break
            if tem_a:
                inicios[numero] = i
                posicao = i + 1
                break

    questoes = {}
    vigente = {"texto": "", "disciplina": "", "ate": None, "formula": False}
    ordenados = sorted(inicios.items())
    fim_anterior = 0
    anterior = None
    for indice, (numero, inicio) in enumerate(ordenados):
        proximo = ordenados[indice + 1][1] if indice + 1 < len(ordenados) else len(linhas)
        dados = gabarito.get(numero, {"letra": None, "disciplina": ""})
        questao = QuestaoExtraida(numero=numero, disciplina=dados["disciplina"],
                                  correta=dados["letra"], pagina=linhas[inicio].pagina)

        # 2. o que há entre o fim da questão anterior e este número
        faixa = range(fim_anterior, inicio)
        ultimo_cabecalho = max((i for i in faixa if i in cabecalhos), default=None)
        if anterior is None and ultimo_cabecalho is None:
            antes = []          # capa e instruções antes da primeira disciplina
        else:
            comeco = fim_anterior if ultimo_cabecalho is None else ultimo_cabecalho + 1
            antes = [linhas[i] for i in range(comeco, inicio) if i not in cabecalhos and i not in lixo]
        formula_no_apoio = False
        if antes:
            textos, _ = paragrafos(antes, juncao, numerar=True)
            texto = "\n\n".join(textos)
            formula_no_apoio = any(l.pendencia_formula for l in antes)
            explicita = _RE_FAIXA_QUESTOES.search(texto[:400])
            if ultimo_cabecalho is not None:
                vigente = {"texto": texto, "disciplina": questao.disciplina, "ate": None,
                           "formula": formula_no_apoio}
            elif explicita:
                vigente = {"texto": texto, "disciplina": questao.disciplina,
                           "ate": int(explicita.group(2)), "formula": formula_no_apoio}
                questao.avisos.append("texto de apoio para uma faixa de questões")
            else:
                questao.problemas.append("texto solto antes da questão")
                questao.texto_solto = texto
                if anterior is not None:
                    anterior.problemas.append("texto solto depois das alternativas")
        if vigente["texto"] and vigente["disciplina"] == questao.disciplina \
                and (vigente["ate"] is None or numero <= vigente["ate"]):
            questao.texto_apoio = vigente["texto"]
            if vigente["formula"]:
                questao.problemas.append("sobrescrito ou subscrito não resolvido no texto de apoio")

        # 3. corpo: enunciado e alternativas
        corpo = [l for i, l in enumerate(linhas[inicio + 1:proximo], inicio + 1)
                 if i not in lixo]
        indices_corpo = [i for i in range(inicio + 1, proximo) if i not in lixo]
        marcas = []            # posição, no corpo, de (A), (B), ...
        procurar = 0
        for letra in "ABCDE":
            achado = next((k for k in range(procurar, len(corpo))
                           if corpo[k].texto.startswith(f"({letra})")), None)
            if achado is None:
                break
            marcas.append(achado)
            procurar = achado + 1
        if not marcas:
            questao.problemas.append("alternativas não encontradas")
            questoes[numero] = questao
            fim_anterior = proximo
            anterior = questao
            continue

        largura_ref = max((len(l.texto) for l in corpo), default=0)
        textos, estruturado = paragrafos(corpo[:marcas[0]], juncao, largura_ref=largura_ref)
        questao.enunciado = "\n\n".join(textos)

        # fim da última alternativa: até onde as linhas seguem coladas ou recuadas
        ultima = marcas[-1]
        fim = ultima + 1
        normal = _espacamento_normal(corpo[marcas[0]:]) if len(corpo) - marcas[0] > 1 else 12.5
        while fim < len(corpo):
            linha, previa = corpo[fim], corpo[fim - 1]
            if indices_corpo[fim] in cabecalhos:
                break
            mesma = (linha.pagina, linha.coluna) == (previa.pagina, previa.coluna)
            colada = mesma and 0 < previa.y - linha.y <= normal + _FOLGA_ALTERNATIVA
            recuada = mesma and linha.x - corpo[ultima].x > _RECUO_MINIMO
            if not (colada or recuada):
                break
            fim += 1

        limites = marcas + [fim]
        for k, comeco in enumerate(marcas):
            trecho = corpo[comeco:limites[k + 1]]
            letra = trecho[0].texto[1]
            primeira = Linha(**{**trecho[0].__dict__,
                                "texto": _RE_ALTERNATIVA.match(trecho[0].texto).group(2)})
            texto, e = bloco_para_texto([primeira] + trecho[1:], juncao, largura_ref,
                                        primeira_e_rotulo=True)
            estruturado = estruturado or e
            questao.alternativas.append((letra, texto))
        fim_anterior = indices_corpo[fim - 1] + 1

        # 4. conferências
        letras = "".join(letra for letra, _ in questao.alternativas)
        if letras != "ABCDE":
            questao.problemas.append(f"alternativas fora do padrão A–E ({letras or 'nenhuma'})")
        if any(not texto for _, texto in questao.alternativas):
            questao.problemas.append("alternativa sem texto (provável figura ou fórmula)")
        if not questao.enunciado:
            questao.problemas.append("enunciado vazio")
        if questao.correta is None:
            questao.problemas.append("anulada no gabarito")
        if _tem_figura(linhas[inicio], corpo[:fim], figuras):
            questao.problemas.append("figura na área da questão")
        if any(l.pendencia_formula for l in corpo[:fim]):
            questao.problemas.append("sobrescrito ou subscrito não resolvido (fórmula)")
        if _RE_EXIBICAO.search(questao.enunciado):
            questao.problemas.append("cita figura, gráfico ou tabela (conferir no caderno)")
        tudo = questao.enunciado + " " + " ".join(t for _, t in questao.alternativas)
        if _RE_DESTAQUE.search(questao.enunciado) and "**" not in tudo + questao.texto_apoio:
            questao.problemas.append("menciona destaque, mas nenhum trecho destacado foi identificado")
        if estruturado:
            questao.avisos.append("contém código, lista ou tabela com quebras de linha preservadas")
        questoes[numero] = questao
        anterior = questao

    for numero in sorted(set(range(1, total + 1)) - set(inicios)):
        dados = gabarito.get(numero, {"letra": None, "disciplina": ""})
        questoes[numero] = QuestaoExtraida(
            numero=numero, disciplina=dados["disciplina"], correta=dados["letra"],
            problemas=["questão não localizada no caderno"])
    return [questoes[n] for n in sorted(questoes)]


def _tem_figura(linha_numero, corpo, figuras):
    """Há figura entre o topo e a base da questão, na mesma página e coluna?"""
    if not figuras:
        return False
    trechos = {}     # (pagina, coluna) -> (y_topo, y_base)
    for linha in [linha_numero] + list(corpo):
        chave = (linha.pagina, linha.coluna)
        topo, base = trechos.get(chave, (linha.y, linha.y))
        trechos[chave] = (max(topo, linha.y), min(base, linha.y))
    for figura in figuras:
        faixa = trechos.get((figura.pagina, figura.coluna))
        if faixa and figura.y_base <= faixa[0] + 2 and figura.y_topo >= faixa[1] - 2:
            return True
    return False


# ── Conferência entre duas versões do caderno ───────────────────────────────

def _assinatura(questao):
    return (normalizar(questao.enunciado),
            frozenset(normalizar(texto) for _, texto in questao.alternativas))


def _texto_da_correta(questao):
    return next((normalizar(t) for letra, t in questao.alternativas if letra == questao.correta), None)


def conferir_versoes(questoes, questoes_conferencia):
    """Confere cada questão contra a outra versão do caderno.

    As versões trazem as mesmas questões em outra ordem, cada uma com seu
    gabarito. Se a mesma questão (mesmo enunciado, mesmas alternativas) tem como
    resposta o MESMO TEXTO nas duas, a leitura do caderno e a ligação com o
    gabarito estão certas nas duas pontas.

    Devolve {numero: 'conferida' | 'divergente' | 'sem par'}. Questões com
    problema nesta versão, ou sem correspondente legível na outra, ficam
    'sem par'.
    """
    por_assinatura = {}
    por_enunciado = {}
    for q in questoes_conferencia:
        letras = "".join(letra for letra, _ in q.alternativas)
        if q.correta is None or letras != "ABCDE" or not q.enunciado:
            continue
        por_assinatura[_assinatura(q)] = q
        por_enunciado.setdefault(normalizar(q.enunciado), []).append(q)

    resultado = {}
    for q in questoes:
        if q.problemas or q.correta is None:
            resultado[q.numero] = "sem par"
            continue
        par = por_assinatura.get(_assinatura(q))
        if par is None:
            mesmos = por_enunciado.get(normalizar(q.enunciado), [])
            par = mesmos[0] if len(mesmos) == 1 else None
        if par is None:
            resultado[q.numero] = "sem par"
        elif _texto_da_correta(q) == _texto_da_correta(par) and _assinatura(q)[1] == _assinatura(par)[1]:
            resultado[q.numero] = "conferida"
        else:
            resultado[q.numero] = "divergente"
    return resultado
