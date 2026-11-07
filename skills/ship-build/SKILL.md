---
name: ship-build
description: Turn an app repo into a signed build uploaded to App Store Connect, for SwiftUI, UIKit, XcodeGen, CocoaPods, Expo and React Native apps. Runs a preflight (icon, permission strings, privacy manifest, export compliance, test ad IDs, version), bumps version and build number, archives, exports and uploads with the team App Store Connect API key (no Apple ID password). Use when the user wants to build, archive, upload to TestFlight or App Store Connect, bump a build number, or check an app is ready to ship.
---

# ship-build

Goal: a signed build sitting in App Store Connect, and its build number handed to
`ship-store`'s `testflight` step. This skill produces the build; `ship-store` owns
metadata, IAPs, screenshot upload, TestFlight groups and submission. Do not do those here.

State lives in `./.ship/ship.json` (contract: `../ship/references/ship-json.md`).

## Rules (read first)

1. **Every change goes out as a proper store build.** Never use EAS Update, CodePush or
   any over-the-air JS update as a substitute. It can get the app rejected or the account
   flagged, and users would run code App Review never saw.
2. **Prefer local builds** (this skill's `release.sh`). `eas build --local` and
   `eas submit` are acceptable for Expo users who want them; see `references/stacks.md`.
3. **Uploading needs a go-ahead in chat the first time per session.** Build and export
   freely; run with `--upload` only after the user says yes to this specific upload.
   `release.sh` does not upload unless you pass `--upload`.
4. **Never print, log or commit a key.** Refer to the env file by path and the variables
   by name. Do not paste key values into ship.json, PROGRESS.md or messages.
5. No Apple ID or app-specific password. Signing and upload use the API key only.

## Inputs to check before starting

Read ship.json. Needed: `app.bundleId`, `app.teamId`, `app.marketingVersion`,
`secrets.ascEnv`. If one is empty, ask the user once, write it back, carry on. The env
file at `secrets.ascEnv` (else `~/.config/shipkit/defaults.json`) must define
`ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_PATH` (absolute path to the `.p8`, chmod 600,
outside the repo). If the user has no key: App Store Connect > Users and Access >
Integrations > App Store Connect API > Team Keys > generate with **App Manager** role
(or Admin); the `.p8` downloads once. Walk them through it, then store it as above.

The app record must exist in App Store Connect with the same bundle ID before the first
upload (ship-store creates it, or the user does in the web UI).

Optional ship.json fields this skill reads (all additive, empty means auto-detect):
`build.scheme`, `build.project` (path to `.xcworkspace` or `.xcodeproj`). It writes
`build.lastBuildNumber` and `build.lastVersion` after an upload.

## Steps

### 1. Detect the stack

```bash
"${CLAUDE_SKILL_DIR}/scripts/detect-stack.sh" .
```

| STACK | What release.sh does |
|---|---|
| `xcodeproj` / `workspace` | `pod install` if a Podfile exists, then archive |
| `xcodegen` | `xcodegen generate`, then archive |
| `expo` | writes version and buildNumber into `app.json`, `npx expo prebuild --platform ios` (with `--clean` only when `ios/` is gitignored), `pod install`, archive |
| `react-native` | `pod install` in `ios/`, archive |
| `flutter` | manual, see `references/stacks.md` (the script prints the commands and stops) |

Record the stack in `app.stack` if it was `unknown`.

### 2. Preflight

```bash
"${CLAUDE_SKILL_DIR}/scripts/preflight.py" --repo . --ship ./.ship/ship.json
```

Prints a PASS / WARN / FAIL / SKIP table and exits 1 on any FAIL. It checks: 1024 icon
exists and has no alpha, a usage-description string for every permission API the code
uses, `PrivacyInfo.xcprivacy` and its required-reason entries, `ITSAppUsesNonExemptEncryption`,
bundle ID matches ship.json, deployment target, test ad IDs and test keys left in the
repo (AdMob `ca-app-pub-3940256099942544`, Stripe test keys, committed `.p8` files,
localhost URLs), and that the version is above the live one (read-only App Store
Connect call; `--offline` skips it).

Fix every FAIL before archiving: the fix is usually one line in Info.plist,
`app.json` or the asset catalog. Show the user the table and the fixes you made. WARN
rows are judgement calls; mention them, do not block. A heuristic false positive can be
silenced with a regex line in `.ship/preflight-allow.txt`. Details in
`references/preflight.md`.

Why a script and not "just archive": most rejections and stalled uploads (missing
purpose string, alpha icon, no privacy manifest, export compliance question) are known
before Xcode runs, and an archive takes minutes.

### 3. Optional release gate

If the app has developer-only switches (debug menus, free-unlock flags, test servers),
put an executable `.ship/release-gate.sh` in the repo. `release.sh` runs it as
`config`, `archive <path>` and `ipa <path>` and aborts on non-zero exit. Write it to
fail when a dev flag is on in the compiled output (grep the built `Info.plist` and the
JS bundle). A public build must never carry a dev switch. See `references/preflight.md`.

### 4. Build

Dry-run first, so the user sees exactly what will run:

```bash
"${CLAUDE_SKILL_DIR}/scripts/release.sh" --dry-run --upload
```

Then build without uploading:

```bash
"${CLAUDE_SKILL_DIR}/scripts/release.sh"                # version from ship.json, build = last uploaded + 1
"${CLAUDE_SKILL_DIR}/scripts/release.sh" --version 1.1.0 --build 14
```

What it does: loads the ASC env file, runs preflight, stamps version and build number
(`MARKETING_VERSION` and `CURRENT_PROJECT_VERSION` overrides, plus `app.json` for Expo),
archives `Release` for `generic/platform=iOS` with automatic signing
(`-allowProvisioningUpdates -authenticationKeyPath/-ID/-IssuerID`), writes
`build/ExportOptions.plist` (method `app-store-connect`, your `teamID`), and exports.
The `.ipa` lands in `build/export/`. Build number is the highest uploaded build plus one
(from App Store Connect, else `build.lastBuildNumber`), because a build number may never
repeat or go down within a version.

Add `build/` to `.gitignore` if missing.

### 5. Upload (needs the user's go-ahead)

Ask: "Upload version X build N to App Store Connect now?" On yes:

```bash
"${CLAUDE_SKILL_DIR}/scripts/release.sh" --upload              # xcodebuild exports straight to App Store Connect
"${CLAUDE_SKILL_DIR}/scripts/release.sh" --upload --method altool   # export an .ipa, then xcrun altool with the API key
```

The default method needs no `.ipa` on disk; use `altool` if you want to keep the `.ipa`
or the first method fails. On success the script prints `UPLOADED version=X build=N` and
writes `build.lastBuildNumber`. Tick the line in `.ship/PROGRESS.md` with the build
number. Then tell the user the next step: `ship-store testflight --build N` (processing
takes about 5 to 20 minutes; the build is not selectable until then).

### 6. Failures

| Symptom | Likely cause and fix |
|---|---|
| `No profiles for 'com.x.y' were found` | App record or bundle ID missing in the developer account; create the App ID (ship-store) and retry, `-allowProvisioningUpdates` makes the profile |
| `Authentication failed` / 401 | wrong `ASC_KEY_ID`/`ASC_ISSUER_ID`, key revoked, or role lacks App Manager |
| `Cloud signing permission error` | key role too low; Admin or App Manager needed to create distribution certs |
| Upload ok but build never shows | email from Apple lists the problem (missing purpose string, invalid icon); fix, bump build number, upload again |
| `The bundle version must be higher` | build number reused; pass a higher `--build` |
| Pod or Node errors on Expo | run `npx expo-doctor`, delete `ios/` if it is gitignored, retry |

## Android (only if `app.platforms` includes `android`)

Brief on purpose. Play wants a signed **`.aab`**:

```bash
cd android && ./gradlew bundleRelease     # Expo: run npx expo prebuild --platform android first
# output: android/app/build/outputs/bundle/release/app-release.aab
```

Signing: create an upload keystore once (`keytool -genkeypair -v -storetype PKCS12 -keystore upload.jks -alias upload -keyalg RSA -keysize 2048 -validity 10000`), keep it
outside the repo with its passwords in an env file, and reference it from
`android/gradle.properties` or an untracked `keystore.properties`. Bump `versionCode`
(integer, always increasing) and `versionName` per build. Play App Signing holds the
real app key; you only hold the upload key.

The **first release must be created by hand** in Play Console (create app, fill store
listing and content rating, upload the first `.aab` to a track). The Play Developer API
only works for apps that already have a release, so do not try to automate release one.
Later uploads: `eas submit --platform android`, `fastlane supply`, or the console.

## Done when

`build.lastBuildNumber` is set, the build shows in App Store Connect (or the `.ipa`
exists and the user has not said to upload yet), PROGRESS.md is ticked, and the user
knows the next step.
