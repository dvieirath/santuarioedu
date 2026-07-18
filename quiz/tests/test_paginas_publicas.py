"""
Testes das páginas públicas — devem responder sem login.
"""
from django.test import TestCase, Client


class TestPaginasPublicas(TestCase):
    def setUp(self):
        self.c = Client()

    def test_landing_responde_200(self):
        r = self.c.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'SantuarioEdu', r.content)

    def test_faq_responde_200(self):
        r = self.c.get('/faq/')
        self.assertEqual(r.status_code, 200)

    def test_politica_privacidade_responde_200(self):
        r = self.c.get('/legal/privacidade/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'LGPD', r.content)

    def test_termos_uso_responde_200(self):
        r = self.c.get('/legal/termos/')
        self.assertEqual(r.status_code, 200)

    def test_health_check(self):
        r = self.c.get('/health/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/json')

    def test_robots_txt(self):
        r = self.c.get('/robots.txt')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Disallow: /admin/', r.content)

    def test_sitemap_xml(self):
        r = self.c.get('/sitemap.xml')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'<urlset', r.content)

    def test_404_personalizada(self):
        r = self.c.get('/url-que-nao-existe/')
        self.assertEqual(r.status_code, 404)

    def test_headers_seguranca(self):
        r = self.c.get('/')
        # X-Frame-Options sempre presente (anti-clickjacking)
        self.assertIn('X-Frame-Options', r)
        # Permissions-Policy do nosso middleware custom
        self.assertIn('Permissions-Policy', r)
        # CSP do django-csp
        self.assertIn('Content-Security-Policy', r)
