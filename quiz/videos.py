"""
Vídeos relacionados ao tema da questão.

Regra do projeto: o aluno só vê conteúdo revisado. Vídeo entra como
`VideoAula` ligado a uma categoria e, opcionalmente, a uma palavra-chave de
assunto; só o aprovado aparece. Sem vídeo aprovado, a tela oferece um link de
busca no YouTube com o tema da questão.

Como um vídeo casa com uma questão:
  1. vídeo com assunto: a palavra-chave dele aparece no assunto da questão
     ("responsabilidade civil" casa com "Responsabilidade civil do Estado"),
     na categoria da questão ou numa categoria acima dela;
  2. vídeo sem assunto: vale para a categoria inteira e as de baixo.
Os de assunto vêm primeiro (palavra-chave mais longa = mais específica), depois
os gerais da categoria mais próxima.

Também ficam aqui o leitor de link do YouTube, a consulta oEmbed (título e
canal, sem chave) e as chamadas à YouTube Data API usadas pela busca automática
(`manage.py buscar_videos_youtube`).
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

LIMITE_PADRAO = 3
_UA = 'SantuarioEdu/1.0 (Python urllib)'
_RE_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
_RE_LINK = re.compile(
    r'(?:youtu\.be/|youtube(?:-nocookie)?\.com/(?:embed/|shorts/|live/|v/|watch\?(?:[^#]*&)?v=))'
    r'([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])')


class ErroYouTube(Exception):
    """Falha ao consultar o YouTube (rede, vídeo inexistente, cota)."""


class VideoIndisponivel(ErroYouTube):
    """O vídeo não existe, é privado ou o dono não deixa exibir fora do YouTube."""


class CotaEsgotada(ErroYouTube):
    """A cota diária gratuita da YouTube Data API acabou."""


# ── Identificação do vídeo ────────────────────────────────────────────────
def id_valido(valor):
    return bool(valor) and bool(_RE_ID.match(valor))


def extrair_id(texto):
    """ID de 11 caracteres a partir de link do YouTube ou do próprio ID; None se não achar."""
    texto = (texto or '').strip()
    if id_valido(texto):
        return texto
    achado = _RE_LINK.search(texto)
    return achado.group(1) if achado else None


def url_assistir(video_id):
    return f'https://www.youtube.com/watch?v={video_id}'


def url_embed(video_id):
    return f'https://www.youtube-nocookie.com/embed/{video_id}'


def url_miniatura(video_id):
    return f'https://i.ytimg.com/vi/{video_id}/mqdefault.jpg'


def link_busca(termo):
    termo = ' '.join((termo or '').split())
    return 'https://www.youtube.com/results?' + urllib.parse.urlencode({'search_query': f'{termo} aula'})


def duracao_texto(segundos):
    if not segundos:
        return ''
    h, resto = divmod(int(segundos), 3600)
    m, s = divmod(resto, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def normalizar(texto):
    from .models import _normalizar_texto
    return _normalizar_texto(texto or '')


# ── Escolha dos vídeos de uma questão ─────────────────────────────────────
def cadeia_categorias(categoria_id, pais):
    """[categoria, pai, avô, ...] a partir do mapa {id: parent_id}."""
    cadeia, atual = [], categoria_id
    while atual and atual not in cadeia and len(cadeia) < 12:
        cadeia.append(atual)
        atual = pais.get(atual)
    return cadeia


def escolher(videos, cadeia, assunto_norm, limite=LIMITE_PADRAO):
    """Ordena e corta os vídeos que valem para a questão.

    `videos`: VideoAula (ou objetos com categoria_id, assunto_norm, youtube_id).
    `cadeia`: ids da categoria da questão até a raiz.
    """
    distancia = {cat_id: n for n, cat_id in enumerate(cadeia)}
    pontuados = []
    for v in videos:
        if v.categoria_id not in distancia:
            continue
        if v.assunto_norm:
            if not assunto_norm or v.assunto_norm not in assunto_norm:
                continue
            chave = (0, -len(v.assunto_norm), distancia[v.categoria_id])
        else:
            chave = (1, distancia[v.categoria_id], 0)
        pontuados.append((chave, getattr(v, 'id', 0) or 0, v))
    pontuados.sort(key=lambda t: (t[0], t[1]))
    escolhidos, vistos = [], set()
    for _chave, _id, v in pontuados:
        if v.youtube_id in vistos:
            continue
        vistos.add(v.youtube_id)
        escolhidos.append(v)
        if len(escolhidos) >= limite:
            break
    return escolhidos


def mapa_de_pais():
    from .models import Categoria
    return dict(Categoria.objects.values_list('id', 'parent_id'))


def videos_para(questao, limite=LIMITE_PADRAO):
    """Vídeos aprovados para a questão, do mais específico ao mais geral."""
    from .models import Categoria, VideoAula
    if not getattr(questao, 'categoria_id', None):
        return []
    cadeia, atual = [], questao.categoria_id
    while atual and atual not in cadeia and len(cadeia) < 12:
        cadeia.append(atual)
        atual = Categoria.objects.filter(id=atual).values_list('parent_id', flat=True).first()
    candidatos = VideoAula.objects.filter(aprovado=True, categoria_id__in=cadeia)
    return escolher(candidatos, cadeia, normalizar(questao.assunto), limite)


def termo_da_questao(questao):
    """Tema usado no link de busca: o assunto, ou o nome da categoria."""
    assunto = ' '.join((getattr(questao, 'assunto', '') or '').split())
    if assunto:
        return assunto
    categoria = getattr(questao, 'categoria', None)
    return categoria.nome if categoria else ''


# ── Consultas ao YouTube ──────────────────────────────────────────────────
def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': _UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def buscar_oembed(video_id, timeout=10):
    """Título e canal pelo oEmbed público do YouTube (sem chave).

    401/403: o dono não deixa incorporar o vídeo. 400/404: vídeo inexistente
    ou privado. Os dois casos levantam ErroYouTube com a explicação.
    """
    url = 'https://www.youtube.com/oembed?' + urllib.parse.urlencode(
        {'url': url_assistir(video_id), 'format': 'json'})
    try:
        dados = _get_json(url, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise VideoIndisponivel('O dono deste vídeo não permite exibi-lo em outros sites.') from e
        if e.code in (400, 404):
            raise VideoIndisponivel('Vídeo não encontrado, privado ou removido.') from e
        raise ErroYouTube(f'O YouTube respondeu com erro {e.code}.') from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise ErroYouTube('Não consegui consultar o YouTube agora.') from e
    return {'titulo': (dados.get('title') or '').strip()[:200],
            'canal': (dados.get('author_name') or '').strip()[:120]}


_RE_DURACAO = re.compile(r'^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$')


def segundos_iso8601(valor):
    """'PT1H2M3S' -> 3723. None se o formato não for reconhecido."""
    achado = _RE_DURACAO.match(valor or '')
    if not achado or not any(achado.groups()):
        return None
    d, h, m, s = (int(x) if x else 0 for x in achado.groups())
    return d * 86400 + h * 3600 + m * 60 + s


def _api(caminho, parametros, chave, timeout=20):
    url = f'https://www.googleapis.com/youtube/v3/{caminho}?' + urllib.parse.urlencode(
        {**parametros, 'key': chave})
    try:
        return _get_json(url, timeout=timeout)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode('utf-8', errors='replace')[:600]
        if e.code == 403 and ('quotaExceeded' in corpo or 'dailyLimitExceeded' in corpo):
            raise CotaEsgotada('A cota diária gratuita da YouTube Data API acabou.') from e
        motivo = ''
        try:
            motivo = json.loads(corpo)['error']['message']
        except (ValueError, KeyError, TypeError):
            pass
        raise ErroYouTube(f'YouTube Data API respondeu {e.code}: {motivo or corpo[:160]}') from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise ErroYouTube(f'Falha de rede ao consultar a YouTube Data API: {e}') from e


def buscar_na_api(termo, chave, quantos=3, minimo_seg=180, maximo_seg=5400):
    """Vídeos para `termo`, já filtrados: públicos, incorporáveis, sem ao vivo,
    com duração entre `minimo_seg` e `maximo_seg`. Gasta 101 unidades de cota."""
    busca = _api('search', {
        'part': 'snippet', 'q': termo, 'type': 'video', 'maxResults': 10,
        'relevanceLanguage': 'pt', 'regionCode': 'BR', 'safeSearch': 'strict',
        'videoEmbeddable': 'true',
    }, chave)
    ids = [item.get('id', {}).get('videoId') for item in busca.get('items', [])]
    ids = [i for i in ids if id_valido(i)]
    if not ids:
        return []
    detalhes = _api('videos', {'part': 'snippet,contentDetails,status', 'id': ','.join(ids)}, chave)
    por_id = {item.get('id'): item for item in detalhes.get('items', [])}
    achados = []
    for video_id in ids:   # mantém a ordem de relevância da busca
        item = por_id.get(video_id)
        if not item:
            continue
        status, snippet = item.get('status', {}), item.get('snippet', {})
        duracao = segundos_iso8601(item.get('contentDetails', {}).get('duration'))
        titulo = (snippet.get('title') or '').strip()
        if not status.get('embeddable') or status.get('privacyStatus') != 'public':
            continue
        if snippet.get('liveBroadcastContent', 'none') != 'none':
            continue
        if not duracao or not (minimo_seg <= duracao <= maximo_seg) or '#shorts' in titulo.lower():
            continue
        achados.append({'youtube_id': video_id, 'titulo': titulo[:200],
                        'canal': (snippet.get('channelTitle') or '').strip()[:120],
                        'duracao_segundos': duracao})
        if len(achados) >= quantos:
            break
    return achados
