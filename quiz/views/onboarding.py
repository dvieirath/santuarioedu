"""Onboarding + limites — extraidas de views/_todos.py."""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ..models import Perfil, ConcursoPreferido



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403

@login_required(login_url='account_login')
def onboarding_dispensar(request):
    """POST: user clica no X do card de onboarding pra dispensa-lo."""
    if request.method == 'POST':
        from ..models import Perfil
        perfil, _ = Perfil.objects.get_or_create(usuario=request.user)
        perfil.onboarding_dispensado = True
        perfil.save(update_fields=['onboarding_dispensado'])
    return redirect('dashboard')

@login_required(login_url='account_login')
def onboarding_concurso(request):
    """Pergunta concurso + tempo até prova + horas/dia. App agora 100% gratuita."""
    from ..models import ConcursoPreferido
    from ..forms import ConcursoPreferidoForm

    if request.method == 'POST':
        form = ConcursoPreferidoForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Preencha concurso e horas/dia.')
            return redirect('onboarding_concurso')

        cp, _ = ConcursoPreferido.objects.get_or_create(usuario=request.user)
        cp.concurso = form.cleaned_data['concurso']
        cp.horas_por_dia = form.cleaned_data.get('horas_por_dia') or 2
        if form.cleaned_data.get('data_prova_esperada'):
            cp.data_prova_esperada = form.cleaned_data['data_prova_esperada']
        cp.save()

        # Vai direto pra escolher tema (nao pra dashboard vazio) — 1o clique real
        return redirect('escolher_tema')

    return render(request, 'quiz/onboarding_concurso.html')

@login_required(login_url='account_login')
def limite_atingido_questoes(request):
    """Deprecated — app agora 100% gratuita. Redireciona pro dashboard."""
    return redirect('dashboard')
