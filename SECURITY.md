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

## Security boundaries

The threat model above says what we protect. This section says **where the
system stops** — the lines a reviewer should hold us to, and the ones that are
architectural rather than temporary.

### Trust zones

| Zone | What it is | Trusted for |
|------|-----------|-------------|
| **Operator** | The browser and the authenticator holding the passkey | Acting as the owner. The private key never leaves the device. |
| **Management network** | The link the dashboard is served over | Carrying operator sessions. TLS via the offline local CA in Phase 1. Anything on this network can reach the dashboard port. |
| **Monitored LAN** | The home/office network under observation | **Nothing.** It is observed, never trusted. The LAN watch is read-only. |
| **Sensor plane** | MQTT broker and the three nodes | Moving messages. Administered by ACL, not by hope. |
| **Physical** | The boxes, the USB evidence drive, the SD cards | Nothing. Hands on the hardware is game over for that hardware. |

### Component boundaries — the separation that is the point

No single node both **decides** and **records**. That split is why a compromise
of any one board is survivable.

| Component | Trusted for | If it is compromised |
|-----------|-------------|----------------------|
| **Pi4** — governance | Deciding: score, band, alerting | Total. It is the decision-maker, so it can report a false GREEN. This is the crown jewel and the highest-value target in the system. |
| **Pi3a** — detection | Observing: Suricata, LAN join watch, passive WiFi | It can lie — invent events or suppress them — but it **cannot rewrite history**. The vault belongs to Pi3b. |
| **Pi3b** — alert | Recording: the vault, SMTP, Markdown reports | It can falsify the record, but it cannot forge an operator session or move a score. |
| **Dashboard server** | Rendering, operator auth, and starting the sensor drill | It opens the vault **read-only**, so it cannot rewrite history. It can mint and revoke sessions, and it can launch the drill — which runs one script from a closed set (`demo` or `stress`) via `exec`, never a shell, so a client cannot influence the command line beyond those two names. |
| **MQTT broker** | Moving messages | It can drop or replay messages. Only Pi4 may write `risk/#` (ACL), so it cannot forge a score by publishing. |
| **ESP32-C3** — indicator | Showing the band on the OLED and LED | It can display a wrong band. Cosmetic: the dashboard is the source of truth. |
| **ESP32-WROOM** — tripwire | Reporting a physical event over GPIO/UART | It can raise a false tripwire. The event is weighted, not decisive. |

### What ULTRON does not defend against

Stated plainly, because "notify-only" has consequences people skip past:

- **It does not stop anything.** No blocking, quarantining or remediation in
  Phase 1. Detection latency is exposure time.
- **It does not inspect encrypted traffic.** A device exfiltrating data over
  HTTPS is invisible to it.
- **Passive WiFi does not decrypt.** It observes 802.11 frames; it cannot read
  the contents of WPA2/WPA3 traffic.
- **It does not harden the Pis themselves.** No secure boot, no measured boot,
  no encrypted root. Physical access to a board is compromise of that board.
- **It has no notion of "known good".** A new MAC is *unknown*, not *malicious*.
  The LAN watch reports arrivals; it does not authenticate devices.
- **The risk score is a heuristic.** False positives and false negatives are
  expected behaviour, not bugs. A clean scoreboard is not proof of safety.
- **The dashboard is not hardened for the open internet.** It is built for a
  management network. Do not port-forward it.
- **It does not sandbox its own outbound egress.** Once a mail relay or a push
  topic is configured, the alert node dials out on every band change and the
  content leaves the LAN. That is an operator-chosen egress, and it stays off
  until you configure it — with no `PUSH_TOPIC` set, the push channel dials
  nothing at all. The relay and the topic are part of your attack surface, not
  an implementation detail.

### Authorisation and legal boundary

ULTRON performs **passive wireless monitoring** and **LAN device discovery**.
This is a real boundary, not a formality:

- Run it only on networks **you own or have written authorisation to monitor**.
  Monitoring a third party's network may be unlawful where you are.
- It records MAC addresses and SSIDs, which are personal data under GDPR and
  comparable regimes. The evidence vault is a store of personal data and should
  be handled as one — retained, and deleted, deliberately.
- ULTRON captures no user payload by design. Keeping it that way is a feature;
  a change that starts capturing traffic content is a scope change that needs
  re-review.

### Residual risk we accept

| Risk | Why it is accepted |
|------|--------------------|
| Demo-rig escapes stay in the tree | They are load-bearing for the demo; documented below and reviewed on each release. |
| Detection is heuristic | A transparent, explainable score beats an opaque one that is wrong silently. |
| Notify-only | Response is a Phase 2 decision, taken deliberately rather than shipped half-built. |
| Physical access defeats the appliance | A shelf box in a house cannot win against an attacker holding the box. |

## Deliberate, documented posture (read before reporting)

Three behaviours are intentional and exist **only** for the laptop demo rig. If
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
