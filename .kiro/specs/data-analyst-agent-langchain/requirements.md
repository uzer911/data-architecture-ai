# Requirements Document

## Introduction

The Data Analyst Agent replaces the current chain-based text-to-SQL pipeline with a LangChain Agent that can reason about data, use tools iteratively, self-correct SQL errors, and provide richer analytical responses. Unlike the existing single-pass approach (question → SQL → result → answer), the agent can decompose complex questions into multiple steps, inspect intermediate results, retry failed queries, and combine insights from multiple queries to deliver comprehensive data analysis.

The agent integrates with the existing multi-connector framework and AWS Bedrock (Amazon Nova models), preserving all current safety guardrails (read-only execution, table allowlisting, LIMIT enforcement) while adding agentic capabilities.

## Glossary

- **Agent**: A LangChain Agent that uses an LLM to decide which tools to invoke, in what order, and how to interpret results — as opposed to a fixed chain of operations.
- **Tool**: A callable function registered with the Agent that performs a specific action (e.g., execute SQL, inspect schema, validate a query).
- **Agent_Executor**: The LangChain AgentExecutor runtime that manages the agent loop — invoking tools, collecting observations, and deciding when to produce a final answer.
- **Thought_Action_Observation**: The reasoning cycle where the Agent produces a thought (reasoning), selects an action (tool call), and receives an observation (tool result).
- **SQL_Tool**: A tool that executes validated, read-only SQL queries against the active data source connector and returns results.
- **Schema_Tool**: A tool that retrieves database schema information (tables, columns, types) from the active connector.
- **Query_Validator**: The component that checks SQL queries for safety before execution (read-only, allowlisted tables, no destructive operations).
- **Connector**: An implementation of BaseConnector that provides schema discovery and SQL execution for a specific data source (Athena, Redshift, RDS, Snowflake, Databricks).
- **Agent_Configuration**: Settings that control agent behavior including maximum iterations, model selection, temperature, and tool availability.
- **Iteration_Limit**: The maximum number of reasoning steps the Agent may take before returning a response, preventing infinite loops.
- **Conversation_Memory**: A buffer that stores prior exchanges within a session so the Agent can reference earlier questions and results.

## Requirements

### Requirement 1: Agent Core Loop

**User Story:** As a data analyst, I want the system to reason through complex questions step-by-step, so that I get accurate answers to multi-part analytical questions.

#### Acceptance Criteria

1. WHEN a natural language question is submitted, THE Agent_Executor SHALL invoke the Agent to produce a Thought_Action_Observation cycle until a final answer is determined.
2. WHILE the Agent is processing, THE Agent_Executor SHALL enforce the configured Iteration_Limit to prevent unbounded execution.
3. IF the Agent exceeds the Iteration_Limit, THEN THE Agent_Executor SHALL return a partial answer summarizing progress made and indicate that the analysis was truncated.
4. THE Agent_Executor SHALL pass the active Connector context to all tools so that queries execute against the user-selected data source.
5. WHEN the Agent produces a final answer, THE Agent_Executor SHALL include the SQL queries executed and their results as structured metadata alongside the natural language response.

### Requirement 2: SQL Execution Tool

**User Story:** As a data analyst, I want the agent to execute SQL queries safely against my data source, so that I can get real query results as part of the analysis.

#### Acceptance Criteria

1. WHEN the Agent invokes the SQL_Tool with a SQL query string, THE SQL_Tool SHALL pass the query through the Query_Validator before execution.
2. IF the Query_Validator rejects the SQL query, THEN THE SQL_Tool SHALL return the validation error message to the Agent as an observation without executing the query.
3. WHEN a valid SQL query is executed, THE SQL_Tool SHALL return the result rows formatted as a readable table string to the Agent.
4. THE SQL_Tool SHALL enforce the configured maximum result row limit on all executed queries.
5. IF SQL execution raises a database error, THEN THE SQL_Tool SHALL return the error message to the Agent so it can attempt a corrected query.

### Requirement 3: Schema Inspection Tool

**User Story:** As a data analyst, I want the agent to inspect available tables and columns, so that it can generate accurate SQL for my specific database schema.

#### Acceptance Criteria

1. WHEN the Agent invokes the Schema_Tool, THE Schema_Tool SHALL return the full catalog of available databases, tables, and columns from the active Connector.
2. THE Schema_Tool SHALL format the schema as a structured listing with database name, table name, and column names clearly delineated.
3. WHEN the Agent invokes the Schema_Tool with a specific table name argument, THE Schema_Tool SHALL return only the columns and metadata for that table.

### Requirement 4: Query Validation and Safety

**User Story:** As a platform operator, I want all agent-generated SQL to pass through the same safety checks as the existing system, so that the agent cannot perform destructive operations.

#### Acceptance Criteria

1. THE Query_Validator SHALL reject SQL queries containing destructive keywords (DROP, DELETE, UPDATE, ALTER, INSERT, TRUNCATE, CREATE, REPLACE).
2. THE Query_Validator SHALL reject SQL queries that do not begin with a read-only statement (SELECT or WITH).
3. THE Query_Validator SHALL reject multi-statement SQL queries (containing semicolons followed by additional statements).
4. THE Query_Validator SHALL reject SQL queries referencing tables not present in the allowed tables set from the active Connector.
5. THE Query_Validator SHALL reject SQL queries containing SQL comments (-- or /* */).
6. WHEN a SQL query passes validation but lacks a LIMIT clause, THE Query_Validator SHALL append a LIMIT clause using the configured maximum result row count.

### Requirement 5: Self-Correction on SQL Errors

**User Story:** As a data analyst, I want the agent to automatically fix SQL errors and retry, so that I get answers without needing to manually debug queries.

#### Acceptance Criteria

1. WHEN the SQL_Tool returns a database error to the Agent, THE Agent SHALL analyze the error message and attempt to generate a corrected SQL query.
2. THE Agent SHALL make a maximum of 3 retry attempts for a single logical query before reporting the failure to the user.
3. WHEN the Agent retries a failed query, THE Agent SHALL include the original error message in its reasoning to inform the correction.

### Requirement 6: Conversation Memory

**User Story:** As a data analyst, I want the agent to remember previous questions and answers in my session, so that I can ask follow-up questions without repeating context.

#### Acceptance Criteria

1. WHILE a user session is active, THE Conversation_Memory SHALL retain all prior question-answer pairs for the Agent to reference.
2. WHEN the user asks a follow-up question referencing prior context, THE Agent SHALL use Conversation_Memory to resolve references to earlier results.
3. THE Conversation_Memory SHALL be scoped to individual user sessions and not shared across sessions.
4. THE Conversation_Memory SHALL enforce a configurable maximum token limit, discarding the oldest exchanges when the limit is exceeded.

### Requirement 7: Agent Configuration

**User Story:** As a platform operator, I want to configure agent behavior through environment variables, so that I can tune performance and cost without code changes.

#### Acceptance Criteria

1. THE Agent_Configuration SHALL support the following settings via environment variables: AGENT_MAX_ITERATIONS (default 10), AGENT_MODEL (default from BEDROCK_MODEL), AGENT_TEMPERATURE (default 0.0), AGENT_MEMORY_MAX_TOKENS (default 4000).
2. THE Agent_Configuration SHALL be validated at startup using the existing Pydantic BaseSettings pattern.
3. IF an Agent_Configuration value is invalid, THEN THE Agent_Configuration SHALL raise a SettingsError with a descriptive message at startup.

### Requirement 8: API Integration

**User Story:** As a developer integrating with the service, I want the agent to be accessible through the existing HTTP API, so that I can use the enhanced capabilities without changing my client code.

#### Acceptance Criteria

1. WHEN a POST request is sent to the /query endpoint, THE API SHALL route the question to the Agent_Executor instead of the legacy chain-based service.
2. THE API response format SHALL remain backward-compatible, returning an "answer" field with the natural language response.
3. THE API SHALL add an optional "metadata" field to the response containing the list of SQL queries executed and the number of reasoning steps taken.
4. WHEN the Agent_Executor encounters an unrecoverable error, THE API SHALL return an HTTP 500 response with a descriptive error message.
5. THE /health endpoint SHALL verify that the Agent_Executor can be initialized without executing a query.

### Requirement 9: Streamlit UI Integration

**User Story:** As a data analyst using the chat interface, I want to see the agent's reasoning process, so that I can understand how it arrived at an answer.

#### Acceptance Criteria

1. WHEN the Agent produces intermediate reasoning steps, THE Streamlit UI SHALL display them in a collapsible section below the final answer.
2. THE Streamlit UI SHALL display each SQL query executed by the Agent in a formatted code block within the reasoning section.
3. WHILE the Agent is processing, THE Streamlit UI SHALL display a progress indicator showing the current reasoning step number.
4. THE Streamlit UI SHALL support both the legacy chain mode and the new agent mode, selectable via a sidebar toggle.

### Requirement 10: Multi-Connector Support

**User Story:** As a data analyst, I want the agent to work with any configured data source, so that I can analyze data regardless of where it is stored.

#### Acceptance Criteria

1. THE Agent_Executor SHALL accept any BaseConnector implementation as its data source.
2. WHEN the active Connector changes (via sidebar selection), THE Agent_Executor SHALL reinitialize its tools with the new Connector's schema and execution capabilities.
3. THE Schema_Tool SHALL include the Connector's SQL dialect in its output so the Agent generates dialect-appropriate SQL.
4. THE SQL_Tool SHALL use the active Connector's execute_sql method for query execution.

### Requirement 11: Agent Response Formatting

**User Story:** As a data analyst, I want the agent's answers to be well-formatted and include supporting data, so that I can quickly understand and trust the results.

#### Acceptance Criteria

1. WHEN the Agent produces a final answer, THE Agent_Executor SHALL format the response as a natural language summary followed by any supporting data tables.
2. WHEN query results contain tabular data, THE Agent_Executor SHALL format the data as a markdown table in the response.
3. THE Agent_Executor SHALL include the executed SQL query in the response metadata for auditability.
