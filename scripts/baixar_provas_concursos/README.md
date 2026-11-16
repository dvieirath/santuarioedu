# Baixador de provas e gabaritos

Baixa provas e gabaritos oficiais (gratuitos e publicos) de concursos e salva,
para cada prova, um PDF unico (prova + gabarito mesclados) com nome legivel.

## Instalar

```bash
cd scripts/baixar_provas_concursos
pip install -r requirements.txt
```

## Usar

### 1. Cebraspe (Cespe) — suporte completo e automatico

Achar o identificador ("slug") do concurso pelo nome:

```bash
python baixar_provas.py buscar PRF
```

Baixar e mesclar tudo de um concurso (o slug vem da busca acima, ou da URL
`cebraspe.org.br/concursos/<slug>`):

```bash
python baixar_provas.py cebraspe PRF_21
```

Varios concursos de uma vez, com pasta de destino customizada:

```bash
python baixar_provas.py cebraspe PRF_21 PF_25 --saida "D:\provas"
```

Por padrao os arquivos vao para `~/Downloads/provas_concursos/<slug>/`, um
PDF mesclado por prova (`_baixados/` dentro da mesma pasta guarda os PDFs
originais, sem mesclar, para nao baixar de novo se voce rodar outra vez).

### 2. Cesgranrio — caderno, segunda versão para conferência e gabaritos

O slug é o trecho final da URL `cesgranrio.org.br/concurso/<slug>/`:

```bash
python baixar_provas.py cesgranrio banco-do-brasil-bb-01-2022 --pasta BB_23 --conferencia 2
```

Os arquivos vão para `provas_pdf/materia_prima/<pasta>/`, sem mesclar, com um
`manifesto_cesgranrio.json`. Na página da banca, "GABARITO 1" a "GABARITO 5" são
as versões do caderno de questões; o adaptador baixa a versão 1 e, com
`--conferencia 2`, também a 2. Baixa o gabarito preliminar e o alterado depois
dos recursos, quando existe.

A importação é feita pelo comando Django, que lê os PDFs sem IA e só aceita a
questão cuja resposta bate nas duas versões do caderno:

```bash
python manage.py importar_cesgranrio provas_pdf/materia_prima/BB_23 --ano 2023
python manage.py importar_cesgranrio provas_pdf/materia_prima/BB_23 --ano 2023 --aplicar
```

### 3. Outras bancas (FGV, FCC, Vunesp, IBFC, AOCP, ...) — melhor esforço

Não existe um adaptador dedicado para cada banca — cada site organiza a
lista de provas/gabaritos de um jeito diferente. O modo genérico abre a URL
que você passar e procura links de PDF cujo texto pareça de prova ou
gabarito:

```bash
python baixar_provas.py generico "https://www.exemplo.com.br/concursos/xyz/provas" --nome "TRT SP 2024"
```

Se a página da banca carrega a lista de provas via JavaScript (em vez de já
vir pronta no HTML), o modo genérico não vai encontrar nada — nesse caso é
preciso escrever um adaptador específico (veja `bancas/cebraspe.py` como
exemplo: ele usa a API JSON que o site do Cebraspe usa internamente, em vez
de tentar ler o HTML renderizado).

## Como o pareamento prova/gabarito funciona

O script classifica cada link pelo título (contém "PROVA", "GABARITO",
"PADRÃO DE RESPOSTA" etc.) e depois casa cada prova com o gabarito de título
mais parecido (ex.: "PROVA OBJETIVA — ITENS DE 9 A 120" com "GABARITO
DEFINITIVO — ITENS DE 9 A 120"). Quando existe gabarito preliminar e
definitivo para a mesma prova, o definitivo é preferido. Provas sem gabarito
correspondente ainda são salvas (sozinhas, com o sufixo `SEM_GABARITO`).

## Aviso

O script só baixa material que a própria banca publica gratuitamente para o
público (provas e gabaritos oficiais). Ele identifica User-Agent como
`SantuarioEdu-BaixadorDeProvas` e faz uma pequena pausa entre downloads para
não sobrecarregar o servidor.
