# Templates for the orchestrator

Fill these in; keep the shape so the user can read a batch at a glance. Secrets never go into any of them (hard rule 5).

## Digest

One digest per project, a section per batch, newest batch first.

```
## Batch <date>: <one-line goal>

Budget: weekly <x>% used (resets <when>), 5-hour <y>% (resets <when>); estimate for the batch <lo>-<hi>%.
Mode: features | freeze until <exit, e.g. "errors 0/day and wrong answers ≤ 10% for 7 days">, re-check <date>; now <numbers>.
Split: features <n> / fixes <n> / debt <n>. Ledger: <path>.

| Session | Branch | Commits | Checked | Waits on | Next |
|---|---|---|---|---|---|
| [<name>](<link>) | <branch> @ <sha> | <n> on main | tests ok, lint ok, CI green | user: push yes | land after <other> |

### Files
| Session | Owns | Shared, landed by the orchestrator |
|---|---|---|
| <name> | <paths or areas> | CHANGELOG.md |

### Queue
1. <task>: waits for <session> to land (overlaps <files>)

### Done
- <name>: landed <sha> on <date>, archived <yes/no>
```

- **Checked** is what you verified yourself (git, CI), not what the report says.
- **Waits on** is one of: nothing, user (and for what), a session, a limit (and when it resets).
- **Next** is the one step that moves this row.

## File ownership and overlap check

Before each `start_session`, list the files or areas the new task will touch and compare them with the **Files** table:
- no overlap → start it and add its row;
- overlap with a running session → it goes to the queue behind that session, or into that session as a follow-up;
- overlap only in shared files (changelog, roadmap, docs index) → start it, and say in the brief that you update those after landing.

A test file belongs to the session whose code it tests. Two sessions that both need the same test file is an overlap.

## Message to siblings when main moves

Send after each landing to every running writing session whose branch is behind the default branch:

```
main moved to <short sha> (<branch that landed>: <one line>). Before your next commit:
git fetch && git rebase <default branch>; re-run your checks.
On a conflict in a file you do not own (see your brief), stop and report instead of picking a side.
```

## Reviewer brief

For the one fresh-context review before landing (SKILL section 6) and, with a lens and a budget instead of a diff, for an audit (section 1b).

```
You review <branch> against <default branch>: the diff and the code it directly calls or is called by.
Input: the diff (git diff <base>...<branch>), the findings ledger <path or "none">, the decision records <path or "none">.
Not your input: the worker's reasoning or report.

Look for, in this order: wrong behaviour for a person, lost or leaked data, security, a broken contract
(API, schema, a rule in CLAUDE.md), a regression in something that worked, a significant structural risk this diff adds.

For each finding give a card: where (file:line), scenario (input or state → wrong outcome),
evidence (run: a command or test you ran, with its output | read | opinion), harm P0–P3, the fix in one line.
A finding without run evidence is P2 at most, unless it is security or data loss.
A finding already in the ledger or settled by a decision record: write "known <id>", nothing more.

Do not propose a global refactor or an alternative design. Do not count taste as a defect.
End with one verdict line: "can land: no P0/P1" or "cannot land: <ids of P0/P1>".
"No P0/P1" is a normal outcome; do not look for something to say.
```

## Findings ledger

One file per project (default `docs/quality/findings.md`). A row per finding; ids stay stable, rows are never deleted, only their decision changes.

```
# Findings ledger

| Id | Where | Harm | Evidence | Decision | Revisit when | Source |
|---|---|---|---|---|---|---|
| F12 | services/notify.py:88 | P1 | run: test_quiet_hours_overlap | now → landed 3f05ba8 | — | review of <branch>, <date> |
| R9 | db.py:21 | P3 | read | accepted: one process today | a second process opens the base | arch review <date> |
| A3 | parse.py:306 | P2 | read | debt (hot spot) | parse.py is changed next | audit <date> |
```

- **Decision** is `now`, `debt` or `accepted: <reason>`; when a `now` lands, add its commit.
- **Revisit when** is a fact someone can check, not "later".
- The orchestrator writes the ledger after landing; workers and reviewers propose rows in their reports.

## When to write project memory

Memory is the orchestrator's cache between sessions. Update it at these points, one line each, and nowhere else:
- batch start: the batch line, the queue, the digest location, the mode (and a freeze's exit and date), the ledger's path;
- session started: name, id, branch, model and effort as `get_session` reports them;
- report received: the receipt status and what it waits on;
- landed: branch, sha, date; the next queue item;
- archived: name and reason; remove its open lines.

Rules the user states for future batches go in when they are said (section 5), not at these points.
