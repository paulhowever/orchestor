#!/usr/bin/env python3
"""PreToolUse on mcp__ccd_session__start_session: a worker brief without its required parts is sent back.

Acts only when the prompt has a line that starts with "You are a worker session started by an orchestrator"
(SKILL.md, section 4). Then it denies, listing what is missing: hard rules 1-3 word for word (compared with
SKILL.md now, no copy here), the receipt, boundaries, a stop line, acceptance criteria, and use_worktree: true
unless the brief says it is read-only. It also denies a likely secret, naming its kind and never its value.
Any other call passes silently: titles without a prompt, proposals started by id, sessions that are not workers.
Checks form only, not whether the brief is right. Never asks, fails open.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hooklib import deny, hard_rules, run

MARKER = re.compile(r"(?im)^[\s>*_#-]*you are a worker session started by an orchestrator\b")
READ_ONLY = re.compile(r"(?im)^[\s>*_#-]*(mode:\s*)?read-only\b"
                       r"|\btask \([^)\n]*\bread-only\b[^)\n]*\)"
                       r"|\b(this|the) (brief|task|session) is read-only\b"
                       r"|\bthis is a read-only (brief|task|session)\b")
RECEIPT = ("status", "branch", "commits", "checked", "open", "tokens")
# Labels as SKILL.md names them, and the Russian ones for a brief in the user's language.
BOUNDARIES = (("Always", r"always|всегда"), ("Ask first", r"ask first|сначала спроси\w*"), ("Never", r"never|никогда"))
STOP = r"\bstop line\b|\bstop at (about|around|~)|стоп-линия|остановись (примерно )?(на|после)"
DONE = r"\bacceptance criteria\b|\bdone when\b|критери\w+ (при[её]мки|готовности)|готово, когда"
SECRETS = (
    ("an AWS access key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("a GitHub token", r"\bgh[pousr]_[A-Za-z0-9]{36}|\bgithub_pat_[A-Za-z0-9_]{60,}"),
    ("an Anthropic key", r"\bsk-ant-[A-Za-z0-9_-]{24,}"),
    ("an OpenAI key", r"\bsk-(?:proj-|svcacct-)[A-Za-z0-9_-]{32,}|\bsk-[A-Za-z0-9]{40,}"),
    ("a Slack token", r"\bxox[abprs]-[0-9]{8,}-[A-Za-z0-9-]{16,}"),
    ("a Google API key", r"\bAIza[0-9A-Za-z_-]{35}"),
    ("a live Stripe key", r"\b[sr]k_live_[0-9A-Za-z]{20,}"),
    ("a Telegram bot token", r"\b[0-9]{8,10}:AA[0-9A-Za-z_-]{33}\b"),
    ("a JSON web token", r"\beyJ[A-Za-z0-9_-]{16,}\.eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"),
    ("a private key", r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----\s*[A-Za-z0-9+/=]{20,}"),
)


def plain(s):
    """Text without markdown marks, quote styles and line breaks, so that only the words are compared."""
    s = s.translate({0x201c: '"', 0x201d: '"', 0x2018: "'", 0x2019: "'", 0x2013: "-", 0x2014: "-"})
    return re.sub(r"\s+", " ", re.sub(r"[*_`>]", "", s)).strip().lower()


def missing(call, text):
    out = []
    rules, have = hard_rules()[:3], plain(text)
    lost = [str(n) for n, r in enumerate(rules, 1) if plain(r) not in have]
    if lost:
        out.append(f"hard rule(s) {', '.join(lost)}, word for word from the skill's SKILL.md")
    keys = [k for k in RECEIPT if not re.search(rf"(?m)^[\s>*`-]*{k}\s*:", text)]
    if keys:
        out.append(f"the receipt block (no line for {', '.join(keys)})")
    groups = [n for n, rx in BOUNDARIES if not re.search(rf"(?im)(?:^|[\s*_(])(?:{rx})[*_]*\s*:", text)]
    if groups:
        out.append(f"boundaries: {', '.join(g + ':' for g in groups)}")
    if not re.search(STOP, text, re.I):
        out.append('a stop line ("Stop at about N messages or X% of the weekly limit ...")')
    if not re.search(DONE, text, re.I):
        out.append('"Acceptance criteria" (what is true when it is done, and how to check it)')
    # A cloud session has its own clone, use_worktree does not apply there.
    if call.get("use_worktree") is not True and call.get("target") != "cloud" and not READ_ONLY.search(text):
        out.append("use_worktree: true (with a fresh context; a fork cannot take it), or a line that starts with "
                   '"Read-only." if it writes nothing')
    return out


def handler(event):
    call = event.get("tool_input")
    if event.get("tool_name") != "mcp__ccd_session__start_session" or not isinstance(call, dict):
        return None
    prompt = call.get("prompt")
    if not isinstance(prompt, str) or not MARKER.search(prompt):
        return None
    background = call.get("background") if isinstance(call.get("background"), str) else ""
    text = prompt + "\n" + background       # the worker gets both
    gaps = missing(call, text)
    everything = "\n".join(v for v in call.values() if isinstance(v, str))
    # EXAMPLE marks the well-known documentation keys
    kinds = [k for k, rx in SECRETS if any("EXAMPLE" not in m.group(0) for m in re.finditer(rx, everything))]
    if not gaps and not kinds:
        return None
    why = ["orchestrate: the worker brief is not ready, the session was not started."]
    if gaps:
        why += ["Missing:"] + [f"- {g}" for g in gaps]
    if kinds:
        why += [f"It looks like it holds {' and '.join(kinds)} (hard rule 5): say where the secret lives instead."]
    why += ["Fix the brief and start the session again (SKILL.md, section 4)."]
    return deny("\n".join(why))


if __name__ == "__main__":
    run(handler)
