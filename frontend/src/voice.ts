/**
 * Voice input via mic capture -> 16kHz mono WAV -> Sarvam STT (server-side key).
 *
 * Web Speech API recognition was unreliable (Chrome/Windows silently no-ops,
 * needs Google's backend, unsupported in many browsers). We now capture raw
 * PCM through the Web Audio API, downsample to 16kHz mono, encode a WAV (the
 * format Sarvam transcribes most reliably), and POST it to /api/stt.
 * speak() still uses the browser's built-in synthesis for read-aloud.
 */

export function micSupported(): boolean {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) return false;
  return (
    typeof (window as any).AudioContext !== "undefined" ||
    typeof (window as any).webkitAudioContext !== "undefined"
  );
}

export interface Recorder {
  stop: () => void; // stops capture -> triggers transcription
  cancel: () => void; // aborts without transcribing
}

const TARGET_RATE = 16000;

/**
 * Starts capturing immediately. Call stop() to finish and transcribe.
 * onText fires with the transcript; onError with a message; onState reports
 * "recording" | "transcribing" | "idle".
 */
export async function startDictation(
  onText: (text: string) => void,
  onError: (msg: string) => void,
  onState?: (s: "recording" | "transcribing" | "idle") => void
): Promise<Recorder> {
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
  } catch (e: any) {
    onError("Mic permission denied");
    onState?.("idle");
    throw e;
  }

  const AC: typeof AudioContext =
    (window as any).AudioContext || (window as any).webkitAudioContext;
  const ctx = new AC();
  const source = ctx.createMediaStreamSource(stream);
  const bufSize = 4096;
  const processor = ctx.createScriptProcessor(bufSize, 1, 1);
  const chunks: Float32Array[] = [];
  let cancelled = false;

  processor.onaudioprocess = (e) => {
    chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  };
  source.connect(processor);
  processor.connect(ctx.destination);
  onState?.("recording");

  async function teardown() {
    processor.disconnect();
    source.disconnect();
    stream.getTracks().forEach((t) => t.stop());
    const rate = ctx.sampleRate;
    await ctx.close();
    return rate;
  }

  return {
    stop: async () => {
      const rate = await teardown();
      if (cancelled) return;
      onState?.("transcribing");
      try {
        const pcm = downsample(flatten(chunks), rate, TARGET_RATE);
        if (pcm.length < TARGET_RATE * 0.3) {
          onError("Too short — hold the mic and speak");
          return;
        }
        const wav = encodeWav(pcm, TARGET_RATE);
        const text = await transcribe(wav);
        if (text) onText(text);
        else onError("No speech detected");
      } catch (err: any) {
        onError(String(err?.message || err));
      } finally {
        onState?.("idle");
      }
    },
    cancel: async () => {
      cancelled = true;
      await teardown();
      onState?.("idle");
    },
  };
}

function flatten(chunks: Float32Array[]): Float32Array {
  const len = chunks.reduce((a, c) => a + c.length, 0);
  const out = new Float32Array(len);
  let off = 0;
  for (const c of chunks) {
    out.set(c, off);
    off += c.length;
  }
  return out;
}

function downsample(buf: Float32Array, from: number, to: number): Float32Array {
  if (to >= from) return buf;
  const ratio = from / to;
  const outLen = Math.floor(buf.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.floor((i + 1) * ratio);
    let sum = 0;
    for (let j = start; j < end && j < buf.length; j++) sum += buf[j];
    out[i] = sum / Math.max(1, end - start);
  }
  return out;
}

function encodeWav(pcm: Float32Array, rate: number): Blob {
  const buffer = new ArrayBuffer(44 + pcm.length * 2);
  const view = new DataView(buffer);
  const w = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  };
  w(0, "RIFF");
  view.setUint32(4, 36 + pcm.length * 2, true);
  w(8, "WAVE");
  w(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits
  w(36, "data");
  view.setUint32(40, pcm.length * 2, true);
  let off = 44;
  for (let i = 0; i < pcm.length; i++, off += 2) {
    const s = Math.max(-1, Math.min(1, pcm[i]));
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([view], { type: "audio/wav" });
}

async function transcribe(blob: Blob): Promise<string> {
  const fd = new FormData();
  fd.append("file", blob, "speech.wav");
  const r = await fetch("/api/stt", { method: "POST", body: fd });
  if (!r.ok) throw new Error(`stt ${r.status}`);
  const j = await r.json();
  if (!j.ok) throw new Error(j.error || "transcription failed");
  return (j.transcript || "").trim();
}

export function speak(text: string) {
  if (typeof window === "undefined" || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-US";
  u.rate = 1.02;
  window.speechSynthesis.speak(u);
}
