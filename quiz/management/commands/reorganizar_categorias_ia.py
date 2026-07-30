"""
Reorganiza categorias em hierarquia usando IA baseada nos assuntos existentes.

Uso:
  # 1. Analisa e imprime JSON de sugestao (nao muda nada):
  python manage.py reorganizar_categorias_ia --dry_run

  # 2. Filtra so uma categoria:
  python manage.py reorganizar_categorias_ia --dry_run --categoria "Direito Constitucional"

  # 3. Salva sugestoes em arquivo JSON:
  python manage.py reorganizar_categorias_ia --dry_run --output sugestoes.json

  # 4. Aplica sugestoes de um arquivo revisado por voce:
  python manage.py reorganizar_categorias_ia --aplicar sugestoes.json
"""
import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from quiz.models import Categoria, Questao

logger = logging.getLogger(__name__)


PROMPT_HIERARQUIA = """Voce e especialista em taxonomia de conhecimento pra concursos publicos brasileiros.

Analise a categoria "{nome}" que hoje esta plana e tem os seguintes assuntos frequentes no banco:

{lista_assuntos}

Sua tarefa: propor uma hierarquia melhor de sub-categorias pra organizar essas questoes.

REGRAS:
- Cada assunto deve virar filho de exatamente 1 sub-categoria
- Sub-categorias devem agrupar assuntos que fazem sentido juntos
- Use 3 a 6 sub-categorias por categoria (nao muitas, nao poucas)
- Sub-categorias devem ter nomes CLAROS e PADRONIZADOS (usa nomenclatura oficial do concurso quando aplicavel)
- Se algum assunto ja e mais generico e virou "guarda-chuva" de outros, use ele como sub-categoria
- Se a categoria original ja e granular suficiente e nao precisa sub-dividir, retorne lista vazia em "sub_categorias"

Formato JSON estrito (sem markdown, sem texto antes/depois):
{{
  "raiz": "{nome}",
  "sub_categorias": [
    {{
      "nome": "Nome da sub-categoria 1",
      "assuntos_originais": ["assunto1", "assunto2", "assunto3"]
    }},
    {{
      "nome": "Nome da sub-categoria 2",
      "assuntos_originais": ["assunto4"]
    }}
  ]
}}
"""


class Command(BaseCommand):
    help = 'Sugere reorganizacao hierarquica de categorias via IA (baseado nos assuntos existentes).'

    def add_arguments(self, parser):
        parser.add_argument('--dry_run', action='store_true',
                            help='Analisa e imprime sugestao sem alterar BD')
        parser.add_argument('--categoria', type=str, default='',
                            help='Filtra so uma categoria (por nome)')
        parser.add_argument('--output', type=str, default='',
                            help='Salva sugestoes JSON num arquivo')
        parser.add_argument('--aplicar', type=str, default='',
                            help='Aplica sugestoes de um arquivo JSON previamente gerado')
        parser.add_argument('--min_assuntos', type=int, default=3,
                            help='Minimo de assuntos distintos pra sugerir sub-cats (default 3)')

    def handle(self, *args, **opts):
        if opts['aplicar']:
            return self._aplicar_sugestoes(opts['aplicar'])
        if not opts['dry_run']:
            raise CommandError(
                'Use --dry_run pra analisar ou --aplicar ARQUIVO.json pra executar sugestoes.'
            )
        self._analisar(opts)

    # ═══════════════════════════════════════════════════════════════════════
    def _analisar(self, opts):
        try:
            from quiz.ai_provider import gerar_conteudo
        except ImportError:
            raise CommandError('Nao consegui importar quiz.ai_provider.gerar_conteudo')

        cats_qs = Categoria.objects.filter(parent__isnull=True).order_by('nome')
        if opts['categoria']:
            cats_qs = cats_qs.filter(nome__iexact=opts['categoria'].strip())

        cats = list(cats_qs)
        if not cats:
            raise CommandError('Nenhuma categoria raiz encontrada.')

        self.stdout.write(self.style.HTTP_INFO(
            f'\nAnalisando {len(cats)} categoria(s) raiz...\n'
        ))

        todas_sugestoes = {'gerado_em': datetime.now().isoformat(),
                           'total_categorias': len(cats),
                           'sugestoes': []}

        for i, cat in enumerate(cats, 1):
            self.stdout.write(self.style.HTTP_INFO(
                f'[{i}/{len(cats)}] {cat.nome}...'
            ))

            # Coleta top assuntos dessa categoria
            assuntos_qs = (Questao.objects.filter(categoria=cat)
                           .exclude(assunto__isnull=True).exclude(assunto='')
                           .values('assunto')
                           .annotate(n=Count('id'))
                           .order_by('-n')[:40])
            assuntos = [(a['assunto'], a['n']) for a in assuntos_qs]

            n_distintos = len(assuntos)
            if n_distintos < opts['min_assuntos']:
                self.stdout.write(f'  Skip: apenas {n_distintos} assunto(s) distinto(s).')
                continue

            lista_str = '\n'.join([f'  - {nome} ({n}x)' for nome, n in assuntos])
            prompt = PROMPT_HIERARQUIA.format(nome=cat.nome, lista_assuntos=lista_str)

            try:
                resposta = gerar_conteudo(prompt, json_mode=True, max_tokens=2048)
                # Limpa markdown fences se IA errou
                import re as _re
                texto = _re.sub(r'^```(?:json)?\s*', '', resposta.strip())
                texto = _re.sub(r'\s*```$', '', texto)
                data = json.loads(texto)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  IA erro: {type(e).__name__}: {str(e)[:80]}'))
                continue

            sub_cats = data.get('sub_categorias', [])
            if not sub_cats:
                self.stdout.write('  IA sugere: manter plana (sem sub-categorias).')
                continue

            self.stdout.write(self.style.SUCCESS(
                f'  IA sugere {len(sub_cats)} sub-categoria(s):'
            ))
            for sc in sub_cats:
                nome = sc.get('nome', '?')
                assuntos_orig = sc.get('assuntos_originais', [])
                self.stdout.write(f'    • {nome} <- {len(assuntos_orig)} assunto(s)')

            todas_sugestoes['sugestoes'].append({
                'categoria_id': cat.id,
                'categoria_nome': cat.nome,
                'sub_categorias': sub_cats,
                'assuntos_originais_map': {a['assunto']: a['n'] for a in assuntos_qs},
            })

        # Salva se pediu output
        if opts['output']:
            path = Path(opts['output'])
            path.write_text(json.dumps(todas_sugestoes, ensure_ascii=False, indent=2),
                            encoding='utf-8')
            self.stdout.write(self.style.SUCCESS(
                f'\n✓ Sugestoes salvas em {path.absolute()}'
            ))
            self.stdout.write(
                f'  Revisa o JSON e roda: python manage.py reorganizar_categorias_ia --aplicar {path}'
            )
        else:
            self.stdout.write('\n' + '=' * 60)
            self.stdout.write(json.dumps(todas_sugestoes, ensure_ascii=False, indent=2))

    # ═══════════════════════════════════════════════════════════════════════
    def _aplicar_sugestoes(self, arquivo):
        path = Path(arquivo)
        if not path.exists():
            raise CommandError(f'Arquivo nao existe: {path}')

        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except Exception as e:
            raise CommandError(f'JSON invalido: {e}')

        sugestoes = data.get('sugestoes', [])
        if not sugestoes:
            self.stdout.write(self.style.WARNING('Nenhuma sugestao pra aplicar.'))
            return

        # Backup automatico
        backup_path = path.parent / f'backup_categorias_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        self._backup_estado_atual(backup_path)
        self.stdout.write(self.style.SUCCESS(f'✓ Backup em {backup_path.name}'))

        aplicadas = 0
        skipped = 0
        with transaction.atomic():
            for sug in sugestoes:
                cat_id = sug['categoria_id']
                try:
                    cat_pai = Categoria.objects.get(pk=cat_id)
                except Categoria.DoesNotExist:
                    self.stdout.write(self.style.WARNING(
                        f'  Skip cat #{cat_id}: nao existe mais.'
                    ))
                    skipped += 1
                    continue

                for sc in sug.get('sub_categorias', []):
                    nome_sub = sc.get('nome', '').strip()
                    assuntos = sc.get('assuntos_originais', [])
                    if not nome_sub or not assuntos:
                        continue

                    # Cria sub-categoria (ou pega se ja existe)
                    sub, criada = Categoria.objects.get_or_create(
                        nome=nome_sub, parent=cat_pai,
                    )
                    prefixo = '✚ Criada' if criada else '↻ Reusa'
                    self.stdout.write(f'  {prefixo}: {cat_pai.nome} > {nome_sub}')

                    # Move questoes: filtra por categoria=pai + assunto in lista
                    for assunto_str in assuntos:
                        movidas = (Questao.objects
                                   .filter(categoria=cat_pai, assunto__iexact=assunto_str.strip())
                                   .update(categoria=sub))
                        if movidas:
                            self.stdout.write(f'      ↳ {movidas} questao(oes) movidas de "{assunto_str}"')

                aplicadas += 1

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ {aplicadas} categoria(s) reorganizada(s), {skipped} skip.\n'
            f'  Backup em: {backup_path.name}'
        ))
        self.stdout.write(
            '  Pra reverter: restaura o backup manualmente ou apaga as sub-categorias criadas.'
        )

    # ═══════════════════════════════════════════════════════════════════════
    def _backup_estado_atual(self, path):
        """Salva snapshot de todas as categorias + Questao.categoria_id atual."""
        cats = list(Categoria.objects.values('id', 'nome', 'parent_id'))
        questoes = list(Questao.objects.values('id', 'categoria_id', 'assunto'))
        path.write_text(json.dumps({
            'gerado_em': datetime.now().isoformat(),
            'categorias': cats,
            'questoes': questoes,
        }, ensure_ascii=False, indent=2), encoding='utf-8')
