/** Animated startup mark.
 *
 *  The risk engine sits at the centre of the mesh with the watched nodes around
 *  it; a detection wave leaves the core and each node reports in, in turn. It is
 *  the appliance's own diagram — detect at the edge, decide in the middle,
 *  alert outward — rather than decoration.
 *
 *  Motion lives in global.css as keyframes so the mark carries no CSS units of
 *  its own (the token lint forbids raw px/ms/hex here), and so the
 *  prefers-reduced-motion rule can switch the whole thing off in one place.
 */
export function BootMark() {
  return (
    <svg
      className="boot-mark"
      viewBox="0 0 120 120"
      width="148"
      height="148"
      role="img"
      aria-label="ULTRON is starting"
    >
      {/* the perimeter being swept */}
      <circle className="bm-ring bm-spin" cx="60" cy="60" r="54" strokeDasharray="3 7" />
      <circle className="bm-ring" cx="60" cy="60" r="44" />

      {/* detection waves leaving the core */}
      <circle className="bm-wave" cx="60" cy="60" r="52" />
      <circle className="bm-wave bm-wave-late" cx="60" cy="60" r="52" />

      {/* the mesh of watched nodes */}
      <path className="bm-edge" d="M60 14 L100 82 L20 82 Z" />
      <path className="bm-spoke" d="M60 60 L60 14" />
      <path className="bm-spoke" d="M60 60 L100 82" />
      <path className="bm-spoke" d="M60 60 L20 82" />

      {/* nodes reporting in, one after another */}
      <circle className="bm-node" cx="60" cy="14" r="4.5" />
      <circle className="bm-node bm-node-late" cx="100" cy="82" r="4.5" />
      <circle className="bm-node bm-node-later" cx="20" cy="82" r="4.5" />

      {/* the risk engine */}
      <circle className="bm-core" cx="60" cy="60" r="5.5" />
    </svg>
  );
}
