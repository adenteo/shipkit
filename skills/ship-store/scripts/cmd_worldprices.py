"""world-prices: regional pricing bands for the app price, subscriptions and IAPs.

Plans from live App Store Connect data (the source of truth, not ship.json), writes
.ship/pricing/plan.json and plan.md, and only sends with --confirm.

The trick: Apple equalizes any USA price point into every territory. For a band with
ratio r, take the USA point nearest base x r and read its equalizations for that band's
territories. One call per band per product, and every target is a real local tier.
"""
import datetime
import json
import os
from decimal import Decimal

import time

from asclib import BASE, ASCError, die, rel

# World Bank income groups (snapshot, mid 2025), intersected with the 175 App Store
# territories, with the poorer upper-middle markets (Indonesia, Ukraine, Algeria,
# Guatemala and others) moved to band 3, where apps that tested regional prices
# settle. Everything not listed is band 1 and is left alone by the gni model.
# Judgment calls worth a look per app: China (band 2), and high income markets with
# lower purchasing power (Poland, Hungary, Romania, Bulgaria, Croatia, Chile, Uruguay)
# which stay band 1 unless monetization.priceBands moves them.
BAND2 = """ALB ARG ARM AZE BLR BLZ BIH BWA BRA CHN COL CRI DMA DOM ECU FJI GAB GEO GRD
JAM KAZ LBY MYS MDV MUS MEX MNE MKD PRY PER RUS SRB ZAF LCA VCT THA TUR""".split()
BAND3 = """AFG BFA COD GMB GNB LBR MDG MWI MLI MOZ NER RWA SLE TCD UGA YEM
AGO BEN BTN BOL CPV KHM CMR COG CIV EGY SWZ GHA HND IND JOR KEN KGZ LAO LBN MRT FSM MNG MAR
MMR NPL NIC NGA PAK PNG PHL STP SEN SLB LKA TJK TZA TUN UZB VUT VNM ZMB ZWE
DZA GTM IDN IRQ MDA NAM SLV SUR TKM TON UKR VEN XKS""".split()
DEFAULT_RATIOS = {2: Decimal("0.6"), 3: Decimal("0.3")}
SAMPLE = "IND BRA TUR MEX IDN VNM PHL EGY NGA PAK CHN POL".split()
JUDGMENT_NOTE = ("China and the high income Eastern EU markets (Poland, Hungary, Romania, Bulgaria, "
                 "Croatia) are judgment calls; move them with monetization.priceBands.")

# Per product kind: price point type, USA points path, equalizations path, relationship names.
KINDS = {
    "subscription": {"pp": "subscriptionPricePoints",
                     "points": "/v1/subscriptions/{id}/pricePoints?filter[territory]={t}&limit=200",
                     "eq": "/v1/subscriptionPricePoints/{pp}/equalizations"},
    "iap": {"pp": "inAppPurchasePricePoints",
            "points": "/v2/inAppPurchases/{id}/pricePoints?filter[territory]={t}&limit=200",
            "eq": "/v1/inAppPurchasePricePoints/{pp}/equalizations"},
    "app": {"pp": "appPricePoints",
            "points": "/v1/apps/{id}/appPricePoints?filter[territory]={t}&limit=200",
            "eq": "/v3/appPricePoints/{pp}/equalizations"},
}


# ------------------------------------------------------------------ helpers

def pages_inc(c, path):
    """Like Client.pages, but keeps `included` (keyed by (type, id))."""
    data, inc = [], {}
    while path:
        o = c.get(path)
        if not o:
            break
        d = o.get("data", [])
        data += d if isinstance(d, list) else [d]
        for i in o.get("included", []):
            inc[(i["type"], i["id"])] = i
        nxt = (o.get("links") or {}).get("next")
        path = nxt.replace(BASE, "") if nxt else None
    return data, inc


def today():
    return datetime.date.today().isoformat()


def is_current(attrs):
    sd, ed = attrs.get("startDate"), attrs.get("endDate")
    return (not sd or sd <= today()) and (not ed or ed > today())


def price_rows(c, path, pp_rel):
    """Price entries -> {territory: {"current": {...}, "scheduled": [...]}}."""
    data, inc = pages_inc(c, path)
    out = {}
    for p in data:
        a = p.get("attributes") or {}
        if a.get("planType") not in (None, "UPFRONT"):
            continue
        r = p.get("relationships") or {}
        t = ((r.get("territory") or {}).get("data") or {}).get("id")
        ppd = (r.get(pp_rel) or {}).get("data") or {}
        pt = inc.get((ppd.get("type"), ppd.get("id")), {})
        cur = (inc.get(("territories", t), {}).get("attributes") or {}).get("currency", "")
        if not t or not pt:
            continue
        row = {"price": pt["attributes"]["customerPrice"], "pp": ppd["id"], "currency": cur,
               "startDate": a.get("startDate"), "manual": a.get("manual")}
        slot = out.setdefault(t, {"current": None, "scheduled": []})
        if is_current(a):
            prev = slot["current"]
            if not prev or (row["startDate"] or "") >= (prev["startDate"] or ""):
                slot["current"] = row
        elif (a.get("startDate") or "") > today():
            slot["scheduled"].append(row)
    return out


def nearest_point(points, target):
    best = None
    for p in points:
        v = Decimal(p["attributes"]["customerPrice"])
        if v <= 0:
            continue
        d = abs(v - target)
        if best is None or d < best[0] or (d == best[0] and v < best[1]):
            best = (d, v, p["id"])
    return (best[2], best[1]) if best else (None, None)


def equalize(c, kind, pp, territories):
    """{territory: {"pp", "price", "currency"}} for a price point across territories."""
    out = {}
    terr = sorted(territories)
    for i in range(0, len(terr), 60):
        chunk = ",".join(terr[i:i + 60])
        data, inc = pages_inc(c, KINDS[kind]["eq"].format(pp=pp)
                              + f"?filter[territory]={chunk}&include=territory&limit=200")
        for p in data:
            t = (((p.get("relationships") or {}).get("territory") or {}).get("data") or {}).get("id")
            if t:
                cur = (inc.get(("territories", t), {}).get("attributes") or {}).get("currency", "")
                out[t] = {"pp": p["id"], "price": p["attributes"]["customerPrice"], "currency": cur}
    return out


def bands_for(ctx):
    bands = {t: 2 for t in BAND2}
    bands.update({t: 3 for t in BAND3})
    for t, b in (ctx.s("monetization", "priceBands", default={}) or {}).items():
        bands[t.upper()] = int(b)
    ratios = dict(DEFAULT_RATIOS)
    for b, r in (ctx.s("monetization", "priceRatios", default={}) or {}).items():
        ratios[int(b)] = Decimal(str(r))
    return bands, ratios


def pct(new, old):
    old, new = Decimal(old), Decimal(new)
    if old == 0:
        return ""
    return f"{(new - old) / old * 100:+.0f}%"


def ratio(v, eq):
    if not eq or Decimal(eq) == 0:
        return ""
    return f"x{Decimal(v) / Decimal(eq):.2f}"


# ------------------------------------------------------------------ products

def list_products(ctx):
    c, app_id = ctx.client, ctx.app_id()
    prods = [{"kind": "app", "id": app_id, "productId": "app", "name": ctx.s("app", "name", default="app")}]
    for g in c.pages(f"/v1/apps/{app_id}/subscriptionGroups?limit=200"):
        for s in c.pages(f"/v1/subscriptionGroups/{g['id']}/subscriptions?limit=200"):
            a = s["attributes"]
            prods.append({"kind": "subscription", "id": s["id"], "productId": a.get("productId"),
                          "name": a.get("name"), "period": a.get("subscriptionPeriod"), "state": a.get("state")})
    for p in c.pages(f"/v1/apps/{app_id}/inAppPurchasesV2?limit=200"):
        a = p["attributes"]
        prods.append({"kind": "iap", "id": p["id"], "productId": a.get("productId"), "name": a.get("name"),
                      "type": a.get("inAppPurchaseType"), "state": a.get("state")})
    only = getattr(ctx.args, "only", None)
    if only:
        prods = [p for p in prods if p["productId"] == only]
        if not prods:
            die(f"no product with productId {only!r} (use 'app' for the app price)")
    return prods


def current_prices(ctx, prod):
    """Returns (rows, base_territory, schedule_manual) for a product."""
    c, k, pid = ctx.client, prod["kind"], prod["id"]
    if k == "subscription":
        rows = price_rows(c, f"/v1/subscriptions/{pid}/prices?include=subscriptionPricePoint,territory&limit=200",
                          "subscriptionPricePoint")
        return rows, "USA", {}
    if k == "iap":
        sched = c.get(f"/v2/inAppPurchases/{pid}/iapPriceSchedule?include=baseTerritory")
        sid, pp_rel, typ = (sched or {}).get("data", {}).get("id"), "inAppPurchasePricePoint", "inAppPurchasePriceSchedules"
    else:
        sched = c.get(f"/v1/apps/{pid}/appPriceSchedule?include=baseTerritory")
        sid, pp_rel, typ = (sched or {}).get("data", {}).get("id"), "appPricePoint", "appPriceSchedules"
    if not sid:
        return {}, "USA", {}
    base = (((sched["data"].get("relationships") or {}).get("baseTerritory") or {}).get("data") or {}).get("id") or "USA"
    manual = price_rows(c, f"/v1/{typ}/{sid}/manualPrices?include={pp_rel},territory&limit=200", pp_rel)
    auto = price_rows(c, f"/v1/{typ}/{sid}/automaticPrices?include={pp_rel},territory&limit=200", pp_rel)
    rows = dict(auto)
    rows.update(manual)
    return rows, base, manual


def plan_product(ctx, prod, model, bands, ratios, all_terr):
    c, k = ctx.client, prod["kind"]
    rows, base_t, manual = current_prices(ctx, prod)
    base_row = (rows.get(base_t) or {}).get("current")
    if not base_row or Decimal(base_row["price"]) == 0:
        return {**prod, "skip": "free or no base price" if rows else "no price set"}
    base = Decimal(base_row["price"])
    if base_t != "USA" and bands.get(base_t, 1) != 1:
        return {**prod, "skip": f"base territory {base_t} is in band {bands[base_t]}; set a band 1 base first"}
    sold = set(rows) - {base_t}
    plan = {**prod, "baseTerritory": base_t, "basePrice": str(base), "basePP": base_row["pp"],
            "baseCurrency": base_row["currency"], "model": model, "bands": {}, "territories": {},
            "keepManual": {}}

    if model == "equalized":
        groups = {1: sorted(sold & set(all_terr))}
        targets_by_band = {1: (base_row["pp"], base)}
    else:
        groups = {b: sorted(t for t in sold if bands.get(t, 1) == b) for b in (2, 3)}
        pts = c.pages(KINDS[k]["points"].format(id=prod["id"], t=base_t))
        targets_by_band = {}
        for b in (2, 3):
            if groups[b]:
                pp, v = nearest_point(pts, base * ratios[b])
                if pp:
                    targets_by_band[b] = (pp, v)
    reference = equalize(c, k, base_row["pp"], [t for g in groups.values() for t in g])

    for b, terr in groups.items():
        if b not in targets_by_band or not terr:
            continue
        pp, v = targets_by_band[b]
        plan["bands"][str(b)] = {"ratio": "1.0" if model == "equalized" else str(ratios[b]),
                                 "basePoint": str(v), "territories": len(terr)}
        eq = reference if model == "equalized" else equalize(c, k, pp, terr)
        for t in terr:
            tgt = eq.get(t)
            cur = (rows.get(t) or {}).get("current")
            if not tgt or not cur:
                continue
            sched = (rows.get(t) or {}).get("scheduled") or []
            if Decimal(tgt["price"]) == Decimal(cur["price"]) and not sched:
                change = "same"
            elif any(Decimal(s["price"]) == Decimal(tgt["price"]) for s in sched):
                change = "scheduled"
            else:
                change = "down" if Decimal(tgt["price"]) < Decimal(cur["price"]) else "up"
                if Decimal(tgt["price"]) == Decimal(cur["price"]):
                    change = "same"
                elif change == "up" and model != "equalized" and not getattr(ctx.args, "allow_increases", False):
                    change = "kept"  # already cheaper than the band; never raise unless asked
            plan["territories"][t] = {
                "band": b if model != "equalized" else bands.get(t, 1), "currency": tgt["currency"] or cur["currency"],
                "current": cur["price"], "target": tgt["price"], "targetPP": tgt["pp"],
                "equalized": (reference.get(t) or {}).get("price"), "change": change}

    # IAP and app schedules replace every manual price at once; carry over the ones we do not touch.
    if k in ("iap", "app") and model != "equalized":
        for t, r in manual.items():
            if t != base_t and t not in plan["territories"] and r.get("current"):
                plan["keepManual"][t] = r["current"]["pp"]
    plan["changes"] = sum(1 for v in plan["territories"].values() if v["change"] in ("up", "down"))
    return plan


# ------------------------------------------------------------------ output

def label(p):
    extra = p.get("period") or p.get("type") or ""
    return f"{p['productId']} ({p['kind']}{', ' + extra if extra else ''})"


def summary_lines(p):
    if p.get("skip"):
        return [f"{label(p)}: skipped, {p['skip']}"]
    out = [f"{label(p)}: base {p['baseCurrency']} {p['basePrice']} in {p['baseTerritory']}, "
           f"{p['changes']} territories change"]
    for b, info in sorted(p["bands"].items()):
        out.append(f"  band {b}: ratio {info['ratio']}, USA point {info['basePoint']}, {info['territories']} territories")
    terr = p["territories"]
    picks = [t for t in SAMPLE if t in terr] or sorted(terr)[:6]
    for t in picks:
        r = terr[t]
        out.append(f"  {t} b{r['band']}  {r['currency']} {r['current']} -> {r['target']}  "
                   f"{pct(r['target'], r['current']) or '0%'}  ({ratio(r['current'], r['equalized'])} -> "
                   f"{ratio(r['target'], r['equalized'])} of equalized)  {r['change']}")
    ups = [t for t, r in terr.items() if r["change"] == "up"]
    if ups:
        out.append(f"  price increases in {len(ups)}: {' '.join(sorted(ups))}")
    kept = [t for t, r in terr.items() if r["change"] == "kept"]
    if kept:
        out.append(f"  already cheaper than the band, left alone in {len(kept)} (--allow-increases to raise them)")
    return out


def write_plan(ctx, plans, model, ratios):
    d = os.path.join(ctx.ship_dir, "pricing")
    os.makedirs(d, exist_ok=True)
    meta = {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "model": model,
            "ratios": {str(k): str(v) for k, v in ratios.items()}, "note": JUDGMENT_NOTE}
    with open(os.path.join(d, "plan.json"), "w") as f:
        json.dump({"meta": meta, "products": plans}, f, indent=2)
    md = [f"# World prices plan ({model})", "", f"Generated {meta['generated']} from live App Store Connect data.",
          f"Band ratios: 2 = x{ratios[2]}, 3 = x{ratios[3]} of the equalized price. Band 1 is untouched.",
          "", f"Note: {JUDGMENT_NOTE}", ""]
    for p in plans:
        md += [f"## {label(p)}", ""]
        if p.get("skip"):
            md += [f"Skipped: {p['skip']}.", ""]
            continue
        md += [f"Base {p['baseCurrency']} {p['basePrice']} ({p['baseTerritory']}). {p['changes']} changes.", "",
               "| Territory | Band | Currency | Current | Planned | Change | vs equalized |",
               "|---|---|---|---|---|---|---|"]
        for t, r in sorted(p["territories"].items(), key=lambda x: (x[1]["band"], x[0])):
            md.append(f"| {t} | {r['band']} | {r['currency']} | {r['current']} | {r['target']} | "
                      f"{pct(r['target'], r['current']) or '0%'} {r['change']} | "
                      f"{ratio(r['current'], r['equalized'])} -> {ratio(r['target'], r['equalized'])} |")
        md.append("")
    with open(os.path.join(d, "plan.md"), "w") as f:
        f.write("\n".join(md))
    return d


# ------------------------------------------------------------------ apply

def apply_subscription(ctx, p):
    c, sent = ctx.client, []
    # A subscription that has been approved can only change price from a future date
    # ("Initial price cannot be created again after subscription is approved");
    # one still in setup takes the price immediately.
    start = None
    if p.get("state") not in ("MISSING_METADATA", "READY_TO_SUBMIT", "WAITING_FOR_REVIEW", "IN_REVIEW",
                              "DEVELOPER_ACTION_NEEDED", "REJECTED"):
        start = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        print(f"  {p['productId']} is {p.get('state')}: new prices start {start}")
    failed = []
    for t, r in sorted(p["territories"].items()):
        if r["change"] not in ("up", "down"):
            continue
        body = {"data": {
            "type": "subscriptionPrices",
            # Increases keep existing subscribers on their price (no consent prompt);
            # decreases pass straight to them.
            "attributes": {"startDate": start, "preserveCurrentPrice": r["change"] == "up"},
            "relationships": {"subscription": rel("subscriptions", p["id"]),
                              "subscriptionPricePoint": rel("subscriptionPricePoints", r["targetPP"]),
                              "territory": rel("territories", t)}}}
        for attempt in range(3):
            try:
                c.call("POST", "/v1/subscriptionPrices", body)
                sent.append(t)
                break
            except ASCError as e:
                # Apple's server errors are usually transient; a rerun re-plans and skips what landed.
                if e.status >= 500 and attempt < 2:
                    time.sleep(5 * (attempt + 1))
                    continue
                failed.append(f"{t} (HTTP {e.status})")
                break
    if failed:
        print(f"  {len(failed)} territory price(s) not sent: {', '.join(failed)}. Rerun to retry; done ones are skipped.")
    return sent


def apply_schedule(ctx, p):
    """IAP and app: one new schedule. Base price, untouched manual prices, and every planned territory."""
    c, k = ctx.client, p["kind"]
    changed = [t for t, r in p["territories"].items() if r["change"] in ("up", "down")]
    if not changed:
        return []
    pps = [p["basePP"]] + list(p.get("keepManual", {}).values())
    if p["model"] != "equalized":
        pps += [r["targetPP"] for r in p["territories"].values()]
    if k == "iap":
        typ, price_t, pp_t, owner = "inAppPurchasePriceSchedules", "inAppPurchasePrices", "inAppPurchasePricePoints", \
            {"inAppPurchase": rel("inAppPurchases", p["id"])}
        pp_rel = "inAppPurchasePricePoint"
    else:
        typ, price_t, pp_t, owner = "appPriceSchedules", "appPrices", "appPricePoints", {"app": rel("apps", p["id"])}
        pp_rel = "appPricePoint"
    refs = [{"type": price_t, "id": f"${{price{i}}}"} for i in range(len(pps))]
    inc = [{"type": price_t, "id": f"${{price{i}}}", "attributes": {"startDate": None},
            "relationships": {pp_rel: rel(pp_t, pp)}} for i, pp in enumerate(pps)]
    c.call("POST", f"/v1/{typ}", {
        "data": {"type": typ, "attributes": {}, "relationships": {
            **owner, "baseTerritory": rel("territories", p["baseTerritory"]), "manualPrices": {"data": refs}}},
        "included": inc})
    return changed


def read_back(ctx, p, sent):
    picks = [t for t in SAMPLE if t in sent][:3] or sorted(sent)[:3]
    if not picks:
        return
    rows, _, _ = current_prices(ctx, p)
    for t in picks:
        r, want = rows.get(t) or {}, p["territories"][t]["target"]
        cur = (r.get("current") or {}).get("price")
        sch = [f"{s['price']} from {s['startDate']}" for s in r.get("scheduled", [])]
        ok = cur is not None and Decimal(cur) == Decimal(want) or \
            any(Decimal(s["price"]) == Decimal(want) for s in r.get("scheduled", []))
        print(f"  read back {t}: now {cur}{', scheduled ' + '; '.join(sch) if sch else ''} "
              f"(wanted {want}) {'ok' if ok else 'NOT YET'}")


# ------------------------------------------------------------------ command

def inversions(plans):
    """Territories where the planned prices flip the order of the products' base prices
    (for example a monthly ending up dearer than an annual), within subscriptions and within IAPs."""
    out = []
    for kind in ("subscription", "iap"):
        ps = [p for p in plans if p["kind"] == kind and not p.get("skip")]
        terr = set().union(*[p["territories"] for p in ps]) if ps else set()
        for t in sorted(terr):
            rows = []
            for p in ps:
                r = p["territories"].get(t)
                if r:
                    final = r["target"] if r["change"] in ("up", "down", "scheduled") else r["current"]
                    rows.append((Decimal(p["basePrice"]), Decimal(final), p["productId"]))
            for a in rows:
                for b in rows:
                    if a[0] < b[0] and a[1] > b[1]:
                        out.append(f"{t}: {a[2]} ({a[1]}) would cost more than {b[2]} ({b[1]})")
    return out


def cmd_world_prices(ctx):
    a = ctx.args
    model = a.model or ctx.s("monetization", "priceModel", default="gni") or "gni"
    if model not in ("gni", "equalized"):
        die(f"unknown price model {model!r}; use gni or equalized")
    bands, ratios = bands_for(ctx)
    all_terr = ctx.territories()
    prods = list_products(ctx)
    print(f"world-prices: model {model}, {len(prods)} product(s), reading live prices...")
    plans = [plan_product(ctx, p, model, bands, ratios, all_terr) for p in prods]
    out = write_plan(ctx, plans, model, ratios)
    for p in plans:
        print("\n".join(summary_lines(p)))
    bad = inversions(plans)
    for line in bad[:20]:
        print(f"ORDER  {line}")
    if bad:
        print(f"{len(bad)} price order problem(s) (a cheaper product would cost more somewhere).")
    print(f"\nnote: {JUDGMENT_NOTE}")
    print(f"plan: {os.path.join(out, 'plan.md')} (full table) and plan.json")
    total = sum(p.get("changes", 0) for p in plans)
    if not a.confirm:
        print(f"\n{total} territory price change(s) planned. Nothing sent. "
              "Show the user plan.md; rerun with --confirm after a yes in chat.")
        return
    if total == 0:
        print("nothing to change.")
        return
    if bad:
        die("not sending: fix the price order problems above first (adjust priceRatios or use --only).")
    for p in plans:
        if p.get("skip") or not p.get("changes"):
            continue
        sent = apply_subscription(ctx, p) if p["kind"] == "subscription" else apply_schedule(ctx, p)
        print(f"{label(p)}: {'planned' if ctx.dry else 'sent'} {len(sent)} territory change(s)")
        if not ctx.dry and sent:
            read_back(ctx, p, sent)
    if not ctx.dry:
        print("Subscription changes can show as scheduled for the next day; that is a successful write.")
