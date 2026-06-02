Project: Data Architecture with Generative AI

Overview
- Notebook `mda_text_to_sql_langchain_bedrock.ipynb` demonstrates using LangChain + Bedrock to convert text to SQL and query data.
- Datasets: `s3_library_data.json` (NDJSON), `s3_cars_data.csv` (CSV).

Quick setup
1. Create a Python virtualenv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure AWS credentials (environment or AWS CLI).
3. Run `setup.sh` to perform optional staging actions (uploads are commented out).
4. Run production checks:
   - `make check` (syntax/compile gate)
   - `make test` (unit tests)
   - `make smoke` (local data smoke test)
   - `make prod-check` (all of the above)

Docker Desktop
- **Not required** for: running the Streamlit UI (`make ui`), tests, scripts, querying the deployed API, or CloudFormation operations.
- **Required only** for building and pushing container images (`./scripts/push_ecr.sh`, `make deploy-all`, `./deploy-changeset.sh --auto`).
- Once the image is in ECR and ECS is running, Docker Desktop can be closed.

Files
- `requirements.txt` — pinned project dependencies
- `scripts/streamlit_app.py` — Streamlit chat UI (`make ui`)
- `scripts/setup.sh` — helper script to install deps and optionally upload files
- `scripts/normalize_cars.py` — ingestion and normalization for `s3_cars_data.csv`
- `scripts/deploy-rds.sh` — deploy Aurora Serverless v2 (separate stack)
- `scripts/load_rds_data.py` — load sample data (library + cars) into Aurora via Secrets Manager credentials
- `schema/cars_schema.json`, `schema/library_schema.json` — JSON Schema draft-07 definitions
- `cloudformation-template-validated.yml` — main IaC template (VPC, S3, Glue, ECS, Lambda)
- `cloudformation-rds-aurora.yml` — Aurora Serverless v2 template (separate stack)
- `config/connections/*.yaml.template` — data source connection templates (Athena, Redshift, RDS, Snowflake, Databricks)
- `src/llm_sql/connectors/` — multi-connector framework
- `.env.template` — environment variable template
- `deploy-changeset.sh` — deployment script for main stack
- `DEPLOYMENT.md` — detailed deployment guide with examples

S3 Buckets
The CloudFormation template creates an S3 data bucket with a globally unique name:
- `langchain-471613014056-eu-north-1` — primary bucket (eu-north-1)

The bucket has versioning, AES-256 encryption, public access blocked, and a 30-day
lifecycle rule to expire Athena query results.

Deployment
- See [DEPLOYMENT.md](DEPLOYMENT.md) for CloudFormation stack creation and change set workflow.
- Main stack: `cloudformation-template-validated.yml` (VPC, ECS, Lambda, Glue, S3)
- RDS stack: `cloudformation-rds-aurora.yml` (Aurora Serverless v2, separate lifecycle)
- Deploy all: `./deploy-changeset.sh --auto` (main) + `./scripts/deploy-rds.sh --auto` (database)

CloudFormation Stacks

| Stack | Template | Purpose |
|-------|----------|---------|
| `ai-analyst-agent-project` | `cloudformation-template-validated.yml` | VPC, ECS, ALB, Lambda, Glue, S3, VPC endpoints |
| `ai-rds-aurora` | `cloudformation-rds-aurora.yml` | Aurora Serverless v2 (MySQL), Secrets Manager credentials |

CloudFormation Outputs (consumed by the notebook)
| Output Key | Description |
|---|---|
| `VpcId` | Stack-managed VPC |
| `PrivateSubnetIds` | Private subnets (ECS tasks, RDS) |
| `ServiceSecurityGroupId` | ECS security group (used by RDS for ingress) |
| `ProjectfilesBucketName` | Primary S3 bucket |
| `LibraryDatabaseName` | Glue database for library data |
| `CarsDatabaseName` | Glue database for cars data |
| `LibraryCrawlerName` | Glue crawler for library data |
| `CarsCrawlerName` | Glue crawler for cars data |
| `AthenaWorkgroupName` | Athena workgroup for queries |
| `LoadBalancerUrl` | Public HTTP URL for the Text-to-SQL API |
| `EcrRepositoryUri` | ECR URI for container images |
| `EcsClusterName` | ECS cluster name |
| `EcsServiceName` | ECS service name |
| `CrawlerTriggerLambdaArn` | Lambda that auto-triggers Glue Crawlers |

Data & Testing
- Run `python run_smoke.py` to smoke-test data loading and normalization locally (no AWS calls).
- Normalized cars CSV: `s3_cars_data_normalized.csv` (produced by normalization).
- Unit tests: `PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v`

Production baseline
- Safer query execution defaults:
  - read-only and allowlist SQL validation
  - automatic `LIMIT` enforcement when missing
  - max question length guard
- Config hardening via typed settings:
  - `MAX_RESULT_ROWS`, `MAX_QUESTION_CHARS`, `LOG_LEVEL`
- Operational CLI behavior:
  - explicit non-zero exit codes on setup/catalog/query failures
  - optional JSON output (`--json-output`) for automation
- Container hardening:
  - non-root runtime user
  - Python runtime safety defaults
  - reduced Docker build context via `.dockerignore`
- CI quality gate:
  - compile checks, unit tests, and smoke test on push/PR

Production-grade setup
1. Set required runtime variables:
   - `GLUE_DB_NAME`
   - `PROJECT_FILES_BUCKET`
   - Optional hardening controls:
     - `MAX_RESULT_ROWS` (default `200`)
     - `MAX_QUESTION_CHARS` (default `1000`)
     - `LOG_LEVEL` (`DEBUG|INFO|WARNING|ERROR|CRITICAL`)
     - `ATHENA_WORKGROUP` (default `primary`; use `project-text-to-sql` when deployed via CloudFormation)
     - `API_KEY` (optional HTTP API auth)
2. Run the full production gate locally before deployment:
   - `make prod-check`
3. Run the query CLI in automation-friendly mode when needed:
   - `PYTHONPATH=src python scripts/run_query.py --question "..." --json-output`
4. Build and run with Docker for consistent execution (ECS needs `linux/amd64`; use `scripts/push_ecr.sh` on Apple Silicon):
   - `DESIRED_COUNT=1 ./scripts/push_ecr.sh`
   - Local run: `docker build --platform linux/amd64 -t data-architecture-ai .`
   - API: `GET /health`, `POST /query` with `{"question": "..."}`
5. Deploy to ECS Fargate (recommended production path):
   - `./deploy-changeset.sh --auto` (deploys stack + builds image + starts service)
   - Or step by step: `./deploy-changeset.sh` → execute change set → `DESIRED_COUNT=1 ./scripts/push_ecr.sh`
   - See [DEPLOYMENT.md](DEPLOYMENT.md) for full ECS workflow
6. Deploy Aurora Serverless v2 (optional, for RDS MySQL connector):
   - `./scripts/deploy-rds.sh --auto`
   - Paste the printed connection config into `config/connections/rds-mysql.yaml`
   - Load sample data: `PYTHONPATH=src python3 scripts/load_rds_data.py`
7. Keep CI required on pull requests:
   - Workflow: `.github/workflows/ci.yml`
   - Gates: compile, unit tests, smoke test

Notebook environment variable
Set `CFN_STACK_NAME` before launching Jupyter to avoid editing the placeholder in cell 4:
```bash
export CFN_STACK_NAME=ai-analyst-agent-project
```

Streamlit UI
```bash
export GLUE_DB_NAME=project_library_db
export PROJECT_FILES_BUCKET=langchain-471613014056-eu-north-1
export ATHENA_WORKGROUP=project-text-to-sql
export ATHENA_USE_MANAGED_RESULTS=true
make ui
```
Opens http://localhost:8501 — or set `API_URL` to use the deployed ECS API. See [DEPLOYMENT.md](DEPLOYMENT.md).

Next steps
- Review `mda_text_to_sql_langchain_bedrock.ipynb` and set `CFN_STACK_NAME`.
- Run `deploy-changeset.sh` to create a change set and review before deploying to AWS.
