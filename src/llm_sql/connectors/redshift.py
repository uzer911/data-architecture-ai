"""Redshift connector — connects to Amazon Redshift via redshift_connector."""
from __future__ import annotations

import logging
from typing import Any

from llm_sql.connectors.base import BaseConnector

logger = logging.getLogger(__name__)


class RedshiftConnector(BaseConnector):
    """Connector for Amazon Redshift.

    Settings:
        host: Redshift cluster endpoint
        port: Port (default 5439)
        database: Database name
        schema: Schema name (default 'public')
        user: Username (or use user_from_secret)
        password: Password (or use user_from_secret)
        user_from_secret: AWS Secrets Manager secret name
        region: AWS region
    """

    @property
    def dialect(self) -> str:
        return "redshift"

    def _get_credentials(self) -> tuple[str, str]:
        """Resolve username and password from settings or Secrets Manager."""
        user = self.settings.get('user', '')
        password = self.settings.get('password', '')

        secret_name = self.settings.get('user_from_secret')
        if secret_name and (not user or not password):
            import boto3
            import json
            region = self.settings.get('region', 'eu-north-1')
            client = boto3.client('secretsmanager', region_name=region)
            resp = client.get_secret_value(SecretId=secret_name)
            secret = json.loads(resp['SecretString'])
            user = secret.get('username', user)
            password = secret.get('password', password)

        if not user or not password:
            raise ValueError(
                "Redshift credentials not configured. "
                "Set 'user'/'password' in settings or 'user_from_secret' for Secrets Manager."
            )
        return user, password

    def _get_connection(self):
        """Create a Redshift connection."""
        try:
            import redshift_connector
        except ImportError:
            raise ImportError(
                "redshift-connector is required. Install with: "
                "pip install redshift-connector"
            )

        user, password = self._get_credentials()
        return redshift_connector.connect(
            host=self.settings['host'],
            port=int(self.settings.get('port', 5439)),
            database=self.settings.get('database', 'dev'),
            user=user,
            password=password,
        )

    def get_schema(self) -> tuple[str, set[str]]:
        """Discover schema from Redshift information_schema."""
        schema_name = self.settings.get('schema', 'public')
        database = self.settings.get('database', 'dev')

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = '{schema_name}'
                ORDER BY table_name, ordinal_position
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
        """Execute a read-only SQL query against Redshift."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()
