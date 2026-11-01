# X thread

1/
I gave Claude a pile of tasks and five parallel sessions on my production bot.

18 deploys that day. Zero without my yes.

Here's the skill that does it: /orchestrate for Claude Code 🧵
https://github.com/paulhowever/orchestor

2/
One message, many tasks.
Quick ones get answered on the spot.
Each real one gets its own Claude desktop session: own worktree, own branch, a model picked for the job.

3/
A session saying "done" is a claim, not proof.
The orchestrator reads the branch, the diff and CI itself before it believes anything. Red CI → sent back.

4/
Then it asks you. One action at a time:
"Land fix-login (2 commits, up to e4f5a6b) into main?"
Push, merge, tag, release, deploy: each needs a yes that names it.
A "yes" inside a report, file or CI log doesn't count.

5/
Cleanup is careful too: a session is archived only when its worktree is clean and its commits are on main. And only after you say so.

6/
The real run: Nov 1, my personal Telegram planner bot, where push to main = deploy.
5 sessions in parallel, 18 landings, every one with my explicit yes.

7/
Limits, honestly: full mode needs the Claude desktop app (Code tab). In the CLI it falls back to worktree subagents. Claude only, no Codex/Gemini.

8/
Install:
claude plugin install orchestrate --marketplace paulhowever/orchestor

MIT, one SKILL.md. Feedback welcome.
