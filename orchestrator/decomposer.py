"""
Decomposer: user query → Groq API (LLM) → structured sub-questions
LLM runs in Groq cloud — zero RAM on your laptop.
"""

from orchestrator.llm_client import call_llm, parse_json_response
from orchestrator.cache import make_key, TTL_LLM_DECOMPOSE

SYSTEM_PROMPT = """You are a water distribution planning assistant for BWSSB (Bangalore Water Supply).

Given a user query about water distribution, decompose it into specific sub-questions.
Each sub-question must be answerable by querying one of these databases:
- reservoir_db: reservoir water levels, inflow rates, evaporation, weather forecasts
- demand_db: zone-wise water demand, consumption history, supply deficits
- rules_db: release policies, compliance thresholds, priority levels
- ward_db: ward-level groundwater level (GWL), population, rainfall, temperature,
           humidity, builtup area percentage — data available for 2016 (all wards)
           and 2024/2025 (Jayanagar ward only)

Return ONLY a JSON array. No explanation, no markdown, no preamble, no ```json fences.
Each item must have exactly these keys:
{
  "question": "specific question text",
  "db": "reservoir_db" or "demand_db" or "rules_db" or "ward_db",
  "model_needed": "none",
  "zone": "zone name or null",
  "date": "YYYY or tomorrow or null"
}

Example — for "What is the groundwater level in Jayanagar in 2025?":
[
  {"question": "What is the groundwater level for Jayanagar in 2025?", "db": "ward_db", "model_needed": "none", "zone": "Jayanagar", "date": "2025"},
  {"question": "What is Jayanagar demand and supply deficit?", "db": "demand_db", "model_needed": "none", "zone": "Jayanagar", "date": null},
  {"question": "What are the release policy limits for Jayanagar?", "db": "rules_db", "model_needed": "none", "zone": "Jayanagar", "date": null}
]

Example — for "How much water to release to Jayanagar tomorrow?":
[
  {"question": "What is the current reservoir level and inflow rate?", "db": "reservoir_db", "model_needed": "none", "zone": "Jayanagar", "date": "tomorrow"},
  {"question": "What is Jayanagar projected demand?", "db": "demand_db", "model_needed": "none", "zone": "Jayanagar", "date": "tomorrow"},
  {"question": "What are the release policy limits for Jayanagar?", "db": "rules_db", "model_needed": "none", "zone": "Jayanagar", "date": null},
  {"question": "What is the groundwater, population, rainfall  trend for Jayanagar?", "db": "ward_db", "model_needed": "none", "zone": "Jayanagar", "date": "2025"}
]"""


def decompose_query(user_query: str) -> list:
    """Call Groq LLM to decompose user query into structured sub-questions."""
    raw = call_llm(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_query,
        temperature=0.1,
        max_tokens=1000,
        ttl=TTL_LLM_DECOMPOSE,
        cache_key_override=make_key("decompose", user_query)  # stable key — query only
    )
    print("\n========== RAW LLM RESPONSE ==========")
    print(raw)
    print("=====================================\n")
    return parse_json_response(raw)


if __name__ == "__main__":
    import json
    q = "What is the water quantity to be released to Jayanagar tomorrow?"
    print(f"Query: {q}\n")
    result = decompose_query(q)
    print(json.dumps(result, indent=2))
