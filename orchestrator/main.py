"""
Orchestrator — port 8000
Pipeline:
  1. UI submits user query
  2. LLM 1 decomposes query into sub-questions
  3. Orchestrator routes sub-questions to local SQLite DBs
  4. response_formatter computes release calculation in Python
  5. LLM 2 writes only RISK ASSESSMENT + RECOMMENDATION
  6. Structured response returned to UI
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
from datetime import datetime

from orchestrator.decomposer import decompose_query
from orchestrator.langchain_orchestrator import run_langchain_orchestration
from orchestrator.response_formatter import format_response, is_release_query
from orchestrator.cache import clear, stats

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
    direct_answer:   str
    key_factors:     str
    risk_assessment: str
    recommendation:  str
    final_answer:    str
    timestamp: str


@app.post("/query", response_model=QueryResponse)
def process_query(req: QueryRequest):

    # Step 2: LLM 1 decompose
    try:
        sub_questions = decompose_query(req.query)
    except Exception as e:
        raise HTTPException(500, f"Step 2 failed (LLM decomposition): {e}")

    # Step 3: LangChain DB orchestration
    try:
        db_results = run_langchain_orchestration(sub_questions)
    except Exception as e:
        raise HTTPException(500, f"LangChain orchestration failed: {e}")

    # Step 4-5: Python calculation + LLM for risk/recommendation only
    zone = next((sq.get("zone") for sq in sub_questions if sq.get("zone")), "the zone")
    release_q = is_release_query(req.query)

    sections = format_response(
        user_query=req.query,
        zone=zone,
        db_results=db_results,
        is_release_query=release_q
    )

    final_answer = "\n\n".join([
        f"DIRECT ANSWER\n{sections['direct_answer']}",
        f"KEY FACTORS\n{sections['key_factors']}",
        f"RISK ASSESSMENT\n{sections['risk_assessment']}",
        f"RECOMMENDATION\n{sections['recommendation']}",
    ])

    return QueryResponse(
        query=req.query,
        sub_questions=sub_questions,
        db_results=db_results,
        direct_answer=sections["direct_answer"],
        key_factors=sections["key_factors"],
        risk_assessment=sections["risk_assessment"],
        recommendation=sections["recommendation"],
        final_answer=final_answer,
        timestamp=datetime.now().isoformat()
    )


@app.get("/health")
def health():
    provider = os.environ.get("LLM_PROVIDER", "groq").lower()
    models = {
        "groq":      os.environ.get("GROQ_MODEL",      "llama-3.1-8b-instant"),
        "gemini":    os.environ.get("GEMINI_MODEL",    "gemini-1.5-flash"),
        "openai":    os.environ.get("OPENAI_MODEL",    "gpt-4o-mini"),
        "anthropic": os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
    }
    return {
        "status": "ok", "service": "orchestrator",
        "active_provider": provider,
        "active_model": models.get(provider, "unknown"),
        "dbs": "local sqlite"
    }

@app.get("/cache/stats")
def cache_stats():
    return stats()

@app.post("/cache/clear")
def cache_clear():
    clear()
    return {"status": "cache cleared"}
