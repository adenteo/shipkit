#!/usr/bin/env python3
"""lottie_kit: a standard-library Lottie (bodymovin) DSL for small app animations drawn in code.

    import lottie_kit as lk
    lk.use_palette(lk.Palette(ink='#2B2B3A', hero='#FF6B81', accent='#FFD166'))
    c = lk.Comp('hello', 66)
    c.add('heart', [lk.heart_art(100)], p=(150, 150),
          s=lk.K((0, [0, 0], 'out'), (12, [110, 110], 'io'), (20, [100, 100])))
    lk.write(c, 'out/')           # validate, prune, compact, write out/hello.json

Run an example:  python3 build.py ../examples/loading_heart.py --out /tmp/lottie

Rules kept so lottie-ios's Core Animation engine renders exactly what lottie-web shows:
  * every path lives in its own group with its own fill and/or stroke (nothing is inherited
    by child groups, so no group ever combines paths or rescales an inherited stroke)
  * the outline stroke is listed before the fill, so it draws on top in both renderers
    (a CAShapeLayer always strokes over its fill)
  * trims only in stroke-only groups; static dashes only; no mattes, effects, expressions,
    text, images, precomps or 3D. Gradient fills (linear and radial, with opacity stops) and
    layer masks (mode add) ARE fine: the Core Animation engine draws both.
  * haptic beats can live in the file as markers named `haptic:<kind>[@intensity]:<n>` at the
    frame of each impact (Comp.beat); the app fires them, so timings are never guessed in code
  * easing handles keep y inside 0..1: springs and overshoots are explicit keyframes
  * layer transforms carry 3 components, shape transforms 2, as bodymovin writes them
  * every shape transform carries `o` (lottie-web draws nothing without it) and every trim `m`
    (lottie-ios's default dictionary parser requires it); other default fields are omitted
"""
import json
import math
import os
import random
import sys
import re

FPS, W, H = 60, 300, 300


# ----------------------------------------------------------------------------- palette
def _hls(c):
    import colorsys
    r, g, b = (int(c.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def _hex(h, l, s):
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h, max(0, min(1, l)), max(0, min(1, s)))
    return '#%02X%02X%02X' % (round(r * 255), round(g * 255), round(b * 255))


def shade_of(c):
    """The flat shade colour of `c`: a little darker and a little more saturated."""
    h, l, s = _hls(c)
    return _hex(h, l * 0.9, s * 1.08)


class Palette:
    """The colours an animation draws with, by ROLE. Everything in the kit asks the active
    palette, so one animation file re-skins by changing this and nothing else.

    ink      outline colour (dark, a hue close to your brand reads softer than black)
    hero     the main brand colour: the thing the animation is about
    alt      a lighter sibling of hero (small hearts, secondary shapes)
    accent   a warm highlight colour (sparkles, stars)
    accent2  a second warm colour (clappers, doors)
    cool     a cool support colour
    shadow   ground shadows, drawn at low opacity
    confetti the colours confetti() throws
    Shades (`shade_of`) are derived unless you pass `shades={'#hex': '#shade'}`."""

    def __init__(self, ink='#2B2B3A', hero='#F45E77', alt='#FCAFC0', accent='#FFD166',
                 accent2='#FFB347', cool='#8FD0F0', shadow='#2E6C9A', confetti=None, shades=None):
        self.ink, self.hero, self.alt, self.accent = ink, hero, alt, accent
        self.accent2, self.cool, self.shadow = accent2, cool, shadow
        self.confetti = confetti or [alt, hero, accent, cool, accent2, '#FFFFFF']
        self._shades = dict(shades or {})

    def sh(self, c):
        return self._shades.get(c) or shade_of(c)


P = Palette()  # the active palette; use_palette() changes it in place


def use_palette(p):
    P.__dict__.update(p.__dict__)
    return P


WHITE, WHITE_SH = '#FFFFFF', '#E9E9EE'
LINE_W, LINE_O = 2.5, 85  # the outline weight and opacity
# Outline weight multiplier for the animation being built: icons shown far smaller than 300 pt
# should draw heavier lines. write() resets it to 1 after each build.
STYLE = {'ink': 1.0, 'flat': False}


def rgba(hex_color):
    h = hex_color.lstrip('#')
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)] + [1]


# ----------------------------------------------------------------------------- keyframes
# (o.x, o.y, i.x, i.y) of the curve from one key to the next
EASE = {
    'lin': (0.0, 0.0, 1.0, 1.0),
    'io': (0.42, 0.0, 0.58, 1.0),     # ease in-out
    'sine': (0.37, 0.0, 0.63, 1.0),   # gentle in-out, for bobs
    'out': (0.33, 1.0, 0.68, 1.0),    # cubic out
    'out2': (0.16, 1.0, 0.3, 1.0),    # strong out, for bursts
    'outq': (0.5, 1.0, 0.89, 1.0),    # quad out: rising against gravity
    'in': (0.32, 0.0, 0.67, 0.0),     # cubic in
    'inq': (0.11, 0.0, 0.5, 0.0),     # quad in: falling under gravity
    'in2': (0.64, 0.0, 0.78, 0.0),    # strong in
}


class K:
    """An animated property. Keys are (frame, value[, ease]); the ease shapes the move to the next key."""

    def __init__(self, *keys, ease='io'):
        ks = []
        for k in keys:
            t, v = k[0], k[1]
            e = k[2] if len(k) > 2 else ease
            if ks and abs(ks[-1][0] - t) < 1e-9:
                assert _close(ks[-1][1], v), f'two different values at frame {t}: {ks[-1][1]} / {v}'
                ks[-1] = (ks[-1][0], ks[-1][1], e)
                continue
            assert not ks or t > ks[-1][0], f'keys out of order at frame {t}'
            ks.append((t, v, e))
        self.keys = ks

    def json(self, third=None):
        out = []
        for idx, (t, v, e) in enumerate(self.keys):
            s = list(v) if isinstance(v, (list, tuple)) else [v]
            if third is not None and len(s) == 2:
                s = s + [third]
            d = {'t': t, 's': s}
            if idx < len(self.keys) - 1:
                if e == 'hold' or _close(v, self.keys[idx + 1][1]):  # no change: a hold is identical and smaller
                    d['h'] = 1
                else:
                    ox, oy, ix, iy = EASE[e] if isinstance(e, str) else e
                    d['o'] = {'x': ox, 'y': oy}  # scalar handles: accepted by lottie-web and both
                    d['i'] = {'x': ix, 'y': iy}  # lottie-ios parsers, one curve for every dimension
            out.append(d)
        return {'a': 1, 'k': out}


def _close(a, b):
    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        if not isinstance(a, (list, tuple)) or not isinstance(b, (list, tuple)):
            return False
        return len(a) == len(b) and all(abs(x - y) < 1e-6 for x, y in zip(a, b))
    return abs(a - b) < 1e-6


def prop(v, third=None):
    if isinstance(v, K):
        return v.json(third)
    if isinstance(v, (list, tuple)):
        v = list(v)
        if third is not None and len(v) == 2:
            v = v + [third]
    return {'a': 0, 'k': v}


def pop(t, to=100.0, frm=0.0, over=(1.18, 0.93, 1.03), d=(7, 5, 5, 5), e0='out'):
    """Spring keys for a scalar: overshoot, undershoot, small overshoot, settle."""
    span = to - frm
    vals = [frm + span * o for o in over] + [to]
    assert len(d) == len(vals), 'pop needs one duration per overshoot plus the settle'
    keys, tt = [(t, frm, e0)], t
    for dt, v in zip(d, vals):
        tt += dt
        keys.append((tt, v, 'io'))
    return keys


def uni(keys):
    """Scalar keys -> uniform scale keys."""
    return [(k[0], [k[1], k[1]]) + tuple(k[2:]) for k in keys]


# ----------------------------------------------------------------------------- shape items
def sh_item(v, i, o, closed=True):
    return {'ty': 'sh', 'ks': {'a': 0, 'k': {'c': closed, 'v': v, 'i': i, 'o': o}}}


def rc(w, h, r=0, x=0, y=0):
    return {'ty': 'rc', 's': prop([w, h]), 'p': prop([x, y]), 'r': prop(r)}


def el(w, h, x=0, y=0):
    return {'ty': 'el', 's': prop([w, h]), 'p': prop([x, y])}


def fl(c, o=100):
    return {'ty': 'fl', 'c': prop(rgba(c)), 'o': prop(o)}


def st(c=None, w=LINE_W, o=LINE_O, lc=2, lj=2, dash=None):
    if c is None or c == P.ink:
        c = P.ink
        w = w * STYLE['ink']
    d = {'ty': 'st', 'c': prop(rgba(c)), 'o': prop(o), 'w': prop(w), 'lc': lc, 'lj': lj}
    if dash:
        d['d'] = [{'n': 'd', 'nm': 'dash', 'v': prop(dash[0])},
                  {'n': 'g', 'nm': 'gap', 'v': prop(dash[1])},
                  {'n': 'o', 'nm': 'offset', 'v': prop(0)}]
    return d


def tm(s=0, e=100, o=0):
    return {'ty': 'tm', 's': prop(s), 'e': prop(e), 'o': prop(o), 'm': 1}


def tr(p=(0, 0), a=(0, 0), s=(100, 100), r=0, o=100):
    """Shape transform; static p/a/s/r at their defaults are omitted (both engines default them)."""
    d = {'ty': 'tr'}
    for key, v, default in (('p', p, [0, 0]), ('a', a, [0, 0]), ('s', s, [100, 100]), ('r', r, 0)):
        if isinstance(v, K) or not _close(v if not isinstance(v, tuple) else list(v), default):
            d[key] = prop(v)
    d['o'] = prop(o)  # lottie-web reads the group opacity unconditionally
    return d


def piece(path, fill=None, stroke=None, trim=None, nm=None, **t):
    """One path and its own styles: what the Core Animation engine draws as one CAShapeLayer.
    fill: colour string or fl(); stroke: True (the outline) or st()."""
    it = [path]
    if trim:
        it.append(trim)
    if stroke:
        it.append(st() if stroke is True else stroke)
    if fill:
        it.append(fl(fill) if isinstance(fill, str) else fill)
    it.append(tr(**t))
    g = {'ty': 'gr', 'it': it}
    if nm:
        g['nm'] = nm
    return g


def G(kids, nm=None, **t):
    """A container group; kids are listed back to front (painter's order)."""
    g = {'ty': 'gr', 'it': list(reversed(kids)) + [tr(**t)]}
    if nm:
        g['nm'] = nm
    return g


# ----------------------------------------------------------------------------- paths
def bez(start, segs, closed=True):
    """Path from absolute cubic segments (c1, c2, end); c1/c2 None means a straight line."""
    v, i, o = [list(start)], [[0, 0]], []
    cur = start
    for n, (c1, c2, p) in enumerate(segs):
        c1 = cur if c1 is None else c1
        c2 = p if c2 is None else c2
        o.append([c1[0] - cur[0], c1[1] - cur[1]])
        if closed and n == len(segs) - 1:
            assert math.dist(p, start) < 1e-6, 'closed path must end at its start'
            i[0] = [c2[0] - start[0], c2[1] - start[1]]
        else:
            v.append(list(p))
            i.append([c2[0] - p[0], c2[1] - p[1]])
        cur = p
    if not closed:
        o.append([0, 0])
    return sh_item(v, i, o, closed)


def smooth(points, closed=False, tension=1 / 6):
    """Catmull-Rom through points, as a bezier path."""
    n = len(points)
    segs = []
    rng = range(n) if closed else range(n - 1)
    for k in rng:
        p0 = points[(k - 1) % n] if (closed or k > 0) else points[k]
        p1 = points[k]
        p2 = points[(k + 1) % n]
        p3 = points[(k + 2) % n] if (closed or k + 2 < n) else points[(k + 1) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) * tension, p1[1] + (p2[1] - p0[1]) * tension)
        c2 = (p2[0] - (p3[0] - p1[0]) * tension, p2[1] - (p3[1] - p1[1]) * tension)
        segs.append((c1, c2, p2))
    return bez(points[0], segs, closed)


# A plump heart: two round lobes meeting in a real cusp, sides that curve all the way into the
# point, in a 100-unit box (x 2..98, y 8..92). Cubic segments (c1, c2, end) from START, clockwise.
_HSTART = (50.0, 27.0)
_HEART = [
    ((53.0, 14.0), (62.0, 8.0), (73.0, 8.0)),
    ((88.0, 8.0), (98.0, 19.0), (98.0, 34.0)),
    ((98.0, 58.0), (70.0, 76.0), (50.0, 92.0)),
    ((30.0, 76.0), (2.0, 58.0), (2.0, 34.0)),
    ((2.0, 19.0), (12.0, 8.0), (27.0, 8.0)),
    ((38.0, 8.0), (47.0, 14.0), (50.0, 27.0)),
]
_HW, _HH, _HC = 96.0, 84.0, (50.0, 50.0)
HEART_H = _HH / _HW  # height / width


def heart(w, cx=0, cy=0):
    k = w / _HW

    def T(p):
        return (cx + (p[0] - _HC[0]) * k, cy + (p[1] - _HC[1]) * k)
    return bez(T(_HSTART), [(T(a), T(b), T(c)) for a, b, c in _HEART])


def sparkle(r, cx=0, cy=0, ka=0.26, kb=0.06):
    """Four-point sparkle with concave sides; tips at radius r."""
    tips = [(0, -1), (1, 0), (0, 1), (-1, 0)]
    P = lambda x, y: (cx + x * r, cy + y * r)
    segs = []
    for k in range(4):
        a, b = tips[k], tips[(k + 1) % 4]
        c1 = P(a[0] * ka + b[0] * kb, a[1] * ka + b[1] * kb)
        c2 = P(a[0] * kb + b[0] * ka, a[1] * kb + b[1] * ka)
        segs.append((c1, c2, P(*b)))
    return bez(P(*tips[0]), segs)


def flower(R, r, n=6, cx=0, cy=0, rot=-90, roundness=0.46):
    """Scalloped daisy outline: n round petals reaching radius R, valleys at radius r."""
    step = 2 * math.pi / n
    rot = math.radians(rot)
    pol = lambda rad, ang: (cx + rad * math.cos(ang), cy + rad * math.sin(ang))
    valleys = [pol(r, rot + (k + 0.5) * step) for k in range(n)]
    d = step * roundness
    rc_ = (8 * R - 2 * r * math.cos(step / 2)) / (6 * math.cos(d))
    segs = []
    for k in range(n):
        th = rot + k * step
        segs.append((pol(rc_, th - d), pol(rc_, th + d), valleys[k]))
    return bez(valleys[-1], segs)


# ----------------------------------------------------------------------------- art kit
def gloss(x, y, w, h, r=0, o=92, c=WHITE):
    return piece(el(w, h), fill=fl(c, o), p=(x, y), r=r)


def bbox(item):
    """The box of a path item (el / rc / sh) in its group's space."""
    if item['ty'] in ('el', 'rc'):
        (w, h), (x, y) = item['s']['k'], item['p']['k']
        return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    k = item['ks']['k']
    pts = list(k['v'])
    for v, i_, o_ in zip(k['v'], k['i'], k['o']):
        pts += [(v[0] + i_[0], v[1] + i_[1]), (v[0] + o_[0], v[1] + o_[1])]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def blob(mk, color, shade=None, inset=None, hl=(), line=True, lw=LINE_W, nm=None, grad=True, **t):
    """Shaded outlined object. The base is drawn in the shade colour and the main colour is an
    inset copy scaled toward `inset` = (anchor x, anchor y, percent), so a soft darker crescent shows
    along the far edges without any mask. The main colour is a diagonal gradient from a lighter tint
    at the top left (depth, as the badges in the reference have), with a faint white inner rim on
    anything big enough to carry one. Highlights sit on top, then the outline."""
    kids = []
    fill = color
    big = False
    if grad and not STYLE['flat'] and not color.upper().startswith('#FFFFFF'):
        x0, y0, x1, y1 = bbox(mk())
        big = min(x1 - x0, y1 - y0) >= 26
        fill = gfill([(0, mix(color, WHITE, 0.42)), (0.6, color), (1, color)], (x0, y0), (x1, y1))
    if shade:
        ax, ay, k = inset
        kids.append(piece(mk(), fill=shade))
        kids.append(piece(mk(), fill=fill, a=(ax, ay), p=(ax, ay), s=(k, k)))
    else:
        kids.append(piece(mk(), fill=fill))
    if big:
        x0, y0, x1, y1 = bbox(mk())
        cxm, cym = (x0 + x1) / 2, (y0 + y1) / 2
        kids.append(piece(mk(), stroke=st(WHITE, 2, 38), a=(cxm, cym), p=(cxm, cym - 0.6), s=(86, 86)))
    kids.extend(hl)
    if line:
        kids.append(piece(mk(), stroke=st(w=lw)))
    return G(kids, nm=nm, **t)


def heart_art(w, color=None, shade=None, cx=0, cy=0, shine=True, lw=LINE_W, line=True, inset=92, **t):
    color = color or P.hero
    shade = shade or P.sh(color)
    h = w * HEART_H
    hl = []
    if shine:
        hl = [gloss(cx - w * 0.25, cy - h * 0.17, w * 0.17, h * 0.12, r=-30, o=55)]  # one soft blob 
    return blob(lambda: heart(w, cx, cy), color, shade, inset=(cx - w * 0.3, cy - h * 0.34, inset),
                hl=hl, line=line, lw=lw, **t)


def sparkle_art(rad, color=None, shade=None, lw=2.2, line=True, cx=0, cy=0, **t):
    color = color or P.accent
    return blob(lambda: sparkle(rad, cx, cy), color, shade, inset=(cx - rad * 0.3, cy - rad * 0.3, 88),
                line=line, lw=lw, **t)


def shadow(w, h, o=16):
    """A contact shadow, soft at its edge (a radial gradient, never a blur)."""
    return soft_shadow(w * 1.12, h * 1.3, o * 1.55)


# ----------------------------------------------------------------------------- rich kit
# Depth without blur: gradient fills, radial glows, soft contact shadows, inner rims, masked
# light sweeps, trim-path rims that draw themselves on, ray bursts, shock rings, twinkles and
# confetti. Everything the Core Animation engine renders natively.
HAPTICS = ('light', 'medium', 'heavy', 'rigid', 'soft', 'selection', 'success', 'celebrate')


def gfill(stops, start, end, radial=False, o=100):
    """Gradient fill. stops: (position 0..1, '#hex'[, opacity 0..100]). start/end are in the
    group's space; a radial gradient's radius is |end - start|."""
    cols, alph = [], []
    for st_ in stops:
        pos, c = st_[0], st_[1]
        op_ = st_[2] if len(st_) > 2 else 100
        r, g, b, _ = rgba(c)
        cols += [pos, r, g, b]
        alph += [pos, op_ / 100]
    k = cols if all(a >= 0.999 for a in alph[1::2]) else cols + alph
    d = {'ty': 'gf', 'o': prop(o), 'r': 1, 'bm': 0, 'g': {'p': len(stops), 'k': prop(k)},
         's': prop(list(start)), 'e': prop(list(end)), 't': 2 if radial else 1}
    if radial:
        d['h'] = prop(0)
        d['a'] = prop(0)
    return d


def mix(c1, c2, t):
    a, b = rgba(c1), rgba(c2)
    return '#' + ''.join(f'{round((a[i] + (b[i] - a[i]) * t) * 255):02X}' for i in range(3))


def glow(d, color=WHITE, o=70, cx=0, cy=0, **t):
    """A soft round glow: radial gradient to nothing, no blur."""
    return piece(el(d, d, cx, cy), fill=gfill([(0, color, o), (0.55, color, o * 0.45), (1, color, 0)],
                                              (cx, cy), (cx + d / 2, cy), radial=True), **t)


def soft_shadow(w, h, o=22, color=None, cx=0, cy=0, **t):
    """A contact shadow that fades at its edge (an ellipse scaled from a radial gradient)."""
    color = color or P.shadow
    return piece(el(w, h, cx, cy), fill=gfill([(0, color, o), (0.6, color, o * 0.55), (1, color, 0)],
                                              (cx, cy), (cx + w / 2, cy), radial=True), **t)


def rich(mk, light, color, shade, box, hl=(), lw=LINE_W, rim=True, line=True, inset=95, nm=None, **t):
    """An outlined object with depth: the shade as a crescent at the far edge, a diagonal gradient
    body from `light` (top left of `box` = (x0, y0, x1, y1)) to `color`, a thin white inner rim,
    highlights, then the warm outline."""
    x0, y0, x1, y1 = box
    body = color if STYLE['flat'] else gfill([(0, light), (0.55, color), (1, color)], (x0, y0), (x1, y1))
    kids = [piece(mk(), fill=shade), piece(mk(), fill=body, a=(x0, y0), p=(x0, y0), s=(inset, inset))]
    if rim and not STYLE['flat']:
        cxm, cym = (x0 + x1) / 2, (y0 + y1) / 2
        kids.append(piece(mk(), stroke=st(WHITE, 2.2, 45), a=(cxm, cym), p=(cxm, cym - 0.8), s=(88, 88)))
    kids.extend(hl)
    if line:
        kids.append(piece(mk(), stroke=st(w=lw)))
    return G(kids, nm=nm, **t)


def rich_heart(w, color=None, shade=None, light=None, cx=0, cy=0, lw=LINE_W, **t):
    color = color or P.hero
    shade = shade or P.sh(color)
    h = w * HEART_H
    light = light or mix(color, WHITE, 0.45)
    hl = [] if STYLE['flat'] else [gloss(cx - w * 0.25, cy - h * 0.17, w * 0.17, h * 0.12, r=-30, o=55)]
    return rich(lambda: heart(w, cx, cy), light, color, shade,
                (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), hl=hl, lw=lw, **t)


def ellipse_path(w, h, cx=0, cy=0):
    k = 0.5523
    rx, ry = w / 2, h / 2
    return bez((cx, cy - ry), [((cx + rx * k, cy - ry), (cx + rx, cy - ry * k), (cx + rx, cy)),
                               ((cx + rx, cy + ry * k), (cx + rx * k, cy + ry), (cx, cy + ry)),
                               ((cx - rx * k, cy + ry), (cx - rx, cy + ry * k), (cx - rx, cy)),
                               ((cx - rx, cy - ry * k), (cx - rx * k, cy - ry), (cx, cy - ry))])


def rrect_path(w, h, r, cx=0, cy=0):
    """A rounded rectangle as a bezier path (rc() cannot be a mask or be trimmed from a corner)."""
    k = 0.5523 * r
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    return bez((x0 + r, y0), [(None, None, (x1 - r, y0)), ((x1 - r + k, y0), (x1, y0 + r - k), (x1, y0 + r)),
                              (None, None, (x1, y1 - r)), ((x1, y1 - r + k), (x1 - r + k, y1), (x1 - r, y1)),
                              (None, None, (x0 + r, y1)), ((x0 + r - k, y1), (x0, y1 - r + k), (x0, y1 - r)),
                              (None, None, (x0, y0 + r)), ((x0, y0 + r - k), (x0 + r - k, y0), (x0 + r, y0))])


def sweep(c, nm, mask, t0, t1, x0, x1, cy=0, w=38, h=360, angle=22, o=75, parent=None, ip=None, op=None):
    """A glossy band of light crossing `mask` (a path in the layer's space) from x0 to x1."""
    band = piece(rc(w, h, 0), fill=gfill([(0, WHITE, 0), (0.5, WHITE, o), (1, WHITE, 0)], (-w / 2, 0), (w / 2, 0)),
                 p=K((t0, [x0, cy], 'io'), (t1, [x1, cy])), r=angle)
    thin = piece(rc(w * 0.28, h, 0), fill=fl(WHITE, o * 0.6),
                 p=K((t0 + 3, [x0 - w * 0.9, cy], 'io'), (t1 + 3, [x1 - w * 0.9, cy])), r=angle)
    c.add(nm, [thin, band], ip=t0 if ip is None else ip, op=(t1 + 4) if op is None else op,
          parent=parent, masks=[mask])


def draw_on(path_fn, t0, t1, color=WHITE, w=3.0, o=95, ease='io', glow_w=None):
    """A line that draws itself along `path_fn()` from t0 to t1 (a neon rim), with an optional
    wide faint copy under it for glow."""
    kids = []
    if glow_w:
        kids.append(piece(path_fn(), stroke=st(color, glow_w, o * 0.28), trim=tm(e=K((t0, 0, ease), (t1, 100)))))
    kids.append(piece(path_fn(), stroke=st(color, w, o), trim=tm(e=K((t0, 0, ease), (t1, 100)))))
    return kids


def runner(path_fn, t0, t1, color=WHITE, w=4.0, o=95, length=22, ease='io'):
    """A short bright dash that runs once round `path_fn()`."""
    return piece(path_fn(), stroke=st(color, w, o),
                 trim=tm(s=K((t0, 0, ease), (t1, 100 - length)), e=K((t0, length, ease), (t1, 100))))


def rays(n, r0, r1, spread_deg, colors, o=55, phase=0):
    """A starburst: n wedges from radius r0 to r1, each fading outward (radial gradient)."""
    kids = []
    for k in range(n):
        a = math.radians(phase + k * 360 / n)
        hw_ = math.radians(spread_deg) / 2
        p = [(r0 * math.cos(a - hw_ * 0.4), r0 * math.sin(a - hw_ * 0.4)),
             (r1 * math.cos(a - hw_), r1 * math.sin(a - hw_)),
             (r1 * math.cos(a + hw_), r1 * math.sin(a + hw_)),
             (r0 * math.cos(a + hw_ * 0.4), r0 * math.sin(a + hw_ * 0.4))]
        path = bez(p[0], [(None, None, p[1]), (None, None, p[2]), (None, None, p[3]), (None, None, p[0])])
        col = colors[k % len(colors)]
        kids.append(piece(path, fill=gfill([(0, col, o), (0.7, col, o * 0.5), (1, col, 0)], (0, 0), (r1, 0), radial=True)))
    return kids


def ring(c, nm, t, center, d0, d1, color=WHITE, w=5, o=90, dur=22, parent=None, squash=100, at=None):
    """A shock ring that expands from d0 to d1 and fades. It fades IN over its first frames too: a
    ring born at full opacity shows as a crisp little dot for a frame (the paywall gift's drop rings
    read as a stray "o" on the box). `squash` flattens it (a ripple seen at an angle)."""
    k = squash / 100
    c.add(nm, [piece(el(100, 100), stroke=st(color, w * 100 / ((d0 + d1) / 2), o))], ip=t, op=t + dur + 1,
          p=center, s=K((t, [d0, d0 * k], 'out2'), (t + dur, [d1, d1 * k])),
          o=K((t, 0, 'lin'), (t + 3, 100, 'lin'), (t + dur * 0.4, 90, 'in'), (t + dur, 0)), parent=parent, at=at)


def twinkle(r, t0, period=34, color=None, lw=2.0, until=None, **t):
    """A sparkle that pops in and then twinkles (shrinks and swells, turning) until `until`."""
    keys = [(t0, [0, 0], 'out'), (t0 + 7, [120, 120], 'io'), (t0 + 12, [100, 100], 'sine')]
    rk = [(t0, -45, 'out'), (t0 + 12, 0, 'sine')]
    tt = t0 + 12
    end = until or (t0 + 12)
    while tt + period <= end:
        keys += [(tt + period / 2, [55, 55], 'sine'), (tt + period, [100, 100], 'sine')]
        rk += [(tt + period, rk[-1][1] + 45, 'sine')]
        tt += period
    art = sparkle_art(r, color or P.accent, None, lw=lw)
    return G([art], s=K(*keys), r=K(*rk), **t)


def confetti(t0, origin, n=26, seed=1, speed=(150, 260), angle=(-160, -20), gravity=520, life=(36, 54),
             colors=None, kinds=('rect', 'rect', 'dot', 'heart', 'spark'), scale=1.0):
    """One layer's worth of confetti: n bits thrown from `origin` on ballistic arcs (speed in px/s,
    gravity in px/s^2). Three keys a bit, as `posted` does it: an outer group drifts sideways with
    drag, an inner group rises (quad out) to its apex and falls (quad in); the ribbon bits flip as
    they tumble, everything spins, shrinks and fades."""
    rng = random.Random(seed)
    cols = colors or P.confetti
    kids = []
    for i in range(n):
        ang = math.radians(rng.uniform(*angle))
        v = rng.uniform(*speed)
        vx, vy = v * math.cos(ang), v * math.sin(ang)     # vy < 0 is up
        L = rng.randint(*life)
        ts = t0 + rng.choice((0, 0, 1, 2, 3))
        T = L / FPS
        dx = vx * T * 0.72                                   # drag
        up = max(0.0, -vy)
        ta = min(T * 0.6, up / gravity)                      # seconds to the apex
        rise = up * ta - 0.5 * gravity * ta * ta
        fall = 0.5 * gravity * (T - ta) ** 2
        fa = max(ts + 2, round(ts + ta * FPS))
        kind = rng.choice(kinds)
        col = rng.choice(cols)
        spin = rng.uniform(-540, 540)
        r0 = rng.uniform(0, 360)
        sz = rng.uniform(0.8, 1.25) * scale
        if kind == 'rect':
            shape = rc(9 * sz, 4.4 * sz, 1.4 * sz)
            per = rng.randint(7, 11)
            # two flips are enough to read as a ribbon tumbling (each key costs bytes)
            flips = [(ts + q, [100, 100] if (q // per) % 2 == 0 else [22, 100], 'sine')
                     for q in range(per, L - 10, per)][:3]
            sk = K((0, [0, 0], 'hold'), (ts, [0, 0], 'out2'), (ts + 3, [100, 100], 'sine'), *flips,
                   (ts + L - 8, [100, 100], 'in'), (ts + L, [40, 40]))
            fill = col
        else:
            shape = el(5.6 * sz, 5.6 * sz) if kind == 'dot' else heart(10 * sz) if kind == 'heart' else sparkle(4.6 * sz)
            fill = P.accent if kind == 'spark' else col
            sk = K((0, [0, 0], 'hold'), (ts, [0, 0], 'out2'), (ts + 4, [110, 110], 'io'), (ts + 8, [100, 100], 'lin'),
                   (ts + L - 10, [100, 100], 'in'), (ts + L, [30, 30]))
        bit = piece(shape, fill=fill, r=K((ts, r0, 'lin'), (ts + L, r0 + spin)), s=sk)
        yk = [(ts, [0, 0], 'outq')]
        if fa > ts and rise > 0.5:
            yk.append((fa, [0, -rise], 'inq'))
        yk.append((ts + L, [0, -rise + fall]))
        # invisible before its start through its scale (held at 0), so the fade needs only two keys
        kids.append(G([G([bit], p=K(*yk))], p=K((ts, list(origin), 'out'), (ts + L, [origin[0] + dx, origin[1]])),
                      o=K((ts + L - 12, 100, 'in'), (ts + L, 0))))
    return kids


# ----------------------------------------------------------------------------- composition
class Comp:
    def __init__(self, name, frames, w=None, h=None):
        self.name, self.op, self.layers = name, frames, []
        # Most are 300 x 300 tiles; a full-screen one (celebrate) is taller.
        self.w, self.h = w or W, h or H

    def add(self, nm, kids, ip=0, op=None, p=(0, 0), a=(0, 0), s=(100, 100), r=0, o=100, parent=None, at=None,
            masks=None):
        """Layers are added back to front (or inserted at index `at`); kids are listed back to front.
        `parent` names an earlier layer whose transform this one inherits. `masks` are path items
        (bez / heart / ...) in the layer's own space: only what falls inside them draws."""
        l = dict(nm=nm, kids=kids, ip=ip, op=op or self.op, p=p, a=a, s=s, r=r, o=o, parent=parent, masks=masks)
        self.layers.insert(len(self.layers) if at is None else at, l)

    def beat(self, frame, kind, intensity=None):
        """A haptic at `frame` (see the module docstring): light, medium, heavy, rigid, soft,
        selection, success or celebrate; `intensity` 0..1 for the impact kinds."""
        if not hasattr(self, 'beats'):
            self.beats = []
        self.beats.append((frame, kind, intensity))

    def index(self, nm):
        """Where the layer named `nm` sits (for `at=` inserts)."""
        return next(n for n, l in enumerate(self.layers) if l['nm'] == nm)

    def loop_haptics(self):
        """A looping file whose first pass should still be felt (the paywall's gift)."""
        self.first_loop = True

    def json(self):
        layers = []
        ind = {l['nm']: idx + 1 for idx, l in enumerate(reversed(self.layers))}
        for idx, l in enumerate(reversed(self.layers)):
            layers.append({
                'ddd': 0, 'ind': idx + 1, 'ty': 4, 'nm': l['nm'], 'sr': 1,
                'ks': {'o': prop(l['o']), 'r': prop(l['r']), 'p': prop(l['p'], 0),
                       'a': prop(l['a'], 0), 's': prop(l['s'], 100)},
                'ao': 0, 'shapes': list(reversed(l['kids'])),
                'ip': l['ip'], 'op': l['op'], 'st': 0, 'bm': 0})
            if l['parent']:
                layers[-1]['parent'] = ind[l['parent']]
            if l.get('masks'):
                layers[-1]['hasMask'] = True
                layers[-1]['masksProperties'] = [
                    {'inv': False, 'mode': 'a', 'pt': {'a': 0, 'k': m['ks']['k']}, 'o': {'a': 0, 'k': 100},
                     'x': {'a': 0, 'k': 0}, 'nm': f'Mask {n + 1}'} for n, m in enumerate(l['masks'])]
        markers = []
        if getattr(self, 'first_loop', False):
            markers.append({'tm': 0, 'cm': 'haptics:first-loop', 'dr': 0})
        for n, (f, kind, k) in enumerate(sorted(getattr(self, 'beats', []), key=lambda b: b[0])):
            assert kind in HAPTICS, f'unknown haptic {kind}'
            assert 0 <= f < self.op, f'haptic at {f} outside the comp'
            tag = kind if k is None else f'{kind}@{k:g}'
            markers.append({'tm': f, 'cm': f'haptic:{tag}:{n}', 'dr': 0})
        return {'v': '5.7.4', 'fr': FPS, 'ip': 0, 'op': self.op, 'w': self.w, 'h': self.h, 'nm': self.name,
                'ddd': 0, 'assets': [], 'layers': layers, 'markers': markers}


def compact(x, nd=1):
    """Round for size: 0.1 px geometry, 3 decimals for colours and easing handles."""
    if isinstance(x, float):
        r = round(x, nd)
        return int(r) if r == int(r) else r
    if isinstance(x, list):
        return [compact(v, nd) for v in x]
    if isinstance(x, dict):
        if 'x' in x and 'y' in x:  # an easing handle
            nd = 3
        return {k: compact(v, 3 if k in ('c', 't', 'g') else nd) for k, v in x.items()}
    return x



# ----------------------------------------------------------------------------- checks
def validate(doc):
    """Structural checks for things either renderer would silently get wrong."""
    problems = []
    op = doc['op']

    def check_prop(pth, pr):
        if not isinstance(pr, dict) or pr.get('a') != 1:
            return
        ks = pr['k']
        for a, b in zip(ks, ks[1:]):
            if b['t'] <= a['t']:
                problems.append(f'{pth}: key times not increasing')
            if 'o' in a:
                for hv in (a['o']['y'], a['i']['y'], a['o']['x'], a['i']['x']):
                    if hv < 0 or hv > 1:
                        problems.append(f'{pth}: easing handle outside 0..1')
        n = {len(k['s']) for k in ks}
        if len(n) != 1:
            problems.append(f'{pth}: keys with different dimensions')

    def walk_items(pth, items, top=False):
        paths = [x for x in items if x['ty'] in ('sh', 'rc', 'el', 'sr')]
        styles = [x for x in items if x['ty'] in ('fl', 'st', 'gf', 'gs')]
        groups = [x for x in items if x['ty'] == 'gr']
        trims = [x for x in items if x['ty'] == 'tm']
        if len(paths) > 1:
            problems.append(f'{pth}: {len(paths)} paths in one group')
        if styles and not paths:
            problems.append(f'{pth}: styles with no path of their own (would be inherited)')
        if paths and groups:
            problems.append(f'{pth}: paths mixed with child groups')
        if trims and any(s['ty'] == 'fl' for s in styles):
            problems.append(f'{pth}: trim on a filled shape (Core Animation cannot)')
        if not top and items and items[-1]['ty'] != 'tr':
            problems.append(f'{pth}: group transform must be last')
        order = [x['ty'] for x in items]
        if 'st' in order and 'fl' in order and order.index('st') > order.index('fl'):
            problems.append(f'{pth}: fill listed before stroke')
        for x in items:
            if x['ty'] == 'sh':
                k = x['ks']['k']
                if not (len(k['v']) == len(k['i']) == len(k['o'])):
                    problems.append(f'{pth}: path v/i/o length mismatch')
            for key, v in x.items():
                if isinstance(v, dict) and 'a' in v:
                    check_prop(f'{pth}.{x["ty"]}.{key}', v)
            if x['ty'] == 'gr':
                walk_items(f'{pth}/{x.get("nm", "gr")}', x['it'])

    for l in doc['layers']:
        if l['ip'] < 0 or l['op'] > op or l['ip'] >= l['op']:
            problems.append(f'{l["nm"]}: bad ip/op {l["ip"]}..{l["op"]}')
        for key, v in l['ks'].items():
            check_prop(f'{l["nm"]}.ks.{key}', v)
        walk_items(l['nm'], l['shapes'], top=True)
    return problems


def _ease_at(k0, k1, f):
    """Value of a keyed property between keys k0 and k1 at frame f (cubic-bezier easing, holds)."""
    t0, t1 = k0['t'], k1['t']
    v0, v1 = k0['s'], k1['s']
    if k0.get('h'):
        return v0
    u = (f - t0) / (t1 - t0)
    ox, oy = k0['o']['x'], k0['o']['y']
    ix, iy = k0['i']['x'], k0['i']['y']
    ox = ox[0] if isinstance(ox, list) else ox
    oy = oy[0] if isinstance(oy, list) else oy
    ix = ix[0] if isinstance(ix, list) else ix
    iy = iy[0] if isinstance(iy, list) else iy
    lo, hi = 0.0, 1.0
    for _ in range(30):                      # solve bezier x(s) = u
        m = (lo + hi) / 2
        x = 3 * (1 - m) ** 2 * m * ox + 3 * (1 - m) * m * m * ix + m ** 3
        lo, hi = (m, hi) if x < u else (lo, m)
    m = (lo + hi) / 2
    y = 3 * (1 - m) ** 2 * m * oy + 3 * (1 - m) * m * m * iy + m ** 3
    return [a + (b - a) * y for a, b in zip(v0, v1)]


def value_at(pr, f):
    if not isinstance(pr, dict):
        return None
    if pr.get('a') != 1:
        v = pr['k']
        return v if isinstance(v, list) else [v]
    ks = pr['k']
    if f <= ks[0]['t']:
        return ks[0]['s']
    for k0, k1 in zip(ks, ks[1:]):
        if k0['t'] <= f < k1['t']:
            return _ease_at(k0, k1, f)
    return ks[-1]['s']


def tiny_visible(doc, scale=0.22, min_run=1):
    """Anything drawn at a sliver of its own size: a styled path whose effective scale (layer times
    every group above it) is above zero but under `scale`, at over 30 percent opacity, while it is
    still GROWING (before its beat), for `min_run` frames or more. A pop born at zero passes; a ring
    born at 12 percent at full opacity (the paywall gift's stray "o", one crisp frame at each drop)
    does not. Things shrinking away at the end of their life are left alone."""
    found = []
    for l in doc['layers']:
        ip, op = l['ip'], l['op']

        def leaves(items, chain):
            tr_ = next((x for x in items if x['ty'] == 'tr'), None)
            chain = chain + [tr_] if tr_ else chain
            paths = [x for x in items if x['ty'] in ('el', 'rc', 'sh')]
            styled = any(x['ty'] in ('fl', 'gf', 'st') for x in items)
            for x in items:
                if x['ty'] == 'gr':
                    yield from leaves(x['it'], chain)
            if paths and styled:
                yield paths[0], chain

        for path, chain in leaves(l['shapes'], []):
            if path['ty'] in ('el', 'rc'):
                sz = value_at(path['s'], ip)
                size = max(sz) if sz else 0
            else:
                v = path['ks']['k']['v']
                size = max(max(p[0] for p in v) - min(p[0] for p in v), max(p[1] for p in v) - min(p[1] for p in v))
            def eff(f):
                k = max(abs(v) for v in value_at(l['ks']['s'], f)[:2]) / 100
                for t_ in chain:
                    if 's' in t_:
                        k *= max(abs(v) for v in value_at(t_['s'], f)[:2]) / 100
                return k
            run, first = 0, None
            for f in range(ip, op):
                sc, o = 1.0, 1.0
                ls = value_at(l['ks']['s'], f)
                sc *= max(abs(ls[0]), abs(ls[1])) / 100
                o *= value_at(l['ks']['o'], f)[0] / 100
                for t_ in chain:
                    if 's' in t_:
                        gs = value_at(t_['s'], f)
                        sc *= max(abs(gs[0]), abs(gs[1])) / 100
                    if 'o' in t_:
                        o *= value_at(t_['o'], f)[0] / 100
                growing = eff(f + 1) > sc + 1e-4
                if 0.001 < sc < scale and o > 0.3 and size * sc > 0.3 and growing:
                    run += 1
                    first = f if run == 1 else first
                else:
                    if run >= min_run:
                        found.append(f'{l["nm"]}: {run} frames from f{first} at {size:.0f} px x scale')
                    run = 0
            if run >= min_run:
                found.append(f'{l["nm"]}: {run} frames from f{first} at {size:.0f} px x scale')
    return sorted(set(found))


# ----------------------------------------------------------------------------- keyframe pruning
# Size matters in an app bundle. A key goes when the curve without it stays within a hair of the curve with it at every
# frame it spans (a sampled arc, a flat run, a linear run). Colours, gradients and animated paths
# are never touched.
PRUNE_TOL = {'p': 0.35, 'a': 0.35, 's': 0.6, 'r': 0.4, 'o': 1.0, 'e': 0.4, 'w': 0.1}


def _curve_at(ks, f):
    if f <= ks[0]['t']:
        return ks[0]['s']
    for k0, k1 in zip(ks, ks[1:]):
        if k0['t'] <= f < k1['t']:
            return _ease_at(k0, k1, f)
    return ks[-1]['s']


def prune_keys(ks, tol):
    ks = [dict(k) for k in ks]
    changed = True
    while changed and len(ks) > 2:
        changed = False
        n = 1
        while n < len(ks) - 1:
            a, b, c = ks[n - 1], ks[n], ks[n + 1]
            if len(a['s']) != len(b['s']) or len(b['s']) != len(c['s']):
                n += 1
                continue
            trial = ks[:n] + ks[n + 1:]
            a2 = dict(trial[n - 1])
            same = all(abs(x - y) < 1e-6 for x, y in zip(a['s'], c['s']))
            if same:
                a2.pop('o', None); a2.pop('i', None); a2['h'] = 1
            elif a.get('h'):
                n += 1
                continue
            trial[n - 1] = a2
            ok = True
            f = a['t']
            while f < c['t']:
                v0, v1 = _curve_at(ks, f), _curve_at(trial, f)
                if any(abs(x - y) > tol for x, y in zip(v0, v1)):
                    ok = False
                    break
                f += 1
            if ok:
                ks = trial
                changed = True
            else:
                n += 1
    return ks


def prune(doc):
    """Prune every animated scalar or vector property in the document, in place."""
    def walk(x):
        if isinstance(x, dict):
            for key, v in list(x.items()):
                if (key in PRUNE_TOL and isinstance(v, dict) and v.get('a') == 1 and isinstance(v.get('k'), list)
                        and v['k'] and isinstance(v['k'][0], dict) and isinstance(v['k'][0].get('s'), list)
                        and all(isinstance(e, (int, float)) for e in v['k'][0]['s'])):
                    v['k'] = prune_keys(v['k'], PRUNE_TOL[key])
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(doc['layers'])
    return doc




# ----------------------------------------------------------------------------- output
def write(comp, out_dir, name=None, prune_keys_=True):
    """Validate, prune keys, round, and write <out_dir>/<name>.json. Returns the file path.
    Prints one line with frames, seconds, size and layer count, plus any problem found."""
    doc = comp.json()
    problems = validate(doc)
    if prune_keys_:
        doc = prune(doc)
    doc = compact(doc)
    text = json.dumps(doc, separators=(',', ':'))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f'{name or comp.name}.json')
    with open(path, 'w') as f:
        f.write(text)
    print(f'{comp.name:18s} {doc["op"]:4d} frames  {doc["op"] / FPS:4.2f} s  {len(text) / 1024:5.1f} KB  '
          f'{len(doc["layers"]):2d} layers')
    for p in problems:
        print('   !', p)
    for p in tiny_visible(doc):
        print('   ~ speck:', p)
    STYLE['ink'] = 1.0
    if problems:
        raise SystemExit(f'{comp.name}: {len(problems)} problem(s)')
    return path
