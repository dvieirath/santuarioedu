"""
Gera questões em lote usando o ai_provider (Groq primeiro, Gemini fallback).

FLUXO DE 2 PASSOS (garante consistência de formato):
  1. Este comando gera ENUNCIADO + ALTERNATIVAS + ASSUNTO (justificativa = vazio)
  2. `gerar_justificativas_ia` preenche as justificativas no formato padrão
     SantuarioEdu (🔍 Por que · ⚠️ Armadilhas · 🧠 Conceito · etc)

Uso:
    python manage.py gerar_questoes_ia --categoria "Direito Penal" --qtd 30
    python manage.py gerar_questoes_ia --categoria "Atualidades" --qtd 50 --banca Cebraspe --tipo CE
    python manage.py gerar_questoes_ia --categoria "Direito Processual Penal" --qtd 100 --batch 10 --assunto "Prisão em flagrante"
    python manage.py gerar_questoes_ia --categoria "X" --qtd 10 --criar-se-necessario

Depois:
    python manage.py gerar_justificativas_ia --limit 100

Questões geradas entram com revisada=False, gerada_por_ia=True e sem justificativa.
Revise em /admin-revisao/ (tecla `B` para aprovação em lote) depois de gerar justificativas.
"""
import json
import re
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quiz.models import Questao, Alternativa, Categoria
from quiz.ai_provider import gerar_conteudo, AIError, AIQuotaExceeded


PROMPT_TEMPLATE = """Você é um especialista em concursos públicos brasileiros.
Gere {qtd} questões inéditas e originais sobre o tema "{categoria}"{assunto_extra}, no padrão da banca {banca}.

TIPO DE QUESTÃO: {tipo_desc}

Para CADA questão:
- Elabore enunciados TOTALMENTE ORIGINAIS. NÃO reproduza texto literal de leis, súmulas, doutrinas ou provas anteriores. Parafraseie e crie situações hipotéticas.
- Use linguagem técnica, formal e similar ao padrão da banca {banca}, mas com PALAVRAS PRÓPRIAS
- Aborde temas RELEVANTES e ATUAIS, frequentemente cobrados em provas reais
- Varie a dificuldade (algumas fáceis, médias e difíceis)
- Enunciado deve ser COMPLETO — não termine em conjunção, vírgula, dois-pontos ou reticências. Nada de "[...]" ou "___".
- NUNCA referencie IMAGENS/FIGURAS/GRÁFICOS (não temos imagens). Se citar visualmente, é proibido.
- {texto_apoio_instrucao}
- NÃO use a mesma questão duas vezes
- Para múltipla escolha (ME): SEMPRE 5 alternativas (A, B, C, D, E), apenas 1 correta
- Para certo/errado (CE): NÃO inclua alternativas, use "resposta_ce": "C" ou "E"
- NÃO inclua justificativa — ela será gerada depois em formato padronizado pelo comando gerar_justificativas_ia

Responda SOMENTE em JSON válido, sem texto antes ou depois, sem markdown code fences.
Formato exato:

[
  {{
    "texto": "Enunciado completo da questão, terminando em ponto final.",
    "tipo": "{tipo}",
    "assunto": "Tópico específico (ex: Princípios da Administração)",
    {alternativas_fmt}
  }}
]
"""


class Command(BaseCommand):
    help = 'Gera questões via IA (Groq/Gemini) para uma categoria específica'

    def add_arguments(self, parser):
        parser.add_argument('--categoria', type=str, required=True,
                            help='Nome da categoria (ex: "Direito Penal")')
        parser.add_argument('--qtd', type=int, default=10, help='Total (default 10)')
        parser.add_argument('--batch', type=int, default=5, help='Por chamada (default 5)')
        parser.add_argument('--banca', type=str, default='Cebraspe',
                            help='Banca a imitar (Cebraspe, FGV, FCC, VUNESP...)')
        parser.add_argument('--tipo', type=str, default='ME', choices=['ME', 'CE'])
        parser.add_argument('--assunto', type=str, default='', help='Sub-tópico específico')
        parser.add_argument('--delay', type=float, default=1.0,
                            help='Segundos entre chamadas (default 1s)')
        parser.add_argument('--criar-se-necessario', action='store_true',
                            help='Cria a categoria se não existir')
        parser.add_argument('--com_texto_apoio', type=float, default=0.0,
                            help='Fração 0-1 de questões que devem ter texto de apoio '
                                 'INTEGRADO no enunciado (default 0.0 = nenhuma)')

    def handle(self, *args, **opts):
        nome_cat = opts['categoria']
        try:
            categoria = Categoria.objects.get(nome__iexact=nome_cat)
        except Categoria.DoesNotExist:
            if opts['criar_se_necessario']:
                categoria = Categoria.objects.create(nome=nome_cat)
                self.stdout.write(self.style.WARNING(
                    f'Categoria "{nome_cat}" criada.'
                ))
            else:
                cats_disponiveis = ', '.join(Categoria.objects.values_list('nome', flat=True))
                raise CommandError(
                    f'Categoria "{nome_cat}" não encontrada.\n'
                    f'Disponíveis: {cats_disponiveis}\n\n'
                    f'Se quiser criar, use --criar-se-necessario'
                )

        qtd_total  = opts['qtd']
        batch_size = opts['batch']
        banca      = opts['banca']
        tipo       = opts['tipo']
        assunto    = opts['assunto']
        delay      = opts['delay']

        self.stdout.write(self.style.HTTP_INFO(
            f'\nGerando {qtd_total} questões de "{categoria.nome}" '
            f'(banca {banca}, tipo {tipo}) em lotes de {batch_size}...\n'
        ))

        criadas, falhas, duplicadas = 0, 0, 0
        n_lotes = (qtd_total + batch_size - 1) // batch_size

        for lote in range(n_lotes):
            falta = min(batch_size, qtd_total - criadas)
            if falta <= 0:
                break

            tipo_desc = ('Múltipla escolha (5 alternativas, 1 correta)'
                         if tipo == 'ME'
                         else 'Certo ou Errado (julgamento de proposição única)')
            assunto_extra = f' com foco em "{assunto}"' if assunto else ''
            alternativas_fmt = (
                '"alternativas": [{"texto":"...","correta":true},'
                '{"texto":"...","correta":false},{"texto":"...","correta":false},'
                '{"texto":"...","correta":false},{"texto":"...","correta":false}]'
                if tipo == 'ME'
                else '"resposta_ce": "C"'
            )

            pct_apoio = float(opts.get('com_texto_apoio') or 0.0)
            if pct_apoio > 0:
                n_apoio = max(1, round(falta * pct_apoio))
                texto_apoio_instrucao = (
                    f'Em EXATAMENTE {n_apoio} das {falta} questões deste lote, '
                    'inclua um TEXTO DE APOIO integrado no próprio enunciado — mini-narrativa, '
                    'situação hipotética descrita, notícia fictícia ou paragrafo teórico '
                    '(150-300 palavras) escrito ANTES da pergunta, todo dentro do campo '
                    '"texto". A pergunta então faz referência a esse texto ("Considerando '
                    'o texto acima..." é OK PORQUE o texto está incluso). NUNCA cite texto '
                    'externo que não esteja no campo "texto".'
                )
            else:
                texto_apoio_instrucao = (
                    'NÃO cite "texto acima/abaixo" nem trechos externos. '
                    'Enunciado é auto-contido.'
                )

            prompt = PROMPT_TEMPLATE.format(
                qtd=falta, categoria=categoria.nome, banca=banca,
                tipo=tipo, tipo_desc=tipo_desc,
                assunto_extra=assunto_extra, alternativas_fmt=alternativas_fmt,
                texto_apoio_instrucao=texto_apoio_instrucao,
            )

            self.stdout.write(f'  Lote {lote+1}/{n_lotes} ({falta}) → ', ending='')
            self.stdout.flush()

            try:
                texto = gerar_conteudo(prompt, json_mode=True, max_tokens=4000, temperature=0.6)
                texto = re.sub(r'^```(?:json)?\s*', '', texto.strip())
                texto = re.sub(r'\s*```$', '', texto)
                dados = json.loads(texto)
                # Alguns providers retornam {"questoes": [...]} ao invés de lista direta
                if isinstance(dados, dict):
                    dados = dados.get('questoes') or dados.get('items') or []
            except json.JSONDecodeError as e:
                self.stdout.write(self.style.WARNING(f'JSON inválido: {e}'))
                falhas += falta
                if delay:
                    time.sleep(delay)
                continue
            except AIQuotaExceeded as e:
                self.stdout.write(self.style.ERROR(f'Quota IA esgotada: {e}'))
                break
            except AIError as e:
                self.stdout.write(self.style.WARNING(f'IA falhou: {str(e)[:120]}'))
                falhas += falta
                if delay:
                    time.sleep(delay)
                continue

            n_lote, n_dup = 0, 0
            with transaction.atomic():
                for item in dados:
                    texto_q = (item.get('texto') or '').strip()
                    if not texto_q:
                        continue

                    if Questao.objects.filter(
                        categoria=categoria,
                        texto__istartswith=texto_q[:80]
                    ).exists():
                        n_dup += 1
                        continue

                    q = Questao.objects.create(
                        categoria=categoria,
                        texto=texto_q,
                        tipo=tipo,
                        justificativa='',  # gerada depois pelo prompt padronizado
                        assunto=(item.get('assunto') or '').strip() or None,
                        banca=banca,
                        revisada=False,
                        gerada_por_ia=True,
                    )

                    if tipo == 'ME':
                        for alt in (item.get('alternativas') or []):
                            Alternativa.objects.create(
                                questao=q,
                                texto=(alt.get('texto') or '').strip(),
                                correta=bool(alt.get('correta')),
                            )
                    else:
                        resp_ce = (item.get('resposta_ce') or 'C').upper()
                        Alternativa.objects.create(questao=q, texto='Certo',  correta=(resp_ce == 'C'))
                        Alternativa.objects.create(questao=q, texto='Errado', correta=(resp_ce == 'E'))

                    n_lote += 1
                    criadas += 1

            duplicadas += n_dup
            msg = f'+{n_lote}'
            if n_dup:
                msg += f' ({n_dup} dup)'
            self.stdout.write(self.style.SUCCESS(msg))

            if delay and lote < n_lotes - 1:
                time.sleep(delay)

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(
            f'✓ {criadas} questões criadas em "{categoria.nome}"'
        ))
        if duplicadas:
            self.stdout.write(f'  {duplicadas} duplicatas ignoradas')
        if falhas:
            self.stdout.write(self.style.WARNING(f'  {falhas} falharam'))
        self.stdout.write('\nPróximo passo:')
        self.stdout.write(self.style.HTTP_INFO(
            f'  python manage.py gerar_justificativas_ia --limit {max(criadas, 50)} '
            f'--categoria "{categoria.nome}"'
        ))
        self.stdout.write('  Depois revise em /admin-revisao/ (tecla `B` para bulk approve).')
