"""Preparacao — Hub por concurso, edital, curva, progresso — extraidas de views/_todos.py."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import Http404
from django_ratelimit.decorators import ratelimit

from ..models import EditalPersonalizado, RespostaUsuario
from ..concurso_landing import CONCURSOS_LANDING



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403

@login_required(login_url='account_login')
@ratelimit(key='user', rate='10/h', method='POST', block=True)
def meu_edital(request):
    """
    Meu Edital Pessoal — user cola texto do edital, IA extrai:
    - Concurso/orgao
    - Banca provavel
    - Data da prova
    - Salario aproximado
    - Disciplinas com pesos e sub-topicos

    Depois gera cronograma personalizado (X dias × Y horas/dia).
    """
    from ..models import EditalPersonalizado
    import json as _json

    edital = EditalPersonalizado.objects.filter(usuario=request.user).first()

    if request.method == 'POST':
        acao = request.POST.get('acao', 'analisar')

        if acao == 'analisar':
            # Validacao estruturada via Form (padrao adotado para novos POSTs)
            from ..forms import EditalPersonalizadoForm
            form = EditalPersonalizadoForm(request.POST)
            if not form.is_valid():
                for erros in form.errors.values():
                    for msg in erros:
                        messages.error(request, msg)
                return redirect('meu_edital')

            texto = form.cleaned_data['texto_edital']
            horas = form.cleaned_data['horas_dia']

            # Cria/atualiza registro
            edital, _ = EditalPersonalizado.objects.update_or_create(
                usuario=request.user,
                defaults={
                    'texto_bruto': texto,
                    'horas_dia':   horas,
                },
            )

            # Chama IA pra extrair estrutura
            try:
                from ..ai_provider import gerar_conteudo, AIError
                prompt = (
                    f'Analise o edital abaixo e extraia informacoes estruturadas em JSON puro '
                    f'(sem markdown, sem ```json). Formato OBRIGATORIO:\n\n'
                    f'{{\n'
                    f'  "concurso": "Nome do concurso",\n'
                    f'  "orgao": "Orgao responsavel",\n'
                    f'  "banca": "Banca provavel se mencionada",\n'
                    f'  "data_prova": "AAAA-MM-DD ou null",\n'
                    f'  "salario_inicial": "R$ X.XXX,XX ou null",\n'
                    f'  "vagas": numero ou null,\n'
                    f'  "disciplinas": [\n'
                    f'    {{ "nome": "Direito Constitucional", "peso": 3, "topicos": ["Principios", "Direitos Fundamentais"] }},\n'
                    f'    ...\n'
                    f'  ]\n'
                    f'}}\n\n'
                    f'Se um campo nao aparecer no edital, use null. Disciplinas SEMPRE devem ser '
                    f'lista de objetos com nome/peso/topicos.\n\n'
                    f'EDITAL:\n{texto[:15000]}'
                )
                resposta = gerar_conteudo(prompt, max_tokens=2500, temperature=0.2)

                # Limpa markdown wrappers se IA colocou
                resposta = resposta.strip()
                if resposta.startswith('```'):
                    resposta = resposta.split('\n', 1)[-1]
                    if resposta.endswith('```'):
                        resposta = resposta.rsplit('```', 1)[0]
                resposta = resposta.strip()

                analise = _json.loads(resposta)
                edital.analise_ia = analise

                # Gera cronograma baseado na analise
                edital.cronograma = _gerar_cronograma_edital(analise, edital.horas_dia)

                edital.save()
                messages.success(request, 'Edital analisado — cronograma gerado abaixo.')
            except (AIError, _json.JSONDecodeError, KeyError, ValueError) as e:
                messages.error(request, f'Nao foi possivel analisar o edital: {e}')

            return redirect('meu_edital')

        elif acao == 'limpar' and edital:
            edital.delete()
            messages.success(request, 'Edital removido.')
            return redirect('meu_edital')

    return render(request, 'quiz/meu_edital.html', {
        'edital': edital,
    })

@login_required(login_url='account_login')
def preparacao_concurso(request, concurso):
    """
    Hub de preparacao completa por concurso — /preparacao/<concurso>/
    Consolida:
    - Analise de incidencia (% por disciplina)
    - Sub-topicos hot (o que mais cai)
    - Analise da banca (estilo, pegadinhas, tempo)
    - Gaps do user cruzados com incidencia (o que priorizar)
    - Cronograma sugerido (horas por disciplina)
    - Materiais disponiveis (resumos, mapas mentais)
    """
    from ..preparacao import resumo_completo
    from ..concurso_landing import CONCURSOS_LANDING
    from django.http import Http404

    if concurso not in CONCURSOS_LANDING:
        raise Http404('Concurso nao suportado')

    contexto = resumo_completo(request.user, concurso)
    return render(request, 'quiz/preparacao_concurso.html', contexto)

@login_required(login_url='account_login')
def curva_esquecimento(request):
    """Visualiza retencao estimada por disciplina (Ebbinghaus + SM-2)."""
    from .. import curva_esquecimento as _curva
    ctx = _curva.resumo_curva(request.user)
    return render(request, 'quiz/curva_esquecimento.html', ctx)

@login_required(login_url='account_login')
def progresso_edital_vivo(request):
    """
    Progresso do Edital VIVO — checklist baseado nos topicos do Meu Edital.
    Marca topico como dominado se user acertou >= 3 questoes cujo assunto
    contem o nome do topico (match icontains).
    """
    from ..models import EditalPersonalizado, RespostaUsuario

    edital = EditalPersonalizado.objects.filter(usuario=request.user).first()
    if not edital or not edital.analise_ia.get('disciplinas'):
        return render(request, 'quiz/progresso_edital_vivo.html', {
            'edital': None,
        })

    disciplinas_com_progresso = []
    total_topicos = 0
    total_dominados = 0

    for disc in edital.analise_ia.get('disciplinas', []):
        topicos = disc.get('topicos', [])
        topicos_status = []
        dominados = 0

        for topico in topicos:
            # Match: assunto ou texto da questao contem o topico
            respostas = RespostaUsuario.objects.filter(
                usuario=request.user,
                questao__revisada=True,
                acertou=True,
            ).filter(
                # Match no assunto OU categoria
                # (simplificacao — evita busca full-text pesada)
                questao__assunto__icontains=topico[:50]
            )
            n_acertos = respostas.count()
            dominado = n_acertos >= 3

            topicos_status.append({
                'nome':      topico,
                'acertos':   n_acertos,
                'dominado':  dominado,
                'faltam':    max(0, 3 - n_acertos),
            })

            total_topicos += 1
            if dominado:
                dominados += 1
                total_dominados += 1

        pct = round(dominados / len(topicos) * 100) if topicos else 0
        disciplinas_com_progresso.append({
            'nome':        disc.get('nome', '—'),
            'peso':        disc.get('peso', 1),
            'topicos':     topicos_status,
            'total':       len(topicos),
            'dominados':   dominados,
            'pct':         pct,
        })

    pct_geral = round(total_dominados / total_topicos * 100) if total_topicos else 0

    return render(request, 'quiz/progresso_edital_vivo.html', {
        'edital':          edital,
        'disciplinas':     disciplinas_com_progresso,
        'total_topicos':   total_topicos,
        'total_dominados': total_dominados,
        'pct_geral':       pct_geral,
    })

def _gerar_cronograma_edital(analise, horas_dia):
    """
    A partir da analise (com disciplinas + pesos), gera cronograma
    distribuindo as horas por peso relativo.
    Retorna list de dicts: [{disciplina, horas_semana, prioridade}]
    """
    disciplinas = analise.get('disciplinas', [])
    if not disciplinas:
        return []

    total_peso = sum(d.get('peso', 1) or 1 for d in disciplinas)
    horas_semana = horas_dia * 7

    cronograma = []
    for d in disciplinas:
        peso = d.get('peso', 1) or 1
        pct = peso / total_peso
        horas_disc_semana = round(horas_semana * pct, 1)
        cronograma.append({
            'disciplina':    d.get('nome', '—'),
            'peso':          peso,
            'topicos':       d.get('topicos', []),
            'horas_semana':  horas_disc_semana,
            'pct_tempo':     round(pct * 100, 1),
        })

    cronograma.sort(key=lambda x: -x['horas_semana'])
    return cronograma
