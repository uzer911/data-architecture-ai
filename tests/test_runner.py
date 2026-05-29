import unittest
from unittest.mock import patch

from llm_sql.runner import (
    make_athena_connection_string,
    should_omit_s3_staging_dir,
    workgroup_uses_managed_results,
)


class AthenaConnectionTests(unittest.TestCase):
    @patch('llm_sql.runner.boto3.client')
    def test_managed_workgroup_uses_empty_s3_staging_param(self, mock_boto_client):
        mock_boto_client.return_value.get_work_group.return_value = {
            'WorkGroup': {
                'Configuration': {
                    'ManagedQueryResultsConfiguration': {'Enabled': True},
                },
            },
        }
        workgroup_uses_managed_results.cache_clear()
        conn = make_athena_connection_string(
            'project_library_db',
            'langchain-123-eu-north-1',
            region='eu-north-1',
            athena_workgroup='project-text-to-sql',
        )
        self.assertIn('s3_staging_dir=', conn)
        self.assertNotIn('athenaresults', conn)
        self.assertIn('work_group=project-text-to-sql', conn)

    def test_project_workgroup_omits_staging_without_boto3(self):
        with patch('llm_sql.runner.get_settings') as mock_settings:
            mock_settings.return_value.athena_use_managed_results = None
            self.assertTrue(
                should_omit_s3_staging_dir('project-text-to-sql', 'eu-north-1')
            )

    @patch('llm_sql.runner.boto3.client')
    def test_classic_workgroup_includes_s3_staging(self, mock_boto_client):
        mock_boto_client.return_value.get_work_group.return_value = {
            'WorkGroup': {
                'Configuration': {
                    'ResultConfiguration': {
                        'OutputLocation': 's3://bucket/athenaresults/',
                    },
                },
            },
        }
        workgroup_uses_managed_results.cache_clear()
        with patch('llm_sql.runner.get_settings') as mock_settings:
            mock_settings.return_value.athena_use_managed_results = None
            conn = make_athena_connection_string(
                'project_library_db',
                'langchain-123-eu-north-1',
                region='eu-north-1',
                athena_workgroup='primary',
            )
        self.assertIn('s3_staging_dir=', conn)
        self.assertIn('langchain-123-eu-north-1', conn)
        self.assertIn('work_group=primary', conn)
        self.assertIn('athenaresults', conn)


if __name__ == '__main__':
    unittest.main()
