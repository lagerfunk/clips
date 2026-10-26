"""Lane management for the Drive Like a Local Autobahn kit: overhead LED gantries (Anzeigequerschnitte) with one
variable message unit above each lane, lane signals (StVO section 37 Abs. 3) and temporary hard-shoulder running
(TSF). Everything stands on the frozen world.Road and is placed with its public functions (point, frame, matrix,
strip, place); world.py and stage.py are not changed.

Spec (sources for every number in reports/lanemgmt.md):
- gantries every 1.5 to 2 km; speeds 40, 60, 80, 100, 120, 130 km/h; warning symbols on the same units
- lane signals: red crossed bars = lane closed, green arrow pointing down = lane open, flashing yellow arrow pointing
  down to one side = change lane to that side
- hard-shoulder running: at most 100 km/h on every lane while the shoulder is open; emergency bays at least every
  1,000 m, at least 80 m long and 3.00 m wide; shoulder lane at least 3.25 m (3.50 m used here)
Signs only through signs.py (Commons pictures, unaltered, shown on the LED units with an emissive look). The lane
signals are lights, built here as LED dot matrices; they are not signs from the catalogue.

    import lanemgmt as LM
    LM.setup(ASSETS)                                   # after stage.build_world
    g = LM.Gantry(road, M, env, lib, s=520.0)          # or LM.gantry_series(road, M, env, lib, 500, 2400)
    g.units[0].set("main", "X", frame=1)               # red X over the left lane
    g.units[1].set("main", 80, frame=1)                # speed sign 274-80 (Commons picture) on the LED unit
    g.units[1].set("top", "101", frame=1)              # warning sign above it
    g.units[2].set("main", "L", frame=90)              # flashing yellow arrow: move left, from frame 90
    hs = LM.HardShoulder(road, M, env, lib, 300.0, 2300.0, avoid=[520.0])
    hs.open([g], frame=1, speed=100)                   # green arrow over the shoulder, 100 on every lane
"""
import json
import math
import os
import struct
import tempfile
import zlib
from functools import lru_cache

import bpy
import numpy as np
from mathutils import Vector

import signs as SG
import stage
import world as W

try:  # the vehicles agent's motion module; fall back to stage.bake_motion until it is merged
    import motion as MO
except Exception:  # noqa: BLE001
    MO = None

HERE = os.path.dirname(os.path.abspath(__file__))
SET = "de-lanemgmt"
CORE = "de-core"
FPS = 30

# ---------------------------------------------------------------- spec numbers
LANES = (4.625, 8.375, 12.125)       # lane centres of the RQ 36 carriageway in world.py (3 x 3.75 m from x = 2.75)
EDGE_R = 14.15                       # centre of the right edge line (0.30 m, 14.0 .. 14.3)
PAVED_R = 16.8                       # outer edge of the paved hard shoulder in world.py
GANTRY_SPACING = (1500.0, 2000.0)    # m between gantries
SPEEDS = (40, 60, 80, 100, 120, 130)  # km/h shown on the units
TSF_MAX_KMH = 100                    # every lane while the hard shoulder is open
TSF_LANE_W = 3.50                    # shoulder lane (edge line centre to outer edge line centre), minimum 3.25
BAY_LEN, BAY_W, BAY_MAX_GAP = 80.0, 3.0, 1000.0
BAY_TAPER = 15.0                     # entry and exit taper of a bay: modelling choice, UNVERIFIED
FLASH_HALF = 15                      # yellow arrow flashing, frames on / off (1 Hz): UNVERIFIED rate
LED_EMIT = 3.2                       # emission of the sign pictures on the LED units
UNIT_W, UNIT_H, UNIT_D = 1.9, 3.3, 0.42
UNIT_Z = 5.2                         # bottom of the units above the road
TRUSS_Z = (6.9, 8.4)                 # bottom and top chords
TRUSS_Y = 0.55                       # chords at y = +-0.55 (front and back of the box truss)


# ---------------------------------------------------------------- signs (only through signs.py)
STUB = None
_REAL = None


@lru_cache(None)
def _list_ids(set_):
    p = os.path.join(HERE, "..", "signs", set_ + ".json")
    try:
        return frozenset(e["id"] for e in json.load(open(p, encoding="utf-8"))["signs"])
    except OSError:
        return frozenset()


def _have(set_, id_):
    base = _REAL if STUB else SG.SIGN_DIR
    return bool(base) and os.path.exists(os.path.join(base, set_, id_ + ".png"))


def ref(id_):
    """(set, id) for a sign id: this module's list, then de-core; a set that has the picture wins."""
    if isinstance(id_, tuple):
        return id_
    id_ = str(id_)
    sets = [s for s in (SET, CORE) if id_ in _list_ids(s)]
    if not sets:
        raise KeyError(f"sign {id_} is in no list file: add it to signs/{SET}.json")
    for s in sets:
        if _have(s, id_):
            return (s, id_)
    return (sets[0], id_)


def speed_ref(kmh):
    return ref(f"274-{int(kmh)}")


def setup(assets, allow_stub=False):
    """signs.setup(assets). allow_stub=True is for tests and local previews only: every sign missing from the library
    becomes a magenta and black TEST STUB picture in a temporary folder. Never for stills or episodes."""
    global STUB, _REAL
    if not allow_stub:
        SG.setup(assets)
        STUB = None
        return False
    real = os.path.join(assets, "signs")
    _REAL = real if os.path.isdir(real) else None
    STUB = tempfile.mkdtemp(prefix="TEST_STUB_signs_")
    os.makedirs(os.path.join(STUB, "signs"))
    SG.setup(STUB)
    print("WARN lanemgmt: stub mode, missing signs become TEST STUB pictures (tests and local previews only)")
    return True


def available(id_):
    """True when the real Commons picture is in the library (stub pictures do not count)."""
    try:
        set_, i = ref(id_)
    except KeyError:
        return False
    return _have(set_, i)


def pick(*ids):
    """First id whose real picture is in the library; in stub mode the first id when none is (a stub is drawn)."""
    for i in ids:
        if available(i):
            return i
    return ids[0] if STUB else None


_STUB_ASPECT = (("605", (250, 1000)), ("1004", (600, 330)), ("531", (1600, 1250)), ("616", (1000, 1200)),
                ("101", (1000, 880)), ("12", (1000, 880)), ("114", (1000, 880)))


def _png(path, rgba):
    h, w = rgba.shape[:2]
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _ensure(set_, id_):
    """Stub mode: link the real picture if the library has it, else write a TEST STUB picture."""
    p = os.path.join(SG.SIGN_DIR, set_, id_ + ".png")
    if not STUB or os.path.exists(p):
        return p
    os.makedirs(os.path.dirname(p), exist_ok=True)
    src = os.path.join(_REAL, set_, id_ + ".png") if _REAL else None
    if src and os.path.exists(src):
        os.symlink(src, p)
        sj, dj = os.path.join(_REAL, set_, "sources.json"), os.path.join(os.path.dirname(p), "sources.json")
        if os.path.exists(sj) and not os.path.exists(dj):
            os.symlink(sj, dj)
        return p
    w, h = next((a for k, a in _STUB_ASPECT if id_.startswith(k)), (1000, 1000))
    w, h = 256, max(8, int(256 * h / w))
    yy, xx = np.mgrid[0:h, 0:w]
    chk = ((xx // 32 + yy // 32) % 2).astype(np.uint8) * 255
    img = np.zeros((h, w, 4), np.uint8)
    img[..., 0], img[..., 2], img[..., 3] = chk, chk, 255
    _png(p, img[::-1].copy())
    print(f"WARN TEST STUB sign picture {set_}/{id_}")
    return p


def face(id_, c, width, emit=0.0, back=True, name=None):
    set_, i = ref(id_)
    _ensure(set_, i)
    return SG.face(i, c, width, set_=set_, name=name, emit=emit, back=back)


def assembly(stack, c, loc, rz=0.0, bottom=2.0, name="signs", emit=0.0):
    st = []
    for id_, w in stack:
        s_, i = ref(id_)
        _ensure(s_, i)
        st.append(((s_, i), w))
    root = SG.assembly(st, c, loc, rz=rz, bottom=bottom, name=name, emit=emit)
    root["signs"] = ",".join(f"{s}/{i}" for (s, i), _w in st)
    return root


def road_sign(road, stack, s, x, c, name, h=-0.06, bottom=2.0):
    """A roadside sign post on the road at (s, x), readable by traffic in our direction."""
    _c, th, _f, _r, _sl = road.frame(s)
    o = assembly(stack, c, tuple(road.point(s, x, h)), rz=-th, bottom=bottom, name=name)
    o["road_s"], o["road_x"] = float(s), float(x)
    return o


# ---------------------------------------------------------------- small geometry helpers
class MB:
    """Mesh builder: tubes, boxes and polygons into one mesh (flat or smooth per face)."""

    def __init__(self):
        self.V, self.F, self.S = [], [], []

    def tube(self, p0, p1, r, seg=8, smooth=True):
        p0, p1 = Vector(p0), Vector(p1)
        z = (p1 - p0).normalized()
        x = z.orthogonal().normalized()
        y = z.cross(x)
        b = len(self.V)
        for p in (p0, p1):
            for k in range(seg):
                a = 2 * math.pi * k / seg
                self.V.append(tuple(p + (x * math.cos(a) + y * math.sin(a)) * r))
        for k in range(seg):
            k2 = (k + 1) % seg
            self.F.append((b + k, b + k2, b + seg + k2, b + seg + k))
            self.S.append(smooth)

    def box(self, c, s):
        cx, cy, cz = c
        hx, hy, hz = s[0] / 2, s[1] / 2, s[2] / 2
        b = len(self.V)
        for dz in (-hz, hz):
            for dx, dy in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)):
                self.V.append((cx + dx, cy + dy, cz + dz))
        for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self.F.append(tuple(b + i for i in f))
            self.S.append(False)

    def poly(self, pts, smooth=False):
        b = len(self.V)
        self.V += [tuple(p) for p in pts]
        self.F.append(tuple(range(b, b + len(pts))))
        self.S.append(smooth)

    def obj(self, name, mat, c, parent=None):
        o = W.mesh_obj(name, self.V, self.F, mat, c)
        o.data.polygons.foreach_set("use_smooth", self.S)
        if parent is not None:
            o.parent = parent
        return o


def galvanised(name="lm_galv"):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = W.noisy(name, (0.5, 0.52, 0.53), (0.66, 0.68, 0.69), 1.6, rough=0.34, rough2=0.5, bump=0.05)
    m.node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 0.85
    return m


def mat(name, *a, **k):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    return W.principled(name, *a, **k)


def flash_mat(name, rgb, strength):
    """Emissive material whose brightness follows the object's colour (red channel 0..1), so one material serves many
    lamps that flash at different times: key obj.color per object."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (rgb[0] * 0.5, rgb[1] * 0.5, rgb[2] * 0.5, 1)
    p.inputs["Roughness"].default_value = 0.15
    p.inputs["Emission Color"].default_value = (*rgb, 1)
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(oi.outputs["Color"], sep.inputs["Color"])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = strength
    nt.links.new(sep.outputs[0], mul.inputs[0])
    nt.links.new(mul.outputs[0], p.inputs["Emission Strength"])
    return m


def key_flash(o, pairs, cycle=False):
    """Key obj.color (red channel = lamp brightness 0..1) with constant steps; cycle=True repeats the pattern."""
    for f, v in pairs:
        o.color = (v, v, v, 1.0)
        o.keyframe_insert("color", frame=f)
    for fc in stage.fcurves(o):
        if fc.data_path != "color":
            continue
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"
        if cycle and not fc.modifiers:
            fc.modifiers.new("CYCLES")


def ribbon(road, name, xfun, w, s0, s1, mat_, c, dz=0.009, step=2.0):
    """Marking or strip whose centre follows xfun(s) (tapers, shifted lanes)."""
    verts, faces, uvs = [], [], []
    s, k = s0, 0
    while True:
        x = xfun(s)
        verts += [tuple(road.point(s, x - w / 2, dz)), tuple(road.point(s, x + w / 2, dz))]
        uvs += [(abs(x - w / 2), s), (abs(x + w / 2), s)]
        if k:
            a = 2 * (k - 1)
            faces.append((a, a + 1, a + 3, a + 2))
        k += 1
        if s >= s1:
            break
        s = min(s1, s + step)
    o = W.mesh_obj(name, verts, faces, mat_, c, uvs)
    o["xs"] = [round(xfun(s0), 4), round(xfun(s1), 4)]
    return o


def ribbon_dashes(road, name, xfun, w, s0, s1, mat_, c, dash=6.0, gap=12.0, dz=0.009):
    verts, faces, uvs = [], [], []
    s = s0
    while s < s1:
        e = min(s + dash, s1)
        b = len(verts)
        for ss in (s, (s + e) / 2, e):
            x = xfun(ss)
            verts += [tuple(road.point(ss, x - w / 2, dz)), tuple(road.point(ss, x + w / 2, dz))]
            uvs += [(abs(x - w / 2), ss), (abs(x + w / 2), ss)]
        for j in range(2):
            a = b + 2 * j
            faces.append((a, a + 1, a + 3, a + 2))
        s += dash + gap
    return W.mesh_obj(name, verts, faces, mat_, c, uvs)


def band(road, name, x0fun, x1fun, s0, s1, mat_, c, dz0=0.0, dz1=None, step=2.0):
    """Surface between two lateral offsets that both vary along s."""
    dz1 = dz0 if dz1 is None else dz1
    verts, faces, uvs = [], [], []
    s, k = s0, 0
    while True:
        a_, b_ = x0fun(s), x1fun(s)
        verts += [tuple(road.point(s, a_, dz0)), tuple(road.point(s, b_, dz1))]
        uvs += [(abs(a_), s), (abs(b_), s)]
        if k:
            a = 2 * (k - 1)
            faces.append((a, a + 1, a + 3, a + 2))
        k += 1
        if s >= s1:
            break
        s = min(s1, s + step)
    return W.mesh_obj(name, verts, faces, mat_, c, uvs)


def smooth(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def smoother(u):
    u = min(1.0, max(0.0, u))
    return u * u * u * (u * (u * 6 - 15) + 10)


def root_at(road, s, x, c, name, h=0.0, yaw=0.0):
    e = bpy.data.objects.new(name, None)
    c.objects.link(e)
    e.matrix_world = road.matrix(s, x, h, yaw)
    e["road_s"], e["road_x"] = float(s), float(x)
    return e


# ---------------------------------------------------------------- traffic tracks (CONTRACTS motion format)
def cruise(s0, v, n, fps=FPS):
    """(s, v) per frame for n frames at constant speed v (m/s)."""
    return [(s0 + v * i / fps, v) for i in range(n)]


def road_track(road, sv, xfun, ind=None, z=0.0, reverse=False):
    """Per-frame track dicts {"x", "y", "z", "yaw", "v", "ind"} from (s, v) per frame and the lateral offset xfun(s).
    yaw: radians, 0 = +x (like jx.Path). ind(frame_index) -> None | "L" | "R" | "H". reverse=True: the vehicle
    drives towards -s (other carriageway, x negative); "pitch" is extra for the stage.bake_motion fallback."""
    tr = []
    for i, (s, v) in enumerate(sv):
        x = xfun(s)
        p = road.point(s, x, z)
        _c, th, _f, _r, sl = road.frame(s)
        dxds = (xfun(s + 0.5) - xfun(s - 0.5))
        yaw = (math.pi / 2 - th) - math.atan(dxds) + (math.pi if reverse else 0.0)
        tr.append({"x": p.x, "y": p.y, "z": p.z, "yaw": yaw, "v": v, "ind": ind(i) if ind else None,
                   "pitch": -math.atan(sl) if reverse else math.atan(sl)})
    return tr


def bake(obj, track, night=False):
    """motion.bake when the vehicles agent's module is there (wheels, steering, lights), else stage.bake_motion."""
    if MO is not None:
        clean = [{k: t[k] for k in ("x", "y", "z", "yaw", "v", "ind")} for t in track]
        MO.bake(MO.rig(obj), clean, night=night)
        return "motion"
    frames = list(range(1, len(track) + 1))
    locs = [(t["x"], t["y"], t["z"]) for t in track]
    rots, prev = [], None
    for t in track:
        rz = t["yaw"] - math.pi / 2
        if prev is not None:
            while rz - prev > math.pi:
                rz -= 2 * math.pi
            while rz - prev < -math.pi:
                rz += 2 * math.pi
        prev = rz
        rots.append((t.get("pitch", 0.0), 0.0, rz))
    stage.bake_motion(obj, frames, locs, rots)
    return "stage"


def instance(coll, c, name):
    e = bpy.data.objects.new(name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = coll
    c.objects.link(e)
    return e


# ---------------------------------------------------------------- LED lane signals (dot matrices)
def _sym_x(u, v):
    if max(abs(u), abs(v)) > 0.8:
        return False
    return abs(u - v) < 0.19 or abs(u + v) < 0.19


def _sym_down(u, v):
    if -0.08 <= v <= 0.84 and abs(u) < 0.17:
        return True
    if -0.84 <= v < -0.08:
        return abs(u) <= 0.64 * (v + 0.84) / 0.76
    return False


def _sym_diag(side):
    a = math.radians(45.0 if side == "R" else -45.0)
    ca, sa = math.cos(-a), math.sin(-a)

    def f(u, v):
        uu, vv = (u * ca - v * sa) / 0.9, (u * sa + v * ca) / 0.9
        return _sym_down(uu, vv)
    return f


SIGNALS = {"X": (_sym_x, (1.0, 0.0, 0.0), 3.5), "arrow": (_sym_down, (0.02, 1.0, 0.18), 3.5),
           "L": (_sym_diag("L"), (1.0, 0.5, 0.0), 4.0), "R": (_sym_diag("R"), (1.0, 0.5, 0.0), 4.0)}
# emission kept moderate so AgX keeps the colours saturated (a pure red X, not salmon); the look-dev bloom adds glow
DOTS, DOT_FIELD, DOT_R = 27, 1.36, 0.019


def dot_matrix(name, pred, c, mat_, n=DOTS, size=DOT_FIELD, r=DOT_R, y=-0.232, seg=8):
    """LED dots in the XZ plane (facing -Y), centred on x = z = 0, lit where pred(u, v) is true (u, v in -1..1)."""
    verts, faces = [], []
    for i in range(n):
        for j in range(n):
            u, v = -1 + (i + 0.5) * 2 / n, -1 + (j + 0.5) * 2 / n
            if not pred(u, v):
                continue
            cx, cz = u * size / 2, v * size / 2
            b = len(verts)
            for k in range(seg):
                a = 2 * math.pi * k / seg
                verts.append((cx + r * math.cos(a), y, cz + r * math.sin(a)))
            faces.append(tuple(range(b, b + seg)))
    return W.mesh_obj(name, verts, faces, mat_, c)


# ---------------------------------------------------------------- the variable message unit
class Unit:
    """One LED unit over a lane: slot "top" for warning signs, slot "main" for the speed sign or a lane signal.
    States: "off"; main: a speed (int km/h or "274-80"), "X", "arrow", "L", "R" (the yellow arrows flash);
    top: any sign id. set(slot, state, frame) can be called any number of times; the keys are rebuilt each time."""
    SLOT_Z = {"main": 0.92, "top": 2.42}
    SIGN_W = {"main": 1.30, "top": 1.30}

    def __init__(self, gantry, x, idx, kind="lane"):
        self.g, self.x, self.idx, self.kind = gantry, x, idx, kind
        c = gantry.c
        nm = f"{gantry.name}_u{idx}"
        self.name = nm
        self.root = bpy.data.objects.new(nm, None)
        c.objects.link(self.root)
        self.root.parent = gantry.root
        self.root.location = (x, -(TRUSS_Y + 0.06 + UNIT_D / 2), UNIT_Z)
        hs = mat("lm_housing", (0.016, 0.016, 0.018), 0.55, metal=0.3)
        front = mat("lm_front", (0.003, 0.003, 0.004), 0.38, spec=0.25)
        b = MB()
        b.box((0, 0, UNIT_H / 2), (UNIT_W, UNIT_D, UNIT_H))
        b.box((0, -UNIT_D / 2 - 0.12, UNIT_H + 0.02), (UNIT_W + 0.06, 0.34, 0.035))      # sun visor
        for sx in (-1, 1):
            b.box((sx * (UNIT_W / 2 + 0.015), -UNIT_D / 2 - 0.1, UNIT_H - 0.6), (0.03, 0.26, 1.2))
            for zc in TRUSS_Z:                                                              # brackets to the chords
                b.box((sx * 0.6, UNIT_D / 2 + 0.06, zc - UNIT_Z), (0.1, 0.16, 0.12))
        b.box((0, UNIT_D / 2 + 0.01, UNIT_H * 0.3), (UNIT_W * 0.7, 0.04, UNIT_H * 0.4))    # back service door
        b.obj(nm + "_housing", hs, c, self.root)
        f = MB()
        f.poly([(-UNIT_W / 2 + 0.05, -UNIT_D / 2 - 0.004, 0.05), (UNIT_W / 2 - 0.05, -UNIT_D / 2 - 0.004, 0.05),
                (UNIT_W / 2 - 0.05, -UNIT_D / 2 - 0.004, UNIT_H - 0.05),
                (-UNIT_W / 2 + 0.05, -UNIT_D / 2 - 0.004, UNIT_H - 0.05)])
        f.obj(nm + "_front", front, c, self.root)
        off = mat("lm_dot_off", (0.014, 0.015, 0.016), 0.3, metal=0.2)
        dots = dot_matrix(nm + "_dots_off", lambda u, v: True, c, off, y=-UNIT_D / 2 - 0.006)
        dots.parent = self.root
        dots.location.z = self.SLOT_Z["main"]
        self.syms = {"main": {}, "top": {}}
        self.events = {"main": [], "top": []}

    def _key(self, slot, state):
        if state in (None, "off"):
            return "off"
        if slot == "main" and state in SIGNALS:
            return state
        if isinstance(state, (int, float)):
            return speed_ref(int(state))
        return ref(state)          # a sign id string: "101", "274-80", "223.1-51"

    def _sym(self, slot, key):
        if key == "off" or key in self.syms[slot]:
            return
        c = self.g.c
        nm = f"{self.name}_{slot}_{key if isinstance(key, str) else key[1]}"
        if isinstance(key, str):
            pred, rgb, st = SIGNALS[key]
            m = mat(f"lm_led_{key}", (rgb[0] * 0.3, rgb[1] * 0.3, rgb[2] * 0.3), 0.25, emit=rgb, estr=st)
            o = dot_matrix(nm, pred, c, m, y=-UNIT_D / 2 - 0.009)
            o.parent = self.root
            o.location.z = self.SLOT_Z[slot]
        else:
            o = face(key, c, self.SIGN_W[slot], emit=LED_EMIT, back=False, name=nm)
            o.parent = self.root
            h = o["height"]
            o.location = (0.0, -UNIT_D / 2 - 0.012, self.SLOT_Z[slot] - h / 2)
        o["lm_state"] = key if isinstance(key, str) else f"{key[0]}/{key[1]}"
        self.syms[slot][key] = o

    def set(self, slot, state, frame=1):
        if self.kind == "lane" and slot == "main" and isinstance(state, (int, float)) and state not in SPEEDS:
            raise ValueError(f"speed {state} not shown on German gantries ({SPEEDS})")
        key = self._key(slot, state)
        self._sym(slot, key)
        self.events[slot] = [e for e in self.events[slot] if e[0] != frame] + [(frame, key)]
        self._rekey(slot)
        return self

    def state_at(self, slot, frame):
        st = "off"
        for f, k in sorted(self.events[slot], key=lambda e: e[0]):
            if f <= frame:
                st = k
        return st

    def _rekey(self, slot):
        evs = sorted(self.events[slot], key=lambda e: e[0])
        horizon = max(bpy.context.scene.frame_end, (evs[-1][0] if evs else 0) + 600)
        timeline = [(-1000, "off")] if evs and evs[0][0] > -1000 else []
        for i, (f, k) in enumerate(evs):
            f_next = evs[i + 1][0] if i + 1 < len(evs) else horizon
            if k in ("L", "R"):
                t, on = f, True
                while t < f_next:
                    timeline.append((t, k if on else "off"))
                    on = not on
                    t += FLASH_HALF
            else:
                timeline.append((f, k))
        for k, o in self.syms[slot].items():
            o.animation_data_clear()
            for f, vis in timeline:
                hidden = vis != k
                o.hide_render = hidden
                o.hide_viewport = hidden
                o.keyframe_insert("hide_render", frame=f)
                o.keyframe_insert("hide_viewport", frame=f)


# ---------------------------------------------------------------- the gantry
def gantry_frame(M, lib, x0=0.95, x1=19.2, name="lm_gantry_frame"):
    """Steel box truss on two round posts with concrete foundations, a maintenance walkway with handrail behind the
    units, a caged ladder on the right post and a roadside cabinet. Local: x across the road, y along it (traffic
    towards +y), z up; built once into lib and instanced per gantry."""
    key = f"{name}_{x0:.2f}_{x1:.2f}"
    if key in bpy.data.collections:
        return bpy.data.collections[key]
    root = bpy.data.collections.new(key)
    lib.children.link(root)
    steel = galvanised()
    grate = mat("lm_grating", (0.2, 0.21, 0.22), 0.55, metal=0.7)
    z0, z1 = TRUSS_Z
    ty = TRUSS_Y
    t = MB()
    xa, xb = x0 + 0.28, x1 - 0.28
    for y in (-ty, ty):
        for z in (z0, z1):
            t.tube((xa, y, z), (xb, y, z), 0.085, 10)
    n = max(2, int(round((xb - xa) / 1.5)))
    pts = [xa + (xb - xa) * k / n for k in range(n + 1)]
    for k, x in enumerate(pts):
        for y in (-ty, ty):
            t.tube((x, y, z0), (x, y, z1), 0.04)
        for z in (z0, z1):
            t.tube((x, -ty, z), (x, ty, z), 0.035)
        if k < n:
            xn = pts[k + 1]
            for y in (-ty, ty):
                a, b_ = ((x, y, z0), (xn, y, z1)) if k % 2 == 0 else ((x, y, z1), (xn, y, z0))
                t.tube(a, b_, 0.035)
            for z in (z0, z1):
                a, b_ = ((x, -ty, z), (xn, ty, z)) if k % 2 == 0 else ((x, ty, z), (xn, -ty, z))
                t.tube(a, b_, 0.03)
    # posts: two tubes each side, braced, with cap and base plates
    for x in (x0, x1):
        for y in (-0.35, 0.35):
            t.tube((x, y, 0.3), (x, y, z1 + 0.25), 0.2, 16)
        for z in (1.2, 2.9, 4.6, 6.3):
            t.tube((x, -0.35, z), (x, 0.35, z + 1.5), 0.045)
        t.box((x, 0, z1 + 0.27), (0.6, 1.2, 0.04))
        for y in (-0.35, 0.35):
            t.box((x, y, 0.32), (0.62, 0.62, 0.04))
    t.obj(key + "_steel", steel, root)
    con = MB()
    for x in (x0, x1):
        con.box((x, 0, -0.35), (1.3, 1.9, 1.3))
    con.obj(key + "_foundation", M.concrete, root)
    # walkway behind the units: grating deck, toe board, handrail
    wk = MB()
    wy0, wy1 = ty + 0.05, ty + 0.85
    wk.box(((xa + x1 + 0.6) / 2, (wy0 + wy1) / 2, z0 - 0.06), (x1 + 0.6 - xa, wy1 - wy0, 0.05))
    wk.obj(key + "_walkway", grate, root)
    hr = MB()
    xs = list(np.arange(xa, x1 + 0.6, 1.5)) + [x1 + 0.6]
    for x in xs:
        hr.tube((x, wy1, z0 - 0.04), (x, wy1, z0 + 1.1), 0.025)
    for z in (z0 + 0.55, z0 + 1.1):
        hr.tube((xa, wy1, z), (x1 + 0.6, wy1, z), 0.025)
    hr.box(((xa + x1 + 0.6) / 2, wy1, z0 + 0.04), (x1 + 0.6 - xa, 0.02, 0.15))
    # ladder with safety cage on the back of the right post
    lx, ly = x1 + 0.0, wy1 - 0.05
    for sx in (-0.22, 0.22):
        hr.tube((lx + sx, ly, 0.35), (lx + sx, ly, z0 - 0.04), 0.022)
    z = 0.6
    while z < z0 - 0.1:
        hr.tube((lx - 0.22, ly, z), (lx + 0.22, ly, z), 0.016)
        z += 0.28
    z = 2.5
    while z < z0:
        prev = None
        for k in range(9):
            a = math.pi * k / 8
            p = (lx + 0.36 * math.cos(a), ly + 0.36 * math.sin(a) + 0.02, z)
            if prev:
                hr.tube(prev, p, 0.014, 6)
            prev = p
        z += 0.9
    for a in (0.0, math.pi / 2, math.pi):
        hr.tube((lx + 0.36 * math.cos(a), ly + 0.36 * math.sin(a) + 0.02, 2.5),
                (lx + 0.36 * math.cos(a), ly + 0.36 * math.sin(a) + 0.02, z0 - 0.05), 0.014, 6)
    hr.obj(key + "_rail", steel, root)
    # roadside cabinet (grey, generic)
    cab = MB()
    cab.box((x1 + 1.6, 1.4, 0.85), (0.95, 0.5, 1.5))
    cab.box((x1 + 1.6, 1.4, 1.63), (1.05, 0.6, 0.06))
    cab.obj(key + "_cabinet", mat("lm_cabinet", (0.55, 0.57, 0.55), 0.45), root)
    plinth = MB()
    plinth.box((x1 + 1.6, 1.4, -0.1), (1.1, 0.65, 0.4))
    plinth.obj(key + "_plinth", M.concrete, root)
    return root


class Gantry:
    """A lane-control gantry at road position s: the instanced frame plus one Unit per lane (and one over the hard
    shoulder when shoulder_x is given). units[0] is the left lane."""

    def __init__(self, road, M, c, lib, s, lanes=LANES, shoulder_x=None, x0=0.95, x1=19.2, name=None):
        self.road, self.s, self.c = road, float(s), c
        self.name = name or f"lm_gantry_{int(round(s))}"
        self.root = root_at(road, s, 0.0, c, self.name)
        self.root["lm_gantry"] = True
        fr = gantry_frame(M, lib, x0, x1)
        e = instance(fr, c, self.name + "_frame")
        e.parent = self.root
        self.units = [Unit(self, x, i) for i, x in enumerate(lanes)]
        self.shoulder = Unit(self, shoulder_x, len(lanes), kind="shoulder") if shoulder_x is not None else None

    def all_units(self):
        return self.units + ([self.shoulder] if self.shoulder else [])

    def show(self, frame, speed=None, signals=None, warn=None):
        """Convenience: speed for every lane, signals {lane index: "X"|"arrow"|"L"|"R"} (override the speed),
        warn: sign id for every top slot (or a dict per lane index)."""
        for i, u in enumerate(self.units):
            st = (signals or {}).get(i, speed if speed is not None else "off")
            u.set("main", st, frame)
            w = warn.get(i, "off") if isinstance(warn, dict) else (warn or "off")
            u.set("top", w, frame)
        return self


def gantry_series(road, M, c, lib, s_first, s_last, spacing=1750.0, **kw):
    """Gantries from s_first every `spacing` m (must be 1.5 to 2 km) up to s_last."""
    if not GANTRY_SPACING[0] <= spacing <= GANTRY_SPACING[1]:
        raise ValueError(f"gantry spacing {spacing} m outside {GANTRY_SPACING}")
    out, s = [], s_first
    while s <= s_last + 1e-6:
        out.append(Gantry(road, M, c, lib, s, **kw))
        s += spacing
    return out


# ---------------------------------------------------------------- temporary hard-shoulder running (TSF)
class HardShoulder:
    """Hard shoulder widened to a TSF lane between s0 and s1: extra paving, an outer edge line, emergency bays (80 m
    full width, 3.0 m wide, at most 1,000 m apart, with entry and exit tapers, Zeichen 328 and an emergency phone),
    Leitpfosten moved to the new edge. open()/close() switch the gantries."""

    def __init__(self, road, M, c, lib, s0, s1, lane_w=TSF_LANE_W, bay_gap=900.0, avoid=(), signs328=True,
                 phones=True):
        if lane_w < 3.25:
            raise ValueError("a shoulder lane must be at least 3.25 m")
        if bay_gap > BAY_MAX_GAP:
            raise ValueError(f"bays at least every {BAY_MAX_GAP:.0f} m")
        self.road, self.c, self.s0, self.s1 = road, c, float(s0), float(s1)
        self.x_line = EDGE_R + lane_w                 # centre of the new outer edge line
        self.x_pave = self.x_line + 0.35              # paved edge
        self.lane_w = lane_w
        self.lane_x = (EDGE_R + self.x_line) / 2      # centre of the shoulder lane (gantry unit above it)
        paint = M.paint
        # bays: start-to-start gap <= bay_gap, keeping clear of gantry posts
        bays, s = [], self.s0 + 120.0
        while s + BAY_LEN + BAY_TAPER <= self.s1 - 60.0:
            b0 = s
            for g in avoid:
                if b0 - BAY_TAPER - 15 < g < b0 + BAY_LEN + BAY_TAPER + 15:
                    b0 = g + BAY_TAPER + 20
            if b0 + BAY_LEN + BAY_TAPER > self.s1 - 60.0:
                break
            bays.append((b0, b0 + BAY_LEN))
            s = b0 + bay_gap
        self.bays = bays

        def xb(s_):
            for a, b_ in bays:
                if a - BAY_TAPER <= s_ <= b_ + BAY_TAPER:
                    if s_ < a:
                        return self.x_pave + BAY_W * smooth((s_ - (a - BAY_TAPER)) / BAY_TAPER)
                    if s_ > b_:
                        return self.x_pave + BAY_W * smooth(((b_ + BAY_TAPER) - s_) / BAY_TAPER)
                    return self.x_pave + BAY_W
            return self.x_pave
        self.bay_edge = xb
        road.strip("tsf_paving", PAVED_R, self.x_pave, self.s0, self.s1, M.asph_sh, c, dz0=-0.002)
        for a, b_ in bays:
            band(road, f"tsf_bay_{int(a)}", lambda s_: self.x_pave, xb, a - BAY_TAPER, b_ + BAY_TAPER, M.asph_sh, c,
                 dz0=-0.002, step=1.0)
            band(road, f"tsf_bay_bank_{int(a)}", lambda s_: xb(s_), lambda s_: xb(s_) + 2.4,
                 a - BAY_TAPER, b_ + BAY_TAPER, M.grass, c, dz0=-0.002, dz1=-0.62, step=1.0)
            ribbon(road, f"tsf_bay_line_{int(a)}", lambda s_: xb(s_) - 0.18, 0.30, a - BAY_TAPER, b_ + BAY_TAPER,
                   paint, c, dz=0.006, step=1.0)
            if signs328:
                road_sign(road, [("328", 0.75)], a - BAY_TAPER - 5.0, self.x_pave + 0.9, c, f"tsf_328_{int(a)}")
            if phones:
                NR = W.emergency_phone(M, lib) if "notruf" not in bpy.data.collections else bpy.data.collections["notruf"]
                road.place(NR, (a + b_) / 2, self.x_pave + BAY_W + 0.7, -0.05, c=c, name=f"tsf_phone_{int(a)}")
        # outer edge line, broken at the bay mouths
        cuts = [(self.s0, self.s1)]
        for a, b_ in bays:
            nxt = []
            for p, q in cuts:
                if q <= a - BAY_TAPER or p >= b_ + BAY_TAPER:
                    nxt.append((p, q))
                else:
                    if p < a - BAY_TAPER:
                        nxt.append((p, a - BAY_TAPER))
                    if q > b_ + BAY_TAPER:
                        nxt.append((b_ + BAY_TAPER, q))
            cuts = nxt
        for p, q in cuts:
            road.strip(f"tsf_edge_{int(p)}", self.x_line - 0.15, self.x_line + 0.15, p, q, paint, c, dz0=0.006)
        self._move_posts()

    def _move_posts(self):
        """Leitpfosten (stage instances of the leitpfosten collection) in the section move to the new paved edge."""
        for o in list(bpy.data.objects):
            ic = o.instance_collection
            if o.type != "EMPTY" or ic is None or not ic.name.startswith("leitpfosten"):
                continue
            s, d, _z = self.road.nearest(o.location.x, o.location.y)
            _c, _th, _f, r, _sl = self.road.frame(s)
            side = (o.location - self.road.point(s, 0.0)).dot(r)
            if side <= 0 or not (self.s0 <= s <= self.s1):
                continue
            o.matrix_world = self.road.matrix(s, self.bay_edge(s) + 0.5, -0.15)

    def open(self, gantries, frame=1, speed=TSF_MAX_KMH):
        if speed > TSF_MAX_KMH:
            raise ValueError(f"hard-shoulder running allows at most {TSF_MAX_KMH} km/h")
        for g in gantries:
            for u in g.units:
                u.set("main", speed, frame)
            if g.shoulder:
                g.shoulder.set("main", "arrow", frame)
                g.shoulder.set("top", "223.1-51", frame)
        return self

    def close(self, gantries, frame=1, clear_frames=150):
        """Shoulder to be cleared (Zeichen 223.3) for clear_frames, then the red X."""
        for g in gantries:
            if g.shoulder:
                g.shoulder.set("top", "223.3-51", frame)
                g.shoulder.set("main", "X", frame + clear_frames)
        return self
