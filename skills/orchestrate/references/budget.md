# Budget: estimate, limits, and what a batch cost

Open before a batch starts, when a limit is hit, and after a batch closes. Section numbers are those of SKILL.md.

Cost is mostly cached context re-read on every step, so it is about context size × steps, not about the model alone. `python3 <skill dir>/usage.py` (`--help` lists the commands) reads only the usage numbers of the transcripts in `~/.claude/projects`, never message text, and keeps the log and the calibration in `~/.claude/orchestrate/`. `usage.py tokens` gives one weighted figure per session, `usage.py days` totals per day, `--project` narrows both. Totals include a session's subagents and workflows. `--session` takes the app id or the transcript id.

## Before a batch

1. Read `get_usage` (load it with ToolSearch if deferred): the weekly and 5-hour percents and when they reset, and your own context fill.
2. Size each task (section 3b) and estimate it as a **range**, never one number: `usage.py estimate --type <kind> --size <S|M|L>` (`<kind>` is the kind on the route card; from past sessions of that kind; with fewer than 3 it says so and you give `--ctx` and `--steps LO-HI`). It prints percents once a calibration exists.
3. Pick a model and effort for each task with `route.py pick --dry-run` and its card (section 3), which writes nothing. Say the parent effort here, before any session starts.
4. Show a table before you start anything:

   | Task | Size | Model / effort | Estimate | % weekly | % 5-hour |
   |---|---|---|---|---|---|

   with a last line: left until the weekly reset, left until the 5-hour reset. When the budget is tight, give routine work a cheaper tier or a lower effort with `--override`, and the budget as the reason.
5. If the batch does not fit, say what to postpone and to when; the user decides.
6. Put a stop line in each brief: "Stop at about N messages or X% of the weekly limit, and report how far you got." Prefer a new session over a long one once context passes 50–60%.

When a session or the whole queue hits a limit, stop the queue and tell the user when it resets. Do not switch the work to another provider or a model the user did not pick.

Without `get_usage` (plain CLI), work in weighted tokens and say that percents are unknown. Without a calibration, say the same.

## After a batch

`usage.py sync` writes the actual cost of each task that `route.py bind` tied to a session. `land_check.py` runs it after `ok to land` and `ok to archive`; run it by hand for tasks that land without it. A session is counted once it is archived or idle for 6 hours, and its row is refreshed if it goes on.

For each finished task that had an estimate, store its range, then sync and review, in this order:

```
python3 <skill dir>/usage.py log --type <kind> --session <id> --est LO HI
python3 <skill dir>/usage.py sync
python3 <skill dir>/usage.py review
```

`log` is left for this one thing: storing the estimate range. `sync` copies the range into its own row for the same session and kind, so use the kind on the route card. The `sync` after `log` is needed even when the session was counted before, or `review` shows its row without an estimate. With several tasks, run `log` for each, then `sync` and `review` once. Say in the digest which kinds run over.

## Calibration

Take two `get_usage` readings at least 3% apart, with their times, and run `usage.py calibrate 91@<time> 94@<time> --window weekly` (or `--window 5h`). The moment a window resets counts as a reading of 0%, so `0@<reset time>` and the current reading is a valid pair once the current one is 3% or more. The rate is saved with its date and drifts, so redo it now and then.

A calibration made with older accounting (other prices, or no subagents) still prints percents, with a warning that they are off. One new `usage.py calibrate` for that window clears it.
