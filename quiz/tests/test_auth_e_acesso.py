"""
Testes de autenticação, IDOR e proteções.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from quiz.models import Simulado, GrupoEstudo, MembroGrupo, CupomDesconto


User = get_user_model()


class TestAcessoSemLogin(TestCase):
    def setUp(self):
        self.c = Client()

    def test_dashboard_exige_login(self):
        r = self.c.get('/dashboard/', follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn('login', r.url)

    def test_painel_xp_exige_login(self):
        r = self.c.get('/xp/', follow=False)
        self.assertEqual(r.status_code, 302)

    def test_perfil_exige_login(self):
        r = self.c.get('/perfil/', follow=False)
        self.assertEqual(r.status_code, 302)


class TestIDOR(TestCase):
    """Garante que usuário Bob não acessa dados da Alice."""

    def setUp(self):
        self.alice = User.objects.create_user('alice', password='senha123')
        self.bob   = User.objects.create_user('bob',   password='senha123')
        self.sim_alice = Simulado.objects.create(
            usuario=self.alice, finalizado=True, finalizado_em=timezone.now()
        )
        self.grupo_alice = GrupoEstudo.objects.create(
            nome='Grupo da Alice', criador=self.alice,
        )
        MembroGrupo.objects.create(grupo=self.grupo_alice, usuario=self.alice, papel='admin')

    def test_bob_nao_acessa_simulado_da_alice(self):
        c = Client(); c.force_login(self.bob)
        r = c.get(f'/simulado/{self.sim_alice.id}/resultado/', follow=False)
        # Redirect (302) é OK — o sistema bloqueou
        self.assertIn(r.status_code, (302, 404))

    def test_bob_nao_finaliza_simulado_da_alice(self):
        sim = Simulado.objects.create(usuario=self.alice, finalizado=False)
        c = Client(); c.force_login(self.bob)
        c.get(f'/simulado/{sim.id}/finalizar/', follow=False)
        sim.refresh_from_db()
        self.assertFalse(sim.finalizado, 'Bob conseguiu finalizar simulado da Alice (IDOR)')

    def test_bob_nao_acessa_grupo_privado_da_alice(self):
        c = Client(); c.force_login(self.bob)
        r = c.get(f'/grupos/{self.grupo_alice.id}/', follow=False)
        self.assertIn(r.status_code, (302, 404))


class TestCupomDesconto(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('joao', password='senha123')
        self.cupom = CupomDesconto.objects.create(
            codigo='WELCOME30', plano_alvo='pro', dias=30, usos_max=10,
        )

    def test_aplicar_cupom_valido(self):
        c = Client(); c.force_login(self.user)
        r = c.post('/cupom/aplicar/', {'codigo': 'WELCOME30'}, follow=False)
        self.cupom.refresh_from_db()
        self.assertEqual(self.cupom.usos_feitos, 1)

    def test_cupom_inexistente(self):
        c = Client(); c.force_login(self.user)
        r = c.post('/cupom/aplicar/', {'codigo': 'NAOEXISTE'}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.cupom.refresh_from_db()
        self.assertEqual(self.cupom.usos_feitos, 0)

    def test_mesmo_cupom_so_uma_vez_por_usuario(self):
        c = Client(); c.force_login(self.user)
        c.post('/cupom/aplicar/', {'codigo': 'WELCOME30'})
        c.post('/cupom/aplicar/', {'codigo': 'WELCOME30'})  # segunda tentativa
        self.cupom.refresh_from_db()
        self.assertEqual(self.cupom.usos_feitos, 1)
