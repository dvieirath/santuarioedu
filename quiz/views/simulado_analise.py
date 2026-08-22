"""Simulados/analises — estilo banca, sob medida, intensivo — extraidas de views/_todos.py."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ..models import (
    Questao, Alternativa, Categoria, Simulado, RespostaSimulado,
    RespostaUsuario,
)



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403
from ._todos import _check_pode_criar_simulado

@login_required(login_url='account_login')
def simulado_analise_detalhada(request, simulado_id):
    """
    Analise pos-simulado completa: por disciplina, tempo, questoes erradas,
    comparativo com anteriores, sugestoes.
    """
    from django.shortcuts import get_object_or_404
    simulado = get_object_or_404(Simulado, id=simulado_id, usuario=request.user)
    if not simulado.finalizado:
        return redirect('simulado_questao', simulado_id=simulado.id, numero=1)

    respostas = list(simulado.respostas.select_related(
        'questao', 'questao__categoria', 'alternativa_escolhida'
    ))

    # Stats por disciplina
    por_disc = {}
    for r in respostas:
        if not r.alternativa_escolhida:
            continue
        cat = r.questao.categoria
        if not cat:
            continue
        # Sobe pra raiz
        while cat.parent_id:
            cat = cat.parent
        key = cat.nome
        if key not in por_disc:
            por_disc[key] = {'nome': key, 'total': 0, 'acertos': 0, 'erradas': []}
        por_disc[key]['total'] += 1
        acertou = r.alternativa_escolhida.correta
        if acertou:
            por_disc[key]['acertos'] += 1
        else:
            por_disc[key]['erradas'].append(r)

    disciplinas = []
    for key, stats in por_disc.items():
        pct = round(stats['acertos'] / stats['total'] * 100) if stats['total'] else 0
        disciplinas.append({
            **stats,
            'pct':      pct,
            'status':   'solido' if pct >= 70 else 'atencao' if pct >= 50 else 'critico',
        })
    disciplinas.sort(key=lambda d: -d['total'])

    # Tempo total (aproximado — inicio vs fim)
    tempo_total_seg = 0
    if simulado.finalizado_em and simulado.iniciado_em:
        tempo_total_seg = int((simulado.finalizado_em - simulado.iniciado_em).total_seconds())

    total_respondidas = sum(1 for r in respostas if r.alternativa_escolhida)
    tempo_medio_seg = tempo_total_seg // max(1, total_respondidas)

    # Total geral
    total = len(respostas)
    acertos_total = sum(
        1 for r in respostas
        if r.alternativa_escolhida and r.alternativa_escolhida.correta
    )
    pct_geral = round(acertos_total / total * 100) if total else 0

    # Comparativo com simulados anteriores (media dos ultimos 3)
    anteriores = list(Simulado.objects.filter(
        usuario=request.user, finalizado=True,
    ).exclude(id=simulado.id).order_by('-finalizado_em')[:3])

    media_anterior_pct = None
    if anteriores:
        pcts_anteriores = []
        for sim in anteriores:
            r_ant = list(sim.respostas.all())
            t = len(r_ant)
            a = sum(1 for r in r_ant if r.alternativa_escolhida and r.alternativa_escolhida.correta)
            if t:
                pcts_anteriores.append(round(a / t * 100))
        if pcts_anteriores:
            media_anterior_pct = round(sum(pcts_anteriores) / len(pcts_anteriores))

    # Erradas com contexto — top 5 pra treinar
    erradas_top = []
    for d in disciplinas:
        erradas_top.extend(d['erradas'][:2])
    erradas_top = erradas_top[:5]

    return render(request, 'quiz/simulado_analise_detalhada.html', {
        'simulado':          simulado,
        'total':             total,
        'acertos_total':     acertos_total,
        'pct_geral':         pct_geral,
        'disciplinas':       disciplinas,
        'tempo_total_seg':   tempo_total_seg,
        'tempo_medio_seg':   tempo_medio_seg,
        'media_anterior_pct': media_anterior_pct,
        'erradas_top':       erradas_top,
    })

@login_required(login_url='account_login')
def simulado_sob_medida(request):
    """
    Cria simulado personalizado por IA — 20 questoes focadas nos gaps
    do user. Prioriza disciplinas fracas + assuntos pouco respondidos.
    """
    resp = _check_pode_criar_simulado(request)
    if resp: return resp

    # Analise dos gaps: disciplinas onde acerto < 60% + pouca massa
    from django.db.models import Count, Q
    stats_cat = (RespostaUsuario.objects
        .filter(usuario=request.user)
        .values('questao__categoria_id', 'questao__categoria__nome')
        .annotate(
            total=Count('id'),
            acertos=Count('id', filter=Q(acertou=True)),
        )
        .order_by('-total'))

    # Categorias fracas: pct < 60% com pelo menos 3 respostas
    cat_gaps_ids = []
    for s in stats_cat:
        if s['total'] >= 3:
            pct = s['acertos'] / s['total']
            if pct < 0.6:
                cat_gaps_ids.append(s['questao__categoria_id'])

    # Se nao tem gaps ainda, faz mix aleatorio (fallback)
    if not cat_gaps_ids:
        pool = Questao.objects.filter(revisada=True)
    else:
        # 70% das questoes vem dos gaps, 30% de outras (variedade)
        respondidas_ids = list(RespostaUsuario.objects.filter(
            usuario=request.user
        ).values_list('questao_id', flat=True))

        pool_gaps = Questao.objects.filter(
            revisada=True, categoria_id__in=cat_gaps_ids,
        ).exclude(id__in=respondidas_ids)
        pool_geral = Questao.objects.filter(
            revisada=True,
        ).exclude(id__in=respondidas_ids)

        questoes_gaps = list(pool_gaps.order_by('?')[:14])
        questoes_geral = list(pool_geral.order_by('?')[:6])
        questoes = questoes_gaps + questoes_geral
        if len(questoes) < 10:
            # fallback: relaxa filtro de "nao respondidas"
            questoes = list(Questao.objects.filter(revisada=True).order_by('?')[:20])
        else:
            import random as _r
            _r.shuffle(questoes)

    if len(cat_gaps_ids) == 0:
        questoes = list(Questao.objects.filter(revisada=True).order_by('?')[:20])

    if len(questoes) < 10:
        messages.error(request, 'Nao ha questoes suficientes pra montar um simulado personalizado.')
        return redirect('escolher_tema')

    questoes = questoes[:20]  # cap
    simulado = Simulado.objects.create(usuario=request.user)
    RespostaSimulado.objects.bulk_create([
        RespostaSimulado(simulado=simulado, questao=q, ordem=i + 1)
        for i, q in enumerate(questoes)
    ])
    messages.success(
        request,
        f'Simulado sob medida criado — {len(questoes)} questoes focadas nos seus gaps.',
    )
    return redirect('simulado_questao', simulado_id=simulado.id, numero=1)

@login_required(login_url='account_login')
def escolher_estilo_banca(request):
    """
    Pagina de selecao de estilo de simulado por banca.
    Cebraspe = so C/E. FGV/FCC/etc = so ME.
    """
    from ..preparacao import BANCAS_META
    from ..models import Questao

    bancas_com_stats = []
    for slug, meta in BANCAS_META.items():
        # Estima quantas questoes disponiveis pra cada estilo
        tipo_alvo = 'CE' if meta['estilo_pergunta'] == 'certo_errado' else 'ME'
        n = Questao.objects.filter(revisada=True, tipo=tipo_alvo).count()
        bancas_com_stats.append({
            'slug':          slug,
            'meta':          meta,
            'tipo':          tipo_alvo,
            'questoes_disp': n,
        })

    return render(request, 'quiz/escolher_estilo_banca.html', {
        'bancas': bancas_com_stats,
    })

@login_required(login_url='account_login')
def iniciar_simulado_estilo_banca(request, banca):
    """
    Cria simulado filtrado pelo estilo tipico da banca:
    - Cebraspe: so questoes CE (Certo/Errado)
    - FGV/FCC/VUNESP/CESGRANRIO: so ME (Multipla Escolha)
    """
    from ..preparacao import BANCAS_META

    resp = _check_pode_criar_simulado(request)
    if resp:
        return resp

    banca_meta = BANCAS_META.get(banca.lower())
    if not banca_meta:
        messages.error(request, 'Banca nao suportada.')
        return redirect('escolher_estilo_banca')

    tipo_alvo = 'CE' if banca_meta['estilo_pergunta'] == 'certo_errado' else 'ME'

    pool = Questao.objects.filter(revisada=True, tipo=tipo_alvo)
    if pool.count() < 10:
        messages.error(
            request,
            f'Poucas questoes {tipo_alvo} disponiveis pra {banca_meta["nome"]}. '
            f'Volte em breve.'
        )
        return redirect('escolher_estilo_banca')

    qtd = min(Simulado.TOTAL_QUESTOES, pool.count())
    questoes = list(pool.order_by('?')[:qtd])

    simulado = Simulado.objects.create(usuario=request.user)
    RespostaSimulado.objects.bulk_create([
        RespostaSimulado(simulado=simulado, questao=q, ordem=i + 1)
        for i, q in enumerate(questoes)
    ])

    messages.success(
        request,
        f'Simulado estilo {banca_meta["nome"]} iniciado — {qtd} questoes {tipo_alvo}.',
    )
    return redirect('simulado_questao', simulado_id=simulado.id, numero=1)

@login_required(login_url='account_login')
def ranking_concurso(request, concurso):
    """
    Top 10 users com esse concurso como preferido, ordenados por XP.
    Mostra posicao do proprio user.
    """
    from ..models import ConcursoPreferido, NivelUsuario
    from ..concurso_landing import CONCURSOS_LANDING

    if concurso not in CONCURSOS_LANDING:
        from django.http import Http404
        raise Http404('Concurso nao suportado')

    config = CONCURSOS_LANDING[concurso]

    # Users com esse concurso preferido
    prefs = ConcursoPreferido.objects.filter(concurso=concurso).select_related('usuario')
    users_ids = [p.usuario_id for p in prefs]

    if not users_ids:
        return render(request, 'quiz/ranking_concurso.html', {
            'config':          config,
            'concurso':        concurso,
            'ranking':         [],
            'total_users':     0,
            'posicao_user':    None,
        })

    # Ranking por XP
    niveis = list(NivelUsuario.objects.filter(usuario_id__in=users_ids)
                  .select_related('usuario').order_by('-xp_total'))

    ranking = []
    posicao_user = None
    for i, n in enumerate(niveis[:20], 1):
        entry = {
            'posicao': i,
            'usuario': n.usuario,
            'xp':      n.xp_total,
            'nivel':   n.nivel,
            'rank':    n.rank_nome,
            'eu':      n.usuario == request.user,
        }
        ranking.append(entry)

    # Descobre posicao do user (mesmo fora do top 20)
    for i, n in enumerate(niveis, 1):
        if n.usuario_id == request.user.id:
            posicao_user = i
            break

    return render(request, 'quiz/ranking_concurso.html', {
        'config':       config,
        'concurso':     concurso,
        'ranking':      ranking,
        'total_users':  len(users_ids),
        'posicao_user': posicao_user,
    })

@login_required(login_url='account_login')
def modo_intensivo(request, categoria_id):
    """
    Modo intensivo por disciplina: sessao focada com timer configuravel
    (30/45/60min) e stats em tempo real via session.

    Session state:
      intensivo_<cat_id> = {
        'iniciado_em': iso timestamp,
        'duracao_min': 30|45|60,
        'respondidas_ids': [],
        'acertos': N,
      }
    """
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    cat = get_object_or_404(Categoria, id=categoria_id)
    session_key = f'intensivo_{cat.id}'
    estado = request.session.get(session_key)

    # Iniciar sessao
    if request.method == 'POST' and request.POST.get('acao') == 'iniciar':
        duracao = int(request.POST.get('duracao_min', 30))
        if duracao not in (15, 30, 45, 60, 90):
            duracao = 30
        request.session[session_key] = {
            'iniciado_em':     timezone.now().isoformat(),
            'duracao_min':     duracao,
            'respondidas_ids': [],
            'acertos':         0,
        }
        request.session.modified = True
        return redirect('modo_intensivo', categoria_id=cat.id)

    # Encerrar sessao
    if request.method == 'POST' and request.POST.get('acao') == 'encerrar':
        estado_final = request.session.pop(session_key, None)
        request.session.modified = True
        if estado_final:
            return render(request, 'quiz/modo_intensivo_resultado.html', {
                'categoria':      cat,
                'total':          len(estado_final.get('respondidas_ids', [])),
                'acertos':        estado_final.get('acertos', 0),
                'duracao_min':    estado_final.get('duracao_min', 30),
            })
        return redirect('modo_intensivo', categoria_id=cat.id)

    # Se nao ha sessao ativa, mostra tela de configuracao
    if not estado:
        subarv = cat.subarvore_ids()
        n_disponiveis = Questao.objects.filter(
            revisada=True, categoria_id__in=subarv,
        ).count()
        return render(request, 'quiz/modo_intensivo_config.html', {
            'categoria':      cat,
            'n_disponiveis':  n_disponiveis,
            'duracoes':       [15, 30, 45, 60, 90],
        })

    # Verifica se tempo expirou
    iniciado = parse_datetime(estado['iniciado_em'])
    agora = timezone.now()
    duracao_min = estado['duracao_min']
    segundos_totais = duracao_min * 60
    segundos_gastos = int((agora - iniciado).total_seconds())
    segundos_restantes = max(0, segundos_totais - segundos_gastos)

    if segundos_restantes == 0:
        # Tempo esgotado -> encerra automaticamente
        request.session.pop(session_key, None)
        request.session.modified = True
        return render(request, 'quiz/modo_intensivo_resultado.html', {
            'categoria':      cat,
            'total':          len(estado['respondidas_ids']),
            'acertos':        estado['acertos'],
            'duracao_min':    duracao_min,
            'tempo_esgotado': True,
        })

    # Processar resposta se POST
    if request.method == 'POST' and request.POST.get('alternativa_id'):
        alt_id = request.POST.get('alternativa_id')
        try:
            alt = Alternativa.objects.get(id=alt_id)
            q = alt.questao
            if q.id not in estado['respondidas_ids']:
                estado['respondidas_ids'].append(q.id)
                if alt.correta:
                    estado['acertos'] += 1

                # Tambem cria RespostaUsuario (conta pro XP/streak/analise)
                RespostaUsuario.objects.get_or_create(
                    usuario=request.user, questao=q,
                    defaults={'acertou': alt.correta},
                )

                request.session[session_key] = estado
                request.session.modified = True
        except Alternativa.DoesNotExist:
            pass

    # Escolhe proxima questao (nao respondida na sessao)
    subarv = cat.subarvore_ids()
    proxima = (Questao.objects
               .filter(revisada=True, categoria_id__in=subarv)
               .exclude(id__in=estado['respondidas_ids'])
               .order_by('?').first())

    if not proxima:
        # Acabaram as questoes -> encerra
        request.session.pop(session_key, None)
        request.session.modified = True
        return render(request, 'quiz/modo_intensivo_resultado.html', {
            'categoria':      cat,
            'total':          len(estado['respondidas_ids']),
            'acertos':        estado['acertos'],
            'duracao_min':    duracao_min,
            'esgotou_pool':   True,
        })

    return render(request, 'quiz/modo_intensivo.html', {
        'categoria':          cat,
        'questao':            proxima,
        'alternativas':       list(proxima.alternativa_set.all()),
        'respondidas':        len(estado['respondidas_ids']),
        'acertos':            estado['acertos'],
        'segundos_restantes': segundos_restantes,
        'duracao_min':        duracao_min,
    })
