#!/usr/bin/env python3
"""Pre-archive checks for an iOS app repo. Prints a PASS/WARN/FAIL/SKIP table, exits 1 on any FAIL.

  preflight.py [--repo .] [--ship .ship/ship.json] [--version 1.2.0] [--offline] [--json]

Checks: app icon 1024 (no alpha), permission usage strings, privacy manifest, export
compliance key, bundle id vs ship.json, deployment target, test ad IDs and keys left in
the repo, version vs the live App Store version. Read-only: it never changes the repo and
only does GET requests to App Store Connect (skipped with --offline).

False positive? Add a regex per line to .ship/preflight-allow.txt; any finding whose
"path:line text" matches is ignored.
"""
import json, os, re, struct, subprocess, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shipjson

SKIP_DIRS = {"node_modules", "Pods", "build", ".build", "DerivedData", ".git", ".ship", "vendor",
             "dist", ".expo", ".next", "Carthage", "xcuserdata", ".gradle", "android"}
rows = []


def add(status, check, detail=""):
    rows.append((status, check, detail))


def walk(root, exts=None, names=None, max_size=2_000_000):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            p = os.path.join(dp, fn)
            if names and fn in names:
                yield p
            elif exts and os.path.splitext(fn)[1] in exts:
                try:
                    if os.path.getsize(p) <= max_size:
                        yield p
                except OSError:
                    pass


def read(p):
    try:
        with open(p, errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def png_info(path):
    """(width, height, has_alpha) from a PNG, or None."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h, depth, ctype = struct.unpack(">IIBB", data[16:26])
    return w, h, ctype in (4, 6) or b"tRNS" in data[:4096] or b"tRNS" in data


# ---------------------------------------------------------------- context
def build_context(repo):
    c = {"repo": repo}
    c["pbx"] = "\n".join(read(p) for p in walk(repo, names={"project.pbxproj"}))
    c["ymls"] = "\n".join(read(p) for p in walk(repo, names={"project.yml"}))
    c["plists"] = {p: read(p) for p in walk(repo, names={"Info.plist"})}
    c["appjson"] = read(os.path.join(repo, "app.json"))
    c["pkg"] = read(os.path.join(repo, "package.json"))
    c["expo_cfg"] = ""
    if os.path.isfile(os.path.join(repo, "package.json")) and '"expo"' in c["pkg"] \
            and os.path.isdir(os.path.join(repo, "node_modules")) \
            and any(os.path.isfile(os.path.join(repo, f)) for f in ("app.config.ts", "app.config.js")):
        try:  # dynamic config: let expo evaluate it (read-only)
            r = subprocess.run(["npx", "--no-install", "expo", "config", "--json"], cwd=repo,
                               capture_output=True, text=True, timeout=90)
            c["expo_cfg"] = r.stdout
        except Exception:
            pass
    c["config_text"] = "\n".join([c["pbx"], c["ymls"], "\n".join(c["plists"].values()), c["appjson"], c["expo_cfg"]])
    c["is_js"] = '"expo"' in c["pkg"] or '"react-native"' in c["pkg"]
    c["swift_src"] = [(p, read(p)) for p in walk(repo, exts={".swift", ".m", ".mm"})]
    return c


def expo_json(c):
    for t in (c["expo_cfg"], c["appjson"]):
        try:
            d = json.loads(t)
            return d.get("expo", d)
        except ValueError:
            continue
    return {}


# ---------------------------------------------------------------- checks
def check_icon(c, repo):
    best = None
    for dp, dns, fns in os.walk(repo):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for d in dns:
            if d.endswith(".appiconset"):
                try:
                    cj = json.load(open(os.path.join(dp, d, "Contents.json")))
                except (OSError, ValueError):
                    continue
                for im in cj.get("images", []):
                    if im.get("size") == "1024x1024" and im.get("filename"):
                        best = os.path.join(dp, d, im["filename"])
                        break
    if not best:
        ex = expo_json(c)
        ic = ex.get("icon") or (ex.get("ios") or {}).get("icon")
        if isinstance(ic, str) and os.path.isfile(os.path.join(repo, ic)):
            best = os.path.join(repo, ic)
    if not best:
        cands = [p for p in walk(repo, exts={".png"}) if re.search(r"(^|/)icon[^/]*\.png$", p, re.I)]
        if cands:
            best = sorted(cands)[0]
    if not best:
        icons = [d for dp, dns, _ in os.walk(repo) for d in dns if d.endswith(".icon")]
        if icons:
            add("SKIP", "App icon 1024", "Icon Composer .icon bundle found; Xcode renders it, check the preview by hand")
        else:
            add("FAIL", "App icon 1024", "no 1024x1024 icon found in an AppIcon set or app.json")
        return
    info = png_info(best)
    rel = os.path.relpath(best, repo)
    if not info:
        add("FAIL", "App icon 1024", f"{rel} is not a readable PNG")
    elif (info[0], info[1]) != (1024, 1024):
        add("FAIL", "App icon 1024", f"{rel} is {info[0]}x{info[1]}, need 1024x1024")
    elif info[2]:
        add("FAIL", "App icon alpha", f"{rel} has an alpha channel; App Store rejects it. Flatten onto a solid colour")
    else:
        add("PASS", "App icon 1024", f"{rel}, no alpha")


# (label, native code regex, extra same-file regex, npm package regex, accepted plist keys, expo plugin synonyms)
PERMS = [
    ("Camera", r"AVCaptureDevice|AVCaptureSession|AVCapturePhotoOutput|DataScannerViewController|VNDocumentCameraViewController", None,
     r"expo-camera|react-native-vision-camera|react-native-camera|expo-barcode-scanner", ["NSCameraUsageDescription"], ["cameraPermission"]),
    ("Camera (picker)", r"UIImagePickerController", r"\.camera\b", r"$^", ["NSCameraUsageDescription"], ["cameraPermission"]),
    ("Microphone", r"AVAudioRecorder|requestRecordPermission|AVAudioApplication|AVCaptureDevice.*audio|\.record\b", r"AVAudio|AVCapture",
     r"expo-audio|expo-av|react-native-audio|vision-camera", ["NSMicrophoneUsageDescription"], ["microphonePermission", "recordAudioAndroid"]),
    ("Speech recognition", r"SFSpeechRecognizer|SpeechAnalyzer|SpeechTranscriber", None,
     r"expo-speech-recognition|react-native-voice|@react-native-voice", ["NSSpeechRecognitionUsageDescription"], ["speechRecognitionPermission"]),
    ("Photo library", r"PHPhotoLibrary\.(requestAuthorization|authorizationStatus)|PHAsset\b|PHFetchResult", None,
     r"expo-media-library|expo-image-picker|react-native-image-picker|react-native-camera-roll|camera-roll", ["NSPhotoLibraryUsageDescription"], ["photosPermission"]),
    ("Photo library (add only)", r"UIImageWriteToSavedPhotosAlbum|PHAssetChangeRequest|PHAssetCreationRequest", None,
     r"expo-media-library|camera-roll", ["NSPhotoLibraryAddUsageDescription", "NSPhotoLibraryUsageDescription"], ["savePhotosPermission", "photosPermission"]),
    ("Location", r"CLLocationManager|requestWhenInUseAuthorization|requestAlwaysAuthorization|CLMonitor", None,
     r"expo-location|react-native-geolocation|react-native-maps|geolocation", ["NSLocationWhenInUseUsageDescription", "NSLocationAlwaysAndWhenInUseUsageDescription"],
     ["locationWhenInUsePermission", "locationAlwaysAndWhenInUsePermission", "locationAlwaysPermission"]),
    ("Contacts", r"CNContactStore|CNContactPicker", r"CNContactStore", r"expo-contacts|react-native-contacts", ["NSContactsUsageDescription"], ["contactsPermission"]),
    ("Calendars", r"EKEventStore", None, r"expo-calendar|react-native-calendar", ["NSCalendarsUsageDescription", "NSCalendarsFullAccessUsageDescription", "NSCalendarsWriteOnlyAccessUsageDescription"], ["calendarPermission"]),
    ("Face ID", r"LAContext", None, r"expo-local-authentication|react-native-biometrics", ["NSFaceIDUsageDescription"], ["faceIDPermission"]),
    ("Bluetooth", r"CBCentralManager|CBPeripheralManager", None, r"react-native-ble|expo-bluetooth|react-native-bluetooth", ["NSBluetoothAlwaysUsageDescription"], ["bluetoothAlwaysPermission"]),
    ("Motion", r"CMMotionActivityManager|CMPedometer|CMAltimeter", None, r"expo-sensors|react-native-sensors", ["NSMotionUsageDescription"], ["motionPermission"]),
    ("HealthKit", r"HKHealthStore", None, r"react-native-health|expo-health", ["NSHealthShareUsageDescription", "NSHealthUpdateUsageDescription"], ["healthSharePermission"]),
    ("Tracking (ATT)", r"ATTrackingManager|ASIdentifierManager", None, r"expo-tracking-transparency|react-native-tracking-transparency", ["NSUserTrackingUsageDescription"], ["userTrackingPermission"]),
]


def check_permissions(c, ship_features):
    cfg = c["config_text"]
    pkg = c["pkg"]
    problems, ok = [], []
    for label, rx, extra, npm, keys, syn in PERMS:
        used = False
        for p, t in c["swift_src"]:
            if re.search(rx, t) and (not extra or re.search(extra, t)):
                used = True
                break
        if not used and c["is_js"] and re.search(npm, pkg):
            used = True
        if label.startswith("Tracking") and not used and ship_features.get("ads", "none") not in ("none", ""):
            used = True  # ads normally means ATT
        if not used:
            continue
        have = any(k in cfg for k in keys) or any(s in cfg for s in syn)
        if have and all(re.search(rf"<key>{k}</key>\s*<string>\s*</string>", cfg) is None for k in keys if k in cfg):
            ok.append(label)
        elif have:
            problems.append(f"{label}: usage string is empty")
        else:
            problems.append(f"{label}: add {keys[0]}")
    if problems:
        add("FAIL", "Permission strings", "; ".join(problems))
    elif ok:
        add("PASS", "Permission strings", "declared for " + ", ".join(ok))
    else:
        add("PASS", "Permission strings", "no permission-gated APIs found in code")
    ads = ship_features.get("ads", "none")
    if ads == "admob" and "GADApplicationIdentifier" not in cfg and "iosAppId" not in cfg:
        add("FAIL", "AdMob app ID", "ads is admob but no GADApplicationIdentifier / iosAppId (the app crashes at launch)")


REQ = [
    ("UserDefaults", "NSPrivacyAccessedAPICategoryUserDefaults", r"UserDefaults|NSUserDefaults|@AppStorage|AppStorage\("),
    ("File timestamps", "NSPrivacyAccessedAPICategoryFileTimestamp",
     r"\.(creationDate|modificationDate)\b|contentModificationDateKey|creationDateKey|NSFileCreationDate|NSFileModificationDate|\bstat\("),
    ("System boot time", "NSPrivacyAccessedAPICategorySystemBootTime", r"systemUptime|mach_absolute_time|clock_gettime"),
    ("Disk space", "NSPrivacyAccessedAPICategoryDiskSpace", r"volumeAvailableCapacity|systemFreeSize|systemSize|statfs|statvfs"),
    ("Active keyboards", "NSPrivacyAccessedAPICategoryActiveKeyboards", r"activeInputModes"),
]


def check_privacy_manifest(c, repo):
    files = list(walk(repo, names={"PrivacyInfo.xcprivacy"}))
    text = "\n".join(read(p) for p in files)
    expo_pm = "privacyManifests" in c["appjson"] or "privacyManifests" in c["expo_cfg"]
    if not files and not expo_pm:
        add("FAIL", "Privacy manifest", "no PrivacyInfo.xcprivacy (required since 2024; list required-reason APIs even if you only use them in code)")
        return
    text += c["appjson"] + c["expo_cfg"]
    used = [(n, cat) for n, cat, rx in REQ if any(re.search(rx, t) for _, t in c["swift_src"])]
    if c["is_js"]:  # React Native core touches these
        used += [(n, cat) for n, cat, _ in REQ[:3] if (n, cat) not in used]
    missing = [n for n, cat in used if cat not in text]
    if missing:
        add("WARN", "Privacy manifest", "present, but no entry for: " + ", ".join(missing) + " (code or RN core appears to use it)")
    else:
        add("PASS", "Privacy manifest", "present" + (f", covers {len(used)} required-reason categories" if used else ""))


def check_encryption(c):
    if "ITSAppUsesNonExemptEncryption" in c["config_text"] or "usesNonExemptEncryption" in c["config_text"] \
            or "INFOPLIST_KEY_ITSAppUsesNonExemptEncryption" in c["config_text"]:
        add("PASS", "Export compliance", "ITSAppUsesNonExemptEncryption is set")
    else:
        add("FAIL", "Export compliance", "set ITSAppUsesNonExemptEncryption (false if you only use HTTPS/system crypto) or every upload stalls on a question")


def check_bundle_id(c, ship):
    want = shipjson.get(ship, "app.bundleId") or ""
    cands = set(re.findall(r"PRODUCT_BUNDLE_IDENTIFIER\s*[=:]\s*\"?([A-Za-z0-9.\-_$()]+)", c["pbx"] + "\n" + c["ymls"]))
    cands |= set(re.findall(r"bundleIdentifier\"?\s*[:=]\s*\"([^\"]+)\"", c["appjson"] + c["expo_cfg"]))
    cands = {x for x in cands if not re.search(r"(?i)tests?$|\.tests?\b|widget|extension|clip", x)} or cands
    if not want:
        add("FAIL", "Bundle ID", "app.bundleId is empty in ship.json")
    elif not cands:
        add("SKIP", "Bundle ID", "no bundle id in project files (dynamic config?); verify " + want)
    elif want in cands:
        add("PASS", "Bundle ID", want)
    elif all("$(" in x for x in cands):
        add("SKIP", "Bundle ID", "set through variables; verify it resolves to " + want)
    else:
        add("FAIL", "Bundle ID", f"ship.json says {want}, project says {', '.join(sorted(cands))}")


def check_deployment(c):
    vals = re.findall(r"IPHONEOS_DEPLOYMENT_TARGET\s*=\s*\"?([\d.]+)", c["pbx"])
    vals += re.findall(r"iOS:\s*\"?([\d.]+)", c["ymls"])
    vals += re.findall(r"deploymentTarget\"?\s*:\s*\"?(\d+(?:\.\d+)?)", c["appjson"] + c["expo_cfg"])
    nums = [float(re.match(r"\d+(\.\d+)?", v).group()) for v in vals if re.match(r"\d", v)]
    if not nums:
        add("SKIP", "Deployment target", "not found in project files (framework default applies)")
        return
    lo = min(nums)
    if lo < 15:
        add("WARN", "Deployment target", f"iOS {lo:g} is old; current Xcode may refuse it and modern SDKs need 15+")
    elif lo > 18:
        add("WARN", "Deployment target", f"iOS {lo:g} excludes users on older phones; intended?")
    else:
        add("PASS", "Deployment target", f"iOS {lo:g}")


SECRET_RX = [
    ("FAIL", r"ca-app-pub-3940256099942544", "AdMob TEST ad unit or app ID"),
    ("FAIL", r"sk_(test|live)_[A-Za-z0-9]{16,}", "Stripe secret key in the repo"),
    ("WARN", r"pk_test_[A-Za-z0-9]{16,}", "Stripe TEST publishable key"),
    ("WARN", r"\btest_[A-Za-z]{24,}\b", "RevenueCat-style test store key"),
    ("FAIL", r"-----BEGIN (RSA |EC )?PRIVATE KEY-----", "private key committed"),
    ("WARN", r"https?://(localhost|127\.0\.0\.1|10\.0\.2\.2)[:/]", "localhost URL"),
]
TEXT_EXTS = {".swift", ".m", ".mm", ".h", ".plist", ".json", ".js", ".jsx", ".ts", ".tsx", ".yml", ".yaml",
             ".xcconfig", ".pbxproj", ".storekit", ".entitlements", ".gradle", ".kt"}


def check_test_ids(repo):
    allow = []
    for line in read(os.path.join(repo, ".ship", "preflight-allow.txt")).splitlines():
        if line.strip() and not line.startswith("#"):
            allow.append(re.compile(line.strip()))
    hits = {}
    for p in walk(repo, exts=TEXT_EXTS):
        base = os.path.basename(p)
        if base in ("package-lock.json", "yarn.lock", "ship.json") or re.search(r"(?i)(test|spec|mock|fixture)", p.replace(repo, "")):
            continue
        for i, line in enumerate(read(p).splitlines(), 1):
            if len(line) > 600:
                continue
            for sev, rx, label in SECRET_RX:
                if re.search(rx, line):
                    loc = f"{os.path.relpath(p, repo)}:{i}"
                    if any(a.search(f"{loc} {line}") for a in allow):
                        continue
                    hits.setdefault((sev, label), []).append(loc)
    keys = list(walk(repo, exts={".p8"}))
    if keys:
        hits[("FAIL", "App Store Connect .p8 key inside the repo")] = [os.path.relpath(k, repo) for k in keys]
    if not hits:
        add("PASS", "Test IDs and keys", "none found")
        return
    for (sev, label), locs in sorted(hits.items(), key=lambda x: x[0][0]):
        extra = f" (+{len(locs) - 3} more)" if len(locs) > 3 else ""
        add(sev, label, ", ".join(locs[:3]) + extra)


def vkey(v):
    return tuple(int(x) if x.isdigit() else 0 for x in v.split("."))


def check_version(ship, version, offline):
    if not version:
        add("FAIL", "Version", "app.marketingVersion is empty")
        return
    if not re.fullmatch(r"\d+(\.\d+){0,2}", version):
        add("FAIL", "Version", f"{version} is not like 1.2.3")
        return
    if offline or not shipjson.get(ship, "app.ascAppId"):
        add("SKIP", "Version vs live", f"{version}; " + ("offline" if offline else "no ascAppId yet, so this is a first release"))
        return
    try:
        import asc_api
        vs = asc_api.versions(ship)
    except Exception as e:
        add("SKIP", "Version vs live", f"could not reach App Store Connect ({str(e)[:60]})")
        return
    shipped = [v for v, s in vs if s in asc_api.SHIPPED]
    editable = [v for v, s in vs if s in asc_api.EDITABLE]
    live = max(shipped, key=vkey) if shipped else ""
    if version in editable:
        add("PASS", "Version vs live", f"{version} is the open version (live: {live or 'none'})")
    elif live and vkey(version) <= vkey(live):
        add("FAIL", "Version vs live", f"{version} is not above the live/submitted {live}; bump app.marketingVersion")
    else:
        add("PASS", "Version vs live", f"{version} > {live or 'none yet'}")


def main():
    a = sys.argv[1:]

    def opt(name, default=None):
        if name in a:
            i = a.index(name)
            v = a[i + 1] if i + 1 < len(a) else default
            return v
        return default

    repo = os.path.abspath(opt("--repo", "."))
    ship = opt("--ship", os.path.join(repo, ".ship", "ship.json"))
    offline = "--offline" in a
    version = opt("--version") or shipjson.get(ship, "app.marketingVersion") or ""
    features = shipjson.get(ship, "features") or {}
    if not isinstance(features, dict):
        features = {}

    c = build_context(repo)
    check_icon(c, repo)
    check_permissions(c, features)
    check_privacy_manifest(c, repo)
    check_encryption(c)
    check_bundle_id(c, ship)
    check_deployment(c)
    check_test_ids(repo)
    check_version(ship, version, offline)

    if "--json" in a:
        print(json.dumps([{"status": s, "check": k, "detail": d} for s, k, d in rows], indent=2))
    else:
        w = max(len(k) for _, k, _ in rows)
        print(f"{'':6} {'Check'.ljust(w)}  Detail")
        for s, k, d in rows:
            print(f"{s:6} {k.ljust(w)}  {d}")
        n = {s: sum(1 for r in rows if r[0] == s) for s in ("PASS", "WARN", "FAIL", "SKIP")}
        print(f"\n{n['PASS']} pass, {n['WARN']} warn, {n['FAIL']} fail, {n['SKIP']} skipped")
    sys.exit(1 if any(r[0] == "FAIL" for r in rows) else 0)


if __name__ == "__main__":
    main()
