"""
Gera justificativas via IA para questões que ainda não têm.

Uso:
    # Gera pra até 20 questões sem justificativa
    python manage.py gerar_justificativas_ia

    # Quantidade custom
    python manage.py gerar_justificativas_ia --limit 100

    # Apenas de uma categoria
    python manage.py gerar_justificativas_ia --categoria "Direito Constitucional"

    # Só as geradas por IA sem justificativa (típico após importar PDF)
    python manage.py gerar_justificativas_ia --somente_ia

    # Dry-run
    python manage.py gerar_justificativas_ia --dry_run

Comportamento:
- Pula questões sem alternativa correta marcada (não dá pra gerar sem gabarito)
- Salva `assunto` também se estiver vazio
- Delay entre chamadas evita rate-limit
"""
import time
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from quiz.models import Questao, Categoria
from quiz.ai_provider import gerar_json, AIError
from quiz.prompts_justificativa import montar_prompt


class Command(BaseCommand):
    help = 'Gera justificativas via IA para questões que estão sem'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20,
                            help='Máximo de questões a processar (default 20)')
        parser.add_argument('--categoria', type=str, default='',
                            help='Filtrar por nome de categoria')
        parser.add_argument('--somente_ia', action='store_true',
                            help='Só questões com gerada_por_ia=True')
        parser.add_argument('--somente_pendentes', action='store_true',
                            help='Só questões ainda não revisadas')
        parser.add_argument('--somente_aprovadas', action='store_true',
                            help='Só questões já aprovadas (revisada=True)')
        parser.add_argument('--regenerar', action='store_true',
                            help='REGENERAR justificativas existentes (útil pra migrar de formato)')
        parser.add_argument('--formato_antigo', action='store_true',
                            help='Só regenerar as que estão no formato antigo (sem 🔍 no texto)')
        parser.add_argument('--delay', type=float, default=2.0,
                            help='Segundos entre chamadas à IA')
        parser.add_argument('--dry_run', action='store_true',
                            help='Mostra quantas serão processadas sem gerar')

    def handle(self, *args, **opts):
        # ── Query: por padrão pega SEM justificativa ──
        if opts['regenerar']:
            # Regenerar → todas as questões que tenham gabarito, sem filtrar por justificativa vazia
            qs = Questao.objects.exclude(rejeitada_definitiva=True)
            if opts['formato_antigo']:
                # Só regerar as que NÃO têm o novo marcador visual (🔍)
                qs = qs.exclude(justificativa__contains='🔍')
        else:
            # Padrão: só as sem justificativa
            qs = Questao.objects.filter(
                Q(justificativa__isnull=True) | Q(justificativa='')
            ).exclude(rejeitada_definitiva=True)

        if opts['categoria']:
            try:
                cat = Categoria.objects.get(nome__iexact=opts['categoria'])
                qs = qs.filter(categoria=cat)
            except Categoria.DoesNotExist:
                raise CommandError(f'Categoria "{opts["categoria"]}" não encontrada')

        if opts['somente_ia']:
            qs = qs.filter(gerada_por_ia=True)
        if opts['somente_pendentes']:
            qs = qs.filter(revisada=False)
        if opts['somente_aprovadas']:
            qs = qs.filter(revisada=True)

        total_encontrado = qs.count()
        qs = qs.select_related('categoria').prefetch_related('alternativa_set')[:opts['limit']]

        self.stdout.write(self.style.HTTP_INFO(
            f'\nEncontradas {total_encontrado} questões sem justificativa. '
            f'Processando {min(opts["limit"], total_encontrado)}…\n'
        ))

        if opts['dry_run']:
            for q in qs:
                self.stdout.write(f'  · Q#{q.id} [{q.categoria.nome}] {q.texto[:80]}…')
            self.stdout.write(self.style.WARNING('\n--dry_run ativo. Nada gerado.'))
            return

        # ── Processa ──
        criadas, puladas, falhas = 0, 0, 0
        for idx, q in enumerate(qs, 1):
            self.stdout.write(
                f'  [{idx}/{len(qs)}] Q#{q.id} [{q.categoria.nome[:20]}]… ',
                ending=''
            )
            self.stdout.flush()

            # Monta prompt (compartilhado com o painel de revisão)
            try:
                prompt = montar_prompt(q)
            except ValueError:
                self.stdout.write(self.style.WARNING('sem gabarito — pulado'))
                puladas += 1
                continue

            # Chama IA — max_tokens maior porque agora o formato é mais rico
            try:
                dados = gerar_json(prompt, max_tokens=2500, temperature=0.4)
            except AIError as e:
                msg = str(e)
                if 'quota' in msg.lower() or '429' in msg:
                    self.stdout.write(self.style.ERROR('quota IA esgotada — encerrando'))
                    break
                self.stdout.write(self.style.WARNING(f'erro: {msg[:60]}'))
                falhas += 1
                if opts['delay']:
                    time.sleep(opts['delay'])
                continue

            # Salva
            just = (dados.get('justificativa') or '').strip()
            assunto = (dados.get('assunto') or '').strip()[:255]
            if not just:
                self.stdout.write(self.style.WARNING('IA não retornou justificativa'))
                falhas += 1
                continue

            q.justificativa = just
            if not q.assunto:
                q.assunto = assunto
            q.save(update_fields=['justificativa', 'assunto'])

            self.stdout.write(self.style.SUCCESS(
                f'✓ {len(just)} chars gerados'
            ))
            criadas += 1

            if opts['delay'] and idx < len(qs):
                time.sleep(opts['delay'])

        # ── Resumo ──
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(f'✓ {criadas} justificativas geradas'))
        if puladas:
            self.stdout.write(self.style.WARNING(
                f'⚠ {puladas} puladas (sem gabarito — corrija manualmente)'
            ))
        if falhas:
            self.stdout.write(self.style.WARNING(f'⚠ {falhas} falhas técnicas'))

        # Quantas ainda faltam
        if opts['regenerar'] and opts['formato_antigo']:
            ainda = Questao.objects.exclude(rejeitada_definitiva=True).exclude(
                justificativa__contains='🔍'
            ).count()
            self.stdout.write(f'\n📋 Restam {ainda} questões no formato antigo.')
        else:
            ainda = Questao.objects.filter(
                Q(justificativa__isnull=True) | Q(justificativa='')
            ).exclude(rejeitada_definitiva=True).count()
            self.stdout.write(f'\n📋 Restam {ainda} questões sem justificativa.')

        if ainda > 0:
            proximo = f'--limit {min(ainda, 500)}'
            if opts['regenerar']:
                proximo = f'--regenerar --formato_antigo ' + proximo
            self.stdout.write(f'   Rode novamente: python manage.py gerar_justificativas_ia {proximo}')
