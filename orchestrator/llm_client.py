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
                "max_tokens":  max_tokens,
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
                    "temperature":     0,
                    "maxOutputTokens": 6000

                }
            },
            timeout=60
        )
        _raise_for_status(resp, "Gemini")
        print("\n========== SUMMARY OUTPUT ==========")
        print(resp.json())
        print("===================================\n")

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

import os
import requests


class OpenRouterProvider:
    def _check_key(self):
        if not os.getenv("OPENROUTER_API_KEY"):
            raise ValueError(
                "OPENROUTER_API_KEY not found in .env"
            )

    def call(
        self,
        system_prompt,
        user_message,
        temperature=0,
        max_tokens=1000
    ):

        self._check_key()

        model = os.getenv(
            "OPENROUTER_MODEL",
            "~google/gemini-flash-latest"
        )

        print(f"  [provider] OpenRouter → {model}")

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization":
                    f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                "Content-Type":
                    "application/json",
                "HTTP-Referer":
                    "http://localhost:8000",
                "X-Title":
                    "Water Release Demo"
            },
            json=payload,
            timeout=60
        )

        if response.status_code != 200:
            raise Exception(
                f"OpenRouter API error "
                f"{response.status_code}: "
                f"{response.text}"
            )

        data = response.json()

        return (
            data["choices"][0]
                ["message"]
                ["content"]
                .strip()
        )

# ══════════════════════════════════════════════════════════════════════════════
# FACTORY — reads LLM_PROVIDER from .env and returns the right provider
# ══════════════════════════════════════════════════════════════════════════════

PROVIDERS = {
    "groq":      GroqProvider,
    "gemini":    GeminiProvider,
    "openai":    OpenAIProvider,
    "anthropic": AnthropicProvider,
    "openrouter": OpenRouterProvider
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
        raise RuntimeError(f"{provider_name} rate limit hit. Wait 10 seconds and retry.")
    if not resp.ok:
        raise RuntimeError(f"{provider_name} API error {resp.status_code}: {resp.text}")


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
    """
    provider_name = os.environ.get("LLM_PROVIDER", "groq").lower()
    cache_key = cache_key_override if cache_key_override else make_key("llm", user_message)

    if use_cache:
        cached = get(cache_key)
        if cached:
            print(f"  [cache HIT]  key={cache_key[:12]}...")
            return cached
        print(f"  [cache MISS] key={cache_key[:12]}... — calling {provider_name}")

    try:
        provider = _get_provider()
        result   = provider.call(system_prompt, user_message, temperature, max_tokens)
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot reach {provider_name} API. Check your internet connection.\n"
            "Tip: if on venue WiFi, switch to your mobile hotspot."
        )

    if use_cache:
        set(cache_key, result, ttl)
        print(f"  [cache SET]  key={cache_key[:12]}... ttl={ttl}s")

    return result


def parse_json_response(raw: str):
    """Robustly extract JSON from LLM response — handles markdown fences."""
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("[") or part.startswith("{"):
                raw = part
                break

    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = raw.find(start_char)
        end   = raw.rfind(end_char) + 1
        if start != -1 and end > 0:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                continue

    raise ValueError(f"Could not extract JSON from LLM response:\n{raw}")
