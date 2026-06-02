#!/usr/bin/env bash
set -euo pipefail

echo "Setting up virtualenv and installing dependencies..."
python -m venv .venv || true
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

printf "Setup complete.\nVirtual environment: .venv\nActivate with: source .venv/bin/activate\n"

# Upload data to S3 staging bucket
# BUCKET=langchain-471613014056-eu-north-1
# aws s3 cp data/s3_library_data.json s3://$BUCKET/library-data/
# aws s3 cp data/s3_cars_data_normalized.csv s3://$BUCKET/cars-data/
