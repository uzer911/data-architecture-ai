# Interview Explanation Steering

## One-Line Summary

This project is an AI-powered Text-to-SQL data analyst agent: a user asks a question in plain English, Amazon Bedrock generates SQL, the app validates the SQL for safety, Athena runs it against data stored in S3, and the final result is converted back into a human-readable answer.

## How To Explain The Project

When explaining this project in an interview, describe it as a secure natural-language analytics system.

The user does not need to know SQL. They can ask questions such as "How many books are in the library?" or "What are the top 5 most expensive cars?" The system reads the available database schema, asks an LLM to generate SQL, validates that the generated SQL is safe, executes it on the data source, and then returns a clean English answer.

## Main Runtime Flow

1. The user asks a question in the Streamlit chat UI or through the FastAPI `/query` endpoint.
2. The backend loads runtime configuration such as Glue database name, S3 bucket, AWS region, Athena workgroup, and Bedrock model.
3. The service reads table and column metadata from AWS Glue.
4. The Glue schema is sent to Amazon Bedrock along with the user question.
5. Bedrock decides whether the question can be answered from the database and suggests SQL.
6. The app extracts the SQL from the model response.
7. The app validates the SQL before execution.
8. The app blocks destructive SQL such as `DROP`, `DELETE`, `UPDATE`, `INSERT`, `CREATE`, and multi-statement SQL.
9. The app checks that the SQL references known allowed tables.
10. The app adds a result `LIMIT` if the model did not include one.
11. Athena executes the SQL against data stored in S3.
12. The raw query result is sent back to Bedrock.
13. Bedrock converts the raw result into a clear final answer.
14. The answer is returned to the user.

## LangChain Clarification

The README and dependency list mention LangChain because the original proof of concept was based around LangChain and Bedrock for Text-to-SQL.

In the current production code path, the main LLM call is made directly through `boto3` using the Bedrock Runtime client. The app keeps LangChain dependencies, but the safer production logic is custom code inside `src/llm_sql/core.py`.

Explain it like this:

"LangChain is part of the project dependency set and POC direction, but the current production service uses direct Bedrock calls through boto3. This gives the app tighter control over prompts, SQL extraction, validation, retry behavior, and safety rules."

## Service Names And Responsibilities

### Amazon Bedrock

Amazon Bedrock provides the large language model. It is used to understand the natural-language question, generate SQL, and convert raw query results into a final English answer.

### Amazon S3

Amazon S3 stores the source data files, such as CSV and JSON datasets. Athena queries these files directly.

### AWS Glue

AWS Glue stores the data catalog. It tells the app which databases, tables, and columns exist.

### AWS Glue Crawler

Glue Crawlers scan S3 data and create or update table metadata in the Glue Catalog.

### Amazon Athena

Athena is the SQL query engine. It runs SQL over files stored in S3 using Glue Catalog metadata.

### AWS Lambda

Lambda reacts to S3 upload events. When new data arrives in an S3 folder, Lambda can create or start a Glue Crawler so the new data becomes queryable.

### FastAPI

FastAPI exposes the backend HTTP service. It provides `/health` for health checks and `/query` for asking natural-language questions.

### Uvicorn

Uvicorn runs the FastAPI application in production or local server mode.

### Streamlit

Streamlit provides the interactive chat UI. It lets the user log in, configure AWS/API settings, select a data source, ask questions, and view answers.

### ECS Fargate

ECS Fargate runs the backend API container in AWS without managing servers.

### Application Load Balancer

The Application Load Balancer exposes the ECS service through a public URL and routes incoming HTTP requests to the running containers.

### Amazon ECR

ECR stores the Docker container image used by ECS Fargate.

### CloudWatch Logs

CloudWatch Logs stores application logs from ECS and Lambda so operators can debug runtime behavior.

### AWS Secrets Manager

Secrets Manager stores credentials securely, such as database passwords, Bedrock credential overrides, and connector tokens.

### Amazon RDS Aurora Serverless v2

Aurora is optional. It provides a managed relational database for the RDS MySQL connector path.

### VPC, Subnets, Security Groups, And VPC Endpoints

These provide the network foundation. The ALB lives in public subnets, ECS and databases live in private subnets, security groups control traffic, and VPC endpoints allow private access to AWS services.

### IAM Roles And Policies

IAM controls permissions. ECS, Lambda, Glue Crawlers, and other services need roles to access S3, Glue, Athena, Bedrock, CloudWatch, and Secrets Manager.

## Important Code Areas

- `src/llm_sql/core.py`: Main LLM-to-SQL service, Bedrock calls, SQL extraction, validation, execution, and final answer generation.
- `src/llm_sql/runner.py`: Builds the Athena-backed service and connects Glue, Athena, and the LLM service.
- `src/llm_sql/api.py`: FastAPI app with `/health` and `/query`.
- `scripts/streamlit_app.py`: Chat UI and local/remote query flow.
- `src/llm_sql/connectors/`: Multi-database connector framework.
- `lambda/s3_trigger_crawler/handler.py`: S3 event to Glue Crawler automation.
- `cloudformation-template-validated.yml`: Main infrastructure stack.
- `cloudformation-rds-aurora.yml`: Optional Aurora database stack.

## Interview-Ready Spoken Answer

This project is an AI data analyst agent. The user asks a question in normal English, and the system converts it into SQL, runs the SQL on the data, and returns a simple English answer.

The data is stored in Amazon S3. AWS Glue crawlers scan that data and create table metadata in the Glue Catalog. Athena uses that catalog to run SQL directly on the S3 data.

For the AI part, the system uses Amazon Bedrock. The backend sends Bedrock the user question and the database schema. Bedrock generates SQL. Before executing that SQL, the app validates it very carefully. It only allows read-only SQL, blocks dangerous commands, checks table names, blocks multiple statements, and adds a limit to avoid large result sets.

After validation, Athena executes the SQL. The result comes back to the Python service, and the service sends that result back to Bedrock so the model can explain it in a clear sentence.

The frontend is Streamlit, which gives the user a chat interface. The backend is FastAPI, which exposes `/health` and `/query`. In production, the FastAPI service runs as a Docker container on ECS Fargate behind an Application Load Balancer.

LangChain is included in the project and was part of the original proof of concept, but the current production code mainly calls Bedrock directly using boto3. That gives the service more control over prompt handling, SQL validation, and safety.

So the short version is: S3 stores data, Glue describes the data, Athena queries the data, Bedrock generates and explains SQL, FastAPI serves the backend, Streamlit provides the UI, and ECS deploys the API in AWS.
