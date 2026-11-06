"""Tests for usage.py on synthetic transcripts. Run: python3 -m unittest skills/orchestrate/test_usage.py"""
import json, os, subprocess, sys, tempfile, unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "usage.py")


def line(sid, mid, model, ts, i=10, o=100, cr=1000, cw5=0, cw1=0):
    return json.dumps({"type": "assistant", "sessionId": sid, "timestamp": ts.isoformat(), "message": {
        "id": mid, "model": model, "content": [{"type": "text", "text": "SECRET TEXT"}],
        "usage": {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cr,
                  "cache_creation_input_tokens": cw5 + cw1,
                  "cache_creation": {"ephemeral_5m_input_tokens": cw5, "ephemeral_1h_input_tokens": cw1}}}})


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = dict(os.environ, ORCHESTRATE_PROJECTS=os.path.join(self.tmp.name, "p"),
                        ORCHESTRATE_HOME=os.path.join(self.tmp.name, "h"))
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

    def test_calibrate(self):
        a, b = (self.now - timedelta(hours=6)).isoformat(), self.now.isoformat()
        self.assertIn("refused", self.run_cli("calibrate", f"90@{a}", f"92@{b}", ok=False))
        out = self.run_cli("calibrate", f"90@{a}", f"93@{b}")
        self.assertIn("per 1%", out)
        self.assertIn("3% = 10.10M", self.run_cli("calibration"))  # 6M + 4.1M over 3%
        self.assertIn("% of the limit", self.run_cli("estimate", "--type", "z", "--ctx", "100000", "--steps", "5-10"))


if __name__ == "__main__":
    unittest.main()
