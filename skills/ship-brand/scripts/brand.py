#!/usr/bin/env python3
"""
Brand outputs from one icon and the vibe in ship.json.

  brand.py check ICON.png                 is it a valid App Store icon?
  brand.py icon ICON.png [--dark D.png] [--tinted T.png] [--xcassets PATH] [--expo]
                                          write the iOS icon (fixes alpha and size)
  brand.py web ICON.png --out DIR         favicon.ico, 16/32/180/192/512 PNGs, site.webmanifest
  brand.py tokens --out DIR               tokens.css, Theme.swift, theme.ts from ship.json vibe
  brand.py og --icon ICON.png --out og.png [--title T] [--tagline T]
                                          1200x630 social preview, rendered with headless Chrome

Needs Pillow (pip install Pillow). `og` also needs Chrome or Chromium.
"""
import argparse
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    from PIL import Image
except ImportError:
    sys.exit("brand.py needs Pillow: pip3 install Pillow")


def load_ship(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def hex_rgb(h, fallback=(255, 255, 255)):
    h = (h or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return fallback


# ---------------------------------------------------------------------------
# App icon
# ---------------------------------------------------------------------------

def check_icon(path):
    """Problems that get an icon rejected or looking wrong on the home screen."""
    im = Image.open(path)
    problems = []
    if im.size != (1024, 1024):
        problems.append(f"size is {im.size[0]}x{im.size[1]}, needs 1024x1024")
    if im.mode in ("RGBA", "LA", "P"):
        alpha = im.convert("RGBA").getchannel("A")
        if alpha.getextrema()[0] < 255:
            problems.append("has transparent pixels (App Store icons must be fully opaque)")
        else:
            problems.append("has an alpha channel (all opaque, but strip it to be safe)")
    rgb = im.convert("RGB")
    w, h = rgb.size
    corners = [rgb.getpixel(p) for p in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]]
    centre = rgb.getpixel((w // 2, h // 2))
    if all(c == (255, 255, 255) for c in corners) and centre != (255, 255, 255):
        problems.append("white corners: looks like rounded corners were drawn in. "
                        "iOS rounds the icon itself; fill the whole square")
    return problems


def opaque_1024(src, bg):
    im = Image.open(src).convert("RGBA")
    if im.size != (1024, 1024):
        im = im.resize((1024, 1024), Image.LANCZOS)
    base = Image.new("RGBA", im.size, bg + (255,))
    base.alpha_composite(im)
    return base.convert("RGB")


def find_xcassets(repo):
    hits = []
    for root, dirs, _ in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "Pods", "build", ".git", "DerivedData")]
        for d in dirs:
            if d == "AppIcon.appiconset":
                hits.append(os.path.join(root, d))
    return hits


def cmd_icon(a):
    ship = load_ship(a.ship)
    bg = hex_rgb(ship.get("vibe", {}).get("palette", {}).get("bg"), (255, 255, 255))
    for p in check_icon(a.icon):
        print(f"fixing: {p}")
    light = opaque_1024(a.icon, bg)
    variants = [("AppIcon.png", light, None)]
    if a.dark:
        # Dark variant may keep transparency: iOS draws it on its own dark backdrop.
        variants.append(("AppIcon-dark.png", Image.open(a.dark).convert("RGBA").resize((1024, 1024)), "dark"))
    if a.tinted:
        variants.append(("AppIcon-tinted.png", Image.open(a.tinted).convert("L").resize((1024, 1024)), "tinted"))

    # Expo regenerates ios/ on prebuild, so only write an asset catalog there when asked.
    targets = [a.xcassets] if a.xcassets else ([] if a.expo else find_xcassets(a.repo))
    if not a.expo and not targets:
        print("No AppIcon.appiconset found. Pass --xcassets PATH or --expo.")
    for t in targets:
        os.makedirs(t, exist_ok=True)
        images = []
        for name, im, appearance in variants:
            im.save(os.path.join(t, name), format="PNG")
            entry = {"filename": name, "idiom": "universal", "platform": "ios", "size": "1024x1024"}
            if appearance:
                entry["appearances"] = [{"appearance": "luminosity", "value": appearance}]
            images.append(entry)
        with open(os.path.join(t, "Contents.json"), "w") as f:
            json.dump({"images": images, "info": {"author": "xcode", "version": 1}}, f, indent=2)
        print(f"wrote {t} ({len(images)} variant(s))")
    if a.expo:
        out = os.path.join(a.repo, "assets", "images")
        os.makedirs(out, exist_ok=True)
        for name, im, appearance in variants:
            fname = {None: "icon.png", "dark": "icon-dark.png", "tinted": "icon-tinted.png"}[appearance]
            im.save(os.path.join(out, fname), format="PNG")
            print(f"wrote {os.path.join(out, fname)}")
        print('Set app.json "icon": "./assets/images/icon.png" (and ios.icon {light,dark,tinted} if you made variants).')


def cmd_check(a):
    problems = check_icon(a.icon)
    print("ok: valid 1024x1024 opaque icon" if not problems else "\n".join(f"- {p}" for p in problems))
    sys.exit(1 if problems else 0)


# ---------------------------------------------------------------------------
# Web icons
# ---------------------------------------------------------------------------

def rounded(im, radius_frac=0.2235):
    """Web icons look better with the iOS-like rounded square baked in."""
    from PIL import ImageDraw
    size = im.size[0]
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * radius_frac), fill=255)
    out = im.convert("RGBA")
    out.putalpha(mask)
    return out


def cmd_web(a):
    ship = load_ship(a.ship)
    bg = hex_rgb(ship.get("vibe", {}).get("palette", {}).get("bg"), (255, 255, 255))
    src = opaque_1024(a.icon, bg)
    os.makedirs(a.out, exist_ok=True)
    src.resize((180, 180), Image.LANCZOS).save(os.path.join(a.out, "apple-touch-icon.png"))
    for s in (16, 32, 192, 512):
        rounded(src).resize((s, s), Image.LANCZOS).save(os.path.join(a.out, f"icon-{s}.png"))
    rounded(src).save(os.path.join(a.out, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
    name = ship.get("app", {}).get("name") or "App"
    theme = ship.get("vibe", {}).get("palette", {}).get("primary") or "#000000"
    manifest = {
        "name": name, "short_name": name[:12],
        "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}],
        "theme_color": theme, "background_color": "#%02x%02x%02x" % bg, "display": "standalone",
    }
    with open(os.path.join(a.out, "site.webmanifest"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"wrote favicon.ico, apple-touch-icon.png, icon-16/32/192/512.png, site.webmanifest to {a.out}")


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def cmd_tokens(a):
    vibe = load_ship(a.ship).get("vibe", {})
    pal = {k: v for k, v in vibe.get("palette", {}).items() if v}
    fonts = vibe.get("fonts", {})
    if not pal:
        sys.exit("ship.json vibe.palette is empty. Pick a vibe first (ship-images explore).")
    os.makedirs(a.out, exist_ok=True)
    css = [":root {"] + [f"  --color-{k}: {v};" for k, v in pal.items()]
    for k, v in fonts.items():
        if v:
            css.append(f"  --font-{k}: \"{v}\", system-ui, sans-serif;")
    css.append("}")
    with open(os.path.join(a.out, "tokens.css"), "w") as f:
        f.write("\n".join(css) + "\n")

    def swift_color(h):
        r, g, b = hex_rgb(h, (0, 0, 0))
        return f"Color(red: {r / 255:.3f}, green: {g / 255:.3f}, blue: {b / 255:.3f})"
    swift = ["import SwiftUI", "", "/// Brand colours from .ship/ship.json (vibe.palette).", "enum Brand {"]
    swift += [f"    static let {k} = {swift_color(v)}  // {v}" for k, v in pal.items()]
    swift.append("}")
    with open(os.path.join(a.out, "Theme.swift"), "w") as f:
        f.write("\n".join(swift) + "\n")

    ts = ["// Brand tokens from .ship/ship.json (vibe).", "export const colors = {"]
    ts += [f"  {k}: \"{v}\"," for k, v in pal.items()]
    ts += ["} as const;", "", "export const fonts = {"]
    ts += [f"  {k}: \"{v}\"," for k, v in fonts.items() if v]
    ts.append("} as const;")
    with open(os.path.join(a.out, "theme.ts"), "w") as f:
        f.write("\n".join(ts) + "\n")
    print(f"wrote tokens.css, Theme.swift, theme.ts to {a.out}")


# ---------------------------------------------------------------------------
# Social preview (OG) image
# ---------------------------------------------------------------------------

def chrome_path():
    for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium"):
        if os.path.exists(p):
            return p
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def cmd_og(a):
    ship = load_ship(a.ship)
    app, vibe = ship.get("app", {}), ship.get("vibe", {})
    pal, fonts = vibe.get("palette", {}), vibe.get("fonts", {})
    title = a.title or app.get("name") or "App"
    tagline = a.tagline or app.get("tagline") or app.get("oneLiner") or ""
    display = fonts.get("display") or "system-ui"
    body = fonts.get("body") or display
    chrome = chrome_path()
    if not chrome:
        sys.exit("No Chrome or Chromium found for rendering.")
    tmp = tempfile.mkdtemp()
    icon = os.path.join(tmp, "icon.png")
    rounded(opaque_1024(a.icon, hex_rgb(pal.get("bg")))).save(icon)
    families = "&".join("family=" + f.replace(" ", "+") + ":wght@400;700"
                        for f in dict.fromkeys([display, body]) if f != "system-ui")
    font_link = f'<link href="https://fonts.googleapis.com/css2?{families}&display=block" rel="stylesheet">' if families else ""
    page = f"""<!doctype html><html><head><meta charset="utf-8">{font_link}<style>
html,body{{margin:0;width:1200px;height:630px;overflow:hidden}}
body{{background:{pal.get('bg') or '#fff'};color:{pal.get('text') or '#111'};display:flex;align-items:center;
gap:64px;padding:0 96px;box-sizing:border-box;font-family:"{body}",system-ui,sans-serif}}
img{{width:280px;height:280px;flex:none;filter:drop-shadow(0 18px 40px rgba(0,0,0,.18))}}
h1{{font-family:"{display}",system-ui,sans-serif;font-size:84px;line-height:1;margin:0 0 20px;letter-spacing:-.02em}}
p{{font-size:38px;line-height:1.25;margin:0;opacity:.8;max-width:620px}}
.bar{{position:absolute;left:0;right:0;bottom:0;height:18px;background:{pal.get('primary') or '#111'}}}
</style></head><body><img src="icon.png"><div><h1>{html.escape(title)}</h1><p>{html.escape(tagline)}</p></div><div class="bar"></div></body></html>"""
    with open(os.path.join(tmp, "og.html"), "w") as f:
        f.write(page)
    out = os.path.abspath(a.out)
    subprocess.run([chrome, "--headless=new", "--hide-scrollbars", "--disable-gpu", f"--screenshot={out}",
                    "--window-size=1200,630", "--virtual-time-budget=5000", f"file://{tmp}/og.html"],
                   capture_output=True, check=False)
    if not os.path.exists(out):
        sys.exit("Chrome did not write the image.")
    Image.open(out).convert("RGB").save(out)
    print(f"wrote {out} (1200x630). Look at it before using it.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ship", default=".ship/ship.json")
    p.add_argument("--repo", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("icon")
    i = sub.add_parser("icon"); i.add_argument("icon"); i.add_argument("--dark"); i.add_argument("--tinted")
    i.add_argument("--xcassets"); i.add_argument("--expo", action="store_true")
    w = sub.add_parser("web"); w.add_argument("icon"); w.add_argument("--out", required=True)
    t = sub.add_parser("tokens"); t.add_argument("--out", default=".ship/brand")
    o = sub.add_parser("og"); o.add_argument("--icon", required=True); o.add_argument("--out", default=".ship/brand/og.png")
    o.add_argument("--title"); o.add_argument("--tagline")
    a = p.parse_args()
    {"check": cmd_check, "icon": cmd_icon, "web": cmd_web, "tokens": cmd_tokens, "og": cmd_og}[a.cmd](a)


if __name__ == "__main__":
    main()
