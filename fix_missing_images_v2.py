"""
Corrige imagens faltantes — segunda rodada:
- Q16 (id=3733): esquema água do mar (pag 6, vetor entre Q16 texto e alternativas)
- Q19 (id=3736): tabela de votação (pag 7, lado direito)
- Q26 (id=3743): mapa Sol/cidades — compartilha com Q25 (xref=100)
- Q27 (id=3744): mapa cidades — região com 3 desenhos no rodapé pag 8 (y=600-810)
- Q32 (id=3749): panela de pressão — xref=122 pag 10
- Q33 (id=3750): panela de pressão — mesma figura
- Q61 (id=3778): gráfico velocidade da avenida (procurar local)
"""
import fitz, os, sys
sys.path.insert(0, r'C:\Users\USER\Downloads\projeto_prf')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prf_master.settings')
import django; django.setup()

from django.db import transaction
from django.core.files.base import ContentFile
from quiz.models import Questao, Categoria, LogSistema

PDF_PATH = r'C:\Users\USER\Downloads\1999_amarela.pdf'

doc = fitz.open(PDF_PATH)

def render_region(pnum, y0, y1, x0=0, x1=None, zoom=2.0, gray=True):
    page = doc[pnum]
    if x1 is None:
        x1 = page.rect.width
    rect = fitz.Rect(x0, y0, x1, y1)
    mat  = fitz.Matrix(zoom, zoom)
    cs   = fitz.csGRAY if gray else fitz.csRGB
    pix  = page.get_pixmap(matrix=mat, clip=rect, colorspace=cs)
    return pix.tobytes("png")

def render_xref(pnum, xref, zoom=2.0):
    page = doc[pnum]
    rects = page.get_image_rects(xref)
    if not rects:
        return None
    r = rects[0]
    rect_exp = fitz.Rect(r.x0-3, r.y0-3, r.x1+3, r.y1+3)
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, clip=rect_exp, colorspace=fitz.csGRAY)
    return pix.tobytes("png")


# ── Q16 (id=3733): esquema água do mar — pag 6, y=85-325 ─────────────────────
# Q16 inicia y=57 (texto "água do mar..."), alternativas começam ~y=290
# Renderiza o desenho do esquema (que é vetor/texto com setas)
img_q16 = render_region(5, y0=70, y1=325)

# ── Q19 (id=3736): tabela de votação — pag 7, lado direito ───────────────────
# A tabela "Ordenação | Nº votantes" fica entre y=130 e y=280 do lado direito
img_q19 = render_region(6, y0=110, y1=280, x0=280, x1=595)

# ── Q26 (id=3743): mapa Sol/cidades — mesma figura de Q25 (xref=100) ─────────
img_q26 = render_xref(7, 100)

# ── Q27 (id=3744): rodapé pag 8 com diagramas das cidades (vetor) ────────────
# Q26 termina ~y=735, Q27 começa y=741, alternativas vão até y=805
# A figura com SUL/SUL/SUL fica acima de Q27 (y=580-655)
img_q27 = render_region(7, y0=540, y1=660)

# ── Q32 (id=3749): panela de pressão — xref=122 pag 10 ───────────────────────
img_q32 = render_xref(9, 122)

# ── Q33 (id=3750): mesma figura ──────────────────────────────────────────────
img_q33 = img_q32

# ── Q61 (id=3778): gráfico avenida — pag 18 entre Q60 e Q61 ──────────────────
# Q60 começa y=474 pag 18, Q61 começa y=727. Gráfico entre alternativas Q60 e Q61
# Olhando: Q60 tem 5 alternativas (~y=474-560), então gráfico em y=560-725
img_q61 = render_region(17, y0=560, y1=725)

doc.close()

assignments = [
    (3733, 'Q16', 'enem1999_p6_esquema_q16.png',    img_q16),
    (3736, 'Q19', 'enem1999_p7_tabela_q19.png',     img_q19),
    (3743, 'Q26', 'enem1999_p8_mapa_q26.png',       img_q26),
    (3744, 'Q27', 'enem1999_p8_cidades_q27.png',    img_q27),
    (3749, 'Q32', 'enem1999_p10_panela_q32.png',    img_q32),
    (3750, 'Q33', 'enem1999_p10_panela_q33.png',    img_q33),
    (3778, 'Q61', 'enem1999_p18_grafico_q61.png',   img_q61),
]

print("Imagens renderizadas:")
for qid, label, fname, data in assignments:
    sz = len(data)//1024 if data else 0
    print(f"  {label} (id={qid}): {sz}KB → {fname}")

print()
print("Aplicando ao banco...")
with transaction.atomic():
    for qid, label, fname, data in assignments:
        if not data:
            print(f"  ⚠ {label} (id={qid}): sem dados, pulando")
            continue
        q = Questao.objects.get(id=qid)
        if q.imagem:
            q.imagem.delete(save=False)
        q.imagem.save(fname, ContentFile(data), save=True)
        print(f"  ✓ {label} (id={qid}): imagem salva")

# Registra no log do sistema
LogSistema.objects.create(
    nivel='INFO',
    origem='import/enem-1999',
    mensagem=f'Imagens v2: {len(assignments)} questões corrigidas',
    detalhe='\n'.join(f'{l} (id={i}) → {f}' for i,l,f,_ in assignments),
)

print()
print("=== Estado final ENEM 1999 (com imagem) ===")
cat = Categoria.objects.get(nome='ENEM')
for q in Questao.objects.filter(categoria=cat).exclude(imagem='').exclude(imagem=None).order_by('id'):
    qnum = q.id - 3717
    print(f"  Q{qnum:02d} id={q.id}: {os.path.basename(q.imagem.name)[:48]}")
