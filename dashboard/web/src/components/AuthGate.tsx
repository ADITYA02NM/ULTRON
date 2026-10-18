import { useEffect, useState } from "react";
import { useStore, store } from "../store/store";
import { BootMark } from "./BootMark";
import { HardwareTwin } from "./HardwareTwin";
import {
  checkAuth, setupBegin, setupComplete,
  loginBegin, loginComplete, demoLogin, skipRegistration,
} from "../lib/auth";

// Static facts only: nothing on the lock screen may reflect live data before auth.
const TRUST = ["Zero cloud", "Owner-only passkey", "~$290 · ~38 W", "Event → screen < 100 ms", "Phase 1: notify-only"];

// Remembers "this browser skipped sign-in", so it does not ask again.
const SKIP_KEY = "ultron_skip_auth";

// How long the startup mark stays on screen before the session check takes over.
// A local check answers in a few milliseconds, which would flash it for a single
// frame; set to 0 to remove the hold entirely.
const BOOT_HOLD = 900;

/** Every successful sign-in path funnels through here: wipe anything left over
 *  from a previous session, then open the dashboard. */
function signedIn(): void {
  store.reset();
  store.setAuth(true, true);
}

function AuthLayout({ children }: { children: React.ReactNode }) {
  const [skipBusy, setSkipBusy] = useState(false);

  async function handleSkip() {
    if (skipBusy) return;
    setSkipBusy(true);
    try {
      localStorage.setItem(SKIP_KEY, "true");
      await skipRegistration();
    } catch (e) {
      console.warn("Skip call failed, falling back to local demo state:", e);
    } finally {
      signedIn();
      setSkipBusy(false);
    }
  }

  return (
    <main className="auth-screen">
      <button
        className="auth-skip-corner"
        onClick={handleSkip}
        disabled={skipBusy}
        type="button"
        aria-label="Skip registration"
        title="Skip registration"
      >
        {skipBusy ? "…" : "skip"}
      </button>
      <section className="auth-hero">
        <h1 className="auth-logo">ULT<b>RON</b></h1>
        <p className="auth-subtitle">Detect → govern → alert for the smart-home IoT layer. Zero cloud.</p>
        <div className="auth-action">{children}</div>
        <ul className="auth-trust">
          {TRUST.map((t) => <li key={t}>{t}</li>)}
        </ul>
      </section>
      <aside className="auth-visual" aria-hidden="true">
        <HardwareTwin idle />
        <span className="auth-visual-cap">Pi4 · Pi3a · Pi3b · ESP32-C3 · ESP32-WROOM — one shelf, one switch</span>
      </aside>
    </main>
  );
}

function SetupScreen({ onDone }: { onDone?: () => void }) {
  const urlToken = new URLSearchParams(location.search).get("t") ?? "";
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSetup() {
    setBusy(true);
    setStatus("Requesting registration…");
    try {
      // The QR link carries ?t=<token>. Opened straight from this machine the
      // server accepts a tokenless first-owner registration, so the button
      // below just works either way.
      const options = await setupBegin(urlToken.trim());
      options.challenge = b64ToBuf(options.challenge as unknown as string);
      (options as any).user.id = b64ToBuf((options as any).user.id);
      if ((options as any).excludeCredentials) {
        for (const c of (options as any).excludeCredentials) c.id = b64ToBuf(c.id);
      }
      setStatus("Choose your passkey device — on a laptop you can pick “Use a phone” and scan the QR…");
      const cred = await navigator.credentials.create({ publicKey: options });
      if (!cred) { setStatus("Registration cancelled"); setBusy(false); return; }
      setStatus("Verifying…");
      await setupComplete(cred);
      onDone?.();
      signedIn();
    } catch (e: any) {
      setStatus(e.message || "Registration failed");
      setBusy(false);
    }
  }

  return (
    <AuthLayout>
      <h2 className="auth-title">Register your passkey</h2>
      <p className="auth-hint">
        Create the owner passkey for this dashboard. On a laptop you can choose
        “Use a phone” and scan the QR, then approve with your fingerprint.
      </p>
      <button className="auth-btn" onClick={handleSetup} disabled={busy} autoFocus>
        Register your passkey
      </button>
      {status && <div className="auth-status" role="status">{status}</div>}
    </AuthLayout>
  );
}

function LoginScreen() {
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState("");
  const [codeBusy, setCodeBusy] = useState(false);

  async function handleLogin() {
    setBusy(true);
    setStatus("Starting authentication...");
    try {
      const options = await loginBegin();
      setStatus("Touch your authenticator...");
      const cred = await navigator.credentials.get({ publicKey: options });
      if (!cred) { setStatus("Authentication cancelled"); setBusy(false); return; }
      setStatus("Verifying...");
      await loginComplete(cred);
      signedIn();
    } catch (e: any) {
      setStatus(e.message || "Authentication failed");
      setBusy(false);
    }
  }

  async function handleDemo() {
    if (!code.trim()) { setStatus("Enter the LAN access code"); return; }
    setCodeBusy(true);
    setStatus("Checking access code…");
    try {
      await demoLogin(code.trim());
      signedIn();
      setStatus("");
    } catch (e: any) {
      setStatus(e.message || "Access code rejected");
    } finally {
      setCodeBusy(false);
    }
  }

  return (
    <AuthLayout>
      <button className="auth-btn" onClick={handleLogin} disabled={busy} autoFocus>
        Unlock with passkey
      </button>
      {status && <div className="auth-status" role="status">{status}</div>}
      <div className="auth-demo">
        <span className="auth-hint">Demo rig on the LAN?</span>
        <input
          className="auth-code"
          type="password"
          value={code}
          placeholder="access code"
          autoComplete="off"
          aria-label="LAN demo access code"
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleDemo(); }}
        />
        <button className="auth-btn auth-btn-ghost" onClick={handleDemo} disabled={codeBusy}>
          Unlock
        </button>
      </div>
    </AuthLayout>
  );
}

function CheckingScreen() {
  return (
    <AuthLayout>
      <BootMark />
      <div className="auth-status" role="status">Checking session…</div>
    </AuthLayout>
  );
}

export function AuthGate({ children }: { children?: React.ReactNode }) {
  const phase = useStore((s) => s.authPhase);
  // A `?t=<enrollment token>` in the URL always wins — that is how the QR code
  // hands over a passkey even when an owner is already registered.
  const [pendingToken, setPendingToken] = useState(() =>
    Boolean(new URLSearchParams(location.search).get("t"))
  );
  const [booted, setBooted] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(() => setBooted(true), BOOT_HOLD);
    return () => window.clearTimeout(t);
  }, []);

  useEffect(() => {
    const trySkip = async (): Promise<boolean> => {
      try {
        await skipRegistration();
        signedIn();
        return true;
      } catch {
        localStorage.removeItem(SKIP_KEY);
        return false;
      }
    };

    checkAuth()
      .then(async (s) => {
        if (!s.authenticated && localStorage.getItem(SKIP_KEY) === "true") {
          if (await trySkip()) return;
        }
        store.setAuth(s.authenticated, s.has_owner);
      })
      .catch(async () => {
        if (localStorage.getItem(SKIP_KEY) === "true") {
          if (await trySkip()) return;
        }
        store.setAuth(false, false);
      });
  }, []);

  const finishSetup = () => {
    history.replaceState(null, "", location.pathname);
    setPendingToken(false);
  };

  if (!booted || phase === "checking") return <CheckingScreen />;
  if (pendingToken) return <SetupScreen onDone={finishSetup} />;
  if (phase === "setup") return <SetupScreen />;
  if (phase === "login") return <LoginScreen />;
  return <>{children}</>;
}

function b64ToBuf(b64: string): ArrayBuffer {
  const s = b64.replace(/-/g, "+").replace(/_/g, "/");
  const pad = s.length % 4 === 0 ? "" : "=".repeat(4 - (s.length % 4));
  const raw = atob(s + pad);
  const buf = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i);
  return buf.buffer;
}
