# Swarm on Bourdon

Five AI agents work a developer ticket **concurrently**, coordinating through
**one shared memory layer only** — [Bourdon](https://github.com/getbourdon/bourdon),
a cross-agent memory federation server exposed over MCP. No agent ever receives
another's output as a function argument; their only channel is Bourdon, and each
agent's read access is **enforced server-side** by Bourdon's federation registry.

## The five agents (asymmetric memory access)

| Agent | Tier | Reads | Writes | The point |
|-------|------|-------|--------|-----------|
| **Architect** | trusted | everything | `swarm-architect` (decisions), `swarm-architect-reasoning` (reasoning) | Turns the ticket into atomic decisions; splits *what* from *why* into separate namespaces |
| **Implementer** | quarantined | `swarm-architect` only | `swarm-implementer` | Sees decisions but is **structurally blind to reasoning** — proven live |
| **Reviewer** | quarantined | decisions + corrections | `swarm-reviewer` | Judges against remembered decisions & past human corrections |
| **Skeptic** | none | **nothing** — has no Bourdon token at all | — | Amnesiac *by construction*, not instruction. First-principles risks a memory-primed team overlooks |
| **Curator** | trusted | everything | `swarm-curator` | Reads the concurrent writes, resolves contradictions under a stated, visible policy |

Asymmetry is real: the Implementer's UI panel shows it querying the reasoning
namespace and getting **BLIND** back, because Bourdon denies the token.

## What it demonstrates

- **NLP** — ticket → structured entities with confidence; NL query box over
  memory with **cited** answers (entity + committing agent); voice input/output.
- **Task automation** — real GitHub issue/PR/CI + Notion ticket read/status flip
  (gated on your tokens; off = red pills, everything else still runs).
- **Recommendations** — team preference profile learned from corrections;
  proactive suggestions drawn from similar past tickets; sharpens each run.
- **Correction loop** — reject a decision → committed as a `correction` entity →
  future Architect runs read it, cite it, and stop re-proposing it.
- **Ablation** — one-click A/B: the same ticket through the full swarm with
  memory ON vs every agent's client nulled, with **real** token + cost counters.

## Prerequisites (must be done by hand)

1. **Bourdon installed** with an agent library (default `~/agent-library`).
2. **Roles registered** — run once, captures the per-role tokens to
   `.state/role_tokens.json` (the Skeptic deliberately gets none):
   ```bash
   env -u PYTHONPATH python -m backend.bootstrap_roles
   ```
3. **Environment** (secrets stay server-side, never in the browser):
   - `BOURDON_BACKEND_TOKEN` — a trusted token (Architect or Curator) for
     orchestration reads. Falls back to the tokens file if unset.
   - `ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY` — the LLM proxy (real calls,
     real usage). Model defaults to `cc/claude-haiku-4-5-20251001`.
   - Optional: `GITHUB_TOKEN` + `SWARM_GITHUB_REPO` (`owner/name`), `NOTION_TOKEN`.
   - On this machine, **always clear `PYTHONPATH`** for backend commands
     (`env -u PYTHONPATH …`) — the app env otherwise shadows the real install.

## Run (three services)

```bash
# 1. Bourdon MCP server over HTTP (browsers can't do stdio) — port 7500
bourdon serve --http --port 7500        # exposes http://127.0.0.1:7500/mcp

# 2. Backend — FastAPI, holds all secrets + the Bourdon connection — port 8000
env -u PYTHONPATH BOURDON_BACKEND_TOKEN="bdn_…" \
  python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000

# 3. Frontend — Vite dev server, proxies /api to :8000 — port 5173
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173/**. Click **Sample** → **Run swarm**. Watch the five
panels light up; the Implementer flips to BLIND, the Curator resolves
contradictions. Ask the memory box "how should money be stored?" for a cited
answer. Flip **Memory ON/OFF** or hit **Run A/B** to see the ablation.

## Architecture notes / decisions

- **Transport is HTTP, not stdio** (the brief's `docker compose` assumed a
  container; here Bourdon runs `serve --http`). Tokens live only in the backend.
- **Bourdon's `find_entity` is exact-match only** (pre-alpha), so listing/search
  walks each namespace's L5 manifest (`agent-library://agents/{id}/memory`) and
  flattens `known_entities` with provenance — see
  `backend/bourdon_client.py:enumerate_entities`.
- **Concurrency is real** (`asyncio.gather`), so downstream agents **poll**
  Bourdon for the Architect's decisions (bounded read-after-write) rather than
  receive a handoff — still pure memory coordination.
- The LLM proxy occasionally returns 520s under concurrent load; `backend/llm.py`
  retries with jittered backoff.

## Layout

```
backend/
  app.py              FastAPI: /api/run, /api/ablation, /api/query, /api/reject,
                      /api/memory, /api/profile, SSE /api/stream, integrations
  orchestrator.py     concurrent run_swarm + ablation, real token accounting
  agents.py           the five agent behaviours + blindness proofs
  roles.py            tiers, grants, personas — the asymmetric access model
  bourdon_client.py   async MCP client (one per role token)
  nlp.py              parse_ticket, answer_query (cited), team_profile, suggestions
  bootstrap_roles.py  registers the 5 federation members, captures tokens
  integrations/       github.py, notion.py (real REST, gated on tokens)
frontend/src/         React + TS dashboard, SSE live events, Web Speech voice
```
