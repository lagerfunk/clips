"""Drive Like a Local #21, Germany (standard): missed your Autobahn exit? Never cut across. The signs count you down
early (Zeichen 448 at 1,000 m, 449 at 500 m, Baken 450 at 200 and 100 m, exit board 332 and 333 at the gore): move
right in good time, brake in the exit lane, never drive over the hatched Sperrflaeche (Zeichen 298); missed it, take
the next exit. Set: kit/interchange.py northbound exit (taper 60 m, exit lane 250 m, Abfahrtslinie 6 / 6 m, hatched
gore, orange reflectors), SUMO background traffic with the vehicles that would cross the choreography removed.
Heroes hand-choreographed through motion.bake: teal rental hatchback, 40 t artic in the right lane.
The 300 m Bake (450-52) is not placed by kit/interchange.py (its only Commons file is a construction drawing with
dimension arrows inside the face; reports/interchange.md), so the countdown shows the 200 m and 100 m Baken.
Canonical timeline (English order; ep21_edit.json cuts each language):
HOOK 0-2.2, SITUATION 2.2-12.2, RULE 12.2-20.2, COST 20.2-24.7, CORRECT 24.7-31.2, END 31.2-33.9.
Run: python ep21_exit_sequence.py OUTDIR --frames 1-1017 --res 540 --samples 8 --assets ASSETS [--stills 50,330]
     python ep21_exit_sequence.py --check     (plain python: choreography and traffic filter checks, no Blender)
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
import bisect  # noqa: E402

TL = Timeline([("HOOK", 2.2), ("SITUATION", 10.0), ("RULE", 8.0), ("COST", 4.5), ("CORRECT", 6.5), ("END", 2.7)])
HERO_MODELS["hero_hatch"] = ("hatch", (0.06, 0.4, 0.42), "JX DL 721")
EXIT_PTS = [(XA, float(y), 0.0) for y in range(-1000, -612, 4)] + [tuple(p) for p in IC.layout(1)["exit"]]
EXIT_PATH, EXIT = poly_path(EXIT_PTS)
_EY = [p[1] for p in EXIT_PTS]


def exit_xz(y):
    """x and z of the exit lane / exit ramp centreline at station y (the ramp keeps climbing northwards)."""
    k = max(1, min(len(_EY) - 1, bisect.bisect_left(_EY, y)))
    a, b = EXIT_PTS[k - 1], EXIT_PTS[k]
    u = (y - a[1]) / max(1e-6, b[1] - a[1])
    return a[0] + (b[0] - a[0]) * u, a[2] + (b[2] - a[2]) * u


def swerve(n, y0, v, x0, t_sw, dur, ind_fn=lambda t: None, t0=0.0):
    """From lane x0 straight across the lanes (and the hatched gore) onto the exit ramp: x blends from x0 to the ramp
    centreline at the same station, z with it."""
    pts, y = [], y0
    for i in range(n):
        t = t0 + i * DT
        u = sm((t - t_sw) / dur)
        rx, rz = exit_xz(y)
        pts.append((x0 + (rx - x0) * u, y, rz * u))
        y += 0.5 * (v(t) + v(t + DT)) * DT
    return rows_from_pts(pts, t0, ind_fn)


def s_exit(y):
    return EXIT.nearest_s(exit_xz(y)[0], y)[0]


hatch, artic = Hero("hatch", "hero_hatch", 4.1), Hero("artic", "t_blue", 16.45)
n = TL.n
# HOOK: across the right lane and the hatching at 90 km/h, the artic brakes and sounds its horn
hatch.segs["HOOK"] = swerve(n("HOOK"), -630.0, vprof([(0, 25.0), (2.2, 23.0)]), XM, 0.4, 1.8, ind((0.9, 9, "R")))
artic.segs["HOOK"] = run(n("HOOK"), MAIN, -651.6, vprof([(0, 22.2), (1.1, 22.2), (2.2, 18.5)]), lane(XR))
# SITUATION: middle lane at 110 past 448 (cut), past 449 (cut), then the gore: late brake and swerve
hatch.segs["SITUATION"] = concat(
    run(105, MAIN, -1965.0, vprof([(0, 30.6)]), lane(XM)),
    run(105, MAIN, -1480.0, vprof([(0, 30.6)]), lane(XM), t0=3.5),
    swerve(90, -690.0, vprof([(7.0, 30.6), (7.6, 30.6), (9.5, 22.0)]), XM, 8.0, 1.7, ind((7.6, 99, "R")), t0=7.0))
artic.segs["SITUATION"] = concat(
    run(105, MAIN, -1905.0, vprof([(0, 22.2)]), lane(XR)),
    run(105, MAIN, -1440.0, vprof([(0, 22.2)]), lane(XR), t0=3.5),
    run(90, MAIN, -705.0, vprof([(7.0, 22.2), (8.3, 22.2), (10.0, 16.5)]), lane(XR), t0=7.0))
# RULE: the right way under the call-outs: right lane, into the exit lane at its start, brake inside it
hatch.segs["RULE"] = concat(
    hide(150),
    run(90, EXIT_PATH, s_exit(-700.0), vprof([(5.0, 24.0), (8.0, 17.0)]), t0=5.0))
# COST: shaken, on the exit ramp; the artic far behind still braking
hatch.segs["COST"] = concat(run(66, EXIT_PATH, s_exit(-545.0), vprof([(0, 20.0), (2.2, 15.0)])), hide(69))
artic.segs["COST"] = concat(run(66, MAIN, -700.0, vprof([(0, 15.0), (2.2, 19.0)]), lane(XR)), hide(69))
# CORRECT: right lane after 449, into the exit lane at its start, brake there; then a second pass: missed it, straight on
hatch.segs["CORRECT"] = concat(
    run(75, MAIN, -1400.0, vprof([(0, 30.6)]), lane(XM, (0.5, 1.0, XR)), ind((0.2, 1.6, "R"))),
    # into the exit lane as its taper opens (y -887 to -857, full width at -860), brake lamps once inside (c2 caption)
    run(75, MAIN, -920.0, vprof([(2.5, 30.0), (4.4, 30.0), (5.0, 27.0)]), lane(XR, (3.6, 1.0, XA)),
        ind((3.2, 4.8, "R")), t0=2.5),
    run(45, MAIN, -640.0, vprof([(5.0, 30.6)]), lane(XR), t0=5.0))
artic.segs["CORRECT"] = concat(run(75, MAIN, -1330.0, vprof([(0, 22.2)]), lane(XR)), hide(120))
HEROES = [hatch, artic]
for h in HEROES:
    h.build(TL)

DATA = load_traffic()
W0 = {"HOOK": 300, "SITUATION": 650, "RULE": 1000, "COST": 1300, "CORRECT": 1500}
BOX_GORE = (-25.0, 60.0, -900.0, -250.0)


def clear_near(seg, h, t_from, back=70.0, ahead=70.0, x0=10.2, x1=21.0):
    def f(t, x, y):
        if t < t_from:
            return False
        hx, hy, hz = h.at(TL.a(seg, t))
        return hz > -500 and x0 < x < x1 and hy - back < y < hy + ahead
    return f


PLAN = {
    "HOOK": pick(DATA, TL, "HOOK", W0["HOOK"], HEROES, BOX_GORE, excl=clear_near("HOOK", hatch, 0.0)),
    "SITUATION": pick(DATA, TL, "SITUATION", W0["SITUATION"], HEROES, around(hatch.segs["SITUATION"], 200.0, 400.0),
                      excl=clear_near("SITUATION", hatch, 7.0)),
    "RULE": pick(DATA, TL, "RULE", W0["RULE"], HEROES, around(hatch.segs["SITUATION"][:210] + hatch.segs["RULE"][150:], 150.0, 400.0),
                 excl=clear_near("RULE", hatch, 5.0, 40.0, 40.0, 14.0, 21.0)),
    "COST": pick(DATA, TL, "COST", W0["COST"], HEROES, BOX_GORE, excl=lambda t, x, y: x > 14.0 and y > -620.0),
    "CORRECT": pick(DATA, TL, "CORRECT", W0["CORRECT"], HEROES, around(hatch.segs["CORRECT"], 200.0, 400.0),
                    excl=clear_near("CORRECT", hatch, 2.5, 60.0, 40.0)),
}
if CHECK:
    sys.exit(0 if check(TL, HEROES, PLAN, DATA) else 1)

# ------------------------------------------------------------------ the scene
blender_imports()
S = build_scene()
for h in HEROES:
    drive(S, h)
for seg, kept in PLAN.items():
    play(S, DATA, TL, seg, W0[seg], kept)
a = TL.a
sign_at = {o["sign_id"]: o for o in S["builder"].signs if str(o.get("tag", "")).startswith("n_")}


def over(sid, dz=3.2, dx=0.0):
    o = sign_at[sid]
    return (o.location.x + dx, o.location.y - 1.0, o.location.z + o["bottom"] + dz)


# call-outs: the real sign, big and lit, over its own post as the camera passes
for sid, t_on, width in (("448", a("SITUATION", 0.6), 4.2), ("449", a("SITUATION", 3.8), 4.6),
                         ("332", a("SITUATION", 7.3), 4.0)):
    # dz: centre of the call-out above the plate's lower edge; r3 f97 showed the 448 call-out almost touching its sign
    callout(S, sid, over(sid, 5.2 if sid != "332" else 4.4), [(t_on, t_on + 1.0)], width=width, name=f"callout_{sid}")
for sid, t_on, t_off, width in (("448", a("RULE", 0.3), a("RULE", 1.6), 5.2), ("449", a("RULE", 1.7), a("RULE", 3.0), 5.6),
                                ("450-51", a("RULE", 3.1), a("RULE", 5.0), 1.5), ("450-50", a("RULE", 3.6), a("RULE", 5.0), 1.5)):
    callout(S, sid, over(sid, 3.6 if sid.startswith("450") else 5.4), [(t_on, t_off)], width=width,
            name=f"callout_r_{sid}")
# RULE highlights: the exit lane from its start (blue), the Abfahrtslinie (green), the hatched gore (red, no entry)
r0, c0 = a("RULE"), a("COST")
ys = [IC.EXIT_START + 2.0 * k for k in range(int((IC.DIVERGE - IC.EXIT_START) / 2.0) + 1)]
strip(S, "glow_exitlane", [(14.3 + IC.aux_width(y) / 2, y) for y in ys], lambda i: max(0.2, IC.aux_width(ys[i]) - 0.4),
      (0.25, 0.55, 1.0), [(r0 + 4.0, c0)])
strip(S, "glow_line", [(14.15, y) for y in ys if y >= IC.EXIT_PARALLEL], lambda i: 0.8, (0.2, 1.0, 0.35),
      [(r0 + 5.2, c0)], z=0.045)
gy = [IC.DIVERGE + 1.0 * k for k in range(int(S["nose_y"]["exit"] - IC.DIVERGE))]
strip(S, "glow_gore", [((14.3 + exit_xz(y)[0] - 2.25) / 2, y) for y in gy],
      lambda i: max(0.05, exit_xz(gy[i])[0] - 2.25 - 14.3), (1.0, 0.12, 0.08), [(r0 + 5.0, c0), (c0 + 2.3, a("CORRECT"))])
cross(S, (15.9, S["nose_y"]["exit"] - 9.0, 0.3), [(r0 + 5.6, c0), (c0 + 3.0, a("CORRECT"))], 0.75, name="x_gore")
ribbon(S, [(r["x"], r["y"]) for r in hatch.segs["HOOK"][::3]], (1.0, 0.1, 0.08), c0 + 2.4, a("CORRECT"), width=1.4,
       name="rib_swerve")

# ------------------------------------------------------------------ cameras
shots = jx.Shots(TL.N)
shots.add("H_drone", 24, a("HOOK"), a("HOOK", 1.3), fixed((26.0, -665.0, 30.0), (13.0, -598.0, 0.0)))
shots.add("H_low", 32, a("HOOK", 1.3), a("SITUATION"), fixed((22.5, -560.0, 1.1), (15.5, -588.0, 0.5)))
shots.add("S_drone", 26, a("SITUATION"), a("SITUATION", 3.5), follow(hatch, (12.0, -40.0, 16.0), (2.0, 60.0, 2.0)))
shots.add("S_chase", 28, a("SITUATION", 3.5), a("SITUATION", 7.0), follow(hatch, (1.2, -10.0, 2.6), (-0.5, 30.0, 1.2)))
shots.add("S_pov", 30, a("SITUATION", 7.0), a("RULE"), follow(hatch, (-0.36, 1.25, 1.42), (0.4, 40.0, 1.15), rel=True))  # bonnet a thin strip
shots.add("R_448", 26, a("RULE"), a("RULE", 1.6), fixed((13.0, -1985.0, 12.0), (19.0, -1915.0, 4.5), (0, 8.0, 0), a("RULE")))
shots.add("R_449", 26, a("RULE", 1.6), a("RULE", 3.0), fixed((13.0, -1488.0, 12.0), (19.5, -1415.0, 4.5), (0, 8.0, 0),
                                                             a("RULE", 1.6)))
shots.add("R_baken", 24, a("RULE", 3.0), a("RULE", 5.0), fixed((9.0, -1190.0, 20.0), (17.0, -1010.0, 0.0), (0, 30.0, 0),
                                                              a("RULE", 3.0)))
top(shots, "R_top", 30, a("RULE", 5.0), c0, fixed((16.0, -612.0, 95.0), (16.0, -612.0, 0.0)))
shots.add("C_ramp", 30, c0, a("COST", 2.2), follow(hatch, (-2.0, 14.0, 2.2), (0.0, -30.0, 0.5), rel=True))
top(shots, "C_top", 30, a("COST", 2.2), a("CORRECT"), fixed((16.0, -606.0, 85.0), (16.0, -606.0, 0.0)))
k0 = a("CORRECT")
shots.add("K_drone", 24, k0, k0 + 2.5, follow(hatch, (14.0, -50.0, 30.0), (-4.0, 40.0, 0.0)))
shots.add("K_chase", 30, k0 + 2.5, k0 + 5.0, follow(hatch, (0.8, -10.0, 2.6), (-0.2, 30.0, 1.0)))
shots.add("K_pass", 28, k0 + 5.0, a("END"), follow(hatch, (-2.5, -9.0, 2.2), (1.5, 30.0, 1.0)))
end_card(S, shots, a("END"), TL.T, signs_=(("448", 2.8), ("449", 2.8), ("450-51", 0.8), ("450-50", 0.8), ("332", 2.8),
                                          ("333", 2.4)))
finish(S, shots, TL, skip=("glow_exitlane", "glow_line", "glow_gore", "rib_swerve"))
