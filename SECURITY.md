# Security policy

## Reporting a vulnerability

Please report security problems **privately** through GitHub's private vulnerability reporting:
<https://github.com/Yash-814800/GH-Breakout/security/advisories/new>. Do not open a public issue for a
vulnerability. You can expect a first reply within a week.

## What is in scope

- The code in this repository (the `breakout` Python package, the GitHub Actions workflows, the Astro site).
- Secrets handling: the project uses a Hugging Face write token and a GitHub token with no scopes, both
  only as GitHub Actions secrets and in a git-ignored local `.env`. If you find a token in the history,
  the logs or a published file, report it the same way.

## What is not a vulnerability

- A repository appearing on, or missing from, the leaderboard. Owners can ask to be removed through an
  [issue](https://github.com/Yash-814800/GH-Breakout/issues/new?template=review-request.md); the list
  of hidden repositories is `config/hidden_repos.yaml`.
- The data itself: it comes from public sources (GH Archive, the public GitHub API, Hacker News).

## How the project protects itself

- Every workflow declares minimal `permissions`; third-party actions are pinned to commit SHAs and updated
  by Dependabot (Python, npm and Actions).
- `gitleaks` runs as a pre-commit hook and over the full history during the final audit
  (`reports/final_audit.md`).
- No secret is printed: tokens are compared or validated without being echoed.
