"""Sitemap.xml dinâmico — apenas páginas públicas (landing, legais, FAQ)."""
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
            ('faq', 0.8, 'monthly'),
            ('politica_privacidade', 0.5, 'yearly'),
            ('termos_uso', 0.5, 'yearly'),
            ('cadastro', 0.9, 'monthly'),
        ]

    def location(self, item):
        return reverse(item[0])

    def priority(self, item):
        return item[1]

    def changefreq(self, item):
        return item[2]
