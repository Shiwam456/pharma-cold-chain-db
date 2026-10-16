import json
import random
import uuid
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

# ── Constants ─────────────────────────────────────────────────────────────────
UNIT_STATUSES   = ["In Stock", "In Transit", "Delivered", "Quarantined"]
UNIT_STATUS_W   = [0.45,       0.25,         0.25,        0.05]          # weights
BATCH_STATUSES  = ["Active", "Expired", "Recalled"]
BATCH_STATUS_W  = [0.80,      0.12,      0.08]
LOC_TYPES       = ["Warehouse", "Distribution Center", "Cold Storage"]

# ── Helpers ───────────────────────────────────────────────────────────────────
def rand_date(start_days_ago: int, end_days_ago: int = 0) -> datetime:
    delta = random.randint(end_days_ago, start_days_ago)
    return datetime.now() - timedelta(days=delta)

def rand_gps() -> str:
    lat  = round(random.uniform(25.0, 48.0), 6)   # continental US / EU range
    lon  = round(random.uniform(-122.0, 28.0), 6)
    return f"{lat},{lon}"

# ── Main ──────────────────────────────────────────────────────────────────────
def generate_synthetic_data(json_file_path: str):
    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        cur  = conn.cursor()

        # ── 0. Load real FDA product data ─────────────────────────────────────
        with open(json_file_path, "r") as f:
            fda_data = json.load(f)

        product_ndcs: list[str] = [
            item["product_ndc"] for item in fda_data if item.get("product_ndc")
        ]
        cold_chain_ndcs: set[str] = {
            item["product_ndc"]
            for item in fda_data
            if item.get("product_ndc")
            and item.get("openfda", {}).get("route", [""])[0].lower()
               in ("intravenous", "subcutaneous", "injection")  # proxy for cold-chain
        }
        manufacturers: list[str] = list({
            m
            for item in fda_data
            for m in item.get("openfda", {}).get("manufacturer_name", [])
            if m
        })

        print(f"Loaded {len(product_ndcs)} NDCs | "
              f"{len(cold_chain_ndcs)} cold-chain | "
              f"{len(manufacturers)} manufacturers")

        # ── 1. companies ──────────────────────────────────────────────────────
        # Use SERIAL / sequence — let Postgres assign company_id
        company_ids: list[int] = []
        for name in manufacturers[:100]:
            cur.execute(
                """
                INSERT INTO project.companies (name)
                VALUES (%s)
                ON CONFLICT DO NOTHING
                RETURNING company_id
                """,
                (name,),
            )
            row = cur.fetchone()
            if row:
                company_ids.append(row[0])

        # If all rows conflicted (re-run), fetch existing ids
        if not company_ids:
            cur.execute("SELECT company_id FROM project.companies LIMIT 100")
            company_ids = [r[0] for r in cur.fetchall()]

        print(f"  companies      : {len(company_ids)}")

        # ── 2. inventory_locations ────────────────────────────────────────────
        # Must come BEFORE hospitals (hospitals.location_id → inventory_locations)
        location_ids: list[int] = []
        for i in range(1, 31):
            loc_type = random.choice(LOC_TYPES)
            cur.execute(
                """
                INSERT INTO project.inventory_locations
                    (location_id, name, type, gps_coordinates)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING location_id
                """,
                (i, f"{loc_type} {i}", loc_type, rand_gps()),
            )
            row = cur.fetchone()
            location_ids.append(row[0] if row else i)

        print(f"  inv_locations  : {len(location_ids)}")

        # ── 3. hospitals ──────────────────────────────────────────────────────
        hospital_ids: list[int] = []
        city_names = [
            "New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
            "Philadelphia", "San Antonio", "San Diego", "Dallas", "Vienna",
            "Budapest", "Berlin", "Paris", "London", "Madrid", "Rome",
            "Warsaw", "Prague", "Brussels", "Amsterdam", "Zurich", "Lisbon",
            "Athens", "Oslo", "Stockholm", "Helsinki", "Copenhagen", "Dublin",
            "Bratislava", "Ljubljana",
        ]
        for i, city in enumerate(city_names[:50], start=1):
            loc_id = random.choice(location_ids)   # assign nearest hub
            cur.execute(
                """
                INSERT INTO project.hospitals
                    (hospital_id, name, location_id, contact_email, contact_phone)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING hospital_id
                """,
                (
                    i,
                    f"{city} General Hospital",
                    loc_id,
                    f"supply@hospital{i}.org",
                    f"+1-555-{random.randint(100,999)}-{random.randint(1000,9999)}",
                ),
            )
            row = cur.fetchone()
            hospital_ids.append(row[0] if row else i)

        print(f"  hospitals      : {len(hospital_ids)}")

        # ── 4. transit_thresholds ─────────────────────────────────────────────
        # One row per product_ndc — drives alert logic
        for ndc in product_ndcs[:500]:
            is_cold = ndc in cold_chain_ndcs
            cur.execute(
                """
                INSERT INTO project.transit_thresholds
                    (product_ndc, max_transit_hours, requires_cold_chain)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    ndc,
                    random.choice([24, 48, 72, 120]),   # realistic transit windows
                    is_cold,
                ),
            )

        print("  transit_thresholds: done")

        # ── 5. batches ────────────────────────────────────────────────────────
        batch_records: list[dict] = []   # {batch_id, product_ndc, exp_date, status}
        for ndc in product_ndcs[:500]:
            num_batches = random.randint(1, 4)
            for _ in range(num_batches):
                batch_id = f"BATCH-{uuid.uuid4().hex[:8].upper()}"
                status   = random.choices(BATCH_STATUSES, BATCH_STATUS_W)[0]

                if status == "Expired":
                    mfg_date = rand_date(1000, 730)
                    exp_date = mfg_date + timedelta(days=random.randint(180, 720))
                    # ensure exp_date is actually in the past
                    if exp_date > datetime.now():
                        exp_date = datetime.now() - timedelta(days=10)
                else:
                    mfg_date = rand_date(365, 30)
                    exp_date = mfg_date + timedelta(days=random.randint(365, 1095))

                cur.execute(
                    """
                    INSERT INTO project.batches
                        (batch_id, product_ndc, mfg_date, exp_date, status)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (batch_id, ndc, mfg_date.date(), exp_date.date(), status),
                )
                batch_records.append(
                    {"batch_id": batch_id, "product_ndc": ndc,
                     "exp_date": exp_date, "status": status}
                )

        print(f"  batches        : {len(batch_records)}")

        # ── 6. serialized_units + movement_logs ───────────────────────────────
        # Only move Active batches; Expired/Recalled go straight to Quarantined
        serial_count = 0
        movement_count = 0
        alert_serials: list[dict] = []   # collect candidates for alerts

        for br in batch_records:
            units_per_batch = random.randint(5, 20)
            for _ in range(units_per_batch):
                serial = f"SN-{uuid.uuid4().hex[:10].upper()}"
                loc    = random.choice(location_ids)
                hosp   = random.choice(hospital_ids)

                # Status logic
                if br["status"] in ("Expired", "Recalled"):
                    unit_status = "Quarantined"
                else:
                    unit_status = random.choices(UNIT_STATUSES, UNIT_STATUS_W)[0]

                assigned_hosp = hosp if unit_status == "Delivered" else None

                cur.execute(
                    """
                    INSERT INTO project.serialized_units
                        (serial_number, batch_id, current_location_id,
                         assigned_hospital_id, status)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (serial, br["batch_id"], loc, assigned_hosp, unit_status),
                )
                serial_count += 1

                # ── movement log ──────────────────────────────────────────────
                # to_location_id must be an inventory_location (not a hospital)
                to_loc       = random.choice(location_ids)
                departure    = rand_date(60, 1)
                transit_hrs  = random.randint(4, 200)   # some intentionally long
                arrival      = departure + timedelta(hours=transit_hrs)
                expected_arr = departure + timedelta(hours=random.randint(12, 96))
                breached     = arrival > expected_arr   # arrived late?

                cur.execute(
                    """
                    INSERT INTO project.movement_logs
                        (serial_number, from_location_id, to_location_id,
                         departure_time, arrival_time, expected_arrival,
                         alert_triggered)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        serial, loc, to_loc,
                        departure, arrival, expected_arr,
                        breached,
                    ),
                )
                movement_count += 1

                if breached or unit_status == "Quarantined":
                    alert_serials.append(
                        {"serial": serial, "batch_id": br["batch_id"],
                         "breached": breached, "quarantined": unit_status == "Quarantined"}
                    )

        print(f"  serialized_units: {serial_count}")
        print(f"  movement_logs  : {movement_count}")

        # ── 7. hospital_inventory ─────────────────────────────────────────────
        # Aggregate stock: one row per (hospital, batch) pair
        inventory_count = 0
        for hospital_id in hospital_ids:
            # Each hospital carries a random subset of batches
            sample_batches = random.sample(
                batch_records, k=min(len(batch_records), random.randint(20, 60))
            )
            for br in sample_batches:
                quantity  = random.randint(0, 500)
                threshold = random.randint(10, 50)
                cur.execute(
                    """
                    INSERT INTO project.hospital_inventory
                        (hospital_id, batch_id, quantity,
                         low_stock_threshold, last_updated)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        hospital_id,
                        br["batch_id"],
                        quantity,
                        threshold,
                        rand_date(30),
                    ),
                )
                inventory_count += 1

                # Flag low-stock alert candidates
                if quantity < threshold:
                    alert_serials.append(
                        {"serial": None, "batch_id": br["batch_id"],
                         "hospital_id": hospital_id,
                         "breached": False, "quarantined": False,
                         "low_stock": True, "quantity": quantity}
                    )

        print(f"  hospital_inventory: {inventory_count}")

        # ── 8. alerts ─────────────────────────────────────────────────────────
        # Generate realistic alerts from the flagged candidates
        alert_types = {
            "transit_breach": ("Transit Delay",         "Medium"),
            "cold_chain":     ("Cold Chain Violation",  "High"),
            "low_stock":      ("Low Stock",             "Medium"),
            "quarantine":     ("Quarantine Required",   "High"),
            "expiry":         ("Near Expiry",           "Low"),
        }
        alert_count = 0
        # Limit to a realistic number (not one alert per unit)
        sample_alerts = random.sample(alert_serials, k=min(len(alert_serials), 300))

        for a in sample_alerts:
            if a.get("low_stock"):
                atype, severity = alert_types["low_stock"]
                msg = (f"Stock for batch {a['batch_id']} at hospital "
                       f"{a['hospital_id']} is below threshold "
                       f"({a['quantity']} units remaining).")
                hosp_id = a["hospital_id"]
                serial  = None
            elif a.get("quarantined"):
                atype, severity = alert_types["quarantine"]
                msg     = f"Unit {a['serial']} from batch {a['batch_id']} quarantined."
                hosp_id = random.choice(hospital_ids)
                serial  = a["serial"]
            elif a.get("breached"):
                atype, severity = alert_types["transit_breach"]
                msg     = f"Unit {a['serial']} exceeded expected transit time."
                hosp_id = random.choice(hospital_ids)
                serial  = a["serial"]
            else:
                continue

            is_resolved  = random.random() < 0.4
            triggered_at = rand_date(60, 1)
            resolved_at  = (triggered_at + timedelta(hours=random.randint(1, 72))
                            if is_resolved else None)

            cur.execute(
                """
                INSERT INTO project.alerts
                    (alert_type, severity, serial_number, hospital_id,
                     batch_id, message, triggered_at, resolved_at, is_resolved)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    atype, severity, serial, hosp_id,
                    a["batch_id"], msg,
                    triggered_at, resolved_at, is_resolved,
                ),
            )
            alert_count += 1

        print(f"  alerts         : {alert_count}")

        # ── Commit everything ─────────────────────────────────────────────────
        conn.commit()
        print("\n✅  All synthetic data committed successfully.")

    except Exception as e:
        print(f"\n❌  Error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    generate_synthetic_data("fda_data.json")
