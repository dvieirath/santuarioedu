"""Flashcards — extraidas de views/_todos.py."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from ..models import Flashcard, Categoria, Questao



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403

@login_required(login_url='account_login')
def flashcards(request):
    """Lista e cria flashcards do usuário. GET=listar, POST=criar."""
    categorias = Categoria.objects.all().order_by('nome')
    cat_id = request.GET.get('categoria', '')

    if request.method == 'POST':
        frente    = request.POST.get('frente', '').strip()
        verso     = request.POST.get('verso', '').strip()
        cat_id_p  = request.POST.get('categoria_id', '')
        if frente and verso:
            cat = Categoria.objects.filter(id=cat_id_p).first() if cat_id_p else None
            Flashcard.objects.create(
                usuario=request.user,
                frente=frente,
                verso=verso,
                categoria=cat,
            )
            messages.success(request, 'Flashcard criado com sucesso!')
        else:
            messages.error(request, 'Preencha a frente e o verso do flashcard.')
        return redirect('flashcards')

    qs = Flashcard.objects.filter(usuario=request.user)
    if cat_id:
        qs = qs.filter(categoria_id=cat_id)

    # Pendentes de revisão hoje
    hoje = timezone.localdate()
    pendentes = qs.filter(
        proxima_revisao__isnull=False,
        proxima_revisao__lte=hoje
    ).count() + qs.filter(proxima_revisao__isnull=True).count()
    total_q  = qs.count()
    em_dia   = max(0, total_q - pendentes)

    return render(request, 'quiz/flashcards.html', {
        'flashcards': qs,
        'categorias': categorias,
        'cat_id':    cat_id,
        'pendentes': pendentes,
        'em_dia':    em_dia,
        'total':     total_q,
    })

@login_required(login_url='account_login')
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def api_flashcard_deletar(request, flashcard_id):
    """Deleta um flashcard do usuário via AJAX."""
    fc = get_object_or_404(Flashcard, id=flashcard_id, usuario=request.user)
    fc.delete()
    return JsonResponse({'status': 'ok'})
