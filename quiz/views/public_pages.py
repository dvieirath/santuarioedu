"""Paginas publicas (landing, home, FAQ, legal) — extraidas de views/_todos.py."""
from django.shortcuts import render, redirect
from django.http import Http404

from ..models import Questao, Simulado, RespostaUsuario, Categoria



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403

def home(request):
    """Landing page pública. Se logado, vai direto pro dashboard."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    # Estatísticas reais pra dar credibilidade na landing
    from ..models import Questao, Categoria, Simulado, RespostaUsuario
    from ..concurso_landing import CONCURSOS_LANDING
    contexto = {
        'total_questoes': Questao.objects.count(),
        'total_disciplinas': Categoria.objects.count(),
        'total_simulados': Simulado.objects.filter(finalizado=True).count(),
        'total_respostas': RespostaUsuario.objects.count(),
        'concursos_landing': CONCURSOS_LANDING,
    }
    return render(request, 'landing.html', contexto)

def landing_concurso(request, slug):
    """
    Landing SEO por concurso — /concurso/<slug>/
    Cada slug otimizado pra keyword especifica (concurso PRF, INSS, etc.).
    Redireciona logado pro dashboard (mesmo comportamento da home).
    """
    from ..concurso_landing import CONCURSOS_LANDING
    from django.http import Http404
    from ..models import Questao, Categoria

    if request.user.is_authenticated:
        return redirect('dashboard')

    if slug not in CONCURSOS_LANDING:
        raise Http404('Concurso nao encontrado')

    config = CONCURSOS_LANDING[slug]

    # Contagem de questoes relevantes ao concurso: prioriza disciplinas listadas
    # (match no nome da categoria raiz). Fallback: contagem total.
    from django.db.models import Q
    disc_q = Q()
    for d in config['disciplinas']:
        disc_q |= Q(categoria__nome__icontains=d)
        disc_q |= Q(categoria__parent__nome__icontains=d)
    total_questoes_concurso = Questao.objects.filter(disc_q).distinct().count()
    total_geral = Questao.objects.count()

    return render(request, 'landing_concurso.html', {
        'config':              config,
        'slug':                slug,
        'total_questoes':      total_questoes_concurso or total_geral,
        'total_geral':         total_geral,
        'concursos_landing':   CONCURSOS_LANDING,
    })

def cadastro(request):
    """Rota antiga /cadastro/ — redireciona pro fluxo unificado do allauth
    (/accounts/signup/) que ja tem email obrigatorio + verificacao por codigo."""
    from django.shortcuts import redirect as _redirect
    return _redirect('account_signup', permanent=False)

def politica_privacidade(request):
    """Página pública: Política de Privacidade (LGPD)."""
    return render(request, 'legal/privacidade.html')

def termos_uso(request):
    """Página pública: Termos de Uso."""
    return render(request, 'legal/termos.html')

def faq(request):
    """Página pública: Perguntas frequentes."""
    return render(request, 'faq.html')

def sobre(request):
    """Pagina publica: sobre nos, missao, valores."""
    from ..models import Questao, Simulado, RespostaUsuario
    from django.contrib.auth import get_user_model
    User = get_user_model()

    ctx = {
        'total_questoes':   Questao.objects.filter(revisada=True).count(),
        'total_users':      User.objects.count(),
        'total_respostas':  RespostaUsuario.objects.count(),
        'total_simulados':  Simulado.objects.filter(finalizado=True).count(),
    }
    return render(request, 'sobre.html', ctx)
