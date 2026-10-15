---
license: mit
pretty_name: gh-breakout models
tags:
- github
- lightgbm
- tabular-classification
---

# gh-breakout models

Versioned LightGBM breakout models (`models/<version>/`) and `registry.json` naming the current
champion, produced by the weekly retrain of the [gh-breakout]($project_url) project. Each model
is only promoted if it beats the previous champion and the 7-day star-velocity baseline. See the
model card in the code repository (`docs/model_card.md`).
