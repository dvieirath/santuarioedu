#!/usr/bin/env bash
# Script de build executado pelas plataformas (Render, Railway).
set -o errexit

echo "==> Instalando dependências"
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Coletando arquivos estáticos"
python manage.py collectstatic --noinput --clear

echo "==> Aplicando migrations"
python manage.py migrate --noinput

echo "==> Build OK"
