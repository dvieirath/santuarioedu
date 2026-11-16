"""
Trilha Banco do Brasil, fase 0.

Confere que a especificação bate com o edital 2022/001, que o comando de seed
só acrescenta e pode rodar várias vezes, e que a categoria de espera
"A classificar" não aparece para o aluno.
"""
import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from quiz import trilha_bb
from quiz.categorias_pendentes import NOME_A_CLASSIFICAR, categoria_a_classificar
from quiz.models import Alternativa, Categoria, Questao
from quiz.preparacao import CONCURSO_DISCIPLINAS, _match_categoria


def _seed(*args):
    saida = io.StringIO()
    call_command('seed_trilha_bb', *args, stdout=saida)
    return saida.getvalue()


class EspecificacaoDoEditalTests(TestCase):
    def test_prova_tem_70_questoes_e_100_pontos_nos_dois_cargos(self):
        for slug in ('bb', 'bb-ti'):
            with self.subTest(cargo=slug):
                self.assertEqual(trilha_bb.total_questoes(slug), 70)
                self.assertEqual(trilha_bb.total_pontos(slug), 100.0)
                self.assertEqual(trilha_bb.pontos_por_bloco(slug), {
                    'Conhecimentos Básicos': 32.5,
                    'Conhecimentos Específicos': 67.5,
                })

    def test_pesos_do_agente_comercial(self):
        pontos = {i['nome_edital']: i['pontos'] for i in trilha_bb.itens_do_cargo('bb')}
        self.assertEqual(pontos, {
            'Língua Portuguesa': 15.0,
            'Língua Inglesa': 5.0,
            'Matemática': 7.5,
            'Atualidades do Mercado Financeiro': 5.0,
            'Matemática Financeira': 7.5,
            'Conhecimentos Bancários': 15.0,
            'Conhecimentos de Informática': 22.5,
            'Vendas e Negociação': 22.5,
        })

    def test_pesos_do_agente_de_tecnologia(self):
        especificos = {i['nome_edital']: (i['questoes'], i['pontos'])
                       for i in trilha_bb.itens_do_cargo('bb-ti')
                       if i['bloco'] == 'Conhecimentos Específicos'}
        self.assertEqual(especificos, {
            'Probabilidade e Estatística': (5, 7.5),
            'Conhecimentos Bancários': (5, 7.5),
            'Tecnologia da Informação': (35, 52.5),
        })

    def test_regras_de_eliminacao_e_formato(self):
        e = trilha_bb.EDITAL
        self.assertEqual((e['banca'], e['tipo_questao'], e['alternativas']), ('Cesgranrio', 'ME', 5))
        self.assertEqual(e['aproveitamento_minimo'], 0.5)
        self.assertTrue(e['elimina_zero_em_disciplina'])
        self.assertEqual((e['redacao_minima'], e['redacao_maxima']), (70, 100))
        self.assertEqual(e['duracao_min'], 300)

    def test_topicos_seguem_o_anexo_iii(self):
        itens = {chave: {item for item, _ in d['topicos']} for chave, d in trilha_bb.DISCIPLINAS.items()}
        self.assertEqual(itens['portugues'], set(range(1, 10)))
        self.assertEqual(itens['matematica'], set(range(1, 12)))
        self.assertEqual(itens['atualidades'], set(range(1, 16)))
        self.assertEqual(itens['mat_financeira'], set(range(1, 5)))
        self.assertEqual(itens['bancarios'], set(range(1, 24)))
        self.assertEqual(itens['informatica'], set(range(1, 15)))
        self.assertEqual(itens['vendas'], set(range(1, 18)))
        self.assertEqual(itens['estatistica'], set(range(1, 11)))
        self.assertEqual(itens['ti'], set(range(1, 7)))

    def test_sem_topico_repetido_dentro_da_disciplina(self):
        for chave, d in trilha_bb.DISCIPLINAS.items():
            nomes = [nome for _, nome in d['topicos']]
            self.assertEqual(len(nomes), len(set(nomes)), chave)

    def test_disciplinas_registradas_para_os_dois_cargos(self):
        self.assertEqual(len(CONCURSO_DISCIPLINAS['bb']), 8)
        self.assertEqual(len(CONCURSO_DISCIPLINAS['bb-ti']), 7)
        self.assertIn('Vendas e Negociação', CONCURSO_DISCIPLINAS['bb'])
        self.assertIn('Tecnologia da Informação', CONCURSO_DISCIPLINAS['bb-ti'])
        self.assertNotIn('Tecnologia da Informação', CONCURSO_DISCIPLINAS['bb'])


class SeedTrilhaBbTests(TestCase):
    def test_simulacao_nao_grava_nada(self):
        saida = _seed()
        self.assertEqual(Categoria.objects.count(), 0)
        self.assertIn('Simulação', saida)
        self.assertIn('Áreas Específicas > Vendas e Negociação > Técnicas de Vendas', saida)

    def test_aplicar_cria_a_arvore_e_repetir_nao_duplica(self):
        _seed('--aplicar')
        total = Categoria.objects.count()
        self.assertGreater(total, 100)
        _seed('--aplicar')
        self.assertEqual(Categoria.objects.count(), total)

    def test_reaproveita_categoria_existente_mesmo_sem_acento(self):
        raiz = Categoria.objects.create(nome='Informatica')
        windows = Categoria.objects.create(nome='Windows', parent=raiz)
        _seed('--aplicar')
        raizes = [c.nome for c in Categoria.objects.filter(parent__isnull=True)]
        self.assertEqual(sorted(n for n in raizes if n.lower().startswith('inform')), ['Informatica'])
        self.assertEqual(Categoria.objects.filter(nome='Windows').get(), windows)
        self.assertTrue(Categoria.objects.filter(nome='Linux', parent=raiz).exists())

    def test_nao_move_nem_altera_questoes_existentes(self):
        cat = Categoria.objects.create(nome='Informática')
        q = Questao.objects.create(categoria=cat, texto='Questão que já existia antes do seed', revisada=True)
        _seed('--aplicar')
        q.refresh_from_db()
        self.assertEqual(q.categoria, cat)
        self.assertTrue(q.revisada)

    def test_toda_disciplina_dos_cargos_e_encontrada_na_arvore(self):
        _seed('--aplicar')
        for slug in ('bb', 'bb-ti'):
            for nome in CONCURSO_DISCIPLINAS[slug]:
                with self.subTest(cargo=slug, disciplina=nome):
                    achadas = _match_categoria(nome)
                    self.assertEqual([c.nome for c in achadas], [nome])

    def test_ti_fica_separada_da_informatica_do_agente_comercial(self):
        _seed('--aplicar')
        informatica = Categoria.objects.get(nome='Informática', parent__isnull=True)
        ti = Categoria.objects.get(nome='Tecnologia da Informação')
        self.assertNotIn(ti.id, informatica.subarvore_ids())
        self.assertEqual(ti.parent.nome, 'Áreas Específicas')


class GeracaoSoMultiplaEscolhaTests(TestCase):
    def test_plano_de_geracao_do_bb_nao_tem_certo_ou_errado(self):
        from quiz.management.commands.gerar_bateria_multi_concurso import (
            BANCAS_POR_CONCURSO, CONCURSOS_SO_ME,
        )
        self.assertEqual(CONCURSOS_SO_ME, {'bb', 'bb-ti'})
        self.assertEqual(BANCAS_POR_CONCURSO['bb'], ['Cesgranrio'])
        self.assertEqual(BANCAS_POR_CONCURSO['bb-ti'], ['Cesgranrio'])

        saida = io.StringIO()
        call_command('gerar_bateria_multi_concurso', concursos='bb,bb-ti', qtd=10,
                     dry_run=True, stdout=saida)
        linhas = [l.split() for l in saida.getvalue().splitlines() if l.startswith('bb')]
        self.assertEqual(len(linhas), 15)
        for colunas in linhas:
            self.assertEqual((colunas[-2], colunas[-1]), ('0', '10'), colunas)


class EstudarEscondeAEsperaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.aluno = User.objects.create_user(username='aluno_trilha')
        cls.staff = User.objects.create_user(username='staff_trilha', is_staff=True)
        cls.disciplina = Categoria.objects.create(nome='Disciplina comum')
        liberada = Questao.objects.create(
            categoria=cls.disciplina, texto='Questão liberada da trilha', revisada=True)
        pendente = Questao.objects.create(
            categoria=categoria_a_classificar(), texto='Questão aguardando classificação')
        for q in (liberada, pendente):
            Alternativa.objects.create(questao=q, texto='Certo', correta=True)
            Alternativa.objects.create(questao=q, texto='Errado', correta=False)

    def _nomes(self, user):
        self.client.force_login(user)
        r = self.client.get('/estudar/')
        self.assertEqual(r.status_code, 200)
        return {c['nome'] for c in r.context['categorias']}

    def test_aluno_nao_ve_a_espera(self):
        self.assertEqual(self._nomes(self.aluno), {'Disciplina comum'})

    def test_staff_ve_a_espera(self):
        self.assertEqual(self._nomes(self.staff), {'Disciplina comum', NOME_A_CLASSIFICAR})
