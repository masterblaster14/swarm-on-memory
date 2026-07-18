import { useRef, useState } from "react";
import { api } from "../api";
import type { QueryAnswer } from "../types";
import { micSupported, speak, startDictation, type Recorder } from "../voice";

export function QueryBox() {
  const [q, setQ] = useState("");
  const [ans, setAns] = useState<QueryAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [voiceState, setVoiceState] = useState<"idle" | "recording" | "transcribing">("idle");
  const [err, setErr] = useState("");
  const recRef = useRef<Recorder | null>(null);
  const voice = micSupported();

  async function ask(question: string) {
    if (!question.trim()) return;
    setBusy(true);
    setErr("");
    try {
      const r = await api.query(question);
      setAns(r);
      speak(r.answer);
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function mic() {
    if (voiceState === "recording") {
      recRef.current?.stop();
      return;
    }
    if (voiceState === "transcribing") return;
    setErr("");
    try {
      recRef.current = await startDictation(
        (text) => {
          setQ(text);
          ask(text);
        },
        (msg) => setErr(msg),
        setVoiceState
      );
    } catch {
      /* startDictation surfaced the error */
    }
  }

  return (
    <div className="card">
      <h2>Ask memory · cited answers {voice ? "· 🎙 voice" : ""}</h2>
      <div className="row">
        <input
          type="text"
          placeholder="e.g. how should money be stored?"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask(q)}
        />
        {voice && (
          <button
            className={"mic" + (voiceState === "recording" ? " rec" : "")}
            onClick={mic}
            disabled={voiceState === "transcribing"}
            title="Speak (Sarvam)"
          >
            {voiceState === "recording" ? "●" : voiceState === "transcribing" ? "…" : "🎙"}
          </button>
        )}
        <button onClick={() => ask(q)} disabled={busy}>
          {busy ? "…" : "Ask"}
        </button>
      </div>
      {err && <div className="err" style={{ marginTop: 8 }}>{err}</div>}
      {ans && (
        <div style={{ marginTop: 10 }}>
          <div className="answer">{ans.answer}</div>
          {ans.citations?.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div className="small">Citations:</div>
              {ans.citations.map((c, i) => (
                <div className="cite" key={i}>
                  ▸ {c.entity} <span className="small">— {c.agent}</span>
                </div>
              ))}
            </div>
          )}
          {ans.usage && (
            <div className="small" style={{ marginTop: 6 }}>
              {ans.usage.total_tokens} tokens · ${ans.usage.cost_usd.toFixed(4)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
