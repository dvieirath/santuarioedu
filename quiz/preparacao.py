"""
Hub de preparacao completa por concurso.

Deriva analises a partir dos dados que ja existem no BD:
- Incidencia: % de cada disciplina nas questoes do concurso
- Sub-topicos hot: assuntos mais cobrados
- Analise da banca: estilo, distribuicao, pegadinhas tipicas
- Gaps do user: onde ele ta fraco NO que mais cai
- Cronograma: distribuicao de horas por disciplina

Sem novo model — tudo computado on-the-fly com cache curto.
"""
from django.core.cache import cache
from django.db.models import Count, Q, Avg

CACHE_TTL_ANALISE = 60 * 30  # 30min — dados nao mudam constantemente


# ═══════════════════════════════════════════════════════════════════════════
# Analise da banca
# ═══════════════════════════════════════════════════════════════════════════

BANCAS_META = {
    'cebraspe': {
        'nome': 'Cebraspe (CESPE)',
        'estilo': 'Certo/Errado',
        'descricao': 'Banca federal predominante. Formato C/E dominante — cada '
                     'item vale +1 (acertos) ou -1 (erros). Punicao severa por chute.',
        'estilo_pergunta': 'certo_errado',
        'pegadinhas': [
            'Palavras absolutas: "sempre", "nunca", "todos" — geralmente ERRADO',
            'Excecoes: enunciados "salvo", "exceto" invertem logica — leia 2x',
            'Numeros/prazos: memorize com precisao, banca cobra literalidade',
            'Doutrina vs jurisprudencia: banca prefere entendimento consolidado STF/STJ',
            'Sinal negativo (nao, salvo, exceto) — sublinhe pra nao passar batido',
        ],
        'dicas_tempo': 'Cerca de 1min por item. Nao tente responder tudo — chute so no que estiver 70%+ certo.',
        'topicos_fortes': ['Direito Constitucional', 'Direito Administrativo', 'Portugues'],
    },
    'fgv': {
        'nome': 'FGV',
        'estilo': 'Multipla escolha',
        'descricao': 'Banca em ascensao. Enunciados longos com contexto, alternativas '
                     'plausiveis. Cobra interpretacao > memorizacao.',
        'estilo_pergunta': 'multipla_escolha',
        'pegadinhas': [
            'Enunciados de caso pratico — foque no fato descrito, nao teoria pura',
            'Alternativas com "apenas" ou "somente" — pode ser armadilha',
            'Jurisprudencia recente do STF/STJ e cobrada frequentemente',
            'Textos longos com informacoes irrelevantes — extraia so o essencial',
        ],
        'dicas_tempo': 'Cerca de 2-3min por questao. Leia o comando ANTES do enunciado.',
        'topicos_fortes': ['Direito Constitucional', 'Direito Civil', 'Portugues'],
    },
    'fcc': {
        'nome': 'FCC',
        'estilo': 'Multipla escolha',
        'descricao': 'Cobra letra da lei. Enunciados diretos, alternativas curtas. '
                     'Foco em memorizacao precisa.',
        'estilo_pergunta': 'multipla_escolha',
        'pegadinhas': [
            'Troca de artigo/paragrafo ou incisos com valores diferentes',
            'Palavras semelhantes (competencia vs atribuicao)',
            'Prazos: dias corridos vs dias uteis',
            'Alternativas com pequenas alteracoes na letra da lei',
        ],
        'dicas_tempo': 'Cerca de 2min por questao. Se sabe a lei, resolve rapido.',
        'topicos_fortes': ['Direito Administrativo', 'Direito Tributario', 'Portugues'],
    },
    'vunesp': {
        'nome': 'VUNESP',
        'estilo': 'Multipla escolha',
        'descricao': 'Banca de concursos estaduais SP. Estilo pratico, foco em '
                     'aplicacao da lei.',
        'estilo_pergunta': 'multipla_escolha',
        'pegadinhas': [
            'Enunciados de caso pratico — atento a detalhes',
            'Alternativas "salvo" e "exceto" invertem premissa',
            'Cobrancas de datas e prazos com precisao',
        ],
        'dicas_tempo': 'Cerca de 2min por questao. Bem tempo controlado.',
        'topicos_fortes': ['Direito Administrativo', 'Portugues'],
    },
    'cesgranrio': {
        'nome': 'CESGRANRIO',
        'estilo': 'Multipla escolha',
        'descricao': 'Banca de concursos federais (Petrobras, INSS). Foco em '
                     'raciocinio logico + interpretacao.',
        'estilo_pergunta': 'multipla_escolha',
        'pegadinhas': [
            'Problemas matematicos com enunciado longo — extraia os dados',
            'Interpretacao de texto tecnico',
            'Aplicacao pratica de leis',
        ],
        'dicas_tempo': 'Cerca de 2-3min por questao — enunciados longos comuns.',
        'topicos_fortes': ['Raciocinio Logico', 'Portugues', 'Direito Previdenciario'],
    },
}


def get_analise_banca(banca):
    """Retorna dict com analise da banca ou None se nao mapeada."""
    if not banca:
        return None
    return BANCAS_META.get(banca.lower().strip())


# ═══════════════════════════════════════════════════════════════════════════
# Analise de incidencia (por concurso)
# ═══════════════════════════════════════════════════════════════════════════

# Mapeia concurso -> disciplinas relevantes (subset das categorias)
# Usado como filtro base pra analises focadas.
CONCURSO_DISCIPLINAS = {
    'prf': [
        'Direito Constitucional', 'Direito Administrativo', 'Direito Penal',
        'Legislacao de Transito', 'Portugues', 'Raciocinio Logico', 'Informatica',
    ],
    'pf': [
        'Direito Constitucional', 'Direito Administrativo', 'Direito Penal',
        'Direito Processual Penal', 'Portugues', 'Informatica',
    ],
    'inss': [
        'Direito Constitucional', 'Direito Administrativo', 'Direito Previdenciario',
        'Etica no Servico Publico', 'Portugues', 'Raciocinio Logico', 'Informatica',
    ],
    'tjdf': [
        'Direito Constitucional', 'Direito Administrativo', 'Direito Civil',
        'Direito Processual Civil', 'Direito Penal', 'Portugues',
    ],
    'trf': [
        'Direito Constitucional', 'Direito Administrativo', 'Direito Civil',
        'Direito Processual Civil', 'Direito Penal', 'Portugues',
    ],
    'camara': [
        'Direito Constitucional', 'Direito Administrativo', 'Portugues',
        'Administracao Publica',
    ],
    'enem': [
        'Linguagens e Codigos', 'Ciencias Humanas', 'Ciencias da Natureza',
        'Matematica', 'Redacao',
    ],
}


def _match_categoria(nome_alvo):
    """
    Encontra a categoria mais adequada pra um nome de disciplina em
    qualquer nivel hierarquico. Retorna list de categorias (pode ser
    varias — ex: raiz + sub-categoria com mesmo nome).
    Prioridade:
    1. Match iexact em qualquer nivel
    2. Match icontains (tolera "Direito Constitucional" vs "Constitucional")
    """
    from .models import Categoria

    # Nivel 1: match exato em qualquer profundidade
    exatos = list(Categoria.objects.filter(nome__iexact=nome_alvo))
    if exatos:
        return exatos

    # Nivel 2: match parcial (mais permissivo)
    palavras = nome_alvo.lower().split()
    if not palavras:
        return []
    # Palavra mais especifica (nao "direito", "de", "do") — geralmente a ultima
    palavra_chave = palavras[-1]
    if palavra_chave in ('direito', 'de', 'do', 'e', 'da'):
        palavra_chave = palavras[0] if len(palavras) > 1 else nome_alvo
    parciais = list(Categoria.objects.filter(nome__icontains=palavra_chave))
    return parciais[:3]  # cap


def analisar_incidencia_disciplinas(concurso):
    """
    Retorna list de dicts:
    [{disciplina, total, pct, cor}, ...] ordenado por % desc.

    Deriva incidencia agregando todas as sub-categorias que casam com o
    nome da disciplina — funciona pra categorias hierarquicas (ex:
    "Direito Constitucional" pode ser sub-categoria de "Direito").
    """
    from .models import Questao, Categoria

    cache_key = f'incidencia_disc:{concurso}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    disciplinas_alvo = CONCURSO_DISCIPLINAS.get(concurso, [])
    if not disciplinas_alvo:
        return []

    resultado = []
    total_geral = 0
    ids_ja_contados = set()  # evita dupla-contagem entre disciplinas

    for disc_nome in disciplinas_alvo:
        cats = _match_categoria(disc_nome)
        if not cats:
            continue

        # Pega todas as questoes da sub-arvore (dedup via set)
        questao_ids = set()
        for cat in cats:
            for qid in Questao.objects.filter(
                categoria_id__in=cat.subarvore_ids(),
                revisada=True,
            ).exclude(id__in=ids_ja_contados).values_list('id', flat=True):
                questao_ids.add(qid)

        if questao_ids:
            resultado.append({
                'disciplina': disc_nome,
                'total':      len(questao_ids),
            })
            total_geral += len(questao_ids)
            ids_ja_contados.update(questao_ids)

    # Calcula %
    cores = ['#002046', '#006c4d', '#7c3aed', '#0ea5e9', '#f59e0b', '#dc2626', '#059669']
    for i, item in enumerate(resultado):
        item['pct'] = round(item['total'] / total_geral * 100, 1) if total_geral else 0
        item['cor'] = cores[i % len(cores)]

    resultado.sort(key=lambda x: -x['pct'])

    cache.set(cache_key, resultado, CACHE_TTL_ANALISE)
    return resultado


def analisar_subtopicos_hot(concurso, limite=10):
    """
    Retorna top N sub-topicos (Questao.assunto) mais frequentes nas
    questoes do concurso.
    """
    from .models import Questao, Categoria

    cache_key = f'subtopicos_hot:{concurso}:{limite}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    disciplinas_alvo = CONCURSO_DISCIPLINAS.get(concurso, [])
    if not disciplinas_alvo:
        return []

    # Cria filtro Q pra todas as disciplinas relevantes
    from django.db.models import Q as _Q
    filtro = _Q()
    for d in disciplinas_alvo:
        filtro |= _Q(categoria__nome__icontains=d)
        filtro |= _Q(categoria__parent__nome__icontains=d)

    top = (Questao.objects
           .filter(filtro, revisada=True)
           .exclude(assunto__isnull=True)
           .exclude(assunto='')
           .values('assunto', 'categoria__nome')
           .annotate(n=Count('id'))
           .order_by('-n')[:limite])

    resultado = list(top)
    cache.set(cache_key, resultado, CACHE_TTL_ANALISE)
    return resultado


def analisar_gaps_user(user, concurso):
    """
    Cruza incidencia (o que mais cai) com desempenho do user.
    Retorna disciplinas priorizadas: quanto mais cai + user pior, maior prioridade.

    Prioridade = (incidencia_pct * (100 - user_pct)) / 100
    """
    from .models import RespostaUsuario, Categoria

    disciplinas_alvo = CONCURSO_DISCIPLINAS.get(concurso, [])
    if not disciplinas_alvo:
        return []

    incidencia = {d['disciplina']: d for d in analisar_incidencia_disciplinas(concurso)}

    resultado = []
    for disc_nome in disciplinas_alvo:
        cats = _match_categoria(disc_nome)
        if not cats:
            continue

        # Agrega IDs de todas as sub-arvores
        cat_ids = set()
        for cat in cats:
            cat_ids.update(cat.subarvore_ids())

        respostas = RespostaUsuario.objects.filter(
            usuario=user,
            questao__categoria_id__in=cat_ids,
        )
        total_user = respostas.count()
        acertos_user = respostas.filter(acertou=True).count()
        pct_user = round(acertos_user / total_user * 100) if total_user else 0

        inc = incidencia.get(disc_nome, {'pct': 0})
        pct_inc = inc.get('pct', 0)

        # Prioridade: cai muito E user pior nesse assunto
        prioridade = (pct_inc * (100 - pct_user)) / 100

        resultado.append({
            'disciplina':       disc_nome,
            'incidencia_pct':   pct_inc,
            'user_pct':         pct_user,
            'user_total':       total_user,
            'user_acertos':     acertos_user,
            'prioridade':       round(prioridade, 1),
            'status':           _classificar_status(pct_user, total_user),
        })

    resultado.sort(key=lambda x: -x['prioridade'])
    return resultado


def _classificar_status(pct_user, total_user):
    """Rotulo curto pra usar no template."""
    if total_user == 0:
        return {'label': 'Sem dados', 'cor': 'slate'}
    if pct_user >= 80:
        return {'label': 'Dominado', 'cor': 'emerald'}
    if pct_user >= 60:
        return {'label': 'Regular', 'cor': 'amber'}
    return {'label': 'Fraco', 'cor': 'rose'}


def sugerir_cronograma(user, concurso, horas_por_dia=2, dias_ate_prova=None):
    """
    Sugere distribuicao de horas por disciplina baseado em:
    - Incidencia (mais cai = mais tempo)
    - Gaps do user (fraco = mais tempo)

    Retorna list de dicts:
    [{disciplina, minutos_por_dia, prioridade, ...}]
    """
    gaps = analisar_gaps_user(user, concurso)
    if not gaps:
        return []

    # Peso: incidencia + fator de gap (inverso do desempenho)
    for g in gaps:
        # Fator gap: 1 se sem dados, 2 se fraco, 1.5 se regular, 0.8 se dominado
        st = g['status']['label']
        fator_gap = {'Sem dados': 1.3, 'Fraco': 2.0, 'Regular': 1.5, 'Dominado': 0.7}.get(st, 1.0)
        g['peso'] = g['incidencia_pct'] * fator_gap

    total_peso = sum(g['peso'] for g in gaps) or 1
    minutos_totais = horas_por_dia * 60

    for g in gaps:
        pct_tempo = g['peso'] / total_peso
        g['minutos_por_dia'] = int(pct_tempo * minutos_totais)
        g['horas_str'] = f'{g["minutos_por_dia"] // 60}h{g["minutos_por_dia"] % 60:02d}'

    # Ordena por tempo decrescente
    gaps.sort(key=lambda g: -g['minutos_por_dia'])
    return gaps


def resumo_completo(user, concurso):
    """
    Compila tudo pra passar pro template do hub.
    """
    from .concurso_landing import CONCURSOS_LANDING
    from .models import ConcursoPreferido, Categoria

    config = CONCURSOS_LANDING.get(concurso, {})

    # Info do user pra esse concurso
    pref = ConcursoPreferido.objects.filter(usuario=user).first()
    dias_prova = pref.dias_para_prova if pref and pref.concurso == concurso else None
    horas_por_dia = pref.horas_por_dia if pref and pref.concurso == concurso else 2

    incidencia = analisar_incidencia_disciplinas(concurso)
    subtopicos = analisar_subtopicos_hot(concurso, limite=10)
    gaps       = analisar_gaps_user(user, concurso)
    cronograma = sugerir_cronograma(user, concurso, horas_por_dia, dias_prova)

    # Banca predominante do concurso — pega da config do landing
    bancas_concurso = config.get('bancas', [])
    banca_principal = bancas_concurso[0].lower() if bancas_concurso else None
    analise_banca = get_analise_banca(banca_principal) if banca_principal else None

    # Materiais disponiveis (por disciplina raiz)
    from .models import ResumoIA, MapaMental
    materiais_ids_disc = []
    for d in CONCURSO_DISCIPLINAS.get(concurso, []):
        cat = Categoria.objects.filter(nome__iexact=d, parent__isnull=True).first()
        if cat:
            materiais_ids_disc.append(cat.id)
    resumos_disp = ResumoIA.objects.filter(categoria_id__in=materiais_ids_disc).count()
    mapas_disp   = MapaMental.objects.filter(categoria_id__in=materiais_ids_disc).count()

    return {
        'concurso':          concurso,
        'config':            config,
        'incidencia':        incidencia,
        'subtopicos':        subtopicos,
        'gaps':              gaps,
        'cronograma':        cronograma,
        'analise_banca':     analise_banca,
        'dias_prova':        dias_prova,
        'horas_por_dia':     horas_por_dia,
        'total_questoes':    sum(i['total'] for i in incidencia),
        'resumos_disponiveis': resumos_disp,
        'mapas_disponiveis':   mapas_disp,
        'bancas_concurso':   bancas_concurso,
    }
