"""Shared scene runner for the Florida scenes: CLI, takes (one choreography per segment, hard cuts between), cameras,
end card, render or --check dump. Same CLI as ep02:
    python flNN_<slug>.py OUT --frames a-b | --stills a,b --res 540 --samples 8 --assets ASSETS [--check OUT.json]"""
import math
import sys

import bpy
from mathutils import Vector

import fl01_uskit as K
import jx
import motion
import stage

FPS = 30


def cli():
    a = sys.argv
    o = dict(out="frames", res=360, samples=8, assets="assets", frames=None, stills=None, check=None)
    for i, x in enumerate(a):
        if i == 1 and not x.startswith("--"):
            o["out"] = x
        if x == "--res":
            o["res"] = int(a[i + 1])
        if x == "--samples":
            o["samples"] = int(a[i + 1])
        if x == "--assets":
            o["assets"] = a[i + 1]
        if x == "--frames":
            p, q = a[i + 1].split("-")
            o["frames"] = (int(p), int(q))
        if x == "--stills":
            o["stills"] = [int(v) for v in a[i + 1].split(",")]
        if x == "--check":
            o["check"] = a[i + 1]
    return o


class Ep:
    """segs: [(name, dur)] in render order. Times passed to take()/shot() are relative to the segment start."""

    def __init__(self, segs):
        self.start, t = {}, 0.0
        for name, d in segs:
            self.start[name] = (t, t + d)
            t += d
        self.T = t
        self.N = int(round(t * FPS))
        self.shots = jx.Shots(self.N)
        self.takes = {}

    def t(self, seg, rel):
        return self.start[seg][0] + rel

    def take(self, car, seg, path, s0, v0, plan, t0=0.0, t1=None, ind=()):
        """car follows path in [t0, t1) of seg with jx.kinematics(s0, v0, plan); ind: [(side, rel0, rel1)]."""
        a, b = self.start[seg]
        t1 = (b - a) if t1 is None else t1
        n = int(round((t1 - t0) * FPS))
        sv = jx.kinematics(s0, v0, plan, n)
        self.takes.setdefault(car["name"], (car, []))[1].append((int(round((a + t0) * FPS)), path, sv,
                                                                 [(s, a + r0, a + r1) for s, r0, r1 in ind]))
        return sv

    def bake(self, beacon=None):
        """beacon: {car name: [(abs t0, t1)]} light bar on."""
        for name, (car, takes) in self.takes.items():
            track = [dict(x=9000.0 + 30 * len(name), y=0.0, z=0.0, yaw=math.pi / 2, v=0.0, ind=None)
                     for _ in range(self.N)]
            for f0, path, sv, inds in takes:
                wb = 0.55 * car["L"]
                for i, (s, v) in enumerate(sv):
                    f = f0 + i
                    if not 0 <= f < self.N:
                        continue
                    pf, _ = path.at(s + wb / 2)
                    pr, _ = path.at(s - wb / 2)
                    p, _ = path.at(s)
                    d = pf - pr
                    track[f] = dict(x=p.x, y=p.y, z=0.0, yaw=math.atan2(d.y, d.x), v=v, ind=None)
                for side, t0, t1 in inds:
                    for f in range(int(t0 * FPS), min(self.N, int(t1 * FPS))):
                        track[f]["ind"] = side
            for t0, t1 in (beacon or {}).get(name, []):
                for f in range(int(t0 * FPS), min(self.N, int(t1 * FPS))):
                    track[f]["beacon"] = True
            car["rig"] = motion.bake(car["rig"], track)
            car["track"] = [(t["x"], t["y"], 0.0) for t in track]

    def pos(self, car, t):
        f = max(0, min(self.N - 1, int(t * FPS)))
        return Vector(car["track"][f])

    def shot(self, name, lens, seg, r0, r1, fn, up=None):
        a = self.start[seg][0]
        self.shots.add(name, lens, a + r0, a + r1, lambda t: fn(t - a), up_fn=(lambda t: up) if up else None)

    def chase(self, name, car, seg, r0, r1, back=9.0, up=2.6, ahead=25.0, side=-0.6, lens=26):
        """The heading comes from the car's own track inside this segment only: in the last 0.4 s the look-ahead
        point used to fall into the next segment (car parked off-set), which swung the camera sideways into the
        haze for a few frames before the cut (the 'white dissolve' of r3)."""
        a, b = self.start[seg]

        def fn(rt):
            ta = a + rt
            p = self.pos(car, ta)
            if ta + 0.4 < b - 1.0 / FPS:
                d = self.pos(car, ta + 0.4) - p
            else:
                d = p - self.pos(car, max(a, ta - 0.4))
            d = Vector((d.x, d.y, 0.0))
            d = d.normalized() if 0.05 < d.length < 200.0 else Vector((0, 1, 0))
            n = Vector((d.y, -d.x, 0))
            return p - d * back + n * side + Vector((0, 0, up)), p + d * ahead + Vector((0, 0, 0.8))
        self.shot(name, lens, seg, r0, r1, fn)

    def card(self, sign=None, cam=None, tgt=None, seg="END", lens=35.0, frac=0.25, y_px=1150, max_h_px=380):
        """Full-frame end card (as the German episodes): a rendered shot of the episode's real road scene behind the
        end text. sign: the assembly root K.sign returned; the camera stands in front of that Commons sign (turned
        20 degrees towards the road) so the plate is `frac` of the frame width (at most max_h_px tall) with its centre
        at y_px of 1920, below the end lines (y 520..820) and above the source line (y 1395..1480). Without a sign:
        cam and tgt give a fixed shot. A slow 4 % push-in over the card."""
        dur = self.start[seg][1] - self.start[seg][0] + 0.1
        if sign is not None:
            ctr, w, h = sign_box(sign)
            fh = 36.0 / lens                         # frame height per metre of distance (sensor_fit VERTICAL, 36 mm)
            d = w / (frac * fh * 9 / 16)
            d = max(d, h / (max_h_px / 1920.0 * fh))
            n = sign.matrix_world.to_3x3() @ Vector((0, -1, 0))
            n = Vector((n.x, n.y, 0)).normalized()
            best = None
            for a in (0.35, -0.35):                  # the side that puts the camera towards the road's middle
                r = Vector((n.x * math.cos(a) - n.y * math.sin(a), n.x * math.sin(a) + n.y * math.cos(a), 0))
                if best is None or abs((ctr + r * d).x) < abs((ctr + best * d).x):
                    best = r
            dz = (y_px - 960) / 1920.0 * d * fh

            def fn(rt):
                dd = d * (1.0 - 0.013 * rt)
                p = ctr + best * dd + Vector((0, 0, (y_px - 960) / 1920.0 * dd * fh))
                return p, p - best * dd
            self.shot("E_card", lens, seg, 0.0, dur, fn)
            print("END CARD", tuple(round(v, 2) for v in ctr), "w", round(w, 2), "h", round(h, 2), "d", round(d, 2),
                  "dz", round(dz, 2))
            return
        if cam is None:                              # sign file missing: a plain view down the road
            cam, tgt = (0.0, -60.0, 3.0), (0.0, 0.0, 6.0)
        cam, tgt = Vector(cam), Vector(tgt)
        self.shot("E_card", lens, seg, 0.0, dur, lambda rt: (cam + (tgt - cam) * 0.013 * rt, tgt))

    def run(self, o, assets, haze_skip=(), haze=850.0):
        """haze: distance (m) at which the humid Florida air hides 1 - 1/e of a surface; the land and the woods
        fade into the sky colour before the horizon, so there is no hard horizon line."""
        K.light(assets)
        stage.hazify_all(color=(0.68, 0.75, 0.84), dist=haze, skip=haze_skip)
        if o["check"]:
            K.check_dump(o["check"], {"T": self.T, "N": self.N})
            return
        stage.render_setup(o["samples"], o["res"], int(round(o["res"] * 16 / 9)))
        todo = o["stills"] or list(range(o["frames"][0], o["frames"][1] + 1) if o["frames"] else range(1, self.N + 1))
        jx.render_frames(self.shots, o["out"], todo)
        print("RENDER_DONE", o["frames"])


def sign_box(root):
    """(centre, width, height) in world space of the sign plates under an assembly root (the post left out)."""
    bpy.context.view_layer.update()
    pts = []
    stack = list(root.children)
    while stack:
        ob = stack.pop()
        stack += list(ob.children)
        if ob.type == "MESH" and "post" not in ob.name:
            pts += [ob.matrix_world @ Vector(v) for v in ob.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (lo + hi) / 2, max(hi.x - lo.x, hi.y - lo.y), hi.z - lo.z


def freeway_dress(c, lib, fw, seed=5, wall=34.0):
    """Freeway surroundings: sabal palms in front of the sound walls, then behind each wall a frontage road, oaks and
    the ranch-house grid, low buildings and woods out to the haze (K.hinterland), on lawn at kerb height."""
    palms = K.palm_lib(lib, seed=seed)
    for sx in (-1, 1):
        for k, y in enumerate(range(int(fw.y0) + 50, int(fw.y1) - 50, 17)):
            K.instance(palms[k % 3], c, (sx * (26.0 + (k % 3) * 2.2), y, 0.0), k * 1.3, 0.9 + 0.1 * (k % 3), name="palm")
        xa, xb = sorted((sx * (wall + 0.2), sx * 300.0))
        K.rects("fw_back_ground", [(xa, xb, fw.y0 - 400.0, fw.y1 + 400.0)], K.KERB_H - 0.004, K.mats()["grass"], c)
        K.hinterland(c, lib, wall + 2.0, [(fw.y0 - 300.0, fw.y1 + 300.0)], [], sx, seed=seed)
        # verge planting: shrub groups behind the clear zone (30 ft from the travel lane) and oaks along the wall
        import random
        import flora
        rnd = random.Random(seed * 3 + (sx > 0))
        trees = K.tree_groups(lib)
        shrubs, oaks = [], []
        y = fw.y0 + rnd.uniform(0, 20)
        while y < fw.y1:
            for _ in range(rnd.randint(2, 5)):
                shrubs.append((sx * rnd.uniform(fw.x_out + 9.5, fw.x_out + 12.0), y + rnd.uniform(-3, 3), 0.0))
            y += rnd.uniform(18, 40)
        y = fw.y0 + rnd.uniform(0, 15)
        while y < fw.y1:
            oaks.append((sx * rnd.uniform(wall - 3.2, wall - 2.2), y, 0.0))
            y += rnd.uniform(9, 22)
        flora.scatter(f"fw_shrubs_{sx}", shrubs, trees["bush"], c, 0.45, 0.8, seed=seed)
        flora.scatter(f"fw_oaks_{sx}", oaks, trees["decid"], c, 1.0, 1.4, seed=seed + 1)


def dress(c, lib, art, y0, y1, seed=1, skip=(), sides=(-1, 1)):
    """Florida arterial frontage: sabal palms in the grass strip, cobra-head lights, parking lots with parked cars
    (blank plates) and plain strip-mall shops behind them. skip: [(ya, yb)] kept clear (a crossing)."""
    import random
    rnd = random.Random(seed)
    palms = K.palm_lib(lib, seed=seed)
    cars = [K.us_car(k, col, f"parked_{i}", lib) for i, (k, col) in enumerate(
        (("hatch", (0.5, 0.05, 0.04)), ("suv", (0.7, 0.71, 0.72)), ("estate", (0.08, 0.15, 0.35)),
         ("saloon", (0.88, 0.88, 0.86)), ("van", (0.92, 0.92, 0.9))))]
    free = [(y0, y1)]
    for a, b in skip:
        free = [q for (u, v) in free for q in ((u, min(v, a)), (max(u, b), v)) if q[1] - q[0] > 25]
    # local streets reach the arterial's frontage through gaps between the mall buildings (every 220 to 300 m)
    cross = []
    for a, b in free:
        y = a + rnd.uniform(140, 240)
        while y < b - 110:
            cross.append(y)
            y += rnd.uniform(220, 300)
    for sx in sides:
        x_lot = art.lip + 0.15 + 2.2 + K.WALK + 3.0
        x_back = x_lot + 21.5 + 14.0
        for k, (a, b) in enumerate(free):
            xa, xb = sorted((sx * x_lot, sx * (x_lot + 20.3)))
            K.parking_lot(c, xa, xb, a + 4, b - 4, cars=cars, seed=seed + k + (sx > 0) * 10)
            cuts = [a + 2] + [q for ys in cross if a < ys < b for q in (ys - 11.0, ys + 11.0)] + [b - 2]
            for j in range(0, len(cuts), 2):
                K.strip_mall(c, sx * (x_lot + 21.5), cuts[j], cuts[j + 1], side=sx, seed=seed + k * 3 + j + (sx > 0))
            for ys in cross:
                if a < ys < b:
                    xa, xb = sorted((sx * (x_lot + 20.3), sx * x_back))
                    K.rects("mall_drive", [(xa, xb, ys - 4.0, ys + 4.0)], K.KERB_H + 0.004, K.mats()["asphalt_lot"], c,
                            uv=True)
            y = a + rnd.uniform(4, 9)
            while y < b - 4:
                K.instance(rnd.choice(palms), c, (sx * (art.lip + 1.25), y, K.KERB_H), rnd.uniform(0, 6.28),
                           rnd.uniform(0.85, 1.15), name="palm")
                y += rnd.uniform(14, 22)
            y = a + 10
            while y < b - 4:
                K.street_light(c, sx * (art.lip + 0.75), y, side=sx)
                y += 48.0
        K.hinterland(c, lib, x_back, free, cross, sx, seed=seed)
        # the corners of a signalised crossing (kept clear of malls): oaks, and a stand-alone low building when the
        # corner is long enough, so a drone shot over the crossing sees no bare lawn
        import flora
        oaks = []
        for a, b in skip:
            yc = art.cross if art.cross is not None else (a + b) / 2
            for q0, q1 in ((a + 4.0, yc - art.B - 13.0), (yc + art.B + 13.0, b - 4.0)):
                if q1 - q0 < 8.0:
                    continue
                if q1 - q0 > 40.0:
                    d = min(36.0, q1 - q0 - 16.0)
                    K.low_building(c, sx * (x_lot + 26.5), (q0 + q1) / 2, 18.0, d, 5.5, rnd, name="corner_bldg")
                    xa, xb = sorted((sx * (x_lot + 7.5), sx * (x_lot + 17.0)))
                    K.rects("corner_lot", [(xa, xb, q0, q1)], K.KERB_H + 0.004, K.mats()["asphalt_lot"], c, uv=True)
                y = q0 + 2.0
                while y < q1:
                    oaks.append((sx * rnd.uniform(x_lot + 2.0, x_lot + 7.0), y, K.KERB_H))
                    y += rnd.uniform(7.0, 11.0)
        if oaks:
            flora.scatter(f"corner_oaks_{sx}", oaks, K.tree_groups(lib)["decid"], c, 0.9, 1.3, seed=seed)
