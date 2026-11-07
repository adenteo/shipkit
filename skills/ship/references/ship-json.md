# `.ship/` folder and `ship.json`

Every shipkit skill reads and writes one folder at the root of the app repo:

```
.ship/
  ship.json          the answers and IDs every step needs (schema below)
  PROGRESS.md        the checklist: one line per step, ticked as each finishes
  inspiration/       moodboards, icon concepts, screen ideas (from ship-images)
  assets/            final generated art before it is copied into the app
  screenshots/       raw simulator captures and rendered App Store images
  listing/           drafts of the App Store text, one file per locale
  review/            submission checklist, review notes, rejection log
  launch/            launch posts, preview video, press kit
```

Commit `.ship/` except `.ship/**/raw/` and anything large. **Never put a secret in it.**
`ship.json` stores *where* a key lives (a file path and a variable name), never the key.

## Personal defaults

Answers that are the same for every app (team ID, where your App Store Connect key
file lives, your support email, preferred stack, image backend) go in
`~/.config/shipkit/defaults.json`, using the same shape as `ship.json`. The `ship`
skill merges them in when it creates a new `ship.json`, so they never end up in a
public repo and you are not asked for them again.

## Fields

Unknown or not-yet-decided values stay as empty strings. A step that needs a value
that is still empty asks for it then, writes it back, and carries on.

### `app` (written by: ship intake)

| Key | Values | Notes |
|---|---|---|
| `name` | string | The product name, not the 30 character App Store name |
| `tagline` | string | One short line, used on the landing page and screenshots |
| `oneLiner` | string | What it does and for whom, in one sentence |
| `audience` | string | Who it is for, in plain words |
| `platforms` | `["ios"]`, `["ios","android"]` | Android steps are skipped unless listed |
| `stack` | `swiftui`, `uikit`, `expo`, `react-native`, `flutter`, `unknown` | Detected from the repo when code exists |
| `bundleId` | `com.example.app` | Must match the Xcode target / `app.json` |
| `sku` | string | Any unique string; defaults to the bundle ID |
| `teamId` | 10 char Apple team ID | From defaults if set |
| `ascAppId` | numeric string | Filled once the app record exists in App Store Connect |
| `marketingVersion` | `1.0.0` | The version users see |
| `primaryLocale` | `en-US` | |
| `isGame` | bool | Turns on Game Center and audio questions |

### `vibe` (written by: ship-images explore mode)

`direction` is a short name for the chosen look ("warm paper", "neon arcade").
`palette` holds hex colours, `fonts` holds family names that are free to use on the
web and in the app (Google Fonts or system). `references` lists image paths in
`.ship/inspiration/` the user picked. `avoid` lists things the user said no to.

### `features` (written by: ship intake)

| Key | Values |
|---|---|
| `payments` | `revenuecat`, `storekit`, `none` |
| `analytics` | `posthog`, `telemetrydeck`, `none` |
| `ads` | `admob`, `none` |
| `accounts` | `none`, `apple`, `apple+google`, `email`, `custom` |
| `gameCenter` | bool |
| `notifications` | `none`, `local`, `remote` |
| `audio` | bool (generated music and sound effects) |
| `localizations` | list of App Store locale codes (`localize.py locales` lists valid ones) |

### `images` (written by: ship intake, used by: ship-images)

| Key | Values | Notes |
|---|---|---|
| `backend` | `openai`, `codex`, `codex-herdr`, `none` | See ship-images for how each works |
| `model` | `gpt-image-2` (default) | OpenAI image model for the `openai` backend |
| `codexModel` | string or empty | Passed as `-m` to `codex exec` when the account needs it |
| `shipArt` | `true`, `false`, `null` | May generated images ship inside the app? `false` keeps them to inspiration only; `null` means ask |

### `secrets` (paths only)

Each value is `path/to/file.env:VARIABLE` or just a path when the file holds one
variable. Examples: `~/.config/myapp/asc.env` with `ASC_KEY_ID`, `ASC_ISSUER_ID`,
`ASC_KEY_PATH`; `~/.config/openai/openai.env:OPENAI_API_KEY`;
`~/.config/gemini/gemini.env:GEMINI_API_KEY` (`geminiEnv`, used by ship-localize).
Scripts load the file themselves. Never print a value.

The App Store Connect env file must define:

```
ASC_KEY_ID=XXXXXXXXXX
ASC_ISSUER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
ASC_KEY_PATH=/absolute/path/AuthKey_XXXXXXXXXX.p8
```

### `monetization` (written by: ship-payments)

`price` is `free` or a USD price tier like `0.99`. `products` lists what the app sells:

```json
{ "id": "com.example.app.pro.monthly", "type": "subscription", "name": "Pro Monthly",
  "price": "3.99", "period": "P1M", "group": "Pro", "trial": "P1W",
  "description": "Unlock everything", "entitlement": "pro" }
```

`type` is `subscription`, `consumable`, `non-consumable` or `non-renewing`.
`period` uses ISO 8601 (`P1W`, `P1M`, `P3M`, `P6M`, `P1Y`).

Worldwide pricing (read by ship-store `world-prices`):

| Key | Values | Notes |
|---|---|---|
| `priceModel` | `gni` (default), `equalized` | `gni` discounts lower-income markets in bands; `equalized` resets every territory to Apple's equalized price |
| `priceRatios` | `{"2": 0.6, "3": 0.3}` | Multiplier on the equalized local price per band; band 1 is always 1.0 |
| `priceBands` | `{"POL": 2, "IND": 3}` | Territory (ISO alpha-3) to band overrides on top of the built-in World Bank income bands |

The plan is written to `.ship/pricing/plan.json` and `plan.md`.

### `localize` (written by: ship-localize)

| Key | Values | Notes |
|---|---|---|
| `engine` | `claude` (default), `openai`, `gemini`, `codex` | Who translates. `claude` writes job files for Claude subagents |
| `model` | string | Model for `openai` (default `gpt-5.4-mini`) or `gemini` (default `gemini-3.5-flash`) |
| `keep` | list | Words never translated, beyond the app name and Apple product names (for example the paid tier's name) |
| `noDashes` | `true`, `false` | Reject translations that contain em or en dashes |
| `voice` | string | Tone for translators; defaults to `vibe.voice` or `vibe.words` |

Also read: `features.localizations` (target locales), `secrets.openaiEnv`,
`secrets.geminiEnv`, `images.codexModel` (for the `codex` engine). Work files live
in `.ship/localize/` (`jobs/`, `out/`).

### `build` (written by: ship-build)

| Key | Values | Notes |
|---|---|---|
| `scheme` | string | Xcode scheme to archive. Empty means first non-Pods, non-test scheme |
| `project` | path | `.xcworkspace` or `.xcodeproj` to build. Empty means detect |
| `lastBuildNumber` | numeric string | Written after each upload; ship-store `testflight` reads it |
| `lastVersion` | `1.0.0` | Marketing version of that upload |

ship-build also reads an optional `.ship/release-gate.sh` and `.ship/preflight-allow.txt`.

### `screenshots` (written by: ship-screenshots, read by: ship-store)

Optional defaults for rendering: `style` (`framed`, `fullbleed`, `hero`), `bgMode`
(`cycle`, `solid`), `frame` (hex). The real copy and ordering live in
`.ship/screenshots/plan.json`.

Folder layout, the contract between ship-screenshots and ship-store:

```
.ship/screenshots/
  raw/iphone/01-home.png        simulator captures, not committed
  raw/ipad/01-home.png
  plan.json                     copy, styles, order (headline/subline may be {locale: text}, see ship-localize)
  index.html                    contact sheet for review
  <locale>/<display-type>/01.png ... 10.png
```

`<locale>` is an App Store locale code from `features.localizations` (`en-US`, `ja`, ...).
`<display-type>` is the App Store Connect `screenshotDisplayType` and is exactly one of
`APP_IPHONE_67` (1320x2868 or 1290x2796, renders 1320x2868) or
`APP_IPAD_PRO_3GEN_129` (2064x2752). Files are numbered `01.png` upward, uploaded in
filename order, 1 to 10 per set, PNG, **no alpha channel**. ship-store uploads the
files in each `<locale>/<display-type>/` folder it finds.

### `site` (written by: ship-landing)

`kind` is `nextjs`, `static` or `none`; `dir` is where the site code lives;
`owner` is the legal name of the developer or company shown on the policies;
`urls` are the four public URLs App Store Connect asks for. Apple requires a
privacy policy URL and a support URL for every app.

### `store` (written by: ship-listing and ship-store)

`primaryCategory` / `secondaryCategory` use App Store Connect category IDs
(`GAMES_PUZZLE`, `PRODUCTIVITY`, `HEALTH_AND_FITNESS`, ...). `ageRating` holds the
questionnaire answers. `privacyLabels` lists the data types the app collects, worked
out from `features` by ship-listing (it cannot be set through the API; the user
clicks it in once with the list we give them). `review` holds the contact and notes
App Review sees.

### `listing` (written by: ship-listing)

One object per locale. Limits: `name` 30, `subtitle` 30, `keywords` 100 (comma
separated, no spaces after commas), `promotionalText` 170, `description` 4000,
`whatsNew` 4000. ship-listing checks them before anything is uploaded.

## PROGRESS.md

Plain markdown checklist. The `ship` skill creates it from the plan and each child
ticks its own line with the date and a short note:

```
- [x] intake (2026-11-07)
- [x] vibe: "warm paper" picked from 4 boards
- [ ] icon
...
```

When `ship` is run again it reads this file first and continues from the first
unticked line.

## Additions by ship-store

Added so the App Store Connect toolkit can run from `ship.json` alone. All optional.

| Field | Meaning |
|---|---|
| `app.supportsIpad` | bool. When true, `screenshots` insists on an iPad folder (`APP_IPAD_PRO_3GEN_129`) |
| `store.capabilities` | extra bundle ID capabilities beyond those implied by `features` (`ICLOUD`, `ASSOCIATED_DOMAINS`, ...) |
| `store.excludeTerritories` | territory codes to leave out (`["CHN"]`); `availability` may also be a list of allowed codes |
| `store.contentRights` | `DOES_NOT_USE_THIRD_PARTY_CONTENT` (default) or `USES_THIRD_PARTY_CONTENT` |
| `store.usesNonExemptEncryption` | bool, default false; set on builds that lack the Info.plist key |
| `store.testflight.publicLink` | bool; external groups get a public link when true |
| `store.testflight.betaReviewNotes` | notes for Beta App Review (defaults to `store.review.notes`) |
| `store.gameCenter` | `{ "leaderboards": [...], "achievements": [...] }`, see below |
| `monetization.products[]` extras | `displayName` (30 chars), `reviewNote`, `reviewScreenshot` (path), `level`, `familySharable`, `localizations` (`{locale: {name, description}}`) |
| `listing.<locale>` extras | `supportUrl`, `marketingUrl`, `privacyPolicyUrl` override `site.urls` for that locale |

`store.gameCenter.leaderboards[]`: `id` (vendor identifier), `name`, `formatter`
(`INTEGER`, `ELAPSED_TIME_CENTISECOND`, ...), `sort` (`ASC` or `DESC`), `submission`
(`BEST_SCORE` or `MOST_RECENT_SCORE`), `scoreMin`, `scoreMax`, `recurring` (`"daily"` or omit).
`store.gameCenter.achievements[]`: `id`, `name`, `points` (all together at most 1000),
`beforeDescription`, `afterDescription`, `hidden`, `repeatable`, `image` (path to a 1024 px PNG).
