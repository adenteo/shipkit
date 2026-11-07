#!/usr/bin/env python3
"""
Localize an app: the App Store listing, the screenshot headlines and the app's own
strings, into many languages at once, checked by machine rather than by eye.

  localize.py locales [--preset top|europe|asia|all] [--set]
      Lists App Store locale codes. --set saves the preset to features.localizations.
  localize.py listing   [--locales de-DE,ja] [--engine E] [--force]
  localize.py headlines [--locales ...] [--engine E] [--force]
  localize.py strings   [--locales ...] [--engine E] [--catalog PATH] [--batch 40]
      Translate. Only what is missing is sent, so reruns are cheap and human edits
      are never overwritten (--force redoes the listing or headlines).
  localize.py apply listing|headlines|strings
      Merge the answers Claude subagents wrote for the "claude" engine.
  localize.py check [--locales ...] [--catalog PATH]
      Detectors: limits, placeholders, protected words, URLs, dashes, wrong script,
      untranslated text, keyword waste.

Engines: claude (default; writes job files for Claude subagents, no key needed),
openai (secrets.openaiEnv), gemini (secrets.geminiEnv), codex (Codex CLI on a
ChatGPT plan). Settings come from ship.json "localize" over
~/.config/shipkit/defaults.json "localize".
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

# --------------------------------------------------------------------------- locales

# Every locale App Store Connect accepts for listings, with the code the app
# bundle uses for the same language (String Catalog / .lproj / i18n file).
LOCALES = {
    "ar-SA": ("Arabic", "ar"), "bn-BD": ("Bengali", "bn"), "ca": ("Catalan", "ca"),
    "cs": ("Czech", "cs"), "da": ("Danish", "da"), "de-DE": ("German", "de"), "el": ("Greek", "el"),
    "en-AU": ("English (Australia)", "en-AU"), "en-CA": ("English (Canada)", "en-CA"),
    "en-GB": ("English (UK)", "en-GB"), "en-US": ("English (US)", "en"),
    "es-ES": ("Spanish (Spain)", "es"), "es-MX": ("Spanish (Mexico)", "es-MX"), "fi": ("Finnish", "fi"),
    "fr-CA": ("French (Canada)", "fr-CA"), "fr-FR": ("French", "fr"), "gu-IN": ("Gujarati", "gu"),
    "he": ("Hebrew", "he"), "hi": ("Hindi", "hi"), "hr": ("Croatian", "hr"), "hu": ("Hungarian", "hu"),
    "id": ("Indonesian", "id"), "it": ("Italian", "it"), "ja": ("Japanese", "ja"), "kn-IN": ("Kannada", "kn"),
    "ko": ("Korean", "ko"), "ml-IN": ("Malayalam", "ml"), "mr-IN": ("Marathi", "mr"), "ms": ("Malay", "ms"),
    "nl-NL": ("Dutch", "nl"), "no": ("Norwegian", "nb"), "or-IN": ("Odia", "or"), "pa-IN": ("Punjabi", "pa"),
    "pl": ("Polish", "pl"), "pt-BR": ("Portuguese (Brazil)", "pt-BR"), "pt-PT": ("Portuguese (Portugal)", "pt-PT"),
    "ro": ("Romanian", "ro"), "ru": ("Russian", "ru"), "sk": ("Slovak", "sk"), "sl-SI": ("Slovenian", "sl"),
    "sv": ("Swedish", "sv"), "ta-IN": ("Tamil", "ta"), "te-IN": ("Telugu", "te"), "th": ("Thai", "th"),
    "tr": ("Turkish", "tr"), "uk": ("Ukrainian", "uk"), "ur-PK": ("Urdu", "ur"), "vi": ("Vietnamese", "vi"),
    "zh-Hans": ("Chinese (Simplified)", "zh-Hans"), "zh-Hant": ("Chinese (Traditional)", "zh-Hant"),
}
# Plausible codes App Store Connect rejects for listings.
REJECTED = {"fil", "az", "bg", "et", "lt", "lv", "sq", "sr", "mk", "kk", "mn", "hy", "ka", "is", "sl"}
PRESETS = {
    "top": ["de-DE", "fr-FR", "es-ES", "es-MX", "pt-BR", "it", "ja", "ko", "zh-Hans", "nl-NL"],
    "europe": ["de-DE", "fr-FR", "es-ES", "it", "nl-NL", "pt-PT", "pl", "sv", "da", "no", "fi", "en-GB"],
    "asia": ["ja", "ko", "zh-Hans", "zh-Hant", "id", "th", "vi", "ms", "hi"],
    "all": sorted(LOCALES),
}
# Storefront a locale's keywords should be researched in (listing.py --country).
COUNTRY = {"de-DE": "de", "fr-FR": "fr", "fr-CA": "ca", "es-ES": "es", "es-MX": "mx", "pt-BR": "br",
           "pt-PT": "pt", "it": "it", "ja": "jp", "ko": "kr", "zh-Hans": "cn", "zh-Hant": "tw", "nl-NL": "nl",
           "en-GB": "gb", "en-AU": "au", "en-CA": "ca", "sv": "se", "da": "dk", "no": "no", "fi": "fi",
           "pl": "pl", "tr": "tr", "ru": "ru", "id": "id", "th": "th", "vi": "vn", "ms": "my", "hi": "in",
           "ar-SA": "sa", "he": "il"}
# Unicode ranges a translation in this language must mostly be written in.
SCRIPTS = {
    "ja": r"[\u3040-\u30ff\u4e00-\u9fff]", "zh-Hans": r"[\u4e00-\u9fff]", "zh-Hant": r"[\u4e00-\u9fff]",
    "ko": r"[\uac00-\ud7af]", "ar-SA": r"[\u0600-\u06ff]", "ur-PK": r"[\u0600-\u06ff]", "he": r"[\u0590-\u05ff]",
    "ru": r"[\u0400-\u04ff]", "uk": r"[\u0400-\u04ff]", "el": r"[\u0370-\u03ff]", "th": r"[\u0e00-\u0e7f]",
    "hi": r"[\u0900-\u097f]", "mr-IN": r"[\u0900-\u097f]", "bn-BD": r"[\u0980-\u09ff]",
    "gu-IN": r"[\u0a80-\u0aff]", "pa-IN": r"[\u0a00-\u0a7f]", "ta-IN": r"[\u0b80-\u0bff]",
    "te-IN": r"[\u0c00-\u0c7f]", "kn-IN": r"[\u0c80-\u0cff]", "ml-IN": r"[\u0d00-\u0d7f]", "or-IN": r"[\u0b00-\u0b7f]",
}
# Apple product names stay as written in every language. Feature names such as Sign in
# with Apple, Home Screen and Lock Screen are NOT here: Apple translates those itself
# ("Mit Apple anmelden", "Sperrbildschirm"), and a translation should use Apple's term.
APPLE_NAMES = ["Apple", "iPhone", "iPad", "Apple Watch", "Mac", "iOS", "iPadOS", "App Store", "Siri", "iCloud",
               "Game Center", "Face ID", "Touch ID"]

LISTING_LIMITS = {"name": 30, "subtitle": 30, "keywords": 100, "promotionalText": 170,
                  "description": 4000, "whatsNew": 4000}
PLACEHOLDER = re.compile(r"%(?:\d+\$)?[-+0#]*\d*(?:\.\d+)?(?:ll|l|h)?[@dDuUxXoOfFeEgGcCsSaAp]|%%|\{\{\s*[\w.]+\s*\}\}|\{[\w.]+\}")
URLISH = re.compile(r"https?://\S+|[\w.+-]+@[\w-]+\.[\w.]+")
DASHES = re.compile(r"[\u2013\u2014]")


def die(msg):
    sys.exit(f"error: {msg}")


def load_json(path, default=None):
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return {} if default is None else default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def read_env_value(spec, default_var):
    """One variable from an env file. spec is "path" or "path:VARIABLE"."""
    path, _, var = (spec or "").partition(":")
    path = os.path.expanduser(path)
    if not path or not os.path.exists(path):
        return ""
    with open(path) as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    for ln in lines:
        k, sep, v = ln.partition("=")
        if sep and k.strip().removeprefix("export ").strip() == (var or default_var):
            return v.strip().strip('"').strip("'")
    if len(lines) == 1 and "=" not in lines[0]:
        return lines[0]
    return ""


class Ctx:
    def __init__(self, a):
        self.a = a
        self.ship_path = a.ship
        self.ship = load_json(a.ship)
        if not self.ship:
            die(f"{a.ship} not found. Run the ship intake first, or pass --ship.")
        self.shipdir = os.path.dirname(os.path.abspath(a.ship))
        self.root = os.path.dirname(self.shipdir)
        d = load_json("~/.config/shipkit/defaults.json")
        clean = lambda o: {k: v for k, v in (o or {}).items() if v not in ("", None, [])}
        self.cfg = {**clean(d.get("localize")), **clean(self.ship.get("localize"))}
        self.secrets = {**clean(d.get("secrets")), **clean(self.ship.get("secrets"))}
        self.images = {**clean(d.get("images")), **clean(self.ship.get("images"))}
        app = self.ship.get("app", {})
        self.name = app.get("name", "")
        self.primary = app.get("primaryLocale", "en-US")

    def locales(self):
        if getattr(self.a, "locales", None):
            locs = [l.strip() for l in self.a.locales.split(",") if l.strip()]
        else:
            locs = self.ship.get("features", {}).get("localizations") or self.cfg.get("locales") or []
        locs = [l for l in locs if l != self.primary]
        bad = [l for l in locs if l not in LOCALES]
        if bad:
            hint = " (App Store Connect rejects these)" if set(bad) & REJECTED else ""
            die(f"unknown App Store locale(s): {', '.join(bad)}{hint}. See `localize.py locales`.")
        if not locs:
            die("no target locales. Pass --locales or set features.localizations (see `localize.py locales`).")
        return locs

    def keep(self):
        words = [self.name, *self.cfg.get("keep", []), *APPLE_NAMES]
        for p in self.ship.get("monetization", {}).get("products", []) or []:
            if p.get("displayName") and self.name and self.name in p["displayName"]:
                words.append(p["displayName"])
        return [w for w in dict.fromkeys(words) if w]

    @property
    def no_dashes(self):
        return bool(self.cfg.get("noDashes", False))

    def engine(self):
        e = self.a.engine or self.cfg.get("engine") or "claude"
        if e not in ENGINES:
            die(f"unknown engine {e!r}. Use one of: {', '.join(ENGINES)}")
        return e

    def path(self, *parts):
        return os.path.join(self.shipdir, "localize", *parts)


# --------------------------------------------------------------------------- briefs

def brief(ctx, locale, what):
    lang = LOCALES[locale][0]
    app = ctx.ship.get("app", {})
    vibe = ctx.ship.get("vibe", {}) or {}
    voice = ctx.cfg.get("voice") or vibe.get("voice") or vibe.get("words") or "clear, warm and plain"
    if isinstance(voice, list):
        voice = ", ".join(voice)
    rules = [
        "Translate meaning, not words. Write what a native speaker would write; rewrite anything that reads oddly when literal.",
        f"Never translate these, keep them exactly as written: {', '.join(ctx.keep())}.",
        "Keep every URL and email address exactly as written.",
        "Keep every placeholder exactly (%@, %lld, %d, %1$@, {name}, {{count}}): never add, drop or change one. "
        "Reorder them only if the grammar needs it.",
        "Keep the capitalisation style of the source (ALL CAPS stays ALL CAPS), and every leading or trailing "
        "space, line break, list marker and *asterisk* emphasis pair.",
        "Do not invent features, prices or claims that are not in the source.",
        "Apple feature names (Sign in with Apple, Home Screen, Lock Screen, Dynamic Island, widgets) use Apple's "
        "own official term in this language, as on Apple's local website.",
    ]
    if ctx.no_dashes:
        rules.append("Never use an em dash or an en dash. Use a comma, a colon, a period, or restructure.")
    return (f"You are localizing {what} for an iOS app called {ctx.name or 'this app'} into {lang} ({locale}).\n\n"
            f"About the app: {app.get('oneLiner') or app.get('description') or ''} "
            f"{('For: ' + app['audience'] + '.') if app.get('audience') else ''}\n"
            f"Voice: {voice}.\n\nHARD RULES:\n" + "\n".join(f"- {r}" for r in rules))


def listing_brief(ctx, locale, fields):
    research = ""
    cc = COUNTRY.get(locale)
    kpath = os.path.join(ctx.shipdir, "listing", f"keywords.{cc}.json") if cc else ""
    if kpath and os.path.exists(kpath):
        rows = load_json(kpath).get("keywords", [])[:25]
        research = ("\nScored local searches for this market (keyword: popularity/difficulty), prefer the strong, "
                    "relevant ones: " + ", ".join(f"{r['keyword']} {r['popularity']}/{r['difficulty']}" for r in rows))
    limits = "\n".join(f"- {f}: at most {LISTING_LIMITS[f]} characters including spaces." for f in fields)
    return (brief(ctx, locale, "the App Store listing") + "\n\nFIELD RULES:\n" + limits + f"""
- name: must contain {ctx.name or 'the app name'} exactly. Lead with the words people in this market would search
  for, if the source does. Count the characters.
- subtitle: a benefit, not a slogan, and no word that is already in name.
- keywords: comma separated with no spaces after commas. These are the terms people in this market actually type,
  not a translation of the English list. No word already in name or subtitle (Apple indexes those already), no
  competitor brand names, singular forms only. Use the budget.
- description: keep every heading, bullet and line break, and every URL.{research}

Return ONLY a JSON object with exactly these keys: {', '.join(fields)}.""")


def list_brief(ctx, locale, what):
    return (brief(ctx, locale, what) +
            "\n\nYou receive a JSON array of English strings. Return ONLY a JSON array of the same length, in the "
            "same order, holding the translations. No keys, no commentary, no code fences.")


# --------------------------------------------------------------------------- engines

def parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if m:
            return json.loads(m.group(1))
        raise


def http_json(url, body, headers, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", **headers})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {msg}")


def run_openai(ctx, system, user):
    key = os.environ.get("OPENAI_API_KEY") or read_env_value(ctx.secrets.get("openaiEnv"), "OPENAI_API_KEY")
    if not key:
        die("openai engine needs OPENAI_API_KEY or ship.json secrets.openaiEnv")
    model = ctx.cfg.get("model") or "gpt-5.4-mini"
    j = http_json("https://api.openai.com/v1/chat/completions",
                  {"model": model, "messages": [{"role": "system", "content": system},
                                                {"role": "user", "content": user}]},
                  {"authorization": f"Bearer {key}"})
    return j["choices"][0]["message"]["content"]


def run_gemini(ctx, system, user):
    key = os.environ.get("GEMINI_API_KEY") or read_env_value(ctx.secrets.get("geminiEnv"), "GEMINI_API_KEY")
    if not key:
        die("gemini engine needs GEMINI_API_KEY or ship.json secrets.geminiEnv")
    model = ctx.cfg.get("model") or "gemini-3.5-flash"
    j = http_json(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                  {"systemInstruction": {"parts": [{"text": system}]},
                   "contents": [{"role": "user", "parts": [{"text": user}]}],
                   "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}},
                  {"x-goog-api-key": key})
    return "".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"])


def run_codex(ctx, system, user):
    if not shutil.which("codex"):
        die("codex engine needs the Codex CLI (logged in with ChatGPT)")
    model = ctx.cfg.get("codexModel") or ctx.images.get("codexModel")
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "answer.txt")
        args = ["codex", "exec", "--skip-git-repo-check", "-s", "read-only", "-C", tmp, "-o", out]
        if model:
            args += ["-m", model]
        prompt = (system + "\n\nDo not run commands or edit files. Reply with the JSON only.\n\nINPUT:\n" + user)
        r = subprocess.run(args + ["-"], input=prompt, capture_output=True, text=True, timeout=900)
        if r.returncode != 0 or not os.path.exists(out):
            raise RuntimeError(f"codex exited {r.returncode}: {(r.stderr or r.stdout)[-300:]}")
        with open(out, encoding="utf-8") as f:
            return f.read()


ENGINES = {"claude": None, "openai": run_openai, "gemini": run_gemini, "codex": run_codex}


def ask(ctx, system, user):
    return parse_json(ENGINES[ctx.engine()](ctx, system, user))


def write_job(ctx, kind, locale, system, payload, expect):
    os.makedirs(ctx.path("jobs"), exist_ok=True)
    os.makedirs(ctx.path("out"), exist_ok=True)
    out = ctx.path("out", f"{kind}.{locale}.json")
    job = {"kind": kind, "locale": locale, "instructions": system, "input": payload, "expect": expect,
           "write_answer_to": out}
    path = ctx.path("jobs", f"{kind}.{locale}.json")
    save_json(path, job)
    return path


def print_job_help(kind, paths):
    print(f"\nWrote {len(paths)} job file(s) for Claude subagents:")
    for p in paths:
        print(f"  {p}")
    print(f"\nSpawn subagents (a few locales each). Each one reads its job file, follows `instructions` on `input`, "
          f"and writes only the JSON answer to `write_answer_to`. Then run: localize.py apply {kind}")


# --------------------------------------------------------------------------- checks

def placeholders(s):
    return sorted(PLACEHOLDER.findall(s or ""))


def check_text(ctx, locale, src, dst, field=""):
    """Problems with one translated string, as (level, message) pairs."""
    out = []
    label = f"{locale} {field}".strip()
    if not isinstance(dst, str) or not dst.strip():
        return [("FAIL", f"{label}: empty")]
    if placeholders(src) != placeholders(dst):
        out.append(("FAIL", f"{label}: placeholders {placeholders(dst)} != source {placeholders(src)}"))
    for w in ctx.keep():
        if w in src and w not in dst:
            out.append(("FAIL", f"{label}: lost protected word {w!r}"))
    for u in URLISH.findall(src):
        if u.rstrip(".,)") not in dst:
            out.append(("FAIL", f"{label}: lost {u}"))
    if ctx.no_dashes and DASHES.search(dst):
        out.append(("FAIL", f"{label}: em or en dash"))
    if src.count("*") != dst.count("*"):
        out.append(("WARN", f"{label}: *emphasis* markers changed"))
    bare = dst
    for w in sorted(ctx.keep(), key=len, reverse=True):  # brand and product names stay Latin
        bare = bare.replace(w, " ")
    bare = PLACEHOLDER.sub(" ", URLISH.sub(" ", bare))
    letters = re.sub(r"[\W\d_]", "", bare)
    script = SCRIPTS.get(locale)
    if script and len(letters) >= 4:
        native = len(re.findall(script, bare))
        if native < len(letters) * 0.3:
            out.append(("FAIL", f"{label}: mostly not in the {LOCALES[locale][0]} script"))
    if not locale.startswith("en") and len(re.sub(r"[\W\d_]", "", dst)) > 3 and dst.strip() == src.strip():
        kept = any(dst.strip() == w for w in ctx.keep())
        if not kept:
            out.append(("WARN", f"{label}: identical to the source (untranslated?)"))
    return out


def words(s):
    return set(re.findall(r"\w+", (s or "").lower()))


def check_listing(ctx, locale, src, dst):
    out = []
    for f, v in dst.items():
        if f in LISTING_LIMITS and isinstance(v, str) and len(v) > LISTING_LIMITS[f]:
            out.append(("FAIL", f"{locale} {f}: {len(v)}/{LISTING_LIMITS[f]} characters"))
        if f in src and f in LISTING_LIMITS and f != "keywords":  # URLs are copied, not translated
            out += check_text(ctx, locale, src[f], v, f)
    if not locale.startswith("en") and src.get("description") and dst.get("description"):
        src_lines = {x.strip() for x in src["description"].splitlines() if len(x.strip()) > 8}
        keep = [w.lower() for w in ctx.keep()]
        left = [x.strip() for x in dst["description"].splitlines()
                if x.strip() in src_lines and not URLISH.search(x)
                and re.sub(r"[\W\d_]", "", x.lower()) not in {re.sub(r"[\W\d_]", "", k) for k in keep}]
        if left:
            out.append(("FAIL", f"{locale} description: {len(left)} line(s) left in the source language, "
                                f"for example {left[0]!r}"))
    if ctx.name and ctx.name not in (dst.get("name") or ""):
        out.append(("FAIL", f"{locale} name: does not contain {ctx.name}"))
    for f in ("name", "subtitle"):
        if re.search(r"\b(apple|iphone|ipad|ios)\b", (dst.get(f) or "").lower()):
            out.append(("FAIL", f"{locale} {f}: Apple trademark in name or subtitle"))
    kw = dst.get("keywords") or ""
    if kw:
        if ", " in kw:
            out.append(("WARN", f"{locale} keywords: spaces after commas waste characters"))
        if ctx.no_dashes and DASHES.search(kw):
            out.append(("FAIL", f"{locale} keywords: em or en dash"))
        terms = [t.strip().lower() for t in kw.split(",") if t.strip()]
        dupes = sorted({t for t in terms if terms.count(t) > 1})
        if dupes:
            out.append(("WARN", f"{locale} keywords repeated: {', '.join(dupes)}"))
        wasted = sorted({w for t in terms for w in t.split() if w in words(dst.get("name")) | words(dst.get("subtitle"))})
        if wasted:
            out.append(("WARN", f"{locale} keywords already in name or subtitle: {', '.join(wasted)}"))
        dense = locale in ("ja", "ko", "zh-Hans", "zh-Hant")  # one character carries a word
        if len(kw) < (40 if dense else 70):
            out.append(("WARN", f"{locale} keywords: only {len(kw)}/100 characters used"))
    return out


def report(problems):
    fails = [m for l, m in problems if l == "FAIL"]
    for l, m in problems:
        print(f"{l}  {m}")
    return len(fails)


# --------------------------------------------------------------------------- listing

def listing_source(ctx):
    src = (ctx.ship.get("listing") or {}).get(ctx.primary)
    if not src:
        die(f"no listing.{ctx.primary} in ship.json; write the source listing first (ship-listing)")
    return {f: src[f] for f in LISTING_LIMITS if isinstance(src.get(f), str) and src[f].strip()}


def accept_listing(ctx, locale, src, dst):
    probs = check_listing(ctx, locale, src, dst)
    nfail = report(probs)
    if nfail:
        print(f"  {locale}: not saved ({nfail} failures)")
        return False
    listing = ctx.ship.setdefault("listing", {})
    keep = {k: v for k, v in (listing.get(locale) or {}).items() if k not in src}
    listing[locale] = {**keep, **{f: dst[f] for f in src}}
    print(f"  {locale}: saved to listing.{locale}")
    return True


def cmd_listing(ctx):
    src = listing_source(ctx)
    fields = list(src)
    todo = [l for l in ctx.locales() if ctx.a.force or not (ctx.ship.get("listing") or {}).get(l)]
    if not todo:
        print("Every locale already has a listing. Use --force to redo.")
        return
    if ctx.engine() == "claude":
        paths = [write_job(ctx, "listing", l, listing_brief(ctx, l, fields), src,
                           f"one JSON object with keys {fields}") for l in todo]
        return print_job_help("listing", paths)
    saved = 0
    for l in todo:
        print(f"{l}: translating with {ctx.engine()}")
        system = listing_brief(ctx, l, fields)
        try:
            out = ask(ctx, system, json.dumps(src, ensure_ascii=False))
            for attempt in range(3):
                over = [f"{f} is {len(out.get(f) or '')} characters, the limit is {LISTING_LIMITS[f]}"
                        for f in fields if len(out.get(f) or "") > LISTING_LIMITS[f]]
                if not over:
                    break
                print(f"  retry {attempt + 1}: {'; '.join(over)}")
                fix = {**src, "_fix": "Too long: " + ". ".join(over) + ". Return all keys again; tighten the listed "
                       "fields by rewriting, never by dropping headings, bullets or URLs. Count characters.",
                       "_previous": out}
                again = ask(ctx, system, json.dumps(fix, ensure_ascii=False))
                out.update({f: again[f] for f in fields if again.get(f)})
        except Exception as e:  # one bad locale should not stop the rest
            print(f"  {l}: failed ({e})")
            continue
        if accept_listing(ctx, l, src, out):
            saved += 1
            save_json(ctx.ship_path, ctx.ship)  # after every locale, so a crash loses nothing
    print(f"\n{saved}/{len(todo)} locale(s) saved. Next: score the new keywords per market "
          "(listing.py keywords ... --country <cc>) and lint, then ship-store listing --dry-run.")


# --------------------------------------------------------------------------- headlines

def plan_path(ctx):
    return os.path.join(ctx.shipdir, "screenshots", "plan.json")


def headline_items(ctx, plan):
    """(slide index, field, English text) for every headline and subline."""
    items = []
    for i, s in enumerate(plan.get("slides", [])):
        for f in ("headline", "subline"):
            v = s.get(f)
            if isinstance(v, dict):
                v = v.get(ctx.primary) or v.get("en-US") or next(iter(v.values()), "")
            if isinstance(v, str) and v.strip():
                items.append((i, f, v))
    return items


def merge_headlines(ctx, plan, locale, items, answers):
    probs, ok = [], 0
    for (i, f, src), dst in zip(items, answers):
        p = check_text(ctx, locale, src, dst, f"slide {i + 1} {f}")
        if src.count("\n") != (dst or "").count("\n"):
            p.append(("WARN", f"{locale} slide {i + 1} {f}: line breaks changed"))
        probs += p
        if any(l == "FAIL" for l, _ in p):
            continue
        s = plan["slides"][i]
        cur = s.get(f)
        s[f] = {**(cur if isinstance(cur, dict) else {ctx.primary: cur}), locale: dst}
        ok += 1
    report(probs)
    print(f"  {locale}: {ok}/{len(items)} headline texts saved")


def ordered_locales(ctx, locs):
    rest = sorted({l for l in locs if l != ctx.primary})
    return [ctx.primary, *rest]


def cmd_headlines(ctx):
    pp = plan_path(ctx)
    plan = load_json(pp)
    if not plan.get("slides"):
        die(f"no slides in {pp}; plan the screenshots first (ship-screenshots)")
    items = headline_items(ctx, plan)
    texts = [t for _, _, t in items]
    todo = []
    for l in ctx.locales():
        done = all(isinstance(plan["slides"][i].get(f), dict) and plan["slides"][i][f].get(l) for i, f, _ in items)
        if ctx.a.force or not done:
            todo.append(l)
    if not todo:
        print("Every locale already has headlines. Use --force to redo.")
        return
    what = ("App Store screenshot headlines (short benefit lines over app screenshots). Keep them as short as the "
            "English or shorter; \\n is a deliberate line break and *word* marks the accent colour")
    if ctx.engine() == "claude":
        paths = [write_job(ctx, "headlines", l, list_brief(ctx, l, what), texts,
                           f"a JSON array of {len(texts)} strings") for l in todo]
        return print_job_help("headlines", paths)
    for l in todo:
        print(f"{l}: translating {len(texts)} headline texts with {ctx.engine()}")
        try:
            out = ask(ctx, list_brief(ctx, l, what), json.dumps(texts, ensure_ascii=False))
        except Exception as e:
            print(f"  {l}: failed ({e})")
            continue
        if not isinstance(out, list) or len(out) != len(texts):
            print(f"  {l}: wrong answer shape, skipped")
            continue
        merge_headlines(ctx, plan, l, items, out)
    plan["locales"] = ordered_locales(ctx, [*(plan.get("locales") or []), *todo])
    save_json(pp, plan)
    print(f"\nSaved {pp}. Render with ship-screenshots render.py (every locale in plan.locales).")


# --------------------------------------------------------------------------- strings

def find_catalog(ctx):
    if ctx.a.catalog:
        return os.path.abspath(ctx.a.catalog)
    root = ctx.root
    skip = ("/node_modules/", "/Pods/", "/build/", "/DerivedData/", "/.git/", "/ios/Pods/")
    found = [p for p in glob.glob(os.path.join(root, "**", "Localizable.xcstrings"), recursive=True)
             if not any(s in p for s in skip)]
    if found:
        return sorted(found, key=len)[0]
    for pat in ("locales/en.json", "src/locales/en.json", "i18n/en.json", "src/i18n/en.json",
                "assets/locales/en.json", "src/i18n/locales/en.json", "app/i18n/en.json", "translations/en.json"):
        p = os.path.join(root, pat)
        if os.path.exists(p):
            return p
    found = [p for p in glob.glob(os.path.join(root, "**", "en.lproj", "Localizable.strings"), recursive=True)
             if not any(s in p for s in skip)]
    return sorted(found, key=len)[0] if found else None


class Catalog:
    """Uniform view of a String Catalog, an i18n JSON folder, or .strings files."""

    def __init__(self, path, primary_lang):
        self.path = path
        self.kind = ("xcstrings" if path.endswith(".xcstrings") else
                     "json" if path.endswith(".json") else "strings")
        self.src_lang = primary_lang
        if self.kind == "xcstrings":
            self.data = load_json(path)
            self.src_lang = self.data.get("sourceLanguage", primary_lang)
            with open(path, encoding="utf-8") as f:
                self.sep = " : " if '" : ' in f.read(4000) else ": "  # keep Xcode's or the repo's style
        elif self.kind == "json":
            self.dir = os.path.dirname(path)
            self.src = flatten(load_json(path))
            self.targets = {}
        else:
            self.dir = os.path.dirname(os.path.dirname(path))
            self.src = parse_strings(path)
            self.targets = {}

    def lang_code(self, locale):
        code = LOCALES[locale][1]
        if self.kind != "xcstrings":
            return code
        have = set()
        for e in self.data.get("strings", {}).values():
            have |= set((e.get("localizations") or {}).keys())
        base = code.split("-")[0]
        # Follow the catalog's existing convention (some apps use "pt", not "pt-BR").
        if code not in have and base in have and base != code:
            return base
        return code

    def missing(self, lang):
        """[(key, source text)] that need a translation into lang."""
        out = []
        if self.kind == "xcstrings":
            for key, e in self.data.get("strings", {}).items():
                if e.get("shouldTranslate") is False or not key.strip() or not re.search(r"[A-Za-z]", key):
                    continue
                locs = e.get("localizations") or {}
                if "variations" in (locs.get(self.src_lang) or {}) or "variations" in (locs.get(lang) or {}):
                    continue  # plural and device variations: by hand
                unit = (locs.get(lang) or {}).get("stringUnit") or {}
                if unit.get("state") == "translated" and unit.get("value"):
                    continue
                src = ((locs.get(self.src_lang) or {}).get("stringUnit") or {}).get("value") or key
                out.append((key, src))
            return out
        have = self.load_target(lang)
        return [(k, v) for k, v in self.src.items() if isinstance(v, str) and v.strip() and not have.get(k)]

    def variations_skipped(self, lang):
        if self.kind != "xcstrings":
            return 0
        return sum(1 for e in self.data.get("strings", {}).values()
                   if "variations" in ((e.get("localizations") or {}).get(self.src_lang) or {}))

    def target_path(self, lang):
        if self.kind == "json":
            return os.path.join(self.dir, f"{lang}.json")
        return os.path.join(self.dir, f"{lang}.lproj", "Localizable.strings")

    def load_target(self, lang):
        if lang not in self.targets:
            p = self.target_path(lang)
            self.targets[lang] = (flatten(load_json(p)) if self.kind == "json" else
                                  parse_strings(p) if os.path.exists(p) else {})
        return self.targets[lang]

    def set(self, lang, key, value):
        if self.kind == "xcstrings":
            e = self.data["strings"][key]
            e.setdefault("localizations", {})[lang] = {"stringUnit": {"state": "translated", "value": value}}
        else:
            self.load_target(lang)[key] = value

    def save(self):
        if self.kind == "xcstrings":
            ordered = {"sourceLanguage": self.data.get("sourceLanguage"), "strings": {},
                       "version": self.data.get("version", "1.0")}
            for k in sorted(self.data["strings"]):
                ordered["strings"][k] = self.data["strings"][k]
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(ordered, f, indent=2, ensure_ascii=False, separators=(",", self.sep))
                f.write("\n")
            return [self.path]
        paths = []
        for lang, flat in self.targets.items():
            p = self.target_path(lang)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            if self.kind == "json":
                save_json(p, unflatten({k: flat[k] for k in self.src if k in flat}))
            else:
                with open(p, "w", encoding="utf-8") as f:
                    for k in self.src:
                        if k in flat:
                            f.write(f'"{esc(k)}" = "{esc(flat[k])}";\n')
            paths.append(p)
        return paths


def flatten(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        else:
            out[key] = v
    return out


def unflatten(flat):
    out = {}
    for k, v in flat.items():
        cur = out
        parts = k.split(".")
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = v
    return out


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def parse_strings(path):
    if not os.path.exists(path):
        return {}
    text = open(path, encoding="utf-8").read()
    pairs = re.findall(r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;', text)
    un = lambda s: s.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    return {un(k): un(v) for k, v in pairs}


def strings_what(ctx):
    return ("the interface strings of the app (buttons, headings, empty states, alerts, accessibility labels). "
            "Keep them about as long as the English; they must fit the same space")


def accept_strings(ctx, cat, locale, lang, chunk, answers):
    wrote, probs = 0, []
    for (key, src), dst in zip(chunk, answers):
        p = check_text(ctx, locale, src, dst, f"{key[:50]!r}")
        p = [x for x in p if not (x[0] == "WARN" and "identical" in x[1] and len(src) < 12)]
        probs += p
        if any(l == "FAIL" for l, _ in p):
            continue
        cat.set(lang, key, dst)
        wrote += 1
    return wrote, probs


def cmd_strings(ctx):
    path = find_catalog(ctx)
    if not path:
        die("no string catalog found (Localizable.xcstrings, locales/en.json or en.lproj). "
            "The app is not set up for localization yet; see the bootstrap section of this skill.")
    cat = Catalog(path, LOCALES.get(ctx.primary, ("", "en"))[1].split("-")[0])
    print(f"Catalog: {os.path.relpath(path, ctx.root)} ({cat.kind})")
    batch = ctx.a.batch
    jobs, total, all_probs = [], 0, []
    for locale in ctx.locales():
        lang = cat.lang_code(locale)
        todo = cat.missing(lang)
        if not todo:
            print(f"{locale} ({lang}): nothing missing")
            continue
        print(f"{locale} ({lang}): {len(todo)} strings to translate")
        system = list_brief(ctx, locale, strings_what(ctx))
        for n in range(0, len(todo), batch):
            chunk = todo[n:n + batch]
            if ctx.engine() == "claude":
                jobs.append(write_job(ctx, "strings", f"{locale}.{n // batch:03d}", system,
                                      [s for _, s in chunk], f"a JSON array of {len(chunk)} strings"))
                save_json(ctx.path("jobs", f"strings.{locale}.{n // batch:03d}.keys.json"),
                          {"catalog": path, "lang": lang, "keys": [k for k, _ in chunk]})
                continue
            out = None
            for attempt in range(3):
                try:
                    got = ask(ctx, system, json.dumps([s for _, s in chunk], ensure_ascii=False))
                    if isinstance(got, list) and len(got) == len(chunk):
                        out = got
                        break
                    raise ValueError(f"got {len(got) if isinstance(got, list) else type(got).__name__}")
                except Exception as e:
                    print(f"  batch {n // batch} attempt {attempt + 1}: {e}")
                    time.sleep(2 * (attempt + 1))
            if out is None:
                continue
            wrote, probs = accept_strings(ctx, cat, locale, lang, chunk, out)
            total += wrote
            all_probs += probs
            print(f"  {min(n + batch, len(todo))}/{len(todo)}")
    if jobs:
        return print_job_help("strings", jobs)
    report(all_probs)
    for p in cat.save():
        print(f"Saved {os.path.relpath(p, ctx.root)}")
    skipped = cat.variations_skipped(None)
    print(f"\nWrote {total} translations. Rejected strings stay untranslated (they fall back to the source)."
          + (f" {skipped} plural or device-variation keys are left for you." if skipped else ""))
    after_strings(ctx, cat)


def after_strings(ctx, cat):
    if cat.kind == "xcstrings":
        others = [p for p in glob.glob(os.path.join(ctx.root, "**", "Localizable.xcstrings"), recursive=True)
                  if os.path.abspath(p) != os.path.abspath(cat.path) and "/build/" not in p]
        if others:
            print("Other catalogs exist (widgets and extensions read their own bundle): "
                  + ", ".join(os.path.relpath(p, ctx.root) for p in others)
                  + ". Copy or translate them too, or extension text stays in the source language.")


# --------------------------------------------------------------------------- apply

def read_answer(path):
    """A subagent's answer file, tolerating code fences; None when absent or unreadable."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return parse_json(f.read())
    except (ValueError, json.JSONDecodeError):
        print(f"  unreadable JSON in {path}")
        return None


def cmd_apply(ctx):
    kind = ctx.a.kind
    jobs = sorted(glob.glob(ctx.path("jobs", f"{kind}.*.json")))
    jobs = [j for j in jobs if not j.endswith(".keys.json")]
    if not jobs:
        die(f"no {kind} job files in {ctx.path('jobs')}")
    missing = []
    if kind == "listing":
        src = listing_source(ctx)
        for j in jobs:
            job = load_json(j)
            ans = read_answer(job["write_answer_to"])
            if ans is None:
                missing.append(job["locale"])
                continue
            accept_listing(ctx, job["locale"], src, ans)
        save_json(ctx.ship_path, ctx.ship)
    elif kind == "headlines":
        pp = plan_path(ctx)
        plan = load_json(pp)
        items = headline_items(ctx, plan)
        for j in jobs:
            job = load_json(j)
            ans = read_answer(job["write_answer_to"])
            if not isinstance(ans, list) or len(ans) != len(items):
                missing.append(job["locale"])
                continue
            merge_headlines(ctx, plan, job["locale"], items, ans)
            plan["locales"] = ordered_locales(ctx, [*(plan.get("locales") or []), job["locale"]])
        save_json(pp, plan)
    else:
        cats, probs, total = {}, [], 0
        for j in jobs:
            job = load_json(j)
            meta = load_json(j[:-5] + ".keys.json")
            ans = read_answer(job["write_answer_to"])
            if not isinstance(ans, list) or len(ans) != len(meta["keys"]):
                missing.append(job["locale"])
                continue
            path = meta["catalog"]
            if path not in cats:
                cats[path] = Catalog(path, "en")
            cat = cats[path]
            locale = job["locale"].rsplit(".", 1)[0]
            chunk = list(zip(meta["keys"], job["input"]))
            wrote, p = accept_strings(ctx, cat, locale, meta["lang"], chunk, ans)
            total += wrote
            probs += p
        report(probs)
        for cat in cats.values():
            for p in cat.save():
                print(f"Saved {p}")
            after_strings(ctx, cat)
        print(f"Wrote {total} translations.")
    if missing:
        print(f"No usable answer yet for: {', '.join(missing)}")
    else:
        print(f"All {kind} jobs applied.")


# --------------------------------------------------------------------------- check, locales

def cmd_check(ctx):
    probs = []
    listing = ctx.ship.get("listing") or {}
    src = {f: v for f, v in (listing.get(ctx.primary) or {}).items() if isinstance(v, str)}
    locs = [l for l in listing if l != ctx.primary and isinstance(listing[l], dict)]
    if ctx.a.locales:
        locs = [l for l in locs if l in ctx.a.locales.split(",")]
    for l in locs:
        probs += check_listing(ctx, l, src, listing[l])
    plan = load_json(plan_path(ctx))
    if plan.get("slides"):
        for i, s in enumerate(plan["slides"]):
            for f in ("headline", "subline"):
                v = s.get(f)
                if isinstance(v, dict):
                    base = v.get(ctx.primary, "")
                    for l, t in v.items():
                        if l != ctx.primary and l in LOCALES:
                            probs += check_text(ctx, l, base, t, f"slide {i + 1} {f}")
    path = find_catalog(ctx)
    if path:
        cat = Catalog(path, "en")
        if cat.kind == "xcstrings":
            langs = {}
            for key, e in cat.data.get("strings", {}).items():
                locs_ = e.get("localizations") or {}
                src_t = ((locs_.get(cat.src_lang) or {}).get("stringUnit") or {}).get("value") or key
                for lang, v in locs_.items():
                    unit = v.get("stringUnit") or {}
                    if lang == cat.src_lang or not unit.get("value"):
                        continue
                    loc = next((l for l, (_, c) in LOCALES.items() if c == lang or c.split("-")[0] == lang), None)
                    if loc:
                        langs[lang] = langs.get(lang, 0) + 1
                        probs += [x for x in check_text(ctx, loc, src_t, unit["value"], f"{key[:40]!r}")
                                  if x[0] == "FAIL"]
            total = sum(1 for e in cat.data.get("strings", {}).values() if e.get("shouldTranslate") is not False)
            print("String catalog coverage: " + ", ".join(f"{l} {n}/{total}" for l, n in sorted(langs.items())))
    nfail = report(probs)
    print(f"\n{nfail} failure(s), {len(probs) - nfail} warning(s).")
    sys.exit(1 if nfail else 0)


def cmd_locales(ctx):
    preset = ctx.a.preset
    if preset:
        locs = PRESETS[preset]
        print(f"{preset}: {', '.join(locs)}")
        if ctx.a.set:
            ctx.ship.setdefault("features", {})["localizations"] = [l for l in locs if l != ctx.primary]
            save_json(ctx.ship_path, ctx.ship)
            print("Saved to features.localizations.")
        return
    print("App Store locale -> language (code inside the app)")
    for l, (name, code) in sorted(LOCALES.items()):
        print(f"  {l:8} {name:24} {code}")
    print(f"\nPresets: " + "; ".join(f"{k} ({len(v)})" for k, v in PRESETS.items()))
    print("Rejected by App Store Connect despite looking valid: " + ", ".join(sorted(REJECTED)))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ship", default=".ship/ship.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    lo = sub.add_parser("locales")
    lo.add_argument("--preset", choices=sorted(PRESETS))
    lo.add_argument("--set", action="store_true")
    for name in ("listing", "headlines", "strings"):
        sp = sub.add_parser(name)
        sp.add_argument("--locales")
        sp.add_argument("--engine", choices=sorted(ENGINES))
        sp.add_argument("--force", action="store_true")
        if name == "strings":
            sp.add_argument("--catalog")
            sp.add_argument("--batch", type=int, default=40)
    ap = sub.add_parser("apply")
    ap.add_argument("kind", choices=["listing", "headlines", "strings"])
    ck = sub.add_parser("check")
    ck.add_argument("--locales")
    ck.add_argument("--catalog")
    a = p.parse_args()
    for k in ("locales", "engine", "catalog", "force"):
        if not hasattr(a, k):
            setattr(a, k, None)
    ctx = Ctx(a)
    {"locales": cmd_locales, "listing": cmd_listing, "headlines": cmd_headlines, "strings": cmd_strings,
     "apply": cmd_apply, "check": cmd_check}[a.cmd](ctx)


if __name__ == "__main__":
    main()
