# plan.json reference

`.ship/screenshots/plan.json` drives `render.py`. `render.py --init` writes a starter from
the raws it finds. All colours are hex.

```json
{
  "style": "framed",
  "bgMode": "cycle",
  "frame": "#101114",
  "captionPos": "bottom",
  "palette": { "primary": "#ff5fa2" },
  "fonts": { "display": "Lilita One", "body": "Nunito" },
  "locales": ["en-US"],
  "slides": [
    { "raw": "01-play", "headline": "Slash four.\n*Watch them fall.*", "subline": "One swipe clears a group" },
    { "raw": "02-daily", "style": "hero", "raw2": "01-play", "headline": "A new wall *every day*" },
    { "raw": "03-win", "style": "fullbleed", "headline": "Cash it in", "bg": "#3b1d8f,#24106a" }
  ]
}
```

| Key | Meaning |
|---|---|
| `style` | `framed` (default), `fullbleed`, `hero`. Per slide or plan-wide. Defaults also read from `ship.json screenshots.style` |
| `bgMode` | `cycle` (slides step through primary, accent, bg, surface) or `solid` (all primary) |
| `frame` | device bezel colour. Dark `#101114` suits most; use a light frame on dark backgrounds only if it reads |
| `palette`, `fonts` | override `vibe.palette` and `vibe.fonts` from ship.json |
| `locales` | default is `features.localizations` |
| slide `raw` | file name in `raw/iphone/` (and `raw/ipad/`) without `.png` |
| slide `raw2` | second screen for `hero` |
| slide `headline` | string, or `{ "en-US": "...", "ja": "..." }`. `*word*` becomes the accent colour. `\n` breaks a line |
| slide `subline` | optional, same shape as headline |
| slide `bg` | `"#hex"` or `"#hex1,#hex2"` gradient, overrides the cycle |
| slide `captionPos` | `fullbleed` only: `bottom` (default) or `top` |
| slide `shotPosition` | `fullbleed` only: CSS `object-position`, default `50% 0%` |
| slide `textColor` | forced text colour; otherwise auto-picked for contrast 4.5 or better |

A slide whose raw is missing for a device is skipped for that device, so iPad can have
fewer slides than iPhone. Output numbering follows the slide position in the plan.

## Styles

- **framed**: headline on a colour field, real screen inside a CSS device frame that
  bleeds off the bottom edge. Safest default; works for every app.
- **fullbleed**: the real screen fills the canvas, a colour band carries the caption.
  Use for screens with rich art (games, photos) where a frame would shrink it. The band
  covers about 20 percent of the screen, so choose raws whose bottom (or top, with
  `captionPos: top`) is not the point.
- **hero**: two screens overlapping, tilted. Use for slide 1 or 2 to show breadth.

## Fonts

Fonts load from Google Fonts at render time (needs internet). A font installed on the
Mac works offline by name. If a family is missing, the system font stack is used and the
output still renders; check the contact sheet.

## Copy rules

Benefit, not feature: "Never miss a refill", not "Reminder system". 3 to 6 words. One idea
per screenshot. Lead with the outcome the user wants; the first two screenshots carry the
store page (most people never swipe). Never put prices, rankings ("#1") or claims you
cannot prove on a screenshot; App Review rejects them.
