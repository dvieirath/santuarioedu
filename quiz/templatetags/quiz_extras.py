from django import template
from django.template.defaultfilters import stringfilter
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
