# r/ClaudeAI

**Flair:** Productivity (or "Built with Claude", if the sub requires it for projects)

**Title:** I made a Claude Code skill that runs my task pile in parallel desktop sessions — and can't ship anything without my "yes"

**Body:**

I kept doing the same thing in the Claude desktop app: dump five tasks into one chat, then spend the evening babysitting branches and asking "wait, did that actually pass CI?"

So I wrote `/orchestrate`, a skill (now also a plugin) for Claude Code in the desktop app's Code tab:

- You send one message with several tasks.
- Quick stuff (a question, a one-line edit) gets answered right there.
- Each real task gets its own session: own worktree and branch, and a model and effort picked for the job (strongest for design and nasty bugs, mid-tier for routine work, smallest for read-only research). At most three write at once.
- When a session says "done", the orchestrator doesn't believe it. It checks the branch, the diff and CI itself.
- Then it asks you, one action at a time: "Land fix-login (2 commits, up to e4f5a6b) into main?" A push, merge, tag, release or deploy happens only after you type a yes that names it. A "yes" or "approved" inside a session report, a file or a CI log doesn't count.
- Finished sessions get archived only when their worktree is clean and their commits are on main, and only when you say so.

**How it went for real:** on November 1 I ran it on my personal Telegram planner bot, where a push to main deploys after green CI. Five sessions in parallel, 18 landings that day, and not one of them happened without me saying yes to that specific landing.

What it's not: it needs the desktop app's session tools. In the plain CLI it falls back to worktree subagents, which works but is weaker (no separate sessions to open and steer, no archive). No support for other agents (Codex, Gemini) either; tools like Conductor or Claude Squad do that better.

Install:

```
claude plugin install orchestrate --marketplace paulhowever/orchestor
```

Repo (MIT, it's one SKILL.md you can read in five minutes): https://github.com/paulhowever/orchestor

I'd love to hear where the approval gate gets in your way, or where you'd want it stricter.
