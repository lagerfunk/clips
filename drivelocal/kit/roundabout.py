"""German Kreisverkehr for the junction kit: a single-lane town roundabout and a two-lane one, built to the FGSV
Merkblatt fuer die Anlage von Kreisverkehren (2006) as quoted by Hessen Mobil (Leitfaden Qualitaetssicherung
Kreisverkehre 2013), the Forum Verlag excerpt of the Merkblatt tables and the KIT colloquium slides (sources and pages
in reports/junctions.md). Same look as the approved town kit (asphalt, Hochbord, cobble gutters, paver footways,
houses, hedges, farmland). Arms on the axes (S, E, N, W); right-hand traffic, anticlockwise circulation.

single (kleiner Kreisverkehr innerorts):
  D 30 m (Regelwert innerorts 30 to 35 m), Kreisfahrbahn Bk 8.00 m at D 30 (Merkblatt table) = 6.50 m asphalt (the
  table's car-only width, Bk at D 40) plus a 1.50 m overrunnable Innenring of granite setts, ring edge a Flachbord
  4 cm high (Hessen 3 to 4 cm, Merkblatt 4 to 6 cm), central island 14 m with Hochbord. Entry lane 3.50 m (3.25 to 3.75), exit 4.00 m
  (3.50 to 4.00), corner radii entry 12 m (10 to 14), exit 14 m (12 to 16). Splitter island 2.50 m (at least 2.00 m
  where pedestrians cross), Schraegbord 0.12 m. Zebra (Zeichen 293, 0.50 m strips and gaps, 4.00 m long) on every
  arm, its near edge 4.50 m from the circle (4 to 5 m), Zeichen 350-10 at each side.
two_lane (kleiner Kreisverkehr mit zweistreifig befahrbarer Kreisfahrbahn):
  D 50 m (innerorts minimum 40, Regelwert 50), Bk 8.00 m (8 to 10), no Innenring, island not overrunnable (Flachbord),
  two-lane entries 2 x 3.25 m, single-lane exits 4.00 m, the two circulating lanes NOT marked, no lane arrows (the
  Merkblatt marks neither), no zebra (Fussgaengerueberwege unzulaessig at two-lane entries): an unmarked crossing
  through the splitter island 4.50 m back.
Both: Zeichen 205 over Zeichen 215 on every entry (two-lane: repeated on the splitter island), Zeichen 222 on the
splitter island head, the circle edge across every entry and exit as a broken Breitstrich 0.25 m, 1.5 m dash, 1.5 m
gap (Hessen Arbeitsblatt 13), the inner edge of the circulating carriageway Zeichen 295 (0.12 m).

    import roundabout as RB
    S = RB.build(ASSETS, kind="single", seed=4, heroes=[("hatch", (0.5, 0.03, 0.02), "carA", "WI LK 204", 0.3)])
    P = S["lane_path"]("S", "N", 0)                 # jx.Path subclass with .s_yield, .s_indicate, ...
    sv = jx.kinematics(0.0, 8.0, [(0, "cruise", 8.0), (2.0, "stop", P.stop_s(4.28, P.s_yield))], 300)
"""
import math
import random

import bpy
from mathutils import Vector

import jx
import junctions as JN
import town as TN
import world as W

ARMS = ("S", "E", "N", "W")
NEXT_CCW = {"S": "E", "E": "N", "N": "W", "W": "S"}
L_PATH = 95.0

SPEC = {
    "single": dict(D=30.0, Bk=8.0, ring=1.5, ring_h=0.04, island_kerb_h=0.15, lanes_in=1, Bz=3.50, Ba=4.00, Rz=12.0,
                   Ra=14.0, split_w=2.50, split_kerb_h=0.12, crossing="zebra", cross_off=4.50, cross_w=4.00,
                   we_far=3.25, wx_far=3.25, flare=(25.0, 45.0), tip=36.0, taper0=28.0, h_tip=0.40,
                   tracks=(12.0,), r_entry=10.0, r_exit=12.0,
                   lane_bp=([(25.0, 3.0), (45.0, 1.625)],), exit_bp=[(25.0, -3.25), (45.0, -1.625)], lane_line=None),
    "two_lane": dict(D=50.0, Bk=8.0, ring=0.0, ring_h=0.0, island_kerb_h=0.05, lanes_in=2, Bz=3.25, Ba=4.00, Rz=14.0,
                     Ra=16.0, split_w=3.00, split_kerb_h=0.12, crossing="plain", cross_off=4.50, cross_w=3.00,
                     we_far=3.25, wx_far=3.25, flare=(45.0, 70.0), tip=62.0, taper0=45.0, h_tip=0.45,
                     tracks=(23.0, 19.0), r_entry=12.0, r_exit=14.0,
                     lane_bp=([(48.0, 6.375), (66.0, 1.625)], [(45.0, 3.125), (70.0, 1.625)]),
                     exit_bp=[(45.0, -3.5), (70.0, -1.625)], lane_line=([(45.0, 4.75), (70.0, 3.25)], 52.0)),
}
KREISRAND = dict(width=JN.BROAD, dash=1.5, gap=1.5)
INNER_EDGE = dict(width=JN.NARROW)
ZEBRA = dict(strip=0.50, gap=0.50)


def mats(T):
    if not hasattr(T, "setts"):
        T.setts = TN.brick("setts_granite", (0.33, 0.33, 0.32), (0.44, 0.43, 0.41), (0.13, 0.13, 0.13), 1.0,
                           mortar_size=0.02, row_h=0.11, brick_w=0.11, bump=0.4, var=0.4, rough=0.85)
        T.setts_light = TN.brick("setts_light", (0.55, 0.55, 0.53), (0.66, 0.65, 0.62), (0.3, 0.3, 0.29), 1.0,
                                 mortar_size=0.02, row_h=0.16, brick_w=0.16, bump=0.3, var=0.3, rough=0.8)
    return T


class Geo:
    """All roundabout numbers and the analytic kerb and island shapes (arm frame: u out along the arm, v to the right
    of inbound traffic)."""

    def __init__(self, kind):
        if kind not in SPEC:
            raise ValueError(f"kind must be one of {list(SPEC)}")
        self.kind = kind
        self.__dict__.update(SPEC[kind])
        self.Ro = self.D / 2
        self.r_in = self.Ro - self.Bk                      # inner edge of the Kreisfahrbahn (incl. Innenring)
        self.r_asph = self.r_in + self.ring                # inner edge of the asphalt
        self.h = self.split_w / 2
        self.we = self.h + self.Bz * self.lanes_in         # entry kerb at the circle
        self.wx = self.h + self.Ba                         # exit kerb at the circle
        self.ce = self._fillet(self.Ro, self.we, self.Rz)  # (u, v) of the kerb fillet centres
        self.cx = self._fillet(self.Ro, self.wx, self.Ra)
        self.th_e = math.atan2(self.ce[1], self.ce[0])     # circle tangent angles from the arm axis
        self.th_x = math.atan2(self.cx[1], self.cx[0])
        self.r_line = self.Ro - TN.GUTTER - KREISRAND["width"] / 2
        self.u_cross0 = self.Ro + self.cross_off           # crossing near edge
        self.u_cross1 = self.u_cross0 + self.cross_w
        self.u_nose = self.Ro + 0.8

    @staticmethod
    def _fillet(r_circle, w, rf):
        vc = w + rf
        return (math.sqrt((r_circle + rf) ** 2 - vc ** 2), vc)

    def w_entry(self, u):
        return JN.interp([(self.flare[0], self.we), (self.flare[1], self.we_far)], u, smooth=True)

    def w_exit(self, u):
        return JN.interp([(self.flare[0], self.wx), (self.flare[1], self.wx_far)], u, smooth=True)

    def kerb_v(self, side, u):
        """Lateral of the kerb face at u (entry side positive, exit side negative), valid for u >= the circle
        tangent."""
        if side > 0:
            cu, cv, rf, wf = self.ce[0], self.ce[1], self.Rz, self.w_entry
        else:
            cu, cv, rf, wf = self.cx[0], self.cx[1], self.Ra, self.w_exit
        if u >= cu:
            v = wf(u)
        else:
            v = cv - math.sqrt(max(0.0, rf * rf - (u - cu) ** 2))
        return v if side > 0 else -v

    def h_split(self, u):
        if u <= self.taper0:
            return self.h
        return JN.interp([(self.taper0, self.h), (self.tip, self.h_tip)], u)

    def lane_v(self, lane, u):
        """Centre of entry lane `lane` (0 = right/outer) at u: h + Bz * (lanes - lane - 0.5) near the circle."""
        return JN.interp(self.lane_bp[lane], u, smooth=True)

    def exit_v(self, u):
        return JN.interp(self.exit_bp, u, smooth=True)

    def numbers(self):
        return dict(kind=self.kind, D=self.D, Ro=self.Ro, Bk=self.Bk, ring=self.ring, ring_h=self.ring_h,
                    asphalt=self.Ro - self.r_asph, island_d=2 * self.r_in, lanes_in=self.lanes_in, Bz=self.Bz,
                    Ba=self.Ba, Rz=self.Rz, Ra=self.Ra, split_w=self.split_w, split_kerb_h=self.split_kerb_h,
                    island_kerb_h=self.island_kerb_h, crossing=self.crossing, cross_off=self.cross_off,
                    cross_w=self.cross_w, split_len=self.tip - self.u_nose, kreisrand=dict(KREISRAND),
                    inner_edge=dict(INNER_EDGE), zebra=dict(ZEBRA) if self.crossing == "zebra" else None,
                    tracks=self.tracks, kerb_h=TN.KERB_H, footway=TN.FOOT, gutter=TN.GUTTER)


# ------------------------------------------------------------------ outlines
def _dedupe(P, eps=1e-4):
    out = []
    for p in P:
        if not out or (p - out[-1]).length > eps:
            out.append(p)
    return out


def _arc_pts(c, r, a0, a1, step=0.4):
    n = max(2, int(abs(a1 - a0) * r / step))
    return [Vector((c.x + r * math.cos(a0 + (a1 - a0) * k / n), c.y + r * math.sin(a0 + (a1 - a0) * k / n)))
            for k in range(n + 1)]


def _ang(p):
    return math.atan2(p.y, p.x)


def _short(a0, a1):
    return a0 + (a1 - a0 + math.pi) % (2 * math.pi) - math.pi


def block_kerb(g, A, L):
    """Kerb of the block between arm A (its entry side) and the next arm anticlockwise (its exit side), ordered so
    the road is on the right: in along B's exit side, round the circle clockwise, out along A's entry side."""
    B = NEXT_CCW[A]
    P = []
    us = [L, 160.0, 100.0] + [g.flare[1] - (g.flare[1] - g.flare[0]) * k / 16 for k in range(17)]
    for u in us:
        if u > g.cx[0]:
            P.append(JN.arm_pt(B, u, -g.w_exit(u)))
    P.append(JN.arm_pt(B, g.cx[0], -g.wx))
    cB = JN.arm_pt(B, g.cx[0], -g.cx[1])
    tB = cB * (g.Ro / (g.Ro + g.Ra))
    a0 = _ang(JN.arm_pt(B, g.cx[0], -g.wx) - cB)
    P += _arc_pts(cB, g.Ra, a0, _short(a0, _ang(tB - cB)))
    cA = JN.arm_pt(A, g.ce[0], g.ce[1])
    tA = cA * (g.Ro / (g.Ro + g.Rz))
    aB, aA = _ang(tB), _ang(tA)
    span = (aB - aA) % (2 * math.pi)
    P += _arc_pts(Vector((0, 0)), g.Ro, aB, aB - span)
    a0 = _ang(tA - cA)
    P += _arc_pts(cA, g.Rz, a0, _short(a0, _ang(JN.arm_pt(A, g.ce[0], g.we) - cA)))
    for u in reversed(us):
        if u > g.ce[0]:
            P.append(JN.arm_pt(A, u, g.w_entry(u)))
    return _dedupe(P)


def _cap(p_end, d_out, half, n=10):
    """Half circle from the right edge round the end to the left edge (frame: d_out points away from the body)."""
    nrm = Vector((-d_out.y, d_out.x))
    c = p_end - d_out * half
    return [c + (-nrm * math.cos(math.pi * k / n) + d_out * math.sin(math.pi * k / n)) * half for k in range(n + 1)]


def island_piece(g, arm, u0, u1, round_near=0.6, round_far=0.3, tip=False):
    """Splitter island part between u0 < u1 as an anticlockwise loop in world coordinates: the exit-side edge
    (v < 0) outward, the far end (a round nose when tip), the entry-side edge back, the rounded near end."""
    hf = g.h_split(u1)
    ue = u1 - hf if tip else u1
    n = max(2, int((ue - u0) / 0.6))
    us = [u0 + (ue - u0) * k / n for k in range(n + 1)]
    r0 = min(round_near, g.h_split(u0) * 0.9)
    qa = [math.pi / 2 * k / 4 for k in range(5)]
    near_l = [(u0 + r0 - r0 * math.sin(t), g.h_split(u0) - r0 + r0 * math.cos(t)) for t in qa]
    near_r = [(u0 + r0 - r0 * math.cos(t), -g.h_split(u0) + r0 - r0 * math.sin(t)) for t in qa]
    right = [(u, -g.h_split(u)) for u in us if u > u0 + r0 + 0.05]
    left = [(u, g.h_split(u)) for u in reversed(us) if u > u0 + r0 + 0.05]
    if tip:
        cap = _cap(Vector((u1, 0.0)), Vector((1, 0)), hf)
        far = [(p.x, p.y) for p in cap]
        right = [p for p in right if p[0] < ue - 0.05]
        left = [p for p in left if p[0] < ue - 0.05]
    else:
        r1 = min(round_far, hf * 0.9)
        far = [(u1 - r1 + r1 * math.sin(t), -hf + r1 - r1 * math.cos(t)) for t in qa]
        far += [(u1 - r1 + r1 * math.cos(t), hf - r1 + r1 * math.sin(t)) for t in qa]
        right = [p for p in right if p[0] < u1 - r1 - 0.05]
        left = [p for p in left if p[0] < u1 - r1 - 0.05]
    uv = near_r + right + far + left + near_l
    pts = _dedupe([JN.arm_pt(arm, u, v) for u, v in uv])
    if (pts[0] - pts[-1]).length < 1e-4:
        pts.pop()
    return pts


def circle_loop(r, n=192):
    return [Vector((r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n))) for k in range(n)]


# ------------------------------------------------------------------ the roundabout surfaces
class Roundabout:
    def __init__(self, T, c, kind="single", L=240.0):
        self.T, self.c, self.L = mats(T), c, L
        self.g = Geo(kind)
        self.kind = kind
        self.kerbs = {}
        self.islands = {}
        self.objs = {}
        self.build()

    def build(self):
        T, c, L, g = self.T, self.c, self.L, self.g
        W.mesh_obj("asphalt", [(-L, -L, 0), (L, -L, 0), (L, L, 0), (-L, L, 0)], [(0, 1, 2, 3)], T.asph, c,
                   uvs=[(-L, -L), (L, -L), (L, L), (-L, L)])
        for A in ARMS:
            P = block_kerb(g, A, L)
            self.kerbs[A] = P
            dA, _ = JN.arm_frame(A)
            dB, _ = JN.arm_frame(NEXT_CCW[A])
            JN.kerb_block(T, c, P, [dA * L + dB * L], name="block_" + A)
        self.central()
        for A in ARMS:
            self.splitter(A)

    def central(self):
        T, c, g = self.T, self.c, self.g
        if g.ring > 0:
            # Innenring: Flachbord (4 cm) at the asphalt edge, granite setts, then the island Hochbord
            P = circle_loop(g.r_asph)
            fb = JN.loop_sweep("ring_flachbord", P, [(0.0, 0.0), (0.0, g.ring_h - 0.01), (0.012, g.ring_h),
                                                     (TN.KERB_W, g.ring_h)], T.curb, c)
            fb["role"] = "ring_edge"
            st = JN.loop_strip("innenring", P, TN.KERB_W, g.ring, g.ring_h, g.ring_h, T.setts, c)
            st["role"] = "innenring"
            TN.uv_world(st)
            Pi = circle_loop(g.r_in)
            z0, hk = g.ring_h, g.island_kerb_h
            k = JN.loop_sweep("island_kerb", Pi, [(0.0, z0), (0.0, z0 + hk - 0.02), (0.02, z0 + hk),
                                                  (TN.KERB_W, z0 + hk)], T.curb, c)
            k["role"] = "island_kerb"
            top = z0 + hk
            JN.flat_poly("island_lawn", JN.offset_loop(Pi, TN.KERB_W), top + 0.002, T.lawn, c)
            bed = JN.loop_strip("island_bed", JN.offset_loop(Pi, TN.KERB_W), 0.5, 2.1, top + 0.006, top + 0.006,
                                T.bed, c)
            TN.uv_world(bed)
            self.island_top = top
        else:
            P = circle_loop(g.r_in)
            hk = g.island_kerb_h
            k = JN.loop_sweep("island_flachbord", P, [(0.0, 0.0), (0.0, hk - 0.01), (0.012, hk), (0.18, hk)],
                              T.curb, c)
            k["role"] = "island_kerb"
            band = JN.loop_strip("island_band", P, 0.18, 0.9, hk, hk + 0.01, T.setts_light, c)
            TN.uv_world(band)
            self.island_top = hk
            self.mound(JN.offset_loop(P, 0.9), g.r_in - 0.9, hk + 0.01, 1.3)

    def mound(self, ring_pts, r0, z0, hmax, nr=10):
        """Low grassed mound on the two-lane island (keeps the view across the circle short, no rigid obstacles)."""
        verts, faces = [], []
        n = len(ring_pts)
        for j in range(nr):
            k = j / nr
            z = z0 + hmax * (0.5 - 0.5 * math.cos(math.pi * min(1.0, k * 1.6)))
            for p in ring_pts:
                verts.append((p.x * (1 - k), p.y * (1 - k), z))
        verts.append((0.0, 0.0, z0 + hmax))
        for j in range(nr - 1):
            for i in range(n):
                a, b = j * n + i, j * n + (i + 1) % n
                faces.append((a, b, b + n, a + n))
        cidx = len(verts) - 1
        for i in range(n):
            faces.append(((nr - 1) * n + i, (nr - 1) * n + (i + 1) % n, cidx))
        o = W.mesh_obj("island_mound", verts, faces, self.T.lawn, self.c, smooth=True)
        for poly in o.data.polygons:
            if poly.normal.z < 0:
                poly.flip()
        TN.uv_world(o)
        o["role"] = "mound"
        return o

    def splitter(self, A):
        T, c, g = self.T, self.c, self.g
        hk = g.split_kerb_h
        prof = [(0.0, 0.0), (0.0, 0.04), (0.08, hk), (TN.KERB_W, hk)]
        pieces = [(g.u_nose, g.u_cross0, False), (g.u_cross1, g.tip, True)]
        self.islands[A] = []
        for k, (u0, u1, tip) in enumerate(pieces):
            P = island_piece(g, A, u0, u1, tip=tip)
            self.islands[A].append(P)
            kk = JN.loop_sweep(f"split_{A}{k}_kerb", P, prof, T.curb, c)
            kk["role"] = "split_kerb"
            JN.flat_poly(f"split_{A}{k}_top", JN.offset_loop(P, TN.KERB_W), hk, T.setts, c)
        # the crossing through the island at road level (lowered, pavers)
        q = [JN.arm_pt(A, g.u_cross0 + 0.05, -g.h), JN.arm_pt(A, g.u_cross1 - 0.05, -g.h),
             JN.arm_pt(A, g.u_cross1 - 0.05, g.h), JN.arm_pt(A, g.u_cross0 + 0.05, g.h)]
        JN.flat_poly(f"split_{A}_crossing", q, 0.02, T.pavers, c)


# ------------------------------------------------------------------ markings and signs
def markings(R):
    T, c, g = R.T, R.c, R.g
    out = {"kreisrand": [], "inner_edge": None, "zebra": [], "centre": [], "lane": [], "sperr": []}
    for A in ARMS:
        a = JN.ARM_ANGLE[A]
        arc = _arc_pts(Vector((0, 0)), g.r_line, a - g.th_x, a + g.th_e, step=0.2)
        o = JN.paint_along(T, c, arc, KREISRAND["width"], dash=KREISRAND["dash"], gap=KREISRAND["gap"], phase=0.25,
                           name="kreisrand_" + A, role="kreisrand")
        o["arm"] = A
        out["kreisrand"].append(o)
    o = JN.paint_along(T, c, circle_loop(g.r_asph + 0.06 + INNER_EDGE["width"] / 2 + (0.25 if g.ring == 0 else 0.0)),
                       INNER_EDGE["width"], closed=True, name="inner_edge", role="inner_edge")
    out["inner_edge"] = o
    for A in ARMS:
        # solid line from the island tip outward, then the Leitlinie
        tip_line = [JN.arm_pt(A, g.tip - 0.2, 0.0), JN.arm_pt(A, g.tip + 12.0, 0.0)]
        out["sperr"].append(JN.paint_along(T, c, tip_line, JN.NARROW, name="sperr_" + A, role="sperrlinie"))
        out["centre"].append(JN.paint_along(T, c, [JN.arm_pt(A, g.tip + 15.0, 0.0), JN.arm_pt(A, 150.0, 0.0)],
                                            JN.NARROW, dash=JN.LEIT_DASH, gap=JN.LEIT_GAP, name="centre_" + A,
                                            role="leitlinie"))
        if g.lane_line:
            # line between the two entry lanes, from the circle edge to where the flare closes; dashes 1:1 (3 m / 3 m)
            # as at junctions (road_spec section 6)
            bp, u_end = g.lane_line
            us = [g.Ro + 0.6 + k * 0.5 for k in range(int((u_end - g.Ro - 0.6) / 0.5) + 1)]
            pts = [JN.arm_pt(A, u, JN.interp(bp, u, smooth=True)) for u in us]
            o = JN.paint_along(T, c, pts, JN.NARROW, dash=3.0, gap=3.0, name="lane_" + A, role="lane")
            o["arm"] = A
            out["lane"].append(o)
        if g.crossing == "zebra":
            for side in (1, -1):
                lo = g.h + 0.25
                hi = min(abs(g.kerb_v(side, u)) for u in (g.u_cross0, g.u_cross1, (g.u_cross0 + g.u_cross1) / 2))
                hi -= TN.GUTTER + 0.1
                n = int((hi - lo + ZEBRA["gap"]) / (ZEBRA["strip"] + ZEBRA["gap"]))
                tot = n * ZEBRA["strip"] + (n - 1) * ZEBRA["gap"]
                v0 = lo + (hi - lo - tot) / 2
                quads = []
                for k in range(n):
                    va = v0 + k * (ZEBRA["strip"] + ZEBRA["gap"])
                    vb = va + ZEBRA["strip"]
                    quads.append([JN.arm_pt(A, g.u_cross0, side * va), JN.arm_pt(A, g.u_cross1, side * va),
                                  JN.arm_pt(A, g.u_cross1, side * vb), JN.arm_pt(A, g.u_cross0, side * vb)])
                o = JN.paint_quads(T, c, quads, name=f"zebra_{A}{'in' if side > 0 else 'out'}", role="zebra")
                o["arm"], o["side"], o["strips"] = A, side, n
                out["zebra"].append(o)
    return out


def signs(R, records):
    """Commons signs only (kit/signs.py): 205 over 215 on every entry, 222 on every splitter island head, 350-10 at
    both sides of every zebra (single) and the 205/215 repeat on the island of two-lane entries."""
    c, g = R.c, R.g
    z = TN.KERB_H
    for A in ARMS:
        d, _n = JN.arm_frame(A)
        rz_in = TN.facing((-d.x, -d.y))
        rz_out = TN.facing((d.x, d.y))
        u = g.u_cross1 + 4.0
        v = g.kerb_v(1, u) + JN.SIGN_BACK
        p = JN.arm_pt(A, u, v)
        JN.sign_stack(records, [("205", JN.SIZE["triangle"]), ("215", JN.SIZE["round"])], c, (p.x, p.y, z), rz_in,
                      name="rb_entry_" + A, arm=A, role="entry", side="right")
        if g.lanes_in == 2:
            p = JN.arm_pt(A, u + 1.5, 0.0)
            JN.sign_stack(records, [("205", JN.SIZE["triangle"]), ("215", JN.SIZE["round"])], c,
                          (p.x, p.y, g.split_kerb_h), rz_in, name="rb_entry_isl_" + A, arm=A, role="entry",
                          side="island")
        p = JN.arm_pt(A, g.tip - 0.9, 0.0)
        JN.sign_stack(records, [("222", JN.SIZE["round"])], c, (p.x, p.y, g.split_kerb_h), rz_in,
                      bottom=JN.ISLAND_BOTTOM + 0.4, name="rb_keepright_" + A, arm=A, role="keep_right",
                      side="island")
        if g.crossing == "zebra":
            u = g.u_cross1 + 0.4
            p = JN.arm_pt(A, u, g.kerb_v(1, u) + JN.SIGN_BACK)
            JN.sign_stack(records, [("350-10", JN.SIZE["square"])], c, (p.x, p.y, z), rz_in, name="rb_zebra_in_" + A,
                          arm=A, role="zebra", side="right")
            u = g.u_cross0 - 0.4
            p = JN.arm_pt(A, u, g.kerb_v(-1, u) - JN.SIGN_BACK)
            JN.sign_stack(records, [("350-10", JN.SIZE["square"])], c, (p.x, p.y, z), rz_out,
                          name="rb_zebra_out_" + A, arm=A, role="zebra_exit", side="right")
    return records


# ------------------------------------------------------------------ lane paths
def lane_path(entry, exit_, lane=0, kind="single", L=L_PATH, exit_from="outer", step=0.4):
    """Path FROM arm `entry` (the car drives in towards the centre) round the circle anticlockwise and out on arm
    `exit_` (entry == exit_ is a full U-turn). lane: entry lane, 0 = right (outer); on the two-lane roundabout lane 1
    enters on the left and circulates on the inner track, then (exit_from='outer', the taught way) moves to the
    outer track before its exit, or leaves straight from the inner track (exit_from='inner'). Arc length 0 is L metres
    out on the entry arm. Attributes: s_yield (front crosses the give-way line), s_cross_in / s_cross_out (crossings),
    s_circle_in, s_circle_out, s_indicate (right indicator on, only when leaving), exits_passed, turn."""
    g = Geo(kind)
    if entry not in ARMS or exit_ not in ARMS:
        raise ValueError("arms are S, E, N, W")
    if not 0 <= lane < g.lanes_in:
        raise ValueError(f"{kind} has {g.lanes_in} entry lane(s)")
    if lane > 0 and turn_of_arms(entry, exit_) == 1:
        raise ValueError("the first exit (right turn) is taken from the right lane")
    r_in = g.tracks[lane]
    r_out = g.tracks[0] if (lane == 0 or exit_from == "outer") else g.tracks[lane]
    ve = g.lane_v(lane, g.flare[0])
    vx = g.exit_v(g.flare[0])
    rf_e, rf_x = g.r_entry, g.r_exit
    ue = math.sqrt((r_in + rf_e) ** 2 - (ve + rf_e) ** 2)
    ux = math.sqrt((r_out + rf_x) ** 2 - (-vx + rf_x) ** 2)
    pts = []
    n_far = int((L - ue) / step)
    for k in range(n_far + 1):
        u = L - (L - ue) * k / n_far
        pts.append(JN.arm_pt(entry, u, g.lane_v(lane, u)))
    s_marks = {}
    cE = JN.arm_pt(entry, ue, ve + rf_e)
    tE = cE * (r_in / (r_in + rf_e))
    a0 = _ang(pts[-1] - cE)
    pts += _arc_pts(cE, rf_e, a0, _short(a0, _ang(tE - cE)), step)[1:]
    cX = JN.arm_pt(exit_, ux, vx - rf_x)
    tX = cX * (r_out / (r_out + rf_x))
    a_in, a_out = _ang(tE), _ang(tX)
    span = (a_out - a_in) % (2 * math.pi)
    if entry == exit_ and span < math.pi:
        span += 2 * math.pi
    if turn_of_arms(entry, exit_) == 1 and span > 1.5 * math.pi:
        raise ValueError("right turn geometry does not close")
    n = max(4, int(span * r_in / step))
    for k in range(1, n + 1):
        a = a_in + span * k / n
        to_end = (span - span * k / n)
        w = 1.0 - min(1.0, max(0.0, (to_end - math.radians(12)) / math.radians(48)))
        w = w * w * (3 - 2 * w)
        r = r_in + (r_out - r_in) * w
        pts.append(Vector((r * math.cos(a), r * math.sin(a))))
    b0 = _ang(tX - cX)
    b1 = _short(b0, _ang(JN.arm_pt(exit_, ux, vx) - cX))
    pts += _arc_pts(cX, rf_x, b0, b1, step)[1:]
    n_far = int((L - ux) / step)
    for k in range(1, n_far + 1):
        u = ux + (L - ux) * k / n_far
        pts.append(JN.arm_pt(exit_, u, g.exit_v(u)))
    pts = _dedupe(pts)
    turn_k = int(round(((JN.ARM_ANGLE[exit_] - JN.ARM_ANGLE[entry]) % (2 * math.pi)) / (math.pi / 2))) % 4
    P = JN.LanePath(pts, entry=entry, exit=exit_, lane=lane, kind=kind, L=L, exit_from=exit_from,
                    exits_passed=(turn_k - 1) % 4 if turn_k else 3,
                    turn={1: "right", 2: "straight", 3: "left", 0: "u"}[turn_k],
                    r_track=(r_in, r_out))
    P.s_yield = P.s_first(lambda p: p.length <= g.Ro - TN.GUTTER)
    P.s_circle_in = P.s_first(lambda p: p.length <= g.Ro - 0.5)
    P.s_circle_out = P.s_last(lambda p: p.length <= g.Ro - 0.5)
    P.s_cross_in = P.s_first(lambda p: JN.to_arm(entry, p)[0] <= g.u_cross1)
    P.s_cross_out = P.s_first(lambda p: JN.to_arm(exit_, p)[0] >= g.u_cross0 and p.length > g.Ro,
                              start=P.s_circle_out or 0.0)
    P.s_indicate = max(P.s_circle_in, P.s_circle_out - 0.5 * math.pi / 2 * g.tracks[0])
    P.meta.update(s_yield=P.s_yield, s_circle_in=P.s_circle_in, s_circle_out=P.s_circle_out)
    return P


def turn_of_arms(entry, exit_):
    return int(round(((JN.ARM_ANGLE[exit_] - JN.ARM_ANGLE[entry]) % (2 * math.pi)) / (math.pi / 2))) % 4


def ribbon_span(P, car_len=4.3):
    """(s0, s1) for jx.ribbon: from just in front of a car waiting at the give-way line to a few metres out of the
    circle."""
    return P.s_yield - 0.2, P.s_circle_out + 9.0


# ------------------------------------------------------------------ dressing
def dress(S, R, seed):
    g, T = R.g, S["T"]
    D = JN.Dresser(S, seed, keep_out=lambda p: p.length < g.Ro + 6.0)
    rnd = D.rnd
    for A in ARMS:
        D.arm_row(A, 1, g.flare[1] + 3.0, 5, g.we_far)
        D.arm_row(A, -1, g.flare[1] + 3.0 + rnd.uniform(0, 8), 5, g.wx_far)
        a = JN.ARM_ANGLE[A] + math.pi / 4 + rnd.uniform(-0.12, 0.12)
        dvec = Vector((math.cos(a), math.sin(a)))
        D.house_facing(dvec * (g.Ro + 9.0 + (1.0 if g.kind == "two_lane" else 0.0)), -dvec)
    D.farmland(ARMS, max(g.we_far, g.wx_far))
    D.country_roads(ARMS, max(g.we_far, g.wx_far))
    D.tree_belt(ARMS)
    for A in ARMS:
        a = JN.ARM_ANGLE[A] + math.pi / 4
        dvec = Vector((math.cos(a), math.sin(a)))
        D.lamp(dvec * (g.Ro + TN.KERB_W + 0.6), -dvec)
        for u in (g.flare[1] + 12.0, g.flare[1] + 46.0):
            D.lamp(JN.arm_pt(A, u, g.we_far + TN.KERB_W + 0.6), JN.arm_frame(A)[1] * -1)
        for u in (g.flare[0] - 2.0, g.flare[1] + 25.0):
            p = JN.arm_pt(A, u, g.kerb_v(1, u) - 0.18) if u > g.ce[0] else None
            if p is not None:
                TN.gully(T, S["env"], p.x, p.y, rz=JN.ARM_ANGLE[A])
    for k in range(3):
        a = rnd.uniform(0, 2 * math.pi)
        r = (g.r_asph + g.Ro) / 2
        TN.manhole(T, S["env"], r * math.cos(a), r * math.sin(a))
    for A in ARMS:
        for u in (g.flare[1] + 9.0, g.flare[1] + 38.0):
            p = JN.arm_pt(A, u, rnd.choice((-1, 1)) * 1.6)
            TN.manhole(T, S["env"], p.x, p.y)
    # wear: wheel tracks round the circulating lanes and along every arm, crack seals and patches
    radii = [(g.r_asph + g.Ro) / 2] if g.lanes_in == 1 else list(g.tracks)
    strips = [(circle_loop(r) + [circle_loop(r)[0]], [0.0]) for r in radii]
    for A in ARMS:
        strips.append(([JN.arm_pt(A, u, 0.0) for u in (g.flare[1], 200.0)], [1.625, -1.625]))
    JN.wear(T, S["env"], strips, seed=seed)
    bushes, trees = S["bushes"], S["trees"]
    # corner lawns between the arms: a couple of trees and shrub groups so the open grass reads as gardens
    for A in ARMS:
        a0 = JN.ARM_ANGLE[A] + math.pi / 4
        for k in range(2):
            a = a0 + rnd.choice((-1, 1)) * rnd.uniform(0.14, 0.3)
            r = g.Ro + TN.KERB_W + TN.FOOT + rnd.uniform(3.0, 5.5)
            W.instance(rnd.choice(trees), (r * math.cos(a), r * math.sin(a), TN.KERB_H), rz=rnd.uniform(0, 6.3),
                       s=rnd.uniform(0.7, 0.95), c=S["env"])
        for k in range(3):
            a = a0 + rnd.uniform(-0.4, 0.4)
            r = g.Ro + TN.KERB_W + TN.FOOT + rnd.uniform(1.2, 3.0)
            W.instance(rnd.choice(bushes), (r * math.cos(a), r * math.sin(a), TN.KERB_H - 0.1),
                       rz=rnd.uniform(0, 6.3), s=rnd.uniform(0.35, 0.55), c=S["env"])
    for A in ARMS:
        for k in range(2):
            u = g.flare[1] + 30.0 + 26.0 * k + rnd.uniform(-4, 4)
            side = 1 if (k + ARMS.index(A)) % 2 else -1
            p = JN.arm_pt(A, u, side * (g.we_far - 1.05))
            d = JN.arm_frame(A)[0]
            D.parked((p.x, p.y), (-d.x, -d.y) if side > 0 else (d.x, d.y))
    # planting on the central island: low shrubs on the bed ring; small trees only off the entry axes
    bushes, trees = S["bushes"], S["trees"]
    if g.ring > 0:
        for k in range(11):
            a = 2 * math.pi * k / 11 + rnd.uniform(-0.1, 0.1)
            r = g.r_in - TN.KERB_W - 1.3
            W.instance(rnd.choice(bushes), (r * math.cos(a), r * math.sin(a), R.island_top), rz=rnd.uniform(0, 6.3),
                       s=rnd.uniform(0.38, 0.5), c=S["env"])
    else:
        def mound_z(r):
            k = 1 - r / (g.r_in - 0.9)
            return R.island_top + 0.01 + 1.3 * (0.5 - 0.5 * math.cos(math.pi * min(1.0, k * 1.6)))
        for k in range(22):
            a = 2 * math.pi * k / 22 + rnd.uniform(-0.08, 0.08)
            r = g.r_in - rnd.uniform(3.5, 5.5)
            W.instance(rnd.choice(bushes), (r * math.cos(a), r * math.sin(a), mound_z(r) - 0.15),
                       rz=rnd.uniform(0, 6.3), s=rnd.uniform(0.75, 1.05), c=S["env"])
        # small trees on the diagonals, never in line with an entry (Hessen p. 32: no rigid obstacles there)
        for k in range(4):
            a = math.pi / 4 + k * math.pi / 2 + rnd.uniform(-0.15, 0.15)
            r = rnd.uniform(5.5, 8.0)
            W.instance(rnd.choice(trees), (r * math.cos(a), r * math.sin(a), mound_z(r) - 0.1),
                       rz=rnd.uniform(0, 6.3), s=rnd.uniform(0.75, 0.95), c=S["env"])
    if g.ring > 0:
        for k in range(5):
            a = 2 * math.pi * k / 5 + 0.3
            r = 0.0 if k == 0 else 1.6
            W.instance(rnd.choice(bushes), (r * math.cos(a), r * math.sin(a), R.island_top - 0.05),
                       rz=rnd.uniform(0, 6.3), s=rnd.uniform(0.45, 0.6), c=S["env"])
    return D


# ------------------------------------------------------------------ build
def build(src, kind="single", seed=4, heroes=(), dress_town=True, c=None, L=240.0):
    """src: assets path (new scene, town dressing, returns a stage dict like townstage.build) or a town.TownMats
    (adds only the roundabout to the current scene, into collection c). kind: 'single' or 'two_lane'."""
    if isinstance(src, str):
        S = JN.new_scene(src, heroes)
        R = Roundabout(S["T"], S["env"], kind, L)
    else:
        cc = c or W.coll("roundabout")
        R = Roundabout(src, cc, kind, L)
        S = dict(T=src, M=src.M, env=cc, houses=[], parked=[], heroes={}, furniture=dict(signals={}))
    records = []
    S["J"] = R
    S["roundabout"] = R
    S["geom"] = R.g.numbers()
    S["marks"] = markings(R)
    signs(R, records)
    S["signs"] = records
    S["kind"] = kind
    S["arms"] = ARMS
    S["lane_path"] = lambda e, x, lane=0, L=L_PATH, exit_from="outer": lane_path(e, x, lane, kind, L, exit_from)
    if isinstance(src, str) and dress_town:
        dress(S, R, seed)
    return S
