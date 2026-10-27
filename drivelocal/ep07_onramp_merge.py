"""Drive Like a Local #7, Germany (standard): don't merge onto the Autobahn like this. The through carriageway has
priority (StVO § 18 Abs. 3): build up to traffic speed along the whole acceleration lane, indicate, merge into a gap.
Set: kit/interchange.py (RQ 36, loop R 45 m, acceleration lane 250 m plus 60 m taper, Einfahrt line 6 / 6 m,
Commons 330.1 at the ramp start), SUMO background traffic (traffic/interchange_day.json.gz via kit/traffic.py) with
every vehicle that would cross the choreography removed. Heroes are hand-choreographed through motion.bake: white
rental hatchback, dark saloon, 40 t artic. Canonical timeline (English order; ep07_edit.json cuts each language):
HOOK 0-2.2, SITUATION 2.2-12.2, RULE 12.2-19.2, COST 19.2-23.7, CORRECT 23.7-30.2, END 30.2-32.9.
Run: python ep07_onramp_merge.py OUTDIR --frames 1-987 --res 540 --samples 8 --assets ASSETS [--stills 40,300]
     python ep07_onramp_merge.py --check     (plain python: choreography and traffic filter checks, no Blender)
"""
# ==== a3 common: the same block in ep07, ep11 and ep21 (Autobahn interchange episodes) ====
import gzip
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit")]
import interchange as IC  # noqa: E402  (spec part is plain python)

OUT, RES, SAMPLES, ASSETS, FR, STILLS, CHECK = "frames", 540, 8, "assets", None, None, False
_a = sys.argv
for _i, _x in enumerate(_a):
    if _i == 1 and not _x.startswith("--"):
        OUT = _x
    if _x == "--res":
        RES = int(_a[_i + 1])
    if _x == "--samples":
        SAMPLES = int(_a[_i + 1])
    if _x == "--assets":
        ASSETS = _a[_i + 1]
    if _x == "--frames":
        _p, _q = _a[_i + 1].split("-")
        FR = (int(_p), int(_q))
    if _x == "--stills":
        STILLS = [int(v) for v in _a[_i + 1].split(",")]
    if _x == "--check":
        CHECK = True
FPS = 30
DT = 1.0 / FPS
XL, XM, XR, XA = 4.625, 8.375, 12.125, 16.175   # lane centres northbound: left, middle, right, exit / merge lane
NORTH = math.pi / 2
HIDE_Z = -1000.0
TRACK_FILE = next(p for p in (os.path.join(HERE, "traffic", "interchange_day.json.gz"),
                              os.path.join(HERE, "..", "traffic", "interchange_day.json.gz")) if os.path.exists(p))
sm = IC.smooth5


class Timeline:
    """Segments back to back on the canonical (English) timeline."""

    def __init__(self, segs):
        self.order, self.span, t = [], {}, 0.0
        for k, d in segs:
            self.order.append(k)
            self.span[k] = (t, t + d)
            t += d
        self.T = t
        self.N = int(round(t * FPS))

    def a(self, seg, rel=0.0):
        return self.span[seg][0] + rel

    def f(self, seg, rel=0.0):          # scene frame (1-based)
        return int(round((self.span[seg][0] + rel) * FPS)) + 1

    def n(self, seg):
        return int(round(self.span[seg][1] * FPS)) - int(round(self.span[seg][0] * FPS))


def vprof(keys):
    """Speed v(t) (m/s) linear between keys [(t, v)], constant outside."""
    def v(t):
        if t <= keys[0][0]:
            return keys[0][1]
        for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
            if t <= t1:
                return v0 + (v1 - v0) * (t - t0) / max(1e-6, t1 - t0)
        return keys[-1][1]
    return v


def lane(x0, *moves):
    """Lateral position over time: start at x0, then each (t0, dur, x1) moves there on a smooth5 curve."""
    def f(t):
        x = x0
        for t0, dur, x1 in moves:
            x = x + (x1 - x) * sm((t - t0) / dur)
        return x
    return f


def ind(*spans):
    """Indicator per time: spans [(t0, t1, 'L' | 'R' | 'H')]."""
    return lambda t: next((s for t0, t1, s in spans if t0 <= t < t1), None)


def MAIN(s):
    """Northbound main line as a path: arc length = y, lateral offset = x (right of travel)."""
    return 0.0, s, 0.0, NORTH


def poly_path(pts):
    P = IC.Poly(pts)
    return P.at, P


def run(n, path, s0, v, lat=lambda t: 0.0, ind_fn=lambda t: None, t0=0.0, extra=None):
    """Rows for n frames: arc length from s0 with speed v(t), lateral offset lat(t) (right of travel), indicator.
    t runs from t0 (segment-relative seconds of the first frame). yaw and v are derived from the positions."""
    ss, s = [], s0
    for i in range(n):
        t = t0 + i * DT
        ss.append(s)
        s += 0.5 * (v(t) + v(t + DT)) * DT
    pts = []
    for i, s in enumerate(ss):
        t = t0 + i * DT
        px, py, pz, h = path(s)
        d = lat(t)
        pts.append((px + math.sin(h) * d, py - math.cos(h) * d, pz))
    rows = rows_from_pts(pts, t0, ind_fn, extra)
    for i, r in enumerate(rows):
        # brake lamps follow the driver's speed, not the lateral part of a lane change (motion.bake reads "v")
        r["v"] = v(t0 + i * DT)
    return rows


def rows_from_pts(pts, t0=0.0, ind_fn=lambda t: None, extra=None):
    """Track rows from per-frame positions: yaw and speed from central differences."""
    n = len(pts)
    rows = []
    for i, (x, y, z) in enumerate(pts):
        a, b = pts[max(0, i - 1)], pts[min(n - 1, i + 1)]
        if i == 0 or i == n - 1:
            a, b = (pts[0], pts[1]) if i == 0 else (pts[-2], pts[-1])
            k = 1.0
        else:
            k = 2.0
        yaw = math.atan2(b[1] - a[1], b[0] - a[0])
        vv = math.hypot(b[0] - a[0], b[1] - a[1]) / (k * DT)
        r = dict(x=x, y=y, z=z, yaw=yaw, v=vv, ind=ind_fn(t0 + i * DT))
        if extra:
            r.update(extra(t0 + i * DT))
        rows.append(r)
    return rows


def concat(*parts):
    out = []
    for p in parts:
        out += p
    return out


class Hero:
    """A choreographed vehicle: model key (stage.fleet or HERO_MODELS), length, rows per segment."""

    def __init__(self, name, model, L):
        self.name, self.model, self.L, self.segs, self.full = name, model, L, {}, None

    def build(self, tl):
        out, last = [], (0.0, IC.Y_START)
        for k in tl.order:
            n = tl.n(k)
            rows = self.segs.get(k)
            if rows:
                assert len(rows) >= n, (self.name, k, len(rows), n)
                out += rows[:n]
                last = (rows[n - 1]["x"], rows[n - 1]["y"])
            else:
                out += [dict(x=last[0], y=last[1], z=HIDE_Z, yaw=NORTH, v=0.0, ind=None) for _ in range(n)]
        self.full = out
        return out

    def at(self, t):
        r = self.full[max(0, min(len(self.full) - 1, int(round(t * FPS))))]
        return r["x"], r["y"], r["z"]

    def on(self, f):
        r = self.full[f - 1]
        return None if r["z"] < -500 else r


def load_traffic():
    with gzip.open(TRACK_FILE, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def stretch(v, w0, n, rate):
    """A vehicle's rows from data frame w0 played at `rate` (0.5 = half speed) for n frames, renumbered w0..."""
    rows = {r[0]: r for r in v["track"]}
    zs = {r[0]: z for r, z in zip(v["track"], v.get("z") or [0.0] * len(v["track"]))}
    out, oz = [], []
    for k in range(n):
        fx = w0 + k * rate
        a, b = int(math.floor(fx)), int(math.floor(fx)) + 1
        if a not in rows or b not in rows:
            continue
        u = fx - a
        ra, rb = rows[a], rows[b]
        dyaw = (rb[3] - ra[3] + math.pi) % (2 * math.pi) - math.pi
        out.append([w0 + k, ra[1] + (rb[1] - ra[1]) * u, ra[2] + (rb[2] - ra[2]) * u, ra[3] + dyaw * u,
                    (ra[4] + (rb[4] - ra[4]) * u) * rate, ra[5] if u < 0.5 else rb[5]])
        oz.append(zs[a] + (zs[b] - zs[a]) * u)
    return dict(v, track=out, z=oz)


def pick(data, tl, seg, w0, heroes, box, excl=None, rate=1.0, margin=8.0):
    """SUMO vehicles for one segment: data frames w0.. land on the segment's scene frames. Kept when a row lies in
    box (x0, x1, y0, y1); dropped when any row comes near a hero present at that frame (same or overlapping lane,
    closer than both half lengths plus `margin`) or matches excl(t_rel, x, y)."""
    f0, n = tl.f(seg), tl.n(seg)
    inside = box if callable(box) else (lambda x, y: box[0] < x < box[1] and box[2] < y < box[3])
    kept = []
    for v in data["vehicles"]:
        if rate != 1.0:
            v = stretch(v, w0, n, rate)
        rows = [r for r in v["track"] if w0 <= r[0] < w0 + n]
        if len(rows) < 2 or not any(inside(r[1], r[2]) for r in rows):
            continue
        L = 16.5 if v["kind"] == "truck" else (5.2 if v["kind"] == "van" else 4.7)
        bad = False
        for r in rows:
            F = r[0] - w0 + f0
            t = (r[0] - w0) * DT
            if excl and excl(t, r[1], r[2]):
                bad = True
                break
            for h in heroes:
                hr = h.on(F)
                if hr and abs(hr["x"] - r[1]) < 3.0 and abs(hr["y"] - r[2]) < (h.L + L) / 2 + margin:
                    bad = True
                    break
            if bad:
                break
        if not bad:
            kept.append(v)
    return kept


def around(rows, back=250.0, ahead=450.0, x0=-25.0, x1=45.0, step=25.0):
    """Region (callable) of the stations within [back, ahead] metres of the given hero rows: keeps the traffic to
    what the cameras of that segment can see."""
    bins = set()
    for r in rows:
        if r["z"] > -500:
            for k in range(int((r["y"] - back) // step), int((r["y"] + ahead) // step) + 1):
                bins.add(k)
    return lambda x, y: x0 < x < x1 and int(y // step) in bins


def check(tl, heroes, plan, data):
    """Plain-python sanity report: closest approach between heroes, lorries off the left lane, indicator before
    every lateral move, kept traffic per segment."""
    ok = True
    for i, a in enumerate(heroes):
        for b in heroes[i + 1:]:
            best = (1e9, 0)
            for f in range(1, tl.N + 1):
                ra, rb = a.on(f), b.on(f)
                if ra and rb and abs(ra["x"] - rb["x"]) < 2.2:
                    gap = abs(ra["y"] - rb["y"]) - (a.L + b.L) / 2
                    best = min(best, (gap, f))
            if best[0] < 1e8:
                print(f"gap {a.name}-{b.name}: {best[0]:.1f} m at frame {best[1]}")
                ok = ok and best[0] > 1.5
    for h in heroes:
        if h.model.startswith("t_"):
            left = [f for f in range(1, tl.N + 1) if h.on(f) and h.on(f)["x"] < 6.6 and h.on(f)["y"] > IC.Y_START]
            print(f"{h.name} frames in the left lane: {len(left)}")
            ok = ok and not left
        moved = 0
        for f in range(2, tl.N + 1):
            r, p = h.on(f), h.on(f - 1)
            lane_of = lambda q: int((q["x"] - 2.75) // 3.75)      # noqa: E731  0 left .. 3 merge / exit lane
            if (r and p and lane_of(r) != lane_of(p) and abs(r["yaw"] - NORTH) < 0.4 and r["y"] > IC.MERGE - 5
                    and 2.75 < r["x"] < 18.6 and abs(r["y"] - p["y"]) < 3.0):
                window = [h.on(g) for g in range(max(1, f - 45), f + 1)]
                if not any(w and w["ind"] for w in window):
                    moved += 1
        print(f"{h.name}: lateral frames without an indicator in the 1.5 s before: {moved}")
    for seg, kept in plan.items():
        lorries_left = sum(1 for v in kept if v["kind"] == "truck" for r in v["track"]
                           if (IC.main_lane(r[1], r[2]) or (0, 9))[1] == 0)
        print(f"traffic {seg}: {len(kept)} vehicles, lorry rows in a left lane (either carriageway): {lorries_left}")
        ok = ok and not lorries_left
    print("CHECK", "OK" if ok else "FAILED")
    return ok


# ---------------------------------------------------------------- Blender side (imported only when rendering)
HERO_MODELS = {}      # key: (kind, colour, plate)


def blender_imports():
    global bpy, Vector, jx, motion, SG, stage, TR, V, W
    import bpy  # noqa: F401
    from mathutils import Vector  # noqa: F401
    import jx  # noqa: F401
    import motion  # noqa: F401
    import signs as SG  # noqa: F401
    import stage  # noqa: F401
    import traffic as TR  # noqa: F401
    import vehicles as V  # noqa: F401
    import world as W  # noqa: F401


def build_scene():
    """kit/interchange.build with the episode's hero models added to the fleet (built first, as vehicles.md asks);
    stage.fleet is wrapped for this call only, the module is not changed."""
    _fleet = stage.fleet

    def fleet_plus(lib):
        cars, vans, trucks = _fleet(lib)
        for k, (kind, col, plate) in HERO_MODELS.items():
            cars[k] = V.make(kind, k, col, plate, c=lib)
        return cars, vans, trucks
    stage.fleet = fleet_plus
    try:
        S = IC.build(ASSETS)
    finally:
        stage.fleet = _fleet
    return S


def needed(tl, seg):
    a, b = tl.f(seg), tl.f(seg) + tl.n(seg) - 1
    if STILLS:
        return any(a - 2 <= f <= b + 2 for f in STILLS)
    if FR:
        return not (b < FR[0] or a > FR[1])
    return True


def drive(S, h, beacon=None):
    r = motion.rig(S["fleet"][h.model], c=S["traffic"])
    r.obj.name = "hero_" + h.name
    tr = [dict(rw) for rw in h.full]
    if beacon:
        for i, rw in enumerate(tr):
            rw["beacon"] = beacon(i + 1)
    motion.bake(r, tr, night=False)
    return r


def play(S, data, tl, seg, w0, kept, rate=1.0):
    if not kept or not needed(tl, seg):
        return []
    sub = dict(data, vehicles=kept)
    fleet = {k: c for k, c in S["fleet"].items() if k not in HERO_MODELS}
    f0 = tl.f(seg)
    return TR.play(sub, fleet, S["traffic"], frames=(w0, w0 + tl.n(seg) - 1), offset=f0 - w0)


def keys_vis(o, windows):
    """Visible only inside the (t_on, t_off) windows (absolute seconds)."""
    o.hide_render = True
    o.keyframe_insert("hide_render", frame=1)
    for t_on, t_off in windows:
        o.hide_render = False
        o.keyframe_insert("hide_render", frame=int(t_on * FPS) + 1)
        o.hide_render = True
        o.keyframe_insert("hide_render", frame=int(t_off * FPS) + 1)


def pop(root, windows, size=1.0):
    keys = [(1, 0.0)]
    for t_on, t_off in windows:
        f_on, f_off = int(t_on * FPS) + 1, int(t_off * FPS) + 1
        keys += [(f_on, 0.0), (f_on + 4, 1.18 * size), (f_on + 7, size), (f_off, size), (f_off + 5, 0.0)]
    for f, s in keys:
        root.scale = (s, s, s)
        root.keyframe_insert("scale", frame=f)


def strip(S, name, pts, width_fn, color, windows, z=0.035, emit=2.2, alpha=0.5):
    """Glowing translucent band over the road along pts [(x, y)], width_fn(i) metres wide (rule highlights)."""
    m = jx.flat_mat(name, color, emit=emit, alpha=alpha)
    verts, faces = [], []
    for i, (x, y) in enumerate(pts):
        a, b = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
        h = math.atan2(b[1] - a[1], b[0] - a[0])
        w = width_fn(i) / 2
        verts += [(x + math.sin(h) * w, y - math.cos(h) * w, z), (x - math.sin(h) * w, y + math.cos(h) * w, z)]
        if i:
            faces.append((2 * i - 2, 2 * i - 1, 2 * i + 1, 2 * i))
    o = W.mesh_obj(name, verts, faces, m, S["env"])
    o.visible_shadow = False
    keys_vis(o, windows)
    return o


def callout(S, sid, loc, windows, width=2.6, tilt=0.0, rz=0.0, emit=0.6, name=None):
    """A Commons sign (kit/signs.py, unaltered) shown big as a call-out: tilt -pi/2 lies flat facing up (top view,
    screen up = +y); tilt 0 stands facing -y (towards northbound traffic and the chase cameras)."""
    root = bpy.data.objects.new(name or f"callout_{sid}", None)
    S["env"].objects.link(root)
    f = SG.face(sid, S["env"], width, S["builder"].sign_set(sid), name=(name or f"callout_{sid}") + "_face",
                emit=emit)
    f.parent = root
    f.location = (0, 0, -f["height"] / 2)
    for o in (f, *f.children):
        o.visible_shadow = False
    root.location = loc
    root.rotation_euler = (tilt, 0, rz)
    pop(root, windows)
    return root


def cross(S, loc, windows, size=1.0, name="xcross"):
    root = bpy.data.objects.new(name, None)
    S["env"].objects.link(root)
    root.location = loc
    red = jx.flat_mat(name + "_red", (1.0, 0.05, 0.05), emit=2.5)
    white = jx.flat_mat(name + "_white", (1, 1, 1), emit=1.5)
    for k, ang in enumerate((math.pi / 4, -math.pi / 4)):
        for nm, w_, l_, m_, z_ in (("w", 0.75, 3.5, white, 0.0), ("r", 0.5, 3.2, red, 0.01)):
            o = W.mesh_obj(f"{name}_{nm}{k}", [(-l_ / 2, -w_ / 2, z_), (l_ / 2, -w_ / 2, z_), (l_ / 2, w_ / 2, z_),
                                                (-l_ / 2, w_ / 2, z_)], [(0, 1, 2, 3)], m_, S["env"])
            o.rotation_euler = (0, 0, ang)
            o.parent = root
            o.visible_shadow = False
    pop(root, windows, size)
    return root


def ribbon(S, pts, color, t_on, t_off, width=1.2, name="ribbon"):
    p = jx.Path(pts)
    o = jx.ribbon(p, 0.0, p.length, color, S["env"], t_on, t_off, width=width, z=0.05, name=name)
    # out of the render outside its window: even fully transparent, a band 5 cm over the asphalt darkened the road
    # under a chase camera (ep11 r3 f217)
    keys_vis(o, [(t_on - 0.1, t_off + 0.4)])
    return o


def golden(sun_color=(1.0, 0.7, 0.46), energy=4.4, ambient=0.68):
    """The approved interchange look-dev light (ld_interchange.golden): warm low sun, cool light haze."""
    sc = bpy.context.scene
    sun = bpy.data.objects["sun"].data
    sun.color, sun.energy, sun.angle = sun_color, energy, math.radians(1.0)
    nt = sc.world.node_tree
    bg = nt.nodes["Background"]
    amb = [nd for nd in nt.nodes if nd.type == "BACKGROUND" and nd != bg][0]
    amb.inputs["Strength"].default_value = ambient
    g = next(nd for nd in nt.nodes if nd.type == "VALTORGB")
    els = sorted(g.color_ramp.elements, key=lambda e: e.position)
    for el, col in zip(els, ((0.18, 0.15, 0.12, 1), (0.88, 0.8, 0.72, 1), (0.36, 0.48, 0.76, 1))):
        el.color = col


def follow(h, pos, tgt, rel=False):
    """Camera fn tied to a hero: offsets in world axes (the episodes film northbound, +y ahead), or with rel=True
    turned with the hero's smoothed heading (ramps)."""
    def fn(t):
        x, y, z = h.at(t)
        if not rel:
            return Vector((x + pos[0], y + pos[1], z + pos[2])), Vector((x + tgt[0], y + tgt[1], z + tgt[2]))
        i = max(0, min(len(h.full) - 1, int(round(t * FPS))))
        ys = [h.full[k]["yaw"] for k in range(max(0, i - 12), min(len(h.full), i + 13)) if h.full[k]["z"] > -500]
        a = (sum(ys) / len(ys) if ys else NORTH) - NORTH
        ca, sa = math.cos(a), math.sin(a)
        p = Vector((x + pos[0] * ca - pos[1] * sa, y + pos[0] * sa + pos[1] * ca, z + pos[2]))
        q = Vector((x + tgt[0] * ca - tgt[1] * sa, y + tgt[0] * sa + tgt[1] * ca, z + tgt[2]))
        return p, q
    return fn


def fixed(pos, tgt, move=(0, 0, 0), t0=0.0):
    def fn(t):
        d = Vector(move) * (t - t0)
        return Vector(pos) + d, Vector(tgt) + d
    return fn


def hide(n, x=0.0, y=IC.Y_START):
    return [dict(x=x, y=y, z=HIDE_Z, yaw=NORTH, v=0.0, ind=None) for _ in range(n)]


def top(shots, name, lens, t0, t1, fn):
    return shots.add(name, lens, t0, t1, fn, up_fn=lambda t: Vector((0, 1, 0)))


def end_card(S, shots, t0, t1, signs_=(), z=400.0, title="DRIVE LIKE A LOCAL"):
    """Series end card: a road-grey card with white edge lines, the episode's Commons signs laid on it, the series
    title painted like a road marking, its own soft key light; nothing casts a shadow on the scene below."""
    M, c = S["M"], S["env"]
    w, h = 26.0, 48.0
    win = [(t0 - 0.2, t1 + 1.0)]          # the card floats 400 m up: out of the render before END (r3: a grey speck
    #                                       in the sky of low shots)

    def quad(nm, x0, y0, x1, y1, mat, zz):
        o = W.mesh_obj(nm, [(x0, y0, zz), (x1, y0, zz), (x1, y1, zz), (x0, y1, zz)], [(0, 1, 2, 3)], mat, c)
        o.visible_shadow = False
        keys_vis(o, win)
        return o
    quad("endcard", -w / 2, -h / 2, w / 2, h / 2, M.asph, z)
    for sx in (-1, 1):
        quad("endcard_line", sx * 9.6 - 0.15, -h / 2, sx * 9.6 + 0.15, h / 2, M.paint, z + 0.01)
    k = len(signs_)
    for i, (sid, width) in enumerate(signs_):
        x = (i - (k - 1) / 2) * (16.0 / max(1, k - 1) if k > 2 else 5.6)
        callout(S, sid, (x, -4.6, z + 0.05), [(t0 - 0.2, t1 + 1.0)], width=width, tilt=-math.pi / 2, emit=0.15,
                name=f"endsign_{sid}")
    t = W.text_obj("endcard_title", title, 1.25, M.paint, c, "CENTER", "CENTER", 0.0, font=W.SIGN_FONT)
    t.location = (0, -10.0, z + 0.02)
    t.visible_shadow = False
    keys_vis(t, win)
    li = bpy.data.lights.new("endcard_key", "AREA")
    li.size, li.energy, li.color = 34.0, 5200.0, (1.0, 0.95, 0.88)
    lo = bpy.data.objects.new("endcard_key", li)
    c.objects.link(lo)
    keys_vis(lo, win)
    lo.location = (3.0, -6.0, z + 14.0)
    lo.rotation_euler = (math.radians(8), math.radians(-6), 0)
    return top(shots, "E_card", 30, t0, t1, lambda tt: (Vector((0.0, -1.2 - 0.25 * (tt - t0), z + 34.0 - 0.9 * (tt - t0))),
                                                      Vector((0.0, -1.2 - 0.25 * (tt - t0), z))))


def fix_jumps(thresh=2.5):
    """Hold every baked transform constant across a teleport (a cut), so motion blur never smears a vehicle from one
    shot's position to the next (render uses motion_blur_position START)."""
    n = 0
    for o in bpy.data.objects:
        ad = o.animation_data
        if not ad or not ad.action:
            continue
        try:
            fcs = stage.fcurves(o)
        except Exception:
            continue
        loc = [fc for fc in fcs if fc.data_path == "location"]
        if len(loc) < 2 or len(loc[0].keyframe_points) < 3:
            continue
        cols = [[kp.co[1] for kp in fc.keyframe_points] for fc in loc]
        frames = [kp.co[0] for kp in loc[0].keyframe_points]
        jumps = set()
        for i in range(len(frames) - 1):
            if frames[i + 1] - frames[i] > 1.5:
                continue
            d = math.sqrt(sum((cv[i + 1] - cv[i]) ** 2 for cv in cols if len(cv) == len(frames)))
            if d > thresh:
                jumps.add(frames[i])
        if not jumps:
            continue
        for fc in fcs:
            for kp in fc.keyframe_points:
                if kp.co[0] in jumps:
                    kp.interpolation = "CONSTANT"
                    n += 1
        for ch in o.children_recursive:
            if ch.animation_data and ch.animation_data.action:
                try:
                    for fc in stage.fcurves(ch):
                        for kp in fc.keyframe_points:
                            if kp.co[0] in jumps:
                                kp.interpolation = "CONSTANT"
                except Exception:
                    pass
    return n


def finish(S, shots, tl, light=(0.45, 0.88, -0.25), elev=16.0, skip=()):
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, tl.N
    stage.sky(S["road"], Vector(light).normalized(), ASSETS, sun_elev_deg=elev, sun_energy=4.6)
    golden()
    fix_jumps()
    stage.hazify_all(dist=2600.0, skip=tuple(skip))
    stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
    sc.render.motion_blur_position = "START"
    sc.view_settings.exposure = 0.1
    print("SIGN_SOURCES", sorted(str(k) for k in SG.sources_used()))
    todo = STILLS or list(range(FR[0], FR[1] + 1) if FR else range(1, tl.N + 1))
    jx.render_frames(shots, OUT, todo)
    print("RENDER_DONE", FR or STILLS)
# ==== end of a3 common ====


TL = Timeline([("HOOK", 2.2), ("SITUATION", 10.0), ("RULE", 7.0), ("COST", 4.5), ("CORRECT", 6.5), ("END", 2.7)])
HERO_MODELS["hero_hatch"] = ("hatch", (0.86, 0.87, 0.88), "QX DL 207")
LOOP_PATH, LOOP = poly_path([p for p in IC.layout(1)["loop"]] + [(XA, y, 0.0) for y in range(-40, 400, 4)])
S_MERGE = LOOP.nearest_s(XA, IC.MERGE + 30.0)[0] - 30.0          # arc length at the start of the merge lane


def s_at_y(y):
    return LOOP.nearest_s(XA if y > IC.MERGE else IC.layout(1)["loop"][-1][0], y)[0]


hatch, saloon, artic = Hero("hatch", "hero_hatch", 4.1), Hero("saloon", "saloon_black", 4.8), Hero("artic", "t_white", 16.45)
n = TL.n
# HOOK: the end of the acceleration lane at 70 km/h, left indicator, the saloon closing in and braking
hatch.segs["HOOK"] = run(n("HOOK"), MAIN, 140.0, vprof([(0, 19.4)]), lane(XA, (1.0, 2.6, XR)), ind((0.3, 9, "L")))
saloon.segs["HOOK"] = run(n("HOOK"), MAIN, 80.0, vprof([(0, 36.0), (1.2, 36.0), (2.2, 27.0)]),
                          lane(XR, (1.5, 0.6, XR - 0.6)))
# SITUATION: off the ramp at 60, holds 70 the whole lane (cut at 3.0 s), merges 3 m ahead of the saloon
hatch.segs["SITUATION"] = concat(
    run(90, LOOP_PATH, s_at_y(-215.0), vprof([(0, 16.7), (1.5, 19.4)])),
    run(210, MAIN, 55.0, vprof([(3.0, 19.4)]), lane(XA, (8.0, 1.6, XR)), ind((7.0, 9.8, "L")), t0=3.0))
saloon.segs["SITUATION"] = run(n("SITUATION"), MAIN, -160.45, vprof([(0, 36.0), (8.1, 36.0), (9.85, 19.4)]),
                               lane(XR, (8.3, 0.5, XR - 0.8), (8.9, 1.0, XR)))
artic.segs["SITUATION"] = run(n("SITUATION"), MAIN, 68.4, vprof([(0, 22.2)]), lane(XR))
# RULE: the right way as a demonstration under the lane highlights: up to speed along the lane, merge in its last
# 40 m before the taper (y 150 to 180; "use the whole lane", r3 caption 5.25 s)
hatch.segs["RULE"] = run(n("RULE"), MAIN, 20.0, vprof([(0, 22.0), (3.5, 25.0)]), lane(XA, (5.4, 1.2, XR)),
                         ind((4.0, 6.7, "L")))
# COST: the near miss again at half speed, then both slow down with hazards, the artic braking behind
_sit_h, _sit_s = hatch.segs["SITUATION"], saloon.segs["SITUATION"]


def slowmo(rows, t_from, n_, rate=0.5, haz=None):
    out = []
    for k in range(n_):
        fx = t_from * FPS + k * rate
        a = int(fx)
        u = fx - a
        ra, rb = rows[a], rows[min(len(rows) - 1, a + 1)]
        r = {q: ra[q] + (rb[q] - ra[q]) * u for q in ("x", "y", "z", "yaw")}
        r.update(v=(ra["v"] + (rb["v"] - ra["v"]) * u) * rate, ind=("H" if haz is not None and k * DT >= haz else ra["ind"]))
        out.append(r)
    return out


hatch.segs["COST"] = concat(slowmo(_sit_h, 7.9, 66, haz=1.8),
                            run(69, MAIN, 185.0, vprof([(2.2, 17.0), (3.6, 7.0)]), lane(XR), ind((2.2, 9, "H")), t0=2.2))
saloon.segs["COST"] = concat(slowmo(_sit_s, 7.9, 66, haz=1.5),
                             run(69, MAIN, 172.0, vprof([(2.2, 17.0), (3.6, 7.0)]), lane(XR), ind((2.2, 9, "H")), t0=2.2))
artic.segs["COST"] = concat(run(66, MAIN, 260.0, vprof([(0, 11.0)]), lane(XR)),
                            run(69, MAIN, 112.0, vprof([(2.2, 21.0), (4.5, 10.0)]), lane(XR), t0=2.2))
# CORRECT: floors it along the lane, indicator at half way, merges in the lane's last 40 m (y 153 to 190) into the
# gap behind the artic (about 25 m); saloon unaffected
hatch.segs["CORRECT"] = run(n("CORRECT"), MAIN, 40.0, vprof([(0, 17.0), (3.2, 26.0), (4.9, 26.0), (6.5, 25.0)]),
                            lane(XA, (4.9, 1.4, XR)), ind((3.2, 6.4, "L")))
artic.segs["CORRECT"] = run(n("CORRECT"), MAIN, 92.0, vprof([(0, 22.2)]), lane(XR))
saloon.segs["CORRECT"] = run(n("CORRECT"), MAIN, -39.6, vprof([(0, 38.9)]), lane(XM))
HEROES = [hatch, saloon, artic]
for h in HEROES:
    h.build(TL)

# SUMO background, one window of the 60 s track per segment (COST at half speed under the slow motion)
DATA = load_traffic()
BOX = (-25.0, 45.0, -300.0, 650.0)
W0 = {"HOOK": 400, "SITUATION": 700, "RULE": 1100, "COST": 1350, "CORRECT": 1500}


def gap_behind(h, back=80.0, ahead=40.0):
    """Keep the right lane clear around the hero (the gap it merges into, up to the artic ahead)."""
    def f(t, x, y):
        x0, y0, z0 = h.at(TL.a("CORRECT", t))
        return 10.2 < x < 14.0 and y0 - back < y < y0 + ahead
    return f


PLAN = {
    "HOOK": pick(DATA, TL, "HOOK", W0["HOOK"], HEROES, BOX),
    "SITUATION": pick(DATA, TL, "SITUATION", W0["SITUATION"], HEROES, (-25.0, 45.0, -420.0, 650.0)),
    "RULE": pick(DATA, TL, "RULE", W0["RULE"], HEROES, BOX),
    "COST": pick(DATA, TL, "COST", W0["COST"], HEROES, BOX, rate=0.5,
                 excl=lambda t, x, y: t > 2.2 and 10.2 < x < 14.0 and 90 < y < 260),
    "CORRECT": pick(DATA, TL, "CORRECT", W0["CORRECT"], HEROES, BOX, excl=gap_behind(hatch)),
}
if CHECK:
    sys.exit(0 if check(TL, HEROES, PLAN, DATA) else 1)

# ------------------------------------------------------------------ the scene
blender_imports()
S = build_scene()
for h in HEROES:
    drive(S, h)
for seg, kept in PLAN.items():
    play(S, DATA, TL, seg, W0[seg], kept, rate=0.5 if seg == "COST" else 1.0)

# RULE highlights: the whole acceleration lane in soft blue, the through lane in green with an arrow (priority)
r0, r1 = TL.a("RULE"), TL.a("COST")
ys = [IC.MERGE + 2.0 * k for k in range(int((IC.MERGE_END - IC.MERGE) / 2.0))]
strip(S, "glow_merge", [(14.3 + IC.aux_width(y) / 2, y) for y in ys], lambda i: max(0.2, IC.aux_width(ys[i]) - 0.4),
      (0.25, 0.55, 1.0), [(r0 + 0.2, r1)])
ribbon(S, [(XR, -80.0), (XR, 300.0)], (0.2, 1.0, 0.35), r0 + 0.6, r1, width=1.6, name="rib_priority")
# no 330.1 call-out in the top view (r3: read as a sign lying in the field; the captions do not use it). The real
# 330.1 stands on its post at the ramp start (kit/interchange.py) and is on the end card.

# ------------------------------------------------------------------ cameras
shots = jx.Shots(TL.N)
a = TL.a
shots.add("H_chase", 28, a("HOOK"), a("HOOK", 1.4), follow(hatch, (0.8, -9.0, 2.3), (-1.2, 25.0, 0.9)))
shots.add("H_mirror", 30, a("HOOK", 1.4), a("SITUATION"), follow(hatch, (-1.15, 0.6, 1.1), (-2.6, -35.0, 0.9)))
shots.add("S_drone", 24, a("SITUATION"), a("SITUATION", 3.0), follow(hatch, (14.0, -55.0, 42.0), (-6.0, 35.0, 0.0)))
pov = shots.add("S_pov", 30, a("SITUATION", 3.0), a("SITUATION", 7.5), follow(hatch, (-0.36, 1.25, 1.42), (-0.6, 40.0, 1.15)))  # bonnet a thin strip (QA: grey blob)
shots.add("S_rear", 35, a("SITUATION", 7.5), a("SITUATION", 8.6), follow(hatch, (-0.7, -2.8, 1.05), (-0.4, -40.0, 0.9)))
shots.add("S_high", 30, a("SITUATION", 8.6), a("RULE"), follow(hatch, (3.5, -26.0, 7.0), (-1.5, 6.0, 0.8)))
shots.add("R_side", 22, a("RULE"), a("RULE", 3.5), fixed((62.0, 40.0, 34.0), (14.0, 95.0, 0.0), (0, 6.0, 0), a("RULE")))
top(shots, "R_top", 30, a("RULE", 3.5), a("COST"), fixed((15.0, 120.0, 115.0), (15.0, 120.0, 0.0)))
shots.add("C_slow", 30, a("COST"), a("COST", 2.2), follow(hatch, (6.0, -14.0, 1.6), (-1.5, -5.0, 0.9)))
top(shots, "C_top", 35, a("COST", 2.2), a("CORRECT"), follow(saloon, (0.0, 5.0, 60.0), (0.0, 5.0, 0.0)))
shots.add("K_drone", 24, a("CORRECT"), a("CORRECT", 3.0), follow(hatch, (20.0, -48.0, 36.0), (-5.0, 30.0, 0.0)))
shots.add("K_chase", 30, a("CORRECT", 3.0), a("END"), follow(hatch, (0.5, -9.5, 2.5), (-1.0, 25.0, 1.0)))
end_card(S, shots, a("END"), TL.T, signs_=(("330.1", 5.0),))
finish(S, shots, TL, skip=("glow_merge", "rib_priority"))
