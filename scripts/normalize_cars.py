import os
import pandas as pd

# Resolve paths relative to the project root (one level up from scripts/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
CSV = os.path.join(DATA_DIR, 's3_cars_data.csv')
OUTPUT_CSV = os.path.join(DATA_DIR, 's3_cars_data_normalized.csv')


def normalize(input_path: str = CSV, output_path: str = OUTPUT_CSV) -> pd.DataFrame:
    """Normalize the cars CSV: map word numbers to integers, coerce numeric columns,
    and drop rows missing critical values.

    Args:
        input_path: Path to the raw cars CSV file.
        output_path: Path to write the normalized CSV file.

    Returns:
        Normalized DataFrame.

    Raises:
        FileNotFoundError: If input_path does not exist.
        ValueError: If required columns are missing from the CSV.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    df = pd.read_csv(input_path)

    required_cols = {'doors', 'cylinders', 'horsepower', 'price'}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    # Map written-out numbers to integers for doors and cylinders
    word_map = {
        'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
        'ten': 10, 'twelve': 12,
    }
    doors_raw = df['doors'].astype(str).str.lower()
    cylinders_raw = df['cylinders'].astype(str).str.lower()
    df['doors'] = doors_raw.map(word_map).fillna(doors_raw)
    df['cylinders'] = cylinders_raw.map(word_map).fillna(cylinders_raw)

    # Coerce numeric types; non-parseable values become NaN
    numeric_cols = ['doors', 'curb_weight', 'cylinders', 'horsepower', 'mpg', 'price']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    rows_before = len(df)
    df = df.dropna(subset=['horsepower', 'price'])
    rows_dropped = rows_before - len(df)
    if rows_dropped:
        print(f"Dropped {rows_dropped} row(s) with missing horsepower or price.")

    df.to_csv(output_path, index=False)
    print(f"Wrote {len(df)} rows to {output_path}")
    return df


if __name__ == '__main__':
    normalize()
