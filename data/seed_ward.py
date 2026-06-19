"""
seed_ward.py — reads ward CSV, populates ward.db, then generates
2024 + 2025 monthly data for every ward found in the CSV.

Usage:
  Place your CSV at data/ward_data.csv  (or pass path as argument)
  python3 data/seed_ward.py
  python3 data/seed_ward.py /path/to/custom.csv
"""

import sqlite3, os, csv, random, sys
from datetime import datetime

BASE = os.path.dirname(__file__)
DB   = os.path.join(BASE, "ward.db")

# ── Accept optional CSV path argument ─────────────────────────────────────────
CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "ward_data.csv")

if not os.path.exists(CSV_PATH):
    print(f"⚠  CSV not found at: {CSV_PATH}")
    print("   Place your CSV at data/ward_data.csv and re-run.")
    print("   Expected columns: Year,Month,Ward_NO,Ward_Name,Building_Area_km2,")
    print("   Builtup_Area_Percentage,Population,Rainfall,RH2M,T2M_MAX,T2M_MIN,WS2M,GWL")
    sys.exit(1)

# ── Create / reset DB ──────────────────────────────────────────────────────────
con = sqlite3.connect(DB)
con.executescript("""
CREATE TABLE IF NOT EXISTS ward_data (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    year                    INTEGER,
    month                   INTEGER,
    ward_no                 INTEGER,
    ward_name               TEXT,
    building_area_km2       REAL,
    builtup_area_percentage REAL,
    population              INTEGER,
    rainfall                REAL,
    rh2m                    REAL,
    t2m_max                 REAL,
    t2m_min                 REAL,
    ws2m                    REAL,
    gwl                     REAL
);
CREATE INDEX IF NOT EXISTS idx_ward_year_month ON ward_data(year, month, ward_no);
CREATE INDEX IF NOT EXISTS idx_ward_name       ON ward_data(ward_name);
""")

# Wipe before re-seeding to avoid duplicates
con.execute("DELETE FROM ward_data")
con.commit()

# ── Step 1: Read and import CSV ────────────────────────────────────────────────
def safe_float(val):
    try:
        return float(val) if val.strip() != "" else None
    except (ValueError, AttributeError):
        return None

def safe_int(val):
    try:
        return int(float(val)) if val.strip() != "" else None
    except (ValueError, AttributeError):
        return None

csv_rows = []
with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    # Normalise header names — strip spaces, lowercase
    reader.fieldnames = [h.strip() for h in reader.fieldnames]

    for row in reader:
        # Map both capitalised and lowercase column names
        r = {k.strip().lower(): v.strip() for k, v in row.items()}
        csv_rows.append((
            safe_int  (r.get("year")),
            safe_int  (r.get("month")),
            safe_int  (r.get("ward_no")),
            r.get     ("ward_name", "").lower().strip(),
            safe_float(r.get("building_area_km2")),
            safe_float(r.get("builtup_area_percentage")),
            safe_int  (r.get("population")),
            safe_float(r.get("rainfall")),
            safe_float(r.get("rh2m")),
            safe_float(r.get("t2m_max")),
            safe_float(r.get("t2m_min")),
            safe_float(r.get("ws2m")),
            safe_float(r.get("gwl")),
        ))

con.executemany("""
    INSERT INTO ward_data
    (year,month,ward_no,ward_name,building_area_km2,builtup_area_percentage,
     population,rainfall,rh2m,t2m_max,t2m_min,ws2m,gwl)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
""", csv_rows)
con.commit()
print(f"✓ Imported {len(csv_rows)} rows from CSV")

# ── Step 2: Build a baseline per ward from CSV data ───────────────────────────
# Group rows by ward — compute averages to use as generation baseline
ward_baselines = {}
for row in csv_rows:
    year, month, ward_no, ward_name = row[0], row[1], row[2], row[3]
    if not ward_name or ward_no is None:
        continue
    key = ward_no
    if key not in ward_baselines:
        ward_baselines[key] = {
            "ward_no":   ward_no,
            "ward_name": ward_name,
            "building_area_km2":       [],
            "builtup_area_percentage": [],
            "population":              [],
            "gwl":                     [],
            "ws2m":                    [],
            "rh2m":                    [],
            "t2m_max":                 [],
            "t2m_min":                 [],
            "rainfall":                [],
        }
    b = ward_baselines[key]
    for field, idx in [("building_area_km2",4),("builtup_area_percentage",5),
                       ("population",6),("rainfall",7),("rh2m",8),
                       ("t2m_max",9),("t2m_min",10),("ws2m",11),("gwl",12)]:
        if row[idx] is not None:
            b[field].append(row[idx])

def avg(lst, default=0.0):
    return sum(lst) / len(lst) if lst else default

baselines = {}
for ward_no, b in ward_baselines.items():
    baselines[ward_no] = {
        "ward_no":                 b["ward_no"],
        "ward_name":               b["ward_name"],
        "building_area_km2":       avg(b["building_area_km2"]),
        "builtup_area_percentage": avg(b["builtup_area_percentage"]),
        "population":              int(avg(b["population"])),
        "gwl":                     avg(b["gwl"]),
        "ws2m":                    avg(b["ws2m"]),
    }

print(f"✓ Built baselines for {len(baselines)} wards")

# ── Step 3: Monthly seasonal patterns (Bangalore) ─────────────────────────────
RAINFALL_PATTERN = {
     1: 2.1,  2: 4.3,  3: 9.8,  4:38.5,
     5:97.2,  6:112.4, 7:88.3,  8:89.6,
     9:127.4,10:95.2, 11:35.6, 12: 5.8
}
T2M_MAX_PATTERN = {
     1:32.1, 2:34.2, 3:35.8, 4:34.5,
     5:33.1, 6:29.4, 7:28.6, 8:28.9,
     9:29.8,10:28.7,11:28.2,12:29.1
}
T2M_MIN_PATTERN = {
     1:15.2, 2:16.8, 3:19.4, 4:21.2,
     5:21.8, 6:20.1, 7:19.6, 8:19.8,
     9:19.9,10:19.2,11:17.4,12:15.6
}
RH2M_PATTERN = {
     1:62.1, 2:58.3, 3:55.4, 4:62.1,
     5:70.2, 6:82.4, 7:85.6, 8:84.3,
     9:83.1,10:79.4,11:72.3,12:65.2
}

# ── Step 4: Generate 2024 + 2025 for every ward ───────────────────────────────
# Growth assumptions applied from CSV base year (assumed 2016) → 2024/2025:
#   Population:           +1.8% / year  (Bangalore urban growth)
#   Builtup area %:       +0.4% / year  (densification)
#   Building area km2:    unchanged     (ward boundary fixed)
#   GWL:                  -0.5 m / year (groundwater depletion)
#   T2M_MAX/MIN:          +0.15°C/year  (urban heat island)
#   RH2M:                 -0.1 / year
#   WS2M:                 stable ± noise

random.seed(42)
rows_generated = 0

# Detect base year from CSV
base_year = min(r[0] for r in csv_rows if r[0]) if csv_rows else 2016

for ward_no, b in baselines.items():
    for year in [2024, 2025]:
        years_delta = year - base_year

        pop     = int(b["population"] * (1.018 ** years_delta))
        builtup = min(99.0, round(b["builtup_area_percentage"] + 0.4 * years_delta, 2))
        gwl_base = round(b["gwl"] - 0.5 * years_delta, 2)

        for month in range(1, 13):
            rainfall = round(RAINFALL_PATTERN[month] * random.uniform(0.75, 1.25), 3)
            t2m_max  = round(T2M_MAX_PATTERN[month] + 0.15 * years_delta + random.uniform(-0.3, 0.3), 2)
            t2m_min  = round(T2M_MIN_PATTERN[month] + 0.12 * years_delta + random.uniform(-0.2, 0.2), 2)
            rh2m     = round(RH2M_PATTERN[month]    - 0.1  * years_delta + random.uniform(-1.5, 1.5), 2)
            ws2m     = round(b["ws2m"] + random.uniform(-0.3, 0.3), 2)
            # GWL higher in monsoon (recharge), lower in dry season
            monsoon_bonus = 2.5 if month in [6, 7, 8, 9] else 0
            gwl = round(gwl_base + monsoon_bonus + random.uniform(-0.8, 0.8), 2)

            con.execute("""
                INSERT INTO ward_data
                (year,month,ward_no,ward_name,building_area_km2,builtup_area_percentage,
                 population,rainfall,rh2m,t2m_max,t2m_min,ws2m,gwl)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (year, month,
                  b["ward_no"], b["ward_name"],
                  b["building_area_km2"],
                  builtup, pop, rainfall,
                  rh2m, t2m_max, t2m_min, ws2m, gwl))
            rows_generated += 1

con.commit()
con.close()
print(f"✓ Generated {rows_generated} rows for 2024–2025 ({len(baselines)} wards × 2 years × 12 months)")

# ── Verification ───────────────────────────────────────────────────────────────
con = sqlite3.connect(DB)
total = con.execute("SELECT COUNT(*) FROM ward_data").fetchone()[0]
wards = con.execute("SELECT COUNT(DISTINCT ward_no) FROM ward_data").fetchone()[0]
years = [r[0] for r in con.execute("SELECT DISTINCT year FROM ward_data ORDER BY year").fetchall()]

print(f"\n✓ ward.db ready")
print(f"  Total rows : {total}")
print(f"  Wards      : {wards}")
print(f"  Years      : {years}")

# Sample — Jayanagar Jan across years
rows = con.execute("""
    SELECT year, population, rainfall, gwl, t2m_max, builtup_area_percentage
    FROM ward_data WHERE ward_name='jayanagar' AND month=1 ORDER BY year
""").fetchall()
if rows:
    print(f"\n  Jayanagar Jan trend:")
    print(f"  {'Year':<6} {'Pop':<8} {'Rainfall':<10} {'GWL':<8} {'T2M_MAX':<8} {'Builtup%'}")
    for r in rows:
        print(f"  {r[0]:<6} {r[1]:<8} {round(r[2],2):<10} {round(r[3],2):<8} {r[4]:<8} {r[5]}")
con.close()
