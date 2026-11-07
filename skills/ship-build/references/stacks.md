# Stack notes

## Expo / React Native (Continuous Native Generation)

`release.sh` treats `ios/` as generated when it is gitignored: it runs
`npx expo prebuild --platform ios --clean --no-install` every release so the native
project always reflects `app.json` / `app.config.ts` exactly. A stale `ios/` once kept
a removed background mode and an old SKAdNetwork ID in a shipped build. If `ios/` is
committed, the script prebuilds without `--clean` and never deletes it.

- Static `app.json`: the script stamps `expo.version` and `expo.ios.buildNumber`.
- Dynamic `app.config.ts`: it cannot rewrite the file. The `MARKETING_VERSION` and
  `CURRENT_PROJECT_VERSION` overrides on the archive still apply because the generated
  Info.plist reads `$(MARKETING_VERSION)` and `$(CURRENT_PROJECT_VERSION)`.
- Env-driven config (flags read by `app.config.ts`) must be exported before running the
  script; they are read at prebuild and again when Xcode embeds the config.
- Permission strings come from plugin options, for example
  `["expo-camera", { "cameraPermission": "Scan receipts" }]`. Preflight accepts either
  the plist key or the plugin option name.
- Privacy manifest: set `ios.privacyManifests` in app config; Expo writes the file.
- Export compliance: `ios.config.usesNonExemptEncryption: false`.

### EAS alternatives (acceptable when the user prefers them)

```bash
eas build --platform ios --profile production --local   # builds on this Mac
eas submit --platform ios --latest                       # uploads the newest build
```

Still run preflight first. Never `eas update` as a release channel for this app.

## Flutter (manual)

```bash
flutter build ipa --release --build-name 1.2.0 --build-number 14 \
  --export-options-plist build/ExportOptions.plist
```

Generate `ExportOptions.plist` like release.sh does (method app-store-connect, teamID,
destination export), then upload `build/ios/ipa/*.ipa` with
`xcrun altool --upload-app -f <ipa> -t ios --api-key $ASC_KEY_ID --api-issuer $ASC_ISSUER_ID`
(altool finds `AuthKey_<id>.p8` in `~/.appstoreconnect/private_keys` or
`$API_PRIVATE_KEYS_DIR`). Run `preflight.py` against the repo first; it reads `ios/`.

## CocoaPods

Archive the `.xcworkspace`, never the `.xcodeproj`. release.sh picks the workspace when
one exists. Run `pod install` after changing dependencies; commit `Podfile.lock`.

## XcodeGen

The `.xcodeproj` is generated from `project.yml`. Keep `MARKETING_VERSION` and
`CURRENT_PROJECT_VERSION` as variables, not hard-coded `CFBundleVersion` in the plist, so
the overrides take effect.

## Multiple schemes / extensions

Set `build.scheme` in ship.json to the app scheme (not a widget or test scheme). Embedded
extensions get signed automatically; their bundle IDs must be prefixed by the app's.
