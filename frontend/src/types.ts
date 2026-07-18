export type RoleId =
  | "swarm-architect"
  | "swarm-implementer"
  | "swarm-reviewer"
  | "swarm-skeptic"
  | "swarm-curator";

export interface RoleMeta {
  id: string;
  label: string;
  tier: string;
  reads: string;
  color: string;
  has_token: boolean;
}

export interface Health {
  integrations: { github: boolean; notion: boolean; llm: boolean; bourdon: boolean; sarvam?: boolean };
  roles: RoleMeta[];
  bourdon?: { ok: boolean; tools?: string[]; url?: string; error?: string };
}

export interface ScoreRow {
  agent: string;
  label: string;
  no_mem_in: number;
  no_mem_out: number;
  mem_in: number;
  mem_out: number;
  saved_pct: number;
  cost_no_mem: number;
  cost_mem: number;
}

export interface Scoreboard {
  rows: ScoreRow[];
  totals: ScoreRow & { cost_saved: number };
  full_context_tokens: number;
  basis: string;
}

export interface SwarmEvent {
  kind: string;
  run_id?: string;
  agent?: string;
  ablation_side?: "on" | "off";
  [k: string]: any;
}

export interface Entity {
  name: string;
  type: string;
  summary: string;
  tags: string[];
  visibility: string;
  valid_from?: string | null;
  valid_to?: string | null;
  agent: string;
}

export interface Citation {
  entity: string;
  agent: string;
}

export interface QueryAnswer {
  question: string;
  answer: string;
  citations: Citation[];
  _matched_entities?: string[];
  usage?: { total_tokens: number; cost_usd: number };
}

export interface Correction {
  run_id?: string;
  entity: string;
  namespace?: string;
  reason: string;
}

export interface Profile {
  preferences: string[];
  confidence: number;
  basis_count: number;
  corrections: Correction[];
}

export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
}
