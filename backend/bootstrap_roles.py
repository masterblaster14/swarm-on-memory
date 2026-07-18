"""
Register the five swarm roles as Bourdon federation members with the
correct tiers + namespace grants, and persist their tokens server-side.

Run once (idempotent-ish): re-running rotates tokens for existing members.
The Skeptic is deliberately NOT registered -- amnesia by construction.

Usage:
    env -u PYTHONPATH python -m backend.bootstrap_roles
"""
from __future__ import annotations
import json
import re
import subprocess
import sys

from backend.config import TOKENS_FILE, load_role_tokens
from backend.roles import ALL_ROLES

TOKEN_RE = re.compile(r"token:\s*(bdn_[0-9a-f]+)")


def _run(args: list[str]) -> str:
    proc = subprocess.run(
        ["bourdon", *args], capture_output=True, text=True,
        env=_clean_env(),
    )
    return (proc.stdout or "") + (proc.stderr or "")


def _clean_env() -> dict:
    import os
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)  # avoid the app-env broken pydantic
    return env


def _existing_members() -> set[str]:
    out = _run(["agent", "list"])
    return set(re.findall(r"^\s*([a-z0-9][a-z0-9_-]*)\b", out, re.MULTILINE))


def register_all() -> dict[str, str]:
    existing = _existing_members()
    tokens = load_role_tokens()

    # namespaces that must exist as members so grants resolve
    aux_namespaces = ["swarm-architect-reasoning"]

    for role in ALL_ROLES:
        if role.tier == "none":
            print(f"  {role.label:12s} -> NO token (amnesia by construction)")
            tokens.pop(role.id, None)
            continue

        args = ["agent", "add", role.id, "--tier", role.tier]
        for g in role.grants:
            args += ["--grant", g]

        if role.id in existing:
            # rotate to get a fresh token we can capture
            out = _run(["agent", "rotate", role.id])
        else:
            out = _run(args)
        m = TOKEN_RE.search(out)
        if not m:
            print(f"  {role.label}: could not capture token:\n{out}", file=sys.stderr)
            continue
        tokens[role.id] = m.group(1)
        print(f"  {role.label:12s} -> tier={role.tier:11s} grants={list(role.grants)}")

    # ensure aux namespaces exist (as trusted, they just hold entities)
    for ns in aux_namespaces:
        if ns not in existing:
            _run(["agent", "add", ns, "--tier", "trusted"])

    TOKENS_FILE.write_text(json.dumps(tokens, indent=2))
    print(f"\nWrote {len(tokens)} role tokens to {TOKENS_FILE}")
    return tokens


if __name__ == "__main__":
    register_all()
