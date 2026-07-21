release: python manage.py migrate --noinput && python manage.py axes_reset && (python manage.py createsuperuser --noinput || true) && (gunzip -f data_export/backup_quiz.json.gz && python manage.py loaddata data_export/backup_quiz.json || true)
web: gunicorn prf_master.wsgi --bind 0.0.0.0:$PORT --workers 3 --threads 2 --timeout 60 --access-logfile - --error-logfile -
