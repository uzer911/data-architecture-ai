"""Abstract base class for all data source connectors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseConnector(ABC):
    """Interface that every data source connector must implement.

    A connector knows how to:
    1. Discover schema (tables + columns) from the data source
    2. Execute read-only SQL queries
    3. Report its SQL dialect so the LLM generates correct syntax
    """

    def __init__(self, name: str, settings: dict[str, Any]):
        self.name = name
        self.settings = settings

    @property
    @abstractmethod
    def dialect(self) -> str:
        """SQL dialect identifier (e.g. 'athena', 'postgresql', 'snowflake', 'spark').

        Used in the LLM prompt to generate correct SQL syntax.
        """

    @abstractmethod
    def get_schema(self) -> tuple[str, set[str]]:
        """Discover the schema from the data source.

        Returns:
            A tuple of (catalog_string, allowed_tables) where:
            - catalog_string: pipe-delimited rows like "database|table|column_name"
            - allowed_tables: set of table names the LLM is allowed to query
        """

    @abstractmethod
    def execute_sql(self, sql: str) -> list[dict[str, Any]]:
        """Execute a read-only SQL query and return results as list of dicts.

        Args:
            sql: The SQL query to execute (must be read-only).

        Returns:
            List of row dictionaries.

        Raises:
            RuntimeError: If the query fails or is not read-only.
        """

    def test_connection(self) -> bool:
        """Test if the connection is working.

        Returns:
            True if connection is healthy, False otherwise.
        """
        try:
            self.get_schema()
            return True
        except Exception:
            return False

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} dialect={self.dialect!r}>"
