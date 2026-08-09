"""Sitemap.xml dinâmico — apenas páginas públicas (landing, legais, FAQ, concursos)."""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class PaginasPublicasSitemap(Sitemap):
    """Mapa das páginas públicas, sem login."""
    changefreq = 'monthly'
    priority = 0.7
    protocol = 'https'

    def items(self):
        return [
            ('home', 1.0, 'weekly'),
            ('sobre', 0.9, 'monthly'),
            ('faq', 0.8, 'monthly'),
            ('politica_privacidade', 0.5, 'yearly'),
            ('termos_uso', 0.5, 'yearly'),
            ('cadastro', 0.9, 'monthly'),
            ('guest_quiz', 0.9, 'weekly'),
            ('blog_lista', 0.9, 'weekly'),
        ]

    def location(self, item):
        return reverse(item[0])

    def priority(self, item):
        return item[1]

    def changefreq(self, item):
        return item[2]


class ConcursosLandingSitemap(Sitemap):
    """Landing pages SEO por concurso — priority alta pra Google indexar."""
    changefreq = 'weekly'
    priority = 0.9
    protocol = 'https'

    def items(self):
        # Retorna slugs de concursos com landing dedicada
        from quiz.concurso_landing import CONCURSOS_LANDING
        return list(CONCURSOS_LANDING.keys())

    def location(self, slug):
        return reverse('landing_concurso', args=[slug])


class BlogSitemap(Sitemap):
    """Posts do blog publicados — priority alta pra Google indexar."""
    changefreq = 'weekly'
    priority = 0.8
    protocol = 'https'

    def items(self):
        from quiz.models import PostBlog
        from django.utils import timezone
        return PostBlog.objects.filter(
            publicado=True, publicado_em__lte=timezone.now(),
        )

    def location(self, post):
        return reverse('blog_detalhe', args=[post.slug])

    def lastmod(self, post):
        return post.atualizado_em
