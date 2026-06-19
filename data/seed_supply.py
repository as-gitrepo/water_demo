"""
seed_supply.py — seeds two new tables:
  1. supply_history   — daily actual supply per ward in lpcd (last 30 days)
  2. rainwater_harvesting — RWH house counts per ward

These tables are queried to answer:
  - What was the supply to Jayanagar yesterday?
  - How many houses have rainwater harvesting done?
"""

import sqlite3, os, random
from datetime import datetime, timedelta

BASE = os.path.dirname(__file__)
DB   = os.path.join(BASE, "supply.db")

random.seed(42)

con = sqlite3.connect(DB)
con.executescript("""
CREATE TABLE IF NOT EXISTS supply_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT,
    ward_no       INTEGER,
    ward_name     TEXT,
    population    INTEGER,
    supplied_lpcd REAL,        -- actual litres per capita per day supplied
    supplied_mld  REAL,        -- total MLD supplied
    supply_hours  REAL,        -- how many hours valve was open
    flow_rate_lph REAL,        -- flow rate in litres per hour
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS rainwater_harvesting (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    ward_no              INTEGER,
    ward_name            TEXT,
    total_houses         INTEGER,
    rwh_houses           INTEGER,   -- houses with rainwater harvesting
    rwh_percentage       REAL,      -- % of houses with RWH
    avg_tank_size_litres INTEGER,   -- average RWH tank capacity in litres
    rainfall_threshold_mm REAL,     -- min rainfall (mm) to trigger RWH benefit
    last_updated         TEXT
);

CREATE INDEX IF NOT EXISTS idx_supply_date_ward
    ON supply_history(date, ward_no);
CREATE INDEX IF NOT EXISTS idx_rwh_ward
    ON rainwater_harvesting(ward_no);
""")

con.execute("DELETE FROM supply_history")
con.execute("DELETE FROM rainwater_harvesting")
con.commit()

# ── Ward master (matches ward_data.csv wards) ──────────────────────────────────
# (ward_no, ward_name, population)
# flow_rate_lph is calculated as population × 92.7 lph/person
WARDS = [
    (1,   "kempegowda ward",          43870),
    (2,   "chowdeswari ward",         49985),
    (3,   "atturu",                   90428),
    (4,   "yelahanka satellite town", 53579),
    (5,   "jakkuru",                  81956),
    (6,   "thanisandra",             134849),
    (7,   "byatarayanapura",         109377),
    (9,   "vidyaranyapura",           89928),
    (10,  "dodda bommasandra",        47201),
    (12,  "shettihalli",              89700),
    (14,  "bagalakunte",              98756),
    (16,  "jalahalli",                43401),
    (18,  "radhakrishna temple ward", 40656),
    (19,  "sanjaya nagar",            37665),
    (22,  "vishwanath nagenahalli",   73103),
    (24,  "hbr layout",               79851),
    (25,  "horamavu",                175482),
    (26,  "ramamurthy nagar",         69485),
    (27,  "banasavadi",               64895),
    (28,  "kammanahalli",             54735),
    (29,  "kacharkanahalli",          36136),
    (35,  "aramane nagara",           40389),
    (36,  "mattikere",                37627),
    (38,  "hmt ward",                 41051),
    (39,  "chokkasandra",             83187),
    (40,  "dodda bidarakallu",       141193),
    (41,  "peenya industrial area",   83877),
    (42,  "lakshmi devi nagar",       52579),
    (45,  "malleswaram",              33181),
    (46,  "indiranagar",              71000),  # major ward, approx population
    (48,  "muneshwara nagar",         38804),
    (50,  "benniganahalli",           60823),
    (51,  "vijnanapura",              52943),
    (52,  "k r puram",                40525),
    (53,  "basavanapura",             72181),
    (54,  "hudi",                     78154),
    (58,  "new tippasandara",         49606),
    (65,  "kadu malleshwar ward",     36413),
    (68,  "mahalakshimpuram",         49684),
    (69,  "laggere",                  85611),
    (72,  "herohalli",               110805),
    (73,  "kottegepalya",            106069),
    (74,  "shakthi ganapathi nagar",  49405),
    (77,  "dattatreya temple",        32972),
    (78,  "pulikeshinagar",           29184),
    (80,  "hoysala nagar",            34902),
    (81,  "vijnana nagar",            86631),
    (82,  "garudachar playa",         76445),
    (83,  "kadugodi",                 61815),
    (84,  "hagadur",                  70613),
    (85,  "dodda nekkundi",          106782),
    (86,  "marathahalli",             52883),
    (87,  "hal airport",              43873),
    (90,  "halsoor",                  34696),
    (93,  "vasanth nagar",            21525),
    (94,  "gandhinagar",              29339),
    (96,  "okalipuram",               39279),
    (104, "govindaraja nagar",        27440),
    (110, "sampangiram nagar",        25064),
    (112, "domlur",                   28788),
    (114, "agaram",                   37575),
    (119, "dharmaraya swamy temple",  24452),
    (124, "hosahalli",                40282),
    (126, "maruthi mandir ward",      34014),
    (128, "nagarabhavi",              47538),
    (129, "jnana bharathi ward",     110527),
    (130, "ullalu",                   98465),
    (143, "vishveshwara puram",       30786),
    (144, "siddapura",                36304),
    (145, "hombegowda nagara",        39271),
    (147, "adugodi",                  36708),
    (149, "varthuru",                 80637),
    (150, "bellanduru",              158470),
    (153, "jayanagar",                46137),
    (154, "basavanagudi",             31073),
    (157, "gali anjenaya temple ward",39068),
    (158, "deepanjali nagar",         55972),
    (159, "kengeri",                  52202),
]

# Flow rate: population × 92.7 lph/person
# Derived so that releasing policy_min MLD takes ~8 hours
# e.g. Jayanagar: 46137 × 92.7 = 4,277,499 lph → 34.2MLD ÷ 4,277,499 = 7.99h ✓
def flow_rate_for(population):
    return int(population * 92.7)

# ── Seed supply_history (last 30 days) ────────────────────────────────────────
BANGALORE_NORM_LPCD = 135   # BWSSB standard norm
FLOW_RATE_LPH       = 4275000  # litres per hour — ward-level main supply line (gives ~8h at policy min)

today = datetime.today()
supply_rows = []

for ward_no, ward_name, population in WARDS:
    flow_rate_lph = flow_rate_for(population)
    for days_ago in range(1, 31):
        date = (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        supply_pct    = random.uniform(0.75, 0.95)
        supplied_lpcd = round(BANGALORE_NORM_LPCD * supply_pct, 2)
        supplied_mld  = round(supplied_lpcd * population / 1_000_000, 4)
        supply_litres = supplied_lpcd * population
        supply_hours  = round(supply_litres / flow_rate_lph, 2)
        notes = "normal supply" if supply_pct > 0.85 else "reduced supply"

        supply_rows.append((
            date, ward_no, ward_name, population,
            supplied_lpcd, supplied_mld,
            supply_hours, flow_rate_lph, notes
        ))

con.executemany("""
    INSERT INTO supply_history
    (date, ward_no, ward_name, population,
     supplied_lpcd, supplied_mld, supply_hours, flow_rate_lph, notes)
    VALUES (?,?,?,?,?,?,?,?,?)
""", supply_rows)
print(f"✓ supply_history: {len(supply_rows)} rows inserted")

# ── Seed rainwater_harvesting ──────────────────────────────────────────────────

rwh_rows = []
HOUSES_PER_PERSON = 4.2  # avg household size Bangalore

# RWH profiles: (rwh_pct, avg_tank_litres, rainfall_threshold_mm)
# RWH profiles: (rwh_pct, avg_tank_litres, rainfall_threshold_mm)
RWH_PROFILES = {
    45:  (0.35, 2000, 5.0),   # malleswaram — 35% (old residential, good adoption)
    46:  (0.30, 2000, 5.0),   # indiranagar — 30% (affluent residential area)
    93:  (0.30, 1800, 5.0),   # vasanth nagar
    110: (0.28, 1800, 5.0),   # sampangiram nagar
    112: (0.25, 1500, 5.0),   # domlur
    153: (0.80, 2000, 5.0),   # jayanagar — 80% as specified
    154: (0.28, 1800, 5.0),   # basavanagudi
    19:  (0.22, 1500, 5.0),   # sanjaya nagar
}
DEFAULT_RWH = (0.15, 1500, 5.0)

for ward_no, ward_name, population in WARDS:
    rwh_pct, avg_tank, threshold = RWH_PROFILES.get(ward_no, DEFAULT_RWH)
    total_houses = int(population / HOUSES_PER_PERSON)
    rwh_houses   = int(total_houses * rwh_pct)
    rwh_rows.append((
        ward_no, ward_name,
        total_houses, rwh_houses,
        round(rwh_pct * 100, 1),
        avg_tank, threshold,
        today.strftime("%Y-%m-%d")
    ))

con.executemany("""
    INSERT INTO rainwater_harvesting
    (ward_no, ward_name, total_houses, rwh_houses,
     rwh_percentage, avg_tank_size_litres, rainfall_threshold_mm, last_updated)
    VALUES (?,?,?,?,?,?,?,?)
""", rwh_rows)
print(f"✓ rainwater_harvesting: {len(rwh_rows)} rows inserted")

con.commit()
con.close()

# ── Verify ─────────────────────────────────────────────────────────────────────
con = sqlite3.connect(DB)
yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
jay = con.execute("""
    SELECT ward_name, supplied_lpcd, supplied_mld, supply_hours
    FROM supply_history
    WHERE ward_name='jayanagar' AND date=?
""", (yesterday,)).fetchone()

rwh = con.execute("""
    SELECT ward_name, total_houses, rwh_houses, rwh_percentage, avg_tank_size_litres
    FROM rainwater_harvesting WHERE ward_name='jayanagar'
""").fetchone()

print(f"\n  Jayanagar yesterday ({yesterday}):")
print(f"    Supplied: {jay[1]} lpcd | {jay[2]} MLD | valve open {jay[3]} hrs")
print(f"  Jayanagar RWH: {rwh[2]}/{rwh[1]} houses ({rwh[3]}%) | avg tank {rwh[4]}L")
con.close()
