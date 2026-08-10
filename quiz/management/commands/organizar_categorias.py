"""
Reorganiza estrutura de categorias hierarquicamente:

1. Consolida duplicatas por acento (Áreas Específicas / Areas Especificas)
2. Move disciplinas raiz pra sub-categorias apropriadas:
   - Historia, Geografia, Filosofia, Sociologia -> Ciencias Humanas
   - Biologia, Fisica, Quimica -> Ciencias da Natureza
   - Matematica, RLM, Estatistica/BI -> Matematica e Raciocinio
   - Portugues, Ingles, Espanhol, Redacao, Artes, Ed Fisica -> Linguagens e Codigos
   - Enfermagem, Eng Mecanica, Eng Eletrica, Materiais, Petroleo, Telecom,
     Programacao TI, Auditoria, Seguranca Trabalho, Contabilidade -> Areas Especificas
3. Deleta categorias vazias orfas
4. Padroniza nomes (usa forma com acento como canonica)

Idempotente. Uso:
    python manage.py organizar_categorias --dry_run
    python manage.py organizar_categorias
"""
from django.core.management.base import BaseCommand
from django.db import connections

from quiz.models import Categoria, Questao


def _reconectar_db():
    for conn in connections.all():
        try:
            conn.close_if_unusable_or_obsolete()
            conn.ensure_connection()
        except Exception:
            try: conn.close()
            except Exception: pass


# Grupos: (nome_raiz_pai, [nomes_de_filhas])
HIERARQUIA = {
    'Ciências Humanas': [
        'História', 'Geografia', 'Filosofia', 'Sociologia',
    ],
    'Ciências da Natureza': [
        'Biologia', 'Física', 'Química',
    ],
    'Matemática e Raciocínio': [
        'Matemática', 'Raciocínio Lógico', 'Estatística/BI',
    ],
    'Linguagens e Códigos': [
        'Português', 'Língua Portuguesa', 'Língua Inglesa', 'Língua Espanhola',
        'Redação', 'Artes', 'Educação Física',
    ],
    'Áreas Específicas': [
        'Enfermagem/Saúde', 'Engenharia/Mecanica', 'Engenharia Elétrica',
        'Materiais/Ligas', 'Petróleo/Refinaria', 'Telecomunicações',
        'Programação/TI', 'Auditoria/Controle', 'Segurança do Trabalho',
        'Contabilidade', 'Administração', 'Direito Militar/Segurança Pública',
    ],
}

# Duplicatas por acento (chave = canonico, valor = duplicatas pra merge)
DUPLICATAS = {
    'Áreas Específicas': ['Areas Especificas'],
    'Direito Previdenciário': ['Direito Previdenciario'],
    'Linguagens e Códigos': ['Linguagens e Codigos'],
}

# Categorias vazias/orfas pra deletar se sem questoes
DELETAR_SE_VAZIA = [
    'Administração Pública', 'Gestão de Pessoas', 'Nao Classificado',
    'Ética no Serviço Público', 'Matemática e Raciocínio',  # a raiz antiga tinha sub
]


class Command(BaseCommand):
    help = 'Reorganiza estrutura hierarquica de categorias'

    def add_arguments(self, parser):
        parser.add_argument('--dry_run', action='store_true')

    def handle(self, *args, **opts):
        dry_run = opts['dry_run']
        self.stdout.write(self.style.HTTP_INFO(
            f'\n═══ Reorganizar categorias {"(DRY RUN)" if dry_run else ""} ═══\n'
        ))

        # ── FASE 1: Consolidar duplicatas por acento ────────────────────
        self.stdout.write('FASE 1: Consolidar duplicatas por acento')
        for canonico, duplicatas in DUPLICATAS.items():
            _reconectar_db()
            cat_canonica = Categoria.objects.filter(nome=canonico).first()
            if not cat_canonica:
                # Cria a canonica
                if not dry_run:
                    cat_canonica, _ = Categoria.objects.get_or_create(nome=canonico, parent=None)
                self.stdout.write(f'  ✓ Criada categoria canonica: {canonico}')

            for dup_nome in duplicatas:
                _reconectar_db()
                dup = Categoria.objects.filter(nome=dup_nome).first()
                if not dup:
                    continue
                n_questoes = Questao.objects.filter(categoria=dup).count()
                n_filhas = Categoria.objects.filter(parent=dup).count()

                if dry_run:
                    self.stdout.write(f'  [DRY] Merge "{dup_nome}" -> "{canonico}" '
                                      f'({n_questoes} questoes, {n_filhas} filhas)')
                    continue

                # Move questoes
                if n_questoes:
                    Questao.objects.filter(categoria=dup).update(categoria=cat_canonica)
                # Move sub-categorias
                if n_filhas:
                    Categoria.objects.filter(parent=dup).update(parent=cat_canonica)
                # Delete duplicata
                dup.delete()
                self.stdout.write(self.style.SUCCESS(
                    f'  ✓ Merged "{dup_nome}" -> "{canonico}" ({n_questoes} questoes)'
                ))

        # ── FASE 2: Reorganizar em hierarquia ───────────────────────────
        self.stdout.write('\nFASE 2: Reorganizar em hierarquia')
        for pai_nome, filhas_nomes in HIERARQUIA.items():
            _reconectar_db()
            # Cria/pega pai
            if not dry_run:
                pai, _ = Categoria.objects.get_or_create(nome=pai_nome, parent=None)
            else:
                pai = Categoria.objects.filter(nome=pai_nome, parent=None).first()

            movidas = 0
            for filha_nome in filhas_nomes:
                _reconectar_db()
                filha = Categoria.objects.filter(nome=filha_nome, parent__isnull=True).first()
                if not filha:
                    # Talvez ja seja sub de outro
                    continue
                if not pai:
                    continue
                if filha.id == pai.id:
                    continue  # nao pode ser filha de si mesma

                n_questoes = Questao.objects.filter(categoria=filha).count()

                if dry_run:
                    self.stdout.write(f'  [DRY] "{filha_nome}" ({n_questoes} q) -> sob "{pai_nome}"')
                    continue

                filha.parent = pai
                filha.save(update_fields=['parent'])
                movidas += 1
                self.stdout.write(f'  ✓ {filha_nome} ({n_questoes} q) → sob {pai_nome}')

        # ── FASE 3: Deletar orfas vazias ────────────────────────────────
        self.stdout.write('\nFASE 3: Limpar categorias vazias')
        for nome in DELETAR_SE_VAZIA:
            _reconectar_db()
            cat = Categoria.objects.filter(nome=nome).first()
            if not cat:
                continue
            n_questoes = Questao.objects.filter(categoria=cat).count()
            n_filhas = Categoria.objects.filter(parent=cat).count()

            if n_questoes > 0 or n_filhas > 0:
                self.stdout.write(f'  ⊘ "{nome}" nao esta vazia ({n_questoes} q, {n_filhas} filhas), skip')
                continue

            if dry_run:
                self.stdout.write(f'  [DRY] Deletar "{nome}" (vazia)')
                continue

            cat.delete()
            self.stdout.write(self.style.SUCCESS(f'  ✓ Deletada "{nome}" (vazia)'))

        # ── FASE 4: Padronizar nomes (acentos, barras) ──────────────────
        renomeacoes = {
            'Engenharia/Mecanica':   'Engenharia Mecânica',
            'Estatística/BI':        'Estatística',
            'Materiais/Ligas':       'Materiais',
            'Petróleo/Refinaria':    'Petróleo',
            'Programação/TI':        'Programação',
            'Auditoria/Controle':    'Auditoria',
            'Enfermagem/Saúde':      'Enfermagem',
            'Direito Militar/Segurança Pública': 'Direito Militar',
        }
        self.stdout.write('\nFASE 4: Padronizar nomes')
        for antigo, novo in renomeacoes.items():
            _reconectar_db()
            cat = Categoria.objects.filter(nome=antigo).first()
            if not cat:
                continue
            # Ve se ja existe uma com novo nome
            existente = Categoria.objects.filter(nome=novo, parent=cat.parent).exclude(id=cat.id).first()
            if existente:
                # Merge
                if dry_run:
                    self.stdout.write(f'  [DRY] Merge "{antigo}" -> "{novo}" (existente)')
                    continue
                Questao.objects.filter(categoria=cat).update(categoria=existente)
                Categoria.objects.filter(parent=cat).update(parent=existente)
                cat.delete()
                self.stdout.write(f'  ✓ Merged "{antigo}" -> "{novo}"')
            else:
                if dry_run:
                    self.stdout.write(f'  [DRY] Rename "{antigo}" -> "{novo}"')
                    continue
                cat.nome = novo
                cat.save(update_fields=['nome'])
                self.stdout.write(f'  ✓ Renomeada "{antigo}" -> "{novo}"')

        # ── Snapshot final ──────────────────────────────────────────────
        _reconectar_db()
        self.stdout.write('\n' + '═' * 60)
        self.stdout.write('SNAPSHOT FINAL (raizes):')
        for c in Categoria.objects.filter(parent__isnull=True).order_by('nome'):
            n_diretas = Questao.objects.filter(categoria=c).count()
            filhas = list(Categoria.objects.filter(parent=c).values_list('nome', flat=True))
            n_arvore = Questao.objects.filter(categoria_id__in=c.subarvore_ids()).count()
            marker = f' [{len(filhas)} filhas]' if filhas else ''
            self.stdout.write(
                f'  {c.nome:35s} arvore={n_arvore:5d} diretas={n_diretas}{marker}'
            )
