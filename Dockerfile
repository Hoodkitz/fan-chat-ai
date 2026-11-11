FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
RUN useradd -r -u 10001 app && mkdir -p /app/var/exports && chown -R app /app/var
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
# Migrationen separat als Owner ausfuehren: docker run ... alembic upgrade head
# Behind a reverse proxy set FORWARDED_ALLOW_IPS to the proxy address, so IP rate limits see real clients.
ENV FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
