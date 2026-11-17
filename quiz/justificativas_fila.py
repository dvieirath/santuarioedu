"""
Fila de geração de justificativas por IA.

Define QUAIS questões sem justificativa entram primeiro e QUAIS não devem ser
geradas antes de uma revisão humana.

Motivo: em questão com defeito estrutural (sem gabarito único, texto cortado,
referência a imagem/texto ausente), a IA tende a explicar um gabarito duvidoso
ou a inventar o conteúdo que falta — isso é pior do que não ter justificativa,
porque dá aparência de conteúdo revisado a um item defeituoso.

Usado por:
  - `manage.py fila_justificativas` (relatório e CSV, somente leitura)
  - `manage.py gerar_justificativas_ia` (ordem e filtro de processamento)
"""
import csv
import json
from collections import Counter
from pathlib import Path

from django.db.models import Count, Q

from .auditoria import detectar_flags
from .models import Questao


# Flags de auditoria que impedem uma justificativa confiável. São os defeitos
# em que a IA teria de supor o que falta ou endossar um gabarito ambíguo.
FLAGS_IMPEDEM_GERACAO = frozenset({
    'sem_gabarito',
    'multiplos_gabaritos',
    'alternativa_vazia',
    'alternativa_muito_curta',
    'alternativas_duplicadas',
    'alternativa_igual_ao_enunciado',
    'numero_alts_invalido_ce',
    'numero_alts_invalido_me',
    'texto_muito_curto',
    'marcador_conteudo_faltando',
    'referencia_a_imagem_sem_imagem',
    'referencia_a_texto_ausente',
    'letras_flutuantes',
    'watermark_residual',
})

_BASE = Path(__file__).resolve().parent


def textos_demo():
    """Enunciados da demo pública (/testar/), que precisam de prioridade máxima."""
    try:
        itens = json.loads((_BASE / 'demo_curadoria.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return set()
    return {(item.get('texto') or '') for item in itens if item.get('texto')}


def sem_justificativa(incluir_pendentes=False, somente_pendentes=False,
                      somente_ia=False):
    """Questões sem justificativa, com contagem de respostas de usuários.

    Por padrão só entram as liberadas (revisada=True e não rejeitada), ou seja,
    as que o aluno realmente vê. `somente_pendentes` serve ao pipeline de
    importação, que gera a justificativa antes da aprovação.
    """
    qs = Questao.objects.filter(
        Q(justificativa__isnull=True) | Q(justificativa='')
    ).exclude(rejeitada_definitiva=True)

    if somente_pendentes:
        qs = qs.filter(revisada=False)
    elif not incluir_pendentes:
        qs = qs.filter(revisada=True)

    if somente_ia:
        qs = qs.filter(gerada_por_ia=True)

    return (
        qs.select_related('categoria')
        .prefetch_related('alternativa_set')
        .annotate(n_respostas=Count('respostausuario'))
    )


def avaliar_questao(questao, alts=None):
    """Retorna (elegivel, motivos) para decidir se a IA pode gerar a justificativa."""
    flags = detectar_flags(questao, alts)
    motivos = sorted(set(flags) & FLAGS_IMPEDEM_GERACAO)
    return (not motivos), motivos


def selecionar(queryset, limite=None, priorizar=True, incluir_inelegiveis=False):
    """Transforma o queryset em uma fila ordenada de dicts.

    Ordem de prioridade:
      1. questões da demo pública (o usuário vê antes de qualquer cadastro);
      2. questões que já receberam respostas de usuários (impacto real);
      3. demais, por id (ordem de importação, que acompanha a categoria).
    """
    demo = textos_demo()
    itens = []
    for q in queryset:
        alts = list(q.alternativa_set.all())
        elegivel, motivos = avaliar_questao(q, alts)
        if motivos and not incluir_inelegiveis:
            continue
        itens.append({
            'questao': q,
            'elegivel': elegivel,
            'motivos': motivos,
            'demo': (q.texto or '') in demo,
            'respostas': getattr(q, 'n_respostas', 0) or 0,
        })

    if priorizar:
        itens.sort(key=lambda i: (not i['demo'], -i['respostas'], i['questao'].id))

    return itens[:limite] if limite else itens


def resumo(queryset=None, incluir_pendentes=False):
    """Consolida o estado da fila para relatório (não altera nada)."""
    qs = queryset if queryset is not None else sem_justificativa(
        incluir_pendentes=incluir_pendentes,
    )
    demo = textos_demo()

    motivos = Counter()
    elegiveis_por_categoria = Counter()
    inelegiveis_por_categoria = Counter()
    exemplos_inelegiveis = []

    total = elegiveis = respondidas = demo_sem_justificativa = 0
    for q in qs:
        total += 1
        elegivel, motivos_q = avaliar_questao(q, list(q.alternativa_set.all()))
        if (q.texto or '') in demo:
            demo_sem_justificativa += 1
        if getattr(q, 'n_respostas', 0):
            respondidas += 1
        if elegivel:
            elegiveis += 1
            elegiveis_por_categoria[q.categoria.nome] += 1
        else:
            motivos.update(motivos_q)
            inelegiveis_por_categoria[q.categoria.nome] += 1
            if len(exemplos_inelegiveis) < 10:
                exemplos_inelegiveis.append({
                    'id': q.id,
                    'categoria': q.categoria.nome,
                    'motivos': motivos_q,
                    'texto': (q.texto or '')[:90],
                })

    return {
        'total_sem_justificativa': total,
        'elegiveis': elegiveis,
        'inelegiveis': total - elegiveis,
        'demo_total': len(demo),
        'demo_sem_justificativa': demo_sem_justificativa,
        'respondidas_sem_justificativa': respondidas,
        'motivos': motivos,
        'elegiveis_por_categoria': elegiveis_por_categoria,
        'inelegiveis_por_categoria': inelegiveis_por_categoria,
        'exemplos_inelegiveis': exemplos_inelegiveis,
    }


def exportar_csv(itens, caminho):
    """Escreve a fila em CSV (UTF-8 com BOM, abre no Excel sem ajuste)."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open('w', encoding='utf-8-sig', newline='') as fh:
        escritor = csv.writer(fh, delimiter=';')
        escritor.writerow([
            'id', 'prioridade', 'categoria', 'tipo', 'banca', 'ano',
            'respostas', 'elegivel', 'motivos', 'texto',
        ])
        for item in itens:
            q = item['questao']
            if item['demo']:
                prioridade = 'demo'
            elif item['respostas']:
                prioridade = 'respondida'
            else:
                prioridade = 'nova'
            escritor.writerow([
                q.id, prioridade, q.categoria.nome, q.tipo, q.banca or '',
                q.ano or '', item['respostas'], 'sim' if item['elegivel'] else 'nao',
                '|'.join(item['motivos']), (q.texto or '')[:200].replace('\n', ' '),
            ])
    return caminho
