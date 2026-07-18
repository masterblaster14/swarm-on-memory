"""
Concurrent swarm run + ablation.

All agents run at the SAME time via asyncio.gather. They never receive each
other's output as a function argument -- their only channel is Bourdon. The
Curator runs in a second concurrent wave (it must observe the others' writes),
which is a deliberate read-after-write, not a data handoff.

Ablation: memory_on=False constructs every agent with bourdon=None, so no
reads and no writes happen. Agents then drift -- the demo's whole point.
"""
from __future__ import annotations
import asyncio
import json
import time
import uuid
from typing import Awaitable, Callable

from backend import agents as A
from backend.agents import AgentContext
from backend.bourdon_client import BourdonClient
from backend.config import (load_role_tokens, PRICE_IN_PER_MTOK,
                            PRICE_OUT_PER_MTOK)
from backend.integrations import github, notion
from backend.llm import Usage
from backend.roles import (ARCHITECT, CURATOR, IMPLEMENTER, REVIEWER, SKEPTIC,
                          ALL_ROLES, ROLES_BY_ID)

Emit = Callable[[dict], Awaitable[None]]


def _est_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token), enough for an illustrative counter."""
    return max(0, round(len(text) / 4))


def _scoreboard(per_agent: dict, peer_outputs: dict) -> dict:
    """
    Estimated full-context (no memory) vs retrieval (with memory).

    With memory, each agent retrieves only the slice its grants expose -- that's
    the REAL measured usage. Without memory, an agent has no shared brain to pull
    from, so the whole run's context must be stuffed into its prompt every call.
    We model that as: no_mem_in = real mem_in + the full shared context in tokens.
    Memory-less agents (the Skeptic) carry no context either way, so they stay flat.
    """
    full_ctx = _est_tokens(json.dumps(peer_outputs, default=str))
    rows, tot = [], {"no_mem_in": 0, "no_mem_out": 0, "mem_in": 0, "mem_out": 0,
                     "cost_no_mem": 0.0, "cost_mem": 0.0}
    for rid, pa in per_agent.items():
        role = ROLES_BY_ID.get(rid)
        uses_mem = bool(role and role.tier != "none")
        mem_in = pa["prompt_tokens"]
        mem_out = pa["completion_tokens"]
        no_mem_in = mem_in + (full_ctx if uses_mem else 0)
        no_mem_out = mem_out
        cost_mem = mem_in / 1e6 * PRICE_IN_PER_MTOK + mem_out / 1e6 * PRICE_OUT_PER_MTOK
        cost_no_mem = no_mem_in / 1e6 * PRICE_IN_PER_MTOK + no_mem_out / 1e6 * PRICE_OUT_PER_MTOK
        no_mem_total = no_mem_in + no_mem_out
        mem_total = mem_in + mem_out
        saved_pct = round((1 - mem_total / no_mem_total) * 100, 1) if no_mem_total else 0.0
        rows.append({
            "agent": rid, "label": role.label if role else rid,
            "no_mem_in": no_mem_in, "no_mem_out": no_mem_out,
            "mem_in": mem_in, "mem_out": mem_out,
            "saved_pct": saved_pct,
            "cost_no_mem": round(cost_no_mem, 5), "cost_mem": round(cost_mem, 5),
        })
        for k, v in (("no_mem_in", no_mem_in), ("no_mem_out", no_mem_out),
                     ("mem_in", mem_in), ("mem_out", mem_out),
                     ("cost_no_mem", cost_no_mem), ("cost_mem", cost_mem)):
            tot[k] += v
    tot_no = tot["no_mem_in"] + tot["no_mem_out"]
    tot_mem = tot["mem_in"] + tot["mem_out"]
    tot["saved_pct"] = round((1 - tot_mem / tot_no) * 100, 1) if tot_no else 0.0
    tot["cost_no_mem"] = round(tot["cost_no_mem"], 5)
    tot["cost_mem"] = round(tot["cost_mem"], 5)
    tot["cost_saved"] = round(tot["cost_no_mem"] - tot["cost_mem"], 5)
    return {"rows": rows, "totals": tot, "full_context_tokens": full_ctx,
            "basis": "estimated"}


def _pr_body(summary: dict) -> str:
    """Render a run summary into markdown for the PR + Notion ticket."""
    out = summary["outputs"]
    ticket = summary["ticket"]
    lines = [f"# {ticket['title']}", "", ticket.get("body", ""), "",
             f"_Swarm run `{summary['run_id']}` · {summary['usage']['total_tokens']} tokens "
             f"· ${summary['usage']['cost_usd']:.4f}_", ""]
    decisions = (out.get(ARCHITECT.id) or {}).get("decisions", [])
    if decisions:
        lines.append("## Decisions")
        for d in decisions:
            lines.append(f"- **{d.get('name')}** — {d.get('decision')} "
                         f"({round((d.get('confidence') or 0) * 100)}%)")
        lines.append("")
    review = out.get(REVIEWER.id) or {}
    if review.get("overall"):
        lines.append(f"## Review: {review['overall']}")
        for v in review.get("verdicts", []):
            mark = "PASS" if v.get("status") == "PASS" else "FAIL"
            lines.append(f"- [{mark}] {v.get('decision')} — {v.get('note')}")
        lines.append("")
    contradictions = (out.get(CURATOR.id) or {}).get("contradictions", [])
    if contradictions:
        lines.append("## Contradictions resolved")
        for c in contradictions:
            lines.append(f"- **{c.get('subject')}**: {c.get('resolution')} "
                         f"(policy {c.get('policy_clause')})")
    return "\n".join(lines)


async def _publish(summary: dict, emit: Emit) -> dict:
    """Open a real GitHub PR + append a Notion ticket for a finished run."""
    run_id = summary["run_id"]
    title = f"[swarm] {summary['ticket']['title']}"[:250]
    body = _pr_body(summary)
    files = (summary["outputs"].get(IMPLEMENTER.id) or {}).get("files", [])
    published: dict = {}

    if github.enabled():
        try:
            pr = await github.publish_run(run_id, title, body, files)
            published["github"] = pr
            await emit({"kind": "published", "target": "github", **pr})
        except Exception as e:
            published["github"] = {"ok": False, "error": str(e)}
            await emit({"kind": "published", "target": "github", "ok": False, "error": str(e)})

    if notion.can_create():
        pr_url = (published.get("github") or {}).get("url", "")
        try:
            tk = await notion.create_ticket(summary["ticket"]["title"], "Pending", pr_url)
            published["notion"] = tk
            await emit({"kind": "published", "target": "notion", **tk})
        except Exception as e:
            published["notion"] = {"ok": False, "error": str(e)}
            await emit({"kind": "published", "target": "notion", "ok": False, "error": str(e)})

    return published


def _client_for(role, tokens: dict[str, str], memory_on: bool) -> BourdonClient | None:
    # Skeptic: never gets a client. Ablation off: nobody gets a client.
    if role.tier == "none" or not memory_on:
        return None
    tok = tokens.get(role.id)
    return BourdonClient(tok, role.id) if tok else None


async def run_swarm(ticket: dict, memory_on: bool, emit: Emit,
                   publish: bool = False) -> dict:
    run_id = ticket.get("run_id") or ("run_" + uuid.uuid4().hex[:8])
    ticket["run_id"] = run_id
    tokens = load_role_tokens()
    started = time.time()

    contexts: dict[str, AgentContext] = {}
    for role in ALL_ROLES:
        contexts[role.id] = AgentContext(
            role=role,
            bourdon=_client_for(role, tokens, memory_on),
            ticket=ticket,
            memory_on=memory_on,
            emit=emit,
        )

    await emit({"kind": "run_start", "run_id": run_id, "memory_on": memory_on,
                "ticket": {"title": ticket["title"]}})

    # Wave 1: architect, implementer, reviewer, skeptic -- all concurrent.
    # They coordinate ONLY through Bourdon; implementer/reviewer read whatever
    # the architect has committed by the time they query (eventual, not passed).
    wave1 = {
        ARCHITECT.id: A.run_architect(contexts[ARCHITECT.id]),
        IMPLEMENTER.id: A.run_implementer(contexts[IMPLEMENTER.id]),
        REVIEWER.id: A.run_reviewer(contexts[REVIEWER.id]),
        SKEPTIC.id: A.run_skeptic(contexts[SKEPTIC.id]),
    }
    results = await asyncio.gather(*wave1.values(), return_exceptions=True)
    peer_outputs = {}
    for rid, res in zip(wave1.keys(), results):
        peer_outputs[rid] = res if not isinstance(res, Exception) else {"error": str(res)}

    # Wave 2: curator observes the concurrent writes and resolves contradictions.
    curator_out = await A.run_curator(contexts[CURATOR.id], peer_outputs)
    peer_outputs[CURATOR.id] = curator_out

    # Aggregate real token usage across all agents.
    total = Usage()
    per_agent = {}
    for rid, ctx in contexts.items():
        total.add(ctx.usage)
        per_agent[rid] = {
            "prompt_tokens": ctx.usage.prompt_tokens,
            "completion_tokens": ctx.usage.completion_tokens,
            "cost_usd": round(ctx.usage.cost_usd, 6),
            "reads": ctx.read_log,
            "writes": ctx.write_log,
            "read_scope": ctx.role.reads,
        }

    summary = {
        "run_id": run_id,
        "memory_on": memory_on,
        "ticket": ticket,
        "outputs": peer_outputs,
        "per_agent": per_agent,
        "usage": {
            "prompt_tokens": total.prompt_tokens,
            "completion_tokens": total.completion_tokens,
            "total_tokens": total.total,
            "cost_usd": round(total.cost_usd, 6),
        },
        "scoreboard": _scoreboard(per_agent, peer_outputs),
        "elapsed_s": round(time.time() - started, 2),
    }

    # Publish real side effects (GitHub PR + Notion ticket) only for genuine
    # runs -- ablation runs twice and must not double-publish.
    if publish:
        summary["published"] = await _publish(summary, emit)

    await emit({"kind": "run_done", **summary})
    return summary
