"""Drive Like a Local B6, Netherlands: shark teeth mean give way, and turning traffic gives way to cyclists going
straight. 9:16, 30 fps, canonical timeline from kit/country.py TIMELINE["B06"] (HOOK 2.6, SITUATION 9.5, RULE 8.0,
COST 4.5, CORRECT 6.5, END 4.2 = 35.3 s).
Set: a Dutch T-junction on junctions.TJunction (no German dressing). Main road W-E: 6.50 m carriageway with a dashed
centre line, a 1.50 m raised grass verge with trees, then a one-way red cycle path (red asphalt, the kit's 1.85 m
cycle-lane width, country.SPEC) on each side. The side road (6.00 m, from the south) crosses the cycle path: shark
teeth (haaientanden) across its inbound half just before the crossing, block markings along the crossing edges, B6 on
the right corner, G11 after the crossing on both paths (unaltered Commons files, signs/nl.json). Brick terraces with
flat roofs and stepped gables (country.terrace, palette nl). Hero: green hatchback with a fictional German plate;
cyclists and walkers (kit/figures.py); local cars with blank plates.
Run: python b06_cyclists_priority.py OUTDIR --frames 1-1059 --res 540 --samples 8 --assets ASSETS [--stills 40]
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import country as CY  # noqa: E402
import figures as F  # noqa: E402
import flora  # noqa: E402
import junctions as JN  # noqa: E402
import jx  # noqa: E402
import parking as PK  # noqa: E402
import signs as SG  # noqa: E402
import stage  # noqa: E402
import town as TN  # noqa: E402
import vehicles as V  # noqa: E402
import world as W  # noqa: E402
import inserts as IN  # noqa: E402

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
# every number on an insert comes from a VERIFIED key of facts/nl.json
NUMBERS = {"nl_priority_failure_fine_320": "€ 320"}
SEG, T_END = CY.spans("B06")
N = int(round(T_END * FPS))
NAMES = ("HOOK", "SITUATION", "RULE", "COST", "CORRECT", "END")
H0, S0, R0, C0, K0, E0 = (SEG[k][0] for k in NAMES)
NS = [int(round((SEG[k][1] - SEG[k][0]) * FPS)) for k in NAMES]
NS[4] = N - (sum(NS) - NS[4])
n_h, n_s, n_r, n_c, n_k, n_e = NS
SIGNS = ["b6-give-way", "g11-cycle-path"]
HW_C, VERGE, FP = 3.25, 1.50, CY.SPEC["nl"]["cycle_lane"]   # carriageway half width, verge, cycle path
HY = HW_C + VERGE + FP                    # 6.60: kerb line of the main road
HX, RK = 3.0, 5.0                         # side road half width, corner radius
Y_FP = -(HW_C + VERGE + FP / 2)           # centre of the south cycle path (eastbound cyclists)
LN = 1.625
HL, HWD = V.KINDS["hatch"]["L"], V.KINDS["hatch"]["W"]
TOOTH = 0.5
Y_TEETH = -(HY + 0.3)                     # base line of the shark teeth; tips point at the waiting driver (south)
Y_TIPS = Y_TEETH - TOOTH * 1.35
HIDE = -3000.0

# ------------------------------------------------------------------ set
S = JN.new_scene(ASSETS, heroes=[("hatch", (0.05, 0.3, 0.12), "hero", "QX NL 306", 0.5)])
T, env, lib, traffic = S["T"], S["env"], S["lib"], S["traffic"]
J = JN.TJunction(T, env, hw_ns=HX, hw_ew=HY, R=RK, L=240.0)
nl = W.coll("nl")
CM = CY.Mats("nl")
red = W.noisy("nl_fietspad", (0.30, 0.06, 0.045), (0.37, 0.08, 0.055), 2.5, rough=0.85, bump=0.3)
CY.ground(nl, "far_ground", [(-2500, -2500), (2500, -2500), (2500, 2500), (-2500, 2500)], T.lawn, z=-0.05)
for sy in (-1, 1):
    y0, y1 = sy * (HW_C + VERGE), sy * HY
    JN.flat_poly("fietspad", [Vector((-240, y0)), Vector((240, y0)), Vector((240, y1)), Vector((-240, y1))], 0.004,
                 red, nl)
X_GAP = 7.5                               # the verge stops short of the side-road mouth (turning sweep)


def verge(x0, x1, sy):
    yc = sy * (HW_C + VERGE / 2)
    TN.box("verge_kerb", nl, ((x0 + x1) / 2, yc, 0.06), (x1 - x0, VERGE, 0.12), T.curb, bevel=0.02)
    TN.box("verge_grass", nl, ((x0 + x1) / 2, yc, 0.125), (x1 - x0 - 0.3, VERGE - 0.3, 0.03), T.lawn)


verge(-240.0, 240.0, 1)
verge(-240.0, -X_GAP, -1)
verge(X_GAP, 240.0, -1)
for x0, x1 in ((-240.0, -X_GAP - 1.0), (X_GAP + 1.0, 240.0)):      # dashed centre line (urban, 3 m dash, 9 m gap)
    JN.paint_along(T, nl, [(x0, 0.0), (x1, 0.0)], 0.10, dash=3.0, gap=9.0, name="centre")
xk = HX + RK - math.sqrt(RK ** 2 - (HY + RK + Y_TEETH) ** 2)          # kerb of the flared mouth at the teeth
teeth = TN.haifisch(T, nl, (xk / 2 + 0.05, Y_TEETH), (1, 0), (0, -1), xk - 0.4, size=TOOTH, gap=0.25)
for yb in (-(HW_C + VERGE) - 0.2, -HY + 0.2):                        # block markings along the crossing edges
    JN.paint_along(T, nl, [(-HX - RK, yb), (HX + RK, yb)], 0.3, dash=0.3, gap=0.3, name="blok")
SG.assembly([("b6-give-way", 0.9)], nl, (HX + 0.9, -(HY + RK + 1.5), TN.KERB_H), TN.facing((0, 1)), 2.2, set_="nl",
            name="nl_b6")
SG.assembly([("g11-cycle-path", 0.6)], nl, (HX + RK + 3.0, -(HY + 1.0), TN.KERB_H), TN.facing((1, 0)), 2.2,
            set_="nl", name="nl_g11_S")
SG.assembly([("g11-cycle-path", 0.6)], nl, (-(HX + RK + 3.0), HY + 1.0, TN.KERB_H), TN.facing((-1, 0)), 2.2,
            set_="nl", name="nl_g11_N")
# brick terraces: facades behind the footways (street on the right of p0 -> p1), back rows for the skyline
FY, FX = HY + 3.5, HX + 3.4
CY.terrace(nl, CM, (-200.0, FY), (200.0, FY), seed=11)
CY.terrace(nl, CM, (200.0, -FY), (13.0, -FY), seed=12)
CY.terrace(nl, CM, (-13.0, -FY), (-200.0, -FY), seed=13)
CY.terrace(nl, CM, (FX, -20.0), (FX, -200.0), seed=14)
CY.terrace(nl, CM, (-FX, -200.0), (-FX, -20.0), seed=15)
CY.terrace(nl, CM, (200.0, 42.0), (-200.0, 42.0), seed=16)
CY.terrace(nl, CM, (-200.0, -46.0), (-17.0, -46.0), seed=17)
CY.terrace(nl, CM, (17.0, -46.0), (200.0, -46.0), seed=18)
trees = [(x, sy * (HW_C + VERGE / 2), 0.14) for sy in (-1, 1) for x in range(-160, 161, 14)
         if not (sy < 0 and abs(x) < X_GAP + 4)]
flora.scatter("nl_trees", trees, S["groups"]["decid"], nl, seed=3)

# ------------------------------------------------------------------ vehicles
hero = S["heroes"]["hero"]
cab = PK.see_through(hero)
top, bot, KH = PK._windscreen("hatch")
body_c = hero["obj"].instance_collection
for o in cab["parts"]:
    if o.name not in body_c.objects:
        body_c.objects.link(o)
fleet = [bpy.data.collections[k] for k in S["fleet"]]
CY.blank_plates(fleet + [hero["coll"]])          # the hero is a local car: blank plate


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


def segs(**kw):
    out = []
    for k, n in zip(NAMES, NS):
        out += kw.get(k) or CY.hold(HIDE, n)
    return out


RT = 7.0                                  # hero's right turn: radius of the centre line
cxy = (HX / 2 + RT, -LN - RT)
P_TURN = jx.Path([(HX / 2, -200.0)] + [(cxy[0] + RT * math.cos(math.pi - k * math.pi / 48),
                                        cxy[1] + RT * math.sin(math.pi - k * math.pi / 48)) for k in range(25)] +
                 [(300.0, -LN)])
s_teeth = Y_TIPS - HL / 2 + 200.0          # centre when the front bumper reaches the teeth tips
s_stop = s_teeth - 0.4                     # waiting 0.4 m before them
# the mistake: 4 m/s, slows to a creep (1.6 m/s), rolls over the teeth at 4.0 s, sees the bike late, stops hard at 7.1
K_SIT = [(0, 4.0), (3.0, 4.0), (3.8, 1.6), (6.8, 1.6), (7.1, 0.0)]
base = prof(0.0, K_SIT, n_s)
sit_sv = [(s + s_teeth - base[120][0], v) for s, v in base]
s_fin = sit_sv[-1][0]
pf, _ = P_TURN.at(s_fin + 0.275 * HL)
pr, _ = P_TURN.at(s_fin - 0.275 * HL)
pc, _ = P_TURN.at(s_fin)
yaw = math.atan2(pf.y - pr.y, pf.x - pr.x)
f_, l_ = Vector((math.cos(yaw), math.sin(yaw))), Vector((-math.sin(yaw), math.cos(yaw)))
corn = [pc + f_ * (sx * HL / 2) + l_ * (sy * (HWD + 0.08)) for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
xs = []
for p0, p1 in zip(corn, corn[1:] + corn[:1]):
    if (p0.y - Y_FP) * (p1.y - Y_FP) <= 0 and abs(p1.y - p0.y) > 1e-6:
        xs.append(p0.x + (p1.x - p0.x) * (Y_FP - p0.y) / (p1.y - p0.y))
x_hit = min(xs) if xs else pc.x - 1.0
EBC = jx.Path([(-300.0, Y_FP), (300.0, Y_FP)])      # eastbound cycle path, s = x + 300
WBC = jx.Path([(300.0, -Y_FP), (-300.0, -Y_FP)])    # westbound (north) cycle path, s = 300 - x
s_c_stop = x_hit - 0.12 - 0.9 + 300.0              # front tyre a hand's width from the door
K_C0 = [(0, 5.0), (6.7, 5.0), (7.7, 0.0)]
c0b = prof(0.0, K_C0, n_s)
c0_sit = [(s + s_c_stop - c0b[-1][0], v) for s, v in c0b]
x_conf = cxy[0] - math.sqrt(RT ** 2 - (Y_FP - cxy[1]) ** 2)      # where the turn crosses the cycle path


def passing(x_pass, t_pass, v, n, west=False):
    s_pass = (300.0 - x_pass) if west else (x_pass + 300.0)
    return prof(s_pass - v * t_pass, [(0, v)], n)


hero_sv = segs(HOOK=sit_sv[150:150 + n_h], SITUATION=sit_sv, RULE=CY.hold(s_stop, n_r), COST=CY.hold(s_stop, n_c),
               CORRECT=prof(s_stop - 2.0, [(0, 4.0), (1.0, 0.0), (4.6, 0.0), (6.5, 4.75)], n_k))
jx.blink(hero, "R", H0, S0)
jx.blink(hero, "R", S0 + 3.8, R0)
jx.blink(hero, "R", K0 + 0.2, E0)
CY.drive_pieces(hero, [(P_TURN, hero_sv)])
HPS = [(P_TURN, s) for (s, _v) in hero_sv]

# cyclists: (path, per-segment tracks); c0 is the near miss
BIKES = [(EBC, dict(HOOK=c0_sit[150:150 + n_h], SITUATION=c0_sit, RULE=passing(x_conf, 1.0, 5.0, n_r),
                    CORRECT=passing(x_conf, 1.4, 5.0, n_k))),
         (EBC, dict(SITUATION=passing(x_conf, 0.6, 4.8, n_s), RULE=passing(x_conf, 2.6, 4.6, n_r),
                    CORRECT=passing(x_conf, 2.2, 4.8, n_k))),
         (EBC, dict(SITUATION=passing(x_conf, 1.8, 5.2, n_s), RULE=passing(x_conf, 4.4, 5.2, n_r),
                    CORRECT=passing(x_conf, 3.0, 5.0, n_k))),
         (EBC, dict(HOOK=passing(x_conf, -3.4, 5.0, n_h), SITUATION=passing(x_conf, 3.0, 5.0, n_s),
                    RULE=passing(x_conf, 5.8, 4.8, n_r), CORRECT=passing(x_conf, 3.7, 5.0, n_k))),
         (EBC, dict(RULE=passing(x_conf, 7.2, 5.0, n_r), CORRECT=passing(x_conf, 4.3, 5.2, n_k))),
         (WBC, dict(HOOK=passing(-2.0, 1.2, 5.0, n_h, True), SITUATION=passing(0.0, 1.0, 5.0, n_s, True),
                    RULE=passing(0.0, 3.0, 5.0, n_r, True), CORRECT=passing(0.0, 0.8, 4.6, n_k, True))),
         (WBC, dict(SITUATION=passing(0.0, 2.5, 4.6, n_s, True), RULE=passing(0.0, 6.0, 4.6, n_r, True),
                    CORRECT=passing(0.0, 4.5, 5.0, n_k, True)))]
RIDERS = [dict(sex="f", jacket=F.YELLOW), dict(sex="m"), dict(sex="f", bag="backpack"), dict(sex="m", seed=7),
          dict(sex="f", seed=9), dict(sex="m", seed=11), dict(sex="f", seed=13)]
BIKE_KW = [dict(frame="step", basket=True), dict(frame="diamond"), dict(frame="step"), dict(frame="diamond"),
           dict(frame="step", basket=True), dict(frame="diamond"), dict(frame="step")]
for k, (P, plan) in enumerate(BIKES):
    cy = F.cyclist(traffic, f"bike{k}", rider=RIDERS[k], bike=BIKE_KW[k], seed=k + 1)
    sv = []
    for nm, n in zip(NAMES, NS):        # off screen: riding far away (no stop-and-go pose at the next cut)
        sv += plan.get(nm) or prof(HIDE - 400.0 * NAMES.index(nm), [(0, 5.0)], n)
    F.ride(cy, P, sv, foot="R")
    jumps = {f + 1 for f in range(N - 1) if abs(sv[f + 1][0] - sv[f][0]) > 1.0}
    objs = [cy["root"]] + list(cy["root"].children_recursive) + [cy["rider"]["arm"]]
    for o in objs:                      # no motion-blur smear where a track jumps at a cut
        ids = [o] + ([o.data.shape_keys] if o.type == "MESH" and o.data.shape_keys else [])
        for idb in ids:
            if not (idb.animation_data and idb.animation_data.action):
                continue
            for fc in stage.fcurves(idb):
                for kp in fc.keyframe_points:
                    if int(round(kp.co.x)) in jumps:
                        kp.interpolation = "CONSTANT"
EBR = jx.Path([(-300.0, -LN), (300.0, -LN)])
WBR = jx.Path([(300.0, LN), (-300.0, LN)])
for k, (P, plan, col) in enumerate(((EBR, dict(SITUATION=passing(0.0, 1.6, 8.5, n_s),
                                                CORRECT=passing(0.0, 2.0, 8.5, n_k)), fleet[0]),
                                    (WBR, dict(SITUATION=passing(0.0, 2.4, 8.5, n_s, True),
                                               CORRECT=passing(0.0, 4.2, 8.5, n_k, True)), fleet[3 % len(fleet)]))):
    e = bpy.data.objects.new(f"local{k}", None)
    e.instance_type, e.instance_collection = "COLLECTION", col
    traffic.objects.link(e)
    CY.drive_pieces(dict(obj=e, L=4.4, blinks=[]), [(P, segs(**plan))])
for k, (x0, y0, x1, y1, sd) in enumerate(((20.0, HY + 1.7, -30.0, HY + 1.7, 2), (-HX - 1.7, -14.0, -HX - 1.7, -60.0, 6))):
    ped = F.person(traffic, f"ped{k}", seed=sd)
    F.walk(ped, jx.Path([(x0, y0), (x1, y1)]), jx.kinematics(0.0, 1.25, [(0, "cruise", 1.25)], N),
           ground=lambda x, y: TN.KERB_H)

# ------------------------------------------------------------------ teaching graphics
BLUE, RED, YEL, GREY = (0.1, 0.45, 1.0), (0.95, 0.06, 0.04), (1.0, 0.8, 0.05), (0.55, 0.57, 0.6)
glow = [CY.flat(nl, "tooth_glow", [(v.co.x, v.co.y) for v in o.data.vertices], (1.0, 1.0, 1.0), loc=(0, 0, 0.02),
                rot=(0, 0, 0), emit=3.0) for o in teeth]
CY.show(glow, [(R0 + 0.3, R0 + 3.8)])
gw = CY.flat(nl, "gw_bar", CY.bar_pts(0.1, Y_TIPS - 0.35, xk - 0.3, Y_TIPS - 0.35, 0.35), YEL, loc=(0, 0, 0.03),
             rot=(0, 0, 0), emit=1.6)
CY.show(gw, [(R0 + 0.8, C0)])
crs = [CY.flat(nl, f"cross{j}", CY.bar_pts(-0.9, s_ * 0.9, 0.9, -s_ * 0.9, 0.35), RED, loc=(x_conf, Y_FP, 0.05),
               rot=(0, 0, 0), emit=1.4) for j, s_ in enumerate((1, -1))]
CY.show(crs, [(R0 + 1.8, R0 + 3.8)])
jx.ribbon(EBC, x_conf + 300.0 - 16.0, x_conf + 300.0 + 12.0, BLUE, nl, R0 + 3.9, C0, width=0.9, name="ribbon_bike")
jx.ribbon(P_TURN, s_stop - 9.0, s_stop + 0.2, GREY, nl, R0 + 4.6, C0, width=0.9, name="ribbon_turn")
# COST (owner rule 27 Oct: no flat primitive scenes): the fine on a kitchen table, typeset Dutch text, envelope beside
# it, a mug; every number from NUMBERS (VERIFIED, tests/test_trackb_town.py checks it)
ins = W.coll("inserts")
IN.setup(ASSETS)
LR = Vector((9300.0, 0.0, 0.0))
IN.room(ins, "kit_room", LR, w=4.0, d=3.6, h=2.6, wall=(0.82, 0.8, 0.74))
TT = IN.table(ins, "kit_table", tuple(LR + Vector((0.1, 0.5, 0.75))))
CL = Vector(TT)
INK = IN.INK
IN.letter(ins, "letter", tuple(CL), math.radians(-5), [
    ("Verkeersboete · Beschikking", 0.0062, "din", IN.GREY_T, 0.0),
    ("Aan de kentekenhouder", 0.0072, "din", INK, 0.012),
    ("Personenauto", 0.0072, "din", INK, 0.004),
    ("Gedraging", 0.0072, "din", IN.GREY_T, 0.022),
    ("Geen voorrang verlenen", 0.0125, "bold", INK, 0.006),
    ("bij het afslaan, kruising met fietspad", 0.0072, "din", INK, 0.006),
    ("Boetebedrag:  " + NUMBERS["nl_priority_failure_fine_320"], 0.0145, "bold", IN.RED, 0.022),
    ("Exclusief administratiekosten.", 0.0062, "din", IN.GREY_T, 0.008),
    ("Betaal binnen de gestelde termijn.", 0.0072, "din", INK, 0.016),
    ("Niet eens? Maak binnen de termijn bezwaar.", 0.0072, "din", INK, 0.006),
    ("Deze brief is automatisch aangemaakt.", 0.0058, "din", IN.GREY_T, 0.026),
])
IN.mug(ins, "kit_mug", tuple(TT + Vector((-0.32, 0.18, 0.0))), color=(0.95, 0.45, 0.05))
ec_pos, ec_tgt, ec_scale = CY.end_card(ins, "nl", SIGNS, x0=-9000.0)

# ------------------------------------------------------------------ cameras
shots = jx.Shots(N)


def pose(t):
    P, s = HPS[min(len(HPS) - 1, int(t * FPS))]
    pf_, pr_ = P.at(s + 1.2)[0], P.at(s - 1.2)[0]
    return P.at(s)[0], math.atan2(pf_.y - pr_.y, pf_.x - pr_.x)


def cabin(t, lx, ly, z):
    p, yw = pose(t)
    return Vector((p.x + lx * math.sin(yw) + ly * math.cos(yw), p.y - lx * math.cos(yw) + ly * math.sin(yw), z))


def chase(t, back=7.5, h=2.5, lag=0.35):
    p, _ = pose(t)
    q, yw = pose(max(0.0, t - lag))
    f = Vector((math.cos(yw), math.sin(yw)))
    return Vector((p.x - f.x * back, p.y - f.y * back, h)), Vector((p.x + f.x * 14, p.y + f.y * 14, 1.2))


CONF = Vector((x_conf, Y_FP, 0.0))
# the cabin close-up rendered black (no light under the roof): low rear three-quarter view towards the red path
shots.add("H_cab", 26, H0, H0 + 1.1, lambda t: (cabin(t, -1.5, -5.5, 1.45), cabin(t, -0.4, 12.0, 1.0)))
shots.add("H_side", 30, H0 + 1.1, S0, lambda t: (Vector((-5.5 + 0.3 * (t - H0), -13.0, 3.6)),
                                                 CONF + Vector((0.3, 0.2, 0.6))))
shots.add("S_drone", 24, S0, S0 + 3.0, lambda t: (Vector((4.0 - 0.3 * (t - S0), -34.0 + 1.2 * (t - S0), 30.0)),
                                                  Vector((0.0, -2.0, 0.0))))
shots.add("S_chase", 26, S0 + 3.0, S0 + 6.5, lambda t: chase(t, 7.0, 2.6, 0.3))
shots.add("S_close", 30, S0 + 6.5, R0, lambda t: (Vector((-4.6 + 0.05 * (t - S0), -10.6, 1.5)),
                                                  CONF + Vector((-1.2, 0.4, 0.85))))
shots.add("R_top1", 26, R0, R0 + 3.8, lambda t: (Vector((2.2, -9.5, 19.0)), Vector((2.2, -8.5, 0.0))))
shots.add("R_top2", 26, R0 + 3.8, C0, lambda t: (Vector((1.0, -7.5, 23.0)), Vector((1.0, -6.5, 0.0))))
shots.add("C_letter", 40, C0, K0, lambda t: (CL + Vector((0.0, -0.62 + 0.06 * (t - C0), 0.62 - 0.04 * (t - C0))),
                                             CL + Vector((0.0, 0.03, 0.0))))
shots.add("K_chase", 26, K0, K0 + 3.2, lambda t: chase(t, 6.5, 2.4, 0.3))
shots.add("K_drone", 24, K0 + 3.2, E0, lambda t: (Vector((2.5 - 0.2 * (t - K0), -31.0 + 0.6 * (t - K0), 24.0)),
                                                  Vector((2.0, -3.0, 0.0))))
cam_e = shots.add("E_card", 50, E0, T_END, lambda t: (Vector(ec_pos), Vector(ec_tgt)))
cam_e.data.type = "ORTHO"
cam_e.data.ortho_scale = ec_scale
for nm in ("H_cab", "C_letter"):
    bpy.data.objects[nm].data.clip_start = 0.02
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, N
sc.camera = bpy.data.objects["H_cab"]

CY.sun_light(ASSETS, az_deg=215.0, elev_deg=34.0, energy=3.6, overcast=0.6)
stage.hazify_all(color=(0.72, 0.75, 0.8), dist=600.0,
                 skip=[m.name for m in bpy.data.materials if m.name.endswith("_m") or m.name.startswith(
                     ("sign_", "ribbon"))])
stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
todo = STILLS or list(range(FR[0], FR[1] + 1) if FR else range(1, N + 1))
jx.render_frames(shots, OUT, todo)
print("RENDER_DONE", FR, "signs", SG.sources_used().keys())
