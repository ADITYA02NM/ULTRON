import { memo, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { UEvent } from "../store/store";
import { store, useStore } from "../store/store";
import { bandForScore } from "../lib/bands";
import { cssVar } from "../lib/cssVars";

export type HistoryRange = "1h" | "6h" | "24h";

const RANGES: HistoryRange[] = ["1h", "6h", "24h"];

/** How many events the hover readout will list before it gives up. */
const TIP_MAX = 5;

/** Held high so the readout never re-renders from sensor traffic. */
const NO_EVENTS: UEvent[] = [];

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

/** A sample of the line, and where it sits in the plotted array. */
export type HoverPick = { index: number; ts: number; value: number };

/**
 * The sample nearest a horizontal fraction of the plot, where 0 is the left
 * edge and 1 the right. Pure, and the inverse of `fracAt`. Exported for tests.
 */
export function pickAt(
  points: Array<[number, number]>,
  t0: number,
  span: number,
  frac: number,
): HoverPick | null {
  if (!points.length) return null;
  const clamped = Math.min(1, Math.max(0, frac));
  const target = t0 + clamped * Math.max(1, span);
  let best = 0;
  let bestD = Math.abs(points[0]![0] - target);
  for (let i = 1; i < points.length; i++) {
    const d = Math.abs(points[i]![0] - target);
    if (d < bestD) { bestD = d; best = i; }
  }
  return { index: best, ts: points[best]![0], value: points[best]![1] };
}

/** The fraction a sample sits at. Out-of-range indexes report the left edge. */
export function fracAt(
  points: Array<[number, number]>,
  t0: number,
  span: number,
  index: number,
): number {
  const p = points[index];
  if (!p) return 0;
  return Math.min(1, Math.max(0, (p[0] - t0) / Math.max(1, span)));
}

/**
 * How far either side of the cursor still counts as "at that time".
 *
 * A fixed number of seconds would be unfindable at range: across a 24 h window
 * one pixel is minutes, so six pixels of slop is minutes too, and the promise
 * "what happened here" stays honest at every zoom. The floor keeps a tight
 * window — a live drill spans 90 s — from collapsing to nothing to hit.
 */
export function toleranceSec(spanSec: number, widthPx: number): number {
  return Math.max(10, (spanSec / Math.max(1, widthPx)) * 6);
}

/** Events inside the tolerance window, newest first, capped. */
export function eventsNear<T extends { ts: number }>(
  events: T[],
  ts: number,
  tolSec: number,
  max: number,
): T[] {
  return events
    .filter((e) => Math.abs(e.ts - ts) <= tolSec)
    .sort((a, b) => b.ts - a.ts)
    .slice(0, max);
}

/**
 * Where the readout hangs. Under the pointer whenever there is one, so it never
 * covers the moment being pointed at; under the sample itself when the cursor
 * was moved by the keyboard, which has no pointer to hang from.
 */
export function tipY(cursorY: number | null, value: number, heightCss: number): number {
  if (cursorY !== null) return cursorY;
  return heightCss - (value / 100) * heightCss;
}

/** UTC clock, the same convention the event feed uses. */
function clockOf(ts: number): string {
  return new Date(ts * 1000).toISOString().slice(11, 19);
}

/** The stretch beat in ms, read from the token sheet so timing has one source. */
function beatMs(): number {
  const v = parseFloat(cssVar("--dur-live"));
  return Number.isFinite(v) && v > 0 ? v : 1100;
}

/** Geometry from the last paint, so handlers can hit-test without repainting. */
type Geo = { pts: Array<[number, number]>; t0: number; span: number; css: number; hcss: number };

function HistoryImpl({ compact }: { compact?: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const noteRef = useRef<HTMLDivElement>(null);
  const range = useStore((s) => s.historyRange);
  // Only the compact copy in the risk panel goes live; the full-size view keeps
  // whatever range the operator chose.
  const live = useStore((s) => s.simRunning) && compact === true;

  // The cursor lives in a ref, not in state: a live drill repaints every frame
  // and a state update per frame would flood the tree. Only the reading itself
  // is state, and it changes when you cross a sample.
  const [hover, setHover] = useState<
    { pick: HoverPick; tol: number; frac: number; y: number } | null
  >(null);
  const cursorRef = useRef<number | null>(null);
  // Pointer height in CSS px down from the top of the plot, or null when the
  // cursor was last moved by the keyboard — there is no pointer to hang the
  // readout from in that case, so it falls back to the sample's own height.
  const cursorYRef = useRef<number | null>(null);
  const shownRef = useRef<{ pick: HoverPick; y: number } | null>(null);

  // Only subscribe to events while the readout is open — it is capped at 500
  // rows, so holding it unconditionally would re-render on every sensor frame.
  const hovering = hover !== null;
  const events = useStore((s) => (hovering ? s.events : NO_EVENTS));

  useEffect(() => {
    let raf = 0;
    let looping = false;
    let size = "";
    let geo: Geo | null = null;

    let lastFrac = 0;
    const publish = (p: HoverPick | null, y: number) => {
      const prev = shownRef.current;
      if (!p) {
        if (!prev) return;
        shownRef.current = null;
        setHover(null);
        return;
      }
      // Same sample at the same height as last paint: nothing moved, so nothing
      // re-renders. The vertical half of that check is what lets the readout
      // follow the pointer down the plot without a render per stray pixel.
      if (prev && prev.pick.index === p.index && prev.pick.ts === p.ts && prev.y === y) return;
      shownRef.current = { pick: p, y };
      // The tolerance and the side of the plot come from the frame that was just
      // painted, not from the pick, so they always describe what is on screen.
      setHover({ pick: p, tol: geo ? toleranceSec(geo.span, geo.css) : 10, frac: lastFrac, y });
    };

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
        geo = null;
        publish(null, 0);
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
      const px = (i: number) => ((hist[i]![0] - t0) / span) * w;
      const py = (i: number) => h - (hist[i]![1] / 100) * h;
      const headX = px(hist.length - 1);
      const headY = py(hist.length - 1);

      // The line is drawn as a smooth monotone curve, not straight segments.
      // A 72 falling to an 8 between two adjacent samples used to be a vertical
      // cliff, which is exactly what read as the chart glitching. Each span
      // still takes the colour of the band it lands in.
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      for (let i = 1; i < hist.length; i++) {
        const x0 = px(i - 1), y0 = py(i - 1), y1 = py(i);
        let x1 = px(i);
        if (i === hist.length - 1) x1 = x0 + (x1 - x0) * grow;
        const mx = (x0 + x1) / 2;
        ctx.strokeStyle = cssVar("--" + bandForScore(hist[i]![1]).toLowerCase());
        ctx.lineWidth = (isLive ? 1.9 : 1.5) * dpr;
        // Oldest fades out, newest is full strength: the eye lands on the drill.
        ctx.globalAlpha = isLive ? 0.3 + 0.7 * (i / hist.length) : 1;
        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.bezierCurveTo(mx, y0, mx, y1, x1, y1);
        ctx.stroke();
      }

      // A node per event, coloured by the band that sample sat in, so a scan
      // reads as a mark on the line rather than a random wiggle. Skipped down
      // to a stride when the samples are denser than the pixels available.
      const stride = Math.max(1, Math.ceil(hist.length / Math.max(8, w / (6 * dpr))));
      for (let i = 0; i < hist.length; i += stride) {
        const isHead = i === hist.length - 1;
        const x = isHead ? headX : px(i);
        const y = isHead ? headY : py(i);
        const r = (isHead ? 3 : 2.1) * dpr;
        const colour = cssVar("--" + bandForScore(hist[i]![1]).toLowerCase());
        ctx.globalAlpha = isLive ? 0.35 + 0.65 * (i / hist.length) : 0.9;
        ctx.fillStyle = colour;
        ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
        // A rim keeps each node legible where the line runs behind it.
        ctx.globalAlpha = 1;
        ctx.strokeStyle = cssVar("--border");
        ctx.lineWidth = dpr;
        ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.stroke();
      }
      if (isLive) {
        // The head breathes, so a live console is visibly alive.
        ctx.globalAlpha = 0.18;
        ctx.fillStyle = cssVar("--" + bandForScore(hist[hist.length - 1]![1]).toLowerCase());
        ctx.beginPath();
        ctx.arc(headX, headY, 4.5 * dpr + Math.sin(t / 240) * 1.6 * dpr, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      geo = { pts: hist, t0, span, css: c.clientWidth || 1, hcss: h / dpr };
      // Where the cursor is, resolved against this frame's data — so during a
      // live drill the rule stays over the same moment as the line scrolls
      // under it rather than over the same pixel.
      const cur = cursorRef.current;
      const hit = cur === null ? null : pickAt(hist, t0, span, cur);
      let tip = 0;
      if (hit) {
        lastFrac = cur === null ? 0 : Math.min(1, Math.max(0, cur));
        tip = tipY(cursorYRef.current, hit.value, geo.hcss);
        const px = ((hit.ts - t0) / span) * w;
        const py = h - (hit.value / 100) * h;
        ctx.strokeStyle = cssVar("--muted");
        ctx.lineWidth = dpr;
        ctx.setLineDash([2 * dpr, 2 * dpr]);
        ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, h); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = cssVar("--text");
        ctx.beginPath(); ctx.arc(px, py, 2.5 * dpr, 0, Math.PI * 2); ctx.fill();
      }
      publish(hit, tip);
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
    // While the loop runs the next frame picks the cursor up on its own; when it
    // is parked this is what makes the cursor move at all.
    const nudge = () => { if (!looping) sync(); };

    const onMove = (ev: PointerEvent) => {
      const c = canvasRef.current;
      const r = c && geo && geo.pts.length ? c.getBoundingClientRect() : null;
      if (!r || !r.width) return;
      cursorRef.current = Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width));
      cursorYRef.current = ev.clientY - r.top;
      nudge();
    };
    const onLeave = () => {
      if (cursorRef.current === null && cursorYRef.current === null) return;
      cursorRef.current = null;
      cursorYRef.current = null;
      nudge();
    };
    const onKey = (ev: KeyboardEvent) => {
      if (!geo || !geo.pts.length) return;
      const n = geo.pts.length;
      const at = cursorRef.current === null ? null : pickAt(geo.pts, geo.t0, geo.span, cursorRef.current);
      let i = at ? at.index : n - 1;
      if (ev.key === "ArrowLeft") i = Math.max(0, i - 1);
      else if (ev.key === "ArrowRight") i = Math.min(n - 1, i + 1);
      else if (ev.key === "Home") i = 0;
      else if (ev.key === "End") i = n - 1;
      else if (ev.key === "Escape") { onLeave(); return; }
      else return;
      ev.preventDefault();
      cursorRef.current = fracAt(geo.pts, geo.t0, geo.span, i);
      // No pointer in this path, so the readout hangs from the sample instead.
      cursorYRef.current = null;
      nudge();
    };

    const unsub = store.subscribe(sync);
    sync();
    const c = canvasRef.current;
    c?.addEventListener("pointermove", onMove);
    c?.addEventListener("pointerleave", onLeave);
    c?.addEventListener("blur", onLeave);
    c?.addEventListener("keydown", onKey);
    window.addEventListener("resize", sync);
    return () => {
      unsub(); looping = false; cancelAnimationFrame(raf);
      cursorRef.current = null; cursorYRef.current = null; shownRef.current = null;
      c?.removeEventListener("pointermove", onMove);
      c?.removeEventListener("pointerleave", onLeave);
      c?.removeEventListener("blur", onLeave);
      c?.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", sync);
    };
  }, [compact]);

  const near = hover ? eventsNear(events, hover.pick.ts, hover.tol, TIP_MAX) : [];

  return (
    <div className={"hist-wrap" + (compact ? " hist-compact" : "")}>
      <canvas
        className={`spark${compact ? " spark-compact" : ""}${live ? " spark-live" : ""}`}
        ref={canvasRef}
        tabIndex={0}
        role="img"
        aria-label={`Risk score over the last ${compact && live ? "90 seconds" : range}. Hover, or use the arrow keys, to see what happened at a moment.`}
      />
      {hover && (
        <div
          className={"hist-tip" + (hover.frac < 0.5 ? " left" : " right")}
          // Unitless on purpose: the token sheet is where the px lives, so the
          // readout is positioned by one calc() in CSS rather than a hard number
          // smuggled in from here.
          style={{ "--tip-y": String(Math.round(hover.y)) } as CSSProperties}
          role="status"
        >
          <div className="hist-tip-hd">
            <span className="num">{clockOf(hover.pick.ts)}</span>
            <span className={"hist-sev sev-" + bandForScore(hover.pick.value).toLowerCase()}>
              {hover.pick.value}
            </span>
          </div>
          {near.length === 0 ? (
            // The store keeps only the most recent events, so a stretch further
            // back than that is genuinely unknown rather than quiet. Say so.
            <div className="hist-tip-none">no events retained for this moment</div>
          ) : (
            near.map((e) => (
              <div className="hist-tip-ev" key={e.id}>
                <span className="num">{clockOf(e.ts)}</span>
                <span className={"hist-sev sev-" + e.sev}>{e.kind}</span>
                <span className="hist-tip-s">{e.summary}</span>
              </div>
            ))
          )}
        </div>
      )}
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
