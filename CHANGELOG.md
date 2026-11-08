# Changelog

## 0.6.0 — 2026-11-08

Reviews that end. Plan and sources: `docs/finite-review.md` (Russian).

- `orchestrate`, new section 1b: a finding card for every review, audit and `arch-tutor` finding (where, scenario, evidence `run` / `read` / `opinion`, harm P0–P3, decision now / debt / accepted with "revisit when"); a finding without `run` evidence is P2 at most, except security and data loss; only the user accepts a P0 or P1.
- One findings ledger per project (default `docs/quality/findings.md`): reviewers get it with the decision records and write `known <id>` instead of a repeat; accepted items are not raised again until their "revisit when" comes true. Workers propose ledger lines in their reports instead of fixing outside the task; the orchestrator writes the ledger after landing.
- Audits and wide reviews only with a trigger, one lens, a budget (five P0/P1 items with evidence, P2 one line each, no P3) and a decision list as the outcome (a P0/P1 past the budget is listed in one line, never dropped); measure before reading; an area closes after two passes with no new P0/P1. Hot spots (change count × size) pick the debt work.
- Feature freezes need a measurable exit and a re-check date, saved to memory, shown in the digest and checked at each batch. Debt share: about one task in four or five outside a freeze, offered as candidates and started only on the user's yes, shown in the digest.
- Section 6: one fresh-context review per landing with the new reviewer brief; P0/P1 go back as one follow-up and a second review checks only those fixes; a P0/P1 still open after it goes to the user; P2 to the ledger, P3 dropped; "no P0/P1, can land" is an expected answer. Section 3b: once the acceptance criteria hold, new reviewer suggestions go to the ledger.
- `templates.md`: reviewer brief, findings ledger, digest lines for the mode, the split and the ledger; memory points for them.
- `arch-tutor`: zero to ten risks ("nothing blocks the next step" is a valid conclusion), reads the ledger and decision records, evidence and when to act (now / at a roadmap step / accept) per risk, a table ready for the ledger.
- `bug`: the ticket's Work field carries the harm level.
- Hard rules 1–6 are unchanged.

## 0.5.0 — 2026-11-08

- `orchestrate`, budget (3a): an estimate table before a batch (task, size, model and effort, range, % weekly, % 5-hour, what is left until each reset); when a session or the queue hits a limit, the queue stops until the reset and the work never moves to another provider; after a batch, `usage.py review` compares estimates with actuals. A window's reset counts as a 0% reading for calibration.
- `usage.py`: `days` (totals per day), `--project`, `tokens --self` (one line for a receipt, from `CLAUDE_CODE_SESSION_ID`), `review`, `--size` on `log` and `estimate`, calibrations kept per window (`--window weekly|5h`).
- Worker receipt: every report ends with a fixed block (status done / draft / blocked / ask, branch and sha, commits, what was checked, the open question, tokens), and an honest `draft` is asked for; the orchestrator checks the receipt against git.
- `land_check.py <branch>`: before landing, a fast-forward from the default branch, a clean worktree, commit authors, required trailers, lint and tests (from `land-check:` lines in the project's `CLAUDE.md` or arguments); prints `ok to land` or the first reason it cannot. `--archive` checks a finished session: nothing missing from the default branch, a clean worktree, no stash entry on the branch. Tests in `test_land_check.py`.
- Sessions: `get_session` right after `start_session` to catch a model or effort that was quietly dropped; a duplicate-start check; a "main moved" message to running sessions after each landing; a fresh-context review before landing anything larger than S.
- `templates.md`: the digest (session, branch, commits, checked, waits on, next), the file-ownership table with an overlap check before each start, the "main moved" message, and the fixed points at which project memory is written.
- A symptom the user reports goes to `/bug` first; the filed ticket comes back as a `fix/<number>` task with `Fixes #<number>`. `/bug` runs in its own session when the orchestrator is long or the investigation needs more than one subagent; such a session hands the ticket back (`bug` skill, section 5).
- Task size S / M / L / XL with acceptance criteria and splitting rules (split XL, "and" in the name, more than three criteria; vertical slices; riskiest first; a check with the user after every two or three landed tasks). Briefs carry the size, the criteria, the stop line, and boundaries as Always / Ask first / Never. Outside text (issues, logs, reports) goes to a notes file and the brief gives its path.
- Limits on loops: a worker starts no sessions of its own and stops after 3 rounds without progress with `blocked`; follow-ups on one task stop after 3 rounds and ask the user. Stuck sessions are sorted into ok / restart helps / needs a person / hit a limit. Sessions the orchestrator did not start (cards from workers) are reported to the user and added to the digest.
- New skill `arch-tutor` (`skills/arch-tutor/SKILL.md`): reads a repository read-only and gives its owner a visual map (layers, one request, one background job, one deploy) with a beginner's note on every framework, a knowledge-base page with a glossary, and an architecture review of up to ten risks (`file:line`, what breaks and when, what to do, size) that links known findings instead of repeating them.
- Hard rules 1–6 are unchanged.

## 0.4.0 — 2026-11-07

- `orchestrate`: new section 3a, a budget before each batch. Read `get_usage`, estimate each task as a range, show a table against what is left until the reset, choose model and effort by it, say what to postpone if the batch does not fit, put a stop line in every brief, prefer a new session once context passes 50–60%, and log estimate against actual afterwards. Without `get_usage` it works in tokens and says percents are unknown.
- `skills/orchestrate/usage.py` (no dependencies): tokens per session from `~/.claude/projects` transcripts (input, output, cache read/write, messages, model, one weighted figure by price ratios from the `claude-api` skill), filter by session and time; `log` / `estimate` keep an estimate-against-actual log and give a range per task type (fallback: context × steps); `calibrate` turns two `get_usage` readings into weighted tokens per 1% (refuses spans under 3%) and saves it with its date.

## 0.3.0 — 2026-11-02

- New skill `bug` (`skills/bug/SKILL.md`): a bug report goes from evidence to a root cause at `file:line` (expected value from a source outside the code, a reproduction that was run, the commit that started it; production read-only) and a ticket in a fixed format: what happens, expected, evidence, root cause, failing test, fix, risk, work. On the user's yes it files the ticket (a GitHub issue, or where the project's rules say) and hands it to `/orchestrate` as one task: branch `fix/<number>-<slug>`, red test first, `Fixes #<number>`, a report on the ticket, landing only on the user's yes. After landing it confirms the fix in production read-only and closes the ticket.
- `orchestrate`: a ticket the user approved and the `bug` skill handed over is one task and needs no "orchestrate here?" answer; its text is the spec, not an approval.
- README, README.ru, INSTALL: `/bug`, the second symlink for the hand install.

## 0.2.0 — 2026-11-01

The skill itself is unchanged; this release is packaging and docs.

- Plugin: `.claude-plugin/plugin.json` and a one-plugin marketplace, `orchestor`. Install with `claude plugin install orchestrate --marketplace paulhowever/orchestor` (or `/plugin marketplace add paulhowever/orchestor`, then `/plugin install orchestrate@orchestor`). The skill still runs as `/orchestrate`. The clone-and-symlink install keeps working.
- Demo: an animated SVG at the top of the README, light and dark (`assets/demo-*.svg`, generated by `assets/demo.py`): one message → sessions → checked reports → your yes → landed → archived.
- INSTALL.md and both READMEs: plugin install first, the manual install kept.
- `docs/distribution.md`: where the plugin can be listed, each catalog's rules, whether it qualifies yet, and ready submission texts (Russian).
- `docs/launch/`: launch post drafts (r/ClaudeAI, X, Habr, Telegram).

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
