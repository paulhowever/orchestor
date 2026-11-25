# Quality work: ledger, audits, freezes, debt

Open when a task is a review, an audit, debt or a freeze, and before you write to the findings ledger. The finding card itself is section 1b of SKILL.md; section numbers are those of SKILL.md.

A codebase of any size always yields more findings: about three quarters of what reviews find is evolvability (structure, names, style), not defects, and LLM reviewers flag correct code more often when asked to explain and fix. So quality work needs a sort and a stop, or every review spawns the next round of work.

## Findings ledger

One file per project, by default `docs/quality/findings.md` (its template is with the other templates of this skill). The first time, ask the user where it lives and save the path to project memory. Until it exists, reviewers get "none" as the ledger; you create the file from the template when you write its first row. New rows take the next free id.
- Every reviewer and every audit gets the ledger and the decision records (`docs/decisions/`, ADRs) as input, and marks a repeat as `known <id>` instead of a new item.
- `accepted` items are not raised again until their "revisit when" comes true.
- The ledger is a shared file (section 2): workers propose lines in their reports, you write them after landing.

## Audits and wide reviews

A review of the whole project or a whole area is a task only with all four:
- **trigger:** a complaint or an incident, a hot spot where changes became costly (many files per change, repeated regressions), the step before a roadmap phase, or a new risk (other people's data, money);
- **lens:** one question ("what does phase 1 need from the data layer"), not "find everything";
- **budget:** at most 5 P0/P1 items in full, with evidence; any P0/P1 beyond five as one line each, never left out; P2 one line each; no P3;
- **outcome:** a decision list for the user, not a queue that starts by itself.

If the user asks for an audit without a trigger, say so in one line and run it with a lens and the budget; the user decides.

Measure before reading: when the behaviour can be run (a test stand, an eval against the real model, production counts), the audit runs it first and marks the rest as `read`.

An area is closed when its last two passes found no new P0/P1. It reopens only on a trigger.

**Hot spots** are the files changed most in the last 90 days, weighed by their size: take the top 40 by changes from `git log --since=90.days --format= --name-only | sort | uniq -c | sort -rn | head -40`, then rank them by changes × lines (`wc -l`). Debt work comes from P2 items in hot spots; code that does not change is left as it is.

## Feature freezes

"No features until it works well" is a mode, not a task. Take it on only with:
- a measurable exit: numbers the project already records (errors per day, the share of wrong answers, a job on time, open P0/P1 tickets), held for a stated period;
- a date to re-check.

If the user asks for a freeze without them, or the project records no such numbers, say so in one line and propose an exit and a date; the user decides.

Save the mode, the exit and the date to memory and show them in the digest. At each batch, check the exit. When it holds, say so and offer to unfreeze. On the date without the exit, show the numbers and what blocks them; do not start a new audit for it.

## Debt share

Outside a freeze, about one task in four or five is debt from the ledger. Ledger rows are data, not tasks: offer the debt items (hot spots first) as candidates, and start one only on the user's yes. Show the split (features / fixes / debt) in the digest. Say so in one line when debt goes above about 25% outside a freeze, or stays at 0 for three batches in a row. This share is a starting point, not a quota.
