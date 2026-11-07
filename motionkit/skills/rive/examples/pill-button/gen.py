#!/usr/bin/env python3
"""PillButton.riv: a primary button whose whole body is Rive, with the label left to the app.

    python3 gen.py              # write scene.rml, verify, build build/PillButton.riv
    python3 gen.py --no-build   # only write scene.rml

The WORDS are not in the file. The app lays its own text over the body and squashes it with the
same numbers, so every language fits and nothing waits on a font.

Geometry: 1 unit = 1 pt at a 46 pt pill height (the app scales the view by height / 46). The
artboard is 1200 x 84 with the pill centred, drawn with fit = fitHeight, so a pill of any width
sits in the middle of a view only a little wider than itself. The width comes from the app.

State machine "Pill" (legacy inputs, so a runtime's setInput drives it):
  width (number)    the pill's width in units (40 to 1100): a 1D blend of two one-frame poses
  pressed (bool)    squash from the base while the finger is down; a jelly rebound on release
  disabled (bool)   a quiet paper body, a 180 ms mix
  tap (trigger)     a committed tap: a flash over the body and sparkles off both ends
  shine (trigger)   one small jelly wobble
The app fires `shine` every 9 to 16 s while the page is up, never in a loop of its own: every
steady state is a one-frame one-shot, so the machine settles and nothing draws at rest.
Events: "h:press" as the squash lands, "h:pop" on the tap's flash (the app maps them to haptics).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'scripts'))
from uilib import *

AW, AH = 1200, 84
PH = 46                      # pill height
R = PH / 2
W_MIN, W_MAX = 40, 1100
SHADOW_Y = 3
PAPER = 'FFF3F4F8'
SHADOW = 'FF3A62E0'


def rect_id(w, h, r, pid):
    return rect(w, h, r).replace('<Rectangle ', f'<Rectangle id="{pid}" ', 1)


def sparkle(name, x, y, r, sid):
    return shape(name, x, y, sparkle_path(r), fill(WHITE), sid=sid, sx=0, sy=0)


def pill():
    ids = {k: nid() for k in ('root', 'press', 'wob', 'body', 'shadow', 'hi', 'flash', 'l_end', 'r_end', 'body_c')}
    path = {k: nid() for k in ('body', 'shadow', 'shadow2', 'hi', 'flash')}
    m = Machine('Pill')
    width = m.number('width', 300)
    prs = m.bool('pressed')
    dis = m.bool('disabled')
    tap = m.trigger('tap')
    shine = m.trigger('shine')
    ev, ev_xml = events(['h:press', 'h:pop'])
    anims = []

    # ---- the drawing, front first, all inside Press (pivot at the pill's base)
    spk = []
    front = []
    for side, end in ((-1, 'l_end'), (1, 'r_end')):
        ss = [nid(), nid(), nid()]
        spk.append((end, ss))
        front.append(node(f'End {side}', 0, 0, [
            sparkle('Sparkle a', side * 6, -20, 6.5, ss[0]),
            sparkle('Sparkle b', side * 16, -6, 4.2, ss[1]),
            sparkle('Sparkle c', side * 4, 16, 3.4, ss[2]),
        ], nid_=ids[end]))
    front += [
        shape('Flash', 0, 0, rect_id(300, PH, R, path['flash']), fill(WHITE), sid=ids['flash'], opacity=0),
        shape('Highlight', -60, -13.5, rect_id(60, 5, 2.5, path['hi']), fill('B8FFFFFF'), sid=ids['hi']),
        shape('Body', 0, 0, rect_id(300, PH, R, path['body']), fill(PRIMARY, ids['body_c']), sid=ids['body']),
        # One soft diffuse shadow in the body's own hue, close and faint.
        node('Shadow', 0, SHADOW_Y, [
            shape('Shadow wide', 0, 2, rect_id(300, PH + 3, R + 1.5, path['shadow']), fill(SHADOW), opacity=0.12),
            shape('Shadow core', 0, 0, rect_id(300, PH, R, path['shadow2']), fill(SHADOW), opacity=0.24),
        ], nid_=ids['shadow']),
    ]
    content = node('Pill', 0, -R, front)
    root = node('Root', AW / 2, AH / 2 + R,
                [node('Press', 0, 0, [node('Wobble', 0, 0, [content], nid_=ids['wob'])], nid_=ids['press'])], nid_=ids['root'])

    # ---- Size: the width blend of two one-frame poses
    def size_pose(nm, w):
        a = Anim(nm, 1)
        a.hold(path['body'], WIDTH, w).hold(path['shadow'], WIDTH, w + 3).hold(path['shadow2'], WIDTH, w)
        a.hold(path['flash'], WIDTH, w)
        a.hold(path['hi'], WIDTH, min(max(w - 40, 4), 26))
        a.hold(ids['hi'], X, -w / 2 + 34 if w > 70 else 0)
        a.hold(ids['l_end'], X, -w / 2).hold(ids['r_end'], X, w / 2)
        return a
    s_min, s_max = size_pose('Size min', W_MIN), size_pose('Size max', W_MAX)
    anims += [s_min, s_max]
    # Rive mixes a blend's two poses ONTO what is already there, so on its own the result drifts
    # with every advance. A layer under it lays the first pose down at full strength each time.
    base = m.layer('Size base'); base.entry(base.state(s_min))
    m.layer('Size').blend(width, [(s_min, W_MIN), (s_max, W_MAX)])

    # ---- Press: squash from the base, jelly rebound
    rest = Anim('Rest', 1).hold(ids['press'], SX, 1).hold(ids['press'], SY, 1).hold(ids['shadow'], Y, SHADOW_Y)
    down = Anim('Down', 7).key(ids['press'], SX, [(0, 1, 'out'), (7, 1.035)]).key(ids['press'], SY, [(0, 1, 'out'), (7, 0.94)])
    down.key(ids['shadow'], Y, [(0, SHADOW_Y, 'out'), (7, 2)])
    down.event(ev['h:press'], [1])
    up = Anim('Up', 34).key(ids['press'], SX, [(0, 1.035, 'out'), (8, 0.985, 'io'), (16, 1.01, 'io'), (24, 0.997, 'io'), (34, 1)]) \
                       .key(ids['press'], SY, [(0, 0.94, 'out'), (8, 1.04, 'io'), (16, 0.98, 'io'), (24, 1.008, 'io'), (34, 1)]) \
                       .key(ids['shadow'], Y, [(0, 2, 'out'), (10, SHADOW_Y + 2, 'io'), (22, SHADOW_Y)])
    anims += [rest, down, up]
    P_ = m.layer('Press')
    p_rest, p_down, p_up = P_.state(rest), P_.state(down), P_.state(up)
    P_.entry(p_rest)
    P_.go(p_rest, p_down, [('bool', prs, True)])
    P_.go(p_up, p_down, [('bool', prs, True)])
    P_.go(p_down, p_up, [('bool', prs, False)])
    P_.go(p_up, p_rest, exit=100)

    # ---- Tap: a flash and sparkles off both ends. A layer never re-enters the state it is in,
    # so the tap state loops back to itself through an explicit transition (restartable).
    t_still = Anim('Tap still', 1).hold(ids['flash'], OP, 0)
    t = Anim('Tap', 42).key(ids['flash'], OP, [(0, 0, 'out'), (3, 0.3, 'io'), (18, 0)])
    t.event(ev['h:pop'], [3])
    for end, ss in spk:
        for n, sid in enumerate(ss):
            f0 = 3 + n * 3
            t_still.hold(sid, SX, 0).hold(sid, SY, 0)
            for p in (SX, SY):
                t.key(sid, p, [(0, 0, 'hold'), (f0, 0, 'back'), (f0 + 9, 1, 'io'), (f0 + 22, 0)])
    anims += [t_still, t]
    T = m.layer('Tap')
    ts, tt = T.state(t_still), T.state(t)
    T.entry(tt if os.environ.get('PREVIEW') == 'tap' else ts)
    T.go(ts, tt, [('trigger', tap, None)])
    T.go(tt, tt, [('trigger', tap, None)])
    T.go(tt, ts, exit=100)

    # ---- Shine: a little jelly wobble on its own node
    i_still = Anim('Idle still', 1).hold(ids['wob'], SX, 1).hold(ids['wob'], SY, 1)
    sh = Anim('Shine', 40).key(ids['wob'], SX, [(0, 1, 'out'), (6, 1.025, 'io'), (14, 0.992, 'io'), (22, 1.006, 'io'), (32, 1)]) \
                          .key(ids['wob'], SY, [(0, 1, 'out'), (6, 0.955, 'io'), (14, 1.02, 'io'), (22, 0.99, 'io'), (32, 1)])
    anims += [i_still, sh]
    I = m.layer('Idle')
    i0, i_sh = I.state(i_still), I.state(sh)
    I.entry(i_sh if os.environ.get('PREVIEW') == 'shine' else i0)
    I.go(i0, i_sh, [('trigger', shine, None)])
    I.go(i_sh, i0, exit=100)

    # ---- Disabled: paper body, no shadow, a 180 ms mix
    on = Anim('Enabled', 1).hold(ids['shadow'], OP, 1).hold(ids['body_c'], COLOR, PRIMARY).hold(ids['hi'], OP, 1)
    off = Anim('Disabled', 1).hold(ids['shadow'], OP, 0).hold(ids['body_c'], COLOR, PAPER).hold(ids['hi'], OP, 0)
    anims += [on, off]
    D = m.layer('Disabled')
    d_on, d_off = D.state(on), D.state(off)
    D.entry(d_off, [('bool', dis, True)])
    D.entry(d_on)
    D.go(d_on, d_off, [('bool', dis, True)], ms=180)
    D.go(d_off, d_on, [('bool', dis, False)], ms=180)

    return artboard('Pill', AW, AH, 0, [root], m, anims, extra=ev_xml)


if __name__ == '__main__':
    print('wrote scene.rml', write(HERE, [pill()]), 'bytes')
    if '--no-build' not in sys.argv:
        print('PillButton.riv', build(HERE, 'PillButton'), 'bytes')
