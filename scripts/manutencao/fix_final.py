"""
Correção final:
1. img85 → id=3737 (garrafa cilíndrica, calcular volume)   — remover de id=3731
2. img89 → id=3741 (José e Antônio chegam ao mesmo local)  — remover de id=3740
3. Limpar alt E com texto vazado (next-question context)
"""
import fitz, os, sys, re
sys.path.insert(0, r'C:\Users\USER\Downloads\projeto_prf')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prf_master.settings')
import django; django.setup()

from django.db import transaction
from django.core.files.base import ContentFile
from quiz.models import Questao, Alternativa, Categoria

PDF_PATH  = r"C:\Users\USER\Downloads\1999_amarela.pdf"
MEDIA_DIR = r"C:\Users\USER\Downloads\projeto_prf\media\questoes"

cat = Categoria.objects.get(nome='ENEM')

# ── Mostra estado atual das questões envolvidas ──────────────────────────────
print("=== Estado atual ===")
for qid in [3731, 3737, 3740, 3741]:
    try:
        q = Questao.objects.get(id=qid)
        img = os.path.basename(q.imagem.name) if q.imagem else '-'
        print(f"  id={qid}: img={img} | {q.texto[:70]}")
    except Questao.DoesNotExist:
        print(f"  id={qid}: NÃO ENCONTRADA")
print()

# ── Renderiza img85 e img89 diretamente do PDF ───────────────────────────────
doc = fitz.open(PDF_PATH)
page7 = doc[6]  # página 7 (0-indexed)

def render_region(page, xref):
    rects = page.get_image_rects(xref)
    if not rects:
        return None
    rect = rects[0]
    rect_exp = fitz.Rect(rect.x0-2, rect.y0-2, rect.x1+2, rect.y1+2)
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat, clip=rect_exp, colorspace=fitz.csGRAY)
    return pix.tobytes("png")

img85_data = render_region(page7, 85)
img89_data = render_region(page7, 89)
doc.close()

print(f"img85: {'OK' if img85_data else 'FALHOU'}")
print(f"img89: {'OK' if img89_data else 'FALHOU'}")
print()

with transaction.atomic():

    # ── 1. Remove img85 de id=3731 (garrafas vazias — errada) ────────────────
    q3731 = Questao.objects.get(id=3731)
    if q3731.imagem:
        q3731.imagem.delete(save=False)
        q3731.imagem = None
        q3731.save()
        print(f"✓ id=3731: imagem removida")
    else:
        print(f"  id=3731: já sem imagem")

    # ── 2. Adiciona img85 a id=3737 (calcular volume do líquido na garrafa) ──
    q3737 = Questao.objects.get(id=3737)
    if img85_data:
        q3737.imagem.save("enem1999_p7_img85.png", ContentFile(img85_data), save=True)
        print(f"✓ id=3737: img85 vinculada")
    else:
        print(f"⚠ id=3737: img85_data indisponível")

    # ── 3. Remove img89 de id=3740 (slogans reformistas — sem imagem) ────────
    q3740 = Questao.objects.get(id=3740)
    if q3740.imagem:
        q3740.imagem.delete(save=False)
        q3740.imagem = None
        q3740.save()
        print(f"✓ id=3740: imagem removida")
    else:
        print(f"  id=3740: já sem imagem")

    # ── 4. Adiciona img89 a id=3741 (José e Antônio — gráfico probabilidade) ─
    q3741 = Questao.objects.get(id=3741)
    if img89_data:
        q3741.imagem.save("enem1999_p7_img89.png", ContentFile(img89_data), save=True)
        print(f"✓ id=3741: img89 vinculada")
    else:
        print(f"⚠ id=3741: img89_data indisponível")

    # ── 5. Limpa alternativas com texto vazado ────────────────────────────────
    print()
    print("=== Limpeza de alternativas com texto vazado ===")
    qs_all = Questao.objects.filter(categoria=cat).order_by('id')
    fixed_alts = 0
    for q in qs_all:
        for a in q.alternativa_set.all():
            original = a.texto
            fixed = a.texto

            # Remove rodapé "N AMARELA ..."
            fixed = re.sub(r'\n?\s*\d{1,2}\s+AMARELA[^\n]*', '', fixed).strip()

            # Remove texto que começa como número de questão (\n\d{2} no início de linha)
            cut = re.search(r'\n\d{2}[\s\n]', fixed)
            if cut:
                fixed = fixed[:cut.start()].strip()

            # Para alternativas muito longas: corta em primeira linha em branco
            if len(fixed) > 120:
                blank = fixed.find('\n\n')
                if 0 < blank < len(fixed):
                    fixed = fixed[:blank].strip()

            if fixed != original:
                a.texto = fixed
                a.save()
                fixed_alts += 1
                print(f"  ✓ Q id={q.id} alt: {repr(original[:80])} → {repr(fixed[:60])}")

    print(f"\n{fixed_alts} alternativas corrigidas.")

print()
print("=== Estado final (questões com imagem) ===")
for q in Questao.objects.filter(categoria=cat).exclude(imagem='').exclude(imagem=None).order_by('id'):
    print(f"  id={q.id}: {os.path.basename(q.imagem.name)[:45]} | {q.texto[:60]}")
