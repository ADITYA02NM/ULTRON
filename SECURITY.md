# Security Policy

## Scope

ULTRON is a Phase 1 **notify-only** IoT monitoring appliance. It detects, scores
and alerts. It does not block, quarantine or remediate — response is Phase 2.
Please report issues on that basis.

## Supported versions

| Version | Supported |
|---------|-----------|
| `master` | ✅ |
| `0.5.0-phase1` | ✅ |
| anything older | ❌ |

## Reporting a vulnerability

Open a [private security advisory](https://github.com/ADITYA02NM/ULTRON/security/advisories/new)
rather than a public issue. Please include a reproduction, the affected
version (`/healthz` reports it) and the impact you believe it has.

Expect an acknowledgement within a few days. This is a small project, not a
staffed programme.

## Threat model

The appliance is expected to sit on a **management network**, not the open
internet. Sessions are bearer cookies over the management link; the Phase 1
deployment terminates TLS with an offline local CA (`tools/make_local_ca.sh`).

Assets worth protecting, in order:

1. **The evidence vault** — the SQLite alert/scores history. The dashboard
   server opens it **read-only** (`file:…?mode=ro`) and never writes; only the
   Pi3b alert node appends. A compromise of the dashboard must not be able to
   rewrite history.
2. **Operator identity** — WebAuthn passkeys. Credentials are stored as public
   keys only; private keys never leave the authenticator.
3. **The risk score** — a forged score is a forged sense of safety.

## Deliberate, documented posture (read before reporting)

Two behaviours are intentional and exist **only** for the laptop demo rig. If
you deploy this beyond a rehearsal, gate them off.

- **`POST /auth/skip`** mints an authenticated session **with no credential at
  all**. It exists so a presenter can open the dashboard without a passkey. If
  the port is reachable, so is the dashboard. Not gated by any flag today —
  treat it as a known exposure and remove or feature-flag it before any real
  deployment.
- **`POST /auth/demo`** exchanges a shared LAN access code (env
  `ULTRON_DEMO_CODE`) for a session, so a phone on the Wi-Fi can sign in even
  though passkeys are pinned to `localhost`. The code is stable across restarts
  and is printed by the launcher; it is a shared secret, not an identity.
- **`ULTRON_ALLOW_LAN=1`** permits non-loopback `http://` origins. Plain HTTP
  on a LAN is interceptable — the demo accepts that; production uses TLS.

Token-free first-owner setup (`POST /auth/setup` with no token) is **not** part
of this list: it is accepted only when the request arrives from loopback *and*
no owner exists, so ownership cannot be claimed across the network.

## What ULTRON trusts, and why that matters

This is a security tool that consumes untrusted input by definition. Every
string in the system — SSIDs, vendor names, MAC addresses, Suricata signature
text, alert bodies — is **attacker-controlled**, because a hostile device
chooses them. Treat the UI as a rendering surface for hostile text:

- escape on render (the dashboard does not use `dangerouslySetInnerHTML`)
- never interpolate device-supplied text into a shell, a query, or a prompt
- if you add the planned AI assistant, fence untrusted fields away from the
  system prompt and treat model output as a suggestion, not a command

## Dependencies

Pinned in `dashboard/server/requirements.txt` and
`dashboard/web/package.json`. CI runs the full suite on every push so a
breaking bump fails loudly rather than silently.
