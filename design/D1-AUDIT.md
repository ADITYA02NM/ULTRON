# D1 — "Generic AI" Design Audit

## Before screenshots

| View | File |
|---|---|
| GREEN 1920×1080 | `before/green-1920x1080.jpg` |
| RED 1920×1080 | `before/red-1920x1080.jpg` |
| RED 1280×720 | `before/red-1280x720.jpg` |
| RED 1024px | `before/red-1024px.jpg` |
| Lock screen | `before/lock-screen-1920x1080.jpg` |
| Booth RED | `before/booth-red-1920x1080.jpg` |

---

## Audit table

| # | Tell | Severity | Where (file/component) | Evidence | One-line fix |
|---|---|---|---|---|---|
| 1 | **Tailwind-default signal colours** — `#22c55e` (green-500), `#ef4444` (red-500), `#eab308` (yellow-500), `#a855f7` (purple-500) used verbatim | HIGH | `tokens.css:13-16`, `bands.ts`, `History.tsx:5`, banner SVG | Every band colour is an unmodified Tailwind palette stop — instantly recognisable as AI/framework output | Design custom band ramps with near-equal perceived lightness; define in OKLCH |
| 2 | **Tailwind-default background palette** — `#0a0e14` (slate-950-ish), `#111823` (slate-900-ish), `#0d141d`, `#1e2a3a` (slate-800) | HIGH | `tokens.css:5-8` | The dark backgrounds are the stock "dark AI dashboard" palette | Choose a distinctive base: warmer charcoal, cooler graphite, or true black per direction |
| 3 | **`system-ui` as sole voice** — one font family for everything, no deliberate type scale | HIGH | `tokens.css:24-25`, all components | `system-ui` sans + `ui-monospace` with zero intentional hierarchy; body, labels, titles, numerals all the same weight | Self-host a deliberate font pairing with modular scale and distinct roles |
| 4 | **Bento monotony** — all 6 panels have identical padding (14px→10px), radius (6px), border (1px solid var(--border)), and `.label` title treatment | HIGH | `global.css:22-32`, `ops-grid > .panel` | Every panel reads as a clone; no hierarchy across Scoring (hero) vs Events (dense) vs IoT (spatial) | Give each panel distinct density and emphasis; Scoring gets hero treatment |
| 5 | **Uppercase letter-spaced labels on everything** — `.label` with `text-transform: uppercase; letter-spacing: 0.08em` used for ALL panel titles, stat labels, command output headers, node legend | MED | `global.css:15-18` | "SCORING", "COMMAND CONSOLE", "MY DEVICE MAP", "EVENTS HAPPENING", "QUICK CONTROLS", "EXTERNAL IoT ARCHITECTURE", "COMMAND OUTPUT", "REGISTERED DEVICES" — uppercase everywhere = no hierarchy | Uppercase for ONE role only (e.g. node badges); panel titles quiet |
| 6 | **Off-scale spacing values** — 13px, 15px, 11px, 18px, 14px, 10px, 26px scattered across component CSS | MED | `global.css` throughout (font-size: 13px body, 11px labels, 22px stats, 10px chips, etc.) | No coherent spatial system; sizes appear arbitrary | Adopt 8px base grid with 4px half-step; all spacing from tokens |
| 7 | **Glows with no meaning** — `box-shadow: 0 0 7px` on the LIVE/STALE/OFFLINE LED, `0 0 6px` on lit layer cubes, node status dots, LED dots, all using the same glow effect | MED | `global.css:51-53` (.chip LEDs), `:233-234` (layers), `:342` (LED dots), `:353-355` (node status) | The green glow on a "known device" has the same visual weight as the glow on a critical alert. Signal is diluted. | Glow only on actively-signalling elements; one token; disabled under reduced motion |
| 8 | **Generic copy** — "SCORING", "MY DEVICE MAP", "EVENTS HAPPENING", "QUICK CONTROLS", "EXTERNAL IoT ARCHITECTURE", "OWNER SETUP" | MED | Panel titles in `OperatorView.tsx`, `AuthGate.tsx` | Generic dashboard language; "EVENTS HAPPENING" reads like a marketing template | Precise operator voice: "Risk", "Hardware", "Events", "Commands", "IoT topology" |
| 9 | **Numbers not tabular in practice** — `.num { font-variant-numeric: tabular-nums }` declared but many numeric displays use `system-ui` without the `.num` class; inconsistent unit presentation | MED | `global.css:14`, `RiskPanel.tsx` (numeral is system-ui bold), `StatsStrip.tsx`, `PipelineStrip.tsx` | Score "72" and "/100" render in system-ui, not a true mono; "41ms" has no unit separation; "p95 63ms" inconsistent | All updating numerals get `tabular-nums slashed-zero`; units smaller and muted |
| 10 | **Inconsistent timestamp formats** — `HH:MM:SS UTC` in some places, `HH:MM:SS` without UTC in others, ISO-ish in command output | LOW | `format.ts` (utcTime adds " UTC"), event feed, command output timestamps | `09:39:11 UTC` in events but `09:38:24` in command output; footer says `09:06:23 UTC` | One format everywhere: `HH:MM:SS` with UTC stated once in the header |
| 11 | **Muted text failing WCAG AA** — `--muted: #7a8b9f` on `--bg: #0a0e14` = ~3.6:1 contrast ratio; `--muted-2: #4a5a6e` = ~2.1:1 | HIGH | `tokens.css:9-10`, used by `.label`, `.posture`, `.meta`, `.lval`, `.tm`, `.src`, footer, status strip | Body-sized muted text is below 4.5:1 AA threshold. `--muted-2` fails even 3:1 for large text. | Bump muted to ≥4.5:1; add automated contrast test |
| 12 | **Default focus rings** — no custom `:focus-visible` anywhere; uses browser default blue outline | MED | No `:focus-visible` in `global.css` | Tab navigation shows stock blue Chrome focus ring, jarring against the dark theme | Custom focus rings from accent tokens; visible in all components |
| 13 | **Default scrollbars** — only `.ops-grid > .panel::-webkit-scrollbar` has thin styling; the rest use browser defaults | LOW | `global.css:99-101` | Event feed, alert feed, command output use stock scrollbars | Token-coloured thin scrollbars on all scrollable areas |
| 14 | **Undesigned empty states** — "No alerts — all quiet in the sensor mesh" is plain centered muted text; no visual anchor | LOW | `AlertFeed.tsx:47`, `EventFeed.tsx:73`, `IoTGraph.tsx:81` | Empty states are indistinguishable from each other; no illustration or meaningful layout | Design calm, operator-appropriate empty states with contextual information |
| 15 | **Decorative `::selection` unstylked** — no custom selection colour | LOW | Not present in any CSS | Text selection uses Chrome's default blue highlight, clashing with the dark palette | Set `::selection` to accent-weak |
| 16 | **Pills and badges overused** — GREEN/YELLOW/RED/PURPLE pill in header, "notify only — response is Phase 2" in its own bordered pill, severity bars, node badges all compete | MED | `Header.tsx` (`.pill`), `RiskPanel.tsx` (`.note`), `EventFeed.tsx` (`.ev-node`) | 4+ distinct badge/pill styles within view; no visual hierarchy among them | Reduce to 2 badge styles max; severity via shape not just colour |
| 17 | **Severity relies on colour alone** — event severity bars (`.ev-bar`) and alert bars (`.bar`) use only colour to distinguish red/yellow/green/purple | HIGH | `global.css:174-177` (alert bars), `:209-213` (event bars) | Colour-blind users cannot distinguish severity levels from the bars alone | Pair colour with distinct icon shapes (circle/triangle/octagon/diamond) |
| 18 | **Motion that doesn't signal** — the cursor blink on the LIVE chip (`.cursor`) animates constantly; LED dots animate chase/strobe/pulse purely decoratively | LOW | `Header.tsx:48` (.cursor), `IndicatorTwin.tsx:56-68` | The cursor blink is visual noise; LED animations are entertaining but carry no information the dashboard doesn't already show | Cursor: still or remove. LED patterns: match hardware but respect reduced-motion more strictly |
| 19 | **Panel grid pattern is decorative noise** — `repeating-linear-gradient` creating an 8px grid pattern on every panel background | LOW | `global.css:23-26` | Adds visual texture but no information; competes with real data | Remove or reduce to barely visible; the grid shouldn't compete with content |
| 20 | **Node tile legend has mismatched density** — the compact node tiles (pi4/pi3a/pi3b/esp32) use different font sizes, spacing and badge styles from the main event feed | LOW | `NodeTiles.tsx`, `global.css:360-367` | Mini tiles are a different design language from event rows and quick control buttons | Unify component micro-spacing from the same token scale |
| 21 | **Auth/lock screen is minimal** — centred card on empty dark background; no visual identity, no trust signals, no hardware reference | MED | `AuthGate.tsx`, `global.css:393-438` | The first thing a Black Hat visitor sees is an empty dark screen with a small card. No brand presence, no differentiation from a generic login. | Hero composition: wordmark treatment, hardware twin art, trust signals, passkey action |
| 22 | **`data-band` colour swap is all-or-nothing** — switching from GREEN to RED replaces every accent instance simultaneously; no ramp granularity | MED | `tokens.css:29-32` | Band colours have one stop each; no tint/soft/base/strong variants. A RED accent applied to both a subtle tint background and a bold badge uses the same hex. | 4-step ramp per band: tint (bg), soft (border), base (text/icon), strong (emphasis) |
| 23 | **Footer with redundant static info** — the booth-view footer (`Footer.tsx`) lists MQTT address, evidence DB path, node IP — duplicating the status strip | LOW | `Footer.tsx:8-12` | Static config repeated in two places; valuable screen space wasted | Consolidate into a single minimal status strip |

---

## Summary

**Critical (HIGH):** 5 items — Tailwind-default colours (1,2), system-ui typography (3), flat panel hierarchy (4), WCAG contrast failure (11), colour-only severity (17).

**Medium:** 9 items — uppercase everywhere (5), off-scale spacing (6), meaningless glows (7), generic copy (8), inconsistent numbers (9), no focus rings (12), badge overuse (16), bare auth screen (21), flat band ramp (22).

**Low:** 9 items — timestamps (10), scrollbars (13), empty states (14), selection colour (15), decorative motion (18), panel grid noise (19), node legend density (20), footer duplication (23).

The dashboard is functionally solid, but its visual language is the default output of an LLM using Tailwind conventions: every colour, font choice, spacing value, and component treatment is the path of least resistance. A design-literate visitor at Black Hat will recognise these tells in seconds.
