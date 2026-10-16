import json
import os
import psycopg2
from dotenv import load_dotenv

# ── Connection ────────────────────────────────────────────────────────────────
load_dotenv()

conn_params = {
    "dbname":   os.environ["DB_NAME"],
    "user":     os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "host":     os.environ["DB_HOST"],
    "port":     os.environ.get("DB_PORT", "5432"),
}

def populate_companies(json_file_path: str):
    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        cur  = conn.cursor()

        # ── Load FDA JSON ─────────────────────────────────────────────────────
        with open(json_file_path, "r") as f:
            fda_data = json.load(f)

        # Use labeler_name — always present at top level
        manufacturers = list({
            item.get("labeler_name")
            for item in fda_data
            if item.get("labeler_name")
        })

        print(f"Found {len(manufacturers)} unique manufacturers to insert.")

        # ── Insert into companies ─────────────────────────────────────────────
        inserted = 0
        for name in manufacturers:
            cur.execute(
                """
                INSERT INTO project.companies (name)
                VALUES (%s)
                ON CONFLICT DO NOTHING
                RETURNING company_id
                """,
                (name,),
            )
            if cur.fetchone():
                inserted += 1

        conn.commit()

        # ── Verify ────────────────────────────────────────────────────────────
        cur.execute("SELECT COUNT(*) FROM project.companies")
        total = cur.fetchone()[0]

        print(f"✅  Done. Inserted: {inserted} | Total in table: {total}")

    except Exception as e:
        print(f"❌  Error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    populate_companies("fda_data.json")
