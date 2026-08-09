"""
Corrige:
1. Mapeamento errado de imagens (img85→Q20, img89→Q24, Q19/Q23 sem imagem)
2. Texto das alternativas E com conteúdo vazado da próxima questão
3. Rodapés "X AMARELA" nos textos de alternativas
"""
import sys, os, re
sys.path.insert(0, r'C:\Users\USER\Downloads\projeto_prf')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prf_master.settings')
import django; django.setup()

from django.db import transaction
from django.core.files.base import ContentFile
from quiz.models import Questao, Alternativa, Categoria

MEDIA_DIR = r"C:\Users\USER\Downloads\projeto_prf\media\questoes"
cat = Categoria.objects.get(nome='ENEM')
qs  = list(Questao.objects.filter(categoria=cat).order_by('id'))

def q_by_keyword(keyword):
    return next((q for q in qs if keyword.lower() in q.texto.lower()), None)

print("=== Diagnóstico ===")
for q in qs:
    img = os.path.basename(q.imagem.name) if q.imagem else None
    for a in q.alternativa_set.all():
        if re.search(r'\d{1,2}\s+AMARELA', a.texto) or \
           (len(a.texto) > 60 and re.search(r'\n\d{2}[\s\n]', a.texto)):
            print(f"  Q(id={q.id}) alt E com vazamento: {repr(a.texto[:120])}")
    if img:
        pass  # já sabemos

print()

with transaction.atomic():

    # ── 1. Corrige vazamento de texto nas alternativas E ─────────────────────
    for q in qs:
        alt_e = q.alternativa_set.all()
        for a in alt_e:
            original = a.texto
            fixed = a.texto

            # Remove rodapé "N AMARELA ..."
            fixed = re.sub(r'\n?\d{1,2}\s+AMARELA[^\n]*', '', fixed).strip()

            # Remove texto da próxima questão (linha que começa com \d{2})
            cut = re.search(r'\n\d{2}[\s\n]', fixed)
            if cut:
                fixed = fixed[:cut.start()].strip()

            # Remove contexto extra após linha em branco (para alt E longa)
            if len(fixed) > 80:
                blank = fixed.find('\n\n')
                if 0 < blank < len(fixed):
                    fixed = fixed[:blank].strip()

            if fixed != original:
                a.texto = fixed
                a.save()
                print(f"  ✓ Alt corrigida (Q id={q.id}): {repr(original[:80])} → {repr(fixed[:80])}")

    # ── 2. Corrige mapeamento de imagens ─────────────────────────────────────

    # Q19: eleição/votação — NÃO tem imagem (a tabela é texto)
    q19 = q_by_keyword('candidatos A, B, C e 33 eleitores')
    if q19 and q19.imagem:
        # Guarda o fname da img85 para reusar em Q20
        img85_fname = os.path.basename(q19.imagem.name)
        img85_path  = os.path.join(MEDIA_DIR, img85_fname)
        q19.imagem.delete(save=False)
        q19.imagem = None
        q19.save()
        print(f"  ✓ Q19 (id={q19.id}): imagem removida")
    else:
        img85_fname = next((f for f in os.listdir(MEDIA_DIR) if 'p7_img85' in f), None)
        img85_path  = os.path.join(MEDIA_DIR, img85_fname) if img85_fname else None

    # Q20: garrafa cilíndrica — deve ter img85
    q20 = q_by_keyword('garrafa cil')
    if q20:
        if img85_path and os.path.exists(img85_path):
            with open(img85_path, 'rb') as f:
                q20.imagem.save(os.path.basename(img85_path), ContentFile(f.read()), save=True)
            print(f"  ✓ Q20 (id={q20.id}): imagem img85 vinculada")
        else:
            print(f"  ⚠ Q20: img85 não encontrada em {img85_path}")

    # Q23: slogans/reformistas — NÃO tem imagem
    q23 = q_by_keyword('slogan')
    if not q23:
        q23 = q_by_keyword('reformist')
    if q23 and q23.imagem:
        img89_fname = os.path.basename(q23.imagem.name)
        img89_path  = os.path.join(MEDIA_DIR, img89_fname)
        q23.imagem.delete(save=False)
        q23.imagem = None
        q23.save()
        print(f"  ✓ Q23 (id={q23.id}): imagem removida")
    else:
        img89_fname = next((f for f in os.listdir(MEDIA_DIR) if 'p7_img89' in f), None)
        img89_path  = os.path.join(MEDIA_DIR, img89_fname) if img89_fname else None

    # Q24: "de acordo com o gráfico" / "chegada de José e Antônio" — deve ter img89
    q24 = q_by_keyword('chegada de')
    if not q24:
        q24 = q_by_keyword('a probabilidade de que josé e antônio')
    if not q24:
        # Procura pela questão sobre probabilidade de viagem
        q24 = q_by_keyword('viagem')
    print(f"  Q24 encontrada: id={q24.id if q24 else 'NÃO'} | texto: {q24.texto[:60] if q24 else ''}")

    if q24 and not q24.imagem and img89_path and os.path.exists(img89_path):
        with open(img89_path, 'rb') as f:
            q24.imagem.save(os.path.basename(img89_path), ContentFile(f.read()), save=True)
        print(f"  ✓ Q24 (id={q24.id}): imagem img89 vinculada")

print("\n=== Estado final das questões com imagem ===")
for q in Questao.objects.filter(categoria=cat).exclude(imagem='').exclude(imagem=None).order_by('id'):
    print(f"  id={q.id}: {os.path.basename(q.imagem.name)} | {q.texto[:60]}")
