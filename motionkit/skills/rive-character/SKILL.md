---
name: rive-character
description: Rig and animate a 2D character in Rive from a reference drawing or an existing animation. Use when building a character, mascot, avatar or creature rig in Rive (.riv/RML), converting a flipbook or video to a rig, reading how an existing .riv rig was built, or when a Rive character reads stiff. Covers bones, IK, skinning, measuring motion off reference frames, and the gates that catch a bad rig before it ships.
---

# Rigging a character in Rive

Load the `rive` skill too. It owns the CLI workflow, data binding, motion, painted layers, gotchas
and the review bar. This skill is the rigging part.

## The one thing that matters most

**A character is BONES and SKINNED PATHS. It is not a hierarchy of rigid shapes.** Four rigs were
built as parent/child `Node`s with each part a solid shape that translates, rotates and scales.
Every one read stiff, and no amount of retiming fixed it, because a limb that cannot BEND is not a
limb.

The proof is any professional marketplace character. Take one apart (`readriv.py` below) and the
structure is always the same:

    bones           Root, Hips, Chest, Head,
                    Front Shoulder > Front Bicep > Front Forearm > Front Hand,
                    Back Shoulder  > Back Bicep  > Back Forearm  > Back Hand,
                    Back leg > Back leg2 > Back foot,
                    Front leg > Front leg2 > Front foot
    IK targets      Back Leg Control, Back Foot Control, Front Leg Control, Front Foot Control
    skinned shapes  Front_Glove, Front_Arm, Front_Shoulder, Back_Arm, Back_leg, Front_Leg, Body, ...
    clips           Run, Jump          machine  State Machine 1, input Jump

Read that structure closely, because it is the whole lesson:

1. **Every limb is a CHAIN of three or four bones**, not one piece. An arm is shoulder, bicep,
   forearm, hand. A leg is thigh, shin, foot.
2. **The legs are driven by IK with separate CONTROL nodes.** You animate where the foot IS and the
   knee solves itself. That is why a walk looks like a walk.
3. **The drawn shapes are SKINNED to those bones.** Note the naming: bones in `Title Case With
   Spaces` and skinned shapes in `Title_Case_With_Underscores`, a convention worth copying because it
   makes the two readable apart.
4. There is a `No Rig` state, so the rig can be bypassed.

## How to actually do it

### Bones

```xml
<RootBone x="235" y="519" length="120" rotation="-1.57" name="Shoulder" id="0:40">
    <Bone length="90" rotation="0.3" name="Forearm" id="0:41">
        <Bone length="40" rotation="0.1" name="Hand" id="0:42"/>
    </Bone>
</RootBone>
```

`length` positions the next bone; `rotation` is radians relative to the parent.

### Skinning a drawn path to them

A `Skin` nests **inside the thing it deforms** (a `PointsPath` or an image's `Mesh`, nothing else),
holds one `Tendon` per bone, and every vertex carries a `Weight`:

```xml
<PointsPath name="Path">
    <StraightVertex x="0" y="-10"><Weight values="255" indices="1"/></StraightVertex>
    <StraightVertex x="80" y="-10"><Weight values="255" indices="2"/></StraightVertex>
    <Skin tx="0" ty="0" name="Skin">
        <Tendon boneId="0:40" tx="0" ty="0" name="Upper"/>
        <Tendon boneId="0:41" tx="76" ty="0" name="Fore"/>
    </Skin>
</PointsPath>
```

Four traps, each of which fails silently:

- **`indices` is 1-BASED.** Each byte is `tendonIndex + 1`; a `0` slot is the identity and pins the
  vertex where it was bound, which looks exactly like bones not working.
- **`values` must total 255.** Split an even blend 128/127, not 128/128.
- Both are packed a byte per slot, four slots max, slot 0 the low byte. Half and half on tendons 0
  and 1 is `indices="513" values="32640"`.
- **`Tendon`'s matrix is `Mat2D(xx, xy, yx, yy, tx, ty)`**: the x unit is `(xx, xy)`, the y unit is
  `(yx, yy)`. Swapped, the rest pose renders mirrored or collapsed with no error.

`CubicWeight` is the same for cubic vertices, adding `inIndices`/`inValues` and
`outIndices`/`outValues` so the handles deform too.

### IK

```xml
<Bone length="90" name="Forearm" id="0:41">
    <IKConstraint targetId="0:70" parentBoneCount="1" name="Elbow"/>
</Bone>
```

`parentBoneCount="1"` is a two-bone solve, the elbow or knee. `parentBoneCount="0"` is Rive's
**look-at**: the bone aims at the target, which is how a head tracks. **An `IKConstraint` must sit on
a `Bone`**: anywhere else the whole file fails to import and the error names no object.

## Getting the motion right

Do not invent timings. If a reference animation exists, MEASURE it.

1. Decode the clip to frames. Segment each frame into the drawing's own flat colours (a handful of
   nearest-colour classes is enough for flat vector art) and take connected components.
2. Track each feature's centroid, bounding box and area per frame.
3. **Fit the motion, do not assume it.** A hand's path across 97 frames fitted a circle at radius 207
   with a 0.4 px residual, meaning that limb IS a rigid rotation about a findable point, and the point
   is the pivot. Fit first, then you know whether one bone will do or you need a chain.
4. Reduce each measured curve to its TURNING POINTS and key those. Poses at extremes, with the easing
   between doing the work. A key every frame is a sampled function and reads dead
   (`rive` skill, `motion.md`: `fit_hermite`).

**Measure inside a window and you will clip the motion.** A paw's travel was read as 35 px because
the window it was measured in cut off the far end of the swing. It is 202 px. The rig was six times
too small and every retime made it worse, because the amplitude was never the thing being retimed.

## The gates

Without these you will grade on a global impression and ship something obviously wrong.

- **Grade every feature SEPARATELY against the reference.** Silhouette IoU read 0.938 on a face whose
  mouth was at 0.23, because the body is 280,000 pixels and the mouth is 6,000. An average over a
  character is dominated by its largest part and the face is never the largest part. Report IoU,
  centroid shift and size ratio per feature; name anything under 0.80.
- **Grade every FRAME, not just the rest pose.** A rig can be perfect at frame 0 and wrong for the
  other 240.
- **Look at the failing feature at full size**, next to the reference. The numbers say which; the eye
  says why.

## Where the parts come from

If the character has no layered source, the parts have to be drawn, one picture each, with the
reference attached for style. Two rules bought the hard way:

- **A generated part's INTERNAL composition is not controllable by prompt.** Four arms were generated
  and the paw pads landed somewhere different inside the paw every time (1.22, 0.25, 0.18 of the
  reference's area). So: **anything whose position inside a part matters is not a detail of that part,
  it is a part, with its own measured anchor.** Splitting the pads out fixed them in one pass, 0.18 to
  0.921.
- **An anchor box is the union of EVERY colour the part is made of.** Using one colour's box squeezes
  the rest of the part into it.
- Generation earns its keep on parts with real drawn character in them. Forms that are an ellipse or
  a rounded blob should be a Rive `Ellipse` at a measured box, which IS the measurement rather than a
  redrawing of it.

## Draw order, building, review

Rive paints the **first** child declared ON TOP, the reverse of SVG and HTML. Overlap is meaning: a
muzzle drawn OVER a mouth gives a face its scalloped mouth line. Everything general (the CLI
workflow, data binding, eases and springs, events to haptics, painted layers, 3D, silent failures,
the review bar) lives in the `rive` skill.

Rigging lessons from shipping and maintaining a mascot rig as RML text:

- **Edit a shipped rig with asserting scripts**: each asserts its predecessor ran, that it has not
  run, and the count of every substitution, on EVERY copy of a duplicated character
  (`rive` skill, `scripts/rive_keys.py`).
- **New controls go on new parent nodes** nothing keys (touch root, lens fit), so every reaction
  composes with any move.
- **Mirror a move key for key** for the other side: rotations swap sides as negated deltas, other x
  values reflect about their setup values, and eases are copied.
- **Re-key baked motion at turning points and spring the hanging parts**: 26,000 keys to about 8,000,
  a smaller file with more life.
- **Arms**: a raised limb must meet the body at full width with its root buried; clip rectangles must
  sit behind the body; the visible arm must not get longer than the approved one. Sleeves drawn
  hanging do not survive being skinned upward; four automated attempts were reverted, so draw them
  for the raised pose or edit them by hand.
- **Blinks and idle beats belong to the app**, on each character's own clock, not to the rig's Idle.

## Reading somebody else's .riv

**An exported `.riv` keeps the whole rig.** It is not a compiled blob, it is a property stream: every
object, every property, every name. Bones, their lengths and rotations, skins, each tendon's bind
matrix and every vertex weight are all in there, because the runtime needs them to pose the
character. What it drops is editor scaffolding: folders, selection, window layout.

`${CLAUDE_SKILL_DIR}/readriv.py` reads one (`python3 readriv.py foo.riv`, or `--tree` for names
only). The format:

    "RIVE", then major, minor and a file id as varuints.
    A TABLE OF CONTENTS: property keys as varuints, terminated by 0, then a
    bitmap of two bits per key: 0 varuint, 1 string, 2 float32, 3 colour.
    Then objects back to back: a varuint typeKey, then (key, value) pairs
    until a key of 0 ends the object.

Things that each cost an hour:

- **The ToC bitmap is FOUR keys per 32-bit word, in the LOW byte only.** `rive-runtime`'s
  `RuntimeHeader::read` steps `currentBit` 0, 2, 4, 6 then reads a fresh `uint32`; the other three
  bytes of every word are padding. So 4 keys cost 4 bytes, 24 keys cost 24, 88 keys cost 88. Reading
  16 keys per word only works on files with 4 or fewer ToC keys and desyncs every larger file, which
  decodes as a plausible run of small types before dissolving into impossible ones like
  `type53486165`. A run of nonsense typeKeys is always a desync upstream, never a weird file.
- **Marketplace exports usually strip component names.** Bones, shapes, paths and skins come back
  nameless; artboards and animations keep names because runtimes look them up. Topology and geometry
  are all intact. A `.rev` keeps every name, so ask for that when a file's labels matter.
- **The ToC only lists keys the runtime might NOT know**: four of them on a 1,500-object file.
  Everything else comes from a built-in property-type table, and `rive schema <Type> --json --all` is
  that table. `schema.json` beside this file is all 353 core types dumped once: 353 typeKeys and 999
  property keys with their value types.

So a marketplace file can be taken apart and learned from, which is what makes "use a marketplace rig
and replace the art" a real plan rather than a hope. Check the file's licence before reusing its art
or rig.

## Working files

- `readriv.py` and `schema.json` (this folder): the reader and the property table it needs.
- Rive's own docs, which are the authority: `rive docs`, and on disk at `~/.rive/versions/<v>/docs/`.
  `rigging.md` is bones, skinning and constraints; `easing.md` covers joysticks and blend states.
- `rive <dir> --screenshot --advance=N` renders one frame headless, which is how you look at your own
  output.

## A limit worth stating

**Video cannot be watched.** A video tutorial teaches nothing here. What can be used: the docs, a real
`.riv` taken apart, and the reference animation's own frames decoded to PNG and measured. Ask for a
file or a link to a file, not a video.
