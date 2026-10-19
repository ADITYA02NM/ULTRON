import { rc } from "../dev/rc";
import { memo, useEffect, useRef, useState } from "react";
import { store, useStore } from "../store/store";
import { clearPrefs } from "../lib/prefs";
import { utcClock } from "../lib/format";
import { logout } from "../lib/auth";
import { transport } from "../transport/transport";
import { simulation } from "../lib/simulation";

const LABEL: Record<string, string> = { live: "LIVE", stale: "STALE", offline: "OFFLINE" };

function HeaderImpl() {
  rc("Header");
  const conn = useStore((s) => s.conn);
  const band = useStore((s) => s.band);
  const bump = useStore((s) => s.bandBump);
  const simRunning = useStore((s) => s.simRunning);
  const [clock, setClock] = useState(utcClock());
  const headRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const t = window.setInterval(() => setClock(utcClock()), 1000);
    return () => window.clearInterval(t);
  }, []);

  // Escalation sweep across the header (one-shot).
  useEffect(() => {
    if (!bump || !headRef.current) return;
    const el = headRef.current;
    el.classList.remove("sweep");
    void el.offsetWidth;
    el.classList.add("sweep");
  }, [bump]);

  // One accent sweep when the link recovers to LIVE.
  const prevConn = useRef(conn);
  useEffect(() => {
    if (prevConn.current !== "live" && conn === "live" && headRef.current) {
      const el = headRef.current;
      el.classList.remove("sweep"); void el.offsetWidth; el.classList.add("sweep");
    }
    prevConn.current = conn;
  }, [conn]);

  return (
    <header ref={headRef}>
      <div className="wordmark">ULT<b>RON</b></div>
      <div className={"chip " + conn} role="status" aria-live="polite">
        <span className="led" />
        <span>{LABEL[conn]}</span>
        {conn === "live" && <span className="cursor" />}
      </div>
      <div className="spacer" />
      <div className="pill">{band}</div>
      <div className="clock">{clock} UTC</div>
      <div className="tag">MONITOR</div>
      <button
        className={"sim-btn" + (simRunning ? " running" : "")}
        title={simRunning
          ? "Stop the sensor drill"
          : "Run the sensor drill — real events, real alerts"}
        onClick={() => {
          if (simRunning) {
            // Stop both: a drill on the server, and any local sim left over
            // from the console, so the button and the truth agree again.
            simulation.stop();
            transport.sendSim("stop");
          } else {
            transport.sendSim("start", "stress");
          }
        }}
      >
        {simRunning ? "■ STOP" : "▶ SIMULATE"}
      </button>
      <button
        className="reset-chip"
        title="Reset the console — stop any drill and forget every event, alert, device and view preference"
        onClick={() => {
          // Stop the drill first. reset() clears simRunning locally, but the
          // server carries on pushing sim frames, so the flag would flip back
          // to running within a second and the reset would look like a no-op.
          simulation.stop();
          transport.sendSim("stop");
          // clearPrefs before reset: reset() rebuilds state from initial(),
          // which reads the stored preferences back off disk, so clearing
          // afterwards would leave them applied until the next reload.
          clearPrefs();
          store.reset();
        }}
      >
        ⟲ RESET
      </button>
      <button className="session-chip" title="Sign out" onClick={() => { transport.stop(); simulation.stop(); logout(); }}>SIGN OUT</button>
    </header>
  );
}

export const Header = memo(HeaderImpl);
