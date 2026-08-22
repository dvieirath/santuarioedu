"""Guest Quiz — demo publico sem cadastro (max 3 questoes) — extraidas de views/_todos.py."""
from django.shortcuts import render, redirect

from ..models import Questao, Alternativa, Categoria


GUEST_QUIZ_LIMITE = 3



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403

def guest_quiz(request):
    """Demo de 3 questoes sem cadastro. Session tracker."""
    # Se ja logado, manda direto pro quiz real
    if request.user.is_authenticated:
        return redirect('escolher_tema')

    respondidas = request.session.get('guest_respondidas', [])
    acertos = request.session.get('guest_acertos', 0)

    # Se ja terminou o demo, mostra tela final
    if len(respondidas) >= GUEST_QUIZ_LIMITE:
        return render(request, 'quiz/guest_quiz_final.html', {
            'acertos': acertos,
            'total':   GUEST_QUIZ_LIMITE,
            'pct':     round(acertos / GUEST_QUIZ_LIMITE * 100),
        })

    q = _guest_pegar_questao(respondidas)
    if not q:
        # BD vazio (nao deveria acontecer em prod)
        return redirect('cadastro')

    return render(request, 'quiz/guest_quiz.html', {
        'questao':    q,
        'alternativas': list(q.alternativa_set.all()),
        'progresso':  len(respondidas) + 1,
        'total':      GUEST_QUIZ_LIMITE,
        'acertos':    acertos,
    })

def guest_quiz_responder(request):
    """POST: registra resposta na session e mostra resultado."""
    if request.method != 'POST':
        return redirect('guest_quiz')
    if request.user.is_authenticated:
        return redirect('escolher_tema')

    q_id_raw = request.POST.get('questao_id', '').strip()
    alt_id_raw = request.POST.get('alternativa_id', '').strip()

    if not (q_id_raw.isdigit() and alt_id_raw.isdigit()):
        return redirect('guest_quiz')

    try:
        q = Questao.objects.get(id=int(q_id_raw), revisada=True)
        alt = Alternativa.objects.get(id=int(alt_id_raw), questao=q)
    except (Questao.DoesNotExist, Alternativa.DoesNotExist):
        return redirect('guest_quiz')

    # Session tracking (idempotente: se ja respondeu essa questao, ignora)
    respondidas = request.session.get('guest_respondidas', [])
    if q.id in respondidas:
        return redirect('guest_quiz')

    acertou = alt.correta
    respondidas.append(q.id)
    request.session['guest_respondidas'] = respondidas

    acertos = request.session.get('guest_acertos', 0)
    if acertou:
        acertos += 1
    request.session['guest_acertos'] = acertos
    request.session.modified = True

    correta = q.alternativa_set.filter(correta=True).first()
    return render(request, 'quiz/guest_quiz_resultado.html', {
        'questao':   q,
        'sua_alt':   alt,
        'correta':   correta,
        'acertou':   acertou,
        'progresso': len(respondidas),
        'total':     GUEST_QUIZ_LIMITE,
        'acertos':   acertos,
        'termina':   len(respondidas) >= GUEST_QUIZ_LIMITE,
    })

def guest_quiz_reset(request):
    """Reseta a sessao guest — util pra testar de novo ou apos falhar."""
    for k in ('guest_respondidas', 'guest_acertos'):
        request.session.pop(k, None)
    return redirect('guest_quiz')

def _guest_pegar_questao(ja_respondidas_ids):
    """Escolhe questao demo — priorizacao curada:
    1. Direito Constitucional (nosso forte apos batch 636)
    2. Fallback: qualquer questao revisada
    """
    from ..models import Categoria
    q = None
    # Prioriza Direito Const (maior massa e mais interessante)
    dc = Categoria.objects.filter(
        nome__iexact='Direito Constitucional',
    ).first()
    if dc:
        q = (Questao.objects
             .filter(revisada=True, categoria_id__in=dc.subarvore_ids())
             .exclude(id__in=ja_respondidas_ids)
             .order_by('?').first())
    if not q:
        # Fallback: qualquer revisada
        q = (Questao.objects
             .filter(revisada=True)
             .exclude(id__in=ja_respondidas_ids)
             .order_by('?').first())
    return q
