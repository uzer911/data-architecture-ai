"""HTTP API for the Text-to-SQL service."""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .config import SettingsError, get_settings, require_runtime_settings
from .runner import build_athena_service

logger = logging.getLogger(__name__)

app = FastAPI(title='Data Architecture AI', version='1.0.0')
_service = None
_service_error: Optional[str] = None


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=10000)


class QueryResponse(BaseModel):
    answer: str


class HealthResponse(BaseModel):
    status: str
    detail: Optional[str] = None


def _parse_glue_db_names(raw: str | None, fallback: str | None) -> list[str]:
    if raw:
        names = [part.strip() for part in raw.split(',') if part.strip()]
        if names:
            return names
    if fallback:
        return [fallback]
    return []


def get_service():
    """Lazy-init the query service so /health stays fast for ALB probes."""
    global _service, _service_error
    if _service is not None:
        return _service
    if _service_error is not None:
        raise RuntimeError(_service_error)

    settings = get_settings()
    try:
        runtime = require_runtime_settings(settings)
    except SettingsError as exc:
        _service_error = str(exc)
        raise RuntimeError(_service_error) from exc

    glue_db_names = _parse_glue_db_names(
        os.environ.get('GLUE_DB_NAMES'),
        runtime.glue_db_name,
    )
    if not glue_db_names:
        _service_error = 'No Glue database configured (GLUE_DB_NAME or GLUE_DB_NAMES).'
        raise RuntimeError(_service_error)

    try:
        _service = build_athena_service(
            glue_db_names,
            runtime.project_files_bucket,
            region=runtime.region,
            athena_workgroup=runtime.athena_workgroup,
        )
    except Exception as exc:
        logger.exception('Service initialization failed')
        _service_error = str(exc)
        raise RuntimeError(_service_error) from exc
    return _service


def reset_service_cache() -> None:
    """Clear cached service state (for tests)."""
    global _service, _service_error
    _service = None
    _service_error = None


def _check_api_key(x_api_key: Optional[str]) -> None:
    settings = get_settings()
    expected = settings.api_key
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail='Invalid or missing API key')


@app.get('/health', response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    try:
        require_runtime_settings(settings)
    except SettingsError as exc:
        return HealthResponse(status='degraded', detail=str(exc))
    return HealthResponse(status='ok')


@app.post('/query', response_model=QueryResponse)
def query(
    body: QueryRequest,
    x_api_key: Optional[str] = Header(default=None, alias='X-Api-Key'),
) -> QueryResponse:
    _check_api_key(x_api_key)
    try:
        service = get_service()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        answer = service.run_query(body.question)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('Query failed')
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return QueryResponse(answer=answer)
