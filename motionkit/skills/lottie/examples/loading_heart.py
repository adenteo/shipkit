"""A loading heart: it hops, squashes on landing, with a shadow and a sparkle each landing.
A seamless loop (66 frames at 60 fps). Palette: warm coral.

    python3 ../scripts/build.py loading_heart.py --out /tmp/lottie
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
from lottie_kit import *

PALETTE = Palette(ink='#3B2A33', hero='#FF6F7D', accent='#FFD479')


def build():
    """A plump heart hops: squash, stretch up, hang, fall, squash on landing, a tiny sparkle. Loops."""
    use_palette(PALETTE)
    c = Comp('loading-heart', 66)
    G0 = 224              # ground line (heart tip rests here)
    w = 112
    h = w * HEART_H
    up = 58               # hop height

    c.add('shadow', [shadow(98, 15, 17)], p=(150, G0 + 5),
          s=K((0, [100, 100], 'io'), (7, [108, 100], 'io'), (9, [104, 100], 'outq'), (30, [54, 60], 'inq'),
              (48, [100, 100], 'out'), (51, [116, 104], 'io'), (58, [100, 100], 'lin'), (66, [100, 100])),
          o=K((0, 100, 'lin'), (9, 100, 'outq'), (30, 55, 'inq'), (48, 100, 'lin'), (66, 100)))

    # two tiny sparkles pop on the landing
    for (x, y, r, t0, rot) in [(222, 132, 14, 47, 18), (80, 158, 9.5, 49, -14)]:
        c.add('sparkle', [sparkle_art(r, lw=2.2)], p=(x, y),
              s=K((0, [0, 0], 'hold'), (t0, [0, 0], 'out'), (t0 + 6, [115, 115], 'io'), (t0 + 10, [100, 100], 'in'),
                  (t0 + 17, [0, 0], 'lin'), (66, [0, 0])),
              r=K((0, -rot, 'hold'), (t0, -rot, 'out'), (t0 + 17, rot, 'lin'), (66, rot)))

    c.add('heart', [heart_art(w, cy=-h / 2)], p=K((0, [150, G0], 'lin'), (9, [150, G0], 'outq'),
                                                  (30, [150, G0 - up], 'inq'), (48, [150, G0], 'lin'),
                                                  (66, [150, G0])),
          s=K((0, [100, 100], 'io'), (7, [114, 86], 'out'), (13, [88, 113], 'io'), (24, [100, 100], 'io'),
              (31, [102, 98], 'io'), (42, [95, 106], 'in'), (48, [93, 108], 'out'), (51, [122, 80], 'io'),
              (56, [95, 106], 'io'), (61, [102, 98], 'io'), (66, [100, 100])),
          r=K((0, 0, 'io'), (9, 0, 'io'), (21, -6, 'io'), (38, 5, 'io'), (48, 0, 'lin'), (66, 0)))
    return c

