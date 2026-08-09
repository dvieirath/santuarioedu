"""
Injects dark mode include into all quiz frontend templates.
Run once: python inject_dark_mode.py
"""
import os, re

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__),
                              'quiz', 'templates', 'quiz')

# Templates to update (standalone HTML files, not admin)
TARGETS = [
    'dashboard.html',
    'escolher_tema.html',
    'responder.html',
    'resultado.html',
    'conquistas.html',
    'ranking.html',
    'analytics.html',
    'plano_estudos.html',
    'caderno_erros.html',
    'favoritas.html',
    'historico_simulados.html',
    'perfil.html',
    'perfil_publico.html',
    'revisao_srs_inicio.html',
    'sem_questoes.html',
]

HEAD_INCLUDE   = '{% include "quiz/includes/dark_mode.html" %}\n'
TOGGLE_INCLUDE = '{% include "quiz/includes/dark_toggle_btn.html" %}\n      '

updated = []
skipped = []

for fname in TARGETS:
    path = os.path.join(TEMPLATES_DIR, fname)
    if not os.path.exists(path):
        skipped.append(fname + ' (not found)')
        continue

    with open(path, encoding='utf-8') as f:
        html = f.read()

    changed = False

    # 1. Inject dark_mode.html before </head>
    if HEAD_INCLUDE.strip() not in html:
        html = html.replace('</head>', HEAD_INCLUDE + '</head>', 1)
        changed = True

    # 2. Inject toggle button into the main <header> (not sidebar)
    #    Strategy: find the FIRST <header class="flex items-center ... sticky ...">
    #    and insert the toggle btn just before </header>
    if TOGGLE_INCLUDE.strip() not in html:
        # Match the main sticky header closing tag
        # Pattern: <header ... sticky ... > ... </header>
        # We look for the first </header> that follows a sticky header
        pattern = r'(<header[^>]*sticky[^>]*>)(.*?)(</header>)'
        def inject_toggle(m):
            inner = m.group(2)
            # Only inject if toggle not already there
            if 'theme-toggle-btn' in inner:
                return m.group(0)
            return m.group(1) + inner.rstrip() + '\n      ' + TOGGLE_INCLUDE.strip() + '\n    ' + m.group(3)
        new_html = re.sub(pattern, inject_toggle, html, count=1, flags=re.DOTALL)
        if new_html != html:
            html = new_html
            changed = True

    if changed:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
        updated.append(fname)
    else:
        skipped.append(fname + ' (already done)')

print(f"\n✅ Updated ({len(updated)}): {', '.join(updated)}")
print(f"⏭  Skipped ({len(skipped)}): {', '.join(skipped)}")
