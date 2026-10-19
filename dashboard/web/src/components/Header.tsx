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
  const simPaused = useStore((s) => s.simPaused);
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
        className={"sim-btn" + (simPaused ? " paused" : simRunning ? " running" : "")}
        title={simPaused
          ? "Resume the drill from where it stopped"
          : simRunning
            ? "Pause the drill — it keeps its place in the cycle"
            : "Run the sensor drill — real events, real alerts"}
        onClick={() => {
          if (simPaused) {
            // Resuming is not the same as starting: the server kept the drill
            // suspended with all its state, so the cycle carries on where it
            // was rather than replaying the first two minutes.
            simulation.resume();
            transport.sendSim("resume");
          } else if (simRunning) {
            // Pause, not stop. The local beats are only timers, so they are
            // cleared and re-scheduled on resume; the server side is a real
            // process that is suspended with SIGSTOP and resumed with SIGCONT.
            simulation.pause();
            transport.sendSim("pause");
          } else {
            transport.sendSim("start", "stress");
          }
        }}
      >
        {simPaused ? "▶ RESUME" : simRunning ? "❚❚ PAUSE" : "▶ SIMULATE"}
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
