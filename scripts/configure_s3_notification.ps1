# Configure S3 event notification to trigger the crawler Lambda.
# Only needed when the S3 bucket existed before the stack was deployed
# (CreatePrimaryDataBucket=false). For buckets created by the stack,
# the notification is wired automatically by CloudFormation.
#
# Usage: .\scripts\configure_s3_notification.ps1

$ErrorActionPreference = "Stop"

$REGION     = if ($env:AWS_REGION)   { $env:AWS_REGION }   else { "eu-north-1" }
$STACK_NAME = if ($env:STACK_NAME)   { $env:STACK_NAME }   else { "ai-analyst-agent-project" }

Write-Host "Resolving stack outputs from: $STACK_NAME" -ForegroundColor Yellow

$LAMBDA_ARN = aws cloudformation describe-stacks `
    --stack-name $STACK_NAME `
    --region $REGION `
    --query "Stacks[0].Outputs[?OutputKey=='CrawlerTriggerLambdaArn'].OutputValue" `
    --output text

$BUCKET_NAME = aws cloudformation describe-stacks `
    --stack-name $STACK_NAME `
    --region $REGION `
    --query "Stacks[0].Outputs[?OutputKey=='ProjectfilesBucketName'].OutputValue" `
    --output text

if (-not $LAMBDA_ARN -or $LAMBDA_ARN -eq "None") {
    Write-Host "ERROR: Could not resolve CrawlerTriggerLambdaArn from stack outputs." -ForegroundColor Red
    Write-Host "Deploy the stack first: .\deploy.ps1" -ForegroundColor Red
    exit 1
}

if (-not $BUCKET_NAME -or $BUCKET_NAME -eq "None") {
    Write-Host "ERROR: Could not resolve ProjectfilesBucketName from stack outputs." -ForegroundColor Red
    exit 1
}

Write-Host "Bucket : $BUCKET_NAME"
Write-Host "Lambda : $LAMBDA_ARN"
Write-Host ""

$NOTIFICATION_CONFIG = @"
{
  "LambdaFunctionConfigurations": [
    {
      "Id": "S3CrawlerTrigger",
      "LambdaFunctionArn": "$LAMBDA_ARN",
      "Events": ["s3:ObjectCreated:*"]
    }
  ]
}
"@

# Write to a temp file to avoid inline quoting issues with aws cli
$TMP = [System.IO.Path]::GetTempFileName() + ".json"
$NOTIFICATION_CONFIG | Set-Content -Path $TMP -Encoding UTF8

Write-Host "Applying S3 event notification..." -ForegroundColor Yellow
aws s3api put-bucket-notification-configuration `
    --bucket $BUCKET_NAME `
    --notification-configuration "file://$TMP" `
    --region $REGION

Remove-Item $TMP -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "S3 notification configured." -ForegroundColor Green
Write-Host "Any file upload to s3://$BUCKET_NAME/ will now trigger the crawler Lambda." -ForegroundColor Cyan
