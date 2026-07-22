"""
Extrai as imagens embutidas de PDFs de provas e associa a Questao.imagem
usando match por texto adjacente (contexto ao redor da imagem no PDF).

Fluxo:
  1. PyMuPDF abre o PDF, itera paginas
  2. Em cada pagina, pega imagens embutidas (embedded) com bounding box
  3. Extrai o texto ao redor de cada imagem (contexto)
  4. Compara com Questao.texto no BD (mesma banca/ano) via fuzzy match
  5. Salva a imagem como PNG em media/questoes/ e seta Questao.imagem

Uso:
    # 1 PDF
    python manage.py extrair_imagens_pdf --arquivo provas_pdf/processados/cespe_prf_2013.pdf

    # Pasta inteira
    python manage.py extrair_imagens_pdf --pasta provas_pdf/

    # Dry-run (nao salva)
    python manage.py extrair_imagens_pdf --arquivo ... --dry_run

    # Threshold de similaridade (default 0.35)
    python manage.py extrair_imagens_pdf --arquivo ... --min_sim 0.4
"""
import re
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

import fitz  # PyMuPDF

from quiz.models import Questao


BANCAS_MAP = {
    'cebraspe': 'Cebraspe',
    'cespe':    'CESPE',
    'funcab':   'FUNCAB',
    'funrio':   'FUNRIO',
    'fgv':      'FGV',
}


def detectar_banca_ano(filename):
    nome = filename.lower()
    banca = None
    for key, label in BANCAS_MAP.items():
        if key in nome:
            banca = label
            break
    m = re.search(r'(19[89]\d|20\d{2})', nome)
    ano = int(m.group(1)) if m else None
    return banca, ano


def similarity(a, b):
    return SequenceMatcher(None, a[:300], b[:300]).ratio()


class Command(BaseCommand):
    help = 'Extrai imagens embutidas de PDFs e associa a Questao.imagem'

    def add_arguments(self, parser):
        grupo = parser.add_mutually_exclusive_group(required=True)
        grupo.add_argument('--arquivo', type=str)
        grupo.add_argument('--pasta', type=str)
        parser.add_argument('--banca', type=str, default='',
                            help='Override banca detectada')
        parser.add_argument('--ano', type=int, default=None,
                            help='Override ano detectado')
        parser.add_argument('--min_sim', type=float, default=0.35,
                            help='Similaridade minima pra dar match (default 0.35)')
        parser.add_argument('--min_width', type=int, default=80,
                            help='Ignora imagens menores que N pixels (logos/icones)')
        parser.add_argument('--dry_run', action='store_true')
        parser.add_argument('--sobrescrever', action='store_true',
                            help='Substitui imagem existente na questao')

    def handle(self, *args, **opts):
        if opts['arquivo']:
            arquivos = [Path(opts['arquivo'])]
        else:
            pasta = Path(opts['pasta'])
            if not pasta.is_dir():
                raise CommandError(f'Pasta nao encontrada: {pasta}')
            arquivos = sorted(pasta.glob('*.pdf'))

        total_attach = 0
        total_orphan = 0
        for pdf in arquivos:
            self.stdout.write(self.style.HTTP_INFO(
                f'\n{"=" * 60}\n▶ {pdf.name}\n{"=" * 60}'
            ))
            a, o = self._processar_pdf(pdf, opts)
            total_attach += a
            total_orphan += o

        self.stdout.write(self.style.SUCCESS(
            f'\n{"=" * 60}\nTOTAL: {total_attach} imagens anexadas · {total_orphan} orphan (sem match)'
        ))
        if opts['dry_run']:
            self.stdout.write(self.style.WARNING('[DRY-RUN] Nada foi salvo'))

    def _processar_pdf(self, pdf_path, opts):
        if not pdf_path.exists():
            self.stdout.write(self.style.ERROR(f'  Nao existe: {pdf_path}'))
            return 0, 0

        banca_det, ano_det = detectar_banca_ano(pdf_path.name)
        banca = opts['banca'] or banca_det
        ano = opts['ano'] or ano_det
        self.stdout.write(f'  Banca: {banca or "?"} | Ano: {ano or "?"}')

        # Candidatas do BD: filtradas por banca/ano
        filtro = {}
        if banca:
            filtro['banca'] = banca
        if ano:
            filtro['ano'] = ano
        # Se ja tem imagem e nao pediu sobrescrever, ignora
        candidatas = Questao.objects.filter(**filtro)
        if not opts['sobrescrever']:
            candidatas = candidatas.filter(imagem='')
        candidatas = list(candidatas)
        self.stdout.write(f'  Candidatas no BD: {len(candidatas)}')

        if not candidatas:
            self.stdout.write('  Nenhuma candidata — pulando')
            return 0, 0

        # Abre PDF
        doc = fitz.open(str(pdf_path))
        imagens = self._extrair_imagens_com_contexto(doc, opts['min_width'])
        doc.close()
        self.stdout.write(f'  Imagens encontradas no PDF: {len(imagens)}')

        # Match
        attach = 0
        orphan = 0
        candidatas_disponiveis = list(candidatas)
        for img in imagens:
            melhor = None
            melhor_sim = 0.0
            for q in candidatas_disponiveis:
                texto_q = q.texto or ''
                sim = similarity(img['contexto'], texto_q)
                if sim > melhor_sim:
                    melhor_sim = sim
                    melhor = q

            if melhor and melhor_sim >= opts['min_sim']:
                # Salva a imagem
                if not opts['dry_run']:
                    fname = f'pdf_pg{img["page"]}_q{melhor.id}.{img["ext"]}'
                    melhor.imagem.save(fname, ContentFile(img['bytes']), save=True)
                self.stdout.write(
                    f'    [match {melhor_sim:.0%}] pg{img["page"]} → Q#{melhor.id} '
                    f'({img["width"]}x{img["height"]} {img["ext"]})'
                )
                attach += 1
                candidatas_disponiveis.remove(melhor)
            else:
                orphan += 1

        self.stdout.write(self.style.SUCCESS(
            f'  ✓ {attach} anexadas · {orphan} orphan'
        ))
        return attach, orphan

    def _extrair_imagens_com_contexto(self, doc, min_width):
        """Retorna lista de dicts: {page, bbox, bytes, ext, width, height, contexto}
        Watermarks (imagens repetidas em varias paginas) sao filtradas por hash."""
        import hashlib

        # Passo 1: coleta todas as imagens com seus hashes pra identificar
        # watermarks (mesma imagem em multiplas paginas = watermark)
        hashes_por_pagina = {}
        for page_num, page in enumerate(doc, 1):
            for img_ref in page.get_images(full=True):
                xref = img_ref[0]
                try:
                    data = doc.extract_image(xref)
                    h = hashlib.md5(data['image']).hexdigest()
                    hashes_por_pagina.setdefault(h, set()).add(page_num)
                except Exception:
                    pass

        # Hash considerado watermark: aparece em 3+ paginas OU e a imagem
        # conhecida do PCI (3727 bytes exatos)
        watermark_hashes = {
            h for h, pgs in hashes_por_pagina.items() if len(pgs) >= 3
        }
        # Hash conhecido do watermark PCI Concursos 350x350
        PCI_WATERMARK_MD5 = None  # sera detectado pelo tamanho abaixo

        result = []
        for page_num, page in enumerate(doc, 1):
            imgs = page.get_images(full=True)
            for img_ref in imgs:
                xref = img_ref[0]
                # Bounding box da imagem na pagina
                try:
                    bboxes = page.get_image_bbox(img_ref, transform=False)
                except Exception:
                    continue
                if not bboxes or bboxes.is_empty:
                    continue
                # Descarta pequenas (logos, watermarks graficos)
                if bboxes.width < min_width or bboxes.height < min_width:
                    continue

                # Contexto de texto AO REDOR da imagem — pega texto acima e no meio
                # da pagina, comprimento ~500 chars pra ter enunciado
                acima = fitz.Rect(0, max(0, bboxes.y0 - 500),
                                  page.rect.width, bboxes.y0)
                abaixo = fitz.Rect(0, bboxes.y1,
                                   page.rect.width, min(page.rect.height, bboxes.y1 + 200))
                txt_acima = (page.get_text('text', clip=acima) or '').strip()
                txt_abaixo = (page.get_text('text', clip=abaixo) or '').strip()
                # Contexto: 300 ultimos chars acima (mais proximo) + 100 primeiros abaixo
                contexto = (txt_acima[-400:] + '\n' + txt_abaixo[:200]).strip()
                # Limpa watermarks
                contexto = re.sub(r'pcimarkpci\s*\S*|www\.pciconcursos\.com\.br', '', contexto)

                # Extrai bytes da imagem
                try:
                    img_data = doc.extract_image(xref)
                except Exception:
                    continue

                # Pula watermark: hash repetido em multiplas paginas OU
                # tamanho conhecido do PCI Concursos (3727 bytes)
                h = hashlib.md5(img_data['image']).hexdigest()
                if h in watermark_hashes:
                    continue
                if len(img_data['image']) == 3727:
                    continue

                result.append({
                    'page': page_num,
                    'bbox': (bboxes.x0, bboxes.y0, bboxes.x1, bboxes.y1),
                    'bytes': img_data['image'],
                    'ext': img_data.get('ext', 'png'),
                    'width': img_data.get('width', int(bboxes.width)),
                    'height': img_data.get('height', int(bboxes.height)),
                    'contexto': contexto,
                })
        return result
