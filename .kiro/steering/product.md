# Product

This project demonstrates a **Text-to-SQL** pipeline using Generative AI on AWS. It allows users to query structured datasets using natural language, which is translated into SQL by an LLM and executed against a database.

## Core Capability

- Natural language → SQL query generation via LangChain + Amazon Bedrock
- Two sample datasets: a cars catalog (CSV) and a library catalog (NDJSON)
- Local smoke testing with SQLite; production queries run via Amazon Athena

## Target Use Case

Data exploration and analytics for non-technical users who want to query structured data without writing SQL. The project serves as a reference architecture and lab environment for AI-powered data access on AWS.

## Key Datasets

- `s3_cars_data.csv` — automobile specs (make, price, horsepower, mpg, etc.)
- `s3_library_data.json` — book catalog (title, author, genre, pub_date) in NDJSON format
