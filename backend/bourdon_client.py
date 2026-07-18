"""
Thin async wrapper over the Bourdon L6 MCP server (HTTP transport).

One client per role token. The token is sent as a Bearer header; Bourdon
resolves it to an AgentIdentity and enforces tier + grants server-side.
The Skeptic role has token=None -> BourdonClient is never constructed for it.
"""
from __future__ import annotations
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from backend.config import BOURDON_URL


class BourdonClient:
    def __init__(self, token: str, agent_id: str):
        self.agent_id = agent_id
        self._token = token

    def _transport(self) -> StreamableHttpTransport:
        return StreamableHttpTransport(
            url=BOURDON_URL,
            headers={"Authorization": f"Bearer {self._token}"},
        )

    async def _call(self, tool: str, args: dict[str, Any]) -> Any:
        async with Client(self._transport()) as c:
            res = await c.call_tool(tool, args)
            return res.data if hasattr(res, "data") else res

    async def list_tools(self) -> list[str]:
        async with Client(self._transport()) as c:
            return [t.name for t in await c.list_tools()]

    # ---- reads -------------------------------------------------------------
    async def find_entity(self, name: str, access_level: str = "public") -> dict:
        return await self._call("find_entity",
                                {"name": name, "access_level": access_level})

    async def query_agent_memory(self, agent: str, topic: str,
                                 access_level: str = "public") -> dict:
        return await self._call("query_agent_memory",
                                {"agent": agent, "topic": topic,
                                 "access_level": access_level})

    async def list_recent_work(self, since: str | None = None,
                               agent: str | None = None, limit: int = 50) -> dict:
        args: dict[str, Any] = {"limit": limit}
        if since:
            args["since"] = since
        if agent:
            args["agent"] = agent
        return await self._call("list_recent_work", args)

    async def cross_agent_summary(self, project: str,
                                  access_level: str = "team") -> dict:
        return await self._call("get_cross_agent_summary",
                                {"project": project, "access_level": access_level})

    async def agent_manifest(self, agent_id: str) -> dict:
        """Full visibility-filtered manifest for one agent (has known_entities)."""
        import json as _j
        async with Client(self._transport()) as c:
            res = await c.read_resource(f"agent-library://agents/{agent_id}/memory")
            if not res:
                return {}
            txt = getattr(res[0], "text", None) or "{}"
            try:
                return _j.loads(txt)
            except Exception:
                return {}

    async def enumerate_entities(self, agent_ids: list[str]) -> list[dict]:
        """
        Walk each namespace's manifest and flatten known_entities with
        provenance. This is how we list/search memory, since find_entity
        only matches exact names. Access is still enforced: reading a
        namespace this token isn't granted returns an empty/denied manifest.
        """
        out: list[dict] = []
        for aid in agent_ids:
            m = await self.agent_manifest(aid)
            if not isinstance(m, dict) or m.get("error"):
                continue
            for e in m.get("known_entities", []) or []:
                if not isinstance(e, dict) or not e.get("name"):
                    continue
                out.append({
                    "name": e.get("name"),
                    "type": e.get("type"),
                    "summary": e.get("summary", ""),
                    "tags": e.get("tags", []),
                    "visibility": e.get("visibility", "public"),
                    "valid_from": e.get("valid_from"),
                    "valid_to": e.get("valid_to"),
                    "agent": aid,
                })
        return out

    async def list_agents(self) -> Any:
        async with Client(self._transport()) as c:
            # list_agents is exposed as a resource-backed tool
            try:
                res = await c.call_tool("list_agents", {})
                return res.data if hasattr(res, "data") else res
            except Exception:
                return await c.read_resource("agent-library://agents")

    # ---- write -------------------------------------------------------------
    async def commit(self, agent_id: str, entities: list[dict],
                     agent_type: str = "other",
                     role_narrative: str | None = None) -> dict:
        args: dict[str, Any] = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "entities": entities,
        }
        if role_narrative:
            args["role_narrative"] = role_narrative
        return await self._call("commit_to_federation", args)


async def probe_server(token: str) -> dict:
    """Health probe used by the backend on startup and by /api/health."""
    c = BourdonClient(token, "operator")
    tools = await c.list_tools()
    return {"ok": True, "tools": tools, "url": BOURDON_URL}
