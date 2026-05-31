#!/usr/bin/env bash
# CloudFormation deployment script.
# The stack creates its own VPC, subnets, and VPC endpoints — no external
# VPC parameters are needed. No NAT gateway is used.
#
# Usage:
#   ./deploy-changeset.sh          # Review mode: creates change set, shows summary
#   ./deploy-changeset.sh --auto   # Full auto: deploy stack + push image + start service
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────
TEMPLATE_FILE="cloudformation-template-validated.yml"
STACK_NAME="cgs-ai-analyst-agent-project"
REGION="${AWS_REGION:-eu-north-1}"
IAM_USER="${IAM_USER:-$(aws iam get-user --query 'User.UserName' --output text 2>/dev/null || echo 'unknown')}"
DESIRED_COUNT="${DESIRED_COUNT:-1}"
AUTO_MODE=false

# Parse flags
for arg in "$@"; do
  case "$arg" in
    --auto) AUTO_MODE=true ;;
  esac
done

# Detect which data-layer resources already exist
eval "$(bash scripts/detect_existing_resources.sh | grep -E '^[A-Z_]+=')"

# ── Change set type ────────────────────────────────────────────────────────
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

# On first deploy (CREATE) in auto mode, deploy with DesiredCount=0 to avoid
# ECS service getting stuck waiting for a container image that doesn't exist yet.
# The image is pushed after stack creation, then the service is scaled up.
DEPLOY_DESIRED_COUNT="$DESIRED_COUNT"
if $AUTO_MODE && [[ "$CHANGE_SET_TYPE" == "CREATE" ]]; then
  DEPLOY_DESIRED_COUNT="0"
fi

# ── CloudFormation parameters ─────────────────────────────────────────────
CFN_PARAMETERS=$(cat <<EOF
[
  {"ParameterKey": "DesiredCount",              "ParameterValue": "${DEPLOY_DESIRED_COUNT}"},
  {"ParameterKey": "PrimaryDataBucketName",     "ParameterValue": "${PRIMARY_DATA_BUCKET_NAME}"},
  {"ParameterKey": "CreatePrimaryDataBucket",   "ParameterValue": "${CREATE_PRIMARY_DATA_BUCKET}"},
  {"ParameterKey": "AthenaWorkgroupName",       "ParameterValue": "${ATHENA_WORKGROUP_NAME}"},
  {"ParameterKey": "CreateAthenaWorkgroup",     "ParameterValue": "${CREATE_ATHENA_WORKGROUP}"},
  {"ParameterKey": "LibraryGlueDatabaseName",   "ParameterValue": "${LIBRARY_GLUE_DATABASE_NAME}"},
  {"ParameterKey": "CarsGlueDatabaseName",      "ParameterValue": "${CARS_GLUE_DATABASE_NAME}"},
  {"ParameterKey": "CreateLibraryGlueDatabase", "ParameterValue": "${CREATE_LIBRARY_GLUE_DATABASE}"},
  {"ParameterKey": "CreateCarsGlueDatabase",    "ParameterValue": "${CREATE_CARS_GLUE_DATABASE}"},
  {"ParameterKey": "CreateAppLogGroup",         "ParameterValue": "${CREATE_APP_LOG_GROUP}"}
]
EOF
)

echo "=========================================="
echo "CloudFormation Deployment"
echo "=========================================="
echo "Stack Name:      $STACK_NAME"
echo "Template:        $TEMPLATE_FILE"
echo "Region:          $REGION"
echo "IAM User:        $IAM_USER"
echo "Mode:            $(if $AUTO_MODE; then echo 'AUTO (deploy + push + start)'; else echo 'REVIEW (change set only)'; fi)"
echo "Change Set Type: $CHANGE_SET_TYPE (stack status: ${STACK_STATUS})"
echo ""

# ── Validate template ──────────────────────────────────────────────────────
echo "Validating template..."
aws cloudformation validate-template \
  --template-body file://"$TEMPLATE_FILE" \
  --region "$REGION" \
  > /dev/null && echo "✓ Template valid"

# ── Create change set ──────────────────────────────────────────────────────
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

# ── Wait for change set ────────────────────────────────────────────────────
echo "Waiting for change set to be created..."
if ! aws cloudformation wait change-set-create-complete \
  --stack-name "$STACK_NAME" \
  --change-set-name "$CHANGE_SET_NAME" \
  --region "$REGION" \
  2>/dev/null; then
  # Check if changeset failed
  CS_STATUS="$(aws cloudformation describe-change-set \
    --stack-name "$STACK_NAME" \
    --change-set-name "$CHANGE_SET_NAME" \
    --region "$REGION" \
    --query 'Status' --output text 2>/dev/null || echo 'UNKNOWN')"
  CS_REASON="$(aws cloudformation describe-change-set \
    --stack-name "$STACK_NAME" \
    --change-set-name "$CHANGE_SET_NAME" \
    --region "$REGION" \
    --query 'StatusReason' --output text 2>/dev/null || echo '')"
  if [[ "$CS_STATUS" == "FAILED" ]]; then
    echo ""
    echo "❌ Change set FAILED: $CS_REASON"
    echo ""
    echo "Cleaning up failed change set..."
    aws cloudformation delete-change-set \
      --stack-name "$STACK_NAME" \
      --change-set-name "$CHANGE_SET_NAME" \
      --region "$REGION" 2>/dev/null || true
    # If stack is in REVIEW_IN_PROGRESS (failed CREATE), delete the empty stack
    if [[ "$CHANGE_SET_TYPE" == "CREATE" ]]; then
      echo "Deleting empty stack (was never created)..."
      aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$REGION" 2>/dev/null || true
    fi
    echo ""
    echo "Common causes:"
    echo "  - A resource already exists outside the stack (check ResourceExistenceCheck)"
    echo "  - Re-run: ./deploy-changeset.sh --auto (detection script will adapt)"
    exit 1
  fi
fi

# ── Show summary ───────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "Change Set Summary:"
echo "=========================================="
aws cloudformation describe-change-set \
  --stack-name "$STACK_NAME" \
  --change-set-name "$CHANGE_SET_NAME" \
  --region "$REGION" \
  --query 'Changes[*].[Type, ResourceChange.Action, ResourceChange.LogicalResourceId, ResourceChange.ResourceType]' \
  --output table

# ── Auto mode: execute + push + start ──────────────────────────────────────
if $AUTO_MODE; then
  echo ""
  echo "=========================================="
  echo "AUTO MODE: Executing change set..."
  echo "=========================================="
  aws cloudformation execute-change-set \
    --stack-name "$STACK_NAME" \
    --change-set-name "$CHANGE_SET_NAME" \
    --region "$REGION"

  echo "Waiting for stack to complete (this may take 5-10 minutes)..."
  if [[ "$CHANGE_SET_TYPE" == "CREATE" ]]; then
    aws cloudformation wait stack-create-complete \
      --stack-name "$STACK_NAME" \
      --region "$REGION"
  else
    aws cloudformation wait stack-update-complete \
      --stack-name "$STACK_NAME" \
      --region "$REGION"
  fi
  echo "✓ Stack $CHANGE_SET_TYPE complete"

  echo ""
  echo "=========================================="
  echo "Building and pushing container image..."
  echo "=========================================="
  DESIRED_COUNT="$DESIRED_COUNT" ./scripts/push_ecr.sh

  echo ""
  echo "=========================================="
  echo "Running Glue Crawlers (populates table catalog)..."
  echo "=========================================="
  for CRAWLER_NAME in project-library-crawler project-cars-crawler; do
    CRAWLER_STATE="$(aws glue get-crawler --name "$CRAWLER_NAME" --region "$REGION" \
      --query 'Crawler.State' --output text 2>/dev/null || echo 'NOT_FOUND')"
    if [[ "$CRAWLER_STATE" == "READY" ]]; then
      echo "Starting crawler: $CRAWLER_NAME"
      aws glue start-crawler --name "$CRAWLER_NAME" --region "$REGION" 2>/dev/null || true
    elif [[ "$CRAWLER_STATE" == "NOT_FOUND" ]]; then
      echo "⚠️  Crawler $CRAWLER_NAME not found — skipping"
    else
      echo "⚠️  Crawler $CRAWLER_NAME is in state $CRAWLER_STATE — skipping"
    fi
  done
  # Wait for crawlers to finish (up to 2 minutes)
  echo "Waiting for crawlers to complete..."
  for i in $(seq 1 12); do
    sleep 10
    LIB_STATE="$(aws glue get-crawler --name project-library-crawler --region "$REGION" \
      --query 'Crawler.State' --output text 2>/dev/null || echo 'READY')"
    CARS_STATE="$(aws glue get-crawler --name project-cars-crawler --region "$REGION" \
      --query 'Crawler.State' --output text 2>/dev/null || echo 'READY')"
    if [[ "$LIB_STATE" == "READY" && "$CARS_STATE" == "READY" ]]; then
      echo "✓ Crawlers complete — Glue tables registered"
      break
    fi
    if [[ $i -eq 12 ]]; then
      echo "⚠️  Crawlers still running after 2 min — tables may not be ready yet"
    fi
  done

  echo ""
  echo "=========================================="
  echo "Configuring S3 event notification (fail-safe)..."
  echo "=========================================="
  bash scripts/configure_s3_notification.sh || echo "⚠️  S3 notification config skipped (Lambda may not be ready yet)"

  echo ""
  echo "=========================================="
  echo "✅ DEPLOYMENT COMPLETE"
  echo "=========================================="
  ALB_URL="$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='LoadBalancerUrl'].OutputValue" \
    --output text 2>/dev/null || true)"
  if [[ -n "$ALB_URL" && "$ALB_URL" != "None" ]]; then
    echo "🌐 API URL:     $ALB_URL"
    echo "❤️  Health:      $ALB_URL/health"
    echo "💬 Query:       curl -X POST $ALB_URL/query -H 'Content-Type: application/json' -d '{\"question\":\"How many books?\"}'"
  fi
else
  # Review mode — show next steps
  echo ""
  echo "=========================================="
  echo "Next Steps:"
  echo "=========================================="
  echo ""
  echo "  Option A — Run everything automatically:"
  echo ""
  echo "    ./deploy-changeset.sh --auto"
  echo ""
  echo "  Option B — Execute manually:"
  echo ""
  echo "    1. Execute the change set:"
  echo "       aws cloudformation execute-change-set \\"
  echo "         --stack-name $STACK_NAME \\"
  echo "         --change-set-name $CHANGE_SET_NAME \\"
  echo "         --region $REGION"
  echo ""
  echo "    2. Wait for completion:"
  echo "       aws cloudformation wait stack-${CHANGE_SET_TYPE,,}-complete \\"
  echo "         --stack-name $STACK_NAME --region $REGION"
  echo ""
  echo "    3. Push image and start:"
  echo "       DESIRED_COUNT=1 ./scripts/push_ecr.sh"
  echo ""
  echo "  To delete the change set without executing:"
  echo "    aws cloudformation delete-change-set \\"
  echo "      --stack-name $STACK_NAME \\"
  echo "      --change-set-name $CHANGE_SET_NAME \\"
  echo "      --region $REGION"
  echo ""
fi
