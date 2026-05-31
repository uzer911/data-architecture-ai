#!/usr/bin/env python3
"""Load sample data (library + cars) into Aurora Serverless v2 via pymysql.

This script connects to the Aurora cluster using credentials from Secrets Manager,
creates tables, and loads data from the local data/ directory.

Usage:
    PYTHONPATH=src python3 scripts/load_rds_data.py

Requires: pymysql, boto3
"""
import csv
import json
import os
import sys

import boto3
import pymysql

REGION = os.environ.get("AWS_REGION", "eu-north-1")
SECRET_NAME = os.environ.get("RDS_SECRET", "cgs-ai-rds-aurora/aurora-credentials")
DATABASE = os.environ.get("RDS_DATABASE", "analyst_db")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
LIBRARY_FILE = os.path.join(DATA_DIR, "s3_library_data.json")
CARS_FILE = os.path.join(DATA_DIR, "s3_cars_data.csv")


def get_credentials(secret_name: str, region: str) -> dict:
    """Fetch database credentials from Secrets Manager."""
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])


def connect(creds: dict, database: str) -> pymysql.Connection:
    """Create a pymysql connection using Secrets Manager credentials."""
    return pymysql.connect(
        host=creds["host"],
        port=int(creds.get("port", 3306)),
        user=creds["username"],
        password=creds["password"],
        database=database,
        charset="utf8mb4",
        connect_timeout=30,
    )


def create_tables(conn: pymysql.Connection):
    """Create library and cars tables if they don't exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS library (
                book_id INT PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                author VARCHAR(300) NOT NULL,
                genre VARCHAR(200),
                pub_date DATE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cars (
                id INT PRIMARY KEY,
                make VARCHAR(50) NOT NULL,
                doors VARCHAR(10),
                body_style VARCHAR(50),
                drive VARCHAR(10),
                curb_weight INT,
                cylinders VARCHAR(20),
                horsepower INT,
                mpg INT,
                price DECIMAL(10,2)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    conn.commit()
    print("✓ Tables created (library, cars)")


def load_library(conn: pymysql.Connection):
    """Load library data from JSON lines file."""
    if not os.path.exists(LIBRARY_FILE):
        print(f"⚠️  Library file not found: {LIBRARY_FILE}")
        return

    records = []
    with open(LIBRARY_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE library")
        sql = "INSERT INTO library (book_id, title, author, genre, pub_date) VALUES (%s, %s, %s, %s, %s)"
        batch = []
        for r in records:
            pub_date = r.get("pub_date", "")[:10] if r.get("pub_date") else None
            batch.append((
                r["book_id"],
                r["title"][:500],
                r["author"][:300],
                (r.get("genre") or "")[:200],
                pub_date,
            ))
            if len(batch) >= 500:
                cur.executemany(sql, batch)
                batch = []
        if batch:
            cur.executemany(sql, batch)
    conn.commit()
    print(f"✓ Loaded {len(records)} library records")


def load_cars(conn: pymysql.Connection):
    """Load cars data from CSV file."""
    if not os.path.exists(CARS_FILE):
        print(f"⚠️  Cars file not found: {CARS_FILE}")
        return

    records = []
    with open(CARS_FILE, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE cars")
        sql = """INSERT INTO cars (id, make, doors, body_style, drive, curb_weight,
                 cylinders, horsepower, mpg, price) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        batch = []
        for r in records:
            batch.append((
                int(r["id"]),
                r["make"],
                r.get("doors", ""),
                r.get("body_style", ""),
                r.get("drive", ""),
                int(r["curb_weight"]) if r.get("curb_weight") else None,
                r.get("cylinders", ""),
                int(r["horsepower"]) if r.get("horsepower") else None,
                int(r["mpg"]) if r.get("mpg") else None,
                float(r["price"]) if r.get("price") else None,
            ))
            if len(batch) >= 500:
                cur.executemany(sql, batch)
                batch = []
        if batch:
            cur.executemany(sql, batch)
    conn.commit()
    print(f"✓ Loaded {len(records)} cars records")


def main():
    print("=" * 50)
    print("Loading sample data into Aurora Serverless v2")
    print("=" * 50)
    print(f"  Secret: {SECRET_NAME}")
    print(f"  Database: {DATABASE}")
    print(f"  Region: {REGION}")
    print()

    print("Fetching credentials from Secrets Manager...")
    creds = get_credentials(SECRET_NAME, REGION)
    print(f"  Host: {creds['host']}")
    print()

    print("Connecting to Aurora...")
    conn = connect(creds, DATABASE)
    print("✓ Connected")
    print()

    try:
        create_tables(conn)
        print()
        load_library(conn)
        load_cars(conn)
        print()

        # Verify
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM library")
            lib_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM cars")
            cars_count = cur.fetchone()[0]
        print("=" * 50)
        print(f"✅ Data loaded successfully!")
        print(f"   library: {lib_count} rows")
        print(f"   cars:    {cars_count} rows")
        print("=" * 50)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
