#!/usr/bin/env python3
"""Render App Store screenshots from real raw captures with headless Chrome.

  render.py --init                    write a starter plan.json from the raws found
  render.py                           render every slide, every locale, every display with raws
  render.py --display iphone          only iphone (or ipad)
  render.py --locale en-US --only 1,2 limit the run
  render.py --chrome /path/to/chrome  override Chrome detection

Layout (all under <repo>/.ship/screenshots/):
  raw/iphone/01-home.png              captures (same file name in raw/ipad/ for iPad)
  plan.json                           copy, styles, order (see references/plan.md)
  <locale>/APP_IPHONE_67/01.png ...   finals, exact size, no alpha
  <locale>/APP_IPAD_PRO_3GEN_129/01.png
  index.html                          contact sheet
  _html/                              intermediate pages (safe to delete)
Needs Python 3.8+ and Chrome/Chromium. Pillow is optional (see pngtool.py).
"""
import argparse, glob, html, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(os.path.dirname(HERE), "templates")
sys.path.insert(0, HERE)
import pngtool

DISPLAYS = {
    "iphone": dict(type="APP_IPHONE_67", W=1320, H=2868, dw=1060, hdw=960, bezel=24, sr=125, hsize=124, sub=50, maxHeader=860),
    "ipad": dict(type="APP_IPAD_PRO_3GEN_129", W=2064, H=2752, dw=1020, hdw=800, bezel=28, sr=46, hsize=96, sub=50, maxHeader=620),
}
DEFAULT_PALETTE = dict(bg="#0f172a", surface="#1e293b", text="#ffffff", primary="#4f46e5", accent="#f59e0b")
FONT_STACK = "-apple-system, 'SF Pro Display', 'Helvetica Neue', Helvetica, Arial, sans-serif"


# ---------------------------------------------------------------- colour helpers
def hex_rgb(h):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in c)


def lum(h):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = hex_rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a, b, t):
    ra, rb = hex_rgb(a), hex_rgb(b)
    return rgb_hex([ra[i] * (1 - t) + rb[i] * t for i in range(3)])


def valid_hex(h):
    return isinstance(h, str) and re.fullmatch(r"#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", h.strip() or "x") is not None


def norm(h):
    h = h.strip()
    return h if h.startswith("#") else "#" + h


def pick_text(bg, preferred):
    for c in (preferred, "#ffffff", "#111111"):
        if c and valid_hex(c) and contrast(norm(c), bg) >= 4.5:
            return norm(c)
    return "#ffffff" if contrast("#ffffff", bg) > contrast("#111111", bg) else "#111111"


# ---------------------------------------------------------------- chrome
def find_chrome(override=None):
    cands = [override, os.environ.get("CHROME")]
    cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
              "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
    for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "microsoft-edge"):
        cands.append(shutil.which(n))
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    sys.exit("Chrome or Chromium not found. Install it or pass --chrome /path/to/binary (or set CHROME).")


def shoot(chrome, page, out, W, H):
    prof = tempfile.mkdtemp(prefix="shipshots-")
    try:
        cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
               "--no-first-run", "--no-default-browser-check", "--allow-file-access-from-files",
               f"--user-data-dir={prof}", "--virtual-time-budget=8000", f"--window-size={W},{H}",
               f"--screenshot={out}", "file://" + page]
        subprocess.run(cmd, capture_output=True, timeout=90)
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    return os.path.isfile(out)


# ---------------------------------------------------------------- plan
def load_json(p):
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def font_link(fonts):
    fams = []
    for f in fonts:
        if f and f not in fams and f.lower() not in ("system", "system-ui", "sf pro", "-apple-system"):
            fams.append(f)
    if not fams:
        return ""
    q = "&".join("family=" + f.replace(" ", "+") + ":wght@400;500;700;800" for f in fams)
    return f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{q}&display=swap">'


def text_html(s):
    s = html.escape(s or "", quote=False)
    s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
    return s.replace("\n", "<br>")


def localized(v, loc, primary):
    if isinstance(v, dict):
        return v.get(loc) or v.get(loc.split("-")[0]) or v.get(primary) or next(iter(v.values()), "")
    return v or ""


def fill(tpl, vals):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(vals.get(m.group(1), "")), tpl)


def read(p):
    with open(p) as f:
        return f.read()


def headline_size(text, base):
    n = max((len(x) for x in re.sub(r"[*]", "", text).split("\n")), default=0)
    total = len(re.sub(r"[*\n]", "", text))
    s = base
    if total > 22 or n > 13:
        s = base * 0.9
    if total > 32:
        s = base * 0.78
    return round(s)


def init_plan(shots, ship):
    raws = {}
    for kind in ("iphone", "ipad"):
        for p in sorted(glob.glob(os.path.join(shots, "raw", kind, "*.png"))):
            raws.setdefault(os.path.splitext(os.path.basename(p))[0], True)
    plan = {
        "style": "framed", "bgMode": "cycle", "frame": "#101114",
        "slides": [{"raw": n, "headline": "", "subline": ""} for n in raws],
    }
    out = os.path.join(shots, "plan.json")
    if os.path.exists(out):
        sys.exit(f"{out} exists; edit it instead.")
    os.makedirs(shots, exist_ok=True)
    with open(out, "w") as f:
        json.dump(plan, f, indent=2)
        f.write("\n")
    print(f"wrote {out} with {len(raws)} slides; fill in headlines")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--ship")
    ap.add_argument("--plan")
    ap.add_argument("--display", default="all", choices=["all", "iphone", "ipad"])
    ap.add_argument("--locale")
    ap.add_argument("--only", help="comma separated slide numbers, 1-based")
    ap.add_argument("--chrome")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--keep-html", action="store_true")
    a = ap.parse_args()

    repo = os.path.abspath(a.repo)
    shots = os.path.join(repo, ".ship", "screenshots")
    ship = load_json(a.ship or os.path.join(repo, ".ship", "ship.json"))
    if a.init:
        return init_plan(shots, ship)
    plan = load_json(a.plan or os.path.join(shots, "plan.json"))
    if not plan.get("slides"):
        sys.exit("No slides in plan.json. Run with --init first, then write the headlines.")

    vibe, app = ship.get("vibe", {}), ship.get("app", {})
    defaults = ship.get("screenshots", {})
    pal = dict(DEFAULT_PALETTE)
    for src in (vibe.get("palette", {}), plan.get("palette", {})):
        pal.update({k: v for k, v in src.items() if valid_hex(v)})
    fonts = dict(vibe.get("fonts", {}))
    fonts.update(plan.get("fonts", {}))
    fd = fonts.get("display") or fonts.get("body") or ""
    fb = fonts.get("body") or fd or ""
    fd_css = f"'{fd}', {FONT_STACK}" if fd else FONT_STACK
    fb_css = f"'{fb}', {FONT_STACK}" if fb else FONT_STACK
    flink = font_link([fd, fb])
    primary_loc = app.get("primaryLocale") or "en-US"
    locales = plan.get("locales") or (ship.get("features", {}) or {}).get("localizations") or [primary_loc]
    if a.locale:
        locales = [a.locale]
    default_style = plan.get("style") or defaults.get("style") or "framed"
    bg_mode = plan.get("bgMode") or defaults.get("bgMode") or "cycle"
    frame = norm(plan.get("frame") or defaults.get("frame") or "#101114")
    cyc = []
    for k in ("primary", "accent", "bg", "surface"):
        c = norm(pal[k])
        if c not in cyc:
            cyc.append(c)
    only = {int(x) for x in a.only.split(",")} if a.only else None
    kinds = ["iphone", "ipad"] if a.display == "all" else [a.display]

    chrome = find_chrome(a.chrome)
    base_css = read(os.path.join(TPL, "_base.css"))
    autofit_tpl = read(os.path.join(TPL, "_autofit.html"))
    work = os.path.join(shots, "_html")
    os.makedirs(work, exist_ok=True)
    results, problems = [], []

    for kind in kinds:
        d = DISPLAYS[kind]
        for loc in locales:
            outdir = os.path.join(shots, loc, d["type"])
            slides_done = 0
            for i, s in enumerate(plan["slides"], 1):
                if only and i not in only:
                    continue
                raw = os.path.join(shots, "raw", kind, s["raw"] + ("" if s["raw"].endswith(".png") else ".png"))
                if not os.path.isfile(raw):
                    if kind == "iphone" or os.path.isdir(os.path.join(shots, "raw", kind)):
                        problems.append(f"slide {i}: missing raw {os.path.relpath(raw, shots)}")
                    continue
                style = s.get("style") or default_style
                raw2 = ""
                if style == "hero":
                    r2 = s.get("raw2", "")
                    raw2 = os.path.join(shots, "raw", kind, r2 + ("" if r2.endswith(".png") else ".png")) if r2 else ""
                    if not raw2 or not os.path.isfile(raw2):
                        problems.append(f"slide {i}: hero needs raw2 in raw/{kind}; used framed instead")
                        style, raw2 = "framed", ""
                bgspec = s.get("bg") or ""
                if bgspec:
                    parts = [norm(x) for x in bgspec.split(",") if valid_hex(x)]
                    bg1 = parts[0] if parts else cyc[0]
                    bg2 = parts[1] if len(parts) > 1 else None
                else:
                    bg1 = cyc[(i - 1) % len(cyc)] if bg_mode == "cycle" else cyc[0]
                    bg2 = None
                if not bg2:
                    bg2 = mix(bg1, "#000000", 0.30 if lum(bg1) < 0.5 else 0.14)
                text = pick_text(bg1, s.get("textColor") or pal["text"])
                sub = mix(text, bg1, 0.22)
                em = norm(pal["accent"])
                if contrast(em, bg1) < 3 or contrast(em, bg2) < 3:
                    em = text
                head = localized(s.get("headline"), loc, primary_loc)
                subl = localized(s.get("subline"), loc, primary_loc)
                if not head:
                    problems.append(f"slide {i}: empty headline for {loc}")
                u = d["W"] / 1320
                hs = headline_size(head, d["hsize"])
                pos = s.get("captionPos") or plan.get("captionPos") or "bottom"
                vals = dict(
                    u=f"{u:.5f}", W=d["W"], H=d["H"], bg1=bg1, bg2=bg2, text=text, sub=sub, em=em,
                    frame=frame, frameEdge=mix(frame, "#ffffff", 0.18), fd=fd_css, fb=fb_css,
                    hsize=hs, bezel=d["bezel"], sr=d["sr"], dw=d["dw"], hdw=d["hdw"],
                    fontLink=flink, headline=text_html(head),
                    subline=f'<p class="sub">{text_html(subl)}</p>' if subl else "",
                    img1="file://" + raw, img2="file://" + raw2 if raw2 else "", pos=pos,
                    shotPos=s.get("shotPosition") or "50% 0%",
                    maxHeader=int(d["maxHeader"] * u),
                )
                vals["base_css"] = fill(base_css, vals)
                vals["autofit"] = fill(autofit_tpl, vals)
                page = fill(read(os.path.join(TPL, style + ".html")), vals)
                hp = os.path.join(work, f"{loc}-{d['type']}-{i:02d}.html")
                with open(hp, "w") as f:
                    f.write(page)
                os.makedirs(outdir, exist_ok=True)
                out = os.path.join(outdir, f"{i:02d}.png")
                if not shoot(chrome, hp, out, d["W"], d["H"]):
                    problems.append(f"slide {i} {loc} {kind}: Chrome produced no file")
                    continue
                try:
                    pngtool.flatten(out)
                except RuntimeError as e:
                    problems.append(str(e))
                inf = pngtool.info(out)
                ok = inf and (inf[0], inf[1]) == (d["W"], d["H"]) and not inf[2]
                if not ok:
                    problems.append(f"{os.path.relpath(out, shots)}: got {inf}, need {d['W']}x{d['H']} without alpha")
                results.append(dict(loc=loc, kind=kind, type=d["type"], n=i, path=out, ok=bool(ok),
                                    headline=re.sub(r"\*", "", head), size=f"{inf[0]}x{inf[1]}" if inf else "?",
                                    alpha=bool(inf and inf[2]), style=style))
                slides_done += 1
            if slides_done:
                print(f"{loc} {d['type']}: {slides_done} slides")

    write_index(shots, results, plan, app)
    bad = [r for r in results if not r["ok"]]
    print(f"\n{len(results)} rendered, {len(results) - len(bad)} verified (exact size, no alpha)")
    for p in problems:
        print("  note:", p)
    n = len(plan["slides"])
    if n < 5 or n > 10:
        print(f"  note: {n} slides; the App Store allows 1 to 10, 5 to 8 works best")
    if not a.keep_html:
        shutil.rmtree(work, ignore_errors=True)
    print(f"contact sheet: {os.path.join(shots, 'index.html')}")
    sys.exit(1 if bad or not results else 0)


def write_index(shots, results, plan, app):
    groups = {}
    for r in results:
        groups.setdefault((r["loc"], r["type"]), []).append(r)
    esc = html.escape
    parts = []
    for (loc, typ), rs in groups.items():
        cells = "".join(
            f'<figure class="{"ok" if r["ok"] else "bad"}"><a href="{esc(os.path.relpath(r["path"], shots))}">'
            f'<img loading="lazy" src="{esc(os.path.relpath(r["path"], shots))}"></a>'
            f'<figcaption><b>{r["n"]:02d}</b> {esc(r["headline"])}<span>{r["size"]} {"no alpha" if not r["alpha"] else "ALPHA"} {esc(r["style"])}</span></figcaption></figure>'
            for r in sorted(rs, key=lambda x: x["n"]))
        parts.append(f"<section><h2>{esc(loc)} <small>{esc(typ)}</small></h2><div class=row>{cells}</div></section>")
    name = esc(app.get("name") or "App")
    page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} screenshots</title><style>
:root{{--bg:#f6f5f2;--fg:#17171a;--mut:#6b6b73;--card:#fff}}
@media (prefers-color-scheme:dark){{:root{{--bg:#131316;--fg:#eee;--mut:#9a9aa3;--card:#1d1d22}}}}
body{{margin:0;padding:24px 16px 60px;background:var(--bg);color:var(--fg);font:15px/1.4 -apple-system,system-ui,sans-serif}}
h1{{font-size:22px;margin:0 0 4px}}p.m{{color:var(--mut);margin:0 0 24px}}
h2{{font-size:17px;margin:28px 0 12px}}h2 small{{color:var(--mut);font-weight:400;margin-left:8px}}
.row{{display:flex;gap:14px;overflow-x:auto;padding-bottom:12px}}
figure{{margin:0;flex:none;width:230px;background:var(--card);border-radius:12px;padding:8px}}
figure img{{width:100%;display:block;border-radius:6px}}
figcaption{{margin-top:8px;font-size:13px}}figcaption span{{display:block;color:var(--mut);font-size:11px;margin-top:2px}}
figure.bad{{outline:2px solid #d33}}
</style></head><body><h1>{name} App Store screenshots</h1>
<p class=m>Click an image for full size. The first two carry the store page. Red outline means the size or alpha check failed.</p>
{''.join(parts)}</body></html>"""
    os.makedirs(shots, exist_ok=True)
    with open(os.path.join(shots, "index.html"), "w") as f:
        f.write(page)


if __name__ == "__main__":
    main()
