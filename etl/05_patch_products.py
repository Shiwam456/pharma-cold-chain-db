import json
import random
from datetime import datetime, timedelta
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

# ── Realistic pharmaceutical class values ─────────────────────────────────────
PHARM_CLASSES = [
    "Analgesic",
    "Antibiotic",
    "Antifungal",
    "Antiviral",
    "Anticoagulant",
    "Antidiabetic",
    "Antihypertensive",
    "Antidepressant",
    "Antipsychotic",
    "Antihistamine",
    "Bronchodilator",
    "Corticosteroid",
    "Diuretic",
    "Immunosuppressant",
    "Proton Pump Inhibitor",
    "Statin",
    "Muscle Relaxant",
    "Anticonvulsant",
    "Antiemetic",
    "Thyroid Agent",
]

# Products with these routes are cold-chain candidates
COLD_CHAIN_ROUTES = {"intravenous", "subcutaneous", "injection", "implant"}


def patch_products(json_file_path: str):
    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        cur  = conn.cursor()

        # ── Load FDA JSON ─────────────────────────────────────────────────────
        with open(json_file_path, "r") as f:
            fda_data = json.load(f)

        # Build a lookup: manufacturer_name → product_ndc list + route info
        ndc_info: dict[str, dict] = {}
        for item in fda_data:
            ndc = item.get("product_ndc")
            if not ndc:
                continue
            openfda    = item.get("openfda", {})
            mfr_names  = openfda.get("manufacturer_name", [])
            routes     = [r.lower() for r in openfda.get("route", [])]
            pharm_list = openfda.get("pharm_class_epc", [])   # FDA pharm class field

            ndc_info[ndc] = {
                "manufacturer": mfr_names[0] if mfr_names else None,
                "is_cold_chain": any(r in COLD_CHAIN_ROUTES for r in routes),
                "fda_pharm_class": pharm_list[0] if pharm_list else None,
            }

        print(f"Loaded info for {len(ndc_info)} NDCs from JSON.")

        # ── Fetch company name → id map from DB ───────────────────────────────
        cur.execute("SELECT company_id, name FROM project.companies")
        company_map: dict[str, int] = {name: cid for cid, name in cur.fetchall()}
        print(f"Found {len(company_map)} companies in DB.")

        # ── Fetch all product NDCs currently in the products table ────────────
        cur.execute("SELECT product_ndc FROM project.products")
        existing_ndcs = [row[0] for row in cur.fetchall()]
        print(f"Products to patch: {len(existing_ndcs)}")

        # ── Patch each product ────────────────────────────────────────────────
        updated   = 0
        no_match  = 0

        for ndc in existing_ndcs:
            info = ndc_info.get(ndc, {})

            # company_id — exact name match
            mfr        = info.get("manufacturer")
            company_id = company_map.get(mfr)   # None if not found

            # requires_cold_chain — from route data, else random (10% chance)
            is_cold = info.get("is_cold_chain", random.random() < 0.10)

            # pharm_class — prefer FDA field, fall back to synthetic
            fda_pc     = info.get("fda_pharm_class")
            pharm_class = (
                fda_pc.split("[")[0].strip()   # FDA strings can be long; trim codes
                if fda_pc
                else random.choice(PHARM_CLASSES)
            )

            # start_date — random approval date between 5 and 30 years ago
            start_date = datetime.now() - timedelta(
                days=random.randint(365 * 5, 365 * 30)
            )

            # expiry_date — product line expiry (not batch expiry)
            # active products: 5–15 years from now; some already discontinued
            discontinued = random.random() < 0.08   # 8% discontinued
            if discontinued:
                expiry_date = datetime.now() - timedelta(days=random.randint(30, 730))
            else:
                expiry_date = datetime.now() + timedelta(
                    days=random.randint(365 * 5, 365 * 15)
                )

            cur.execute(
                """
                UPDATE project.products
                SET
                    company_id          = COALESCE(%s, company_id),
                    requires_cold_chain = %s,
                    pharm_class         = %s,
                    start_date          = %s,
                    expiry_date         = %s
                WHERE product_ndc = %s
                """,
                (
                    company_id,
                    is_cold,
                    pharm_class,
                    start_date.date(),
                    expiry_date.date(),
                    ndc,
                ),
            )

            if company_id:
                updated += 1
            else:
                no_match += 1

        conn.commit()

        print(f"\n✅  Patch complete.")
        print(f"   company_id matched : {updated}")
        print(f"   company_id missing : {no_match}  "
              f"(product kept its old value — manufacturer not in companies table)")

    except Exception as e:
        print(f"\n❌  Error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    patch_products("fda_data.json")
