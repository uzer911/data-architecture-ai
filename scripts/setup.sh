#!/usr/bin/env bash
set -euo pipefail

echo "Setting up virtualenv and installing dependencies..."
python -m venv .venv || true
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

printf "Setup complete.\nVirtual environment: .venv\nActivate with: source .venv/bin/activate\n"

# Optional: copy data to an S3 staging bucket (uncomment and set BUCKET)
# BUCKET=my-project-bucket
# aws s3 cp data/s3_library_data.json s3://$BUCKET/library-data/
# aws s3 cp data/s3_cars_data.csv s3://$BUCKET/cars-data/
