"""
The five agents. Each runs concurrently. Their ONLY channel is Bourdon.

An agent's `read_memory()` pulls exactly what its grants allow (enforced
server-side). The Skeptic has bourdon=None and therefore reads nothing.
Nothing is passed agent-to-agent as a function argument.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from backend import llm
from backend.bourdon_client import BourdonClient
from backend.llm import Usage
from backend.roles import (ARCHITECT, CURATOR, IMPLEMENTER, REVIEWER, SKEPTIC,
                          Role, CORRECTION_NAMESPACE, DECISION_NAMESPACE,
                          REASONING_NAMESPACE)

Emit = Callable[[dict], Any]  # async event emitter


@dataclass
class AgentContext:
    role: Role
    bourdon: BourdonClient | None            # None for Skeptic / ablation
    ticket: dict
    memory_on: bool
    emit: Emit
    usage: Usage = field(default_factory=Usage)
    read_log: list[dict] = field(default_factory=list)     # what it read
    write_log: list[dict] = field(default_factory=list)    # what it committed

    async def event(self, kind: str, **payload):
        await self.emit({"agent": self.role.id, "kind": kind, **payload})


async def _read_corrections(ctx: AgentContext) -> list[dict]:
    """Corrections live in the curator namespace; only granted agents see them."""
    if not ctx.bourdon or not ctx.memory_on:
        return []
    out: list[dict] = []
    for topic in ("correction", "reject", "prefer"):
        try:
            r = await ctx.bourdon.find_entity(topic)
            for m in r.get("matches", []):
                if CORRECTION_NAMESPACE in (m.get("agents") or []):
                    out.append(m)
        except Exception:
            pass
    # dedupe by name
    seen, uniq = set(), []
    for m in out:
        if m["name"] not in seen:
            seen.add(m["name"]); uniq.append(m)
    return uniq


async def _read_decisions(ctx: AgentContext, wait: bool = False) -> list[dict]:
    """
    Read the architect's decisions FROM MEMORY (never passed as an argument).

    Under true concurrency, a downstream agent may query before the architect
    has committed. When `wait` is set, poll Bourdon briefly for decisions to
    appear -- this is still pure memory coordination (read-after-write on the
    shared layer), not a direct handoff. Bounded so a genuinely empty memory
    (e.g. ablation OFF) returns fast.
    """
    if not ctx.bourdon or not ctx.memory_on:
        return []
    import asyncio as _a
    deadline = 12  # seconds
    waited = 0.0
    while True:
        try:
            r = await ctx.bourdon.query_agent_memory(DECISION_NAMESPACE, "decision")
            matches = r.get("matches", [])
        except Exception:
            matches = []
        if matches or not wait or waited >= deadline:
            return matches
        await _a.sleep(1.0)
        waited += 1.0


def _fmt_entities(items: list[dict]) -> str:
    if not items:
        return "(none visible to you)"
    lines = []
    for m in items:
        who = ", ".join(m.get("agents", []))
        summ = "; ".join(m.get("summaries", {}).values()) or m.get("summary", "")
        lines.append(f"- [{m.get('name')}] ({who}): {summ}")
    return "\n".join(lines)


def _ticket_text(t: dict) -> str:
    return f"TITLE: {t.get('title','')}\n\nBODY:\n{t.get('body','')}"


# --------------------------------------------------------------------------
# Individual agents
# --------------------------------------------------------------------------
async def run_architect(ctx: AgentContext) -> dict:
    await ctx.event("start", note="reading corrections (full access)")
    corrections = await _read_corrections(ctx)
    ctx.read_log += [{"source": "corrections", "entity": c["name"]} for c in corrections]
    await ctx.event("read", scope="corrections", items=[c["name"] for c in corrections])

    system = ARCHITECT.persona
    user = (
        f"{_ticket_text(ctx.ticket)}\n\n"
        f"TEAM CORRECTIONS you must honor (never violate these):\n{_fmt_entities(corrections)}\n\n"
        "Produce 3-5 atomic engineering decisions. Return JSON: "
        '{"decisions":[{"name":"kebab-slug","decision":"one sentence, testable",'
        '"reasoning":"why","confidence":0.0-1.0,"cites":["correction-slug if used"]}]}'
    )
    data, u = await llm.complete_json(system, user, max_tokens=1200)
    ctx.usage.add(u)
    decisions = data.get("decisions", []) if isinstance(data, dict) else []

    committed = []
    for d in decisions:
        slug = _slug(d.get("name", "decision"))
        # DECISION -> public, architect namespace
        if ctx.bourdon and ctx.memory_on:
            await ctx.bourdon.commit(DECISION_NAMESPACE, [{
                "name": slug, "type": "decision", "visibility": "public",
                "summary": d.get("decision", ""), "tags": ["decision", ctx.ticket["run_id"]],
                "confidence": d.get("confidence"),
            }], role_narrative="Architect decisions")
            # REASONING -> SEPARATE namespace (implementer is blind to it)
            await ctx.bourdon.commit(REASONING_NAMESPACE, [{
                "name": slug + "-why", "type": "reasoning", "visibility": "public",
                "summary": d.get("reasoning", ""), "tags": ["reasoning", ctx.ticket["run_id"]],
            }], role_narrative="Architect reasoning")
        committed.append({"name": slug, "decision": d.get("decision"),
                         "reasoning": d.get("reasoning"), "confidence": d.get("confidence"),
                         "cites": d.get("cites", [])})
        ctx.write_log.append({"namespace": DECISION_NAMESPACE, "entity": slug})
        await ctx.event("commit", namespace=DECISION_NAMESPACE, entity=slug,
                       summary=d.get("decision"))
    await ctx.event("done", decisions=committed)
    return {"decisions": committed}


async def run_implementer(ctx: AgentContext) -> dict:
    await ctx.event("start", note="waiting on DECISIONS in memory (blind to reasoning)")
    decisions = await _read_decisions(ctx, wait=True)
    ctx.read_log += [{"source": "decisions", "entity": m["name"]} for m in decisions]
    await ctx.event("read", scope="decisions", items=[m["name"] for m in decisions])
    # prove blindness: attempt to read reasoning, expect empty
    reasoning_seen = []
    if ctx.bourdon and ctx.memory_on:
        try:
            r = await ctx.bourdon.query_agent_memory(REASONING_NAMESPACE, "reasoning")
            reasoning_seen = [m["name"] for m in r.get("matches", [])]
        except Exception:
            reasoning_seen = []
    await ctx.event("access_check", tried=REASONING_NAMESPACE,
                   visible=reasoning_seen, blind=(len(reasoning_seen) == 0))

    system = IMPLEMENTER.persona
    user = (
        f"{_ticket_text(ctx.ticket)}\n\n"
        f"DECISIONS you must implement exactly:\n{_fmt_entities(decisions)}\n\n"
        "Write the minimal code satisfying every decision. Return JSON: "
        '{"language":"...","files":[{"path":"...","content":"..."}],'
        '"notes":"gaps or assumptions"}'
    )
    data, u = await llm.complete_json(system, user, max_tokens=1600)
    ctx.usage.add(u)
    files = data.get("files", []) if isinstance(data, dict) else []
    if ctx.bourdon and ctx.memory_on:
        await ctx.bourdon.commit(IMPLEMENTER.id, [{
            "name": f"impl-{ctx.ticket['run_id']}", "type": "artifact",
            "visibility": "public", "summary": (data.get("notes") or "code written")[:400],
            "tags": ["code", ctx.ticket["run_id"]],
        }], role_narrative="Implementer output")
        ctx.write_log.append({"namespace": IMPLEMENTER.id, "entity": f"impl-{ctx.ticket['run_id']}"})
        await ctx.event("commit", namespace=IMPLEMENTER.id, entity=f"impl-{ctx.ticket['run_id']}")
    await ctx.event("done", files=[f.get("path") for f in files], notes=data.get("notes"))
    return {"files": files, "notes": data.get("notes"), "blind_to_reasoning": len(reasoning_seen) == 0}


async def run_reviewer(ctx: AgentContext) -> dict:
    await ctx.event("start", note="reading DECISIONS + CORRECTIONS")
    decisions = await _read_decisions(ctx, wait=True)
    corrections = await _read_corrections(ctx)
    ctx.read_log += [{"source": "decisions", "entity": m["name"]} for m in decisions]
    ctx.read_log += [{"source": "corrections", "entity": m["name"]} for m in corrections]
    await ctx.event("read", scope="decisions+corrections",
                   items=[m["name"] for m in decisions + corrections])

    system = REVIEWER.persona
    user = (
        f"{_ticket_text(ctx.ticket)}\n\n"
        f"DECISIONS:\n{_fmt_entities(decisions)}\n\n"
        f"CORRECTIONS:\n{_fmt_entities(corrections)}\n\n"
        "Judge whether the plan honors each decision and correction. Return JSON: "
        '{"verdicts":[{"decision":"slug","status":"PASS|FAIL","checked_against":"entity name","note":"..."}],'
        '"overall":"PASS|FAIL"}'
    )
    data, u = await llm.complete_json(system, user, max_tokens=1100)
    ctx.usage.add(u)
    verdicts = data.get("verdicts", []) if isinstance(data, dict) else []
    if ctx.bourdon and ctx.memory_on:
        await ctx.bourdon.commit(REVIEWER.id, [{
            "name": f"review-{ctx.ticket['run_id']}", "type": "review",
            "visibility": "public", "summary": f"overall {data.get('overall')}",
            "tags": ["review", ctx.ticket["run_id"]],
        }], role_narrative="Reviewer verdicts")
        ctx.write_log.append({"namespace": REVIEWER.id, "entity": f"review-{ctx.ticket['run_id']}"})
        await ctx.event("commit", namespace=REVIEWER.id, entity=f"review-{ctx.ticket['run_id']}")
    await ctx.event("done", verdicts=verdicts, overall=data.get("overall"))
    return {"verdicts": verdicts, "overall": data.get("overall")}


async def run_skeptic(ctx: AgentContext) -> dict:
    # No bourdon client at all. No reads. Ever.
    await ctx.event("start", note="NO memory access -- first principles only")
    await ctx.event("access_check", tried="*", visible=[], blind=True,
                   note="Skeptic has no Bourdon token by construction")
    system = SKEPTIC.persona
    user = (
        f"{_ticket_text(ctx.ticket)}\n\n"
        "You have never seen any prior decision. From first principles, list the "
        "risks and at least one alternative a memory-primed team would overlook. "
        'Return JSON: {"risks":["..."],"alternatives":["..."],"stance":"one sentence"}'
    )
    data, u = await llm.complete_json(system, user, max_tokens=800)
    ctx.usage.add(u)
    await ctx.event("done", risks=data.get("risks", []),
                   alternatives=data.get("alternatives", []), stance=data.get("stance"))
    return data if isinstance(data, dict) else {"_raw": data}


async def run_curator(ctx: AgentContext, peer_outputs: dict) -> dict:
    """
    Runs after peers so it can see their concurrent writes. Detects
    contradictions and resolves under a stated policy.
    """
    await ctx.event("start", note="scanning concurrent writes for contradictions")
    decisions = await _read_decisions(ctx)
    await ctx.event("read", scope="all", items=[m["name"] for m in decisions])

    # Feed the curator the actual concurrent outputs (their committed claims).
    packed = json.dumps({
        "architect": peer_outputs.get("swarm-architect", {}),
        "implementer": peer_outputs.get("swarm-implementer", {}),
        "reviewer": peer_outputs.get("swarm-reviewer", {}),
        "skeptic": peer_outputs.get("swarm-skeptic", {}),
    }, default=str)[:4000]

    system = CURATOR.persona
    user = (
        f"Ticket: {ctx.ticket.get('title')}\n\n"
        f"Concurrent agent outputs:\n{packed}\n\n"
        "Find contradictions (incompatible claims about the same subject). "
        "Resolve each under your policy. Return JSON: "
        '{"contradictions":[{"subject":"...","claim_a":"...","by_a":"role",'
        '"claim_b":"...","by_b":"role","resolution":"...","policy_clause":"1|2|3",'
        '"winner":"role"}]}'
    )
    data, u = await llm.complete_json(system, user, max_tokens=1200)
    ctx.usage.add(u)
    contradictions = data.get("contradictions", []) if isinstance(data, dict) else []
    for c in contradictions:
        slug = _slug("contradiction-" + c.get("subject", "x"))[:60]
        if ctx.bourdon and ctx.memory_on:
            await ctx.bourdon.commit(CURATOR.id, [{
                "name": f"{slug}-{ctx.ticket['run_id']}", "type": "resolution",
                "visibility": "public",
                "summary": f"{c.get('resolution')} [policy {c.get('policy_clause')}]",
                "tags": ["resolution", ctx.ticket["run_id"]],
            }], role_narrative="Curator resolutions")
        await ctx.event("resolve", subject=c.get("subject"),
                       resolution=c.get("resolution"), policy=c.get("policy_clause"),
                       winner=c.get("winner"))
    await ctx.event("done", contradictions=contradictions)
    return {"contradictions": contradictions}


def _slug(s: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s or "entity"
