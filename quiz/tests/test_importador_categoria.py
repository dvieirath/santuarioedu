"""
Importador de provas: categoria de destino.

Antes, quando a classificação por IA falhava (ou devolvia só a raiz), a questão
ia para "Direito > Direito Constitucional", e qualquer texto devolvido pela IA
virava categoria nova. Agora ela fica em "A classificar", pendente, e nenhum
caminho de aprovação libera questão que ainda está lá.
"""
import io
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import OutputWrapper
from django.test import TestCase

from quiz.auditoria import FLAGS_GRAVES, detectar_flags
from quiz.categorias_pendentes import (
    NOME_A_CLASSIFICAR, categoria_a_classificar, eh_a_classificar,
)
from quiz.management.commands.importar_pdf_questoes import Command
from quiz.models import Alternativa, Categoria, Questao

JUSTIFICATIVA = 'Explicação longa o bastante para passar na regra de tamanho mínimo da validação.'


def _comando():
    cmd = Command()
    cmd.stdout = OutputWrapper(io.StringIO())
    return cmd


def _item(texto):
    return {
        'texto': texto,
        'tipo': 'ME',
        'alternativas': [
            {'texto': 'Alternativa A', 'correta': True},
            {'texto': 'Alternativa B', 'correta': False},
            {'texto': 'Alternativa C', 'correta': False},
            {'texto': 'Alternativa D', 'correta': False},
            {'texto': 'Alternativa E', 'correta': False},
        ],
    }


class ResolverCategoriaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.direito = Categoria.objects.create(nome='Direito')
        cls.constitucional = Categoria.objects.create(nome='Direito Constitucional', parent=cls.direito)
        cls.areas = Categoria.objects.create(nome='Áreas Específicas')

    def test_desce_ate_o_nivel_mais_profundo_que_existe(self):
        cat = _comando()._resolver_categoria_path(
            'Direito > Direito Constitucional > Tópico Que Não Existe', {})
        self.assertEqual(cat, self.constitucional)

    def test_ignora_acento_e_maiusculas(self):
        self.assertEqual(_comando()._resolver_categoria_path('areas especificas', {}), self.areas)

    def test_primeiro_nivel_inexistente_devolve_none(self):
        self.assertIsNone(_comando()._resolver_categoria_path('Geologia > Petróleo', {}))

    def test_nunca_cria_categoria(self):
        antes = Categoria.objects.count()
        cmd = _comando()
        for path in ('Geologia', 'Direito > Inventada', 'Direito Ambiental não está disponível, então:'):
            cmd._resolver_categoria_path(path, {})
        self.assertEqual(Categoria.objects.count(), antes)


class ImportacaoSemDestinoPadraoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        direito = Categoria.objects.create(nome='Direito')
        cls.constitucional = Categoria.objects.create(nome='Direito Constitucional', parent=direito)
        cls.areas = Categoria.objects.create(nome='Áreas Específicas')

    def _importar(self, resposta_ia, texto):
        opts = {'auto_categoria': True, 'com_justificativa': False}
        with patch('quiz.ai_provider.gerar_conteudo', **resposta_ia), patch('time.sleep'):
            _comando()._salvar_questoes([_item(texto)], None, 'Cesgranrio', 2023, opts)
        return Questao.objects.get(texto=texto)

    def test_falha_da_ia_vai_para_a_espera_e_nao_para_constitucional(self):
        from quiz.ai_provider import AIError
        q = self._importar({'side_effect': AIError('sem quota')},
                           'Questão de geologia do petróleo importada sem classificação')
        self.assertEqual(q.categoria.nome, NOME_A_CLASSIFICAR)
        self.assertIsNone(q.categoria.parent)
        self.assertFalse(q.revisada)
        self.assertEqual(Questao.objects.filter(categoria=self.constitucional).count(), 0)

    def test_resposta_so_com_a_raiz_e_aceita(self):
        q = self._importar({'return_value': 'Areas Especificas'},
                           'Questão de termodinâmica classificada apenas na raiz')
        self.assertEqual(q.categoria, self.areas)

    def test_texto_inventado_pela_ia_nao_vira_categoria(self):
        antes = set(Categoria.objects.values_list('nome', flat=True))
        q = self._importar(
            {'return_value': 'Direito Ambiental não está disponível, então a resposta mais próxima seria:'},
            'Questão cuja classificação voltou como frase em vez de caminho')
        self.assertEqual(q.categoria.nome, NOME_A_CLASSIFICAR)
        depois = set(Categoria.objects.values_list('nome', flat=True))
        self.assertEqual(depois - antes, {NOME_A_CLASSIFICAR})

    def test_caminho_valido_continua_funcionando(self):
        q = self._importar({'return_value': 'Direito > Direito Constitucional'},
                           'Questão de direitos fundamentais classificada corretamente')
        self.assertEqual(q.categoria, self.constitucional)


class NadaLiberaQuestaoNaEsperaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_superuser(
            username='revisor_espera', email='revisor@example.test', password='x')
        cls.normal = Categoria.objects.create(nome='Disciplina definida')

    def _questao(self, categoria, texto, ia=False):
        q = Questao.objects.create(
            categoria=categoria, texto=texto, tipo='ME',
            justificativa=JUSTIFICATIVA, gerada_por_ia=ia)
        for i, letra in enumerate('ABCDE'):
            Alternativa.objects.create(questao=q, texto=f'Alternativa {letra}', correta=(i == 0))
        return q

    def setUp(self):
        self.client.force_login(self.staff)
        self.na_espera = self._questao(
            categoria_a_classificar(), 'Enunciado completo de uma questão que aguarda classificação.')
        self.classificada = self._questao(
            self.normal, 'Enunciado completo de uma questão já classificada em disciplina.')

    def _revisada(self, q):
        q.refresh_from_db()
        return q.revisada

    def test_auditoria_marca_como_defeito_grave(self):
        self.assertIn('categoria_a_classificar', FLAGS_GRAVES)
        self.assertTrue(eh_a_classificar(self.na_espera))
        self.assertIn('categoria_a_classificar', detectar_flags(self.na_espera))
        self.assertNotIn('categoria_a_classificar', detectar_flags(self.classificada))

    def test_validacao_automatica_nao_aprova(self):
        call_command('validar_questoes_auto', stdout=io.StringIO())
        self.assertFalse(self._revisada(self.na_espera))
        self.assertTrue(self._revisada(self.classificada))

    def test_aprovacao_individual_no_painel_e_recusada(self):
        r = self.client.post(f'/admin-revisao/acao/{self.na_espera.id}/', {'acao': 'aprovar'})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['erro'], 'sem_categoria')
        self.assertFalse(self._revisada(self.na_espera))

        r = self.client.post(f'/admin-revisao/acao/{self.classificada.id}/', {'acao': 'aprovar'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self._revisada(self.classificada))

    def test_aprovacao_em_lote_no_painel_pula(self):
        r = self.client.post(
            '/api/admin/revisao/bulk-approve/',
            data=json.dumps({'apenas_ia': False, 'apenas_com_justif': True}),
            content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['ids_aprovadas'], [self.classificada.id])
        self.assertFalse(self._revisada(self.na_espera))

    def test_acoes_do_django_admin_pulam(self):
        for acao in ('aprovar_revisao', 'aprovar_se_valida'):
            with self.subTest(acao=acao):
                Questao.objects.update(revisada=False)
                r = self.client.post('/admin/quiz/questao/', {
                    'action': acao,
                    '_selected_action': [self.na_espera.id, self.classificada.id],
                })
                self.assertEqual(r.status_code, 302)
                self.assertFalse(self._revisada(self.na_espera))
                self.assertTrue(self._revisada(self.classificada))
