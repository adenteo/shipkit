"""
Batch-generate a set of images with OpenAI's gpt-image API.

Usage:
    python3 generate_images.py <config.json>

The key comes from OPENAI_API_KEY, else from the env file named in
SHIPKIT_OPENAI_ENV ("path" or "path:VARIABLE"), which imagine.py sets from
ship.json secrets.openaiEnv. Most callers should use imagine.py, which picks
the backend (OpenAI API, Codex CLI, or Codex in a Herdr pane) for you.

Handles any images, illustrations, icons, mascot art, marketing visuals,
backgrounds, at any supported dimensions. The config JSON drives everything;
see references/example-config.json and SKILL.md for the field reference.

Behaviour:
  - Each image is generated once and written as <output_dir>/<name>.png.
  - Images already on disk are SKIPPED (re-runs only fill gaps / re-post-
    process), so iterate on one bad image by deleting just its file.
  - `use_reference` images go through /images/edits with `reference_image`
    attached, so they stay on-style with an existing asset.
  - Other images go through /images/generations (standalone).
  - `size` / `quality` may be set globally and overridden per image.
  - Optional post-processing (per-image `transparent` / `crop`) runs after
    generation, useful for icons/stickers, off by default for normal images.

stdlib only for the API calls; Pillow is needed only for post-processing.
"""

import base64
import io
import json
import os
import sys
import urllib.request
import urllib.error
import uuid

GENERATIONS_URL = "https://api.openai.com/v1/images/generations"
EDITS_URL = "https://api.openai.com/v1/images/edits"

# ChatGPT Image 2. Set "model" in the config (or images.model in ship.json) to
# pin a dated snapshot or a newer model; fall back to "gpt-image-1" if the
# API rejects the id.
DEFAULT_MODEL = "gpt-image-2"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict:
    with open(path, "r") as f:
        cfg = json.load(f)
    cfg.setdefault("model", DEFAULT_MODEL)
    cfg.setdefault("size", "1024x1024")
    cfg.setdefault("quality", "medium")
    cfg.setdefault("style_preamble", "")
    cfg.setdefault("output_dir", "generated-images")
    cfg.setdefault("post_process", {})
    cfg["post_process"].setdefault("transparent_background", False)
    cfg["post_process"].setdefault("flood_fill_tolerance", 40)
    cfg["post_process"].setdefault("crop_to_subject", False)
    cfg["post_process"].setdefault("crop_margin_pct", 0.08)
    # `images` is the canonical key; accept `icons` as an alias.
    images = cfg.get("images") or cfg.get("icons")
    if not images:
        sys.exit("ERROR: config has no `images` list.")
    cfg["images"] = images
    base = os.path.dirname(os.path.abspath(path))
    if not os.path.isabs(cfg["output_dir"]):
        cfg["output_dir"] = os.path.join(base, cfg["output_dir"])
    if cfg.get("reference_image") and not os.path.isabs(cfg["reference_image"]):
        cfg["reference_image"] = os.path.join(base, cfg["reference_image"])
    return cfg


def read_env_value(spec: str, default_var: str) -> str:
    """Read one variable from an env file. spec is "path" or "path:VARIABLE"."""
    path, _, var = spec.partition(":")
    path = os.path.expanduser(path)
    var = var or default_var
    if not os.path.exists(path):
        return ""
    with open(path) as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    for ln in lines:
        k, sep, v = ln.partition("=")
        if sep and k.strip().removeprefix("export ").strip() == var:
            return v.strip().strip('"').strip("'")
    # A file holding just the raw key on one line.
    if len(lines) == 1 and "=" not in lines[0]:
        return lines[0]
    return ""


def api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key and os.environ.get("SHIPKIT_OPENAI_ENV"):
        key = read_env_value(os.environ["SHIPKIT_OPENAI_ENV"], "OPENAI_API_KEY")
    if not key:
        sys.exit("ERROR: no OpenAI key. Set OPENAI_API_KEY, or point ship.json "
                 "secrets.openaiEnv at an env file that defines it.")
    return key


# ---------------------------------------------------------------------------
# Multipart form-data builder (stdlib only): for the /images/edits endpoint
# ---------------------------------------------------------------------------

def build_multipart(fields, files):
    """fields: [(name, value)]   files: [(name, filename, bytes, content_type)]"""
    boundary = uuid.uuid4().hex
    buf = io.BytesIO()
    for name, value in fields:
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        buf.write(value.encode("utf-8"))
        buf.write(b"\r\n")
    for name, filename, data, ctype in files:
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(
            f'Content-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"\r\n'.encode()
        )
        buf.write(f"Content-Type: {ctype}\r\n\r\n".encode())
        buf.write(data)
        buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _post(url, body, headers, name):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        print(f"  ERROR {e.code} for {name}: "
              f"{e.read().decode('utf-8', 'replace')[:400]}")
        return None
    except urllib.error.URLError as e:
        print(f"  ERROR (network) for {name}: {e.reason}")
        return None
    try:
        data = json.loads(raw)
        return data["data"][0]["b64_json"]
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"  ERROR parsing response for {name}: {e}  body={raw[:200]!r}")
        return None


def generate(image, cfg, ref_bytes, key, out_path):
    """Generate one image. Returns True on success."""
    name = image["name"]
    use_ref = image.get("use_reference", False) and ref_bytes is not None
    prompt = image["prompt"]
    if use_ref and cfg["style_preamble"]:
        prompt = cfg["style_preamble"] + prompt
    size = image.get("size", cfg["size"])
    quality = image.get("quality", cfg["quality"])

    if use_ref:
        fields = [("model", cfg["model"]), ("prompt", prompt),
                  ("size", size), ("quality", quality), ("n", "1")]
        files = [("image[]", "reference.png", ref_bytes, "image/png")]
        body, ctype = build_multipart(fields, files)
        headers = {"Authorization": f"Bearer {key}", "Content-Type": ctype}
        b64 = _post(EDITS_URL, body, headers, name)
    else:
        payload = {"model": cfg["model"], "prompt": prompt,
                   "size": size, "quality": quality, "n": 1}
        headers = {"Authorization": f"Bearer {key}",
                   "Content-Type": "application/json"}
        b64 = _post(GENERATIONS_URL, json.dumps(payload).encode(), headers, name)

    if b64 is None:
        return False
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(b64))
    print(f"  saved {out_path}  ({size})")
    return True


# ---------------------------------------------------------------------------
# Post-processing (Pillow): optional, mainly for icons / stickers
# ---------------------------------------------------------------------------

def post_process(cfg):
    """Apply per-image transparency + crop. image-level keys override globals."""
    pp = cfg["post_process"]
    needs = [im for im in cfg["images"]
             if im.get("transparent", pp["transparent_background"])
             or im.get("crop", pp["crop_to_subject"])]
    if not needs:
        return
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("\nWARNING: Pillow not installed, skipping transparency/crop.")
        print("  Install: pip3 install Pillow")
        return

    print(f"\n--- Post-processing ({len(needs)} image(s)) ---")
    for im in needs:
        path = os.path.join(cfg["output_dir"], f"{im['name']}.png")
        if not os.path.exists(path):
            continue
        transparent = im.get("transparent", pp["transparent_background"])
        crop = im.get("crop", pp["crop_to_subject"])
        try:
            img = Image.open(path).convert("RGBA")
            if transparent:
                # Flood-fill the flat background from all 4 corners.
                # IMPORTANT: this only works if the subject does NOT touch
                # the corners, otherwise the seed lands inside the subject
                # and erases it. Prompt for a clear background margin.
                w, h = img.size
                for xy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
                    ImageDraw.floodfill(img, xy=xy, value=(0, 0, 0, 0),
                                        thresh=pp["flood_fill_tolerance"])
            if crop:
                bbox = img.getbbox()
                if bbox:
                    c = img.crop(bbox)
                    cw, ch = c.size
                    mx = int(round(cw * pp["crop_margin_pct"]))
                    my = int(round(ch * pp["crop_margin_pct"]))
                    padded = Image.new("RGBA", (cw + 2 * mx, ch + 2 * my),
                                       (0, 0, 0, 0))
                    padded.paste(c, (mx, my))
                    img = padded
            img.save(path, format="PNG")
            print(f"  {im['name']}: "
                  f"{'transparent ' if transparent else ''}"
                  f"{'cropped' if crop else ''}".strip())
        except Exception as exc:
            print(f"  WARNING: could not post-process {im['name']}: {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python3 generate_images.py <config.json>")
    cfg = load_config(sys.argv[1])
    os.makedirs(cfg["output_dir"], exist_ok=True)

    pending = [im for im in cfg["images"]
               if not os.path.exists(os.path.join(cfg["output_dir"],
                                                   f"{im['name']}.png"))]

    if pending:
        key = api_key()
        ref_bytes = None
        if cfg.get("reference_image"):
            if not os.path.exists(cfg["reference_image"]):
                sys.exit(f"ERROR: reference_image not found: {cfg['reference_image']}")
            with open(cfg["reference_image"], "rb") as f:
                ref_bytes = f.read()
            print(f"Reference image: {cfg['reference_image']} ({len(ref_bytes):,} bytes)")
        print(f"Model: {cfg['model']}")

        ok, fail = [], []
        print(f"\n--- Generating {len(pending)} image(s) "
              f"({len(cfg['images']) - len(pending)} already on disk) ---")
        for im in cfg["images"]:
            out = os.path.join(cfg["output_dir"], f"{im['name']}.png")
            if os.path.exists(out):
                continue
            print(f"Generating {im['name']} ...")
            (ok if generate(im, cfg, ref_bytes, key, out) else fail).append(im["name"])
        print(f"\nGenerated {len(ok)}/{len(pending)}. "
              + (f"FAILED: {', '.join(fail)}" if fail else "All OK."))
        if fail:
            print("Re-run to retry failed images (successful ones are skipped).")
    else:
        print("All images already on disk, skipping generation, post-processing only.")

    post_process(cfg)
    print(f"\nDone. Output: {cfg['output_dir']}")


if __name__ == "__main__":
    main()
