"""APIs gerais — search, proxima acao, notificacoes — extraidas de views/_todos.py."""
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from django.http import JsonResponse

from ..models import Notificacao, Categoria, Questao



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403
from ._todos import _silencioso

@login_required
@ratelimit(key='user', rate='30/m', method='GET', block=True)
def api_search_global(request):
    """
    Busca global: consulta categorias, questões e resumos IA.
    Rate limit: 30 buscas/min (evita scrape).
    Retorna JSON com até 15 hits ordenados por relevância implícita
    (categoria > resumo > questão).
    """
    q = (request.GET.get('q') or '').strip()
    if len(q) < 2:
        return JsonResponse({'hits': [], 'query': q})

    hits = []

    for c in Categoria.objects.filter(nome__icontains=q)[:5]:
        hits.append({
            'tipo':  'disciplina',
            'label': c.nome,
            'sub':   'Disciplina',
            'url':   f'/quiz/{c.id}/',
            'icon':  'menu_book',
        })

    resumos = ResumoIA.objects.filter(
        Q(categoria__nome__icontains=q) | Q(conteudo__icontains=q)
    ).select_related('categoria')[:4]
    for r in resumos:
        hits.append({
            'tipo':  'resumo',
            'label': f'Resumo — {r.categoria.nome}',
            'sub':   'Resumo IA',
            'url':   f'/resumos/{r.categoria.id}/',
            'icon':  'auto_stories',
        })

    remaining = max(0, 15 - len(hits))
    if remaining:
        qns = Questao.objects.filter(
            Q(texto__icontains=q) | Q(assunto__icontains=q)
        ).select_related('categoria')[:remaining]
        for qn in qns:
            texto_preview = (qn.texto or '')[:90]
            if len(qn.texto or '') > 90:
                texto_preview += '…'
            sub = qn.categoria.nome + ((' · ' + qn.assunto) if qn.assunto else '')
            hits.append({
                'tipo':  'questao',
                'label': texto_preview,
                'sub':   sub,
                'url':   f'/quiz/{qn.categoria_id}/?questao={qn.id}',
                'icon':  'help',
            })

    return JsonResponse({'hits': hits, 'query': q, 'total': len(hits)})

@login_required
def api_proxima_acao(request):
    """
    Retorna a "próxima ação" mais valiosa para o usuário agora.
    Ordem de prioridade (primeiro que matchar vence):
      1. Metas semanais expiram em <= 2 dias e ainda não bateram
      2. Nunca respondeu nada -> sugerir escolher tema
      3. Streak em risco (última atividade > 20h)
      4. Disciplina fraca (aproveitamento < 50% nas últimas 30 respostas)
      5. Padrão: reforçar erros ou aleatório
    """
    user = request.user
    hoje = timezone.localdate()
    agora = timezone.now()

    respostas = RespostaUsuario.objects.filter(usuario=user)
    total_resp = respostas.count()

    try:
        metas = MetaAvancada.objects.filter(
            usuario=user, ativa=True, periodo='semanal', fim__gte=hoje,
        ).order_by('fim')
        for m in metas:
            dias_restantes = (m.fim - hoje).days
            if dias_restantes <= 2:
                r_cnt = respostas.filter(
                    data__date__gte=m.inicio, data__date__lte=m.fim
                ).count()
                if r_cnt < m.questoes_alvo:
                    faltam = m.questoes_alvo - r_cnt
                    return JsonResponse({
                        'titulo': 'Meta semanal em risco',
                        'descricao': f'Faltam {faltam} questões pra bater a meta ({dias_restantes} dia(s) restantes).',
                        'cta_label': 'Estudar agora',
                        'cta_url':   '/quiz/?modo=todas',
                        'prioridade': 'alta',
                        'icone': 'flag',
                    })
    except Exception:
        _silencioso("view_bloco_17")
    if total_resp == 0:
        return JsonResponse({
            'titulo': 'Comece por uma disciplina',
            'descricao': 'Você ainda não respondeu nenhuma questão. Escolha um tema pra começar.',
            'cta_label': 'Escolher tema',
            'cta_url':   '/estudar/',  # era /temas/ (404 — URL nao existe)
            'prioridade': 'media',
            'icone': 'menu_book',
        })

    ultima = respostas.order_by('-data').values_list('data', flat=True).first()
    if ultima:
        horas_desde = (agora - ultima).total_seconds() / 3600
        if 20 <= horas_desde <= 30:
            return JsonResponse({
                'titulo': 'Streak em risco',
                'descricao': 'Faltam poucas horas pra você perder seu streak. Uma questão já mantém.',
                'cta_label': 'Responder 1 questão',
                'cta_url':   '/questao-do-dia/',
                'prioridade': 'alta',
                'icone': 'local_fire_department',
            })
        if horas_desde > 72:
            dias = int(horas_desde / 24)
            return JsonResponse({
                'titulo': 'Volta pro ritmo',
                'descricao': f'Você não estuda há {dias} dia(s). Comece com só 5 questões.',
                'cta_label': 'Reaquecer',
                'cta_url':   '/quiz/?modo=todas',
                'prioridade': 'media',
                'icone': 'wb_sunny',
            })

    ultimas = list(respostas.order_by('-data')[:30].select_related('questao__categoria'))
    por_cat = {}
    for r in ultimas:
        cid = r.questao.categoria_id
        d = por_cat.setdefault(cid, {'total': 0, 'acertos': 0, 'nome': r.questao.categoria.nome})
        d['total'] += 1
        if r.acertou:
            d['acertos'] += 1
    fraca = None
    for cid, d in por_cat.items():
        if d['total'] >= 5:
            pct = round(d['acertos'] / d['total'] * 100)
            if pct < 50 and (fraca is None or pct < fraca['pct']):
                fraca = {'cid': cid, 'pct': pct, 'nome': d['nome']}
    if fraca:
        return JsonResponse({
            'titulo': f'Sua taxa em {fraca["nome"]} caiu',
            'descricao': f'Só {fraca["pct"]}% de acertos nas últimas questões. Vale reforçar.',
            'cta_label': f'Treinar {fraca["nome"]}',
            'cta_url':   f'/quiz/{fraca["cid"]}/',
            'prioridade': 'media',
            'icone': 'trending_down',
        })

    tem_erros = respostas.filter(acertou=False).exists()
    if tem_erros:
        return JsonResponse({
            'titulo': 'Reforce seus erros',
            'descricao': 'Você tem questões erradas no caderno. Bom hábito de revisão.',
            'cta_label': 'Ver caderno de erros',
            'cta_url':   '/caderno-de-erros/',  # era /caderno-erros/ (404 — falta o 'de')
            'prioridade': 'baixa',
            'icone': 'error_outline',
        })

    return JsonResponse({
        'titulo': 'Continue no ritmo',
        'descricao': 'Nada crítico agora. Responda umas questões para manter o streak.',
        'cta_label': 'Aleatórias',
        'cta_url':   '/quiz/?modo=todas',
        'prioridade': 'baixa',
        'icone': 'shuffle',
    })

@login_required(login_url='account_login')
@require_POST
@ratelimit(key='user', rate='60/m', method='POST', block=True)
def api_notificacao_lida(request, notif_id):
    """Marca uma notificação como lida."""
    Notificacao.objects.filter(id=notif_id, usuario=request.user).update(lida=True)
    return JsonResponse({'status': 'ok'})

@login_required(login_url='account_login')
def api_notificacoes_count(request):
    """Retorna contagem de não-lidas para o badge."""
    count = Notificacao.objects.filter(usuario=request.user, lida=False).count()
    return JsonResponse({'count': count})
