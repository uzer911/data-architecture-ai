#!/usr/bin/env python3
"""AI Data Analyst Agent — conversational UI for natural-language data queries.

Local mode (default): uses AWS credentials and env vars directly.
Remote mode: set API_URL to your ECS load balancer.

Example:
  export GLUE_DB_NAME=project_library_db
  export PROJECT_FILES_BUCKET=langchain-471613014056-eu-north-1
  export ATHENA_WORKGROUP=project-text-to-sql
  streamlit run scripts/streamlit_app.py
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from typing import Optional

import hashlib
import hmac

import requests
import streamlit as st

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(PROJECT_ROOT, 'src')
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from llm_sql.config import SettingsError, get_settings, require_runtime_settings
from llm_sql.runner import build_athena_service
from llm_sql.connectors.registry import (
    get_connector,
    get_connector_from_env,
    list_connections,
    load_connections,
)

# ── Logo path ────────────────────────────────────────────────────────────────
LOGO_PATH = Path(PROJECT_ROOT) / "assets" / "cloudage-logo.svg"


def _get_logo_b64() -> str:
    """Read the SVG logo and return a base64 data URI."""
    if LOGO_PATH.exists():
        svg_content = LOGO_PATH.read_text()
        b64 = base64.b64encode(svg_content.encode()).decode()
        return f"data:image/svg+xml;base64,{b64}"
    return ""


def _inject_custom_css():
    """Inject custom CSS — white background, CloudAge blue branding, moving clouds."""
    st.markdown("""
    <style>
    /* ── Global Reset ───────────────────────────────────────────────────── */
    .stApp {
        background-color: #FFFFFF;
    }
    [data-testid="stHeader"] {
        background-color: #FFFFFF;
        border-bottom: 1px solid #E8EDF2;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #F0F7FF 0%, #FFFFFF 100%);
        border-right: 1px solid #E8EDF2;
    }

    /* ── Moving Clouds Animation ────────────────────────────────────────── */
    @keyframes drift {
        from { transform: translateX(-100%); }
        to   { transform: translateX(100vw); }
    }
    .clouds-container {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 220px;
        overflow: hidden;
        pointer-events: none;
        z-index: 0;
        opacity: 0.45;
    }
    .cloud {
        position: absolute;
        background: #E3F2FD;
        border-radius: 50px;
        animation: drift linear infinite;
    }
    .cloud::before, .cloud::after {
        content: '';
        position: absolute;
        background: #E3F2FD;
        border-radius: 50%;
    }
    .cloud-1 {
        width: 120px; height: 40px;
        top: 30px;
        animation-duration: 35s;
        animation-delay: 0s;
    }
    .cloud-1::before {
        width: 50px; height: 50px;
        top: -20px; left: 20px;
    }
    .cloud-1::after {
        width: 60px; height: 45px;
        top: -18px; left: 50px;
    }
    .cloud-2 {
        width: 160px; height: 50px;
        top: 80px;
        animation-duration: 45s;
        animation-delay: -10s;
    }
    .cloud-2::before {
        width: 65px; height: 60px;
        top: -28px; left: 30px;
    }
    .cloud-2::after {
        width: 75px; height: 55px;
        top: -22px; left: 70px;
    }
    .cloud-3 {
        width: 100px; height: 35px;
        top: 50px;
        animation-duration: 55s;
        animation-delay: -20s;
    }
    .cloud-3::before {
        width: 45px; height: 42px;
        top: -18px; left: 15px;
    }
    .cloud-3::after {
        width: 50px; height: 38px;
        top: -15px; left: 45px;
    }
    .cloud-4 {
        width: 140px; height: 45px;
        top: 130px;
        animation-duration: 40s;
        animation-delay: -5s;
    }
    .cloud-4::before {
        width: 55px; height: 52px;
        top: -24px; left: 25px;
    }
    .cloud-4::after {
        width: 65px; height: 48px;
        top: -20px; left: 60px;
    }
    .cloud-5 {
        width: 90px; height: 30px;
        top: 160px;
        animation-duration: 50s;
        animation-delay: -15s;
    }
    .cloud-5::before {
        width: 40px; height: 38px;
        top: -16px; left: 12px;
    }
    .cloud-5::after {
        width: 45px; height: 35px;
        top: -14px; left: 38px;
    }

    /* Ensure main content sits above clouds */
    [data-testid="stMainBlockContainer"] {
        position: relative;
        z-index: 1;
    }

    /* ── Hero Section ───────────────────────────────────────────────────── */
    .hero-section {
        text-align: center;
        padding: 2.5rem 1rem 1.5rem;
    }
    .hero-logo-img {
        width: 220px;
        margin: 0 auto 1.5rem;
        display: block;
    }
    .hero-title {
        font-size: 2rem;
        font-weight: 700;
        color: #0D47A1;
        margin-bottom: 0.5rem;
        letter-spacing: -0.01em;
    }
    .hero-subtitle {
        font-size: 1.15rem;
        color: #1976D2;
        font-weight: 500;
        margin-bottom: 0.5rem;
    }
    .hero-desc {
        font-size: 0.95rem;
        color: #64748B;
        max-width: 520px;
        margin: 0 auto;
        line-height: 1.5;
    }

    /* ── Feature Pills (Spotter-style) ──────────────────────────────────── */
    .features-row {
        display: flex;
        justify-content: center;
        gap: 1.25rem;
        flex-wrap: wrap;
        padding: 2rem 0 1.5rem;
    }
    .feature-pill {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        padding: 0.75rem 1.25rem;
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 50px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        transition: all 0.2s ease;
    }
    .feature-pill:hover {
        border-color: #1976D2;
        box-shadow: 0 4px 16px rgba(25,118,210,0.1);
        transform: translateY(-1px);
    }
    .feature-pill-icon {
        font-size: 1.25rem;
    }
    .feature-pill-text {
        font-size: 0.85rem;
        font-weight: 500;
        color: #334155;
    }
    .feature-pill-desc {
        font-size: 0.75rem;
        color: #64748B;
    }

    /* ── Suggestion Cards ───────────────────────────────────────────────── */
    .suggestions-header {
        text-align: center;
        font-size: 0.85rem;
        color: #94A3B8;
        margin: 1.5rem 0 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 500;
    }

    /* Style the suggestion buttons */
    div[data-testid="stHorizontalBlock"] button[kind="secondary"] {
        border-radius: 12px;
        border: 1px solid #E2E8F0;
        background: #F8FAFC;
        color: #334155;
        font-size: 0.82rem;
        padding: 0.6rem 1rem;
        transition: all 0.2s ease;
    }
    div[data-testid="stHorizontalBlock"] button[kind="secondary"]:hover {
        border-color: #1976D2;
        background: #EBF5FF;
        color: #1565C0;
    }

    /* ── Chat Messages ──────────────────────────────────────────────────── */
    [data-testid="stChatMessage"] {
        border-radius: 16px;
        padding: 1rem 1.25rem;
        margin-bottom: 0.75rem;
        border: 1px solid #F1F5F9;
    }

    /* ── Chat Input ─────────────────────────────────────────────────────── */
    [data-testid="stChatInputContainer"] {
        border-top: 1px solid #E8EDF2;
        padding-top: 0.5rem;
    }

    /* ── Sidebar Elements ───────────────────────────────────────────────── */
    .sidebar-logo {
        text-align: center;
        padding: 1.25rem 0 1rem;
        border-bottom: 1px solid #E2E8F0;
        margin-bottom: 1.25rem;
    }
    .sidebar-logo img {
        width: 160px;
    }
    .sidebar-section-title {
        font-size: 0.7rem;
        font-weight: 600;
        color: #94A3B8;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin: 1rem 0 0.5rem;
    }
    .connection-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.3rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 500;
        background: #ECFDF5;
        color: #059669;
        margin-bottom: 0.75rem;
    }
    .connection-badge::before {
        content: '';
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #059669;
    }
    .info-table {
        font-size: 0.8rem;
        color: #475569;
        line-height: 1.8;
    }
    .info-table strong {
        color: #1E293B;
    }

    /* ── Compact Chat Header ────────────────────────────────────────────── */
    .chat-header {
        text-align: center;
        padding: 0.5rem 0 1rem;
        border-bottom: 1px solid #F1F5F9;
        margin-bottom: 1rem;
    }
    .chat-header img {
        width: 140px;
    }

    /* ── Hide Streamlit defaults ────────────────────────────────────────── */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stDecoration"] {display: none;}
    [data-testid="stToolbar"] {display: none;}
    .stDeployButton {display: none;}
    </style>
    """, unsafe_allow_html=True)

    # Inject moving cloud elements
    st.markdown("""
    <div class="clouds-container">
        <div class="cloud cloud-1"></div>
        <div class="cloud cloud-2"></div>
        <div class="cloud cloud-3"></div>
        <div class="cloud cloud-4"></div>
        <div class="cloud cloud-5"></div>
    </div>
    """, unsafe_allow_html=True)


# ── Service Layer ────────────────────────────────────────────────────────────

def _parse_glue_db_names(raw: str | None, fallback: str | None) -> list[str]:
    if raw:
        names = [part.strip() for part in raw.split(',') if part.strip()]
        if names:
            return names
    if fallback:
        return [fallback]
    return []


@st.cache_resource(show_spinner=False)
def _get_local_service(_db, _bucket, _region, _workgroup):
    """Build the Athena service. Args are used as cache keys so config changes reconnect."""
    from llm_sql.config import get_settings as _gs
    _gs.cache_clear()  # clear lru_cache so new env vars are picked up
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
    # Pass current config as cache keys so service rebuilds on config change
    db = os.environ.get('GLUE_DB_NAME', '')
    bucket = os.environ.get('PROJECT_FILES_BUCKET', '')
    region = os.environ.get('AWS_REGION', 'eu-north-1')
    workgroup = os.environ.get('ATHENA_WORKGROUP', 'primary')
    service = _get_local_service(db, bucket, region, workgroup)
    return service.run_query(question)


def _ask(question: str) -> str:
    if _api_base_url():
        return _ask_remote(question)

    # Check which data source is selected in the sidebar
    CONNECTOR_OPTIONS = {
        '☁️ Athena (AWS)': 'athena',
        '🔴 Redshift (AWS)': 'redshift',
        '🐘 RDS PostgreSQL': 'rds_postgres',
        '🐬 RDS MySQL': 'rds_mysql',
        '❄️ Snowflake': 'snowflake',
        '🧱 Databricks': 'databricks',
    }

    active_source = st.session_state.get('active_source', '☁️ Athena (AWS)')
    selected_type = CONNECTOR_OPTIONS.get(active_source, '')

    # If Athena is selected, use the existing local service (backward compatible)
    if selected_type == 'athena':
        return _ask_local(question)

    # Try connector framework for other sources (config/connections/*.yaml)
    connections = load_connections()

    # Find a matching configured connection
    matching_conn = None
    for name, config in connections.items():
        if config.get('type') == selected_type:
            matching_conn = name
            break

    if matching_conn:
        try:
            connector = get_connector(matching_conn)
            if hasattr(connector, 'run_query'):
                return connector.run_query(question)
            else:
                catalog, tables = connector.get_schema()
                return (
                    f"✅ Connected to **{matching_conn}** ({selected_type}). "
                    f"Found {len(tables)} tables. "
                    f"Full LLM-powered query support coming soon."
                )
        except NotImplementedError as e:
            return f"⚠️ {e}"
        except Exception as e:
            return f"⚠️ Connector error: {e}"

    # No config file found for this type
    return (
        f"⚠️ **{active_source}** is not configured yet.\n\n"
        f"To set it up:\n"
        f"1. Copy `config/connections/{selected_type}.yaml.template` → "
        f"`config/connections/{selected_type}.yaml`\n"
        f"2. Fill in your connection details\n"
        f"3. Restart the app"
    )


# ── UI Components ────────────────────────────────────────────────────────────

def _render_hero():
    """Render the Spotter-inspired hero/welcome section."""
    logo_uri = _get_logo_b64()

    logo_html = ""
    if logo_uri:
        logo_html = f'<img src="{logo_uri}" class="hero-logo-img" alt="AI Data Analyst"/>'

    st.markdown(f"""
    <div class="hero-section">
        {logo_html}
        <div class="hero-title" style="color:#059669;">AI Data Analyst Agent</div>
        <div class="hero-subtitle">Instant answers from your data</div>
        <div class="hero-desc">
            Ask questions in plain English. The agent generates SQL, executes it
            against your data warehouse, and delivers trusted answers in seconds.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Feature pills (Spotter-style)
    st.markdown("""
    <div class="features-row">
        <div class="feature-pill">
            <span class="feature-pill-icon">🧠</span>
            <div>
                <div class="feature-pill-text">Multi-step reasoning</div>
                <div class="feature-pill-desc">Breaks down complex questions</div>
            </div>
        </div>
        <div class="feature-pill">
            <span class="feature-pill-icon">⚡</span>
            <div>
                <div class="feature-pill-text">Instant insights</div>
                <div class="feature-pill-desc">SQL generated in seconds</div>
            </div>
        </div>
        <div class="feature-pill">
            <span class="feature-pill-icon">🛡️</span>
            <div>
                <div class="feature-pill-text">Enterprise-grade trust</div>
                <div class="feature-pill-desc">Read-only, fully auditable</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_suggestions():
    """Render clickable suggestion buttons."""
    st.markdown(
        '<div class="suggestions-header">Try asking</div>',
        unsafe_allow_html=True,
    )

    suggestions = [
        ("📚", "How many books are in the library?"),
        ("🚗", "What is the average price of cars?"),
        ("💰", "Top 5 most expensive cars"),
        ("📖", "List all genres in the library"),
        ("🏎️", "Cars with horsepower above 200"),
        ("📅", "Books published after 1950"),
    ]

    cols = st.columns(3)
    for i, (icon, text) in enumerate(suggestions):
        with cols[i % 3]:
            if st.button(
                f"{icon}  {text}",
                key=f"sug_{i}",
                use_container_width=True,
            ):
                st.session_state['pending_question'] = text
                st.rerun()


def _render_sidebar():
    """Render sidebar with CloudAge logo and connection info."""
    logo_uri = _get_logo_b64()

    with st.sidebar:
        # Logo
        if logo_uri:
            st.markdown(
                f'<div class="sidebar-logo">'
                f'<img src="{logo_uri}" alt="CloudAge"/>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="sidebar-logo">'
                '<span style="font-size:1.5rem; font-weight:700; color:#0D47A1;">'
                'AI Data Analyst</span></div>',
                unsafe_allow_html=True,
            )

        settings = get_settings()
        api_url = _api_base_url()

        # ── Load Balancer URL (always visible at top) ──
        st.markdown(
            '<div class="sidebar-section-title">⚖️ Load Balancer URL</div>',
            unsafe_allow_html=True,
        )
        remote_url = st.text_input(
            'ALB URL',
            value=st.session_state.get('api_url', ''),
            placeholder='http://data-arch-ai-alb-xxx.elb.amazonaws.com',
            key='api_url_input',
            label_visibility='collapsed',
        )
        if remote_url:
            st.session_state['api_url'] = remote_url.strip().rstrip('/')

        # ── Connection status ──
        st.markdown(
            '<div class="sidebar-section-title">Connection</div>',
            unsafe_allow_html=True,
        )

        if _api_base_url():
            st.markdown(
                '<div class="connection-badge">Remote API ✓</div>',
                unsafe_allow_html=True,
            )
            if not os.environ.get('API_KEY'):
                st.session_state.setdefault('api_key', '')
                st.session_state['api_key'] = st.text_input(
                    '🔑 API Key (optional)',
                    type='password',
                    key='api_key_input',
                    placeholder='X-Api-Key header',
                )
        else:
            try:
                runtime = require_runtime_settings(settings)
                st.markdown(
                    '<div class="connection-badge">Local AWS ✓</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="info-table">'
                    f'<strong>Database:</strong> {runtime.glue_db_name}<br>'
                    f'<strong>Region:</strong> {runtime.region}<br>'
                    f'<strong>Workgroup:</strong> {runtime.athena_workgroup}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            except SettingsError:
                st.markdown(
                    '<div style="padding:0.5rem 0.75rem; background:#ECFDF5; '
                    'border:1px solid #A7F3D0; border-radius:8px; '
                    'font-size:0.8rem; color:#065F46;">'
                    '⚙️ <strong>Setup needed</strong><br>'
                    'Enter a Load Balancer URL above, or fill in AWS details below.'
                    '</div>',
                    unsafe_allow_html=True,
                )

        # ── AWS Configuration (always visible) ──
        with st.expander("☁️ AWS Configuration", expanded=not bool(_api_base_url())):
            new_db = st.text_input(
                '🔗 Glue Database',
                value=os.environ.get('GLUE_DB_NAME', st.session_state.get('cfg_glue_db', '')),
                placeholder='e.g. project_library_db',
                key='cfg_glue_db_input',
            )
            new_bucket = st.text_input(
                '🪣 S3 Bucket',
                value=os.environ.get('PROJECT_FILES_BUCKET', st.session_state.get('cfg_bucket', '')),
                placeholder='e.g. langchain-471613014056-eu-north-1',
                key='cfg_bucket_input',
            )
            new_workgroup = st.text_input(
                '📊 Athena Workgroup',
                value=os.environ.get('ATHENA_WORKGROUP', st.session_state.get('cfg_workgroup', 'project-text-to-sql')),
                placeholder='e.g. project-text-to-sql',
                key='cfg_workgroup_input',
            )
            new_region = st.text_input(
                '🌍 AWS Region',
                value=os.environ.get('AWS_REGION', st.session_state.get('cfg_region', 'eu-north-1')),
                placeholder='e.g. eu-north-1',
                key='cfg_region_input',
            )

            # Save to session state so the service layer picks them up
            if new_db:
                st.session_state['cfg_glue_db'] = new_db
                os.environ['GLUE_DB_NAME'] = new_db
            if new_bucket:
                st.session_state['cfg_bucket'] = new_bucket
                os.environ['PROJECT_FILES_BUCKET'] = new_bucket
            if new_workgroup:
                st.session_state['cfg_workgroup'] = new_workgroup
                os.environ['ATHENA_WORKGROUP'] = new_workgroup
            if new_region:
                st.session_state['cfg_region'] = new_region
                os.environ['AWS_REGION'] = new_region

        st.divider()

        # ── Data Source Picker ──
        st.markdown(
            '<div class="sidebar-section-title">📊 Data Source</div>',
            unsafe_allow_html=True,
        )

        # Always show all supported connector types
        CONNECTOR_OPTIONS = {
            '☁️ Athena (AWS)': 'athena',
            '🔴 Redshift (AWS)': 'redshift',
            '🐘 RDS PostgreSQL': 'rds_postgres',
            '🐬 RDS MySQL': 'rds_mysql',
            '❄️ Snowflake': 'snowflake',
            '🧱 Databricks': 'databricks',
        }

        # Also include any configured connections from YAML files
        connections = load_connections()
        configured_names = list(connections.keys())

        # Build the full options list
        all_options = list(CONNECTOR_OPTIONS.keys())
        for name in configured_names:
            if name not in all_options:
                conn_type = connections[name].get('type', 'unknown')
                all_options.append(f"📁 {name} ({conn_type})")

        current = st.session_state.get('active_source', all_options[0])
        if current not in all_options:
            current = all_options[0]

        selected = st.selectbox(
            'Active data source',
            options=all_options,
            index=all_options.index(current),
            key='source_selector',
            label_visibility='collapsed',
        )
        st.session_state['active_source'] = selected

        # Show connection status for selected source
        selected_type = CONNECTOR_OPTIONS.get(selected, '')
        if selected_type:
            # Check if any loaded connection matches this type
            has_config = any(
                c.get('type') == selected_type for c in connections.values()
            )
            if has_config or selected_type == 'athena':
                st.caption(f"✅ Type: `{selected_type}` — configured")
            else:
                st.caption(f"⚠️ No `.yaml` config found for `{selected_type}`")

        st.divider()

        # Actions
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🗑️ Clear", use_container_width=True):
                st.session_state['messages'] = []
                st.rerun()
        with col2:
            if st.button("🔄 Reconnect", use_container_width=True):
                st.cache_resource.clear()
                st.rerun()
        with col3:
            if st.button("🚪 Logout", use_container_width=True):
                st.session_state['authenticated'] = False
                st.session_state['messages'] = []
                st.rerun()

        # Footer
        st.markdown(
            '<div style="text-align:center; font-size:0.7rem; color:#94A3B8; '
            'padding:1rem 1rem 0.5rem; margin-top:1rem;">'
            'Powered by AWS Bedrock + Athena'
            '</div>',
            unsafe_allow_html=True,
        )



def _check_login() -> bool:
    """Display login form and validate credentials.

    Credentials are read from environment variables:
      - APP_USERNAME (default: admin)
      - APP_PASSWORD (default: cloudage)

    Returns True if authenticated, False otherwise.
    """
    if st.session_state.get('authenticated'):
        return True

    # Get credentials from env (or defaults for training)
    valid_username = os.environ.get('APP_USERNAME', 'admin')
    valid_password = os.environ.get('APP_PASSWORD', 'cloudage')

    logo_uri = _get_logo_b64()

    # Center the login form
    st.markdown("""
    <style>
    [data-testid="stForm"] {
        max-width: 400px;
        margin: 0 auto;
        padding: 2rem;
        border: 1px solid #E2E8F0;
        border-radius: 16px;
        background: #FFFFFF;
        box-shadow: 0 4px 24px rgba(0,0,0,0.06);
    }
    </style>
    """, unsafe_allow_html=True)

    # Logo + title
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if logo_uri:
            st.markdown(
                f'<div style="text-align:center; padding:2rem 0 1rem;">'
                f'<img src="{logo_uri}" style="width:180px;" alt="AI Data Analyst"/>'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.markdown(
            '<p style="text-align:center; color:#64748B; font-size:0.9rem; margin-bottom:1.5rem;">'
            'Sign in to Data Intelligence</p>',
            unsafe_allow_html=True,
        )

    # Login form
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form('login_form'):
            username = st.text_input('Username', placeholder='Enter username')
            password = st.text_input('Password', type='password', placeholder='Enter password')
            submitted = st.form_submit_button('Sign In', use_container_width=True)

            if submitted:
                if username == valid_username and password == valid_password:
                    st.session_state['authenticated'] = True
                    st.session_state['user'] = username
                    st.rerun()
                else:
                    st.error('Invalid username or password')

    return False


def main() -> None:
    st.set_page_config(
        page_title='AI Data Analyst Agent',
        page_icon='🤖',
        layout='centered',
        initial_sidebar_state='collapsed',
    )

    _inject_custom_css()

    # ── Login gate ──
    if not _check_login():
        return

    _render_sidebar()

    # Initialize state
    if 'messages' not in st.session_state:
        st.session_state['messages'] = []

    # Show hero or chat history
    if not st.session_state['messages']:
        _render_hero()
        _render_suggestions()
    else:
        # Compact header in chat mode — show logo
        logo_uri = _get_logo_b64()
        if logo_uri:
            st.markdown(
                f'<div class="chat-header">'
                f'<img src="{logo_uri}" alt="CloudAge"/>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Render chat history
        for msg in st.session_state['messages']:
            role = msg['role']
            content = msg['content']
            with st.chat_message(role):
                st.markdown(content)

    # Handle pending question from suggestion buttons
    pending = st.session_state.pop('pending_question', None)
    question = pending or st.chat_input("Ask Bigger Questions")

    if not question:
        return

    # Add user message
    st.session_state['messages'].append({'role': 'user', 'content': question})
    with st.chat_message('user'):
        st.markdown(question)

    # Generate response
    with st.chat_message('assistant'):
        thinking = st.empty()
        thinking.markdown(
            '<span style="color:#64748B; font-size:0.85rem;">'
            '🔍 Analyzing your question and generating SQL…</span>',
            unsafe_allow_html=True,
        )
        try:
            answer = _ask(question)
            thinking.empty()
            st.markdown(answer)
            st.session_state['messages'].append(
                {'role': 'assistant', 'content': answer}
            )
        except Exception as exc:
            thinking.empty()
            err_msg = f"⚠️ **Error:** {exc}"
            st.markdown(err_msg)
            st.session_state['messages'].append(
                {'role': 'assistant', 'content': err_msg}
            )


if __name__ == '__main__':
    main()
