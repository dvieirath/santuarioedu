"""
Aprova em lote as questoes IA que ja tem justificativa e sem defeitos graves.

Uso:
    # A partir do diretorio raiz do projeto (com venv ativo)
    python scripts/manutencao/aprovar_ia_com_just.py

Regras:
- So mexe em questoes com gerada_por_ia=True, revisada=False, rejeitada_definitiva=False
- Ignora questoes sem justificativa (precisam do gerar_justificativas_ia primeiro)
- Aprova (revisada=True) se nao tem flags graves alem das toleraveis
- Mantem pendente o que tem defeito real (imagem/texto ausente, sem gabarito, etc)

Flags toleraveis (nao impedem aprovacao):
- letras_flutuantes (sequencias curtas podem ser acronimos)
- espacos_duplicados / espaco_antes_pontuacao / palavras_duplicadas (formatacao)
- caracteres_repetidos (idem)
"""
import os
import sys
import django

# Descobre raiz do projeto (2 niveis acima)
_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_this_dir, '..', '..'))
sys.path.insert(0, _project_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prf_master.settings')
django.setup()

from django.db import transaction
from django.db.models import Q
from quiz.models import Questao
from quiz.auditoria import detectar_flags

FLAGS_TOLERAVEIS = {
    'letras_flutuantes',
    'espacos_duplicados',
    'espaco_antes_pontuacao',
    'palavras_duplicadas',
    'caracteres_repetidos',
}

qs_com_just = Questao.objects.filter(
    gerada_por_ia=True, revisada=False, rejeitada_definitiva=False,
).exclude(Q(justificativa='') | Q(justificativa__isnull=True))

print(f'[aprovar_ia_com_just] Candidatas: {qs_com_just.count()}')

aprovadas = 0
mantidas = 0
motivos = {}
por_cat = {}

with transaction.atomic():
    for q in qs_com_just.prefetch_related('alternativa_set').select_related('categoria'):
        alts = list(q.alternativa_set.all())
        flags = set(detectar_flags(q, alts))
        graves = flags - FLAGS_TOLERAVEIS
        cat = q.categoria.nome if q.categoria_id else '(sem)'
        if not graves:
            q.revisada = True
            q.save(update_fields=['revisada'])
            aprovadas += 1
            por_cat.setdefault(cat, [0, 0])
            por_cat[cat][0] += 1
        else:
            mantidas += 1
            por_cat.setdefault(cat, [0, 0])
            por_cat[cat][1] += 1
            for f in graves:
                motivos[f] = motivos.get(f, 0) + 1

print(f'APROVADAS: {aprovadas}')
print(f'MANTIDAS pendentes (defeitos reais): {mantidas}')
if motivos:
    print('\nMotivos de nao aprovacao:')
    for f, n in sorted(motivos.items(), key=lambda x: -x[1]):
        print(f'  {n:>4} - {f}')
print('\nPor categoria:')
for cat, (apr, mant) in sorted(por_cat.items(), key=lambda x: -x[1][0]):
    print(f'  {cat[:35]:<35} aprovadas={apr:>3} mantidas={mant:>3}')

total_rev = Questao.objects.filter(revisada=True).count()
total_rev_ia = Questao.objects.filter(revisada=True, gerada_por_ia=True).count()
print(f'\nTotal revisadas: {total_rev} (IA={total_rev_ia})')
