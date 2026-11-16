"""
Categoria de espera para questões importadas sem classificação confiável.

Quando a classificação automática falha, a questão fica em "A classificar"
(raiz), pendente, até alguém definir a disciplina. Nenhum caminho de aprovação
libera questão que ainda está aqui.

Antes, o importador jogava essas questões em "Direito > Direito Constitucional".
Foi assim que a disciplina recebeu centenas de questões de Geologia,
Termodinâmica e outras áreas.
"""

NOME_A_CLASSIFICAR = 'A classificar'


def categoria_a_classificar():
    """Devolve a categoria de espera, criando-a se ainda não existir."""
    from .models import Categoria
    categoria, _ = Categoria.objects.get_or_create(nome=NOME_A_CLASSIFICAR, parent=None)
    return categoria


def filtro_a_classificar(prefixo='categoria'):
    """Kwargs de filtro para querysets de Questao: as que estão na espera.

    Uso: Questao.objects.exclude(**filtro_a_classificar())
    """
    return {f'{prefixo}__nome': NOME_A_CLASSIFICAR, f'{prefixo}__parent__isnull': True}


def eh_a_classificar(questao):
    """True se a questão está na categoria de espera.

    Usa a categoria já carregada (select_related) quando houver; só consulta o
    banco se ela não estiver em memória.
    """
    if not questao.categoria_id:
        return False
    carregada = questao._state.fields_cache.get('categoria')
    if carregada is not None:
        return carregada.parent_id is None and carregada.nome == NOME_A_CLASSIFICAR
    from .models import Categoria
    return Categoria.objects.filter(
        pk=questao.categoria_id, parent__isnull=True, nome=NOME_A_CLASSIFICAR,
    ).exists()
