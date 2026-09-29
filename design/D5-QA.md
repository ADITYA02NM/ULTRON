# D5 — QA and proof

Direction: **B — Intelligence Brief**. Body font: Schibsted Grotesk (IBM Plex Sans stays available in the dev-only specimen). Panel titles: the quiet set (Risk / Console / Hardware / Events / Controls / IoT Topology). Both were left as defaults; swapping either is a one-line change.

## Screenshots

| What | File |
|---|---|
| Operator, 4 bands @ 1920×1080 | `after/d5-{green,yellow,red,purple}-1920x1080.png` |
| Operator RED @ 1280×720 | `after/d5-red-1280x720.png` |
| Operator RED @ 1024 (stacked, full content height) | `after/d5-red-1024.png` |
| Per-panel before/after (RED) | `after/d3-panels/<panel>-{before,after}.png` |
| Booth @ 1920×1080 | `after/d5-booth-red-1920x1080.png` (+ `-25pct.png` legibility check) |
| Lock screen: TV / laptop / phone | `after/d5-lock-{1920x1080,1366x768,390x844}.png` |
| Severity in grayscale | `after/d5-events-grayscale.png` |
| Before (D1) | `before/*` (captured at 1568×744) |

## D1 audit re-check

| # | Tell | Status | Evidence |
|---|---|---|---|
| 1 | Tailwind signal colours | fixed | custom 4-step band ramps in `tokens.css`, oklch + sRGB fallback |
| 2 | Tailwind background palette | fixed | warm charcoal `--bg/--panel/--panel-2` |
| 3 | `system-ui` as sole voice | fixed | Newsreader / Schibsted Grotesk / JetBrains Mono, self-hosted subsets, `DESIGN.md` type roles |
| 4 | Bento monotony | fixed | Risk panel is the only hero (accent top border, tint, serif numeral) — `d5-red-1920x1080.png` |
| 5 | Uppercase everywhere | fixed | uppercase limited to panel labels, chips and buttons; titles, body, posture are sentence case |
| 6 | Off-scale spacing | fixed | 0 raw px outside tokens (`npm run check:tokens`), spacing on 4/8px grid |
| 7 | Glows with no meaning | fixed | glow only on the LIVE LED, hot pipeline stage and lit LED strip, one `--glow-blur` token |
| 8 | Generic copy | fixed | panel titles, empty states and banner rewritten in operator voice |
| 9 | Numbers not tabular | fixed | all numerals `tabular-nums slashed-zero`; Newsreader digits measured equal width (no 9→10→99 jitter); units set muted |
| 10 | Inconsistent timestamps | fixed | `HH:MM:SS UTC` everywhere (event feed, stamps, clock) |
| 11 | Muted text fails AA | fixed | `tests/contrast.test.ts` 17/17 across 4 bands |
| 12 | Default focus rings | fixed | `:focus-visible` accent ring; 28/28 enabled controls show visible focus |
| 13 | Default scrollbars | fixed | thin token scrollbars on every scroller |
| 14 | Undesigned empty states | fixed | dashed-border serif-italic empty states with specific copy |
| 15 | Unstyled selection | fixed | `--selection-bg` |
| 16 | Pills overused | fixed | band pill outline-only; Phase-2 note is plain mono text; node badge is neutral (no severity colours) |
| 17 | Severity by colour only | fixed | filled shapes circle/triangle/square/diamond + bar width — `d5-events-grayscale.png` |
| 18 | Motion that doesn't signal | fixed | cursor is a static 1px mark; all ambient motion stops under reduced motion (verified) |
| 19 | Panel grid noise | fixed | removed |
| 20 | Node legend density | fixed | legend uses the shared token scale and a state word (`up / stale / down / no data`) |
| 21 | Minimal auth screen | fixed | asymmetric lock-screen hero: wordmark, subhead, one action, trust signals, idle shelf drawing |
| 22 | All-or-nothing band swap | fixed | tint / soft / base / strong per band |
| 23 | Footer duplication | fixed in operator view | operator view uses only the status strip; the legacy `Footer` component is no longer rendered |

## Checklist

- [x] **Contrast:** 17/17 in all 4 bands (`tests/contrast.test.ts`).
- [x] **Severity in grayscale:** shape carries severity without colour.
- [x] **Tokens:** `npm run check:tokens` → hex 0 · rgb 0 · px 0 · ms 0. Exceptions: 0/1px/2px; the OLED canvas geometry (physical SSD1306 pixels); SVG viewBox units; `@media` breakpoints (custom properties are invalid there).
- [x] **Fonts:** 113.2 KB woff2 total, same-origin (`default-src 'self'` covers `font-src`), metric-matched fallbacks. **CLS on load = 0** (layout-shift observer, lock screen, fonts loaded).
- [x] **Bundle:** JS + CSS gzip — before (first D2 build) 61.85 + 8.70 = 70.6 KB; after 63.14 + 0.83 + 7.34 = **71.3 KB** (budget 150 KB).
- [x] **Lock screen:** no live data before auth (no score, band, times or counts in the DOM; the shelf drawing has no status), one action, CLS 0; phone 390×844 keeps the full-width unlock button above the fold with no horizontal scroll.
- [x] **Booth:** fits 1920×1080 with no clipped panels; `d5-booth-red-25pct.png` stays legible for numeral, band, posture, pipeline and alert titles.
- [x] **Performance (in-browser, 900 envelopes, 300 frames of 1–5):** handler p50 0.07 ms / **p95 0.15 ms** (< 8 ms); envelope stamp → post-paint p50 23 ms / **p95 30 ms** (< 100 ms). Measured through the same `applyBatch` → rAF → paint path as `transport.ts`. **Not measured:** the Mosquitto → server → WS hop (no broker on this machine).
- [x] **No page scroll** at 1920×1080 or 1280×720; 1024 px stacks to two columns with no horizontal scroll and no clipped panels.
- [x] **Reduced motion:** with `prefers-reduced-motion: reduce`, `document.getAnimations()` has no running animations and the LED strip stays solid.
- [x] **Keyboard:** 28 enabled controls reachable (including IoT device nodes, now `role=button`), all with visible focus; disabled Phase-2 chips are skipped by design.
- [x] **Tests:** web 31/31 (the stale suricata/wifi test now uses the CP5 `t:"event"` contract); server 39/39 incl. the new WS refusal suite and CSP tests.
- [x] **External requests:** none (resource timing lists only same-origin hosts).
- [ ] **Git tag `design-v2`:** not created — the project directory is not a git repository.
