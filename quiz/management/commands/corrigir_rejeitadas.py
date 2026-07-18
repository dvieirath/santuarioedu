"""
Processa questões reprovadas: envia para IA reescrever baseado no motivo de rejeição.

Uso:
    # Processa todas as questões com motivo_rejeicao preenchido
    python manage.py corrigir_rejeitadas

    # Apenas X questões por vez
    python manage.py corrigir_rejeitadas --limit 10

    # IDs específicos
    python manage.py corrigir_rejeitadas --ids 123,124,125

    # Limite de tentativas antes de marcar como rejeitada definitiva
    python manage.py corrigir_rejeitadas --max_tentativas 3
"""
import json
import re
import time
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings
import google.generativeai as genai

from quiz.models import Questao, Alternativa


PROMPT_CORRECAO = """Você é um revisor especialista em concursos públicos.

Uma questão de "{categoria}" foi REPROVADA por um revisor humano.

QUESTÃO ORIGINAL:
Enunciado: {texto}
Tipo: {tipo_desc}
Banca: {banca}
Justificativa anterior: {justificativa}

ALTERNATIVAS ORIGINAIS:
{alternativas}

MOTIVO DA REPROVAÇÃO (pelo revisor humano):
"{motivo}"

TAREFA:
Reescreva a questão CORRIGINDO os problemas apontados. Mantenha o mesmo tema, mas:
- Resolva especificamente o que o revisor apontou no motivo
- Garanta clareza no enunciado
- Garanta gabarito correto com base legal/teórica
- Alternativas devem ser plausíveis e distintas (para ME, sempre 5)
- Justificativa deve citar artigo/dispositivo legal quando aplicável

Responda SOMENTE em JSON válido, sem markdown code fences:

{{
  "texto": "Novo enunciado corrigido...",
  "assunto": "Tópico específico",
  "justificativa": "Nova justificativa com base legal/teórica",
  {alternativas_fmt}
}}
"""


class Command(BaseCommand):
    help = 'Reprocessa questões reprovadas usando IA com base no motivo'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20,
                            help='Quantas questões processar nesta execução')
        parser.add_argument('--ids', type=str, default='',
                            help='IDs específicos (vírgula-separados)')
        parser.add_argument('--max_tentativas', type=int, default=3,
                            help='Após N tentativas, marca como rejeitada_definitiva')
        parser.add_argument('--model', type=str, default='gemini-3.1-flash-lite')
        parser.add_argument('--delay', type=float, default=2.0)

    def handle(self, *args, **opts):
        api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            raise CommandError('GEMINI_API_KEY não configurada')

        max_t = opts['max_tentativas']

        qs = Questao.objects.exclude(motivo_rejeicao='').filter(
            rejeitada_definitiva=False,
            revisada=False,
        )

        if opts['ids']:
            try:
                ids = [int(x) for x in opts['ids'].split(',') if x.strip()]
                qs = qs.filter(id__in=ids)
            except ValueError:
                raise CommandError('IDs inválidos')

        questoes = list(qs[:opts['limit']])

        if not questoes:
            self.stdout.write(self.style.SUCCESS(
                'Nenhuma questão pendente de correção. ✓'
            ))
            return

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(opts['model'])

        self.stdout.write(self.style.HTTP_INFO(
            f'\nReprocessando {len(questoes)} questão(ões)…\n'
        ))

        corrigidas, esgotadas, falhas = 0, 0, 0

        for idx, q in enumerate(questoes, 1):
            self.stdout.write(
                f'  [{idx}/{len(questoes)}] id={q.id} '
                f'(tentativa {q.tentativas_correcao + 1}/{max_t})… ',
                ending=''
            )
            self.stdout.flush()

            # Esgotou? Marca como rejeitada definitiva
            if q.tentativas_correcao >= max_t:
                q.rejeitada_definitiva = True
                q.save(update_fields=['rejeitada_definitiva'])
                self.stdout.write(self.style.WARNING('esgotado → rejeitada definitiva'))
                esgotadas += 1
                continue

            # Monta prompt
            alts_orig = list(q.alternativa_set.all())
            tipo_desc = ('Múltipla escolha (5 alternativas, 1 correta)'
                         if q.tipo == 'ME'
                         else 'Certo ou Errado')

            if q.tipo == 'ME':
                alts_str = '\n'.join([
                    f'  [{"X" if a.correta else " "}] {a.texto}'
                    for a in alts_orig
                ])
                alternativas_fmt = (
                    '"alternativas": [{"texto":"...","correta":true},'
                    '{"texto":"...","correta":false},'
                    '{"texto":"...","correta":false},'
                    '{"texto":"...","correta":false},'
                    '{"texto":"...","correta":false}]'
                )
            else:  # CE
                alts_str = '\n'.join([
                    f'  [{"X" if a.correta else " "}] {a.texto}'
                    for a in alts_orig
                ])
                alternativas_fmt = '"resposta_ce": "C"  // ou "E"'

            prompt = PROMPT_CORRECAO.format(
                categoria=q.categoria.nome,
                texto=q.texto,
                tipo_desc=tipo_desc,
                banca=q.banca or 'Cebraspe',
                justificativa=q.justificativa or '(sem justificativa)',
                alternativas=alts_str or '(sem alternativas)',
                motivo=q.motivo_rejeicao,
                alternativas_fmt=alternativas_fmt,
            )

            try:
                resp = model.generate_content(prompt)
                texto = (resp.text or '').strip()
                texto = re.sub(r'^```(?:json)?\s*', '', texto)
                texto = re.sub(r'\s*```$', '', texto)
                dados = json.loads(texto)
            except json.JSONDecodeError as e:
                self.stdout.write(self.style.WARNING(f'JSON inválido: {str(e)[:50]}'))
                falhas += 1
                q.tentativas_correcao += 1
                q.save(update_fields=['tentativas_correcao'])
                if opts['delay']: time.sleep(opts['delay'])
                continue
            except Exception as e:
                tipo_err = type(e).__name__
                if 'ResourceExhausted' in tipo_err or '429' in str(e):
                    self.stdout.write(self.style.WARNING('quota Gemini esgotada — encerrando'))
                    break
                self.stdout.write(self.style.WARNING(f'erro {tipo_err}'))
                falhas += 1
                q.tentativas_correcao += 1
                q.save(update_fields=['tentativas_correcao'])
                if opts['delay']: time.sleep(opts['delay'])
                continue

            # Aplica a correção
            with transaction.atomic():
                q.texto = (dados.get('texto') or q.texto).strip()
                q.assunto = (dados.get('assunto') or q.assunto or '')[:255]
                q.justificativa = (dados.get('justificativa') or q.justificativa or '').strip()
                q.motivo_rejeicao = ''   # limpa motivo — entra de volta na fila de revisão
                q.tentativas_correcao += 1
                q.save(update_fields=['texto', 'assunto', 'justificativa',
                                      'motivo_rejeicao', 'tentativas_correcao'])

                # Substitui alternativas
                q.alternativa_set.all().delete()
                if q.tipo == 'ME':
                    for alt in dados.get('alternativas', []):
                        Alternativa.objects.create(
                            questao=q,
                            texto=(alt.get('texto') or '').strip(),
                            correta=bool(alt.get('correta')),
                        )
                else:  # CE
                    resp_ce = (dados.get('resposta_ce') or 'C').upper()
                    Alternativa.objects.create(questao=q, texto='Certo', correta=(resp_ce == 'C'))
                    Alternativa.objects.create(questao=q, texto='Errado', correta=(resp_ce == 'E'))

            self.stdout.write(self.style.SUCCESS(f'corrigida — volta pra fila de revisão'))
            corrigidas += 1

            if opts['delay'] and idx < len(questoes):
                time.sleep(opts['delay'])

        # Resumo
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(f'✓ {corrigidas} corrigidas pela IA'))
        if esgotadas:
            self.stdout.write(self.style.WARNING(
                f'⛔ {esgotadas} marcadas como rejeitada_definitiva (esgotaram tentativas)'
            ))
        if falhas:
            self.stdout.write(self.style.WARNING(f'⚠ {falhas} falhas técnicas (tentar de novo)'))

        self.stdout.write(
            '\nAs corrigidas voltaram para fila de revisão. '
            'Acesse /admin/quiz/questao/?revisada__exact=0&motivo_rejeicao__exact='
        )
