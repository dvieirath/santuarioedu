"""
Gera em massa Resumos IA + Mapas Mentais pras disciplinas de um concurso.

Preenche gaps de materiais visiveis no hub /preparacao/<concurso>/.
Idempotente: skipa disciplinas que ja tem material.

Uso:
    python manage.py gerar_materiais_ia_concurso prf
    python manage.py gerar_materiais_ia_concurso inss --so_resumos
    python manage.py gerar_materiais_ia_concurso all  # todos os concursos
    python manage.py gerar_materiais_ia_concurso prf --dry_run
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
import time

from quiz.preparacao import CONCURSO_DISCIPLINAS, _match_categoria
from quiz.models import Categoria, ResumoIA, MapaMental


class Command(BaseCommand):
    help = 'Gera resumos IA + mapas mentais das disciplinas de um concurso'

    def add_arguments(self, parser):
        parser.add_argument('concurso', type=str,
                            help='Slug do concurso (prf, inss, tjdf, etc.) ou "all"')
        parser.add_argument('--so_resumos', action='store_true',
                            help='Gera apenas resumos IA (skip mapas)')
        parser.add_argument('--so_mapas', action='store_true',
                            help='Gera apenas mapas mentais (skip resumos)')
        parser.add_argument('--dry_run', action='store_true',
                            help='Mostra o que seria gerado, sem chamar IA')
        parser.add_argument('--sleep', type=float, default=1.0,
                            help='Segundos de sleep entre chamadas IA (evita rate limit)')

    def handle(self, *args, **opts):
        concurso   = opts['concurso'].lower().strip()
        so_resumos = opts['so_resumos']
        so_mapas   = opts['so_mapas']
        dry_run    = opts['dry_run']
        sleep_s    = opts['sleep']

        if concurso == 'all':
            concursos = list(CONCURSO_DISCIPLINAS.keys())
        elif concurso in CONCURSO_DISCIPLINAS:
            concursos = [concurso]
        else:
            raise CommandError(
                f'Concurso "{concurso}" nao reconhecido. Opcoes: '
                f'{", ".join(CONCURSO_DISCIPLINAS.keys())} ou "all"'
            )

        gerar_resumos = not so_mapas
        gerar_mapas   = not so_resumos

        total_criados = {'resumo': 0, 'mapa': 0}
        skipados      = {'resumo': 0, 'mapa': 0}

        for cslug in concursos:
            self.stdout.write(self.style.HTTP_INFO(
                f'\n═══ Processando concurso: {cslug} ═══'
            ))

            disciplinas = CONCURSO_DISCIPLINAS[cslug]
            for disc_nome in disciplinas:
                cats = _match_categoria(disc_nome)
                if not cats:
                    self.stdout.write(f'  ⊘ {disc_nome} — categoria nao encontrada, skip')
                    continue
                cat = cats[0]

                if gerar_resumos:
                    if ResumoIA.objects.filter(categoria=cat).exists():
                        skipados['resumo'] += 1
                        self.stdout.write(f'  ⊘ Resumo {cat.nome} — ja existe, skip')
                    else:
                        if dry_run:
                            self.stdout.write(f'  [DRY] Gerar RESUMO {cat.nome}')
                            total_criados['resumo'] += 1
                        else:
                            ok = self._gerar_resumo(cat, cslug)
                            if ok:
                                total_criados['resumo'] += 1
                                self.stdout.write(self.style.SUCCESS(
                                    f'  ✓ Resumo {cat.nome} gerado'
                                ))
                            else:
                                self.stdout.write(self.style.ERROR(
                                    f'  ✗ Resumo {cat.nome} — falha na IA'
                                ))
                            time.sleep(sleep_s)

                if gerar_mapas:
                    if MapaMental.objects.filter(categoria=cat).exists():
                        skipados['mapa'] += 1
                        self.stdout.write(f'  ⊘ Mapa {cat.nome} — ja existe, skip')
                    else:
                        if dry_run:
                            self.stdout.write(f'  [DRY] Gerar MAPA {cat.nome}')
                            total_criados['mapa'] += 1
                        else:
                            ok = self._gerar_mapa(cat, cslug)
                            if ok:
                                total_criados['mapa'] += 1
                                self.stdout.write(self.style.SUCCESS(
                                    f'  ✓ Mapa {cat.nome} gerado'
                                ))
                            else:
                                self.stdout.write(self.style.ERROR(
                                    f'  ✗ Mapa {cat.nome} — falha na IA'
                                ))
                            time.sleep(sleep_s)

        # Relatorio final
        self.stdout.write('\n' + '═' * 70)
        self.stdout.write(self.style.SUCCESS(
            f'✓ {total_criados["resumo"]} resumos + {total_criados["mapa"]} mapas '
            f'{"seriam gerados" if dry_run else "gerados"}'
        ))
        if skipados['resumo'] or skipados['mapa']:
            self.stdout.write(self.style.WARNING(
                f'⊘ Skips (ja existiam): {skipados["resumo"]} resumos + {skipados["mapa"]} mapas'
            ))

    def _gerar_resumo(self, cat, concurso):
        """Chama IA pra gerar resumo consolidado da disciplina."""
        from quiz.ai_provider import gerar_conteudo as gerar_com_fallback, AIError

        prompt = (
            f'Você é um professor especializado em concursos publicos. '
            f'Gere um resumo COMPLETO de estudo sobre "{cat.nome}" focado no '
            f'concurso {concurso.upper()}.\n\n'
            f'Estrutura obrigatória (use markdown):\n\n'
            f'# {cat.nome}\n\n'
            f'## 1. Introdução (2-3 paragrafos)\n'
            f'Contextualize a disciplina, sua relevancia pro concurso {concurso.upper()}, '
            f'peso tipico no edital.\n\n'
            f'## 2. Tópicos Fundamentais (5-8 tópicos)\n'
            f'Liste os assuntos mais cobrados. Para cada topico:\n'
            f'- **Conceito** (1 linha)\n'
            f'- **Como cai**: exemplo de questao tipica\n'
            f'- **Pegadinha**: armadilha comum\n\n'
            f'## 3. Legislação Aplicavel\n'
            f'Leis, artigos, sumulas relevantes com numeros exatos.\n\n'
            f'## 4. Estratégia de Estudo\n'
            f'Como estudar essa disciplina eficientemente pra {concurso.upper()}.\n\n'
            f'## 5. Erros Comuns\n'
            f'3-5 erros que os candidatos cometem.\n\n'
            f'Tamanho: 800-1200 palavras. Portugues brasileiro. Direto ao ponto.'
        )

        try:
            texto = gerar_com_fallback(prompt, max_tokens=2500, temperature=0.4)
            if not texto or len(texto) < 200:
                return False
            ResumoIA.objects.create(categoria=cat, conteudo=texto)
            return True
        except AIError:
            return False
        except Exception as e:
            self.stderr.write(f'    Erro inesperado: {e}')
            return False

    def _gerar_mapa(self, cat, concurso):
        """Chama IA pra gerar mapa mental Mermaid."""
        from quiz.ai_provider import gerar_conteudo as gerar_com_fallback, AIError

        prompt = (
            f'Gere um mapa mental em sintaxe Mermaid mindmap sobre "{cat.nome}" '
            f'pro concurso {concurso.upper()}.\n\n'
            f'Formato OBRIGATORIO — apenas o codigo Mermaid puro, sem markdown '
            f'wrappers, sem "```mermaid", sem explicacoes:\n\n'
            f'mindmap\n'
            f'  root(({cat.nome}))\n'
            f'    Ramo1\n'
            f'      subitem\n'
            f'      subitem\n'
            f'    Ramo2\n'
            f'      subitem\n'
            f'...\n\n'
            f'Requisitos:\n'
            f'- Root com nome exato "{cat.nome}"\n'
            f'- 5-8 ramos principais (topicos)\n'
            f'- 3-5 subitens por ramo\n'
            f'- Nomes curtos (max 30 chars por node)\n'
            f'- Foco nos assuntos que MAIS caem em {concurso.upper()}\n'
            f'- Sem caracteres especiais ({{}} [] () // que quebram Mermaid)'
        )

        try:
            texto = gerar_com_fallback(prompt, max_tokens=1500, temperature=0.5)
            if not texto or 'mindmap' not in texto.lower():
                return False
            # Limpa wrappers markdown que a IA as vezes coloca
            texto = texto.strip()
            if texto.startswith('```'):
                texto = texto.split('\n', 1)[-1]
                if texto.endswith('```'):
                    texto = texto.rsplit('```', 1)[0]
            texto = texto.strip()
            MapaMental.objects.create(categoria=cat, mermaid=texto)
            return True
        except AIError:
            return False
        except Exception as e:
            self.stderr.write(f'    Erro inesperado: {e}')
            return False
