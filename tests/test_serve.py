import unittest
from unittest.mock import patch

from llm_sql import api
from llm_sql.api import QueryRequest, health, query


class ServeApiTests(unittest.TestCase):
    def setUp(self):
        api.reset_service_cache()

    def test_health_ok_when_config_present(self):
        with patch('llm_sql.api.require_runtime_settings') as mock_require:
            mock_require.return_value = object()
            response = health()
        self.assertEqual(response.status, 'ok')

    def test_health_degraded_when_config_missing(self):
        with patch('llm_sql.api.require_runtime_settings') as mock_require:
            from llm_sql.config import SettingsError
            mock_require.side_effect = SettingsError('Missing GLUE_DB_NAME')
            response = health()
        self.assertEqual(response.status, 'degraded')

    def test_query_returns_answer(self):
        class FakeService:
            def run_query(self, question: str) -> str:
                return f'Answer to: {question}'

        with patch('llm_sql.api.get_service', return_value=FakeService()):
            response = query(QueryRequest(question='How many books?'))
        self.assertEqual(response.answer, 'Answer to: How many books?')


if __name__ == '__main__':
    unittest.main()
