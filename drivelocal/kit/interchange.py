"""Autobahn interchange (Anschlussstelle, halbes Kleeblatt) for Drive Like a Local: Module B of MODEL-PLAN.md.

One spec drives everything: rnd/build_net.py turns LAYOUT into a SUMO network (nodes, edges, netconvert), the SUMO
lane shapes and junction polygons are exported to traffic/interchange_net.json.gz, and build() below turns that file
into the visible road in the approved episode 1 look (world.py materials, markings, Leitpfosten, terrain, flora).
The spec part of this module needs no Blender, so the net builder and the tests import it with plain python.

Layout (metres; y along the motorway, northbound = +y; x = 0 is the median centre; bridge of the crossing road at
y = 0, crossing road 6.6 m above the motorway on an embankment). Northbound, travelling +y:
  exit taper -920 .. -860 (60 m), exit lane parallel -860 .. -610 (250 m), diverge at -610, physical nose ~ -564;
  direct exit ramp (R 300 / straight / R 250) up to the crossing road at x = 129.55;
  entry loop: leg from the crossing road at x = 114.55 south to y = -260, half loop R 45 m (centre x 69.55),
  convergence at about 4 degrees to the merge point y = -60; acceleration lane -60 .. 190 (250 m), taper 190 .. 250.
Southbound is the point mirror (x, y) -> (-x, -y). Sign distances are measured to the start of the exit (the start
of the taper, Beginn des Ausfaedelungsstreifens): 448 at 1,000 m, 449 at 500 m, Baken 450 at 300 / 200 / 100 m.

Usage (Blender):
    import interchange as IC, traffic as TR
    S = IC.build(ASSETS)                       # fleet, roads, markings, gores, furniture, signs, terrain, flora
    data = TR.load("traffic/interchange_day.json.gz")
    TR.play(data, S["fleet"], S["traffic"], frames=(880, 920), keep=TR.near((20.0, -60.0), 600.0))
    (x, y, z), yaw = IC.main_point(+1, y=-1400.0, lane=1)   # a lane centre, for cameras
    S["ground"].h(x, y)                                    # terrain height anywhere
"""
import gzip
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NET_JSON = os.path.join(ROOT, "traffic", "interchange_net.json.gz")

# ------------------------------------------------------------------ the spec (sources in reports/interchange.md)
LANE = 3.75                 # RQ 36 lane width [road_spec 1, world.py]
LANES = 3
X_LEFT = 2.75               # left edge of the left lane (median 0 .. 2, left strip 2.0 .. 2.75)
X_RIGHT = 14.0              # right edge of the right lane; edge line 14.0 .. 14.3; shoulder to 16.8 (world.py)
X_PAVED = 16.8
LINE_LANE, LINE_EDGE, LINE_EXIT = 0.15, 0.30, 0.30
DASH_LANE, GAP_LANE = 6.0, 12.0          # Leitlinie on the Autobahn [S12]
DASH_EXIT, GAP_EXIT = 6.0, 6.0           # Abfahrtslinie / Einfahrt line [S12]
AUX_STRIP = 0.50                          # edge strip of the exit / merge lane, line on it [S1]
RAMP_LANE, RAMP_PAVED = 4.50, 6.50        # Q1 one-lane ramp [S2, S9]
LOOP_R = 45.0                             # loop radius, 40 .. 50 m [S6]
EXIT_TAPER, EXIT_LANE = 60.0, 250.0       # RAA 2008, EKA 1 [S1]
ENTRY_LANE, ENTRY_TAPER = 250.0, 60.0     # RAA 2008 [S3, S4, S8]
LP_SPACING = 50.0                         # Leitpfosten Zeichen 620 [S45]
BRIDGE_Z = 6.6                            # crossing road surface over the motorway (clearance 5.3 m under the deck)

Y_START, Y_END = -2700.0, 2700.0          # main line per carriageway (both sign sequences plus lead-in)
Y_VIS = 2050.0                            # tracks are clipped to |y| <= Y_VIS (no pop-in near the net ends)
X_VIS = 700.0                             # and to |x| <= X_VIS on the crossing road
EXIT_START = -920.0                       # start of the exit taper (reference for the sign distances)
EXIT_PARALLEL = EXIT_START + EXIT_TAPER   # -860
DIVERGE = EXIT_PARALLEL + EXIT_LANE       # -610
EXIT_SUMO_START = EXIT_START + EXIT_TAPER / 2   # SUMO's exit lane starts mid-taper
MERGE = -60.0                             # merge point (end of the convergence, start of the acceleration lane)
MERGE_PARALLEL_END = MERGE + ENTRY_LANE   # 190
MERGE_END = MERGE_PARALLEL_END + ENTRY_TAPER   # 250
MERGE_SUMO_END = MERGE_PARALLEL_END + ENTRY_TAPER / 2   # SUMO's merge lane ends mid-taper (220)

RAMP_X0 = X_RIGHT + LINE_EDGE + RAMP_LANE / 2   # 16.55: ramp centre where its left line meets the main edge line
EXIT_ARC1, EXIT_ANG, EXIT_ARC2 = 300.0, 28.0, 250.0
J_EXIT_X = 129.55                         # exit ramp meets the crossing road
J_LOOP_X = 114.55                         # loop leg leaves the crossing road (= loop centre x + R)
LOOP_Y = -260.0                           # loop centre y
CONV_LEN, CONV_SHIFT = 200.0, 8.0         # convergence from the loop to the merge point (max angle about 4.3 deg)

SIGNS_EXIT = [  # (id, distance before EXIT_START, width m, lower edge m, x offset beyond the paved edge)
    ("448", 1000.0, 2.40, 1.80, 2.2),
    ("449", 500.0, 3.80, 1.80, 2.6),
    ("450-52", 300.0, 0.65, 1.00, 1.6),   # 650 x 1500 mm (dimensions on the Commons drawing)
    ("450-51", 200.0, 0.65, 1.00, 1.6),
    ("450-50", 100.0, 0.65, 1.00, 1.6),
]
CROSS_LANE = 3.50                         # RQ 11 crossing road [S54]
CROSS_X0, CROSS_X1 = -900.0, 900.0
BRIDGE_HALF = 36.0                        # abutments at x = +-36


def smooth5(t):
    t = min(1.0, max(0.0, t))
    return t * t * t * (t * (6 * t - 15) + 10)


def smooth5_d(t):
    if t <= 0.0 or t >= 1.0:
        return 0.0
    return 30 * t * t * (t - 1) ** 2


# ------------------------------------------------------------------ polylines
class Poly:
    """3D polyline with arc length. pts: [(x, y, z)]."""

    def __init__(self, pts):
        self.p = [tuple(map(float, q)) + ((0.0,) if len(q) == 2 else ()) for q in pts]
        self.s = [0.0]
        for a, b in zip(self.p, self.p[1:]):
            self.s.append(self.s[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        self.L = self.s[-1]

    def _seg(self, s):
        s = min(max(s, 0.0), self.L)
        lo, hi = 0, len(self.s) - 1
        while hi - lo > 1:
            m = (lo + hi) // 2
            if self.s[m] <= s:
                lo = m
            else:
                hi = m
        d = self.s[hi] - self.s[lo]
        return lo, hi, ((s - self.s[lo]) / d if d > 0 else 0.0)

    def at(self, s):
        """(x, y, z, heading) at arc length s; heading = atan2(dy, dx) (0 = +x)."""
        lo, hi, u = self._seg(s)
        a, b = self.p[lo], self.p[hi]
        x = a[0] + (b[0] - a[0]) * u
        y = a[1] + (b[1] - a[1]) * u
        z = a[2] + (b[2] - a[2]) * u
        # heading from a short central difference (smooth across vertices)
        e = 1.0
        lo2, hi2, u2 = self._seg(max(0.0, s - e))
        lo3, hi3, u3 = self._seg(min(self.L, s + e))
        pa = [self.p[lo2][k] + (self.p[hi2][k] - self.p[lo2][k]) * u2 for k in range(2)]
        pb = [self.p[lo3][k] + (self.p[hi3][k] - self.p[lo3][k]) * u3 for k in range(2)]
        return x, y, z, math.atan2(pb[1] - pa[1], pb[0] - pa[0])

    def offset_pt(self, s, d, h=0.0):
        """Point d metres to the RIGHT of travel at arc length s."""
        x, y, z, th = self.at(s)
        return (x + math.sin(th) * d, y - math.cos(th) * d, z + h)

    def resample(self, step):
        n = max(1, int(math.ceil(self.L / step)))
        return Poly([self.at(self.L * k / n)[:3] for k in range(n + 1)])

    def reversed(self):
        return Poly(list(reversed(self.p)))

    def nearest_s(self, x, y):
        best, bs = 1e18, 0.0
        for i, (a, b) in enumerate(zip(self.p, self.p[1:])):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
            qx, qy = a[0] + dx * u, a[1] + dy * u
            d = (qx - x) ** 2 + (qy - y) ** 2
            if d < best:
                best, bs = d, self.s[i] + u * math.sqrt(L2)
        return bs, math.sqrt(best)


def _walk(start, heading_cw_deg, parts, step=2.0):
    """Centreline from primitives. heading measured clockwise from +y (north), right turns positive.
    parts: ('line', L) | ('arc', R, deg) | ('to_y', y) (straight line until y is reached)."""
    x, y = start
    h = math.radians(heading_cw_deg)
    pts = [(x, y)]
    for p in parts:
        if p[0] in ("line", "to_y"):
            if p[0] == "line":
                L = p[1]
            else:
                L = (p[1] - y) / math.cos(h)
            n = max(1, int(L / step))
            for k in range(1, n + 1):
                pts.append((x + math.sin(h) * L * k / n, y + math.cos(h) * L * k / n))
            x, y = pts[-1]
        else:
            R, deg = p[1], p[2]
            sg = 1 if deg > 0 else -1
            # centre to the right (sg > 0) or left of travel
            cx, cy = x + sg * math.cos(h) * R, y - sg * math.sin(h) * R
            a0 = math.atan2(y - cy, x - cx)
            tot = math.radians(abs(deg))
            n = max(2, int(R * tot / step))
            for k in range(1, n + 1):
                a = a0 - sg * tot * k / n
                pts.append((cx + R * math.cos(a), cy + R * math.sin(a)))
            x, y = pts[-1]
            h += math.radians(deg)
    return pts


def _with_z(pts2, zfun):
    P = Poly(pts2)
    out = []
    for p, s in zip(P.p, P.s):
        out.append((p[0], p[1], zfun(s, P.L)))
    return out


def cross_y(x):
    """Crossing road centreline: straight over the interchange, gentle bends further out."""
    a = abs(x) - 420.0
    if a <= 0:
        return 0.0
    return (0.00035 if x > 0 else -0.0003) * a * a


def cross_z(x):
    """Crossing road surface height: 6.6 m over the motorway and the ramp junctions, down to grade beyond 420 m."""
    a = abs(x)
    if a <= 200.0:
        return BRIDGE_Z
    return BRIDGE_Z * (1.0 - smooth5((a - 200.0) / 220.0))


def ramp_exit_xy():
    """Northbound exit ramp centreline from the diverge to the crossing road (2D)."""
    # solve the straight length so the ramp arrives at x = J_EXIT_X heading north
    a = math.radians(EXIT_ANG)
    gain = EXIT_ARC1 * (1 - math.cos(a)) + EXIT_ARC2 * (1 - math.cos(a))
    Ls = (J_EXIT_X - RAMP_X0 - gain) / math.sin(a)
    return _walk((RAMP_X0, DIVERGE), 0.0, [("arc", EXIT_ARC1, EXIT_ANG), ("line", Ls), ("arc", EXIT_ARC2, -EXIT_ANG),
                                            ("to_y", 0.0)])


def ramp_loop_xy():
    """Northbound entry: leg from the crossing road south, half loop R 45, convergence to the merge point (2D)."""
    pts = _walk((J_LOOP_X, 0.0), 180.0, [("to_y", LOOP_Y), ("arc", LOOP_R, 180.0)])
    x0 = pts[-1][0]
    n = int(CONV_LEN / 2.0)
    for k in range(1, n + 1):
        t = k / n
        pts.append((x0 - CONV_SHIFT * smooth5(t), LOOP_Y + CONV_LEN * t))
    return pts


def exit_z(s, L):
    return BRIDGE_Z * smooth5((s - 60.0) / max(1.0, L - 60.0 - 25.0))


def loop_z(s, L):
    return BRIDGE_Z * (1.0 - smooth5(s / max(1.0, L - 45.0)))


def layout(direction=1):
    """Everything the net builder needs, for one carriageway (direction +1 northbound, -1 southbound, point
    mirror). Returns centrelines with z and the key stations."""
    m = direction

    def T(p):
        return (m * p[0], m * p[1]) + tuple(p[2:])

    ex = _with_z(ramp_exit_xy(), exit_z)
    lp = _with_z(ramp_loop_xy(), loop_z)
    return dict(exit=[T(p) for p in ex], loop=[T(p) for p in lp], dir=m)


def aux_width(y):
    """Visual width of the auxiliary lane on the northbound main line at y (exit lane with taper, merge lane with
    taper); 0 where there is none. Southbound: aux_width(-y)."""
    if EXIT_START <= y < EXIT_PARALLEL:
        return LANE * (y - EXIT_START) / EXIT_TAPER
    if EXIT_PARALLEL <= y <= DIVERGE:
        return LANE
    if MERGE <= y <= MERGE_PARALLEL_END:
        return LANE
    if MERGE_PARALLEL_END < y < MERGE_END:
        return LANE * (MERGE_END - y) / ENTRY_TAPER
    return 0.0


def edge_in(y):
    """Inner edge (x) of the right edge line of the northbound main line. Along an exit or merge lane the line moves
    out with the lane: from 14.0 (normal edge line) to 18.05 (beyond the 0.30 m broken line and the 3.75 m lane)."""
    return X_RIGHT + aux_width(y) * (LANE + LINE_EXIT) / LANE


def paved_right(y):
    """Right paved edge (x) of the northbound main line: hard shoulder (16.8), or along an exit / merge lane its
    0.50 m edge strip (Randstreifen, the edge line sits on it): 18.55 at full width."""
    w = aux_width(y)
    return max(X_PAVED, edge_in(y) + AUX_STRIP) if w > 0 else X_PAVED


def sign_stations():
    """Northbound exit sequence: [(id, y, width, lower edge, x)]."""
    out = []
    for sid, d, w, low, dx in SIGNS_EXIT:
        y = EXIT_START - d
        out.append((sid, y, w, low, paved_right(y) + dx))
    return out


def load_net(path=None):
    with gzip.open(path or NET_JSON, "rt", encoding="utf-8") as f:
        return json.load(f)


def main_lane(x, y):
    """Classify a point on the motorway main line: (direction, lane) with lane 0 = left, 1 = middle, 2 = right,
    3 = auxiliary (exit / merge lane), or None when the point is not on a main carriageway lane."""
    d = 1 if x > 0 else -1
    ax, ay = abs(x), d * y
    if ay < Y_START - 1 or ay > Y_END + 1 or ax < X_LEFT:
        return None
    if ax < X_RIGHT:
        return d, int((ax - X_LEFT) // LANE)
    if aux_width(ay) > 0.5 and ax < edge_in(ay):
        return d, 3
    return None


def main_point(direction, y, lane=1, h=0.0):
    """World point of a through lane centre (lane 1 = right, 3 = left) at station y (northbound coordinates; for
    southbound pass the northbound-equivalent y, the point is mirrored). Returns ((x, y, z), yaw)."""
    x = X_RIGHT - LANE / 2 - (lane - 1) * LANE
    return (direction * x, direction * y, h), (math.pi / 2 if direction > 0 else -math.pi / 2)


# ================================================================== Blender build (needs bpy)
try:
    import bpy
    from mathutils import Vector, kdtree, noise
except ImportError:      # plain python: net builder and spec checks
    bpy = None

# plate rectangles of the two Commons construction drawings (same values as signs/de-interchange.json)
PLATES = {"449": (0.041, 0.022, 0.96, 0.9578), "450-52": (0.1904, 0.0893, 0.9209, 1.0)}
SIGN_SIZE = {  # id: (width m, lower edge m, posts); Baken 450: 650 x 1500 mm (dimensions on the Commons drawing)
    "448": (3.0, 2.0, 2), "449": (3.9, 2.0, 2), "450-52": (0.65, 0.9, 1), "450-51": (0.65, 0.9, 1),
    "450-50": (0.65, 0.9, 1), "332": (3.2, 1.7, 2), "333": (2.6, 0.9, 2), "330.1": (0.9, 1.7, 1),
    "330.2": (0.9, 1.7, 1), "205": (0.9, 1.7, 1)}
RAMP_LL = RAMP_LR = RAMP_LANE / 2                    # lane half widths
RAMP_SL, RAMP_SR = 0.75, 1.25                        # paved strips left / right (6.50 m paved; the split is assumed)
CROSS_PAVED = CROSS_LANE + 0.5                       # RQ 11: 3.50 m lane plus 0.50 m edge strip [S54]
CROSS_VIS = 1500.0                                   # crossing road drawn to +-1.5 km (SUMO net: +-900 m)
SIGN_GAP = 2.0                                       # sign edge to the paved edge (m), assumption


def chain(net, edges, lane=0):
    """Centreline [(x, y, z)] from SUMO lane shapes: lane `lane` of each edge plus the internal (via) lane between
    consecutive edges, as netconvert wrote them."""
    L = net["lanes"]
    via = {(c["from"], c["to"], c["fromLane"], c["toLane"]): c.get("via") for c in net["connections"]}
    pts = []

    def add(shape):
        for p in shape:
            q = (float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0)
            if not pts or math.hypot(q[0] - pts[-1][0], q[1] - pts[-1][1]) > 0.05:
                pts.append(q)
    for k, e in enumerate(edges):
        add(L[f"{e}_{lane}"]["shape"])
        if k + 1 < len(edges):
            v = via.get((e, edges[k + 1], str(lane), str(lane)))
            if v and v in L:
                add(L[v]["shape"])
    return pts


def ramp_prof(kind, s, L):
    """Lateral offsets from a ramp centreline at arc length s (right of travel positive):
    (left paved edge, left lane edge, right lane edge, right paved edge). The exit ramp starts as wide as the exit
    lane (3.75 m lane, 0.50 m strip) and widens to the Q1 section within 50 m; the entry ends the same way; both
    narrow to the bare lane over the 20 m where they meet the crossing road (SUMO junction polygon)."""
    if kind == "exit":
        u, e = smooth5(s / 50.0), smooth5((L - s) / 20.0)
    else:
        u, e = smooth5((L - s) / 50.0), smooth5(s / 20.0)
    lr = 1.5 + (RAMP_LR - 1.5) * u
    sr = (0.5 + (RAMP_SR - 0.5) * u) * e
    return -(RAMP_LL + RAMP_SL * e), -RAMP_LL, lr, lr + sr


class _CL:
    """Centreline resampled every `step` m: pts [(x, y, z, heading)], s (arc length)."""

    def __init__(self, pts, step=1.0):
        P = Poly(pts).resample(step)
        self.P = P
        self.s = list(P.s)
        self.pts = [P.at(s) for s in self.s]
        self.L = P.L

    def off(self, i, d, dz=0.0):
        x, y, z, th = self.pts[i]
        return (x + math.sin(th) * d, y - math.cos(th) * d, z + dz)

    def index(self, s):
        return max(0, min(len(self.s) - 1, int(round(s / (self.L / (len(self.s) - 1))))))


class Builder:
    """Builds the interchange into the current scene. Geometry is generated in northbound coordinates and turned by
    180 degrees about z for the southbound carriageway (sg = -1): the layout is a point mirror, so face winding
    stays valid."""

    def __init__(self, assets, M, env, lib, net):
        import signs as SG
        import world as W
        self.W, self.SG, self.M, self.env, self.lib, self.net = W, SG, M, env, lib, net
        self.assets = assets
        self.asph_ramp = W.asphalt("asphalt_ramp", tracks=False)
        self.objs = {}
        self.signs = []
        self.posts = []
        self.ramps = {}
        self.nose_y = {}

    # ---------------------------------------------------------------- mesh helpers
    def obj(self, name, verts, faces, mat, uvs=None, **props):
        o = self.W.mesh_obj(name, verts, faces, mat, self.env, uvs)
        for k, v in props.items():
            o[k] = v
        self.objs.setdefault(name, []).append(o)
        return o

    @staticmethod
    def T(sg, p):
        return (sg * p[0], sg * p[1], p[2])

    def ribbon(self, name, sg, rows, mat, keep=None, uv=None, **props):
        """rows: list of rows of points (northbound coordinates) ordered left to right of travel; travel runs along
        the rows. keep(i): keep the quads between rows i and i + 1. One mesh, faces up."""
        verts, faces, uvs = [], [], []
        n = len(rows[0])
        for i, row in enumerate(rows):
            for j, p in enumerate(row):
                verts.append(self.T(sg, p))
                uvs.append(uv(i, j, p) if uv else (abs(p[0]), p[1]))
        for i in range(len(rows) - 1):
            if keep and not keep(i):
                continue
            for j in range(n - 1):
                a, b = i * n + j, (i + 1) * n + j
                faces.append((a, a + 1, b + 1, b))
        if not faces:
            return None
        return self.obj(name, verts, faces, mat, uvs, **props)

    def quads(self, name, sg, quads_, mat, **props):
        """Separate quads [(p0, p1, p2, p3)] (counter-clockwise from above, northbound coordinates) in one mesh."""
        verts, faces, uvs = [], [], []
        for q in quads_:
            k = len(verts)
            for p in q:
                verts.append(self.T(sg, p))
                uvs.append((p[0], p[1]))
            faces.append((k, k + 1, k + 2, k + 3))
        if not faces:
            return None
        return self.obj(name, verts, faces, mat, uvs, **props)

    def boxes(self, name, items, mat):
        """Many boxes in one mesh: items [(x, y, z_bottom, sx, sy, sz, yaw)] in world coordinates."""
        verts, faces = [], []
        for x, y, z0, sx, sy, sz, yaw in items:
            c, s = math.cos(yaw), math.sin(yaw)
            k = len(verts)
            for dz in (0.0, sz):
                for dx, dy in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2)):
                    verts.append((x + dx * c - dy * s, y + dx * s + dy * c, z0 + dz))
            faces += [(k + 3, k + 2, k + 1, k), (k + 4, k + 5, k + 6, k + 7), (k, k + 1, k + 5, k + 4),
                      (k + 1, k + 2, k + 6, k + 5), (k + 2, k + 3, k + 7, k + 6), (k + 3, k, k + 4, k + 7)]
        return self.obj(name, verts, faces, mat) if faces else None

    @staticmethod
    def cut(a, b, holes):
        out = [(a, b)]
        for h0, h1 in holes:
            nxt = []
            for c0, c1 in out:
                if h1 <= c0 or h0 >= c1:
                    nxt.append((c0, c1))
                    continue
                if c0 < h0:
                    nxt.append((c0, h0))
                if h1 < c1:
                    nxt.append((h1, c1))
            out = nxt
        return [(c0, c1) for c0, c1 in out if c1 - c0 > 0.5]

    # ---------------------------------------------------------------- main carriageways (straight, along y)
    def main_line(self, sg):
        M = self.M
        side = "n" if sg > 0 else "s"

        def ys(a, b, step):
            out = [a]
            if step:
                k = a + step
                while k < b - 1e-6:
                    out.append(k)
                    k += step
            out.append(b)
            return out

        def val(f, y):
            return f(y) if callable(f) else f

        def band(name, x0, x1, a, b, mat, dz0=0.0, dz1=None, step=None, **pr):
            dz1 = dz0 if dz1 is None else dz1
            rows = [[(val(x0, y), y, dz0), (val(x1, y), y, dz1)] for y in ys(a, b, step)]
            return self.ribbon(name, sg, rows, mat, **pr)

        def dashes(name, xc, w, a, b, dash, gap, mat, dz=0.006, **pr):
            qs = []
            y = a
            while y < b - 0.01:
                e = min(y + dash, b)
                qs.append(((xc - w / 2, y, dz), (xc + w / 2, y, dz), (xc + w / 2, e, dz), (xc - w / 2, e, dz)))
                y += dash + gap
            return self.quads(name, sg, qs, mat, dash=dash, gap=gap, width=w, x=xc, **pr)

        band(f"{side}_lanes", 2.0, X_RIGHT + LINE_LANE, Y_START, Y_END, M.asph)
        band(f"{side}_edgeL", X_LEFT - LINE_EDGE, X_LEFT, Y_START, Y_END, M.paint, 0.006, width=LINE_EDGE)
        for x in (X_LEFT + LANE, X_LEFT + 2 * LANE):
            dashes(f"{side}_leitlinie", x, LINE_LANE, Y_START + 3.0, Y_END, DASH_LANE, GAP_LANE, M.paint)
        nx, ne = self.nose_y["exit"], self.nose_y["entry"]
        for a, b, aux in ((Y_START, EXIT_START, False), (EXIT_START, DIVERGE, True), (DIVERGE, MERGE, False),
                          (MERGE, MERGE_END, True), (MERGE_END, Y_END, False)):
            if not aux:
                band(f"{side}_edgeR", X_RIGHT, X_RIGHT + LINE_EDGE, a, b, M.paint, 0.006, width=LINE_EDGE)
                band(f"{side}_shoulder", X_RIGHT + LINE_LANE, X_PAVED, a, b, M.asph_sh, -0.002)
            else:
                band(f"{side}_auxlane", X_RIGHT + LINE_LANE, edge_in, a, b, M.asph, step=2.0, y0=a, y1=b)
                band(f"{side}_auxstrip", edge_in, paved_right, a, b, M.asph_sh, -0.002, step=2.0)
                band(f"{side}_edgeR_aux", edge_in, lambda y: edge_in(y) + LINE_EDGE, a, b, M.paint, 0.006, step=2.0,
                     width=LINE_EDGE)
                nm = f"{side}_abfahrtslinie" if a == EXIT_START else f"{side}_einfahrtslinie"
                dashes(nm, X_RIGHT + LINE_EXIT / 2, LINE_EXIT, a, b, DASH_EXIT, GAP_EXIT, M.paint, y0=a, y1=b)
            for c0, c1 in self.cut(a, b, [(DIVERGE, nx), (ne, MERGE)]):
                band(f"{side}_bankett", paved_right, lambda y: paved_right(y) + 1.5, c0, c1, M.gravel, -0.02, -0.12,
                     step=2.0 if aux else None)

    def median(self):
        M = self.M
        self.ribbon("median", 1, [[(-2.0, Y_START, 0.0), (2.0, Y_START, 0.0)], [(-2.0, Y_END, 0.0), (2.0, Y_END, 0.0)]],
                    M.grass)
        w = [(0.0, 0.0), (0.03, 0.08), (0.0, 0.155), (0.03, 0.23), (0.0, 0.31)]   # W-beam (world.py profile)
        for sgn in (1, -1):
            for nm, prof, mat in (("rail_median", [(sgn * (0.12 + dx), 0.45 + h) for dx, h in w], M.steel),
                                  ("rail_median_back", [(sgn * 0.105, 0.45), (sgn * 0.105, 0.76)], M.steel_dark)):
                m = len(prof)
                verts = [(x, y, h) for y in (Y_START, Y_END) for x, h in prof]
                faces = [(j, j + 1, m + j + 1, m + j) if sgn < 0 else (j, m + j, m + j + 1, j + 1) for j in range(m - 1)]
                self.obj(nm, verts, faces, mat)
        n = int((Y_END - Y_START) / 2.0)
        self.boxes("rail_median_posts", [(0.0, Y_START + 2.0 * k, 0.0, 0.1, 0.1, 0.8, 0.0) for k in range(n)],
                   M.steel_dark)

    # ---------------------------------------------------------------- ramps from the SUMO lane shapes
    def ramp_lines(self):
        """Centrelines in northbound coordinates of the exit ramp and the entry (loop), both carriageways, chained
        from the SUMO lane shapes (s_* shapes turned back by 180 degrees)."""
        out = {}
        for sg, pre in ((1, "n"), (-1, "s")):
            ex = [(sg * p[0], sg * p[1], p[2]) for p in chain(self.net, [f"{pre}_off1", f"{pre}_off2"])]
            ex.insert(0, (ex[0][0], DIVERGE - 2.0, ex[0][2]))     # starts 2 m under the end of the exit lane
            en = [(sg * p[0], sg * p[1], p[2]) for p in chain(self.net, [f"{pre}_on1", f"{pre}_on2", f"{pre}_on3"])]
            en.append((en[-1][0], MERGE + 2.0, en[-1][2]))
            out[sg] = {"exit": _CL(ex), "entry": _CL(en)}
        self.ramps = out
        return out

    def find_noses(self):
        """Gore tips: where the ramp's left paved edge leaves the main carriageway's paved edge (16.8 m)."""
        ex, en = self.ramps[1]["exit"], self.ramps[1]["entry"]
        ny = next(ex.pts[i][1] for i in range(len(ex.pts))
                  if ex.off(i, ramp_prof("exit", ex.s[i], ex.L)[0])[0] > X_PAVED)
        ey = next(en.pts[i][1] for i in range(len(en.pts) - 1, -1, -1)
                  if en.off(i, ramp_prof("entry", en.s[i], en.L)[0])[0] > X_PAVED)
        self.nose_y = {"exit": ny, "entry": ey}
        return self.nose_y

    @staticmethod
    def clamp_main(p):
        """Keep ramp surface points off the through lanes and the hard shoulder (northbound coordinates,
        ground-level part only): the surfaces meet edge to edge at 16.8 m. Along the exit / merge lane the ramp's
        first and last metres tuck 3 mm under that lane, so there is never a gap."""
        x, y, z = p
        if z < 0.5 and Y_START < y < Y_END and x < X_PAVED:
            return (X_PAVED, y, z)
        return p

    def ramp(self, sg, kind):
        M = self.M
        cl = self.ramps[sg][kind]
        nm = ("n" if sg > 0 else "s") + "_" + kind
        prof = [ramp_prof(kind, s, cl.L) for s in cl.s]
        rows = [[self.clamp_main(cl.off(i, d, -0.003)) for d in (l0, l1, 0.0, r1, r0)]
                for i, (l0, l1, r1, r0) in enumerate(prof)]
        self.ribbon(nm + "_surface", sg, rows, self.asph_ramp, uv=lambda i, j, p: (40.0 + 1.6 * j, cl.s[i]),
                    lane=RAMP_LANE, paved=RAMP_LANE + RAMP_SL + RAMP_SR)

        def live(s):
            return s < cl.L - 22.0 if kind == "exit" else s > 22.0

        def keep(i):
            return live(cl.s[i]) and live(cl.s[i + 1])
        self.ribbon(nm + "_lineL", sg, [[cl.off(i, p[1] - LINE_EDGE, 0.006), cl.off(i, p[1], 0.006)]
                                        for i, p in enumerate(prof)], M.paint, keep=keep, width=LINE_EDGE)
        self.ribbon(nm + "_lineR", sg, [[cl.off(i, p[2], 0.006), cl.off(i, p[2] + LINE_EDGE, 0.006)]
                                        for i, p in enumerate(prof)], M.paint, keep=keep, width=LINE_EDGE)

        def free(i):      # left Bankett only where the ramp is clear of the main carriageway
            p = cl.off(i, prof[i][0] - 1.0)
            return p[2] > 0.5 or p[0] > paved_right(p[1]) + 1.5
        self.ribbon(nm + "_bankettL", sg, [[cl.off(i, p[0] - 1.0, -0.12), cl.off(i, p[0], -0.02)]
                                           for i, p in enumerate(prof)], M.gravel,
                    keep=lambda i: keep(i) and free(i) and free(i + 1))
        self.ribbon(nm + "_bankettR", sg, [[cl.off(i, p[3], -0.02), cl.off(i, p[3] + 1.0, -0.12)]
                                           for i, p in enumerate(prof)], M.gravel, keep=keep)

    # ---------------------------------------------------------------- gores (Sperrflaeche Zeichen 298, hatched)
    def gore(self, sg, kind):
        """Hatched area between the main edge line and the ramp's left edge line, closed by a line at the nose."""
        M = self.M
        cl = self.ramps[sg][kind]
        pts = []
        for i in range(len(cl.pts)):
            if cl.pts[i][2] < 0.5:
                p = cl.off(i, ramp_prof(kind, cl.s[i], cl.L)[1] - LINE_EDGE)
                pts.append((p[1], p[0]))
        pts.sort()
        ys = [p[0] for p in pts]
        xs = [p[1] for p in pts]

        def xr(y):
            if y <= ys[0]:
                return xs[0]
            if y >= ys[-1]:
                return xs[-1]
            lo, hi = 0, len(ys) - 1
            while hi - lo > 1:
                m = (lo + hi) // 2
                if ys[m] <= y:
                    lo = m
                else:
                    hi = m
            u = (y - ys[lo]) / max(1e-9, ys[hi] - ys[lo])
            return xs[lo] + (xs[hi] - xs[lo]) * u
        x0 = X_RIGHT + LINE_EDGE
        if kind == "exit":
            ya, yb = DIVERGE, self.nose_y["exit"] - 3.0
            yc = yb
        else:
            ya, yb = self.nose_y["entry"] + 3.0, MERGE
            yc = ya
        h = LINE_EDGE / 2
        nm = ("n" if sg > 0 else "s") + "_" + kind
        self.quads(nm + "_gore_close", sg, [((x0, yc - h, 0.0065), (xr(yc), yc - h, 0.0065), (xr(yc), yc + h, 0.0065),
                                            (x0, yc + h, 0.0065))], M.paint)
        # 45 degree stripes, 0.50 m wide every 2.5 m along the road (stripe size: assumption, RMS plans not open)
        sw, period = 0.50, 2.5
        lean = 1.0 if kind == "exit" else -1.0
        qs = []
        yk = ya - 20.0
        while yk < yb + 20.0:
            ed = []
            for e in (-sw / 2, sw / 2):
                def yat(x, e=e, yk=yk):
                    return yk + e * math.sqrt(2.0) + lean * (x - x0)
                ins = [x0 + 0.05 * t for t in range(161) if ya <= yat(x0 + 0.05 * t) <= yb
                       and x0 + 0.05 * t <= xr(yat(x0 + 0.05 * t))]
                if not ins:
                    ed = None
                    break
                ed.append((ins[0], ins[-1], yat))
            yk += period
            if not ed:
                continue
            (a0, b0, f0), (a1, b1, f1) = ed
            q = ((a0, f0(a0), 0.007), (b0, f0(b0), 0.007), (b1, f1(b1), 0.007), (a1, f1(a1), 0.007))
            (ax, ay, _), (bx, by, _), (cx, cy, _) = q[0], q[1], q[2]
            if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) < 0:
                q = tuple(reversed(q))
            qs.append(q)
        self.quads(nm + "_hatch", sg, qs, M.paint, stripe=sw, period=period, y0=ya, y1=yb)

    # ---------------------------------------------------------------- crossing road, junctions, bridge
    def crossing(self):
        M = self.M
        xs = [-CROSS_VIS + 2.0 * k for k in range(int(CROSS_VIS) + 1)]
        cl = _CL([(x, cross_y(x), cross_z(x)) for x in xs], 2.0)
        self.cross = cl
        h = CROSS_PAVED
        self.ribbon("cross_surface", 1, [[cl.off(i, -h), cl.off(i, 0.0), cl.off(i, h)] for i in range(len(cl.pts))],
                    self.asph_ramp, uv=lambda i, j, p: (60.0 + j * h, cl.s[i]))
        # centre Leitlinie 0.12 m, 6 m dash / 12 m gap (1:2 outside junctions [S12, S14]; length assumed)
        qs = []
        s = 3.0
        while s + 6.0 < cl.L:
            a, b = cl.P.offset_pt(s, -0.06, 0.006), cl.P.offset_pt(s, 0.06, 0.006)
            c_, d_ = cl.P.offset_pt(s + 6.0, 0.06, 0.006), cl.P.offset_pt(s + 6.0, -0.06, 0.006)
            qs.append((a, b, c_, d_))
            s += 18.0
        self.quads("cross_leitlinie", 1, qs, M.paint)
        mouths = {1: (J_LOOP_X - 14, J_EXIT_X + 14), -1: (-J_EXIT_X - 14, -J_LOOP_X + 14)}

        def free(i, side):
            a, b = mouths[side]
            return not (a < cl.pts[i][0] < b)
        for side in (1, -1):
            if side > 0:
                lr = [[cl.off(i, h - 0.5, 0.006), cl.off(i, h - 0.25, 0.006)] for i in range(len(cl.pts))]
                br = [[cl.off(i, h, -0.02), cl.off(i, h + 1.0, -0.12)] for i in range(len(cl.pts))]
            else:
                lr = [[cl.off(i, -h + 0.25, 0.006), cl.off(i, -h + 0.5, 0.006)] for i in range(len(cl.pts))]
                br = [[cl.off(i, -h - 1.0, -0.12), cl.off(i, -h, -0.02)] for i in range(len(cl.pts))]
            self.ribbon("cross_edge", 1, lr, M.paint, keep=lambda i, side=side: free(i, side) and free(i + 1, side))
            self.ribbon("cross_bankett", 1, br, M.gravel,
                        keep=lambda i, side=side: free(i, side) and free(i + 1, side)
                        and abs(cl.pts[i][0]) > BRIDGE_HALF + 0.5)
        # junction fills from the SUMO junction polygons (fillets where the ramps join), 5 mm under the road
        import bmesh
        for jid in ("jEE", "jEL", "jWE", "jWL"):
            J = self.net["junctions"][jid]
            pts = []
            for p in J["shape"]:
                q = (p[0], p[1], (p[2] if len(p) > 2 else J["z"]) - 0.005)
                if not pts or math.hypot(q[0] - pts[-1][0], q[1] - pts[-1][1]) > 0.01:
                    pts.append(q)
            if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 0.01:
                pts.pop()
            me = bpy.data.meshes.new("junction_" + jid)
            bm = bmesh.new()
            f = bm.faces.new([bm.verts.new(p) for p in pts])
            bmesh.ops.triangulate(bm, faces=[f])
            bm.normal_update()
            for fc in bm.faces:
                if fc.normal.z < 0:
                    fc.normal_flip()
            bm.to_mesh(me)
            bm.free()
            uv = me.uv_layers.new(name="UVMap")
            for poly in me.polygons:
                for li, vi in zip(poly.loop_indices, poly.vertices):
                    co = me.vertices[vi].co
                    uv.data[li].uv = (co.x, co.y)
            me.materials.append(self.asph_ramp)
            o = bpy.data.objects.new("junction_" + jid, me)
            self.env.objects.link(o)
            o["sumo_junction"] = jid

    def bridge(self):
        """Two-span concrete beam bridge carrying the crossing road over the motorway (abutments at x = +-36 m,
        median pier), with railings."""
        M = self.M
        zt = BRIDGE_Z
        hw = CROSS_PAVED + 1.5
        bx = [(0.0, 0.0, zt - 1.6, 2 * BRIDGE_HALF, 2 * hw, 1.58, 0.0)]
        for sy in (-1, 1):
            bx.append((0.0, sy * (CROSS_PAVED + 0.75), zt - 0.02, 2 * BRIDGE_HALF, 1.5, 0.17, 0.0))
        bx.append((0.0, 0.0, -0.8, 0.9, 7.0, zt - 1.6 + 0.8, 0.0))
        for sx in (-1, 1):
            bx.append((sx * (BRIDGE_HALF + 0.6), 0.0, -0.8, 1.2, 2 * hw + 2.0, zt + 0.8, 0.0))
        self.boxes("bridge_concrete", bx, M.concrete)
        rail = []
        for sy in (-1, 1):
            y = sy * (hw - 0.15)
            for k in range(int(BRIDGE_HALF) + 1):
                rail.append((-BRIDGE_HALF + 2.0 * k, y, zt + 0.15, 0.06, 0.06, 1.0, 0.0))
            rail.append((0.0, y, zt + 1.12, 2 * BRIDGE_HALF, 0.08, 0.08, 0.0))
            rail.append((0.0, y, zt + 0.65, 2 * BRIDGE_HALF, 0.04, 0.04, 0.0))
        self.boxes("bridge_railing", rail, M.steel)

    # ---------------------------------------------------------------- guardrails along ramps and embankments
    def rail_along(self, name, sg, cl, offset, keep):
        """W-beam guardrail at a lateral offset (right of travel positive) where keep(i); the beam faces the road."""
        M = self.M
        side = 1.0 if offset > 0 else -1.0
        w = [(0.0, 0.0), (0.03, 0.08), (0.0, 0.155), (0.03, 0.23), (0.0, 0.31)]
        prof = [(offset - side * dx, 0.45 + hh) for dx, hh in w]
        verts, faces, posts = [], [], []
        m = len(prof)
        for i in range(len(cl.pts)):
            verts += [self.T(sg, cl.off(i, d, hh)) for d, hh in prof]
            if i and keep(i - 1):
                a, b = (i - 1) * m, i * m
                for j in range(m - 1):
                    faces.append((a + j, a + j + 1, b + j + 1, b + j) if side > 0 else
                                 (a + j, b + j, b + j + 1, a + j + 1))
        acc = 0.0
        for i in range(len(cl.pts) - 1):
            if not keep(i):
                continue
            acc += cl.s[i + 1] - cl.s[i]
            if acc >= 2.0:
                acc = 0.0
                p = self.T(sg, cl.off(i, offset + side * 0.12, 0.0))
                posts.append((p[0], p[1], p[2] - 0.2, 0.1, 0.1, 1.0, 0.0))
        if faces:
            self.obj(name, verts, faces, M.steel)
            self.boxes(name + "_posts", posts, M.steel_dark)

    # ---------------------------------------------------------------- Leitpfosten (Zeichen 620)
    def leitpfosten(self):
        M, W = self.M, self.W
        white = W.leitpfosten(M, self.lib)
        orange = bpy.data.collections.new("leitpfosten_orange")
        self.lib.children.link(orange)
        for o in white.objects:
            if not o.name.startswith("lp_refl"):
                orange.objects.link(o.copy())
        # exits: orange elongated reflector [S45] in the black band, same face as the white one
        r = [(-0.016, -0.0375, 0.68), (0.016, -0.0375, 0.68), (0.016, -0.0375, 0.88), (-0.016, -0.0375, 0.88)]
        W.mesh_obj("lp_refl_orange", r, [(0, 1, 2, 3)], M.refl_amber, orange)
        self.lp = {"white": white, "orange": orange}

    def post(self, kind, x, y, z, heading, tag):
        e = self.W.instance(self.lp[kind], (x, y, z - 0.053), rz=heading - math.pi / 2, c=self.env)
        e.name = f"lp_{tag}"
        e["lp"] = kind
        e["tag"] = tag
        self.posts.append(e)
        return e

    def island_x(self, sg, yy):
        """x (northbound coordinates) of the middle of the gore island at station yy."""
        cl = self.ramps[sg]["exit"]
        s, _d = cl.P.nearest_s(X_PAVED + 6.0, yy)
        i = cl.index(s)
        xl = cl.off(i, ramp_prof("exit", cl.s[i], cl.L)[0])[0]
        return (X_PAVED + xl) / 2

    def place_posts(self, sg):
        """Right side of each carriageway every 50 m, 0.5 m beyond the paved edge: orange along the exit lane and
        on the gore island; ramps every 50 m (25 m on the loop), the exit ramp's first 150 m orange."""
        side = "n" if sg > 0 else "s"
        hd = math.pi / 2 if sg > 0 else -math.pi / 2
        y = math.floor(Y_START / LP_SPACING) * LP_SPACING + 10.0
        while y < Y_END - 20:
            skip = (DIVERGE - 1 < y < self.nose_y["exit"] + 40) or (self.nose_y["entry"] - 40 < y < MERGE + 1)
            if not skip and y > Y_START + 20:
                kind = "orange" if EXIT_START - 1 <= y <= DIVERGE else "white"
                self.post(kind, sg * (paved_right(y) + 0.5), sg * y, 0.0, hd, f"{side}_main")
            y += LP_SPACING
        for dy in (2.0, 12.0):
            yy = self.nose_y["exit"] + dy
            self.post("orange", sg * self.island_x(sg, yy), sg * yy, 0.0, hd, f"{side}_gore")
        for kind, step in (("exit", 50.0), ("entry", 25.0)):
            cl = self.ramps[sg][kind]
            s = 30.0
            while s < cl.L - 25:
                i = cl.index(s)
                p = cl.off(i, ramp_prof(kind, cl.s[i], cl.L)[3] + 0.5)
                if p[2] <= 2.0 and (p[2] > 0.5 or p[0] > paved_right(p[1]) + 1.0):
                    col = "orange" if (kind == "exit" and s < 150) else "white"
                    w = self.T(sg, p)
                    self.post(col, w[0], w[1], p[2] - 0.1, cl.pts[i][3] + (0.0 if sg > 0 else math.pi), f"{side}_{kind}")
                s += step

    # ---------------------------------------------------------------- signs (Commons files through kit/signs.py)
    def sign_set(self, sid):
        SG = self.SG
        if sid in PLATES:
            if os.path.exists(os.path.join(SG.SIGN_DIR, "de-interchange", sid + ".png")):
                return "de-interchange"
            # list de-interchange not fetched yet: the same Commons file from de-core with the plate rectangle of
            # signs/de-interchange.json (only the opaque plate is shown; the file is unaltered)
            SG._material("de-core", sid, 0.0)
            e = dict(SG._used.get(("de-core", sid), {}))
            e["plate"] = list(PLATES[sid])
            SG._used[("de-core", sid)] = e
        return "de-core"

    def sign(self, sid, x, y, heading, ground, tag, yn=None):
        SG = self.SG
        width, bottom, nposts = SIGN_SIZE[sid]
        set_ = self.sign_set(sid)
        rz = heading - math.pi / 2
        name = f"sign_{sid}_{tag}"
        if nposts == 1:
            root = SG.assembly([(sid, width)], self.env, (x, y, ground), rz=rz, bottom=bottom, set_=set_, name=name)
        else:
            root = bpy.data.objects.new(name, None)
            self.env.objects.link(root)
            root.location = (x, y, ground)
            root.rotation_euler = (0, 0, rz)
            f = SG.face(sid, self.env, width, set_, name=name + "_face")
            f.location = (0, 0, bottom)
            f.parent = root
            top = bottom + f["height"]
            for dx in (-0.32 * width, 0.32 * width):
                p = SG.post(self.env, top + 0.05, r=0.05, name=name + "_post")
                p.location = (dx, 0.08, (top + 0.05) / 2)
                p.parent = root
        root["sign_id"] = sid
        root["set"] = set_
        root["tag"] = tag
        root["width"] = width
        root["bottom"] = bottom
        if yn is not None:
            root["yn"] = yn
        self.signs.append(root)
        return root

    def place_signs(self, sg, ground, show_300=False):
        side = "n" if sg > 0 else "s"
        hd = math.pi / 2 if sg > 0 else -math.pi / 2
        for sid, d, _w, _low, _dx in SIGNS_EXIT:
            if sid == "450-52" and not show_300:
                continue        # the Commons drawing has dimension arrows inside the sign face (report)
            yn = EXIT_START - d
            x = paved_right(yn) + SIGN_GAP + SIGN_SIZE[sid][0] / 2
            self.sign(sid, sg * x, sg * yn, hd, ground(sg * x, sg * yn), f"{side}_seq", yn=yn)
        for sid, dy in (("333", 12.0), ("332", 30.0)):      # gore island: arrow board near the tip, exit board behind
            yy = self.nose_y["exit"] + dy
            xm = self.island_x(sg, yy)
            self.sign(sid, sg * xm, sg * yy, hd, ground(sg * xm, sg * yy), f"{side}_gore", yn=yy)
        cl = self.ramps[sg]["exit"]
        for sid, back in (("330.2", 70.0), ("205", 16.0)):  # end of the exit ramp: end of the Autobahn, give way
            i = cl.index(cl.L - back)
            p = cl.off(i, ramp_prof("exit", cl.s[i], cl.L)[3] + 1.2)
            w = self.T(sg, p)
            self.sign(sid, w[0], w[1], cl.pts[i][3] + (0.0 if sg > 0 else math.pi), p[2] - 0.15, f"{side}_rampend")
        cl = self.ramps[sg]["entry"]                       # start of the on-ramp: Zeichen 330.1
        i = cl.index(26.0)
        p = cl.off(i, ramp_prof("entry", cl.s[i], cl.L)[3] + 1.2)
        w = self.T(sg, p)
        self.sign("330.1", w[0], w[1], cl.pts[i][3] + (0.0 if sg > 0 else math.pi), p[2] - 0.15, f"{side}_onramp",
                  yn=p[1])


# ------------------------------------------------------------------ ground (terrain height)
class Ground:
    """Terrain height: farmland hills (world.ground_z) flattened near the interchange, the motorway verge profile of
    episode 1 (about 0.8 m below the road at 27 m), embankments (1:2.2) under raised ramps and the crossing road,
    and a slope cone under each bridge end."""

    def __init__(self, road, ramps, cross):
        import world as W
        self.W, self.road = W, road
        self.roads = []
        for sg in (1, -1):
            for kind in ("exit", "entry"):
                self.roads.append(self._kd([(sg * p[0], sg * p[1], p[2]) for p in ramps[sg][kind].pts], 3.5, "ramp"))
        self.roads.append(self._kd([p[:3] for p in cross.pts], CROSS_PAVED, "cross"))

    @staticmethod
    def _kd(pts, half, kind):
        kd = kdtree.KDTree(len(pts))
        for i, p in enumerate(pts):
            kd.insert((p[0], p[1], 0.0), i)
        kd.balance()
        return dict(kd=kd, pts=pts, half=half, kind=kind)

    @staticmethod
    def near(x, y):
        return abs(x) < 1700 and (abs(y) < 760 or abs(y - cross_y(x)) < 450)

    def query(self, x, y):
        out = []
        for r in self.roads:
            _co, i, d = r["kd"].find((x, y, 0.0))
            out.append((r, r["pts"][i], d))
        return out

    def h(self, x, y, want_far=False):
        ax = abs(x)
        yn = y if x >= 0 else -y
        pr = paved_right(yn) if Y_START < yn < Y_END else X_PAVED
        g_main = -0.15 if ax <= pr + 1.5 else -0.15 - (ax - pr - 1.5) * 0.077
        qs = self.query(x, y) if self.near(x, y) else []
        dmin = min([d for _r, _p, d in qs], default=1e9)
        base = self.W.ground_z(self.road, x, y)
        base = -0.8 + smooth5((dmin - 50.0) / 220.0) * (base + 0.8)
        g = max(base, g_main)
        caps = []
        for r, p, d in qs:
            z = p[2]
            bridge = r["kind"] == "cross" and abs(p[0]) < BRIDGE_HALF
            if bridge:
                z = BRIDGE_Z - (BRIDGE_HALF - abs(p[0])) / 1.5
            e = d - r["half"]
            g = max(g, z - 0.15 - max(0.0, e - 1.0) * 0.45)
            if e < 0.6 and not bridge:
                caps.append(p[2] - 0.12)
        for z in caps:
            g = min(g, z)
        if ax < pr + 0.3 and Y_START < yn < Y_END:
            g = min(g, -0.15)
        if not want_far:
            return g
        # fields from about 15 m beyond the road edge; meadow inside the interchange (60 m around the ramps)
        de = min([ax - pr] + [d - r["half"] for r, _p, d in qs if r["kind"] == "cross"])
        dr = min([d for r, _p, d in qs if r["kind"] == "ramp"], default=1e9)
        far = min(max(0.0, (de - 8.0) / 8.0), max(0.0, (dr - 60.0) / 25.0))
        return g, min(1.0, far)

    def edge_dist(self, x, y):
        """Distance from (x, y) to the nearest paved edge (negative on a road)."""
        ax = abs(x)
        yn = y if x >= 0 else -y
        pr = paved_right(yn) if Y_START < yn < Y_END else X_PAVED
        d = ax - pr if ax > 2.0 else -1.0
        for r, _p, dd in (self.query(x, y) if self.near(x, y) else []):
            d = min(d, dd - (r["half"] if r["kind"] == "cross" else 3.5))
        return d


# ------------------------------------------------------------------ material touches (this scene only)
def soften_patches(m, factor=0.9, threshold=0.93):
    """world.asphalt draws darker repair patches; seen from a driver's seat one can read as a shadow in the lane.
    Fewer and lighter patches here (the node tree of this scene's copy only; world.py is unchanged)."""
    for n in m.node_tree.nodes:
        if n.type == "MATH" and n.operation == "GREATER_THAN" and abs(n.inputs[1].default_value - 0.88) < 1e-6:
            n.inputs[1].default_value = threshold
        if n.type == "MIX" and getattr(n, "blend_type", "") == "MULTIPLY":
            for s in n.inputs:
                if s.type == "RGBA" and s.name == "B" and abs(s.default_value[0] - 0.7) < 1e-6:
                    s.default_value = (factor, factor, factor + 0.02, 1)


def grass_detail(m):
    """The landscape material's verge grass is one large-scale noise: add mid-scale clumps, October straw tones and
    a bump, so close shots read as grass rather than a flat plane."""
    nt = m.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    gnz = next(n for n in nt.nodes if n.type == "TEX_NOISE" and abs(n.inputs["Scale"].default_value - 0.05) < 1e-6)
    gr = next(lk.to_node for lk in gnz.outputs["Fac"].links if lk.to_node.type == "VALTORGB")
    tc = next(n for n in nt.nodes if n.type == "TEX_COORD")
    fine = nt.nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 1.6
    fine.inputs["Detail"].default_value = 8.0
    nt.links.new(tc.outputs["Object"], fine.inputs["Vector"])
    straw = nt.nodes.new("ShaderNodeValToRGB")
    straw.color_ramp.elements[0].position = 0.38
    straw.color_ramp.elements[0].color = (0.09, 0.2, 0.035, 1)
    straw.color_ramp.elements[1].position = 0.72
    straw.color_ramp.elements[1].color = (0.36, 0.38, 0.13, 1)
    nt.links.new(fine.outputs["Fac"], straw.inputs["Fac"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "OVERLAY"
    mix.inputs["Factor"].default_value = 0.65
    cols = [s for s in mix.inputs if s.type == "RGBA"]
    out = [s for s in mix.outputs if s.type == "RGBA"][0]
    target = [lk.to_socket for lk in gr.outputs["Color"].links]
    nt.links.new(gr.outputs["Color"], cols[0])
    nt.links.new(straw.outputs["Color"], cols[1])
    for s in target:
        nt.links.new(out, s)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bn = nt.nodes.new("ShaderNodeTexNoise")
    bn.inputs["Scale"].default_value = 9.0
    bn.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], bn.inputs["Vector"])
    nt.links.new(bn.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])


def tuft_library(lib, n=3, seed=31):
    """Grass tufts (thin blades) for close shots: n variants under lib_tufts (flora.scatter picks children)."""
    import random

    import world as W
    rnd = random.Random(seed)
    g = bpy.data.collections.new("lib_tufts")
    lib.children.link(g)
    mats = [W.noisy("tuft_a", (0.12, 0.24, 0.05), (0.3, 0.36, 0.1), 3.0, rough=0.8, coord="Object"),
            W.noisy("tuft_b", (0.22, 0.27, 0.08), (0.46, 0.42, 0.17), 3.0, rough=0.85, coord="Object")]
    for k in range(n):
        sub = bpy.data.collections.new(f"tuft{k}")
        g.children.link(sub)
        verts, faces = [], []
        for _b in range(rnd.randint(14, 22)):
            a = rnd.uniform(0, 2 * math.pi)
            r0 = rnd.uniform(0.0, 0.09)
            h = rnd.uniform(0.18, 0.46)
            lean = rnd.uniform(0.05, 0.22)
            w = rnd.uniform(0.012, 0.022)
            cx, cy = r0 * math.cos(a), r0 * math.sin(a)
            px, py = -math.sin(a) * w, math.cos(a) * w
            tx, ty = cx + math.cos(a) * lean, cy + math.sin(a) * lean
            i = len(verts)
            verts += [(cx - px, cy - py, 0.0), (cx + px, cy + py, 0.0), (tx, ty, h)]
            faces.append((i, i + 1, i + 2))
        W.mesh_obj(f"tuft{k}", verts, faces, mats[k % 2], sub)
    return g


def verge_tufts(G, lib, c, center, radius, spacing=0.7, seed=3, min_edge=1.7):
    """Scatter grass tufts on the ground within `radius` of `center` (x, y), not on roads or the Bankett."""
    import random

    import flora
    rnd = random.Random(seed)
    lib_t = bpy.data.collections.get("lib_tufts") or tuft_library(lib)
    pts = []
    cx, cy = center
    n = int(2 * radius / spacing)
    for j in range(n):
        for i in range(n):
            x = cx - radius + (i + rnd.random()) * spacing
            y = cy - radius + (j + rnd.random()) * spacing
            if (x - cx) ** 2 + (y - cy) ** 2 > radius * radius:
                continue
            if G.edge_dist(x, y) < min_edge:
                continue
            pts.append((x, y, G.h(x, y) + 0.02))
    print("tufts", len(pts), flush=True)
    return flora.scatter("tufts", pts, lib_t, c, 0.8, 1.5, seed=seed)


def _axis(lo, hi, bands):
    out, v = [], lo
    while v < hi:
        out.append(v)
        v += next(s for lim, s in bands if abs(v) < lim)
    out.append(hi)
    return out


def terrain(G, M, c, xr=16000.0, yr=16000.0):
    """One tensor grid: 3 to 4 m around the interchange, coarser outwards, 600 m cells out to 16 km so the horizon is
    hills in the haze, not the edge of the world."""
    import world as W
    xs = _axis(-xr, xr, [(160, 3.0), (480, 5.0), (1600, 15.0), (4000, 60.0), (1e9, 600.0)])
    ys = _axis(-yr, yr, [(650, 4.0), (2800, 12.0), (5000, 60.0), (1e9, 600.0)])
    nx = len(xs)
    verts, far = [], []
    for y in ys:
        for x in xs:
            g, f = G.h(x, y, want_far=True)
            verts.append((x, y, g))
            far.append(f)
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i)
             for j in range(len(ys) - 1) for i in range(nx - 1)]
    o = W.mesh_obj("terrain", verts, faces, None, c)
    attr = o.data.color_attributes.new("far", "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", [v for f in far for v in (f, f, f, 1.0)])
    o.data.polygons.foreach_set("use_smooth", [True] * len(faces))
    mat = W.fields_material(M)
    grass_detail(mat)
    o.data.materials.append(mat)
    print("terrain", nx, "x", len(ys), flush=True)
    return o


def village(G, houses, church, c, x, y, n=36, radius=140.0, seed=1):
    """world.village on our ground (the episode 1 house library)."""
    import random

    import world as W
    rnd = random.Random(seed)
    rot0 = rnd.uniform(0, math.pi)
    kids = list(houses.children)
    for _k in range(n):
        a = rnd.uniform(0, 2 * math.pi)
        r = radius * math.sqrt(rnd.random())
        px, py = x + math.cos(a) * r, y + math.sin(a) * r
        W.instance(rnd.choice(kids), (px, py, G.h(px, py) - 0.4),
                   rz=rot0 + rnd.choice((0, math.pi / 2)) + rnd.uniform(-0.15, 0.15), c=c)
    W.instance(church, (x, y, G.h(x, y) - 0.4), rz=rot0, c=c)


def vegetation(G, groups, c, xr=1900.0, yr=2900.0, spacing=7.0, seed=5, exclude=()):
    import random

    import flora
    rnd = random.Random(seed)
    forest, conif, bushes, roadside = [], [], [], []
    for j in range(int(2 * yr / spacing)):
        for i in range(int(2 * xr / spacing)):
            x = -xr + (i + rnd.random()) * spacing
            y = -yr + (j + rnd.random()) * spacing
            ax = abs(x)
            if ax < 27 or any((x - ex) ** 2 + (y - ey) ** 2 < er * er for ex, ey, er in exclude):
                continue
            qs = G.query(x, y) if G.near(x, y) else []
            de = min([ax - 18.0] + [d - r["half"] for r, _p, d in qs])
            if de < 9.0:
                continue
            n1 = noise.noise(Vector((x / 380, y / 380, 4.2)))
            n2 = noise.noise(Vector((x / 90, y / 90, 7.1)))
            if de < 40:
                if n2 > 0.18 and rnd.random() < 0.8:
                    (bushes if (rnd.random() < 0.55 or de < 14) else roadside).append((x, y, G.h(x, y) - 0.3))
                continue
            pick = None
            if n1 > 0.18:
                pick = conif if n1 > 0.32 else forest
            elif (n1 > 0.1 and rnd.random() < 0.25) or rnd.random() < 0.004:
                pick = forest
            if pick is not None:
                pick.append((x, y, G.h(x, y) - 0.3))
    print("vegetation", len(forest), len(conif), len(roadside), len(bushes), flush=True)
    return [flora.scatter("forest", forest, groups["decid"], c, 0.9, 1.5, seed=1),
            flora.scatter("conifers", conif, groups["conif"], c, 0.8, 1.2, seed=4),
            flora.scatter("roadside", roadside, groups["decid"], c, 0.7, 1.1, seed=7),
            flora.scatter("bushes", bushes, groups["bush"], c, 0.7, 1.3, seed=9)]


VILLAGES = [(-620, -1500, 150, 2), (680, 950, 130, 5), (-760, 1900, 160, 8), (1250, 470, 120, 11)]
TURBINES = [(620, -900), (780, -620), (560, -1250), (-700, 300), (-900, 650), (820, 1500), (-560, -2200),
            (1100, -1800)]


def build(assets, fleet=True, landscape=True, show_300=False, signs=True):
    """Build the whole interchange scene (factory-fresh file). Returns a dict: road, M, lib, env, traffic, fleet
    ({model name: collection}), net, ground, builder (objects, signs, posts), ramps, nose_y."""
    import flora
    import stage
    import world as W
    bpy.ops.wm.read_factory_settings(use_empty=True)
    W.setup(assets, None)
    lib = W.coll("lib")
    env = W.coll("env")
    traffic = W.coll("traffic")
    models = {}
    if fleet:      # vehicles first: building them in a full scene is slow (reports/vehicles.md)
        cars, vans, trucks = stage.fleet(lib)
        models = {**cars, **vans, **trucks}
    road = W.Road(length=Y_END - Y_START, bends=(), crest=(), origin=(0.0, Y_START, 0.0))
    M = W.Mats()
    B = Builder(assets, M, env, lib, load_net())
    for m in (M.asph, M.asph_sh, B.asph_ramp):
        soften_patches(m)
    if signs:
        B.SG.setup(assets)
    B.ramp_lines()
    B.find_noses()
    for sg in (1, -1):
        B.main_line(sg)
    B.median()
    for sg in (1, -1):
        for kind in ("exit", "entry"):
            B.ramp(sg, kind)
            B.gore(sg, kind)
    B.crossing()
    B.bridge()
    G = Ground(road, B.ramps, B.cross)
    for sg in (1, -1):    # guardrails on the outer side of raised ramp sections
        cl = B.ramps[sg]["exit"]
        B.rail_along("rail_exit", sg, cl, RAMP_LR + RAMP_SR + 0.5,
                     lambda i, cl=cl: cl.pts[i][2] > 2.0 and cl.s[i] < cl.L - 25)
        cl = B.ramps[sg]["entry"]
        B.rail_along("rail_loop", sg, cl, -(RAMP_LL + RAMP_SL + 0.5),
                     lambda i, cl=cl: cl.pts[i][2] > 2.0 and cl.s[i] > 25)
    cc = B.cross
    for side in (1, -1):  # crossing road on its embankment, not at the ramp mouths
        a, b = (J_LOOP_X - 14, J_EXIT_X + 14) if side > 0 else (-J_EXIT_X - 14, -J_LOOP_X + 14)
        B.rail_along("rail_cross", 1, cc, side * (CROSS_PAVED + 0.5),
                     lambda i, a=a, b=b: (cc.pts[i][2] > 2.0 and abs(cc.pts[i][0]) > BRIDGE_HALF + 1
                                          and not a < cc.pts[i][0] < b))
    B.leitpfosten()
    RD = W.rail_delineator(M, lib)
    y = math.floor(Y_START / LP_SPACING) * LP_SPACING + 10.0
    while y < Y_END:
        W.instance(RD, (0.0, y, 0.0), c=env)
        y += LP_SPACING
    for sg in (1, -1):
        B.place_posts(sg)
        if signs:
            B.place_signs(sg, G.h, show_300=show_300)
    if landscape:
        terrain(G, M, env)
        HG, CH = W.house_library(lib, M)
        for vx, vy, vr, seed in VILLAGES:
            village(G, HG, CH, env, vx, vy, n=int(vr / 4), radius=vr, seed=seed)
        groups = flora.library(lib)
        vegetation(G, groups, env, exclude=[(vx, vy, vr + 25) for vx, vy, vr, _s in VILLAGES])
        TB, _rot = W.wind_turbine(M, lib)
        for k, (tx, ty) in enumerate(TURBINES):
            W.instance(TB, (tx, ty, G.h(tx, ty) - 1.0), rz=math.radians(200 + k * 3), c=env)
    return dict(road=road, M=M, lib=lib, env=env, traffic=traffic, fleet=models, net=B.net, ground=G, builder=B,
                ramps=B.ramps, nose_y=B.nose_y)
