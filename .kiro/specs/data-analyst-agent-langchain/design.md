# Design Document: Data Analyst Agent LangChain

## Overview

This design replaces the current single-pass chain-based text-to-SQL pipeline (`LLMSQLService`) with a LangChain Agent architecture. The agent uses a ReAct-style reasoning loop (Thought → Action → Observation) to decompose complex questions, execute SQL iteratively, self-correct errors, and produce comprehensive analytical responses.

The design preserves backward compatibility with the existing API contract, connector framework, and safety guardrails while adding agentic capabilities.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Streamlit UI / FastAPI                   │
│                  (mode toggle: chain vs agent)                │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                     AgentService                             │
│  ┌───────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ Agent Config  │  │  Memory Mgr  │  │ Response Format │  │
│  └───────────────┘  └──────────────┘  └─────────────────┘  │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   LangChain AgentExecutor                     │
│                                                              │
│  ┌─────────┐    ┌──────────┐    ┌────────────────────────┐  │
│  │  Agent  │───▶│  Tools   │───▶│  BaseConnector (any)   │  │
│  │ (ReAct) │    │          │    │  - Athena              │  │
│  └─────────┘    │ SQL_Tool │    │  - Redshift            │  │
│       │         │ Schema   │    │  - RDS                 │  │
│       ▼         │ Validate │    │  - Snowflake           │  │
│  ┌─────────┐   └──────────┘    │  - Databricks          │  │
│  │ Bedrock │                    └────────────────────────┘  │
│  │  (Nova) │                                                 │
│  └─────────┘                                                 │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. Agent Configuration (`src/llm_sql/agent/config.py`)

Extends the existing Pydantic `Settings` class with agent-specific fields:

```python
class AgentSettings(BaseSettings):
    agent_max_iterations: int = Field(10, env='AGENT_MAX_ITERATIONS', ge=1, le=50)
    agent_model: str | None = Field(None, env='AGENT_MODEL')  # Falls back to BEDROCK_MODEL
    agent_temperature: float = Field(0.0, env='AGENT_TEMPERATURE', ge=0.0, le=1.0)
    agent_memory_max_tokens: int = Field(4000, env='AGENT_MEMORY_MAX_TOKENS', ge=500, le=32000)
    agent_max_retries: int = Field(3, env='AGENT_MAX_RETRIES', ge=1, le=10)
```

### 2. Agent Tools (`src/llm_sql/agent/tools.py`)

Three LangChain `Tool` instances wrapping the connector:

- **`sql_query`** — Validates and executes SQL, returns results or error
- **`inspect_schema`** — Returns full or filtered schema from the connector
- **`validate_sql`** — Dry-run validation without execution (for agent self-check)

Each tool receives the active `BaseConnector` and `QueryValidator` via closure.

### 3. Query Validator (`src/llm_sql/agent/validator.py`)

Extracted from the existing `LLMSQLService._validate_sql_query` and `_apply_result_limit` methods into a standalone, testable class:

```python
class QueryValidator:
    def __init__(self, allowed_tables: set[str], max_result_rows: int):
        ...

    def validate(self, sql: str) -> str | None:
        """Return error message if invalid, None if valid."""

    def apply_limit(self, sql: str) -> str:
        """Append LIMIT if missing."""
```

### 4. Agent Service (`src/llm_sql/agent/service.py`)

The main orchestrator that replaces `LLMSQLService.run_query` for agent mode:

```python
class AgentService:
    def __init__(self, connector: BaseConnector, config: AgentSettings):
        ...

    def run_query(self, question: str, session_id: str | None = None) -> AgentResponse:
        """Execute the agent loop and return structured response."""

    def get_executor(self, session_id: str) -> AgentExecutor:
        """Build or retrieve a cached AgentExecutor with memory for this session."""
```

### 5. Conversation Memory (`src/llm_sql/agent/memory.py`)

Session-scoped memory using LangChain's `ConversationTokenBufferMemory`:

```python
class SessionMemoryManager:
    def __init__(self, max_tokens: int):
        ...

    def get_memory(self, session_id: str) -> ConversationTokenBufferMemory:
        """Get or create memory for a session."""

    def clear_session(self, session_id: str) -> None:
        """Clear memory for a session."""
```

### 6. Response Model (`src/llm_sql/agent/models.py`)

```python
@dataclass
class AgentResponse:
    answer: str
    metadata: AgentMetadata | None = None

@dataclass
class AgentMetadata:
    sql_queries: list[str]
    reasoning_steps: int
    tools_used: list[str]
```

### 7. Result Formatter (`src/llm_sql/agent/formatter.py`)

Converts raw query results into markdown tables:

```python
def format_results_as_table(rows: list[dict]) -> str:
    """Convert list of dicts to markdown table string."""

def format_agent_response(answer: str, results: list[dict] | None) -> str:
    """Combine natural language answer with formatted data."""
```

## File Structure

```
src/llm_sql/agent/
├── __init__.py          # Exports AgentService, AgentResponse
├── config.py            # AgentSettings (Pydantic)
├── service.py           # AgentService — main orchestrator
├── tools.py             # LangChain Tool definitions
├── validator.py         # QueryValidator (extracted from core.py)
├── memory.py            # SessionMemoryManager
├── models.py            # AgentResponse, AgentMetadata dataclasses
└── formatter.py         # Result formatting (markdown tables)
```

## Integration Points

### API (`src/llm_sql/api.py`)

- Add `agent_mode: bool = True` to settings
- When agent mode is enabled, `get_service()` returns an `AgentService` instead of `LLMSQLService`
- Response model extended with optional `metadata` field
- Backward compatible: `{"answer": "..."}` always present

### Streamlit (`scripts/streamlit_app.py`)

- Add sidebar toggle: "🤖 Agent Mode" (default on)
- When agent mode is active, display reasoning steps in `st.expander`
- Show SQL queries in `st.code` blocks
- Progress indicator via `st.status` during agent execution

### Connector Framework

- No changes to `BaseConnector` interface
- Agent tools call `connector.get_schema()` and `connector.execute_sql()`
- Dialect from `connector.dialect` included in agent system prompt

## LangChain Agent Configuration

```python
from langchain.agents import AgentExecutor, create_react_agent
from langchain_community.chat_models import BedrockChat

llm = BedrockChat(
    model_id=config.agent_model or config.bedrock_model,
    region_name=config.region,
    model_kwargs={"temperature": config.agent_temperature},
)

agent = create_react_agent(llm=llm, tools=tools, prompt=agent_prompt)
executor = AgentExecutor(
    agent=agent,
    tools=tools,
    memory=memory,
    max_iterations=config.agent_max_iterations,
    handle_parsing_errors=True,
    return_intermediate_steps=True,
)
```

## Safety Considerations

1. **All existing guardrails preserved** — QueryValidator enforces read-only, allowlist, LIMIT
2. **Iteration limit** — Prevents runaway agent loops (default 10, configurable)
3. **Retry limit** — Max 3 retries per failed query prevents infinite error loops
4. **Memory bounded** — Token limit prevents unbounded memory growth
5. **No new network access** — Agent tools only access the configured connector
6. **Audit trail** — All SQL queries logged and returned in metadata

## Correctness Properties

### Property 1: Query Validator Rejects Destructive SQL (Req 4.1, 4.2, 4.3, 4.5)

For any SQL string containing destructive keywords, not starting with SELECT/WITH, containing multiple statements, or containing comments, the QueryValidator SHALL return a non-None error message.

### Property 2: Query Validator Preserves Valid SQL (Req 4.6)

For any valid SELECT/WITH query referencing allowed tables without a LIMIT clause, `apply_limit(sql)` SHALL produce a string that ends with `LIMIT <max_rows>` and contains the original query as a prefix.

### Property 3: SQL Tool Never Executes Invalid Queries (Req 2.1, 2.2)

For any SQL string that the QueryValidator rejects, the SQL_Tool SHALL return an error observation and the connector's `execute_sql` method SHALL NOT be called.

### Property 4: Agent Respects Iteration Limit (Req 1.2)

For any question and any iteration limit N >= 1, the Agent_Executor SHALL complete in at most N tool invocations.

### Property 5: Memory Token Bound (Req 6.4)

For any sequence of exchanges added to Conversation_Memory, the total token count SHALL never exceed the configured maximum.

### Property 6: Result Formatter Round-Trip (Req 11.2)

For any list of dictionaries with string keys and scalar values, `format_results_as_table` SHALL produce a valid markdown table with a header row matching the dictionary keys and data rows matching the values.

### Property 7: Agent Response Always Contains Answer (Req 8.2)

For any agent execution (success or failure), the AgentResponse SHALL always contain a non-empty `answer` field.

### Property 8: Schema Tool Includes Dialect (Req 10.3)

For any BaseConnector implementation, the Schema_Tool output SHALL contain the connector's dialect string.

### Property 9: Retry Count Bounded (Req 5.2)

For any sequence of SQL execution failures, the Agent SHALL invoke the SQL_Tool at most 3 additional times for the same logical query.

### Property 10: Session Memory Isolation (Req 6.3)

For any two distinct session IDs, exchanges added to one session's memory SHALL NOT appear in the other session's memory.
