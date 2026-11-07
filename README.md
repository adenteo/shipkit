# shipkit

A Claude Code plugin that walks an iOS app from working code to a live App Store
listing. It asks what you want (payments, analytics, look and feel, which image
tool you have), writes a plan, then does each step with you: brand, paywall,
website and policies, listing copy, screenshots, App Store Connect, signed
builds, TestFlight, review and launch. It picks up where it left off.

It does not write your app. Bring an app that runs; shipkit gets it shipped.

## Install

```
/plugin marketplace add adenteo/shipkit
/plugin install shipkit@shipkit
```

Then, in your app's repo: `/shipkit:ship`. To jump to one step:
`/shipkit:ship screenshots`.

## What it does

| Step | Skill | What you get |
|---|---|---|
| Intake and plan | `ship` | `.ship/ship.json` with your answers, `.ship/PROGRESS.md` checklist |
| Vibe | `ship-images` | Four moodboard directions to pick from, palette and fonts |
| Brand | `ship-brand` | App icon (checked against App Store rules, dark and tinted variants), colour and font tokens for Swift, CSS and TypeScript, favicons, social preview image |
| In-app art | `ship-images` | A consistent set of illustrations, badges or mascot poses, cut out and sized |
| Payments | `ship-payments` | RevenueCat (SwiftUI or Expo) or StoreKit 2, products and prices, paywall rules App Review checks |
| Analytics | `ship-analytics` | PostHog or TelemetryDeck, an event plan, privacy implications |
| Website | `ship-landing` | Landing page, privacy policy, terms and support pages written from what the app collects; deploy |
| Keywords and listing | `ship-listing` | Keywords scored for popularity, difficulty and opportunity with no paid ASO tool, rank tracking, name, subtitle, keyword field, description, App Privacy answers, review notes, lint |
| Screenshots | `ship-screenshots` | Real simulator captures rendered into designed screenshots at exact sizes, plus a contact sheet |
| Localization | `ship-localize` | The listing (with keywords per market), screenshot headlines and the app's own strings in up to 49 more languages, every one checked by machine for limits, placeholders, protected names, URLs and wrong script |
| App Store Connect | `ship-store` | Bundle ID, listing, categories, age rating, pricing, in-app purchases and subscriptions, screenshot upload, review details, TestFlight, submit; all idempotent with `--dry-run` |
| Worldwide prices | `ship-store world-prices` | Fair prices per country in income bands (World Bank groups), planned from Apple's own price points, applied only after a yes |
| Build | `ship-build` | Preflight checks, version bump, archive, export and upload with your API key (SwiftUI, UIKit, XcodeGen, CocoaPods, Expo, React Native) |
| Review | `ship-review` | A checklist of the guidelines that reject most apps, submission, and rejection handling |
| Launch | `ship-launch` | Preview and launch videos from the real app, press kit, launch post drafts, launch-day checklist |

## Images: use what you have

`ship-images` works with any of these, chosen at intake:

- **OpenAI API key**: `gpt-image-2` through the Images API, with reference-image
  edits for consistent sets.
- **Codex CLI** on a ChatGPT plan: no API key; each image is one `codex exec` run.
- **Codex in [Herdr](https://herdr.dev)**: if you run Claude Code inside Herdr,
  shipkit starts Codex in the pane next to Claude. You watch it work, can talk to
  it directly, and it keeps context across a set.

`imagine.py ask` also gets Codex's second opinion on names, taglines and designs.

Translations use the same idea: Claude subagents by default (no key), or an
OpenAI key, a Gemini key, or the Codex CLI.

## Requirements

- macOS with Xcode for building and screenshots; Python 3.9+; Google Chrome or
  Chromium (renders screenshots and social images)
- Pillow (`pip install Pillow`) for icon and image processing
- An Apple Developer Program membership and an App Store Connect API key
- Optional: `cryptography` (else `openssl` is used to sign API tokens), Node for
  Expo and Next.js, the Codex CLI, an OpenAI API key

## What stays with you

shipkit never signs up for anything, accepts agreements, enters passwords or
payment details, or publishes without asking. You create the accounts (Apple
Developer, RevenueCat, PostHog, hosting), create the app record once in App Store
Connect (shipkit gives you the exact values), click in the App Privacy answers it
prepares, and say yes before each upload, deploy or submission. Every App Store
Connect write can be previewed with `--dry-run`.

Keys never go in `ship.json` or the repo; it stores the path of an env file and
the variable name. Answers that are the same for every app (team ID, key file
path, support email, preferred stack and image tool) can live in
`~/.config/shipkit/defaults.json`.

## Layout

```
.claude-plugin/        plugin and marketplace manifests
skills/ship/           the guided parent: intake, plan, order, shared ship.json contract
skills/ship-*/         one skill per step, each with its own scripts and references
```

Every skill reads and writes `.ship/` in your app repo; the contract is
`skills/ship/references/ship-json.md`.

## License

MIT
