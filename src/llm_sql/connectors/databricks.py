"""Databricks SQL connector — connects via databricks-sql-connector."""
from __future__ import annotations

import logging
from typing import Any

from llm_sql.connectors.base import BaseConnector

logger = logging.getLogger(__name__)


class DatabricksConnector(BaseConnector):
    """Connector for Databricks SQL Warehouse.

    Settings:
        host: Databricks workspace URL (e.g. adb-123456.azuredatabricks.net)
        http_path: SQL warehouse HTTP path
        catalog: Unity Catalog name (default 'main')
        schema: Schema name (default 'default')
        token: Personal access token (or use token_from_secret)
        token_from_secret: AWS Secrets Manager secret name for PAT token
        region: AWS region (for Secrets Manager lookup)
    """

    @property
    def dialect(self) -> str:
        return "databricks"

    def _get_token(self) -> str:
        """Resolve the Databricks PAT token."""
        token = self.settings.get('token', '')
        if token:
            return token

        secret_name = self.settings.get('token_from_secret')
        if secret_name:
            import boto3
            import json
            region = self.settings.get('region', 'eu-north-1')
            client = boto3.client('secretsmanager', region_name=region)
            resp = client.get_secret_value(SecretId=secret_name)
            secret = json.loads(resp['SecretString'])
            # Support both {"token": "..."} and plain string secrets
            if isinstance(secret, dict):
                token = secret.get('token', secret.get('access_token', ''))
            else:
                token = str(secret)

        if not token:
            raise ValueError(
                "Databricks token not configured. "
                "Set 'token' in settings or 'token_from_secret' for Secrets Manager."
            )
        return token

    def _get_connection(self):
        """Create a Databricks SQL connection."""
        try:
            from databricks import sql as databricks_sql
        except ImportError:
            raise ImportError(
                "databricks-sql-connector is required. "
                "Install with: pip install databricks-sql-connector"
            )

        token = self._get_token()
        return databricks_sql.connect(
            server_hostname=self.settings['host'],
            http_path=self.settings['http_path'],
            access_token=token,
            catalog=self.settings.get('catalog', 'main'),
            schema=self.settings.get('schema', 'default'),
        )

    def get_schema(self) -> tuple[str, set[str]]:
        """Discover schema from Databricks Unity Catalog."""
        catalog = self.settings.get('catalog', 'main')
        schema_name = self.settings.get('schema', 'default')

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT table_name, column_name
                FROM {catalog}.information_schema.columns
                WHERE table_schema = '{schema_name}'
                ORDER BY table_name, ordinal_position
            """)
            rows = cursor.fetchall()
        finally:
            conn.close()

        catalog_lines = ['database|table|column_name']
        tables = set()
        for table_name, column_name in rows:
            catalog_lines.append(f"{catalog}|{table_name}|{column_name}")
            tables.add(table_name)

        return '\n'.join(catalog_lines), tables

    def execute_sql(self, sql: str) -> list[dict[str, Any]]:
        """Execute a read-only SQL query against Databricks."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()
