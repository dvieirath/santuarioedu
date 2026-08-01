"""
Testes de regressao dos fluxos criticos.

Cobre bugs REAIS que aconteceram em prod:
1. slice.first() no iniciar_quiz (TypeError) — commit dbad4dd
2. endif orfao em resultado.html — commit dbad4dd
3. Webhook MP nao idempotente — commit 297c7e9
4. Trial sobrescreve plano pago — commit 297c7e9
5. /api/upgrade/ liberado em prod — commit 297c7e9
6. Cupom race condition — commit 8d60d9c
7. Seed hierarquia idempotente — commit 4e7a84e
8. Busca hierarquica — commit ed00cc0

Rodar:
    python manage.py test quiz.tests.test_fluxos_criticos
"""
import json
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from quiz.models import (
    Categoria, Questao, Alternativa, RespostaUsuario,
    PlanoUsuario, MetaEstudo, CupomDesconto, UsoCupom,
    PagamentoMP,
)

User = get_user_model()


# ══════════════════════════════════════════════════════════════════════════════
# BUG 1+2: Fluxo responder questao (slice.first + endif orfao)
# ══════════════════════════════════════════════════════════════════════════════
class TestResponderQuestao(TestCase):
    """Cobre o bug do slice.first() que quebrou quiz inteiro em prod."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='resp', password='xyz', email='r@t.com',
        )
        PlanoUsuario.objects.update_or_create(
            usuario=self.user,
            defaults={'plano': 'pro', 'ativo': True},
        )
        MetaEstudo.objects.get_or_create(usuario=self.user)

        self.cat = Categoria.objects.create(nome='Test Cat')
        self.questao = Questao.objects.create(
            categoria=self.cat, texto='Q1', revisada=True,
        )
        self.alt_correta = Alternativa.objects.create(
            questao=self.questao, texto='A correta', correta=True,
        )
        self.alt_errada = Alternativa.objects.create(
            questao=self.questao, texto='B errada', correta=False,
        )

        self.client = Client()
        self.client.force_login(self.user)

    def test_get_quiz_por_categoria_nao_crasha(self):
        """Regressao: slice[N:N+1].first() dava TypeError. Deve retornar 200."""
        r = self.client.get(f'/quiz/{self.cat.id}/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.questao.texto)

    def test_post_resposta_correta_renderiza_resultado(self):
        """Regressao: endif orfao em resultado.html crashava aqui."""
        r = self.client.post('/quiz/', {
            'alternativa_id': self.alt_correta.id,
            'categoria_id': self.cat.id,
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Resposta correta')

    def test_post_resposta_errada_mostra_certa(self):
        r = self.client.post('/quiz/', {
            'alternativa_id': self.alt_errada.id,
            'categoria_id': self.cat.id,
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Resposta incorreta')
        self.assertContains(r, self.alt_correta.texto)

    def test_idempotencia_mesma_questao_hoje(self):
        """F5 na tela de resultado NAO duplica RespostaUsuario/XP/streak."""
        self.client.post('/quiz/', {
            'alternativa_id': self.alt_correta.id,
            'categoria_id': self.cat.id,
        })
        n1 = RespostaUsuario.objects.filter(usuario=self.user).count()

        # Segundo POST — mesma questao, mesmo dia
        self.client.post('/quiz/', {
            'alternativa_id': self.alt_correta.id,
            'categoria_id': self.cat.id,
        })
        n2 = RespostaUsuario.objects.filter(usuario=self.user).count()
        self.assertEqual(n1, n2, 'Idempotencia falhou — resposta duplicou')

    def test_alternativa_id_invalido_nao_500(self):
        """Regressao: Alternativa.objects.get() sem try/except dava 500."""
        r = self.client.post('/quiz/', {
            'alternativa_id': '',
            'categoria_id': self.cat.id,
        })
        # Deve redirecionar com msg de erro (nao 500)
        self.assertIn(r.status_code, (301, 302))


# ══════════════════════════════════════════════════════════════════════════════
# BUG 3: Webhook MP idempotente
# ══════════════════════════════════════════════════════════════════════════════
class TestWebhookMPIdempotente(TestCase):
    """Regressao Batch 1 — antes MP retry dava +30 dias multiplos."""

    def setUp(self):
        self.user = User.objects.create_user(username='wh', password='x', email='wh@t.com')
        self.pagamento = PagamentoMP.objects.create(
            usuario=self.user,
            plano_alvo='pro',
            valor_centavos=1490,
            status='pending',
            payment_id='',
        )

    @override_settings(MP_ACCESS_TOKEN='FAKE_TOKEN', MP_WEBHOOK_SECRET='')
    @patch('quiz.mercadopago_service.consultar_payment')
    def test_webhook_duplicado_nao_soma_dias(self, mock_consultar):
        """MP retry envia mesma notification 2x -> nao deve empilhar 60 dias."""
        # 1a chamada: MP retorna 'approved'
        mock_consultar.return_value = {
            'id': '12345',
            'status': 'approved',
            'external_reference': str(self.pagamento.id),
        }

        c = Client()
        # Simula webhook
        r = c.post('/pagamento/webhook/',
                   json.dumps({'type': 'payment', 'data': {'id': '12345'}}),
                   content_type='application/json')
        self.assertEqual(r.status_code, 200)

        # Verifica plano ativado — deve ter expira_em ~30d
        self.pagamento.refresh_from_db()
        self.assertEqual(self.pagamento.status, 'approved')
        plano = PlanoUsuario.objects.get(usuario=self.user)
        expira_1 = plano.expira_em
        self.assertIsNotNone(expira_1)

        # 2a chamada: mesmo webhook (MP retry)
        r = c.post('/pagamento/webhook/',
                   json.dumps({'type': 'payment', 'data': {'id': '12345'}}),
                   content_type='application/json')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertEqual(data.get('skipped'), 'ja_processado')

        # Plano NAO deve ter ganho +30 dias adicionais
        plano.refresh_from_db()
        self.assertEqual(plano.expira_em, expira_1,
                         'Bug: webhook duplicado somou dias')


# ══════════════════════════════════════════════════════════════════════════════
# BUG 4: Trial nao sobrescreve pago
# ══════════════════════════════════════════════════════════════════════════════
class TestTrialNaoSobrescrevePago(TestCase):
    """Regressao Batch 1 — trial 7d apagava plano PRO 30d vigente."""

    def setUp(self):
        self.user = User.objects.create_user(username='tr', password='x', email='tr@t.com')

    def test_trial_nao_sobrescreve_pro_ativo(self):
        """User PRO pago -> confirma email secundario -> plano permanece."""
        # Simula pagamento previo: PRO ativo ate 30d
        expira_pago = timezone.now() + timedelta(days=30)
        PlanoUsuario.objects.create(
            usuario=self.user, plano='pro', ativo=True, expira_em=expira_pago,
        )

        # Dispara signal email_confirmed manualmente
        from allauth.account.signals import email_confirmed
        from allauth.account.models import EmailAddress
        email_addr, _ = EmailAddress.objects.get_or_create(
            user=self.user, email='tr@t.com',
            defaults={'verified': True, 'primary': True},
        )
        email_confirmed.send(sender=EmailAddress, request=None, email_address=email_addr)

        # Plano NAO deve ter sido virado pra trial 7d
        plano = PlanoUsuario.objects.get(usuario=self.user)
        self.assertEqual(plano.plano, 'pro')
        # Delta pequeno pra evitar problema de precisao de microsegundos
        self.assertGreater(plano.expira_em, timezone.now() + timedelta(days=25))

    def test_trial_nao_concede_segunda_vez(self):
        """User cujo trial ja expirou NAO ganha novo trial confirmando email."""
        # Trial expirado (plano PRO com expira_em no passado)
        PlanoUsuario.objects.create(
            usuario=self.user, plano='pro', ativo=True,
            expira_em=timezone.now() - timedelta(days=1),
        )

        from allauth.account.signals import email_confirmed
        from allauth.account.models import EmailAddress
        email_addr, _ = EmailAddress.objects.get_or_create(
            user=self.user, email='tr@t.com', defaults={'verified': True, 'primary': True},
        )
        email_confirmed.send(sender=EmailAddress, request=None, email_address=email_addr)

        plano = PlanoUsuario.objects.get(usuario=self.user)
        # Nao deve ter ganho novo trial (expira_em nao mudou pra futuro)
        # Continua com o valor original (passado) OU foi normalizado — mas nao 7d futuro
        if plano.expira_em:
            # Se ainda tem valor, deve ser o passado que ja estava
            self.assertLessEqual(plano.expira_em, timezone.now())


# ══════════════════════════════════════════════════════════════════════════════
# BUG 5: /api/upgrade/ fechado em prod
# ══════════════════════════════════════════════════════════════════════════════
class TestApiUpgradeFechadoEmProd(TestCase):
    """Regressao Batch 1 — endpoint dava PRO gratis em prod."""

    def setUp(self):
        self.user = User.objects.create_user(username='up', password='x', email='up@t.com')
        self.client.force_login(self.user)

    @override_settings(DEBUG=False)
    def test_upgrade_bloqueado_em_prod(self):
        r = self.client.post('/api/upgrade/',
                             json.dumps({'plano': 'pro'}),
                             content_type='application/json')
        # Deve retornar 404 (Http404 raised)
        self.assertEqual(r.status_code, 404)

    @override_settings(DEBUG=True)
    def test_upgrade_funciona_em_dev(self):
        r = self.client.post('/api/upgrade/',
                             json.dumps({'plano': 'pro'}),
                             content_type='application/json')
        # Em dev pode funcionar (aceita ou 400 se algo faltando)
        self.assertNotEqual(r.status_code, 404)


# ══════════════════════════════════════════════════════════════════════════════
# BUG 6: Cupom race condition (F() + atomic)
# ══════════════════════════════════════════════════════════════════════════════
class TestCupomFAtomic(TestCase):
    """Regressao Batch 2 — cupom.usos_feitos += 1 dava race."""

    def test_cupom_incrementa_via_F_expression(self):
        """Confirma que usos_feitos foi incrementado (nao verifica race real,
        so que o mecanismo F() funciona)."""
        cupom = CupomDesconto.objects.create(
            codigo='TEST123', plano_alvo='pro', dias=30,
            usos_max=100, usos_feitos=0, ativo=True,
        )
        user = User.objects.create_user(username='cup', password='x', email='c@t.com')
        c = Client(); c.force_login(user)

        r = c.post('/cupom/aplicar/', {'codigo': 'TEST123'})
        self.assertIn(r.status_code, (200, 301, 302))

        cupom.refresh_from_db()
        self.assertEqual(cupom.usos_feitos, 1)
        self.assertTrue(
            UsoCupom.objects.filter(cupom=cupom, usuario=user).exists()
        )

    def test_cupom_nao_pode_ser_usado_2x_mesmo_user(self):
        """DB constraint UsoCupom.unique_together = (cupom, usuario)."""
        cupom = CupomDesconto.objects.create(
            codigo='DOIS', plano_alvo='pro', dias=30,
            usos_max=100, usos_feitos=0, ativo=True,
        )
        user = User.objects.create_user(username='c2', password='x', email='c2@t.com')
        c = Client(); c.force_login(user)

        c.post('/cupom/aplicar/', {'codigo': 'DOIS'})
        c.post('/cupom/aplicar/', {'codigo': 'DOIS'})

        # Deve ter apenas 1 UsoCupom
        self.assertEqual(
            UsoCupom.objects.filter(cupom=cupom, usuario=user).count(), 1
        )


# ══════════════════════════════════════════════════════════════════════════════
# BUG 7: Seed hierarquia idempotente
# ══════════════════════════════════════════════════════════════════════════════
class TestSeedHierarquiaIdempotente(TestCase):
    """Regressao commit 4e7a84e — rodar 2x nao deve quebrar."""

    def test_seed_pode_rodar_multiplas_vezes(self):
        from django.core.management import call_command
        from io import StringIO

        # 1a execucao
        out1 = StringIO()
        call_command('seed_hierarquia_canonica', '--aplicar', stdout=out1)
        n1 = Categoria.objects.count()

        # 2a execucao — nao deve quebrar
        out2 = StringIO()
        try:
            call_command('seed_hierarquia_canonica', '--aplicar', stdout=out2)
        except Exception as e:
            self.fail(f'Seed nao eh idempotente: {e}')

        n2 = Categoria.objects.count()
        self.assertEqual(n1, n2, 'Seed criou duplicatas na 2a execucao')


# ══════════════════════════════════════════════════════════════════════════════
# BUG 8: Busca hierarquica em /estudar/
# ══════════════════════════════════════════════════════════════════════════════
class TestBuscaHierarquica(TestCase):
    """Regressao ed00cc0 — busca ?q=x deve achar em qualquer nivel."""

    def setUp(self):
        self.user = User.objects.create_user(username='bh', password='x', email='b@t.com')
        self.client.force_login(self.user)

        # Cria hierarquia: Ciencias > Biologia > Anatomia Humana
        self.raiz = Categoria.objects.create(nome='Ciencias')
        self.biologia = Categoria.objects.create(nome='Biologia', parent=self.raiz)
        self.anatomia = Categoria.objects.create(nome='Anatomia Humana', parent=self.biologia)

    def test_busca_acha_categoria_folha(self):
        r = self.client.get('/estudar/?q=anatomia')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Anatomia Humana')
        # Deve mostrar caminho completo (breadcrumb hierarquico)
        self.assertContains(r, 'Ciencias')

    def test_busca_acha_categoria_pai(self):
        r = self.client.get('/estudar/?q=biologia')
        self.assertContains(r, 'Biologia')

    def test_busca_sem_resultados_nao_crasha(self):
        r = self.client.get('/estudar/?q=xyzabc123nao_existe')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '0 resultado')


# ══════════════════════════════════════════════════════════════════════════════
# BUG 9: Toggle favorita exige POST (era GET vulneravel a prefetch)
# ══════════════════════════════════════════════════════════════════════════════
class TestFavoritaRequirePOST(TestCase):
    """Regressao Batch 2 — GET podia toggle favorita via prefetch/<img>."""

    def setUp(self):
        self.user = User.objects.create_user(username='fv', password='x', email='f@t.com')
        self.cat = Categoria.objects.create(nome='C')
        self.questao = Questao.objects.create(categoria=self.cat, texto='Q')

    def test_get_toggle_favorita_rejeita_405(self):
        c = Client(); c.force_login(self.user)
        r = c.get(f'/api/favorita/{self.questao.id}/')
        self.assertEqual(r.status_code, 405, 'toggle_favorita aceita GET — vulneravel a prefetch')

    def test_post_toggle_favorita_funciona(self):
        c = Client(); c.force_login(self.user)
        r = c.post(f'/api/favorita/{self.questao.id}/')
        self.assertEqual(r.status_code, 200)
