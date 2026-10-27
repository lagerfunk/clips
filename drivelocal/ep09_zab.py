"""Shared Autobahn set for the a3b episodes (ep09 no speed limit, ep17 out of fuel, ep19 tailgating); not a scene.
The interchange stage (kit/interchange.py, RQ 36, northbound +y, lane centres x 4.625 / 8.375 / 12.125, hard shoulder
14.3 to 16.8) with SUMO background traffic (kit/traffic.py) that is filtered so it never drives through a hero;
heroes are hand-choreographed per segment in pieces (speed plan, lane moves, indicators) and baked with motion.bake;
cameras through jx.Shots; Commons signs through kit/signs.py only; series end card; render loop.
Episode CLI (same as ep02): OUT --frames a-b | --stills a,b --res --samples --assets.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(HERE, "..", "kit"), os.path.join(HERE, "kit"), HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import interchange as IC  # noqa: E402
import jx  # noqa: E402
import motion  # noqa: E402
import signs as SG  # noqa: E402
import stage  # noqa: E402
import traffic as TR  # noqa: E402
import vehicles as V  # noqa: E402
import world as W  # noqa: E402

FPS = 30
X = {"L": 4.625, "M": 8.375, "R": 12.125, "HS": 15.55, "EXIT": 16.175}
NORTH = math.pi / 2
UP_N = Vector((0, 1, 0))
HIDE = (0.0, -9000.0, -600.0)
TRACK = next((p for p in (os.path.join(HERE, "traffic", "interchange_day.json.gz"),
                          os.path.join(HERE, "..", "traffic", "interchange_day.json.gz")) if os.path.exists(p)), None)
FONT_DIR = next((d for d in (os.path.join(HERE, "fonts"), os.path.join(HERE, "..", "fonts")) if os.path.isdir(d)), None)


def cli():
    a = dict(OUT="frames", RES=540, SAMPLES=8, ASSETS="assets", FR=None, STILLS=None)
    v = sys.argv
    for i, x in enumerate(v):
        if i == 1 and not x.startswith("--"):
            a["OUT"] = x
        if x == "--res":
            a["RES"] = int(v[i + 1])
        if x == "--samples":
            a["SAMPLES"] = int(v[i + 1])
        if x == "--assets":
            a["ASSETS"] = v[i + 1]
        if x == "--frames":
            p, q = v[i + 1].split("-")
            a["FR"] = (int(p), int(q))
        if x == "--stills":
            a["STILLS"] = [int(s) for s in v[i + 1].split(",")]
    return a


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

    def f0(self, seg):
        return int(round(self.span[seg][0] * FPS))

    def n(self, seg):
        return int(round(self.span[seg][1] * FPS)) - self.f0(seg)


def smooth(u):
    u = min(1.0, max(0.0, u))
    return u * u * u * (u * (6 * u - 15) + 10)


def piece(n, y0, x0, v0, speed=(), moves=(), inds=(), yaw_off=(), extra=None, z=None):
    """n frames of a northbound driver. speed: [(t, v_target, a)] (accelerate or brake towards v_target at |a| m/s2
    from t); moves: [(t0, dur, x_to)] smooth lane moves; inds: [(t0, t1, "L"|"R"|"H")]; yaw_off: [(t0, dur, dyaw)]
    extra heading turned in smoothly (a spin); extra(t, row) may add keys (beacon, pitch). Times relative to the piece."""
    rows, y, v, x = [], y0, v0, x0
    sp = sorted(speed)
    yaw_prev = NORTH
    for i in range(n):
        t = i / FPS
        tgt = None
        for (ts, vt, acc) in sp:
            if t >= ts:
                tgt = (vt, acc)
        if tgt and i:
            vt, acc = tgt
            dv = acc / FPS
            v = min(vt, v + dv) if v < vt else max(vt, v - dv)
        if i:
            y += v / FPS
        xx = x0
        for (m0, md, xt) in moves:
            if t >= m0:
                xx = xx + (xt - xx) * smooth((t - m0) / md)
        ind = None
        for (a0, a1, s) in inds:
            if a0 <= t < a1:
                ind = s
        off = sum(dy * smooth((t - y0_) / dur) for (y0_, dur, dy) in yaw_off)
        rows.append(dict(x=xx, y=y, z=0.0 if z is None else z, v=v, ind=ind, _off=off))
    for i, r in enumerate(rows):
        j0, j1 = max(0, i - 1), min(n - 1, i + 1)
        dx, dy = rows[j1]["x"] - rows[j0]["x"], rows[j1]["y"] - rows[j0]["y"]
        yaw = math.atan2(dy, dx) if math.hypot(dx, dy) > 0.02 else yaw_prev
        yaw_prev = yaw
        r["yaw"] = yaw + r.pop("_off")
        if extra:
            extra(i / FPS, r)
    return rows


def hidden(n):
    return [dict(x=HIDE[0], y=HIDE[1], z=HIDE[2], yaw=NORTH, v=0.0, ind=None) for _ in range(n)]


class Hero:
    """A hand-choreographed vehicle: pieces per segment, baked over the whole canonical timeline."""

    def __init__(self, coll, name):
        self.coll, self.name, self.parts, self.track, self.rig = coll, name, {}, None, None

    def at(self, seg, rel, **kw):
        self.parts.setdefault(seg, []).append((rel, kw))
        return self

    def build(self, TL):
        tr = []
        for seg in TL.order:
            n, ps = TL.n(seg), sorted(self.parts.get(seg, []), key=lambda p: p[0])
            if not ps:
                tr += hidden(n)
                continue
            first = int(round(ps[0][0] * FPS))
            tr += hidden(first)
            for k, (rel, kw) in enumerate(ps):
                end = int(round(ps[k + 1][0] * FPS)) if k + 1 < len(ps) else n
                m = end - int(round(rel * FPS))
                tr += piece(m, **kw) if kw else hidden(m)
        self.track = tr[:TL.N] + hidden(max(0, TL.N - len(tr)))
        return self.track

    def bake(self, TL, c):
        self.build(TL)
        self.rig = motion.rig(self.coll, c)
        self.rig.obj.name = "hero_" + self.name
        motion.bake(self.rig, self.track)
        return self.rig

    def pos(self, t):
        i = max(0, min(len(self.track) - 1, int(round(t * FPS))))
        r = self.track[i]
        return Vector((r["x"], r["y"], r["z"])), r["yaw"]


def heroes_lib(lib, specs):
    """specs: {key: (kind, color, plate)}; kind 'artic' builds a 40 t artic, 'police' the police estate."""
    out = {}
    for key, (kind, col, plate) in specs.items():
        if kind == "artic":
            out[key] = V.truck("h_" + key, col, (0.86, 0.87, 0.88), "", c=lib, plate=plate)
        else:
            out[key] = V.make(kind, "h_" + key, color=col, plate=plate, c=lib)
    return out


def traffic(S, heroes, TL, excl=lambda f: (3.4, 48.0), radius=650.0, cap=140):
    """SUMO day traffic over the whole timeline, minus every vehicle that ever comes within excl(f) = (dx, dy) of a
    visible hero at the same frame (so nothing drives through a hand-choreographed car), and minus vehicles that never
    come within `radius` of a hero (render cost)."""
    data = TR.load(TRACK)
    tracks = [h.track for h in heroes]
    keep = []
    for veh in data["vehicles"]:
        ok, near = True, False
        for row in veh["track"]:
            f = int(row[0])
            if f < 1 or f > TL.N:
                continue
            dx_, dy_ = excl(f)
            for tr in tracks:
                h = tr[f - 1]
                if h["z"] < -100:
                    continue
                ax, ay = abs(row[1] - h["x"]), abs(row[2] - h["y"])
                if ax < dx_ and ay < dy_:
                    ok = False
                    break
                if ax + ay < radius:
                    near = True
            if not ok:
                break
        if ok and near:
            keep.append(veh)
    keep = keep[:cap]
    d = dict(data)
    d["vehicles"] = keep
    rigs = TR.play(d, S["fleet"], S["traffic"], frames=(1, TL.N))
    print("traffic kept", len(rigs), "of", len(data["vehicles"]), flush=True)
    return rigs


def ground(S, x, y):
    try:
        return S["ground"].h(x, y)
    except Exception:
        return 0.0


def sign_post(S, sid, y, c, width=1.26, x=18.6, bottom=2.0, set_="de-core"):
    """A Commons sign on a post at the right verge of the northbound carriageway, readable by northbound traffic."""
    return SG.assembly([(sid, width)], c, (x, y, ground(S, x, y)), rz=0.0, bottom=bottom, set_=set_, name="sg_" + sid)


def pop(root, windows, size=1.0):
    keys = [(1, 0.0)]
    for t_on, t_off in windows:
        f_on, f_off = int(t_on * FPS) + 1, int(t_off * FPS) + 1
        keys += [(f_on, 0.0), (f_on + 4, 1.18 * size), (f_on + 7, size), (f_off, size), (f_off + 5, 0.0)]
    for f, s in keys:
        root.scale = (s, s, s)
        root.keyframe_insert("scale", frame=f)


def callout(sid, loc, look_from, windows, c, width=3.0, set_="de-core", emit=0.9, flat=False):
    """A Commons sign (unaltered) floating big near its real position, turned to the camera (or lying flat, face up,
    top towards +y, when flat=True); pops in and out in the windows (absolute seconds)."""
    root = bpy.data.objects.new(f"call_{sid}_{len(bpy.data.objects)}", None)
    c.objects.link(root)
    root.location = loc
    plate = SG.face(sid, c, width, set_, name=f"callp_{sid}_{len(bpy.data.objects)}", emit=emit)
    plate.parent = root
    if flat:
        plate.rotation_euler = (-math.pi / 2, 0, 0)
        plate.location = (0, -plate["height"] / 2, 0)
    else:
        d = Vector(look_from) - Vector(loc)
        root.rotation_euler = (0, 0, math.atan2(d.y, d.x) + math.pi / 2)
        plate.location = (0, 0, -plate["height"] / 2)
    for o in [plate] + list(plate.children):
        o.visible_shadow = False
    pop(root, windows)
    return root


def quad(name, pts, mat, c, z=0.0):
    o = W.mesh_obj(name, [(x, y, z) for x, y in pts], [(0, 1, 2, 3)], mat, c)
    o.visible_shadow = False
    return o


def graphic_mat(name, color, emit=1.1, alpha=0.72):
    """Unlit graphic colour: emission over transparency, so a bar keeps one colour in sun, dusk or rain (a lit,
    glossy band picked up the sky and the wet road and changed shade from shot to shot)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = emit
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    mx.inputs["Fac"].default_value = alpha
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return m


def bar(name, color, c, emit=1.1, alpha=0.72):
    """A flat graphic band on the road (unit length along +y, 1 m wide), placed and scaled per frame by key_bar.
    Returns the band with two end caps (o["caps"]), so it reads as a measured distance, not as a lane marking."""
    mat = graphic_mat(name, color, emit, alpha)
    objs = []
    for nm in (name, name + "_cap0", name + "_cap1"):
        o = quad(nm, [(-0.5, 0.0), (0.5, 0.0), (0.5, 1.0), (-0.5, 1.0)], mat, c)
        o.visible_glossy = False
        o.scale = (0, 0, 0)
        o.keyframe_insert("scale", frame=1)
        objs.append(o)
    objs[0]["caps"] = [objs[1].name, objs[2].name]
    return objs[0]


def key_bar(o, frames, fn, width=1.6, cap_w=2.6, cap_l=0.4, dz=0.06):
    """fn(f) -> (x, y0, y1, z) or None (hidden) for each frame; the band is `width` wide, centred on x, with a
    cross bar (cap_w x cap_l) at each end; dz lifts it off the road (draw order between two bands)."""
    caps = [bpy.data.objects[n] for n in o.get("caps", [])]
    for f in frames:
        r = fn(f)
        parts = [(o, None)] + [(cp, k) for k, cp in enumerate(caps)]
        for ob, k in parts:
            if r is None:
                ob.scale = (0, 0, 0)
            else:
                x, y0, y1, z = r
                if k is None:
                    ob.location = (x, y0, z + dz)
                    ob.scale = (width, max(0.01, y1 - y0), 1)
                else:
                    ya = y0 if k == 0 else y1 - cap_l
                    ob.location = (x, ya, z + dz + 0.004)
                    ob.scale = (cap_w, cap_l, 1)
            ob.keyframe_insert("location", frame=f)
            ob.keyframe_insert("scale", frame=f)
    for ob in [o] + caps:
        for fc in stage.fcurves(ob):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


def key_head(h, windows, level=4.0):
    """Headlight flashes: the instance's "head" lamp property high in the windows [(t0, t1)] (absolute seconds)."""
    frames = list(range(1, len(h.track) + 1))
    vals = [level if any(a <= (f - 1) / FPS < b for a, b in windows) else 0.0 for f in frames]
    for o in h.rig.units.values():
        motion.keys(o, '["head"]', 0, frames, vals, interp=0, compress=True)


def chase(h, back=8.0, up=1.6, side=0.0, ahead=24.0, look_up=0.6):
    def fn(t):
        p, yaw = h.pos(t)
        fwd = Vector((math.cos(yaw), math.sin(yaw), 0))
        rgt = Vector((math.sin(yaw), -math.cos(yaw), 0))
        return p - fwd * back + rgt * side + Vector((0, 0, up)), p + fwd * ahead + Vector((0, 0, look_up))
    return fn


def pov(h, L=4.6, ahead=40.0, lift=1.3):
    """The driver's line of sight (left-hand drive side), taken from just ahead of the bonnet: the bonnet is out of
    frame (seen from the seat it filled the bottom fifth as a mirror strip with the sky in it and did not read)."""
    def fn(t):
        p, yaw = h.pos(t)
        fwd = Vector((math.cos(yaw), math.sin(yaw), 0))
        rgt = Vector((math.sin(yaw), -math.cos(yaw), 0))
        e = p + fwd * (L / 2 + 0.3) - rgt * 0.36 + Vector((0, 0, lift))
        return e, e + fwd * ahead - Vector((0, 0, 0.55))
    return fn


def drone(h, off=(14.0, -26.0, 16.0), tgt=(0.0, 12.0, 0.0), drift=(0.0, 0.0, 0.0), t0=0.0):
    def fn(t):
        p, _ = h.pos(t)
        k = t - t0
        return p + Vector(off) + Vector(drift) * k, p + Vector(tgt)
    return fn


def top(h, height=60.0, ahead=18.0, side=0.0):
    def fn(t):
        p, _ = h.pos(t)
        return p + Vector((side, ahead - 0.01, height)), p + Vector((side, ahead, 0.0))
    return fn


def fixed(pos, tgt, drift=(0, 0, 0), t0=0.0):
    return lambda t: (Vector(pos) + Vector(drift) * (t - t0), Vector(tgt))


def end_card(S, c, shots, t0, t1, signs_=(), z=400.0, title="DRIVE LIKE A LOCAL"):
    """Series end card: road-grey card (Autobahn asphalt, white edge lines), the episode's Commons signs laid flat,
    the series title painted like a road marking; own soft key light; no live action."""
    M = S["M"]
    w, h = 26.0, 48.0
    quad("endcard", [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)], M.asph, c, z=z)
    for sx in (-1, 1):
        quad("endcard_line", [(sx * 9.6 - 0.15, -h / 2), (sx * 9.6 + 0.15, -h / 2), (sx * 9.6 + 0.15, h / 2),
                              (sx * 9.6 - 0.15, h / 2)], M.paint, c, z=z + 0.01)
    k = len(signs_)
    for i, (sid, width) in enumerate(signs_):
        root = bpy.data.objects.new(f"flat_{sid}", None)
        c.objects.link(root)
        root.location = ((i - (k - 1) / 2) * 5.6, -4.6, z + 0.03)
        plate = SG.face(sid, c, width, "de-core", name=f"flat_{sid}_{len(bpy.data.objects)}", emit=0.15)
        plate.parent = root
        plate.rotation_euler = (-math.pi / 2, 0, 0)
        plate.location = (0, -plate["height"] / 2, 0)
    t = W.text_obj("endcard_title", title, 1.25, M.paint, c, "CENTER", "CENTER", 0.0, font=W.SIGN_FONT)
    t.location = (0, -10.0 if k else -7.0, z + 0.02)
    li = bpy.data.lights.new("endcard_key", "AREA")
    li.size, li.energy, li.color = 34.0, 5200.0, (1.0, 0.95, 0.88)
    lo = bpy.data.objects.new("endcard_key", li)
    c.objects.link(lo)
    lo.location = (3.0, -6.0, z + 14.0)
    lo.rotation_euler = (math.radians(8), math.radians(-6), 0)
    # the card hangs 400 m up: it showed as a dark rectangle in the sky of low shots and could throw a shadow, so it
    # renders only from the END shot on
    f_end = int(t0 * FPS) + 1
    for o in list(c.objects):
        if o.name.startswith(("endcard", "flat_")) or (o.parent and o.parent.name.startswith("flat_")):
            for ob in [o] + list(o.children_recursive):
                for f, hid in ((1, True), (f_end - 1, True), (f_end, False)):
                    ob.hide_render = hid
                    ob.keyframe_insert("hide_render", frame=f)
    return shots.add("E_card", 30, t0, t1, lambda tt: (Vector((0.0, -1.2 - 0.25 * (tt - t0), z + 34.0 - 0.9 * (tt - t0))),
                                                       Vector((0.0, -1.2 - 0.25 * (tt - t0), z))), up_fn=lambda tt: UP_N)


def fix_jumps(thresh=2.5):
    """Constant interpolation across teleports (cuts), so motion blur never smears a car between shots."""
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
                except Exception:
                    pass


SMOKE = bool(os.environ.get("A3B_SMOKE"))          # quick local check: no landscape, no render


def build(A, light=(0.45, 0.88, -0.25), elev=16.0, energy=4.6):
    S = IC.build(A["ASSETS"], fleet=True, landscape=not SMOKE)
    SG.setup(A["ASSETS"])
    S["light"] = (light, elev, energy)
    return S


def light(S, A, exposure=0.1, haze=2800.0):
    li, elev, energy = S["light"]
    stage.sky(S["road"], Vector(li).normalized(), A["ASSETS"], sun_elev_deg=elev, sun_energy=energy)
    stage.hazify_all(dist=haze)
    bpy.context.scene.view_settings.exposure = exposure


def finish(A, shots, TL):
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, TL.N
    fix_jumps()
    stage.render_setup(A["SAMPLES"], A["RES"], int(round(A["RES"] * 16 / 9)))
    sc.render.motion_blur_position = "START"
    print("SIGN_SOURCES", sorted(SG.sources_used()), flush=True)
    if SMOKE:
        print("SMOKE_OK", TL.N, len(bpy.data.objects), flush=True)
        return
    todo = A["STILLS"] or list(range(A["FR"][0], A["FR"][1] + 1) if A["FR"] else range(1, TL.N + 1))
    jx.render_frames(shots, A["OUT"], todo)
    print("RENDER_DONE", A["FR"], flush=True)
