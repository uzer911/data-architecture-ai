# Deploying to Your AWS Account

**Account ID:** `471613014056`  
**Region:** `eu-north-1`  
**S3 Bucket:** `langchain-471613014056-eu-north-1` (created automatically by the deploy script)

---

## Prerequisites

- AWS CLI installed and configured (`aws configure`)
- Docker installed (for building the container image)
- Git + GitHub repo with this code

---

## Step 1 — Configure AWS CLI for your account

```bash
aws configure
# AWS Access Key ID: <your key>
# AWS Secret Access Key: <your secret>
# Default region name: eu-north-1
# Default output format: json
```

Verify you're in the right account:
```bash
aws sts get-caller-identity
# Should show: "Account": "471613014056"
```

---

## Step 2 — Enable Bedrock model access

The app uses **Amazon Nova** models. You must enable them in the console first:

1. Open [AWS Console → Bedrock → Model access](https://eu-north-1.console.aws.amazon.com/bedrock/home?region=eu-north-1#/modelaccess)
2. Click **Manage model access**
3. Enable: **Amazon Nova Micro**, **Amazon Nova Lite**, **Amazon Nova Pro**
4. Click **Save changes** (takes ~1 minute to activate)

---

## Step 3 — Create the GitHub Actions deploy role (one-time)

This creates an IAM role that GitHub Actions uses to deploy — no long-lived keys needed.

```bash
# Deploy the OIDC role stack
aws cloudformation deploy \
  --template-file cloudformation-github-oidc-role.yml \
  --stack-name github-actions-ai-agent-role \
  --region eu-north-1 \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    GitHubOrg=YOUR_GITHUB_USERNAME \
    GitHubRepo=YOUR_REPO_NAME
```

> Replace `YOUR_GITHUB_USERNAME` and `YOUR_REPO_NAME` with your actual GitHub username and repo name.

Get the role ARN:
```bash
aws cloudformation describe-stacks \
  --stack-name github-actions-ai-agent-role \
  --region eu-north-1 \
  --query "Stacks[0].Outputs[?OutputKey=='DeployRoleArn'].OutputValue" \
  --output text
```

Add it as a GitHub secret:
1. Go to your GitHub repo → **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Name: `AWS_DEPLOY_ROLE_ARN`
4. Value: the ARN from the command above (e.g. `arn:aws:iam::471613014056:role/github-actions-ai-agent-deploy`)

---

## Step 4 — Copy .env.template to .env

```bash
cp .env.template .env
```

The `.env` file is already pre-filled with your account ID. Optionally change `APP_PASSWORD`.

---

## Step 5 — Deploy the main stack

This creates everything: VPC, S3 bucket, Glue, Athena, ECR, ECS, Lambda, ALB.

```bash
# Full auto deploy (recommended for first deploy)
./deploy-changeset.sh --auto
```

What `--auto` does:
1. Detects which resources already exist (skips re-creating them)
2. Creates a CloudFormation change set and executes it
3. Builds and pushes the Docker image to ECR
4. Runs the Glue crawlers to populate the table catalog
5. Configures the S3 → Lambda notification
6. Prints the API URL when done

> First deploy takes ~10 minutes (VPC endpoints + ECS service startup).

---

## Step 6 — Upload sample data to S3

```bash
# Upload library data
aws s3 cp data/s3_library_data.json \
  s3://langchain-471613014056-eu-north-1/library-data/s3_library_data.json \
  --region eu-north-1

# Upload cars data
aws s3 cp data/s3_cars_data_normalized.csv \
  s3://langchain-471613014056-eu-north-1/cars-data/s3_cars_data_normalized.csv \
  --region eu-north-1
```

Uploading triggers the Lambda which auto-creates Glue crawlers and catalogs the data.

---

## Step 7 — Test the API

```bash
# Get the API URL
ALB_URL=$(aws cloudformation describe-stacks \
  --stack-name ai-analyst-agent-project \
  --region eu-north-1 \
  --query "Stacks[0].Outputs[?OutputKey=='LoadBalancerUrl'].OutputValue" \
  --output text)

echo "API URL: $ALB_URL"

# Health check
curl $ALB_URL/health

# Ask a question
curl -X POST $ALB_URL/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How many books are in the library?"}'
```

---

## Step 8 — CI/CD via GitHub Actions

Once the GitHub secret `AWS_DEPLOY_ROLE_ARN` is set, every push to `main` will:
1. Run tests
2. Build and push the Docker image to ECR
3. Force a new ECS deployment

---

## Resource Summary

| Resource | Name |
|----------|------|
| CloudFormation stack | `ai-analyst-agent-project` |
| S3 bucket | `langchain-471613014056-eu-north-1` |
| ECR repository | `471613014056.dkr.ecr.eu-north-1.amazonaws.com/data-architecture-ai` |
| ECS cluster | `data-architecture-ai` |
| ECS service | `data-architecture-ai` |
| Athena workgroup | `project-text-to-sql` |
| Glue databases | `project_library_db`, `project_cars_db` |
| Bedrock model | `eu.amazon.nova-micro-v1:0` |
| GitHub deploy role | `arn:aws:iam::471613014056:role/github-actions-ai-agent-deploy` |

---

## Teardown

```bash
# Delete main stack (keeps S3 bucket and log group — DeletionPolicy: Retain)
aws cloudformation delete-stack \
  --stack-name ai-analyst-agent-project \
  --region eu-north-1

# Empty and delete the S3 bucket manually if needed
aws s3 rm s3://langchain-471613014056-eu-north-1 --recursive
aws s3 rb s3://langchain-471613014056-eu-north-1
```
