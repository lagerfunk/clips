"""Drive Like a Local #29, Germany: Autobahn roadworks, follow the yellow lines. 9:16, 30 fps, golden hour.
The render carries one opening per language (QA r7: no shared hook shot): HOOK 0-2.2 (EN, drone over the taper and the
wall), HOOK_DE 2.2-4.4 (low behind the hatchback, between the yellow and the white line where they split), HOOK_FR
4.4-6.6 (the 60 repeater inside the works, the hatchback past it at 85), then SITUATION 6.6-16.6, RULE 16.6-24.6,
COST 24.6-29.1, CORRECT 29.1-35.6, END 35.6-39.2: 1176 frames. Each language's cut uses its own hook and its own
order of the rest (post_ep29.py), so every cut is 34.8 s (1044 frames).
World: the episode 1 Autobahn on a 4 km road with a long-term roadworks (kit/roadworks.py): advance signs at 2 km and
800 m (Zeichen 123), the lane-reduction sign 531-11, the speed funnel 120, 100, 80, 60 (Commons pictures), the mobile
barrier with its flashing arrow, Leitbaken along a 1:20 taper that closes the right lane, yellow temporary lines that
shift the two remaining lanes left (3.00 m and 3.50 m) while the old white lines stay visible and run straight on, and
a steel protection wall with reflectors along the works. A speed trailer stands in the works area.
Traffic is simulated (ep13_zkit.Sim); the teal hatchback is choreographed:
  A (the mistake) follows the white lines at 100 km/h, a hand's width from the wall, and brakes behind an artic;
  B (the right move) is down to 60 before the zone and keeps to the middle of the yellow lane;
  C (the cost) passes the 60 repeater and the speed trailer at 85 km/h in the 60 zone and is flashed.
The trailer gets its road rear here (the end facing traffic, opposite the drawbar): light board with two lamp
clusters, red triangle reflectors, a plate holder with a German plate and its lamp (QA r7: plain box).
Run: python ep29_roadworks_yellow_lines.py OUTDIR --frames 1-1176 --res 540 --samples 8 --assets ASSETS
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit"), os.path.join(HERE, "..", "ep13")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import enforcement as EN  # noqa: E402
import ep13_zkit as Z  # noqa: E402
import lanemgmt as LM  # noqa: E402
import motion  # noqa: E402
import roadworks as RW  # noqa: E402
import stage  # noqa: E402
import vehicles as V  # noqa: E402

O = Z.cli()
C = Z.Canon([("HOOK", 2.2), ("HOOK_DE", 2.2), ("HOOK_FR", 2.2), ("SITUATION", 10.0), ("RULE", 8.0), ("COST", 4.5),
             ("CORRECT", 6.5), ("END", 3.6)])
ST = 2400.0                       # taper start
TEAL = (0.006, 0.26, 0.27)
HERO_L = V.KINDS["hatch"]["L"]
TRAILER_S = ST + 520.0
SIGN60_S = ST - 200.0
SIGNW_S = ST + 400.0              # 60 repeater inside the works (both sides)

MODELS = {}


def prebuild(lib):
    allm, models = Z.fleet_models(lib)
    allm["hero"] = V.car("hatch", TEAL, "hero", "JX DL 29", metal=0.45, c=lib)
    MODELS.update(allm)
    MODELS["_sim"] = models


Z.prebuild(prebuild)
S = Z.world(O["ASSETS"], length=4000.0, s0=40.0, s1=3960.0, gantry_s=0, bridge_s=3500.0, phone_s=1150.0)
road, lib, env, traffic, M = S["road"], S["lib"], S["env"], S["traffic"], S["M"]
sc = bpy.context.scene
sc.render.fps = Z.FPS
sc.frame_start, sc.frame_end = 1, C.N
LM.setup(O["ASSETS"])

# ---------------------------------------------------------------- roadworks: old white lines stay, yellow lines shift left
PLAN = [(2000.0, [("123", 1.26), ("1004-35", 0.84)]), (1200.0, [("274-120", 0.75)]),
        (800.0, [("123", 1.26), ("1004-800", 0.84)]), (700.0, [("531-11", 1.6)]), (600.0, [("274-100", 0.75)]),
        (400.0, [("274-80", 0.75)]), (200.0, [("274-60", 0.75)])]
rw = RW.RoadWorks(road, M, env, lib, s_taper=ST, road_s0=40.0, mask_white=False, signs=PLAN, strict=False)
rw.flash(1, C.N)

# steel protection wall with reflectors along the works, just right of the yellow edge line
WALL0, WALL1 = rw.s_t1 + 4.0, ST + 1100.0
xw = rw.x_close1 + 0.75
prof = [(xw, 0.0), (xw, 0.12), (xw + 0.07, 0.3), (xw + 0.1, 0.82), (xw + 0.34, 0.82), (xw + 0.37, 0.3),
        (xw + 0.44, 0.12), (xw + 0.44, 0.0)]
wall = road.sweep("a4_wall", prof, WALL0, WALL1, LM.galvanised(), env, step=2.0)
refl_m = Z._mat("a4_wall_refl", (1.0, 0.6, 0.05), 0.2, emit=(1.0, 0.55, 0.05), estr=1.2)
refl_w = Z._mat("a4_wall_refl_w", (0.95, 0.95, 0.95), 0.2, emit=(1, 1, 1), estr=0.6)
s = WALL0 + 2.0
k = 0
while s < WALL1:
    b = LM.MB()
    b.box((0, 0, 0.0), (0.07, 0.02, 0.07))
    o = b.obj("a4_wall_reflector", refl_m if k % 2 == 0 else refl_w, env)
    o.matrix_world = road.matrix(s, xw + 0.05, 0.62)
    s += 6.0
    k += 1
# works vehicles parked in the closed lane
park = [("van_white", ST + 300.0, 12.0, 0.04), ("t_white", ST + 760.0, 12.2, -0.03)]

# the limit repeated inside the works, both sides (the 60 holds to the end of the zone)
for x_, h_, nm in ((18.4, -0.06, "r"), (1.35, 0.0, "m")):
    LM.road_sign(road, [("274-60", 0.75)], SIGNW_S, x_, env, f"a4_rep60_{nm}", h=h_, bottom=1.6)

# speed trailer in the works area, facing approaching traffic
trailer = EN.SpeedTrailer(road, env, TRAILER_S, x=12.0, h=0.012)
trailer.light["peak"] = 3600.0


def trailer_rear(tr, plate="JX VM 290"):
    """Road rear of the trailer: the end facing traffic (local +y), opposite the drawbar. A dark light board under the
    shell on two brackets, a lamp cluster at each end (amber indicator outside, red tail and brake lens inside), a red
    triangle reflector inboard of each cluster, a plate holder with a German plate in the middle and a plate lamp."""
    L, _Wd, _H = tr.dims
    y1, g = L / 2, tr.root
    nm = g.name
    steel = bpy.data.materials["en_trailer_steel"]
    dark = bpy.data.materials["en_trailer_dark"]
    red = Z._mat("a4_tr_tail", (0.42, 0.012, 0.01), 0.12, emit=(1.0, 0.04, 0.02), estr=0.12)
    amber = Z._mat("a4_tr_ind", (0.6, 0.26, 0.012), 0.12)
    tri = Z._mat("a4_tr_tri", (0.62, 0.015, 0.012), 0.25, emit=(1.0, 0.05, 0.03), estr=0.3)
    clear = Z._mat("a4_tr_platelamp", (0.75, 0.75, 0.72), 0.1, emit=(1.0, 0.97, 0.9), estr=0.2)
    yf = y1 + 0.08                                                           # front face of the board
    b = LM.MB()
    b.box((0.0, y1 + 0.06, 0.215), (1.46, 0.04, 0.17))                      # light board
    b.box((0.0, y1 + 0.075, 0.307), (1.46, 0.07, 0.02))                     # top flange
    for sx in (-1, 1):
        b.box((sx * 0.45, y1 - 0.10, 0.285), (0.05, 0.32, 0.05))           # brackets under the shell
        b.box((sx * 0.585, yf + 0.008, 0.215), (0.30, 0.016, 0.115))        # lamp housing
    b.box((0.0, yf + 0.004, 0.205), (0.56, 0.008, 0.145))                   # plate holder rim
    b.obj(nm + "_rearboard", dark, env, g)
    hood = LM.MB()
    hood.box((0.0, yf + 0.02, 0.292), (0.10, 0.03, 0.022))                  # plate lamp hood
    hood.obj(nm + "_platelamp_hood", steel, env, g)
    lam, ind = LM.MB(), LM.MB()
    for sx in (-1, 1):
        lam.box((sx * 0.53, yf + 0.019, 0.215), (0.15, 0.008, 0.085))
        ind.box((sx * 0.675, yf + 0.019, 0.215), (0.08, 0.008, 0.085))
    lam.obj(nm + "_taillamps", red, env, g)
    ind.obj(nm + "_indicators", amber, env, g)
    t3 = LM.MB()
    for sx in (-1, 1):
        cx, a = sx * 0.355, 0.15                                            # equilateral, point up, hollow centre
        t3.poly([(cx - a / 2, yf + 0.003, 0.14), (cx + a / 2, yf + 0.003, 0.14), (cx, yf + 0.003, 0.14 + a * 0.866)])
    t3.obj(nm + "_triangles", tri, env, g)
    pl = LM.MB()
    pl.box((0.0, yf + 0.021, 0.279), (0.06, 0.004, 0.006))
    pl.obj(nm + "_platelamp", clear, env, g)
    bpy.context.view_layer.update()
    mw = g.matrix_world
    n = (mw.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
    V.plate_on(env, g, tuple(mw @ Vector((0.0, yf + 0.009, 0.205))), tuple(n), plate, V.common(), nm + "_plate")


trailer_rear(trailer)
EN.assert_no_section_control()

# ---------------------------------------------------------------- traffic simulations
SIMS = MODELS["_sim"]
LIM = [(1200.0, 1800.0, Z.kmh(120)), (1800.0, 2000.0, Z.kmh(100)), (2000.0, 2200.0, Z.kmh(80)),
       (2200.0, 3960.0, Z.kmh(60))]


def base_sim(seed, dens=1.0):
    sim = Z.Sim(0.0, 3960.0, seed=seed)
    sim.set_models(SIMS)
    sim.closures.append((2, ST - 650.0, rw.s_merge - 4.0, 3960.0))
    sim.limits.extend(LIM)
    for lane, hw, kinds, vr in ((0, 3.6, [("car", 1)], (33.0, 40.0)),
                                (1, 2.6, [("car", 6), ("van", 1)], (28.0, 34.0)),
                                (2, 2.6, [("car", 3), ("van", 1), ("truck", 4)], (23.0, 27.0))):
        sim.fill(lane, 0.0, 3900.0, hw / dens, vr[0], kinds, v0_range=vr)
        sim.inflow.append((lane, hw * 1.15 / dens, kinds, vr[0], vr[1]))
    return sim


def xfun(lanef, s):
    l0 = max(0, min(2, int(math.floor(lanef))))
    l1 = min(2, l0 + 1)
    u = lanef - l0
    return rw.lane_x(l0, s) + (rw.lane_x(l1, s) - rw.lane_x(l0, s)) * u


# A: 100 km/h on the old white lines (x = 8.375 straight on), a hand's width from the wall; brakes behind the artic
VA = Z.kmh(100)
WA0 = 20.0
SA0 = ST - 400.0
TBA = WA0 + (ST + 360.0 - SA0) / VA
KA = Z.Kin(WA0 - 20.0, SA0 - 20.0 * VA, VA, [(WA0 - 20.0, "v", VA), (TBA, "v", Z.kmh(55), 2.0, 6.5)], TBA + 12.0,
           L=HERO_L)


def wA(s):
    return WA0 + (s - SA0) / VA


def heroA(T):
    s, v = KA.at(T)
    return dict(s=s, lane=1.0, x=Z.LANES[1], v=v, ind=None)


# the artic ahead in the yellow right lane, 60 km/h, brakes a little at TBA - 0.5
KT = Z.Kin(WA0 - 20.0, ST + 420.0 - (TBA - (WA0 - 20.0)) * Z.kmh(60), Z.kmh(60),
           [(WA0 - 20.0, "v", Z.kmh(60)), (TBA - 0.5, "v", Z.kmh(42), 1.0, 2.2), (TBA + 3.5, "v", Z.kmh(60), 0.8)],
           TBA + 12.0, L=16.45)


def artic(T):
    s, v = KT.at(T)
    return dict(s=s, lane=1.0, v=v, ind=None)


simA = base_sim(29)
simA.script("hero", "hero", HERO_L, heroA)
simA.script("artic", "t_nord", 16.45, artic, kind="truck")
simA.run(0.0, TBA + 10.0)
simA.drop_conflicts()

# B: slows from 110 to 60 before the zone, follows the yellow lines (middle lane -> right yellow lane), keeps a safe
# gap behind a truck, then overtakes it slowly in the narrow left lane, centred
WB0 = 20.0
SB0 = ST - 420.0
KB = Z.Kin(WB0 - 20.0, SB0 - 20.0 * Z.kmh(110), Z.kmh(110),
           [(WB0 - 20.0, "v", Z.kmh(110)), (WB0 + 0.2, "v", Z.kmh(60), 2.0, 3.6)], WB0 + 60.0, L=HERO_L)


def wB(s):
    for i, ss in enumerate(KB.ss):
        if ss >= s:
            return KB.ts[i]
    return KB.ts[-1]


T_LCB = None


def heroB(T):
    s, v = KB.at(T)
    lane = Z.lane_change(T, T_LCB, 2.6, 1.0, 0.0)
    ind = "L" if T_LCB - 1.1 <= T < T_LCB + 2.9 else None
    return dict(s=s, lane=lane, v=v, ind=ind)


V_TB = Z.kmh(50)


def truckB(T):
    # an artic in the right yellow lane, 40 m ahead of the hatchback at ST + 150 (a safe gap), 50 km/h
    t0 = wB(ST + 150.0)
    return dict(s=ST + 150.0 + 40.4 + V_TB * (T - t0), lane=1.0, v=V_TB, ind=None)


T_LCB = wB(ST + 290.0)
simB = base_sim(31)
simB.script("hero", "hero", HERO_L, heroB)
simB.script("truck", "t_alpen", 16.45, truckB, kind="truck")
simB.run(0.0, wB(ST + 700.0) + 4.0)
simB.drop_conflicts()

# C: 85 km/h in the 60 zone past the speed trailer
VC = Z.kmh(85)
WC0 = 30.0


def heroC(T):
    s = TRAILER_S + VC * (T - WC0)
    return dict(s=s, lane=1.0, v=VC, ind=None)


simC = base_sim(37)
simC.script("hero", "hero", HERO_L, heroC)
simC.run(WC0 - 12.0, WC0 + 8.0)
simC.drop_conflicts()

D = Z.Director(C, road, xfun)
D.variant("A", simA)
D.variant("B", simB)
D.variant("C", simC)
D.variant("_card", None)
t = C.t
HA, HB, HC = "A:hero", "B:hero", "C:hero"

# ---------------------------------------------------------------- shots
# HOOK 0.0-1.3: drone over the taper, he stays on the white lines while the yellow lines swing left
D.shot("H_drone", t("HOOK", 0.0), t("HOOK", 1.3), "A", wA(ST - 30.0), lens=26,
       cam=lambda tt, f: (road.point(ST - 70.0 + 20.0 * tt, 4.0, 26.0), road.point(ST + 120.0, 9.5, 0.0)))
# HOOK 1.3-2.2: above the wall, looking back along it: he flashes past a hand's width from it (QA r3: the camera sat
# 0.2 m over the wall top, which filled half the frame as a flat slab at the lens)
WH = ST + 200.0
D.shot("H_wall", t("HOOK", 1.3), t("HOOK", 2.2), "A", wA(WH - 11.0), lens=26,
       cam=lambda tt, f: (road.point(WH + 2.5, xw + 0.55, 1.95), road.point(WH - 30.0, Z.LANES[1] + 0.2, 0.7)))

# HOOK_DE 0.0-2.2 (the German cut opens here): low behind the hatchback, the camera between the yellow lane line and
# the white one exactly where they split at the taper, so both run out from under the lens; he stays on the white
WD0 = ST + 6.0


def de_x(s):
    return 0.5 * (rw.lane_line(s) + 6.5)


def de_cam(tt, f):
    st = D.st(HA, f)
    if not st:
        return None, None
    sc_ = st["s"] - 8.0
    return road.point(sc_, de_x(sc_), 0.42), road.point(st["s"] + 25.0, 8.6, 0.8)


D.shot("H_de", t("HOOK_DE", 0.0), t("HOOK_DE", 2.2), "A", wA(WD0), lens=24, cam=de_cam)
# HOOK_FR 0.0-2.2 (the French cut opens here): the 60 repeater inside the works, large on the left, slow push; the
# hatchback (variant C, 85 km/h) passes it on the right and pulls away into the zone
D.shot("H_fr", t("HOOK_FR", 0.0), t("HOOK_FR", 2.2), "C", WC0 - (TRAILER_S - (SIGNW_S - 11.0)) / VC, lens=28,
       cam=lambda tt, f: (road.point(SIGNW_S - 7.0 + 0.8 * tt, 2.4, 2.0), road.point(SIGNW_S + 10.0, 3.4, 1.4)))

# SITUATION 0.0-3.5: high drone, white lines straight on, yellow lines curving left, the barrier with its arrow
D.shot("S_drone", t("SITUATION", 0.0), t("SITUATION", 3.5), "A", wA(ST - 330.0), lens=26,
       cam=lambda tt, f: (road.point(ST - 300.0 + 16.0 * tt, -2.0, 46.0), road.point(ST + 60.0, 8.5, 0.0)))
# SITUATION 3.5-7.0: low tracking camera ahead of the hatchback looking back: on the white line, the wall right
D.shot("S_front", t("SITUATION", 3.5), t("SITUATION", 7.0), "A", wA(ST + 60.0), lens=32,
       cam=lambda tt, f: (D.st(HA, f) and road.point(D.st(HA, f)["s"] + 15.0 - 0.6 * tt, Z.LANES[1] - 1.9, 1.5),
                          D.st(HA, f) and road.point(D.st(HA, f)["s"] - 6.0, Z.LANES[1] + 0.6, 0.9)))
# SITUATION 7.0-10.0: low chase, the wall close on the right, the artic ahead brakes, so does he (QA r3: replaces the
# driver's view, whose cockpit read as primitives)
D.shot("S_chase", t("SITUATION", 7.0), t("SITUATION", 10.0), "A", TBA - 1.0, lens=28,
       cam=D.chase(HA, back=7.5, side=-1.1, up=1.9, ahead=40.0, ahead_up=1.4, ahead_side=0.6))

# RULE 0.0-3.0: straight down over the shift: the yellow lines glow, the white ones fade, the yellow lane path shows
D.shot("R_top", t("RULE", 0.0), t("RULE", 3.0), "B", wB(ST - 120.0), lens=30,
       cam=lambda tt, f: (road.point(ST + 40.0 + 2.0 * tt, 8.0, 95.0 - 3.0 * tt), road.point(ST + 40.0 + 2.0 * tt, 8.0, 0.0),
                          road.frame(ST + 40.0)[2]))
# RULE 3.0-5.5: the 60 sign, traffic passing behind it
D.shot("R_sign", t("RULE", 3.0), t("RULE", 5.5), "B", wB(SIGN60_S - 120.0), lens=55,
       cam=lambda tt, f: (road.point(SIGN60_S - 11.0 + 0.5 * tt, 24.5, 1.7), road.point(SIGN60_S, 18.4, 2.0)))
# RULE 5.5-8.0: high chase, centred in the narrow left lane beside the truck
D.shot("R_chase", t("RULE", 5.5), t("RULE", 8.0), "B", T_LCB + 7.5, lens=28,
       cam=D.chase(HB, back=11.0, side=-1.6, up=4.2, ahead=40.0, ahead_up=0.8, ahead_side=1.2))

# COST 0.0-2.0: chase at 85 in the 60 zone, the trailer ahead on the right beyond the wall
D.shot("K_chase", t("COST", 0.0), t("COST", 2.0), "C", WC0 - 3.0, lens=30,
       cam=D.chase(HC, back=9.0, side=-1.2, up=1.7, ahead=26.0, ahead_up=1.0, ahead_side=2.6))
# COST 2.0-4.5, under the fine card (QA r7: the card sat over the trailer alone): raised view from upstream over the
# lane edge, pitched down, so the hatchback comes in from the bottom, passes the trailer's road rear (lamps, plate,
# flash window) and is flashed at COST 2.7, then pulls away up the lane; the camera pushes on slowly
K_FLASH = 2.7
D.shot("K_pass", t("COST", 2.0), t("COST", 4.5), "C", WC0 - 0.75, lens=24,
       cam=lambda tt, f: (road.point(TRAILER_S - 15.0 + 5.0 * tt, 9.3, 5.6 - 0.3 * tt),
                          road.point(TRAILER_S + 6.0 + 8.0 * tt, 10.4, 0.0)))

# CORRECT 0.0-3.0: drone, down to 60 before the zone, into the yellow shift
D.shot("C_drone", t("CORRECT", 0.0), t("CORRECT", 3.0), "B", WB0 - 0.5, lens=28,
       cam=D.chase(HB, back=30.0, side=-5.0, up=16.0, ahead=80.0, ahead_up=0.0, ahead_side=3.0))
# CORRECT 3.0-6.5: chase, centred in the narrow lane, a safe gap to the truck
D.shot("C_chase", t("CORRECT", 3.0), t("CORRECT", 6.5), "B", wB(ST + 110.0), lens=30,
       cam=D.chase(HB, back=8.0, side=-0.9, up=2.0, ahead=45.0, ahead_up=1.4, ahead_side=0.2))

Z.end_card(D, "E_card", t("END", 0.0), C.T, [("de-core", "123"), ("de-core", "274-80"), ("de-core", "274-60")],
           O["ASSETS"])

# ---------------------------------------------------------------- vehicles, cockpit, cameras, graphics
D.build_tracks()
D.protect |= {"artic", "truck"}
D.cull(650.0, {"S_drone": 1100.0, "H_drone": 800.0, "C_drone": 900.0, "R_top": 500.0})
D.cast(traffic, MODELS)
for key, sc_s, x, yaw in park:
    e = LM.instance(MODELS[key], env, "parked_" + key)
    e.matrix_world = road.matrix(sc_s, x, 0.012, yaw)
D.cameras()
# trailer flash as the hatchback reaches the trailer in K_pass (post_ep29.py puts the flash sound at COST 2.7 too)
f_flash = C.frame(t("COST", K_FLASH))
st_f = D.st(HC, f_flash)
if st_f:
    print(f"ep29 flash at frame {f_flash}: hatchback {st_f['s'] - TRAILER_S:+.1f} m from the trailer, "
          f"{st_f['v'] * 3.6:.0f} km/h", file=sys.stderr)
trailer.flash(f_flash)
Z.hud_flash(D.cam_obj("K_pass"), [f_flash], peak=0.45)

# RULE top: yellow glow, white fade, the yellow lane path
ym = bpy.data.materials["rw_yellow"]
pb = ym.node_tree.nodes["Principled BSDF"]
pb.inputs["Emission Color"].default_value = (1.0, 0.62, 0.02, 1)
for f, v in ((1, 0.0), (C.frame(t("RULE", 0.3)), 0.0), (C.frame(t("RULE", 0.8)), 3.0), (C.frame(t("RULE", 2.9)), 3.0),
             (C.frame(t("RULE", 3.0)), 0.0)):
    pb.inputs["Emission Strength"].default_value = v
    pb.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)
fade = bpy.data.materials.new("a4_white_fade")
fade.use_nodes = True
nt = fade.node_tree
p = nt.nodes["Principled BSDF"]
p.inputs["Base Color"].default_value = (0.032, 0.034, 0.037, 1)
p.inputs["Roughness"].default_value = 0.85
tr = nt.nodes.new("ShaderNodeBsdfTransparent")
mx = nt.nodes.new("ShaderNodeMixShader")
oi = nt.nodes.new("ShaderNodeObjectInfo")
sp = nt.nodes.new("ShaderNodeSeparateColor")
nt.links.new(oi.outputs["Color"], sp.inputs["Color"])
nt.links.new(sp.outputs[0], mx.inputs[0])
nt.links.new(tr.outputs[0], mx.inputs[1])
nt.links.new(p.outputs[0], mx.inputs[2])
nt.links.new(mx.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
for x in (6.5, 10.25, 14.15):
    w = 0.34 if x > 14 else 0.22
    o = road.strip(f"a4_white_fade_{x}", x - w / 2, x + w / 2, ST - 60.0, ST + 400.0, fade, env, dz0=0.014)
    o.visible_shadow = False
    Z.key_alpha(o, [(1, 0.0), (C.frame(t("RULE", 1.0)), 0.0), (C.frame(t("RULE", 1.8)), 0.92),
                    (C.frame(t("RULE", 2.95)), 0.92), (C.frame(t("RULE", 3.0)), 0.0)])
path_m = Z.fade_mat("a4_path_yellow", (1.0, 0.62, 0.03), 2.2)
pts = []
s = ST - 90.0
while s <= ST + 200.0:
    pts.append(s)
    s += 2.0
vs, fs = [], []
for i, s in enumerate(pts):
    x = xfun(1.0, s)
    w = 0.55
    vs += [tuple(road.point(s, x - w, 0.02)), tuple(road.point(s, x + w, 0.02))]
    if i:
        a = 2 * (i - 1)
        fs.append((a, a + 1, a + 3, a + 2))
s_h = pts[-1]
x_h = xfun(1.0, s_h)
b0 = len(vs)
vs += [tuple(road.point(s_h, x_h - 1.3, 0.02)), tuple(road.point(s_h, x_h + 1.3, 0.02)), tuple(road.point(s_h + 4.0, x_h, 0.02))]
fs.append((b0, b0 + 1, b0 + 2))
path = Z._mesh("a4_lane_path", vs, fs, path_m, env)
path.visible_shadow = False
Z.key_alpha(path, [(1, 0.0), (C.frame(t("RULE", 1.2)), 0.0), (C.frame(t("RULE", 1.9)), 0.85),
                   (C.frame(t("RULE", 2.95)), 0.85), (C.frame(t("RULE", 3.0)), 0.0)])
# call-outs: Zeichen 123 and the 60 sign in the drone shot
Z.hud_sign(D.cam_obj("S_drone"), ("de-core", "123"), t("SITUATION", 0.5), t("SITUATION", 3.4), u=0.22, v=0.74,
           wfrac=0.26, name="call_123")
Z.hud_sign(D.cam_obj("S_drone"), ("de-core", "274-60"), t("SITUATION", 1.2), t("SITUATION", 3.4), u=0.78, v=0.74,
           wfrac=0.24, name="call_60")

# ---------------------------------------------------------------- light and render
c0, th, fwd, right, _ = road.frame(ST)
stage.sky(road, (-fwd * 0.62 - right * 0.78).normalized(), O["ASSETS"], sun_elev_deg=13.0, sun_energy=4.6)
Z.golden(energy=4.6, ambient=0.62)
Z.finish(D, O)
