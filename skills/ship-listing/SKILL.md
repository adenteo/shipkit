---
name: ship-listing
description: >-
  Write the App Store listing for an iOS app and do its ASO: keyword research
  scored for popularity and difficulty from real App Store search suggestions
  and the apps that rank, rank tracking, the 30 character name and subtitle,
  the 100 character keyword field, promotional text, description, categories,
  age rating answers, App Privacy answers derived from what the app collects,
  and the notes for App Review, all checked against Apple's limits and common
  rejection causes. Use when the user needs App Store copy, ASO, keyword
  research, keyword rankings, a subtitle, an app description, privacy labels,
  age rating, review notes, or when the ship skill reaches its listing step.
---

# ship-listing

Everything here ends up in `ship.json` (`listing.<locale>`, `store.*`) and is sent
to App Store Connect by `ship-store`. Drafts and research live in `.ship/listing/`.

```bash
L="${CLAUDE_SKILL_DIR}/scripts/listing.py"
python3 "$L" research "seed term" "another seed" [--country us]
python3 "$L" keywords "term" "term" ... [--expand] [--country us] [--app-id 123]
python3 "$L" rank --app-id 123 [terms...] [--country us]
python3 "$L" lint [--locale en-US]
python3 "$L" privacy
```

No account or paid ASO tool needed. Apple publishes no search volumes, so
`keywords` builds two proxies from public endpoints:

- **Popularity (5 to 100)**: type the phrase one letter at a time; the fewer
  letters Apple needs before suggesting it (or a longer search that starts with
  it), the more people search it. 5 is the floor: Apple never suggests it, so the
  volume is unknown and probably tiny.
- **Difficulty (0 to 100)**: median ratings of the top ten apps for the term (log
  scale) and how many of them carry the exact phrase in their name.
- **Opportunity** = popularity x (100 - difficulty) / 100, and **Rank** = where
  the app sits in the top 200 (pass `--app-id`, the number in its App Store URL).

Use them to compare candidates with each other, not as volumes. Results are
cached for three days in `.ship/listing/cache/`; Apple rate limits the search
API, so 20 terms take about two minutes.

## 1. Research (15 minutes, not a day)

1. Write five to eight seed terms the way a stranger would search for the app's
   job, not its name ("bedtime journal", "gratitude diary", "sleep diary").
2. Run `keywords` on them with `--expand`, which adds Apple's autocomplete
   suggestions for each seed and scores up to 40 terms.
3. **Cut for intent before anything else.** A keyword is worth having only when
   the person typing it wants this app. Two traps look attractive because their
   popularity is high: too generic ("tracker" for a calorie tracker: the searcher
   may want flights or sleep) and adjacent but wrong ("muscle growth" for a calorie
   tracker: they want workouts, and the installs that come do not stay).
4. **Pick fights the app can win.** For a new app, difficulty above about 60 is a
   bet on the future, not traffic now; keep such a term in the name only if it is
   the app's identity, and fill the keyword field with winnable terms. An
   established app (thousands of ratings) can contest 50 to 70.
5. Choose the **main keyword** (strong popularity, winnable, exact intent), a
   **second keyword** for the subtitle, and the rest for the keyword field. Never
   build the name on a floor-popularity term. Show the user the scored table and
   get a yes on the main and second keyword before writing copy.

## 2. Name, subtitle, keywords

Apple indexes the name, subtitle and keyword field together, and matches words
across them, so never repeat a word between them.

- **Name (30)**: the main keyword leads, the brand follows, when the brand is not
  yet known: `Bedtime Journal: Nightpage` usually beats `Nightpage: Bedtime
  Journal`, because people search the job, not a brand they have never heard of.
  Make brand-first a deliberate choice, not a default. No "free", no "best", no
  Apple trademarks (iPhone, iPad, Apple, iOS).
- **Subtitle (30)**: led by the second keyword, a benefit in plain words, not a
  slogan: `Calm writing before sleep`.
- **Keywords (100)**: comma separated, no spaces, singular forms only (plurals
  match), no words already in the name or subtitle, no competitor brand names, no
  category name ("app", "health" are free already).

## 3. Promotional text, description, what's new

- **Promotional text (170)**: the freshest reason to download today. It can change
  any time without a new build, so use it for updates and seasons.
- **Description (4000)**: not indexed for search, but read by people deciding. Open
  with one or two lines that say what it does for whom; most readers stop at "more".
  Then short sections with plain headings: what you can do, what makes it
  different, privacy, pricing. Describe only features in the build that will be
  reviewed. With subscriptions, end with the renewal terms and links to the Terms
  of Use and Privacy Policy (from `site.urls`).
- **What's New**: skip for version 1.0. For updates, two or three lines a user cares
  about, not "bug fixes".
- Copyright: `<year> <owner>`.

Write the copy into `ship.json` `listing.<locale>`, run `lint`, fix every FAIL and
think about every WARN. Show the user the name, subtitle and first three lines of
the description side by side with two competitors and ask for approval.

## 4. Categories and age rating

- Pick `store.primaryCategory` (where it competes for charts) and an optional
  `secondaryCategory` using App Store Connect IDs such as `PRODUCTIVITY`,
  `HEALTH_AND_FITNESS`, `LIFESTYLE`, `GAMES_PUZZLE` (a game's primary is `GAMES`
  with a subcategory).
- Age rating: `ship-store age-rating` sets every question to none and derives ads
  and in-app purchases from `ship.json`. Put only the answers that differ in
  `store.ageRating`, using the API's field names. To see the current field names,
  run `ship-store`'s `asc.py raw GET /v1/appInfos/<id>/ageRatingDeclaration`.
  Answer honestly: user-generated content, chat, unrestricted web access, gambling
  mechanics, and medical or wellness claims all change the rating.

## 5. App Privacy answers

Run `privacy`. It works out the data types from `features` (accounts, analytics,
purchases, ads, push, Game Center), saves them to `store.privacyLabels`, and
writes `.ship/listing/app-privacy.md` with the exact answers. Then search the code
for any SDK it does not know about (crash reporting, attribution, maps, support
chat) and add what they collect. These answers are entered by hand in App Store
Connect (there is no API); ship-store walks the user through it.

## 6. Notes for App Review

Write `store.review.notes` so a reviewer can test everything in five minutes:

- How to start (no account needed, or the demo account in `store.review`; never put
  the password in notes, ship-store sends it from the env var).
- Where every paid feature and product is, and how to reach the paywall.
- Anything non-obvious: permissions and why they are asked, features that need a
  second device or a specific time, hardware needed.
- For games and anything that looks like a common template: what is original
  about it (guideline 4.3 spam rejections are common for simple games).
- Contact details in `store.review` (first name, last name, email, phone).

## 7. After launch: track and adjust

Run `rank --app-id <id>` weekly; it appends to `.ship/listing/ranks.csv`. A new
app ranking around 100 to 1000 for its own subtitle term has an authority
problem (too few installs and ratings), not a keyword problem: more keywords will
not fix it, installs and ratings will. Swap keyword-field terms that stay beyond
200 after a month for the next best scored ones; keywords change with any new
version, the name and subtitle need one too.

Other languages are ship-localize's job, with keywords scored per country
(`keywords ... --country de`).

Tick the listing line in `.ship/PROGRESS.md`.
