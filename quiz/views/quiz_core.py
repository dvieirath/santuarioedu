"""Quiz — fluxo core (escolher tema, responder, favoritas, analises) — extraidas de views/_todos.py."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta

from ..models import (
    Questao, Alternativa, Categoria, RespostaUsuario, QuestaoFavorita,
    MetaEstudo, RevisaoEspacada, NivelUsuario, AnotacaoUsuario,
    Notificacao,
)



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403
from ._todos import _dar_xp

@login_required(login_url='account_login')
def escolher_tema(request):
    """Navegacao hierarquica de categorias. Otimizado pra evitar N+1:
    - Todas Categoria carregadas de uma vez (~24 registros)
    - Contagens de Questao agregadas em 1 query
    - Respondidas do usuario em 1 query
    Total: ~4-5 queries independente de N categorias. Antes: 100+.

    Modo busca (?q=xxx): retorna lista FLAT de categorias cujo nome bate
    (icontains), em qualquer nivel da arvore. Cada resultado mostra o
    caminho completo (Ciencias > Biologia > Anatomia)."""
    parent_id = request.GET.get('parent', '').strip()
    query = request.GET.get('q', '').strip()

    # Load all Categoria em memoria (baixa cardinalidade, ~24 no total)
    todas_cats = list(Categoria.objects.all())
    filhos_map = {}  # {parent_id: [filhos_da_categoria]}
    id_map = {c.id: c for c in todas_cats}
    for c in todas_cats:
        filhos_map.setdefault(c.parent_id, []).append(c)

    def _subarvore_ids(cat_id):
        """BFS in-memory — evita queries recursivas ao BD."""
        resultado = [cat_id]
        pilha = list(filhos_map.get(cat_id, []))
        while pilha:
            f = pilha.pop()
            resultado.append(f.id)
            pilha.extend(filhos_map.get(f.id, []))
        return resultado

    parent = None
    breadcrumb = []
    if parent_id.isdigit():
        parent = id_map.get(int(parent_id))
        if parent:
            no = parent
            while no:
                breadcrumb.insert(0, {'id': no.id, 'nome': no.nome})
                no = id_map.get(no.parent_id) if no.parent_id else None

    # Categorias visiveis:
    # - Se ?q=xxx: busca em TODA arvore por nome (case-insensitive)
    # - Se parent: filhos daquele parent
    # - Senao: raizes
    if query:
        q_lower = query.lower()
        cats_visiveis = sorted(
            [c for c in todas_cats if q_lower in c.nome.lower()],
            key=lambda c: (0 if c.nome.lower().startswith(q_lower) else 1, c.nome)
        )
    elif parent:
        cats_visiveis = sorted(filhos_map.get(parent.id, []), key=lambda c: c.nome)
    else:
        cats_visiveis = sorted(filhos_map.get(None, []), key=lambda c: c.nome)

    # Pra cada categoria visivel, resolve sua subarvore (in-memory)
    subarvores = {c.id: _subarvore_ids(c.id) for c in cats_visiveis}

    # Query 1: contagem de questoes por categoria_id (uma unica query)
    from django.db.models import Q as _Q
    todos_ids_relevantes = set()
    for ids in subarvores.values():
        todos_ids_relevantes.update(ids)

    counts_qs = (Questao.objects.filter(categoria_id__in=todos_ids_relevantes)
                 .values('categoria_id')
                 .annotate(
                     total=Count('id'),
                     de_prova=Count('id', filter=_Q(gerada_por_ia=False) & ~_Q(banca__isnull=True) & ~_Q(banca='')),
                     por_ia=Count('id', filter=_Q(gerada_por_ia=True)),
                 ))
    counts_map = {c['categoria_id']: c for c in counts_qs}

    # Query 2: respondidas do usuario por categoria_id
    resp_qs = (RespostaUsuario.objects
               .filter(usuario=request.user, questao__categoria_id__in=todos_ids_relevantes)
               .values('questao__categoria_id')
               .annotate(n=Count('questao_id', distinct=True)))
    resp_map = {r['questao__categoria_id']: r['n'] for r in resp_qs}

    def _caminho_completo(cat_id):
        """Reconstroi 'Ciencias > Biologia > Anatomia' a partir de cat_id."""
        partes = []
        no = id_map.get(cat_id)
        for _ in range(10):
            if not no:
                break
            partes.append(no.nome)
            no = id_map.get(no.parent_id) if no.parent_id else None
        return ' > '.join(reversed(partes))

    dados_categorias = []
    for cat in cats_visiveis:
        ids_sub = subarvores[cat.id]
        total = sum(counts_map.get(cid, {}).get('total', 0) for cid in ids_sub)
        de_prova = sum(counts_map.get(cid, {}).get('de_prova', 0) for cid in ids_sub)
        por_ia = sum(counts_map.get(cid, {}).get('por_ia', 0) for cid in ids_sub)
        respondidas = sum(resp_map.get(cid, 0) for cid in ids_sub)
        n_filhos = len(filhos_map.get(cat.id, []))

        dados_categorias.append({
            'id': cat.id,
            'nome': cat.nome,
            'total': total,
            'de_prova': de_prova,
            'por_ia': por_ia,
            'respondidas': respondidas,
            'concluido': respondidas >= total and total > 0,
            'n_filhos': n_filhos,
            'tem_filhos': n_filhos > 0,
            # Caminho completo — mostrado quando busca ativa
            'caminho': _caminho_completo(cat.id) if query else '',
        })

    contexto = {
        'categorias': dados_categorias,
        'parent': parent,
        'breadcrumb': breadcrumb,
        'query': query,
        'total_resultados': len(dados_categorias),
    }
    if parent:
        parent_sub_ids = _subarvore_ids(parent.id)
        contexto['parent_total_subarvore'] = sum(
            counts_map.get(cid, {}).get('total', 0) for cid in parent_sub_ids
        )

    return render(request, 'quiz/escolher_tema.html', contexto)

@login_required(login_url='account_login')
def iniciar_quiz(request, categoria_id=None):
    if request.method == 'POST':
        # ── Limite de plano: questões/dia ──
        from ..limits import pode_responder_questao, get_plano
        if not pode_responder_questao(request.user):
            if get_plano(request.user) == 'gratuito':
                # Modal contextual (view dedicada) em vez de warning + planos generico.
                # Momento quente = maior conversao free -> PRO.
                return redirect('limite_atingido_questoes')
            messages.warning(request, 'Limite diário de questões atingido.')
            return redirect('dashboard')

        # Valida alternativa_id (evita 500 se payload malformado)
        alternativa_id = request.POST.get('alternativa_id', '').strip()
        if not alternativa_id.isdigit():
            messages.error(request, 'Selecione uma alternativa antes de confirmar.')
            return redirect('escolher_tema')

        escolha = get_object_or_404(Alternativa, id=int(alternativa_id))
        cat_id_post = request.POST.get('categoria_id')

        # ── Idempotencia: se ja respondeu essa questao HOJE, nao duplica ──
        # Protege contra: double-click, F5 na pagina de resultado, back-button.
        hoje = timezone.localdate()
        ja_respondeu = RespostaUsuario.objects.filter(
            usuario=request.user, questao=escolha.questao, data__date=hoje,
        ).exists()

        xp_ganho = 0
        subiu_nivel = None
        novas_conquistas_qs = []

        if not ja_respondeu:
            RespostaUsuario.objects.create(
                usuario=request.user,
                questao=escolha.questao,
                acertou=escolha.correta,
            )

            # Atualiza streak e meta diária
            meta, _ = MetaEstudo.objects.get_or_create(usuario=request.user)
            meta.atualizar_streak()

            # SRS
            srs, _ = RevisaoEspacada.objects.get_or_create(
                usuario=request.user,
                questao=escolha.questao,
                defaults={'proxima_revisao': timezone.localdate()},
            )
            srs.atualizar(escolha.correta)

            # Conquistas
            novas_conquistas_qs = verificar_conquistas(request.user)
            if novas_conquistas_qs:
                request.session['novas_conquistas'] = novas_conquistas_qs

            # XP (so pra acerto)
            if escolha.correta:
                xp_ganho = 10
                _dar_xp(request.user, xp_ganho, request.session)
                subiu_nivel = request.session.pop('subiu_nivel', None)

        # Justificativa IA — chamada assincrona via fetch no resultado.html
        # (antes era sincrona, bloqueava request ate 30s sem feedback visual)

        is_favorita = QuestaoFavorita.objects.filter(
            usuario=request.user, questao=escolha.questao
        ).exists()
        anotacao = AnotacaoUsuario.objects.filter(
            usuario=request.user, questao=escolha.questao
        ).first()
        filtros = {
            'banca':  request.POST.get('f_banca', ''),
            'ano':    request.POST.get('f_ano', ''),
            'tipo':   request.POST.get('f_tipo', ''),
            'modo':   request.POST.get('f_modo', ''),
            'origem': request.POST.get('f_origem', ''),
        }
        avaliacao_obj = AvaliacaoQuestao.objects.filter(
            usuario=request.user, questao=escolha.questao
        ).first()

        # Streak atual pra mostrar no toast do resultado
        try:
            streak_atual = request.user.metaestudo.streak_atual
        except Exception:
            streak_atual = 0

        return render(request, 'quiz/resultado.html', {
            'escolha': escolha,
            'categoria_id': cat_id_post,
            'is_favorita': is_favorita,
            'anotacao': anotacao,
            'filtros': filtros,
            'avaliacao_dificuldade': avaliacao_obj.dificuldade if avaliacao_obj else None,
            'ja_respondeu_antes': ja_respondeu,
            'xp_ganho': xp_ganho,
            'streak_atual': streak_atual,
            'subiu_nivel': subiu_nivel,
            'novas_conquistas': [
                {'codigo': c, **CONQUISTAS_META.get(c, {'label': c, 'emoji': '🏆', 'desc': ''})}
                for c in request.session.pop('novas_conquistas', [])
            ],
        })

    # LÓGICA DO GET (EXIBIÇÃO)
    # Página aleatória removida: bare /quiz/ sem categoria nem filtros → escolher matéria
    if categoria_id is None and not request.GET:
        return redirect('escolher_tema')

    # Só questões aprovadas na revisão chegam ao usuário — pendentes/rejeitadas
    # (IA sem justificativa, texto de apoio ausente, sem gabarito) ficam fora.
    questoes = Questao.objects.filter(revisada=True, rejeitada_definitiva=False)

    if categoria_id:
        questoes = questoes.filter(categoria_id=categoria_id)

    # Filtros avançados via GET
    f_banca  = request.GET.get('banca', '').strip()
    f_ano    = request.GET.get('ano', '').strip()
    f_tipo   = request.GET.get('tipo', '').strip()
    f_modo   = request.GET.get('modo', 'novas')     # 'novas' | 'erradas' | 'todas'
    f_origem = request.GET.get('origem', '').strip()  # 'real' | 'ia' | ''

    if f_banca:
        questoes = questoes.filter(banca__icontains=f_banca)
    if f_ano:
        questoes = questoes.filter(ano=f_ano)
    if f_tipo:
        questoes = questoes.filter(tipo=f_tipo)
    if f_origem == 'real':
        # Prova real = tem banca preenchida E não foi gerada por IA
        questoes = questoes.filter(gerada_por_ia=False).exclude(banca='').exclude(banca__isnull=True)
    elif f_origem == 'ia':
        questoes = questoes.filter(gerada_por_ia=True)

    if f_modo == 'erradas':
        erradas_ids = RespostaUsuario.objects.filter(
            usuario=request.user, acertou=False
        ).values_list('questao_id', flat=True)
        questoes = questoes.filter(id__in=erradas_ids)
    elif f_modo != 'todas':
        # padrão: apenas não respondidas
        respondidas_ids = RespostaUsuario.objects.filter(
            usuario=request.user
        ).values_list('questao_id', flat=True)
        questoes = questoes.exclude(id__in=respondidas_ids)

    # Substitui .order_by('?') (full table scan + sort — 200-500ms em bancos
    # grandes) por sampling via random offset. Uma query pra count e outra
    # pra fetch — total O(1) em vez de O(n log n).
    # BUG anterior: usava .first() apos slice — Django adiciona order_by('pk')
    # internamente em .first() e nao pode reordenar apos slice. Fix: iter ou index.
    _count = questoes.count()
    questao = None
    if _count:
        import random as _random
        _offset = _random.randrange(_count)
        _slice = list(questoes[_offset:_offset + 1])
        if _slice:
            questao = _slice[0]

    if not questao:
        msg = 'Nenhuma questão encontrada com esses filtros.' if (f_banca or f_ano or f_tipo) else (
            'Você concluiu todas as questões deste tema!' if categoria_id
            else 'Você concluiu todas as questões disponíveis!'
        )
        return render(request, 'quiz/sem_questoes.html', {'mensagem': msg})

    filtros = {'banca': f_banca, 'ano': f_ano, 'tipo': f_tipo, 'modo': f_modo, 'origem': f_origem}

    # Progresso real do usuario na categoria/filtro atual (X/N no card lateral)
    progresso_ctx = {}
    if categoria_id:
        try:
            cat = Categoria.objects.get(pk=categoria_id)
            ids_sub = cat.subarvore_ids()  # inclui sub-categorias na contagem
            total_cat = Questao.objects.filter(
                categoria_id__in=ids_sub, revisada=True, rejeitada_definitiva=False,
            ).count()
            resp_cat = RespostaUsuario.objects.filter(
                usuario=request.user, questao__categoria_id__in=ids_sub,
            ).values('questao').distinct().count()
            progresso_ctx = {
                'categoria_nome':       cat.nome,
                'total_categoria':      total_cat,
                'respondidas_categoria':resp_cat,
                'restam_categoria':     max(0, total_cat - resp_cat),
            }
        except Categoria.DoesNotExist:
            pass

    # Estado de favorita/anotacao pra questao atual — vinha vazio antes,
    # entao icones nao refletiam estado real
    is_favorita_atual = QuestaoFavorita.objects.filter(
        usuario=request.user, questao=questao,
    ).exists()

    contexto = {
        'questao': questao,
        'categoria_id': categoria_id,
        'filtros': filtros,
        'is_favorita_atual': is_favorita_atual,
        **progresso_ctx,
    }
    return render(request, 'quiz/responder.html', contexto)

@login_required(login_url='account_login')
def estudar_por_assunto(request):
    """
    Lista assuntos hierárquicos (Disciplina — Tópico — Subtópico) com filtros
    por disciplina e tópico. Permite iniciar quiz filtrando por assunto.

    Estrutura dos dados:
    - cada Questao.assunto segue formato 'Disciplina — Tópico — Subtópico'
    - parseamos em níveis e agrupamos por tópico para facilitar navegação
    """
    cat_id     = request.GET.get('categoria', '')
    topico     = request.GET.get('topico', '').strip()
    busca      = request.GET.get('q', '').strip()
    nivel_filtro = request.GET.get('nivel', '').strip()  # forte/regular/fraco/novo
    banca_filtro = request.GET.get('banca', '').strip()
    ano_filtro   = request.GET.get('ano', '').strip()

    qs_assuntos = (
        Questao.objects
        .filter(assunto__isnull=False, revisada=True)
        .exclude(assunto='')
    )
    if cat_id:
        qs_assuntos = qs_assuntos.filter(categoria_id=cat_id)
    if busca:
        qs_assuntos = qs_assuntos.filter(assunto__icontains=busca)
    if banca_filtro:
        qs_assuntos = qs_assuntos.filter(banca__iexact=banca_filtro)
    if ano_filtro:
        try:
            qs_assuntos = qs_assuntos.filter(ano=int(ano_filtro))
        except (TypeError, ValueError):
            pass

    raw_assuntos = (
        qs_assuntos
        .values('assunto', 'categoria__nome', 'categoria__id')
        .annotate(total=Count('id'))
        .order_by('categoria__nome', 'assunto')
    )

    # Respostas do usuário por assunto (mapa para enriquecer)
    respondidas_por_assunto = (
        RespostaUsuario.objects.filter(
            usuario=request.user,
            questao__assunto__isnull=False,
        )
        .values('questao__assunto')
        .annotate(
            resp=Count('id'),
            acertos=Count('id', filter=Q(acertou=True)),
        )
    )
    resp_map = {r['questao__assunto']: r for r in respondidas_por_assunto}

    def _parse_niveis(assunto_str):
        """Parseia 'Disciplina — Tópico — Subtópico' em até 3 níveis."""
        # Aceita ' — ' (em-dash) ou ' - ' (hyphen) como separador
        partes = [p.strip() for p in assunto_str.replace(' — ', '|').replace(' - ', '|').split('|')]
        if len(partes) == 1:
            return {'disciplina_raw': None, 'topico': partes[0], 'subtopico': None, 'label_curto': partes[0]}
        if len(partes) == 2:
            return {'disciplina_raw': partes[0], 'topico': partes[1], 'subtopico': None, 'label_curto': partes[1]}
        # 3+ níveis: junta o resto como subtópico
        return {'disciplina_raw': partes[0], 'topico': partes[1], 'subtopico': ' — '.join(partes[2:]),
                'label_curto': partes[1] + ' · ' + ' — '.join(partes[2:])}

    # Lista achatada com parsing
    assuntos_dados = []
    for a in raw_assuntos:
        nome    = a['assunto']
        r_data  = resp_map.get(nome, {'resp': 0, 'acertos': 0})
        total   = a['total']
        resp    = r_data['resp']
        acertos = r_data['acertos']
        pct     = round(acertos / resp * 100) if resp else 0
        nivel   = 'forte' if pct >= 70 else 'regular' if pct >= 50 else 'fraco' if resp else 'novo'
        parsed  = _parse_niveis(nome)
        assuntos_dados.append({
            'assunto':     nome,
            'cat_nome':    a['categoria__nome'],
            'cat_id':      a['categoria__id'],
            'topico':      parsed['topico'],
            'subtopico':   parsed['subtopico'],
            'label_curto': parsed['label_curto'],
            'total':       total,
            'resp':        resp,
            'acertos':     acertos,
            'pct':         pct,
            'nivel':       nivel,
        })

    # Filtro por tópico (depois do parsing, para usar valor parseado)
    if topico:
        assuntos_dados = [a for a in assuntos_dados if a['topico'].lower() == topico.lower()]
    if nivel_filtro:
        assuntos_dados = [a for a in assuntos_dados if a['nivel'] == nivel_filtro]

    # ── Agrupamento Disciplina → Tópico → Subtópicos ─────────────────────────
    # Estrutura final: lista de disciplinas, cada uma com lista de tópicos,
    # cada tópico com lista de subtópicos + agregados (total, resp, acertos).
    from collections import defaultdict
    disc_topic_map = defaultdict(lambda: defaultdict(list))
    for a in assuntos_dados:
        disc_topic_map[(a['cat_id'], a['cat_nome'])][a['topico']].append(a)

    grupos = []
    for (cat_id_g, cat_nome_g), topicos_map in sorted(disc_topic_map.items(), key=lambda x: x[0][1]):
        topicos_list = []
        for topico_nome, subs in sorted(topicos_map.items()):
            total_t   = sum(s['total']   for s in subs)
            resp_t    = sum(s['resp']    for s in subs)
            acertos_t = sum(s['acertos'] for s in subs)
            pct_t     = round(acertos_t / resp_t * 100) if resp_t else 0
            nivel_t   = 'forte' if pct_t >= 70 else 'regular' if pct_t >= 50 else 'fraco' if resp_t else 'novo'
            # Se só tem 1 subtópico igual ao tópico (sem hierarquia), simplifica
            tem_hierarquia = any(s['subtopico'] for s in subs) or len(subs) > 1
            topicos_list.append({
                'topico':    topico_nome,
                'subs':      sorted(subs, key=lambda s: s['subtopico'] or ''),
                'total':     total_t,
                'resp':      resp_t,
                'acertos':   acertos_t,
                'pct':       pct_t,
                'nivel':     nivel_t,
                'tem_hierarquia': tem_hierarquia,
            })
        grupos.append({
            'cat_id':   cat_id_g,
            'cat_nome': cat_nome_g,
            'topicos':  topicos_list,
            'total_questoes': sum(t['total']   for t in topicos_list),
            'total_resp':     sum(t['resp']    for t in topicos_list),
            'total_topicos':  len(topicos_list),
        })

    # Lista de tópicos disponíveis para o dropdown (filtra pela categoria se aplicado)
    topicos_dropdown = sorted({a['topico'] for a in assuntos_dados})

    # ── Estatísticas globais ────────────────────────────────────────────────
    stats_global = {
        'total_assuntos': len(assuntos_dados),
        'total_questoes': sum(a['total']  for a in assuntos_dados),
        'total_resp':     sum(a['resp']   for a in assuntos_dados),
        'total_acertos':  sum(a['acertos'] for a in assuntos_dados),
        'fortes':   sum(1 for a in assuntos_dados if a['nivel'] == 'forte'),
        'regulares':sum(1 for a in assuntos_dados if a['nivel'] == 'regular'),
        'fracos':   sum(1 for a in assuntos_dados if a['nivel'] == 'fraco'),
        'novos':    sum(1 for a in assuntos_dados if a['nivel'] == 'novo'),
    }
    stats_global['pct_geral'] = (
        round(stats_global['total_acertos'] / stats_global['total_resp'] * 100)
        if stats_global['total_resp'] else 0
    )

    categorias = Categoria.objects.order_by('nome')

    # Dropdowns de banca e ano — a partir do universo total revisado (nao
    # filtrado) pra manter opcoes visiveis mesmo quando filtro atual as
    # remove do resultado.
    bancas_disponiveis = list(
        Questao.objects.filter(revisada=True)
        .exclude(banca__isnull=True).exclude(banca='')
        .values_list('banca', flat=True).distinct().order_by('banca')
    )
    anos_disponiveis = list(
        Questao.objects.filter(revisada=True)
        .exclude(ano__isnull=True)
        .values_list('ano', flat=True).distinct().order_by('-ano')
    )

    return render(request, 'quiz/estudar_por_assunto.html', {
        'grupos':             grupos,
        'topicos_dropdown':   topicos_dropdown,
        'categorias':         categorias,
        'cat_id':             cat_id,
        'topico':             topico,
        'busca':              busca,
        'nivel_filtro':       nivel_filtro,
        'banca_filtro':       banca_filtro,
        'ano_filtro':         ano_filtro,
        'bancas_disponiveis': bancas_disponiveis,
        'anos_disponiveis':   anos_disponiveis,
        'stats':              stats_global,
    })

@login_required(login_url='account_login')
def quiz_por_assunto(request, assunto):
    """Quiz filtrando por assunto específico."""
    import urllib.parse
    assunto_decoded = urllib.parse.unquote(assunto)

    if request.method == 'POST':
        return iniciar_quiz(request)

    questoes = Questao.objects.filter(
        assunto__iexact=assunto_decoded, revisada=True, rejeitada_definitiva=False,
    )
    respondidas_ids = RespostaUsuario.objects.filter(
        usuario=request.user
    ).values_list('questao_id', flat=True)

    nao_respondidas = questoes.exclude(id__in=respondidas_ids)
    questao = nao_respondidas.order_by('?').first() or questoes.order_by('?').first()

    if not questao:
        return render(request, 'quiz/sem_questoes.html', {
            'mensagem': f'Nenhuma questão encontrada para o assunto "{assunto_decoded}".'
        })

    return render(request, 'quiz/responder.html', {
        'questao':       questao,
        'categoria_id':  questao.categoria_id,
        'filtros':       {},
        'assunto_atual': assunto_decoded,
    })

@login_required(login_url='account_login')
def caderno_erros(request):
    cat_id = request.GET.get('categoria', '')
    busca  = request.GET.get('q', '').strip()

    # Erros de estudo livre (RespostaUsuario)
    erros_estudo = set(
        RespostaUsuario.objects
        .filter(usuario=request.user, acertou=False)
        .values_list('questao_id', flat=True)
    )
    # Erros de simulados (RespostaSimulado) — antes ficavam invisiveis
    # aqui, mesmo que fossem os erros mais relevantes do concurseiro.
    erros_simulado = set(
        RespostaSimulado.objects
        .filter(simulado__usuario=request.user, acertou=False)
        .values_list('questao_id', flat=True)
    )
    erros_qs = list(erros_estudo | erros_simulado)

    questoes = (
        Questao.objects
        .filter(id__in=erros_qs)
        .select_related('categoria')
        .prefetch_related('alternativa_set')
    )

    if cat_id:
        questoes = questoes.filter(categoria_id=cat_id)
    if busca:
        questoes = questoes.filter(texto__icontains=busca)

    # Anotar com contagem de erros do usuário
    questoes_com_erros = []
    for q in questoes:
        n_erros = RespostaUsuario.objects.filter(
            usuario=request.user, questao=q, acertou=False
        ).count()
        is_fav = QuestaoFavorita.objects.filter(usuario=request.user, questao=q).exists()
        questoes_com_erros.append({'questao': q, 'erros': n_erros, 'is_fav': is_fav})
    questoes_com_erros.sort(key=lambda x: x['erros'], reverse=True)

    from django.core.paginator import Paginator
    paginator = Paginator(questoes_com_erros, 20)
    page_obj  = paginator.get_page(request.GET.get('page', 1))

    categorias = Categoria.objects.all().order_by('nome')
    return render(request, 'quiz/caderno_erros.html', {
        'page_obj': page_obj,
        'categorias': categorias,
        'cat_id': cat_id,
        'busca': busca,
        'total': len(questoes_com_erros),
    })

@login_required(login_url='account_login')
def favoritas(request):
    cat_id = request.GET.get('categoria', '')
    qs = (
        QuestaoFavorita.objects
        .filter(usuario=request.user)
        .select_related('questao__categoria')
        .prefetch_related('questao__alternativa_set')
    )
    if cat_id:
        qs = qs.filter(questao__categoria_id=cat_id)

    from django.core.paginator import Paginator
    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page', 1))
    categorias = Categoria.objects.all().order_by('nome')
    return render(request, 'quiz/favoritas.html', {
        'page_obj': page_obj,
        'categorias': categorias,
        'cat_id': cat_id,
        'total': qs.count(),
    })

@login_required(login_url='account_login')
@require_POST
@ratelimit(key='user', rate='60/m', method='POST', block=True)
def toggle_favorita(request, questao_id):
    """Alterna favorita. Exige POST — nunca GET (evita prefetch acidental).
    Rate limit: 60 favoritas/min por user (evita bot spam)."""
    questao = get_object_or_404(Questao, id=questao_id)
    fav, criada = QuestaoFavorita.objects.get_or_create(
        usuario=request.user, questao=questao
    )
    if not criada:
        fav.delete()
        return JsonResponse({'status': 'removed'})
    return JsonResponse({'status': 'added'})

@login_required(login_url='account_login')
@ratelimit(key='user', rate='10/h', method='GET', block=True)
def analise_erros(request):
    """
    Analisa padrões de erro do usuário com IA e exibe insights
    acionáveis + gráficos de desempenho.
    """
    import json as _json

    respostas = RespostaUsuario.objects.filter(usuario=request.user)
    total     = respostas.count()

    if total < 10:
        return render(request, 'quiz/analise_erros.html', {
            'dados_insuficientes': True,
            'total': total,
        })

    # ── Por categoria ─────────────────────────────────────────────────────────
    cats_data = []
    for cat in Categoria.objects.all():
        r = respostas.filter(questao__categoria=cat)
        t = r.count()
        if t < 3:
            continue
        a = r.filter(acertou=True).count()
        e = t - a
        pct = round(a / t * 100)
        cats_data.append({
            'id':      cat.id,
            'nome':    cat.nome,
            'total':   t,
            'acertos': a,
            'erros':   e,
            'pct':     pct,
        })
    cats_data.sort(key=lambda x: x['pct'])  # pior primeiro

    # ── Top questões mais erradas ─────────────────────────────────────────────
    top_erros = list(
        respostas.filter(acertou=False)
        .values('questao__id', 'questao__texto', 'questao__categoria__nome',
                'questao__assunto')
        .annotate(vezes=Count('id'))
        .order_by('-vezes')[:10]
    )

    # ── Erros por dia da semana ────────────────────────────────────────────────
    from django.db.models.functions import ExtractWeekDay
    erros_por_dia_qs = (
        respostas.filter(acertou=False)
        .annotate(dia=ExtractWeekDay('data'))
        .values('dia')
        .annotate(n=Count('id'))
        .order_by('dia')
    )
    dias_semana = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb']
    erros_dia_map = {e['dia']: e['n'] for e in erros_por_dia_qs}
    erros_semana  = [{'dia': dias_semana[i], 'n': erros_dia_map.get(i + 1, 0)} for i in range(7)]

    # ── Tendência (últimas 4 semanas) ─────────────────────────────────────────
    from django.db.models.functions import TruncWeek as _TrW
    tendencia_qs = (
        respostas.filter(data__gte=timezone.now() - timedelta(days=28))
        .annotate(sem=_TrW('data'))
        .values('sem')
        .annotate(
            total=Count('id'),
            acertos=Count('id', filter=Q(acertou=True)),
        )
        .order_by('sem')
    )
    tendencia = [
        {
            'semana': t['sem'].strftime('%d/%m') if t['sem'] else '',
            'pct': round(t['acertos'] / t['total'] * 100) if t['total'] else 0,
            'total': t['total'],
        }
        for t in tendencia_qs
    ]

    # ── Insight de IA ─────────────────────────────────────────────────────────
    ia_insight = ''
    if cats_data:
        pior    = cats_data[0]
        melhor  = cats_data[-1] if len(cats_data) > 1 else cats_data[0]
        assuntos_erros = [e['questao__assunto'] for e in top_erros[:5] if e.get('questao__assunto')]
        resumo_prompt = (
            f"Candidato tem {total} respostas totais.\n"
            f"Disciplina mais fraca: {pior['nome']} com {pior['pct']}% "
            f"({pior['erros']} erros em {pior['total']} questões).\n"
            f"Disciplina mais forte: {melhor['nome']} com {melhor['pct']}%.\n"
            f"Assuntos com mais erros: {', '.join(assuntos_erros) if assuntos_erros else 'variados'}.\n"
            f"Total de erros: {sum(c['erros'] for c in cats_data)}.\n"
        )
        try:
            ia_insight = ai_tutor_responder(
                "Com base nos dados de estudo abaixo, forneça 4 insights curtos e diretos "
                "em formato de bullets (•) sobre: padrões de erro, o que priorizar, "
                "estratégia de revisão recomendada e uma dica motivacional. "
                "Seja específico ao concurso alvo do candidato.\n\n" + resumo_prompt,
                usuario=request.user,
            )
        except Exception:
            ia_insight = ''

    return render(request, 'quiz/analise_erros.html', {
        'total':             total,
        'cats_data':         cats_data,
        'top_erros':         top_erros,
        'erros_semana':      erros_semana,
        'tendencia':         tendencia,
        'ia_insight':        ia_insight,
        'dados_insuficientes': False,
        'cats_json':         _json.dumps([
            {'nome': c['nome'], 'pct': c['pct'], 'erros': c['erros'], 'total': c['total']}
            for c in cats_data
        ]),
        'semana_json':       _json.dumps(erros_semana),
        'tendencia_json':    _json.dumps(tendencia),
    })

@login_required(login_url='account_login')
def analise_subtemas(request):
    """Quebra performance por assunto (campo Questao.assunto), não só categoria."""
    from ..models import RespostaUsuario
    from django.db.models import Count, Q

    qs = (RespostaUsuario.objects
          .filter(usuario=request.user, questao__assunto__isnull=False)
          .exclude(questao__assunto='')
          .values('questao__categoria__id', 'questao__categoria__nome', 'questao__assunto')
          .annotate(
              total=Count('id'),
              acertos=Count('id', filter=Q(acertou=True)),
          )
          .order_by('-total'))

    dados = []
    for r in qs:
        total = r['total']
        acertos = r['acertos']
        pct = round(acertos / total * 100) if total else 0
        dados.append({
            'categoria_id': r['questao__categoria__id'],
            'categoria':    r['questao__categoria__nome'] or '—',
            'assunto':      r['questao__assunto'],
            'total':        total,
            'acertos':      acertos,
            'pct':          pct,
            'cor':          'emerald' if pct >= 75 else 'amber' if pct >= 50 else 'red',
        })

    fracos = [d for d in dados if d['pct'] < 60][:10]
    fortes = [d for d in dados if d['pct'] >= 75][:10]

    return render(request, 'quiz/analise_subtemas.html', {
        'dados':  dados,
        'fracos': fracos,
        'fortes': fortes,
        'total_subtemas': len(dados),
    })
