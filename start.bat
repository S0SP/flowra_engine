@echo off
echo Starting Flowra Engine (Django + Celery Worker + Celery Beat)...
echo.

:: Start Django server in new window
start "Flowra Django" cmd /k "cd /d d:\wa\flowra-engine && venv\Scripts\activate && python manage.py runserver 0.0.0.0:8001"

:: Wait 2 seconds for Django to start
timeout /t 2 /nobreak >nul

:: Start Celery Worker (--pool=solo required for Windows)
start "Flowra Celery Worker" cmd /k "cd /d d:\wa\flowra-engine && venv\Scripts\activate && celery -A flowra_engine worker --loglevel=info --pool=solo"

:: Wait 2 seconds
timeout /t 2 /nobreak >nul

:: Start Celery Beat scheduler
start "Flowra Celery Beat" cmd /k "cd /d d:\wa\flowra-engine && venv\Scripts\activate && celery -A flowra_engine beat --loglevel=info"

echo.
echo All 3 processes started in separate windows!
echo   - Django:        http://localhost:8001
echo   - Celery Worker: processing tasks
echo   - Celery Beat:   polling sheets every 60s
pause
