release: python manage.py migrate --noinput && python manage.py axes_reset
web: gunicorn prf_master.wsgi --bind 0.0.0.0:$PORT --workers 3 --threads 2 --timeout 60 --access-logfile - --error-logfile -
