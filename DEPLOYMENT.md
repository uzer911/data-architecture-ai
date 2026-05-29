# CloudFormation Deployment Guide

This guide shows how to deploy the `cloudformation-template-validated.yml` template using AWS CloudFormation change sets.

## Prerequisites

- AWS CLI installed and configured with credentials
- IAM permissions to create CloudFormation stacks, IAM roles, S3 resources, and Glue resources
- A deployed AWS region

## Quick Start

### Option 1: Using the deployment script (recommended)

```bash
chmod +x deploy-changeset.sh
./deploy-changeset.sh
```

**S3 Buckets created:**
- `langchain-<account-id>-eu-north-1` — primary data bucket
- `langchain-<account-id>-eu-central-1` — secondary data bucket

### Option 2: Manual AWS CLI commands

#### 1. Set environment variables
```bash
export AWS_REGION="eu-north-1"
export STACK_NAME="gbl-ai-project-monitoring-stack"
```

#### 2. Validate template
```bash
aws cloudformation validate-template \
  --template-body file://cloudformation-template-validated.yml \
  --region "$AWS_REGION"
```

#### 3. Resolve VPC parameters and create a change set

On the **first deploy** the stack does not exist yet. You must pass `--change-set-type CREATE`.
Use JSON for `--parameters` so comma-separated subnet IDs are not split by the CLI.

```bash
CHANGE_SET_NAME="${STACK_NAME}-changeset-$(date +%s)"

eval "$(bash scripts/get_vpc_params.sh | grep -E '^(VPC_ID|PUBLIC_SUBNET_IDS)=')"

CFN_PARAMETERS=$(cat <<EOF
[
  {"ParameterKey": "VpcId", "ParameterValue": "${VPC_ID}"},
  {"ParameterKey": "PublicSubnetIds", "ParameterValue": "${PUBLIC_SUBNET_IDS}"},
  {"ParameterKey": "DesiredCount", "ParameterValue": "0"}
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
The stack uses only the `Environment` template parameter (default: `production`), so no required parameters are needed for the deployment script path above.

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
  --stack-name gbl-ai-project-monitoring-stack \
  --region eu-north-1

aws cloudformation wait stack-delete-complete \
  --stack-name gbl-ai-project-monitoring-stack \
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

Or attach the missing actions to role `gbl-ai-project-monitoring-stack-EcsTaskRole-*` in IAM Console:
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
export PROJECT_FILES_BUCKET=langchain-<account-id>-eu-north-1
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
| ECR repository | `data-architecture-ai` container images |
| ECS cluster + Fargate service | Runs the API container |
| Application Load Balancer | Public HTTP endpoint on port 80 |
| IAM task role | Bedrock, Glue, Athena, S3 access (scoped) |
| Athena workgroup | `project-text-to-sql` with 1 GB scan limit |

### Deploy workflow

#### 1. Deploy infrastructure (tasks start at 0 until image exists)

```bash
./deploy-changeset.sh
# Review, then execute the change set
aws cloudformation execute-change-set \
  --stack-name gbl-ai-project-monitoring-stack \
  --change-set-name <changeset-name> \
  --region eu-north-1
```

#### 2. Build, push, and start the API

```bash
chmod +x scripts/push_ecr.sh scripts/get_vpc_params.sh
DESIRED_COUNT=1 ./scripts/push_ecr.sh
```

#### 3. Get the API URL

```bash
aws cloudformation describe-stacks \
  --stack-name gbl-ai-project-monitoring-stack \
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
| `VpcId` | (from script) | VPC for ALB and Fargate |
| `PublicSubnetIds` | (from script) | Public subnets (Fargate uses assignPublicIp) |
| `DesiredCount` | `0` | Set to `1` after pushing the container image |
| `ContainerImage` | ECR `:latest` | Override with a specific image URI |
| `ApiKey` | empty | Optional `X-Api-Key` header value |
| `AlbIngressCidr` | `0.0.0.0/0` | Restrict in production |
| `GlueDatabaseForQueries` | `project_library_db` | Primary Glue DB for Athena connection |

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
