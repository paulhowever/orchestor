# Install

## Requirements

- **Claude Code in the Claude desktop app, Code tab.** The skill starts and archives sessions with the app's session tools (`start_session`, `archive_session`, `list_sessions`, `clear_session`, `mark_chapter`). They exist only there.
- **A git repository** for each project you orchestrate. Sessions work in their own worktrees and branches.
- Plain CLI, IDE extensions and claude.ai/code have no session tools. The skill still loads there: it falls back to subagents or to doing the work in one session, and says so.

## Install

User-wide (every project):

```bash
git clone https://github.com/paulhowever/orchestor.git ~/orchestor
mkdir -p ~/.claude/skills
ln -s ~/orchestor/skills/orchestrate ~/.claude/skills/orchestrate
```

The symlink keeps the skill in step with the clone. To copy instead: `cp -R ~/orchestor/skills/orchestrate ~/.claude/skills/`.

One project only: put the folder at `<project>/.claude/skills/orchestrate/` instead.

Optional: paste [`CLAUDE.md.snippet`](CLAUDE.md.snippet) into `~/.claude/CLAUDE.md`. With it, Claude asks once per project whether to orchestrate when you send several tasks in one message, and remembers the answer. Without it, the skill runs when you type `/orchestrate` (or when Claude matches a batch of tasks to the skill's description).

## Check

Open a new session in the Code tab (skills load at session start) and type `/orchestrate`. Claude should load the skill and either ask whether to orchestrate in this project or start splitting your message. If `/orchestrate` is not offered, check that `~/.claude/skills/orchestrate/SKILL.md` exists (`ls -L` follows the symlink).

## Update

```bash
git -C ~/orchestor pull
```

With the symlink, new sessions pick it up. With a copy, copy the folder again. [CHANGELOG.md](CHANGELOG.md) says what changed.

## Second machine

Repeat the clone and the symlink on the other machine, and `git pull` on both when you update. If you sync `~/.claude` some other way (a dotfiles repo, iCloud), sync the clone too, or use a copy instead of the symlink there. The per-project answer ("orchestrate here: yes/no") lives in Claude Code's project memory on each machine, so each machine asks once.

## Uninstall

```bash
rm -r ~/.claude/skills/orchestrate
```

(`rm` without `-r` for the symlink.) Remove the snippet from `~/.claude/CLAUDE.md` if you added it.
