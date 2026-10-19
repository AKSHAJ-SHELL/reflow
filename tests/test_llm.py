"""M-01: load_model speaks HTTP once and returns text. No tools, no retries."""
import ast
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from reflow.llm import Completion, ModelError, load_model

ROOT = Path(__file__).resolve().parents[1]
LLM_PATH = ROOT / "reflow" / "llm.py"

_ALLOWED_IMPORTS = {
    "__future__",
    "json",
    "urllib.error",
    "urllib.request",
    "dataclasses",
    "typing",
}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        self.server.requests.append({
            "path": self.path,
            "body": raw,
            "headers": {k.lower(): v for k, v in self.headers.items()},
        })
        payload = self.server.body
        self.send_response(self.server.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


class _Recorder(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.requests = []
        self.status = 200
        self.body = b"{}"


@pytest.fixture
def server():
    httpd = _Recorder()
    thread = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True,
    )
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()


def _config(server, **overrides):
    port = server.server_address[1]
    cfg = {
        "max_attempts": 3,
        "compile_cap": 2,
        "provider": "anthropic",
        "model": "widget-from-config",
        "api_key": "test-key",
        "base_url": f"http://127.0.0.1:{port}",
        "timeout_s": 5,
    }
    cfg.update(overrides)
    return cfg


def _anthropic_ok(text="export const Board = () => null\n"):
    return json.dumps({
        "model": "server-picked-id",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 11, "output_tokens": 7},
    }).encode()


def _openai_ok(text="export const Board = () => null\n"):
    return json.dumps({
        "model": "server-picked-id",
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4},
    }).encode()


def _error_body(message):
    return json.dumps({"type": "error", "error": {"message": message}}).encode()


def _has_key(obj, key):
    if isinstance(obj, dict):
        return key in obj or any(_has_key(v, key) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_key(v, key) for v in obj)
    return False


def test_source_is_stdlib_and_has_no_model_id():
    src = LLM_PATH.read_text()
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported <= _ALLOWED_IMPORTS
    lowered = src.lower()
    for banned in ("litellm", "pydantic", "claude", "sonnet", "gpt-", "opus", "haiku"):
        assert banned not in lowered
    assert "reflow.toml" not in src
    assert "os.environ" not in src
    assert "getenv" not in src


def test_none_config_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        load_model(None)


def test_missing_model_raises_before_any_request(server):
    cfg = _config(server)
    del cfg["model"]
    with pytest.raises(ModelError):
        load_model(cfg)
    assert server.requests == []


def test_unknown_provider_raises(server):
    with pytest.raises(ModelError):
        load_model(_config(server, provider="litellm"))
    assert server.requests == []


def test_anthropic_complete_returns_completion_from_config_model(server):
    server.body = _anthropic_ok("hello from model")
    model = load_model(_config(server))
    got = model.complete("SYSTEM-TEXT", "USER-TEXT", max_tokens=128)
    assert isinstance(got, Completion)
    assert got.text == "hello from model"
    assert got.model == "anthropic/widget-from-config"
    assert got.input_tokens == 11
    assert got.output_tokens == 7
    assert len(server.requests) == 1
    req = server.requests[0]
    assert req["path"] == "/v1/messages"
    body = json.loads(req["body"])
    assert set(body) == {"model", "max_tokens", "system", "messages"}
    assert body["model"] == "widget-from-config"
    assert body["max_tokens"] == 128
    assert body["system"] == "SYSTEM-TEXT"
    assert body["messages"] == [{"role": "user", "content": "USER-TEXT"}]
    assert not _has_key(body, "tools")
    assert b"test-key" not in req["body"]
    assert req["headers"]["x-api-key"] == "test-key"


def test_default_max_tokens_is_4096(server):
    server.body = _anthropic_ok("x")
    load_model(_config(server)).complete("s", "p")
    body = json.loads(server.requests[0]["body"])
    assert body["max_tokens"] == 4096


@pytest.mark.parametrize("status", [401, 500])
def test_http_error_raises_model_error_and_does_not_retry(server, status):
    server.status = status
    server.body = _error_body(f"boom-{status}")
    model = load_model(_config(server, max_attempts=3, compile_cap=2))
    with pytest.raises(ModelError, match=f"boom-{status}"):
        model.complete("system", "prompt")
    assert len(server.requests) == 1
    body = json.loads(server.requests[0]["body"])
    assert not _has_key(body, "tools")


def test_tool_use_does_not_start_a_tool_loop(server):
    server.body = json.dumps({
        "model": "server-picked-id",
        "content": [
            {"type": "text", "text": "board"},
            {"type": "tool_use", "id": "toolu_1", "name": "search_parts", "input": {"q": "4.7k"}},
        ],
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }).encode()
    got = load_model(_config(server)).complete("system", "prompt")
    assert got.text == "board"
    assert len(server.requests) == 1


def test_tool_use_without_text_raises_once(server):
    server.body = json.dumps({
        "model": "server-picked-id",
        "content": [
            {"type": "tool_use", "id": "toolu_1", "name": "search_parts", "input": {}},
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }).encode()
    with pytest.raises(ModelError):
        load_model(_config(server)).complete("system", "prompt")
    assert len(server.requests) == 1


def test_openai_compatible_complete(server):
    server.body = _openai_ok("local text")
    model = load_model(_config(server, provider="openai-compatible", model="local-from-config"))
    got = model.complete("SYSTEM-TEXT", "USER-TEXT", max_tokens=64)
    assert got.text == "local text"
    assert got.model == "openai-compatible/local-from-config"
    assert got.input_tokens == 3
    assert got.output_tokens == 4
    assert len(server.requests) == 1
    req = server.requests[0]
    assert req["path"] == "/v1/chat/completions"
    body = json.loads(req["body"])
    assert set(body) == {"model", "max_tokens", "messages"}
    assert body["model"] == "local-from-config"
    assert body["messages"] == [
        {"role": "system", "content": "SYSTEM-TEXT"},
        {"role": "user", "content": "USER-TEXT"},
    ]
    assert not _has_key(body, "tools")
    assert b"local-from-config" in req["body"]
    assert req["headers"]["authorization"] == "Bearer test-key"


def test_openai_tool_call_does_not_loop(server):
    server.body = json.dumps({
        "model": "server-picked-id",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "search_parts", "arguments": "{}"},
                }],
            },
        }],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }).encode()
    with pytest.raises(ModelError):
        load_model(_config(server, provider="openai")).complete("s", "p")
    assert len(server.requests) == 1
    body = json.loads(server.requests[0]["body"])
    assert not _has_key(body, "tools")


def test_connection_failure_raises_model_error():
    cfg = {
        "max_attempts": 3,
        "compile_cap": 2,
        "provider": "anthropic",
        "model": "widget-from-config",
        "api_key": "test-key",
        "base_url": "http://127.0.0.1:1",
        "timeout_s": 1,
    }
    with pytest.raises(ModelError):
        load_model(cfg).complete("s", "p")
