import { useRef, useState } from "react";
import { micSupported, startDictation, type Recorder } from "../voice";

interface Props {
  title: string;
  body: string;
  setTitle: (s: string) => void;
  setBody: (s: string) => void;
  memoryOn: boolean;
  setMemoryOn: (b: boolean) => void;
  running: boolean;
  onRun: () => void;
}

const SAMPLE = {
  title: "Add discount codes to checkout",
  body: "Support percentage and fixed-amount discount codes at checkout. Codes have expiry dates and usage limits. Apply before tax. New endpoint POST /checkout/apply-discount.",
};

export function TicketInput({
  title,
  body,
  setTitle,
  setBody,
  memoryOn,
  setMemoryOn,
  running,
  onRun,
}: Props) {
  const [voiceState, setVoiceState] = useState<"idle" | "recording" | "transcribing">("idle");
  const [voiceErr, setVoiceErr] = useState("");
  const recRef = useRef<Recorder | null>(null);
  const voice = micSupported();

  async function dictate() {
    if (voiceState === "recording") {
      recRef.current?.stop();
      return;
    }
    if (voiceState === "transcribing") return;
    setVoiceErr("");
    try {
      recRef.current = await startDictation(
        (text) => setBody((body ? body + " " : "") + text),
        (msg) => setVoiceErr(msg),
        setVoiceState
      );
    } catch {
      /* startDictation already surfaced the error */
    }
  }

  return (
    <div className="card">
      <h2>Ticket</h2>
      <input
        type="text"
        placeholder="Ticket title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <textarea
        style={{ marginTop: 8 }}
        rows={5}
        placeholder="Describe the work…"
        value={body}
        onChange={(e) => setBody(e.target.value)}
      />
      <div className="row" style={{ marginTop: 10 }}>
        <button onClick={onRun} disabled={running || !title.trim()}>
          {running ? "Swarm running…" : "Run swarm"}
        </button>
        {voice && (
          <button
            className={"mic" + (voiceState === "recording" ? " rec" : "")}
            onClick={dictate}
            disabled={voiceState === "transcribing"}
            title="Dictate body (Sarvam)"
          >
            {voiceState === "recording"
              ? "● stop"
              : voiceState === "transcribing"
              ? "… transcribing"
              : "🎙 dictate"}
          </button>
        )}
        <button
          className="ghost"
          onClick={() => {
            setTitle(SAMPLE.title);
            setBody(SAMPLE.body);
          }}
        >
          Sample
        </button>
        <div className="spacer" />
        <label className="toggle" onClick={() => setMemoryOn(!memoryOn)}>
          <span className={"switch" + (memoryOn ? " on" : "")}>
            <span className="knob" />
          </span>
          Memory {memoryOn ? "ON" : "OFF"}
        </label>
      </div>
      {voiceErr && <div className="err" style={{ marginTop: 6 }}>🎙 {voiceErr}</div>}
    </div>
  );
}
