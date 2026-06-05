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

zone_pop = {"Jayanagar": 285000, "Koramangala": 210000,
            "HSR Layout": 195000, "BTM Layout": 230000, "Banashankari": 260000}

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
    con.execute("""INSERT OR IGNORE INTO release_policies
        (policy_id, zone, min_release_mld, max_release_mld, priority_level, effective_from, notes)
        VALUES (?,?,?,?,?,?,?)""",
        (f"POL-{z[:3].upper()}-001", z, base_min, base_max,
         1 if z == "Jayanagar" else 2, "2024-01-01",
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


# ── Ward DB ───────────────────────────────────────────────────────────────────
import importlib.util, sys
spec = importlib.util.spec_from_file_location("seed_ward",
    os.path.join(os.path.dirname(__file__), "seed_ward.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
