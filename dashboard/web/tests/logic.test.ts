import { describe, it, expect } from "vitest";
import { bandForScore, isWorse, bandRank } from "../src/lib/bands";
import { LatencyWindow, ClockSync } from "../src/lib/latency";
import { isEnvelope, isPong } from "../src/contracts/ws";
import { Store } from "../src/store/store";
import {
  eventsNear, filterHistory, fracAt, pickAt, tipY, toleranceSec,
} from "../src/components/History";
import type { Envelope } from "../src/contracts/ws";
import { clearPrefs, readPrefs } from "../src/lib/prefs";

const env = (t: string, d: unknown, ts = Date.now() / 1000): Envelope =>
  ({ t, ts, d } as unknown as Envelope);

describe("bands", () => {
  it("maps score to band at the exact edges", () => {
    expect(bandForScore(0)).toBe("GREEN");
    expect(bandForScore(29)).toBe("GREEN");
    expect(bandForScore(30)).toBe("YELLOW");
    expect(bandForScore(59)).toBe("YELLOW");
    expect(bandForScore(60)).toBe("RED");
    expect(bandForScore(84)).toBe("RED");
    expect(bandForScore(85)).toBe("PURPLE");
    expect(bandForScore(100)).toBe("PURPLE");
  });
  it("orders severity and detects worsening", () => {
    expect(bandRank("GREEN")).toBeLessThan(bandRank("PURPLE"));
    expect(isWorse("RED", "GREEN")).toBe(true);
    expect(isWorse("GREEN", "RED")).toBe(false);
  });
});

describe("latency math", () => {
  it("computes percentiles", () => {
    const w = new LatencyWindow(100);
    for (let i = 1; i <= 100; i++) w.add(i);
    expect(w.p50()).toBeGreaterThanOrEqual(50);
    expect(w.p95()).toBeGreaterThanOrEqual(95);
    expect(w.count()).toBe(100);
  });
  it("estimates a stable clock offset", () => {
    const c = new ClockSync();
    // server is 1000ms ahead; rtt 20ms => offset ~1000
    for (let i = 0; i < 5; i++) c.addPong(1000, 2010, 1020);
    expect(c.ready()).toBe(true);
    expect(Math.abs(c.offsetMs() - 1000)).toBeLessThan(5);
  });
});

describe("contract guards", () => {
  it("accepts valid envelopes and pongs", () => {
    expect(isEnvelope({ t: "score", ts: 1, d: { v: 5 } })).toBe(true);
    expect(isEnvelope({ t: "nope", ts: 1, d: {} })).toBe(false);
    expect(isPong({ ctl: "pong", c: 1, s: 2 })).toBe(true);
    expect(isPong({ t: "score" })).toBe(false);
  });
});

describe("store.applyBatch", () => {
  it("updates score + appends history", () => {
    const s = new Store();
    s.applyBatch([env("score", { v: 42 })]);
    expect(s.getState().score).toBe(42);
    expect(s.getState().history.length).toBe(1);
  });
  it("bumps on worsening band only", () => {
    const s = new Store();
    s.applyBatch([env("band", { b: "GREEN" })]);
    const b0 = s.getState().bandBump;
    s.applyBatch([env("band", { b: "RED" })]);   // worse -> bump
    s.applyBatch([env("band", { b: "GREEN" })]); // better -> no bump
    expect(s.getState().bandBump).toBe(b0 + 1);
    expect(s.getState().band).toBe("GREEN");
  });
  it("dedupes alert ids and counts open vs acked", () => {
    const s = new Store();
    s.applyBatch([env("alert", { id: "x", sev: "red", title: "t", src: "s", body: "b", ack: false })]);
    s.applyBatch([env("alert", { id: "x", sev: "red", title: "t", src: "s", body: "b", ack: false })]); // dup
    s.applyBatch([env("alert", { id: "y", sev: "red", title: "t", src: "s", body: "b", ack: true })]);
    const st = s.getState();
    expect(st.alerts.length).toBe(2);
    expect(st.openCount).toBe(1);
    expect(st.ackDone).toBe(1);
  });
  it("ackLocal decrements open and marks acked", () => {
    const s = new Store();
    s.applyBatch([env("alert", { id: "x", sev: "red", title: "t", src: "s", body: "b", ack: false })]);
    expect(s.getState().openCount).toBe(1);
    s.ackLocal("x");
    expect(s.getState().openCount).toBe(0);
    expect(s.getState().alerts[0]!.ack).toBe(true);
  });
  // CP5 contract: suricata/wifi arrive as t:"event", never t:"alert".
  it("routes suricata/wifi events into detection layers", () => {
    const s = new Store();
    s.applyBatch([env("event", { topic: "ultron/suricata/eth0", node: "pi3a", kind: "suricata", sev: "red", summary: "ET x" })]);
    s.applyBatch([env("event", { topic: "ultron/wifi/rogue", node: "pi3a", kind: "wifi", sev: "yellow", summary: "rogue AP" })]);
    expect(s.getState().layers.idsCount).toBe(1);
    expect(s.getState().layers.wifiRogue).toBe(true);
  });
});

describe("store.reset", () => {
  it("wipes live state but preserves the auth phase", () => {
    const s = new Store();
    s.setAuth(true, true);
    s.applyBatch([
      env("score", { v: 88 }),
      env("band", { b: "PURPLE" }),
      env("lan", { mac: "AA:BB:CC:DD:EE:FF", ip: "192.168.100.50", vendor: "X", known: false }),
      env("alert", { id: "z", sev: "red", title: "t", src: "s", body: "b", ack: false }),
    ]);
    expect(Object.keys(s.getState().devices).length).toBe(1);
    expect(s.getState().openCount).toBe(1);

    s.reset();

    const st = s.getState();
    expect(st.authPhase).toBe("ready"); // auth survives the wipe
    expect(st.score).toBe(0);
    expect(st.band).toBe("GREEN");
    expect(st.alerts.length).toBe(0);
    expect(st.events.length).toBe(0);
    expect(Object.keys(st.devices).length).toBe(0);
    expect(st.openCount).toBe(0);
  });

  it("leaves sign-out working after a reset", () => {
    const s = new Store();
    s.setAuth(true, true);
    s.reset();
    s.setAuth(false, true);
    expect(s.getState().authPhase).toBe("login");
  });
});

describe("alert acknowledgement round-trip", () => {
  it("refreshes the row when the node re-stamps a repeat id with ack=true", () => {
    const s = new Store();
    s.setAuth(true, true);
    s.applyBatch([env("alert", { id: "c1-1", sev: "yellow", title: "t", src: "s", body: "b", ack: false })]);
    expect(s.getState().alerts).toHaveLength(1);
    expect(s.getState().openCount).toBe(1);
    expect(s.getState().ackDone).toBe(0);

    s.applyBatch([
      env("alert", { id: "c1-1", sev: "yellow", title: "t", src: "s", body: "b", ack: true, ack_ts: 1700000000 }),
    ]);
    const st = s.getState();
    expect(st.alerts).toHaveLength(1);
    expect(st.alerts[0]!.ack).toBe(true);
    expect(st.alerts[0]!.ack_ts).toBe(1700000000);
    expect(st.openCount).toBe(0);
    expect(st.ackDone).toBe(1);
  });

  it("ignores a plain duplicate and never double-counts one acknowledgement", () => {
    const s = new Store();
    s.setAuth(true, true);
    s.applyBatch([env("alert", { id: "c1-2", sev: "info", title: "t", src: "s", body: "b", ack: false })]);
    s.applyBatch([env("alert", { id: "c1-2", sev: "info", title: "t", src: "s", body: "b", ack: false })]);
    expect(s.getState().alerts).toHaveLength(1);
    expect(s.getState().ackTotal).toBe(1);
    expect(s.getState().openCount).toBe(1);

    s.applyBatch([env("alert", { id: "c1-2", sev: "info", title: "t", src: "s", body: "b", ack: true, ack_ts: 1 })]);
    s.applyBatch([env("alert", { id: "c1-2", sev: "info", title: "t", src: "s", body: "b", ack: true, ack_ts: 1 })]);
    expect(s.getState().alerts).toHaveLength(1);
    expect(s.getState().ackDone).toBe(1);
    expect(s.getState().openCount).toBe(0);
  });
});

describe("filterHistory", () => {
  const nowMs = 1_000_000_000_000; // fixed epoch ms
  it("drops points older than the range span", () => {
    const points: Array<[number, number]> = [
      [nowMs / 1000 - 7200, 10], // 2h ago -> outside 1h
      [nowMs / 1000 - 1800, 20], // 30m ago -> inside 1h
      [nowMs / 1000, 30],        // now -> inside 1h
    ];
    const out = filterHistory(points, "1h", nowMs);
    expect(out.length).toBe(2);
    expect(out.every(([, v]) => v !== 10)).toBe(true);
  });
  it("handles an empty series", () => {
    expect(filterHistory([], "24h", nowMs)).toEqual([]);
  });
  it("24h keeps a full day of recent points", () => {
    const points: Array<[number, number]> = [
      [nowMs / 1000 - 86000, 1], // just under 24h ago
      [nowMs / 1000 - 100000, 2], // >24h ago -> dropped
      [nowMs / 1000 - 60, 3],
    ];
    const out = filterHistory(points, "24h", nowMs);
    expect(out.length).toBe(2);
    expect(out.map(([, v]) => v).sort()).toEqual([1, 3]);
  });
});

describe("stored view preferences", () => {
  const bag = new Map<string, string>();
  const fake: Storage = {
    get length() {
      return bag.size;
    },
    clear: () => bag.clear(),
    getItem: (k: string) => (bag.has(k) ? (bag.get(k) as string) : null),
    key: (n: number) => {
      const ks = Array.from(bag.keys());
      return n >= 0 && n < ks.length ? ks[n] : null;
    },
    removeItem: (k: string) => {
      bag.delete(k);
    },
    setItem: (k: string, v: string) => {
      bag.set(k, v);
    },
  };
  const install = (s: Storage | null) => {
    if (s) (globalThis as { localStorage?: Storage }).localStorage = s;
    else delete (globalThis as { localStorage?: Storage }).localStorage;
  };

  it("persists a change and restores it into a store built later", () => {
    bag.clear();
    install(fake);
    try {
      const a = new Store();
      expect(a.getState().historyRange).toBe("24h");
      a.setHistoryRange("1h");
      a.setEventFilter("alerts");
      a.setShowDevices(true);
      const b = new Store();
      expect(b.getState().historyRange).toBe("1h");
      expect(b.getState().eventFilter).toBe("alerts");
      expect(b.getState().showDevices).toBe(true);
    } finally {
      install(null);
    }
  });

  it("rejects a stored value of the wrong shape instead of trusting it", () => {
    bag.clear();
    bag.set("ultron.prefs", JSON.stringify({ historyRange: "9h", showDevices: "yes" }));
    install(fake);
    try {
      const s = new Store();
      expect(s.getState().historyRange).toBe("24h");
      expect(s.getState().showDevices).toBe(false);
    } finally {
      install(null);
    }
  });

  it("survives unparseable storage rather than throwing", () => {
    bag.clear();
    bag.set("ultron.prefs", "{not json");
    install(fake);
    try {
      expect(new Store().getState().historyRange).toBe("24h");
    } finally {
      install(null);
    }
  });

  it("falls back to defaults when there is no storage at all", () => {
    install(null);
    const s = new Store();
    expect(s.getState().historyRange).toBe("24h");
    expect(s.getState().eventFilter).toBe("all");
    expect(s.getState().showDevices).toBe(false);
    expect(s.getState().selectedDevice).toBeNull();
    expect(s.getState().focusNode).toBeNull();
  });

  it("clearPrefs forgets what was stored, so the next store starts on defaults", () => {
    bag.clear(); install(fake);
    try {
      const a = new Store();
      a.setHistoryRange("1h");
      a.setShowDevices(true);
      expect(readPrefs().historyRange).toBe("1h");

      clearPrefs();

      expect(readPrefs()).toEqual({});
      const b = new Store();
      expect(b.getState().historyRange).toBe("24h");
      expect(b.getState().showDevices).toBe(false);
    } finally { install(null); }
  });

  it("clearPrefs is a no-op without storage rather than a throw", () => {
    install(null);
    expect(() => clearPrefs()).not.toThrow();
    expect(readPrefs()).toEqual({});
  });
});

describe("history hover", () => {
  // 1000, 1010, 1030, 1060 — unevenly spaced on purpose, the way a real feed
  // arrives, so a test cannot pass by assuming a regular step.
  const pts: Array<[number, number]> = [
    [1000, 10],
    [1010, 40],
    [1030, 70],
    [1060, 90],
  ];

  it("maps a fraction of the plot back to the nearest sample", () => {
    expect(pickAt(pts, 1000, 60, 0)!.ts).toBe(1000);
    expect(pickAt(pts, 1000, 60, 1)!.ts).toBe(1060);
    // a quarter in is t=1015, whose nearest neighbours are 1010 and 1030 — 5
    // beats 15, so the earlier one wins
    expect(pickAt(pts, 1000, 60, 0.25)!.value).toBe(40);
    const mid = pickAt(pts, 1000, 60, 0.5)!;
    expect(mid.ts).toBe(1030);
    expect(mid.index).toBe(2);
    expect(mid.value).toBe(70);
  });

  it("clamps a fraction outside the plot instead of falling off the end", () => {
    expect(pickAt(pts, 1000, 60, -3)!.ts).toBe(1000);
    expect(pickAt(pts, 1000, 60, 9)!.ts).toBe(1060);
  });

  it("returns nothing for an empty series", () => {
    expect(pickAt([], 1000, 60, 0.5)).toBeNull();
  });

  it("fracAt inverts pickAt, so a keypress lands where a pointer would", () => {
    for (let i = 0; i < pts.length; i++) {
      expect(pickAt(pts, 1000, 60, fracAt(pts, 1000, 60, i))!.index).toBe(i);
    }
    expect(fracAt(pts, 1000, 60, 99)).toBe(0);
  });

  it("scales the tolerance with the zoom so the promise holds at any range", () => {
    // 24h across 600px: a pixel is 144s, so six of them is 864s of slop
    expect(toleranceSec(86400, 600)).toBeCloseTo(864, 5);
    // an hour across the same width: 36s
    expect(toleranceSec(3600, 600)).toBeCloseTo(36, 5);
    // a live drill spans 90s, which at six pixels would be under a second —
    // the floor is what keeps that usable
    expect(toleranceSec(90, 600)).toBe(10);
    // a zero-width canvas must not divide by zero
    expect(toleranceSec(3600, 0)).toBe(21600);
  });

  it("keeps only what happened at that time, newest first and capped", () => {
    const evs = [
      { id: "a", ts: 1000 },
      { id: "b", ts: 1005 },
      { id: "c", ts: 1030 },
      { id: "d", ts: 2000 },
    ];
    expect(eventsNear(evs, 1030, 30, 5).map((e) => e.id)).toEqual(["c", "b", "a"]);
    expect(eventsNear(evs, 1030, 30, 1).map((e) => e.id)).toEqual(["c"]);
    // a moment with nothing near it is nothing, not an implied calm stretch
    expect(eventsNear(evs, 1500, 30, 5)).toEqual([]);
  });

  it("does not mutate the event list it was given", () => {
    const evs = [{ id: "a", ts: 1000 }, { id: "b", ts: 1060 }];
    eventsNear(evs, 1030, 30, 5);
    expect(evs.map((e) => e.id)).toEqual(["a", "b"]);
  });

  it("hangs the readout under the pointer, never over the moment", () => {
    // the pointer's own height wins whenever there is one — including hard
    // against the top, where a 90/100 score would otherwise sit above it
    expect(tipY(41, 90, 150)).toBe(41);
    expect(tipY(2, 90, 150)).toBe(2);
    // and hard against the bottom it stays below rather than being clamped up
    expect(tipY(147, 10, 150)).toBe(147);
  });

  it("hangs it under the sample when the keyboard moved the cursor", () => {
    // no pointer to follow, so the readout tracks the sample's own height
    expect(tipY(null, 100, 150)).toBe(0);
    expect(tipY(null, 30, 150)).toBe(105);
    expect(tipY(null, 0, 150)).toBe(150);
  });
});
