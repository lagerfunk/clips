"""a5 scene kit: the shared part of the standard town episodes 10, 16, 20 and 26 of Drive Like a Local (Germany).
Not a scene by itself. The episode scripts import it (it sits next to them on the runners; locally they add ../ep10
to sys.path). Same CLI as ep02: OUT --frames a-b | --stills a,b --res --samples --assets.
Owner rules kept here: signs only through kit/signs.py (Commons files, unaltered), never town.py's procedural signs;
no brands or wordmarks (vehicles.LABELS stays False); German plates with fictional codes (vehicles.plate_text);
every car through motion.bake (wheels, steering, brake lights, indicators, low beams at night); no voice, no music.
Weather is switched per time window at render time (kit/weather.py: apply restores the stage first, under 1 s).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import figures as F  # noqa: E402
import jx  # noqa: E402
import motion  # noqa: E402
import signs as SG  # noqa: E402
import stage  # noqa: E402
import town as TN  # noqa: E402
import townplus as TP  # noqa: E402
import townstage as TS  # noqa: E402
import vehicles as V  # noqa: E402
import weather as WX  # noqa: E402
import world as W  # noqa: E402

OUT, RES, SAMPLES, ASSETS, FR, STILLS = "frames", 540, 8, "assets", None, None
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
FPS = jx.FPS
FONT_DIR = next((d for d in (os.path.join(HERE, "fonts"), os.path.join(HERE, "..", "fonts"),
                             "/home/claude/sf2/fonts") if os.path.isdir(d)), None)
UP_N = Vector((0, 1, 0))
HIDE = -600.0


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

    def n(self, seg):
        return int(round(self.span[seg][1] * FPS)) - int(round(self.span[seg][0] * FPS))

    def f(self, seg, rel=0.0):
        return int(round((self.span[seg][0] + rel) * FPS)) + 1


def kin(s0, v0, plan, n, **kw):
    return jx.kinematics(s0, v0, plan, n, **kw)


def hold(s, n):
    return [(s, 0.0)] * n


def line(*pts):
    return jx.Path([tuple(p) for p in pts])


def s_of_y(path, y):
    """Arc length where the polyline path first reaches coordinate y, interpolated along the segment. jx.Path.s_of_y
    returns the arc length of the nearest VERTEX: on a two-point line from y = -200 that is 0, which parked the ep20
    cars 190 m short of the stop line in rev 2 (the drone and top shots showed an empty junction)."""
    p, acc = path.p, path.acc
    for i in range(len(p) - 1):
        a, b = p[i].y, p[i + 1].y
        if (a - y) * (b - y) <= 0 and a != b:
            return acc[i] + (acc[i + 1] - acc[i]) * (y - a) / (b - a)
    return path.s_of_y(y)


def brake(s_stop, v0, t_b, t_s, n):
    """(s, v) per frame of a segment: v0 until t_b, then an even stop (or a slide on ice) ending at s_stop at t_s."""
    s_b = s_stop - v0 * (t_s - t_b) / 2.0
    out = []
    for i in range(n):
        t = i / FPS
        if t < t_b:
            out.append((s_b - v0 * (t_b - t), v0))
        elif t < t_s:
            u = t - t_b
            a = v0 / (t_s - t_b)
            out.append((s_b + v0 * u - a * u * u / 2, v0 - a * u))
        else:
            out.append((s_stop, 0.0))
    return out


def ease(u):
    return jx.ease(u)


def track(TL, parts, L=4.2):
    """Per-frame motion.bake track for frames 1..N from per-segment parts. A part is (path, sv[, extra]) with sv one
    (s, v) per frame of the segment, or a ready list of track dicts (parking.parallel_track). extra: ind=[(side, r0,
    r1)] seconds from the segment start, yaw=fn(rel_t) (a slide: the body yaws off the path). A car missing from a
    segment waits far out of sight."""
    locs, yaws, vs, inds = [], [], [], []
    wb = 0.55 * L
    for k in TL.order:
        n, p = TL.n(k), parts.get(k)
        if p is None:
            locs += [(HIDE, HIDE, 0.0)] * n
            yaws += [0.0] * n
            vs += [0.0] * n
            inds += [None] * n
            continue
        if isinstance(p, list):
            p = (p + [dict(p[-1], v=0.0)] * n)[:n]
            locs += [(d["x"], d["y"], 0.0) for d in p]
            yaws += [d["yaw"] for d in p]
            vs += [d["v"] for d in p]
            inds += [d.get("ind") for d in p]
            continue
        path, sv = p[0], p[1]
        ex = p[2] if len(p) > 2 else {}
        sv = (sv + [(sv[-1][0], 0.0)] * n)[:n]
        for i, (s, v) in enumerate(sv):
            t = i / FPS
            pf, _ = path.at(s + wb / 2)
            pr, _ = path.at(s - wb / 2)
            q, _ = path.at(s)
            d = pf - pr
            locs.append((q.x, q.y, 0.0))
            yaws.append(math.atan2(d.y, d.x) + (ex["yaw"](t) if "yaw" in ex else 0.0))
            vs.append(v)
            ind = None
            for side, r0, r1 in ex.get("ind", ()):
                if r0 <= t < r1:
                    ind = side
            inds.append(ind)
    return motion.track_from(locs, yaws, vs, inds)


def bake(car, trk, night=False):
    car["rig"] = motion.bake(car.get("rig") or motion.rig(car), trk, night=night, frame0=1)
    car["track"] = [(d["x"], d["y"], 0.0) for d in trk]
    return car


def vehicle(src, c, name, L=4.6):
    """A traffic vehicle from a collection (stage fleet, or vehicles.car(..., police=True)), ready for bake()."""
    e = bpy.data.objects.new(name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = src
    c.objects.link(e)
    return dict(obj=e, L=L, name=name)


def parked(env, src, name, x, y, yaw):
    e = bpy.data.objects.new("parked_" + name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = src
    e.location = (x, y, 0)
    e.rotation_euler = (0, 0, yaw - math.pi / 2)
    env.objects.link(e)
    return e


def at(car, t):
    i = max(0, min(len(car["track"]) - 1, int(round(t * FPS))))
    x, y, _ = car["track"][i]
    return Vector((x, y, 0.0))


def heading(car, t, jump=1.0):
    """Direction of travel at time t from the track, looking up to 3 frames ahead but never across a teleport (a
    segment cut): rev 2 of ep10 turned the chase camera towards the next segment's start in the last frames of
    S_chase, a 2-frame flash of a side view at the SITUATION > RULE join. Falls back to looking back, then yaw0."""
    tr = car["track"]
    n = len(tr)
    i = max(0, min(n - 1, int(round(t * FPS))))
    P = lambda k: Vector(tr[k][:2])  # noqa: E731
    j = i
    while j + 1 < n and j < i + 3 and (P(j + 1) - P(j)).length < jump:
        j += 1
    d = P(j) - P(i)
    if d.length <= 1e-4:
        k = i
        while k - 1 >= 0 and k > i - 3 and (P(k) - P(k - 1)).length < jump:
            k -= 1
        d = P(i) - P(k)
    return math.atan2(d.y, d.x) if d.length > 1e-4 else car.get("yaw0", math.pi / 2)


class Shots(jx.Shots):
    """jx.Shots with frame-exact starts: it takes int(t0 * FPS) + 1, and float sums such as 32.3 * 30 = 968.99..
    put a cut one frame early (ep10 rev 2: the end road with the snow preset for one rendered frame before END)."""

    def add(self, name, lens, t0, t1, fn, up_fn=None):
        return super().add(name, lens, t0 + 1e-6, t1 + 1e-6, fn, up_fn)


def light(az, elev, energy=5.0, col=(1.0, 0.64, 0.4), tint=(1.0, 0.84, 0.7), amb=0.75, exposure=0.3):
    """Low late-October sun (azimuth from +x, counter-clockwise), long shadows, warm sky (as episode 22)."""
    TS.light(sun_az_deg=az, sun_elev_deg=elev, assets=ASSETS)
    sun = bpy.data.objects["sun"]
    sun.data.color, sun.data.energy, sun.data.angle = col, energy, math.radians(1.0)
    nt = bpy.context.scene.world.node_tree
    env = next(n for n in nt.nodes if n.type == "TEX_ENVIRONMENT")
    bg = nt.nodes["Background"]
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    mul.inputs["B"].default_value = (*tint, 1)
    nt.links.new(env.outputs["Color"], mul.inputs["A"])
    nt.links.new(mul.outputs["Result"], bg.inputs["Color"])
    for nd in nt.nodes:
        if nd.type == "BACKGROUND" and nd != bg:
            nd.inputs["Strength"].default_value = amb
    bpy.context.scene.view_settings.exposure = exposure


def pop(root, windows, size=1.0):
    """Scale keys: hidden, then popping in and out for each (t_on, t_off) window (absolute seconds)."""
    keys = [(1, 0.0)]
    for t_on, t_off in windows:
        f_on, f_off = int(t_on * FPS) + 1, int(t_off * FPS) + 1
        keys += [(f_on, 0.0), (f_on + 4, 1.18 * size), (f_on + 7, size), (f_off, size), (f_off + 5, 0.0)]
    for f, s in keys:
        root.scale = (s, s, s)
        root.keyframe_insert("scale", frame=f)


def empty(name, c, loc=(0, 0, 0), rot=(0, 0, 0)):
    o = bpy.data.objects.new(name, None)
    c.objects.link(o)
    o.location, o.rotation_euler = loc, rot
    return o


def have(sid, set_):
    return TP.has_sign(sid, set_)


def callout(sid, loc, windows, c, width=2.6, set_="de-core", emit=0.9, up=True):
    """A Commons sign (signs.py, unaltered) floating above its real position: flat for the top views (up=True) or
    upright facing -Y. Skipped (no stand-in) when the file is not in the library yet."""
    if not have(sid, set_):
        print("SIGN_MISSING", set_, sid)
        return None
    root = empty(f"call_{sid}", c, loc)
    plate = SG.face(sid, c, width, set_, name=f"call_{sid}_{len(bpy.data.objects)}", emit=emit)
    plate.parent = root
    if up:
        plate.rotation_euler = (-math.pi / 2, 0, 0)
        plate.location = (0, -plate["height"] / 2, 0)
    else:
        plate.location = (0, 0, -plate["height"] / 2)
    for o in [plate] + list(plate.children):
        o.visible_shadow = False
    pop(root, windows)
    return root


def flat_sign(sid, loc, c, width, set_="de-core", emit=0.0):
    root = empty(f"flat_{sid}", c, loc)
    plate = SG.face(sid, c, width, set_, name=f"flat_{sid}_{len(bpy.data.objects)}", emit=emit)
    plate.parent = root
    plate.rotation_euler = (-math.pi / 2, 0, 0)
    plate.location = (0, -plate["height"] / 2, 0)
    return root


def quad(name, pts, mat, c, z=0.008, shadow=False):
    o = W.mesh_obj(name, [(p[0], p[1], z) for p in pts], [(0, 1, 2, 3)], mat, c, uvs=[(p[0], p[1]) for p in pts])
    TP.up(o)
    o.visible_shadow = shadow
    return o


def bar(name, c, a, b, w, mat, z=0.0, plane="xy", parent=None):
    """A flat bar from a to b (2D), width w, in the xy plane (face up) or the xz plane (face -Y)."""
    a, b = Vector(a), Vector(b)
    d = (b - a).normalized()
    n = Vector((-d.y, d.x)) * (w / 2)
    q = [a + n, a - n, b - n, b + n]
    if plane == "xy":
        vs = [(p.x, p.y, z) for p in q]
    else:
        vs = [(p.x, z, p.y) for p in q]
    o = W.mesh_obj(name, vs, [(0, 1, 2, 3)], mat, c)
    o.visible_shadow = False
    if parent:
        o.parent = parent
    return o


def mark(kind, name, c, loc, size, windows, plane="xz", rot=(0, 0, 0)):
    """A green tick or a red cross (white outline under it) that pops in for the windows; plane xz faces -Y."""
    root = empty(name, c, loc, rot)
    col = (0.1, 0.85, 0.2) if kind == "tick" else (1.0, 0.06, 0.05)
    m_in, m_out = jx.flat_mat(name + "_in", col, emit=2.2), jx.flat_mat(name + "_out", (1, 1, 1), emit=1.4)
    s = size
    segs = ([((-0.45 * s, 0.0), (-0.12 * s, -0.33 * s)), ((-0.12 * s, -0.33 * s), (0.5 * s, 0.4 * s))]
            if kind == "tick" else [((-0.45 * s, -0.45 * s), (0.45 * s, 0.45 * s)),
                                    ((-0.45 * s, 0.45 * s), (0.45 * s, -0.45 * s))])
    for k, (a, b) in enumerate(segs):
        bar(f"{name}_o{k}", c, a, b, 0.24 * s, m_out, z=0.0 if plane == "xy" else 0.002, plane=plane, parent=root)
        bar(f"{name}_i{k}", c, a, b, 0.15 * s, m_in, z=0.004 if plane == "xy" else -0.002, plane=plane, parent=root)
    pop(root, windows)
    return root


def outline(name, c, centre, yaw, L, Wd, col, windows, w=0.22, z=0.06):
    """A glowing rectangle round a parked car (top views)."""
    root = empty(name, c, (centre[0], centre[1], z), (0, 0, yaw))
    m = jx.flat_mat(name + "_m", col, emit=2.4)
    hl, hw = L / 2 + 0.3, Wd / 2 + 0.3
    for k, (a, b) in enumerate((((-hl, -hw), (hl, -hw)), ((hl, -hw), (hl, hw)), ((hl, hw), (-hl, hw)),
                                ((-hl, hw), (-hl, -hw)))):
        bar(f"{name}_{k}", c, a, b, w, m, parent=root)
    pop(root, windows)
    return root


def area(name, c, loc, energy, size=6.0, rot=(0, 0, 0), col=(1.0, 0.95, 0.88)):
    li = bpy.data.lights.new(name, "AREA")
    li.size, li.energy, li.color = size, energy, col
    o = bpy.data.objects.new(name, li)
    c.objects.link(o)
    o.location, o.rotation_euler = loc, rot
    return o


def slip(name, c, loc, yaw, t_on, drop=0.5, tilt=0.42, t_off=None):
    """A plain yellow parking ticket (no crest, no text) that drops onto the windscreen at t_on (gone at t_off)."""
    m = W.principled(name + "_m", (0.95, 0.78, 0.08), 0.6)
    o = TN.box(name, c, (0, 0, 0), (0.11, 0.2, 0.004), m)
    root = empty(name + "_root", c)
    o.parent = root
    f = int(t_on * FPS) + 1
    for ff, dz, wob in ((1, 40.0, 0.0), (f - 1, 40.0, 0.0), (f, drop, 0.5), (f + 4, drop * 0.3, -0.3),
                        (f + 8, 0.0, 0.08), (f + 12, 0.0, 0.0)):
        root.location = (loc[0], loc[1], loc[2] + dz)
        root.rotation_euler = (tilt * math.cos(yaw), tilt * math.sin(yaw), yaw + wob)
        root.keyframe_insert("location", frame=max(1, ff))
        root.keyframe_insert("rotation_euler", frame=max(1, ff))
    if t_off is not None:
        g = int(t_off * FPS) + 1
        for ff, dz in ((g - 1, 0.0), (g, 40.0)):
            root.location = (loc[0], loc[1], loc[2] + dz)
            root.keyframe_insert("location", frame=ff)
    return root


def windscreen_point(car, t, back=1.05, z=1.12):
    """Roughly the lower middle of the windscreen of a car at time t (for the ticket and the torch)."""
    p, yaw = at(car, t), heading(car, t)
    return Vector((p.x + math.cos(yaw) * (car["L"] / 2 - back), p.y + math.sin(yaw) * (car["L"] / 2 - back), z)), yaw


def foot_ground(x, y):
    """Every walker in these scenes stays on a footway (town.KERB_H above the road)."""
    return TN.KERB_H


def walker(c, name, seed, pts, sv, coat=None, role=None, gesture=(), look=(), **kw):
    """A person (kit/figures.py) on the footway along pts with one (s, v) per frame of the whole timeline. role
    "attendant": municipal parking enforcement (navy uniform, ticket device, no crest). gesture/look: seconds from
    frame 1, as figures.walk."""
    if role == "attendant":
        p = F.parking_attendant(c, name, seed=seed, **kw)
    else:
        p = F.person(c, name, seed=seed, jacket=coat, **kw)
    F.walk(p, jx.Path([tuple(q) for q in pts]), sv, ground=foot_ground, gesture=list(gesture), look=list(look))
    return p


def pad(c, loc, t0, t1, name="pad", rot=(0, 0, 0), paper_rgb=(0.66, 0.66, 0.63)):
    """Close-up prop: a plain notepad and a pen that scribbles from t0 to t1. The page's local +y is its top edge,
    the pad's underside is 11 mm below the origin (rest it on a surface with on_body). The paper is a mid-light grey
    so it keeps tone in the light of the scene (rev 2: a 0.93 sheet under its own key light came out pure white)."""
    root = empty(name, c, loc, rot)
    paper = W.principled(name + "_paper", paper_rgb, 0.75)
    TN.box(name + "_sheet", c, (0, 0, 0), (0.16, 0.22, 0.012), paper).parent = root
    TN.box(name + "_back", c, (0, 0, -0.008), (0.17, 0.23, 0.006), W.principled(name + "_card", (0.2, 0.22, 0.3), 0.6)
           ).parent = root
    ink = W.principled(name + "_ink", (0.1, 0.12, 0.2), 0.5)
    for k in range(6):
        ln = TN.box(f"{name}_l{k}", c, (0, 0.07 - 0.03 * k, 0.0062), (0.12, 0.002, 0.0006), W.principled(
            name + "_rule", (0.42, 0.5, 0.66), 0.6))
        ln.parent, ln.visible_shadow = root, False
    pen = TN.cyl(name + "_pen", c, (0, 0, 0), 0.006, 0.14, ink, rot=(0.0, 0.9, 0.3))
    pen.parent = root
    f0, f1 = int(t0 * FPS) + 1, int(t1 * FPS) + 1
    for f in range(f0, f1 + 1, 2):
        u = (f - f0) / max(1, f1 - f0)
        pen.location = (-0.05 + 0.1 * ((f // 2) % 5) / 4.0, 0.06 - 0.09 * u, 0.06)
        pen.keyframe_insert("location", frame=f)
    return root


def show_between(root, t_on, t_off):
    """Render root and everything under it only from t_on to t_off (absolute seconds; hide_render keys, no pop)."""
    f_on, f_off = int(round(t_on * FPS)) + 1, int(round(t_off * FPS)) + 1
    for o in [root] + list(root.children_recursive):
        for fr, hid in ((1, True), (f_on, False), (f_off, True)):
            o.hide_render = hid
            o.keyframe_insert("hide_render", frame=fr)


def adopt(car):
    """jx.hero rigs the car as soon as it is built: motion.rig points the instance at a body collection made from the
    objects the car had then. Parts added to car["coll"] later (parking.see_through: dashboard, seats, wheel;
    parking.windscreen_mount: the disc) never rendered (rev 2: an empty cabin, the disc missing, the inside of the
    tail lamp showing through the glass as a red blob). Link them into the body collection. Returns how many."""
    r = car.get("rig")
    body = r.md["body"] if r is not None and getattr(r, "md", None) else None
    if body is None:
        return 0
    have = set(body.all_objects)
    n = 0
    for o in car["coll"].all_objects:
        if o in have or motion._is_tyre(o) or motion._is_rim(o):
            continue
        body.objects.link(o)
        n += 1
    return n


def car_matrix(car, x, y, yaw):
    """World matrix of the car's model space (front +y, x to the right, z up, y from the middle of the car) for a car
    standing at (x, y) with heading yaw, as motion.bake keys the instance (rz = yaw - pi/2)."""
    from mathutils import Matrix
    coll = car["obj"].instance_collection or car["coll"]
    return (Matrix.Translation((x, y, 0.0)) @ Matrix.Rotation(yaw - math.pi / 2, 4, "Z") @
            Matrix.Translation(-Vector(coll.instance_offset)))


def on_body(car, M, y, x=0.0):
    """World point and outward normal on top of the car body over model point (x, y): a ray cast straight down onto
    the body mesh, else the roof line of vehicles.KINDS. M from car_matrix."""
    body = car["coll"].objects[car["name"] + "_body"]
    mw = body.matrix_local
    inv = mw.inverted()
    try:
        bpy.context.view_layer.update()
        hit, loc, nrm, _i = body.ray_cast(inv @ Vector((x, y, 3.0)), (inv.to_3x3() @ Vector((0, 0, -1))).normalized(),
                                          distance=5.0)
    except Exception as ex:                                  # noqa: BLE001
        print("ON_BODY ray cast failed", ex)
        hit = False
    if hit:
        loc, nrm = mw @ loc, (mw.to_3x3() @ nrm).normalized()
    else:
        k = V.KINDS[car["kind"]]
        st = [(s[0] - k["L"] / 2, s[7]) for s in k["stations"]]
        j = max(0, min(len(st) - 2, next((i for i in range(len(st) - 1) if st[i + 1][0] >= y), len(st) - 2)))
        (y0, z0), (y1, z1) = st[j], st[j + 1]
        u = (y - y0) / max(1e-6, y1 - y0)
        loc = Vector((x, y, z0 + (z1 - z0) * u))
        nrm = Vector((0.0, -(z1 - z0), y1 - y0)).normalized()
    print("ON_BODY", car["name"], round(y, 2), round(x, 2), "hit" if hit else "stations", tuple(round(v, 3) for v in loc))
    return M @ loc, (M.to_3x3() @ nrm).normalized()


def lay_rot(nrm, top_dir):
    """Euler rotation of a flat prop lying on a surface with normal nrm, its local +y towards top_dir."""
    from mathutils import Matrix
    z = Vector(nrm).normalized()
    yv = Vector(top_dir) - z * Vector(top_dir).dot(z)
    yv.normalize()
    xv = yv.cross(z)
    return Matrix((xv, yv, z)).transposed().to_euler()


def fix_jumps(thresh=2.5):
    """Hold baked transforms constant across a teleport (a cut), so motion blur never smears between segments."""
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
        for ob in [o] + list(o.children_recursive):
            if ob.animation_data and ob.animation_data.action:
                try:
                    for fc in stage.fcurves(ob):
                        for kp in fc.keyframe_points:
                            if kp.co[0] in jumps:
                                kp.interpolation = "CONSTANT"
                                n += 1
                except Exception:
                    pass
    return n


def end_card(T, c, shots, t0, t1, signs_=(), z=400.0, title="DRIVE LIKE A LOCAL"):
    """Series end card: a straight road with white edge lines running into the haze, the episode's Commons signs
    standing on one post at its edge (signs.assembly, unaltered files, real sizes). Without a sign the series title
    is painted on the road like a marking (stretched along the road as real markings are). The caption layer carries
    the sign-off and the source line, so nothing here sits under them (sign at y 980..1140 of 1920). Own key light."""
    w, y0, y1 = 26.0, -30.0, 300.0
    quad("endcard", [(-w / 2, y0), (w / 2, y0), (w / 2, y1), (-w / 2, y1)], T.asph, c, z=z)
    for sx in (-1, 1):
        quad("endcard_line", [(sx * 3.4 - 0.15, y0), (sx * 3.4 + 0.15, y0), (sx * 3.4 + 0.15, y1),
                              (sx * 3.4 - 0.15, y1)], T.paint, c, z=z + 0.01)
    stack = [(s[0], s[1]) for s in signs_ if have(s[0], s[2] if len(s) > 2 else "de-core")]
    set_ = signs_[0][2] if signs_ and len(signs_[0]) > 2 else "de-core"
    if stack:
        SG.assembly(stack, c, (2.2, 5.5, z), rz=0.0, bottom=2.0, set_=set_, name="endcard_signs")
    else:
        tt = W.text_obj("endcard_title", title, 0.42, T.paint, c, "CENTER", "CENTER", 0.0, font=W.SIGN_FONT)
        tt.location, tt.scale = (0.0, 6.0, z + 0.02), (1.0, 2.4, 1.0)
    area("endcard_key", c, (-4.0, -8.0, z + 9.0), 2600.0, 16.0, (math.radians(48), 0, math.radians(-25)))
    return shots.add("E_card", 30, t0, t1, lambda t: (Vector((0.0, -9.5 + 0.4 * (t - t0), z + 3.0 - 0.08 * (t - t0))),
                                                     Vector((0.6, 3.0, z + 3.4))))


def finish(shots, TL, wx=(), skip=(), haze=(0.8, 0.74, 0.68)):
    """Render. wx: [(t0, t1, preset, strength)] on the canonical timeline (default day); weather.apply runs when the
    preset changes between two rendered frames, so a preview chunk or a still always gets the right weather."""
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, TL.N
    fix_jumps()
    stage.hazify_all(color=haze, dist=900.0, skip=tuple(skip))
    stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
    sc.render.motion_blur_position = "START"
    print("SIGN_SOURCES", sorted(SG.sources_used()))
    print("SHOT_STARTS", [(nm, f0) for nm, f0, _f1 in getattr(shots, "list", [])])
    todo = STILLS or list(range(FR[0], FR[1] + 1) if FR else range(1, TL.N + 1))
    os.makedirs(OUT, exist_ok=True)
    cur = None
    for f in todo:
        t = (f - 1) / FPS
        p = next(((w[2], w[3]) for w in wx if w[0] - 1e-6 <= t < w[1] - 1e-6), ("day", 1.0))
        if p != cur:
            WX.apply(p[0], strength=p[1])
            cur = p
            print("WEATHER", f, p, flush=True)
        sc.frame_set(f)
        sc.camera = shots.camera_at(f) or sc.camera
        sc.render.filepath = os.path.join(OUT, f"f_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("Saved", sc.render.filepath, flush=True)
    print("RENDER_DONE", FR)
