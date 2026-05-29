FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY src /app/src
COPY scripts /app/scripts
USER app
ENTRYPOINT ["python", "/app/scripts/run_query.py"]
