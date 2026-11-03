"""Relatório somente leitura do SQLite local; não importa settings nem chama IA."""
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quiz.auditoria import detectar_flags


def main():
    destino = ROOT / 'output' / ('auditoria_banco_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    destino.mkdir(parents=True, exist_ok=False)
    db = sqlite3.connect((ROOT / 'db.sqlite3').as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    alternativas = defaultdict(list)
    for linha in db.execute('SELECT questao_id, texto, correta FROM quiz_alternativa'):
        alternativas[linha['questao_id']].append(SimpleNamespace(**dict(linha)))
    questoes = [dict(r) for r in db.execute('SELECT q.*, c.nome AS categoria_nome FROM quiz_questao q JOIN quiz_categoria c ON c.id=q.categoria_id')]
    contagem = Counter()
    pendencias = []
    textos = defaultdict(list)
    for q in questoes:
        liberada = bool(q['revisada'] and not q['rejeitada_definitiva'])
        contagem['total'] += 1
        contagem['liberadas'] += liberada
        contagem['rejeitadas'] += bool(q['rejeitada_definitiva'])
        contagem['liberadas_sem_justificativa'] += liberada and not (q['justificativa'] or '').strip()
        flags = detectar_flags(SimpleNamespace(**q), alternativas[q['id']])
        if flags:
            pendencias.append({'id': q['id'], 'categoria': q['categoria_nome'], 'liberada': liberada,
                               'sinais_para_revisao': flags})
        textos[' '.join(q['texto'].casefold().split())].append(q['id'])
    duplicatas = [ids for texto, ids in textos.items() if texto and len(ids) > 1]
    resumo = dict(contagem)
    resumo.update(gerado_em=datetime.now(timezone.utc).isoformat(),
                  questoes_com_sinais=len(pendencias), grupos_texto_repetido=len(duplicatas),
                  flags_liberadas=dict(Counter(f for p in pendencias if p['liberada'] for f in p['sinais_para_revisao'])))
    (destino / 'resumo.json').write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding='utf-8')
    (destino / 'pendencias.json').write_text(json.dumps(pendencias, ensure_ascii=False, indent=2), encoding='utf-8')
    (destino / 'textos_repetidos.json').write_text(json.dumps(duplicatas, indent=2), encoding='utf-8')
    (destino / 'LEIA-ME.md').write_text('# Auditoria de leitura\n\nSinais automáticos são candidatos à revisão, não confirmação de erro. Sem justificativa nesta heurística também inclui textos com menos de 50 caracteres; o resumo separa justificativas realmente vazias. Repetição de enunciado não prova duplicação: compare alternativas e contexto. Nenhum registro foi alterado e nenhuma IA foi chamada.\n', encoding='utf-8')
    db.close()
    print(destino)
    print(json.dumps(resumo, ensure_ascii=False))

if __name__ == '__main__':
    main()
