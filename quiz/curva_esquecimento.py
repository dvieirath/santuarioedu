"""
Curva de Esquecimento (Ebbinghaus + SM-2 do sistema).

Estima retencao atual por disciplina baseado em:
- Data da ultima resposta correta (por questao)
- Intervalo do SRS (fator de facilidade)
- Formula: R(t) = exp(-t / S) onde S = 1 + fator_facilidade * intervalo_dias

Nao e ciencia exata — usa aproximacao SM-2 pra estimar retencao %.
Objetivo: dar visualizacao clara pra user do que esta pra esquecer.
"""
from django.core.cache import cache
from django.utils import timezone
from django.db.models import Max, Count
import math


def calcular_retencao(dias_desde_ultima, fator_facilidade=2.5, repeticoes=1):
    """
    Retorna % de retencao estimada (0-100).
    Ebbinghaus: R = e^(-t/S)
    Onde S (estabilidade) cresce com repeticoes bem sucedidas.
    """
    if dias_desde_ultima < 0:
        return 100.0
    # S cresce com repeticoes + fator de facilidade
    S = max(1, repeticoes) * fator_facilidade * 2
    retencao = math.exp(-dias_desde_ultima / S)
    return round(retencao * 100, 1)


def curva_por_disciplina(user):
    """
    Pra cada disciplina raiz onde user respondeu, calcula:
    - dias_desde_ultima_resposta_correta
    - retencao_estimada (%)
    - total_questoes_estudadas
    - status (solido/atencao/critico)

    Cache 10min pra evitar recomputar em cada refresh.
    """
    cache_key = f'curva_disc:{user.id}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    from .models import RespostaUsuario, RevisaoEspacada, Categoria

    hoje = timezone.localdate()
    resultado = []

    # Pega todas as categorias raiz que o user tocou
    cats_ids = (RespostaUsuario.objects
                .filter(usuario=user)
                .values_list('questao__categoria__parent_id',
                             'questao__categoria_id')
                .distinct())

    raiz_ids = set()
    for parent_id, cat_id in cats_ids:
        # Sobe ate encontrar a raiz
        atual = cat_id
        while atual:
            cat = Categoria.objects.filter(id=atual).first()
            if not cat:
                break
            if cat.parent_id is None:
                raiz_ids.add(cat.id)
                break
            atual = cat.parent_id

    for raiz_id in raiz_ids:
        cat = Categoria.objects.get(id=raiz_id)
        subarv = cat.subarvore_ids()

        respostas = RespostaUsuario.objects.filter(
            usuario=user, questao__categoria_id__in=subarv,
        )
        total = respostas.count()
        if total < 3:
            continue  # pouca massa, ignora

        # Ultima resposta certa nessa disciplina
        ultima_certa = respostas.filter(acertou=True).aggregate(m=Max('data'))
        if not ultima_certa['m']:
            continue
        dias_desde = (timezone.now() - ultima_certa['m']).days

        # Media do fator SRS e repeticoes das questoes desta arvore
        srs = RevisaoEspacada.objects.filter(
            usuario=user, questao__categoria_id__in=subarv,
        )
        srs_stats = srs.aggregate(
            fator=Max('fator_facilidade'),  # pega o maior (melhor estabilidade)
            reps_max=Max('repeticoes'),
        )
        fator = srs_stats['fator'] or 2.5
        reps = srs_stats['reps_max'] or 1

        retencao = calcular_retencao(dias_desde, fator, reps)

        if retencao >= 70:
            status = 'solido'
            cor = 'emerald'
        elif retencao >= 40:
            status = 'atencao'
            cor = 'amber'
        else:
            status = 'critico'
            cor = 'rose'

        resultado.append({
            'disciplina':       cat.nome,
            'categoria_id':     cat.id,
            'total_questoes':   total,
            'dias_desde':       dias_desde,
            'retencao':         retencao,
            'status':           status,
            'cor':              cor,
            'fator':            round(fator, 2),
            'repeticoes':       reps,
        })

    resultado.sort(key=lambda x: x['retencao'])
    cache.set(cache_key, resultado, 600)  # 10min
    return resultado


def resumo_curva(user):
    """Retorna resumo agregado + list detalhada."""
    disc = curva_por_disciplina(user)
    if not disc:
        return {
            'disciplinas':    [],
            'total':          0,
            'solido':         0,
            'atencao':        0,
            'critico':        0,
            'retencao_media': 0,
        }
    return {
        'disciplinas':    disc,
        'total':          len(disc),
        'solido':         sum(1 for d in disc if d['status'] == 'solido'),
        'atencao':        sum(1 for d in disc if d['status'] == 'atencao'),
        'critico':        sum(1 for d in disc if d['status'] == 'critico'),
        'retencao_media': round(sum(d['retencao'] for d in disc) / len(disc), 1),
    }
