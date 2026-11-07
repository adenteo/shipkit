#!/usr/bin/env python3
"""
Website pages every App Store app needs, written from ship.json.

  site.py policies --out DIR   privacy.md, terms.md, support.md (for any site, including Next.js)
  site.py static --out DIR     a complete static site: index, privacy, terms, support,
                               robots.txt, sitemap.xml (uses .ship/brand outputs if present)

The privacy policy is built from what the app actually uses (features in ship.json).
It is a solid starting point, not legal advice: the user must read it and adjust it.
"""
import argparse
import datetime
import html
import json
import os
import re
import shutil
import sys

EULA = "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/"


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        sys.exit(f"Could not read {path}. Run the ship intake first.")


def facts(ship):
    app, site, feat = ship.get("app", {}), ship.get("site", {}), ship.get("features", {})
    owner = site.get("owner") or ship.get("store", {}).get("copyright", "").lstrip("0123456789 ").strip()
    return {
        "name": app.get("name") or "the app",
        "owner": owner or "[developer or company name]",
        "email": site.get("supportEmail") or "[support email]",
        "domain": site.get("domain") or "",
        "tagline": app.get("tagline") or "",
        "oneLiner": app.get("oneLiner") or "",
        "ascAppId": app.get("ascAppId") or "",
        "payments": feat.get("payments", "none"),
        "analytics": feat.get("analytics", "none"),
        "ads": feat.get("ads", "none"),
        "accounts": feat.get("accounts", "none"),
        "notifications": feat.get("notifications", "none"),
        "gameCenter": feat.get("gameCenter", False),
        "subscriptions": any(p.get("type") == "subscription" for p in ship.get("monetization", {}).get("products", [])),
        "today": datetime.date.today().strftime("%-d %B %Y"),
    }


# ---------------------------------------------------------------------------
# Policy text (markdown)
# ---------------------------------------------------------------------------

def privacy_md(f):
    collect, providers = [], []
    if f["accounts"] != "none":
        collect.append("**Account details.** When you sign in we receive an account identifier and, if you choose to share it, "
                       "your name and email address (with Sign in with Apple you can hide your real email). We use them to keep "
                       "your account and data in sync. You can delete your account from inside the app at any time, which deletes "
                       "the data linked to it.")
    if f["analytics"] == "posthog":
        collect.append("**Usage data.** We record how the app is used (for example which screens are opened and which features "
                       "are used), with a random identifier, device type, operating system and app version. We use this to "
                       "understand what works and to fix problems. It is not used for advertising.")
        providers.append("PostHog (product analytics)")
    elif f["analytics"] == "telemetrydeck":
        collect.append("**Usage signals.** We receive anonymous signals about how the app is used (for example that a feature "
                       "was opened), without personal data. We use them to improve the app.")
        providers.append("TelemetryDeck (anonymous usage analytics)")
    if f["payments"] in ("revenuecat", "storekit"):
        collect.append("**Purchases.** Payments are handled by Apple. We never see your card or payment details. We receive "
                       "a record of what you bought so we can unlock it on your devices.")
        if f["payments"] == "revenuecat":
            providers.append("RevenueCat (purchase and subscription status)")
    if f["ads"] == "admob":
        collect.append("**Advertising.** The app shows ads from Google AdMob. Google may collect device identifiers and usage "
                       "data to show and measure ads. Personalised ads are only shown if you allow tracking when asked; you can "
                       "change this any time in Settings, Privacy and Security, Tracking.")
        providers.append("Google AdMob (advertising), see https://policies.google.com/privacy")
    if f["notifications"] == "remote":
        collect.append("**Notifications.** If you allow notifications, we store a push token for your device so we can send "
                       "them. Turning notifications off in Settings stops them.")
    if f["gameCenter"]:
        collect.append("**Game Center.** If you use Game Center, Apple shares your player identifier and scores with us to show "
                       "leaderboards. Game Center is optional.")
    if not collect:
        collect.append("**Nothing personal.** The app does not collect personal data. What you create stays on your device "
                       "(and in your own iCloud account if you use iCloud).")

    lines = [f"# Privacy Policy", "", f"Last updated: {f['today']}", "",
             f"This policy explains what {f['name']} (\"the app\"), made by {f['owner']}, collects and why. "
             "We collect as little as we can.", "", "## What we collect", ""]
    lines += [f"- {c}" for c in collect]
    lines += ["", "## How we use it", "",
              "Only to run the app, keep your purchases and data working, understand and improve the app, and answer you "
              "when you contact us. We do not sell your data.", ""]
    if providers:
        lines += ["## Services we use", "", "These companies process data for us under their own privacy terms:", ""]
        lines += [f"- {p}" for p in providers] + [""]
    lines += ["## How long we keep it", "",
              "We keep data only as long as we need it for the purposes above, then delete it or make it anonymous.", "",
              "## Your choices and rights", "",
              f"You can ask us what data we hold about you, ask us to correct or delete it, or ask any question about "
              f"this policy by emailing {f['email']}. Depending on where you live (for example under the GDPR or CCPA) "
              "you may have further rights; we honour them.", "",
              "## Children", "",
              f"{f['name']} is not directed at children under 13 and we do not knowingly collect their personal data.", "",
              "## Changes", "",
              "If this policy changes we will update the date above, and tell you in the app if the change matters.", "",
              "## Contact", "", f"{f['owner']}, {f['email']}", ""]
    return "\n".join(lines)


def terms_md(f):
    lines = ["# Terms of Use", "", f"Last updated: {f['today']}", "",
             f"{f['name']} is provided by {f['owner']}. By downloading or using the app you agree to Apple's "
             f"[Licensed Application End User License Agreement]({EULA}) and these terms.", ""]
    if f["subscriptions"]:
        lines += ["## Subscriptions", "",
                  "- Payment is charged to your Apple Account when you confirm the purchase.",
                  "- Subscriptions renew automatically unless cancelled at least 24 hours before the end of the current period.",
                  "- Your account is charged for renewal within 24 hours before the end of the current period.",
                  "- You can manage and cancel subscriptions in your Apple Account settings after purchase.",
                  "- If a free trial is offered, any unused part of it ends when you buy a subscription.", ""]
    elif f["payments"] != "none":
        lines += ["## Purchases", "", "Purchases are made through Apple and are covered by Apple's terms, "
                  "including its refund policy.", ""]
    lines += ["## Using the app", "",
              "Use the app lawfully and do not try to break, reverse engineer or misuse it. We may update or change "
              "features over time.", "",
              "## Disclaimer", "",
              "The app is provided as is. To the extent the law allows, we are not liable for indirect or "
              "consequential losses from using it.", "",
              "## Contact", "", f"{f['email']}", ""]
    return "\n".join(lines)


def support_md(f):
    q = [("How do I contact you?", f"Email {f['email']}. We usually reply within two working days.")]
    if f["payments"] != "none":
        q.append(("How do I restore my purchase?", "Open the app, go to Settings and tap Restore Purchases, signed in to the "
                  "same Apple Account you bought with."))
    if f["subscriptions"]:
        q.append(("How do I cancel my subscription?", "On your iPhone open Settings, tap your name, then Subscriptions, pick "
                  f"{f['name']} and tap Cancel. Refunds are handled by Apple at reportaproblem.apple.com."))
    if f["accounts"] != "none":
        q.append(("How do I delete my account?", "In the app, open Settings and tap Delete Account. This deletes your account "
                  "and the data linked to it. You can also email us and we will do it for you."))
    q.append(("What data do you collect?", "See our Privacy Policy."))
    lines = ["# Support", "", f"Need help with {f['name']}? Email **{f['email']}** and include your device and iOS "
             "version if something is not working.", "", "## Common questions", ""]
    for question, answer in q:
        lines += [f"### {question}", "", answer, ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Static site
# ---------------------------------------------------------------------------

def md_to_html(md):
    """Enough markdown for the policy pages: headings, lists, paragraphs, bold, links."""
    out, in_list = [], False
    for line in md.splitlines():
        esc = html.escape(line)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        esc = re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', esc)
        esc = re.sub(r"(?<![\"'>])(https?://[^\s<,]+[^\s<,.])", r'<a href="\1">\1</a>', esc)
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{esc[2:]}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.startswith("### "):
            out.append(f"<h3>{esc[4:]}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{esc[3:]}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{esc[2:]}</h1>")
        elif line.strip():
            out.append(f"<p>{esc}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def page(f, ship, title, body, desc, path):
    pal = ship.get("vibe", {}).get("palette", {})
    fonts = ship.get("vibe", {}).get("fonts", {})
    display, text_font = fonts.get("display") or "", fonts.get("body") or ""
    fams = "&".join("family=" + x.replace(" ", "+") + ":wght@400;600;700" for x in dict.fromkeys([display, text_font]) if x)
    font_link = f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n<link href="https://fonts.googleapis.com/css2?{fams}&display=swap" rel="stylesheet">' if fams else ""
    base = f"https://{f['domain']}" if f["domain"] else ""
    banner = f'<meta name="apple-itunes-app" content="app-id={f["ascAppId"]}">' if f["ascAppId"] else ""
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
{f'<link rel="canonical" href="{base}{path}">' if base else ''}
<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="{base}/og.png"><meta name="twitter:card" content="summary_large_image">
{banner}
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
{font_link}
<style>
:root{{--bg:{pal.get('bg') or '#ffffff'};--surface:{pal.get('surface') or '#f5f5f5'};--text:{pal.get('text') or '#111111'};
--primary:{pal.get('primary') or '#111111'};--accent:{pal.get('accent') or '#555555'};
--display:"{display or 'system-ui'}",system-ui,sans-serif;--body:"{text_font or 'system-ui'}",system-ui,sans-serif}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:17px/1.6 var(--body)}}
main{{max-width:720px;margin:0 auto;padding:48px 20px 80px}}
h1,h2,h3{{font-family:var(--display);line-height:1.15}}h1{{font-size:clamp(34px,6vw,52px);margin:0 0 12px}}
a{{color:var(--primary)}}nav{{display:flex;gap:18px;justify-content:center;padding:24px 20px;font-size:15px}}
nav a{{color:inherit;text-decoration:none;opacity:.75}}nav a:hover{{opacity:1}}
footer{{text-align:center;font-size:14px;opacity:.7;padding:32px 20px}}
.hero{{text-align:center;padding-top:24px}}.hero img.icon{{width:120px;height:120px;border-radius:27px;box-shadow:0 12px 32px rgba(0,0,0,.15)}}
.tag{{font-size:21px;opacity:.85;margin:0 auto 28px;max-width:520px}}
.badge img{{height:54px}}.shots{{display:flex;gap:16px;overflow-x:auto;padding:36px 4px;scroll-snap-type:x mandatory}}
.shots img{{height:520px;border-radius:28px;scroll-snap-align:center;box-shadow:0 10px 30px rgba(0,0,0,.12)}}
</style></head><body>
<nav><a href="/">{html.escape(f['name'])}</a><a href="/support">Support</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a></nav>
<main>{body}</main>
<footer>&copy; {datetime.date.today().year} {html.escape(f['owner'])} &middot; <a href="mailto:{html.escape(f['email'])}">{html.escape(f['email'])}</a></footer>
</body></html>
"""


def cmd_policies(a):
    ship = load(a.ship)
    f = facts(ship)
    os.makedirs(a.out, exist_ok=True)
    for name, fn in (("privacy.md", privacy_md), ("terms.md", terms_md), ("support.md", support_md)):
        with open(os.path.join(a.out, name), "w") as fh:
            fh.write(fn(f))
    print(f"wrote privacy.md, terms.md, support.md to {a.out}. Read them, fill any [brackets], adjust to the app.")


def cmd_static(a):
    ship = load(a.ship)
    f = facts(ship)
    out = a.out
    os.makedirs(out, exist_ok=True)
    brand = os.path.join(os.path.dirname(a.ship), "brand")
    for fname in ("favicon.ico", "apple-touch-icon.png", "icon-192.png", "icon-512.png", "site.webmanifest", "og.png"):
        src = os.path.join(brand, "web", fname) if fname != "og.png" else os.path.join(brand, fname)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(out, fname))
    shots_dir = os.path.join(os.path.dirname(a.ship), "screenshots", ship.get("app", {}).get("primaryLocale", "en-US"), "APP_IPHONE_67")
    shots = sorted(x for x in os.listdir(shots_dir) if x.endswith(".png"))[:5] if os.path.isdir(shots_dir) else []
    if shots:
        os.makedirs(os.path.join(out, "shots"), exist_ok=True)
        for s in shots:
            shutil.copy(os.path.join(shots_dir, s), os.path.join(out, "shots", s))
    store_url = ship.get("site", {}).get("urls", {}).get("appStore") or (
        f"https://apps.apple.com/app/id{f['ascAppId']}" if f["ascAppId"] else "")
    cta = (f'<a class="badge" href="{store_url}"><img src="app-store-badge.svg" alt="Download on the App Store"></a>'
           if store_url else '<p><strong>Coming soon to the App Store.</strong></p>')
    icon = '<img class="icon" src="icon-512.png" alt="">' if os.path.exists(os.path.join(out, "icon-512.png")) else ""
    gallery = ('<div class="shots">' + "".join(f'<img src="shots/{s}" alt="{html.escape(f["name"])} screenshot {i + 1}" loading="lazy">'
                                              for i, s in enumerate(shots)) + "</div>") if shots else ""
    home = (f'<section class="hero">{icon}<h1>{html.escape(f["name"])}</h1><p class="tag">{html.escape(f["tagline"] or f["oneLiner"])}</p>'
            f'{cta}</section>{gallery}<p>{html.escape(f["oneLiner"])}</p>')
    desc = f["oneLiner"] or f["tagline"] or f["name"]
    pages = {
        "index.html": (f"{f['name']}: {f['tagline']}" if f["tagline"] else f["name"], home, desc, "/"),
        "privacy.html": (f"Privacy Policy | {f['name']}", md_to_html(privacy_md(f)), f"How {f['name']} handles your data.", "/privacy"),
        "terms.html": (f"Terms of Use | {f['name']}", md_to_html(terms_md(f)), f"Terms of use for {f['name']}.", "/terms"),
        "support.html": (f"Support | {f['name']}", md_to_html(support_md(f)), f"Get help with {f['name']}.", "/support"),
    }
    for fname, (title, body, d, path) in pages.items():
        with open(os.path.join(out, fname), "w") as fh:
            fh.write(page(f, ship, title, body, d, path))
    base = f"https://{f['domain']}" if f["domain"] else ""
    with open(os.path.join(out, "robots.txt"), "w") as fh:
        fh.write("User-agent: *\nAllow: /\n" + (f"Sitemap: {base}/sitemap.xml\n" if base else ""))
    if base:
        urls = "".join(f"<url><loc>{base}{p}</loc></url>" for p in ("/", "/support", "/privacy", "/terms"))
        with open(os.path.join(out, "sitemap.xml"), "w") as fh:
            fh.write(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')
    print(f"wrote {', '.join(pages)} and robots.txt to {out}")
    if store_url and not os.path.exists(os.path.join(out, "app-store-badge.svg")):
        print("Add Apple's official badge as app-store-badge.svg (from https://tools.applemarketingtools.com). Do not redraw it.")
    print("Pages link to /privacy and /support without .html: hosts like Vercel, Cloudflare Pages and Netlify serve them;"
          " on GitHub Pages use the .html URLs in App Store Connect.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ship", default=".ship/ship.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("policies", "static"):
        s = sub.add_parser(name)
        s.add_argument("--out", required=True)
    a = p.parse_args()
    {"policies": cmd_policies, "static": cmd_static}[a.cmd](a)


if __name__ == "__main__":
    main()
