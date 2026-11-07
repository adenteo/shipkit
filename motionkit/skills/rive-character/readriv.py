#!/usr/bin/env python3
"""Read an exported .riv and print what is in it, including the rig.

    python3 readriv.py ~/Downloads/foo.riv
    python3 readriv.py foo.riv --tree     # parent/child, names only

Question it answers: can you see how a rig was built, in an exported file?

It IS visible. A `.riv` is not a compiled blob, it is a property stream, and it
keeps every object, every property and every name. What it does NOT keep is the
editor's own scaffolding: folder structure, selection, the artboard's layout in
the editor window, and anything marked editor-only. The RIG is not editor-only,
because the runtime needs it to pose the character, so the bones, their
lengths, their rotations, the skins, every tendon's bind matrix and every
vertex weight are all there.

THE FORMAT
  magic "RIVE", then major, minor and file id as varuints.
  Then a TABLE OF CONTENTS: the property keys this file uses, as varuints,
  terminated by a 0, followed by a bitmap of TWO BITS per key saying how to
  read that property's value.
  Then the objects, back to back: a varuint typeKey, then (key, value) pairs
  until a key of 0 ends the object.

The two-bit codes are the whole trick, and they are why a reader does not need
to know what every property means: 0 is a varuint, 1 is a string, 2 is a
float32, 3 is a colour. Anything this file does not name in its ToC is a
property it does not use.
"""
from __future__ import annotations
import json, struct, sys, os

SCHEMA = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "schema.json")))
TYPE = {int(k): v for k, v in SCHEMA["types"].items()}
PROP = {int(k): v for k, v in SCHEMA["props"].items()}

# How a value is stored, from its declared type. The ToC only lists the keys a
# runtime might NOT know, which on this file is four of them; everything else
# comes from the built-in table, and that table is what `rive schema` knows.
# Dumped once from all 353 core types into `schema.json`.
STORE = {"double": "f32", "Color": "color", "String": "str", "Bytes": "bytes",
         "callback": "skip"}
class R:
    def __init__(self, b): self.b, self.i = b, 0
    def byte(self):
        v = self.b[self.i]; self.i += 1; return v
    def varuint(self):
        r, s = 0, 0
        while True:
            c = self.byte()
            r |= (c & 0x7F) << s
            if not c & 0x80: return r
            s += 7
    def f32(self):
        v = struct.unpack_from("<f", self.b, self.i)[0]; self.i += 4; return v
    def color(self):
        v = struct.unpack_from("<I", self.b, self.i)[0]; self.i += 4; return v
    def string(self):
        n = self.varuint()
        s = self.b[self.i:self.i + n].decode("utf-8", "replace"); self.i += n
        return s
    def bytes_(self):
        n = self.varuint(); v = self.b[self.i:self.i + n]; self.i += n; return v


def read(path):
    r = R(open(path, "rb").read())
    assert r.b[:4] == b"RIVE", "not a .riv"
    r.i = 4
    major, minor, fid = r.varuint(), r.varuint(), r.varuint()
    keys = []
    while True:
        k = r.varuint()
        if k == 0:
            break
        keys.append(k)
    # The bitmap is FOUR keys per 32-bit word, two bits each in the LOW byte;
    # the other three bytes of every word are padding. This is exactly what
    # rive-runtime's RuntimeHeader::read does (currentBit 0,2,4,6 then a
    # fresh readUint32). A file with 4 keys costs 4 bytes, 24 keys cost 24.
    # Reading 16 keys per word works only on files with <=4 ToC keys and
    # desyncs the object stream on everything else.
    bits = []
    for i in range(len(keys)):
        if i % 4 == 0:
            word = struct.unpack_from("<I", r.b, r.i)[0]; r.i += 4
        bits.append((word >> (2 * (i % 4))) & 3)
    toc = dict(zip(keys, bits))

    def value(k):
        if k in toc:                      # the file told us
            c = toc[k]
            return (r.varuint() if c == 0 else r.string() if c == 1
                    else r.f32() if c == 2 else r.color())
        t = PROP.get(k, {}).get("type", "uint")
        how = STORE.get(t, "uint")
        return (r.f32() if how == "f32" else r.color() if how == "color"
                else r.string() if how == "str" else r.bytes_() if how == "bytes"
                else r.varuint())

    objs = []
    while r.i < len(r.b):
        t = r.varuint()
        o = {"_type": TYPE.get(t, f"type{t}"), "_typeKey": t}
        while True:
            k = r.varuint()
            if k == 0:
                break
            o[PROP.get(k, {}).get("name", f"p{k}")] = value(k)
        objs.append(o)
    return {"version": f"{major}.{minor}", "id": fid, "objects": objs}


def main(path, tree=False):
    d = read(path)
    print(f"{os.path.basename(path)}  format {d['version']}  "
          f"{len(d['objects'])} objects\n")
    from collections import Counter
    c = Counter(o["_type"] for o in d["objects"])
    print("what is in it:")
    for k, n in c.most_common():
        print(f"   {n:5d}  {k}")
    print("\nthe rig:")
    for o in d["objects"]:
        if o["_type"] in ("RootBone", "Bone"):
            print(f"   {o['_type']:8s} {o.get('name',''):18s} "
                  f"length {o.get('length',0):7.2f}  "
                  f"rotation {o.get('rotation',0):8.4f}  "
                  f"x {o.get('x',0):7.1f} y {o.get('y',0):7.1f}")
        elif o["_type"] == "IKConstraint":
            print(f"   IK       parentBoneCount={o.get('parentBoneCount')} "
                  f"strength={o.get('strength')} target={o.get('p173')}")
    tend = [o for o in d["objects"] if o["_type"] == "Tendon"]
    print(f"\n{len(tend)} tendons (a skin's bind pose, one per bone it uses):")
    for o in tend[:6]:
        print(f"   bone {o.get('boneId')}  tx {o.get('tx',0):7.2f} "
              f"ty {o.get('ty',0):7.2f}  "
              f"xx {o.get('xx',1):.3f} xy {o.get('xy',0):.3f} "
              f"yx {o.get('yx',0):.3f} yy {o.get('yy',1):.3f}")
    w = [o for o in d["objects"] if o["_type"] in ("Weight", "CubicWeight")]
    print(f"\n{len(w)} vertex weights. First few, decoded:")
    for o in w[:6]:
        vals, idx = int(o.get("values", 0)), int(o.get("indices", 0))
        inf = [(( idx >> (8*i)) & 255, (vals >> (8*i)) & 255) for i in range(4)]
        inf = [f"tendon {t-1}: {v/255:.0%}" for t, v in inf if t]
        print("   " + ", ".join(inf))


if __name__ == "__main__":
    main(sys.argv[1], "--tree" in sys.argv)
