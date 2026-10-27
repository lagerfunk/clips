"""Drive Like a Local #13, Germany: the speed trailer: the tolerance is a measuring margin, not free speed. 9:16,
30 fps, 1077 frames (35.9 s), golden hour. Canonical order HOOK 0-2.2, SITUATION 2.2-12.2, RULE 12.2-20.2,
COST 20.2-25.8, CORRECT 25.8-32.3, END 32.3-35.9 (the per-language cuts reorder the segments, see post_ep13.py).
World: the episode 1 Autobahn on a 4 km road with a roadworks zone (kit/roadworks.py): advance signs at 2 km and 800 m,
the speed funnel 120, 100, 80 (Commons pictures), 531-11, the mobile barrier with its flashing arrow, Leitbaken on a
1:20 taper closing the right lane, yellow lines, a reverse taper and Zeichen 278-80 at the end. 320 m after the 80
sign a generic speed trailer (kit/enforcement.py, 3.15 x 1.52 x 1.84 m, no brand) stands behind the Baken; a fixed
camera column and a police laser check stand further on. No section control anywhere.
Traffic is simulated (ep13_zkit.Sim); the orange hatchback is choreographed:
  A (the mistake) drives into the 80 zone at 95 and passes the trailer at 105: flash;
  B (the right move) holds 80 from sign to sign: the lens stays dark.
COST is a small interior set (front door, letter slot, mat, an envelope with an address window, no emblem).
QA r3: the driver's-view shots are chase shots now (the cockpit read as primitives), the column is filmed from the
front and dressed (lens, visor, flash frame, flange, bands), the flash is the trailer's own flash window (no icon).
Run: python ep13_speed_trailer.py OUTDIR --frames 1-1077 --res 540 --samples 8 --assets ASSETS
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
import roadworks as RW  # noqa: E402
import stage  # noqa: E402
import vehicles as V  # noqa: E402
import world as W  # noqa: E402

O = Z.cli()
C = Z.Canon([("HOOK", 2.2), ("SITUATION", 10.0), ("RULE", 8.0), ("COST", 5.6), ("CORRECT", 6.5), ("END", 3.6)])
ST = 2300.0                       # taper start
SE = ST + 260.0                   # reverse taper start (end of the works)
ORANGE = (0.8, 0.22, 0.01)
HERO_L = V.KINDS["hatch"]["L"]
TR_S = ST + 120.0                 # speed trailer (the 80 sign stands at ST - 200)
COL_S, LAS_S = ST + 430.0, ST + 640.0
END278 = SE + 120.0

MODELS = {}


def prebuild(lib):
    allm, models = Z.fleet_models(lib)
    allm["hero"] = V.car("hatch", ORANGE, "hero", "QZ DL 13", metal=0.45, c=lib)
    MODELS.update(allm)
    MODELS["_sim"] = models


Z.prebuild(prebuild)
S = Z.world(O["ASSETS"], length=4000.0, s0=40.0, s1=3960.0, gantry_s=0, bridge_s=3150.0, phone_s=1100.0)
road, lib, env, traffic, M = S["road"], S["lib"], S["env"], S["traffic"], S["M"]
sc = bpy.context.scene
sc.render.fps = Z.FPS
sc.frame_start, sc.frame_end = 1, C.N
LM.setup(O["ASSETS"])

# ---------------------------------------------------------------- roadworks, end sign, enforcement
rw = RW.RoadWorks(road, M, env, lib, s_taper=ST, s_end=SE, road_s0=40.0, strict=False, dress=False)
rw.flash(1, C.N)
for side, x in ((1, 18.4), (-1, 1.35)):
    LM.road_sign(road, [("278-80", 0.75)], END278, x, env, f"z278_{side}", h=-0.06 if side > 0 else 0.0, bottom=1.6)
milled = W.noisy("a4_milled", (0.05, 0.05, 0.052), (0.1, 0.1, 0.1), 2.5, rough=0.95, bump=0.6)
road.strip("a4_milled_strip", rw.x_close1 + 0.9, 13.8, rw.s_t1 + 10.0, SE - 6.0, milled, env, dz0=0.012)
cone_m = LM.mat("rw_cone", (0.9, 0.18, 0.02), 0.45)
for s in range(int(rw.s_t1 + 30), int(SE - 10), 30):
    b = LM.MB()
    b.tube((0, 0, 0.02), (0, 0, 0.62), 0.12, 12)
    o = b.obj("a4_cone", cone_m, env)
    o.matrix_world = road.matrix(float(s), 13.4, 0.0)
    o.scale = (1.0, 1.0, 1.0)
trailer = EN.SpeedTrailer(road, env, TR_S, x=12.3, h=0.012)
trailer.light["peak"] = 2600.0

def trailer_rear(tr, plate="JX VM 131"):
    """(Copied from ep29, QA r14: the ep13 trailer rear showed a blank panel.) Road rear of the trailer: the end facing traffic (local +y), opposite the drawbar. A dark light board under the
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
column = EN.CameraColumn(road, env, COL_S, x=19.0)
laser = EN.LaserCheck(road, env, lib, LAS_S, x=19.6)
EN.assert_no_section_control()

# ---------------------------------------------------------------- traffic
SIMS = MODELS["_sim"]
LIM = [(ST - 1200.0, ST - 600.0, Z.kmh(120)), (ST - 600.0, ST - 200.0, Z.kmh(100)), (ST - 200.0, END278, Z.kmh(80))]


def base_sim(seed):
    sim = Z.Sim(0.0, 3960.0, seed=seed)
    sim.set_models(SIMS)
    sim.closures.append((2, ST - 700.0, rw.s_merge - 4.0, SE + 40.0))
    sim.limits.extend(LIM)
    for lane, hw, kinds, vr in ((0, 3.8, [("car", 1)], (33.0, 40.0)),
                                (1, 2.6, [("car", 6), ("van", 1)], (28.0, 34.0)),
                                (2, 2.7, [("car", 3), ("van", 1), ("truck", 4)], (23.0, 27.0))):
        sim.fill(lane, 0.0, 3900.0, hw, vr[0], kinds, v0_range=vr)
        sim.inflow.append((lane, hw * 1.15, kinds, vr[0], vr[1]))
    return sim


def xfun(lanef, s):
    l0 = max(0, min(2, int(math.floor(lanef))))
    l1 = min(2, l0 + 1)
    u = lanef - l0
    return rw.lane_x(l0, s) + (rw.lane_x(l1, s) - rw.lane_x(l0, s)) * u


# A: 95 into the 80 zone, a little more on, 105 past the trailer
WA0 = 30.0
KA = Z.Kin(WA0 - 30.0, ST - 200.0 - 30.0 * Z.kmh(95), Z.kmh(95),
           [(WA0 - 30.0, "v", Z.kmh(95)), (WA0 + 4.5, "v", Z.kmh(105), 0.9, 2.0)], WA0 + 30.0, L=HERO_L)


def wA(s):
    for i, ss in enumerate(KA.ss):
        if ss >= s:
            return KA.ts[i]
    return KA.ts[-1]


def heroA(T):
    s, v = KA.at(T)
    return dict(s=s, lane=1.0, v=v, ind=None)


simA = base_sim(13)
simA.script("hero", "hero", HERO_L, heroA)
simA.run(0.0, wA(SE + 300.0))
simA.drop_conflicts()

# B: 80 from the sign on, steady
WB0 = 30.0
KB = Z.Kin(WB0 - 30.0, ST - 260.0 - 30.0 * Z.kmh(100), Z.kmh(100),
           [(WB0 - 30.0, "v", Z.kmh(100)), (WB0 - 6.0, "v", Z.kmh(80), 1.5, 1.6)], WB0 + 40.0, L=HERO_L)


def wB(s):
    for i, ss in enumerate(KB.ss):
        if ss >= s:
            return KB.ts[i]
    return KB.ts[-1]


def heroB(T):
    s, v = KB.at(T)
    return dict(s=s, lane=1.0, v=v, ind=None)


simB = base_sim(17)
simB.script("hero", "hero", HERO_L, heroB)
simB.run(0.0, wB(SE + 300.0))
simB.drop_conflicts()

D = Z.Director(C, road, xfun)
D.variant("A", simA)
D.variant("B", simB)
D.variant("_set", None)
D.variant("_card", None)
t = C.t
HA, HB = "A:hero", "B:hero"
PASS_A = wA(TR_S)                  # world time when hero A passes the trailer


# ---------------------------------------------------------------- COST set: front door, letter slot, mat, envelope
def letter_set(origin=(6000.0, 300.0, 40.0)):
    c = W.coll("letter_set")
    ox, oy, oz = origin
    wall_m = W.noisy("a4_plaster", (0.62, 0.6, 0.56), (0.7, 0.68, 0.64), 6.0, rough=0.9, bump=0.05)
    floor_m = W.noisy("a4_floor", (0.24, 0.13, 0.06), (0.36, 0.2, 0.09), 1.5, rough=0.55, bump=0.08)
    door_m = Z._mat("a4_door", (0.78, 0.78, 0.76), 0.35)
    steel = Z._mat("a4_steel", (0.6, 0.61, 0.62), 0.28, metal=1.0)
    mat_m = W.noisy("a4_coir", (0.25, 0.16, 0.07), (0.42, 0.3, 0.14), 40.0, rough=0.98, bump=0.4)
    glass = Z._mat("a4_door_glass", (0.85, 0.88, 0.92), 0.2, emit=(1.0, 0.93, 0.82), estr=2.6)
    paper = Z._mat("a4_paper", (0.86, 0.85, 0.82), 0.6)
    win_m = Z._mat("a4_window", (0.62, 0.63, 0.65), 0.3)
    ink = Z._mat("a4_ink", (0.08, 0.08, 0.09), 0.5)

    def box(name, cx, cy, cz, sx, sy, sz, m):
        return Z._box(c, name, (ox + cx, oy + cy, oz + cz), (sx, sy, sz), m, None)
    box("set_floor", 0, 1.5, -0.02, 4.0, 3.4, 0.04, floor_m)
    box("set_ceiling", 0, 1.5, 2.62, 4.0, 3.4, 0.04, wall_m)
    box("set_wall_door", 0, -0.12, 1.3, 4.0, 0.1, 2.64, wall_m)
    box("set_wall_back", 0, 3.2, 1.3, 4.0, 0.1, 2.64, wall_m)
    box("set_wall_l", -2.0, 1.5, 1.3, 0.1, 3.4, 2.64, wall_m)
    box("set_wall_r", 2.0, 1.5, 1.3, 0.1, 3.4, 2.64, wall_m)
    box("set_door", 0, -0.04, 1.03, 1.0, 0.06, 2.06, door_m)
    box("set_door_glass", 0, -0.005, 1.62, 0.5, 0.01, 0.62, glass)
    box("set_slot_frame", 0, -0.003, 0.82, 0.34, 0.012, 0.08, steel)
    box("set_slot_dark", 0, 0.0035, 0.82, 0.27, 0.004, 0.036, Z._mat("a4_slot_dark", (0.01, 0.01, 0.01), 0.6))
    box("set_handle", 0.38, 0.03, 1.02, 0.03, 0.06, 0.16, steel)
    box("set_mat", 0, 0.42, 0.006, 0.8, 0.5, 0.012, mat_m)
    box("set_skirting", 0, -0.065, 0.05, 4.0, 0.02, 0.1, door_m)
    # envelope: paper, an address window and a few printed sender lines (no emblem of any authority)
    env_root = bpy.data.objects.new("envelope", None)
    c.objects.link(env_root)
    Z._box(c, "env_paper", (0, 0, 0), (0.22, 0.11, 0.003), paper, env_root)
    Z._box(c, "env_window", (0.03, -0.012, 0.0016), (0.09, 0.04, 0.0006), win_m, env_root)
    for k in range(3):
        Z._box(c, "env_line", (-0.07, 0.03 - 0.008 * k, 0.0016), (0.05, 0.0025, 0.0005), ink, env_root)
    # light: a warm ceiling lamp and the daylight through the door glass
    ld = bpy.data.lights.new("set_lamp", "AREA")
    ld.energy, ld.size, ld.color = 120.0, 0.8, (1.0, 0.86, 0.68)
    lo = bpy.data.objects.new("set_lamp", ld)
    c.objects.link(lo)
    lo.location = (ox + 0.2, oy + 1.2, oz + 2.5)
    # envelope animation: pushed through the slot, falls, lands on the mat, settles
    e = env_root
    e.rotation_mode = "XYZ"
    t0 = t("COST", 0.0)
    keys = [(t0 - 0.2, (0, -0.15, 0.82), (math.radians(90), 0, 0)), (t0 + 0.05, (0, -0.15, 0.82), (math.radians(90), 0, 0)),
            (t0 + 0.32, (0, 0.06, 0.82), (math.radians(90), 0, 0)),
            (t0 + 0.42, (0, 0.13, 0.78), (math.radians(60), math.radians(8), 0)),
            (t0 + 0.55, (0.02, 0.27, 0.35), (math.radians(20), math.radians(-6), math.radians(8))),
            (t0 + 0.62, (0.03, 0.34, 0.016), (0.0, 0.0, math.radians(14))),
            (t0 + 0.7, (0.03, 0.35, 0.016), (math.radians(-2), 0.0, math.radians(15))),
            (t0 + 0.8, (0.03, 0.35, 0.014), (0.0, 0.0, math.radians(15)))]
    for tt, loc, rot in keys:
        f = C.frame(tt)
        e.location = (ox + loc[0], oy + loc[1], oz + loc[2])
        e.rotation_euler = rot
        e.keyframe_insert("location", frame=max(1, f))
        e.keyframe_insert("rotation_euler", frame=max(1, f))
    return Vector(origin)


SET = letter_set()

# ---------------------------------------------------------------- shots
# HOOK 0.0-1.2: the trailer's nose: the flash fires as the hatchback passes
D.shot("H_nose", t("HOOK", 0.0), t("HOOK", 1.2), "A", PASS_A - 0.25, lens=55,
       cam=lambda tt, f: (road.point(TR_S - 6.2 + 0.4 * tt, 11.0, 1.45), road.point(TR_S - 1.2, 12.3, 1.15)))
# HOOK 1.2-2.2: pull back and round, the hatchback shoots on
D.shot("H_chase", t("HOOK", 1.2), t("HOOK", 2.2), "A", PASS_A + 0.7, lens=28,
       cam=lambda tt, f: (road.point(TR_S + 4.0 + 18.0 * tt, 10.6 - 1.2 * tt, 1.4 + 1.2 * tt),
                          road.point(D.st(HA, f)["s"] + 6.0, 7.2, 1.0)))
# SITUATION 0.0-3.0: drone over the 80 sign at the start of the works, the trailer 320 m on behind the Baken
D.shot("S_drone", t("SITUATION", 0.0), t("SITUATION", 3.0), "A", wA(ST - 262.0), lens=28,
       cam=lambda tt, f: (road.point(ST - 300.0 + 20.0 * tt, 3.0, 30.0), road.point(TR_S, 10.5, 0.0)))
# SITUATION 3.0-7.0: low chase behind the hatchback as it speeds up, the trailer growing ahead on the right
D.shot("S_chase", t("SITUATION", 3.0), t("SITUATION", 7.0), "A", PASS_A - 4.6, lens=26,
       cam=D.chase(HA, back=7.5, side=-0.9, up=1.9, ahead=42.0, ahead_up=1.2, ahead_side=1.4))
# SITUATION 7.0-10.0: on the verge in front of the trailer: its nose (lens and flash windows) right, the hatchback
# comes past on the left and the flash window fires as it passes (about 7.6)
D.shot("S_close", t("SITUATION", 7.0), t("SITUATION", 10.0), "A", PASS_A - 0.6, lens=30,
       cam=lambda tt, f: (road.point(TR_S - 9.5 + 0.25 * tt, 14.7, 1.3), road.point(TR_S - 0.6, 10.4, 1.05)))

# RULE 0.0-2.7: the three tools: trailer, fixed column, laser check (0.9 s each)
D.shot("R_trailer", t("RULE", 0.0), t("RULE", 0.9), "B", wB(TR_S - 60.0), lens=45,
       cam=lambda tt, f: (road.point(TR_S + 5.0 + 1.0 * tt, 10.4 + 0.5 * tt, 1.2), road.point(TR_S, 12.3, 1.0)))
D.shot("R_column", t("RULE", 0.9), t("RULE", 1.8), "B", wB(COL_S - 70.0), lens=40,
       cam=lambda tt, f: (road.point(COL_S - 5.2 - 0.4 * tt, 16.7 + 0.2 * tt, 1.5), road.point(COL_S, 19.0, 1.85)))
D.shot("R_laser", t("RULE", 1.8), t("RULE", 2.7), "B", wB(LAS_S - 70.0), lens=45,
       cam=lambda tt, f: (road.point(LAS_S + 4.0 + 0.6 * tt, 17.2, 1.5), road.point(LAS_S, 19.6, 1.45)))
# RULE 2.7-5.4: drone, the three devices on the same road, each with its beam
D.shot("R_drone", t("RULE", 2.7), t("RULE", 5.4), "B", wB(ST + 60.0), lens=26,
       cam=lambda tt, f: (road.point(ST - 40.0 + 10.0 * tt, 4.0, 62.0), road.point(ST + 420.0, 12.0, 0.0)))
# RULE 5.4-8.0: straight down, the hatchback passes the trailer; the speed bar (measured, notch, counted)
D.shot("R_top", t("RULE", 5.4), t("RULE", 8.0), "B", wB(TR_S - 30.0), lens=32,
       cam=lambda tt, f: (road.point(TR_S + 2.0 + 3.0 * tt, 9.0, 34.0), road.point(TR_S + 2.0 + 3.0 * tt, 9.0, 0.0),
                          road.frame(TR_S)[2]))

# COST 0.0-2.2: the letter drops through the slot onto the mat
D.shot("K_slot", t("COST", 0.0), t("COST", 2.2), "_set", 0.0, lens=32,
       cam=lambda tt, f: (SET + Vector((0.32 - 0.04 * tt, 1.35 - 0.05 * tt, 0.32)), SET + Vector((0.0, 0.1, 0.42))))
# COST 2.2-5.6: top-down on the envelope on the mat (the fine cards sit above it)
D.shot("K_mat", t("COST", 2.2), t("COST", 5.6), "_set", 0.0, lens=40,
       cam=lambda tt, f: (SET + Vector((0.03, 0.56, 1.05 - 0.05 * tt)), SET + Vector((0.03, 0.56, 0.0)),
                          Vector((0, 1, 0))))

# CORRECT 0.0-2.5: chase at 80, the 80 sign ahead on the right and past it
D.shot("C_chase", t("CORRECT", 0.0), t("CORRECT", 2.5), "B", wB(ST - 252.0), lens=26,
       cam=D.chase(HB, back=7.5, side=-1.0, up=2.0, ahead=45.0, ahead_up=1.6, ahead_side=1.8))
# CORRECT 2.5-6.5: drone behind and above: past the trailer at the limit, the lens stays dark; the zone ends ahead
D.shot("C_drone", t("CORRECT", 2.5), t("CORRECT", 6.5), "B", wB(TR_S) - 0.3, lens=28,
       cam=D.chase(HB, back=lambda u: 26.0 + 1.0 * u, side=-4.5, up=lambda u: 13.0 + 0.6 * u, ahead=110.0, ahead_up=0.0,
                   ahead_side=4.0))

Z.end_card(D, "E_card", t("END", 0.0), C.T, [("de-core", "274-80"), ("de-core", "278-80")], O["ASSETS"])

# ---------------------------------------------------------------- vehicles, cameras, graphics
D.build_tracks()
D.cull(650.0, {"S_drone": 1000.0, "R_drone": 1000.0, "C_drone": 900.0})
D.cast(traffic, MODELS)
D.cameras()


def column_dress(col):
    """Front details on the plain kit column (QA r3: it read as a grey box): a round lens with a steel bezel in the
    lower window, a visor over it, a steel frame round the flash window, a base flange and two seam bands."""
    g = col.root
    cc = g.users_collection[0]
    steel = Z._mat("a4_col_steel", (0.55, 0.56, 0.57), 0.3, metal=1.0)
    seam = Z._mat("a4_col_seam", (0.12, 0.12, 0.13), 0.6)
    lens_m = Z._mat("a4_col_lens", (0.01, 0.012, 0.02), 0.04, metal=0.2)
    r = 0.32
    fy = r * math.cos(math.pi / 6) + 0.004
    h = col.height

    def hexband(name, rr, z0, z1, m):
        vs = [(rr * math.cos(2 * math.pi * k / 6), rr * math.sin(2 * math.pi * k / 6), z) for z in (z0, z1)
              for k in range(6)]
        fs = [(k, (k + 1) % 6, 6 + (k + 1) % 6, 6 + k) for k in range(6)] + [tuple(range(5, -1, -1)),
                                                                            tuple(range(6, 12))]
        o = Z._mesh(name, vs, fs, m, cc)
        o.parent = g
        return o

    def disc(name, rad, y, z, m, n=28, r_in=None):
        if r_in is None:
            vs = [(rad * math.cos(2 * math.pi * k / n), y, z + rad * math.sin(2 * math.pi * k / n)) for k in range(n)]
            fs = [tuple(range(n))]
        else:
            vs = []
            for k in range(n):
                a = 2 * math.pi * k / n
                vs += [(r_in * math.cos(a), y, z + r_in * math.sin(a)), (rad * math.cos(a), y, z + rad * math.sin(a))]
            fs = [(2 * k, 2 * ((k + 1) % n), 2 * ((k + 1) % n) + 1, 2 * k + 1) for k in range(n)]
        o = Z._mesh(name, vs, fs, m, cc)
        o.parent = g
        return o

    parts = [hexband("col_flange", 0.40, 0.24, 0.30, steel), hexband("col_band1", r + 0.006, 1.02, 1.05, seam),
             hexband("col_band2", r + 0.006, 1.86, 1.89, seam)]
    zl = h - 0.8
    parts.append(disc("col_lens", 0.072, fy + 0.006, zl, lens_m))
    parts.append(disc("col_bezel", 0.092, fy + 0.008, zl, steel, r_in=0.07))
    parts.append(Z._box(cc, "col_visor", (0.0, fy + 0.05, h - 0.52), (0.30, 0.10, 0.018), steel, g))
    zf = h - 1.4
    for nm, cx, cz, sx, sz in (("t", 0.0, zf + 0.1, 0.27, 0.02), ("b", 0.0, zf - 0.1, 0.27, 0.02),
                               ("l", -0.125, zf, 0.02, 0.2), ("r", 0.125, zf, 0.02, 0.2)):
        parts.append(Z._box(cc, "col_flashframe_" + nm, (cx, fy + 0.006, cz), (sx, 0.012, sz), steel, g))
    return parts


column_dress(column)

# flashes: whenever hero A passes the trailer on screen (HOOK close-up and the SITUATION close-up on its nose)
for name in ("H_nose", "S_close"):
    co, f0, f1 = D.cams[name]
    for f in range(f0, f1 + 1):
        st = D.st(HA, f)
        prev = D.st(HA, f - 1)
        if st and prev and prev["s"] < TR_S + 1.0 <= st["s"]:
            trailer.flash(f)
            Z.hud_flash(co, [f], peak=0.55 if name == "H_nose" else 0.4, name="flash_" + name)
            break

# call-outs: the 80 sign (SITUATION drone), the end of the limit (CORRECT drone)
Z.hud_sign(D.cam_obj("S_drone"), ("de-core", "274-80"), t("SITUATION", 0.5), t("SITUATION", 2.95), u=0.76, v=0.72,
           wfrac=0.26, name="call_80")
Z.hud_sign(D.cam_obj("C_drone"), ("de-core", "278-80"), t("CORRECT", 4.6), t("CORRECT", 6.45), u=0.76, v=0.72,
           wfrac=0.26, name="call_278")

# beams in the RULE drone: a translucent red fan from each device into the lanes
beam_m = Z.fade_mat("a4_beam", (1.0, 0.08, 0.04), 2.5)
for s_dev, x_dev, nm in ((TR_S, 12.3, "trailer"), (COL_S, 19.0, "column"), (LAS_S, 19.6, "laser")):
    vs = [tuple(road.point(s_dev - 1.5, x_dev, 0.9)), tuple(road.point(s_dev - 46.0, 3.2, 0.05)),
          tuple(road.point(s_dev - 46.0, 9.2, 0.05))]
    b = Z._mesh("a4_beam_" + nm, vs, [(0, 1, 2)], beam_m, env)
    b.visible_shadow = False
    Z.key_alpha(b, [(1, 0.0), (C.frame(t("RULE", 2.9)), 0.0), (C.frame(t("RULE", 3.3)), 0.45),
                    (C.frame(t("RULE", 5.35)), 0.45), (C.frame(t("RULE", 5.4)), 0.0)])

# speed bar (RULE top): measured value grows, a notch is taken off (tolerance), the rest counts; no numerals
co = D.cam_obj("R_top")
t0 = t("RULE", 5.4)
Z.hud_bar(co, "bar_measured", 0.14, 0.7, 0.62, 0.028, (0.95, 0.95, 0.95),
          [(0.0, 0.0), (t0 + 0.3, 0.0), (t0 + 1.2, 0.62), (t0 + 2.6, 0.62)], strength=2.2)
Z.hud_bar(co, "bar_counted", 0.14, 0.7, 0.57, 0.034, (1.0, 0.72, 0.0),
          [(0.0, 0.0), (t0 + 1.7, 0.0), (t0 + 2.0, 0.57), (t0 + 2.6, 0.57)], strength=2.6)
notch = Z.hud_bar(co, "bar_notch", 0.71, 0.7, 0.05, 0.05, (1.0, 0.1, 0.05),
                  [(0.0, 0.05), (t0 + 2.6, 0.05)], strength=3.0)
Z.show_keys(notch, t0 + 1.25, t0 + 2.0)

# ---------------------------------------------------------------- light and render
c0, th, fwd, right, _ = road.frame(TR_S)
stage.sky(road, (-fwd * 0.55 + right * 0.83).normalized(), O["ASSETS"], sun_elev_deg=12.0, sun_energy=4.7)
Z.golden(energy=4.8, ambient=0.6)
Z.finish(D, O)
