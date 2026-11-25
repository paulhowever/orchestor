#!/usr/bin/env python3
"""Token spend per Claude Code session, estimates, and calibration to plan-limit percents.

Reads transcripts in ~/.claude/projects (usage numbers only, never message text): main ones, and the
subagent and workflow ones, which count towards their parent session. No dependencies. Python 3.8+.

  usage.py tokens [--session ID | --self] [--project P] [--since T] [--until T] [--json]
  usage.py days [--project P] [--since T] [--until T] [--json]     totals per local day
  usage.py log --type TYPE --session ID --est LO HI [--effort E] [--size S|M|L|XL]   append estimate vs actual
  usage.py sync [--quiet]                       one row per task in routes.jsonl whose session has ended
  usage.py review [--type TYPE]                 estimate against actual, inside / over / under
  usage.py estimate --type TYPE [--size S|M|L|XL] [--model M] [--ctx TOKENS --steps LO-HI]   range for a new task
  usage.py calibrate PCT@TIME PCT@TIME          weighted tokens per 1% from two get_usage readings
  usage.py calibration                          show saved calibrations

ID is the desktop app's id (local_...) or the transcript id. The app keeps the link between them in
$ORCHESTRATE_APP_SESSIONS (default ~/Library/Application Support/Claude/claude-code-sessions, undocumented,
macOS); without that folder only transcript ids work.
"Ended" for `sync`: archived in the app, or no message for 6 hours. A row is refreshed if the session goes on.
T is an ISO time ("2026-11-07T00:00", "2026-11-07 09:30+03:00") a relative "6h" / "2d" ago, or "now".
Naive times are local. The log and calibrations live in $ORCHESTRATE_HOME (default ~/.claude/orchestrate).
"""
import argparse, contextlib, glob, itertools, json, os, re, sys
from collections import namedtuple
from datetime import datetime, timedelta, timezone

# --- Price table: $ per 1M tokens (in, out, cache read). Source, read on PRICES_DATE:
# https://platform.claude.com/docs/en/about-claude/pricing.md ("Model pricing"; cache writes on every row are
# 1.25 x input for 5 min and 2 x input for 1 h). Change PRICES_DATE with the table: it marks rows and
# calibrations as made with other prices. Bump SCHEMA when what is counted changes (1 = no subagents,
# copies in forks counted again).
PRICES_DATE, SCHEMA = "2026-11-25", 2
PRICES = {
    "claude-fable-5-2":  (8.0, 40.0, 0.20),
    "claude-fable-5-1":  (10.0, 50.0, 0.25),
    "claude-fable-5":    (10.0, 50.0, 1.00),
    "claude-mythos-5-2": (8.0, 40.0, 0.20),
    "claude-mythos-5-1": (10.0, 50.0, 0.25),
    "claude-mythos-5":   (10.0, 50.0, 1.00),
    "claude-opus-5-5":   (4.0, 20.0, 0.20),
    "claude-opus-5":     (5.0, 25.0, 0.50),
    "claude-opus-4-8":   (5.0, 25.0, 0.50),
    "claude-opus-4-7":   (5.0, 25.0, 0.50),
    "claude-opus-4-6":   (5.0, 25.0, 0.50),
    "claude-opus-4-5":   (5.0, 25.0, 0.50),
    "claude-opus-4-1":   (15.0, 75.0, 1.50),
    "claude-opus-4":     (15.0, 75.0, 1.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.10),
    "claude-sonnet-5":   (2.0, 10.0, 0.20),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30),
    "claude-sonnet-4-5": (3.0, 15.0, 0.30),
    "claude-sonnet-4":   (3.0, 15.0, 0.30),
    "claude-haiku-5-5":  (0.10, 0.50, 0.01),
    "claude-haiku-4-5":  (1.0, 5.0, 0.10),
}
# Requests with a longer prompt (input + cache reads + cache writes) pay the second row in full.
LONG = {"claude-haiku-5-5": (100000, (0.50, 2.50, 0.05))}
# what may follow a table name in a model id: a date, a cloud version, a variant
SUFFIX = re.compile(r"(-latest|-\d{8})?(-v\d+(:\d+)?)?(@[\w-]+)?(\[\w+\])?$")
UNKNOWN = "claude-opus-5-5"          # used for models with no name in common with the table
BASE = 2.0                           # 1 weighted token = 1 input token of Sonnet 5.5 ($2/M)
W5M, W1H = 1.25, 2.0                 # cache-write multipliers on input price
# Fallback when there is no history: per step = re-read the context + a little output and cache growth.
STEP_OUT, STEP_GROW = 1500, 12000   # measured on 2 real Opus 5.5 sessions: ~1.4k out, ~13k cache write per message
MIN_LINES = 3                        # fewer past lines of a type than this -> fallback
MIN_PCT = 3                          # calibration spans under this many percent are refused
IDLE_HOURS = 6                       # `sync`: a session with no message for this long has ended

HOME = os.environ.get("ORCHESTRATE_HOME") or os.path.expanduser("~/.claude/orchestrate")
LOG, CAL, ROUTES = (os.path.join(HOME, n) for n in ("estimates.jsonl", "calibration.jsonl", "routes.jsonl"))
PROJECTS = os.path.expanduser(os.environ.get("ORCHESTRATE_PROJECTS") or "~/.claude/projects")
APP = os.path.expanduser(os.environ.get("ORCHESTRATE_APP_SESSIONS")
                         or "~/Library/Application Support/Claude/claude-code-sessions")

# One assistant message. session = the transcript id that pays for it; sub = made by a subagent.
Msg = namedtuple("Msg", "session project model ts input output cache_read cw5 cw1 sub effort")


def price(model, prompt=0):
    """-> (in, out, cache read) and the table name it is only a guess from (None when the model is in the table)."""
    model = model[max(model.find("claude-"), 0):]
    best = max((k for k in PRICES if model.startswith(k)), key=len, default=None)
    guess = None if best and SUFFIX.match(model[len(best):]) else best or UNKNOWN
    limit, long_row = LONG.get(best, (0, None))
    return (long_row if long_row and prompt > limit else PRICES[best or UNKNOWN]), guess


def weigh(model, inp, out, cr, cw5, cw1):
    (pi, po, pr), _ = price(model, inp + cr + cw5 + cw1)
    return (inp * pi + out * po + cr * pr + cw5 * pi * W5M + cw1 * pi * W1H) / BASE


def parse_time(s):
    s = s.strip()
    if s == "now":
        return datetime.now(timezone.utc)
    if s[-1:] in "hdm" and s[:-1].isdigit():
        return datetime.now(timezone.utc) - timedelta(**{{"h": "hours", "d": "days", "m": "minutes"}[s[-1]]: int(s[:-1])})
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.astimezone()


# --- Session ids
class UnknownSession(Exception):
    pass


def app_sessions():
    """-> {app id: {"cli": [transcript ids, current one last], "archived": bool}} from the app's metadata files."""
    out = {}
    for f in glob.glob(os.path.join(glob.escape(APP), "**", "*.json"), recursive=True):
        try:
            with open(f, errors="replace") as fh:
                d = json.load(fh)
            aid, cli = d["sessionId"], d["cliSessionId"]
            old = [x for x in d.get("priorCliSessionIds") or [] if isinstance(x, str) and x != cli]
        except Exception:
            continue                 # another kind of file, or a session with no transcript yet
        if isinstance(aid, str) and isinstance(cli, str):
            out[aid] = {"cli": old + [cli], "archived": bool(d.get("isArchived"))}
    return out


def app_of(apps):
    """-> {transcript id: app id}; the session that uses the transcript now wins over one that used it before."""
    out = {}
    for current in (False, True):
        for aid, a in apps.items():
            for t in a["cli"][-1:] if current else a["cli"][:-1]:
                out[t] = aid
    return out


def transcript_files():
    """-> [(file, project, top transcript id, is a subagent's)]. Layout: <project>/<id>.jsonl, and under
    <project>/<id>/subagents/ the agents' and (workflows/<run>/) the workflow agents' transcripts."""
    out = []
    for d in glob.glob(os.path.join(glob.escape(PROJECTS), "*")):
        proj = os.path.basename(d)
        out += [(f, proj, os.path.basename(f)[:-6], False) for f in glob.glob(os.path.join(glob.escape(d), "*.jsonl"))]
        for f in glob.glob(os.path.join(glob.escape(d), "*", "subagents", "**", "*.jsonl"), recursive=True):
            out.append((f, proj, os.path.relpath(f, d).split(os.sep)[0], True))
    return out


def resolve(sid, apps, tops):
    """App id, transcript id or a part of one -> (app id or None, [transcript ids of that session]).

    A part of an id may fit several sessions: then the list has them all and the app id is None."""
    apps_by_cli = app_of(apps)
    hits = [a for a in (sid, "local_" + sid) if a in apps]
    if not hits and sid.startswith("local_"):
        bare = sid[len("local_"):]
        if bare in tops:
            return apps_by_cli.get(bare) or sid, [bare]
        hits = [a for a in apps if a.startswith(sid)]
        if len(hits) != 1:
            raise UnknownSession(f"session {sid}: " + (
                f"{len(hits)} app sessions start like this; give the full id" if hits
                else f"not in the app's metadata at {APP}" if os.path.isdir(APP)
                else f"this is an app id, and the app's metadata folder {APP} is absent")
                + ". Pass the transcript id, or set ORCHESTRATE_APP_SESSIONS to the folder.")
    if not hits:
        found = [sid] if sid in tops or sid in apps_by_cli else sorted(t for t in tops if sid in t)
        if len(found) != 1 or found[0] not in apps_by_cli:
            return None, found
        hits = [apps_by_cli[found[0]]]
    return hits[0], apps[hits[0]]["cli"]


# --- Reading transcripts
def records(f):
    """Yield (kind, id, time, line as dict) for the assistant messages and compaction marks of one file."""
    with open(f, errors="replace") as fh:
        for line in fh:
            if not ('"usage"' in line and '"assistant"' in line) and '"compact_boundary"' not in line:
                continue
            try:
                d = json.loads(line)
                if d.get("type") == "system" and d.get("subtype") == "compact_boundary":
                    yield "compact", d["uuid"], parse_time(d["timestamp"]), d
                elif d.get("type") == "assistant" and d["message"].get("model") and not d["message"]["model"].startswith("<"):
                    d["message"]["usage"].get("input_tokens")
                    yield "message", d["message"].get("id") or d["uuid"], parse_time(d["timestamp"]), d
            except Exception:
                continue


def load(sessions=None, since=None, until=None, project=None, files=None):
    """-> ([Msg], {transcript id: compactions}).

    Forked and resumed sessions start with a copy of the old messages, so every id counts once over all files.
    It goes to the session named in the record if that one has a copy (a fork keeps the name); when each copy
    names its own file (a resume rewrites it), to the oldest file. `sessions` filters after that."""
    copies, born = {}, {}
    files = transcript_files() if files is None else files
    if sessions is not None:         # a file untouched since before their first message cannot share messages with them
        starts = [r[2] for f in files if f[2] in sessions for r in itertools.islice(records(f[0]), 1)]
        if not starts:
            return [], {}
        since = max(since, min(starts)) if since else min(starts)
    for f, proj, top, sub in files:
        try:
            st = os.stat(f)
        except OSError:
            continue
        if since and datetime.fromtimestamp(st.st_mtime, timezone.utc) < since:
            continue
        last = None
        for kind, mid, ts, d in records(f):
            last = max(last, ts) if last else ts
            if (since and ts < since) or (until and ts > until):
                continue
            copies.setdefault((kind, mid), []).append((top, d.get("sessionId"), proj, sub, ts, slim(d)))
        if last and not sub:         # no birth time on this system -> the file that stopped first
            born[top] = min(born.get(top, (float("inf"),)), (getattr(st, "st_birthtime", 0), last.timestamp()))
    rows, compacts = [], {}
    for (kind, _), cs in copies.items():
        tops = {c[0] for c in cs}
        named = {c[1] for c in cs} & tops
        owner = min(named or tops, key=lambda t: (born.get(t, (float("inf"),)), t))
        mine = [c for c in cs if c[0] == owner]
        proj, sub = mine[0][2], all(c[3] for c in mine)
        if (sessions is not None and owner not in sessions) or (project and project not in proj):
            continue
        if kind == "compact":
            compacts[owner] = compacts.get(owner, 0) + (not sub)
            continue
        top, _, _, _, ts, (model, effort, side, u) = max(cs, key=lambda c: c[5][3][1])  # the fullest copy
        rows.append(Msg(owner, proj, model, ts, *u, sub or side, effort))
    return rows, compacts


def slim(d):
    """The model, effort, sidechain flag and five token counts of an assistant record."""
    m = d.get("message") or {}
    u = m.get("usage") or {}
    cc = u.get("cache_creation") or {}
    cw1 = cc.get("ephemeral_1h_input_tokens") or 0
    cw5 = cc.get("ephemeral_5m_input_tokens")
    if cw5 is None:
        cw5 = (u.get("cache_creation_input_tokens") or 0) - cw1
    return m.get("model"), d.get("effort") or "", bool(d.get("isSidechain")), (
        u.get("input_tokens") or 0, u.get("output_tokens") or 0, u.get("cache_read_input_tokens") or 0, cw5, cw1)


def top_of(counts):
    return max(sorted(counts), key=counts.get) if counts else ""


def group(rows, key):
    """Sum message rows into {key(row): stats}. Model, effort and peak context are the main thread's."""
    out = {}
    for r in rows:
        k = key(r)
        s = out.setdefault(k, dict(key=k, session=r.session, project=r.project, input=0, output=0, cache_read=0,
                                   cache_write=0, messages=0, weighted=0.0, sub_weighted=0.0, sub_messages=0,
                                   peak_context=0, models={}, main={}, efforts={}, sessions=set(),
                                   first=r.ts, last=r.ts, unpriced=False, priced_as=None))
        w = weigh(r.model, r.input, r.output, r.cache_read, r.cw5, r.cw1)
        s["input"] += r.input; s["output"] += r.output; s["cache_read"] += r.cache_read
        s["cache_write"] += r.cw5 + r.cw1; s["messages"] += 1; s["weighted"] += w
        s["models"][r.model] = s["models"].get(r.model, 0) + 1
        if r.sub:
            s["sub_weighted"] += w; s["sub_messages"] += 1
        else:
            s["main"][r.model] = s["main"].get(r.model, 0) + 1
            s["efforts"][r.effort] = s["efforts"].get(r.effort, 0) + 1
            s["peak_context"] = max(s["peak_context"], r.input + r.cache_read + r.cw5 + r.cw1)
        s["sessions"].add(r.session)
        s["first"], s["last"] = min(s["first"], r.ts), max(s["last"], r.ts)
        s["priced_as"] = s["priced_as"] or price(r.model)[1]
    for s in out.values():
        s["model"], s["effort"] = top_of(s.pop("main") or s["models"]), top_of(s.pop("efforts"))
        s["sessions"], s["unpriced"] = len(s["sessions"]), bool(s["priced_as"])
    return out


def scan(session=None, since=None, until=None, project=None, merge=False):
    """-> {transcript id: stats}; merge=True sums all transcripts of the one session under its current id."""
    files, apps, ids = transcript_files(), app_sessions(), None
    if session:
        try:
            aid, ids = resolve(session, apps, {f[2] for f in files})
        except UnknownSession as e:
            sys.exit(str(e))
        if merge and not aid and len(ids) > 1:
            sys.exit(f"{len(ids)} transcripts match '{session}'; give the full id")
    rows, _ = load(ids, since, until, project, files)
    out = group(rows, key=lambda r: ids[-1] if merge else r.session)
    names = app_of(apps)
    for k, s in out.items():
        s["session"], s["app_session"] = k, names.get(k)
    return out


def fmt(n):
    n = float(n)
    return f"{n/1e6:.2f}M" if n >= 1e6 else f"{n/1e3:.0f}k" if n >= 1e4 else f"{n:.0f}"


def read_jsonl(path):
    return [r for _, r in read_lines(path) if r is not None]


def read_lines(path):
    """-> [(line, object or None if the line is not a JSON object)]; a missing file is empty."""
    out = []
    try:
        with open(path, errors="surrogateescape") as fh:
            lines = [l for l in fh.read().split("\n") if l.strip()]
    except OSError:
        return out
    for l in lines:
        try:
            r = json.loads(l)
        except ValueError:
            r = None
        out.append((l, r if isinstance(r, dict) else None))
    return out


@contextlib.contextmanager
def locked():
    """`sync` rewrites the log that `log` appends to, and hooks may start two syncs at once."""
    os.makedirs(HOME, exist_ok=True)
    with open(os.path.join(HOME, ".lock"), "w") as fh:
        try:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass                     # no file locks on this system
        yield


def append(path, rec):
    with locked(), open(path, "a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def is_old(rec):
    return rec.get("schema") != SCHEMA or rec.get("prices") != PRICES_DATE


def history(task_type=None):
    """Rows of the log. A hand-made line for a session and type that `sync` has a row for is left out."""
    rows = [r for r in read_jsonl(LOG) if "actual" in r and (not task_type or r.get("task_type") == task_type)]
    synced = {(t, r.get("task_type")) for r in rows if r.get("source") == "sync" for t in r.get("sessions") or []}
    return [r for r in rows if r.get("source") == "sync" or (r.get("session"), r.get("task_type")) not in synced]


def warn_old_cal(c):
    if is_old(c):
        print(f"  warning: the {c['date']} calibration uses old accounting (other prices, or no subagents), so these "
              "percents are off; run `calibrate` with two new readings")


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


def share(s):
    return f"{100 * s['sub_weighted'] / s['weighted'] if s['weighted'] else 0:.0f}%"


def cmd_tokens(a):
    me = getattr(a, "self", False)
    rows = sorted(scan(own_session(a), a.since, a.until, a.project, merge=me).values(), key=lambda s: -s["weighted"])
    if a.json:
        dump(rows); return
    if me and rows:
        s = rows[0]
        mins = (s["last"] - s["first"]).total_seconds() / 60
        print(f"tokens: in {fmt(s['input'])}, out {fmt(s['output'])}, cache read {fmt(s['cache_read'])}, "
              f"cache write {fmt(s['cache_write'])}; weighted {fmt(s['weighted'])}; "
              f"{s['messages']} messages over {mins:.0f} min; {s['model']}"
              + (f"; subagents {share(s)}" if s["sub_messages"] else ""))
        return
    print(f"{'session':36} {'msgs':>5} {'input':>7} {'output':>7} {'c.read':>8} {'c.write':>8} {'weighted':>9} {'sub':>4}  model")
    for s in rows[: a.top]:
        print(f"{s['session']:36} {s['messages']:5} {fmt(s['input']):>7} {fmt(s['output']):>7} "
              f"{fmt(s['cache_read']):>8} {fmt(s['cache_write']):>8} {fmt(s['weighted']):>9} {share(s) if s['sub_messages'] else '-':>4}  {s['model']}"
              + (f"  (price unknown, used {s['priced_as']})" if s["unpriced"] else ""))
    t, sub = sum(s["weighted"] for s in rows), sum(s["sub_weighted"] for s in rows)
    print(f"{len(rows)} sessions, total weighted {fmt(t)} (1 = one Sonnet 5.5 input token); "
          f"subagents {fmt(sub)} ({share(dict(weighted=t, sub_weighted=sub))})")


def cmd_days(a):
    def day(r):
        return r.ts.astimezone().date().isoformat()
    rows = sorted(group(load(None, a.since, a.until, a.project)[0], key=day).values(), key=lambda s: s["key"])
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
        warn_old_cal(c)


def cmd_review(a):
    rows = history(a.type)
    if not rows:
        print("no estimate lines yet"); return
    inside = judged = 0
    for r in rows:
        head = f"{r['ts'][:10]}  {r['task_type']:12} {r.get('size') or '-':3} "
        if not r.get("estimate"):
            print(f"{head}{'no estimate':>15} actual {fmt(r['actual']):>7}"); continue
        lo, hi = r["estimate"]
        mark = "inside" if lo <= r["actual"] <= hi else ("over" if r["actual"] > hi else "under")
        inside += mark == "inside"; judged += 1
        print(f"{head}{fmt(lo):>7}-{fmt(hi):<7} actual {fmt(r['actual']):>7}  {mark}"
              + ("  (old accounting)" if is_old(r) else ""))
    print(f"{inside} of {judged} inside the estimate")


def cmd_log(a):
    s = next(iter(scan(a.session, a.since, a.until, merge=True).values()), None)
    if not s:
        sys.exit("no transcript found for that session")
    rec = dict(ts=datetime.now(timezone.utc).isoformat(timespec="seconds"), session=s["session"],
               app_session=s["app_session"], task_type=a.type, model=s["model"], effort=a.effort or s["effort"],
               messages=s["messages"], weighted=round(s["weighted"]), sub_weighted=round(s["sub_weighted"]),
               estimate=[a.est[0], a.est[1]], actual=round(s["weighted"]), size=a.size,
               source="log", schema=SCHEMA, prices=PRICES_DATE)
    append(LOG, rec)
    inside = "inside" if a.est[0] <= rec["actual"] <= a.est[1] else "OUTSIDE"
    print(f"logged: {a.type}, actual {fmt(rec['actual'])} vs estimate {fmt(a.est[0])}-{fmt(a.est[1])} ({inside})")


# --- sync
def runs(events):
    """Task events -> [run]: the plan, the bound sessions and the outcome of one go at a task.

    Several binds are one run (a failed task goes on in a fresh session); a plan after an outcome starts another."""
    out, live = [], {}
    for e in events:
        task, kind = e.get("task"), e.get("event")
        if not isinstance(task, str) or kind not in ("plan", "bind", "outcome"):
            continue
        r = live.get(task)
        if r is None or (kind == "plan" and r["outcome"]):
            r = live[task] = dict(task=task, run=r["run"] + 1 if r else 1, plan={}, binds=[], outcome={})
            out.append(r)
        if kind == "bind":
            if isinstance(e.get("session"), str) and e["session"]:
                r["binds"] = [b for b in r["binds"] if b != e["session"]] + [e["session"]]
        else:
            r[kind] = e
    return out


def last_message(files):
    return max((ts for f in files for _, _, ts, _ in records(f[0])), default=None)


def cmd_sync(a):
    say = (lambda *x: None) if a.quiet else print
    todo = [r for r in runs(read_jsonl(ROUTES)) if r["binds"]]
    if not todo:
        say("sync: no bound tasks in routes.jsonl"); return
    files, apps = transcript_files(), app_sessions()
    if not apps:
        say(f"sync: no app metadata at {APP} (ORCHESTRATE_APP_SESSIONS): app ids cannot be found, "
            f"a session counts as ended after {IDLE_HOURS} idle hours")
    tops, by_top, archived = {f[2] for f in files}, {}, {t for x in apps.values() if x["archived"] for t in x["cli"]}
    for f in files:
        by_top.setdefault(f[2], []).append(f)
    with locked():
        lines = read_lines(LOG)
        at = {(r.get("task"), r.get("run")): n for n, (_, r) in enumerate(lines) if r and r.get("source") == "sync"}
        loaded, done, changed = None, 0, 0
        for run in todo:
            aid, ids, bad = None, [], []
            for b in run["binds"]:
                try:
                    aid, found = resolve(b, apps, tops)
                except UnknownSession as e:
                    bad.append(str(e)); continue
                if not aid and len(found) != 1:
                    bad.append(f"session {b}: {len(found)} transcripts match"); continue
                ids = [t for t in ids if t not in found] + found
            mine = [f for t in ids for f in by_top.get(t, [])]
            n = at.get((run["task"], run["run"]))
            old = lines[n][1] if n is not None else {}
            kept = {k: old.get(k) for k in FACTS} if old and old.get("sessions") == ids and not is_old(old) else None
            if bad or not (mine or kept):
                say(f"sync: {run['task']}: skipped, " + ("; ".join(bad) or "no transcript")); continue
            # A stamp of the files tells a finished row from one to count again (the count reads every transcript).
            stamp = [len(mine)] + [max((getattr(os.stat(f[0]), k) for f in mine), default=0)
                                   for k in ("st_mtime_ns", "st_size")]
            if kept and (not mine or kept["stamp"] == stamp):
                facts = kept
            else:
                last = last_message(mine)
                waiting = [t for t in ids if t in by_top and t not in archived]
                if not last or (waiting and datetime.now(timezone.utc) - (
                        last_message([f for t in waiting for f in by_top[t]]) or last) < timedelta(hours=IDLE_HOURS)):
                    say(f"sync: {run['task']}: still running"); continue
                loaded = loaded or load(files=files)
                facts = count(ids, loaded, stamp)
                if kept and (not facts or facts["messages"] < kept["messages"]):
                    facts = kept     # old transcripts get cleaned up; keep the full count
                if not facts:
                    say(f"sync: {run['task']}: skipped, no counted messages"); continue
            row = outcome_row(run, aid, ids, facts, lines)
            done += 1
            if row == old:
                continue
            changed += 1
            entry = (json.dumps(row, ensure_ascii=False), row)
            if n is None:
                at[(run["task"], run["run"])] = len(lines)
                lines.append(entry)
            else:
                lines[n] = entry
        if changed:
            tmp = LOG + ".tmp"
            with open(tmp, "w", errors="surrogateescape") as fh:
                fh.write("".join(l + "\n" for l, _ in lines))
            os.replace(tmp, LOG)
    say(f"sync: {done} finished tasks, {changed} rows written")


FACTS = ("ts", "model", "effort", "models", "messages", "sub_messages", "weighted", "sub_weighted", "peak_context",
         "compactions", "stamp")


def count(ids, loaded, stamp):
    rows, compacts = loaded
    s = group([r for r in rows if r.session in ids], key=lambda r: 0).get(0)
    # the model and effort of the last session: the ones the task ended on
    own = group([r for r in rows if r.session == ids[-1]], key=lambda r: 0).get(0) or s
    return s and dict(ts=s["last"].astimezone(timezone.utc).isoformat(timespec="seconds"), model=own["model"],
                      effort=own["effort"], models=s["models"], messages=s["messages"], sub_messages=s["sub_messages"],
                      weighted=round(s["weighted"]), sub_weighted=round(s["sub_weighted"]),
                      peak_context=s["peak_context"], compactions=sum(compacts.get(t, 0) for t in ids), stamp=stamp)


def outcome_row(run, aid, ids, facts, lines):
    plan, out = run["plan"], run["outcome"]
    kind = plan.get("type") if isinstance(plan.get("type"), str) else "unknown"
    est = [r["estimate"] for _, r in lines if r and r.get("source") != "sync" and r.get("session") in ids
           and r.get("task_type") == kind and r.get("estimate")]
    row = dict(source="sync", schema=SCHEMA, prices=PRICES_DATE, task=run["task"], run=run["run"], session=ids[-1],
               app_session=aid, sessions=ids, task_type=kind, size=plan.get("size"), planned_model=plan.get("model"),
               planned_effort=plan.get("effort"), estimate=est[-1] if est else None, actual=facts["weighted"], **facts)
    for src, keys in ((plan, ("override",)), (out, ("result", "rounds", "p0p1"))):
        row.update({k: src[k] for k in keys if k in src})
    return row


def cmd_estimate(a):
    rows = history(a.type)
    new = [r for r in rows if not is_old(r)]
    rows = new if len(new) >= MIN_LINES else rows
    for field, want in (("size", a.size), ("model", a.model)):
        same = [r for r in rows if want and r.get(field) == want]
        rows = same if len(same) >= MIN_LINES else rows
    if len(rows) >= MIN_LINES:
        v = sorted(r["actual"] for r in rows)
        lo, hi = v[len(v) // 4], v[-1 - len(v) // 4]
        src = f"{len(rows)} past '{a.type}' sessions (middle half of actuals)"
        old = sum(map(is_old, rows))
        src += f"; {old} of them by old accounting (other prices, or no subagents)" if old else ""
    else:
        if not (a.ctx and a.steps):
            sys.exit(f"only {len(rows)} past '{a.type}' lines (need {MIN_LINES}): too little history. "
                     "Give --ctx <context tokens> and --steps LO-HI to use context size x steps.")
        s_lo, s_hi = (int(x) for x in a.steps.split("-"))
        (pi, po, pr), _ = price(a.model or UNKNOWN, a.ctx)
        per = (a.ctx * pr + STEP_OUT * po + STEP_GROW * pi * W1H) / BASE
        lo, hi = per * s_lo, per * s_hi
        src = f"too little history ({len(rows)} lines): context {fmt(a.ctx)} x {s_lo}-{s_hi} steps"
    print(f"estimate {fmt(lo)} - {fmt(hi)} weighted  [{src}]")
    c = latest_cal(a.window)
    if c:
        print(f"  = {lo / c['per_pct']:.1f} - {hi / c['per_pct']:.1f}% of the limit "
              f"(calibration {c['date']}: {fmt(c['per_pct'])} per 1%, window '{c.get('window', '?')}')")
        warn_old_cal(c)
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
           "to": t2.isoformat(), "pct": d, "weighted": round(tot), "per_pct": round(tot / d),
           "schema": SCHEMA, "prices": PRICES_DATE}
    append(CAL, rec)
    print(f"{fmt(tot)} weighted over {d:g}% -> {fmt(rec['per_pct'])} per 1% (saved {rec['date']}). "
          f"Whole-percent readings: about +-{100 / d:.0f}% error here; other machines are not counted.")


def cmd_calibration(a):
    for c in read_jsonl(CAL):
        print(f"{c['date']}  {c['pct']:g}% = {fmt(c['weighted'])}  -> {fmt(c['per_pct'])}/1%  [{c.get('window', '?')}]"
              + ("  old accounting (other prices, or no subagents)" if is_old(c) else f"  prices {c['prices']}"))
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
    y = sub.add_parser("sync"); y.add_argument("--quiet", action="store_true", help="print nothing")
    y.set_defaults(f=cmd_sync)
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
