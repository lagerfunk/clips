"""People and a generic city bike for Drive Like a Local, in the look of the cars: smooth subdivision cages built
from cross-sections, clean materials, believable proportions, no brands, no logos, no crests.

    import figures as F
    p = F.person(c, "ped", height=1.68, sex="f", skin=3, hair="bob", jacket=(0.30, 0.04, 0.03), bag="shoulder")
    F.walk(p, path, sv)                     # path: jx.Path, sv: [(s, v)] per frame from frame 1 (jx.kinematics)
    F.walk(p, path, sv, ground=F.kerb_ground("x", 3.0), look=[(1.0, 2.5, 70), (2.5, 3.6, -70)])
    F.stand(p, (x, y), heading, n_frames, look=[(0.5, 2.0, (x2, y2, 1.0))], gesture=[("wave", 2.0, 3.4)])
    cy = F.cyclist(c, "cy", rider=dict(jacket=F.YELLOW), bike=dict(frame="step", basket=True))
    F.ride(cy, path, sv, signal=[("L", 1.0, 2.8)], foot="L")
    pa = F.parking_attendant(c, "pa"); F.stand(pa, (x, y), h, n, gesture=[("write", 0.0, 9.0)])
    po = F.police_officer(c, "po");    F.stand(po, (x, y), h, n, gesture=[("laser", 0.4, 9.0)])

Colours are linear RGB tuples like the rest of the kit (vehicles.car). A person is one skinned mesh (subdivision
surface on top of an armature modifier, dual-quaternion skinning) plus small rigid props parented to bones. The
armature: hips (root), spine, chest, neck, head, thigh/shin/foot/toe and upperarm/forearm/hand per side (.L is the
figure's left, -x in its own space; the figure faces +y, feet on z = 0).

Animation is computed in Python and keyed per frame (pose-bone quaternions, the root offset, the object's place on
the path): feet are planted on footprints laid along the path (heel strike, roll over, toe off), legs and arms are
solved with analytic two-bone IK, so nothing slides; arms swing against the legs; idle standing shifts weight and
turns the head. The cyclist uses the same rig: pelvis on the saddle, feet on the pedals, hands on the grips, the
crank turning with distance (development DEV metres per crank turn), wheels turning with distance, lean in turns,
hand signals and a foot put down when the bike stops.
"""
import math
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Quaternion, Vector, kdtree
from mathutils.bvhtree import BVHTree

import world as W

FPS = 30
G = 9.81
V_STOP = 0.05            # m/s: a walker below this is standing
DUTY = 0.60              # fraction of a gait cycle a foot is on the ground
DEV = 4.4                # m travelled per crank turn (city bike in a middle hub gear: 15 km/h at 57 rpm)
BRANDS = ("gazelle", "batavus", "kalkhoff", "pegasus", "hercules", "kettler", "cube", "trek", "giant", "shimano",
          "sram", "brooks", "schwalbe", "continental", "busch", "sks", "abus", "axa", "basil", "bosch", "nike",
          "adidas", "puma", "wolfskin", "north face", "zara", "h&m", "decathlon", "btwin", "riese", "mueller")


def srgb(r, g, b):
    """0..255 sRGB to the linear RGB the materials take."""
    def f(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f(r), f(g), f(b))


SKIN = [srgb(244, 210, 186), srgb(228, 186, 156), srgb(212, 160, 124), srgb(190, 136, 98), srgb(164, 112, 78),
        srgb(132, 86, 58), srgb(104, 66, 44), srgb(78, 50, 36)]
HAIR = {"black": srgb(22, 18, 16), "dark": srgb(48, 32, 22), "brown": srgb(92, 60, 36), "auburn": srgb(122, 52, 26),
        "blond": srgb(178, 142, 70), "grey": srgb(150, 146, 140), "white": srgb(210, 206, 198)}
JACKETS = [srgb(32, 42, 66), srgb(28, 28, 30), srgb(70, 72, 76), srgb(84, 92, 58), srgb(176, 138, 96),
           srgb(110, 30, 38), srgb(30, 92, 98), srgb(196, 150, 40), srgb(88, 108, 132), srgb(170, 40, 34),
           srgb(40, 78, 52), srgb(200, 190, 170)]
TROUSERS = [srgb(36, 48, 74), srgb(70, 90, 122), srgb(26, 26, 28), srgb(60, 60, 62), srgb(150, 130, 96),
            srgb(84, 62, 46)]
SHOES = [srgb(24, 22, 22), srgb(62, 40, 28), srgb(226, 224, 220), srgb(96, 98, 102), srgb(150, 104, 66)]
YELLOW = srgb(232, 196, 30)           # a yellow rain jacket
HIVIS = srgb(214, 236, 20)            # fluorescent yellow (EN ISO 20471)
NAVY = srgb(26, 32, 54)               # parking attendant uniform
POLICE_BLUE = srgb(28, 46, 92)        # German police blue (jacket)
POLICE_DARK = srgb(20, 26, 44)        # trousers, cap

_mats = {}


def _alive(idb):
    try:
        idb.name
        return True
    except (ReferenceError, AttributeError):
        return False


def _key(prefix, color):
    return prefix + "_" + "".join(f"{int(max(0.0, min(1.0, c)) * 255):02x}" for c in color)


def material(key, color, rough=0.6, metal=0.0, emit=None, estr=0.0, coat=0.0, sheen=0.0, var=0.0, scale=8.0,
             spec=0.5):
    """Cached principled material; var > 0 adds a soft noise variation of the colour (no flat plastic look). The
    noise reads Generated coordinates, which do not swim on a deforming (skinned) mesh."""
    name = _key("fig_" + key, color)
    m = _mats.get(name)
    if m is not None and _alive(m):
        return m
    m = W.principled(name, color, rough, metal=metal, emit=emit, estr=estr, coat=coat, spec=spec)
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    if sheen:
        p.inputs["Sheen Weight"].default_value = sheen
        p.inputs["Sheen Roughness"].default_value = 0.45
    if var:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = scale
        nz.inputs["Detail"].default_value = 4.0
        nt.links.new(tc.outputs["Generated"], nz.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.3
        ramp.color_ramp.elements[0].color = (*[c * (1 - var) for c in color], 1)
        ramp.color_ramp.elements[1].position = 0.7
        ramp.color_ramp.elements[1].color = (*[min(1.0, c * (1 + var)) for c in color], 1)
        nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    _mats[name] = m
    return m


def cloth(color, key="cloth", rough=0.85, var=0.07):
    return material(key, color, rough, sheen=0.4, var=var, scale=14.0)


def hair_material(color):
    """Hair: fine streaks running down the head (a distorted wave texture on Generated coordinates, so they stay
    put on the head), lighter and darker strands, a soft sheen and a matching bump. Reads as hair, not plastic."""
    name = _key("fig_hair", color)
    m = _mats.get(name)
    if m is not None and _alive(m):
        return m
    m = W.principled(name, color, 0.42, spec=0.55)
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Sheen Weight"].default_value = 0.10
    p.inputs["Sheen Tint"].default_value = (*color, 1)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    dx = nt.nodes.new("ShaderNodeMath")
    dx.operation = "SUBTRACT"
    dx.inputs[1].default_value = 0.5
    nt.links.new(sep.outputs["X"], dx.inputs[0])
    dy = nt.nodes.new("ShaderNodeMath")
    dy.operation = "SUBTRACT"
    dy.inputs[1].default_value = 0.5
    nt.links.new(sep.outputs["Y"], dy.inputs[0])
    az = nt.nodes.new("ShaderNodeMath")
    az.operation = "ARCTAN2"
    nt.links.new(dy.outputs[0], az.inputs[0])
    nt.links.new(dx.outputs[0], az.inputs[1])
    ka = nt.nodes.new("ShaderNodeMath")
    ka.operation = "MULTIPLY"
    ka.inputs[1].default_value = 9.0
    nt.links.new(az.outputs[0], ka.inputs[0])
    kz = nt.nodes.new("ShaderNodeMath")
    kz.operation = "MULTIPLY"
    kz.inputs[1].default_value = 1.2
    nt.links.new(sep.outputs["Z"], kz.inputs[0])
    cmb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(ka.outputs[0], cmb.inputs["X"])
    nt.links.new(kz.outputs[0], cmb.inputs["Y"])
    wv = nt.nodes.new("ShaderNodeTexNoise")       # streaks: fast round the head, slow from crown to ends
    wv.inputs["Scale"].default_value = 3.0
    wv.inputs["Detail"].default_value = 8.0
    wv.inputs["Roughness"].default_value = 0.6
    nt.links.new(cmb.outputs["Vector"], wv.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.2
    ramp.color_ramp.elements[0].color = (*[c * 0.62 for c in color], 1)
    ramp.color_ramp.elements[1].position = 0.9
    ramp.color_ramp.elements[1].color = (*[min(1.0, c * 1.3 + 0.01) for c in color], 1)
    nt.links.new(wv.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = 0.25
    bp.inputs["Distance"].default_value = 0.002
    nt.links.new(wv.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], p.inputs["Normal"])
    _mats[name] = m
    return m


# ------------------------------------------------------------------ mesh building
def _frame(d, fwd):
    """Ring axes (U, V) for a tube running along d: V is fwd made perpendicular to d, U = V x d (so U x V = d and
    rings go counter-clockwise around d, which makes the bridged faces point outwards)."""
    d = d.normalized()
    v = fwd - d * fwd.dot(d)
    if v.length < 1e-6:
        v = Vector((0, 0, 1)) - d * d.z
        if v.length < 1e-6:
            v = Vector((1, 0, 0)) - d * d.x
    v.normalize()
    return v.cross(d), v


def _sq(c, p):
    return math.copysign(abs(c) ** (2.0 / p), c)


def ring_pts(C, U, V, ru, rv_f, rv_b=None, n=10, p=2.0):
    """Superellipse ring around C in the (U, V) plane; rv_f is the half depth on the +V side, rv_b on the -V side."""
    rv_b = rv_f if rv_b is None else rv_b
    out = []
    for k in range(n):
        a = 2 * math.pi * k / n
        x = _sq(math.cos(a), p) * ru
        sa = _sq(math.sin(a), p)
        y = sa * (rv_f if sa > 0 else rv_b)
        out.append(C + U * x + V * y)
    return out


class Cage:
    """Vertices with bone weights, quads with material slots, edge creases and islands; builds one mesh object."""

    def __init__(self):
        self.co, self.wt, self.faces, self.fm, self.mats = [], [], [], [], []
        self.crease = {}
        self.islands = []          # (first face, last face + 1, closed)
        self.tags = {}             # name -> vertex indices (shape keys, measurements)
        self._open = None
        self.flat = set()          # face indices shaded flat (rigid parts)

    def m(self, mat):
        for i, x in enumerate(self.mats):
            if x is mat:
                return i
        self.mats.append(mat)
        return len(self.mats) - 1

    def begin(self, tag=None, closed=True):
        self._open = (len(self.faces), closed, tag, len(self.co))

    def end(self):
        f0, closed, tag, v0 = self._open
        self.islands.append((f0, len(self.faces), closed))
        if tag:
            self.tags.setdefault(tag, []).extend(range(v0, len(self.co)))
        self._open = None

    def v(self, p, w):
        self.co.append(Vector(p))
        self.wt.append(w)
        return len(self.co) - 1

    def ring(self, pts, w):
        return [self.v(p, w) for p in pts]

    def bridge(self, a, b, mat):
        n = len(a)
        for k in range(n):
            k2 = (k + 1) % n
            mm = mat[k] if isinstance(mat, (list, tuple)) else mat
            self.faces.append((a[k], a[k2], b[k2], b[k]))
            self.fm.append(self.m(mm))

    def cap(self, r, mat, start):
        self.faces.append(tuple(reversed(r)) if start else tuple(r))
        self.fm.append(self.m(mat))

    def crease_ring(self, r, val):
        for k in range(len(r)):
            self.crease[frozenset((r[k], r[(k + 1) % len(r)]))] = val

    def crease_line(self, idx, val):
        for a, b in zip(idx[:-1], idx[1:]):
            self.crease[frozenset((a, b))] = val

    def tube(self, stations, mat, caps=(True, True), crease=None):
        """stations: [(pts, weights, mat_after)] -> rings bridged in order. Returns the rings."""
        rings = [self.ring(p, w) for p, w, _m in stations]
        for i in range(len(rings) - 1):
            self.bridge(rings[i], rings[i + 1], stations[i][2] or mat)
        if caps[0]:
            self.cap(rings[0], stations[0][2] or mat, True)
        if caps[1]:
            self.cap(rings[-1], stations[-2][2] or mat, False)
        return rings

    def fix_normals(self):
        """Closed islands: flip every face of an island whose signed volume is negative (inside out)."""
        for f0, f1, closed in self.islands:
            if not closed:
                continue
            vol = 0.0
            for f in self.faces[f0:f1]:
                a = self.co[f[0]]
                for i in range(1, len(f) - 1):
                    vol += a.dot(self.co[f[i]].cross(self.co[f[i + 1]]))
            if vol < 0:
                for i in range(f0, f1):
                    self.faces[i] = tuple(reversed(self.faces[i]))

    def build(self, name, c):
        self.fix_normals()
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(p) for p in self.co], [], self.faces)
        for m in self.mats:
            me.materials.append(m)
        me.polygons.foreach_set("material_index", self.fm)
        me.polygons.foreach_set("use_smooth", [True] * len(self.faces))
        if self.crease:
            at = me.attributes.new("crease_edge", "FLOAT", "EDGE")
            vals = [0.0] * len(me.edges)
            for e in me.edges:
                vals[e.index] = self.crease.get(frozenset(e.vertices), 0.0)
            at.data.foreach_set("value", vals)
        o = bpy.data.objects.new(name, me)
        c.objects.link(o)
        groups = {}
        for i, w in enumerate(self.wt):
            for g, x in w.items():
                if x > 1e-4:
                    groups.setdefault(g, {}).setdefault(round(x, 4), []).append(i)
        for g in sorted(groups):
            vg = o.vertex_groups.new(name=g)
            for x, idx in groups[g].items():
                vg.add(idx, x, "REPLACE")
        return o


# ------------------------------------------------------------------ proportions (units of the stature H)
def _lerp_rows(rows, z):
    """Interpolate a station table [(z, ...numbers..., weights)] at height z."""
    for a, b in zip(rows[:-1], rows[1:]):
        if a[0] <= z <= b[0]:
            u = (z - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
            vals = tuple(x + (y - x) * u for x, y in zip(a[1:-1], b[1:-1]))
            w = {}
            for g in set(a[-1]) | set(b[-1]):
                w[g] = a[-1].get(g, 0.0) * (1 - u) + b[-1].get(g, 0.0) * u
            return (z,) + vals + (w,)
    r = rows[0] if z < rows[0][0] else rows[-1]
    return (z,) + tuple(r[1:])


# z, half width, half depth front, half depth back, centre y, superellipse exponent, weights
TORSO_M = [
    (0.462, 0.034, 0.030, 0.030, -0.006, 2.0, {"hips": 1.0}),
    (0.474, 0.080, 0.052, 0.058, -0.008, 2.2, {"hips": 1.0}),
    (0.505, 0.100, 0.058, 0.068, -0.008, 2.4, {"hips": 1.0}),
    (0.540, 0.104, 0.060, 0.068, -0.008, 2.4, {"hips": 1.0}),
    (0.580, 0.097, 0.060, 0.062, -0.004, 2.4, {"hips": 0.6, "spine": 0.4}),
    (0.625, 0.090, 0.060, 0.060, 0.000, 2.4, {"spine": 1.0}),
    (0.675, 0.094, 0.064, 0.064, 0.003, 2.5, {"spine": 0.5, "chest": 0.5}),
    (0.725, 0.100, 0.070, 0.066, 0.004, 2.6, {"chest": 1.0}),
    (0.768, 0.104, 0.066, 0.066, 0.000, 2.8, {"chest": 1.0}),
    (0.786, 0.108, 0.062, 0.064, -0.003, 3.0, {"chest": 1.0}),
    (0.798, 0.106, 0.054, 0.060, -0.006, 3.0, {"chest": 1.0}),
    (0.810, 0.086, 0.044, 0.052, -0.009, 2.6, {"chest": 0.85, "neck": 0.15}),
    (0.821, 0.060, 0.041, 0.045, -0.010, 2.2, {"chest": 0.7, "neck": 0.3}),
    (0.830, 0.050, 0.041, 0.043, -0.008, 2.0, {"chest": 0.5, "neck": 0.5}),
]


def _torso_rows(sex, build):
    b = {"slim": 0.92, "average": 1.0, "broad": 1.1}[build]
    rows = []
    for z, rx, yf, yb, cy, p, w in TORSO_M:
        if sex == "f":
            if z <= 0.56:
                rx *= 1.06
                yb *= 1.04
            elif z <= 0.65:
                rx *= 0.92
            elif z <= 0.74:
                rx *= 0.93
                if z >= 0.70:
                    yf += 0.010
                    cy += 0.002
            elif z <= 0.81:
                rx *= 0.92
        k = b if z < 0.82 else 1.0
        rows.append((z, rx * k, yf * (1 + (k - 1) * 0.8), yb * (1 + (k - 1) * 0.6), cy, p, w))
    return rows


def skeleton(H, sex="m", build="average"):
    """Joint positions (metres, rest pose, figure facing +y, feet on z = 0)."""
    sx_sh = 0.100 if sex == "m" else 0.092
    sx_hip = 0.051 if sex == "m" else 0.055
    b = {"slim": 0.95, "average": 1.0, "broad": 1.06}[build]
    sx_sh *= b

    def P(x, y, z):
        return Vector((x * H, y * H, z * H))
    J = {"pelvis": P(0, -0.006, 0.530), "spine": P(0, -0.004, 0.600), "chest": P(0, 0.000, 0.700),
         "neck": P(0, -0.012, 0.818), "headj": P(0, -0.006, 0.886), "top": P(0, -0.006, 1.0)}
    for side, sx in (("L", -1), ("R", 1)):
        sh = P(sx * sx_sh, -0.004, 0.792)
        el = sh + P(sx * 0.032, -0.006, -0.183)
        wr = el + P(sx * 0.010, 0.020, -0.144)
        tip = wr + P(sx * 0.003, 0.006, -0.094)
        hip = P(sx * sx_hip, 0.0, 0.512)
        kn = P(sx * (sx_hip - 0.002), 0.004, 0.285)
        an = P(sx * (sx_hip - 0.003), -0.002, 0.044)
        ball = an + P(sx * 0.003, 0.088, -0.038)
        toe = an + P(sx * 0.004, 0.120, -0.040)
        J.update({"sh" + side: sh, "el" + side: el, "wr" + side: wr, "tip" + side: tip, "hip" + side: hip,
                  "kn" + side: kn, "an" + side: an, "ball" + side: ball, "toe" + side: toe})
    return J


BONES = [  # name, head, tail, parent, connected, z axis hint
    ("hips", "pelvis", "spine", None, False, (0, 1, 0)),
    ("spine", "spine", "chest", "hips", True, (0, 1, 0)),
    ("chest", "chest", "neck", "spine", True, (0, 1, 0)),
    ("neck", "neck", "headj", "chest", True, (0, 1, 0)),
    ("head", "headj", "top", "neck", True, (0, 1, 0)),
]
for _s in ("L", "R"):
    BONES += [
        ("thigh." + _s, "hip" + _s, "kn" + _s, "hips", False, (0, 1, 0)),
        ("shin." + _s, "kn" + _s, "an" + _s, "thigh." + _s, True, (0, 1, 0)),
        ("foot." + _s, "an" + _s, "ball" + _s, "shin." + _s, True, (0, 0, 1)),
        ("toe." + _s, "ball" + _s, "toe" + _s, "foot." + _s, True, (0, 0, 1)),
        ("upperarm." + _s, "sh" + _s, "el" + _s, "chest", False, (0, 1, 0)),
        ("forearm." + _s, "el" + _s, "wr" + _s, "upperarm." + _s, True, (0, 1, 0)),
        ("hand." + _s, "wr" + _s, "tip" + _s, "forearm." + _s, True, (0, 1, 0)),
    ]


def armature(name, c, J):
    a = bpy.data.armatures.new(name + "_rig")
    o = bpy.data.objects.new(name, a)
    c.objects.link(o)
    vl = bpy.context.view_layer
    prev = vl.objects.active
    vl.objects.active = o
    bpy.ops.object.mode_set(mode="EDIT")
    eb = {}
    for bn, h, t, par, con, zax in BONES:
        b = a.edit_bones.new(bn)
        b.head, b.tail = J[h], J[t]
        b.align_roll(Vector(zax))
        if par:
            b.parent = eb[par]
            b.use_connect = con
        eb[bn] = b
    bpy.ops.object.mode_set(mode="OBJECT")
    vl.objects.active = prev
    a.display_type = "STICK"
    for pb in o.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return o


# ------------------------------------------------------------------ the person mesh
def _chain_stations(pts, svals):
    """Positions and directions along a polyline at arc lengths svals (extrapolates past both ends)."""
    seg = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    lens = [(b - a).length for a, b in seg]
    acc = [0.0]
    for L in lens:
        acc.append(acc[-1] + L)
    out = []
    for s in svals:
        i = 0
        while i < len(seg) - 1 and s > acc[i + 1]:
            i += 1
        a, b = seg[i]
        d = (b - a).normalized()
        u = (s - acc[i]) / lens[i]
        pos = a.lerp(b, u) if 0 <= u <= 1 else a + d * (s - acc[i])
        # blend direction across a joint (within 0.02 of it)
        dd = d
        for j in range(1, len(pts) - 1):
            if abs(s - acc[j]) < 0.03 * acc[-1]:
                d0 = (pts[j] - pts[j - 1]).normalized()
                d1 = (pts[j + 1] - pts[j]).normalized()
                dd = (d0 + d1).normalized()
        out.append((pos, dd))
    return out, acc


def _limb(cg, pts, rows, H, fwd, mat_fn, n=10, p=2.0, caps=(True, True), lip=None, tag=None, offv=None):
    """rows: [(s (units of H along the chain), radius_u, radius_v, weights)] -> one closed tube. mat_fn(i) is the
    material of the band after station i. lip: list of station indices whose ring gets a crease (hems, cuffs)."""
    st, acc = _chain_stations(pts, [r[0] * H for r in rows])
    cg.begin(tag)
    rings = []
    for (pos, d), r in zip(st, rows):
        U, V = _frame(d, fwd)
        C = pos + (V * (r[4] * H) if len(r) > 4 else Vector())
        rings.append(cg.ring(ring_pts(C, U, V, r[1] * H, r[2] * H, n=n, p=p), r[3]))
    for i in range(len(rings) - 1):
        cg.bridge(rings[i], rings[i + 1], mat_fn(i))
    if caps[0]:
        cg.cap(rings[0], mat_fn(0), True)
    if caps[1]:
        cg.cap(rings[-1], mat_fn(len(rings) - 2), False)
    for i in (lip or ()):
        cg.crease_ring(rings[i], 0.75)
    cg.end()
    return rings


def _wsplit(a, b, u):
    return {a: 1 - u, b: u} if 0 < u < 1 else ({a: 1.0} if u <= 0 else {b: 1.0})


def _sphere(cg, C, rad, mat, w, nu=10, nv=8, shape=None, tag=None, keep=None, scale_fn=None, closed=True):
    """UV sphere around C (radii rad, or a shape(x, y, z) on the unit sphere returning an offset). keep(x, y, z)
    selects faces by their unit-sphere centre (for hair shells); scale_fn scales each unit point radially."""
    cg.begin(tag, closed=closed and keep is None)
    rings = []
    unit = []
    for j in range(1, nv):
        ph = -math.pi / 2 + math.pi * j / nv
        r_ = []
        u_ = []
        for k in range(nu):
            th = 2 * math.pi * k / nu
            x, y, z = math.cos(ph) * math.cos(th), math.cos(ph) * math.sin(th), math.sin(ph)
            u_.append((x, y, z))
            s = scale_fn(x, y, z) if scale_fn else 1.0
            off = Vector(shape(x, y, z)) if shape else Vector((x * rad[0], y * rad[1], z * rad[2]))
            r_.append(C + off * s)
        rings.append(r_)
        unit.append(u_)
    sb = scale_fn(0, 0, -1) if scale_fn else 1.0
    st = scale_fn(0, 0, 1) if scale_fn else 1.0
    bot = C + (Vector(shape(0, 0, -1)) if shape else Vector((0, 0, -rad[2]))) * sb
    top = C + (Vector(shape(0, 0, 1)) if shape else Vector((0, 0, rad[2]))) * st
    idx = [[cg.v(p, w) for p in r_] for r_ in rings]
    ib, it = cg.v(bot, w), cg.v(top, w)
    mi = cg.m(mat)

    def want(pts):
        if keep is None:
            return True
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        cz = sum(p[2] for p in pts) / len(pts)
        return keep(cx, cy, cz)
    for j in range(len(idx) - 1):
        for k in range(nu):
            k2 = (k + 1) % nu
            if want([unit[j][k], unit[j][k2], unit[j + 1][k2], unit[j + 1][k]]):
                cg.faces.append((idx[j][k], idx[j][k2], idx[j + 1][k2], idx[j + 1][k]))
                cg.fm.append(mi)
    for k in range(nu):
        k2 = (k + 1) % nu
        if want([(0, 0, -1), unit[0][k2], unit[0][k]]):
            cg.faces.append((ib, idx[0][k2], idx[0][k]))
            cg.fm.append(mi)
        if want([(0, 0, 1), unit[-1][k], unit[-1][k2]]):
            cg.faces.append((it, idx[-1][k], idx[-1][k2]))
            cg.fm.append(mi)
    cg.end()
    return idx


def _blob(cg, C, rad, mat, w, rot=None, nu=8, nv=6, tag=None):
    R = rot or Matrix.Identity(3)
    return _sphere(cg, C, rad, mat, w, nu, nv, shape=lambda x, y, z: R @ Vector((x * rad[0], y * rad[1], z * rad[2])),
                   tag=tag)


def person(c, name="person", height=None, sex=None, build=None, skin=None, hair=None, hair_color=None, jacket=None,
           trousers=None, shoes=None, sole=None, bag=None, bag_color=None, hiviz=False, headwear=None,
           headwear_color=None, hem=None, collar=True, seed=0, detail=1, text=None, belt=False, gloves=None):
    """Build a person (adult, 1.60 to 1.90 m). Every argument left at None is drawn from the seed.
    sex "m" or "f"; build "slim" | "average" | "broad"; skin 0..7 (light to deep) or an RGB tuple; hair "short" |
    "buzz" | "bob" | "long" | "bun" | "ponytail" | "bald"; jacket, trousers, shoes: linear RGB; bag None |
    "shoulder" | "backpack" | "tote"; hiviz True turns the jacket into a fluorescent yellow EN ISO 20471 jacket with
    two retroreflective bands round the body and the sleeves; headwear None | "cap" (peaked uniform cap) |
    "baseball" | "helmet"; hem (units of H) is where the jacket ends (0.50 hip length); text puts plain lettering
    on the back and left chest (the police use "POLIZEI"); detail = subdivision level at render (1: about 16k
    triangles, the default; 2 for close-ups: about 65k).
    Returns a dict: arm (the armature object, also the thing to move), mesh, H, J (joints), sex, props, name."""
    rnd = random.Random(seed * 7919 + 17)
    sex = sex or rnd.choice("mf")
    height = height or (rnd.uniform(1.70, 1.88) if sex == "m" else rnd.uniform(1.60, 1.76))
    assert 1.55 <= height <= 1.95, "adults only: 1.55 to 1.95 m"
    build = build or rnd.choice(("slim", "average", "average", "broad"))
    H = height
    k = H / 1.75
    if skin is None:
        skin = rnd.randrange(len(SKIN))
    skin_c = SKIN[skin] if isinstance(skin, int) else skin
    if hair is None:
        hair = rnd.choice(("short", "short", "buzz", "bald") if sex == "m" else ("bob", "long", "bun", "ponytail",
                                                                               "short"))
    if hair_color is None:
        dark_skin = isinstance(skin, int) and skin >= 5
        hair_color = HAIR["black"] if dark_skin else HAIR[rnd.choice(("dark", "brown", "brown", "blond", "black",
                                                                      "auburn", "grey"))]
    elif isinstance(hair_color, str):
        hair_color = HAIR[hair_color]
    jacket = jacket or rnd.choice(JACKETS)
    trousers = trousers or rnd.choice(TROUSERS)
    shoes = shoes or rnd.choice(SHOES)
    sole = sole or (srgb(232, 230, 226) if rnd.random() < 0.4 else srgb(40, 38, 36))
    hem = hem or rnd.choice((0.47, 0.50, 0.50, 0.53))
    J = skeleton(H, sex, build)
    arm = armature(name, c, J)

    M = dict(
        skin=material("skin", skin_c, 0.48, spec=0.4, sheen=0.15),
        lips=material("lips", tuple(x * 0.72 + d for x, d in zip(skin_c, (0.03, 0.0, 0.0))), 0.4),
        hair=hair_material(hair_color),
        brow=material("brow", tuple(x * 0.7 for x in hair_color), 0.6),
        eye=material("eyewhite", srgb(236, 232, 226), 0.25, coat=1.0),
        iris=material("iris", srgb(40, 26, 18), 0.15, coat=1.0),
        jacket=material("hivis", HIVIS, 0.7, emit=HIVIS, estr=0.18, sheen=0.3) if hiviz else cloth(jacket, "jacket"),
        band=material("reflect", srgb(196, 200, 206), 0.32, metal=0.55),
        trousers=cloth(trousers, "trousers", var=0.09),
        shoe=material("shoe", shoes, 0.42, coat=0.3, var=0.05),
        sole=material("sole", sole, 0.7),
        hand=material("glove", gloves, 0.6) if gloves else None,
    )
    M["hand"] = M["hand"] or M["skin"]
    cg = Cage()
    rows = _torso_rows(sex, build)

    # ---- torso: pelvis in trouser cloth, the jacket from the hem up, a collar, the neck
    zs = sorted(set([r[0] for r in rows] + [hem - 0.004, hem]))
    band_z = []
    if hiviz:
        a = hem + 0.030
        band_z = [(a, a + 0.029), (a + 0.058, a + 0.087)]
        zs = sorted(set(zs + [z for b_ in band_z for z in b_]))
    if belt:
        zs = sorted(set(zs + [hem - 0.030, hem - 0.012]))
    st = []
    for z in zs:
        z_, rx, yf, yb, cy, p, w = _lerp_rows(rows, z)
        grow = 1.035 if abs(z - hem) < 1e-6 else (1.0 if z < hem else 1.012)
        if abs(z - (hem - 0.004)) < 1e-6:
            grow = 0.985
        st.append((z, rx * grow, yf * grow, yb * grow, cy, p, w))
    neck_r = 0.036 if sex == "m" else 0.033
    if collar:
        n_ = neck_r
        st += [(0.838, n_ + 0.019, n_ + 0.013, n_ + 0.015, -0.006, 2.2, {"chest": 0.4, "neck": 0.6}),
               (0.853, n_ + 0.014, n_ + 0.010, n_ + 0.012, -0.004, 2.0, {"chest": 0.2, "neck": 0.8}),
               (0.850, n_ + 0.005, n_ + 0.003, n_ + 0.005, -0.004, 2.0, {"neck": 1.0})]
    st += [(0.846, neck_r, neck_r, neck_r + 0.002, -0.004, 2.0, {"neck": 1.0}),
           (0.872, neck_r - 0.002, neck_r, neck_r, 0.000, 2.0, {"neck": 0.6, "head": 0.4}),
           (0.895, neck_r - 0.006, neck_r - 0.004, neck_r - 0.008, 0.002, 2.0, {"head": 1.0}),
           (0.915, 0.012, 0.012, 0.012, 0.004, 2.0, {"head": 1.0})]
    cg.begin("torso")
    trings = []
    for z, rx, yf, yb, cy, p, w in st:
        C = Vector((0, cy * H, z * H))
        trings.append(cg.ring(ring_pts(C, Vector((1, 0, 0)), Vector((0, 1, 0)), rx * H, yf * H, yb * H, n=12, p=p),
                              w))

    def tmat(i):
        z0, z1 = st[i][0], st[i + 1][0]
        zm = (z0 + z1) / 2
        if z1 > 0.845 and z0 >= 0.846 - 1e-6:
            return M["skin"]
        if collar and z0 >= 0.836 - 1e-6:
            return M["jacket"]
        if belt and hem - 0.030 <= zm <= hem - 0.012:
            return material("belt", srgb(20, 20, 22), 0.4, coat=0.4)
        if zm < hem - 0.002:
            return M["trousers"]
        for a_, b_ in band_z:
            if a_ <= zm <= b_:
                return M["band"]
        return M["jacket"]
    for i in range(len(trings) - 1):
        cg.bridge(trings[i], trings[i + 1], tmat(i))
    cg.cap(trings[0], M["trousers"], True)
    cg.cap(trings[-1], M["skin"], False)
    for i, s_ in enumerate(st):
        if abs(s_[0] - hem) < 1e-6 or (collar and abs(s_[0] - 0.853) < 1e-6):
            cg.crease_ring(trings[i], 0.8)
    cg.end()

    # ---- garment details: front zip and two pocket flaps (they catch light and shadow, so the jacket reads)
    zipm = material("zip", srgb(40, 40, 42), 0.35, metal=0.5)
    zz = [hem + 0.004 + (0.832 - hem - 0.004) * j / 9 for j in range(10)]
    _surface_band(cg, [_torso_point(rows, H, z, math.pi / 2, 0.0028) for z in zz], H, 0.0021, 0.0016, zipm)
    for sx in (-1, 1):
        angs = [math.pi / 2 + sx * math.radians(a_) for a_ in (34, 46, 58, 70)]
        _surface_band(cg, [_torso_point(rows, H, hem + 0.052, a_, 0.0026) for a_ in angs], H, 0.0085, 0.0022,
                      M["jacket"])

    # ---- legs (trousers down to the shoes)
    for side, sx in (("L", -1), ("R", 1)):
        pts = [J["hip" + side], J["kn" + side], J["an" + side]]
        lt = (J["kn" + side] - J["hip" + side]).length / H
        L = lt + (J["an" + side] - J["kn" + side]).length / H
        th, sh = "thigh." + side, "shin." + side
        rows_l = [(-0.034, 0.030, 0.030, {"hips": 0.6, th: 0.4}),
                  (-0.016, 0.046, 0.046, {"hips": 0.5, th: 0.5}),
                  (0.020, 0.057, 0.058, {"hips": 0.3, th: 0.7}),
                  (0.060, 0.056, 0.057, {th: 1.0}),
                  (0.110, 0.051, 0.052, {th: 1.0}),
                  (0.160, 0.045, 0.046, {th: 1.0}),
                  (lt - 0.026, 0.039, 0.040, {th: 0.8, sh: 0.2}),
                  (lt, 0.037, 0.038, {th: 0.5, sh: 0.5}),
                  (lt + 0.026, 0.037, 0.038, {th: 0.2, sh: 0.8}),
                  (lt + 0.070, 0.038, 0.040, {sh: 1.0}, -0.004),
                  (lt + 0.130, 0.034, 0.035, {sh: 1.0}, -0.002),
                  (L - 0.042, 0.030, 0.031, {sh: 1.0}),
                  (L - 0.008, 0.033, 0.034, {sh: 0.9, "foot." + side: 0.1}),
                  (L - 0.006, 0.025, 0.026, {sh: 0.9, "foot." + side: 0.1})]
        f = 1.06
        rows_l = [(r[0], r[1] * f, r[2] * f) + tuple(r[3:]) for r in rows_l]
        _limb(cg, pts, rows_l, H, Vector((0, 1, 0)), lambda i: M["trousers"], n=10, lip=[12], tag="leg" + side)

    # ---- shoes (built along +y at the ankle; heel, instep, ball, toe cap; flat creased sole)
    for side, sx in (("L", -1), ("R", 1)):
        an = J["an" + side]
        ft, to = "foot." + side, "toe." + side
        S = [(-0.036, 0.019, 0.036), (-0.030, 0.027, 0.048), (-0.012, 0.030, 0.055), (0.012, 0.031, 0.057),
             (0.040, 0.034, 0.044), (0.066, 0.038, 0.035), (0.088, 0.039, 0.029), (0.104, 0.035, 0.025),
             (0.116, 0.026, 0.021), (0.122, 0.014, 0.016)]
        t = 0.010
        cg.begin("shoe" + side)
        rings = []
        for y, w, h in S:
            yy = y * H
            ww, hh, tt = w * H, h * H, min(t, h * 0.5) * H
            cx = an.x + sx * (0.002 + max(0.0, y) * 0.03) * H
            prof = [(-ww * 0.90, 0.0), (-ww, tt), (-ww * 0.97, hh * 0.55), (-ww * 0.72, hh * 0.92), (-ww * 0.28, hh),
                    (ww * 0.28, hh), (ww * 0.72, hh * 0.92), (ww * 0.97, hh * 0.55), (ww, tt), (ww * 0.90, 0.0)]
            if y >= 0.095:
                wgt = {to: 1.0}
            elif y >= 0.080:
                wgt = {ft: 0.5, to: 0.5}
            else:
                wgt = {ft: 1.0}
            rings.append(cg.ring([Vector((cx + px, an.y + yy, pz)) for px, pz in prof], wgt))
        mats = [M["sole"]] + [M["shoe"]] * 7 + [M["sole"], M["sole"]]
        for i in range(len(rings) - 1):
            cg.bridge(rings[i], rings[i + 1], mats)
        cg.cap(rings[0], M["shoe"], True)
        cg.cap(rings[-1], M["shoe"], False)
        cg.crease_line([r[0] for r in rings], 1.0)
        cg.crease_line([r[9] for r in rings], 1.0)
        cg.crease_line([r[1] for r in rings], 0.6)
        cg.crease_line([r[8] for r in rings], 0.6)
        cg.end()

    # ---- arms (sleeves) and hands
    for side, sx in (("L", -1), ("R", 1)):
        pts = [J["sh" + side], J["el" + side], J["wr" + side]]
        ua, fa = "upperarm." + side, "forearm." + side
        lu = (J["el" + side] - J["sh" + side]).length / H
        L = lu + (J["wr" + side] - J["el" + side]).length / H
        f = 1.08
        rows_a = [(-0.017, 0.010, 0.010, {"chest": 0.4, ua: 0.6}),
                  (-0.009, 0.019, 0.019, {"chest": 0.25, ua: 0.75}),
                  (0.000, 0.026, 0.026, {"chest": 0.1, ua: 0.9}),
                  (0.040, 0.026, 0.026, {ua: 1.0}),
                  (0.090, 0.024, 0.025, {ua: 1.0}),
                  (lu - 0.030, 0.022, 0.022, {ua: 1.0}),
                  (lu - 0.012, 0.0215, 0.0215, {ua: 0.75, fa: 0.25}),
                  (lu, 0.021, 0.021, {ua: 0.5, fa: 0.5}),
                  (lu + 0.012, 0.0215, 0.0215, {ua: 0.25, fa: 0.75}),
                  (lu + 0.045, 0.0228, 0.022, {fa: 1.0}),
                  (lu + 0.095, 0.0198, 0.019, {fa: 1.0}),
                  (L - 0.018, 0.0178, 0.017, {fa: 1.0}),
                  (L - 0.007, 0.0192, 0.0186, {fa: 1.0}),
                  (L - 0.004, 0.013, 0.013, {fa: 0.9, "hand." + side: 0.1})]
        rows_a = [(r[0], r[1] * f, r[2] * f, r[3]) for r in rows_a]
        band_rows = []
        if hiviz:
            band_rows = [(0.090, 0.118), (lu + 0.060, lu + 0.088)]
            extra = []
            for a_, b_ in band_rows:
                for s_ in (a_, b_):
                    lo = max(r for r in rows_a if r[0] <= s_)
                    hi = min(r for r in rows_a if r[0] >= s_)
                    u = (s_ - lo[0]) / (hi[0] - lo[0]) if hi[0] > lo[0] else 0
                    w = {g: lo[3].get(g, 0) * (1 - u) + hi[3].get(g, 0) * u for g in set(lo[3]) | set(hi[3])}
                    extra.append((s_, lo[1] + (hi[1] - lo[1]) * u, lo[2] + (hi[2] - lo[2]) * u, w))
            rows_a = sorted(rows_a + extra, key=lambda r: r[0])

        def amat(i, rows_a=rows_a, band_rows=band_rows):
            sm = (rows_a[i][0] + rows_a[i + 1][0]) / 2
            for a_, b_ in band_rows:
                if a_ <= sm <= b_:
                    return M["band"]
            return M["jacket"]
        lip = [i for i, r in enumerate(rows_a) if abs(r[0] - (L - 0.007)) < 1e-6]
        _limb(cg, pts, rows_a, H, Vector((0, 1, 0)), amat, n=10, lip=lip, tag="arm" + side)
        _hand(cg, J, side, H, M["hand"])

    # ---- head, face, hair, headwear
    hair_obj = _head(cg, J, H, k, M, hair, headwear, headwear_color, sex, rnd, c, name)

    # ---- bags made of skin cloth (straps), rigid props below
    if bag in ("shoulder", "backpack"):
        _straps(cg, rows, H, bag, material("strap", srgb(30, 28, 26), 0.6))

    me = cg.build(name + "_body", c)
    mesh = me
    mesh.parent = arm
    mod = mesh.modifiers.new("rig", "ARMATURE")
    mod.object = arm
    mod.use_deform_preserve_volume = True
    sub = mesh.modifiers.new("sub", "SUBSURF")
    sub.levels = 1
    sub.render_levels = detail
    fig = dict(name=name, arm=arm, mesh=mesh, H=H, J=J, sex=sex, props={}, tags=cg.tags, k=k, seed=seed,
               lengths={"thigh": (J["knL"] - J["hipL"]).length, "shin": (J["anL"] - J["knL"]).length,
                        "upperarm": (J["elL"] - J["shL"]).length, "forearm": (J["wrL"] - J["elL"]).length})
    _grip_keys(fig, cg)
    if hair_obj is not None:
        attach(fig, hair_obj, "head", Matrix.Identity(4))
        hair_obj.modifiers["sub"].render_levels = detail
        fig["hair"] = hair_obj
    arm["dl_figure"] = True
    arm["dl_height"] = H
    if bag in ("shoulder", "backpack", "tote"):
        _bag_prop(fig, c, bag, bag_color or rnd.choice([srgb(40, 32, 26), srgb(110, 70, 40), srgb(30, 30, 34),
                                                        srgb(120, 30, 34)]))
    if text:
        _lettering(fig, c, text)
    return fig


def _hand(cg, J, side, H, mat, curl=None):
    """A mitten hand with a thumb: palm, knuckles, the finger block curled towards the palm. Two shapes are built
    with the same topology (relaxed and grip); the grip shape becomes a shape key."""
    wr, tip = J["wr" + side], J["tip" + side]
    Y = (tip - wr).normalized()
    P = Vector((1, 0, 0)) if side == "L" else Vector((-1, 0, 0))      # palm faces the thigh
    P = (P - Y * P.dot(Y)).normalized()
    T = P.cross(Y) if side == "L" else Y.cross(P)                       # thumb side (forward)
    hb, fb = "hand." + side, "forearm." + side

    def build(curl_total, thumb_in):
        rows = [(-0.012, 0.015, 0.011), (0.000, 0.020, 0.0125), (0.020, 0.025, 0.0135), (0.042, 0.0265, 0.013),
                (0.058, 0.026, 0.012), (0.074, 0.0235, 0.0105), (0.087, 0.019, 0.0090), (0.096, 0.012, 0.0070)]
        pos = wr + Y * (rows[0][0] * H)
        d = Y.copy()
        out = []
        prev_s = rows[0][0]
        for s, w, t in rows:
            ds = (s - prev_s) * H
            if s > 0.050:
                ang = curl_total * (s - prev_s) / 0.046
                d = (Quaternion(T, -ang) @ d).normalized() if side == "L" else (Quaternion(T, ang) @ d).normalized()
            pos = pos + d * ds
            prev_s = s
            U, V = _frame(d, P)
            out.append((ring_pts(pos, U, V, w * H, t * H, n=8, p=2.4), {hb: 1.0} if s > 0.004 else
                        {hb: 0.6, fb: 0.4}))
        # thumb: from the base of the palm on the thumb side, forward and towards the palm
        base = wr + Y * (0.016 * H) + T * (0.016 * H) + P * (0.004 * H)
        td = (Y * 0.55 + T * 0.55 + P * (0.25 + thumb_in)).normalized()
        th = []
        q = base
        for i, (s, r) in enumerate(((0.0, 0.0088), (0.022, 0.0082), (0.040, 0.0072), (0.052, 0.0050))):
            if i:
                q = q + td * ((s - prev) * H)
                td = (td + P * (0.25 + thumb_in) * 0.5 - T * 0.1).normalized()
            prev = s
            U, V = _frame(td, P)
            th.append((ring_pts(q, U, V, r * H, r * H, n=6), {hb: 1.0}))
        return out, th
    if curl is None:
        curl = math.radians(30)
    relaxed = build(curl, 0.0)
    grip = build(math.radians(150), 0.35)
    v0 = len(cg.co)
    for part in relaxed:
        cg.begin("hand" + side)
        rings = [cg.ring(p, w) for p, w in part]
        for i in range(len(rings) - 1):
            cg.bridge(rings[i], rings[i + 1], mat)
        cg.cap(rings[0], mat, True)
        cg.cap(rings[-1], mat, False)
        cg.end()
    grip_pts = [p for part in grip for pts, _w in part for p in pts]
    cg.tags["grip_" + side] = (v0, grip_pts)


def _grip_keys(fig, cg):
    me = fig["mesh"]
    me.shape_key_add(name="Basis", from_mix=False)
    for side in ("L", "R"):
        v0, pts = cg.tags["grip_" + side]
        sk = me.shape_key_add(name="grip_" + side, from_mix=False)
        for i, p in enumerate(pts):
            sk.data[v0 + i].co = p
        sk.value = 0.0
    fig["grip"] = {s: me.data.shape_keys.key_blocks["grip_" + s] for s in ("L", "R")}


# head profile (metres for a 1.75 m adult): z above the chin, half width, y of the widest point, face side y,
# back side y, superellipse exponent. y = 0 is the neck axis; the face looks along +y.
HEAD_ROWS = [
    (0.000, 0.012, 0.056, 0.068, 0.044, 2.0),
    (0.012, 0.033, 0.050, 0.082, 0.022, 2.3),
    (0.030, 0.050, 0.036, 0.087, -0.008, 2.5),
    (0.055, 0.062, 0.020, 0.089, -0.040, 2.7),
    (0.085, 0.067, 0.006, 0.094, -0.074, 2.5),
    (0.115, 0.073, -0.004, 0.093, -0.097, 2.4),
    (0.145, 0.076, -0.008, 0.092, -0.104, 2.3),
    (0.175, 0.075, -0.010, 0.085, -0.104, 2.2),
    (0.200, 0.068, -0.012, 0.071, -0.096, 2.1),
    (0.218, 0.054, -0.014, 0.051, -0.080, 2.0),
    (0.230, 0.032, -0.015, 0.027, -0.056, 2.0),
]
HEAD_TOP = 0.235


def _head_rows_at(z):
    rows = HEAD_ROWS
    if z <= rows[0][0]:
        return rows[0]
    if z >= rows[-1][0]:
        return rows[-1]
    for a, b in zip(rows[:-1], rows[1:]):
        if a[0] <= z <= b[0]:
            u = (z - a[0]) / (b[0] - a[0])
            return tuple(x + (y - x) * u for x, y in zip(a, b))


def _head_pt(z, th, grow=0.0, hang=None):
    """Surface point of the head profile at height z (m above the chin) and angle th (0 = +x, pi/2 = face), grown
    outwards by `grow` metres. hang: hair below this height drops straight down from the row at `hang`."""
    zr = z if hang is None or z >= hang else hang
    _z, hw, yc, yf, yb, p = _head_rows_at(zr)
    c, s = math.cos(th), math.sin(th)
    x = _sq(c, p) * hw
    sy = _sq(s, p)
    y = yc + sy * ((yf - yc) if sy > 0 else (yc - yb))
    rad = Vector((x, y - yc, 0))
    n = rad.normalized() if rad.length > 1e-6 else Vector((0, 0, 1))
    return Vector((x, y, z)) + n * grow


def _head_mesh(cg, base, k, mat, w, tag="head", nu=16):
    """Skin head from HEAD_ROWS (rings plus top and bottom poles); base = chin point (x = 0, y of the neck axis)."""
    cg.begin(tag)
    rings = []
    for row in HEAD_ROWS:
        z = row[0]
        rings.append(cg.ring([base + _head_pt(z, 2 * math.pi * i / nu) * k for i in range(nu)], w))
    for i in range(len(rings) - 1):
        cg.bridge(rings[i], rings[i + 1], mat)
    top = cg.v(base + Vector((0, -0.016, HEAD_TOP)) * k, w)
    bot = cg.v(base + Vector((0, 0.058, -0.003)) * k, w)
    mi = cg.m(mat)
    for i in range(nu):
        i2 = (i + 1) % nu
        cg.faces.append((rings[-1][i], rings[-1][i2], top))
        cg.fm.append(mi)
        cg.faces.append((rings[0][i2], rings[0][i], bot))
        cg.fm.append(mi)
    cg.end()


def _hair_line(style):
    """Height (fraction of the head, 0 chin .. 1 top) of the hairline at angle th, and the height below which the
    hair hangs straight (None: follows the head)."""
    def short(th):
        s = math.sin(th)
        return 0.62 + 0.24 * s - 0.08 * s * s
    if style in ("short", "buzz", "bun", "ponytail"):
        return short, None
    if style in ("bob", "long"):
        low = 0.20 if style == "bob" else 0.12

        def f(th):
            s = math.sin(th)
            if s > 0.80:
                return 0.70 + 0.08 * (s - 0.80) / 0.20      # a light fringe over the forehead
            if s > 0.68:
                u = (s - 0.68) / 0.12
                return low + (0.70 - low) * u * u * (3 - 2 * u)
            return low
        return f, 0.40
    return None, None


def _hair_mesh(cg, base, k, mat, style, nu=28, nz=16):
    line, hang = _hair_line(style)
    if line is None:
        return
    thick = {"short": 0.011, "buzz": 0.0035, "bob": 0.010, "long": 0.010, "bun": 0.010, "ponytail": 0.010}[style]
    zlo = min(line(2 * math.pi * i / nu) for i in range(nu)) * HEAD_TOP
    zs = [zlo + (HEAD_TOP * 0.985 - zlo) * (j / nz) ** 0.85 for j in range(nz + 1)]
    cg.begin("hair", closed=False)
    grid = []
    for z in zs:
        row = []
        for i in range(nu):
            th = 2 * math.pi * i / nu
            zl = line(th) * HEAD_TOP
            d = (z - zl) / (0.20 * HEAD_TOP)
            g = -0.0015 + (thick + 0.0015) * (max(0.0, min(1.0, d)) ** 0.6)
            if hang is not None and z < hang * HEAD_TOP:
                g = thick * (1.0 + 0.2 * (hang * HEAD_TOP - z) / (hang * HEAD_TOP))     # ends flare a little
                if z <= zs[0] + 1e-6:
                    g = thick * 0.35                                                   # and curl under
            row.append(cg.v(base + _head_pt(z, th, g, hang * HEAD_TOP if hang else None) * k, {"head": 1.0}))
        grid.append(row)
    topv = cg.v(base + Vector((0, -0.016, HEAD_TOP + thick)) * k, {"head": 1.0})
    mi = cg.m(mat)
    for j in range(len(zs) - 1):
        for i in range(nu):
            i2 = (i + 1) % nu
            th = 2 * math.pi * (i + 0.5) / nu
            zl = line(th) * HEAD_TOP
            if (zs[j] + zs[j + 1]) / 2 < zl - 0.004:
                continue
            cg.faces.append((grid[j][i], grid[j][i2], grid[j + 1][i2], grid[j + 1][i]))
            cg.fm.append(mi)
    for i in range(nu):
        cg.faces.append((grid[-1][i], grid[-1][(i + 1) % nu], topv))
        cg.fm.append(mi)
    cg.end()
    if style == "bun":
        _blob(cg, base + Vector((0, -0.095, 0.205)) * k, (0.038 * k, 0.034 * k, 0.036 * k), mat, {"head": 1.0},
              nu=10, nv=8)
    if style == "ponytail":
        q = [base + Vector((0, -0.100, 0.185)) * k, base + Vector((0, -0.128, 0.120)) * k,
             base + Vector((0, -0.124, 0.020)) * k, base + Vector((0, -0.112, -0.040)) * k]
        rr = [0.020, 0.023, 0.017, 0.006]
        rings = []
        for i, (p, r) in enumerate(zip(q, rr)):
            d = (q[min(i + 1, 3)] - q[max(i - 1, 0)]).normalized()
            U, V = _frame(d, Vector((0, -1, 0)))
            rings.append(cg.ring(ring_pts(p, U, V, r * k, r * 0.85 * k, n=8), {"head": 1.0}))
        cg.begin("ponytail")
        for i in range(3):
            cg.bridge(rings[i], rings[i + 1], mat)
        cg.cap(rings[0], mat, True)
        cg.cap(rings[-1], mat, False)
        cg.end()
    if style == "long":
        # hair falling down the back to the shoulder blades
        q = [base + Vector((0, -0.080, 0.080)) * k, base + Vector((0, -0.100, -0.020)) * k,
             base + Vector((0, -0.112, -0.130)) * k, base + Vector((0, -0.110, -0.200)) * k]
        rr = [(0.072, 0.030), (0.078, 0.026), (0.074, 0.018), (0.062, 0.010)]
        rings = []
        for i, (p, (a, b)) in enumerate(zip(q, rr)):
            d = (q[min(i + 1, 3)] - q[max(i - 1, 0)]).normalized()
            U, V = _frame(d, Vector((0, -1, 0)))
            rings.append(cg.ring(ring_pts(p, U, V, a * k, b * k, n=10, p=2.6), {"head": 1.0}))
        cg.begin("hairback")
        for i in range(3):
            cg.bridge(rings[i], rings[i + 1], mat)
        cg.cap(rings[0], mat, True)
        cg.cap(rings[-1], mat, False)
        cg.end()


def _head(cg, J, H, k, M, hair, headwear, hw_color, sex, rnd, c=None, fig_name="p"):
    """Skin head and face into the body cage; hair and headwear as a rigid shell on the head bone (returned)."""
    w = {"head": 1.0}
    kh = k * 1.06
    base = Vector((0, J["headj"].y, J["top"].z - HEAD_TOP * kh))
    _head_mesh(cg, base, kh, M["skin"], w)
    eye_z = 0.116
    for sx in (-1, 1):
        e = base + Vector((sx * 0.031, 0.083, eye_z)) * kh
        _blob(cg, e, (0.0128 * kh, 0.0085 * kh, 0.0072 * kh), M["eye"], w, nu=10, nv=6, tag="head")
        _blob(cg, e + Vector((sx * 0.0008, 0.0068, 0.0004)) * kh, (0.0070 * kh, 0.0030 * kh, 0.0070 * kh), M["iris"], w,
              nu=10, nv=6, tag="head")
        # upper lid: skin over the top of the eye gives a calm, natural look
        _blob(cg, e + Vector((0, 0.0010, 0.0068)) * kh, (0.0142 * kh, 0.0092 * kh, 0.0052 * kh), M["skin"], w,
              nu=10, nv=6, tag="head")
        b = base + Vector((sx * 0.032, 0.0905, 0.137)) * kh
        R = Matrix.Rotation(sx * math.radians(-6), 3, "Y") @ Matrix.Rotation(sx * math.radians(12), 3, "Z")
        _blob(cg, b, (0.0175 * kh, 0.0040 * kh, 0.0034 * kh), M["brow"], w, rot=R, nu=8, nv=5, tag="head")
        ear = base + Vector((sx * 0.0745, -0.014, 0.110)) * kh
        _blob(cg, ear, (0.009 * kh, 0.016 * kh, 0.027 * kh), M["skin"], w,
              rot=Matrix.Rotation(math.radians(-14), 3, "X") @ Matrix.Rotation(sx * math.radians(-12), 3, "Z"),
              nu=8, nv=6, tag="head")
    _blob(cg, base + Vector((0, 0.098, 0.096)) * kh, (0.0105 * kh, 0.0112 * kh, 0.0165 * kh), M["skin"], w,
          rot=Matrix.Rotation(math.radians(-24), 3, "X"), nu=8, nv=6, tag="head")
    _blob(cg, base + Vector((0, 0.0875, 0.050)) * kh, (0.0165 * kh, 0.0050 * kh, 0.0040 * kh), M["lips"], w, nu=10,
          nv=5, tag="head")
    # hair and headwear: rigid shell on the head bone (thickened, subdivided)
    hc = Cage()
    if hair and headwear != "helmet":
        _hair_mesh(hc, base, kh, M["hair"], hair if headwear is None else ("buzz" if hair == "buzz" else "short"))
    if headwear:
        _headwear(hc, base, kh, headwear, hw_color, M)
    if not hc.faces or c is None:
        return None
    o = hc.build(fig_name + "_hair", c)
    o.vertex_groups.clear()
    so = o.modifiers.new("thick", "SOLIDIFY")
    so.thickness = 0.004 * k
    so.offset = -1.0
    so.use_even_offset = True
    sub = o.modifiers.new("sub", "SUBSURF")
    sub.levels, sub.render_levels = 1, 2
    return o


def _shell(cg, base, k, mat, zlo, grow, nu=24, nz=10, tag="shell", top_grow=None):
    """Open shell over the head from height zlo(th) up to the top, offset outwards by grow(th, z)."""
    zmin = min(zlo(2 * math.pi * i / nu) for i in range(nu))
    zs = [zmin + (HEAD_TOP * 0.985 - zmin) * (j / nz) ** 0.8 for j in range(nz + 1)]
    cg.begin(tag, closed=False)
    grid = []
    for z in zs:
        row = []
        for i in range(nu):
            th = 2 * math.pi * i / nu
            zz = max(z, zlo(th))
            row.append(cg.v(base + _head_pt(zz, th, grow(th, zz)) * k, {"head": 1.0}))
        grid.append(row)
    tg = grow(math.pi / 2, HEAD_TOP) if top_grow is None else top_grow
    topv = cg.v(base + Vector((0, -0.016, HEAD_TOP + tg)) * k, {"head": 1.0})
    mi = cg.m(mat)
    for j in range(nz):
        for i in range(nu):
            i2 = (i + 1) % nu
            cg.faces.append((grid[j][i], grid[j][i2], grid[j + 1][i2], grid[j + 1][i]))
            cg.fm.append(mi)
    for i in range(nu):
        cg.faces.append((grid[-1][i], grid[-1][(i + 1) % nu], topv))
        cg.fm.append(mi)
    cg.end()
    return grid


def _plate_arc(cg, pts_top, thick, mat, tag="plate"):
    """A thin curved plate from rows of points (list of rows, each a list of points), thickness downwards."""
    cg.begin(tag, closed=False)
    top = [cg.ring(r_, {"head": 1.0}) for r_ in pts_top]
    bot = [cg.ring([p - Vector((0, 0, thick)) for p in r_], {"head": 1.0}) for r_ in pts_top]
    mi = cg.m(mat)
    n = len(pts_top[0])
    for j in range(len(top) - 1):
        for i in range(n - 1):
            cg.faces.append((top[j][i], top[j][i + 1], top[j + 1][i + 1], top[j + 1][i]))
            cg.fm.append(mi)
            cg.faces.append((bot[j][i + 1], bot[j][i], bot[j + 1][i], bot[j + 1][i + 1]))
            cg.fm.append(mi)
        cg.faces.append((top[j][0], top[j + 1][0], bot[j + 1][0], bot[j][0]))
        cg.fm.append(mi)
        cg.faces.append((bot[j][n - 1], bot[j + 1][n - 1], top[j + 1][n - 1], top[j][n - 1]))
        cg.fm.append(mi)
    for i in range(n - 1):
        cg.faces.append((top[-1][i], top[-1][i + 1], bot[-1][i + 1], bot[-1][i]))
        cg.fm.append(mi)
    cg.end()


def _headwear(cg, base, k, kind, color, M):
    w = {"head": 1.0}
    if kind == "cap":
        # peaked uniform cap (Schirmmuetze): band, flared crown, black peak, a thin cord; no badge, no crest
        color = color or POLICE_DARK
        crown = cloth(color, "cap", rough=0.7, var=0.04)
        band = material("capband", tuple(x * 0.55 for x in color), 0.6)
        peak = material("peak", srgb(14, 14, 16), 0.18, coat=1.0)
        cord = material("cord", srgb(170, 172, 176), 0.3, metal=0.8)
        tilt = Matrix.Rotation(math.radians(7), 3, "X")
        C = base + Vector((0, -0.006, 0.168)) * k
        rows = [(-0.004, 0.0800, 0.1000, 0.0, band), (0.036, 0.0820, 0.1020, 0.0, crown),
                (0.060, 0.0960, 0.1200, 0.006, crown), (0.072, 0.0950, 0.1180, 0.006, crown),
                (0.079, 0.0700, 0.0880, 0.004, crown), (0.082, 0.0020, 0.0020, 0.0, crown)]
        cg.begin("cap")
        rings = []
        for z, rx, ry, dy, m_ in rows:
            pts = ring_pts(Vector((0, dy, 0)), Vector((1, 0, 0)), Vector((0, 1, 0)), rx * k, ry * k, n=18, p=2.2)
            rings.append(cg.ring([C + tilt @ (p + Vector((0, 0, z * k))) for p in pts], w))
        for i in range(len(rings) - 1):
            cg.bridge(rings[i], rings[i + 1], rows[i][4])
        cg.cap(rings[0], band, True)
        cg.cap(rings[-1], crown, False)
        cg.crease_ring(rings[2], 0.7)
        cg.crease_ring(rings[1], 0.4)
        cg.end()
        prow = []
        for j, (yy, zz) in enumerate(((0.096, 0.0), (0.124, -0.011), (0.150, -0.026))):
            r_ = []
            for i in range(11):
                a = math.radians(-64 + 128 * i / 10)
                x = math.sin(a) * (0.081 + 0.018 * j) * k
                y = math.cos(a) * yy * k
                r_.append(C + tilt @ Vector((x, y, (zz - 0.003 * (1 - abs(math.sin(a)))) * k)))
            prow.append(r_)
        _plate_arc(cg, prow, 0.004 * k, peak, "peak")
        cg.begin("cord")
        pts = [C + tilt @ Vector((math.sin(math.radians(a)) * 0.0835 * k, math.cos(math.radians(a)) * 0.1035 * k,
                                  0.008 * k)) for a in range(-64, 65, 16)]
        _tube_into(cg, pts, 0.0026 * k, cord, w)
        cg.end()
    elif kind == "baseball":
        color = color or NAVY
        cm = cloth(color, "bcap", rough=0.75, var=0.05)

        def zlo(th):
            return 0.152 + 0.018 * math.sin(th)
        _shell(cg, base, k, cm, zlo, lambda th, z: 0.010 + 0.004 * max(0.0, (z - 0.17) / 0.06), tag="bcap")
        rows = []
        for j, (yy, dz) in enumerate(((0.090, 0.0), (0.128, -0.006), (0.162, -0.014))):
            r_ = []
            for i in range(11):
                a = math.radians(-60 + 120 * i / 10)
                r_.append(base + Vector((math.sin(a) * (0.072 + 0.004 * j), math.cos(a) * yy,
                                         0.172 + dz - 0.004 * (1 - abs(math.sin(a))))) * k)
            rows.append(r_)
        _plate_arc(cg, rows, 0.005 * k, cm, "brim")
        _blob(cg, base + Vector((0, -0.016, HEAD_TOP + 0.012)) * k, (0.007 * k, 0.007 * k, 0.004 * k), cm, w)
    elif kind == "helmet":
        color = color or srgb(40, 44, 52)
        hm = material("helmet", color, 0.3, coat=1.0)
        rim = material("helmetrim", srgb(20, 20, 22), 0.5)

        def zlo(th):
            s = math.sin(th)
            return 0.150 + 0.028 * s if s > 0 else 0.150 + 0.050 * s

        def grow(th, z):
            return 0.022 + 0.010 * max(0.0, -math.sin(th)) + 0.006 * max(0.0, (z - 0.17) / 0.06)
        grid = _shell(cg, base, k, hm, zlo, grow, tag="helmet")
        cg.begin("helmet_rim")
        pts = [cg.co[i] for i in grid[0]] + [cg.co[grid[0][0]]]
        _tube_into(cg, pts, 0.005 * k, rim, w)
        cg.end()
        # vents: three dark stripes over the top
        for dx in (-0.025, 0.0, 0.025):
            pts = [base + _head_pt(z, math.pi / 2 if dx == 0 else math.pi / 2 - 4 * dx, 0.035) * k
                   for z in (0.200, 0.215, 0.228)]
            pts = [p + Vector((dx * k, 0, 0)) for p in pts]
            cg.begin("vent")
            _tube_into(cg, pts, 0.004 * k, rim, w)
            cg.end()


def _tube_into(cg, pts, r, mat, w, n=6):
    rings = []
    for i, p in enumerate(pts):
        d = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        U, V = _frame(d, Vector((0, 0, 1)))
        rings.append(cg.ring(ring_pts(p, U, V, r, r, n=n), w))
    for i in range(len(rings) - 1):
        cg.bridge(rings[i], rings[i + 1], mat)
    cg.cap(rings[0], mat, True)
    cg.cap(rings[-1], mat, False)
    return rings


def _torso_point(rows, H, z, ang, out=0.0):
    """Point on the torso cage at height z (units of H) and angle ang around it (0 = +x, pi/2 = front)."""
    z_, rx, yf, yb, cy, p, w = _lerp_rows(rows, z)
    x = _sq(math.cos(ang), p) * rx
    sa = _sq(math.sin(ang), p)
    y = sa * (yf if sa > 0 else yb)
    v = Vector((x, y, 0))
    n = v.normalized() if v.length else Vector((1, 0, 0))
    return Vector((x * H, (y + cy) * H, z * H)) + n * out * H, w


def _surface_band(cg, pts, H, half_w, half_t, mat):
    """A flat band lying on the torso through pts [(point, weights)] (zip, pocket flap), skinned like the cloth."""
    cg.begin("band")
    rings = []
    for i, (p, w) in enumerate(pts):
        d = (pts[min(i + 1, len(pts) - 1)][0] - pts[max(i - 1, 0)][0]).normalized()
        nrm = Vector((p.x, p.y, 0)).normalized()
        U, V = _frame(d, nrm)
        rings.append(cg.ring(ring_pts(p, U, V, half_w * H, half_t * H, n=6, p=3.0), w))
    for i in range(len(rings) - 1):
        cg.bridge(rings[i], rings[i + 1], mat)
    cg.cap(rings[0], mat, True)
    cg.cap(rings[-1], mat, False)
    cg.end()


def _straps(cg, rows, H, bag, mat):
    if bag == "shoulder":
        # across the body: left shoulder to the right hip, front and back
        paths = []
        for back in (False, True):
            sgn = -1 if back else 1
            pts = []
            for z, ang in ((0.812, math.radians(150 if not back else 210)), (0.790, math.radians(120 * sgn)),
                           (0.745, math.radians(100 * sgn)), (0.690, math.radians(80 * sgn)),
                           (0.630, math.radians(55 * sgn)), (0.575, math.radians(30 * sgn))):
                pts.append(_torso_point(rows, H, z, ang, 0.008))
            paths.append(pts)
    else:
        paths = []
        for sx in (-1, 1):
            pts = []
            for z, ang in ((0.70, math.radians(90 + sx * 30)), (0.76, math.radians(90 + sx * 35)),
                           (0.806, math.radians(90 + sx * 60)), (0.812, math.radians(90 + sx * 85)),
                           (0.80, math.radians(270 - sx * 60)), (0.76, math.radians(270 - sx * 40))):
                pts.append(_torso_point(rows, H, z, ang, 0.009))
            paths.append(pts)
    for pts in paths:
        cg.begin("strap")
        rings = []
        for i, (p, w) in enumerate(pts):
            d = (pts[min(i + 1, len(pts) - 1)][0] - pts[max(i - 1, 0)][0]).normalized()
            nrm = Vector((p.x, p.y + 0.004 * H, 0)).normalized()
            U, V = _frame(d, nrm)
            rings.append(cg.ring(ring_pts(p, U, V, 0.013 * H, 0.003 * H, n=6, p=3.0), w))
        for i in range(len(rings) - 1):
            cg.bridge(rings[i], rings[i + 1], mat)
        cg.cap(rings[0], mat, True)
        cg.cap(rings[-1], mat, False)
        cg.end()


# ------------------------------------------------------------------ rigid props parented to bones
def rbox(name, size, mat, c, bevel=0.004, center=(0, 0, 0)):
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    cx, cy, cz = center
    v = [(cx + x, cy + y, cz + z) for z in (-hz, hz) for y in (-hy, hy) for x in (-hx, hx)]
    f = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    o = W.mesh_obj(name, v, f, mat, c)
    if bevel:
        b = o.modifiers.new("b", "BEVEL")
        b.width, b.segments = bevel, 2
        b.limit_method = "NONE"
    return o


def attach(fig, obj, bone, M_rest):
    """Parent a prop to a bone so that, in the rest pose, it sits at M_rest (armature space)."""
    arm = fig["arm"]
    b = arm.data.bones[bone]
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = bone
    tail = b.matrix_local @ Matrix.Translation((0, b.length, 0))
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = tail.inverted() @ M_rest
    return obj


def _bag_prop(fig, c, kind, color):
    H, J = fig["H"], fig["J"]
    m = material("bag", color, 0.5, coat=0.2, var=0.05)
    if kind == "shoulder":
        o = rbox(fig["name"] + "_bag", (0.07 * H * 0.6, 0.15 * H * 0.9, 0.12 * H * 0.8), m, c, 0.012)
        p = Vector((0.118 * H, 0.010 * H, 0.540 * H))
        attach(fig, o, "hips", Matrix.Translation(p) @ Matrix.Rotation(math.radians(-8), 4, "Y"))
    elif kind == "backpack":
        o = rbox(fig["name"] + "_bag", (0.17 * H, 0.08 * H, 0.24 * H), m, c, 0.02)
        p = Vector((0, -0.112 * H, 0.700 * H))
        attach(fig, o, "chest", Matrix.Translation(p))
    else:
        o = rbox(fig["name"] + "_bag", (0.035 * H, 0.20 * H, 0.17 * H), m, c, 0.008)
        hp = fig["J"]["tipR"]
        attach(fig, o, "hand.R", Matrix.Translation(hp + Vector((0.008, 0, -0.07 * H))))
    fig["props"]["bag"] = o
    return o


def _text_mesh(body, size, font=None):
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = body
    cu.font = font or W.SIGN_FONT or bpy.data.fonts.load("<builtin>")
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    o = bpy.data.objects.new("txt", cu)
    bpy.context.scene.collection.objects.link(o)
    me = bpy.data.meshes.new_from_object(o)
    bpy.data.objects.remove(o)
    bpy.data.curves.remove(cu)
    return me


def _lettering(fig, c, body):
    """Plain lettering (neutral sans) laid onto the jacket: large across the back, small on the left chest.
    Projected onto the subdivided rest-pose surface and skinned like the cloth under it."""
    H = fig["H"]
    mesh, arm = fig["mesh"], fig["arm"]
    dg = bpy.context.evaluated_depsgraph_get()
    bpy.context.view_layer.update()
    bvh = BVHTree.FromObject(mesh, dg)
    tree = kdtree.KDTree(len(mesh.data.vertices))
    torso = set(fig["tags"].get("torso", []))
    for v in mesh.data.vertices:
        if v.index in torso:
            tree.insert(v.co, v.index)
    tree.balance()
    vg_names = {g.index: g.name for g in mesh.vertex_groups}
    white = material("lettering", srgb(232, 234, 236), 0.35, metal=0.2)
    parts = []
    for where, size, cx, cz in (("back", 0.040 * H, 0.0, 0.735 * H), ("chest", 0.0115 * H, -0.050 * H, 0.745 * H)):
        me = _text_mesh(body, size)
        bm = bmesh.new()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        # text is in the XY plane reading along +x; stand it up facing -y (back) or +y (chest)
        for v in bm.verts:
            x, y = v.co.x, v.co.y
            if where == "back":
                p = Vector((-x + cx, -1.0, y + cz))
                d = Vector((0, 1, 0))
            else:
                p = Vector((x + cx, 1.0, y + cz))
                d = Vector((0, -1, 0))
            hit, nrm, _i, _d = bvh.ray_cast(p, d)
            v.co = (hit + nrm * 0.0025) if hit else p
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
        out = bpy.data.meshes.new(fig["name"] + "_txt_" + where)
        bm.to_mesh(out)
        bm.free()
        o = bpy.data.objects.new(fig["name"] + "_txt_" + where, out)
        c.objects.link(o)
        out.materials.append(white)
        groups = {}
        for v in out.vertices:
            _co, idx, _dist = tree.find(v.co)
            for ge in mesh.data.vertices[idx].groups:
                groups.setdefault(vg_names[ge.group], []).append((v.index, ge.weight))
        for g, lst in groups.items():
            vg = o.vertex_groups.new(name=g)
            for i, wv in lst:
                vg.add([i], wv, "REPLACE")
        o.parent = arm
        md = o.modifiers.new("rig", "ARMATURE")
        md.object = arm
        md.use_deform_preserve_volume = True
        parts.append(o)
    fig["props"]["lettering"] = parts
    fig["text"] = body
    return parts


# ------------------------------------------------------------------ posing: FK / IK on the armature
def _clamp(x, a, b):
    return a if x < a else (b if x > b else x)


def smooth(a, b, x):
    t = _clamp((x - a) / (b - a), 0.0, 1.0) if b != a else (1.0 if x >= b else 0.0)
    return t * t * (3 - 2 * t)


def _qx(a):
    return Quaternion((1, 0, 0), a)


def _qy(a):
    return Quaternion((0, 1, 0), a)


def _qz(a):
    return Quaternion((0, 0, 1), a)


def _M(R3, t):
    M = R3.to_4x4()
    M.translation = t
    return M


def _frame_xy(y, xhint):
    """Rotation whose columns are (x, y, z): y exact, x as close to xhint as possible, z = x cross y."""
    y = y.normalized()
    x = xhint - y * xhint.dot(y)
    if x.length < 1e-8:
        x = Vector((1, 0, 0)) - y * y.x
    x.normalize()
    return Matrix((x, y, x.cross(y))).transposed()


def two_bone(root, target, a, b, pole):
    """Analytic two-bone IK. Returns (mid joint, reached end, hinge axis u x w)."""
    d_vec = target - root
    d = d_vec.length
    u = d_vec / d if d > 1e-9 else Vector((0, 0, -1))
    dc = _clamp(d, abs(a - b) + 1e-4, (a + b) * 0.9995)
    w = pole - u * pole.dot(u)
    if w.length < 1e-8:
        w = Vector((0, 1, 0)) - u * u.y
    w.normalize()
    ca = _clamp((a * a + dc * dc - b * b) / (2 * a * dc), -1.0, 1.0)
    al = math.acos(ca)
    mid = root + (u * math.cos(al) + w * math.sin(al)) * a
    return mid, root + u * dc, u.cross(w).normalized()


class Rig:
    """Rest data of a figure's armature and helpers to turn armature-space targets into bone-local (basis)
    transforms: pose = parent_pose @ (parent_rest^-1 @ rest) @ basis."""

    def __init__(self, arm):
        bones = arm.data.bones
        self.o = arm
        self.names = [b[0] for b in BONES]
        self.parent = {n: (bones[n].parent.name if bones[n].parent else None) for n in self.names}
        self.rest = {n: bones[n].matrix_local.copy() for n in self.names}
        self.rel = {}
        for n in self.names:
            p = self.parent[n]
            self.rel[n] = (self.rest[p].inverted() @ self.rest[n]) if p else self.rest[n].copy()
        self.length = {n: bones[n].length for n in self.names}

    def base(self, n, pose):
        p = self.parent[n]
        return (pose[p] @ self.rel[n]) if p else self.rel[n]

    def fk(self, n, q, pose, basis, loc=None):
        B = q.to_matrix().to_4x4()
        if loc is not None:
            B.translation = loc
        basis[n] = B
        pose[n] = self.base(n, pose) @ B

    def ik(self, n, M, pose, basis):
        B = self.base(n, pose).inverted() @ M
        basis[n] = B
        pose[n] = self.base(n, pose) @ B

    def rest_rot(self, n):
        return self.rest[n].to_3x3()


def _foot_geo(fig, side):
    J, H = fig["J"], fig["H"]
    an, ball = J["an" + side], J["ball" + side]
    return dict(a_h=an.z, heel=Vector((0, -0.030 * H, 0)), ball=Vector((0, ball.y - an.y, 0)),
                toe=Vector((0, J["toe" + side].y - an.y, 0)))


def _foot_place(geo, F, yaw, pitch):
    """Ankle position (3D) of a foot whose footprint origin is F (3D, on the ground, under the ankle), pointing along
    heading yaw (0 = +x, like jx.Path) with pitch (toe up +), rotating about the heel for pitch >= 0 and about the
    ball for pitch < 0. The foot geometry in geo points along +y."""
    piv = geo["heel"] if pitch >= 0 else geo["ball"]
    a = Vector((0, 0, geo["a_h"]))
    rel = Matrix.Rotation(pitch, 3, "X") @ (a - piv) + piv
    return F + Matrix.Rotation(yaw - math.pi / 2, 3, "Z") @ rel


def _foot_points(geo, F, yaw, pitch):
    """Heel, ball and toe-tip points for the same pose (the toe stays flat when the heel is up)."""
    piv = geo["heel"] if pitch >= 0 else geo["ball"]
    Rz = Matrix.Rotation(yaw - math.pi / 2, 3, "Z")
    Rx = Matrix.Rotation(pitch, 3, "X")
    out = []
    for p in (geo["heel"], geo["ball"], geo["toe"]):
        q = p if (pitch < 0 and p is geo["toe"]) else Rx @ (p - piv) + piv
        out.append(F + Rz @ q)
    return out


# ------------------------------------------------------------------ keys
def _fcurves(idb):
    ad = idb.animation_data
    act = ad.action
    try:
        return list(act.fcurves)
    except AttributeError:
        return list(act.layers[0].strips[0].channelbag(ad.action_slot).fcurves)


def keys(idb, path, index, frames, values, interp=1):
    """Replace the keys of one channel with (frame, value) pairs (foreach_set, fast). interp: 0 constant, 1 linear."""
    fc = None
    if idb.animation_data and idb.animation_data.action:
        for f in _fcurves(idb):
            if f.data_path == path and f.array_index == index:
                fc = f
    if fc is None:
        try:
            idb.keyframe_insert(path, index=index, frame=frames[0])
        except TypeError:                       # a scalar property (shape key value)
            idb.keyframe_insert(path, frame=frames[0])
        fc = next(f for f in _fcurves(idb) if f.data_path == path and f.array_index == index)
    kp = fc.keyframe_points
    kp.clear()
    kp.add(len(frames))
    co = []
    for f, v in zip(frames, values):
        co += [float(f), float(v)]
    kp.foreach_set("co", co)
    kp.foreach_set("interpolation", [interp] * len(frames))
    fc.update()
    return fc


def _unwrap(vals):
    out = list(vals)
    for i in range(1, len(out)):
        while out[i] - out[i - 1] > math.pi:
            out[i] -= 2 * math.pi
        while out[i] - out[i - 1] < -math.pi:
            out[i] += 2 * math.pi
    return out


def _write(fig, frames, rec, obj_track=None):
    """rec: list per frame of dict(basis={bone: Matrix4}, grip={"L", "R"}). obj_track: [(x, y, z, heading)] for
    the armature object (heading: radians, 0 = the figure walks along +x)."""
    arm = fig["arm"]
    for n in [b[0] for b in BONES]:
        pb = arm.pose.bones[n]
        qs = []
        prev = None
        for r in rec:
            q = r["basis"][n].to_quaternion()
            if prev is not None and q.dot(prev) < 0:
                q.negate()
            qs.append(q)
            prev = q
        for i in range(4):
            keys(arm, f'pose.bones["{n}"].rotation_quaternion', i, frames, [q[i] for q in qs])
        if n == "hips":
            for i in range(3):
                keys(arm, f'pose.bones["{n}"].location', i, frames, [r["basis"][n].translation[i] for r in rec])
        pb.rotation_quaternion = qs[0]
    if obj_track is not None:
        yaw = _unwrap([t[3] - math.pi / 2 for t in obj_track])
        arm.rotation_mode = "XYZ"
        for i in range(3):
            keys(arm, "location", i, frames, [t[i] for t in obj_track])
        for i in range(2):
            keys(arm, "rotation_euler", i, frames, [0.0] * len(frames))
        keys(arm, "rotation_euler", 2, frames, yaw)
    sk = fig["mesh"].data.shape_keys
    for s in ("L", "R"):
        keys(sk, f'key_blocks["grip_{s}"].value', 0, frames, [r["grip"][s] for r in rec])


# ------------------------------------------------------------------ the pose of one frame
ARM_POLE = {"L": Vector((-0.5, -0.6, -1.0)), "R": Vector((0.5, -0.6, -1.0))}


def _solve(fig, rig, st):
    """st: pelvis_pos, pelvis_R (3x3 delta), spine/chest/neck/head quats, legs {side: (ankle, footR, toeR, pole)},
    arms {side: dict(fk=(qu, qf, qh), ik=None | dict(w, wrist, handR, pole))}. Returns the basis dict."""
    pose, basis = {}, {}
    rig.ik("hips", _M(st["pelvis_R"] @ rig.rest_rot("hips"), st["pelvis_pos"]), pose, basis)
    rig.fk("spine", st["spine"], pose, basis)
    rig.fk("chest", st["chest"], pose, basis)
    rig.fk("neck", st["neck"], pose, basis)
    rig.fk("head", st["head"], pose, basis)
    L = fig["lengths"]
    for side in ("L", "R"):
        ankle, footR, toeR, pole = st["legs"][side]
        th, sh, ft, to = "thigh." + side, "shin." + side, "foot." + side, "toe." + side
        hip = rig.base(th, pose).translation
        knee, end, n = two_bone(hip, ankle, L["thigh"], L["shin"], pole)
        rig.ik(th, _M(_frame_xy(knee - hip, n), hip), pose, basis)
        rig.ik(sh, _M(_frame_xy(end - knee, n), knee), pose, basis)
        rig.ik(ft, _M(footR @ rig.rest_rot(ft), end), pose, basis)
        rig.ik(to, _M(toeR @ rig.rest_rot(to), pose[ft] @ Vector((0, rig.length[ft], 0))), pose, basis)
    for side in ("L", "R"):
        a = st["arms"][side]
        ua, fa, hd = "upperarm." + side, "forearm." + side, "hand." + side
        b_fk, p_fk = {}, dict(pose)
        for n_, q in zip((ua, fa, hd), a["fk"]):
            rig.fk(n_, q, p_fk, b_fk)
        g = a.get("g")
        ik = _carry(pose["chest"] @ rig.rest["chest"].inverted(), g) if g else None
        if not ik or ik["w"] <= 1e-4:
            for n_ in (ua, fa, hd):
                basis[n_], pose[n_] = b_fk[n_], p_fk[n_]
            continue
        sh_ = rig.base(ua, pose).translation
        el, end, n = two_bone(sh_, ik["wrist"], L["upperarm"], L["forearm"], ik["pole"])
        b_ik, p_ik = {}, dict(pose)
        rig.ik(ua, _M(_frame_xy(el - sh_, -n), sh_), p_ik, b_ik)
        rig.ik(fa, _M(_frame_xy(end - el, -n), el), p_ik, b_ik)
        rig.ik(hd, _M(ik["handR"], end), p_ik, b_ik)
        for n_ in (ua, fa, hd):
            q = b_fk[n_].to_quaternion().slerp(b_ik[n_].to_quaternion(), ik["w"])
            rig.fk(n_, q, pose, basis)
    return basis, pose


# ------------------------------------------------------------------ gestures (hand targets in the rest chest frame)
def _hand_R(fwd, palm, side):
    """Hand bone rotation (armature space) for fingers pointing along fwd with the palm facing palm."""
    y = fwd.normalized()
    pn = (palm - y * palm.dot(y)).normalized()
    x = pn if side == "L" else -pn
    return Matrix((x, y, x.cross(y))).transposed()


def gesture_targets(fig, name, t, side):
    """(wrist position, hand rotation, elbow pole, grip, head pitch) of a named gesture at time t (s) for one arm, in
    rest armature space (carried with the chest). None: this arm keeps its walk or ride pose."""
    H = fig["H"]
    sx = -1 if side == "L" else 1
    P = lambda x, y, z: Vector((x * H, y * H, z * H))  # noqa: E731
    if name == "write":                    # parking attendant: device in the left hand, right hand taps on it
        if side == "L":
            return (P(-0.045, 0.150, 0.640), _hand_R(Vector((0.55, 0.8, 0.1)), Vector((0.1, 0, 1)), "L"),
                    ARM_POLE["L"], 0.75, math.radians(-26))
        tap = 0.006 * math.sin(2 * math.pi * 2.2 * t)
        return (P(0.020, 0.165, 0.668 + tap), _hand_R(Vector((-0.6, 0.7, -0.3)), Vector((0, 0, -1)), "R"),
                ARM_POLE["R"], 0.45, math.radians(-26))
    if name == "laser":                    # police: handheld speed laser at eye level, both hands
        if side == "R":
            return (P(0.040, 0.140, 0.858), _hand_R(Vector((-0.15, 1.0, 0.35)), Vector((-1, 0, 0)), "R"),
                    Vector((0.6, -0.2, -1.0)), 1.0, 0.0)
        return (P(0.015, 0.205, 0.858), _hand_R(Vector((0.55, 1.0, 0.25)), Vector((0.1, 0, 1)), "L"),
                Vector((-0.6, -0.3, -1.0)), 0.55, 0.0)
    if name == "wave":                     # thank-you wave with the right hand
        if side == "L":
            return None
        sw = 0.025 * math.sin(2 * math.pi * 2.0 * t)
        return (P(0.150 + sw, 0.060, 0.930), _hand_R(Vector((sw * 6, 0.1, 1.0)), Vector((0, 1, 0)), "R"),
                Vector((1.0, -0.3, -0.6)), 0.0, 0.0)
    if name == "halt":                     # police: arm raised high
        if side == "L":
            return None
        return (P(0.080, 0.030, 1.180), _hand_R(Vector((0, 0.05, 1.0)), Vector((0, 1, 0)), "R"),
                Vector((1.0, 0.0, -0.3)), 0.0, 0.0)
    if name in ("signal_L", "signal_R"):   # arm straight out to the side (cyclist hand signal)
        if side != name[-1]:
            return None
        return (P(sx * 0.42, 0.030, 0.800), _hand_R(Vector((sx, 0.05, 0)), Vector((0, 0, -1)), side),
                Vector((0, -1.0, -0.3)), 0.0, 0.0)
    return None


def _gestures_at(fig, gestures, t):
    """{side: (weight, wrist, handR, pole, grip, head pitch)} in rest armature space at time t; 0.45 s ease."""
    out = {}
    for g in gestures:
        name, t0, t1 = g[0], g[1], g[2]
        w = smooth(t0, t0 + 0.45, t) * (1.0 - smooth(t1 - 0.45, t1, t))
        if w <= 0:
            continue
        for side in ("L", "R"):
            tg = gesture_targets(fig, name, t - t0, side)
            if tg is not None and (side not in out or out[side][0] < w):
                out[side] = (w,) + tuple(tg)
    return out


def _carry(chest_rel, g):
    """Move a rest-space gesture target with the chest (chest_rel = chest pose @ chest rest^-1)."""
    w, wrist, hR, pole, grip, hp = g
    R3 = chest_rel.to_3x3()
    return dict(w=w, wrist=chest_rel @ wrist, handR=R3 @ hR, pole=R3 @ pole)


# ------------------------------------------------------------------ walking and standing
class _Track:
    def __init__(self, sv, fps):
        self.s = [float(p[0]) for p in sv]
        self.v = [float(p[1]) for p in sv]
        self.fps, self.n = fps, len(sv)

    def s_at(self, t):
        f = t * self.fps
        if f <= 0:
            return self.s[0] + self.v[0] * t
        if f >= self.n - 1:
            return self.s[-1] + self.v[-1] * (t - (self.n - 1) / self.fps)
        i = int(f)
        return self.s[i] + (self.s[i + 1] - self.s[i]) * (f - i)

    def v_at(self, t):
        f = t * self.fps
        if f <= 0:
            return self.v[0]
        if f >= self.n - 1:
            return self.v[-1]
        i = int(f)
        return self.v[i] + (self.v[i + 1] - self.v[i]) * (f - i)


def _heading(path, s, d=0.35):
    a, _ = path.at(s - d)
    b, _ = path.at(s + d)
    v = b - a
    return math.atan2(v.y, v.x)


def _rate(v, H):
    """Gait cycles per second at speed v: step length 0.36 H v^0.42 (0.73 m at 1.4 m/s for a 1.75 m adult), 1 to
    2.6 steps a second."""
    L = 0.36 * H * max(v, 0.05) ** 0.42
    return 0.5 * _clamp(v / L, 1.0, 2.6)


def _gait(tr, H, n, fps):
    """Gait phase per frame and the stances (footprints) of both feet. The left foot lands at phase k, the right at
    k + 0.5; each stays on the ground for DUTY of a cycle; a footprint lies where the body will be half way through
    that stance. A walker who stops finishes the step (feet together) and stands: the phase freezes in double
    support and starts again when the body moves."""
    sub = 4
    st = {"L": [], "R": []}
    if tr.v_at(0) < V_STOP and tr.v_at(0.3) < V_STOP:
        i0, phi, frozen = 0, 0.55, True
        s0 = tr.s_at(0)
        st["L"].append(dict(phi=0.0, s=s0, stand=True, r=0.0))
        st["R"].append(dict(phi=0.5, s=s0, stand=True, r=0.0))
    else:
        i0, phi, frozen = -2 * fps * sub, 0.0, False
        t = i0 / (fps * sub)
        r = _rate(tr.v_at(t), H)
        st["L"].append(dict(phi=0.0, s=tr.s_at(t + DUTY / r / 2), stand=False, r=r))
        tR = t - 0.5 / r
        st["R"].append(dict(phi=-0.5, s=tr.s_at(tR + DUTY / r / 2), stand=False, r=r))
    i_end = (n - 1 + 3 * fps) * sub
    per = [None] * n
    i = i0
    dt = 1.0 / (fps * sub)
    while i <= i_end:
        t = i / (fps * sub)
        if i >= 0 and i % sub == 0 and i // sub < n:
            per[i // sub] = (phi, frozen)
        v = tr.v_at(t)
        if frozen:
            if tr.v_at(t + 0.15) > V_STOP:
                frozen = False
        else:
            m = phi % 1.0
            if ((m < DUTY - 0.5) or (0.5 <= m < DUTY)) and v < V_STOP and tr.v_at(t + 0.3) < V_STOP:
                if abs(st["L"][-1]["s"] - st["R"][-1]["s"]) < 0.16:
                    frozen = True
        if not frozen:
            r = _rate(v, H)
            nphi = phi + r * dt
            for kk in range(math.floor(phi * 2) + 1, math.floor(nphi * 2) + 1):
                e = kk / 2.0
                te = t + (e - phi) / r
                foot = "L" if kk % 2 == 0 else "R"
                st[foot].append(dict(phi=e, s=tr.s_at(te + DUTY / r / 2), stand=False, r=r))
            phi = nphi
        i += 1
    return per, st


def _stand_weight(per, fps, ramp=0.3):
    """0 walking .. 1 standing, eased over `ramp` seconds around each freeze."""
    n = len(per)
    raw = [1.0 if p[1] else 0.0 for p in per]
    k = max(1, int(ramp * fps))
    out = []
    for i in range(n):
        lo, hi = max(0, i - k), min(n, i + k + 1)
        a = sum(raw[lo:hi]) / (hi - lo)
        out.append(a * a * (3 - 2 * a))
    return out


def kerb_ground(axis="x", hw=3.0, kerb=0.15):
    """Ground height for a straight street: axis "x" means the carriageway is |x| < hw (a north-south street), "y"
    means |y| < hw; footways stand at the kerb height (town.KERB_H = 0.15 m)."""
    if axis == "x":
        return lambda x, y: kerb if abs(x) > hw else 0.0
    return lambda x, y: kerb if abs(y) > hw else 0.0


def _footprint(fig, path, rec, side, ground, H):
    if "pos" in rec:
        return rec
    s = rec["s"]
    p, _ = path.at(s)
    h = _heading(path, s)
    nrm = Vector((-math.sin(h), math.cos(h)))
    lat = (0.052 if rec["stand"] else 0.034) * H * (1 if side == "L" else -1)
    q = p + nrm * lat
    yaw = h + math.radians(6 if side == "L" else -6)
    geo = _foot_geo(fig, side)
    z = 0.0
    if ground:
        fw = Vector((math.cos(yaw), math.sin(yaw)))

        def level(qq):
            a_, b_ = qq + fw * geo["heel"].y, qq + fw * geo["toe"].y
            return ground(a_.x, a_.y), ground(b_.x, b_.y)
        za, zb = level(q)
        if abs(za - zb) > 0.01:      # never stand half on a kerb: shift the step to one level
            for dd in [0.02 * j * sgn for j in range(1, 16) for sgn in (1, -1)]:
                za, zb = level(q + fw * dd)
                if abs(za - zb) <= 0.01:
                    q = q + fw * dd
                    break
        z = ground(q.x, q.y)
    rec.update(pos=Vector((q.x, q.y, z)), yaw=yaw)
    return rec


TH_HS, TH_TO = math.radians(14), math.radians(-38)


def _stance_pitch(psi, amp):
    if psi < 0.08:
        return TH_HS * amp * (1 - smooth(0.0, 0.08, psi))
    if psi < 0.30:
        return 0.0
    u = (psi - 0.30) / (DUTY - 0.30)
    return TH_TO * amp * u * u


def _feet(fig, path, per, st, ground, H, ws):
    """Per frame and foot (world space): ankle, yaw, pitch, toe pitch, stance flag and the footprint."""
    out = []
    geo = {s: _foot_geo(fig, s) for s in ("L", "R")}
    for f, (phi, _fr) in enumerate(per):
        res = {}
        for side in ("L", "R"):
            lst = st[side]
            j = max(i for i, r in enumerate(lst) if r["phi"] <= phi + 1e-9)
            cur = _footprint(fig, path, lst[j], side, ground, H)
            psi = phi - cur["phi"]
            g = geo[side]
            amp = 0.0 if cur["stand"] else _clamp(cur["r"] / 0.9, 0.35, 1.0)
            if psi < DUTY:
                pitch = _stance_pitch(psi, amp) * (1 - ws[f])
                ankle = _foot_place(g, cur["pos"], cur["yaw"], pitch)
                res[side] = dict(ankle=ankle, yaw=cur["yaw"], pitch=pitch, toe=max(pitch, 0.0), z=cur["pos"].z,
                                 stance=True, fp=cur, psi=psi)
                continue
            nxt = _footprint(fig, path, lst[j + 1], side, ground, H)
            u = _clamp((psi - DUTY) / (1 - DUTY), 0.0, 1.0)
            amp_n = _clamp(nxt["r"] / 0.9, 0.35, 1.0)
            p0, p1 = TH_TO * amp, TH_HS * amp_n
            A0 = _foot_place(g, cur["pos"], cur["yaw"], p0)
            A1 = _foot_place(g, nxt["pos"], nxt["yaw"], p1)
            uh = u - math.sin(2 * math.pi * u) / (2 * math.pi)
            dyaw = (nxt["yaw"] - cur["yaw"] + math.pi) % (2 * math.pi) - math.pi
            yaw = cur["yaw"] + dyaw * uh
            mid_lo, mid_hi = math.radians(-12) * amp, math.radians(8) * amp_n
            if u < 0.3:
                pitch = p0 + (mid_lo - p0) * smooth(0, 0.3, u)
            elif u < 0.7:
                pitch = mid_lo + (mid_hi - mid_lo) * smooth(0.3, 0.7, u)
            else:
                pitch = mid_hi + (p1 - mid_hi) * smooth(0.7, 1.0, u)
            toe = pitch * smooth(0.0, 0.3, u)
            step = (Vector((A1.x, A1.y)) - Vector((A0.x, A0.y))).length
            lift = (0.035 * H * min(1.0, step / (0.5 * H)) + 0.010 * H) * math.sin(math.pi * u) ** 1.2
            ankle = A0.lerp(A1, uh)
            ankle.z = A0.z + (A1.z - A0.z) * smooth(0.1, 0.8, u) + lift
            # keep heel, ball and toe clear of the ground (kerbs included)
            F = ankle - _foot_place(g, Vector(), yaw, pitch)
            pts = _foot_points(g, F, yaw, pitch)
            zg = max(cur["pos"].z, nxt["pos"].z)
            need = max(zg + 0.006 * math.sin(math.pi * u) - min(p.z for p in pts), 0.0)
            ankle.z += need
            res[side] = dict(ankle=ankle, yaw=yaw, pitch=pitch, toe=toe, z=zg, stance=False, fp=nxt, u=u, psi=psi)
        out.append(res)
    return out


def _look_at(look, t, body_xy, h, H):
    """Head yaw (left +) and pitch (up +) relative to the body heading for look = [(t0, t1, target)], target a yaw
    in degrees (left +) or a world point (x, y[, z]). 0.35 s ease in and out; later entries win."""
    yaw = pitch = 0.0
    for t0, t1, tg in look:
        w = smooth(t0, t0 + 0.35, t) * (1.0 - smooth(t1 - 0.35, t1, t))
        if w <= 0:
            continue
        if isinstance(tg, (int, float)):
            y_, p_ = math.radians(tg), 0.0
        else:
            dx, dy = tg[0] - body_xy[0], tg[1] - body_xy[1]
            dz = (tg[2] if len(tg) > 2 else 1.2) - 0.93 * H
            y_ = (math.atan2(dy, dx) - h + math.pi) % (2 * math.pi) - math.pi
            p_ = math.atan2(dz, math.hypot(dx, dy))
        y_ = _clamp(y_, math.radians(-100), math.radians(100))
        yaw = yaw * (1 - w) + y_ * w
        pitch = pitch * (1 - w) + _clamp(p_, -0.6, 0.5) * w
    return yaw, pitch


def _upper_body(fig, st, t, sf, ws, phi, look_yaw, look_pitch, g_pitch, ph0, lean_extra=0.0, yaw_p=0.0):
    """Spine, chest, neck and head quaternions: forward lean with speed, shoulders against the hips, a level gaze,
    the look direction spread over chest (15 %), neck (35 %) and head (50 %)."""
    tw = math.radians(4.5) * sf * math.cos(2 * math.pi * phi)
    breathe = math.radians(0.8) * ws * math.sin(2 * math.pi * t / 4.2 + ph0)
    f_sp = math.radians(2.0 + 3.0 * sf) + lean_extra * 0.5
    f_ch = math.radians(1.0 + 2.0 * sf) + breathe + lean_extra * 0.5
    side = -st.get("roll", 0.0)
    ch_look = 0.15 * look_yaw
    st["spine"] = _qy(tw) @ _qx(f_sp) @ _qz(side * 0.6)
    st["chest"] = _qy(tw + ch_look) @ _qx(f_ch) @ _qz(side * 0.4)
    acc = yaw_p + 2 * tw + ch_look
    rem = look_yaw - acc + math.radians(2.0) * ws * math.sin(2 * math.pi * t / 7.0 + ph0)
    lean = f_sp + f_ch + st.get("tilt", 0.0)
    pit = -look_pitch - g_pitch * 1.0
    st["neck"] = _qy(rem * 0.4) @ _qx(-lean * 0.45 + pit * 0.4)
    st["head"] = _qy(rem * 0.6) @ _qx(-lean * 0.55 + pit * 0.6)


def _arms_fk(sf, ws, phi, t, ph0, amp=math.radians(18)):
    out = {}
    for side, ph in (("L", 0.5), ("R", 0.0)):
        sg = 1 if side == "L" else -1
        sw = amp * sf * math.cos(2 * math.pi * (phi - ph))
        idle = math.radians(1.5) * ws * math.sin(2 * math.pi * t / 4.2 + ph0 + (0 if side == "L" else 1.3))
        flex = sw + math.radians(2.0) * ws + idle
        elbow = math.radians(12 + 14 * max(0.0, sw / amp if amp else 0.0)) * max(sf, 0.0) + math.radians(9) * ws
        elbow = max(elbow, math.radians(8))
        out[side] = (_qx(flex) @ _qz(sg * math.radians(2.5)), _qx(elbow), _qx(math.radians(-4)))
    return out


def walk(fig, path, sv, frames=None, ground=None, look=(), gesture=(), fps=FPS, frame0=1):
    """Bake a person along `path` (jx.Path or anything with .at(s) -> (Vector2, heading) and .length) with the
    per-frame (s, v) list sv (frame frame0 = sv[0]). Speeds under V_STOP stand (feet together, weight shift, head
    turns). ground(x, y) -> z (kerb_ground) lifts footprints onto kerbs; steps never straddle a kerb edge.
    look: [(t0, t1, yaw_deg | (x, y[, z]))]; gesture: [(name, t0, t1)] with name write, laser, wave, halt,
    signal_L, signal_R. Times in seconds from frame0. Returns per-frame foot data (for checks)."""
    n = len(sv)
    frames = frames or list(range(frame0, frame0 + n))
    H, J = fig["H"], fig["J"]
    rig = fig.get("rig") or Rig(fig["arm"])
    fig["rig"] = rig
    tr = _Track(sv, fps)
    per, st_ = _gait(tr, H, n, fps)
    ws = _stand_weight(per, fps)
    feet = _feet(fig, path, per, st_, ground, H, ws)
    rnd = random.Random(fig["seed"] * 31 + 5)
    ph0 = rnd.uniform(0, 2 * math.pi)
    Lmax = 0.985 * (fig["lengths"]["thigh"] + fig["lengths"]["shin"])
    pel = J["pelvis"]
    rec, track = [], []
    zb_prev = None
    for f in range(n):
        t = f / fps
        s, v = sv[f]
        p, _ = path.at(s)
        h = _heading(path, s)
        phi = per[f][0]
        w_st = ws[f]
        sf = min(1.0, max(v, 0.0) / 1.3) * (1 - w_st)
        ft = feet[f]
        zsum = wsum = 0.0
        for side in ("L", "R"):
            d = ft[side]
            wg = (1 - smooth(0.6 * DUTY, DUTY, d["psi"])) if d["stance"] else smooth(0.5, 1.0, d["u"])
            zsum += wg * d["z"]
            wsum += wg
        z_body = zsum / wsum if wsum > 1e-6 else max(ft["L"]["z"], ft["R"]["z"])
        zb_prev = z_body
        Minv = (Matrix.Translation((p.x, p.y, 0)) @ Matrix.Rotation(h - math.pi / 2, 4, "Z")).inverted()
        R_inv = Minv.to_3x3()
        # pelvis: bob, sway towards the stance foot, list, rotation, idle weight shift
        bob = 0.010 * H * sf * math.cos(4 * math.pi * (phi - 0.3))
        drop = 0.013 * H * sf + 0.004 * H * w_st
        shift = 0.010 * H * w_st * math.sin(2 * math.pi * t / 5.5 + ph0)
        x_off = -0.011 * H * sf * math.cos(2 * math.pi * (phi - 0.3)) + shift
        roll = math.radians(4) * sf * math.cos(2 * math.pi * (phi - 0.3)) - math.radians(2.5) * shift / (0.010 * H)
        yaw_p = -math.radians(5) * sf * math.cos(2 * math.pi * phi)
        tilt = math.radians(3) * sf
        Rp = Matrix.Rotation(yaw_p, 3, "Z") @ Matrix.Rotation(roll, 3, "Y") @ Matrix.Rotation(-tilt, 3, "X")
        P = Vector((x_off, pel.y + 0.006 * H * sf, pel.z - drop + bob + z_body))
        legs = {}
        for side in ("L", "R"):
            d = ft[side]
            yl = d["yaw"] - h
            ank = Minv @ d["ankle"]
            footR = Matrix.Rotation(yl, 3, "Z") @ Matrix.Rotation(d["pitch"], 3, "X")
            toeR = Matrix.Rotation(yl, 3, "Z") @ Matrix.Rotation(d["toe"], 3, "X")
            sg = -1 if side == "L" else 1
            pole = Matrix.Rotation(yl, 3, "Z") @ Vector((sg * 0.12, 1.0, 0.0))
            legs[side] = [ank, footR, toeR, pole]
        # never ask a leg for more than it has: lower the pelvis instead
        for _it in range(2):
            low = 0.0
            for side in ("L", "R"):
                hip = P + Rp @ (J["hip" + side] - pel)
                a = legs[side][0]
                hd = math.hypot(hip.x - a.x, hip.y - a.y)
                if hd < Lmax and (hip - a).length > Lmax:
                    low = max(low, (hip.z - a.z) - math.sqrt(Lmax * Lmax - hd * hd))
            P.z -= low
        st = dict(pelvis_pos=P, pelvis_R=Rp, legs=legs, roll=roll, tilt=tilt)
        gs = _gestures_at(fig, gesture, t)
        g_pitch = max((g[5] * g[0] for g in gs.values()), key=abs, default=0.0)
        ly, lp = _look_at(look, t, (p.x, p.y), h, H)
        _upper_body(fig, st, t, sf, w_st, phi, ly, lp, g_pitch, ph0, yaw_p=yaw_p)
        afk = _arms_fk(sf, w_st, phi, t, ph0)
        st["arms"] = {s_: dict(fk=afk[s_], g=gs.get(s_)) for s_ in ("L", "R")}
        basis, pose = _solve(fig, rig, st)
        grip = {s_: (gs[s_][0] * gs[s_][4] if s_ in gs else 0.0) for s_ in ("L", "R")}
        if fig.get("tote"):
            grip["R"] = max(grip["R"], 0.9)
        rec.append(dict(basis=basis, grip=grip))
        track.append((p.x, p.y, 0.0, h))
    _write(fig, frames, rec, track)
    fig["feet"] = feet
    fig["frames"] = frames
    return feet


def stand(fig, pos, heading, n_frames, ground=None, look=(), gesture=(), fps=FPS, frame0=1):
    """A person standing at pos (x, y) facing heading (radians, 0 = +x) for n_frames: weight shift, breathing, head
    turns (look), gestures (gesture). heading may also be a point to face."""
    import jx
    if not isinstance(heading, (int, float)):
        heading = math.atan2(heading[1] - pos[1], heading[0] - pos[0])
    a = Vector((pos[0], pos[1]))
    d = Vector((math.cos(heading), math.sin(heading)))
    path = jx.Path([tuple(a - d), tuple(a), tuple(a + d)])
    return walk(fig, path, [(1.0, 0.0)] * n_frames, None, ground, look, gesture, fps, frame0)


def walk_profile(length, v=1.4, n_frames=None, plan=None, s0=0.0, fps=FPS, a_acc=1.2, a_brake=1.6):
    """(s, v) per frame for a pedestrian (gentler accelerations than a car): plan as in jx.kinematics
    [(t, "cruise", v) | (t, "stop", s_line) | (t, "hold", None)]; default walks the whole length at v."""
    import jx
    n_frames = n_frames or int((length / v + 1.0) * fps)
    plan = plan or [(0.0, "cruise", v)]
    return jx.kinematics(s0, plan[0][2] if plan[0][1] == "cruise" else 0.0, plan, n_frames, fps, a_acc, a_brake)


# ------------------------------------------------------------------ the city bike
def _ptf(path, closed=False, n0=None):
    """Tangents and parallel-transported normals along a polyline (no twist)."""
    n = len(path)
    T = []
    for i in range(n):
        if closed:
            a, b = path[i - 1], path[(i + 1) % n]
        else:
            a, b = path[max(i - 1, 0)], path[min(i + 1, n - 1)]
        T.append((b - a).normalized())
    N = Vector(n0) if n0 is not None else None
    if N is None or abs(N.dot(T[0])) > 0.99:
        N = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
    Ns = []
    for i, t in enumerate(T):
        if i:
            N = T[i - 1].rotation_difference(t) @ N
        N = (N - t * N.dot(t)).normalized()
        Ns.append(N)
    return T, Ns


def sweep(cg, path, profile, mat, closed=False, caps=True, scale=None, n0=None, w=None):
    """Sweep a closed 2D profile [(u, v)] along a 3D polyline. mat may be a list (one per profile segment)."""
    path = [Vector(p) for p in path]
    T, Ns = _ptf(path, closed, n0)
    w = w if w is not None else {}
    cg.begin(None, closed=closed or caps)
    rings = []
    for i, p in enumerate(path):
        U = Ns[i]
        V = T[i].cross(U)
        k = scale[i] if scale else 1.0
        rings.append(cg.ring([p + U * (a * k) + V * (b * k) for a, b in profile], w))
    for i in range(len(rings) - 1):
        cg.bridge(rings[i], rings[i + 1], mat)
    if closed:
        cg.bridge(rings[-1], rings[0], mat)
    elif caps:
        m0 = mat[0] if isinstance(mat, (list, tuple)) else mat
        cg.cap(rings[0], m0, True)
        cg.cap(rings[-1], m0, False)
        cg.flat.update((len(cg.faces) - 2, len(cg.faces) - 1))
    cg.end()
    return rings


def circle(r, n=8, rv=None):
    rv = rv or r
    return [(r * math.cos(2 * math.pi * i / n), rv * math.sin(2 * math.pi * i / n)) for i in range(n)]


def tube(cg, pts, r, mat, n=8, caps=True):
    return sweep(cg, pts, circle(r, n), mat, caps=caps)


def bezier(p0, p1, p2, n=10, p3=None):
    p0, p1, p2 = Vector(p0), Vector(p1), Vector(p2)
    out = []
    for i in range(n + 1):
        t = i / n
        if p3 is None:
            out.append(p0 * (1 - t) ** 2 + p1 * 2 * t * (1 - t) + p2 * t * t)
        else:
            q3 = Vector(p3)
            out.append(p0 * (1 - t) ** 3 + p1 * 3 * t * (1 - t) ** 2 + p2 * 3 * t * t * (1 - t) + q3 * t ** 3)
    return out


def arc_yz(c, r, a0, a1, n, x=0.0):
    """Points on a circle around the axle c (x axis) from angle a0 to a1 (degrees, 0 = +y forward, 90 = up)."""
    return [Vector((c[0] + x, c[1] + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
                    c[2] + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))) for i in range(n + 1)]


def _box_into(cg, center, size, mat, R=None):
    R = R or Matrix.Identity(3)
    c = Vector(center)
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    cg.begin(None)
    v = [cg.v(c + R @ Vector((x, y, z)), {}) for z in (-hz, hz) for y in (-hy, hy) for x in (-hx, hx)]
    mi = cg.m(mat)
    for f in [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]:
        cg.faces.append(tuple(v[i] for i in f))
        cg.fm.append(mi)
        cg.flat.add(len(cg.faces) - 1)
    cg.end()


def _extrude_outline(cg, outline_yz, x0, x1, mat):
    """A flat plate from a 2D outline in the (y, z) plane, between x0 and x1."""
    cg.begin(None)
    a = [cg.v((x0, y, z), {}) for y, z in outline_yz]
    b = [cg.v((x1, y, z), {}) for y, z in outline_yz]
    mi = cg.m(mat)
    cg.faces.append(tuple(reversed(a)))
    cg.fm.append(mi)
    cg.faces.append(tuple(b))
    cg.fm.append(mi)
    cg.flat.update((len(cg.faces) - 2, len(cg.faces) - 1))
    n = len(a)
    for i in range(n):
        j = (i + 1) % n
        cg.faces.append((a[i], a[j], b[j], b[i]))
        cg.fm.append(mi)
    cg.end()


def _rigid(cg, name, c, parent=None, inv=None, smooth=True, subsurf=0):
    o = cg.build(name, c)
    if not smooth:
        o.data.polygons.foreach_set("use_smooth", [False] * len(o.data.polygons))
    elif cg.flat:
        sm = [True] * len(o.data.polygons)
        for i in cg.flat:
            if i < len(sm):
                sm[i] = False
        o.data.polygons.foreach_set("use_smooth", sm)
    if parent is not None:
        o.parent = parent
        o.matrix_parent_inverse = inv if inv is not None else Matrix.Identity(4)
    if subsurf:
        s = o.modifiers.new("sub", "SUBSURF")
        s.levels, s.render_levels = 1, subsurf
    return o


BIKE_R = 0.351           # 28 x 1.6 in (ETRTO 40-622): 702 mm over the tyre
BIKE_WB = 1.12           # wheelbase
HEAD_ANGLE = 70.0        # degrees from horizontal
SEAT_ANGLE = 72.0


def city_bike(c, name="bike", frame="step", color=None, basket=False, rack=True, guards=None, saddle_h=0.74,
              lights=True, seed=0, rider=None):
    """A generic German city bike (Hollandrad / Citybike type, no brand): 28 in wheels (radius 0.351 m),
    wheelbase 1.12 m, about 1.85 m long over the mudguards; frame "step" (low wave frame) or "diamond"; full
    mudguards with a front mud flap, chain guard, rear rack with spring clip, kickstand, frame lock, hub dynamo,
    front lamp and rear light, reflectors (front white, rear red, yellow pedal reflectors, reflective tyre
    sidewalls), sprung saddle, swept-back bars, bell; optional front wire basket. Origin on the ground half way
    between the axles, forward +y. With rider (a person dict) the saddle height fits that rider's legs.
    Returns a dict with root, steer, wheels, crank, pedals and the geometry the rider needs."""
    rnd = random.Random(seed * 13 + 3)
    color = color or rnd.choice([srgb(24, 40, 70), srgb(110, 20, 24), srgb(30, 60, 44), srgb(200, 196, 186),
                                 srgb(30, 30, 32), srgb(120, 150, 170)])
    guards = guards or ("frame" if rnd.random() < 0.5 else "silver")
    R, wb = BIKE_R, BIKE_WB
    paint = material("bikepaint", color, 0.25, metal=0.3, coat=1.0)
    alu = material("bikealu", srgb(200, 202, 206), 0.25, metal=1.0)
    black = material("bikeblack", srgb(18, 18, 20), 0.5)
    rubber = material("tyre", srgb(22, 22, 22), 0.75, var=0.05, scale=60)
    refl = material("tyrestripe", srgb(200, 202, 204), 0.35, metal=0.4)
    guard_m = paint if guards == "frame" else material("guardalu", srgb(186, 188, 192), 0.2, metal=1.0)
    red = material("bikered", srgb(150, 10, 8), 0.2, emit=srgb(255, 20, 10), estr=1.2 if lights else 0.0)
    redref = material("bikereflector_r", srgb(150, 16, 12), 0.15, coat=1.0)
    yel = material("bikereflector_y", srgb(240, 150, 20), 0.15, coat=1.0)
    lamp_m = material("bikelamp", srgb(240, 240, 232), 0.1, emit=srgb(255, 248, 230), estr=2.0 if lights else 0.0)
    whiteref = material("bikereflector_w", srgb(232, 232, 228), 0.15, coat=1.0)
    saddle_m = material("saddle", srgb(36, 28, 24), 0.45, coat=0.3, var=0.06)
    root = bpy.data.objects.new(name, None)
    c.objects.link(root)
    root.empty_display_size = 0.3
    Ra, Fa = Vector((0, -wb / 2, R)), Vector((0, wb / 2, R))
    BB = Vector((0, -0.10, 0.285))
    sdir = Vector((0, -math.cos(math.radians(SEAT_ANGLE)), math.sin(math.radians(SEAT_ANGLE))))
    ax = Vector((0, -math.cos(math.radians(HEAD_ANGLE)), math.sin(math.radians(HEAD_ANGLE))))
    Q = Vector((0, Fa.y - 0.045 / math.sin(math.radians(HEAD_ANGLE)), R))     # steering axis at axle height
    ht0, ht1 = Q + ax * 0.42, Q + ax * 0.62
    st_top = BB + sdir * 0.50
    # saddle height: the rider's leg nearly straight at the bottom of the stroke
    if rider is not None:
        saddle_h = _fit_saddle(rider, BB, sdir)
    S_top = BB + sdir * saddle_h
    # ---- frame
    fr = Cage()
    fr.flat = set()
    tube(fr, [ht0, ht1], 0.019, paint, 12)
    tube(fr, [BB, st_top + sdir * 0.02], 0.015, paint, 10)
    if frame == "diamond":
        tube(fr, [ht0 + ax * 0.16, st_top - sdir * 0.01], 0.015, paint, 10)
        tube(fr, [ht0 + ax * 0.03, BB + Vector((0, 0.02, 0.02))], 0.017, paint, 10)
    else:
        tube(fr, bezier(ht0 + ax * 0.06, (0, 0.10, 0.31), BB + Vector((0, 0.03, 0.03)), 12), 0.022, paint, 12)
        tube(fr, bezier(ht0 + ax * 0.14, (0, 0.06, 0.48), BB + sdir * 0.26, 10), 0.013, paint, 10)
    for sx in (-1, 1):
        tube(fr, [BB + Vector((sx * 0.032, -0.02, 0)), Ra + Vector((sx * 0.064, 0.02, 0))], 0.010, paint, 8)
        tube(fr, [st_top + Vector((sx * 0.018, 0.0, -0.05)), Ra + Vector((sx * 0.062, 0.0, 0.02))], 0.0085, paint, 8)
        _box_into(fr, Ra + Vector((sx * 0.066, 0, 0)), (0.008, 0.035, 0.03), paint)
    # kickstand (folded along the left chainstay)
    tube(fr, [BB + Vector((-0.05, -0.12, 0.0)), Ra + Vector((-0.10, 0.10, -0.05))], 0.008, alu, 8)
    # frame lock on the seat stays (ring lock, closed body)
    lk = arc_yz(Ra, 0.27, 50, 76, 6)
    sweep(fr, lk, [(-0.012, -0.045), (0.012, -0.045), (0.016, 0), (0.012, 0.045), (-0.012, 0.045), (-0.016, 0)],
          black, n0=(0, 0, 1))
    # seat post and saddle (sprung comfort saddle)
    tube(fr, [st_top, S_top - sdir * 0.07], 0.0135, alu, 10)
    _box_into(fr, S_top - sdir * 0.065 + Vector((0, 0.01, 0)), (0.05, 0.08, 0.02), black)
    for sx in (-1, 1):
        sp = []
        for i in range(41):
            a = 2 * math.pi * 4 * i / 40
            sp.append(S_top + Vector((sx * 0.055 + 0.015 * math.cos(a), -0.075 + 0.015 * math.sin(a),
                                      -0.10 + 0.055 * i / 40)))
        tube(fr, sp, 0.0032, alu, 6)
        tube(fr, [S_top + Vector((sx * 0.055, -0.075, -0.10)), S_top - sdir * 0.065 + Vector((sx * 0.02, 0, 0))],
             0.004, alu, 6)
    # chain guard, chainring cover and chain line (right side)
    out = [(0.125, 0.0), (0.108, 0.062), (0.062, 0.108), (0.0, 0.125), (-0.06, 0.118), (-0.40, 0.098),
           (-0.44, 0.077), (-0.40, 0.052), (-0.10, 0.066), (-0.05, 0.030), (0.07, -0.022)]
    _extrude_outline(fr, [(BB.y + y, BB.z + z) for y, z in out], 0.088, 0.093, guard_m if guards == "frame" else black)
    for z0, z1 in ((0.095, 0.040), (-0.095, -0.040)):
        tube(fr, [BB + Vector((0.058, 0, z0)), Ra + Vector((0.058, 0, z1))], 0.0045, black, 6)
    sweep(fr, arc_yz(Ra, 0.042, 0, 360, 16, x=0.058)[:-1], circle(0.004, 6), black, closed=True)
    # rear mudguard with stays
    prof_g = [(0.002, -0.030), (0.006, -0.032), (0.010, -0.017), (0.012, 0.0), (0.010, 0.017), (0.006, 0.032),
              (0.002, 0.030), (0.006, 0.014), (0.007, 0.0), (0.006, -0.014)]
    sweep(fr, arc_yz(Ra, R + 0.018, 40, 196, 20), prof_g, guard_m, n0=(0, math.cos(math.radians(40)),
                                                                    math.sin(math.radians(40))))
    for a in (110, 160):
        q = arc_yz(Ra, R + 0.022, a, a, 1)[0]
        for sx in (-1, 1):
            tube(fr, [q + Vector((sx * 0.028, 0, 0)), Ra + Vector((sx * 0.07, 0, 0))], 0.0028, alu, 6)
    # rear rack with spring clip, rear light and reflector
    if rack:
        zr = R + 0.43
        for sx in (-1, 1):
            tube(fr, [Vector((sx * 0.066, -0.30, zr)), Vector((sx * 0.066, -0.86, zr))], 0.0065, black, 8)
            tube(fr, [Vector((sx * 0.044, -0.34, zr + 0.016)), Vector((sx * 0.044, -0.82, zr + 0.016))], 0.004,
                 alu, 6)
            tube(fr, [Vector((sx * 0.066, -0.86, zr)), Ra + Vector((sx * 0.070, 0, 0))], 0.0055, black, 8)
            tube(fr, [Vector((sx * 0.066, -0.66, zr)), Ra + Vector((sx * 0.070, 0, 0.01))], 0.0055, black, 8)
            tube(fr, [Vector((sx * 0.066, -0.30, zr)), st_top + Vector((sx * 0.02, -0.03, -0.07))], 0.0055, black,
                 8)
        for y in (-0.42, -0.58, -0.74, -0.86):
            tube(fr, [Vector((-0.066, y, zr)), Vector((0.066, y, zr))], 0.0045, black, 6)
        _box_into(fr, (0, -0.880, zr - 0.012), (0.080, 0.032, 0.048), black)
        _box_into(fr, (0, -0.897, zr - 0.012), (0.066, 0.004, 0.030), red)
        _box_into(fr, (0, -0.900, zr - 0.050), (0.075, 0.006, 0.030), redref)
    else:
        _box_into(fr, Ra + Vector((0, -R - 0.05, 0.08)), (0.07, 0.02, 0.035), red)
    frame_o = _rigid(fr, name + "_frame", c, root)
    sad = Cage()
    sad.flat = set()
    rows = [(-0.120, 0.090, 0.016), (-0.105, 0.112, 0.024), (-0.075, 0.118, 0.026), (-0.035, 0.104, 0.025),
            (0.000, 0.078, 0.023), (0.040, 0.050, 0.021), (0.080, 0.035, 0.020), (0.112, 0.028, 0.018),
            (0.128, 0.016, 0.012)]
    sad.begin("saddle")
    rings = []
    for y, hw, ht in rows:
        cc = S_top + Vector((0, y + 0.015, -ht + 0.002 + 0.006 * (1 - abs(y) / 0.12)))
        rings.append(sad.ring(ring_pts(cc, Vector((1, 0, 0)), Vector((0, 0, 1)), hw / 2 * 1.0, ht, n=12, p=3.0),
                              {}))
    for i in range(len(rings) - 1):
        sad.bridge(rings[i], rings[i + 1], saddle_m)
    sad.cap(rings[0], saddle_m, True)
    sad.cap(rings[-1], saddle_m, False)
    sad.end()
    _rigid(sad, name + "_saddle", c, root, subsurf=2)
    # ---- steering: fork, steerer, stem, bars, grips, levers, bell, front guard, lamp, basket
    steer = bpy.data.objects.new(name + "_steer", None)
    c.objects.link(steer)
    steer.parent = root
    steer.rotation_mode = "ZYX"
    steer.location = Q
    steer.rotation_euler = (math.radians(90 - HEAD_ANGLE), 0, 0)
    steer.empty_display_size = 0.1
    st_rest = Matrix.Translation(Q) @ Matrix.Rotation(math.radians(90 - HEAD_ANGLE), 4, "X")
    sc = Cage()
    sc.flat = set()
    crown = Q + ax * 0.40
    _box_into(sc, crown, (0.11, 0.04, 0.03), paint, Matrix.Rotation(math.radians(90 - HEAD_ANGLE), 3, "X"))
    for sx in (-1, 1):
        tube(sc, bezier(crown + Vector((sx * 0.045, 0, -0.01)), Q + ax * 0.12 + Vector((sx * 0.048, 0.005, 0)),
                        Fa + Vector((sx * 0.050, 0, 0)), 10), 0.011, paint, 8)
    top = Q + ax * 0.70
    tube(sc, [ht1, top], 0.0135, alu, 10)
    bar_c = top + Vector((0, 0.07, 0.02))
    tube(sc, [top - ax * 0.01, bar_c], 0.013, alu, 10)
    bar = []
    for sx in (-1, 1):
        side = [Vector((sx * 0.28, 0.150, 1.045)), Vector((sx * 0.25, 0.220, 1.045)), Vector((sx * 0.19, 0.300, 1.040)),
                Vector((sx * 0.10, 0.338, 1.032))]
        bar += side if sx < 0 else list(reversed(side))
        if sx < 0:
            bar.append(Vector((0, bar_c.y, bar_c.z)))
    bar = [p + Vector((0, 0, bar_c.z - 1.03)) for p in bar]
    tube(sc, bezier_chain(bar, 3), 0.011, alu, 10)
    grips = {}
    for sx, side in ((-1, "L"), (1, "R")):
        g0 = Vector((sx * 0.245, 0.214, 1.045 + bar_c.z - 1.03))
        g1 = Vector((sx * 0.282, 0.140, 1.045 + bar_c.z - 1.03))
        tube(sc, [g0, g1], 0.0175, black, 10)
        grips[side] = (g0 + g1) / 2
        grips[side + "dir"] = (g1 - g0).normalized()
        tube(sc, [Vector((sx * 0.17, 0.315, bar_c.z + 0.012)), Vector((sx * 0.25, 0.262, bar_c.z + 0.002))], 0.006,
             alu, 6)
    b = Vector((-0.13, 0.334, bar_c.z + 0.022))
    sweep(sc, [b, b + Vector((0, 0, 0.022))], [(0.022, 0), (0.0, 0.022), (-0.022, 0), (0, -0.022)], alu)
    _box_into(sc, b + Vector((0, 0, 0.026)), (0.02, 0.02, 0.012), alu)
    prof_f = [(0.002, -0.028), (0.006, -0.030), (0.010, -0.016), (0.012, 0.0), (0.010, 0.016), (0.006, 0.030),
              (0.002, 0.028), (0.006, 0.013), (0.007, 0.0), (0.006, -0.013)]
    sweep(sc, arc_yz(Fa, R + 0.018, -22, 168, 20), prof_f, guard_m,
          n0=(0, math.cos(math.radians(-22)), math.sin(math.radians(-22))))
    flap = arc_yz(Fa, R + 0.02, -22, -22, 1)[0]
    _box_into(sc, flap + Vector((0, 0.012, -0.045)), (0.05, 0.004, 0.09), black,
              Matrix.Rotation(math.radians(-15), 3, "X"))
    for a in (15, 60):
        q = arc_yz(Fa, R + 0.022, a, a, 1)[0]
        for sx in (-1, 1):
            tube(sc, [q + Vector((sx * 0.026, 0, 0)), Fa + Vector((sx * 0.055, 0, 0))], 0.0026, alu, 6)
    lamp_at = crown + Vector((0, 0.075, -0.015))
    tube(sc, [lamp_at - Vector((0, 0.035, 0)), lamp_at + Vector((0, 0.035, 0))], 0.026, black, 14)
    sweep(sc, [lamp_at + Vector((0, 0.035, 0)), lamp_at + Vector((0, 0.038, 0))], circle(0.022, 14), lamp_m)
    _box_into(sc, lamp_at + Vector((0, -0.02, -0.035)), (0.012, 0.05, 0.03), black)
    _box_into(sc, crown + Vector((0, 0.05, 0.05)), (0.05, 0.004, 0.03), whiteref)
    if basket:
        _basket(sc, Vector((0, 0.53, 0.915)), alu if rnd.random() < 0.4 else black, Fa)
    steer_o = _rigid(sc, name + "_fork", c, steer, st_rest.inverted())
    # ---- wheels
    wheels = {}
    for key, A, par, inv in (("R", Ra, root, None), ("F", Fa, steer, st_rest.inverted())):
        wc = Cage()
        wc.flat = set()
        o0 = Vector()
        ang = [0, 30, 60, 80, 100, 130, 180, 230, 260, 280, 300, 330]
        prof_t = [(0.0195 * math.cos(math.radians(a)), 0.021 * math.sin(math.radians(a))) for a in ang]
        mats_t = [rubber] * 12
        mats_t[3] = refl
        mats_t[8] = refl
        sweep(wc, arc_yz(o0, R - 0.0195, 0, 360, 48)[:-1], prof_t, mats_t, closed=True, n0=(0, 1, 0))
        prof_r = [(-0.012, -0.011), (0.004, -0.011), (0.007, -0.006), (0.007, 0.006), (0.004, 0.011), (-0.012, 0.011)]
        sweep(wc, arc_yz(o0, 0.300, 0, 360, 48)[:-1], prof_r, alu, closed=True, n0=(0, 1, 0))
        hub_r = 0.034 if key == "F" else 0.030
        tube(wc, [Vector((-0.05, 0, 0)), Vector((0.05, 0, 0))], hub_r * 0.75, alu, 14)
        tube(wc, [Vector((-0.012, 0, 0)), Vector((0.012, 0, 0))], hub_r, alu if key == "F" else black, 14)
        for sx in (-1, 1):
            tube(wc, [Vector((sx * 0.032, 0, 0)), Vector((sx * 0.036, 0, 0))], 0.031, alu, 14)
            tube(wc, [Vector((sx * 0.050, 0, 0)), Vector((sx * 0.070, 0, 0))], 0.006, alu, 6)
        for i in range(36):
            sx = -1 if i % 2 else 1
            ar = 2 * math.pi * i / 36
            ah = ar + (1 if (i // 2) % 2 else -1) * 2 * math.pi * 3 / 18
            hp = Vector((sx * 0.033, 0.029 * math.cos(ah), 0.029 * math.sin(ah)))
            rp = Vector((sx * 0.004, 0.290 * math.cos(ar), 0.290 * math.sin(ar)))
            tube(wc, [hp, rp], 0.0011, alu, 4, caps=False)
        wo = _rigid(wc, f"{name}_wheel_{key}", c, par, inv)
        wo.location = A
        wo.rotation_mode = "XYZ"
        wheels[key] = wo
    # ---- crank and pedals
    cc = Cage()
    cc.flat = set()
    sweep(cc, arc_yz(Vector(), 0.095, 0, 360, 36, x=0.058)[:-1], [(-0.006, -0.002), (0.006, -0.002), (0.006, 0.002),
                                                                     (-0.006, 0.002)], black, closed=True,
          n0=(0, 1, 0))
    for i in range(5):
        a = 2 * math.pi * i / 5
        tube(cc, [Vector((0.058, 0, 0)), Vector((0.058, 0.09 * math.cos(a), 0.09 * math.sin(a)))], 0.006, alu, 6)
    tube(cc, [Vector((-0.07, 0, 0)), Vector((0.07, 0, 0))], 0.012, alu, 10)
    tube(cc, [Vector((0.066, 0, 0)), Vector((0.092, 0.170, 0))], 0.010, alu, 8)
    tube(cc, [Vector((-0.066, 0, 0)), Vector((-0.092, -0.170, 0))], 0.010, alu, 8)
    crank = _rigid(cc, name + "_crank", c, root)
    crank.location = BB
    crank.rotation_mode = "XYZ"
    pedals = {}
    for side, sx, yy in (("R", 1, 0.170), ("L", -1, -0.170)):
        pc = Cage()
        pc.flat = set()
        _box_into(pc, (sx * 0.055, 0, 0), (0.095, 0.062, 0.020), black)
        _box_into(pc, (sx * 0.055, 0.032, 0), (0.06, 0.004, 0.012), yel)
        _box_into(pc, (sx * 0.055, -0.032, 0), (0.06, 0.004, 0.012), yel)
        tube(pc, [Vector((0, 0, 0)), Vector((sx * 0.012, 0, 0))], 0.006, alu, 6)
        po = _rigid(pc, f"{name}_pedal_{side}", c, crank)
        po.location = (sx * 0.094, yy, 0)
        po.rotation_mode = "XYZ"
        pedals[side] = po
    return dict(name=name, root=root, steer=steer, steer_rest=st_rest, wheels=wheels, crank=crank, pedals=pedals,
                R=R, wb=wb, BB=BB, sdir=sdir, saddle=S_top, grips=grips, Q=Q, axis=ax, dev=DEV, frame=frame_o,
                fork=steer_o)


def bezier_chain(pts, n=3):
    """Round off a polyline: quadratic bezier through midpoints (keeps the ends)."""
    pts = [Vector(p) for p in pts]
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a = (pts[i - 1] + pts[i]) / 2 if i > 1 else pts[0]
        b = (pts[i] + pts[i + 1]) / 2 if i < len(pts) - 2 else pts[-1]
        out += bezier(a, pts[i], b, n)[1:]
    return out


def _basket(cg, center, mat, axle):
    """Front wire basket (about 36 x 27 x 22 cm) with struts down to the front axle."""
    w0, d0, w1, d1, h = 0.36, 0.27, 0.32, 0.23, 0.22
    zt, zb = center.z + h / 2, center.z - h / 2

    def rect(w, d, z):
        return [center + Vector((x, y, z - center.z)) for x, y in
                ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2))]
    for z, w, d, r in ((zt, w0, d0, 0.0045), (zb + h * 0.66, w0 - (w0 - w1) * 0.34, d0 - (d0 - d1) * 0.34, 0.0022),
                       (zb + h * 0.33, w0 - (w0 - w1) * 0.67, d0 - (d0 - d1) * 0.67, 0.0022), (zb, w1, d1, 0.0035)):
        r_ = rect(w, d, z)
        sweep(cg, r_ + [r_[0]], circle(r, 6), mat, caps=False)
    top, bot = rect(w0, d0, zt), rect(w1, d1, zb)
    for i in range(4):
        a, b = top[i], top[(i + 1) % 4]
        a2, b2 = bot[i], bot[(i + 1) % 4]
        n = max(2, int((b - a).length / 0.035))
        for k in range(1, n):
            u = k / n
            tube(cg, [a.lerp(b, u), a2.lerp(b2, u)], 0.0018, mat, 4, caps=False)
        tube(cg, [a, a2], 0.003, mat, 4, caps=False)
    for k in range(1, 8):
        x = -w1 / 2 + w1 * k / 8
        tube(cg, [center + Vector((x, -d1 / 2, zb - center.z)), center + Vector((x, d1 / 2, zb - center.z))], 0.0018,
             mat, 4, caps=False)
    for sx in (-1, 1):
        tube(cg, [center + Vector((sx * w1 * 0.35, 0.0, zb - center.z)), axle + Vector((sx * 0.06, 0, 0))], 0.004,
             mat, 6)
    tube(cg, [center + Vector((0, -d0 / 2, zt - center.z - 0.02)), center + Vector((0, -d0 / 2 - 0.09, zt -
                                                                                      center.z - 0.03))], 0.006, mat, 6)


def _fit_saddle(fig, BB, sdir):
    """Seat-post length (BB to saddle top along the seat tube) so that the rider's knee is nearly straight (leg at
    0.96 of its length) with the pedal at the bottom."""
    lo, hi = 0.50, 1.00
    for _ in range(30):
        h = (lo + hi) / 2
        hip, ank = _ride_hip_and_ankle(fig, BB + sdir * h, BB + Vector((0.105, 0.0, -0.170)), "R")
        d = (hip - ank).length
        if d < 0.96 * (fig["lengths"]["thigh"] + fig["lengths"]["shin"]):
            lo = h
        else:
            hi = h
    return (lo + hi) / 2


RIDE_TILT = math.radians(20)


def _ride_pelvis(fig, S_top, slide=0.0):
    H = fig["H"]
    P = S_top + Vector((0, -0.020 * fig["k"] + slide * 0.11, 0.118 * fig["k"] - slide * 0.025))
    Rp = Matrix.Rotation(-RIDE_TILT * (1 - 0.4 * slide), 3, "X")
    return P, Rp


def _ride_hip_and_ankle(fig, S_top, pedal, side, pitch=math.radians(-18)):
    J = fig["J"]
    P, Rp = _ride_pelvis(fig, S_top)
    hip = P + Rp @ (J["hip" + side] - J["pelvis"])
    geo = _foot_geo(fig, side)
    F = pedal + Vector((0, 0, 0.011)) - geo["ball"]
    return hip, _foot_place(geo, F, math.pi / 2, pitch)


# ------------------------------------------------------------------ cyclist
def cyclist(c, name="cyclist", rider=None, bike=None, helmet=False, seed=0):
    """A rider on a city bike. rider: person() arguments (jacket=YELLOW for the yellow rain jacket, hiviz=True
    for a fluorescent one); bike: city_bike() arguments (frame "step" | "diamond", basket=True, color=...).
    The rider's armature is parented to the bike root; ride() moves both. Returns dict(rider, bike, root)."""
    rk = dict(rider or {})
    rk.setdefault("seed", seed)
    if helmet:
        rk["headwear"] = "helmet"
    if rk.get("bag") in ("shoulder", "tote"):
        rk["bag"] = "backpack"
    fig = person(c, name + "_rider", **rk)
    bk = dict(bike or {})
    bk.setdefault("seed", seed)
    b = city_bike(c, name + "_bike", rider=fig, **bk)
    fig["arm"].parent = b["root"]
    cy = dict(name=name, rider=fig, bike=b, root=b["root"])
    ride(cy, None, [(0.0, 4.0)], frames=[1], _static=True)
    return cy


def _crank_plan(sv, fps, dev, foot):
    """Crank angle per frame: turns with distance while the rider pedals (development dev metres a turn),
    freewheels when braking or rolling slowly (cranks go level), and sets the take-off pedal at two o'clock
    before a stop. Angle 0: right crank pointing forward; it grows in the pedalling direction."""
    n = len(sv)
    a = 0.0
    out, ped = [], []
    stop_a = 7 * math.pi / 4 if foot == "L" else 3 * math.pi / 4
    for f in range(n):
        s, v = sv[f]
        ds = s - sv[f - 1][0] if f else 0.0
        acc = (sv[min(f + 1, n - 1)][1] - sv[max(f - 1, 0)][1]) * fps / max(1, (min(f + 1, n - 1) - max(f - 1, 0)))
        stopping = any(sv[j][1] < 0.15 for j in range(f, min(n, f + int(1.2 * fps))))
        pedal = v > 0.35 and acc > -0.25 and not (stopping and v < 2.5 and acc < 0.05)
        if pedal:
            a += 2 * math.pi * ds / dev
        else:
            target = stop_a if stopping else round(a / math.pi) * math.pi
            k = 2 * math.pi
            d = ((target - a) + math.pi) % k - math.pi
            step = _clamp(d, -3.0 / fps, 3.0 / fps)
            a += step
        out.append(a)
        ped.append(pedal)
    return out, ped


def _hand_on_grip(fig, side, G, gdir):
    """Wrist position and hand rotation that close the fist round a grip at G (bike space)."""
    H = fig["H"]
    sx = -1 if side == "L" else 1
    fwd = (Vector((sx * 0.15, 1.0, -0.55))).normalized()
    palm = Vector((-sx * 0.35, 0.25, -1.0))
    hR = _hand_R(fwd, palm, side)
    wrist = G - fwd * (0.052 * H) + Vector((0, 0, 0.012 * H)) - hR.col[0] * (0.004 * H) * (1 if side == "L" else -1)
    return wrist, hR


def ride(cy, path, sv, frames=None, ground=None, signal=(), foot="L", look=(), fps=FPS, frame0=1, dev=None,
         _static=False):
    """Bake a cyclist along `path` with per-frame (s, v): the bike follows the path (heading from rear to front
    axle), the wheels turn with distance (angle = distance / radius), the crank turns at speed / development
    (pedalling) or freewheels, the bike leans into turns (atan(v^2 kappa / g)) and steers (atan(wheelbase kappa)),
    the rider sits, pedals and holds the bars. signal: [("L" | "R", t0, t1)] arm out to that side. At a stop the
    rider puts the `foot` side down and leans the bike a little that way. Returns per-frame data."""
    fig, b = cy["rider"], cy["bike"]
    n = len(sv)
    frames = frames or list(range(frame0, frame0 + n))
    H = fig["H"]
    rig = fig.get("rig") or Rig(fig["arm"])
    fig["rig"] = rig
    dev = dev or b["dev"]
    R, wb = b["R"], b["wb"]
    alpha, pedalling = _crank_plan(sv, fps, dev, foot)
    rnd = random.Random(fig["seed"] * 7 + 1)
    ph0 = rnd.uniform(0, 6.28)
    # where and how the bike stands each frame
    poses = []
    for f in range(n):
        s, v = sv[f]
        if path is None:
            poses.append((Vector((0, 0)), math.pi / 2, 0.0))
            continue
        pf, _ = path.at(s + wb / 2)
        pr, _ = path.at(s - wb / 2)
        d = pf - pr
        h = math.atan2(d.y, d.x)
        h1, h0 = _heading(path, s + 0.6, 0.3), _heading(path, s - 0.6, 0.3)
        kap = ((h1 - h0 + math.pi) % (2 * math.pi) - math.pi) / 1.2
        poses.append(((pf + pr) / 2, h, kap))
    raw_stop = []
    for f in range(n):
        v = sv[f][1]
        ahead = [sv[j][1] for j in range(f, min(n, f + int(0.4 * fps)))]
        raw_stop.append(1.0 if (v < 0.15 or (v < 1.0 and min(ahead) < 0.15)) else 0.0)
    k = int(0.35 * fps)
    w_fd = []
    for f in range(n):
        lo, hi = max(0, f - k), min(n, f + k + 1)
        x = sum(raw_stop[lo:hi]) / (hi - lo)
        w_fd.append(x * x * (3 - 2 * x))
    steer, lean = [], []
    for f in range(n):
        lo, hi = max(0, f - 3), min(n, f + 4)
        kap = sum(poses[j][2] for j in range(lo, hi)) / (hi - lo)
        v = sv[f][1]
        steer.append(_clamp(math.atan(wb * kap), -0.6, 0.6) * (1 - 0.5 * w_fd[f]))
        lt = -math.atan(v * v * kap / G) if v > 1.0 else 0.0
        ls = math.radians(-9 if foot == "L" else 9)
        lean.append(_clamp(lt, -0.45, 0.45) * (1 - w_fd[f]) + ls * w_fd[f])
    J = fig["J"]
    rec, data = [], []
    rl, rm = b["root"], [b["wheels"]["R"], b["wheels"]["F"]]
    root_track, steer_k, wheel_k, crank_k = [], [], [], []
    for f in range(n):
        t = f / fps
        s, v = sv[f]
        xy, h, _k = poses[f]
        z0 = ground(xy.x, xy.y) if ground else 0.0
        a = alpha[f]
        root_track.append((xy.x, xy.y, z0, lean[f], h))
        # --- rider in bike space (the armature is parented to the bike root)
        slide = w_fd[f]
        P, Rp = _ride_pelvis(fig, b["saddle"], slide)
        st = dict(pelvis_pos=P, pelvis_R=Rp, roll=0.0, tilt=RIDE_TILT * (1 - 0.4 * slide))
        Rs = Matrix.Rotation(steer[f], 3, "Z")
        Mst = b["steer_rest"].to_3x3()
        Q = b["Q"]
        legs = {}
        for side, sx, off in (("R", 1, 0.0), ("L", -1, math.pi)):
            aa = a + off
            ped = b["BB"] + Vector((sx * 0.105, 0.170 * math.cos(aa), -0.170 * math.sin(aa)))
            pitch = math.radians(-15 - 10 * math.sin(aa))
            geo = _foot_geo(fig, side)
            F = ped + Vector((0, 0, 0.011)) - Matrix.Rotation(sx * math.radians(-3), 3, "Z") @ geo["ball"]
            ank = _foot_place(geo, F, math.pi / 2 + sx * math.radians(-3), pitch)
            fR = Matrix.Rotation(sx * math.radians(-3), 3, "Z") @ Matrix.Rotation(pitch, 3, "X")
            if side == foot and slide > 1e-3:
                # foot down: flat on the ground beside the bike (world), carried into bike space
                Mroot = (Matrix.Translation((xy.x, xy.y, z0)) @ Matrix.Rotation(h - math.pi / 2, 4, "Z") @
                         Matrix.Rotation(lean[f], 4, "Y"))
                gw = Mroot @ Vector((sx * 0.30, -0.10, 0.0))
                gw.z = z0
                Fl = Mroot.inverted() @ gw
                lean_c = Matrix.Rotation(-lean[f], 3, "Y")
                ank_g = Fl + lean_c @ Vector((0, 0, geo["a_h"]))
                e = slide
                ank = ank.lerp(ank_g, e) + Vector((0, 0, 0.07 * H * math.sin(math.pi * e)))
                fR_g = lean_c @ Matrix.Rotation(sx * math.radians(-8), 3, "Z")
                fR = fR.to_4x4().lerp(fR_g.to_4x4(), e).to_3x3().normalized()
            pole = Vector((sx * 0.18, 1.0, 0.25))
            legs[side] = [ank, fR, fR, pole]
        if slide > 1e-3:
            # off the saddle front with the foot down: lower the pelvis until that leg reaches the ground
            Lmax = 0.975 * (fig["lengths"]["thigh"] + fig["lengths"]["shin"])
            hip = P + Rp @ (J["hip" + foot] - J["pelvis"])
            a_ = legs[foot][0]
            hd = math.hypot(hip.x - a_.x, hip.y - a_.y)
            if hd < Lmax and (hip - a_).length > Lmax:
                P.z -= min(0.16, (hip.z - a_.z) - math.sqrt(Lmax * Lmax - hd * hd))
        st["legs"] = legs
        # --- upper body: lean on the bars, level gaze, look, breathing
        ly, lp = _look_at(look, t, (xy.x, xy.y), h, H) if look else (0.0, 0.0)
        bre = math.radians(0.6) * math.sin(2 * math.pi * t / 3.6 + ph0)
        st["spine"] = _qy(0.15 * ly) @ _qx(math.radians(-3))
        st["chest"] = _qy(0.15 * ly) @ _qx(math.radians(2) + bre)
        lean_t = RIDE_TILT * (1 - 0.4 * slide) + math.radians(-1)
        rem = ly * 0.7
        st["neck"] = _qy(rem * 0.4) @ _qx(-lean_t * 0.55 - lp * 0.4)
        st["head"] = _qy(rem * 0.6) @ _qx(-lean_t * 0.45 - lp * 0.6)
        arms = {}
        gsig = []
        for g in signal:
            gsig.append(("signal_" + g[0], g[1], g[2]))
        gs = _gestures_at(fig, gsig, t)
        grip = {}
        for side in ("L", "R"):
            G0 = b["grips"][side]
            Gs = Q + Mst @ Rs @ Mst.inverted() @ (G0 - Q)
            gdir = Mst @ Rs @ Mst.inverted() @ b["grips"][side + "dir"]
            wrist, hR = _hand_on_grip(fig, side, Gs, gdir)
            hR = Mst @ Rs @ Mst.inverted() @ hR
            sx = -1 if side == "L" else 1
            pole = Vector((sx * 0.8, -0.4, -1.0))
            g_bar = (1.0, wrist, hR, pole, 1.0, 0.0)
            arms[side] = dict(fk=(_qx(0.0), _qx(0.3), _qx(0.0)), g=g_bar, carry=False)
            grip[side] = 1.0
            if side in gs:
                wsig = gs[side][0]
                arms[side]["g_sig"] = gs[side]
                grip[side] = 1.0 - wsig
        st["arms"] = arms
        basis, pose = _solve_ride(fig, rig, st)
        rec.append(dict(basis=basis, grip=grip))
        steer_k.append(steer[f])
        wheel_k.append(-s / R)
        crank_k.append(-a)
        data.append(dict(s=s, v=v, alpha=a, pedal=pedalling[f], lean=lean[f], steer=steer[f], foot_down=w_fd[f]))
    _write(fig, frames, rec, None)
    # bike keys
    rl.rotation_mode = "XYZ"
    if path is not None:
        yaw = _unwrap([r[4] - math.pi / 2 for r in root_track])
        for i in range(3):
            keys(rl, "location", i, frames, [r[i] for r in root_track])
        keys(rl, "rotation_euler", 0, frames, [0.0] * n)
        keys(rl, "rotation_euler", 1, frames, [r[3] for r in root_track])
        keys(rl, "rotation_euler", 2, frames, yaw)
    keys(b["steer"], "rotation_euler", 2, frames, steer_k)
    for wo in rm:
        keys(wo, "rotation_euler", 0, frames, wheel_k)
    keys(b["crank"], "rotation_euler", 0, frames, crank_k)
    for po in b["pedals"].values():
        keys(po, "rotation_euler", 0, frames, [-x for x in crank_k])
    cy["data"] = data
    cy["frames"] = frames
    return data


def _solve_ride(fig, rig, st):
    """Like _solve, with the hands held at bike-space grip targets (not carried by the chest); a signalling arm
    blends to the gesture carried by the chest."""
    arms = st["arms"]
    st2 = dict(st)
    st2["arms"] = {s: dict(fk=a["fk"], g=None) for s, a in arms.items()}
    pose, basis = {}, {}
    rig.ik("hips", _M(st["pelvis_R"] @ rig.rest_rot("hips"), st["pelvis_pos"]), pose, basis)
    for n_ in ("spine", "chest", "neck", "head"):
        rig.fk(n_, st[n_], pose, basis)
    L = fig["lengths"]
    for side in ("L", "R"):
        ankle, footR, toeR, pole = st["legs"][side]
        th, sh, ft, to = "thigh." + side, "shin." + side, "foot." + side, "toe." + side
        hip = rig.base(th, pose).translation
        knee, end, n = two_bone(hip, ankle, L["thigh"], L["shin"], pole)
        rig.ik(th, _M(_frame_xy(knee - hip, n), hip), pose, basis)
        rig.ik(sh, _M(_frame_xy(end - knee, n), knee), pose, basis)
        rig.ik(ft, _M(footR @ rig.rest_rot(ft), end), pose, basis)
        rig.ik(to, _M(toeR @ rig.rest_rot(to), pose[ft] @ Vector((0, rig.length[ft], 0))), pose, basis)
    chest_rel = pose["chest"] @ rig.rest["chest"].inverted()
    for side in ("L", "R"):
        a = arms[side]
        ua, fa, hd = "upperarm." + side, "forearm." + side, "hand." + side
        _w, wrist, hR, pole, _g, _hp = a["g"]
        sh_ = rig.base(ua, pose).translation
        res = []
        for wr_, hR_, pole_ in [(wrist, hR, pole)] + ([tuple(_carry(chest_rel, a["g_sig"])[k] for k in
                                                             ("wrist", "handR", "pole"))] if "g_sig" in a else []):
            el, end, n = two_bone(sh_, wr_, L["upperarm"], L["forearm"], pole_)
            b_, p_ = {}, dict(pose)
            rig.ik(ua, _M(_frame_xy(el - sh_, -n), sh_), p_, b_)
            rig.ik(fa, _M(_frame_xy(end - el, -n), el), p_, b_)
            rig.ik(hd, _M(hR_, end), p_, b_)
            res.append(b_)
        wsig = a["g_sig"][0] if "g_sig" in a else 0.0
        for n_ in (ua, fa, hd):
            q = res[0][n_].to_quaternion()
            if wsig > 0:
                q = q.slerp(res[1][n_].to_quaternion(), wsig)
            rig.fk(n_, q, pose, basis)
    return basis, pose


# ------------------------------------------------------------------ roles
def _device(fig, c):
    """Handheld ticket device (rugged PDA with printer): dark grey body, screen, keys; no brand, no crest."""
    H = fig["H"]
    body = material("device", srgb(46, 48, 52), 0.45, coat=0.3)
    screen = material("screen", srgb(30, 60, 80), 0.1, emit=srgb(150, 200, 230), estr=0.6, coat=1.0)
    keys_m = material("devkeys", srgb(90, 92, 96), 0.5)
    o = rbox(fig["name"] + "_device", (0.075, 0.035, 0.19), body, c, 0.008)
    s_ = rbox(fig["name"] + "_screen", (0.058, 0.004, 0.075), screen, c, 0.002, center=(0, -0.018, 0.035))
    k_ = rbox(fig["name"] + "_keys", (0.054, 0.004, 0.05), keys_m, c, 0.002, center=(0, -0.018, -0.045))
    paper = rbox(fig["name"] + "_ticket", (0.055, 0.001, 0.045), material("paper", srgb(236, 234, 226), 0.8), c, 0,
                 center=(0, 0.0, 0.115))
    for p in (s_, k_, paper):
        p.parent = o
    hb = fig["arm"].data.bones["hand.L"]
    # placed in the write pose: across the palm, screen facing the eyes; then carried by the hand
    wr, hR, _pole, _g, _hp = gesture_targets(fig, "write", 0.0, "L")
    yd = Vector((0, 0.35, -0.94))
    xd = Vector((1, 0, 0))
    Rd = Matrix((xd, yd, xd.cross(yd))).transposed()
    pos = wr + hR.col[1] * (0.042 * H) + hR.col[0] * (0.020 * H)
    attach(fig, o, "hand.L", hb.matrix_local @ _M(hR, wr).inverted() @ _M(Rd, pos))
    fig["props"]["device"] = o
    return o


def _laser(fig, c):
    """Handheld speed laser (lidar gun): body with two front apertures, a sighting scope on top, pistol grip.
    Generic shape, no maker's name."""
    H = fig["H"]
    body = material("laser", srgb(36, 38, 42), 0.4, coat=0.4)
    glass = material("laserglass", srgb(20, 30, 40), 0.05, coat=1.0)
    o = rbox(fig["name"] + "_laser", (0.075, 0.20, 0.095), body, c, 0.012, center=(0, 0.04, 0.10))
    parts = [rbox("grip", (0.040, 0.05, 0.11), body, c, 0.010, center=(0, -0.01, 0.025)),
             rbox("scope", (0.030, 0.10, 0.032), body, c, 0.008, center=(0, 0.02, 0.165)),
             rbox("lens1", (0.040, 0.004, 0.040), glass, c, 0.004, center=(0.0, 0.142, 0.110)),
             rbox("lens2", (0.022, 0.004, 0.022), glass, c, 0.003, center=(0.0, 0.142, 0.072)),
             rbox("trigger", (0.010, 0.02, 0.022), body, c, 0.003, center=(0, 0.02, 0.055))]
    for p in parts:
        p.parent = o
    hb = fig["arm"].data.bones["hand.R"]
    # place it in the gesture pose of the right hand, then express that in the hand's rest frame
    wr, hR, _pole, _g, _hp = gesture_targets(fig, "laser", 0.0, "R")
    M_hand = _M(hR, wr)
    fist = wr + hR.col[1] * (0.045 * H)
    M_dev = _M(Matrix.Identity(3), fist - Vector((0, -0.01, 0.03)))
    rest_hand = hb.matrix_local
    attach(fig, o, "hand.R", rest_hand @ M_hand.inverted() @ M_dev)
    fig["props"]["laser"] = o
    return o


def parking_attendant(c, name="attendant", sex="f", height=None, seed=11, **kw):
    """Municipal parking enforcement: dark navy uniform jacket and trousers, light grey collar band, navy baseball
    cap, black shoes, handheld ticket device in the left hand. No crest, no authority name."""
    kw.setdefault("skin", 2)
    kw.setdefault("hair", "ponytail" if sex == "f" else "short")
    p = person(c, name, height=height or (1.68 if sex == "f" else 1.78), sex=sex, jacket=NAVY, trousers=NAVY,
               shoes=srgb(20, 20, 22), sole=srgb(26, 26, 26), headwear="baseball", headwear_color=NAVY, hem=0.52,
               seed=seed, **kw)
    _device(p, c)
    p["role"] = "attendant"
    return p


def police_officer(c, name="police", sex="m", height=None, seed=12, **kw):
    """German police look: blue uniform jacket with plain "POLIZEI" lettering (back and chest, neutral sans), dark
    blue trousers and peaked cap, black duty belt, black boots, a handheld speed laser in the right hand. No state
    crest, no badge on the cap."""
    kw.setdefault("skin", 1)
    kw.setdefault("hair", "short")
    p = person(c, name, height=height or (1.82 if sex == "m" else 1.70), sex=sex, jacket=POLICE_BLUE,
               trousers=POLICE_DARK, shoes=srgb(16, 16, 18), sole=srgb(20, 20, 20), headwear="cap",
               headwear_color=POLICE_DARK, hem=0.585, belt=True, text="POLIZEI", seed=seed, **kw)
    _laser(p, c)
    p["role"] = "police"
    return p


def names_used():
    """Every object, material, mesh and text body made by this module in the current file (for brand checks)."""
    out = []
    for coll in (bpy.data.objects, bpy.data.materials, bpy.data.meshes, bpy.data.armatures):
        out += [x.name for x in coll]
    out += [cu.body for cu in bpy.data.curves if hasattr(cu, "body")]
    return out
