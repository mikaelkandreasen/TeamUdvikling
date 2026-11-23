FROM python:3.15-slim

ARG VERSION=dev
LABEL org.opencontainers.image.title="Team Udvikling" \
      org.opencontainers.image.description="Spillerudvikling for børnehold (DBU-roller x nøglefærdigheder)" \
      org.opencontainers.image.version="${VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TEAMUDVIKLING_DATA_DIR=/data

WORKDIR /app
RUN useradd --system --uid 10001 --create-home app && mkdir /data && chown app:app /data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY VERSION wsgi.py gunicorn.conf.py ./
COPY app ./app

USER app
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=4s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)" || exit 1

CMD ["gunicorn", "-c", "gunicorn.conf.py", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "30", "--limit-request-line", "4094", "--limit-request-fields", "50", "--access-logfile", "-", "wsgi:app"]
