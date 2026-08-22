"""
Limites de uso — MODO 100% GRATUITO.

App e totalmente gratuita. Todas as verificacoes retornam:
- pode_responder_questao/pode_iniciar_simulado/pode_criar_flashcard: True
- get_plano: 'gratuito' (mas sem restricoes)
- limite: infinito
- status_uso: uso irrestrito

Mantido pra compatibilidade com views existentes — nao remove chamadas,
so libera tudo.

Se voltar a monetizar no futuro, re-implementar essas funcoes.
"""


def get_plano(user):
    """Sempre retorna 'gratuito' (que agora eh sem limites)."""
    return 'gratuito'


def limite(user, recurso):
    """Sem limites."""
    return 999_999_999


def questoes_respondidas_hoje(user):
    from .models import RespostaUsuario
    from django.utils import timezone
    inicio = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return RespostaUsuario.objects.filter(usuario=user, data__gte=inicio).count()


def simulados_iniciados_semana(user):
    from datetime import timedelta
    from .models import Simulado
    from django.utils import timezone
    sete_dias = timezone.now() - timedelta(days=7)
    return Simulado.objects.filter(usuario=user, iniciado_em__gte=sete_dias).count()


def flashcards_total(user):
    from .models import Flashcard
    return Flashcard.objects.filter(usuario=user).count()


# ── Bloqueios sempre-permite ─────────────────────────────────────────────────

def pode_responder_questao(user):
    return True


def pode_iniciar_simulado(user):
    return True


def pode_criar_flashcard(user):
    return True


def status_uso(user):
    """Retorna estatisticas SEM limite."""
    return {
        'plano': 'gratuito',
        'questoes_dia': {
            'atual':  questoes_respondidas_hoje(user),
            'limite': 999_999_999,
        },
        'simulados_semana': {
            'atual':  simulados_iniciados_semana(user),
            'limite': 999_999_999,
        },
        'flashcards': {
            'atual':  flashcards_total(user),
            'limite': 999_999_999,
        },
    }
