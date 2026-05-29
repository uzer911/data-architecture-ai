from __future__ import annotations

from typing import Iterable

from langchain_community.utilities import SQLDatabase
from sqlalchemy import create_engine
from .config import get_settings
from .core import LLMSQLService, parse_catalog


def make_athena_connection_string(
    glue_db_name: str,
    project_files_bucket: str,
    region: str | None = None,
    athena_workgroup: str = 'primary',
) -> str:
    runtime_settings = get_settings()
    region = region or runtime_settings.region or 'eu-north-1'
    connathena = f'athena.{region}.amazonaws.com'
    port = '443'
    s3_staging = f's3://{project_files_bucket}/athenaresults/'
    return (
        f'awsathena+rest://@{connathena}:{port}/{glue_db_name}'
        f'?s3_staging_dir={s3_staging}&work_group={athena_workgroup}'
    )


def create_athena_engine(
    glue_db_name: str,
    project_files_bucket: str,
    region: str | None = None,
    athena_workgroup: str = 'primary',
):
    connection_string = make_athena_connection_string(
        glue_db_name=glue_db_name,
        project_files_bucket=project_files_bucket,
        region=region,
        athena_workgroup=athena_workgroup,
    )
    return create_engine(connection_string, echo=False, pool_pre_ping=True)


def build_athena_service(
    glue_db_names: Iterable[str],
    project_files_bucket: str,
    *,
    region: str | None = None,
    athena_workgroup: str = 'primary',
    bedrock_model: str | None = None,
    max_retries: int | None = None,
    retry_base_delay: float | None = None,
    secrets_manager_secret: str | None = None,
) -> LLMSQLService:
    glue_db_names = list(glue_db_names)
    if not glue_db_names:
        raise ValueError('At least one Glue database name must be provided.')
    runtime_settings = get_settings()
    region = region or runtime_settings.region or 'eu-north-1'
    glue_db_name = glue_db_names[0]
    engine = create_athena_engine(
        glue_db_name=glue_db_name,
        project_files_bucket=project_files_bucket,
        region=region,
        athena_workgroup=athena_workgroup,
    )
    db = SQLDatabase(engine)
    glue_catalog, allowed_tables = parse_catalog(glue_db_names, region=region)

    return LLMSQLService(
        db=db,
        glue_catalog=glue_catalog,
        allowed_tables=allowed_tables,
        bedrock_model=bedrock_model or runtime_settings.bedrock_model,
        region=region,
        max_retries=max_retries if max_retries is not None else runtime_settings.bedrock_max_retries,
        retry_base_delay=(
            retry_base_delay
            if retry_base_delay is not None
            else runtime_settings.bedrock_retry_base_delay
        ),
        secrets_manager_secret=(
            secrets_manager_secret
            if secrets_manager_secret is not None
            else runtime_settings.secrets_manager_secret
        ),
        max_result_rows=runtime_settings.max_result_rows,
        max_question_chars=runtime_settings.max_question_chars,
    )
