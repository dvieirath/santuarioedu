# Preparatório Banco do Brasil — Escopo

Versão 2, 11/11/2026. Inclui as decisões do Davi, o que a fase 0 entregou e o
resultado da primeira importação de provas (fase 1).

## 1. Decisões tomadas (10/11/2026)

| Tema | Decisão |
|---|---|
| Cargos | Os dois: Agente Comercial e Agente de Tecnologia |
| Posição no produto | BB é uma trilha de aprendizado ao lado das outras. O site não fica exclusivo para BB |
| Banca de referência | A do último concurso (Cesgranrio), até sair o edital novo |
| Metas de conteúdo | As da seção 8, contando só questão verificada |
| Preço | Gratuito |
| Redação | Sem resposta ainda. Assumida na segunda fase |

## 2. Situação do concurso (consultado em 10/11/2026)

- Não há edital publicado nem data definida. O banco diz que não há previsão; a
  imprensa especializada e o sindicato falam em 2027.
- A banca não está confirmada. A Cesgranrio organizou os dois últimos (2021 e 2023).
- Último edital: Seleção Externa 2022/001, prova em 23/04/2023, 6.000 vagas de
  Escriturário (4.000 imediatas e 2.000 de cadastro de reserva).

A referência é o edital 2022/001. Tudo que depende dele está em um arquivo só,
`quiz/trilha_bb.py`. Quando o edital novo sair, atualiza-se esse arquivo e roda-se
o comando de seed.

## 3. A prova de referência (edital 2022/001, lido no PDF oficial)

Para os dois cargos: 70 questões de múltipla escolha, 5 alternativas, uma correta.
100 pontos. Objetiva e redação no mesmo dia, 5 horas no total.

Conhecimentos Básicos, igual para os dois cargos, 32,5 pontos:

| Disciplina | Questões | Valor | Pontos |
|---|---:|---:|---:|
| Língua Portuguesa | 10 | 1,5 | 15,0 |
| Língua Inglesa | 5 | 1,0 | 5,0 |
| Matemática | 5 | 1,5 | 7,5 |
| Atualidades do Mercado Financeiro | 5 | 1,0 | 5,0 |

Conhecimentos Específicos, 67,5 pontos:

| Cargo | Disciplina | Questões | Valor | Pontos |
|---|---|---:|---:|---:|
| Agente Comercial | Matemática Financeira | 5 | 1,5 | 7,5 |
| Agente Comercial | Conhecimentos Bancários | 10 | 1,5 | 15,0 |
| Agente Comercial | Conhecimentos de Informática | 15 | 1,5 | 22,5 |
| Agente Comercial | Vendas e Negociação | 15 | 1,5 | 22,5 |
| Agente de Tecnologia | Probabilidade e Estatística | 5 | 1,5 | 7,5 |
| Agente de Tecnologia | Conhecimentos Bancários | 5 | 1,5 | 7,5 |
| Agente de Tecnologia | Tecnologia da Informação | 35 | 1,5 | 52,5 |

Regras que mudam o desenho do produto:

- **Eliminação na objetiva (7.1.4 e 7.2.4):** menos de 50% do total, ou menos de
  50% em Conhecimentos Básicos, ou menos de 50% em Conhecimentos Específicos, ou
  nota zero em qualquer disciplina.
- **Redação (7.3):** dissertativo-argumentativa, 100 pontos, eliminatória, mínimo
  de 70. Só é corrigida para quem ficou dentro de 3 vezes a soma de vagas e
  cadastro de reserva da sua microrregião.
- **Classificação:** só pelos pontos da objetiva, por microrregião.
- **Agente de Tecnologia:** só existe na microrregião de TI, em Brasília.

O que isso significa:

1. No Agente Comercial, Informática e Vendas e Negociação somam 45 pontos.
2. No Agente de Tecnologia, uma disciplina sozinha vale 52,5 pontos.
3. Zero em qualquer disciplina elimina. Inglês e Atualidades valem 5 pontos cada,
   mas não podem ficar sem cobertura.
4. O formato é múltipla escolha de 5 alternativas. Questão de certo ou errado não
   serve para simulado BB.
5. A redação elimina.

## 4. O que o banco de questões já tem (SQLite local, 10/11/2026)

| Disciplina | Oficiais liberadas | Das quais múltipla escolha | IA liberadas |
|---|---:|---:|---:|
| Língua Portuguesa | 79 | 9 | 364 |
| Língua Inglesa | 12 | — | 0 |
| Matemática | 145 | 17 | 0 |
| Atualidades do Mercado Financeiro | 0 | 0 | 0 |
| Matemática Financeira | 0 | 0 | 0 |
| Conhecimentos Bancários | 0 | 0 | 0 |
| Conhecimentos de Informática | 94 | 16 | 206 |
| Vendas e Negociação | 0 | 0 | 0 |
| Probabilidade e Estatística | 2 | 0 | 0 |
| Tecnologia da Informação | 49 | 8 | 0 |

- Questões da Cesgranrio no banco: **zero**.
- Quase todo o acervo oficial é Cebraspe, de certo ou errado. No formato da prova
  do BB, o que existe hoje são dezenas de questões, não centenas.
- As IA liberadas não passaram por verificação de gabarito. Não contam.

O código da plataforma se aproveita quase inteiro. O conteúdo BB começa do zero.

### Depois da primeira importação (11/11/2026)

Provas BB 2021 e 2023, os dois cargos: 8 provas, 560 questões no total.
Entraram 492, todas **pendentes de revisão**; 68 ficaram retidas.

| Disciplina | Pendentes importadas | Meta de lançamento |
|---|---:|---:|
| Vendas e Negociação | 86 | 300 |
| Conhecimentos de Informática | 85 | 300 |
| Língua Portuguesa | 79 | 250 |
| Conhecimentos Bancários | 69 | 250 |
| Tecnologia da Informação | 43 | 400 |
| Língua Inglesa | 40 | 80 |
| Atualidades do Mercado Financeiro | 40 | 80 |
| Matemática | 24 | 120 |
| Matemática Financeira | 20 | 120 |
| Probabilidade e Estatística | 6 | 120 |

O que garante cada questão importada:

- lida do PDF oficial da banca, sem IA;
- gabarito oficial, o definitivo quando a banca publicou alteração;
- conferida na segunda versão do caderno: mesmo enunciado, mesmas alternativas
  e a mesma resposta, lida de outro PDF e de outra coluna do gabarito;
- cinco alternativas e exatamente uma correta.

O que a conferência automática **não** garante, e por isso tudo entrou pendente:
tabela que o PDF desenha de forma irregular, símbolo matemático fora do padrão e
erro que apareça igual nas duas versões do caderno. A revisão humana continua
sendo a porta de liberação.

Motivos das 68 retidas (uma questão pode ter mais de um):

| Motivo | Questões |
|---|---:|
| Fórmula com expoente ou índice | 15 |
| Cita figura, gráfico ou tabela | 14 |
| Texto solto ao redor (tabela, quadro de dados, código) | 12 pares |
| Figura na área da questão | 10 |
| Fala em destaque, mas o PDF não marca o trecho | 6 |
| Anulada no gabarito | 5 |
| Alternativa sem texto ou fora do padrão A a E | 7 |
| Não conferida na segunda versão | 5 |

O texto lido de cada retida está nos relatórios, para conferência manual:
`output/importacao_cesgranrio_BB_23_20261111_105214/relatorio.json` e
`output/importacao_cesgranrio_BB_21_20261111_105225/relatorio.json`.
Backup de antes da importação: `backups/antes_importacao_bb_20261111_104759.sqlite3`.

## 5. Escopo

### Dentro (primeira versão)

1. **Trilhas `bb` e `bb-ti`**, com as disciplinas e os tópicos do Anexo III.
2. **Banco de questões BB.** Múltipla escolha de 5 alternativas, cada questão
   ligada a um tópico do edital, com gabarito conferido e explicação.
3. **Simulado no formato da prova**, um por cargo: 70 questões na distribuição do
   edital, 5 horas, nota em pontos com os pesos, e o resultado dizendo se o aluno
   seria eliminado por alguma das quatro regras.
4. **Estudo por tópico** com revisão espaçada e caderno de erros. Já existe.
5. **Painel de preparação** por cargo. A base já existe em `/preparacao/<slug>/`.
6. **Páginas públicas** `/concurso/bb/` e `/concurso/bb-ti/`, e opção BB no
   cadastro do aluno.

### Segunda fase

7. **Redação.** Temas, os 5 critérios do edital e correção assistida.
8. **Questões inéditas por IA**, só com verificação de gabarito e, nos tópicos de
   norma, com o texto da norma no prompt.
9. **Material de teoria** por tópico. A geração já existe.

### Fora

- Videoaulas e correção humana de redação.
- Duelo e simulado coletivo como destaque da trilha.
- Promessa de aprovação. A linha do `PIVOT_ESTUDOS.md` continua valendo.
- Uso de marca: o material precisa dizer que não tem vínculo com o Banco do
  Brasil nem com a banca.

## 6. De onde vêm as questões

### Provas oficiais (primeiro)

Candidatas, a confirmar no site da Cesgranrio antes de baixar:

| Prova | Serve para |
|---|---|
| Banco do Brasil 2021 e 2023, os dois cargos | Todas as disciplinas, formato idêntico |
| Caixa, Técnico Bancário Novo 2021 e 2024 | Português, Matemática Financeira, Bancários, Informática, Atendimento |
| Banco da Amazônia e BNB, Cesgranrio | Português, Matemática, Bancários, Informática |
| Banco do Brasil 2010 a 2015 | Português, Matemática, Bancários; conferir vigência |
| Outras Cesgranrio de nível médio e de TI | Português, Matemática, Inglês, Informática, TI, Estatística |

Limite conhecido: Vendas e Negociação e Atualidades do Mercado Financeiro só
existem nesse formato desde 2021. A oferta de questão oficial é pequena e só dá
para medir depois de baixar.

### Regras de entrada (valem para oficial e IA)

- Questão só é liberada com tópico do edital, gabarito conferido com o gabarito
  oficial e enunciado completo.
- Se a classificação automática falhar, a questão fica pendente em
  "A classificar". **Feito na fase 0.**
- Questão anulada no gabarito definitivo não entra.
- IA só entra depois de uma segunda resolução às cegas concordar com o gabarito.
  Nos tópicos de norma, o texto da norma vai no prompt e a explicação cita o artigo.
- Geração para BB é sempre múltipla escolha, estilo Cesgranrio. **Feito na fase 0.**

## 7. O que muda no código

| Item | Onde | Situação |
|---|---|---|
| Especificação do edital (prova, pesos, tópicos, regras) | `quiz/trilha_bb.py` | Feito |
| Disciplinas das trilhas `bb` e `bb-ti` | `quiz/preparacao.py` | Feito |
| Comando que cria disciplinas e tópicos na árvore | `manage.py seed_trilha_bb` | Feito e aplicado ao banco local |
| Importador sem destino padrão em Direito Constitucional | `importar_pdf_questoes.py` | Feito |
| Categoria de espera "A classificar", bloqueada em toda aprovação | `quiz/categorias_pendentes.py` | Feito |
| Geração em massa só de múltipla escolha para BB | `gerar_bateria_multi_concurso.py` | Feito |
| Listas de categoria só com conteúdo (seletor de simulado, flashcards etc.) | `quiz/categorias.py` | Feito |
| Adaptador Cesgranrio no baixador | `scripts/baixar_provas_concursos/bancas/cesgranrio.py` | Feito |
| Leitor de caderno e gabarito da Cesgranrio, sem IA | `quiz/cesgranrio.py` | Feito |
| Importação com conferência entre versões do caderno | `manage.py importar_cesgranrio` | Feito |
| Texto de apoio compartilhado entre questões | modelo `TextoApoio`, migração 0059 | Feito |
| Destaque em negrito e enunciado sem HTML nas telas | filtro `enunciado` | Feito, exceto `resultado.html` |
| Classificação das questões por tópico do edital | hoje entram só na disciplina | Pendente |
| Opção BB no cadastro, com migração | `quiz/models.py` | Pendente, fase 2 |
| Páginas públicas | `quiz/concurso_landing.py` | Pendente, fase 2 |
| Simulado com pesos, pontos e regra de eliminação | `EDITAIS_OFICIAIS` só tem contagem hoje | Pendente, fase 2 |
| Demo com 3 questões BB | `quiz/demo_curadoria.json` | Pendente, fase 2 |
| Verificação de gabarito para IA | novo passo antes de aprovar | Pendente, fase 3 |
| Redação | módulo novo | Pendente, fase 4 |

Por que a opção BB no cadastro e as páginas públicas ficaram para a fase 2:
sem questões, o aluno escolheria BB e cairia em telas vazias.

Como repetir a importação para outra prova da Cesgranrio:

```
cd scripts/baixar_provas_concursos
python baixar_provas.py cesgranrio <slug-da-pagina> --pasta <PASTA> --conferencia 2
cd ../..
python manage.py importar_cesgranrio provas_pdf/materia_prima/<PASTA> --ano <ANO>
python manage.py importar_cesgranrio provas_pdf/materia_prima/<PASTA> --ano <ANO> --aplicar
```

Sem `--aplicar` o comando só simula e gera o relatório. A ligação entre disciplina
do gabarito e categoria vem de `quiz/trilha_bb.py`; prova de outro concurso com
disciplinas diferentes precisa ter as suas incluídas lá.

`resultado.html` ficou de fora do filtro de destaque porque tem alterações suas
ainda não commitadas. A troca é de uma linha e pode ir junto quando você commitar.

## 8. Meta de conteúdo

Só conta questão verificada. Lançamento é o mínimo para abrir a trilha; alvo é
onde ela deve chegar.

| Disciplina | Cargo | Pontos | Lançamento | Alvo |
|---|---|---:|---:|---:|
| Tecnologia da Informação | Tecnologia | 52,5 | 400 | 1000 |
| Conhecimentos de Informática | Comercial | 22,5 | 300 | 1000 |
| Vendas e Negociação | Comercial | 22,5 | 300 | 1000 |
| Conhecimentos Bancários | Os dois | 15,0 e 7,5 | 250 | 1000 |
| Língua Portuguesa | Os dois | 15,0 | 250 | 1000 |
| Matemática | Os dois | 7,5 | 120 | 600 |
| Matemática Financeira | Comercial | 7,5 | 120 | 600 |
| Probabilidade e Estatística | Tecnologia | 7,5 | 120 | 600 |
| Língua Inglesa | Os dois | 5,0 | 80 | 400 |
| Atualidades do Mercado Financeiro | Os dois | 5,0 | 80 | 400 |

A meta de lançamento permite cerca de 20 simulados completos sem repetir questão.
A divisão entre oficial e IA em cada disciplina só dá para fixar depois de medir
quantas questões oficiais existem.

## 9. Fases

| Fase | Entrega | Situação |
|---|---|---|
| 0 | Decisões; especificação do edital; trilhas `bb` e `bb-ti`; comando de seed; importador sem destino padrão | Concluída em 10/11/2026 |
| 1 | Listas de categoria só com conteúdo; seed aplicado; adaptador Cesgranrio; provas BB 2021 e 2023 importadas e conferidas; contagem real por disciplina | Concluída em 11/11/2026: 492 questões pendentes |
| 1b | Revisar e liberar as 492; tratar as 68 retidas; explicações | Depende de você |
| 2 | Demais provas bancárias; simulado no formato da prova; painel, páginas públicas e opção no cadastro | |
| 3 | IA com verificação para fechar os tópicos com pouca questão oficial; explicações | |
| 4 | Redação; beta fechado com poucos candidatos | |

A limpeza do acervo atual (rebaixar as IA sem verificação e reclassificar as
oficiais em categoria errada) corre em paralelo e não bloqueia a trilha.

## 10. Árvore de tópicos (Anexo III do edital 2022/001)

Os nomes abaixo são os do edital. Em `quiz/trilha_bb.py` cada item virou um
tópico de nome curto, com o número do item.

### Conhecimentos Básicos, os dois cargos

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

### Conhecimentos Bancários, os dois cargos

Sistema Financeiro Nacional: estrutura, órgãos normativos, supervisores,
executores e operadores. Mercado financeiro: monetário, de crédito, de capitais e
cambial. Moeda e política monetária, inclusive quantitative easing, Selic e
compromissadas, depósitos remunerados. Orçamento público, títulos do Tesouro e
dívida pública. Produtos bancários: cartões, CDC, crédito rural, poupança,
capitalização, previdência, consórcio, investimentos, seguros. Mercado de
capitais. Mercado de câmbio: instituições e operações básicas; regimes cambiais;
câmbio nominal e real; impactos sobre exportações e importações; diferencial de
juros, prêmio de risco e fluxo de capitais. Mercado interbancário. Mercado
bancário: tesouraria, varejo e recuperação de crédito. Juros de curto prazo e
curva de juros; nominais e reais. Garantias: aval, fiança, penhor mercantil,
alienação fiduciária, hipoteca, fianças bancárias. Lavagem de dinheiro: Lei
9.613/98, Circular 3.978/2020, Carta Circular 4.001/2020. Autorregulação bancária.
Sigilo bancário: LC 105/2001. LGPD: Lei 13.709/2018. Anticorrupção: Lei
12.846/2013 e Decreto 11.129/2022. Segurança cibernética: Resolução CMN
4.893/2021. Ética aplicada e Código de Ética do BB. Política de Responsabilidade
Socioambiental do BB.

### Só Agente Comercial

**Matemática Financeira.** Conceitos gerais: valor do dinheiro no tempo; capital,
juros, taxas; capitalização e regimes; fluxos de caixa; equivalência financeira.
Juros simples. Juros compostos. Sistemas de amortização: Price e SAC.

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

### Só Agente de Tecnologia

**Probabilidade e Estatística.** Representação tabular e gráfica. Medidas de
tendência central e de dispersão. Variáveis aleatórias e distribuição de
probabilidade. Teorema de Bayes. Probabilidade condicional. População e amostra.
Variância e covariância. Correlação linear simples. Distribuição binomial e
distribuição normal. Noções de amostragem e inferência estatística.

**Tecnologia da Informação.** Aprendizagem de máquina: fundamentos, algoritmos
supervisionados e não supervisionados, processamento de linguagem natural. Banco
de dados: NoSQL, MongoDB, SQL2008, SGBD, data warehouse, modelagem
entidade-relacionamento, modelo relacional e normalização, PostgreSQL. Big data:
fundamentos, preparação e apresentação de dados. Desenvolvimento mobile:
Java/Kotlin, Swift, React Native, Android e iOS. Estrutura de dados e algoritmos:
busca sequencial e binária, ordenação, lista encadeada, pilha, fila, árvore
binária. Ferramentas e linguagens: Ansible, Java, TypeScript, Python para IA e
analytics (Pandas, NumPy, SciPy, Matplotlib, Scikit-learn).

Versões de software e normas citadas são as de 2022. O edital novo deve trocar
várias; por isso o tópico é o nó da árvore, e a versão é um detalhe.

## 11. Riscos

- **Banca diferente da Cesgranrio.** Muda o estilo das questões. O banco guarda
  banca e formato em cada questão para o simulado poder filtrar.
- **Edital novo com conteúdo diferente.** Atualidades, Informática e Tecnologia da
  Informação são os mais expostos.
- **Pouca questão oficial** de Vendas, Atualidades e Tecnologia da Informação no
  formato da prova. A cobertura vai depender de IA, que hoje não é confiável sem
  verificação.
- **Árvore de categorias com duplicatas.** Existem "Português" e "Lingua
  Portuguesa", "Estatística" e "Estatística e Probabilidade", e nomes criados por
  engano. A trilha usa "Português" e "Estatística e Probabilidade". A unificação
  faz parte da limpeza do acervo.
- **Prazo.** Sem data de edital, a janela é de meses. Dá tempo de fazer a fase 1
  bem feita antes de pensar em volume.

## Fontes

- Edital de Abertura, Seleção Externa 2022/001 (PDF oficial):
  https://www.bb.com.br/docs/portal/dipes/Edital-de-Abertura-de-Selecao-Externa-2022-01.pdf
- Página do concurso na banca: https://www.cesgranrio.org.br/concurso/banco-do-brasil-bb-01-2022/
- Situação em 2026: https://www.estrategiaconcursos.com.br/blog/concurso-banco-do-brasil-ultimas-noticias/
  e https://www.direcaoconcursos.com.br/noticias/concurso-banco-do-brasil-nao-tera-edital-em-2026
