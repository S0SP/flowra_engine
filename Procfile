# Local development Procfile
# Use: heroku local OR honcho start
# Install: pip install honcho

web: gunicorn flowra_engine.wsgi:application --bind 0.0.0.0:8000 --reload
worker: celery -A flowra_engine worker --loglevel=info
beat: celery -A flowra_engine beat --loglevel=info
