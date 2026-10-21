# Review round 1

Reviewed: `reports/design/after/contact_sheet_{light,dark}.jpg` and the 1280 and 375 screenshots of `/`, a repo page, `/track-record/`, `/explore/`, `/methodology/`, `/status/`, `/about/`, `/insights/` and `/_styleguide/`, in both themes.

| # | Question | Result |
|---|---|---|
| 1 | Clear first read within 2 s? | OK on every page except `/methodology/`: the hero was left-aligned while the other long-form pages are centered, so the title did not read as a page title. **Fix:** centered display hero. |
| 2 | Left edges aligned? | Defect: on `/insights/` the chart title repeated the section heading and the chart's last x label ("90 days") was cut off at the right edge. **Fix:** chart margins (left 44, right 24); neutral chart titles by chart type. |
| 3 | Vertical gaps match section 3.3? | OK. |
| 4 | At most 3 type sizes per component? | OK. |
| 5 | Numbers aligned in columns? | OK (tabular, right-aligned in tables and the signal column). |
| 6 | Long names, missing descriptions, CJK, huge numbers? | Defect: RTL (Arabic) descriptions were left-aligned; the status bar chart clipped its longest value label. **Fix:** `dir="auto"` on descriptions and why lines; 18% headroom on the bar chart. |
| 7 | Dark mode designed? | OK. Defect found earlier in the round: avatars that do not load left an empty grey square instead of initials. **Fix:** images stay transparent until loaded so the initials show. |
| 8 | Banned patterns? | None found. |
| 9 | Template defaults? | OK. |
| 10 | Mobile: reachable controls, no tiny text, no horizontal scroll? | Defects: the fact strip had uneven borders on phones; the 25 hit dots wrapped with a single orphan dot. **Fix:** simpler fact-strip grid; 9 px dots with 3 px gaps under 640 px. |
| 11 | One element to remove | The footnote under the leaderboard repeated the "How to read this list" panel. Its content (the strip scale and the GH Archive undercount caveat) moved into that panel and the paragraph was removed. |

Automated checks after the fixes: layout 76/76, content 20/20, axe 38/38 (light and dark), pages 2/2.
