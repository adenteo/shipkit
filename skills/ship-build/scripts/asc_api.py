#!/usr/bin/env python3
"""Tiny read-only App Store Connect API client (GET only, stdlib + openssl).

Used by preflight (is this version already live?) and release.sh (next build number).
Mutations (metadata, IAP, TestFlight, submit) belong to ship-store, not here.

  asc_api.py live-version  <ship.json>      newest version string that has shipped, or ""
  asc_api.py editable-version <ship.json>   version string currently being prepared, or ""
  asc_api.py last-build <ship.json> [ver]   highest build number uploaded (for ver if given)
"""
import base64, json, os, subprocess, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shipjson


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def der_to_raw(der):
    # ECDSA DER -> r||s (32 bytes each)
    assert der[0] == 0x30
    i = 2 if der[1] < 0x80 else 2 + (der[1] & 0x7F)
    parts = []
    for _ in range(2):
        assert der[i] == 0x02
        n = der[i + 1]
        parts.append(int.from_bytes(der[i + 2:i + 2 + n], "big").to_bytes(32, "big"))
        i += 2 + n
    return b"".join(parts)


def token(key_id, issuer, key_path):
    head = b64(json.dumps({"alg": "ES256", "kid": key_id, "typ": "JWT"}).encode())
    body = b64(json.dumps({"iss": issuer, "iat": int(time.time()),
                           "exp": int(time.time()) + 600, "aud": "appstoreconnect-v1"}).encode())
    msg = f"{head}.{body}".encode()
    der = subprocess.run(["openssl", "dgst", "-sha256", "-sign", key_path],
                         input=msg, capture_output=True, check=True).stdout
    return f"{head}.{body}.{b64(der_to_raw(der))}"


def get(ship, path, params=None):
    kid, iss, kp = shipjson.asc_credentials(ship)
    if not (kid and iss and os.path.isfile(kp)):
        raise RuntimeError("no App Store Connect credentials")
    url = "https://api.appstoreconnect.apple.com" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token(kid, iss, kp)})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def vkey(v):
    return tuple(int(x) if x.isdigit() else 0 for x in v.split("."))


SHIPPED = {"READY_FOR_SALE", "PENDING_DEVELOPER_RELEASE", "PENDING_APPLE_RELEASE", "PROCESSING_FOR_APP_STORE",
           "IN_REVIEW", "WAITING_FOR_REVIEW", "REMOVED_FROM_SALE", "DEVELOPER_REMOVED_FROM_SALE",
           "PENDING_CONTRACT", "REPLACED_WITH_NEW_VERSION", "ACCEPTED"}
EDITABLE = {"PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED", "INVALID_BINARY"}


def versions(ship):
    app = shipjson.get(ship, "app.ascAppId")
    if not app:
        raise RuntimeError("no ascAppId yet")
    d = get(ship, f"/v1/apps/{app}/appStoreVersions", {"limit": 50, "filter[platform]": "IOS"})
    return [(x["attributes"]["versionString"], x["attributes"].get("appStoreState", "")) for x in d["data"]]


def last_build(ship, version=None):
    app = shipjson.get(ship, "app.ascAppId")
    if not app:
        raise RuntimeError("no ascAppId yet")
    p = {"filter[app]": app, "sort": "-uploadedDate", "limit": 50}
    if version:
        p["filter[preReleaseVersion.version]"] = version
    d = get(ship, "/v1/builds", p)
    nums = [int(x["attributes"]["version"]) for x in d["data"] if x["attributes"]["version"].isdigit()]
    return max(nums) if nums else 0


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, ship = sys.argv[1], sys.argv[2]
    try:
        if cmd == "live-version":
            live = [v for v, s in versions(ship) if s in SHIPPED]
            print(max(live, key=vkey) if live else "")
        elif cmd == "editable-version":
            ed = [v for v, s in versions(ship) if s in EDITABLE]
            print(max(ed, key=vkey) if ed else "")
        elif cmd == "last-build":
            print(last_build(ship, sys.argv[3] if len(sys.argv) > 3 else None))
        else:
            sys.exit(__doc__)
    except Exception as e:  # network, auth, missing creds: callers treat as "unknown"
        print(f"asc_api: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
