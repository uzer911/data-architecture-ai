# CloudFormation Deployment Guide

This guide shows how to deploy the `cloudformation-template-validated.yml` template using AWS CloudFormation change sets.

## Prerequisites

- AWS CLI installed and configured with credentials
- IAM permissions to create CloudFormation stacks, IAM roles, EC2 (VPC/subnets/endpoints), S3, Glue, Athena, ECS, ECR resources
- A deployed AWS region (default: `eu-north-1`)
- **Docker Desktop** — required only for building/pushing container images (see below)

### Docker Desktop Requirements

Docker Desktop is **only needed** when building and pushing container images to ECR:

| Task | Docker Desktop Required? |
|------|:------------------------:|

| Building and pushing container images (`./scripts/push_ecr.sh`) | ✅ Yes |
| Full auto deploy (`./deploy-changeset.sh --auto`) | ✅ Yes |
| `make deploy-all` | ✅ Yes |

**In short:** Once the image is in ECR and the ECS service is running, Docker Desktop can be closed. You only need it when rebuilding the container.

> **No VPC required beforehand.** The stack creates its own VPC (10.0.0.0/16), public subnets
> (ALB), private subnets (ECS tasks), and all VPC endpoints. No NAT gateway is used — AWS
> service traffic (ECR, Bedrock, Athena, Glue, Secrets Manager, S3, CloudWatch Logs) flows
> through VPC interface/gateway endpoints at no NAT cost.

## Quick Start

### Option 1: Fully automated (one command)

Deploys the stack, builds the Docker image, pushes to ECR, and starts the ECS service:

```bash
chmod +x deploy-changeset.sh scripts/push_ecr.sh
./deploy-changeset.sh --auto
```

Or using make:

```bash
make deploy-all
```

This does everything end-to-end: validate → create stack → wait → build image → push to ECR → start service → print API URL.

### Option 2: Review first, then deploy

```bash
./deploy-changeset.sh        # Shows what will change (review mode)
./deploy-changeset.sh --auto # Execute after reviewing
```

Or step by step with make:

```bash
make deploy      # Review mode — shows change set summary
make deploy-all  # Full auto — deploys everything
```

**S3 Buckets created:**
- `langchain-<account-id>-eu-north-1` — primary data bucket
- `langchain-<account-id>-eu-central-1` — secondary data bucket

### Option 2: Manual AWS CLI commands

#### 1. Set environment variables
```bash
export AWS_REGION="eu-north-1"
export STACK_NAME="cgs-ai-analyst-agent-project"
```

#### 2. Validate template
```bash
aws cloudformation validate-template \
  --template-body file://cloudformation-template-validated.yml \
  --region "$AWS_REGION"
```

#### 3. Create a change set

No VPC parameters needed — the stack manages its own network.

```bash
CHANGE_SET_NAME="${STACK_NAME}-changeset-$(date +%s)"

eval "$(bash scripts/detect_existing_resources.sh | grep -E '^[A-Z_]+=')"

CFN_PARAMETERS=$(cat <<EOF
[
  {"ParameterKey": "DesiredCount",            "ParameterValue": "0"},
  {"ParameterKey": "PrimaryDataBucketName",   "ParameterValue": "${PRIMARY_DATA_BUCKET_NAME}"},
  {"ParameterKey": "CentralDataBucketName",   "ParameterValue": "${CENTRAL_DATA_BUCKET_NAME}"},
  {"ParameterKey": "CreatePrimaryDataBucket", "ParameterValue": "${CREATE_PRIMARY_DATA_BUCKET}"},
  {"ParameterKey": "CreateCentralDataBucket", "ParameterValue": "${CREATE_CENTRAL_DATA_BUCKET}"}
]
EOF
)

# First deploy: CREATE. Later updates: UPDATE.
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
  CHANGE_SET_TYPE="UPDATE"
else
  CHANGE_SET_TYPE="CREATE"
fi

aws cloudformation create-change-set \
  --stack-name "$STACK_NAME" \
  --change-set-name "$CHANGE_SET_NAME" \
  --change-set-type "$CHANGE_SET_TYPE" \
  --template-body file://cloudformation-template-validated.yml \
  --capabilities CAPABILITY_IAM \
  --region "$AWS_REGION" \
  --parameters "$CFN_PARAMETERS" \
  --tags \
    "Key=DeployedBy,Value=$(aws iam get-user --query 'User.UserName' --output text)" \
    "Key=Environment,Value=production"
```

> **Troubleshooting:** If you see `Stack [...] does not exist`, add `--change-set-type CREATE`.
> Or use `./deploy-changeset.sh`, which sets this automatically.

#### 4. Review the change set
```bash
aws cloudformation describe-change-set \
  --stack-name "$STACK_NAME" \
  --change-set-name "$CHANGE_SET_NAME" \
  --region "$AWS_REGION" \
  --output table
```

#### 5. Execute the change set
```bash
aws cloudformation execute-change-set \
  --stack-name "$STACK_NAME" \
  --change-set-name "$CHANGE_SET_NAME" \
  --region "$AWS_REGION"
```

#### 6. Monitor stack creation
```bash
aws cloudformation wait stack-create-complete \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION"
```

#### 7. View stack outputs
```bash
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs'
```

## Understanding Change Sets

A **change set** is a preview of changes that will be applied to your CloudFormation stack. Benefits:

- **Review before applying**: See exactly what will be created, modified, or deleted
- **Safe deployments**: Catch unintended changes before they're applied
- **Audit trail**: Track who deployed what and when (via tags)
- **Rollback capability**: Revert if needed

## Parameters Explained
The stack creates its own VPC and subnets — no `VpcId` or `PublicSubnetIds` parameters are needed. The deployment script auto-detects existing data-layer resources (S3 buckets, Glue DBs, Athena workgroup, CloudWatch log group) and passes the appropriate `Create*` flags.

## Capabilities

This template requires **CAPABILITY_IAM** because it creates IAM roles and policies. Pass this via `--capabilities CAPABILITY_IAM`.

## Tagging for Audit and Governance

The deployment script automatically tags the stack with:

- `DeployedBy`: IAM user who deployed it (auto-detected)
- `DeploymentDate`: UTC timestamp of deployment
- `Environment`: Tag to indicate environment (prod/dev/staging)

Add custom tags in the script or via AWS CLI:
```bash
--tags "Key=CostCenter,Value=engineering" "Key=Owner,Value=team@example.com"
```

## Cleanup

To delete the stack and all resources:

```bash
aws cloudformation delete-stack \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION"

# Wait for deletion
aws cloudformation wait stack-delete-complete \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION"
```

## Troubleshooting

### Resource name conflict (bucket, Athena workgroup, Glue DB already exists)

If stack creation fails with errors like:

```text
Resource of type 'AWS::S3::Bucket' with identifier 'langchain-...' already exists.
Resource of type 'AWS::Athena::WorkGroup' with identifier 'project-text-to-sql' already exists.
Resource of type 'AWS::Logs::LogGroup' with identifier '/ecs/data-architecture-ai' already exists.
```

Those resources were created outside this stack (or by a previous failed deploy). The deploy script now **detects and reuses** them automatically:

```bash
bash scripts/detect_existing_resources.sh   # preview what will be reused vs created
./deploy-changeset.sh                       # passes Create*=false for existing resources
```

You should **not** see `ProjectDataBucketNorth` or `ProjectAthenaWorkgroup` in the change set summary when reuse is working.

### Stuck stack (`REVIEW_IN_PROGRESS` or `ROLLBACK_COMPLETE`)

Delete the failed stack, then redeploy:

```bash
aws cloudformation delete-stack \
  --stack-name cgs-ai-analyst-agent-project \
  --region eu-north-1

aws cloudformation wait stack-delete-complete \
  --stack-name cgs-ai-analyst-agent-project \
  --region eu-north-1

./deploy-changeset.sh
```

### CannotPullContainerError: platform linux/amd64

ECS Fargate requires **linux/amd64** images. If you built on an **Apple Silicon Mac** without cross-compilation, the image in ECR is **arm64** only.

Rebuild and push with the project script (it builds for amd64 automatically):

```bash
DESIRED_COUNT=1 ./scripts/push_ecr.sh
```

Or manually:

```bash
docker buildx build --platform linux/amd64 -t <ecr-uri>:latest --push .
```

### Athena: ManagedQueryResultsConfiguration and ResultConfiguration

If you see:

```text
ManagedQueryResultsConfiguration and ResultConfiguration cannot be set together
```

Your Athena workgroup (`project-text-to-sql`) uses **managed query results**. The app now detects this and does not send an S3 staging path. **Redeploy the ECS image** after pulling the latest code:

```bash
DESIRED_COUNT=1 ./scripts/push_ecr.sh
```

For local Streamlit/API testing, restart the app after `git pull`.

### API error 500: Bedrock inference profile required

If logs show:

```text
Invocation of model ID amazon.nova-micro-v1:0 with on-demand throughput isn't supported.
Retry your request with the ID or ARN of an inference profile
```

Set:

```bash
export BEDROCK_MODEL=eu.amazon.nova-micro-v1:0
```

Redeploy ECS (`./scripts/push_ecr.sh`) or restart local Streamlit. The app auto-maps legacy model IDs to `eu.amazon.nova-micro-v1:0` in EU regions.

### Athena AccessDenied: ListTableMetadata

LangChain's SQL layer calls `athena:ListTableMetadata` when connecting. The ECS task role must include metadata permissions (added in the template).

Update the stack, then restart ECS tasks:

```bash
./deploy-changeset.sh
# execute the change set, wait for UPDATE_COMPLETE

aws ecs update-service \
  --cluster data-architecture-ai \
  --service data-architecture-ai \
  --force-new-deployment \
  --region eu-north-1
```

Or attach the missing actions to role `cgs-ai-analyst-agent-project-EcsTaskRole-*` in IAM Console:
`athena:ListTableMetadata`, `athena:GetTableMetadata`, `athena:ListDatabases`, `athena:GetDatabase`, `athena:GetDataCatalog` on `arn:aws:athena:REGION:ACCOUNT:datacatalog/*` and `database/*`.

### Change set shows no changes
- If the change set has no changes, the stack either already exists with identical parameters, or there's a syntax issue. Review the template.

### Insufficient permissions
- Ensure your IAM user has `cloudformation:*`, `iam:*`, `s3:*`, and `glue:*` permissions.

### Template format error
- Validate the YAML syntax: `aws cloudformation validate-template --template-body file://cloudformation-template-validated.yml`

### Stack creation timeout
- If the stack creation takes too long, check CloudFormation events for errors: `aws cloudformation describe-stack-events --stack-name "$STACK_NAME" --region "$AWS_REGION"`

## Streamlit UI (chat)

Browser interface for asking questions (local AWS or remote ECS API).

### Local mode (your laptop uses Bedrock + Athena directly)

```bash
export GLUE_DB_NAME=project_library_db
export PROJECT_FILES_BUCKET=langchain-015337708931-eu-north-1
export ATHENA_WORKGROUP=project-text-to-sql
export ATHENA_USE_MANAGED_RESULTS=true
pip install -r requirements.txt
make ui
# or: PYTHONPATH=src streamlit run scripts/streamlit_app.py
```

Opens at **http://localhost:8501**

### Remote mode (calls ECS API behind the load balancer)

```bash
export API_URL=http://<your-alb-dns>
export API_KEY=your-key   # only if you set ApiKey in CloudFormation
streamlit run scripts/streamlit_app.py
```

## ECS Fargate API (production serving layer)

The stack provisions an **ECS Fargate** service behind an **Application Load Balancer** running the Text-to-SQL HTTP API.

### Resources added

| Resource | Purpose |
|----------|---------|
| VPC + subnets | Stack-managed network (public for ALB, private for ECS) |
| Internet Gateway | Outbound internet for ALB only |
| VPC Interface Endpoints | ECR, Bedrock, Athena, Glue, Secrets Manager, CloudWatch Logs |
| S3 Gateway Endpoint | Free S3 access from private subnets (no NAT) |
| ECR repository | `data-architecture-ai` container images |
| ECS cluster + Fargate service | Runs the API in private subnets |
| Application Load Balancer | Public HTTP endpoint on port 80 (public subnets) |
| IAM task role | Bedrock, Glue, Athena, S3, Secrets Manager access (scoped) |
| Athena workgroup | `project-text-to-sql` with 1 GB scan limit |

### Deploy workflow

#### Automated (recommended)

```bash
./deploy-changeset.sh --auto
```

This single command: validates template → deploys stack → waits for completion → builds Docker image → pushes to ECR → starts ECS service → prints the API URL.

#### Manual (step by step)

##### 1. Deploy infrastructure

```bash
./deploy-changeset.sh          # Review what will change
./deploy-changeset.sh --auto   # Or go straight to full deploy
```

##### 2. Build, push, and start the API

```bash
chmod +x scripts/push_ecr.sh
DESIRED_COUNT=1 ./scripts/push_ecr.sh
```

##### 3. Get the API URL

```bash
aws cloudformation describe-stacks \
  --stack-name cgs-ai-analyst-agent-project \
  --region eu-north-1 \
  --query "Stacks[0].Outputs[?OutputKey=='LoadBalancerUrl'].OutputValue" \
  --output text
```

#### 4. Call the API

```bash
ALB_URL="http://your-alb-dns.amazonaws.com"

curl "${ALB_URL}/health"

curl -X POST "${ALB_URL}/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "How many books are in the library?"}'
```

If you set the `ApiKey` stack parameter, include the header:

```bash
curl -X POST "${ALB_URL}/query" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: your-secret-key" \
  -d '{"question": "How many books are in the library?"}'
```

### Stack parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `VpcCidr` | `10.0.0.0/16` | CIDR for the stack-managed VPC |
| `PublicSubnet1Cidr` | `10.0.0.0/24` | Public subnet 1 (ALB) — AZ a |
| `PublicSubnet2Cidr` | `10.0.1.0/24` | Public subnet 2 (ALB) — AZ b |
| `PrivateSubnet1Cidr` | `10.0.2.0/24` | Private subnet 1 (ECS tasks) — AZ a |
| `PrivateSubnet2Cidr` | `10.0.3.0/24` | Private subnet 2 (ECS tasks) — AZ b |
| `DesiredCount` | `0` | Set to `1` after pushing the container image |
| `ContainerImage` | ECR `:latest` | Override with a specific image URI |
| `ApiKey` | empty | Optional `X-Api-Key` header value |
| `AlbIngressCidr` | `0.0.0.0/0` | Restrict in production |
| `CreateAppLogGroup` | `true` | Set `false` if the CloudWatch log group `/ecs/data-architecture-ai` already exists |
| `GlueDatabaseForQueries` | `project_library_db` | Primary Glue DB for Athena connection |

> **No VpcId or PublicSubnetIds parameters.** The stack creates and owns the entire network.
> ECS tasks run in private subnets with `AssignPublicIp: DISABLED`. All AWS API calls
> (ECR, Bedrock, Athena, Glue, Secrets Manager, CloudWatch Logs) use VPC interface endpoints.
> S3 uses a free Gateway endpoint. No NAT gateway is provisioned.

### Local API development

```bash
export GLUE_DB_NAME=project_library_db
export PROJECT_FILES_BUCKET=langchain-<account-id>-eu-north-1
export ATHENA_WORKGROUP=project-text-to-sql
export ATHENA_USE_MANAGED_RESULTS=true
PYTHONPATH=src python scripts/serve.py
# curl http://localhost:8080/health
```

### CLI mode (Docker)

The default Docker entrypoint runs the HTTP API. For one-off CLI queries:

```bash
docker run --rm \
  -e GLUE_DB_NAME=project_library_db \
  -e PROJECT_FILES_BUCKET=langchain-<account-id>-eu-north-1 \
  --entrypoint python \
  data-architecture-ai /app/scripts/run_query.py --question "How many books?"
```

## References

- [AWS CloudFormation User Guide](https://docs.aws.amazon.com/cloudformation/)
- [Change Sets Documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html)
- [IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)

## CI/CD — Automated Docker Build & Deploy to Fargate

The `.github/workflows/deploy.yml` workflow automates the full build-push-deploy cycle.

### Trigger

- **Automatic:** every push to `main` (after tests pass)
- **Manual:** click "Run workflow" in GitHub Actions (optionally set `desired_count`)

### What it does

1. Runs compile check + unit tests + smoke test (gate)
2. Builds `linux/amd64` Docker image
3. Pushes to ECR with both `:latest` and `:<commit-sha>` tags
4. Forces ECS service redeployment with `desired_count=1`
5. Waits for service stability
6. Prints the ALB URL

### Setup required

1. Create an IAM role for GitHub Actions with permissions for ECR, ECS, and CloudFormation read:
   ```
   ecr:GetAuthorizationToken, ecr:BatchCheckLayerAvailability, ecr:PutImage, ...
   ecs:UpdateService, ecs:DescribeServices
   cloudformation:DescribeStacks
   ```
2. Store the role ARN as a GitHub secret: `AWS_DEPLOY_ROLE_ARN`
3. Enable OIDC trust between GitHub and your AWS account ([docs](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services))

## Lambda — Auto-Trigger Glue Crawlers on S3 Upload

A Lambda function fires on any file upload to the primary S3 bucket. It:

1. Extracts the top-level folder (prefix) from the S3 key
2. If no Glue database exists for that prefix → creates one (`project_{prefix}_db`)
3. If no Glue crawler exists → creates one (`project-{prefix}-crawler`)
4. Starts the crawler → Glue discovers the schema → tables appear in Athena

### Example

Upload `s3://your-bucket/sales-data/2024.csv`:
- Creates DB `project_sales_data_db`
- Creates crawler `project-sales-data-crawler`
- Crawler runs → creates table `sales_data` in Athena

### For pre-existing buckets

If your S3 bucket existed before the stack (common case), run:

```bash
./scripts/configure_s3_notification.sh
```

This wires the S3 event notification to the Lambda. For buckets created by the stack (`CreatePrimaryDataBucket=true`), the notification is configured automatically.

## Multi-Connector Framework

The app supports multiple data sources beyond Athena. Each connector is configured via a YAML file in `config/connections/`.

### Supported connectors

| Type | Package required | Config template |
|------|-----------------|-----------------|
| Athena | (built-in) | `athena.yaml.template` |
| Redshift | `redshift-connector` | `redshift.yaml.template` |
| RDS PostgreSQL | `psycopg2-binary` | `rds-postgres.yaml.template` |
| RDS MySQL | `pymysql` | (use rds-postgres template, change type to `rds_mysql`) |
| Snowflake | `snowflake-connector-python` | `snowflake.yaml.template` |
| Databricks | `databricks-sql-connector` | `databricks.yaml.template` |

### Adding a data source

```bash
# 1. Copy the template
cp config/connections/redshift.yaml.template config/connections/redshift.yaml

# 2. Edit with your values (credentials go in Secrets Manager, not the file)
vim config/connections/redshift.yaml

# 3. Install the connector package
pip install redshift-connector

# 4. Restart the UI — the new source appears in the sidebar dropdown
make ui
```

### Credentials

Never put passwords in YAML files. Use `user_from_secret` or `token_from_secret` to reference an AWS Secrets Manager secret:

```yaml
settings:
  host: my-cluster.xxxx.redshift.amazonaws.com
  user_from_secret: redshift/prod-creds  # Secret with {"username":"...", "password":"..."}
```

## Aurora Serverless v2 (RDS MySQL)

A separate CloudFormation stack deploys Aurora Serverless v2 in the same VPC. It scales to near-zero when idle (0.5 ACU minimum) — cost-efficient for training and dev.

### Deploy

```bash
./scripts/deploy-rds.sh --auto
```

This takes 5-10 minutes. After completion, it prints the connection config.

### Connect the app

Paste the printed output into `config/connections/rds-mysql.yaml`:

```yaml
name: RDS MySQL
type: rds_mysql
enabled: true
settings:
  host: <cluster-endpoint-printed-by-script>
  port: 3306
  database: analyst_db
  user_from_secret: cgs-ai-rds-aurora/aurora-credentials
  region: eu-north-1
```

### Load sample data

After the Aurora stack is deployed and the connection config is in place, load the sample datasets (library + cars) into the database:

```bash
PYTHONPATH=src python3 scripts/load_rds_data.py
```

The script fetches credentials from Secrets Manager, creates the `library` and `cars` tables, and bulk-inserts data from `data/s3_library_data.json` and `data/s3_cars_data.csv`.

Override defaults with environment variables if needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `RDS_SECRET` | `cgs-ai-rds-aurora/aurora-credentials` | Secrets Manager secret name |
| `RDS_DATABASE` | `analyst_db` | Target database |
| `AWS_REGION` | `eu-north-1` | Region for Secrets Manager calls |

### Architecture

- **Template:** `cloudformation-rds-aurora.yml`
- **Stack name:** `cgs-ai-rds-aurora`
- **Engine:** Aurora MySQL 8.0 (Serverless v2)
- **Scaling:** 0.5–4 ACU (configurable via parameters)
- **Network:** Same VPC + private subnets as the main stack
- **Security:** Only ECS tasks can connect (port 3306 restricted to `ServiceSecurityGroup`)
- **Credentials:** Auto-generated, stored in Secrets Manager, rotatable
- **Deletion:** Takes a snapshot before deletion (`DeletionPolicy: Snapshot`)

### Delete

```bash
aws cloudformation delete-stack \
  --stack-name cgs-ai-rds-aurora \
  --region eu-north-1
```

A final snapshot is created automatically before deletion.
