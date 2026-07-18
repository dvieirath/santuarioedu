"""
Importa as 120 questões CEBRASPE - PF - Agente Administrativo - Edital 2025
Tipo: Certo/Errado
Gabarito oficial definitivo (gabarito_definitivo.pdf):
  - Itens 1-50:  Conhecimentos Básicos (Nível Médio)  — página 2 do gabarito
  - Itens 51-120: Conhecimentos Específicos (Cargo 15) — página 17 do gabarito
  - Itens 96 e 97: ANULADOS (X)
"""
import sys, os
sys.path.insert(0, r'C:\Users\USER\Downloads\projeto_prf')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prf_master.settings')
import django; django.setup()

from django.db import transaction
from quiz.models import Questao, Alternativa, Categoria

# ── Gabarito definitivo ───────────────────────────────────────────────────────
# C = Certo, E = Errado, X = Anulado
GABARITO = {
    # Conhecimentos Básicos – Nível Médio (pág. 2)
    1:'E', 2:'C', 3:'C', 4:'E', 5:'E', 6:'E', 7:'C', 8:'E', 9:'E', 10:'E',
    11:'C', 12:'E', 13:'E', 14:'C', 15:'C', 16:'C', 17:'E', 18:'E', 19:'C', 20:'E',
    21:'C', 22:'E', 23:'E', 24:'C', 25:'E', 26:'C', 27:'C', 28:'E', 29:'E', 30:'C',
    31:'E', 32:'C', 33:'C', 34:'C', 35:'E', 36:'C', 37:'C', 38:'C', 39:'E', 40:'E',
    41:'C', 42:'E', 43:'E', 44:'C', 45:'C', 46:'C', 47:'C', 48:'E', 49:'E', 50:'E',
    # Conhecimentos Específicos – Cargo 15: Agente Administrativo (pág. 17)
    51:'C', 52:'C', 53:'E', 54:'E', 55:'E', 56:'C', 57:'E', 58:'C', 59:'C', 60:'E',
    61:'C', 62:'C', 63:'E', 64:'E', 65:'C', 66:'C', 67:'E', 68:'E', 69:'C', 70:'C',
    71:'C', 72:'E', 73:'E', 74:'E', 75:'C', 76:'C', 77:'C', 78:'E', 79:'C', 80:'C',
    81:'E', 82:'C', 83:'E', 84:'E', 85:'E', 86:'C', 87:'E', 88:'C', 89:'E', 90:'E',
    91:'E', 92:'E', 93:'C', 94:'C', 95:'C', 96:'X', 97:'X', 98:'E', 99:'E', 100:'C',
    101:'E', 102:'E', 103:'E', 104:'C', 105:'C', 106:'C', 107:'C', 108:'E', 109:'C', 110:'C',
    111:'E', 112:'C', 113:'C', 114:'C', 115:'E', 116:'E', 117:'E', 118:'C', 119:'E', 120:'C',
}

# ── Categorias ────────────────────────────────────────────────────────────────
CAT_LP,   _ = Categoria.objects.get_or_create(nome='Língua Portuguesa')
CAT_RL,   _ = Categoria.objects.get_or_create(nome='Raciocínio Lógico e Matemática')
CAT_INFO, _ = Categoria.objects.get_or_create(nome='Informática')
CAT_DC,   _ = Categoria.objects.get_or_create(nome='Direito Constitucional')
CAT_DA,   _ = Categoria.objects.get_or_create(nome='Direito Administrativo')
CAT_AP,   _ = Categoria.objects.get_or_create(nome='Administração Pública')
CAT_SP,   _ = Categoria.objects.get_or_create(nome='Segurança Pública')

# ── Dados das questões: (categoria, assunto, texto) ───────────────────────────
QUESTOES = {
    # ── CONHECIMENTOS BÁSICOS ─────────────────────────────────────────────────
    # Língua Portuguesa — Texto 1: Criatividade (Q1–Q8)
    1:  (CAT_LP, 'Língua Portuguesa — Crase',
         'É opcional o emprego do acento indicativo de crase no vocábulo "àqueles" (último período do primeiro parágrafo do texto sobre criatividade).'),
    2:  (CAT_LP, 'Língua Portuguesa — Interpretação de texto',
         'De acordo com o texto sobre criatividade, muitas pessoas descreem da própria capacidade criativa.'),
    3:  (CAT_LP, 'Língua Portuguesa — Referência pronominal',
         'No quinto parágrafo do texto sobre criatividade, os termos "aquele" (primeiro período) e "Ele" (segundo período) têm o mesmo referente.'),
    4:  (CAT_LP, 'Língua Portuguesa — Interpretação de texto',
         'Entende-se da leitura do texto sobre criatividade que a criatividade é fruto da combinação entre os pensamentos convergente e divergente.'),
    5:  (CAT_LP, 'Língua Portuguesa — Interpretação de texto',
         'O autor do texto sobre criatividade argumenta contra a proposta de J. P. Guilford sobre o raciocínio humano.'),
    6:  (CAT_LP, 'Língua Portuguesa — Interpretação de texto',
         'No texto sobre criatividade, o pensamento convergente é apresentado como mais complexo para os seres humanos que o divergente.'),
    7:  (CAT_LP, 'Língua Portuguesa — Concordância',
         'No primeiro período do texto sobre criatividade, o termo "incapazes" refere-se ao substantivo "animais".'),
    8:  (CAT_LP, 'Língua Portuguesa — Concordância verbal',
         'No trecho "ou chegar a conclusões após uma análise" (segundo período do quarto parágrafo do texto sobre criatividade), o verbo "chegar" poderia ser flexionado no plural — chegarem — sem prejuízo da correção gramatical e do sentido original do texto.'),

    # Língua Portuguesa — Texto 2: Segurança Cibernética (Q9–Q18)
    9:  (CAT_LP, 'Língua Portuguesa — Concordância',
         'No último período do terceiro parágrafo do texto sobre segurança cibernética, o termo "utilizadas" está flexionado no feminino plural porque estabelece concordância com "pessoas famosas e celebridades".'),
    10: (CAT_LP, 'Língua Portuguesa — Interpretação de texto',
         'Segundo o texto sobre segurança cibernética, a IA generativa tem crescido de forma exponencial, assim como a adoção de medidas de segurança cibernética.'),
    11: (CAT_LP, 'Língua Portuguesa — Regência verbal',
         'O verbo "induzir" (terceiro período do terceiro parágrafo do texto sobre segurança cibernética), na acepção em que está empregado no texto, comporta-se como transitivo direto, não admitindo, portanto, que seu complemento seja introduzido pela preposição a.'),
    12: (CAT_LP, 'Língua Portuguesa — Interpretação de texto',
         'De acordo com o texto sobre segurança cibernética, os crimes cibernéticos em que se utiliza a tecnologia deepfake são os que mais crescem no Brasil.'),
    13: (CAT_LP, 'Língua Portuguesa — Interpretação de texto',
         'Conclui-se do texto sobre segurança cibernética que o Brasil lidera o ranking mundial de fraudes cometidas em ambiente virtual baseadas na utilização de imagens de pessoas famosas e celebridades.'),
    14: (CAT_LP, 'Língua Portuguesa — Pronomes e coesão',
         'A substituição de "Isso" (segundo período do segundo parágrafo do texto sobre segurança cibernética) por "O que" prejudicaria a correção gramatical do texto.'),
    15: (CAT_LP, 'Língua Portuguesa — Sintaxe',
         'No primeiro período do terceiro parágrafo do texto sobre segurança cibernética, a supressão da expressão "é o que" alteraria as relações sintáticas entre elementos do período, mas manteria a coerência das ideias e a correção gramatical do texto.'),
    16: (CAT_LP, 'Língua Portuguesa — Pontuação',
         'O emprego de travessão no lugar da vírgula após "deepfakes" (primeiro período do terceiro parágrafo do texto sobre segurança cibernética) manteria a correção gramatical do texto sem prejuízo de seu sentido original.'),
    17: (CAT_LP, 'Língua Portuguesa — Pronome se',
         'Em "Trata-se de uma tática" (terceiro período do terceiro parágrafo do texto sobre segurança cibernética), o vocábulo "se" funciona como pronome apassivador.'),
    18: (CAT_LP, 'Língua Portuguesa — Crase',
         'Na expressão "Não à toa" (último período do terceiro parágrafo do texto sobre segurança cibernética), é facultativo o emprego do sinal indicativo de crase no vocábulo "à".'),

    # Redação Oficial (Q19–Q20)
    19: (CAT_LP, 'Redação Oficial — Manual de Redação da Presidência da República',
         'No corpo do texto de uma correspondência oficial, os pronomes de tratamento podem ser empregados em sua forma abreviada ou por extenso.'),
    20: (CAT_LP, 'Redação Oficial — Manual de Redação da Presidência da República',
         'Nas comunicações oficiais, deve-se evitar o emprego de palavras e expressões simples, assim como o de frases curtas.'),

    # Raciocínio Lógico — Lógica Sentencial (Q21–Q23)
    # Proposição P: "Não quero debate, mas não tenho receio de debater."
    21: (CAT_RL, 'Raciocínio Lógico — Lógica sentencial',
         'Considerando a proposição P: "Não quero debate, mas não tenho receio de debater." — A proposição P é equivalente à negação de "Se não quero debate, então tenho receio de debater.".'),
    22: (CAT_RL, 'Raciocínio Lógico — Tabela-verdade',
         'Considerando a proposição P: "Não quero debate, mas não tenho receio de debater." — A tabela-verdade associada à proposição P tem mais de 5 linhas.'),
    23: (CAT_RL, 'Raciocínio Lógico — Condição suficiente',
         'Considerando a proposição P: "Não quero debate, mas não tenho receio de debater." — "Não quero debate" é condição suficiente para a veracidade da proposição P.'),

    # Raciocínio Lógico — Probabilidade (Q24–Q26)
    # Contexto: entrevista com 60 pessoas; 17 gostam de dirigir; 53 sentem nervosismo ao dirigir
    24: (CAT_RL, 'Raciocínio Lógico — Probabilidade',
         'Em uma entrevista com 60 pessoas, 17 informaram que gostam de dirigir e 53 informaram que sentem nervosismo ao dirigir. Se uma das pessoas entrevistadas for escolhida aleatoriamente, a probabilidade de ela ter informado que gosta de dirigir é superior a 1/4.'),
    25: (CAT_RL, 'Raciocínio Lógico — Conjuntos',
         'Em uma entrevista com 60 pessoas, 17 informaram que gostam de dirigir e 53 informaram que sentem nervosismo ao dirigir. Conclui-se das informações apresentadas que não há, entre as pessoas entrevistadas, quem tenha informado que não gosta de dirigir e que não sente nervosismo ao dirigir.'),
    26: (CAT_RL, 'Raciocínio Lógico — Conjuntos',
         'Em uma entrevista com 60 pessoas, 17 informaram que gostam de dirigir e 53 informaram que sentem nervosismo ao dirigir. Pelo menos 10 entre as pessoas entrevistadas informaram tanto gostar de dirigir quanto sentir nervosismo ao dirigir.'),

    # Ética no Serviço Público (Q27–Q32)
    27: (CAT_DA, 'Ética no Serviço Público — Princípios',
         'A moralidade é princípio que rege a atuação da administração pública.'),
    28: (CAT_DA, 'Ética no Serviço Público — Código de Ética',
         'Advertência, suspensão e demissão são penas aplicáveis ao servidor público pela comissão de ética.'),
    29: (CAT_DA, 'Ética no Serviço Público — Conduta do servidor',
         'A função pública é segregada da vida particular do servidor público, razão pela qual fatos e atos verificados em sua vida privada não interferem no bom conceito de sua vida funcional.'),
    30: (CAT_DA, 'Ética no Serviço Público — Decreto n.º 1.171/1994',
         'O Código de Ética Profissional do Serviço Público (Decreto n.º 1.171/1994) estabelece como dever fundamental do servidor público a imediata comunicação a seus superiores de qualquer ato ou fato contrário ao interesse público, bem como a exigência das providências cabíveis.'),
    31: (CAT_DA, 'Ética no Serviço Público — Conceito de servidor',
         'Para fins de apuração do comprometimento ético, só é considerado servidor público aquele que, após aprovação em concurso público, preste serviços de natureza permanente, com retribuição financeira, a órgão do poder estatal.'),
    32: (CAT_DA, 'Ética no Serviço Público — Conduta do servidor',
         'Ao servidor público é defeso ser, em decorrência do seu espírito de solidariedade, conivente com condutas imorais, ilegais ou aéticas no exercício da função pública.'),

    # Lei 8.112/1990 (Q33–Q35)
    33: (CAT_DA, 'Lei 8.112/1990 — Regime disciplinar',
         'A penalidade de suspensão aplicável ao servidor público não poderá exceder o prazo de 90 dias.'),
    34: (CAT_DA, 'Lei 8.112/1990 — Deveres do servidor',
         'Zelar pela economia do material utilizado no exercício de suas funções constitui um dos deveres do servidor público.'),
    35: (CAT_DA, 'Lei 8.112/1990 — Responsabilidade civil',
         'A restituição dos valores de indenização pagos pelo Estado a particular em razão de danos causados a este devido a ato doloso praticado por servidor público será, preferencialmente, realizada mediante desconto na remuneração do servidor.'),

    # Improbidade e Conflito de Interesses (Q36–Q40)
    36: (CAT_DA, 'Lei 12.813/2013 — Conflito de interesses',
         'A prestação de serviços, ainda que eventuais, por agente público a empresa cuja atividade seja fiscalizada pelo ente ao qual o agente público está vinculado constitui situação de conflito de interesses.'),
    37: (CAT_DA, 'Lei 8.429/1992 — Improbidade Administrativa',
         'A voluntariedade do agente na prática de um ato de improbidade administrativa é condição insuficiente para caracterizar o dolo para fins de responsabilização nos termos da Lei de Improbidade Administrativa.'),
    38: (CAT_DA, 'Lei 12.813/2013 — Conflito de interesses',
         'A apresentação da declaração de imposto de renda e proventos de qualquer natureza é exigida para a posse de agente público e para o seu exercício no cargo público.'),
    39: (CAT_DA, 'Lei 8.429/1992 — Improbidade Administrativa',
         'A conduta de servidor público permitir, de forma dolosa, a locação de bem patrimonial do Estado por preço inferior ao de mercado consiste em ato de improbidade administrativa que importa enriquecimento ilícito.'),
    40: (CAT_DA, 'Lei 12.813/2013 — Conflito de interesses',
         'A ocorrência de lesão ao patrimônio público é indispensável para a caracterização de situação de conflito de interesses.'),

    # Informática — Windows/Office/Redes (Q41–Q45)
    41: (CAT_INFO, 'Informática — Redes de computadores',
         'LAN é uma rede de computadores geralmente restrita a um único ambiente físico, como um escritório ou uma escola, permitindo a comunicação entre dispositivos locais.'),
    42: (CAT_INFO, 'Informática — Redes de computadores',
         'Em redes de computadores, o endereço IP é definido como o protocolo responsável pela conversão de nomes de domínio em endereços físicos de dispositivos.'),
    43: (CAT_INFO, 'Informática — Windows 10',
         'No Windows 10, o recurso Visão de Tarefas permite visualizar, em segundo plano, as tarefas que estão sendo executadas pelo Gerenciador de Tarefas.'),
    44: (CAT_INFO, 'Informática — Excel 2019',
         'Ao se utilizar a função SOMASE do Excel 2019, caso haja um critério que inclua símbolos lógicos ou matemáticos, ele deve estar entre aspas duplas.'),
    45: (CAT_INFO, 'Informática — Excel 2019',
         'Em uma planilha do Excel 2019 com crimes registrados em A2:A200 e datas em B2:B200, para contar quantas vezes o crime de furto aparece, é correto utilizar a fórmula =CONT.SE(A2:A200;"furto").'),

    # Informática — Arquivos/Malware/Nuvem (Q46–Q50)
    46: (CAT_INFO, 'Informática — Armazenamento em nuvem',
         'No armazenamento de dados em nuvem, a escalabilidade de recursos pode ser automática, conforme a demanda.'),
    47: (CAT_INFO, 'Informática — Windows 10',
         'No Explorador de Arquivos do Windows 10, é possível, depois de selecionadas as opções correspondentes, exibir arquivos ocultos e extensões de nomes de arquivos.'),
    48: (CAT_INFO, 'Informática — Armazenamento em nuvem',
         'O armazenamento de dados em nuvem pública garante total controle físico dos dados pelo usuário, o que melhora a segurança da informação.'),
    49: (CAT_INFO, 'Informática — Malware',
         'Rootkit é um conjunto de ferramentas que permite ao atacante ocultar a presença de outros malwares, contudo sua principal fragilidade é a facilidade de ser detectado.'),
    50: (CAT_INFO, 'Informática — Malware',
         'Ransomware é um tipo de malware que não pode ser propagado por phishing, mas bloqueia o acesso ao sistema ou criptografa os arquivos da vítima, sendo exigido um pagamento de resgate para que o acesso seja restaurado.'),

    # ── CONHECIMENTOS ESPECÍFICOS ─────────────────────────────────────────────
    # Direito Constitucional (Q51–Q55)
    51: (CAT_DC, 'Direito Constitucional — Direitos fundamentais',
         'Nos presídios, o procedimento de revista em criança, adolescente ou pessoa com deficiência intelectual que não possa expressar seu consentimento válido deve ser substituído pela revista invertida, que é direcionada à pessoa a ser visitada.'),
    52: (CAT_DC, 'Direito Constitucional — Competência legislativa',
         'Norma estadual ou municipal que proíbe o uso da linguagem neutra de gênero nas instituições de ensino e nos órgãos públicos é inconstitucional, por invadir competência legislativa da União.'),
    53: (CAT_DC, 'Direito Constitucional — Poderes do Presidente da República',
         'Compete ao presidente da República expedir instruções para a execução de leis, decretos e regulamentos.'),
    54: (CAT_DC, 'Direito Constitucional — Jurisprudência STF',
         'Conforme o entendimento jurisprudencial do STF, a candidatura aos cargos de presidente ou de vice-presidente da República é permitida a indivíduos que não tenham filiação partidária.'),
    55: (CAT_DC, 'Direito Constitucional — Distrito Federal',
         'O Distrito Federal possui as mesmas competências legislativas dos estados, porém, por não ser dividido em municípios, não pode legislar a respeito de matérias afetas aos municípios.'),

    # Direito Constitucional — Previdência/Finanças (Q56–Q59)
    56: (CAT_DC, 'Direito Constitucional — Teto remuneratório',
         'Lei estadual não pode estabelecer a inclusão de verbas remuneratórias para servidores públicos como exceção ao teto constitucional.'),
    57: (CAT_DC, 'Direito Constitucional — Finanças públicas',
         'As normas de gestão financeira e patrimonial da administração pública direta e indireta devem ser estabelecidas por lei ordinária específica.'),
    58: (CAT_DC, 'Direito Constitucional — Banco Central',
         'Com o objetivo de regular a taxa de juros, o Banco Central do Brasil pode comprar e vender títulos de emissão do Tesouro Nacional.'),
    59: (CAT_DC, 'Direito Constitucional — Previdência social',
         'Qualquer benefício que venha a substituir o salário de contribuição ou o rendimento do trabalho do segurado da previdência social não poderá ser estabelecido em valor mensal inferior ao salário mínimo.'),

    # Direito Administrativo — Atos/Descentralização (Q60–Q61)
    60: (CAT_DA, 'Direito Administrativo — Atos administrativos',
         'São classificados como atos de gestão os atos administrativos que se destinam a dar andamento aos processos e documentos que tramitam na administração pública, preparando-os para posterior decisão de mérito a ser proferida pela autoridade competente.'),
    61: (CAT_DA, 'Direito Administrativo — Desconcentração e descentralização',
         'A criação do Departamento de Polícia Federal (DPF) é exemplo de desconcentração administrativa, uma vez que o DPF não goza de personalidade jurídica própria.'),

    # Direito Administrativo — Licitações/Controle/Responsabilidade (Q62–Q65)
    62: (CAT_DA, 'Direito Administrativo — Controle externo — TCU',
         'O controle legislativo sobre os atos da administração pública federal é exercido pelo Congresso Nacional com o auxílio do Tribunal de Contas da União (TCU), competindo a este último, entre outras atribuições, fiscalizar as contas nacionais das empresas supranacionais de cujo capital social a União participe, de forma direta ou indireta, nos termos do tratado constitutivo.'),
    63: (CAT_DA, 'Direito Administrativo — Responsabilidade civil do Estado',
         'A CF adota como regra a responsabilidade civil objetiva do Estado, com fundamento na teoria do risco integral, nas hipóteses em que um agente público, por meio de ação comissiva, causar dano a particular, bastando, para fins de responsabilização do Estado, a comprovação do dano e da atuação administrativa.'),
    64: (CAT_DA, 'Direito Administrativo — Licitações',
         'É permitido ao administrador público, com justificativa no interesse público e na particularidade do caso concreto, combinar duas das modalidades de licitação previstas em lei.'),
    65: (CAT_DA, 'Direito Administrativo — Contratação direta',
         'A contratação direta por inexigibilidade de licitação é admitida quando há inviabilidade de competição, ao passo que, nos casos de contratação direta por dispensa de licitação, existe a possibilidade de competição que justifique a licitação, todavia a lei autoriza que a administração pública opte pela realização, ou não, do procedimento licitatório.'),

    # LGPD / Processo Administrativo (Q66–Q67)
    66: (CAT_DA, 'Direito Administrativo — Processo administrativo federal (Lei 9.784/1999)',
         'A competência, no âmbito do processo administrativo federal, é irrenunciável e exercida pelos órgãos administrativos aos quais foi atribuída como própria, ressalvados os casos de delegação e avocação legalmente admitidos.'),
    67: (CAT_DA, 'LGPD — Dados pessoais sensíveis',
         'A LGPD veda o tratamento de dados pessoais sensíveis, podendo tal tratamento ocorrer na hipótese exclusiva de o titular ou seu responsável legal consenti-lo, de forma específica e destacada, para finalidades específicas.'),

    # Princípios da Administração Pública / Decreto 9.830/2019 (Q68–Q69)
    68: (CAT_DA, 'Direito Administrativo — Princípio da motivação',
         'A motivação de uma decisão administrativa deve ser específica, não podendo ser constituída por declaração de concordância com o conteúdo de notas técnicas, pareceres, informações, decisões ou propostas que tenham precedido a decisão.'),
    69: (CAT_DA, 'Direito Administrativo — Princípio da motivação',
         'Em decorrência do princípio da motivação, a administração pública deve indicar os fundamentos de fato e de direito de suas decisões, não se exigindo, em regra, formalidade específica.'),

    # Organizações e Cultura Organizacional (Q70–Q72)
    70: (CAT_AP, 'Administração — Estrutura organizacional — Departamentalização',
         'A departamentalização funcional tem como vantagens a manutenção do controle e da influência nas funções principais e a geração de eficiência mediante a especialização das atividades.'),
    71: (CAT_AP, 'Administração — Cultura organizacional',
         'Vida confortável, senso de autorrealização e equidade são exemplos de valores terminais da cultura organizacional.'),
    72: (CAT_AP, 'Administração — Estrutura organizacional — Departamentalização',
         'Entre as desvantagens da departamentalização por cliente, estão a dificuldade na aplicação de mão de obra e a complexidade da cooperação interdepartamental.'),

    # Planejamento Estratégico / Governança (Q73–Q74)
    73: (CAT_AP, 'Administração — Planejamento estratégico',
         'Na elaboração do planejamento estratégico, a análise interna tem por finalidade colocar em evidência as oportunidades e as ameaças da organização, a fim de que esta melhor se posicione no nicho de negócio.'),
    74: (CAT_AP, 'Administração — Gestão pública — Geração de valor',
         'A geração de valor na gestão pública consiste em gerenciar de forma a alcançar resultados consistentes, assegurando-se, para todas as partes interessadas, a primazia do aumento do valor intangível sobre o tangível.'),

    # Gestão por Processos e Projetos (Q75–Q77)
    75: (CAT_AP, 'Administração — Gestão de projetos — Rastreabilidade de requisitos',
         'A matriz de rastreabilidade de requisitos tem como objetivo garantir que cada requerimento adicione valor ao objetivo do projeto e esteja perfeitamente conectado ao escopo de atividades.'),
    76: (CAT_AP, 'Administração — Gestão da qualidade — Ciclo PDCA',
         'A terceira etapa do ciclo PDCA associa-se à coleta de informações referentes aos resultados obtidos, em que se verificam erros e acertos em relação ao planejamento.'),
    77: (CAT_AP, 'Administração — Gestão da qualidade — Custos da qualidade',
         'Os custos com refugos, retrabalhos e ações corretivas nos produtos ou serviços atrelam-se aos custos da não conformidade.'),

    # Inovação na Gestão Pública (Q78–Q79)
    78: (CAT_AP, 'Administração — Inovação — Inteligência artificial',
         'A inteligência artificial, imune às falhas de controle, pode automatizar tarefas repetitivas, como o processamento de documentos e a geração de relatórios, liberando tempo e recursos para atividades mais estratégicas.'),
    79: (CAT_AP, 'Administração — Inovação — Design thinking',
         'O uso de maquetes, encenações, fluxogramas e impressões em 3D adequa-se à etapa de prototipação do design thinking.'),

    # Recrutamento, Seleção, T&D (Q80–Q81)
    80: (CAT_AP, 'Gestão de Pessoas — Treinamento e desenvolvimento',
         'A prática de treinamento e desenvolvimento de pessoas pode promover o aumento da sua capacidade de entregar valor à organização, favorecendo a melhoria das habilidades para lidar com as atribuições e para assumir responsabilidades mais complexas.'),
    81: (CAT_AP, 'Gestão de Pessoas — Recrutamento e seleção',
         'Nos processos de recrutamento e seleção de pessoas, as organizações contemporâneas adotam abordagens tradicionais, centradas no cargo, embora o sistema formal das empresas seja construído de forma vinculada às competências.'),

    # Gestão de Desempenho, Motivação, Competências (Q82–Q84)
    82: (CAT_AP, 'Gestão de Pessoas — Motivação',
         'A geração de um ambiente de trabalho agradável e seguro, bem como a garantia de relações humanas amistosas e cooperativas, contribui na motivação para o trabalho e no alcance dos objetivos organizacionais.'),
    83: (CAT_AP, 'Gestão de Pessoas — Gestão de desempenho',
         'A gestão de desempenho é um processo que se limita ao alcance dos objetivos organizacionais e à entrega de resultados, mediante a realização de revisões periódicas e avaliações sistemáticas das pessoas integrantes do processo.'),
    84: (CAT_AP, 'Gestão de Pessoas — Gestão por competências',
         'Usualmente, é adequado que as competências sejam trabalhadas isoladamente nos processos de gestão organizacional, buscando-se identificar e reter talentos individuais para agregar valor aos negócios.'),

    # Comportamento Humano, Equipes, Conflitos (Q85–Q87)
    85: (CAT_AP, 'Gestão de Pessoas — Equipes de trabalho',
         'São denominadas autodirigidas as equipes compostas de talentos treinados para desempenhar um conjunto de tarefas independentes em diversas unidades de trabalho.'),
    86: (CAT_AP, 'Gestão de Pessoas — Comportamento organizacional',
         'O comportamento humano demonstrado no trabalho é decorrente tanto de características inatas, sejam elas biológicas, fisiológicas, físicas ou psicológicas, quanto da aprendizagem oriunda das vivências e experiências obtidas ao longo da vida.'),
    87: (CAT_AP, 'Gestão de Pessoas — Gestão de conflitos',
         'No mundo contemporâneo, o ideal é a eliminação dos conflitos no ambiente de trabalho, os quais devem ser abordados de forma adequada e reativa.'),

    # Gestão do Conhecimento e QVT (Q88–Q89)
    88: (CAT_AP, 'Gestão de Pessoas — Qualidade de vida no trabalho',
         'A qualidade de vida no trabalho extrapola os aspectos inerentes às necessidades, aos valores e às expectativas do indivíduo, abrangendo aspectos relativos à estrutura organizacional, aos sistemas de recompensas e às políticas internas.'),
    89: (CAT_AP, 'Gestão de Pessoas — Gestão do conhecimento',
         'Na atualidade, a gestão do conhecimento está mais vinculada aos recursos tecnológicos disponíveis (hardware e software) que aos saberes das pessoas.'),

    # Licitações / Contratos Lei 14.133/2021 (Q90–Q95)
    90: (CAT_AP, 'Administração — Licitações e contratos — Lei 14.133/2021 — Sanções',
         'As sanções a serem aplicadas pela administração pública no âmbito de contratações públicas restringem-se a advertência, multa e impedimento de licitar e contratar.'),
    91: (CAT_AP, 'Administração — Licitações e contratos — Fiscalização de contratos',
         'Os resultados da aplicação de instrumento para aferição da qualidade da prestação dos serviços contratados não têm o condão de ensejar alteração dos valores financeiros a serem pagos aos fornecedores.'),
    92: (CAT_AP, 'Administração — Licitações e contratos — Convênios',
         'É vedado à administração pública federal celebrar convênios com entidades privadas sem fins lucrativos para transferências de recursos.'),
    93: (CAT_AP, 'Administração — Licitações e contratos — IN MPOG n.º 5/2017',
         'A planilha de custos e formação de preços apresentada pelos licitantes, nos casos de contratação de serviços de limpeza, será a base da análise da exequibilidade da proposta de preços.'),
    94: (CAT_AP, 'Administração — Licitações e contratos — Fiscalização de contratos',
         'O fiscal técnico do contrato poderá aceitar a justificativa de fornecedor para a prestação do serviço com menor nível de conformidade que o pactuado, desde que comprovado o caráter excepcional da ocorrência e desde que esta resulte de fatores imprevisíveis e alheios ao controle do prestador de serviços.'),
    95: (CAT_AP, 'Administração — Licitações e contratos — Registro de preços',
         'Em regra, os órgãos da administração pública federal que tenham interesse em aderir à ata de registro de preços na condição de não participantes devem demonstrar a compatibilidade dos valores registrados com os valores praticados pelo mercado.'),

    # Gestão de Materiais (Q96–Q99)  — Q96 e Q97 anulados
    96: (CAT_AP, 'Administração — Gestão de materiais — Depreciação',
         'O método linear de depreciação de bens é o sistema aceito pela Receita Federal do Brasil.'),
    97: (CAT_AP, 'Administração — Gestão de materiais — Recebimento',
         'Na hipótese de recusa parcial de material no ato de seu recebimento, é necessária a emissão de nota fiscal de devolução.'),
    98: (CAT_AP, 'Administração — Gestão de materiais — Classificação de demanda',
         'Itens natalinos apresentam demanda de natureza irregular.'),
    99: (CAT_AP, 'Administração — Gestão de materiais — Curva ABC',
         'A curva ABC utiliza os valores unitários dos estoques de cada material como critério de classificação.'),

    # Lei 14.967/2024 — Segurança Privada (Q100–Q105)
    100: (CAT_SP, 'Lei 14.967/2024 — Segurança Privada — Agências bancárias',
          'Nas agências bancárias, durante o horário de atendimento ao público, é necessária a presença de, no mínimo, dois vigilantes, os quais deverão estar equipados com coletes balísticos.'),
    101: (CAT_SP, 'Lei 14.967/2024 — Segurança Privada — Cooperação entre PJs',
          'A prestação de serviços de segurança privada de forma cooperada entre pessoas jurídicas especializadas depende de prévia autorização do DPF.'),
    102: (CAT_SP, 'Lei 14.967/2024 — Segurança Privada — Requisitos do vigilante',
          'As atividades de vigilante e de vigilante supervisor podem ser exercidas por brasileiro nato ou naturalizado, sendo requisitos específicos mínimos para ambas as atividades a idade mínima de 21 anos e a conclusão do ensino médio.'),
    103: (CAT_SP, 'Lei 14.967/2024 — Segurança Privada — Condomínios',
          'Em condomínios edilícios que possuam serviços orgânicos de segurança privada, é vedado utilizar animais na execução de atividades de segurança.'),
    104: (CAT_SP, 'Lei 14.967/2024 — Segurança Privada — Serviços',
          'A segurança de eventos em espaços de uso comum do povo e a segurança perimetral nas guaritas são consideradas serviços de segurança privada.'),
    105: (CAT_SP, 'Lei 14.967/2024 — Segurança Privada — Competência da PF',
          'A aprovação dos modelos de uniformes adotados pelos prestadores de serviço de segurança privada é competência da Polícia Federal, à qual também cabe realizar, obrigatoriamente, ao menos uma vistoria anual nas dependências de instituições financeiras.'),

    # Lei 10.357/2001 / Lei 12.830/2013 (Q106–Q111)
    106: (CAT_SP, 'Lei 12.830/2013 — Inquérito policial',
          'Um inquérito policial em curso somente poderá ser avocado ou redistribuído por superior hierárquico do delegado de polícia, mediante despacho fundamentado, por motivo de interesse público ou nas hipóteses de inobservância dos procedimentos previstos em regulamento da corporação que prejudique a eficácia da investigação.'),
    107: (CAT_SP, 'Lei 10.357/2001 — Produtos químicos controlados',
          'O ministro de Estado da justiça e segurança pública pode atualizar a lista de produtos químicos a serem controlados, definida por meio de portaria, incluindo ou removendo produtos, independentemente de proposta do DPF, da Secretaria Nacional Antidrogas ou da Agência Nacional de Vigilância Sanitária.'),
    108: (CAT_SP, 'Lei 10.357/2001 — Produtos químicos controlados',
          'É exigida autorização prévia do DPF para importação, exportação ou reexportação de produtos químicos que possam ser utilizados como insumo na elaboração de substâncias entorpecentes, psicotrópicas ou que determinem dependência física ou psíquica, exceto no caso de substâncias que não estejam sob controle do órgão competente do Ministério da Saúde.'),
    109: (CAT_SP, 'Lei 10.357/2001 — Produtos químicos controlados',
          'Pessoa física que exerça atividade sujeita a controle e fiscalização cometerá infração administrativa se deixar de informar ao DPF qualquer suspeita de desvio de produto químico controlado, para fins ilícitos.'),
    110: (CAT_SP, 'Lei 10.357/2001 — Produtos químicos — FUNAD',
          'Os recursos relativos à cobrança da taxa de controle e fiscalização de produtos químicos, à aplicação de multa e à alienação de produtos químicos previstas na Lei n.º 10.357/2001 constituem receita do Fundo Nacional Antidrogas (FUNAD).'),
    111: (CAT_SP, 'Lei 10.357/2001 — Isenção de taxa',
          'As instituições de ensino, públicas e privadas, as entidades de caráter assistencial que comprovem essa condição e os órgãos da administração pública direta e indireta federal, estadual e municipal são isentos do pagamento da taxa de controle e fiscalização de produtos químicos.'),

    # Lei de Migração (Q112–Q117)
    112: (CAT_SP, 'Lei 13.445/2017 — Migração — Expulsão',
          'A expulsão é medida administrativa, e não judicial, que se caracteriza pela retirada compulsória de migrante ou visitante do território nacional, conjugada com o impedimento de reingresso por prazo determinado.'),
    113: (CAT_SP, 'Lei 13.445/2017 — Migração — Repatriação e deportação coletiva',
          'A repatriação, a deportação e a expulsão coletivas são vedadas, entendendo-se por repatriação, deportação ou expulsão coletiva aquela que não individualiza a situação migratória irregular de cada pessoa.'),
    114: (CAT_SP, 'Lei 13.445/2017 — Migração — Emigrante',
          'Brasileiro que se estabeleça no exterior, ainda que de forma temporária, será considerado emigrante.'),
    115: (CAT_SP, 'Lei 13.445/2017 — Migração — Transformação de visto',
          'Quando um visto diplomático ou oficial é transformado em autorização de residência, as prerrogativas decorrentes do visto são mantidas.'),
    116: (CAT_SP, 'Lei 13.445/2017 — Migração — Destino da expulsão',
          'Se um estrangeiro for expulso do território brasileiro, a sua expulsão deverá ser feita para o país de sua nacionalidade ou de sua procedência, ainda que outro país o aceite.'),
    117: (CAT_SP, 'Lei 13.445/2017 — Migração — Princípios',
          'Um dos princípios da política migratória brasileira previsto expressamente na Lei de Migração é o da independência nacional.'),

    # Estatuto do Desarmamento (Q118–Q120)
    118: (CAT_SP, 'Lei 10.826/2003 — Estatuto do Desarmamento — Crimes',
          'Constitui crime a conduta de importar, a qualquer título, arma de fogo sem autorização da autoridade competente, sendo aumentada da metade a pena aplicável se a arma de fogo for de uso proibido ou restrito.'),
    119: (CAT_SP, 'Lei 10.826/2003 — Estatuto do Desarmamento — Porte restrito',
          'No território nacional, a autorização para portar arma de fogo de uso restrito é competência da Polícia Federal, prescindindo tal concessão de autorização do Sistema Nacional de Armas (SINARM).'),
    120: (CAT_SP, 'Lei 10.826/2003 — Estatuto do Desarmamento — Munições',
          'A comercialização de munições entre duas pessoas físicas é permitida desde que haja a devida autorização do Sistema Nacional de Armas (SINARM).'),
}

# ── Importação ────────────────────────────────────────────────────────────────
print(f"Total de questões a importar: {len(QUESTOES)}")
print(f"Itens anulados (serão importados como anulado=True implicitamente): "
      f"{[n for n,g in GABARITO.items() if g=='X']}")

created_q = 0
created_a = 0
anuladas  = 0

with transaction.atomic():
    for num in range(1, 121):
        cat, assunto, texto = QUESTOES[num]
        gab = GABARITO[num]  # 'C', 'E' ou 'X'

        q = Questao.objects.create(
            categoria  = cat,
            texto      = texto,
            tipo       = 'CE',
            assunto    = assunto,
            banca      = 'CEBRASPE',
            ano        = 2025,
        )
        created_q += 1

        if gab == 'X':
            # Item anulado: cria ambas sem marcar nenhuma como correta
            Alternativa.objects.create(questao=q, texto='Certo',  correta=False)
            Alternativa.objects.create(questao=q, texto='Errado', correta=False)
            anuladas += 1
        else:
            Alternativa.objects.create(questao=q, texto='Certo',  correta=(gab=='C'))
            Alternativa.objects.create(questao=q, texto='Errado', correta=(gab=='E'))
        created_a += 2

print(f"\n✓ {created_q} questões criadas")
print(f"✓ {created_a} alternativas criadas")
print(f"  {anuladas} questões anuladas (itens 96 e 97)")

# Verificação rápida
print("\n=== Distribuição por categoria ===")
from django.db.models import Count
cats = (Questao.objects.filter(banca='CEBRASPE', ano=2025)
        .values('categoria__nome')
        .annotate(n=Count('id'))
        .order_by('-n'))
for c in cats:
    print(f"  {c['categoria__nome']}: {c['n']} questões")
