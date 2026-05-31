"""RDS connectors — PostgreSQL and MySQL via SQLAlchemy."""
from __future__ import annotations

import logging
from typing import Any

from llm_sql.connectors.base import BaseConnector

logger = logging.getLogger(__name__)


def _resolve_credentials(settings: dict[str, Any]) -> tuple[str, str]:
    """Resolve username and password from settings or Secrets Manager."""
    user = settings.get('user', '')
    password = settings.get('password', '')

    secret_name = settings.get('user_from_secret')
    if secret_name and (not user or not password):
        import boto3
        import json
        region = settings.get('region', 'eu-north-1')
        client = boto3.client('secretsmanager', region_name=region)
        resp = client.get_secret_value(SecretId=secret_name)
        secret = json.loads(resp['SecretString'])
        user = secret.get('username', user)
        password = secret.get('password', password)

    if not user or not password:
        raise ValueError(
            "Database credentials not configured. "
            "Set 'user'/'password' in settings or 'user_from_secret' for Secrets Manager."
        )
    return user, password


class RdsPostgresConnector(BaseConnector):
    """Connector for Amazon RDS PostgreSQL.

    Settings:
        host: RDS endpoint
        port: Port (default 5432)
        database: Database name
        schema: Schema name (default 'public')
        user: Username (or use user_from_secret)
        password: Password (or use user_from_secret)
        user_from_secret: AWS Secrets Manager secret name
        region: AWS region
    """

    @property
    def dialect(self) -> str:
        return "postgresql"

    def _get_engine(self):
        """Create a SQLAlchemy engine for PostgreSQL."""
        try:
            from sqlalchemy import create_engine
        except ImportError:
            raise ImportError("sqlalchemy is required (already in requirements.txt)")

        try:
            import psycopg2  # noqa: F401
        except ImportError:
            raise ImportError(
                "psycopg2-binary is required for PostgreSQL. "
                "Install with: pip install psycopg2-binary"
            )

        user, password = _resolve_credentials(self.settings)
        host = self.settings['host']
        port = int(self.settings.get('port', 5432))
        database = self.settings.get('database', 'postgres')

        url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
        return create_engine(url, pool_pre_ping=True)

    def get_schema(self) -> tuple[str, set[str]]:
        """Discover schema from PostgreSQL information_schema."""
        from sqlalchemy import text

        schema_name = self.settings.get('schema', 'public')
        database = self.settings.get('database', 'postgres')
        engine = self._get_engine()

        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = :schema
                ORDER BY table_name, ordinal_position
            """), {'schema': schema_name})
            rows = result.fetchall()

        catalog_lines = ['database|table|column_name']
        tables = set()
        for table_name, column_name in rows:
            catalog_lines.append(f"{database}|{table_name}|{column_name}")
            tables.add(table_name)

        return '\n'.join(catalog_lines), tables

    def execute_sql(self, sql: str) -> list[dict[str, Any]]:
        """Execute a read-only SQL query against PostgreSQL."""
        from sqlalchemy import text

        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys()) if result.returns_rows else []
            if not columns:
                return []
            return [dict(zip(columns, row)) for row in result.fetchall()]


class RdsMysqlConnector(BaseConnector):
    """Connector for Amazon RDS MySQL.

    Settings:
        host: RDS endpoint
        port: Port (default 3306)
        database: Database name
        user: Username (or use user_from_secret)
        password: Password (or use user_from_secret)
        user_from_secret: AWS Secrets Manager secret name
        region: AWS region
    """

    @property
    def dialect(self) -> str:
        return "mysql"

    def _get_engine(self):
        """Create a SQLAlchemy engine for MySQL."""
        try:
            from sqlalchemy import create_engine
        except ImportError:
            raise ImportError("sqlalchemy is required (already in requirements.txt)")

        try:
            import pymysql  # noqa: F401
        except ImportError:
            raise ImportError(
                "pymysql is required for MySQL. "
                "Install with: pip install pymysql"
            )

        user, password = _resolve_credentials(self.settings)
        host = self.settings['host']
        port = int(self.settings.get('port', 3306))
        database = self.settings.get('database', 'mysql')

        url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        return create_engine(url, pool_pre_ping=True)

    def get_schema(self) -> tuple[str, set[str]]:
        """Discover schema from MySQL information_schema."""
        from sqlalchemy import text

        database = self.settings.get('database', 'mysql')
        engine = self._get_engine()

        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = :db
                ORDER BY table_name, ordinal_position
            """), {'db': database})
            rows = result.fetchall()

        catalog_lines = ['database|table|column_name']
        tables = set()
        for table_name, column_name in rows:
            catalog_lines.append(f"{database}|{table_name}|{column_name}")
            tables.add(table_name)

        return '\n'.join(catalog_lines), tables

    def execute_sql(self, sql: str) -> list[dict[str, Any]]:
        """Execute a read-only SQL query against MySQL."""
        from sqlalchemy import text

        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys()) if result.returns_rows else []
            if not columns:
                return []
            return [dict(zip(columns, row)) for row in result.fetchall()]
