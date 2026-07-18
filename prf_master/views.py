"""Views auxiliares do projeto."""
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.db import connection


def health(request):
    """Health check para orquestradores (Railway, Render, K8s).

    Retorna 200 + JSON com status de subsistemas:
      - db: consegue query no banco?
      - cache: consegue set/get?
      - version: hash do commit (se disponível)
    """
    import os as _os
    from django.core.cache import cache

    db_ok = True
    try:
        with connection.cursor() as c:
            c.execute('SELECT 1'); c.fetchone()
    except Exception:
        db_ok = False

    cache_ok = True
    try:
        cache.set('_health_ping', 1, 5)
        cache_ok = cache.get('_health_ping') == 1
    except Exception:
        cache_ok = False

    versao = (
        _os.environ.get('RAILWAY_GIT_COMMIT_SHA', '')
        or _os.environ.get('RENDER_GIT_COMMIT', '')
        or _os.environ.get('SOURCE_COMMIT', '')
    )[:7] or 'dev'

    ok = db_ok and cache_ok
    payload = {
        'status': 'ok' if ok else 'degraded',
        'db': db_ok, 'cache': cache_ok, 'version': versao,
    }
    return JsonResponse(payload, status=200 if ok else 503)


def robots_txt(request):
    """robots.txt — controla crawlers."""
    lines = [
        'User-agent: *',
        'Disallow: /admin/',
        'Disallow: /accounts/',
        'Disallow: /api/',
        'Allow: /',
        '',
        f'Sitemap: {request.scheme}://{request.get_host()}/sitemap.xml',
    ]
    return HttpResponse('\n'.join(lines), content_type='text/plain')


def page_404(request, exception=None):
    return render(request, 'errors/404.html', status=404)


def page_500(request):
    return render(request, 'errors/500.html', status=500)


def page_403(request, exception=None):
    return render(request, 'errors/403.html', status=403)


def ratelimited_view(request, exception=None):
    """Handler chamado pelo django-ratelimit quando o limite é atingido."""
    msg = ('Você atingiu o limite de requisições para este recurso de IA. '
           'Tente novamente em alguns minutos.')
    if request.headers.get('Accept', '').startswith('application/json') or request.path.startswith('/api/'):
        return JsonResponse({'erro': msg, 'codigo': 'ratelimited'}, status=429)
    return render(request, '429.html', {'mensagem': msg}, status=429)
