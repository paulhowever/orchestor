#!/usr/bin/env python3
"""Token spend per Claude Code session, estimates, and calibration to plan-limit percents.

Reads transcripts in ~/.claude/projects/*/*.jsonl (usage numbers only, never message text).
No dependencies. Python 3.8+.

  usage.py tokens [--session ID | --self] [--project P] [--since T] [--until T] [--json]
  usage.py days [--project P] [--since T] [--until T] [--json]     totals per local day
  usage.py log --type TYPE --session ID --est LO HI [--effort E] [--size S|M|L|XL]   append estimate vs actual
  usage.py review [--type TYPE]                 estimate against actual, inside / over / under
  usage.py estimate --type TYPE [--size S|M|L|XL] [--model M] [--ctx TOKENS --steps LO-HI]   range for a new task
  usage.py calibrate PCT@TIME PCT@TIME          weighted tokens per 1% from two get_usage readings
  usage.py calibration                          show saved calibrations

T is an ISO time ("2026-11-07T00:00", "2026-11-07 09:30+03:00") a relative "6h" / "2d" ago, or "now".
Naive times are local. The log and calibrations live in $ORCHESTRATE_HOME (default ~/.claude/orchestrate).
"""
import argparse, glob, json, os, sys
from datetime import datetime, timedelta, timezone

# --- Price table: $ per 1M tokens (in, out, cache read). Source: the `claude-api` skill,
# "Current Models" (cached 2026-10-06). Re-read it when models change.
# Models whose cache-read price the skill does not state use 0.1 x input (assumption).
# Cache write is not in the table either: standard 1.25 x input (5 min), 2 x input (1 h).
PRICES = {
    "claude-fable-5":   (10.0, 50.0, 0.25),
    "claude-opus-5-5":  (4.0, 20.0, 0.20),
    "claude-opus-5":    (5.0, 25.0, 0.50),
    "claude-opus-4":    (5.0, 25.0, 0.50),
    "claude-sonnet-5":  (2.0, 10.0, 0.20),
    "claude-sonnet-4":  (3.0, 15.0, 0.30),
    "claude-haiku-5":   (0.10, 0.50, 0.01),
    "claude-haiku-4":   (1.0, 5.0, 0.10),
}
UNKNOWN = "claude-opus-5-5"          # used for models not in the table (flagged in output)
BASE = 2.0                           # 1 weighted token = 1 input token of Sonnet 5.5 ($2/M)
W5M, W1H = 1.25, 2.0                 # cache-write multipliers on input price
# Fallback when there is no history: per step = re-read the context + a little output and cache growth.
STEP_OUT, STEP_GROW = 1500, 12000   # measured on 2 real Opus 5.5 sessions: ~1.4k out, ~13k cache write per message
MIN_LINES = 3                        # fewer past lines of a type than this -> fallback
MIN_PCT = 3                          # calibration spans under this many percent are refused

HOME = os.environ.get("ORCHESTRATE_HOME") or os.path.expanduser("~/.claude/orchestrate")
LOG, CAL = os.path.join(HOME, "estimates.jsonl"), os.path.join(HOME, "calibration.jsonl")


def price(model):
    best = max((k for k in PRICES if model.startswith(k)), key=len, default=None)
    return PRICES[best or UNKNOWN], best is None


def weigh(model, inp, out, cr, cw5, cw1):
    (pi, po, pr), _ = price(model)
    return (inp * pi + out * po + cr * pr + cw5 * pi * W5M + cw1 * pi * W1H) / BASE


def parse_time(s):
    s = s.strip()
    if s == "now":
        return datetime.now(timezone.utc)
    if s[-1:] in "hdm" and s[:-1].isdigit():
        return datetime.now(timezone.utc) - timedelta(**{{"h": "hours", "d": "days", "m": "minutes"}[s[-1]]: int(s[:-1])})
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.astimezone()


def messages(session=None, since=None, until=None, project=None):
    """-> list of (session, project, model, ts, input, output, cache_read, cw5, cw1).

    One entry per unique assistant message id (last copy wins). Only usage numbers are read."""
    msgs = {}
    root = os.environ.get("ORCHESTRATE_PROJECTS") or "~/.claude/projects"
    for f in glob.glob(os.path.join(os.path.expanduser(root), "*", "*.jsonl")):
        proj = os.path.basename(os.path.dirname(f))
        if session and session not in os.path.basename(f):
            continue
        if project and project not in proj:
            continue
        if since and datetime.fromtimestamp(os.path.getmtime(f), timezone.utc) < since:
            continue
        sid_file = os.path.basename(f)[:-6]
        with open(f, errors="replace") as fh:
            for line in fh:
                if '"usage"' not in line or '"assistant"' not in line:
                    continue
                try:
                    d = json.loads(line)
                    m = d["message"]; u = m["usage"]; ts = parse_time(d["timestamp"])
                except Exception:
                    continue
                if d.get("type") != "assistant" or not m.get("model") or m["model"].startswith("<"):
                    continue
                if (since and ts < since) or (until and ts > until):
                    continue
                cc = u.get("cache_creation") or {}
                cw1 = cc.get("ephemeral_1h_input_tokens", 0)
                cw5 = cc.get("ephemeral_5m_input_tokens", u.get("cache_creation_input_tokens", 0) - cw1)
                msgs[(sid_file, m.get("id") or d.get("uuid"))] = (
                    d.get("sessionId") or sid_file, proj, m["model"], ts,
                    u.get("input_tokens", 0), u.get("output_tokens", 0),
                    u.get("cache_read_input_tokens", 0), cw5, cw1)
    return list(msgs.values())


def group(rows, key):
    """Sum message rows into {key(row): stats}."""
    out = {}
    for r in rows:
        sid, proj, model, ts, i, o, cr, cw5, cw1 = r
        k = key(r)
        s = out.setdefault(k, dict(key=k, session=sid, project=proj, input=0, output=0, cache_read=0,
                                   cache_write=0, messages=0, weighted=0.0, models={}, sessions=set(),
                                   first=ts, last=ts, unpriced=False))
        s["input"] += i; s["output"] += o; s["cache_read"] += cr; s["cache_write"] += cw5 + cw1
        s["messages"] += 1; s["weighted"] += weigh(model, i, o, cr, cw5, cw1)
        s["models"][model] = s["models"].get(model, 0) + 1
        s["sessions"].add(sid)
        s["first"], s["last"] = min(s["first"], ts), max(s["last"], ts)
        s["unpriced"] |= price(model)[1]
    for s in out.values():
        s["model"] = max(s["models"], key=s["models"].get)
        s["sessions"] = len(s["sessions"])
    return out


def scan(session=None, since=None, until=None, project=None):
    """-> {session_id: stats}."""
    return group(messages(session, since, until, project), key=lambda r: r[0])


def fmt(n):
    n = float(n)
    return f"{n/1e6:.2f}M" if n >= 1e6 else f"{n/1e3:.0f}k" if n >= 1e4 else f"{n:.0f}"


def read_jsonl(path):
    try:
        return [json.loads(l) for l in open(path) if l.strip()]
    except OSError:
        return []


def append(path, rec):
    os.makedirs(HOME, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def latest_cal(window="weekly"):
    c = [r for r in read_jsonl(CAL) if r.get("window", "weekly") == window]
    return c[-1] if c else None


def own_session(a):
    if getattr(a, "self", False):
        sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
        if not sid:
            sys.exit("--self: CLAUDE_CODE_SESSION_ID is not set here; pass --session <id>")
        return sid
    return a.session


def dump(rows):
    for s in rows:
        s.update(first=s["first"].isoformat(), last=s["last"].isoformat())
    print(json.dumps(rows, indent=1))


def cmd_tokens(a):
    rows = sorted(scan(own_session(a), a.since, a.until, a.project).values(), key=lambda s: -s["weighted"])
    if a.json:
        dump(rows); return
    if getattr(a, "self", False) and rows:
        s = rows[0]
        mins = (s["last"] - s["first"]).total_seconds() / 60
        print(f"tokens: in {fmt(s['input'])}, out {fmt(s['output'])}, cache read {fmt(s['cache_read'])}, "
              f"cache write {fmt(s['cache_write'])}; weighted {fmt(s['weighted'])}; "
              f"{s['messages']} messages over {mins:.0f} min; {s['model']}")
        return
    print(f"{'session':36} {'msgs':>5} {'input':>7} {'output':>7} {'c.read':>8} {'c.write':>8} {'weighted':>9}  model")
    for s in rows[: a.top]:
        print(f"{s['session']:36} {s['messages']:5} {fmt(s['input']):>7} {fmt(s['output']):>7} "
              f"{fmt(s['cache_read']):>8} {fmt(s['cache_write']):>8} {fmt(s['weighted']):>9}  {s['model']}"
              + ("  (price unknown, used " + UNKNOWN + ")" if s["unpriced"] else ""))
    t = sum(s["weighted"] for s in rows)
    print(f"{len(rows)} sessions, total weighted {fmt(t)} (1 = one Sonnet 5.5 input token)")


def cmd_days(a):
    def day(r):
        return r[3].astimezone().date().isoformat()
    rows = sorted(group(messages(None, a.since, a.until, a.project), key=day).values(), key=lambda s: s["key"])
    if a.json:
        dump(rows); return
    print(f"{'day':10} {'sess':>4} {'msgs':>5} {'input':>7} {'output':>7} {'c.read':>8} {'c.write':>8} {'weighted':>9}")
    for s in rows:
        print(f"{s['key']:10} {s['sessions']:4} {s['messages']:5} {fmt(s['input']):>7} {fmt(s['output']):>7} "
              f"{fmt(s['cache_read']):>8} {fmt(s['cache_write']):>8} {fmt(s['weighted']):>9}")
    t = sum(s["weighted"] for s in rows)
    print(f"{len(rows)} days, total weighted {fmt(t)}")
    c = latest_cal(a.window)
    if c and rows:
        print(f"  = {t / c['per_pct']:.0f}% of the limit at the {c['date']} calibration")


def cmd_review(a):
    rows = [r for r in read_jsonl(LOG) if not a.type or r.get("task_type") == a.type]
    if not rows:
        print("no estimate lines yet"); return
    inside = 0
    for r in rows:
        lo, hi = r["estimate"]
        mark = "inside" if lo <= r["actual"] <= hi else ("over" if r["actual"] > hi else "under")
        inside += mark == "inside"
        print(f"{r['ts'][:10]}  {r['task_type']:12} {r.get('size') or '-':3} {fmt(lo):>7}-{fmt(hi):<7} "
              f"actual {fmt(r['actual']):>7}  {mark}")
    print(f"{inside} of {len(rows)} inside the estimate")


def cmd_log(a):
    found = scan(a.session, a.since, a.until)
    s = found.get(a.session) or next(iter(found.values()), None)
    if not s:
        sys.exit("no transcript found for that session")
    rec = dict(ts=datetime.now(timezone.utc).isoformat(timespec="seconds"), session=s["session"], task_type=a.type,
               model=s["model"], effort=a.effort, messages=s["messages"], weighted=round(s["weighted"]),
               estimate=[a.est[0], a.est[1]], actual=round(s["weighted"]), size=a.size)
    append(LOG, rec)
    inside = "inside" if a.est[0] <= rec["actual"] <= a.est[1] else "OUTSIDE"
    print(f"logged: {a.type}, actual {fmt(rec['actual'])} vs estimate {fmt(a.est[0])}-{fmt(a.est[1])} ({inside})")


def cmd_estimate(a):
    rows = [r for r in read_jsonl(LOG) if r.get("task_type") == a.type]
    for field, want in (("size", a.size), ("model", a.model)):
        same = [r for r in rows if want and r.get(field) == want]
        rows = same if len(same) >= MIN_LINES else rows
    if len(rows) >= MIN_LINES:
        v = sorted(r["actual"] for r in rows)
        lo, hi = v[len(v) // 4], v[-1 - len(v) // 4]
        src = f"{len(rows)} past '{a.type}' sessions (middle half of actuals)"
    else:
        if not (a.ctx and a.steps):
            sys.exit(f"only {len(rows)} past '{a.type}' lines (need {MIN_LINES}): too little history. "
                     "Give --ctx <context tokens> and --steps LO-HI to use context size x steps.")
        s_lo, s_hi = (int(x) for x in a.steps.split("-"))
        (pi, po, pr), _ = price(a.model or UNKNOWN)
        per = (a.ctx * pr + STEP_OUT * po + STEP_GROW * pi * W1H) / BASE
        lo, hi = per * s_lo, per * s_hi
        src = f"too little history ({len(rows)} lines): context {fmt(a.ctx)} x {s_lo}-{s_hi} steps"
    print(f"estimate {fmt(lo)} - {fmt(hi)} weighted  [{src}]")
    c = latest_cal(a.window)
    if c:
        print(f"  = {lo / c['per_pct']:.1f} - {hi / c['per_pct']:.1f}% of the limit "
              f"(calibration {c['date']}: {fmt(c['per_pct'])} per 1%, window '{c.get('window', '?')}')")
    else:
        print(f"  percent unknown: no '{a.window}' calibration yet (run `calibrate`)")


def cmd_calibrate(a):
    (p1, t1), (p2, t2) = (x.split("@", 1) for x in (a.first, a.second))
    p1, p2, t1, t2 = float(p1), float(p2), parse_time(t1), parse_time(t2)
    if t2 < t1:
        p1, p2, t1, t2 = p2, p1, t2, t1
    d = p2 - p1
    if d < MIN_PCT:
        sys.exit(f"refused: span is {d:g}% (< {MIN_PCT}%). Readings are whole percents shared by the account; "
                 "wait for a bigger move.")
    tot = sum(s["weighted"] for s in scan(None, t1, t2).values())
    rec = {"date": datetime.now().date().isoformat(), "window": a.window, "from": t1.isoformat(),
           "to": t2.isoformat(), "pct": d, "weighted": round(tot), "per_pct": round(tot / d)}
    append(CAL, rec)
    print(f"{fmt(tot)} weighted over {d:g}% -> {fmt(rec['per_pct'])} per 1% (saved {rec['date']}). "
          f"Whole-percent readings: about +-{100 / d:.0f}% error here; other machines are not counted.")


def cmd_calibration(a):
    for c in read_jsonl(CAL):
        print(f"{c['date']}  {c['pct']:g}% = {fmt(c['weighted'])}  -> {fmt(c['per_pct'])}/1%  [{c.get('window', '?')}]")
    if not os.path.exists(CAL):
        print("no calibrations yet")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tokens"); t.add_argument("--session"); t.add_argument("--since", type=parse_time)
    t.add_argument("--until", type=parse_time); t.add_argument("--top", type=int, default=20); t.add_argument("--json", action="store_true")
    t.add_argument("--project", help="substring of the ~/.claude/projects folder name")
    t.add_argument("--self", action="store_true", help="this session (CLAUDE_CODE_SESSION_ID), one line for a receipt")
    t.set_defaults(f=cmd_tokens)
    d = sub.add_parser("days"); d.add_argument("--since", type=parse_time); d.add_argument("--until", type=parse_time)
    d.add_argument("--project"); d.add_argument("--json", action="store_true")
    d.add_argument("--window", default="weekly"); d.set_defaults(f=cmd_days)
    r = sub.add_parser("review"); r.add_argument("--type"); r.set_defaults(f=cmd_review)
    l = sub.add_parser("log"); l.add_argument("--type", required=True); l.add_argument("--session", required=True)
    l.add_argument("--est", type=float, nargs=2, required=True, metavar=("LO", "HI")); l.add_argument("--effort", default="")
    l.add_argument("--size", choices=["S", "M", "L", "XL"])
    l.add_argument("--since", type=parse_time); l.add_argument("--until", type=parse_time); l.set_defaults(f=cmd_log)
    e = sub.add_parser("estimate"); e.add_argument("--type", required=True); e.add_argument("--ctx", type=int)
    e.add_argument("--steps"); e.add_argument("--model"); e.add_argument("--size", choices=["S", "M", "L", "XL"])
    e.add_argument("--window", default="weekly", help="which calibration to print percents with (weekly, 5h)")
    e.set_defaults(f=cmd_estimate)
    c = sub.add_parser("calibrate"); c.add_argument("first"); c.add_argument("second")
    c.add_argument("--window", default="weekly"); c.set_defaults(f=cmd_calibrate)
    sub.add_parser("calibration").set_defaults(f=cmd_calibration)
    a = p.parse_args(); a.f(a)


if __name__ == "__main__":
    main()
