#!/usr/bin/env python3
"""ship-store: drive App Store Connect from .ship/ship.json.

  python3 asc.py whoami | status | raw | bundle-id | listing | age-rating | pricing
                 | products | screenshots | review-details | testflight | attach-build
                 | submit | game-center | world-prices

Every command reads ./.ship/ship.json (override with --ship). Every mutating command
accepts --dry-run: GETs still run, POST/PATCH/DELETE are printed and never sent.
Credentials: ship.json secrets.ascEnv, else ASC_KEY_ID / ASC_ISSUER_ID / ASC_KEY_PATH,
else ~/.config/shipkit/defaults.json secrets.ascEnv. Values are never printed.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from asclib import ASCError, Ctx, die  # noqa: E402


def cmd_whoami(ctx):
    c = ctx.client
    apps = c.pages("/v1/apps?limit=200&fields[apps]=bundleId,name")
    print(f"credentials ok; this key can see {len(apps)} app(s)")
    bid, aid = ctx.bundle_id, ctx.s("app", "ascAppId", default="")
    hit = next((a for a in apps if a["id"] == aid or (bid and a["attributes"]["bundleId"] == bid)), None)
    if hit:
        print(f"app record found: id {hit['id']}, name {hit['attributes']['name']!r}, bundle {hit['attributes']['bundleId']}")
    else:
        print(f"no app record for bundle ID {bid or '(empty)'} yet: create it once in the web UI (SKILL.md step 2)")


def cmd_status(ctx):
    """Read-only summary. Safe to run any time."""
    c, app_id = ctx.client, ctx.app_id()
    app = c.get(f"/v1/apps/{app_id}")["data"]["attributes"]
    print(f"app {app_id}: {app.get('name')!r} bundle {app.get('bundleId')} sku {app.get('sku')} "
          f"primaryLocale {app.get('primaryLocale')} contentRights {app.get('contentRightsDeclaration')}")
    for i in c.pages(f"/v1/apps/{app_id}/appInfos"):
        a = i["attributes"]
        print(f"appInfo {i['id'][:8]}: state {a.get('state')} ageRating {a.get('appStoreAgeRating')}")
    for v in c.pages(f"/v1/apps/{app_id}/appStoreVersions?limit=20"):
        a = v["attributes"]
        locs = c.pages(f"/v1/appStoreVersions/{v['id']}/appStoreVersionLocalizations?limit=200")
        shots = []
        for l in locs:
            for s in c.pages(f"/v1/appStoreVersionLocalizations/{l['id']}/appScreenshotSets?limit=50"):
                n = len(c.pages(f"/v1/appScreenshotSets/{s['id']}/appScreenshots?limit=50"))
                shots.append(f"{l['attributes']['locale']}/{s['attributes']['screenshotDisplayType']}={n}")
        b = c.get(f"/v1/appStoreVersions/{v['id']}/build")
        bv = ((b or {}).get("data") or {}).get("id")
        print(f"version {a['versionString']} ({a['platform']}): {a.get('appStoreState')}; "
              f"locales {[l['attributes']['locale'] for l in locs]}; build attached {bool(bv)}; "
              f"screenshots {shots or 'none'}")
    builds = (c.get(f"/v1/builds?filter[app]={app_id}&sort=-uploadedDate&limit=5") or {}).get("data", [])
    for b in builds:
        a = b["attributes"]
        print(f"build {a.get('version')}: {a.get('processingState')} expired={a.get('expired')} "
              f"uploaded {str(a.get('uploadedDate'))[:10]}")
    iaps = c.pages(f"/v1/apps/{app_id}/inAppPurchasesV2?limit=200")
    for i in iaps:
        a = i["attributes"]
        print(f"iap {a['productId']}: {a['inAppPurchaseType']} {a.get('state')}")
    for g in c.pages(f"/v1/apps/{app_id}/subscriptionGroups?limit=50"):
        for s in c.pages(f"/v1/subscriptionGroups/{g['id']}/subscriptions?limit=50"):
            a = s["attributes"]
            print(f"subscription {a['productId']}: group {g['attributes']['referenceName']!r} "
                  f"{a.get('subscriptionPeriod')} {a.get('state')}")
    if not iaps and not c.pages(f"/v1/apps/{app_id}/subscriptionGroups?limit=50"):
        print("no in-app purchases or subscriptions")
    subs = c.pages(f"/v1/apps/{app_id}/reviewSubmissions?limit=10")
    print("review submissions: " + (", ".join(f"{s['attributes'].get('state')}" for s in subs) or "none"))
    groups = c.pages(f"/v1/apps/{app_id}/betaGroups?limit=50")
    print("beta groups: " + (", ".join(f"{g['attributes']['name']}({'internal' if g['attributes'].get('isInternalGroup') else 'external'})"
                                       for g in groups) or "none"))
    d = c.get(f"/v1/apps/{app_id}/gameCenterDetail")
    if d and d.get("data"):
        lb = c.pages(f"/v1/gameCenterDetails/{d['data']['id']}/gameCenterLeaderboards?limit=200")
        ac = c.pages(f"/v1/gameCenterDetails/{d['data']['id']}/gameCenterAchievements?limit=200")
        print(f"game center: {len(lb)} leaderboards, {len(ac)} achievements")
    else:
        print("game center: not set up")


def cmd_raw(ctx):
    a = ctx.args
    body = json.loads(a.body) if a.body else None
    method = a.method.upper()
    if method != "GET" and not ctx.dry:
        print(f"note: sending a live {method}", file=sys.stderr)
    out = ctx.client.call(method, a.path, body)
    print(json.dumps(out, indent=2))


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ship", default=None, help="path to ship.json (default ./.ship/ship.json)")
    common.add_argument("--verbose", action="store_true", help="print full request bodies in dry runs")
    mut = argparse.ArgumentParser(add_help=False, parents=[common])
    mut.add_argument("--dry-run", action="store_true", help="print planned POST/PATCH/DELETE, send nothing")
    p = argparse.ArgumentParser(prog="asc.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami", parents=[common], help="check credentials and find the app record")
    sub.add_parser("status", parents=[common], help="read-only summary of app, versions, builds, IAPs, review")
    r = sub.add_parser("raw", parents=[mut], help="raw API call: raw METHOD PATH [JSON]")
    r.add_argument("method")
    r.add_argument("path")
    r.add_argument("body", nargs="?")
    sub.add_parser("bundle-id", parents=[mut], help="register bundle ID and enable capabilities")
    li = sub.add_parser("listing", parents=[mut], help="localized text, URLs, categories, copyright")
    li.add_argument("--locales", help="only push these locales (text only, app-level settings untouched)")
    sub.add_parser("pull-listing", parents=[common], help="copy the store's current listing into ship.json")
    sub.add_parser("age-rating", parents=[mut], help="age rating questionnaire")
    sub.add_parser("pricing", parents=[mut], help="app price and territory availability")
    pr = sub.add_parser("products", parents=[mut], help="IAPs and subscriptions from monetization.products")
    pr.add_argument("--only", help="only this product id")
    sh = sub.add_parser("screenshots", parents=[mut], help="upload .ship/screenshots/<locale>/<display-type>/*.png")
    sh.add_argument("--dir", help="screenshots root (default .ship/screenshots)")
    sh.add_argument("--no-dim-check", action="store_true", help="skip the pixel size check")
    sub.add_parser("review-details", parents=[mut], help="App Review contact, notes, demo account")
    tf = sub.add_parser("testflight", parents=[mut], help="wait for build, what to test, groups, optional beta review")
    for sp in (tf, ):
        sp.add_argument("--build", help="build number (default: newest)")
        sp.add_argument("--notes", help="what to test (default store.testflight.whatToTest)")
        sp.add_argument("--no-wait", action="store_true", help="do not poll for processing")
        sp.add_argument("--timeout", type=int, default=60, help="minutes to wait for processing")
        sp.add_argument("--submit-beta-review", action="store_true", help="submit to Beta App Review (needs --confirm)")
        sp.add_argument("--confirm", action="store_true", help="the user approved this send, in chat")
    ab = sub.add_parser("attach-build", parents=[mut], help="attach a processed build to the app version")
    ab.add_argument("--build", help="build number (default: newest)")
    ab.add_argument("--no-wait", action="store_true")
    ab.add_argument("--timeout", type=int, default=60)
    sb = sub.add_parser("submit", parents=[mut], help="submit the version for App Review (needs --confirm)")
    sb.add_argument("--confirm", action="store_true", help="the user approved this send, in chat")
    sb.add_argument("--force", action="store_true", help="ignore preflight blockers")
    sub.add_parser("game-center", parents=[mut], help="leaderboards and achievements from store.gameCenter")
    wp = sub.add_parser("world-prices", parents=[mut], help="regional price bands for app, subscriptions, IAPs")
    wp.add_argument("--model", choices=["gni", "equalized"], help="default monetization.priceModel, else gni")
    wp.add_argument("--only", help="only this productId ('app' for the app price)")
    wp.add_argument("--confirm", action="store_true", help="send the plan; the user approved it in chat")
    wp.add_argument("--allow-increases", action="store_true", help="also raise prices already below their band")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    ctx = Ctx(args)
    handlers = {"whoami": cmd_whoami, "status": cmd_status, "raw": cmd_raw}
    name = args.cmd
    if name in handlers:
        fn = handlers[name]
    else:
        mod = {"bundle-id": ("cmd_listing", "cmd_bundle_id"), "listing": ("cmd_listing", "cmd_listing"),
               "pull-listing": ("cmd_listing", "cmd_pull_listing"),
               "age-rating": ("cmd_listing", "cmd_age_rating"), "pricing": ("cmd_listing", "cmd_pricing"),
               "review-details": ("cmd_listing", "cmd_review_details"),
               "products": ("cmd_products", "cmd_products"), "screenshots": ("cmd_screenshots", "cmd_screenshots"),
               "testflight": ("cmd_testflight", "cmd_testflight"), "attach-build": ("cmd_testflight", "cmd_attach_build"),
               "submit": ("cmd_testflight", "cmd_submit"), "game-center": ("cmd_gamecenter", "cmd_game_center"),
               "world-prices": ("cmd_worldprices", "cmd_world_prices")}[name]
        fn = getattr(__import__(mod[0]), mod[1])
    try:
        fn(ctx)
    except ASCError as e:
        die(str(e))
    if ctx.dry:
        print(f"\n[dry-run] {ctx.client.planned} mutating request(s) planned, none sent.")


if __name__ == "__main__":
    main()
