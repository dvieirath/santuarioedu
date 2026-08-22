"""
Pacote quiz.views — dividido pra facilitar manutencao.

Estrutura:
    quiz/views/
        __init__.py       ← re-exporta tudo (compat total: from .views import x)
        _todos.py         ← views.py original (10.325 linhas)
        [futuros modulos] ← auth.py, coach.py, preparacao.py, etc.

Extracao incremental: mover funcoes de _todos.py pra modulos especificos
sem quebrar imports (o __init__.py re-exporta seja qual for a origem).
"""
# Compat total: import everything from _todos como se ainda fosse views.py
from ._todos import *  # noqa: F401,F403
