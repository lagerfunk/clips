"""Drive Like a Local: Florida #2 (release Tue 17 Nov 2026): red light (Florida Statutes §316.075). 9:16, 30 fps,
33.7 s on the canonical (English) timeline: HOOK 0-3, SITUATION 3-11, RULE 11-19, COST 19-24.2, CORRECT 24.2-30.7,
END 30.7-33.7. Four-lane arterial, signalised crossing with span-wire heads, ladder crosswalks, stop bars and a
northbound right-turn lane. The visuals never show a turn on red (that rule is one source only): the sedan in the
turn lane waits for green.
Run: python fl02_red_light.py OUT --frames 1-1011 --res 540 --samples 8 --assets ASSETS [--stills 40,200] [--check X]"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "fl01"), os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit")]

import bpy  # noqa: E402,F401  (mathutils only exists once bpy is loaded)
from mathutils import Vector  # noqa: E402

import fl01_uskit as K  # noqa: E402
import fl01_usscene as S  # noqa: E402
import jx  # noqa: E402

o = S.cli()
lib, env, traffic = K.new_scene(o["assets"])
E = S.Ep([("HOOK", 3.0), ("SITUATION", 8.0), ("RULE", 8.0), ("COST", 5.2), ("CORRECT", 6.5), ("END", 3.0)])
art = K.Arterial(env, -700.0, 700.0, cross=0.0, rtl=True)
A, B = art.lip, art.B
S.dress(env, lib, art, -700.0, 700.0, seed=2, skip=[(-90.0, 30.0)])

# span wire diagonally across the crossing, heads over each approach
at = K.span_wire(env, (-(A + 3.0), -(B + 3.0)), (A + K.LANE + 3.0, B + 3.0))
ns, ew = K.Signal("ns"), K.Signal("ew")
for k in range(3):
    x = (k + 0.5) * K.LANE
    K.signal_head(env, ns, at(x=x), 0.0, name=f"sig_nb{k}")
for k in range(2):
    K.signal_head(env, ns, at(x=-(k + 0.5) * K.LANE), math.pi, name=f"sig_sb{k}")
K.signal_head(env, ew, at(x=1.0), -math.pi / 2, name="sig_eb")
K.signal_head(env, ew, at(x=-1.0), math.pi / 2, name="sig_wb")
sg = K.sign(env, "R10-6", (A + K.LANE + 1.2, art.stop_nb - 1.0, 0.15), 0.0, width=0.62, bottom=2.1)


def phase(t, n_, e_):
    ns.key(t, n_)
    ew.key(t, e_)


for t, n_, e_ in ((0.0, "Y", "R"), (0.8, "R", "R"), (2.6, "R", "G"),          # hook
                  (3.0, "R", "R"), (6.0, "R", "G"), (10.9, "R", "G"),          # situation
                  (11.0, "R", "G"), (18.2, "R", "G"),                          # rule: red throughout
                  (19.0, "G", "R"),                                            # cost (next block)
                  (24.2, "R", "G"), (27.2, "G", "R"), (27.4, "R", "G"), (30.0, "G", "R")):   # correct, two takes
    phase(t, n_, e_)
ns.done()
ew.done()

# cars
teal = K.hero(K.us_car("saloon", (0.0, 0.32, 0.34), "sedan", lib), "saloon", traffic)
pick = K.hero(K.us_car("suv", (0.55, 0.56, 0.58), "suv_x", lib), "suv", traffic)
cop = K.hero(K.us_car("saloon", None, "patrol", lib, police=True), "saloon", traffic)
L = teal["L"]
P1, P2, P3 = (K.straight(art.lane_x(k)) for k in range(3))
s_line = art.stop_nb + 2000.0 - 0.6 - L / 2          # centre arc length with the bumper at the stop bar
PW = jx.Path([(300.0, K.LANE / 2), (-300.0, K.LANE / 2)])          # westbound cross street
s_w = 300.0 - (art.stop_wb + 0.6 + pick["L"] / 2)
mph = 0.44704
E.take(teal, "HOOK", P1, s_line - 40 * mph * 2.0, 40 * mph, [(0, "cruise", 40 * mph)])
E.take(pick, "HOOK", PW, s_w, 0.0, [(0, "hold", None)])
E.take(teal, "SITUATION", P1, s_line - 45 * mph * 3.6, 45 * mph, [(0, "cruise", 45 * mph)])
E.take(pick, "SITUATION", PW, s_w, 0.0, [(0, "hold", None), (3.0, "cruise", 6.0), (4.2, "stop", s_w + 5.2)])
E.take(teal, "RULE", P3, s_line - 60.0, 12.0, [(0, "cruise", 12.0), (2.0, "stop", s_line)])
E.take(pick, "RULE", PW, s_w - 120.0, 13.0, [(0, "cruise", 13.0)])
PR = jx.Path([(art.lane_x(2), -2000.0), (art.lane_x(2), -B - 3.0)] +
             [(A + 9.0 - (A + 9.0 - art.lane_x(2)) * math.cos(u * math.pi / 2 / 10),
               -B - 3.0 + (B + 3.0 - K.LANE / 2) * math.sin(u * math.pi / 2 / 10)) for u in range(1, 11)] +
             [(400.0, -K.LANE / 2)])
E.take(teal, "COST", P2, 2300.0, 40 * mph, [(0, "cruise", 40 * mph), (2.6, "cruise", 6.0), (4.0, "stop", 2300 + 70)])
E.take(cop, "COST", P2, 2300.0 - 45.0, 44 * mph, [(0, "cruise", 46 * mph), (2.6, "cruise", 7.0),
                                                   (4.0, "stop", 2300 + 70 - 9.0)])
E.take(teal, "CORRECT", P1, s_line - 35.0, 35 * mph, [(0, "stop", s_line), (3.0, "cruise", 9.0)], t1=3.2)
E.take(pick, "CORRECT", jx.Path([(-300.0, -K.LANE / 2), (300.0, -K.LANE / 2)]), 300.0 - 60.0, 12.0,
       [(0, "cruise", 12.0)], t1=3.2)
E.take(teal, "CORRECT", PR, s_line - 25.0, 8.0, [(0, "stop", s_line), (2.8, "cruise", 5.0)], t0=3.2,
       ind=[("R", 3.8, 6.5)])
E.bake(beacon={"patrol": [(E.t("COST", 1.0), E.t("COST", 5.2))]})

walker = K.person(env, (A + 2.6, -B - 1.6, K.KERB_H), math.pi / 2, shirt=(0.75, 0.3, 0.12), name="walker")
for t, xy in ((0.0, (A + 2.6, -B - 1.6)), (E.t("SITUATION", 4.0), (A + 2.6, -B - 1.6)),
              (E.t("SITUATION", 4.5), (A + 3.6, -B - 2.4)), (E.t("CORRECT", 3.3), (A + 1.5, -B - 1.2)),
              (E.t("CORRECT", 3.9), (A + 1.5, -B - 1.2)), (E.t("CORRECT", 5.8), (A + 1.5, B + 1.2))):
    walker.location = (xy[0], xy[1], K.KERB_H)
    walker.keyframe_insert("location", frame=int(t * 30) + 1)
walker.rotation_euler = (0, 0, math.pi)
walker.keyframe_insert("rotation_euler", frame=int(E.t("CORRECT", 3.2) * 30))

# the red cross on the path and the red bar on the stop line (top shot, SITUATION 5.4 to 8.0)
red = jx.flat_mat("fl_red_mark", (1.0, 0.08, 0.05), emit=2.0)
ys = art.stop_nb
mk = [K.rects("mark_bar", [(0.3, art.edge, ys - 0.9, ys + 0.3)], 0.03, red, env)]
for sgn in (1, -1):
    vs = [(art.lane_x(0) + sgn * d - 0.5, ys + 8 + d, 0.03) for d in (-3.5, 3.5)]
    mk.append(K.poly("mark_x", [(vs[0][0], vs[0][1]), (vs[0][0] + 1.0, vs[0][1]), (vs[1][0] + 1.0, vs[1][1]),
                                (vs[1][0], vs[1][1])], 0.03, red, env, uv=False))
for m_ in mk:
    for f, h in ((1, True), (int(E.t("SITUATION", 5.6) * 30), False), (int(E.t("SITUATION", 8.0) * 30), True)):
        m_.hide_render = h
        m_.keyframe_insert("hide_render", frame=f)

# cameras
UP = Vector((0, 1, 0))
E.chase("H_chase", teal, "HOOK", 0.0, 1.8, back=8.0, up=2.0)
E.shot("H_side", 30, "HOOK", 1.8, 3.0, lambda t: (Vector((A + 26.0, art.stop_nb - 4.0, 6.0)),
                                                  Vector((2.0, art.stop_nb + 2.0, 2.5))))
E.shot("S_drone", 24, "SITUATION", 0.0, 2.7, lambda t: (Vector((30.0, -95.0 + 4 * t, 60.0)), Vector((0, -10.0, 0))))
E.chase("S_chase", teal, "SITUATION", 2.7, 5.4, back=10.0, up=2.6)
E.shot("S_top", 30, "SITUATION", 5.4, 8.0, lambda t: (Vector((2.0, -2.0, 52.0)), Vector((2.0, -1.9, 0.0))), up=UP)
E.shot("R_drone", 26, "RULE", 0.0, 3.5, lambda t: (Vector((26.0 - 3 * t, -40.0, 16.0)),
                                                  Vector((3.0, art.stop_nb, 3.0))))
E.chase("R_chase", teal, "RULE", 3.5, 8.0, back=8.5, up=2.2, side=-1.0)
E.chase("C_chase", cop, "COST", 0.0, 1.6, back=9.0, up=2.4)
# pulled over: a mid shot from behind the patrol car (no tight rear-corner close-up until dl/vehicles2 lands)
E.shot("C_mid", 30, "COST", 1.6, 5.2, lambda t: (E.pos(teal, E.t("COST", t)) + Vector((-4.0, -17.0, 3.0)),
                                                E.pos(teal, E.t("COST", t)) + Vector((0.6, 4.0, 0.8))))
E.shot("K_drone", 26, "CORRECT", 0.0, 3.2, lambda t: (Vector((24.0, -60.0, 22.0)), Vector((2.0, -8.0, 1.0))))
E.chase("K_chase", teal, "CORRECT", 3.2, 6.5, back=10.5, up=2.8, side=-1.0)
E.card(sg)
E.run(o, o["assets"], haze_skip=("fl_red_mark",))
