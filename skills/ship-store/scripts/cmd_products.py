"""products: in-app purchases and auto-renewable subscriptions from monetization.products."""
import os
from decimal import Decimal

from asclib import (ASCError, die, is_fake, rel, upload_asset, png_info, diff_attrs)

IAP_TYPES = {"consumable": "CONSUMABLE", "non-consumable": "NON_CONSUMABLE",
             "non-renewing": "NON_RENEWING_SUBSCRIPTION"}
PERIODS = {"P1W": "ONE_WEEK", "P1M": "ONE_MONTH", "P2M": "TWO_MONTHS", "P3M": "THREE_MONTHS",
           "P6M": "SIX_MONTHS", "P1Y": "ONE_YEAR"}
TRIALS = {"P3D": "THREE_DAYS", "P1W": "ONE_WEEK", "P2W": "TWO_WEEKS", "P1M": "ONE_MONTH",
          "P2M": "TWO_MONTHS", "P3M": "THREE_MONTHS", "P6M": "SIX_MONTHS", "P1Y": "ONE_YEAR"}
# Local limits (App Store Connect rejects longer text with an unhelpful error).
IAP_DISPLAY, IAP_DESC, SUB_DESC = 30, 45, 55


def review_shot(ctx, p):
    """A product's review screenshot: product.reviewScreenshot, else .ship/screenshots/review/<id>.png."""
    cands = [p.get("reviewScreenshot"),
             os.path.join(ctx.ship_dir, "screenshots", "review", p["id"] + ".png"),
             os.path.join(ctx.ship_dir, "screenshots", "review", "default.png")]
    for c in cands:
        if c:
            path = c if os.path.isabs(c) else os.path.join(os.getcwd(), c)
            if os.path.exists(path):
                return path
    return None


def check_product(p):
    errs = []
    for k in ("id", "type", "name"):
        if not p.get(k):
            errs.append(f"product missing {k}: {p}")
    if p.get("type") not in (*IAP_TYPES, "subscription"):
        errs.append(f"{p.get('id')}: unknown type {p.get('type')}")
    if p.get("type") == "subscription":
        if p.get("period") not in PERIODS:
            errs.append(f"{p['id']}: period must be one of {sorted(PERIODS)}")
        if p.get("trial") and p["trial"] not in TRIALS:
            errs.append(f"{p['id']}: trial must be one of {sorted(TRIALS)}")
    if not p.get("price"):
        errs.append(f"{p.get('id')}: price is empty")
    lim = SUB_DESC if p.get("type") == "subscription" else IAP_DESC
    if len(p.get("description") or "") > lim:
        errs.append(f"{p['id']}: description {len(p['description'])} chars, limit {lim}")
    if len(p.get("displayName") or p.get("name") or "") > IAP_DISPLAY:
        errs.append(f"{p['id']}: display name over {IAP_DISPLAY} chars")
    return errs


# ------------------------------------------------------------------ in-app purchases

def ensure_iap(ctx, p, existing):
    c, app_id = ctx.client, ctx.app_id()
    note = p.get("reviewNote") or ctx.s("store", "review", "notes", default="") or None
    it = existing.get(p["id"])
    if it:
        print(f"[exists]  {p['id']} state={it['attributes'].get('state')}")
        delta = diff_attrs(it["attributes"], {"name": p["name"], "reviewNote": note})
        if delta:
            c.call("PATCH", f"/v2/inAppPurchases/{it['id']}", {"data": {
                "type": "inAppPurchases", "id": it["id"], "attributes": delta}})
            print(f"  patched {sorted(delta)}")
        iid = it["id"]
    else:
        iid = c.call("POST", "/v2/inAppPurchases", {"data": {
            "type": "inAppPurchases",
            "attributes": {"name": p["name"], "productId": p["id"], "inAppPurchaseType": IAP_TYPES[p["type"]],
                           "reviewNote": note, "familySharable": bool(p.get("familySharable"))},
            "relationships": {"app": rel("apps", app_id)}}})["data"]["id"]
        print(f"[created] {p['id']}")
    ensure_iap_localizations(ctx, p, iid)
    ensure_iap_price(ctx, p, iid)
    ensure_iap_availability(ctx, iid)
    ensure_review_screenshot(ctx, p, iid, "inAppPurchaseAppStoreReviewScreenshots",
                             "inAppPurchaseV2", "inAppPurchases", f"/v2/inAppPurchases/{iid}/appStoreReviewScreenshot")


def localization_map(ctx, p):
    loc = {ctx.primary_locale: {"name": p.get("displayName") or p["name"], "description": p.get("description") or ""}}
    for k, v in (p.get("localizations") or {}).items():
        loc[k] = {"name": v.get("name") or loc[ctx.primary_locale]["name"],
                  "description": v.get("description", "")}
    return loc


def ensure_iap_localizations(ctx, p, iid):
    c = ctx.client
    have = {} if is_fake(iid) else {l["attributes"]["locale"]: l for l in
                                    c.pages(f"/v2/inAppPurchases/{iid}/inAppPurchaseLocalizations?limit=200")}
    for locale, a in localization_map(ctx, p).items():
        cur = have.get(locale)
        if cur:
            delta = diff_attrs(cur["attributes"], a)
            if delta:
                c.call("PATCH", f"/v1/inAppPurchaseLocalizations/{cur['id']}", {"data": {
                    "type": "inAppPurchaseLocalizations", "id": cur["id"], "attributes": delta}})
                print(f"  patched {locale} localization")
        else:
            c.call("POST", "/v1/inAppPurchaseLocalizations", {"data": {
                "type": "inAppPurchaseLocalizations", "attributes": {"locale": locale, **a},
                "relationships": {"inAppPurchaseV2": rel("inAppPurchases", iid)}}})
            print(f"  + {locale} localization")


def current_iap_price(c, iid):
    if is_fake(iid):
        return None
    sched = c.get(f"/v2/inAppPurchases/{iid}/iapPriceSchedule")
    if not sched or not sched.get("data"):
        return None
    _, inc = c.included(f"/v1/inAppPurchasePriceSchedules/{sched['data']['id']}/manualPrices"
                        "?include=inAppPurchasePricePoint&limit=50")
    pts = [i for i in inc if i["type"] == "inAppPurchasePricePoints"]
    return Decimal(pts[0]["attributes"]["customerPrice"]) if pts else None


def ensure_iap_price(ctx, p, iid):
    c, want = ctx.client, Decimal(str(p["price"]))
    if current_iap_price(c, iid) == want:
        return
    pts = c.pages(f"/v2/inAppPurchases/{iid}/pricePoints?filter[territory]=USA&limit=200") if not is_fake(iid) else []
    match = [x for x in pts if Decimal(x["attributes"]["customerPrice"]) == want]
    if not match and not is_fake(iid):
        raise ASCError("GET", "pricePoints", 0, {"errors": f"no USA price point at {want} for {p['id']}"})
    pp = match[0]["id"] if match else "DRYRUN-price-point"
    # One USA base price; Apple equalizes every other territory automatically for IAPs.
    c.call("POST", "/v1/inAppPurchasePriceSchedules", {
        "data": {"type": "inAppPurchasePriceSchedules", "attributes": {}, "relationships": {
            "inAppPurchase": rel("inAppPurchases", iid), "baseTerritory": rel("territories", "USA"),
            "manualPrices": {"data": [{"type": "inAppPurchasePrices", "id": "${price0}"}]}}},
        "included": [{"type": "inAppPurchasePrices", "id": "${price0}", "attributes": {"startDate": None},
                      "relationships": {"inAppPurchasePricePoint": rel("inAppPurchasePricePoints", pp)}}]})
    print(f"  + price USD {want}")


def ensure_iap_availability(ctx, iid):
    c = ctx.client
    if not is_fake(iid):
        av = c.get(f"/v2/inAppPurchases/{iid}/inAppPurchaseAvailability")
        if av and av.get("data"):
            return
    c.call("POST", "/v1/inAppPurchaseAvailabilities", {"data": {
        "type": "inAppPurchaseAvailabilities", "attributes": {"availableInNewTerritories": True},
        "relationships": {"inAppPurchase": rel("inAppPurchases", iid),
                          "availableTerritories": {"data": [{"type": "territories", "id": t} for t in ctx.territories()]}}}})
    print(f"  + availability ({len(ctx.territories())} territories)")


def ensure_review_screenshot(ctx, p, rid, type_, rel_name, rel_type, get_path):
    """Review screenshot proving where the purchase lives in the app. Required before submission.

    Must be a flat PNG (no alpha). A stale half-uploaded one is deleted and redone."""
    c = ctx.client
    path = review_shot(ctx, p)
    cur = None if is_fake(rid) else c.get(get_path)
    cur = (cur or {}).get("data")
    if cur:
        st = (cur["attributes"].get("assetDeliveryState") or {}).get("state")
        if st in ("COMPLETE", "UPLOAD_COMPLETE"):
            return
        c.call("DELETE", f"/v1/{type_}/{cur['id']}")
        print(f"  - removed incomplete review screenshot ({st})")
    if not path:
        print(f"  ! no review screenshot for {p['id']}: add .ship/screenshots/review/{p['id']}.png "
              "or product.reviewScreenshot (Apple requires one before submission)")
        return
    w, h, alpha = png_info(path)
    if alpha:
        die(f"{path} has an alpha channel; export it flat (no transparency)")
    upload_asset(c, type_, rel_name, rel_type, rid, path, get_path)
    print(f"  + review screenshot {os.path.basename(path)}")


# ------------------------------------------------------------------ subscriptions

def ensure_group(ctx, name, groups):
    c = ctx.client
    g = groups.get(name)
    if g:
        gid = g["id"]
        print(f"[exists]  group {name}")
    else:
        gid = c.call("POST", "/v1/subscriptionGroups", {"data": {
            "type": "subscriptionGroups", "attributes": {"referenceName": name},
            "relationships": {"app": rel("apps", ctx.app_id())}}})["data"]["id"]
        print(f"[created] group {name}")
    have = {} if is_fake(gid) else {l["attributes"]["locale"] for l in
                                    c.pages(f"/v1/subscriptionGroups/{gid}/subscriptionGroupLocalizations?limit=200")}
    for locale in {ctx.primary_locale, *[l for l in ctx.locales()]}:
        if locale not in have:
            c.call("POST", "/v1/subscriptionGroupLocalizations", {"data": {
                "type": "subscriptionGroupLocalizations",
                "attributes": {"locale": locale, "name": name, "customAppName": ctx.s("app", "name", default=name)},
                "relationships": {"subscriptionGroup": rel("subscriptionGroups", gid)}}})
            print(f"  + group {locale} localization")
    return gid


def ensure_subscription(ctx, p, gid, level):
    c = ctx.client
    note = p.get("reviewNote") or ctx.s("store", "review", "notes", default="") or None
    subs = [] if is_fake(gid) else c.pages(f"/v1/subscriptionGroups/{gid}/subscriptions?limit=200")
    s = next((x for x in subs if x["attributes"]["productId"] == p["id"]), None)
    if s:
        print(f"[exists]  {p['id']} state={s['attributes'].get('state')}")
        sid = s["id"]
        delta = diff_attrs(s["attributes"], {"name": p["name"], "reviewNote": note})
        if delta:
            c.call("PATCH", f"/v1/subscriptions/{sid}", {"data": {
                "type": "subscriptions", "id": sid, "attributes": delta}})
            print(f"  patched {sorted(delta)}")
    else:
        sid = c.call("POST", "/v1/subscriptions", {"data": {
            "type": "subscriptions",
            "attributes": {"productId": p["id"], "name": p["name"], "subscriptionPeriod": PERIODS[p["period"]],
                           "groupLevel": p.get("level", level), "familySharable": bool(p.get("familySharable")),
                           "reviewNote": note},
            "relationships": {"group": rel("subscriptionGroups", gid)}}})["data"]["id"]
        print(f"[created] {p['id']}")
    state = (s or {}).get("attributes", {}).get("state", "")
    # Order matters: localization, then availability, then prices. Prices before availability fail.
    have = {} if is_fake(sid) else {l["attributes"]["locale"]: l for l in
                                    c.pages(f"/v1/subscriptions/{sid}/subscriptionLocalizations?limit=200")}
    for locale, a in localization_map(ctx, p).items():
        cur = have.get(locale)
        if cur:
            delta = diff_attrs(cur["attributes"], a)
            if delta:
                c.call("PATCH", f"/v1/subscriptionLocalizations/{cur['id']}", {"data": {
                    "type": "subscriptionLocalizations", "id": cur["id"], "attributes": delta}})
                print(f"  patched {locale} localization")
        else:
            c.call("POST", "/v1/subscriptionLocalizations", {"data": {
                "type": "subscriptionLocalizations", "attributes": {"locale": locale, **a},
                "relationships": {"subscription": rel("subscriptions", sid)}}})
            print(f"  + {locale} localization")
    ensure_sub_availability(ctx, sid)
    ensure_sub_prices(ctx, p, sid, state)
    ensure_trial(ctx, p, sid)
    ensure_review_screenshot(ctx, p, sid, "subscriptionAppStoreReviewScreenshots", "subscription",
                             "subscriptions", f"/v1/subscriptions/{sid}/appStoreReviewScreenshot")


def ensure_sub_availability(ctx, sid):
    c = ctx.client
    if not is_fake(sid):
        av = c.get(f"/v1/subscriptions/{sid}/subscriptionAvailability")
        if av and av.get("data"):
            return
    c.call("POST", "/v1/subscriptionAvailabilities", {"data": {
        "type": "subscriptionAvailabilities", "attributes": {"availableInNewTerritories": True},
        "relationships": {"subscription": rel("subscriptions", sid),
                          "availableTerritories": {"data": [{"type": "territories", "id": t} for t in ctx.territories()]}}}})
    print(f"  + availability ({len(ctx.territories())} territories)")


def priced_territories(c, sid):
    """{territory: Decimal price} for prices already set (include= gives the price point amount)."""
    out = {}
    if is_fake(sid):
        return out
    path = f"/v1/subscriptions/{sid}/prices?include=subscriptionPricePoint,territory&limit=200"
    while path:
        o = c.get(path) or {}
        pts = {i["id"]: Decimal(i["attributes"]["customerPrice"]) for i in o.get("included", [])
               if i["type"] == "subscriptionPricePoints"}
        for pr in o.get("data", []):
            t = (pr["relationships"].get("territory") or {}).get("data")
            pp = (pr["relationships"].get("subscriptionPricePoint") or {}).get("data")
            if t:
                out[t["id"]] = pts.get(pp["id"]) if pp else None
        nxt = (o.get("links") or {}).get("next")
        path = nxt.replace("https://api.appstoreconnect.apple.com", "") if nxt else None
    return out


def post_sub_price(c, sid, pp_id, territory):
    c.call("POST", "/v1/subscriptionPrices", {"data": {
        "type": "subscriptionPrices", "attributes": {"startDate": None, "preserveCurrentPrice": False},
        "relationships": {"subscription": rel("subscriptions", sid),
                          "subscriptionPricePoint": rel("subscriptionPricePoints", pp_id),
                          "territory": rel("territories", territory)}}})


def ensure_sub_prices(ctx, p, sid, state):
    """USA base price, then Apple's equalized price in every other territory.

    Quirks: price points are per subscription (not global); equalizations hang off the USA point;
    a territory with no price simply is not sold there. Changing the USA price of a subscription
    that is already live is a price increase with consent rules, so this script will not do it."""
    c, want = ctx.client, Decimal(str(p["price"]))
    have = priced_territories(c, sid)
    if have.get("USA") not in (None, want):
        print(f"  ! USA price is {have['USA']} but ship.json says {want}. Not changing an existing price; "
              "edit it in App Store Connect (price changes on live subscriptions need care).")
        return
    pts = [] if is_fake(sid) else c.pages(f"/v1/subscriptions/{sid}/pricePoints?filter[territory]=USA&limit=200")
    match = [x for x in pts if Decimal(x["attributes"]["customerPrice"]) == want]
    if not match and not is_fake(sid):
        raise ASCError("GET", "pricePoints", 0, {"errors": f"no USA price point at {want} for {p['id']}"})
    usa_pp = match[0]["id"] if match else "DRYRUN-usa-point"
    if "USA" not in have:
        post_sub_price(c, sid, usa_pp, "USA")
        have["USA"] = want
        print(f"  + price USA {want}")
    eq = [] if is_fake(usa_pp) else c.pages(
        f"/v1/subscriptionPricePoints/{usa_pp}/equalizations?include=territory&limit=200")
    added, failed = 0, []
    for e in eq:
        terr = e["relationships"]["territory"]["data"]["id"]
        if terr in have:
            continue
        try:
            post_sub_price(c, sid, e["id"], terr)
            have[terr] = None
            added += 1
        except ASCError as err:
            failed.append(f"{terr}: {str(err)[:160]}")
    if added:
        print(f"  + equalized prices in {added} territories")
    if is_fake(usa_pp):
        print("  + (dry run) equalized prices would follow in every other territory")
    if failed:
        print(f"  ! {len(failed)} territory prices failed: " + "; ".join(failed[:4]))


def ensure_trial(ctx, p, sid):
    """Free-trial introductory offer for all territories. Less battle-tested than the rest."""
    if not p.get("trial"):
        return
    c = ctx.client
    cur = [] if is_fake(sid) else c.pages(f"/v1/subscriptions/{sid}/introductoryOffers?limit=50")
    if cur:
        return
    try:
        c.call("POST", "/v1/subscriptionIntroductoryOffers", {"data": {
            "type": "subscriptionIntroductoryOffers",
            "attributes": {"duration": TRIALS[p["trial"]], "offerMode": "FREE_TRIAL", "numberOfPeriods": 1},
            "relationships": {"subscription": rel("subscriptions", sid)}}})
        print(f"  + free trial {p['trial']}")
    except ASCError as e:
        print(f"  ! trial offer failed ({str(e)[:200]}); set it in the web UI")


# ------------------------------------------------------------------ command

def cmd_products(ctx):
    products = ctx.s("monetization", "products", default=[]) or []
    if not products:
        print("monetization.products is empty, nothing to do")
        return
    errs = [e for p in products for e in check_product(p)]
    if errs:
        die("products fail checks, nothing sent:\n  " + "\n  ".join(errs))
    only = getattr(ctx.args, "only", None)
    c, app_id = ctx.client, ctx.app_id()
    iaps = {i["attributes"]["productId"]: i for i in c.pages(f"/v1/apps/{app_id}/inAppPurchasesV2?limit=200")}
    groups = {g["attributes"]["referenceName"]: g
              for g in c.pages(f"/v1/apps/{app_id}/subscriptionGroups?limit=200")}
    levels = {}
    problems = []
    for p in products:
        if only and p["id"] != only:
            continue
        try:
            if p["type"] == "subscription":
                gname = p.get("group") or "Subscriptions"
                gid = ensure_group(ctx, gname, groups)
                groups.setdefault(gname, {"id": gid})
                levels[gname] = levels.get(gname, 0) + 1
                ensure_subscription(ctx, p, gid, levels[gname])
            else:
                ensure_iap(ctx, p, iaps)
        except ASCError as e:
            problems.append(f"{p['id']}: {e}")
            print(f"  ! {e}")
    print("\nreminder: the FIRST in-app purchase or subscription must be added to the app version in the web UI "
          "(version page, 'In-App Purchases and Subscriptions') and goes to review with that version.")
    if problems:
        raise SystemExit("problems:\n  " + "\n  ".join(problems))
