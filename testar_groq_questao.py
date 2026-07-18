"""Teste avançado: pede ao Groq que gere uma questão de concurso completa em JSON."""
import json, sys, time, urllib.request


def chamar_groq(prompt, json_mode=False):
    api_key = None
    with open('.env', encoding='utf-8') as f:
        for linha in f:
            if linha.startswith('GROQ_API_KEY='):
                api_key = linha.split('=', 1)[1].strip()
                break

    payload = {
        'model': 'llama-3.3-70b-versatile',
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.4,
        'max_tokens': 1500,
    }
    if json_mode:
        payload['response_format'] = {'type': 'json_object'}

    req = urllib.request.Request(
        'https://api.groq.com/openai/v1/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'SantuarioEdu/1.0',
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


prompt = '''Gere 1 questão de Direito Constitucional para concurso PRF (banca Cebraspe).
Use múltipla escolha com 5 alternativas (A-E), apenas 1 correta.

Retorne JSON com este formato exato:
{
  "enunciado": "...",
  "alternativas": [
    {"letra":"A","texto":"...","correta":false},
    {"letra":"B","texto":"...","correta":true},
    {"letra":"C","texto":"...","correta":false},
    {"letra":"D","texto":"...","correta":false},
    {"letra":"E","texto":"...","correta":false}
  ],
  "justificativa": "explicação com base legal/artigo",
  "assunto": "tópico"
}'''

inicio = time.time()
resp = chamar_groq(prompt, json_mode=True)
elapsed = time.time() - inicio

texto = resp['choices'][0]['message']['content']
uso = resp['usage']
data = json.loads(texto)

print(f'═══ Questão gerada em {elapsed:.2f}s ({uso["total_tokens"]} tokens) ═══\n')
print(f'Assunto: {data.get("assunto")}\n')
print(f'Enunciado:\n{data.get("enunciado")}\n')
print('Alternativas:')
for a in data.get('alternativas', []):
    m = '✓' if a.get('correta') else ' '
    print(f"  [{m}] {a.get('letra')}) {a.get('texto')}")
print(f'\nJustificativa:\n{data.get("justificativa")}')
