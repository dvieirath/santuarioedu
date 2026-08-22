"""Convidar amigos — extraidas de views/_todos.py."""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403

@login_required(login_url='account_login')
def convidar(request):
    """
    Pagina de convite: user copia link unico santuarioedu.com.br/?ref=<user>
    Cada amigo que se cadastra via esse link entrega XP pra ambos.
    """
    from django.conf import settings as _settings
    from ..models import Referencia, NivelUsuario

    site_url = getattr(_settings, 'SITE_URL', 'https://santuarioedu.com.br').rstrip('/')
    codigo   = request.user.username
    link     = f'{site_url}/?ref={codigo}'

    referencias = Referencia.objects.filter(convidador=request.user).select_related('convidado')
    total_convites = referencias.count()
    xp_total = sum(r.xp_convidador for r in referencias)

    # Nivel atual pra mostrar impacto do XP ganho
    nivel, _ = NivelUsuario.objects.get_or_create(usuario=request.user)

    return render(request, 'quiz/convidar.html', {
        'link':           link,
        'codigo':         codigo,
        'referencias':    referencias[:10],  # 10 mais recentes
        'total_convites': total_convites,
        'xp_ganho_total': xp_total,
        'nivel_atual':    nivel,
        'xp_por_convite': 150,
    })
