# Steps the user does by hand

Give these at the moment they are needed, with the exact values from `ship.json`.
Wait for the user to say it is done, then continue.

## Apple Developer Program

https://developer.apple.com/programs/enroll/ . Paid yearly. An individual
account shows the person's name as the seller; an organization needs a D-U-N-S
number and shows the company name. Approval can take a day or more for
organizations.

## App Store Connect API key

App Store Connect, Users and Access, Integrations, App Store Connect API, Team
Keys, generate. Role: App Manager (Admin if it must also manage certificates).
Download the `.p8` once (it cannot be downloaded again) and keep it outside every
repo, for example `~/.config/<app>/AuthKey_<KEYID>.p8`. Then write an env file
next to it:

```
ASC_KEY_ID=<Key ID>
ASC_ISSUER_ID=<Issuer ID shown above the keys table>
ASC_KEY_PATH=/absolute/path/AuthKey_<KEYID>.p8
```

`chmod 600` both files and set `ship.json` `secrets.ascEnv` to the env file path.

## Bundle ID

`ship-store bundle-id` registers it through the API with the capabilities the app
needs. If the user prefers the web: Certificates, Identifiers and Profiles,
Identifiers, plus, App IDs.

## App record

App Store Connect, Apps, plus, New App:

| Field | Value |
|---|---|
| Platforms | iOS |
| Name | `listing.<primaryLocale>.name` (must be unique on the store) |
| Primary Language | `app.primaryLocale` |
| Bundle ID | `app.bundleId` |
| SKU | `app.sku` (any unique text; the bundle ID is fine) |
| User Access | Full Access |

Then copy the Apple ID number from App Information into `ship.json` `app.ascAppId`.

## Agreements, tax and banking

Only for paid apps or in-app purchases. App Store Connect, Business: accept the
Paid Apps agreement, add bank account and tax forms. Purchases fail until it is
active.

## App Privacy

App Store Connect, the app, App Privacy. Enter the answers from
`.ship/listing/app-privacy.md` and publish.

## RevenueCat (if chosen)

Create a project at https://app.revenuecat.com, add the App Store app with the
bundle ID, upload an In-App Purchase key (App Store Connect, Users and Access,
Integrations, In-App Purchase), set the App Store Server Notifications URL it
shows into App Store Connect (App Information), then create the entitlement,
import products, create the `default` offering and design the paywall.

## Analytics (if chosen)

Create a PostHog or TelemetryDeck project and save the project key in the env
file named in `secrets.posthogEnv`.

## Domain and hosting

Optional. Any registrar. Point it at the host chosen in ship-landing. The user
signs up for the host themselves.

## Sandbox tester

App Store Connect, Users and Access, Sandbox, Test Accounts. Then on the device:
Settings, App Store, Sandbox Account.
