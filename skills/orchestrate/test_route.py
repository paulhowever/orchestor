"""Tests for route.py and routes.json. Run: python3 skills/orchestrate/test_route.py

Expected cells use tier names, not model names: those live only in routes.json."""
import copy, itertools, json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "route.py")
sys.path.insert(0, HERE)
import route  # noqa: E402

DATA = route.load()
MODEL = {t["tier"]: t["model"] for t in DATA["tiers"]}
TIER = {t["model"]: t["tier"] for t in DATA["tiers"]}
RANK = {t["tier"]: i for i, t in enumerate(DATA["tiers"])}
SITES = ["unknown", 0, 1, 2, 3, 4, 50]
RISKS = [["data"], ["auth"], ["money"], ["public-api"], ["hard-to-undo"], ["data", "money"]]


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def card(kind, size="M", sites=2, spec="agreed", verifier="exists", risk=()):
    return dict(kind=kind, size=size, sites=sites, spec=spec, verifier=verifier, risk=list(risk))


def cards(sizes=("S", "M", "L"), risks=([],)):
    for k, s, n, p, v, r in itertools.product(route.KINDS, sizes, SITES, route.SPECS, route.VERIFIERS, risks):
        yield card(k, s, n, p, v, r)


def ladder(c, data=DATA):
    return [r.name for r in route.choose(data, c).ladder]


def first(c, data=DATA):
    return route.choose(data, c).rung.name


DOCS = ["cheap/medium", "cheap/high"]
SMALL = ["cheap/high", "strong/high"]
FEATURE = ["strong/medium", "strong/high"]
COMPLETE = ["strong/medium", "strong/high", "top/high"]
OPEN = ["strong/high", "top/high"]
WEB = ["cheap/medium", "strong/medium"]


class Table(unittest.TestCase):
    """Every cell of the table, with its ladder."""

    CELLS = [
        (card("docs-config"), DOCS), (card("docs-config", "L", 9), DOCS), (card("docs-config", "S", "unknown"), DOCS),
        (card("rename", sites=40), DOCS), (card("rename", sites=2, verifier="can-be-written"), DOCS),
        (card("rename", sites="unknown"), COMPLETE),              # no full list of places
        (card("fix-known-cause", "S", 1), SMALL), (card("fix-known-cause", "S", 2), SMALL),
        (card("feature", "S", 1), SMALL), (card("feature", "S", 2), SMALL),
        (card("fix-known-cause", "S", 3), FEATURE), (card("feature", "S", 3), FEATURE),
        (card("feature", "S", "unknown"), FEATURE), (card("fix-known-cause", "S", "unknown"), FEATURE),
        (card("feature", "S", 1, verifier="can-be-written"), FEATURE),
        (card("feature", "M", 1), FEATURE), (card("feature", "L", 6), FEATURE),
        (card("fix-known-cause", "M", 1), FEATURE), (card("fix-known-cause", "L", 6), FEATURE),
        (card("refactor"), COMPLETE), (card("tests"), COMPLETE), (card("migration"), COMPLETE), (card("ui"), COMPLETE),
        (card("fix-unknown-cause"), OPEN), (card("fix-unknown-cause", "S", 1), OPEN), (card("design"), OPEN),
        (card("code-research"), FEATURE), (card("web-research"), WEB), (card("review"), FEATURE),
    ] + [(card(k, spec="open"), OPEN) for k in route.KINDS]

    def test_cells(self):
        for c, want in self.CELLS:
            with self.subTest(c):
                self.assertEqual(ladder(c), want)
                self.assertEqual(first(c), want[0])

    def test_cells_cover_every_kind_route_and_rung(self):
        self.assertEqual({c["kind"] for c, _ in self.CELLS}, set(route.KINDS))
        self.assertEqual({route.choose(DATA, c).route["id"] for c, _ in self.CELLS}, {r["id"] for r in DATA["routes"]})

    def test_every_card_has_a_route(self):
        for c in cards():
            self.assertTrue(ladder(c), c)

    def test_checklist(self):
        for k in route.KINDS:
            want = k in ("refactor", "tests", "migration", "ui")
            self.assertEqual(bool(route.choose(DATA, card(k)).route.get("checklist")), want, k)

    def test_code_research_never_smallest(self):
        for c in cards():
            if c["kind"] == "code-research":
                for r in ladder(c):
                    self.assertFalse(r.startswith("smallest"), c)

    def test_model_names_only_in_data(self):
        names = [x for t in DATA["tiers"] for x in (t["model"], t["label"], t["label"].split()[0])]
        for f in (SCRIPT, os.path.abspath(__file__)):
            text = read(f).lower()
            for n in names:
                self.assertNotIn(n.lower(), text, f)


class HardRules(unittest.TestCase):
    def check(self, data):
        rank = {t["tier"]: i for i, t in enumerate(data["tiers"])}
        n = 0
        for c in cards(risks=[[]] + RISKS):
            p = route.choose(data, c)
            risky, blind = bool(c["risk"]), c["verifier"] == "human-only"
            if risky or blind:
                n += 1
                self.assertGreaterEqual(rank[p.rung.tier], rank["strong"], c)
            if risky:
                self.assertGreaterEqual(route.EFFORTS.index(p.rung.effort), route.EFFORTS.index("high"), c)
            self.assertEqual(p.review, risky, c)
            if risky or blind:
                self.assertIsNone(p.next, c)       # escalation is never automatic here
        self.assertGreater(n, 1000)

    def test_risky_or_unverifiable_never_cheap(self):
        self.check(DATA)

    def test_hold_whatever_the_table_says(self):
        for rung in ("smallest/low", "cheap/medium", "cheap/max", "strong/low", "top/low"):
            bad = copy.deepcopy(DATA)
            for r in bad["routes"]:
                r["ladder"] = [rung]
            with self.subTest(rung):
                self.check(bad)

    def test_human_only_is_one_rung_up(self):
        for c, want in [(card("feature", "S", 1), "strong/high"), (card("feature"), "strong/high"),
                        (card("refactor"), "strong/high"), (card("design"), "top/high"),
                        (card("web-research"), "strong/medium"),
                        (card("docs-config"), "strong/medium")]:     # the rung up is still cheap: lifted to strong
            c["verifier"] = "human-only"
            self.assertEqual(first(c), want, c)

    def test_human_only_is_never_weaker_than_with_a_check(self):
        for c in cards(risks=[[], ["auth"]]):
            if c["verifier"] == "human-only":
                base = route.choose(DATA, dict(c, verifier="exists")).rung
                self.assertGreaterEqual(route.choose(DATA, c).rung.key, base.key, c)

    def test_xl_refused(self):
        for c in cards(sizes=("XL",), risks=[[], ["data"]]):
            with self.assertRaises(route.Refused) as e:
                route.choose(DATA, c)
            self.assertIn("split", str(e.exception))


class Validate(unittest.TestCase):
    def test_shipped_data(self):
        self.assertEqual(route.problems(DATA), [])
        self.assertRegex(DATA["reviewed"], r"^\d{4}-\d\d-\d\d$")
        self.assertIn("ntested", DATA["note"])

    def broken(self, text, change):
        d = copy.deepcopy(DATA)
        change(d)
        found = route.problems(d)
        self.assertTrue(any(text in p for p in found), (text, found))

    def test_breakage_is_found(self):
        r = lambda d, i: next(x for x in d["routes"] if x["id"] == i)
        self.broken("no route", lambda d: d["routes"].remove(r(d, "review")))
        self.broken("never", lambda d: d["routes"].append(dict(r(d, "review"), id="dead")))
        self.broken("duplicate", lambda d: d["routes"].append(r(d, "review")))
        self.broken("ladder", lambda d: r(d, "review").update(ladder=[]))
        self.broken("ladder", lambda d: r(d, "review").update(ladder=["strong/high", "strong/medium"]))
        self.broken("ladder", lambda d: r(d, "review").update(ladder=["strong/low", "strong/medium", "strong/high", "top/high"]))
        self.broken("rung", lambda d: r(d, "review").update(ladder=["nope/high"]))
        self.broken("rung", lambda d: r(d, "review").update(ladder=["strong/huge"]))
        self.broken("rung", lambda d: r(d, "review").update(ladder=[7]))
        self.broken("nope", lambda d: r(d, "review").update(any=[{"kind": ["nope"]}]))
        self.broken("unknown field", lambda d: r(d, "review").update(any=[{"colour": ["red"]}]))
        self.broken("code-research", lambda d: r(d, "code-research").update(ladder=["smallest/high", "strong/high"]))
        self.broken("strong_tier", lambda d: d.update(strong_tier="nope"))
        self.broken("strong_tier", lambda d: d.update(strong_tier="cheap", tiers=d["tiers"][1:]))
        self.broken("tiers", lambda d: d.update(tiers=[]))
        self.broken("tiers", lambda d: d["tiers"].append(dict(d["tiers"][0])))
        self.broken("reviewed", lambda d: d.update(reviewed="soon"))
        self.broken("note", lambda d: d.update(note=""))
        self.broken("routes", lambda d: d.update(routes={}))
        self.broken("why", lambda d: r(d, "review").pop("why"))
        self.assertTrue(route.problems([]))

    def test_names_cannot_hide_the_cheap_tier(self):
        self.broken("strong_tier", lambda d: d.update(strong_tier="smallest"))


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "h")
        # HOME too: a bug that ignores ORCHESTRATE_HOME must not reach the real log
        self.env = dict(os.environ, ORCHESTRATE_HOME=self.home, HOME=self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *a, code=0):
        r = subprocess.run([sys.executable, SCRIPT, *map(str, a)], env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        return r.stdout + r.stderr

    def rows(self):
        p = os.path.join(self.home, "routes.jsonl")
        return [json.loads(x) for x in read(p).splitlines()] if os.path.exists(p) else []

    def pick(self, task="t1", *extra, code=0, **c):
        c = dict(card("feature", "S", 1), **c)
        risk = ["--risk", ",".join(c["risk"])] if c["risk"] else []
        return self.run_cli("pick", "--task", task, "--kind", c["kind"], "--size", c["size"], "--sites", c["sites"],
                            "--spec", c["spec"], "--verifier", c["verifier"], *risk, *extra, code=code)

    def fail(self, task="t1", ev="make test -> 1 failed", code=0):
        return self.run_cli("fail", "--task", task, "--evidence", ev, code=code)

    def last(self):
        r = self.rows()[-1]
        return r["action"], TIER.get(r["model"]), r["effort"]

    # --- pick
    def test_pick_prints_and_logs(self):
        out = self.pick()
        for want in (MODEL["cheap"], "high", "small agreed change", MODEL["strong"] + "/high",
                     "kind=feature size=S sites=1 spec=agreed verifier=exists risk=none"):
            self.assertIn(want, out)
        self.assertRegex(out, r"review required: no")
        row, = self.rows()
        self.assertEqual(set(row), {"event", "task", "ts", "type", "size", "card", "model", "effort"})
        self.assertEqual((row["event"], row["task"], row["type"], row["size"]), ("plan", "t1", "feature", "S"))
        self.assertEqual(row["card"], dict(card("feature", "S", 1)))
        self.assertEqual((row["model"], row["effort"]), (MODEL["cheap"], "high"))
        self.assertRegex(row["ts"], r"^\d{4}-\d\d-\d\dT.*(\+00:00|Z)$")

    def test_pick_sites_unknown_and_risk(self):
        out = self.pick(kind="docs-config", sites="unknown", risk=["money", "auth"])
        self.assertIn("review required: yes", out)
        self.assertIn("the user", out)
        row, = self.rows()
        self.assertEqual((row["model"], row["effort"]), (MODEL["strong"], "high"))
        self.assertEqual(row["card"]["sites"], "unknown")
        self.assertEqual(row["card"]["risk"], ["auth", "money"])

    def test_checklist_line(self):
        self.assertIn("completeness checklist", self.pick(kind="refactor").lower())
        self.assertNotIn("completeness checklist", self.pick("t2").lower())

    def test_xl(self):
        self.assertIn("split", self.pick(size="XL", code=1))
        self.assertIn("split", self.pick("t1", "--override", "strong/high", "--reason", "x", size="XL", code=1))
        self.assertEqual(self.rows(), [])

    def test_dry_run_writes_nothing(self):
        self.pick("t1", "--dry-run")
        self.assertFalse(os.path.exists(self.home))

    def test_parent_effort(self):
        for parent, told in (("low", True), ("medium", True), ("high", False), ("xhigh", False)):
            out = self.pick("t1", "--parent-effort", parent)
            self.assertEqual("start_session" in out, told, parent)
            if told:
                self.assertRegex(out, "user decides")
        self.assertNotIn("start_session", self.pick())

    def test_bad_values(self):
        for k, v in (("kind", "x"), ("size", "XXL"), ("sites", "-1"), ("sites", "few"), ("spec", "x"),
                     ("verifier", "x"), ("risk", ["x"]), ("risk", ["none", "auth"])):
            self.pick(code=2, **{k: v})
        for slug in ("", "a b", "../x", "x" * 65, "ghp_" + "a" * 36, "deadbeef" * 5):
            self.pick(slug, code=2)
        self.assertEqual(self.rows(), [])

    # --- override
    def test_override_needs_a_reason(self):
        self.pick("t1", "--override", "strong/high", code=2)
        self.pick("t1", "--override", "strong/high", "--reason", "  ", code=2)
        self.pick("t1", "--reason", "why", code=2)
        for bad in ("strong", "nope/high", "strong/huge", "a/b/c"):
            self.pick("t1", "--override", bad, "--reason", "x", code=2)
        self.assertEqual(self.rows(), [])

    def test_override_recorded(self):
        for name in ("top", MODEL["top"]):
            out = self.pick("t1", "--override", name + "/high", "--reason", "long unattended run")
            self.assertNotIn("WARNING", out)
            row = self.rows()[-1]
            self.assertEqual((row["model"], row["effort"]), (MODEL["top"], "high"))
            self.assertEqual(row["override"], {"from": MODEL["cheap"] + "/high", "reason": "long unattended run",
                                               "warnings": []})

    def test_override_below_a_hard_rule_warns(self):
        for c, o in ((dict(risk=["data"]), "cheap/max"), (dict(risk=["data"]), "strong/medium"),
                     (dict(verifier="human-only"), "cheap/high")):
            out = self.pick("t1", "--override", o, "--reason", "budget", **c)
            self.assertIn("WARNING", out)
            self.assertEqual(len(self.rows()[-1]["override"]["warnings"]), 1)
            self.assertIn("review required: " + ("yes" if c.get("risk") else "no"), out)

    # --- bind, outcome
    def test_bind_and_outcome_rows(self):
        self.pick()
        self.run_cli("bind", "--task", "t1", "--session", "local_76b00180-1615")
        self.run_cli("outcome", "--task", "t1", "--result", "landed", "--rounds", 2, "--p0p1", 1)
        self.run_cli("outcome", "--task", "t1", "--result", "reverted")
        _, b, o, o2 = self.rows()
        self.assertEqual({k: b[k] for k in b if k != "ts"},
                         {"event": "bind", "task": "t1", "session": "local_76b00180-1615"})
        self.assertEqual({k: o[k] for k in o if k != "ts"},
                         {"event": "outcome", "task": "t1", "result": "landed", "rounds": 2, "p0p1": 1})
        self.assertEqual(set(o2), {"event", "task", "ts", "result"})

    def test_unplanned_task_refused(self):
        self.run_cli("bind", "--task", "nope", "--session", "s", code=1)
        self.run_cli("outcome", "--task", "nope", "--result", "landed", code=1)
        self.fail("nope", code=1)
        self.pick()
        self.run_cli("bind", "--task", "t1", "--session", "a b", code=2)
        self.run_cli("outcome", "--task", "t1", "--result", "won", code=2)
        self.run_cli("outcome", "--task", "t1", "--result", "landed", "--rounds", "-1", code=2)
        self.assertEqual(len(self.rows()), 1)

    def test_dry_run_everywhere(self):
        self.pick()
        self.run_cli("bind", "--task", "t1", "--session", "s", "--dry-run")
        self.run_cli("outcome", "--task", "t1", "--result", "landed", "--dry-run")
        self.run_cli("fail", "--task", "t1", "--evidence", "a -> b", "--dry-run")
        self.assertEqual(len(self.rows()), 1)

    # --- fail
    def test_fail_needs_evidence(self):
        self.pick()
        self.run_cli("fail", "--task", "t1", code=2)
        for ev in ("", "  ", "it does not work", "->", "make test ->", "-> failed", "make test → "):
            self.fail(ev=ev, code=2)
        self.fail(ev="curl -H 'Authorization: Bearer abcdef123456789' → 401", code=2)
        self.fail(ev="x → " + "y" * 400, code=2)
        self.assertEqual(len(self.rows()), 1)

    def test_secrets_refused_plain_text_is_not(self):
        for bad in ("sk-ant-api03-abcdefgh1234", "ghp_abc123def456ghi", "AKIAABCDEFGHIJKLMNOP", "-----BEGIN PRIVATE KEY",
                    "https://me:pw@host", "API_KEY=abcd1234", "password: hunter2", "Bearer abcdef123456789"):
            with self.assertRaises(route.argparse.ArgumentTypeError, msg=bad):
                route.evidence("curl -> " + bad)
        for good in ("basic functionality broken", "SyntaxError: Unexpected token: punc", "sk-learn-pipeline failed"):
            self.assertIn(good, route.evidence("make test -> " + good))

    def test_ladder_retry_then_fresh_session_then_stop(self):
        self.pick()                                        # cheap/high, strong/high
        out = self.fail(ev="make  test →\n 1 failed")
        self.assertEqual(self.last(), ("retry", "cheap", "high"))
        self.assertIn("same session", out)
        row = self.rows()[-1]
        self.assertEqual(set(row), {"event", "task", "ts", "action", "model", "effort", "from", "climbs", "evidence"})
        self.assertEqual((row["event"], row["climbs"], row["evidence"]), ("escalate", 0, "make test → 1 failed"))
        out = self.fail()
        self.assertEqual(self.last(), ("fresh-session", "strong", "high"))
        self.assertIn("fresh session", out)
        out = self.fail()                                  # no rung left
        self.assertEqual(self.last(), ("stop", "strong", "high"))
        self.assertRegex(out, "split.*user")
        self.fail()
        self.assertEqual(self.last()[0], "stop")

    def test_raise_effort_in_same_session_then_fresh_then_cap(self):
        self.pick(kind="refactor")                         # strong/medium, strong/high, top/high
        self.fail()
        self.assertEqual(self.last(), ("retry", "strong", "medium"))
        self.assertIn("same session", self.fail())
        self.assertEqual(self.last(), ("raise-effort", "strong", "high"))
        self.assertIn("fresh session", self.fail())
        self.assertEqual(self.last(), ("fresh-session", "top", "high"))
        self.assertEqual(self.rows()[-1]["climbs"], 2)
        self.fail()
        self.assertEqual(self.last()[0], "stop")

    def test_cap_survives_a_new_pick(self):
        self.pick(kind="refactor")
        for _ in range(3):
            self.fail()
        self.pick(kind="refactor")                         # back at the first rung, two climbs already used
        self.fail()
        self.assertEqual(self.last()[0], "stop")

    def test_cap_holds_below_the_table(self):
        self.pick("t1", "--override", "smallest/low", "--reason", "trial", kind="refactor")
        for _ in range(4):
            self.fail()
        self.assertEqual([r["action"] for r in self.rows() if r["event"] == "escalate"],
                         ["retry", "fresh-session", "raise-effort", "stop"])

    def test_override_above_the_table(self):
        self.pick("t1", "--override", "top/max", "--reason", "x")
        self.fail()
        self.fail()
        self.assertEqual(self.last()[0], "stop")

    def test_outcome_closes_the_task(self):
        self.pick()
        self.fail()
        self.run_cli("outcome", "--task", "t1", "--result", "dropped")
        self.fail(code=1)
        self.pick()
        self.fail()
        self.assertEqual(self.last()[0], "retry")          # counts start again

    def test_risk_and_human_only_go_to_the_user(self):
        for i, c in enumerate((dict(risk=["auth"]), dict(verifier="human-only"))):
            t = "r%d" % i
            before = self.pick(t, **c)
            self.assertRegex(before, "next.*user")
            out = self.fail(t)
            self.assertIn("ask the user", out.lower())
            self.assertEqual(self.last()[0], "ask-user")
            self.assertEqual(self.rows()[-1]["climbs"], 0)

    def test_dropping_a_risk_flag_is_called_out(self):
        self.pick(risk=["auth", "data"])
        out = self.pick(risk=["data"])
        self.assertRegex(out, "WARNING.*auth")

    def test_tasks_do_not_mix(self):
        self.pick("a")
        self.pick("b")
        self.fail("a")
        self.fail("b")
        self.assertEqual(self.last()[0], "retry")

    def test_broken_log_lines(self):
        self.pick()
        with open(os.path.join(self.home, "routes.jsonl"), "a") as f:
            f.write('not json\n[1]\n{"event": "plan"}\n{"event": "plan", "task": "t1", "card": 3}\n{"event": "pl')
        self.fail()
        lines = read(os.path.join(self.home, "routes.jsonl")).splitlines()
        self.assertEqual(json.loads(lines[-1])["action"], "retry")

    # --- table, validate
    def test_table_and_validate(self):
        out = self.run_cli("table")
        for r in DATA["routes"]:
            self.assertIn(r["id"], out)
        for t in ("cheap", "strong", "top"):
            self.assertIn(MODEL[t], out)
        self.assertIn(DATA["reviewed"], out)
        self.assertIn("ok", self.run_cli("validate"))
        bad = os.path.join(self.tmp.name, "bad.json")
        for text in ("{", "[]", '{"routes": []}'):
            with open(bad, "w") as f:
                f.write(text)
            self.run_cli("validate", bad, code=1)
        self.run_cli("validate", os.path.join(self.tmp.name, "missing.json"), code=1)
        self.assertFalse(os.path.exists(self.home))


if __name__ == "__main__":
    unittest.main()
