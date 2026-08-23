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
    from django.core.cache import cache

    # Cache 10min — landing é a rota mais quente e essas queries batem em
    # tabelas grandes. Invalida sozinho.
    stats = cache.get('landing_stats')
    if not stats:
        # Só revisadas contam (não infla banco com pendentes/rejeitadas)
        rev = Questao.objects.filter(revisada=True)
        # Bancas distintas (Cebraspe, FGV, etc) — filtra vazias
        bancas = set(
            rev.exclude(banca__isnull=True).exclude(banca='')
               .values_list('banca', flat=True).distinct()
        )
        # Disciplinas RAIZ (top-level) — não conta sub-sub-categorias
        discs_raiz = Categoria.objects.filter(parent__isnull=True).count()

        stats = {
            'total_questoes':    rev.count(),
            'total_disciplinas': discs_raiz,
            'total_bancas':      len(bancas),
            'total_simulados':   Simulado.objects.filter(finalizado=True).count(),
            'total_respostas':   RespostaUsuario.objects.count(),
            'total_concursos':   len(CONCURSOS_LANDING),
        }
        cache.set('landing_stats', stats, 600)  # 10 min

    return render(request, 'landing.html', {
        **stats,
        'concursos_landing': CONCURSOS_LANDING,
    })

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

    # Usa o mesmo pipeline de _match_categoria da preparacao (accent-insensitive)
    # pra contar questões RELEVANTES + REVISADAS do concurso — nao infla com
    # pendentes ou rejeitadas.
    from ..preparacao import _match_categoria, CONCURSO_DISCIPLINAS
    from django.core.cache import cache

    cache_key = f'landing_concurso_stats:{slug}'
    stats = cache.get(cache_key)
    if not stats:
        disc_alvo = CONCURSO_DISCIPLINAS.get(slug, config.get('disciplinas', []))
        ids_disc = set()
        breakdown = []
        for d in disc_alvo:
            cats = _match_categoria(d)
            ids_d = set()
            for c in cats:
                ids_d.update(c.subarvore_ids())
            n = Questao.objects.filter(
                categoria_id__in=ids_d, revisada=True
            ).count()
            if n:
                breakdown.append({'disciplina': d, 'total': n})
            ids_disc.update(ids_d)
        total_concurso = Questao.objects.filter(
            categoria_id__in=ids_disc, revisada=True
        ).count()
        breakdown.sort(key=lambda x: -x['total'])

        # Bancas cobertas nesse concurso
        bancas = set(Questao.objects.filter(
            categoria_id__in=ids_disc, revisada=True,
        ).exclude(banca__isnull=True).exclude(banca='').values_list('banca', flat=True))

        total_geral = Questao.objects.filter(revisada=True).count()
        stats = {
            'total_questoes':   total_concurso or total_geral,
            'total_geral':      total_geral,
            'breakdown_disc':   breakdown,
            'total_bancas':     len(bancas),
            'lista_bancas':     sorted(bancas)[:5],
        }
        cache.set(cache_key, stats, 600)

    return render(request, 'landing_concurso.html', {
        'config':              config,
        'slug':                slug,
        'concursos_landing':   CONCURSOS_LANDING,
        **stats,
    })

def banco_publico(request):
    """
    /banco/ — página pública mostrando composição do banco de questões
    (concursos, disciplinas, bancas). SEO + prova social pra usuários
    não-logados. Cachea 15min.
    """
    from ..concurso_landing import CONCURSOS_LANDING
    from ..preparacao import _match_categoria, CONCURSO_DISCIPLINAS
    from django.core.cache import cache

    stats = cache.get('banco_publico:v1')
    if not stats:
        rev = Questao.objects.filter(revisada=True)
        total = rev.count()

        # Por concurso
        por_concurso = []
        for slug, cfg in CONCURSOS_LANDING.items():
            ids = set()
            for d in CONCURSO_DISCIPLINAS.get(slug, cfg.get('disciplinas', [])):
                cats = _match_categoria(d)
                for c in cats:
                    ids.update(c.subarvore_ids())
            n = rev.filter(categoria_id__in=ids).count() if ids else 0
            if n:
                por_concurso.append({
                    'slug': slug, 'nome': cfg.get('nome_completo', cfg.get('nome')),
                    'nome_curto': cfg.get('nome'),
                    'total': n,
                    'palavra_chave': cfg.get('palavra_chave', ''),
                })
        por_concurso.sort(key=lambda x: -x['total'])

        # Por banca
        bancas = {}
        for row in rev.exclude(banca__isnull=True).exclude(banca='').values('banca'):
            b = row['banca']
            bancas[b] = bancas.get(b, 0) + 1
        top_bancas = sorted(
            [{'nome': b, 'total': n} for b, n in bancas.items()],
            key=lambda x: -x['total']
        )[:8]

        # Por disciplina raiz (top-level)
        top_disciplinas = []
        for cat in Categoria.objects.filter(parent__isnull=True):
            ids = cat.subarvore_ids()
            n = rev.filter(categoria_id__in=ids).count()
            if n:
                top_disciplinas.append({'nome': cat.nome, 'total': n, 'id': cat.id})
        top_disciplinas.sort(key=lambda x: -x['total'])
        top_disciplinas = top_disciplinas[:10]

        # Por ano
        anos = {}
        for row in rev.exclude(ano__isnull=True).values('ano'):
            a = row['ano']
            anos[a] = anos.get(a, 0) + 1
        por_ano = sorted(
            [{'ano': a, 'total': n} for a, n in anos.items()],
            key=lambda x: -x['ano']
        )[:10]

        stats = {
            'total':           total,
            'por_concurso':    por_concurso,
            'top_bancas':      top_bancas,
            'top_disciplinas': top_disciplinas,
            'por_ano':         por_ano,
        }
        cache.set('banco_publico:v1', stats, 900)  # 15 min

    return render(request, 'quiz/banco_publico.html', stats)


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
