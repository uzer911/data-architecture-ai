#!/usr/bin/env python3
"""CLI wrapper to run a natural-language question against the LLM→SQL service.

Example:
  GLUE_DB_NAME=mydb PROJECT_FILES_BUCKET=mybucket python scripts/run_query.py --question "How many books are in the library?"
"""
import argparse
import json
import logging
import sys
from typing import Optional

from sqlalchemy import create_engine, text

from llm_sql import LLMSQLService, parse_catalog
from llm_sql.config import SettingsError, get_settings, require_runtime_settings

logger = logging.getLogger(__name__)


def configure_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s %(name)s - %(message)s',
    )


def make_athena_engine(
    glue_db_name: str,
    project_files_bucket: str,
    region: Optional[str] = None,
    workgroup: Optional[str] = None,
):
    settings = get_settings()
    region = region or settings.region
    connathena = f'athena.{region}.amazonaws.com'
    portathena = '443'
    schemaathena = glue_db_name
    s3stagingathena = f's3://{project_files_bucket}/athenaresults/'
    wkgrpathena = workgroup or settings.athena_workgroup
    connection_string = (
        f'awsathena+rest://@{connathena}:{portathena}/{schemaathena}'
        f'?s3_staging_dir={s3stagingathena}/&work_group={wkgrpathena}'
    )
    engine = create_engine(connection_string, echo=False, pool_pre_ping=True)
    return engine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--question', '-q', required=True)
    parser.add_argument(
        '--json-output',
        action='store_true',
        help='Print the answer as JSON: {"answer": "..."}',
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)

    try:
        runtime_settings = require_runtime_settings(settings)
    except SettingsError as exc:
        logger.error('%s', exc)
        return 2

    try:
        engine = make_athena_engine(
            runtime_settings.glue_db_name,
            runtime_settings.project_files_bucket,
            runtime_settings.region,
        )
    except Exception as exc:
        logger.exception('Athena engine initialization failed')
        logger.error('%s', exc)
        return 3

    class SimpleDB:
        """Minimal DB wrapper providing a `run(sql)` method used by LLMSQLService."""

        def __init__(self, engine):
            self._engine = engine

        def run(self, sql: str):
            with self._engine.connect() as conn:
                res = conn.execute(text(sql))
                try:
                    rows = [dict(r._mapping) for r in res]
                except Exception:
                    rows = []
            return rows

    db = SimpleDB(engine)

    try:
        glue_catalog, allowed_tables = parse_catalog(
            [runtime_settings.glue_db_name],
            region=runtime_settings.region,
        )
    except Exception as exc:
        logger.exception('Glue catalog loading failed')
        logger.error('%s', exc)
        return 4

    service = LLMSQLService(
        db,
        glue_catalog,
        allowed_tables,
        region=runtime_settings.region,
        bedrock_model=runtime_settings.bedrock_model,
        max_retries=runtime_settings.bedrock_max_retries,
        retry_base_delay=runtime_settings.bedrock_retry_base_delay,
        secrets_manager_secret=runtime_settings.secrets_manager_secret,
        max_result_rows=runtime_settings.max_result_rows,
        max_question_chars=runtime_settings.max_question_chars,
    )

    try:
        answer = service.run_query(args.question)
    except Exception as exc:
        logger.exception('Query execution failed')
        logger.error('%s', exc)
        return 5

    if args.json_output:
        print(json.dumps({'answer': answer}, ensure_ascii=False))
    else:
        print(answer)
    return 0


if __name__ == '__main__':
    sys.exit(main())