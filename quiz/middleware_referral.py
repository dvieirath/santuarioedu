"""
Middleware simples pra capturar ?ref=<username> na URL e guardar na session.

Usado pelo signal user_signed_up (quiz/signals.py) pra criar Referencia
quando o user completa o cadastro (allauth).

Fluxo:
1. User A copia link santuarioedu.com.br/?ref=userA
2. User B (novo) clica -> middleware pega ref=userA e salva session['ref_code']
3. User B navega, se cadastra -> signal cria Referencia + XP pra ambos
4. Session limpa apos processar

Sem side effects se ?ref= ausente. Sem hit no BD (so session write).
"""

REF_SESSION_KEY = 'ref_code'
REF_QUERY_PARAM = 'ref'
# Cookie fallback pra usuarios que abrem a URL, fecham navegador, voltam
# depois: session so vive na aba. Cookie 30 dias.
REF_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 dias


class CapturaReferralMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        codigo = request.GET.get(REF_QUERY_PARAM)
        if codigo:
            codigo = codigo.strip()[:150]  # sanity limit (username max_length=150)
            if codigo and codigo.replace('_', '').replace('-', '').replace('.', '').isalnum():
                # Guarda na session pra o signal ler no cadastro
                request.session[REF_SESSION_KEY] = codigo

        response = self.get_response(request)

        # Tambem seta cookie (fallback pra session expirada)
        if codigo and codigo.replace('_', '').replace('-', '').replace('.', '').isalnum():
            response.set_cookie(
                REF_SESSION_KEY, codigo,
                max_age=REF_COOKIE_MAX_AGE,
                samesite='Lax',
                secure=not request.is_secure() is False,  # secure em prod
            )

        return response
