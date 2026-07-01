"""
response_formatter.py

Step 1: Python computes ALL numbers from DB results (no LLM math)
Step 2: Passes the computed results to LLM as a pre-computed fact sheet
Step 3: LLM writes ONLY the narrative for each section — no calculations

This guarantees DIRECT ANSWER is always correct regardless of LLM provider.
"""

from orchestrator.cache import make_key, TTL_LLM_SUMMARISE
from orchestrator.llm_client import call_llm

BANGALORE_NORM_LPCD = 135


# ── Extract DB result by name ──────────────────────────────────────────────────

def _get(db_results: list, db_name: str) -> dict:
    for r in db_results:
        if r.get("db") == db_name:
            d = r.get("data", {})
            if isinstance(d, dict) and "error" not in d:
                return d
    return {}


# ── Python calculation — all math done here ────────────────────────────────────

def compute_release(db_results: list) -> dict:
    """
    Reads DB results and computes every number needed for the response.
    Returns a flat dict of facts — no narrative, just numbers and labels.
    """
    supply = _get(db_results, "supply_history_db")
    rwh    = _get(db_results, "rwh_db")
    rules  = _get(db_results, "rules_db")
    ward   = _get(db_results, "ward_db")
    demand = _get(db_results, "demand_db")

    # Population — prefer supply_history, then demand_db, then ward_db
    population    = (supply.get("population") or
                     demand.get("population") or
                     ward.get("population", 0))

    # ── GUARD: if no data found for this ward, return clear error ────────────
    if population == 0:
        return {
            "is_release_query":  True,
            "demand_negative":   False,
            "valve_hours":       0,
            "final_mld":         0,
            "lpcd_equiv":        0,
            "policy_state":      "No data",
            "norm_lpcd":         BANGALORE_NORM_LPCD,
            "supplied_lpcd":     0, "supplied_mld": 0, "supply_date": "unknown",
            "supply_notes":      "Ward not found in database",
            "rwh_active":        False, "rwh_lpcd": 0, "rwh_pct": 0,
            "rwh_houses":        0, "total_houses": 0,
            "building_area_km2": 0, "builtup_area_percentage": 0,
            "roof_area_m2":      0, "runoff_coefficient": 0.60,
            "captured_litres_total": 0,
            "rainfall_mm":       0, "rainfall_m": 0, "threshold_mm": 5, "rwh_mld": 0,
            "rwh_contribution_litres": 0,
            "adjusted_lpcd":     BANGALORE_NORM_LPCD,
            "required_mld":      0, "final_litres": 0,
            "min_mld": 0, "max_mld": 999,
            "flow_rate_lph":     4276899,
            "valve_state":       "Cannot calculate — ward not in database",
            "gwl": 0, "gwl_trend": "unknown",
            "demand_mld": 0, "deficit_mld": 0,
            "population": 0,
            "_error": True,
        }

    supplied_lpcd = supply.get("supplied_lpcd", 0)
    supplied_mld  = supply.get("supplied_mld", 0)
    flow_rate_lph = supply.get("flow_rate_lph") or int(population * 92.7) or 4276899
    supply_date   = supply.get("date", "yesterday")
    supply_notes  = supply.get("notes", "no supply data available")

    if not supply:
        supplied_lpcd = 0
        supply_notes  = "No supply history available — assuming full demand unmet"

    # ── Actual consumption from demand_db (residential + commercial + industrial)
    # More accurate than supplied_lpcd — excludes distribution losses
    # Keep consumption fields for reference/display but don't use for surplus calc
    consumption_lpcd = demand.get("consumption_lpcd", 0)
    consumption_mld  = demand.get("actual_consumption_mld", 0)
    residential_mld  = demand.get("residential_mld", 0)
    commercial_mld   = demand.get("commercial_mld", 0)
    industrial_mld   = demand.get("industrial_mld", 0)
    losses_lpcd      = demand.get("losses_lpcd", 0)
    losses_mld       = demand.get("losses_mld", 0)

    # Extract sewage data — replaces consumption_history for surplus calculation
    sewage = _get(db_results, "sewage_db")
    sewage_lpcd        = sewage.get("sewage_generated_lpcd", 0)
    sewage_mld         = sewage.get("sewage_generated_mld", 0)
    sewage_factor      = sewage.get("sewage_factor", 0.80)
    # Fallback: if no sewage DB data, compute from supply using standard factor
    if sewage_lpcd == 0 and supplied_lpcd > 0:
        sewage_factor = 0.80
        sewage_lpcd   = round(supplied_lpcd * sewage_factor, 2)
        sewage_mld    = round(supplied_mld  * sewage_factor, 4)

    rwh_active    = rwh.get("rwh_active", False)
    rwh_lpcd      = rwh.get("rwh_contribution_lpcd", 0)
    rwh_pct       = rwh.get("rwh_percentage", 0)
    rwh_houses    = rwh.get("rwh_houses", 0)
    total_houses  = rwh.get("total_houses", 0)
    building_area_km2       = rwh.get("building_area_km2", 0)
    builtup_area_percentage = rwh.get("builtup_area_percentage", 0)
    roof_area_m2             = rwh.get("roof_area_m2", 0)
    runoff_coefficient       = rwh.get("runoff_coefficient", 0.60)
    captured_litres_total    = rwh.get("captured_litres_total", 0)
    rainfall_mm   = rwh.get("expected_rainfall_mm", 0)
    captured_volume_m3 = rwh.get("captured_volume_m3", 0)
    monthly_rainfall_mm = rwh.get("monthly_rainfall_mm", 0)
    threshold_mm  = rwh.get("rainfall_threshold_mm", 5)
    rwh_mld       = rwh.get("rwh_reduces_release_by_mld", 0)

    # If no RWH data — treat as no RWH
    if not rwh:
        rwh_active = False
        rwh_lpcd   = 0

    min_mld       = rules.get("min_release_mld", 0)
    max_mld       = rules.get("max_release_mld", 999)

    gwl           = ward.get("avg_annual_gwl_m") or ward.get("latest_month_gwl_m", 0)
    gwl_trend     = ward.get("gwl_trend", "unknown")

    demand_mld    = demand.get("demand_mld", 0)
    deficit_mld   = demand.get("deficit_mld", 0)

    # ── Step 1: Total available water ───────────────────────────────────────
    # surplus = yesterday_supply - sewage_generated (80% of supply per CPHEEO)
    # sewage is subtracted because that water has left the system
    # + RWH = additional water available from rainwater harvesting
    surplus_lpcd     = round(supplied_lpcd - sewage_lpcd, 2)
    total_available  = round(surplus_lpcd + rwh_lpcd, 2)

    # ── Step 2: Water to release ─────────────────────────────────────────────
    # demand - total_available = how much piped water still needs to be sent
    water_to_release_lpcd = round(BANGALORE_NORM_LPCD - total_available, 2)
    demand_met            = water_to_release_lpcd <= 0

    # For backward compat — keep adjusted_lpcd as the release quantity
    adjusted_lpcd  = water_to_release_lpcd
    demand_negative = demand_met

    # ── Step 2: Required release ─────────────────────────────────────────────
    if demand_negative:
        required_litres = 0
        required_mld    = 0.0
    else:
        required_litres = round(adjusted_lpcd * population)
        required_mld    = round(required_litres / 1_000_000, 4)

    # ── Step 3: Policy clamp ─────────────────────────────────────────────────
    # If demand is negative (RWH covers it), no release needed — policy minimum
    # does NOT apply. Policy minimum only kicks in when there IS actual demand.
    if demand_negative:
        final_mld    = 0.0
        policy_state = "No release required — total available water covers demand. Policy minimum does not apply."
    elif required_mld < min_mld:
        final_mld    = min_mld
        policy_state = f"Calculated {required_mld} MLD is below policy minimum of {min_mld} MLD — release set to {min_mld} MLD"
    elif required_mld > max_mld:
        final_mld    = max_mld
        policy_state = f"Calculated {required_mld} MLD exceeds policy maximum — release clamped to {max_mld} MLD"
    else:
        final_mld    = required_mld
        policy_state = f"Release of {final_mld} MLD is within policy limits ({min_mld}–{max_mld} MLD)"

    final_litres = round(final_mld * 1_000_000)
    lpcd_equiv   = round(final_litres / population, 1) if population > 0 else 0

    # ── Step 4: Valve hours ──────────────────────────────────────────────────
    if final_litres == 0:
        valve_hours = 0.0
        valve_state = "Valve need not be opened"
    else:
        valve_hours = round(final_litres / flow_rate_lph, 1)
        valve_state = f"Open valve for {valve_hours} hours"

    return {
        # Core answer
        "valve_hours":        valve_hours,
        "final_mld":          final_mld,
        "lpcd_equiv":         lpcd_equiv,
        "demand_negative":    demand_negative,
        "demand_met":         demand_met,
        "valve_state":        valve_state,

        # Step 1 — available water
        "norm_lpcd":          BANGALORE_NORM_LPCD,
        "supplied_lpcd":      supplied_lpcd,
        "supplied_mld":       supplied_mld,
        "supply_date":        supply_date,
        "supply_notes":       supply_notes,
        "sewage_lpcd":        sewage_lpcd,
        "sewage_mld":         sewage_mld,
        "sewage_factor":      sewage_factor,
        "consumption_lpcd":   consumption_lpcd,
        "consumption_mld":    consumption_mld,
        "residential_mld":    residential_mld,
        "commercial_mld":     commercial_mld,
        "industrial_mld":     industrial_mld,
        "losses_lpcd":        losses_lpcd,
        "losses_mld":         losses_mld,
        "surplus_lpcd":       surplus_lpcd,
        "rwh_active":         rwh_active,
        "rwh_lpcd":           rwh_lpcd,
        "rwh_mld":            rwh_mld,
        "rwh_contribution_litres": int(captured_litres_total * rwh_pct / 100),
        "total_available":    total_available,
        "adjusted_lpcd":      adjusted_lpcd,

        # RWH detail
        "rwh_pct":          rwh_pct,
        "rwh_houses":       rwh_houses,
        "total_houses":     total_houses,
        "tank_litres":      0,  # deprecated — kept for backward compat
        "building_area_km2":       building_area_km2,
        "builtup_area_percentage": builtup_area_percentage,
        "roof_area_m2":            roof_area_m2,
        "runoff_coefficient":      runoff_coefficient,
        "captured_litres_total":   captured_litres_total,
        "rainfall_mm":      rainfall_mm,
        "rainfall_m":       round(rainfall_mm / 1000, 7),
        "captured_volume_m3": captured_volume_m3,
        "monthly_rainfall_mm": monthly_rainfall_mm,
        "threshold_mm":     threshold_mm,

        # Step 2
        "population":       population,
        "required_mld":     required_mld,
        "final_litres":     final_litres,

        # Step 3
        "min_mld":          min_mld,
        "max_mld":          max_mld,
        "policy_state":     policy_state,

        # Step 4
        "flow_rate_lph":    flow_rate_lph,

        # Supporting
        "gwl":              gwl,
        "gwl_trend":        gwl_trend,
        "demand_mld":       demand_mld,
        "deficit_mld":      deficit_mld,
    }


# ── LLM narrative builder ──────────────────────────────────────────────────────

def build_narrative(zone: str, user_query: str, c: dict) -> dict:
    """
    Pass pre-computed facts to LLM.
    LLM writes narrative ONLY — no arithmetic.
    Returns dict with four section strings.
    """

    # Build the fact sheet — all numbers computed by Python
    # RWH contribution is calculated directly from rainfall — no on/off threshold gate
    rwh_status = (
        f"  Expected rainfall      = {c['rainfall_mm']}mm\n"
        f"  Houses with RWH        = {c['rwh_houses']:,} of {c['total_houses']:,} ({c['rwh_pct']}%)\n"
        f"  Building area          = {c['building_area_km2']} km2\n"
        f"  Builtup area           = {c['builtup_area_percentage']}% of ward\n"
        f"  Roof area (85% of builtup) = {int(c['roof_area_m2']):,} m2\n"
        f"  Runoff coefficient     = {c['runoff_coefficient']}\n"
        f"  Captured (roof x rain x coeff) = {int(c['captured_litres_total']):,} litres\n"
        f"  Scaled to RWH adoption ({c['rwh_pct']}%) = {int(c['captured_litres_total']*c['rwh_pct']/100):,} litres\n"
        f"  RWH contribution       = {int(c['captured_litres_total']*c['rwh_pct']/100):,} / {c['population']:,} people = {c['rwh_lpcd']} lpcd ({c['rwh_mld']} MLD)"
    )

    facts = f"""
ZONE: {zone}
USER QUERY: {user_query}

=== USE THESE EXACT VALUES IN YOUR RESPONSE ===

FOR DIRECT ANSWER — use this sentence:
{"Total available water covers demand for " + zone + " tomorrow — the supply valve does not need to be opened. Supply surplus of " + str(c['surplus_lpcd']) + " lpcd + RWH " + str(c['rwh_lpcd']) + " lpcd = " + str(c['total_available']) + " lpcd available, which exceeds the " + str(c['norm_lpcd']) + " lpcd norm."
 if c['valve_hours'] == 0 else
 "The supply valve to " + zone + " should be opened for " + str(c['valve_hours']) + " hours tomorrow to release " + str(c['final_mld']) + " MLD (" + str(c['lpcd_equiv']) + " lpcd equivalent) of water."}

=== PRE-COMPUTED FACTS ===

STEP 1 — TOTAL AVAILABLE WATER:
  Formula: total_available = (supply - sewage_generated) + RWH

  Yesterday supply           = {c['supplied_lpcd']} lpcd ({c['supplied_mld']} MLD)
  Sewage generated           = {c['sewage_lpcd']} lpcd ({c['sewage_mld']} MLD)
    Sewage factor            = {c['sewage_factor']} (CPHEEO standard: 80% of supply returns as sewage)
  Surplus carried forward    = {c['supplied_lpcd']} - {c['sewage_lpcd']} = {c['surplus_lpcd']} lpcd
  RWH status                 = {rwh_status}
  Total available            = {c['surplus_lpcd']} (surplus) + {c['rwh_lpcd']} (RWH) = {c['total_available']} lpcd

STEP 2 — WATER TO RELEASE:
  Formula: water_to_release = demand - total_available

  Population                 = {c['population']:,}
  Demand (norm)              = {c['norm_lpcd']} lpcd
  Total available            = {c['total_available']} lpcd
  Water to release           = {c['norm_lpcd']} - {c['total_available']} = {c['adjusted_lpcd']} lpcd
  {'→ Total available exceeds demand — no release required' if c['demand_met'] else f'→ Release volume = {c["adjusted_lpcd"]} lpcd × {c["population"]:,} = {c["final_litres"]:,} litres = {c["required_mld"]} MLD'}

STEP 3 — POLICY CHECK:
  Policy limits              = Min {c['min_mld']} MLD, Max {c['max_mld']} MLD
  Policy state               = {c['policy_state']}
  Final release              = {c['final_mld']} MLD = {c['lpcd_equiv']} lpcd equivalent

STEP 4 — VALVE HOURS:
  Final release volume       = {c['final_litres']:,} litres
  Pipeline flow rate         = {c['flow_rate_lph']:,} lph
  Valve open duration        = {c['valve_hours']} hours
  Valve state                = {c['valve_state']}

SUPPORTING DATA:
  Groundwater level (GWL)    = {c['gwl']}m, {c['gwl_trend']} trend
  Current demand             = {c['demand_mld']} MLD
  Current deficit            = {c['deficit_mld']} MLD
""".strip()

    system = f"""You are a senior water distribution engineer at BWSSB Bangalore.

You will receive pre-computed facts. Copy the numbers exactly — do not recalculate anything.

Write exactly these four sections with these exact headers:

DIRECT ANSWER
{"Total available water covers demand for " + zone + " tomorrow — the supply valve does not need to be opened." if c['valve_hours'] == 0 else "The supply valve to " + zone + " should be opened for " + str(c['valve_hours']) + " hours tomorrow to release " + str(c['final_mld']) + " MLD (" + str(c['lpcd_equiv']) + " lpcd equivalent) of water."}

KEY FACTORS
Write steps using this exact format for each line — two spaces indent, label, two spaces, equals sign, two spaces, value:

Step 1 — Total available water  (supply - sewage_generated + RWH)
  Yesterday's supply    = {c['supplied_lpcd']} lpcd  ({c['supplied_mld']} MLD)
  Sewage generated      = {c['sewage_lpcd']} lpcd  ({c['sewage_factor']} x supply, CPHEEO standard)
  Surplus carried fwd   = {c['supplied_lpcd']} - {c['sewage_lpcd']} = {c['surplus_lpcd']} lpcd
  RWH contribution      = {c['rwh_lpcd']} lpcd
  Total available       = {c['surplus_lpcd']} + {c['rwh_lpcd']} = {c['total_available']} lpcd

Step 2 — RWH catchment calculation  (roof area x rainfall x runoff coefficient)
  RWH daily rainfall    = {c['monthly_rainfall_mm']}mm per month = {c['rainfall_mm']}mm per day
  RWH roof area (a)     = {int(c['roof_area_m2']):,} m2
  RWH rainfall (b)      = {c['rainfall_mm']}mm = {c['rainfall_m']}m
  RWH runoff coeff (c)  = {c['runoff_coefficient']}
  RWH volume (axbxc)    = {int(c['roof_area_m2']):,} m2 x {c['rainfall_m']}m x {c['runoff_coefficient']} = {c['captured_volume_m3']} m3
  RWH volume in litres  = {c['captured_volume_m3']} m3 x 1000 = {int(c['captured_litres_total']):,} litres
  RWH adoption scaling  = {int(c['captured_litres_total']):,} litres x {c['rwh_pct']}% = {c['rwh_contribution_litres']:,} litres
  RWH per capita        = {c['rwh_contribution_litres']:,} litres / {c['population']:,} people = {c['rwh_lpcd']} lpcd

Step 3 — Water to release  (demand - total_available)
  Demand (norm)         = {c['norm_lpcd']} lpcd
  Total available       = {c['total_available']} lpcd
  Water to release      = {c['norm_lpcd']} - {c['total_available']} = {c['adjusted_lpcd']} lpcd
  Release volume        = {c['final_litres']:,} litres = {c['required_mld']} MLD

(Steps 4 and 5 will be added automatically — do not write them.)

RISK ASSESSMENT
Write 3-4 bullet points. Each bullet starts with a dash. End each with — HIGH, — MEDIUM, or — LOW.

RECOMMENDATION
Write 3-4 numbered action steps."""

    try:
        raw = call_llm(
            system_prompt=system,
            user_message=facts,
            temperature=0.2,
            max_tokens=1400,
            ttl=TTL_LLM_SUMMARISE,
            cache_key_override=make_key("narrative", zone, facts)
        )
        result = _parse_sections(raw)

        # If all sections empty — LLM returned unexpected format, use fallback
        if all(v == "" for v in result.values()):
            print("  [formatter] parse failed — using Python fallback")
            return _fallback_sections(zone, c, "LLM format unrecognised")

        # Inject Python-computed Steps 4 and 5 into key_factors — never trust LLM for these
        result["key_factors"] = _inject_policy_valve_steps(result.get("key_factors", ""), c)

        return result

    except Exception as e:
        # Fallback — build sections directly from facts
        return _fallback_sections(zone, c, str(e))


def _inject_policy_valve_steps(key_factors: str, c: dict) -> str:
    """
    Replace whatever the LLM wrote for Steps 4 (Policy check) and 5 (Valve hours)
    with Python-computed values — these are pure arithmetic, LLM must not improvise.
    Strips any existing Step 4/5 content and appends the correct structured lines.
    """
    import re

    # Build the canonical Step 4 and 5 from Python facts
    step4 = (
        f"\nStep 4 — Policy check\n"
        f"  Policy limits         = Min {c['min_mld']} MLD, Max {c['max_mld']} MLD\n"
        f"  Policy state          = {c['policy_state']}\n"
        f"  Final release         = {c['final_mld']} MLD = {c['lpcd_equiv']} lpcd equivalent"
    )

    if c['valve_hours'] == 0:
        step5 = (
            f"\nStep 5 — Valve hours\n"
            f"  Valve open duration   = No release required — valve need not be opened"
        )
    else:
        step5 = (
            f"\nStep 5 — Valve hours\n"
            f"  Final release volume  = {c['final_litres']:,} litres\n"
            f"  Pipeline flow rate    = {c['flow_rate_lph']:,} lph\n"
            f"  Valve open duration   = {c['final_litres']:,} litres ÷ {c['flow_rate_lph']:,} lph = {c['valve_hours']} hours"
        )

    # Remove any existing Step 4 / Step 5 content the LLM may have written
    # (stops at next Step N or end of string)
    cleaned = re.sub(
        r'\n?Step\s*[45]\s*[—–-][^\n]*(?:\n(?!Step\s*[1-9]).*)*',
        '',
        key_factors,
        flags=re.IGNORECASE
    ).rstrip()

    return cleaned + step4 + step5


def _parse_sections(raw: str) -> dict:
    """
    Split LLM output into four section strings.
    Handles: markdown bold (**HEADER**), extra whitespace,
    lowercase headers, colon suffixes, content before first header.
    """
    sections = {"direct_answer": "", "key_factors": "",
                "risk_assessment": "", "recommendation": ""}

    # Normalise markers — strip **, #, colons, extra spaces
    MARKERS = {
        "DIRECT ANSWER":   "direct_answer",
        "KEY FACTORS":     "key_factors",
        "RISK ASSESSMENT": "risk_assessment",
        "RECOMMENDATION":  "recommendation",
    }

    def clean_line(line: str) -> str:
        """Strip markdown and punctuation to get plain uppercase text."""
        return line.strip().strip("*#_:").strip().upper()

    current = None
    for line in raw.splitlines():
        cleaned = clean_line(line)
        matched = next((m for m in MARKERS if cleaned.startswith(m)), None)
        if matched:
            current = MARKERS[matched]
        elif current and line.strip():
            # Strip markdown bold/italic from content lines
            content_line = line.replace("**", "").replace("__", "")
            sections[current] += content_line + "\n"

    for k in sections:
        sections[k] = sections[k].strip()

    # If all sections empty — LLM returned unexpected format, use fallback
    if all(v == "" for v in sections.values()):
        print(f"  [parse] WARNING: all sections empty. Raw response:\n{raw[:300]}")
        # Put everything in key_factors so content is not lost
        sections["direct_answer"] = "See key factors below."
        sections["key_factors"]   = raw.strip()

    print(f"  [parse] sections: " +
          " | ".join(f"{k}={len(v)} chars" for k, v in sections.items()))

    return sections


def _fallback_sections(zone: str, c: dict, error: str) -> dict:
    """
    Pure Python fallback — builds all four sections directly from computed facts.
    Called when LLM fails or returns unrecognised format.
    No LLM needed — output is deterministic and always correct.
    """
    # DIRECT ANSWER
    if c["valve_hours"] == 0:
        direct = (
            f"Total available water covers demand for {zone} tomorrow — "
            f"the supply valve does not need to be opened.\n"
            f"Supply surplus of {c['surplus_lpcd']} lpcd + RWH contribution of {c['rwh_lpcd']} lpcd "
            f"= {c['total_available']} lpcd available, which exceeds the {c['norm_lpcd']} lpcd norm."
        )
    else:
        direct = (
            f"The supply valve to {zone} should be opened for {c['valve_hours']} hours "
            f"tomorrow to release {c['final_mld']} MLD ({c['lpcd_equiv']} lpcd equivalent) of water."
        )

    # KEY FACTORS — clean aligned format
    captured_total = c.get('captured_litres_total', 0)
    captured_m3    = c.get('captured_volume_m3', 0)
    rwh_scaled     = int(captured_total * c['rwh_pct'] / 100)
    days_note = f"  RWH daily rainfall est = {c['monthly_rainfall_mm']}mm/month ÷ days in month = {c['rainfall_mm']}mm/day\n"
    rwh_line = (
        f"  RWH contribution      = {c['rwh_lpcd']} lpcd\n"
        f"{days_note}"
        f"  RWH roof area (a)     = {c['builtup_area_percentage']}% builtup × 85% roof = {int(c['roof_area_m2']):,} m2\n"
        f"  RWH rainfall (b)      = {c['rainfall_mm']}mm = {round(c['rainfall_mm']/1000, 5)} m\n"
        f"  RWH runoff coeff (c)  = {c['runoff_coefficient']}\n"
        f"  RWH volume (a×b×c)    = {int(c['roof_area_m2']):,} m2 × {round(c['rainfall_mm']/1000, 5)} m × {c['runoff_coefficient']} = {captured_m3:,.2f} m3\n"
        f"  RWH volume in litres  = {captured_m3:,.2f} m3 × 1000 = {int(captured_total):,} litres\n"
        f"  RWH adoption scaling  = {int(captured_total):,} × {c['rwh_pct']}% = {rwh_scaled:,} litres\n"
        f"  RWH per capita        = {rwh_scaled:,} ÷ {c['population']:,} people = {c['rwh_lpcd']} lpcd"
    )
    step2_line = (
        f"  Required release      = 0 MLD  (RWH covers full demand)"
        if c['demand_negative']
        else f"  Release volume        = {c['adjusted_lpcd']} lpcd \u00d7 {c['population']:,} = {c['final_litres']:,} litres = {c['required_mld']} MLD"
    )
    step4_line = (
        f"  Valve open duration   = 0 hours — valve need not be opened tomorrow"
        if c['valve_hours'] == 0
        else f"  Valve open duration   = {c['final_litres']:,} litres \u00f7 {c['flow_rate_lph']:,} lph = {c['valve_hours']} hours"
    )
    kf = (
        f"Step 1 — Total available water  (supply - sewage_generated + RWH)\n"
        f"  Yesterday's supply    = {c['supplied_lpcd']} lpcd  ({c['supplied_mld']} MLD)\n"
        f"  Sewage generated      = {c['sewage_lpcd']} lpcd  ({c['sewage_mld']} MLD, factor {c['sewage_factor']} per CPHEEO)\n"
        f"  Surplus carried fwd   = {c['supplied_lpcd']} - {c['sewage_lpcd']} = {c['surplus_lpcd']} lpcd\n"
        f"  RWH contribution      = {c['rwh_lpcd']} lpcd  (see Step 2 for calculation)\n"
        f"  Total available       = {c['surplus_lpcd']} + {c['rwh_lpcd']} = {c['total_available']} lpcd\n"
        f"\nStep 2 — RWH catchment calculation  (roof area × rainfall × runoff coefficient)\n"
        f"{rwh_line}\n"
        f"\nStep 3 — Water to release  (demand - total_available)\n"
        f"  Demand (norm)         = {c['norm_lpcd']} lpcd\n"
        f"  Total available       = {c['total_available']} lpcd\n"
        f"  Water to release      = {c['norm_lpcd']} - {c['total_available']} = {c['adjusted_lpcd']} lpcd"
        + (" → total available exceeds demand — no release needed\n" if c['demand_met'] else "\n")
        + step2_line + "\n"
        + f"\nStep 4 — Policy check\n"
        + f"  {c['policy_state']}\n"
        + f"  Final release         = {c['final_mld']} MLD = {c['lpcd_equiv']} lpcd equivalent\n"
        + f"\nStep 5 — Valve hours\n"
        + step4_line + "\n"
        + f"\nSupporting data\n"
        + f"  RWH: {c['rwh_houses']:,} of {c['total_houses']:,} houses ({c['rwh_pct']}%)  |  roof area {int(c['roof_area_m2']):,}m2\n"
        + f"  GWL: {c['gwl']}m, {c['gwl_trend']} trend  |  Deficit: {c['deficit_mld']} MLD"
    )

    # RISK ASSESSMENT
    risks = []
    if c['supplied_lpcd'] < c['norm_lpcd']:
        risks.append(f"- Yesterday supply {c['supplied_lpcd']} lpcd was below {c['norm_lpcd']} lpcd norm — MEDIUM")
    if c['gwl_trend'] == 'declining':
        risks.append(f"- Groundwater level {c['gwl']}m declining — MEDIUM")
    if c['rwh_lpcd'] > 0:
        risks.append(f"- RWH contributes {c['rwh_lpcd']} lpcd based on {c['rainfall_mm']}mm daily rainfall — if actual rainfall is lower, release quantity must be increased — MEDIUM")
    else:
        risks.append(f"- No rainfall expected — RWH contribution is 0 lpcd, full demand must come from piped supply — MEDIUM")
    if c['deficit_mld'] > 0:
        risks.append(f"- Current supply deficit of {c['deficit_mld']} MLD — MEDIUM")
    if not risks:
        risks.append("- No significant risks identified")

    # RECOMMENDATION
    if c['valve_hours'] == 0:
        rec = (
            f"1. The supply valve to {zone} does not need to be opened tomorrow.\n"
            f"2. RWH contribution of {c['rwh_lpcd']} lpcd combined with surplus covers the {c['norm_lpcd']} lpcd norm.\n"
            f"3. Keep valve on standby — open if actual rainfall is significantly lower than {c['rainfall_mm']}mm.\n"
            f"4. Monitor GWL trend — currently {c['gwl']}m and {c['gwl_trend']}."
        )
    else:
        rec = (
            f"1. Open the supply valve to {zone} for {c['valve_hours']} hours tomorrow.\n"
            f"2. Target release of {c['final_mld']} MLD to meet adjusted demand of {c['adjusted_lpcd']} lpcd.\n"
            f"3. RWH is contributing {c['rwh_lpcd']} lpcd based on estimated {c['rainfall_mm']}mm daily rainfall — adjust release if actual rainfall differs.\n"
            f"4. Monitor GWL — currently {c['gwl']}m with {c['gwl_trend']} trend."
        )

    return {
        "direct_answer":   direct,
        "key_factors":     kf,
        "risk_assessment": "\n".join(risks),
        "recommendation":  rec,
    }


# ── Non-release query handler ──────────────────────────────────────────────────

def build_general_narrative(user_query: str, db_results: list) -> dict:
    """For non-release queries — pass DB data to LLM for full narrative."""
    lines = [f"USER QUERY: {user_query}", "", "DATABASE RESULTS:"]
    for r in db_results:
        data = r.get("data", {})
        if isinstance(data, dict) and "error" not in data:
            lines.append(f"\n[{r.get('db','').upper()}]")
            for k, v in data.items():
                if v is not None and k not in {"monthly_gwl", "trend_7d", "thresholds"}:
                    lines.append(f"  {k}: {v}")

    system = """You are a senior water distribution engineer at BWSSB.
Write a clear response using the database results provided.
Output format must be EXACTLY as shown below:

DIRECT ANSWER
[2-3 sentences answering the question directly with specific numbers.]

KEY FACTORS
[Write 3-5 bullet points. Each bullet must explain the significance of a number — not just state it. Format: "• <what the number means and why it matters>". Example style:
• HSR Layout is facing a supply deficit of 1.02 MLD — demand stands at 30.5 MLD but only 29.48 MLD is being supplied, leaving residents short by about 5 lpcd
• Groundwater level is at 13.79m with a stable trend — no immediate stress but the long-term declining pattern across Bangalore warrants monitoring
• Monthly rainfall averages 63.2mm which is moderate — RWH systems in 15% of households provide limited buffer against supply shortfalls]

RISK ASSESSMENT
- [risk description] — HIGH / MEDIUM / LOW

RECOMMENDATION
1. [action step with specific number]
2. [action step]

Rules: each KEY FACTORS bullet starts with •, explains context not just numbers, no markdown bold."""

    try:
        raw = call_llm(
            system_prompt=system,
            user_message="\n".join(lines),
            temperature=0.2,
            max_tokens=600,
            ttl=TTL_LLM_SUMMARISE,
            cache_key_override=make_key("general", user_query)
        )
        return _parse_sections(raw)
    except Exception as e:
        return {
            "direct_answer":   f"Query: {user_query}",
            "key_factors":     "\n".join(lines[2:]),
            "risk_assessment": f"LLM unavailable: {e}",
            "recommendation":  "Please check the database results panel for details.",
        }


# ── Entry point ────────────────────────────────────────────────────────────────

def is_release_query(query: str) -> bool:
    q = query.lower()

    # Explicit exclusions — these contain "release" but are factual lookups,
    # not requests to calculate a release volume/valve schedule
    exclusion_patterns = [
        "policy limit", "policy for", "release polic",
        "min release", "max release", "minimum release", "maximum release",
        "release rule", "what is the policy", "what are the policy",
    ]
    if any(p in q for p in exclusion_patterns):
        return False

    keywords = ["release", "quantity to release", "how much water",
                "valve", "supply tomorrow", "water tomorrow"]
    return any(kw in q for kw in keywords)


def format_response(user_query: str, zone: str,
                    db_results: list, is_release_query: bool) -> dict:
    if is_release_query:
        c = compute_release(db_results)

        # Ward not found in DB — show clear error
        if c.get("_error"):
            return {
                "direct_answer":   f"No supply or RWH data found for '{zone}' in the database.",
                "key_factors":     f"Ward '{zone}' is not currently in the supply history or RWH database.\nPlease run '0. Seed Databases' in PyCharm to refresh, or check the ward name spelling.\nAvailable wards include: Jayanagar, Koramangala, HSR Layout, Basavanagudi, Malleswaram, Indiranagar, BTM Layout.",
                "risk_assessment": f"- Data unavailable for {zone} — HIGH\n- Cannot assess supply situation without historical data",
                "recommendation":  f"1. Check that '{zone}' is spelled correctly in your query.\n2. Run '0. Seed Databases' in PyCharm to populate supply data.\n3. Verify the ward exists in data/ward_data.csv.",
            }

        return build_narrative(zone, user_query, c)
    return build_general_narrative(user_query, db_results)
