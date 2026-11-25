# Tracking sessions

Open when a session is silent or stuck, when one you did not start appears, or when a new batch comes while one runs. Section numbers are those of SKILL.md.

A session that has not reported for a long time is one of:
- **ok**: working, its last activity is recent; leave it.
- **restart helps**: an error loop, a lost connection, a crashed tool; tell the user and offer a follow-up message or a fresh session from its last commit.
- **needs a person**: waiting on a permission prompt, a plan approval or a question; give the user its link (hard rule 4: you do not answer for them).
- **hit a limit**: stopped on a usage limit; note when it resets (`get_usage`) and hold the queue until then.

Sessions you did not start (a card a worker proposed, a session the user started from one) are not yours until the user says so. When one appears in `list_sessions` linked to this batch, tell the user and add it to the digest; check its files against the Files table.

A new batch while one runs: reconcile first (section 8a), then check its files against the files running sessions own; overlapping tasks wait behind the session that owns those files.
