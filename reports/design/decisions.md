# Design decisions and deviations (Phase 14)

Changes to the original front-end redesign brief, and choices it left open, with the reason.

## Fonts and type
- **Font axes.** `@fontsource-variable/instrument-sans/wdth.css` exists, so the full-axes file is used. The `@font-face` rules declare `font-weight: 400 700` and `font-stretch: 75% 100%`, matching the expected ranges. `num-lg` and `num-xl` use `font-stretch: 87.5%`.
- **Token name.** The phase file's `@theme inline { --font-sans: var(--font-sans) }` would reference itself, so the family lives in `--font-ui` and Tailwind's `--font-sans` points to it.
- **Fallback font.** Metrics from `@capsizecss/metrics` (Instrument Sans against Arial): `size-adjust` 102.74%, `ascent-override` 94.42%, `descent-override` 24.33%, `line-gap-override` 0%. Measured CLS is 0.000 on all three audited pages, desktop and mobile.
- **OG images use static Instrument Sans.** satori reads neither woff2 nor variable axes, so the large percentage is not condensed there (it is condensed on the site).

## Tokens and Tailwind
- Tailwind's default palette is switched off with `@theme { --color-*: initial }`, so `text-gray-500` cannot compile. `scripts/lint-tokens.mjs` also rejects it.
- Four tokens were added to the table in the phase file, all outside the semantic palette: `--scrim` (mobile menu backdrop), `--paper` and `--paper-ink` (matplotlib figures are drawn for a white canvas, so they sit on a white card in dark mode too), and `--shadow-seg` (the selected segment's 1 px shadow).
- `<meta name="theme-color">` cannot use CSS variables, so its two `--bg` values are literals; the lint skips exactly that line.
- Language dots use GitHub's own colors from `linguist-languages` (692 languages with a color), generated into `src/lib/languages.json`. They are data, not UI colors.

## Components
- **Icons.** `lucide-static` icon nodes rendered by `Icon.astro`. Lucide 1.x has no brand icons, so the GitHub mark is a hand-drawn path in the same component.
- **Tooltip.** Popover API plus JavaScript positioning. CSS anchor positioning is not available in every browser, and the phase file allows a fallback; the fallback is the only path, to keep one behavior.
- **Rank change.** The exporter publishes `up | down | same | new` without the number of places, so the pill shows an arrow without a number ("Moved up" for screen readers).
- **Rail.** The "How to read this list" panel does not stick (the phase file's optional rule) because a sticky first panel would scroll over the others. The repo page aside does stick at `lg`.
- **Style guide route.** Astro ignores files starting with `_`, so `/_styleguide/` is injected with a small integration in `astro.config.mjs`.
- **Digest.** Phase 12 has no data yet. The layout reads a provisional shape (`digests/index.json`, `digests/<week>.json`, defined in `src/lib/types.ts`) and shows an empty state when it is missing. Phase 12 can change the shape; the zod schema will fail the build with a clear message if it does.
- **Badge panel and RSS links** are omitted until Phase 12 produces badges and `feed.xml`. The footer and the "Follow the list" panel check for `public/feed.xml`.

## Data shown, and what was left out on purpose
- **Track-record sentence** is produced by `breakout publish site-data` (`summary.headline`), as the phase file asks; the template only displays it.
- **Calibration diagram** is drawn only when bins have a non-zero count. The Phase 10 exporter fills `realized_avg` with the predicted value when any list has matured and sets `count` to 0, which would draw a perfect diagonal that was never measured. This should be fixed in the exporter (reported in `docs/PROGRESS.md`).
- **dbt test count** is not shown on the status page. The exporter hardcodes `tests_passing: 162` instead of reading dbt results.
- **Per-type ingest freshness** (§8.8) is rendered when `rows_ingested_last_14d` has rows; the exporter currently writes an empty list, so the page says the counts are not published yet.
- **Metric decimals.** PR-AUC and ROC-AUC are shown with three or four decimals (0.108, 0.1081), as is usual for these metrics. The content test allows this on `/methodology/` and `/status/` only.
- **Methodology numbers** are read at build time from `reports/metrics/model_cv.json` and `baseline.json`. The Phase 10 page had hand-typed values, and two were wrong (baseline 2 and 3 ROC-AUC were 0.782 and 0.795; the reports say 0.741 and 0.711).

## Behavior
- **Filters** write `?new=1&lang=Rust&hide=unusual&sort=gain|stars|newest` (`new` instead of the phase file's `new=1` spelling is the same; `sort=stars7d` became `sort=gain` because the sort uses GitHub's weekly gain, not the event count).
- **DuckDB-WASM** is self-hosted (the `eh` bundle, 34 MB, downloaded only on `/explore/` and `/backtest/`). The Phase 10 page loaded it from jsDelivr. DuckDB still fetches its Parquet extension from `extensions.duckdb.org` at runtime (no cookies, no user data); that cannot be self-hosted without repackaging the extension.
- **Backtest rows** clone a server-rendered `RepoRow` template, so the CSS and markup are the same as on the leaderboard.
- **Chart text alternatives.** Plot's SVG is marked `aria-hidden` and each `ChartFigure` carries an sr-only summary, because Plot writes `aria-label` onto bare `<g>` elements, which axe rejects.

## QA
- **Visual snapshots** are viewport-sized (1280 x 900 and 375 x 900), not full page, so each stays under 300 KB. They are generated with `mcr.microsoft.com/playwright:v1.64.1-noble` through Podman locally and the same image in CI.
- **`check-base-paths.mjs`** keeps its Phase 10 name and now also scans built CSS for root-relative `url()`.
- **Vitest** runs only `src/**/*.test.ts`; Playwright specs are separate.
- **Lighthouse** runs against the fixture build; scores are in `docs/PROGRESS.md`.
