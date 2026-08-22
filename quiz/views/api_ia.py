"""APIs de IA — tutor, insight, analise — extraidas de views/_todos.py."""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from django.http import JsonResponse

from ..models import Questao, Categoria, ConcursoPreferido



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403

@login_required(login_url='account_login')
@require_POST
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def api_tutor_ia(request):
    """
    Endpoint AJAX para o Tutor IA.
    Body JSON: { "pergunta": "...", "questao_id": 123 (opcional) }
    """
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'erro': 'JSON inválido'}, status=400)

    pergunta = data.get('pergunta', '').strip()
    if not pergunta:
        return JsonResponse({'erro': 'Pergunta vazia'}, status=400)

    # Contexto opcional: texto da questão referenciada
    questao_id = data.get('questao_id')
    contexto_questao = ''
    if questao_id:
        try:
            q = Questao.objects.get(id=questao_id)
            alts = q.alternativa_set.all()
            alts_txt = '\n'.join(
                f"{'✓' if a.correta else '  '} {a.texto}" for a in alts
            )
            contexto_questao = f"Disciplina: {q.categoria}\nQuestão: {q.texto}\nAlternativas:\n{alts_txt}"
        except Questao.DoesNotExist:
            pass

    resposta = ai_tutor_responder(pergunta, contexto_questao, usuario=request.user)
    return JsonResponse({'resposta': resposta})

@login_required
@require_POST
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def api_insight_banca(request):
    """Gera insight tático via IA para uma banca específica."""
    import json as _json
    try:
        body  = _json.loads(request.body)
        banca = body.get('banca', '').strip()
    except Exception:
        return JsonResponse({'erro': 'JSON inválido'}, status=400)

    if not banca:
        return JsonResponse({'erro': 'Banca não informada'}, status=400)

    respostas = RespostaUsuario.objects.filter(
        usuario=request.user, questao__banca=banca
    )
    total = respostas.count()
    if total == 0:
        return JsonResponse({'erro': 'Sem dados para esta banca'}, status=400)

    acertos = respostas.filter(acertou=True).count()
    pct     = round(acertos / total * 100)

    cats_qs = (
        respostas
        .values('questao__categoria__nome')
        .annotate(
            ct=Count('id'),
            ca=Count('id', filter=Q(acertou=True)),
        )
        .filter(ct__gte=3)
        .annotate(pct_cat=Cast(F('ca') * 100, output_field=models.FloatField()) / Cast(F('ct'), output_field=models.FloatField()))
        .order_by('pct_cat')
    )
    cats_list = list(cats_qs)
    pior_cat   = cats_list[0]['questao__categoria__nome']   if cats_list else ''
    melhor_cat = cats_list[-1]['questao__categoria__nome']  if cats_list else ''

    texto = ai_insight_banca(banca, total, pct, pior_cat, melhor_cat, usuario=request.user)
    return JsonResponse({'insight': texto})

@login_required(login_url='account_login')
@ratelimit(key='user', rate='10/h', method='GET', block=True)
def analise_banca(request):
    """Sprint 21 — Dashboard preditivo de banca: breakdown por disciplina,
    tendência semanal e insights IA por banca."""
    import json as _json
    from datetime import timedelta as td

    respostas = RespostaUsuario.objects.filter(usuario=request.user)
    hoje = timezone.localdate()

    # ── Por banca (com breakdown por categoria) ──────────────────────────────
    bancas_qs = (
        respostas
        .filter(questao__banca__isnull=False)
        .exclude(questao__banca='')
        .values('questao__banca')
        .annotate(
            total=Count('id'),
            acertos=Count('id', filter=Q(acertou=True)),
        )
        .order_by('-total')
    )

    bancas = []
    for b in bancas_qs:
        total = b['total']
        acert = b['acertos']
        pct   = round(acert / total * 100) if total else 0

        # Breakdown por categoria dentro desta banca
        cats_qs = (
            respostas
            .filter(questao__banca=b['questao__banca'])
            .values('questao__categoria__nome')
            .annotate(
                cat_total=Count('id'),
                cat_acertos=Count('id', filter=Q(acertou=True)),
            )
            .order_by('-cat_total')
        )
        cats = []
        for c in cats_qs:
            ct = c['cat_total']
            ca = c['cat_acertos']
            cats.append({
                'nome':    c['questao__categoria__nome'] or 'Sem categoria',
                'total':   ct,
                'acertos': ca,
                'erros':   ct - ca,
                'pct':     round(ca / ct * 100) if ct else 0,
            })

        pior_cat   = min(cats, key=lambda x: x['pct'])['nome'] if cats else ''
        melhor_cat = max(cats, key=lambda x: x['pct'])['nome'] if cats else ''

        bancas.append({
            'banca':      b['questao__banca'],
            'total':      total,
            'acertos':    acert,
            'erros':      total - acert,
            'pct':        pct,
            'cats':       cats,
            'pior_cat':   pior_cat,
            'melhor_cat': melhor_cat,
        })

    # ── Tendência semanal (últimas 8 semanas) ────────────────────────────────
    tendencia = []
    for w in range(7, -1, -1):
        semana_ini = hoje - td(days=hoje.weekday() + 7 * w)
        semana_fim = semana_ini + td(days=6)
        rs = respostas.filter(data__date__gte=semana_ini, data__date__lte=semana_fim)
        t  = rs.count()
        a  = rs.filter(acertou=True).count()
        tendencia.append({
            'label': semana_ini.strftime('%d/%m'),
            'total': t,
            'acertos': a,
            'pct': round(a / t * 100) if t else 0,
        })

    # ── Por ano ──────────────────────────────────────────────────────────────
    anos_qs = (
        respostas
        .filter(questao__ano__isnull=False)
        .values('questao__ano')
        .annotate(
            total=Count('id'),
            acertos=Count('id', filter=Q(acertou=True)),
        )
        .order_by('questao__ano')
    )
    anos = [
        {
            'ano':     a['questao__ano'],
            'total':   a['total'],
            'acertos': a['acertos'],
            'pct':     round(a['acertos'] / a['total'] * 100) if a['total'] else 0,
        }
        for a in anos_qs
    ]

    sem_banca = respostas.filter(
        Q(questao__banca__isnull=True) | Q(questao__banca='')
    ).count()

    # Banca com melhor e pior aproveitamento (para destaque)
    banca_top   = max(bancas, key=lambda x: x['pct']) if bancas else None
    banca_fraca = min(bancas, key=lambda x: x['pct']) if bancas else None

    return render(request, 'quiz/analise_banca.html', {
        'bancas':            bancas,
        'anos':              anos,
        'tendencia':         tendencia,
        'bancas_json':       _json.dumps(bancas),
        'anos_json':         _json.dumps(anos),
        'tendencia_json':    _json.dumps(tendencia),
        'sem_banca':         sem_banca,
        'total_respondidas': respostas.count(),
        'banca_top':         banca_top,
        'banca_fraca':       banca_fraca,
    })
