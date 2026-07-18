import { useEffect, useState } from "react";
import { api } from "../api";
import type { Profile } from "../types";

export function Preferences({ refreshKey }: { refreshKey: number }) {
  const [p, setP] = useState<Profile | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    try {
      setP(await api.profile());
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  return (
    <div className="card">
      <h2>Learned preferences {busy ? "· …" : ""}</h2>
      <p className="small">
        Derived from {p?.basis_count ?? 0} human correction(s). Confidence{" "}
        {p ? Math.round((p.confidence || 0) * 100) : 0}%.
      </p>
      {p?.preferences?.length ? (
        p.preferences.map((pref, i) => (
          <div className="pref" key={i}>
            ✓ {pref}
          </div>
        ))
      ) : (
        <div className="small">No preferences learned yet. Reject an entity to teach the team.</div>
      )}
      {p?.corrections?.length ? (
        <>
          <h2 style={{ marginTop: 12 }}>Corrections</h2>
          {p.corrections.map((c, i) => (
            <div className="pref" key={i}>
              ✗ <b>{c.entity}</b>
              <div className="reason">{c.reason}</div>
            </div>
          ))}
        </>
      ) : null}
    </div>
  );
}
