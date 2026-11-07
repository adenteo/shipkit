#!/usr/bin/env python3
"""PNG helpers with no required dependencies.

  pngtool.py info  file.png [...]     print WxH and whether there is an alpha channel
  pngtool.py flat  file.png [...]     remove the alpha channel in place (App Store rejects alpha)

flat tries, in order: Pillow, sips (macOS, lossless via BMP), ImageMagick, then a slow
pure-Python rewrite of 8-bit RGBA PNGs.
"""
import os, shutil, struct, subprocess, sys, tempfile, zlib


def info(path):
    """Return (width, height, has_alpha) or None if not a PNG."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h, _depth, ctype = struct.unpack(">IIBB", data[16:26])
    return w, h, ctype in (4, 6) or b"tRNS" in data


def _pil(path):
    from PIL import Image
    im = Image.open(path)
    bg = Image.new("RGB", im.size, (255, 255, 255))
    im = im.convert("RGBA")
    bg.paste(im, mask=im.split()[3])
    bg.save(path, optimize=False)


def _sips(path):
    if not shutil.which("sips"):
        raise RuntimeError("no sips")
    d = tempfile.mkdtemp()
    try:
        bmp, out = os.path.join(d, "a.bmp"), os.path.join(d, "a.png")
        subprocess.run(["sips", "-s", "format", "bmp", path, "--out", bmp], check=True, capture_output=True)
        subprocess.run(["sips", "-s", "format", "png", bmp, "--out", out], check=True, capture_output=True)
        i = info(out)
        if not i or i[2]:
            raise RuntimeError("sips kept alpha")
        shutil.move(out, path)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _magick(path):
    exe = shutil.which("magick") or shutil.which("convert")
    if not exe:
        raise RuntimeError("no imagemagick")
    subprocess.run([exe, path, "-background", "white", "-alpha", "remove", "-alpha", "off", path], check=True)


def _pure(path):
    with open(path, "rb") as f:
        data = f.read()
    w, h, depth, ctype, _c, _f, interlace = struct.unpack(">IIBBBBB", data[16:29])
    if depth != 8 or ctype != 6 or interlace:
        raise RuntimeError("pure-python path only handles 8-bit non-interlaced RGBA")
    pos, idat = 8, b""
    while pos < len(data):
        n, t = struct.unpack(">I4s", data[pos:pos + 8])
        if t == b"IDAT":
            idat += data[pos + 8:pos + 8 + n]
        pos += 12 + n
    raw = zlib.decompress(idat)
    stride, bpp = w * 4, 4
    prev = bytearray(stride)
    out = bytearray()
    p = 0
    for _ in range(h):
        ft = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        prev = line
        row = bytearray()
        for i in range(0, stride, 4):
            a = line[i + 3]
            if a == 255:
                row += line[i:i + 3]
            else:
                row += bytes((line[i + k] * a + 255 * (255 - a)) // 255 for k in range(3))
        out += b"\x00" + row

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(bytes(out), 6)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def flatten(path):
    i = info(path)
    if i is None:
        raise RuntimeError(f"{path} is not a PNG")
    if not i[2]:
        return
    for fn in (_pil, _sips, _magick, _pure):
        try:
            fn(path)
        except Exception:
            continue
        j = info(path)
        if j and not j[2]:
            return
    raise RuntimeError(f"could not remove alpha from {path}")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("info", "flat"):
        sys.exit(__doc__)
    for p in sys.argv[2:]:
        if sys.argv[1] == "info":
            i = info(p)
            print(f"{p}: {i[0]}x{i[1]} alpha={'yes' if i[2] else 'no'}" if i else f"{p}: not a PNG")
        else:
            flatten(p)
