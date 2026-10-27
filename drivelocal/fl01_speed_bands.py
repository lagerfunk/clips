"""Drive Like a Local: Florida #1 (release Mon 16 Nov 2026): speeding is priced in bands (Florida Statutes §318.18).
9:16, 30 fps, 34.4 s canonical (English) timeline: HOOK 0-3, SITUATION 3-10.5, RULE 10.5-17, COST 17-26.4,
CORRECT 26.4-31.4, END 31.4-34.4. Four-lane arterial, speed limit sign R2-1-45 (the Commons file of the 45 limit), a patrol
sedan on the verge with an officer and a handheld laser. Band colours in the RULE top shot carry no numbers; the
mph band meter is drawn in the captions (post_fl01.py), not here.
Run: python fl01_speed_bands.py OUT --frames 1-1032 --res 540 --samples 8 --assets ASSETS [--stills ..] [--check X]"""
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
E = S.Ep([("HOOK", 3.0), ("SITUATION", 7.5), ("RULE", 6.5), ("COST", 9.4), ("CORRECT", 5.0), ("END", 3.0)])
art = K.Arterial(env, -900.0, 900.0)
A = art.lip
S.dress(env, lib, art, -900.0, 900.0, seed=1)
sg45 = K.sign(env, "R2-1-45", (A + 0.7, 0.0, K.KERB_H), 0.0, width=0.62, bottom=2.1)
K.sign(env, "R2-1-45", (-(A + 0.7), 120.0, K.KERB_H), math.pi, width=0.62, bottom=2.1, name="sign_R2-1-45_sb")

mph = 0.44704
LIM = 45 * mph
teal = K.hero(K.us_car("saloon", (0.0, 0.32, 0.34), "sedan", lib), "saloon", traffic)
hatch = K.hero(K.us_car("hatch", (0.72, 0.7, 0.62), "hatch_x", lib), "hatch", traffic)
cop = K.hero(K.us_car("saloon", None, "patrol", lib, police=True), "saloon", traffic)
P0, P1 = K.straight(art.lane_x(0)), K.straight(art.lane_x(1))
y_cop = 190.0
PC = jx.Path([(A + 12.5, y_cop), (A - 30.0, y_cop)])          # parked nose to the road in the lot
s0 = 2000.0 - 40.0
E.take(teal, "HOOK", P0, s0, LIM, [(0, "cruise", LIM), (0.5, "cruise", 62 * mph)], ind=[])
E.take(hatch, "HOOK", P1, s0 + 6.0, LIM, [(0, "cruise", LIM)])
E.take(teal, "SITUATION", P0, 2000.0 - LIM * 1.5, LIM, [(0, "cruise", LIM), (3.2, "cruise", 72 * mph)])
E.take(hatch, "SITUATION", P1, 2000.0 - LIM * 1.5 - 14.0, LIM, [(0, "cruise", LIM)])
E.take(cop, "SITUATION", PC, 0.0, 0.0, [(0, "hold", None)])
E.take(teal, "RULE", P0, 2000.0 - 40.0, 14.0, [(0, "cruise", 14.0)])
E.take(teal, "COST", P0, 2000.0 + 150.0, 60 * mph, [(0, "cruise", 60 * mph), (3.0, "cruise", 30 * mph),
                                                    (4.5, "stop", 2000 + 150 + 125)])
PCL = K.lane_change(art.lane_x(1), art.lane_x(0), 2000.0 + 140.0, 30.0)
E.take(cop, "COST", PCL, 2000.0 + 105.0, 66 * mph, [(0, "cruise", 66 * mph), (3.0, "cruise", 30 * mph),
                                                    (4.5, "stop", 2000 + 150 + 125 - 8.5)])
E.take(teal, "CORRECT", P0, 2000.0 + y_cop - LIM * 2.5, LIM, [(0, "cruise", LIM)])
E.take(hatch, "CORRECT", P1, 2000.0 + y_cop - LIM * 2.5 - 20.0, LIM, [(0, "cruise", LIM)])
E.take(cop, "CORRECT", PC, 0.0, 0.0, [(0, "hold", None)])
E.bake(beacon={"patrol": [(E.t("COST", 1.0), E.t("COST", 9.4))]})

# officer (kit/figures.py person: navy uniform, cap, duty belt, no lettering, no crest) on the grass verge between
# the kerb and the sidewalk (palms at lip + 1.25, lights at lip + 0.75, sidewalk from lip + 2.35), aiming a handheld
# speed laser (figures' generic lidar gun) at the northbound traffic; the beam flashes at SITUATION 6.0 s
import figures as F  # noqa: E402
P_OFF = (A + 1.95, y_cop - 3.0)
off = F.person(env, "officer", height=1.82, sex="m", skin=1, hair="short", jacket=F.NAVY, trousers=F.POLICE_DARK,
               shoes=F.srgb(16, 16, 18), sole=F.srgb(20, 20, 20), headwear="cap", headwear_color=F.POLICE_DARK,
               hem=0.585, belt=True, seed=12)
F._laser(off, env)
F.stand(off, P_OFF, (art.lane_x(0), y_cop - 70.0), E.N, ground=lambda x, y: K.KERB_H, gesture=[("laser", 0.0, E.T)])
t_fl = E.t("SITUATION", 6.0)
tgt = E.pos(teal, t_fl) + Vector((0, 0, 0.8))
src = Vector((P_OFF[0], P_OFF[1], K.KERB_H + 1.55))
src = src + (tgt - src).normalized() * 0.45
d = tgt - src
beam = K.cyl("laser_beam", env, tuple((src + tgt) / 2), 0.012, d.length, jx.flat_mat("laser_red", (1, 0.05, 0.05),
                                                                                      emit=8.0), 6)
beam.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
for f, h in ((1, True), (int(t_fl * 30), False), (int((t_fl + 0.35) * 30), True)):
    beam.hide_render = h
    beam.keyframe_insert("hide_render", frame=f)

# RULE top shot: four flat colour bands laid along the northbound lanes, the top one glows red
cols = [(0.1, 0.8, 0.25), (1.0, 0.8, 0.0), (1.0, 0.45, 0.0), (1.0, 0.06, 0.04)]
bands = []
for k, col in enumerate(cols):
    b = K.rects(f"band_{k}", [(0.4, art.edge - 0.1, 30.0 + k * 26.0, 52.0 + k * 26.0)], 0.03,
                jx.flat_mat(f"band_m{k}", col, emit=2.0 if k < 3 else 3.2, alpha=0.88), env)
    bands.append(b)
    for f, h in ((1, True), (int(E.t("RULE", 0.2 + 0.4 * k) * 30), False), (int(E.t("RULE", 6.5) * 30), True)):
        b.hide_render = h
        b.keyframe_insert("hide_render", frame=f)

UP = Vector((0, 1, 0))
E.chase("H_chase", teal, "HOOK", 0.0, 1.6, back=8.0, up=2.0)
E.shot("H_mid", 30, "HOOK", 1.6, 3.0, lambda t: (E.pos(teal, E.t("HOOK", t)) + Vector((-6.5, -12.5, 2.4)),
                                                E.pos(teal, E.t("HOOK", t)) + Vector((0.8, 4.0, 0.9))))
# "The road sign shows the limit.": the 45 sign large in the lower half of the frame, the sedan driving past it
E.shot("S_sign", 30, "SITUATION", 0.0, 3.0, lambda t: (Vector((A + 2.6, -5.2 - 0.25 * t, 3.25)),
                                                      Vector((A - 2.0, 9.0, 3.3))))
E.chase("S_chase", teal, "SITUATION", 3.0, 5.0, back=9.0, up=2.4)
# "Police measure the speed.": over the officer's left shoulder from the back grass strip (lip + 4.4, short of the
# lot at lip + 7.2, so no parked car can stand between camera and officer); the officer right of centre at about
# 5.5 m, the laser aimed down the northbound lanes, the approaching traffic left of centre; slow push-in
E.shot("S_officer", 28, "SITUATION", 5.0, 7.5, lambda t: (Vector((A + 4.45 - 0.06 * t, y_cop + 1.85 - 0.2 * t,
                                                                  K.KERB_H + 1.9)),
                                                         Vector((A - 3.2, y_cop - 18.2, K.KERB_H + 1.15))))
E.shot("R_top", 30, "RULE", 0.0, 3.5, lambda t: (Vector((3.0, 74.0, 95.0)), Vector((3.0, 74.1, 0.0))), up=UP)
E.shot("R_close", 30, "RULE", 3.5, 6.5, lambda t: (Vector((14.0, 92.0, 7.0)), Vector((3.0, 120.0, 0.0))))
E.chase("C_chase", cop, "COST", 0.0, 4.0, back=9.0, up=2.4)
# pulled over: a mid shot from behind the patrol car (no tight rear-corner close-up until dl/vehicles2 lands)
E.shot("C_mid", 30, "COST", 4.0, 9.4, lambda t: (E.pos(teal, E.t("COST", t)) + Vector((-4.2, -17.0, 3.0)),
                                                E.pos(teal, E.t("COST", t)) + Vector((0.6, 4.0, 0.8))))
E.chase("K_chase", teal, "CORRECT", 0.0, 5.0, back=9.0, up=2.4, side=-1.2)
E.card(sg45)
E.run(o, o["assets"], haze_skip=tuple(f"band_m{k}" for k in range(4)) + ("laser_red",))
