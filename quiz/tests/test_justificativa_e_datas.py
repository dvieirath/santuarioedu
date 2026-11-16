"""
Regressões corrigidas em 10/11/2026:

1. Resposta vazia (None ou '') de um provider de IA não derruba mais o lote:
   o orquestrador trata como falha daquele provider e tenta o próximo.
2. Nenhuma tela do aluno gera e grava justificativa por IA sem revisão:
   /api/justificativa/<id>/ é somente leitura e a revisão do simulado não
   chama a IA ao abrir.
3. "Hoje" é o dia do fuso do projeto (America/Sao_Paulo), não o dia UTC.
4. Avisos de limite não falam mais em plano pago.
"""
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from quiz.models import (
    Alternativa, Categoria, Questao, RespostaSimulado, RespostaUsuario, Simulado,
)


class _ProviderFalso:
    """Provider mínimo: devolve o que for configurado em `retorno`."""
    retorno = None
    chamadas = 0

    @classmethod
    def disponivel(cls):
        return True

    @classmethod
    def em_cooldown(cls):
        return False

    @classmethod
    def gerar(cls, prompt, **kwargs):
        cls.chamadas += 1
        return cls.retorno


class _Vazio(_ProviderFalso):
    retorno = None
    chamadas = 0


class _SoEspacos(_ProviderFalso):
    retorno = '   \n'
    chamadas = 0


class _Bom(_ProviderFalso):
    retorno = '{"justificativa": "texto ok"}'
    chamadas = 0


class RespostaVaziaDoProviderTests(TestCase):
    def setUp(self):
        for cls in (_Vazio, _SoEspacos, _Bom):
            cls.chamadas = 0

    @override_settings(AI_PROVIDER_ORDER=['vazio', 'espacos', 'bom'])
    def test_resposta_vazia_cai_para_o_proximo_provider(self):
        from quiz import ai_provider
        falsos = {'vazio': _Vazio, 'espacos': _SoEspacos, 'bom': _Bom}
        with patch.dict(ai_provider.PROVIDERS, falsos, clear=True):
            self.assertEqual(
                ai_provider.gerar_json('explique a questão'),
                {'justificativa': 'texto ok'},
            )
        self.assertEqual((_Vazio.chamadas, _SoEspacos.chamadas, _Bom.chamadas), (1, 1, 1))

    @override_settings(AI_PROVIDER_ORDER=['vazio', 'espacos'])
    def test_todos_vazios_viram_aierror_e_nao_attributeerror(self):
        from quiz import ai_provider
        falsos = {'vazio': _Vazio, 'espacos': _SoEspacos}
        with patch.dict(ai_provider.PROVIDERS, falsos, clear=True):
            with self.assertRaises(ai_provider.AIError) as ctx:
                ai_provider.gerar_json('explique a questão')
        self.assertIn('resposta vazia', str(ctx.exception))


class JustificativaSemGeracaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='sem_geracao')
        cat = Categoria.objects.create(nome='Categoria justificativa')
        cls.sem_just = Questao.objects.create(
            categoria=cat, texto='Liberada sem justificativa', revisada=True)
        cls.com_just = Questao.objects.create(
            categoria=cat, texto='Liberada com justificativa', revisada=True,
            justificativa='Explicação já revisada.')
        cls.pendente = Questao.objects.create(
            categoria=cat, texto='Pendente com rascunho',
            justificativa='Rascunho ainda não revisado.')
        cls.rejeitada = Questao.objects.create(
            categoria=cat, texto='Rejeitada com texto', revisada=True,
            rejeitada_definitiva=True, justificativa='Texto de item rejeitado.')
        for q in (cls.sem_just, cls.com_just, cls.pendente, cls.rejeitada):
            Alternativa.objects.create(questao=q, texto='Certo', correta=True)
            Alternativa.objects.create(questao=q, texto='Errado', correta=False)

    def setUp(self):
        self.client.force_login(self.user)
        # Qualquer chamada de IA nestes testes é um erro.
        proibido = AssertionError('a tela não pode chamar a IA')
        for alvo in ('quiz.ai_provider.gerar_conteudo', 'quiz.ai_service.gerar_justificativa_ia'):
            p = patch(alvo, side_effect=proibido)
            p.start()
            self.addCleanup(p.stop)

    def _simulado_finalizado(self):
        simulado = Simulado.objects.create(usuario=self.user, finalizado=True)
        errada = self.sem_just.alternativa_set.get(correta=False)
        RespostaSimulado.objects.create(
            simulado=simulado, questao=self.sem_just, ordem=1,
            alternativa_escolhida=errada, acertou=False)
        return simulado

    def test_api_devolve_justificativa_revisada(self):
        r = self.client.post(f'/api/justificativa/{self.com_just.id}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'justificativa': 'Explicação já revisada.',
                                    'gerado_agora': False})

    def test_api_nao_gera_nem_grava_quando_nao_ha_justificativa(self):
        r = self.client.post(f'/api/justificativa/{self.sem_just.id}/')
        self.assertEqual(r.status_code, 404)
        self.assertIn('explicação revisada', r.json()['erro'])
        self.sem_just.refresh_from_db()
        self.assertFalse(self.sem_just.justificativa)

    def test_api_nao_expoe_questao_pendente_nem_rejeitada(self):
        for q in (self.pendente, self.rejeitada):
            with self.subTest(q=q.texto):
                r = self.client.post(f'/api/justificativa/{q.id}/')
                self.assertEqual(r.status_code, 404)
                self.assertNotIn(q.justificativa.encode(), r.content)

    def test_revisao_do_simulado_nao_gera_ao_abrir(self):
        simulado = self._simulado_finalizado()
        r = self.client.get(f'/simulado/{simulado.id}/revisao/')
        self.assertEqual(r.status_code, 200)
        self.sem_just.refresh_from_db()
        self.assertFalse(self.sem_just.justificativa)

    def test_revisao_do_simulado_tolera_indice_invalido(self):
        simulado = self._simulado_finalizado()
        for valor in ('abc', '²', '-1', '9' * 500):
            with self.subTest(valor=valor[:8]):
                r = self.client.get(f'/simulado/{simulado.id}/revisao/', {'q': valor})
                self.assertEqual(r.status_code, 200)

    def test_resultado_do_simulado_nao_oferece_geracao(self):
        simulado = self._simulado_finalizado()
        r = self.client.get(f'/simulado/{simulado.id}/resultado/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ainda não tem uma explicação revisada')
        self.assertNotContains(r, '/api/justificativa/')
        self.assertNotContains(r, 'pedirIA')


@override_settings(TIME_ZONE='America/Sao_Paulo', USE_TZ=True)
class DiaLocalTests(TestCase):
    """22h30 de segunda em Brasília já é terça em UTC; o app deve ficar na segunda."""
    # 2026-11-10 01:30 UTC  ==  2026-11-09 22:30 em America/Sao_Paulo (segunda)
    AGORA = datetime(2026, 11, 10, 1, 30, tzinfo=dt_timezone.utc)

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='dia_local')
        cat = Categoria.objects.create(nome='Categoria datas')
        cls.questao = Questao.objects.create(categoria=cat, texto='Questão datas', revisada=True)
        Alternativa.objects.create(questao=cls.questao, texto='Certo', correta=True)

    def setUp(self):
        self.client.force_login(self.user)
        p = patch('django.utils.timezone.now', return_value=self.AGORA)
        p.start()
        self.addCleanup(p.stop)
        RespostaUsuario.objects.create(usuario=self.user, questao=self.questao, acertou=True)
        RespostaUsuario.objects.filter(usuario=self.user).update(data=self.AGORA)

    def test_painel_xp_conta_o_acerto_no_dia_de_hoje(self):
        r = self.client.get('/xp/')
        self.assertEqual(r.status_code, 200)
        hoje = r.context['historico_xp'][-1]
        self.assertEqual(hoje, {'label': '09/11', 'xp': 10})

    def test_metas_semanais_abre_no_dia_local(self):
        self.assertEqual(self.client.get('/metas-semanais/').status_code, 200)


class LimiteDiarioDeIaTests(TestCase):
    @override_settings(IA_CAP_DIARIO_FREE=0)
    def test_aviso_de_limite_nao_fala_em_plano_pago(self):
        from quiz import ai_provider
        cache.clear()
        user = get_user_model().objects.create_user(username='limite_ia')
        with self.assertRaises(ai_provider.AIQuotaExceeded) as ctx:
            ai_provider.gerar_conteudo('pergunta simples', usuario=user)
        msg = str(ctx.exception)
        self.assertIn('limite diário', msg)
        self.assertNotIn('PRO', msg)
        self.assertNotIn('upgrade', msg.lower())
