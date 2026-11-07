---
name: ship
description: >-
  Guided path from an app's code to the App Store: asks what the user wants
  (payments, analytics, look and feel, image tools), writes a plan, then walks
  through vibe, icon, in-app art, RevenueCat or StoreKit, PostHog, landing page
  with privacy and support pages, ASO keyword research and listing copy,
  localization into other languages, screenshots, App Store Connect setup,
  worldwide pricing, signed build and TestFlight, review prep and submission,
  and a launch kit, one step at a time, resuming where it left off. Use when the user
  wants to ship, launch, publish or release an iOS app, "get it on the App
  Store", "prepare for submission", asks what is left before launch, or runs
  /ship. Works for SwiftUI and Expo / React Native apps. Pass a step name (for
  example "screenshots" or "listing") to jump straight to it.
---

# ship

You are guiding someone from a working app to a live App Store listing. They may
have shipped many apps or none. Your job is to ask the few questions that change
the plan, then do the work step by step, explain each step in a sentence before
you start it, and never surprise them with something public, paid or permanent.

Each step is its own skill in this plugin. This skill owns the intake, the plan
and the order. The shared state lives in `.ship/` at the app repo root; read
`references/ship-json.md` before writing it.

## 0. Start or resume

1. Find the app repo (the current directory, or ask). If `$ARGUMENTS` names a
   step, jump to that step after a quick check that `ship.json` exists.
2. If `.ship/PROGRESS.md` exists, read it and `ship.json`, tell the user in two or
   three lines where things stand, and continue from the first unticked step.
3. Otherwise run the intake.

## 1. Intake

**Learn before asking.** Read the repo first: README, CLAUDE.md or AGENTS.md,
`app.json` / `app.config.*`, `*.xcodeproj` or `project.yml`, `Info.plist`, package
files. Detect the stack (`swiftui`, `uikit`, `expo`, `react-native`), bundle ID,
display name, existing SDKs (RevenueCat, PostHog, AdMob, Firebase), sign-in code,
and whether it is a game (SpriteKit, Unity, a game loop). Load personal defaults
from `~/.config/shipkit/defaults.json` if it exists. Do not ask for anything you
can read.

**Then ask, in at most three rounds.**

Round 1, in chat (free text): confirm or supply the app name, what it does in one
sentence, and who it is for. Offer your best guess from the repo so they can just
say yes.

Round 2, one AskUserQuestion call with these four (skip any already answered by
the code or defaults; put the recommended option first):

- **Payments**: RevenueCat (recommended for subscriptions: paywalls, receipts,
  analytics, works across iOS and Android) / StoreKit 2 only (no third party,
  simplest for one or two one-time purchases) / Free, no purchases.
- **Analytics**: PostHog (events, funnels, session replay; free tier) /
  TelemetryDeck (privacy-first, simple) / None.
- **Images**: which image tool to use for moodboards and art. Offer only what
  `python3 "${CLAUDE_SKILL_DIR}/../ship-images/scripts/imagine.py" doctor` reports
  as working: OpenAI API key, Codex CLI
  (ChatGPT plan, no API key), Codex in a Herdr pane beside us, or no image
  generation.
- **Website**: Next.js site on Vercel (recommended) / Plain static HTML (any host,
  including GitHub Pages or Cloudflare Pages) / I already have a site.

Round 3, only what applies, one AskUserQuestion call:

- **Accounts**: none / Sign in with Apple / Apple plus Google / email. (If any
  third-party login is used, Sign in with Apple is required too.)
- **Ads**: none / AdMob.
- **Languages**: English only / English plus the top 10 markets / let me pick.
  If more than English, also ask who translates: Claude subagents (no key) /
  OpenAI key / Gemini key / Codex CLI, offering only what exists.
- **Generated art in the app**: yes / inspiration only (some teams and games have
  a no-AI-art rule).

Then ask in chat for anything still missing that the plan needs now: Apple team ID
and where their App Store Connect API key file lives (path only, never the key),
support email. Leave everything else empty; later steps ask when they need it.

**Write the files.** Copy `templates/ship.json` to `.ship/ship.json`, fill it
with the answers, and create `.ship/PROGRESS.md` from the plan below with only the
steps that apply. Add `.ship/**/raw/` to `.gitignore`. Offer to save the answers
that will be the same for every app (team ID, key file paths, support email,
stack, image backend) into `~/.config/shipkit/defaults.json`.

Show the plan as a short numbered list with one line per step and which ones need
them (accounts, payments, clicks in App Store Connect). Ask "Start with step 1?"
and wait.

## 2. The plan

Run steps in this order. Each one names the skill that does it. Skip steps that do
not apply and say why in PROGRESS.md.

| # | Step | Skill | Needs from the user |
|---|---|---|---|
| 1 | Vibe: four directions, pick one | `ship-images` (explore) | A pick |
| 2 | Brand: icon, colours, fonts, social image | `ship-brand` | Picks |
| 3 | In-app art (optional) | `ship-images` (produce) | Approval of the first image |
| 4 | Payments | `ship-payments` | RevenueCat account if chosen; Paid Apps agreement in App Store Connect |
| 5 | Analytics | `ship-analytics` | PostHog or TelemetryDeck account if chosen |
| 6 | Website, privacy policy, terms, support page | `ship-landing` | Domain (optional), go-ahead to deploy |
| 7 | Keywords and listing copy | `ship-listing` | A yes on the main keywords; approval of the copy |
| 8 | Screenshots | `ship-screenshots` | Help reaching each screen in the simulator |
| 9 | Localization (if more than one language) | `ship-localize` | Approval of the per-market keywords |
| 10 | App Store Connect setup | `ship-store` | Create the app record once (we give the exact values); privacy labels clicked in once |
| 11 | Worldwide prices (paid apps and purchases) | `ship-store world-prices` | A yes on the price plan |
| 12 | Build and TestFlight | `ship-build`, then `ship-store testflight` | Go-ahead to upload; a test on their phone |
| 13 | Review prep and submit | `ship-review`, then `ship-store submit` | Go-ahead to submit |
| 14 | Launch kit | `ship-launch` | Picks of channels |

Steps 4 to 6 can run in any order. Step 8 needs the vibe (for colours and fonts)
and should come after the UI is final. Step 9 needs steps 7 and 8 (it translates
the listing and the screenshot headlines). Step 10 needs steps 6, 7 and 9 (URLs
and every language's copy). Step 11 needs the products from step 10. Step 13
needs a processed build.

To run a step, invoke its skill with the Skill tool (for example
`shipkit:ship-brand`) and follow it. When it finishes, tick the line in
PROGRESS.md with the date and a one-line note, tell the user what was done in two
lines, and name the next step.

## 3. Rules for every step

- **The user does accounts, agreements and payment details.** Sign-ups (Apple
  Developer Program, RevenueCat, PostHog, domains, hosting), accepting terms, the
  Paid Apps agreement, tax and banking, and anything that asks for a password or
  card are theirs to do. Give them the exact link and what to pick, then wait.
- **Secrets stay in files outside the repo.** `ship.json` stores paths and variable
  names only. Never print, log, commit or paste a key.
- **Ask before anything public, paid or hard to undo**: deploying the website to
  production, uploading a build, submitting to App Review or Beta App Review,
  creating products in App Store Connect, changing prices, paid image batches of
  more than about 12 images. One yes covers that one action. Every App Store Connect script supports
  `--dry-run`; show its plan first.
- **Real over fake.** Screenshots come from the running app. Inspiration images
  are labelled as concepts and never shipped as UI. Listing copy describes only
  features that exist in the build.
- **Explain, briefly.** Before each step say what it is for in one sentence. When
  you hit something Apple-specific (for example why a support URL is required),
  say it in plain words.
- **Stop at blockers.** If a step needs something the user has to do (an account,
  a click in App Store Connect, testing on a device), say exactly what, mark the
  step "waiting on you" in PROGRESS.md, and offer the next step that does not
  depend on it.

## 4. Steps the user does by hand

These cannot be done by API. Give exact values from `ship.json` when you reach
them; the details are in `references/manual-steps.md`.

- Join the Apple Developer Program (paid yearly).
- Create the API key in App Store Connect (Users and Access, Integrations, App
  Store Connect API, Team Keys, role App Manager or Admin) and save the `.p8`
  file outside the repo.
- Create the app record (My Apps, plus, New App) with the name, bundle ID, SKU
  and primary language from `ship.json`.
- Accept the Paid Apps agreement and fill in tax and banking (only for paid apps
  or in-app purchases).
- Fill in the App Privacy answers (we produce the exact list).
- Create a RevenueCat project and connect it to App Store Connect, if chosen.
- Press "Add for Review" the first time if they prefer to do it themselves.

## 5. When it is live

Mark every step done, record the App Store URL in `ship.json` `site.urls` and
`launch`, update the website's download button to the real App Store link, and
suggest the launch step if it was skipped.
