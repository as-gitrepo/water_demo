"""
cache.py — in-memory cache with file backup.

On Render: uses in-memory dict (fast, works within a session).
Locally: also saves to data/cache.json so cache survives server restarts.

TTLs:
  TTL_LLM_DECOMPOSE  = 7 days
  TTL_LLM_SUMMARISE  = 24 hours
  TTL_DB_QUERY       = 1 hour
"""

import json, hashlib, os, time

TTL_LLM_DECOMPOSE  = 60 * 60 * 24 * 7
TTL_LLM_SUMMARISE  = 60 * 60 * 24
TTL_DB_QUERY       = 60 * 60

CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache.json")

# ── In-memory store — shared across all requests in the same process ──────────
_store: dict = {}


def make_key(*parts) -> str:
    combined = "||".join(str(p) for p in parts)
    return hashlib.md5(combined.encode()).hexdigest()


def get(key: str):
    """Return cached value or None if missing/expired."""
    entry = _store.get(key)
    if not entry:
        # Try loading from file (useful on first request after local restart)
        _load_from_file()
        entry = _store.get(key)
    if not entry:
        return None
    if time.time() > entry["expires_at"]:
        del _store[key]
        return None
    print(f"  [cache HIT] key={key[:12]}...")
    return entry["value"]


def set(key: str, value, ttl: int):
    """Store value with TTL (seconds)."""
    _store[key] = {
        "value":      value,
        "expires_at": time.time() + ttl,
        "cached_at":  time.strftime("%Y-%m-%d %H:%M:%S")
    }
    print(f"  [cache SET] key={key[:12]}... ttl={ttl}s  (total entries: {len(_store)})")
    _save_to_file()   # best-effort — silently skipped if filesystem is read-only


def clear():
    _store.clear()
    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
        except Exception:
            pass


def stats():
    now = time.time()
    alive = sum(1 for e in _store.values() if e["expires_at"] > now)
    return {
        "backend":       "memory",
        "total_entries": len(_store),
        "alive":         alive,
        "expired":       len(_store) - alive,
    }


def _load_from_file():
    """Load persisted cache from file into memory (local dev convenience)."""
    if not os.path.exists(CACHE_FILE):
        return
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        now = time.time()
        loaded = 0
        for k, v in data.items():
            if v.get("expires_at", 0) > now:
                _store[k] = v
                loaded += 1
        if loaded:
            print(f"  [cache] Loaded {loaded} entries from file")
    except Exception:
        pass


def _save_to_file():
    """Best-effort save to file — skipped silently if not writable (Render)."""
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(_store, f, indent=2)
    except Exception:
        pass  # Render ephemeral filesystem — fine, memory cache still works
