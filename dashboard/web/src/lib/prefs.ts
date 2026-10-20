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

/**
 * Forget the stored view preferences, so the next store built starts on the
 * defaults rather than on whatever the previous operator was looking at.
 *
 * Only the reset button calls this, and it calls it *before* store.reset():
 * reset() rebuilds its state from initial(), which reads these back, so
 * clearing afterwards would leave them applied until the next reload.
 */
export function clearPrefs(): void {
  const s = storage();
  if (!s) return;
  try {
    s.removeItem(KEY);
  } catch {
    /* best effort, same as writePrefs */
  }
}

const TOPOLOGY_KEY = "ultron.topology";

/**
 * The LAN devices the console has actually observed, remembered across reloads.
 *
 * The server replays history and unacknowledged alerts when an operator joins,
 * but it does not replay devices -- those are published once, as they are seen.
 * Without this the topology map is blank on every reload until something new
 * appears on the wire, which reads as a broken sensor rather than a quiet
 * network. Kept under its own key on purpose: RESET clears the event log and
 * the view preferences, but the topology is observed fact and survives.
 */
export function readTopology<T>(): Record<string, T> {
  const s = storage();
  if (!s) return {};
  try {
    const raw = s.getItem(TOPOLOGY_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null
      ? (parsed as Record<string, T>)
      : {};
  } catch {
    return {};
  }
}

export function writeTopology(devices: Record<string, unknown>): void {
  const s = storage();
  if (!s) return;
  try {
    s.setItem(TOPOLOGY_KEY, JSON.stringify(devices));
  } catch {
    /* best effort: a topology that cannot be stored is not an error */
  }
}

/** Only the auth boundary calls this. A fresh operator must not inherit the
 *  previous one's map, so sign-out wipes it along with the rest of the state. */
export function clearTopology(): void {
  const s = storage();
  if (!s) return;
  try {
    s.removeItem(TOPOLOGY_KEY);
  } catch {
    /* best effort, same as clearPrefs */
  }
}
