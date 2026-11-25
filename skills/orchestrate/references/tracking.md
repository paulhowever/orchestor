# Tracking sessions

Open when a session is silent or stuck, when one you did not start appears, when a new batch comes while one runs, or when `route.py fail` prints a fresh session. Section numbers are those of SKILL.md.

## A silent session

A session that has not reported for a long time is one of:
- **ok**: working, its last activity is recent; leave it.
- **restart helps**: an error loop, a lost connection, a crashed tool; tell the user and offer a follow-up message or a fresh session from its last commit.
- **needs a person**: waiting on a permission prompt, a plan approval or a question; give the user its link (hard rule 4: you do not answer for them).
- **hit a limit**: stopped on a usage limit; note when it resets (`get_usage`) and hold the queue until then.

## Sessions you did not start

Sessions you did not start (a card a worker proposed, a session the user started from one) are not yours until the user says so. When one appears in `list_sessions` linked to this batch, tell the user and add it to the digest; check its files against the Files table.

## A new batch while one runs

Reconcile first (section 8a), then check its files against the files running sessions own; overlapping tasks wait behind the session that owns those files.

## A climb to a fresh session

`route.py fail` prints "raise effort in the same session" (a follow-up, nothing new starts) or "start a fresh session". In the second case the first session still holds the task, so this is the failed case of the duplicate check (section 4): the new session replaces it, and one task never has two live writers.

1. **Ask the user**, naming the failed check, the first session and the printed model and effort. Start nothing before the yes.
2. **Stop the first writer.** Send it one last message: commit what it has, report with status `draft`, do no more work on this task. Check that it has ended its turn and that its worktree is clean at that commit. While it runs or does not answer, the new session waits; give the user its link.
3. **Move its files.** In the Files table the new session owns them and the first owns none; the digest says which session replaced which. The new session takes the first one's place among the 3 writing sessions.
4. **Start** the new session from the first one's branch, on its own branch, with the same brief plus the failing check, what was tried and the diff. Put the printed model and effort on the Route line and do not run `pick` again: it would set the task back to its first rung. Then `route.py bind` the new session and check it with `get_session`.
5. **Land** only the new branch. The first session stays open and idle until then, and is archived by section 7 like any other.
