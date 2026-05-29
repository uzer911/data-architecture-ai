#!/usr/bin/env python3
"""ECS Fargate entrypoint — runs the Text-to-SQL HTTP API."""
import logging
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(PROJECT_ROOT, 'src')
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

import uvicorn

from llm_sql.api import app
from llm_sql.config import get_settings


def configure_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s %(name)s - %(message)s',
    )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    uvicorn.run(
        app,
        host='0.0.0.0',
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == '__main__':
    main()
