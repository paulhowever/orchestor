"""Tests for land_check.py on a throwaway git repo. Run: python3 -m unittest skills/orchestrate/test_land_check.py"""
import os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "land_check.py")
ME = "me@example.com"


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.wt = os.path.join(self.tmp.name, "wt")
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
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
        r = subprocess.run([sys.executable, SCRIPT, *a, "--repo", self.repo], env=self.env,
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
