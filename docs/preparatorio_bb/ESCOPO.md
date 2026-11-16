# Preparatório Banco do Brasil — Escopo

Versão 0, 10/11/2026. Documento de partida: define o que entra, o que fica fora,
o que já existe e as decisões que ainda são suas. Nada aqui foi implementado.

## 1. Situação do concurso (consultado em 10/11/2026)

- Não há edital publicado nem data definida. O banco diz que não há previsão; a
  imprensa especializada e o sindicato falam em 2027.
- A banca não está confirmada. A Cesgranrio organizou os dois últimos (2021 e 2023);
  há notícia de outras interessadas (Cebraspe, FGV, IBFC).
- Último edital: Seleção Externa 2022/001, prova em 23/04/2023, 6.000 vagas de
  Escriturário (4.000 imediatas + 2.000 cadastro de reserva).

Consequência para o projeto: a referência é o edital 2022/001, mas nada pode ficar
preso à Cesgranrio ou àquele conteúdo. Quando o edital novo sair, a diferença de
conteúdo vira uma tarefa de atualização, não uma reconstrução.

## 2. A prova de referência (edital 2022/001, lido no PDF oficial)

Escriturário, Agente Comercial. 70 questões de múltipla escolha, 5 alternativas,
uma correta. 100 pontos. Objetiva e redação no mesmo dia, 5 horas no total.

| Bloco | Disciplina | Questões | Valor | Pontos |
|---|---|---:|---:|---:|
| Básicos | Língua Portuguesa | 10 | 1,5 | 15,0 |
| Básicos | Língua Inglesa | 5 | 1,0 | 5,0 |
| Básicos | Matemática | 5 | 1,5 | 7,5 |
| Básicos | Atualidades do Mercado Financeiro | 5 | 1,0 | 5,0 |
| Específicos | Matemática Financeira | 5 | 1,5 | 7,5 |
| Específicos | Conhecimentos Bancários | 10 | 1,5 | 15,0 |
| Específicos | Conhecimentos de Informática | 15 | 1,5 | 22,5 |
| Específicos | Vendas e Negociação | 15 | 1,5 | 22,5 |
| | **Total** | **70** | | **100,0** |

Regras que mudam o desenho do produto:

- **Eliminação na objetiva (7.2.4):** menos de 50% do total, ou menos de 50% em
  Conhecimentos Básicos, ou menos de 50% em Conhecimentos Específicos, ou nota
  zero em qualquer disciplina.
- **Redação (7.3):** dissertativo-argumentativa, 100 pontos, eliminatória, mínimo
  de 70. Só é corrigida para quem ficou dentro de 3 vezes a soma de vagas e
  cadastro de reserva da sua microrregião.
- **Classificação:** só pelos pontos da objetiva, por microrregião.

O que isso significa:

1. Informática e Vendas e Negociação somam 45 pontos. São a prioridade de conteúdo.
2. Zero em qualquer disciplina elimina. Inglês e Atualidades valem só 5 pontos
   cada, mas não podem ficar sem cobertura.
3. O formato é múltipla escolha de 5 alternativas. Questão de certo ou errado não
   serve para simulado BB.
4. A redação elimina. Um preparatório sem redação está incompleto.

## 3. O que o banco de questões já tem (SQLite local, 10/11/2026)

| Disciplina BB | Pontos | Oficiais liberadas | IA liberadas | Observação |
|---|---:|---:|---:|---|
| Conhecimentos de Informática | 22,5 | 94 | 206 | Oficiais são Cebraspe, quase todas certo ou errado |
| Vendas e Negociação | 22,5 | 0 | 0 | Categoria não existe |
| Conhecimentos Bancários | 15,0 | 0 | 0 | Categoria não existe |
| Língua Portuguesa | 15,0 | 98 | 364 | Idem Informática |
| Matemática | 7,5 | 145 | 0 | Mistura ENEM e concursos |
| Matemática Financeira | 7,5 | 0 | 0 | Categoria existe, vazia |
| Língua Inglesa | 5,0 | 12 | 0 | |
| Atualidades do Mercado Financeiro | 5,0 | 0 | 0 | Categoria não existe |

- Questões da Cesgranrio no banco: **zero**.
- Das liberadas, 79% são de certo ou errado. O acervo atual é Cebraspe.
- Disciplinas sem nenhuma questão somam 50 dos 100 pontos da prova.
- As IA liberadas não passaram por verificação de gabarito (análise de 10/11).
  Não contam como conteúdo pronto.

Conclusão: o código da plataforma se aproveita quase inteiro; o conteúdo BB
começa praticamente do zero.

## 4. Escopo

### Dentro (primeira versão)

1. **Trilha BB.** Concurso `bb` com as 8 disciplinas e a árvore de tópicos do
   Anexo III do edital (seção 7 deste documento).
2. **Banco de questões BB.** Múltipla escolha de 5 alternativas, cada questão
   ligada a um tópico do Anexo III, com gabarito conferido e explicação.
3. **Simulado no formato da prova.** 70 questões na distribuição do edital, 5 horas,
   nota em pontos com os pesos, e o resultado dizendo se o aluno seria eliminado
   por alguma das quatro regras do item 7.2.4.
4. **Estudo por tópico** com revisão espaçada e caderno de erros. Já existe.
5. **Painel de preparação BB.** Cobertura do edital, desempenho por disciplina em
   pontos, o que priorizar. A base já existe em `/preparacao/<slug>/`.
6. **Página pública `/concurso/bb/`** e demo com 3 questões BB conferidas.

### Segunda fase

7. **Redação.** Temas, os 5 critérios do edital e correção assistida.
8. **Questões inéditas por IA**, só com verificação de gabarito e, nos tópicos de
   norma, com o texto da norma no prompt.
9. **Material de teoria** por tópico (resumo, mapa mental). A geração já existe.

### Fora

- Agente de Tecnologia (35 questões de TI, só a microrregião de Brasília).
- Videoaulas e correção humana de redação.
- Duelo e simulado coletivo como parte do lançamento BB. Continuam no código,
  sem destaque.
- Qualquer promessa de aprovação. A linha do `PIVOT_ESTUDOS.md` continua valendo.
- Uso de marca: o material precisa dizer que não tem vínculo com o Banco do
  Brasil nem com a banca.

## 5. De onde vêm as questões

### Provas oficiais (primeiro)

Candidatas, a confirmar no site da Cesgranrio antes de baixar:

| Prova | Serve para |
|---|---|
| Banco do Brasil 2021 e 2023, Agente Comercial | Todas as 8 disciplinas, formato idêntico |
| Caixa, Técnico Bancário Novo 2021 e 2024 | Português, Matemática Financeira, Bancários, Informática, Atendimento |
| Banco da Amazônia e BNB, Cesgranrio | Português, Matemática, Bancários, Informática |
| Banco do Brasil 2010 a 2015 | Português, Matemática, Bancários; conteúdo antigo, conferir vigência |
| Outras Cesgranrio de nível médio | Português, Matemática, Inglês, Informática |

Limite conhecido: Vendas e Negociação e Atualidades do Mercado Financeiro só
existem nesse formato desde 2021. A oferta de questão oficial é pequena e só dá
para medir depois de baixar. A meta de 1000 oficiais por disciplina não fecha
nessas duas; a proposta está na seção 8.

### Regras de entrada (valem para oficial e IA)

- Questão só é liberada com tópico do Anexo III, gabarito conferido com o
  gabarito oficial e enunciado completo.
- Se a classificação automática falhar, a questão fica pendente em "A classificar".
  Hoje ela cai em Direito Constitucional (`importar_pdf_questoes.py`); isso precisa
  ser corrigido antes de importar qualquer prova nova.
- Questão anulada no gabarito definitivo não entra.
- IA só entra depois de uma segunda resolução às cegas concordar com o gabarito.
  Nos tópicos de norma (Lei 9.613/98, LC 105/2001, LGPD, Lei 12.846/2013,
  Resoluções CMN 4.893, 4.949 e 4.860, CDC, Lei 13.146/2015), o texto da norma
  vai no prompt e a explicação cita o artigo.

## 6. O que muda no código

| Item | Onde | Tamanho |
|---|---|---|
| Corrigir o destino padrão da importação | `quiz/management/commands/importar_pdf_questoes.py` | pequeno |
| Concurso `bb` nas escolhas do usuário | `quiz/models.py`, com migração | pequeno |
| Disciplinas do concurso | `quiz/preparacao.py` | pequeno |
| Página pública | `quiz/concurso_landing.py` | pequeno |
| Árvore de categorias do Anexo III | comando de seed novo | médio |
| Adaptador Cesgranrio no baixador | `scripts/baixar_provas_concursos/bancas/` | médio |
| Extração de múltipla escolha com gabarito por letra | importador | médio |
| Simulado com pesos, pontos e regra de eliminação | `EDITAIS_OFICIAIS` só tem contagem hoje | médio |
| Demo com 3 questões BB | `quiz/demo_curadoria.json` | pequeno |
| Verificação de gabarito para IA | novo passo antes de aprovar | médio |
| Redação | módulo novo | grande, fase 2 |

## 7. Árvore de tópicos (Anexo III do edital 2022/001)

**Língua Portuguesa.** Compreensão de textos. Ortografia oficial. Classe e emprego
de palavras. Crase. Sintaxe da oração e do período. Pontuação. Concordância verbal
e nominal. Regência verbal e nominal. Colocação dos pronomes oblíquos átonos.

**Língua Inglesa.** Vocabulário fundamental e aspectos gramaticais básicos para
compreensão de textos.

**Matemática.** Números inteiros, racionais e reais; problemas de contagem. Sistema
legal de medidas. Razões e proporções; divisão proporcional; regras de três;
porcentagens. Lógica proposicional. Noções de conjuntos. Relações e funções;
funções polinomiais, exponenciais e logarítmicas. Matrizes. Determinantes.
Sistemas lineares. Sequências. Progressões aritméticas e geométricas.

**Atualidades do Mercado Financeiro.** Os bancos na era digital. Internet banking.
Mobile banking. Open banking. Novos modelos de negócios. Fintechs, startups e big
techs. Shadow banking. Funções da moeda. Blockchain, bitcoin e demais
criptomoedas. Marketplace. Correspondentes bancários. Arranjos de pagamentos.
PIX. Segmentação e interações digitais. Transformação digital no sistema
financeiro.

**Matemática Financeira.** Conceitos gerais: valor do dinheiro no tempo; capital,
juros, taxas; capitalização e regimes; fluxos de caixa; equivalência financeira.
Juros simples. Juros compostos. Sistemas de amortização: Price e SAC.

**Conhecimentos Bancários.** Sistema Financeiro Nacional: estrutura, órgãos
normativos, supervisores, executores e operadores. Mercado financeiro: monetário,
de crédito, de capitais e cambial. Moeda e política monetária, inclusive
quantitative easing, Selic e compromissadas, depósitos remunerados. Orçamento
público, títulos do Tesouro e dívida pública. Produtos bancários: cartões, CDC,
crédito rural, poupança, capitalização, previdência, consórcio, investimentos,
seguros. Mercado de capitais. Mercado de câmbio: instituições e operações básicas;
regimes cambiais; câmbio nominal e real; impactos sobre exportações e
importações; diferencial de juros, prêmio de risco e fluxo de capitais. Dinâmica
do mercado: interbancário. Mercado bancário: tesouraria, varejo e recuperação de
crédito. Juros de curto prazo e curva de juros; nominais e reais. Garantias: aval,
fiança, penhor mercantil, alienação fiduciária, hipoteca, fianças bancárias.
Lavagem de dinheiro: Lei 9.613/98, Circular 3.978/2020, Carta Circular 4.001/2020.
Autorregulação bancária. Sigilo bancário: LC 105/2001. LGPD: Lei 13.709/2018.
Anticorrupção: Lei 12.846/2013 e Decreto 11.129/2022. Segurança cibernética:
Resolução CMN 4.893/2021. Ética aplicada e Código de Ética do BB. Política de
Responsabilidade Socioambiental do BB.

**Conhecimentos de Informática.** Windows 10 e Linux (SUSE SLES 15 SP2). Word,
Excel e PowerPoint (O365). Segurança da informação. Proteção de estações de
trabalho: USB, hardening, antimalware, firewall pessoal. Organização de arquivos,
pastas e programas. Redes, Internet e intranet. Navegadores (Edge, Firefox), busca
na Web. Correio eletrônico, grupos, fóruns e wikis. Redes sociais. Suporte à
decisão e inteligência de negócio. Fundamentos de análise de dados. Educação a
distância. Ferramentas multimídia. Ferramentas de produtividade e trabalho a
distância (Teams, Webex, Hangout, Drive, Skype).

**Vendas e Negociação.** Estratégia empresarial: análise de mercado, forças
competitivas, imagem, identidade e posicionamento. Segmentação de mercado. Valor
percebido pelo cliente. Gestão da experiência do cliente. Aprendizagem e
sustentabilidade organizacional. Características dos serviços. Qualidade em
serviços. Técnicas de vendas: da pré-abordagem ao pós-venda. Marketing digital:
leads, copywriting, gatilhos mentais, inbound. Ética e conduta em vendas. Padrões
de qualidade no atendimento. Canais remotos. Comportamento do consumidor. Política
de relacionamento com o cliente: Resolução 4.949/2021. Ouvidoria: Resolução CMN
4.860/2020. Lei Brasileira de Inclusão: Lei 13.146/2015. CDC: Lei 8.078/1990.

Versões de software e normas citadas são as de 2022. O edital novo deve trocar
várias; por isso o tópico é o nó da árvore, e a versão é um atributo.

## 8. Meta de conteúdo proposta

Sua meta geral é 1000 oficiais e 1000 IA por disciplina. Para o BB proponho duas
metas, ambas contando só questão verificada:

| Disciplina | Pontos | Lançamento | Alvo |
|---|---:|---:|---:|
| Conhecimentos de Informática | 22,5 | 300 | 1000 |
| Vendas e Negociação | 22,5 | 300 | 1000 |
| Conhecimentos Bancários | 15,0 | 250 | 1000 |
| Língua Portuguesa | 15,0 | 250 | 1000 |
| Matemática | 7,5 | 120 | 600 |
| Matemática Financeira | 7,5 | 120 | 600 |
| Língua Inglesa | 5,0 | 80 | 400 |
| Atualidades do Mercado Financeiro | 5,0 | 80 | 400 |

A meta de lançamento permite cerca de 20 simulados completos sem repetir questão.
A divisão entre oficial e IA em cada disciplina só dá para fixar depois de medir
quantas questões oficiais existem.

## 9. Fases

| Fase | Entrega | Depende de |
|---|---|---|
| 0 | Decisões da seção 10; correção do destino padrão da importação; concurso `bb`, disciplinas e árvore de tópicos no código | Suas respostas |
| 1 | Adaptador Cesgranrio; provas BB 2021 e 2023 importadas e conferidas; contagem real por disciplina | Fase 0 |
| 2 | Demais provas bancárias; simulado no formato da prova; painel e página pública | Fase 1 |
| 3 | IA com verificação para fechar os tópicos com pouca questão oficial; explicações | Fase 2 |
| 4 | Redação; beta fechado com poucos candidatos | Fase 3 |

A limpeza do acervo atual (rebaixar as IA sem verificação e reclassificar as
oficiais em categoria errada) corre em paralelo e não bloqueia a fase 0.

## 10. Decisões suas

1. **Cargo.** Só Agente Comercial, como proposto, ou também Agente de Tecnologia?
2. **O que quer dizer exclusivo.** O SantuarioEdu é lançado só com BB e os outros
   concursos saem da vitrine, ou BB é uma trilha a mais ao lado de PRF? Proposta:
   lançar só com BB. Um concurso bem coberto vale mais que sete pela metade.
3. **Banca de referência.** Cesgranrio até a banca ser anunciada. Confirma?
4. **Metas.** As da seção 8 servem, ou mantém 1000 e 1000 como condição de lançamento?
5. **Redação.** Segunda fase, como proposto, ou condição de lançamento?
6. **Preço.** Continua 100% gratuito ou o preparatório BB é pago?

## 11. Riscos

- **Banca diferente da Cesgranrio.** Muda o estilo das questões. O banco precisa
  guardar banca e formato em cada questão para o simulado poder filtrar.
- **Edital novo com conteúdo diferente.** Atualidades e Informática são os mais
  expostos. A árvore por tópico limita o retrabalho.
- **Pouca questão oficial de Vendas e Atualidades.** A cobertura depende de IA, que
  hoje não é confiável sem verificação.
- **Prazo.** Sem data de edital, a janela é de meses, não de semanas. Dá tempo de
  fazer a fase 1 bem feita antes de pensar em volume.

## Fontes

- Edital de Abertura, Seleção Externa 2022/001 (PDF oficial):
  https://www.bb.com.br/docs/portal/dipes/Edital-de-Abertura-de-Selecao-Externa-2022-01.pdf
- Página do concurso na banca: https://www.cesgranrio.org.br/concurso/banco-do-brasil-bb-01-2022/
- Situação em 2026: https://www.estrategiaconcursos.com.br/blog/concurso-banco-do-brasil-ultimas-noticias/
  e https://www.direcaoconcursos.com.br/noticias/concurso-banco-do-brasil-nao-tera-edital-em-2026
