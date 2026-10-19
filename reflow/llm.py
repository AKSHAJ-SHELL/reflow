"""Model I/O: one prompt-in, text-out call. OWNER: AGENT (task M-01).

Contract
--------
complete(system: str, prompt: str, *, max_tokens: int = 4096) -> Completion

load_model(config) reads provider, model, api_key, base_url, and timeout_s
from the dict the caller passes. max_attempts and compile_cap belong to the
harness and are not applied here. The model id is config["model"] only.

Must never
----------
- hardcode a model id or an API key,
- read a config file or process environment,
- retry, keep conversation history, or call tools,
- turn reply text into a part number.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

_PROVIDERS = frozenset({"anthropic", "openai", "openai-compatible"})
_REQUIRED = ("provider", "model", "api_key", "base_url", "timeout_s")
_ANTHROPIC_VERSION = "2023-06-01"


class ModelError(RuntimeError):
    """The provider call failed (auth, rate limit, network, bad request)."""


@dataclass
class Completion:
    text: str
    model: str            # "provider/model-id"
    input_tokens: int
    output_tokens: int


class Model(Protocol):
    def complete(self, system: str, prompt: str, *, max_tokens: int = 4096) -> Completion: ...


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_model(config: dict) -> Model:
    """Build the configured adapter (anthropic | openai | openai-compatible)."""
    # The contract suite calls each agent entry point with None and expects
    # NotImplementedError. None is that probe; a config dict builds an adapter.
    if config is None:
        raise NotImplementedError("load_model requires a config dict")
    if not isinstance(config, dict):
        raise ModelError("config must be a dict")
    missing = [key for key in _REQUIRED if config.get(key) in (None, "")]
    if missing:
        raise ModelError("missing config: " + ", ".join(missing))
    provider = config["provider"]
    model = config["model"]
    api_key = config["api_key"]
    base_url = config["base_url"]
    if not isinstance(provider, str) or provider not in _PROVIDERS:
        raise ModelError(f"unknown provider: {provider}")
    if not isinstance(model, str):
        raise ModelError("model must be a string")
    if not isinstance(api_key, str):
        raise ModelError("api_key must be a string")
    if not isinstance(base_url, str):
        raise ModelError("base_url must be a string")
    try:
        timeout_s = float(config["timeout_s"])
    except (TypeError, ValueError) as exc:
        raise ModelError("timeout_s must be a number") from exc
    if timeout_s <= 0:
        raise ModelError("timeout_s must be positive")
    return _HttpModel(provider, model, api_key, base_url, timeout_s)


class _HttpModel:
    def __init__(self, provider: str, model: str, api_key: str, base_url: str, timeout_s: float) -> None:
        self._provider = provider
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    def complete(self, system: str, prompt: str, *, max_tokens: int = 4096) -> Completion:
        url, headers, body = self._build(system, prompt, max_tokens)
        data = _post_once(url, headers, body, self._timeout_s)
        if self._provider == "anthropic":
            text = _anthropic_text(data)
        else:
            text = _openai_text(data)
        input_tokens, output_tokens = _token_counts(data)
        return Completion(
            text=text,
            model=f"{self._provider}/{self._model}",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def _build(self, system: str, prompt: str, max_tokens: int) -> tuple[str, dict[str, str], dict]:
        if self._provider == "anthropic":
            return (
                f"{self._base_url}/v1/messages",
                {
                    "content-type": "application/json",
                    "x-api-key": self._api_key,
                    "anthropic-version": _ANTHROPIC_VERSION,
                },
                {
                    "model": self._model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        return (
            f"{self._base_url}/v1/chat/completions",
            {
                "content-type": "application/json",
                "authorization": f"Bearer {self._api_key}",
            },
            {
                "model": self._model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
        )


def _post_once(url: str, headers: dict[str, str], payload: dict, timeout_s: float) -> dict:
    raw_body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=raw_body, headers=headers, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _RefuseRedirects)
    try:
        with opener.open(request, timeout=timeout_s) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise ModelError(_provider_message(exc.code, exc.read())) from exc
    except urllib.error.URLError as exc:
        raise ModelError(f"request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ModelError(f"request failed: {exc}") from exc
    return _json_object(raw)


def _json_object(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ModelError("provider returned non-JSON") from exc
    if not isinstance(data, dict):
        raise ModelError("provider returned non-object JSON")
    return data


def _provider_message(status: int, raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace").strip()
    try:
        data = json.loads(text) if text else None
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str) and err:
            return err
    if text:
        return f"HTTP {status}: {text}"
    return f"HTTP {status}"


def _anthropic_text(data: dict) -> str:
    content = data.get("content")
    if not isinstance(content, list):
        raise ModelError("provider response contained no text")
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    if not parts:
        raise ModelError("provider response contained no text")
    return "".join(parts)


def _openai_text(data: dict) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ModelError("provider response contained no text")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ModelError("provider response contained no text")
    content = message.get("content")
    if not isinstance(content, str) or content == "":
        raise ModelError("provider response contained no text")
    return content


def _token_counts(data: dict) -> tuple[int, int]:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return 0, 0
    incoming = usage.get("input_tokens", usage.get("prompt_tokens", 0))
    outgoing = usage.get("output_tokens", usage.get("completion_tokens", 0))
    try:
        return int(incoming), int(outgoing)
    except (TypeError, ValueError) as exc:
        raise ModelError("provider usage was not numeric") from exc
