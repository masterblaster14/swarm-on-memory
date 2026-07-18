"""
Real GitHub integration via the REST API. Gated on GITHUB_TOKEN + repo.
No mocking: if the token is absent, endpoints return {"enabled": false} and
the UI shows the connector as off rather than faking data.
"""
from __future__ import annotations

import httpx

from backend.config import GITHUB_REPO, GITHUB_TOKEN

API = "https://api.github.com"


def enabled() -> bool:
    return bool(GITHUB_TOKEN and GITHUB_REPO)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def get_issue(number: int) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{API}/repos/{GITHUB_REPO}/issues/{number}", headers=_headers())
        r.raise_for_status()
        d = r.json()
    return {"title": d.get("title", ""), "body": d.get("body", "") or "",
            "number": d.get("number"), "state": d.get("state"), "url": d.get("html_url")}


async def open_pull_request(title: str, body: str, head: str, base: str = "main") -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{API}/repos/{GITHUB_REPO}/pulls", headers=_headers(),
                         json={"title": title, "body": body, "head": head, "base": base})
        if r.status_code >= 300:
            return {"ok": False, "status": r.status_code, "error": r.text[:400]}
        d = r.json()
    return {"ok": True, "number": d.get("number"), "url": d.get("html_url")}


async def _repo_is_empty(c: httpx.AsyncClient) -> bool:
    r = await c.get(f"{API}/repos/{GITHUB_REPO}", headers=_headers())
    return r.status_code < 300 and r.json().get("size", 1) == 0


async def _seed_initial_commit(c: httpx.AsyncClient, base: str) -> dict:
    """Initialize an empty repo with a first commit on `base` via the contents API."""
    import base64
    put = await c.put(f"{API}/repos/{GITHUB_REPO}/contents/README.md", headers=_headers(),
                      json={"message": "chore: initialize repository",
                            "branch": base,
                            "content": base64.b64encode(
                                b"# openswarm_agent\n\nSeeded by Swarm-on-Bourdon.\n").decode()})
    if put.status_code >= 300:
        return {"ok": False, "error": f"seed: {put.text[:200]}"}
    return {"ok": True}


async def create_branch_with_file(branch: str, path: str, content: str, message: str,
                                  base: str = "main") -> dict:
    """Create a branch off base and commit one file -- enough to open a real PR.

    Handles a brand-new empty repo by seeding the base branch's first commit.
    """
    import base64
    async with httpx.AsyncClient(timeout=30) as c:
        ref = await c.get(f"{API}/repos/{GITHUB_REPO}/git/ref/heads/{base}", headers=_headers())
        if ref.status_code >= 300:
            # Empty repo (409) -> seed an initial commit on base, then re-read.
            if await _repo_is_empty(c):
                seed = await _seed_initial_commit(c, base)
                if not seed.get("ok"):
                    return seed
                ref = await c.get(f"{API}/repos/{GITHUB_REPO}/git/ref/heads/{base}",
                                  headers=_headers())
            if ref.status_code >= 300:
                return {"ok": False, "error": f"base ref: {ref.text[:200]}"}
        sha = ref.json()["object"]["sha"]
        mk = await c.post(f"{API}/repos/{GITHUB_REPO}/git/refs", headers=_headers(),
                          json={"ref": f"refs/heads/{branch}", "sha": sha})
        if mk.status_code >= 300 and "already exists" not in mk.text.lower():
            return {"ok": False, "error": f"branch: {mk.text[:200]}"}
        put = await c.put(f"{API}/repos/{GITHUB_REPO}/contents/{path}", headers=_headers(),
                          json={"message": message, "branch": branch,
                                "content": base64.b64encode(content.encode()).decode()})
        if put.status_code >= 300:
            return {"ok": False, "error": f"commit: {put.text[:200]}"}
    return {"ok": True, "branch": branch}


async def publish_run(run_id: str, title: str, body: str, files: list[dict],
                     base: str = "main") -> dict:
    """Create a branch, commit the run's summary (+ any generated files), open a PR.

    Single entry point used by the orchestrator after a run completes. Returns
    {"ok": bool, "url": ..., "number": ...} or {"ok": False, "error": ...}.
    """
    if not enabled():
        return {"ok": False, "skipped": True}
    branch = f"swarm/{run_id}"
    # 1) branch + summary file (always committed so the PR has a diff)
    br = await create_branch_with_file(
        branch, f"swarm-runs/{run_id}.md", body,
        f"swarm({run_id}): summary", base=base)
    if not br.get("ok"):
        return {"ok": False, "error": br.get("error")}
    # 2) commit each implementer-generated file (best-effort, skip on clash)
    import base64
    async with httpx.AsyncClient(timeout=30) as c:
        for f in files or []:
            path, content = f.get("path"), f.get("content")
            if not path or content is None:
                continue
            await c.put(f"{API}/repos/{GITHUB_REPO}/contents/swarm-runs/{run_id}/{path}",
                        headers=_headers(),
                        json={"message": f"swarm({run_id}): {path}", "branch": branch,
                              "content": base64.b64encode(str(content).encode()).decode()})
    # 3) open the PR
    return await open_pull_request(title, body, head=branch, base=base)


async def check_runs(ref: str) -> dict:
    """Read CI check results for a ref (branch or SHA)."""
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{API}/repos/{GITHUB_REPO}/commits/{ref}/check-runs", headers=_headers())
        if r.status_code >= 300:
            return {"ok": False, "error": r.text[:300], "runs": []}
        d = r.json()
    runs = [{"name": x.get("name"), "status": x.get("status"),
             "conclusion": x.get("conclusion")} for x in d.get("check_runs", [])]
    failed = [x for x in runs if x["conclusion"] in ("failure", "timed_out")]
    return {"ok": True, "runs": runs, "failed": failed, "total": len(runs)}
