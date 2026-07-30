"""
Extrai figuras de PDFs com precisao usando Gemini Vision + PyMuPDF crop.

Fluxo (por pagina):
1. PyMuPDF renderiza pagina como PNG 200 DPI (captura vetores + tudo visual)
2. Gemini Vision analisa a pagina e retorna, pra cada figura:
     - question_text_snippet (primeiros ~80 chars da questao que a referencia)
     - bbox em % da pagina [x0, y0, x1, y1]
3. PyMuPDF crop a regiao do PDF ORIGINAL (nao da imagem renderizada — melhor qualidade)
4. Fuzzy match do snippet contra Questao.texto no BD (mesmo banca+ano)
5. Salva no ImageField — django-storages faz upload pro R2 automatico

Uso:
    python manage.py extrair_figuras_vision --arquivo provas_pdf/processados/cespe_prf_2013.pdf
    python manage.py extrair_figuras_vision --pasta provas_pdf/processados/
    python manage.py extrair_figuras_vision --arquivo ... --dry_run

Requer:
    - GEMINI_API_KEY configurada
    - PyMuPDF (fitz) instalado
    - AWS_* configurada (django-storages -> R2) pra upload de prod
"""
import io
import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

import fitz  # PyMuPDF

from quiz.models import Questao


PROMPT_FIGURAS = """Voce esta vendo a IMAGEM de uma pagina de prova de concurso publico brasileiro.
Identifique TODAS as figuras/graficos/tabelas/mapas visualmente relevantes nesta pagina.

Para cada elemento visual encontrado, retorne:
- question_text_snippet: os PRIMEIROS ~80 chars do enunciado da questao que referencia essa figura
  (copie textualmente da pagina, sem traduzir/parafrasear)
- description: descricao curta do que a figura mostra (1 frase)
- bbox: [x0, y0, x1, y1] em PERCENTUAIS da pagina (0-100)
  ex: [10, 20, 60, 50] = comeca 10% da esquerda, 20% do topo, vai ate 60% e 50%

IGNORE:
- Cabecalhos, rodapes, marcas d'agua (PCI Concursos, etc)
- Logos institucionais (CESPE, banca)
- Ilustracoes decorativas sem valor didatico
- Elementos de fluxo/tipografia (setas, marcadores)

Se a pagina nao tem figuras relevantes, retorne "figures": []
Se ha figura mas voce nao consegue identificar qual questao referencia, retorne
question_text_snippet: "".

Formato JSON estrito (sem markdown, sem texto antes/depois):
{
  "figures": [
    {
      "question_text_snippet": "Considere o texto acima e julgue...",
      "description": "grafico de barras horizontais mostrando...",
      "bbox": [10, 30, 90, 65]
    }
  ]
}
"""


def _similaridade(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or '')[:200], (b or '')[:200]).ratio()


BANCAS_MAP = {
    'cebraspe': 'Cebraspe', 'cespe': 'CESPE', 'funcab': 'FUNCAB',
    'funrio': 'FUNRIO', 'fgv': 'FGV',
}


def _detectar_banca_ano(filename: str):
    nome = filename.lower()
    banca = None
    for key, label in BANCAS_MAP.items():
        if key in nome:
            banca = label
            break
    m = re.search(r'(19[89]\d|20\d{2})', nome)
    ano = int(m.group(1)) if m else None
    return banca, ano


class Command(BaseCommand):
    help = 'Extrai figuras de PDFs via Gemini Vision (precisao) + PyMuPDF crop'

    def add_arguments(self, parser):
        grupo = parser.add_mutually_exclusive_group(required=True)
        grupo.add_argument('--arquivo', type=str, help='PDF unico')
        grupo.add_argument('--pasta', type=str, help='Pasta com PDFs')

        parser.add_argument('--banca', type=str, default='', help='Override banca')
        parser.add_argument('--ano', type=int, default=None, help='Override ano')
        parser.add_argument('--dry_run', action='store_true',
                            help='Nao salva imagens, so mostra o que faria')
        parser.add_argument('--min_area_pct', type=float, default=3.0,
                            help='Ignora bboxes < N%% da pagina (default 3)')
        parser.add_argument('--min_sim', type=float, default=0.55,
                            help='Similaridade minima do fuzzy match (default 0.55)')
        parser.add_argument('--dpi_render', type=int, default=110,
                            help='DPI de render enviado ao Gemini (default 110 — '
                                 'imagem menor = resposta mais rapida)')
        parser.add_argument('--dpi_crop', type=int, default=250,
                            help='DPI de saida da figura cropada (default 250)')
        parser.add_argument('--gemini_timeout', type=int, default=45,
                            help='Timeout de cada chamada Gemini em segundos (default 45)')
        parser.add_argument('--delay', type=float, default=5.0,
                            help='Segundos entre chamadas Gemini (default 5 — '
                                 'respeita 15 RPM do free tier)')
        parser.add_argument('--model', type=str, default='gemini-3.5-flash',
                            help='Modelo Gemini (default gemini-3.5-flash)')

    def handle(self, *args, **opts):
        try:
            import google.generativeai as genai
        except ImportError:
            raise CommandError('google-generativeai nao instalado')

        api_key = getattr(settings, 'GEMINI_API_KEY', '')
        if not api_key:
            raise CommandError('GEMINI_API_KEY nao configurada')
        genai.configure(api_key=api_key)

        if opts['arquivo']:
            pdfs = [Path(opts['arquivo'])]
        else:
            pasta = Path(opts['pasta'])
            if not pasta.is_dir():
                raise CommandError(f'Pasta nao existe: {pasta}')
            pdfs = sorted(pasta.glob('*.pdf'))
            if not pdfs:
                raise CommandError(f'Nenhum PDF em {pasta}')

        total_attach = 0
        total_orphan = 0
        for pdf in pdfs:
            self.stdout.write(self.style.HTTP_INFO(
                f'\n{"=" * 60}\n▶ {pdf.name}\n{"=" * 60}'
            ))
            a, o = self._processar_pdf(pdf, opts, genai)
            total_attach += a
            total_orphan += o

        self.stdout.write(self.style.SUCCESS(
            f'\nTOTAL: {total_attach} figuras anexadas · {total_orphan} orphan (sem match)'
        ))

    def _processar_pdf(self, pdf_path, opts, genai):
        if not pdf_path.exists():
            self.stdout.write(self.style.ERROR(f'  Nao existe: {pdf_path}'))
            return 0, 0

        banca_det, ano_det = _detectar_banca_ano(pdf_path.name)
        banca = opts['banca'] or banca_det
        ano = opts['ano'] or ano_det
        self.stdout.write(f'  Banca: {banca or "?"} | Ano: {ano or "?"}')

        # Candidatas: mesmo banca/ano, sem imagem ainda
        filtro = {'imagem': ''}
        if banca:
            filtro['banca'] = banca
        if ano:
            filtro['ano'] = ano
        candidatas = list(Questao.objects.filter(**filtro))
        self.stdout.write(f'  Candidatas sem imagem: {len(candidatas)}')

        if not candidatas:
            return 0, 0

        # Abre PDF
        doc = fitz.open(str(pdf_path))
        model = genai.GenerativeModel(opts['model'])

        attach = 0
        orphan = 0
        candidatas_disponiveis = list(candidatas)

        for page_num in range(len(doc)):
            page = doc[page_num]
            self.stdout.write(f'  Pg {page_num + 1}/{len(doc)}... ', ending='')
            self.stdout.flush()

            # Render pagina como PNG
            try:
                pix = page.get_pixmap(dpi=opts['dpi_render'])
                page_png = pix.tobytes('png')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'render falhou: {e}'))
                continue

            # Chama Gemini
            try:
                image_part = {'mime_type': 'image/png', 'data': page_png}
                resp = model.generate_content(
                    [PROMPT_FIGURAS, image_part],
                    generation_config={
                        'temperature': 0.1,
                        'max_output_tokens': 2048,
                        'response_mime_type': 'application/json',
                    },
                    request_options={'timeout': opts.get('gemini_timeout', 45)},
                )
                raw = (resp.text or '').strip()
                raw = re.sub(r'^```(?:json)?\s*', '', raw)
                raw = re.sub(r'\s*```$', '', raw)
                data = json.loads(raw)
                figures = data.get('figures', []) if isinstance(data, dict) else []
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'Gemini erro: {type(e).__name__}: {str(e)[:60]}'
                ))
                if opts['delay']:
                    time.sleep(opts['delay'])
                continue

            if not figures:
                self.stdout.write('sem figuras')
                if opts['delay']:
                    time.sleep(opts['delay'])
                continue

            self.stdout.write(f'{len(figures)} figuras')

            # Processa cada figura
            for i, fig in enumerate(figures, 1):
                bbox_pct = fig.get('bbox', [])
                if not isinstance(bbox_pct, list) or len(bbox_pct) != 4:
                    orphan += 1
                    continue

                # Area sanity check
                w_pct = bbox_pct[2] - bbox_pct[0]
                h_pct = bbox_pct[3] - bbox_pct[1]
                area_pct = (w_pct * h_pct) / 100  # aproximado
                if area_pct < opts['min_area_pct']:
                    orphan += 1
                    continue

                # Fuzzy match a Questao pela snippet
                snippet = (fig.get('question_text_snippet') or '').strip()
                if not snippet:
                    orphan += 1
                    continue

                melhor = None
                melhor_sim = 0.0
                for c in candidatas_disponiveis:
                    sim = _similaridade(snippet, c.texto or '')
                    if sim > melhor_sim:
                        melhor_sim = sim
                        melhor = c

                if not melhor or melhor_sim < opts['min_sim']:
                    orphan += 1
                    self.stdout.write(
                        f'    orphan: sim={melhor_sim:.0%} snippet={snippet[:50]!r}'
                    )
                    continue

                # Crop da figura do PDF original
                x0_pdf = (bbox_pct[0] / 100) * page.rect.width
                y0_pdf = (bbox_pct[1] / 100) * page.rect.height
                x1_pdf = (bbox_pct[2] / 100) * page.rect.width
                y1_pdf = (bbox_pct[3] / 100) * page.rect.height
                clip = fitz.Rect(x0_pdf, y0_pdf, x1_pdf, y1_pdf)

                try:
                    crop_pix = page.get_pixmap(dpi=opts['dpi_crop'], clip=clip)
                    crop_png_bytes = crop_pix.tobytes('png')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'    crop falhou: {e}'
                    ))
                    orphan += 1
                    continue

                fname = f'q{melhor.id}_pg{page_num + 1}_f{i}.png'

                if opts['dry_run']:
                    self.stdout.write(
                        f'    [DRY] match {melhor_sim:.0%} → Q#{melhor.id} '
                        f'({crop_pix.width}x{crop_pix.height}, {len(crop_png_bytes)}B)'
                    )
                else:
                    melhor.imagem.save(fname, ContentFile(crop_png_bytes), save=True)
                    self.stdout.write(
                        f'    ✓ match {melhor_sim:.0%} → Q#{melhor.id} '
                        f'({crop_pix.width}x{crop_pix.height})'
                    )

                attach += 1
                candidatas_disponiveis.remove(melhor)

            if opts['delay']:
                time.sleep(opts['delay'])

        doc.close()
        self.stdout.write(self.style.SUCCESS(
            f'  ✓ {attach} figuras · {orphan} orphan'
        ))
        return attach, orphan
