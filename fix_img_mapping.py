"""
Corrige mapeamento final de imagens:
- Q20 (garrafa): img85 da pag 7
- Q23 (slogans): remover imagem
- Q24 (gráfico chegada): img89 da pag 7
"""
import fitz, os, sys
sys.path.insert(0, r'C:\Users\USER\Downloads\projeto_prf')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prf_master.settings')
import django; django.setup()

from django.db import transaction
from django.core.files.base import ContentFile
from quiz.models import Questao, Categoria

PDF_PATH  = r"C:\Users\USER\Downloads\1999_amarela.pdf"
MEDIA_DIR = r"C:\Users\USER\Downloads\projeto_prf\media\questoes"

cat = Categoria.objects.get(nome='ENEM')
qs  = list(Questao.objects.filter(categoria=cat).order_by('id'))

def q_by_kw(*keywords):
    for q in qs:
        if all(kw.lower() in q.texto.lower() for kw in keywords):
            return q
    return None

# Mostra contexto de Q20, Q23, Q24 para confirmar
q20 = q_by_kw('garrafa')
q23 = q_by_kw('slogan')
q24 = q_by_kw('probabilidade', 'chegar')
if not q24:
    q24 = q_by_kw('probabilidade', 'antônio')
if not q24:
    q24 = q_by_kw('probabilidade', 'antonio')
if not q24:
    # Q24 = "A probabilidade de que José e Antônio cheguem..."
    for q in qs:
        if 'probabilidade' in q.texto.lower() and ('josé' in q.texto.lower() or 'jose' in q.texto.lower()):
            q24 = q
            break

print(f"Q20: id={q20.id if q20 else 'NÃO'} | {q20.texto[:60] if q20 else ''}")
print(f"Q23: id={q23.id if q23 else 'NÃO'} | {q23.texto[:60] if q23 else ''} | img={bool(q23.imagem) if q23 else None}")
print(f"Q24: id={q24.id if q24 else 'NÃO'} | {q24.texto[:60] if q24 else ''}")
print()

# Extrai img85 (xref=85, pag 7) e img89 (xref=89, pag 7) do PDF via renderização
doc = fitz.open(PDF_PATH)
page7 = doc[6]  # page 7 (0-indexed)

def render_image_region(page, xref):
    """Renderiza a região do xref na página."""
    rects = page.get_image_rects(xref)
    if not rects:
        return None
    rect = rects[0]
    rect_exp = fitz.Rect(rect.x0-2, rect.y0-2, rect.x1+2, rect.y1+2)
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat, clip=rect_exp, colorspace=fitz.csGRAY)
    return pix.tobytes("png")

img85_data = render_image_region(page7, 85)
img89_data = render_image_region(page7, 89)

print(f"img85: {'OK' if img85_data else 'FALHOU'}")
print(f"img89: {'OK' if img89_data else 'FALHOU'}")

doc.close()

with transaction.atomic():

    # Q20: adiciona img85 (garrafa)
    if q20 and img85_data:
        fname = "enem1999_p7_img85.png"
        q20.imagem.save(fname, ContentFile(img85_data), save=True)
        print(f"✓ Q20 (id={q20.id}): imagem vinculada")
    elif q20:
        print(f"⚠ Q20: img85_data não disponível")

    # Q23: remove imagem (slogans não tem imagem)
    if q23 and q23.imagem:
        q23.imagem.delete(save=False)
        q23.imagem = None
        q23.save()
        print(f"✓ Q23 (id={q23.id}): imagem removida")
    else:
        print(f"  Q23: já sem imagem ou não encontrada")

    # Q24: adiciona img89 (gráfico chegada de José/Antônio)
    if q24 and img89_data:
        fname = "enem1999_p7_img89.png"
        q24.imagem.save(fname, ContentFile(img89_data), save=True)
        print(f"✓ Q24 (id={q24.id}): imagem vinculada")
    elif q24:
        print(f"⚠ Q24: img89_data não disponível")
    else:
        print(f"⚠ Q24: questão não encontrada por keywords")

print()
print("=== Estado final ===")
for q in Questao.objects.filter(categoria=cat).exclude(imagem='').exclude(imagem=None).order_by('id'):
    print(f"  id={q.id}: {os.path.basename(q.imagem.name)[:40]} | {q.texto[:55]}")
