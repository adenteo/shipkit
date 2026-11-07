# 3D in Rive

There are two ways to get a turning, opening, lit object into a `.riv`. Pick by where the file has
to run and what has to move.

| | Real 3D on the GPU Canvas | Fake 3D (orthographic to 2D affine) |
|---|---|---|
| Source | A glTF/GLB mesh read as a blob by a Luau script, drawn with WGSL | A Python model; each planar face is drawn flat and placed by nested Nodes |
| Free camera, free rotation, relight at runtime | yes | no: one fixed camera, with motion baked to keys |
| Looks like | Whatever the shader says (toon bands and outlines read as illustration) | Hand-drawn vector, every face a real Rive shape you can style |
| Runs on | Runtimes with GPU Canvas: rive-ios 6.25.0+ through the `Worker` API, web `@rive-app/webgl2` 2.42.0+, React Native 0.5.3+, Flutter 0.15.0-dev.1, Unreal, C++; Android experimental (11.12.0+) | Every runtime, every renderer, the legacy iOS `RiveViewModel` |
| Ships as | `--publish` (signed scripts and shaders) | `--once` |
| Example | `examples/gpu-toon-heart/`, `examples/gpu-phone-artboard/` | build your own with the projection recipe below |

## Real glTF, drawn to look vector

The technique: standard glTF models loaded straight into Rive and drawn on the GPU Canvas with flat
three-tone shading and outlines, so they read as illustration rather than as a render. A phone model's
screen can be a live artboard you scroll and tap in 3D. It can be built entirely with the CLI.

### What each piece is

**VERIFIED** means read in CLI 1.2.0's docs and/or built and rendered. **INFERRED** means not seen
stated.

| Piece | How | Status |
|---|---|---|
| Scripting | A Luau `Layout` script (`ScriptedLayout` in a fill-sized `LayoutComponent`), with `init`, `resize(self, size, scale)`, `advance`, `draw` and pointer handlers | VERIFIED |
| Loading glTF | **No glTF asset type.** A `.glb` is a blob: `<BlobAsset file="phone.glb" name="phone"/>`, or just referenced by name. Read it with `context:blob('phone').data`, a Luau `buffer`. Parse it yourself: 12-byte header, JSON chunk, BIN chunk, accessors to `GPUBuffer`s. A parser and a small JSON decoder are in `examples/*/phone3d.luau`, `main.luau` and `json.luau`. | VERIFIED (built) |
| GPU drawing | `context:gpuCanvas()`, sized in `resize` to `size * scale` pixels. `GPUPipeline.new{vertex, fragment, vertexLayout, colorTargets, depthStencil, cullMode, sampleCount}`, `GPUBuffer`, `GPUBindGroup` from `pipeline:getBindGroupLayout(0)`, `canvas:beginRenderPass{color, depthStencil}`, `pass:drawIndexed`, then `renderer:drawImage(canvas.image, ...)` composites it into the 2D scene. Docs: `luau/api/gpu.md`. | VERIFIED |
| Shaders | `.wgsl` files are compiled at build and fetched with `context:shader('name')`. Several entry points per file are allowed: `{module = shader, entryPoint = 'vs_outline'}`. Only vertex and fragment stages. Raw WGSL strings are not accepted at runtime. | VERIFIED |
| Three-tone shading | In the fragment shader, `d = dot(normalize(n), light)`. Pick shadow, mid or lit by two thresholds (we used -0.05 and 0.45). **Soften each band edge by `fwidth(d)` with `smoothstep`**, or the bands stair-step. | VERIFIED (built) |
| Outlines | Inverted hull: the same mesh drawn first with `cullMode='front'`, each vertex pushed out along its normal by a width uniform, flat ink colour. It needs smooth (averaged) normals; a hard-edged mesh splits its hull at the creases. Screen-space edge detection (depth/normal discontinuities in a second pass) is the alternative for hard-edged models. | Hull: VERIFIED (built). Edge pass: INFERRED |
| Smooth silhouettes | 4x MSAA: a `GPUTexture{sampleCount=4, renderTarget=true}` as the colour view, the canvas's `colorView()` as `resolveTarget`, and a depth texture `depth32float` with the same sample count. Pipelines take `sampleCount = 4`. Without it, the outline is jagged. | VERIFIED (built) |
| An artboard as a texture | Take an artboard input (`Input<Artboard>` filled by `<ScriptInputArtboard artboardId="0:100" name="screen"/>`), then `self.screen:instance()`, and `board:advance(dt)` in advance. Each draw: `local r = canvas2d:beginFrame{}`, `board:draw(r)`, `canvas2d:endFrame()`, where `canvas2d = context:canvas{width, height}`. Sample `canvas2d.image:view()` in a WGSL `texture_2d` at `@binding(1)` with a `GPUSampler` at `@binding(2)`. The artboard keeps its own state machine, view model, text and layouts. | VERIFIED (built) |
| Using it in 3D (tap and scroll) | In the Layout's `pointerDown`/`Up`/`Move`: invert the MVP, unproject the pointer at NDC z 0 and 1 into model space, intersect the screen's plane, and map the hit to UV, then to artboard pixels. Call `board:pointerDown(PointerEvent.new(event.id, Vector.xy(u*W, v*H)))`. Its listeners fire. A headless click on the 3D tab moved the dot. | VERIFIED (built) |
| Spin, relight, animate | Uniforms written every frame from `advance` (a model matrix, a light vector), so all of it is live and can be bound to view model data | VERIFIED (built) |
| CLI then editor | `rive push` sends scripts, shaders, blobs and artboards to an account file, so the editor's tools keep iterating on it | VERIFIED (docs) |
| Small files | The phone proof is 451 KB, of which 394 KB is the embedded font. Geometry, two shaders, scripts and the screen artboard are about 55 KB. Quantised meshes and no fonts keep a whole scene in the low hundreds of KB. | VERIFIED |

### The two proofs

Both work on CLI 1.2.0, headless:

- `examples/gpu-toon-heart/` draws a 6,305-vertex implicit-surface heart, written as a GLB by
  `make_heart.py`. The `.riv` is 255 KB. See `examples/shots/toon-heart.png`.
- `examples/gpu-phone-artboard/` draws a phone slab and screen quad (a 17 KB GLB) with a live
  "Screen" artboard on it. A view model `dotX` and a click listener on the tab write `dotX = 260`.
  `--pointer=click@280,528` on the tilted 3D phone lands at artboard (180, 620), the tab's centre,
  and the dot moves. See `examples/shots/phone-before-tap.png` and `phone-after-tap.png`.

Run one with:

```bash
cp -R ${CLAUDE_SKILL_DIR}/examples/gpu-toon-heart /tmp/x && cd /tmp/x
python3 make_heart.py && rive . --screenshot=$PWD/build/heart.png --advance=10
```

### Things the proofs taught (each cost a build)

- Luau types are checked. Annotate descriptor tables (`local layouts: { VertexBufferLayout } =
  {...}`, `local depth: DepthStencilState = {...}`), or the literal's inferred string-union type
  fails the check.
- The depth format is `depth32float` (also `depth16unorm`, `depth24plus-stencil8`,
  `depth32float-stencil8`). `depth24plus` is not a texture format here.
- `VertexAttribute.slot` is the WGSL `@location`. One `GPUBuffer` per glTF attribute (one layout
  each) avoids interleaving.
- `UBOEntry`/`TextureEntry`/`SamplerEntry.slot` is the WGSL `@binding`. Lay uniforms out by hand:
  mat4 64 bytes, then vec4s at 16-byte steps. A wrong offset reads garbage silently.
- glTF is y-up and right-handed; `Mat4.perspective` and `Mat4.lookAt` are right-handed with depth 0
  to 1. Upload `proj * view * model` with `writeToBuffer`.
- Composite the GPU canvas with `renderer:transform(Mat2D.withScale(1/scale))` so a canvas sized in
  pixels lands at point size.
- Compute matrices in `advance`, not `draw`. Pointer handlers can run before the first draw.
- `Image:view()` on an `ImageAsset` samples all zeros (documented). Draw the image into a
  `context:canvas()` and sample that canvas's image.
- In the Screen artboard, the dot was hidden behind the card until it was declared FIRST (the first
  child draws on top).

### What it costs on iOS

The legacy `RiveViewModel` path does not run the GPU Canvas. GPU Canvas content needs
`Worker(configuration: .init(enableGPUCanvas: true))` with `File(source:worker:)` and `Rive(file:)`,
the Swift Concurrency API (rive-ios 6.25.0+). The setting is fixed for the worker's lifetime. A 3D
piece is therefore its own view on that API, not a new artboard in an existing `.riv` played by the
legacy path. Scripts and shaders must ship signed (`--publish`). Set `shaderOutputs: [msl]` in
`rive.yaml` for an Apple-only file.

## Fake 3D by projection (a chest that opens)

A streak-reward chest that opens, with coins flying out and settling, was built this way. Its camera
is ONE orthographic view (yaw 24, pitch 20). The result was 112 KB of pure vectors.

- **Under an orthographic camera every planar face projects by an exact 2D affine map.** Draw each
  face once, flat, in its own 2D coordinates (rounded rectangles, a heart lock, rivets, gradients).
  Place it with two nested `Node`s whose rotation / scale / rotation is that map's SVD
  (`np.linalg.svd(J)`). A swinging lid keys only those six numbers per sample, not vertices, so the
  hasp and lock stay in perspective in every frame.
- Curved parts (the lid's half cylinder) are the union of the two end caps plus the quad between
  their tangent points, with four keyed vertices. The outline is a stroke painted UNDER the fill, so
  the union has one clean outline.
- Straps over a curve are strokes along the arc, cut to the side facing you by a keyed `TrimPath`
  (start and end measured in screen length, the way Rive trims).
- **Depth order is computed once per pose:** faces sorted far to near, coins nearest first, emitted
  in reversed order because the first child draws on top.
- Coins are a nested artboard `Coin` (face, band and back, so it has a real edge) with a `Flip`
  timeline. Each instance's `NestedRemapAnimation.time` picks its angle: still on the heap, keyed
  linearly in flight. Flight arcs are exact parabolas (three keys with the `up`/`down` quadratic
  eases). Each coin lands face up, hops twice, wobbles, and has its own shadow.
- One authored timeline is sliced into the states (Fall, Wait, Shake, Open, Glow, Closed). The
  authored rest pose is the finished one, so an unplayed `Glow` shows the open chest. An env var that
  swaps the triggers for exit times lets the whole story render headless.
- The first review said: the lock is not positioned relative to the angle of the chest, the coins
  look flat, and the inside of the chest looks bad. Every planar part must live in its face's plane,
  and nothing may be a flat disc pretending to be a coin.

**Tradeoffs.** Fake 3D runs everywhere, ships with `--once`, and every face is a styleable vector.
But the camera is fixed and every motion is baked, so a spin or relight means regenerating. Real 3D
needs the GPU Canvas runtime, signing and a newer iOS API, but the model can turn, relight, take a
live screen and be tapped. For a fixed-angle hero moment, use projection. For anything the user
rotates, or a 3D surface with live UI, use the GPU Canvas. For a single hero object seen alone, a
properly modelled and textured mesh beats both ([quality-bar.md](quality-bar.md)).
