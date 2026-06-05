
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
    If none of the sub-questions target ward_db but a zone is present,
    inject a ward_db sub-question automatically.
    """
    has_ward = any(sq.get("db") == "ward_db" for sq in sub_questions)
    if has_ward:
        return sub_questions  # already there — nothing to do

    # Find the zone from existing sub-questions
    zone = None
    for sq in sub_questions:
        if sq.get("zone"):
            zone = sq.get("zone")
            break

    if not zone:
        return sub_questions  # no zone found — can't inject meaningfully

    ward_sq = {
        "question": f"What is the groundwater level, population and rainfall trend for {zone}?",
        "db":           "ward_db",
        "model_needed": "none",
        "zone":         zone,
        "date":         "2025"
    }
    print(f"\n  [ward injected] Added ward_db sub-question for zone: {zone}")
    return sub_questions + [ward_sq]

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

You will receive a water management query and data fetched from four databases:
- RESERVOIR_DB: reservoir levels, inflow rates, weather
- DEMAND_DB: zone water demand, supply, deficit
- RULES_DB: release policy limits for the zone
- WARD_DB: ward-level groundwater level (GWL), population, rainfall, temperature

Write a detailed, actionable recommendation for the field operator.
Use ALL the data provided. Do not skip any database. Use specific numbers throughout.

Format your response EXACTLY as shown in this example — same sections, same style, same depth:

DIRECT ANSWER
one or two sentences with specific numbers (use MLD = Million Litres per Day)

KEY FACTORS
one or two sentences in numbered bullet points of the most relevant data from the databases, look at groundwater level, rainfall, population, demand etc.

RISK ASSESSMENT
one or two sentences in numbered bullet points on the anomalies seen, look at groundwater level, rainfall, population, demand etc


RECOMMENDATION
4-5 sentences in numbered bullet points on the recommendations based on the data from databases and the direct answer.
---EXAMPLE END---

Now follow the EXACT same format for the actual query below.
Use MLD (Million Litres per Day) for all water quantities.
Use metres (m) for groundwater levels, and also use population details.
Do not add any extra sections. Do not skip any section.
The format shown above is for reference only. Do not skip any database. Use specific numbers throughout. Do not use the numbers shown in the prompt
"""

    try:
        return call_llm(
            system_prompt=system,
            user_message=context,
            temperature=0.3,
            max_tokens=2000,        # 800 output + ~600 input = ~1400 total, well within limits
            ttl=TTL_LLM_SUMMARISE,
            cache_key_override=make_key("summarise", user_query)
        )
    except Exception as e:
        return f"Summary generation failed: {e}"
