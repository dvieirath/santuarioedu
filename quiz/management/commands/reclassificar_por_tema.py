"""
Reclassifica questoes que estao com categoria = nome de prova
(ex: "Prova TELEBRAS_25") em temas corretos (Direito Const, Adm, etc).

Estrategia hibrida:
1. Keywords Python (barato, ~70% dos casos)
2. Fallback IA pras que nao bateram score suficiente

Uso:
    python manage.py reclassificar_por_tema --dry_run          # preview
    python manage.py reclassificar_por_tema                    # roda
    python manage.py reclassificar_por_tema --categoria "Prova TELEBRAS_25"  # so uma
    python manage.py reclassificar_por_tema --usar_ia          # ativa fallback IA (mais lento)
"""
import time
import re
from django.core.management.base import BaseCommand
from django.db import transaction, connections

from quiz.models import Questao, Categoria


def _reconectar_db():
    for conn in connections.all():
        try:
            conn.close_if_unusable_or_obsolete()
            conn.ensure_connection()
        except Exception:
            try: conn.close()
            except Exception: pass


# Keywords por tema (case-insensitive, matches partial)
KEYWORDS = {
    'Direito Constitucional': [
        r'\bcf\b', r'constituição federal', r'constitucional',
        r'art\.?\s*5[°º]', r'art\.?\s*37', r'direitos fundamentais',
        r'\bstf\b', r'controle de constitucionalidade',
        r'\badi\b', r'\badc\b', r'\badpf\b',
        r'mandado de segurança', r'habeas corpus', r'habeas data',
        r'poder constituinte', r'principios fundamentais',
        r'organização do estado', r'poder legislativo', r'poder executivo',
        r'poder judiciario', r'poder judiciário', r'ministerio publico',
        r'ministério público', r'nacionalidade', r'direitos politicos',
        r'direitos políticos', r'ordem social', r'ordem econômica',
        r'defensor publico', r'defensor público',
    ],
    'Direito Administrativo': [
        r'licitação', r'licitações', r'\blei 8\.?666\b', r'\blei 14\.?133\b',
        r'servidor publico', r'servidor público', r'servidores publicos',
        r'processo administrativo', r'\blei 9\.?784\b',
        r'ato administrativo', r'atos administrativos',
        r'poder de policia', r'poder de polícia',
        r'agente publico', r'agente público',
        r'improbidade administrativa', r'\blei 8\.?429\b',
        r'concessão', r'permissão', r'autorização',
        r'organizacao administrativa', r'organização administrativa',
        r'autarquia', r'fundacao publica', r'fundação pública',
        r'empresa publica', r'sociedade de economia mista',
        r'desapropriação', r'servidão',
    ],
    'Direito Penal': [
        r'\bcp\b(?!,)', r'código penal', r'codigo penal',
        r'crime', r'crimes', r'pena', r'contravenção',
        r'dolo', r'culpa', r'excludente', r'imputabilidade',
        r'concurso de pessoas', r'concurso de crimes',
        r'flagrante', r'\bdecreto-lei 2\.?848\b',
        r'furto', r'roubo', r'homicidio', r'homicídio',
        r'estelionato', r'lesão corporal',
    ],
    'Direito Processual Penal': [
        r'processo penal', r'\bcpp\b', r'código de processo penal',
        r'inquerito policial', r'inquérito policial',
        r'prisão preventiva', r'prisao preventiva', r'prisão temporária',
        r'medidas cautelares', r'\bdecreto-lei 3\.?689\b',
    ],
    'Direito Civil': [
        r'código civil', r'codigo civil', r'\bcc\b(?!,)',
        r'contratos', r'contrato de', r'obrigação', r'obrigações',
        r'\blei 10\.?406\b', r'direito de familia', r'direito de família',
        r'sucessões', r'sucessão', r'usucapião', r'usucapiao',
        r'responsabilidade civil', r'personalidade juridica',
        r'personalidade jurídica', r'coisa julgada',
    ],
    'Direito Processual Civil': [
        r'\bcpc\b', r'código de processo civil', r'processo civil',
        r'\blei 13\.?105\b', r'petição inicial', r'petição',
        r'sentença', r'agravo', r'apelação', r'recurso especial',
        r'recurso extraordinario', r'recurso extraordinário',
        r'coisa julgada', r'jurisdição',
    ],
    'Direito Tributário': [
        r'tributário', r'tributario', r'\bctn\b', r'código tributário',
        r'imposto', r'taxa', r'contribuição de melhoria',
        r'obrigação tributária', r'lançamento tributário',
        r'\blei 5\.?172\b', r'fato gerador',
    ],
    'Direito Previdenciário': [
        r'previdenciário', r'previdenciario', r'\binss\b',
        r'aposentadoria', r'pensão', r'benefício previdenciário',
        r'\blei 8\.?213\b', r'\blei 8\.?212\b', r'segurado',
        r'auxilio-doenca', r'auxílio-doença', r'salario-maternidade',
    ],
    'Direito do Trabalho': [
        r'\bclt\b', r'consolidação das leis do trabalho',
        r'contrato de trabalho', r'empregador', r'empregado',
        r'jornada de trabalho', r'ferias', r'férias', r'fgts',
        r'aviso previo', r'aviso prévio', r'demissão',
    ],
    'Direito Ambiental': [
        r'ambiental', r'meio ambiente', r'\blei 6\.?938\b',
        r'sisnama', r'conama', r'poluição', r'poluicao',
        r'licenciamento ambiental',
    ],
    'Português': [
        r'coesão', r'coesao', r'coerência', r'coerencia',
        r'concordância', r'concordancia', r'regência', r'regencia',
        r'crase', r'ortografia', r'pontuação',
        r'período composto', r'oração subordinada', r'sujeito',
        r'predicado', r'tempo verbal', r'figura de linguagem',
    ],
    'Raciocínio Lógico': [
        r'proposição', r'proposicao', r'silogismo',
        r'conjunção', r'disjunção', r'implicação lógica',
        r'tabela verdade', r'quantificador', r'argumento válido',
        r'\bmatemática\b', r'\bmatematica\b',
    ],
    'Informática': [
        r'windows', r'excel', r'word', r'powerpoint',
        r'internet', r'firewall', r'antivirus', r'antivírus',
        r'sistema operacional', r'navegador', r'browser',
        r'planilha eletronica', r'planilha eletrônica',
        r'hardware', r'software', r'protocolo tcp',
        r'lgpd', r'seguran[çc]a da informação',
    ],
    'Legislação de Trânsito': [
        r'\bctb\b', r'código de tr[âa]nsito', r'trânsito', r'transito',
        r'\bcnh\b', r'motorista', r'condutor', r'via', r'infração',
        r'\blei 9\.?503\b',
    ],
    'Atualidades': [
        r'atualidades', r'brasil contemporâneo', r'geopolitica',
        r'geopolítica', r'sociedade brasileira',
    ],
}

# Prefixo "Prova " indica categoria a reclassificar
CATS_PROVA_PREFIX = 'Prova '


def classificar_por_keywords(texto):
    """
    Retorna (tema, score) baseado em matches de keywords.
    Score = numero de matches (mais alto = mais confianca).
    """
    if not texto:
        return None, 0
    texto_lower = texto.lower()
    scores = {}
    for tema, kws in KEYWORDS.items():
        n = 0
        for kw in kws:
            if re.search(kw, texto_lower):
                n += 1
        if n > 0:
            scores[tema] = n
    if not scores:
        return None, 0
    tema = max(scores, key=scores.get)
    return tema, scores[tema]


class Command(BaseCommand):
    help = 'Reclassifica questoes com categoria=nome de prova em temas corretos'

    def add_arguments(self, parser):
        parser.add_argument('--dry_run', action='store_true')
        parser.add_argument('--categoria', type=str, default=None,
                            help='Rodar so nessa categoria (ex: "Prova TELEBRAS_25")')
        parser.add_argument('--usar_ia', action='store_true',
                            help='Fallback IA pras questoes com score < 2 keywords')
        parser.add_argument('--min_score', type=int, default=2,
                            help='Score minimo de keywords pra aceitar (default 2)')
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **opts):
        dry_run = opts['dry_run']
        categoria_alvo = opts['categoria']
        usar_ia = opts['usar_ia']
        min_score = opts['min_score']
        limit = opts['limit']

        qs = Questao.objects.filter(
            categoria__nome__startswith=CATS_PROVA_PREFIX,
        ).select_related('categoria')

        if categoria_alvo:
            qs = qs.filter(categoria__nome=categoria_alvo)

        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(self.style.HTTP_INFO(
            f'\n═══ {total} questoes pra reclassificar '
            f'{"(DRY RUN)" if dry_run else ""} ═══\n'
        ))

        # Cache de categorias-tema (evita query repetida)
        cache_cats = {}

        def _get_cat_tema(nome):
            if nome in cache_cats:
                return cache_cats[nome]
            # Tenta match em qualquer nivel (raiz ou sub)
            cat = Categoria.objects.filter(nome__iexact=nome).first()
            if not cat and not dry_run:
                # Cria no primeiro nivel abaixo da raiz "Direito" se apropriado
                if any(k in nome.lower() for k in ('direito', 'processual')):
                    parent = Categoria.objects.filter(nome__iexact='Direito', parent__isnull=True).first()
                    if parent:
                        cat, _ = Categoria.objects.get_or_create(nome=nome, parent=parent)
            if not cat and not dry_run:
                cat, _ = Categoria.objects.get_or_create(nome=nome, parent=None)
            cache_cats[nome] = cat
            return cat

        stats = {
            'reclassificadas': 0,
            'ia_usada':        0,
            'sem_classificacao': 0,
            'por_tema':        {},
        }

        # Processa em batches pra reconectar Postgres
        BATCH = 100
        ids = list(qs.values_list('id', flat=True))

        for i in range(0, len(ids), BATCH):
            _reconectar_db()
            batch_ids = ids[i:i+BATCH]

            for q_id in batch_ids:
                q = Questao.objects.filter(id=q_id).first()
                if not q:
                    continue

                tema, score = classificar_por_keywords(q.texto)

                # Fallback IA se score baixo
                if (tema is None or score < min_score) and usar_ia:
                    tema_ia = self._classificar_ia(q.texto)
                    if tema_ia:
                        tema = tema_ia
                        score = min_score
                        stats['ia_usada'] += 1

                if tema is None:
                    stats['sem_classificacao'] += 1
                    continue

                stats['por_tema'][tema] = stats['por_tema'].get(tema, 0) + 1
                stats['reclassificadas'] += 1

                if dry_run:
                    continue

                # Reassigna categoria
                cat = _get_cat_tema(tema)
                if cat:
                    q.categoria = cat
                    q.save(update_fields=['categoria'])

            self.stdout.write(
                f'  → Lote {min(i+BATCH, len(ids))}/{len(ids)} · '
                f'{stats["reclassificadas"]} reclassificadas'
            )

        # Relatorio
        self.stdout.write('\n' + '═' * 60)
        self.stdout.write(self.style.SUCCESS(
            f'✓ {stats["reclassificadas"]} reclassificadas'
        ))
        if stats['ia_usada']:
            self.stdout.write(f'  → {stats["ia_usada"]} via IA (fallback)')
        if stats['sem_classificacao']:
            self.stdout.write(self.style.WARNING(
                f'⊘ {stats["sem_classificacao"]} sem match (score < {min_score})'
            ))
        self.stdout.write('\nPor tema:')
        for tema, n in sorted(stats['por_tema'].items(), key=lambda x: -x[1]):
            self.stdout.write(f'  {tema:40s} {n}')

    def _classificar_ia(self, texto):
        """Fallback IA — pede tema em 1 palavra."""
        prompt = (
            'Classifique a questao abaixo em UM UNICO tema. Responda APENAS o nome '
            f'do tema (uma das opcoes: {", ".join(KEYWORDS.keys())}). '
            'Sem explicacao, sem markdown, so o nome exato.\n\n'
            f'QUESTAO: {texto[:1500]}'
        )
        try:
            from quiz.ai_provider import gerar_conteudo
            resp = gerar_conteudo(prompt, max_tokens=30, temperature=0.1)
            resp = resp.strip().replace('"', '').replace("'", '')
            # Tenta match com KEYWORDS keys
            for tema in KEYWORDS.keys():
                if tema.lower() in resp.lower() or resp.lower() in tema.lower():
                    return tema
            return None
        except Exception:
            return None
