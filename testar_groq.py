"""
Teste autônomo do provider Groq — não depende de Django nem cryptography.
Roda com: python testar_groq.py
"""
import json
import sys
import time
import urllib.error
import urllib.request


def testar(api_key, modelo='llama-3.3-70b-versatile'):
    print(f'═══ Testando Groq · modelo {modelo} ═══\n')

    payload = {
        'model': modelo,
        'messages': [
            {'role': 'user',
             'content': 'Em UMA frase, explique o art. 5º da CF/88 (princípio da igualdade).'}
        ],
        'temperature': 0.7,
        'max_tokens': 200,
    }

    req = urllib.request.Request(
        'https://api.groq.com/openai/v1/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'SantuarioEdu/1.0 (Python urllib)',
        },
    )

    inicio = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f'❌ Erro HTTP {e.code}')
        print(body[:500])
        return False
    except Exception as e:
        print(f'❌ Erro: {e}')
        return False

    latencia = time.time() - inicio
    texto = data['choices'][0]['message']['content']
    uso = data.get('usage', {})

    print(f'✅ Sucesso em {latencia:.2f}s')
    print(f'   Tokens: {uso.get("total_tokens", "?")} '
          f'(prompt {uso.get("prompt_tokens", "?")} + completion {uso.get("completion_tokens", "?")})')
    print(f'\nResposta:\n{texto}\n')
    return True


if __name__ == '__main__':
    # Lê do .env manualmente
    api_key = None
    try:
        with open('.env', encoding='utf-8') as f:
            for linha in f:
                if linha.startswith('GROQ_API_KEY='):
                    api_key = linha.split('=', 1)[1].strip().strip('"').strip("'")
                    break
    except Exception:
        pass

    if not api_key:
        print('❌ GROQ_API_KEY não encontrada no .env')
        print('   Pegue uma em https://console.groq.com/keys')
        sys.exit(1)

    if not testar(api_key):
        sys.exit(1)
