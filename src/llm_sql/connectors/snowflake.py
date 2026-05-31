"""Snowflake connector — connects via snowflake-connector-python."""
from __future__ import annotations

import logging
from typing import Any

from llm_sql.connectors.base import BaseConnector

logger = logging.getLogger(__name__)


class SnowflakeConnector(BaseConnector):
    """Connector for Snowflake.

    Settings:
        account: Snowflake account identifier (e.g. xy12345.eu-west-1)
        warehouse: Compute warehouse name
        database: Database name
        schema: Schema name (default 'PUBLIC')
        role: Snowflake role
        user: Username (or use user_from_secret)
        password: Password (or use user_from_secret)
        user_from_secret: AWS Secrets Manager secret name for credentials
        token_from_secret: Secret name for OAuth/key-pair token
    """

    @property
    def dialect(self) -> str:
        return "snowflake"

    def _get_credentials(self) -> dict[str, str]:
        """Resolve credentials from settings or Secrets Manager."""
        creds = {}

        # Try direct settings first
        if self.settings.get('user') and self.settings.get('password'):
            return {
                'user': self.settings['user'],
                'password': self.settings['password'],
            }

        # Try Secrets Manager
        secret_name = self.settings.get('user_from_secret') or self.settings.get('token_from_secret')
        if secret_name:
            import boto3
            import json
            region = self.settings.get('region', 'eu-north-1')
            client = boto3.client('secretsmanager', region_name=region)
            resp = client.get_secret_value(SecretId=secret_name)
            secret = json.loads(resp['SecretString'])
            creds['user'] = secret.get('username', secret.get('user', ''))
            creds['password'] = secret.get('password', secret.get('token', ''))

        if not creds.get('user') or not creds.get('password'):
            raise ValueError(
                "Snowflake credentials not configured. "
                "Set 'user'/'password' or 'user_from_secret' in settings."
            )
        return creds

    def _get_connection(self):
        """Create a Snowflake connection."""
        try:
            import snowflake.connector
        except ImportError:
            raise ImportError(
                "snowflake-connector-python is required. "
                "Install with: pip install snowflake-connector-python"
            )

        creds = self._get_credentials()
        return snowflake.connector.connect(
            account=self.settings['account'],
            user=creds['user'],
            password=creds['password'],
            warehouse=self.settings.get('warehouse', 'COMPUTE_WH'),
            database=self.settings.get('database', ''),
            schema=self.settings.get('schema', 'PUBLIC'),
            role=self.settings.get('role', ''),
        )

    def get_schema(self) -> tuple[str, set[str]]:
        """Discover schema from Snowflake INFORMATION_SCHEMA."""
        database = self.settings.get('database', '')
        schema_name = self.settings.get('schema', 'PUBLIC')

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT TABLE_NAME, COLUMN_NAME
                FROM {database}.INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = '{schema_name}'
                ORDER BY TABLE_NAME, ORDINAL_POSITION
            """)
            rows = cursor.fetchall()
        finally:
            conn.close()

        catalog_lines = ['database|table|column_name']
        tables = set()
        for table_name, column_name in rows:
            catalog_lines.append(f"{database}|{table_name}|{column_name}")
            tables.add(table_name)

        return '\n'.join(catalog_lines), tables

    def execute_sql(self, sql: str) -> list[dict[str, Any]]:
        """Execute a read-only SQL query against Snowflake."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()
