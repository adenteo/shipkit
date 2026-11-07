"""uilib: RML helpers for small generated Rive pieces (buttons, toggles, tab icons, loaders).

A generator script (gen.py) builds a scene.rml as text with these helpers, so re-running it
rebuilds the piece exactly. RML paints the FIRST declared child on top, so every helper returns
pieces in top-to-bottom order and callers list the front first.

Pieces are artboards with a state machine whose steady states are ONE-FRAME one-shot animations,
so the machine settles and the runtime stops drawing at rest. The app wakes it by setting an
input.

    import sys; sys.path.insert(0, '<skill>/scripts')
    from uilib import *
"""
from __future__ import annotations
import math, os, shutil, subprocess

RIVE = shutil.which('rive') or os.path.expanduser('~/.rive/bin/rive')

_id = [100]


def nid():
    _id[0] += 1
    return f"0:{_id[0]}"


# ---------------------------------------------------------------- palette (ARGB hex)
# Neutral defaults. A project sets its own constants (or passes colours explicitly).
INK = 'FF1F2430'          # outline colour
PRIMARY = 'FF4F7CFF'
PRIMARY_SHADE = 'FF3A62E0'
PRIMARY_LIGHT = 'FF9DB6FF'
ACCENT = 'FFFFC857'
ACCENT_SHADE = 'FFF0A92E'
SURFACE = 'FFFFFFFF'
SURFACE_SHADE = 'FFE6E9F0'
TRACK_OFF = 'FFD9DDE6'
WHITE = 'FFFFFFFF'


def argb(c):
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), int(c[6:8], 16)


def hexc(a, r, g, b):
    return f'{round(a):02X}{round(r):02X}{round(g):02X}{round(b):02X}'


def muted(c, sat=0.35, over=(0xF4, 0xF8, 0xFA), keep=0.7):
    """The inactive tab's colour: saturation down to `sat`, then `keep` of it over the bar."""
    a, r, g, b = argb(c)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    r, g, b = (lum + sat * (v - lum) for v in (r, g, b))
    r, g, b = (keep * v + (1 - keep) * o for v, o in zip((r, g, b), over))
    return hexc(a, r, g, b)


# ---------------------------------------------------------------- paths
def ellipse(w, h):
    return f'<Ellipse width="{w:.2f}" height="{h:.2f}" name="Path"/>'


def rect(w, h, r=0, ox=0.5, oy=0.5, rs=None):
    """A rounded rectangle; `rs` = (tl, tr, br, bl) for unlinked corners."""
    if rs:
        tl, tr, br, bl = rs
        return (f'<Rectangle width="{w:.2f}" height="{h:.2f}" linkCornerRadius="false" cornerRadiusTL="{tl:.2f}" '
                f'cornerRadiusTR="{tr:.2f}" cornerRadiusBR="{br:.2f}" cornerRadiusBL="{bl:.2f}" '
                f'originX="{ox}" originY="{oy}" name="Path"/>')
    return (f'<Rectangle width="{w:.2f}" height="{h:.2f}" cornerRadiusTL="{r:.2f}" originX="{ox}" originY="{oy}" '
            f'name="Path"/>')


def poly(pts, closed=True, radius=0.0):
    """Straight vertices, each optionally rounded; pts = [(x, y) or (x, y, r)]."""
    vs = ''.join(f'<StraightVertex x="{p[0]:.2f}" y="{p[1]:.2f}" radius="{(p[2] if len(p) > 2 else radius):.2f}"/>' for p in pts)
    return f'<PointsPath isClosed="{"true" if closed else "false"}" name="Path">{vs}</PointsPath>'


def cubic_path(segs, closed=True):
    """segs: [(point, in_handle, out_handle)] in absolute coordinates."""
    out = []
    for p, i_, o_ in segs:
        ir = math.atan2(i_[1] - p[1], i_[0] - p[0]); idist = math.dist(i_, p)
        orr = math.atan2(o_[1] - p[1], o_[0] - p[0]); odist = math.dist(o_, p)
        out.append(f'<CubicDetachedVertex x="{p[0]:.2f}" y="{p[1]:.2f}" inRotation="{ir:.4f}" inDistance="{idist:.2f}" '
                   f'outRotation="{orr:.4f}" outDistance="{odist:.2f}"/>')
    return f'<PointsPath isClosed="{"true" if closed else "false"}" name="Path">{"".join(out)}</PointsPath>'


# A plump heart in a 96 x 84 box: two round lobes meeting in a cusp, sides curving into the point.
# Cubic segments (c1, c2, end) from START, clockwise on screen.
HEART_START = (50.0, 27.0)
HEART = [
    ((53.0, 14.0), (62.0, 8.0), (73.0, 8.0)),
    ((88.0, 8.0), (98.0, 19.0), (98.0, 34.0)),
    ((98.0, 58.0), (70.0, 76.0), (50.0, 92.0)),
    ((30.0, 76.0), (2.0, 58.0), (2.0, 34.0)),
    ((2.0, 19.0), (12.0, 8.0), (27.0, 8.0)),
    ((38.0, 8.0), (47.0, 14.0), (50.0, 27.0)),
]
HEART_W, HEART_CENTRE = 96.0, (50.0, 50.0)


def heart_path(w, cx=0.0, cy=0.0):
    k = w / HEART_W
    T = lambda p: (cx + (p[0] - HEART_CENTRE[0]) * k, cy + (p[1] - HEART_CENTRE[1]) * k)
    pts = [T(HEART_START)] + [T(s[2]) for s in HEART[:-1]]
    outs = [T(s[0]) for s in HEART]
    ins = [T(HEART[-1][1])] + [T(s[1]) for s in HEART[:-1]]
    return cubic_path(list(zip(pts, ins, outs)))


def arc_path(w, h, up=True):
    """An open arc, ends at (+-w/2, 0), bulging up (a happy closed eye) or down (asleep)."""
    r = -math.pi / 2 if up else math.pi / 2
    d = abs(h) * 1.33
    return (f'<PointsPath isClosed="false" name="Path">'
            f'<CubicDetachedVertex x="{-w/2:.2f}" y="0" inRotation="{r:.4f}" inDistance="0" outRotation="{r:.4f}" outDistance="{d:.2f}"/>'
            f'<CubicDetachedVertex x="{w/2:.2f}" y="0" inRotation="{r:.4f}" inDistance="{d:.2f}" outRotation="{r:.4f}" outDistance="0"/>'
            f'</PointsPath>')


def sparkle_path(r, k=0.28):
    """A four-pointed sparkle of radius r."""
    pts = []
    for i in range(8):
        a = -math.pi / 2 + i * math.pi / 4
        rr = r if i % 2 == 0 else r * k
        pts.append((rr * math.cos(a), rr * math.sin(a), 0.6 if i % 2 == 0 else r * 0.12))
    return poly(pts)


# ---------------------------------------------------------------- paints
def solid(c, cid=None):
    idattr = f' id="{cid}"' if cid else ''
    return f'<SolidColor colorValue="{c}" name="C"{idattr}/>'


def fill(c, cid=None):
    return f'<Fill name="Fill">{solid(c, cid)}</Fill>'


def stroke(c, w, cid=None, sid=None, cap='round'):
    s = f' id="{sid}"' if sid else ''
    return f'<Stroke thickness="{w:.2f}" cap="{cap}" join="round" name="Line"{s}>{solid(c, cid)}</Stroke>'


def shape(name, x, y, body, paints, sid=None, rot=0, opacity=None, clip=None, sx=None, sy=None):
    sid = sid or nid()
    extra = ''
    if rot: extra += f' rotation="{rot:.4f}"'
    if opacity is not None: extra += f' opacity="{opacity}"'
    if sx is not None: extra += f' scaleX="{sx}"'
    if sy is not None: extra += f' scaleY="{sy}"'
    c = f'<ClippingShape name="Clip" sourceId="{clip}" id="{nid()}"/>' if clip else ''
    return f'<Shape x="{x:.2f}" y="{y:.2f}"{extra} name="{name}" id="{sid}">{body}{paints}{c}</Shape>'


def node(name, x, y, children, nid_=None, rot=0, opacity=None, sx=None, sy=None):
    nid_ = nid_ or nid()
    extra = ''
    if rot: extra += f' rotation="{rot:.4f}"'
    if opacity is not None: extra += f' opacity="{opacity}"'
    if sx is not None: extra += f' scaleX="{sx}"'
    if sy is not None: extra += f' scaleY="{sy}"'
    return f'<Node x="{x:.2f}" y="{y:.2f}"{extra} name="{name}" id="{nid_}">' + ''.join(children) + '</Node>'


class Colors:
    """Every SolidColor that should follow a palette swap (the tab icons' muted / full)."""

    def __init__(self):
        self.ids = {}        # id -> full colour

    def __call__(self, c):
        cid = nid()
        self.ids[cid] = c
        return cid


def cel(name, body_fn, base, shade, line=INK, lw=3.0, dx=-0.06, dy=-0.07, w=1.0, colors=None, sid=None):
    """A flat cel shape: the base fills `shade`, a copy nudged up-left fills `base` over it
    (clipped to the base), so a crescent of shade is left on the lower right; ink on top.
    body_fn(scale) returns the path for a scale of the shape (1 = full). Returns front-first."""
    base_id = sid or nid()
    col = colors or (lambda c: None)
    out = [shape(f'{name} line', 0, 0, body_fn(1.0), stroke(line, lw, col(line))),
           shape(f'{name} face', dx * w, dy * w, body_fn(1.0), fill(base, col(base)), clip=base_id),
           shape(f'{name} base', 0, 0, body_fn(1.0), fill(shade, col(shade)), sid=base_id)]
    return out


# ---------------------------------------------------------------- keys
X, Y, ROT, SX, SY, OP = 13, 14, 15, 16, 17, 18
COLOR = 37
THICK = 47
WIDTH, HEIGHT = 20, 21
CALLBACK = 395
CURVES = {'io': (0.42, 0, 0.58, 1), 'out': (0.2, 0.9, 0.35, 1), 'in': (0.55, 0, 0.85, 0.35),
          'soft': (0.3, 0, 0.3, 1), 'back': (0.3, 1.6, 0.5, 1), 'up': (1 / 3, 2 / 3, 2 / 3, 1),
          'down': (1 / 3, 0, 2 / 3, 1 / 3)}


class Anim:
    """A LinearAnimation. key(oid, prop, [(frame, value[, ease])]); ease names CURVES, 'lin'
    or 'hold'; the ease of a key shapes the segment that LEAVES it."""

    def __init__(self, name, dur, loop='oneShot', fps=60):
        self.name, self.dur, self.loop, self.fps, self.id = name, dur, loop, fps, nid()
        self.objs = {}

    def key(self, oid, prop, frames, ease='io'):
        self.objs.setdefault(oid, {})[prop] = [(f[0], f[1], f[2] if len(f) > 2 else ease) for f in frames]
        return self

    def hold(self, oid, prop, v):
        return self.key(oid, prop, [(0, v, 'hold')])

    def event(self, eid, frames):
        self.objs.setdefault(eid, {})[CALLBACK] = [(f, 0, 'lin') for f in frames]
        return self

    def xml(self):
        out = [f'<LinearAnimation loopValue="{self.loop}" fps="{self.fps}" duration="{self.dur}" name="{self.name}" id="{self.id}">']
        for oid, props in self.objs.items():
            out.append(f'<KeyedObject objectId="{oid}">')
            for prop, frames in props.items():
                out.append(f'<KeyedProperty propertyKey="{prop}">')
                frames = sorted(frames, key=lambda k: k[0])
                for n, (f, v, e) in enumerate(frames):
                    last = n == len(frames) - 1
                    if prop == CALLBACK:
                        out.append(f'<KeyFrameCallback frame="{f}"/>')
                        continue
                    tag = 'KeyFrameColor' if prop == COLOR else 'KeyFrameDouble'
                    val = v if prop == COLOR else f'{v:.4f}'
                    if e == 'hold' and not last:
                        out.append(f'<{tag} value="{val}" frame="{f}" interpolationType="hold"/>')
                    elif last or e == 'lin':
                        out.append(f'<{tag} value="{val}" frame="{f}" interpolationType="linear"/>')
                    else:
                        x1, y1, x2, y2 = CURVES[e]
                        out.append(f'<{tag} value="{val}" frame="{f}" interpolationType="cubic">'
                                   f'<CubicEaseInterpolator x1="{x1:.4f}" y1="{y1:.4f}" x2="{x2:.4f}" y2="{y2:.4f}"/></{tag}>')
                out.append('</KeyedProperty>')
            out.append('</KeyedObject>')
        out.append('</LinearAnimation>')
        return ''.join(out)


# ---------------------------------------------------------------- state machines
class Machine:
    """A state machine with legacy inputs (bools, numbers, triggers), several layers.

        m = Machine('Tab'); sel = m.bool('selected'); tap = m.trigger('tap')
        L = m.layer('Select'); off = L.state(anim_off); on = L.state(anim_on)
        L.entry(off)
        L.go(off, on, cond=[('bool', sel, True)], ms=0)
        L.go(on, off, exit=100)
    """

    def __init__(self, name):
        self.name, self.id = name, nid()
        self.inputs, self.layers = [], []

    def bool(self, name, v=False):
        i = nid(); self.inputs.append(f'<StateMachineBool name="{name}" value="{str(v).lower()}" id="{i}"/>'); return i

    def number(self, name, v=0):
        i = nid(); self.inputs.append(f'<StateMachineNumber name="{name}" value="{v}" id="{i}"/>'); return i

    def trigger(self, name):
        i = nid(); self.inputs.append(f'<StateMachineTrigger name="{name}" id="{i}"/>'); return i

    def layer(self, name):
        L = Layer(name, len(self.layers)); self.layers.append(L); return L

    def xml(self):
        return (f'<StateMachine name="{self.name}" id="{self.id}">' + ''.join(self.inputs)
                + ''.join(L.xml() for L in self.layers) + '</StateMachine>')


class Layer:
    def __init__(self, name, n):
        self.name, self.id, self.n = name, nid(), n
        self.states, self.trans, self.entries, self.blends = [], {}, [], []

    def blend(self, input_id, pairs):
        """A 1D blend of one-frame poses driven by a number input: pairs = [(anim, value)].
        Rive mixes a blend's poses ONTO what is already there, so put a layer under this one
        that enters a plain state holding the first pose (a "base" layer), or the result drifts."""
        sid = nid()
        body = ''.join(f'<BlendAnimation1D animationId="{a.id}" value="{v}"/>' for a, v in pairs)
        self.blends.append(f'<BlendState1DInput inputId="{input_id}" x="200" y="{self.n * 200}" id="{sid}">{body}</BlendState1DInput>')
        self.entries.append(self._t(sid))
        return sid

    def state(self, anim):
        sid = nid(); self.states.append((sid, anim)); self.trans[sid] = []; return sid

    @staticmethod
    def _t(to, cond=(), ms=0, exit=None):
        conds = []
        for kind, iid, v in cond:
            if kind == 'bool':
                conds.append(f'<TransitionBoolCondition inputId="{iid}" opValue="{"equal" if v else "notEqual"}"/>')
            elif kind == 'trigger':
                conds.append(f'<TransitionTriggerCondition inputId="{iid}"/>')
            elif kind == 'number':
                op, val = v
                conds.append(f'<TransitionNumberCondition inputId="{iid}" opValue="{op}" value="{val}"/>')
        attrs = f' duration="{ms}"' if ms else ''
        if exit is not None:
            attrs += f' enableExitTime="true" exitTimeIsPercetange="true" exitTime="{exit}"'
        return f'<StateTransition stateToId="{to}"{attrs}>' + ''.join(conds) + '</StateTransition>'

    def entry(self, to, cond=()):
        self.entries.append(self._t(to, cond))

    def go(self, frm, to, cond=(), ms=0, exit=None):
        self.trans[frm].append(self._t(to, cond, ms, exit))

    def xml(self):
        y = self.n * 200
        out = [f'<StateMachineLayer name="{self.name}" id="{self.id}">',
               f'<AnyState x="400" y="{y - 100}"/><ExitState x="600" y="{y - 100}"/>',
               f'<EntryState x="0" y="{y}">' + ''.join(self.entries) + '</EntryState>']
        for k, (sid, anim) in enumerate(self.states):
            out.append(f'<AnimationState x="{200 + 180 * k}" y="{y}" animationId="{anim.id}" id="{sid}">'
                       + ''.join(self.trans[sid]) + '</AnimationState>')
        out.extend(self.blends)
        out.append('</StateMachineLayer>')
        return ''.join(out)


def events(names):
    """{name: id} and their XML (Events are artboard children)."""
    ev = {n: nid() for n in names}
    return ev, ''.join(f'<Event name="{n}" id="{i}"/>' for n, i in ev.items())


def artboard(name, w, h, x0, children_top_down, machine, anims, extra=''):
    ab = nid()
    return (f'<Artboard defaultStateMachineId="{machine.id}" width="{w}" height="{h}" x="{x0}" y="0" clip="false" '
            f'name="{name}" id="{ab}">' + extra + ''.join(children_top_down) + machine.xml()
            + ''.join(a.xml() for a in anims) + '</Artboard>')


def write(here, artboards):
    doc = '<Rive version="1" kind="fragment">\n' + '\n'.join(artboards) + '\n</Rive>\n'
    open(os.path.join(here, 'scene.rml'), 'w').write(doc)
    return len(doc)


def build(here, name, dest=None):
    """rive . --verify, then --once (the clean unsigned file), optionally copy it to `dest`.
    Returns the size in bytes of build/<name>.riv (the name is rive.yaml's `name`)."""
    r = subprocess.run([RIVE, here, '--verify'], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stdout + r.stderr)
    r = subprocess.run([RIVE, here, '--once'], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stdout + r.stderr)
    src = os.path.join(here, 'build', f'{name}.riv')
    if dest:
        shutil.copy(src, dest)
    return os.path.getsize(src)
