"""Importa justificativas autorais sem qualquer chamada a APIs de geração."""
import json
import argparse
import os
from pathlib import Path
import re
import sqlite3
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prf_master.settings')
os.environ['SENTRY_DSN'] = ''
import django
django.setup()
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from quiz.models import Questao

BASE = ROOT / 'docs' / 'geracao_justificativas'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entradas', nargs='+', default=['lote_codex_01_entrada.json', 'lote_codex_02_entrada.json'])
    parser.add_argument('--respostas', default='lote_codex_01_respostas.json')
    parser.add_argument('--validar', action='store_true', help='Valida o lote sem gravar no banco.')
    args = parser.parse_args()
    source = {}
    for filename in args.entradas:
        source.update({r['id']: r for r in json.loads((BASE / filename).read_text(encoding='utf-8'))})
    answers = json.loads((BASE / args.respostas).read_text(encoding='utf-8'))
    assert len({r['id'] for r in answers}) == len(answers)
    for r in answers:
        old = source[r['id']]
        correct = [a for a in old['alternativas'] if a['correta']]
        assert len(correct) == 1
        if old['tipo'] == 'CE':
            heads = ['🔍 Por que a resposta é ' + correct[0]['texto'].upper(),
                     '⚠️ O erro típico', '🧠 Conceito-chave', '📚 Onde aprofundar', '💡 Padrão a memorizar']
        else:
            heads = ['🔍 Por que a resposta é essa', '⚠️ Armadilhas', '🧠 Conceito-chave',
                     '🎯 O que esta questão testa', '📚 Onde aprofundar', '💡 Padrão a memorizar']
        assert re.findall(r'^## (.+)$', r['justificativa'], re.M) == heads, r['id']
        assert all(len(s.strip()) > 25 for s in re.split(r'^## .+$', r['justificativa'], flags=re.M)[1:])
    if args.validar:
        print(json.dumps({'validadas': len(answers), 'respostas': args.respostas}))
        return
    db = Path(settings.DATABASES['default']['NAME']).resolve()
    assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'
    assert db == ROOT / 'db.sqlite3'
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup = ROOT / 'backups' / f'antes_lote_codex_{stamp}.sqlite3'
    with sqlite3.connect(str(db)) as src, sqlite3.connect(str(backup)) as dest:
        src.backup(dest)
        assert dest.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    saved, skipped = [], []
    with transaction.atomic():
        for row in answers:
            old = source[row['id']]
            q = Questao.objects.filter(pk=row['id']).first()
            if (q is None or q.justificativa or q.rejeitada_definitiva or q.imagem or
                    q.texto != old['texto'] or q.tipo != old['tipo'] or
                    list(q.alternativa_set.order_by('id').values('id', 'texto', 'correta')) != old['alternativas']):
                skipped.append(row['id'])
                continue
            Questao.objects.filter(pk=q.pk).update(justificativa=row['justificativa'])
            assert Questao.objects.get(pk=q.pk).justificativa == row['justificativa']
            saved.append(q.pk)
    pending = Questao.objects.filter(Q(justificativa__isnull=True) | Q(justificativa='')).exclude(rejeitada_definitiva=True).count()
    result = dict(salvas=len(saved), ids_salvos=saved, ignoradas=skipped, pendentes=pending,
                  entradas=args.entradas, respostas=args.respostas,
                  backup=str(backup), origem='Redação direta pelo Codex; sem Groq/Gemini')
    (BASE / f'resultado_codex_{stamp}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    main()
