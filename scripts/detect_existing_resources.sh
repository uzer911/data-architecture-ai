#!/usr/bin/env bash
# Detect existing AWS resources and emit shell exports for CloudFormation parameters.
set -euo pipefail

REGION="${AWS_REGION:-eu-north-1}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

PRIMARY_BUCKET="langchain-${ACCOUNT_ID}-eu-north-1"
CENTRAL_BUCKET="langchain-${ACCOUNT_ID}-eu-central-1"
ATHENA_WORKGROUP="project-text-to-sql"
LIBRARY_DB="project_library_db"
CARS_DB="project_cars_db"

resource_exists() {
  "$@" >/dev/null 2>&1
}

if resource_exists aws s3api head-bucket --bucket "$PRIMARY_BUCKET"; then
  CREATE_PRIMARY="false"
else
  CREATE_PRIMARY="true"
fi

if resource_exists aws s3api head-bucket --bucket "$CENTRAL_BUCKET"; then
  CREATE_CENTRAL="false"
else
  CREATE_CENTRAL="true"
fi

if resource_exists aws athena get-work-group --work-group "$ATHENA_WORKGROUP" --region "$REGION"; then
  CREATE_ATHENA="false"
else
  CREATE_ATHENA="true"
fi

if resource_exists aws glue get-database --name "$LIBRARY_DB" --region "$REGION"; then
  CREATE_LIBRARY_DB="false"
else
  CREATE_LIBRARY_DB="true"
fi

if resource_exists aws glue get-database --name "$CARS_DB" --region "$REGION"; then
  CREATE_CARS_DB="false"
else
  CREATE_CARS_DB="true"
fi

echo "PRIMARY_DATA_BUCKET_NAME=$PRIMARY_BUCKET"
echo "CENTRAL_DATA_BUCKET_NAME=$CENTRAL_BUCKET"
echo "CREATE_PRIMARY_DATA_BUCKET=$CREATE_PRIMARY"
echo "CREATE_CENTRAL_DATA_BUCKET=$CREATE_CENTRAL"
echo "CREATE_ATHENA_WORKGROUP=$CREATE_ATHENA"
echo "ATHENA_WORKGROUP_NAME=$ATHENA_WORKGROUP"
echo "CREATE_LIBRARY_GLUE_DATABASE=$CREATE_LIBRARY_DB"
echo "CREATE_CARS_GLUE_DATABASE=$CREATE_CARS_DB"
echo "LIBRARY_GLUE_DATABASE_NAME=$LIBRARY_DB"
echo "CARS_GLUE_DATABASE_NAME=$CARS_DB"
echo ""
echo "Reuse summary:"
echo "  Primary bucket:   create=$CREATE_PRIMARY  name=$PRIMARY_BUCKET"
echo "  Central bucket:   create=$CREATE_CENTRAL  name=$CENTRAL_BUCKET"
echo "  Athena workgroup: create=$CREATE_ATHENA  name=$ATHENA_WORKGROUP"
echo "  Library Glue DB:  create=$CREATE_LIBRARY_DB"
echo "  Cars Glue DB:     create=$CREATE_CARS_DB"
