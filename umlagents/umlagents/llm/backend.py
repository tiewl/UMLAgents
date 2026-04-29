"""
LLM backend abstraction layer.

Provides a clean interface for multiple LLM providers (Anthropic, DeepSeek, or any
OpenAI-compatible API). Uses only Python stdlib — no pip packages required.

Usage:
    backend = LLMBackendFactory.create("deepseek")
    response = backend.chat_complete(system_prompt, user_prompt, temperature=0.7, max_tokens=4096)
"""

import os
import json
import time
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Optional


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class LLMError(RuntimeError):
    """Base exception for LLM API errors."""
    pass

class InsufficientCreditsError(LLMError):
    """Raised when the API key has no remaining credits or billing is exhausted."""
    pass

class LLMTimeoutError(LLMError):
    """Raised when the LLM API call times out."""
    pass


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class LLMBackend(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    def chat_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """
        Send a chat completion request and return the response text.

        Args:
            system_prompt: System-level instructions for the model
            user_prompt: The user's message / task
            temperature: Sampling temperature (0.0 - 1.0)
            max_tokens: Maximum tokens in the response

        Returns:
            Generated response text

        Raises:
            InsufficientCreditsError: API key exhausted or billing issue
            LLMError: Other API or network errors
        """
        ...


# ---------------------------------------------------------------------------
# Anthropic Backend (Messages API)
# ---------------------------------------------------------------------------

class AnthropicBackend(LLMBackend):
    """
    Calls Anthropic's Messages API via stdlib urllib.

    Endpoint: POST https://api.anthropic.com/v1/messages
    Auth: x-api-key header
    """

    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.model = os.getenv("UMLAGENTS_DEFAULT_MODEL", "claude-sonnet-4-6")
        # Per-agent override handled by BaseAgent before passing here
        self.timeout = 180

        if not self.api_key or self.api_key.startswith("your_"):
            print("[WARNING] ANTHROPIC_API_KEY not set. AI features will be disabled.")

    def _build_payload(self, system_prompt: str, user_prompt: str,
                       temperature: float, max_tokens: int) -> bytes:
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": temperature,
        }
        return json.dumps(body).encode("utf-8")

    def _build_request(self, payload: bytes) -> urllib.request.Request:
        req = urllib.request.Request(
            self.API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": self.API_VERSION,
            },
            method="POST",
        )
        return req

    def _parse_response(self, body: dict) -> str:
        """Extract response text from Anthropic response JSON."""
        content = body.get("content", [])
        if not content:
            raise LLMError(f"Empty content in Anthropic response: {body}")
        # Anthropic returns content as a list of blocks; text is in content[0].text
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    return block.get("text", "")
            raise LLMError(f"No text block in Anthropic response content: {body}")
        return str(content)

    def _check_billing_error(self, error_text: str):
        """Check if error indicates credit/billing exhaustion."""
        lower = error_text.lower()
        if "credit balance is too low" in lower or "billing" in lower or "insufficient" in lower:
            raise InsufficientCreditsError(error_text)

    def chat_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        if not self.api_key or self.api_key.startswith("your_"):
            raise LLMError("ANTHROPIC_API_KEY not configured. Cannot call AI API.")

        payload = self._build_payload(system_prompt, user_prompt, temperature, max_tokens)
        req = self._build_request(payload)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                response_body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            self._check_billing_error(error_body)
            raise LLMError(f"Anthropic API HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise LLMError(f"Anthropic API connection error: {e.reason}")
        except TimeoutError:
            raise LLMTimeoutError("Anthropic API request timed out")

        return self._parse_response(response_body)


# ---------------------------------------------------------------------------
# DeepSeek Backend (OpenAI-compatible Chat Completions API)
# ---------------------------------------------------------------------------

class DeepSeekBackend(LLMBackend):
    """
    Calls DeepSeek's OpenAI-compatible Chat Completions API via stdlib urllib.

    Endpoint: POST {base_url}/chat/completions  (default: https://api.deepseek.com/v1)
    Auth: Authorization: Bearer header
    """

    def __init__(self, model: Optional[str] = None):
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
        self.model = model or os.getenv("UMLAGENTS_DEEPSEEK_MODEL", "deepseek-v4-pro")
        self.timeout = 180

        if not self.api_key or self.api_key == "your_deepseek_api_key_here":
            print("[WARNING] DEEPSEEK_API_KEY not set. AI features will be disabled.")

    @property
    def api_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _build_payload(self, system_prompt: str, user_prompt: str,
                       temperature: float, max_tokens: int) -> bytes:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        return json.dumps(body).encode("utf-8")

    def _build_request(self, payload: bytes) -> urllib.request.Request:
        req = urllib.request.Request(
            self.api_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        return req

    def _parse_response(self, body: dict) -> str:
        """Extract response text from OpenAI-compatible response JSON."""
        choices = body.get("choices", [])
        if not choices:
            raise LLMError(f"No choices in DeepSeek response: {body}")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not content:
            raise LLMError(f"Empty content in DeepSeek response: {body}")
        return content

    def _check_billing_error(self, error_text: str):
        lower = error_text.lower()
        if "credit balance" in lower or "insufficient" in lower or "billing" in lower:
            raise InsufficientCreditsError(error_text)

    def chat_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        if not self.api_key or self.api_key == "your_deepseek_api_key_here":
            raise LLMError("DEEPSEEK_API_KEY not configured. Cannot call AI API.")

        payload = self._build_payload(system_prompt, user_prompt, temperature, max_tokens)
        req = self._build_request(payload)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                response_body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            self._check_billing_error(error_body)
            raise LLMError(f"DeepSeek API HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise LLMError(f"DeepSeek API connection error: {e.reason}")
        except TimeoutError:
            raise LLMTimeoutError("DeepSeek API request timed out")

        return self._parse_response(response_body)


# ---------------------------------------------------------------------------
# OpenAI / Generic OpenAI-Compatible Backend
# ---------------------------------------------------------------------------

class OpenAIBackend(LLMBackend):
    """
    Calls any OpenAI-compatible Chat Completions API via stdlib urllib.

    Endpoint: POST {base_url}/chat/completions
    Auth: Authorization: Bearer header

    Can be used for OpenAI, OpenRouter, Together AI, Groq, or any OpenAI-compatible provider.

    Config via env vars:
        UMLAGENTS_OPENAI_API_KEY  — API key (defaults to OPENAI_API_KEY)
        UMLAGENTS_OPENAI_BASE_URL — Base URL (default: https://api.openai.com/v1)
        UMLAGENTS_OPENAI_MODEL    — Model name (default: gpt-4o)
    """

    def __init__(self, model: Optional[str] = None):
        self.api_key = os.getenv("UMLAGENTS_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        self.base_url = os.getenv("UMLAGENTS_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.getenv("UMLAGENTS_OPENAI_MODEL", "gpt-4o")
        self.timeout = 180

        if not self.api_key or self.api_key.startswith("your_"):
            print("[WARNING] OpenAI API key not set. AI features will be disabled.")

    @property
    def api_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _build_payload(self, system_prompt: str, user_prompt: str,
                       temperature: float, max_tokens: int) -> bytes:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        return json.dumps(body).encode("utf-8")

    def _build_request(self, payload: bytes) -> urllib.request.Request:
        req = urllib.request.Request(
            self.api_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        return req

    def _parse_response(self, body: dict) -> str:
        choices = body.get("choices", [])
        if not choices:
            raise LLMError(f"No choices in OpenAI response: {body}")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not content:
            raise LLMError(f"Empty content in OpenAI response: {body}")
        return content

    def _check_billing_error(self, error_text: str):
        lower = error_text.lower()
        if "credit balance" in lower or "insufficient" in lower or "billing" in lower or "429" in error_text:
            raise InsufficientCreditsError(error_text)

    def chat_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        if not self.api_key or self.api_key.startswith("your_"):
            raise LLMError("OpenAI API key not configured. Cannot call AI API.")

        payload = self._build_payload(system_prompt, user_prompt, temperature, max_tokens)
        req = self._build_request(payload)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                response_body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            self._check_billing_error(error_body)
            raise LLMError(f"OpenAI API HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise LLMError(f"OpenAI API connection error: {e.reason}")
        except TimeoutError:
            raise LLMTimeoutError("OpenAI API request timed out")

        return self._parse_response(response_body)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class LLMBackendFactory:
    """
    Creates the appropriate LLM backend based on configuration.

    Provider is selected via UMLAGENTS_LLM_PROVIDER env var (default: "anthropic").
    Supported values: "anthropic", "deepseek", "openai", "openai-compatible".
    """

    _PROVIDER_MAP = {
        "anthropic": AnthropicBackend,
        "deepseek": DeepSeekBackend,
        "openai": OpenAIBackend,
        "openai-compatible": OpenAIBackend,
    }

    @staticmethod
    def create(provider: Optional[str] = None, model: Optional[str] = None) -> LLMBackend:
        """
        Create an LLM backend instance.

        Args:
            provider: Provider name. If None, reads from UMLAGENTS_LLM_PROVIDER env var.
                      Falls back to "anthropic".
            model: Optional model override for providers that support it.

        Returns:
            An LLMBackend instance.

        Raises:
            ValueError: If provider is unknown.
        """
        if provider is None:
            provider = os.getenv("UMLAGENTS_LLM_PROVIDER", "anthropic").lower()

        provider = provider.lower().replace("-", "").replace("_", "")
        # Normalize aliases
        alias_map = {
            "anthropic": "anthropic",
            "claude": "anthropic",
            "deepseek": "deepseek",
            "ds": "deepseek",
            "openai": "openai",
            "openai compatible": "openai",
            "gpt": "openai",
            "openrouter": "openai",
            "together": "openai",
        }
        resolved = alias_map.get(provider, provider)

        backend_class = LLMBackendFactory._PROVIDER_MAP.get(resolved)
        if backend_class is None:
            raise ValueError(
                f"Unknown LLM provider: '{provider}'. "
                f"Supported: {', '.join(LLMBackendFactory._PROVIDER_MAP.keys())}"
            )

        # DeepSeekBackend and OpenAIBackend accept a model override
        if resolved in ("deepseek", "openai") and model is not None:
            return backend_class(model=model)

        return backend_class()
