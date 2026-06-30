"""
Decomposer: user query → Groq API (LLM) → structured sub-questions
LLM runs in Groq cloud — zero RAM on your laptop.
"""

from orchestrator.llm_client import call_llm, parse_json_response
from orchestrator.cache import make_key, TTL_LLM_DECOMPOSE

SYSTEM_PROMPT = """You are a water distribution planning assistant for BWSSB (Bangalore Water Supply).

IMPORTANT: Your response must be a raw JSON array only.
- Do NOT include any explanation, reasoning, thinking, or commentary
- Do NOT use markdown or ```json fences
- Do NOT write anything before or after the JSON array
- Start your response with [ and end with ]

Given a user query about water distribution, decompose it into specific sub-questions.
Each sub-question must be answerable by querying one of these databases:
- reservoir_db: reservoir water levels, inflow rates, evaporation, weather forecasts
- demand_db: zone-wise water demand, consumption history, supply deficits
- rules_db: release policies, min/max release limits for the zone
- ward_db: ward-level groundwater level (GWL), population, rainfall, temperature
- supply_history_db: actual water supplied to a ward yesterday in lpcd and MLD, valve hours
- rwh_db: rainwater harvesting house counts, roof area catchment, RWH water contribution in lpcd

Always generate ALL of these sub-questions when asked about water release for a zone:
1. What was the actual supply to <zone> yesterday? → supply_history_db
2. What is the expected rainfall in <zone> tomorrow? → ward_db
3. How many houses in <zone> have rainwater harvesting and what is the RWH contribution? → rwh_db
4. What is the current demand and deficit for <zone>? → demand_db
5. What are the release policy limits for <zone>? → rules_db

Each item in the array must have exactly these keys:
{
  "question": "specific question text",
  "db": one of the db names above,
  "model_needed": "none",
  "zone": "zone name or null",
  "date": "YYYY or tomorrow or yesterday or null"
}

Example output for "What is water quantity to be released to Jayanagar tomorrow?":
[
  {"question": "What was the actual water supply to Jayanagar yesterday in lpcd?", "db": "supply_history_db", "model_needed": "none", "zone": "Jayanagar", "date": "yesterday"},
  {"question": "What is the expected rainfall in Jayanagar tomorrow?", "db": "ward_db", "model_needed": "none", "zone": "Jayanagar", "date": "tomorrow"},
  {"question": "How many houses in Jayanagar have rainwater harvesting and what is the RWH water contribution?", "db": "rwh_db", "model_needed": "none", "zone": "Jayanagar", "date": "tomorrow"},
  {"question": "What is the current water demand and deficit for Jayanagar?", "db": "demand_db", "model_needed": "none", "zone": "Jayanagar", "date": null},
  {"question": "What are the min and max release policy limits for Jayanagar?", "db": "rules_db", "model_needed": "none", "zone": "Jayanagar", "date": null},
  {"question": "What is the groundwater level trend for Jayanagar?", "db": "ward_db", "model_needed": "none", "zone": "Jayanagar", "date": "2025"}
]"""


def decompose_query(user_query: str) -> list:
    """Call Groq LLM to decompose user query into structured sub-questions."""
    raw = call_llm(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_query,
        temperature=0.1,
        max_tokens=2000,       # increased — Gemini tokeniser needs more room for JSON array
        ttl=TTL_LLM_DECOMPOSE,
        cache_key_override=make_key("decompose", user_query)  # stable key — query only
    )
    return parse_json_response(raw)


if __name__ == "__main__":
    import json
    q = "What is the water quantity to be released to Jayanagar tomorrow?"
    print(f"Query: {q}\n")
    result = decompose_query(q)
    print(json.dumps(result, indent=2))
