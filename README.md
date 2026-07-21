# Data Architecture with Generative AI

![Project Status](https://img.shields.io/badge/Status-Active-green)

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Quick Setup](#quick-setup)
- [Docker Desktop](#docker-desktop)
- [Project Structure](#project-structure)
- [S3 Buckets](#s3-buckets)
- [Deployment](#deployment)
- [CloudFormation Stacks](#cloudformation-stacks)
- [CloudFormation Outputs](#cloudformation-outputs)
- [Data & Testing](#data--testing)
- [Production Baseline](#production-baseline)
- [Production-Grade Setup](#production-grade-setup)
- [Notebook Environment Variable](#notebook-environment-variable)
- [Streamlit UI](#streamlit-ui)
- [Next Steps](#next-steps)
- [Contributing](#contributing)
- [License](#license)

## Overview

This project demonstrates building a robust data architecture leveraging Generative AI, specifically focusing on using LangChain and AWS Bedrock for text-to-SQL conversion and data querying. It provides a scalable, cloud-native solution for interacting with data using natural language.

## Features

- **Text-to-SQL Conversion**: Utilizes LangChain and AWS Bedrock to translate natural language queries into SQL commands.
- **Data Querying**: Seamlessly queries various data sources (e.g., S3, RDS) using generated SQL.
- **Serverless Architecture**: Deploys on AWS using CloudFormation, ECS, Lambda, and Glue for scalability and cost-efficiency.
- **Streamlit UI**: Provides an interactive chat interface for natural language data interaction.
- **Comprehensive Testing**: Includes unit, smoke, and production checks for reliable deployments.
- **Production Hardening**: Implements safety measures like read-only SQL validation, `LIMIT` enforcement, and API key authentication.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

- Python 3.8+
- AWS CLI configured with appropriate credentials
- Docker Desktop (optional, for building and pushing container images)

### Quick Setup

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/uzer911/data-architecture-ai.git
    cd data-architecture-ai
    ```

2.  **Create a Python virtual environment and install dependencies**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Configure AWS credentials** (if not already done via environment variables or AWS CLI).

4.  **Run `setup.sh`** to perform optional staging actions (uploads are commented out by default):
    ```bash
    ./scripts/setup.sh
    ```

5.  **Run production checks**:
    - `make check` (syntax/compile gate)
    - `make test` (unit tests)
    - `make smoke` (local data smoke test)
    - `make prod-check` (all of the above)

## Docker Desktop

-   **Not required** for: running the Streamlit UI (`make ui`), tests, scripts, querying the deployed API, or CloudFormation operations.
-   **Required only** for building and pushing container images (`./scripts/push_ecr.sh`, `make deploy-all`, `./deploy-changeset.sh --auto`).
-   Once the image is in ECR and ECS is running, Docker Desktop can be closed.

## Project Structure

-   `requirements.txt` — Pinned project dependencies.
-   `scripts/streamlit_app.py` — Streamlit chat UI (`make ui`).
-   `scripts/setup.sh` — Helper script to install dependencies and optionally upload files.
-   `scripts/normalize_cars.py` — Ingestion and normalization for `s3_cars_data.csv`.
-   `scripts/deploy-rds.sh` — Deploys Aurora Serverless v2 (separate stack).
-   `scripts/load_rds_data.py` — Loads sample data (library + cars) into Aurora via Secrets Manager credentials.
-   `schema/cars_schema.json`, `schema/library_schema.json` — JSON Schema draft-07 definitions.
-   `cloudformation-template-validated.yml` — Main Infrastructure as Code (IaC) template (VPC, S3, Glue, ECS, Lambda).
-   `cloudformation-rds-aurora.yml` — Aurora Serverless v2 template (separate stack).
-   `config/connections/*.yaml.template` — Data source connection templates (Athena, Redshift, RDS, Snowflake, Databricks).
-   `src/llm_sql/connectors/` — Multi-connector framework.
-   `.env.template` — Environment variable template.
-   `deploy-changeset.sh` — Deployment script for the main stack.
-   `DEPLOYMENT.md` — Detailed deployment guide with examples.

## S3 Buckets

The CloudFormation template creates an S3 data bucket with a globally unique name. For example:

-   `langchain-471613014056-eu-north-1` — Primary bucket (eu-north-1).

The bucket features versioning, AES-256 encryption, blocked public access, and a 30-day lifecycle rule to expire Athena query results.

## Deployment

Refer to [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions on CloudFormation stack creation and the change set workflow.

-   **Main stack**: `cloudformation-template-validated.yml` (VPC, ECS, ALB, Lambda, Glue, S3).
-   **RDS stack**: `cloudformation-rds-aurora.yml` (Aurora Serverless v2, separate lifecycle).
-   **Deploy all**: `./deploy-changeset.sh --auto` (main) + `./scripts/deploy-rds.sh --auto` (database).

## CloudFormation Stacks

| Stack                     | Template                                | Purpose                                            |
| :------------------------ | :-------------------------------------- | :------------------------------------------------- |
| `ai-analyst-agent-project`| `cloudformation-template-validated.yml` | VPC, ECS, ALB, Lambda, Glue, S3, VPC endpoints     |
| `ai-rds-aurora`           | `cloudformation-rds-aurora.yml`         | Aurora Serverless v2 (MySQL), Secrets Manager credentials |

## CloudFormation Outputs

These outputs are consumed by the Jupyter notebook:

| Output Key             | Description                                     |
| :--------------------- | :---------------------------------------------- |
| `VpcId`                | Stack-managed VPC                               |
| `PrivateSubnetIds`     | Private subnets (ECS tasks, RDS)                |
| `ServiceSecurityGroupId`| ECS security group (used by RDS for ingress)    |
| `ProjectfilesBucketName`| Primary S3 bucket                               |
| `LibraryDatabaseName`  | Glue database for library data                  |
| `CarsDatabaseName`     | Glue database for cars data                     |
| `LibraryCrawlerName`   | Glue crawler for library data                   |
| `CarsCrawlerName`      | Glue crawler for cars data                      |
| `AthenaWorkgroupName`  | Athena workgroup for queries                    |
| `LoadBalancerUrl`      | Public HTTP URL for the Text-to-SQL API         |
| `EcrRepositoryUri`     | ECR URI for container images                    |
| `EcsClusterName`       | ECS cluster name                                |
| `EcsServiceName`       | ECS service name                                |
| `CrawlerTriggerLambdaArn`| Lambda that auto-triggers Glue Crawlers         |

## Data & Testing

-   Run `python run_smoke.py` to smoke-test data loading and normalization locally (no AWS calls).
-   Normalized cars CSV: `s3_cars_data_normalized.csv` (produced by normalization).
-   Unit tests: `PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v`

## Production Baseline

-   **Safer query execution defaults**:
    -   Read-only and allowlist SQL validation.
    -   Automatic `LIMIT` enforcement when missing.
    -   Max question length guard.
-   **Config hardening via typed settings**:
    -   `MAX_RESULT_ROWS`, `MAX_QUESTION_CHARS`, `LOG_LEVEL`.
-   **Operational CLI behavior**:
    -   Explicit non-zero exit codes on setup/catalog/query failures.
    -   Optional JSON output (`--json-output`) for automation.
-   **Container hardening**:
    -   Non-root runtime user.
    -   Python runtime safety defaults.
    -   Reduced Docker build context via `.dockerignore`.
-   **CI quality gate**:
    -   Compile checks, unit tests, and smoke test on push/PR.

## Production-Grade Setup

1.  **Set required runtime variables**:
    -   `GLUE_DB_NAME`
    -   `PROJECT_FILES_BUCKET`
    -   Optional hardening controls:
        -   `MAX_RESULT_ROWS` (default `200`)
        -   `MAX_QUESTION_CHARS` (default `1000`)
        -   `LOG_LEVEL` (`DEBUG|INFO|WARNING|ERROR|CRITICAL`)
        -   `ATHENA_WORKGROUP` (default `primary`; use `project-text-to-sql` when deployed via CloudFormation)
        -   `API_KEY` (optional HTTP API auth)
2.  **Run the full production gate locally before deployment**:
    -   `make prod-check`
3.  **Run the query CLI in automation-friendly mode when needed**:
    -   `PYTHONPATH=src python scripts/run_query.py --question "..." --json-output`
4.  **Build and run with Docker for consistent execution** (ECS needs `linux/amd64`; use `scripts/push_ecr.sh` on Apple Silicon):
    -   `DESIRED_COUNT=1 ./scripts/push_ecr.sh`
    -   Local run: `docker build --platform linux/amd64 -t data-architecture-ai .`
    -   API: `GET /health`, `POST /query` with `{"question": "..."}`
5.  **Deploy to ECS Fargate** (recommended production path):
    -   `./deploy-changeset.sh --auto` (deploys stack + builds image + starts service)
    -   Or step by step: `./deploy-changeset.sh` → execute change set → `DESIRED_COUNT=1 ./scripts/push_ecr.sh`
    -   See [DEPLOYMENT.md](DEPLOYMENT.md) for full ECS workflow.
6.  **Deploy Aurora Serverless v2** (optional, for RDS MySQL connector):
    -   `./scripts/deploy-rds.sh --auto`
    -   Paste the printed connection config into `config/connections/rds-mysql.yaml`.
    -   Load sample data: `PYTHONPATH=src python3 scripts/load_rds_data.py`.
7.  **Keep CI required on pull requests**:
    -   Workflow: `.github/workflows/ci.yml`
    -   Gates: compile, unit tests, smoke test.

## Notebook Environment Variable

Set `CFN_STACK_NAME` before launching Jupyter to avoid editing the placeholder in cell 4:

```bash
export CFN_STACK_NAME=ai-analyst-agent-project
```

## Streamlit UI

```bash
export GLUE_DB_NAME=project_library_db
export PROJECT_FILES_BUCKET=langchain-471613014056-eu-north-1
export ATHENA_WORKGROUP=project-text-to-sql
export ATHENA_USE_MANAGED_RESULTS=true
make ui
```

Opens `http://localhost:8501` — or set `API_URL` to use the deployed ECS API. See [DEPLOYMENT.md](DEPLOYMENT.md).

## Next Steps

-   Review `mda_text_to_sql_langchain_bedrock.ipynb` and set `CFN_STACK_NAME`.
-   Run `deploy-changeset.sh` to create a change set and review before deploying to AWS.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## License

This project is licensed under the MIT License - see the LICENSE.md file for details. (Placeholder - assuming MIT, will verify or adjust if a LICENSE.md exists.)
