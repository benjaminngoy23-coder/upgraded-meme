# FundFlow est une application Python autonome utilisant uniquement la bibliothèque standard.
# Aucun pip install, Flask ou Gunicorn n'est nécessaire.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DATA_DIR=/app/data \
    DB_FILE=fundflow_stable.db

WORKDIR /app

# La base SQLite et les journaux sont conservés dans /app/data.
RUN mkdir -p /app/data

# L'application complète tient dans ce fichier.
COPY app.py /app/app.py

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health', timeout=4).read()" || exit 1

STOPSIGNAL SIGTERM
CMD ["python", "/app/app.py", "--no-browser"]
