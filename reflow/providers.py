"""Which model providers need an API key.  OWNER: AGENT (task M-04).

`claude-code` (reflow/claude_code.py) runs on the user's Claude Code login, so the CLI
passes this set to `load_config(keyless_providers=...)`, which then doesn't
require REFLOW_API_KEY for it. Every other provider
needs the key. This list lives here because config.py (stdlib only) and llm.py name no
vendor or model (tests/test_config.py, tests/test_llm.py).
"""
KEYLESS_PROVIDERS = frozenset({"claude-code"})
