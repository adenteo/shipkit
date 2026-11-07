"""screenshots: upload .ship/screenshots/<locale>/<display-type>/*.png to the version localization."""
import glob
import os

from asclib import Ctx, die, is_fake, md5_file, png_info, rel, upload_asset

ALIASES = {"iphone69": "APP_IPHONE_67", "iphone-6.9": "APP_IPHONE_67", "iphone67": "APP_IPHONE_67",
           "iphone-6.7": "APP_IPHONE_67", "iphone65": "APP_IPHONE_65", "iphone-6.5": "APP_IPHONE_65",
           "ipad13": "APP_IPAD_PRO_3GEN_129", "ipad-13": "APP_IPAD_PRO_3GEN_129",
           "ipad129": "APP_IPAD_PRO_3GEN_129"}
# Sizes ASC accepts per display type (portrait; landscape is the swap). The 6.9in 1320x2868 set is
# uploaded into APP_IPHONE_67, the largest iPhone slot the API exposes.
SIZES = {"APP_IPHONE_67": {(1290, 2796), (1284, 2778), (1320, 2868)},
         "APP_IPHONE_65": {(1242, 2688), (1284, 2778)},
         "APP_IPAD_PRO_3GEN_129": {(2048, 2732), (2064, 2752)}}
SKIP_DIRS = {"raw", "review"}


def plan_files(ctx, root):
    """{locale: {display_type: [png paths sorted]}} from the folder layout."""
    out = {}
    for loc in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if loc in SKIP_DIRS or not os.path.isdir(os.path.join(root, loc)):
            continue
        for d in sorted(os.listdir(os.path.join(root, loc))):
            full = os.path.join(root, loc, d)
            if not os.path.isdir(full):
                continue
            dtype = ALIASES.get(d.lower(), d)
            files = sorted(glob.glob(os.path.join(full, "*.png")))
            if files:
                out.setdefault(loc, {}).setdefault(dtype, []).extend(files)
    return out


def validate(files, dtype, skip_dims):
    errs = []
    if len(files) > 10:
        errs.append(f"{dtype}: {len(files)} screenshots, ASC allows 10")
    ok = SIZES.get(dtype)
    for f in files:
        try:
            w, h, alpha = png_info(f)
        except ValueError:
            errs.append(f"{f}: not a valid PNG")
            continue
        if alpha:
            errs.append(f"{f}: has an alpha channel; ASC rejects it. Export RGB without transparency")
        if ok and not skip_dims and (w, h) not in ok and (h, w) not in ok:
            errs.append(f"{f}: {w}x{h} is not accepted for {dtype} ({sorted(ok)})")
    return errs


def cmd_screenshots(ctx):
    root = ctx.args.dir or os.path.join(ctx.ship_dir, "screenshots")
    plan = plan_files(ctx, root)
    if not plan:
        die(f"no PNGs under {root}/<locale>/<display-type>/ (e.g. en-US/APP_IPHONE_67/01-hero.png)")
    errs = [e for loc, d in plan.items() for t, fs in d.items() for e in validate(fs, t, ctx.args.no_dim_check)]
    if ctx.s("app", "supportsIpad") and not any("APP_IPAD" in t for d in plan.values() for t in d):
        errs.append("app.supportsIpad is true but no APP_IPAD_PRO_3GEN_129 folder exists (ASC requires iPad shots)")
    if errs:
        die("screenshot checks failed, nothing sent:\n  " + "\n  ".join(errs))
    c = ctx.client
    vid = ctx.version_id(create=True)
    locs = {} if is_fake(vid) else {
        x["attributes"]["locale"]: x["id"]
        for x in c.pages(f"/v1/appStoreVersions/{vid}/appStoreVersionLocalizations?limit=200")}
    for loc, by_type in plan.items():
        lid = locs.get(loc)
        if not lid and not ctx.dry:
            die(f"no version localization for {loc}; run the listing command first")
        lid = lid or f"DRYRUN-loc-{loc}"
        sets = [] if is_fake(lid) else c.pages(f"/v1/appStoreVersionLocalizations/{lid}/appScreenshotSets?limit=50")
        for dtype, files in by_type.items():
            print(f"{loc} {dtype}: {len(files)} files")
            sset = next((s for s in sets if s["attributes"]["screenshotDisplayType"] == dtype), None)
            if sset:
                sid = sset["id"]
                cur = c.pages(f"/v1/appScreenshotSets/{sid}/appScreenshots?limit=50")
                same = [s["attributes"].get("sourceFileChecksum") for s in cur] == [md5_file(f) for f in files]
                done = all((s["attributes"].get("assetDeliveryState") or {}).get("state") == "COMPLETE" for s in cur)
                if same and done:
                    print("  unchanged, skipped")
                    continue
                for s in cur:  # replace the whole set so order and content match the folder exactly
                    c.call("DELETE", f"/v1/appScreenshots/{s['id']}")
                print(f"  replaced {len(cur)} existing")
            else:
                sid = c.call("POST", "/v1/appScreenshotSets", {"data": {
                    "type": "appScreenshotSets", "attributes": {"screenshotDisplayType": dtype},
                    "relationships": {"appStoreVersionLocalization": rel("appStoreVersionLocalizations", lid)}}})["data"]["id"]
            ids = [upload_asset(c, "appScreenshots", "appScreenshotSet", "appScreenshotSets", sid, f,
                                "/v1/appScreenshots") for f in files]
            # Uploads can finish out of order; this PATCH pins the order shown on the store page.
            c.call("PATCH", f"/v1/appScreenshotSets/{sid}/relationships/appScreenshots",
                   {"data": [{"type": "appScreenshots", "id": i} for i in ids]})
            print(f"  uploaded {len(ids)} in order")
