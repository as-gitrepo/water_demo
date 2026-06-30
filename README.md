# IWAS — Integrated Water Management Advisory System

AI-powered water release planning tool for BWSSB Bangalore, built with FastAPI,
LangChain, and local SQLite databases. Works with Groq, Gemini, OpenAI, or
Anthropic — switch providers with one line in `.env`.

## Quick Start — works on a machine with nothing installed

You do **not** need to install Python, pip, or any libraries yourself.
The setup script detects what's missing and installs it automatically.

### macOS / Linux
```bash
./run.sh
```

### Windows
Double-click `run.bat`, or run from Command Prompt:
```cmd
run.bat
```

### What the script does automatically
1. Detects if Python 3.10+ is installed
   - **macOS**: installs via Homebrew (installs Homebrew too, if missing)
   - **Linux**: installs via apt/dnf/yum
   - **Windows**: installs via winget
2. Creates a Python virtual environment (`.venv/`)
3. Installs all required packages (`requirements.txt`)
4. Creates `.env` from `.env.example` on first run and pauses for you to add an API key
5. Seeds all SQLite databases (reservoir, demand, rules, supply, ward, sewage)
6. Starts the server at **http://localhost:8000**

### First-time setup
1. Run the script once — it will create `.env` and stop, asking for an API key
2. Open `.env`, add a free API key from one provider (Groq is fastest to set up — https://console.groq.com)
3. Run the script again — it will start the server

### Re-running later
Just run `./run.sh` (or `run.bat`) again — it skips reinstalling Python/packages
and reseeding databases if they already exist, so startup after the first run
takes a few seconds.

### Resetting the databases
Delete the `.db` files in `data/` and re-run the script to reseed from scratch:
```bash
rm data/*.db data/cache.json
./run.sh
```

## Manual setup (if you prefer not to use the script)
```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then add your API key
python data/seed.py
python data/seed_ward.py
PYTHONPATH=. uvicorn orchestrator.main:app --port 8000
```

## Architecture
```
User query → LLM 1 (decompose) → LangChain orchestrator → local SQLite DBs
           → Python calculation engine → LLM 2 (narrative) → structured UI
```

- `orchestrator/` — FastAPI backend, LLM clients, calculation engine
- `data/` — SQLite databases and seed scripts
- `static/index.html` — frontend UI (single file, no build step)

## Deploy to Render (give anyone a public URL)

This app can be hosted on [Render](https://render.com) for free, giving you a
public URL you can share with anyone — no install required on their end.

### Steps

1. **Push this project to a GitHub repository** (Render deploys from git).
   ```bash
   git init
   git add .
   git commit -m "IWAS water demo"
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```

2. **Create a new Web Service on Render**
   - Go to https://dashboard.render.com → New → Web Service
   - Connect your GitHub repo
   - Render will detect `render.yaml` automatically (Blueprint deploy) — or set manually:
     - **Build Command**: `pip install -r requirements.txt && python data/seed.py && python data/seed_ward.py`
     - **Start Command**: `uvicorn orchestrator.main:app --host 0.0.0.0 --port $PORT`
     - **Runtime**: Python 3

3. **Add your API key as an environment variable**
   - In the Render dashboard, go to your service → Environment
   - Add: `GROQ_API_KEY` = your actual key (get one free at https://console.groq.com)
   - `LLM_PROVIDER` is already set to `groq` in `render.yaml` — change it there or
     in the dashboard if you want to use Gemini/OpenAI/Anthropic instead

4. **Deploy** — Render builds and starts the service automatically.
   You'll get a URL like `https://iwas-water-ai.onrender.com` — share this with
   anyone, no setup needed on their side, it just opens in a browser.

### Notes on the free tier
- Render's free tier spins the service down after 15 minutes of inactivity.
  The first request after idle takes ~30-50 seconds to wake up — this is
  normal, just let it load once before a demo.
- The SQLite databases are rebuilt fresh on every deploy (via the build
  command), so data resets each time you redeploy — fine for a demo, not
  meant for production data persistence.
- For an always-on instance with no spin-down, upgrade to a paid Render plan.
