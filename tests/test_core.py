import unittest
from unittest.mock import patch

from llm_sql.core import LLMSQLService


class FakeDB:
    def __init__(self):
        self.executed_sql: list[str] = []

    def run(self, sql: str):
        self.executed_sql.append(sql)
        return [{'avg_price': 100.0}]


class DeterministicService(LLMSQLService):
    def query_bedrock(self, prompt: str) -> str:
        low = prompt.lower()
        if 'respond only with a single json object' in low:
            return '{"channel":"db","sql":"SELECT AVG(price) AS avg_price FROM cars"}'
        if 'respond with a single json object' in low:
            return '{"sql":"SELECT AVG(price) AS avg_price FROM cars"}'
        if 'convert this result into a clear' in low:
            return 'The average price is 100.0.'
        return ''


class UnknownTableService(LLMSQLService):
    def query_bedrock(self, prompt: str) -> str:
        low = prompt.lower()
        if 'respond only with a single json object' in low:
            return '{"channel":"db","sql":"SELECT COUNT(*) FROM flights"}'
        if 'convert this result into a clear' in low:
            return 'No answer.'
        return ''


class MultiStatementService(LLMSQLService):
    def query_bedrock(self, prompt: str) -> str:
        low = prompt.lower()
        if 'respond only with a single json object' in low:
            return '{"channel":"db","sql":"SELECT * FROM cars; DROP TABLE cars"}'
        if 'convert this result into a clear' in low:
            return 'No answer.'
        return ''


class LLMSQLServiceTests(unittest.TestCase):
    @patch('llm_sql.core.boto3.client')
    def test_run_query_applies_default_limit(self, mock_boto_client):
        mock_boto_client.return_value = object()
        db = FakeDB()
        service = DeterministicService(
            db=db,
            glue_catalog='database|table|column_name\nlocal|cars|price',
            allowed_tables={'cars'},
            region='eu-north-1',
            max_result_rows=25,
        )

        answer = service.run_query('What is the average price?')

        self.assertEqual(answer, 'The average price is 100.0.')
        self.assertEqual(
            db.executed_sql[-1],
            'SELECT AVG(price) AS avg_price FROM cars LIMIT 25',
        )

    @patch('llm_sql.core.boto3.client')
    def test_run_query_rejects_unknown_table(self, mock_boto_client):
        mock_boto_client.return_value = object()
        db = FakeDB()
        service = UnknownTableService(
            db=db,
            glue_catalog='database|table|column_name\nlocal|cars|price',
            allowed_tables={'cars'},
            region='eu-north-1',
        )

        answer = service.run_query('How many flights are there?')

        self.assertIn('unknown table', answer.lower())
        self.assertEqual(db.executed_sql, [])

    @patch('llm_sql.core.boto3.client')
    def test_run_query_rejects_multi_statement_sql(self, mock_boto_client):
        mock_boto_client.return_value = object()
        db = FakeDB()
        service = MultiStatementService(
            db=db,
            glue_catalog='database|table|column_name\nlocal|cars|price',
            allowed_tables={'cars'},
            region='eu-north-1',
        )

        answer = service.run_query('Return cars then drop the table')

        self.assertIn('multi-statement', answer.lower())
        self.assertEqual(db.executed_sql, [])

    @patch('llm_sql.core.boto3.client')
    def test_run_query_enforces_question_length(self, mock_boto_client):
        mock_boto_client.return_value = object()
        db = FakeDB()
        service = DeterministicService(
            db=db,
            glue_catalog='database|table|column_name\nlocal|cars|price',
            allowed_tables={'cars'},
            region='eu-north-1',
            max_question_chars=64,
        )

        answer = service.run_query('x' * 65)

        self.assertIn('maximum length', answer.lower())
        self.assertEqual(db.executed_sql, [])


if __name__ == '__main__':
    unittest.main()
