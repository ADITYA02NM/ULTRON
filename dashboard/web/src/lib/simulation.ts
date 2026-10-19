// Client-side demo simulation — a paced script of synthetic envelopes that
// exercises every live panel (score/band/history, health, LAN, tripwire,
// suricata/wifi events, alerts + ACK, toasts, degraded banner) without any
// server or MQTT dependency. Pure frontend: injects straight into the store.
import type { Envelope, PayloadFor } from "../contracts/ws";
import { bandForScore } from "./bands";
import { execCommand } from "./commands";
import { store } from "../store/store";
import { transport } from "../transport/transport";

const CYCLE_MS = 92000;
const SCORE_TICK_MS = 1000;
const HEALTH_TICK_MS = 4000;

// Smart-home endpoints on the monitored LAN. Must stay in step with
// dashboard/tools/mock_feed.py LAN_DEVICES so the client-side simulation and
// the real MQTT demo feed paint the same topology.
const IOT_DEVICES = [
  { mac: "B0:4E:26:1A:2B:3C", ip: "192.168.100.61", vendor: "Hikvision", label: "IP camera" },
  { mac: "50:C7:BF:4D:5E:6F", ip: "192.168.100.62", vendor: "TP-Link", label: "Smart plug" },
  { mac: "24:6F:28:7A:8B:9C", ip: "192.168.100.63", vendor: "Espressif", label: "Door sensor" },
] as const;
const [CAMERA, PLUG, DOOR] = IOT_DEVICES;

interface Beat { at: number; run: (cycle: number) => void; }

export class Simulation {
  private running = false;
  private cycle = 0;
  private alertSeq = 0;
  private target = 10;
  private score = 0;
  private silence = false;
  private startedAt = 0;
  private beatTimers: number[] = [];
  private scoreTimer = 0;
  private healthTimer = 0;
  /** Suspended rather than finished: the beat timers are gone but the cycle
   *  position is kept, so resuming replays only what is left. */
  private paused = false;
  private pausedAt = 0;
  private cycleStartedAt = 0;

  isRunning(): boolean { return this.running; }

  private emit<T extends Envelope["t"]>(t: T, d: PayloadFor<T>): void {
    store.applyBatch([{ t, ts: Date.now() / 1000, d } as unknown as Envelope]);
  }

  private toast(msg: string, sev: string): void {
    this.emit("toast", { msg, sev });
  }

  private alert(sev: "info" | "yellow" | "red" | "purple", title: string, src: string, body: string): void {
    this.emit("alert", {
      id: `sim-${this.cycle}-${++this.alertSeq}`,
      sev, title, src, body,
      ts: Math.floor(Date.now() / 1000), ack: false,
    });
  }

  private cmd(raw: string): void { execCommand(raw); }

  /** Re-announce every smart-home endpoint — keeps lastSeen fresh so the
   *  topology never ages them out. */
  private lanAll(): void {
    for (const d of IOT_DEVICES) {
      this.emit("lan", { mac: d.mac, ip: d.ip, vendor: d.vendor, known: true });
    }
  }

  private clearTimers(): void {
    for (const id of this.beatTimers) window.clearTimeout(id);
    this.beatTimers = [];
    if (this.scoreTimer) window.clearInterval(this.scoreTimer);
    if (this.healthTimer) window.clearInterval(this.healthTimer);
    this.scoreTimer = 0;
    this.healthTimer = 0;
  }

  private scorePump = (): void => {
    const diff = this.target - this.score;
    if (diff !== 0) {
      const step = Math.sign(diff) * Math.min(Math.abs(diff), Math.max(2, Math.ceil(Math.abs(diff) / 6)));
      this.score = Math.max(0, Math.min(100, this.score + step));
      this.emit("score", { v: this.score });
      const band = bandForScore(this.score);
      if (band !== store.getState().band) this.emit("band", { b: band });
    }
  };

  private healthPump = (): void => {
    const up = Math.floor((Date.now() - this.startedAt) / 1000);
    const nodes = ["pi4", "pi3a", "pi3b", "esp32"];
    for (const node of nodes) {
      if (node === "pi3a" && this.silence) continue;
      this.emit("health", { node, up });
    }
  };

  private beats(): Beat[] {
    return [
      { at: 0, run: () => {
        this.toast("Watch started — narrating the home LAN", "info");
        this.cmd("/health");
        this.target = 8;
      } },

      // ── Phase A · every node and endpoint reports in, all healthy ────────
      { at: 1500, run: () => {
        this.emit("lan", { mac: "00:11:22:33:44:55", ip: "192.168.100.10", vendor: "TP-Link", known: true });
        this.alert("info", "Pi4 governance online", "health/pi4",
          "192.168.100.1 — mosquitto, risk engine and dashboard up. Watchdog armed.");
      } },
      { at: 3000, run: () => {
        this.emit("lan", { mac: CAMERA.mac, ip: CAMERA.ip, vendor: CAMERA.vendor, known: true });
        this.alert("info", `${CAMERA.label} checked in`, "detect/lan",
          `${CAMERA.vendor} ${CAMERA.ip} — 1080p stream healthy, RTSP 554 open, uptime 6 d.`);
      } },
      { at: 4500, run: () => {
        this.emit("lan", { mac: PLUG.mac, ip: PLUG.ip, vendor: PLUG.vendor, known: true });
        this.alert("info", `${PLUG.label} reported in`, "detect/lan",
          `${PLUG.vendor} ${PLUG.ip} — relay closed, drawing 11 W, Wi-Fi −54 dBm.`);
      } },
      { at: 6000, run: () => this.cmd(`/device ${PLUG.ip}`) },
      { at: 7500, run: () => {
        this.emit("lan", { mac: DOOR.mac, ip: DOOR.ip, vendor: DOOR.vendor, known: true });
        this.alert("info", `${DOOR.label} paired`, "detect/lan",
          `${DOOR.label} ${DOOR.ip} — front door contact, battery 92%, last event 3 h ago.`);
      } },
      { at: 9000, run: () => this.alert("info", "Detection node online", "health/pi3a",
        "192.168.100.2 — Suricata 26,140 signatures loaded, LAN observer on eth0. No drops.") },

      // ── Phase B · ordinary household activity, nothing wrong ─────────────
      { at: 12000, run: () => this.alert("info", "Front door opened", "detect/lan",
        `${DOOR.label} ${DOOR.ip} — contact opened, resident arriving home.`) },
      { at: 14500, run: () => this.cmd(`/device ${DOOR.ip}`) },
      { at: 17000, run: () => this.alert("info", "Front door closed", "detect/lan",
        `${DOOR.label} ${DOOR.ip} — contact closed after 5 s, battery unchanged at 92%.`) },
      { at: 19500, run: () => {
        this.target = 14;
        this.alert("info", `${PLUG.label} load changed`, "detect/lan",
          `${PLUG.label} ${PLUG.ip} — draw 11 W → 46 W, kettle switched on.`);
      } },
      { at: 22000, run: () => this.alert("info", `${CAMERA.label} stream healthy`, "detect/lan",
        `${CAMERA.label} ${CAMERA.ip} — 1080p @ 15 fps, 0 dropped frames this hour.`) },
      { at: 25000, run: () => {
        this.emit("lan", { mac: "AA:BB:CC:DD:EE:FF", ip: "192.168.100.57", vendor: "Apple", known: false });
        this.alert("info", "Unfamiliar device joined", "detect/lan",
          "AA:BB:CC:DD:EE:FF · 192.168.100.57 — first seen on the LAN, watching before trusting.");
      } },
      { at: 30000, run: () => {
        this.emit("lan", { mac: "AA:BB:CC:DD:EE:FF", ip: "192.168.100.57", vendor: "Apple", known: true });
        this.alert("info", "Unfamiliar device identified", "detect/lan",
          "AA:BB:CC:DD:EE:FF resolved to a household iPhone on the guest SSID — marked known.");
      } },

      // ── Phase C · the one real finding of the cycle ───────────────────────
      { at: 34000, run: () => {
        this.emit("event", { topic: "ultron/detect/suricata", node: "pi3a", kind: "suricata",
          sev: "yellow", summary: "ET SCAN default credential probe",
          src_ip: "192.168.100.57", dest_ip: CAMERA.ip, sig_id: 2010935 });
        this.alert("yellow", `${CAMERA.label} probed for default credentials`, "detect/suricata",
          `192.168.100.57 → ${CAMERA.ip} — 14 login attempts to the camera web UI in 30 s.`);
        this.target = 38;
      } },
      { at: 36000, run: () => this.toast("YELLOW — one finding under review", "yellow") },
      { at: 37500, run: () => this.cmd("/filter type:suricata") },
      { at: 39000, run: () => this.alert("info", "Probe rejected", "detect/suricata",
        `All 14 attempts failed — ${CAMERA.label} is not on default credentials. No access gained.`) },
      { at: 41000, run: () => this.alert("yellow", `${CAMERA.label} firmware is stale`, "detect/lan",
        `${CAMERA.vendor} ${CAMERA.ip} — firmware v5.6.2, 14 months old, 3 known CVEs unpatched.`) },
      { at: 43000, run: () => {
        const open = store.getState().alerts.find((a) => !a.ack);
        if (open) transport.sendAck(open.id);
      } },
      { at: 45000, run: () => {
        this.target = 10;
        this.toast("Finding acknowledged — decaying to GREEN", "info");
      } },

      // ── Phase D · close out the cycle, everything nominal ─────────────────
      { at: 47000, run: () => this.alert("info", "Pi3a heartbeat steady", "health/pi4",
        "Detection node reporting every 4 s, Suricata drop rate 0 %.") },
      { at: 51000, run: () => this.cmd("/clear-filter") },
      { at: 55000, run: () => this.lanAll() },
      { at: 59000, run: () => this.alert("info", "Indicator reading GREEN", "health/esp32",
        "ESP32-C3 OLED GREEN, LED steady — no operator action required.") },
      { at: 63000, run: () => this.cmd("/history 6h") },
      { at: 67000, run: () => this.alert("info", "All endpoints nominal", "health/pi4",
        "7/7 nodes healthy · 1 acknowledged advisory · 0 open critical. Watch continues.") },
      { at: 71000, run: () => this.cmd("/latency") },
      { at: 75000, run: () => {
        for (const a of store.getState().alerts) {
          if (!a.ack) transport.sendAck(a.id);
        }
      } },
      { at: 79000, run: () => this.lanAll() },
      { at: 83000, run: () => this.cmd("/focus") },
      { at: 87000, run: () => this.toast("Cycle complete — restarting watch", "info") },
      { at: 89000, run: () => this.cmd("/health") },
      { at: CYCLE_MS, run: (c) => {
        this.cycle = c + 1;
        this.alertSeq = 0;
        this.scheduleCycle();
      } },
    ];
  }

  private scheduleCycle(): void {
    this.scheduleFrom(0);
  }

  /** Arm every beat still ahead of `elapsed` ms into the current cycle. */
  private scheduleFrom(elapsed: number): void {
    // A cycle that ran out while we were away rolls over rather than leaving
    // the drill with nothing armed at all.
    if (elapsed >= CYCLE_MS) {
      this.cycle += 1;
      this.alertSeq = 0;
      elapsed = 0;
    }
    this.cycleStartedAt = Date.now() - elapsed;
    for (const b of this.beats()) {
      if (b.at <= elapsed) continue;
      this.beatTimers.push(window.setTimeout(() => {
        if (this.running && !this.paused) b.run(this.cycle);
      }, b.at - elapsed));
    }
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.cycle = 0;
    this.alertSeq = 0;
    this.target = 10;
    this.score = store.getState().score;
    this.silence = false;
    this.startedAt = Date.now();
    this.paused = false;
    store.setSimRunning(true);
    store.setSimPaused(false);
    this.healthPump();
    this.scorePump();
    this.scoreTimer = window.setInterval(this.scorePump, SCORE_TICK_MS);
    this.healthTimer = window.setInterval(this.healthPump, HEALTH_TICK_MS);
    this.scheduleCycle();
  }

  pause(): void {
    if (!this.running || this.paused) return;
    this.paused = true;
    this.pausedAt = Date.now();
    this.clearTimers();
    store.setSimPaused(true);
    this.toast("Simulation paused", "info");
  }

  resume(): void {
    if (!this.running || !this.paused) return;
    const away = Date.now() - this.pausedAt;
    this.paused = false;
    // The beat timers did not survive the pause, so start the cycle clock back
    // exactly `away` ms — otherwise a long pause would silently fast-forward
    // the drill and fire every missed beat at once.
    const elapsed = Math.max(0, Date.now() - away - this.cycleStartedAt);
    store.setSimPaused(false);
    this.healthPump();
    this.scorePump();
    this.scoreTimer = window.setInterval(this.scorePump, SCORE_TICK_MS);
    this.healthTimer = window.setInterval(this.healthPump, HEALTH_TICK_MS);
    this.scheduleFrom(elapsed);
    this.toast("Simulation resumed", "info");
  }

  stop(): void {
    if (!this.running) return;
    this.running = false;
    this.clearTimers();
    this.silence = false;
    this.paused = false;
    store.setSimRunning(false);
    store.setSimPaused(false);
    this.toast("Simulation stopped", "info");
  }

  toggle(): void {
    if (this.paused) this.resume();
    else if (this.running) this.pause();
    else this.start();
  }
}

export const simulation = new Simulation();
