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
    # ─── Disciplinas gerais (ENEM/vestibular/professor) ────────────────
    'Matemática': [
        r'\bequação', r'inequação', r'função quadrática', r'função exponencial',
        r'polinômio', r'\btrigonometria', r'\bseno\b', r'\bcosseno\b', r'\btangente\b',
        r'\bmatriz\b', r'\bdeterminante', r'\bvetor', r'geometria analitica',
        r'geometria analítica', r'geometria plana', r'geometria espacial',
        r'\bprogressão\b', r'\baritmética\b', r'\bgeométrica\b',
        r'\blogaritmo', r'derivada', r'integral', r'limite',
        r'\bnúmero\s+complexo', r'\bfatorial\b', r'\bcombinatória',
        r'\bprobabilidade', r'\bestatística', r'\bmédia\b', r'\bmediana\b',
        r'\bvariância', r'desvio padrão',
    ],
    'Física': [
        r'\bcinemática', r'\bmovimento\s+(uniforme|acelerado|circular)',
        r'\bvelocidade', r'\baceleração', r'\bforça\b',
        r'\benergia\s+(cinética|potencial|mecânica|térmica|elétrica)',
        r'\bpotência\b', r'\btrabalho\s+mecânico', r'\bcalor\b',
        r'\btermodinâmica', r'\bondas\b', r'\bfrequência', r'\bamplitude',
        r'\bótica\b', r'\bespelho', r'\blente', r'\brefração',
        r'\beletromagnetismo', r'\bcorrente elétrica', r'\btensão',
        r'\bresistor', r'\bcapacitor', r'\bcircuito', r'\bcampo elétrico',
        r'\bcampo magnético', r'\bfísica\b',
    ],
    'Química': [
        r'\btabela periódica', r'\breação química', r'\breações químicas',
        r'\bequação química', r'\bligação\s+(iônica|covalente|metálica)',
        r'\betoma\b', r'\bmolécula', r'\bion\b', r'\bíon\b',
        r'\boxidação', r'\bredução', r'\bácido\b', r'\bbase\b',
        r'\bpH\b', r'\bsolução\s+(molar|aquosa)', r'\bconcentração',
        r'\bpolímero', r'\bhidrocarboneto', r'\borgânica', r'\binorgânica',
        r'\bestequiometria', r'\btermo?química', r'\bcinética química',
        r'\beletroquímica', r'\bquímica\b',
    ],
    'Biologia': [
        r'\bcélula\b', r'\bcelular', r'\bmitocôndria', r'\bribossomo',
        r'\bnúcleo\s+celular', r'\bmembrana\s+plasmática', r'\bDNA\b',
        r'\bRNA\b', r'\bgene\b', r'\bcromossomo', r'\bgenética',
        r'\bhereditariedade', r'\bmendel', r'\bevolução\s+(biológica|das espécies)',
        r'\bdarwin', r'\bmutação', r'\bseleção natural',
        r'\becologia', r'\becossistema', r'\bcadeia alimentar',
        r'\bbioma\b', r'\bfotossíntese', r'\brespiração celular',
        r'\bfermentação', r'\bmetabolismo', r'\btecido\s+(epitelial|nervoso|muscular)',
        r'\bsistema\s+(digestório|circulatório|respiratório|nervoso|imune)',
        r'\bvírus\b', r'\bbactéria', r'\bfungos?\b', r'\bprotozoário',
        r'\banatomia', r'\bfisiologia', r'\bbiologia\b',
    ],
    'História': [
        r'\bimpério\s+(romano|bizantino|islâmico|otomano|colonial)',
        r'\bidade\s+(antiga|média|moderna|contemporânea)',
        r'\brenascimento', r'\biluminismo', r'\brevolução\s+(francesa|industrial|russa|americana)',
        r'\bcolonização', r'\bindependência\s+(do brasil|dos eua)',
        r'\bregime\s+(militar|imperial|republicano)', r'\bditadura\s+militar',
        r'\bgetúlio\s+vargas', r'\bestado novo', r'\bera vargas',
        r'\brepública\s+(velha|nova)', r'\bimpério\s+brasileiro',
        r'\bguerra\s+(mundial|fria|civil|do paraguai|de canudos)',
        r'\bnazismo', r'\bfascismo', r'\bcomunismo', r'\bsocialismo',
        r'\bcapitalismo', r'\bséculo\s+(XIX|XVIII|XVII|XVI|XV|XX|XXI)',
        r'\bhistória\s+(do brasil|geral|antiga|contemporânea)',
    ],
    'Geografia': [
        r'\brelevo\b', r'\bclima\s+(tropical|temperado|equatorial|árido)',
        r'\bvegetação', r'\bhidrografia', r'\bbacia\s+hidrográfica',
        r'\bcontinente\b', r'\bocean(o|ico)', r'\bfuso horário',
        r'\bcapital\s+(federal|do brasil|do estado)',
        r'\bpopulação\s+(brasileira|mundial)', r'\bdemografia',
        r'\burbanização', r'\bmigração', r'\bglobalização',
        r'\bregião\s+(norte|nordeste|sul|sudeste|centro-oeste)',
        r'\bproduto interno bruto', r'\bPIB\b', r'\bIDH\b',
        r'\bimperialismo', r'\bcolonialismo', r'\bgeografia\b',
        r'\bcartografia', r'\bescala\s+(cartográfica|numérica)',
    ],
    'Filosofia': [
        r'\bfilosofia', r'\bfilósofo', r'\bética\b', r'\bmoral\b',
        r'\bmetafísica', r'\bepistemologia', r'\bconhecimento\s+empírico',
        r'\bconhecimento\s+racional', r'\bsócrates', r'\bplatão',
        r'\baristóteles', r'\bkant\b', r'\bhegel', r'\bnietzsche',
        r'\bdescartes', r'\bhume\b', r'\bmarx\b', r'\bfoucault',
        r'\bexistencialismo', r'\bfenomenologia', r'\bidealismo',
        r'\bempirismo', r'\bracionalismo',
    ],
    'Sociologia': [
        r'\bsociologia', r'\bclasses?\s+sociais?', r'\bdurkheim',
        r'\bweber\b', r'\bmovimento social', r'\bindústria cultural',
        r'\bglobalização\s+cultural', r'\bidentidade\s+cultural',
        r'\bfamília\b', r'\bcidadania', r'\bdesigualdade\s+social',
        r'\bmulticulturalismo', r'\bpreconceito\s+racial', r'\bfeminismo',
        r'\bmovimento\s+(negro|feminista|lgbt)',
    ],
    'Língua Espanhola': [
        r'\blíngua\s+espanhola', r'\bidioma\s+espanhol', r'\bcastellano',
        r'\bcastelhano', r'\btraduza\s+para\s+o\s+espanhol',
        r'\bacento\s+(agudo|grave)\s+em\s+espanhol',
    ],
    'Língua Inglesa': [
        r'\blíngua\s+inglesa', r'\bidioma\s+inglês', r'\breading comprehension',
        r'\baccording to the text', r'\bthe following text',
    ],
    'Artes': [
        r'\bartes\s+(visuais|cênicas)', r'\bhistória\s+da arte', r'\brenascimento\s+artístico',
        r'\bbarroco\b', r'\bmodernismo\s+brasileiro', r'\bsemana\s+de arte moderna',
        r'\bpicasso', r'\bvan gogh', r'\bmona lisa', r'\btarsila do amaral',
        r'\bportinari', r'\basi', r'\bestética\b', r'\bcubismo', r'\bimpressionismo',
    ],
    'Educação Física': [
        r'\beducação\s+física', r'\bmusculação', r'\btreinamento\s+esportivo',
        r'\bcoordenação\s+motora', r'\baptidão\s+física',
        r'\besporte\s+(coletivo|individual|olímpico)',
        r'\bmodalidades?\s+esportivas', r'\bcondicionamento físico',
    ],
    'Redação': [
        r'\bredação', r'\bdissertação\s+(argumentativa)?',
        r'\btese\s+e\s+argumentos', r'\bcoesão\s+textual',
        r'\bcoerência\s+textual', r'\bconclusão\s+da\s+redação',
        r'\btexto\s+dissertativo',
    ],
    'Legislação Educacional': [
        r'\bLDB\b', r'\blei\s+de\s+diretrizes', r'\blei\s+9\.394',
        r'\bPCN\b', r'\bBNCC\b', r'\bplano nacional de educação',
        r'\beducação\s+básica', r'\beducação\s+infantil', r'\bensino\s+fundamental',
        r'\bensino\s+médio', r'\bmec\b',
    ],
    'Contabilidade': [
        r'\bcontabilidade', r'\bcontabil', r'\bdemonstração\s+(contábil|financeira)',
        r'\bbalanço\s+patrimonial', r'\bDRE\b', r'\bdemonstração de resultado',
        r'\bativo\s+(circulante|não\s+circulante)', r'\bpassivo\s+circulante',
        r'\bpatrimônio\s+líquido', r'\bregime\s+de\s+competência',
    ],
    'Administração': [
        r'\badministração\s+(pública|geral)', r'\bteoria\s+da\s+administração',
        r'\bgestão\s+(estratégica|de pessoas|financeira|de projetos)',
        r'\bplanejamento\s+estratégico', r'\bplanejamento\s+organizacional',
        r'\bliderança\b', r'\bmotivação', r'\bcultura\s+organizacional',
        r'\bmintzberg', r'\btaylor\b', r'\bfayol\b', r'\bmaslow',
    ],
    'Enfermagem/Saúde': [
        r'\benfermag(em|eiro)', r'\bcuidados de\s+enfermagem',
        r'\bpaciente\s+(hospitalar|internado)', r'\bSUS\b', r'\bsistema único de saúde',
        r'\batenção\s+primária', r'\bhipertensão', r'\bdiabetes\b',
        r'\bdoença\s+(crônica|infecciosa|contagiosa)', r'\bvacina',
        r'\bantibiótico', r'\bfarmacologia',
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
        parser.add_argument('--min_score', type=int, default=1,
                            help='Score minimo de keywords pra aceitar (default 1)')
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
