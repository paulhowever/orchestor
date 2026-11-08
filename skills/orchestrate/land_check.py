#!/usr/bin/env python3
"""Check a task branch before landing (or before archiving its session). Read-only for git.

  land_check.py BRANCH [--base main] [--repo DIR] [--dir WORKTREE]
                [--lint CMD] [--test CMD] [--trailer KEY]... [--author EMAIL]...
  land_check.py BRANCH --archive [--base main] [--repo DIR]

Landing checks, in order; the first failure is printed and the exit code is 1:
  1. the branch exists and has commits on top of BASE;
  2. it is a fast-forward from BASE (BASE is an ancestor of the branch);
  3. the branch's worktree is clean (no uncommitted or untracked files);
  4. every commit's author email is allowed (default: `git config user.email`);
  5. every commit has each required trailer (for example Co-Authored-By);
  6. lint, then tests, run in the branch's worktree.
All pass -> "ok: ..." and exit code 0.

--archive checks a finished session instead: nothing ahead of BASE (or every commit
already applied there, as `git cherry` sees it), a clean worktree, no stash entry made on the branch.

Commands and trailers come from the arguments, or else from lines in the project's CLAUDE.md:
  land-check: lint = ruff check .
  land-check: test = uv run pytest -q
  land-check: trailer = Co-Authored-By
  land-check: author = me@example.com
Without a lint or test command the step is skipped and the result says so.
Lint and tests run with `sh -c` in the worktree; the script itself never commits, pushes or deletes.
"""
import argparse, os, re, subprocess, sys


def git(repo, *a, ok=False):
    r = subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True)
    if r.returncode and not ok:
        raise RuntimeError(f"git {' '.join(a)}: {r.stderr.strip()}")
    return r.stdout.strip() if r.returncode == 0 else None


def project_rules(repo):
    rules = {"lint": None, "test": None, "trailer": [], "author": []}
    path = os.path.join(repo, "CLAUDE.md")
    if not os.path.exists(path):
        return rules
    for line in open(path, errors="replace"):
        m = re.match(r"\s*(?:[-*]\s*)?`?land-check:\s*(lint|test|trailer|author)\s*=\s*(.+?)`?\s*$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if k in ("trailer", "author"):
            rules[k].append(v)
        else:
            rules[k] = v
    return rules


def worktree_of(repo, branch):
    cur = None
    for line in (git(repo, "worktree", "list", "--porcelain") or "").splitlines():
        if line.startswith("worktree "):
            cur = line[9:]
        elif line == f"branch refs/heads/{branch}":
            return cur
    return None


def default_base(repo):
    head = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", ok=True)
    return head.split("/", 1)[1] if head else "main"


def run(cmd, cwd):
    r = subprocess.run(["sh", "-c", cmd], cwd=cwd, capture_output=True, text=True)
    tail = (r.stdout + r.stderr).strip().splitlines()[-5:]
    return r.returncode == 0, "\n    ".join(tail)


def dirty(wt):
    out = git(wt, "status", "--porcelain")
    return f"worktree {wt} is not clean ({len(out.splitlines())} changed or untracked file(s))" if out else None


def check_land(a, repo, base, wt, notes):
    if git(repo, "rev-list", "--count", f"{base}..{a.branch}") == "0":
        return "no commits on top of " + base
    if git(repo, "merge-base", "--is-ancestor", base, a.branch, ok=True) is None:
        behind = git(repo, "rev-list", "--count", f"{a.branch}..{base}")
        return f"not a fast-forward: {base} has {behind} commit(s) the branch lacks; rebase on {base} first"
    if wt:
        if dirty(wt):
            return dirty(wt)
    else:
        notes.append("no worktree for the branch: cleanliness not checked")
    rules = project_rules(wt or repo)
    authors = a.author or rules["author"] or [git(repo, "config", "user.email", ok=True) or ""]
    trailers = a.trailer or rules["trailer"]
    for line in git(repo, "log", "--format=%h%x09%ae", f"{base}..{a.branch}").splitlines():
        sha, email = line.split("\t")
        if email not in authors:
            return f"commit {sha} has author {email}, allowed: {', '.join(authors)}"
        for t in trailers:
            if not git(repo, "log", "-1", f"--format=%(trailers:key={t},valueonly)", sha):
                return f"commit {sha} has no '{t}:' trailer"
    for step in ("lint", "test"):
        cmd = getattr(a, step) or rules[step]
        if not cmd:
            notes.append(f"no {step} command (CLAUDE.md 'land-check: {step} = ...' or --{step}): skipped")
            continue
        if not wt:
            return f"cannot run {step}: no worktree for the branch (give --dir)"
        good, tail = run(cmd, wt)
        if not good:
            return f"{step} failed: {cmd}\n    {tail}"
        notes.append(f"{step} passed: {cmd}")
    return None


def check_archive(a, repo, base, wt, notes):
    if git(repo, "rev-parse", "--verify", "-q", f"refs/heads/{a.branch}", ok=True):
        pending = [x for x in (git(repo, "cherry", base, a.branch) or "").splitlines() if x.startswith("+")]
        if pending:
            return f"{len(pending)} commit(s) on the branch are not in {base}"
    if wt and dirty(wt):
        return dirty(wt)
    stash = [s for s in (git(repo, "stash", "list") or "").splitlines()
             if re.search(rf"(?:WIP on|On) {re.escape(a.branch)}:", s)]
    if stash:
        return f"stash has {len(stash)} entry(ies) made on {a.branch}: {stash[0].split(':')[0]}"
    notes.append("nothing ahead, clean, no stash on the branch")
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("branch")
    p.add_argument("--base")
    p.add_argument("--repo", default=".")
    p.add_argument("--dir", help="worktree to check and run in (default: the one that has the branch)")
    p.add_argument("--lint"); p.add_argument("--test")
    p.add_argument("--trailer", action="append", default=[])
    p.add_argument("--author", action="append", default=[])
    p.add_argument("--archive", action="store_true", help="check before archiving instead of before landing")
    a = p.parse_args()
    repo = os.path.abspath(a.repo)
    try:
        base = a.base or default_base(repo)
        if not git(repo, "rev-parse", "--verify", "-q", base, ok=True):
            print(f"no: base {base} not found"); sys.exit(1)
        exists = git(repo, "rev-parse", "--verify", "-q", f"refs/heads/{a.branch}", ok=True)
        if not exists and not a.archive:
            print(f"no: branch {a.branch} not found"); sys.exit(1)
        wt = a.dir or worktree_of(repo, a.branch)
        notes = []
        why = (check_archive if a.archive else check_land)(a, repo, base, wt, notes)
    except RuntimeError as e:
        print(f"no: {e}"); sys.exit(1)
    if why:
        print(f"no: {why}"); sys.exit(1)
    head = git(repo, "rev-parse", "--short", a.branch, ok=True) or "-"
    n = git(repo, "rev-list", "--count", f"{base}..{a.branch}", ok=True) or "0"
    print(f"ok to {'archive' if a.archive else 'land'}: {a.branch} at {head}, {n} commit(s) on {base}")
    for x in notes:
        print("  " + x)


if __name__ == "__main__":
    main()
