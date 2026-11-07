"""A ringing bell: a plump bell with a heart swings and rings, ring marks flick out at each
swing, a sparkle pops. A seamless loop (96 frames). Palette: violet and amber. Shows the heavier
outline (STYLE['ink']) for an animation that will be shown small.

    python3 ../scripts/build.py bell.py --out /tmp/lottie
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
from lottie_kit import *

PALETTE = Palette(ink='#2E2147', hero='#8B5CF6', alt='#C4B0FA', accent='#FFC857', accent2='#FF9F43', cool='#7DD3FC')


def bell_path(k=1.0):
    segs = [((16, 4), (28, 8), (30, 18)), ((32, 30), (34, 52), (42, 66)), ((48, 76), (60, 78), (60, 86)),
            ((60, 92), (30, 95), (0, 95)), ((-30, 95), (-60, 92), (-60, 86)), ((-60, 78), (-48, 76), (-42, 66)),
            ((-34, 52), (-32, 30), (-30, 18)), ((-28, 8), (-16, 4), (0, 4))]
    S = lambda p: (p[0] * k, p[1] * k)
    return bez(S((0, 4)), [(S(a), S(b), S(q)) for a, b, q in segs])



def build():
    """Notifications step: a plump butter bell with a pink heart swings and rings, ring lines flick
    out at each swing, a small sparkle pops. Loops."""
    N = 96
    use_palette(PALETTE)
    c = Comp('bell', N)
    STYLE['ink'] = 1.2
    k = 1.08
    PV = (150, 86)  # pivot at the knob
    swing = [(0, 0), (8, 16), (20, -15), (32, 12), (43, -9), (53, 5), (61, -2), (68, 0)]
    c.add('shadow', [shadow(112, 13, 14)], p=(PV[0], 236),
          s=K(*[(t, [100 - abs(v) * 0.6, 100], 'io') for t, v in swing], (N, [100, 100])))
    clap = [(0, 0), (8, -9), (14, 7), (20, 9), (26, -7), (32, -7), (38, 5), (43, 5), (49, -3), (56, 1), (62, 0)]
    clapper = G([blob(lambda: el(22, 22, 0, 104 * k), P.accent2, P.sh(P.accent2), inset=(-8, 104 * k - 8, 88), lw=2.3)],
                r=K(*[(t, v, 'io') for t, v in clap], (N, 0)))
    knob = blob(lambda: el(20, 18, 0, -3), P.sh(P.accent), None, lw=2.3)
    body = blob(lambda: bell_path(k), P.accent, P.sh(P.accent), inset=(-40 * k, 6 * k, 94),
                hl=[piece(rc(9, 34, 4.5, -23 * k, 44 * k), fill=fl(WHITE, 80)), gloss(-24 * k, 70 * k, 5, 5, o=80)])
    rim = blob(lambda: rc(128 * k, 13, 6.5, 0, 89 * k), P.sh(P.accent), None, lw=2.3)
    heart_ = heart_art(36, P.hero, P.sh(P.hero), cy=50 * k, lw=2.4)
    c.add('bell', [clapper, knob, body, rim, heart_], p=PV,
          r=K(*[(t, v, 'io') for t, v in swing], (N, 0)))
    # ring lines flick out on the side the bell swings toward
    for side, hits in ((1, (8, 32, 53)), (-1, (20, 43))):
        x = PV[0] + side * 84
        marks = []
        for n, (dx, hgt, yy) in enumerate(((0, 26, 160), (side * 10, 16, 160))):
            p0, p1 = (x + dx, yy - hgt / 2), (x + dx, yy + hgt / 2)
            b = side * 6
            marks.append(piece(bez(p0, [((p0[0] + b, p0[1] + hgt * 0.3), (p1[0] + b, p1[1] - hgt * 0.3), p1)],
                                   closed=False), stroke=st(P.hero, 3.4, 100)))
        ok = [(0, 0, 'hold')]
        for t in hits:
            ok += [(t - 2, 0, 'out'), (t + 1, 100, 'lin'), (t + 6, 100, 'in'), (t + 10, 0, 'hold')]
        ok.append((N, 0))
        c.add('ring', marks, o=K(*ok))
    for n, t in enumerate((8, 20, 32, 43)):
        ring(c, f'wave-{n}', t, (PV[0], PV[1] + 64), 96, 230, color=WHITE, w=3.2, o=55 - n * 8, dur=20)
    for (x, y, r_, t0) in [(226, 74, 12, 10), (78, 96, 8, 34)]:
        c.add('sparkle', [sparkle_art(r_, lw=2.2)], p=(x, y), ip=t0, op=t0 + 26,
              s=K(*uni(pop(t0, 100, 0, over=(1.2, 0.95), d=(6, 4, 4))), (t0 + 16, [100, 100], 'in'), (t0 + 25, [0, 0])),
              r=K((t0, -30, 'out'), (t0 + 25, 20)))
    return c
