"""
LangChain-enabled DB router.
Four tools: reservoir_db, demand_db, rules_db, ward_db (new).
"""

import sqlite3, os
from datetime import datetime, timedelta
from langchain.tools import tool

BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def get_db(name: str):
    path = os.path.join(BASE, f"{name.replace('_db','')}.db")
    con  = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def resolve_date(date_str):
    if not date_str or date_str == "null":
        return datetime.today().strftime("%Y-%m-%d")
    if date_str == "tomorrow":
        return (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    return date_str


# ── Reservoir tool ─────────────────────────────────────────────────────────────

@tool("reservoir_tool")
def reservoir_tool(zone: str = "Jayanagar", date: str = "today") -> dict:
    """Query reservoir database for water levels, inflow and weather forecast."""
    print("LangChain → Reservoir DB")
    con  = get_db("reservoir_db")
    resolved_date = resolve_date(date)
    rows = con.execute("""
        SELECT r.*, w.temp_c, w.rainfall_mm, w.humidity_pct
        FROM reservoir_levels r
        LEFT JOIN weather_forecast w ON w.date = ? AND w.zone = ?
        WHERE r.date = (SELECT MAX(date) FROM reservoir_levels)
        ORDER BY r.reservoir_id
    """, (resolved_date, zone)).fetchall()
    con.close()
    if not rows:
        return {"error": "No reservoir data found"}
    total_level    = sum(r["level_m"]    for r in rows)
    total_capacity = sum(r["capacity_m"] for r in rows)
    r0 = rows[0]
    return {
        "reservoir_level_pct": round(total_level / total_capacity * 100, 2),
        "inflow_mld":          round(sum(r["inflow_mld"] for r in rows), 2),
        "evaporation_mld":     round(sum(r["evaporation_mld"] for r in rows), 2),
        "temp_c":              r0["temp_c"]       or 28.0,
        "rainfall_mm":         r0["rainfall_mm"]  or 0.0,
        "humidity_pct":        r0["humidity_pct"] or 65.0,
        "date":                resolved_date
    }


# ── Demand tool ────────────────────────────────────────────────────────────────

@tool("demand_tool")
def demand_tool(zone: str = "Jayanagar", date: str = "today") -> dict:
    """Query demand database for zone-wise consumption and supply deficits."""
    print("LangChain → Demand DB")
    con  = get_db("demand_db")
    rows = con.execute("""
        SELECT zd.*, ch.residential_mld, ch.commercial_mld,
               ch.industrial_mld, ch.losses_mld
        FROM zone_demand zd
        LEFT JOIN consumption_history ch ON ch.date=zd.date AND ch.zone=zd.zone
        WHERE zd.zone = ?
        ORDER BY zd.date DESC LIMIT 7
    """, (zone,)).fetchall()
    con.close()
    if not rows:
        return {"error": f"No demand data for {zone}"}
    latest = rows[0]
    return {
        "zone":              zone,
        "demand_mld":        latest["demand_mld"],
        "actual_supply_mld": latest["actual_supply_mld"],
        "deficit_mld":       latest["deficit_mld"],
        "peak_hour_factor":  latest["peak_hour_factor"],
        "losses_mld":        latest["losses_mld"] or 0.0,
        "population":        latest["population"],
        "trend_7d":          [dict(r)["demand_mld"] for r in rows]
    }


# ── Rules tool ─────────────────────────────────────────────────────────────────

@tool("rules_tool")
def rules_tool(zone: str = "Jayanagar", date: str = "today") -> dict:
    """Query rules database for release policies and compliance thresholds."""
    print("LangChain → Rules DB")
    con    = get_db("rules_db")
    policy = con.execute(
        "SELECT * FROM release_policies WHERE zone=? ORDER BY priority_level",
        (zone,)).fetchone()
    thresholds = con.execute("SELECT * FROM compliance_thresholds").fetchall()
    con.close()
    if not policy:
        return {"error": f"No policy found for {zone}"}
    return {
        "zone":            zone,
        "policy_id":       policy["policy_id"],
        "min_release_mld": policy["min_release_mld"],
        "max_release_mld": policy["max_release_mld"],
        "priority_level":  policy["priority_level"],
        "thresholds":      [dict(t) for t in thresholds]
    }


# ── Ward tool ──────────────────────────────────────────────────────────────────

@tool("ward_tool")
def ward_tool(zone: str = "Jayanagar", date: str = "2025") -> dict:
    """
    Query ward database for groundwater level (GWL), population, rainfall,
    temperature, humidity and builtup area by ward name.
    Data available: 2016 (all wards), 2024 and 2025 (Jayanagar only).
    """
    print("LangChain → Ward DB")
    con  = get_db("ward_db")
    zone_lower = zone.lower()

    # Resolve year
    if "2025" in str(date):
        year = 2025
    elif "2024" in str(date):
        year = 2024
    else:
        year = 2025   # default to most recent

    rows = con.execute("""
        SELECT * FROM ward_data
        WHERE LOWER(ward_name) = ? AND year = ?
        ORDER BY month
    """, (zone_lower, year)).fetchall()

    # Fallback to any available year
    if not rows:
        rows = con.execute("""
            SELECT * FROM ward_data
            WHERE LOWER(ward_name) = ?
            ORDER BY year DESC, month DESC LIMIT 12
        """, (zone_lower,)).fetchall()

    con.close()
    if not rows:
        return {"error": f"No ward data found for '{zone}'"}

    latest   = rows[-1]
    avg_gwl      = round(sum(r["gwl"]      for r in rows) / len(rows), 3)
    avg_rainfall = round(sum(r["rainfall"] for r in rows) / len(rows), 3)
    avg_t2m_max  = round(sum(r["t2m_max"]  for r in rows) / len(rows), 2)

    return {
        "ward_no":                 latest["ward_no"],
        "ward_name":               latest["ward_name"],
        "year":                    latest["year"],
        "population":              latest["population"],
        "building_area_km2":       latest["building_area_km2"],
        "builtup_area_percentage": latest["builtup_area_percentage"],
        "avg_annual_gwl_m":        avg_gwl,
        "avg_monthly_rainfall_mm": avg_rainfall,
        "avg_t2m_max_c":           avg_t2m_max,
        "latest_month_gwl_m":      latest["gwl"],
        "latest_month":            latest["month"],
        "monthly_gwl":             [{"month": r["month"], "gwl": r["gwl"]} for r in rows]
    }


# ── Tool registry ──────────────────────────────────────────────────────────────

TOOLS = {
    "reservoir_db": reservoir_tool,
    "demand_db":    demand_tool,
    "rules_db":     rules_tool,
    "ward_db":      ward_tool       # NEW
}
