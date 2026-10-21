# Phase 14 — Frontend redesign: design system, every page, pixel-level QA

## Goal
Replace the Phase 10 look with a **professional, cohesive product design** that feels like it was
made by a small, careful design team. Clean and calm like apple.com, dense and scannable like
trendshift.io, and formatted flawlessly at every screen width in light and dark mode.

This phase owns **all visual design and front-end formatting** for every page of the site,
including pages added in Phases 11–13. Data generation (`breakout publish site-data`) does not change
except where this phase asks for an extra field (§7.11).

When this phase is done, nobody should be able to tell the site was generated. Every number is
formatted, every row aligns to the grid, nothing overflows, dark mode is as polished as light, and
the layout holds from 360 px phones to 1920 px monitors.

## Prerequisites
- Phase 10 done (site builds and deploys). Phases 11–13 may be done or not; if a page from those phases
  does not exist yet, build its **layout** here using fixture data, so it is ready when the data arrives.
- Node.js LTS installed; `site/` builds with `npm run build`.

## How to work through this phase (read first)
1. Work in the order of the sections below. **Do not start page work (§8) before the design system
   (§3–§7) and the style guide page (§7.12) exist and you have reviewed screenshots of them.**
2. After each major step, build, take screenshots (§10.1), **open the PNGs with your image-reading tool
   and look at them**, then fix what you see. Never declare visual work done without looking at it.
3. Treat every value in this file (sizes, colors, spacing) as the spec. If something looks wrong when
   implemented, record the change and the reason in `reports/design/decisions.md`, not silently.
4. There are two **HUMAN checkpoints** (§11). Stop and ask at each one.

---

## 0. Non-negotiables

1. **One typeface: Instrument Sans** (variable, SIL Open Font License), the same family trendshift.io uses
   (verified on the live site in Oct 2026: `font-family: "Instrument Sans"`). Self-host it via Fontsource;
   **no requests to Google Fonts** (privacy, no third-party cookies, faster).
2. **Do not use or self-host Apple's SF Pro.** Its license only allows use on Apple platforms. "Apple-like"
   here means Apple's *principles*: generous whitespace, tight display tracking, restrained color, a frosted
   sticky nav, long-form pages with a comfortable reading measure. It does not mean Apple assets.
3. **Inspired by, not copied from.** Do not copy Trendshift's or Apple's markup, CSS files, logos,
   illustrations (e.g. the Trendshift owl), copy text, or the gold/silver/bronze medal badges. We take
   patterns (bordered list with divider rows, quiet indigo accent, compact metadata, right-hand rail),
   and the implementation is ours.
4. **Banned "AI-generated look" tells** (enforced in review §10.3):
   - ALL-CAPS tracked-out labels/eyebrows above headings (acronyms like SQL, HN, UTC are fine).
   - Meta strings joined with middle dots (`TypeScript · 23 days · 186 stars`). Use spaced items with icons.
   - `→` or `»` appended to link or button text. Use an external-link icon only for off-site links.
   - Accenting a single word of a headline in another color, italic, or weight.
   - Gradient washes, glows, blurred blobs, glassmorphism cards (the nav blur is the only blur allowed).
   - Identical soft-shadow cards for every piece of content. Content sits on the page or in one bordered
     list. Cards are reserved for the side rail and a few grouped panels.
   - Decorative numbering (01 / 02 / 03) on things that are not sequences.
   - Emoji as icons. Fade-and-slide entrance animations on sections.
   - Monospace for ordinary numbers. Mono is only for code, SQL, hashes, and file names.
5. **No layout shift and no overflow**, at any width from 360 px to 1920 px (enforced in §10.2).
6. **No raw values on screen**: never show `NaN`, `undefined`, `null`, `[object Object]`, `Invalid Date`,
   ISO timestamps, unrounded floats (`0.34182`), or `true/false`. All formatting goes through `lib/format.ts` (§5).
7. Every interactive element works with a keyboard and has a visible focus ring. Color is never the only
   carrier of meaning.

---

## 1. Step 1 — Audit the current site (before touching code)

1. Build the current site with fixture data and start `npm run preview`.
2. Write a Playwright script `site/scripts/screenshot.mjs` (also used later) that captures full-page
   screenshots of every route in §8 at widths **375, 768, 1280, 1440** px, in **light and dark**
   (`colorScheme` option). Save them to `reports/design/before/<route>-<width>-<theme>.png`. Use
   `deviceScaleFactor: 1` to keep files small. Wait for `document.fonts.ready` and network idle before capturing.
3. Open the screenshots. Write `reports/design/audit_before.md` listing every defect with route, width, and a
   one-line description. Classify each as **broken** (overflow, overlap, missing styles, wrong base path, raw
   values), **inconsistent** (spacing, sizes, alignment differ between pages), or **unpolished** (default
   browser controls, weak hierarchy, crowded areas).
4. Explicitly check and note these common root causes of "not formatted correctly":
   - Global CSS not imported on some pages (pages that don't use the shared layout).
   - Assets or CSS 404 because of the GitHub Pages base path (`/<repo>/`).
   - Web font not loading (falls back to Times or Arial). Check `document.fonts`.
   - Tables or long repo names pushing the page wider than the viewport.
   - Markdown pages (methodology, blog) with unstyled `h2/p/ul/table/code`.
   - Raw floats, ISO dates, UTC confusion, missing thousands separators.
   - Charts sized in fixed pixels that overflow on mobile, or are unreadable in dark mode.
5. Commit the audit (screenshots are allowed in `reports/`; keep each < 500 KB, use JPEG at quality 80 if needed).

---

## 2. Design direction: "Breakout Radar"

**Product name:** `Breakout Radar` (read from `config/project.yaml` → `site.brand_name`, add it if missing).
**Tagline:** "GitHub repos likely to break out in the next 30 days. Updated daily."
**HUMAN checkpoint A (§11)** confirms the name before the logo and OG images are generated.

**Audience:** developers, open-source watchers, VCs and tech journalists, and recruiters looking at the project.
**Primary job:** scan today's list in under 30 seconds and trust what the numbers mean.

**Personality:** precise, calm, honest. It is an instrument, not a hype machine. Numbers are big and
quiet, and explanations are plain sentences. Misses are shown as clearly as hits.

**What we take from Trendshift:** a single bordered list container with hairline dividers between rows; row
hover tint; compact repo title `owner/name` at 16 px; muted 14 px description; tiny status pills; a 300 px
right rail with small grouped panels; a cool indigo accent used sparingly; a max content width around 1280 px.

**What we take from Apple:** a frosted 56 px sticky nav with a hairline; very generous vertical spacing;
large, tightly tracked headings on long-form pages; 17 px long-form body text with a ~680 px measure;
alternating full-bleed section bands (`--bg` / `--surface`) on story pages; pill-shaped primary actions;
restraint (one accent color, almost no shadows).

**The one memorable element (spend boldness here only): the "signal column."** On every repo row, the right
column shows the **probability in large condensed tabular numerals** (Instrument Sans width axis at 87.5),
above a **28-day momentum strip** (tiny bar chart, the last 7 days in accent). It is the same component on the
leaderboard, backtest, digest, and repo pages, so it becomes the site's signature. Everything else stays quiet.

---

## 3. Design tokens (exact values)

Create `site/src/styles/tokens.css`. All colors, sizes, and radii in the codebase come from these
variables. **No hex values anywhere else** (enforced by a lint script, §10.2).

### 3.1 Color

Contrast ratios below were computed with the WCAG formula; keep them when adjusting.

| Token | Light | Dark | Use | Contrast (light on --bg / dark on --bg) |
|---|---|---|---|---|
| `--bg` | `#FFFFFF` | `#111216` | page background | — |
| `--surface` | `#F5F6F8` | `#17191E` | rail panels, alternating bands, footer, code blocks | — |
| `--raised` | `#FFFFFF` | `#1D2026` | popovers, menus, the list container in dark mode | — |
| `--ink` | `#17181C` | `#ECEDF1` | primary text, numbers | 17.7 / 16.0 |
| `--ink-2` | `#555A6A` | `#A9ADBB` | secondary text: descriptions, `owner/` prefix | 6.9 / 8.4 |
| `--ink-3` | `#6A6F82` | `#8E93A4` | tertiary: meta rows, axis labels, captions | 5.0 / 6.1 |
| `--line` | `#E4E6EC` | `#2A2D35` | hairlines, dividers, borders | — |
| `--line-strong` | `#C9CDD8` | `#3B3F4A` | input borders, focus-adjacent borders | — |
| `--accent` | `#4650C4` | `#929BF2` | links, primary buttons, momentum strip highlight, active states | 6.6 / 7.3 |
| `--accent-hover` | `#3A43AD` | `#A9B0F5` | hover/pressed | — |
| `--accent-soft` | `#EEF0FC` | `#23264A` | selected segment, "New" pill bg, row hover tint (light) | — |
| `--on-accent` | `#FFFFFF` | `#111216` | text on `--accent` | 6.6 / 7.3 |
| `--rise` | `#17744B` | `#52C48E` | realized hits, positive deltas, "healthy" status | 5.8 / 8.6 |
| `--rise-soft` | `#E7F4EC` | `#163126` | hit pill bg | — |
| `--caution` | `#995706` | `#EAA545` | unusual star pattern, stale status | 5.6 / 8.9 |
| `--caution-soft` | `#FCF1E1` | `#33260F` | caution pill bg | — |
| `--danger` | `#B42318` | `#F97066` | failed pipeline status only | — |
| `--star` | `#D99A0B` | `#E8B23A` | star icon fill only, never text | — |
| `--row-hover` | `#F8F9FB` | `#1A1C22` | list row hover | — |

Rules:
- `--ink-3` must not sit on `--accent-soft` (4.4:1). Use `--ink-2` there.
- Never encode meaning by color alone: hits are filled dots plus an sr-only label, misses are hollow dots.
- Do not color probabilities red/green. Probabilities are `--ink`. Only the meter/strip uses `--accent`.
- Chart palette (max 3 series per chart): series 1 `--accent`, series 2 `--ink-3` (dashed if it is a
  baseline/reference), series 3 `--caution`. Hits/positives: `--rise`.
- Dark mode is defined by token swaps only. No `dark:` one-off colors in components.

### 3.2 Typography

**Install:** `npm i @fontsource-variable/instrument-sans` (variable, axes `wght` and `wdth`). Import the
file that includes **both axes**. Check `node_modules/@fontsource-variable/instrument-sans/` for a `wdth.css`
(Fontsource's "full axes" file). If it is not there, use the default import and replace every `wdth` usage
below with `font-stretch: normal`. Record which you used in `reports/design/decisions.md`.
Verify the available ranges by reading the package's `@font-face` rules: expected `wght 400–700` and
`wdth 75–100`. Clamp all values used here to the real ranges.

Also `npm i @fontsource/instrument-sans` (static) only for OG image generation (§9.6), which needs `.woff`, not `.woff2`.

```css
--font-sans: "Instrument Sans Variable", "Instrument Sans", ui-sans-serif, system-ui, -apple-system,
             "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
--font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
```

Preload the latin `wght`/`wdth` woff2 file in `<head>` (`<link rel="preload" as="font" type="font/woff2" crossorigin>`)
using Vite's `?url` import, so the hashed path is correct with the base path.

**Global settings** on `html`: `font-family: var(--font-sans)`, `-webkit-font-smoothing: antialiased`,
`-moz-osx-font-smoothing: grayscale`, `text-rendering: optimizeLegibility`, `font-optical-sizing: auto`,
`font-kerning: normal`. **All numbers in tables, rows, stats, and charts** use `font-variant-numeric: tabular-nums`
(class `.num`).

**Type scale** (desktop ≥ 768 px / mobile < 768 px). Create a class per token in `base.css`
(`.t-display`, `.t-h1`, …) and use only these.

| Token | Size (desktop / mobile) | Line height | Weight | Tracking | Width | Use |
|---|---|---|---|---|---|---|
| `display` | 48 / 36 px | 1.08 | 600 | -0.025em | 100 | Long-form page titles: Methodology, About, Insights, Blog, Track-record hero |
| `h1` | 32 / 28 px | 1.18 | 600 | -0.02em | 100 | App page titles: Leaderboard, Backtest, Explore, Status, repo name |
| `h2` | 24 / 22 px | 1.25 | 600 | -0.015em | 100 | Section titles |
| `h3` | 18 / 17 px | 1.35 | 600 | -0.01em | 100 | Panel titles, sub-sections |
| `lead` | 19 / 17 px | 1.5 | 400 | -0.005em | 100 | One-sentence page intros (`--ink-2`) |
| `prose` | 17 / 17 px | 1.65 | 400 | 0 | 100 | Long-form body text |
| `body` | 16 px | 1.5 | 400 | 0 | 100 | Default UI text, repo name (500/600) |
| `body-sm` | 14 px | 1.45 | 400 | 0 | 100 | Descriptions, explanations, table cells |
| `caption` | 13 px | 1.4 | 400 or 500 | 0 | 100 | Meta rows, captions, footer |
| `micro` | 12 px | 1.35 | 500 | 0.01em | 100 | Pills, axis labels, small helper text |
| `num-lg` | 28 / 24 px | 1.0 | 600 | -0.02em | **87.5** | Probability in the signal column |
| `num-xl` | 44 / 36 px | 1.0 | 600 | -0.03em | **87.5** | Headline stats (track record, repo facts) |

Weights used: 400, 500, 600 only (700 only in the wordmark). Headings use `text-wrap: balance`;
paragraphs use `text-wrap: pretty`. Long-form measure: `max-width: 68ch` (≈ 680 px at 17 px). UI
descriptions: `max-width: 72ch`.

### 3.3 Space, size, radius, elevation, motion, z-index, breakpoints

```css
/* 4px base spacing scale */
--space-1: 4px;  --space-2: 8px;  --space-3: 12px; --space-4: 16px; --space-5: 20px;
--space-6: 24px; --space-8: 32px; --space-10: 40px; --space-12: 48px; --space-16: 64px; --space-24: 96px;

/* layout */
--container: 1200px;                 /* max content width */
--gutter: 16px;                      /* 24px ≥ 640, 32px ≥ 1024 (set in media queries) */
--rail: 300px;                       /* leaderboard right rail */
--aside: 320px;                      /* repo page aside */
--measure: 68ch;                     /* long-form reading width */
--nav-h: 56px;

/* radius: hierarchy, not one radius everywhere */
--r-xs: 4px;     /* bars in charts, code inline */
--r-sm: 6px;     /* inputs inside panels, small buttons */
--r-md: 8px;     /* buttons, selects, segmented control */
--r-lg: 12px;    /* list container, rail panels, code blocks */
--r-xl: 16px;    /* large figures, OG frames, callouts on long-form pages */
--r-pill: 999px; /* pills, primary CTA on long-form pages */

/* elevation: only for things that float */
--shadow-pop: 0 1px 2px rgb(16 18 24 / .06), 0 8px 24px rgb(16 18 24 / .12);   /* menus, tooltips, popovers */
/* dark: 0 1px 2px rgb(0 0 0 / .4), 0 12px 32px rgb(0 0 0 / .5) */

/* motion */
--ease: cubic-bezier(.2, 0, 0, 1);
--dur-1: 120ms;  /* color/background on hover */
--dur-2: 200ms;  /* disclosure open/close, menu */
--dur-3: 600ms;  /* the one chart draw-in on the repo page */

/* z-index */
--z-nav: 50; --z-menu: 60; --z-tooltip: 70; --z-skip: 100;
```

Breakpoints (mobile-first): `sm 640`, `md 768`, `lg 1024`, `xl 1280`. The right rail and asides appear at `lg`.

**Vertical rhythm:** page header block `padding-top: 48px` (32 mobile), `padding-bottom: 24px`;
between page sections `64px` (48 mobile); inside a section, heading → content `16px`; panel padding `20px`
(16 mobile); list row padding `20px 20px` (16 mobile). Long-form story bands: `96px` vertical (64 mobile).

---

## 4. Tech setup

1. **Styling: Tailwind CSS v4**, CSS-first config, wired into Astro through the official Vite plugin
   (`@tailwindcss/vite`). Follow the current Astro + Tailwind v4 guide. **Do not** use v3 syntax:
   no `tailwind.config.js`, no `@tailwind base;` directives, no `@astrojs/tailwind` integration.
   In `site/src/styles/global.css`:
   ```css
   @import "tailwindcss";
   @import "./tokens.css";
   @import "./base.css";
   @import "./prose.css";
   @theme inline {
     --font-sans: var(--font-sans);
     --color-bg: var(--bg); --color-surface: var(--surface); --color-raised: var(--raised);
     --color-ink: var(--ink); --color-ink-2: var(--ink-2); --color-ink-3: var(--ink-3);
     --color-line: var(--line); --color-line-strong: var(--line-strong);
     --color-accent: var(--accent); --color-accent-soft: var(--accent-soft);
     --color-rise: var(--rise); --color-rise-soft: var(--rise-soft);
     --color-caution: var(--caution); --color-caution-soft: var(--caution-soft);
     --radius-sm: var(--r-sm); --radius-md: var(--r-md); --radius-lg: var(--r-lg); --radius-xl: var(--r-xl);
   }
   @custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));
   ```
   Dark tokens are defined twice in `tokens.css`: under `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { … } }`
   and under `:root[data-theme="dark"] { … }`. This supports system, light, and dark (§9.1).
   If Tailwind's palette defaults leak in (`text-gray-500`, `bg-blue-600`), the lint in §10.2 fails the build.
2. `global.css` is imported **once**, in `src/layouts/BaseLayout.astro`. **Every page uses a layout** that
   extends `BaseLayout` (add a test that every page file imports a layout).
3. **Icons: Lucide.** Use the official Astro package if one exists (check npm for `@lucide/astro`). Otherwise
   copy the needed SVGs from `lucide-static` into `src/components/ui/Icon.astro` as an inline-SVG map. Default
   16 px in text and 20 px in buttons, `stroke-width: 1.75`, `currentColor`, `aria-hidden="true"` unless meaningful.
4. **Charts:** Observable Plot (already used), themed by `lib/plot-theme.ts` (§9.4). Sparklines and momentum
   strips are **server-rendered inline SVG** (no JS).
5. **Client JS budget:** the leaderboard ships < 30 KB gzipped JS. Interactivity uses small Astro `<script>`
   modules (vanilla TS) with data attributes. **No React/Vue/Svelte.** Exceptions loaded only on their pages:
   DuckDB-WASM and CodeMirror on `/explore/`, and Plot on pages with charts.
6. **Typed data loading:** `src/lib/data.ts` reads `public/data/*.json` at build time with types in
   `src/lib/types.ts`, matching the JSON Schemas from Phase 10. Use `zod` to validate, and fail the build with a
   clear message naming the file and field.
7. **File structure** to create:
   ```
   site/src/
     styles/        tokens.css base.css prose.css global.css
     lib/           format.ts format.test.ts data.ts types.ts theme.ts plot-theme.ts languages.ts url.ts
     layouts/       BaseLayout.astro AppLayout.astro LongformLayout.astro
     components/
       layout/      Nav.astro MobileMenu.astro Footer.astro PageHeader.astro Section.astro Rail.astro
                    ThemeToggle.astro FreshnessPill.astro SkipLink.astro Seo.astro
       ui/          Button.astro Pill.astro SegmentedControl.astro Select.astro Tooltip.astro Panel.astro
                    Callout.astro Table.astro EmptyState.astro Disclosure.astro CopyButton.astro Avatar.astro
                    Icon.astro ExternalLink.astro Skeleton.astro Kbd.astro
       data/        RepoRow.astro RepoTitle.astro SignalColumn.astro MomentumStrip.astro FactStrip.astro
                    HitDots.astro ShapBars.astro ChartFigure.astro LanguageDot.astro OutcomeBanner.astro
     pages/         (all routes in §8) + _styleguide.astro
   site/tests/      layout.spec.ts a11y.spec.ts visual.spec.ts content.spec.ts
   site/scripts/    screenshot.mjs lint-tokens.mjs check-base-path.mjs
   ```
8. Remove dead Phase 10 styles and components after migrating. Use no inline `style=""` except to pass
   computed CSS custom properties (e.g. `style="--w: 34%"`).

---

## 5. Formatting rules (`src/lib/format.ts`) — the cure for "not formatted correctly"

Every displayed number, date, and string goes through one of these functions. Write `format.test.ts`
(Vitest) with at least the cases listed. Locale is fixed to `en-US`. **All dates are UTC** and say so where a
time is shown.

| Function | Rules | Examples (input → output) |
|---|---|---|
| `count(n, {compact})` | Integers. Thousands separators. `compact` (rows, pills) uses one decimal from 1,000: `k`, `M`. Tables use full numbers. | `186 → "186"`, `2912 → "2,912"`, `2912 compact → "2.9k"`, `1_250_000 compact → "1.3M"`, `999 compact → "999"`, `1000 compact → "1k"` (no `.0`) |
| `delta(n)` | Signed with true minus sign `−` (U+2212). Zero → "0". | `412 → "+412"`, `-3 → "−3"` |
| `pct(p)` | Probability or share 0–1 → integer percent. `< 0.01` → "<1%", `> 0.99` → ">99%". Never a decimal unless `digits` is given. | `0.3418 → "34%"`, `0.004 → "<1%"`, `0.996 → ">99%"` |
| `odds(p)` | Plain-language odds for tooltips and sub-labels. `p < 0.5` → "About 1 in N", where N = round(1/p) capped at 1,000 ("Less than 1 in 1,000"). `0.5 ≤ p < 0.65` → "About even odds". `p ≥ 0.65` → "Likely". | `0.34 → "About 1 in 3"`, `0.07 → "About 1 in 14"` |
| `date(d)` | UTC, `MMM D, YYYY`. | `2026-10-21 → "Oct 21, 2026"` |
| `shortDate(d)` | UTC, `MMM D`, plus the year if it differs from the build year. | `"Oct 21"`, `"Dec 30, 2025"` |
| `dateRange(a,b)` | En dash, shared parts merged. | `"Aug 22 – Oct 21, 2026"` |
| `relTime(ts, now)` | `Intl.RelativeTimeFormat`, numeric "auto". | `"3 hours ago"`, `"yesterday"` |
| `utcTime(ts)` | `HH:mm UTC`. | `"03:42 UTC"` |
| `hours(h)` | Durations: < 1 h → "under 1 h"; < 48 h → "~N h"; else "~N days". | `3.2 → "~3 h"`, `70 → "~3 days"` |
| `age(days)` | "1 day old", "23 days old", "Created today". | — |
| `plural(n, one, many)` | Always used for unit nouns. | `1 star`, `2 stars` |
| `repoName(full)` | Returns `{owner, name}`. The display inserts `<wbr>` after `/` and allows `overflow-wrap: anywhere` on the name. | — |
| `cleanText(s, max)` | Trim, collapse whitespace and newlines, strip GitHub emoji shortcodes (`:rocket:`), strip markdown links to their text, cut at a word boundary with `…`. Empty → `null` (component shows "No description"). | — |
| `missing()` | Renders `—` with `aria-label="Not available"`. Used for null numbers. | — |
| `hash(h)` | First 10 hex chars + `…`, with the full hash in `title` and copy button. | — |

Content rules:
- Explanation sentences come from Phase 8 already in sentence case. Ensure exactly one terminal period and no
  double spaces.
- Language names come from data. The colored dot comes from `lib/languages.ts`, which is generated at build
  from the `linguist-languages` npm package (verify the name; else ship a small static map for the top 40
  languages). Unknown → `--ink-3` dot.
- CJK, RTL, and emoji descriptions must render cleanly (fixtures in §10.4 cover them).

---

## 6. Copy & microcopy guide

Voice: plain, precise, calm. Write for a developer skimming on a phone. Sentence case everywhere (titles,
buttons, nav, table headers). Active verbs. No hype words ("explosive", "rocket", "insane"), no emoji in UI copy.

Glossary (use these exact words everywhere):
- **Breakout:** a repo gaining stars faster than 99.5% of similar young repos over the next 30 days. Defined once
  per page in a tooltip or footnote, linked to Methodology.
- **Breakout chance:** the calibrated probability. Label it "breakout chance", never "score".
- **Flagged:** entered the top 50.
- **Stars observed:** stars seen in GH Archive since the repo appeared. GitHub's own count may differ; say so in a tooltip.
- **Unusual star pattern:** suspicion signal. Never "fake", "fraud", or "bot farm".
- **Hit / miss:** realized outcome of a matured prediction.

Required strings (use verbatim or near-verbatim):
- Leaderboard intro: "Young GitHub repositories most likely to break out in the next 30 days, ranked by breakout chance. Updated every morning from public GitHub activity."
- Probability tooltip: "Breakout chance: {pct} ({odds}). Of repos we gave about this chance in the past, about {pct} broke out."
- Unusual pattern pill tooltip: "An unusual share of recent stars came from new or inactive accounts. This may or may not mean the stars are inauthentic. See details."
- Backtest banner: "These are simulated predictions from back-testing on past data, not predictions we published at the time."
- Empty filter result: "No repos match these filters." with a "Clear filters" button.
- Stale data (heartbeat older than 30 h): "Today's update is late. Showing data through {date}." in a caution callout.
- 404: "This page doesn't exist. Repo pages stay up for 90 days after a repo leaves the list." with "Go to today's list".
- Explorer errors: show DuckDB's message, then one hint line, e.g. "Check the column names in the schema panel."

Buttons say what happens: "Open on GitHub", "Copy badge", "Run query", "Clear filters", "Show all 25".

---

## 7. Components (build these first, all visible on `/_styleguide/`)

Each component: props typed, all states implemented (default, hover, active/pressed, focus-visible, disabled,
loading where relevant, empty/missing data), light and dark, and documented in the style guide with examples.

### 7.1 Layout shell
- **`BaseLayout`**: `<html lang="en" data-theme>` with the theme script inline in `<head>` before CSS (§9.1), font
  preload, `Seo` component, skip link ("Skip to content"), `<Nav/>`, `<main id="content">`, `<Footer/>`.
- **`AppLayout`** (app pages): container (`max-width: var(--container)`, gutters), optional rail slot. Grid at
  `lg`: `grid-template-columns: minmax(0,1fr) var(--rail); column-gap: 32px` (40 at `xl`). Main column first in the DOM.
- **`LongformLayout`** (methodology, about, blog, insights): centered `--measure` column; figures may break out
  to 880 px; optional sticky table of contents in a left column at `xl` (200 px, `top: calc(var(--nav-h) + 24px)`).

### 7.2 `Nav`
```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ [◎] Breakout Radar   Today  Track record  Backtest  Explore  Insights  Methodology       │
│                                                       ● Updated 3 hours ago  [◐] [GH]    │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```
- Height 56 px, `position: sticky; top: 0; z-index: var(--z-nav)`. Background
  `color-mix(in srgb, var(--bg) 78%, transparent)` with `backdrop-filter: saturate(180%) blur(16px)`, and a 1 px
  bottom border in `--line`. Use a solid fallback `--bg` when `backdrop-filter` is unsupported (`@supports`).
- Logo (20 px mark + wordmark 16/600, tracking -0.01em) links home. Nav links are 14/500 `--ink-2` with 8 px 12 px
  padding and `--r-md` radius; hover `--ink`; current page `--ink` with `aria-current="page"` and a 2 px `--accent` bar
  under the link, inset 12 px.
- Right side: `FreshnessPill` (8 px dot `--rise` if the heartbeat < 30 h old, `--caution` otherwise, plus text
  "Updated 3 hours ago", 13/500). Hidden < 1024 px (shown in the mobile menu instead). Theme toggle icon button.
  GitHub icon button linking to the repo (label "Source code on GitHub").
- < 1024 px: logo + menu button ("Menu", icon `menu`). It opens `MobileMenu`, a `<dialog>`-based full-width sheet from the
  top: links at 17/500 with 48 px rows, freshness, and theme toggle. Focus is trapped (native dialog), Esc closes, and body
  scroll is locked.

### 7.3 `Footer`
`--surface` background, 1 px top border, padding 48/32. Four columns at `lg` (2 at `sm`, 1 on mobile):
**Product** (Today, Track record, Backtest, Explore, Insights, Digest), **Data** (Events dataset, Snapshots,
Prediction ledger, Model card; on Hugging Face/GitHub with an external icon), **Project** (Methodology, Status,
Source code, RSS feed), **About** (About, Opt-out request, "Not affiliated with GitHub"). Column titles are 13/600
`--ink`, and links are 13/400 `--ink-2` with 8 px vertical rhythm. Bottom line, 12 px `--ink-3`, as separate items with
16 px gaps: "Data through Oct 20, 2026", "Model 20261019-a1b2c3d", "Built Oct 21, 03:58 UTC".

### 7.4 `PageHeader`
Props: `title`, `lead?`, `meta?` (slot), `actions?` (slot), `size: 'app' | 'display'`. `h1` (or `display` for long-form),
lead 19/17 `--ink-2` max 60ch with 8 px gap, then meta/actions row with 16 px gap. Left-aligned on app pages,
centered on long-form heroes.

### 7.5 `Button`
Variants: `primary` (`--accent` bg, `--on-accent` text), `secondary` (`--raised` bg, 1 px `--line-strong` border,
`--ink` text), `ghost` (transparent, `--ink-2`, hover `--surface`), `icon` (square, ghost style).
Sizes: `sm` 32 px high, 12 px x-padding, 13/500; `md` 36 px, 14 px x-padding, 14/500; `lg` 44 px, 20 px x-padding,
16/500. Radius `--r-md`; the `pill` modifier uses `--r-pill` (long-form CTAs only). Icon gap 6 px. Pressed state:
`transform: translateY(0.5px)` plus darker bg. Disabled: 50% opacity, `cursor: not-allowed`. Loading: spinner replaces the
icon and the label stays. Renders `<a>` when `href` is given, else `<button type="button">`. External links add an
`arrow-up-right` 14 px icon after the text plus `target="_blank" rel="noopener"` and sr-only "(opens in new tab)".

### 7.6 `Pill`
Height 20 px, padding 0 8 px, `--r-pill`, 12/500, optional 12 px leading icon. Variants: `neutral`
(`--surface` / `--ink-2`), `accent` ("New": `--accent-soft` / `--accent`), `rise` ("Hit": `--rise-soft` / `--rise`),
`caution` ("Unusual star pattern": `--caution-soft` / `--caution`, icon `alert-triangle`), `rank-up`/`rank-down`
(neutral with `arrow-up`/`arrow-down` icon and number: "3", sr-only "up 3 places"). Sentence case text. Never all caps.

### 7.7 `SegmentedControl`
Real radio inputs in a `fieldset` with a `legend` (sr-only). Track: `--surface` bg, 1 px `--line` border, `--r-md`,
padding 2 px, height 36 px. Segment: 14/500 `--ink-2`, padding 0 12 px. Selected: `--raised` bg with `--shadow-pop`
reduced to `0 1px 2px` and `--ink` text. Arrow keys move between options natively. Used for: All / New today, and for
chart granularity on repo pages.

### 7.8 `Select`
Native `<select>` (accessible and good on mobile) styled: height 36 px, `--raised` bg, 1 px `--line-strong` border,
`--r-md`, 14/500, padding 0 32 px 0 12 px, custom `chevron-down` icon positioned absolutely, `appearance: none`.
Visible label (13/500 `--ink-2`) or `aria-label`.

### 7.9 `Tooltip`
Trigger is a button or focusable element; content appears on hover **and** focus, after 150 ms, dismissed by Esc.
Implement with the Popover API (`popover="manual"`) plus CSS anchor positioning where supported and a small JS
fallback for positioning. Style: `--raised` bg, `--shadow-pop`, `--r-md`, padding 8 px 10 px, 13/400 `--ink`,
max-width 280 px. Never put essential information only in a tooltip on touch devices: probability odds also appear
in the row as a sub-label.

### 7.10 `Panel`, `Callout`, `Table`, `EmptyState`, `Disclosure`, `CopyButton`, `Avatar`, `Skeleton`
- **Panel** (rail): `--surface` bg in light, `--raised` in dark, 1 px `--line` border, `--r-lg`, padding 20 px. Title h3
  (16/600 in panels) and optional action link at the right of the title row.
- **Callout**: variants info/caution/rise. 1 px border in the variant color at 30% (`color-mix`), soft bg, 16 px icon,
  14 px text, `--r-lg`, padding 12 px 16 px.
- **Table**: wrapper `overflow-x: auto` inside the content column (never the page), with an inset shadow cue on the
  scrollable edge. `<caption>` (sr-only if visually redundant). Header 12/500 `--ink-3`, sentence case, bottom border
  `--line`, `position: sticky; top: 0` inside scroll containers. Cells 14 px, padding 10 px 12 px, hairline rows, no
  zebra. Numeric columns right-aligned `.num`. First column may be sticky-left on mobile.
- **EmptyState**: centered within its container, 40 px icon in `--ink-3`, title 16/600, one line of help, and an optional
  action button. No illustrations.
- **Disclosure**: `<details>/<summary>` with a chevron that rotates 90° (`--dur-2`), summary 14/500, and content padding-top 12 px.
- **CopyButton**: icon button. On success it swaps to a `check` icon for 1.5 s and announces "Copied" via an
  `aria-live="polite"` region.
- **Avatar**: GitHub avatar `https://avatars.githubusercontent.com/u/{owner_id}?s=64&v=4` (needs `owner_id`, §7.11).
  `width`/`height` attributes always set, `loading="lazy"`, `decoding="async"`, `referrerpolicy="no-referrer"`. **Users
  are circles, organizations are rounded squares (`--r-sm`)**, as on GitHub. Fallback (no id or load error): initials
  on `--surface` with `--ink-2` text. Alt text is the owner login.
- **Skeleton**: `--surface` blocks with a subtle shimmer (disabled with reduced motion). Used only on `/explore/` while
  DuckDB loads.

### 7.11 Data components (the product's core)

**`RepoRow`** (leaderboard, backtest, digest, similar repos in compact mode). All rows live inside **one** list
container: `--raised` bg, 1 px `--line` border, `--r-lg`, `overflow: hidden`, rows separated by 1 px `--line`
(`divide-y`). Row padding 20 px (16 mobile). Hover: `--row-hover` bg (`--dur-1`). The whole row is clickable via a
stretched link on the repo title (`::after { content:""; position:absolute; inset:0 }`); inner interactive
elements (`GitHub` icon link, tooltips) get `position: relative; z-index: 1`.

Desktop anatomy (≥ 768 px):
```
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│  4   (av) owner/name        [New] [↑3] [⚠ Unusual star pattern]                   34%           │
│           Description in 14px ink-2, clamped to 2 lines, max 72ch…               About 1 in 3   │
│           ┃ 72% of recent stars come from experienced accounts, and issues      ▁▁▂▂▃▄▆█▇█     │
│           ┃ get a first response in ~3 h.                                        +412 this week │
│           ● TypeScript   ◷ 23 days old   ☆ 186 stars observed   On the list 4 days            │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
  32px      32px avatar + 12px gap         flexible main column (min 0)                 160px signal column
```
- Grid: `grid-template-columns: 32px 32px minmax(0,1fr) 160px; column-gap: 12px` (gap 16 px before the signal column).
- **Rank:** 15/600 `.num`, right-aligned in its 32 px cell, `--ink-3` (top 3 in `--ink`). No medals.
- **Avatar** 32 px, aligned to the first line of the title (`margin-top: 2px`).
- **Title** (`RepoTitle`): `owner/` in 16/400 `--ink-2` and `name` in 16/600 `--ink`, `<wbr>` after the slash,
  `overflow-wrap: anywhere`. Pills follow the title inline with an 8 px gap and wrap below on narrow widths.
- **Description:** 14/1.45 `--ink-2`, `-webkit-line-clamp: 2`, `max-width: 72ch`, 4 px below the title. Missing →
  "No description" in `--ink-3` regular (no italics anywhere in the UI).
- **Why line:** 14/1.45 `--ink`, `padding-left: 10px`, `border-left: 2px solid var(--accent-soft)` (dark:
  `--accent` at 40%), 8 px below the description, clamp 2 lines on the leaderboard (full on repo pages).
- **Meta row:** 13/400 `--ink-3`, items separated by a 16 px gap (no dots), each with a 14 px icon: `LanguageDot`
  (8 px circle) + language; `clock` + age; `star` (fill `--star`) + "186 stars observed"; `calendar` + "On the list 4 days".
  Wraps on narrow widths. 10 px below the why line.
- **`SignalColumn`** (right, 160 px, right-aligned): probability `num-lg` in `--ink` (tooltip with odds and
  definition), the sub-label `odds()` 12/500 `--ink-3`, then a 12 px gap, the **`MomentumStrip`** (120 × 28),
  then "+412 this week" 12/500 `--ink-2` `.num`. Vertically top-aligned with the title.

Mobile anatomy (< 768 px):
```
┌───────────────────────────────────────────────┐
│ 4  (av) owner/                          34%   │
│         name                    About 1 in 3  │
│ [New] [↑3]                                    │
│ Description, 2 lines…                         │
│ ┃ Why line, 3 lines max…                      │
│ ▁▁▂▂▃▄▆█▇█▁▂▃▄▆█▇█▁▂▃▄▆█▇█   +412 this week   │
│ ● TypeScript  ◷ 23 days old  ☆ 186            │
└───────────────────────────────────────────────┘
```
- Grid: `24px 28px minmax(0,1fr) auto` for the top line; the probability sits top-right at 24 px. Below it, the
  momentum strip spans the full content width (`width: 100%`, height 24 px, SVG `preserveAspectRatio="none"` with bars
  computed in percentages) with the weekly delta to its right. The meta row shows language, age, and stars (compact count).

**`MomentumStrip`** (server-rendered SVG, no JS):
- Props: `values: number[]` (28 daily star counts, oldest → newest), `highlight = 7`, `markerIndex?` (day first flagged),
  `width`, `height`, `label`.
- Bars: 28 bars with 1.5 px gaps, width computed to fill; height `max(1, round(h * v / max))`, aligned to the bottom; radius
  `--r-xs` on top corners only if bar width ≥ 3 px. Earlier 21 bars `--ink-3` at 35% opacity, last 7 bars `--accent`. Zero
  days show a 1 px tick in `--line`. Optional marker: 1 px vertical line in `--ink-2` at the flag day with a 3 px dot on top.
- Accessibility: `role="img"` and `aria-label` like "Stars per day, last 28 days: 612 total, peak 140 on Oct 18."
- All repos on one page share the same **per-row** scale (each strip scales to its own max). Write this rule in the
  methodology footnote; the shape, not the height, is the signal.

**`FactStrip`** (repo page header): 4–5 cells in a row separated by 1 px vertical `--line` dividers (not cards), each
with a label 13/500 `--ink-3` above a value `num-xl` in `--ink` (the probability) or 24/600 `.num` (others). It becomes a
2-column grid on mobile with horizontal dividers.

**`HitDots`** (track record): 25 dots of 10 px in a row with a 4 px gap; a hit is a filled `--rise` circle, a miss is a hollow 1.5 px `--ink-3` ring,
and not-yet-matured is a 2 px `--line-strong` dash. Wraps at small widths. Includes an sr-only text summary ("7 of 25 broke out").

**`ShapBars`** (why flagged, repo page): a horizontal diverging bar chart rendered as server-side SVG/HTML. Rows are
feature sentences (14 px `--ink`, left) and bars (right, 40% width) extending right in `--accent` for pushes up and
left in `--ink-3` for pushes down from a center line, with the value label at the bar end 12 px `.num`. 5–7 rows max.
Axis caption: "Pushes the chance up / down".

**`OutcomeBanner`** (matured predictions): a callout with `--rise` "Broke out: +2,340 stars in 30 days (threshold +410)"
or neutral "Did not break out: +180 stars in 30 days (threshold +410)". Tone is neutral, with no celebration.

**`ChartFigure`**: `<figure>` wrapper with a title (h3), an optional legend (inline, 13 px, color swatch 10 × 2 px line or
10 px square), the chart slot, `<figcaption>` 13 px `--ink-3`, and an sr-only data table or summary. Responsive
width via `ResizeObserver` (re-render Plot on width change, debounced 100 ms).

**Data field needed:** add `owner_id` and `owner_type` per repo to `leaderboard.json` and `repos/<id>.json` in
`breakout publish site-data` (from repo metadata). Update the JSON schemas and Python tests.

### 7.12 `/_styleguide/` page
Not linked, `noindex`, and excluded from the sitemap. Sections: color tokens (swatches with names and contrast ratios
computed live), the type scale (each token with a sample), spacing scale, radii, buttons (all variants × sizes × states),
pills, segmented control, select, tooltip, panel, callout, table, empty state, disclosure, avatar (user/org/fallback),
RepoRow with each edge-case fixture (§10.4), MomentumStrip variants, FactStrip, HitDots, ShapBars, OutcomeBanner,
and a sample chart. It has a light/dark toggle at the top. **This page is the primary review surface for checkpoint B.**

---

## 8. Pages (exact layouts)

General rules for every page: uses a layout; exactly one `h1`; logical heading order; page `<title>` pattern
`"{Page} | Breakout Radar"` (home: `"Breakout Radar: GitHub repos likely to break out"`); meta description ≤ 155 chars;
canonical URL with base path; OG image (§9.6).

### 8.1 `/` Today (leaderboard)
```
[Nav]
┌──────────────────────────────────────── container 1200 ────────────────────────────────────────┐
│ Repos likely to break out                                       (h1 32)                          │
│ Young GitHub repositories most likely to break out in the next 30 days, ranked by breakout       │
│ chance. Updated every morning from public GitHub activity.      (lead 19, ink-2, 60ch)           │
│ ◷ Data through Oct 20, 2026   ⓘ What the numbers mean                       (caption, 16px gap)  │
│                                                                                                  │
│ ┌ main (minmax 0, 1fr) ─────────────────────────────────────┐   ┌ rail 300 ───────────────────┐ │
│ │ [All | New today]  [Language ▾]  [Sort: Breakout chance ▾] │   │ How to read this list        │ │
│ │ [☐ Hide unusual star patterns]                  50 repos   │   │ 3 short lines + link         │ │
│ │ ┌─ list container (r-lg, border) ───────────────────────┐ │   ├──────────────────────────────┤ │
│ │ │ RepoRow 1                                             │ │   │ Track record so far           │ │
│ │ │───────────────────────────────────────────────────────│ │   │ 18% of top-25 picks broke out │ │
│ │ │ RepoRow 2                                             │ │   │ vs 2% for all candidates      │ │
│ │ │ …                                                     │ │   │ [mini line chart 268×64]      │ │
│ │ └───────────────────────────────────────────────────────┘ │   │ See the track record          │ │
│ │                                                           │   ├──────────────────────────────┤ │
│ │                                                           │   │ Matured this week             │ │
│ │                                                           │   │ 3 compact rows with Hit/Miss  │ │
│ │                                                           │   ├──────────────────────────────┤ │
│ │                                                           │   │ Follow the list               │ │
│ │                                                           │   │ [RSS] [Bluesky] [Badge] icons │ │
│ └───────────────────────────────────────────────────────────┘   └──────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
[Footer]
```
- If data is stale (> 30 h), show the caution `Callout` above the filters.
- Filter bar: a flex-wrap row with a 12 px gap, aligned to the list's left edge; the result count is right-aligned 13/500
  `--ink-3` `.num`. On mobile, the controls stack into two rows and stay full width. Filters update the URL query
  (`?lang=Rust&new=1&hide=unusual&sort=stars7d`), so views are shareable; state restores on load; there is no layout jump.
  Filtering toggles `hidden` on rows (no re-render) and updates the count; an empty result shows `EmptyState` inside the
  list container.
- The rail moves **below** the list on < 1024 px, as a 2-column grid of panels at `md` and 1 column on mobile.
  "Follow the list" moves into the footer area on mobile, not duplicated.
- The rail panels do not stick (avoids long-rail overlap). On ≥ 1280 px, the "How to read this list" panel may be sticky
  at `top: calc(var(--nav-h) + 24px)` if the rail is shorter than the viewport.
- Show all 50 rows (no pagination); the list is light because strips are SVG.

### 8.2 `/repo/[id]/` Repo detail
```
[Nav]
Today / owner/name                                   (breadcrumb, 13px ink-3, `/` separators)
(av56) owner/name                        [Open on GitHub ↗] [Copy badge]
       Description, 17px ink-2, max 68ch
       [New] [⚠ Unusual star pattern]
┌ FactStrip ───────────────────────────────────────────────────────────────────────────────┐
│ Breakout chance │ Rank today │ Age          │ Stars, last 7 days │ Stars observed         │
│ 34%  (num-xl)   │ 4 of 50    │ 23 days      │ +412               │ 1,186                  │
└──────────────────────────────────────────────────────────────────────────────────────────┘
┌ main ───────────────────────────────────────────────┐  ┌ aside 320 (sticky at lg) ─────┐
│ Why it's flagged (h2)                                │  │ Details                        │
│ Explanation sentence (17px)                          │  │ Language   ● TypeScript         │
│ ShapBars                                             │  │ Owner      Organization         │
│                                                      │  │ Created    Sep 28, 2026         │
│ Star momentum (h2)          [Daily | Cumulative]     │  │ First flagged Oct 17, 2026      │
│ Line/bar chart, 280px tall, flag markers             │  │ License    MIT                  │
│                                                      │  ├────────────────────────────────┤
│ Prediction history (h2)                              │  │ Badge for your README           │
│ Small line chart of chance by day + compact table    │  │ preview + code block + Copy     │
│                                                      │  ├────────────────────────────────┤
│ Who's starring (h2)                                  │  │ Links                           │
│ 3 stat cells + short text                            │  │ GitHub ↗, Hacker News threads ↗ │
│                                                      │  └────────────────────────────────┘
│ Stars vs adoption (h2) retention heatmap (Phase 11)  │
│ Similar repos (h2) compact RepoRows                  │
│ Unusual star pattern (h2) only if flagged            │
│ Outcome (OutcomeBanner) if matured — placed FIRST    │
│   in main when it exists                             │
└──────────────────────────────────────────────────────┘
```
- Sections whose data is missing are omitted entirely, with no empty headings.
- The star momentum chart uses Plot with daily bars (`--ink-3` 35%, last 7 days `--accent`), or a cumulative line in
  cumulative mode. Flag days are marked with a small `--accent` dot on the x-axis; matured outcomes show a shaded horizon band
  (`--accent-soft`). The x-axis uses `shortDate`; the y-axis shows grid lines only, 4 ticks max.
- The chart draw-in (`--dur-3`) is the **only** non-user-triggered animation on the site; skip it under reduced motion.

### 8.3 `/track-record/`
- Long-form hero centered: `display` "Track record", then a data-generated lead sentence such as "Since Jul 3, 2026, 18% of
  our top-25 picks broke out within 30 days, against 2% for all candidates." (Generate the sentence in
  `publish site-data`, not in the template.)
- Stat row of 3 cells (`FactStrip` style): "Top-25 hit rate", "Baseline hit rate" (B1), "Median lead over GitHub
  Trending". Each value is `num-xl` with a 13 px caption explaining it in one line.
- Charts: rolling precision@25 (model `--accent` solid vs baseline `--ink-3` dashed, legend inline) and a reliability
  diagram (square, max 420 px, diagonal reference `--line-strong` dashed, points sized by count, axis "Predicted chance"
  vs "Share that broke out").
- Matured predictions: a list with one row per date: date (14/600), `HitDots`, "7 of 25" `.num`, and a disclosure to expand
  the 25 repos (compact rows with the realized gain and a Hit pill). Newest first, with 30 visible plus "Show older".
- "Verify this record" panel: 3 numbered steps (a real sequence), the latest ledger hash (mono, `hash()` with copy
  button), and links to the snapshots dataset and `ledger/predictions.csv`.
- If live history is short (< 30 matured days), say so in a neutral callout instead of showing thin charts.

### 8.4 `/backtest/`
Page header + info `Callout` (backtest banner copy, §6). Date control: prev/next week icon buttons + a native
`<input type="date">` constrained to available snapshot dates (snap to the nearest available date, shown in the label) +
"Latest" button. The list uses `RepoRow` with an outcome pill instead of the "New" pill, and the why line hidden.
Summary line above the list: "On Mar 4, 2024: 6 of the top 25 broke out (24%)."

### 8.5 `/explore/`
- Desktop two-pane layout: left 280 px panel "Tables" (each view, its columns with types in 13 px mono, click to insert)
  and "Examples" (buttons with sentence-case titles); right: the editor and results.
- Editor: CodeMirror 6 with SQL highlighting, loaded lazily on this page only, 14 px mono, min height 160 px,
  `--surface` bg, `--r-lg`. Theme colors from tokens (light/dark). "Run query" primary button with `Kbd` hint
  "⌘↵ / Ctrl↵".
- Status line (13 px `--ink-3`): "Loading DuckDB…" with Skeleton, "1,250 rows in 84 ms (showing first 500)". Errors
  use a danger-tinted callout with the message in mono.
- Results table: `Table` component with sticky header, horizontal scroll inside the pane, numbers right-aligned,
  nulls as `—`, timestamps formatted, a 500-row display cap, and a "Download CSV" ghost button.
- Mobile: panes stack (examples become a horizontal chip scroller), and the editor is full width.

### 8.6 `/methodology/`, `/about/`, `/blog/[slug]/` (LongformLayout + `prose.css`)
`prose.css` (write it; do not use the default Tailwind typography plugin unmodified):
- Body 17/1.65 `--ink`, paragraphs 0 0 20 px; `h2` (long-form variant, larger than the app `h2` on purpose) 28/1.2 600 -0.02em with 56 px top and 12 px bottom margin; `h3` 20/1.3 600
  with 32/8 px margins; lists with 24 px indent and 6 px item gap, markers `--ink-3`; links `--accent`, underline
  `text-underline-offset: 3px`, `text-decoration-thickness: 1px`, hover thicker; blockquote 3 px `--line-strong` left
  border with `--ink-2` text; inline code 0.9em mono on `--surface` with `--r-xs` and 2 px 5 px padding; code blocks
  `--surface` bg, `--r-lg`, padding 16 px, 14/1.6 mono, horizontal scroll; tables via the `Table` styles; images and
  figures `--r-xl` with 13 px caption `--ink-3`; `hr` 1 px `--line` with 48 px margins.
- Methodology adds a sticky TOC at `xl` (13/500 links, current section highlighted via IntersectionObserver), a
  definitions list for the label and candidate rules styled as a two-column `dl`, and the figures from `reports/figures`.
  Charts rendered as images get dark-mode variants (generate both from matplotlib with the token colors), or are placed
  on a light `--r-xl` card so they never sit as black-on-dark.
- About: a centered display hero, then bands alternating `--bg`/`--surface` (Apple-style), each 96 px tall in vertical
  padding: what it is, how it works (3 real steps), data and credits, contact and opt-out.

### 8.7 `/insights/` (Phase 11 data)
Long-form hero, then one **band** per story (alternating backgrounds): story title h2 (28 px), 3 sentences (17 px, 60ch),
`ChartFigure` up to 880 px wide, and a `Disclosure` "Show the SQL" with a mono code block and copy button. Left-aligned
text within the centered measure.

### 8.8 `/status/`
App layout without a rail. Top: a big status line, "All systems normal" or "Today's update is late", with a status icon
(check/alert, not color alone) and the last run time. Then:
- "Pipeline steps": horizontal bar chart of step durations for the last run (Plot), plus a 14-day small multiple of total
  runtime.
- "Data freshness" `Table`: event type, latest event, rows ingested in the last 24 h, missing hours.
- "Model": version, trained date, holdout PR-AUC and precision@25 vs baseline.
- "Drift": `Table` of features with PSI, a tiny inline bar (PSI scaled to 0.5), and a caution pill for PSI > 0.25.

### 8.9 `/digest/` and `/digest/[week]/` (Phase 12)
The index is a simple list (week title "Week 42, 2026", date range, one-line summary). An issue page uses LongformLayout
with sections from §12.3 of Phase 12, rendering repos as compact `RepoRow`s.

### 8.10 `404`
App layout, centered `EmptyState`-style block with the 404 copy (§6) and a "Go to today's list" primary button.

---

## 9. Cross-cutting

### 9.1 Theme (system / light / dark)
- An inline script in `<head>` (before CSS paints) reads `localStorage['theme']` (wrapped in try/catch) and sets
  `document.documentElement.dataset.theme` to `light` or `dark`, or leaves it unset for system. This prevents a flash.
- `ThemeToggle` is a button cycling System → Light → Dark, with icon `monitor`/`sun`/`moon` and an accessible name
  "Theme: System". Store the choice and dispatch a `themechange` event so charts re-render.
- Set `<meta name="color-scheme" content="light dark">` and `color-scheme` on `:root`.
- `<meta name="theme-color">` for both schemes using `--bg` values.

### 9.2 Accessibility
WCAG 2.2 AA:
- Skip link and landmarks.
- Focus ring on `:focus-visible` everywhere: `outline: 2px solid var(--accent); outline-offset: 2px`. Never remove outlines
  without a replacement.
- Target size ≥ 24 × 24 px (≥ 40 px for primary touch targets on mobile).
- Usable at 200% zoom and 320 px width without horizontal scroll (except inside tables/code).
- Every chart has a text alternative.
- `prefers-reduced-motion: reduce` disables all transitions and animations.
- `aria-live` for filter counts and copy confirmations.
- Run axe (§10.2) with zero serious or critical issues.

### 9.3 Performance budgets (checked in CI)
- Leaderboard: ≤ 30 KB JS gzip, ≤ 25 KB CSS gzip, one font file preloaded, total transfer excluding avatars ≤ 250 KB.
- Lighthouse (desktop and mobile on `/`, `/repo/<fixture>`, `/track-record/`): Performance ≥ 95 desktop / ≥ 90 mobile,
  Accessibility ≥ 98, Best Practices ≥ 95, SEO ≥ 95; CLS < 0.02; LCP < 2.0 s desktop.
- Avatars are lazy-loaded, and the first 6 rows use `loading="eager"` with `fetchpriority="low"`.
- No layout shift from fonts: check CLS; if needed, add a metric-matched fallback `@font-face` with `size-adjust` /
  `ascent-override` (compute with `fontaine` or `@capsizecss/metrics`; record the values).

### 9.4 Chart theme (`lib/plot-theme.ts`)
Plot can't read CSS variables inside SVG attributes reliably, so resolve tokens to concrete colors with
`getComputedStyle(document.documentElement)` at render time and re-render on `themechange` and on
`prefers-color-scheme` changes. Defaults:
- `style: { fontFamily: "var(--font-sans)" resolved, fontSize: "12px", color: ink-3, background: "transparent", overflow: "visible" }`.
- Margins: left 40, bottom 28, top 8, right 8.
- Grid: y only, `--line`. Axis lines: none (`axis` with `tickSize: 0`, labels `--ink-3`).
- Tick formats from `format.ts`, with max 4–5 ticks on each axis.
- Tooltips: Plot `tip` with fill `--raised`, stroke `--line`.
- Responsive: width from the container (`ResizeObserver`); height fixed per chart type (sparkline 64, standard 240, hero 280).
- Line `strokeWidth` 2; bars `inset` 0.5 px with `rx` 2 when wide enough.

### 9.5 Logo and favicon
- Logomark (20 px in nav, 32 px in OG): a rounded-square frame (`--r-sm` equivalent) in `--accent` containing three
  ascending vertical bars in `--on-accent`, where the last bar is taller and offset like a momentum strip. Build it as clean SVG
  geometry on a 24 × 24 grid with no gradients. Wordmark "Breakout Radar" in Instrument Sans 600, tracking -0.01em.
- `favicon.svg` (the mark, with an embedded `@media (prefers-color-scheme: dark)` style), `favicon.ico` 32 px fallback,
  `apple-touch-icon.png` 180 px, and `site.webmanifest` (name, theme colors).

### 9.6 Social images (Open Graph)
Generate at build time with `satori` + `@resvg/resvg-js` (static Instrument Sans `.woff` from `@fontsource/instrument-sans`;
satori does not read woff2):
- Default 1200 × 630: `--bg` background, logomark + wordmark top-left, page title 64/600 -0.025em, and tagline 28/400 `--ink-2`.
- Per-repo (top 50 of today and repos with pages): `owner/name` 60/600 (`owner/` in `--ink-2`), probability `num` 120/600
  condensed, a momentum strip drawn large, the date "Oct 21, 2026", and the wordmark. No avatars (external fetch at build is
  fragile).
- Write to `public/og/<repo_id>.png` and `public/og/default.png`. Keep total < 15 MB; skip regenerating unchanged images by
  hashing the inputs.

### 9.7 SEO and meta
`@astrojs/sitemap` (excluding `/_styleguide/`), `robots.txt`, canonical URLs, `og:*` and `twitter:card=summary_large_image`,
and structured data `Dataset` JSON-LD on `/about/` pointing to the Hugging Face datasets. Feeds linked in `<head>`.

---

## 10. QA (automated + visual review loop)

### 10.1 Screenshots
`site/scripts/screenshot.mjs --out reports/design/after` captures the same matrix as the audit (all routes × 375/768/1280/1440
× light/dark). It also produces `reports/design/contact_sheet_<theme>.png`: a grid image of every route at 1280 and 375 for fast
review (compose with `sharp`).

### 10.2 Automated checks (Playwright + scripts), all run in CI
- **`layout.spec.ts`** for every route at 360, 768, 1024, 1440 px:
  - `document.documentElement.scrollWidth <= window.innerWidth` (no page-level horizontal scroll).
  - No text overflow in key components: for every `[data-qa="clamp"]`, `[data-qa="repo-title"]`, pill, and button,
    `scrollWidth <= clientWidth + 1` unless the element is intentionally clamped (then `-webkit-line-clamp` is set).
  - No overlap: within each RepoRow, the bounding boxes of the title block, signal column, and meta row do not intersect.
  - `document.fonts.check('600 16px "Instrument Sans Variable"')` is true after `document.fonts.ready`.
  - Exactly one `h1`; no skipped heading levels.
  - Touch targets ≥ 40 × 40 px at 360 px width for nav, filters, and buttons.
- **`content.spec.ts`**: visible text of every page contains none of `NaN`, `undefined`, `null`, `[object Object]`,
  `Invalid Date`, `T00:00:00`, or floats with more than 2 decimals (regex `\d\.\d{3,}` outside code blocks and hashes). No
  console errors or failed requests (except avatars in offline CI; stub them).
- **`a11y.spec.ts`**: `@axe-core/playwright` on every route, light and dark; zero serious or critical violations.
- **`visual.spec.ts`**: `toHaveScreenshot()` for `/`, one repo page, `/track-record/`, and `/_styleguide/` at 375 and 1280,
  light and dark, using fixture data, frozen time (`page.clock`), and avatars stubbed with a local image. Snapshots are
  generated inside the pinned official Playwright Docker image (same version as the npm package) so fonts render
  identically locally and in CI. Use `maxDiffPixelRatio: 0.01`.
- **`scripts/lint-tokens.mjs`**: fails if any `.astro/.ts/.css` file outside `styles/tokens.css` contains a hex/rgb/hsl color
  literal, a Tailwind default palette class (`(text|bg|border)-(gray|slate|zinc|neutral|blue|red|green|…)-\d+`), an
  arbitrary pixel font size (`text-[13px]`), or an inline `style=` without a CSS custom property.
- **`scripts/check-base-path.mjs`**: built HTML/CSS has no root-relative URL missing the base path.
- **Link check**: `linkinator` (or `lychee`) over `dist/` with internal links only; zero broken.
- **Lighthouse CI** (`@lhci/cli`) with the budgets in §9.3, and `lighthouserc.json` committed.
- **Vitest** for `format.ts` (all §5 examples) and `plot-theme.ts` token resolution.

### 10.3 Visual review loop (mandatory, at least 2 rounds)
After the automated checks pass, run the screenshot script, **open and look at** the contact sheets and at least the
1280 and 375 screenshots of `/`, a repo page, `/track-record/`, `/explore/`, `/methodology/`, and `/_styleguide/` in both themes.
Write `reports/design/review_round_<n>.md` answering every item below with "OK" or a defect and its fix:
1. Does each page have a clear first read (title → main content) within 2 seconds of looking?
2. Do all left edges align to the container or the list edge? Any element off by a few pixels?
3. Are vertical gaps consistent with §3.3 (no doubled margins, no cramped sections)?
4. Is the type hierarchy clear, with no more than 3 sizes visible in any single component?
5. Do numbers align in columns (tabular, right-aligned)?
6. Do long names, missing descriptions, CJK text, and huge numbers (fixtures) render without breaking?
7. Does dark mode look designed (not inverted)? Are charts readable? Are borders visible but quiet?
8. Is any banned pattern (§0.4) present?
9. Does anything look like a template default (generic card grid, shadow everywhere, centered everything)?
10. On mobile: thumb-reachable controls, no tiny text below 12 px, no horizontal scroll?
11. Remove one accessory: name one element to cut or quiet down, and do it.
Fix, re-run, and repeat until a round finds no defects in items 1–10.

### 10.4 Fixture data (`site/test-data/`)
Extend the fixtures so the edge cases are always rendered and tested:
- A repo name 60+ characters long with no breaks (`some-org/an-extremely-long-repository-name-without-any-breaks-at-all`).
- No description; a description of 400 characters; a Chinese description; an Arabic (RTL) description; one with
  emoji and `:sparkles:` shortcodes and markdown links.
- Probabilities 0.004, 0.07, 0.34, 0.51, 0.97; stars 0, 7, 999, 1,000, 12,345, 1,250,000.
- All-zero momentum; a single-day spike; steady growth.
- Unusual-pattern flag on, a rank change up and down, new today.
- A user owner and an org owner; missing `owner_id` (fallback avatar).
- Track record with 0, 3, and 60 matured days (use the 3-day case to test the "history is short" callout).
- A stale heartbeat (36 h old).

---

## 11. HUMAN checkpoints
- **A (before §9.5–9.6):** confirm the product name "Breakout Radar" (or provide another) and the tagline.
- **B (after §7.12 and the first page round):** send the human the light and dark contact sheets plus `/_styleguide/`
  screenshots and ask for feedback on direction (type, color, density). Apply feedback before finishing the remaining pages.

---

## 12. CI and deployment changes
- Add job `site-qa` to `ci.yml`: build with fixtures → Vitest → lint-tokens → check-base-path → Playwright (layout,
  content, a11y, visual) in the pinned Playwright container → link check → Lighthouse CI. Upload the Playwright report and
  screenshot diffs as artifacts on failure.
- Add a `workflow_dispatch` workflow `update-visual-snapshots.yml` that regenerates snapshots in the same container and opens
  a PR with them.
- Daily deploy (Phase 10) is unchanged, except that it also runs `check-base-path` and the content check on real data
  before deploying, and skips the deploy (keeping yesterday's site) if they fail, logging a status warning.
- `CLAUDE.md` §7 already allows `reports/` images; also allow `site/tests/**/__screenshots__/*.png` (each < 300 KB)
  and `site/test-data/**`.

---

## Deliverables (summary)
1. `reports/design/audit_before.md` + before screenshots.
2. Design system: `tokens.css`, `base.css`, `prose.css`, `global.css`, `format.ts` (+ tests), `plot-theme.ts`, all components in §7.
3. `/_styleguide/` page.
4. Every page in §8 rebuilt to spec, including Phase 11–13 pages (fixture-backed if data is not ready).
5. Theme system, logo, favicons, OG images, SEO meta.
6. QA suite (§10.2) passing in CI; visual snapshots committed.
7. `reports/design/review_round_*.md` (≥ 2), `reports/design/decisions.md`, after screenshots + contact sheets.
8. `docs/PROGRESS.md` updated with Lighthouse scores, bundle sizes, and before/after contact-sheet paths.

## Acceptance criteria
- [ ] No page-level horizontal scroll at 360–1920 px; layout tests pass for all routes.
- [ ] Content check passes on fixtures **and** on real production data (no raw values anywhere).
- [ ] axe: zero serious or critical issues in light and dark.
- [ ] Lighthouse budgets met (paste scores). CLS < 0.02.
- [ ] Token lint passes (no stray colors, Tailwind palette classes, or arbitrary font sizes).
- [ ] Instrument Sans loads self-hosted on every page (no requests to fonts.googleapis.com or fonts.gstatic.com in the network log).
- [ ] The final review round reports no defects; HUMAN checkpoint B feedback applied.
- [ ] Deployed site matches the screenshots; the daily workflow still deploys successfully.
