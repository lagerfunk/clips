"""Drive Like a Local: Florida. US world kit for the five Florida scenes (fl01 .. fl05), built to MUTCD 2009 (r. 2023)
and FDOT Standard Plans (Index 711-001 pavement markings, 700-series signals). It lives in fl01/ as fl01_uskit.py so
the public build copies it next to the scenes on the runners; the scenes in fl02 .. fl05 put ../fl01 on sys.path.

Road along +y, right-hand traffic: northbound lanes at x > 0, southbound at x < 0. Metres.
  12 ft lanes (3.66 m), 6 in lines, white broken lane lines 10 ft dash and 30 ft gap, double yellow centre line,
  white right edge line, yellow left edge line on the freeway, 24 in stop bars, ladder crosswalks (24 in bars, 12 in
  transverse lines, 10 ft wide), span-wire signals with backplates (bottom of housing 15 to 25.6 ft above the road),
  freeway with 10 ft paved right shoulder and a concrete median barrier, open-road toll gantry with camera boxes.
Nothing carries a name, logo or wordmark; plates are blank (owner rule: no invented Florida plate). Every marking
object carries custom properties (us_line, us_x, us_dash, us_gap) that tests/test_gta_build.py measures."""
import math
import random

import bpy
from mathutils import Matrix, Vector

import jx
import motion
import stage
import vehicles as V
import world as W

try:
    import signs as SG
except ImportError:  # pragma: no cover
    SG = None

FT = 0.3048
IN = FT / 12
LANE = 12 * FT                      # 3.6576 m travel lane (MUTCD 3A, FDOT standard)
DASH, GAP = 10 * FT, 30 * FT        # broken lane line: 10 ft line, 30 ft gap (MUTCD 3A.06)
LINE = 6 * IN                       # 6 in longitudinal lines (FDOT Index 711-001)
DY_SPACE = 6 * IN                   # space between the two lines of the double yellow
STOP_BAR = 24 * IN                  # stop line 24 in (MUTCD 3B.16 allows 12 to 24 in)
XW_BAR, XW_SPACE, XW_W, XW_EDGE = 24 * IN, 24 * IN, 10 * FT, 12 * IN   # ladder crosswalk
STOP_TO_XW = 4 * FT                 # stop bar 4 ft ahead of the crosswalk (MUTCD 3B.16)
SHOULDER, SHOULDER_L = 10 * FT, 4 * FT
SIG_BOTTOM = 5.4                    # bottom of the signal housing above the road (15 to 25.6 ft, MUTCD 4D.15)
SIG_LENS = 12 * IN
GANTRY_CLEAR = 5.8                  # clearance under the toll gantry (> 16.5 ft)
KERB_H, GUTTER, WALK = 6 * IN, 2 * FT, 6 * FT
BANNED = ("rockstar", "take-two", "taketwo", "sunpass", "e-pass", "epass", "gta", "leonida", "vice city")

_m = {}


def lawn_mat(name):
    """Florida ground, stylised: large patches (about 80 m) of mown St Augustine green, darker shade green and
    sun-bleached tan, times a fine grain with bump, so the land never reads as one flat colour, near or far."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    bs = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord")
    big = N.new("ShaderNodeTexNoise")
    big.inputs["Scale"].default_value = 0.012
    big.inputs["Detail"].default_value = 5.0
    L.new(tc.outputs["Object"], big.inputs["Vector"])
    ramp = N.new("ShaderNodeValToRGB")
    el = ramp.color_ramp.elements
    el[0].position, el[0].color = 0.40, (0.07, 0.13, 0.03, 1)
    el[1].position, el[1].color = 0.62, (0.30, 0.28, 0.13, 1)
    mid = el.new(0.5)
    mid.color = (0.15, 0.23, 0.055, 1)
    L.new(big.outputs["Fac"], ramp.inputs["Fac"])

    def factor(node, k, c0):                 # node output * k + c0 (a brightness factor around 1)
        m_ = N.new("ShaderNodeMath")
        m_.operation = "MULTIPLY_ADD"
        m_.inputs[1].default_value, m_.inputs[2].default_value = k, c0
        L.new(node.outputs["Fac"], m_.inputs[0])
        return m_.outputs[0]

    def mul(a, b):
        m_ = N.new("ShaderNodeMath")
        m_.operation = "MULTIPLY"
        L.new(a, m_.inputs[0])
        L.new(b, m_.inputs[1])
        return m_.outputs[0]

    fine = N.new("ShaderNodeTexNoise")       # grain, about 0.7 m
    fine.inputs["Scale"].default_value = 1.4
    fine.inputs["Detail"].default_value = 6.0
    L.new(tc.outputs["Object"], fine.inputs["Vector"])
    clump = N.new("ShaderNodeTexNoise")      # clumps and worn spots, about 7 m: reads from a drone at 70 m
    clump.inputs["Scale"].default_value = 0.15
    clump.inputs["Detail"].default_value = 3.0
    L.new(tc.outputs["Object"], clump.inputs["Vector"])
    stripe = N.new("ShaderNodeTexWave")      # mowing stripes along the road (+y), 2.5 m light and 2.5 m dark
    stripe.wave_type, stripe.bands_direction = "BANDS", "X"
    stripe.inputs["Scale"].default_value = 0.126
    stripe.inputs["Distortion"].default_value = 0.6
    L.new(tc.outputs["Object"], stripe.inputs["Vector"])
    val = mul(mul(factor(fine, 1.5, 0.25), factor(clump, 1.3, 0.35)), factor(stripe, 0.24, 0.88))
    hsv = N.new("ShaderNodeHueSaturation")
    L.new(ramp.outputs["Color"], hsv.inputs["Color"])
    L.new(val, hsv.inputs["Value"])
    L.new(hsv.outputs["Color"], bs.inputs["Base Color"])
    bs.inputs["Roughness"].default_value = 0.95
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    L.new(fine.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bs.inputs["Normal"])
    return m


def mat(key, color, rough=0.5, metal=0.0, emit=None, estr=0.0, coat=0.0):
    if key not in _m:
        _m[key] = W.principled(key, color, rough, metal=metal, emit=emit, estr=estr, coat=coat)
    return _m[key]


def mats():
    if "asphalt" not in _m:
        _m["asphalt"] = W.asphalt("us_asphalt", base=(0.055, 0.056, 0.06), tracks=False)
        _m["asphalt_lot"] = W.asphalt("us_asphalt_lot", base=(0.075, 0.075, 0.078), tracks=False)
        _m["concrete"] = W.noisy("us_concrete", (0.52, 0.5, 0.46), (0.62, 0.6, 0.56), 2.5, rough=0.85)
        _m["grass"] = lawn_mat("us_grass")
        _m["white"] = mat("us_paint_white", (0.86, 0.86, 0.84), 0.55)
        _m["yellow"] = mat("us_paint_yellow", (0.85, 0.55, 0.03), 0.55)
    return _m


# ------------------------------------------------------------------ geometry helpers
def rects(name, rs, z, m, c, uv=False, **props):
    """One mesh of axis-aligned rectangles rs = [(x0, x1, y0, y1)] at height z."""
    vs, fs, uvs = [], [], []
    for x0, x1, y0, y1 in rs:
        k = len(vs)
        vs += [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
        uvs += [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        fs.append((k, k + 1, k + 2, k + 3))
    o = W.mesh_obj(name, vs, fs, m, c, uvs=uvs if uv else None)
    for k, v in props.items():
        o[k] = v
    return o


def poly(name, pts, z, m, c, uv=True):
    pts = list(pts)
    if sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
           for i in range(len(pts))) < 0:
        pts = pts[::-1]
    return W.mesh_obj(name, [(x, y, z) for x, y in pts], [tuple(range(len(pts)))], m, c,
                      uvs=[(x, y) for x, y in pts] if uv else None)


def box(name, c, ctr, size, m, bev=0.0, rz=0.0, parent=None):
    x, y, z = size[0] / 2, size[1] / 2, size[2] / 2
    vs = [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z), (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]
    fs = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    o = W.mesh_obj(name, vs, fs, m, c)
    o.location = ctr
    o.rotation_euler = (0, 0, rz)
    if bev:
        b = o.modifiers.new("b", "BEVEL")
        b.width, b.segments = bev, 2
    if parent:
        o.parent = parent
    return o


def cyl(name, c, ctr, r, h, m, n=16, rot=(0, 0, 0), r_top=None):
    r_top = r if r_top is None else r_top
    vs, fs = [], []
    for k in range(n):
        a = 2 * math.pi * k / n
        vs += [(r * math.cos(a), r * math.sin(a), -h / 2), (r_top * math.cos(a), r_top * math.sin(a), h / 2)]
    for k in range(n):
        j = (k + 1) % n
        fs.append((2 * k, 2 * j, 2 * j + 1, 2 * k + 1))
    fs += [tuple(2 * k for k in range(n))[::-1], tuple(2 * k + 1 for k in range(n))]
    o = W.mesh_obj(name, vs, fs, m, c, smooth=True)
    o.location, o.rotation_euler = ctr, rot
    return o


def offset(P, d):
    """Polyline P offset by d to its left (d < 0: right)."""
    out = []
    for i, p in enumerate(P):
        a = Vector(P[max(0, i - 1)])
        b = Vector(P[min(len(P) - 1, i + 1)])
        t = (b - a).normalized()
        out.append((p[0] - t.y * d, p[1] + t.x * d))
    return out


def band(name, P, d0, d1, z, m, c, z1=None):
    """Strip between offsets d0 and d1 of polyline P (flat at z, or a ramp from z to z1 for a kerb face)."""
    A, B = offset(P, d0), offset(P, d1)
    z1 = z if z1 is None else z1
    vs = [(a[0], a[1], z) for a in A] + [(b[0], b[1], z1) for b in B]
    n = len(P)
    fs = [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)]
    o = W.mesh_obj(name, vs, fs, m, c, uvs=[(v[0], v[1]) for v in vs])
    if o.data.polygons and o.data.polygons[0].normal.z < 0:
        o.data.flip_normals()
    return o


def fillet(cx, cy, r, a0, a1, n=8):
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / n), cy + r * math.sin(a0 + (a1 - a0) * k / n))
            for k in range(n + 1)]


def tag(o, **kw):
    for k, v in kw.items():
        o[k] = v
    return o


# ------------------------------------------------------------------ pavement markings
def solid(name, x, y0, y1, c, colour="white", w=LINE, z=0.006):
    m = mats()[colour]
    return tag(rects(name, [(x - w / 2, x + w / 2, y0, y1)], z, m, c), us_line=f"{colour}_solid", us_x=x, us_w=w)


def broken(name, x, y0, y1, c, colour="white", phase=0.0, w=LINE, z=0.006):
    rs, y = [], y0 + phase
    while y < y1:
        rs.append((x - w / 2, x + w / 2, y, min(y1, y + DASH)))
        y += DASH + GAP
    return tag(rects(name, rs, z, mats()[colour], c), us_line=f"{colour}_broken", us_x=x, us_w=w, us_dash=DASH,
               us_gap=GAP)


def double_yellow(name, x, y0, y1, c):
    off = (DY_SPACE + LINE) / 2
    rs = [(x - off - LINE / 2, x - off + LINE / 2, y0, y1), (x + off - LINE / 2, x + off + LINE / 2, y0, y1)]
    return tag(rects(name, rs, 0.006, mats()["yellow"], c), us_line="double_yellow", us_x=x, us_w=LINE,
               us_space=DY_SPACE)


def stop_bar(name, x0, x1, y, c, facing=1):
    """24 in white stop line across the approach lanes; y is its edge nearest the intersection."""
    y0, y1 = (y - STOP_BAR, y) if facing > 0 else (y, y + STOP_BAR)
    return tag(rects(name, [(x0, x1, y0, y1)], 0.007, mats()["white"], c), us_line="stop_bar", us_w=STOP_BAR)


def ladder(name, x0, x1, y0, y1, c, along="x"):
    """Ladder crosswalk: two 12 in transverse lines and 24 in bars between them (bars parallel to traffic)."""
    rs = []
    if along == "x":       # crossing an arterial that runs along y: the people walk along x
        rs += [(x0, x1, y0, y0 + XW_EDGE), (x0, x1, y1 - XW_EDGE, y1)]
        x = x0 + XW_SPACE / 2
        while x + XW_BAR <= x1:
            rs.append((x, x + XW_BAR, y0 + XW_EDGE, y1 - XW_EDGE))
            x += XW_BAR + XW_SPACE
    else:
        rs += [(x0, x0 + XW_EDGE, y0, y1), (x1 - XW_EDGE, x1, y0, y1)]
        y = y0 + XW_SPACE / 2
        while y + XW_BAR <= y1:
            rs.append((x0 + XW_EDGE, x1 - XW_EDGE, y, y + XW_BAR))
            y += XW_BAR + XW_SPACE
    return tag(rects(name, rs, 0.007, mats()["white"], c), us_line="crosswalk", us_bar=XW_BAR, us_w=XW_W)


def turn_arrow(name, x, y, c, right=True):
    """Right-turn lane arrow (MUTCD 3B.20 shape, simplified outline), 2.9 m long, pointing +y then right."""
    s = 1 if right else -1
    pts = [(1.3 * px, 1.3 * py) for px, py in ((-0.15, 0), (0.15, 0), (0.15, 1.6), (0.6, 1.6), (0.6, 1.35),
                                                (1.1, 1.85), (0.6, 2.35), (0.6, 2.1), (-0.15, 2.1))]
    if not right:
        pts = [(-px, py) for px, py in pts]
    return tag(poly(name, [(x + px, y + py) for px, py in pts], 0.007, mats()["white"], c, uv=False),
               us_line="arrow")


# ------------------------------------------------------------------ the arterial (urban, curbed)
class Arterial:
    """Four-lane (lanes=2 each way) undivided arterial with a painted double yellow, white lane and edge lines, curb
    and gutter, 6 ft sidewalks and grass. Optional one signalised crossing with a cross street (two lanes) and a
    northbound right-turn lane."""

    def __init__(self, c, y0=-400.0, y1=400.0, lanes=2, cross=None, rtl=False):
        self.c, self.y0, self.y1, self.lanes, self.cross, self.rtl = c, y0, y1, lanes, cross, rtl
        self.edge = lanes * LANE                  # centre of the white edge line
        self.lip = self.edge + 0.3                # gutter lip (pavement edge)
        self.B = LANE + 0.3 if cross is not None else 0.0   # cross street half width to its lip
        self.build()

    def lane_x(self, k, nb=True):
        """Centre of lane k (0 = next to the centre line) northbound (or southbound with nb=False)."""
        x = (k + 0.5) * LANE
        return x if nb else -x

    def build(self):
        M, c = mats(), self.c
        A, yc, B = self.lip, self.cross, self.B
        R = 7.6                                   # 25 ft curb return radius
        far = 300.0
        rects("art_asphalt", [(-A, A, self.y0, self.y1)], 0.0, M["asphalt"], c, uv=True)
        ext = 0.0
        if yc is not None:
            rects("cross_asphalt", [(-far, -A, yc - B, yc + B), (A, far, yc - B, yc + B)], 0.0, M["asphalt"], c,
                  uv=True)
            if self.rtl:
                ext = LANE
                y_t0, y_t1 = yc - B - 75.0, yc - B - 45.0     # 30 m taper, 45 m full width storage
                poly("rtl_asphalt", [(A - 0.01, y_t0), (A + ext, y_t1), (A + ext, yc - B), (A - 0.01, yc - B)], 0.0,
                     M["asphalt"], c)
        # curb lines per side (and per quadrant at the crossing), each with gutter, kerb, sidewalk, block
        for sx in (-1, 1):
            if yc is None:
                lines = [[(sx * A, self.y0), (sx * A, self.y1)]]
            else:
                e = ext if (sx > 0 and self.rtl) else 0.0
                south = [(sx * A, self.y0)]
                if e:
                    south += [(sx * A, yc - B - 75.0), (sx * (A + e), yc - B - 45.0)]
                    south += [(sx * (A + e), yc - B - R)]
                else:
                    south += [(sx * A, yc - B - R)]
                ax = A + e
                arc = fillet(sx * (ax + R), yc - B - R, R, math.pi if sx > 0 else 0.0,
                             math.pi / 2 if sx > 0 else math.pi / 2, 8)
                south += arc[1:] + [(sx * far, yc - B)]
                north = [(sx * far, yc + B)] + fillet(sx * (A + R), yc + B + R, R,
                                                       -math.pi / 2, -math.pi if sx > 0 else 0.0, 8) + \
                    [(sx * A, self.y1)]
                lines = [south, north]
            for k, P in enumerate(lines):
                self.curb(f"curb_{sx}_{k}", P, -sx, sx * far)
        # markings
        segs = [(self.y0, self.y1)] if yc is None else [(self.y0, yc - B - STOP_TO_XW - XW_W - 0.5),
                                                         (yc + B + XW_W + 0.5, self.y1)]
        for i, (a, b) in enumerate(segs):
            double_yellow(f"cl_{i}", 0.0, a, b, c)
            for sx in (-1, 1):
                for k in range(1, self.lanes):
                    broken(f"ll_{i}_{sx}_{k}", sx * k * LANE, a, b, c, phase=(i * 3.1) % (DASH + GAP))
                solid(f"edge_{i}_{sx}", sx * self.edge, a, b, c)
        if yc is not None:
            self.crossing_marks()

    def curb(self, name, P, sign, far_x):
        """Gutter (2 ft concrete), 6 in kerb face and top, 6 ft sidewalk and the grass block along polyline P;
        sign: +1 when the block lies to the left of P's direction, -1 to the right."""
        M, c = mats(), self.c
        band(name + "_gutter", P, -sign * GUTTER, 0.0, 0.004, M["concrete"], c)
        band(name + "_face", P, 0.0, sign * 0.002, 0.0, M["concrete"], c, z1=KERB_H)
        band(name + "_top", P, sign * 0.002, sign * 0.15, KERB_H, M["concrete"], c)
        band(name + "_walk", P, sign * 2.2, sign * (2.2 + WALK), KERB_H + 0.003, M["concrete"], c)
        G = offset(P, sign * 0.15)
        for q in ((far_x, G[-1][1]), (far_x, G[0][1])):
            if abs(q[0] - G[-1][0]) > 0.5 or abs(q[1] - G[-1][1]) > 0.5:
                G.append(q)
        poly(name + "_block", G, KERB_H - 0.002, M["grass"], c)

    def crossing_marks(self):
        c, A, yc, B = self.c, self.lip, self.cross, self.B
        ex = LANE if self.rtl else 0.0
        # crosswalks on the four legs, stop bars on the four approaches
        ladder("xw_s", -A, A + ex, yc - B - XW_W, yc - B, c, along="x")
        ladder("xw_n", -A, A, yc + B, yc + B + XW_W, c, along="x")
        ladder("xw_w", -A - XW_W, -A, yc - B, yc + B, c, along="y")
        ladder("xw_e", A, A + XW_W, yc - B, yc + B, c, along="y")
        self.stop_nb = yc - B - XW_W - STOP_TO_XW            # near edge of the northbound stop bar
        stop_bar("stop_nb", 0.3, self.edge + ex, self.stop_nb, c, 1)
        stop_bar("stop_sb", -self.edge, -0.3, yc + B + XW_W + STOP_TO_XW, c, -1)
        xs = A + XW_W + STOP_TO_XW              # cross street stop bars (eastbound south half, westbound north half)
        tag(rects("stop_eb", [(-xs - STOP_BAR, -xs, yc - LANE, yc - 0.3)], 0.007, mats()["white"], c),
            us_line="stop_bar", us_w=STOP_BAR)
        tag(rects("stop_wb", [(xs, xs + STOP_BAR, yc + 0.3, yc + LANE)], 0.007, mats()["white"], c),
            us_line="stop_bar", us_w=STOP_BAR)
        self.stop_wb = xs
        if self.rtl:
            y_s = yc - B - 45.0
            solid("rtl_line", self.edge, y_s, self.stop_nb - STOP_BAR, c, w=8 * IN)
            solid("rtl_edge", self.edge + LANE, y_s, self.stop_nb - STOP_BAR, c)
            turn_arrow("rtl_arrow", self.edge + LANE / 2 - 0.2, self.stop_nb - 12.0, c)
        # cross street centre line and edge lines outside the crosswalks
        for sx in (-1, 1):
            x_a, x_b = (A + XW_W + 0.4, 300.0) if sx > 0 else (-300.0, -A - XW_W - 0.4)
            o = rects(f"cross_cl_{sx}", [(x_a, x_b, yc - (DY_SPACE + LINE) / 2 - LINE / 2, yc - (DY_SPACE + LINE) / 2
                                          + LINE / 2), (x_a, x_b, yc + (DY_SPACE + LINE) / 2 - LINE / 2,
                                                        yc + (DY_SPACE + LINE) / 2 + LINE / 2)],
                      0.006, mats()["yellow"], c)
            tag(o, us_line="double_yellow_x")


# ------------------------------------------------------------------ freeway
class Freeway:
    """Divided freeway, three 12 ft lanes each way, 10 ft paved right shoulder, 4 ft left shoulder, yellow left edge
    line, white right edge line, white broken lane lines, concrete median barrier (32 in), grass, sound walls."""

    def __init__(self, c, y0=-900.0, y1=900.0, lanes=3, wall=34.0):
        self.c, self.y0, self.y1, self.lanes = c, y0, y1, lanes
        self.x_in = 0.3 + SHOULDER_L                 # yellow left edge line
        self.x_out = self.x_in + lanes * LANE        # white right edge line
        self.build(wall)

    def lane_x(self, k, nb=True):
        """Lane k counted from the right (0 = right lane)."""
        x = self.x_out - (k + 0.5) * LANE
        return x if nb else -x

    def build(self, wall):
        M, c = mats(), self.c
        for sx in (-1, 1):
            a, b = sorted((sx * 0.25, sx * (self.x_out + SHOULDER)))
            rects(f"fw_asphalt_{sx}", [(a, b, self.y0, self.y1)], 0.0, M["asphalt"], c, uv=True)
            solid(f"fw_left_{sx}", sx * self.x_in, self.y0, self.y1, c, "yellow")
            solid(f"fw_right_{sx}", sx * self.x_out, self.y0, self.y1, c, "white")
            for k in range(1, self.lanes):
                broken(f"fw_ll_{sx}_{k}", sx * (self.x_in + k * LANE), self.y0, self.y1, c, phase=k * 4.0)
            # wall behind palms and grass
            box(f"wall_{sx}", c, (sx * wall, (self.y0 + self.y1) / 2, 2.25), (0.3, self.y1 - self.y0, 4.5),
                mat("us_wall", (0.62, 0.58, 0.5), 0.9))
            for y in range(int(self.y0), int(self.y1), 6):
                box(f"wall_post_{sx}", c, (sx * (wall - 0.2), y, 2.3), (0.15, 0.4, 4.6),
                    mat("us_wall_post", (0.55, 0.51, 0.44), 0.9))
        # median barrier: constant-slope profile, 32 in high
        prof = [(-0.3, 0.0), (-0.2, 0.25), (-0.09, 0.81), (0.09, 0.81), (0.2, 0.25), (0.3, 0.0)]
        vs, fs = [], []
        for y in (self.y0, self.y1):
            vs += [(x, y, z) for x, z in prof]
        n = len(prof)
        fs = [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)]
        o = W.mesh_obj("median_barrier", vs, fs, mat("us_barrier", (0.6, 0.59, 0.56), 0.85), c)
        if o.data.polygons[0].normal.z < 0:
            o.data.flip_normals()
        rects("fw_grass", [(-400, 400, self.y0 - 400, self.y1 + 400)], -0.03, M["grass"], c)


def toll_gantry(c, y, x0, x1, lanes_x, flash=None, name="toll"):
    """Open-road toll gantry across one carriageway: two columns, a box truss, one camera box per lane facing the
    oncoming traffic plus one facing away, a transponder reader panel per lane and a roadside cabinet. No booth, no
    barrier, no sign, no operator name. flash: [(t0, t1)] seconds when the cameras' white strobes fire."""
    steel = mat("us_galv", (0.62, 0.64, 0.66), 0.35, metal=0.9)
    dark = mat("us_cam_body", (0.16, 0.17, 0.18), 0.4, metal=0.3)
    lens = mat("us_cam_lens", (0.01, 0.01, 0.015), 0.05)
    reader = mat("us_reader", (0.8, 0.8, 0.78), 0.5)
    strobe = W.principled("us_strobe", (0.9, 0.9, 0.95), 0.2, emit=(1.0, 0.98, 0.95), estr=0.0)
    g = bpy.data.objects.new(name, None)
    c.objects.link(g)
    top = GANTRY_CLEAR + 1.4
    for x in (x0, x1):
        box(f"{name}_col", c, (x, y, top / 2), (0.45, 0.45, top), steel, bev=0.02, parent=g)
        box(f"{name}_base", c, (x, y, 0.3), (0.9, 0.9, 0.6), mat("us_barrier", (0.6, 0.59, 0.56), 0.85), parent=g)
    for z in (GANTRY_CLEAR + 0.1, top - 0.1):
        for dy in (-0.45, 0.45):
            o = cyl(f"{name}_chord", c, ((x0 + x1) / 2, y + dy, z), 0.09, x1 - x0, steel, 12, rot=(0, math.pi / 2, 0))
            o.parent = g
    n = int((x1 - x0) / 1.2)
    for k in range(n):
        xa = x0 + (k + 0.5) * (x1 - x0) / n
        for dy in (-0.45, 0.45):
            o = cyl(f"{name}_diag", c, (xa, y + dy, (GANTRY_CLEAR + top) / 2), 0.035, 1.6, steel, 8,
                    rot=(0, math.radians(38 if k % 2 else -38), 0))
            o.parent = g
    for x in lanes_x:
        box(f"{name}_cam", c, (x, y - 0.75, GANTRY_CLEAR - 0.05), (0.32, 0.55, 0.3), dark, bev=0.03, parent=g)
        o = cyl(f"{name}_lens", c, (x, y - 1.03, GANTRY_CLEAR - 0.05), 0.08, 0.04, lens, 16, rot=(math.pi / 2, 0, 0))
        o.parent = g
        box(f"{name}_strobe", c, (x + 0.28, y - 0.85, GANTRY_CLEAR - 0.05), (0.18, 0.08, 0.12), strobe, parent=g)
        box(f"{name}_cam_rear", c, (x - 0.6, y + 0.75, GANTRY_CLEAR - 0.05), (0.32, 0.55, 0.3), dark, bev=0.03, parent=g)
        box(f"{name}_reader", c, (x - 0.6, y - 0.62, GANTRY_CLEAR + 0.05), (0.55, 0.06, 0.4), reader, bev=0.01,
            parent=g)
    box(f"{name}_cabinet", c, (x1 + 2.5, y + 4.0, 0.9), (1.0, 0.7, 1.8), mat("us_cabinet", (0.7, 0.71, 0.7), 0.6),
        bev=0.02)
    if flash:
        inp = strobe.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
        pairs = [(1, 0.0)]
        for t0, t1 in flash:
            pairs += [(int(t0 * 30) + 1, 0.0), (int(t0 * 30) + 2, 60.0), (int(t1 * 30) + 1, 0.0)]
        for f, v in pairs:
            inp.default_value = v
            inp.keyframe_insert("default_value", frame=f)
        for fc in stage.fcurves(strobe.node_tree):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
    return g


# ------------------------------------------------------------------ signals (span wire)
class Signal:
    """One signal phase: shared emissive lens materials, keyed per frame. states: 'R', 'Y', 'G'."""

    def __init__(self, name):
        self.name = name
        self.m = {k: W.principled(f"sig_{name}_{k}", col, 0.2, emit=em, estr=0.0) for k, col, em in (
            ("R", (0.25, 0.01, 0.01), (1.0, 0.05, 0.02)), ("Y", (0.3, 0.16, 0.0), (1.0, 0.55, 0.02)),
            ("G", (0.0, 0.18, 0.12), (0.1, 1.0, 0.6)))}

    def key(self, t, state):
        for k, m in self.m.items():
            inp = m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
            inp.default_value = 14.0 if k == state else 0.0
            inp.keyframe_insert("default_value", frame=int(round(t * 30)) + 1)

    def done(self):
        for m in self.m.values():
            for fc in stage.fcurves(m.node_tree):
                for kp in fc.keyframe_points:
                    kp.interpolation = "CONSTANT"


def signal_head(c, sig, loc, rz, name="sig_head"):
    """Three-section 12 in vehicle signal head, black housing, black backplate with a 3 in yellow retroreflective
    border (FDOT), hung from the span wire; faces -Y rotated by rz (rz = 0: seen by traffic driving towards +y).
    loc is the hanger point on the wire; the housing bottom sits at SIG_BOTTOM."""
    blk = mat("sig_black", (0.02, 0.02, 0.02), 0.5)
    yel = mat("sig_border", (0.9, 0.62, 0.02), 0.35, emit=(0.9, 0.62, 0.02), estr=0.15)
    g = bpy.data.objects.new(name, None)
    c.objects.link(g)
    g.location = (loc[0], loc[1], 0.0)
    g.rotation_euler = (0, 0, rz)
    h = 3 * 0.36 + 0.06
    zc = SIG_BOTTOM + h / 2
    box(name + "_housing", c, (0, 0, zc), (0.38, 0.3, h), blk, bev=0.02, parent=g)
    box(name + "_border", c, (0, 0.17, zc), (0.68, 0.015, h + 0.3), yel, parent=g)
    box(name + "_plate", c, (0, 0.165, zc), (0.53, 0.02, h + 0.15), blk, parent=g)
    for k, s in enumerate(("R", "Y", "G")):
        z = SIG_BOTTOM + 0.03 + 0.36 * (2 - k) + 0.18
        o = cyl(name + "_lens_" + s, c, (0, -0.16, z), SIG_LENS / 2, 0.02, sig.m[s], 20, rot=(math.pi / 2, 0, 0))
        o.parent = g
        box(name + "_visor", c, (0, -0.28, z + 0.13), (0.36, 0.24, 0.025), blk, parent=g)
    top = loc[2]
    cyl(name + "_hanger", c, (0, 0, (SIG_BOTTOM + h + top) / 2), 0.02, top - SIG_BOTTOM - h, blk, 6).parent = g
    g["us_signal_bottom"] = SIG_BOTTOM
    return g


def span_wire(c, a, b, z=6.9, sag=0.25, name="span"):
    """Steel pole at each end and a sagging messenger wire between (a, b) = (x, y) feet of the poles."""
    pole_m = mat("us_pole", (0.5, 0.5, 0.48), 0.5, metal=0.6)
    for p in (a, b):
        cyl(name + "_pole", c, (p[0], p[1], 4.2), 0.17, 8.4, pole_m, 16, r_top=0.12)
    pts = []
    for k in range(17):
        u = k / 16
        pts.append((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, z + 0.6 - sag * 4 * u * (1 - u)))
    for p, q in zip(pts, pts[1:]):
        d = Vector(q) - Vector(p)
        o = cyl(name + "_wire", c, tuple((Vector(p) + Vector(q)) / 2), 0.012, d.length, pole_m, 6)
        o.rotation_euler = d.to_track_quat("Z", "Y").to_euler()

    def at(x=None, y=None):
        """Point on the wire above the given x (or y)."""
        u = (x - a[0]) / (b[0] - a[0]) if x is not None else (y - a[1]) / (b[1] - a[1])
        return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, z + 0.6 - sag * 4 * u * (1 - u))
    return at


# ------------------------------------------------------------------ roadside: palms, buildings, lights, people
def palm_lib(lib, n=3, seed=3):
    rnd = random.Random(seed)
    trunk_m = W.noisy("palm_trunk", (0.25, 0.21, 0.16), (0.36, 0.31, 0.24), 3.0, rough=0.9, bump=0.4)
    leaf_m = W.noisy("palm_leaf", (0.07, 0.16, 0.04), (0.16, 0.26, 0.07), 1.5, rough=0.7)
    leaf_m.use_backface_culling = False
    out = []
    for i in range(n):
        cc = bpy.data.collections.new(f"palm_{i}")
        lib.children.link(cc)
        h = rnd.uniform(7.0, 10.5)
        lean = rnd.uniform(-0.25, 0.25)
        segs = 8
        vs, fs = [], []
        for k in range(segs + 1):
            z = h * k / segs
            r = 0.2 - 0.04 * k / segs
            cx = lean * (k / segs) ** 2
            for j in range(10):
                a = 2 * math.pi * j / 10
                vs.append((cx + r * math.cos(a), r * math.sin(a), z))
        for k in range(segs):
            for j in range(10):
                a, b = k * 10 + j, k * 10 + (j + 1) % 10
                fs.append((a, b, b + 10, a + 10))
        o = W.mesh_obj(f"palm_trunk_{i}", vs, fs, trunk_m, cc, smooth=True)
        top = Vector((lean, 0, h))
        # sabal crown: 22 fan fronds on stalks, arching out and down
        vs, fs = [], []
        for f in range(22):
            az = 2 * math.pi * f / 22 + rnd.uniform(-0.1, 0.1)
            el = math.radians(rnd.uniform(-35, 55))
            d = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
            side = Vector((-math.sin(az), math.cos(az), 0))
            L = rnd.uniform(1.8, 2.6)
            base = len(vs)
            for k in range(6):
                u = k / 5
                p = top + d * (L * u) + Vector((0, 0, -0.9 * u * u))
                w = 0.08 + 0.75 * math.sin(math.pi * min(1.0, u * 1.15)) if k else 0.06
                vs += [tuple(p - side * w), tuple(p + Vector((0, 0, 0.06)) ), tuple(p + side * w)]
            for k in range(5):
                a = base + 3 * k
                fs += [(a, a + 3, a + 4, a + 1), (a + 1, a + 4, a + 5, a + 2)]
        W.mesh_obj(f"palm_crown_{i}", vs, fs, leaf_m, cc, smooth=True)
        out.append(cc)
    return out


def instance(cc, c, loc, rz=0.0, s=1.0, name=None):
    e = bpy.data.objects.new(name or ("inst_" + cc.name), None)
    e.instance_type = "COLLECTION"
    e.instance_collection = cc
    e.location, e.rotation_euler, e.scale = loc, (0, 0, rz), (s, s, s)
    c.objects.link(e)
    return e


def strip_mall(c, x_face, y0, y1, side=1, seed=1, depth=14.0, z0=KERB_H):
    """A row of plain one-storey stucco shops facing the road (side +1: east of the road, facing -x). Glass shop
    fronts, plain awnings, a parapet; no names, no logos, no signs."""
    rnd = random.Random(seed)
    stucco = [mat(f"stucco_{k}", col, 0.9) for k, col in enumerate(
        ((0.86, 0.8, 0.68), (0.9, 0.86, 0.78), (0.82, 0.74, 0.62), (0.88, 0.82, 0.74)))]
    awn = [mat(f"awning_{k}", col, 0.7) for k, col in enumerate(
        ((0.1, 0.32, 0.36), (0.55, 0.12, 0.08), (0.12, 0.2, 0.38), (0.25, 0.3, 0.12)))]
    glass = mat("shop_glass", (0.02, 0.03, 0.035), 0.06)
    frame_m = mat("shop_frame", (0.75, 0.75, 0.74), 0.4, metal=0.6)
    y = y0
    while y < y1 - 8:
        w = rnd.uniform(14, 32)
        h = rnd.uniform(5.2, 6.8)
        xm = x_face + side * depth / 2
        box("mall", c, (xm, y + w / 2, z0 + h / 2), (depth, w - 0.3, h), rnd.choice(stucco))
        box("mall_parapet", c, (x_face + side * 0.2, y + w / 2, z0 + h + 0.35), (0.4, w - 0.3, 0.7),
            rnd.choice(stucco))
        box("mall_glass", c, (x_face - side * 0.02, y + w / 2, z0 + 1.55), (0.05, w - 2.0, 2.9), glass)
        for k in range(int(w / 3.5) + 1):
            box("mall_mullion", c, (x_face - side * 0.05, y + 1.0 + k * (w - 2.0) / max(1, int(w / 3.5)),
                                    z0 + 1.55), (0.06, 0.08, 2.9), frame_m)
        box("mall_awning", c, (x_face - side * 0.9, y + w / 2, z0 + 3.4), (1.8, w - 1.2, 0.14), rnd.choice(awn))
        y += w


def parking_lot(c, x0, x1, y0, y1, z=KERB_H + 0.004, cars=(), seed=2):
    """Asphalt lot with white stall lines (9 ft x 18 ft stalls, 4 in lines) and parked cars (static instances)."""
    rnd = random.Random(seed)
    rects("lot", [(x0, x1, y0, y1)], z, mats()["asphalt_lot"], c, uv=True)
    rs = []
    sw, sl = 9 * FT, 18 * FT
    xs = [x0 + 1.0, x1 - 1.0 - sl]
    for xa in xs:
        y = y0 + 1.0
        while y + sw < y1 - 1.0:
            rs.append((xa, xa + sl, y - 2 * IN, y + 2 * IN))
            if cars and rnd.random() < 0.55:
                instance(rnd.choice(cars), c, (xa + sl / 2, y + sw / 2, z), rz=(math.pi / 2 if xa == xs[0] else
                                                                                 -math.pi / 2) +
                         rnd.uniform(-0.04, 0.04), name="parked")
            y += sw
    rects("lot_lines", rs, z + 0.003, mats()["white"], c)


def street_light(c, x, y, side=1, h=9.5):
    """Cobra-head street light on a tapered pole, arm over the road (side +1: pole east of the road)."""
    m = mat("us_pole", (0.5, 0.5, 0.48), 0.5, metal=0.6)
    cyl("light_pole", c, (x, y, h / 2), 0.13, h, m, 12, r_top=0.08)
    o = cyl("light_arm", c, (x - side * 1.4, y, h - 0.1), 0.05, 2.8, m, 8, rot=(0, math.pi / 2, 0))
    box("light_head", c, (x - side * 2.9, y, h - 0.2), (0.75, 0.32, 0.16), mat("us_light_head", (0.6, 0.6, 0.6),
                                                                              0.4), bev=0.05)
    return o


# ------------------------------------------------------------------ hinterland (behind the strip malls)
HOUSE_WALLS = ((0.86, 0.80, 0.66), (0.92, 0.89, 0.80), (0.80, 0.70, 0.58), (0.78, 0.80, 0.74), (0.74, 0.79, 0.82),
               (0.90, 0.78, 0.68), (0.93, 0.92, 0.88))
HOUSE_ROOFS = ((0.42, 0.19, 0.11), (0.30, 0.30, 0.31), (0.36, 0.30, 0.24), (0.52, 0.30, 0.18), (0.62, 0.62, 0.6))


def hip_roof(name, w, d, z, rh, ov, m, c):
    """Hip roof over a w x d footprint centred on the origin, eaves at z, overhang ov, ridge height rh."""
    a, b = w / 2 + ov, d / 2 + ov
    if a >= b:
        r = a - b
        vs = [(-a, -b, z), (a, -b, z), (a, b, z), (-a, b, z), (-r, 0, z + rh), (r, 0, z + rh)]
        fs = [(0, 1, 5, 4), (2, 3, 4, 5), (1, 2, 5), (3, 0, 4), (0, 3, 2, 1)]
    else:
        r = b - a
        vs = [(-a, -b, z), (a, -b, z), (a, b, z), (-a, b, z), (0, -r, z + rh), (0, r, z + rh)]
        fs = [(0, 1, 4), (1, 2, 5, 4), (2, 3, 5), (3, 0, 4, 5), (0, 3, 2, 1)]
    return W.mesh_obj(name, vs, fs, m, c)


def house_lib(lib, n=10, seed=11):
    """Single-storey Florida ranch houses (stucco block walls, hip roofs in barrel tile, shingle or white metal),
    garage door, windows, front door and the concrete driveway, as instancable collections. No names, no numbers.
    Local frame: the street edge is the line y = 0, the lot runs to +y and the house faces -y."""
    if "houses" in _m:
        return _m["houses"]
    rnd = random.Random(seed)
    glass = mat("house_glass", (0.025, 0.03, 0.035), 0.08)
    trim = mat("house_trim", (0.88, 0.88, 0.86), 0.6)
    conc = mats()["concrete"]
    out = []
    for i in range(n):
        cc = bpy.data.collections.new(f"house_{i}")
        lib.children.link(cc)
        w, d = rnd.uniform(13.0, 19.0), rnd.uniform(10.0, 13.5)
        sb, h = rnd.uniform(7.5, 9.5), rnd.uniform(2.9, 3.3)
        wall = mat(f"house_wall_{i % 7}", HOUSE_WALLS[i % 7], 0.9)
        roof = mat(f"house_roof_{i % 5}", HOUSE_ROOFS[(i * 3) % 5], 0.75)
        yc = sb + d / 2
        box("house_body", cc, (0, yc, h / 2), (w, d, h), wall)
        hip_roof("house_roof", w, d, h, rnd.uniform(1.6, 2.4), 0.55, roof, cc).location = (0, yc, 0)
        gx = rnd.choice((-1, 1)) * (w / 2 - 3.3)
        box("house_garage", cc, (gx, sb - 0.03, 1.15), (4.9, 0.06, 2.3), trim)
        box("house_drive", cc, (gx, sb / 2, 0.012), (5.6, sb, 0.024), conc)
        box("house_walk", cc, (-gx * 0.3, sb / 2, 0.01), (1.2, sb, 0.02), conc)
        xs = [x for x in (-w / 2 + 1.6 + k * 2.6 for k in range(int((w - 2.4) / 2.6))) if abs(x - gx) > 3.4]
        for k, x in enumerate(xs):
            if k == len(xs) // 2:
                box("house_door", cc, (x, sb - 0.03, 1.05), (1.0, 0.06, 2.1), trim)
            else:
                box("house_win", cc, (x, sb - 0.03, 1.55), (1.3, 0.06, 1.3), glass)
        for x in (-w / 4, w / 4):
            box("house_win_back", cc, (x, sb + d + 0.03, 1.4), (2.4, 0.06, 2.0), glass)
        cc["w"], cc["sb"], cc["d"], cc["gx"] = w, sb, d, gx
        out.append(cc)
    _m["houses"] = out
    return out


def tree_groups(lib):
    """Florida trees for scattering: live oaks (the flora kit's broadleaf blobs, scaled up), slash pines (its
    conifers), shrubs and sabal palms, each a collection whose children flora.scatter picks from."""
    if "trees" in _m:
        return _m["trees"]
    import flora
    g = flora.library(lib)
    pg = bpy.data.collections.new("lib_palms_scatter")
    lib.children.link(pg)
    for cc in palm_lib(lib, n=3, seed=41):
        pg.children.link(cc)
    g["palm"] = pg
    _m["trees"] = g
    return g


def low_building(c, x, y, w, d, h, rnd, name="bldg"):
    """Plain flat-roofed one-storey building (warehouse, office, church hall): tilt-up concrete or stucco walls,
    parapet, roof membrane, a few roof units, dark doors. No names, no logos."""
    wall = mat(f"lowb_wall_{rnd.randrange(4)}", rnd.choice(((0.78, 0.76, 0.72), (0.86, 0.82, 0.74),
                                                             (0.7, 0.72, 0.74), (0.82, 0.74, 0.64))), 0.9)
    box(name, c, (x, y, KERB_H + h / 2), (w, d, h), wall)
    box(name + "_roof", c, (x, y, KERB_H + h + 0.01), (w - 0.8, d - 0.8, 0.04),
        mat("lowb_membrane", (0.6, 0.6, 0.58), 0.8))
    for k in range(rnd.randint(1, 4)):
        box(name + "_unit", c, (x + rnd.uniform(-w / 3, w / 3), y + rnd.uniform(-d / 3, d / 3), KERB_H + h + 0.6),
            (2.2, 1.6, 1.2), mat("lowb_unit", (0.72, 0.73, 0.72), 0.5, metal=0.3))
    dm = mat("lowb_door", (0.18, 0.19, 0.2), 0.6)
    for k in range(int(d / 9)):
        box(name + "_door", c, (x - w / 2 - 0.03, y - d / 2 + 5 + k * 9, KERB_H + 2.1), (0.06, 3.6, 4.2), dm)


def hinterland(c, lib, x_back, free, cross, side, seed=5, mods=6, x_end=3200.0):
    """The land behind one row of strip malls, so no camera ever sees a bare plane to the horizon: a service alley,
    a buffer row of oaks, a grid of ranch-house streets (mods blocks of two lots and a street, 80 m each), a band of
    low flat-roofed buildings, then woods and scattered buildings out to x_end on the lawn ground. side +1: east of the
    road. x_back: |x| of the malls' back wall. free: [(ya, yb)] y-intervals along the road (outside any crossing).
    cross: world y of the local streets that come through the gaps between the malls. The scene's haze
    (Ep.run haze) fades it into the sky."""
    import flora
    rnd = random.Random(seed * 7 + (side > 0))
    M = mats()
    sx = side
    houses, trees = house_lib(lib), tree_groups(lib)
    z = KERB_H + 0.004
    ya, yb = min(a for a, _ in free), max(b for _, b in free)

    def R(u0, u1, y0, y1):
        xa, xb = sorted((sx * u0, sx * u1))
        return (xa, xb, y0, y1)

    pts = {"decid": [], "conif": [], "palm": [], "bush": []}
    # ground out to the horizon (the arterial's own grass blocks end 300 m out) and beyond both road ends
    rects("far_ground", [R(300.0, x_end, ya - 3000.0, yb + 3000.0)], KERB_H - 0.004, M["grass"], c)
    rects("far_ground_ends", [R(0.0, 300.0, yb, yb + 3000.0), R(0.0, 300.0, ya - 3000.0, ya)], -0.02, M["grass"], c)
    u0 = x_back + 14.0
    u_res = u0 + 80.0 * mods
    for a, b in free:
        rects("alley", [R(x_back, x_back + 7.0, a, b)], z, M["asphalt_lot"], c, uv=True)
        y = a + rnd.uniform(2, 8)
        while y < b:
            pts["decid"].append((sx * (x_back + rnd.uniform(9.0, 12.5)), y, KERB_H))
            y += rnd.uniform(7, 13)
        for k in range(mods):
            rects("res_street", [R(u0 + 80 * k + 36, u0 + 80 * k + 44, a - 4, b + 4)], z, M["asphalt"], c, uv=True)
    for ys in cross:
        rects("res_cross", [R(x_back, u_res, ys - 4.0, ys + 4.0)], z + 0.002, M["asphalt"], c, uv=True)

    def world(ox, oy, rz, lx, ly):
        return (ox + lx * math.cos(rz) - ly * math.sin(rz), oy + lx * math.sin(rz) + ly * math.cos(rz), KERB_H)

    for k in range(mods):
        um = u0 + 80 * k
        for u_edge, rz in ((um + 36, sx * math.pi / 2), (um + 44, -sx * math.pi / 2)):
            for a, b in free:
                yl = a + 12.0
                while yl < b - 12.0:
                    if any(abs(yl - ys) < 18.0 for ys in cross) or rnd.random() < 0.06:
                        yl += 24.0
                        continue
                    hc = rnd.choice(houses)
                    ox = sx * u_edge
                    instance(hc, c, (ox, yl, KERB_H), rz, name="house")
                    w, sb, d = hc["w"], hc["sb"], hc["d"]
                    if rnd.random() < 0.85:
                        pts["decid"].append(world(ox, yl, rz, rnd.uniform(-9, 9), rnd.uniform(sb + d + 3.5, 34.5)))
                    if rnd.random() < 0.45:
                        pts["palm" if rnd.random() < 0.5 else "decid"].append(
                            world(ox, yl, rz, rnd.choice((-1, 1)) * rnd.uniform(w / 2 - 1, 10.5), rnd.uniform(2, 5)))
                    for _ in range(rnd.randint(1, 3)):
                        pts["bush"].append(world(ox, yl, rz, rnd.uniform(-w / 2 + 1, w / 2 - 4), sb - 1.2))
                    yl += 24.0
    # band of low flat-roofed buildings behind the houses, then woods with the odd building, out to the haze
    y = ya - 200.0
    while y < yb + 200.0:
        w, d = rnd.uniform(25, 60), rnd.uniform(30, 90)
        low_building(c, sx * (u_res + 30 + w / 2 + rnd.uniform(0, 60)), y + d / 2, w, d, rnd.uniform(5.5, 8.5), rnd)
        y += d + rnd.uniform(15, 60)
    for _ in range(int((x_end - u_res) / 25)):
        cu, cy = rnd.uniform(u_res + 200, x_end), rnd.uniform(ya - 2500, yb + 2500)
        if rnd.random() < 0.18:
            w, d = rnd.uniform(25, 70), rnd.uniform(25, 70)
            low_building(c, sx * cu, cy, w, d, rnd.uniform(5, 9), rnd, name="far_bldg")
            continue
        kind = "conif" if rnd.random() < 0.4 else "decid"
        rr = rnd.uniform(25, 70)
        for _ in range(rnd.randint(10, 26)):
            a_, r_ = rnd.uniform(0, 2 * math.pi), rr * math.sqrt(rnd.random())
            pts[kind].append((sx * (cu + r_ * math.cos(a_)), cy + r_ * math.sin(a_), KERB_H))
    for kind, (s0, s1) in (("decid", (1.15, 1.7)), ("conif", (1.4, 2.2)), ("palm", (0.85, 1.15)),
                           ("bush", (0.5, 0.8))):
        if pts[kind]:
            flora.scatter(f"hint_{kind}_{'e' if sx > 0 else 'w'}", pts[kind], trees[kind], c, s0, s1, seed=seed)
    return u_res


def person(c, loc, rz=0.0, shirt=(0.1, 0.12, 0.2), legs=(0.08, 0.09, 0.12), hat=None, name="person"):
    """Stylised adult figure (1.78 m), faces -Y rotated by rz. Returns the root empty (arms are children
    'name_arm_r' and 'name_arm_l' with their pivot at the shoulder, so a scene can raise one)."""
    g = bpy.data.objects.new(name, None)
    c.objects.link(g)
    g.location, g.rotation_euler = loc, (0, 0, rz)
    skin = mat("us_skin", (0.55, 0.36, 0.25), 0.6)
    sm, lm = mat(name + "_shirt", shirt, 0.8), mat(name + "_legs", legs, 0.8)
    for sx in (-1, 1):
        cyl(name + "_leg", c, (sx * 0.1, 0, 0.45), 0.075, 0.9, lm, 10).parent = g
        box(name + "_shoe", c, (sx * 0.1, -0.05, 0.04), (0.11, 0.26, 0.08), mat("us_shoe", (0.02, 0.02, 0.02), 0.5),
            parent=g)
    box(name + "_torso", c, (0, 0, 1.18), (0.42, 0.24, 0.62), sm, bev=0.07, parent=g)
    for sx, nm in ((1, "_arm_r"), (-1, "_arm_l")):
        p = bpy.data.objects.new(name + nm, None)
        c.objects.link(p)
        p.parent = g
        p.location = (sx * 0.27, 0, 1.44)
        cyl(name + nm + "_m", c, (0, 0, -0.32), 0.055, 0.62, sm, 8).parent = p
    h = cyl(name + "_head", c, (0, 0, 1.64), 0.11, 0.24, skin, 14)
    h.parent = g
    if hat:
        cyl(name + "_hat", c, (0, 0, 1.78), 0.13, 0.07, mat(name + "_hatm", hat, 0.6), 14).parent = g
        box(name + "_brim", c, (0, -0.1, 1.75), (0.22, 0.12, 0.02), mat(name + "_hatm", hat, 0.6), parent=g)
    return g


def sign(c, sid, loc, rz=0.0, width=0.76, bottom=2.1, name=None):
    """A MUTCD sign from the Commons library (signs/us.json) on a post. Missing file: nothing is placed (owner rule:
    a sign with no Commons file is left out of the picture)."""
    if SG is None:
        return None
    try:
        return SG.assembly([(sid, width)], c, loc, rz, bottom=bottom, set_="us", name=name or f"sign_{sid}")
    except (FileNotFoundError, RuntimeError) as ex:
        print("SIGN MISSING (left out):", sid, ex)
        return None


# ------------------------------------------------------------------ vehicles (blank plates, no badges)
def _us_finish(coll, kind):
    """Strip the German plates and the chrome badge from a kit car and give it one blank rear plate (Florida needs
    a rear plate only; the owner allows no invented Florida plate, so the plate stays blank)."""
    for o in list(coll.objects):
        if o.name.startswith(("plate_", "badge")) or o.name.split(".")[0] in ("plate_f", "plate_r"):
            bpy.data.objects.remove(o)
    g = next(o for o in coll.objects if o.type == "EMPTY" and o.parent is None)
    body = next(o for o in coll.objects if o.name.endswith("_body"))
    k = V.KINDS[kind]
    C = V.common()
    p = V.stick(coll, g, body, (0, -1.0, k["stations"][1][3] - 0.24), (0, 1, 0), (0.305, 0.012, 0.152), C["plate"],
                bevel=0.004, name="us_plate_blank")
    if p:
        p.location.y -= k["L"] / 2
        p["us_plate"] = "blank"
    return coll


def us_car(kind, color, name, lib, metal=0.45, police=False):
    """A car collection in lib (static use: instance it). police=True: generic US patrol sedan, black with white
    doors, red and blue light bar (dark until the track sets beacon), push bar, no words or marks."""
    coll = V.car(kind, color if not police else (0.015, 0.015, 0.018), name, "QX US 1", metal=metal, c=lib)
    _us_finish(coll, kind)
    if police:
        _police_us(coll, kind)
    return coll


def _police_us(coll, kind):
    k = V.KINDS[kind]
    L, Wh = k["L"], k["W"]
    g = next(o for o in coll.objects if o.type == "EMPTY" and o.parent is None)
    body = next(o for o in coll.objects if o.name.endswith("_body"))
    white = V.mat("us_police_white", (0.9, 0.9, 0.9), 0.3, coat=1.0)
    zbelt = k["stations"][len(k["stations"]) // 2][3]
    y0, y1 = k["axles"][0] + 0.5, k["axles"][1] - 0.55
    for sx in (-1, 1):
        for j in range(10):
            for zz in (0.55, 0.75):
                y = y0 + (y1 - y0) * (j + 0.5) / 10
                o = V.stick(coll, g, body, (sx * (Wh + 1.0), y, zz), (-sx, 0, 0), ((y1 - y0) / 10 + 0.01, 0.01, 0.22),
                            white, name="us_police_door", bevel=0.0, embed=0.004)
                if o:
                    o.location.y -= L / 2
    red = V.lamp("us_beacon_red", (0.6, 0.02, 0.02), 0.15, (1.0, 0.05, 0.03), 0.15, [("beacon_a", 18.0)])
    blue = V.lamp("us_beacon_blue", (0.03, 0.12, 0.7), 0.15, (0.05, 0.25, 1.0), 0.15, [("beacon_b", 18.0)])
    base = V.mat("police_bar_base", (0.2, 0.2, 0.22), 0.35)
    roof_z = max(s_[7] for s_ in k["stations"])
    ym = (k["axles"][0] + k["axles"][1]) / 2 - 0.35
    hit, loc, nrm, _i = body.ray_cast(Vector((0, ym, roof_z + 1.0)), Vector((0, 0, -1)))
    if hit:
        for nm, dx, sz, m_ in (("us_lightbar", 0.0, (1.25, 0.3, 0.05), base), ("us_bar_red", -0.33, (0.58, 0.26, 0.1),
                                                                             red),
                               ("us_bar_blue", 0.33, (0.58, 0.26, 0.1), blue)):
            o = box(nm, coll, (dx, loc.y - L / 2, loc.z + 0.04 + sz[2] / 2), sz, m_, bev=0.03, parent=g)
    box("us_pushbar", coll, (0, L / 2 + 0.08, 0.5), (1.1, 0.08, 0.35), V.mat("car_plastic", (0.03, 0.03, 0.032), 0.55),
        bev=0.02, parent=g)


def hero(coll, kind, traffic, name=None):
    """Instance of a car collection in traffic, rigged for jx.drive (wheels, steering, lamps, beacons)."""
    k = V.KINDS.get(kind, {"L": 10.7, "W": 1.22})
    e = bpy.data.objects.new((name or coll.name) + "_inst", None)
    e.instance_type = "COLLECTION"
    e.instance_collection = coll
    traffic.objects.link(e)
    car = dict(name=name or coll.name, kind=kind, obj=e, coll=coll, L=k["L"], W=k["W"], blinks=[])
    car["rig"] = motion.rig(e)
    return car


def school_bus(lib, name="school_bus"):
    """Generic Type C school bus (35 ft, 96 in wide): National School Bus Yellow body, black bumpers and rub rails,
    no words or names, alternating red (beacon_a left, beacon_b right) and amber warning lamps, a folding stop arm on
    the left side and a door on the right (both animated by the scene: objects bus_arm and bus_door, made by
    bus_parts()). Front +y, origin on the ground at the middle."""
    root = bpy.data.collections.new(name)
    lib.children.link(root)
    g = bpy.data.objects.new(name, None)
    root.objects.link(g)
    L, Wd = 10.7, 2.44
    yel = V.mat("bus_yellow", (0.98, 0.62, 0.0), 0.35, coat=0.6)
    blk = V.mat("bus_black", (0.02, 0.02, 0.02), 0.5)
    C = V.common()
    yb, yh = -L / 2, L / 2 - 1.7          # box body from the rear to the windscreen, hood beyond
    V._box(root, g, "bus_body", (0, (yb + yh) / 2, 1.85), (Wd, yh - yb, 2.1), yel, bev=0.14)
    V._box(root, g, "bus_skirt", (0, (yb + yh) / 2, 0.68), (Wd - 0.06, yh - yb - 0.1, 0.4), yel, bev=0.03)
    V._box(root, g, "bus_hood", (0, yh + 0.8, 1.05), (2.1, 1.7, 0.85), yel, bev=0.12)
    V._box(root, g, "bus_grille", (0, L / 2 + 0.02, 1.0), (1.0, 0.04, 0.6), blk, bev=0.02)
    V._box(root, g, "bus_bumper_f", (0, L / 2 + 0.05, 0.55), (2.3, 0.18, 0.28), blk, bev=0.03)
    V._box(root, g, "bus_bumper_r", (0, yb - 0.08, 0.6), (2.4, 0.18, 0.3), blk, bev=0.03)
    V._box(root, g, "bus_windscreen", (0, yh + 0.02, 2.25), (2.2, 0.05, 0.95), C["glass"], bev=0.02)
    V._box(root, g, "bus_rear_glass", (0, yb - 0.02, 2.35), (1.2, 0.05, 0.7), C["glass"], bev=0.02)
    for sx in (-1, 1):
        V._box(root, g, "bus_windows", (sx * (Wd / 2 + 0.005), (yb + yh) / 2 - 0.2, 2.25), (0.03, yh - yb - 1.4, 0.75),
               C["glass"])
        for k in range(12):
            V._box(root, g, "bus_pillar", (sx * (Wd / 2 + 0.012), yb + 0.55 + k * 0.76, 2.25), (0.03, 0.09, 0.78), yel)
        for z in (1.12, 1.45, 1.78):
            V._box(root, g, "bus_rail", (sx * (Wd / 2 + 0.02), (yb + yh) / 2, z), (0.03, yh - yb - 0.3, 0.07), blk)
    # warning lamps (FMVSS 108): a red pair outboard and an amber pair inboard, front and rear, at the top
    red_l = V.lamp("bus_red_a", (0.5, 0.02, 0.02), 0.15, (1.0, 0.04, 0.02), 0.2, [("beacon_a", 22.0)])
    red_r = V.lamp("bus_red_b", (0.5, 0.02, 0.02), 0.15, (1.0, 0.04, 0.02), 0.2, [("beacon_b", 22.0)])
    amber = W.principled("bus_amber", (0.5, 0.25, 0.0), 0.15, emit=(1.0, 0.5, 0.0), estr=0.0)
    for yf, ny in ((yh + 0.03, 1), (yb - 0.03, -1)):
        for sx in (-1, 1):
            for dx, m_ in ((0.88, red_l if sx < 0 else red_r), (0.55, amber)):
                o = cyl("bus_lamp", root, (sx * dx, yf, 2.75), 0.11, 0.06, m_, 16, rot=(math.pi / 2, 0, 0))
                o.parent = g
                V._box(root, g, "bus_lamp_hood", (sx * dx, yf + ny * 0.06, 2.88), (0.28, 0.12, 0.03), blk)
    tail = C["tail"]
    for sx in (-1, 1):
        V._box(root, g, "taillight", (sx * 0.95, yb - 0.04, 1.0), (0.22, 0.04, 0.22), tail)
        V._box(root, g, "headlight", (sx * 0.8, L / 2 - 0.02, 1.05), (0.26, 0.04, 0.18), C["head"])
        V._box(root, g, "mirror", (sx * 1.35, yh + 0.6, 2.0), (0.1, 0.25, 0.45), blk, bev=0.03)
    for ay in (yh + 0.3, yb + 2.4):
        for sx in (-1, 1):
            V.wheel(root, g, sx * 0.98, ay, 0.5, 0.32 if ay > 0 else 0.5, sx, style="steel")
    root["dl_lamps"] = [v for side in (-1, 1) for (y, z) in ((L / 2 - 0.05, 1.05), (yb - 0.06, 1.0))
                        for v in (side * 1.1, y, z, 0.06, 0.16, 0.1, float(side), 0.0)]
    root["dl_heads"] = [-0.8, L / 2, 1.05, 0.8, L / 2, 1.05]
    return root


def bus_parts(bus_car, c, sig):
    """Stop arm (left side, behind the driver) and entrance door (right front) as separate objects parented to the
    bus instance, so the scene can key them. Stop arm face: the Commons STOP sign R1-1 (unaltered) on both sides with
    two red lamps; with no Commons file the blade stays a plain red octagon. sig: emissive material for the arm
    lamps (keyed by the scene). Returns (arm_pivot, door)."""
    inst = bus_car["obj"]
    L = 10.7
    piv = bpy.data.objects.new("bus_arm", None)
    c.objects.link(piv)
    piv.parent = inst
    piv.location = (-1.25, L / 2 - 2.9, 1.75)
    face = None
    if SG is not None:
        try:
            face = SG.face("R1-1", c, 0.46, set_="us", name="bus_arm_face", back=False)
        except (FileNotFoundError, RuntimeError):
            face = None
    if face is not None:
        face.parent = piv
        face.location = (-0.32, 0.0, -0.23)
        back = SG.face("R1-1", c, 0.46, set_="us", name="bus_arm_face_b", back=False)
        back.parent = piv
        back.location = (-0.32, 0.0, -0.23)
        back.rotation_euler = (0, 0, math.pi)
    else:
        o = cyl("bus_arm_blade", c, (-0.32, 0, 0), 0.23, 0.015, mat("bus_arm_red", (0.6, 0.02, 0.02), 0.4), 8,
                rot=(0, math.pi / 2, math.pi / 8))
        o.parent = piv
    for dz in (0.2, -0.2):
        o = cyl("bus_arm_lamp", c, (-0.32, 0.0, dz), 0.035, 0.03, sig, 10, rot=(0, math.pi / 2, 0))
        o.parent = piv
    door = box("bus_door", c, (1.235, L / 2 - 2.35, 1.35), (0.04, 0.75, 1.9), mat("bus_door_glass", (0.03, 0.03, 0.035),
                                                                                0.1), parent=inst)
    return piv, door


# ------------------------------------------------------------------ scene shell
def new_scene(assets):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    W.setup(assets, None)
    _m.clear()
    if SG is not None:
        try:
            SG.setup(assets)
        except FileNotFoundError as ex:
            print("signs library missing:", ex)
    return W.coll("lib"), W.coll("env"), W.coll("traffic")


def straight(x, y0=-2000.0, y1=2000.0, south=False):
    return jx.Path([(x, y1), (x, y0)] if south else [(x, y0), (x, y1)])


def lane_change(x0, x1, y_start, length, y0=-2000.0, y1=2000.0):
    """Northbound path from lane x0 to lane x1, the move starting at y_start over `length` metres (cosine ease)."""
    pts = [(x0, y0)]
    for k in range(25):
        u = k / 24
        pts.append((x0 + (x1 - x0) * (1 - math.cos(math.pi * u)) / 2, y_start + length * u))
    pts.append((x1, y1))
    return jx.Path(pts)


def light(assets, az=200.0, elev=34.0):
    a = math.radians(az)
    to_sun = Vector((math.cos(a), math.sin(a), 0))
    stage.sky(None, -to_sun, assets, sun_elev_deg=elev, sun_energy=4.6)


def check_dump(path, extra=None):
    """Write what tests/test_gta_build.py checks: object names, every text body, marking specs, signal heights,
    plates. No rendering."""
    import json
    out = {"objects": [], "texts": [], "lines": [], "signals": [], "plates": [], "signs": []}
    for o in bpy.data.objects:
        out["objects"].append(o.name)
        if o.type == "FONT":
            out["texts"].append(o.data.body)
        if "us_line" in o:
            d = {k: (float(o[k]) if isinstance(o[k], (int, float)) else str(o[k])) for k in o.keys()
                 if k.startswith("us_")}
            vs = [o.matrix_world @ v.co for v in o.data.vertices]
            d["name"] = o.name
            d["quads"] = [[round(min(vs[i].x for i in p.vertices), 4), round(max(vs[i].x for i in p.vertices), 4),
                           round(min(vs[i].y for i in p.vertices), 4), round(max(vs[i].y for i in p.vertices), 4)]
                          for p in o.data.polygons][:40]
            out["lines"].append(d)
        if "us_signal_bottom" in o:
            hs = [c_ for c_ in o.children if c_.name.startswith(o.name + "_housing")]
            z = min((c_.matrix_world @ v.co).z for c_ in hs for v in c_.data.vertices) if hs else None
            out["signals"].append({"name": o.name, "bottom": z})
        if o.name.startswith("plate") or "us_plate" in o:
            out["plates"].append(o.name)
        if "sign" in o:
            out["signs"].append(str(o["sign"]))
    for c in bpy.data.collections:
        out["objects"].append(c.name)
    for m in bpy.data.materials:
        out["objects"].append(m.name)
    out.update(extra or {})
    json.dump(out, open(path, "w"), indent=0)
    print("CHECK_DONE", path)
