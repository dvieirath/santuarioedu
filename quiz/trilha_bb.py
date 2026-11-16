"""
Trilha Banco do Brasil — fonte única do que o edital pede.

Referência: Edital de Abertura, Seleção Externa 2022/001 (prova em 23/04/2023,
Fundação Cesgranrio). É o último edital publicado e vale como referência até
sair o próximo. Estrutura da prova: itens 7.1 e 7.2. Conteúdo: Anexo III.
https://www.bb.com.br/docs/portal/dipes/Edital-de-Abertura-de-Selecao-Externa-2022-01.pdf

Quando sair edital novo: atualizar ESTE arquivo e rodar
`python manage.py seed_trilha_bb --aplicar`. O resto do sistema (disciplinas do
concurso, árvore de categorias) deriva daqui.

Dois cargos, ambos Escriturário:
  - 'bb'    Agente Comercial (todas as microrregiões, exceto a de TI)
  - 'bb-ti' Agente de Tecnologia (microrregião 158, TI)

Cada disciplina do edital aponta para uma categoria da árvore (`caminho`) e
lista os tópicos que viram subcategorias. Disciplinas gerais (Português,
Matemática, Informática) reaproveitam as categorias que já existem, para o
conteúdo servir a mais de uma trilha. `item` é o número do item no Anexo III.
"""

EDITAL = {
    'id': 'bb_2022_001',
    'orgao': 'Banco do Brasil',
    'banca': 'Cesgranrio',
    'ano_prova': 2023,
    'tipo_questao': 'ME',          # múltipla escolha, uma correta
    'alternativas': 5,
    'duracao_min': 300,            # objetiva + redação, mesmo dia
    # 7.1.4 e 7.2.4: elimina quem fica abaixo de 50% no total, em Conhecimentos
    # Básicos ou em Conhecimentos Específicos, e quem zera qualquer disciplina.
    'aproveitamento_minimo': 0.5,
    'elimina_zero_em_disciplina': True,
    # 7.3: redação dissertativo-argumentativa, eliminatória.
    'redacao_maxima': 100,
    'redacao_minima': 70,
    # 7.1.6 e 7.2.6: só corrige a redação de quem ficou dentro deste múltiplo
    # de (vagas + cadastro de reserva) da microrregião.
    'redacao_multiplo_vagas': 3,
}

_AREAS = 'Áreas Específicas'

DISCIPLINAS = {
    'portugues': {
        'nome_edital': 'Língua Portuguesa',
        'caminho': ('Linguagens e Códigos', 'Português'),
        'topicos': [
            (1, 'Compreensão de Textos'),
            (2, 'Ortografia Oficial'),
            (3, 'Classe e Emprego de Palavras'),
            (4, 'Crase'),
            (5, 'Sintaxe da Oração e do Período'),
            (6, 'Pontuação'),
            (7, 'Concordância Verbal e Nominal'),
            (8, 'Regência Verbal e Nominal'),
            (9, 'Colocação Pronominal'),
        ],
    },
    'ingles': {
        'nome_edital': 'Língua Inglesa',
        'caminho': ('Linguagens e Códigos', 'Língua Inglesa'),
        # Item único no edital: vocabulário e gramática básica para compreensão
        # de textos. Não há subdivisão oficial; as questões ficam na disciplina.
        'topicos': [],
    },
    'matematica': {
        'nome_edital': 'Matemática',
        'caminho': ('Matemática e Raciocínio', 'Matemática'),
        'topicos': [
            (1, 'Números e Problemas de Contagem'),
            (2, 'Sistema Legal de Medidas'),
            (3, 'Razões, Proporções e Porcentagens'),
            (4, 'Lógica Proposicional'),
            (5, 'Noções de Conjuntos'),
            (6, 'Relações e Funções'),
            (7, 'Matrizes'),
            (8, 'Determinantes'),
            (9, 'Sistemas Lineares'),
            (10, 'Sequências'),
            (11, 'Progressões Aritméticas e Geométricas'),
        ],
    },
    'atualidades': {
        'nome_edital': 'Atualidades do Mercado Financeiro',
        'caminho': (_AREAS, 'Atualidades do Mercado Financeiro'),
        'topicos': [
            (1, 'Bancos na Era Digital'),
            (2, 'Internet Banking'),
            (3, 'Mobile Banking'),
            (4, 'Open Banking'),
            (5, 'Novos Modelos de Negócios'),
            (6, 'Fintechs, Startups e Big Techs'),
            (7, 'Shadow Banking'),
            (8, 'Funções da Moeda'),
            (9, 'Blockchain e Criptomoedas'),
            (10, 'Marketplace'),
            (11, 'Correspondentes Bancários'),
            (12, 'Arranjos de Pagamentos'),
            (13, 'PIX'),
            (14, 'Segmentação e Interações Digitais'),
            (15, 'Transformação Digital no Sistema Financeiro'),
        ],
    },
    'mat_financeira': {
        'nome_edital': 'Matemática Financeira',
        'caminho': ('Matemática e Raciocínio', 'Matemática Financeira'),
        'topicos': [
            (1, 'Conceitos Gerais e Valor do Dinheiro no Tempo'),
            (2, 'Juros Simples'),
            (3, 'Juros Compostos'),
            (4, 'Sistemas de Amortização (Price e SAC)'),
        ],
    },
    'bancarios': {
        'nome_edital': 'Conhecimentos Bancários',
        'caminho': (_AREAS, 'Conhecimentos Bancários'),
        'topicos': [
            (1, 'Sistema Financeiro Nacional'),
            (2, 'Mercado Financeiro e seus Desdobramentos'),
            (3, 'Moeda e Política Monetária'),
            (4, 'Orçamento Público, Títulos do Tesouro e Dívida Pública'),
            (5, 'Produtos Bancários'),
            (6, 'Mercado de Capitais'),
            (7, 'Mercado de Câmbio'),
            (8, 'Regimes de Taxas de Câmbio'),
            (9, 'Taxas de Câmbio Nominais e Reais'),
            (10, 'Câmbio, Exportações e Importações'),
            (11, 'Diferencial de Juros, Prêmio de Risco e Fluxo de Capitais'),
            (12, 'Mercado Interbancário'),
            (13, 'Mercado Bancário: Tesouraria, Varejo e Recuperação de Crédito'),
            (14, 'Taxas de Juros e Curva de Juros'),
            (15, 'Garantias do Sistema Financeiro Nacional'),
            (16, 'Prevenção à Lavagem de Dinheiro'),
            (17, 'Autorregulação Bancária'),
            (18, 'Sigilo Bancário'),
            (19, 'Lei Geral de Proteção de Dados (LGPD)'),
            (20, 'Legislação Anticorrupção'),
            (21, 'Segurança Cibernética'),
            (22, 'Ética Aplicada e Código de Ética do BB'),
            (23, 'Responsabilidade Socioambiental do BB'),
        ],
    },
    'informatica': {
        'nome_edital': 'Conhecimentos de Informática',
        'caminho': ('Informática',),
        # Itens 1, 2, 3 e 6 reaproveitam subcategorias que já existiam.
        'topicos': [
            (1, 'Windows'),
            (1, 'Linux'),
            (2, 'Pacote Office'),
            (3, 'Segurança da Informação'),
            (4, 'Proteção de Estações de Trabalho'),
            (5, 'Organização de Arquivos, Pastas e Programas'),
            (6, 'Redes de Computadores'),
            (7, 'Navegadores e Busca na Web'),
            (8, 'Correio Eletrônico, Grupos, Fóruns e Wikis'),
            (9, 'Redes Sociais'),
            (10, 'Suporte à Decisão e Inteligência de Negócio'),
            (11, 'Fundamentos de Análise de Dados'),
            (12, 'Educação a Distância'),
            (13, 'Ferramentas Multimídia'),
            (14, 'Ferramentas de Produtividade e Trabalho a Distância'),
        ],
    },
    'vendas': {
        'nome_edital': 'Vendas e Negociação',
        'caminho': (_AREAS, 'Vendas e Negociação'),
        'topicos': [
            (1, 'Estratégia Empresarial'),
            (2, 'Segmentação de Mercado'),
            (3, 'Valor Percebido pelo Cliente'),
            (4, 'Gestão da Experiência do Cliente'),
            (5, 'Aprendizagem e Sustentabilidade Organizacional'),
            (6, 'Características dos Serviços'),
            (7, 'Gestão da Qualidade em Serviços'),
            (8, 'Técnicas de Vendas'),
            (9, 'Marketing Digital'),
            (10, 'Ética e Conduta Profissional em Vendas'),
            (11, 'Padrões de Qualidade no Atendimento'),
            (12, 'Canais Remotos para Vendas'),
            (13, 'Comportamento do Consumidor'),
            (14, 'Política de Relacionamento com o Cliente'),
            (15, 'Ouvidoria'),
            (16, 'Estatuto da Pessoa com Deficiência'),
            (17, 'Código de Defesa do Consumidor'),
        ],
    },
    # ── Só Agente de Tecnologia ──────────────────────────────────────────────
    'estatistica': {
        'nome_edital': 'Probabilidade e Estatística',
        'caminho': ('Matemática e Raciocínio', 'Estatística e Probabilidade'),
        'topicos': [
            (1, 'Representação Tabular e Gráfica'),
            (2, 'Medidas de Tendência Central e de Dispersão'),
            (3, 'Variáveis Aleatórias e Distribuição de Probabilidade'),
            (4, 'Teorema de Bayes'),
            (5, 'Probabilidade Condicional'),
            (6, 'População e Amostra'),
            (7, 'Variância e Covariância'),
            (8, 'Correlação Linear Simples'),
            (9, 'Distribuição Binomial e Distribuição Normal'),
            (10, 'Amostragem e Inferência Estatística'),
        ],
    },
    'ti': {
        'nome_edital': 'Tecnologia da Informação',
        'caminho': (_AREAS, 'Tecnologia da Informação'),
        'topicos': [
            (1, 'Aprendizagem de Máquina'),
            (2, 'Banco de Dados'),
            (3, 'Big Data'),
            (4, 'Desenvolvimento Mobile'),
            (5, 'Estrutura de Dados e Algoritmos'),
            (6, 'Linguagens de Programação e Ferramentas'),
        ],
    },
}

# (chave da disciplina, questões, valor de cada questão)
_BASICOS = [
    ('portugues', 10, 1.5),
    ('ingles', 5, 1.0),
    ('matematica', 5, 1.5),
    ('atualidades', 5, 1.0),
]

CARGOS = {
    'bb': {
        'nome': 'Banco do Brasil — Agente Comercial',
        'cargo': 'Escriturário — Agente Comercial',
        'blocos': [
            ('Conhecimentos Básicos', _BASICOS),
            ('Conhecimentos Específicos', [
                ('mat_financeira', 5, 1.5),
                ('bancarios', 10, 1.5),
                ('informatica', 15, 1.5),
                ('vendas', 15, 1.5),
            ]),
        ],
    },
    'bb-ti': {
        'nome': 'Banco do Brasil — Agente de Tecnologia',
        'cargo': 'Escriturário — Agente de Tecnologia',
        'blocos': [
            ('Conhecimentos Básicos', _BASICOS),
            ('Conhecimentos Específicos', [
                ('estatistica', 5, 1.5),
                ('bancarios', 5, 1.5),
                ('ti', 35, 1.5),
            ]),
        ],
    },
}


def itens_do_cargo(slug):
    """Lista plana das disciplinas de um cargo, na ordem do edital.

    Cada item: {chave, bloco, nome_edital, categoria, caminho, questoes, valor, pontos}.
    `categoria` é o nome da categoria na árvore (último nível de `caminho`).
    """
    itens = []
    for bloco, disciplinas in CARGOS[slug]['blocos']:
        for chave, questoes, valor in disciplinas:
            d = DISCIPLINAS[chave]
            itens.append({
                'chave': chave,
                'bloco': bloco,
                'nome_edital': d['nome_edital'],
                'categoria': d['caminho'][-1],
                'caminho': d['caminho'],
                'questoes': questoes,
                'valor': valor,
                'pontos': questoes * valor,
            })
    return itens


def disciplinas_do_cargo(slug):
    """Nomes das categorias das disciplinas do cargo (formato de CONCURSO_DISCIPLINAS)."""
    return [item['categoria'] for item in itens_do_cargo(slug)]


def total_questoes(slug):
    return sum(item['questoes'] for item in itens_do_cargo(slug))


def total_pontos(slug):
    return sum(item['pontos'] for item in itens_do_cargo(slug))


def pontos_por_bloco(slug):
    totais = {}
    for item in itens_do_cargo(slug):
        totais[item['bloco']] = totais.get(item['bloco'], 0) + item['pontos']
    return totais
