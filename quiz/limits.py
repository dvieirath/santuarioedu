"""
Limites de uso por plano (Gratuito / PRO / Premium).

Os números são lidos do .env — você pode ajustá-los sem mexer no código.
"""
from datetime import timedelta
from decouple import config
from django.utils import timezone


# ── Configuração de limites (lidos do .env, com defaults razoáveis) ──────────

LIMITES = {
    'gratuito': {
        'questoes_dia':       config('LIMIT_FREE_QUESTOES_DIA', default=30, cast=int),
        'simulados_semana':   config('LIMIT_FREE_SIMULADOS_SEMANA', default=1, cast=int),
        'ia_dia':             config('LIMIT_FREE_IA_DIA', default=3, cast=int),
        'flashcards_total':   config('LIMIT_FREE_FLASHCARDS', default=50, cast=int),
    },
    'pro': {
        'questoes_dia':       config('LIMIT_PRO_QUESTOES_DIA', default=999_999, cast=int),
        'simulados_semana':   config('LIMIT_PRO_SIMULADOS_SEMANA', default=999_999, cast=int),
        'ia_dia':             config('LIMIT_PRO_IA_DIA', default=30, cast=int),
        'flashcards_total':   config('LIMIT_PRO_FLASHCARDS', default=999_999, cast=int),
    },
    'premium': {
        'questoes_dia':       999_999,
        'simulados_semana':   999_999,
        'ia_dia':             100,
        'flashcards_total':   999_999,
    },
}


def get_plano(user):
    """Retorna a string do plano do usuário ('gratuito', 'pro' ou 'premium')."""
    if not user.is_authenticated:
        return 'gratuito'
    try:
        plano_obj = user.plano  # related_name=plano em PlanoUsuario
        if not plano_obj.ativo or plano_obj.expirado:
            return 'gratuito'
        return plano_obj.plano
    except Exception:
        return 'gratuito'


def limite(user, recurso):
    """Retorna o limite numérico do usuário para um recurso."""
    plano = get_plano(user)
    return LIMITES.get(plano, LIMITES['gratuito']).get(recurso, 0)


# ── Helpers de contagem ──────────────────────────────────────────────────────

def questoes_respondidas_hoje(user):
    """Quantas questões o usuário respondeu hoje."""
    from .models import RespostaUsuario
    inicio = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return RespostaUsuario.objects.filter(usuario=user, data__gte=inicio).count()


def simulados_iniciados_semana(user):
    """Quantos simulados iniciou na última semana."""
    from .models import Simulado
    sete_dias = timezone.now() - timedelta(days=7)
    return Simulado.objects.filter(usuario=user, iniciado_em__gte=sete_dias).count()


def flashcards_total(user):
    """Quantos flashcards o usuário tem."""
    from .models import Flashcard
    return Flashcard.objects.filter(usuario=user).count()


# ── Bloqueios usados pelas views ─────────────────────────────────────────────

def pode_responder_questao(user):
    """True se ainda pode responder mais questões hoje."""
    return questoes_respondidas_hoje(user) < limite(user, 'questoes_dia')


def pode_iniciar_simulado(user):
    """True se ainda pode iniciar mais simulados nesta semana."""
    return simulados_iniciados_semana(user) < limite(user, 'simulados_semana')


def pode_criar_flashcard(user):
    """True se ainda cabe mais flashcards no plano."""
    return flashcards_total(user) < limite(user, 'flashcards_total')


def status_uso(user):
    """Dicionário com contagem atual e limite — útil pra mostrar no dashboard."""
    plano = get_plano(user)
    return {
        'plano': plano,
        'questoes_dia': {
            'atual': questoes_respondidas_hoje(user),
            'limite': limite(user, 'questoes_dia'),
        },
        'simulados_semana': {
            'atual': simulados_iniciados_semana(user),
            'limite': limite(user, 'simulados_semana'),
        },
        'flashcards': {
            'atual': flashcards_total(user),
            'limite': limite(user, 'flashcards_total'),
        },
    }
