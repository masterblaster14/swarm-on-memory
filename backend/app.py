"""
FastAPI backend. Holds all secrets + the Bourdon connection server-side.
Streams live agent events to the browser over SSE.
"""
from __future__ import annotations
import asyncio
import json
import uuid
from typing import Any

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend import nlp, store
from backend.bourdon_client import BourdonClient, probe_server
from backend.config import (BOURDON_BACKEND_TOKEN, integration_status,
                            load_role_tokens)
from backend.integrations import github, notion, sarvam
from backend.llm import Usage
from backend.orchestrator import run_swarm
from backend.roles import ALL_ROLES

app = FastAPI(title="Swarm-on-Bourdon")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

store.init_db()

# In-memory pub/sub of run events for SSE.
_subscribers: list[asyncio.Queue] = []


async def _broadcast(event: dict):
    for q in list(_subscribers):
        await q.put(event)


def _backend_client() -> BourdonClient:
    tokens = load_role_tokens()
    tok = BOURDON_BACKEND_TOKEN or tokens.get("swarm-curator") or tokens.get("swarm-architect", "")
    return BourdonClient(tok, "operator")


# ---- models ----------------------------------------------------------------
class RunReq(BaseModel):
    title: str
    body: str = ""
    memory_on: bool = True


class QueryReq(BaseModel):
    question: str


class RejectReq(BaseModel):
    run_id: str
    entity: str
    namespace: str = "swarm-curator"
    reason: str


class GitHubIssueReq(BaseModel):
    number: int


class NotionPageReq(BaseModel):
    page_id: str


# ---- meta ------------------------------------------------------------------
@app.get("/api/health")
async def health():
    tokens = load_role_tokens()
    out: dict[str, Any] = {"integrations": integration_status(),
                           "roles": []}
    for r in ALL_ROLES:
        out["roles"].append({"id": r.id, "label": r.label, "tier": r.tier,
                             "reads": r.reads, "color": r.color,
                             "has_token": r.id in tokens})
    try:
        probe = await probe_server(BOURDON_BACKEND_TOKEN or next(iter(tokens.values())))
        out["bourdon"] = {"ok": True, "tools": probe["tools"], "url": probe["url"]}
    except Exception as e:
        out["bourdon"] = {"ok": False, "error": str(e)}
    return out


# ---- SSE stream ------------------------------------------------------------
@app.get("/api/stream")
async def stream(request: Request):
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.append(q)

    async def gen():
        try:
            yield _sse({"kind": "connected"})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                    yield _sse(event)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            if q in _subscribers:
                _subscribers.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, default=str)}\n\n"


# ---- run -------------------------------------------------------------------
@app.post("/api/run")
async def run(req: RunReq):
    run_id = "run_" + uuid.uuid4().hex[:8]
    ticket = {"title": req.title, "body": req.body, "run_id": run_id}

    # NLP #1: parse the ticket into structured entities (real LLM call).
    parsed, u = await nlp.parse_ticket(req.title, req.body)
    await _broadcast({"kind": "ticket_parsed", "run_id": run_id, "parsed": parsed})

    # Recommendations: proactive suggestions from similar past tickets.
    try:
        sugg, _ = await nlp.suggestions(req.title, req.body, _backend_client())
        await _broadcast({"kind": "suggestions", "run_id": run_id, **sugg})
    except Exception as e:
        await _broadcast({"kind": "suggestions", "run_id": run_id,
                         "suggestions": [], "error": str(e)})

    seq = {"n": 0}

    async def emit(event: dict):
        event.setdefault("run_id", run_id)
        seq["n"] += 1
        store.save_event(run_id, seq["n"], event)
        await _broadcast(event)

    summary = await run_swarm(ticket, req.memory_on, emit, publish=True)
    summary["parsed"] = parsed
    store.save_run(summary)
    return summary


# ---- ablation compare (runs BOTH states) -----------------------------------
@app.post("/api/ablation")
async def ablation(req: RunReq):
    results = {}
    for memory_on in (True, False):
        run_id = "run_" + uuid.uuid4().hex[:8]
        ticket = {"title": req.title, "body": req.body, "run_id": run_id}

        async def emit(event: dict, _mo=memory_on):
            event.setdefault("run_id", run_id)
            event["ablation_side"] = "on" if _mo else "off"
            await _broadcast(event)

        summary = await run_swarm(ticket, memory_on, emit)
        store.save_run(summary)
        results["on" if memory_on else "off"] = summary
    await _broadcast({"kind": "ablation_done",
                     "on_usage": results["on"]["usage"],
                     "off_usage": results["off"]["usage"]})
    return results


# ---- NL query over memory (with citations) ---------------------------------
@app.post("/api/query")
async def query(req: QueryReq):
    data, u = await nlp.answer_query(req.question, _backend_client())
    return {"question": req.question, **data,
            "usage": {"total_tokens": u.total, "cost_usd": round(u.cost_usd, 6)}}


# ---- speech-to-text (Sarvam, mic dictation) --------------------------------
@app.post("/api/stt")
async def stt(file: UploadFile = File(...)):
    if not sarvam.enabled():
        return {"ok": False, "error": "Sarvam STT not configured"}
    audio = await file.read()
    return await sarvam.transcribe(
        audio,
        filename=file.filename or "speech.webm",
        content_type=file.content_type or "audio/webm",
    )


# ---- corrections + learned profile -----------------------------------------
@app.post("/api/reject")
async def reject(req: RejectReq):
    # Commit the rejection to Bourdon as a correction entity (curator namespace).
    client = _backend_client()
    slug = "reject-" + req.entity.lower().replace(" ", "-")[:40]
    await client.commit("swarm-curator", [{
        "name": slug, "type": "correction", "visibility": "public",
        "summary": f"REJECTED {req.entity}: {req.reason}",
        "tags": ["correction", "reject"],
    }], role_narrative="Human correction")
    store.add_correction(req.run_id, req.entity, req.namespace, req.reason)
    await _broadcast({"kind": "correction_added", "entity": req.entity,
                     "reason": req.reason})
    return {"ok": True, "committed": slug}


@app.get("/api/profile")
async def profile():
    corrections = store.list_corrections()
    data, u = await nlp.team_profile(corrections, _backend_client())
    return {**data, "corrections": corrections}


@app.get("/api/corrections")
async def corrections():
    return {"corrections": store.list_corrections()}


# ---- memory inspector ------------------------------------------------------
SWARM_NAMESPACES = ["swarm-architect", "swarm-architect-reasoning",
                    "swarm-implementer", "swarm-reviewer", "swarm-curator"]


@app.get("/api/memory")
async def memory(q: str = ""):
    """Full memory inspector: every entity with provenance + access level."""
    client = _backend_client()
    entities = await client.enumerate_entities(SWARM_NAMESPACES)
    if q:
        ql = q.lower()
        entities = [e for e in entities
                    if ql in (e["name"] or "").lower()
                    or ql in (e["summary"] or "").lower()
                    or any(ql in str(t).lower() for t in e.get("tags", []))]
    # newest-ish first: keep insertion but group by namespace
    return {"query": q, "count": len(entities), "entities": entities,
            "namespaces": SWARM_NAMESPACES}


@app.get("/api/runs")
async def runs():
    return {"runs": store.list_runs()}


# ---- integrations ----------------------------------------------------------
@app.get("/api/integrations")
async def integrations():
    return {"github": github.enabled(), "notion": notion.enabled()}


@app.post("/api/github/issue")
async def gh_issue(req: GitHubIssueReq):
    if not github.enabled():
        return {"enabled": False}
    return await github.get_issue(req.number)


@app.post("/api/notion/page")
async def notion_page(req: NotionPageReq):
    if not notion.enabled():
        return {"enabled": False}
    return await notion.get_page_ticket(req.page_id)
