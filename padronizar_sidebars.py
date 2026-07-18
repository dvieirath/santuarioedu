"""
Padroniza sidebars em todas as pages — substitui custom sidebars pelo include
'quiz/includes/sidebar.html' com o grupo correto pré-aberto.

Mapeia cada template ao seu grupo ativo correspondente:
  painel      → /dashboard/
  praticar    → /estudar/, /questao-do-dia/, /assuntos/, /modo-desafio/
  simulados   → /simulado-*, /historico-simulados/
  revisao     → /flashcards/, /revisao-*, /caderno-erros/, /favoritas/
  ia          → /analise-banca/, /analise-erros/, /resumos/, /previsao-*, /plano-ia/
  progresso   → /analytics/, /relatorio-*, /progresso-*, /mapa-*, /xp/, /performance/, /certificado/
  planejamento → /plano-estudos/, /plano-dinamico/, /metas/
  competicao  → /duelo/, /coletivo/, /grupos/, /ranking/
  conta       → /materiais/, /notificacoes/, /preferencias/, /planos/, /minha-assinatura/, /perfil/
"""
import os, re, sys
sys.path.insert(0, r'C:\Users\USER\Downloads\projeto_prf')

TEMPLATES_DIR = r'C:\Users\USER\Downloads\projeto_prf\quiz\templates\quiz'

# Mapa: nome do template → (active group, header info)
PAGES = {
    # Progresso
    'analytics.html':              'progresso',
    'analise_erros.html':          'ia',
    'relatorio_semanal.html':      'progresso',
    'progresso_edital.html':       'progresso',
    'mapa_conhecimento.html':      'progresso',
    'painel_xp.html':              'progresso',
    'performance_comparativa.html':'progresso',
    'certificado.html':            'progresso',
    # Revisão
    'caderno_erros.html':          'revisao',
    'favoritas.html':              'revisao',
    'revisao_srs_inicio.html':     'revisao',
    # Praticar (já feitas via custom OK ou via include)
    # Inteligência IA
    'resumos_lista.html':          'ia',
    'resumo_disciplina.html':      'ia',
    'previsao_topicos.html':       'ia',
    'plano_estudos_ia.html':       'ia',
    # Planejamento
    'plano_estudos.html':          'planejamento',
    'plano_dinamico.html':         'planejamento',
    'metas_avancadas.html':        'planejamento',
    'metas_semanais.html':         'planejamento',
    # Competição
    'ranking.html':                'competicao',
    'grupos_lista.html':           'competicao',
    'grupo_detalhe.html':          'competicao',
    # Conta
    'conquistas.html':             'conta',
    'central_notificacoes.html':   'conta',
    'preferencias_notificacao.html':'conta',
    'planos.html':                 'conta',
    'minha_assinatura.html':       'conta',
    'perfil.html':                 'conta',
    # Simulados (extras)
    'simulado_personalizado.html': 'simulados',
    'simulado_preditivo.html':     'simulados',
    'simulado_revisao.html':       'simulados',
    'laudo_desempenho.html':       'simulados',
    'relatorio_simulado_ia.html':  'simulados',
}

# Pages que DEVEM ficar full-screen (sem sidebar) — modos de foco
FOCUS_MODE = {
    'responder.html', 'resultado.html', 'sem_questoes.html',
    'simulado_questao.html', 'simulado_resultado.html',
    'modo_desafio.html', 'modo_prova_real.html',
    'flashcard_estudar.html', 'revisao_por_voz.html',  # voz já tem sidebar mas é foco
    'duelo_home.html', 'duelo_jogar.html', 'duelo_resultado.html', 'duelo_sala.html',
    'coletivo_home.html', 'coletivo_jogar.html', 'coletivo_resultado.html', 'coletivo_sala.html',
    'offline.html', 'conquista_card.html', 'relatorio_pdf.html', 'certificado.html',
    'perfil_publico.html',
}

def detectar_aside_block(content):
    """Encontra o bloco <aside>...</aside> de sidebar (procura por w-64 fixed left-0)."""
    # Procura por aside que tenha as classes típicas de sidebar (fixed left, w-64)
    pattern = re.compile(
        r'(?:<!--[^\n]*[Ss]idebar[^\n]*-->[\s\n]*)?'
        r'<aside\s+[^>]*(?:hidden\s+md:flex|w-64\s+fixed|fixed\s+left-0)[^>]*>',
        re.IGNORECASE
    )
    match = pattern.search(content)
    if not match:
        return None, None

    start = match.start()
    # Conta aside abre/fecha balanceando
    pos = match.end()
    depth = 1
    while pos < len(content) and depth > 0:
        next_open  = content.find('<aside', pos)
        next_close = content.find('</aside>', pos)
        if next_close == -1:
            return None, None
        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + 6
        else:
            depth -= 1
            pos = next_close + 8
    return start, pos

def processar_template(filename, active_group):
    path = os.path.join(TEMPLATES_DIR, filename)
    if not os.path.exists(path):
        return f'  ✗ {filename}: não encontrado'

    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Já usa o include?
    if "quiz/includes/sidebar.html" in content:
        return f'  ─ {filename}: já usa include (active={active_group})'

    start, end = detectar_aside_block(content)
    if start is None:
        return f'  ⚠ {filename}: sem aside detectado (active={active_group}, precisaria add manualmente)'

    include_tag = f"{{% include \"quiz/includes/sidebar.html\" with active='{active_group}' %}}"
    new_content = content[:start].rstrip() + '\n\n' + include_tag + '\n' + content[end:].lstrip()

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return f'  ✓ {filename}: convertida (active={active_group})'


print('PADRONIZANDO SIDEBARS')
print('='*60)
for fname, group in PAGES.items():
    print(processar_template(fname, group))
