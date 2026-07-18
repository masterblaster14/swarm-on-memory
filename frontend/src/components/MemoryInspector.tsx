import { useEffect, useState } from "react";
import { api } from "../api";
import type { Entity } from "../types";

export function MemoryInspector({ refreshKey }: { refreshKey: number }) {
  const [q, setQ] = useState("");
  const [ents, setEnts] = useState<Entity[]>([]);
  const [count, setCount] = useState(0);
  const [busy, setBusy] = useState(false);

  async function load(query: string) {
    setBusy(true);
    try {
      const r = await api.memory(query);
      setEnts(r.entities);
      setCount(r.count);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    load(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  return (
    <div className="card">
      <h2>Memory inspector · {count} entities</h2>
      <div className="row">
        <input
          type="text"
          placeholder="filter by name / summary / tag"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load(q)}
        />
        <button className="ghost" onClick={() => load(q)} disabled={busy}>
          {busy ? "…" : "Search"}
        </button>
      </div>
      <div style={{ maxHeight: 340, overflowY: "auto", marginTop: 8 }}>
        {ents.map((e) => (
          <div className="ent" key={`${e.agent}:${e.name}`}>
            <div className="en">{e.name}</div>
            <div className="prov">
              {e.type} · committed by <b>{e.agent}</b> · {e.visibility}
              {e.valid_from ? ` · from ${e.valid_from}` : ""}
            </div>
            {e.summary && <div className="small">{e.summary}</div>}
            <div style={{ marginTop: 3 }}>
              {(e.tags || []).map((t) => (
                <span className="tag" key={t}>
                  {t}
                </span>
              ))}
            </div>
          </div>
        ))}
        {!ents.length && <div className="small">No entities match.</div>}
      </div>
    </div>
  );
}
