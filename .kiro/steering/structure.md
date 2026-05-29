# Project Structure

```
DataArchitectureWithAi/
├── mda_text_to_sql_langchain_bedrock.ipynb  # Main notebook: Text-to-SQL demo with LangChain + Bedrock
├── run_smoke.py                              # Local smoke test (no AWS calls, uses SQLite)
├── requirements.txt                          # Python dependencies
├── setup.sh                                  # Virtualenv setup + optional S3 upload
├── deploy-changeset.sh                       # CloudFormation change set deployment script
├── cloudformation-template-validated.yml     # IaC template (IAM, Lambda, EventBridge)
│
├── s3_cars_data.csv                          # Raw cars dataset
├── s3_library_data.json                      # Raw library dataset (NDJSON format)
│
├── schema/
│   ├── cars_schema.json                      # JSON Schema (draft-07) for cars data
│   └── library_schema.json                   # JSON Schema (draft-07) for library data
│
└── scripts/
    └── normalize_cars.py                     # Standalone CSV normalization script
```

## Conventions

### Data Files
- Raw data files are prefixed with `s3_` to indicate they are intended for S3 storage
- Normalized outputs drop the `s3_` prefix and add `_normalized` (e.g., `s3_cars_data_normalized.csv`)
- Library data uses NDJSON (newline-delimited JSON); load with `pd.read_json(..., lines=True)`

### Schemas
- All dataset schemas live in `schema/` as JSON Schema draft-07 files
- Schema filenames match their dataset: `cars_schema.json` ↔ `s3_cars_data.csv`
- Required fields are declared explicitly in the `required` array

### Scripts
- Standalone utility scripts go in `scripts/`
- Scripts should be runnable directly (`if __name__ == '__main__'`) and operate on paths relative to the project root

### Infrastructure
- All CloudFormation changes must go through a change set — never apply directly
- Always validate the template before creating a change set
- Tag every deployment with `DeployedBy`, `DeploymentDate`, and `Environment`

### Testing
- `run_smoke.py` is the local test entry point — keep it free of AWS/Bedrock dependencies
- Smoke tests use in-memory SQLite to mirror the Athena query patterns
- Run smoke tests before any deployment to verify data loading and normalization
