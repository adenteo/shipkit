---
name: ship-analytics
description: >-
  Add product analytics to an iOS app before launch: PostHog or TelemetryDeck
  for SwiftUI or Expo / React Native, a small event plan built around the
  activation and paywall funnel, user identity, keeping the project key out of
  git, and the App Store privacy answers the choice implies. Use when the user
  wants analytics, events, funnels, retention, PostHog or TelemetryDeck in an
  app, or when the ship skill reaches its analytics step.
---

# ship-analytics

Read `ship.json` `features.analytics`. If it is `none`, record that (it makes the
privacy answers simpler), tick the step and stop.

## 1. Event plan first

Agree on a short list before touching code. Ten good events beat fifty noisy
ones. Start from this and adapt names to the app:

| Event | When | Properties |
|---|---|---|
| `app_opened` | Launch and return to foreground | `first_open` |
| `onboarding_started` / `onboarding_completed` | First run | `step_count` |
| `core_action` (rename: `entry_saved`, `level_cleared`, ...) | The one thing the app is for | what matters to analyse |
| `activation` | The moment a new user has clearly got value (for example the third core action on day one) | |
| `paywall_viewed` | Paywall shown | `trigger` |
| `purchase_started` / `purchase_completed` / `purchase_failed` | Purchase flow | `product_id` |
| `restore_completed` | Restore tapped and finished | `restored` |
| `share_tapped` | Any share | `what` |
| `notification_permission` | Answered the prompt | `granted` |

Write the list into `.ship/analytics-events.md` with one line per event saying
why it exists. Each event should answer a question the user will actually ask
("how many people finish onboarding", "which trigger sells").

## 2. The key stays out of git

The PostHog project key and TelemetryDeck app ID are public client IDs, but keep
them out of the repo anyway so forks and screenshots do not send events into the
user's project. Put the value in an env file named in `ship.json`
`secrets.posthogEnv` and pass it at build time:

- Xcode: a build setting (`POSTHOG_TOKEN=$(POSTHOG_TOKEN)` in Info.plist, the
  value set on the `xcodebuild` command line by ship-build), read with
  `Bundle.main.object(forInfoDictionaryKey:)`. If it is empty, send nothing.
- Expo: `EXPO_PUBLIC_POSTHOG_KEY` in `.env` (gitignored) or the EAS env.

## 3. Install

### PostHog, SwiftUI

Swift Package `https://github.com/PostHog/posthog-ios`. Check the current README
for the version you install.

```swift
import PostHog

enum Analytics {
    static func start() {
        guard let key = Bundle.main.object(forInfoDictionaryKey: "POSTHOG_TOKEN") as? String,
              !key.isEmpty else { return }
        let config = PostHogConfig(apiKey: key, host: "https://us.i.posthog.com") // or eu.i.posthog.com
        config.captureApplicationLifecycleEvents = true
        config.captureScreenViews = false   // name screens yourself; SwiftUI auto names are noise
        PostHogSDK.shared.setup(config)
    }
    static func track(_ event: String, _ props: [String: Any] = [:]) {
        PostHogSDK.shared.capture(event, properties: props)
    }
    static func identify(_ userId: String) { PostHogSDK.shared.identify(userId) }
    static func reset() { PostHogSDK.shared.reset() }
}
```

Call `Analytics.start()` in the `App` init. Every event goes through
`Analytics.track` so names live in one file.

### PostHog, Expo / React Native

```bash
npx expo install posthog-react-native expo-file-system expo-application expo-device expo-localization
```

Wrap the app in `<PostHogProvider apiKey={process.env.EXPO_PUBLIC_POSTHOG_KEY} options={{ host: "https://us.i.posthog.com" }}>`
and use `usePostHog()` inside, or create one client with `new PostHog(key, { host })`
and export `track`. Check the current posthog-react-native README first.

### TelemetryDeck

Swift Package `https://github.com/TelemetryDeck/SwiftSDK`; initialise with the app
ID and send signals with `TelemetryDeck.signal("entry_saved")`. React Native:
`@telemetrydeck/sdk`. TelemetryDeck does not collect personal data by default,
which keeps the privacy answers short.

## 4. Identity

If the app has accounts, call `identify` with the app's own user ID right after
sign-in and `reset` on sign-out. Never send email addresses or names as event
properties unless the privacy policy says so.

## 5. Verify

Run the app in the simulator, do the core path once, then check the events
arrived (PostHog Activity view, or TelemetryDeck's live signals). Fix names that
came through wrong now; renaming later splits the history.

## 6. What it means for the privacy answers

Record in `ship.json` `store.privacyLabels` what this adds, so ship-listing can
write the App Privacy answers:

- PostHog with anonymous IDs: "Usage Data: Product Interaction" and
  "Identifiers: Device ID" (or "User ID" if you identify), used for Analytics,
  linked to the user only if you identify, not used for tracking.
- Session replay adds "Other Usage Data" and must be disclosed in the privacy
  policy.
- TelemetryDeck defaults: usually "Usage Data", not linked, not tracking.
- Neither needs the App Tracking Transparency prompt unless the data is combined
  with other companies' data for advertising. Ads SDKs (AdMob) are what usually
  bring ATT in.

Tick the analytics line in `.ship/PROGRESS.md`.
