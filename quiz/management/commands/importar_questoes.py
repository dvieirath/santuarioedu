"""
Importa questoes de arquivo JSON estruturado com path hierarquico,
banca, ano e alternativas. Aproveita dedup automatico via texto_hash
(SHA-256 do enunciado normalizado — commit 9a5bfa8).

Formato do JSON:
[
  {
    "categoria_path": "Direito > Direito Constitucional > Principios Fundamentais",
    "banca": "TJ-AP",
    "ano": 2023,
    "tipo": "ME",
    "texto": "Enunciado completo...",
    "assunto": "Fundamentos da Republica" (opcional),
    "alternativas": [
      {"texto": "A", "correta": false},
      {"texto": "B", "correta": true},
      ...
    ]
  },
  {
    "categoria_path": "Direito > Direito Constitucional",
    "banca": "Cebraspe",
    "ano": 2018,
    "tipo": "CE",
    "texto": "Enunciado...",
    "resposta_ce": "C"  // ou "E"
  }
]

Uso:
    python manage.py importar_questoes arquivo.json
    python manage.py importar_questoes arquivo.json --dry_run
    python manage.py importar_questoes arquivo.json --revisada  # aprova ja
"""
import json
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quiz.models import Questao, Alternativa, Categoria


class Command(BaseCommand):
    help = 'Importa questoes de arquivo JSON com path hierarquico + banca/ano + dedup automatico'

    def add_arguments(self, parser):
        parser.add_argument('arquivo_json', type=str,
                            help='Caminho para o arquivo JSON com as questoes')
        parser.add_argument('--dry_run', action='store_true',
                            help='Preview do que sera importado, sem salvar')
        parser.add_argument('--revisada', action='store_true',
                            help='Marca questoes como revisada=True (aprovadas de imediato)')

    def handle(self, *args, **opts):
        arquivo = opts['arquivo_json']
        dry_run = opts['dry_run']
        ja_revisada = opts['revisada']

        if not os.path.exists(arquivo):
            raise CommandError(f'Arquivo nao encontrado: {arquivo}')

        with open(arquivo, 'r', encoding='utf-8') as f:
            try:
                dados = json.load(f)
            except json.JSONDecodeError as e:
                raise CommandError(f'JSON invalido: {e}')

        # Suporta tanto lista direta quanto {"questoes": [...]}
        if isinstance(dados, dict) and 'questoes' in dados:
            dados = dados['questoes']

        if not isinstance(dados, list):
            raise CommandError('JSON deve ser lista ou objeto com chave "questoes"')

        self.stdout.write(self.style.HTTP_INFO(
            f'\n═══ Importando {len(dados)} questoes de {arquivo} ═══'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY RUN] Nada sera salvo\n'))

        criadas = 0
        dup_hash = 0
        curtas = 0
        cat_nao_encontrada = 0
        sem_correta = 0
        erros = []

        # Cache de categorias pra evitar queries repetidas
        cache_cats = {}

        def _resolver_categoria(path):
            """Resolve path como 'Direito > Direito Constitucional > Principios'
            retornando a categoria folha. Cria ao longo do caminho se nao existir."""
            if path in cache_cats:
                return cache_cats[path]

            partes = [p.strip() for p in path.split('>')]
            parent = None
            for i, nome in enumerate(partes):
                cat = Categoria.objects.filter(
                    nome__iexact=nome, parent=parent,
                ).first()
                if not cat and not dry_run:
                    cat, _ = Categoria.objects.get_or_create(
                        nome=nome, parent=parent,
                    )
                if not cat and dry_run:
                    # Em dry_run, se nao existe, marca falha
                    return None
                parent = cat
            cache_cats[path] = parent
            return parent

        # Wrap em atomic — tudo ou nada
        with transaction.atomic():
            for idx, item in enumerate(dados, 1):
                categoria_path = item.get('categoria_path') or item.get('categoria', '')
                texto = (item.get('texto') or '').strip()
                tipo = item.get('tipo', 'ME').upper()
                banca = (item.get('banca') or '').strip()
                ano = item.get('ano')
                assunto = (item.get('assunto') or '').strip() or None
                alternativas = item.get('alternativas', [])
                resposta_ce = item.get('resposta_ce', '').upper()

                # Validacoes
                if not categoria_path or not texto:
                    erros.append(f'Item {idx}: categoria_path ou texto vazio')
                    continue

                if len(texto) < 30:
                    curtas += 1
                    continue

                cat = _resolver_categoria(categoria_path)
                if not cat:
                    cat_nao_encontrada += 1
                    erros.append(f'Item {idx}: categoria "{categoria_path}" nao existe')
                    continue

                # Dedup via texto_hash — auto-calculado no save() do model.
                # Aqui pre-checa antes de criar pra evitar query extra.
                from quiz.models import _hash_texto_questao
                h = _hash_texto_questao(texto)
                if h and Questao.objects.filter(texto_hash=h).exists():
                    dup_hash += 1
                    continue

                # Valida alternativas ME
                if tipo == 'ME':
                    if not alternativas:
                        erros.append(f'Item {idx}: ME sem alternativas')
                        continue
                    n_corretas = sum(1 for a in alternativas if a.get('correta'))
                    if n_corretas != 1:
                        sem_correta += 1
                        erros.append(
                            f'Item {idx}: ME deve ter EXATAMENTE 1 correta '
                            f'(tem {n_corretas})'
                        )
                        continue

                # Cria (se nao for dry_run)
                if dry_run:
                    self.stdout.write(
                        f'  [{idx}] ✓ {categoria_path[:50]}... '
                        f'({banca}/{ano}, {tipo})'
                    )
                    criadas += 1
                    continue

                obj = Questao.objects.create(
                    categoria=cat,
                    texto=texto,
                    tipo=tipo,
                    assunto=assunto,
                    banca=banca or None,
                    ano=ano if isinstance(ano, int) and 1990 <= ano <= 2030 else None,
                    revisada=ja_revisada,
                    gerada_por_ia=False,
                )

                if tipo == 'CE':
                    correta_c = resposta_ce in ('C', 'CERTO', 'V', 'VERDADEIRO')
                    Alternativa.objects.create(
                        questao=obj, texto='Certo', correta=correta_c,
                    )
                    Alternativa.objects.create(
                        questao=obj, texto='Errado', correta=not correta_c,
                    )
                else:  # ME
                    for alt in alternativas:
                        Alternativa.objects.create(
                            questao=obj,
                            texto=(alt.get('texto') or '').strip(),
                            correta=bool(alt.get('correta')),
                        )

                criadas += 1

            # Se dry_run, rollback
            if dry_run:
                transaction.set_rollback(True)

        # Relatorio
        self.stdout.write('\n' + '═' * 70)
        self.stdout.write(self.style.SUCCESS(
            f'✓ {criadas} {"seriam criadas" if dry_run else "criadas"}'
        ))
        if dup_hash:
            self.stdout.write(self.style.WARNING(
                f'⊘ {dup_hash} duplicatas por hash (ja existem no BD)'
            ))
        if curtas:
            self.stdout.write(self.style.WARNING(
                f'⊘ {curtas} texto muito curto (< 30 chars)'
            ))
        if cat_nao_encontrada:
            self.stdout.write(self.style.WARNING(
                f'⊘ {cat_nao_encontrada} categoria nao existe (dry_run apenas)'
            ))
        if sem_correta:
            self.stdout.write(self.style.ERROR(
                f'✗ {sem_correta} ME com quantidade errada de alternativas corretas'
            ))
        if erros and len(erros) <= 10:
            self.stdout.write(self.style.ERROR('\nErros detalhados:'))
            for e in erros:
                self.stdout.write(f'  {e}')
        elif erros:
            self.stdout.write(self.style.ERROR(f'\n{len(erros)} erros (primeiros 10):'))
            for e in erros[:10]:
                self.stdout.write(f'  {e}')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\n[DRY RUN] Nada foi salvo. Remova --dry_run pra executar.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\n✓ Aprove em /admin-revisao/ '
                f'{"(ja aprovadas com --revisada)" if ja_revisada else "(revisada=False por padrao)"}'
            ))
