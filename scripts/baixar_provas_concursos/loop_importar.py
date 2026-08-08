#!/usr/bin/env python3
"""
Wrapper que roda importar_manifesto.py em loop, esperando cota IA resetar.

Loop:
1. Roda importar_manifesto.py
2. Se completou tudo (retorno 0 sem "[PAUSADO]"): SAI
3. Se pausou por cota: espera WAIT_MINUTOS e tenta de novo
4. Se erro real: retenta ate MAX_RETRIES seguidos

Uso:
    python scripts/baixar_provas_concursos/loop_importar.py
    python scripts/baixar_provas_concursos/loop_importar.py --wait 30    # 30min entre tentativas
    python scripts/baixar_provas_concursos/loop_importar.py --max_horas 12  # roda no maximo 12h
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PY_VENV = RAIZ.parent.parent / 'venv' / 'Scripts' / 'python.exe'
IMPORTAR_MANIFESTO = RAIZ / 'importar_manifesto.py'
LOG_FILE = RAIZ.parent.parent / 'provas_pdf' / 'materia_prima' / 'loop_importar.log'


def timestamp() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def log(msg: str, tee_stdout: bool = True) -> None:
    linha = f'[{timestamp()}] {msg}'
    if tee_stdout:
        print(linha, flush=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(linha + '\n')


def executar_uma_rodada() -> tuple[str, str]:
    """
    Roda importar_manifesto.py uma vez.
    Retorna (status, output_final):
      status: 'concluido' | 'pausado_cota' | 'erro' | 'timeout'
      output_final: ultimas linhas do stdout
    """
    python_exe = str(PY_VENV) if PY_VENV.exists() else sys.executable
    log(f'Rodando importar_manifesto.py (python: {python_exe})')

    try:
        result = subprocess.run(
            [python_exe, str(IMPORTAR_MANIFESTO)],
            cwd=str(RAIZ.parent.parent),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=6 * 3600,  # 6h max por rodada
        )
        output = result.stdout + result.stderr
        # Detecta "[PAUSADO]" no output
        if '[PAUSADO]' in output:
            return 'pausado_cota', output[-500:]
        if result.returncode == 0:
            return 'concluido', output[-500:]
        return 'erro', f'retcode={result.returncode}\n{output[-500:]}'
    except subprocess.TimeoutExpired:
        return 'timeout', 'Rodada excedeu 6h'
    except Exception as e:
        return 'erro', f'Excecao: {e}'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--wait', type=int, default=30,
                        help='Minutos de espera entre tentativas apos cota (default 30)')
    parser.add_argument('--max_horas', type=float, default=24,
                        help='Tempo maximo total em horas (default 24h)')
    parser.add_argument('--max_retries_erro', type=int, default=3,
                        help='Max tentativas seguidas em erro real (default 3)')
    args = parser.parse_args()

    limite = datetime.now() + timedelta(hours=args.max_horas)
    tentativa = 0
    erros_seguidos = 0

    log('=' * 70)
    log(f'INICIO — loop_importar.py')
    log(f'  wait={args.wait}min, max_horas={args.max_horas}h, max_erros_seguidos={args.max_retries_erro}')
    log(f'  Termina em: {limite.strftime("%Y-%m-%d %H:%M:%S")}')
    log('=' * 70)

    while datetime.now() < limite:
        tentativa += 1
        log(f'\n─── Tentativa {tentativa} ───')

        status, output = executar_uma_rodada()

        if status == 'concluido':
            log('✓ CONCLUIDO! Todas as provas do manifesto foram processadas.')
            log(output[-300:])
            return 0

        if status == 'pausado_cota':
            log(f'⏸  Pausou por cota. Esperando {args.wait} minutos...')
            erros_seguidos = 0
            time.sleep(args.wait * 60)
            continue

        if status == 'erro':
            erros_seguidos += 1
            log(f'✗ Erro (seguidos: {erros_seguidos}/{args.max_retries_erro})')
            log(output[-300:])
            if erros_seguidos >= args.max_retries_erro:
                log(f'MAX_RETRIES atingido. Abortando.')
                return 1
            # backoff exponencial em erros: 5, 10, 20 min
            wait_erro = 5 * (2 ** (erros_seguidos - 1))
            log(f'Backoff de {wait_erro} minutos antes de tentar novamente...')
            time.sleep(wait_erro * 60)
            continue

        if status == 'timeout':
            log('⚠️  Timeout na rodada. Reiniciando em 5min...')
            time.sleep(5 * 60)
            continue

    log(f'\n⏱  Tempo maximo ({args.max_horas}h) atingido. Saindo.')
    log('Rode de novo pra continuar de onde parou.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
