"""
Onboarding Checklist — primeiros 7 dias do usuario.

Combate ao churn precoce: 70% dos abandonos acontecem nos primeiros 3
dias. Um checklist gamificado com micro-recompensas (XP) mantem o user
voltando pra "fechar" as tarefas antes de esquecer que a plataforma
existe.

Design:
- Lista fixa de tarefas hardcoded aqui (nao precisa admin/CMS).
- Cada tarefa tem um checker(user) que verifica se ja foi completada.
- get_status(user) retorna lista com estado atual — usado no template.
- check_and_award(user) verifica todas + entrega XP das novas concluidas
  (idempotente via Perfil.onboarding_awarded).

Sem novo modelo pesado: tudo derivado dos dados que ja existem (respostas,
simulados, ConcursoPreferido, streak). Chamado no dashboard.
"""
from django.urls import reverse
from django.utils import timezone


TASKS = [
    {
        'slug': 'primeiras_5',
        'titulo': 'Responder 5 questões',
        'descricao': 'Se familiarize com o formato — leva 2 minutos.',
        'icone': 'menu_book',
        'cor': 'blue',
        'xp': 50,
        'url_name': 'escolher_tema',
    },
    {
        'slug': 'concurso_pref',
        'titulo': 'Marcar concurso preferido',
        'descricao': 'A gente adapta ranks e recomendações ao seu foco.',
        'icone': 'flag',
        'cor': 'violet',
        'xp': 30,
        'url_name': 'perfil',
    },
    {
        'slug': 'primeiro_simulado',
        'titulo': 'Fazer 1 simulado cronometrado',
        'descricao': 'Teste seu tempo em condição de prova.',
        'icone': 'timer',
        'cor': 'indigo',
        'xp': 100,
        'url_name': 'escolher_tema',   # simulados também partem daqui
    },
    {
        'slug': 'ver_analise',
        'titulo': 'Ver análise por subtema',
        'descricao': 'Mapa dos seus pontos fracos, em detalhe.',
        'icone': 'insights',
        'cor': 'sky',
        'xp': 20,
        'url_name': 'analise_subtemas',
    },
    {
        'slug': 'streak_3',
        'titulo': 'Estudar 3 dias seguidos',
        'descricao': 'Construa o hábito — o retorno vem depois.',
        'icone': 'local_fire_department',
        'cor': 'amber',
        'xp': 80,
        'url_name': 'escolher_tema',
    },
]


def _completou_primeiras_5(user):
    from .models import RespostaUsuario
    return RespostaUsuario.objects.filter(usuario=user).count() >= 5


def _completou_concurso_pref(user):
    from .models import ConcursoPreferido
    return ConcursoPreferido.objects.filter(usuario=user).exists()


def _completou_primeiro_simulado(user):
    from .models import Simulado
    return Simulado.objects.filter(usuario=user, finalizado=True).exists()


def _completou_ver_analise(user):
    # Nao ha tracking direto de visualizacao — proxy: user tem >= 10 respostas
    # (so faz sentido ver analise com massa minima).
    # Alternativa mais precisa exigiria model novo — proxy resolve.
    from .models import RespostaUsuario
    return RespostaUsuario.objects.filter(usuario=user).count() >= 10


def _completou_streak_3(user):
    from .models import MetaEstudo
    m = MetaEstudo.objects.filter(usuario=user).first()
    return bool(m and m.streak_atual >= 3)


CHECKERS = {
    'primeiras_5':       _completou_primeiras_5,
    'concurso_pref':     _completou_concurso_pref,
    'primeiro_simulado': _completou_primeiro_simulado,
    'ver_analise':       _completou_ver_analise,
    'streak_3':          _completou_streak_3,
}


def get_status(user):
    """
    Retorna lista de dicts com estado do onboarding pro user:
    [{slug, titulo, descricao, icone, cor, xp, url, feito, xp_recebido}, ...]
    """
    from .models import Perfil
    perfil, _ = Perfil.objects.get_or_create(usuario=user)
    awarded = set(perfil.onboarding_awarded or [])

    resultado = []
    for task in TASKS:
        checker = CHECKERS.get(task['slug'])
        feito = bool(checker and checker(user))
        try:
            url = reverse(task['url_name'])
        except Exception:
            url = '/dashboard/'
        resultado.append({
            **task,
            'feito':        feito,
            'xp_recebido':  task['slug'] in awarded,
            'url':          url,
        })
    return resultado


def check_and_award(user):
    """
    Verifica tarefas completadas e entrega XP das NAO recompensadas ainda.
    Idempotente: cada slug so entrega XP uma vez.
    Retorna lista de tasks recem-recompensadas (pra flash message opcional).
    """
    from .models import Perfil, NivelUsuario
    perfil, _ = Perfil.objects.get_or_create(usuario=user)
    awarded = list(perfil.onboarding_awarded or [])
    novas = []

    for task in TASKS:
        slug = task['slug']
        if slug in awarded:
            continue
        checker = CHECKERS.get(slug)
        if checker and checker(user):
            # Award XP
            nivel, _ = NivelUsuario.objects.get_or_create(usuario=user)
            nivel.adicionar_xp(task['xp'])
            awarded.append(slug)
            novas.append(task)

    if novas:
        perfil.onboarding_awarded = awarded
        perfil.save(update_fields=['onboarding_awarded'])

    return novas


def deve_exibir_card(user):
    """
    True se o card de onboarding deve aparecer no dashboard.
    Regras:
    - User dispensou explicitamente (X no card) -> nao mostra.
    - User completou todas as tarefas -> nao mostra (mas antes, mostra
      celebracao de conclusao na proxima renderizacao — v2).
    - User cadastrou ha mais de 30 dias -> nao mostra (esqueceu, veio velho).
    - Caso contrario -> mostra.
    """
    from .models import Perfil
    perfil = Perfil.objects.filter(usuario=user).first()
    if perfil and perfil.onboarding_dispensado:
        return False

    dias_desde_cadastro = (timezone.now() - user.date_joined).days
    if dias_desde_cadastro > 30:
        return False

    status = get_status(user)
    if all(t['feito'] for t in status):
        return False

    return True


def resumo(user):
    """
    Retorna dict de resumo pro dashboard:
    { total, feitos, pendentes, pct, dias_desde_cadastro, deve_exibir }
    """
    status = get_status(user)
    total = len(status)
    feitos = sum(1 for t in status if t['feito'])
    dias = (timezone.now() - user.date_joined).days
    return {
        'total':        total,
        'feitos':       feitos,
        'pendentes':    total - feitos,
        'pct':          round(feitos / total * 100) if total else 0,
        'dias':         dias,
        'tasks':        status,
        'deve_exibir':  deve_exibir_card(user),
    }
