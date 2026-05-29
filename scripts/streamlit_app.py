#!/usr/bin/env python3
"""Streamlit chat UI for Text-to-SQL (Bedrock + Athena).

Local mode (default): uses AWS credentials and env vars directly.
Remote mode: set API_URL to your ECS load balancer (e.g. http://xxx.elb.amazonaws.com).

Example:
  export GLUE_DB_NAME=project_library_db
  export PROJECT_FILES_BUCKET=langchain-<account-id>-eu-north-1
  export ATHENA_WORKGROUP=project-text-to-sql
  streamlit run scripts/streamlit_app.py

Remote:
  export API_URL=http://<alb-dns>
  export API_KEY=your-key   # optional
  streamlit run scripts/streamlit_app.py
"""
from __future__ import annotations

import os
import sys
from typing import Optional

import requests
import streamlit as st

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(PROJECT_ROOT, 'src')
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from llm_sql.config import SettingsError, get_settings, require_runtime_settings
from llm_sql.runner import build_athena_service


def _parse_glue_db_names(raw: str | None, fallback: str | None) -> list[str]:
    if raw:
        names = [part.strip() for part in raw.split(',') if part.strip()]
        if names:
            return names
    if fallback:
        return [fallback]
    return []


@st.cache_resource(show_spinner='Connecting to Athena and Bedrock…')
def _get_local_service():
    settings = get_settings()
    runtime = require_runtime_settings(settings)
    glue_db_names = _parse_glue_db_names(
        os.environ.get('GLUE_DB_NAMES'),
        runtime.glue_db_name,
    )
    if not glue_db_names:
        raise SettingsError('Set GLUE_DB_NAME or GLUE_DB_NAMES.')
    return build_athena_service(
        glue_db_names,
        runtime.project_files_bucket,
        region=runtime.region,
        athena_workgroup=runtime.athena_workgroup,
    )


def _api_base_url() -> Optional[str]:
    url = (os.environ.get('API_URL') or st.session_state.get('api_url') or '').strip()
    if not url:
        return None
    return url.rstrip('/')


def _ask_remote(question: str) -> str:
    base = _api_base_url()
    if not base:
        raise RuntimeError('API_URL is not set.')
    headers = {'Content-Type': 'application/json'}
    api_key = os.environ.get('API_KEY') or st.session_state.get('api_key')
    if api_key:
        headers['X-Api-Key'] = api_key
    response = requests.post(
        f'{base}/query',
        json={'question': question},
        headers=headers,
        timeout=300,
    )
    if response.status_code != 200:
        detail = response.text
        try:
            detail = response.json().get('detail', detail)
        except Exception:
            pass
        raise RuntimeError(f'API error ({response.status_code}): {detail}')
    return response.json()['answer']


def _ask_local(question: str) -> str:
    service = _get_local_service()
    return service.run_query(question)


def _ask(question: str) -> str:
    if _api_base_url():
        return _ask_remote(question)
    return _ask_local(question)


def main() -> None:
    st.set_page_config(
        page_title='Text-to-SQL',
        page_icon='💬',
        layout='centered',
    )
    st.title('Text-to-SQL')
    st.caption('Ask questions in plain English — Bedrock generates SQL, Athena runs it.')

    settings = get_settings()
    api_url = _api_base_url()

    with st.sidebar:
        st.subheader('Connection')
        if api_url:
            st.success('Remote API')
            st.code(api_url, language=None)
            if os.environ.get('API_KEY'):
                st.text('API key: from API_KEY env')
            else:
                st.session_state.setdefault('api_key', '')
                st.session_state['api_key'] = st.text_input(
                    'API key (optional)',
                    type='password',
                    key='api_key_input',
                )
        else:
            st.info('Local (AWS credentials)')
            try:
                runtime = require_runtime_settings(settings)
                st.text(f'Glue DB: {runtime.glue_db_name}')
                st.text(f'S3 bucket: {runtime.project_files_bucket}')
                st.text(f'Region: {runtime.region}')
                st.text(f'Athena WG: {runtime.athena_workgroup}')
            except SettingsError as exc:
                st.error(str(exc))
                st.markdown(
                    'Set env vars or `.env`:\n'
                    '- `GLUE_DB_NAME`\n'
                    '- `PROJECT_FILES_BUCKET`\n'
                    '- `ATHENA_WORKGROUP` (optional)'
                )

            st.divider()
            st.text('Or use remote API:')
            remote_url = st.text_input(
                'API URL',
                value=st.session_state.get('api_url', ''),
                placeholder='http://your-alb-dns.amazonaws.com',
                key='api_url_input',
            )
            if remote_url:
                st.session_state['api_url'] = remote_url.strip().rstrip('/')

        st.divider()
        if st.button('Clear chat'):
            st.session_state['messages'] = []
            st.rerun()

    if 'messages' not in st.session_state:
        st.session_state['messages'] = []

    for role, content in st.session_state['messages']:
        with st.chat_message(role):
            st.markdown(content)

    examples = [
        'How many books are in the library?',
        'What is the average price of cars?',
        'List the top 5 most expensive cars.',
    ]
    st.markdown('**Examples:** ' + ' · '.join(f'`{e}`' for e in examples))

    question = st.chat_input('Ask a question about your data…')
    if not question:
        return

    st.session_state['messages'].append(('user', question))
    with st.chat_message('user'):
        st.markdown(question)

    with st.chat_message('assistant'):
        with st.spinner('Generating SQL and querying Athena…'):
            try:
                answer = _ask(question)
                st.markdown(answer)
                st.session_state['messages'].append(('assistant', answer))
            except Exception as exc:
                err = f'**Error:** {exc}'
                st.markdown(err)
                st.session_state['messages'].append(('assistant', err))


if __name__ == '__main__':
    main()
