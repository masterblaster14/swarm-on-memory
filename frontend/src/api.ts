import type { Health, Entity, QueryAnswer, Profile } from "./types";

async function jget<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}
async function jpost<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

export const api = {
  health: () => jget<Health>("/api/health"),
  run: (title: string, body: string, memory_on: boolean) =>
    jpost<any>("/api/run", { title, body, memory_on }),
  ablation: (title: string, body: string) =>
    jpost<any>("/api/ablation", { title, body }),
  query: (question: string) => jpost<QueryAnswer>("/api/query", { question }),
  memory: (q: string) =>
    jget<{ query: string; count: number; entities: Entity[]; namespaces: string[] }>(
      `/api/memory?q=${encodeURIComponent(q)}`
    ),
  profile: () => jget<Profile>("/api/profile"),
  corrections: () => jget<{ corrections: Profile["corrections"] }>("/api/corrections"),
  reject: (run_id: string, entity: string, reason: string, namespace = "swarm-curator") =>
    jpost<{ ok: boolean; committed: string }>("/api/reject", {
      run_id,
      entity,
      reason,
      namespace,
    }),
  runs: () => jget<{ runs: any[] }>("/api/runs"),
};
