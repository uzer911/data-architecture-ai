#!/usr/bin/env bash
# Print default VPC ID and comma-separated public subnet IDs for CloudFormation parameters.
set -euo pipefail

REGION="${AWS_REGION:-eu-north-1}"

VPC_ID="$(aws ec2 describe-vpcs \
  --region "$REGION" \
  --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' \
  --output text)"

if [[ -z "$VPC_ID" || "$VPC_ID" == "None" ]]; then
  echo "No default VPC found in $REGION. Create a VPC or pass VpcId/PublicSubnetIds manually." >&2
  exit 1
fi

SUBNETS="$(aws ec2 describe-subnets \
  --region "$REGION" \
  --filters "Name=vpc-id,Values=$VPC_ID" "Name=map-public-ip-on-launch,Values=true" \
  --query 'Subnets[*].SubnetId' \
  --output text | tr '\t' ',')"

if [[ -z "$SUBNETS" ]]; then
  echo "No public subnets found in default VPC $VPC_ID." >&2
  exit 1
fi

echo "VPC_ID=$VPC_ID"
echo "PUBLIC_SUBNET_IDS=$SUBNETS"
echo ""
echo "Example deploy parameters (JSON — required for comma-separated subnet lists):"
cat <<EOF
  --parameters '[{"ParameterKey":"VpcId","ParameterValue":"$VPC_ID"},{"ParameterKey":"PublicSubnetIds","ParameterValue":"$SUBNETS"}]'
EOF
