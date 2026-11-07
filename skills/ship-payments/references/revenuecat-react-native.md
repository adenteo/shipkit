# RevenueCat in an Expo / React Native app

Same shape as the Swift version: one place owns "is this user premium", every gate
reads it, and the paywall is RevenueCat's remote paywall so it can change without
an app update.

## Install

```bash
npx expo install react-native-purchases react-native-purchases-ui
```

Purchases need native code, so they do not work in Expo Go. Use a development
build (`npx expo run:ios`, or `eas build --profile development`). Check the
current RevenueCat docs for the installed version before writing code; the API
below matches react-native-purchases 8 to 10.

## Configure once

```ts
// src/lib/purchases.ts
import Purchases, { LOG_LEVEL } from "react-native-purchases";
import { Platform } from "react-native";

const IOS_KEY = process.env.EXPO_PUBLIC_RC_IOS_KEY!; // appl_..., public, safe in the app

export function initPurchases() {
  Purchases.setLogLevel(__DEV__ ? LOG_LEVEL.DEBUG : LOG_LEVEL.ERROR);
  if (Platform.OS === "ios") Purchases.configure({ apiKey: IOS_KEY });
}
```

Call `initPurchases()` once at startup, before any screen asks about premium.

## One source of truth

```ts
// src/hooks/usePremium.ts
import { useEffect, useState } from "react";
import Purchases, { CustomerInfo } from "react-native-purchases";

export const ENTITLEMENT = "pro"; // must match the RevenueCat dashboard exactly

const isActive = (info: CustomerInfo) => info.entitlements.active[ENTITLEMENT] !== undefined;

export function usePremium() {
  const [premium, setPremium] = useState(false);
  useEffect(() => {
    Purchases.getCustomerInfo().then((i) => setPremium(isActive(i))).catch(() => {});
    const listener = (i: CustomerInfo) => setPremium(isActive(i));
    Purchases.addCustomerInfoUpdateListener(listener);
    return () => { Purchases.removeCustomerInfoUpdateListener(listener); };
  }, []);
  return premium;
}
```

If several screens need it, lift it into a context provider so there is one
listener.

## Gate and show the paywall

```ts
import RevenueCatUI, { PAYWALL_RESULT } from "react-native-purchases-ui";

async function openPro(trigger: string) {
  track("paywall_viewed", { trigger });
  const result = await RevenueCatUI.presentPaywallIfNeeded({ requiredEntitlementIdentifier: ENTITLEMENT });
  return result === PAYWALL_RESULT.PURCHASED || result === PAYWALL_RESULT.RESTORED;
}

if (premium || withinFreeAllowance) startFeature();
else if (await openPro("export")) startFeature();
```

## Identity and restore

- After sign-in: `await Purchases.logIn(user.id)`. On sign-out:
  `await Purchases.logOut()`. Without this, purchases stay on an anonymous ID and
  do not follow the user to a new phone.
- Settings needs a visible "Restore Purchases" button:
  `const info = await Purchases.restorePurchases();` then refresh state and tell
  the user whether anything was restored.

## Pitfalls

| Symptom | Cause |
|---|---|
| "There is no singleton instance" | `configure` ran after a component called the SDK. Configure first. |
| Offerings empty | Products not imported or not in the `default` offering, Paid Apps agreement not active, or bundle ID mismatch. |
| Works in dev build, not TestFlight | Wrong API key per build, or the entitlement name differs. |
| Paywall shows on Android only | iOS key missing in that build's env. |
