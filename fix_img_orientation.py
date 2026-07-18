"""
Corrige orientação das imagens renderizando a região da página.
Usa get_page_images + get_image_rects que funcionam com este PDF.
"""
import fitz, os, sys
sys.path.insert(0, r'C:\Users\USER\Downloads\projeto_prf')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prf_master.settings')
import django; django.setup()
from quiz.models import Questao, Categoria

PDF_PATH  = r"C:\Users\USER\Downloads\1999_amarela.pdf"
MEDIA_DIR = r"C:\Users\USER\Downloads\projeto_prf\media\questoes"

cat = Categoria.objects.get(nome='ENEM')
qs_img = Questao.objects.filter(categoria=cat).exclude(imagem='').exclude(imagem=None)
in_use = {os.path.basename(q.imagem.name) for q in qs_img}
print(f"Imagens em uso: {sorted(in_use)}\n")

doc   = fitz.open(PDF_PATH)
fixed = 0

for pnum in range(doc.page_count):
    page = doc[pnum]

    for img in doc.get_page_images(pnum):
        xref = img[0]
        fname_base = f"enem1999_p{pnum+1}_img{xref}"

        # Verifica se este xref está em uso (nome começa com fname_base)
        matched = [f for f in in_use if f.startswith(fname_base)]
        if not matched:
            continue

        fname = matched[0]
        fpath = os.path.join(MEDIA_DIR, fname)
        if not os.path.exists(fpath):
            print(f"  {fname}: arquivo não encontrado, ignorado")
            continue

        # Bounding box da imagem na página
        rects = page.get_image_rects(xref)
        if not rects:
            print(f"  {fname}: sem rect, ignorado")
            continue

        rect = rects[0]
        # Margem mínima para não cortar bordas
        rect_expanded = fitz.Rect(
            rect.x0 - 2, rect.y0 - 2,
            rect.x1 + 2, rect.y1 + 2
        )

        # Renderiza a região da página (inclui transformações corretas)
        mat = fitz.Matrix(2.0, 2.0)  # 2x zoom para boa qualidade
        pix = page.get_pixmap(matrix=mat, clip=rect_expanded, colorspace=fitz.csGRAY)

        pix.save(fpath)
        print(f"  ✓ Q{fname}: renderizado {pix.width}x{pix.height}px (bbox={rect.x0:.0f},{rect.y0:.0f},{rect.x1:.0f},{rect.y1:.0f})")
        fixed += 1

doc.close()
print(f"\n✓ {fixed} imagens corrigidas.")
