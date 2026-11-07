"""game-center: leaderboards and achievements from store.gameCenter."""
import datetime
import os

from asclib import ASCError, die, is_fake, rel, upload_asset, diff_attrs
from cmd_listing import wanted_capabilities


def next_midnight_utc():
    # recurrenceStartDate may not be in the past (RECURRENCE_START_CANNOT_BE_PAST), so use tomorrow 00:00Z.
    d = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_detail(ctx):
    c, app_id = ctx.client, ctx.app_id()
    cur = c.get(f"/v1/apps/{app_id}/gameCenterDetail")
    if cur and cur.get("data"):
        print(f"gameCenterDetail: exists {cur['data']['id']}")
        return cur["data"]["id"]
    r = c.call("POST", "/v1/gameCenterDetails", {"data": {
        "type": "gameCenterDetails", "relationships": {"app": rel("apps", app_id)}}})
    print("gameCenterDetail: created")
    return r["data"]["id"]


def ensure_app_version_enabled(ctx):
    """`enabled` is rejected on create (409): create bare, then PATCH enabled=true."""
    c, vid = ctx.client, ctx.version_id(create=True)
    cur = None if is_fake(vid) else c.get(f"/v1/appStoreVersions/{vid}/gameCenterAppVersion")
    cur = (cur or {}).get("data")
    if cur and cur["attributes"].get("enabled"):
        print("gameCenterAppVersion: enabled")
        return
    if not cur:
        cur = c.call("POST", "/v1/gameCenterAppVersions", {"data": {
            "type": "gameCenterAppVersions", "relationships": {"appStoreVersion": rel("appStoreVersions", vid)}}})["data"]
    c.call("PATCH", f"/v1/gameCenterAppVersions/{cur['id']}", {"data": {
        "type": "gameCenterAppVersions", "id": cur["id"], "attributes": {"enabled": True}}})
    print("gameCenterAppVersion: enabled")


def ensure_loc(ctx, existing, path, type_, parent_rel, locale, attrs):
    c = ctx.client
    cur = existing.get(locale)
    if cur:
        delta = diff_attrs(cur["attributes"], attrs)
        if delta:
            c.call("PATCH", f"{path}/{cur['id']}", {"data": {"type": type_, "id": cur["id"], "attributes": delta}})
        return cur
    return c.call("POST", path, {"data": {"type": type_, "attributes": {"locale": locale, **attrs},
                                          "relationships": parent_rel}})["data"]


def leaderboards(ctx, detail_id, specs):
    c = ctx.client
    have = {} if is_fake(detail_id) else {
        x["attributes"]["vendorIdentifier"]: x
        for x in c.pages(f"/v1/gameCenterDetails/{detail_id}/gameCenterLeaderboards?limit=200")}
    for sp in specs:
        vid_ = sp["id"]
        lb = have.get(vid_)
        if lb:
            print(f"leaderboard {vid_}: exists")
        else:
            attrs = {"referenceName": sp.get("referenceName") or sp["name"], "vendorIdentifier": vid_,
                     "defaultFormatter": sp.get("formatter", "INTEGER"),
                     "submissionType": sp.get("submission", "BEST_SCORE"),
                     "scoreSortType": sp.get("sort", "DESC"),
                     "scoreRangeStart": str(sp.get("scoreMin", 0)), "scoreRangeEnd": str(sp.get("scoreMax", 1000000000))}
            if sp.get("recurring") == "daily":
                # Bare "P1D" is rejected; the API wants a time based ISO 8601 duration.
                attrs.update({"recurrenceStartDate": next_midnight_utc(), "recurrenceDuration": "PT24H",
                              "recurrenceRule": "FREQ=DAILY;INTERVAL=1"})
            lb = c.call("POST", "/v1/gameCenterLeaderboards", {"data": {
                "type": "gameCenterLeaderboards", "attributes": attrs,
                "relationships": {"gameCenterDetail": rel("gameCenterDetails", detail_id)}}})["data"]
            print(f"leaderboard {vid_}: created")
        locs = {} if is_fake(lb["id"]) else {
            x["attributes"]["locale"]: x for x in c.pages(f"/v1/gameCenterLeaderboards/{lb['id']}/localizations?limit=50")}
        ensure_loc(ctx, locs, "/v1/gameCenterLeaderboardLocalizations", "gameCenterLeaderboardLocalizations",
                   {"gameCenterLeaderboard": rel("gameCenterLeaderboards", lb["id"])},
                   ctx.primary_locale, {"name": sp["name"]})


def achievements(ctx, detail_id, specs):
    c = ctx.client
    have = {} if is_fake(detail_id) else {
        x["attributes"]["vendorIdentifier"]: x
        for x in c.pages(f"/v1/gameCenterDetails/{detail_id}/gameCenterAchievements?limit=200")}
    total = sum(int(s.get("points", 0)) for s in specs)
    if total > 1000:
        die(f"achievement points total {total}; Apple allows at most 1000 across all achievements")
    for i, sp in enumerate(specs, 1):
        ach = have.get(sp["id"])
        want = {"points": int(sp.get("points", 10))}
        if ach:
            delta = diff_attrs(ach["attributes"], want)
            if delta:
                c.call("PATCH", f"/v1/gameCenterAchievements/{ach['id']}", {"data": {
                    "type": "gameCenterAchievements", "id": ach["id"], "attributes": delta}})
            print(f"achievement {sp['id']}: exists")
        else:
            ach = c.call("POST", "/v1/gameCenterAchievements", {"data": {
                "type": "gameCenterAchievements",
                "attributes": {"referenceName": f"{i:02d} {sp['name']}"[:64], "vendorIdentifier": sp["id"],
                               "points": want["points"], "showBeforeEarned": not sp.get("hidden", False),
                               "repeatable": bool(sp.get("repeatable", False))},
                "relationships": {"gameCenterDetail": rel("gameCenterDetails", detail_id)}}})["data"]
            print(f"achievement {sp['id']}: created")
        locs = {} if is_fake(ach["id"]) else {
            x["attributes"]["locale"]: x for x in c.pages(f"/v1/gameCenterAchievements/{ach['id']}/localizations?limit=50")}
        loc = ensure_loc(ctx, locs, "/v1/gameCenterAchievementLocalizations", "gameCenterAchievementLocalizations",
                         {"gameCenterAchievement": rel("gameCenterAchievements", ach["id"])}, ctx.primary_locale,
                         {"name": sp["name"], "beforeEarnedDescription": sp.get("beforeDescription") or sp.get("description", ""),
                          "afterEarnedDescription": sp.get("afterDescription") or sp.get("description", "")})
        img = sp.get("image")
        if img and not os.path.isabs(img):
            img = os.path.join(os.getcwd(), img)
        if img and os.path.exists(img):
            cur = None if is_fake(loc["id"]) else c.get(f"/v1/gameCenterAchievementLocalizations/{loc['id']}/gameCenterAchievementImage")
            cur = (cur or {}).get("data")
            if cur and (cur["attributes"].get("assetDeliveryState") or {}).get("state") in ("COMPLETE", "UPLOAD_COMPLETE"):
                continue
            if cur:
                c.call("DELETE", f"/v1/gameCenterAchievementImages/{cur['id']}")
            upload_asset(c, "gameCenterAchievementImages", "gameCenterAchievementLocalization",
                         "gameCenterAchievementLocalizations", loc["id"], img, "/v1/gameCenterAchievementImages")


def cmd_game_center(ctx):
    gc = ctx.s("store", "gameCenter", default={}) or {}
    if not gc:
        die("ship.json store.gameCenter is empty (expects leaderboards and/or achievements lists)")
    if "GAME_CENTER" not in wanted_capabilities(ctx):
        print("note: GAME_CENTER capability is not requested; run bundle-id after setting features.gameCenter")
    detail = ensure_detail(ctx)
    leaderboards(ctx, detail, gc.get("leaderboards") or [])
    achievements(ctx, detail, gc.get("achievements") or [])
    ensure_app_version_enabled(ctx)
    print("note: Game Center items must also be attached to the version in the web UI the first time, and "
          "the app binary needs the Game Center entitlement.")
