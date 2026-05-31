import unittest
import urllib.parse
from unittest.mock import patch

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from llm_sql.runner import (
    make_athena_connection_string,
    should_omit_s3_staging_dir,
    workgroup_uses_managed_results,
)


class AthenaConnectionTests(unittest.TestCase):

    # ── Existing preservation test (kept) ─────────────────────────────────

    @patch('llm_sql.runner.boto3.client')
    def test_managed_workgroup_uses_empty_s3_staging_param(self, mock_boto_client):
        """Preservation: workgroup with Enabled=true produces empty s3_staging_dir
        (reqs 3.1, 3.2)."""
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

    # ── Bug condition exploration tests (task 1 — inverted post-fix) ──────

    def test_env_var_true_causes_empty_staging_dir(self):
        """Post-fix: env var True still short-circuits to True (req 3.1).
        When the operator explicitly sets ATHENA_USE_MANAGED_RESULTS=true,
        the function honours that override."""
        with patch('llm_sql.runner.get_settings') as mock_settings:
            mock_settings.return_value.athena_use_managed_results = True
            result = should_omit_s3_staging_dir('project-text-to-sql', 'eu-north-1')
        self.assertTrue(result)

    @patch('llm_sql.runner.boto3.client')
    def test_hardcoded_set_causes_empty_staging_dir(self, mock_boto_client):
        """Post-fix: with no env var, the API is consulted. When API returns
        Enabled=false, result is False (req 2.1) — bug path 2 is gone."""
        mock_boto_client.return_value.get_work_group.return_value = {
            'WorkGroup': {
                'Configuration': {
                    'ManagedQueryResultsConfiguration': {'Enabled': False},
                },
            },
        }
        workgroup_uses_managed_results.cache_clear()
        with patch('llm_sql.runner.get_settings') as mock_settings:
            mock_settings.return_value.athena_use_managed_results = None
            result = should_omit_s3_staging_dir('project-text-to-sql', 'eu-north-1')
        self.assertFalse(result)

    # ── New correctness tests (tasks 4.2–4.5) ─────────────────────────────

    @patch('llm_sql.runner.boto3.client')
    def test_non_managed_workgroup_includes_s3_staging(self, mock_boto_client):
        """Fix check: workgroup with ManagedQueryResultsConfiguration.Enabled=false
        must produce a connection string with a real S3 staging dir (req 2.1, 2.2)."""
        mock_boto_client.return_value.get_work_group.return_value = {
            'WorkGroup': {
                'Configuration': {
                    'ManagedQueryResultsConfiguration': {'Enabled': False},
                },
            },
        }
        workgroup_uses_managed_results.cache_clear()
        with patch('llm_sql.runner.get_settings') as mock_settings:
            mock_settings.return_value.athena_use_managed_results = None
            mock_settings.return_value.region = 'eu-north-1'
            conn = make_athena_connection_string(
                'project_library_db',
                'langchain-123-eu-north-1',
                region='eu-north-1',
                athena_workgroup='project-text-to-sql',
            )
        self.assertIn('s3://langchain-123-eu-north-1/athenaresults/', urllib.parse.unquote(conn))
        self.assertIn('work_group=project-text-to-sql', conn)

    def test_explicit_false_override_returns_false(self):
        """Preservation: ATHENA_USE_MANAGED_RESULTS=false always returns False
        regardless of workgroup name or API response (req 3.5)."""
        with patch('llm_sql.runner.get_settings') as mock_settings:
            mock_settings.return_value.athena_use_managed_results = False
            result = should_omit_s3_staging_dir('project-text-to-sql', 'eu-north-1')
        self.assertFalse(result)

    @patch('llm_sql.runner.boto3.client')
    def test_api_failure_defaults_to_false(self, mock_boto_client):
        """Preservation: when the Athena API call fails and no env var is set,
        should_omit_s3_staging_dir() returns False as a safe default (req 3.3)."""
        from botocore.exceptions import ClientError
        mock_boto_client.return_value.get_work_group.side_effect = ClientError(
            {'Error': {'Code': 'AccessDeniedException', 'Message': 'Access denied'}},
            'GetWorkGroup',
        )
        workgroup_uses_managed_results.cache_clear()
        with patch('llm_sql.runner.get_settings') as mock_settings:
            mock_settings.return_value.athena_use_managed_results = None
            result = should_omit_s3_staging_dir('project-text-to-sql', 'eu-north-1')
        self.assertFalse(result)

    @patch('llm_sql.runner.boto3.client')
    def test_classic_workgroup_includes_s3_staging(self, mock_boto_client):
        """Preservation: non-managed workgroup produces a full S3 staging dir (req 3.4)."""
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
            mock_settings.return_value.region = 'eu-north-1'
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


class AthenaConnectionPropertyTests(unittest.TestCase):
    """Property-based tests using hypothesis to verify no hardcoded-name assumptions remain."""

    @given(st.text(min_size=1))
    @h_settings(max_examples=50)
    def test_any_non_managed_workgroup_returns_false(self, workgroup_name):
        """Property 1: for ANY workgroup name, when the API returns Enabled=false
        and no env var is set, should_omit_s3_staging_dir() returns False.
        Verifies no remaining hardcoded-name assumptions (req 2.1)."""
        with patch('llm_sql.runner.boto3.client') as mock_boto_client, \
             patch('llm_sql.runner.get_settings') as mock_settings:
            mock_boto_client.return_value.get_work_group.return_value = {
                'WorkGroup': {
                    'Configuration': {
                        'ManagedQueryResultsConfiguration': {'Enabled': False},
                    },
                },
            }
            mock_settings.return_value.athena_use_managed_results = None
            workgroup_uses_managed_results.cache_clear()
            result = should_omit_s3_staging_dir(workgroup_name, 'eu-north-1')
        self.assertFalse(result)

    @given(st.text(min_size=1))
    @h_settings(max_examples=50)
    def test_any_managed_workgroup_returns_true(self, workgroup_name):
        """Property 2: for ANY workgroup name, when the API returns Enabled=true
        and no env var is set, should_omit_s3_staging_dir() returns True.
        Verifies preservation of managed-results behaviour (reqs 3.1, 3.2)."""
        with patch('llm_sql.runner.boto3.client') as mock_boto_client, \
             patch('llm_sql.runner.get_settings') as mock_settings:
            mock_boto_client.return_value.get_work_group.return_value = {
                'WorkGroup': {
                    'Configuration': {
                        'ManagedQueryResultsConfiguration': {'Enabled': True},
                    },
                },
            }
            mock_settings.return_value.athena_use_managed_results = None
            workgroup_uses_managed_results.cache_clear()
            result = should_omit_s3_staging_dir(workgroup_name, 'eu-north-1')
        self.assertTrue(result)

    @given(
        st.text(min_size=1),
        st.from_regex(r'[a-z0-9][a-z0-9-]{0,20}[a-z0-9]', fullmatch=True),
    )
    @h_settings(max_examples=50)
    def test_any_non_managed_workgroup_connection_string_has_s3_staging(
        self, workgroup_name, bucket_name
    ):
        """Property 3: for ANY workgroup name and bucket name, when the API returns
        Enabled=false, make_athena_connection_string() includes s3:// in the
        s3_staging_dir parameter (req 3.4)."""
        with patch('llm_sql.runner.boto3.client') as mock_boto_client, \
             patch('llm_sql.runner.get_settings') as mock_settings:
            mock_boto_client.return_value.get_work_group.return_value = {
                'WorkGroup': {
                    'Configuration': {
                        'ManagedQueryResultsConfiguration': {'Enabled': False},
                    },
                },
            }
            mock_settings.return_value.athena_use_managed_results = None
            mock_settings.return_value.region = 'eu-north-1'
            workgroup_uses_managed_results.cache_clear()
            conn = make_athena_connection_string(
                'project_library_db',
                bucket_name,
                region='eu-north-1',
                athena_workgroup=workgroup_name,
            )
        self.assertIn('s3://', urllib.parse.unquote(conn))
        self.assertIn('athenaresults', conn)
