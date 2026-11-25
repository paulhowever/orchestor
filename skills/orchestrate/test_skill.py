"""Tests for the text of the skill: SKILL.md (the core), references/*.md and templates.md.

Run: python3 skills/orchestrate/test_skill.py. After a compaction Claude Code re-attaches only the first 5,000
tokens of a skill, so the rules needed late in a batch must sit at the start of SKILL.md. The other checks keep
the text in step with the scripts and hooks it names. Nothing here touches the real ~/.claude.
"""
import glob, hashlib, json, os, re, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(ROOT, "hooks")
WINDOW, CORE = 12000, 20000             # characters
# Hard rules 1-6 as approved by the user; a change of wording needs their yes, then a new hash here.
RULES_SHA = "f7ec1b9e4be023ea"
sys.dont_write_bytecode = True
sys.path.insert(0, HOOKS)
import hooklib  # noqa: E402


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


SKILL = read(os.path.join(HERE, "SKILL.md"))
REFS = {os.path.relpath(p, HERE): read(p) for p in
        sorted(glob.glob(os.path.join(HERE, "references", "**", "*"), recursive=True)) if os.path.isfile(p)}
REFS["templates.md"] = read(os.path.join(HERE, "templates.md"))
TEXTS = dict(REFS, **{"SKILL.md": SKILL})


def sections(text):
    """{heading: (start, end)} of the ## sections."""
    heads = [(m.group(1), m.start()) for m in re.finditer(r"(?m)^## (.+)$", text)]
    ends = [s for _, s in heads[1:]] + [len(text)]
    return {h: (s, e) for (h, s), e in zip(heads, ends)}


def section(text, words):
    for h, (s, e) in sections(text).items():
        if words.lower() in h.lower():
            return text[s:e]
    raise AssertionError(f"no section {words!r}")


def env():
    return dict(os.environ, ORCHESTRATE_HOME=os.path.join(tempfile.gettempdir(), "orchestrate-none"))


class Core(unittest.TestCase):
    def test_late_rules_sit_in_the_window(self):
        for words in ("Hard rules", "After a cut", "Land in order", "Archive finished sessions", "When to open"):
            with self.subTest(words):
                found = [(h, e) for h, (s, e) in sections(SKILL).items() if words.lower() in h.lower()]
                self.assertEqual(len(found), 1, f"one ## heading with {words!r}")
                self.assertLessEqual(found[0][1], WINDOW, "the whole section must be inside the window")

    def test_size(self):
        self.assertLessEqual(len(SKILL), CORE)

    def test_hard_rules_word_for_word(self):
        rules = hooklib.hard_rules()
        self.assertEqual(len(rules), 6)
        self.assertEqual(hashlib.sha256("\n".join(rules).encode()).hexdigest()[:16], RULES_SHA)


class References(unittest.TestCase):
    def test_each_is_in_the_index_with_a_when(self):
        self.assertGreaterEqual(len(REFS), 4)
        index = section(SKILL, "When to open")
        for name in REFS:
            lines = [x for x in index.splitlines() if f"]({name})" in x]
            self.assertEqual(len(lines), 1, f"one line for {name} in the index")
            self.assertRegex(lines[0], r"(?i)\b(before|when|after|at)\b")

    def test_named_files_exist(self):
        for where, text in TEXTS.items():
            for name in re.findall(r"\]\(([^)#:<>]+)\)", text) + re.findall(r"`((?:references/)?[a-z_]+\.(?:md|py|json))`", text):
                if where == "templates.md" and name == "link":
                    continue
                self.assertTrue(os.path.isfile(os.path.join(HERE, name)), f"{where} names {name}")

    def test_one_level_deep(self):
        names = [os.path.basename(n) for n in REFS]
        for where, text in REFS.items():
            self.assertIn(os.path.dirname(where), ("", "references"))
            for n in names:
                self.assertFalse(re.search(r"(?<![\w-])" + re.escape(n), text) or "references/" in text,
                                 f"{where} points at {n}: only SKILL.md points at references")

    def test_cited_sections_exist(self):
        have = {m for h in sections(SKILL) for m in re.findall(r"^(\d+[a-z]?)\.", h)}
        cited = {}
        for where, text in TEXTS.items():
            for n in re.findall(r"\bsections? (\d+[a-z]?)\b", text):
                cited.setdefault(n, where)
        for path in glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md")) + glob.glob(os.path.join(HOOKS, "*.py")):
            if os.path.dirname(path) == HERE:
                continue
            for n in re.findall(r"(?:orchestrate`[^.\n]{0,40}|SKILL\.md, )section (\d+[a-z]?)\b", read(path)):
                cited.setdefault(n, os.path.relpath(path, ROOT))
        for n in ("1b", "4"):
            self.assertIn(n, cited)
        for n, where in cited.items():
            self.assertIn(n, have, f"{where} cites section {n}")


class Labels(unittest.TestCase):
    """What the hooks read in a brief. The skill must name each one, or the hook would deny a brief that follows it."""
    FIRST = "You are a worker session started by an orchestrator. Do not orchestrate or ask about it."

    def template(self):
        blocks = re.findall(r"(?ms)^(`{3,})[a-z]*\n(.*?)^\1$", REFS.get("references/brief.md", ""))
        found = [body for _, body in blocks if body.startswith(self.FIRST)]
        self.assertEqual(len(found), 1, "one brief template in references/brief.md")
        return found[0]

    def check(self, prompt, **call):
        call = dict({"prompt": prompt, "title": "t", "context": "fresh", "use_worktree": True}, **call)
        r = subprocess.run([sys.executable, os.path.join(HOOKS, "worker_brief.py")], capture_output=True, env=env(),
                           input=json.dumps({"hook_event_name": "PreToolUse", "tool_input": call,
                                             "tool_name": "mcp__ccd_session__start_session"}).encode())
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        out = r.stdout.decode().strip()
        return json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"] if out else None

    def test_core_names_the_labels(self):
        for label in (self.FIRST, "Always:", "Ask first:", "Never:", "Stop line", "Acceptance criteria", "receipt"):
            self.assertIn(label, SKILL)

    def test_template_passes_the_hook(self):
        t = self.template()
        self.assertIsNone(self.check(t))
        self.assertIn("use_worktree: true", self.check(t, use_worktree=None), "the template is not a read-only brief")

    def test_template_needs_each_part(self):
        for label, part in (("Always:", "Always:"), ("Ask first:", "Ask first:"), ("Never:", "Never:"),
                            ("Stop line", "a stop line"), ("Acceptance criteria", "Acceptance criteria"),
                            ("status:", "status"), ("is not the user's yes", "hard rule(s) 2")):
            with self.subTest(label):
                cut = "\n".join(x for x in self.template().splitlines() if label not in x)
                self.assertIn(part, self.check(cut) or "passed")

    def test_template_takes_the_card(self):
        for label in ("Task:", "Card:", "Route:", "If a check fails:"):
            self.assertIn(label, self.template())

    def test_reviewer_brief(self):
        text = section(REFS["templates.md"], "Reviewer brief").lower()
        self.assertNotIn("the fix in one line", text)
        for part in ("do not propose fixes", "acceptance criteri", "read-only", "can land: no p0/p1"):
            self.assertIn(part, text)


class Commands(unittest.TestCase):
    """Every subcommand and flag the text names exists in the script."""
    SUBS = {"route.py": True, "usage.py": True, "land_check.py": False}
    OTHER = {"--force-with-lease", "--force", "--since", "--format", "--name-only", "--ff-only"}   # git's own
    cache = {}

    def help(self, script, *sub):
        if (script, sub) not in self.cache:
            r = subprocess.run([sys.executable, os.path.join(HERE, script), *sub, "--help"], capture_output=True,
                               text=True, env=env())
            self.cache[script, sub] = r.stdout if r.returncode == 0 else None
        return self.cache[script, sub]

    def spans(self):
        for where, text in TEXTS.items():
            for block in re.findall(r"(?ms)^```[a-z]*\n(.*?)^```", text):
                for line in block.splitlines():
                    yield where, line
            for span in re.findall(r"`([^`\n]+)`", re.sub(r"(?ms)^```.*?^```", "", text)):
                yield where, span

    def test_calls(self):
        seen = set()
        for where, span in self.spans():
            for script, rest in re.findall(r"\b(route\.py|usage\.py|land_check\.py)((?: [^;&()]*)?)", span):
                words = rest.split()
                sub = ()
                if self.SUBS[script] and words:
                    sub = (words[0],)
                    seen.add((script, words[0]))
                text = self.help(script, *sub)
                self.assertIsNotNone(text, f"{where}: {script} {' '.join(words)}: no such command")
                for flag in re.findall(r"(?<!\S)\[?(--[a-z][a-z0-9-]*)", rest):
                    self.assertRegex(text, re.escape(flag) + r"(?![a-z0-9-])", f"{where}: {script} {words}")
        for need in [("route.py", s) for s in ("pick", "bind", "fail", "outcome")] + \
                [("usage.py", s) for s in ("sync", "log", "estimate", "review", "calibrate", "tokens")]:
            self.assertIn(need, seen)

    def test_flags_alone(self):
        known = {f for s, subs in (("route.py", ("pick", "bind", "fail", "outcome")), ("land_check.py", (None,)),
                                   ("usage.py", ("tokens", "days", "log", "sync", "estimate", "calibrate")))
                 for x in subs for f in re.findall(r"--[a-z][a-z0-9-]*", self.help(s, *([x] if x else [])))}
        for where, span in self.spans():
            if span.startswith("--"):
                for flag in re.findall(r"--[a-z][a-z0-9-]*", span):
                    self.assertIn(flag, known | self.OTHER, f"{where}: {span}")


class Chain(unittest.TestCase):
    """The landing of several ready branches, as section 6 describes it, passes land_check.py and the push guard."""

    def test_three_branches_one_yes(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmp = os.path.realpath(tmp.name)
        e = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE"))}
        e.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, HOME=tmp,
                 ORCHESTRATE_HOME=os.path.join(tmp, "home"), CLAUDE_CONFIG_DIR=os.path.join(tmp, "claude"),
                 ORCHESTRATE_APP_SESSIONS=os.path.join(tmp, "none"))
        repo = os.path.join(tmp, "repo")

        def git(*a):
            return subprocess.run(["git", *a], cwd=repo, env=e, check=True, capture_output=True, text=True).stdout.strip()

        def commit(name, text="x"):
            with open(os.path.join(repo, name), "w") as f:
                f.write(text)
            git("add", "-A")
            git("commit", "-q", "-m", name)

        def land(*a):
            r = subprocess.run([sys.executable, os.path.join(HERE, "land_check.py"), "--test", "true", *a], cwd=repo,
                               env=e, capture_output=True, text=True)
            self.assertTrue(r.stdout.startswith("ok to land"), r.stdout + r.stderr)

        def guard(command):
            r = subprocess.run([sys.executable, os.path.join(HOOKS, "push_guard.py")], env=e, capture_output=True,
                               text=True, input=json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                                            "cwd": repo, "tool_input": {"command": command}}))
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout

        os.makedirs(repo)
        git("init", "-q", "--bare", "-b", "main", os.path.join(tmp, "origin.git"))
        git("init", "-q", "-b", "main")
        git("config", "user.email", "me@example.com")
        git("config", "user.name", "Me")
        commit("CLAUDE.md", "land-check: test = true\n")
        git("remote", "add", "origin", os.path.join(tmp, "origin.git"))
        git("push", "-q", "-u", "origin", "main")
        for name, base in (("a", "main"), ("b", "a"), ("c", "b")):      # b rebased on a, c on b
            git("checkout", "-q", "-b", name, base)
            commit(name + ".txt")
        git("checkout", "-q", "main")
        git("remote", "set-head", "origin", "main")
        for name in "abc":
            git("worktree", "add", "-q", os.path.join(tmp, "wt-" + name), name)
        land("a")
        land("b", "--base", "a")
        land("c", "--base", "b")
        self.assertIn("deny", guard("git commit -am x && git push origin main"))
        self.assertIn("deny", guard("git push origin b:main"))          # its record was made against a, not main
        for name in "abc":                                              # the yes named all three commits
            git("fetch", "-q")
            land(name, "--base", "origin/main")
            self.assertEqual(guard(f"git push origin {name}:main"), "")
            git("push", "-q", "origin", f"{name}:main")
        self.assertEqual(git("rev-parse", "origin/main"), git("rev-parse", "c"))


if __name__ == "__main__":
    unittest.main()
