
"""
LangChain orchestration layer.
"""

from langchain_core.runnables import RunnableLambda

from orchestrator.cache import TTL_LLM_SUMMARISE, make_key
from orchestrator.llm_client import call_llm
from orchestrator.router import TOOLS
import json

# =========================================================
# SINGLE TASK EXECUTION
# =========================================================

def execute_task(sub_question: dict):
    db_name = sub_question.get("db")
    print("\n================================")
    print(f"LangChain Routing → {db_name}")
    tool = TOOLS.get(db_name)

    if not tool:
        return {
            "error": f"No tool found for {db_name}"
        }

    # Pass zone and date as kwargs — matches all tool signatures
    try:
        result = tool.invoke({
            "zone": sub_question.get("zone") or "Jayanagar",
            "date": sub_question.get("date") or "today"
        })
    except Exception as e:
        result = {"error": str(e)}

    return {
        "question": sub_question.get("question"),
        "db":       db_name,
        "zone":     sub_question.get("zone"),
        "data":     result
    }

# =========================================================
# LANGCHAIN RUNNABLE
# =========================================================

execution_chain = RunnableLambda(execute_task)

# =========================================================
# WARD SUB-QUESTION INJECTION
# Always ensure ward_db is queried when a zone is mentioned.
# This is the safety net — if LLM 1 forgot to include ward_db,
# we add it here before LangChain executes.
# =========================================================

def inject_ward_subquestion(sub_questions: list) -> list:
    """
    Safety net — ensures supply_history_db, rwh_db and ward_db
    sub-questions are always present when a zone is mentioned.
    If LLM 1 forgot any of them, inject them here.
    """
    dbs_present = {sq.get("db") for sq in sub_questions}

    # Find zone from existing sub-questions
    zone = None
    for sq in sub_questions:
        if sq.get("zone"):
            zone = sq.get("zone")
            break

    if not zone:
        return sub_questions  # no zone — nothing to inject

    injected = list(sub_questions)

    if "sewage_db" not in dbs_present:
        injected.append({
            "question":     f"What is the sewage generated in {zone} yesterday and the surplus carried forward?",
            "db":           "sewage_db",
            "model_needed": "none",
            "zone":         zone,
            "date":         "yesterday"
        })
        print(f"  [injected] sewage_db for {zone}")

    if "supply_history_db" not in dbs_present:
        injected.append({
            "question":     f"What was the actual water supply to {zone} yesterday in lpcd?",
            "db":           "supply_history_db",
            "model_needed": "none",
            "zone":         zone,
            "date":         "yesterday"
        })
        print(f"  [injected] supply_history_db for {zone}")

    if "rwh_db" not in dbs_present:
        injected.append({
            "question":     f"How many houses in {zone} have rainwater harvesting and what is the RWH contribution?",
            "db":           "rwh_db",
            "model_needed": "none",
            "zone":         zone,
            "date":         "tomorrow"
        })
        print(f"  [injected] rwh_db for {zone}")

    if "ward_db" not in dbs_present:
        injected.append({
            "question":     f"What is the groundwater level and rainfall for {zone}?",
            "db":           "ward_db",
            "model_needed": "none",
            "zone":         zone,
            "date":         "2025"
        })
        print(f"  [injected] ward_db for {zone}")

    return injected

# =========================================================
# MAIN ORCHESTRATION FUNCTION
# =========================================================

def run_langchain_orchestration(sub_questions: list):
    print("\n================================")
    print("LANGCHAIN ORCHESTRATION STARTED")

    # Always include ward_db
    sub_questions = inject_ward_subquestion(sub_questions)

    results = []
    for sq in sub_questions:
        result = execution_chain.invoke(sq)
        results.append(result)

    print("\n================================")
    print("LANGCHAIN ORCHESTRATION COMPLETED")
    return results

# ── Step 4 → 5: Query DBs then summarise via LLM 2 ───────────────────────────

def _trim_db_results(db_results: list) -> list:
    """
    Remove only raw array fields — keep all scalar values intact.
    This keeps context rich but avoids token bloat from arrays.
    """
    STRIP_KEYS = {"monthly_gwl", "trend_7d", "thresholds"}
    trimmed = []
    for r in db_results:
        data = r.get("data", {})
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k not in STRIP_KEYS}
        trimmed.append({
            "question":  r.get("question", ""),
            "source_db": r.get("db", ""),
            "data":      data
        })
    return trimmed


def _build_context(user_query: str, db_results: list) -> str:
    """
    Build a clean readable context string from DB results.
    Formatted as plain text — easier for LLM to parse than raw JSON.
    """
    lines = [f"USER QUERY: {user_query}", "", "DATABASE ANSWERS:"]
    for r in _trim_db_results(db_results):
        lines.append(f"\n[{r['source_db'].upper()}] {r['question']}")
        data = r.get("data", {})
        if isinstance(data, dict) and "error" not in data:
            for k, v in data.items():
                if v is not None:
                    lines.append(f"  {k}: {v}")
        elif isinstance(data, dict) and "error" in data:
            lines.append(f"  ERROR: {data['error']}")
    return "\n".join(lines)


def summarise_with_llm(user_query: str,
                       sub_questions: list,
                       db_results: list) -> str:
    """
    LLM 2 call with caching.
    Uses plain-text context (more token-efficient than JSON)
    and a detailed system prompt for a rich, useful response.
    """
    context = _build_context(user_query, db_results)

    # Log token estimate (1 token ≈ 4 chars)
    estimated_tokens = len(context) // 4
    print(f"  [summarise] context ~{estimated_tokens} tokens")

    system = """You are a senior water distribution engineer at BWSSB (Bangalore Water Supply and Sewerage Board).

You will receive a water management query and data from these databases:
- SUPPLY_HISTORY_DB: yesterday's actual supply in lpcd and MLD, flow_rate_lph
- RWH_DB: rainwater harvesting house counts, tank sizes, rwh_contribution_lpcd, rwh_active flag
- WARD_DB: population, groundwater level (GWL), expected rainfall
- DEMAND_DB: current demand and deficit
- RULES_DB: min/max release policy limits in MLD

IMPORTANT — CALCULATION ORDER:
You must CALCULATE FIRST, then write your response.
Internally work through Steps 1-4 before writing anything.
The DIRECT ANSWER must reflect the FINAL result of your calculation — not an estimate.
NEVER write DIRECT ANSWER before completing all four calculation steps.

OUTPUT FORMAT — use exactly these four headers in this order:
DIRECT ANSWER
KEY FACTORS
RISK ASSESSMENT
RECOMMENDATION

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IF query is about water release or valve operation:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

First, silently work through these steps:
  CALC Step 1: adjusted_demand = 135 - supplied_lpcd - rwh_contribution_lpcd
               (use rwh_contribution_lpcd=0 if rwh_active=false)
  CALC Step 2: IF adjusted_demand <= 0 → required_release = 0 MLD
               ELSE → required_release = (adjusted_demand × population) / 1,000,000
  CALC Step 3: IF required_release < min_release_mld → final_release = min_release_mld
               IF required_release > max_release_mld → final_release = max_release_mld
               ELSE → final_release = required_release
               IF required_release = 0 AND policy has no mandatory minimum → final_release = 0
  CALC Step 4: IF final_release = 0 → valve_hours = 0
               ELSE → valve_hours = (final_release × 1,000,000) / flow_rate_lph

Now write your response using the calculated values:

DIRECT ANSWER
[Based on your calculation above, write ONE of these:]
• If valve_hours = 0:
  "RWH fully covers demand for <zone> tomorrow — the supply valve does not need to be opened. RWH contribution of <rwh_lpcd> lpcd combined with yesterday's supply of <supplied_lpcd> lpcd exceeds the 135 lpcd norm."
• If valve_hours > 0:
  "The supply valve to <zone> should be opened for <valve_hours> hours tomorrow to release <final_release> MLD (<lpcd_equiv> lpcd equivalent) of water."

KEY FACTORS
Step 1 — Adjusted demand (lpcd):
  Bangalore norm        = 135 lpcd
  Yesterday's supply   = <supplied_lpcd> lpcd (<supplied_mld> MLD for <population> people)
  RWH contribution      = <rwh_contribution_lpcd> lpcd (<rwh_pct>% of <total_houses> houses, <tank>L tanks, rainfall <mm>mm <≥/<> <threshold>mm, 20% fill)
  Adjusted demand       = 135 - <supplied_lpcd> - <rwh_contribution_lpcd> = <adjusted_demand> lpcd
  [If adjusted_demand ≤ 0: "Negative demand — RWH + yesterday supply exceed 135 lpcd norm. No piped supply required."]

Step 2 — Release volume:
  [If required_release = 0: "Required release = 0 MLD (RWH covers full demand)"]
  [If required_release > 0: "Release = <adjusted_demand> × <population> = <litres> litres = <MLD> MLD"]

Step 3 — Policy check:
  [State clearly: within limits / clamped to minimum / clamped to maximum / not required]
  Final release = <final_release> MLD

Step 4 — Valve hours:
  [If final_release = 0: "Valve hours = 0. Valve need not be opened tomorrow."]
  [If final_release > 0: "<final_litres> litres ÷ <flow_rate_lph> lph = <valve_hours> hours"]

Supporting data:
  - RWH: <rwh_houses> of <total_houses> houses (<rwh_pct>%) have RWH, avg tank <tank>L
  - GWL: <gwl>m, <trend>
  - Policy: Min <min_mld> MLD, Max <max_mld> MLD

RISK ASSESSMENT
- [Each risk on its own line with LOW / MEDIUM / HIGH]
- [If no supply needed: "RWH dependency HIGH — if rainfall < <threshold>mm, full 135 lpcd must come from pipe"]

RECOMMENDATION
[If valve_hours = 0:]
1. The supply valve to <zone> does not need to be opened tomorrow.
2. Verify rainfall forecast before withholding supply.
3. Keep valve on standby — open immediately if rainfall falls below <threshold>mm.
[If valve_hours > 0:]
1. Open the supply valve to <zone> for <valve_hours> hours tomorrow.
2. [Further steps]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IF query is about anything else (GWL, deficit, rainfall, population, policy):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DIRECT ANSWER
<2-3 sentences answering directly with specific numbers. Use lpcd wherever applicable.>

KEY FACTORS
- <bullet with data and numbers — use lpcd for all per-person water figures>
- <add as many bullets as needed>

RISK ASSESSMENT
- <each risk with LOW / MEDIUM / HIGH>
- If no risks: "No significant risks identified"

RECOMMENDATION
1. <action item>
2. <further steps>

ABSOLUTE RULES:
- NEVER write CASE A or CASE B in your response
- NEVER write DIRECT ANSWER before completing the calculation
- DIRECT ANSWER must match the valve_hours and final_release from your calculation exactly
- Use lpcd for per-capita figures, MLD for totals, metres for GWL
- Use ALL data from ALL databases
- Valve hours must be less than 10 — if > 10, split into two equal shifts"""

from orchestrator.cache import TTL_LLM_SUMMARISE, make_key
from orchestrator.llm_client import call_llm
from orchestrator.router import TOOLS
import json

# =========================================================
# SINGLE TASK EXECUTION
# =========================================================

def execute_task(sub_question: dict):
    db_name = sub_question.get("db")
    print("\n================================")
    print(f"LangChain Routing → {db_name}")
    tool = TOOLS.get(db_name)

    if not tool:
        return {
            "error": f"No tool found for {db_name}"
        }

    # Pass zone and date as kwargs — matches all tool signatures
    try:
        result = tool.invoke({
            "zone": sub_question.get("zone") or "Jayanagar",
            "date": sub_question.get("date") or "today"
        })
    except Exception as e:
        result = {"error": str(e)}

    return {
        "question": sub_question.get("question"),
        "db":       db_name,
        "zone":     sub_question.get("zone"),
        "data":     result
    }

# =========================================================
# LANGCHAIN RUNNABLE
# =========================================================

execution_chain = RunnableLambda(execute_task)

# =========================================================
# WARD SUB-QUESTION INJECTION
# Always ensure ward_db is queried when a zone is mentioned.
# This is the safety net — if LLM 1 forgot to include ward_db,
# we add it here before LangChain executes.
# =========================================================

def inject_ward_subquestion(sub_questions: list) -> list:
    """
    Safety net — ensures supply_history_db, rwh_db and ward_db
    sub-questions are always present when a zone is mentioned.
    If LLM 1 forgot any of them, inject them here.
    """
    dbs_present = {sq.get("db") for sq in sub_questions}

    # Find zone from existing sub-questions
    zone = None
    for sq in sub_questions:
        if sq.get("zone"):
            zone = sq.get("zone")
            break

    if not zone:
        return sub_questions  # no zone — nothing to inject

    injected = list(sub_questions)

    if "supply_history_db" not in dbs_present:
        injected.append({
            "question":     f"What was the actual water supply to {zone} yesterday in lpcd?",
            "db":           "supply_history_db",
            "model_needed": "none",
            "zone":         zone,
            "date":         "yesterday"
        })
        print(f"  [injected] supply_history_db for {zone}")

    if "rwh_db" not in dbs_present:
        injected.append({
            "question":     f"How many houses in {zone} have rainwater harvesting and what is the RWH contribution?",
            "db":           "rwh_db",
            "model_needed": "none",
            "zone":         zone,
            "date":         "tomorrow"
        })
        print(f"  [injected] rwh_db for {zone}")

    if "ward_db" not in dbs_present:
        injected.append({
            "question":     f"What is the groundwater level and rainfall for {zone}?",
            "db":           "ward_db",
            "model_needed": "none",
            "zone":         zone,
            "date":         "2025"
        })
        print(f"  [injected] ward_db for {zone}")

    return injected

# =========================================================
# MAIN ORCHESTRATION FUNCTION
# =========================================================

def run_langchain_orchestration(sub_questions: list):
    print("\n================================")
    print("LANGCHAIN ORCHESTRATION STARTED")

    # Always include ward_db
    sub_questions = inject_ward_subquestion(sub_questions)

    results = []
    for sq in sub_questions:
        result = execution_chain.invoke(sq)
        results.append(result)

    print("\n================================")
    print("LANGCHAIN ORCHESTRATION COMPLETED")
    return results

# ── Step 4 → 5: Query DBs then summarise via LLM 2 ───────────────────────────

def _trim_db_results(db_results: list) -> list:
    """
    Remove only raw array fields — keep all scalar values intact.
    This keeps context rich but avoids token bloat from arrays.
    """
    STRIP_KEYS = {"monthly_gwl", "trend_7d", "thresholds"}
    trimmed = []
    for r in db_results:
        data = r.get("data", {})
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k not in STRIP_KEYS}
        trimmed.append({
            "question":  r.get("question", ""),
            "source_db": r.get("db", ""),
            "data":      data
        })
    return trimmed


def _build_context(user_query: str, db_results: list) -> str:
    """
    Build a clean readable context string from DB results.
    Formatted as plain text — easier for LLM to parse than raw JSON.
    """
    lines = [f"USER QUERY: {user_query}", "", "DATABASE ANSWERS:"]
    for r in _trim_db_results(db_results):
        lines.append(f"\n[{r['source_db'].upper()}] {r['question']}")
        data = r.get("data", {})
        if isinstance(data, dict) and "error" not in data:
            for k, v in data.items():
                if v is not None:
                    lines.append(f"  {k}: {v}")
        elif isinstance(data, dict) and "error" in data:
            lines.append(f"  ERROR: {data['error']}")
    return "\n".join(lines)


def summarise_with_llm(user_query: str,
                       sub_questions: list,
                       db_results: list) -> str:
    """
    LLM 2 call with caching.
    Uses plain-text context (more token-efficient than JSON)
    and a detailed system prompt for a rich, useful response.
    """
    context = _build_context(user_query, db_results)

    # Log token estimate (1 token ≈ 4 chars)
    estimated_tokens = len(context) // 4
    print(f"  [summarise] context ~{estimated_tokens} tokens")

    system = """You are a senior water distribution engineer at BWSSB (Bangalore Water Supply and Sewerage Board).

You will receive a water management query and data from these databases:
- SUPPLY_HISTORY_DB: yesterday's actual supply in lpcd and MLD, flow_rate_lph
- RWH_DB: rainwater harvesting house counts, tank sizes, rwh_contribution_lpcd, rwh_active flag
- WARD_DB: population, groundwater level (GWL), expected rainfall
- DEMAND_DB: current demand and deficit
- RULES_DB: min/max release policy limits in MLD

CRITICAL OUTPUT RULES:
1. NEVER print "CASE A" or "CASE B" or any case label in your response
2. ALWAYS start your response with "DIRECT ANSWER" — never with anything else
3. Use EXACTLY these four section headers in this order:
   DIRECT ANSWER
   KEY FACTORS
   RISK ASSESSMENT
   RECOMMENDATION
4. If adjusted demand is negative or zero — state clearly that no supply is needed,
   then check if policy mandates a minimum release anyway

IF the query is about water release or valve operation:

DIRECT ANSWER
[One of these two sentences depending on adjusted demand:]
IF adjusted demand ≤ 0: "RWH fully covers the demand for <zone> tomorrow — the supply valve does not need to be opened. [If policy minimum applies: However, policy requires a minimum release of X MLD, so the valve must be opened for Y hours.]"
IF adjusted demand > 0: "The supply valve to <zone> should be opened for <X> hours tomorrow to release <Y> MLD (<Z> lpcd equivalent) of water."

KEY FACTORS
Step 1 — Adjusted demand (lpcd):
  Bangalore norm                     = 135 lpcd
  Yesterday's supply                 = <supplied_lpcd> lpcd  (<supplied_mld> MLD for <population> people)
  RWH contribution (<rwh_pct>% of <total_houses> houses, <tank>L tanks, rainfall <mm>mm <≥/< threshold>mm, 20% fill) = <rwh_contribution_lpcd> lpcd
  Adjusted demand                    = 135 - <supplied_lpcd> - <rwh_lpcd> = <result> lpcd
  [IF result ≤ 0: state "Adjusted demand is negative — RWH + yesterday's supply exceed the 135 lpcd norm. No additional piped supply is required from a demand perspective."]

Step 2 — Release volume:
  [IF adjusted demand ≤ 0:]
  Required release                   = 0 MLD (RWH covers full demand)
  [IF adjusted demand > 0:]
  Population                         = <population>
  Release volume                     = <adj_lpcd> × <population> = <litres> litres = <MLD> MLD

Step 3 — Policy check:
  [IF release = 0 and no policy minimum: "No release required. Valve need not be opened."]
  [IF release = 0 but policy mandates minimum: "Policy requires minimum release of <min> MLD even when demand is met by RWH."]
  [IF release > 0: state within limits / clamped to minimum / clamped to maximum]
  Final release                      = <MLD> MLD = <lpcd_equivalent> lpcd equivalent

Step 4 — Valve hours:
  [IF final release = 0: "Valve open duration = 0 hours. Valve need not be opened tomorrow."]
  [IF final release > 0:]
  Final release volume               = <litres> litres
  Pipeline flow rate                 = <flow_rate_lph> lph
  Valve open duration                = <litres> ÷ <flow_rate_lph> = <hours> hours

Supporting data:
  - RWH: <rwh_houses> of <total_houses> houses (<rwh_pct>%) have RWH, avg tank <tank>L
  - GWL: <gwl>m, <trend>
  - Policy: Min <min> MLD, Max <max> MLD

RISK ASSESSMENT
- <each risk on its own line with severity: LOW / MEDIUM / HIGH>
- [If no supply needed: "RWH dependency HIGH — if rainfall < threshold, full 135 lpcd must be supplied by pipe"]

RECOMMENDATION
[IF no supply needed:]
1. The supply valve to <zone> does not need to be opened tomorrow.
2. Confirm rainfall forecast is accurate before withholding supply.
3. Keep valve ready — open immediately if rainfall drops below <threshold>mm.
4. <further steps>
[IF supply needed:]
1. Open the main supply valve to <zone> for <X> hours tomorrow.
2. <further numbered action steps>

IF the query is about anything else (GWL, deficit, rainfall, population, policy):

DIRECT ANSWER
<2-3 sentences answering directly with specific numbers. Use lpcd wherever applicable.>

KEY FACTORS
- <bullet with data and numbers — use lpcd for all per-person water figures>
- <add as many bullets as needed — cover all relevant DB data>

RISK ASSESSMENT
- <each risk with LOW / MEDIUM / HIGH>
- If no risks: write "No significant risks identified"

RECOMMENDATION
1. <action item 1>
2. <further steps as needed>

ABSOLUTE RULES:
- NEVER start with CASE A or CASE B — start directly with DIRECT ANSWER
- Use lpcd for ALL per-capita figures, MLD for zone totals, metres for GWL
- Use ALL data from ALL databases — never say "no data available" for RWH_DB
- If RWH_DB shows rwh_active=false, state "RWH not active (rainfall below threshold)" and use 0 lpcd
- Show specific numbers throughout — no vague statements
- Valve hours must always be less than 10 — if > 10, split into two equal shifts"""

    try:
        return call_llm(
            system_prompt=system,
            user_message=context,
            temperature=0.3,
            max_tokens=800,        # 800 output + ~600 input = ~1400 total, well within limits
            ttl=TTL_LLM_SUMMARISE,
            cache_key_override=make_key("summarise", user_query)
        )
    except Exception as e:
        return f"Summary generation failed: {e}"
