"""Connector registry — discovers and instantiates connectors from YAML config files.

Config files live in config/connections/*.yaml. Each file defines one data source.
The registry auto-discovers all enabled connections at startup.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from llm_sql.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

# ── Connector type → class mapping ──────────────────────────────────────────
_CONNECTOR_CLASSES: dict[str, type[BaseConnector]] = {}


def _register_defaults():
    """Register built-in connector types."""
    from llm_sql.connectors.athena import AthenaConnector
    from llm_sql.connectors.redshift import RedshiftConnector
    from llm_sql.connectors.rds import RdsPostgresConnector, RdsMysqlConnector
    from llm_sql.connectors.snowflake import SnowflakeConnector
    from llm_sql.connectors.databricks import DatabricksConnector

    _CONNECTOR_CLASSES.update({
        'athena': AthenaConnector,
        'redshift': RedshiftConnector,
        'rds_postgres': RdsPostgresConnector,
        'rds_mysql': RdsMysqlConnector,
        'snowflake': SnowflakeConnector,
        'databricks': DatabricksConnector,
    })


def _get_config_dir() -> Path:
    """Resolve the config/connections directory."""
    # Check relative to project root
    project_root = Path(__file__).resolve().parents[3]  # src/llm_sql/connectors -> root
    config_dir = project_root / 'config' / 'connections'
    if config_dir.exists():
        return config_dir

    # Fallback: check env var
    env_path = os.environ.get('CONNECTIONS_CONFIG_DIR')
    if env_path:
        return Path(env_path)

    return config_dir  # Return default even if it doesn't exist yet


def load_connections() -> dict[str, dict[str, Any]]:
    """Load all connection configs from YAML files.

    Returns:
        Dict mapping connection name → full config dict.
    """
    config_dir = _get_config_dir()
    connections: dict[str, dict[str, Any]] = {}

    if not config_dir.exists():
        logger.info("No config/connections directory found at %s", config_dir)
        return connections

    for yaml_file in sorted(config_dir.glob('*.yaml')):
        try:
            with open(yaml_file) as f:
                config = yaml.safe_load(f)
            if not config or not isinstance(config, dict):
                continue
            if not config.get('enabled', True):
                logger.debug("Skipping disabled connection: %s", yaml_file.name)
                continue
            name = config.get('name', yaml_file.stem)
            connections[name] = config
            logger.debug("Loaded connection: %s (%s)", name, config.get('type'))
        except Exception as exc:
            logger.warning("Failed to load %s: %s", yaml_file, exc)

    return connections


def list_connections() -> list[dict[str, str]]:
    """List all available connections with name and type.

    Returns:
        List of dicts with 'name', 'type', and 'enabled' keys.
    """
    connections = load_connections()
    return [
        {
            'name': name,
            'type': config.get('type', 'unknown'),
            'enabled': config.get('enabled', True),
        }
        for name, config in connections.items()
    ]


def get_connector(name: str) -> BaseConnector:
    """Instantiate a connector by connection name.

    Args:
        name: The connection name (from the YAML config 'name' field).

    Returns:
        An instantiated connector ready to use.

    Raises:
        ValueError: If the connection name is not found or type is unsupported.
    """
    if not _CONNECTOR_CLASSES:
        _register_defaults()

    connections = load_connections()
    if name not in connections:
        raise ValueError(
            f"Connection '{name}' not found. "
            f"Available: {list(connections.keys())}"
        )

    config = connections[name]
    conn_type = config.get('type', '')

    if conn_type not in _CONNECTOR_CLASSES:
        raise ValueError(
            f"Unsupported connector type '{conn_type}'. "
            f"Available types: {list(_CONNECTOR_CLASSES.keys())}"
        )

    connector_class = _CONNECTOR_CLASSES[conn_type]
    settings = config.get('settings', {})

    return connector_class(name=name, settings=settings)


def get_connector_from_env() -> BaseConnector | None:
    """Build an Athena connector from environment variables (backward compatible).

    Returns the connector if env vars are set, None otherwise.
    """
    if not _CONNECTOR_CLASSES:
        _register_defaults()

    glue_db = os.environ.get('GLUE_DB_NAME', '')
    bucket = os.environ.get('PROJECT_FILES_BUCKET', '')

    if not glue_db or not bucket:
        return None

    from llm_sql.connectors.athena import AthenaConnector
    settings = {
        'glue_db_name': glue_db,
        'glue_db_names': os.environ.get('GLUE_DB_NAMES', ''),
        's3_bucket': bucket,
        'workgroup': os.environ.get('ATHENA_WORKGROUP', 'primary'),
        'region': os.environ.get('AWS_REGION', 'eu-north-1'),
    }
    return AthenaConnector(name='Athena (env)', settings=settings)
