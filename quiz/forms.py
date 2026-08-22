"""
Django Forms — validacao estruturada de POST.

Substitui os `request.POST.get('campo', '').strip()` cru por validadores
declarativos com sanitizacao automatica.

Padrao de uso:
    form = MeuFormulario(request.POST)
    if form.is_valid():
        dados = form.cleaned_data
        # dados['nome'] ja veio limpo, validado, com tipo correto
    else:
        # form.errors tem estrutura serializavel
        pass

Vantagens sobre POST.get() manual:
- Sanitizacao automatica (strip, MaxLength, tipos)
- Erros estruturados (i18n-ready)
- CSRF ja incluso quando renderiza {{ form }}
- Testes ficam menores (nao precisa validar cada campo na view)

Adicione novos Forms aqui conforme migrar views.
"""
from django import forms
from django.core.validators import MinValueValidator, MaxValueValidator, MinLengthValidator


class EditalPersonalizadoForm(forms.Form):
    """Cadastro/analise do edital colado pelo user."""
    texto_edital = forms.CharField(
        min_length=200,
        max_length=20000,
        widget=forms.Textarea,
        error_messages={
            'required':   'Cole o texto do edital.',
            'min_length': 'Edital muito curto — cole ao menos 200 caracteres.',
            'max_length': 'Edital muito longo (max 20 mil chars).',
        },
    )
    horas_dia = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=12,
        initial=2,
        error_messages={
            'min_value': 'Minimo 1h/dia.',
            'max_value': 'Maximo 12h/dia.',
        },
    )

    def clean_horas_dia(self):
        return self.cleaned_data.get('horas_dia') or 2


class MensagemCoachIAForm(forms.Form):
    """Nova mensagem enviada pro coach IA."""
    mensagem = forms.CharField(
        min_length=1,
        max_length=3000,
        widget=forms.Textarea,
    )


class AnotacaoQuestaoForm(forms.Form):
    """Anotacao pessoal em uma questao."""
    texto = forms.CharField(
        max_length=2000,
        required=False,
        widget=forms.Textarea,
    )


class ComentarioForm(forms.Form):
    """Comentario em questao ou justificativa."""
    conteudo = forms.CharField(
        min_length=3,
        max_length=1500,
        widget=forms.Textarea,
    )


class SuporteTicketForm(forms.Form):
    """Abertura de ticket de suporte."""
    CATEGORIAS = [
        ('bug',       '🐛 Bug ou erro técnico'),
        ('duvida',    '❓ Dúvida sobre a plataforma'),
        ('sugestao',  '💡 Sugestão de melhoria'),
        ('outro',     '📝 Outro'),
    ]
    categoria = forms.ChoiceField(choices=CATEGORIAS)
    assunto = forms.CharField(min_length=3, max_length=200)
    mensagem = forms.CharField(min_length=10, max_length=5000, widget=forms.Textarea)


class ConcursoPreferidoForm(forms.Form):
    """Setup inicial do onboarding."""
    CONCURSOS = [
        ('prf', 'PRF'), ('pf', 'PF'), ('inss', 'INSS'),
        ('tjdf', 'TJ-DF'), ('trf', 'TRF'), ('camara', 'Câmara/Senado'),
        ('enem', 'ENEM'), ('estadual', 'Estadual'), ('municipal', 'Municipal'),
        ('outro', 'Outro'),
    ]
    concurso = forms.ChoiceField(choices=CONCURSOS)
    horas_por_dia = forms.IntegerField(
        min_value=1, max_value=16, initial=2, required=False,
    )
    data_prova_esperada = forms.DateField(required=False)
