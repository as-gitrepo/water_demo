"""
Orchestrator — port 8000
Pipeline:
  1. UI submits user query
  2. LLM 1 (Groq) decomposes query into sub-questions
  3. Orchestrator routes sub-questions to local SQLite DBs
  4. Orchestrator collects all DB answers
  5. LLM 2 (Groq) receives user query + DB answers → summary
  6. Orchestrator returns final answer to UI
Everything runs locally except the two Groq API calls.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os, json
from datetime import datetime

from orchestrator.decomposer import decompose_query
from orchestrator.langchain_orchestrator import (
    run_langchain_orchestration, summarise_with_llm
)
from orchestrator.llm_client import call_llm
from orchestrator.cache import get, set, make_key, clear, stats, TTL_DB_QUERY, TTL_LLM_SUMMARISE

STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

app = FastAPI(title="Water Orchestrator")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC, "index.html"))


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    query: str
    sub_questions: list
    db_results: list
    final_answer: str
    timestamp: str



# ── Main pipeline endpoint ─────────────────────────────────────────────────────

@app.post("/query", response_model=QueryResponse)
def process_query(req: QueryRequest):

    # ── Step 2: LLM 1 (Groq) — decompose query (cached 24h) ─────────────────
    try:
        sub_questions = decompose_query(req.query)
    except Exception as e:
        raise HTTPException(500, f"Step 2 failed (LLM decomposition): {e}")

    # ── Step 3: Query local DBs (each result cached 30 mins) ─────────────────
    '''db_results = []
    for sq in sub_questions:
        cache_key = make_key("db", sq.get("db"), sq.get("zone"), sq.get("date"))
        cached_data = get(cache_key)
        if cached_data:
            print(f"  [cache HIT] DB query: {sq.get('db')} / {sq.get('zone')}")
            data = cached_data
        else:
            try:
                data = route_and_query(sq)
            except Exception as e:
                data = {"error": str(e)}
            set(cache_key, data, TTL_DB_QUERY)
            print(f"  [cache SET] DB query: {sq.get('db')} / {sq.get('zone')}")

        db_results.append({
            "question": sq.get("question", ""),
            "db":       sq.get("db", "unknown"),
            "zone":     sq.get("zone"),
            "data":     data
        })'''

    # ── Step 3: LangChain DB orchestration ─────────────────

    try:
        db_results = run_langchain_orchestration(
            sub_questions
        )
    except Exception as e:
        raise HTTPException(
            500,
            f"LangChain orchestration failed: {e}"
        )


    # ── Step 4 → 5: LLM 2 (Groq) — summarise (cached 2h) ────────────────────
    final_answer = summarise_with_llm(req.query, sub_questions, db_results)

    # ── Step 6: Return collated response ──────────────────────────────────────
    return QueryResponse(
        query=req.query,
        sub_questions=sub_questions,
        db_results=db_results,
        final_answer=final_answer,
        timestamp=datetime.now().isoformat()
    )


@app.get("/health")
def health():
    provider = os.environ.get("LLM_PROVIDER", "groq").lower()
    models = {
        "groq":      os.environ.get("GROQ_MODEL",      "llama-3.1-8b-instant"),
        "gemini":    os.environ.get("GEMINI_MODEL",    "gemini-flash-latest"),
        "openai":    os.environ.get("OPENAI_MODEL",    "gpt-4o-mini"),
        "anthropic": os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
    }
    return {
        "status":           "ok",
        "service":          "orchestrator",
        "active_provider":  provider,
        "active_model":     models.get(provider, "unknown"),
        "dbs":              "local sqlite"
    }

@app.get("/cache/stats")
def cache_stats():
    """See how many entries are cached and how many have expired."""
    return stats()

@app.post("/cache/clear")
def cache_clear():
    """Wipe the cache — useful during demo if you want fresh LLM responses."""
    clear()
    return {"status": "cache cleared"}
