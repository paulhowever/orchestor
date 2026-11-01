"""Generate assets/demo-light.svg and assets/demo-dark.svg, a looping CSS-animated storyboard.

Usage: python3 assets/demo.py assets
"""
import sys

D = 16.0  # loop length, seconds
OUT = sys.argv[1]

THEMES = {
    "light": dict(bg="#faf9f5", card="#ffffff", line="#d6d3c8", fg="#1f1e1d", mute="#6b6a65",
                  acc="#c96442", accbg="#f5e4dc", ok="#3d7a4f", okbg="#e3efe6", bad="#b5452c", track="#ece9e0", onacc="#ffffff"),
    "dark": dict(bg="#161b22", card="#0d1117", line="#3d444d", fg="#e6edf3", mute="#9198a1",
                 acc="#e08a6b", accbg="#3a2620", ok="#6cc287", okbg="#1d3326", bad="#f0805f", track="#262c34", onacc="#161b22"),
}
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

kf = []   # keyframe css blocks
n = [0]


def pct(t):
    return f"{max(0.0, min(100.0, t / D * 100)):.2f}%"


def anim(points):
    """points: list of (t, css-declarations). Returns a class name with an infinite animation."""
    n[0] += 1
    name = f"k{n[0]}"
    frames = [f"0%{{{points[0][1]}}}"] + [f"{pct(t)}{{{css}}}" for t, css in points] + [f"100%{{{points[-1][1]}}}"]
    kf.append(f"@keyframes {name}{{{''.join(frames)}}}.{name}{{animation:{name} {D}s linear infinite}}")
    return name


def show(t_in, t_out=15.4, dx_out=0):
    """Fade in at t_in, out at t_out (optionally sliding right)."""
    out = f"opacity:0;transform:translateX({dx_out}px)" if dx_out else "opacity:0"
    stay = "opacity:1;transform:translateX(0)" if dx_out else "opacity:1"
    return anim([(t_in, "opacity:0"), (t_in + 0.35, stay), (t_out, stay), (t_out + 0.5, out)])


def bar(t0, t1, t_out):
    return anim([(t0, "transform:scaleX(0)"), (t1, "transform:scaleX(1)"), (t_out, "transform:scaleX(1)")])


def build(c):
    kf.clear()
    n[0] = 0
    el = []
    A = el.append

    # step strip at the bottom
    steps = [("split", 0.2, 2.0), ("run", 2.0, 5.2), ("check", 5.2, 6.6),
             ("your yes", 6.6, 8.4), ("land", 8.4, 10.2), ("archive", 10.2, 15.4)]
    x = 24
    w = 148
    for i, (label, a, b) in enumerate(steps):
        A(f'<rect x="{x}" y="404" width="{w}" height="26" rx="13" fill="{c["track"]}"/>')
        A(f'<rect class="{show(a, b)}" x="{x}" y="404" width="{w}" height="26" rx="13" fill="{c["accbg"]}" stroke="{c["acc"]}" stroke-width="1.5"/>')
        A(f'<text x="{x + w / 2}" y="421.5" text-anchor="middle" class="st">{i + 1} · {label}</text>')
        x += w + 4.4

    # column headers
    A('<text class="cap" x="24" y="34">YOU</text>')
    A('<text class="cap" x="292" y="34">SESSIONS</text>')
    A('<text class="cap" x="652" y="34">CLAUDE ASKS · YOU ANSWER</text>')

    # 1. the message
    A(f'<g class="{show(0.2)}"><rect x="24" y="48" width="244" height="150" rx="14" fill="{c["accbg"]}" stroke="{c["acc"]}" stroke-width="1.5"/>'
      f'<text class="h" x="42" y="76">One message</text>'
      f'<text class="t" x="42" y="104">• fix the Safari login loop</text>'
      f'<text class="t" x="42" y="128">• add CSV export</text>'
      f'<text class="t" x="42" y="152">• which Node is prod on?</text>'
      f'<text class="t" x="42" y="176">• research rate limiting</text></g>')

    # quick thing answered inline
    A(f'<g class="{show(1.3)}"><rect x="24" y="214" width="244" height="54" rx="12" fill="{c["card"]}" stroke="{c["line"]}" stroke-width="1.5"/>'
      f'<path d="M40 238 l6 6 l11 -13" class="ok"/>'
      f'<text class="t" x="66" y="237">Node 22.11 — answered here</text>'
      f'<text class="m" x="66" y="256">no session needed</text></g>')

    # 2. sessions
    sess = [("fix-login", "strongest · high effort", 2.0, 4.6),
            ("csv-export", "mid-tier · medium effort", 2.3, 4.9),
            ("rate-limit-research", "smallest · read-only", 2.6, 4.2)]
    for i, (name, model, t_in, t_done) in enumerate(sess):
        y = 48 + i * 82
        A(f'<g class="{show(t_in, 10.4 + i * 0.25, dx_out=60)}">')
        A(f'<rect x="292" y="{y}" width="336" height="70" rx="12" fill="{c["card"]}" stroke="{c["line"]}" stroke-width="1.5"/>'
          f'<text class="hm" x="310" y="{y + 25}">{name}</text>'
          f'<text class="m" x="310" y="{y + 44}">{model}</text>'
          f'<rect x="310" y="{y + 54}" width="200" height="6" rx="3" fill="{c["track"]}"/>'
          f'<rect class="{bar(t_in + 0.3, t_done, 15.4)} grow" x="310" y="{y + 54}" width="200" height="6" rx="3" fill="{c["acc"]}"/>')
        if name == "csv-export":
            A(f'<text class="{show(5.4, 7.0)} bad" x="612" y="{y + 30}" text-anchor="end">CI red (lint)</text>')
            A(f'<text class="{show(5.4, 7.0)} m" x="612" y="{y + 48}" text-anchor="end">sent back</text>')
            A(f'<text class="{show(7.4)} okt" x="612" y="{y + 30}" text-anchor="end">CI green ✓</text>')
            A(f'<text class="{show(7.4)} m" x="612" y="{y + 48}" text-anchor="end">fixed, rebased</text>')
        elif name == "fix-login":
            A(f'<text class="{show(5.2)} okt" x="612" y="{y + 30}" text-anchor="end">CI green ✓</text>')
            A(f'<text class="{show(5.2)} m" x="612" y="{y + 48}" text-anchor="end">2 commits</text>')
        else:
            A(f'<text class="{show(4.5)} okt" x="612" y="{y + 30}" text-anchor="end">summary ✓</text>')
            A(f'<text class="{show(4.5)} m" x="612" y="{y + 48}" text-anchor="end">in the digest</text>')
        A('</g>')

    A(f'<text class="{show(2.8, 10.2)} m" x="292" y="306">≤ 3 sessions write at once · own worktree each</text>')

    # 3–5. ask / yes / land
    def claude(y, t, l1, l2):
        A(f'<g class="{show(t)}"><rect x="652" y="{y}" width="284" height="56" rx="12" fill="{c["card"]}" stroke="{c["line"]}" stroke-width="1.5"/>'
          f'<text class="t" x="668" y="{y + 24}">{l1}</text><text class="m" x="668" y="{y + 43}">{l2}</text></g>')

    def you(y, t, text):
        bw = 26 + len(text) * 7.4
        A(f'<g class="{show(t)}"><rect x="{936 - bw}" y="{y}" width="{bw}" height="32" rx="16" fill="{c["acc"]}"/>'
          f'<text class="yt" x="{936 - bw / 2}" y="{y + 21}" text-anchor="middle">{text}</text></g>')

    claude(48, 6.0, "Land fix-login → main?", "2 commits to e4f5a6b · CI green")
    you(112, 7.0, "yes, land fix-login")
    claude(152, 8.0, "Landed. csv-export is green", "now too. Land it?")
    you(216, 8.9, "yes")
    claude(256, 9.6, "Landed. All 3 clean and merged.", "Archive them?")
    you(320, 10.2, "archive them")

    # 6. archive
    A(f'<g class="{show(11.0)}"><rect x="292" y="48" width="336" height="236" rx="12" fill="none" stroke="{c["line"]}" stroke-width="1.5" stroke-dasharray="6 5"/>'
      f'<path d="M434 118 h68 v14 h-68 z M440 132 h56 v44 h-56 z M456 148 h24" fill="none" stroke="{c["mute"]}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
      f'<text class="h" x="460" y="210" text-anchor="middle">3 sessions archived</text>'
      f'<text class="m" x="460" y="232" text-anchor="middle">worktrees clean · commits on main</text></g>')
    A(f'<g class="{show(12.0)}"><text class="big" x="292" y="350">Nothing waits on you.</text>'
      f'<text class="m" x="292" y="376">Nothing shipped without a yes that named it.</text></g>')

    css = f"""
    .bg{{fill:{c['bg']}}}
    .cap{{font:600 11px {SANS};fill:{c['mute']};letter-spacing:1.2px}}
    .h{{font:700 15px {SANS};fill:{c['fg']}}}
    .hm{{font:700 14px {MONO};fill:{c['fg']}}}
    .t{{font:400 13.5px {SANS};fill:{c['fg']}}}
    .m{{font:400 12px {MONO};fill:{c['mute']}}}
    .st{{font:600 12px {SANS};fill:{c['fg']}}}
    .yt{{font:600 13px {SANS};fill:{c['onacc']}}}
    .okt{{font:700 13px {SANS};fill:{c['ok']}}}
    .bad{{font:700 13px {SANS};fill:{c['bad']}}}
    .big{{font:700 26px {SANS};fill:{c['fg']};letter-spacing:-0.5px}}
    .ok{{fill:none;stroke:{c['ok']};stroke-width:2.6;stroke-linecap:round;stroke-linejoin:round}}
    .grow{{transform-box:fill-box;transform-origin:left center}}
    """
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 448" width="960" height="448" role="img" '
            f'aria-label="Animated demo: one message with four tasks; one is answered right away, three go to their own sessions with a model each; '
            f'reports are checked against CI, one is sent back and fixed; Claude asks to land each branch and lands it only after you say yes; '
            f'the three finished sessions are archived.">'
            f'<style>{css}{"".join(kf)}</style>'
            f'<rect class="bg" width="960" height="448" rx="18"/>' + "".join(el) + '</svg>\n')


for theme, colors in THEMES.items():
    svg = build(colors)
    with open(f"{OUT}/demo-{theme}.svg", "w") as f:
        f.write(svg)
    print(theme, len(svg))
