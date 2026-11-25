# Findings ledger

| Id | Where | Harm | Evidence | Decision | Revisit when | Source |
|---|---|---|---|---|---|---|
| F1 | skills/orchestrate/usage.py (sync) | P2 | run: full transcript load took 8 s on 3.4 GB | debt | a sync takes over 20 s, or land_check reaches its 30 s limit | review of usage-sync, 2026-11-25 |
| F2 | skills/orchestrate/route.py (--override, re-pick) | P2 | run: override below the risk floor is accepted with a logged warning | accepted: an override is the user's call and needs a reason | an override on a risky task turns out wrong | review of route-card, 2026-11-25 |
| F3 | skills/orchestrate/land_check.py (default_base) | P2 | read: a `master` repository without origin/HEAD needs `--base` | debt | someone lands in a `master` repository | worker report plugin-hooks, 2026-11-25 |
| F4 | skills/bug/SKILL.md (hand-over) | P2 | read: picks the model tier in prose, may contradict the route card | debt | skills/bug is changed next | worker report skill-core, 2026-11-25 |
| F5 | skills/orchestrate/SKILL.md section 7 after a chain (R3) | P2 | run: `--archive` without a base refuses a landed branch while local main is behind; fails safe | debt | an archive check is refused after a chain landing | review of skill-core, 2026-11-25 |
| F6 | skills/orchestrate/references/split.md (R5) | P2 | run: "check the direction after two or three landed tasks" is only read before splitting | debt | a batch continues past three landings without the check | review of skill-core, 2026-11-25 |
