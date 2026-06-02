"""Configuration helpers for the llm_sql package.

Uses pydantic BaseSettings to validate and load environment variables.
Supports a local `.env` file for development via `python-dotenv`.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


class SettingsError(RuntimeError):
    """Raised when required runtime settings are missing."""


class Settings(BaseSettings):
    # Runtime-required settings (validated via require_runtime_settings).
    glue_db_name: str | None = Field(None, env='GLUE_DB_NAME')
    project_files_bucket: str | None = Field(None, env='PROJECT_FILES_BUCKET')
    region: str = Field('eu-north-1', env='AWS_REGION')

    # Bedrock / LLM configuration (use inference profile IDs in EU/US, e.g. eu.amazon.nova-micro-v1:0)
    bedrock_model: str = Field('eu.amazon.nova-micro-v1:0', env='BEDROCK_MODEL')
    bedrock_max_retries: int = Field(4, env='BEDROCK_MAX_RETRIES', ge=1)
    bedrock_retry_base_delay: float = Field(1.0, env='BEDROCK_RETRY_BASE_DELAY', gt=0)

    # Athena / query settings
    athena_workgroup: str = Field('primary', env='ATHENA_WORKGROUP')
    # Set true when the workgroup uses Athena managed query results (no S3 output path).
    athena_use_managed_results: bool | None = Field(None, env='ATHENA_USE_MANAGED_RESULTS')
    # Optional Secrets Manager secret containing credentials or overrides.
    secrets_manager_secret: str | None = Field(None, env='SECRETS_MANAGER_SECRET')
    max_result_rows: int = Field(200, env='MAX_RESULT_ROWS', ge=1, le=10000)
    max_question_chars: int = Field(1000, env='MAX_QUESTION_CHARS', ge=64, le=10000)
    log_level: str = Field('INFO', env='LOG_LEVEL')

    # HTTP API (ECS Fargate)
    api_port: int = Field(8080, env='PORT', ge=1024, le=65535)
    api_key: str | None = Field(None, env='API_KEY')

    @field_validator('log_level')
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if normalized not in allowed:
            raise ValueError(
                'LOG_LEVEL must be one of: '
                + ', '.join(sorted(allowed))
            )
        return normalized

    model_config = {
        'env_file': '.env',
        'env_file_encoding': 'utf-8',
        'extra': 'ignore',
    }


def resolve_bedrock_model(model: str, region: str) -> str:
    """Map legacy foundation-model IDs to regional inference profiles when needed."""
    if model.count('.') >= 2 and model.split('.')[0] in {
        'eu', 'us', 'ap', 'global', 'us-gov', 'us-iso', 'us-isob',
    }:
        return model
    legacy_to_profile = {
        'amazon.nova-micro-v1:0': {
            'eu': 'eu.amazon.nova-micro-v1:0',
            'us': 'us.amazon.nova-micro-v1:0',
        },
        'amazon.nova-lite-v1:0': {
            'eu': 'eu.amazon.nova-lite-v1:0',
            'us': 'us.amazon.nova-lite-v1:0',
        },
        'amazon.nova-pro-v1:0': {
            'eu': 'eu.amazon.nova-pro-v1:0',
            'us': 'us.amazon.nova-pro-v1:0',
        },
    }
    prefix = region.split('-', 1)[0]
    mapped = legacy_to_profile.get(model, {}).get(prefix)
    return mapped or model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings loaded from environment and optional .env."""
    return Settings()


def require_runtime_settings(settings: Settings | None = None) -> Settings:
    """Ensure required runtime settings are present before executing queries."""
    runtime_settings = settings or get_settings()
    required = {
        'glue_db_name': 'GLUE_DB_NAME',
        'project_files_bucket': 'PROJECT_FILES_BUCKET',
    }
    missing = [
        env_name for attr_name, env_name in required.items()
        if not getattr(runtime_settings, attr_name)
    ]
    if missing:
        raise SettingsError(
            'Missing required configuration: '
            + ', '.join(missing)
            + '. Set them as environment variables or in a .env file.'
        )
    return runtime_settings


settings = get_settings()