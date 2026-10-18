/**
 * The handful of view preferences an operator sets and expects to keep.
 *
 * Everything else in the store is either server state that is re-hydrated over
 * the WebSocket on join (score, alerts, history, devices …) or genuinely
 * transient, so it is deliberately not stored. A hard refresh used to reset
 * these along with everything else; this is what fixes that.
 *
 * Every access is wrapped, because web storage throws in private modes, can
 * throw on quota, and does not exist at all in the node test environment.
 * Failing to remember a preference must never break the store.
 */

export type Prefs = {
  historyRange?: "1h" | "6h" | "24h";
  showDevices?: boolean;
  eventFilter?: string;
  selectedDevice?: string | null;
  focusNode?: string | null;
};

const KEY = "ultron.prefs";

function storage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

export function readPrefs(): Prefs {
  const s = storage();
  if (!s) return {};
  try {
    const raw = s.getItem(KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? (parsed as Prefs) : {};
  } catch {
    return {};
  }
}

export function writePrefs(patch: Prefs): void {
  const s = storage();
  if (!s) return;
  try {
    s.setItem(KEY, JSON.stringify({ ...readPrefs(), ...patch }));
  } catch {
    /* best effort: a preference that cannot be stored is not an error */
  }
}
