pip install wger && wger create_settings && python manage.py makemigrations && python manage.py migrate && gunicorn wger.wsgi:application --log-file -
