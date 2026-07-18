"""
Prompts para geração de justificativas — padrão SantuarioEdu.

Arquitetura própria: 6 blocos que priorizam DIAGNÓSTICO e ARMADILHAS
(linguagem alinhada com o posicionamento "estudos com IA").

Estrutura de saída (markdown, ordem específica):
  🔍 Por que a resposta é essa
  ⚠️ Armadilhas
  🧠 Conceito-chave
  🎯 O que esta questão testa
  📚 Onde aprofundar
  💡 Padrão a memorizar

Diferenciada de plataformas concorrentes:
- Ordem invertida (do específico ao geral)
- Terminologia "diagnóstico / armadilha / padrão" (IA-flavored)
- Ícones + emojis próprios
"""


TEMPLATE_ME = """Você é um especialista em análise de questões objetivas.
Sua função é escrever a análise de uma questão de múltipla escolha no formato SantuarioEdu.

CATEGORIA: {categoria}
BANCA: {banca}

ENUNCIADO:
{enunciado}

ALTERNATIVAS:
{alternativas}

GABARITO: alternativa {letra_correta}

═══════════════════════════════════════════════════════════
FORMATO DE SAÍDA — retorne SOMENTE este JSON válido:

{{
  "assunto": "tópico curto (máx 80 chars)",
  "justificativa": "TEXTO MARKDOWN abaixo com os 6 blocos NESSA ORDEM EXATA"
}}

O campo "justificativa" deve conter EXATAMENTE esta estrutura em markdown:

## 🔍 Por que a resposta é essa
Explique de forma direta e didática por que a alternativa {letra_correta} está correta.
Aponte a regra, princípio ou fato específico que a torna verdadeira.
Máximo 4 frases. Vá direto ao ponto.

## ⚠️ Armadilhas
Analise CADA alternativa incorreta individualmente:
- **A)** [se A não for a correta] Qual conceito ela confunde. Que "quase-verdade" contém.
- **B)** [se B não for a correta] Idem.
- **C)** [se C não for a correta] Idem.
- **D)** [se D não for a correta] Idem.
- **E)** [se E não for a correta] Idem.

Nunca liste a correta aqui. Não copie o texto das alternativas — só explique o erro.

## 🧠 Conceito-chave
Explique de forma compacta a teoria ou regra envolvida.
Se houver múltiplas facetas, use lista com "- " (máx 4 itens).
Foco: contexto que ajuda a acertar outras questões parecidas.

## 🎯 O que esta questão testa
1-2 frases descrevendo qual skill/conhecimento essa questão avalia.
Ex: "capacidade de distinguir X de Y" ou "aplicação da lei Z ao caso concreto".

## 📚 Onde aprofundar
Uma referência prática pra estudar mais o tema.
Ex: "Manual de Direito Administrativo, Matheus Carvalho, cap. 5"
ou "Lei 8.112/90, arts. 116-142"
ou "Doutrina majoritária + súmula X do STJ"
Se não houver referência óbvia, sugira o tema geral ("estude o capítulo de teoria da constituição").

## 💡 Padrão a memorizar
1-2 frases com uma regrinha, mnemônico ou palavra-gatilho.
Ex: "Quando aparecer 'sempre', 'nunca' ou 'apenas', desconfie."
Ou: "Prazo prescricional da Fazenda Pública = 5 anos (Lei 9.784, art. 54)."

═══════════════════════════════════════════════════════════
REGRAS:
- Português brasileiro claro e direto.
- Sem emojis além dos títulos (🔍 ⚠️ 🧠 🎯 📚 💡).
- Zero markdown code fences (```).
- JSON válido — escape aspas internas com \\".
- NÃO adicione blocos além dos 6 acima.
"""


TEMPLATE_CE = """Você é um especialista em análise de questões objetivas.
Análise de uma proposição CERTO/ERRADO no formato SantuarioEdu.

CATEGORIA: {categoria}
BANCA: {banca}

PROPOSIÇÃO:
{enunciado}

GABARITO: {status_texto}

═══════════════════════════════════════════════════════════
FORMATO DE SAÍDA — SOMENTE JSON:

{{
  "assunto": "tópico curto",
  "justificativa": "TEXTO MARKDOWN com os 5 blocos NESSA ORDEM"
}}

Estrutura EXATA em markdown:

## 🔍 Por que a resposta é {status_texto}
Explique DIRETAMENTE por que a proposição está {status_texto}.
Aponte a palavra, expressão ou conceito que decide o gabarito.
Máximo 4 frases.

## ⚠️ O erro típico
Que armadilha essa proposição arma? Que "quase-verdade" ela apresenta?
Onde um candidato desatento cai?

## 🧠 Conceito-chave
Explique a teoria ou norma envolvida de forma compacta.
Use listas com "- " quando houver múltiplos elementos.

## 📚 Onde aprofundar
Referência bibliográfica ou legal (autor + obra, ou lei + artigo).

## 💡 Padrão a memorizar
1-2 frases com regrinha, palavra-gatilho ou mnemônico.

═══════════════════════════════════════════════════════════
REGRAS:
- Português claro.
- Sem code fences.
- Emojis SÓ nos títulos.
"""


def montar_prompt_me(categoria: str, banca: str, enunciado: str,
                     alternativas: list, letra_correta: str) -> str:
    letras = ['A', 'B', 'C', 'D', 'E', 'F']
    linhas = []
    for i, a in enumerate(alternativas):
        letra = letras[i] if i < len(letras) else '?'
        marca = ' ← CORRETA' if a.correta else ''
        linhas.append(f'{letra}) {a.texto[:400]}{marca}')

    return TEMPLATE_ME.format(
        categoria=categoria,
        banca=banca or 'Genérica',
        enunciado=enunciado[:2500],
        alternativas='\n'.join(linhas),
        letra_correta=letra_correta,
    )


def montar_prompt_ce(categoria: str, banca: str, enunciado: str,
                     alternativa_correta) -> str:
    texto_correta = (alternativa_correta.texto or '').strip().lower()
    status = 'CERTO' if texto_correta.startswith('c') else 'ERRADO'

    return TEMPLATE_CE.format(
        categoria=categoria,
        banca=banca or 'Genérica',
        enunciado=enunciado[:2500],
        status_texto=status,
    )


def montar_prompt(questao) -> str:
    """API unificada — escolhe ME ou CE automaticamente."""
    alts = list(questao.alternativa_set.all())
    correta = next((a for a in alts if a.correta), None)
    if not correta:
        raise ValueError('Questão sem alternativa correta marcada')

    if questao.tipo == 'CE':
        return montar_prompt_ce(
            categoria=questao.categoria.nome,
            banca=questao.banca or '',
            enunciado=questao.texto,
            alternativa_correta=correta,
        )

    letras = ['A', 'B', 'C', 'D', 'E', 'F']
    letra_correta = '?'
    for i, a in enumerate(alts):
        if a.correta and i < len(letras):
            letra_correta = letras[i]
            break

    return montar_prompt_me(
        categoria=questao.categoria.nome,
        banca=questao.banca or '',
        enunciado=questao.texto,
        alternativas=alts,
        letra_correta=letra_correta,
    )
