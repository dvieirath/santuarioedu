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
# Dedup por hash SHA-256 do enunciado normalizado
# ══════════════════════════════════════════════════════════════════════════════
class TestDedupHashQuestao(TestCase):
    """Confirma que Questao.save() calcula texto_hash automatico e que
    variacoes triviais (espacos, acentos, pontuacao) dao mesmo hash."""

    def setUp(self):
        self.cat = Categoria.objects.create(nome='TestDedup')

    def test_hash_calculado_no_save(self):
        q = Questao.objects.create(categoria=self.cat, texto='Enunciado teste 1')
        self.assertEqual(len(q.texto_hash), 64)  # SHA-256 hex = 64 chars

    def test_hash_igual_ignora_acentos_case_pontuacao(self):
        """'Administração' e 'administracao' devem hasear igual."""
        from quiz.models import _hash_texto_questao
        h1 = _hash_texto_questao('Administração Pública — princípios básicos.')
        h2 = _hash_texto_questao('administracao publica principios basicos')
        h3 = _hash_texto_questao('ADMINISTRAÇÃO PÚBLICA! PRINCÍPIOS BÁSICOS?')
        self.assertEqual(h1, h2)
        self.assertEqual(h1, h3)

    def test_hash_diferente_pra_textos_diferentes(self):
        from quiz.models import _hash_texto_questao
        h1 = _hash_texto_questao('Enunciado A completo aqui longo texto')
        h2 = _hash_texto_questao('Enunciado B completamente diferente')
        self.assertNotEqual(h1, h2)

    def test_texto_vazio_hash_vazio(self):
        from quiz.models import _hash_texto_questao
        self.assertEqual(_hash_texto_questao(''), '')
        self.assertEqual(_hash_texto_questao(None), '')


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


# ══════════════════════════════════════════════════════════════════════════════
# Streak freeze (feature retention critica)
# ══════════════════════════════════════════════════════════════════════════════
class TestStreakFreeze(TestCase):
    """Valida que streak freeze protege contra churn quando user pula 1 dia."""

    def setUp(self):
        from quiz.models import MetaEstudo
        self.user_free = User.objects.create_user(username='sf_free', password='x', email='f@t.com')
        self.user_pro = User.objects.create_user(username='sf_pro', password='x', email='p@t.com')
        PlanoUsuario.objects.create(usuario=self.user_free, plano='gratuito', ativo=True)
        PlanoUsuario.objects.create(usuario=self.user_pro, plano='pro', ativo=True)
        self.meta_free = MetaEstudo.objects.create(usuario=self.user_free)
        self.meta_pro = MetaEstudo.objects.create(usuario=self.user_pro)

    def test_cap_freezes_por_plano(self):
        self.assertEqual(self.meta_free.cap_freezes(), 1)
        self.assertEqual(self.meta_pro.cap_freezes(), 3)

    def test_gap_1_dia_nao_usa_freeze(self):
        """Estudou ontem — sequencia natural, freeze permanece."""
        self.meta_free.streak_atual = 5
        self.meta_free.streak_freezes = 1
        self.meta_free.ultimo_estudo = timezone.localdate() - timedelta(days=1)
        self.meta_free.save()

        usou = self.meta_free.atualizar_streak()
        self.meta_free.refresh_from_db()

        self.assertFalse(usou)
        self.assertEqual(self.meta_free.streak_atual, 6)
        self.assertEqual(self.meta_free.streak_freezes, 1)

    def test_gap_2_dias_com_freeze_consome(self):
        """Pulou 1 dia mas tem freeze — consome e mantem streak, cria notif."""
        from quiz.models import Notificacao

        self.meta_pro.streak_atual = 10
        self.meta_pro.streak_freezes = 2
        self.meta_pro.ultimo_estudo = timezone.localdate() - timedelta(days=2)
        self.meta_pro.save()

        usou = self.meta_pro.atualizar_streak()
        self.meta_pro.refresh_from_db()

        self.assertTrue(usou)
        self.assertEqual(self.meta_pro.streak_atual, 11)
        self.assertEqual(self.meta_pro.streak_freezes, 1)
        self.assertEqual(self.meta_pro.total_freezes_usados, 1)
        # Notif de streak protegido criada
        self.assertTrue(Notificacao.objects.filter(usuario=self.user_pro, tipo='streak').exists())

    def test_gap_2_dias_sem_freeze_zera(self):
        """Sem freeze disponivel, streak zera."""
        self.meta_free.streak_atual = 10
        self.meta_free.streak_freezes = 0
        self.meta_free.ultimo_estudo = timezone.localdate() - timedelta(days=2)
        self.meta_free.save()

        usou = self.meta_free.atualizar_streak()
        self.meta_free.refresh_from_db()

        self.assertFalse(usou)
        self.assertEqual(self.meta_free.streak_atual, 1)

    def test_gap_3_dias_com_freeze_zera_sem_gastar(self):
        """Gap > 2 dias nao pode ser salvo — economiza freeze."""
        self.meta_pro.streak_atual = 10
        self.meta_pro.streak_freezes = 3
        self.meta_pro.ultimo_estudo = timezone.localdate() - timedelta(days=3)
        self.meta_pro.save()

        usou = self.meta_pro.atualizar_streak()
        self.meta_pro.refresh_from_db()

        self.assertFalse(usou)
        self.assertEqual(self.meta_pro.streak_atual, 1)
        self.assertEqual(self.meta_pro.streak_freezes, 3, 'freeze economizado pra proxima oportunidade')

    def test_repor_freeze_respeita_cap(self):
        """Free cap=1, PRO cap=3. Reposicao nao ultrapassa."""
        self.meta_free.streak_freezes = 0
        self.meta_free.save()
        self.assertTrue(self.meta_free.repor_freeze())
        self.meta_free.refresh_from_db()
        self.assertEqual(self.meta_free.streak_freezes, 1)

        # Tenta repor novamente — ja no cap free (1)
        self.assertFalse(self.meta_free.repor_freeze())
        self.meta_free.refresh_from_db()
        self.assertEqual(self.meta_free.streak_freezes, 1)

        # PRO consegue chegar em 3
        self.meta_pro.streak_freezes = 0
        self.meta_pro.save()
        for i in range(5):
            self.meta_pro.repor_freeze()
        self.meta_pro.refresh_from_db()
        self.assertEqual(self.meta_pro.streak_freezes, 3, 'PRO capped em 3')
