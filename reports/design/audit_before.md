# Audit of the Phase 10 site (before Phase 14)

Method: `site/scripts/screenshot.mjs` (72 screenshots, `reports/design/before/`) plus a DOM probe at 375/768/1280/1440 px
on every route (page width, h1 count, fonts, raw-value regex, failed requests). Data: real `public/data` of 2026-10-21.
Tall pages are cropped to 6,000 px / re-compressed to stay under 500 KB per file.

## Root-cause checklist (§1.4)

| Check | Result |
|---|---|
| Global CSS missing on some pages | OK: all 9 routes use `Layout.astro`, which imports `global.css`. Weak point: no shared layout tiers (app vs long-form). |
| Base-path 404s | OK: 0 failed requests, 0 un-prefixed URLs (`check-base-paths.mjs`). |
| Web font not loading | **Broken**: no web font exists; `font-family` is the system stack (`-apple-system, BlinkMacSystemFont, "Segoe UI"...`). Renders differently per OS. |
| Tables/names widening the page | **Broken**: at 375 px every route is wider than the viewport (392 px; `/track-record/` 409 px). |
| Unstyled markdown pages | Methodology/About use hand-written CSS, no shared prose rules; no TOC. |
| Raw floats, ISO dates, units | **Broken**: see list below. |
| Charts fixed in pixels / dark mode | Charts use hard-coded colors; see list. |

## Defects

| # | Route | Width | Class | Defect |
|---|---|---|---|---|
| 1 | all | 375 | broken | Page-level horizontal scroll: `scrollWidth` 392 (409 on `/track-record/`). Cause: 8-column table in a non-scrolling wrapper; header nav not collapsing. |
| 2 | `/` | all | broken | "gain: n/a yet" and "daily" fragments print on every row; the cell wraps into 3 lines ("gain:", "n/a", "yet"). |
| 3 | `/` | all | broken | "Age" column wraps "13 / d" onto two lines. |
| 4 | `/` | all | broken | "Why flagged" cell truncated to "Flagged because 60..." and shows nothing useful; the full explanation is only on the detail page. |
| 5 | `/` | all | broken | Rows 1-2 of the real data show a bare repo with no description ("Gathin23/cleanyourtv" has one; "google-research/harness2" shows none and no "No description" fallback). |
| 6 | `/repo/*` | all | broken | Raw float `0.8363` on the page (raw score / SHAP value). Repo name shown as `repo_id=1024717607` for repos without metadata (fixture); link `github.com/repo_id=...` is dead. |
| 7 | `/backtest/` | all | broken | ISO timestamps `2018-02-05T00:00:00` visible in the date list. |
| 8 | `/methodology/`, `/status/` | all | broken | Unrounded metrics `0.1081`, `0.1016`, `0.883`, `0.158` printed as raw decimals. |
| 9 | all | all | inconsistent | Three different heading scales and spacing systems between pages; each page defines its own container width. |
| 10 | all | all | inconsistent | Emoji used as icons and a rocket emoji favicon; "Honest probability" callout uses an info glyph in a different style from the rest. |
| 11 | `/` | all | inconsistent | Probability colored green/purple in the table; the rest of the site uses neutral ink. Rank column uses a star glyph next to every rank. |
| 12 | all | 375 | unpolished | Header shows the full desktop nav; no menu pattern. |
| 13 | `/` | all | unpolished | Default browser `<select>` and checkbox look, labels "Search:", "Language:", "Min Probability:" inline in one row. |
| 14 | all | dark | unpolished | Dark mode is an inversion: borders and badges lose contrast, the Observable Plot charts keep light backgrounds on `/track-record/`. |
| 15 | all | all | unpolished | Middle-dot meta strings and a monospace badge ("Daily ML Leaderboard", "Data through: 2026-10-20") in tracked-out caps. Banned by §0.4. |
| 16 | all | all | unpolished | No favicon beyond an emoji data-URI, no OG image, no theme toggle, no skip link. |
| 17 | `/` | all | unpolished | Probability tooltip is the plain `title` attribute; odds shown as "~1 in 3" with a tilde and no sentence. |
| 18 | `/explore/` | all | unpolished | Plain `<textarea>` editor with no highlighting; results table has no sticky header, unformatted numbers/timestamps. |
| 19 | all | all | unpolished | Heading `h1` count is 1 everywhere (OK) but heading levels skip (h1 to h4) on `/repo/*`. |

Passing already: exactly one `h1` per page; no failed network requests; base path correct; no CLS from fonts (because none load).

## Consequences for the redesign

Defects 1-8 are the acceptance-critical ones: the new layouts must use `minmax(0, 1fr)` grids and in-column scrolling tables,
every value goes through `lib/format.ts`, repos without metadata need a display name rule (the real `repo_name` is
`owner/name` from the GitHub API when known, otherwise the page falls back to `Repo #id` and hides the GitHub link).
