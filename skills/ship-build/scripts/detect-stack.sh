#!/usr/bin/env bash
# Print what kind of iOS project lives in the repo, as KEY=value lines.
#   detect-stack.sh [repo-dir]
# STACK is one of: expo, react-native, flutter, xcodegen, workspace, xcodeproj, none.
# Order matters: Expo and Flutter win over a generated ios/ folder.
set -euo pipefail
cd "${1:-.}"

emit() { printf '%s=%s\n' "$1" "$2"; }
find_first() { # find_first <maxdepth> <pattern>; skips generated and vendored dirs
  find . -maxdepth "$1" -name "$2" \
    -not -path '*/node_modules/*' -not -path '*/Pods/*' -not -path '*/build/*' \
    -not -path '*/.build/*' -not -path '*/DerivedData/*' -not -path '*/.git/*' \
    -not -path '*/*.xcodeproj/project.xcworkspace' 2>/dev/null | sort | head -1
}

STACK=none; NOTE=""
if [ -f pubspec.yaml ] && grep -q '^flutter:' pubspec.yaml; then
  STACK=flutter; NOTE="Flutter is manual: run 'flutter build ipa --release', then upload the .ipa (see SKILL.md)."
elif [ -f package.json ] && grep -q '"expo"' package.json; then
  STACK=expo; NOTE="Continuous Native Generation: 'npx expo prebuild' creates ios/ before xcodebuild."
elif [ -f package.json ] && grep -q '"react-native"' package.json; then
  STACK=react-native; NOTE="Bare React Native: ios/ is committed, run pod install before xcodebuild."
elif [ -f project.yml ] && grep -q '^targets:' project.yml; then
  STACK=xcodegen; NOTE="XcodeGen: 'xcodegen generate' creates the .xcodeproj from project.yml."
elif [ -n "$(find_first 3 '*.xcworkspace')" ]; then
  STACK=workspace; NOTE="Workspace (CocoaPods or SwiftPM multi-project)."
elif [ -n "$(find_first 3 '*.xcodeproj')" ]; then
  STACK=xcodeproj; NOTE="Plain Xcode project."
fi
emit STACK "$STACK"
emit NOTE "$NOTE"

# Native project location (for expo this exists only after prebuild)
WS=""; PROJ=""
if [ "$STACK" = expo ] || [ "$STACK" = react-native ]; then
  WS="$(find ios -maxdepth 1 -name '*.xcworkspace' 2>/dev/null | head -1 || true)"
  PROJ="$(find ios -maxdepth 1 -name '*.xcodeproj' 2>/dev/null | head -1 || true)"
else
  WS="$(find_first 3 '*.xcworkspace' || true)"
  PROJ="$(find_first 3 '*.xcodeproj' || true)"
fi
emit WORKSPACE "${WS#./}"
emit PROJECT "${PROJ#./}"

# Expo config file kind
CFG=""
for f in app.config.ts app.config.js app.json; do [ -f "$f" ] && { CFG="$f"; break; }; done
[ "$STACK" = expo ] && emit EXPO_CONFIG "$CFG"
[ -f Podfile ] || [ -f ios/Podfile ] && emit COCOAPODS yes || emit COCOAPODS no
[ -f app.json ] && grep -q '"ios"' app.json && emit EXPO_IOS_STATIC yes || true
if [ "$STACK" = expo ] || [ "$STACK" = react-native ]; then
  if git check-ignore -q ios 2>/dev/null; then emit NATIVE_DIR_IGNORED yes; else emit NATIVE_DIR_IGNORED no; fi
fi
