import json
import os
import psycopg2
from dotenv import load_dotenv

# Connection settings come from environment variables (see .env.example)
load_dotenv()

DB_CONFIG = {
    "dbname":   os.environ["DB_NAME"],
    "user":     os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "host":     os.environ["DB_HOST"],
    "port":     os.environ.get("DB_PORT", "5432"),
}
def load_to_staging(file_path):
    try:
        # Connect to the CEU SQL server
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Load the local JSON file
        with open(file_path, 'r') as f:
            raw_data = json.load(f)

        print(f"Starting upload of {len(raw_data)} records...")

        for entry in raw_data:
            # Insert the entire object into the JSONB column for processing later
            cur.execute(
                "INSERT INTO project.staging_fda_raw (json_data) VALUES (%s)",
                [json.dumps(entry)]
            )

        conn.commit()
        print("Success: Data loaded into project.staging_fda_raw.")

    except Exception as e:
        print(f"Error during staging: {e}")
    finally:
        # Only try to close if 'conn' was actually created
        if 'conn' in locals() and conn is not None:
            cur.close()
            conn.close()
if __name__ == "__main__":
    load_to_staging('fda_data.json')