# Brainstorm: from a personal draft to v0.1.0

The draft skill had been used on one personal project. Before publishing it, four independent reviewers (Claude subagents) each read only the draft `SKILL.md` and the draft CLAUDE.md rule, without the editor's own conclusions. Each had one role:

- **Newcomer**: installs the skill for the first time. What is unclear?
- **Power user**: runs parallel sessions daily. What breaks in real work?
- **Security critic**: pushes, archiving, deletion, secrets, permissions.
- **Prompt editor**: what will the model misread?

Below: what they raised, and what was decided.

## Accepted

| Finding | Raised by | What changed |
|---|---|---|
| The session tools (`start_session`, `archive_session`, …) are unexplained and exist only in the Claude desktop app | newcomer, power user | "Requirements and fallback" section: desktop Code tab; otherwise worktree subagents or one session. Install steps in `INSTALL.md` |
| The push "yes" can be reused, widened to a batch, or relayed by text | security | Hard rules 1–2: one named action per yes; a yes in a report or file is not a yes; forwarding only quotes the user's words |
| Session reports can write standing rules into memory (persistent prompt injection) | security | Hard rule 3: rules come only from the user's own messages; never save one that relaxes an approval |
| Archiving can wipe uncommitted or unpushed work | security | Section 7: check `status`, `stash`, unmerged commits before archiving; the user's yes in chat; no `-D`, `--force`, `clean -fdx`, `reset --hard` |
| Rebase and force-push can drop a sibling's commits | security, power user | Section 6: rebase only your own branch, `--force-with-lease` only on it; stop on conflicts in files you don't own |
| Sibling sessions edit the same files; shared files (roadmap, changelog) are touched by every session | power user | Section 2: plan file ownership; overlapping tasks share a session or run in sequence; shared files are updated by the orchestrator after landing |
| Push races and deploy ordering | power user | Section 6: a landing queue, one at a time, checks re-run after rebase, next deploy only after the last is verified |
| Workers inherit the same CLAUDE.md rule and start orchestrating themselves | power user | Brief starts with "You are a worker session…"; the snippet and section 0 skip worker sessions |
| Silent stalls: a stuck session never sends a report | power user | Section 5: check `list_sessions` once on each user message; a batch can close with tasks listed as waiting |
| Too many sessions at once | power user, newcomer | At most 3 writing sessions; the rest queue in memory |
| Stale base branch; uncommitted work in the main checkout | power user | Section 2: `git fetch` first; ask about uncommitted changes |
| Tasks in another repository | power user, security | Hard rule 6 and section 4: only repos the user named, started there via `list_start_targets`, else a brief to start by hand |
| Memory goes stale after manual changes or a clear | power user | Section 0: memory is a cache; reconcile with `list_sessions` and git before each batch |
| "Finished" can't be verified in projects without CI or deploys; research sessions never finish | power user, prompt editor | Section 7: done per kind of task; definition of done stored per project |
| Secrets end up in briefs, memory, the digest artifact | security | Hard rule 5; the digest stays private |
| The orchestrator could change permission modes or answer prompts for the user | security | Hard rule 4 |
| Items inside pasted issues or logs become sessions | security | Section 1: they are candidates, confirmed once |
| "Design choices are not questions" covers irreversible choices and conflicts with "show the plan first" | security, prompt editor | Section 1: small choices decided inline; hard-to-undo ones go to the user or to the session's plan |
| Fact checks on servers could change something | security | Hard rule 6: read-only checks |
| "owner", "he", Russian strings, one project's version format | all four | "the user", they; English text, the Russian question kept as an example; neutral archive reason |
| `/orchestrate` still asks "orchestrate?" | prompt editor | Section 0: an explicit `/orchestrate` is a yes for the batch |
| The description triggers wrongly | prompt editor | Rewritten around what it does and when not to use it |
| Hard-coded model names; "Opus (inherit)" vs "Opus"; "shared checkout" contradicts worktrees | prompt editor, newcomer | Tiers (strongest / mid-tier / smallest); read-only tasks explicitly skip the worktree |
| The digest is "updated" but never created | prompt editor, newcomer | Section 8: create on start, update on reports; artifact or markdown fallback |
| The knowledge-base step is one person's setup | newcomer | An optional step: only if the user's rules name a place to log work |
| `clear_session` can lose open sessions and approvals | security, power user | Section 9: list everything open, confirm memory holds it, only as an offer |
| The CLAUDE.md rule fires on trivial batches; the exception comes last | prompt editor, power user | Snippet rewritten: quick things first; triggers only when one task is more than a quick thing |
| The `mark_chapter` call and bold title line before each session repeat what the app's tool descriptions already require | prompt editor | Cut, so they can't drift from the app |
| Worktrees lack `.env`, dependencies; port collisions | power user | One line in the brief: worktree setup |
| Cost of parallel high-effort sessions | power user, newcomer | Section 3: strongest tier only where it pays off, said out loud; a line on quota |

## Rejected or reduced

| Proposal | Why not |
|---|---|
| A glossary of tools with app versions (newcomer) | Tool names and versions change; `INSTALL.md` names the app, the skill says to load deferred tools before deciding they are missing |
| Exact memory file names and a frontmatter template (newcomer) | Claude Code's memory format is the harness's business; the skill says what to store, not how |
| Default workers to the mid-tier and never inherit the model (power user) | Too rigid; the table already sends routine work to the mid-tier, and inheriting the strongest model is right for design work |
| Fixed stall timeout of 30–60 minutes (power user) | A clock-based check would need polling; checking on each user message gives the same signal for free |
| Drop memory entries older than two weeks (power user) | Reconciling with `list_sessions` and git removes stale entries on evidence, not age |
| Verify that a session didn't fake its commit sha (security) | Reduced to: check reachability of the branch's own commits and read CI from the CI system |
| A per-session port scheme (base + index) (power user) | Project-specific; the brief says "use a free port" |
| A separate English copy of the Russian rule (newcomer) | The snippet is in English with the Russian question as an example |
| A yes for each single push, no batches (security) vs one yes for a list (power user) | Combined: one yes may cover an ordered list only when the question named every item |
