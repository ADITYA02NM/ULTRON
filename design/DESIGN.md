# ULTRON — Design System (Intelligence Brief)

## Mood statement

A classified intelligence briefing viewed after hours: editorial gravity, warm restraint, nothing decorative. Every element earns its ink. The dashboard reads like a Financial Times data page redesigned for an air-gapped SCIF terminal — serious, warm, quietly confident.

## References

1. **Financial Times data journalism** — warm off-black backgrounds, Financier Display serif for headlines, metric sans for body, restrained signal colour.
2. **The Economist Intelligence Unit** — dense, information-first layouts, serif headlines above sans body, muted palette with a single accent.
3. **NSA declassified document covers** — all-caps classification banners, monospaced metadata, institutional typography over decoration.

## Type roles

| Role | Font | Weight | Size | Use |
|---|---|---|---|---|
| display | Newsreader | 700 | 64px | Risk score numeral |
| title | Newsreader | 400 / 700 | 14–16px | Panel labels, band name, wordmark |
| posture | Newsreader italic | 400 | 12–13px | Posture description, auth subtitle |
| body | Schibsted Grotesk* | 400–500 | 13–14px | Event summaries, descriptions, UI text |
| label | Schibsted Grotesk* | 500–600 | 10–11px | Uppercase labels, chip text, node badges |
| data-lg | JetBrains Mono | 700 | 20–22px | Stat values, latency numbers |
| data | JetBrains Mono | 400 | 11–13px | Timestamps, IPs, MACs, command output |
| data-sm | JetBrains Mono | 400 | 9–10px | Event kind labels, auth nodes, small data |
| caption | Schibsted Grotesk* | 400 | 10px | Help text, Phase 2 note |

*Pending user confirmation; IBM Plex Sans is the alternative.

All fonts use `font-variant-numeric: tabular-nums slashed-zero` on updating numerals. Newsreader confirmed to have true tabular figures (no jitter 9→10→99).

## Font files

Built by `scripts/build-fonts.py` into `src/assets/fonts/` (same-origin, `font-src 'self'`), subset to Basic Latin + Latin-1 + the UI's symbols (— · → ± × … −).

| File | Axes | Size |
|---|---|---|
| newsreader-400 / -700 | static (opsz pinned 18) | 18.3 / 19.5 KB |
| newsreader-italic-400 | static | 20.0 KB |
| schibsted-grotesk-var | wght 400–700 | 32.9 KB |
| jetbrains-mono-var | wght 400–700, ASCII + symbols | 22.5 KB |
| **production total** | | **113.2 KB** |

`fonts.css` also defines metric-matched fallbacks (`size-adjust`, `ascent-override`, `descent-override`, `line-gap-override`) on Times New Roman / Arial / Courier New and their Liberation equivalents, so the swap causes no layout shift.

## Colour system: 60-30-10

| Share | Role | Tokens |
|---|---|---|
| 60% | Surfaces | `--bg` (#100e0c), `--panel` (#1a1714), `--panel-2` (#14120f) |
| 30% | Structure | `--text` (#ddd4c8), `--muted` (#9a8e80), `--border` (#2a2420), `--border-2` (#352e28) |
| 10% | Signal | `--accent` (current band base), `--accent-weak` (tint), `--accent-line` (soft) |

Band signal ramps use 4 stops: tint (8–10% opacity bg), soft (30% border/highlight), base (text/icon), strong (emphasis).

| Band | Tint | Soft | Base | Strong |
|---|---|---|---|---|
| GREEN | rgba(58,200,112,.08) | rgba(58,200,112,.30) | #3ac870 | #28a858 |
| YELLOW | rgba(212,176,48,.08) | rgba(212,176,48,.30) | #d4b030 | #b89820 |
| RED | rgba(208,72,56,.10) | rgba(208,72,56,.30) | #d04838 | #b83020 |
| PURPLE | rgba(160,96,208,.10) | rgba(160,96,208,.30) | #a060d0 | #8040b0 |

All colours live in `tokens.css`: sRGB hex fallbacks in `:root`, overridden by `oklch()` values inside `@supports (color: oklch(0 0 0))`. Canvas components read them through `src/lib/cssVars.ts`, cached per band.

## Spacing scale

4px half-step, 8px base grid. No off-grid values in component CSS.

| Token | Value |
|---|---|
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 24px |
| `--space-6` | 32px |
| `--gap` | 12px |

## Radius

`--radius: 3px` — one value. Rounded corners are structural, not decorative. The OLED canvas uses `border-radius: 2px` as the single exception (matching the hardware bezel).

## Motion tokens and rules

| Token | Value | Use |
|---|---|---|
| `--dur` | 200ms | Default transition duration |
| `--ease` | cubic-bezier(0.22, 0.61, 0.36, 1) | Ease-out for UI transitions |

Rules:
- Motion signals state change, never decoration.
- Escalation sweep (header) fires once per band change, not continuously.
- LED animations mirror the physical hardware; respect `prefers-reduced-motion`.
- `@media (prefers-reduced-motion: reduce)` disables all animation and transition via `* { animation: none !important; transition: none !important; }`.
- Score numeral animates with 300ms ease-out; skipped under reduced motion.
- Cursor blink is a static 1px line at 60% opacity — no animation.

## Icon rules

- No emoji. No icon library (no Lucide, no FontAwesome, no Material).
- Custom inline SVGs in `src/components/Icons.tsx`: 16×16 grid, 1.5 stroke, round caps/joins, `currentColor`. Rendered at `--icon-size` (14px).
- Two families, never mixed: **stroked** outline = event kind, **filled** solid = severity.
- Event kind icons:
  - alert: bell
  - suricata (IDS): shield with check
  - wifi: radio arcs
  - lan: three linked nodes
  - tripwire: lid lifting off a box (mirrors the physical case tripwire)
  - band change: ascending steps
- Severity glyphs (at `--icon-size-sm`, 10px): info/green = circle, warn/yellow = triangle, red/critical = square, purple = diamond. The silhouettes stay distinct in a grayscale screenshot. The severity bar's width (3/4/4/5px) and corners are a secondary cue.
- Each icon carries `<title>` (hover) and `aria-label` (screen readers) with the kind or severity name.

## Signature element

The hero scoring panel: accent-coloured 2px top border, gradient tint from `--accent-weak` fading to `--panel` over 80px. The serif numeral (Newsreader 64px 700) animating with ease-out is the dashboard's visual anchor — the one element a visitor remembers. All other panels are subordinate: same `--panel` background, same 1px border, no gradient.
