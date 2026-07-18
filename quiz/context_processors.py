"""
Context processors — variáveis disponíveis em TODOS os templates sem precisar
passar via view.
"""
from django.conf import settings


def configuracao_global(request):
    """Disponibiliza emails de contato + flags úteis em todos templates."""
    return {
        # Emails de contato (vêm do .env)
        'SUPORTE_EMAIL':     getattr(settings, 'SUPORTE_EMAIL', 'suporte@santuarioedu.com.br'),
        'FINANCEIRO_EMAIL':  getattr(settings, 'FINANCEIRO_EMAIL', 'financeiro@santuarioedu.com.br'),
        'PRIVACIDADE_EMAIL': getattr(settings, 'PRIVACIDADE_EMAIL', 'privacidade@santuarioedu.com.br'),

        # Configuração
        'DEBUG': settings.DEBUG,

        # Analytics (o partial decide se injeta com base nesses valores)
        'PLAUSIBLE_DOMAIN':  getattr(settings, 'PLAUSIBLE_DOMAIN',  ''),
        'GA_MEASUREMENT_ID': getattr(settings, 'GA_MEASUREMENT_ID', ''),
    }


def admin_badges(request):
    """Para usuários staff, expõe contadores pra mostrar badges na sidebar."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return {}
    try:
        from django.core.cache import cache
        from .models import Questao, TicketSuporte
        cached = cache.get('admin_badges')
        if cached is None:
            cached = {
                'admin_pendentes_qtd': Questao.objects.filter(
                    revisada=False, rejeitada_definitiva=False
                ).count(),
                'admin_tickets_abertos': TicketSuporte.objects.filter(
                    status__in=['aberto', 'aguardando']
                ).count(),
            }
            cache.set('admin_badges', cached, 60)  # 60s de cache
        return cached
    except Exception:
        return {}


def plano_usuario(request):
    """Disponibiliza o plano e limites do usuário em templates."""
    if not request.user.is_authenticated:
        return {'plano_atual': 'gratuito', 'is_pro': False, 'is_premium': False}
    try:
        from .limits import get_plano
        plano = get_plano(request.user)
        return {
            'plano_atual': plano,
            'is_pro':     plano in ('pro', 'premium'),
            'is_premium': plano == 'premium',
        }
    except Exception:
        return {'plano_atual': 'gratuito', 'is_pro': False, 'is_premium': False}
