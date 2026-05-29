import json
import logging
import re
import time
from typing import Iterable, Set, Tuple

import boto3
from botocore.exceptions import ClientError

from .config import resolve_bedrock_model
from .secrets import get_secret_dict

logger = logging.getLogger(__name__)

_SQL_RE = re.compile(r"(SELECT\b.*?)(?:;|$)", re.IGNORECASE | re.DOTALL)
_SQL_LIMIT_RE = re.compile(r"\blimit\s+\d+\b", re.IGNORECASE)
_DESTRUCTIVE_RE = re.compile(r"\b(drop|delete|update|alter|insert|truncate|create|replace)\b", re.IGNORECASE)
_READ_ONLY_START_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_MULTI_STATEMENT_RE = re.compile(r";\s*\S")
_SQL_COMMENT_RE = re.compile(r"(--|/\*|\*/)")


def parse_catalog(gdc: Iterable[str], region: str | None = None) -> Tuple[str, Set[str]]:
    """Return a pipe-delimited Glue catalog string and an allowlist of table names."""
    databases = list(gdc)
    if not databases:
        raise ValueError("At least one Glue database name must be provided.")
    rows = ["database|table|column_name"]
    glue_client = boto3.client('glue', region_name=region)
    allowed_tables: Set[str] = set()
    for db in databases:
        kwargs = {'DatabaseName': db}
        while True:
            response = glue_client.get_tables(**kwargs)
            for table in response.get('TableList', []):
                sd = table.get('StorageDescriptor', {})
                dbname = table.get('DatabaseName', db)
                tblname = table.get('Name', '')
                for col in sd.get('Columns', []):
                    rows.append(f"{dbname}|{tblname}|{col.get('Name', '')}")
                if tblname:
                    allowed_tables.add(tblname)
            next_token = response.get('NextToken')
            if not next_token:
                break
            kwargs['NextToken'] = next_token
    return '\n'.join(rows), allowed_tables


class LLMSQLService:
    """Service encapsulating model calls and safe SQL execution."""

    def __init__(
        self,
        db,
        glue_catalog: str,
        allowed_tables: Set[str],
        *,
        bedrock_model: str = 'amazon.nova-micro-v1:0',
        region: str | None = None,
        max_retries: int = 4,
        retry_base_delay: float = 1.0,
        secrets_manager_secret: str | None = None,
        max_result_rows: int = 200,
        max_question_chars: int = 1000,
    ):
        if max_retries < 1:
            raise ValueError("max_retries must be >= 1")
        if retry_base_delay <= 0:
            raise ValueError("retry_base_delay must be > 0")
        if max_result_rows < 1:
            raise ValueError("max_result_rows must be >= 1")
        if max_question_chars < 64:
            raise ValueError("max_question_chars must be >= 64")
        self.db = db
        self.glue_catalog = glue_catalog
        self.allowed_tables = allowed_tables
        self.bedrock_model = resolve_bedrock_model(bedrock_model, region or 'eu-north-1')
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.region = region
        self.max_result_rows = max_result_rows
        self.max_question_chars = max_question_chars

        bkwargs = {}
        if secrets_manager_secret:
            try:
                sec = get_secret_dict(secrets_manager_secret, region=region)
                aws_key = sec.get('aws_access_key_id') or sec.get('access_key')
                aws_secret = sec.get('aws_secret_access_key') or sec.get('secret_key')
                aws_token = sec.get('aws_session_token') or sec.get('session_token')
                if aws_key and aws_secret:
                    bkwargs['aws_access_key_id'] = aws_key
                    bkwargs['aws_secret_access_key'] = aws_secret
                if aws_token:
                    bkwargs['aws_session_token'] = aws_token
                if 'bedrock_model' in sec:
                    self.bedrock_model = resolve_bedrock_model(
                        sec['bedrock_model'],
                        region or 'eu-north-1',
                    )
            except ClientError:
                logger.exception('Failed to fetch secret %s', secrets_manager_secret)

        self.bedrock_client = boto3.client('bedrock-runtime', region_name=region, **bkwargs)

    def query_bedrock(self, prompt: str) -> str:
        body = {
            'inferenceConfig': {'max_new_tokens': 1000},
            'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
        }
        delay = self.retry_base_delay
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.bedrock_client.invoke_model(
                    modelId=self.bedrock_model,
                    contentType='application/json',
                    accept='application/json',
                    body=json.dumps(body),
                )
                response_body = json.loads(response['body'].read())
                return response_body['output']['message']['content'][0]['text']
            except ClientError as exc:
                code = exc.response['Error'].get('Code', '')
                if code in ('ThrottlingException', 'ServiceUnavailableException') and attempt < self.max_retries:
                    logger.warning(
                        'Bedrock throttled (attempt %d/%d). Retrying in %.1fs...',
                        attempt,
                        self.max_retries,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    logger.exception('Bedrock call failed')
                    raise
        raise RuntimeError('Bedrock call did not return a response.')

    def identify_channel(self, query: str) -> Tuple[str, str]:
        prompt = (
            'You are a SQL expert. Based on the schema below, determine if this question '
            'can be answered using SQL.\n\n'
            f'Schema:\n{self.glue_catalog}\n\n'
            f'Question: {query}\n\n'
            'Respond ONLY with a single JSON object with two fields:\n'
            '- "channel": one of "db" or "api"\n'
            '- "sql": a suggested SQL query string if channel is "db", otherwise an empty string\n\n'
            'Example: {"channel":"db","sql":"SELECT COUNT(*) FROM my_table"}'
        )
        generated_text = self.query_bedrock(prompt)
        clean = generated_text.strip().strip('`').strip()
        if clean.startswith('json'):
            clean = clean[4:].strip()
        try:
            parsed = json.loads(clean)
            channel = str(parsed.get('channel', 'db')).lower()
            suggested_sql = str(parsed.get('sql', ''))
        except json.JSONDecodeError:
            low = generated_text.lower()
            if any(kw in low for kw in ('select', 'from', 'where')):
                channel, suggested_sql = 'db', generated_text
            elif any(kw in low for kw in ('api', 'http')):
                channel, suggested_sql = 'api', ''
            else:
                channel, suggested_sql = 'db', ''
        return channel, suggested_sql

    def _extract_sql(self, text: str) -> str:
        clean = text.strip().strip('`').strip()
        if clean.startswith('json'):
            clean = clean[4:].strip()
        try:
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                return str(parsed.get('sql', '')).strip()
        except (json.JSONDecodeError, TypeError):
            pass
        if _READ_ONLY_START_RE.match(clean):
            return clean
        for line in text.splitlines():
            if line.strip().startswith('SQLQuery:'):
                return line.replace('SQLQuery:', '').strip()
        match = _SQL_RE.search(text)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _apply_result_limit(self, sql_query: str) -> str:
        normalized = sql_query.strip().rstrip(';').strip()
        if _SQL_LIMIT_RE.search(normalized):
            return normalized
        return f'{normalized} LIMIT {self.max_result_rows}'

    def _validate_sql_query(self, sql_query: str) -> str | None:
        if not sql_query:
            return 'Model did not return a SQL statement.'
        if _MULTI_STATEMENT_RE.search(sql_query):
            return 'Refusing to run multi-statement SQL query.'
        if _SQL_COMMENT_RE.search(sql_query):
            return 'Refusing to run SQL containing comments for safety.'
        if not _READ_ONLY_START_RE.match(sql_query):
            return 'Refusing to run non read-only SQL statement.'
        if _DESTRUCTIVE_RE.search(sql_query):
            return 'Refusing to run potentially destructive SQL statement.'
        if not self.allowed_tables:
            return 'No allowed table list is configured. Refusing to execute query.'
        if not any(re.search(rf'\b{re.escape(t)}\b', sql_query, re.IGNORECASE) for t in self.allowed_tables):
            return 'SQL references unknown table(s). Refusing to execute for safety.'
        return None

    def run_query(self, query: str) -> str:
        clean_query = str(query or '').strip()
        if not clean_query:
            return 'Question cannot be empty.'
        if len(clean_query) > self.max_question_chars:
            return (
                f'Question exceeds maximum length of '
                f'{self.max_question_chars} characters.'
            )

        channel, suggested_sql = self.identify_channel(clean_query)
        logger.info('run_query: channel=%s', channel)
        if channel != 'db':
            raise ValueError(f'Unsupported channel {channel!r}. Only "db" is implemented.')
        if not suggested_sql:
            sql_prompt = (
                'You are a SQL expert. Generate a SQL query for the following question.\n\n'
                f'Database schema:\n{self.glue_catalog}\n\n'
                f'Question: {clean_query}\n\n'
                'Respond with a single JSON object: {"sql":"SELECT ..."}\n'
                'Do not include any other text.'
            )
            suggested_sql = self.query_bedrock(sql_prompt)
        sql_query = self._extract_sql(suggested_sql).strip().rstrip(';').strip()
        logger.info('Extracted SQL: %s', sql_query)
        validation_error = self._validate_sql_query(sql_query)
        if validation_error:
            return validation_error
        sql_to_run = self._apply_result_limit(sql_query)
        logger.info('Executing SQL with safety controls: %s', sql_to_run)
        try:
            result = self.db.run(sql_to_run)
            logger.info('Query result: %s', result)
        except Exception as exc:
            logger.exception('SQL execution error')
            return f'Error executing SQL query: {exc}'
        answer_prompt = (
            f'I executed the following SQL query:\n{sql_to_run}\n\n'
            f'Result:\n{result}\n\n'
            f'Convert this result into a clear, grammatically correct sentence that answers: \"{clean_query}\"'
        )
        return self.query_bedrock(answer_prompt)
