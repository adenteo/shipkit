---
name: ship-review
description: >-
  Get an iOS app through App Review: a pre-submission check against the
  guidelines that cause most rejections (crashes and placeholders, in-app
  purchase and subscription rules, privacy and permissions, account deletion,
  Sign in with Apple, metadata accuracy, copycat and spam apps, tracking),
  testing the exact build on a device, submitting, and handling a rejection
  (reading the message, mapping it to the guideline, fixing, replying or
  appealing). Use before submitting an app or update, when the user asks if an
  app will pass review, or when they paste a rejection from App Store Connect.
---

# ship-review

Submitting is quick; a rejection costs days. Run the checklist on the exact build
that will be submitted, then submit with `ship-store submit` once the user says go.

## 1. Pre-submission checklist

Go through `references/checklist.md` item by item against the code, the build and
`ship.json`. For each item record PASS, FIX (and fix it), or N/A in
`.ship/review/checklist-<version>.md`. The items that reject most apps:

1. **It works (2.1).** No crashes, no placeholder text or "lorem ipsum", no broken
   links, no "coming soon" features, no debug menus in release. Test on a real
   device from TestFlight, from a fresh install, with the network off once.
2. **Payments (3.1.1, 3.1.2).** Digital goods only through in-app purchase; the
   paywall shows price, period, renewal terms, Terms and Privacy links; Restore
   exists; products are attached to the version (first time) and have review
   screenshots.
3. **Privacy (5.1.1, 5.1.2).** Privacy policy URL works; App Privacy answers match
   the code; every permission prompt has a specific purpose string and is asked
   when needed, not at launch; ATT shown before any tracking; account deletion in
   the app if accounts exist; no login wall for features that do not need an
   account.
4. **Sign in with Apple (4.8).** Required if any third-party or social login is
   offered.
5. **Metadata (2.3).** Screenshots show the real app; name and subtitle have no
   keywords stuffing or Apple trademarks; description matches the build; no other
   platforms named; age rating honest.
6. **Minimum functionality and spam (4.2, 4.3).** More than a wrapped website;
   not a near-copy of a template or of the developer's own other apps. Review notes
   explain what is original.
7. **Kids and health claims (1.3, 1.4.1).** No medical claims without evidence; if
   it targets kids, the Kids Category rules apply.
8. **Ads (if any).** No ads in the first screen before the user does anything, no
   ads that look like app content, no rewarded ads required to progress basic
   features, ATT and consent forms in place.

## 2. Final checks before pressing submit

- `ship-build` preflight passes on the release build.
- The build in TestFlight was installed and the core path, the paywall, a sandbox
  purchase and restore were tried on a device.
- `ship-store status` shows: listing complete for every locale, screenshots for
  every required display size, review details with contact info, age rating set,
  pricing set, build attached, App Privacy published (the user confirms).
- Choose the release option with the user: manual release after approval (safest
  for a first launch, so the website and posts can go out together) or automatic.

Then show `ship-store submit --dry-run`, get a clear yes, and run it with
`--confirm`. Tell the user typical review time is about a day, sometimes longer
for a first submission, and that they get an email either way.

## 3. If it is rejected

Ask the user to paste the full message from App Store Connect (App Review,
Messages). Then:

1. Identify the guideline number(s) and quote the exact sentence that says what
   they saw. Keep a log in `.ship/review/rejections.md`.
2. Decide which kind it is:
   - **A real problem**: fix it, bump the build, upload, reply briefly saying what
     changed and where to see it, and resubmit.
   - **A misunderstanding** (the reviewer missed the paywall, the restore button,
     the demo account): reply in the Resolution Center with exact steps and a
     screenshot or screen recording; no new build needed.
   - **Metadata only** (screenshots, description, privacy answers): fix in App Store
     Connect and resubmit without a build.
   - **Disagreement on a judgment call**: one calm, specific reply first. Only if
     that fails, the App Review Board appeal form. Never argue in the first reply.
3. Draft the reply for the user: short, polite, specific ("The Restore Purchases
   button is in Settings, second row, see the attached screenshot."). The user
   sends it.

`references/rejections.md` lists the common rejection messages with the usual fix.

Tick the review line in `.ship/PROGRESS.md` with the submission date, then the
approval date.
