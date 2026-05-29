#!/usr/bin/env bash
# CloudFormation deployment script: create change set and deploy template
# Demonstrates capabilities, IAM user tracking, and region config

set -euo pipefail

# Configuration
TEMPLATE_FILE="cloudformation-template-validated.yml"
STACK_NAME="gbl-ai-project-monitoring-stack"
REGION="${AWS_REGION:-eu-north-1}"
IAM_USER="${IAM_USER:-$(aws iam get-user --query 'User.UserName' --output text 2>/dev/null || echo 'unknown')}"
DESIRED_COUNT="${DESIRED_COUNT:-0}"

# VPC + existing-resource parameters
eval "$(bash scripts/get_vpc_params.sh | grep -E '^(VPC_ID|PUBLIC_SUBNET_IDS)=')"
eval "$(bash scripts/detect_existing_resources.sh | grep -E '^[A-Z_]+=')"
if [[ -z "${VPC_ID:-}" || -z "${PUBLIC_SUBNET_IDS:-}" ]]; then
  echo "Failed to resolve VPC parameters. Set VPC_ID and PUBLIC_SUBNET_IDS manually." >&2
  exit 1
fi

# JSON avoids AWS CLI splitting comma-separated List parameters (PublicSubnetIds).
CFN_PARAMETERS=$(cat <<EOF
[
  {"ParameterKey": "VpcId", "ParameterValue": "${VPC_ID}"},
  {"ParameterKey": "PublicSubnetIds", "ParameterValue": "${PUBLIC_SUBNET_IDS}"},
  {"ParameterKey": "DesiredCount", "ParameterValue": "${DESIRED_COUNT}"},
  {"ParameterKey": "PrimaryDataBucketName", "ParameterValue": "${PRIMARY_DATA_BUCKET_NAME}"},
  {"ParameterKey": "CentralDataBucketName", "ParameterValue": "${CENTRAL_DATA_BUCKET_NAME}"},
  {"ParameterKey": "CreatePrimaryDataBucket", "ParameterValue": "${CREATE_PRIMARY_DATA_BUCKET}"},
  {"ParameterKey": "CreateCentralDataBucket", "ParameterValue": "${CREATE_CENTRAL_DATA_BUCKET}"},
  {"ParameterKey": "AthenaWorkgroupName", "ParameterValue": "${ATHENA_WORKGROUP_NAME}"},
  {"ParameterKey": "CreateAthenaWorkgroup", "ParameterValue": "${CREATE_ATHENA_WORKGROUP}"},
  {"ParameterKey": "LibraryGlueDatabaseName", "ParameterValue": "${LIBRARY_GLUE_DATABASE_NAME}"},
  {"ParameterKey": "CarsGlueDatabaseName", "ParameterValue": "${CARS_GLUE_DATABASE_NAME}"},
  {"ParameterKey": "CreateLibraryGlueDatabase", "ParameterValue": "${CREATE_LIBRARY_GLUE_DATABASE}"},
  {"ParameterKey": "CreateCarsGlueDatabase", "ParameterValue": "${CREATE_CARS_GLUE_DATABASE}"}
]
EOF
)


# Change set name (unique per deployment)
CHANGE_SET_NAME="${STACK_NAME}-changeset-$(date +%s)"

STACK_STATUS="$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].StackStatus' \
  --output text 2>/dev/null || echo 'NOT_FOUND')"

if [[ "$STACK_STATUS" == "NOT_FOUND" || "$STACK_STATUS" == "DELETE_COMPLETE" ]]; then
  CHANGE_SET_TYPE="CREATE"
else
  CHANGE_SET_TYPE="UPDATE"
fi

echo "=========================================="
echo "CloudFormation Change Set Deployment"
echo "=========================================="
echo "Stack Name: $STACK_NAME"
echo "Template: $TEMPLATE_FILE"
echo "Region: $REGION"
echo "IAM User: $IAM_USER"
echo "Change Set: $CHANGE_SET_NAME"
echo "Change Set Type: $CHANGE_SET_TYPE (stack status: ${STACK_STATUS})"
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
if ! aws cloudformation create-change-set \
  --stack-name "$STACK_NAME" \
  --change-set-name "$CHANGE_SET_NAME" \
  --change-set-type "$CHANGE_SET_TYPE" \
  --template-body "file://${TEMPLATE_FILE}" \
  --capabilities CAPABILITY_IAM \
  --region "$REGION" \
  --parameters "$CFN_PARAMETERS" \
  --tags \
    "Key=DeployedBy,Value=${IAM_USER}" \
    "Key=DeploymentDate,Value=$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    "Key=Environment,Value=production" 2>"${TMPDIR:-/tmp}/cfn-changeset.err"; then
  if grep -q 'Stack.*does not exist' "${TMPDIR:-/tmp}/cfn-changeset.err"; then
    echo "Stack not found — retrying with --change-set-type CREATE..."
    CHANGE_SET_TYPE="CREATE"
    aws cloudformation create-change-set \
      --stack-name "$STACK_NAME" \
      --change-set-name "$CHANGE_SET_NAME" \
      --change-set-type CREATE \
      --template-body "file://${TEMPLATE_FILE}" \
      --capabilities CAPABILITY_IAM \
      --region "$REGION" \
      --parameters "$CFN_PARAMETERS" \
      --tags \
        "Key=DeployedBy,Value=${IAM_USER}" \
        "Key=DeploymentDate,Value=$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        "Key=Environment,Value=production"
  else
    cat "${TMPDIR:-/tmp}/cfn-changeset.err" >&2
    exit 1
  fi
fi

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
echo "4. Push the container image and start the API:"
echo ""
echo "   chmod +x scripts/push_ecr.sh"
echo "   DESIRED_COUNT=1 ./scripts/push_ecr.sh"
echo ""
echo ""
echo "5. To delete the change set without executing:"
echo ""
echo "   aws cloudformation delete-change-set \\"
echo "     --stack-name $STACK_NAME \\"
echo "     --change-set-name $CHANGE_SET_NAME \\"
echo "     --region $REGION"
echo ""
