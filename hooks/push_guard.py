#!/usr/bin/env python3
"""PreToolUse on Bash: no `git push` to the default branch without a landing check of that exact commit.

This is a guard against forgetting, not a security boundary. It reads the text of one command; a script, an
alias, `gh`, an API call or another machine gets past it. Branch protection on the server is the boundary.

Scope: repositories that opted in with a `land-check:` line in CLAUDE.md (the lines land_check.py reads), either
in the checkout the command runs in or in the main checkout. Silent everywhere else.
Denied there, when the target is the remote's default branch:
  - a force-push (any form) or a delete;
  - a commit without an "ok to land" record from land_check.py (landings.jsonl), or a record whose default
    branch has moved since;
  - a commit made by the same command line, which no check can have seen.
A record says the checks passed. It is not the user's yes: hard rule 1 still asks for it.

Parsed conservatively: when the command does not show the target (a variable, --git-dir, GIT_* variables, a
remote given as a URL, an unparsable line), it passes, because a wrong denial stops unrelated work and the
miss is what the guard already allows for. Never asks, fails open.
"""
import json, os, re, sys
sys.dont_write_bytecode = True      # no __pycache__ in the plugin's install directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hooklib import SKILL_DIR, deny, git, run

MAX_RECORDS = 512 * 1024    # bytes read from the end of landings.jsonl


class CannotTell(Exception):
    """The command does not show what it pushes or where: let it pass."""


# --- the command line -> simple commands -----------------------------------------------------------------------
# A word is a str, or None when its value is only known to the shell ($x, $(...), `...`).

class Lexer:
    """Enough of sh to split a line into simple commands: quotes, operators, subshells, $(...), heredocs."""

    def __init__(self, text):
        self.s, self.i, self.events, self.heredocs = text, 0, [], []

    def parse(self, until=None):
        """Append ("cmd", words), ("open",) and ("close",) events; stop after `until`."""
        words, word, dynamic, skip = [], None, False, False
        pending = len(self.heredocs)

        def end_word():
            nonlocal word, dynamic, skip
            if word is not None:
                if not skip:
                    words.append(None if dynamic else word)
                skip = False
            word, dynamic = None, False

        def end_cmd():
            nonlocal words, skip
            end_word()
            skip = False
            if words:
                self.events.append(("cmd", words))
            words = []

        s = self.s
        while self.i < len(s):
            c, two = s[self.i], s[self.i:self.i + 2]
            if c == until:
                self.i += 1
                end_cmd()
                return
            if c == "\n":
                end_cmd()
                self.i += 1
                self.skip_heredocs(pending)
            elif c in " \t\r":
                end_word()
                self.i += 1
            elif c == "#" and word is None:
                n = s.find("\n", self.i)
                self.i = len(s) if n < 0 else n
            elif two == "\\\n":
                self.i += 2
            elif c == "\\":
                word = (word or "") + s[self.i + 1:self.i + 2]
                self.i += 2
            elif c == "'" or two == "$'":
                start = self.i + len(two if c == "$" else c)
                end = start
                while end < len(s) and s[end] != "'":
                    end += 2 if c == "$" and s[end] == "\\" else 1
                if end >= len(s):
                    raise CannotTell("unclosed quote")
                word = (word or "") + s[start:end]
                dynamic = dynamic or c == "$" and "\\" in s[start:end]
                self.i = end + 1
            elif c == '"':
                word, d = word or "", dynamic
                self.i += 1
                while True:
                    if self.i >= len(s):
                        raise CannotTell("unclosed quote")
                    c = s[self.i]
                    if c == '"':
                        self.i += 1
                        break
                    if c == "\\" and s[self.i + 1:self.i + 2] in ('"', "\\", "$", "`", "\n"):
                        word += s[self.i + 1].replace("\n", "")
                        self.i += 2
                    elif c in "$`" and self.expansion():
                        d = True
                    else:
                        word += c
                        self.i += 1
                dynamic = d
            elif c in "$`" and self.expansion():
                word, dynamic = word or "", True
            elif two in ("<(", ">("):
                self.i += 2
                self.nested()
                word, dynamic = word or "", True
            elif c in "<>" or two == "&>":
                if word is not None and word.isdigit() and not dynamic:
                    word = None                     # the 2 of 2>&1
                end_word()
                op = re.match(r"&>>?|<<<|<<-?|<&|<>|<|>>|>&|>\||>", s[self.i:]).group(0)
                self.i += len(op)
                if op in ("<<", "<<-"):
                    self.heredoc(op)
                else:
                    skip = True                     # the next word is a file
            elif c in "()":
                end_cmd()
                self.events.append(("open",) if c == "(" else ("close",))
                self.i += 1
            elif c in ";&|":
                end_cmd()
                self.i += 1
            else:
                word = (word or "") + c
                self.i += 1
        if until:
            raise CannotTell(f"no closing {until}")
        end_cmd()

    def nested(self):
        """The inside of $( ) or <( ); its commands count too, in their own subshell."""
        self.events.append(("open",))
        depth_start = len(self.events)
        while True:
            self.parse(until=")")
            opened = sum({"open": 1, "close": -1}.get(e[0], 0) for e in self.events[depth_start:])
            if opened <= 0:
                break
            self.events.append(("close",))          # that ")" closed an inner subshell
        self.events.append(("close",))

    def expansion(self):
        """Skip an expansion at $ or `; False when the $ is literal."""
        s = self.s
        if s[self.i] == "`":
            end = s.find("`", self.i + 1)
            if end < 0:
                raise CannotTell("unclosed `")
            self.i = end + 1
        elif s.startswith("$(", self.i):
            self.i += 2
            self.nested()
        elif s.startswith("${", self.i):
            end = s.find("}", self.i)
            if end < 0:
                raise CannotTell("unclosed ${")
            self.i = end + 1
        else:
            m = re.match(r"\$(\w+|[@*#?$!-])", s[self.i:])
            if not m:
                return False
            self.i += len(m.group(0))
        return True

    def heredoc(self, op):
        m = re.match(r"""[ \t]*(?:'([^'\n]*)'|"([^"\n]*)"|\\?([^\s;&|<>()'"]+))""", self.s[self.i:])
        if not m:
            raise CannotTell("heredoc without a delimiter")
        self.heredocs.append((next(g for g in m.groups() if g is not None), op == "<<-"))
        self.i += len(m.group(0))

    def skip_heredocs(self, pending):
        while len(self.heredocs) > pending:
            delimiter, tabs = self.heredocs.pop(pending)
            while self.i < len(self.s):
                end = self.s.find("\n", self.i)
                end = len(self.s) if end < 0 else end
                line = self.s[self.i:end]
                self.i = min(end + 1, len(self.s))
                if (line.lstrip("\t") if tabs else line) == delimiter:
                    break
            else:
                raise CannotTell("heredoc without an end")


# --- simple commands -> pushes ---------------------------------------------------------------------------------

RESERVED = {"!", "{", "}", "if", "then", "elif", "else", "while", "until", "do", "time"}
WRAPPERS = {"command", "exec", "nohup", "env"}
MOVERS = {"commit", "merge", "rebase", "reset", "cherry-pick", "revert", "am", "pull", "update-ref"}
PUSH_VALUE = {"-o", "--push-option", "--receive-pack", "--exec", "--repo", "--recurse-submodules"}
GLOBAL_VALUE = {"-c", "--exec-path", "--config-env", "--namespace", "--super-prefix", "--attr-source"}


def strip_prefix(words):
    """Drop reserved words, assignments and plain wrappers; None when the rest depends on GIT_* variables."""
    words = list(words)
    while words and words[0]:
        w = words[0]
        if re.match(r"[A-Za-z_]\w*\+?=", w):
            if w.startswith("GIT_"):
                return []           # GIT_DIR and friends: cannot tell which repository
            words.pop(0)
        elif w in RESERVED or w in WRAPPERS:
            words.pop(0)
        elif w == "timeout" and len(words) > 1 and words[1] and words[1][0].isdigit():
            del words[:2]
        else:
            break
    return words


def resolve(cwd, path):
    """`path` seen from cwd, or None when it is not a directory we can see."""
    if cwd is None or path is None:
        return None
    d = os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))
    return d if os.path.isdir(d) else None


def pushes(command, cwd):
    """Yield (directory, push arguments, branch switched to in this line, directories changed by this line)."""
    lexer = Lexer(command)
    lexer.parse()
    stack, branch, changed = [], {}, set()
    for event in lexer.events:
        if event[0] == "open":
            stack.append(cwd)
            continue
        if event[0] == "close":
            cwd = stack.pop() if stack else cwd
            continue
        words = strip_prefix(event[1])
        if not words or words[0] is None:
            continue
        name, args = os.path.basename(words[0]), words[1:]
        if name in ("cd", "pushd"):
            args = [a for a in args if a is None or not re.fullmatch(r"-[LPe@]|--", a)]
            cwd = resolve(cwd, args[0] if args else "~")        # `cd -` is no directory: unknown from here on
        elif name == "popd":
            cwd = None
        if name != "git":
            continue
        where = cwd
        while args:
            if args[0] == "-C" and len(args) > 1:
                where = resolve(where, args[1])
                args = args[2:]
            elif args[0] in GLOBAL_VALUE and len(args) > 1:
                if args[1] is None or re.match(r"(push|remote|branch|url|alias)\.", args[1], re.I):
                    where = None    # the target may come from that setting
                args = args[2:]
            elif args[0] is None or args[0].startswith(("--git-dir", "--work-tree")):
                where = None        # cannot tell which repository
                break
            elif args[0].startswith("-"):
                args = args[1:]
            else:
                break
        if where is None or not args:
            continue
        sub, args = args[0], args[1:]
        if sub in MOVERS or sub == "fetch" and any(a and ":" in a for a in args) \
                or sub == "branch" and any(a and re.match(r"-\w*[fMD]|--force|--delete", a) for a in args):
            changed.add(where)
        elif sub in ("checkout", "switch"):
            names = [a for a in args if a is None or a == "-" or not a.startswith("-")]
            created = any(a in ("-b", "-B", "-c", "-C", "--create") for a in args)
            detached = any(a in ("--detach", "-d") for a in args)
            if detached:
                branch[where] = None
            elif names and names[0] and (created or len(names) == 1 and "--" not in args and
                                       git(where, "rev-parse", "-q", "--verify", f"refs/heads/{names[0]}")):
                branch[where] = names[0]
            elif "--" not in args and len(names) != 0:
                branch[where] = None            # a commit, a file or a variable: unknown branch
        elif sub == "push":
            yield where, args, branch, changed


# --- one push --------------------------------------------------------------------------------------------------

class Repo:
    def __init__(self, cwd):
        out = git(cwd, "rev-parse", "--show-toplevel", "--git-common-dir")
        if not out or "\n" not in out:
            raise CannotTell("not a checkout")
        self.cwd = cwd
        self.top, common = out.split("\n")[:2]
        self.common = os.path.realpath(os.path.join(cwd, common))
        self.main = os.path.dirname(self.common) if os.path.basename(self.common) == ".git" else self.top

    def opted_in(self, project_rules):
        return any(any(project_rules(d).values()) for d in {self.top, self.main})

    def load(self):
        self.config = {}
        for item in (git(self.cwd, "config", "-z", "--list") or "").split("\0"):
            k, _, v = item.partition("\n")
            self.config.setdefault(k, []).append(v)
        self.remotes = (git(self.cwd, "remote") or "").split()

    def get(self, key):
        return (self.config.get(key) or [None])[-1]

    def sha(self, ref):
        return git(self.cwd, "rev-parse", "-q", "--verify", ref + "^{commit}")

    def default_branch(self, remote):
        head = git(self.cwd, "symbolic-ref", "-q", f"refs/remotes/{remote}/HEAD")
        if head:
            return head.split("/", 3)[3]
        # No record of the remote's HEAD: for the one landing remote assume main, then master (as land_check.py
        # does for main). A second remote without it may be a fork or a backup: cannot tell.
        if remote == "origin" or self.remotes == [remote]:
            for name in ("main", "master"):
                if self.sha(f"refs/heads/{name}") or self.sha(f"refs/remotes/{remote}/{name}"):
                    return name
        raise CannotTell(f"default branch of {remote} unknown")

    def still(self, cur, then, record):
        """A default-branch ref stands where it stood at the check, or moved only within what was checked."""
        return cur is None or cur in (then, record["base_sha"], record["head"]) or \
            git(self.cwd, "merge-base", "--is-ancestor", cur, record["base_sha"]) is not None


def read_args(args):
    """(options, positionals) of `git push`."""
    opts, pos, i = set(), [], 0
    while i < len(args):
        a = args[i]
        i += 1
        if a == "--":
            pos += args[i:]
            break
        if a is None or not a.startswith("-") or a == "-":
            pos.append(a)
        elif a in PUSH_VALUE:
            if a == "--repo":
                opts.add("--repo")
            i += 1
        elif a.startswith("--"):
            opts.add(a.split("=")[0])
        else:
            opts.update("-" + c for c in (a[1:] if not a.startswith("-o") else ""))
    return opts, pos


def short(ref):
    """The branch a destination names, or None for a ref that is no branch."""
    for p in ("refs/heads/", "heads/"):
        if ref.startswith(p):
            return ref[len(p):]
    return None if ref.startswith("refs/") else ref


def targets(repo, opts, pos, current):
    """(remote, [(src, dst branch, force)]); src "" deletes."""
    if "--repo" in opts or any(p is None for p in pos):
        raise CannotTell("remote or refspec only the shell knows")
    remote = pos[0] if pos else (repo.get(f"branch.{current}.pushremote") or repo.get("remote.pushdefault")
                                 or repo.get(f"branch.{current}.remote") or "origin")
    if remote not in repo.remotes:
        raise CannotTell("the remote is a URL, a path or unknown")
    default = repo.default_branch(remote)
    force = bool(opts & {"-f", "--force", "--force-with-lease"})
    push_default = (repo.get("push.default") or "simple").lower()

    def upstream(branch):
        merge = repo.get(f"branch.{branch}.merge") if push_default in ("upstream", "tracking") else None
        return short(merge) if merge else branch

    if "--mirror" in opts:
        return remote, default, [(f"refs/heads/{default}", default, True)]
    everything = [(f"refs/heads/{default}", default, force)]
    if opts & {"--all", "--branches"}:
        return remote, default, everything
    specs = pos[1:]
    if not specs:
        if f"remote.{remote}.push" in repo.config:
            raise CannotTell("remote.<name>.push decides")
        if "--tags" in opts or push_default == "nothing":
            return remote, default, []
        if push_default == "matching":
            return remote, default, everything
        if not current:
            raise CannotTell("detached HEAD or an unknown branch")
        return remote, default, [(f"refs/heads/{current}", upstream(current), force)]
    out, tag = [], False
    for spec in specs:
        if tag or spec == "tag":
            tag = not tag
            continue
        forced = force or spec.startswith("+")
        spec = spec.lstrip("+")
        if spec == ":":
            out += [(s, d, forced) for s, d, _ in everything]
            continue
        src, colon, dst = spec.partition(":")
        if "-d" in opts or "--delete" in opts:
            src, dst = "", spec
        elif not colon:
            if f"remote.{remote}.push" in repo.config:
                raise CannotTell("remote.<name>.push decides")
            name = current if src in ("HEAD", "@") else short(src)
            if not name:
                continue            # a tag or another ref, or a detached HEAD, which git refuses without a target
            src, dst = f"refs/heads/{name}", upstream(name)
        if current:                 # HEAD as it will be after a checkout earlier in the line
            src = re.sub(r"^(HEAD|@)(?=[~^]|$)", f"refs/heads/{current}", src)
        if "*" in dst:
            pre, _, post = dst.partition("*")
            full = f"refs/heads/{default}"
            if not (full.startswith(pre) and full.endswith(post) and len(full) >= len(pre + post)):
                continue
            src, dst = src.replace("*", full[len(pre):len(full) - len(post)]), full
        out.append((src, short(dst), forced))
    return remote, default, out


def records(path, repo_id):
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - MAX_RECORDS))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except FileNotFoundError:
        return
    for line in reversed(lines):
        try:
            r = json.loads(line)
            if r["repo"] == repo_id and all(isinstance(r[k], str) for k in ("base", "head", "base_sha")):
                yield r
        except (ValueError, TypeError, KeyError):
            continue                # a torn or foreign line


def why_not(repo, args, branch, changed, land_check):
    """The reason to deny this push, or None."""
    opts, pos = read_args(args)
    if "-n" in opts or "--dry-run" in opts:
        return None
    current = branch[repo.cwd] if repo.cwd in branch else git(repo.cwd, "symbolic-ref", "-q", "--short", "HEAD")
    remote, default, refs = targets(repo, opts, pos, current)
    script = os.path.join(SKILL_DIR, "land_check.py")
    for src, dst, force in refs:
        if dst != default:
            continue
        if force:
            return f"a force-push to {remote}/{default}. Force-pushing the default branch is not part of landing; " \
                   "if the user wants it, they run it themselves."
        if not src:
            return f"it deletes the default branch {remote}/{default}."
        unknown_head = branch.get(repo.cwd, "") is None and re.match(r"(HEAD|@)([~^]|$)", src)
        if unknown_head or not re.fullmatch(r"[0-9a-f]{40}", src) and any(
                os.path.realpath(d) == os.path.realpath(repo.cwd) or Repo(d).common == repo.common for d in changed):
            return f"the same command line changes commits and pushes to {remote}/{default}, so no landing check can " \
                   f"have seen what it pushes. Run the push as its own command, after {script} says `ok to land`."
        sha = repo.sha(src)
        if not sha:
            continue                # git will refuse it
        tracking = f"refs/remotes/{remote}/{default}"
        if repo.sha(tracking) == sha:
            continue                # nothing to push
        names = {default, f"{remote}/{default}", f"refs/heads/{default}", tracking}
        found = [r for r in records(land_check.landings_file(), repo.common) if r["head"] == sha and r["base"] in names]
        if not found:
            return f"{sha[:7]} goes to {remote}/{default} without an `ok to land` record for that commit. From the main " \
                   f"checkout run `python3 {script} <branch>` (for commits made on {default} itself: " \
                   f"`{default} --base {remote}/{default}`), then ask the user for the yes (hard rule 1)."
        moved = [ref for ref in (f"refs/heads/{default}", tracking)
                 if not repo.still(repo.sha(ref), (found[0].get("refs") or {}).get(ref), found[0])]
        if moved:
            return f"{moved[0]} moved after the landing check of {sha[:7]}. Rebase if needed, run " \
                   f"`python3 {script} <branch>` again and show the user the new commits."
    return None


def handler(event):
    call = event.get("tool_input")
    if event.get("tool_name") != "Bash" or not isinstance(call, dict):
        return None
    command = call.get("command")
    if not isinstance(command, str) or "push" not in command or "git" not in command:
        return None
    cwd = event.get("cwd") if isinstance(event.get("cwd"), str) else os.getcwd()
    try:
        for where, args, branch, changed in pushes(command, cwd):
            try:
                repo = Repo(where)
                sys.path.insert(0, SKILL_DIR)
                import land_check
                if not repo.opted_in(land_check.project_rules):
                    continue
                repo.load()
                reason = why_not(repo, args, branch, changed, land_check)
            except CannotTell:
                continue            # see the file header
            if reason:
                return deny("orchestrate landing guard: " + reason + " (This repository opted in with `land-check:` "
                            "lines in CLAUDE.md. A passed check is not the user's yes.)")
    except CannotTell:
        pass                        # an unparsable line
    return None


if __name__ == "__main__":
    run(handler)
