---
name: rive
description: Make Rive content (.riv) with the Rive CLI and RML text, including animated UI pieces (buttons, toggles, tab icons, loaders), illustrated and painted assets, 3D-looking objects (real glTF on the GPU Canvas, or faked with orthographic projection), state machines, data binding, events that drive haptics, and headless verification. Use it whenever someone builds or edits a Rive file, an RML scene, a Luau or WGSL script for Rive, a Rive state machine or view model, a micro-animation meant to ship as .riv, or asks why a Rive file looks or moves wrong. For rigging a character (bones, skinning, IK), also load rive-character.
---

# Making Rive content that looks good

Rive here is authored as TEXT. A project is a directory with `rive.yaml` and `scene.rml` (an XML
scene: artboards, shapes, animations, state machines, view models), plus any `.luau` scripts,
`.wgsl` shaders, images and blobs. The Rive CLI (`rive`, normally `~/.rive/bin/rive`) compiles it,
renders frames headless, and pushes it to the Rive editor. Treat the text as the source of truth:
do not hand-edit in the browser and then export over it.

The lessons here were measured on CLI 1.2.0. Newer CLIs can refuse to run an older version
("rive X is required"); `rive update` or `rive switch` fixes that, and the docs on disk at
`~/.rive/versions/<v>/docs/` are the authority for anything that changed.

## Pick the method before drawing anything

| What you are making | Method | Example to copy |
|---|---|---|
| A small icon or UI piece that reacts (tab icon, toggle, pill button, loader) | Generated RML from a Python script with `scripts/uilib.py`: flat cel shapes, an outline, one-frame steady states | `examples/toggle`, `examples/pill-button`, `examples/loader` |
| A rich illustrated object (glass jar, premium prop) | Painted layers: image renders on a key colour, keyed, split into back and front, laid in as `Image`s | [painted-layers.md](painted-layers.md) |
| A 3D object that turns, opens or spins | Real 3D (glTF and WGSL on the GPU Canvas) or fake 3D (orthographic projection to 2D affine maps). See [3d-in-rive.md](3d-in-rive.md) | `examples/gpu-toon-heart` |
| A 2D screen mapped onto 3D (a phone, a card, a sign) | An artboard rendered into a `Canvas`, sampled as a texture, pointer events raycast back to it | `examples/gpu-phone-artboard` |
| A character or mascot | Bones, skinning, IK. Load the `rive-character` skill | |
| Changing an existing big scene | An asserting edit script that rewrites the RML text and fails loudly if it does not apply | `scripts/rive_keys.py` |

## The workflow

1. **Reference first.** Find or generate the board the piece must match. The board is the spec,
   element by element. Approved art is the reference for every redraw (feed it in as an edit, not
   as a text prompt).
2. **Generate, do not hand-type.** A Python generator writes `scene.rml` with fresh ids, named
   eases and helper shapes (`scripts/uilib.py`: `cel`, `shape`, `Anim`, `Machine`, `events`,
   `artboard`, `build`). Re-running it rebuilds the piece exactly. Start from the closest example.
3. **`rive <dir> --verify` after every edit.** It compiles RML, Luau and WGSL and writes nothing.
   A clean build is NOT a correct file (see [gotchas.md](gotchas.md)).
4. **Render and look at the result yourself.** Use
   `rive <dir> --screenshot=<abs path> --advance=1 --artboard=<name>`. Make state sheets by
   rewriting input defaults in a temporary copy (`scripts/shoot.py`). Grade at full size against
   the board ([quality-bar.md](quality-bar.md)).
5. **Build the shipped file.**
   - With no scripts, `rive <dir> --once` writes the clean unsigned `.riv`.
   - A `--publish` from a project that is not linked to a cloud file can come out bigger and show a
     splash screen in the app.
   - Files WITH Luau or WGSL scripts must ship from `--publish` (signed). The CDN and the web
     runtimes reject unsigned scripts. Link the project with `rive push` first so the publish is
     clean. See [cli-workflow.md](cli-workflow.md).
6. **Record the first seconds in the app** before shipping a new `.riv`. Look for a black box or
   splash, a missing asset, and a wrong first frame.

## Rules that hold everywhere

- **The first child declared paints ON TOP.** That is the reverse of SVG and HTML, so list the
  front first. Overlap carries meaning: a highlight inside an eye node closes with the blink.
- **Steady states are one-frame one-shot animations.** The machine settles, `advance` reports
  nothing left, and the runtime can stop its display link, so nothing draws at rest. The app fires
  idle life (`idle`, `shine`, `twinkle`) every 9 to 16 s. Do not use a looping idle pulse on UI
  chrome. A loader is the one honest loop, and it is paused when off screen.
- **A layer never re-enters the state it is in.** For a retriggerable reaction, make two copies and
  alternate the triggers (`pokeA` / `pokeB`), or add an explicit state-to-itself transition.
- **Events carry haptics and sounds.** Key a Rive `Event` (`h:pop`, `m:squish`) on the impact
  frame. The app maps the name to a haptic. That beats guessing timings in app code
  ([motion.md](motion.md)).
- **Words stay out of the file.** A button's label is native text laid over the Rive body and
  squashed with the same numbers, so it localises and never waits on a font.
- **Drive with data, not with copies.** A width is a number feeding a 1D blend of two one-frame
  poses. A look is a view model with colour, image and number properties
  ([data-binding.md](data-binding.md)).
- **New controls go on NEW parent nodes.** A property that some animation keys is overwritten every
  frame. Wrap the body in new nodes that nothing else keys and drive those.
- **Shading is a style decision made once.** The default in `uilib.cel` is flat cel plus an outline:
  base fill, a copy nudged up-left and clipped to it (which leaves a shade crescent lower right),
  and the line on top. Use no gloss unless the board has it.
- **Shared pieces are one source.** A heart or logo shape used by the app, by a Lottie and by Rive
  should come from one set of numbers.
- **Draw a mascot only as a live rig.** Never fake a mascot with code-drawn shapes or a still where
  the rig belongs.

## Scripts (bundled, run from anywhere)

- `${CLAUDE_SKILL_DIR}/scripts/uilib.py`: shapes (`ellipse`, `rect`, `poly`, `cubic_path`,
  `heart_path`, `sparkle_path`, `arc_path`), paints, `cel`, `node`, `Anim` (keys with named eases,
  one-frame holds, events), `Machine` and `Layer` (bool, number and trigger inputs, transitions,
  1D blends), `artboard`, `write`, `build`. Palette constants at the top are neutral defaults:
  override them.
- `${CLAUDE_SKILL_DIR}/scripts/rive_keys.py`: for editing an existing scene with scripts. Fresh
  ids that assert they are unused, key and animation writers, view model property insertion,
  trigger and number conditions, springs, Hermite re-keying of baked tracks, converters.
- `${CLAUDE_SKILL_DIR}/scripts/shoot.py`: headless labelled state sheets (needs Pillow).

Import them from a generator with
`sys.path.insert(0, '${CLAUDE_SKILL_DIR}/scripts')`, or copy the three files next to your project.

## Examples (each builds with `python3 gen.py`, then `rive . --verify`)

- `examples/toggle/`: a switch. Slide with stretch and squash, track recolour, a floating tick, a
  press layer, haptic events. Two layers, one-frame steady states.
- `examples/pill-button/`: a button body of any width (1D blend), press squash and rebound,
  disabled mix, a tap flash with sparkles, a shine wobble, events. Label left to the app.
- `examples/loader/`: three dots hopping in turn, one looping state, parabola eases.
- `examples/gpu-toon-heart/`: a glTF heart loaded from a blob, three-tone toon shading plus
  inverted-hull outline, 4x MSAA. Run `python3 make_heart.py` to write `heart.glb`, then
  `rive . --screenshot=$PWD/build/heart.png --advance=10`. Result: `examples/shots/toon-heart.png`.
- `examples/gpu-phone-artboard/`: a glTF phone whose screen is a live artboard (its own state
  machine, view model and listener). Run `python3 make_phone.py` (needs numpy), then a headless
  `--pointer=click` on the 3D tab moves the dot. Before and after: `examples/shots/phone-*.png`.

## Reference files

- [cli-workflow.md](cli-workflow.md): project layout, RML ids, assets, `--verify`, `--once` vs
  `--publish`, screenshots, data dumps, pointers, push and pull, asset size, loading on iOS.
- [3d-in-rive.md](3d-in-rive.md): the glTF plus GPU Canvas technique, artboards on 3D, and fake 3D
  by projection. Tradeoffs.
- [painted-layers.md](painted-layers.md): generate on a key colour, key, split back and front,
  write geometry, place sprites.
- [data-binding.md](data-binding.md): view models, binds, converters, image properties, Solo
  switching, listener write-back, the app side.
- [motion.md](motion.md): eases, springs, follow-through, re-keying baked tracks, events to
  haptics, idle life without loops.
- [gotchas.md](gotchas.md): every silent failure we hit, one line each with the fix.
- [quality-bar.md](quality-bar.md): how to review. Full-size frames, side by side, against the
  board, at 1x on device size, every frame of a move.

Rive's own docs are the authority: `rive docs`, on disk at `~/.rive/versions/<v>/docs/`
(`gotchas.md`, `data.md`, `state-machines.md`, `luau/api/gpu.md`). `rive schema <Type> --all` lists
every property. `rive samples` lists the starter projects.
