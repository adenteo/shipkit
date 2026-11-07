#!/usr/bin/env python3
"""
App Store listing helpers. No account needed; uses Apple's public search endpoints.

  listing.py research TERM [TERM ...] [--country us]
      App Store search suggestions for each seed term (what people actually type)
      and the top apps ranking for it. Writes .ship/listing/research.md.
  listing.py keywords TERM [TERM ...] [--country us] [--expand] [--app-id ID]
      Scores each keyword: popularity (how few letters Apple needs before it
      suggests the phrase), difficulty (ratings and exact-title use among the top
      10 apps), opportunity, and where the app ranks. Writes
      .ship/listing/keywords.<country>.json and .md.
  listing.py rank --app-id ID [TERM ...] [--country us]
      Where the app ranks (top 200) for each term; defaults to the scored keywords.
      Appends to .ship/listing/ranks.csv so movement can be tracked.
  listing.py lint [--locale en-US]
      Checks the listing in ship.json against App Store limits and common rejection causes.
  listing.py privacy
      Works out the App Privacy answers from ship.json features, saves them to
      store.privacyLabels and writes .ship/listing/app-privacy.md for the user to click in.
"""
import argparse
import csv
import datetime
import hashlib
import json
import math
import os
import plistlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

STOREFRONTS = {"us": "143441", "gb": "143444", "ca": "143455", "au": "143460", "nz": "143461", "ie": "143449",
               "sg": "143464", "de": "143443", "at": "143445", "ch": "143459", "fr": "143442", "be": "143446",
               "nl": "143452", "es": "143454", "pt": "143453", "it": "143450", "se": "143456", "no": "143457",
               "dk": "143458", "fi": "143447", "pl": "143478", "tr": "143480", "jp": "143462", "kr": "143466",
               "cn": "143465", "tw": "143470", "hk": "143463", "in": "143467", "id": "143476", "th": "143475",
               "vn": "143471", "ph": "143474", "my": "143473", "br": "143503", "mx": "143468", "sa": "143479",
               "ae": "143481", "il": "143491", "za": "143472"}
LIMITS = {"name": 30, "subtitle": 30, "keywords": 100, "promotionalText": 170,
          "description": 4000, "whatsNew": 4000}


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        sys.exit(f"Could not read {path}.")


def get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "shipkit/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


# ---------------------------------------------------------------------------
# research
# ---------------------------------------------------------------------------

CACHE_DAYS = 3


def cached(url, headers=None, cache_dir=None, pause=0.0):
    """GET with a small disk cache (Apple's search endpoints rate limit hard) and one backoff retry."""
    path = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        key = hashlib.sha1((url + json.dumps(headers or {}, sort_keys=True)).encode()).hexdigest()
        path = os.path.join(cache_dir, key)
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < CACHE_DAYS * 86400:
            with open(path, "rb") as f:
                return f.read()
    for attempt in range(3):
        try:
            time.sleep(pause)
            body = get(url, headers)
            break
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 503) and attempt < 2:
                time.sleep(20 * (attempt + 1))
                continue
            raise
    if path:
        with open(path, "wb") as f:
            f.write(body)
    return body


def suggestions(term, country, cache_dir=None):
    front = STOREFRONTS.get(country, "143441")
    url = ("https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa/hints?clientApplication=Software&term="
           + urllib.parse.quote(term))
    try:
        data = plistlib.loads(cached(url, {"X-Apple-Store-Front": f"{front}-1,29"}, cache_dir, 0.1))
        return [h["term"] for h in data.get("hints", [])]
    except Exception as e:  # undocumented endpoint: degrade quietly
        return [f"(suggestions unavailable: {e.__class__.__name__})"]


def top_apps(term, country, limit=10, cache_dir=None, pause=0.0):
    url = (f"https://itunes.apple.com/search?entity=software&limit={limit}&country={country}&term="
           + urllib.parse.quote(term))
    try:
        return json.loads(cached(url, None, cache_dir, pause)).get("results", [])
    except Exception:
        return []


def cmd_research(a):
    out = [f"# Keyword research ({a.country.upper()})", "",
           "Suggestions are App Store autocomplete for each seed: real searches, roughly in order of popularity. "
           "Top apps show who you compete with for that search.", ""]
    cache_dir = os.path.join(a.shipdir, "listing", "cache")
    for term in a.terms:
        out += [f"## {term}", "", "**People also search:** " + ", ".join(suggestions(term, a.country, cache_dir)), "",
                "| App | Ratings | Genre | Price |", "|---|---|---|---|"]
        for r in top_apps(term, a.country, 10, cache_dir):
            out.append(f"| {r.get('trackName', '')} | {r.get('userRatingCount', 0):,} | "
                       f"{r.get('primaryGenreName', '')} | {r.get('formattedPrice', '')} |")
        out.append("")
    text = "\n".join(out)
    os.makedirs(os.path.join(a.shipdir, "listing"), exist_ok=True)
    path = os.path.join(a.shipdir, "listing", "research.md")
    with open(path, "w") as f:
        f.write(text)
    print(text)
    print(f"\nSaved {path}")


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------

def words(s):
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def cmd_lint(a):
    ship = load(a.ship)
    listing = ship.get("listing", {}).get(a.locale)
    if not listing:
        sys.exit(f"No listing for {a.locale} in ship.json.")
    errors, warns = [], []
    for key, limit in LIMITS.items():
        n = len(listing.get(key) or "")
        if n > limit:
            errors.append(f"{key} is {n} characters (limit {limit})")
    for key in ("name", "subtitle", "keywords", "description"):
        if not (listing.get(key) or "").strip() and key != "subtitle":
            errors.append(f"{key} is empty")
    kw = listing.get("keywords") or ""
    if ", " in kw:
        warns.append("keywords: remove spaces after commas, they waste characters")
    kws = [k.strip().lower() for k in kw.split(",") if k.strip()]
    dupes = sorted({k for k in kws if kws.count(k) > 1})
    if dupes:
        warns.append(f"keywords repeated: {', '.join(dupes)}")
    in_title = words(listing.get("name")) | words(listing.get("subtitle"))
    wasted = sorted({w for k in kws for w in k.split() if w in in_title})
    if wasted:
        warns.append(f"keywords already in name or subtitle (Apple indexes those, so these waste space): {', '.join(wasted)}")
    plural = sorted({k for k in kws if k.endswith("s") and k[:-1] in kws})
    if plural:
        warns.append(f"singular and plural both listed (Apple matches both): {', '.join(plural)}")
    alltext = " ".join(str(listing.get(k) or "") for k in LIMITS)
    low = alltext.lower()
    for pat, why in [
        (r"\b(android|google play|play store)\b", "mentions another platform (guideline 2.3.10)"),
        (r"\b(best|#1|number one|top rated)\b", "unprovable superlative; reviewers and users distrust it"),
        (r"\b(beta|test version|coming soon)\b", "describes the app as unfinished (2.2)"),
        (r"\bfree\b", "says free: fine if true, but not in the name or subtitle, and not if a paywall blocks core use"),
        (r"\$\s?\d", "a price in the copy goes stale across countries; let the App Store show prices"),
    ]:
        if re.search(pat, low):
            warns.append(why)
    for field in ("name", "subtitle"):
        if re.search(r"\b(apple|iphone|ipad|ios)\b", (listing.get(field) or "").lower()):
            errors.append(f"{field} uses an Apple trademark (iPhone, iPad, Apple, iOS), which App Review rejects")
    products = ship.get("monetization", {}).get("products", [])
    if any(p.get("type") == "subscription" for p in products):
        desc = (listing.get("description") or "").lower()
        if "terms" not in desc or "privacy" not in desc:
            errors.append("subscriptions: the description must link to the Terms of Use (EULA) and the Privacy Policy (3.1.2)")
    if "—" in alltext or "–" in alltext:
        warns.append("contains em or en dashes; fine for Apple, but check it matches your house style")
    for e in errors:
        print(f"FAIL  {e}")
    for w in warns:
        print(f"WARN  {w}")
    used = {k: f"{len(listing.get(k) or '')}/{v}" for k, v in LIMITS.items()}
    print("\n" + "  ".join(f"{k} {v}" for k, v in used.items()))
    if not errors and not warns:
        print("Listing looks clean.")
    sys.exit(1 if errors else 0)


# ---------------------------------------------------------------------------
# privacy
# ---------------------------------------------------------------------------

def privacy_labels(ship):
    f = ship.get("features", {})
    labels = []

    def add(category, dtype, linked, tracking, purposes, source):
        labels.append({"category": category, "type": dtype, "linkedToUser": linked,
                       "usedForTracking": tracking, "purposes": purposes, "because": source})

    identified = f.get("accounts", "none") != "none"
    if identified:
        add("Contact Info", "Email Address", True, False, ["App Functionality"], "accounts (Sign in with Apple may share email)")
        add("Contact Info", "Name", True, False, ["App Functionality"], "accounts")
        add("Identifiers", "User ID", True, False, ["App Functionality"], "accounts")
    if f.get("analytics") == "posthog":
        add("Usage Data", "Product Interaction", identified, False, ["Analytics"], "PostHog events")
        add("Identifiers", "User ID" if identified else "Device ID", identified, False, ["Analytics"], "PostHog distinct id")
    elif f.get("analytics") == "telemetrydeck":
        add("Usage Data", "Product Interaction", False, False, ["Analytics"], "TelemetryDeck signals")
    if f.get("payments") in ("revenuecat", "storekit"):
        add("Purchases", "Purchase History", identified, False, ["App Functionality"],
            "RevenueCat customer record" if f.get("payments") == "revenuecat" else "StoreKit transactions checked by the app")
    if f.get("ads") == "admob":
        add("Identifiers", "Device ID", False, True, ["Third-Party Advertising"], "AdMob (IDFA when ATT allowed)")
        add("Usage Data", "Advertising Data", False, True, ["Third-Party Advertising"], "AdMob")
        add("Location", "Coarse Location", False, True, ["Third-Party Advertising"], "AdMob uses IP-derived location")
        add("Diagnostics", "Crash Data", False, False, ["Analytics"], "Google Mobile Ads SDK")
    if f.get("notifications") == "remote":
        add("Identifiers", "Device ID", identified, False, ["App Functionality"], "push token stored server side")
    if f.get("gameCenter"):
        add("Gameplay Content", "Gameplay Content", True, False, ["App Functionality"], "Game Center scores")
    # Merge duplicate types, unioning purposes.
    merged = {}
    for l in labels:
        k = (l["category"], l["type"])
        if k in merged:
            m = merged[k]
            m["purposes"] = sorted(set(m["purposes"]) | set(l["purposes"]))
            m["linkedToUser"] |= l["linkedToUser"]
            m["usedForTracking"] |= l["usedForTracking"]
            m["because"] += "; " + l["because"]
        else:
            merged[k] = l
    return list(merged.values())


def cmd_privacy(a):
    ship = load(a.ship)
    labels = privacy_labels(ship)
    ship.setdefault("store", {})["privacyLabels"] = labels
    with open(a.ship, "w") as f:
        json.dump(ship, f, indent=2)
        f.write("\n")
    lines = ["# App Privacy answers", "",
             "App Store Connect, your app, App Privacy, Get Started. Answer exactly this. "
             "It must match the privacy policy and what the code really does.", ""]
    if not labels:
        lines += ["**Do you or your third-party partners collect data from this app?** No.", ""]
    else:
        lines += ["**Do you or your third-party partners collect data from this app?** Yes.", "",
                  "| Data type | Linked to the user | Used for tracking | Purposes | Why |", "|---|---|---|---|---|"]
        for l in labels:
            lines.append(f"| {l['category']}: {l['type']} | {'Yes' if l['linkedToUser'] else 'No'} | "
                         f"{'Yes' if l['usedForTracking'] else 'No'} | {', '.join(l['purposes'])} | {l['because']} |")
        if any(l["usedForTracking"] for l in labels):
            lines += ["", "Tracking is declared, so the app must show the App Tracking Transparency prompt before "
                      "any tracking and include NSUserTrackingUsageDescription."]
    lines += ["", "Search the code for other SDKs (crash reporting, attribution, maps, chat) and add what they collect "
              "before submitting. Apple checks this against the binary's privacy manifests."]
    os.makedirs(os.path.join(a.shipdir, "listing"), exist_ok=True)
    path = os.path.join(a.shipdir, "listing", "app-privacy.md")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nSaved {path} and store.privacyLabels in ship.json")


# ---------------------------------------------------------------------------
# keywords and rank
# ---------------------------------------------------------------------------
# Apple publishes no search volumes. Two free signals stand in for them:
#   popularity: autocomplete reach. Type the phrase one letter at a time; the
#     fewer letters Apple needs before it offers the whole phrase, the more people
#     search it. A phrase Apple never suggests, even fully typed, sits at the floor.
#   difficulty: who already ranks. Many ratings among the top ten apps, and many
#     of them carrying the exact phrase in their name, make a term hard to win.
# Both are proxies. Use them to rank candidates against each other, not as volumes.

FLOOR = 5


def norm_term(t):
    return re.sub(r"\s+", " ", t.strip().lower())


def hit(t, hints):
    """Index of the phrase, or of a longer search that starts with it, in a suggestion list."""
    for i, h in enumerate(hints):
        if h == t or h.startswith(t + " "):
            return i
    return None


def popularity(term, country, cache_dir):
    t = norm_term(term)
    full = [norm_term(h) for h in suggestions(t, country, cache_dir)]
    tails = sum(1 for h in full if h.startswith(t + " "))
    if hit(t, full) is None:
        return {"popularity": FLOOR, "letters": None, "position": None, "tails": tails}
    probes = sorted({k for k in (1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 18, 22, 27, 33) if k < len(t)} | {len(t)})
    prev = 0
    for k in probes:
        hints = [norm_term(h) for h in suggestions(t[:k], country, cache_dir)]
        if hit(t, hints) is not None:
            # Narrow down between the last miss and this hit.
            for j in range(prev + 1, k):
                hj = [norm_term(h) for h in suggestions(t[:j], country, cache_dir)]
                if hit(t, hj) is not None:
                    k, hints = j, hj
                    break
            pos = hit(t, hints)
            score = max(FLOOR + 1, min(100, round(100 - (k - 1) * 7 - pos * 2)))
            return {"popularity": score, "letters": k, "position": pos + 1, "tails": tails}
        prev = k
    return {"popularity": FLOOR, "letters": None, "position": None, "tails": tails}


def difficulty(term, results):
    top = results[:10]
    if not top:
        return {"difficulty": 0, "medianRatings": 0, "exactTitles": 0, "giants": 0, "topApp": ""}
    counts = sorted(r.get("userRatingCount", 0) or 0 for r in top)
    median = counts[len(counts) // 2]
    t = norm_term(term)
    exact = sum(1 for r in top if t in norm_term(r.get("trackName", "")))
    giants = sum(1 for c in counts if c >= 100_000)
    rating_score = min(100.0, math.log10(median + 1) / 5 * 100)
    score = round(0.6 * rating_score + 0.4 * exact / len(top) * 100)
    lead = max(top, key=lambda r: r.get("userRatingCount", 0) or 0)
    return {"difficulty": score, "medianRatings": median, "exactTitles": exact, "giants": giants,
            "topApp": f"{lead.get('trackName', '')[:28]} ({lead.get('userRatingCount', 0):,})"}


def rank_of(app_id, results):
    if not app_id:
        return None
    for i, r in enumerate(results, 1):
        if str(r.get("trackId")) == str(app_id):
            return i
    return 0  # not in the top 200


def fmt_rank(r):
    return "" if r is None else (">200" if r == 0 else str(r))


def cmd_keywords(a):
    cache_dir = os.path.join(a.shipdir, "listing", "cache")
    terms = []
    for t in a.terms:
        t = norm_term(t)
        if t and t not in terms:
            terms.append(t)
    if a.expand:
        for seed in list(terms):
            for h in suggestions(seed, a.country, cache_dir):
                h = norm_term(h)
                if h and not h.startswith("(") and h not in terms:
                    terms.append(h)
        terms = terms[:a.max]
    print(f"Scoring {len(terms)} keywords in {a.country.upper()} (cached for {CACHE_DAYS} days)...", file=sys.stderr)
    rows = []
    for i, t in enumerate(terms, 1):
        results = top_apps(t, a.country, 200, cache_dir, pause=1.0)
        row = {"keyword": t, "country": a.country, **popularity(t, a.country, cache_dir), **difficulty(t, results),
               "results": len(results), "rank": rank_of(a.app_id, results)}
        row["opportunity"] = round(row["popularity"] * (100 - row["difficulty"]) / 100)
        rows.append(row)
        print(f"  {i}/{len(terms)} {t}: pop {row['popularity']} diff {row['difficulty']}", file=sys.stderr)
    rows.sort(key=lambda r: (-r["opportunity"], -r["popularity"]))
    out_dir = os.path.join(a.shipdir, "listing")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"keywords.{a.country}.json"), "w") as f:
        json.dump({"date": datetime.date.today().isoformat(), "country": a.country, "appId": a.app_id,
                   "keywords": rows}, f, indent=2)
    lines = [f"# Keyword scores ({a.country.upper()}, {datetime.date.today().isoformat()})", "",
             "Popularity: 100 means Apple suggests the phrase (or a longer search starting with it) after one letter; "
             "each extra letter needed costs 7; "
             f"{FLOOR} means Apple never suggests it (unknown, likely tiny). Difficulty: median ratings of the top 10 "
             "apps (log scale) and how many carry the exact phrase in their name. Opportunity = popularity x (100 - "
             "difficulty) / 100. Relevance is yours to judge: cut anything the searcher would not want this app for.", "",
             "| Keyword | Pop | Diff | Opp | Letters | Tails | Exact titles | Top app (ratings) | Rank |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['keyword']} | {r['popularity']} | {r['difficulty']} | {r['opportunity']} | "
                     f"{r['letters'] or '-'} | {r['tails']} | {r['exactTitles']}/10 | {r['topApp']} | {fmt_rank(r['rank'])} |")
    text = "\n".join(lines) + "\n"
    with open(os.path.join(out_dir, f"keywords.{a.country}.md"), "w") as f:
        f.write(text)
    print(text)
    print(f"Saved {os.path.join(out_dir, f'keywords.{a.country}.md')} and .json")


def cmd_rank(a):
    cache_dir = os.path.join(a.shipdir, "listing", "cache")
    terms = [norm_term(t) for t in a.terms]
    if not terms:
        path = os.path.join(a.shipdir, "listing", f"keywords.{a.country}.json")
        if not os.path.exists(path):
            sys.exit(f"No terms given and no {path}; run keywords first or pass terms.")
        terms = [r["keyword"] for r in load(path)["keywords"]]
    global CACHE_DAYS
    CACHE_DAYS = 0  # ranks move daily; always fetch fresh
    today = datetime.date.today().isoformat()
    log = os.path.join(a.shipdir, "listing", "ranks.csv")
    new = not os.path.exists(log)
    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(log, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "country", "app_id", "keyword", "rank"])
        for t in terms:
            r = rank_of(a.app_id, top_apps(t, a.country, 200, None, pause=1.0))
            w.writerow([today, a.country, a.app_id, t, fmt_rank(r)])
            print(f"{fmt_rank(r):>5}  {t}")
    print(f"\nAppended to {log}. The iTunes Search API approximates App Store search; expect small differences.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ship", default=".ship/ship.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("research"); r.add_argument("terms", nargs="+"); r.add_argument("--country", default="us")
    l = sub.add_parser("lint"); l.add_argument("--locale", default="en-US")
    sub.add_parser("privacy")
    k = sub.add_parser("keywords")
    k.add_argument("terms", nargs="+")
    k.add_argument("--country", default="us")
    k.add_argument("--expand", action="store_true", help="also score each seed's autocomplete suggestions")
    k.add_argument("--max", type=int, default=40, help="cap on keywords after --expand")
    k.add_argument("--app-id", help="App Store ID (from the app's URL) to show its rank")
    rk = sub.add_parser("rank")
    rk.add_argument("terms", nargs="*")
    rk.add_argument("--country", default="us")
    rk.add_argument("--app-id", required=True)
    a = p.parse_args()
    a.shipdir = os.path.dirname(os.path.abspath(a.ship))
    {"research": cmd_research, "lint": cmd_lint, "privacy": cmd_privacy,
     "keywords": cmd_keywords, "rank": cmd_rank}[a.cmd](a)


if __name__ == "__main__":
    main()
