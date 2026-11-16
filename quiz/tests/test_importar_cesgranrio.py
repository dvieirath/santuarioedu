"""
Importação de provas da Cesgranrio e texto de apoio compartilhado.

- só entra questão lida sem problema e conferida na segunda versão do caderno;
- entra pendente, na disciplina da trilha, com banca e ano;
- o texto de apoio é um registro próprio; o enunciado guarda só a pergunta;
- perguntas iguais sobre textos diferentes não são duplicata;
- as telas mostram o texto de apoio e o destaque em negrito, sem interpretar
  o enunciado como HTML;
- o adaptador do baixador entende a página da banca nos dois formatos.
"""
import io
import sys
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.template import Context, Template
from django.test import TestCase

from quiz.auditoria import detectar_flags
from quiz.cesgranrio import QuestaoExtraida
from quiz.management.commands.importar_cesgranrio import (
    avaliar, categorias_por_disciplina, gravar, separar_titulo,
)
from quiz.models import Alternativa, Categoria, Questao, TentativaDesafio, TextoApoio
from quiz.prompts_justificativa import montar_prompt

TEXTO_A = "O método braile\n\n[1] Ler no escuro é impossível.\n\n[2] Braille dedicou a vida a isso."
TEXTO_B = "Privacidade digital\n\n[1] Somos milhões de usuários de internet.\n\n[2] A rede guarda rastros."


def extraida(numero, enunciado, disciplina="LINGUA PORTUGUESA", correta="B", apoio="", problemas=(),
             alternativas=("primeira", "segunda", "terceira", "quarta", "quinta")):
    return QuestaoExtraida(
        numero=numero, disciplina=disciplina, enunciado=enunciado, correta=correta, texto_apoio=apoio,
        alternativas=list(zip("ABCDE", alternativas)), problemas=list(problemas))


class ImportacaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_trilha_bb", "--aplicar", stdout=io.StringIO())
        cls.categorias = categorias_por_disciplina()

    def _gravar(self, questoes, conferencia=None, aplicar=True):
        if conferencia is None:
            conferencia = {q.numero: "conferida" for q in questoes}
        return gravar(avaliar(questoes, conferencia), self.categorias, "Cesgranrio", 2023,
                      aplicar, fonte="Banco do Brasil 2023, PROVA A")

    def test_disciplinas_do_gabarito_apontam_para_a_trilha(self):
        self.assertEqual(self.categorias["VENDAS E NEGOCIACAO"].nome, "Vendas e Negociação")
        self.assertEqual(self.categorias["LINGUA PORTUGUESA"].nome, "Português")
        self.assertEqual(self.categorias["CONHECIMENTOS DE INFORMATICA"].nome, "Informática")
        self.assertEqual(self.categorias["TECNOLOGIA DA INFORMACAO"].parent.nome, "Áreas Específicas")

    def test_entra_pendente_na_disciplina_com_banca_ano_e_gabarito(self):
        registros = self._gravar([extraida(31, "O Sistema Financeiro Nacional é composto por",
                                           disciplina="CONHECIMENTOS BANCARIOS", correta="D")])
        q = Questao.objects.get(pk=registros[0]["id"])
        self.assertEqual((q.categoria.nome, q.banca, q.ano, q.tipo), ("Conhecimentos Bancários", "Cesgranrio", 2023, "ME"))
        self.assertFalse(q.revisada)
        self.assertFalse(q.gerada_por_ia)
        self.assertEqual(list(q.alternativa_set.order_by("id").values_list("texto", "correta")), [
            ("primeira", False), ("segunda", False), ("terceira", False), ("quarta", True), ("quinta", False)])
        self.assertEqual(registros[0]["situacao"], "importada")

    def test_questao_com_problema_ou_sem_conferencia_fica_de_fora(self):
        questoes = [
            extraida(1, "Questão com figura na área", problemas=["figura na área da questão"]),
            extraida(2, "Questão que divergiu entre as versões do caderno"),
            extraida(3, "Questão sem correspondente na outra versão"),
            extraida(4, "Questão lida e conferida sem ressalvas"),
        ]
        registros = self._gravar(questoes, {1: "sem par", 2: "divergente", 3: "sem par", 4: "conferida"})
        self.assertEqual([r["situacao"] for r in registros], ["retida", "retida", "retida", "importada"])
        self.assertEqual(registros[0]["motivos"], ["figura na área da questão"])
        self.assertIn("divergente", registros[1]["motivos"][0])
        self.assertEqual(registros[1]["lido"]["enunciado"], "Questão que divergiu entre as versões do caderno")
        self.assertEqual(Questao.objects.count(), 1)

    def test_simulacao_nao_grava_nada(self):
        registros = self._gravar([extraida(1, "De acordo com o texto, Braille", apoio=TEXTO_A)], aplicar=False)
        self.assertEqual(registros[0]["situacao"], "importada")
        self.assertIsNone(registros[0]["id"])
        self.assertEqual((Questao.objects.count(), TextoApoio.objects.count()), (0, 0))

    def test_texto_de_apoio_vira_registro_proprio_e_e_compartilhado(self):
        registros = self._gravar([
            extraida(1, "De acordo com o texto, Braille dedicou a vida a", apoio=TEXTO_A),
            extraida(2, "No parágrafo 2, a palavra isso refere-se a", apoio=TEXTO_A),
        ])
        self.assertEqual(TextoApoio.objects.count(), 1)
        apoio = TextoApoio.objects.get()
        self.assertEqual(apoio.titulo, "O método braile")
        self.assertTrue(apoio.texto.startswith("[1] Ler no escuro"))
        self.assertIn("Banco do Brasil 2023, PROVA A", apoio.fonte)
        q1, q2 = (Questao.objects.get(pk=r["id"]) for r in registros)
        self.assertEqual(q1.texto, "De acordo com o texto, Braille dedicou a vida a")
        self.assertEqual((q1.texto_apoio, q2.texto_apoio), (apoio, apoio))

    def test_mesma_pergunta_sobre_textos_diferentes_nao_e_duplicata(self):
        registros = self._gravar([
            extraida(1, "O objetivo principal do texto é", apoio=TEXTO_A),
            extraida(11, "O objetivo principal do texto é", apoio=TEXTO_B),
        ])
        self.assertEqual([r["situacao"] for r in registros], ["importada", "importada"])
        self.assertEqual(Questao.objects.count(), 2)
        self.assertEqual(TextoApoio.objects.count(), 2)

    def test_importar_de_novo_nao_duplica(self):
        questoes = [extraida(1, "O objetivo principal do texto é", apoio=TEXTO_A),
                    extraida(40, "A garantia em que o devedor mantém a posse do bem é",
                             disciplina="CONHECIMENTOS BANCARIOS")]
        self._gravar(questoes)
        registros = self._gravar(questoes)
        self.assertEqual([r["situacao"] for r in registros], ["duplicada", "duplicada"])
        self.assertEqual((Questao.objects.count(), TextoApoio.objects.count()), (2, 1))

    def test_separar_titulo(self):
        self.assertEqual(separar_titulo(TEXTO_A),
                         ("O método braile", "[1] Ler no escuro é impossível.\n\n[2] Braille dedicou a vida a isso."))
        self.assertEqual(separar_titulo("[1] Texto sem título.\n\n[2] Segundo parágrafo."),
                         ("", "[1] Texto sem título.\n\n[2] Segundo parágrafo."))


class TextoApoioNasTelasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.aluno = User.objects.create_user(username="aluno_apoio")
        cls.staff = User.objects.create_superuser(username="staff_apoio", email="s@example.test", password="x")
        cls.cat = Categoria.objects.create(nome="Português de teste")
        cls.apoio = TextoApoio.objects.create(
            titulo="O método braile", texto="[1] Ler no escuro é impossível, mas x < 5 e <b>isto</b> não é HTML.")
        cls.com_apoio = Questao.objects.create(
            categoria=cls.cat, texto="De acordo com o texto, a palavra **destacada** indica",
            revisada=True, texto_apoio=cls.apoio, tipo="ME",
            justificativa="Explicação revisada com mais de cinquenta caracteres para a auditoria.")
        for i, texto in enumerate(["são **muitos** conhecidos", "segunda", "terceira", "quarta", "quinta"]):
            Alternativa.objects.create(questao=cls.com_apoio, texto=texto, correta=(i == 0))

    def _questao_simples(self, texto):
        q = Questao.objects.create(categoria=self.cat, texto=texto, revisada=True)
        Alternativa.objects.create(questao=q, texto="Certo", correta=True)
        Alternativa.objects.create(questao=q, texto="Errado", correta=False)
        return q

    def test_filtro_enunciado_escapa_html_e_marca_destaque(self):
        saida = Template("{% load quiz_extras %}{{ t|enunciado }}").render(
            Context({"t": "Se x < 5 e <script>alert(1)</script>, a palavra **só** está em destaque."}))
        self.assertIn("x &lt; 5", saida)
        self.assertIn("&lt;script&gt;", saida)
        self.assertIn("<strong>só</strong>", saida)
        self.assertNotIn("<script>", saida)

    def test_quiz_mostra_texto_de_apoio_acima_do_enunciado(self):
        self.client.force_login(self.aluno)
        r = self.client.get(f"/quiz/{self.cat.id}/")
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Texto de apoio", html)
        self.assertIn("O método braile", html)
        self.assertIn("x &lt; 5 e &lt;b&gt;isto&lt;/b&gt; não é HTML", html)
        self.assertLess(html.index("Ler no escuro"), html.index("De acordo com o texto"))
        self.assertIn("a palavra <strong>destacada</strong> indica", html)
        self.assertIn("são <strong>muitos</strong> conhecidos", html)

    def test_questao_sem_texto_de_apoio_nao_ganha_o_bloco(self):
        outra = Categoria.objects.create(nome="Sem apoio")
        q = Questao.objects.create(categoria=outra, texto="Questão comum, sem texto de apoio.", revisada=True)
        Alternativa.objects.create(questao=q, texto="Certo", correta=True)
        Alternativa.objects.create(questao=q, texto="Errado", correta=False)
        self.client.force_login(self.aluno)
        r = self.client.get(f"/quiz/{outra.id}/")
        self.assertNotContains(r, "Texto de apoio")

    def test_auditoria_nao_acusa_texto_ausente_quando_ha_texto_de_apoio(self):
        self.assertNotIn("referencia_a_texto_ausente", detectar_flags(self.com_apoio))
        sem = self._questao_simples("De acordo com o texto, a ideia central é a seguinte.")
        self.assertIn("referencia_a_texto_ausente", detectar_flags(sem))

    def test_auditoria_aceita_enunciado_aberto_em_multipla_escolha(self):
        aberto = "Nessas condições, o preço do caminhão, em reais, é de, aproximadamente,"
        me = Questao.objects.create(categoria=self.cat, texto=aberto, tipo="ME", revisada=True)
        ce = Questao.objects.create(categoria=self.cat, texto=aberto + " e", tipo="CE", revisada=True)
        self.assertNotIn("enunciado_termina_em_pontuacao_incompleta", detectar_flags(me))
        self.assertIn("termina_em_conjuncao", detectar_flags(ce))
        me.texto = "Diferentemente do método de Barbier, o método de Haüy e"
        self.assertNotIn("termina_em_conjuncao", detectar_flags(me))

    def test_prompt_de_justificativa_leva_o_texto_de_apoio(self):
        prompt = montar_prompt(self.com_apoio)
        self.assertIn("TEXTO DE APOIO:", prompt)
        self.assertIn("Ler no escuro é impossível", prompt)

    def test_painel_de_revisao_recebe_o_texto_de_apoio(self):
        self.client.force_login(self.staff)
        r = self.client.get(f"/api/admin/revisao/por-id/{self.com_apoio.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["questao"]["texto_apoio"]["titulo"], "O método braile")

    def test_modo_desafio_nao_sorteia_questao_com_texto_de_apoio(self):
        for i in range(6):
            self._questao_simples(f"Questão rápida número {i} para o modo desafio.")
        self.client.force_login(self.aluno)
        self.assertEqual(self.client.get("/modo-desafio/").status_code, 200)
        sorteadas = TentativaDesafio.objects.get(usuario=self.aluno).questoes_ids
        self.assertNotIn(self.com_apoio.id, sorteadas)
        self.assertGreaterEqual(len(sorteadas), 5)


class AdaptadorDoBaixadorTests(TestCase):
    """A página da banca troca os nomes: "GABARITO n" é a versão do caderno."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        sys.path.insert(0, str(Path(settings.BASE_DIR) / "scripts" / "baixar_provas_concursos"))
        from bancas import cesgranrio
        cls.adaptador = cesgranrio

    @staticmethod
    def _link(arquivo, texto):
        return f'<a href="https://inscricao.cesgranrio.com.br/storage.ashx?file=pdf/{arquivo}">{texto}</a>'

    def test_pagina_de_2022(self):
        html = "<title>Banco do Brasil – BB 01/2022 – Cesgranrio</title>" + "".join([
            self._link("bb0122/PROVA A - ESCRITURÁRIO - AGENTE COMERCIAL - Alterada em 12 maio 23.pdf",
                       "Gabaritos Alterados – Prova A (Agente Comercial)"),
            self._link("bb0122/PROVA - AGENTE DE TECNOLOGIA - MICRORREGIAO 158 - TI - Alterado em 12 maio 23.pdf",
                       "Gabaritos Alterados – Prova Agente de Tecnologia)"),
            self._link("bb0122/gabarito/GABARITO - 23-04-2023 - PROVA A - ESCRITURÁRIO - AGENTE COMERCIAL.pdf",
                       "GABARITO – PROVA A – ESCRITURÁRIO – AGENTE COMERCIAL"),
            self._link("bb0122/gabarito/GABARITO - 23-04-2023 - PROVA - AGENTE DE TECNOLOGIA - MICRORREGIAO 158 - TI.pdf",
                       "GABARITO – PROVA – AGENTE DE TECNOLOGIA – MICRORREGIAO 158 – TI"),
            self._link("bb0122/provas/PROVA A - AGENTE COMERCIAL - GABARITO 1.pdf", "PROVA A – AGENTE COMERCIAL – GABARITO 1"),
            self._link("bb0122/provas/PROVA A - AGENTE COMERCIAL - GABARITO 2.pdf", "PROVA A – AGENTE COMERCIAL – GABARITO 2"),
            self._link("bb0122/provas/AGENTE DE TECNOLOGIA - Microrregião 158 - TI - GABARITO 1.pdf",
                       "AGENTE DE TECNOLOGIA – Microrregião 158 – TI – GABARITO 1"),
            self._link("bb0122/bb0122_edital6.pdf", "Edital nº 6"),
        ])
        nome, provas = self.adaptador.interpretar_pagina(html)
        self.assertEqual(nome, "Banco do Brasil – BB 01/2022 – Cesgranrio")
        self.assertEqual([p.chave for p in provas], ["PROVA A", "TECNOLOGIA"])
        a, ti = provas
        self.assertEqual(sorted(a.cadernos), [1, 2])
        self.assertIn("provas/PROVA A - AGENTE COMERCIAL - GABARITO 1.pdf", a.cadernos[1])
        self.assertIn("Alterada em 12 maio 23", a.gabarito_definitivo)
        self.assertIn("gabarito/GABARITO - 23-04-2023 - PROVA A", a.gabarito_preliminar)
        self.assertEqual(a.gabarito, a.gabarito_definitivo)
        self.assertIn("Alterado em 12 maio 23", ti.gabarito_definitivo)

    def test_pagina_de_2021_com_as_pastas_invertidas(self):
        html = "".join([
            self._link("bb0121/provas/PROVA A - ESCRITURÁRIO - AGENTE COMERCIAL.pdf",
                       "PROVA A – ESCRITURÁRIO – AGENTE COMERCIAL"),
            self._link("bb0121/gabarito/PROVA A - ESCRITURÁRIO - AGENTE COMERCIAL - GABARITO 1.pdf",
                       "PROVA A – ESCRITURÁRIO – AGENTE COMERCIAL – GABARITO 1"),
            self._link("bb0121/provas/PROVA - AGENTE DE TECNOLOGIA - MICRORREGIAO 16 DF TI.pdf",
                       "PROVA – AGENTE DE TECNOLOGIA – MICRORREGIAO 16 DF TI"),
            self._link("bb0121/gabarito/AGENTE DE TECNOLOGIA - MICRORREGIÃO 16 DF-TI - GABARITO 1.pdf",
                       "AGENTE DE TECNOLOGIA – MICRORREGIÃO 16 DF-TI – GABARITO 1"),
            self._link("bb0121/recursos/PROVA - AGENTE DE TECNOLOGIA - MICRORREGIAO 16 DF TI - ALTERADO EM 05_10_2021.pdf",
                       "Gabaritos Alterados"),
        ])
        _, provas = self.adaptador.interpretar_pagina(html)
        a, ti = provas
        self.assertIn("gabarito/PROVA A", a.cadernos[1])          # caderno está na pasta "gabarito"
        self.assertIn("provas/PROVA A", a.gabarito_preliminar)    # e o gabarito, na pasta "provas"
        self.assertIsNone(a.gabarito_definitivo)
        self.assertEqual(a.gabarito, a.gabarito_preliminar)
        self.assertIn("ALTERADO EM 05_10_2021", ti.gabarito_definitivo)

    def test_interface_comum_devolve_um_caderno_e_um_gabarito_por_prova(self):
        html = "".join([
            self._link("x/provas/PROVA A - AGENTE COMERCIAL - GABARITO 2.pdf", "PROVA A – AGENTE COMERCIAL – GABARITO 2"),
            self._link("x/provas/PROVA A - AGENTE COMERCIAL - GABARITO 1.pdf", "PROVA A – AGENTE COMERCIAL – GABARITO 1"),
            self._link("x/gabarito/GABARITO - PROVA A.pdf", "GABARITO – PROVA A – AGENTE COMERCIAL"),
        ])
        with self.settings():
            import bancas.cesgranrio as modulo
            original = modulo.listar_provas
            modulo.listar_provas = lambda slug: modulo.interpretar_pagina(html)
            try:
                _, documentos = modulo.buscar_documentos("qualquer")
            finally:
                modulo.listar_provas = original
        self.assertEqual([d.tipo for d in documentos], ["prova", "gabarito"])
        self.assertIn("GABARITO 1.pdf", documentos[0].url)
