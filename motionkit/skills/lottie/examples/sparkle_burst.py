"""A capture burst: a soft flash, a plump heart popping in the middle, sparkles and small hearts
shooting outward. Plays once and ends empty (54 frames). Palette: blue and gold.

    python3 ../scripts/build.py sparkle_burst.py --out /tmp/lottie
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
from lottie_kit import *

PALETTE = Palette(ink='#1F2A44', hero='#3D7BFF', alt='#9CC2FF', accent='#FFC93C', cool='#7FD6C8')


def build():
    """Capture burst for over a photo: a soft white flash, a plump heart popping in the centre, and
    sparkles and small hearts shooting outward. Plays once, ends empty."""
    N = 54
    use_palette(PALETTE)
    c = Comp('sparkle-burst', N)
    C = (150, 150)
    c.add('flash-soft', [piece(el(170, 170), fill=fl(WHITE, 38))], ip=0, op=24, p=C,
          s=K((0, [30, 30], 'out2'), (20, [185, 185])), o=K((0, 0, 'lin'), (2, 100, 'lin'), (4, 100, 'out'), (22, 0)))
    c.add('flash', [piece(el(120, 120), fill=fl(WHITE, 85))], ip=0, op=20, p=C,
          s=K((0, [20, 20], 'out2'), (16, [150, 150])), o=K((0, 0, 'lin'), (2, 100, 'lin'), (3, 100, 'out'), (18, 0)))
    c.add('ring', [piece(el(120, 120), stroke=st(WHITE, 4, 100))], ip=2, op=22, p=C,
          s=K((2, [40, 40], 'out2'), (20, [200, 200])), o=K((2, 100, 'lin'), (8, 90, 'in'), (21, 0)))

    # radial pop lines
    for n in range(8):
        a = math.radians(-90 + n * 45 + 22.5)
        p0 = (C[0] + 52 * math.cos(a), C[1] + 52 * math.sin(a))
        p1 = (C[0] + 78 * math.cos(a), C[1] + 78 * math.sin(a))
        c.add(f'line-{n}', [piece(bez(p0, [(None, None, p1)], closed=False), stroke=st(P.sh(P.accent), 4.2, 100),
                                  trim=tm(s=K((9, 0, 'in'), (21, 100)), e=K((5, 0, 'out'), (15, 100))))],
              ip=5, op=22)

    # particles
    parts = []
    jit = [(-6, 104), (5, 90), (-3, 112), (8, 96), (4, 100), (-7, 88), (2, 110), (-4, 94)]
    for n in range(8):
        ang = -90 + n * 45 + jit[n][0]
        parts.append((ang, jit[n][1], 'sparkle' if n % 2 == 0 else 'heart', n))
    for ang, dist, kind, n in parts:
        a = math.radians(ang)
        t0 = 6 + (n % 3)
        start = (C[0] + 34 * math.cos(a), C[1] + 34 * math.sin(a))
        end = (C[0] + dist * math.cos(a), C[1] + dist * math.sin(a))
        if kind == 'sparkle':
            art = sparkle_art((13, 10.5, 11.5, 9.5)[n % 4 // 1 % 4] if n % 2 == 0 else 10, lw=2.1)
        else:
            art = heart_art(24 if n % 4 == 1 else 20, P.hero if n % 4 == 1 else P.alt, P.sh(P.hero) if n % 4 == 1 else P.sh(P.alt),
                            lw=2.1, shine=False)
        c.add(f'bit-{n}', [art], ip=t0, op=t0 + 40,
              p=K((t0, list(start), 'out2'), (t0 + 22, list(end), 'lin'), (t0 + 40, [end[0] + 6 * math.cos(a), end[1] + 6 * math.sin(a)])),
              s=K((t0, [0, 0], 'out'), (t0 + 6, [118, 118], 'io'), (t0 + 11, [100, 100], 'lin'), (t0 + 26, [100, 100], 'in'),
                  (t0 + 38, [0, 0])),
              r=K((t0, -30 if n % 2 else 30, 'out'), (t0 + 22, 0, 'lin'), (t0 + 38, 12 if n % 2 else -12)))

    # the heart in the middle
    hw = 96
    c.add('heart', [heart_art(hw, P.hero, P.sh(P.hero), lw=2.6)], ip=3, op=48, p=C,
          s=K((3, [0, 0], 'out'), (11, [124, 118], 'io'), (16, [90, 96], 'io'), (21, [105, 102], 'io'),
              (26, [100, 100], 'lin'), (33, [100, 100], 'io'), (38, [112, 108], 'in'), (46, [0, 0])),
          r=K((3, -14, 'out'), (13, 5, 'io'), (21, -2, 'io'), (27, 0, 'lin'), (46, 0)),
          o=100)
    return c

