"""
Leitor de cadernos e gabaritos da Cesgranrio (quiz/cesgranrio.py).

Tudo com dados sintéticos: os PDFs oficiais ficam fora do repositório. Os
trechos imitam o que o leitor recebe do PDF: (x, y, texto, negrito, tamanho),
com a origem embaixo, à esquerda, e duas colunas (x de 28 e de 312).
"""
from django.test import SimpleTestCase

from quiz import cesgranrio as c

ESQ, DIR = 28.3, 311.8


def linhas(trechos):
    return c.montar_linhas(trechos)[0]


def textos(trechos):
    return [l.texto for l in linhas(trechos)]


class GabaritoTests(SimpleTestCase):
    TEXTO = """BANCO DO BRASIL -  Prova  A  -  Escriturário – Agente Comercial
SELEÇÃO EXTERNA 2022 / 001   -   EDITAL No 01
GABARITO 1
CONHECIMENTOS BÁSICOS
LÍNGUA PORTUGUESA
1 - B 2 - Anulada 3 -  E
MATEMÁTICA
4 - D 5- A
GABARITO 2
CONHECIMENTOS BÁSICOS
LÍNGUA PORTUGUESA
1 -  C 2 -  A 3 -  D
"""

    def test_le_cada_versao_com_disciplina_e_letra(self):
        versoes = c.ler_gabarito(self.TEXTO)
        self.assertEqual(sorted(versoes), [1, 2])
        self.assertEqual(versoes[1][1], {"letra": "B", "disciplina": "LINGUA PORTUGUESA"})
        self.assertEqual(versoes[1][4], {"letra": "D", "disciplina": "MATEMATICA"})
        self.assertEqual(versoes[1][5]["letra"], "A")
        self.assertEqual(versoes[2][1]["letra"], "C")

    def test_anulada_fica_sem_letra(self):
        self.assertIsNone(c.ler_gabarito(self.TEXTO)[1][2]["letra"])

    def test_titulos_de_bloco_nao_viram_disciplina(self):
        disciplinas = {d["disciplina"] for d in c.ler_gabarito(self.TEXTO)[1].values()}
        self.assertEqual(disciplinas, {"LINGUA PORTUGUESA", "MATEMATICA"})


class MontarLinhasTests(SimpleTestCase):
    def test_coluna_esquerda_vem_antes_da_direita(self):
        self.assertEqual(textos([
            (DIR, 700, "direita em cima"),
            (ESQ, 700, "esquerda em cima"),
            (ESQ, 688, "esquerda embaixo"),
        ]), ["esquerda em cima", "esquerda embaixo", "direita em cima"])

    def test_descarta_cabecalho_e_rodape(self):
        self.assertEqual(textos([
            (240, 786, "BANCO DO BRASIL"), (ESQ, 700, "conteúdo"), (294, 48, "7"),
        ]), ["conteúdo"])

    def test_hifen_solto_na_margem_e_translineacao(self):
        resultado, viu = c.montar_linhas([(ESQ, 700, "A posição dos pon"), (280, 700, "-")])
        self.assertEqual(resultado[0].texto, "A posição dos pon")
        self.assertTrue(resultado[0].hifen_mole)
        self.assertTrue(viu)

    def test_trecho_sem_posicao_continua_o_anterior(self):
        self.assertEqual(textos([(ESQ, 700, "LÍNGUA POR"), (None, None, "TUGUESA")]),
                         ["LÍNGUA PORTUGUESA"])

    def test_numero_de_questao_desenhado_algarismo_por_algarismo(self):
        self.assertEqual(textos([(ESQ, 700, "5"), (34.5, 700, "8")]), ["58"])

    def test_trechos_encostados_nao_ganham_espaco(self):
        self.assertEqual(textos([(ESQ, 700, "2", False, 10), (33.9, 700, "022) Só 2022", False, 10)]),
                         ["2022) Só 2022"])

    def test_numero_na_margem_e_marcador_de_paragrafo(self):
        linha = linhas([(29, 700, "2"), (68, 700, "Nesse cenário, pensar em privacidade")])[0]
        self.assertEqual((linha.marcador, linha.texto, linha.x), ("2", "Nesse cenário, pensar em privacidade", 68))

    def test_marcador_impresso_duas_vezes(self):
        linha = linhas([(29, 700, "1"), (31, 700, "1"), (68, 700, "Atualmente, somos mais")])[0]
        self.assertEqual((linha.marcador, linha.texto), ("1", "Atualmente, somos mais"))

    def test_negrito_no_meio_da_linha_vira_destaque(self):
        self.assertEqual(textos([
            (ESQ, 700, "(A) Braille e seu método são ", False, 10),
            (190, 700, "muitos", True, 10),
            (222, 700, " conhecidos.", False, 10),
        ]), ["(A) Braille e seu método são **muitos** conhecidos."])

    def test_linha_toda_em_negrito_nao_e_marcada(self):
        linha = linhas([(90, 700, "A história do método braile", True, 12)])[0]
        self.assertEqual(linha.texto, "A história do método braile")
        self.assertTrue(linha.negrito_total)

    def test_ordinal_sobrescrito_entra_depois_do_numero(self):
        linha = linhas([
            (ESQ, 700, "1 mês ele escolheu A; no 2 mês, B", False, 10),
            (34.5, 704, "o", False, 6),
            (141, 704, "o", False, 6),
        ])[0]
        self.assertEqual(linha.texto, "1º mês ele escolheu A; no 2º mês, B")
        self.assertFalse(linha.pendencia_formula)

    def test_expoente_marca_a_linha_como_formula_pendente(self):
        linha = linhas([
            (ESQ, 700, "(A) y = - 200x - 5800x + 63600", False, 10),
            (84, 704, "2", False, 6),
        ])[0]
        self.assertTrue(linha.pendencia_formula)
        self.assertEqual(linha.texto, "(A) y = - 200x - 5800x + 63600")

    def test_indice_subscrito_tambem_fica_pendente(self):
        linha = linhas([(ESQ, 700, "2 + 5 ∙ log 2", False, 10), (88, 696, "10", False, 6)])[0]
        self.assertTrue(linha.pendencia_formula)

    def test_numero_da_questao_acima_do_enunciado_nao_e_sobrescrito(self):
        self.assertEqual(textos([(ESQ, 712, "7"), (ESQ, 700, "Em relação ao texto, é correto afirmar")]),
                         ["7", "Em relação ao texto, é correto afirmar"])


class DesniveisTests(SimpleTestCase):
    """Expoente e índice que chegam dentro do mesmo trecho (cadernos de 2021)."""

    def test_ordinal_depois_de_numero(self):
        pedacos = [("no 1", 10, 28, 700), ("o", 7, 50, 704), (" mês", 10, 54, 700)]
        self.assertEqual(c._desniveis("no 1o mês", pedacos), ("no 1º mês", False, False, None))

    def test_expoente_fica_pendente(self):
        pedacos = [("a(x)=1000 e", 10, 28, 700), ("kx", 7, 90, 704), (", e L", 10, 100, 700)]
        texto, formula, colar, _ = c._desniveis("a(x)=1000 ekx, e L", pedacos)
        self.assertEqual((texto, formula, colar), ("a(x)=1000 ekx, e L", True, False))

    def test_indice_fica_pendente(self):
        pedacos = [("ln x = log", 10, 28, 700), ("e", 7, 80, 696), ("x, qual", 10, 84, 700)]
        self.assertTrue(c._desniveis("ln x = logex, qual", pedacos)[1])

    def test_ordinal_no_comeco_pede_para_colar_no_trecho_anterior(self):
        pedacos = [("th", 7, 100, 704), (" century", 10, 108, 700)]
        self.assertEqual(c._desniveis("th century", pedacos), ("th century", False, True, 700))

    def test_trecho_colado_junta_com_o_numero(self):
        self.assertEqual(textos([
            (ESQ, 700, "(D) in the beginning of the 20", False, 10, False, False),
            (170, 700, "th century", False, 10, False, True),
        ]), ["(D) in the beginning of the 20th century"])

    def test_sem_desnivel_nada_muda(self):
        pedacos = [("seus clientes,", 10, 28, 700), (" já que", 10, 92, 700)]
        self.assertEqual(c._desniveis("seus clientes, já que", pedacos),
                         ("seus clientes, já que", False, False, None))


class JuncaoDeLinhasTests(SimpleTestCase):
    def _linha(self, texto, y, x=ESQ, **kw):
        return c.Linha(texto=texto, x=x, y=y, **kw)

    def test_translineacao_some(self):
        juncao = c._Juncao(hifen_separado=True)
        self.assertEqual(c._juntar([
            self._linha("que podem ser combi", 700, hifen_mole=True),
            self._linha("nados de 63 maneiras", 688),
        ], juncao), "que podem ser combinados de 63 maneiras")

    def test_hifen_no_texto_fica_quando_a_translineacao_vem_separada(self):
        juncao = c._Juncao(hifen_separado=True)
        self.assertEqual(c._juntar([self._linha("concertos com ex-", 700), self._linha("alunos de Braille", 688)],
                                   juncao), "concertos com ex-alunos de Braille")

    def test_vocabulario_decide_quando_a_translineacao_vem_no_texto(self):
        juncao = c._Juncao(hifen_separado=False, vocabulario={"exposição", "fosse"})
        self.assertEqual(c._juntar([self._linha("diante de tamanha expo-", 700), self._linha("sição, essa", 688)],
                                   juncao), "diante de tamanha exposição, essa")
        self.assertEqual(c._juntar([self._linha("que o valor fos-", 700), self._linha("se reconhecido", 688)],
                                   juncao), "que o valor fosse reconhecido")

    def test_pronome_depois_de_verbo_mantem_o_hifen(self):
        juncao = c._Juncao(hifen_separado=False, vocabulario=set())
        self.assertEqual(c._juntar([self._linha("o método tornou-", 700), self._linha("se conhecido", 688)],
                                   juncao), "o método tornou-se conhecido")

    def test_hifen_repetido_na_linha_de_baixo(self):
        juncao = c._Juncao(hifen_separado=False)
        self.assertEqual(c._juntar([self._linha("270 mostraram-", 700), self._linha("-se interessados", 688)],
                                   juncao), "270 mostraram-se interessados")

    def test_linha_em_negrito_dentro_do_bloco_e_destaque(self):
        juncao = c._Juncao()
        self.assertEqual(c._juntar([
            self._linha("Braille e sua família não ficaram", 700),
            self._linha("só.", 688, negrito_total=True),
        ], juncao), "Braille e sua família não ficaram **só**.")

    def test_destaques_vizinhos_viram_um_so(self):
        juncao = c._Juncao()
        self.assertEqual(c._juntar([
            self._linha("the worst outcome **would**", 700),
            self._linha("**be** to let inflation", 688),
        ], juncao), "the worst outcome **would be** to let inflation")

    def test_tira_espaco_antes_de_pontuacao(self):
        self.assertEqual(c._acabamento("fazem isso pelo smartphone . Depois"), "fazem isso pelo smartphone. Depois")

    def test_hifen_antes_de_destaque_fica_colado(self):
        self.assertEqual(c._acabamento("em “Automatiza- **se** facilmente”"), "em “Automatiza-**se** facilmente”")

    def test_paragrafos_por_recuo_espaco_e_marcador(self):
        ls = [
            self._linha("Título do texto", 760, x=90),
            self._linha("Ler no escuro. Quem já tentou sabe que é impos", 736, x=48, marcador="1", hifen_mole=True),
            self._linha("sível.", 724, x=ESQ),
            self._linha("A tragédia não o impediu de estudar.", 712, x=48, marcador="2"),
        ]
        resultado, estruturado = c.paragrafos(ls, c._Juncao(), numerar=True)
        self.assertEqual(resultado, [
            "Título do texto",
            "[1] Ler no escuro. Quem já tentou sabe que é impossível.",
            "[2] A tragédia não o impediu de estudar.",
        ])
        self.assertFalse(estruturado)

    def test_codigo_mantem_quebras_e_recuo(self):
        ls = [
            self._linha("SELECT E.CNPJ", 700),
            self._linha("FROM Empresa E", 688),
            self._linha("WHERE E.CNPJ NOT IN (", 676),
            self._linha("SELECT T.CNPJ", 664, x=ESQ + 14),
            self._linha(")", 652),
        ]
        texto, estruturado = c.bloco_para_texto(ls, c._Juncao(), largura_ref=56)
        self.assertTrue(estruturado)
        self.assertEqual(texto, "SELECT E.CNPJ\nFROM Empresa E\nWHERE E.CNPJ NOT IN (\n    SELECT T.CNPJ\n)")

    def test_texto_corrido_de_duas_linhas_e_reunido(self):
        ls = [self._linha("argue that slowing the economic growth will definitely", 700),
              self._linha("cause inflation to take root.", 688, x=45.4)]
        texto, estruturado = c.bloco_para_texto(ls, c._Juncao(), largura_ref=58, primeira_e_rotulo=True)
        self.assertFalse(estruturado)
        self.assertEqual(texto, "argue that slowing the economic growth will definitely cause inflation to take root.")


def pagina(trechos, figuras=()):
    resultado, hifen = c.montar_linhas(trechos)
    return c.Pagina(numero=1, linhas=resultado, figuras=list(figuras), hifen_separado=hifen)


def questao_em(y, numero, enunciado, alternativas=None, x=ESQ):
    """Trechos de uma questão simples a partir da altura y. Devolve (trechos, y final)."""
    alternativas = alternativas or ["um", "dois", "três", "quatro", "cinco"]
    trechos = [(x, y, str(numero), True, 11), (x, y - 12, enunciado, False, 10)]
    y -= 27
    for letra, texto in zip("ABCDE", alternativas):
        trechos.append((x, y, f"({letra}) {texto}", False, 10))
        y -= 12
    return trechos, y


class MontarQuestoesTests(SimpleTestCase):
    GAB = {
        1: {"letra": "B", "disciplina": "LINGUA PORTUGUESA"},
        2: {"letra": "D", "disciplina": "MATEMATICA"},
        3: {"letra": "A", "disciplina": "MATEMATICA"},
    }

    def _caderno(self, extra=(), figuras=(), enunciado_2="Quanto é dois mais dois, em unidades?"):
        trechos = [
            (240, 786, "BANCO DO BRASIL", True, 12),
            (70, 760, "CONHECIMENTOS BÁSICOS", True, 12),
            (86, 745, "LÍNGUA POR", True, 12), (None, None, " TUGUESA", True, 12),
            (90, 725, "O método braile", True, 11),
            (29, 705, "1", True, 8), (68, 705, "Ler no escuro é impossível para quem enxerga, mas", False, 10),
            (48, 693, "foi a isso que Braille dedicou a vida.", False, 10),
        ]
        q1, y = questao_em(670, 1, "De acordo com o texto, Braille dedicou a vida a",
                           ["trabalhar em selarias", "permitir a leitura no escuro, o que antes",
                            "ensinar piano", "viajar", "escrever"])
        # continuação recuada da alternativa (B)
        q1.insert(4, (45.4, 631 - 6, "era considerado impossível", False, 10))
        # reposiciona C, D, E abaixo da continuação
        q1 = q1[:5] + [(x, yy - 12, t, n, s) for (x, yy, t, n, s) in q1[5:]]
        trechos += q1
        trechos += [(397, 760, "MATEMÁTICA", True, 12)]
        q2, y2 = questao_em(740, 2, enunciado_2, x=DIR)
        q3, _ = questao_em(y2 - 30, 3, "Quanto é três vezes três, em unidades?", x=DIR)
        trechos += q2 + list(extra) + q3
        return [pagina(trechos, figuras)]

    def test_monta_questoes_com_disciplina_e_gabarito(self):
        qs = c.montar_questoes(self._caderno(), self.GAB)
        self.assertEqual([q.numero for q in qs], [1, 2, 3])
        self.assertEqual([q.disciplina for q in qs], ["LINGUA PORTUGUESA", "MATEMATICA", "MATEMATICA"])
        self.assertEqual([q.correta for q in qs], ["B", "D", "A"])
        self.assertEqual([q.problemas for q in qs], [[], [], []])

    def test_texto_antes_da_primeira_questao_da_disciplina_e_apoio(self):
        q1, q2, _ = c.montar_questoes(self._caderno(), self.GAB)
        self.assertEqual(q1.texto_apoio,
                         "O método braile\n\n[1] Ler no escuro é impossível para quem enxerga, mas "
                         "foi a isso que Braille dedicou a vida.")
        self.assertEqual(q1.enunciado, "De acordo com o texto, Braille dedicou a vida a")
        self.assertEqual(q2.texto_apoio, "")

    def test_alternativa_continua_na_linha_recuada(self):
        q1 = c.montar_questoes(self._caderno(), self.GAB)[0]
        self.assertEqual([l for l, _ in q1.alternativas], list("ABCDE"))
        self.assertEqual(q1.alternativas[1][1],
                         "permitir a leitura no escuro, o que antes era considerado impossível")

    def test_capa_e_instrucoes_nao_viram_texto_de_apoio(self):
        paginas = [pagina([(ESQ, 700, "LEIA ATENTAMENTE AS INSTRUÇÕES ABAIXO.", True, 10),
                           (ESQ, 688, "01 - O candidato recebeu do fiscal este caderno.", False, 10)])]
        paginas += self._caderno()
        self.assertNotIn("INSTRUÇÕES", c.montar_questoes(paginas, self.GAB)[0].texto_apoio)

    def test_anulada_fica_retida(self):
        gab = {**self.GAB, 2: {"letra": None, "disciplina": "MATEMATICA"}}
        self.assertEqual(c.montar_questoes(self._caderno(), gab)[1].problemas, ["anulada no gabarito"])

    def test_figura_na_area_da_questao(self):
        figura = c.Figura(pagina=1, coluna=1, y_base=700, y_topo=722)
        qs = c.montar_questoes(self._caderno(figuras=[figura]), self.GAB)
        self.assertEqual(qs[1].problemas, ["figura na área da questão"])
        self.assertEqual(qs[2].problemas, [])

    def test_texto_solto_entre_questoes_retem_as_duas(self):
        # bem abaixo da alternativa (E): linha colada nela seria continuação
        solto = [(DIR, 640, "Dado: 1,01 elevado a 120 = 3,3", False, 10)]
        qs = c.montar_questoes(self._caderno(extra=solto), self.GAB)
        self.assertIn("texto solto depois das alternativas", qs[1].problemas)
        self.assertIn("texto solto antes da questão", qs[2].problemas)
        self.assertIn("1,01 elevado a 120", qs[2].texto_solto)

    def test_destaque_mencionado_mas_nao_encontrado(self):
        qs = c.montar_questoes(self._caderno(enunciado_2="A palavra destacada no trecho indica"), self.GAB)
        self.assertEqual(qs[1].problemas, ["menciona destaque, mas nenhum trecho destacado foi identificado"])

    def test_citar_figura_ou_tabela_retem_a_questao(self):
        casos = [
            "A Figura a seguir é um esboço desse mapa. A distância é",
            "Os dados foram dispostos em uma Tabela, da seguinte forma. O total é",
            "Observe o gráfico abaixo e indique o valor de",
        ]
        for enunciado in casos:
            with self.subTest(enunciado=enunciado[:30]):
                qs = c.montar_questoes(self._caderno(enunciado_2=enunciado), self.GAB)
                self.assertEqual(qs[1].problemas, ["cita figura, gráfico ou tabela (conferir no caderno)"])

    def test_tabela_de_banco_de_dados_e_tipo_de_grafico_nao_retem(self):
        casos = [
            "A coluna atividade da tabela Empresa é uma chave estrangeira. O comando é",
            "O tipo de gráfico adequado para visualizar esses dados é o seguinte:",
            "Uma boa imagem institucional deve ser construída pela empresa, que",
        ]
        for enunciado in casos:
            with self.subTest(enunciado=enunciado[:30]):
                qs = c.montar_questoes(self._caderno(enunciado_2=enunciado), self.GAB)
                self.assertEqual(qs[1].problemas, [])

    def test_questao_que_falta_no_caderno(self):
        gab = {**self.GAB, 4: {"letra": "C", "disciplina": "MATEMATICA"}}
        self.assertEqual(c.montar_questoes(self._caderno(), gab)[3].problemas,
                         ["questão não localizada no caderno"])

    def test_titulo_de_disciplina_em_duas_linhas_nao_e_texto_solto(self):
        gab = {1: {"letra": "A", "disciplina": "MATEMATICA"},
               2: {"letra": "B", "disciplina": "ATUALIDADES DO MERCADO FINANCEIRO"}}
        q1, y = questao_em(740, 1, "Quanto é dois mais dois, em unidades?")
        cabecalho = [(120, y - 20, "A TUALIDADES", True, 12), (90, y - 34, "DO MERCADO FINANCEIRO", True, 12)]
        q2, _ = questao_em(y - 60, 2, "O Pix é um arranjo de pagamentos instituído pelo")
        qs = c.montar_questoes([pagina([(397, 760, "MATEMÁTICA", True, 12)] + q1 + cabecalho + q2)], gab)
        self.assertEqual([q.problemas for q in qs], [[], []])
        self.assertEqual(qs[1].texto_apoio, "")

    def test_rascunho_repetido_nao_entra_na_alternativa(self):
        gab = {1: {"letra": "A", "disciplina": "MATEMATICA"}}
        q1, y = questao_em(740, 1, "Quanto é dois mais dois, em unidades?")
        q1.append((ESQ, y, "RASCUNHO", True, 14))
        q1.append((120, y, "RASCUNHO", True, 14))
        qs = c.montar_questoes([pagina([(86, 760, "MATEMÁTICA", True, 12)] + q1)], gab)
        self.assertEqual(qs[0].alternativas[4], ("E", "cinco"))


class ConferenciaEntreVersoesTests(SimpleTestCase):
    def _q(self, numero, enunciado, alternativas, correta, problemas=()):
        return c.QuestaoExtraida(numero=numero, enunciado=enunciado, correta=correta,
                                 alternativas=list(zip("ABCDE", alternativas)), problemas=list(problemas))

    def test_mesma_resposta_com_alternativas_embaralhadas(self):
        a = [self._q(1, "Capital do Brasil?", ["Rio", "Brasília", "Recife", "Belém", "Natal"], "B")]
        b = [self._q(7, "Capital do Brasil?", ["Natal", "Belém", "Recife", "Rio", "Brasília"], "E")]
        self.assertEqual(c.conferir_versoes(a, b), {1: "conferida"})

    def test_resposta_diferente_e_divergencia(self):
        a = [self._q(1, "Capital do Brasil?", ["Rio", "Brasília", "Recife", "Belém", "Natal"], "B")]
        b = [self._q(7, "Capital do Brasil?", ["Natal", "Belém", "Recife", "Rio", "Brasília"], "D")]
        self.assertEqual(c.conferir_versoes(a, b), {1: "divergente"})

    def test_alternativa_contaminada_em_uma_versao_e_divergencia(self):
        a = [self._q(1, "Taxa?", ["1,6%\nDados:", "1,8%", "2,0%", "3,1%", "4,0%"], "E")]
        b = [self._q(2, "Taxa?", ["1,8%\nDados:", "1,6%", "4,0%", "2,0%", "3,1%"], "C")]
        self.assertEqual(c.conferir_versoes(a, b), {1: "divergente"})

    def test_sem_correspondente_na_outra_versao(self):
        a = [self._q(1, "Capital do Brasil?", ["Rio", "Brasília", "Recife", "Belém", "Natal"], "B")]
        self.assertEqual(c.conferir_versoes(a, []), {1: "sem par"})

    def test_questao_com_problema_nao_e_conferida(self):
        a = [self._q(1, "Capital?", ["a", "b", "c", "d", "e"], "B", problemas=["figura na área da questão"])]
        self.assertEqual(c.conferir_versoes(a, a), {1: "sem par"})

    def test_par_com_texto_solto_ao_redor_ainda_serve(self):
        a = [self._q(1, "Capital do Brasil?", ["Rio", "Brasília", "Recife", "Belém", "Natal"], "B")]
        b = [self._q(7, "Capital do Brasil?", ["Natal", "Belém", "Recife", "Rio", "Brasília"], "E",
                     problemas=["texto solto antes da questão"])]
        self.assertEqual(c.conferir_versoes(a, b), {1: "conferida"})
