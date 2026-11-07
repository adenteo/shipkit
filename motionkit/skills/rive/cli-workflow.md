# The CLI workflow

The CLI is `rive` (normally `~/.rive/bin/rive`). `rive --version` checks it; `rive switch` picks a
cached version and `rive update` installs the newest. Its docs are on disk at
`~/.rive/versions/<v>/docs/`; start with `README.md`, `gotchas.md` and `format.md`. Everything here
was measured on 1.2.0.

## A project

```
piece/
  rive.yaml        name (required); main artboard; exclude; push link; shaderOutputs
  scene.rml        the scene (or several .rml files, compiled as one document)
  *.luau           scripts (no markup needed, a ScriptAsset is created)
  *.wgsl           shaders (no markup needed, fetched by name from Luau)
  art/*.webp|png   images, declared as <ImageAsset file="art/x.webp" .../>
  anything else    a blob, declared as <BlobAsset file="..."/> or read with context:blob
```

- Keep generators beside their output and exclude them: `exclude: ["*.py", "shots/**"]`.
- Assets are embedded only when something references them. A stray file adds nothing to the
  output, but a typo'd image path becomes a blob silently.
- To start from an editor file, use `rive create <dir> --from-rev=x.rev` or
  `--from-remote-file=<id>`. That writes every script, shader and asset as a file.

## RML in one screen

```xml
<Rive version="1" kind="fragment">
  <Artboard defaultStateMachineId="0:7" width="80" height="80" name="TabHome" id="0:2">
    <LayoutComponentStyle name="Artboard Style" id="0:5"/>   <!-- an artboard needs a style -->
    <Shape x="40" y="40" name="Front" id="0:10">            <!-- FIRST child = drawn on TOP -->
      <Ellipse width="20" height="20" name="Path"/>
      <Fill name="Fill"><SolidColor colorValue="FF4F7CFF" name="C"/></Fill>
    </Shape>
    <StateMachine name="Tab" id="0:7">...</StateMachine>
    <LinearAnimation loopValue="oneShot" fps="60" duration="1" name="Off" id="0:20">...</LinearAnimation>
  </Artboard>
  <ImageAsset file="art/big/back.webp" width="486" height="900" name="big-back" id="0:900"/>
</Rive>
```

- **Ids** are `"0:N"`. Generators hand them out from a counter (`uilib.nid`). Edit scripts on an
  existing scene take a fresh range and assert it is unused (`rive_keys.Ids(scene, 1300000)`), so a
  script cannot run twice.
- **Colours are ARGB hex** without `#`: `FF` + RGB, so `2E4F8A5E` is that green at 18 percent.
- **Rotation is radians. Durations and frames are frames** at the animation's fps (60).
- **Property keys** you key and bind most: x 13, y 14, rotation 15, scaleX 16, scaleY 17,
  opacity 18, width 20, height 21, colorValue 37, stroke thickness 47, Image assetId 206, Event
  trigger 395, bone y 91. The bindable `propertyValue` keys are number 636, boolean 634, trigger
  686, colour 638 and Id 823. Look anything else up with `rive schema <Type> --all`, or `--json`
  for scripts. The rive-character skill ships `schema.json` with all 353 types.
- `rive inspect <dir> --json | jq '.problems'` reports dangling binds and type mismatches that the
  build does not.

## Build modes

| Command | Use |
|---|---|
| `rive <dir> --verify` | After every edit. Compiles RML, Luau and WGSL, writes nothing. |
| `rive <dir> --once` | A clean unsigned `.riv` in `build/<name>.riv`. **The shipping build for files with no scripts.** |
| `rive <dir> --publish` | Signed `.riv` (scripts compiled server-side). **Required for any file with Luau/WGSL that ships**: the CDN and web runtimes reject unsigned scripts, while the local viewer plays them happily. |
| `rive <dir>` | A live window that rebuilds on save, and the only way to see Retina scale (`viewport 1880x1130 @2x`). |
| `rive <dir> --test` | Runs Luau `Tests` scripts. |

Watermark and splash history, so you know what to look for:

- On a free plan, `--publish` printed "watermarked" and every view showed a black splash for about
  4 s from the view's creation.
- After a paid plan, a `--publish` of an UNLINKED project still came out about 15 KB bigger and
  showed the splash for about 2 s.
- `--publish` is clean once the project is linked to an account file with `rive push` (a
  `push: projectId/fileId` block in `rive.yaml`).

So: ship script-free files from `--once`. Ship scripted files from `--publish` on a linked project.
Record the app's first seconds either way.

## Looking at frames headless

```bash
rive <dir> --screenshot=/abs/out.png --artboard=Jar --viewport=480x480 --fit=contain --advance=500ms
rive <dir> --screenshot=/abs/x.png --data=eyeMood=3 --data=bodyColor=FFF2A2B0 --advance=650ms
rive <dir> --screenshot=/abs/x.png --advance=20 --pointer=click@280,528 --advance=10
rive <dir> --data-dump=- --data-dump-filter='energy,look*' --data-dump-every=100ms --advance=2s
rive <dir> --bench=600          # advance and render stats, wasm memory growth
```

- **Always `--advance` at least 1.** Without it you capture the authored rest pose before the state
  machine ran. That looks valid and is wrong.
- Headless capture is always at `@1x` with `scale = 1`. It cannot show a canvas sized in points
  instead of pixels.
- `--data` sets view model properties. It cannot set legacy state-machine inputs or images. For
  inputs, rewrite the input's default in a temporary copy of the scene (`scripts/shoot.py` does
  this and tiles a labelled sheet). For an image property, point the default instance's image
  property at an asset id in a scratch copy.
- **Parallel renders share `build/`.** Give each worker its own `cp -Rc` copy of the project.
- `--pointer=kind@x,y` is in artboard coordinates. Combine it with `--advance` steps to test
  listeners and scripted pointer handlers.
- In headless runs, `advance` and pointer handlers run before any `draw`. A script that computes
  its matrices in `draw` has nothing when the pointer arrives, so compute them in `advance`.

## Editing a big existing scene (the rig pattern)

A large scene (a character rig is about 1 MB of RML text) is changed only by asserting scripts:

1. Each script runs ONLY after its predecessor and only once: `assert 'name="eyeStyle"' in s, "run
   the previous script first"` and `assert MARK not in s, "already applied"`.
2. Each substitution asserts its count, and edits EVERY copy of a duplicated thing (two characters
   that share a rig). A future layout change then fails loudly instead of silently doing nothing.
3. Rebuild: unzip the source, run only the NEW script, `rive . --verify`, `rive . --once`, copy
   `build/*.riv` into the app, then re-zip the edited `scene.rml` into the source archive.
4. Keep a byte check: a `--once` build of the unchanged source must equal the shipped `.riv`.
5. Write the rebuild order down in the repo, next to the scripts.

## Push and pull (the editor round trip)

- The first `rive push` picks a project, then records `push.projectId` / `push.fileId` in
  `rive.yaml`. Commit that block.
- Later pushes diff and patch, and a push is authoritative over open editor sessions. Revisions are
  kept, so a push never loses history.
- `rive pull` overwrites the project from the cloud file. Ask before using it.
- **A cloud file can be OLDER than the text source.** Never export or pull it over the source
  without diffing. Pull a backup first. If someone edits in the editor on purpose, take that edit
  back as the truth (export `.riv` or pull), because the text no longer describes the shipped file.
- Sessions use `rive login`. A process with a different `HOME` reports `Not logged in`.

## Size

Measured on real files:

| What | Cost |
|---|---|
| An embedded font (Montserrat) | 394 KB of a 451 KB proof. The 3D geometry, shaders and scripts were about 55 KB. |
| Layered outfit PNGs | Took a rig from 11.56 MB to 14.59 MB. |
| Re-keying baked motion at turning points | Took a rig from 11.90 MB to 11.53 MB, with more motion in it (26,000 keys became about 8,000). |
| A fake-3D chest | 112 KB of pure vectors with a nested coin artboard. |
| A looping living mark | 12 KB. |
| A UI piece | A few KB. |

Levers:

- WebP q88 for painted layers, and one art size per display density.
- No fonts in the file (lay the app's text over the Rive view).
- `shaderOutputs: [msl]` in `rive.yaml` when a scripted file ships only to Apple (all five backends
  are compiled by default).
- Quantised glTF (int16 positions, `snorm8x4` normals) for 3D.

## Runtime on iOS (rive-ios)

- **Load the `RiveFile` off the main thread**, once per process, on its own queue. On main, it
  froze the launch for 0.57 s. Small UI files parse in under a millisecond and can be cached on
  main.
- Share the file; give each view its own artboard and view model instance.
- Image assets come through the loader closure (`RiveFile(name:in:loadCdn:false) { asset, bytes,
  factory in ... imageAsset.renderImage(factory.decodeImage(bytes)) }`). Images added at runtime
  come from `RiveRenderImage(data:)`.
- Make the `RiveView` transparent (`isOpaque = false`, `.clear`). Fade the view in after the first
  advance, because it is black before its first frame.
- **Pause what you cannot see.** Hidden players kept running: a screen at rest used 14.8 percent
  CPU with Rive and 0.0 without. Pause behind sheets, in the background and off-tab. Idle playback
  at 30 fps read as stutter, so use 60 and pause instead.
- Events arrive from `advance`. Hop to main if not already on it. `MainActor.assumeIsolated` traps.
- Put a large `.riv` in the APP bundle, not a package shared with a widget extension.
- **Widgets and Live Activities cannot run Rive.** Render snapshots from the live rig in the app
  into the App Group, or draw SwiftUI shapes. A Live Activity also cannot run its own timer, so
  drive any frame from the state.
- The GPU Canvas (3D, shaders) needs rive-ios 6.25.0+ through the Swift Concurrency
  `Worker(configuration: .init(enableGPUCanvas: true))` API. The legacy `RiveViewModel` path does
  not run it ([3d-in-rive.md](3d-in-rive.md)).
- If SwiftPM hangs at 0 percent CPU resolving the runtime, it is fetching a binary xcframework zip.
  Download the artifact by hand and point the package at it.
