import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { Health, RoleMeta, SwarmEvent } from "./types";
import { useStream } from "./useStream";
import { AgentPanels } from "./components/AgentPanels";
import { TicketInput } from "./components/TicketInput";
import { Results } from "./components/Results";
import { Ablation } from "./components/Ablation";
import { MemoryInspector } from "./components/MemoryInspector";
import { QueryBox } from "./components/QueryBox";
import { Preferences } from "./components/Preferences";
import { TokenScoreboard } from "./components/TokenScoreboard";

const AGENT_ORDER = [
  "swarm-architect",
  "swarm-implementer",
  "swarm-reviewer",
  "swarm-skeptic",
  "swarm-curator",
];

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [memoryOn, setMemoryOn] = useState(true);
  const [running, setRunning] = useState(false);

  const [events, setEvents] = useState<Record<string, SwarmEvent[]>>({});
  const [runId, setRunId] = useState<string | null>(null);
  const [summary, setSummary] = useState<any | null>(null);
  const [parsed, setParsed] = useState<any | null>(null);
  const [suggestions, setSuggestions] = useState<SwarmEvent | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  const onEvent = useCallback((e: SwarmEvent) => {
    if (e.kind === "ticket_parsed") setParsed(e.parsed);
    if (e.kind === "suggestions") setSuggestions(e);
    if (e.kind === "run_done") {
      setSummary(e);
      setRunning(false);
      setRefreshKey((k) => k + 1);
    }
    if (e.agent) {
      setEvents((prev) => ({
        ...prev,
        [e.agent!]: [...(prev[e.agent!] || []), e],
      }));
    }
  }, []);

  const connected = useStream(onEvent);

  async function run() {
    setRunning(true);
    setEvents({});
    setSummary(null);
    setParsed(null);
    setSuggestions(null);
    setRunId(null);
    try {
      const res = await api.run(title, body, memoryOn);
      setRunId(res.run_id);
      setSummary(res);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      console.error(e);
    } finally {
      setRunning(false);
    }
  }

  const roles: RoleMeta[] =
    health?.roles.slice().sort(
      (a, b) => AGENT_ORDER.indexOf(a.id) - AGENT_ORDER.indexOf(b.id)
    ) || [];

  const integ = health?.integrations;

  return (
    <div className="app">
      <header className="top">
        <h1>Swarm on Bourdon</h1>
        <span className={"pill " + (connected ? "ok" : "off")}>
          {connected ? "live" : "offline"}
        </span>
        <span className={"pill " + (integ?.bourdon ? "ok" : "off")}>
          bourdon {health?.bourdon?.ok ? `· ${health.bourdon.tools?.length} tools` : ""}
        </span>
        <span className={"pill " + (integ?.llm ? "ok" : "off")}>llm</span>
        <span className={"pill " + (integ?.github ? "ok" : "off")}>github</span>
        <span className={"pill " + (integ?.notion ? "ok" : "off")}>notion</span>
        <span className={"pill " + (integ?.sarvam ? "ok" : "off")}>voice</span>
        <div className="spacer" />
        <span className="small">5 agents · one shared memory · asymmetric access</span>
      </header>

      <div className="grid">
        {/* Left column: input + preferences */}
        <div className="col">
          <TicketInput
            title={title}
            body={body}
            setTitle={setTitle}
            setBody={setBody}
            memoryOn={memoryOn}
            setMemoryOn={setMemoryOn}
            running={running}
            onRun={run}
          />
          <Ablation title={title} body={body} />
          <Preferences refreshKey={refreshKey} />
        </div>

        {/* Center column: agents + results */}
        <div className="col">
          <div className="card">
            <h2>Live agents</h2>
            <AgentPanels roles={roles} events={events} running={running} />
          </div>
          <Results
            runId={runId}
            summary={summary}
            parsed={parsed}
            suggestions={suggestions}
            onCorrection={() => setRefreshKey((k) => k + 1)}
          />
        </div>

        {/* Right column: scoreboard + query + memory */}
        <div className="col">
          <TokenScoreboard scoreboard={summary?.scoreboard || null} running={running} />
          <QueryBox />
          <MemoryInspector refreshKey={refreshKey} />
        </div>
      </div>
    </div>
  );
}
