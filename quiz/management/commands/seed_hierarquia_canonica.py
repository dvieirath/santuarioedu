"""
Estrutura hierarquica canonica de disciplinas de concursos publicos brasileiros.

Fluxo:
  1. Cria/atualiza a arvore de disciplinas (raizes + sub-topicos padrao)
  2. Move as categorias planas existentes pros lugares certos (mapping)
  3. Categorias sem mapeamento ficam onde estao (nao destroi nada)

Uso:
  # 1. Preview do que vai fazer:
  python manage.py seed_hierarquia_canonica --dry_run

  # 2. Aplicar:
  python manage.py seed_hierarquia_canonica --aplicar

  # 3. Preview apenas mapeamento (sem criar novos):
  python manage.py seed_hierarquia_canonica --dry_run --so_mapear
"""
import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quiz.models import Categoria, Questao


# ══════════════════════════════════════════════════════════════════════════════
# Arvore canonica: cada tupla eh (nome, [filhos...]).
# Baseada em editais reais de concursos brasileiros comuns (PRF, INSS, PF, ENEM,
# TJ, banca CESPE/Cebraspe padrao).
# ══════════════════════════════════════════════════════════════════════════════
ARVORE = [
    ('Linguagens e Códigos', [
        ('Língua Portuguesa', [
            'Gramática',
            'Interpretação de Texto',
            'Redação Oficial',
            'Concordância Verbal',
            'Concordância Nominal',
            'Regência',
            'Crase',
            'Pontuação',
            'Ortografia',
        ]),
        ('Literatura', []),
        ('Língua Estrangeira', [
            'Inglês',
            'Espanhol',
        ]),
    ]),

    ('Matemática e Raciocínio', [
        'Raciocínio Lógico',
        'Matemática Básica',
        'Estatística e Probabilidade',
        'Matemática Financeira',
    ]),

    ('Ciências Humanas', [
        'História',
        'Geografia',
        'Filosofia',
        'Sociologia',
        'Atualidades',
    ]),

    ('Ciências da Natureza', [
        ('Biologia', [
            'Anatomia Humana',
            'Fisiologia',
            'Genética',
            'Ecologia',
            'Botânica',
            'Zoologia',
            'Microbiologia',
        ]),
        ('Química', [
            'Química Geral',
            'Química Orgânica',
            'Físico-Química',
        ]),
        ('Física', [
            'Mecânica',
            'Termologia',
            'Eletromagnetismo',
            'Óptica',
        ]),
    ]),

    ('Direito', [
        'Direito Constitucional',
        'Direito Administrativo',
        'Direito Penal',
        'Direito Processual Penal',
        'Direito Civil',
        'Direito Processual Civil',
        'Direito Tributário',
        'Direito do Trabalho',
        'Direito Previdenciário',
        'Legislação de Trânsito',
    ]),

    ('Administração Pública', [
        'Administração Pública',
        'Ética no Serviço Público',
        'Gestão de Pessoas',
        'Administração Financeira',
    ]),

    ('Informática', [
        'Windows',
        'Pacote Office',
        'Segurança da Informação',
        'Redes de Computadores',
        'Banco de Dados',
        'Programação e Lógica',
    ]),

    ('Áreas Específicas', [
        'Medicina',
        'Enfermagem',
        'Psicologia Judiciária',
        'Análise de Sistemas',
        'Jornalismo',
        'Segurança Pública',
        'Operações de Laboratório',
        'Agente Administrativo',
    ]),

    ('Coleções por Concurso', [
        'Prova PRF',
        'ENEM',
        'INSS',
        'Polícia Federal',
        'TJ-DF',
    ]),
]

# Mapeamento das 24 categorias planas existentes -> caminho novo
# (chave = nome atual case-insensitive, valor = caminho completo separado por ' > ')
MAPEAMENTO_EXISTENTES = {
    'língua portuguesa':                'Linguagens e Códigos > Língua Portuguesa',
    'lingua portuguesa':                'Linguagens e Códigos > Língua Portuguesa',
    'raciocínio lógico e matemática':   'Matemática e Raciocínio > Raciocínio Lógico',
    'raciocinio logico e matematica':   'Matemática e Raciocínio > Raciocínio Lógico',
    'atualidades':                      'Ciências Humanas > Atualidades',
    'direito constitucional':           'Direito > Direito Constitucional',
    'direito administrativo':           'Direito > Direito Administrativo',
    'direito penal':                    'Direito > Direito Penal',
    'direito processual penal':         'Direito > Direito Processual Penal',
    'direito civil':                    'Direito > Direito Civil',
    'legislação de trânsito':           'Direito > Legislação de Trânsito',
    'legislacao de transito':           'Direito > Legislação de Trânsito',
    'administração pública':            'Administração Pública > Administração Pública',
    'administracao publica':            'Administração Pública > Administração Pública',
    'ética no serviço público':         'Administração Pública > Ética no Serviço Público',
    'etica no servico publico':         'Administração Pública > Ética no Serviço Público',
    'informática':                      'Informática',  # vira raiz mesmo
    'informatica':                      'Informática',
    'medicina':                         'Áreas Específicas > Medicina',
    'enfermagem':                       'Áreas Específicas > Enfermagem',
    'psicologia judiciária':            'Áreas Específicas > Psicologia Judiciária',
    'psicologia judiciaria':            'Áreas Específicas > Psicologia Judiciária',
    'análise de sistemas':              'Áreas Específicas > Análise de Sistemas',
    'analise de sistemas':              'Áreas Específicas > Análise de Sistemas',
    'jornalismo':                       'Áreas Específicas > Jornalismo',
    'segurança pública':                'Áreas Específicas > Segurança Pública',
    'seguranca publica':                'Áreas Específicas > Segurança Pública',
    'operações de laboratório':         'Áreas Específicas > Operações de Laboratório',
    'operacoes de laboratorio':         'Áreas Específicas > Operações de Laboratório',
    'agente administrativo':            'Áreas Específicas > Agente Administrativo',
    'conhecimentos específicos':        'Áreas Específicas',  # generica, deixa como raiz
    'conhecimentos especificos':        'Áreas Específicas',
    'conhecimentos gerais':             'Ciências Humanas > Atualidades',  # aproximado
    'prova prf':                        'Coleções por Concurso > Prova PRF',
    'enem':                             'Coleções por Concurso > ENEM',
}


class Command(BaseCommand):
    help = 'Cria estrutura hierarquica canonica + move categorias planas existentes.'

    def add_arguments(self, parser):
        parser.add_argument('--dry_run', action='store_true',
                            help='Preview sem aplicar')
        parser.add_argument('--aplicar', action='store_true',
                            help='Aplica de verdade (dentro de transaction.atomic)')
        parser.add_argument('--so_mapear', action='store_true',
                            help='So mostra o mapeamento, nao cria nova estrutura')

    def handle(self, *args, **opts):
        if not (opts['dry_run'] or opts['aplicar']):
            raise CommandError('Use --dry_run pra preview ou --aplicar pra executar.')

        aplicar = opts['aplicar']

        # Wrap em atomic pra rollback total se algo falhar no meio
        if aplicar:
            with transaction.atomic():
                self._executar(opts)
        else:
            self._executar(opts)

    def _executar(self, opts):
        aplicar = opts['aplicar']
        so_mapear = opts['so_mapear']

        # SNAPSHOT: captura IDs de raizes SEM FILHOS antes da FASE 1.
        # Heuristica: raiz canonica sempre tem filhos (definida em ARVORE).
        # "Legada" (categoria plana antiga) nao tem filhos ainda.
        # Isso evita FASE 2 tentar absorver raizes canonicas recem criadas
        # (bug antes do fix: absorvia raiz Adm Pub -> filhos viravam orfaos).
        raizes_legadas_ids = set(
            Categoria.objects.filter(parent__isnull=True, filhos__isnull=True)
            .values_list('id', flat=True).distinct()
        )

        # Fase 1: cria arvore canonica (idempotente via get_or_create)
        criadas_novas = []
        existentes = []

        if not so_mapear:
            self.stdout.write(self.style.HTTP_INFO('\n═══ FASE 1: Criando arvore canonica ═══'))
            for entrada in ARVORE:
                self._criar_no(entrada, parent=None, criadas=criadas_novas,
                               existentes=existentes, aplicar=aplicar, prefixo='')

        # Fase 2: mover SOMENTE categorias planas legadas (nao as canonicas criadas na FASE 1)
        self.stdout.write(self.style.HTTP_INFO('\n═══ FASE 2: Mapeando categorias existentes ═══'))
        movidas = 0
        skipped = 0
        nao_mapeadas = []

        for cat in Categoria.objects.filter(parent__isnull=True).order_by('nome'):
            # So processa categorias que ja eram raizes ANTES da FASE 1.
            # Raizes canonicas recem criadas nao devem ser tratadas como "plana legada".
            if cat.id not in raizes_legadas_ids:
                continue

            nome_lower = cat.nome.lower().strip()
            caminho_novo = MAPEAMENTO_EXISTENTES.get(nome_lower)

            if not caminho_novo:
                nao_mapeadas.append(cat.nome)
                continue

            partes = [p.strip() for p in caminho_novo.split('>')]

            # Caso 1: caminho = so 1 nivel, mesmo nome (ex: 'Informática' -> 'Informática')
            if len(partes) == 1 and partes[0].lower() == cat.nome.lower():
                skipped += 1
                self.stdout.write(f'  = {cat.nome} (mantido como raiz)')
                continue

            # Caso 2: caminho termina com o proprio nome (ex: 'Direito > Direito Constitucional')
            # -> mover cat como filha do path[-2]. Se pai ja tem filho com mesmo
            # nome (criado na FASE 1), ABSORVE.
            if partes[-1].lower() == cat.nome.lower():
                pai_path = ' > '.join(partes[:-1])
                if aplicar:
                    pai = self._buscar_por_caminho(partes[:-1])
                    if not pai:
                        self.stdout.write(self.style.ERROR(
                            f'  ⚠ {cat.nome} -> pai "{pai_path}" nao existe'
                        ))
                        continue

                    # Ja existe filho com mesmo nome (criado na FASE 1)? ABSORVE.
                    conflito = Categoria.objects.filter(
                        parent=pai, nome__iexact=cat.nome,
                    ).exclude(pk=cat.pk).first()
                    if conflito:
                        n = Questao.objects.filter(categoria=cat).update(categoria=conflito)
                        cat.delete()
                        self.stdout.write(self.style.SUCCESS(
                            f'  ↳ {cat.nome} -> ABSORVIDO por filho ja existente em "{pai_path}" ({n} questoes)'
                        ))
                    elif cat.parent_id != pai.id:
                        cat.parent = pai
                        cat.save(update_fields=['parent'])
                        self.stdout.write(self.style.SUCCESS(
                            f'  ↳ {cat.nome} -> filho de "{pai_path}"'
                        ))
                    else:
                        self.stdout.write(f'  = {cat.nome} (ja e filho de "{pai_path}")')
                else:
                    self.stdout.write(self.style.SUCCESS(
                        f'  ↳ {cat.nome} -> filho de "{pai_path}"'
                    ))
                movidas += 1
            else:
                # Caso 3: renomeacao (ex: 'Conhecimentos Gerais' -> 'Ciências Humanas > Atualidades')
                # Categoria antiga sera absorvida por 'Atualidades' — questoes movidas.
                self.stdout.write(self.style.SUCCESS(
                    f'  ↳ {cat.nome} -> absorvido por "{caminho_novo}" (questoes migradas)'
                ))
                if aplicar:
                    pai = self._buscar_por_caminho(partes[:-1])
                    destino, _ = Categoria.objects.get_or_create(
                        nome=partes[-1], parent=pai,
                    )
                    n = Questao.objects.filter(categoria=cat).update(categoria=destino)
                    cat.delete()
                    self.stdout.write(f'    → {n} questoes movidas, categoria antiga deletada')
                movidas += 1

        self.stdout.write(self.style.HTTP_INFO('\n═══ RESUMO ═══'))
        self.stdout.write(f'  Categorias criadas (novas): {len(criadas_novas)}')
        self.stdout.write(f'  Categorias ja existentes: {len(existentes)}')
        self.stdout.write(f'  Categorias movidas: {movidas}')
        self.stdout.write(f'  Categorias mantidas como estao: {skipped}')

        if nao_mapeadas:
            self.stdout.write(self.style.WARNING(
                f'\n  Nao mapeadas ({len(nao_mapeadas)}) — ficam onde estao:'
            ))
            for n in nao_mapeadas:
                self.stdout.write(f'    - {n}')

        if not aplicar:
            self.stdout.write(self.style.WARNING(
                '\n[DRY RUN] Nada foi salvo. Rode com --aplicar pra executar.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                '\n✓ Estrutura aplicada. Verifique em /admin/quiz/categoria/'
            ))

    def _criar_no(self, entrada, parent, criadas, existentes, aplicar, prefixo):
        """Cria um no da arvore recursivamente."""
        if isinstance(entrada, tuple):
            nome, filhos = entrada
        else:
            nome, filhos = entrada, []

        cat, criado = Categoria.objects.get_or_create(nome=nome, parent=parent) if aplicar else (
            self._buscar_por_caminho([nome] if parent is None else None), False
        )

        if aplicar:
            if criado:
                criadas.append(cat)
                self.stdout.write(self.style.SUCCESS(f'{prefixo}+ {nome}'))
            else:
                existentes.append(cat)
                self.stdout.write(f'{prefixo}= {nome}')
        else:
            self.stdout.write(f'{prefixo}? {nome}')

        for filho in filhos:
            self._criar_no(filho, parent=cat if aplicar else None,
                           criadas=criadas, existentes=existentes,
                           aplicar=aplicar, prefixo=prefixo + '  ')

    def _buscar_por_caminho(self, partes):
        """Busca categoria por caminho tipo ['Direito', 'Direito Constitucional']."""
        if not partes:
            return None
        cat = None
        for i, nome in enumerate(partes):
            cat = Categoria.objects.filter(
                nome__iexact=nome,
                parent=cat if i > 0 else None,
            ).first()
            if not cat:
                return None
        return cat
