"""
Audita questões por problemas de qualidade e opcionalmente aplica correções seguras.

Detecta:
  - Enunciado incompleto (termina em conjunção, dois-pontos, vírgula, etc)
  - Marcadores de conteúdo faltando ([...], ___, "abaixo:" sem imagem)
  - Espaços duplicados/triplicados
  - Espaço antes de pontuação
  - Aspas mistas ('' vs "")
  - Caracteres de controle / \\n literal
  - Palavras coladas suspeitas
  - Alternativa vazia ou muito curta
  - Alternativa idêntica ao enunciado
  - Ponto duplo no fim (".."  em vez de ".")

Uso:
    # Só relatório (padrão)
    python manage.py auditar_questoes

    # Aplica fixes seguros (whitespace, aspas, etc). NÃO edita conteúdo.
    python manage.py auditar_questoes --fix

    # Reverte aprovações de questões com problemas graves (sem gabarito, incompleto)
    python manage.py auditar_questoes --fix --reverter-aprovadas

    # Só uma categoria
    python manage.py auditar_questoes --categoria "Direito Penal"
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from quiz.models import Questao, Alternativa, Categoria
from quiz.auditoria import (
    detectar_flags, label_flag,
    FLAGS_GRAVES, CARS_CONTROLE, BACKSLASH_N_LITERAL,
    RE_LETRAS_FLUTUANTES_LONGAS, RE_WATERMARKS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Correções automáticas — SEGURAS: só normalizam formatação, não alteram
# semântica. Retorna (novo_texto, quais_flags_foram_corrigidas).
# ─────────────────────────────────────────────────────────────────────────────
def _autofix_texto(texto):
    original = texto
    fixes = set()

    # Watermarks residuais (PCI Concursos, Q-concursos etc)
    if RE_WATERMARKS.search(texto):
        texto = RE_WATERMARKS.sub('', texto)
        fixes.add('watermark_residual')

    # Sequências longas de letras flutuantes (5+ letras isoladas: "d o m i c")
    # Só cola sequências grandes — 3-4 letras podem ser acrônimo (PRF, CNH).
    def _cola_flutuantes(match):
        return match.group(0).replace(' ', '')
    novo = RE_LETRAS_FLUTUANTES_LONGAS.sub(_cola_flutuantes, texto)
    if novo != texto:
        texto = novo
        fixes.add('letras_flutuantes_longas')

    # Escapes literais → caractere real
    if BACKSLASH_N_LITERAL.search(texto):
        texto = texto.replace('\\n', '\n').replace('\\r', '\n').replace('\\t', ' ')
        fixes.add('escapes_literais')

    # Chars de controle removidos
    if CARS_CONTROLE.search(texto):
        texto = CARS_CONTROLE.sub('', texto)
        fixes.add('caracteres_controle')

    # Aspas curvas mistas → retas
    tem_curvas = ('“' in texto) or ('”' in texto) or ('‘' in texto) or ('’' in texto)
    if tem_curvas:
        texto = texto.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
        # não conta como fix visível — questão pode ter aspas legítimas

    # Espaços duplicados → 1 espaço (preserva quebra de linha)
    novo = re.sub(r'[ \t]+', ' ', texto)
    if novo != texto:
        texto = novo
        fixes.add('espacos_duplicados')

    # Espaço antes de pontuação
    novo = re.sub(r' +([.,;:!?])', r'\1', texto)
    if novo != texto:
        texto = novo
        fixes.add('espaco_antes_pontuacao')

    # Ponto duplo no final ".." → "." (mas preserva "...")
    if texto.rstrip().endswith('..') and not texto.rstrip().endswith('...'):
        texto = re.sub(r'\.\.$', '.', texto.rstrip())
        fixes.add('ponto_duplo_no_fim')

    # Palavras consecutivas duplicadas ("de de")
    novo = re.sub(r'\b(\w{3,})\s+\1\b', r'\1', texto, flags=re.I)
    if novo != texto:
        texto = novo
        fixes.add('palavras_duplicadas')

    # Trim edges
    texto = texto.strip()

    return texto, fixes



class Command(BaseCommand):
    help = 'Audita questões e opcionalmente aplica correções seguras'

    def add_arguments(self, parser):
        parser.add_argument('--fix', action='store_true',
                            help='Aplica correções seguras de formatação (não muda semântica)')
        parser.add_argument('--reverter-aprovadas', action='store_true',
                            help='Se combinado com --fix, marca revisada=False em questões '
                                 'aprovadas que ainda tenham FLAGS_GRAVES depois do fix.')
        parser.add_argument('--categoria', type=str, default='',
                            help='Filtra por categoria')
        parser.add_argument('--status', type=str, default='all',
                            choices=['all', 'pending', 'approved'],
                            help='Auditar quais: all (padrão) | pending | approved')

    def handle(self, *args, **opts):
        qs = Questao.objects.all()
        if opts['status'] == 'pending':
            qs = qs.filter(revisada=False, rejeitada_definitiva=False)
        elif opts['status'] == 'approved':
            qs = qs.filter(revisada=True)

        if opts['categoria']:
            try:
                cat = Categoria.objects.get(nome__iexact=opts['categoria'])
                qs = qs.filter(categoria=cat)
            except Categoria.DoesNotExist:
                self.stderr.write(f'Categoria "{opts["categoria"]}" não encontrada.')
                return

        qs = qs.select_related('categoria').prefetch_related('alternativa_set')

        contagem_flags = {}
        problematicas_com_grave = []
        fixes_aplicadas = {'texto': 0, 'alts': 0}
        total = 0

        for q in qs:
            total += 1
            alts = list(q.alternativa_set.all())

            # Auto-fix ANTES da detecção (pra não contar flag que já vamos consertar)
            if opts['fix']:
                novo_texto, fixes_t = _autofix_texto(q.texto or '')
                if fixes_t and novo_texto != (q.texto or ''):
                    q.texto = novo_texto
                    q.save(update_fields=['texto'])
                    fixes_aplicadas['texto'] += 1

                for a in alts:
                    novo_alt, fixes_a = _autofix_texto(a.texto or '')
                    if fixes_a and novo_alt != (a.texto or ''):
                        a.texto = novo_alt
                        a.save(update_fields=['texto'])
                        fixes_aplicadas['alts'] += 1

                if (q.justificativa or '').strip():
                    novo_j, fixes_j = _autofix_texto(q.justificativa)
                    if fixes_j and novo_j != q.justificativa:
                        q.justificativa = novo_j
                        q.save(update_fields=['justificativa'])

            # Detecta problemas restantes
            flags = detectar_flags(q, alts)
            for f in flags:
                contagem_flags[f] = contagem_flags.get(f, 0) + 1

            if flags and any(f in FLAGS_GRAVES for f in flags):
                problematicas_com_grave.append((q.id, q.revisada, flags))

        # Reverter aprovações com problemas graves
        revertidas = 0
        if opts['fix'] and opts['reverter_aprovadas']:
            ids_para_reverter = [
                qid for qid, aprov, flags in problematicas_com_grave if aprov
            ]
            if ids_para_reverter:
                with transaction.atomic():
                    revertidas = Questao.objects.filter(
                        id__in=ids_para_reverter, revisada=True
                    ).update(revisada=False)

        # ── Relatório ──────────────────────────────────────────────────────
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.HTTP_INFO(
            f'Auditadas {total} questão(ões) [status={opts["status"]}]'
        ))
        if opts['fix']:
            self.stdout.write(self.style.SUCCESS(
                f'Fixes aplicados: {fixes_aplicadas["texto"]} enunciados, '
                f'{fixes_aplicadas["alts"]} alternativas'
            ))
        if opts['reverter_aprovadas'] and revertidas:
            self.stdout.write(self.style.WARNING(
                f'Reverted (aprovadas → pendentes com problemas graves): {revertidas}'
            ))

        if contagem_flags:
            self.stdout.write('\nProblemas detectados (depois do fix, se --fix):')
            for flag, n in sorted(contagem_flags.items(), key=lambda x: -x[1]):
                marker = '⚠' if flag in FLAGS_GRAVES else ' '
                label = flag.replace('_', ' ')
                self.stdout.write(f'  {marker} {n:>4} — {label}')
            self.stdout.write('\n⚠ = grave (requer intervenção humana ou geração IA)')

        n_graves = sum(1 for _, _, fs in problematicas_com_grave)
        self.stdout.write(
            f'\n{n_graves} questão(ões) com pelo menos 1 flag grave.'
        )
        if opts['fix'] and not opts['reverter_aprovadas']:
            aprovadas_graves = sum(
                1 for _, aprov, _ in problematicas_com_grave if aprov
            )
            if aprovadas_graves:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠ {aprovadas_graves} delas estão APROVADAS. '
                    f'Rode com --reverter-aprovadas pra passar pra pendente.'
                ))
