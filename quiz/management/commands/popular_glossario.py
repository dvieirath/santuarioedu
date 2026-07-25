"""
Popula o glossario com termos gerados por IA para categorias em lote.

Uso:
    # Todas as categorias que tem >= 5 questoes
    python manage.py popular_glossario

    # Categorias especificas (nomes exatos, separados por virgula)
    python manage.py popular_glossario --categorias "Direito Penal,Português"

    # Quantidade de termos por categoria (default 30)
    python manage.py popular_glossario --qtd 20

    # Dry-run — mostra o que faria sem chamar IA
    python manage.py popular_glossario --dry_run

    # Sobrescreve termos existentes ao inves de pular
    python manage.py popular_glossario --sobrescrever

    # Delay entre chamadas IA (default 3s)
    python manage.py popular_glossario --delay 5
"""
import time

from django.core.management.base import BaseCommand
from django.db.models import Count

from quiz.models import Categoria, TermoGlossario
from quiz.ai_service import ai_glossario_termos


class Command(BaseCommand):
    help = 'Gera termos de glossario via IA para categorias em lote'

    def add_arguments(self, parser):
        parser.add_argument('--categorias', type=str, default='',
                            help='Nomes exatos de categorias, separados por virgula. '
                                 'Se vazio, usa todas com >= 5 questoes.')
        parser.add_argument('--qtd', type=int, default=30,
                            help='Termos por categoria (default 30)')
        parser.add_argument('--delay', type=float, default=3.0,
                            help='Segundos entre chamadas IA (default 3)')
        parser.add_argument('--sobrescrever', action='store_true',
                            help='Se termo ja existe, atualiza definicao. '
                                 'Sem essa flag: pula termos ja existentes.')
        parser.add_argument('--dry_run', action='store_true')

    def handle(self, *args, **opts):
        if opts['categorias']:
            nomes = [n.strip() for n in opts['categorias'].split(',') if n.strip()]
            categorias = Categoria.objects.filter(nome__in=nomes)
            faltantes = set(nomes) - set(categorias.values_list('nome', flat=True))
            if faltantes:
                self.stdout.write(self.style.WARNING(
                    f'Categorias nao encontradas: {", ".join(faltantes)}'
                ))
        else:
            # Padrao: categorias com >= 5 questoes
            categorias = (Categoria.objects
                          .annotate(n=Count('questao'))
                          .filter(n__gte=5)
                          .order_by('nome'))

        total = categorias.count()
        self.stdout.write(self.style.HTTP_INFO(
            f'\nGerando ~{opts["qtd"]} termos em {total} categoria(s)...\n'
        ))
        if opts['dry_run']:
            for c in categorias:
                self.stdout.write(f'  - {c.nome} ({c.questao_set.count()} questoes)')
            self.stdout.write(self.style.WARNING('\n[DRY-RUN] Nada gerado.'))
            return

        total_criados = 0
        total_atualizados = 0
        total_pulados = 0
        for idx, cat in enumerate(categorias, 1):
            self.stdout.write(self.style.HTTP_INFO(
                f'[{idx}/{total}] {cat.nome}'
            ))

            try:
                termos = ai_glossario_termos(cat.nome, qtd=opts['qtd'])
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'  Erro na IA: {type(e).__name__}: {str(e)[:120]}'
                ))
                if opts['delay']:
                    time.sleep(opts['delay'])
                continue

            if not termos:
                self.stdout.write(self.style.WARNING('  IA retornou vazio.'))
                if opts['delay']:
                    time.sleep(opts['delay'])
                continue

            criados_cat = 0
            atualizados_cat = 0
            pulados_cat = 0
            for t in termos:
                termo = (t.get('termo') or '').strip()
                definicao = (t.get('definicao') or '').strip()
                exemplo = (t.get('exemplo_uso') or '').strip()
                if not termo or not definicao:
                    continue

                existente = TermoGlossario.objects.filter(termo__iexact=termo).first()
                if existente:
                    if opts['sobrescrever']:
                        existente.definicao = definicao
                        if exemplo:
                            existente.exemplo_uso = exemplo
                        existente.save()
                        existente.categorias.add(cat)
                        atualizados_cat += 1
                    else:
                        # So associa a categoria (permite mesmo termo em varias disciplinas)
                        existente.categorias.add(cat)
                        pulados_cat += 1
                else:
                    obj = TermoGlossario.objects.create(
                        termo=termo,
                        definicao=definicao,
                        exemplo_uso=exemplo,
                    )
                    obj.categorias.add(cat)
                    criados_cat += 1

            total_criados += criados_cat
            total_atualizados += atualizados_cat
            total_pulados += pulados_cat
            self.stdout.write(self.style.SUCCESS(
                f'  +{criados_cat} novos · ~{atualizados_cat} atualizados · '
                f'{pulados_cat} ja existiam (soh vinculei categoria)'
            ))

            if opts['delay'] and idx < total:
                time.sleep(opts['delay'])

        # Resumo
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(
            f'\nTOTAL: {total_criados} termos novos · '
            f'{total_atualizados} atualizados · {total_pulados} ja existiam'
        ))
        self.stdout.write(f'Total no glossario agora: {TermoGlossario.objects.count()}')
        self.stdout.write('\nVer em /glossario/')
