$ErrorActionPreference = "Stop"

$REGION     = "eu-north-1"
$ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$BUCKET     = "langchain-$ACCOUNT_ID-$REGION"
$STACK_MAIN = "ai-analyst-agent-project"
$STACK_OIDC = "github-oidc-role"
$GITHUB_ORG  = "uzer911"
$GITHUB_REPO = "data-architecture-ai"

Write-Host "=== Starting full deployment ===" -ForegroundColor Cyan
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
            ParameterKey=CreatePrimaryDataBucket,ParameterValue=false `
            ParameterKey=CreateLibraryGlueDatabase,ParameterValue=true `
            ParameterKey=CreateCarsGlueDatabase,ParameterValue=true `
            ParameterKey=CreateAthenaWorkgroup,ParameterValue=true `
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

# ─── STEP 5: Upload sample data ───────────────────────────────────────────────
Write-Host "`n[5/6] Uploading sample data to S3..." -ForegroundColor Yellow
aws s3 cp data/s3_library_data.json          "s3://$BUCKET/library-data/" --region $REGION
aws s3 cp data/s3_cars_data_normalized.csv   "s3://$BUCKET/cars-data/"    --region $REGION
Write-Host "Sample data uploaded." -ForegroundColor Green

# ─── STEP 6: Print next steps ─────────────────────────────────────────────────
Write-Host "`n[6/6] Getting deploy role ARN..." -ForegroundColor Yellow
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
