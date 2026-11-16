"""
Conferência de gabarito das questões geradas por IA, só com cota gratuita.

Ideia: dois modelos de famílias diferentes resolvem a questão SEM ver o
gabarito. O voto de cada um fica gravado; a decisão sai dos votos:

- confirmada: todos responderam o gabarito, com certeza, sem apontar defeito
              e sem achar a questão fraca;
- rejeitar:   dois modelos apontaram defeito, ou dois acharam a questão fraca,
              ou dois responderam a mesma coisa e ela não é o gabarito;
- dúvida:     qualquer outro caso. Fica pendente para revisão humana.

Conferir só o gabarito não basta: na calibragem, 5 de 14 questões com gabarito
"confirmado" eram ruins (caso juridicamente incoerente, resposta que era só a
menos errada). Por isso cada juiz também diz se a questão é fraca.

Quem gera a questão e quem confere não podem ser o mesmo modelo: um modelo
tende a concordar com o próprio erro. Por isso a decisão exige votos de
famílias diferentes (`familia_de`).

Este módulo não toca no banco. Quem grava é `manage.py verificar_pendentes_ia`.
"""
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings

from .ai_provider import AIBadResponse, AIError, AIQuotaExceeded

PREFIXO_MOTIVO = '[conferência por IA] '
LETRAS = 'ABCDE'
_UA = 'SantuarioEdu/1.0 (Python urllib)'


class CotaDiariaEsgotada(AIQuotaExceeded):
    """A cota do dia deste modelo acabou: não adianta esperar, só amanhã."""


# ──────────────────────────────────────────────────────────────────────────
# Chamada aos provedores (modelo escolhido por chamada, sem custo)
# ──────────────────────────────────────────────────────────────────────────
def familia_de(juiz):
    """'groq:openai/gpt-oss-120b' -> 'openai'. Votos da mesma família contam como um."""
    provedor, _, modelo = juiz.partition(':')
    m = modelo.lower()
    if provedor == 'gemini' or 'gemini' in m or 'gemma' in m:
        return 'google'
    for marca in ('gpt-oss', 'openai'):
        if marca in m:
            return 'openai'
    for marca in ('qwen', 'nemotron', 'llama', 'kimi', 'deepseek', 'mistral'):
        if marca in m:
            return marca
    return m.split('/')[0] or provedor


def _espera_em_segundos(texto):
    """'try again in 7m12.5s' / 'retryDelay: 32s' -> segundos (None se não achar)."""
    m = re.search(r'try again in (?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)s)?', texto or '')
    if m and any(m.groups()):
        h, mi, s = (float(x) if x else 0.0 for x in m.groups())
        return h * 3600 + mi * 60 + s
    m = re.search(r'"retryDelay"\s*:\s*"([\d.]+)s"', texto or '')
    return float(m.group(1)) if m else None


def _post(url, payload, cabecalhos, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'User-Agent': _UA, **cabecalhos})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _tratar_429(juiz, corpo):
    """Decide se o 429 é do minuto (dá para esperar) ou do dia (acabou por hoje)."""
    baixo = corpo.lower()
    espera = _espera_em_segundos(corpo)
    diaria = ('per day' in baixo or 'perday' in baixo or 'per-day' in baixo or '(tpd)' in baixo
              or '(rpd)' in baixo or 'daily' in baixo
              or (espera is not None and espera > 120))
    if diaria:
        raise CotaDiariaEsgotada(f'{juiz}: cota diária esgotada. {corpo[:200]}')
    return min(90.0, (espera or 20.0) + 1.0)


def chamar(juiz, prompt, max_tokens=1500, temperatura=0.0, esforco='low',
           tentativas=4, timeout=120):
    """Chama o modelo e devolve o texto. Espera sozinho os limites por minuto.

    Levanta CotaDiariaEsgotada quando a cota do dia acabou, e AIError nos
    demais erros.
    """
    provedor, _, modelo = juiz.partition(':')
    for tentativa in range(tentativas):
        try:
            if provedor == 'gemini':
                dados = _post(
                    f'https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent',
                    {'contents': [{'parts': [{'text': prompt}]}],
                     'generationConfig': {'temperature': temperatura,
                                          'maxOutputTokens': max_tokens,
                                          'responseMimeType': 'application/json'}},
                    {'x-goog-api-key': settings.GEMINI_API_KEY}, timeout)
                partes = (dados.get('candidates') or [{}])[0].get('content', {}).get('parts') or []
                texto = ''.join(p.get('text', '') for p in partes if not p.get('thought'))
            else:
                if provedor == 'groq':
                    url, chave = 'https://api.groq.com/openai/v1/chat/completions', settings.GROQ_API_KEY
                elif provedor == 'openrouter':
                    url, chave = 'https://openrouter.ai/api/v1/chat/completions', settings.OPENROUTER_API_KEY
                else:
                    raise AIError(f'provedor desconhecido: {provedor}')
                corpo = {'model': modelo, 'temperature': temperatura,
                         'messages': [{'role': 'user', 'content': prompt}],
                         'response_format': {'type': 'json_object'}}
                if provedor == 'groq' and 'gpt-oss' in modelo:
                    corpo['max_completion_tokens'] = max_tokens
                    corpo['reasoning_effort'] = esforco
                else:
                    corpo['max_tokens'] = max_tokens
                dados = _post(url, corpo, {'Authorization': f'Bearer {chave}'}, timeout)
                texto = (dados.get('choices') or [{}])[0].get('message', {}).get('content')
            if not isinstance(texto, str) or not texto.strip():
                raise AIBadResponse(f'{juiz}: resposta vazia')
            return texto
        except urllib.error.HTTPError as e:
            corpo_erro = e.read().decode('utf-8', errors='replace')[:600]
            if e.code == 429:
                espera = _tratar_429(juiz, corpo_erro)
                if tentativa == tentativas - 1:
                    raise AIQuotaExceeded(f'{juiz}: limite por minuto não liberou. {corpo_erro[:200]}')
                time.sleep(espera)
                continue
            if e.code in (500, 502, 503, 504) and tentativa < tentativas - 1:
                time.sleep(5 * (tentativa + 1))
                continue
            raise AIError(f'{juiz}: HTTP {e.code}: {corpo_erro[:300]}')
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if tentativa < tentativas - 1:
                time.sleep(5 * (tentativa + 1))
                continue
            raise AIError(f'{juiz}: falha de rede: {e}')
    raise AIError(f'{juiz}: sem resposta')


def ler_json(texto):
    """JSON da resposta, tolerando cerca de markdown e texto em volta."""
    limpo = re.sub(r'^```(?:json)?\s*|\s*```$', '', (texto or '').strip())
    try:
        return json.loads(limpo)
    except json.JSONDecodeError:
        inicio, fim = limpo.find('{'), limpo.rfind('}')
        if 0 <= inicio < fim:
            try:
                return json.loads(limpo[inicio:fim + 1])
            except json.JSONDecodeError:
                pass
    raise AIBadResponse(f'JSON inválido: {(texto or "")[:200]}')


# ──────────────────────────────────────────────────────────────────────────
# Resolução às cegas
# ──────────────────────────────────────────────────────────────────────────
INSTRUCOES_CEGAS = """Você é examinador de concursos públicos brasileiros e vai conferir questões escritas por outra pessoa.
Resolva cada questão por conta própria, como um candidato muito bem preparado. Você NÃO recebe o gabarito.

Para cada questão devolva:
- "id": o número que aparece depois de ###
- "resposta": em certo/errado, "C" ou "E"; em múltipla escolha, a letra da alternativa correta
- "certeza": "alta", "media" ou "baixa"
- "defeito": "" quando a questão pode ir para o aluno como está; senão, uma frase curta dizendo qual é o defeito

"defeito" é problema na QUESTÃO, não no conteúdo que ela afirma. Aponte defeito só quando:
- múltipla escolha com mais de uma alternativa defensável, ou com nenhuma;
- a questão depende de texto, figura, tabela ou dado que não aparece;
- o ENUNCIADO (o caso, o contexto, o comando) parte de lei, artigo, súmula, órgão ou fato real descrito de forma errada, a ponto de não haver resposta segura;
- o item de certo/errado não é uma afirmação que se possa julgar;
- a redação é confusa a ponto de não se saber o que é pedido.

NÃO é defeito:
- item de certo/errado que afirma algo falso, cita artigo que não existe ou descreve a lei de forma errada: isso é só um item cuja resposta é "E". Deixe "defeito" vazio e responda "E";
- alternativa errada em múltipla escolha;
- caso hipotético com pessoa, município, empresa ou lei local inventados;
- questão fácil, ou que você redigiria de outro jeito.

- "fraca": "" quando a questão é boa para treinar um candidato; senão, uma frase curta dizendo por que é fraca

Marque "fraca" quando existe uma melhor resposta, mas a questão não deveria ir para o aluno assim:
- o caso narrado é juridicamente ou tecnicamente incoerente (órgão que não cuida daquele assunto, instituto que não se aplica àquela situação, procedimento que não existe daquele jeito);
- a resposta é só "a menos errada": o enquadramento certo não está entre as alternativas, ou a justificativa da alternativa certa é imprecisa;
- a questão se apoia em norma revogada como se estivesse em vigor;
- a questão não cobra conhecimento real da disciplina indicada entre colchetes.
Questão simples, direta e correta é boa: deixe "fraca" vazio.

Mesmo quando apontar defeito ou fraqueza, preencha "resposta" com a melhor resposta possível.

Responda SOMENTE com JSON neste formato:
{"respostas": [{"id": 123, "resposta": "C", "certeza": "alta", "defeito": "", "fraca": ""}]}

QUESTÕES
"""


@dataclass
class Item:
    """Uma questão pronta para ser conferida (sem acesso ao banco)."""
    id: int
    tipo: str
    categoria: str
    texto: str
    alternativas: tuple
    gabarito: str
    texto_apoio: str = ''


def item_de(questao):
    """Monta o Item a partir de uma Questao (alternativas já carregadas)."""
    alts = list(questao.alternativa_set.all())
    correta = next((i for i, a in enumerate(alts) if a.correta), None)
    if correta is None:
        raise ValueError('questão sem gabarito')
    if questao.tipo == 'CE':
        gabarito = 'C' if (alts[correta].texto or '').strip().lower().startswith('c') else 'E'
    else:
        gabarito = LETRAS[correta] if correta < len(LETRAS) else '?'
    apoio = questao.texto_apoio.texto if getattr(questao, 'texto_apoio_id', None) else ''
    return Item(
        id=questao.id, tipo=questao.tipo, categoria=questao.categoria.nome,
        texto=(questao.texto or '').strip(),
        alternativas=tuple((a.texto or '').strip() for a in alts),
        gabarito=gabarito, texto_apoio=apoio,
    )


def bloco_da_questao(item):
    """Texto da questão como o juiz vê: sem gabarito."""
    linhas = [f'### {item.id} [{item.categoria}] '
              + ('(certo/errado)' if item.tipo == 'CE' else '(múltipla escolha)')]
    if item.texto_apoio:
        linhas += ['TEXTO DE APOIO:', item.texto_apoio[:5000], 'PERGUNTA:']
    linhas.append(item.texto[:3000])
    if item.tipo != 'CE':
        linhas += [f'{LETRAS[i]}) {t[:500]}' for i, t in enumerate(item.alternativas[:5])]
    return '\n'.join(linhas)


def montar_prompt_cego(itens):
    return INSTRUCOES_CEGAS + '\n\n'.join(bloco_da_questao(i) for i in itens)


def _normalizar_resposta(valor, tipo):
    r = str(valor or '').strip().upper()
    if tipo == 'CE':
        if r in ('C', 'CERTO', 'CERTA', 'CORRETO', 'CORRETA', 'V', 'VERDADEIRO'):
            return 'C'
        if r in ('E', 'ERRADO', 'ERRADA', 'INCORRETO', 'INCORRETA', 'F', 'FALSO'):
            return 'E'
        return None
    r = r.strip('().: ')
    return r if len(r) == 1 and r in LETRAS else None


_SEM_OBSERVACAO = {'', 'nenhum', 'nenhuma', 'não', 'nao', 'sem defeito', 'n/a', '-',
                   'null', 'none', 'false', 'boa', 'ok'}


def _observacao(valor):
    """Texto livre do juiz; vazio quando ele só quis dizer que não há problema."""
    texto = str(valor or '').strip()
    return '' if texto.lower().rstrip('.') in _SEM_OBSERVACAO else texto[:300]


def interpretar_votos(texto, itens):
    """Resposta do juiz -> {id: {'r': 'C', 'c': 'alta', 'd': ''}} só com votos válidos."""
    dados = ler_json(texto)
    lista = dados.get('respostas') if isinstance(dados, dict) else dados
    if not isinstance(lista, list):
        raise AIBadResponse('resposta sem a lista "respostas"')
    por_id = {i.id: i for i in itens}
    votos = {}
    for entrada in lista:
        if not isinstance(entrada, dict):
            continue
        try:
            qid = int(entrada.get('id'))
        except (TypeError, ValueError):
            continue
        item = por_id.get(qid)
        if not item:
            continue
        resposta = _normalizar_resposta(entrada.get('resposta'), item.tipo)
        if not resposta:
            continue
        certeza = str(entrada.get('certeza') or '').strip().lower()
        certeza = {'média': 'media', 'medio': 'media', 'médio': 'media'}.get(certeza, certeza)
        if certeza not in ('alta', 'media', 'baixa'):
            certeza = 'baixa'
        votos[qid] = {'r': resposta, 'c': certeza,
                      'd': _observacao(entrada.get('defeito')),
                      'f': _observacao(entrada.get('fraca'))}
    return votos


# ──────────────────────────────────────────────────────────────────────────
# Decisão a partir dos votos
# ──────────────────────────────────────────────────────────────────────────
CONFIRMADA, REJEITAR, DUVIDA, INCOMPLETA = 'confirmada', 'rejeitar', 'duvida', 'incompleta'


def decidir(gabarito, votos, minimo_de_familias=2):
    """(decisão, motivo) a partir de {juiz: voto}.

    Só decide com votos de pelo menos duas famílias de modelo. Dentro de uma
    família vale o primeiro voto, para um modelo não contar duas vezes.
    """
    por_familia = {}
    for juiz in sorted(votos):
        por_familia.setdefault(familia_de(juiz), votos[juiz])
    if len(por_familia) < minimo_de_familias:
        return INCOMPLETA, 'faltam votos de modelos independentes'

    lista = list(por_familia.values())
    com_defeito = [v for v in lista if v['d']]
    fracas = [v for v in lista if v.get('f')]
    acertos = [v for v in lista if v['r'] == gabarito]
    limpos = [v for v in acertos if not v['d'] and not v.get('f') and v['c'] != 'baixa']

    if len(com_defeito) >= 2:
        return REJEITAR, 'defeito apontado por dois modelos: ' + ' | '.join(v['d'] for v in com_defeito[:2])
    if len([v for v in lista if v['d'] or v.get('f')]) >= 2:
        return REJEITAR, 'questão fraca segundo dois modelos: ' + ' | '.join(
            (v['d'] or v['f']) for v in lista if v['d'] or v.get('f'))[:500]

    contra = {}
    for v in lista:
        if v['r'] != gabarito:
            contra[v['r']] = contra.get(v['r'], 0) + 1
    if contra and max(contra.values()) >= 2 and max(contra.values()) > len(acertos):
        outra = max(contra, key=contra.get)
        return REJEITAR, f'gabarito {gabarito}, mas dois modelos independentes responderam {outra}'

    if len(limpos) == len(lista):
        return CONFIRMADA, ''
    # Desempate com três famílias: dois votos limpos no gabarito bastam, desde
    # que o terceiro não tenha respondido outra coisa com certeza alta.
    if len(lista) >= 3 and len(limpos) >= 2 and not any(
            v['r'] != gabarito and v['c'] == 'alta' for v in lista):
        return CONFIRMADA, ''

    if com_defeito:
        return DUVIDA, 'um modelo apontou defeito: ' + com_defeito[0]['d']
    if fracas:
        return DUVIDA, 'um modelo achou a questão fraca: ' + fracas[0]['f']
    if len(acertos) < len(lista):
        return DUVIDA, f'modelos divergem sobre a resposta (gabarito {gabarito})'
    return DUVIDA, 'modelos acertaram o gabarito com baixa certeza'


# ──────────────────────────────────────────────────────────────────────────
# Estado: votos gravados em disco, para a conferência continuar noutro dia
# ──────────────────────────────────────────────────────────────────────────
class Estado:
    """Votos por questão em arquivo JSONL (uma linha por voto, só acrescenta)."""

    def __init__(self, caminho):
        self.caminho = caminho
        self.votos = {}
        if caminho.exists():
            for linha in caminho.read_text(encoding='utf-8').splitlines():
                try:
                    reg = json.loads(linha)
                    self.votos.setdefault(int(reg['id']), {})[reg['juiz']] = reg['voto']
                except (ValueError, KeyError, TypeError):
                    continue

    def registrar(self, juiz, votos, gabaritos):
        """Grava os votos de um lote. `gabaritos` entra só para auditoria posterior."""
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self.caminho.open('a', encoding='utf-8') as fh:
            for qid, voto in votos.items():
                self.votos.setdefault(qid, {})[juiz] = voto
                fh.write(json.dumps({'id': qid, 'juiz': juiz, 'voto': voto,
                                     'gabarito': gabaritos.get(qid),
                                     'quando': time.strftime('%Y-%m-%dT%H:%M:%S')},
                                    ensure_ascii=False) + '\n')

    def de(self, qid):
        return self.votos.get(qid, {})
