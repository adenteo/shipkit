---
name: ship-localize
description: >-
  Localize an iOS app into many languages at once: the App Store listing (name,
  subtitle, keywords researched per market, description), the screenshot
  headlines, and the app's own strings (String Catalog, .strings, or Expo /
  React Native i18n JSON), then check every language by machine for limits,
  placeholders, protected names, URLs, wrong script and untranslated text. Uses
  Claude subagents by default, or an OpenAI key, a Gemini key, or the Codex CLI.
  Use when the user wants to localize, translate, go international, add
  languages, "make it work in Japan", or when the ship skill reaches its
  localization step.
---

# ship-localize

Three things get localized, in this order, all from `ship.json`:

1. **The listing**: what people see and search in the App Store. Highest value.
2. **Screenshot headlines**: the words over the screenshots, in the same
   vocabulary the listing ranks for.
3. **The app's strings**: so a German who installs it is not met by English.

```bash
Z="${CLAUDE_SKILL_DIR}/scripts/localize.py"
python3 "$Z" locales [--preset top|europe|asia|all] [--set]
python3 "$Z" listing   [--locales de-DE,ja] [--engine claude|openai|gemini|codex] [--force]
python3 "$Z" headlines [--locales ...] [--engine ...]
python3 "$Z" strings   [--locales ...] [--engine ...] [--catalog PATH]
python3 "$Z" apply listing|headlines|strings     # after Claude subagents answered
python3 "$Z" check
```

## 0. Choose languages and engine, once

Ask once with AskUserQuestion, then save, and never ask again in later steps:

- **Languages**: Top 10 markets (recommended: `top` = German, French, Spanish
  for Spain and Mexico, Brazilian Portuguese, Italian, Japanese, Korean,
  Simplified Chinese, Dutch) / Europe / Asia / All 49 / let me pick.
  `locales --preset top --set` writes `features.localizations`.
- **Engine**: Claude subagents (default, no key, uses their Claude plan) /
  OpenAI key / Gemini key / Codex CLI on a ChatGPT plan. Save in
  `ship.json` `localize.engine`. Offer only what exists: an `openaiEnv` or
  `geminiEnv` secret, or `codex` on the PATH.

Also settle, from the vibe and the user's house rules: `localize.keep` (words
never translated beyond the app name and Apple's product names, for example the
paid tier's name), `localize.noDashes` (true if their style bans em and en
dashes), `localize.voice` (defaults to the vibe's words).

## 1. Listing

Needs the source listing in `listing.<primaryLocale>` (ship-listing).

1. **Research per market, not per translation.** For each big market, score the
   local terms people type: `listing.py keywords "<local terms>" --country de`
   (ship-listing). Germans search "kalorienzähler", not a translation of
   "calorie counter". `listing` feeds these scores to the translator
   automatically when `.ship/listing/keywords.<country>.json` exists.
2. `listing` translates every locale that has no listing yet. Over-long fields
   are retried with the exact overflow named. Each locale is saved to
   `listing.<locale>` only if it passes the checks.
3. After translating, score the keywords it chose in that storefront and swap
   weak ones (popularity at the floor, or irrelevant). Keywords are the one field
   where a fluent answer can still be wrong.
4. Show the user a table: locale, name, subtitle, keywords. Push later with
   `ship-store listing --locales <new ones> --dry-run`, then for real after a yes.

**Getting it live.** For an app already on the store, start with
`ship-store pull-listing` so the source is the live text. A live app's name,
subtitle, keywords and description only change with its next version, so new
languages ride along with the next update. Every new locale needs its own
screenshots before that version can be submitted (App Store Connect does not
fall back to the primary language's screenshots for a locale added by the API):
render them per locale with the translated headlines (step 2) and upload with
`ship-store screenshots`. Do not add locales to a version someone else is about to
submit without telling them.

## 2. Screenshot headlines

`headlines` translates every `headline` and `subline` in
`.ship/screenshots/plan.json` into the `{ "en-US": "...", "ja": "..." }` form
and adds the locales to `plan.locales`. Keep `*accent*` pairs and `\n` breaks;
the checks flag both. Then render with ship-screenshots (`render.py`); on macOS
Chrome falls back to the system fonts for Japanese, Chinese, Korean, Arabic,
Hebrew, Thai and Indic scripts. Look at the contact sheet for any locale whose
headline had to shrink and tighten that one by hand.

Only the headline is localized; the app screen inside stays as captured. If the
app's strings are localized too, capture each locale's screens in that
language for full marks: `capture.sh launch <bundle-id> -AppleLanguages "(de)"
-AppleLocale de_DE`, saving raws per locale.

## 3. The app's strings

`strings` finds the catalog itself: `Localizable.xcstrings` (SwiftUI), an i18n
JSON file such as `locales/en.json` (Expo, React Native, i18next), or
`en.lproj/Localizable.strings`. Only missing strings are sent, so reruns after
new UI copy cost one small batch, and a human fix is never overwritten.

- **Rejected, never shipped**: a changed placeholder set (`%@`, `%lld`,
  `{{count}}`; a dropped one crashes or lies), a lost protected word or URL, the
  wrong script, a banned dash. Rejected strings stay in the source language.
- **Plural and device variations** in a String Catalog are skipped and listed;
  do those by hand in Xcode.
- **Widgets and extensions** read their own bundle. If the app has a second
  catalog for a widget, translate it too or copy the main one into it, or the
  widget stays in English on a German phone.
- Build and run once in a translated language before calling it done:
  truncated buttons and clipped labels only show on screen.

**Not set up for localization yet?**
- SwiftUI: `Text("literal")` is already localizable. Add a String Catalog
  (`Localizable.xcstrings`) to the app target, build once so Xcode extracts the
  keys, and turn string-returning helpers into `String(localized:)`. For Swift
  packages, set `defaultLocalization: "en"` or the catalog is silently ignored.
- Expo / React Native: `expo-localization` plus `i18n-js` or `i18next`, one
  `locales/<lang>.json` per language, every visible literal through `t()`.
- Add the languages to the Xcode project's Localizations (or
  `CFBundleLocalizations` / `ios.infoPlist` in app.json) so iOS offers them.
Ask before a bootstrap: it touches many files.

## 4. Claude subagents engine

With `engine: claude` the script cannot call Claude itself, so it writes job
files instead (`.ship/localize/jobs/*.json`). Spawn subagents, a few job files
each, with this brief: "Read each job file. Follow its `instructions` on its
`input`. Write only the JSON answer (`expect` says the shape) to
`write_answer_to`. No commentary." Then run `apply <kind>`, which runs the same
checks and merges. Re-run `apply` after re-doing any locale it reports missing.

## 5. Check and report

`check` runs every detector over the listing, the headlines and the String
Catalog (coverage per language, plus failures). Fix every FAIL. Report to the
user: languages done, strings translated, anything left in English and why, and
which keyword choices are data-backed versus judgment calls.

Tick the localization line in `.ship/PROGRESS.md`.
