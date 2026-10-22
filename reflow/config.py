"""Load `reflow.toml` and the process environment. OWNER: AGENT (task M-02).

Contract
--------
    load_config(path: Path | str | None = None) -> dict

The dict always has these keys, in this order:

    max_attempts   int          default 3
    compile_cap    int          default 2
    provider       str          file or REFLOW_PROVIDER, default ""
    model          str          file or REFLOW_MODEL, default ""
    api_key        str          REFLOW_API_KEY only
    base_url       str | None   file or REFLOW_BASE_URL, default None
    timeout_s      int          default 60
    max_tokens     int          default 4096 (per model reply; raise it for reasoning models)

A set environment variable overrides the file. A missing file uses the
defaults above. A missing or blank REFLOW_API_KEY raises ConfigError.
An `api_key` entry in the toml file raises ConfigError.

Must never
----------
- hardcode a model id, an API key, or a filesystem path
- call a model or open a network connection
- read an API key from a file
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

_FILENAME = "reflow.toml"

_KEYS = (
    "max_attempts",
    "compile_cap",
    "provider",
    "model",
    "api_key",
    "base_url",
    "timeout_s",
    "max_tokens",
)

_DEFAULTS: dict[str, object] = {
    "max_attempts": 3,
    "compile_cap": 2,
    "provider": "",
    "model": "",
    "base_url": None,
    "timeout_s": 60,
    "max_tokens": 4096,
}

# Smallest legal value for each integer setting.
_INT_MIN = {
    "max_attempts": 1,
    "compile_cap": 1,
    "timeout_s": 1,
    "max_tokens": 1,
}

_ENV = {
    "max_attempts": "REFLOW_MAX_ATTEMPTS",
    "compile_cap": "REFLOW_COMPILE_CAP",
    "provider": "REFLOW_PROVIDER",
    "model": "REFLOW_MODEL",
    "base_url": "REFLOW_BASE_URL",
    "timeout_s": "REFLOW_TIMEOUT_S",
    "max_tokens": "REFLOW_MAX_TOKENS",
}

_FILE_KEYS = frozenset(_INT_MIN) | {"provider", "model", "base_url"}


class ConfigError(Exception):
    """reflow.toml or the environment is missing or invalid."""


def load_config(path: Path | str | None = None) -> dict[str, object]:
    """Read caps, provider, and model settings. The API key comes from the environment."""
    file_path = _resolve_path(path)
    data = _read_toml(file_path) if file_path is not None else {}
    _reject_file_secrets(data)
    _reject_unknown(data)

    values = dict(_DEFAULTS)
    for key in _FILE_KEYS:
        if key in data:
            values[key] = _coerce_file(key, data[key])
    for key, env_name in _ENV.items():
        if env_name in os.environ:
            values[key] = _coerce_env(key, env_name, os.environ[env_name])

    raw_key = os.environ.get("REFLOW_API_KEY", "")
    api_key = raw_key.strip()
    if api_key == "":
        raise ConfigError("REFLOW_API_KEY is not set")
    values["api_key"] = api_key
    return {key: values[key] for key in _KEYS}


def _resolve_path(path: Path | str | None) -> Path | None:
    if path is not None:
        candidate = Path(path)
        if not candidate.is_file():
            raise ConfigError(f"{candidate.name} not found")
        return candidate
    start = Path.cwd()
    for directory in (start, *start.parents):
        candidate = directory / _FILENAME
        if candidate.is_file():
            return candidate
    return None


def _read_toml(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"could not read {path.name}: {exc.strerror}") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"could not parse {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} must be a table")
    return data


def _reject_file_secrets(data: dict) -> None:
    if "api_key" in data:
        raise ConfigError(
            "API key must be set in the environment as REFLOW_API_KEY, not in reflow.toml"
        )


def _reject_unknown(data: dict) -> None:
    unknown = sorted(set(data) - _FILE_KEYS)
    if unknown:
        raise ConfigError("unknown reflow.toml key: " + ", ".join(unknown))


def _coerce_file(key: str, value: object) -> object:
    if key in _INT_MIN:
        return _as_int(key, value, minimum=_INT_MIN[key])
    if key == "base_url":
        return _as_optional_str(key, value)
    return _as_str(key, value)


def _coerce_env(key: str, env_name: str, raw: str) -> object:
    if key in _INT_MIN:
        text = raw.strip()
        try:
            parsed = int(text, 10)
        except ValueError:
            raise ConfigError(f"{env_name} must be an integer") from None
        return _as_int(key, parsed, minimum=_INT_MIN[key])
    if key == "base_url":
        return raw.strip() or None
    return raw.strip()


def _as_int(key: str, value: object, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    if value < minimum:
        raise ConfigError(f"{key} must be >= {minimum}")
    return value


def _as_str(key: str, value: object) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a string")
    return value.strip()


def _as_optional_str(key: str, value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a string")
    text = value.strip()
    return text or None
