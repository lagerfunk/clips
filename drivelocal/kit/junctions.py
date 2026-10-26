"""Junction kit, batch 2: an unsigned T-junction (rechts vor links) and a bending priority road (abknickende
Vorfahrt), plus the shared tools kit/roundabout.py builds on: closed kerb loops (islands), paint along curves, sign
stacks from the Commons library (kit/signs.py, unaltered files), the town dressing for new layouts and lane paths as
jx.Path objects (so jx badges, ribbons and kinematics work unchanged). Right-hand traffic, arms on the axes:
S = south (a car from S drives north), E, N, W, exactly as jx.lane_path.

Numbers (sources in reports/junctions.md):
- streets 6.0 m, Hochbord 0.15 m, kerb stone 0.16 m, gutter 0.30 m, footway 2.50 m, kerb radius 6 m: the approved
  town kit (town.py, road_spec.md section 6).
- Breitstrich 0.25 m (VwV-StVO old Nr. 87: at least 25 cm; road_spec.md: 0.25 m off the Autobahn), Schmalstrich and
  Leitlinie 0.12 m, Leitlinie 3 m dash / 6 m gap (townstage priority centre line).
- Sign sizes, size 2 in town (VwV-StVO via signs.py): triangle 900 mm, round 600 mm, Zeichen 306 side 600 mm (the
  Commons picture is the 849 mm diagonal), Zusatzzeichen 600 mm wide; lower edge 2.0 m in town.
- Bending priority road: Zeichen 306 + Zusatzzeichen 'Verlauf der Vorfahrtstrasse' on the priority arms (StVO
  Anlage 3, 2.1), Zeichen 205 + the same Zusatzzeichen on the side arms (StVO Anlage 2, 'zu 2 und 3'); among the side
  roads rechts vor links still applies (bussgeldrechner.org, 26 May 2026).

    import junctions as JN
    S = JN.build(ASSETS, kind="t", seed=4, heroes=[("hatch", (0.5, 0.03, 0.02), "carA", "WI LK 204", 0.3)])
    P = JN.lane_path("S", "W", kind="t")             # stem to the left: a jx.Path with .s_mouth etc.
    S = JN.build(ASSETS, kind="bend", priority=("S", "W"))   # priority road from the south bends to the west
"""
import math
import os
import random

import bpy
from mathutils import Vector

import flora
import jx
import stage
import town as TN
import world as W

try:
    import signs as SG
except Exception:  # noqa: BLE001
    SG = None
try:
    import motion as MO          # vehicles agent (wheel spin, steering, lights); falls back to jx.drive
except Exception:  # noqa: BLE001
    MO = None

HW = 3.0                        # half carriageway of a 6.0 m residential street (town.py)
R_KERB = 6.0                    # kerb radius at the corners (town.py)
PL = TN.KERB_W + TN.FOOT        # property line, measured from the kerb face
KERB_PROFILE = [(0.0, 0.0), (0.0, TN.KERB_H - 0.02), (0.02, TN.KERB_H), (TN.KERB_W, TN.KERB_H)]
SIGN_BACK = TN.KERB_W + 0.75    # post behind the kerb face, so a 0.9 m triangle stays about 0.46 m clear of it
BROAD = 0.25                    # Breitstrich
NARROW = 0.12                   # Schmalstrich, Leitlinie
LEIT_DASH, LEIT_GAP = 3.0, 6.0  # Leitlinie in town
SIZE = {"triangle": 0.90, "round": 0.60, "square": 0.60, "diamond": 0.85, "plate": 0.60}
SIGN_BOTTOM = 2.0
ISLAND_BOTTOM = 0.60
ALLOW_STUB = False              # tests only: a magenta placeholder when a sign file is missing (never in stills)
ARM_ANGLE = {"E": 0.0, "N": math.pi / 2, "W": math.pi, "S": -math.pi / 2}
X_ARMS = ("S", "E", "N", "W")
T_ARMS = ("W", "E", "S")
TURN = {0: "u", 1: "right", 2: "straight", 3: "left"}

# Zusatzzeichen 'Verlauf der Vorfahrtstrasse' (VzKat 1002): the two screen sides the thick line joins, seen by the
# driver who reads the sign (bottom = the driver's own arm) -> plate. Crossroads ('an Kreuzungen') only; read off the
# Commons drawings and titles 26 Oct 2026 (1002-10 'von unten nach links', 1002-11 'von oben nach links', 1002-20
# 'von unten nach rechts', 1002-21 'von oben nach rechts'); tests/test_junctions.py checks every title again.
PLATES_X = {
    frozenset(("bottom", "left")): "1002-10",
    frozenset(("top", "left")): "1002-11",
    frozenset(("bottom", "right")): "1002-20",
    frozenset(("top", "right")): "1002-21",
}
PLATE_WORDS = {"1002-10": ("Kreuzungen", "von unten nach links"), "1002-11": ("Kreuzungen", "von oben nach links"),
               "1002-20": ("Kreuzungen", "von unten nach rechts"), "1002-21": ("Kreuzungen", "von oben nach rechts")}


# ------------------------------------------------------------------ arms and frames
def arm_frame(arm):
    """(d, n): d points from the centre out along the arm, n is the right-hand side of INBOUND traffic."""
    a = ARM_ANGLE[arm]
    d = Vector((math.cos(a), math.sin(a)))
    return d, Vector((-d.y, d.x))


def arm_pt(arm, u, v):
    d, n = arm_frame(arm)
    return d * u + n * v


def to_arm(arm, p):
    d, n = arm_frame(arm)
    p = Vector((p[0], p[1]))
    return p.dot(d), p.dot(n)


def turn_of(entry, exit_):
    k = int(round((ARM_ANGLE[exit_] - ARM_ANGLE[entry]) / (math.pi / 2))) % 4
    return TURN[k]


def screen_side(own, other):
    """Where arm `other` appears for a driver approaching on arm `own`."""
    k = int(round((ARM_ANGLE[other] - ARM_ANGLE[own]) / (math.pi / 2))) % 4
    return {0: "bottom", 1: "right", 2: "top", 3: "left"}[k]


def interp(bp, u, smooth=False):
    """Piecewise interpolation of breakpoints [(u, v), ...] (ascending u), clamped; smooth = smoothstep per piece."""
    if u <= bp[0][0]:
        return bp[0][1]
    for (u0, v0), (u1, v1) in zip(bp, bp[1:]):
        if u <= u1:
            t = (u - u0) / (u1 - u0) if u1 > u0 else 1.0
            if smooth:
                t = t * t * (3 - 2 * t)
            return v0 + (v1 - v0) * t
    return bp[-1][1]


# ------------------------------------------------------------------ paths
class LanePath(jx.Path):
    """jx.Path with metadata (entry, exit, lane, s_mouth, ...) as attributes."""

    def __init__(self, pts, **meta):
        super().__init__([(p[0], p[1]) for p in pts])
        self.meta = dict(meta)
        for k, v in meta.items():
            setattr(self, k, v)

    def s_first(self, pred, start=0.0):
        for p, s in zip(self.p, self.acc):
            if s >= start and pred(p):
                return s
        return None

    def s_last(self, pred):
        hit = None
        for p, s in zip(self.p, self.acc):
            if pred(p):
                hit = s
        return hit

    def stop_s(self, car_len, line_s, margin=0.6):
        """Arc length of the car centre when its front bumper waits `margin` metres before a line at line_s."""
        return line_s - car_len / 2 - margin


def resample(path, step):
    """Points every `step` metres along a jx.Path (keeps both ends)."""
    n = max(2, int(math.ceil(path.length / step)))
    return [path.at(path.length * k / n)[0] for k in range(n + 1)]


def lane_path(entry, exit_, lane=0, kind="t", L=95.0, priority=("S", "W")):
    """T-junction and bending priority road (both 6.0 m streets with 6 m kerb radii, the jx.lane_path geometry).
    entry/exit: arm letters. Returns LanePath with s_mouth (front reaches the start of the kerb radius) and s_centre."""
    arms = T_ARMS if kind == "t" else X_ARMS
    if entry not in arms or exit_ not in arms or entry == exit_:
        raise ValueError(f"{kind}: no path {entry} -> {exit_} (arms {arms})")
    turn = turn_of(entry, exit_)
    on_priority = kind == "bend" and entry in priority
    follows = bool(kind == "bend" and entry in priority and exit_ in priority)
    if follows:
        # along the bending priority road: concentric with the bend (centre of the inner corner kerb)
        corner = arm_frame(entry)[0] + arm_frame(exit_)[0]
        cen = corner * (HW + R_KERB)
        u0 = HW + R_KERB
        a = arm_pt(entry, u0, jx.LANE)
        b = arm_pt(exit_, u0, -jx.LANE)
        r = (a - cen).length
        a0 = math.atan2(a.y - cen.y, a.x - cen.x)
        a1 = math.atan2(b.y - cen.y, b.x - cen.x)
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        pts = [arm_pt(entry, u, jx.LANE) for u in (L, u0 + 10.0)]
        pts += TN.arc(cen.x, cen.y, r, a0, a0 + da, 32)
        pts += [arm_pt(exit_, u, -jx.LANE) for u in (u0 + 10.0, L)]
        base = jx.Path([(p.x, p.y) for p in pts])
    else:
        base = jx.lane_path(entry, turn, L=L)
    return LanePath(resample(base, 0.4), entry=entry, exit=exit_, lane=lane, turn=turn, kind=kind, L=L,
                    s_mouth=L - (HW + R_KERB), s_centre=L, follows_priority=follows, on_priority=on_priority)


# ------------------------------------------------------------------ geometry helpers
def offset_loop(P, d):
    """Offset a CLOSED polyline (no repeated end point) to its left by d, mitred."""
    n = len(P)
    out = []
    for i in range(n):
        a, b, c_ = P[i - 1], P[i], P[(i + 1) % n]
        t1 = (b - a).normalized()
        t2 = (c_ - b).normalized()
        n1, n2 = Vector((-t1.y, t1.x)), Vector((-t2.y, t2.x))
        m = n1 + n2
        m = m.normalized() if m.length > 1e-6 else n1
        out.append(b + m * (d / max(0.3, m.dot(n1))))
    return out


def loop_sweep(name, P, profile, mat, c):
    """Sweep a profile [(left offset, z)] round a closed loop (anticlockwise loop: left = inside)."""
    rings = [offset_loop(P, d) for d, _z in profile]
    Pc = P + [P[0]]
    acc = TN.poly_len(Pc)
    m = len(profile)
    verts, faces, uvs = [], [], []
    for i in range(len(Pc)):
        for j, (_d, z) in enumerate(profile):
            q = rings[j][i % len(P)]
            verts.append((q.x, q.y, z))
            uvs.append((acc[i], j * 0.1))
    for i in range(len(Pc) - 1):
        for j in range(m - 1):
            faces.append((i * m + j, (i + 1) * m + j, (i + 1) * m + j + 1, i * m + j + 1))
    return W.mesh_obj(name, verts, faces, mat, c, uvs=uvs)


def loop_strip(name, P, d0, d1, z0, z1, mat, c):
    A, B = offset_loop(P, d0), offset_loop(P, d1)
    Pc = P + [P[0]]
    acc = TN.poly_len(Pc)
    verts, faces, uvs = [], [], []
    for i in range(len(Pc)):
        a, b = A[i % len(P)], B[i % len(P)]
        verts += [(a.x, a.y, z0), (b.x, b.y, z1)]
        uvs += [(acc[i], d0), (acc[i], d1)]
    for i in range(len(Pc) - 1):
        a, b = 2 * i, 2 * (i + 1)
        faces.append((a, b, b + 1, a + 1) if d1 > d0 else (a + 1, b + 1, b, a))
    return W.mesh_obj(name, verts, faces, mat, c, uvs=uvs)


def flat_poly(name, pts, z, mat, c, uv=True):
    """One upward-facing n-gon (concave is fine) at height z."""
    o = W.mesh_obj(name, [(p.x, p.y, z) for p in pts], [tuple(range(len(pts)))], mat, c)
    me = o.data
    me.update()
    if me.polygons[0].normal.z < 0:
        me.flip_normals()
    if uv:
        TN.uv_world(o, 1.0)
    return o


def island(T, c, P, fill, name="island", gutter=True, kerb_mat=None):
    """Raised island inside the anticlockwise loop P: cobble gutter outside, Hochbord, filled top."""
    objs = []
    if gutter:
        objs.append(loop_strip(name + "_gutter", P, -TN.GUTTER, 0.0, 0.004, 0.004, T.cobble, c))
    k = loop_sweep(name + "_kerb", P, KERB_PROFILE, kerb_mat or T.curb, c)
    k["role"] = "island_kerb"
    objs.append(k)
    if fill is not None:
        objs.append(flat_poly(name + "_top", offset_loop(P, TN.KERB_W), TN.KERB_H, fill, c))
    return objs


def kerb_block(T, c, P, corners, name="block", foot=TN.FOOT):
    """A town block along the open kerb line P (road on the right of the walking direction): gutter, Hochbord,
    footway, then lawn out to the far corners (same build as town.Junction.block)."""
    g = TN.strip(name + "_gutter", P, -TN.GUTTER, 0.0, 0.004, 0.004, T.cobble, c)
    k = TN.sweep(name + "_kerb", P, KERB_PROFILE, T.curb, c)
    k["role"] = "kerb"
    f = TN.strip(name + "_footway", P, TN.KERB_W, TN.KERB_W + foot, TN.KERB_H, TN.KERB_H, T.pavers, c)
    Q = TN.offset_poly(P, TN.KERB_W + foot)
    gr = flat_poly(name + "_ground", Q + [Vector(q) for q in corners], TN.KERB_H, T.lawn, c)
    return [g, k, f, gr]


# ------------------------------------------------------------------ paint
def paint_along(T, c, P, width, dash=None, gap=None, offset=0.0, phase=0.0, closed=False, z=0.008, step=0.4,
                name="line", role=None):
    """Road paint along polyline P, centred `offset` to its left: solid, or dashes of `dash` with `gap` from `phase`.
    All pieces go into one mesh. Returns the object (None when nothing fits)."""
    Q = [Vector((p[0], p[1])) for p in P]
    if closed:
        Q = Q + [Q[0]]
    path = jx.Path(Q)
    total = path.length
    if dash is None:
        spans = [(0.0, total)]
    else:
        spans, s = [], phase
        while s < total:
            spans.append((s, s + dash))
            s += dash + gap
    verts, faces, uvs = [], [], []
    for s0, s1 in spans:
        s0, s1 = max(0.0, s0), min(total, s1)
        if s1 - s0 < 0.05:
            continue
        n = max(1, int(math.ceil((s1 - s0) / step)))
        base = len(verts)
        for k in range(n + 1):
            s = s0 + (s1 - s0) * k / n
            p = path.at(s)[0]
            t = path.at(min(total, s + 0.05))[0] - path.at(max(0.0, s - 0.05))[0]
            t = t.normalized() if t.length > 1e-9 else Vector((1, 0))
            nl = Vector((-t.y, t.x))
            a, b = p + nl * (offset - width / 2), p + nl * (offset + width / 2)
            verts += [(a.x, a.y, z), (b.x, b.y, z)]
            uvs += [(a.x, a.y), (b.x, b.y)]
            if k:
                i = base + 2 * k
                faces.append((i - 2, i, i + 1, i - 1))
    if not faces:
        return None
    o = W.mesh_obj(name, verts, faces, T.paint, c, uvs=uvs)
    o["role"] = role or name
    o["width"] = width
    o["dash"] = dash or 0.0
    o["gap"] = gap or 0.0
    return o


def paint_quads(T, c, quads, name="paint", role=None, z=0.008):
    """Rectangles (4 points each, any winding) as one painted mesh."""
    verts, faces, uvs = [], [], []
    for q in quads:
        q = [Vector((p[0], p[1])) for p in q]
        area = sum(q[i].x * q[(i + 1) % 4].y - q[(i + 1) % 4].x * q[i].y for i in range(4))
        if area < 0:
            q.reverse()
        base = len(verts)
        verts += [(p.x, p.y, z) for p in q]
        uvs += [(p.x, p.y) for p in q]
        faces.append(tuple(range(base, base + 4)))
    if not faces:
        return None
    o = W.mesh_obj(name, verts, faces, T.paint, c, uvs=uvs)
    o["role"] = role or name
    return o


# ------------------------------------------------------------------ signs (Commons files only, via signs.py)
def setup_signs(assets):
    """signs.setup plus a reset of its material cache: signs.py keeps materials in a module dict, which go stale when
    a new scene is created (read_factory_settings) in the same process."""
    if SG is None:
        return False
    SG._mats.clear()
    try:
        SG.setup(assets)
        return True
    except FileNotFoundError:
        SG.SIGN_DIR = None
        return False


def _norm_stack(stack):
    out = []
    for sid, w in stack:
        s, i = (SG.DEFAULT_SET if SG else "de-core", sid) if isinstance(sid, str) else sid
        out.append((s, i, w))
    return out


def have_sign(set_, id_):
    return bool(SG is not None and SG.SIGN_DIR) and os.path.exists(os.path.join(SG.SIGN_DIR, set_, f"{id_}.png"))


def sign_title(set_, id_):
    """The Commons file title of a library sign ('' when unknown)."""
    import json
    if not (SG is not None and SG.SIGN_DIR):
        return ""
    p = os.path.join(SG.SIGN_DIR, set_, "sources.json")
    if not os.path.exists(p):
        return ""
    return json.load(open(p, encoding="utf-8")).get(id_, {}).get("title", "")


def _stub(st, c, loc, rz, bottom, name):
    """Test-only stand-in for a missing sign file: magenta plates named STUB_<id>. Never rendered in stills."""
    root = bpy.data.objects.new(name, None)
    c.objects.link(root)
    root.location = loc
    root.rotation_euler = (0, 0, rz)
    m = bpy.data.materials.get("STUB_PLACEHOLDER") or W.principled("STUB_PLACEHOLDER", (1, 0, 1), 0.5,
                                                                   emit=(1, 0, 1), estr=1.0)
    z = bottom
    for _s, i, w in reversed(st):
        o = W.mesh_obj(f"STUB_{i}", [(-w / 2, -0.003, z), (w / 2, -0.003, z), (w / 2, -0.003, z + w),
                                     (-w / 2, -0.003, z + w)], [(0, 1, 2, 3)], m, c)
        o.parent = root
        o["stub"] = True
        z += w + 0.06
    p = TN.cyl(name + "_post", c, (0, 0.05, z / 2), 0.03, z, m, 12)
    p.parent = root
    root["stub"] = True
    return root


def sign_stack(records, stack, c, loc, rz, bottom=SIGN_BOTTOM, name="signs", **meta):
    """Post with Commons signs, top to bottom: stack = [(id or (set, id), width)]. loc = (x, y, z of the foot).
    Appends a record (ids, position, facing, stub flag) to `records` and returns the root empty."""
    st = _norm_stack(stack)
    loc = (loc[0], loc[1], loc[2] if len(loc) > 2 else 0.0)
    missing = [f"{s}/{i}" for s, i, _w in st if not have_sign(s, i)]
    if not missing:
        root = SG.assembly([((s, i), w) for s, i, w in st], c, loc, rz, bottom, name=name)
        stub = False
    elif ALLOW_STUB:
        root = _stub(st, c, loc, rz, bottom, name)
        stub = True
    else:
        raise FileNotFoundError("signs missing from the library (fetch first): " + ", ".join(missing))
    root["signs"] = ",".join(i for _s, i, _w in st)
    records.append(dict(name=root.name, ids=[i for _s, i, _w in st], sets=[s for s, _i, _w in st],
                        widths=[w for _s, _i, w in st], loc=(loc[0], loc[1]), z=loc[2], rz=rz, bottom=bottom,
                        stub=stub, **meta))
    return root


# ------------------------------------------------------------------ cars
def animate(car, path, sv, frames, ind=None):
    """Drive a jx.hero car along `path` with (s, v) per frame. Uses kit/motion.py when it exists (wheel spin,
    steering, lights), else jx.drive + jx.brake_lights. ind: None or (side 'L'/'R', t0, t1) for the indicator."""
    if MO is not None:
        try:
            wb = 0.55 * car["L"]
            track = []
            for (s, v) in sv:
                pf, _ = path.at(s + wb / 2)
                pr, _ = path.at(s - wb / 2)
                p, _ = path.at(s)
                dd = pf - pr
                f = len(track) + 1
                on = ind[0] if ind and ind[1] * jx.FPS <= f - 1 <= ind[2] * jx.FPS else None
                track.append({"x": p.x, "y": p.y, "z": 0.0, "yaw": math.atan2(dd.y, dd.x), "v": v, "ind": on})
            MO.bake(MO.rig(car), track)
            car["track"] = [(t["x"], t["y"], 0.0) for t in track]
            return car
        except Exception as ex:  # noqa: BLE001
            print("WARN motion.bake failed, falling back to jx.drive:", ex, flush=True)
    jx.drive(car, path, sv, frames)
    jx.brake_lights(car, sv)
    if ind:
        jx.blink(car, ind[0], ind[1], ind[2])
    return car


# ------------------------------------------------------------------ scene and dressing for new layouts
def new_scene(assets, heroes=()):
    """Fresh scene with the town look (same materials, fleet and flora as townstage.build)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    W.setup(assets, None)
    lib = W.coll("lib")
    env = W.coll("env")
    traffic = W.coll("traffic")
    cars, vans, _trucks = stage.fleet(lib)
    hero_cars = {h[2]: jx.hero(h[0], h[1], h[2], h[3], lib, traffic, metal=h[4]) for h in heroes}
    M = W.Mats()
    T = TN.TownMats(M)
    groups = flora.library(lib)
    autumn = [flora.leaf_mat("leaf_autumn_a", (0.42, 0.2, 0.02), (0.62, 0.38, 0.05)),
              flora.leaf_mat("leaf_autumn_b", (0.35, 0.28, 0.03), (0.55, 0.45, 0.08))]
    trees = list(groups["decid"].children)
    for k, t in enumerate(trees[:2]):
        for o in t.objects:
            if o.name.startswith("crown"):
                o.data.materials[0] = autumn[k]
    setup_signs(assets)
    return dict(T=T, M=M, lib=lib, env=env, traffic=traffic, cars=cars, vans=vans, fleet={**cars, **vans},
                heroes=hero_cars, groups=groups, trees=trees, conifers=list(groups["conif"].children),
                bushes=list(groups["bush"].children), houses=[], parked=[], furniture=dict(signals={}))


def fields(o):
    """Switch a farmland mesh to the October field patchwork of world.fields_material (its 'far' attribute = 1)."""
    attr = o.data.color_attributes.get("far") or o.data.color_attributes.new("far", "FLOAT_COLOR", "POINT")
    for k in range(len(o.data.vertices)):
        attr.data[k].color = (1.0, 1.0, 1.0, 1.0)
    return o


def wear(T, c, strips, seed=0, name="wear"):
    """Road wear the town asphalt lacks at a glance: slightly darker, smoother wheel tracks along the given lane
    centre polylines and a few dark crack-seal lines and patches (decals 2 mm above the asphalt). strips: list of
    (polyline, lane centre offsets)."""
    rnd = random.Random(seed)
    if not hasattr(T, "track_mat"):
        T.track_mat = W.principled("wheel_track", (0.024, 0.025, 0.027), 0.6)
        T.seal_mat = W.principled("crack_seal", (0.012, 0.012, 0.013), 0.35)
        T.patch_mat = W.noisy("asphalt_patch", (0.028, 0.029, 0.031), (0.045, 0.046, 0.049), 3.0, rough=0.8,
                              coord="UV")
    out = []
    for P, offs in strips:
        for off in offs:
            for side in (-0.75, 0.75):
                o = paint_along(T, c, P, 0.42, offset=off + side, z=0.0025, name=name + "_track", role="wear")
                if o:
                    o.data.materials[0] = T.track_mat
                    o.visible_shadow = False
                    out.append(o)
    for P, _offs in strips:
        path = jx.Path([Vector((p[0], p[1])) for p in P])
        for _k in range(int(path.length / 14)):
            s = rnd.uniform(0, path.length)
            p, h = path.at(s)
            t = Vector((math.cos(h), math.sin(h)))
            n = Vector((-t.y, t.x))
            if rnd.random() < 0.55:
                # crack seal: a thin wandering dark line
                pts, q = [], p + n * rnd.uniform(-2.2, 2.2)
                ang = h + rnd.uniform(-1.2, 1.2)
                for _j in range(rnd.randint(5, 12)):
                    pts.append(q.copy())
                    ang += rnd.uniform(-0.5, 0.5)
                    q = q + Vector((math.cos(ang), math.sin(ang))) * rnd.uniform(0.3, 0.7)
                o = paint_along(T, c, pts, rnd.uniform(0.025, 0.05), z=0.0028, name=name + "_seal", role="wear")
                if o:
                    o.data.materials[0] = T.seal_mat
                    o.visible_shadow = False
                    out.append(o)
            else:
                # rectangular repair patch across part of the lane
                w_, l_ = rnd.uniform(0.8, 2.4), rnd.uniform(1.2, 3.5)
                cpt = p + n * rnd.uniform(-1.8, 1.8)
                q = [cpt + t * (sa * l_ / 2) + n * (sb * w_ / 2) for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                o = paint_quads(T, c, [q], name=name + "_patch", role="wear", z=0.0022)
                o.data.materials[0] = T.patch_mat
                o.visible_shadow = False
                out.append(o)
    return out


def house_depth(sd):
    r = random.Random(sd)
    r.uniform(9.0, 11.5)
    return r.uniform(8.5, 10.5)


def facing_rz(f):
    """Rotation of a town.house (street side -y) so its front faces direction f."""
    return math.atan2(f[1], f[0]) + math.pi / 2


class Dresser:
    """Houses with gardens, lamps, farmland, tree belts and country roads around a new junction layout, the same
    recipe as townstage.build (so every stage shares the approved look)."""

    def __init__(self, S, seed, keep_out=None):
        self.S, self.T, self.env = S, S["T"], S["env"]
        self.rnd = random.Random(seed)
        self.seeds = iter(range(100 + seed * 50, 400 + seed * 50))
        self.keep_out = keep_out or (lambda p: abs(p.x) < 17 and abs(p.y) < 17)
        self.driveway_cars = 0.55
        self.extra_trees = 1

    def house(self, cx, cy, rz, sd=None, setback=None):
        sd = next(self.seeds) if sd is None else sd
        setback = self.rnd.uniform(4.5, 6.5) if setback is None else setback
        hc = TN.house(self.T, self.S["lib"], f"house{sd}", sd)
        e = TN.place(hc, (cx, cy, TN.KERB_H), rz, self.env, name=f"h{sd}")
        g = hc.objects[f"house{sd}_root"]
        self.S["houses"].append((e, g))
        self.garden(cx, cy, rz, g, setback)
        return e

    def house_facing(self, front_pt, f, along=None):
        """A house whose property line passes through front_pt (2D) and whose front faces direction f."""
        sd = next(self.seeds)
        setback = self.rnd.uniform(4.5, 6.5)
        d = house_depth(sd)
        f = Vector(f).normalized()
        c_ = Vector(front_pt) - f * (setback + d / 2)
        return self.house(c_.x, c_.y, facing_rz(f), sd, setback)

    def garden(self, cx, cy, rz, g, setback):
        T, env, rnd = self.T, self.env, self.rnd
        trees, conifers, bushes = self.S["trees"], self.S["conifers"], self.S["bushes"]

        def l2w(lx, ly):
            c_, s_ = math.cos(rz), math.sin(rz)
            return Vector((cx + lx * c_ - ly * s_, cy + lx * s_ + ly * c_))
        w, d = g["w"], g["d"]
        gx, dx_ = g["garage_x"], g["door_x"]
        y_pl = -(d / 2 + setback)
        x_lo, x_hi = -10.0, 10.0
        gaps = sorted([(dx_ - 0.75, dx_ + 0.75)] + ([(gx - 1.7, gx + 1.7)] if g["garage"] else []))
        segs, x = [], x_lo
        for a, b in gaps:
            if a > x:
                segs.append((x, a))
            x = max(x, b)
        if x < x_hi:
            segs.append((x, x_hi))
        kind = rnd.choice(("hedge", "hedge", "fence", "low"))
        for a, b in segs:
            if b - a < 0.4:
                continue
            pa, pb = l2w(a, y_pl + 0.45), l2w(b, y_pl + 0.45)
            if kind == "hedge":
                TN.hedge(T, env, pa, pb, h=rnd.uniform(0.9, 1.5))
            elif kind == "fence":
                TN.fence(T, env, pa, pb)
            else:
                TN.hedge(T, env, pa, pb, h=0.55, t=0.5)
        if g["garage"] and rnd.random() < self.driveway_cars and setback > 5.0:
            # a car on the driveway in front of the garage, nose to the house
            p = l2w(gx, y_pl + 2.6)
            k_ = rnd.choice(list(self.S["fleet"]))
            e = bpy.data.objects.new("drive_" + k_, None)
            e.instance_type = "COLLECTION"
            e.instance_collection = self.S["fleet"][k_]
            e.location = (p.x, p.y, TN.KERB_H + 0.01)
            e.rotation_euler = (0, 0, rz + rnd.uniform(-0.05, 0.05))
            env.objects.link(e)
            self.S["parked"].append(e)
        for (a, b, m) in [(dx_ - 0.6, dx_ + 0.6, T.pavers)] + ([(gx - 1.5, gx + 1.5, T.drive)] if g["garage"] else []):
            q = [l2w(a, y_pl), l2w(b, y_pl), l2w(b, -d / 2), l2w(a, -d / 2)]
            flat_poly("path", q, TN.KERB_H + 0.01, m, env)
        if rnd.random() < 0.7:
            for k, kind_ in enumerate(rnd.sample(["grey", "blue", "brown", "yellow"], rnd.randint(1, 3))):
                p = l2w(dx_ + 1.2 + k * 0.7, y_pl + 1.1)
                TN.wheelie_bin(T, env, (p.x, p.y), kind_, rz)
        for _k in range(rnd.randint(1 + self.extra_trees, 3 + self.extra_trees)):
            lx = rnd.choice((-1, 1)) * rnd.uniform(w / 2 + 2.5, w / 2 + 5)
            ly = rnd.uniform(-d / 2, d / 2 + 8)
            p = l2w(lx, ly)
            if self.keep_out(p):
                continue
            src = rnd.choice(trees if rnd.random() < 0.75 else conifers)
            W.instance(src, (p.x, p.y, TN.KERB_H), rz=rnd.uniform(0, 6.3), s=rnd.uniform(0.8, 1.15), c=env)
        for _k in range(rnd.randint(1, 3)):
            lx = rnd.uniform(-w / 2, w / 2)
            ly = rnd.uniform(y_pl + 1.5, -d / 2 - 1.2)
            if abs(lx - dx_) < 1.2 or (g["garage"] and abs(lx - gx) < 2):
                continue
            p = l2w(lx, ly)
            W.instance(rnd.choice(bushes), (p.x, p.y, TN.KERB_H - 0.1), rz=rnd.uniform(0, 6.3),
                       s=rnd.uniform(0.35, 0.55), c=env)

    def arm_row(self, arm, side, u0, n, kerb_v, step=21.0):
        """n houses along arm (side +1: right of inbound traffic, -1: left), the first at u0. kerb_v: lateral of
        the kerb face on that side (positive number)."""
        d, nn = arm_frame(arm)
        for k in range(n):
            u = u0 + step * k
            pl = d * u + nn * (side * (kerb_v + PL))
            self.house_facing(pl, -nn * side)

    def farmland(self, arms, hw, inner=240.0, big=2600.0):
        """Fields from the town edge to the horizon, one polygon per sector between neighbouring arms."""
        fm = W.fields_material(self.S["M"])
        e_ = hw + 1.0
        angs = sorted(ARM_ANGLE[a] % (2 * math.pi) for a in arms)
        for i, a0 in enumerate(angs):
            a1 = angs[(i + 1) % len(angs)]
            if a1 <= a0:
                a1 += 2 * math.pi
            d0 = Vector((math.cos(a0), math.sin(a0)))
            l0 = Vector((-d0.y, d0.x))
            d1 = Vector((math.cos(a1), math.sin(a1)))
            l1 = Vector((-d1.y, d1.x))
            mids = [math.pi / 4 + k * math.pi / 2 for k in range(-4, 12)]
            mids = [m for m in mids if a0 < m < a1]
            q = [d0 * inner + l0 * e_, d0 * big + l0 * e_]
            q += [Vector((math.cos(m), math.sin(m))) * big * math.sqrt(2) for m in mids]
            q += [d1 * big - l1 * e_, d1 * inner - l1 * e_]
            q += [Vector((math.cos(m), math.sin(m))) * inner * math.sqrt(2) for m in reversed(mids)]
            fields(flat_poly("farmland", q, TN.KERB_H - 0.03, fm, self.env, uv=False))

    def country_roads(self, arms, hw, inner=240.0, big=2600.0):
        for a in arms:
            q = [arm_pt(a, inner - 1, -(hw + 1)), arm_pt(a, big, -(hw + 1)), arm_pt(a, big, hw + 1),
                 arm_pt(a, inner - 1, hw + 1)]
            flat_poly("country_road", q, 0.0, self.T.asph, self.env)

    def tree_belt(self, arms, n=260, seed_add=77):
        trng = random.Random(self.rnd.random() + seed_add)
        trees, conifers = self.S["trees"], self.S["conifers"]
        for _k in range(n):
            r_ = trng.uniform(150, 900)
            a_ = trng.uniform(0, 2 * math.pi)
            p = Vector((r_ * math.cos(a_), r_ * math.sin(a_)))
            near = False
            for a in arms:
                d, _n = arm_frame(a)
                if p.dot(d) > 0 and abs(p.x * d.y - p.y * d.x) < 12:
                    near = True
            if near:
                continue
            W.instance(trng.choice(trees + conifers), (p.x, p.y, TN.KERB_H), rz=trng.uniform(0, 6.3),
                       s=trng.uniform(1.0, 1.6), c=self.env)

    def lamp(self, p, toward):
        """Street lamp on the footway at p (2D), arm reaching in direction `toward` over the road."""
        TN.street_lamp(self.T, self.env, (p[0], p[1]), rz=math.atan2(toward[1], toward[0]))

    def parked(self, pos, heading):
        keys = list(self.S["fleet"])
        k = self.rnd.choice(keys)
        e = bpy.data.objects.new("parked_" + k, None)
        e.instance_type = "COLLECTION"
        e.instance_collection = self.S["fleet"][k]
        e.location = (pos[0], pos[1], 0)
        e.rotation_euler = (0, 0, math.atan2(heading[1], heading[0]) - math.pi / 2)
        self.env.objects.link(e)
        self.S["parked"].append(e)
        return e


# ------------------------------------------------------------------ T-junction
class TJunction(TN.Junction):
    """Unsigned T-junction: the through street runs W-E along x, the stem runs south. Same streets, kerbs, gutters,
    footways and corner radii as the approved X junction (town.Junction)."""
    ARMS = T_ARMS

    def build(self):
        T, c, L = self.T, self.c, self.L
        W.mesh_obj("asphalt", [(-L, -L, 0), (L, -L, 0), (L, L, 0), (-L, L, 0)], [(0, 1, 2, 3)], T.asph, c,
                   uvs=[(-L, -L), (L, -L), (L, L), (-L, L)])
        for sx in (-1, 1):
            P = self.kerb_line(sx, -1)
            self.kerbs[(sx, -1)] = P
            self.block(P, sx, -1)
        hy = self.hw_ew
        P = [Vector((x, hy)) for x in (-L, -120.0, -60.0, -20.0, 0.0, 20.0, 60.0, 120.0, L)]
        self.kerbs[(0, 1)] = P
        kerb_block(T, c, P, [(L, L), (-L, L)], name="north")


def dress_t(S, J, seed, parked=True):
    D = Dresser(S, seed)
    hx, hy = J.hw_ns, J.hw_ew
    rnd = D.rnd
    for x in range(-105, 106, 21):
        D.house_facing((x + rnd.uniform(-1.5, 1.5), hy + PL), (0, -1))
    for sx in (-1, 1):
        for k in range(6):
            D.house_facing((sx * (hx + PL), -(hy + 16.0 + 21.0 * k + 5.0)), (-sx, 0))
        for k in range(5):
            D.house_facing((sx * (hx + 36.0 + 21.0 * k), -(hy + PL)), (0, 1))
    wear(S["T"], S["env"], [([arm_pt(a, u, 0.0) for u in (HW + R_KERB, 200.0)], [1.5, -1.5]) for a in T_ARMS],
         seed=seed)
    D.farmland(T_ARMS, HW)
    D.country_roads(T_ARMS, HW)
    D.tree_belt(T_ARMS)
    for y in (-58, -24):
        D.lamp((hx + TN.KERB_W + 0.6, y), (-1, 0))
    for x in (-60, -26, 24, 58):
        D.lamp((x, hy + TN.KERB_W + 0.6), (0, -1))
    for sx in (-1, 1):
        TN.gully(S["T"], S["env"], sx * (hx - 0.18), -(hy + R_KERB + 3), rz=math.pi / 2)
        TN.gully(S["T"], S["env"], sx * (hx + R_KERB + 3), -(hy - 0.18))
    for p in ((0.4, -14), (-0.5, -31), (18, -0.3), (-27, 0.5), (49, 0.3)):
        TN.manhole(S["T"], S["env"], *p)
    if parked:
        for (x, y), hd in (((hx - 1.05, -52.0), (0, 1)), ((-(hx - 1.05), -38.0), (0, -1)),
                           ((44.0, -(hy - 1.05)), (1, 0)), ((-41.0, hy - 1.05), (-1, 0)),
                           ((-47.5, hy - 1.05), (-1, 0)), ((62.0, hy - 1.05), (-1, 0))):
            D.parked((x, y), hd)
    return D


# ------------------------------------------------------------------ bending priority road
def bend_plate(own, priority):
    sides = frozenset(screen_side(own, a) for a in priority)
    if sides not in PLATES_X:
        raise ValueError(f"no Zusatzzeichen 1002 for sides {sorted(sides)}")
    return PLATES_X[sides]


def bend_furniture(T, c, records, priority=("S", "W"), hw=HW, R=R_KERB, arms=X_ARMS):
    """Signs and paint for an X junction whose priority road turns from arm priority[0] to priority[1] (adjacent
    arms). Priority arms: Zeichen 306 over the 1002 plate. Side arms: Zeichen 205 over the 1002 plate. Paint: the
    outer edge of the bending priority road across the side-road mouths as a broken Breitstrich (0.25 m, 1.5 m dash,
    1.5 m gap), Leitlinie (0.12 m, 3 m / 6 m) on the priority arms."""
    p1, p2 = priority
    d1, _ = arm_frame(p1)
    d2, _ = arm_frame(p2)
    corner = d1 + d2
    if abs(abs(corner.x) - 1) > 1e-6 or abs(abs(corner.y) - 1) > 1e-6:
        raise ValueError("the priority road must bend between two neighbouring arms")
    sx, sy = round(corner.x), round(corner.y)
    cen = Vector((sx * (hw + R), sy * (hw + R)))
    # outer edge of the bending road: the two outer kerb lines joined by an arc round the corner kerb's centre,
    # painted just inside the cobble gutter
    rad = R + 2 * hw - TN.GUTTER - BROAD / 2
    a0 = math.atan2(0.0, -sx)
    a1 = math.atan2(-sy, 0.0)
    da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    arc = TN.arc(cen.x, cen.y, rad, a0, a0 + da, 48)
    edge = paint_along(T, c, arc, BROAD, dash=1.5, gap=1.5, name="bend_edge", role="bend_edge")
    centre = []
    for a in priority:
        centre.append(paint_along(T, c, [arm_pt(a, hw + R, 0.0), arm_pt(a, 120.0, 0.0)], NARROW, dash=LEIT_DASH,
                                  gap=LEIT_GAP, phase=1.0, name="centre_" + a, role="leitlinie"))
    # Leitlinie through the bend, 1:1 inside the junction (road_spec section 6)
    mid = TN.arc(cen.x, cen.y, R + hw, a0, a0 + da, 48)
    centre.append(paint_along(T, c, mid, NARROW, dash=3.0, gap=3.0, phase=0.5, name="centre_bend",
                              role="leitlinie_bend"))
    for a in arms:
        d, _n = arm_frame(a)
        loc = arm_pt(a, hw + R + 4.0, hw + SIGN_BACK)
        plate = bend_plate(a, priority)
        if a in priority:
            stack = [("306", SIZE["diamond"]), (("de-junctions", plate), SIZE["plate"])]
            role = "priority"
        else:
            stack = [("205", SIZE["triangle"]), (("de-junctions", plate), SIZE["plate"])]
            role = "give_way"
        sign_stack(records, stack, c, (loc.x, loc.y, TN.KERB_H), TN.facing((-d.x, -d.y)), name="bend_" + a,
                   arm=a, role=role, plate=plate)
    return dict(edge=edge, centre=centre, arc=arc, arc_centre=cen, arc_radius=rad, mid_radius=R + hw)


# ------------------------------------------------------------------ build
def build(src, kind="t", seed=4, heroes=(), parked=True, dress=True, c=None, priority=("S", "W"), L=240.0):
    """kind 't': unsigned T-junction (stem from the south); kind 'bend': X junction with a bending priority road
    (priority[0] -> priority[1]). src is an assets path (new scene, full town dressing, returns a stage dict like
    townstage.build) or a town.TownMats (adds only the junction to the current scene, into collection c)."""
    records = []
    if kind == "bend":
        if isinstance(src, str):
            import townstage as TS
            S = TS.build(src, "plain", seed=seed, heroes=heroes, parked=parked)
            setup_signs(src)
            for o in S["env"].objects:
                if o.name.startswith("farmland"):
                    fields(o)
            wear(S["T"], S["env"], [([arm_pt(a, u, 0.0) for u in (HW + R_KERB, 200.0)], [1.5, -1.5])
                                    for a in X_ARMS], seed=seed)
        else:
            cc = c or W.coll("junction")
            S = dict(T=src, M=src.M, env=cc, J=TN.Junction(src, cc, L=L), houses=[], parked=[], heroes={})
        S["bend"] = bend_furniture(S["T"], S["env"], records, priority)
    elif kind == "t":
        if isinstance(src, str):
            S = new_scene(src, heroes)
            S["J"] = TJunction(S["T"], S["env"], L=L)
            if dress:
                dress_t(S, S["J"], seed, parked)
        else:
            cc = c or W.coll("junction")
            S = dict(T=src, M=src.M, env=cc, J=TJunction(src, cc, L=L), houses=[], parked=[], heroes={})
    else:
        raise ValueError("kind must be 't' or 'bend' (roundabouts: kit/roundabout.py)")
    S["kind"] = kind
    S["signs"] = records
    S["priority"] = tuple(priority) if kind == "bend" else ()
    S["arms"] = T_ARMS if kind == "t" else X_ARMS
    S["lane_path"] = lambda e, x, lane=0, L=95.0: lane_path(e, x, lane, kind=kind, L=L, priority=priority)
    return S
