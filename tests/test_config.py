import unittest
from unittest.mock import patch

from llm_sql.config import Settings, SettingsError, get_settings, require_runtime_settings


class SettingsTests(unittest.TestCase):
    def tearDown(self):
        get_settings.cache_clear()

    @patch.dict(
        'os.environ',
        {
            'GLUE_DB_NAME': 'project_library_db',
            'PROJECT_FILES_BUCKET': 'example-bucket',
            'LOG_LEVEL': 'debug',
            'MAX_RESULT_ROWS': '250',
            'MAX_QUESTION_CHARS': '800',
        },
        clear=False,
    )
    def test_get_settings_reads_environment(self):
        get_settings.cache_clear()
        runtime_settings = get_settings()

        self.assertEqual(runtime_settings.glue_db_name, 'project_library_db')
        self.assertEqual(runtime_settings.project_files_bucket, 'example-bucket')
        self.assertEqual(runtime_settings.log_level, 'DEBUG')
        self.assertEqual(runtime_settings.max_result_rows, 250)
        self.assertEqual(runtime_settings.max_question_chars, 800)

    def test_require_runtime_settings_raises_when_missing(self):
        runtime_settings = Settings(glue_db_name=None, project_files_bucket=None)

        with self.assertRaises(SettingsError):
            require_runtime_settings(runtime_settings)


if __name__ == '__main__':
    unittest.main()
