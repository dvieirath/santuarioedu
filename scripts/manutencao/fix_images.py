"""
1. Limpa imagens duplicadas em media/questoes (mantém só as do import atual)
2. Verifica transform matricies via page.get_drawings / xobject dict
3. Renderiza as páginas com questões para ver como ficam as imagens no contexto
"""
import fitz, os, sys, re
sys.path.insert(0, r'C:\Users\USER\Downloads\projeto_prf')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prf_master.settings')
import django; django.setup()
from quiz.models import Questao, Categoria

PDF_PATH  = r"C:\Users\USER\Downloads\1999_amarela.pdf"
MEDIA_DIR = r"C:\Users\USER\Downloads\projeto_prf\media\questoes"

# ── 1. Imagens em uso (vinculadas a questões) ────────────────────────────────
cat = Categoria.objects.get(nome='ENEM')
qs_img = Questao.objects.filter(categoria=cat).exclude(imagem='').exclude(imagem=None)
in_use = {os.path.basename(q.imagem.name) for q in qs_img}
print(f"Imagens em uso: {sorted(in_use)}\n")

# ── 2. Remove arquivos NÃO usados em media/questoes ──────────────────────────
all_files = set(os.listdir(MEDIA_DIR))
unused = [f for f in all_files if f.startswith('enem1999') and f not in in_use]
for f in unused:
    os.remove(os.path.join(MEDIA_DIR, f))
    print(f"Removido: {f}")
print(f"\n{len(unused)} arquivos duplicados/não-usados removidos.")

# ── 3. Verifica transform das imagens em uso no PDF ──────────────────────────
doc = fitz.open(PDF_PATH)
print("\nTransform matrices das imagens em uso:")
for pnum in range(doc.page_count):
    page = doc[pnum]
    infos = page.get_image_info(hashes=False)
    for info in infos:
        xref  = info.get('xref', 0)
        fname_base = f"enem1999_p{pnum+1}_img{xref}.png"
        # Procura versão com sufixo Django
        matched = [f for f in in_use if f.startswith(f"enem1999_p{pnum+1}_img{xref}")]
        if not matched:
            continue
        m = info.get('transform', None)
        if m:
            a, b, c, d, e, f_val = m
            # Detecta flip vertical: d < 0
            # Detecta rotação: b ou c != 0
            flipped  = d < 0
            rotated  = abs(b) > 1 or abs(c) > 1
            flag = ""
            if flipped:  flag += " FLIP-V"
            if rotated:  flag += " ROTATED"
            print(f"  {matched[0]}: a={a:.1f} b={b:.1f} c={c:.1f} d={d:.1f}{flag}")

doc.close()

# ── 4. Renderiza páginas com questões de imagem para inspeção visual ──────────
print("\nRenderizando páginas para verificação...")
RENDER_DIR = os.path.join(MEDIA_DIR, "_preview")
os.makedirs(RENDER_DIR, exist_ok=True)

doc = fitz.open(PDF_PATH)
pages_to_render = {3, 7, 8, 9, 10, 11, 12, 13, 14}
for pnum in [p-1 for p in pages_to_render]:
    page = doc[pnum]
    mat  = fitz.Matrix(1.5, 1.5)  # 150% zoom
    pix  = page.get_pixmap(matrix=mat)
    out  = os.path.join(RENDER_DIR, f"page_{pnum+1}.png")
    pix.save(out)
    print(f"  Pag {pnum+1}: {out}")
doc.close()
print("\nPronto! Abra a pasta _preview para ver as páginas.")
