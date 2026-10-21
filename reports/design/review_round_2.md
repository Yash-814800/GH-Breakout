# Review round 2

Reviewed the regenerated screenshots (same set, after the round 1 fixes) with extra attention to 375 px in both themes.

| # | Question | Result |
|---|---|---|
| 1 | Clear first read within 2 s? | OK. |
| 2 | Left edges aligned? | OK. |
| 3 | Vertical gaps? | OK. |
| 4 | At most 3 type sizes per component? | OK. |
| 5 | Numbers aligned? | OK. |
| 6 | Long names, missing descriptions, CJK, huge numbers? | OK in rows, repo header, OG cards (the OG card for a 60-character name wraps cleanly after fixing a satori box-sizing issue that had cut the percentage off). |
| 7 | Dark mode designed? | OK. |
| 8 | Banned patterns? | None. |
| 9 | Template defaults? | OK. |
| 10 | Mobile? | Defect: on `/status/` at 375 px the left axis labels of the pipeline chart were clipped ("export site data"). **Fix:** left margin is `clamp(112, 30% of width, 170)` px. |
| 11 | One element to remove | The "Model 2026…" pill under the Methodology title repeated the model version already shown in the footer and on the model card link next to it. Removed the pill. |
