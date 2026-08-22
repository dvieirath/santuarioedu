"""Coach IA — extraidas de views/_todos.py."""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ..models import MensagemCoachIA, ConcursoPreferido
from ..concurso_landing import CONCURSOS_LANDING
from ..ai_provider import gerar_conteudo, AIError



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403

@login_required(login_url='account_login')
def coach_ia(request):
    """
    Chat 1-a-1 com Coach IA. User faz pergunta, coach responde
    considerando historico recente + contexto do concurso preferido.
    """
    from ..models import MensagemCoachIA, ConcursoPreferido
    from ..concurso_landing import CONCURSOS_LANDING

    if request.method == 'POST':
        from ..forms import MensagemCoachIAForm
        form = MensagemCoachIAForm(request.POST)
        if not form.is_valid():
            return redirect('coach_ia')
        conteudo = form.cleaned_data['mensagem']

        # Salva mensagem do user
        MensagemCoachIA.objects.create(
            usuario=request.user, papel='user', conteudo=conteudo,
        )

        # Monta contexto: system prompt + historico recente
        pref = ConcursoPreferido.objects.filter(usuario=request.user).first()
        contexto_concurso = ''
        if pref:
            cfg = CONCURSOS_LANDING.get(pref.concurso, {})
            contexto_concurso = (
                f'\n\nConcurso alvo do usuario: {cfg.get("nome_completo", pref.get_concurso_display())}. '
                f'Ele estuda ~{pref.horas_por_dia}h/dia.'
            )

        system_prompt = (
            'Voce e um coach de concurso publico brasileiro, especialista em preparacao pra provas. '
            'Responda em portugues brasileiro, direto e pratico. Use markdown pra estruturar quando '
            'ajudar. Evite jargao academico. Ofereca planos de acao concretos quando o user pedir. '
            'Se a pergunta for tecnica (uma duvida de disciplina), responda com precisao — cite '
            'artigos de lei, sumulas, jurisprudencia. Se for motivacional, seja realista mas encorajador.'
            + contexto_concurso
        )

        # Pega ultimas 10 mensagens pra manter contexto (evita explodir tokens)
        historico = list(MensagemCoachIA.objects.filter(usuario=request.user)
                         .order_by('-criado_em')[:10])
        historico.reverse()

        # Monta prompt final (em texto — Groq/Gemini nao tem chat separado no wrapper)
        prompt_final = f'SYSTEM:\n{system_prompt}\n\n'
        for m in historico:
            if m.papel == 'user':
                prompt_final += f'USER: {m.conteudo}\n\n'
            elif m.papel == 'assistant':
                prompt_final += f'ASSISTANT: {m.conteudo}\n\n'
        prompt_final += 'ASSISTANT:'

        # Chama IA
        try:
            from ..ai_provider import gerar_conteudo, AIError
            resposta = gerar_conteudo(prompt_final, max_tokens=1500, temperature=0.7)
            if not resposta or len(resposta) < 5:
                resposta = 'Desculpe, nao consegui gerar uma resposta agora. Tente reformular.'
        except AIError as e:
            resposta = f'⚠️ IA temporariamente indisponivel. Tente em instantes.'

        MensagemCoachIA.objects.create(
            usuario=request.user, papel='assistant', conteudo=resposta,
        )

        return redirect('coach_ia')

    mensagens = MensagemCoachIA.objects.filter(usuario=request.user).order_by('criado_em')[:50]
    return render(request, 'quiz/coach_ia.html', {
        'mensagens': mensagens,
    })

@login_required(login_url='account_login')
def coach_ia_limpar(request):
    """Apaga historico do coach (fresh start). Preserva salvas."""
    if request.method == 'POST':
        from ..models import MensagemCoachIA
        # Nao apaga mensagens salvas — user pode nao querer perder essas
        MensagemCoachIA.objects.filter(usuario=request.user, salva=False).delete()
        messages.success(request, 'Histórico do coach limpo (mensagens salvas mantidas).')
    return redirect('coach_ia')

@login_required(login_url='account_login')
def coach_ia_toggle_salvar(request, mensagem_id):
    """POST: alterna flag salva em uma mensagem do assistant."""
    from ..models import MensagemCoachIA
    if request.method != 'POST':
        return redirect('coach_ia')
    m = MensagemCoachIA.objects.filter(
        id=mensagem_id, usuario=request.user, papel='assistant',
    ).first()
    if m:
        m.salva = not m.salva
        m.save(update_fields=['salva'])
    return redirect(request.META.get('HTTP_REFERER', 'coach_ia'))

@login_required(login_url='account_login')
def coach_ia_anotacoes(request):
    """Lista todas as mensagens salvas do coach — 'caderneta pessoal'."""
    from ..models import MensagemCoachIA
    salvas = (MensagemCoachIA.objects
              .filter(usuario=request.user, salva=True)
              .order_by('-criado_em'))
    return render(request, 'quiz/coach_ia_anotacoes.html', {
        'mensagens': salvas,
    })
