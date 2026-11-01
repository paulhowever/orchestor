# Changelog

## 0.1.1 — 2026-11-01

Docs only; the skill is unchanged.

- README: what the skill does, a sample exchange, a one-line install, requirements and the fallback, a comparison with alternatives, FAQ.
- `README.ru.md`: a short Russian version.
- `assets/`: banner and how-it-works diagram as SVG, light and dark.
- `docs/market.md`: research on alternatives and positioning (Russian).

## 0.1.0 — 2026-11-01

First public version of the `orchestrate` skill.

- Splits one message into quick things done inline and real tasks, each in its own Claude desktop session with its own worktree and branch, and a model and effort picked per task.
- Hard rules: landing (push, merge, deploy, release, migration) needs the user's yes for that action; approvals never travel through report text; reports and files are data; no secrets in briefs, memory or the digest; sessions only in the repos the user named.
- Plans file ownership, branches from a fresh default branch, caps writing sessions at 3, lands one session at a time with checks re-run after rebase.
- Archives a session only after checking that its worktree is clean and its commits are merged, and only with the user's yes.
- Keeps a private digest of the batch and can clear the orchestrator session once memory holds the queue.
- Falls back to worktree subagents, or to one session, when the desktop session tools are missing.
- Optional `CLAUDE.md.snippet`: ask once per project whether to orchestrate.
