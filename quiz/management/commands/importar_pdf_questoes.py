"""
Importa questões de PDFs de provas/gabaritos oficiais.

Uso:
    # PDF com prova + gabarito juntos
    python manage.py importar_pdf_questoes --prova "C:/path/prova.pdf" --categoria "Enfermagem"

    # Prova + gabarito separados
    python manage.py importar_pdf_questoes \\
        --prova "C:/path/agente.pdf" \\
        --gabarito "C:/path/gab.pdf" \\
        --categoria "Direito Constitucional" \\
        --banca "Cebraspe"

    # Dry-run (mostra o que extraiu sem salvar)
    python manage.py importar_pdf_questoes --prova "..." --categoria "..." --dry_run
"""
import json
import re
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
import google.generativeai as genai
from pypdf import PdfReader

from quiz.models import Questao, Alternativa, Categoria


PROMPT_EXTRACAO = """Você está recebendo o TEXTO BRUTO de uma prova de concurso.
Extraia TODAS as questões que conseguir identificar e retorne em JSON.

REGRAS:
- Identifique questões numeradas (1, 2, 3... ou QUESTÃO 1, QUESTÃO 2...)
- Para questões de MÚLTIPLA ESCOLHA: capture todas as alternativas (A, B, C, D, E)
- Para questões CERTO/ERRADO (formato Cebraspe): tipo="CE", sem alternativas
- Quando o gabarito for fornecido, USE-O para marcar a alternativa correta
- Quando o gabarito NÃO for fornecido, marque a alternativa que parecer mais correta com `correta=true`
- Ignore textos de cabeçalho, rodapé, instruções
- IGNORE marcas d'água ("pcimarkpci", "www.pciconcursos.com.br", etc.)
- Para questões com base num texto inicial ("Considerando o texto acima..."), INCLUA o texto no enunciado

GABARITO FORNECIDO (use-o!):
{gabarito}

TEXTO DA PROVA:
====================
{texto}
====================

Retorne SOMENTE JSON válido, sem markdown:

[
  {{
    "numero": 1,
    "tipo": "ME",
    "texto": "Enunciado completo...",
    "alternativas": [
      {{"letra": "A", "texto": "...", "correta": false}},
      {{"letra": "B", "texto": "...", "correta": true}},
      {{"letra": "C", "texto": "...", "correta": false}},
      {{"letra": "D", "texto": "...", "correta": false}},
      {{"letra": "E", "texto": "...", "correta": false}}
    ],
    "assunto": "tópico inferido (opcional)"
  }},
  {{
    "numero": 2,
    "tipo": "CE",
    "texto": "Proposição certo/errado...",
    "resposta_ce": "C",
    "assunto": "..."
  }}
]
"""


class Command(BaseCommand):
    help = 'Extrai questões de PDFs de provas usando IA'

    def add_arguments(self, parser):
        parser.add_argument('--prova', type=str, required=True,
                            help='Caminho do PDF da prova')
        parser.add_argument('--gabarito', type=str, default='',
                            help='Caminho do PDF do gabarito (opcional)')
        parser.add_argument('--categoria', type=str, required=True,
                            help='Categoria onde salvar (deve existir)')
        parser.add_argument('--banca', type=str, default='',
                            help='Banca (Cebraspe, FGV, etc.)')
        parser.add_argument('--ano', type=int, default=None,
                            help='Ano da prova')
        parser.add_argument('--chunk_paginas', type=int, default=4,
                            help='Páginas por chamada à IA (default 4)')
        parser.add_argument('--model', type=str, default='gemini-3.1-flash-lite')
        parser.add_argument('--delay', type=float, default=3.0)
        parser.add_argument('--dry_run', action='store_true',
                            help='Mostra extração sem salvar')

    def handle(self, *args, **opts):
        api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            raise CommandError('GEMINI_API_KEY não configurada')

        prova_path = Path(opts['prova'])
        if not prova_path.exists():
            raise CommandError(f'Arquivo não encontrado: {prova_path}')

        try:
            categoria = Categoria.objects.get(nome__iexact=opts['categoria'])
        except Categoria.DoesNotExist:
            cats = ', '.join(Categoria.objects.values_list('nome', flat=True))
            raise CommandError(f'Categoria não existe. Disponíveis: {cats}')

        # ── Lê texto da prova ───────────────────────────────────────────────
        self.stdout.write(self.style.HTTP_INFO(f'\n▶ Lendo prova: {prova_path.name}'))
        texto_prova = self._extrair_pdf(prova_path)
        self.stdout.write(f'  {len(texto_prova)} caracteres, {texto_prova.count(chr(12))+1} páginas')

        # ── Lê gabarito (se houver) ─────────────────────────────────────────
        gabarito_texto = '(não fornecido — extraia o gabarito do próprio enunciado se possível)'
        if opts['gabarito']:
            gab_path = Path(opts['gabarito'])
            if not gab_path.exists():
                raise CommandError(f'Gabarito não encontrado: {gab_path}')
            self.stdout.write(self.style.HTTP_INFO(f'▶ Lendo gabarito: {gab_path.name}'))
            gabarito_texto = self._extrair_pdf(gab_path)[:6000]  # limita
            self.stdout.write(f'  {len(gabarito_texto)} chars')

        # ── Quebra a prova em chunks ────────────────────────────────────────
        chunks = self._quebrar_em_paginas(texto_prova, opts['chunk_paginas'])
        self.stdout.write(self.style.HTTP_INFO(
            f'\n▶ Dividindo em {len(chunks)} chunks para enviar à IA…\n'
        ))

        # ── Configura Gemini ────────────────────────────────────────────────
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(opts['model'])

        todas_questoes = []
        for idx, chunk in enumerate(chunks, 1):
            self.stdout.write(f'  Chunk {idx}/{len(chunks)} ({len(chunk)} chars)… ', ending='')
            self.stdout.flush()

            prompt = PROMPT_EXTRACAO.format(
                gabarito=gabarito_texto,
                texto=chunk,
            )
            try:
                resp = model.generate_content(prompt)
                bruto = (resp.text or '').strip()
                bruto = re.sub(r'^```(?:json)?\s*', '', bruto)
                bruto = re.sub(r'\s*```$', '', bruto)
                dados = json.loads(bruto)
                if isinstance(dados, list):
                    todas_questoes.extend(dados)
                    self.stdout.write(self.style.SUCCESS(f'+{len(dados)} questões'))
                else:
                    self.stdout.write(self.style.WARNING('não retornou lista'))
            except json.JSONDecodeError as e:
                self.stdout.write(self.style.WARNING(f'JSON inválido: {str(e)[:40]}'))
            except Exception as e:
                tipo_err = type(e).__name__
                if 'ResourceExhausted' in tipo_err or '429' in str(e):
                    self.stdout.write(self.style.WARNING('quota Gemini esgotada — encerrando'))
                    break
                self.stdout.write(self.style.WARNING(f'erro: {tipo_err}'))

            if opts['delay'] and idx < len(chunks):
                time.sleep(opts['delay'])

        if not todas_questoes:
            self.stdout.write(self.style.ERROR('\nNenhuma questão extraída.'))
            return

        # ── Resumo ──────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            f'\n✓ {len(todas_questoes)} questões extraídas no total'
        ))

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING('\n--dry_run: nada salvo. Amostra:\n'))
            for q in todas_questoes[:2]:
                self.stdout.write(f'  Nº{q.get("numero","?")} [{q.get("tipo","?")}] {q.get("texto","")[:100]}…')
            return

        # ── Salva no banco ──────────────────────────────────────────────────
        criadas, ignoradas = 0, 0
        with transaction.atomic():
            for q in todas_questoes:
                texto_q = (q.get('texto') or '').strip()
                if len(texto_q) < 20:
                    ignoradas += 1
                    continue

                # Dedupe rápido pelos 80 primeiros chars
                if Questao.objects.filter(
                    categoria=categoria,
                    texto__istartswith=texto_q[:80]
                ).exists():
                    ignoradas += 1
                    continue

                tipo = q.get('tipo', 'ME')
                obj = Questao.objects.create(
                    categoria=categoria,
                    texto=texto_q,
                    tipo=tipo,
                    justificativa='',  # importador não infere — IA pode adicionar depois
                    assunto=(q.get('assunto') or '')[:255] or None,
                    banca=opts['banca'] or None,
                    ano=opts['ano'],
                    revisada=False,
                    gerada_por_ia=True,
                )
                if tipo == 'ME':
                    for alt in q.get('alternativas') or []:
                        Alternativa.objects.create(
                            questao=obj,
                            texto=(alt.get('texto') or '').strip(),
                            correta=bool(alt.get('correta')),
                        )
                else:  # CE
                    resp_ce = (q.get('resposta_ce') or 'C').upper()
                    Alternativa.objects.create(questao=obj, texto='Certo', correta=(resp_ce == 'C'))
                    Alternativa.objects.create(questao=obj, texto='Errado', correta=(resp_ce == 'E'))
                criadas += 1

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ {criadas} novas questões salvas (pendentes de revisão)'
        ))
        if ignoradas:
            self.stdout.write(self.style.WARNING(f'⚠ {ignoradas} ignoradas (duplicadas ou texto curto)'))
        self.stdout.write(
            '\nRevise no /admin/quiz/questao/?revisada__exact=0&gerada_por_ia__exact=1'
        )

    # ── helpers ─────────────────────────────────────────────────────────────
    def _extrair_pdf(self, caminho):
        """Extrai texto do PDF e remove marcas d'água conhecidas."""
        reader = PdfReader(str(caminho))
        partes = []
        for pag in reader.pages:
            try:
                t = pag.extract_text() or ''
            except Exception:
                t = ''
            partes.append(t)
        texto = '\x0c'.join(partes)
        # Remove marcas d'água do PCI Concursos
        texto = re.sub(r'pcimarkpci\s+\S+', '', texto)
        texto = texto.replace('www.pciconcursos.com.br', '')
        return texto

    def _quebrar_em_paginas(self, texto, paginas_por_chunk):
        """Divide o texto em chunks de N páginas (marcador \\x0c)."""
        paginas = texto.split('\x0c')
        chunks = []
        for i in range(0, len(paginas), paginas_por_chunk):
            chunks.append('\n'.join(paginas[i:i + paginas_por_chunk]).strip())
        return [c for c in chunks if c]
