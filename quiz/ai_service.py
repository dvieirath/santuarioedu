"""
Camada de serviços de IA do app.

A partir desta versão, **todas as chamadas de IA** passam pelo `ai_provider`,
que tenta Groq primeiro e cai pro Gemini se a quota acabar.

A classe _RespCompat existe pra manter compatibilidade com o código antigo
que esperava um objeto com `.text` (estilo SDK Google).
"""
from django.conf import settings
import logging
import json

from .ai_provider import gerar_conteudo, AIError

logger = logging.getLogger(__name__)


class _RespCompat:
    """Mimica `response` do SDK Gemini (atributo .text)."""
    def __init__(self, text):
        self.text = text or ''


def _call_ia(prompt, **kwargs):
    """Wrapper que devolve objeto com .text — compatível com o código antigo."""
    try:
        return _RespCompat(gerar_conteudo(prompt, **kwargs))
    except AIError as e:
        logger.error(f'IA falhou em todos os providers: {e}')
        return _RespCompat('')


def _contexto_concurso(usuario=None) -> str:
    """
    Retorna string curta identificando o alvo do usuário para injeção em prompts.

    - Se o usuário tiver ConcursoPreferido cadastrado: usa a label do concurso
      (ex.: "PRF — Polícia Rodoviária Federal", "INSS — Técnico do Seguro Social").
    - Senão: retorna string genérica de concursos públicos brasileiros.

    Usar em prompts:
        contexto = _contexto_concurso(request.user)
        prompt = f"Você é especialista em {contexto}..."
    """
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return 'concursos públicos brasileiros'
    try:
        from .models import ConcursoPreferido
        pref = ConcursoPreferido.objects.filter(usuario=usuario).first()
        if pref:
            return pref.get_concurso_display()
    except Exception:
        pass
    return 'concursos públicos brasileiros'

def gerar_justificativa_ia(questao):
    """
    Gera uma justificativa e identifica o assunto para a questão usando a API do Google Gemini.
    Retorna um dicionário {'justificativa': str, 'assunto': str} ou None se falhar.
    """
    api_key = getattr(settings, 'GROQ_API_KEY', '') or getattr(settings, 'GEMINI_API_KEY', '')
    
    if not api_key:
        logger.warning("Nenhum provider de IA configurado (GROQ_API_KEY ou GEMINI_API_KEY).")
        return None

    try:
        # Construir o prompt dependendo do tipo de questão
        if questao.tipo == 'CE':
            correta = questao.alternativa_set.filter(correta=True).first()
            gabarito = correta.texto if correta else "Desconhecido"
            
            prompt = f"""
            Atue como um professor especialista em concursos públicos brasileiros.
            Analise a seguinte questão e forneça:
            1. O Assunto específico cobrado (ex: Crase, Concordância, Leis de Newton, Atos Administrativos). Seja breve, máximo 5 palavras.
            2. Uma explicação didática e direta por que a afirmação está {gabarito}.

            Questão ({questao.categoria}): "{questao.texto}"
            Gabarito: {gabarito}
            
            Responda EXATAMENTE no seguinte formato JSON:
            {{
                "assunto": "Assunto aqui",
                "justificativa": "Explicação aqui"
            }}
            """
        else:
            correta = questao.alternativa_set.filter(correta=True).first()
            gabarito = correta.texto if correta else "Desconhecido"
            
            prompt = f"""
            Atue como um professor especialista em concursos públicos brasileiros.
            Analise a seguinte questão e forneça:
            1. O Assunto específico cobrado.
            2. Uma explicação de qual é a alternativa correta e por que.
            
            Questão ({questao.categoria}): "{questao.texto}"
            Alternativa Correta: {gabarito}
            
            Responda EXATAMENTE no seguinte formato JSON:
            {{
                "assunto": "Assunto aqui",
                "justificativa": "Explicação aqui"
            }}
            """

        response = _call_ia(prompt)
        
        # Tentar fazer o parse do JSON (o Gemini as vezes coloca markdown ```json ... ```)
        texto_resposta = response.text.strip()
        if texto_resposta.startswith("```json"):
            texto_resposta = texto_resposta[7:]
        if texto_resposta.startswith("```"):
            texto_resposta = texto_resposta[3:]
        if texto_resposta.endswith("```"):
            texto_resposta = texto_resposta[:-3]
            
        try:
            resultado = json.loads(texto_resposta)
            return resultado
        except json.JSONDecodeError:
            # Fallback se não vier JSON válido
            return {
                "assunto": "Geral",
                "justificativa": response.text
            }

    except Exception as e:
        logger.error(f"Erro na API Gemini: {e}")
        return None


def ai_extrair_questoes(texto_bruto):
    """
    Usa o Google Gemini para extrair questões estruturadas a partir de texto copiado
    de um PDF ou edital. Retorna uma lista de dicts prontos para importação.

    Cada dict tem:
        categoria, texto, tipo ('ME' ou 'CE'), banca, ano,
        alternativas: [{'letra': 'a'...'e', 'texto': ..., 'correta': bool}],
        justificativa (pode ser '')
    Retorna [] em caso de falha.
    """
    api_key = getattr(settings, 'GROQ_API_KEY', '') or getattr(settings, 'GEMINI_API_KEY', '')
    if not api_key:
        logger.warning("Nenhum provider de IA configurado (GROQ_API_KEY ou GEMINI_API_KEY).")
        return []

    try:
        prompt = f"""
Você é um especialista em concursos públicos brasileiros.
Extraia TODAS as questões do texto abaixo e retorne um JSON válido.

Regras:
- Para questões de múltipla escolha (A, B, C, D, E) use tipo "ME".
- Para questões Certo/Errado use tipo "CE" com duas alternativas: "Certo" (letra a) e "Errado" (letra b).
- Identifique a categoria/disciplina (ex: Legislação de Trânsito, Português, Matemática, Direito Penal).
- Se houver gabarito no texto, use-o para marcar a alternativa correta; caso contrário, marque correta=false em todas.
- Se houver banca (CESPE, FCC, VUNESP etc.) identifique-a; caso contrário use "".
- Se houver ano identifique-o (número inteiro); caso contrário use null.

Retorne APENAS um JSON no formato abaixo, sem markdown, sem texto extra:
{{
  "questoes": [
    {{
      "categoria": "Nome da categoria",
      "texto": "Enunciado completo da questão",
      "tipo": "ME",
      "banca": "CESPE",
      "ano": 2023,
      "justificativa": "",
      "alternativas": [
        {{"letra": "a", "texto": "Texto da alternativa A", "correta": false}},
        {{"letra": "b", "texto": "Texto da alternativa B", "correta": true}},
        {{"letra": "c", "texto": "Texto da alternativa C", "correta": false}},
        {{"letra": "d", "texto": "Texto da alternativa D", "correta": false}}
      ]
    }}
  ]
}}

TEXTO A PROCESSAR:
---
{texto_bruto[:8000]}
---
"""

        response = _call_ia(prompt)
        texto_resp = response.text.strip()

        # Remove possível markdown
        if texto_resp.startswith("```json"):
            texto_resp = texto_resp[7:]
        elif texto_resp.startswith("```"):
            texto_resp = texto_resp[3:]
        if texto_resp.endswith("```"):
            texto_resp = texto_resp[:-3]

        data = json.loads(texto_resp.strip())
        questoes = data.get('questoes', [])
        logger.info(f"ai_extrair_questoes: extraídas {len(questoes)} questões")
        return questoes

    except json.JSONDecodeError as e:
        logger.error(f"ai_extrair_questoes JSON decode error: {e}")
        return []
    except Exception as e:
        logger.error(f"ai_extrair_questoes error: {e}")
        return []


# ─── SPRINT 11A — TUTOR IA ───────────────────────────────────────────────────

def ai_resumo_disciplina(nome_disciplina: str, usuario=None) -> str:
    """
    Gera um resumo estruturado de uma disciplina para concursos públicos.
    Se o usuário tiver ConcursoPreferido, adapta o foco.
    Retorna texto Markdown com conceitos-chave, macetes e tópicos mais cobrados.
    """
    api_key = getattr(settings, 'GROQ_API_KEY', '') or getattr(settings, 'GEMINI_API_KEY', '')
    if not api_key:
        return "⚠️ Resumo IA indisponível: configure GROQ_API_KEY ou GEMINI_API_KEY no .env."

    contexto = _contexto_concurso(usuario)
    try:
        prompt = f"""Você é um professor especialista em {contexto}.

Crie um resumo didático e completo sobre "{nome_disciplina}" para quem está se preparando para {contexto}.

O resumo deve conter:
1. **Visão Geral** — descrição resumida da matéria e sua importância no edital
2. **Conceitos Fundamentais** — os 5-8 conceitos mais importantes, explicados de forma clara
3. **Tópicos Mais Cobrados** — lista dos assuntos que aparecem com mais frequência em provas de concursos públicos
4. **Macetes e Dicas** — truques para memorizar e resolver questões rapidamente
5. **Pontos de Atenção** — erros comuns e pegadinhas que aparecem nas provas

Use formatação Markdown com títulos (##), listas (- item), negrito (**termo**) e destaques.
Seja objetivo, mas completo. Máximo de 600 palavras."""

        response = _call_ia(prompt)
        return response.text.strip()

    except Exception as e:
        logger.error(f"ai_resumo_disciplina error: {e}")
        return f"⚠️ Não foi possível gerar o resumo: {e}"


def ai_tutor_responder(pergunta: str, contexto_questao: str = '', usuario=None) -> str:
    """
    Responde uma dúvida do aluno sobre matéria de concursos públicos.
    Opcionalmente recebe o texto de uma questão como contexto.
    Retorna string com a resposta.
    """
    api_key = getattr(settings, 'GROQ_API_KEY', '') or getattr(settings, 'GEMINI_API_KEY', '')
    if not api_key:
        return "⚠️ Tutor IA indisponível: chave GEMINI_API_KEY não configurada."

    contexto = _contexto_concurso(usuario)
    try:
        system_ctx = (
            f"Você é o Tutor IA do SantuarioEdu, um assistente especialista em {contexto}. "
            "Responda de forma didática, objetiva e em português. "
            "Use exemplos práticos quando pertinente. "
            "Limite a resposta a no máximo 4 parágrafos."
        )

        if contexto_questao:
            prompt = (
                f"{system_ctx}\n\n"
                f"QUESTÃO DE CONTEXTO:\n{contexto_questao}\n\n"
                f"DÚVIDA DO ALUNO: {pergunta}"
            )
        else:
            prompt = f"{system_ctx}\n\nDÚVIDA DO ALUNO: {pergunta}"

        response = _call_ia(prompt)
        return response.text.strip()

    except Exception as e:
        logger.error(f"ai_tutor_responder error: {e}")
        return f"⚠️ Não foi possível obter resposta do Tutor IA: {e}"


# ─── SPRINT 15C — PLANO DE ESTUDOS IA ────────────────────────────────────────

def ai_plano_estudos(dados_usuario: dict, usuario=None) -> str:
    """
    Gera um plano de estudos semanal personalizado para o concurso do usuário.
    Se o usuário tiver ConcursoPreferido, o plano é ajustado ao concurso alvo.

    dados_usuario:
        - horas_dia: int (horas disponíveis por dia)
        - dias_por_semana: int
        - data_prova: str (ex: '2025-09-15') ou ''
        - pontos_fracos: list[str] (nomes das disciplinas)
        - pontos_fortes: list[str]
        - total_respondidas: int
        - aproveitamento_geral: int (%)

    Retorna Markdown formatado com o cronograma.
    """
    api_key = getattr(settings, 'GROQ_API_KEY', '') or getattr(settings, 'GEMINI_API_KEY', '')
    if not api_key:
        return "⚠️ Plano IA indisponível: GEMINI_API_KEY não configurada."

    try:
        fracos  = ', '.join(dados_usuario.get('pontos_fracos', [])[:5]) or 'não identificado'
        fortes  = ', '.join(dados_usuario.get('pontos_fortes', [])[:3]) or 'não identificado'
        horas   = dados_usuario.get('horas_dia', 2)
        dias    = dados_usuario.get('dias_por_semana', 5)
        prova   = dados_usuario.get('data_prova', '')
        total_q = dados_usuario.get('total_respondidas', 0)
        aprov   = dados_usuario.get('aproveitamento_geral', 0)

        prazo_txt = f"Data da prova: {prova}." if prova else "Data da prova não informada."
        contexto = _contexto_concurso(usuario)

        prompt = f"""Você é um coach especialista em preparação para {contexto}.

Crie um **plano de estudos semanal personalizado** com base nos dados abaixo.

DADOS DO CANDIDATO:
- Concurso alvo: {contexto}
- Horas disponíveis por dia: {horas}h
- Dias de estudo por semana: {dias}
- {prazo_txt}
- Questões respondidas até agora: {total_q}
- Aproveitamento geral: {aprov}%
- Disciplinas mais fracas: {fracos}
- Disciplinas mais fortes: {fortes}

INSTRUÇÕES:
1. Distribua as horas de estudo pelos dias da semana (Segunda a Domingo)
2. Dedique mais tempo às disciplinas fracas
3. Reserve 1 sessão semanal para simulado ou revisão geral
4. Inclua estratégias específicas para cada disciplina fraca
5. Dê metas semanais de questões a resolver por disciplina
6. Formate o plano em Markdown com tabela para os dias da semana

O plano deve ter:
- **Resumo da estratégia** (2-3 linhas)
- **Tabela semanal** (dia | disciplina | duração | objetivo)
- **Metas da semana** (questões por disciplina)
- **Dica de ouro** (1 insight personalizado)

Seja direto, prático e motivador. Máximo 500 palavras."""

        response = _call_ia(prompt)
        return response.text.strip()

    except Exception as e:
        logger.error(f"ai_plano_estudos error: {e}")
        return f"⚠️ Não foi possível gerar o plano: {e}"


# ─── SPRINT 20 — TUTOR IA PERSONALIZADO ──────────────────────────────────────

def ai_explicar_erro(questao_texto: str, categoria: str,
                     alt_escolhida: str, alt_correta: str,
                     rank_usuario: str = 'Cadete', usuario=None) -> str:
    """
    Explica didaticamente por que o aluno errou a questão.
    Linguagem adaptada ao rank/nível do usuário.
    Inclui analogia e dica de fixação.
    """
    api_key = getattr(settings, 'GROQ_API_KEY', '') or getattr(settings, 'GEMINI_API_KEY', '')
    if not api_key:
        return "⚠️ Tutor IA indisponível: GEMINI_API_KEY não configurada."

    # Ranks são apenas rótulos internos do sistema de XP — mapeiam a nível de
    # profundidade da explicação, não a nenhum concurso específico.
    NIVEIS = {
        'Cadete':          'iniciante — use linguagem simples e explique termos técnicos',
        'Aspirante':       'intermediário — assuma conhecimento básico, aprofunde conceitos',
        'Inspetor':        'avançado — seja técnico, cite fundamentos legais quando relevante',
        'Delegado':        'expert — vá direto ao ponto com precisão técnica',
        'Superintendente': 'expert — máxima precisão, sem rodeios',
        'Diretor':         'expert — máxima precisão, sem rodeios',
        'Diretor PRF':     'expert — máxima precisão, sem rodeios',  # backwards-compat
    }
    nivel = NIVEIS.get(rank_usuario, NIVEIS['Cadete'])
    contexto = _contexto_concurso(usuario)

    try:
        prompt = f"""Você é o Tutor IA do SantuarioEdu — coach especialista em {contexto}.

O aluno (perfil: {nivel}) errou esta questão:

📚 **Disciplina:** {categoria}
❓ **Questão:** {questao_texto}
❌ **Alternativa escolhida:** {alt_escolhida}
✅ **Alternativa correta:** {alt_correta}

Explique com as seguintes seções (use Markdown):

**Por que está errado**
Identifique o raciocínio equivocado por trás da escolha do aluno. Seja empático.

**Por que está certo**
Fundamente a alternativa correta de forma clara e objetiva.

**Analogia prática**
Uma comparação do cotidiano ou exemplo concreto que fixe o conceito.

**Dica para não errar de novo**
Uma frase curta e memorável (máx. 20 palavras).

Seja motivador, objetivo e use no máximo 200 palavras no total."""

        resp = _call_ia(prompt)
        return resp.text.strip()

    except Exception as e:
        logger.error(f"ai_explicar_erro error: {e}")
        return f"⚠️ Não foi possível gerar a explicação: {e}"


# ── Sprint 21 — Análise Preditiva de Banca ────────────────────────────────────

def ai_insight_banca(banca: str, total: int, pct: int,
                     pior_cat: str, melhor_cat: str, usuario=None) -> str:
    """Gera um parágrafo de insight tático sobre o desempenho do usuário
    em uma banca específica de concurso público."""
    contexto = _contexto_concurso(usuario)
    prompt = f"""Você é um coach especialista em preparação para {contexto}.

Dados do candidato sobre a banca **{banca}**:
- Questões respondidas: {total}
- Aproveitamento: {pct}%
- Disciplina mais fraca: {pior_cat or 'não identificada'}
- Disciplina mais forte: {melhor_cat or 'não identificada'}

Escreva exatamente 3 parágrafos curtos em Markdown:

**Diagnóstico**
Uma frase direta sobre o nível atual nessa banca.

**Estratégia**
Uma dica tática específica e acionável para melhorar nas próximas semanas.

**Padrão da banca**
Uma observação sobre o estilo de cobranças típico da banca {banca} em concursos públicos.

Seja direto, objetivo e motivador. Máximo 120 palavras no total."""

    try:
        resp = _call_ia(prompt)
        return resp.text.strip()
    except Exception as e:
        logger.error(f"ai_insight_banca error: {e}")
        return f"⚠️ Não foi possível gerar o insight: {e}"


# ── Sprint 22 — Simulado Preditivo ───────────────────────────────────────────

def ai_analisar_simulado(
    aproveitamento: int,
    total_questoes: int,
    cats_stats: list,        # [{'nome': str, 'pct': int, 'total': int}, ...]
    historico_pct: list,     # últimos N aproveitamentos de simulados anteriores
    rank_usuario: str = 'Cadete',
    usuario=None,
) -> dict:
    """Analisa o resultado de um simulado completo e retorna:
      - 'nota_predita': float (0-100) estimada para prova real
      - 'texto': Markdown com análise tática personalizada
    """
    # Calcula nota predita com tendência ponderada
    if historico_pct:
        # Média ponderada: simulado atual (peso 3) + histórico recente (peso 1 cada)
        pesos   = [3] + [1] * len(historico_pct)
        valores = [aproveitamento] + list(historico_pct)
        nota_predita = round(sum(p * v for p, v in zip(pesos, valores)) / sum(pesos), 1)
    else:
        nota_predita = float(aproveitamento)

    # Aplica pequeno fator de conservadorismo (-3%) para refletir pressão real de prova
    nota_predita = max(0.0, min(100.0, nota_predita - 3))

    cats_texto = '\n'.join(
        f"  - {c['nome']}: {c['pct']}% ({c['total']} questões)"
        for c in sorted(cats_stats, key=lambda x: x['pct'])
    ) if cats_stats else '  - Sem dados por disciplina'

    historico_texto = (
        ', '.join(f"{p}%" for p in historico_pct[-5:]) + ' (mais recente →)'
        if historico_pct else 'Primeiro simulado'
    )

    contexto = _contexto_concurso(usuario)
    prompt = f"""Você é um coach especialista em preparação para {contexto}.

Dados do candidato (nível: {rank_usuario}):
- Concurso alvo: {contexto}
- Aproveitamento neste simulado: {aproveitamento}% ({total_questoes} questões)
- Nota predita para a prova real: {nota_predita:.0f}%
- Histórico de simulados anteriores: {historico_texto}

Desempenho por disciplina (do pior para o melhor):
{cats_texto}

Escreva uma análise em Markdown com exatamente 4 seções:

## 📊 Resultado Geral
2 frases sobre o aproveitamento atual e se está acima/abaixo da meta típica (70% é o benchmark comum em concursos brasileiros).

## 🎯 Nota Predita: {nota_predita:.0f}%
1 frase explicando o que essa nota significa para as chances de aprovação.

## 🔴 Pontos Críticos
Liste até 3 disciplinas fracas (abaixo de 60%) com uma dica específica para cada uma.
Se não houver, diga que o candidato está bem distribuído.

## ✅ Plano dos Próximos 7 Dias
3 ações concretas e específicas para melhorar antes do próximo simulado.

Seja direto, motivador e use linguagem de coach. Máximo 200 palavras."""

    try:
        resp = _call_ia(prompt)
        return {'nota_predita': nota_predita, 'texto': resp.text.strip()}
    except Exception as e:
        logger.error(f"ai_analisar_simulado error: {e}")
        return {
            'nota_predita': nota_predita,
            'texto': f"⚠️ Análise indisponível no momento: {e}",
        }


# ── Sprint 23 — Geração de Questões IA + Predição de Tópicos ─────────────────

def ai_gerar_questoes(categoria: str, quantidade: int = 5,
                      dificuldade: str = 'media',
                      assunto: str = '', usuario=None) -> list:
    """Gera questões originais de múltipla escolha para concursos públicos.
    Retorna lista de dicts no mesmo formato que ai_extrair_questoes()."""
    dif_map = {
        'facil':  'nível fácil, voltadas a candidatos iniciantes',
        'media':  'nível médio, similares a provas reais de concursos brasileiros',
        'dificil':'nível difícil, com pegadinhas e detalhes técnicos de prova',
    }
    dif_texto = dif_map.get(dificuldade, dif_map['media'])
    assunto_txt = f' com foco no assunto: **{assunto}**' if assunto else ''
    contexto = _contexto_concurso(usuario)

    prompt = f"""Você é um elaborador de questões especialista em {contexto}.

Crie exatamente {quantidade} questões de múltipla escolha (4 alternativas cada) de **{categoria}**{assunto_txt}, em {dif_texto}.

Requisitos:
- Cada questão deve ter exatamente 4 alternativas (a, b, c, d)
- Exatamente 1 alternativa correta por questão
- Enunciados realistas e alinhados com o padrão de {contexto}
- Inclua justificativa explicando por que a resposta correta está certa
- Não repita enunciados

Retorne APENAS um JSON válido, sem markdown, sem texto extra:
{{
  "questoes": [
    {{
      "texto": "Enunciado completo da questão",
      "justificativa": "Explicação detalhada da resposta correta",
      "assunto": "{assunto or categoria}",
      "alternativas": [
        {{"letra": "a", "texto": "Texto da alternativa A", "correta": false}},
        {{"letra": "b", "texto": "Texto da alternativa B", "correta": true}},
        {{"letra": "c", "texto": "Texto da alternativa C", "correta": false}},
        {{"letra": "d", "texto": "Texto da alternativa D", "correta": false}}
      ]
    }}
  ]
}}"""

    try:
        resp = _call_ia(prompt)
        raw    = resp.text.strip()
        # Remove markdown code fences if present
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        import json as _json
        data = _json.loads(raw)
        questoes = data.get('questoes', [])
        # Normalise: add categoria and tipo
        for q in questoes:
            q['categoria'] = categoria
            q['tipo']      = 'ME'
            q['banca']     = 'IA'
            q['ano']       = None
        return questoes
    except Exception as e:
        logger.error(f"ai_gerar_questoes error: {e}")
        return []


def ai_prever_topicos(cats_stats: list, usuario=None) -> list:
    """Recebe lista de {nome, total, pct, ultima_resposta_dias}
    e retorna lista de {categoria, probabilidade, justificativa}
    ordenada por probabilidade descendente."""

    cats_texto = '\n'.join(
        f"  - {c['nome']}: {c['total']} questões respondidas, {c['pct']}% acertos, "
        f"última prática há {c['dias']} dia(s)"
        for c in cats_stats
    ) if cats_stats else '  - Sem histórico disponível'

    contexto = _contexto_concurso(usuario)
    prompt = f"""Você é um especialista em análise de editais e histórico de provas de {contexto}.

Histórico de estudo do candidato:
{cats_texto}

Com base nos padrões históricos de {contexto} e no histórico acima, estime a probabilidade (0-100%) de cada disciplina aparecer com peso significativo na próxima prova.

Retorne APENAS um JSON válido, sem markdown:
{{
  "previsoes": [
    {{
      "categoria": "Nome exato da disciplina",
      "probabilidade": 85,
      "justificativa": "Uma frase explicando a estimativa"
    }}
  ]
}}

Inclua TODAS as disciplinas listadas, ordene da maior para menor probabilidade."""

    try:
        resp = _call_ia(prompt)
        raw     = resp.text.strip()
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        import json as _json
        data    = _json.loads(raw)
        return data.get('previsoes', [])
    except Exception as e:
        logger.error(f"ai_prever_topicos error: {e}")
        return []
