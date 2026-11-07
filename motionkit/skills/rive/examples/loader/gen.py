#!/usr/bin/env python3
"""Loader.riv: three dots that hop in turn, a seamless loop.

    python3 gen.py              # write scene.rml, verify, build build/Loader.riv
    python3 gen.py --no-build   # only write scene.rml

One state machine ("Loop") with one state: a looping animation. A loader is the one case where
a loop is right, because it only plays while something loads. The app pauses it the moment it
leaves the screen. Each dot crouches, springs up stretched, lands squashed and settles, a third
of the loop after the one before it. The hop uses the `up` / `down` parabola eases (a linear y
reads as floating) and a squash and stretch pair that conserve volume.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'scripts'))
from uilib import *

LW = 2.4
GROUND = 62
N = 96           # loop length in frames at 60 fps
GAP = 26         # frames between one dot and the next
R = 11           # dot size (diameter 2R)
COLORS = [(PRIMARY, PRIMARY_SHADE), (ACCENT, ACCENT_SHADE), (PRIMARY_LIGHT, PRIMARY)]


def dot(i, base, shade):
    outer, body, shadow = nid(), nid(), nid()
    art = node(f'Dot {i} body', 0, -R, cel(f'Dot {i}', lambda s: ellipse(2 * R, 2 * R), base, shade, lw=LW, w=5), nid_=body)
    xml = node(f'Dot {i}', 0, 0, [node(f'Dot {i} squash', 0, 0, [art], nid_=outer)])
    sh = shape(f'Dot {i} shadow', 0, GROUND + 1, ellipse(2 * R, 5), fill(INK), sid=shadow, opacity=0.18)
    return outer, body, shadow, xml, sh


def hop(a, ids, t):
    """One hop starting at frame t: crouch, spring, air, land, settle."""
    outer, body, shadow = ids
    a.key(outer, Y, [(0, GROUND, 'hold'), (t + 6, GROUND, 'up'), (t + 17, GROUND - 16, 'down'), (t + 28, GROUND, 'hold'), (N, GROUND)])
    a.key(body, SX, [(0, 1, 'hold'), (t, 1, 'io'), (t + 6, 1.16, 'out'), (t + 11, 0.88, 'io'), (t + 24, 0.97, 'in'),
                     (t + 28, 1.18, 'out'), (t + 34, 0.95, 'io'), (t + 40, 1, 'hold'), (N, 1)])
    a.key(body, SY, [(0, 1, 'hold'), (t, 1, 'io'), (t + 6, 0.84, 'out'), (t + 11, 1.14, 'io'), (t + 24, 1.03, 'in'),
                     (t + 28, 0.82, 'out'), (t + 34, 1.05, 'io'), (t + 40, 1, 'hold'), (N, 1)])
    a.key(shadow, SX, [(0, 1, 'hold'), (t + 6, 1, 'up'), (t + 17, 0.55, 'down'), (t + 28, 1, 'hold'), (N, 1)])
    a.key(shadow, OP, [(0, 0.18, 'hold'), (t + 6, 0.18, 'up'), (t + 17, 0.08, 'down'), (t + 28, 0.18, 'hold'), (N, 0.18)])


def main():
    a = Anim('Hop', N, loop='loop')
    tree, shadows = [], []
    for i, (base, shade) in enumerate(COLORS):
        outer, body, shadow, xml, sh = dot(i, base, shade)
        x = 50 + (i - 1) * 32
        tree.append(node(f'Dot {i} at', x, 0, [xml]))
        shadows.append(node(f'Shadow {i} at', x, 0, [sh]))
        hop(a, (outer, body, shadow), i * GAP)
    tree.append(node('Shadows', 0, 0, shadows))
    m = Machine('Loop')
    L = m.layer('Layer')
    L.entry(L.state(a))
    return artboard('Loader', 100, 72, 0, tree, m, [a])


if __name__ == '__main__':
    print('wrote scene.rml', write(HERE, [main()]), 'bytes')
    if '--no-build' not in sys.argv:
        print('Loader.riv', build(HERE, 'Loader'), 'bytes')
