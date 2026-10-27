"""Drive Like a Local #16, Germany (standard): parked facing the wrong way. In a two-way street you park on the
right, facing the way of traffic; both sides only in a one-way street (StVO 12 (4)). 9:16, 30 fps, no voice.
Set: the plain town stage with a 9 m residential street (north arm) with marked parallel bays on both kerbs
(kit/parking.py: 2.00 m bays, 5.70 m, end bays 5.20 m), one free gap on the left; the east arm is shown as a one-way
street (both rows facing east, Zeichen 220-20 from Commons). White rental hatchback (hero), an oncoming hatchback,
a parking attendant (kit/figures.py, no crest), a plain yellow ticket (no crest, no text). Day. The rule's arrows
and boxes are ASS drawings (post_ep16.py); the one-way sign is Zeichen 220-20 on its post.
Canonical timeline (English order; finish_ep cuts each language's order from ep16_edit.json):
HOOK 0-2.2, SITUATION 2.2-12.2, RULE 12.2-19.2, COST 19.2-23.7, CORRECT 23.7-30.2, END 30.2-32.9.
Run: python ep16_parking_direction.py OUTDIR --frames 1-987 --res 540 --samples 8 --assets ASSETS [--stills 30,300]
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "ep10")]
import ep10_za5kit as K  # noqa: E402
from ep10_za5kit import Vector, SG, TN, TP, TS, FPS, UP_N  # noqa: E402
import parking as PK  # noqa: E402

TL = K.Timeline([("HOOK", 2.2), ("SITUATION", 10.0), ("RULE", 7.0), ("COST", 4.5), ("CORRECT", 6.5), ("END", 2.7)])
N = TL.N
HX, HY = 4.5, 4.0
S = TS.build(K.ASSETS, "plain", seed=16, hx=HX, hy=HY, parked=False, heroes=[
    ("hatch", (0.86, 0.87, 0.86), "hero", "QX PR 412", 0.35)])
SG.setup(K.ASSETS)
T, env, lib, traf, fleet, J = S["T"], S["env"], S["lib"], S["traffic"], S["fleet"], S["J"]
H = S["heroes"]["hero"]
cars = {k: v for k, v in fleet.items() if not k.startswith("van")}

# ------------------------------------------------------------------ the parking street (north arm, two-way)
stN = TP.arm(J, "N")
NB = 7
LEN = 2 * PK.BAY_L_END + (NB - 2) * PK.BAY_L
PS = PK.street(T, env, stN, cars, n=NB, sides=(+1, -1), s0={+1: 14.0, -1: 14.0 + LEN}, empty={(-1, 3), (+1, 5)},
               seed=7, signs=False)
rowR, rowL = PS["rows"][+1], PS["rows"][-1]
pW, yawW = PK.bay_pose(rowL, 3, wrong_way=True)            # the hero, nose against the traffic on that side
H["yaw0"] = yawW
LANE = 1.25
yb = pW.y
P_in = K.line((LANE, yb - 60.0), (LANE, yb - 13.0), (-0.6, yb - 6.0), (pW.x, yb - 1.5), (pW.x, yb + 4.0))
s_in = K.s_of_y(P_in, yb)          # (jx.Path.s_of_y gives the nearest vertex: the car stopped 1.5 m short of its bay)
park_W = [dict(x=pW.x, y=pW.y, yaw=yawW, v=0.0, ind=None)]
n = TL.n("SITUATION")
sv_in = K.kin(s_in - 13.0, 2.2, [(0, "cruise", 2.2), (2.0, "stop", s_in)], int(6.0 * FPS), a_brake=1.5)
sv_in += K.hold(s_in, n - len(sv_in))
# CORRECT: past the free gap on the left, reverse parallel parking into the free bay on the right (+1, 5)
pp = PK.parallel_paths(rowR, 5, approach=16.0)
full = PK.parallel_track(pp, 600, v_app=3.6, t_stop=0.5, v_rev=1.5, a=1.6)
e = max(i for i, d in enumerate(full) if abs(d["v"]) > 0.01)
nk = TL.n("CORRECT")
park_R = full[max(0, e + 8 - nk): e + 8]
parts = {"HOOK": park_W, "SITUATION": (P_in, sv_in, dict(ind=[("L", 2.6, 4.6)])), "RULE": park_W, "COST": park_W,
         "CORRECT": park_R}
K.bake(H, K.track(TL, parts, H["L"]))
print("CORRECT manoeuvre frames", e + 1, "shown", len(park_R))

# the oncoming hatchback (passes the hero at 6.2 s of SITUATION), more traffic
on = K.vehicle(fleet["hatch_red"], traf, "trf_oncoming")
P_on = K.line((-LANE, 160.0), (-LANE, -80.0))
s_meet = 160.0 - yb
K.bake(on, K.track(TL, {"SITUATION": (P_on, K.kin(s_meet - 7.0 * 6.2, 7.0, [(0, "cruise", 7.0)], n)),
                        "CORRECT": (P_on, K.kin(s_meet - 30.0, 7.5, [(0, "cruise", 7.5)], nk))}))

# ------------------------------------------------------------------ the attendant and the tickets
XF = -(HX + TN.KERB_W + 1.1)
sv_a = []
for k in TL.order:
    m = TL.n(k)
    if k == "SITUATION":
        sv_a += [(min(12.5, max(0.0, 1.3 * (i / FPS - 6.5))), 1.3 if 6.5 < i / FPS < 6.5 + 12.5 / 1.3 else 0.0)
                 for i in range(m)]
    elif k in ("HOOK", "RULE", "COST"):
        sv_a += [(12.5, 0.0)] * m
    else:
        sv_a += [(0.0, 0.0)] * m
K.walker(env, "attendant", 21, [(XF, yb - 12.0 + 0.3), (XF, yb + 0.8)], sv_a, role="attendant",
         gesture=[("write", 0.0, TL.a("SITUATION")), ("write", TL.a("RULE"), TL.a("CORRECT"))],
         look=[(0.0, TL.a("SITUATION"), (pW.x, yb, 1.0)), (TL.a("RULE"), TL.a("CORRECT"), (pW.x, yb, 1.0))])
ws, _ = K.windscreen_point(H, TL.a("HOOK", 0.5))
K.slip("slip_hook", env, ws, yawW, TL.a("HOOK", 1.3), t_off=TL.a("SITUATION"))
K.slip("slip_sit", env, ws, yawW, TL.a("SITUATION", 9.0), t_off=TL.a("CORRECT"))
for k, (x, y) in enumerate(((HX + 1.4, yb - 30.0), (-HX - 1.6, yb + 25.0))):
    K.walker(env, f"ped{k}", 3 + 5 * k, [(x, y), (x, y + (40.0 if k == 0 else -40.0))],
             [(min(40.0, 1.15 * i / FPS), 1.15) for i in range(N)], coat=((0.55, 0.3, 0.1), (0.2, 0.3, 0.2))[k])

# the one-way street (east arm, one-way eastbound): both rows face east; Zeichen 220-20 (arrow to the right, i.e. east
# for a reader looking north at it) on its post on the north footway, readable from the junction. The rule's arrows
# and the red box are ASS drawings in post_ep16.py, never objects in the street.
stE = TP.arm(J, "E")
rE1 = PK.bays(T, env, stE, +1, 16.0, 6, name="bays_e1")
rE2 = PK.bays(T, env, stE, -1, 16.0 + LEN - PK.BAY_L, 6, name="bays_e2")
import random  # noqa: E402
rnd = random.Random(5)
for row, ww in ((rE1, False), (rE2, True)):
    for i in range(6):
        if (row is rE1 and i == 2):
            continue
        PK.park(cars[rnd.choice(sorted(cars))], env, row, i, wrong_way=ww, name="parked_e")
xs = HX + 14.0
SG.assembly([("220-20", 1.0)], env, (xs, HY + TN.KERB_W + 0.6, TN.KERB_H), rz=0.0, bottom=2.0)

# ------------------------------------------------------------------ cameras
sh = K.Shots(N)                  # frame-exact cuts (ep10_za5kit.Shots)


def chase(car, back=6.4, up=1.6, side=-0.5, ahead=10.0, dz=0.6):
    def fn(t):
        p, y = K.at(car, t), K.heading(car, t)
        f, r = Vector((math.cos(y), math.sin(y), 0)), Vector((math.sin(y), -math.cos(y), 0))
        return p - f * back + r * side + Vector((0, 0, up)), p + f * ahead + Vector((0, 0, dz))
    return fn


t0 = TL.a("HOOK")
sh.add("H_drone", 24, t0, t0 + 1.3, lambda t: (Vector((6.0, yb - 16.0 + 1.5 * (t - t0), 13.0)), Vector((-1.5, yb, 0.0))))
sh.add("H_close", 32, t0 + 1.3, TL.a("SITUATION"), lambda t: (Vector((XF - 0.6, ws.y + 2.6, 1.9)), Vector(ws)))
t0 = TL.a("SITUATION")
sh.add("S_drone", 26, t0, t0 + 3.0, lambda t: (Vector((-22.0, yb - 52.0 + 2.0 * (t - t0), 40.0)), Vector((0.0, yb - 6.0, 0.0))))
sh.add("S_chase", 24, t0 + 3.0, t0 + 5.0, chase(H))
# rev 2: the chase camera followed the car into the bay and ended just above the black car parked behind it (a dark
# glossy blob at 8 s). Now a fixed view from above the road behind the hero: the left row, the hero settling into the
# gap nose against the traffic, the right row facing the other way, the oncoming hatchback coming down the lane.
sh.add("S_lane", 26, t0 + 5.0, t0 + 7.0, lambda t: (Vector((-0.3, yb - 11.0 + 0.3 * (t - t0 - 5.0), 4.2)),
                                                   Vector((pW.x + 0.4, yb + 0.5, 0.7))))
sh.add("S_top", 30, t0 + 7.0, TL.a("RULE"), lambda t: (Vector((-1.0, yb - 5.0, 24.0)), Vector((-1.0, yb - 5.0, 0.0))),
       up_fn=lambda t: UP_N)
t0 = TL.a("RULE")
# a5gfx.top() numbers in post_ep16.py: R_top (0, yb, 22 m, lens 26), R_east (xs + 10, 0, 34 m, lens 26)
sh.add("R_top", 26, t0, t0 + 5.1, lambda t: (Vector((0.0, yb, 22.0)), Vector((0.0, yb, 0.0))), up_fn=lambda t: UP_N)
sh.add("R_sign", 24, t0 + 5.1, t0 + 6.1, lambda t: (Vector((xs - 3.0 - 0.3 * (t - t0 - 5.1), -1.3, 2.3)),
                                                   Vector((xs + 1.2, HY + 0.8, 2.2))))
sh.add("R_east", 26, t0 + 6.1, TL.a("COST"), lambda t: (Vector((xs + 10.0, 0.0, 34.0)), Vector((xs + 10.0, 0.0, 0.0))),
       up_fn=lambda t: UP_N)
t0 = TL.a("COST")
sh.add("C_close", 34, t0, t0 + 2.2, lambda t: (Vector((XF - 0.4, ws.y + 2.2 - 0.1 * (t - t0), 1.75)), Vector(ws)))
sh.add("C_top", 30, t0 + 2.2, TL.a("CORRECT"), lambda t: (Vector((pW.x + 2.5, yb, 22.0)), Vector((pW.x + 2.5, yb, 0.0))),
       up_fn=lambda t: UP_N)
t0 = TL.a("CORRECT")
sh.add("K_chase", 24, t0, t0 + 2.5, chase(H, 6.8, 1.7, -0.3))
yR = PK.bay_pose(rowR, 5)[0].y
sh.add("K_drone", 26, t0 + 2.5, TL.a("END"), lambda t: (Vector((-9.0, yR - 14.0, 15.0)), Vector((HX - 1.0, yR, 0.0))))
K.end_card(T, env, sh, TL.a("END"), TL.T, signs_=(("220-20", 1.0),))
K.light(az=230.0, elev=24.0, energy=5.0, exposure=0.3)
K.finish(sh, TL)
