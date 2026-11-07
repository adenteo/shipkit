# The quality bar and how to review

The bar is a real phone, next to the best apps in the category, and the question is "does it look
like a cartoon", not "does the beat read". Every round that was graded from a thumbnail or from
the code came back. These are the gates.

## Before building: the reference is the spec

- Generate or find a board first. When the brief says "exact same implementation", list the board's
  elements top to bottom and build exactly those: same order, proportions and placements.
  "Inspired by" does not pass.
- Approved art is the reference for every redraw. Feed the approved image into the generator (an
  EDIT, not text). A redraw from text loses the approved look and costs a full round.
- For any spend on many assets, show a two-look proof first.

## Review at full size, yourself

- Open the full-resolution frame. A crop or contact-sheet tile hides exactly the drift that
  matters: limb counts, a detached arm, a fringe, an eye off centre in a lens. Grade from 760 px or
  larger.
- If a subagent says it passes, re-render and look before repeating the verdict.
- Look at **1x on device size** too (the real size the piece ships at: a 30 pt tab icon, a 46 pt
  pill). Something can be fine at 3x and mush at 1x, or fine at 1x and broken at 3x.

## Side by side

- Put the render NEXT to the reference or board at the same scale. Judge the silhouette at the key
  pose first, then the beat.
- Grade every feature separately (see `rive-character`). One global IoU read 0.94 on a face whose
  mouth scored 0.23.
- Show before and after for every change to something approved.

## Every frame, every state

- A move is checked at its extremes, not its rest. A sleeve gate failed 225 of 7,581 frames that
  the rest pose hid.
- State sheets: `scripts/shoot.py` renders each input combination at several times into one
  labelled sheet. Look at pressed, released, selected, disabled, tapped and idle, at 0, 100, 200,
  400 and 1200 ms.
- Motion is checked from a RECORDING, frame by frame (`xcrun simctl io <device> recordVideo` with an
  ABSOLUTE path, ffmpeg contact sheets at 30 fps), not from a still. A spring on a just-inserted
  view can appear at its end. An animation's best beat can play under a sheet's slide.
- Check the first seconds of a new `.riv` in the app for a black box or splash, a missing image or a
  wrong first frame.

## Common rejections (do not ship these)

| Area | Rejected |
|---|---|
| Edges | Jagged edges on anything rotated or tilted. Flatten photos with a 1 pt clear margin; draw paper as a shape, not a clipped image. In 3D, use MSAA and fwidth-softened bands. |
| Limbs | Arms that grew longer than before; arms cut in a straight line or detached at the shoulder; a sleeve that twists or folds when raised; a hand poking out sideways; "two limbs". |
| Faces | Eyes off centre in glasses; a moving white dot in the eye that reads as a flaw; a feature the character was never designed with (a mouth on a mouthless character). |
| Art method | Pictures cut up with flood fill, slabs and inpainting. Each part is its own render on a key colour or its own vector, with named states. |
| Fakes | A mascot drawn in code or as a still where the live rig belongs. A splash screen is a clean mark, never a fake mascot. |
| Motion | Linear motion; idle glow pulses on buttons; 3D card flips; scale on scrolling rows; two characters idling in step; looping chrome while nothing happens. |
| Flatness | Flat discs pretending to be 3D coins; a lock not in its face's plane; a dull painted inside. |
| Celebrations | Confetti that steals focus, half hearts. One whole hero burst beats many small ones. |
| Labels | Text that repeats what the picture already says. |
| Customisation | Choices visible only in an editor preview. Every customisation must show on the real output. |

## Performance is part of quality

- 60 fps throughout, measured: main-thread hitch logs, and a device for GPU cost (blur, shadows,
  materials).
- Nothing draws at rest: one-frame steady states, paused hidden players.
- Keep files small. A rig is about 12 MB, UI pieces a few KB, a vector chest 112 KB. Before adding
  megabytes of images, ask whether a vector or a mesh texture would do.

## A review checklist to run before saying "done"

1. Does it match the board element by element? (side by side, full size)
2. Is every state and every extreme frame clean? (state sheet plus extremes)
3. Is it right at 1x on device size? (app screenshot)
4. Are edges smooth on every rotated thing?
5. Does it move with eases, follow-through and the right haptic on impact? (recording)
6. Does nothing draw at rest? Is the first second free of black and splash?
7. Did you look yourself, at the full frame, after the last change?

## Procedural 3D loses to painted art

Six toon-shaded GPU Canvas previews were built from primitives made in Luau (rounded boxes,
spheres, a lathed jar, flat planes): globe, die, coin, polaroids, jar, chest. Side by side with the
existing painted and hand-drawn versions, all six read worse: unpolished shapes, clip art. All six
were dropped.

- Toon shading on primitives reads as clip art. What carries quality is drawn detail: painted layers
  or real modelled meshes with painted textures. Primitives alone never get there.
- A busy scene of many small objects in motion survives primitives, because no single object is
  studied. A single hero object on its own (a die, a chest, a print) is studied, and every flat
  facet shows.
- Before replacing an existing asset, render the new one beside the original at the size it ships,
  and keep the original unless the new one is plainly better in both stills and motion. Motion does
  not excuse a worse still.
- If an object must be 3D and alone on screen, use a properly modelled mesh with bevels and a
  painted or baked texture (generated or sourced), not a primitive.
