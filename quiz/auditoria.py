"""
Detecção de problemas de qualidade em questões.

Módulo puro (sem side effects). Usado por:
  - Management command `auditar_questoes` (relatório + auto-fix)
  - View `api_revisao_proxima` (filtro no painel de revisão)
  - Card de revisão (mostra flags detectadas ao revisor)
"""
import re


CONJUNCOES_FIM = {
    'que', 'de', 'em', 'por', 'para', 'com', 'sobre', 'sem',
    'o', 'a', 'os', 'as', 'do', 'da', 'dos', 'das',
    'no', 'na', 'nos', 'nas', 'ao', 'à', 'aos', 'às',
    'e', 'ou', 'mas', 'se', 'quando', 'onde',
}

TERMINACOES_INCOMPLETAS = {',', ':', ';', '-', '/', '('}
CARS_CONTROLE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
BACKSLASH_N_LITERAL = re.compile(r'\\n|\\r|\\t')

# Flags "graves" — precisam intervenção humana (não têm auto-fix seguro).
FLAGS_GRAVES = {
    'texto_muito_curto',
    'marcador_conteudo_faltando',
    'referencia_a_imagem_sem_imagem',
    'referencia_a_texto_ausente',
    'enunciado_termina_em_pontuacao_incompleta',
    'termina_em_conjuncao',
    'sem_gabarito',
    'multiplos_gabaritos',
    'alternativa_vazia',
    'alternativa_muito_curta',
    'alternativa_igual_ao_enunciado',
    'numero_alts_invalido_ce',
    'numero_alts_invalido_me',
    'alternativas_duplicadas',
    'aspa_desbalanceada',
    'sem_justificativa',
}

# Labels legíveis para UI/CLI
LABEL_FLAG = {
    'texto_muito_curto':                            'Enunciado muito curto (< 40 chars)',
    'marcador_conteudo_faltando':                   'Marcador [...] ou ___ no enunciado',
    'referencia_a_imagem_sem_imagem':               'Cita figura/gráfico/imagem que não está anexada',
    'referencia_a_texto_ausente':                   'Cita "texto/trecho/fragmento" que não está no enunciado',
    'enunciado_termina_em_pontuacao_incompleta':    'Termina com ,;:- (frase cortada)',
    'ponto_duplo_no_fim':                           'Termina com .. (não ...)',
    'termina_em_conjuncao':                         'Termina em conjunção — frase cortada',
    'espacos_duplicados':                           'Espaços duplicados',
    'espaco_antes_pontuacao':                       'Espaço antes de pontuação',
    'caracteres_controle':                          'Caracteres de controle invisíveis',
    'escapes_literais':                             r'Escapes literais (\n, \r, \t)',
    'caracteres_repetidos':                         'Letras repetidas seguidas (aaaa)',
    'aspa_desbalanceada':                           'Aspas desbalanceadas',
    'palavras_duplicadas':                          'Palavras duplicadas seguidas',
    'sem_gabarito':                                 'Nenhuma alternativa marcada correta',
    'multiplos_gabaritos':                          'Mais de 1 alternativa correta',
    'alternativa_vazia':                            'Alternativa em branco',
    'alternativa_muito_curta':                      'Alternativa com < 2 chars',
    'alternativas_duplicadas':                      'Alternativas idênticas',
    'alternativa_igual_ao_enunciado':               'Alternativa idêntica ao enunciado',
    'numero_alts_invalido_ce':                     'CE deve ter 2 alternativas',
    'numero_alts_invalido_me':                     'ME deve ter 4 ou 5 alternativas',
    'sem_justificativa':                            'Sem justificativa (ou < 50 chars)',
}


def detectar_flags(q, alts=None):
    """Retorna lista de flags detectados na questão q e suas alternativas.

    Se `alts` não for passado, faz q.alternativa_set.all() (custoso). Prefira
    passar quando já tem prefetch.
    """
    if alts is None:
        alts = list(q.alternativa_set.all())

    flags = []
    texto = (q.texto or '').strip()

    if len(texto) < 40:
        flags.append('texto_muito_curto')
    if '[...]' in texto or '[…]' in texto:
        flags.append('marcador_conteudo_faltando')
    if re.search(r'_{3,}', texto):
        flags.append('marcador_conteudo_faltando')
    if re.search(r'\b(figura|quadro|imagem|gr[aá]fico|infogr[aá]fico|mapa|desenho|ilustra[cç][aã]o|foto)\b',
                 texto, re.I) and not getattr(q, 'imagem', None):
        flags.append('referencia_a_imagem_sem_imagem')

    # Referência a texto/trecho de apoio que NÃO está no enunciado.
    #
    # 3 níveis de força de sinal (vamos flag se sinal + enunciado curto):
    #  A) Código de referência tipo CESPE (texto CG2A1) → sinal muito forte
    #  B) Frases idiomáticas (texto acima, leia o texto) → sinal forte
    #  C) Menção genérica a "o texto"/"no texto"/"do texto" → sinal médio
    #
    # Heurística de tamanho: em enunciados curtos, referência a "o texto" quase
    # sempre significa que o texto de apoio não foi importado. Em enunciados
    # longos (>800 chars), pode ser que o próprio enunciado seja o texto.

    _tem_aspas_grandes = bool(re.search(r'["“].{50,}["”]', texto))  # trecho entre aspas dentro do enunciado

    # A) Código de referência CESPE (texto CG2A1 etc)
    _codigo_ref = re.search(
        r'\b(?:texto|trecho|fragmento|excerto|par[aá]grafo)\s+([A-Z]{1,4}\d[A-Z0-9\-]{1,10})\b',
        texto,
    )

    # B) Frases idiomáticas fortes
    _sinal_forte = re.search(
        r'\b('
        r'(?:com base|considerando|tendo (?:como referência|em vista)|de acordo)\s+'
        r'(?:no|com|nos?|na)\s+(?:texto|trecho|fragmento|excerto|artigo\s+transcrito|par[aá]grafo|enunciado)|'
        r'texto\s+(?:acima|abaixo|a seguir|apresentado|transcrito|reproduzido)|'
        r'trecho\s+(?:acima|abaixo|a seguir|apresentado|transcrito|reproduzido)|'
        r'fragmento\s+(?:acima|abaixo|a seguir|apresentado|transcrito)|'
        r'(?:leia|analise|observe)\s+(?:o|a)\s+(?:texto|trecho|fragmento|excerto)|'
        r'no\s+(?:texto|trecho|fragmento|excerto)\s+(?:acima|abaixo|a seguir|apresentado)|'
        r'artigo\s+transcrito\s+(?:acima|abaixo|a seguir)|'
        r'(?:no|do|ao)\s+(?:\w+\s+)?par[aá]grafo\s+do\s+texto|'
        r'per[ií]odo\s+do\s+texto'
        r')\b',
        texto, re.I,
    )

    # C) Menção genérica: "o texto", "no texto", "do texto" — mais sensível
    _sinal_medio = re.search(
        r'\b('
        r'(?:o|do|no|ao|pelo)\s+texto\b|'
        r'segundo\s+o\s+texto|'
        r'entende-se\s+(?:do|no)\s+texto|'
        r'conclui-se\s+(?:do|no)\s+texto|'
        r'aspectos?\s+.{1,30}\s+do\s+texto|'
        r'reescrita\s+de\s+trechos?\s+do\s+texto|'
        r'sentidos?\s+do\s+texto|'
        r'quanto\s+ao\s+texto'
        r')\b',
        texto, re.I,
    )

    ln = len(texto)
    marcar_ref = False
    if _codigo_ref and ln < 1200:
        marcar_ref = True
    elif _sinal_forte and ln < 800:
        marcar_ref = True
    elif _sinal_medio and ln < 500 and not _tem_aspas_grandes:
        # Se tem trecho grande entre aspas, provavelmente o texto está embutido
        marcar_ref = True

    if marcar_ref:
        flags.append('referencia_a_texto_ausente')

    if texto and texto[-1] in TERMINACOES_INCOMPLETAS:
        flags.append('enunciado_termina_em_pontuacao_incompleta')
    if texto.endswith('..') and not texto.endswith('...'):
        flags.append('ponto_duplo_no_fim')

    palavras = re.findall(r'\S+', texto)
    if palavras:
        ultima = palavras[-1].lower().strip('.,;:!?')
        if ultima in CONJUNCOES_FIM:
            flags.append('termina_em_conjuncao')

    if re.search(r'  +', texto):
        flags.append('espacos_duplicados')
    if re.search(r' [.,;:!?]', texto):
        flags.append('espaco_antes_pontuacao')
    if CARS_CONTROLE.search(texto):
        flags.append('caracteres_controle')
    if BACKSLASH_N_LITERAL.search(texto):
        flags.append('escapes_literais')
    if re.search(r'([a-záéíóúâêôãõç])\1{3,}', texto, re.I):
        flags.append('caracteres_repetidos')

    aspas_retas = texto.count('"')
    aspas_esq   = texto.count('“')
    aspas_dir   = texto.count('”')
    if aspas_retas % 2 == 1 and aspas_esq == 0 and aspas_dir == 0:
        flags.append('aspa_desbalanceada')

    if re.search(r'\b(\w{3,})\s+\1\b', texto, re.I):
        flags.append('palavras_duplicadas')

    n_corretas = sum(1 for a in alts if a.correta)
    if n_corretas == 0:
        flags.append('sem_gabarito')
    if n_corretas > 1:
        flags.append('multiplos_gabaritos')

    for a in alts:
        at = (a.texto or '').strip()
        if not at:
            flags.append('alternativa_vazia'); break
        if len(at) < 2:
            flags.append('alternativa_muito_curta'); break

    textos_alt = [(a.texto or '').strip().lower() for a in alts]
    if len(set(textos_alt)) < len(textos_alt):
        flags.append('alternativas_duplicadas')
    if any(at == texto.lower() for at in textos_alt if at):
        flags.append('alternativa_igual_ao_enunciado')

    if q.tipo == 'CE' and len(alts) != 2:
        flags.append('numero_alts_invalido_ce')
    if q.tipo == 'ME' and len(alts) not in (4, 5):
        flags.append('numero_alts_invalido_me')

    justif = (q.justificativa or '').strip()
    if len(justif) < 50:
        flags.append('sem_justificativa')

    return flags


def label_flag(flag):
    """Retorna label humano para exibição."""
    return LABEL_FLAG.get(flag, flag.replace('_', ' '))
