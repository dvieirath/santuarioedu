"""
Triagem sem IA das pendentes geradas por IA: só descarta defeito comprovável.

Cada caso "passa" abaixo é um falso positivo real visto na calibragem: a regra
foi apertada até ele parar de ser descartado.
"""
import json
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from quiz.models import Alternativa, Categoria, Questao
from quiz.triagem_pendentes import PREFIXO_MOTIVO, motivo_de_rejeicao


def alt(texto, correta=False):
    return SimpleNamespace(texto=texto, correta=correta)


def ce(texto, gabarito='Certo'):
    q = SimpleNamespace(texto=texto, tipo='CE', imagem=None, texto_apoio_id=None)
    return q, [alt('Certo', gabarito == 'Certo'), alt('Errado', gabarito == 'Errado')]


def me(texto, alternativas=('um', 'dois', 'três', 'quatro', 'cinco'), correta=0):
    q = SimpleNamespace(texto=texto, tipo='ME', imagem=None, texto_apoio_id=None)
    return q, [alt(t, i == correta) for i, t in enumerate(alternativas)]


class RegrasDeDescarteTests(SimpleTestCase):
    def assertDescarta(self, par, trecho):
        motivo = motivo_de_rejeicao(*par)
        self.assertIsNotNone(motivo, par[0].texto)
        self.assertIn(trecho, motivo)

    def assertPassa(self, par):
        self.assertIsNone(motivo_de_rejeicao(*par), par[0].texto)

    # ── gabarito impossível ──
    def test_sem_correta_e_mais_de_uma_correta(self):
        q, alts = ce('A União responde objetivamente.')
        alts[0].correta = False
        self.assertDescarta((q, alts), 'sem alternativa correta')
        alts[0].correta = alts[1].correta = True
        self.assertDescarta((q, alts), 'mais de uma')

    def test_alternativa_em_branco_e_alternativas_iguais(self):
        self.assertDescarta(me('Qual é a capital?', ('a', ' ', 'c', 'd', 'e')), 'em branco')
        self.assertDescarta(me('Qual é a capital?', ('Belém', 'belém ', 'c', 'd', 'e')), 'idêntico')

    def test_numero_de_alternativas(self):
        q, alts = ce('A União responde objetivamente.')
        self.assertDescarta((q, alts + [alt('Talvez')]), 'duas alternativas')
        self.assertDescarta(me('Qual é a capital?', ('a', 'b', 'c')), '4 ou 5')
        self.assertPassa(me('Qual é a capital?', ('a', 'b', 'c', 'd')))

    # ── certo/errado que não é afirmação ──
    def test_ce_com_alternativas_coladas_no_enunciado(self):
        texto = 'O ato configura:\nA) crime tributário\nB) crime econômico\nC) infração leve\nD) nada'
        self.assertDescarta(ce(texto), 'coladas no enunciado')

    def test_ce_que_termina_em_dois_pontos(self):
        self.assertDescarta(ce('Considerando a razoabilidade, a aplicação da multa é:'), 'dois-pontos')
        self.assertDescarta(ce('A partir do caso, é correto afirmar que:'), 'dois-pontos')
        self.assertDescarta(ce('Considerando o caso, a afirmação a seguir é verdadeira:'), 'a seguir')

    def test_ce_que_julga_a_propria_afirmacao_passa(self):
        self.assertPassa(ce('A próxima classificação deve ser B. Essa afirmação é:'))
        self.assertPassa(ce('O prazo é de cinco anos. A afirmação acima está:'))

    def test_ce_com_pergunta_aberta(self):
        self.assertDescarta(ce('O juiz absolveu o servidor. Qual é a base legal da decisão?'), 'pergunta aberta')
        self.assertDescarta(ce('A decisão foi questionada. O que a Constituição prevê?'), 'pergunta aberta')
        self.assertDescarta(ce('A soma dos três primeiros é 12, qual é a soma total?'), 'pergunta aberta')
        self.assertDescarta(ce('Diante do cenário, qual das seguintes afirmações está correta?'), 'a seguir')

    def test_ce_com_pergunta_de_sim_ou_nao_passa(self):
        self.assertPassa(ce('A lei não prevê sanção. O dispositivo é constitucional?'))
        self.assertPassa(ce('A proposta do secretário contradiz o que estabelece a lei?'))
        self.assertPassa(ce('A norma, a qual foi revogada em 2020, ainda produz efeitos?'))
        self.assertPassa(ce('A decisão está correta quanto ao mérito?'))

    def test_ce_com_duas_opcoes(self):
        self.assertDescarta(ce('A contratação realizada pelo prefeito é legal ou ilegal?'), 'duas opções')
        self.assertDescarta(ce('A anulação do contrato é procedente ou improcedente?'), 'duas opções')
        self.assertPassa(ce('A decisão do juiz viola o contraditório, correto ou errado?'))
        self.assertPassa(ce('O prazo é de dez dias. A afirmação é verdadeira ou falsa?'))

    # ── material citado e ausente ──
    def test_texto_acima_sem_texto(self):
        self.assertDescarta(ce('Considerando o texto acima, a infração é considerada grave.'), 'texto acima')
        self.assertDescarta(me('Com base no trecho anterior, qual é a consequência jurídica?'), 'texto acima')

    def test_texto_embutido_no_enunciado_passa(self):
        longo = 'Em 2024, a secretaria publicou o edital. ' * 6
        self.assertPassa(ce('Texto: ' + longo + 'Considerando o texto acima, o edital é válido.'))
        self.assertPassa(ce(longo + 'Considerando o texto acima, o edital é válido.'))
        self.assertPassa(ce('Considerando o texto acima: ' + longo + 'O edital é válido.'))

    def test_texto_a_seguir(self):
        self.assertPassa(me('No texto a seguir, identifique a figura de linguagem: "O silêncio da sala '
                            'parecia um espelho que reflete a ausência de voz."'))
        self.assertDescarta(me('Identifique a figura de linguagem no trecho a seguir.'), 'texto a seguir')

    def test_figura_citada_sem_imagem(self):
        self.assertDescarta(me('Observando o gráfico acima, qual é a tendência das vendas no período?'), 'figura')
        q, alts = me('Observando o gráfico acima, qual é a tendência das vendas no período?')
        q.imagem = 'questoes/grafico.png'
        self.assertPassa((q, alts))

    def test_mencao_generica_a_imagem_ou_figura_passa(self):
        self.assertPassa(ce('O direito à imagem é protegido pela Constituição Federal de 1988.'))
        self.assertPassa(me('Qual figura de linguagem predomina na frase "o mar de gente"?'))

    def test_questao_com_texto_de_apoio_passa(self):
        q, alts = me('Considerando o texto acima, qual é a ideia central do autor?')
        q.texto_apoio_id = 7
        self.assertPassa((q, alts))


class ComandoTriarPendentesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cat = Categoria.objects.create(nome='Triagem')

        def questao(texto, gabarito=True, **kw):
            q = Questao.objects.create(categoria=cat, texto=texto, tipo='CE', gerada_por_ia=True, **kw)
            Alternativa.objects.create(questao=q, texto='Certo', correta=gabarito)
            Alternativa.objects.create(questao=q, texto='Errado', correta=False)
            return q

        cls.boa = questao('A União responde objetivamente pelos danos que seus agentes causarem.')
        cls.sem_gabarito = questao('O prazo decadencial é de cinco anos, contados do ato.', gabarito=False)
        cls.aberta = questao('O servidor foi absolvido. Qual é a base legal que sustenta a decisão?')
        cls.liberada = questao('Considerando o texto acima, a multa é devida ao erário.', revisada=True)
        cls.oficial = questao('Considerando o texto acima, o recurso é tempestivo e cabível.')
        Questao.objects.filter(id=cls.oficial.id).update(gerada_por_ia=False)

    def _rodar(self, pasta, *args):
        saida = StringIO()
        with override_settings(BASE_DIR=pasta):
            call_command('triar_pendentes_ia', '--sem_backup', *args, stdout=saida)
        relatorio = next(Path(pasta, 'output').glob('triagem_pendentes_ia_*/relatorio.json'))
        return json.loads(relatorio.read_text(encoding='utf-8'))

    def test_simulacao_nao_grava(self):
        import tempfile
        with tempfile.TemporaryDirectory() as pasta:
            rel = self._rodar(pasta)
        self.assertEqual(rel['descartadas'], 2)
        self.assertFalse(rel['aplicado'])
        self.assertFalse(Questao.objects.filter(rejeitada_definitiva=True).exists())

    def test_aplicar_descarta_so_pendente_de_ia_com_defeito(self):
        import tempfile
        with tempfile.TemporaryDirectory() as pasta:
            rel = self._rodar(pasta, '--aplicar')
        self.assertEqual(rel['descartadas'], 2)
        self.assertEqual(rel['pendentes_de_ia_depois'], 1)
        rejeitadas = set(Questao.objects.filter(rejeitada_definitiva=True).values_list('id', flat=True))
        self.assertEqual(rejeitadas, {self.sem_gabarito.id, self.aberta.id})
        self.aberta.refresh_from_db()
        self.assertTrue(self.aberta.motivo_rejeicao.startswith(PREFIXO_MOTIVO))
        self.assertFalse(self.aberta.revisada)
        # questão liberada e questão oficial ficam como estavam, mesmo com o mesmo defeito
        for intacta in (self.boa, self.liberada, self.oficial):
            intacta.refresh_from_db()
            self.assertFalse(intacta.rejeitada_definitiva)
            self.assertEqual(intacta.motivo_rejeicao, '')
