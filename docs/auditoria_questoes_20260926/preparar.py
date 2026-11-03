"""Gera plano conservador a partir do levantamento; não altera o banco."""
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
rows = json.loads((BASE / 'levantamento.json').read_text(encoding='utf-8'))
contexto = set(map(int, '46 149 534 1137 1138 3208 3468 3639 3640 4210 6402'.split()))
imagens = set(map(int, '''544 668 669 670 671 718 719 892 915 917 920
1066 1068 1080 1152 1153 1180 1181 1182 1183 1184 1185 1186 1187 1223 1237
1255 1256 1257 1258 1263 1472 1473 1509 1510 1609 1732 1962 2070 2071 2074 2075 2077
2243 2244 2272 2753 2879 2890 2922 2976 2977 2978 2997 3003 3018 3051 3052
3104 3107 3191 3206 3209 3215 3666 3680 3686 3690 3691 3696 3787 3794 3815
3947 3956 3960 3961 3988 3990 4149 4482 4494 4583 4593
5279 5280 5281 5282 5283 5427 5428 5429 5430 5604 5607 5880 5954 5962 5963
6022 6025 6036 6037 6108 6109 6110 6111 6112 6113 6119 6123
6170 6171 6172 6173 6174 6175 6176
6587 6588 6589 6590 6591 6592 6593 6597 6598 6599 6600 6601 6602 6603
6623 6638 6639 6640 6670 6671 6672 6673 6674 6675 6676 6680 6692 6693 6694
6892 6893 6895'''.split()))
plan = []
for row in rows:
    reasons = []
    alts = row['alternativas']
    if not re.sub(r'<[^>]*>|\s|&nbsp;', '', row['texto']):
        reasons.append('Enunciado vazio')
    if len(alts) < 2:
        reasons.append('Menos de duas alternativas')
    if sum(bool(a['correta']) for a in alts) != 1:
        reasons.append('Gabarito ausente ou múltiplo')
    texts = [' '.join(a['texto'].split()) for a in alts]
    if len(texts) != len(set(texts)):
        reasons.append('Alternativas com texto idêntico (preservada a distinção de maiúsculas)')
    if any(not t for t in texts):
        reasons.append('Alternativa vazia')
    content = row['texto'] + '\n' + '\n'.join(texts)
    if re.search(r'/g(?:\d|⃗)|∈g\d|\[(?:fórmula )?ilegível\]|\[FIGURA:\s*ausente\]', content, re.I):
        reasons.append('Extração corrompida: códigos de glifos ou conteúdo explicitamente ilegível/ausente')
    if row['id'] in contexto:
        reasons.append('Enunciado sem o texto, a definição ou a situação indispensável')
    if row['id'] in imagens and not row['imagem']:
        reasons.append('Figura, tabela, gráfico ou fórmula indispensável ausente; conferência manual')
    if row['id'] == 12105:
        reasons.append('Erro claro de redação: repetição acidental «devido devido»')
    if reasons:
        plan.append({'id': row['id'], 'motivos': reasons, 'original': row})
(BASE / 'plano_remocao.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'{len(rows)} questões analisadas; {len(plan)} selecionadas para remoção.')
