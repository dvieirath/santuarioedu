"""
Seletores de categoria das telas do aluno listam só categoria com conteúdo.

"Com conteúdo" = tem questão liberada nela ou em algum descendente. Tópico de
trilha ainda vazio, a espera "A classificar" e sobras de importação não entram.
Telas de administração continuam vendo tudo.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from quiz.categorias import categorias_com_conteudo, ids_com_conteudo
from quiz.categorias_pendentes import categoria_a_classificar
from quiz.models import Alternativa, Categoria, Flashcard, Questao, ResumoIA


class CategoriasComConteudoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='aluno_seletor')
        cls.raiz = Categoria.objects.create(nome='Área com conteúdo')
        cls.disciplina = Categoria.objects.create(nome='Disciplina com conteúdo', parent=cls.raiz)
        cls.topico_vazio = Categoria.objects.create(nome='Tópico ainda vazio', parent=cls.disciplina)
        cls.so_pendente = Categoria.objects.create(nome='Só questões pendentes')
        cls.so_rejeitada = Categoria.objects.create(nome='Só questões rejeitadas')
        cls.sobra = Categoria.objects.create(nome='Sobra de importação')
        cls.espera = categoria_a_classificar()

        def questao(cat, texto, **kw):
            q = Questao.objects.create(categoria=cat, texto=texto, **kw)
            Alternativa.objects.create(questao=q, texto='Certo', correta=True)
            Alternativa.objects.create(questao=q, texto='Errado', correta=False)
            return q

        questao(cls.disciplina, 'Questão liberada do seletor', revisada=True)
        questao(cls.so_pendente, 'Questão pendente do seletor')
        questao(cls.so_rejeitada, 'Questão rejeitada do seletor', revisada=True, rejeitada_definitiva=True)
        questao(cls.espera, 'Questão aguardando classificação no seletor')

    def setUp(self):
        self.client.force_login(self.user)

    def _nomes(self, url, chave='categorias'):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, url)
        itens = r.context[chave]
        return {(c['nome'] if isinstance(c, dict) else c.nome) for c in itens}

    def test_inclui_a_categoria_e_os_ancestrais(self):
        self.assertEqual(ids_com_conteudo(), {self.disciplina.id, self.raiz.id})

    def test_exclui_vazia_pendente_rejeitada_e_espera(self):
        nomes = set(categorias_com_conteudo().values_list('nome', flat=True))
        self.assertEqual(nomes, {'Área com conteúdo', 'Disciplina com conteúdo'})

    def test_tambem_acrescenta_ids_e_ignora_nulos(self):
        nomes = set(categorias_com_conteudo(tambem=[self.sobra.id, None]).values_list('nome', flat=True))
        self.assertEqual(nomes, {'Área com conteúdo', 'Disciplina com conteúdo', 'Sobra de importação'})

    def test_seletores_do_aluno_so_mostram_categoria_com_conteudo(self):
        esperado = {'Área com conteúdo', 'Disciplina com conteúdo'}
        # /modo-desafio/ e /estatisticas/ usam o mesmo filtro, mas ficam fora
        # daqui: a primeira exige um lote de questões e a segunda depende do
        # manifesto de estáticos gerado pelo collectstatic.
        for url in ('/caderno-de-erros/', '/favoritas/', '/duelo/', '/coletivo/',
                    '/flashcards/', '/resumos/'):
            with self.subTest(url=url):
                self.assertEqual(self._nomes(url), esperado)

    def test_resumo_existente_mantem_a_categoria_na_lista(self):
        ResumoIA.objects.create(categoria=self.sobra, conteudo='Resumo já gerado')
        self.assertIn('Sobra de importação', self._nomes('/resumos/'))

    def test_flashcards_mantem_categoria_que_o_aluno_ja_usa(self):
        Flashcard.objects.create(usuario=self.user, categoria=self.topico_vazio,
                                 frente='Pergunta', verso='Resposta')
        self.assertIn('Tópico ainda vazio', self._nomes('/flashcards/'))

    def test_administracao_continua_listando_todas(self):
        staff = get_user_model().objects.create_superuser(
            username='staff_seletor', email='staff@example.test', password='x')
        self.client.force_login(staff)
        nomes = self._nomes('/admin-questoes/')
        self.assertIn('Tópico ainda vazio', nomes)
        self.assertIn('Sobra de importação', nomes)
