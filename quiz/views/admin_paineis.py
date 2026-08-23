"""Paineis admin (status, metricas fundador) — extraidas de views/_todos.py."""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from ._todos import _is_staff
from ..models import RespostaUsuario, Questao, Simulado, Categoria



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403
from ._todos import _is_staff, _silencioso

@login_required(login_url='account_login')
@user_passes_test(_is_staff, login_url='home')
def admin_status(request):
    """Dashboard interno do fundador: metricas de saude do sistema."""
    from django.contrib.auth import get_user_model
    from django.db.models import Count, Q
    from datetime import timedelta

    User = get_user_model()
    hoje = timezone.now()
    ontem = hoje - timedelta(days=1)
    semana = hoje - timedelta(days=7)
    mes = hoje - timedelta(days=30)

    # Users
    total_users = User.objects.count()
    users_semana = User.objects.filter(date_joined__gte=semana).count()
    users_ativos_semana = RespostaUsuario.objects.filter(
        data__gte=semana
    ).values('usuario').distinct().count()

    # Questoes
    q_total = Questao.objects.count()
    q_revisadas = Questao.objects.filter(revisada=True).count()
    q_pendentes = Questao.objects.filter(revisada=False, rejeitada_definitiva=False).count()
    q_rejeitadas = Questao.objects.filter(rejeitada_definitiva=True).count()
    q_ia = Questao.objects.filter(gerada_por_ia=True).count()

    # Por tipo
    q_me = Questao.objects.filter(revisada=True, tipo='ME').count()
    q_ce = Questao.objects.filter(revisada=True, tipo='CE').count()

    # Atividade
    respostas_hoje = RespostaUsuario.objects.filter(data__gte=ontem).count()
    respostas_semana = RespostaUsuario.objects.filter(data__gte=semana).count()
    simulados_semana = Simulado.objects.filter(iniciado_em__gte=semana).count()

    # Planos
    # PlanoUsuario removido
    pro_ativos = 0
    premium_ativos = 0

    # Top disciplinas com questoes
    top_disc = []
    for cat in Categoria.objects.filter(parent__isnull=True):
        n = Questao.objects.filter(categoria_id__in=cat.subarvore_ids(), revisada=True).count()
        if n > 0:
            top_disc.append({'nome': cat.nome, 'total': n})
    top_disc.sort(key=lambda x: -x['total'])
    top_disc = top_disc[:10]

    # Import em progresso (loop_importar.py)
    import_status = None
    try:
        import json as _json
        with open('provas_pdf/materia_prima/import_progresso.json') as f:
            prog = _json.load(f)
        n_concluidos = len(prog.get('concluidos_idx', []))
        # Le manifesto pra ver total
        try:
            with open('provas_pdf/materia_prima/manifesto.json') as f:
                total_manifesto = len(_json.load(f))
        except Exception:
            total_manifesto = 451  # fallback conhecido
        import_status = {
            'concluidos': n_concluidos,
            'total':      total_manifesto,
            'pct':        round(n_concluidos / total_manifesto * 100) if total_manifesto else 0,
        }
    except Exception:
        _silencioso("view_bloco_18")
    # Erros recentes (LogSistema)
    from ..models import LogSistema
    erros_recentes = LogSistema.objects.filter(nivel='ERRO').order_by('-criado_em')[:5]

    return render(request, 'quiz/admin_status.html', {
        'total_users':          total_users,
        'users_semana':         users_semana,
        'users_ativos_semana':  users_ativos_semana,
        'q_total':              q_total,
        'q_revisadas':          q_revisadas,
        'q_pendentes':          q_pendentes,
        'q_rejeitadas':         q_rejeitadas,
        'q_ia':                 q_ia,
        'q_me':                 q_me,
        'q_ce':                 q_ce,
        'respostas_hoje':       respostas_hoje,
        'respostas_semana':     respostas_semana,
        'simulados_semana':     simulados_semana,
        'pro_ativos':           pro_ativos,
        'premium_ativos':       premium_ativos,
        'top_disc':             top_disc,
        'import_status':        import_status,
        'erros_recentes':       erros_recentes,
    })


@login_required(login_url='account_login')
@user_passes_test(_is_staff, login_url='home')
def admin_ia_metricas(request):
    """
    Painel de métricas dos providers de IA — chamadas, tokens, quota, status.
    Consolida stats_do_dia (hoje) + stats_ultimos_dias (7d histórico) e cruza
    com contagem de questões geradas por IA no banco.
    """
    from ..ai_metrics import stats_do_dia, stats_ultimos_dias, PROVIDERS
    from django.db.models import Count
    from datetime import timedelta

    stats_hoje = stats_do_dia()
    stats_7d   = stats_ultimos_dias(7)

    # Somatório da semana por provider
    total_semana = {p: {'ok': 0, 'tokens': 0, 'quota': 0, 'err': 0}
                    for p in PROVIDERS}
    for dia in stats_7d:
        for p in PROVIDERS:
            v = dia['stats'].get(p, {})
            for k in ('ok', 'tokens', 'quota', 'err'):
                total_semana[p][k] += v.get(k, 0)

    # Cruzamento com banco: questões IA geradas / aprovadas
    ia_no_banco = Questao.objects.filter(gerada_por_ia=True).count()
    ia_aprovadas = Questao.objects.filter(gerada_por_ia=True, revisada=True).count()
    ia_pendentes = Questao.objects.filter(
        gerada_por_ia=True, revisada=False, rejeitada_definitiva=False
    ).count()
    ia_rejeitadas = Questao.objects.filter(
        gerada_por_ia=True, rejeitada_definitiva=True
    ).count()
    pct_aprovacao = round(ia_aprovadas / ia_no_banco * 100, 1) if ia_no_banco else 0

    # Últimas 24h: questões geradas por IA (aproximacao via id)
    ia_24h = 0
    try:
        agora = timezone.now()
        ontem = agora - timedelta(hours=24)
        # RespostaUsuario não tem, mas Questao não tem created_at.
        # Aproximação: pega ultimas N inseridas
        ia_24h = Questao.objects.filter(
            gerada_por_ia=True, id__gte=Questao.objects.latest('id').id - 500
        ).count()
    except Questao.DoesNotExist:
        pass

    # Configuração ativa (order + keys presentes)
    from django.conf import settings
    order_ativo = settings.AI_PROVIDER_ORDER
    keys_status = {
        'groq':       bool(getattr(settings, 'GROQ_API_KEY', '')),
        'gemini':     bool(getattr(settings, 'GEMINI_API_KEY', '')),
        'cerebras':   bool(getattr(settings, 'CEREBRAS_API_KEY', '')),
        'openrouter': bool(getattr(settings, 'OPENROUTER_API_KEY', '')),
    }

    return render(request, 'quiz/admin_ia_metricas.html', {
        'stats_hoje':    stats_hoje,
        'stats_7d':      stats_7d,
        'total_semana':  total_semana,
        'providers':     PROVIDERS,
        'order_ativo':   order_ativo,
        'keys_status':   keys_status,
        'ia_no_banco':   ia_no_banco,
        'ia_aprovadas':  ia_aprovadas,
        'ia_pendentes':  ia_pendentes,
        'ia_rejeitadas': ia_rejeitadas,
        'ia_24h':        ia_24h,
        'pct_aprovacao': pct_aprovacao,
    })
