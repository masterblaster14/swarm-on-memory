import { useState } from "react";
import { api } from "../api";
import type { SwarmEvent } from "../types";

interface Props {
  runId: string | null;
  summary: any | null;
  parsed: any | null;
  suggestions: SwarmEvent | null;
  onCorrection: () => void;
}

export function Results({ runId, summary, parsed, suggestions, onCorrection }: Props) {
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState("");

  const decisions = summary?.outputs?.["swarm-architect"]?.decisions || [];
  const contradictions = summary?.outputs?.["swarm-curator"]?.contradictions || [];
  const review = summary?.outputs?.["swarm-reviewer"];
  const skeptic = summary?.outputs?.["swarm-skeptic"];

  async function submitReject(entity: string) {
    if (!runId || !reason.trim()) return;
    try {
      const r = await api.reject(runId, entity, reason);
      setMsg(`Committed correction ${r.committed}`);
      setRejecting(null);
      setReason("");
      onCorrection();
    } catch (e: any) {
      setMsg(String(e.message || e));
    }
  }

  return (
    <div className="card">
      <h2>Swarm output {runId ? `· ${runId}` : ""}</h2>

      {parsed?.entities?.length ? (
        <>
          <div className="small">Parsed entities (confidence):</div>
          <div style={{ marginBottom: 8 }}>
            {parsed.entities.map((e: any, i: number) => (
              <span className="tag" key={i}>
                {e.name} {Math.round((e.confidence || 0) * 100)}%
              </span>
            ))}
          </div>
        </>
      ) : null}

      {suggestions?.suggestions?.length ? (
        <>
          <h2 style={{ marginTop: 10 }}>Proactive suggestions</h2>
          {suggestions.suggestions.map((s: any, i: number) => (
            <div className="pref" key={i}>
              💡 {s.text} <span className="small">({s.based_on})</span>
            </div>
          ))}
        </>
      ) : null}

      {decisions.length > 0 && (
        <>
          <h2 style={{ marginTop: 10 }}>Decisions</h2>
          {decisions.map((d: any) => (
            <div className="decision" key={d.name}>
              <div className="d">
                <b>{d.name}</b> — {d.decision}{" "}
                <span className="small">({Math.round((d.confidence || 0) * 100)}%)</span>
              </div>
              <div className="why">why: {d.reasoning}</div>
              {d.cites?.length ? (
                <div className="cite">cites: {d.cites.join(", ")}</div>
              ) : null}
              {rejecting === d.name ? (
                <div className="row" style={{ marginTop: 4 }}>
                  <input
                    type="text"
                    placeholder="why is this wrong?"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                  <button onClick={() => submitReject(d.name)}>Commit correction</button>
                  <button className="ghost" onClick={() => setRejecting(null)}>
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  className="ghost"
                  style={{ marginTop: 4, padding: "3px 8px" }}
                  onClick={() => setRejecting(d.name)}
                >
                  Reject
                </button>
              )}
            </div>
          ))}
        </>
      )}

      {review?.verdicts?.length ? (
        <>
          <h2 style={{ marginTop: 10 }}>Reviewer · {review.overall}</h2>
          {review.verdicts.map((v: any, i: number) => (
            <div className="decision" key={i}>
              <div className="d">
                {v.status === "PASS" ? "✓" : "✗"} <b>{v.decision}</b> vs{" "}
                {v.checked_against}
              </div>
              <div className="why">{v.note}</div>
            </div>
          ))}
        </>
      ) : null}

      {skeptic?.risks?.length ? (
        <>
          <h2 style={{ marginTop: 10 }}>Skeptic (no memory)</h2>
          <div className="small">stance: {skeptic.stance}</div>
          {skeptic.risks.map((r: string, i: number) => (
            <div className="pref" key={i}>⚠ {r}</div>
          ))}
        </>
      ) : null}

      {contradictions.length > 0 && (
        <>
          <h2 style={{ marginTop: 10 }}>Contradictions resolved</h2>
          {contradictions.map((c: any, i: number) => (
            <div className="contra" key={i}>
              <b>{c.subject}</b>: {c.claim_a} <span className="small">({c.by_a})</span> vs{" "}
              {c.claim_b} <span className="small">({c.by_b})</span>
              <div className="small">
                → {c.resolution} · policy {c.policy_clause} · winner {c.winner}
              </div>
            </div>
          ))}
        </>
      )}

      {summary?.published && (summary.published.github || summary.published.notion) && (
        <>
          <h2 style={{ marginTop: 10 }}>Published</h2>
          {summary.published.github?.ok && summary.published.github.url ? (
            <div className="pref">
              🔀 GitHub PR{" "}
              <a href={summary.published.github.url} target="_blank" rel="noreferrer">
                #{summary.published.github.number}
              </a>
            </div>
          ) : summary.published.github && !summary.published.github.skipped ? (
            <div className="pref">⚠ GitHub: {summary.published.github.error}</div>
          ) : null}
          {summary.published.notion?.ok && summary.published.notion.url ? (
            <div className="pref">
              📄 Notion ticket{" "}
              <a href={summary.published.notion.url} target="_blank" rel="noreferrer">
                open
              </a>
            </div>
          ) : summary.published.notion && !summary.published.notion.skipped ? (
            <div className="pref">⚠ Notion: {summary.published.notion.error}</div>
          ) : null}
        </>
      )}

      {summary?.usage && (
        <div className="small" style={{ marginTop: 10 }}>
          Total: {summary.usage.total_tokens.toLocaleString()} tokens · $
          {summary.usage.cost_usd.toFixed(4)} · {summary.elapsed_s}s ·{" "}
          {summary.memory_on ? "memory ON" : "memory OFF"}
        </div>
      )}
      {msg && <div className="cite" style={{ marginTop: 6 }}>{msg}</div>}
      {!summary && <div className="small">Run a ticket to see decisions, review, and contradictions.</div>}
    </div>
  );
}
