"""Tests for usage.py on synthetic transcripts. Run: python3 -m unittest skills/orchestrate/test_usage.py"""
import json, os, subprocess, sys, tempfile, unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "usage.py")


def line(sid, mid, model, ts, i=10, o=100, cr=1000, cw5=0, cw1=0, effort="high"):
    return json.dumps({"type": "assistant", "sessionId": sid, "timestamp": ts.isoformat(), "effort": effort, "message": {
        "id": mid, "model": model, "content": [{"type": "text", "text": "SECRET TEXT"}],
        "usage": {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cr,
                  "cache_creation_input_tokens": cw5 + cw1,
                  "cache_creation": {"ephemeral_5m_input_tokens": cw5, "ephemeral_1h_input_tokens": cw1}}}})


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = dict(os.environ, ORCHESTRATE_PROJECTS=os.path.join(self.tmp.name, "p"),
                        ORCHESTRATE_HOME=os.path.join(self.tmp.name, "h"),
                        ORCHESTRATE_APP_SESSIONS=os.path.join(self.tmp.name, "app"))
        self.env.pop("CLAUDE_CODE_SESSION_ID", None)
        os.makedirs(os.path.join(self.tmp.name, "p", "proj"))
        now = datetime.now(timezone.utc)
        self.now = now
        rows = [line("s1", "m1", "claude-sonnet-5-5", now - timedelta(hours=5), i=1000000, o=0, cr=0),
                line("s1", "m1", "claude-sonnet-5-5", now - timedelta(hours=5), i=1000000, o=0, cr=0),  # duplicate id
                line("s1", "m2", "claude-sonnet-5-5", now - timedelta(hours=1), i=0, o=1000000, cr=0),
                line("s2", "m3", "claude-opus-5-5", now - timedelta(hours=1), i=0, o=0, cr=1000000, cw1=1000000)]
        for sid, sel in (("s1", rows[:3]), ("s2", rows[3:])):
            with open(os.path.join(self.tmp.name, "p", "proj", sid + ".jsonl"), "w") as f:
                f.write("\n".join(sel) + "\nnot json\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *a, ok=True):
        r = subprocess.run([sys.executable, SCRIPT, *a], env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode == 0, ok, r.stdout + r.stderr)
        return r.stdout + r.stderr

    def rows(self, *a):
        return {s["session"]: s for s in json.loads(self.run_cli("tokens", "--json", *a))}

    def test_weights_and_dedupe(self):
        r = self.rows()
        # Sonnet: 1M input = 1M, 1M output = 5M weighted; the duplicate id is counted once
        self.assertEqual(r["s1"]["messages"], 2)
        self.assertAlmostEqual(r["s1"]["weighted"], 6e6)
        # Opus 5.5: 1M cache read = 0.1M, 1M 1h write = 4*2/2 = 4M
        self.assertAlmostEqual(r["s2"]["weighted"], 4.1e6)

    def test_filters(self):
        self.assertEqual(set(self.rows("--session", "s2")), {"s2"})
        r = self.rows("--since", "3h")
        self.assertAlmostEqual(r["s1"]["weighted"], 5e6)  # the 5h-old message is out

    def test_no_content_printed(self):
        self.assertNotIn("SECRET", self.run_cli("tokens"))

    def test_log_estimate_and_fallback(self):
        out = self.run_cli("estimate", "--type", "k", ok=False)
        self.assertIn("too little history", out)
        for _ in range(3):
            self.run_cli("log", "--type", "k", "--session", "s1", "--est", "1e6", "9e6", "--effort", "high")
        out = self.run_cli("estimate", "--type", "k")
        self.assertIn("3 past 'k' sessions", out)
        self.assertIn("percent unknown", out)

    def test_days_project_self(self):
        days = json.loads(self.run_cli("days", "--json"))
        self.assertAlmostEqual(sum(d["weighted"] for d in days), 10.1e6)
        self.assertEqual(sum(d["messages"] for d in days), 3)
        self.assertEqual(self.rows("--project", "nope"), {})
        self.assertEqual(set(self.rows("--project", "pro")), {"s1", "s2"})
        env = dict(self.env, CLAUDE_CODE_SESSION_ID="s2")
        r = subprocess.run([sys.executable, SCRIPT, "tokens", "--self"], env=env, capture_output=True, text=True)
        self.assertIn("weighted 4.10M", r.stdout)
        self.assertIn("claude-opus-5-5", r.stdout)

    def test_review_and_size(self):
        self.assertIn("no estimate lines", self.run_cli("review"))
        for est in (("1e6", "9e6"), ("1e6", "2e6"), ("7e6", "9e6")):
            self.run_cli("log", "--type", "k", "--session", "s1", "--est", *est, "--size", "M")
        out = self.run_cli("review")
        self.assertIn("inside", out); self.assertIn("over", out); self.assertIn("under", out)
        self.assertIn("1 of 3 inside", out)
        self.assertIn("3 past 'k'", self.run_cli("estimate", "--type", "k", "--size", "M"))

    def test_calibrate(self):
        a, b = (self.now - timedelta(hours=6)).isoformat(), self.now.isoformat()
        self.assertIn("refused", self.run_cli("calibrate", f"90@{a}", f"92@{b}", ok=False))
        out = self.run_cli("calibrate", f"90@{a}", f"93@{b}")
        self.assertIn("per 1%", out)
        self.assertIn("3% = 10.10M", self.run_cli("calibration"))  # 6M + 4.1M over 3%
        self.assertIn("% of the limit", self.run_cli("estimate", "--type", "z", "--ctx", "100000", "--steps", "5-10"))
        self.run_cli("calibrate", f"0@{a}", f"50@{b}", "--window", "5h")
        out = self.run_cli("estimate", "--type", "z", "--ctx", "100000", "--steps", "5-10")
        self.assertIn("window 'weekly'", out)
        self.assertIn("window '5h'", self.run_cli("estimate", "--type", "z", "--ctx", "100000", "--steps", "5-10", "--window", "5h"))

    # --- fixtures for ids, subagents and forks
    def put(self, rel, *rows):
        p = os.path.join(self.tmp.name, "p", "proj", *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write("\n".join(rows) + "\n")

    def app(self, app_id, cli, archived=False, **kw):
        d = os.path.join(self.tmp.name, "app", "u1", "u2")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, app_id + ".json"), "w") as f:
            json.dump(dict(sessionId=app_id, cliSessionId=cli, isArchived=archived, **kw), f)

    def home(self, name):
        return os.path.join(self.tmp.name, "h", name)

    def routes(self, *events):
        os.makedirs(self.home(""), exist_ok=True)
        with open(self.home("routes.jsonl"), "a") as f:
            for e in events:
                f.write(json.dumps(dict(dict(ts=self.now.isoformat()), **e)) + "\n")

    PLAN = dict(event="plan", task="t1", type="feature", size="M", card={"kind": "feature"},
                model="claude-opus-5-5", effort="medium")

    def est_rows(self):
        with open(self.home("estimates.jsonl")) as f:
            return [json.loads(l) for l in f]

    def est_rows_after_junk(self):
        return json.loads(self.est_text().splitlines()[-1])

    def est_text(self):
        with open(self.home("estimates.jsonl")) as f:
            return f.read()

    # --- 1. either id
    def test_app_id_finds_the_session(self):
        self.app("local_aaaa", "s1")
        self.assertEqual(set(self.rows("--session", "local_aaaa")), {"s1"})
        self.assertEqual(self.rows("--session", "local_aaaa")["s1"]["app_session"], "local_aaaa")
        self.assertEqual(set(self.rows("--session", "s1")), {"s1"})
        self.run_cli("log", "--type", "k", "--session", "local_aaaa", "--est", "1e6", "9e6")
        r = self.est_rows()[0]
        self.assertEqual((r["session"], r["app_session"], r["actual"]), ("s1", "local_aaaa", 6000000))

    def test_earlier_transcripts_of_one_app_session_are_summed(self):
        self.app("local_aaaa", "s1", priorCliSessionIds=["s2"])
        self.assertEqual(set(self.rows("--session", "local_aaaa")), {"s1", "s2"})
        self.run_cli("log", "--type", "k", "--session", "s1", "--est", "1e6", "9e6")
        self.assertEqual(self.est_rows()[0]["actual"], 10100000)
        env = dict(self.env, CLAUDE_CODE_SESSION_ID="s1")
        r = subprocess.run([sys.executable, SCRIPT, "tokens", "--self"], env=env, capture_output=True, text=True)
        self.assertIn("weighted 10.10M", r.stdout)

    def test_app_id_without_metadata_is_a_clear_error(self):
        for cmd in (["tokens", "--session", "local_zzzz"], ["log", "--type", "k", "--est", "1", "2", "--session", "local_zzzz"]):
            out = self.run_cli(*cmd, ok=False)
            self.assertIn("ORCHESTRATE_APP_SESSIONS", out)
            self.assertNotIn("Traceback", out)
        self.assertEqual(set(self.rows("--session", "s2")), {"s2"})  # transcript ids still work
        self.app("local_aaaa", "s1")
        self.assertIn("local_zzzz", self.run_cli("tokens", "--session", "local_zzzz", ok=False))

    def test_app_id_equal_to_a_transcript_id_needs_no_metadata(self):
        self.assertEqual(set(self.rows("--session", "local_s1")), {"s1"})

    # --- 2. subagents, forks, prices
    def subagents(self):
        t = self.now - timedelta(minutes=30)
        self.put("s1/subagents/agent-a1.jsonl", line("s1", "a1", "claude-sonnet-5-5", t, i=1000000, o=0, cr=0, effort="low"))
        self.put("s1/subagents/workflows/wf_1/agent-b1.jsonl", line("s1", "b1", "claude-sonnet-5-5", t, i=2000000, o=0, cr=0))
        self.put("s1/subagents/workflows/wf_1/journal.jsonl", json.dumps({"type": "started"}))

    def test_subagents_belong_to_the_parent(self):
        self.subagents()
        s = self.rows()["s1"]
        self.assertAlmostEqual(s["weighted"], 9e6)
        self.assertAlmostEqual(s["sub_weighted"], 3e6)
        self.assertEqual(s["messages"], 4)
        self.assertEqual(self.rows("--session", "s1")["s1"]["weighted"], s["weighted"])
        out = self.run_cli("tokens")
        self.assertIn("33%", out)
        self.assertIn("subagents 3.00M (23%)", out)  # of 13.1M
        env = dict(self.env, CLAUDE_CODE_SESSION_ID="s1")
        r = subprocess.run([sys.executable, SCRIPT, "tokens", "--self"], env=env, capture_output=True, text=True)
        self.assertIn("subagents 33%", r.stdout)
        self.assertAlmostEqual(sum(d["weighted"] for d in json.loads(self.run_cli("days", "--json"))), 13.1e6)

    def test_subagents_of_a_parent_without_transcript(self):
        self.put("s9/subagents/agent-a.jsonl", line("s9", "z1", "claude-sonnet-5-5", self.now, i=1000000, o=0, cr=0))
        self.assertAlmostEqual(self.rows("--session", "s9")["s9"]["weighted"], 1e6)

    def test_fork_counts_shared_messages_once(self):
        t = self.now - timedelta(hours=5)
        old = [line("s1", "m1", "claude-sonnet-5-5", t, i=1000000, o=0, cr=0),
               line("s1", "m2", "claude-sonnet-5-5", self.now - timedelta(hours=1), i=0, o=1000000, cr=0)]
        # a name that sorts first: the owner comes from the recorded sessionId, not from the file order
        self.put("a-fork.jsonl", *old, line("a-fork", "f1", "claude-sonnet-5-5", self.now, i=500000, o=0, cr=0))
        r = self.rows()
        self.assertAlmostEqual(r["s1"]["weighted"], 6e6)
        self.assertAlmostEqual(r["a-fork"]["weighted"], 0.5e6)
        self.assertAlmostEqual(self.rows("--session", "a-fork")["a-fork"]["weighted"], 0.5e6)
        self.assertEqual(sum(d["messages"] for d in json.loads(self.run_cli("days", "--json"))), 4)

    def test_resume_that_rewrites_the_session_id_is_counted_once(self):
        t = self.now - timedelta(hours=5)
        self.put("a-res.jsonl", line("a-res", "m1", "claude-sonnet-5-5", t, i=1000000, o=0, cr=0),
                 line("a-res", "m2", "claude-sonnet-5-5", self.now - timedelta(hours=1), i=0, o=1000000, cr=0),
                 line("a-res", "n1", "claude-sonnet-5-5", self.now, i=1000000, o=0, cr=0))
        r = self.rows()
        self.assertAlmostEqual(sum(s["weighted"] for s in r.values()), 11.1e6)
        self.assertAlmostEqual(r["s1"]["weighted"], 6e6)

    def test_the_fullest_copy_of_a_message_wins(self):
        t = self.now - timedelta(minutes=5)
        self.put("s3.jsonl", line("s3", "q", "claude-sonnet-5-5", t, i=0, o=1000, cr=0),
                 line("s3", "q", "claude-sonnet-5-5", t, i=0, o=200000, cr=0))
        self.put("s4.jsonl", line("s3", "q", "claude-sonnet-5-5", t, i=0, o=1000, cr=0))
        r = self.rows()
        self.assertAlmostEqual(r["s3"]["weighted"], 1e6)
        self.assertNotIn("s4", r)

    def test_prices(self):
        want = {"claude-fable-5-2": (8, 40, .2), "claude-fable-5-1": (10, 50, .25), "claude-fable-5": (10, 50, 1),
                "claude-opus-5-5": (4, 20, .2), "claude-opus-5": (5, 25, .5), "claude-opus-4-8": (5, 25, .5),
                "claude-opus-4-1-20250805": (15, 75, 1.5), "claude-sonnet-5-5": (2, 10, .1), "claude-sonnet-5": (2, 10, .2),
                "claude-sonnet-4-5-20250929": (3, 15, .3), "claude-haiku-5-5": (.1, .5, .01),
                "claude-haiku-4-5-20251001": (1, 5, .1), "us.anthropic.claude-opus-5-5-v1:0": (4, 20, .2)}
        rows, n = [], 0
        for m, _ in want.items():
            for kw in (dict(i=10000, o=0, cr=0), dict(i=0, o=10000, cr=0), dict(i=0, o=0, cr=10000)):
                n += 1
                self.put(f"P{n}.jsonl", line(f"P{n}", f"p{n}", m, self.now, **kw))
        r, n = self.rows(), 0
        for m, w in want.items():
            for x in w:
                n += 1
                self.assertAlmostEqual(r[f"P{n}"]["weighted"], 10000 * x / 2, places=6, msg=m)
                self.assertFalse(r[f"P{n}"]["unpriced"], m)

    def test_haiku_tier_is_per_request_and_counts_cache(self):
        h = "claude-haiku-5-5"
        self.put("H1.jsonl", line("H1", "h1", h, self.now, i=0, o=0, cr=100000), line("H1", "h2", h, self.now, i=0, o=0, cr=100000))
        self.put("H2.jsonl", line("H2", "h3", h, self.now, i=1, o=1000, cr=60000, cw5=40000))
        r = self.rows()
        self.assertAlmostEqual(r["H1"]["weighted"], 200000 * .01 / 2)
        self.assertAlmostEqual(r["H2"]["weighted"], (1 * .5 + 1000 * 2.5 + 60000 * .05 + 40000 * .625) / 2)

    def test_unknown_model_is_flagged(self):
        self.put("U.jsonl", line("U", "u1", "claude-opus-5-9", self.now))
        self.assertTrue(self.rows()["U"]["unpriced"])
        self.assertIn("price unknown", self.run_cli("tokens", "--session", "U"))

    # --- 3. sync
    def bind(self, task="t1", session="local_aaaa"):
        return dict(event="bind", task=task, session=session)

    def test_sync_one_row_for_an_archived_session(self):
        self.subagents()
        self.put("s1.jsonl", line("s1", "m1", "claude-sonnet-5-5", self.now - timedelta(minutes=50), i=1000000, o=0, cr=0),
                 line("s1", "m2", "claude-sonnet-5-5", self.now - timedelta(minutes=40), i=100, o=0, cr=200000, cw1=50000),
                 json.dumps({"type": "system", "subtype": "compact_boundary", "uuid": "c1", "sessionId": "s1",
                             "timestamp": self.now.isoformat()}))
        self.app("local_aaaa", "s1", archived=True)
        self.routes(self.PLAN, self.bind(), dict(event="outcome", task="t1", result="landed", rounds=2, p0p1=0))
        self.assertIn("1", self.run_cli("sync"))
        first = self.est_text()
        (r,) = self.est_rows()
        w = 1e6 + (100 * 2 + 200000 * .1 + 50000 * 4) / 2 + 3e6
        for k, v in dict(task="t1", session="s1", app_session="local_aaaa", task_type="feature", size="M",
                         planned_model="claude-opus-5-5", planned_effort="medium", model="claude-sonnet-5-5",
                         effort="high", weighted=round(w), actual=round(w), sub_weighted=3000000, messages=4,
                         peak_context=1000000, compactions=1, result="landed", rounds=2, source="sync").items():
            self.assertEqual(r[k], v, k)
        self.assertEqual(self.run_cli("sync", "--quiet"), "")
        self.assertEqual(self.est_text(), first)

    def test_sync_waits_until_the_session_ends(self):
        self.app("local_aaaa", "s1")
        self.routes(self.PLAN, self.bind())
        self.run_cli("sync")
        self.assertFalse(os.path.exists(self.home("estimates.jsonl")))  # last message 1h ago, not archived
        self.put("s1.jsonl", line("s1", "m1", "claude-sonnet-5-5", self.now - timedelta(hours=7)))
        self.run_cli("sync")
        self.assertEqual(len(self.est_rows()), 1)

    def test_sync_idle_rule_without_app_metadata(self):
        self.put("s1.jsonl", line("s1", "m1", "claude-sonnet-5-5", self.now - timedelta(hours=7)))
        self.routes(self.PLAN, self.bind(session="s1"), dict(self.PLAN, task="t2"), self.bind("t2", "local_gone"))
        out = self.run_cli("sync")
        self.assertIn("t2", out)
        self.assertEqual([r["task"] for r in self.est_rows()], ["t1"])
        self.assertIsNone(self.est_rows()[0]["app_session"])

    def test_sync_updates_its_row_and_keeps_the_rest(self):
        self.app("local_aaaa", "s1", archived=True)
        os.makedirs(self.home(""))
        with open(self.home("estimates.jsonl"), "w") as f:
            f.write('broken line\n{"ts": "2026-01-01", "task_type": "old", "estimate": [1, 2], "actual": 1, "session": "zz"}\n')
        self.routes(self.PLAN, self.bind())
        self.run_cli("sync")
        one = self.est_text()
        self.routes(dict(event="outcome", task="t1", result="landed"))
        self.put("s1.jsonl", *[line("s1", m, "claude-sonnet-5-5", self.now, i=1000000, o=0, cr=0) for m in ("m1", "m2", "m9")])
        self.run_cli("sync")
        two = self.est_text()
        self.assertEqual(one.splitlines()[:2], two.splitlines()[:2])
        self.assertEqual(len(two.splitlines()), 3)
        r = json.loads(two.splitlines()[2])
        self.assertEqual((r["weighted"], r["result"]), (3000000, "landed"))
        os.remove(os.path.join(self.tmp.name, "p", "proj", "s1.jsonl"))  # transcript cleaned up: the count stays
        self.run_cli("sync")
        self.assertEqual(self.est_text(), two)
        self.put("s1.jsonl", line("s1", "m1", "claude-sonnet-5-5", self.now, i=1000000, o=0, cr=0))  # half cleaned up
        self.routes(dict(event="outcome", task="t1", result="reverted"))
        self.run_cli("sync")
        r = self.est_rows_after_junk()
        self.assertEqual((r["weighted"], r["messages"], r["result"]), (3000000, 3, "reverted"))

    def test_sync_missing_files_are_not_an_error(self):
        self.run_cli("sync")
        self.assertEqual(self.run_cli("sync", "--quiet"), "")
        self.routes(self.bind("orphan", "nope"), dict(event="plan"), dict(event="fail", task="t1"))
        with open(self.home("routes.jsonl"), "a") as f:
            f.write('not json\n[1]\n{"event": "bind", "task": "x", "session": 5}\n{"event": "pl')
        self.assertNotIn("Traceback", self.run_cli("sync"))
        self.assertFalse(os.path.exists(self.home("estimates.jsonl")))

    def test_sync_sums_the_sessions_of_an_escalated_task(self):
        self.app("local_aaaa", "s1", archived=True)
        self.app("local_bbbb", "s2", archived=True)
        self.routes(self.PLAN, self.bind(), self.bind(session="local_bbbb"))
        self.run_cli("sync")
        (r,) = self.est_rows()
        self.assertEqual((r["weighted"], r["session"], r["app_session"]), (10100000, "s2", "local_bbbb"))
        self.assertEqual((r["sessions"], r["model"]), (["s1", "s2"], "claude-opus-5-5"))

    def test_sync_task_name_reused_after_an_outcome_is_a_new_row(self):
        self.app("local_aaaa", "s1", archived=True)
        self.app("local_bbbb", "s2", archived=True)
        self.routes(self.PLAN, self.bind(), dict(event="outcome", task="t1", result="landed"),
                    dict(event="outcome", task="t1", result="reverted"),
                    dict(self.PLAN, type="docs"), self.bind(session="local_bbbb"))
        self.run_cli("sync"); self.run_cli("sync")
        self.assertEqual([(r["session"], r["task_type"], r.get("result")) for r in self.est_rows()],
                         [("s1", "feature", "reverted"), ("s2", "docs", None)])

    def test_estimate_and_review_use_both_kinds_of_rows(self):
        self.app("local_aaaa", "s1", archived=True)
        self.run_cli("log", "--type", "feature", "--session", "s2", "--est", "1e6", "9e6", "--size", "M")
        self.run_cli("log", "--type", "feature", "--session", "s1", "--est", "1e6", "2e6", "--size", "M")
        self.routes(self.PLAN, self.bind(), dict(self.PLAN, task="t2"), self.bind("t2", "s2"))
        self.run_cli("sync")  # t2 is not over yet: only t1 gets a row, which replaces the hand-made line in the maths
        out = self.run_cli("review")
        self.assertIn("1 of 2 inside", out)
        self.assertIn("2 past 'feature'", self.run_cli("estimate", "--type", "feature", ok=False).replace("only ", ""))
        self.app("local_bbbb", "s2", archived=True)
        self.app("local_cccc", "s5", archived=True)
        self.put("s5.jsonl", line("s5", "x5", "claude-sonnet-5-5", self.now, i=2000000, o=0, cr=0))
        self.routes(dict(self.PLAN, task="t3"), self.bind("t3", "local_cccc"))
        self.run_cli("sync")
        self.assertIn("3 past 'feature'", self.run_cli("estimate", "--type", "feature", "--size", "M"))
        self.assertIn("no estimate", self.run_cli("review"))

    # --- 5. old calibrations and rows
    def test_old_calibration_warns(self):
        os.makedirs(self.home(""))
        old = '{"date": "2026-11-07", "window": "weekly", "from": "a", "to": "b", "pct": 3, "weighted": 9, "per_pct": 3000000}\n'
        with open(self.home("calibration.jsonl"), "w") as f:
            f.write(old)
        self.assertIn("old accounting", self.run_cli("calibration"))
        z = ("estimate", "--type", "z", "--ctx", "100000", "--steps", "5-10")
        self.assertIn("warning", self.run_cli(*z))
        self.assertIn("warning", self.run_cli("days"))
        a, b = (self.now - timedelta(hours=6)).isoformat(), self.now.isoformat()
        self.run_cli("calibrate", f"90@{a}", f"93@{b}")
        self.assertNotIn("warning", self.run_cli(*z))
        self.assertNotIn("warning", self.run_cli("days"))
        with open(self.home("calibration.jsonl")) as f:
            txt = f.read()
        self.assertTrue(txt.startswith(old))
        rec = json.loads(txt.splitlines()[1])
        self.assertEqual(rec["schema"], 2)
        self.assertRegex(rec["prices"], r"^\d{4}-\d\d-\d\d$")

    def test_old_log_rows_are_used_with_a_warning(self):
        os.makedirs(self.home(""))
        with open(self.home("estimates.jsonl"), "w") as f:
            for n in range(3):
                f.write(json.dumps(dict(ts="2026-10-01T00:00:00", session=f"o{n}", task_type="k", model="m", effort="",
                                        messages=1, weighted=5, estimate=[1, 9], actual=5, size=None)) + "\n")
        out = self.run_cli("estimate", "--type", "k")
        self.assertIn("3 past 'k'", out)
        self.assertIn("old accounting", out)
        self.assertIn("3 of 3 inside", self.run_cli("review"))


if __name__ == "__main__":
    unittest.main()
