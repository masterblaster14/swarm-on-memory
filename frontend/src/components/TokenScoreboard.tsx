import type { Scoreboard } from "../types";

interface Props {
  scoreboard: Scoreboard | null;
  running: boolean;
}

const n = (v: number) => (v ? v.toLocaleString() : "—");

export function TokenScoreboard({ scoreboard, running }: Props) {
  const sb = scoreboard;
  const t = sb?.totals;
  return (
    <div className="card">
      <h2>
        Token Scoreboard
        <span className="sb-cap">estimated · full-context vs retrieval</span>
      </h2>

      <div className="sb-heads">
        <div className="sb-head no">
          <div className="metric">NO MEMORY</div>
          <div className="big">{t ? n(t.no_mem_in + t.no_mem_out) : "—"}</div>
          <div className="metric">full context every call</div>
        </div>
        <div className="sb-head mem">
          <div className="metric">WITH MEMORY</div>
          <div className="big">{t ? n(t.mem_in + t.mem_out) : "—"}</div>
          <div className="metric">shared-brain retrieval</div>
        </div>
        <div className="sb-head saved">
          <div className="metric">↓ SAVED</div>
          <div className="big">{t ? `${t.saved_pct}%` : "—"}</div>
          <div className="metric">{t ? `$${t.cost_saved.toFixed(4)}` : "run a pipeline"}</div>
        </div>
      </div>

      <table className="sb-table">
        <thead>
          <tr>
            <th>AGENT</th>
            <th>No-Mem In</th>
            <th>No-Mem Out</th>
            <th>Mem In</th>
            <th>Mem Out</th>
            <th>% Saved</th>
            <th>$ Cost</th>
          </tr>
        </thead>
        <tbody>
          {sb?.rows?.length ? (
            sb.rows.map((r) => (
              <tr key={r.agent}>
                <td className="ag">{r.label}</td>
                <td>{n(r.no_mem_in)}</td>
                <td>{n(r.no_mem_out)}</td>
                <td>{n(r.mem_in)}</td>
                <td>{n(r.mem_out)}</td>
                <td className={r.saved_pct > 0 ? "pos" : ""}>{r.saved_pct ? `${r.saved_pct}%` : "—"}</td>
                <td>${r.cost_mem.toFixed(4)}</td>
              </tr>
            ))
          ) : (
            ["Architect", "Implementer", "Reviewer", "Skeptic", "Curator"].map((l) => (
              <tr key={l} className="ghost-row">
                <td className="ag">{l}</td>
                <td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>
              </tr>
            ))
          )}
          {t && (
            <tr className="sb-total">
              <td className="ag">Total</td>
              <td>{n(t.no_mem_in)}</td>
              <td>{n(t.no_mem_out)}</td>
              <td>{n(t.mem_in)}</td>
              <td>{n(t.mem_out)}</td>
              <td className="pos">{t.saved_pct}%</td>
              <td>${t.cost_mem.toFixed(4)}</td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="small sb-foot">
        {running
          ? "Pipeline running… scoreboard fills when the run completes."
          : "Estimated — full-context (no memory) vs retrieval (with memory). Illustrative, not live API billing."}
      </div>
    </div>
  );
}
