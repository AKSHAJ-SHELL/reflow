"""M-02: reflow.toml + environment loader.

Pure Python. No KiCad, no network, no model calls.
"""
import ast
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG_SOURCE = ROOT / "reflow" / "config.py"
COMMITTED_TOML = ROOT / "reflow.toml"

_ENV_VARS = (
    "REFLOW_API_KEY",
    "REFLOW_PROVIDER",
    "REFLOW_MODEL",
    "REFLOW_BASE_URL",
    "REFLOW_MAX_ATTEMPTS",
    "REFLOW_COMPILE_CAP",
    "REFLOW_TIMEOUT_S",
    "REFLOW_MAX_TOKENS",
)

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


@pytest.fixture
def clean_env(monkeypatch):
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _isolate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REFLOW_API_KEY", "test-key")


def test_missing_api_key_raises(clean_env, tmp_path, monkeypatch):
    from reflow.config import ConfigError, load_config

    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError, match="REFLOW_API_KEY"):
        load_config()


def test_blank_api_key_raises(clean_env, tmp_path, monkeypatch):
    from reflow.config import ConfigError, load_config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REFLOW_API_KEY", "   ")
    with pytest.raises(ConfigError, match="REFLOW_API_KEY"):
        load_config()


def test_other_vendor_keys_are_not_used(clean_env, tmp_path, monkeypatch):
    from reflow.config import ConfigError, load_config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "other-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "other-secret")
    with pytest.raises(ConfigError, match="REFLOW_API_KEY"):
        load_config()


def test_defaults_when_no_file(clean_env, tmp_path, monkeypatch):
    from reflow.config import load_config

    _isolate(monkeypatch, tmp_path)
    cfg = load_config()
    assert list(cfg) == list(_KEYS)
    assert cfg["max_attempts"] == 3
    assert cfg["compile_cap"] == 2
    assert cfg["provider"] == ""
    assert cfg["model"] == ""
    assert cfg["api_key"] == "test-key"
    assert cfg["base_url"] is None
    assert cfg["timeout_s"] == 60


def test_empty_toml_uses_defaults(clean_env, tmp_path, monkeypatch):
    from reflow.config import load_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "reflow.toml").write_text("", encoding="utf-8")
    cfg = load_config()
    assert cfg["max_attempts"] == 3
    assert cfg["compile_cap"] == 2
    assert cfg["provider"] == ""
    assert cfg["model"] == ""
    assert cfg["base_url"] is None
    assert cfg["timeout_s"] == 60


def test_toml_values_override_defaults(clean_env, tmp_path, monkeypatch):
    from reflow.config import load_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "reflow.toml").write_text(
        "\n".join([
            "max_attempts = 5",
            "compile_cap = 4",
            'provider = "configured-provider"',
            'model = "configured-model"',
            'base_url = "http://127.0.0.1:9"',
            "timeout_s = 15",
            "",
        ]),
        encoding="utf-8",
    )
    cfg = load_config()
    assert cfg["max_attempts"] == 5
    assert cfg["compile_cap"] == 4
    assert cfg["provider"] == "configured-provider"
    assert cfg["model"] == "configured-model"
    assert cfg["base_url"] == "http://127.0.0.1:9"
    assert cfg["timeout_s"] == 15
    assert cfg["api_key"] == "test-key"


def test_env_overrides_toml(clean_env, tmp_path, monkeypatch):
    from reflow.config import load_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "reflow.toml").write_text(
        "\n".join([
            "max_attempts = 9",
            "compile_cap = 9",
            'provider = "from-file"',
            'model = "from-file"',
            'base_url = "http://file"',
            "timeout_s = 9",
            "",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setenv("REFLOW_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("REFLOW_COMPILE_CAP", "1")
    monkeypatch.setenv("REFLOW_PROVIDER", "from-env")
    monkeypatch.setenv("REFLOW_MODEL", "from-env")
    monkeypatch.setenv("REFLOW_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("REFLOW_TIMEOUT_S", "30")
    cfg = load_config()
    assert cfg["max_attempts"] == 2
    assert cfg["compile_cap"] == 1
    assert cfg["provider"] == "from-env"
    assert cfg["model"] == "from-env"
    assert cfg["base_url"] == "http://127.0.0.1:9"
    assert cfg["timeout_s"] == 30


def test_blank_env_string_overrides_toml(clean_env, tmp_path, monkeypatch):
    from reflow.config import load_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "reflow.toml").write_text(
        'provider = "from-file"\nmodel = "from-file"\nbase_url = "http://file"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("REFLOW_PROVIDER", "")
    monkeypatch.setenv("REFLOW_MODEL", "  ")
    monkeypatch.setenv("REFLOW_BASE_URL", "  ")
    cfg = load_config()
    assert cfg["provider"] == ""
    assert cfg["model"] == ""
    assert cfg["base_url"] is None


def test_api_key_in_toml_raises(clean_env, tmp_path, monkeypatch):
    from reflow.config import ConfigError, load_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "reflow.toml").write_text('api_key = "from-file"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="REFLOW_API_KEY"):
        load_config()


def test_unknown_toml_key_raises(clean_env, tmp_path, monkeypatch):
    from reflow.config import ConfigError, load_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "reflow.toml").write_text("extra = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown"):
        load_config()


def test_bad_integer_raises(clean_env, tmp_path, monkeypatch):
    from reflow.config import ConfigError, load_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "reflow.toml").write_text('max_attempts = "three"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="integer"):
        load_config()


def test_bool_is_not_an_integer(clean_env, tmp_path, monkeypatch):
    from reflow.config import ConfigError, load_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "reflow.toml").write_text("compile_cap = true\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="integer"):
        load_config()


def test_non_positive_caps_raise(clean_env, tmp_path, monkeypatch):
    from reflow.config import ConfigError, load_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "reflow.toml").write_text("timeout_s = 0\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="timeout_s"):
        load_config()


def test_bad_env_integer_raises(clean_env, tmp_path, monkeypatch):
    from reflow.config import ConfigError, load_config

    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("REFLOW_COMPILE_CAP", "nope")
    with pytest.raises(ConfigError, match="REFLOW_COMPILE_CAP"):
        load_config()


def test_malformed_toml_raises(clean_env, tmp_path, monkeypatch):
    from reflow.config import ConfigError, load_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "reflow.toml").write_text("max_attempts = \n", encoding="utf-8")
    with pytest.raises(ConfigError, match="reflow.toml"):
        load_config()


def test_error_does_not_echo_the_api_key(clean_env, tmp_path, monkeypatch):
    from reflow.config import ConfigError, load_config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REFLOW_API_KEY", "super-secret-value")
    (tmp_path / "reflow.toml").write_text('max_attempts = "nope"\n', encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_config()
    assert "super-secret-value" not in str(exc.value)


def test_parent_directory_toml_is_found(clean_env, tmp_path, monkeypatch):
    from reflow.config import load_config

    (tmp_path / "reflow.toml").write_text("max_attempts = 4\ncompile_cap = 2\n", encoding="utf-8")
    child = tmp_path / "sub"
    child.mkdir()
    monkeypatch.chdir(child)
    monkeypatch.setenv("REFLOW_API_KEY", "test-key")
    assert load_config()["max_attempts"] == 4


def test_nearer_toml_wins(clean_env, tmp_path, monkeypatch):
    from reflow.config import load_config

    (tmp_path / "reflow.toml").write_text("max_attempts = 4\ncompile_cap = 2\n", encoding="utf-8")
    child = tmp_path / "sub"
    child.mkdir()
    (child / "reflow.toml").write_text("max_attempts = 7\ncompile_cap = 2\n", encoding="utf-8")
    monkeypatch.chdir(child)
    monkeypatch.setenv("REFLOW_API_KEY", "test-key")
    assert load_config()["max_attempts"] == 7


def test_explicit_path_is_the_file_that_is_read(clean_env, tmp_path, monkeypatch):
    from reflow.config import load_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "reflow.toml").write_text("max_attempts = 4\ncompile_cap = 2\n", encoding="utf-8")
    other = tmp_path / "elsewhere"
    other.mkdir()
    chosen = other / "custom.toml"
    chosen.write_text("max_attempts = 6\ncompile_cap = 1\n", encoding="utf-8")
    assert load_config(chosen)["max_attempts"] == 6
    assert load_config(chosen)["compile_cap"] == 1


def test_missing_explicit_path_raises(clean_env, tmp_path, monkeypatch):
    from reflow.config import ConfigError, load_config

    _isolate(monkeypatch, tmp_path)
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.toml")


def test_loader_does_not_open_a_socket(clean_env, tmp_path, monkeypatch):
    from reflow.config import load_config

    _isolate(monkeypatch, tmp_path)

    def boom(*_args, **_kwargs):
        raise AssertionError("loader opened a socket")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    cfg = load_config()
    assert cfg["api_key"] == "test-key"


def test_loader_imports_stdlib_only():
    tree = ast.parse(CONFIG_SOURCE.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    allowed = {"__future__", "os", "tomllib", "pathlib"}
    assert set(imported) <= allowed
    assert "reflow.llm" not in imported


def test_loader_source_has_no_model_id_key_or_path():
    source = CONFIG_SOURCE.read_text(encoding="utf-8").lower()
    for banned in ("claude", "gpt-", "sonnet", "opus", "ollama", "sk-", "anthropic", "openai"):
        assert banned not in source
    text = CONFIG_SOURCE.read_text(encoding="utf-8")
    assert "/home/" not in text
    assert "/Users/" not in text
    assert "C:\\" not in text


def test_committed_reflow_toml_is_caps_only():
    import tomllib

    text = COMMITTED_TOML.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    assert data == {"max_attempts": 3, "compile_cap": 2}
    lowered = text.lower()
    for secret in ("api_key", "apikey", "secret", "token", "password", "sk-"):
        assert secret not in lowered


def test_repo_root_load_uses_committed_caps(clean_env, monkeypatch):
    from reflow.config import load_config

    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("REFLOW_API_KEY", "test-key")
    cfg = load_config()
    assert cfg["max_attempts"] == 3
    assert cfg["compile_cap"] == 2
    assert cfg["provider"] == ""
    assert cfg["model"] == ""
    assert cfg["base_url"] is None
    assert cfg["timeout_s"] == 60
    assert cfg["api_key"] == "test-key"


# ---------------------------------------------------------------------------
# max_tokens: room for long or reasoning replies (M-03)
# ---------------------------------------------------------------------------

def test_max_tokens_defaults_to_4096(clean_env, tmp_path, monkeypatch):
    from reflow.config import load_config

    _isolate(monkeypatch, tmp_path)
    assert load_config()["max_tokens"] == 4096


def test_max_tokens_from_the_file_and_the_environment(clean_env, tmp_path, monkeypatch):
    from reflow.config import load_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "reflow.toml").write_text("max_tokens = 12000\n", encoding="utf-8")
    assert load_config()["max_tokens"] == 12000
    monkeypatch.setenv("REFLOW_MAX_TOKENS", "16000")
    assert load_config()["max_tokens"] == 16000


@pytest.mark.parametrize("line", ["max_tokens = 0", 'max_tokens = "lots"', "max_tokens = 1.5"])
def test_bad_max_tokens_is_refused(clean_env, tmp_path, monkeypatch, line):
    from reflow.config import ConfigError, load_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "reflow.toml").write_text(line + "\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="max_tokens"):
        load_config()
