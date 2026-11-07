"""Shared App Store Connect helpers for the ship-store toolkit.

Stdlib only. ES256 signing uses `cryptography` when installed, otherwise the
`openssl` binary (present on macOS and nearly every Linux).

Rules every command follows:
  * GET first, PATCH what exists, POST only what is missing.
  * Mutating calls (POST/PATCH/DELETE) go through Client.call(); with dry_run they
    are printed and never sent. GETs are always real, so a dry run shows the true diff.
  * Credentials are never printed. Errors print the ASC error body, nothing else.
"""
import base64
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

BASE = "https://api.appstoreconnect.apple.com"
DEFAULT_SHIP = os.path.join(".ship", "ship.json")
DEFAULTS_FILE = os.path.join("~", ".config", "shipkit", "defaults.json")


class ASCError(Exception):
    def __init__(self, method, path, status, body):
        self.method, self.path, self.status, self.body = method, path, status, body
        errs = body.get("errors", body) if isinstance(body, dict) else body
        super().__init__(f"{method} {path} -> HTTP {status}: {json.dumps(errs)[:2000]}")


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(code)


# --------------------------------------------------------------------------- config

def expand(p):
    return os.path.expanduser(os.path.expandvars(p))


def read_json(path):
    with open(expand(path), encoding="utf-8") as f:
        return json.load(f)


def load_ship(path):
    path = path or DEFAULT_SHIP
    if not os.path.exists(path):
        die(f"{path} not found. Run the ship skill intake first, or pass --ship PATH.")
    return read_json(path)


def save_ship(path, ship):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ship, f, indent=2, ensure_ascii=False)
        f.write("\n")


def dig(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d if d not in (None,) else default


def parse_env_file(path):
    env = {}
    with open(expand(path), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:]
            k, v = line.split("=", 1)
            v = re.sub(r"\s+#.*$", "", v).strip().strip("'\"")
            env[k.strip()] = expand(v)
    return env


def split_secret_ref(ref):
    """'path/to/file.env:VAR' -> (path, VAR); a bare path -> (path, None)."""
    m = re.match(r"^(.*\.[A-Za-z0-9]+):([A-Z][A-Z0-9_]*)$", ref or "")
    return (m.group(1), m.group(2)) if m else (ref, None)


def resolve_asc_creds(ship):
    """Order: ship.json secrets.ascEnv, env vars, ~/.config/shipkit/defaults.json secrets.ascEnv."""
    need = ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_PATH")
    refs = []
    ref = dig(ship, "secrets", "ascEnv", default="")
    if ref:
        refs.append(("ship.json secrets.ascEnv", ref))
    if all(os.environ.get(k) for k in need):
        return {k: expand(os.environ[k]) for k in need}
    try:
        dref = dig(read_json(DEFAULTS_FILE), "secrets", "ascEnv", default="")
        if dref:
            refs.append((f"{DEFAULTS_FILE} secrets.ascEnv", dref))
    except (OSError, ValueError):
        pass
    for label, r in refs:
        path, _ = split_secret_ref(r)
        try:
            env = parse_env_file(path)
        except OSError:
            print(f"warning: {label} points at {path}, which cannot be read", file=sys.stderr)
            continue
        if all(env.get(k) for k in need):
            return {k: env[k] for k in need}
        print(f"warning: {path} is missing one of {', '.join(need)}", file=sys.stderr)
    die("no App Store Connect key found. Set secrets.ascEnv in .ship/ship.json (a file with "
        "ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_PATH), or export those three variables, or set "
        f"secrets.ascEnv in {DEFAULTS_FILE}.")


# --------------------------------------------------------------------------- JWT (ES256)

def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def der_to_raw(der):
    """ECDSA DER signature -> raw r||s (32 bytes each), as JWT ES256 requires."""
    if der[0] != 0x30:
        raise ValueError("bad DER signature")
    i = 2 if der[1] < 0x80 else 2 + (der[1] & 0x7F)
    out = b""
    for _ in range(2):
        if der[i] != 0x02:
            raise ValueError("bad DER integer")
        ln = der[i + 1]
        n = der[i + 2:i + 2 + ln].lstrip(b"\x00")
        out += n.rjust(32, b"\x00")
        i += 2 + ln
    return out


def sign_es256(key_path, data):
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    except ImportError:
        return sign_with_openssl(key_path, data)
    with open(key_path, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    r, s = decode_dss_signature(key.sign(data, ec.ECDSA(hashes.SHA256())))
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def sign_with_openssl(key_path, data):
    try:
        res = subprocess.run(["openssl", "dgst", "-sha256", "-sign", key_path],
                             input=data, capture_output=True, check=True)
    except FileNotFoundError:
        die("need either `pip install cryptography` or the openssl binary to sign API tokens")
    except subprocess.CalledProcessError as e:
        die("openssl could not sign with the .p8 key: " + e.stderr.decode(errors="replace").strip()[:200])
    return der_to_raw(res.stdout)


def make_token(creds):
    header = {"alg": "ES256", "kid": creds["ASC_KEY_ID"], "typ": "JWT"}
    now = int(time.time())
    payload = {"iss": creds["ASC_ISSUER_ID"], "iat": now, "exp": now + 19 * 60,
               "aud": "appstoreconnect-v1"}
    signing = f"{b64url(json.dumps(header).encode())}.{b64url(json.dumps(payload).encode())}"
    return f"{signing}.{b64url(sign_es256(creds['ASC_KEY_PATH'], signing.encode()))}"


# --------------------------------------------------------------------------- HTTP client

def mask(o):
    """Copy of a request body with anything password-like hidden (dry runs print bodies)."""
    if isinstance(o, dict):
        return {k: ("<hidden>" if re.search("password|secret|token", k, re.I) else mask(v))
                for k, v in o.items()}
    if isinstance(o, list):
        return [mask(v) for v in o]
    return o


class Client:
    def __init__(self, creds, dry_run=False, verbose=False):
        self.creds, self.dry_run, self.verbose = creds, dry_run, verbose
        self._tok, self._tok_at, self.planned = None, 0, 0

    def token(self):
        if not self._tok or time.time() - self._tok_at > 15 * 60:
            self._tok, self._tok_at = make_token(self.creds), time.time()
        return self._tok

    def request(self, method, path, body=None):
        """Raw request. Returns (status, json). Never prints credentials."""
        url = path if path.startswith("http") else BASE + path
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(5):
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Authorization", f"Bearer {self.token()}")
            if data is not None:
                req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    raw = resp.read()
                    return resp.status, (json.loads(raw) if raw else {})
            except urllib.error.HTTPError as e:
                raw = e.read()
                if (e.code == 429 or (method == "GET" and e.code >= 500)) and attempt < 4:
                    time.sleep(2 ** attempt * 2)
                    continue
                try:
                    return e.code, json.loads(raw)
                except ValueError:
                    return e.code, {"raw": raw.decode(errors="replace")[:1500]}
            except urllib.error.URLError as e:
                if attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                die(f"network error talking to App Store Connect: {e.reason}")

    def plan(self, method, path, body):
        self.planned += 1
        shown = json.dumps(mask(body), ensure_ascii=False) if body is not None else ""
        if not self.verbose and len(shown) > 700:
            shown = shown[:700] + f"... ({len(shown)} chars)"
        print(f"[dry-run] {method} {path} {shown}".rstrip())
        return {"data": {"id": f"DRYRUN-{self.planned}", "type": "dryrun",
                         "attributes": {"uploadOperations": []}}}

    def call(self, method, path, body=None, allow=()):
        """GET always runs. POST/PATCH/DELETE are only planned when dry_run."""
        method = method.upper()
        if method != "GET" and self.dry_run:
            return self.plan(method, path, body)
        if "DRYRUN-" in path:
            return {"data": []}
        status, out = self.request(method, path, body)
        if status >= 400 and status not in allow:
            raise ASCError(method, path, status, out)
        if status >= 400:
            return None
        return out

    def get(self, path):
        """GET returning None on 404 (and for planned-only resources in a dry run)."""
        if "DRYRUN-" in path:
            return None
        return self.call("GET", path, allow=(404,))

    def pages(self, path):
        out = []
        while path and "DRYRUN-" not in path:
            o = self.get(path)
            if not o:
                break
            d = o.get("data", [])
            out += d if isinstance(d, list) else [d]
            nxt = (o.get("links") or {}).get("next")
            path = nxt.replace(BASE, "") if nxt else None
        return out

    def included(self, path):
        """GET one page and return (data, included) for include= queries."""
        o = self.get(path) or {}
        return o.get("data"), o.get("included", [])


def rel(type_, id_):
    return {"data": {"type": type_, "id": id_}} if id_ else {"data": None}


def is_fake(id_):
    return isinstance(id_, str) and id_.startswith("DRYRUN-")


# --------------------------------------------------------------------------- app context

EDITABLE_VERSION_STATES = {"PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED",
                           "METADATA_REJECTED", "INVALID_BINARY", "WAITING_FOR_REVIEW"}


class Ctx:
    def __init__(self, args):
        self.ship_path = args.ship or DEFAULT_SHIP
        self.ship = load_ship(self.ship_path)
        self.dry = bool(getattr(args, "dry_run", False))
        self.args = args
        self.client = Client(resolve_asc_creds(self.ship), self.dry, getattr(args, "verbose", False))
        self._app = None
        self._version = None
        self.ship_dir = os.path.dirname(os.path.abspath(self.ship_path))

    # ship.json shortcuts
    def s(self, *keys, default=None):
        return dig(self.ship, *keys, default=default)

    @property
    def bundle_id(self):
        return self.s("app", "bundleId", default="")

    @property
    def primary_locale(self):
        return self.s("app", "primaryLocale", default="en-US")

    def locales(self):
        loc = self.s("listing", default={}) or {}
        return [k for k in loc if isinstance(loc[k], dict)]

    def urls(self):
        return self.s("site", "urls", default={}) or {}

    # app
    def app_id(self):
        if self._app:
            return self._app
        c = self.client
        aid = self.s("app", "ascAppId", default="")
        if aid:
            o = c.get(f"/v1/apps/{aid}?fields[apps]=bundleId,name")
            if not o:
                die(f"app {aid} (ship.json app.ascAppId) not found for this API key")
            have = o["data"]["attributes"]["bundleId"]
            if self.bundle_id and have != self.bundle_id:
                die(f"app {aid} has bundle ID {have} but ship.json says {self.bundle_id}; refusing to continue")
        else:
            if not self.bundle_id:
                die("ship.json app.bundleId is empty")
            apps = c.pages(f"/v1/apps?filter[bundleId]={self.bundle_id}")
            if not apps:
                die(f"no App Store Connect app exists for {self.bundle_id}. Create the app record once in "
                    "the web UI (see SKILL.md, step 2), then re-run.")
            aid = apps[0]["id"]
            if not self.dry:
                self.ship.setdefault("app", {})["ascAppId"] = aid
                save_ship(self.ship_path, self.ship)
                print(f"saved app.ascAppId={aid} to {self.ship_path}")
        self._app = aid
        return aid

    def version(self, create=False):
        """The appStoreVersion matching app.marketingVersion (created when create=True)."""
        if self._version or (self._version is False and not create):
            return self._version or None
        want = self.s("app", "marketingVersion", default="1.0.0")
        vs = self.client.pages(f"/v1/apps/{self.app_id()}/appStoreVersions?filter[platform]=IOS&limit=50")
        v = next((x for x in vs if x["attributes"]["versionString"] == want), None)
        if not v:
            editable = [x for x in vs if x["attributes"]["appStoreState"] in EDITABLE_VERSION_STATES]
            if editable:
                have = editable[0]["attributes"]["versionString"]
                die(f"version {have} is still editable but ship.json app.marketingVersion is {want}. "
                    "Align one of them (an editable version cannot coexist with a new one).")
            if not create:
                self._version = False
                return None
            v = self.client.call("POST", "/v1/appStoreVersions", {"data": {
                "type": "appStoreVersions",
                "attributes": {"platform": "IOS", "versionString": want},
                "relationships": {"app": rel("apps", self.app_id())}}})["data"]
            print(f"created version {want}")
        self._version = v
        return v

    def version_id(self, create=False):
        v = self.version(create)
        return v["id"] if v else None

    def is_first_version(self):
        vs = self.client.pages(f"/v1/apps/{self.app_id()}/appStoreVersions?filter[platform]=IOS&limit=50")
        return not any(x["attributes"]["appStoreState"] in
                       ("READY_FOR_SALE", "PENDING_DEVELOPER_RELEASE", "REPLACED_WITH_NEW_VERSION",
                        "REMOVED_FROM_SALE", "DEVELOPER_REMOVED_FROM_SALE") for x in vs)

    def info_id(self):
        infos = self.client.pages(f"/v1/apps/{self.app_id()}/appInfos")
        if not infos:
            die("app has no appInfo yet")
        pick = next((i for i in infos if i["attributes"].get("state") != "READY_FOR_DISTRIBUTION"), infos[0])
        return pick["id"]

    def territories(self):
        if not hasattr(self, "_terr"):
            self._terr = [t["id"] for t in self.client.pages("/v1/territories?limit=200")]
        return self._terr


# --------------------------------------------------------------------------- limits

def check_limits(listing):
    """Return a list of problems across every locale. Apple's limits, plus the keyword rule."""
    bad = []
    for loc, t in listing.items():
        if not isinstance(t, dict):
            continue
        lim = {"name": 30, "subtitle": 30, "keywords": 100, "promotionalText": 170,
               "description": 4000, "whatsNew": 4000}
        for k, n in lim.items():
            if len(t.get(k) or "") > n:
                bad.append(f"{loc}.{k}: {len(t[k])} chars, limit {n}")
        kws = [w.strip() for w in (t.get("keywords") or "").split(",") if w.strip()]
        if ", " in (t.get("keywords") or ""):
            bad.append(f"{loc}.keywords: remove spaces after commas (they eat the 100 character budget)")
        taken = set(re.findall(r"[\w']+", f"{t.get('name', '')} {t.get('subtitle', '')}".lower()))
        dup = [w for w in kws if any(p in taken for p in re.findall(r"[\w']+", w.lower()))]
        if dup:
            bad.append(f"{loc}.keywords repeat words already in name/subtitle (wasted budget): {dup}")
        if len(set(k.lower() for k in kws)) != len(kws):
            bad.append(f"{loc}.keywords contain duplicates")
        for k in ("name", "subtitle", "keywords", "promotionalText", "description", "whatsNew"):
            if re.search("[" + chr(0x2013) + chr(0x2014) + "]", t.get(k) or ""):
                bad.append(f"{loc}.{k}: contains an en or em dash (reads as AI text; use commas or periods)")
    return bad


# --------------------------------------------------------------------------- uploads

def put_parts(ops, data):
    """PUT each upload operation's byte range to the URL ASC handed back (not the ASC API itself)."""
    for op in ops:
        chunk = data[op["offset"]:op["offset"] + op["length"]]
        req = urllib.request.Request(op["url"], data=chunk, method=op["method"])
        for h in op.get("requestHeaders") or []:
            req.add_header(h["name"], h["value"])
        with urllib.request.urlopen(req, timeout=300) as resp:
            if resp.status >= 300:
                die(f"asset part upload failed: HTTP {resp.status}")


def wait_complete(client, get_path, label, timeout=300):
    t0 = time.time()
    while True:
        o = client.get(get_path)
        st = ((o or {}).get("data", {}).get("attributes", {}).get("assetDeliveryState") or {})
        if st.get("state") in ("COMPLETE", "FAILED"):
            if st["state"] == "FAILED":
                print(f"   {label}: FAILED {json.dumps(st.get('errors'))[:400]}")
            return st
        if time.time() - t0 > timeout:
            return {"state": f"TIMEOUT({st.get('state')})"}
        time.sleep(3)


def upload_asset(client, type_, rel_name, rel_type, rel_id, path, get_prefix, extra_attrs=None):
    """The ASC asset flow: reserve (POST), PUT the parts, commit (PATCH uploaded + md5), poll.

    Returns the new resource id (a fake id in a dry run)."""
    data = open(path, "rb").read()
    name = os.path.basename(path)
    attrs = {"fileName": name, "fileSize": len(data), **(extra_attrs or {})}
    res = client.call("POST", f"/v1/{type_}", {"data": {
        "type": type_, "attributes": attrs, "relationships": {rel_name: rel(rel_type, rel_id)}}})["data"]
    if client.dry_run:
        return res["id"]
    put_parts(res["attributes"]["uploadOperations"], data)
    client.call("PATCH", f"/v1/{type_}/{res['id']}", {"data": {
        "type": type_, "id": res["id"],
        "attributes": {"uploaded": True, "sourceFileChecksum": hashlib.md5(data).hexdigest()}}})
    st = wait_complete(client, f"/v1/{type_}/{res['id']}", name)
    print(f"   uploaded {name} ({len(data) // 1024} KB): {st.get('state')}")
    return res["id"]


def md5_file(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def png_info(path):
    """(width, height, has_alpha) read from the PNG header, no imaging library needed."""
    with open(path, "rb") as f:
        head = f.read(33)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    w, h = struct.unpack(">II", head[16:24])
    return w, h, head[25] in (4, 6)


def diff_attrs(current, wanted):
    """Subset of `wanted` that differs from `current` (empty wanted values are ignored)."""
    return {k: v for k, v in wanted.items() if v not in (None, "") and current.get(k) != v}
