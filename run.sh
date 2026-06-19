#!/bin/bash
# ============================================================
#  BWSSB Water Distribution AI — Setup & Run (M2 Pro)
# ============================================================
cd "$(dirname "$0")"

echo ""
echo "======================================"
echo "  BWSSB Water AI — Setup"
echo "======================================"

# ── 1. Virtual environment ─────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "→ Creating virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate

# ── 2. Install ALL dependencies ────────────────────────────
echo "→ Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet \
  fastapi \
  "uvicorn[standard]" \
  requests \
  pydantic \
  python-dotenv \
  langchain \
  langchain-core
echo "✓ Dependencies installed"

# ── 3. Load .env and check API key ────────────────────────
if [ -f ".env" ]; then
  set -a
  source .env
  set +a
fi

# Detect which provider is configured
PROVIDER="${LLM_PROVIDER:-groq}"
echo "→ LLM Provider: $PROVIDER"

# Check the right API key is set
KEY_MISSING=false
case "$PROVIDER" in
  groq)
    [ -z "$GROQ_API_KEY" ]      && KEY_MISSING=true && KEY_NAME="GROQ_API_KEY"      && SIGNUP="https://console.groq.com" ;;
  gemini)
    [ -z "$GEMINI_API_KEY" ]    && KEY_MISSING=true && KEY_NAME="GEMINI_API_KEY"    && SIGNUP="https://aistudio.google.com/app/apikey" ;;
  openai)
    [ -z "$OPENAI_API_KEY" ]    && KEY_MISSING=true && KEY_NAME="OPENAI_API_KEY"    && SIGNUP="https://platform.openai.com/api-keys" ;;
  anthropic)
    [ -z "$ANTHROPIC_API_KEY" ] && KEY_MISSING=true && KEY_NAME="ANTHROPIC_API_KEY" && SIGNUP="https://console.anthropic.com" ;;
esac

if [ "$KEY_MISSING" = true ]; then
  echo ""
  echo "⚠  $KEY_NAME not set."
  echo "   Sign up at $SIGNUP"
  echo "   Then add to .env: $KEY_NAME=your_key_here"
  echo "   Then re-run this script."
  echo ""
  exit 1
fi
echo "✓ API key found for $PROVIDER"

# ── 4. Seed reservoir / demand / rules databases ──────────
echo "→ Seeding reservoir, demand and rules databases..."
python3 data/seed.py
echo "✓ Core databases seeded"

# ── 5. Seed ward database from CSV ────────────────────────
if [ -f "data/ward_data.csv" ]; then
  echo "→ Seeding ward database from data/ward_data.csv..."
  python3 data/seed_ward.py
  echo "✓ Ward database seeded"
else
  echo ""
  echo "⚠  data/ward_data.csv not found — ward DB will be empty."
  echo "   Place your CSV at data/ward_data.csv and re-run to populate it."
  echo "   Expected columns: Year,Month,Ward_NO,Ward_Name,Building_Area_km2,"
  echo "   Builtup_Area_Percentage,Population,Rainfall,RH2M,T2M_MAX,T2M_MIN,WS2M,GWL"
  echo ""
fi

# ── 6. Start orchestrator ─────────────────────────────────
echo ""
echo "======================================"
echo "  Starting orchestrator..."
echo "  Open http://localhost:8000 in Chrome"
echo "======================================"
echo ""

PYTHONPATH=. uvicorn orchestrator.main:app --port 8000 --reload
