$ErrorActionPreference = "SilentlyContinue"

$REGION = "eu-north-1"
$ECR_REPO = "data-architecture-ai"

Write-Host "=== Cleanup: delete stacks + CloudWatch, keep S3 + GitHub ===" -ForegroundColor Cyan

# Stop ECS service first
Write-Host "`n[1/6] Stopping ECS service..." -ForegroundColor Yellow
aws ecs update-service --cluster data-architecture-ai --service data-architecture-ai --desired-count 0 --region $REGION 2>&1 | Out-Null
Write-Host "Done." -ForegroundColor Green

# Clear Athena workgroup (blocks stack deletion if not empty)
Write-Host "`n[2/6] Deleting Athena workgroup..." -ForegroundColor Yellow
aws athena delete-work-group --work-group project-text-to-sql --recursive-delete-option --region $REGION 2>&1 | Out-Null
Write-Host "Done." -ForegroundColor Green

# Clear ECR images (blocks stack deletion if images exist)
Write-Host "`n[3/6] Deleting ECR images..." -ForegroundColor Yellow
$imageIds = aws ecr list-images --repository-name $ECR_REPO --region $REGION --query "imageIds" --output json 2>&1
if ($imageIds -and $imageIds -ne "[]") {
    $ids = ($imageIds | ConvertFrom-Json)
    foreach ($img in $ids) {
        if ($img.imageTag) {
            aws ecr batch-delete-image --repository-name $ECR_REPO --region $REGION --image-ids "imageTag=$($img.imageTag)" 2>&1 | Out-Null
        }
    }
}
Write-Host "Done." -ForegroundColor Green

# Delete main CloudFormation stack
Write-Host "`n[4/6] Deleting main CloudFormation stack (~5 min)..." -ForegroundColor Yellow
aws cloudformation delete-stack --stack-name ai-analyst-agent-project --region $REGION 2>&1 | Out-Null
aws cloudformation wait stack-delete-complete --stack-name ai-analyst-agent-project --region $REGION 2>&1 | Out-Null
Write-Host "Main stack deleted." -ForegroundColor Green

# Delete OIDC role stack
Write-Host "`n[5/6] Deleting OIDC role stack..." -ForegroundColor Yellow
aws cloudformation delete-stack --stack-name github-oidc-role --region $REGION 2>&1 | Out-Null
aws cloudformation wait stack-delete-complete --stack-name github-oidc-role --region $REGION 2>&1 | Out-Null
Write-Host "OIDC stack deleted." -ForegroundColor Green

# Delete CloudWatch log group
Write-Host "`n[6/6] Deleting CloudWatch log group..." -ForegroundColor Yellow
aws logs delete-log-group --log-group-name /ecs/data-architecture-ai --region $REGION 2>&1 | Out-Null
Write-Host "Done." -ForegroundColor Green

# Verify
Write-Host "`n=== Verification ===" -ForegroundColor Yellow
$mainStack = aws cloudformation describe-stacks --stack-name ai-analyst-agent-project --region $REGION 2>&1
$oidcStack = aws cloudformation describe-stacks --stack-name github-oidc-role --region $REGION 2>&1
$logGroup  = aws logs describe-log-groups --log-group-name-prefix /ecs/data-architecture-ai --region $REGION --query "logGroups[].logGroupName" --output text 2>&1

if ($mainStack -match "does not exist") { Write-Host "  Main stack  : deleted" -ForegroundColor Green }
else { Write-Host "  Main stack  : still exists!" -ForegroundColor Red }

if ($oidcStack -match "does not exist") { Write-Host "  OIDC stack  : deleted" -ForegroundColor Green }
else { Write-Host "  OIDC stack  : still exists!" -ForegroundColor Red }

if (-not $logGroup -or $logGroup -eq "") { Write-Host "  CloudWatch  : deleted" -ForegroundColor Green }
else { Write-Host "  CloudWatch  : still exists!" -ForegroundColor Red }

Write-Host "  S3 bucket   : kept (data preserved)" -ForegroundColor Cyan
Write-Host "  GitHub repo : kept" -ForegroundColor Cyan

Write-Host "`n=== Ready for fresh deployment ===" -ForegroundColor Cyan
Write-Host "Run .\deploy.ps1 to redeploy." -ForegroundColor White
