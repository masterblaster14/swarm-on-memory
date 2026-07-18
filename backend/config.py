"""Runtime configuration. Secrets stay here, server-side only."""
from __future__ import annotations
import json
import os
from pathlib import Path

# ---- Paths -----------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
STATE_DIR = ROOT_DIR / ".state"
STATE_DIR.mkdir(exist_ok=True)


def _load_env_file() -> None:
    """Load ROOT/.env into os.environ (without overriding real env vars).

    Dependency-free so secrets survive backend restarts without being baked
    into the launch command. Real environment always wins over the file.
    """
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_env_file()
TOKENS_FILE = STATE_DIR / "role_tokens.json"      # written by bootstrap_roles.py
RUNS_DB = STATE_DIR / "runs.sqlite3"

AGENT_LIBRARY = Path(os.environ.get("BOURDON_LIBRARY",
                                    str(Path.home() / "agent-library")))

# ---- Bourdon MCP endpoint --------------------------------------------------
BOURDON_URL = os.environ.get("BOURDON_URL", "http://127.0.0.1:7500/mcp")
# Trusted backend token (Architect/Curator + orchestration reads).
BOURDON_BACKEND_TOKEN = os.environ.get("BOURDON_BACKEND_TOKEN", "")

# ---- LLM (real calls through the local proxy) ------------------------------
LLM_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "http://localhost:20128").rstrip("/")
LLM_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.environ.get("SWARM_MODEL", "cc/claude-haiku-4-5-20251001")
# Anthropic Haiku 4.5 public pricing ($/1M tokens) for the cost counter.
PRICE_IN_PER_MTOK = float(os.environ.get("SWARM_PRICE_IN", "1.00"))
PRICE_OUT_PER_MTOK = float(os.environ.get("SWARM_PRICE_OUT", "5.00"))

# ---- Optional integrations (real, gated on presence of tokens) -------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
GITHUB_REPO = os.environ.get("SWARM_GITHUB_REPO", "")   # "owner/name"
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
# Notion database a completed run appends a ticket to (empty -> no ticket).
NOTION_TICKETS_DB = os.environ.get("SWARM_NOTION_DB", "")

# ---- Sarvam speech-to-text (real, gated on key presence) -------------------
SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
SARVAM_STT_URL = os.environ.get("SARVAM_STT_URL", "https://api.sarvam.ai/speech-to-text")
SARVAM_STT_MODEL = os.environ.get("SARVAM_STT_MODEL", "saarika:v2.5")
SARVAM_STT_LANGUAGE = os.environ.get("SARVAM_STT_LANGUAGE", "en-IN")


def load_role_tokens() -> dict[str, str]:
    """Map role_id -> bourdon token, written by bootstrap_roles.py."""
    if TOKENS_FILE.exists():
        return json.loads(TOKENS_FILE.read_text())
    return {}


def integration_status() -> dict[str, bool]:
    return {
        "github": bool(GITHUB_TOKEN and GITHUB_REPO),
        "notion": bool(NOTION_TOKEN),
        "llm": bool(LLM_API_KEY),
        "bourdon": bool(BOURDON_BACKEND_TOKEN),
        "sarvam": bool(SARVAM_API_KEY),
    }
