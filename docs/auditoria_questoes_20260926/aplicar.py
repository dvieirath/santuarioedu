"""Inspeciona impacto; --apply salva backup e aplica somente registros inalterados."""
import os
import sys
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prf_master.settings')
os.environ['SENTRY_DSN'] = ''
import django
django.setup()
from django.conf import settings
from django.core import serializers
from django.db import transaction
from django.db.models.deletion import Collector
from quiz.models import Questao

BASE = Path(__file__).resolve().parent
db = Path(settings.DATABASES['default']['NAME']).resolve()
assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'
assert db == ROOT / 'db.sqlite3'
plan = json.loads((BASE / 'plano_remocao.json').read_text(encoding='utf-8'))

def unchanged(q, original):
    fields = {'id': q.pk, 'categoria': q.categoria.nome, 'texto': q.texto,
              'imagem': str(q.imagem or ''), 'tipo': q.tipo,
              'justificativa': q.justificativa, 'revisada': q.revisada}
    return (all(original[k] == v for k, v in fields.items()) and
            sorted(original['alternativas'], key=lambda a: a['id']) ==
            list(q.alternativa_set.order_by('id').values('id', 'texto', 'correta')))

def eligible():
    originals = {p['id']: p['original'] for p in plan}
    return [q for q in Questao.objects.filter(pk__in=originals).select_related('categoria')
            if unchanged(q, originals[q.pk])]

def impact(qs):
    collector = Collector(using='default')
    collector.collect(qs)
    counts = Counter({m._meta.label: len(items) for m, items in collector.data.items()})
    for qs in collector.fast_deletes:
        counts[qs.model._meta.label] += qs.count()
    return collector, dict(counts)

selected = eligible()
collector, counts = impact(selected)
print(json.dumps({'elegiveis': len(selected), 'impacto': counts}, ensure_ascii=False))
if '--apply' not in sys.argv:
    sys.exit(0)

stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup = ROOT / 'backups' / f'antes_limpeza_questoes_{stamp}.sqlite3'
backup.parent.mkdir(exist_ok=True)
with sqlite3.connect(str(db)) as source, sqlite3.connect(str(backup)) as target:
    source.backup(target)
    assert target.execute('PRAGMA quick_check').fetchone()[0] == 'ok'

with transaction.atomic():
    selected = eligible()
    collector, counts = impact(selected)
    # Guarda também todas as dependências excluídas para recuperação pontual.
    objects = [obj for values in collector.data.values() for obj in values]
    for qs in collector.fast_deletes:
        objects.extend(qs)
    (BASE / f'registros_excluidos_{stamp}.json').write_text(
        serializers.serialize('json', objects, indent=2), encoding='utf-8')
    before = Questao.objects.count()
    ids = [q.pk for q in selected]
    deleted, actual = Questao.objects.filter(pk__in=ids).delete()
    assert not Questao.objects.filter(pk__in=ids).exists()
    after = Questao.objects.count()
    assert before - after == len(ids)

result = {'backup': str(backup), 'antes': before, 'depois': after,
          'questoes_removidas': len(ids), 'ids_removidos': ids,
          'ignorados_por_alteracao_ou_ausencia': sorted(set(p['id'] for p in plan) - set(ids)),
          'exclusoes_por_modelo': actual}
(BASE / 'resultado.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
reasons = Counter(r for p in plan if p['id'] in ids for r in p['motivos'])
lines = ['# Auditoria do banco de questões', '',
         'Todas as 12.568 questões do levantamento passaram pela triagem estrutural. '
         'Os indícios de imagens ausentes foram conferidos manualmente. '
         'Esta análise não certifica a correção de todos os gabaritos nem substitui revisão pedagógica integral.', '',
         f'Questões removidas: {len(ids)}. Banco antes: {before}; depois: {after}.',
         f'Backup integral: `{backup}`.', '',
         'Registros alterados depois do levantamento foram preservados. '
         'Questões sem justificativa, afirmações falsas intencionais e dúvidas de conteúdo não foram excluídas por esses motivos.', '',
         '## Motivos (uma questão pode ter mais de um)', '']
lines.extend(f'- {r}: {n}' for r, n in reasons.items())
lines += ['', '## Registros removidos', '']
lines.extend(f"- {p['id']}: {'; '.join(p['motivos'])}." for p in plan if p['id'] in ids)
(BASE / 'relatorio.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k != 'ids_removidos'}, ensure_ascii=False))
