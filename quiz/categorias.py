"""
Quais categorias o aluno deve ver em listas e seletores.

A árvore tem nós sem nenhuma questão liberada: tópicos de trilha que ainda não
receberam conteúdo, a espera "A classificar" e sobras de importações antigas.
Oferecer esses nós em um filtro leva o aluno a uma tela vazia. As telas do
aluno usam `categorias_com_conteudo()`; as telas de administração continuam
listando tudo.
"""
from .models import Categoria, Questao


def ids_com_conteudo():
    """IDs das categorias com questão liberada nelas ou em algum descendente."""
    diretas = set(
        Questao.objects.filter(revisada=True, rejeitada_definitiva=False)
        .values_list('categoria_id', flat=True).distinct()
    )
    pai_de = dict(Categoria.objects.values_list('id', 'parent_id'))
    ids = set()
    for cid in diretas:
        # Sobe até a raiz; para ao encontrar nó já visitado (também evita ciclo).
        while cid is not None and cid not in ids:
            ids.add(cid)
            cid = pai_de.get(cid)
    return ids


def categorias_com_conteudo(tambem=()):
    """Categorias com conteúdo liberado, em ordem alfabética.

    `tambem`: IDs que devem aparecer mesmo sem questão, por exemplo categorias
    que já têm resumo, mapa mental ou flashcard do próprio aluno.
    """
    ids = ids_com_conteudo() | {cid for cid in tambem if cid}
    return Categoria.objects.filter(id__in=ids).order_by('nome')
