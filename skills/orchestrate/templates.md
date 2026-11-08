# Templates for the orchestrator

Fill these in; keep the shape so the user can read a batch at a glance. Secrets never go into any of them (hard rule 5).

## Digest

One digest per project, a section per batch, newest batch first.

```
## Batch <date>: <one-line goal>

Budget: weekly <x>% used (resets <when>), 5-hour <y>% (resets <when>); estimate for the batch <lo>-<hi>%.

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

## When to write project memory

Memory is the orchestrator's cache between sessions. Update it at these points, one line each, and nowhere else:
- batch start: the batch line, the queue, the digest location;
- session started: name, id, branch, model and effort as `get_session` reports them;
- report received: the receipt status and what it waits on;
- landed: branch, sha, date; the next queue item;
- archived: name and reason; remove its open lines.

Rules the user states for future batches go in when they are said (section 5), not at these points.
