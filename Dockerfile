FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    PORT=8080
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY src /app/src
COPY scripts /app/scripts
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"
ENTRYPOINT ["python", "/app/scripts/serve.py"]
