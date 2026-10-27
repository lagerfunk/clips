"""Drive Like a Local: Florida #5 (release Fri 20 Nov 2026): unpaid toll (Florida Statutes §316.1001). 9:16, 30 fps,
32.8 s canonical (English) timeline: HOOK 0-3, SITUATION 3-11, RULE 11-18.6, COST 18.6-23.8, CORRECT 23.8-29.8,
END 29.8-32.8. Three-lane freeway with an open-road toll gantry (camera boxes, readers, no booth, no barrier, no sign,
no operator name: no Commons file shows a gantry sign without a toll programme's name). RULE mid shot: the parked
sedan's rear in its driveway, the blank plate with a plain registration decal (no text); COST: the teal sedan at home in a driveway (a separate set south of
the freeway); CORRECT: the sedan now carries a plain windscreen tag. The flat icons (citation sheet, lock, letter,
beep, invoice and tick) are ASS drawings in post_fl05.py (fl01_uspost.icons_fl05), no clip art, no logos.
Run: python fl05_toll_unpaid.py OUT --frames 1-984 --res 540 --samples 8 --assets ASSETS [--stills ..] [--check X]"""
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
E = S.Ep([("HOOK", 3.0), ("SITUATION", 8.0), ("RULE", 7.6), ("COST", 5.2), ("CORRECT", 6.0), ("END", 3.0)])
fw = K.Freeway(env, -1200.0, 1200.0)
S.freeway_dress(env, lib, fw, seed=5)
YG = 0.0
# strobes: in the hook, and two 0.17 s pulses as the sedan passes under the gantry at SITUATION 4.8 s (the S_cam
# shot under "The toll camera flashes.", 4.0 to 5.9 s); each pulse spans several frames so step-2 previews show it
flashes = [(E.t("HOOK", 2.4), E.t("HOOK", 2.57)), (E.t("SITUATION", 4.78), E.t("SITUATION", 4.95)),
           (E.t("SITUATION", 5.1), E.t("SITUATION", 5.27))]
K.toll_gantry(env, YG, 0.35, fw.x_out + K.SHOULDER + 0.6, [fw.lane_x(k) for k in range(3)], flash=flashes)
K.toll_gantry(env, YG + 3.0, -(fw.x_out + K.SHOULDER + 0.6), -0.35, [fw.lane_x(k, nb=False) for k in range(3)],
              name="toll_sb")

mph = 0.44704
teal = K.hero(K.us_car("saloon", (0.0, 0.32, 0.34), "sedan", lib), "saloon", traffic)
hatch = K.hero(K.us_car("hatch", (0.62, 0.64, 0.66), "hatch_x", lib), "hatch", traffic)
van = K.hero(K.us_car("van", (0.92, 0.92, 0.9), "van_x", lib), "van", traffic)
tag_m = K.mat("us_tag", (0.85, 0.85, 0.85), 0.5)
tag = K.box("tag_windscreen", lib, (0.0, 0.0, 0.0), (0.1, 0.01, 0.04), tag_m)
tag.parent = next(ob for ob in hatch["coll"].objects if ob.type == "EMPTY" and ob.parent is None)
tag.location = (0.0, 0.35, 1.32)
# the teal sedan gets its tag only in CORRECT (it learnt), and a plain registration decal on its blank plate
tag2 = K.box("tag_windscreen_teal", env, (0.0, 0.35, 1.32), (0.1, 0.01, 0.04), tag_m, parent=teal["obj"])
bpy.context.view_layer.update()
plate = next(ob for ob in teal["coll"].objects if ob.name.startswith("us_plate_blank"))
pw = plate.matrix_world.translation
K.box("reg_decal", env, (pw.x + 0.1, pw.y - 0.009, pw.z + 0.045), (0.07, 0.004, 0.045),
      K.mat("reg_decal", (0.9, 0.42, 0.05), 0.35), parent=teal["obj"])

PM, PR, PL = (K.straight(fw.lane_x(k)) for k in (1, 0, 2))
v = 65 * mph
s_g = 2000.0 + YG
E.take(teal, "HOOK", PM, s_g - v * 2.4, v, [(0, "cruise", v)])
E.take(van, "HOOK", PL, s_g - v * 2.4 + 30.0, 60 * mph, [(0, "cruise", 60 * mph)])
E.take(hatch, "SITUATION", PR, s_g - v * 0.8, v, [(0, "cruise", v)])
E.take(teal, "SITUATION", PM, s_g - v * 4.8, v, [(0, "cruise", v)])          # under the gantry at 4.8 s
E.take(van, "SITUATION", PL, s_g - 200.0, 60 * mph, [(0, "cruise", 60 * mph)])
E.take(teal, "RULE", PM, s_g - 40.0, v, [(0, "cruise", v)], t1=4.0)    # R_top; R_plate (4.0 s on) is at home

# COST set: a ranch house with the sedan in its driveway, 2.3 km south of the freeway's end (open lawn there)
YD = -3500.0
houses = K.house_lib(lib)
hc = houses[1]
K.rects("drive_set_street", [(-60.0, 60.0, YD - 9.0, YD - 0.6)], 0.0, K.mats()["asphalt"], env, uv=True)
K.rects("drive_set_walk", [(-60.0, 60.0, YD - 0.6, YD + 0.0)], 0.01, K.mats()["concrete"], env)
for k, dx in enumerate((-24.0, 0.0, 24.0)):
    K.instance(houses[(1 + 3 * k) % len(houses)] if dx else hc, env, (dx, YD, 0.0), 0.0, name="drive_set_house")
trees = K.tree_groups(lib)
import flora  # noqa: E402
flora.scatter("drive_set_oaks", [(-30.0, YD + 40.0, 0.0), (-8.0, YD + 44.0, 0.0), (14.0, YD + 41.0, 0.0),
                                 (33.0, YD + 46.0, 0.0), (-40.0, YD + 70.0, 0.0), (5.0, YD + 75.0, 0.0)],
              trees["decid"], env, 1.3, 1.7, seed=8)
flora.scatter("drive_set_palms", [(hc["gx"] * -1.0 + 3.0, YD + 3.0, 0.0), (21.0, YD + 4.0, 0.0)], trees["palm"], env,
              0.9, 1.05, seed=9)
xd = hc["gx"]
PD = jx.Path([(xd, YD - 100.0), (xd, YD + 100.0)])
E.take(teal, "COST", PD, 100.0 + hc["sb"] / 2 + 0.2, 0.0, [(0, "hold", None)])
# "Unpaid toll can block registration": the sedan already parked in its driveway (standing still, no motion blur)
E.take(teal, "RULE", PD, 100.0 + hc["sb"] / 2 + 0.2, 0.0, [(0, "hold", None)], t0=4.0)

E.take(teal, "CORRECT", PM, s_g - v * 1.4, v, [(0, "cruise", v)])
E.take(hatch, "CORRECT", PR, s_g - 90.0, 62 * mph, [(0, "cruise", 62 * mph)])
E.bake()
for f, h in ((1, True), (int(E.t("CORRECT", 0.0) * 30), False), (int(E.t("END", 0.0) * 30), True)):
    tag2.hide_render = h
    tag2.keyframe_insert("hide_render", frame=max(1, f))

UP = Vector((0, 1, 0))
xg = fw.x_out + K.SHOULDER
E.chase("H_chase", teal, "HOOK", 0.0, 1.8, back=9.0, up=2.6, ahead=80.0)
E.shot("H_side", 30, "HOOK", 1.8, 3.0, lambda t: (Vector((xg + 9.0, YG - 10.0, 4.2)), Vector((fw.lane_x(1), YG, 4.0))))
E.shot("S_drone", 24, "SITUATION", 0.0, 3.0, lambda t: (Vector((xg + 18.0, YG - 50.0 + 3 * t, 22.0)),
                                                       Vector((6.0, YG, 3.0))))
E.chase("S_chase", teal, "SITUATION", 3.0, 4.0, back=10.0, up=3.0, ahead=60.0)
# "The toll camera flashes.": from the shoulder below the gantry, the per-lane camera boxes and their strobes in the
# upper half of the frame, the sedan driving under them and the strobes firing at 4.8 and 5.1 s
E.shot("S_cam", 32, "SITUATION", 4.0, 6.0, lambda t: (Vector((fw.x_out + 1.2, YG - 12.0, 2.2)),
                                                     Vector((fw.lane_x(1) + 1.0, YG - 0.8, K.GANTRY_CLEAR - 0.3))))
E.shot("S_top", 30, "SITUATION", 6.0, 8.0, lambda t: (Vector((7.0, YG, 48.0)), Vector((7.0, YG + 0.1, 0.0))), up=UP)
E.shot("R_top", 30, "RULE", 0.0, 4.0, lambda t: (Vector((14.0, YG + 2 * t, 70.0)), Vector((14.0, YG + 2 * t + 0.1, 0))),
       up=UP)
L2 = teal["L"] / 2
# steady mid shot of the parked sedan's rear from the driveway mouth (static camera, car standing): the whole rear
# about 4/5 of the frame width, the blank plate with its decal near the middle of the frame, the roof under the
# caption and the bumper above the lock icon (caption layer, post_fl05.py)
PR0 = lambda: E.pos(teal, E.t("RULE", 5.0))  # noqa: E731
E.shot("R_plate", 42, "RULE", 4.0, 7.6, lambda t: (PR0() + Vector((0.55, -L2 - 4.6, 1.1)),
                                                  PR0() + Vector((0.05, -L2, 0.58))))
E.shot("C_drive", 30, "COST", 0.0, 1.6, lambda t: (Vector((xd - 7.0 + 0.6 * t, YD - 12.0, 2.4)),
                                                  Vector((xd, YD + hc["sb"] / 2, 1.0))))
# the letter: a mid shot of the house and the sedan in its driveway from across the street; the flat letter icon
# (post) is the only "letter" (no hand, no rear-corner close-up)
E.shot("C_mid", 32, "COST", 1.6, 5.2, lambda t: (Vector((xd + 6.5 - 0.25 * t, YD - 13.0 + 0.3 * t, 2.6)),
                                                Vector((xd - 0.5, YD + hc["sb"] / 2 + 1.5, 1.6))))
E.shot("K_drone", 24, "CORRECT", 0.0, 3.6, lambda t: (Vector((xg + 18.0, YG - 46.0 + 3 * t, 20.0)),
                                                     Vector((6.0, YG, 3.0))))
E.chase("K_chase", teal, "CORRECT", 3.6, 6.0, back=9.0, up=2.6, ahead=60.0)
# end card: no toll sign exists on Commons without a programme name, so the card shows the gantry itself, low in
# the frame below the end lines, from the shoulder 40 m upstream
E.card(cam=(fw.x_out + 1.0, YG - 40.0, 1.6), tgt=(fw.lane_x(1), YG, 10.0))
E.run(o, o["assets"])
