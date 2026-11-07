#!/usr/bin/env python3
"""
One front door for image generation and second opinions, whatever the user has.

Backends (pick with --backend, else ship.json images.backend, else
~/.config/shipkit/defaults.json, else the first one that works):
  openai       OpenAI Images API with the user's API key (pay per image).
  codex        Codex CLI (`codex exec`), using the user's ChatGPT plan. One
               fresh Codex run per image, no API key needed.
  codex-herdr  A Codex agent in a Herdr pane beside this one. The user can watch
               and talk to it, and it keeps context across images. Needs this
               process to run inside Herdr (HERDR_ENV=1).

Commands:
  imagine.py doctor                      which backends work here
  imagine.py gen BATCH.json [--dry-run]  generate every image in a batch
  imagine.py ask "question" [--image a.png ...]
                                         ask Codex for ideas, names, critique

The batch format is the generate_images.py config (images[], style_preamble,
reference_image, size, quality, output_dir, post_process). Images already on
disk are skipped, so re-runs only fill gaps.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import generate_images as gi  # noqa: E402

CODEX_IMAGES = os.path.expanduser("~/.codex/generated_images")
HERDR_AGENT = "shipkit-images"
BACKENDS = ("openai", "codex", "codex-herdr")
_claimed, _claim_lock = set(), threading.Lock()  # fallback copies when runs overlap


# ---------------------------------------------------------------------------
# Settings: ship.json, then personal defaults
# ---------------------------------------------------------------------------

def load_json(path):
    try:
        with open(os.path.expanduser(path)) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def settings(ship_path):
    ship = load_json(ship_path)
    defaults = load_json("~/.config/shipkit/defaults.json")
    images = {**defaults.get("images", {}), **{k: v for k, v in ship.get("images", {}).items() if v not in ("", None)}}
    secrets = {**defaults.get("secrets", {}), **{k: v for k, v in ship.get("secrets", {}).items() if v}}
    return images, secrets


def have_openai(secrets):
    if os.environ.get("OPENAI_API_KEY"):
        return True
    spec = secrets.get("openaiEnv")
    return bool(spec and gi.read_env_value(spec, "OPENAI_API_KEY"))


def have_codex():
    return shutil.which("codex") is not None


def in_herdr():
    return os.environ.get("HERDR_ENV") == "1" and shutil.which("herdr") is not None


def resolve_backend(requested, images, secrets):
    choice = requested or images.get("backend") or ""
    if choice == "none":
        sys.exit("ship.json images.backend is \"none\" (no image generation). Pass --backend to override.")
    if choice:
        if choice not in BACKENDS:
            sys.exit(f"Unknown backend {choice!r}. Use one of: {', '.join(BACKENDS)}")
        return choice
    if have_openai(secrets):
        return "openai"
    if have_codex():
        return "codex-herdr" if in_herdr() else "codex"
    sys.exit("No image backend available. Set an OpenAI key (ship.json secrets.openaiEnv) "
             "or install and log in to the Codex CLI. Run `imagine.py doctor` for details.")


# ---------------------------------------------------------------------------
# Codex helpers
# ---------------------------------------------------------------------------

def newest_codex_image(since):
    """Newest PNG Codex saved after `since` that no other run has taken."""
    with _claim_lock:
        best, best_t = None, since
        for root, _, files in os.walk(CODEX_IMAGES):
            for name in files:
                p = os.path.join(root, name)
                if not name.lower().endswith(".png") or p in _claimed:
                    continue
                t = os.path.getmtime(p)
                if t > best_t:
                    best, best_t = p, t
        if best:
            _claimed.add(best)
        return best


def image_prompt(image, cfg, out_name):
    prompt = image["prompt"]
    if cfg.get("style_preamble"):
        prompt = cfg["style_preamble"] + prompt
    size = image.get("size", cfg["size"])
    w, h = (int(x) for x in size.split("x"))
    shape = "square" if w == h else ("landscape" if w > h else "portrait")
    ref = ""
    if image.get("use_reference") and cfg.get("reference_image"):
        ref = (f" Match the style, palette and rendering of the reference image "
               f"({cfg['reference_image']}).")
    return (
        "Use your built-in image generation tool to create exactly one image. "
        "Do not write code, do not draw it with code, and do not edit any other files. "
        f"Save the final image as ./{out_name} in the current directory "
        "(copy the generated file there). "
        f"Aspect: {shape}, {size}.{ref} "
        f"Image: {prompt.rstrip().rstrip('.')}. "
        "Reply with only the saved file path."
    )


def codex_exec_args(model, image_paths, cwd, sandbox):
    args = ["codex", "exec"]
    # -i takes several values, so it goes first and the next flag ends it.
    for p in image_paths:
        args += ["-i", p]
    args += ["--skip-git-repo-check", "-s", sandbox, "-C", cwd]
    if model:
        args += ["-m", model]
    args.append("-")  # prompt comes on stdin
    return args


def collect(out_path, started):
    """Codex may save into the folder itself or only under ~/.codex/generated_images."""
    if os.path.exists(out_path) and os.path.getmtime(out_path) >= started - 1:
        return True
    found = newest_codex_image(started)
    if found:
        shutil.copyfile(found, out_path)
        return True
    return False


def gen_codex_one(image, cfg, model, timeout):
    name = image["name"]
    out_dir = cfg["output_dir"]
    out_path = os.path.join(out_dir, f"{name}.png")
    refs = [cfg["reference_image"]] if image.get("use_reference") and cfg.get("reference_image") else []
    started = time.time()
    try:
        run = subprocess.run(
            codex_exec_args(model, refs, out_dir, "workspace-write"),
            input=image_prompt(image, cfg, f"{name}.png"),
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"  {name}: timed out after {timeout}s")
        return False
    if run.returncode != 0:
        print(f"  {name}: codex exited {run.returncode}: {run.stderr.strip()[-400:]}")
    if collect(out_path, started):
        print(f"  saved {out_path}")
        return True
    print(f"  {name}: Codex finished but no image was found. Last output:\n{run.stdout.strip()[-400:]}")
    return False


# Herdr: one long-lived Codex agent in a sibling pane.

def herdr(*args, check=True):
    run = subprocess.run(["herdr", *args], capture_output=True, text=True)
    if check and run.returncode != 0:
        raise RuntimeError(f"herdr {' '.join(args[:3])} failed: {(run.stderr or run.stdout).strip()[:400]}")
    try:
        return json.loads(run.stdout) if run.stdout.strip() else {}
    except json.JSONDecodeError:
        return {"raw": run.stdout}


def herdr_agent_exists():
    run = subprocess.run(["herdr", "agent", "get", HERDR_AGENT], capture_output=True, text=True)
    return run.returncode == 0


def ensure_herdr_agent(cwd, model):
    if not in_herdr():
        sys.exit("Not running inside Herdr (HERDR_ENV is not 1). Use --backend codex instead.")
    if herdr_agent_exists():
        return
    layout = herdr("pane", "layout", "--pane", os.environ.get("HERDR_PANE_ID", ""), check=False)
    direction = "right"
    try:
        pane = layout["result"]["pane"] if "pane" in layout.get("result", {}) else layout["result"]
        if int(pane.get("width", 200)) < 2 * int(pane.get("height", 50)):
            direction = "down"
    except (KeyError, TypeError, ValueError):
        pass
    split = herdr("pane", "split", "--current", "--direction", direction, "--cwd", cwd, "--no-focus")
    pane_id = split["result"]["pane"]["pane_id"]
    extra = ["--", "-m", model] if model else []
    herdr("agent", "start", HERDR_AGENT, "--kind", "codex", "--pane", pane_id, *extra)
    print(f"Started Codex as '{HERDR_AGENT}' in pane {pane_id}. You can talk to it there too.")


def herdr_prompt(text, timeout_s):
    run = subprocess.run(
        ["herdr", "agent", "prompt", HERDR_AGENT, text, "--wait", "--timeout", str(timeout_s * 1000)],
        capture_output=True, text=True,
    )
    state = (run.stdout + run.stderr)
    if "blocked" in state or "agent_blocked" in state:
        print(f"  Codex is waiting for an approval in the '{HERDR_AGENT}' pane. Approve it there, then re-run.")
        return False
    if run.returncode != 0:
        print(f"  herdr prompt failed: {state.strip()[:400]}")
        return False
    return True


def gen_herdr_one(image, cfg, timeout):
    name = image["name"]
    out_path = os.path.join(cfg["output_dir"], f"{name}.png")
    started = time.time()
    # The agent's cwd may differ from output_dir, so give it the absolute target.
    text = image_prompt(image, cfg, f"{name}.png").replace(f"./{name}.png", out_path)
    if not herdr_prompt(text, timeout):
        return False
    if collect(out_path, started):
        print(f"  saved {out_path}")
        return True
    print(f"  {name}: no image found yet. Check the '{HERDR_AGENT}' pane.")
    return False


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_doctor(a):
    images, secrets = settings(a.ship)
    rows = [
        ("openai", have_openai(secrets), "OPENAI_API_KEY or ship.json secrets.openaiEnv"),
        ("codex", have_codex(), "codex on PATH (log in once with `codex login`)"),
        ("codex-herdr", have_codex() and in_herdr(), "running inside Herdr with codex installed"),
    ]
    for name, ok, how in rows:
        print(f"{'ok ' if ok else '-- '} {name:12} {how}")
    chosen = images.get("backend") or "(not set)"
    print(f"\nship.json images.backend: {chosen}")


def cmd_gen(a):
    images, secrets = settings(a.ship)
    backend = resolve_backend(a.backend, images, secrets)
    cfg = gi.load_config(a.batch)
    if images.get("model") and "model" not in load_json(a.batch):
        cfg["model"] = images["model"]
    os.makedirs(cfg["output_dir"], exist_ok=True)
    pending = [im for im in cfg["images"]
               if not os.path.exists(os.path.join(cfg["output_dir"], f"{im['name']}.png"))]
    print(f"Backend: {backend}  |  {len(pending)} to make, {len(cfg['images']) - len(pending)} already on disk")
    if a.dry_run:
        for im in pending:
            print(f"\n[{im['name']}]\n{image_prompt(im, cfg, im['name'] + '.png')}")
        return

    if backend == "openai":
        if secrets.get("openaiEnv"):
            os.environ.setdefault("SHIPKIT_OPENAI_ENV", secrets["openaiEnv"])
        if images.get("model"):
            gi.DEFAULT_MODEL = images["model"]  # a "model" in the batch still wins
        sys.argv = ["generate_images.py", a.batch]
        gi.main()
        return

    model = images.get("codexModel", "")
    ok = []
    if backend == "codex":
        with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
            ok = list(pool.map(lambda im: gen_codex_one(im, cfg, model, a.timeout), pending))
    else:
        ensure_herdr_agent(cfg["output_dir"], model)
        for im in pending:  # one conversation, so one image at a time
            ok.append(gen_herdr_one(im, cfg, a.timeout))
    print(f"\nGenerated {sum(ok)}/{len(pending)}.")
    gi.post_process(cfg)
    print(f"Output: {cfg['output_dir']}")


def cmd_ask(a):
    images, _ = settings(a.ship)
    if not have_codex():
        sys.exit("ask needs the Codex CLI. Install it and run `codex login`.")
    question = a.question + "\n\nAnswer directly and concisely. Do not edit any files."
    if a.herdr or (images.get("backend") == "codex-herdr" and in_herdr()):
        ensure_herdr_agent(os.getcwd(), images.get("codexModel", ""))
        for p in a.image:
            question += f"\nLook at this image: {os.path.abspath(p)}"
        if herdr_prompt(question, a.timeout):
            print(f"Answered in the '{HERDR_AGENT}' pane. Read it with: herdr agent read {HERDR_AGENT}")
        return
    last = os.path.join(os.getcwd(), ".ship", ".codex-last.txt")
    os.makedirs(os.path.dirname(last), exist_ok=True)
    args = codex_exec_args(images.get("codexModel", ""), a.image, os.getcwd(), "read-only")
    args[-1:-1] = ["-o", last]
    run = subprocess.run(args, input=question, capture_output=True, text=True, timeout=a.timeout)
    if os.path.exists(last):
        print(open(last).read().strip())
        os.remove(last)
    else:
        print(run.stdout.strip()[-2000:] or run.stderr.strip()[-800:])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ship", default=".ship/ship.json", help="path to ship.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    g = sub.add_parser("gen")
    g.add_argument("batch")
    g.add_argument("--backend", choices=BACKENDS)
    g.add_argument("--dry-run", action="store_true", help="print the prompts, make nothing")
    g.add_argument("--jobs", type=int, default=2, help="parallel Codex runs (codex backend)")
    g.add_argument("--timeout", type=int, default=600, help="seconds per image")
    q = sub.add_parser("ask")
    q.add_argument("question")
    q.add_argument("--image", action="append", default=[])
    q.add_argument("--herdr", action="store_true", help="ask the Codex agent in the Herdr pane")
    q.add_argument("--timeout", type=int, default=300)
    a = p.parse_args()
    {"doctor": cmd_doctor, "gen": cmd_gen, "ask": cmd_ask}[a.cmd](a)


if __name__ == "__main__":
    main()
