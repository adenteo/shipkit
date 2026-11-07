---
name: ship-store
description: Set up and submit an iOS app in App Store Connect through its API, for any app. Use when the user wants to create the App Store listing, register a bundle ID, upload screenshots, set categories, age rating, price, availability, regional or worldwide pricing (purchasing power bands), in-app purchases or subscriptions, Game Center leaderboards, App Review contact details, push a build to TestFlight, attach a build to a version, or submit for App Review. Also use for "ship to the App Store", "set up App Store Connect", "upload metadata", "TestFlight", "ASC API", "IAP setup", "subscription setup". Reads .ship/ship.json (written by the ship skill) and is idempotent.
---

# ship-store: App Store Connect from `ship.json`

One toolkit, `asc.py`, with a subcommand per job. It reads `.ship/ship.json` (contract in
`${CLAUDE_SKILL_DIR}/../ship/references/ship-json.md`), signs its own API tokens, and every
mutating command takes `--dry-run`. Run it as:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/asc.py" <command> [--ship .ship/ship.json] [--dry-run]
```

`--ship` defaults to `./.ship/ship.json`. Run from the app repo root.

## What the API cannot do (tell the user up front)

- **Create the app record.** Once per app, in the web UI (step 3 below). Everything else hangs off it.
- **Privacy nutrition labels.** Web only. Give the user the list from `store.privacyLabels`.
- **Attach the first in-app purchase or subscription to the first version.** Do it in the web UI on the version page ("In-App Purchases and Subscriptions"). The first product has to be reviewed together with the first app version; later ones can go on their own.
- **Accept agreements.** The Account Holder must accept the Paid Apps agreement before any paid product or paid app works. A 403 mentioning agreements means this.
- **Upload the binary.** That is `ship-build` (Xcode, `xcrun altool` or `eas submit`). This skill picks up after the build is uploaded.

## Safety rules

1. **Never send `submit` or `testflight --submit-beta-review` without the user's explicit go-ahead in chat.** Dry-run first, show the plan, ask, then run with `--confirm`. Submission to App Review is not undoable by us, and a bad submission burns days.
2. Run any command with `--dry-run` first on a new app. GETs are real, so the dry run shows the true diff against what is already in App Store Connect.
3. Never print, log or commit key values. Refer to keys by file path and variable name (`secrets.ascEnv`). The demo account password lives in an env var named by `store.review.demoPasswordEnv`; the scripts mask it.
4. Only touch the app in `ship.json`. `app.ascAppId` and `app.bundleId` are cross-checked on every run and the scripts refuse a mismatch.
5. Never use or suggest EAS Update or other over-the-air code pushes to dodge review.

## Credentials

The key (`.p8`) comes from App Store Connect, Users and Access, Integrations, App Store Connect API (a Team Key with App Manager or Admin role). The three values go in a `chmod 600` env file outside the repo:

```
ASC_KEY_ID=XXXXXXXXXX
ASC_ISSUER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
ASC_KEY_PATH=/absolute/path/AuthKey_XXXXXXXXXX.p8
```

Lookup order: `secrets.ascEnv` in ship.json, then those env vars, then `secrets.ascEnv` in `~/.config/shipkit/defaults.json`. If the key is missing, ask the user to create it and tell them where to save it; do not ask them to paste it. Signing uses `cryptography` if installed, else the `openssl` binary, so there is nothing to install.

Check it with `whoami`. It says whether an app record already exists for `app.bundleId`.

## Order of operations

Work through these in order; each is safe to re-run. Tick the line in `.ship/PROGRESS.md` as steps finish.

### 1. Preflight

Confirm `ship.json` has `app.bundleId`, `app.name`, `app.primaryLocale`, `app.marketingVersion`, a `listing` entry per locale, `site.urls.privacy` and `site.urls.support` (Apple requires both), and `store.review` contact fields. Fill what is missing by asking the user, and write it back. Then:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/asc.py" whoami
```

### 2. Register the bundle ID and capabilities

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/asc.py" bundle-id --dry-run   # then without --dry-run
```

Enables Game Center, push, Sign in with Apple and anything in `store.capabilities`, derived from `features`. The bundle ID must exist before the web UI lets you pick it. After capability changes the provisioning profile must be regenerated (Xcode automatic signing does this on the next build).

### 3. Create the app record (web UI, once)

Tell the user to open appstoreconnect.apple.com, My Apps, "+", New App, and type exactly:

| Field | Value from ship.json |
|---|---|
| Platforms | iOS |
| Name | `listing.<primaryLocale>.name` (max 30, must be unique on the whole App Store; try a variant if taken) |
| Primary Language | the language of `app.primaryLocale` (en-US is "English (U.S.)") |
| Bundle ID | `app.bundleId` (pick from the dropdown; appears after step 2) |
| SKU | `app.sku` (any unique string; defaults to the bundle ID) |
| User Access | Full Access |

Then run `whoami` again: it finds the app by bundle ID, and the next command saves `app.ascAppId` into ship.json. (Or have the user copy the number from the URL `.../apps/<id>/...`.)

### 4. Listing, age rating, price, review contact

```bash
asc.py listing --dry-run          # text, URLs, categories, copyright, content rights
asc.py age-rating --dry-run       # defaults to all NONE/false, overridden by store.ageRating
asc.py pricing --dry-run          # free or a USD tier, plus territory availability
asc.py review-details --dry-run   # contact, notes, demo account
```

`listing` checks limits first and aborts before sending anything: name and subtitle 30, keywords 100 (comma separated, no spaces after commas, no word that already appears in name or subtitle, because Apple indexes those for free), promo 170, description 4000. It also rejects en and em dashes. `whatsNew` is skipped on an app's first version because Apple rejects it there. Categories: a `GAMES_*` id is mapped to `GAMES` plus a subcategory automatically.

Age rating answers must be honest. `store.ageRating` holds overrides (for example `{"violenceCartoonOrFantasy": "INFREQUENT_OR_MILD"}`); ask the user about user generated content, web access, gambling and chat before accepting the all-clear defaults. See `references/api-notes.md` for field names.

If the app needs a demo account, set `store.review.demoAccountRequired`, `demoUser`, and export the password into the env var named in `demoPasswordEnv` before running `review-details`.

### 5. In-app purchases and subscriptions

Skip when `monetization.products` is empty.

```bash
asc.py products --dry-run [--only com.example.app.pro.monthly]
```

Creates the subscription group (name from `product.group`), products, localizations, availability in all territories, the USA price plus Apple's equalized prices for every other territory, an optional free trial, and the review screenshot (from `product.reviewScreenshot` or `.ship/screenshots/review/<productId>.png`, a flat PNG showing where the purchase appears in the app). An existing live price is never changed by the script. Read `references/api-notes.md` "Products" before debugging failures. Then remind the user of the web UI step: attach the first product to the version.

### 5b. World prices (optional, after products exist)

Apple's default is one USA price equalized everywhere, so India or Brazil pay a US price in local money. `world-prices` cuts prices in poorer markets in bands and always plans first:

```bash
asc.py world-prices                     # plan only: reads live prices, writes .ship/pricing/plan.md and plan.json
asc.py world-prices --only com.example.app.pro.annual --confirm --dry-run   # show the exact requests
asc.py world-prices --confirm           # send, only after a yes in chat
```

- **Models.** `gni` (default): band 2 (World Bank upper middle income, for example Brazil, Mexico, Turkey, China, Malaysia, Thailand) pays 0.6x the equalized price, band 3 (lower middle and low income plus the poorer upper middle markets, for example India, Indonesia, Vietnam, Philippines, Egypt, Nigeria, Pakistan, Ukraine) pays 0.3x; band 1 is left alone.
- **Never raises by default.** A territory already cheaper than its band (an app that set its own regional prices earlier) is left alone and reported as "already cheaper"; `--allow-increases` raises those too. If most territories come back "already cheaper", the app already has regional pricing: tell the user and leave it.
- **Order check.** Before sending, it refuses if rounding would make a cheaper product cost more than a dearer one anywhere (a monthly above an annual). `equalized` resets every territory to Apple's equalization of the base price and removes overrides. Overrides in ship.json: `monetization.priceModel`, `monetization.priceRatios` (`{"2": 0.6, "3": 0.3}`), `monetization.priceBands` (`{"POL": 2, "IND": 3}`).
- **How targets are picked.** For each band it takes the USA price point nearest base x ratio and uses Apple's own equalization of that point, so every target is a real local tier. Low base prices (0.99) land coarser because local tiers are sparse there; the plan shows each territory as a multiple of its equalized price.
- **Covers** the paid app price, every subscription and every IAP, read from App Store Connect (not ship.json). `--only <productId>` limits it; `--only app` is the app price.
- **Subscriber rule.** Subscriptions get one price per changed territory. Decreases pass to existing subscribers (`preserveCurrentPrice: false`); increases keep existing subscribers on their current price (`preserveCurrentPrice: true`), so no consent prompt is ever triggered. An approved subscription cannot change price immediately ("Initial price cannot be created again"), so its new prices are scheduled from tomorrow; a subscription still in setup takes them at once. A rerun skips territories already scheduled.
- **IAPs and the app price** get one new price schedule with the USA base, every band 2 and 3 territory, and any other manual prices carried over unchanged (a new schedule replaces all manual prices).
- **Show the user plan.md** and get a yes before `--confirm`. Changing prices touches revenue in about 110 territories at once. Point out the judgment calls: China, and high income Eastern EU markets that stay at full price unless moved. After sending, the command reads back three sample territories per product.

### 6. Screenshots

Screenshots come from `ship-screenshots` into `.ship/screenshots/<locale>/<display-type>/NN-name.png`. Folder names are API display types: `APP_IPHONE_67` (1320x2868 or 1290x2796, also the slot for 6.9 inch), `APP_IPHONE_65`, `APP_IPAD_PRO_3GEN_129` (2048x2732 or 2064x2752, required when `app.supportsIpad`). Aliases like `iphone69`, `iphone65`, `ipad13` also work. Files upload in filename order, PNG with no alpha, at most 10 per set.

```bash
asc.py screenshots --dry-run
```

Re-running skips sets whose checksums already match, and replaces a set that differs. The listing for each locale must exist first (step 4).

### 7. Game Center (games only)

Fill `store.gameCenter` (schema in `ship-json.md`), then `asc.py game-center --dry-run`. Creates the Game Center detail, leaderboards (including a daily recurring one), achievements with localizations and optional images, and enables Game Center on the version. Game Center items must be attached to the version in the web UI the first time.

### 8. Web UI leftovers

Walk the user through, with the exact answers derived from `features` and `store.privacyLabels`: App Privacy (data types collected, linked to user, used for tracking), the first IAP attachment, export compliance if the build lacks `ITSAppUsesNonExemptEncryption`, and the content rights question if `listing` changed it. Do not mark done until the user confirms.

### 9. TestFlight

After `ship-build` uploads a build:

```bash
asc.py testflight --dry-run [--build 12] [--notes "What to test"]
```

Fills beta app info and the Beta App Review contact, creates groups from `store.testflight.groups` (names starting with "Internal" or "Team" become internal groups that get every build automatically; others are external, with a public link if `publicLink` is true), waits for processing (up to `--timeout` minutes, default 60; `--no-wait` to skip), sets export compliance, sets "what to test", and attaches the build to external groups.

**Beta App Review is separate and needs the user's go-ahead in chat.** Only internal testers can install without it. When the user agrees: `asc.py testflight --submit-beta-review --confirm`.

### 10. Attach the build and submit

```bash
asc.py attach-build --dry-run
asc.py submit --dry-run          # prints the preflight checklist and the planned requests
```

Show the user the checklist output and the planned requests. Ask plainly: "Submit version X to App Review now?" Only on a clear yes in chat:

```bash
asc.py submit --confirm
```

`submit` refuses on blockers (no build, missing screenshots, no review contact, no price, no age rating) unless `--force`. It reuses an open review submission, adds the version as an item, and flips `submitted`. Afterwards run `status` and report the state (`WAITING_FOR_REVIEW`). Typical review is 24 to 48 hours; if rejected, write the guideline and message into `.ship/review/` and fix before resubmitting.

## Other commands

- `status`: read-only summary of app, versions, builds, IAPs, subscriptions, beta groups, review submissions, Game Center. Safe any time; use it to resume a half-finished setup.
- `world-prices`: regional price bands, see step 5b.
- `pull-listing`: copies the store's current listing (every locale, URLs, copyright, version) into ship.json. Run it first on an app that is already on the store, so edits start from the live text.
- `listing --locales de-DE,ja`: pushes only those locales' text (no categories, copyright or content rights). A live app's listing text only changes with its next version; adding a locale also needs that locale's screenshots before the version can be submitted (`screenshots`).
- `raw METHOD PATH [JSON]`: escape hatch for anything not covered. Mutating raw calls honor `--dry-run`.

## When something fails

Errors print the ASC error body. Look the code up in `references/api-notes.md` first (409 on create, price point not found, screenshot stuck in UPLOAD_COMPLETE, agreements 403). Fix the cause rather than retrying; every command is idempotent so re-running after a fix is safe. If a field name is rejected, Apple probably renamed it: check the current API reference or use `raw GET` on the resource to see the real attribute names.
