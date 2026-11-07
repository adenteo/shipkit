---
name: ship-payments
description: >-
  Add in-app purchases or subscriptions to an iOS app that is about to ship:
  RevenueCat (SwiftUI or Expo / React Native, with its remote paywall) or plain
  StoreKit 2, plus the product plan, prices, the App Store Connect and RevenueCat
  setup the user does by hand, the paywall rules App Review checks, restore
  purchases, and sandbox testing. Use when the user wants a paywall, a Pro tier,
  subscriptions, a one-time unlock, "make this paid", RevenueCat, StoreKit, or
  when the ship skill reaches its payments step.
---

# ship-payments

Read `ship.json` first: `features.payments` (`revenuecat`, `storekit`, `none`),
`app.stack`, and `monetization`. If payments is `none`, set `monetization.price`
(`free` or a paid-up-front price), tick the step and stop.

## 1. Plan what to sell

Agree on the products with the user before writing code, and write them into
`ship.json` `monetization.products` (format in `ship/references/ship-json.md`).

- **What is free and what is paid.** Name the exact features behind the paywall
  and any free allowance ("3 entries a day free"). A free tier people can love
  is what gets them to pay.
- **Product shapes.** Subscriptions (monthly and yearly in one group, optionally a
  free trial on yearly), a lifetime non-consumable, or consumables (coins,
  credits). Keep it to two or three products at launch.
- **Prices.** Suggest a monthly price and a yearly price that is clearly cheaper
  per month. Show yearly first and mark it as the best value on the paywall.
- **IDs.** `com.<company>.<app>.<thing>.<period>`, for example
  `com.acme.journal.pro.yearly`. Product IDs can never be reused, even after
  deletion, so get them right once.

## 2. What the user does by hand

These need their accounts. Give them the steps and wait.

1. **Paid Apps agreement.** App Store Connect, Business: accept the Paid Apps
   agreement and fill in tax and banking. Until it is active, purchases fail even
   in the sandbox.
2. **Products in App Store Connect.** `ship-store products` creates them from
   `ship.json` (show `--dry-run` first and get a yes). The first in-app purchase
   or subscription has to be submitted for review together with an app version.
3. **RevenueCat (if chosen).** Create a project, add an App Store app with the
   bundle ID, upload an In-App Purchase key (App Store Connect, Users and Access,
   Integrations, In-App Purchase, generate a `.p8`), and paste the App Store
   Server Notifications URL RevenueCat shows into App Store Connect (App
   Information). Then in RevenueCat: import the products, create the entitlement
   (for example `pro`), an offering named `default` with the packages, and design
   the paywall. Store the public SDK key path in `ship.json`
   `secrets.revenuecatEnv` (the `appl_` key is public and may live in the app;
   the secret `sk_` key never goes in the app).

## 3. Build it

### RevenueCat, SwiftUI

Follow `references/revenuecat-swift.md`. Short version: add `RevenueCat` and
`RevenueCatUI` packages; configure at launch; one `PremiumService` owns
`isPremium` and every gate reads it (template in
`references/premium-service-template.swift`); present `PaywallView`
imperatively from the top view controller, not from a `.sheet` bound to a
published flag; call `logIn` after sign-in and `logOut` on sign-out; add Restore
Purchases in Settings. Optional server mirror: `references/webhook-edge-function.ts`.

### RevenueCat, Expo / React Native

Follow `references/revenuecat-react-native.md`: `react-native-purchases` and
`react-native-purchases-ui`, a development build (purchases do not work in Expo
Go), configure once at startup, a `usePremium` hook as the single source of
truth, `RevenueCatUI.presentPaywallIfNeeded({ requiredEntitlementIdentifier })`
at each gate, restore in Settings.

### StoreKit 2 only

Follow `references/storekit2.md`: a small `Store` that loads products, buys,
listens to `Transaction.updates`, and derives `isPremium` from
`Transaction.currentEntitlements`. Build the paywall in SwiftUI (or use
`SubscriptionStoreView` for subscriptions). Add a StoreKit configuration file so
purchases work in the simulator without App Store Connect.

### Analytics hooks

If `features.analytics` is set, fire `paywall_viewed` (with the trigger),
`purchase_started`, `purchase_completed` (product id), `purchase_failed`,
`restore_completed`. `ship-analytics` defines the event names; reuse them.

## 4. Paywall rules App Review checks

Guideline 3.1.1 and 3.1.2. Breaking these is one of the most common rejections.

- Every paid digital feature is bought through Apple's in-app purchase. No links
  or buttons to pay on the web for digital content.
- The paywall shows, next to the buy button: the price, the billing period, what
  the user gets, and for a trial, what it costs after the trial and when.
- It says the subscription renews automatically until cancelled, and links to the
  Terms of Use (Apple's standard EULA is fine) and the Privacy Policy. The App
  Store description carries the same two links.
- There is a visible Restore Purchases button (in the paywall and in Settings).
- The close button is visible straight away; no fake countdowns or tricks.
- The app works for its free features without paying; it does not lock the user
  out of things that were free before.
- Write in the App Review notes where the paywall and each product are, so the
  reviewer can find them (ship-review collects this).

## 5. Test it

1. Simulator: a StoreKit configuration file (Xcode, File, New, StoreKit
   Configuration File, synced to the app) lets you buy without the network. In
   the RevenueCat template the debug `devOverride` flips premium on without
   buying.
2. Device with a Sandbox Apple Account (App Store Connect, Users and Access,
   Sandbox): buy each product, see premium unlock and the paywall close, kill
   and relaunch, then delete and reinstall and use Restore.
3. TestFlight: purchases are free and renew fast. Check one full flow there before
   submitting.

Common failures: the entitlement ID in code does not match the dashboard exactly;
products stuck in "Missing Metadata" (they need a review screenshot and a
localized name); the Paid Apps agreement is not active; the bundle ID in
RevenueCat differs from the app.

Tick the payments line in `.ship/PROGRESS.md` with the products and prices.
