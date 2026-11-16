"""
Triagem sem IA das questões pendentes geradas por IA.

Responde uma pergunta só: esta questão tem defeito que dá para PROVAR olhando
o registro, sem perguntar a ninguém? Se tem, ela pode ser descartada sem gastar
revisão humana nem cota de IA.

A regra é conservadora de propósito. As heurísticas da auditoria
(`quiz/auditoria.py`) servem para chamar a atenção do revisor e por isso
aceitam falso positivo ("direito à imagem" acusa imagem ausente). Aqui o
resultado é descarte, então só entra o que foi conferido em amostra:

- gabarito impossível (nenhuma ou mais de uma correta, alternativas iguais);
- formato quebrado (certo/errado com A) a E) dentro do enunciado);
- item de certo/errado que não é afirmação nem pergunta de sim ou não;
- enunciado que cita material que não está nele.

O que não é provável aqui fica para a conferência de gabarito por IA
(`quiz/verificacao_ia.py`).

Usado por `manage.py triar_pendentes_ia`.
"""
import re

PREFIXO_MOTIVO = '[triagem automática] '

_MATERIAL = r'(?:texto|trecho|fragmento|excerto|passagem|tabela|quadro)s?'
_VISUAL = r'(?:figura|gr[aá]fico|imagem|charge|tirinha|ilustra[cç][aã]o)s?'

# "o texto acima": o material deveria vir ANTES da citação.
_RE_ANTES = re.compile(
    rf'\b{_MATERIAL}\s+(?:acima|anterior|supracitad[oa]s?)\b', re.I)
# "o texto a seguir": o material deveria vir DEPOIS da citação.
_RE_DEPOIS = re.compile(
    rf'\b{_MATERIAL}\s+(?:a seguir|abaixo)\b', re.I)
# Figura citada por posição. Questão gerada por IA nunca tem imagem.
_RE_FIGURA = re.compile(
    rf'\b{_VISUAL}\s+(?:acima|anterior|abaixo|a seguir|ao lado)\b', re.I)

_RE_COMECA_COM_TEXTO = re.compile(
    r'^\s*(?:texto|leia|observe|analise|considere o (?:seguinte )?(?:texto|trecho|caso))\b', re.I)
_RE_ALTERNATIVA_NO_TEXTO = re.compile(r'(?m)^\s*\(?[A-Ea-e]\)\s+\S')
_RE_FRASES = re.compile(r'(?<=[.!?])\s+')

_RE_JULGA_AFIRMACAO = re.compile(
    r'\b(?:afirma[cç][aã]o|proposi[cç][aã]o|assertiva|senten[cç]a|enunciado|item)\b'
    r'[^.?!]*\b(?:é|está)\s*:$', re.I)
_RE_PROMETE_CONTEUDO = re.compile(r'\b(?:a seguir|seguintes?|abaixo)\b', re.I)
# Pergunta aberta: pronome interrogativo abrindo a frase, depois de vírgula ou
# seguido de verbo. "a qual", "o que estabelece a lei" e "quanto ao mérito" são
# relativos e aparecem em pergunta de sim ou não, por isso ficam de fora.
_RE_PERGUNTA_ABERTA = re.compile(
    r'^\W*(?:e |então |assim,? |nesse caso,? |diante disso,? )?'
    r'(?:qual|quais|quem|o que|por que|como|onde|quando|quanto|quant[oa]s|de que|em que|a que)\b'
    r'|[,:;]\s*(?:qual|quais|quem|o que|por que|quant[oa]s)\b'
    r'|(?<![oa] )(?<![oa]s )\bqua(?:l|is)\s+(?:é|são|foi|seria|será|deve|das?|dos?)\b',
    re.I)
_RE_DUAS_OPCOES = re.compile(r'\b(\w+)\s+ou\s+(\w+)\s*\?$', re.I)
_SIM = {'correta', 'correto', 'certa', 'certo', 'verdadeira', 'verdadeiro'}
_NAO = {'incorreta', 'incorreto', 'errada', 'errado', 'falsa', 'falso'}


def _certo_errado_responde(a, b):
    """'correta ou incorreta?' se responde com certo/errado; 'legal ou ilegal?' não."""
    a, b = a.lower(), b.lower()
    return (a in _SIM and b in _NAO) or (a in _NAO and b in _SIM)


def _norm(texto):
    return ' '.join((texto or '').lower().split())


def _ultima_frase(texto):
    return _RE_FRASES.split(texto.strip())[-1].strip()


def _motivo_certo_errado(texto):
    """Item de certo/errado precisa ser afirmação, ou no máximo pergunta de sim ou não."""
    fim = texto[-1:]
    if fim not in (':', '?'):
        return None
    frase = _ultima_frase(texto)

    if fim == ':':
        if _RE_JULGA_AFIRMACAO.search(frase) and not _RE_PROMETE_CONTEUDO.search(frase):
            return None  # "(afirmação). Essa afirmação é:"
        if _RE_PROMETE_CONTEUDO.search(frase):
            return 'termina anunciando um conteúdo "a seguir" que não vem'
        return 'item de certo/errado que termina em dois-pontos, pedindo um complemento que não existe'

    if _RE_PROMETE_CONTEUDO.search(frase):
        return 'termina anunciando um conteúdo "a seguir" que não vem'
    if _RE_PERGUNTA_ABERTA.search(frase):
        return 'pergunta aberta em item de certo/errado (não se responde com certo ou errado)'
    duas = _RE_DUAS_OPCOES.search(frase)
    if duas and not _certo_errado_responde(*duas.groups()):
        return 'pergunta com duas opções em item de certo/errado (certo não diz qual delas)'
    return None


def _motivo_material_ausente(q, texto):
    if not getattr(q, 'imagem', None) and _RE_FIGURA.search(texto):
        return 'cita figura, gráfico ou imagem, e a questão não tem imagem'
    if getattr(q, 'texto_apoio_id', None):
        return None

    antes = _RE_ANTES.search(texto)
    if antes and antes.start() < 150 and not _RE_COMECA_COM_TEXTO.search(texto):
        # "Considerando o texto acima: (texto)" traz o material logo depois.
        if not texto[antes.end():antes.end() + 3].lstrip().startswith(':'):
            return 'cita "texto acima" e não há texto antes da citação'

    depois = _RE_DEPOIS.search(texto)
    if depois and len(texto) - depois.end() < 60:
        return 'cita "texto a seguir" e o enunciado acaba logo depois'
    return None


def motivo_de_rejeicao(q, alts):
    """Motivo (str) quando a questão tem defeito comprovável sem IA; senão None."""
    texto = (q.texto or '').strip()
    textos = [(a.texto or '').strip() for a in alts]
    corretas = sum(1 for a in alts if a.correta)

    if not texto:
        return 'enunciado vazio'
    if corretas == 0:
        return 'sem alternativa correta marcada'
    if corretas > 1:
        return 'mais de uma alternativa marcada como correta'
    if any(not t for t in textos):
        return 'alternativa em branco'
    if len({_norm(t) for t in textos}) < len(textos):
        return 'alternativas com texto idêntico'

    if q.tipo == 'CE':
        if len(alts) != 2:
            return 'certo/errado sem exatamente duas alternativas'
        if len(_RE_ALTERNATIVA_NO_TEXTO.findall(texto)) >= 3:
            return 'certo/errado com alternativas de múltipla escolha coladas no enunciado'
        motivo = _motivo_certo_errado(texto)
        if motivo:
            return motivo
    elif len(alts) not in (4, 5):
        return 'múltipla escolha sem 4 ou 5 alternativas'

    return _motivo_material_ausente(q, texto)


def pendentes_de_ia():
    """Fila que a triagem e a conferência por IA atacam."""
    from .models import Questao
    return (
        Questao.objects
        .filter(revisada=False, rejeitada_definitiva=False, gerada_por_ia=True)
        .select_related('categoria', 'texto_apoio')
        .prefetch_related('alternativa_set')
        .order_by('id')
    )
