# BWSSB Water Distribution AI — Demo

AI-powered water release planning. Fully local except two Groq API calls.

## Pipeline

```
User query
    ↓
LLM 1 — Groq API        (decompose query → sub-questions)
    ↓
Orchestrator            (routes sub-questions to local SQLite DBs)
    ↓
SQLite databases        (reservoir.db, demand.db, rules.db)
    ↓
LLM 2 — Groq API        (user query + DB answers → plain English summary)
    ↓
Answer shown to user
```

## Project structure

```
water_demo/
├── .env                        ← Create this with your Groq key
├── .env.example                ← Template
├── run.sh                      ← One-command start
├── requirements.txt
│
├── orchestrator/
│   ├── main.py                 ← FastAPI app, full pipeline
│   ├── decomposer.py           ← LLM 1: query → sub-questions
│   ├── router.py               ← Routes sub-questions to DBs
│   └── llm_client.py           ← Shared Groq API client
│
├── data/
│   ├── seed.py                 ← Seeds all 3 SQLite databases
│   ├── reservoir.db            ← (auto-created on first run)
│   ├── demand.db
│   └── rules.db
│
└── static/
    └── tml              ← Demo UI
```

## Quick start

```bash
# 1. Get a free Groq API key at https://console.groq.com
echo "GROQ_API_KEY=gsk_your_key_here" > .env

# 2. Run
chmod +x run.sh && ./run.sh

# 3. Open in Chrome
open http://localhost:8000
```

## PyCharm setup

1. Open the `water_demo` folder in PyCharm
2. Set Python interpreter to a new virtualenv (Python 3.11)
3. Install deps in PyCharm terminal: `pip install -r requirements.txt`
4. Run configs (auto-loaded from `.idea/runConfigurations/`):
   - `0. Seed Databases` — run once on first use
   - `3. Orchestrator`   — run every time, then open http://localhost:8000

## Groq API key in PyCharm

Either create a `.env` file in the project root, or add it directly in the
run config: Run → Edit Configurations → `3. Orchestrator` → Environment Variables
→ add `GROQ_API_KEY = gsk_your_key_here`
