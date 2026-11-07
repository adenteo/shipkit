---
name: lottie
description: Build small app animations as Lottie (bodymovin) JSON drawn in code with a standard-library Python kit, preview them headless (contact sheets, stills, video), and ship them with the right player per platform. Use when someone wants a loading, success, onboarding, empty-state or celebration animation as a .json Lottie, asks whether to use Lottie, Rive or native animation, needs a Lottie to be smaller or smoother, or asks how to play Lottie on iOS, React Native or the web without hurting performance.
---

# Lottie, drawn in code

A Lottie is a JSON file of shapes and keyframes. This skill draws them from Python (no After
Effects), previews them in a real renderer, and ships them with the cheapest player that works.
Everything bundled is standard library Python plus a small Node preview tool.

## Choose the tool first

| You need | Use |
|---|---|
| A one-off animation that plays and is done (success check, onboarding illustration, confetti, loading, an empty state) and has to run on iOS, Android and web from one file | **Lottie** |
| Something that reacts to input with states (a toggle, a button, a character that looks where you touch, data-driven colours) | **Rive** (`rive` skill) |
| A transition inside one platform's UI (a view fading, a list moving, a button press, a progress bar) | **Native animation** (SwiftUI, Compose, CSS). It costs no file, no player and no dependency |
| A sequence of real photos or video | Video (HEVC with alpha on Apple, WebM on the web), not Lottie |

Rules of thumb:

- If the animation has no state machine and fits in 300 x 300 units, Lottie wins on reach and size.
- If a designer will hand-edit it in After Effects, use their file. This kit is for code-drawn art that
  is regenerated, restyled by palette, and kept in git as a script.
- If the piece should feel alive at rest (idle life, touch reactions), it is Rive, not a Lottie loop.
- Do not ship a Lottie for something native does in three lines.

## Bundled files

- `${CLAUDE_SKILL_DIR}/scripts/lottie_kit.py`: the engine. Keyframes with named eases (`K`), shape
  items (`rc`, `el`, `fl`, `st`, `tm`, `tr`, `piece`, `G`), bezier paths (`bez`, `smooth`,
  `ellipse_path`, `rrect_path`, `heart`, `sparkle`, `flower`), an art kit (`blob`, `heart_art`,
  `sparkle_art`, `shadow`, `gloss`), a rich kit (`gfill` gradients, `glow`, `soft_shadow`, `rich`,
  `ring`, `rays`, `twinkle`, `confetti`, `draw_on`, `runner`, `sweep`), the composition (`Comp`), a
  validator, a speck detector, key pruning, and `write()`.
- `${CLAUDE_SKILL_DIR}/scripts/build.py`: `python3 build.py <example.py> ... --out <dir>`.
- `${CLAUDE_SKILL_DIR}/examples/`: `loading_heart.py` (a seamless loop), `sparkle_burst.py` (a one-shot
  that ends empty), `bell.py` (a loop with ring marks, heavier outline). Each defines `build()`
  returning a `Comp` and sets its own `Palette`. Copy one to start.
- `${CLAUDE_SKILL_DIR}/preview/`: `render.js` (contact sheets), `still.js` (one frame to a transparent
  PNG), `video.js` (an MP4 at the animation's own frame rate). Needs Node, a Chrome or Chromium, and
  `npm install` once in that folder. Set `CHROME_PATH` if Chrome is not in a standard place. `ffmpeg`
  is needed only for `video.js`.

## The build and preview loop

```bash
cd ${CLAUDE_SKILL_DIR}
python3 scripts/build.py examples/bell.py --out /tmp/lottie          # writes /tmp/lottie/bell.json
(cd preview && npm install --silent)                                 # once
node preview/render.js /tmp/lottie --out-dir /tmp/lottie/sheets       # a contact sheet per json
node preview/render.js /tmp/lottie/bell.json --frames 10,14,18 --size 300 --out /tmp/lottie/x.png
node preview/render.js /tmp/lottie/bell.json --bg '#FFFFFF'           # check on paper as well as on colour
node preview/still.js /tmp/lottie/bell.json 20 300 /tmp/lottie/still.png   # transparent still
node preview/video.js /tmp/lottie/bell.json --loops 2                 # MP4 in the current folder
```

1. Write or copy an animation file: `build()` returns a `Comp` (name, length in frames), `c.add(...)`
   adds layers back to front, each with keyed properties.
2. Build. The kit prints frames, seconds, size and layer count, plus any problem its validator finds
   (a group with two paths, a fill without its own path, a trim on a filled shape, an easing handle
   outside 0..1, bad key order, bad in/out points) and any "speck" (something drawn as a sliver of its
   own size for a frame).
3. **Render a sheet and LOOK at it.** Sheets are 12 evenly spaced frames, first to last inclusive: a
   loop's last cell must match its first. `render.js` exits non-zero if a file fails to load or draws
   nothing (lottie-web rejects some files silently).
4. Look at the one-shot's last frame (does it end empty or at rest as intended?) and at the key
   moments at full size (`--frames`, `--size 300`).
5. Check it small, at the size it ships (a 28 pt progress icon needs heavier lines than a 300 pt hero:
   `STYLE['ink'] = 1.3`).
6. Play it in the real player on a device before calling it done.

The final cell of a sheet is drawn at `op - 0.01`, because lottie-web hides a layer AT its out point
while lottie-ios keeps a layer whose op equals the composition's op visible through the last frame.

## Palette as parameters

Colours are chosen by ROLE, never by name in the animation code:

```python
from lottie_kit import *
use_palette(Palette(ink='#2B2B3A', hero='#FF6B81', alt='#FFB3BE', accent='#FFD166',
                    accent2='#FFB347', cool='#8FD0F0', shadow='#2E6C9A'))
```

`hero` is the brand colour, `alt` its light sibling, `accent` and `accent2` warm highlights, `ink`
the outline, `shadow` the ground shadow. Shades are derived (`shade_of`) unless you pass
`shades={'#hex': '#shade'}`. Restyling an animation is one `use_palette` call. Set
`STYLE['flat'] = True` for no gradients or rims at all.

## Rules that keep the engines happy

The kit enforces these; keep them if you hand-edit JSON.

- **One path per group, with its own fill and/or stroke.** Never rely on a parent group's fill or
  stroke: Core Animation draws each path as its own `CAShapeLayer` and rescales inherited strokes
  badly.
- **The outline stroke is listed before the fill** in a group (a `CAShapeLayer` always strokes on top).
- Trims only in stroke-only groups; dashes only static; no masks other than simple add masks, no
  mattes, effects, expressions, text, images or 3D. Gradient fills (linear and radial, with opacity
  stops) and add masks are fine.
- Springs and overshoots are **explicit keyframes**; easing handles stay inside 0..1 (the validator
  checks).
- Every shape transform carries `o` (lottie-web draws nothing without it); every trim carries `m`
  (lottie-ios's default parser needs it).
- **Flat shade without masks:** the base in the shade colour, the main colour as an inset copy on top
  (scaled toward an anchor), the outline over both. Several overlapping puffs get one silhouette
  outline by drawing every puff's outline first, then every puff's fill.
- Fade rings and pops IN over their first frames, and start scaled pops at zero. A ring born at 12
  percent size at full opacity shows as a stray dot for a frame (`tiny_visible` finds these).

## Size and frame rate

- **60 fps** for anything with a bounce, a snap or a spring. 30 fps reads as stutter on a bounce and
  saves little, because the cost is in the layers and keys, not the frame count. Use 30 only for slow
  ambient loops.
- **Canvas 300 x 300** for tiles, taller only when it must fill a screen. The canvas is a coordinate
  system, not pixels: players scale it, and a bigger canvas costs nothing but invites bigger shapes.
- **Budget: under 25 KB per animation, under 50 KB for a hero.** The kit helps: `prune` drops keys a
  curve does not need (within a hair at every frame), `compact` rounds geometry to 0.1 px and easing
  handles to 3 decimals, holds replace repeated values, defaults are omitted.
- Prefer fewer, larger shapes. Each extra layer is a layer the player composes every frame.
- **No blur, no heavy masks, no live shadows.** Make depth with gradient fills, radial glows and
  contact shadows drawn as a radial gradient (`soft_shadow`), not a blur.
- Keep durations short: 0.7 to 1.2 s for a feedback moment, 1.5 to 3 s for an onboarding loop. A
  celebration that runs longer than the screen it plays on is a bug.
- Loops must be seamless: first and last frame equal, and no beat that starts at frame 0 without having
  ended at the last frame.
- Check on at least two backgrounds (the app's colour and paper white).
- Haptics: put impact beats in the file as markers named `haptic:<kind>[@intensity]:<n>` with
  `Comp.beat(frame, 'heavy', 0.8)`; the app fires them as the animation plays, instead of guessing
  timings in code.

## Players per platform

| Platform | Player | Notes |
|---|---|---|
| iOS | **lottie-ios 4.x** (Swift Package `airbnb/lottie-spm`) | Use the default `.automatic` engine, which picks the **Core Animation engine** when the file is compatible: rendering moves off the main thread and costs near zero CPU. A file that breaks the rules above silently falls back to the main-thread engine. Check with `LottieConfiguration` and the compatibility report in debug builds. Use the default dictionary-based parser or `Codable`; both parse these files. |
| Android | **lottie-android** (`com.airbnb.android:lottie` or `lottie-compose`) | `LottieAnimation` in Compose. Enable `enableMergePathsForKitKatAndAbove` only if you use merge paths (this kit does not). Cache compositions. |
| React Native / Expo | **lottie-react-native** | Wraps lottie-ios and lottie-android, so the same file and the same Core Animation behaviour. Pass `source={require('./x.json')}`; `autoPlay`, `loop`, `progress` for scrubbing. Pause or unmount when off screen. |
| Web | **lottie-web light** (`lottie_light.min.js`, `lottie_light` build) | Use the SVG renderer. The light build drops expressions and effects this kit never uses, and is far smaller than the full player. |
| Web (avoid) | dotLottie (WASM) | The dotlottie WASM runtime was 718 KB: it hurt mobile largest contentful paint on a landing page by more than the animation was worth. Only reach for it when you need its state machines or `.lottie` compression at scale. |

## Web performance

- Load `lottie_light` **lazily**: dynamic `import()` or a script injected after the first paint, never
  in the critical path or in `<head>` as a blocking script. A hero Lottie is not above-the-fold
  content for the purpose of LCP: give the slot a fixed width and height, and put a static first frame
  (a PNG or inline SVG from `still.js`) in it so layout does not shift and there is something to paint
  while the player loads.
- Start playback with an `IntersectionObserver`; destroy or pause the instance when it leaves the
  viewport. Never leave off-screen animations running.
- Respect `prefers-reduced-motion`: show the still instead.
- Fetch the JSON with the same lazy trigger, and let the browser cache it; 10 to 25 KB gzips to a few
  KB.
- Use the SVG renderer for crisp scaling at small counts. For many instances on one page, or very
  heavy files, the canvas renderer is lighter, but it does not scale as crisply.
- A row in a long list should show a static still image and mount the player only when it is the one
  playing. A player builds its whole layer tree each time a lazy row comes back.

```js
// Lazy light player, with a still in place until it plays.
const el = document.querySelector('#hero-anim');
new IntersectionObserver(async ([e], io) => {
  if (!e.isIntersecting) return;
  io.disconnect();
  const [{ default: lottie }, data] = await Promise.all([
    import('lottie-web/build/player/lottie_light'),
    fetch('/anim/hero.json').then((r) => r.json()),
  ]);
  lottie.loadAnimation({ container: el, renderer: 'svg', loop: true, autoplay: true, animationData: data });
}).observe(el);
```

## iOS and React Native notes

- Pause every Lottie view you cannot see (behind a sheet, off-tab, in the background).
- A one-shot's best beat can play under a sheet's slide-in. Start it after the presentation (about
  0.35 s) or on appear of the content, not on appear of the container.
- For resting pictures (a list row's empty state), render a still with `still.js` and show an image:
  it costs nothing to scroll past.
- Verify by RECORDING the real screen and stepping the frames, not by trusting the sheet alone. The
  preview renders with lottie-web; the shipped renderer is lottie-ios or lottie-android.

## Writing a new animation (the order that works)

1. Describe the beats in frames at 60 fps: anticipation, action, settle, hold. Write the frame numbers
   down before writing keys.
2. Build the static art first (`blob`, `heart_art`, `sparkle_art`, your own `bez` paths) and render one
   still at full size. Fix the drawing before animating it.
3. Add motion per layer with `K((frame, value, ease), ...)`. Ease names: `lin`, `io`, `sine`, `out`,
   `out2`, `outq` (rising against gravity), `in`, `inq` (falling), `in2`. An ease shapes the move TO
   the next key. `pop(...)` writes overshoot, undershoot, settle keys.
4. Parent layers (`parent='name'`) for rigs: a swing about a pivot is a layer anchored at the pivot.
5. Squash and stretch conserve volume (scale x up 14 percent, y down about 14).
6. Build, sheet, look, adjust. Then check it small and on a second background.
