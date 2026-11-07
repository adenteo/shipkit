# Painted layers (a glass jar, built from rendered art)

Use this when vector shapes cannot reach a board's richness: glass, satin, soft painted light. The
worked example is a glass jar with a cork and paper notes. It went through three versions:

- v1 and v2 were vector shapes. The review: "still far from the reference".
- v3 is PAINTED: image-model renders of the picked board, cut into layers and laid in Rive as
  `Image`s, with all the motion still Rive.

The pipeline is four small scripts you write for your own object: one draws direction boards, one
renders the raw layers, one keys and splits them, and one writes `scene.rml` (with `uilib`) and
builds.

## 1. A board first, then renders that EDIT the board

- Draw four directions as image-model EDITs, with your app icon and a character render as style
  references, so the object lives in the app's world. Keep the boards out of git.
- Once a board is picked, every layer is an EDIT of that board with a fixed style paragraph
  prepended. Match it EXACTLY: same light direction, same outline, same palette. Layers drawn from
  text alone drift.
- Each render is ONE part alone, centred, filling about 70 to 85 percent of the canvas.
- **Background: one flat pure magenta `#FF00FF`**, no gradient, no ground shadow, and "no magenta
  anywhere inside the subject".
- Glass must be painted OPAQUE ("fully opaque paint: the magenta background must NEVER show
  through"). Transparency is made later, on purpose, from the cut. Never let the key decide it.
- Split what must move separately into separate renders:
  - the jar EMPTY (no cork, no notes);
  - the cork alone (state its proportions and angle);
  - twelve notes on one sheet in a 4 x 3 grid with "wide magenta gaps between them, none touching".

## 2. Key the magenta out properly

```python
alpha = 1 - clip((min(r, b) - g - 60) / 120, 0, 1)       # how far green climbed back
rgb   = (im - (1 - alpha) * [255, 0, 255]) / alpha        # un-mix the magenta spill
```

Then solidify: drop specks smaller than 3 percent of the largest blob, fill enclosed holes, force the
inside opaque (erode 2), and keep soft alpha only in a 2-pixel band at the edge (dilate 2). This is
spill removal, not a flood fill. Flood-filled alpha leaves a grey fringe, and cutting pictures up
with flood fill and inpainting is a rejected method. Every part is its own render on the key colour.

## 3. Split one render into BACK and FRONT layers

Anything that sits INSIDE the object (notes in the jar, the cork's plug in the neck) needs the object
both behind and in front of it.

- **back.webp**: the whole jar, opaque: the glass, inside wall, base, rims and ribbon. Inside the
  mouth, darken toward the back for when the cork is out.
- **front.webp**: only what must sit OVER the contents, as alpha:
  - the ribbon and bow, picked by HUE (warm pixels, `r - b > 14` and `r - g > 22`, with opening and
    closing passes and small blobs dropped);
  - the glass HIGHLIGHTS, picked as what is brighter than a 31-pixel median of the glass around it,
    turned into white light;
  - a faint VEIL of glass over the contents, stronger toward the walls (`0.10 + 0.22 * edge**3`), so
    they read as behind glass;
  - the rim's FRONT LIP.
- Composite the front as ribbon over highlight over (lip or veil).

## 4. Split the rim into a back lip and a front lip

The cork must sit IN the neck: behind the near edge of the rim, in front of the far edge.

- Measure the mouth ellipse on the render. Down the centre column, the dark lines are the ring's
  outer edge, the opening's top arc and its bottom arc. Across the opening's middle row, its two
  ends.
- The front lip is rim glass below the opening's lower arc, down to the rim's bottom plus a little
  neck. It goes into `front.webp`. It is slightly see-through (0.8 in its interior), so the cork's
  plug shows faintly behind it.
- **Nothing in front may cross the cork:** above the lip, in the rim, front keeps only the ribbon.
- Set the cork's centre so its plug's bottom sits a fixed number of units below the front arc.

## 5. Write the geometry, then place sprites from it

The cut script writes `art/geom.json` in the object's own units (say a width of 180). It records:

- every layer's size and offset;
- the mouth's y and half width, the lip y, rim top and bottom, neck half width, shoulder y, floor y;
- the inside's half width per height;
- each note's mean colour.

The generator places everything from those numbers, with no eyeballing:

- 36 note sprites (from the twelve) are laid by a pile layout. Each is tested wholly inside the glass
  against the inside half-width at its y, so none is ever clipped.
- The dropped note falls through the mouth and lands on the pile's top for that level.
- The flying note rises from the churning pile and leaves above the cork's seat.

## 6. Lay them in Rive

- The draw order, front first:
  1. sparkles;
  2. the note flying out;
  3. a glint;
  4. `front.webp`;
  5. the cork (behind the front lip);
  6. the note dropping in;
  7. the pile;
  8. `back.webp`;
  9. a feathered shadow.
- `<Image assetId=... scaleX=1/ppu>`, with `ImageAsset`s declared beside the artboards.
- **One art size per display density.** A `big` set at 2.7 px per unit for a 250 pt sheet at 3x, and a
  `small` set at 1 px per unit for a 92 pt card at 3x. Each is its own artboard. The same `Image`
  code scales by `1/ppu`, so the units never change.
- WebP q88, method 6. The whole art set is a few hundred KB.

## 7. The motion stays Rive

The state machine is `level` (0 to 7 buckets of how full, a fade between levels), `target`, `drop`,
`shake` and `twinkle`.

- Steady states are one-frame one-shots, and `twinkle` is fired by the app, so nothing draws at rest.
- Events are `h:land`, `h:lid`, `h:wobble`, `h:pop` and `h:out`.
- The cork pops off to the side on a shake. The notes churn. One note flies out and the app's card
  takes over from it.

## When NOT to paint

- Small UI pieces at 20 to 40 pt stay flat cel vector (`uilib.cel`). Painted detail turns to mush at
  that size, and vectors stay a few KB.
- Characters stay rigged vector plus mesh textures (outfits are textures skinned on a cloth mesh).
  Painted outfit images layered for sleeves cost 3 MB and still failed review.
- Forms that are an ellipse or a rounded blob should be a Rive shape at a measured box, not a drawing
  of one.
