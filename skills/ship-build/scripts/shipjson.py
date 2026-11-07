#!/usr/bin/env python3
"""Read and write .ship/ship.json and resolve App Store Connect credentials.

  shipjson.py get app.bundleId            print a value (empty string if unset)
  shipjson.py set build.lastBuildNumber 12   write a value (creates objects)
  shipjson.py asc-env                      print the path of the ASC env file (never its contents)

--file defaults to ./.ship/ship.json. Defaults from ~/.config/shipkit/defaults.json
are used for any key missing in ship.json. Never prints secret values.
"""
import json, os, sys


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def dig(d, dotted):
    for k in dotted.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def defaults():
    return load(os.path.expanduser("~/.config/shipkit/defaults.json"))


def get(path, key):
    v = dig(load(path), key)
    if v in (None, ""):
        v = dig(defaults(), key)
    return v


def parse_env(path):
    """Parse KEY=value lines without executing anything. Returns a dict."""
    out = {}
    try:
        with open(os.path.expanduser(path)) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:]
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def asc_env_path(path):
    p = get(path, "secrets.ascEnv")
    if isinstance(p, str) and ":" in p and not os.path.exists(os.path.expanduser(p)):
        p = p.split(":")[0]
    return os.path.expanduser(p) if p else ""


def asc_credentials(path):
    """Return (key_id, issuer, key_path) from the env file; empty strings if missing."""
    env = parse_env(asc_env_path(path)) if asc_env_path(path) else {}
    for k in ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_PATH"):
        env.setdefault(k, os.environ.get(k, ""))
    return env["ASC_KEY_ID"], env["ASC_ISSUER_ID"], os.path.expanduser(env["ASC_KEY_PATH"])


def set_key(path, key, value):
    d = load(path)
    cur = d
    parts = key.split(".")
    for k in parts[:-1]:
        cur = cur.setdefault(k, {})
    try:
        value = json.loads(value)
    except ValueError:
        pass
    cur[parts[-1]] = value
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
        f.write("\n")


def main():
    a = sys.argv[1:]
    path = "./.ship/ship.json"
    if "--file" in a:
        i = a.index("--file")
        path = a[i + 1]
        del a[i:i + 2]
    if not a:
        sys.exit(__doc__)
    if a[0] == "get" and len(a) == 2:
        v = get(path, a[1])
        if isinstance(v, (dict, list)):
            print(json.dumps(v))
        elif isinstance(v, bool):
            print("true" if v else "false")
        else:
            print("" if v is None else v)
    elif a[0] == "set" and len(a) == 3:
        set_key(path, a[1], a[2])
    elif a[0] == "asc-env":
        print(asc_env_path(path))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
