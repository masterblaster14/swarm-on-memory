"""
Real Notion integration. Gated on NOTION_TOKEN. Reads a ticket page and
flips its Status property. No mocking: absent token -> {"enabled": false}.
"""
from __future__ import annotations

import httpx

from backend.config import NOTION_TICKETS_DB, NOTION_TOKEN

API = "https://api.notion.com/v1"


def enabled() -> bool:
    return bool(NOTION_TOKEN)


def can_create() -> bool:
    return bool(NOTION_TOKEN and NOTION_TICKETS_DB)


async def create_ticket(title: str, status: str = "Pending",
                        pr_url: str = "") -> dict:
    """Append a ticket row to the OpenSwarm Tickets database.

    Schema: 'Ticket Name' (title), 'Status' (select), 'PR's' (rich_text).
    Absent DB id -> {"ok": False, "skipped": True}.
    """
    if not can_create():
        return {"ok": False, "skipped": True}
    props: dict = {
        "Ticket Name": {"title": [{"text": {"content": title[:200]}}]},
        "Status": {"select": {"name": status}},
    }
    if pr_url:
        props["PR's"] = {"rich_text": [{"text": {"content": pr_url[:300]}}]}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{API}/pages", headers=_headers(),
                         json={"parent": {"database_id": NOTION_TICKETS_DB},
                               "properties": props})
        if r.status_code >= 300:
            return {"ok": False, "error": r.text[:400]}
        d = r.json()
    return {"ok": True, "id": d.get("id"), "url": d.get("url")}


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


async def get_page_ticket(page_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        p = await c.get(f"{API}/pages/{page_id}", headers=_headers())
        p.raise_for_status()
        page = p.json()
        # gather the page's text blocks as the body
        b = await c.get(f"{API}/blocks/{page_id}/children?page_size=50", headers=_headers())
        blocks = b.json().get("results", []) if b.status_code < 300 else []
    title = _extract_title(page)
    body = _extract_blocks_text(blocks)
    return {"title": title, "body": body, "url": page.get("url"), "id": page_id}


async def set_status(page_id: str, status_prop: str, value: str) -> dict:
    """Flip a status/select property. Works for 'status' or 'select' types."""
    async with httpx.AsyncClient(timeout=30) as c:
        # try status type first, fall back to select
        for kind in ("status", "select"):
            payload = {"properties": {status_prop: {kind: {"name": value}}}}
            r = await c.patch(f"{API}/pages/{page_id}", headers=_headers(), json=payload)
            if r.status_code < 300:
                return {"ok": True, "kind": kind, "value": value}
        return {"ok": False, "error": r.text[:300]}


def _extract_title(page: dict) -> str:
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", []))
    return ""


def _extract_blocks_text(blocks: list) -> str:
    out = []
    for blk in blocks:
        t = blk.get("type")
        rich = blk.get(t, {}).get("rich_text", []) if isinstance(blk.get(t), dict) else []
        line = "".join(r.get("plain_text", "") for r in rich)
        if line:
            out.append(line)
    return "\n".join(out)
