# Silent failures, one line each

Format: **symptom**: cause. Fix. Everything here built clean and looked wrong, or did nothing.
Rive's own list is `~/.rive/versions/<v>/docs/gotchas.md`; the ones from it that bit us are repeated.

## Draw order and paint

- **A shape you added is invisible**: the first child declared paints on TOP, and you listed it
  under something opaque. Declare front first.
- **A gradient on a shape never shows**: within one shape, LATER paints draw over earlier ones, and
  a gradient sat before the solid. Put the overlay paint after the base.
- **A prop drew under one eye** (glasses, a hat slot): a `DrawRules` put the slot just in front of a
  sibling, so everything listed before that sibling drew over it. Delete the rule and make the slot
  the anchor's first child, or draw it in front of the topmost paint of the thing it sits on.
- **A glow or blush draws over clothes**: no draw rule on it. Rule it in front of the body's top
  paint and under the clothing.
- **A white box behind the character**: the artboard's own background was white. Make the artboard
  fill `00FFFFFF`.
- **A feathered fill draws nothing**: Rive's docs say "Feather in a Fill renders nothing". Tested on
  CLI 1.2.0, that is true only for the default `nonZero` fill rule. **With `fillRule="2"`
  (clockwise) a Fill+Feather draws a soft blob, and `inner="true"` an inner rim.** Feathered strokes
  work under any rule.
- **A feathered limb has a halo outside its outline**: an inner Feather bleeds past the shape. Clip
  the shape to ITSELF (`<ClippingShape sourceId="<own id>"/>`).
- **A closed path renders as a hole**: a counter-clockwise path is cut out by the clockwise fill
  rule. Wind it clockwise or change `fillRule`.
- **The lit side of a raised arm washed out**: a gradient sits in the SHAPE's frame, not the bone's,
  so a rotating limb swings into its light. Keep the limb's light faint and let the dark edge carry
  the volume.
- **A cel shade crescent was missing**: the face copy was not clipped to its base. Use `uilib.cel`
  (base fills shade, an up-left nudged copy clipped to it fills base, outline on top).

## Clips, limbs and meshes

- **A limb was cut off in a straight line short of the body**: the occlusion clip's inner edge sat
  too far out from the shoulder. Move the clip edge well behind the body.
- **A raised arm looked detached**: the arm tapered to a point at its root, so raised it met the
  body at its narrowest. Keep it full width to the pivot and bury a round cap behind the body.
- **A sleeve folded or twisted when the arm rose**: a drawn hanging sleeve cannot be skinned to rise.
  Skinned follow, a sleeve bone, two-layer sleeves and a hidden elbow all failed. Draw sleeves for
  the raised pose, or edit them by hand in the editor.
- **A collar curled into a horn or left a V notch**: the arm-share falloff was too narrow or too
  wide. A smoothstep field with a generous falloff held.
- **Cloth would not bend smoothly**: a 20-unit mesh grid is too coarse. Split each bent triangle
  4 x 4 with barycentric weights, and check that the rest pose renders pixel-identical.
- **Strap ends floated as two caps**: lengthen each end along its own slope under the art, then cut
  it flush at the body's silhouette in the side bands only.
- **A garment was wider than the body with horn-like flaps**: if a patch needs a patch, retire that
  garment instead.
- **A hat lags the body's tilt**: a hat anchor that does not rotate with the body. Parent it to the
  head bone or add the rotation.
- **Skin weights did nothing**: `Weight indices` are 1-based and `values` must total 255. See
  `rive-character`.

## State machines and keys

- **Two characters blinked in step**: Idle is entered with `reset="true"`, so every move restarted
  its blinks from frame 0. Take blinks out of the rig and blink from the app on each character's own
  clock.
- **A second tap during a reaction was ignored**: a layer never re-enters the state it is in. Use
  two copies of the reaction and alternate the triggers.
- **A property you set from the app snaps back every frame**: some animation keys it. Add a NEW
  parent node that nothing keys and drive that.
- **An artboard renders but nothing moves**: there is no state machine, or the layer has no entry
  transition. An artboard without a machine is half alive.
- **`cubic` keys move linearly**: a `cubic` key with no `CubicEaseInterpolator` eases nothing.
- **A colour key does nothing**: the keyframe type must match the property (`KeyFrameColor` for 37,
  `KeyFrameDouble` for numbers).
- **A one-shot loops or a loop stops**: `loopValue` is `oneShot`, `loop` or `pingPong`. Check what
  the state's exit time assumes.
- **A 1D blend drifts with every advance**: Rive mixes the blend's poses ONTO what is already there.
  Put a layer under it that enters a plain state holding the first pose.
- **A rig edit script ran twice and doubled things**: assert the marker or the id range is unused
  first (`rive_keys.Ids`, `MARK not in s`), and assert every substitution count.

## Data binding

- **`--data` logged the write but nothing changed**: a two-way bind won on the first frame. Set
  `sourceToTargetRunsFirst="true"`.
- **A listener click did nothing**: `ListenerViewModelChange` lacked `direction="true"`.
- **A bind does nothing**: the path dangles or the property key is wrong for the target. Run
  `rive inspect . --json | jq '.problems'`.
- **A script input is always its default**: `ScriptInput*` match Luau fields by NAME, silently, and
  `inspect` does not read Luau.
- **A Luau view model handle is nil forever**: `init` runs twice, and `context:viewModel()` is nil
  the first time. Guard and retry.
- **A shader or blob is nil**: lookups by name are unvalidated strings. Check the result and the
  file name.

## GPU Canvas and Luau

- **A type error on a pipeline descriptor**: an inline table literal is inferred as a string union.
  Annotate it (`local d: DepthStencilState = ...`).
- **`depth24plus` is rejected**: it is not a texture format. Use `depth32float`.
- **The pointer handler had no matrix**: headless runs (and possibly real ones) call `advance` and
  pointer handlers before the first `draw`. Compute state in `advance`.
- **A texture samples black**: `Image:view()` of an `ImageAsset` samples zeros. Draw it into a
  `context:canvas()` and sample that canvas's image.
- **Toon bands or outlines are jagged**: there is no MSAA, or the bands are hard-stepped. Use 4x
  MSAA with resolve, and smoothstep each band edge by `fwidth`.
- **The effect is soft on device but sharp headless**: a canvas or texture was sized in points.
  Multiply by `resize`'s `scale`. Headless always runs @1x, so check in the live window.
- **The web runtime refused the file**: the scripts were unsigned. Build with `--publish`.

## Building and shipping

- **A black splash for 2 to 4 s in the app**: the file came from `--publish` on a free plan, or from
  an unlinked project. Ship script-free files from `--once`, and record the first seconds in the app.
- **The frame was captured before anything moved**: a `--screenshot` without `--advance` shows the
  authored rest pose. Always `--advance=1` or more.
- **Parallel renders overwrote each other**: they share `build/`. Give each worker its own `cp -Rc`.
- **The cloud file undid weeks of work**: the editor file was older than the RML source. Never
  export or pull over the source without diffing. Pull a backup first.
- **A new resource never reached the app**: SwiftPM held a stale resource list. `touch Package.swift`.
- **SwiftPM hangs at 0 percent CPU**: it is fetching a runtime's binary zip. Install the artifact by
  hand.
- **The widget extension is huge**: the `.riv` sat in a package both targets share. Put it in the
  app bundle (`Bundle.main`).
- **Launch froze for half a second**: the `RiveFile` loaded on main. Load it on its own queue at
  app init.
- **The CLI refuses to run ("rive X is required")**: a newer minimum version is published. `rive
  update`, or `rive switch` to a cached version that satisfies it.

## Runtime (iOS)

- **A black square before the character**: a Rive view is black before its first frame. Keep it
  hidden (opacity 0.001, never 0, so its clock runs) until the first advance, then fade in.
- **14.8 percent CPU at rest**: hidden players kept playing. Pause on hide, background, cover or
  off-tab.
- **A crash on a touch**: an event callback assumed main (`MainActor.assumeIsolated` traps). Hop to
  main when not on it.
- **A whole screen rebuilt when a character appeared**: an unchanged look was reassigned to a
  `@Published` property. Compare before setting.
- **An iOS 17 crash, "scale must be > 0"**: a `UIImage` at scale 0.5 rounds to 0 in CoreUI. Clamp
  every runtime image's scale to at least 1.
- **A celebration's best beat played off screen**: it started on appear, under a sheet's slide.
  Start after the presentation (about 0.35 s).
- **A widget or Live Activity shows nothing**: those processes cannot run Rive (or a timer). Render
  stills from the rig in the app, or draw SwiftUI shapes.
