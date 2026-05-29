# CloudFormation Deployment Guide

This guide shows how to deploy the `cloudformation-template-validated.yml` template using AWS CloudFormation change sets.

## Prerequisites

- AWS CLI installed and configured with credentials
- IAM permissions to create CloudFormation stacks, IAM roles, and Lambda functions
- A deployed AWS region

## Quick Start

### Option 1: Using the deployment script (recommended)

```bash
chmod +x deploy-changeset.sh
./deploy-changeset.sh "my-pool-id" "eu-north-1,eu-central-1" "rate(15 minutes)"
```

**Parameters:**
- `my-pool-id`: AI Project Pool ID (required; provide your actual pool ID)
- `eu-north-1,eu-central-1`: Comma-separated list of regions (optional; defaults to current AWS_REGION)
- `rate(15 minutes)`: Monitoring Lambda schedule expression (optional; defaults to `rate(15 minutes)`)

**S3 Buckets created:**
- `langchain-<account-id>-eu-north-1` — primary data bucket
- `langchain-<account-id>-eu-central-1` — secondary data bucket

### Option 2: Manual AWS CLI commands

#### 1. Set environment variables
```bash
export AWS_REGION="eu-north-1"
export STACK_NAME="gbl-ai-project-monitoring-stack"
export AI_POOL_ID="my-pool-id"
export AI_REGIONS="eu-north-1"
export MONITORING_SCHEDULE="rate(15 minutes)"
```

#### 2. Validate template
```bash
aws cloudformation validate-template \
  --template-body file://cloudformation-template-validated.yml \
  --region "$AWS_REGION"
```

#### 3. Create a change set
```bash
CHANGE_SET_NAME="${STACK_NAME}-changeset-$(date +%s)"

aws cloudformation create-change-set \
  --stack-name "$STACK_NAME" \
  --change-set-name "$CHANGE_SET_NAME" \
  --template-body file://cloudformation-template-validated.yml \
  --parameters \
    ParameterKey=AiProjectPoolId,ParameterValue="${AI_POOL_ID}" \
    ParameterKey=AiProjectRegions,ParameterValue="${AI_REGIONS}" \
    ParameterKey=MonitoringScheduleExpression,ParameterValue="${MONITORING_SCHEDULE}" \
  --capabilities CAPABILITY_IAM \
  --region "$AWS_REGION" \
  --tags \
    "Key=DeployedBy,Value=$(aws iam get-user --query 'User.UserName' --output text)" \
    "Key=Environment,Value=production"
```

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

### AiProjectPoolId
- **Type**: String
- **Description**: Identifier for the AI Project pool your monitoring Lambda will target
- **Example**: `my-ai-projects-pool`, `prod-pool-1`

### AiProjectRegions
- **Type**: String (comma-separated)
- **Description**: AWS regions where the monitoring function operates
- **Example**: `eu-north-1`, `eu-north-1,eu-central-1`

### MonitoringScheduleExpression
- **Type**: String
- **Description**: EventBridge schedule expression used to trigger the monitoring Lambda
- **Example**: `rate(15 minutes)`, `rate(1 hour)`, `cron(0/30 * * * ? *)`

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

### Change set shows no changes
- If the change set has no changes, the stack either already exists with identical parameters, or there's a syntax issue. Review the template.

### Insufficient permissions
- Ensure your IAM user has `cloudformation:*`, `iam:*`, `lambda:*`, `logs:*`, and `events:*` permissions.

### Template format error
- Validate the YAML syntax: `aws cloudformation validate-template --template-body file://cloudformation-template-validated.yml`

### Stack creation timeout
- If the stack creation takes too long, check CloudFormation events for errors: `aws cloudformation describe-stack-events --stack-name "$STACK_NAME" --region "$AWS_REGION"`

## References

- [AWS CloudFormation User Guide](https://docs.aws.amazon.com/cloudformation/)
- [Change Sets Documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html)
- [IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
