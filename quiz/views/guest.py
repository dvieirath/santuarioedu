"""Guest Quiz — demo publico sem cadastro (max 3 questoes) — extraidas de views/_todos.py."""
from django.shortcuts import render, redirect
import hashlib
import json
from pathlib import Path

from ..models import Questao, Alternativa


GUEST_QUIZ_LIMITE = 3



DEMO_CURADORIA = json.loads(
    (Path(__file__).resolve().parent.parent / 'demo_curadoria.json').read_text(encoding='utf-8')
)


def _assinatura(q):
    dados = {'texto': q.texto, 'tipo': q.tipo, 'justificativa': q.justificativa,
             'categoria': q.categoria.nome,
             'alternativas': sorted((a.texto, a.correta) for a in q.alternativa_set.all())}
    return hashlib.sha256(json.dumps(dados, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _questoes_demo():
    assinaturas = {item['texto']: item['sha256'] for item in DEMO_CURADORIA}
    candidatas = Questao.objects.filter(
        revisada=True, rejeitada_definitiva=False, texto__in=assinaturas,
    ).select_related('categoria').prefetch_related('alternativa_set').order_by('id')
    return [q for q in candidatas if not q.imagem and _assinatura(q) == assinaturas[q.texto]]

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

    disponiveis = _questoes_demo()
    if len(disponiveis) < GUEST_QUIZ_LIMITE:
        return render(request, 'quiz/guest_indisponivel.html')
    q = next((q for q in disponiveis if q.id == request.session.get('guest_atual')
              and q.id not in respondidas), None)
    q = q or next((q for q in disponiveis if q.id not in respondidas), None)
    if not q:
        # BD vazio (nao deveria acontecer em prod)
        return redirect('cadastro')

    request.session['guest_atual'] = q.id
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

    if not all(value.isascii() and value.isdecimal() and len(value) <= 18
               for value in (q_id_raw, alt_id_raw)):
        return redirect('guest_quiz')

    respondidas = request.session.get('guest_respondidas', [])
    if (len(respondidas) >= GUEST_QUIZ_LIMITE
            or int(q_id_raw) != request.session.get('guest_atual')):
        return redirect('guest_quiz')
    q = next((q for q in _questoes_demo() if q.id == int(q_id_raw)), None)
    if q is None:
        return redirect('guest_quiz')
    try:
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
    request.session.pop('guest_atual', None)
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
    for k in ('guest_respondidas', 'guest_acertos', 'guest_atual'):
        request.session.pop(k, None)
    return redirect('guest_quiz')
