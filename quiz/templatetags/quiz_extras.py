from django import template
from django.template.defaultfilters import stringfilter
import logging
import re

import markdown as md
import nh3
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter()
@stringfilter
def markdown(value):
    return nh3.clean(
        md.markdown(value, extensions=['markdown.extensions.fenced_code']),
        tags={'p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'blockquote',
              'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'pre', 'code', 'hr', 'a'},
        attributes={'a': {'href', 'title'}},
        url_schemes={'https', 'http', 'mailto'},
    )


_RE_DESTAQUE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S)


@register.filter()
@stringfilter
def enunciado(value):
    """Texto de questão ou alternativa para a tela.

    Escapa tudo (enunciado não é HTML: "x < 5" e "<div>" aparecem como
    texto) e só então transforma **trecho** em negrito, que é como as provas
    importadas marcam a palavra "em destaque".
    """
    return mark_safe(_RE_DESTAQUE.sub(r"<strong>\1</strong>", escape(value)))


@register.simple_tag
def videos_relacionados(questao, limite=3):
    """Vídeos aprovados para o tema da questão e o link de busca de reserva.

    Uso: {% videos_relacionados questao as rel %}. Uma falha aqui (tabela
    ausente, banco fora) não pode derrubar a tela da questão: devolve vazio.
    """
    from ..videos import link_busca, termo_da_questao, videos_para
    try:
        videos = videos_para(questao, limite)
        termo = termo_da_questao(questao)
    except Exception:  # noqa: BLE001 - widget opcional na tela de resultado
        logging.getLogger(__name__).exception('falha ao montar vídeos relacionados')
        return {'videos': [], 'termo': '', 'link_busca': ''}
    return {'videos': videos, 'termo': termo, 'link_busca': link_busca(termo) if termo else ''}
