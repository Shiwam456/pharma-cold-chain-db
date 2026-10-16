-- Schema for the pharma cold-chain tracking database (PostgreSQL).
-- NOTE: reconstructed from the ER diagram (docs/er_diagram.png). Data types and
-- constraints are best-effort; replace with a DDL export from your own database
-- (DBeaver: right-click schema > Generate SQL > DDL) if you need exact fidelity.

CREATE SCHEMA IF NOT EXISTS project;
SET search_path TO project;

CREATE TABLE staging_fda_raw (
    id        SERIAL PRIMARY KEY,
    json_data JSONB NOT NULL
);

CREATE TABLE companies (
    company_id SERIAL PRIMARY KEY,
    name       TEXT UNIQUE NOT NULL
);

CREATE TABLE products (
    product_ndc         TEXT PRIMARY KEY,
    brand_name          TEXT,
    generic_name        TEXT,
    dosage_form         TEXT,
    requires_cold_chain BOOLEAN DEFAULT FALSE,
    company_id          INT REFERENCES companies(company_id),
    marketing_category  TEXT,
    manufacturer        TEXT,
    start_date          DATE,
    expiry_date         DATE,
    pharm_class         TEXT
);

CREATE TABLE transit_thresholds (
    threshold_id        SERIAL PRIMARY KEY,
    product_ndc         TEXT UNIQUE REFERENCES products(product_ndc),
    max_transit_hours   INT,
    requires_cold_chain BOOLEAN
);

CREATE TABLE batches (
    batch_id    TEXT PRIMARY KEY,
    product_ndc TEXT REFERENCES products(product_ndc),
    mfg_date    DATE,
    exp_date    DATE,
    status      TEXT            -- Active | Expired | Recalled
);

CREATE TABLE inventory_locations (
    location_id     INT PRIMARY KEY,
    name            TEXT,
    type            TEXT,       -- Warehouse | Distribution Center | Cold Storage
    gps_coordinates TEXT
);

CREATE TABLE hospitals (
    hospital_id   INT PRIMARY KEY,
    name          TEXT,
    location_id   INT REFERENCES inventory_locations(location_id),
    contact_email TEXT,
    contact_phone TEXT
);

CREATE TABLE serialized_units (
    serial_number        TEXT PRIMARY KEY,
    batch_id             TEXT REFERENCES batches(batch_id),
    current_location_id  INT REFERENCES inventory_locations(location_id),
    assigned_hospital_id INT REFERENCES hospitals(hospital_id),
    status               TEXT   -- In Stock | In Transit | Delivered | Quarantined
);

CREATE TABLE movement_logs (
    log_id           SERIAL PRIMARY KEY,
    serial_number    TEXT REFERENCES serialized_units(serial_number),
    from_location_id INT REFERENCES inventory_locations(location_id),
    to_location_id   INT REFERENCES inventory_locations(location_id),
    departure_time   TIMESTAMP,
    arrival_time     TIMESTAMP,
    expected_arrival TIMESTAMP,
    alert_triggered  BOOLEAN DEFAULT FALSE
);

CREATE TABLE transport_vehicles (
    vehicle_id            SERIAL PRIMARY KEY,
    type                  TEXT,
    cooling_supported     BOOLEAN,
    last_maintenance_date DATE,
    vehicle_age           INT
);

CREATE TABLE shipments (
    shipment_id             SERIAL PRIMARY KEY,
    origin_location_id      INT REFERENCES inventory_locations(location_id),
    destination_location_id INT REFERENCES inventory_locations(location_id),
    vehicle_id              INT REFERENCES transport_vehicles(vehicle_id),
    departure_time          TIMESTAMP,
    arrival_time            TIMESTAMP,
    status                  TEXT
);

CREATE TABLE shipment_items (
    shipment_id   INT REFERENCES shipments(shipment_id),
    serial_number TEXT REFERENCES serialized_units(serial_number),
    PRIMARY KEY (shipment_id, serial_number)
);

CREATE TABLE transport_events (
    transport_id     SERIAL PRIMARY KEY,
    serial_number    TEXT REFERENCES serialized_units(serial_number),
    shipment_id      INT REFERENCES shipments(shipment_id),
    from_location_id INT REFERENCES inventory_locations(location_id),
    to_location_id   INT REFERENCES inventory_locations(location_id),
    departure_time   TIMESTAMP,
    arrival_time     TIMESTAMP,
    expected_arrival TIMESTAMP,
    status           TEXT,
    log_id           INT REFERENCES movement_logs(log_id)
);

CREATE TABLE transport_conditions (
    condition_id   SERIAL PRIMARY KEY,
    transport_id   INT REFERENCES transport_events(transport_id),
    temperature    NUMERIC,
    humidity       NUMERIC,
    is_refrigerated BOOLEAN,
    recorded_at    TIMESTAMP
);

CREATE TABLE hospital_inventory (
    inventory_id        SERIAL PRIMARY KEY,
    hospital_id         INT REFERENCES hospitals(hospital_id),
    batch_id            TEXT REFERENCES batches(batch_id),
    quantity            INT,
    low_stock_threshold INT,
    last_updated        TIMESTAMP
);

CREATE TABLE inventory_transactions (
    transaction_id   SERIAL PRIMARY KEY,
    hospital_id      INT REFERENCES hospitals(hospital_id),
    batch_id         TEXT REFERENCES batches(batch_id),
    serial_number    TEXT REFERENCES serialized_units(serial_number),
    transaction_type TEXT,
    quantity         INT,
    source_type      TEXT,
    reference_id     INT,
    created_at       TIMESTAMP
);

CREATE TABLE demand_logs (
    log_id        SERIAL PRIMARY KEY,
    hospital_id   INT REFERENCES hospitals(hospital_id),
    product_ndc   TEXT REFERENCES products(product_ndc),
    quantity_used INT,
    recorded_at   TIMESTAMP
);

CREATE TABLE alerts (
    alert_id             SERIAL PRIMARY KEY,
    alert_type           TEXT,
    severity             TEXT,
    serial_number        TEXT REFERENCES serialized_units(serial_number),
    hospital_id          INT REFERENCES hospitals(hospital_id),
    batch_id             TEXT REFERENCES batches(batch_id),
    message              TEXT,
    triggered_at         TIMESTAMP,
    resolved_at          TIMESTAMP,
    is_resolved          BOOLEAN DEFAULT FALSE,
    related_transport_id INT REFERENCES transport_events(transport_id),
    alert_source         TEXT
);
