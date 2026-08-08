"""
Gera analises IA aprofundadas de concursos (edital comentado, tendencias,
comparativos, estrategia).

Complementa o hub /preparacao/<concurso>/ com conteudo denso e curado.

Uso:
    python manage.py gerar_analise_ia_concurso prf
    python manage.py gerar_analise_ia_concurso prf --tipo edital
    python manage.py gerar_analise_ia_concurso prf --tipo tendencias --force
    python manage.py gerar_analise_ia_concurso all
"""
import time
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from quiz.models import AnaliseConcursoIA
from quiz.preparacao import CONCURSO_DISCIPLINAS
from quiz.concurso_landing import CONCURSOS_LANDING


def _reconectar_db():
    """Reabre conexoes Postgres — Railway fecha durante chamadas IA longas."""
    for conn in connections.all():
        try:
            conn.close_if_unusable_or_obsolete()
            conn.ensure_connection()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass


TIPOS_VALIDOS = ['edital', 'tendencias', 'comparativo', 'estrategia', 'all']


PROMPTS = {
    'edital': lambda concurso, cfg: (
        f'Você é um professor especialista em preparação para o concurso {cfg["nome_completo"]}.\n\n'
        f'Gere um **edital comentado** em markdown, com 800-1200 palavras, cobrindo:\n\n'
        f'# 📋 Edital comentado — {cfg["nome"]}\n\n'
        f'## Visão geral\n'
        f'Contexto do concurso: cargo, atribuições, banca provável, salário aproximado, requisitos.\n\n'
        f'## Estrutura da prova\n'
        f'Fases (objetiva, discursiva, TAF, etc.), pesos, notas mínimas.\n\n'
        f'## Disciplinas do edital\n'
        f'Lista as {len(cfg["disciplinas"])} disciplinas: {", ".join(cfg["disciplinas"])}.\n'
        f'Para cada uma: peso estimado no edital + observações práticas.\n\n'
        f'## Bancas prováveis\n'
        f'{", ".join(cfg["bancas"])}. Estilo dominante de cada uma.\n\n'
        f'## Dicas de inscrição e preparação\n'
        f'Como se organizar 3, 6, 12 meses antes.\n\n'
        f'Português brasileiro, direto, sem jargão.'
    ),

    'tendencias': lambda concurso, cfg: (
        f'Você é um analista de concursos públicos com foco em {cfg["nome_completo"]}.\n\n'
        f'Gere uma **análise de tendências** em markdown, 600-900 palavras, sobre '
        f'o que MAIS caiu nas últimas edições do concurso {cfg["nome"]} e o que '
        f'tende a cair na próxima:\n\n'
        f'# 🎯 Tendências — {cfg["nome"]}\n\n'
        f'## Padrão histórico das últimas provas\n'
        f'Assuntos mais frequentes (últimas 3-5 edições). Peso relativo.\n\n'
        f'## Top 10 sub-tópicos quentes\n'
        f'Lista numerada com sub-tópicos MAIS cobrados nas disciplinas '
        f'{", ".join(cfg["disciplinas"][:4])}. Para cada:\n'
        f'- Sub-tópico\n'
        f'- Por que a banca gosta desse tema\n'
        f'- Como cai (tipo de questão)\n\n'
        f'## O que tende a cair no próximo edital\n'
        f'Baseado em atualizações legislativas recentes, decisões STF/STJ, '
        f'temas em alta social/política.\n\n'
        f'## Armadilhas comuns\n'
        f'3-5 pegadinhas típicas em {cfg["nome"]}.\n\n'
        f'Seja específico, cite artigos, leis, súmulas. Português brasileiro.'
    ),

    'comparativo': lambda concurso, cfg: (
        f'Compare as últimas 2-3 edições do concurso {cfg["nome_completo"]}.\n\n'
        f'Gere análise em markdown, 500-800 palavras:\n\n'
        f'# 📊 Comparativo entre edições — {cfg["nome"]}\n\n'
        f'## Evolução do edital\n'
        f'Como mudaram disciplinas, pesos, formato de prova entre edições recentes.\n\n'
        f'## Nível de dificuldade\n'
        f'Prova ficou mais fácil, mais difícil, ou estável? Por quê?\n\n'
        f'## Assuntos que ganharam peso\n'
        f'Tópicos que apareceram mais na última edição vs anteriores.\n\n'
        f'## Assuntos que perderam peso\n'
        f'Tópicos que sumiram ou reduziram frequência.\n\n'
        f'## Padrão de aprovação\n'
        f'Média histórica de aprovados, corte, concorrência.\n\n'
        f'Português brasileiro, dados concretos quando possível.'
    ),

    'estrategia': lambda concurso, cfg: (
        f'Elabore uma **estratégia de estudo** completa para o concurso {cfg["nome_completo"]}.\n\n'
        f'Formato markdown, 700-1000 palavras:\n\n'
        f'# ⚡ Estratégia de estudo — {cfg["nome"]}\n\n'
        f'## Plano de 3 meses\n'
        f'Mês 1: prioridades. Mês 2: aprofundamento. Mês 3: revisão + simulados.\n\n'
        f'## Plano de 6 meses\n'
        f'Distribuição de disciplinas por mês, foco progressivo.\n\n'
        f'## Plano de 12 meses\n'
        f'Estudo profundo por disciplina + revisão espaçada + simulados semanais.\n\n'
        f'## Distribuição semanal ideal\n'
        f'Quantas horas por disciplina por semana. Baseado nas disciplinas: '
        f'{", ".join(cfg["disciplinas"])}.\n\n'
        f'## Ordem sugerida das disciplinas\n'
        f'Priorização estratégica: quais estudar primeiro e por quê.\n\n'
        f'## Erros a evitar\n'
        f'5 armadilhas comuns na preparação.\n\n'
        f'Português brasileiro, prático e acionável.'
    ),
}


class Command(BaseCommand):
    help = 'Gera analises IA aprofundadas de concursos'

    def add_arguments(self, parser):
        parser.add_argument('concurso', type=str,
                            help='Slug do concurso (prf, pf, inss, ...) ou "all"')
        parser.add_argument('--tipo', type=str, default='all',
                            help=f'Tipo de analise: {", ".join(TIPOS_VALIDOS)}')
        parser.add_argument('--force', action='store_true',
                            help='Regera mesmo se ja existe (bump versao)')
        parser.add_argument('--dry_run', action='store_true')

    def handle(self, *args, **opts):
        concurso = opts['concurso'].lower().strip()
        tipo     = opts['tipo'].lower().strip()
        force    = opts['force']
        dry_run  = opts['dry_run']

        if tipo not in TIPOS_VALIDOS:
            raise CommandError(f'Tipo invalido. Opcoes: {TIPOS_VALIDOS}')

        if concurso == 'all':
            concursos = list(CONCURSOS_LANDING.keys())
        elif concurso in CONCURSOS_LANDING:
            concursos = [concurso]
        else:
            raise CommandError(f'Concurso "{concurso}" nao existe em CONCURSOS_LANDING')

        tipos_processar = ['edital', 'tendencias', 'comparativo', 'estrategia'] if tipo == 'all' else [tipo]

        criados = 0
        skipados = 0

        for c in concursos:
            cfg = CONCURSOS_LANDING[c]
            self.stdout.write(self.style.HTTP_INFO(f'\n═══ {cfg["nome"]} ({c}) ═══'))

            for t in tipos_processar:
                # Reconecta antes de cada iteracao (conexao pode ter morrido
                # apos ~10-30s de chamada IA anterior)
                _reconectar_db()
                existente = AnaliseConcursoIA.objects.filter(concurso=c, tipo=t).first()
                if existente and not force:
                    skipados += 1
                    self.stdout.write(f'  ⊘ {t}: ja existe (v{existente.versao})')
                    continue

                if dry_run:
                    self.stdout.write(f'  [DRY] Gerar {t} pra {cfg["nome"]}')
                    continue

                prompt = PROMPTS[t](c, cfg)
                try:
                    from quiz.ai_provider import gerar_conteudo
                    self.stdout.write(f'  → Gerando {t}...', ending='')
                    texto = gerar_conteudo(prompt, max_tokens=3000, temperature=0.5)
                    if not texto or len(texto) < 300:
                        self.stdout.write(self.style.ERROR(' FALHA (resposta muito curta)'))
                        continue

                    # Reconecta apos chamada IA longa antes de escrever no BD
                    _reconectar_db()
                    obj, criada = AnaliseConcursoIA.objects.update_or_create(
                        concurso=c, tipo=t,
                        defaults={
                            'conteudo_md': texto,
                            'versao': (existente.versao + 1) if existente else 1,
                        },
                    )
                    criados += 1
                    self.stdout.write(self.style.SUCCESS(
                        f' ✓ v{obj.versao} ({len(texto)} chars)'
                    ))
                    time.sleep(1.5)  # rate limit
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f' ERRO: {e}'))

        self.stdout.write('\n' + '═' * 60)
        self.stdout.write(self.style.SUCCESS(f'✓ {criados} analises geradas'))
        if skipados:
            self.stdout.write(self.style.WARNING(f'⊘ {skipados} skipadas (ja existiam, use --force)'))
