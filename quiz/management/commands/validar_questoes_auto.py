"""
Valida questões pendentes SEM usar IA — só heurísticas de qualidade.

Regras aplicadas (todas precisam passar pra auto-aprovar):
  1. Tem exatamente 1 alternativa correta (nem 0 nem 2+)
  2. Enunciado tem >= MIN_TEXTO chars (default 30)
  3. Justificativa tem >= MIN_JUSTIF chars (default 50)
  4. Nenhuma alternativa vazia ou identica a outra
  5. Numero certo de alternativas: ME=4-5, CE=2 (Certo/Errado)
  6. Nao e duplicata (>85% similaridade) de outra APROVADA na mesma categoria

Uso:
    # Dry-run: só relatório, sem aprovar nada
    python manage.py validar_questoes_auto --dry-run

    # Aprova de verdade
    python manage.py validar_questoes_auto

    # Filtra por categoria
    python manage.py validar_questoes_auto --categoria "Direito Penal"

    # Muda thresholds
    python manage.py validar_questoes_auto --min-justif 100
"""
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand
from django.db import transaction

from quiz.models import Questao, Categoria


class Command(BaseCommand):
    help = 'Valida questões pendentes por heurísticas e aprova automaticamente'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Só imprime o relatório, sem alterar nada')
        parser.add_argument('--categoria', type=str, default='',
                            help='Nome da categoria (opcional; padrão: todas)')
        parser.add_argument('--min-texto', type=int, default=30,
                            help='Tamanho mínimo do enunciado (default 30)')
        parser.add_argument('--min-justif', type=int, default=50,
                            help='Tamanho mínimo da justificativa (default 50)')
        parser.add_argument('--dedup-threshold', type=float, default=0.85,
                            help='Threshold de similaridade pra flag duplicata (default 0.85)')
        parser.add_argument('--apenas-ia', action='store_true',
                            help='Só valida questões marcadas gerada_por_ia=True')
        parser.add_argument('--limite', type=int, default=0,
                            help='Máximo de questões a processar (0 = sem limite)')

    def handle(self, *args, **opts):
        MIN_TEXTO  = opts['min_texto']
        MIN_JUSTIF = opts['min_justif']
        DEDUP_TH   = opts['dedup_threshold']
        DRY        = opts['dry_run']
        LIMITE     = opts['limite']

        qs = Questao.objects.filter(revisada=False, rejeitada_definitiva=False)
        if opts['apenas_ia']:
            qs = qs.filter(gerada_por_ia=True)
        if opts['categoria']:
            try:
                cat = Categoria.objects.get(nome__iexact=opts['categoria'])
                qs = qs.filter(categoria=cat)
            except Categoria.DoesNotExist:
                self.stderr.write(f'Categoria "{opts["categoria"]}" não encontrada.')
                return

        qs = qs.select_related('categoria').prefetch_related('alternativa_set')
        if LIMITE:
            qs = qs[:LIMITE]

        aprovadas_ids = []
        rejeitadas_por_regra = {
            'sem_alt_correta':      [],
            'multiplas_corretas':   [],
            'texto_curto':          [],
            'justif_curta':         [],
            'alt_vazia':            [],
            'alts_duplicadas':      [],
            'qtd_alts_invalida':    [],
            'duplicata':            [],
        }

        # Cache de textos aprovados por categoria pra deduplicação
        aprovadas_por_cat = {}

        total = qs.count() if not LIMITE else len(list(qs))
        self.stdout.write(self.style.HTTP_INFO(
            f'\nValidando {total} questão(ões) pendente(s)'
            f'{" (dry-run)" if DRY else ""}...\n'
        ))

        for q in qs:
            alts = list(q.alternativa_set.all())
            n_corretas = sum(1 for a in alts if a.correta)

            # Regra 1: alternativa correta única
            if n_corretas == 0:
                rejeitadas_por_regra['sem_alt_correta'].append(q.id)
                continue
            if n_corretas > 1:
                rejeitadas_por_regra['multiplas_corretas'].append(q.id)
                continue

            # Regra 2: enunciado mínimo
            texto = (q.texto or '').strip()
            if len(texto) < MIN_TEXTO:
                rejeitadas_por_regra['texto_curto'].append(q.id)
                continue

            # Regra 3: justificativa mínima
            justif = (q.justificativa or '').strip()
            if len(justif) < MIN_JUSTIF:
                rejeitadas_por_regra['justif_curta'].append(q.id)
                continue

            # Regra 4: alternativas não vazias e não duplicadas
            alt_textos = [(a.texto or '').strip() for a in alts]
            if any(not t for t in alt_textos):
                rejeitadas_por_regra['alt_vazia'].append(q.id)
                continue
            if len(set(alt_textos)) < len(alt_textos):
                rejeitadas_por_regra['alts_duplicadas'].append(q.id)
                continue

            # Regra 5: quantidade de alternativas coerente com tipo
            n_alts = len(alts)
            if q.tipo == 'CE':
                if n_alts != 2:
                    rejeitadas_por_regra['qtd_alts_invalida'].append(q.id)
                    continue
            else:  # ME
                if n_alts not in (4, 5):
                    rejeitadas_por_regra['qtd_alts_invalida'].append(q.id)
                    continue

            # Regra 6: não é duplicata de já aprovada na mesma categoria
            cat_id = q.categoria_id
            if cat_id not in aprovadas_por_cat:
                aprovadas_por_cat[cat_id] = list(
                    Questao.objects.filter(
                        categoria_id=cat_id, revisada=True
                    ).values_list('texto', flat=True)
                )
            texto_lc = texto.lower()
            eh_dup = False
            for ap in aprovadas_por_cat[cat_id]:
                ap_lc = (ap or '').strip().lower()
                if not ap_lc or abs(len(ap_lc) - len(texto_lc)) > len(texto_lc) * 0.5:
                    continue
                if SequenceMatcher(None, texto_lc, ap_lc).quick_ratio() < DEDUP_TH - 0.05:
                    continue
                if SequenceMatcher(None, texto_lc, ap_lc).ratio() >= DEDUP_TH:
                    eh_dup = True
                    break
            if eh_dup:
                rejeitadas_por_regra['duplicata'].append(q.id)
                continue

            aprovadas_ids.append(q.id)
            # Adiciona ao cache para próximas dedups no mesmo run
            aprovadas_por_cat[cat_id].append(texto)

        # Aplica (se não for dry-run)
        if not DRY and aprovadas_ids:
            with transaction.atomic():
                Questao.objects.filter(id__in=aprovadas_ids).update(
                    revisada=True, motivo_rejeicao='', rejeitada_definitiva=False
                )

        # Relatório
        self.stdout.write('\n' + '=' * 60)
        estilo = self.style.SUCCESS if not DRY else self.style.HTTP_INFO
        self.stdout.write(estilo(
            f'{"[DRY-RUN] Seriam aprovadas" if DRY else "✓ Aprovadas"}: '
            f'{len(aprovadas_ids)} de {total}'
        ))

        total_reprovadas = sum(len(v) for v in rejeitadas_por_regra.values())
        if total_reprovadas:
            self.stdout.write(f'\nNão aprovadas ({total_reprovadas}) — razões:')
            for regra, ids in rejeitadas_por_regra.items():
                if ids:
                    exemplos = ', '.join(f'#{i}' for i in ids[:5])
                    if len(ids) > 5:
                        exemplos += f' +{len(ids) - 5}'
                    label = {
                        'sem_alt_correta':    'Nenhuma alternativa marcada correta',
                        'multiplas_corretas': 'Mais de 1 alternativa correta',
                        'texto_curto':        f'Enunciado < {MIN_TEXTO} chars',
                        'justif_curta':       f'Justificativa < {MIN_JUSTIF} chars',
                        'alt_vazia':          'Alternativa vazia',
                        'alts_duplicadas':    'Alternativas idênticas',
                        'qtd_alts_invalida':  'Nº de alternativas incorreto (ME:4-5, CE:2)',
                        'duplicata':          'Duplicata de questão aprovada',
                    }[regra]
                    self.stdout.write(f'  {len(ids):>4} — {label}  [{exemplos}]')

        self.stdout.write('\nDicas:')
        self.stdout.write('  - Corrigir justif curta:   `gerar_justificativas_ia --limit N`')
        self.stdout.write('  - Ver com problemas no painel: /admin-revisao/ e filtrar')
        self.stdout.write('  - Rodar de novo:           `validar_questoes_auto` (após correções)')
