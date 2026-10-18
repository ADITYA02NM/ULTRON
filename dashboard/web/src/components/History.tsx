import { memo, useEffect, useRef } from "react";
import { store, useStore } from "../store/store";
import { bandForScore } from "../lib/bands";
import { cssVar } from "../lib/cssVars";

export type HistoryRange = "1h" | "6h" | "24h";

const RANGES: HistoryRange[] = ["1h", "6h", "24h"];

/** Pure range filter over [tsSec, value] points. Exported for tests. */
export function filterHistory(
  points: Array<[number, number]>,
  range: HistoryRange,
  nowMs: number,
): Array<[number, number]> {
  const spanSec = range === "1h" ? 3600 : range === "6h" ? 21600 : 86400;
  const cutoff = nowMs / 1000 - spanSec;
  return points.filter(([ts]) => ts >= cutoff);
}

/**
 * Seconds of history the graph shows while a drill is running.
 *
 * A drill lasts under a minute, so on any of the three ranges it lands as a
 * sliver a handful of pixels wide at the right edge — the graph looks frozen
 * while the score is in fact charging through the bands. Narrowing the window
 * to the drill itself is what lets the line stretch across the panel.
 */
export const LIVE_WINDOW_S = 90;

/** The stretch beat in ms, read from the token sheet so timing has one source. */
function beatMs(): number {
  const v = parseFloat(cssVar("--dur-live"));
  return Number.isFinite(v) && v > 0 ? v : 1100;
}

function HistoryImpl({ compact }: { compact?: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const noteRef = useRef<HTMLDivElement>(null);
  const range = useStore((s) => s.historyRange);
  // Only the compact copy in the risk panel goes live; the full-size view keeps
  // whatever range the operator chose.
  const live = useStore((s) => s.simRunning) && compact === true;

  useEffect(() => {
    let raf = 0;
    let looping = false;
    let size = "";

    const paint = (t: number) => {
      const c = canvasRef.current; if (!c) return;
      const s = store.getState();
      const isLive = s.simRunning && compact === true;
      const nowMs = Date.now();
      const hist = isLive
        ? s.history.filter(([ts]) => ts >= nowMs / 1000 - LIVE_WINDOW_S)
        : filterHistory(s.history, s.historyRange, nowMs);
      const dpr = window.devicePixelRatio || 1;
      const h0 = parseFloat(cssVar(compact ? "--spark-h-compact" : "--spark-h"));
      const w = Math.floor(c.clientWidth * dpr);
      const h = Math.floor(h0 * dpr);
      // Resizing the backing store clears it, so only touch it when it changed —
      // a live drill repaints every frame and this keeps that cheap.
      const key = `${w} ${h}`;
      if (key !== size) { c.width = w; c.height = h; size = key; }
      const ctx = c.getContext("2d"); if (!ctx) return;
      ctx.clearRect(0, 0, w, h);
      ctx.strokeStyle = cssVar("--border"); ctx.lineWidth = dpr; ctx.setLineDash([4 * dpr, 4 * dpr]);
      const fs = parseFloat(cssVar("--fs-xs")) * dpr;
      ctx.font = `${fs}px ${cssVar("--mono")}`; ctx.textAlign = "right"; ctx.textBaseline = "bottom";
      [30, 60, 85].forEach((g) => {
        const y = h - (g / 100) * h;
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w - fs * 2.2, y); ctx.stroke();
        ctx.fillStyle = cssVar("--muted-2"); ctx.fillText(String(g), w - 2 * dpr, y + fs / 2);
      });
      ctx.setLineDash([]);
      if (!hist.length) {
        if (noteRef.current) {
          noteRef.current.textContent = isLive ? "live — waiting for samples" : "history empty — skeleton";
        }
        return;
      }
      const lastV = hist[hist.length - 1]![1];
      if (noteRef.current) {
        noteRef.current.textContent = isLive
          ? `live drill · ${hist.length} pts · ${lastV}/100`
          : `${hist.length} samples · ${lastV} now`;
      }
      const t0 = hist[0]![0], t1 = hist[hist.length - 1]![0] || t0 + 1, span = Math.max(1, t1 - t0);
      // While live the newest segment grows out of the previous point once per
      // beat, so the line reads as stretching out rather than simply appearing.
      const beat = isLive ? beatMs() : 0;
      const grow = beat ? Math.min(1, (t % beat) / beat) : 1;
      let headX = 0, headY = h - (hist[hist.length - 1]![1] / 100) * h;
      for (let i = 1; i < hist.length; i++) {
        const x0 = ((hist[i - 1]![0] - t0) / span) * w;
        const y0 = h - (hist[i - 1]![1] / 100) * h;
        const y1 = h - (hist[i]![1] / 100) * h;
        let x1 = ((hist[i]![0] - t0) / span) * w;
        if (i === hist.length - 1) {
          if (grow < 1) x1 = x0 + (x1 - x0) * grow;
          headX = x1; headY = y1;
        }
        ctx.strokeStyle = cssVar("--" + bandForScore(hist[i]![1]).toLowerCase());
        ctx.lineWidth = (isLive ? 1.9 : 1.5) * dpr;
        // Oldest fades out, newest is full strength: the eye lands on the drill.
        ctx.globalAlpha = isLive ? 0.3 + 0.7 * (i / hist.length) : 1;
        ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
      }
      if (isLive) {
        ctx.globalAlpha = 1;
        ctx.fillStyle = cssVar("--" + bandForScore(hist[hist.length - 1]![1]).toLowerCase());
        const r = 2 * dpr;
        ctx.fillRect(headX - r, headY - r, r * 2, r * 2);
      }
      ctx.globalAlpha = 1;
    };

    const loop = (t: number) => { paint(t); raf = requestAnimationFrame(loop); };
    const sync = () => {
      if (compact === true && store.getState().simRunning) {
        if (!looping) { looping = true; raf = requestAnimationFrame(loop); }
        return;
      }
      looping = false;
      cancelAnimationFrame(raf); raf = 0;
      paint(performance.now());
    };

    const unsub = store.subscribe(sync);
    sync();
    window.addEventListener("resize", sync);
    return () => {
      unsub(); looping = false; cancelAnimationFrame(raf);
      window.removeEventListener("resize", sync);
    };
  }, [compact]);

  return (
    <div className={compact ? "hist-compact" : ""}>
      <canvas className={`spark${compact ? " spark-compact" : ""}${live ? " spark-live" : ""}`} ref={canvasRef} />
      {!compact && <div className="histnote" ref={noteRef}>awaiting history…</div>}
      {compact && <div className="histnote" ref={noteRef} />}
      {compact && !live && (
        <div className="hist-range" role="group" aria-label="History range">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              className={"hist-range-btn" + (range === r ? " active" : "")}
              aria-pressed={range === r}
              onClick={() => store.setHistoryRange(r)}
            >
              {r}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export const History = memo(HistoryImpl);
