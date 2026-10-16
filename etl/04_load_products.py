import json
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn_params = {
    "dbname":   os.environ["DB_NAME"],
    "user":     os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "host":     os.environ["DB_HOST"],
    "port":     os.environ.get("DB_PORT", "5432"),
}

def format_fda_date(date_str):
    if date_str and len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return None

def get_first_or_none(data_list):
    if isinstance(data_list, list) and len(data_list) > 0:
        return data_list[0]
    return None

def populate_schema(json_file_path):
    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        cur = conn.cursor()
        print("Connected to PostgreSQL successfully.")

        with open(json_file_path, 'r') as f:
            data = json.load(f)

        for entry in data:
            # Mapping JSON to your specific diagram columns
            product_ndc = entry.get('product_ndc')
            brand_name = entry.get('brand_name')
            generic_name = entry.get('generic_name')
            dosage_form = entry.get('dosage_form')
            marketing_category = entry.get('marketing_category')
            
            # Extract manufacturer from openfda
            openfda = entry.get('openfda', {})
            manufacturer = get_first_or_none(openfda.get('manufacturer_name'))

            # --- INSERT INTO project.products ---
            # Using product_ndc as the conflict target based on your diagram
            cur.execute("""
                INSERT INTO project.products (
                    product_ndc, brand_name, generic_name, 
                    dosage_form, marketing_category, manufacturer
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (product_ndc) DO NOTHING;
            """, (
                product_ndc, brand_name, generic_name, 
                dosage_form, marketing_category, manufacturer
            ))

        conn.commit()
        print(f"Migration complete. Processed {len(data)} product records.")

    except Exception as e:
        print(f"An error occurred: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            cur.close()
            conn.close()

if __name__ == "__main__":
    populate_schema('fda_data.json')
