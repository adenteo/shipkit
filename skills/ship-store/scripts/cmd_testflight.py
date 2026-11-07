"""testflight and attach-build and submit."""
import json
import time

from asclib import Ctx, ASCError, die, is_fake, rel, diff_attrs

INTERNAL_HINTS = ("internal", "team")


def find_build(ctx, number, wait, timeout, interval=30):
    """Poll until the build is VALID. Processing takes 5 to 30 minutes after upload, and the
    build can take a few minutes just to appear. Without --build, the newest build is used."""
    c, app_id = ctx.client, ctx.app_id()
    flt = f"&filter[version]={number}" if number else ""
    t0 = time.time()
    while True:
        bs = c.get(f"/v1/builds?filter[app]={app_id}{flt}&sort=-uploadedDate&limit=1")
        b = (bs or {}).get("data", [None])[0] if bs else None
        if b:
            st = b["attributes"]["processingState"]
            print(f"build {b['attributes']['version']}: {st}", flush=True)
            if st == "VALID":
                return b
            if st in ("FAILED", "INVALID"):
                die(f"build processing {st}; check the email from Apple and the upload log")
        else:
            print("waiting for the build to appear...", flush=True)
        if not wait or time.time() - t0 > timeout:
            return b
        time.sleep(interval)


def ensure_encryption(ctx, b):
    """Skip the export compliance prompt: ITSAppUsesNonExemptEncryption belongs in Info.plist,
    but older builds without it stay blocked until this attribute is set."""
    if b["attributes"].get("usesNonExemptEncryption") is None and not is_fake(b["id"]):
        val = bool(ctx.s("store", "usesNonExemptEncryption", default=False))
        ctx.client.call("PATCH", f"/v1/builds/{b['id']}", {"data": {
            "type": "builds", "id": b["id"], "attributes": {"usesNonExemptEncryption": val}}})
        print(f"set usesNonExemptEncryption={val}")


def beta_app_info(ctx):
    """Beta app description, feedback email and the Beta App Review contact (needed before an
    external group can get a build)."""
    c, app_id, tf = ctx.client, ctx.app_id(), ctx.s("store", "testflight", default={}) or {}
    urls, r = ctx.urls(), ctx.s("store", "review", default={}) or {}
    attrs = {"description": tf.get("betaDescription") or ctx.s("app", "oneLiner", default=""),
             "feedbackEmail": r.get("contactEmail") or ctx.s("site", "supportEmail", default=""),
             "marketingUrl": urls.get("marketing"), "privacyPolicyUrl": urls.get("privacy")}
    locs = c.pages(f"/v1/apps/{app_id}/betaAppLocalizations?limit=50")
    cur = next((x for x in locs if x["attributes"]["locale"] == ctx.primary_locale), None)
    if cur:
        delta = diff_attrs(cur["attributes"], attrs)
        if delta:
            c.call("PATCH", f"/v1/betaAppLocalizations/{cur['id']}", {"data": {
                "type": "betaAppLocalizations", "id": cur["id"], "attributes": delta}})
            print(f"beta app info: patched {sorted(delta)}")
    else:
        c.call("POST", "/v1/betaAppLocalizations", {"data": {
            "type": "betaAppLocalizations",
            "attributes": {"locale": ctx.primary_locale, **{k: v for k, v in attrs.items() if v}},
            "relationships": {"app": rel("apps", app_id)}}})
        print("beta app info: created")
    det = c.get(f"/v1/apps/{app_id}/betaAppReviewDetail")
    det = (det or {}).get("data")
    if det and r.get("contactEmail"):
        want = {k: r.get(k) for k in ("contactFirstName", "contactLastName", "contactEmail", "contactPhone")}
        want["demoAccountRequired"] = False
        want["notes"] = tf.get("betaReviewNotes") or r.get("notes")
        delta = diff_attrs(det["attributes"], want)
        if delta:
            c.call("PATCH", f"/v1/betaAppReviewDetails/{det['id']}", {"data": {
                "type": "betaAppReviewDetails", "id": det["id"], "attributes": delta}})
            print(f"beta review contact: patched {sorted(delta)}")


def ensure_groups(ctx):
    c, app_id, tf = ctx.client, ctx.app_id(), ctx.s("store", "testflight", default={}) or {}
    have = {g["attributes"]["name"]: g for g in c.pages(f"/v1/apps/{app_id}/betaGroups?limit=200")}
    out = []
    for name in tf.get("groups") or ["Internal"]:
        internal = name.lower().startswith(INTERNAL_HINTS)
        g = have.get(name)
        if not g:
            attrs = {"name": name, "isInternalGroup": internal}
            if internal:
                attrs["hasAccessToAllBuilds"] = True
            else:
                attrs.update({"publicLinkEnabled": bool(tf.get("publicLink")), "feedbackEnabled": True})
            g = c.call("POST", "/v1/betaGroups", {"data": {
                "type": "betaGroups", "attributes": attrs, "relationships": {"app": rel("apps", app_id)}}})["data"]
            print(f"created group {name} ({'internal' if internal else 'external'})")
        out.append((name, g, internal))
    return out


def cmd_testflight(ctx):
    a = ctx.args
    if a.submit_beta_review and not a.dry_run and not a.confirm:
        die("--submit-beta-review sends the build to Apple. Get the user's go-ahead in chat, then add --confirm.")
    c = ctx.client
    beta_app_info(ctx)
    groups = ensure_groups(ctx)
    b = find_build(ctx, a.build, wait=not ctx.dry and not a.no_wait, timeout=a.timeout * 60)
    if not b:
        if not ctx.dry:
            die("build not found or not processed yet (re-run later, or raise --timeout)")
        b = {"id": "DRYRUN-build", "attributes": {"version": a.build or "?", "usesNonExemptEncryption": None}}
        print("(dry run) no processed build found, using a placeholder")
    ensure_encryption(ctx, b)
    bid = b["id"]
    notes = a.notes or ctx.s("store", "testflight", "whatToTest", default="") or "Bug fixes and polish."
    locale = ctx.primary_locale
    locs = [] if is_fake(bid) else c.pages(f"/v1/builds/{bid}/betaBuildLocalizations?limit=50")
    cur = next((x for x in locs if x["attributes"]["locale"] == locale), None)
    if cur:
        if cur["attributes"].get("whatsNew") != notes:
            c.call("PATCH", f"/v1/betaBuildLocalizations/{cur['id']}", {"data": {
                "type": "betaBuildLocalizations", "id": cur["id"], "attributes": {"whatsNew": notes}}})
            print("what to test: updated")
    else:
        c.call("POST", "/v1/betaBuildLocalizations", {"data": {
            "type": "betaBuildLocalizations", "attributes": {"locale": locale, "whatsNew": notes},
            "relationships": {"build": rel("builds", bid)}}})
        print("what to test: set")
    for name, g, internal in groups:
        if internal:
            print(f"group {name}: internal groups with access to all builds get it automatically")
            continue
        already = [] if is_fake(bid) or is_fake(g["id"]) else {
            x["id"] for x in c.pages(f"/v1/betaGroups/{g['id']}/builds?limit=200")}
        if bid in already:
            print(f"group {name}: build already attached")
            continue
        c.call("POST", f"/v1/betaGroups/{g['id']}/relationships/builds",
               {"data": [{"type": "builds", "id": bid}]})
        print(f"group {name}: build attached")
        link = (g.get("attributes") or {}).get("publicLink")
        if link:
            print(f"public link: {link}")
    if a.submit_beta_review:
        sub = None if is_fake(bid) else c.get(f"/v1/builds/{bid}/betaAppReviewSubmission")
        if sub and sub.get("data"):
            print("beta review: already submitted,", sub["data"]["attributes"].get("betaReviewState"))
        else:
            try:
                r = c.call("POST", "/v1/betaAppReviewSubmissions", {"data": {
                    "type": "betaAppReviewSubmissions", "relationships": {"build": rel("builds", bid)}}})
                print("beta review: submitted", r["data"]["attributes"].get("betaReviewState", ""))
            except ASCError as e:
                print(f"beta review submission failed: {e}")
    else:
        print("beta review not requested (add --submit-beta-review after the user agrees)")


# ------------------------------------------------------------------ attach-build

def cmd_attach_build(ctx):
    a = ctx.args
    b = find_build(ctx, a.build, wait=not ctx.dry and not a.no_wait, timeout=a.timeout * 60)
    if not b and not ctx.dry:
        die("build not found or not processed")
    b = b or {"id": "DRYRUN-build", "attributes": {"version": "?", "usesNonExemptEncryption": None}}
    ensure_encryption(ctx, b)
    vid = ctx.version_id(create=True)
    cur = None if is_fake(vid) else ctx.client.get(f"/v1/appStoreVersions/{vid}/build")
    if cur and (cur.get("data") or {}).get("id") == b["id"]:
        print(f"build {b['attributes']['version']} already attached")
        return
    ctx.client.call("PATCH", f"/v1/appStoreVersions/{vid}/relationships/build",
                    {"data": {"type": "builds", "id": b["id"]}})
    print(f"attached build {b['attributes']['version']} to version {ctx.s('app', 'marketingVersion')}")


# ------------------------------------------------------------------ submit

def preflight(ctx, vid):
    """Print a checklist of what App Review will check. Returns the list of blockers."""
    c, app_id, bad = ctx.client, ctx.app_id(), []

    def check(ok, label, fix):
        print(f"  [{'x' if ok else ' '}] {label}")
        if not ok:
            bad.append(f"{label}: {fix}")

    if is_fake(vid):
        print("  (version not created yet, dry run)")
        return bad
    build = c.get(f"/v1/appStoreVersions/{vid}/build")
    check(bool(build and build.get("data")), "build attached", "run attach-build")
    locs = c.pages(f"/v1/appStoreVersions/{vid}/appStoreVersionLocalizations?limit=200")
    check(bool(locs) and all(l["attributes"].get("description") for l in locs), "description in every locale", "run listing")
    for l in locs:
        sets = c.pages(f"/v1/appStoreVersionLocalizations/{l['id']}/appScreenshotSets?limit=50")
        check(bool(sets), f"screenshots for {l['attributes']['locale']}", "run screenshots")
    det = c.get(f"/v1/appStoreVersions/{vid}/appStoreReviewDetail")
    check(bool(det and det.get("data") and det["data"]["attributes"].get("contactEmail")), "review details", "run review-details")
    check(bool(c.get(f"/v1/apps/{app_id}/appPriceSchedule")), "price schedule", "run pricing")
    info = c.pages(f"/v1/apps/{app_id}/appInfos")
    check(any(i["attributes"].get("appStoreAgeRating") for i in info), "age rating", "run age-rating")
    print("  [ ] privacy nutrition labels and the first in-app purchase attachment are web-only: confirm in the web UI")
    return bad


def cmd_submit(ctx):
    a = ctx.args
    if not a.dry_run and not a.confirm:
        die("submit sends the app to App Review. Get the user's explicit go-ahead in chat, then add --confirm "
            "(or use --dry-run to see the plan).")
    c, app_id = ctx.client, ctx.app_id()
    vid = ctx.version_id(create=False)
    if not vid and not ctx.dry:
        die("no app version to submit; run listing and attach-build first")
    print("preflight:")
    bad = preflight(ctx, vid) if vid else []
    if bad and not a.force:
        die("blockers:\n  " + "\n  ".join(bad) + "\n(--force overrides, not recommended)")
    subs = c.pages(f"/v1/apps/{app_id}/reviewSubmissions?filter[platform]=IOS&limit=50") if app_id else []
    open_sub = next((s for s in subs if s["attributes"]["state"] == "READY_FOR_REVIEW"), None)
    if any(s["attributes"]["state"] in ("WAITING_FOR_REVIEW", "IN_REVIEW") for s in subs):
        die("a submission is already waiting for or in review")
    if open_sub:
        sid = open_sub["id"]
        print(f"reusing open review submission {sid}")
    else:
        sid = c.call("POST", "/v1/reviewSubmissions", {"data": {
            "type": "reviewSubmissions", "attributes": {"platform": "IOS"},
            "relationships": {"app": rel("apps", app_id)}}})["data"]["id"]
    items = [] if is_fake(sid) else c.pages(f"/v1/reviewSubmissions/{sid}/items?limit=50")
    if not items:
        c.call("POST", "/v1/reviewSubmissionItems", {"data": {
            "type": "reviewSubmissionItems",
            "relationships": {"reviewSubmission": rel("reviewSubmissions", sid),
                              "appStoreVersion": rel("appStoreVersions", vid or "DRYRUN-version")}}})
    c.call("PATCH", f"/v1/reviewSubmissions/{sid}", {"data": {
        "type": "reviewSubmissions", "id": sid, "attributes": {"submitted": True}}})
    print("submitted for App Review" if not ctx.dry else "(dry run) would submit for App Review")
