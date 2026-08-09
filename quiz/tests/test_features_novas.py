"""
Smoke tests para features desta sessao (2026-08):
- Hub Preparacao (/preparacao/<slug>/)
- Meu Edital (/meu-edital/)
- Coach IA (/coach/, /coach/anotacoes/)
- Curva Esquecimento (/curva-esquecimento/)
- Progresso Edital Vivo (/progresso-edital-vivo/)
- Simulado sob Medida (/simulado/sob-medida/)
- Ranking por concurso (/ranking-concurso/<slug>/)
- Modo intensivo (/intensivo/<cat_id>/)
- Simulado estilo banca (/simulado/estilo-banca/)
- Admin Status (/admin-status/)
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse


class TestFeaturesNovas(TestCase):
    """Garante que rotas novas retornam 200/302 esperado."""

    @classmethod
    def setUpTestData(cls):
        U = get_user_model()
        cls.user = U.objects.create_user(
            username='teste_features',
            email='teste@santuarioedu.com.br',
            password='SenhaForte123!',
            is_staff=True,  # pra admin_status
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_preparacao_concurso_prf(self):
        r = self.client.get('/preparacao/prf/')
        self.assertEqual(r.status_code, 200)

    def test_preparacao_concurso_inss(self):
        r = self.client.get('/preparacao/inss/')
        self.assertEqual(r.status_code, 200)

    def test_preparacao_concurso_slug_invalido(self):
        r = self.client.get('/preparacao/nao-existe/')
        self.assertEqual(r.status_code, 404)

    def test_meu_edital(self):
        r = self.client.get('/meu-edital/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'edital', r.content.lower())

    def test_coach_ia(self):
        r = self.client.get('/coach/')
        self.assertEqual(r.status_code, 200)

    def test_coach_ia_anotacoes(self):
        r = self.client.get('/coach/anotacoes/')
        self.assertEqual(r.status_code, 200)

    def test_curva_esquecimento(self):
        r = self.client.get('/curva-esquecimento/')
        self.assertEqual(r.status_code, 200)

    def test_progresso_edital_vivo(self):
        r = self.client.get('/progresso-edital-vivo/')
        self.assertEqual(r.status_code, 200)

    def test_escolher_estilo_banca(self):
        r = self.client.get('/simulado/estilo-banca/')
        self.assertEqual(r.status_code, 200)

    def test_ranking_concurso(self):
        r = self.client.get('/ranking-concurso/prf/')
        self.assertEqual(r.status_code, 200)

    def test_admin_status(self):
        r = self.client.get('/admin-status/')
        self.assertEqual(r.status_code, 200)

    def test_admin_status_bloqueia_nao_staff(self):
        u = get_user_model().objects.create_user(
            username='naostaff', email='ns@t.com', password='x!',
            is_staff=False,
        )
        c = Client()
        c.force_login(u)
        r = c.get('/admin-status/', follow=False)
        # Redireciona (302) pra home
        self.assertEqual(r.status_code, 302)


class TestGuestQuiz(TestCase):
    """Guest quiz mode — sem cadastro."""

    def test_guest_quiz_publico(self):
        """Rota /testar/ eh publica."""
        c = Client()
        r = c.get('/testar/')
        # 200 se tem questoes no BD, 302 se redireciona pra cadastro
        self.assertIn(r.status_code, (200, 302))

    def test_guest_quiz_reset(self):
        c = Client()
        r = c.get('/testar/reset/')
        self.assertEqual(r.status_code, 302)  # sempre redireciona


class TestLandingsPublicas(TestCase):
    """Landings SEO por concurso."""

    def test_home(self):
        r = self.client.get('/')
        # 200 se anonimo, 302 se logado (redirect dashboard)
        self.assertIn(r.status_code, (200, 302))

    def test_landing_prf(self):
        r = self.client.get('/concurso/prf/')
        self.assertEqual(r.status_code, 200)

    def test_landing_slug_invalido(self):
        r = self.client.get('/concurso/nao-existe/')
        self.assertEqual(r.status_code, 404)
