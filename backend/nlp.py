"""
Natural-language capabilities, all grounded in real LLM calls + Bourdon reads:

1. parse_ticket   -> structured entities w/ relationships + confidence
2. answer_query   -> NL question over memory, answered WITH citations to the
                     exact entities and the committing agent
3. team_profile   -> plain-language preference profile derived from corrections
4. suggestions    -> proactive tips drawn from similar past tickets via Bourdon
"""
from __future__ import annotations
import json

from backend import llm
from backend.bourdon_client import BourdonClient
from backend.llm import Usage


async def parse_ticket(title: str, body: str) -> tuple[dict, Usage]:
    system = (
        "You extract structured engineering entities from a developer ticket. "
        "Identify concrete subjects (fields, endpoints, models, constraints) and "
        "the relationships between them, each with a confidence score."
    )
    user = (
        f"TITLE: {title}\nBODY:\n{body}\n\n"
        "Return JSON: {\"entities\":[{\"name\":\"...\",\"type\":\"field|endpoint|model|constraint|auth\","
        "\"summary\":\"...\",\"confidence\":0.0-1.0}],"
        "\"relationships\":[{\"from\":\"...\",\"to\":\"...\",\"rel\":\"...\"}]}"
    )
    data, u = await llm.complete_json(system, user, max_tokens=900)
    if not isinstance(data, dict):
        data = {"entities": [], "relationships": []}
    return data, u


SWARM_NAMESPACES = ["swarm-architect", "swarm-architect-reasoning",
                    "swarm-implementer", "swarm-reviewer", "swarm-curator"]


def _rank(entities: list[dict], terms: list[str], limit: int = 12) -> list[dict]:
    scored = []
    for e in entities:
        hay = f"{e.get('name','')} {e.get('summary','')} {' '.join(map(str, e.get('tags', [])))}".lower()
        score = sum(1 for t in terms if t in hay)
        if score:
            scored.append((score, e))
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:limit]]


async def answer_query(question: str, bourdon: BourdonClient) -> tuple[dict, Usage]:
    """Answer a question about memory, citing exact entities + committing agents."""
    terms = _keywords(question)
    all_entities = await bourdon.enumerate_entities(SWARM_NAMESPACES)
    matches = _rank(all_entities, terms) or all_entities[:8]

    context_lines = []
    for m in matches:
        who = m.get("agent", "")
        summ = m.get("summary", "")
        context_lines.append(f'- entity "{m.get("name")}" committed by [{who}]: {summ}')
    context = "\n".join(context_lines) or "(no matching memory entities found)"

    system = (
        "You answer questions about a team's shared memory. You may ONLY use the "
        "provided entities. Every claim must cite the entity name and the agent "
        "that committed it. If memory does not contain the answer, say so."
    )
    user = (
        f"QUESTION: {question}\n\nMEMORY ENTITIES:\n{context}\n\n"
        "Return JSON: {\"answer\":\"...\",\"citations\":[{\"entity\":\"...\",\"agent\":\"...\"}]}"
    )
    data, u = await llm.complete_json(system, user, max_tokens=700)
    if not isinstance(data, dict):
        data = {"answer": str(data), "citations": []}
    data["_matched_entities"] = [m.get("name") for m in matches]
    return data, u


async def team_profile(corrections: list[dict], bourdon: BourdonClient | None) -> tuple[dict, Usage]:
    """Plain-language profile derived from accumulated corrections."""
    corr_text = "\n".join(
        f"- rejected: {c.get('entity')} ({c.get('reason')})" for c in corrections
    ) or "(no corrections recorded yet)"
    system = (
        "You derive a team's coding preferences from their history of rejections. "
        "Write short, plain-language preference statements (e.g. 'prefers integer "
        "cents', 'requires auth on all new endpoints', 'rejects camelCase')."
    )
    user = (
        f"REJECTIONS:\n{corr_text}\n\n"
        "Return JSON: {\"preferences\":[\"...\"],\"confidence\":0.0-1.0,"
        "\"basis_count\":<int number of corrections used>}"
    )
    data, u = await llm.complete_json(system, user, max_tokens=500)
    if not isinstance(data, dict):
        data = {"preferences": [], "confidence": 0, "basis_count": 0}
    data["basis_count"] = len(corrections)
    return data, u


async def suggestions(title: str, body: str, bourdon: BourdonClient | None) -> tuple[dict, Usage]:
    """Proactive tips drawn from similar past tickets in memory."""
    prior = []
    if bourdon:
        try:
            terms = _keywords(title + " " + body)
            all_entities = await bourdon.enumerate_entities(SWARM_NAMESPACES)
            for m in _rank(all_entities, terms):
                prior.append(f'- {m.get("name")} [{m.get("agent","")}]: {m.get("summary","")}')
        except Exception:
            pass
    prior_text = "\n".join(prior[:12]) or "(no similar prior work in memory)"
    system = (
        "You give proactive, specific suggestions before a team starts a ticket, "
        "grounded in what the shared memory already knows from similar past work."
    )
    user = (
        f"NEW TICKET:\n{title}\n{body}\n\nRELATED MEMORY:\n{prior_text}\n\n"
        "Return JSON: {\"suggestions\":[{\"text\":\"...\",\"based_on\":\"entity or 'general'\"}]}"
    )
    data, u = await llm.complete_json(system, user, max_tokens=600)
    if not isinstance(data, dict):
        data = {"suggestions": []}
    return data, u


_STOP = set("the a an of to in on for with and or is are be by from at as into "
            "should must add new create update ticket please make sure all any".split())


def _keywords(text: str) -> list[str]:
    import re
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", (text or "").lower())
    out, seen = [], set()
    for w in words:
        if w in _STOP or w in seen:
            continue
        seen.add(w); out.append(w)
    return out[:8]
