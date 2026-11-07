# RevenueCat in a SwiftUI app

RevenueCat is the cleanest way to ship subscriptions on iOS: it wraps
StoreKit, handles receipt validation, and exposes a simple `isActive` boolean
per **entitlement**. The app never talks to StoreKit directly, it asks
RevenueCat "is this user entitled?" and gates accordingly.

This skill captures a production integration pattern. It is reusable for any
SwiftUI app; the file paths and names below are conventions, not requirements:
adapt them to the target codebase.

## What you're building

A small, well-defined surface:

1. **SDK config**: one `Purchases.configure(...)` call at app launch.
2. **`PremiumService`**: a `@MainActor ObservableObject` singleton that owns
   the single source of truth: `@Published var isPremium`. Every gate in the
   app reads this; nothing else touches the RevenueCat SDK.
3. **Paywall**: RevenueCat's drop-in `PaywallView` (from `RevenueCatUI`),
   designed in the RC dashboard, presented when a gate is hit.
4. **Identity**: tie the RevenueCat user to your auth user so purchases
   follow the account across devices.
5. **(Optional) Webhook**: a backend endpoint RevenueCat POSTs lifecycle
   events to, mirroring entitlement state into your own DB for server-side
   gating.

Keeping all SDK contact inside `PremiumService` is the load-bearing decision:
it means there is exactly one place to reason about entitlement state, one
place to add logging, and gates elsewhere are just `if premium.isPremium`.

## Before you start: gather these

Ask the user for whatever isn't already discoverable in the repo:

- **RevenueCat public SDK key**: `appl_...` for iOS (RC Dashboard → Project →
  API Keys). This is a *public* key; it's safe in client source.
- **Entitlement identifier**: the exact string from RC Dashboard →
  Entitlements (e.g. `pro`, `premium`). **Case and spaces must match
  exactly**: a mismatch is the #1 cause of "I bought it but I'm still not
  premium" bugs.
- **What's being gated**: which features are free vs. paid, and any free
  allowance (e.g. "first 3 recordings free"). This shapes the gate methods.
- **Auth system**: how the app identifies users (Supabase, Firebase, etc.),
  so the RevenueCat identity can be linked to it.

If RC products/offerings/paywall aren't set up in the dashboard yet, tell the
user that's a prerequisite done in the RC web dashboard, the SDK can't create
them. The skill picks up once a paywall exists in the dashboard.

## Integration steps

### 1. Add the Swift packages

Add via Xcode → File → Add Package Dependencies →
`https://github.com/RevenueCat/purchases-ios`.

Add **two** library products to the app target:

- `RevenueCat`: the core SDK.
- `RevenueCatUI`: the prebuilt `PaywallView`.

Do **not** add `RevenueCat_CustomEntitlementComputation`. That's a separate
mode for apps that compute entitlements on their own backend; mixing it in
breaks the standard `customerInfo` flow this skill relies on.

### 2. Configure the SDK at launch

In the `App` struct's `init()` (before any UI), as early as possible:

```swift
import RevenueCat

init() {
    Purchases.logLevel = PremiumService.isDebugBuild ? .debug : .error
    Purchases.configure(withAPIKey: "appl_YOUR_KEY_HERE")
}
```

`.debug` log level in Debug builds is worth its weight, RevenueCat's logs
tell you exactly which entitlements it sees and why. Drop to `.error` in
release so the console isn't noisy.

### 3. Create `PremiumService`

This is the heart of the integration. Read
`references/premium-service-template.swift`: it is a fully annotated,
copy-ready template. Place it at `Services/PremiumService.swift` (or the
project's equivalent) and adapt:

- `entitlementId` → the user's exact entitlement string.
- The free-tier gate methods (`canStartSolo`, etc.) → the user's actual
  features. Delete the example gates and write the ones that fit.
- Analytics calls (`AnalyticsService.subscriptionActive()`, etc.) → wire to
  the project's analytics, or remove if there is none.

The template includes, and you should keep, these pieces because each exists
to solve a real problem:

- **`isPremium` as the single `@Published` source of truth.** Read it
  everywhere; never re-query the SDK ad hoc.
- **`checkPremiumStatus()`**: call on app launch / foreground to refresh.
- **`identify(userId:)` / `unidentify()`**: see step 4.
- **The Debug `devOverride`**: lets you toggle premium on the simulator
  without a sandbox purchase. Compiled to a no-op in release builds, so it
  cannot leak a free Pro tier to users.
- **`dumpCustomerInfo(...)`**: prints every entitlement key the SDK sees
  after each fetch. When an entitlement mismatch happens, this log is the
  fastest path to the answer.

### 4. Link RevenueCat identity to your auth user

By default RevenueCat assigns an anonymous ID. Call `Purchases.shared.logIn`
with your auth user's stable ID **right after sign-in**, and `logOut` on
sign-out. The template wraps these as `identify(userId:)` / `unidentify()`.

Why this matters: purchases are keyed to the RevenueCat app user ID. If it
stays anonymous, a subscription won't follow the user to a new device, and,
critically, the webhook (step 7) won't know which DB row to update, because
the only identifier it receives is this app user ID.

Wire it into the auth layer: call `identify` wherever the app learns who the
user is (sign-in success, and on launch if a session is restored), and
`unidentify` on sign-out.

### 5. Gate features on `isPremium`

Replace feature entry points with gate checks. Pattern:

```swift
if premium.isPremium || withinFreeAllowance {
    startTheFeature()
} else {
    premium.showPaywall(trigger: "feature_name")
}
```

Put the *logic* for free allowances inside `PremiumService` as small methods
(see the template's `canStartSolo` / `canUseRooms`) so the rules live in one
place and read clearly at the call site. The `trigger` string flows into
analytics, make it descriptive so paywall conversion can be analyzed per
entry point.

### 6. Present the paywall

Use `PaywallView` from `RevenueCatUI`: it renders the paywall designed in the
RC dashboard, so design changes ship without an app update.

The template presents it **imperatively via UIKit** (`showPaywall(trigger:)`),
not via a SwiftUI `.sheet`/`.fullScreenCover` bound to a `@Published` flag.
This is deliberate and you should keep it. Binding a paywall cover to a
published flag causes the cover to attach at multiple levels of the view
hierarchy at once; when the flag flips false, every copy dismisses and the
dismissal propagates up through any presenting sheet, collapsing the whole
stack and sometimes re-triggering presentation. Imperative UIKit presentation
on the top-most view controller sidesteps SwiftUI's presentation hierarchy
entirely. The template's `topMostViewController()` handles finding it.

Hook `.onPurchaseCompleted` and `.onRestoreCompleted` to refresh `isPremium`
and dismiss, both are in the template.

### 7. Restore purchases

App Review **requires** a visible "Restore Purchases" control (typically in
Settings). Wire a button to `PremiumService.restorePurchases()` (in the
template). `PaywallView` also shows its own restore link; both must work.

### 8. (Optional) Server-side entitlement mirror via webhook

The client treats RevenueCat as the source of truth, which is fine for
client-side gating. Add a webhook only if the backend also needs to know who's
premium (server-side gating, analytics, avoiding REST round-trips to RC).

Read `webhook-edge-function.ts` (next to this file): a complete Supabase edge function
that receives RevenueCat lifecycle events and mirrors `is_premium` into a
`users` table. Adapt it to the target backend; the logic (which event types
enable vs. disable, skipping anonymous users, shared-secret auth) is
platform-agnostic.

Setup checklist for the webhook:

- Add columns to the users table: `is_premium boolean`, `premium_expires_at
  timestamptz`, `premium_product_id text`, `premium_updated_at timestamptz`.
- Deploy the function, then register its URL in RC Dashboard → Integrations →
  Webhooks with a shared-secret `Authorization` header value.
- Store that secret as a backend env var (`REVENUECAT_WEBHOOK_SECRET`) and
  verify it on every request, the endpoint is public.
- **Supabase note:** deploy with `--no-verify-jwt`. RevenueCat does not send a
  Supabase JWT, so the gateway's JWT check would reject every event. The
  function authenticates via its own shared secret instead.
- The webhook depends entirely on step 4, if the client never calls
  `identify`, every event arrives with an anonymous `$RCAnonymousID:` user and
  is skipped.

## Verifying it works

- **Simulator / Debug:** flip `devOverride` to confirm gates respond to
  `isPremium` without needing a real purchase.
- **Sandbox purchase:** sign into a sandbox Apple ID, complete a real purchase
  flow, confirm `isPremium` becomes true and the paywall dismisses. Watch the
  `[RC]` logs, `dumpCustomerInfo` prints the entitlement keys; the active set
  must contain your `entitlementId` exactly.
- **Restore:** delete and reinstall the app, tap Restore, confirm premium
  returns.
- **Webhook:** RC Dashboard → Webhooks has a "Send test event" button; check
  the function logs and the DB row.

## Common pitfalls

| Symptom | Cause |
|---|---|
| Bought it, still not premium | `entitlementId` string doesn't match the dashboard (case/spaces), or you're checking the *product* ID instead of the *entitlement* ID. |
| Paywall flickers / dismisses its presenter | Bound to a `@Published` flag via `.fullScreenCover`. Present imperatively instead (step 6). |
| Webhook updates nothing | Client never called `identify`, so events are anonymous; or the function was deployed with JWT verification on. |
| Premium lost on reinstall | `logIn` not called, purchases stuck on an anonymous ID. |
| Works in Debug, not TestFlight | `devOverride` was masking a real bug. It's release-disabled by design; test the real flow in a sandbox. |
