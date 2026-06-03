# cleanup.ps1 — Nuclear clean slate for ai-analyst-agent-project
# Removes EVERYTHING that could block a fresh deployment:
#   - All 3 CloudFormation stacks (handles any stuck/rollback state)
#   - ECR images (tagged + untagged)
#   - Athena workgroup
#   - Glue crawlers + databases
#   - CloudWatch log group
#   - Orphaned IAM roles left by failed stack deployments
#   - S3 notification config (not the bucket itself — data preserved)
#
# Usage: .\cleanup.ps1
# Safe to run multiple times — every step is idempotent.

$ErrorActionPreference = "SilentlyContinue"
$REGION   = "eu-north-1"
$ACCOUNT  = (aws sts get-caller-identity --query Account --output text 2>$null)

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " FULL CLEANUP — account $ACCOUNT / $REGION" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── Helper: wait for a stack to finish deleting ──────────────────────────────
function Remove-Stack {
    param([string]$Name)

    $status = aws cloudformation describe-stacks --stack-name $Name --region $REGION `
        --query "Stacks[0].StackStatus" --output text 2>$null

    if (-not $status -or $status -match "does not exist") {
        Write-Host "  $Name : already gone" -ForegroundColor DarkGray
        return
    }

    Write-Host "  $Name : current status = $status" -ForegroundColor Yellow

    # Force DELETE even from ROLLBACK_COMPLETE or UPDATE_ROLLBACK_FAILED
    if ($status -eq "DELETE_IN_PROGRESS") {
        Write-Host "  $Name : delete already in progress — waiting..." -ForegroundColor Yellow
    } else {
        aws cloudformation delete-stack --stack-name $Name --region $REGION 2>$null | Out-Null
    }

    # Poll until gone (up to 20 min)
    $waited = 0
    do {
        Start-Sleep -Seconds 15
        $waited += 15
        $status = aws cloudformation describe-stacks --stack-name $Name --region $REGION `
            --query "Stacks[0].StackStatus" --output text 2>$null
        if ($status -and $status -ne "None") {
            Write-Host "  $Name : $status ($waited s)" -ForegroundColor DarkGray
        }
        if ($waited -ge 1200) {
            Write-Host "  $Name : timed out after 20 min — check console" -ForegroundColor Red
            return
        }
    } while ($status -and $status -notmatch "does not exist" -and $status -ne "None" -and $status -ne "")

    Write-Host "  $Name : DELETED" -ForegroundColor Green
}

# ── 1. Stop ECS tasks (prevents ENI/SG locks during stack deletion) ──────────
Write-Host "[1/10] Stopping ECS service..." -ForegroundColor Yellow
aws ecs update-service --cluster data-architecture-ai --service data-architecture-ai `
    --desired-count 0 --region $REGION 2>$null | Out-Null
# Wait for tasks to drain
Start-Sleep -Seconds 10
Write-Host "       ECS tasks draining..." -ForegroundColor DarkGray

# ── 2. Delete Athena workgroup (blocks CFN deletion if exists) ────────────────
Write-Host "[2/10] Deleting Athena workgroup..." -ForegroundColor Yellow
aws athena delete-work-group --work-group project-text-to-sql `
    --recursive-delete-option --region $REGION 2>$null | Out-Null
Write-Host "       Done" -ForegroundColor Green

# ── 3. Delete ALL ECR images (tagged + untagged digests) ─────────────────────
Write-Host "[3/10] Deleting ECR images..." -ForegroundColor Yellow
$imageIds = aws ecr list-images --repository-name data-architecture-ai `
    --region $REGION --query "imageIds" --output json 2>$null
if ($imageIds -and $imageIds -ne "[]" -and $imageIds -ne "null") {
    $ids = $imageIds | ConvertFrom-Json
    if ($ids.Count -gt 0) {
        # Build batch delete request
        $idArgs = ($ids | ForEach-Object {
            if ($_.imageTag)    { "imageTag=$($_.imageTag)" }
            elseif ($_.imageDigest) { "imageDigest=$($_.imageDigest)" }
        }) -join " "
        foreach ($id in $ids) {
            if ($id.imageTag) {
                aws ecr batch-delete-image --repository-name data-architecture-ai `
                    --region $REGION --image-ids "imageTag=$($id.imageTag)" 2>$null | Out-Null
            } elseif ($id.imageDigest) {
                aws ecr batch-delete-image --repository-name data-architecture-ai `
                    --region $REGION --image-ids "imageDigest=$($id.imageDigest)" 2>$null | Out-Null
            }
        }
        Write-Host "       Deleted $($ids.Count) image(s)" -ForegroundColor Green
    }
} else {
    Write-Host "       No images found" -ForegroundColor DarkGray
}

# ── 4. Stop + delete Glue crawlers (prevents CFN timeout) ────────────────────
Write-Host "[4/10] Stopping and deleting Glue crawlers..." -ForegroundColor Yellow
foreach ($crawler in @("project-library-crawler","project-cars-crawler")) {
    $state = aws glue get-crawler --name $crawler --region $REGION `
        --query "Crawler.State" --output text 2>$null
    if ($state -eq "RUNNING") {
        aws glue stop-crawler --name $crawler --region $REGION 2>$null | Out-Null
        Start-Sleep -Seconds 5
    }
    aws glue delete-crawler --name $crawler --region $REGION 2>$null | Out-Null
    Write-Host "       $crawler : removed" -ForegroundColor DarkGray
}

# ── 5. Delete Glue databases ──────────────────────────────────────────────────
Write-Host "[5/10] Deleting Glue databases..." -ForegroundColor Yellow
foreach ($db in @("project_library_db","project_cars_db","project_library_data_db","project_cars_data_db")) {
    aws glue delete-database --name $db --region $REGION 2>$null | Out-Null
    Write-Host "       $db : removed" -ForegroundColor DarkGray
}

# ── 6. Delete CloudWatch log group ───────────────────────────────────────────
Write-Host "[6/10] Deleting CloudWatch log group..." -ForegroundColor Yellow
aws logs delete-log-group --log-group-name /ecs/data-architecture-ai `
    --region $REGION 2>$null | Out-Null
Write-Host "       Done" -ForegroundColor Green

# ── 7. Delete RDS Aurora stack (depends on main VPC — must go first) ─────────
Write-Host "[7/10] Deleting Aurora RDS stack..." -ForegroundColor Yellow
Remove-Stack "ai-rds-aurora"

# ── 8. Delete main stack ──────────────────────────────────────────────────────
Write-Host "[8/10] Deleting main stack ai-analyst-agent-project..." -ForegroundColor Yellow
Remove-Stack "ai-analyst-agent-project"

# ── 9. Delete OIDC role stack ─────────────────────────────────────────────────
Write-Host "[9/10] Deleting OIDC role stack..." -ForegroundColor Yellow
Remove-Stack "github-actions-ai-agent-role"

# ── 10. Delete orphaned IAM roles (left by failed/partial deployments) ───────
Write-Host "[10/10] Removing orphaned IAM roles..." -ForegroundColor Yellow
$orphanRoles = @(
    "github-actions-ai-agent-deploy"
)
# Also find any auto-generated CFN roles for this project
$cfnRoles = aws iam list-roles --query `
    "Roles[?contains(RoleName,'ai-analyst-agent') || contains(RoleName,'AiAgent')].RoleName" `
    --output text 2>$null
if ($cfnRoles) { $orphanRoles += $cfnRoles.Split("`t") }

foreach ($role in ($orphanRoles | Where-Object { $_ -and $_.Trim() -ne "" })) {
    $role = $role.Trim()
    # Detach all managed policies first
    $policies = aws iam list-attached-role-policies --role-name $role `
        --query "AttachedPolicies[*].PolicyArn" --output text 2>$null
    if ($policies) {
        foreach ($arn in $policies.Split("`t")) {
            aws iam detach-role-policy --role-name $role --policy-arn $arn.Trim() 2>$null | Out-Null
        }
    }
    # Delete inline policies
    $inlines = aws iam list-role-policies --role-name $role `
        --query "PolicyNames" --output text 2>$null
    if ($inlines) {
        foreach ($p in $inlines.Split("`t")) {
            aws iam delete-role-policy --role-name $role --policy-name $p.Trim() 2>$null | Out-Null
        }
    }
    aws iam delete-role --role-name $role 2>$null | Out-Null
    Write-Host "       $role : removed" -ForegroundColor DarkGray
}
Write-Host "       Done" -ForegroundColor Green

# ── Remove S3 notification config (keeps bucket + data intact) ────────────────
Write-Host "       Clearing S3 notification config..." -ForegroundColor DarkGray
$emptyNotif = '{"LambdaFunctionConfigurations":[],"TopicConfigurations":[],"QueueConfigurations":[]}'
$tmpFile = "$env:TEMP\empty_notif.json"
[System.IO.File]::WriteAllText($tmpFile, $emptyNotif, [System.Text.Encoding]::ASCII)
aws s3api put-bucket-notification-configuration `
    --bucket "langchain-$ACCOUNT-eu-north-1" `
    --notification-configuration "file://$tmpFile" `
    --region $REGION 2>$null | Out-Null
Remove-Item $tmpFile -ErrorAction SilentlyContinue

# ── Final verification ────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " VERIFICATION" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

function Check-Gone {
    param([string]$Label, [string]$Cmd)
    $result = Invoke-Expression $Cmd 2>$null
    if (-not $result -or $result -match "does not exist|NoSuchEntity|ResourceNotFoundException") {
        Write-Host "  $Label : CLEAN" -ForegroundColor Green
    } else {
        Write-Host "  $Label : still present — check manually" -ForegroundColor Red
        Write-Host "    $result" -ForegroundColor DarkGray
    }
}

Check-Gone "Main stack    " "aws cloudformation describe-stacks --stack-name ai-analyst-agent-project --region $REGION --output text 2>&1"
Check-Gone "OIDC stack    " "aws cloudformation describe-stacks --stack-name github-actions-ai-agent-role --region $REGION --output text 2>&1"
Check-Gone "RDS stack     " "aws cloudformation describe-stacks --stack-name ai-rds-aurora --region $REGION --output text 2>&1"
Check-Gone "Log group     " "aws logs describe-log-groups --log-group-name-prefix /ecs/data-architecture-ai --region $REGION --query 'logGroups[0].logGroupName' --output text 2>&1"
Check-Gone "OIDC IAM role " "aws iam get-role --role-name github-actions-ai-agent-deploy --output text 2>&1"

$bucket = "langchain-$ACCOUNT-eu-north-1"
$bucketExists = aws s3api head-bucket --bucket $bucket --region $REGION 2>$null
Write-Host "  S3 bucket     : KEPT — s3://$bucket (data preserved)" -ForegroundColor Cyan
Write-Host "  GitHub secrets: KEPT — AWS_DEPLOY_ROLE_ARN still set" -ForegroundColor Cyan

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host " READY FOR FRESH DEPLOYMENT" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host " Run .\deploy.ps1 to redeploy everything." -ForegroundColor White
Write-Host ""
