"""
Importa as 63 questões do ENEM 1999 (Caderno Amarela) para o Django.
Detecção de questões por span fitz (x0 < 50) + extração por crop pdfplumber.
"""
import sys, os, re, fitz, pdfplumber
sys.path.insert(0, r'C:\Users\USER\Downloads\projeto_prf')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prf_master.settings')
import django; django.setup()

from django.db import transaction
from django.core.files.base import ContentFile
from quiz.models import Questao, Alternativa, Categoria

PDF_PATH  = r"C:\Users\USER\Downloads\1999_amarela.pdf"
MEDIA_DIR = r"C:\Users\USER\Downloads\projeto_prf\media\questoes"

# ── Gabarito oficial ENEM 1999 Caderno Amarela ──────────────────────────────
GABARITO = {
     1:'C',  2:'C',  3:'E',  4:'D',  5:'B',  6:'D',  7:'E',  8:'E',  9:'C', 10:'E',
    11:'E', 12:'B', 13:'A', 14:'A', 15:'A', 16:'C', 17:'D', 18:'B', 19:'C', 20:'B',
    21:'C', 22:'A', 23:'B', 24:'A', 25:'D', 26:'B', 27:'D', 28:'B', 29:'C', 30:'D',
    31:'D', 32:'B', 33:'E', 34:'D', 35:'B', 36:'E', 37:'A', 38:'D', 39:'E', 40:'C',
    41:'E', 42:'A', 43:'B', 44:'C', 45:'A', 46:'D', 47:'C', 48:'A', 49:'C', 50:'B',
    51:'D', 52:'B', 53:'A', 54:'E', 55:'E', 56:'D', 57:'A', 58:'C', 59:'C', 60:'E',
    61:'B', 62:'E', 63:'A',
}

# ── Helpers ──────────────────────────────────────────────────────────────────
def clean(t):
    t = re.sub(r'\(cid:\d+\)', '', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()

ALT_RE = re.compile(r'\(([A-E])\)\s*', re.MULTILINE)

def parse_alternatives(body):
    """Retorna (texto_questao, dict_alternativas). Lida com layout 1-col e 2-col."""
    alt_matches = list(ALT_RE.finditer(body))
    if not alt_matches:
        return None, {}

    # ── Layout sequencial A B C D E ──────────────────────────────────────
    seq_start = None
    for i in range(len(alt_matches) - 4):
        letters = [alt_matches[i+j].group(1) for j in range(5)]
        if letters == ['A','B','C','D','E']:
            seq_start = i
            break

    if seq_start is not None:
        seq   = alt_matches[seq_start:seq_start+5]
        texto = body[:seq[0].start()].strip()
        alts  = {}
        for j in range(5):
            letter   = seq[j].group(1)
            t_start  = seq[j].end()
            t_end    = seq[j+1].start() if j+1 < 5 else len(body)
            alt_text = body[t_start:t_end].strip()
            # Alt E pode capturar texto extra; para na primeira linha em branco
            if letter == 'E' and len(alt_text) > 400:
                cut = alt_text.find('\n\n')
                alt_text = alt_text[:cut].strip() if 0 < cut < 500 else alt_text[:400]
            alts[letter] = alt_text
        return texto, alts

    # ── Layout 2-colunas: letras fora de ordem ───────────────────────────
    letter_map = {}
    for m in alt_matches:
        l = m.group(1)
        if l not in letter_map:
            letter_map[l] = m

    if set(letter_map.keys()) >= {'A','B','C','D','E'}:
        ordered   = sorted(letter_map.items(), key=lambda x: x[1].start())
        first_alt = ordered[0][1]
        texto     = body[:first_alt.start()].strip()
        alts      = {}
        for i, (letter, m) in enumerate(ordered):
            t_start  = m.end()
            t_end    = ordered[i+1][1].start() if i+1 < len(ordered) else len(body)
            alt_text = body[t_start:t_end].strip()
            alt_text = re.sub(r'\s*\([A-E]\)\s*$', '', alt_text).strip()
            # Última alternativa do layout 2-col: corta no início de nova questão
            if i == len(ordered) - 1 and len(alt_text) > 5:
                cut_qnum = re.search(r'\n\d{2}[\s\n]', alt_text)
                if cut_qnum:
                    alt_text = alt_text[:cut_qnum.start()].strip()
                cut_blank = alt_text.find('\n\n')
                if 0 < cut_blank < len(alt_text):
                    alt_text = alt_text[:cut_blank].strip()
            alts[letter] = alt_text
        return texto, alts

    return None, {}


# ── Passo 1: Detecta marcadores via fitz spans ───────────────────────────────
print("Detectando questões via fitz spans (x0 < 50)...")
doc_fitz = fitz.open(PDF_PATH)

q_markers = []   # (page_1indexed, y0, qnum)

for pnum in range(doc_fitz.page_count):
    page = doc_fitz[pnum]
    d    = page.get_text("dict")
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                txt = span["text"].strip()
                x0  = span["bbox"][0]
                y0  = span["bbox"][1]

                # Corresponde a: exatamente "02" OU começa com "02 "
                m = re.match(r'^(\d{2})$', txt) or re.match(r'^(\d{2})\s', txt)
                if not m:
                    continue
                n = int(m.group(1))
                if not (1 <= n <= 63):
                    continue
                if x0 > 50:
                    continue  # não é margem esquerda
                # Exclui rodapés: texto da linha contém AMARELA
                full_line_text = ''.join(s["text"] for s in line["spans"])
                if 'AMARELA' in full_line_text:
                    continue
                q_markers.append((pnum+1, y0, n))

# Deduplica — mantém primeira ocorrência real de cada número
seen    = {}
markers = []
for entry in sorted(q_markers, key=lambda x: (x[0], x[1])):
    n = entry[2]
    if n not in seen:
        seen[n] = True
        markers.append(entry)

markers.sort(key=lambda x: (x[0], x[1]))

detected = sorted(n for _, _, n in markers)
missing  = sorted(set(range(1, 64)) - set(detected))
print(f"Detectadas ({len(detected)}): {detected}")
if missing:
    print(f"⚠ Ainda faltando: {missing}")


# ── Passo 2: Extrai texto via pdfplumber crop ─────────────────────────────────
print("\nExtraindo textos das questões via pdfplumber crop...")

# Pré-computa largura de cada página
with pdfplumber.open(PDF_PATH) as pdf:
    page_widths  = [p.width  for p in pdf.pages]
    page_heights = [p.height for p in pdf.pages]

def extract_question_text(markers, q_idx):
    """Extrai texto da questão markers[q_idx] até markers[q_idx+1]."""
    pg1, y1, n = markers[q_idx]
    if q_idx + 1 < len(markers):
        pg2, y2, _ = markers[q_idx + 1]
    else:
        pg2, y2 = pg1 + 1, 0   # fim da última página

    with pdfplumber.open(PDF_PATH) as pdf:
        parts = []
        for p in range(pg1, min(pg2 + 1, len(pdf.pages) + 1)):
            if p > len(pdf.pages):
                break
            pp     = pdf.pages[p - 1]
            y_top  = y1 - 2 if p == pg1 else 0
            y_bot  = y2 - 2 if p == pg2 else pp.height
            cropped = pp.crop((0, y_top, pp.width, y_bot))
            t = cropped.extract_text() or ""
            parts.append(t)
    return '\n'.join(parts)

q_texts = {}
for i, (pg, y0, n) in enumerate(markers):
    raw = extract_question_text(markers, i)
    # Remove número da questão no início
    raw = re.sub(rf'^\s*{n:02d}[\s\n]?', '', raw.strip())
    q_texts[n] = raw


# ── Passo 3: Mapeia imagens → questões ──────────────────────────────────────
q_page_y = {n: (pg, y0) for pg, y0, n in markers}

img_data = {}
for pnum in range(doc_fitz.page_count):
    page_obj = doc_fitz[pnum]
    for img in doc_fitz.get_page_images(pnum):
        xref = img[0]
        try:
            pix = fitz.Pixmap(doc_fitz, xref)
            if pix.width >= 60 and pix.height >= 60:
                fname = f"enem1999_p{pnum+1}_img{xref}.png"
                if os.path.exists(os.path.join(MEDIA_DIR, fname)):
                    rects = page_obj.get_image_rects(xref)
                    if rects:
                        img_data.setdefault(pnum+1, []).append((rects[0].y0, fname))
        except:
            pass

doc_fitz.close()

img_to_q = {}
for pg, imgs in sorted(img_data.items()):
    qs_on_pg = sorted(
        [(n, y) for n, (p, y) in q_page_y.items() if p == pg],
        key=lambda x: x[1]
    )
    for img_y, fname in sorted(imgs):
        best = None
        for qn, qy in qs_on_pg:
            if qy <= img_y + 30:
                best = qn
        if best is None and qs_on_pg:
            best = qs_on_pg[0][0]
        if best:
            img_to_q[fname] = best

print("\nImagens mapeadas:")
for fname, qn in sorted(img_to_q.items(), key=lambda x: x[1]):
    print(f"  Q{qn:02d} ← {fname}")


# ── Passo 4: Importa para o banco de dados ──────────────────────────────────
cat, created = Categoria.objects.get_or_create(nome='ENEM')
print(f"\nCategoria 'ENEM': {'criada' if created else 'já existia'}")

imported   = 0
img_linked = 0
errors     = []
print("\nImportando...\n")

with transaction.atomic():
    for qnum in range(1, 64):
        if qnum not in q_texts:
            errors.append(f"Q{qnum:02d}: não detectada")
            continue

        raw = q_texts[qnum]
        texto_q, alts = parse_alternatives(raw)

        if not alts or len(alts) < 5:
            errors.append(
                f"Q{qnum:02d}: alternativas={len(alts) if alts else 0} "
                f"— início: {repr(raw[:120])}"
            )
            continue

        texto_q  = clean(texto_q or '')
        alts_cln = {k: clean(v) for k, v in alts.items()}

        q = Questao.objects.create(
            categoria = cat,
            texto     = texto_q if texto_q else f'(Ver imagem — Questão {qnum})',
            tipo      = 'ME',
            banca     = 'INEP',
            ano       = 1999,
            assunto   = 'ENEM 1999',
            revisada  = False,
        )

        fnames_q = [f for f, qn in img_to_q.items() if qn == qnum]
        if fnames_q:
            img_path = os.path.join(MEDIA_DIR, fnames_q[0])
            if os.path.exists(img_path):
                with open(img_path, 'rb') as f:
                    q.imagem.save(fnames_q[0], ContentFile(f.read()), save=True)
                img_linked += 1

        for letra in ['A','B','C','D','E']:
            alt_text = alts_cln.get(letra, '') or '(Ver imagem)'
            Alternativa.objects.create(
                questao = q,
                texto   = alt_text,
                correta = (letra == GABARITO.get(qnum, '')),
            )

        imported += 1
        print(f"  Q{qnum:02d} ✓  {'[+img]' if fnames_q else ''}")

print(f"\n{'='*52}")
print(f"✓  {imported}/63 questões importadas")
print(f"✓  {img_linked} imagens vinculadas")
if errors:
    print(f"\n✗  Erros ({len(errors)}):")
    for e in errors:
        print(f"   {e}")
else:
    print("✓  Nenhum erro!")
