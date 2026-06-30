#!/bin/bash
# ============================================================
#  IWAS Water Distribution AI — Setup & Run (macOS / Linux)
#  Works on a machine with NOTHING installed — will install
#  Python itself if it's missing or too old.
# ============================================================
set -e
cd "$(dirname "$0")"

REQUIRED_PY_MAJOR=3
REQUIRED_PY_MINOR=10   # minimum acceptable Python 3.x

echo ""
echo "======================================"
echo "  IWAS Water AI — Setup"
echo "======================================"

# ── 0. Detect OS ───────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
  Darwin*) PLATFORM="mac" ;;
  Linux*)  PLATFORM="linux" ;;
  *)       PLATFORM="unknown" ;;
esac
echo "→ Detected platform: $PLATFORM"

# ── 1. Find a usable Python 3 ───────────────────────────────
find_python() {
  for candidate in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      ver=$("$candidate" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo "0.0")
      major=$(echo "$ver" | cut -d. -f1)
      minor=$(echo "$ver" | cut -d. -f2)
      if [ "$major" -eq "$REQUIRED_PY_MAJOR" ] && [ "$minor" -ge "$REQUIRED_PY_MINOR" ]; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON_BIN="$(find_python || true)"

if [ -z "$PYTHON_BIN" ]; then
  echo "→ No suitable Python 3.${REQUIRED_PY_MINOR}+ found. Installing..."

  if [ "$PLATFORM" = "mac" ]; then
    if ! command -v brew >/dev/null 2>&1; then
      echo "→ Homebrew not found — installing Homebrew first..."
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
      if [ -d "/opt/homebrew/bin" ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
      elif [ -d "/usr/local/bin" ]; then
        eval "$(/usr/local/bin/brew shellenv)"
      fi
    fi
    echo "→ Installing Python 3.11 via Homebrew..."
    brew install python@3.11
    PYTHON_BIN="python3.11"

  elif [ "$PLATFORM" = "linux" ]; then
    echo "→ Installing Python 3.11 via apt (requires sudo)..."
    if command -v apt-get >/dev/null 2>&1; then
      sudo apt-get update -y
      sudo apt-get install -y software-properties-common
      sudo add-apt-repository -y ppa:deadsnakes/ppa 2>/dev/null || true
      sudo apt-get update -y
      sudo apt-get install -y python3.11 python3.11-venv python3.11-distutils
      PYTHON_BIN="python3.11"
    elif command -v dnf >/dev/null 2>&1; then
      sudo dnf install -y python3.11
      PYTHON_BIN="python3.11"
    elif command -v yum >/dev/null 2>&1; then
      sudo yum install -y python3.11
      PYTHON_BIN="python3.11"
    else
      echo "✗ Could not detect a supported package manager (apt/dnf/yum)."
      echo "  Please install Python 3.10+ manually: https://www.python.org/downloads/"
      exit 1
    fi
  else
    echo "✗ Unsupported or undetected platform: $OS"
    echo "  Please install Python 3.10+ manually: https://www.python.org/downloads/"
    exit 1
  fi
fi

echo "✓ Using Python: $($PYTHON_BIN --version)"

# ── 2. Virtual environment ──────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "→ Creating virtual environment..."
  "$PYTHON_BIN" -m venv .venv
fi
source .venv/bin/activate

# ── 3. Install ALL dependencies ─────────────────────────────
echo "→ Installing dependencies (this may take a minute on first run)..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "✓ Dependencies installed"

# ── 4. Load .env and check API key ──────────────────────────
if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    echo "→ No .env found — creating one from .env.example..."
    cp .env.example .env
    echo ""
    echo "⚠  A .env file has been created for you at: $(pwd)/.env"
    echo "   Open it and add your API key, then re-run this script."
    echo ""
    exit 1
  fi
fi

set -a
source .env
set +a

PROVIDER="${LLM_PROVIDER:-groq}"
echo "→ LLM Provider: $PROVIDER"

KEY_MISSING=false
case "$PROVIDER" in
  groq)
    if [ -z "$GROQ_API_KEY" ] || [ "$GROQ_API_KEY" = "gsk_your_key_here" ]; then
      KEY_MISSING=true; KEY_NAME="GROQ_API_KEY"; SIGNUP="https://console.groq.com"
    fi ;;
  gemini)
    if [ -z "$GEMINI_API_KEY" ] || [ "$GEMINI_API_KEY" = "your_key_here" ]; then
      KEY_MISSING=true; KEY_NAME="GEMINI_API_KEY"; SIGNUP="https://aistudio.google.com/app/apikey"
    fi ;;
  openai)
    if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "sk-your_key_here" ]; then
      KEY_MISSING=true; KEY_NAME="OPENAI_API_KEY"; SIGNUP="https://platform.openai.com/api-keys"
    fi ;;
  anthropic)
    if [ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "sk-ant-your_key_here" ]; then
      KEY_MISSING=true; KEY_NAME="ANTHROPIC_API_KEY"; SIGNUP="https://console.anthropic.com"
    fi ;;
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

# ── 5. Seed databases (only if not already seeded) ──────────
if [ ! -f "data/supply.db" ] || [ ! -s "data/supply.db" ]; then
  echo "→ Seeding core databases (reservoir, demand, rules, supply, sewage)..."
  python data/seed.py
  echo "✓ Core databases seeded"
else
  echo "✓ Core databases already seeded (delete data/*.db to reseed)"
fi

if [ -f "data/ward_data.csv" ]; then
  if [ ! -f "data/ward.db" ] || [ ! -s "data/ward.db" ]; then
    echo "→ Seeding ward database from data/ward_data.csv..."
    python data/seed_ward.py
    echo "✓ Ward database seeded"
  else
    echo "✓ Ward database already seeded"
  fi
else
  echo ""
  echo "⚠  data/ward_data.csv not found — ward DB will be empty."
  echo "   Place your CSV at data/ward_data.csv and re-run to populate it."
  echo ""
fi

# ── 6. Start orchestrator ────────────────────────────────────
echo ""
echo "======================================"
echo "  Starting IWAS orchestrator..."
echo "  Open http://localhost:8000 in your browser"
echo "  Press Ctrl+C to stop"
echo "======================================"
echo ""

PYTHONPATH=. uvicorn orchestrator.main:app --port 8000
