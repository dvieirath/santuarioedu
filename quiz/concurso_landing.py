"""
Configuracao das landing pages SEO por concurso.

Cada concurso vira uma URL indexavel (/concurso/<slug>/) com H1, meta
description e copy adaptados ao termo de busca especifico. Longtail SEO:
"concurso PRF", "concurso INSS 2025" tem menos concorrencia que o generico
"plataforma de estudos".

Adicionar novo concurso = adicionar dict aqui. Zero mudanca de view/template.
"""

CONCURSOS_LANDING = {
    'prf': {
        'nome':          'PRF',
        'nome_completo': 'Polícia Rodoviária Federal',
        'h1':            'Estudo pra PRF com IA',
        'subtitulo':     'Prepare-se pra Polícia Rodoviária Federal com banco de questões oficiais, simulados cronometrados e IA que analisa seus erros.',
        'meta_desc':     'Plataforma completa pra concurso PRF: questões Cebraspe/FGV, simulados cronometrados no formato oficial, IA que corrige e explica seus erros. Grátis pra começar.',
        'disciplinas': [
            'Direito Constitucional',
            'Direito Administrativo',
            'Direito Penal',
            'Legislação de Trânsito',
            'Português',
            'Raciocínio Lógico',
            'Informática',
        ],
        'bancas':      ['Cebraspe', 'FGV'],
        'palavra_chave': 'concurso PRF',
    },
    'pf': {
        'nome':          'Polícia Federal',
        'nome_completo': 'Polícia Federal',
        'h1':            'Estudo pra Polícia Federal com IA',
        'subtitulo':     'Prepare-se pra PF (Agente, Escrivão, Delegado) com questões oficiais, simulados cronometrados e IA que aprende com você.',
        'meta_desc':     'Concurso Polícia Federal: banco de questões Cebraspe, simulados no formato PF, IA que corrige erros. Grátis pra começar sem cartão.',
        'disciplinas': [
            'Direito Constitucional',
            'Direito Administrativo',
            'Direito Penal',
            'Direito Processual Penal',
            'Português',
            'Informática',
            'Legislação Específica',
        ],
        'bancas':      ['Cebraspe'],
        'palavra_chave': 'concurso PF',
    },
    'inss': {
        'nome':          'INSS',
        'nome_completo': 'Técnico do Seguro Social',
        'h1':            'Estudo pra INSS com IA',
        'subtitulo':     'Prepare-se pra Técnico do Seguro Social com questões Cebraspe, simulados no formato oficial e IA que aponta seus gaps.',
        'meta_desc':     'Concurso INSS Técnico do Seguro Social: questões oficiais Cebraspe, simulados cronometrados, IA que explica erros. Comece grátis.',
        'disciplinas': [
            'Direito Constitucional',
            'Direito Administrativo',
            'Direito Previdenciário',
            'Ética no Serviço Público',
            'Português',
            'Raciocínio Lógico',
            'Informática',
        ],
        'bancas':      ['Cebraspe', 'CESGRANRIO'],
        'palavra_chave': 'concurso INSS',
    },
    'tjdf': {
        'nome':          'TJ-DF',
        'nome_completo': 'Tribunal de Justiça do Distrito Federal',
        'h1':            'Estudo pra TJ-DF com IA',
        'subtitulo':     'Prepare-se pra Tribunal de Justiça (Analista/Técnico) com banco de questões, simulados e IA adaptativa.',
        'meta_desc':     'Concurso TJ-DFT Analista e Técnico Judiciário: questões oficiais, simulados, IA que corrige. Grátis pra começar.',
        'disciplinas': [
            'Direito Constitucional',
            'Direito Administrativo',
            'Direito Civil',
            'Direito Processual Civil',
            'Direito Penal',
            'Português',
            'Regimento Interno',
        ],
        'bancas':      ['Cebraspe', 'FGV', 'IADES'],
        'palavra_chave': 'concurso TJ-DF',
    },
    'trf': {
        'nome':          'TRF',
        'nome_completo': 'Tribunal Regional Federal',
        'h1':            'Estudo pra TRF com IA',
        'subtitulo':     'Prepare-se pra Tribunais Regionais Federais (Analista/Técnico) com plataforma completa: questões, simulados e IA.',
        'meta_desc':     'Concurso TRF Analista e Técnico: banco de questões oficiais, simulados no formato Cebraspe, IA que analisa erros. Comece grátis.',
        'disciplinas': [
            'Direito Constitucional',
            'Direito Administrativo',
            'Direito Civil',
            'Direito Processual Civil',
            'Direito Penal',
            'Português',
            'Regimento dos TRFs',
        ],
        'bancas':      ['Cebraspe', 'FGV', 'CESGRANRIO'],
        'palavra_chave': 'concurso TRF',
    },
    'camara': {
        'nome':          'Câmara/Senado',
        'nome_completo': 'Câmara dos Deputados e Senado Federal',
        'h1':            'Estudo pra Câmara e Senado com IA',
        'subtitulo':     'Prepare-se pros concursos do Congresso Nacional (analistas e consultores) com questões oficiais e IA.',
        'meta_desc':     'Concurso Câmara dos Deputados e Senado Federal: questões oficiais, simulados FGV, IA que corrige e explica. Comece grátis.',
        'disciplinas': [
            'Direito Constitucional',
            'Direito Administrativo',
            'Regimento Interno',
            'Processo Legislativo',
            'Português',
            'Administração Pública',
        ],
        'bancas':      ['FGV', 'Cebraspe'],
        'palavra_chave': 'concurso Câmara Senado',
    },
    'enem': {
        'nome':          'ENEM',
        'nome_completo': 'Exame Nacional do Ensino Médio',
        'h1':            'Estudo pra ENEM com IA',
        'subtitulo':     'Prepare-se pra ENEM com banco de questões, simulados cronometrados e IA que identifica seus pontos fracos.',
        'meta_desc':     'ENEM 2025: banco de questões oficiais, simulados no formato ENEM (5h30), IA que corrige e propõe plano de estudos. Grátis pra começar.',
        'disciplinas': [
            'Linguagens e Códigos',
            'Ciências Humanas',
            'Ciências da Natureza',
            'Matemática',
            'Redação',
        ],
        'bancas':      ['INEP'],
        'palavra_chave': 'ENEM',
    },
}
