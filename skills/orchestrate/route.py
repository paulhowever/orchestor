#!/usr/bin/env python3
"""Pick a model and effort for a task from a card of observable facts, and climb only after a verified failure.

The table is data (routes.json, next to this file, also the only place with model names). The hard rules are
code and hold whatever the table says. No network, no model calls, no dependencies. Python 3.8+.

  route.py pick --task SLUG --kind K --size S|M|L|XL --sites N|unknown --spec agreed|open
                --verifier exists|can-be-written|human-only [--risk a,b] [--parent-effort E]
                [--override model/effort --reason TEXT] [--dry-run]
  route.py bind --task SLUG --session ID                     the session that got the task
  route.py fail --task SLUG --evidence "command -> failing result"     what to do next
  route.py outcome --task SLUG --result landed|dropped|reverted [--rounds N] [--p0p1 N]
  route.py table                                             print the table and the hard rules
  route.py validate [FILE]                                   check routes.json

The card holds facts, never a difficulty score. `sites` is how many files or areas are expected to change
(a rename with a number has a full list of places). For research and review, `spec` is whether the question is agreed.
Log: $ORCHESTRATE_HOME/routes.jsonl (default ~/.claude/orchestrate). Keep secrets out of every argument.
Exit codes: 0 done, 1 refused (XL, unknown task, broken table), 2 bad arguments.
"""
import argparse, itertools, json, os, re, sys
from collections import namedtuple
from datetime import datetime, timezone

KINDS = ["docs-config", "rename", "fix-known-cause", "fix-unknown-cause", "feature", "refactor", "tests", "migration",
         "ui", "design", "code-research", "web-research", "review"]
SIZES = ["S", "M", "L", "XL"]
SPECS = ["agreed", "open"]
VERIFIERS = ["exists", "can-be-written", "human-only"]
RISKS = ["data", "auth", "money", "public-api", "hard-to-undo"]
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
RESULTS = ["landed", "dropped", "reverted"]
ENUMS = {"kind": KINDS, "size": SIZES, "spec": SPECS, "verifier": VERIFIERS}
MAX_RUNGS, MAX_CLIMBS, MAX_TEXT = 3, 2, 300

ROUTES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "routes.json")
HOME = os.environ.get("ORCHESTRATE_HOME") or os.path.expanduser("~/.claude/orchestrate")
LOG = os.path.join(HOME, "routes.jsonl")

HARD_RULES = [
    "size XL is refused: split the task",
    "any risk flag: at least the strong tier at high, review required, a failure goes to the user",
    "verifier human-only: one rung up, never below the strong tier, a failure goes to the user",
    "a climb needs evidence: one informed retry first, then at most %d climbs, then split or ask" % MAX_CLIMBS,
]
SECRET = re.compile(r"""(?ix) \b(?:sk|pk|rk|ghp|gho|ghs|ghu|glpat|xox[a-z])[-_](?=\S*\d)[a-z0-9_-]{10,} | github_pat_
    | AKIA[0-9A-Z]{12} | \beyJ[a-z0-9_-]{10,} | PRIVATE\ KEY | \b(?:bearer|basic)\s+(?=\S*\d)[a-z0-9._~+/=-]{8,}
    | ://[^/\s:@]+:[^/\s@]+@ | (?:password|passwd|secret|token|api[-_]?key)=\S{4,} | (?:password|api[-_]?key):\s*\S{4,}""")


class Refused(Exception):
    pass


class Rung(namedtuple("Rung", "tier effort model key")):
    """One model and effort. `key` orders rungs: the tier first, then the effort."""
    @property
    def name(self):
        return self.tier + "/" + self.effort

    @property
    def full(self):
        return self.model + "/" + self.effort


Pick = namedtuple("Pick", "route ladder rung next review why")


# --- the table

def rung(data, text):
    """"tier/effort" or "model/effort" -> Rung; ValueError when either half is unknown."""
    tier, _, effort = text.partition("/")
    for i, t in enumerate(data["tiers"]):
        if tier in (t["tier"], t["model"]) and effort in EFFORTS:
            return Rung(t["tier"], effort, t["model"], (i, EFFORTS.index(effort)))
    raise ValueError("unknown rung %r: use <%s>/<%s>" % (
        text, "|".join(t["tier"] for t in data["tiers"]), "|".join(EFFORTS)))


def matches(cond, card):
    known = card["sites"] != "unknown"
    for k, want in cond.items():
        if k == "sites":
            ok = known == (want == "known")
        elif k == "sites_max":
            ok = known and card["sites"] <= want
        else:
            ok = card[k] in want
        if not ok:
            return False
    return True


def find(data, card):
    return next((r for r in data["routes"] if any(matches(c, card) for c in r["any"])), None)


def higher(ladder, current):
    return next((r for r in ladder if r.key > current.key), None)


def floor(data, card):
    """The least rung the hard rules accept for this card, or None."""
    if card["risk"]:
        return rung(data, data["strong_tier"] + "/high")
    if card["verifier"] == "human-only":
        return rung(data, data["strong_tier"] + "/low")      # the tier is the rule; effort comes from the ladder
    return None


def below(r, least):
    """A higher tier does not make up for a lower effort, so both halves must reach the floor."""
    return least is not None and (r.key[0] < least.key[0] or r.key[1] < least.key[1])


def choose(data, card):
    if card["size"] == "XL":
        raise Refused("size XL: split the task into slices of L or smaller, then route each one")
    route = find(data, card)
    ladder = [rung(data, x) for x in route["ladder"]]
    r, why = ladder[0], [route["why"]]
    blind, risky = card["verifier"] == "human-only", bool(card["risk"])
    if blind:
        r = ladder[min(1, len(ladder) - 1)]
        why.append("only a human can check it: one rung up")
        if r.key[0] < rung(data, data["strong_tier"] + "/low").key[0]:
            r = rung(data, data["strong_tier"] + "/medium")
            why.append("lifted to the strong tier")
    least = floor(data, card)
    if below(r, least):
        tier = max(r.key[0], least.key[0])
        r = rung(data, data["tiers"][tier]["tier"] + "/" + EFFORTS[max(r.key[1], least.key[1])])
        why.append("risk (%s): at least the strong tier at high" % ", ".join(card["risk"]) if risky
                   else "lifted to the strong tier")
    nxt = None if blind or risky else higher(ladder, r)
    return Pick(route, ladder, r, nxt, risky, "; ".join(why))


def problems(data):
    """-> list of what is wrong with the table; empty when it is usable."""
    out = []
    if not isinstance(data, dict):
        return ["the file must hold one JSON object"]
    if not re.match(r"\d{4}-\d\d-\d\d$", str(data.get("reviewed"))):
        out.append("reviewed: a YYYY-MM-DD date is required")
    if not (isinstance(data.get("note"), str) and data["note"].strip()):
        out.append("note: required (what the table rests on and when to review it)")
    tiers = data.get("tiers")
    if not (isinstance(tiers, list) and tiers and all(
            isinstance(t, dict) and all(isinstance(t.get(k), str) and t[k] for k in ("tier", "model", "label")) for t in tiers)):
        return out + ["tiers: a non-empty list of {tier, model, label}, weakest first"]
    names = [x for t in tiers for x in (t["tier"], t["model"])]
    if len(set(names)) != len(names):
        out.append("tiers: duplicate tier or model")
    order = [t["tier"] for t in tiers]
    if data.get("strong_tier") not in order[1:]:
        out.append("strong_tier: must name a tier above the lowest one")
    routes = data.get("routes")
    if not (isinstance(routes, list) and routes and all(isinstance(r, dict) for r in routes)):
        return out + ["routes: a non-empty list is required"]
    ids = [r.get("id") for r in routes]
    usable = True
    for r in routes:
        rid = str(r.get("id"))
        if not isinstance(r.get("id"), str) or ids.count(r.get("id")) > 1:
            out.append("%s: id missing or duplicate" % rid)
        if not (isinstance(r.get("why"), str) and r["why"].strip()):
            out.append("%s: why is required" % rid)
        try:
            ladder = [rung(data, x) for x in r["ladder"]]
        except (KeyError, TypeError, AttributeError, ValueError) as e:
            out.append("%s: bad rung in the ladder (%s)" % (rid, e))
            continue
        if not 1 <= len(ladder) <= MAX_RUNGS or any(a.key >= b.key for a, b in zip(ladder, ladder[1:])):
            out.append("%s: ladder needs 1 to %d rungs, each above the one before" % (rid, MAX_RUNGS))
        conds = r.get("any")
        if not (isinstance(conds, list) and conds and all(isinstance(c, dict) and c for c in conds)):
            out.append("%s: any must be a non-empty list of conditions" % rid)
            usable = False
            continue
        for c in conds:
            for k, v in c.items():
                if k in ENUMS:
                    bad = not (isinstance(v, list) and v and all(x in ENUMS[k] for x in v))
                elif k == "sites":
                    bad = v not in ("known", "unknown")
                elif k == "sites_max":
                    bad = isinstance(v, bool) or not isinstance(v, int) or v < 0
                else:
                    out.append("%s: unknown field %r in a condition" % (rid, k))
                    usable = False
                    continue
                if bad:
                    out.append("%s: bad value %r for %s" % (rid, v, k))
                    usable = False
    if not usable:
        return out
    limits = [c["sites_max"] for r in routes for c in r["any"] if "sites_max" in c]
    sites = ["unknown"] + sorted({0} | set(limits) | {n + 1 for n in limits})
    hit, missing, small = set(), set(), False
    for k, z, n, s, v in itertools.product(KINDS, SIZES[:3], sites, SPECS, VERIFIERS):
        r = find(data, dict(kind=k, size=z, sites=n, spec=s, verifier=v))
        if r is None:
            missing.add(k)
            continue
        hit.add(id(r))
        small |= k == "code-research" and any(str(x).startswith((order[0] + "/", tiers[0]["model"] + "/")) for x in r["ladder"])
    out += ["%s: no route for some cards" % k for k in sorted(missing)]
    out += ["%s: never matches, an earlier route takes its cards" % r.get("id") for r in routes if id(r) not in hit]
    if small:
        out.append("code-research: never the smallest tier")
    return out


def load(path=ROUTES):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise Refused("cannot read %s: %s" % (path, e))
    bad = problems(data)
    if bad:
        raise Refused("%s is broken:\n  %s" % (path, "\n  ".join(bad)))
    return data


# --- the log

def read_log():
    if not os.path.exists(LOG):
        return []
    out = []
    with open(LOG, encoding="utf-8", errors="replace") as fh:
        for text in fh:
            try:
                row = json.loads(text)
            except ValueError:
                continue
            if isinstance(row, dict):
                out.append(row)
    return out


def append(row, dry):
    if dry:
        print("dry run: nothing written")
        return
    row = dict(row, ts=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    os.makedirs(HOME, exist_ok=True)
    with open(LOG, "a+b") as fh:                # append mode: one write per row, safe next to another session
        fh.seek(0, os.SEEK_END)
        torn = False
        if fh.tell():
            fh.seek(-1, os.SEEK_END)
            torn = fh.read(1) != b"\n"          # a half-written last line must not swallow this row
        fh.write((("\n" if torn else "") + json.dumps(row) + "\n").encode())


def state(task):
    """-> dict with the open plan of a task, or None when the task has no plan.

    A new pick replaces the card but keeps the climbs, so re-picking cannot reset the cap; an outcome closes the task."""
    s = None
    for r in read_log():
        if r.get("task") != task:
            continue
        e = r.get("event")
        if e == "plan" and isinstance(r.get("card"), dict) and {"kind", "size", "sites", "spec", "verifier", "risk"} <= set(r["card"]):
            s = s or {"climbs": 0, "retried": False}
            s.update(open=True, card=r["card"], model=r.get("model"), effort=r.get("effort"))
        elif s and e == "escalate":
            s.update(model=r.get("model"), effort=r.get("effort"), climbs=r.get("climbs", 0),
                     retried=s["retried"] or r.get("action") == "retry")
        elif s and e == "outcome":
            s.update(open=False, climbs=0, retried=False)
    return s


def planned(task, must_be_open=False):
    s = state(task)
    if s is None:
        raise Refused("no plan for %s: run pick first" % task)
    if must_be_open and not s["open"]:
        raise Refused("%s already has an outcome: run pick again to reopen it" % task)
    return s


# --- arguments

def no_secret(text):
    if SECRET.search(text):
        raise argparse.ArgumentTypeError("looks like a secret: keep it out of the log")
    return text


def slug(text):
    if not re.match(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", text) or re.search(r"[0-9a-fA-F]{32}", text):
        raise argparse.ArgumentTypeError("use 1-64 letters, digits, '.', '_' or '-', and no keys")
    return no_secret(text)


def session_id(text):
    if not re.match(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}$", text):
        raise argparse.ArgumentTypeError("expected an app or transcript session id")
    return no_secret(text)


def short(text):
    text = " ".join(text.split())
    if not text or len(text) > MAX_TEXT:
        raise argparse.ArgumentTypeError("1 to %d characters are required" % MAX_TEXT)
    return no_secret(text)


def evidence(text):
    text = short(text)
    if not re.match(r".*\w.*?\s*(?:→|->)\s*.*\w", text):
        raise argparse.ArgumentTypeError('expected "<command> -> <failing result>"')
    return text


def count(text):
    if not re.match(r"[0-9]{1,6}$", text):
        raise argparse.ArgumentTypeError("expected a whole number, 0 or more")
    return int(text)


def site_count(text):
    return text if text == "unknown" else count(text)


def risk_list(text):
    got = {x.strip() for x in text.split(",")}
    if got == {"none"}:
        return []
    if not got <= set(RISKS):
        raise argparse.ArgumentTypeError("use a comma list of %s, or none alone" % ", ".join(RISKS))
    return sorted(got)


# --- commands

def card_text(card):
    return "kind=%s size=%s sites=%s spec=%s verifier=%s risk=%s" % (
        card["kind"], card["size"], card["sites"], card["spec"], card["verifier"], ",".join(card["risk"]) or "none")


def cmd_pick(a, parser):
    if (a.override is None) != (a.reason is None):
        parser.error("--override and --reason go together")
    data = load()
    card = {k: getattr(a, k) for k in ("kind", "size", "sites", "spec", "verifier", "risk")}
    p = choose(data, card)
    r, why, warn = p.rung, p.why, []
    row = {"event": "plan", "task": a.task, "type": a.kind, "size": a.size, "card": card}
    if a.override is not None:
        try:
            r = rung(data, a.override)
        except ValueError as e:
            parser.error(str(e))
        why = "override: %s (the table said %s)" % (a.reason, p.rung.full)
        least = floor(data, card)
        if below(r, least):
            warn.append("%s is below the hard rule for %s" % (
                r.full, "risk " + ",".join(card["risk"]) if card["risk"] else "verifier human-only"))
        row["override"] = {"from": p.rung.full, "reason": a.reason, "warnings": list(warn)}
    row.update(model=r.model, effort=r.effort)
    nxt = higher(p.ladder, r) if not (card["risk"] or card["verifier"] == "human-only") else None
    if card["risk"]:
        step = "the user (a risky task is never escalated to a model)"
    elif card["verifier"] == "human-only":
        step = "the user (a failure cannot be verified)"
    else:
        step = nxt.full if nxt else "none: split the task or ask the user"
    old = state(a.task)
    gone = sorted(set(old["card"]["risk"]) - set(card["risk"])) if old and old["open"] else []
    if gone:
        warn.append("risk flags dropped since the last plan: %s. Confirm with the user" % ",".join(gone))
    append(row, a.dry_run)                     # before printing: no card reaches a brief without its plan row
    print("model: %s\neffort: %s\nreason: %s\nnext rung: %s\nreview required: %s" % (
        r.model, r.effort, why, step, "yes" if p.review else "no"))
    for w in warn:
        print("WARNING: " + w)
    if a.parent_effort and EFFORTS.index(a.parent_effort) < r.key[1]:
        print("parent effort is %s: start_session will lower %s to it. The user decides: raise the parent, or accept %s."
              % (a.parent_effort, r.effort, a.parent_effort))
    print("\n--- card for the brief\nTask: %s\nCard: %s\nRoute: %s at %s\nIf a check fails: one informed retry, then %s"
          % (a.task, card_text(card), r.model, r.effort, step) if nxt else
          "\n--- card for the brief\nTask: %s\nCard: %s\nRoute: %s at %s\nIf a check fails: %s"
          % (a.task, card_text(card), r.model, r.effort, step))
    if card["verifier"] == "can-be-written":
        print("Check: write the failing check first, then the change")
    if p.route.get("checklist"):
        print("Completeness checklist: list every place to cover, tick each one, name what was left out")
    if p.review:
        print("Review: required before landing")


def cmd_bind(a, parser):
    planned(a.task)
    append({"event": "bind", "task": a.task, "session": a.session}, a.dry_run)
    print("%s -> %s" % (a.task, a.session))


def cmd_fail(a, parser):
    s = planned(a.task, must_be_open=True)
    data = load()
    p = choose(data, s["card"])
    current = "%s/%s" % (s["model"], s["effort"])
    try:
        now = rung(data, current)
    except ValueError:                          # the model left the table since the plan: any rung counts as a climb
        now = Rung("?", "?", s["model"], (-1, -1))
    to, climbs = None, s["climbs"]
    if s["card"]["risk"] or s["card"]["verifier"] == "human-only":
        action = "ask-user"
        text = "ask the user: %s" % ("a risky task is never escalated to a model" if s["card"]["risk"]
                                     else "a failure cannot be verified here; with a check, pick again with --verifier exists")
    elif not s["retried"] and climbs == 0:
        action = "retry"
        text = "one informed retry in the same session on %s: give it the failing check and what was tried" % current
    else:
        to = higher(p.ladder, now) if climbs < MAX_CLIMBS else None
        if to is None:
            action = "stop"
            text = "no rung left (%d of %d climbs used): split the task or ask the user" % (climbs, MAX_CLIMBS)
        else:
            climbs += 1
            if to.model == s["model"]:
                action = "raise-effort"
                text = "raise effort to %s in the same session (set_session_effort; the app may ask the user)" % to.effort
            else:
                action = "fresh-session"
                text = ("start a fresh session on %s with the brief, the failing check and the diff. start_session never goes "
                        "above the parent's model or effort: check with get_session, and tell the user if it was lowered"
                        % to.full)
    append({"event": "escalate", "task": a.task, "action": action, "model": to.model if to else s["model"],
            "effort": to.effort if to else s["effort"], "from": current, "climbs": climbs, "evidence": a.evidence}, a.dry_run)
    print("next: " + text)


def cmd_outcome(a, parser):
    planned(a.task)
    row = {"event": "outcome", "task": a.task, "result": a.result}
    row.update({k: v for k, v in (("rounds", a.rounds), ("p0p1", a.p0p1)) if v is not None})
    append(row, a.dry_run)
    print("%s: %s" % (a.task, a.result))


def cmd_table(a, parser):
    data = load()
    print("reviewed %s. %s\n\nFirst matching route wins:" % (data["reviewed"], data["note"]))
    for r in data["routes"]:
        when = " OR ".join(" ".join("%s=%s" % (k, "|".join(v) if isinstance(v, list) else v) for k, v in c.items()) for c in r["any"])
        print("\n%s: %s\n  %s%s\n  why: %s" % (r["id"], when, " -> ".join(rung(data, x).full for x in r["ladder"]),
                                             "  + completeness checklist" if r.get("checklist") else "", r["why"]))
    print("\nHard rules, whatever the table says:")
    for h in HARD_RULES:
        print("- " + h)


def cmd_validate(a, parser):
    data = load(a.file)
    print("ok: %d routes, %d kinds, reviewed %s" % (len(data["routes"]), len(KINDS), data["reviewed"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def command(name, fn, task=True):
        p = sub.add_parser(name, allow_abbrev=False)
        p.set_defaults(fn=fn, parser=p)
        if task:
            p.add_argument("--task", type=slug, required=True)
            p.add_argument("--dry-run", action="store_true")
        return p

    p = command("pick", cmd_pick)
    for name, values in ENUMS.items():
        p.add_argument("--" + name, choices=values, required=True)
    p.add_argument("--sites", type=site_count, required=True)
    p.add_argument("--risk", type=risk_list, default=[])
    p.add_argument("--parent-effort", choices=EFFORTS)
    p.add_argument("--override", metavar="MODEL/EFFORT")
    p.add_argument("--reason", type=short)
    command("bind", cmd_bind).add_argument("--session", type=session_id, required=True)
    command("fail", cmd_fail).add_argument("--evidence", type=evidence, required=True)
    p = command("outcome", cmd_outcome)
    p.add_argument("--result", choices=RESULTS, required=True)
    p.add_argument("--rounds", type=count)
    p.add_argument("--p0p1", type=count)
    command("table", cmd_table, task=False)
    command("validate", cmd_validate, task=False).add_argument("file", nargs="?", default=ROUTES)
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    try:
        a.fn(a, a.parser)
    except Refused as e:
        print("refused: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
