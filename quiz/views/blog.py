"""Blog institucional — extraidas de views/_todos.py."""
from django.shortcuts import render, get_object_or_404
from django.utils import timezone

from ..models import PostBlog



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403

def blog_lista(request):
    """Lista publicada de posts. SEO-friendly."""
    from ..models import PostBlog
    from django.utils import timezone
    posts = PostBlog.objects.filter(
        publicado=True,
        publicado_em__lte=timezone.now(),
    ).select_related('autor')
    return render(request, 'blog_lista.html', {'posts': posts})

def blog_detalhe(request, slug):
    """Detalhe de um post. Suporta markdown no corpo."""
    from django.shortcuts import get_object_or_404
    from ..models import PostBlog
    from django.utils import timezone

    post = get_object_or_404(
        PostBlog, slug=slug, publicado=True,
        publicado_em__lte=timezone.now(),
    )

    # Relacionados: posts com tags em comum
    tags = [t.strip() for t in post.tags.split(',') if t.strip()]
    relacionados = []
    if tags:
        from django.db.models import Q
        filtro = Q()
        for t in tags:
            filtro |= Q(tags__icontains=t)
        relacionados = list(
            PostBlog.objects.filter(filtro, publicado=True)
            .exclude(id=post.id)[:3]
        )

    return render(request, 'blog_detalhe.html', {
        'post':         post,
        'relacionados': relacionados,
    })
