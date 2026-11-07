# Preflight reference

`scripts/preflight.py` is static and read-only. It is a safety net, not a guarantee;
App Review can still find things it cannot (a login that needs a demo account, a broken
purchase flow).

## Checks

| Check | Fails when | Typical fix |
|---|---|---|
| App icon 1024 | no 1024x1024 PNG in an `.appiconset` or `expo.icon`; or the PNG has alpha | export again, flatten onto a solid colour (no transparency, no rounded corners; iOS rounds it) |
| Permission strings | code or a dependency uses a gated API and the usage key is missing or empty | add `NSCameraUsageDescription` etc. Say why the app needs it in one human sentence |
| AdMob app ID | `ads` is `admob` and `GADApplicationIdentifier` is missing | add the real app ID (not the test one) |
| Privacy manifest | no `PrivacyInfo.xcprivacy`; WARN when a used required-reason API has no entry | add the file; declare UserDefaults (`CA92.1`), file timestamp (`C617.1`), boot time (`35F9.1`), disk space (`E174.1`) as applicable |
| Export compliance | `ITSAppUsesNonExemptEncryption` absent | set `false` if you only use HTTPS and system crypto |
| Bundle ID | project bundle ID differs from `app.bundleId` | fix whichever is wrong before the first upload; it cannot change later |
| Deployment target | WARN below 15 or above 18 | judgement call |
| Test IDs and keys | AdMob test ID, `sk_test_` / `sk_live_` Stripe secrets, test store keys, committed `.p8`, localhost URLs | swap for production values loaded from build config; never ship a secret key in the app |
| Version vs live | version not above the shipped one | bump `app.marketingVersion` |

Permission detection is by pattern: native sources are grepped for framework types
(`AVCaptureSession`, `CLLocationManager`, `PHPhotoLibrary`, ...), JS stacks by
dependency names in `package.json` (`expo-camera`, `expo-location`, ...). It can miss
exotic wrappers; a human check of the table against the real feature list is still
worth ten seconds.

Required-reason categories use patterns too (UserDefaults, `@AppStorage`, `stat(`,
`systemUptime`, `volumeAvailableCapacity`). JS stacks assume React Native core uses
UserDefaults, file timestamps and boot time.

## Allow list

`.ship/preflight-allow.txt`, one regex per line, `#` for comments. A finding is ignored
when `path:line  matching text` matches any line. Example, a debug-only test ID:

```
Debug/.*ca-app-pub-3940256099942544
```

## Release gate example (`.ship/release-gate.sh`)

```bash
#!/usr/bin/env bash
# Called as: release-gate.sh config | archive <xcarchive> | ipa <ipa>
set -euo pipefail
case "$1" in
  config) grep -q '"devMenu": *true' app.json && { echo "dev menu is on"; exit 1; } || true ;;
  archive) plutil -extract DEV_FLAGS raw "$2/Products/Applications/"*.app/Info.plist 2>/dev/null \
             | grep -qi true && { echo "dev flag compiled in"; exit 1; } || true ;;
  ipa) unzip -p "$2" 'Payload/*.app/Info.plist' >/dev/null ;;
esac
```

Run it three times (before, after archive, on the signed ipa) because each stage can
differ: config can be right while the archive embeds an old value.
