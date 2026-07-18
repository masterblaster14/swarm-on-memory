import type { RoleMeta, SwarmEvent } from "../types";

interface Props {
  roles: RoleMeta[];
  events: Record<string, SwarmEvent[]>; // agentId -> events
  running: boolean;
}

function summarize(e: SwarmEvent): JSX.Element {
  switch (e.kind) {
    case "start":
      return <span>{e.note || "started"}</span>;
    case "read":
      return (
        <span>
          read <b>{e.scope}</b>: {(e.items || []).join(", ") || "(nothing)"}
        </span>
      );
    case "access_check":
      return (
        <span>
          tried <code>{e.tried}</code>
          {e.blind ? (
            <span className="badge blind">BLIND</span>
          ) : (
            <span className="badge">saw {(e.visible || []).length}</span>
          )}
        </span>
      );
    case "commit":
      return (
        <span>
          commit <b>{e.entity}</b>
          <span className="badge commit">{e.namespace}</span>
        </span>
      );
    case "resolve":
      return (
        <span>
          resolved <b>{e.subject}</b> → {e.winner} (policy {e.policy})
        </span>
      );
    case "done":
      return <span><b>done</b></span>;
    default:
      return <span>{e.kind}</span>;
  }
}

export function AgentPanels({ roles, events, running }: Props) {
  return (
    <div className="agents">
      {roles.map((r) => {
        const evs = events[r.id] || [];
        const done = evs.some((e) => e.kind === "done");
        const active = running && evs.length > 0 && !done;
        return (
          <div className="agent" key={r.id} style={{ borderColor: active ? r.color : undefined }}>
            <div className="name">
              <span className="dot" style={{ background: r.color }} />
              {r.label}
            </div>
            <div className="scope">
              {r.reads} · {r.tier}
            </div>
            <div className={"status" + (active ? " live" : "")}>
              {active ? "working…" : done ? "complete" : running ? "queued" : "idle"}
            </div>
            <div className="log">
              {evs.map((e, i) => (
                <div className="ev" key={i}>
                  {summarize(e)}
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
