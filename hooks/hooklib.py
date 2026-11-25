"""Shared by the hooks of this plugin. Python 3.8+, standard library only, no network."""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.join(ROOT, "skills", "orchestrate")
SKILL = os.path.join(SKILL_DIR, "SKILL.md")


def run(handler):
    """Feed the event on stdin to handler; print the JSON it returns, if any.

    Fail open: any problem of ours ends with a line on stderr and exit code 1, which Claude Code treats as a
    non-blocking error (2 would block), so the user's work goes on.
    """
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        if not isinstance(event, dict):
            raise ValueError("the event is not a JSON object")
        out = handler(event)
        if out:
            print(json.dumps(out))
    except Exception as e:
        print(f"orchestrate {os.path.basename(sys.argv[0])}: skipped, {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


def deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def git(cwd, *args):
    """stdout without the trailing newline, or None when git says no, is missing or is slow."""
    try:
        r = subprocess.run(["git", "-C", cwd, *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.decode("utf-8", "replace").rstrip("\n") if r.returncode == 0 else None


def hard_rules():
    """The numbered rules of SKILL.md's "Hard rules" section, as written there; [] if there are none."""
    try:
        with open(SKILL, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        print(f"orchestrate hooks: hard rules not read: {e}", file=sys.stderr)
        return []
    head = re.search(r"^(#+)[ \t]+hard rules\b.*$", text, re.I | re.M)
    if not head:
        return []
    body = text[head.end():]
    end = re.search(r"^#{1,%d}\s" % len(head.group(1)), body, re.M)
    rules, inside = [], False
    for line in (body[:end.start()] if end else body).splitlines():
        item = re.match(r" {0,3}\d+\.\s+(.*)", line)
        if item:
            rules.append(item.group(1).strip())
            inside = True
        elif not line.strip():
            inside = False
        elif rules and (inside or line[0] in " \t"):
            rules[-1] += " " + line.strip()
    return rules
