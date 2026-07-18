import { useEffect, useRef, useState } from "react";
import type { SwarmEvent } from "./types";

/** Subscribes to the backend SSE stream and accumulates live agent events. */
export function useStream(onEvent: (e: SwarmEvent) => void) {
  const [connected, setConnected] = useState(false);
  const cb = useRef(onEvent);
  cb.current = onEvent;

  useEffect(() => {
    const es = new EventSource("/api/stream");
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as SwarmEvent;
        if (data.kind === "connected") {
          setConnected(true);
          return;
        }
        cb.current(data);
      } catch {
        /* keep-alive line */
      }
    };
    return () => es.close();
  }, []);

  return connected;
}
