FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

# Run as a non-root user.
RUN useradd --create-home appuser
USER appuser

# Cloud Run sets $PORT. One worker with threads keeps memory low; Document AI
# calls can take several seconds, hence the long timeout.
CMD exec gunicorn --bind :${PORT:-8080} --workers 1 --threads 8 --timeout 120 app:app
