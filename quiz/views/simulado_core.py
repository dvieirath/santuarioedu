"""Simulado — fluxo core (iniciar, responder, finalizar, resultado) — extraidas de views/_todos.py."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Count, Q
from django.db import transaction
from datetime import timedelta

from ..models import (
    Simulado, RespostaSimulado, Questao, Alternativa, Categoria,
    RespostaUsuario, MetaEstudo, NivelUsuario,
)



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403
from ._todos import _check_pode_criar_simulado, _dar_xp

@login_required(login_url='account_login')
def simulado_edital(request):
    """
    Simulado por Edital: lista editais oficiais de concursos com distribuição fixa.
    GET  → mostra cards de editais disponíveis (PRF, INSS, PF, ENEM, TJ-DF…)
    POST → recebe edital_id e gera simulado conforme a distribuição oficial
    """
    # Mapa: nome de categoria (case-insensitive) → Categoria object (com qtd)
    cats_qs = Categoria.objects.annotate(qtd=Count('questao', filter=Q(
        questao__revisada=True, questao__rejeitada_definitiva=False,
    ))).filter(qtd__gt=0)
    cat_por_nome = {c.nome.lower(): c for c in cats_qs}

    # Para cada edital, calcula quantas questões REAIS podem ser geradas
    editais_disponiveis = []
    for edital in EDITAIS_OFICIAIS:
        cobertas = []
        nao_cobertas = []
        total_real = 0
        for disc, qtd in edital['distribuicao'].items():
            cat = cat_por_nome.get(disc.lower())
            if cat:
                disponivel = min(qtd, cat.qtd)
                cobertas.append({'nome': disc, 'pedido': qtd, 'disponivel': disponivel, 'max': cat.qtd})
                total_real += disponivel
            else:
                nao_cobertas.append({'nome': disc, 'pedido': qtd})

        editais_disponiveis.append({
            **edital,
            'cobertas':      cobertas,
            'nao_cobertas':  nao_cobertas,
            'total_real':    total_real,
            'cobertura_pct': round(total_real / edital['total'] * 100) if edital['total'] else 0,
        })

    if request.method == 'POST':
        resp = _check_pode_criar_simulado(request, fallback_url='simulado_edital')
        if resp: return resp

        edital_id = request.POST.get('edital_id', '')
        edital = next((e for e in EDITAIS_OFICIAIS if e['id'] == edital_id), None)
        if not edital:
            messages.error(request, 'Edital inválido.')
            return redirect('simulado_edital')

        # Monta lista de questões conforme distribuição
        questoes_selecionadas = []
        import random
        for disc, qtd in edital['distribuicao'].items():
            cat = cat_por_nome.get(disc.lower())
            if not cat:
                continue
            disponivel = min(qtd, cat.qtd)
            qs = list(Questao.objects.filter(
                categoria_id=cat.id, revisada=True, rejeitada_definitiva=False,
            ).order_by('?')[:disponivel])
            questoes_selecionadas.extend(qs)

        if len(questoes_selecionadas) < 5:
            messages.error(request, 'Banco insuficiente para gerar este edital. Cadastre mais questões.')
            return redirect('simulado_edital')

        random.shuffle(questoes_selecionadas)

        simulado = Simulado.objects.create(
            usuario=request.user,
            duracao_segundos=edital['duracao_min'] * 60,
        )
        request.session[f'simulado_{simulado.id}_edital'] = edital['nome']

        RespostaSimulado.objects.bulk_create([
            RespostaSimulado(simulado=simulado, questao=q, ordem=i + 1)
            for i, q in enumerate(questoes_selecionadas)
        ])

        # Aviso claro se o banco nao cobre 100% da distribuicao do edital
        pedido_total = edital.get('total', 0)
        entregue = len(questoes_selecionadas)
        if pedido_total and entregue < pedido_total:
            cobertura_pct = round(entregue / pedido_total * 100)
            messages.warning(
                request,
                f'Simulado "{edital["nome"]}" criado com {entregue} de {pedido_total} '
                f'questoes ({cobertura_pct}% de cobertura). O banco ainda nao tem cobertura '
                f'completa desse edital — algumas disciplinas foram reduzidas.'
            )
        else:
            messages.success(request, f'Simulado "{edital["nome"]}" criado com {entregue} questões.')
        return redirect('simulado_questao', simulado_id=simulado.id, numero=1)

    return render(request, 'quiz/simulado_edital.html', {
        'editais':         editais_disponiveis,
        'total_categorias': cats_qs.count(),
    })

@login_required(login_url='account_login')
def iniciar_simulado(request):
    if request.method != 'POST':
        return redirect('escolher_tema')

    resp = _check_pode_criar_simulado(request)
    if resp: return resp

    # Sorteio considera apenas questões revisadas (geradas por IA ainda não aprovadas ficam de fora)
    pool_pub = Questao.objects.filter(revisada=True)
    total_disponivel = pool_pub.count()
    qtd = min(Simulado.TOTAL_QUESTOES, total_disponivel)
    if qtd == 0:
        return redirect('escolher_tema')

    questoes = list(pool_pub.order_by('?')[:qtd])

    simulado = Simulado.objects.create(usuario=request.user)
    RespostaSimulado.objects.bulk_create([
        RespostaSimulado(simulado=simulado, questao=q, ordem=i + 1)
        for i, q in enumerate(questoes)
    ])

    return redirect('simulado_questao', simulado_id=simulado.id, numero=1)

@login_required(login_url='account_login')
@transaction.atomic
def simulado_questao(request, simulado_id, numero):
    simulado = Simulado.objects.select_for_update().filter(id=simulado_id, usuario=request.user).first()
    if not simulado:
        return redirect('escolher_tema')

    if simulado.finalizado or simulado.segundos_restantes() == 0:
        if not simulado.finalizado:
            simulado.finalizado = True
            simulado.finalizado_em = timezone.now()
            simulado.save()
        return redirect('simulado_resultado', simulado_id=simulado.id)

    respostas = list(simulado.respostas.select_related('questao', 'alternativa_escolhida'))
    total = len(respostas)

    if numero < 1 or numero > total:
        return redirect('simulado_questao', simulado_id=simulado.id, numero=1)

    resposta_atual = respostas[numero - 1]
    questao = resposta_atual.questao
    alternativas = questao.alternativa_set.all()

    if request.method == 'POST':
        alt_id = request.POST.get('alternativa_id', '').strip()
        if alt_id and not (alt_id.isascii() and alt_id.isdecimal() and len(alt_id) <= 18):
            messages.error(request, 'Selecione uma alternativa válida para esta questão.')
            return redirect('simulado_questao', simulado_id=simulado.id, numero=numero)
        primeira_resposta = resposta_atual.alternativa_escolhida is None
        if alt_id:
            try:
                alternativa = Alternativa.objects.get(id=alt_id, questao=questao)
                resposta_atual.alternativa_escolhida = alternativa
                resposta_atual.acertou = alternativa.correta
                resposta_atual.save()

                # Gamificacao: streak/XP/SRS/conquistas so na 1a resposta
                # (evita farm via trocar-resposta N vezes na mesma questao).
                if primeira_resposta and simulado.modo != 'prova_real':
                    try:
                        with transaction.atomic():
                            meta, _ = MetaEstudo.objects.get_or_create(usuario=request.user)
                            meta.atualizar_streak()
                            srs, _ = RevisaoEspacada.objects.get_or_create(
                                usuario=request.user, questao=questao,
                                defaults={'proxima_revisao': timezone.localdate()},
                            )
                            srs.atualizar(alternativa.correta)
                            if alternativa.correta:
                                _dar_xp(request.user, 10, request.session)
                            novas = verificar_conquistas(request.user)
                            if novas:
                                request.session['novas_conquistas'] = novas
                    except Exception:
                        import logging
                        logging.getLogger(__name__).exception("Falha na gamificação do simulado %s", simulado.pk)
            except Alternativa.DoesNotExist:
                messages.error(request, 'Selecione uma alternativa válida para esta questão.')
                return redirect('simulado_questao', simulado_id=simulado.id, numero=numero)

        acao = request.POST.get('acao', 'proxima')
        if acao == 'finalizar':
            # Chama a view finalizar direto (request.method eh POST, passa
            # pelo @require_POST). Retorna o redirect pra resultado.
            return finalizar_simulado(request, simulado.id)
        proximo = numero + 1 if numero < total else numero
        return redirect('simulado_questao', simulado_id=simulado.id, numero=proximo)

    respondidas_ids = {r.ordem for r in respostas if r.alternativa_escolhida_id}
    letras = 'ABCDE'

    return render(request, 'quiz/simulado_questao.html', {
        'simulado': simulado,
        'questao': questao,
        'alternativas': alternativas,
        'letras': letras,
        'numero': numero,
        'total': total,
        'respostas': respostas,
        'respondidas_ids': respondidas_ids,
        'resposta_atual': resposta_atual,
        'segundos_restantes': simulado.segundos_restantes(),
        'anterior': numero - 1 if numero > 1 else None,
        'proximo': numero + 1 if numero < total else None,
    })

@login_required(login_url='account_login')
@require_POST
def finalizar_simulado(request, simulado_id):
    """Finaliza simulado. Somente POST (evita CSRF via <img src=/finalizar/>).
    Usa select_for_update pra evitar race no XP quando F5 duplo ou timer-JS
    dispara em paralelo."""
    from django.utils import timezone
    from django.db import transaction as _tx

    with _tx.atomic():
        simulado = (Simulado.objects
                    .select_for_update()
                    .filter(id=simulado_id, usuario=request.user)
                    .first())
        if simulado and not simulado.finalizado:
            simulado.finalizado = True
            simulado.finalizado_em = timezone.now()
            simulado.save(update_fields=['finalizado', 'finalizado_em'])
            _dar_xp(request.user, 50, request.session)  # so 1x graças ao lock
    return redirect('simulado_resultado', simulado_id=simulado_id)

@login_required(login_url='account_login')
def simulado_resultado(request, simulado_id):
    simulado = Simulado.objects.filter(id=simulado_id, usuario=request.user).first()
    if not simulado:
        return redirect('escolher_tema')

    # prefetch_related pra evitar N+1: template itera alternativa_set por questao
    respostas = simulado.respostas.select_related(
        'questao__categoria', 'alternativa_escolhida',
    ).prefetch_related('questao__alternativa_set')
    respondidas = [r for r in respostas if r.acertou is not None]
    acertos = sum(1 for r in respondidas if r.acertou)
    total_respondidas = len(respondidas)
    total = respostas.count()

    aproveitamento = round((acertos / total_respondidas * 100), 1) if total_respondidas else 0

    # Breakdown por categoria
    categorias_dict = {}
    for r in respostas:
        cat = r.questao.categoria.nome
        if cat not in categorias_dict:
            categorias_dict[cat] = {'total': 0, 'respondidas': 0, 'acertos': 0}
        categorias_dict[cat]['total'] += 1
        if r.acertou is not None:
            categorias_dict[cat]['respondidas'] += 1
            if r.acertou:
                categorias_dict[cat]['acertos'] += 1

    # Tempo gasto
    if simulado.finalizado_em:
        tempo_seg = int((simulado.finalizado_em - simulado.iniciado_em).total_seconds())
    else:
        tempo_seg = Simulado.DURACAO_SEGUNDOS
    horas = tempo_seg // 3600
    minutos = (tempo_seg % 3600) // 60
    segundos = tempo_seg % 60
    tempo_formatado = f'{horas:02d}:{minutos:02d}:{segundos:02d}'

    em_branco = total - total_respondidas

    # ── CESPE: estatísticas específicas ──────────────────────────────────
    respostas_ce = [r for r in respostas if r.questao.tipo == 'CE']
    total_ce     = len(respostas_ce)
    acertos_ce   = sum(1 for r in respostas_ce if r.acertou)
    erros_ce     = sum(1 for r in respostas_ce if r.acertou is not None and not r.acertou)
    brancos_ce   = sum(1 for r in respostas_ce if r.acertou is None)
    # Pontuação CESPE com penalidade: certo=+1, errado=-0.5, branco=0
    pontuacao_penalidade = round(acertos_ce - erros_ce * 0.5, 1) if total_ce else None

    return render(request, 'quiz/simulado_resultado.html', {
        'simulado': simulado,
        'acertos': acertos,
        'total': total,
        'total_respondidas': total_respondidas,
        'em_branco': em_branco,
        'aproveitamento': aproveitamento,
        'categorias': categorias_dict,
        'tempo_formatado': tempo_formatado,
        'respostas': respostas,
        # CESPE
        'total_ce': total_ce,
        'acertos_ce': acertos_ce,
        'erros_ce': erros_ce,
        'brancos_ce': brancos_ce,
        'pontuacao_penalidade': pontuacao_penalidade,
    })

@login_required(login_url='account_login')
def historico_simulados(request):
    simulados = (
        Simulado.objects
        .filter(usuario=request.user, finalizado=True)
        .prefetch_related('respostas')
        .order_by('-finalizado_em')
    )
    dados = []
    for s in simulados:
        respostas = s.respostas.all()
        respondidas = [r for r in respostas if r.acertou is not None]
        acertos = sum(1 for r in respondidas if r.acertou)
        total = respostas.count()
        n_resp = len(respondidas)
        pct = round(acertos / n_resp * 100, 1) if n_resp else 0
        if s.finalizado_em:
            seg = int((s.finalizado_em - s.iniciado_em).total_seconds())
        else:
            seg = 0
        dados.append({
            'simulado': s,
            'acertos': acertos,
            'total': total,
            'respondidas': n_resp,
            'aproveitamento': pct,
            'tempo': f'{seg//3600:02d}:{(seg%3600)//60:02d}:{seg%60:02d}',
        })
    return render(request, 'quiz/historico_simulados.html', {'dados': dados})

@login_required(login_url='account_login')
def analytics(request):
    respostas = RespostaUsuario.objects.filter(usuario=request.user)
    total = respostas.count()
    acertos = respostas.filter(acertou=True).count()
    aproveitamento = round(acertos / total * 100, 1) if total else 0

    # Por categoria
    categorias_stats = []
    for cat in Categoria.objects.all().order_by('nome'):
        r = respostas.filter(questao__categoria=cat)
        t = r.count()
        if t == 0:
            continue
        a = r.filter(acertou=True).count()
        categorias_stats.append({
            'nome': cat.nome,
            'total': t,
            'acertos': a,
            'erros': t - a,
            'pct': round(a / t * 100),
        })
    categorias_stats.sort(key=lambda x: x['pct'], reverse=True)

    # Atividade diária (últimos 30 dias)
    trinta_dias = timezone.now() - timedelta(days=30)
    atividade = (
        respostas.filter(data__gte=trinta_dias)
        .annotate(dia=TruncDate('data'))
        .values('dia')
        .annotate(total=Count('id'), acertos=Count('id', filter=Q(acertou=True)))
        .order_by('dia')
    )
    # Constrói série contínua de 30 dias
    dias_map = {item['dia']: item for item in atividade}
    serie_dias = []
    for i in range(29, -1, -1):
        d = (timezone.now() - timedelta(days=i)).date()
        item = dias_map.get(d, {'total': 0, 'acertos': 0})
        serie_dias.append({'dia': d.strftime('%d/%m'), 'total': item['total'], 'acertos': item['acertos']})

    # Evolução semanal (últimas 8 semanas)
    oito_semanas = timezone.now() - timedelta(weeks=8)
    semanal = (
        respostas.filter(data__gte=oito_semanas)
        .annotate(semana=TruncWeek('data'))
        .values('semana')
        .annotate(total=Count('id'), acertos=Count('id', filter=Q(acertou=True)))
        .order_by('semana')
    )

    # Meta e streak
    meta, _ = MetaEstudo.objects.get_or_create(usuario=request.user)
    hoje = timezone.localdate()
    questoes_hoje = respostas.filter(data__date=hoje).count()

    # Questões mais erradas (caderno de erros resumido)
    mais_erradas = (
        respostas.filter(acertou=False)
        .values('questao__categoria__nome')
        .annotate(erros=Count('id'))
        .order_by('-erros')[:5]
    )

    # ── Sessões de estudo ──────────────────────────────────────────────────
    sessoes = SessaoEstudo.objects.filter(usuario=request.user)
    total_sessoes = sessoes.count()
    agg_sessoes = sessoes.aggregate(
        total_seg=Sum('duracao_seg'),
        media_seg=Avg('duracao_seg'),
    )
    total_minutos = round((agg_sessoes['total_seg'] or 0) / 60)
    media_minutos = round((agg_sessoes['media_seg'] or 0) / 60)

    # Tempo diário (últimos 30 dias) em minutos
    sessoes_30d = (
        sessoes.filter(iniciada_em__gte=trinta_dias)
        .annotate(dia=TruncDate('iniciada_em'))
        .values('dia')
        .annotate(minutos=Sum('duracao_seg'))
        .order_by('dia')
    )
    dias_sess_map = {item['dia']: item['minutos'] for item in sessoes_30d}
    serie_tempo = []
    for i in range(29, -1, -1):
        d = (timezone.now() - timedelta(days=i)).date()
        serie_tempo.append({'dia': d.strftime('%d/%m'), 'minutos': round((dias_sess_map.get(d) or 0) / 60, 1)})

    import json as _json
    return render(request, 'quiz/analytics.html', {
        'total': total,
        'acertos': acertos,
        'aproveitamento': aproveitamento,
        'categorias_stats': categorias_stats,
        'serie_dias_json': _json.dumps(serie_dias),
        'semanal_json': _json.dumps([
            {'semana': str(s['semana'])[:10], 'total': s['total'], 'acertos': s['acertos']}
            for s in semanal
        ]),
        'meta': meta,
        'questoes_hoje': questoes_hoje,
        'mais_erradas': list(mais_erradas),
        # sessões
        'total_sessoes': total_sessoes,
        'total_minutos': total_minutos,
        'media_minutos': media_minutos,
        'serie_tempo_json': _json.dumps(serie_tempo),
        # Sprint 16 — XP badge na sidebar
        'nivel_obj': NivelUsuario.objects.get_or_create(usuario=request.user)[0],
    })
