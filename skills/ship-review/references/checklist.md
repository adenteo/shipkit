# Pre-submission checklist

Copy into `.ship/review/checklist-<version>.md` and mark each line PASS, FIX or N/A.
Guideline numbers refer to the App Store Review Guidelines; read the current text
at https://developer.apple.com/app-store/review/guidelines/ when an item is unclear.

## Build and stability (2.1, 2.2, 2.5)
- [ ] Fresh install on a real device from TestFlight: onboarding, core path, settings all work
- [ ] No crash on launch with the network off; sensible error states instead of blank screens
- [ ] No placeholder text, lorem ipsum, test data, "TODO", or "coming soon" buttons
- [ ] No debug menus, test ad unit IDs, test API keys, or verbose logging in the release build
- [ ] Every link and button goes somewhere real (support, privacy, terms open)
- [ ] Works on the smallest supported iPhone and, if iPad is supported, on iPad in both orientations
- [ ] Uses only public APIs; no downloading of executable code

## Payments (3.1.1, 3.1.2, 3.1.3)
- [ ] Digital content and features are sold only with in-app purchase
- [ ] No buttons, links or wording pointing to cheaper or external purchase for digital goods (unless the app qualifies for an allowed exception in the user's storefront and it is implemented per Apple's rules)
- [ ] Paywall shows price, billing period, what is included; trial terms if any
- [ ] Paywall states auto-renewal and links Terms of Use and Privacy Policy
- [ ] Restore Purchases in the paywall and in Settings
- [ ] Close button visible immediately; no misleading timers or fake discounts
- [ ] Products: localized name and description, review screenshot, cleared for sale, attached to this version if first time
- [ ] Free features stay usable without paying

## Privacy and data (5.1)
- [ ] Privacy policy URL loads and matches what the app does
- [ ] App Privacy answers match the code and every SDK
- [ ] PrivacyInfo.xcprivacy present with required-reason API declarations
- [ ] Each permission has a specific purpose string ("to attach photos to your entries") and is requested in context, not at launch
- [ ] App Tracking Transparency prompt before any tracking (only if tracking)
- [ ] Account deletion available in the app if accounts exist (5.1.1(v))
- [ ] No forced sign-in for features that do not need an account (5.1.1)
- [ ] Sign in with Apple offered if any third-party login is offered (4.8)

## Metadata (2.3)
- [ ] Screenshots show the real app UI, current version, required sizes
- [ ] Name, subtitle, keywords: no trademarks, no competitor names, no keyword stuffing
- [ ] Description matches features in this build; no other platforms mentioned
- [ ] Age rating answers honest (UGC, chat, web access, medical, gambling-like mechanics)
- [ ] Support URL shows a way to contact the developer
- [ ] What's New written (updates only)

## Design and originality (4.0, 4.2, 4.3)
- [ ] More than a website in a wrapper; uses native features
- [ ] Not a template or reskin; review notes explain what is original
- [ ] Not substantially the same as another app from the same developer

## Ads (if used)
- [ ] No ad before the user's first interaction; no ads that mimic app UI
- [ ] Interstitial frequency reasonable; rewarded ads optional
- [ ] Consent (UMP in EEA/UK) and ATT flows work; declining still allows use
- [ ] Ad content rating appropriate for the app's age rating

## App Review information
- [ ] Contact name, email, phone filled in
- [ ] Demo account provided and working if sign-in is required (it does not expire during review)
- [ ] Notes explain how to reach every paid feature and anything that needs special setup
