#!/usr/bin/env bash
# CloudFormation deployment script: create change set and deploy template
# Demonstrates parameter passing, capabilities, IAM user tracking, and region config

set -euo pipefail

# Configuration
TEMPLATE_FILE="cloudformation-template-validated.yml"
STACK_NAME="gbl-ai-project-monitoring-stack"
REGION="${AWS_REGION:-eu-north-1}"
IAM_USER="${IAM_USER:-$(aws iam get-user --query 'User.UserName' --output text 2>/dev/null || echo 'unknown')}"

# Parameters
AI_PROJECT_POOL_ID="${1:-default-pool}"
# Use eu-central-1 as the second region when required, e.g. "eu-north-1,eu-central-1"
AI_PROJECT_REGIONS="${2:-${REGION}}"
MONITORING_SCHEDULE_EXPRESSION="${3:-rate(15 minutes)}"

# Change set name (unique per deployment)
CHANGE_SET_NAME="${STACK_NAME}-changeset-$(date +%s)"

echo "=========================================="
echo "CloudFormation Change Set Deployment"
echo "=========================================="
echo "Stack Name: $STACK_NAME"
echo "Template: $TEMPLATE_FILE"
echo "Region: $REGION"
echo "IAM User: $IAM_USER"
echo "Change Set: $CHANGE_SET_NAME"
echo "AI Project Pool ID: $AI_PROJECT_POOL_ID"
echo "AI Project Regions: $AI_PROJECT_REGIONS"
echo "Monitoring Schedule: $MONITORING_SCHEDULE_EXPRESSION"
echo ""

# Validate template first
echo "Validating template..."
aws cloudformation validate-template \
  --template-body file://"$TEMPLATE_FILE" \
  --region "$REGION" \
  > /dev/null && echo "✓ Template valid"

# Create change set
echo ""
echo "Creating change set..."
aws cloudformation create-change-set \
  --stack-name "$STACK_NAME" \
  --change-set-name "$CHANGE_SET_NAME" \
  --template-body "file://${TEMPLATE_FILE}" \
  --parameters \
    "ParameterKey=AiProjectPoolId,ParameterValue=${AI_PROJECT_POOL_ID}" \
    "ParameterKey=AiProjectRegions,ParameterValue=${AI_PROJECT_REGIONS}" \
    "ParameterKey=MonitoringScheduleExpression,ParameterValue=${MONITORING_SCHEDULE_EXPRESSION}" \
  --capabilities CAPABILITY_IAM \
  --region "$REGION" \
  --tags \
    "Key=DeployedBy,Value=${IAM_USER}" \
    "Key=DeploymentDate,Value=$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    "Key=Environment,Value=production"

# Wait for change set creation
echo "Waiting for change set to be created..."
aws cloudformation wait change-set-create-complete \
  --stack-name "$STACK_NAME" \
  --change-set-name "$CHANGE_SET_NAME" \
  --region "$REGION" \
  2>/dev/null || {
    echo "Note: Stack may not exist yet (will be created on execution)"
  }

# Describe change set to show what will change
echo ""
echo "=========================================="
echo "Change Set Summary (what will be created/changed):"
echo "=========================================="
aws cloudformation describe-change-set \
  --stack-name "$STACK_NAME" \
  --change-set-name "$CHANGE_SET_NAME" \
  --region "$REGION" \
  --query 'Changes[*].[Type, ResourceChange.Action, ResourceChange.LogicalResourceId, ResourceChange.ResourceType]' \
  --output table

echo ""
echo "=========================================="
echo "Next Steps:"
echo "=========================================="
echo "1. Review the changes above"
echo "2. To execute the change set, run:"
echo ""
echo "   aws cloudformation execute-change-set \\"
echo "     --stack-name $STACK_NAME \\"
echo "     --change-set-name $CHANGE_SET_NAME \\"
echo "     --region $REGION"
echo ""
echo "3. To monitor stack creation:"
echo ""
echo "   aws cloudformation describe-stack-events \\"
echo "     --stack-name $STACK_NAME \\"
echo "     --region $REGION \\"
echo "     --query 'StackEvents[0:10]' \\"
echo "     --output table"
echo ""
echo "4. To delete the change set without executing:"
echo ""
echo "   aws cloudformation delete-change-set \\"
echo "     --stack-name $STACK_NAME \\"
echo "     --change-set-name $CHANGE_SET_NAME \\"
echo "     --region $REGION"
echo ""
