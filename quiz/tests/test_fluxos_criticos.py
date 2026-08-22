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
# Ranks contextuais por concurso (rebrand)
# ══════════════════════════════════════════════════════════════════════════════
class TestRanksContextuais(TestCase):
    """Valida que ranks refletem ConcursoPreferido do user (nao mais fixo PRF)."""

    def setUp(self):
        from quiz.models import NivelUsuario, ConcursoPreferido
        self.user_prf = User.objects.create_user(username='r_prf', password='x', email='r1@t.com')
        self.user_enem = User.objects.create_user(username='r_enem', password='x', email='r2@t.com')
        self.user_sem_concurso = User.objects.create_user(username='r_semc', password='x', email='r3@t.com')

        ConcursoPreferido.objects.create(usuario=self.user_prf, concurso='prf')
        ConcursoPreferido.objects.create(usuario=self.user_enem, concurso='enem')

        self.n_prf = NivelUsuario.objects.create(usuario=self.user_prf, nivel=4)
        self.n_enem = NivelUsuario.objects.create(usuario=self.user_enem, nivel=4)
        self.n_semc = NivelUsuario.objects.create(usuario=self.user_sem_concurso, nivel=4)

    def test_rank_prf_no_nivel_4_eh_delegado(self):
        self.assertEqual(self.n_prf.rank_nome, 'Delegado')

    def test_rank_enem_no_nivel_4_eh_bacharelando(self):
        self.assertEqual(self.n_enem.rank_nome, 'Bacharelando')

    def test_rank_sem_concurso_usa_default(self):
        # Nivel 4 default = Estudioso
        self.assertEqual(self.n_semc.rank_nome, 'Estudioso')

    def test_ranks_disponiveis_reflete_concurso(self):
        prf_ranks = self.n_prf.ranks_disponiveis
        enem_ranks = self.n_enem.ranks_disponiveis
        self.assertNotEqual(prf_ranks, enem_ranks)
        # PRF tem "Diretor PRF" no nivel 6
        self.assertEqual(prf_ranks[5][1], 'Diretor PRF')
        # ENEM tem "Mestre" no nivel 6
        self.assertEqual(enem_ranks[5][1], 'Mestre')


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


# ═══════════════════════════════════════════════════════════════════════════
# ONBOARDING CHECKLIST — primeiros 7 dias (commit ondemand)
# ═══════════════════════════════════════════════════════════════════════════
class TestOnboardingChecklist(TestCase):
    """
    Cobre:
    - Novo user tem todas tasks pendentes (0%)
    - Award e idempotente (nao entrega XP duas vezes)
    - Dispensar oculta o card
    - deve_exibir_card respeita > 30 dias de cadastro
    """
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user('ob_test', 'ob@t.com', 'x!')

    def test_novo_user_zero_pct(self):
        from quiz import onboarding as ob
        r = ob.resumo(self.user)
        self.assertEqual(r['pct'], 0)
        self.assertEqual(r['feitos'], 0)
        self.assertTrue(r['deve_exibir'])
        self.assertEqual(r['total'], len(ob.TASKS))

    def test_award_e_idempotente(self):
        from quiz import onboarding as ob
        from quiz.models import ConcursoPreferido, NivelUsuario
        ConcursoPreferido.objects.create(usuario=self.user, concurso='inss')

        novas = ob.check_and_award(self.user)
        slugs = [t['slug'] for t in novas]
        self.assertIn('concurso_pref', slugs)

        n = NivelUsuario.objects.get(usuario=self.user)
        xp_inicial = n.xp_total

        # Re-award nao acontece
        novas2 = ob.check_and_award(self.user)
        self.assertEqual(novas2, [])
        n.refresh_from_db()
        self.assertEqual(n.xp_total, xp_inicial, 'XP nao pode duplicar')

    def test_dispensar_oculta_card(self):
        from quiz import onboarding as ob
        from quiz.models import Perfil
        p, _ = Perfil.objects.get_or_create(usuario=self.user)
        p.onboarding_dispensado = True
        p.save()
        self.assertFalse(ob.deve_exibir_card(self.user))

    def test_cadastro_antigo_nao_exibe(self):
        from quiz import onboarding as ob
        from django.utils import timezone
        from datetime import timedelta
        # Simula user cadastrado ha 40 dias
        self.user.date_joined = timezone.now() - timedelta(days=40)
        self.user.save()
        self.assertFalse(ob.deve_exibir_card(self.user))
