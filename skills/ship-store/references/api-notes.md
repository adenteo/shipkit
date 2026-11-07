# App Store Connect API notes (hard-won)

Base URL `https://api.appstoreconnect.apple.com`. JWT ES256, `aud: appstoreconnect-v1`, max lifetime
20 minutes (the client mints 19 minute tokens and refreshes at 15). Pagination follows `links.next`.
`limit` is capped at 200 on most collections.

## Resource map

```
app
  appInfos (pick the one not READY_FOR_DISTRIBUTION) -> appInfoLocalizations (name, subtitle, privacyPolicyUrl)
                                                      -> ageRatingDeclaration, categories (relationships)
  appStoreVersions -> appStoreVersionLocalizations (description, keywords, promo, whatsNew, supportUrl, marketingUrl)
                        -> appScreenshotSets (one per display type) -> appScreenshots
                   -> appStoreReviewDetail, build (relationship), gameCenterAppVersion
  appPriceSchedule (manualPrices) , appAvailabilityV2 -> territoryAvailabilities
  inAppPurchasesV2, subscriptionGroups -> subscriptions
  betaGroups, betaAppLocalizations, betaAppReviewDetail
  reviewSubmissions -> items
bundleIds -> bundleIdCapabilities
```

## Listing

- `whatsNew` is rejected on the first version of an app. The script drops it automatically.
- A version cannot be created while another is still editable; the script refuses and asks you to align `app.marketingVersion`.
- Categories are relationships on appInfo. Games: `primaryCategory=GAMES`, `primarySubcategoryOne/Two=GAMES_PUZZLE...`.
- Keywords: 100 characters, comma separated, no spaces. Words already in name or subtitle are indexed already, so repeating them wastes budget. Apple also ignores plurals variants and "app".
- Name and subtitle are 30 characters each. Promo text is editable any time without a new version; description and keywords are not.
- `contentRightsDeclaration` is an attribute on the app, required before submission.

## Age rating

Attributes sent when present on the declaration: enums (`NONE`, `INFREQUENT_OR_MILD`, `FREQUENT_OR_INTENSE`) for
`alcoholTobaccoOrDrugUseOrReferences`, `contests`, `gamblingSimulated`, `gunsOrOtherWeapons`,
`medicalOrTreatmentInformation`, `profanityOrCrudeHumor`, `sexualContentGraphicAndNudity`, `sexualContentOrNudity`,
`horrorOrFearThemes`, `matureOrSuggestiveThemes`, `violenceCartoonOrFantasy`, `violenceRealistic`,
`violenceRealisticProlongedGraphicOrSadistic`; booleans for `gambling`, `lootBox`, `messagingAndChat`,
`parentalControls`, `unrestrictedWebAccess`, `userGeneratedContent`, `healthOrWellnessTopics`, `ageAssurance`,
`socialMedia`, `advertising`, `inAppPurchases`; `kidsAgeBand` null. Apple adds fields between API versions; the script reports
fields that are still unset.

## Pricing and availability

- App price: a schedule with one USA base `manualPrice`. Free is the price point whose `customerPrice` is `0.0`. Posting a new schedule replaces the old one.
- App availability: POST `/v2/appAvailabilities` with `territoryAvailabilities` inline (placeholders like `${t0}` in `included`). Once it exists, PATCH each territory instead of re-POSTing.
- `/v1/apps/{id}/appPriceSchedule` returns the schedule; the prices live at `/v1/appPriceSchedules/{id}/manualPrices` (the app-level path 404s).

## World prices (regional bands)

Read paths, all confirmed read-only against a live app on 2026-11-07:

| Need | Path |
|---|---|
| Territories (175) | `GET /v1/territories?limit=200` |
| Subscription current prices | `GET /v1/subscriptions/{id}/prices?include=subscriptionPricePoint,territory&limit=200` (one row per territory, plus future rows with `startDate`; skip `planType` other than `UPFRONT`) |
| Subscription USA points | `GET /v1/subscriptions/{id}/pricePoints?filter[territory]=USA&limit=200` (about 800, paged) |
| Subscription equalizations | `GET /v1/subscriptionPricePoints/{pp}/equalizations?filter[territory]=A,B&include=territory` |
| IAP schedule | `GET /v2/inAppPurchases/{id}/iapPriceSchedule?include=baseTerritory`, then `/v1/inAppPurchasePriceSchedules/{id}/manualPrices` and `/automaticPrices` with `include=inAppPurchasePricePoint,territory` |
| IAP USA points | `GET /v2/inAppPurchases/{id}/pricePoints?filter[territory]=USA&limit=200` |
| IAP equalizations | `GET /v1/inAppPurchasePricePoints/{pp}/equalizations?filter[territory]=...&include=territory` |
| App schedule | `GET /v1/apps/{id}/appPriceSchedule?include=baseTerritory`, then `/v1/appPriceSchedules/{id}/manualPrices` and `/automaticPrices` with `include=appPricePoint,territory` |
| App USA points | `GET /v1/apps/{id}/appPricePoints?filter[territory]=USA&limit=200` |
| App equalizations | `GET /v3/appPricePoints/{pp}/equalizations?filter[territory]=...&include=territory` |

Writes (subscription and IAP paths sent and read back on live apps 2026-11-07; the app price path is not yet exercised):

- Subscription: `POST /v1/subscriptionPrices` per territory, attributes `startDate`, `preserveCurrentPrice`, relationships `subscription`, `subscriptionPricePoint`, `territory`. `startDate: null` works only before the subscription is approved; an APPROVED one returns 409 STATE_ERROR "Initial price cannot be created again after subscription is approved", so send tomorrow's date (`YYYY-MM-DD`). The new row then shows with that `startDate` until it takes effect.
- IAP: `POST /v1/inAppPurchasePriceSchedules` with `baseTerritory` and `manualPrices` as inline `inAppPurchasePrices` (`${priceN}` ids) pointing at price points. Replaces every manual price; territories not listed fall back to automatic (equalized) prices. About 110 inline prices in one request is accepted. Takes effect at once, also for approved IAPs.
- App: `POST /v1/appPriceSchedules`, same shape with `appPrices` and `appPricePoints`.

Price point ids are base64 JSON (`{"s": product, "t": territory, "p": tier}`); treat them as opaque. Equalizing a lower USA point is how a band target is found: one call per band per product instead of paging every territory's 800 points.

## Products

- IAP: `POST /v2/inAppPurchases` (note v2), localization `POST /v1/inAppPurchaseLocalizations` with relationship `inAppPurchaseV2`.
  Price: `POST /v1/inAppPurchasePriceSchedules` with a USA base; Apple equalizes the rest. Availability: `POST /v1/inAppPurchaseAvailabilities`.
- Price points are per product. Find the USA point whose `customerPrice` equals the wanted price; if none exists, the tier is not valid (Apple uses fixed tiers, 0.99, 1.99, 2.99 ...). Compare as `Decimal`, not float.
- Subscriptions: group first (`referenceName`, localization with `customAppName`), then subscription (`groupLevel` 1 is the highest tier), then, in this order: localization, availability, USA price, equalized prices for every other territory (`/v1/subscriptionPricePoints/{usaPoint}/equalizations`). Setting prices before availability fails.
- Per-territory price POSTs can fail individually; the script reports the failures and continues. A territory without a price is simply not sold there.
- Changing the price of a live subscription is a price change with consent rules for existing subscribers. The script will not do it; use the web UI.
- Text limits that bite: display name 30, description 45 (IAP) or around 55 (subscription). Longer text gives an unhelpful 409.
- Review screenshot is required before submission, must be a flat PNG, and goes through the same reserve, PUT, commit flow as app screenshots. A previous half-finished upload (state not COMPLETE) must be DELETEd and redone.
- Free trial: `POST /v1/subscriptionIntroductoryOffers` with `offerMode FREE_TRIAL`, `duration`, `numberOfPeriods 1`. Least tested part of the toolkit; if it errors, set the trial in the web UI.
- States: `MISSING_METADATA` means something above is absent (usually the review screenshot, a localization, or a price). `READY_TO_SUBMIT` means complete. `WAITING_FOR_REVIEW` after the version is submitted with it.
- The first product of an app must be selected on the version page in the web UI and ships with that version.

## Screenshots

Flow per screenshot: `POST /v1/appScreenshotSets` once per display type, then per file
`POST /v1/appScreenshots` (fileName, fileSize) which returns `uploadOperations`; `PUT` each byte range to its URL with the given headers; `PATCH` `{uploaded: true, sourceFileChecksum: <md5>}`; poll `assetDeliveryState` until `COMPLETE`. Finally `PATCH /v1/appScreenshotSets/{id}/relationships/appScreenshots` with the ids in order, because completion order is not upload order.

- PNG, no alpha channel. 10 per set maximum.
- Existing sets are replaced wholesale (delete then upload) so order and content always match the folder. Matching `sourceFileChecksum`s skip the set.
- Sizes: 6.9 and 6.7 inch iPhone sets both live in `APP_IPHONE_67` (1320x2868 or 1290x2796). 6.5 inch is `APP_IPHONE_65` (1242x2688 or 1284x2778). 13 inch iPad is `APP_IPAD_PRO_3GEN_129` (2048x2732 or 2064x2752). iPad shots are required when the app supports iPad.

## Review details and submission

- `appStoreReviewDetail`: POST when absent (relationship `appStoreVersion`), PATCH otherwise. Demo password is write-only; the API never returns it.
- Submission uses the reviewSubmissions flow: `POST /v1/reviewSubmissions` (platform IOS), `POST /v1/reviewSubmissionItems` linking the `appStoreVersion`, then `PATCH` the submission `{submitted: true}`. Only one submission can be open per platform, and a submission already `WAITING_FOR_REVIEW` or `IN_REVIEW` blocks a new one.
- States of a version: `PREPARE_FOR_SUBMISSION`, `WAITING_FOR_REVIEW`, `IN_REVIEW`, `PENDING_DEVELOPER_RELEASE`, `READY_FOR_SALE`, `REJECTED`, `METADATA_REJECTED`, `DEVELOPER_REJECTED`.

## TestFlight

- A build takes 5 to 30 minutes to process after upload and can take a few minutes to appear at all. Poll `/v1/builds?filter[app]=ID&filter[version]=N` until `processingState` is `VALID`. `FAILED` or `INVALID` means read Apple's email.
- `usesNonExemptEncryption` null blocks the build behind a compliance prompt; set it with PATCH, or set `ITSAppUsesNonExemptEncryption` in Info.plist so builds arrive cleared.
- What to test: `betaBuildLocalizations` with `whatsNew`. POST if none, PATCH otherwise.
- Internal groups with `hasAccessToAllBuilds` get builds automatically, and PATCHing or adding builds to them returns 409. Skip them. Internal testers need no Beta App Review.
- External groups: attach with `POST /v1/betaGroups/{id}/relationships/builds`. The first build needs Beta App Review (`betaAppReviewSubmissions`), which needs the Beta App Review contact filled in and a beta description. Public link: `publicLinkEnabled`, optional `publicLinkLimit`.

## Bundle IDs and capabilities

`GET /v1/bundleIds?filter[identifier]=` is a prefix match; compare exact identifiers. Capability types: `GAME_CENTER`,
`PUSH_NOTIFICATIONS`, `ICLOUD`, `APPLE_ID_AUTH` (Sign in with Apple), `ASSOCIATED_DOMAINS`, `IN_APP_PURCHASE` (on by default).
`APPLE_ID_AUTH` and `ICLOUD` need `settings` on create; the script sends the defaults, untested against a fresh app.

## Game Center

- Order: `gameCenterDetails` for the app, then leaderboards and achievements under it, then a `localizations` child for each, then (optional) achievement image via the asset flow, then `gameCenterAppVersions` for the version.
- `gameCenterAppVersions`: `enabled` is rejected on create (409). Create bare, then PATCH `enabled: true`.
- Recurring leaderboards: `recurrenceStartDate` must not be in the past (`RECURRENCE_START_CANNOT_BE_PAST`), the duration must be a time based ISO 8601 value (`PT24H`, not `P1D`), and a rule like `FREQ=DAILY;INTERVAL=1`.
- Achievement points across all achievements may not exceed 1000. Lower points before raising others when rebalancing.

## Common errors

| Symptom | Cause and fix |
|---|---|
| 401 | Token expired or wrong key id/issuer; check the env file paths. |
| 403 with "agreement" | Account Holder must accept the latest agreements in the web UI. |
| 403 on a resource | The key role is too low (needs App Manager or Admin). |
| 409 `ENTITY_ERROR.ATTRIBUTE.INVALID` | Read `source.pointer`; usually a length limit or an attribute not allowed on create. |
| 409 STATE_ERROR | Resource is not editable in its current state (version in review, group internal). |
| Price point not found | Not a valid Apple tier for that product. |
| Screenshot stuck `UPLOAD_COMPLETE` | Wrong checksum or missing commit PATCH; delete and re-upload. |
| Screenshot `FAILED` | Wrong dimensions or alpha channel. |
