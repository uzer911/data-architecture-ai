#!/usr/bin/env python3
"""CLI wrapper to run a natural-language question against the LLM→SQL service.

Example:
  GLUE_DB_NAME=mydb PROJECT_FILES_BUCKET=mybucket python scripts/run_query.py --question "How many books are in the library?"
"""
import argparse
import json
import logging
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(PROJECT_ROOT, 'src')
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from llm_sql.config import SettingsError, get_settings, require_runtime_settings
from llm_sql.runner import build_athena_service

logger = logging.getLogger(__name__)


def configure_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s %(name)s - %(message)s',
    )


def _parse_glue_db_names(raw: str | None, fallback: str | None) -> list[str]:
    if raw:
        names = [part.strip() for part in raw.split(',') if part.strip()]
        if names:
            return names
    if fallback:
        return [fallback]
    return []


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

    glue_db_names = _parse_glue_db_names(
        os.environ.get('GLUE_DB_NAMES'),
        runtime_settings.glue_db_name,
    )
    if not glue_db_names:
        logger.error('No Glue database configured (GLUE_DB_NAME or GLUE_DB_NAMES).')
        return 2

    try:
        service = build_athena_service(
            glue_db_names,
            runtime_settings.project_files_bucket,
            region=runtime_settings.region,
            athena_workgroup=runtime_settings.athena_workgroup,
        )
    except Exception as exc:
        logger.exception('Service initialization failed')
        logger.error('%s', exc)
        return 3

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
