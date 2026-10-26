"""Drive Like a Local B5, United Kingdom: keep left, clockwise roundabouts, give way to the right. 9:16, 30 fps,
canonical timeline from kit/country.py TIMELINE["B05"] (HOOK 2.6, SITUATION 9.5, RULE 8.0, COST 5.5, CORRECT 6.5,
END 4.2 = 36.3 s).
Mirrored world: the German single-lane roundabout (kit/roundabout.py, D 30 m) is built, its German signs and zebras are
deleted, a car park is cut into one block, then the whole road set is mirrored in x (country.mirror_world): left-hand
traffic, clockwise circulation. Everything with a picture or text (UK signs from signs/uk.json, unaltered Commons
files, OGL v1.0 credit in b05_facts.md) is built after the mirror, so nothing reads in mirror writing; cars are not
mirrored, they drive mirrored lane paths (their plates read normally). Red brick terraces with slate roofs and chimney
pots (country.terrace), a red pillar box. Hero: silver rental hatchback with a fictional German plate and the steering
wheel moved to the right (parking.see_through cabin); locals with blank plates; the kit's single-decker bus in plain
red (no double-decker in the kit), mirrored so its doors face the kerb, destination text removed; a black saloon taxi
with a plain roof lamp (no text).
Run: python b05_keep_left_roundabouts.py OUTDIR --frames 1-1089 --res 540 --samples 8 --assets ASSETS [--stills 40]
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit")]

import bpy  # noqa: E402  (bpy first: bmesh only exists once bpy is loaded in the bpy module build)
import bmesh  # noqa: E402
from mathutils import Vector  # noqa: E402

import country as CY  # noqa: E402
import flora  # noqa: E402
import junctions as JN  # noqa: E402
import jx  # noqa: E402
import parking as PK  # noqa: E402
import roundabout as RB  # noqa: E402
import signs as SG  # noqa: E402
import stage  # noqa: E402
import town as TN  # noqa: E402
import townplus as TP  # noqa: E402
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
SEG, T_END = CY.spans("B05")
N = int(round(T_END * FPS))
H0, S0, R0, C0, K0, E0 = (SEG[k][0] for k in ("HOOK", "SITUATION", "RULE", "COST", "CORRECT", "END"))
SIGNS = ["keep-left", "roundabout-ahead", "give-way"]
LN = 1.625                      # lane centre far out on every arm (6.50 m carriageway of the kit)
HL = V.KINDS["hatch"]["L"]

# ------------------------------------------------------------------ the German roundabout, then the mirror
S = RB.build(ASSETS, "single", seed=4, dress_town=False,
             heroes=[("hatch", (0.6, 0.62, 0.65), "rental", "QX LR 516", 0.5),
                     ("saloon", (0.015, 0.016, 0.018), "taxi", "QZ TX 77", 0.4)])
SG.setup(ASSETS)
T, env, lib, traffic = S["T"], S["env"], S["lib"], S["traffic"]
recs = list(S["signs"])
for r in recs:                                   # German signs out (205/215, 222, 350-10)
    o = bpy.data.objects.get(r["name"])
    if o:
        for ch in list(o.children_recursive) + [o]:
            bpy.data.objects.remove(ch, do_unlink=True)
for o in S["marks"]["zebra"]:                   # a UK zebra needs beacons and zigzags: none here
    bpy.data.objects.remove(o, do_unlink=True)
LOT, ENT = (-35.0, -5.95, -134.0, -114.0), (-5.95, -2.9, -128.5, -119.5)   # final (mirrored) coordinates


def cut(rects):
    """Delete the block (gutter, kerb, footway, lawn) inside the rectangles; the asphalt below becomes the car park."""
    for o in [o for o in env.objects if o.type == "MESH" and o.name.startswith("block_")]:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        for (x0, x1, y0, y1) in rects:
            for co, no in (((x0, 0, 0), (1, 0, 0)), ((x1, 0, 0), (1, 0, 0)), ((0, y0, 0), (0, 1, 0)),
                           ((0, y1, 0), (0, 1, 0))):
                bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-4,
                                       plane_co=Vector(co), plane_no=Vector(no))
        dead = []
        for f in bm.faces:
            c_ = f.calc_center_median()
            if any(x0 < c_.x < x1 and y0 < c_.y < y1 for (x0, x1, y0, y1) in rects):
                dead.append(f)
        bmesh.ops.delete(bm, geom=dead, context="FACES")
        bm.to_mesh(o.data)
        bm.free()


cut([(-r[1], -r[0], r[2], r[3]) for r in (LOT, ENT)])       # German x = - final x
CY.mirror_world([env])
ux = W.coll("uk")
CM = CY.Mats("uk")
rnd = random.Random(5)

# car park: edging, bays, parked local cars
for (x0, y0, x1, y1) in ((-35, -134, -5.95, -134), (-35, -114, -5.95, -114), (-35, -134, -35, -114),
                         (-5.95, -134, -5.95, -128.5), (-5.95, -119.5, -5.95, -114), (-5.95, -128.5, -3.35, -128.5),
                         (-5.95, -119.5, -3.35, -119.5)):
    TN.box("lot_edge", ux, ((x0 + x1) / 2, (y0 + y1) / 2, 0.08), (max(0.18, abs(x1 - x0)), max(0.18, abs(y1 - y0)),
                                                                  0.16), T.curb)
for k in range(10):
    x = -33.0 + 2.5 * k
    TN.bar(T, ux, x - 0.06, x + 0.06, -121.0, -116.0, name="bay")
    TN.bar(T, ux, x - 0.06, x + 0.06, -132.0, -127.0, name="bay")
fleet = [bpy.data.collections[k] for k in S["fleet"]]
for k in range(9):
    for yy, rz in ((-118.6, 0.0), (-129.4, math.pi)):
        if rnd.random() < 0.25:
            continue
        e = bpy.data.objects.new(f"parked{k}", None)
        e.instance_type, e.instance_collection = "COLLECTION", rnd.choice(fleet)
        e.location, e.rotation_euler = (-31.75 + 2.5 * k, yy, 0.0), (0, 0, rz)
        ux.objects.link(e)

# red brick terraces along every arm (front rows face the street, back rows behind the gardens)
ARMS_F = [Vector((0, -1)), Vector((0, 1)), Vector((1, 0)), Vector((-1, 0))]
for k, d in enumerate(ARMS_F):
    nl = Vector((-d.y, d.x))
    u1 = 210.0 if k == 0 else 140.0
    CY.terrace(ux, CM, tuple(d * 40 + nl * 6.6), tuple(d * u1 + nl * 6.6), seed=10 + k)
    spans_r = [(40.0, 110.0), (138.0, u1)] if k == 0 else [(40.0, u1)]       # the car park sits on arm S, west
    for j, (ua, ub) in enumerate(spans_r):
        CY.terrace(ux, CM, tuple(d * ub - nl * 6.6), tuple(d * ua - nl * 6.6), seed=20 + 2 * k + j)
    CY.terrace(ux, CM, tuple(d * 110 + nl * 40.6), tuple(d * 40 + nl * 40.6), seed=40 + k)
    CY.terrace(ux, CM, tuple(d * 40 - nl * 40.6), tuple(d * 110 - nl * 40.6), seed=50 + k)
    # roundabout-ahead (diagram 510) on the inbound left verge, 75 m out
    din = -d
    nin = Vector((-din.y, din.x))
    p = d * 75 + nin * (3.25 + JN.SIGN_BACK)
    SG.assembly([("roundabout-ahead", 0.9)], ux, (p.x, p.y, TN.KERB_H), TN.facing((din.x, din.y)), 1.8, set_="uk",
                name=f"uk_510_{k}")
trees = [(sx * 19, sy * 19, 0.15) for sx in (-1, 1) for sy in (-1, 1)] + \
    [(sx * 27, sy * 12, 0.15) for sx in (-1, 1) for sy in (-1, 1)] + [(sx * 12, sy * 27, 0.15) for sx in (-1, 1) for sy in (-1, 1)]
flora.scatter("uk_trees", trees, S["groups"]["decid"], ux, seed=3)
# UK signs at the German record positions, mirrored (x -> -x, rz -> -rz): give way at every entry, keep left on
# every splitter island head
for r in recs:
    x, y, rz = -r["loc"][0], r["loc"][1], -r["rz"]
    if r.get("role") == "entry":
        SG.assembly([("give-way", 0.75)], ux, (x, y, r["z"]), rz, 1.5, set_="uk", name="uk_602_" + r.get("arm", ""))
    elif r.get("role") == "keep_right":
        SG.assembly([("keep-left", 0.6)], ux, (x, y, r["z"]), rz, 0.9, set_="uk", name="uk_610_" + r.get("arm", ""))
# pillar box by the car park entrance (plain red, no crown, no text)
red_box = W.principled("pillar_red", (0.6, 0.02, 0.02), 0.35, coat=0.5)
TN.cyl("pillar_base", ux, (-5.2, -110.5, 0.2), 0.3, 0.1, W.principled("pillar_base", (0.03, 0.03, 0.03), 0.5), verts=24)
TN.cyl("pillar", ux, (-5.2, -110.5, 0.95), 0.26, 1.4, red_box, verts=24)
TN.cyl("pillar_cap", ux, (-5.2, -110.5, 1.72), 0.29, 0.14, red_box, verts=24)
TN.box("pillar_slot", ux, (-4.94, -110.5, 1.35), (0.02, 0.3, 0.04), W.principled("slot", (0.01, 0.01, 0.01), 0.8))

# ------------------------------------------------------------------ vehicles
hero, taxi = S["heroes"]["rental"], S["heroes"]["taxi"]
cab = PK.see_through(hero)
top, bot, KH = PK._windscreen("hatch")
Wh = KH["W"]
wheel = cab["parts"][-1]
wheel.location.x = Wh * 0.42                     # right-hand drive
dash_m = bpy.data.materials[hero["name"] + "_dash"]
root = hero["coll"].objects[hero["name"]]
extra = [TN.cyl("rhd_hub", hero["coll"], tuple(wheel.location), 0.05, 0.06, dash_m, verts=16,
                rot=(math.radians(70), 0, 0)),
         TN.box("console", hero["coll"], (0.0, bot.y - 1.05, 0.42), (0.22, 0.7, 0.36), dash_m, bevel=0.03),
         TN.cyl("gear_stick", hero["coll"], (0.0, bot.y - 0.92, 0.72), 0.012, 0.26, dash_m, verts=8),
         TN.cyl("gear_knob", hero["coll"], (0.0, bot.y - 0.92, 0.86), 0.032, 0.05, dash_m, verts=16)]
for sp in ((0.34, 0.025), (0.025, 0.17)):
    extra.append(TN.box("rhd_spoke", hero["coll"], (0, -sp[1] / 2 + 0.0125 if sp[0] < 0.1 else 0, 0), (sp[0], sp[1], 0.012),
                        dash_m, parent=wheel))
for o in extra[:4]:
    o.parent = root
body_c = hero["obj"].instance_collection
for o in cab["parts"] + extra:
    if o.name not in body_c.objects:
        body_c.objects.link(o)
lamp = TN.box("taxi_lamp", taxi["coll"], (0, 0.15, taxi["roof"] + 0.07), (0.5, 0.18, 0.13),
              W.principled("taxi_lamp", (0.9, 0.6, 0.1), 0.3, emit=(1.0, 0.7, 0.2), estr=0.6),
              parent=taxi["coll"].objects[taxi["name"]])
taxi["obj"].instance_collection.objects.link(lamp)
bus_c = V.bus("bus_red", (0.55, 0.035, 0.03), (0.55, 0.035, 0.03), "QZ VB 112", " ", c=lib)
for o in list(bus_c.all_objects):
    if o.type == "FONT" and o.name.startswith("dest"):
        bpy.data.objects.remove(o, do_unlink=True)
CY.blank_plates(fleet + [taxi["coll"], bus_c])
be = bpy.data.objects.new("bus_inst", None)
be.instance_type, be.instance_collection = "COLLECTION", bus_c
traffic.objects.link(be)
be.scale = (-1.0, 1.0, 1.0)                     # doors on the kerb side (left) for left-hand traffic
bus = dict(obj=be, L=12.0, blinks=[])


def mp(P):
    return jx.Path([(-v.x, v.y) for v in P.p])


def arc(cx, cy, r, a0, a1, n=16):
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / n), cy + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


n_h, n_s, n_r, n_c, n_k, n_e = (int(round((SEG[k][1] - SEG[k][0]) * FPS)) for k in
                                ("HOOK", "SITUATION", "RULE", "COST", "CORRECT", "END"))
n_k = N - (n_h + n_s + n_r + n_c + n_e)
n1, n2 = n_h + 180, n_s - 180                    # hook + situation up to the drone / the drone
nr1, nr2 = 105, n_r - 105
nk1, nk2 = 96, n_k - 96
# the mistake: out of the car park, a left turn into the FAR lane (German habit), north on the right, swerve left
sv1 = jx.kinematics(0.0, 3.0, [(0, "cruise", 5.0)], n1)
s_arc = 5.625 + 6.0 * math.pi / 2
t_sw = int(round((S0 + 4.5) * FPS))
y_sw = -118.0 + (sv1[t_sw][0] - s_arc)
lc = [(LN - 2 * LN * (0.5 - 0.5 * math.cos(math.pi * k / 16)), y_sw + 9.0 * k / 16) for k in range(17)]
P_WRONG = jx.Path([(-10.0, -124.0)] + arc(LN - 6.0, -118.0, 6.0, -math.pi / 2, 0.0)[0:] + lc + [(-LN, y_sw + 80)])
PSg = S["lane_path"]("S", "N", 0)
PS = mp(PSg)
s_stop = PSg.stop_s(HL, PSg.s_yield)
PTg = S["lane_path"]("W", "E", 0)               # mirrored: in from the east, past the south entry, out west
PT = mp(PTg)
cp = PS.at(PSg.s_yield + 6.0)[0]
s_conf = min((k * 0.25 for k in range(int(PT.length * 4))), key=lambda s: (PT.at(s)[0] - cp).length)
RP = jx.Path([(-LN, -260.0), (-LN, 0.0)])
CP = jx.Path([(LN, -260.0), (LN, 0.0)])
BP = jx.Path([(LN, 300.0), (LN, -400.0)])        # southbound, s = 300 - y
KP = jx.Path([(-10.0, -124.0)] + arc(-LN - 4.0, -120.0, 4.0, -math.pi / 2, 0.0) + [(-LN, 0.0)])
hero_pieces = [(P_WRONG, sv1),
               (PS, jx.kinematics(s_stop, 0.0, [(0, "hold", None), (0.7, "cruise", 5.0)], n2)),
               (RP, jx.kinematics(90.0, 5.0, [(0, "cruise", 5.0)], nr1)),
               (PS, CY.hold(s_stop, nr2)),
               (CP, jx.kinematics(60.0 - 1.8, 2.0, [(0, "stop", 60.0)], n_c)),
               (KP, jx.kinematics(0.0, 3.0, [(0, "cruise", 5.0)], nk1)),
               (PS, jx.kinematics(s_stop, 0.0, [(0, "hold", None), (1.8, "cruise", 6.0)], nk2)),
               (RP, CY.hold(-3000.0, n_e))]
jx.blink(hero, "L", 0.2, 1.9)
jx.blink(hero, "L", K0 + 0.3, K0 + 1.8)
CY.drive_pieces(hero, hero_pieces)
HPS = [(P, s) for P, sv in hero_pieces for (s, _v) in sv]
taxi_pieces = [(PT, CY.hold(-3000.0, n1)),
               (PT, jx.kinematics(s_conf - 18.2, 6.0, [(0, "cruise", 6.0), (1.5, "stop", s_conf - 6.0),
                                                        (3.0, "cruise", 4.0)], n2, a_brake=5.6)),
               (PT, CY.hold(-3000.0, nr1)),
               (PT, jx.kinematics(s_conf - 12.0, 6.0, [(0, "cruise", 6.0)], nr2)),
               (PT, CY.hold(-3000.0, n_c + nk1)),
               (PT, jx.kinematics(s_conf - 6.0, 6.0, [(0, "cruise", 6.0)], nk2)),
               (PT, CY.hold(-3000.0, n_e))]
CY.drive_pieces(taxi, taxi_pieces)
# the bus: south at 10 m/s, brakes hard (5 m/s2) at SITUATION 4.0 s; 16 m clear of the hatch's nose at the swerve
tb, ts = S0 + 4.0, t_sw / FPS


def bus_d(t):
    u = min(max(0.0, t - tb), 2.0)
    return 10.0 * u - 2.5 * u * u


yb_brake = y_sw + HL / 2 + 16.0 + 6.0 + bus_d(ts)
bus_sv = []
for f in range(n1):
    t = f / FPS
    y = yb_brake + 10.0 * (tb - t) if t < tb else yb_brake - bus_d(t)
    bus_sv.append((300.0 - y, 10.0 if t < tb else max(0.0, 10.0 - 5.0 * (t - tb))))
bus_sv += CY.hold(bus_sv[-1][0], n2) + CY.hold(-3000.0, n_r)
s_bs = 300.0 - (-200.0 + HL / 2 + 0.5 + 6.0)
bus_sv += jx.kinematics(s_bs - 2.25, 2.5, [(0, "stop", s_bs)], n_c)
bus_sv += [(300.0 - (-110.0 + 9.0 * (2.0 - f / FPS)), 9.0) for f in range(nk1 + nk2)] + CY.hold(-3000.0, n_e)
CY.drive_pieces(bus, [(BP, bus_sv)])
for k, (x0, y0, y1, sd) in enumerate(((4.7, -150.0, -96.0, 2), (4.9, -92.0, -140.0, 6))):
    ped = TP.pedestrian(traffic, f"ped{k}", seed=sd)
    TP.walk(ped, jx.Path([(x0, y0), (x0, y1)]), jx.kinematics(0.0, 1.2, [(0, "cruise", 1.2)], N), list(range(1, N + 1)))
    ped["root"].parent = CY.bpy_empty(traffic, f"ped{k}_footway", loc=(0, 0, TN.KERB_H))   # up on the footway

# ------------------------------------------------------------------ teaching graphics (built after the mirror)
BLUE, RED, YEL, GRN = (0.1, 0.45, 1.0), (0.95, 0.06, 0.04), (1.0, 0.8, 0.05), (0.1, 0.85, 0.3)
arr = CY.flat(ux, "keep_arrow", CY.arrow_pts(7.0, 1.0, 2.4, 1.3), BLUE, 1.4, loc=(-LN, -165.0, 0.04), rot=(0, 0, math.pi / 2))
crs = [CY.flat(ux, f"cross{j}", CY.bar_pts(-1.2, s_ * 1.2, 1.2, -s_ * 1.2, 0.45), RED, 1.4, loc=(LN, -161.0, 0.05),
               rot=(0, 0, 0)) for j, s_ in enumerate((1, -1))]
CY.show(arr, [(R0 + 0.3, R0 + 3.5)])
CY.show(crs, [(R0 + 1.8, R0 + 3.5)])


def callout(sid, width, loc, spans_):
    f = SG.face(sid, ux, width, "uk", name="call_" + sid, emit=0.4)
    f.rotation_euler, f.location = (-math.pi / 2, 0, 0), loc
    CY.show(f, spans_)


callout("keep-left", 1.6, (-5.0, -170.0, 1.0), [(R0 + 0.3, R0 + 3.5)])
callout("give-way", 2.2, (-8.8, -27.0, 1.2), [(R0 + 4.2, C0)])
for k in range(8):
    th = 2 * math.pi * k / 8 + 0.2
    pts = [(x_ - 1.5, y_) for x_, y_ in CY.arrow_pts(3.0, 0.6, 1.2, 0.9)]
    o = CY.flat(ux, f"ring_arrow{k}", pts, YEL, 1.4, loc=(12 * math.cos(th), 12 * math.sin(th), 0.05),
                rot=(0, 0, th - math.pi / 2))
    CY.show(o, [(R0 + 5.0 + 0.12 * k, C0)])
jx.ribbon(PT, s_conf - 14.0, s_conf + 4.0, GRN, ux, R0 + 3.8, C0, width=1.2, name="prio")
gp, gh = PS.at(PSg.s_yield)
gn = Vector((-math.sin(gh), math.cos(gh)))
CY.show(CY.flat(ux, "gw_line", CY.bar_pts(*(gp - gn * 1.9), *(gp + gn * 1.9), 0.5), YEL, 1.4, loc=(0, 0, 0.05),
                rot=(0, 0, 0)), [(R0 + 4.2, C0)])
jx.ribbon(KP, 12.0, 40.0, BLUE, ux, K0 + 1.0, K0 + 3.2, width=1.0, name="left_lane")
# COST close-up: a red ring round the gap between the bumpers and a crumpled-bumper icon
GAP = Vector((LN, -200.0 + HL / 2 + 0.25, 0.0))
ring_m = jx.flat_mat("cost_ring_m", RED, 1.4)
rv, rf = [], []
for k in range(48):
    t_ = 2 * math.pi * k / 48
    rv += [(0.75 * math.cos(t_), 0.75 * math.sin(t_), 0), (0.95 * math.cos(t_), 0.95 * math.sin(t_), 0)]
    rf.append((2 * k, 2 * ((k + 1) % 48), 2 * ((k + 1) % 48) + 1, 2 * k + 1))
ring = W.mesh_obj("cost_ring", rv, rf, ring_m, ux)
ring.location, ring.rotation_euler = (LN + 1.4, GAP.y, 0.75), (math.pi / 2, 0, math.pi / 2)
ico = CY.bpy_empty(ux, "crumple", loc=(LN + 0.8, GAP.y, 2.35))
ico.rotation_euler = (math.pi / 2, 0, math.pi / 2)
CY.flat(ux, "cr_plate", CY.disc_pts(1.35, 48, 0, 0.2), (0.97, 0.97, 0.95), 0.6, rot=(0, 0, 0), parent=ico, z=-0.01)
CY.flat(ux, "cr_car", CY.car_icon_pts(), (0.08, 0.09, 0.1), 0.0, rot=(0, 0, 0), parent=ico)
star = [((0.5 if k % 2 == 0 else 0.22) * math.cos(math.pi * k / 7) + 0.95,
         (0.5 if k % 2 == 0 else 0.22) * math.sin(math.pi * k / 7) + 0.4) for k in range(14)]
CY.flat(ux, "cr_star", star, RED, 1.3, rot=(0, 0, 0), parent=ico, z=0.01)
for o in (ring, ico):
    CY.show(o, [(C0 + 2.4, K0)])
ins = W.coll("inserts")
ec_pos, ec_tgt, ec_scale = CY.end_card(ins, "uk", SIGNS, x0=-9000.0)

# ------------------------------------------------------------------ cameras
shots = jx.Shots(N)


def pose(t):
    P, s = HPS[min(len(HPS) - 1, int(t * FPS))]
    pf, pr = P.at(s + 1.2)[0], P.at(s - 1.2)[0]
    return P.at(s)[0], math.atan2(pf.y - pr.y, pf.x - pr.x)


def cabin(t, lx, ly, z):
    p, yaw = pose(t)
    return Vector((p.x + lx * math.sin(yaw) + ly * math.cos(yaw), p.y - lx * math.cos(yaw) + ly * math.sin(yaw), z))


def chase(t, back=7.5, h=2.5, lag=0.35):
    p, _ = pose(t)
    q, yaw = pose(max(0.0, t - lag))
    f = Vector((math.cos(yaw), math.sin(yaw)))
    return Vector((p.x - f.x * back, p.y - f.y * back, h)), Vector((p.x + f.x * 14, p.y + f.y * 14, 1.2))


def drone(t, t0):
    u = t - t0
    return Vector((18.0 - 0.6 * u, -44.0 + 0.5 * u, 18.0)), Vector((-1.5, -12.0, 0.0))


shots.add("H_cab", 22, H0, H0 + 1.1, lambda t: (cabin(t, -0.2, bot.y - 1.8, 1.22),
                                                 cabin(t, Wh * 0.4, bot.y - 0.35, bot.z - 0.08)))
shots.add("H_chase", 26, H0 + 1.1, S0, chase)
shots.add("S_chase", 26, S0, S0 + 3.0, lambda t: chase(t, 8.0, 2.3, 0.2))
shots.add("S_cab", 20, S0 + 3.0, S0 + 6.0, lambda t: (cabin(t, Wh * 0.4, bot.y - 1.35, 1.17),
                                                      cabin(t, 0.25, bot.y + 20.0, 1.25)))
shots.add("S_drone", 24, S0 + 6.0, R0, lambda t: drone(t, S0 + 6.0))
shots.add("R_top1", 26, R0, R0 + 3.5, lambda t: (Vector((0.0, -163.0, 24.0)), Vector((0.0, -162.0, 0.0))))
shots.add("R_top2", 26, R0 + 3.5, C0, lambda t: (Vector((0.0, -12.0, 42.0)), Vector((0.0, -11.0, 0.0))))
shots.add("C_drone", 30, C0, C0 + 2.2,
          lambda t: (Vector((LN + 9.0 + 0.08 * math.sin(37 * t), -207.0 + 0.4 * (t - C0), 7.0 + 0.06 * math.sin(53 * t))),
                     GAP + Vector((0, 0, 0.8))))
shots.add("C_close", 40, C0 + 2.2, K0, lambda t: (Vector((LN + 7.5, GAP.y - 0.3 + 0.05 * (t - C0), 1.3)),
                                                   GAP + Vector((0, 0, 1.1))))
shots.add("K_chase", 26, K0, K0 + 3.2, chase)
shots.add("K_drone", 24, K0 + 3.2, E0, lambda t: drone(t, K0 + 3.2))
cam_e = shots.add("E_card", 50, E0, T_END, lambda t: (Vector(ec_pos), Vector(ec_tgt)))
cam_e.data.type = "ORTHO"
cam_e.data.ortho_scale = ec_scale
for nm in ("H_cab", "S_cab", "C_close"):
    bpy.data.objects[nm].data.clip_start = 0.02
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, N
sc.camera = bpy.data.objects["H_cab"]

CY.sun_light(ASSETS, az_deg=200.0, elev_deg=38.0, energy=3.8, overcast=0.5)
stage.hazify_all(color=(0.74, 0.76, 0.78), dist=650.0,
                 skip=[m.name for m in bpy.data.materials if m.name.endswith("_m") or m.name.startswith(
                     ("sign_", "taxi_lamp", "ribbon", "prio", "left_lane"))])
stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
todo = STILLS or list(range(FR[0], FR[1] + 1) if FR else range(1, N + 1))
jx.render_frames(shots, OUT, todo)
print("RENDER_DONE", FR, "signs", SG.sources_used().keys())
