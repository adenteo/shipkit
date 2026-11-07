#!/usr/bin/env python3
"""Headless state sheets for the Rive UI pieces.

The CLI can set view-model data but not legacy state-machine inputs, so each case rewrites
the inputs' DEFAULT values in a temporary copy of scene.rml (a machine reads them on its
first advance, exactly as the app's setInput before play), renders the artboard after each
--advance, and lays the frames out in one labelled sheet.

    from shoot import sheet
    sheet(proj, 'TabHome', 'out.png', [('selected', {'selected': True}, [0, 100, 200, 400, 1200])])
"""
import os, re, shutil, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont

RIVE = shutil.which('rive') or os.path.expanduser('~/.rive/bin/rive')


def _scene(src, artboard, inputs, bg):
    for k, v in inputs.items():
        val = str(v).lower() if isinstance(v, bool) else str(v)
        src, n = re.subn(rf'(<StateMachine(?:Bool|Number) name="{k}" value=")[^"]*"', rf'\g<1>{val}"', src)
        assert n, f'no input {k}'
    if bg:
        def inject(m):
            ab = m.group(0)
            if f'name="{artboard}"' not in ab.split('>')[0]:
                return ab
            w = float(re.search(r'width="([\d.]+)"', ab).group(1)); h = float(re.search(r'height="([\d.]+)"', ab).group(1))
            rect = (f'<Shape x="{w/2}" y="{h/2}" name="ShootBG"><Rectangle width="{w*3}" height="{h*3}" name="P"/>'
                    f'<Fill name="F"><SolidColor colorValue="{bg}" name="C"/></Fill></Shape>')
            return ab.replace('<StateMachine ', rect + '<StateMachine ', 1)
        src = re.sub(r'<Artboard .*?</Artboard>', inject, src, flags=re.S)
    return src


def frame(proj, artboard, inputs, ms, size, bg='FFF4F8FA'):
    src = open(os.path.join(proj, 'scene.rml')).read()
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, 'scene.rml'), 'w').write(_scene(src, artboard, inputs, bg))
    open(os.path.join(tmp, 'rive.yaml'), 'w').write('name: Shoot\n')
    # image assets referenced by relative path (painted layers in art/)
    for d in ('art',):
        if os.path.isdir(os.path.join(proj, d)):
            os.symlink(os.path.abspath(os.path.join(proj, d)), os.path.join(tmp, d))
    p = os.path.join(tmp, 'x.png')
    adv = [f'--advance={ms}ms'] if ms else ['--advance=1']
    r = subprocess.run([RIVE, tmp, '--quiet', f'--screenshot={p}', f'--artboard={artboard}',
                        f'--viewport={size[0]}x{size[1]}', '--fit=contain', *adv], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stdout + r.stderr)
    im = Image.open(p).convert('RGB')
    shutil.rmtree(tmp, ignore_errors=True)
    return im


def sheet(proj, artboard, out, cases, size=(240, 240), bg='FFF4F8FA'):
    jobs = [(label, inputs, ms) for label, inputs, times in cases for ms in times]
    with ThreadPoolExecutor(6) as ex:
        ims = list(ex.map(lambda j: frame(proj, artboard, j[1], j[2], size, bg), jobs))
    cols = max(len(t) for _, _, t in cases)
    pad, lab = 8, 22
    W = cols * (size[0] + pad) + pad + 150
    H = len(cases) * (size[1] + lab + pad) + pad
    o = Image.new('RGB', (W, H), (255, 255, 255))
    d = ImageDraw.Draw(o)
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 15)
    except Exception:
        font = ImageFont.load_default()
    k = 0
    for r, (label, inputs, times) in enumerate(cases):
        y = pad + r * (size[1] + lab + pad)
        d.text((pad, y + size[1] // 2), label, fill=(30, 30, 40), font=font)
        for c, ms in enumerate(times):
            x = 150 + pad + c * (size[0] + pad)
            o.paste(ims[k], (x, y)); k += 1
            d.text((x + 4, y + size[1] + 3), f'{ms} ms', fill=(120, 110, 105), font=font)
    o.save(out)
    return out
