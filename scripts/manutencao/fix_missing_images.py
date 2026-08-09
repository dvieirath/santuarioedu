"""
Corrige imagens faltantes nas questões ENEM 1999:
- Q36, Q37: diagrama solar (xref=137, já capturado para Q35, renderiza novamente)
- Q43: 5 gráficos de anticorpos em conjunto (página 13, y=141-474)
- Q02: tabela de agendamento (página 2, bloco de texto acima de Q02)
- Q18: tabela de mortalidade infantil (página 6, abaixo de Q18)
- Q45: tabela de transformações de energia (página 14, abaixo de Q45)
- Q51: tabela de lâmpadas (página 16, abaixo de Q51)
- Q52: gráfico populacional (página 16, abaixo de Q52)
- Q56: gráfico crescimento de praga (página 17, ao lado de Q56)
"""
import fitz, os, sys
sys.path.insert(0, r'C:\Users\USER\Downloads\projeto_prf')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prf_master.settings')
import django; django.setup()

from django.db import transaction
from django.core.files.base import ContentFile
from quiz.models import Questao

PDF_PATH  = r'C:\Users\USER\Downloads\1999_amarela.pdf'
MEDIA_DIR = r'C:\Users\USER\Downloads\projeto_prf\media\questoes'

doc = fitz.open(PDF_PATH)

def render_region(pnum, y0, y1, x0=0, x1=None, zoom=2.0, gray=True):
    """Renderiza região da página (pnum 0-indexed)."""
    page = doc[pnum]
    if x1 is None:
        x1 = page.rect.width
    rect = fitz.Rect(x0, y0, x1, y1)
    mat  = fitz.Matrix(zoom, zoom)
    cs   = fitz.csGRAY if gray else fitz.csRGB
    pix  = page.get_pixmap(matrix=mat, clip=rect, colorspace=cs)
    return pix.tobytes("png")

def render_xref(pnum, xref, zoom=2.0):
    """Renderiza região onde o xref aparece na página."""
    page = doc[pnum]
    rects = page.get_image_rects(xref)
    if not rects:
        return None
    r = rects[0]
    rect_exp = fitz.Rect(r.x0-3, r.y0-3, r.x1+3, r.y1+3)
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, clip=rect_exp, colorspace=fitz.csGRAY)
    return pix.tobytes("png")

# ── Q36 (id=3753) e Q37 (id=3754): diagrama energia solar ────────────────────
# xref=137 na página 11 (pnum=10), y=100-353 — mesmo diagrama de Q35 (id=3752)
img_solar = render_xref(10, 137)

# ── Q43 (id=3760): 5 gráficos de anticorpos — renderiza bloco completo ───────
# Página 13 (pnum=12), y=120-490
img_anticorpos = render_region(12, y0=120, y1=490)

# ── Q02 (id=3719): tabela de agendamento ─────────────────────────────────────
# Página 2 (pnum=1), Q01 começa em y=98, Q02 em y=396
# A tabela está entre Q01 texto e Q02 (aprox y=200-390)
img_q02 = render_region(1, y0=195, y1=393)

# ── Q18 (id=3735): tabela mortalidade infantil ────────────────────────────────
# Página 6 (pnum=5), Q18 em y=521, Q19 começa em página 7
# Tabela fica entre texto de Q18 e fim da página (~y=600-820)
img_q18 = render_region(5, y0=600, y1=830)

# ── Q41 (id=3758): quadro usinas hidroelétricas ───────────────────────────────
# Página 12 (pnum=11), Q41 em y=470, Q42 em y=674
# Tabela entre Q41 texto e próxima questão
img_q41 = render_region(11, y0=510, y1=668)

# ── Q45 (id=3762): tabela transformações de energia ──────────────────────────
# Página 14 (pnum=13), Q45 em y=57, Q46 em y=303
# Tabela fica no meio da questão, entre texto e alternativas
img_q45 = render_region(13, y0=115, y1=296)

# ── Q51 (id=3768): tabela de lâmpadas ────────────────────────────────────────
# Página 16 (pnum=15), Q51 em y=57, Q52 em y=307
img_q51 = render_region(15, y0=170, y1=300)

# ── Q52 (id=3769): gráfico populacional ──────────────────────────────────────
# Página 16 (pnum=15), Q52 em y=307, Q53 em y=608
img_q52 = render_region(15, y0=350, y1=600)

# ── Q56 (id=3773): gráfico crescimento de praga ──────────────────────────────
# Página 17 (pnum=16), Q56 em y=437, Q57 em y=698
img_q56 = render_region(16, y0=470, y1=690)

doc.close()

print("Imagens renderizadas:")
assignments = [
    (3753, 'Q36',  'enem1999_p11_solar_q36.png',    img_solar),
    (3754, 'Q37',  'enem1999_p11_solar_q37.png',    img_solar),
    (3760, 'Q43',  'enem1999_p13_anticorpos.png',   img_anticorpos),
    (3719, 'Q02',  'enem1999_p2_tabela_q02.png',    img_q02),
    (3735, 'Q18',  'enem1999_p6_tabela_q18.png',    img_q18),
    (3758, 'Q41',  'enem1999_p12_quadro_q41.png',   img_q41),
    (3762, 'Q45',  'enem1999_p14_tabela_q45.png',   img_q45),
    (3768, 'Q51',  'enem1999_p16_tabela_q51.png',   img_q51),
    (3769, 'Q52',  'enem1999_p16_grafico_q52.png',  img_q52),
    (3773, 'Q56',  'enem1999_p17_grafico_q56.png',  img_q56),
]
for qid, label, fname, data in assignments:
    print(f"  {label} (id={qid}): {len(data)//1024}KB  → {fname}")

with transaction.atomic():
    for qid, label, fname, data in assignments:
        q = Questao.objects.get(id=qid)
        if q.imagem:
            q.imagem.delete(save=False)
        q.imagem.save(fname, ContentFile(data), save=True)
        print(f"  ✓ {label} (id={qid}): imagem salva")

print()
print("=== Estado final ===")
from quiz.models import Categoria
cat = Categoria.objects.get(nome='ENEM')
for q in Questao.objects.filter(categoria=cat).exclude(imagem='').exclude(imagem=None).order_by('id'):
    qnum = q.id - 3717
    exists = os.path.exists(os.path.join(r'C:\Users\USER\Downloads\projeto_prf\media', q.imagem.name))
    print(f"  Q{qnum:02d} id={q.id}: {os.path.basename(q.imagem.name)[:40]}  file={exists}")
