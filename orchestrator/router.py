"""
LangChain-enabled DB router.
Four tools: reservoir_db, demand_db, rules_db, ward_db (new).
"""

import sqlite3, os
from datetime import datetime, timedelta
from langchain_core.tools import tool

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

    # Try case-insensitive match if exact match fails
    if not rows:
        rows = con.execute("""
            SELECT zd.*, ch.residential_mld, ch.commercial_mld,
                   ch.industrial_mld, ch.losses_mld
            FROM zone_demand zd
            LEFT JOIN consumption_history ch ON ch.date=zd.date AND ch.zone=zd.zone
            WHERE LOWER(zd.zone) = LOWER(?)
            ORDER BY zd.date DESC LIMIT 7
        """, (zone,)).fetchall()

    con.close()
    if not rows:
        return {"error": f"No demand data for {zone}"}

    latest = rows[0]
    population = latest["population"]

    # Actual consumption = residential + commercial + industrial (losses excluded)
    residential  = latest["residential_mld"] or 0
    commercial   = latest["commercial_mld"]  or 0
    industrial   = latest["industrial_mld"]  or 0
    losses       = latest["losses_mld"]      or 0
    actual_consumption_mld  = round(residential + commercial + industrial, 4)
    consumption_lpcd        = round(actual_consumption_mld * 1_000_000 / population, 2) if population > 0 else 0

    return {
        "zone":                    zone,
        "population":              population,
        "demand_mld":              latest["demand_mld"],
        "actual_supply_mld":       latest["actual_supply_mld"],
        "deficit_mld":             latest["deficit_mld"],
        "avg_demand_7d":           round(sum(r["demand_mld"] for r in rows) / len(rows), 2),
        # Consumption breakdown
        "residential_mld":         residential,
        "commercial_mld":          commercial,
        "industrial_mld":          industrial,
        "losses_mld":              losses,
        "actual_consumption_mld":  actual_consumption_mld,
        "consumption_lpcd":        consumption_lpcd,
        "losses_lpcd":             round(losses * 1_000_000 / population, 2) if population > 0 else 0,
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
        "gwl_trend":               "declining" if rows[-1]["gwl"] < rows[0]["gwl"] else "stable"
    }


# ── Supply history tool ────────────────────────────────────────────────────────

@tool("supply_history_tool")
def supply_history_tool(zone: str = "Jayanagar", date: str = "yesterday") -> dict:
    """
    Query supply_history database for actual water supplied to a ward.
    Returns yesterday's supply in lpcd and MLD, and valve open hours.
    """
    print("LangChain → Supply History DB")
    con  = get_db("supply_db")
    zone_lower = zone.lower()

    if date == "yesterday" or date == "today" or date is None:
        from datetime import datetime, timedelta
        target_date = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        target_date = date

    row = con.execute("""
        SELECT * FROM supply_history
        WHERE LOWER(ward_name) = ? AND date = ?
        ORDER BY id DESC LIMIT 1
    """, (zone_lower, target_date)).fetchone()

    # Fallback to most recent available
    if not row:
        row = con.execute("""
            SELECT * FROM supply_history
            WHERE LOWER(ward_name) = ?
            ORDER BY date DESC LIMIT 1
        """, (zone_lower,)).fetchone()

    con.close()
    if not row:
        return {"error": f"No supply history found for '{zone}'"}

    return {
        "ward_name":       row["ward_name"],
        "date":            row["date"],
        "population":      row["population"],
        "supplied_lpcd":   row["supplied_lpcd"],
        "supplied_mld":    row["supplied_mld"],
        "supply_hours":    row["supply_hours"],
        "flow_rate_lph":   row["flow_rate_lph"],
        "notes":           row["notes"],
        "norm_lpcd":       135,
        "deficit_lpcd":    round(135 - row["supplied_lpcd"], 2)
    }


# ── Rainwater harvesting tool ──────────────────────────────────────────────────

@tool("rwh_tool")
def rwh_tool(zone: str = "Jayanagar", date: str = "today") -> dict:
    """
    Query rainwater_harvesting database for RWH house counts and tank sizes.
    Also calculates RWH water contribution based on expected rainfall.
    """
    print("LangChain → Rainwater Harvesting DB")
    con  = get_db("supply_db")
    zone_lower = zone.lower()

    # Get population from supply_history (most recent row for this ward)
    pop_row = con.execute("""
        SELECT population FROM supply_history
        WHERE LOWER(ward_name) = ?
        ORDER BY date DESC LIMIT 1
    """, (zone_lower,)).fetchone()
    population = pop_row["population"] if pop_row else 1

    row = con.execute("""
        SELECT * FROM rainwater_harvesting
        WHERE LOWER(ward_name) = ?
    """, (zone_lower,)).fetchone()
    con.close()

    if not row:
        return {"error": f"No RWH data found for '{zone}'"}

    # Get expected rainfall from ward_db
    ward_con = get_db("ward_db")
    from datetime import datetime
    month = datetime.today().month + 1  # tomorrow's month
    if month > 12:
        month = 1
    rainfall_row = ward_con.execute("""
        SELECT rainfall FROM ward_data
        WHERE LOWER(ward_name) = ? AND year = 2025 AND month = ?
    """, (zone_lower, month)).fetchone()
    ward_con.close()

    expected_rainfall_mm  = rainfall_row["rainfall"] if rainfall_row else 0.0
    threshold_mm          = row["rainfall_threshold_mm"]
    rwh_active            = expected_rainfall_mm >= threshold_mm

    # RWH water contribution calculation:
    # If rainfall >= threshold: 20% of RWH tanks get filled
    # Contribution = rwh_houses × avg_tank_size × 20%
    rwh_contribution_litres = 0
    if rwh_active:
        rwh_contribution_litres = row["rwh_houses"] * row["avg_tank_size_litres"] * 0.20

    rwh_contribution_lpcd = round(
        rwh_contribution_litres / population if population > 0 else 0, 2
    ) if rwh_active else 0

    return {
        "ward_name":                  row["ward_name"],
        "total_houses":               row["total_houses"],
        "rwh_houses":                 row["rwh_houses"],
        "rwh_percentage":             row["rwh_percentage"],
        "avg_tank_size_litres":       row["avg_tank_size_litres"],
        "expected_rainfall_mm":       round(expected_rainfall_mm, 2),
        "rainfall_threshold_mm":      threshold_mm,
        "rwh_active":                 rwh_active,
        "rwh_contribution_litres":    round(rwh_contribution_litres, 0),
        "rwh_contribution_lpcd":      rwh_contribution_lpcd,
        "rwh_reduces_release_by_mld": round(rwh_contribution_litres / 1_000_000, 4)
    }


# ── Tool registry ──────────────────────────────────────────────────────────────

TOOLS = {
    "reservoir_db":      reservoir_tool,
    "demand_db":         demand_tool,
    "rules_db":          rules_tool,
    "ward_db":           ward_tool,
    "supply_history_db": supply_history_tool,
    "rwh_db":            rwh_tool
}
