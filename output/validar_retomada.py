"""Valida preparacao de deploy sem carregar .env nem usar o banco real.

Execute com o Python do projeto. Logs ficam em output/deploy_validation/.
Esta verificacao nao substitui o build Linux nem os testes de servicos externos.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path.cwd()


def main():
    output = ROOT / 'output' / 'validacao_retomada_20261020'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='validation-', dir=output) as directory:
        scratch = Path(directory)
        settings = '''import decouple
decouple.config = decouple.Config(decouple.RepositoryEmpty())
from prf_master.settings import *
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': %r}}
STATIC_ROOT = %r
MEDIA_ROOT = %r
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache', 'LOCATION': %r}}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
''' % tuple(str(scratch / name) for name in ['db.sqlite3', 'static', 'media', 'cache'])
        (scratch / 'validation_settings.py').write_text(settings, encoding='utf-8')
        env = {k: v for k, v in os.environ.items() if k.upper() in {
            'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'COMSPEC', 'PATHEXT',
        }}
        env.update(
            PYTHONPATH=str(scratch) + os.pathsep + str(ROOT),
            DJANGO_SETTINGS_MODULE='validation_settings', DEBUG='True',
            SECRET_KEY='validation-only-6qKzP9xL4mRt8sN2vW5yB7cD0eF3gH1jU9iO8pA',
            ALLOWED_HOSTS='localhost,127.0.0.1,testserver,healthcheck.railway.app',
            PYTHONIOENCODING='utf-8',
        )
        commands = [
            ['collectstatic', '--noinput'],
            ['test', 'quiz.tests.test_estudo_disponibilidade', 'quiz.tests.test_seguranca_regressao', '--verbosity=1', '--noinput'],
            ['migrate', '--noinput'],
            ['makemigrations', '--check', '--dry-run'],
            ['shell', '-c', "from django.test import Client; c=Client(); paths=['/','/health/','/accounts/login/','/robots.txt']; results=[(p,c.get(p,secure=True).status_code) for p in paths]; print(results); assert all(code==200 for _,code in results)"],
        ]
        results = []
        for args in commands:
            p = subprocess.run([sys.executable, str(ROOT / 'manage.py'), *args],
                               cwd=ROOT, env=env, capture_output=True, text=True,
                               encoding='utf-8', errors='replace')
            (output / (args[0] + '.log')).write_text(p.stdout + p.stderr, encoding='utf-8')
            results.append({'command': args, 'exit_code': p.returncode})
            print(args[0], p.returncode, (p.stdout + p.stderr)[-1200:], flush=True)
        (output / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    return int(any(r['exit_code'] for r in results))


if __name__ == '__main__':
    sys.exit(main())
