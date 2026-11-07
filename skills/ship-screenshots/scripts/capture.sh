#!/usr/bin/env bash
# Simulator helper for App Store screenshots. Writes raws to .ship/screenshots/raw/<kind>/.
#
#   capture.sh boot [iphone|ipad]            boot a device of the right size and set a clean status bar
#   capture.sh install <path/to/App.app>     install a built simulator app on the booted device
#   capture.sh launch <bundle-id> [args...]  (re)launch the app, optionally with launch arguments
#   capture.sh open <url>                    open a deep link or universal link in the app
#   capture.sh appearance light|dark         switch the simulator appearance
#   capture.sh shot <name> [iphone|ipad]     capture raw/<kind>/<name>.png (re-asserts the clean status bar)
#   capture.sh clean                         remove status bar overrides
#
# Kinds: iphone = iPhone 6.9 inch class (Pro Max, 1320x2868), ipad = iPad Pro 13 inch (2064x2752).
# Use the same <name> for iphone and ipad captures so one plan row covers both.
# Env: SHIP_SHOTS_DIR overrides the output folder (default ./.ship/screenshots).
set -euo pipefail
OUT="${SHIP_SHOTS_DIR:-./.ship/screenshots}"
cmd="${1:-}"; shift || true

pick_device() { # pick_device iphone|ipad -> prints "UDID<TAB>name"
  python3 - "$1" <<'PY'
import json, re, subprocess, sys
kind = sys.argv[1]
d = json.loads(subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "-j"]))
pat = re.compile(r"iPhone \d+ Pro Max") if kind == "iphone" else re.compile(r"iPad Pro 1[13]-inch")
best = None
for rt, devs in d["devices"].items():
    if "iOS" not in rt and "iPadOS" not in rt:
        continue
    ver = tuple(int(x) for x in re.findall(r"\d+", rt.split("iOS-")[-1])[:2] or [0])
    for x in devs:
        if pat.search(x["name"]):
            n = tuple(int(y) for y in re.findall(r"\d+", x["name"]))
            key = (x["state"] == "Booted", ver, n)
            if best is None or key > best[0]:
                best = (key, x["udid"], x["name"])
if not best:
    sys.exit("no matching simulator; install one in Xcode > Settings > Components")
print(best[1] + "\t" + best[2])
PY
}

booted_kind() { # which kind is the booted device
  xcrun simctl list devices booted | grep -q "iPad" && echo ipad || echo iphone
}

status_bar() {
  xcrun simctl status_bar booted override --time 9:41 --dataNetwork wifi --wifiMode active --wifiBars 3 \
    --cellularMode active --cellularBars 4 --operatorName "" --batteryState charged --batteryLevel 100
}

case "$cmd" in
  boot)
    kind="${1:-iphone}"
    IFS=$'\t' read -r udid name < <(pick_device "$kind")
    echo "Using $name ($udid)"
    xcrun simctl boot "$udid" 2>/dev/null || true
    open -a Simulator --args -CurrentDeviceUDID "$udid" 2>/dev/null || true
    xcrun simctl bootstatus "$udid" -b >/dev/null
    status_bar
    echo "Booted $name with a clean status bar (9:41, full battery, full signal)."
    ;;
  install) xcrun simctl install booted "${1:?path to .app}" ;;
  launch)
    bid="${1:?bundle id}"; shift
    xcrun simctl terminate booted "$bid" 2>/dev/null || true
    xcrun simctl launch booted "$bid" "$@"
    ;;
  open) xcrun simctl openurl booted "${1:?url}" ;;
  appearance) xcrun simctl ui booted appearance "${1:?light|dark}" ;;
  shot)
    name="${1:?name, e.g. 01-home}"; kind="${2:-$(booted_kind)}"
    mkdir -p "$OUT/raw/$kind"
    status_bar
    sleep 0.6
    xcrun simctl io booted screenshot --type=png "$OUT/raw/$kind/$name.png" >/dev/null 2>&1
    sz="$(sips -g pixelWidth -g pixelHeight "$OUT/raw/$kind/$name.png" | awk '/pixel/{printf "%s ", $2}')"
    echo "saved $OUT/raw/$kind/$name.png ($sz)"
    ;;
  clean) xcrun simctl status_bar booted clear ;;
  *) sed -n '2,16p' "$0"; exit 2 ;;
esac
