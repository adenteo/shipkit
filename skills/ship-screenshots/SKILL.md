---
name: ship-screenshots
description: Capture real simulator screens and render designed App Store screenshots (headline, brand colours, device frame) at exact App Store sizes with no alpha, plus a contact sheet for review. Use when the user wants App Store screenshots, store images, a screenshot set, marketing screenshots for iPhone or iPad, or to refresh screenshots after a UI change. Never uses fake or AI-drawn app UI.
---

# ship-screenshots

Goal: 5 to 8 screenshots per device size that look designed, built from **real app
screens**. Upload is `ship-store`'s job (`asc.py screenshots`); this skill produces the
files in the agreed folder layout.

Reads `./.ship/ship.json`: `app.oneLiner`, `app.tagline`, `app.name`, `vibe.palette`,
`vibe.fonts`, `features.localizations`, `app.primaryLocale`. Missing vibe values fall
back to a neutral palette and the system font; say so and offer to run `ship-images`
explore mode first if the user wants a stronger look.

## Rules

1. **Real screens only.** Every screenshot shows a genuine capture of the running app.
   Never draw, mock up, or generate UI. App Review rejects screenshots that misrepresent
   the app, and it is the honest thing to do. Marketing copy and backgrounds around a real
   screen are fine.
2. Show the app in a good state: realistic data, no empty lists, no debug banners, no
   test names, no keyboard open by accident. Seed demo data if needed.
3. No claims you cannot prove (rankings, "free forever", prices, awards).
4. Do not write an alpha channel. `render.py` flattens and verifies every file.

## Sizes and folders

| Device | Capture | Final size | Folder name (display type) |
|---|---|---|---|
| iPhone 6.9 inch (Pro Max class) | 1320x2868 | 1320x2868 | `APP_IPHONE_67` |
| iPad 13 inch | 2064x2752 | 2064x2752 | `APP_IPAD_PRO_3GEN_129` |

iPad is only needed if the app supports iPad (`TARGETED_DEVICE_FAMILY` includes 2, or
`app.supportsIpad`). App Store Connect scales the 6.9 inch set down for smaller iPhones.

```
.ship/screenshots/
  raw/iphone/01-home.png    captures (same file names in raw/ipad/)
  plan.json                 copy, styles, order
  <locale>/APP_IPHONE_67/01.png ... 
  <locale>/APP_IPAD_PRO_3GEN_129/01.png ...
  index.html                contact sheet
```

Add `.ship/screenshots/raw/` and `.ship/screenshots/_html/` to `.gitignore`.

## Steps

### 1. Plan the story first (before capturing)

Pick 5 to 8 screens. **The first two carry the store page** because most people never
swipe, so put the core value moment first and the strongest differentiator second. Then
the supporting features, and last a trust or reward screen. Write for each: the screen to
capture, the headline, an optional subline.

Headlines: 3 to 6 words, benefit not feature, one idea each. Derive from
`app.oneLiner` and the listing; keep the voice of `app.tagline`. Mark an accent phrase
with `*stars*`. Examples: "Never miss a refill", "Plan the trip *together*", "Scan.
Split. *Done.*" Show the list to the user and get a yes before capturing.

### 2. Capture

```bash
"${CLAUDE_SKILL_DIR}/scripts/capture.sh" boot iphone        # Pro Max class sim, status bar 9:41, full battery and signal
"${CLAUDE_SKILL_DIR}/scripts/capture.sh" install path/to/App.app   # if not installed (built for the simulator)
"${CLAUDE_SKILL_DIR}/scripts/capture.sh" launch com.example.app [--demo-mode]
"${CLAUDE_SKILL_DIR}/scripts/capture.sh" open "myapp://some/screen"
"${CLAUDE_SKILL_DIR}/scripts/capture.sh" shot 01-home iphone
```

Ways to reach each screen, best first: a launch argument or deep link the app already
supports (look in the code for `URL scheme`, `onOpenURL`, `CommandLine.arguments`); a
debug seed (add one temporarily if cheap, remove it after); or ask the user to tap to
the screen in the Simulator window and say "shot", then you run `shot`. Name files
`NN-name` in story order. Use the same names for `iphone` and `ipad`.
If the app is not built for the simulator yet, build it:
`xcodebuild -scheme <scheme> -destination 'platform=iOS Simulator,name=<device>' -derivedDataPath build/sim build`
(or `npx expo run:ios`).

After each shot open the PNG with the Read tool and check it: right screen, clean
status bar, no overlays, sensible data. Retake rather than excuse. For dark mode
variants use `capture.sh appearance dark`. If the user already has good simulator
screenshots, copy them into `raw/iphone/` instead; they must be portrait and the right
device class (6.9 inch, 1320x2868 or close).

For iPad repeat with `capture.sh boot ipad`, same file names.

### 3. Plan file

```bash
"${CLAUDE_SKILL_DIR}/scripts/render.py" --init
```

Then edit `.ship/screenshots/plan.json`: set headlines, sublines, order, styles. Format
and every option in `references/plan.md`. Choose a layout style:

| Style | Look | Use when |
|---|---|---|
| `framed` | headline on colour, screen in a CSS device frame bleeding off the bottom | default, any app |
| `fullbleed` | real screen fills the canvas, colour caption band | art-heavy screens (games, photos, maps) |
| `hero` | two screens overlapping and tilted (needs `raw2`) | slide 1 or 2, to show breadth |

Mix styles lightly: one style for most slides with `hero` on slide 1 or 2 is a good
default. Colours cycle through the palette; set `"bgMode": "solid"` for one flat brand
colour, or a per-slide `bg`.

### 4. Render and verify

```bash
"${CLAUDE_SKILL_DIR}/scripts/render.py"                    # all slides, locales, devices that have raws
"${CLAUDE_SKILL_DIR}/scripts/render.py" --only 2,3 --display iphone
```

It uses headless Chrome (auto-detected on macOS and Linux; `--chrome` or `CHROME=` to
override) at the exact pixel size, strips alpha, then checks every PNG for exact
dimensions and no alpha. Output goes to `.ship/screenshots/<locale>/<display-type>/NN.png`
and a contact sheet to `.ship/screenshots/index.html`. Exit code 1 means a file failed
verification.

**Look at the results.** Open 2 or 3 finals (always slide 1) with the Read tool and
check: headline not clipped or crammed (the page auto-shrinks long text, but a very long
headline still looks bad: shorten it), enough margin, readable contrast, the app screen
not hidden by a caption band, accent word visible. Fix the plan and re-render. Then open
`index.html` for the user (`open .ship/screenshots/index.html`) and ask for approval.

### 5. Localized sets

Add `features.localizations` locales and make `headline` an object keyed by locale (see
`references/plan.md`). Re-render; each locale gets its own folder. Translate headlines
so they say the same benefit, not word for word, and keep them short. If localizing the
captured UI too, capture raws per locale into `raw/iphone/` under locale-specific names
and point the plan at them; most apps just localize the captions.

### 6. Hand off

Tick the line in `.ship/PROGRESS.md` with counts per device. Tell the user the next
step is `ship-store`: `asc.py screenshots --dry-run`, then the real upload (it needs
their go-ahead).

## Troubleshooting

| Problem | Fix |
|---|---|
| Render fails, "Chrome not found" | install Chrome or Chromium, or `--chrome /path` |
| Wrong font | the font loads from Google Fonts; check spelling and internet, or install it locally |
| Output not exactly sized | rerun; `--keep-html` keeps `_html/` pages to debug in a browser |
| Raw is not 1320x2868 | other phones scale to fit but look softer; recapture on a Pro Max class simulator |
| Status bar not 9:41 | `capture.sh shot` re-applies it; restart the sim if overrides stick (`capture.sh clean`) |
| App shows a permission prompt | pre-grant: `xcrun simctl privacy booted grant all <bundle-id>` |

## Done when

Each device folder holds 5 to 8 verified PNGs, `index.html` is approved by the user, raws
are kept in `raw/`, and PROGRESS.md is ticked.
