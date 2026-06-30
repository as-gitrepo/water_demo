"""
seed_sewage.py — creates sewage_generation table in supply.db

sewage_generated_lpcd = supplied_lpcd × sewage_generation_factor
Standard factor per CPHEEO (Central Public Health & Environmental Engineering Org):
  80% of supplied water returns as sewage
  20% accounts for evaporation, garden/irrigation use, unaccounted losses

Surplus carried forward = yesterday_supply - sewage_generated
This replaces the consumption_history approach for calculating available water.
"""

import sqlite3, os
from datetime import datetime, timedelta

BASE = os.path.dirname(__file__)
DB   = os.path.join(BASE, "supply.db")

con = sqlite3.connect(DB)
con.executescript("""
CREATE TABLE IF NOT EXISTS sewage_generation (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ward_no                 INTEGER,
    ward_name               TEXT,
    sewage_factor           REAL,       -- fraction of supply that becomes sewage (default 0.80)
    notes                   TEXT,
    last_updated            TEXT,
    UNIQUE(ward_no)
);

CREATE TABLE IF NOT EXISTS sewage_history (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    date                    TEXT,
    ward_no                 INTEGER,
    ward_name               TEXT,
    population              INTEGER,
    supplied_lpcd           REAL,
    sewage_factor           REAL,
    sewage_generated_lpcd   REAL,       -- supplied_lpcd × sewage_factor
    sewage_generated_mld    REAL,
    surplus_lpcd            REAL,       -- supplied_lpcd - sewage_generated_lpcd
    surplus_mld             REAL
);

CREATE INDEX IF NOT EXISTS idx_sewage_date_ward ON sewage_history(date, ward_no);
""")

con.execute("DELETE FROM sewage_generation")
con.execute("DELETE FROM sewage_history")
con.commit()

# Read all wards from supply_history
wards = con.execute("""
    SELECT DISTINCT ward_no, ward_name, population
    FROM supply_history ORDER BY ward_no
""").fetchall()

today = datetime.today()
SEWAGE_FACTOR = 0.80   # CPHEEO standard — 80% of supply becomes sewage

# Seed sewage_generation — one row per ward
gen_rows = []
for ward_no, ward_name, population in wards:
    gen_rows.append((
        ward_no, ward_name, SEWAGE_FACTOR,
        "CPHEEO standard — 80% of supply returns as sewage",
        today.strftime("%Y-%m-%d")
    ))

con.executemany("""
    INSERT OR REPLACE INTO sewage_generation
    (ward_no, ward_name, sewage_factor, notes, last_updated)
    VALUES (?,?,?,?,?)
""", gen_rows)
print(f"✓ sewage_generation: {len(gen_rows)} wards seeded (factor={SEWAGE_FACTOR})")

# Seed sewage_history — one row per ward per day, joined from supply_history
supply_rows = con.execute("""
    SELECT date, ward_no, ward_name, population, supplied_lpcd, supplied_mld
    FROM supply_history ORDER BY date, ward_no
""").fetchall()

hist_rows = []
for date, ward_no, ward_name, population, supplied_lpcd, supplied_mld in supply_rows:
    sewage_lpcd = round(supplied_lpcd * SEWAGE_FACTOR, 2)
    sewage_mld  = round(supplied_mld  * SEWAGE_FACTOR, 4)
    surplus_lpcd = round(supplied_lpcd - sewage_lpcd, 2)
    surplus_mld  = round(supplied_mld  - sewage_mld, 4)
    hist_rows.append((
        date, ward_no, ward_name, population,
        supplied_lpcd, SEWAGE_FACTOR,
        sewage_lpcd, sewage_mld,
        surplus_lpcd, surplus_mld
    ))

con.executemany("""
    INSERT INTO sewage_history
    (date, ward_no, ward_name, population, supplied_lpcd, sewage_factor,
     sewage_generated_lpcd, sewage_generated_mld, surplus_lpcd, surplus_mld)
    VALUES (?,?,?,?,?,?,?,?,?,?)
""", hist_rows)
con.commit()
print(f"✓ sewage_history: {len(hist_rows)} rows seeded")

# Verify
con.row_factory = sqlite3.Row
yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
row = con.execute("""
    SELECT * FROM sewage_history
    WHERE ward_name='jayanagar' AND date=?
""", (yesterday,)).fetchone()
if row:
    print(f"\n  Jayanagar yesterday ({yesterday}):")
    print(f"    Supply:          {row['supplied_lpcd']} lpcd")
    print(f"    Sewage factor:   {row['sewage_factor']}")
    print(f"    Sewage generated:{row['sewage_generated_lpcd']} lpcd")
    print(f"    Surplus:         {row['surplus_lpcd']} lpcd")
con.close()
