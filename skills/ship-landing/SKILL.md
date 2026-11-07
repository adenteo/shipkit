---
name: ship-landing
description: >-
  Build and deploy the website an App Store app needs: a landing page in the
  app's brand with real screenshots and the App Store badge, plus the privacy
  policy, terms of use and support pages Apple requires, written from what the
  app actually collects (analytics, purchases, accounts, ads). Next.js on Vercel
  or a static site on any host, with SEO basics (titles, social preview,
  sitemap, Smart App Banner). Use when the user needs a landing page, privacy
  policy, terms, support URL, marketing site or app website, or when the ship
  skill reaches its website step.
---

# ship-landing

App Store Connect will not accept an app without a **Support URL** and a
**Privacy Policy URL**, so this step is required even for users who do not care
about a website. The landing page itself is what people see when they search the
app's name, click a link in a post, or open the App Store listing's website link.

Read `ship.json`: `app`, `vibe`, `features`, `site`. Ask for anything missing that
this step needs: `site.owner` (the legal name of the developer or company that
appears on the policies), `site.supportEmail`, and whether they have a domain
(`site.domain`). A free host subdomain is fine to start.

## 1. Policy pages first

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/site.py" policies --out .ship/site-text
```

This writes `privacy.md`, `terms.md` and `support.md` from the features the app
uses. Read all three, fill any `[brackets]`, and fix anything that does not match
the app (for example data the app sends somewhere we did not know about: search
the code for network calls and third-party SDKs). Tell the user plainly that this
is a careful template, not legal advice, and that they should read it.

Rules that come from App Review:

- If the app has accounts, it must let users delete their account inside the app
  (guideline 5.1.1(v)); the support page explains how.
- If it sells subscriptions, the terms carry the auto-renewal wording and the app
  description links to the terms and the privacy policy.
- The privacy policy must match the App Privacy answers (ship-listing builds both
  from the same feature list).

## 2. The landing page

Pick the path from `site.kind`:

- **`static`**: run
  `python3 "${CLAUDE_SKILL_DIR}/scripts/site.py" static --out site` for a working
  site with index, privacy, terms, support, robots.txt and sitemap.xml, using the
  icon, web icons and social image from `.ship/brand/` and the first screenshots
  from `.ship/screenshots/`. The generated home page is a plain starting point:
  redesign `index.html` properly (below) before deploying.
- **`nextjs`**: create the site in `site.dir` (default `site/` or a separate repo)
  with the current `create-next-app`. Read the installed Next.js version's docs
  before writing routing or metadata code. Routes: `/`, `/privacy`, `/terms`,
  `/support`, rendering the markdown from step 1. Put the web icons and `og.png`
  in `public/`. Use the Metadata API for titles, descriptions, Open Graph and the
  Smart App Banner, and add `sitemap.ts` and `robots.ts`.
- **existing site**: add the three pages and the App Store link to it.

What a good app landing page has, top to bottom:

1. The icon, the app name and one line that says what it does for whom.
2. The App Store badge (Apple's official artwork from
   https://tools.applemarketingtools.com, never redrawn) linking to
   `https://apps.apple.com/app/id<ascAppId>`. Before launch: "Coming soon" with an
   email signup or a TestFlight public link instead.
3. Real screenshots from `.ship/screenshots/` (or the raw simulator captures in a
   phone frame). Never mock up screens that do not exist.
4. Three short sections, each one benefit with one screenshot.
5. A short FAQ (pricing, privacy, devices supported).
6. Footer with Support, Privacy, Terms and the contact email.

Use the brand tokens (`.ship/brand/tokens.css` or `theme.ts`) and fonts. It must
look right at 375px wide with no sideways scrolling, and load fast: compress
screenshots to WebP or JPEG around 1200px tall for the web.

SEO basics: a title of the form `<Name>: <what it does>`, a 150 character
description, the social image, `<meta name="apple-itunes-app" content="app-id=...">`
once the app ID exists, a canonical URL, and JSON-LD `SoftwareApplication` with
`operatingSystem: "iOS"`, `applicationCategory` and the price. Never add ratings
or reviews to the structured data that the app has not earned.

## 3. Deploy

Ask before the first production deploy. Options:

- **Vercel**: `npx vercel` for a preview URL, `npx vercel --prod` once approved.
  The user signs in to Vercel themselves.
- **Cloudflare Pages**: `npx wrangler pages deploy site --project-name <name>`.
- **GitHub Pages / Netlify / any static host**: upload the `site` folder.

Then open the deployed privacy and support pages and check they load. Write the
final URLs into `ship.json` `site.urls` (`marketing`, `support`, `privacy`,
`terms`); ship-store sends them to App Store Connect.

Optional: if the app uses universal links, serve
`/.well-known/apple-app-site-association` (JSON, no extension, `application/json`)
with the app's `<teamId>.<bundleId>`.

Tick the website line in `.ship/PROGRESS.md` with the live URLs.
