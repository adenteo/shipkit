"""rive_keys: helpers for editing an existing RML scene with scripts, and for writing motion.

Not an edit script itself: your `*_edit.py` scripts import it. Everything here writes RML text;
nothing parses the scene beyond the regexes each script asserts on.

Keys are written as (frame, value, ease). Eases are CSS-style cubic beziers on time
(`CubicEaseInterpolator`), so the value stays between its two keys, except the overshooting ones
(`back`, `pop`), whose y runs past 1 and so the value runs past the next key and settles into it,
which is the point.

    import sys; sys.path.insert(0, '<skill>/scripts')
    from rive_keys import *
    ids = Ids(scene_text, 1300000)      # fresh ids from 1300001, asserted unused (so the script runs once)
"""
from __future__ import annotations
import math, re

X, Y, ROT, SX, SY, OP = 13, 14, 15, 16, 17, 18
BONE_Y = 91
CALLBACK = 395   # Event.trigger: a keyed Rive event the app hears

EASES = {
    "io":    (0.42, 0.0, 0.58, 1.0),    # ease in-out: leaves and arrives softly
    "sine":  (0.37, 0.0, 0.63, 1.0),    # a swing between two extremes
    "out":   (0.16, 1.0, 0.30, 1.0),    # fast start, long soft arrival
    "soft":  (0.30, 0.0, 0.20, 1.0),    # ease out with a gentle start
    "in":    (0.55, 0.0, 0.85, 0.35),   # gathering speed (a fall, a wind up)
    "back":  (0.34, 1.45, 0.64, 1.0),   # overshoot the key a little, settle
    "pop":   (0.25, 1.8, 0.45, 1.0),    # a bigger overshoot (a spring popping)
    "up":    (1 / 3, 2 / 3, 2 / 3, 1.0),  # the rising half of a parabola
    "down":  (1 / 3, 0.0, 2 / 3, 1 / 3),  # the falling half
}


class Ids:
    """Fresh ids from `start`, asserted unused in the scene."""

    def __init__(self, scene: str, start: int):
        self.n = start
        assert f'id="0:{start + 1}"' not in scene, f"ids from {start} already used (already applied?)"

    def __call__(self) -> str:
        self.n += 1
        return f"0:{self.n}"


def keyframe(ids: Ids, frame: int, value: float, ease: str) -> str:
    if ease == "hold":
        return f'<KeyFrameDouble id="{ids()}" frame="{frame}" value="{value:.5f}" interpolationType="hold" />'
    if ease == "lin":
        return f'<KeyFrameDouble id="{ids()}" frame="{frame}" value="{value:.5f}" interpolationType="linear" />'
    x1, y1, x2, y2 = EASES[ease]
    return (f'<KeyFrameDouble id="{ids()}" frame="{frame}" value="{value:.5f}" interpolationType="cubic">'
            f'<CubicEaseInterpolator id="{ids()}" x1="{x1:.4f}" y1="{y1:.4f}" x2="{x2:.4f}" y2="{y2:.4f}" />'
            f'</KeyFrameDouble>')


def track_xml(ids: Ids, prop: int, keys) -> str:
    keys = sorted(keys, key=lambda k: k[0])
    if prop == CALLBACK:
        body = "".join(f'<KeyFrameCallback id="{ids()}" frame="{k[0]}" />' for k in keys)
    else:
        body = "".join(keyframe(ids, k[0], k[1], k[2] if len(k) > 2 else "io") for k in keys)
    return f'<KeyedProperty id="{ids()}" propertyKey="{prop}">{body}</KeyedProperty>'


def animation_xml(ids: Ids, name: str, duration: int, tracks: dict, loop: str = "oneShot") -> tuple[str, str]:
    """(animation id, xml). `tracks` maps object id -> {property key: keys}."""
    aid = ids()
    objs = "".join(
        f'<KeyedObject id="{ids()}" objectId="{oid}">' + "".join(track_xml(ids, p, k) for p, k in props.items()) + "</KeyedObject>"
        for oid, props in tracks.items() if props)
    return aid, (f'        <LinearAnimation id="{aid}" name="{name}" duration="{duration}" fps="60" loopValue="{loop}">'
                 f"{objs}</LinearAnimation>\n")


def trigger_condition(ids: Ids, vm: str, prop: str) -> str:
    return (f'<TransitionViewModelCondition id="{ids()}" opValue="notEqual"><TransitionPropertyViewModelComparator id="{ids()}">'
            f'<BindablePropertyTrigger id="{ids()}"><DataBindContext id="{ids()}" sourcePathIds="{vm}-{prop}" propertyKey="686" />'
            f'</BindablePropertyTrigger></TransitionPropertyViewModelComparator><TransitionValueTriggerComparator id="{ids()}" />'
            f'</TransitionViewModelCondition>')


def number_condition(ids: Ids, vm: str, prop: str, op: str, value: float) -> str:
    return (f'<TransitionViewModelCondition id="{ids()}" opValue="{op}"><TransitionPropertyViewModelComparator id="{ids()}">'
            f'<BindablePropertyNumber id="{ids()}"><DataBindContext id="{ids()}" sourcePathIds="{vm}-{prop}" propertyKey="636" />'
            f'</BindablePropertyNumber></TransitionPropertyViewModelComparator><TransitionValueNumberComparator id="{ids()}" value="{value}" />'
            f'</TransitionViewModelCondition>')


def add_vm_properties(s: str, vm_id: str, anchor: str, props: list[tuple[str, str, str]], ids: Ids) -> tuple[str, dict]:
    """Adds (name, kind, default) properties to a view model and a value to every instance.
    kind is Number, Trigger or Boolean. Returns the scene and {name: property id}."""
    vm = re.search(rf'<ViewModel defaultInstanceId="[^"]+" name="[^"]+" id="{vm_id}">[\s\S]*?</ViewModel>', s)
    assert vm, vm_id
    block = vm.group(0)
    assert block.count(anchor) == 1, anchor
    out = {}
    decl = ""
    for name, kind, _ in props:
        assert f'name="{name}"' not in block, f"{name} already on the view model"
        out[name] = ids()
        decl += f'\n        <ViewModelProperty{kind} id="{out[name]}" name="{name}" />'
    block = block.replace(anchor, anchor + decl)
    n_inst = block.count("</ViewModelInstance>")

    def values(m):
        ind = m.group(1)
        v = ""
        for name, kind, default in props:
            if kind == "Trigger":
                v += f'{ind}    <ViewModelInstanceTrigger id="{ids()}" viewModelPropertyId="{out[name]}" />'
            elif kind == "Boolean":
                v += f'{ind}    <ViewModelInstanceBoolean id="{ids()}" viewModelPropertyId="{out[name]}" propertyValue="{default}" />'
            else:
                v += f'{ind}    <ViewModelInstanceNumber id="{ids()}" viewModelPropertyId="{out[name]}" propertyValue="{default}" />'
        return v + f"{ind}</ViewModelInstance>"

    block = re.sub(r"(\s*)</ViewModelInstance>", values, block)
    for name in out:
        assert block.count(f'viewModelPropertyId="{out[name]}"') == n_inst, name
    return s.replace(vm.group(0), block), out


def artboard_span(s: str, artboard_id: str) -> tuple[int, int]:
    a = s.index(f'id="{artboard_id}"')
    a = s.rindex("<Artboard", 0, a)
    b = s.index("</Artboard>", a)
    return a, b


def insert_animations(s: str, artboard_id: str, xml: str) -> str:
    """Appends animations at the end of an artboard (after its last child)."""
    a, b = artboard_span(s, artboard_id)
    end = s.rindex("\n", a, b)
    return s[:end] + "\n" + xml.rstrip("\n") + s[end:]


# ------------------------------------------------------------- baked curves
def parse_track(body: str):
    """[(frame, value, interpolation)] of one KeyedProperty's KeyFrameDoubles, or None."""
    out = []
    for kf in re.finditer(r"<KeyFrameDouble\b[^>]*?(?:/>|>[\s\S]*?</KeyFrameDouble>)", body):
        t = kf.group(0)
        f = re.search(r'\bframe="(\d+)"', t)
        v = re.search(r'\bvalue="([-\d.eE+]+)"', t)
        it = re.search(r'interpolationType="(\w+)"', t)
        if not v:
            return None
        out.append((int(f.group(1)) if f else 0, float(v.group(1)), it.group(1) if it else "hold"))
    return sorted(out) or None


def sample(keys, duration: int):
    """Value at every frame 0..duration, linear between the (dense, baked) keys."""
    out = []
    j = 0
    for f in range(duration + 1):
        while j + 1 < len(keys) and keys[j + 1][0] <= f:
            j += 1
        f0, v0, it = keys[j]
        if j + 1 < len(keys) and f > f0 and it != "hold":
            f1, v1, _ = keys[j + 1]
            q = (f - f0) / (f1 - f0)
            out.append(v0 + (v1 - v0) * q)
        else:
            out.append(v0)
    return out


def spring(values, freq: float, damping: float, fps: float = 60.0, settle_to=None):
    """A damped spring chasing `values` frame by frame: follow-through (a lag and an
    overshoot past every stop, settling). The last eighth of a second eases the
    result onto the target so the clip still ends where it was authored to."""
    w = 2 * math.pi * freq
    dt = 1 / fps
    x, v = values[0], 0.0
    out = []
    for target in values:
        for _ in range(4):   # substeps for stability
            a = w * w * (target - x) - 2 * damping * w * v
            v += a * dt / 4
            x += v * dt / 4
        out.append(x)
    end = values[-1] if settle_to is None else settle_to
    n = min(8, len(out))
    for i in range(n):
        q = (i + 1) / n
        k = len(out) - n + i
        out[k] = out[k] * (1 - q) + end * q
    return out


def fit_hermite(values, tol: float):
    """Key frames for a cubic Hermite through `values`: the turning points (where
    the motion stops or reverses) plus whatever the error asks for. Returns
    [(frame, value, velocity per frame)]."""
    n = len(values)
    if n < 3:
        return [(i, values[i], 0.0) for i in range(n)]
    vel = [0.0] * n
    for i in range(1, n - 1):
        vel[i] = (values[i + 1] - values[i - 1]) / 2
    keys = {0, n - 1}
    eps = (max(values) - min(values)) * 1e-3 + 1e-9
    for i in range(1, n - 1):
        d0 = values[i] - values[i - 1]
        d1 = values[i + 1] - values[i]
        if (d0 > eps and d1 < -eps) or (d0 < -eps and d1 > eps):
            keys.add(i)
        if (abs(d0) <= eps) != (abs(d1) <= eps):   # into or out of a plateau
            keys.add(i)
    def at_key(i):
        # extremes and plateau edges have zero speed, others keep theirs
        d0 = values[i] - values[i - 1] if i > 0 else 0
        d1 = values[i + 1] - values[i] if i < n - 1 else 0
        return 0.0 if (d0 * d1 <= 0 or abs(d0) <= eps or abs(d1) <= eps) else vel[i]
    while True:
        ks = sorted(keys)
        worst, at = 0.0, None
        for a, b in zip(ks, ks[1:]):
            T = b - a
            va, vb = at_key(a) * T, at_key(b) * T
            pa, pb = values[a], values[b]
            for f in range(a + 1, b):
                t = (f - a) / T
                h = ((2 * t ** 3 - 3 * t ** 2 + 1) * pa + (t ** 3 - 2 * t ** 2 + t) * va
                     + (-2 * t ** 3 + 3 * t ** 2) * pb + (t ** 3 - t ** 2) * vb)
                e = abs(h - values[f])
                if e > worst:
                    worst, at = e, f
        if worst <= tol or at is None or len(keys) > n // 2:
            break
        keys.add(at)
    return [(i, values[i], at_key(i)) for i in sorted(keys)]


def hermite_track_body(ids: Ids, keys) -> str:
    """KeyFrameDoubles for fit_hermite's keys: cubicValue, handles at thirds, so each
    segment IS the Hermite cubic (smooth speed through a key, zero at a stop)."""
    out = []
    for j, (f, v, vel) in enumerate(keys):
        if j == len(keys) - 1:
            out.append(f'<KeyFrameDouble id="{ids()}" frame="{f}" value="{v:.6f}" interpolationType="linear" />')
            continue
        f1, v1, vel1 = keys[j + 1]
        T = f1 - f
        y1 = v + vel * T / 3
        y2 = v1 - vel1 * T / 3
        out.append(f'<KeyFrameDouble id="{ids()}" frame="{f}" value="{v:.6f}" interpolationType="cubicValue">'
                   f'<CubicValueInterpolator id="{ids()}" x1="0.3333" y1="{y1:.6f}" x2="0.6667" y2="{y2:.6f}" />'
                   f'</KeyFrameDouble>')
    return "".join(out)


def element_end(s: str, start: int) -> int:
    """Index just past the closing tag of the element whose start tag begins at `start`
    (nesting of the same tag counted; self-closing tags skipped)."""
    tag = re.match(r"<(\w+)", s[start:]).group(1)
    depth = 0
    for m in re.finditer(rf"<(/?){tag}\b[^>]*?(/?)>", s[start:]):
        if m.group(1):
            depth -= 1
        elif not m.group(2):
            depth += 1
        if depth == 0:
            return start + m.end()
    raise AssertionError(f"unclosed {tag} at {start}")


def interpolator_converter(ids: Ids, name: str, seconds: float, ease: str = "soft") -> tuple[str, str]:
    cid = ids()
    x1, y1, x2, y2 = EASES[ease]
    return cid, (f'\n    <DataConverterInterpolator id="{cid}" name="{name}" interpolationType="cubic" duration="{seconds}">'
                 f'<CubicEaseInterpolator id="{ids()}" x1="{x1:.4f}" y1="{y1:.4f}" x2="{x2:.4f}" y2="{y2:.4f}" />'
                 f'</DataConverterInterpolator>')


def mapper_converter(ids: Ids, name: str, in0, in1, out0, out1) -> tuple[str, str]:
    cid = ids()
    return cid, (f'\n    <DataConverterRangeMapper id="{cid}" name="{name}" minInput="{in0}" maxInput="{in1}" '
                 f'minOutput="{out0}" maxOutput="{out1}" />')


def group_converter(ids: Ids, name: str, members: list[str]) -> tuple[str, str]:
    cid = ids()
    return cid, (f'\n    <DataConverterGroup id="{cid}" name="{name}">'
                 + "".join(f'<DataConverterGroupItem id="{ids()}" converterId="{m}" />' for m in members)
                 + "</DataConverterGroup>")
