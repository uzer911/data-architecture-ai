$ErrorActionPreference = "Stop"

$REGION     = "eu-north-1"
$ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$BUCKET     = "langchain-$ACCOUNT_ID-$REGION"
$STACK_MAIN = "ai-analyst-agent-project"
$STACK_OIDC = "github-actions-ai-agent-role"
$STACK_RDS  = "ai-rds-aurora"
$GITHUB_ORG  = "uzer911"
$GITHUB_REPO = "data-architecture-ai"

Write-Host "`n=== Starting full deployment ===" -ForegroundColor Cyan
Write-Host "Account : $ACCOUNT_ID"
Write-Host "Region  : $REGION"
Write-Host "Bucket  : $BUCKET"

# ─── helper: wait for stack ───────────────────────────────────────────────────
function Wait-Stack($name, $waitCmd) {
    Write-Host "Waiting for $name ..." -ForegroundColor Yellow
    & $waitCmd
    $status = aws cloudformation describe-stacks --stack-name $name --region $REGION --query "Stacks[0].StackStatus" --output text
    Write-Host "$name => $status" -ForegroundColor Green
}

# ─── STEP 1: S3 bucket ────────────────────────────────────────────────────────
Write-Host "`n[1/6] S3 bucket..." -ForegroundColor Yellow
$bucketExists = $false
try { aws s3api head-bucket --bucket $BUCKET --region $REGION 2>&1 | Out-Null; $bucketExists = ($LASTEXITCODE -eq 0) } catch {}
if (-not $bucketExists) {
    aws s3api create-bucket --bucket $BUCKET --region $REGION --create-bucket-configuration LocationConstraint=$REGION | Out-Null
    Write-Host "Bucket created: $BUCKET" -ForegroundColor Green
} else {
    Write-Host "Bucket exists: $BUCKET" -ForegroundColor Green
}
$CREATE_BUCKET = if ($bucketExists) { "false" } else { "true" }

# ─── STEP 2: Upload templates ─────────────────────────────────────────────────
Write-Host "`n[2/6] Uploading CloudFormation templates to S3..." -ForegroundColor Yellow
aws s3 cp cloudformation-template-validated.yml "s3://$BUCKET/cfn/template.yml" --region $REGION
aws s3 cp cloudformation-github-oidc-role.yml   "s3://$BUCKET/cfn/oidc-role.yml" --region $REGION
Write-Host "Templates uploaded." -ForegroundColor Green

# ─── STEP 3: Main infrastructure stack ───────────────────────────────────────
Write-Host "`n[3/6] Main infrastructure stack..." -ForegroundColor Yellow
$mainExists = $false
try { aws cloudformation describe-stacks --stack-name $STACK_MAIN --region $REGION 2>&1 | Out-Null; $mainExists = ($LASTEXITCODE -eq 0) } catch {}
if (-not $mainExists) {
    aws cloudformation create-stack `
        --stack-name $STACK_MAIN `
        --template-url "https://s3.$REGION.amazonaws.com/$BUCKET/cfn/template.yml" `
        --capabilities CAPABILITY_IAM `
        --region $REGION `
        --parameters `
            ParameterKey=DesiredCount,ParameterValue=0 `
            ParameterKey=PrimaryDataBucketName,ParameterValue=$BUCKET `
            ParameterKey=CreatePrimaryDataBucket,ParameterValue=$CREATE_BUCKET `
            ParameterKey=CreateLibraryGlueDatabase,ParameterValue=true `
            ParameterKey=CreateCarsGlueDatabase,ParameterValue=true `
            ParameterKey=CreateAthenaWorkgroup,ParameterValue=true `
            ParameterKey=CreateAppLogGroup,ParameterValue=true `
        --tags Key=Environment,Value=production | Out-Null
    Write-Host "Stack creation started (~10 min)..." -ForegroundColor Yellow
    aws cloudformation wait stack-create-complete --stack-name $STACK_MAIN --region $REGION
    Write-Host "Main stack created." -ForegroundColor Green
} else {
    Write-Host "Main stack already exists." -ForegroundColor Green
}

# ─── STEP 4: GitHub OIDC role stack ──────────────────────────────────────────
Write-Host "`n[4/6] GitHub OIDC role stack..." -ForegroundColor Yellow
$oidcExists = $false
try { aws cloudformation describe-stacks --stack-name $STACK_OIDC --region $REGION 2>&1 | Out-Null; $oidcExists = ($LASTEXITCODE -eq 0) } catch {}
if (-not $oidcExists) {
    aws cloudformation create-stack `
        --stack-name $STACK_OIDC `
        --template-url "https://s3.$REGION.amazonaws.com/$BUCKET/cfn/oidc-role.yml" `
        --capabilities CAPABILITY_NAMED_IAM `
        --region $REGION `
        --parameters `
            ParameterKey=GitHubOrg,ParameterValue=$GITHUB_ORG `
            ParameterKey=GitHubRepo,ParameterValue=$GITHUB_REPO | Out-Null
    aws cloudformation wait stack-create-complete --stack-name $STACK_OIDC --region $REGION
    Write-Host "OIDC stack created." -ForegroundColor Green
} else {
    Write-Host "OIDC stack already exists." -ForegroundColor Green
}

# ─── STEP 5: Aurora RDS stack ─────────────────────────────────────────────────
Write-Host "`n[5/7] Aurora RDS stack..." -ForegroundColor Yellow
$rdsExists = $false
try { aws cloudformation describe-stacks --stack-name $STACK_RDS --region $REGION 2>&1 | Out-Null; $rdsExists = ($LASTEXITCODE -eq 0) } catch {}
if (-not $rdsExists) {
    aws s3 cp cloudformation-rds-aurora.yml "s3://$BUCKET/cfn/rds-aurora.yml" --region $REGION
    aws cloudformation create-stack `
        --stack-name $STACK_RDS `
        --template-url "https://s3.$REGION.amazonaws.com/$BUCKET/cfn/rds-aurora.yml" `
        --capabilities CAPABILITY_IAM `
        --region $REGION `
        --parameters `
            ParameterKey=MainStackName,ParameterValue=$STACK_MAIN | Out-Null
    Write-Host "RDS stack creation started (~8 min)..." -ForegroundColor Yellow
    aws cloudformation wait stack-create-complete --stack-name $STACK_RDS --region $REGION
    Write-Host "RDS stack created." -ForegroundColor Green

    # Print connection info
    $rdsEndpoint = aws cloudformation describe-stacks --stack-name $STACK_RDS --region $REGION --query "Stacks[0].Outputs[?OutputKey=='ClusterEndpoint'].OutputValue" --output text
    Write-Host "Aurora endpoint: $rdsEndpoint" -ForegroundColor Cyan
    Write-Host "Copy this to config/connections/rds-mysql.yaml when ready." -ForegroundColor White
} else {
    Write-Host "RDS stack already exists." -ForegroundColor Green
}

# ─── STEP 6: Upload sample data and run crawlers ──────────────────────────────
Write-Host "`n[6/7] Uploading sample data to S3..." -ForegroundColor Yellow
aws s3 cp data/s3_library_data.json        "s3://$BUCKET/library-data/" --region $REGION
aws s3 cp data/s3_cars_data_normalized.csv "s3://$BUCKET/cars-data/"    --region $REGION
Write-Host "Sample data uploaded." -ForegroundColor Green

Write-Host "Starting Glue crawlers..." -ForegroundColor Yellow
aws glue start-crawler --name project-library-crawler --region $REGION 2>&1 | Out-Null
aws glue start-crawler --name project-cars-crawler    --region $REGION 2>&1 | Out-Null

Write-Host "Waiting for crawlers to finish (~2 min)..." -ForegroundColor Yellow
do {
    Start-Sleep -Seconds 15
    $libState  = aws glue get-crawler --name project-library-crawler --region $REGION --query "Crawler.State" --output text 2>&1
    $carsState = aws glue get-crawler --name project-cars-crawler    --region $REGION --query "Crawler.State" --output text 2>&1
    Write-Host "  library=$libState  cars=$carsState"
} while ($libState -eq "RUNNING" -or $carsState -eq "RUNNING")
Write-Host "Crawlers done." -ForegroundColor Green

Write-Host "Setting Athena workgroup S3 output location..." -ForegroundColor Yellow
aws athena update-work-group --work-group project-text-to-sql --region $REGION --configuration-updates "ResultConfigurationUpdates={OutputLocation=s3://$BUCKET/athenaresults/}" 2>&1 | Out-Null
Write-Host "Athena output location set." -ForegroundColor Green

# ─── STEP 6: Print next steps ─────────────────────────────────────────────────
Write-Host "`n[7/7] Getting deploy role ARN..." -ForegroundColor Yellow
$roleArn = aws cloudformation describe-stacks `
    --stack-name $STACK_OIDC --region $REGION `
    --query "Stacks[0].Outputs[?OutputKey=='DeployRoleArn'].OutputValue" `
    --output text

Write-Host "`n=== INFRASTRUCTURE DEPLOYED ===" -ForegroundColor Green
Write-Host ""
Write-Host "Now do these 2 manual steps to complete deployment:" -ForegroundColor Cyan
Write-Host ""
Write-Host "STEP A — Add this secret to GitHub:" -ForegroundColor Yellow
Write-Host "  URL  : https://github.com/$GITHUB_ORG/$GITHUB_REPO/settings/secrets/actions"
Write-Host "  Name : AWS_DEPLOY_ROLE_ARN"
Write-Host "  Value: $roleArn"
Write-Host ""
Write-Host "STEP B — Push code to trigger GitHub Actions:" -ForegroundColor Yellow
Write-Host "  git add -A"
Write-Host "  git commit -m 'deploy'"
Write-Host "  git push -u origin main"
Write-Host ""
Write-Host "GitHub Actions will build the Docker image and deploy to ECS automatically." -ForegroundColor Cyan
