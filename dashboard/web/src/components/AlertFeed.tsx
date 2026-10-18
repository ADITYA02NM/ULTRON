import { rc } from "../dev/rc";
import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useStore } from "../store/store";
import type { AlertD } from "../contracts/ws";
import { transport } from "../transport/transport";
import { utcTime } from "../lib/format";
import { useReducedMotion } from "../hooks/useNow";
import { cssVar } from "../lib/cssVars";
import { eventIntel, intelRows, type EventIntel } from "../lib/eventIntel";

/** A token length as a number, with a fallback for the very first paint. */
function len(name: string, fallback: number): number {
  const v = parseFloat(cssVar(name));
  return Number.isFinite(v) ? v : fallback;
}

/**
 * The floating intel box for one event.
 *
 * Two deliberate choices. It is rendered through a portal onto <body> so no
 * scrolling ancestor can clip it — `.feed` is `overflow: auto`, and an
 * ancestor with a transform or a filter would also capture a fixed child. And
 * it is placed from the row's measured rect rather than by CSS, so it works
 * wherever the feed happens to sit: it opens below the row, or above it when
 * there is no room underneath.
 *
 * It renders hidden for one frame while the browser measures it, then commits
 * its position. That is what the `.pending` class is for.
 */
const IntelBox = memo(function IntelBox({
  intel,
  src,
  anchor,
}: {
  intel: EventIntel;
  src: string;
  anchor: DOMRect;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const gap = len("--intel-gap", 8);
    const below = anchor.bottom + gap;
    const above = anchor.top - gap - el.offsetHeight;
    const fitsBelow = below + el.offsetHeight <= window.innerHeight;
    const top = !fitsBelow && above > 0 ? above : below;
    const maxLeft = window.innerWidth - el.offsetWidth - gap;
    setPos({ top, left: Math.max(gap, Math.min(anchor.left, maxLeft)) });
  }, [anchor]);

  const rows = intelRows(intel);

  return (
    <div
      ref={ref}
      role="tooltip"
      className={"intel" + (pos ? "" : " pending")}
      style={pos ? { top: pos.top, left: pos.left } : undefined}
    >
      <div className="intel-hd">
        <span className="intel-kind">{intel.kind}</span>
        <span className="intel-src">{src}</span>
      </div>
      {rows.length > 0 && (
        <dl className="intel-rows">
          {rows.map(([k, v]) => (
            <div className="intel-row" key={k}>
              <dt>{k}</dt>
              <dd className={k === "command" ? "intel-cmd" : undefined}>{v}</dd>
            </div>
          ))}
        </dl>
      )}
      <p className="intel-means">{intel.means}</p>
      {intel.caution && (
        <p className="intel-caution">
          <span className="intel-caution-tag">Not proven</span>
          {intel.caution}
        </p>
      )}
    </div>
  );
});

const AlertCard = memo(function AlertCard({ a, isNew }: { a: AlertD; isNew: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const intel = eventIntel(a.title);

  useEffect(() => {
    if (!isNew || reduce || !ref.current) return;
    const el = ref.current;
    el.animate(
      [{ transform: `translateY(-${cssVar("--enter-offset")})`, opacity: 0 }, { transform: "none", opacity: 1 }],
      { duration: parseFloat(cssVar("--dur-enter")), easing: cssVar("--ease") }
    );
  }, [isNew, reduce]);

  // The anchor is a snapshot, so it is stale the moment anything moves.
  useEffect(() => {
    if (!anchor) return;
    const drop = () => setAnchor(null);
    window.addEventListener("scroll", drop, true);
    window.addEventListener("resize", drop);
    return () => {
      window.removeEventListener("scroll", drop, true);
      window.removeEventListener("resize", drop);
    };
  }, [anchor]);

  const open = useCallback(() => {
    if (ref.current) setAnchor(ref.current.getBoundingClientRect());
  }, []);
  const close = useCallback(() => setAnchor(null), []);

  return (
    <div
      className={"alert sev-" + (a.sev || "info") + (a.ack ? " acked" : "") + (intel ? " has-intel" : "")}
      ref={ref}
      tabIndex={intel ? 0 : undefined}
      onMouseEnter={open}
      onMouseLeave={close}
      onFocus={open}
      onBlur={close}
    >
      <div className="bar" />
      <div className="body">
        <div className="hd">
          <span className="ttl">{a.title || "Alert"}</span>
          <span className="src">{a.src}</span>
          <span className="tm">{a.ts ? utcTime(a.ts) : ""}</span>
        </div>
        <div className="txt">{a.body}</div>
        {a.ack && <div className="stamp">ACK · {utcTime(a.ack_ts ?? a.ts)}</div>}
      </div>
      <button className="ackbtn" disabled={a.ack} onClick={() => transport.sendAck(a.id)}>
        {a.ack ? "ACKED" : "ACK"}
      </button>
      {intel && anchor && createPortal(<IntelBox intel={intel} src={a.src} anchor={anchor} />, document.body)}
    </div>
  );
});

function AlertFeedImpl() {
  rc("AlertFeed");
  const alerts = useStore((s) => s.alerts);
  const topId = useRef<string | null>(null);
  const isNewTop = alerts[0] ? alerts[0].id !== topId.current : false;
  topId.current = alerts[0]?.id ?? null;

  if (!alerts.length) {
    return <div className="feed"><div className="empty">No active alerts — mesh nominal</div></div>;
  }
  return (
    <div className="feed">
      {alerts.map((a, i) => <AlertCard key={a.id} a={a} isNew={i === 0 && isNewTop} />)}
    </div>
  );
}

export const AlertFeed = memo(AlertFeedImpl);
