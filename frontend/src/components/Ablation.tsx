import { useState } from "react";
import { api } from "../api";
import type { Usage } from "../types";

interface Props {
  title: string;
  body: string;
}

export function Ablation({ title, body }: Props) {
  const [busy, setBusy] = useState(false);
  const [on, setOn] = useState<Usage | null>(null);
  const [off, setOff] = useState<Usage | null>(null);
  const [err, setErr] = useState("");

  async function run() {
    if (!title.trim()) {
      setErr("Enter a ticket title first.");
      return;
    }
    setBusy(true);
    setErr("");
    setOn(null);
    setOff(null);
    try {
      const res = await api.ablation(title, body);
      setOn(res.on.usage);
      setOff(res.off.usage);
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Ablation · memory on vs off</h2>
      <p className="small">
        Runs the same ticket through the full swarm twice — once with Bourdon,
        once with every agent's client nulled. Real token + cost counters.
      </p>
      <button onClick={run} disabled={busy}>
        {busy ? "Running both…" : "Run A/B"}
      </button>
      {err && <div className="err" style={{ marginTop: 8 }}>{err}</div>}
      {(on || off) && (
        <div className="abl" style={{ marginTop: 12 }}>
          <div className="side on">
            <div className="metric">MEMORY ON</div>
            <div className="big">{on ? on.total_tokens.toLocaleString() : "—"}</div>
            <div className="metric">tokens · ${on?.cost_usd.toFixed(4)}</div>
          </div>
          <div className="side off">
            <div className="metric">MEMORY OFF</div>
            <div className="big">{off ? off.total_tokens.toLocaleString() : "—"}</div>
            <div className="metric">tokens · ${off?.cost_usd.toFixed(4)}</div>
          </div>
        </div>
      )}
    </div>
  );
}
