# Tasks: Data Analyst Agent LangChain

## Task 1: Agent Package Scaffold and Configuration

- [ ] 1.1 Create `src/llm_sql/agent/__init__.py` with exports for AgentService and AgentResponse
- [ ] 1.2 Create `src/llm_sql/agent/config.py` with AgentSettings Pydantic model (AGENT_MAX_ITERATIONS, AGENT_MODEL, AGENT_TEMPERATURE, AGENT_MEMORY_MAX_TOKENS, AGENT_MAX_RETRIES)
- [ ] 1.3 Integrate AgentSettings into existing `src/llm_sql/config.py` Settings class or compose them
- [ ] 1.4 Create `src/llm_sql/agent/models.py` with AgentResponse and AgentMetadata dataclasses
- [ ] 1.5 Write unit tests for AgentSettings validation (valid defaults, invalid values raise SettingsError)

## Task 2: Query Validator Extraction

- [ ] 2.1 Create `src/llm_sql/agent/validator.py` with QueryValidator class extracted from core.py
- [ ] 2.2 Implement `validate(sql)` method: destructive keywords, read-only check, multi-statement, comments, table allowlist
- [ ] 2.3 Implement `apply_limit(sql)` method: append LIMIT when missing, preserve existing LIMIT
- [ ] 2.4 Write property-based test: QueryValidator rejects all destructive SQL (hypothesis)
- [ ] 2.5 Write property-based test: apply_limit always produces output containing LIMIT clause
- [ ] 2.6 Refactor core.py to use QueryValidator internally (backward compatibility)

## Task 3: Agent Tools Implementation

- [ ] 3.1 Create `src/llm_sql/agent/tools.py` with tool factory functions
- [ ] 3.2 Implement `create_sql_tool(connector, validator)` — validates and executes SQL, returns results or error
- [ ] 3.3 Implement `create_schema_tool(connector)` — returns full or filtered schema with dialect info
- [ ] 3.4 Implement `create_validate_tool(validator)` — dry-run validation without execution
- [ ] 3.5 Write property-based test: SQL tool never executes when validator rejects (mock connector)
- [ ] 3.6 Write unit tests for schema tool output format (includes dialect, structured listing)

## Task 4: Result Formatter

- [ ] 4.1 Create `src/llm_sql/agent/formatter.py` with format_results_as_table function
- [ ] 4.2 Implement markdown table formatting from list of dicts
- [ ] 4.3 Implement format_agent_response combining answer text with data tables
- [ ] 4.4 Write property-based test: format_results_as_table produces valid markdown table for any list of dicts with scalar values
- [ ] 4.5 Handle edge cases: empty results, single row, missing keys, long values

## Task 5: Conversation Memory Manager

- [ ] 5.1 Create `src/llm_sql/agent/memory.py` with SessionMemoryManager class
- [ ] 5.2 Implement get_memory(session_id) — creates or retrieves ConversationTokenBufferMemory
- [ ] 5.3 Implement clear_session(session_id) — removes memory for a session
- [ ] 5.4 Implement token limit enforcement (discard oldest when exceeded)
- [ ] 5.5 Write property-based test: memory token count never exceeds configured maximum
- [ ] 5.6 Write unit test: two sessions have independent memory (isolation)

## Task 6: Agent Service Core

- [ ] 6.1 Create `src/llm_sql/agent/service.py` with AgentService class
- [ ] 6.2 Implement constructor accepting BaseConnector and AgentSettings
- [ ] 6.3 Implement `_build_executor(session_id)` — creates LangChain AgentExecutor with ReAct agent, tools, and memory
- [ ] 6.4 Implement `run_query(question, session_id)` — executes agent loop, collects intermediate steps, returns AgentResponse
- [ ] 6.5 Implement iteration limit enforcement and partial answer on truncation
- [ ] 6.6 Implement retry logic: max 3 retries per failed SQL query with error context
- [ ] 6.7 Write unit test: agent respects iteration limit (mock LLM)
- [ ] 6.8 Write unit test: run_query always returns AgentResponse with non-empty answer

## Task 7: API Integration

- [ ] 7.1 Extend QueryResponse model with optional `metadata` field (sql_queries, reasoning_steps)
- [ ] 7.2 Add agent mode flag to settings (AGENT_MODE, default True)
- [ ] 7.3 Modify `get_service()` to return AgentService when agent mode is enabled
- [ ] 7.4 Update `/query` endpoint to handle AgentResponse and populate metadata
- [ ] 7.5 Update `/health` endpoint to verify AgentService initialization
- [ ] 7.6 Write unit tests for API backward compatibility (answer field always present)

## Task 8: Streamlit UI Integration

- [ ] 8.1 Add sidebar toggle for agent mode ("🤖 Agent Mode" checkbox, default on)
- [ ] 8.2 Implement agent-mode `_ask` function that calls AgentService.run_query with session_id
- [ ] 8.3 Display reasoning steps in `st.expander("🧠 Reasoning Steps")` below the answer
- [ ] 8.4 Display executed SQL queries in `st.code(sql, language="sql")` blocks
- [ ] 8.5 Add `st.status` progress indicator during agent processing
- [ ] 8.6 Maintain backward compatibility: legacy chain mode still works when toggle is off

## Task 9: Multi-Connector Integration

- [ ] 9.1 Update AgentService to accept any BaseConnector and rebuild tools on connector change
- [ ] 9.2 Include connector dialect in the agent system prompt for SQL generation
- [ ] 9.3 Wire Streamlit data source selector to AgentService connector switching
- [ ] 9.4 Write unit test: AgentService initializes with mock connectors of different dialects

## Task 10: End-to-End Testing and Documentation

- [ ] 10.1 Write integration test: full agent loop with mocked Bedrock and mocked connector
- [ ] 10.2 Write integration test: self-correction flow (first query fails, retry succeeds)
- [ ] 10.3 Write integration test: conversation memory follow-up question
- [ ] 10.4 Update README.md with agent mode documentation and new environment variables
- [ ] 10.5 Add `AGENT_*` variables to `.env.template`
- [ ] 10.6 Verify `make test` passes with all new tests
