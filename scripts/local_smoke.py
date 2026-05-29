#!/usr/bin/env python3
"""Local smoke test: create SQLite DB from `s3_cars_data.csv` and run a query.

This avoids any AWS/Bedrock calls by mocking the LLM responses.
"""
import os
import pandas as pd
import logging
from sqlalchemy import create_engine, text

from llm_sql.core import LLMSQLService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 's3_cars_data.csv')


def build_local_catalog(table_name: str, df: pd.DataFrame) -> tuple:
    rows = ['database|table|column_name']
    db = 'local'
    for col in df.columns:
        rows.append(f"{db}|{table_name}|{col}")
    allowed = set([table_name])
    return '\n'.join(rows), allowed


class SimpleDB:
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


class MockLLMService(LLMSQLService):
    def query_bedrock(self, prompt: str) -> str:
        # Simple heuristics for smoke test prompts
        low = prompt.lower()
        if 'respond only with a single json object' in low or 'example' in low:
            # Return a SQL that computes average price from cars
            return '{"channel":"db","sql":"SELECT AVG(price) as avg_price FROM cars"}'
        if 'convert this result into a clear' in low:
            # The prompt contains the result; extract numeric value
            # Expect the service to pass a result string like "[{'avg_price': 12345.67}]"
            try:
                # crude extraction
                start = prompt.find('Result:')
                snippet = prompt[start:]
                # find a number in snippet
                import re
                m = re.search(r'([0-9]+\.?[0-9]*)', snippet)
                if m:
                    val = float(m.group(1))
                    return f'The average price of a car is {val:.2f}.'
            except Exception:
                pass
            return 'Result parsing failed.'
        # Fallback
        return ''


def main():
    df = pd.read_csv(CSV_PATH)
    engine = create_engine('sqlite:///:memory:')
    df.to_sql('cars', engine, index=False, if_exists='replace')

    glue_catalog, allowed_tables = build_local_catalog('cars', df)

    db = SimpleDB(engine)
    service = MockLLMService(db, glue_catalog, allowed_tables)

    question = 'What is the average price of a car?'
    answer = service.run_query(question)
    print('Question:', question)
    print('Answer:', answer)


if __name__ == '__main__':
    main()
