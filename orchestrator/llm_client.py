"""
llm_client.py — multi-provider LLM client.

Switch provider by setting LLM_PROVIDER in your .env file:
  LLM_PROVIDER=groq        (default — free, fast)
  LLM_PROVIDER=gemini      (Google Gemini)
  LLM_PROVIDER=openai      (OpenAI GPT)
  LLM_PROVIDER=anthropic   (Claude)

Each provider also needs its own API key in .env — see .env.example.
"""

import requests, os, json
from abc import ABC, abstractmethod
from dotenv import load_dotenv
from orchestrator.cache import get, set, make_key, TTL_LLM_DECOMPOSE

load_dotenv(override=True)  # override=True ensures .env always wins over stale os.environ


# ══════════════════════════════════════════════════════════════════════════════
# BASE CLASS — all providers implement this
# ══════════════════════════════════════════════════════════════════════════════

class LLMProvider(ABC):
    """Abstract base — every provider must implement call()."""

    @abstractmethod
    def call(self, system_prompt: str, user_message: str,
             temperature: float, max_tokens: int) -> str:
        """Make the API call and return the raw text response."""
        pass

    def _check_key(self, key_name: str, signup_url: str):
        """Raise a clear error if the API key is missing."""
        if not os.environ.get(key_name, ""):
            raise RuntimeError(
                f"{key_name} not set.\n"
                f"1. Sign up at {signup_url}\n"
                f"2. Create an API key\n"
                f"3. Add to .env: {key_name}=your_key_here\n"
                f"4. Restart the orchestrator"
            )


# ══════════════════════════════════════════════════════════════════════════════
# GROQ  (default — free tier, llama-3.1-8b-instant)
# ══════════════════════════════════════════════════════════════════════════════

class GroqProvider(LLMProvider):
    URL = "https://api.groq.com/openai/v1/chat/completions"

    def call(self, system_prompt, user_message, temperature, max_tokens):
        self._check_key("GROQ_API_KEY", "https://console.groq.com")
        model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
        print(f"  [provider] Groq → {model}")
        resp = requests.post(
            self.URL,
            headers={
                "Authorization": f"Bearer {os.environ['GROQ_API_KEY']}",
                "Content-Type":  "application/json"
            },
            json={
                "model":       model,
                "temperature": temperature,
                "max_tokens":  4000,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message}
                ]
            },
            timeout=30
        )
        _raise_for_status(resp, "Groq")
        return resp.json()["choices"][0]["message"]["content"].strip()


# ══════════════════════════════════════════════════════════════════════════════
# GEMINI  (Google — gemini-1.5-flash default)
# ══════════════════════════════════════════════════════════════════════════════

class GeminiProvider(LLMProvider):

    def call(self, system_prompt, user_message, temperature, max_tokens):
        self._check_key("GEMINI_API_KEY", "https://aistudio.google.com/app/apikey")
        model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
        print(f"  [provider] Gemini → {model}")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
            f"?key={os.environ['GEMINI_API_KEY']}"
        )
        resp = requests.post(
            url,
            json={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"parts": [{"text": user_message}]}],
                "generationConfig": {
                    "temperature":     temperature,
                    "maxOutputTokens": 6000
                }
            },
            timeout=70
        )
        _raise_for_status(resp, "Gemini")
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


# ══════════════════════════════════════════════════════════════════════════════
# OPENAI  (GPT-4o-mini default)
# ══════════════════════════════════════════════════════════════════════════════

class OpenAIProvider(LLMProvider):
    URL = "https://api.openai.com/v1/chat/completions"

    def call(self, system_prompt, user_message, temperature, max_tokens):
        self._check_key("OPENAI_API_KEY", "https://platform.openai.com/api-keys")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        print(f"  [provider] OpenAI → {model}")
        resp = requests.post(
            self.URL,
            headers={
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type":  "application/json"
            },
            json={
                "model":       model,
                "temperature": temperature,
                "max_tokens":  max_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message}
                ]
            },
            timeout=30
        )
        _raise_for_status(resp, "OpenAI")
        return resp.json()["choices"][0]["message"]["content"].strip()


# ══════════════════════════════════════════════════════════════════════════════
# ANTHROPIC  (Claude — claude-3-haiku default)
# ══════════════════════════════════════════════════════════════════════════════

class AnthropicProvider(LLMProvider):
    URL = "https://api.anthropic.com/v1/messages"

    def call(self, system_prompt, user_message, temperature, max_tokens):
        self._check_key("ANTHROPIC_API_KEY", "https://console.anthropic.com")
        model = os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
        print(f"  [provider] Anthropic → {model}")
        resp = requests.post(
            self.URL,
            headers={
                "x-api-key":         os.environ["ANTHROPIC_API_KEY"],
                "anthropic-version": "2023-06-01",
                "Content-Type":      "application/json"
            },
            json={
                "model":       model,
                "system":      system_prompt,
                "max_tokens":  max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "user", "content": user_message}
                ]
            },
            timeout=30
        )
        _raise_for_status(resp, "Anthropic")
        return resp.json()["content"][0]["text"].strip()


# ══════════════════════════════════════════════════════════════════════════════
# FACTORY — reads LLM_PROVIDER from .env and returns the right provider
# ══════════════════════════════════════════════════════════════════════════════

PROVIDERS = {
    "groq":      GroqProvider,
    "gemini":    GeminiProvider,
    "openai":    OpenAIProvider,
    "anthropic": AnthropicProvider,
}

def _get_provider() -> LLMProvider:
    name = os.environ.get("LLM_PROVIDER", "groq").lower()
    cls  = PROVIDERS.get(name)
    if not cls:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER '{name}'. "
            f"Choose from: {', '.join(PROVIDERS.keys())}"
        )
    return cls()


# ══════════════════════════════════════════════════════════════════════════════
# ERROR HELPER
# ══════════════════════════════════════════════════════════════════════════════

def _raise_for_status(resp, provider_name: str):
    if resp.status_code == 401:
        raise RuntimeError(f"Invalid API key for {provider_name}. Check your .env file.")
    if resp.status_code == 429:
        # Signal retry — caught by call_llm
        raise RateLimitError(f"{provider_name} rate limit hit.")
    if not resp.ok:
        raise RuntimeError(f"{provider_name} API error {resp.status_code}: {resp.text}")


class RateLimitError(Exception):
    """Raised on 429 — signals call_llm to retry with backoff."""
    pass


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC INTERFACE — same as before, callers don't change
# ══════════════════════════════════════════════════════════════════════════════

def call_llm(system_prompt: str,
             user_message: str,
             temperature: float = 0.1,
             max_tokens: int = 1000,
             ttl: int = TTL_LLM_DECOMPOSE,
             use_cache: bool = True,
             cache_key_override: str = None) -> str:
    """
    Call the configured LLM provider and return the response text.
    Provider is set via LLM_PROVIDER in .env (default: groq).
    Results are cached by default.
    Automatically retries up to 3 times on rate limit (429) with backoff.
    """
    import time

    provider_name = os.environ.get("LLM_PROVIDER", "groq").lower()
    cache_key = cache_key_override if cache_key_override else make_key("llm", user_message)

    # ── Cache check ───────────────────────────────────────────────────────────
    if use_cache:
        cached = get(cache_key)
        if cached:
            print(f"  [cache HIT]  key={cache_key[:12]}...")
            return cached
        print(f"  [cache MISS] key={cache_key[:12]}... — calling {provider_name}")

    # ── Call with retry on rate limit ─────────────────────────────────────────
    # Backoff: 15s → 30s → 60s  (Gemini free tier resets every 60s)
    retry_waits = [15, 30, 60]
    last_error  = None

    for attempt, wait in enumerate(retry_waits, start=1):
        try:
            provider = _get_provider()
            result   = provider.call(system_prompt, user_message, temperature, max_tokens)
            break   # success — exit retry loop

        except RateLimitError as e:
            last_error = e
            if attempt <= len(retry_waits):
                print(f"  [rate limit] attempt {attempt} — waiting {wait}s before retry...")
                time.sleep(wait)
            continue

        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Cannot reach {provider_name} API. Check your internet connection.\n"
                "Tip: if on venue WiFi, switch to your mobile hotspot."
            )
    else:
        # All retries exhausted
        raise RuntimeError(
            f"Rate limit persists after 3 retries ({sum(retry_waits)}s total wait).\n"
            f"Options:\n"
            f"  1. Switch to Groq: set LLM_PROVIDER=groq in .env (faster + higher limits)\n"
            f"  2. Upgrade Gemini to paid tier at https://ai.google.dev/pricing\n"
            f"  3. Wait 60 seconds and try again"
        )

    # ── Cache the result ──────────────────────────────────────────────────────
    if use_cache:
        set(cache_key, result, ttl)
        print(f"  [cache SET]  key={cache_key[:12]}... ttl={ttl}s")

    return result


def parse_json_response(raw: str):
    """
    Robustly extract JSON from LLM response.
    Handles: markdown fences, thinking/reasoning preamble,
    trailing commentary, and mixed text+JSON (common in Gemini).
    """
    if not raw:
        raise ValueError("Empty response from LLM")

    # Step 1: Extract content inside ```json ... ``` fences if present
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.lower().startswith("json"):
                part = part[4:].strip()
            if part.startswith("[") or part.startswith("{"):
                try:
                    return json.loads(part)
                except json.JSONDecodeError:
                    pass  # try next part

    # Step 2: Find the outermost [ ] or { } — handles preamble/postamble text
    # Try array first (expected for decompose), then object
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = raw.find(start_char)
        if start == -1:
            continue
        # Walk backwards from end to find matching closing bracket
        depth = 0
        end   = -1
        for i, ch in enumerate(raw[start:], start=start):
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end != -1:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                continue

    raise ValueError(
        f"Could not extract JSON from LLM response.\n"
        f"Raw response (first 300 chars):\n{raw[:300]}"
    )
