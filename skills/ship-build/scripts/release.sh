#!/usr/bin/env bash
# Build a signed App Store archive and (only with --upload) send it to App Store Connect.
#
#   release.sh [--repo .] [--ship .ship/ship.json] [--build N] [--version X.Y.Z]
#              [--upload] [--method xcodebuild|altool] [--skip-preflight] [--dry-run]
#
# Without --upload it stops after producing build/export/*.ipa, so a first run is safe.
# --dry-run prints every command and runs none of the build steps (preflight still runs, read-only).
# Credentials: the env file named in ship.json secrets.ascEnv (ASC_KEY_ID, ASC_ISSUER_ID,
# ASC_KEY_PATH), else ~/.config/shipkit/defaults.json. No Apple ID password is ever used.
# Optional gate: an executable .ship/release-gate.sh is run as
#   release-gate.sh config | archive <path.xcarchive> | ipa <path.ipa>
# before archiving, after archiving and after export; a non-zero exit aborts the release.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="."; SHIP=""; BUILD=""; VERSION=""; UPLOAD=0; DRY=0; SKIP_PRE=0; METHOD="xcodebuild"
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --ship) SHIP="$2"; shift 2 ;;
    --build) BUILD="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --upload) UPLOAD=1; shift ;;
    --method) METHOD="$2"; shift 2 ;;
    --skip-preflight) SKIP_PRE=1; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
cd "$REPO"; REPO="$(pwd)"
SHIP="${SHIP:-$REPO/.ship/ship.json}"
SJ() { python3 "$HERE/shipjson.py" --file "$SHIP" "$@"; }

run() { # print, then run unless dry-run
  printf '+ %s\n' "$*"
  [ "$DRY" = 1 ] || "$@"
}

[ -f "$SHIP" ] || { echo "No $SHIP. Run the ship skill intake first." >&2; exit 1; }
BUNDLE_ID="$(SJ get app.bundleId)"; TEAM="$(SJ get app.teamId)"
[ -n "$BUNDLE_ID" ] || { echo "app.bundleId is empty in ship.json" >&2; exit 1; }
[ -n "$TEAM" ] || { echo "app.teamId is empty in ship.json (or ~/.config/shipkit/defaults.json)" >&2; exit 1; }
VERSION="${VERSION:-$(SJ get app.marketingVersion)}"
[ -n "$VERSION" ] || VERSION="1.0.0"

# ---- credentials (paths only; values are never printed)
ENVFILE="$(SJ asc-env)"
[ -n "$ENVFILE" ] && [ -f "$ENVFILE" ] || { echo "ship.json secrets.ascEnv is not set or the file is missing. It must define ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_PATH." >&2; exit 1; }
set -a; . "$ENVFILE"; set +a
ASC_KEY_PATH="${ASC_KEY_PATH/#\~/$HOME}"
: "${ASC_KEY_ID:?ASC_KEY_ID missing in $ENVFILE}" "${ASC_ISSUER_ID:?ASC_ISSUER_ID missing in $ENVFILE}"
[ -f "$ASC_KEY_PATH" ] || { echo "ASC_KEY_PATH in $ENVFILE does not point to a file" >&2; exit 1; }
AUTH=(-allowProvisioningUpdates -authenticationKeyPath "$ASC_KEY_PATH" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID")

# ---- stack
eval "$("$HERE/detect-stack.sh" "$REPO" | sed -E "s/^([A-Z_]+)=(.*)$/\1='\2'/" | grep -v '^NOTE=')"
NATIVE_DIR_IGNORED="${NATIVE_DIR_IGNORED:-no}"
echo "Stack: $STACK"
case "$STACK" in
  flutter) echo "Flutter is manual: 'flutter build ipa --release --build-name $VERSION --build-number <N>', then upload build/ios/ipa/*.ipa with: xcrun altool --upload-app -f <ipa> -t ios --api-key \$ASC_KEY_ID --api-issuer \$ASC_ISSUER_ID (key file must sit in ~/.appstoreconnect/private_keys)." >&2; exit 3 ;;
  none) echo "No iOS project found." >&2; exit 1 ;;
esac

# ---- build number: explicit, else last uploaded + 1, else 1
if [ -z "$BUILD" ]; then
  LAST="$(python3 "$HERE/asc_api.py" last-build "$SHIP" 2>/dev/null || true)"
  [[ "$LAST" =~ ^[0-9]+$ ]] || LAST="$(SJ get build.lastBuildNumber)"
  [[ "$LAST" =~ ^[0-9]+$ ]] || LAST=0
  BUILD=$((LAST + 1))
fi
echo "Version $VERSION, build $BUILD, bundle $BUNDLE_ID"

# ---- preflight
if [ "$SKIP_PRE" = 0 ]; then
  python3 "$HERE/preflight.py" --repo "$REPO" --ship "$SHIP" --version "$VERSION" || {
    echo "Preflight failed. Fix the FAIL rows (or re-run with --skip-preflight if you accept the risk)." >&2; exit 1; }
fi

GATE="$REPO/.ship/release-gate.sh"
gate() { if [ -x "$GATE" ]; then echo "+ release-gate $*"; [ "$DRY" = 1 ] || "$GATE" "$@"; fi; }
gate config

[ "$DRY" = 1 ] || mkdir -p build
# ---- generate the native project
if [ "$STACK" = expo ]; then
  if [ -f app.json ] && [ "$DRY" = 0 ]; then # keep static config in step with the build we are making
    node -e "const fs=require('fs');const j=JSON.parse(fs.readFileSync('app.json'));const e=j.expo||j;e.version=process.argv[1];e.ios=e.ios||{};e.ios.buildNumber=String(process.argv[2]);fs.writeFileSync('app.json',JSON.stringify(j,null,2)+'\n')" "$VERSION" "$BUILD"
  fi
  CLEAN="--clean"; [ "$NATIVE_DIR_IGNORED" = yes ] || CLEAN=""   # never wipe a committed ios/ folder
  run env CI=1 npx expo prebuild --platform ios $CLEAN --no-install
  [ -d ios ] && { [ "$DRY" = 1 ] && echo "+ (cd ios && pod install)" || (cd ios && pod install >/dev/null); }
elif [ "$STACK" = react-native ]; then
  [ "$DRY" = 1 ] && echo "+ (cd ios && pod install)" || (cd ios && pod install >/dev/null)
elif [ "$STACK" = xcodegen ]; then
  run xcodegen generate
elif [ "$STACK" = workspace ] && [ -f Podfile ]; then
  [ "$DRY" = 1 ] && echo "+ pod install" || pod install >/dev/null
fi

# ---- locate project and scheme
eval "$("$HERE/detect-stack.sh" "$REPO" | sed -E "s/^([A-Z_]+)=(.*)$/\1='\2'/" | grep -E '^(WORKSPACE|PROJECT)=')"
OVERRIDE="$(SJ get build.project)"
if [ -n "$OVERRIDE" ]; then WORKSPACE=""; PROJECT=""; case "$OVERRIDE" in *.xcworkspace) WORKSPACE="$OVERRIDE" ;; *) PROJECT="$OVERRIDE" ;; esac; fi
if [ -n "$WORKSPACE" ]; then TARGET=(-workspace "$WORKSPACE"); elif [ -n "$PROJECT" ]; then TARGET=(-project "$PROJECT"); else
  if [ "$DRY" = 1 ]; then TARGET=(-project "<project>"); else echo "No .xcworkspace or .xcodeproj found after generation." >&2; exit 1; fi
fi
SCHEME="$(SJ get build.scheme)"
if [ -z "$SCHEME" ] && [ "$DRY" = 0 ]; then
  SCHEME="$(xcodebuild "${TARGET[@]}" -list -json | python3 -c '
import json,sys
d=json.load(sys.stdin); d=d.get("workspace") or d.get("project") or {}
s=[x for x in d.get("schemes",[]) if not x.startswith("Pods-") and not x.endswith(("Tests","UITests"))]
print(s[0] if s else "")')"
fi
SCHEME="${SCHEME:-<scheme>}"
echo "Target: ${TARGET[*]}  scheme: $SCHEME"

ARCHIVE="build/$SCHEME.xcarchive"; EXPORT="build/export"
[ "$DRY" = 1 ] || rm -rf "$ARCHIVE" "$EXPORT"

run xcodebuild "${TARGET[@]}" -scheme "$SCHEME" -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" -derivedDataPath build/dd-release \
  MARKETING_VERSION="$VERSION" CURRENT_PROJECT_VERSION="$BUILD" DEVELOPMENT_TEAM="$TEAM" \
  "${AUTH[@]}" archive
gate archive "$ARCHIVE"

# ---- export options (generated, so the plugin never ships a team id)
PLIST="build/ExportOptions.plist"
DEST=export; [ "$UPLOAD" = 1 ] && [ "$METHOD" = xcodebuild ] && DEST=upload
if [ "$DRY" = 0 ]; then cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>method</key><string>app-store-connect</string>
  <key>teamID</key><string>$TEAM</string>
  <key>destination</key><string>$DEST</string>
  <key>signingStyle</key><string>automatic</string>
  <key>uploadSymbols</key><true/>
  <key>manageAppVersionAndBuildNumber</key><false/>
</dict>
</plist>
PL
else echo "+ write $PLIST (method app-store-connect, teamID from ship.json, destination $DEST)"; fi

if [ "$DEST" = upload ]; then
  # Exports and uploads in one step. Does not leave an .ipa behind.
  run xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportPath "$EXPORT" -exportOptionsPlist "$PLIST" "${AUTH[@]}"
else
  run xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportPath "$EXPORT" -exportOptionsPlist "$PLIST" "${AUTH[@]}"
  if [ "$DRY" = 0 ]; then IPA="$(ls "$EXPORT"/*.ipa | head -1)"; else IPA="$EXPORT/<app>.ipa"; fi
  gate ipa "$IPA"
  if [ "$UPLOAD" = 1 ]; then
    # altool finds the key by name in API_PRIVATE_KEYS_DIR, so link it into a temp dir.
    KD="$(mktemp -d)"; trap 'rm -rf "$KD"' EXIT
    ln -s "$ASC_KEY_PATH" "$KD/AuthKey_$ASC_KEY_ID.p8"
    echo "+ API_PRIVATE_KEYS_DIR=<tmp> xcrun altool --upload-app -f $IPA -t ios --api-key \$ASC_KEY_ID --api-issuer \$ASC_ISSUER_ID"
    [ "$DRY" = 1 ] || API_PRIVATE_KEYS_DIR="$KD" xcrun altool --upload-app -f "$IPA" -t ios --api-key "$ASC_KEY_ID" --api-issuer "$ASC_ISSUER_ID"
  fi
fi

if [ "$UPLOAD" = 1 ] && [ "$DRY" = 0 ]; then
  SJ set build.lastBuildNumber "$BUILD"; SJ set build.lastVersion "\"$VERSION\""
  echo; echo "UPLOADED version=$VERSION build=$BUILD"
  echo "Next: ship-store testflight --build $BUILD (processing takes a few minutes before the build is selectable)."
elif [ "$DRY" = 1 ]; then
  echo; echo "DRY RUN complete: nothing was built or uploaded."
else
  echo; echo "BUILT version=$VERSION build=$BUILD at $EXPORT. Not uploaded. Re-run with --upload after the user says go."
fi
