import sqlite3, os, random
from datetime import datetime, timedelta

BASE = os.path.dirname(__file__)

# ── Reservoir DB ──────────────────────────────────────────────────────────────
con = sqlite3.connect(f"{BASE}/reservoir.db")
con.executescript("""
CREATE TABLE IF NOT EXISTS reservoir_levels (
    id INTEGER PRIMARY KEY,
    date TEXT,
    reservoir_id TEXT,
    level_m REAL,
    capacity_m REAL,
    inflow_mld REAL,
    evaporation_mld REAL,
    recorded_at TEXT
);
CREATE TABLE IF NOT EXISTS weather_forecast (
    id INTEGER PRIMARY KEY,
    date TEXT,
    zone TEXT,
    temp_c REAL,
    rainfall_mm REAL,
    humidity_pct REAL
);
""")

base_date = datetime.today()
reservoirs = ["KRS", "Thippagondanahalli", "Hesaraghatta"]
for i in range(30):
    d = (base_date - timedelta(days=i)).strftime("%Y-%m-%d")
    for r in reservoirs:
        con.execute("""INSERT OR IGNORE INTO reservoir_levels
            (date, reservoir_id, level_m, capacity_m, inflow_mld, evaporation_mld, recorded_at)
            VALUES (?,?,?,?,?,?,?)""",
            (d, r,
             round(random.uniform(60, 95), 2),
             100.0,
             round(random.uniform(800, 1200), 2),
             round(random.uniform(20, 50), 2),
             datetime.now().isoformat()))

zones = ["Jayanagar", "Koramangala", "HSR Layout", "BTM Layout", "Banashankari"]
for i in range(7):
    d = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
    for z in zones:
        con.execute("""INSERT OR IGNORE INTO weather_forecast
            (date, zone, temp_c, rainfall_mm, humidity_pct) VALUES (?,?,?,?,?)""",
            (d, z,
             round(random.uniform(22, 34), 1),
             round(random.uniform(0, 15), 1),
             round(random.uniform(55, 85), 1)))

con.commit(); con.close()
print("✓ reservoir.db seeded")

# ── Demand DB ─────────────────────────────────────────────────────────────────
con = sqlite3.connect(f"{BASE}/demand.db")
con.executescript("""
CREATE TABLE IF NOT EXISTS zone_demand (
    id INTEGER PRIMARY KEY,
    date TEXT,
    zone TEXT,
    population INTEGER,
    demand_mld REAL,
    actual_supply_mld REAL,
    deficit_mld REAL,
    peak_hour_factor REAL
);
CREATE TABLE IF NOT EXISTS consumption_history (
    id INTEGER PRIMARY KEY,
    date TEXT,
    zone TEXT,
    residential_mld REAL,
    commercial_mld REAL,
    industrial_mld REAL,
    losses_mld REAL
);
""")

zone_pop = {
    "kempegowda ward": 43870, "chowdeswari ward": 49985, "atturu": 90428,
    "yelahanka satellite town": 53579, "jakkuru": 81956, "thanisandra": 134849,
    "byatarayanapura": 109377, "vidyaranyapura": 89928, "dodda bommasandra": 47201,
    "shettihalli": 89700, "bagalakunte": 98756, "jalahalli": 43401,
    "radhakrishna temple ward": 40656, "sanjaya nagar": 37665,
    "vishwanath nagenahalli": 73103, "hbr layout": 79851, "horamavu": 175482,
    "ramamurthy nagar": 69485, "banasavadi": 64895, "kammanahalli": 54735,
    "kacharkanahalli": 36136, "aramane nagara": 40389, "mattikere": 37627,
    "hmt ward": 41051, "chokkasandra": 83187, "dodda bidarakallu": 141193,
    "peenya industrial area": 83877, "lakshmi devi nagar": 52579,
    "malleswaram": 33181, "indiranagar": 71000, "muneshwara nagar": 38804,
    "benniganahalli": 60823, "vijnanapura": 52943, "k r puram": 40525,
    "basavanapura": 72181, "hudi": 78154, "new tippasandara": 49606,
    "kadu malleshwar ward": 36413, "mahalakshimpuram": 49684, "laggere": 85611,
    "herohalli": 110805, "kottegepalya": 106069, "shakthi ganapathi nagar": 49405,
    "dattatreya temple": 32972, "pulikeshinagar": 29184, "hoysala nagar": 34902,
    "vijnana nagar": 86631, "garudachar playa": 76445, "kadugodi": 61815,
    "hagadur": 70613, "dodda nekkundi": 106782, "marathahalli": 52883,
    "hal airport": 43873, "halsoor": 34696, "vasanth nagar": 21525,
    "gandhinagar": 29339, "okalipuram": 39279, "govindaraja nagar": 27440,
    "sampangiram nagar": 25064, "domlur": 28788, "agaram": 37575,
    "dharmaraya swamy temple": 24452, "hosahalli": 40282, "maruthi mandir ward": 34014,
    "nagarabhavi": 47538, "jnana bharathi ward": 110527, "ullalu": 98465,
    "vishveshwara puram": 30786, "siddapura": 36304, "hombegowda nagara": 39271,
    "adugodi": 36708, "varthuru": 80637, "bellanduru": 158470,
    "jayanagar": 46137, "basavanagudi": 31073, "gali anjenaya temple ward": 39068,
    "deepanjali nagar": 55972, "kengeri": 52202,
    # Legacy zones kept for compatibility
    "Jayanagar": 46137, "Koramangala": 210000, "HSR Layout": 195000,
    "BTM Layout": 230000, "Banashankari": 260000,
}

for i in range(30):
    d = (base_date - timedelta(days=i)).strftime("%Y-%m-%d")
    for z, pop in zone_pop.items():
        demand = round(pop * random.uniform(0.000135, 0.000160), 2)
        supply = round(demand * random.uniform(0.88, 1.02), 2)
        con.execute("""INSERT OR IGNORE INTO zone_demand
            (date, zone, population, demand_mld, actual_supply_mld, deficit_mld, peak_hour_factor)
            VALUES (?,?,?,?,?,?,?)""",
            (d, z, pop, demand, supply, round(demand - supply, 2), round(random.uniform(1.4, 1.8), 2)))
        con.execute("""INSERT OR IGNORE INTO consumption_history
            (date, zone, residential_mld, commercial_mld, industrial_mld, losses_mld)
            VALUES (?,?,?,?,?,?)""",
            (d, z,
             round(demand * 0.65, 2), round(demand * 0.20, 2),
             round(demand * 0.08, 2), round(demand * 0.07, 2)))

con.commit(); con.close()
print("✓ demand.db seeded")

# ── Rules DB ──────────────────────────────────────────────────────────────────
con = sqlite3.connect(f"{BASE}/rules.db")
con.executescript("""
CREATE TABLE IF NOT EXISTS release_policies (
    id INTEGER PRIMARY KEY,
    policy_id TEXT,
    zone TEXT,
    min_release_mld REAL,
    max_release_mld REAL,
    priority_level INTEGER,
    effective_from TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS compliance_thresholds (
    id INTEGER PRIMARY KEY,
    metric TEXT,
    warning_threshold REAL,
    critical_threshold REAL,
    unit TEXT
);
""")

for z, pop in zone_pop.items():
    base_min = round(pop * 0.000120, 2)
    base_max = round(pop * 0.000175, 2)
    safe_id  = z[:6].upper().replace(" ", "_")
    con.execute("""INSERT OR IGNORE INTO release_policies
        (policy_id, zone, min_release_mld, max_release_mld, priority_level, effective_from, notes)
        VALUES (?,?,?,?,?,?,?)""",
        (f"POL-{safe_id}-001", z, base_min, base_max,
         1 if z.lower() == "jayanagar" else 2, "2024-01-01",
         f"Standard allocation for {z}"))

thresholds = [
    ("reservoir_level_pct", 40.0, 25.0, "%"),
    ("deficit_mld", 5.0, 10.0, "MLD"),
    ("supply_ratio", 0.90, 0.80, "ratio"),
]
for t in thresholds:
    con.execute("INSERT OR IGNORE INTO compliance_thresholds (metric, warning_threshold, critical_threshold, unit) VALUES (?,?,?,?)", t)

con.commit(); con.close()
print("✓ rules.db seeded")
print("\nAll databases ready.")


# ── Ward DB — only seed if CSV exists ─────────────────────────────────────────
import importlib.util, sys
ward_csv = os.path.join(os.path.dirname(__file__), "ward_data.csv")
if os.path.exists(ward_csv):
    spec = importlib.util.spec_from_file_location("seed_ward",
        os.path.join(os.path.dirname(__file__), "seed_ward.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
else:
    print("\n⚠  Ward DB not seeded — data/ward_data.csv not found.")
    print("   Place your CSV there and re-run to populate ward DB.")


# ── Supply DB (supply_history + rainwater_harvesting) ─────────────────────────
spec2 = importlib.util.spec_from_file_location("seed_supply",
    os.path.join(os.path.dirname(__file__), "seed_supply.py"))
mod2 = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(mod2)
