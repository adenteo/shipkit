"""listing, age-rating, pricing, review-details, bundle-id: the one-time store record setup."""
import json
import os

from asclib import (Ctx, ASCError, EDITABLE_VERSION_STATES, check_limits, diff_attrs, die, dig, is_fake, rel,
                    save_ship)

# ------------------------------------------------------------------ bundle-id

CAPABILITY_SETTINGS = {
    # Settings these capability types require on create (from Apple's docs; verify on first real run).
    "APPLE_ID_AUTH": [{"key": "APPLE_ID_AUTH_APP_CONSENT", "options": [{"key": "PRIMARY_APP_CONSENT"}]}],
    "ICLOUD": [{"key": "ICLOUD_VERSION", "options": [{"key": "XCODE_6"}]}],
}


def wanted_capabilities(ctx):
    caps = set(ctx.s("store", "capabilities", default=[]) or [])
    if ctx.s("features", "gameCenter") or ctx.s("store", "gameCenter"):
        caps.add("GAME_CENTER")
    if ctx.s("features", "notifications") == "remote":
        caps.add("PUSH_NOTIFICATIONS")
    if "apple" in (ctx.s("features", "accounts", default="") or ""):
        caps.add("APPLE_ID_AUTH")
    return sorted(caps)


def cmd_bundle_id(ctx):
    """Register the bundle ID (developer portal resource) and enable capabilities. Idempotent."""
    c, ident = ctx.client, ctx.bundle_id
    if not ident:
        die("ship.json app.bundleId is empty")
    found = c.pages(f"/v1/bundleIds?filter[identifier]={ident}&limit=200")
    found = [b for b in found if b["attributes"]["identifier"] == ident]  # filter is a prefix match
    if found:
        bid = found[0]["id"]
        print(f"bundle ID exists: {ident} (resource {bid})")
    else:
        name = (ctx.s("app", "name", default="") or ident).replace("-", " ")[:50]
        attrs = {"identifier": ident, "name": f"{name} iOS", "platform": "UNIVERSAL"}
        body = {"data": {"type": "bundleIds", "attributes": attrs}}
        bid = c.call("POST", "/v1/bundleIds", body)["data"]["id"]
        print(f"registered bundle ID {ident}")
    have = set()
    if not is_fake(bid):
        _, inc = c.included(f"/v1/bundleIds/{bid}?include=bundleIdCapabilities")
        have = {i["attributes"]["capabilityType"] for i in inc if i["type"] == "bundleIdCapabilities"}
    for cap in wanted_capabilities(ctx):
        if cap in have:
            print(f"capability {cap}: already enabled")
            continue
        attrs = {"capabilityType": cap}
        if cap in CAPABILITY_SETTINGS:
            attrs["settings"] = CAPABILITY_SETTINGS[cap]
        try:
            c.call("POST", "/v1/bundleIdCapabilities", {"data": {
                "type": "bundleIdCapabilities", "attributes": attrs,
                "relationships": {"bundleId": rel("bundleIds", bid)}}})
            print(f"capability {cap}: enabled")
        except ASCError as e:
            print(f"capability {cap}: FAILED ({e}). Enable it in the developer portal if this persists.")
    print("note: after changing capabilities, regenerate the provisioning profile (Xcode: automatic signing does it).")


# ------------------------------------------------------------------ listing

def category_relationships(primary, secondary):
    """Map ship.json category ids onto appInfo relationships.

    GAMES_* ids are subcategories: the parent GAMES category is implied. Learned the hard way:
    a game needs primaryCategory=GAMES plus primarySubcategoryOne/Two, not GAMES_PUZZLE as primary."""
    r = {"primaryCategory": None, "primarySubcategoryOne": None, "primarySubcategoryTwo": None,
         "secondaryCategory": None, "secondarySubcategoryOne": None, "secondarySubcategoryTwo": None}
    if primary.startswith("GAMES_") or primary == "GAMES":
        r["primaryCategory"] = "GAMES"
        if primary != "GAMES":
            r["primarySubcategoryOne"] = primary
        if secondary.startswith("GAMES_"):
            r["primarySubcategoryTwo"] = secondary
        elif secondary:
            r["secondaryCategory"] = secondary
    else:
        r["primaryCategory"] = primary
        r["secondaryCategory"] = secondary or None
    return r


def set_categories(ctx, info_id):
    primary = ctx.s("store", "primaryCategory", default="")
    if not primary:
        print("categories: store.primaryCategory empty, skipped")
        return
    want = category_relationships(primary, ctx.s("store", "secondaryCategory", default="") or "")
    cur = {}
    if not is_fake(info_id):
        data, _ = ctx.client.included(f"/v1/appInfos/{info_id}?include=primaryCategory,"
                                      "primarySubcategoryOne,primarySubcategoryTwo,secondaryCategory")
        cur = {k: (v.get("data") or {}).get("id") for k, v in (data or {}).get("relationships", {}).items()
               if k in want}
    if all(cur.get(k) == v for k, v in want.items() if k in cur or v):
        print("categories: unchanged")
        return
    ctx.client.call("PATCH", f"/v1/appInfos/{info_id}", {"data": {
        "type": "appInfos", "id": info_id,
        "relationships": {k: rel("appCategories", v) for k, v in want.items()
                          if k in ("primaryCategory", "primarySubcategoryOne", "primarySubcategoryTwo",
                                   "secondaryCategory")}}})
    print(f"categories: set {primary}" + (f" + {ctx.s('store', 'secondaryCategory')}" if ctx.s("store", "secondaryCategory") else ""))


def upsert(ctx, existing, patch_path, patch_type, post_path, post_type, locale, attrs, parent_rel):
    """PATCH the localization if it exists and differs, POST it when missing."""
    c = ctx.client
    if existing:
        delta = diff_attrs(existing["attributes"], attrs)
        if not delta:
            print(f"  {locale}: unchanged")
            return existing["id"]
        c.call("PATCH", f"{patch_path}/{existing['id']}", {"data": {
            "type": patch_type, "id": existing["id"], "attributes": delta}})
        print(f"  {locale}: patched {sorted(delta)}")
        return existing["id"]
    clean = {k: v for k, v in attrs.items() if v not in (None, "")}
    res = c.call("POST", post_path, {"data": {
        "type": post_type, "attributes": {"locale": locale, **clean}, "relationships": parent_rel}})
    print(f"  {locale}: created")
    return res["data"]["id"]


def cmd_pull_listing(ctx):
    """Copy the store's current listing (every locale) into ship.json: the starting point for an existing app."""
    c = ctx.client
    vs = c.pages(f"/v1/apps/{ctx.app_id()}/appStoreVersions?filter[platform]=IOS&limit=20")
    if not vs:
        die("the app has no App Store version yet; nothing to pull")
    pick = next((v for v in vs if v["attributes"]["appStoreState"] in EDITABLE_VERSION_STATES), vs[0])
    vid = pick["id"]
    ctx.ship.setdefault("app", {}).setdefault("marketingVersion", pick["attributes"]["versionString"])
    infos = c.pages(f"/v1/apps/{ctx.app_id()}/appInfos")
    info_id = ctx.info_id() if infos else None
    listing = ctx.ship.setdefault("listing", {})
    for x in c.pages(f"/v1/appInfos/{info_id}/appInfoLocalizations?limit=200") if info_id else []:
        a = x["attributes"]
        t = listing.setdefault(a["locale"], {})
        t.update({k: a[k] for k in ("name", "subtitle") if a.get(k)})
        if a.get("privacyPolicyUrl"):
            t["privacyPolicyUrl"] = a["privacyPolicyUrl"]
    for x in c.pages(f"/v1/appStoreVersions/{vid}/appStoreVersionLocalizations?limit=200"):
        a = x["attributes"]
        t = listing.setdefault(a["locale"], {})
        t.update({k: a[k] for k in ("description", "keywords", "promotionalText", "whatsNew", "supportUrl",
                                    "marketingUrl") if a.get(k)})
    prim = listing.get(ctx.primary_locale, {})
    urls = ctx.ship.setdefault("site", {}).setdefault("urls", {})
    for key, field in (("privacy", "privacyPolicyUrl"), ("support", "supportUrl"), ("marketing", "marketingUrl")):
        if prim.get(field) and not urls.get(key):
            urls[key] = prim[field]
    ver = c.get(f"/v1/appStoreVersions/{vid}")["data"]["attributes"]
    if ver.get("copyright"):
        ctx.ship.setdefault("store", {}).setdefault("copyright", ver["copyright"])
    save_ship(ctx.ship_path, ctx.ship)
    print(f"pulled {len(listing)} locale(s) from version {ver.get('versionString')} "
          f"({ver.get('appVersionState') or ver.get('appStoreState')}): {', '.join(sorted(listing))}")


def cmd_listing(ctx):
    listing = ctx.s("listing", default={}) or {}
    only = [l.strip() for l in (getattr(ctx.args, "locales", None) or "").split(",") if l.strip()]
    if only:
        missing = [l for l in only if l not in listing]
        if missing:
            die(f"no listing in ship.json for {', '.join(missing)}")
        listing = {l: listing[l] for l in only}
    problems = check_limits(listing)
    if problems:
        die("listing fails checks, nothing sent:\n  " + "\n  ".join(problems))
    if not listing:
        die("ship.json listing is empty")
    print("limits ok: " + ", ".join(
        f"{l}: name {len(t.get('name', ''))}, sub {len(t.get('subtitle', ''))}, kw {len(t.get('keywords', ''))}"
        for l, t in listing.items()))
    c, urls = ctx.client, ctx.urls()
    info_id = ctx.info_id()
    vid = ctx.version_id(create=not only)
    if not vid:
        die("no editable App Store version; a live app's listing changes ship with its next version "
            "(run without --locales to create it, after a yes)")
    first = ctx.is_first_version()
    if not only:
        set_categories(ctx, info_id)

    print("app info localizations:")
    info_locs = {} if is_fake(info_id) else {
        x["attributes"]["locale"]: x for x in c.pages(f"/v1/appInfos/{info_id}/appInfoLocalizations?limit=200")}
    for loc, t in listing.items():
        attrs = {"name": t.get("name"), "subtitle": t.get("subtitle"),
                 "privacyPolicyUrl": t.get("privacyPolicyUrl") or urls.get("privacy")}
        upsert(ctx, info_locs.get(loc), "/v1/appInfoLocalizations", "appInfoLocalizations",
               "/v1/appInfoLocalizations", "appInfoLocalizations", loc, attrs,
               {"appInfo": rel("appInfos", info_id)})

    print("version localizations:")
    ver_locs = {} if is_fake(vid) else {
        x["attributes"]["locale"]: x
        for x in c.pages(f"/v1/appStoreVersions/{vid}/appStoreVersionLocalizations?limit=200")}
    for loc, t in listing.items():
        attrs = {"description": t.get("description"), "keywords": t.get("keywords"),
                 "promotionalText": t.get("promotionalText"),
                 "supportUrl": t.get("supportUrl") or urls.get("support"),
                 "marketingUrl": t.get("marketingUrl") or urls.get("marketing")}
        if not first:  # ASC rejects whatsNew on an app's very first version
            attrs["whatsNew"] = t.get("whatsNew")
        elif t.get("whatsNew"):
            print(f"  {loc}: whatsNew skipped (first version of the app cannot have it)")
        upsert(ctx, ver_locs.get(loc), "/v1/appStoreVersionLocalizations", "appStoreVersionLocalizations",
               "/v1/appStoreVersionLocalizations", "appStoreVersionLocalizations", loc, attrs,
               {"appStoreVersion": rel("appStoreVersions", vid)})

    if only:
        print(f"only {', '.join(only)}: app-level settings (categories, copyright, content rights) left alone.")
        return
    cp = ctx.s("store", "copyright", default="")
    if cp and not is_fake(vid) and ctx.version()["attributes"].get("copyright") != cp:
        c.call("PATCH", f"/v1/appStoreVersions/{vid}", {"data": {
            "type": "appStoreVersions", "id": vid, "attributes": {"copyright": cp}}})
        print("copyright: set")
    elif cp and is_fake(vid):
        c.call("PATCH", f"/v1/appStoreVersions/{vid}", {"data": {
            "type": "appStoreVersions", "id": vid, "attributes": {"copyright": cp}}})

    rights = ctx.s("store", "contentRights", default="DOES_NOT_USE_THIRD_PARTY_CONTENT")
    app = c.get(f"/v1/apps/{ctx.app_id()}")["data"]["attributes"]
    if app.get("contentRightsDeclaration") != rights:
        c.call("PATCH", f"/v1/apps/{ctx.app_id()}", {"data": {
            "type": "apps", "id": ctx.app_id(), "attributes": {"contentRightsDeclaration": rights}}})
        print(f"content rights declaration: {rights}")
    print("not set here: privacy nutrition labels (web only), age rating (age-rating), price (pricing).")


# ------------------------------------------------------------------ age rating

ENUM_NONE = ["alcoholTobaccoOrDrugUseOrReferences", "contests", "gamblingSimulated", "gunsOrOtherWeapons",
             "medicalOrTreatmentInformation", "profanityOrCrudeHumor", "sexualContentGraphicAndNudity",
             "sexualContentOrNudity", "horrorOrFearThemes", "matureOrSuggestiveThemes",
             "violenceCartoonOrFantasy", "violenceRealisticProlongedGraphicOrSadistic", "violenceRealistic"]
BOOL_FALSE = ["gambling", "lootBox", "messagingAndChat", "parentalControls", "unrestrictedWebAccess",
              "userGeneratedContent", "healthOrWellnessTopics", "ageAssurance", "socialMedia",
              "socialMediaAgeRestricted"]


def cmd_age_rating(ctx):
    """Fill the age rating questionnaire: defaults to all NONE/false, overridden by store.ageRating.

    Only keys the API currently exposes on the declaration are sent (Apple renames these between
    API versions); unknown override keys are reported rather than silently dropped."""
    c = ctx.client
    info_id = ctx.info_id()
    data = None if is_fake(info_id) else c.get(f"/v1/appInfos/{info_id}/ageRatingDeclaration")
    if not data:
        die("no ageRatingDeclaration found for the app info")
    decl = data["data"]
    cur = decl["attributes"]
    attrs = {k: "NONE" for k in ENUM_NONE if k in cur}
    attrs.update({k: False for k in BOOL_FALSE if k in cur})
    if "advertising" in cur:
        attrs["advertising"] = ctx.s("features", "ads", default="none") != "none"
    if "inAppPurchases" in cur:
        attrs["inAppPurchases"] = bool(ctx.s("monetization", "products", default=[]))
    attrs["kidsAgeBand"] = None
    overrides = ctx.s("store", "ageRating", default={}) or {}
    unknown = [k for k in overrides if k not in cur]
    if unknown:
        print(f"warning: store.ageRating keys not in the API declaration, ignored: {unknown}")
    attrs.update({k: v for k, v in overrides.items() if k in cur})
    delta = {k: v for k, v in attrs.items() if cur.get(k) != v}
    left = [k for k in cur if cur[k] is None and k not in attrs]
    if left:
        print(f"note: fields still unset (not in our map): {left}")
    if not delta:
        print("age rating: unchanged")
        return
    c.call("PATCH", f"/v1/ageRatingDeclarations/{decl['id']}", {"data": {
        "type": "ageRatingDeclarations", "id": decl["id"], "attributes": delta}})
    print(f"age rating: patched {sorted(delta)}")


# ------------------------------------------------------------------ pricing + availability

def price_point_id(ctx, price):
    pts = ctx.client.pages(f"/v1/apps/{ctx.app_id()}/appPricePoints?filter[territory]=USA&limit=200")
    from decimal import Decimal
    for p in pts:
        if Decimal(p["attributes"]["customerPrice"]) == Decimal(str(price)):
            return p["id"]
    die(f"no USA app price point at {price}. Apple uses fixed tiers; pick a listed price "
        f"(e.g. {sorted({p['attributes']['customerPrice'] for p in pts}, key=float)[:12]}).")


def cmd_pricing(ctx):
    """Base price (USA, other territories follow Apple's equalization) and territory availability."""
    from decimal import Decimal
    c, app_id = ctx.client, ctx.app_id()
    price = str(ctx.s("monetization", "price", default="free"))
    price = "0" if price.lower() == "free" else price
    cur = None
    sched = c.get(f"/v1/apps/{app_id}/appPriceSchedule")
    if sched:
        _, inc = c.included(f"/v1/appPriceSchedules/{sched['data']['id']}/manualPrices?include=appPricePoint&limit=50")
        pts = [i for i in inc if i["type"] == "appPricePoints"]
        cur = Decimal(pts[0]["attributes"]["customerPrice"]) if pts else None
    if cur is not None and cur == Decimal(price):
        print(f"price: already USD {price}")
    else:
        pp = price_point_id(ctx, price)
        c.call("POST", "/v1/appPriceSchedules", {
            "data": {"type": "appPriceSchedules", "attributes": {}, "relationships": {
                "app": rel("apps", app_id), "baseTerritory": rel("territories", "USA"),
                "manualPrices": {"data": [{"type": "appPrices", "id": "${price0}"}]}}},
            "included": [{"type": "appPrices", "id": "${price0}", "attributes": {"startDate": None},
                          "relationships": {"appPricePoint": rel("appPricePoints", pp)}}]})
        print(f"price: set USD {price} base (was {cur})")
    availability(ctx)


def availability(ctx):
    c, app_id = ctx.client, ctx.app_id()
    avail = ctx.s("store", "availability", default="all")
    excluded = set(ctx.s("store", "excludeTerritories", default=[]) or [])
    if isinstance(avail, list):  # explicit allow list
        excluded = set(ctx.territories()) - set(avail)
    terr = ctx.territories()
    cur = c.get(f"/v1/apps/{app_id}/appAvailabilityV2")
    if cur:
        aid = cur["data"]["id"]
        tas = c.pages(f"/v2/appAvailabilities/{aid}/territoryAvailabilities?limit=200&include=territory")
        changed = 0
        for ta in tas:
            tid = ta["relationships"]["territory"]["data"]["id"]
            want = tid not in excluded
            if ta["attributes"]["available"] != want:
                c.call("PATCH", f"/v1/territoryAvailabilities/{ta['id']}", {"data": {
                    "type": "territoryAvailabilities", "id": ta["id"], "attributes": {"available": want}}})
                changed += 1
        print(f"availability: {changed} territories changed (excluded: {sorted(excluded) or 'none'})")
        return
    inc, rels = [], []
    for i, tid in enumerate(terr):
        ph = "${t%d}" % i
        rels.append({"type": "territoryAvailabilities", "id": ph})
        inc.append({"type": "territoryAvailabilities", "id": ph,
                    "attributes": {"available": tid not in excluded},
                    "relationships": {"territory": rel("territories", tid)}})
    c.call("POST", "/v2/appAvailabilities", {
        "data": {"type": "appAvailabilities", "attributes": {"availableInNewTerritories": True},
                 "relationships": {"app": rel("apps", app_id),
                                   "territoryAvailabilities": {"data": rels}}},
        "included": inc})
    print(f"availability: created for {len(terr)} territories (excluded: {sorted(excluded) or 'none'})")


# ------------------------------------------------------------------ review details

def cmd_review_details(ctx):
    """Contact, notes and demo account App Review sees. The password comes from an env var."""
    r = ctx.s("store", "review", default={}) or {}
    if not r.get("contactEmail"):
        die("store.review.contactEmail is empty (contact name, email and phone are required by Apple)")
    attrs = {k: r.get(k) for k in ("contactFirstName", "contactLastName", "contactEmail", "contactPhone")}
    attrs["demoAccountRequired"] = bool(r.get("demoAccountRequired"))
    attrs["notes"] = r.get("notes") or None
    if attrs["demoAccountRequired"]:
        var = r.get("demoPasswordEnv")
        if not var:
            die("demoAccountRequired is true but store.review.demoPasswordEnv (env var name) is empty")
        pw = os.environ.get(var)
        if not pw and not ctx.dry:
            die(f"export {var} (the demo account password) before running; it is never stored in ship.json")
        attrs["demoAccountName"] = r.get("demoUser")
        attrs["demoAccountPassword"] = pw or f"<{var}>"
    attrs = {k: v for k, v in attrs.items() if v is not None}
    vid = ctx.version_id(create=True)
    c = ctx.client
    cur = None if is_fake(vid) else c.get(f"/v1/appStoreVersions/{vid}/appStoreReviewDetail")
    cur = (cur or {}).get("data")
    shown = {k: ("<hidden>" if k == "demoAccountPassword" else v) for k, v in attrs.items()}
    if cur:
        delta = {k: v for k, v in attrs.items()
                 if k != "demoAccountPassword" and cur["attributes"].get(k) != v}
        if "demoAccountPassword" in attrs:
            delta["demoAccountPassword"] = attrs["demoAccountPassword"]  # write-only, cannot diff
        c.call("PATCH", f"/v1/appStoreReviewDetails/{cur['id']}", {"data": {
            "type": "appStoreReviewDetails", "id": cur["id"], "attributes": delta}})
        print("review details: patched", sorted(delta))
    else:
        c.call("POST", "/v1/appStoreReviewDetails", {"data": {
            "type": "appStoreReviewDetails", "attributes": attrs,
            "relationships": {"appStoreVersion": rel("appStoreVersions", vid)}}})
        print("review details: created", json.dumps(shown)[:300])
