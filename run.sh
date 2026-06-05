#!/bin/bash
# ============================================================
#  BWSSB Water Distribution AI — Setup & Run (M2 Pro)
# ============================================================
set -e
cd "$(dirname "$0")"

echo ""
echo "======================================"
echo "  BWSSB Water AI — Setup"
echo "======================================"

# 1. Virtual environment
if [ ! -d ".venv" ]; then
  echo "→ Creating virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate

# 2. Install dependencies
echo "→ Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet fastapi "uvicorn[standard]" requests pydantic python-dotenv
echo "✓ Dependencies installed"

# 3. Check API key
if [ -z "$GROQ_API_KEY" ]; then
  if [ -f ".env" ]; then export $(cat .env | xargs); fi
fi
if [ -z "$GROQ_API_KEY" ]; then
  echo ""
  echo "⚠  GROQ_API_KEY not set."
  echo "   Get a free key at https://console.groq.com"
  echo "   Then create a .env file: GROQ_API_KEY=gsk_..."
  echo ""
fi

# 4. Seed databases (first time only)
echo "→ Seeding databases..."
python3 data/seed.py

echo ""
echo "======================================"
echo "  Starting orchestrator..."
echo "  Open http://localhost:8000 in Chrome"
echo "======================================"
echo ""

PYTHONPATH=. uvicorn orchestrator.main:app --port 8000 --reload
