from django import template
from django.template.defaultfilters import stringfilter
import markdown as md
import nh3

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
