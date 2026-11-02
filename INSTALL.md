# Install

## Requirements

- **Claude Code in the Claude desktop app, Code tab.** The skill starts and archives sessions with the app's session tools (`start_session`, `archive_session`, `list_sessions`, `clear_session`, `mark_chapter`). They exist only there.
- **A git repository** for each project you orchestrate. Sessions work in their own worktrees and branches.
- Plain CLI, IDE extensions and claude.ai/code have no session tools. The skill still loads there: it falls back to subagents or to doing the work in one session, and says so.

## Install as a plugin (recommended)

From a terminal (Claude Code 2.1.292 or later):

```bash
claude plugin install orchestrate --marketplace paulhowever/orchestor
```

Or inside a Claude Code session (2.1.275 or later):

```
/plugin install orchestrate --marketplace paulhowever/orchestor
```

On older versions, in two steps: `/plugin marketplace add paulhowever/orchestor`, then `/plugin install orchestrate@orchestor` (or `claude plugin marketplace add …` / `claude plugin install …` in a terminal).

The plugin lands in `~/.claude`, which the desktop app's Code tab shares with the CLI, so a terminal install is enough. The skills run as `/orchestrate` and `/bug` (full plugin names `/orchestrate:orchestrate` and `/orchestrate:bug`, if another command already uses the short name).

**Updates.** The plugin carries a version. Run `claude plugin update orchestrate@orchestor` (or `/plugin` → Marketplaces → update), or turn on auto-update for the `orchestor` marketplace in `/plugin`. [CHANGELOG.md](CHANGELOG.md) says what changed.

**Uninstall.** `claude plugin uninstall orchestrate@orchestor`, and `claude plugin marketplace remove orchestor` to forget the marketplace.

## Install by hand (clone + symlink)

Use this if you want to read or edit the skill in place, or you don't use plugins. Pick one way: with both the plugin and the hand-installed skill you get two copies of the same skill.

User-wide (every project):

```bash
git clone https://github.com/paulhowever/orchestor.git ~/orchestor
mkdir -p ~/.claude/skills
ln -s ~/orchestor/skills/orchestrate ~/.claude/skills/orchestrate
ln -s ~/orchestor/skills/bug ~/.claude/skills/bug
```

The `bug` skill is optional; skip its symlink if you only want `/orchestrate`. The symlink keeps the skill in step with the clone. To copy instead: `cp -R ~/orchestor/skills/orchestrate ~/orchestor/skills/bug ~/.claude/skills/`.

One project only: put the folders under `<project>/.claude/skills/` instead.

## Optional: ask once per project

Paste [`CLAUDE.md.snippet`](CLAUDE.md.snippet) into `~/.claude/CLAUDE.md`. With it, Claude asks once per project whether to orchestrate when you send several tasks in one message, and remembers the answer. Without it, the skill runs when you type `/orchestrate` (or when Claude matches a batch of tasks to the skill's description).

## Check

Open a new session in the Code tab (skills load at session start) and type `/orchestrate`. Claude should load the skill and either ask whether to orchestrate in this project or start splitting your message. If `/orchestrate` is not offered: for the plugin, `claude plugin list` should show `orchestrate@orchestor` as enabled; for the hand install, check that `~/.claude/skills/orchestrate/SKILL.md` exists (`ls -L` follows the symlink).

## Update (hand install)

```bash
git -C ~/orchestor pull
```

With the symlink, new sessions pick it up. With a copy, copy the folder again. [CHANGELOG.md](CHANGELOG.md) says what changed.

## Second machine

With the plugin, run the install command there too. With the hand install, repeat the clone and the symlink on the other machine, and `git pull` on both when you update. If you sync `~/.claude` some other way (a dotfiles repo, iCloud), sync the clone too, or use a copy instead of the symlink there. The per-project answer ("orchestrate here: yes/no") lives in Claude Code's project memory on each machine, so each machine asks once.

## Uninstall (hand install)

```bash
rm -r ~/.claude/skills/orchestrate ~/.claude/skills/bug
```

(`rm` without `-r` for the symlinks.) Remove the snippet from `~/.claude/CLAUDE.md` if you added it.
