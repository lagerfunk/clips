"""Drive Like a Local B8, Spain: leave a multi-lane roundabout from the outer lane. 9:16, 30 fps, canonical timeline
from kit/country.py TIMELINE["B08"] (HOOK 2.6, SITUATION 9.5, RULE 8.0, COST 5.0, CORRECT 7.5, END 4.2 = 36.8 s).
Set: the kit's two-lane roundabout (kit/roundabout.py, D 50 m, two circulating tracks, two-lane entries, right-hand
traffic, anticlockwise) with the German signs and the German circle-edge line removed. Spanish dressing: a dashed
give-way line (ceda el paso) across every entry, a painted arrow per entry lane, a dashed line between the two
circulating lanes, R-1 over R-402 at every entry and on the splitter island (unaltered Commons files, signs/es.json;
R-402 is CC BY-SA 4.0 by Majafego, credited in b08_facts.md). Pale plaster terraces with terracotta roofs and
shutters (country.terrace, palette es), palms on the island and the footways. Hero: red hatchback with a fictional
German plate; a white van and a local car with blank plates; a plain white patrol car with a roof bar and blue lamps
(no emblem, no text) for COST.
Run: python b08_roundabout_outer_lane.py OUTDIR --frames 1-1104 --res 540 --samples 8 --assets ASSETS [--stills 40]
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import country as CY  # noqa: E402
import flora  # noqa: E402
import junctions as JN  # noqa: E402
import jx  # noqa: E402
import roundabout as RB  # noqa: E402
import signs as SG  # noqa: E402
import stage  # noqa: E402
import town as TN  # noqa: E402
import vehicles as V  # noqa: E402
import world as W  # noqa: E402

OUT, RES, SAMPLES, ASSETS, FR, STILLS = "frames", 540, 8, "assets", None, None
a = sys.argv
for i, x in enumerate(a):
    if i == 1 and not x.startswith("--"):
        OUT = x
    if x == "--res":
        RES = int(a[i + 1])
    if x == "--samples":
        SAMPLES = int(a[i + 1])
    if x == "--assets":
        ASSETS = a[i + 1]
    if x == "--frames":
        p, q = a[i + 1].split("-")
        FR = (int(p), int(q))
    if x == "--stills":
        STILLS = [int(v) for v in a[i + 1].split(",")]

FPS = jx.FPS
SEG, T_END = CY.spans("B08")
N = int(round(T_END * FPS))
NAMES = ("HOOK", "SITUATION", "RULE", "COST", "CORRECT", "END")
H0, S0, R0, C0, K0, E0 = (SEG[k][0] for k in NAMES)
NS = [int(round((SEG[k][1] - SEG[k][0]) * FPS)) for k in NAMES]
NS[4] = N - (sum(NS) - NS[4])
n_h, n_s, n_r, n_c, n_k, n_e = NS
SIGNS = ["r1-ceda", "r402-rotonda"]
HL = V.KINDS["hatch"]["L"]
HIDE = -3000.0

# ------------------------------------------------------------------ the kit roundabout, German furniture out
S = RB.build(ASSETS, "two_lane", seed=4, dress_town=False,
             heroes=[("hatch", (0.55, 0.03, 0.025), "hero", "QX ES 808", 0.5),
                     ("van", (0.88, 0.88, 0.86), "van", "QZ VN 31", 0.2),
                     ("saloon", (0.9, 0.9, 0.9), "patrol", "QZ PT 12", 0.35)])
SG.setup(ASSETS)
T, env, lib, traffic = S["T"], S["env"], S["lib"], S["traffic"]
g = S["roundabout"].g
recs = list(S["signs"])
for r in recs:                                   # German signs out (205/215, 222)
    o = bpy.data.objects.get(r["name"])
    if o:
        for ch in list(o.children_recursive) + [o]:
            bpy.data.objects.remove(ch, do_unlink=True)
for o in S["marks"]["kreisrand"]:                # German broken Breitstrich round the circle edge
    bpy.data.objects.remove(o, do_unlink=True)
es = W.coll("es")
CM = CY.Mats("es")
plaza = W.noisy("es_plaza", (0.55, 0.5, 0.42), (0.63, 0.58, 0.49), 2.0, rough=0.9, bump=0.2)
for o in env.objects:                            # the kit's lawn behind the footways becomes a pale paved ground
    if o.type == "MESH" and o.name.startswith("block"):
        for sl in o.material_slots:
            if sl.material == T.lawn:
                sl.material = plaza
CY.ground(es, "far_ground", [(-2500, -2500), (2500, -2500), (2500, 2500), (-2500, 2500)],
          W.noisy("es_dry", (0.36, 0.3, 0.18), (0.46, 0.39, 0.24), 30.0, rough=0.95), z=-0.05)

# Spanish markings: ceda el paso across each entry (0.40 m, 0.80 m dashes, 0.40 m gaps), an arrow per entry lane
# (5 m, straight + right on the right lane, straight + left on the left lane), dashed line between the ring lanes
for A in RB.ARMS:
    an = JN.ARM_ANGLE[A]
    a0 = an + (g.split_w / 2 + 0.5) / g.r_line
    JN.paint_along(T, es, RB._arc_pts(Vector((0, 0)), g.r_line, a0, an + g.th_e, step=0.2), 0.40, dash=0.8, gap=0.4,
                   name="ceda_" + A)
JN.paint_along(T, es, RB.circle_loop(sum(g.tracks) / 2), 0.10, dash=3.0, gap=3.0, closed=True, name="ring_lanes")


def lane_arrow(A, lane, u_tail, L=5.0, branch=0):
    v = g.lane_v(lane, u_tail - L / 2)

    def w(pts):
        return [JN.arm_pt(A, u_tail - x, v - y) for x, y in pts]
    JN.flat_poly("arrow", w(CY.arrow_pts(L, 0.18, 1.3, 0.45)), 0.008, T.paint, es)
    if branch:
        c_, s_ = math.cos(math.radians(40)), branch * math.sin(math.radians(40))
        pts = [(1.8 + x * c_ - y * s_, x * s_ + y * c_) for x, y in CY.arrow_pts(2.1, 0.18, 0.95, 0.42)]
        JN.flat_poly("arrow_b", w(pts), 0.008, T.paint, es)


for A in RB.ARMS:
    lane_arrow(A, 0, 40.0, branch=-1)
    lane_arrow(A, 1, 40.0, branch=1)
# R-1 over R-402 where the German entry signs stood (right side and the splitter island repeat)
for r in recs:
    if r.get("role") == "entry":
        SG.assembly([("r1-ceda", 0.9), ("r402-rotonda", 0.6)], es, (r["loc"][0], r["loc"][1], r["z"]), r["rz"], 1.6,
                    set_="es", name="es_entry_" + r.get("arm", ""))
# plaster terraces with terracotta roofs: along every arm and facing the circle on the diagonals
ARMS_D = {"S": Vector((0, -1)), "N": Vector((0, 1)), "E": Vector((1, 0)), "W": Vector((-1, 0))}
for k, d in enumerate(ARMS_D.values()):
    nl = Vector((-d.y, d.x))
    CY.terrace(es, CM, tuple(d * 60 + nl * 10.0), tuple(d * 210 + nl * 10.0), seed=10 + k)
    CY.terrace(es, CM, tuple(d * 210 - nl * 10.0), tuple(d * 60 - nl * 10.0), seed=20 + k)
    CY.terrace(es, CM, tuple(d * 140 + nl * 42.0), tuple(d * 62 + nl * 42.0), seed=30 + k)
    CY.terrace(es, CM, tuple(d * 62 - nl * 42.0), tuple(d * 140 - nl * 42.0), seed=40 + k)
for k in range(4):
    th = math.pi / 4 + k * math.pi / 2
    cp, tg = Vector((34 * math.cos(th), 34 * math.sin(th))), Vector((-math.sin(th), math.cos(th)))
    CY.terrace(es, CM, tuple(cp + tg * 8.0), tuple(cp - tg * 8.0), seed=50 + k)

# palms (trunk with ring scars, nine drooping fronds), instanced from a small library
bark = W.noisy("palm_bark", (0.22, 0.17, 0.12), (0.34, 0.27, 0.19), 4.0, rough=0.9, bump=0.5)
leaf = flora.leaf_mat("palm_leaf", (0.07, 0.18, 0.04), (0.17, 0.3, 0.07))
palms = bpy.data.collections.new("lib_palms")
lib.children.link(palms)
for sd in range(3):
    pc = bpy.data.collections.new(f"palm{sd}")
    palms.children.link(pc)
    rnd = random.Random(40 + sd)
    h, lean = rnd.uniform(6.5, 8.5), rnd.uniform(0.2, 0.6)
    tv, tf, nr, nsd = [], [], 16, 10
    for i in range(nr + 1):
        t = i / nr
        r = 0.24 * (1 - 0.3 * t) + (0.025 if i % 2 else 0.0)
        for j in range(nsd):
            an = 2 * math.pi * j / nsd
            tv.append((lean * t * t + r * math.cos(an), r * math.sin(an), -0.6 + (h + 0.6) * t))
    for i in range(nr):
        for j in range(nsd):
            tf.append((i * nsd + j, i * nsd + (j + 1) % nsd, (i + 1) * nsd + (j + 1) % nsd, (i + 1) * nsd + j))
    W.mesh_obj("palm_trunk", tv, tf, bark, pc, smooth=True)
    top = Vector((lean, 0.0, h))
    fv, ff = [], []
    for k in range(9):
        az = 2 * math.pi * k / 9 + rnd.uniform(-0.2, 0.2)
        L, droop = rnd.uniform(2.6, 3.4), rnd.uniform(0.8, 1.5)
        d3, sd3 = Vector((math.cos(az), math.sin(az), 0)), Vector((-math.sin(az), math.cos(az), 0))
        b0 = len(fv)
        for i in range(9):
            t = i / 8
            c3 = top + d3 * (L * t) + Vector((0, 0, 0.9 * t - (0.9 + droop) * t * t))
            wd = 0.45 * math.sin(math.pi * min(1.0, t * 1.1)) ** 0.7 + 0.03
            fv += [tuple(c3 - sd3 * wd - Vector((0, 0, 0.12 * wd))), tuple(c3 + Vector((0, 0, 0.05))),
                   tuple(c3 + sd3 * wd - Vector((0, 0, 0.12 * wd)))]
        for i in range(8):
            for j in range(2):
                q0 = b0 + 3 * i + j
                ff.append((q0, q0 + 1, q0 + 4, q0 + 3))
    W.mesh_obj("palm_fronds", fv, ff, leaf, pc, smooth=True)
pts = [(10.0 * math.cos(2 * math.pi * k / 7 + 0.3), 10.0 * math.sin(2 * math.pi * k / 7 + 0.3), 0.0) for k in range(7)]
for d in ARMS_D.values():
    nl = Vector((-d.y, d.x))
    for u in range(74, 206, 16):
        for sd in (-1, 1):
            p = d * u + nl * (sd * 5.6)
            pts.append((p.x, p.y, TN.KERB_H))
flora.scatter("es_palms", pts, palms, es, smin=0.85, smax=1.15, seed=2)

# ------------------------------------------------------------------ vehicles and their tracks
hero, van, patrol = S["heroes"]["hero"], S["heroes"]["van"], S["heroes"]["patrol"]
fleet = [bpy.data.collections[k] for k in S["fleet"]]
CY.blank_plates(fleet + [van["coll"], patrol["coll"]])
proot = patrol["coll"].objects[patrol["name"]]
bar_ = TN.box("p_bar", patrol["coll"], (0, -0.1, patrol["roof"] + 0.05), (1.1, 0.24, 0.08),
              W.principled("p_bar_m", (0.08, 0.08, 0.09), 0.5), parent=proot)
bmat = [jx.flat_mat(f"beacon_{c}", (0.08, 0.3, 1.0), 0.0) for c in "ab"]
domes = []
for k, sx in enumerate((-0.36, 0.36)):
    o = TN.cyl(f"p_dome{k}", patrol["coll"], (sx, -0.1, patrol["roof"] + 0.14), 0.11, 0.1, bmat[k], verts=20)
    o.parent = proot
    domes.append(o)
ic = patrol["obj"].instance_collection
for o in [bar_] + domes:
    if o.name not in ic.objects:
        ic.objects.link(o)


def prof(s0, keys, n):
    """(s, v) per frame from piecewise-linear speed keys [(t, v)], integrated from s0."""
    out, s = [], s0
    for f in range(n):
        t = f / FPS
        v = keys[0][1] if t <= keys[0][0] else keys[-1][1]
        for (ta, va), (tb, vb) in zip(keys, keys[1:]):
            if ta <= t <= tb:
                v = va + (vb - va) * (t - ta) / max(1e-6, tb - ta)
                break
        out.append((s, v))
        s += v / FPS
    return out


def at_time(s_ref, t_ref, v, n, t0=0.0):
    """Constant speed v, at s_ref at time t_ref (segment seconds), frames from t0."""
    return [(s_ref - v * (t_ref - (t0 + f / FPS)), v) for f in range(n)]


def segs(**kw):
    out = []
    for k, n in zip(NAMES, NS):
        out += kw.get(k) or CY.hold(HIDE, n)
    return out


PW = S["lane_path"]("S", "N", 1, exit_from="inner")     # the mistake: straight out of the inner lane
PCO = S["lane_path"]("S", "N", 1)                       # taught: move to the outer lane first, then exit
P1 = S["lane_path"]("S", "E", 0)                        # first exit from the outer lane
PV = S["lane_path"]("S", "W", 0)                        # the van stays in the outer lane
PL = S["lane_path"]("N", "S", 0)
R_OUT = g.tracks[0]
s_x = PW.s_first(lambda p: p.length >= R_OUT, start=PW.s_circle_in + 10.0)
px_ = PW.at(s_x)[0]
s_vc = min((k * 0.25 for k in range(int(PV.length * 4))), key=lambda s: (PV.at(s)[0] - px_).length)
T_CUT = 7.0
sit_h = at_time(s_x, T_CUT, 9.0, n_s)
van_sit = [(s + s_vc - 7.0 * (T_CUT + 1.1), v) for s, v in prof(0.0, [(0, 7.0), (T_CUT + 0.2, 7.0),
                                                                       (T_CUT + 0.2 + 7.0 / 6.0, 0.0)], n_s)]
i0 = int((T_CUT - 1.4) * FPS)
n1 = int(4.0 * FPS)
rule_h = CY.hold(HIDE, n1) + at_time(PCO.s_circle_out + 2.0, 7.6, 7.0, n_r - n1, t0=4.0)
s_hc = s_x + 18.0
cost_h = prof(s_hc, [(0, 8.0), (1.5, 8.0), (3.5, 0.0)], n_c)
gap = [16.0 - 8.5 * min(1.0, (f / FPS) / 1.5) for f in range(n_c)]
cost_p = [(s - gp, v + (8.5 / 1.5 if f / FPS < 1.5 else 0.0)) for f, ((s, v), gp) in enumerate(zip(cost_h, gap))]
nk1 = int(3.0 * FPS)
cor_1 = at_time(P1.s_circle_out + 3.0, 2.5, 7.0, nk1)
cor_2 = at_time(PCO.s_circle_out, 6.8, 8.0, n_k - nk1, t0=3.0)
hero_pieces = [(PW, sit_h[i0:i0 + n_h]), (PW, sit_h), (PCO, rule_h), (PW, cost_h), (P1, cor_1), (PCO, cor_2),
               (PW, CY.hold(HIDE, n_e))]
t_ind = 7.6 - (PCO.s_circle_out + 2.0 - PCO.s_indicate) / 7.0
jx.blink(hero, "R", R0 + max(4.1, t_ind - 0.6), C0)
jx.blink(hero, "R", C0 + 0.6, C0 + 3.6)
jx.blink(hero, "R", K0 + 0.2, K0 + 2.9)
jx.blink(hero, "R", K0 + 4.4, E0)
CY.drive_pieces(hero, hero_pieces)
HPS = [(P, s) for P, sv in hero_pieces for (s, _v) in sv]
CY.drive_pieces(van, [(PV, segs(HOOK=van_sit[i0:i0 + n_h], SITUATION=van_sit))])
CY.drive_pieces(patrol, [(PW, segs(COST=cost_p))])
loc = bpy.data.objects.new("local0", None)
loc.instance_type, loc.instance_collection = "COLLECTION", fleet[1 % len(fleet)]
traffic.objects.link(loc)
CY.drive_pieces(dict(obj=loc, L=4.5, blinks=[]),
                [(PL, segs(SITUATION=at_time(PL.s_yield, 0.5, 7.0, n_s), CORRECT=at_time(PL.s_yield, 0.8, 7.0, n_k)))])
# blue lamps: domes alternate at 2.5 Hz during COST; a blue point light rides with the patrol car (lights the hatch)
pairs_a, pairs_b = [(1, 0.0)], [(1, 0.0)]
f0, f1 = int((C0 + 0.3) * FPS) + 1, int(K0 * FPS) + 1
for f in range(f0, f1, 6):
    pairs_a += [(f, 9.0), (f + 3, 0.0)]
    pairs_b += [(f, 0.0), (f + 3, 9.0)]
pairs_a.append((f1, 0.0))
pairs_b.append((f1, 0.0))
jx.key_emission(bmat[0], pairs_a)
jx.key_emission(bmat[1], pairs_b)
bl = bpy.data.lights.new("beacon_light", "POINT")
bl.color, bl.shadow_soft_size = (0.15, 0.35, 1.0), 0.15
blo = bpy.data.objects.new("beacon_light", bl)
es.objects.link(blo)
for f, e_ in pairs_a:
    bl.energy = 1500.0 if e_ > 0 else 0.0
    bl.keyframe_insert("energy", frame=f)
for fc in stage.fcurves(bl):
    for kp in fc.keyframe_points:
        kp.interpolation = "CONSTANT"
for f in range(f0 - 1, f1 + 1):
    x_, y_, _z = patrol["track"][min(N - 1, f - 1)]
    blo.location = (x_, y_, patrol["roof"] + 0.3)
    blo.keyframe_insert("location", frame=f)

# ------------------------------------------------------------------ teaching graphics
BLUE, RED, GRN = (0.1, 0.45, 1.0), (0.95, 0.06, 0.04), (0.1, 0.85, 0.3)
PO = S["lane_path"]("S", "N", 0)
jx.ribbon(PO, PO.s_yield - 6.0, PO.s_circle_out + 14.0, GRN, es, R0 + 0.3, R0 + 4.0, width=1.4, name="ribbon_outer")
RIN = jx.Path([(g.tracks[1] * math.cos(-1.35 + k * 0.05), g.tracks[1] * math.sin(-1.35 + k * 0.05))
               for k in range(116)])
jx.ribbon(RIN, 0.0, RIN.length, BLUE, es, R0 + 1.2, R0 + 4.0, width=1.4, name="ribbon_inner")
crs = [CY.flat(es, f"cross{j}", CY.bar_pts(-1.6, s_ * 1.6, 1.6, -s_ * 1.6, 0.6), RED, loc=(px_.x, px_.y, 0.06),
               rot=(0, 0, 0), emit=1.4) for j, s_ in enumerate((1, -1))]
CY.show(crs, [(R0 + 2.2, R0 + 4.0)])
ins = W.coll("inserts")
ec_pos, ec_tgt, ec_scale = CY.end_card(ins, "es", SIGNS, x0=-9000.0)

# ------------------------------------------------------------------ cameras
shots = jx.Shots(N)


def pose(t):
    P, s = HPS[min(len(HPS) - 1, int(t * FPS))]
    pf_, pr_ = P.at(s + 1.2)[0], P.at(s - 1.2)[0]
    return P.at(s)[0], math.atan2(pf_.y - pr_.y, pf_.x - pr_.x)


def chase(t, back=7.5, h=2.5, lag=0.35):
    p, _ = pose(t)
    q, yw = pose(max(0.0, t - lag))
    f = Vector((math.cos(yw), math.sin(yw)))
    return Vector((p.x - f.x * back, p.y - f.y * back, h)), Vector((p.x + f.x * 14, p.y + f.y * 14, 1.2))


def chase_r(t, back=9.0, side=4.5, h=4.8, lag=0.3):
    """Chase from behind and to the right (outer lane side), so the van alongside stays in frame."""
    p, _ = pose(t)
    q, yw = pose(max(0.0, t - lag))
    f, r = Vector((math.cos(yw), math.sin(yw))), Vector((math.sin(yw), -math.cos(yw)))
    c_ = p - f * back + r * side
    return Vector((c_.x, c_.y, h)), Vector((p.x + f.x * 10 + r.x * 1.5, p.y + f.y * 10 + r.y * 1.5, 0.8))


def top(z=66.0, y=0.0):
    return lambda t: (Vector((0.0, y - 1.0, z)), Vector((0.0, y, 0.0)))


def rear(t):
    p, yw = pose(t)
    f = Vector((math.cos(yw), math.sin(yw), 0.0))
    p3 = Vector((p.x, p.y, 0.0))
    return p3 - f * (HL / 2 + 1.7) + Vector((0, 0, 1.45)), p3 - f * (HL / 2 - 0.7) + Vector((0, 0, 1.05))


shots.add("H_top", 26, H0, H0 + 1.1, top(60.0, 4.0))
shots.add("H_chase", 26, H0 + 1.1, S0, chase_r)
shots.add("S_drone", 24, S0, S0 + 3.0, lambda t: (Vector((16.0 - 0.8 * (t - S0), -78.0 + 3.0 * (t - S0), 26.0)),
                                                  Vector((2.0, -24.0, 0.0))))
shots.add("S_top", 26, S0 + 3.0, S0 + 6.5, top())
shots.add("S_chase", 26, S0 + 6.5, R0, chase_r)
shots.add("R_top1", 26, R0, R0 + 4.0, top())
shots.add("R_top2", 26, R0 + 4.0, C0, top())
shots.add("C_chase", 26, C0, C0 + 2.0, lambda t: chase(t, 17.0, 5.0, 0.3))
shots.add("C_close", 40, C0 + 2.0, K0, rear)
shots.add("K_drone", 24, K0, K0 + 3.0, lambda t: (Vector((24.0 - 0.8 * (t - K0), -64.0 + 2.0 * (t - K0), 28.0)),
                                                  Vector((8.0, -16.0, 0.0))))
shots.add("K_top", 26, K0 + 3.0, E0, top())
cam_e = shots.add("E_card", 50, E0, T_END, lambda t: (Vector(ec_pos), Vector(ec_tgt)))
cam_e.data.type = "ORTHO"
cam_e.data.ortho_scale = ec_scale
bpy.data.objects["C_close"].data.clip_start = 0.05
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, N
sc.camera = bpy.data.objects["H_top"]

CY.sun_light(ASSETS, az_deg=200.0, elev_deg=52.0, energy=4.6, warm=True)
stage.hazify_all(color=(0.78, 0.82, 0.88), dist=900.0,
                 skip=[m.name for m in bpy.data.materials if m.name.endswith("_m") or m.name.startswith(
                     ("sign_", "ribbon", "beacon_"))])
stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
todo = STILLS or list(range(FR[0], FR[1] + 1) if FR else range(1, N + 1))
jx.render_frames(shots, OUT, todo)
print("RENDER_DONE", FR, "signs", SG.sources_used().keys())
