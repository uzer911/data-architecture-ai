# Tech Stack

## Language & Runtime
- Python 3.x
- Jupyter Notebook (`.ipynb`) for interactive exploration

## Key Libraries
| Library | Purpose |
|---|---|
| `langchain` + `langchain-aws` | LLM orchestration and Text-to-SQL chain |
| `boto3` | AWS SDK — Bedrock, S3, and other AWS service calls |
| `pyathena` | Amazon Athena query execution via Python |
| `sqlalchemy` | Database abstraction layer |
| `pandas` | Data loading, normalization, and transformation |
| `requests` | HTTP utility |

## AI / AWS Services
- **Amazon Bedrock** — LLM inference (model invoked via LangChain)
- **Amazon Athena** — Serverless SQL query execution over S3 data
- **AWS S3** — Data lake storage for CSV and JSON datasets
- **AWS CloudFormation** — Infrastructure provisioning (IAM roles, Lambda, EventBridge)

## Infrastructure
- Template: `cloudformation-template-validated.yml`
- Requires `CAPABILITY_IAM` (creates IAM roles and policies)
- Stack name: `gbl-ai-project-monitoring-stack`
- Parameters: `AiProjectPoolId`, `AiProjectRegions`

## Common Commands

### Environment Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Or use the helper script:
```bash
./setup.sh
```

### Smoke Test (local, no AWS calls)
```bash
python run_smoke.py
```

### Data Normalization
```bash
python scripts/normalize_cars.py
```
Produces `s3_cars_data_normalized.csv`.

### Deploy to AWS (CloudFormation change set)
```bash
./deploy-changeset.sh "<pool-id>" "<region1,region2>"
# Example:
./deploy-changeset.sh "my-pool-id" "eu-north-1,eu-central-1"
```

### Validate CloudFormation Template
```bash
aws cloudformation validate-template \
  --template-body file://cloudformation-template-validated.yml \
  --region "$AWS_REGION"
```

## AWS Credentials
Configure before running any AWS-dependent code:
```bash
aws configure
# or set environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
```
