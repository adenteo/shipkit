---
name: ship-brand
description: >-
  Turn the chosen vibe into a shippable brand for an iOS app: the app icon
  (concepts, pick, final 1024px icon with dark and tinted variants, written into
  the Xcode asset catalog or Expo config), colour and font tokens for the app and
  the website, favicons and web manifest, and a 1200x630 social preview image.
  Validates App Store icon rules (size, no transparency, no drawn-in corners).
  Use when the user needs an app icon, logo, favicon, OG or link preview image,
  brand colours or fonts, or when the ship skill reaches its brand step.
---

# ship-brand

Needs `ship.json` `vibe` (palette and fonts). If it is empty, run the vibe step of
`ship-images` first, or ask the user for a palette and two fonts.

All outputs go to `.ship/brand/` first and are copied into the app and site at the
end. One script does the mechanical parts:

```bash
B="${CLAUDE_SKILL_DIR}/scripts/brand.py"   # needs Pillow
python3 "$B" check icon.png
python3 "$B" icon icon.png [--dark dark.png] [--tinted tinted.png] [--xcassets path] [--expo]
python3 "$B" web icon.png --out .ship/brand/web
python3 "$B" tokens --out .ship/brand
python3 "$B" og --icon icon.png --out .ship/brand/og.png
```

## 1. Icon concepts

A good icon is one simple idea, readable at 60 pixels, recognisable in a row of
other icons. Before generating, write six different symbol ideas (not six styles
of one idea): the core object, the core action, the result, a metaphor, a
letterform-free mascot, an abstract mark. Generate one concept each with
`ship-images` (see its prompts reference, "App icon concepts"), show them as a
contact sheet, and ask the user to pick one or two.

If generated images may not ship (`images.shipArt` is `false`), use the concepts
only as references and build the final icon as SVG or HTML (simple shapes,
gradients, the brand font), rendered at 1024x1024 with headless Chrome.

## 2. Final icon

1. Refine the pick: same idea, cleaner shapes, stronger silhouette, two or three
   colours from the palette, a background that fills the square edge to edge.
2. Run `check`. App Store icons must be exactly 1024x1024, fully opaque (no alpha),
   and square. iOS rounds the corners itself, so never draw rounded corners or a
   white border into the file.
3. Look at it small: resize to 60px and 120px and view them next to a few real app
   icons. If the idea disappears, simplify.
4. Optional variants for iOS 18 and later: a **dark** version (the symbol on a
   transparent or dark background) and a **tinted** version (a greyscale symbol
   that iOS colours). If you skip them, iOS derives its own.
5. Write it into the app with `icon`:
   - SwiftUI / Xcode: finds `AppIcon.appiconset` (or pass `--xcassets`) and writes a
     single-size 1024 icon plus variants with a correct `Contents.json`.
   - Expo: `--expo` writes `assets/images/icon.png` (and dark/tinted); set `icon`
     in `app.json` and, for variants, `ios.icon` with `light`, `dark`, `tinted`.
   Projects using Xcode's Icon Composer (`.icon` files with layers) can import the
   final PNG layers there instead.

## 3. Colour and font tokens

Run `tokens` to write `tokens.css` (website), `Theme.swift` (SwiftUI `Brand`
colours) and `theme.ts` (React Native) from the palette and fonts. Copy the one
the app needs into the app and use it everywhere instead of literal hex values.

Check contrast before committing: body text on `bg` and on `surface` should reach
4.5:1, large text 3:1. Adjust the palette in `ship.json` if it fails and rerun.

Fonts must be licensed for apps and the web. Google Fonts are (bundle the `.ttf`
files in the app and register them in Info.plist `UIAppFonts`, or with
`expo-font`). If the user picked a paid font, ask whether they own an app licence.

## 4. Web icons and social preview

- `web` writes `favicon.ico`, `apple-touch-icon.png`, 16/32/192/512 PNGs and
  `site.webmanifest` to `.ship/brand/web/`; ship-landing copies them into the site.
- `og` renders a 1200x630 image with the icon, name and tagline in the brand fonts
  for link previews (X, iMessage, Slack, LinkedIn). Look at it; tweak `--title`
  or `--tagline` if the text wraps badly.

## 5. Finish

Update `ship.json` `vibe` if anything changed, list the files written, and tick the
brand line in `.ship/PROGRESS.md`.
