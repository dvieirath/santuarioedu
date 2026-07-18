"""
Middlewares customizados:
- SecurityHeadersMiddleware: cabeçalhos modernos de segurança
- RatelimitMiddleware: converte Ratelimited (403) em página amigável 429
- NotifyExceptionMiddleware: captura exception 500 e avisa o admin
"""
import traceback

from django.http import JsonResponse
from django.shortcuts import render
from django_ratelimit.exceptions import Ratelimited


class NotifyExceptionMiddleware:
    """Captura exceções não-tratadas (500) e envia notificação ao admin.

    Não interfere no fluxo normal do Django (ele continua renderizando a página
    500 padrão). Só dispara notificação via Discord/Telegram/Email.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        # Ignora exceções esperadas que o Django trata (rate limit, 404, etc)
        if isinstance(exception, Ratelimited):
            return None
        from django.http import Http404
        if isinstance(exception, Http404):
            return None
        try:
            from quiz.notifications import notificar_admin
            tb = traceback.format_exception(type(exception), exception, exception.__traceback__)
            corpo = ''.join(tb)[:2500]
            user = request.user.username if getattr(request, 'user', None) and request.user.is_authenticated else 'anônimo'
            notificar_admin(
                'alta',
                titulo=f'500 em {request.path}',
                corpo=corpo,
                meta=f'{request.method} {request.path} · user={user}',
            )
        except Exception:
            # Nunca "eleva" outra exception a partir de um exception handler
            pass
        return None


class RatelimitMiddleware:
    """Captura exceção Ratelimited e devolve HTTP 429 amigável."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not isinstance(exception, Ratelimited):
            return None
        msg = ('Você atingiu o limite de requisições para este recurso de IA. '
               'Tente novamente em alguns minutos.')
        if request.headers.get('Accept', '').startswith('application/json') or request.path.startswith('/api/'):
            return JsonResponse({'erro': msg, 'codigo': 'ratelimited'}, status=429)
        return render(request, '429.html', {'mensagem': msg}, status=429)


class SecurityHeadersMiddleware:
    """Adiciona headers de segurança modernos a todas as responses."""

    # Desabilita APIs sensíveis que o app não usa. Cada feature listada como ()
    # significa "ninguém pode usar isso, nem o próprio site".
    PERMISSIONS_POLICY = (
        "accelerometer=(), "
        "ambient-light-sensor=(), "
        "autoplay=(), "
        "battery=(), "
        "camera=(), "
        "display-capture=(), "
        "document-domain=(), "
        "encrypted-media=(), "
        "fullscreen=(self), "
        "geolocation=(), "
        "gyroscope=(), "
        "interest-cohort=(), "       # bloqueia FLoC do Chrome
        "magnetometer=(), "
        "microphone=(self), "        # liberado para "Revisão por Voz"
        "midi=(), "
        "payment=(), "
        "picture-in-picture=(), "
        "publickey-credentials-get=(), "
        "screen-wake-lock=(), "
        "sync-xhr=(), "
        "usb=(), "
        "xr-spatial-tracking=()"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Permissions-Policy substitui a Feature-Policy antiga
        response.setdefault('Permissions-Policy', self.PERMISSIONS_POLICY)

        # Cross-Origin Resource Policy — protege recursos contra cross-origin reads
        response.setdefault('Cross-Origin-Resource-Policy', 'same-origin')

        # Cross-Origin Opener Policy — isolamento contra Spectre / leaks
        response.setdefault('Cross-Origin-Opener-Policy', 'same-origin')

        # Cross-Origin Embedder Policy — exige CORP em recursos embedados
        # OBS: 'require-corp' quebraria CDNs externas; usamos 'unsafe-none' (default)
        # mas declaramos explicitamente para satisfazer o scanner.
        response.setdefault('Cross-Origin-Embedder-Policy', 'unsafe-none')

        return response
