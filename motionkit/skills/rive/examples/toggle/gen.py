#!/usr/bin/env python3
"""Toggle.riv: a settings switch. Generated RML, one script, re-run to rebuild.

    python3 gen.py              # write scene.rml, verify, build build/Toggle.riv
    python3 gen.py --no-build   # only write scene.rml

State machine "Toggle":
  on (bool)       the entry picks the resting pose with no motion; a change slides the knob
                  (stretched along its travel, a squash as it lands), recolours the track,
                  and pops a small tick mark that floats away.
  pressed (bool)  the knob squishes while the finger is down, a jelly rebound on release.
Events: "h:on" / "h:off" as the knob lands (the app maps the name to a haptic).

Steady states (Off, On, Rest) are ONE-FRAME animations, so nothing draws at rest.
Units are points at 2x: the artboard is 132 x 100, the track 102 x 62 (a true capsule).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'scripts'))
from uilib import *

LW = 3.0
CX, CY = 66, 50
TRACK_W, TRACK_H = 102, 62
KNOB, INSET = 50, 6
OFF_X = CX - TRACK_W / 2 + INSET + KNOB / 2
ON_X = CX + TRACK_W / 2 - INSET - KNOB / 2
HALF = KNOB / 2


def main():
    knob, squish, slide, track_c, tick = (nid() for _ in range(5))
    m = Machine('Toggle')
    on = m.bool('on')
    prs = m.bool('pressed')
    ev, ev_xml = events(['h:on', 'h:off'])

    # Front first: the tick, then the knob (squash pivot at its base), then the track.
    tick_xml = shape('Tick', ON_X, CY - 22, poly([(-4, 0), (-1, 3), (4, -3)], closed=False),
                     stroke(INK, 2.2), sid=tick, opacity=0)
    knob_body = cel('Knob', lambda s: rect(KNOB, KNOB, KNOB / 2), SURFACE, SURFACE_SHADE, lw=LW, w=8)
    knob_xml = node('Knob', OFF_X, CY, [node('Squish', 0, HALF, [node('Body', 0, -HALF, knob_body, nid_=slide)], nid_=squish)], nid_=knob)
    track = [shape('Track line', CX, CY, rect(TRACK_W, TRACK_H, TRACK_H / 2), stroke(INK, LW)),
             shape('Track', CX, CY, rect(TRACK_W, TRACK_H, TRACK_H / 2), fill(TRACK_OFF, track_c))]
    tree = [tick_xml, knob_xml] + track

    def pose(a, is_on):
        a.hold(knob, X, ON_X if is_on else OFF_X)
        a.hold(track_c, COLOR, PRIMARY if is_on else TRACK_OFF)
        a.hold(slide, SX, 1).hold(slide, SY, 1).hold(tick, OP, 0)

    off_still = Anim('Off', 1); pose(off_still, False)
    on_still = Anim('On', 1); pose(on_still, True)

    def turn(name, to_on):
        a = Anim(name, 40)
        x0, x1 = (OFF_X, ON_X) if to_on else (ON_X, OFF_X)
        a.key(knob, X, [(0, x0, 'out'), (13, x1, 'hold'), (40, x1)])
        # stretched along the travel, then a squash as it lands, then settle
        a.key(slide, SX, [(0, 1, 'out'), (5, 1.22, 'io'), (13, 0.86, 'io'), (19, 1.06, 'io'), (26, 0.98, 'io'), (32, 1)])
        a.key(slide, SY, [(0, 1, 'out'), (5, 0.86, 'io'), (13, 1.1, 'io'), (19, 0.96, 'io'), (26, 1.01, 'io'), (32, 1)])
        a.key(track_c, COLOR, [(0, TRACK_OFF if to_on else PRIMARY, 'io'),
                               (12, PRIMARY if to_on else TRACK_OFF, 'hold'),
                               (40, PRIMARY if to_on else TRACK_OFF)])
        if to_on:
            y0 = CY - 22
            a.key(tick, OP, [(0, 0, 'hold'), (13, 1, 'hold'), (28, 1, 'io'), (40, 0)])
            a.key(tick, Y, [(0, y0, 'hold'), (13, y0, 'out'), (40, y0 - 15)])
        else:
            a.hold(tick, OP, 0)
        a.event(ev['h:on' if to_on else 'h:off'], [12])
        return a

    t_on, t_off = turn('TurnOn', True), turn('TurnOff', False)
    L = m.layer('Switch')
    s_off, s_on, s_ton, s_toff = L.state(off_still), L.state(on_still), L.state(t_on), L.state(t_off)
    if os.environ.get('PREVIEW'):        # headless sheets: start off, so on=true plays TurnOn
        L.entry(s_off)
    else:
        L.entry(s_on, [('bool', on, True)])
        L.entry(s_off, [('bool', on, False)])
    L.go(s_off, s_ton, [('bool', on, True)])
    L.go(s_on, s_toff, [('bool', on, False)])
    L.go(s_ton, s_toff, [('bool', on, False)])
    L.go(s_toff, s_ton, [('bool', on, True)])
    L.go(s_ton, s_on, exit=100)
    L.go(s_toff, s_off, exit=100)

    # A second layer for the press, on a node nothing else keys.
    rest = Anim('Rest', 1).hold(squish, SX, 1).hold(squish, SY, 1)
    down = Anim('Down', 7).key(squish, SX, [(0, 1, 'out'), (7, 1.12)]).key(squish, SY, [(0, 1, 'out'), (7, 0.88)])
    up = Anim('Up', 22).key(squish, SX, [(0, 1.12, 'out'), (8, 0.96, 'io'), (22, 1)]) \
                       .key(squish, SY, [(0, 0.88, 'out'), (8, 1.05, 'io'), (22, 1)])
    P_ = m.layer('Press')
    p_rest, p_down, p_up = P_.state(rest), P_.state(down), P_.state(up)
    P_.entry(p_rest)
    P_.go(p_rest, p_down, [('bool', prs, True)])
    P_.go(p_up, p_down, [('bool', prs, True)])
    P_.go(p_down, p_up, [('bool', prs, False)])
    P_.go(p_up, p_rest, exit=100)
    return artboard('Toggle', 132, 100, 0, tree, m, [off_still, on_still, t_on, t_off, rest, down, up], extra=ev_xml)


if __name__ == '__main__':
    print('wrote scene.rml', write(HERE, [main()]), 'bytes')
    if '--no-build' not in sys.argv:
        print('Toggle.riv', build(HERE, 'Toggle'), 'bytes')
