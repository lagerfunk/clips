"""Drive Like a Local: Florida #3 (release Wed 18 Nov 2026): Move Over (Florida Statutes §316.126). 9:16, 30 fps,
33.7 s canonical (English) timeline: HOOK 0-3, SITUATION 3-11, RULE 11-19, COST 19-24.4, CORRECT 24.4-30.7,
END 30.7-33.7. Three-lane freeway (the fl05 cross-section, no gantry): a patrol sedan stopped on the paved shoulder
with its light bar flashing behind a hatchback with its hazards on, an officer at the hatchback's passenger side.
The FDOT Move Over sign (Commons file, public domain) stands 300 m before the stop, and on the end card. Lane glows
and the down arrow are flat shapes without text; the speed dial is drawn in the captions (post_fl03.py).
Run: python fl03_move_over.py OUT --frames 1-1011 --res 540 --samples 8 --assets ASSETS [--stills ..] [--check X]"""
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
E = S.Ep([("HOOK", 3.0), ("SITUATION", 8.0), ("RULE", 8.0), ("COST", 5.4), ("CORRECT", 6.3), ("END", 3.0)])
fw = K.Freeway(env, -1200.0, 1200.0)
S.freeway_dress(env, lib, fw, seed=3)
x_sh = fw.x_out + K.SHOULDER / 2 + 0.1                 # centre of the paved shoulder
sg = K.sign(env, "FL-MOVEOVER", (fw.x_out + K.SHOULDER + 1.2, -300.0, 0.0), 0.0, width=1.52, bottom=2.1)

mph = 0.44704
v70, v50 = 70 * mph, 50 * mph
cop_c = K.us_car("saloon", None, "patrol", lib, police=True)
cop = K.hero(cop_c, "saloon", traffic, name="patrol")
cop2 = K.hero(cop_c, "saloon", traffic, name="patrol2")
teal = K.hero(K.us_car("saloon", (0.0, 0.32, 0.34), "sedan", lib), "saloon", traffic)
hatch = K.hero(K.us_car("hatch", (0.62, 0.64, 0.66), "hatch_x", lib), "hatch", traffic)
pick = K.hero(K.us_car("suv", (0.45, 0.06, 0.05), "suv_x", lib), "suv", traffic)
van = K.hero(K.us_car("van", (0.92, 0.92, 0.9), "van_x", lib), "van", traffic)
R0, R1 = fw.lane_x(0), fw.lane_x(1)
PR, PM, PL, PSH = K.straight(R0), K.straight(R1), K.straight(fw.lane_x(2)), K.straight(x_sh)
Y_COP, Y_HATCH = 0.0, 9.5
s_y = 2000.0                                             # straight paths start at y = -2000


def detour(y_out, y_back, ln=40.0):
    """Right lane, over to the middle lane from y_out (ln metres, cosine ease), back to the right lane from y_back."""
    pts = [(R0, -2000.0)]
    for y_a, xa, xb in ((y_out, R0, R1), (y_back, R1, R0)):
        for k in range(17):
            u = k / 16
            pts.append((xa + (xb - xa) * (1 - math.cos(math.pi * u)) / 2, y_a + ln * u))
    pts.append((R0, 2000.0))
    return jx.Path(pts)


segs = ("HOOK", "SITUATION", "RULE", "COST", "CORRECT")
for seg in segs:                                         # the stop on the shoulder is there in every live segment
    E.take(cop, seg, PSH, s_y + Y_COP, 0.0, [(0, "hold", None)])
    E.take(hatch, seg, PSH, s_y + Y_HATCH, 0.0, [(0, "hold", None)], ind=[("H", 0.0, 9.0)])
E.take(teal, "HOOK", PR, s_y + Y_COP - v70 * 2.4, v70, [(0, "cruise", v70)])
E.take(van, "HOOK", PL, s_y + Y_COP - v70 * 2.4 + 25.0, 64 * mph, [(0, "cruise", 64 * mph)])
E.take(teal, "SITUATION", PR, s_y + Y_COP - v70 * 5.0, v70, [(0, "cruise", v70)])       # passes the stop at 5.0 s
E.take(pick, "SITUATION", PM, s_y + Y_COP - v70 * 5.0 - 160.0, 65 * mph, [(0, "cruise", 65 * mph)])
# RULE: the middle lane is taken (pickup alongside), so the sedan slows to 20 mph under the limit as it passes
E.take(teal, "RULE", PR, s_y + Y_COP - 150.0, v70, [(0, "cruise", v70), (3.2, "cruise", v50)])
E.take(pick, "RULE", PM, s_y + Y_COP - 150.0 + 4.0, v70, [(0, "cruise", v70), (3.2, "cruise", v50)])
E.take(teal, "COST", PR, s_y + Y_COP - v70 * 0.9, v70, [(0, "cruise", v70), (1.8, "cruise", 45 * mph)])
E.take(cop2, "COST", PR, s_y + Y_COP - v70 * 0.9 - 34.0, 82 * mph, [(0, "cruise", 82 * mph), (1.8, "cruise", 45 * mph)])
s_c = s_y + Y_COP - v70 * 3.2                            # passes the stop at CORRECT 3.2 s
PD = detour(Y_COP - v70 * 1.6, Y_COP + v70 * 1.6 + 25.0)
E.take(teal, "CORRECT", PD, s_c, v70, [(0, "cruise", v70)], ind=[("L", 1.0, 2.2), ("R", 4.4, 5.6)])
E.take(van, "CORRECT", PL, s_c - 40.0, 66 * mph, [(0, "cruise", 66 * mph)])
E.bake(beacon={"patrol": [(0.0, E.T)], "patrol2": [(E.t("COST", 0.6), E.t("COST", 5.4))]})

# officer at the hatchback's passenger side, on the grass beyond the shoulder (never on the traffic side)
import figures as F  # noqa: E402
off = F.person(env, "officer", height=1.82, sex="m", skin=1, hair="short", jacket=F.NAVY, trousers=F.POLICE_DARK,
               shoes=F.srgb(16, 16, 18), sole=F.srgb(20, 20, 20), headwear="cap", headwear_color=F.POLICE_DARK,
               hem=0.585, belt=True, seed=12)
F.stand(off, (fw.x_out + K.SHOULDER + 0.6, Y_HATCH + 0.3), (x_sh, Y_HATCH + 1.0), E.N)

# flat lane glows (no text): SITUATION top: right lane red, middle lane green arrow; RULE: right lane pulses amber,
# middle lane green; RULE top: a flat down arrow ahead of the sedan (slow down)
red = jx.flat_mat("fl_mo_red", (1.0, 0.06, 0.04), emit=1.6, alpha=0.55)
amber = jx.flat_mat("fl_mo_amber", (1.0, 0.72, 0.0), emit=1.6, alpha=0.55)
green = jx.flat_mat("fl_mo_green", (0.1, 0.9, 0.3), emit=1.4, alpha=0.5)
w2 = K.LANE / 2 - 0.25


def show(obj, spans):
    obj.hide_render = True
    obj.keyframe_insert("hide_render", frame=1)
    for t0, t1 in spans:
        obj.hide_render = False
        obj.keyframe_insert("hide_render", frame=max(1, int(t0 * 30)))
        obj.hide_render = True
        obj.keyframe_insert("hide_render", frame=int(t1 * 30))


def arrow(name, x, y, length, m, down=False):
    """Flat arrow along +y (or a down arrow pointing -y when down), on the road."""
    h, sh = length * 0.42, 0.55
    pts = [(-sh, 0), (sh, 0), (sh, length - h), (1.4, length - h), (0, length), (-1.4, length - h), (-sh, length - h)]
    if down:
        pts = [(px, length - py) for px, py in pts]
    return K.poly(name, [(x + px, y + py) for px, py in pts], 0.035, m, env, uv=False)


show(K.rects("glow_right", [(R0 - w2, R0 + w2, Y_COP - 90.0, Y_HATCH + 30.0)], 0.03, red, env),
     [(E.t("SITUATION", 6.2), E.t("SITUATION", 8.0))])
show(arrow("arrow_mid", R1, Y_COP - 60.0, 26.0, green), [(E.t("SITUATION", 6.3), E.t("SITUATION", 8.0)),
                                                        (E.t("RULE", 0.8), E.t("RULE", 3.5))])
pulse = [(E.t("RULE", a), E.t("RULE", a + 0.35)) for a in (0.2, 0.9, 1.6, 2.3, 3.0)]
show(K.rects("glow_amber", [(R0 - w2, R0 + w2, Y_COP - 90.0, Y_HATCH + 30.0)], 0.03, amber, env), pulse)
show(arrow("arrow_down", R0, Y_COP - 75.0, 22.0, amber, down=True), [(E.t("RULE", 3.6), E.t("RULE", 8.0))])

UP = Vector((0, 1, 0))
xs = fw.x_out + K.SHOULDER
E.chase("H_chase", teal, "HOOK", 0.0, 1.8, back=9.0, up=2.6, ahead=90.0, side=-0.4)
E.shot("H_side", 28, "HOOK", 1.8, 3.0, lambda t: (Vector((xs + 8.0, Y_COP - 16.0, 3.2)), Vector((R0, Y_COP + 4.0, 1.2))))
# the stop fills the drone shots (r3: 100 m away, too small): 26 to 30 m off, 38 mm
E.shot("S_drone", 38, "SITUATION", 0.0, 2.7, lambda t: (Vector((xs + 7.0, Y_COP - 24.0 + 1.5 * t, 8.5)),
                                                       Vector((x_sh - 0.5, Y_COP + 4.5, 0.6))))
E.chase("S_chase", teal, "SITUATION", 2.7, 4.2, back=9.0, up=2.6, ahead=50.0, side=-0.6)
# "He passes too close.": from the verge behind the stop, the patrol car, hatchback and officer in frame while the
# sedan passes them in the right lane at 5.0 s without changing lanes
E.shot("S_pass", 30, "SITUATION", 4.2, 6.2, lambda t: (Vector((xs + 3.2, Y_COP - 21.0, 2.4)),
                                                      Vector((R0 + 0.4, Y_COP + 14.0, 0.9))))
E.shot("S_top", 30, "SITUATION", 6.2, 8.0, lambda t: (Vector((R1, Y_COP - 30.0, 70.0)), Vector((R1, Y_COP - 29.9, 0.0))),
       up=UP)
E.shot("R_drone", 34, "RULE", 0.0, 3.5, lambda t: (Vector((xs + 8.0 - 0.6 * t, Y_COP - 30.0, 10.0)),
                                                  Vector((R0, Y_COP + 2.0, 0.0))))
E.shot("R_top", 30, "RULE", 3.5, 8.0, lambda t: (E.pos(teal, E.t("RULE", t)) + Vector((0.0, 6.0, 46.0)),
                                                E.pos(teal, E.t("RULE", t)) + Vector((0.0, 6.1, 0.0))), up=UP)
# "The price:": the sedan passes the stopped patrol car too close (0.9 s), the second unit with its lights behind it
E.shot("C_pass", 30, "COST", 0.0, 1.6, lambda t: (Vector((xs + 3.2, Y_COP - 21.0, 2.4)),
                                                 Vector((R0 + 0.4, Y_COP + 14.0, 0.9))))
# then a mid-distance chase behind the second unit as it pulls the sedan over (no rear-corner close-up)
E.chase("C_follow", cop2, "COST", 1.6, 5.4, back=13.0, up=3.6, ahead=30.0, side=-0.8, lens=30)
E.shot("K_drone", 24, "CORRECT", 0.0, 2.7, lambda t: (Vector((xs + 12.0, Y_COP - 75.0 + 10 * t, 16.0)),
                                                     Vector((R1, Y_COP - 20.0 + 8 * t, 0.0))))
E.chase("K_chase", teal, "CORRECT", 2.7, 6.3, back=9.0, up=2.6, ahead=50.0, side=-0.6)
E.card(sg)
E.run(o, o["assets"], haze_skip=("fl_mo_red", "fl_mo_amber", "fl_mo_green"))
