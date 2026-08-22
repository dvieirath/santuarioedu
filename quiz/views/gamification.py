"""Gamification (conquistas, ranking, XP, SRS) — extraidas de views/_todos.py."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta

from ..models import (
    Conquista, RespostaUsuario, MetaEstudo, NivelUsuario,
    Categoria, Questao, RevisaoEspacada,
)



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403

@login_required(login_url='account_login')
def conquistas(request):
    desbloqueadas = {c.codigo: c for c in Conquista.objects.filter(usuario=request.user)}
    total_respostas = RespostaUsuario.objects.filter(usuario=request.user).count()
    total_simulados = Simulado.objects.filter(usuario=request.user, finalizado=True).count()
    acertos = RespostaUsuario.objects.filter(usuario=request.user, acertou=True).count()
    meta, _ = MetaEstudo.objects.get_or_create(usuario=request.user)
    total_cats = Categoria.objects.count()
    cats_respondidas = RespostaUsuario.objects.filter(
        usuario=request.user).values('questao__categoria').distinct().count()

    def _pct(atual, meta_v):
        if atual >= meta_v:
            return 100
        return min(100, int(atual / meta_v * 100)) if meta_v else 0

    pct_acerto = (acertos / max(1, total_respostas)) if total_respostas else 0

    # Progresso pra cada conquista (todos os 26 codigos)
    progresso = {
        'primeiro_acerto':    100 if acertos >= 1 else 0,
        'dez_questoes':       _pct(total_respostas, 10),
        'centenario':         _pct(total_respostas, 100),
        'quinhentos':         _pct(total_respostas, 500),
        'milenar':            _pct(total_respostas, 1000),
        'streak_3':           _pct(meta.streak_atual, 3),
        'streak_7':           _pct(meta.streak_atual, 7),
        'streak_14':          _pct(meta.streak_atual, 14),
        'streak_30':          _pct(meta.streak_atual, 30),
        'streak_100':         _pct(meta.streak_atual, 100),
        'atirador':           100 if (total_respostas >= 50 and pct_acerto >= 0.90) else _pct(total_respostas, 50),
        'sniper':             100 if (total_respostas >= 100 and pct_acerto >= 0.95) else _pct(total_respostas, 100),
        'perfeicionista':     100 if (total_respostas >= 20 and acertos == total_respostas) else _pct(total_respostas, 20),
        'primeiro_simulado':  _pct(total_simulados, 1),
        'simuladista':        _pct(total_simulados, 5),
        'veterano_simulado':  _pct(total_simulados, 25),
        'simulado_perfeito':  100 if 'simulado_perfeito' in desbloqueadas else 0,
        'enciclopedia':       _pct(cats_respondidas, max(1, total_cats)),
        'generalista':        _pct(cats_respondidas, 5),
        'especialista':       100 if 'especialista' in desbloqueadas else _pct(total_respostas, 100),
        'madrugador':         100 if 'madrugador' in desbloqueadas else 0,
        'noturno':            100 if 'noturno' in desbloqueadas else 0,
        'primeiro_duelo':     100 if 'primeiro_duelo' in desbloqueadas else 0,
        'duelista':           100 if 'duelista' in desbloqueadas else _pct(len(desbloqueadas), 10),
        'colecionador':       _pct(len(desbloqueadas), 5),
        'lenda':              _pct(len(desbloqueadas), 15),
    }

    todas = []
    for codigo, meta_info in CONQUISTAS_META.items():
        obj = desbloqueadas.get(codigo)
        raridade = meta_info.get('raridade', 'comum')
        todas.append({
            'codigo':      codigo,
            'emoji':       meta_info['emoji'],
            'label':       meta_info['label'],
            'desc':        meta_info['desc'],
            'categoria':   meta_info.get('categoria', 'geral'),
            'raridade':    raridade,
            'cor':         RARIDADE_CORES.get(raridade, RARIDADE_CORES['comum']),
            'desbloqueada': obj is not None,
            'data':        obj.desbloqueado_em if obj else None,
            'progresso':   progresso.get(codigo, 0),
        })
    # Ordena: desbloqueadas primeiro, depois por raridade (lendaria antes de comum)
    ordem_rar = {'lendaria': 0, 'epica': 1, 'rara': 2, 'incomum': 3, 'comum': 4}
    todas.sort(key=lambda x: (not x['desbloqueada'], ordem_rar.get(x['raridade'], 5), x['codigo']))

    # Agrupa por categoria pra display
    from collections import OrderedDict
    por_categoria = OrderedDict()
    for t in todas:
        por_categoria.setdefault(t['categoria'], []).append(t)

    return render(request, 'quiz/conquistas.html', {
        'todas': todas,
        'por_categoria': por_categoria,
        'total_desbloqueadas': len(desbloqueadas),
        'total': len(CONQUISTAS_META),
        'pct_completo': round(len(desbloqueadas) / len(CONQUISTAS_META) * 100),
    })

@login_required(login_url='account_login')
def ranking(request):
    """Ranking público: top 20 por questões, acertos e streak."""
    periodo = request.GET.get('periodo', 'total')  # 'total' | 'semana' | 'mes'

    filtro_data = {}
    if periodo == 'semana':
        filtro_data['data__gte'] = timezone.now() - timedelta(days=7)
    elif periodo == 'mes':
        filtro_data['data__gte'] = timezone.now() - timedelta(days=30)

    # Agrega por usuário
    ranking_qs = (
        RespostaUsuario.objects.filter(**filtro_data)
        .values('usuario__id', 'usuario__username', 'usuario__first_name', 'usuario__last_name')
        .annotate(
            total=Count('id'),
            acertos=Count('id', filter=Q(acertou=True)),
        )
        .filter(total__gt=0)
        .order_by('-total', '-acertos')[:20]
    )

    # Enriquecer com streak e conquistas
    dados = []
    meu_id = request.user.id
    minha_pos = None
    for i, r in enumerate(ranking_qs, 1):
        uid = r['usuario__id']
        try:
            m = MetaEstudo.objects.get(usuario_id=uid)
            streak = m.streak_atual
        except MetaEstudo.DoesNotExist:
            streak = 0
        pct = round(r['acertos'] / r['total'] * 100) if r['total'] else 0
        nome = r['usuario__first_name'] or r['usuario__username']
        dados.append({
            'pos': i,
            'username': r['usuario__username'],
            'nome': nome,
            'total': r['total'],
            'acertos': r['acertos'],
            'pct': pct,
            'streak': streak,
            'sou_eu': uid == meu_id,
        })
        if uid == meu_id:
            minha_pos = i

    # Posição do usuário logado se não está no top 20
    if minha_pos is None:
        meu_total = RespostaUsuario.objects.filter(usuario=request.user, **filtro_data).count()
        acima = (
            RespostaUsuario.objects.filter(**filtro_data)
            .values('usuario')
            .annotate(t=Count('id'))
            .filter(t__gt=meu_total)
            .count()
        )
        minha_pos = acima + 1

    return render(request, 'quiz/ranking.html', {
        'dados': dados,
        'periodo': periodo,
        'minha_pos': minha_pos,
        'periodo_choices': [('total', 'Total'), ('mes', 'Último Mês'), ('semana', 'Semana')],
    })

@login_required
def painel_xp(request):
    nivel, _ = NivelUsuario.objects.get_or_create(usuario=request.user)
    top      = NivelUsuario.objects.select_related('usuario').order_by('-xp_total')[:10]
    pos      = NivelUsuario.objects.filter(xp_total__gt=nivel.xp_total).count() + 1
    total_u  = NivelUsuario.objects.count()

    # Histórico de XP diário estimado (acertos × 10 XP via RespostaUsuario)
    hoje = timezone.now().date()
    historico_xp = []
    for i in range(6, -1, -1):
        d = hoje - timedelta(days=i)
        acertos_d = RespostaUsuario.objects.filter(
            usuario=request.user,
            data__date=d,
            acertou=True,
        ).count()
        historico_xp.append({'label': d.strftime('%d/%m'), 'xp': acertos_d * 10})

    return render(request, 'quiz/painel_xp.html', {
        'nivel':        nivel,
        'top':          top,
        'posicao':      pos,
        'total':        total_u,
        'historico_xp': historico_xp,
    })

@login_required(login_url='account_login')
def revisao_srs(request):
    """Modo revisão espaçada: mostra questões com proxima_revisao <= hoje."""
    hoje = timezone.localdate()

    if request.method == 'POST':
        alternativa_id = request.POST.get('alternativa_id')
        cat_id_post    = request.POST.get('categoria_id')
        escolha = get_object_or_404(Alternativa, id=alternativa_id)

        RespostaUsuario.objects.create(
            usuario=request.user, questao=escolha.questao, acertou=escolha.correta
        )
        meta, _ = MetaEstudo.objects.get_or_create(usuario=request.user)
        meta.atualizar_streak()

        # Atualiza SRS
        srs, _ = RevisaoEspacada.objects.get_or_create(
            usuario=request.user, questao=escolha.questao,
            defaults={'proxima_revisao': hoje}
        )
        srs.atualizar(escolha.correta)

        is_favorita = QuestaoFavorita.objects.filter(
            usuario=request.user, questao=escolha.questao
        ).exists()
        anotacao = AnotacaoUsuario.objects.filter(
            usuario=request.user, questao=escolha.questao
        ).first()

        # Quantas ainda pendentes hoje
        pendentes = RevisaoEspacada.objects.filter(
            usuario=request.user, proxima_revisao__lte=hoje
        ).count()

        return render(request, 'quiz/resultado.html', {
            'escolha': escolha,
            'categoria_id': cat_id_post,
            'is_favorita': is_favorita,
            'anotacao': anotacao,
            'filtros': {},
            'modo_srs': True,
            'srs_pendentes': pendentes,
            'srs_proxima': srs.proxima_revisao,
            'novas_conquistas': [],
        })

    # Conta pendentes
    total_pendentes = RevisaoEspacada.objects.filter(
        usuario=request.user, proxima_revisao__lte=hoje
    ).count()

    # GET sem ?start → página de entrada
    if not request.GET.get('start'):
        return render(request, 'quiz/revisao_srs_inicio.html', {
            'pendentes': total_pendentes,
        })

    # GET com ?start → próxima questão SRS
    srs_item = (
        RevisaoEspacada.objects
        .filter(usuario=request.user, proxima_revisao__lte=hoje)
        .select_related('questao')
        .order_by('proxima_revisao', 'fator_facilidade')   # mais urgentes primeiro
        .first()
    )

    if not srs_item:
        pendentes_amanha = RevisaoEspacada.objects.filter(
            usuario=request.user,
            proxima_revisao=hoje + timedelta(days=1)
        ).count()
        return render(request, 'quiz/sem_questoes.html', {
            'mensagem': 'Todas as revisões do dia estão em dia! 🎉',
            'subtexto': f'{pendentes_amanha} questão(ões) agendada(s) para amanhã.',
        })

    return render(request, 'quiz/responder.html', {
        'questao': srs_item.questao,
        'categoria_id': srs_item.questao.categoria_id,
        'filtros': {},
        'modo_srs': True,
        'srs_pendentes': total_pendentes,
    })
