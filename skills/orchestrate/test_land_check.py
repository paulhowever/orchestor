"""Tests for land_check.py on a throwaway git repo. Run: python3 -m unittest skills/orchestrate/test_land_check.py"""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "land_check.py")
ME = "me@example.com"


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.wt = os.path.join(self.tmp.name, "wt")
        self.home = os.path.join(self.tmp.name, "orchestrate")   # never the real ~/.claude/orchestrate
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                        HOME=self.tmp.name, USERPROFILE=self.tmp.name, ORCHESTRATE_HOME=self.home)
        self.script = SCRIPT
        os.makedirs(self.repo)
        self.git(self.repo, "init", "-q", "-b", "main")
        self.git(self.repo, "config", "user.email", ME)
        self.git(self.repo, "config", "user.name", "Me")
        self.commit(self.repo, "a.txt", "one", "base")
        self.git(self.repo, "worktree", "add", "-q", "-b", "task", self.wt)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, cwd, *a):
        return subprocess.run(["git", "-C", cwd, *a], env=self.env, check=True, capture_output=True, text=True).stdout

    def write(self, cwd, name, text):
        with open(os.path.join(cwd, name), "w") as f:
            f.write(text)

    def commit(self, cwd, name, text, msg, author=None):
        self.write(cwd, name, text)
        self.git(cwd, "add", name)
        extra = ["--author", f"X <{author}>"] if author else []
        self.git(cwd, "commit", "-q", "-m", msg, *extra)

    def check(self, *a, ok=True):
        r = subprocess.run([sys.executable, self.script, *a, "--repo", self.repo], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode == 0, ok, r.stdout + r.stderr)
        return r.stdout

    def test_no_commits(self):
        self.assertIn("no commits on top of main", self.check("task", ok=False))

    def test_ok_and_skipped_steps(self):
        self.commit(self.wt, "b.txt", "two", "task work")
        out = self.check("task")
        self.assertIn("ok to land: task", out)
        self.assertIn("no test command", out)

    def test_not_fast_forward(self):
        self.commit(self.wt, "b.txt", "two", "task work")
        self.commit(self.repo, "c.txt", "three", "main moved")
        self.assertIn("not a fast-forward", self.check("task", ok=False))

    def test_dirty_worktree(self):
        self.commit(self.wt, "b.txt", "two", "task work")
        self.write(self.wt, "junk.txt", "x")
        self.assertIn("not clean", self.check("task", ok=False))

    def test_author_and_trailer(self):
        self.commit(self.wt, "b.txt", "two", "task work", author="other@example.com")
        self.assertIn("has author other@example.com", self.check("task", ok=False))
        self.assertIn("ok to land", self.check("task", "--author", "other@example.com"))
        self.assertIn("no 'Co-Authored-By:' trailer",
                      self.check("task", "--author", "other@example.com", "--trailer", "Co-Authored-By", ok=False))

    def test_rules_from_claude_md(self):
        with open(os.path.join(self.wt, "CLAUDE.md"), "w") as f:
            f.write("# rules\n- `land-check: test = test -f b.txt`\nland-check: lint = false\n"
                    "land-check: trailer = Refs\n")
        self.git(self.wt, "add", "CLAUDE.md")
        self.git(self.wt, "commit", "-q", "-m", "rules\n\nRefs: #1")
        self.commit(self.wt, "b.txt", "two", "work\n\nRefs: #1")
        self.assertIn("lint failed: false", self.check("task", ok=False))
        out = self.check("task", "--lint", "true")
        self.assertIn("test passed: test -f b.txt", out)

    def records(self):
        path = os.path.join(self.home, "landings.jsonl")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [json.loads(x) for x in f]

    def sha(self, ref):
        return self.git(self.repo, "rev-parse", ref).strip()

    def test_record_on_success_only(self):
        self.check("task", ok=False)
        self.assertEqual(self.records(), [])
        self.commit(self.wt, "b.txt", "two", "task work")
        self.check("task")
        (r,) = self.records()
        self.assertEqual((r["branch"], r["base"], r["head"], r["base_sha"]),
                         ("task", "main", self.sha("task"), self.sha("main")))
        self.assertEqual(r["repo"], os.path.realpath(os.path.join(self.repo, ".git")))
        self.assertEqual(r["refs"], {"refs/heads/main": self.sha("main")})
        self.assertRegex(r["time"], r"^\d{4}-\d\d-\d\dT.*\+00:00$")

    def test_archive_leaves_no_record(self):
        self.check("task", "--archive")
        self.assertEqual(self.records(), [])

    def test_unwritable_record_changes_nothing(self):
        self.commit(self.wt, "b.txt", "two", "task work")
        self.write(self.tmp.name, "orchestrate", "a file, not a directory")
        self.assertIn("ok to land: task", self.check("task"))

    def test_no_record_when_branch_moves_during_the_check(self):
        self.commit(self.wt, "b.txt", "two", "task work")
        self.assertIn("ok to land", self.check("task", "--test", "git commit -q --allow-empty -m moved"))
        self.assertEqual(self.records(), [])

    def with_usage(self, body):
        """land_check.py next to a stub usage.py (or none)."""
        d = os.path.join(self.tmp.name, "skill")
        os.makedirs(d)
        self.script = shutil.copy(SCRIPT, d)
        if body is not None:
            self.write(d, "usage.py", body)
        self.commit(self.wt, "b.txt", "two" + str(body), "task work")

    def test_sync_runs_on_land_and_archive(self):
        log = os.path.join(self.tmp.name, "calls")
        self.with_usage(f"import sys; open({log!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n'); print('noise')")
        self.check("task", "--archive", ok=False)
        self.assertFalse(os.path.exists(log))
        self.assertNotIn("noise", self.check("task"))
        self.git(self.repo, "merge", "-q", "--ff-only", "task")
        self.check("task", "--archive")
        with open(log) as f:
            self.assertEqual(f.read(), "sync --quiet\n" * 2)

    def test_sync_failures_change_nothing(self):
        for body in (None, "import sys; sys.exit('no such subcommand')", "import time; time.sleep(30)"):
            with self.subTest(body=body):
                shutil.rmtree(os.path.join(self.tmp.name, "skill"), ignore_errors=True)
                self.with_usage(body)
                with open(self.script) as f:
                    text = f.read().replace("SYNC_TIMEOUT = 30", "SYNC_TIMEOUT = 0.3")
                self.write(os.path.dirname(self.script), "land_check.py", text)
                self.assertEqual(self.check("task"), f"ok to land: task at {self.sha('task')[:7]}, "
                                 f"{self.git(self.repo, 'rev-list', '--count', 'main..task').strip()} commit(s) on main\n"
                                 "  no lint command (CLAUDE.md 'land-check: lint = ...' or --lint): skipped\n"
                                 "  no test command (CLAUDE.md 'land-check: test = ...' or --test): skipped\n")

    def test_archive(self):
        self.commit(self.wt, "b.txt", "two", "task work")
        self.assertIn("not in main", self.check("task", "--archive", ok=False))
        self.git(self.repo, "merge", "-q", "--ff-only", "task")
        self.assertIn("ok to archive", self.check("task", "--archive"))
        self.write(self.wt, "b.txt", "changed")
        self.git(self.wt, "stash", "push", "-q", "-m", "left over")
        self.assertIn("stash has 1", self.check("task", "--archive", ok=False))


if __name__ == "__main__":
    unittest.main()
