"""Measure the lit lamps in ld_lamps.py stills (plain python with Pillow, no Blender):
    python3 lookdev/lamps_measure.py DIR [LOG ...]
DIR holds f_NNNN.png (or <job>_f_NNNN.png with --prefix=<job>_); the LAMP lines come from the job logs (the
runner's logs/<job>_c<k>.txt or a local run's stdout). For every lamp box the inner part (INSET of the width and height
in from each side, so the housing rim and the body around the lens stay out; at least the middle pixel) is averaged and reported as display hue (deg), saturation and value; lit parts are marked: brake
(taillight, brake3 on rear views), the left indicator on rear views, the right indicator on front views."""
import colorsys
import glob
import os
import re
import sys

from PIL import Image

LINE = re.compile(r"LAMP f=(\d+) car=(\S+) part=(\S+) mat=(\S+) box=(-?\d+),(-?\d+),(-?\d+),(-?\d+) facing=(\S+)")


INSET = 0.2


def avg(im, box):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    ix0, iy0 = int(round(x0 + w * INSET)), int(round(y0 + h * INSET))
    ix1, iy1 = max(ix0 + 1, int(round(x1 - w * INSET))), max(iy0 + 1, int(round(y1 - h * INSET)))
    ix0, iy0 = max(0, ix0), max(0, iy0)
    ix1, iy1 = min(im.width, ix1), min(im.height, iy1)
    px = [im.getpixel((x, y)) for x in range(ix0, ix1) for y in range(iy0, iy1)]
    if not px:
        return None
    r, g, b = (sum(p[k] for p in px) / len(px) for k in range(3))
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    h *= 360
    return (r, g, b), (h - 360 if h > 180 else h), s, v, len(px)      # red as -5..5, not 355..5


# traffic frame (ld_lamps.py lanes): t0..t2 drive away braking, t0 indicates left, t1 and t3 right
TRAFFIC_IND = {"t0": "dl_ind_L", "t1": "dl_ind_R", "t3": "dl_ind_R"}


def lit(f, car, part, mat, n_kinds=3):
    rear = f <= 2 * n_kinds and f % 2 == 1
    front = f <= 2 * n_kinds and f % 2 == 0
    t = car.split("_")[0] if f == 2 * n_kinds + 1 else None
    if part in ("taillight", "brake3"):
        return rear or (t in ("t0", "t1", "t2"))
    if part == "indicator":
        return (rear and mat == "dl_ind_L") or (front and mat == "dl_ind_R") or TRAFFIC_IND.get(t) == mat
    return False


def main():
    d = sys.argv[1]
    prefix = ""
    logs = []
    for x in sys.argv[2:]:
        if x.startswith("--prefix="):
            prefix = x.split("=", 1)[1]
        else:
            logs += glob.glob(x)
    rows = []
    for lg in logs:
        for ln in open(lg, errors="replace"):
            m = LINE.search(ln)
            if m:
                rows.append(m.groups())
    seen = set()
    for f, car, part, mat, x0, y0, x1, y1, fac in rows:
        k = (f, car, part, mat, x0, y0)
        if k in seen:
            continue
        seen.add(k)
        fp = os.path.join(d, f"{prefix}f_{int(f):04d}.png")
        if not os.path.exists(fp):
            continue
        im = Image.open(fp).convert("RGB")
        res = avg(im, (int(x0), int(y0), int(x1), int(y1)))
        if res is None:
            continue
        (r, g, b), h, s, v, n = res
        tag = "LIT" if lit(int(f), car, part, mat) else "off"
        print(f"{prefix}f{int(f):02d} {car:10s} {part:9s} {mat:9s} {tag} rgb {r:3.0f} {g:3.0f} {b:3.0f}  hue {h:5.1f}  "
              f"sat {s:.2f}  val {v:.2f}  px {n}")


main()
