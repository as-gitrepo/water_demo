"""
cache.py — file-based JSON cache for LLM responses and DB results.
No extra dependencies. Cache survives server restarts.

How it works:
  - Every call is hashed into a cache key (MD5 of inputs)
  - Results stored in data/cache.json as { key: { value, expires_at } }
  - TTL is configurable per call type
  - /cache/clear endpoint lets you wipe it during demo if needed
"""

import json, hashlib, os, time

CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache.json")

# TTL in seconds
TTL_LLM_DECOMPOSE  = 60 * 60 * 24 * 7  # 7 days  — sub-questions for same query never change
TTL_LLM_SUMMARISE  = 60 * 60 * 24      # 24 hours — summary stable within a day
TTL_DB_QUERY       = 60 * 60           # 1 hour   — DB data changes slowly


def _load():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(store):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(store, f, indent=2)


def make_key(*parts) -> str:
    """Hash any number of string parts into a short cache key."""
    combined = "||".join(str(p) for p in parts)
    return hashlib.md5(combined.encode()).hexdigest()


def get(key: str):
    """Return cached value if it exists and hasn't expired. None otherwise."""
    store = _load()
    entry = store.get(key)
    if not entry:
        return None
    if time.time() > entry["expires_at"]:
        # Expired — remove it
        del store[key]
        _save(store)
        return None
    return entry["value"]


def set(key: str, value, ttl: int):
    """Store value in cache with a TTL (seconds)."""
    store = _load()
    store[key] = {
        "value":      value,
        "expires_at": time.time() + ttl,
        "cached_at":  time.strftime("%Y-%m-%d %H:%M:%S")
    }
    _save(store)


def clear():
    """Wipe the entire cache file."""
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)


def stats():
    """Return cache stats — useful for the /cache/stats endpoint."""
    store = _load()
    now   = time.time()
    total   = len(store)
    alive   = sum(1 for e in store.values() if e["expires_at"] > now)
    expired = total - alive
    return {
        "total_entries": total,
        "alive":         alive,
        "expired":       expired,
        "api_calls_saved": alive,   # every alive entry = one saved API call
        "cache_file":    CACHE_FILE
    }
