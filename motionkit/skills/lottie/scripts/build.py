#!/usr/bin/env python3
"""Build Lottie examples (or your own animation files) to JSON.

    python3 build.py ../examples/bell.py ../examples/loading_heart.py --out /tmp/lottie

Each file must define `build()` returning a lottie_kit.Comp. Validates, prunes keys, rounds,
writes <out>/<comp name>.json and prints frames, seconds, size and layers.
"""
import argparse, importlib.util, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lottie_kit as lk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--out', default='build')
    a = ap.parse_args()
    for f in a.files:
        spec = importlib.util.spec_from_file_location(os.path.basename(f)[:-3], f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        lk.STYLE['ink'] = 1.0
        lk.write(mod.build(), a.out)


if __name__ == '__main__':
    main()
