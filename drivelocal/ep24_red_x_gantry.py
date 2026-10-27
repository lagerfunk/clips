"""Drive Like a Local #24, Germany: the red X over your lane (StVO section 37 Abs. 3 lane signals). 9:16, 30 fps,
1044 frames (34.8 s), golden hour. Canonical order HOOK 0-2.2, SITUATION 2.2-12.2, RULE 12.2-20.2, COST 20.2-24.7,
CORRECT 24.7-31.2, END 31.2-34.8 (the per-language cuts reorder the segments, see post_ep24.py).
World: the episode 1 Autobahn on a 4 km road. Lane-control gantries 1,750 m apart: G1 shows the flashing yellow arrow
(change right) over the left lane and 100 on the others, G2 the red X over the left lane and green arrows over the
others. 66 m past G2 a police estate (blue lights) protects a crashed saloon (hazards) in the left lane.
Traffic is simulated (ep13_zkit.Sim: keep right, overtake left only, trucks never in the left lane, indicators on every
lane change, brake lights from deceleration); the teal hatchback is choreographed:
  A (the mistake) stays in the left lane at 110 km/h under both signals and brakes hard 6 m short of the police car;
  B (the right move) indicates at G1, moves to the middle lane and passes the incident slowly under the green arrow;
  C (the cost) is stopped by a police estate and both pull onto the hard shoulder.
Run: python ep24_red_x_gantry.py OUTDIR --frames 1-1044 --res 540 --samples 8 --assets ASSETS [--stills 60,300]
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit"), os.path.join(HERE, "..", "ep13")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import ep13_zkit as Z  # noqa: E402
import lanemgmt as LM  # noqa: E402
import stage  # noqa: E402
import vehicles as V  # noqa: E402
import world as W  # noqa: E402

O = Z.cli()
C = Z.Canon([("HOOK", 2.2), ("SITUATION", 10.0), ("RULE", 8.0), ("COST", 4.5), ("CORRECT", 6.5), ("END", 3.6)])
G1, G2 = 1150.0, 2900.0             # lane-control gantries, 1,750 m apart (spec 1.5 to 2 km)
P_REAR = G2 + 66.0                  # rear of the police estate protecting the crash (left lane)
TEAL = (0.006, 0.26, 0.27)
V110, V100 = Z.kmh(110), Z.kmh(100)
HERO_L = V.KINDS["hatch"]["L"]

MODELS = {}


def prebuild(lib):
    allm, models = Z.fleet_models(lib)
    allm["hero"] = V.car("hatch", TEAL, "hero", "JX DL 24", metal=0.45, c=lib)
    allm["police"] = V.car("estate", None, "police", "QX PO 112", police=True, c=lib)
    allm["crash"] = V.car("saloon", (0.3, 0.31, 0.32), "crash", "QZ UF 17", metal=0.5, c=lib)
    MODELS.update(allm)
    MODELS["_sim"] = models


Z.prebuild(prebuild)
S = Z.world(O["ASSETS"], length=4000.0, s0=40.0, s1=3960.0, gantry_s=0, bridge_s=3330.0, phone_s=2480.0)
road, lib, env, traffic, M = S["road"], S["lib"], S["env"], S["traffic"], S["M"]
sc = bpy.context.scene
sc.render.fps = Z.FPS
sc.frame_start, sc.frame_end = 1, C.N
LM.setup(O["ASSETS"])

# ---------------------------------------------------------------- gantries
g1 = LM.Gantry(road, M, env, lib, G1)
g2 = LM.Gantry(road, M, env, lib, G2)
g1.show(1, speed=100, signals={0: "R"}, warn="101")
g2.show(1, signals={0: "X", 1: "arrow", 2: "arrow"})

# ---------------------------------------------------------------- the incident: hazard triangle on the left edge
tri_m = Z._mat("a4_triangle_red", (0.75, 0.02, 0.01), 0.3, emit=(1, 0.05, 0.02), estr=0.6)
tri_w = Z._mat("a4_triangle_white", (0.9, 0.9, 0.9), 0.4)
tri = bpy.data.objects.new("hazard_triangle", None)
env.objects.link(tri)
tri.matrix_world = road.matrix(P_REAR - 75.0, 3.25, 0.0)
for nm, r0, r1, mm in (("tri_outer", 0.25, 0.19, tri_m), ("tri_inner", 0.19, 0.0, tri_w)):
    vs = []
    for k in range(3):
        a = math.radians(90 + 120 * k)
        vs.append((r0 * math.cos(a), 0.0, 0.29 + r0 * math.sin(a)))
    for k in range(3):
        a = math.radians(90 + 120 * k)
        vs.append((r1 * math.cos(a), -0.002, 0.29 + r1 * math.sin(a)))
    fs = [(0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)] if r1 > 0 else [(0, 1, 2)]
    o = Z._mesh(nm, vs, fs, mm, env)
    o.parent = tri
leg = Z._box(env, "tri_stand", (0, 0.1, 0.03), (0.42, 0.24, 0.02), Z._mat("a4_tri_stand", (0.05, 0.05, 0.05), 0.5), tri)

# ---------------------------------------------------------------- traffic simulations
SIMS = MODELS["_sim"]


def base_sim(seed):
    sim = Z.Sim(0.0, 3960.0, seed=seed)
    sim.set_models(SIMS)
    # the left lane is cleared before the red X: everyone leaves it after G1's yellow arrow, blocked from G2 - 80 m
    sim.closures.append((0, G1 + 20.0, G2 - 80.0, P_REAR + 40.0))
    sim.limits.append((G1, 3960.0, V100))
    for lane, hw, kinds, vr in ((0, 3.4, [("car", 1)], (34.0, 41.0)),
                                (1, 2.3, [("car", 6), ("van", 1)], (29.0, 35.0)),
                                (2, 2.5, [("car", 3), ("van", 1), ("truck", 4)], (24.0, 30.0))):
        sim.fill(lane, 0.0, 3900.0, hw, vr[0], kinds, v0_range=vr)
        sim.inflow.append((lane, hw * 1.15, kinds, vr[0], vr[1]))
    return sim


def statics(sim):
    """Police estate (blue lights) and the crashed saloon (hazards, turned a little) in the left lane."""
    pol_s = P_REAR + V.KINDS["estate"]["L"] / 2
    sim.script("police", "police", V.KINDS["estate"]["L"],
               lambda T: dict(s=pol_s, lane=0.0, x=4.55, v=0.0, ind=None, beacon=True))
    crash_s = P_REAR + V.KINDS["estate"]["L"] + 2.2 + V.KINDS["saloon"]["L"] / 2
    sim.script("crash", "crash", V.KINDS["saloon"]["L"],
               lambda T: dict(s=crash_s, lane=0.0, x=4.1, v=0.0, ind="H", yaw_off=0.32))


# A: the hero ignores both gantries and brakes hard (10.5 m/s2) 6 m short of the police car
WA0 = 15.0                                     # world time when the hero is at G1 - 300
S_STOP = P_REAR - 6.0                          # where the hero's front comes to rest
D_BRAKE = V110 ** 2 / (2 * 10.5)
S_B = S_STOP - D_BRAKE - HERO_L / 2            # centre where braking starts
TB = WA0 + (S_B - (G1 - 300.0)) / V110
KA = Z.Kin(WA0 - 20.0, G1 - 300.0 - 20.0 * V110, V110, [(WA0 - 20.0, "v", V110), (TB, "stop", S_STOP)],
           TB + 12.0, L=HERO_L)


def wA(s):
    """World time at which hero A's centre is at s (before braking)."""
    return WA0 + (s - (G1 - 300.0)) / V110


def heroA(T):
    s, v = KA.at(T)
    return dict(s=s, lane=0.0, v=v, ind="H" if (v < 0.05 and T > TB + 1.5) else None)


simA = base_sim(11)
statics(simA)
simA.script("hero", "hero", HERO_L, heroA)
simA.run(0.0, TB + 8.0)
simA.drop_conflicts()

# B: indicator at G1 - 50, middle lane before G1, 100 km/h, slows to 70 then 60 km/h past the incident
WB0 = 15.0
KB = Z.Kin(WB0 - 20.0, G1 - 300.0 - 20 * V110, V110,
           [(WB0 - 20.0, "v", V110), (WB0 + 8.2, "v", V100, 2.0, 1.5)], WB0 + 140.0, L=HERO_L)
TBI = WB0 + (250.0) / V110                     # indicator on 50 m before G1


def wB(s):
    for i, ss in enumerate(KB.ss):
        if ss >= s:
            return KB.ts[i]
    return KB.ts[-1]


T_G2B = None


def kb2_plan():
    t1 = wB(G2 - 260.0)
    t2 = wB(G2 + 20.0)
    return Z.Kin(WB0 - 20.0, KB.ss[0], V110, [(WB0 - 20.0, "v", V110), (WB0 + 8.2, "v", V100, 2.0, 1.5),
                                              (t1, "v", Z.kmh(72), 2.0, 1.6), (t2 - 1.0, "v", Z.kmh(58), 2.0, 1.4),
                                              (t2 + 6.5, "v", V100, 1.6, 2.0)], WB0 + 140.0, L=HERO_L)


KB = kb2_plan()


def heroB(T):
    s, v = KB.at(T)
    lane = Z.lane_change(T, TBI + 1.0, 1.4, 0.0, 1.0)
    ind = "R" if TBI <= T < TBI + 2.7 else None
    return dict(s=s, lane=lane, v=v, ind=ind)


simB = base_sim(11)
statics(simB)
simB.script("hero", "hero", HERO_L, heroB)
simB.run(0.0, wB(G2 + 160.0) + 2.0)
simB.drop_conflicts()

# C: after the incident the police estate (blue lights) follows the hero onto the hard shoulder
WC0 = 40.0
SC0 = G2 + 230.0
KC = Z.Kin(WC0 - 10.0, SC0 - 10 * Z.kmh(85), Z.kmh(85), [(WC0 - 10.0, "v", Z.kmh(85)), (WC0 + 3.4, "v", Z.kmh(55), 1.5, 2.2),
                                                          (WC0 + 5.6, "stop", SC0 + 168.0)], WC0 + 20.0, L=HERO_L)
SH_X = 15.45                                    # hard shoulder centre


def heroC(T):
    s, v = KC.at(T)
    if T < WC0 + 2.4:
        x = Z.LANES[1]
    else:
        u = Z.smoother((T - (WC0 + 2.4)) / 4.2)
        x = Z.LANES[1] + (SH_X - Z.LANES[1]) * u
    ind = "R" if WC0 + 1.4 <= T < WC0 + 6.8 else ("H" if v < 0.05 else None)
    lane = 1.0 + min(1.0, max(0.0, (x - Z.LANES[1]) / 3.75))
    return dict(s=s, lane=lane, x=x, v=v, ind=ind)


KP = Z.Kin(WC0 - 10.0, SC0 - 38.0 - 10 * Z.kmh(110), Z.kmh(110),
           [(WC0 - 10.0, "v", Z.kmh(110)), (WC0 + 0.6, "v", Z.kmh(88), 2.0, 2.5), (WC0 + 3.0, "v", Z.kmh(55), 1.5, 2.6),
            (WC0 + 5.2, "stop", SC0 + 168.0 - HERO_L - 7.0)], WC0 + 20.0, L=V.KINDS["estate"]["L"])


def policeC(T):
    s, v = KP.at(T)
    if T < WC0 + 0.4:
        x = Z.LANES[0]
    elif T < WC0 + 2.6:
        x = Z.LANES[0] + (Z.LANES[1] - Z.LANES[0]) * Z.smoother((T - (WC0 + 0.4)) / 2.0)
    else:
        x = Z.LANES[1] + (SH_X - Z.LANES[1]) * Z.smoother((T - (WC0 + 2.6)) / 4.4)
    ind = "R" if WC0 - 0.2 <= T < WC0 + 7.0 else None
    lane = (x - Z.LANES[0]) / 3.75
    return dict(s=s, lane=lane, x=x, v=v, ind=ind, beacon=True)


simC = base_sim(23)
statics(simC)
simC.script("hero", "hero", HERO_L, heroC)
simC.script("police2", "police", V.KINDS["estate"]["L"], policeC)
simC.run(WC0 - 6.0, WC0 + 16.0)
simC.drop_conflicts()


def xfun(lanef, s):
    l0 = max(0, min(2, int(math.floor(lanef))))
    l1 = min(2, l0 + 1)
    u = lanef - l0
    return Z.LANES[l0] + (Z.LANES[l1] - Z.LANES[l0]) * u


D = Z.Director(C, road, xfun)
D.variant("A", simA)
D.variant("B", simB)
D.variant("C", simC)
D.variant("_card", None)

# ---------------------------------------------------------------- shots (canonical times)
t = C.t
HA, HB, HC, PC = "A:hero", "B:hero", "C:hero", "C:police2"


def lerp(a, b, u):
    return a + (b - a) * u


# HOOK 0.0-1.3: drone pushing in on G2, the red X over the left lane, the hatchback below heading for it
D.shot("H_drone", t("HOOK", 0.0), t("HOOK", 1.3), "A", wA(G2 - 82.0), lens=30,
       cam=lambda tt, f: (road.point(G2 - 108.0 + 24.0 * tt, 2.6, 11.5 - 0.6 * tt),
                          road.point(G2 + 6.0, 7.4, 5.0 - 0.3 * tt)))
# HOOK 1.3-2.2: low chase, the hatchback goes straight under the red X
D.shot("H_chase", t("HOOK", 1.3), t("HOOK", 2.2), "A", wA(G2 - 26.0), lens=26,
       cam=D.chase(HA, back=7.2, side=-0.7, up=1.25, ahead=34.0, ahead_up=lambda u: 6.5 - 3.0 * u, ahead_side=0.3))

# SITUATION 0.0-2.8: high drone behind the hatchback, G2 with its red X, the blue lights beyond
D.shot("S_drone", t("SITUATION", 0.0), t("SITUATION", 2.8), "A", wA(G2 - 205.0), lens=28,
       cam=lambda tt, f: (road.point(G2 - 262.0 + 26.0 * tt, 1.2, 36.0 - 1.5 * tt),
                          road.point(P_REAR + 10.0, 7.0, 0.0)))
# SITUATION 2.8-4.4: chase towards G1, the yellow arrow flashing, cars ahead indicate and move right; the shot ends
# with the camera still about 20 m short of the gantry (QA r3: the camera flew through the truss at the old end)
D.shot("S_g1", t("SITUATION", 2.8), t("SITUATION", 4.4), "A", wA(G1 - 58.0), lens=28,
       cam=D.chase(HA, back=10.5, side=1.6, up=2.6, ahead=60.0, ahead_up=4.2, ahead_side=1.4))
# SITUATION 4.4-6.0: chase towards G2, the red X ahead, the left lane empty but for him
D.shot("S_g2", t("SITUATION", 4.4), t("SITUATION", 6.0), "A", wA(G2 - 60.0), lens=30,
       cam=D.chase(HA, back=9.0, side=-1.0, up=2.2, ahead=55.0, ahead_up=5.0, ahead_side=1.2))
# SITUATION 6.0-10.0: from above the median past the crash, looking back: the hatchback comes on under the red X
# (G2 at the top of the frame), brakes hard and stops 6 m short of the police car, the crash in the foreground
# (QA r3: replaces the driver's view, whose cockpit read as primitives)
POV_A0 = wA(G2 - 60.0) + 1.6
D.shot("S_crash", t("SITUATION", 6.0), t("SITUATION", 10.0), "A", POV_A0, lens=28,
       cam=lambda tt, f: (road.point(G2 + 88.0 - 0.4 * tt, 1.0, 5.2 - 0.15 * tt),
                          road.point(G2 + 8.0, 5.6, 2.6 - 0.25 * tt)))

# RULE 0.0-2.7: close-up of the red X on G2 (traffic passes below in the open lanes)
WR = wB(G2 - 1400.0)


def gantry_cam(s_g, x_cam, z_cam, dist, x_tgt, drift=1.5, pull=None):
    """Low camera beside the lanes looking up at one LED unit (its face is about 1 m upstream of the truss);
    pull(tt) 0..1 dollies back and up to the whole gantry."""
    def fn(tt, f):
        k = pull(tt) if pull else 0.0
        pos = road.point(s_g - dist - drift * tt - k * 30.0, x_cam + k * 1.4, z_cam + k * 1.6)
        tgt = road.point(s_g - 1.0, x_tgt + k * (10.0 - x_tgt) * 0.75, 6.1 - k * 1.6)
        return pos, tgt
    return fn


D.shot("R_x", t("RULE", 0.0), t("RULE", 2.7), "B", WR + 30.0, lens=55,
       cam=gantry_cam(G2, 3.6, 1.7, 14.0, Z.LANES[0]))
# RULE 2.7-5.4: close-up of the flashing yellow arrow on G1, cars below indicate and move right
D.shot("R_arrow", t("RULE", 2.7), t("RULE", 5.4), "B", wB(G1 - 420.0), lens=55,
       cam=gantry_cam(G1, 1.7, 2.0, 15.0, Z.LANES[0]))
# RULE 5.4-8.0: green arrow over the middle lane, pulling back to the whole gantry
D.shot("R_green", t("RULE", 5.4), t("RULE", 8.0), "B", WR + 40.0, lens=50,
       cam=gantry_cam(G2, 3.4, 2.0, 14.0, Z.LANES[1], drift=1.0, pull=lambda tt: Z.smoother((tt - 0.5) / 2.0)))

# COST 0.0-2.2: low chase behind the police estate, blue lights, it pulls in behind the hatchback
D.shot("K_chase", t("COST", 0.0), t("COST", 2.2), "C", WC0 - 0.2, lens=30,
       cam=D.chase(PC, back=8.0, side=-1.8, up=1.5, ahead=36.0, ahead_up=1.4, ahead_side=1.2))
# COST 2.2-4.5: top view, both stopped on the hard shoulder past the incident
SK = SC0 + 168.0 - HERO_L / 2 - 4.0
D.shot("K_top", t("COST", 2.2), t("COST", 4.5), "C", WC0 + 9.0, lens=34,
       cam=lambda tt, f: (road.point(SK - 4.0 + 0.5 * tt, 12.0, 30.0 - 0.8 * tt), road.point(SK + 3.0, 13.4, 0.0),
                          road.frame(SK)[2]))

# CORRECT 0.0-3.0: drone, the hatchback sees the yellow arrow at G1, indicates and moves to the middle lane
D.shot("C_drone", t("CORRECT", 0.0), t("CORRECT", 3.0), "B", TBI - 0.5, lens=28,
       cam=D.chase(HB, back=lambda u: 34.0 - 2.0 * u, side=-6.0, up=lambda u: 17.0 - 0.8 * u, ahead=70.0,
                   ahead_up=2.0, ahead_side=3.0))
# CORRECT 3.0-6.5: chase in the middle lane under the green arrow, slowly past the police car and the crash
D.shot("C_chase", t("CORRECT", 3.0), t("CORRECT", 6.5), "B", wB(G2 - 6.0), lens=28,
       cam=D.chase(HB, back=8.5, side=1.4, up=2.1, ahead=40.0, ahead_up=1.6, ahead_side=-1.6))

# END: road-grey card with the three lane signals
Z.end_card(D, "E_card", t("END", 0.0), C.T, [], O["ASSETS"], leds=["X", "R", "arrow"])

# ---------------------------------------------------------------- vehicles, cockpit, cameras
D.build_tracks()
D.protect |= {"police", "crash", "police2"}
D.cull(700.0, {"S_drone": 1100.0, "C_drone": 900.0, "H_drone": 900.0})
D.cast(traffic, MODELS)
D.cameras()

# ---------------------------------------------------------------- light and render
c0, th, fwd, right, _ = road.frame(G2)
stage.sky(road, (-fwd * 0.88 + right * 0.47).normalized(), O["ASSETS"], sun_elev_deg=11.0, sun_energy=4.6)
Z.golden(energy=4.8, ambient=0.6)
Z.finish(D, O)
