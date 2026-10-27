"""Drive Like a Local: Florida #4 (release Thu 19 Nov 2026, launch day): stopped school bus (Florida Statutes
§316.172). 9:16, 30 fps, 34.5 s canonical (English) timeline: HOOK 0-3, SITUATION 3-11, RULE 11-19, COST 19-25.8,
CORRECT 25.8-31.5, END 31.5-34.5. Four-lane undivided road with only a painted double yellow (no raised median), a
generic yellow school bus at the right kerb: amber lamps, then alternating red lamps, stop arm and open door. No
children are shown anywhere.
Run: python fl04_school_bus.py OUT --frames 1-1035 --res 540 --samples 8 --assets ASSETS [--stills ..] [--check X]"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "fl01"), os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import fl01_uskit as K  # noqa: E402
import fl01_usscene as S  # noqa: E402
import jx  # noqa: E402
import world as W  # noqa: E402

o = S.cli()
lib, env, traffic = K.new_scene(o["assets"])
E = S.Ep([("HOOK", 3.0), ("SITUATION", 8.0), ("RULE", 8.0), ("COST", 6.8), ("CORRECT", 5.7), ("END", 3.0)])
art = K.Arterial(env, -900.0, 900.0)
A = art.lip
S.dress(env, lib, art, -900.0, 900.0, seed=4)
sg = K.sign(env, "S3-1", (A + 0.7, -160.0, K.KERB_H), 0.0, width=0.76, bottom=2.1)


def clear_card_background(sign, lens=35.0, frac=0.25, max_h_px=380, margin=3.5, reach=62.0):
    """QA r9 #1: a palm trunk of the verge row stood right behind the S3-1 plate on the end card. The END camera of
    S.Ep.card stands in front of the sign, 20 degrees towards the road, looking away from it, so the verge row of
    palms recedes through the frame behind the sign and the end lines. Every palm (with its children) standing
    behind the sign inside the card's horizontal field (plus `margin` m for the crown) out to `reach` m is removed,
    so the plate and the text sit on lot, mall and sky. Same geometry as card(). With seed 4 that is the four verge
    palms at y -159 to -103, all south of every other shot's camera (the HOOK chase starts at y -103 looking north
    and keeps the palm at y -85)."""
    ctr, w, h = S.sign_box(sign)
    fh = 36.0 / lens
    d = max(w / (frac * fh * 9 / 16), h / (max_h_px / 1920.0 * fh))
    n = sign.matrix_world.to_3x3() @ Vector((0, -1, 0))
    n = Vector((n.x, n.y, 0)).normalized()
    sides = [Vector((n.x * math.cos(a) - n.y * math.sin(a), n.x * math.sin(a) + n.y * math.cos(a), 0)) for a in (0.35, -0.35)]
    best = min(sides, key=lambda r: abs((ctr + r * d).x))
    cam, fwd = ctr + best * d, -best
    right = Vector((fwd.y, -fwd.x, 0))
    gone = []
    for ob in [x for x in bpy.data.objects if x.name.startswith("palm") and x.parent is None]:
        rel = ob.matrix_world.translation - cam
        f_, l_ = rel.dot(fwd), rel.dot(right)
        if d - 0.5 < f_ < reach and abs(l_) < f_ * fh * 9 / 32 + margin:
            gone.append((ob.name, round(ob.location.x, 1), round(ob.location.y, 1)))
            for x in [ob] + list(ob.children_recursive):
                bpy.data.objects.remove(x, do_unlink=True)
    print("END CARD palms removed", gone)


clear_card_background(sg)

mph = 0.44704
bus = K.hero(K.school_bus(lib), "bus_us", traffic, name="school_bus")
teal = K.hero(K.us_car("saloon", (0.0, 0.32, 0.34), "sedan", lib), "saloon", traffic)
pick = K.hero(K.us_car("suv", (0.45, 0.06, 0.05), "suv_x", lib), "suv", traffic)
cop = K.hero(K.us_car("saloon", None, "patrol", lib, police=True), "saloon", traffic)
x_bus = art.lane_x(1) + 0.55
PB = K.straight(x_bus)
s_bus = 2000.0                                   # bus centre at y = 0 when stopped
P0, P1 = K.straight(art.lane_x(0)), K.straight(art.lane_x(1))
PS = K.straight(art.lane_x(0, nb=False), south=True)        # far side, southbound inner lane
s_behind = 2000.0 - 5.35 - 6.0 - teal["L"] / 2               # sedan stopped 6 m behind the bus
PL = K.lane_change(art.lane_x(1), art.lane_x(0), -22.0, 14.0)
s_pick_stop = 2000.0 - 16.0 - pick["L"] / 2                  # path runs south: s = 2000 - y
E.take(bus, "HOOK", PB, s_bus - 14.0, 9.0, [(0, "cruise", 9.0), (0.4, "stop", s_bus)])
E.take(teal, "HOOK", P1, s_bus - 95.0, 40 * mph, [(0, "cruise", 40 * mph), (1.6, "stop", s_behind - 20)])
E.take(bus, "SITUATION", PB, s_bus, 0.0, [(0, "hold", None)])
E.take(teal, "SITUATION", PL, s_behind - 30.0, 30 * mph, [(0, "cruise", 35 * mph)], ind=[("L", 2.2, 3.6)])
E.take(pick, "SITUATION", PS, 2000.0 - 120.0, 40 * mph, [(0, "cruise", 40 * mph)])
for seg in ("RULE", "COST"):
    E.take(bus, seg, PB, s_bus, 0.0, [(0, "hold", None)])
E.take(teal, "COST", PL, s_behind - 32.0, 35 * mph, [(0, "cruise", 35 * mph)], ind=[("L", 0.6, 1.6)])
E.take(cop, "COST", PL, s_behind - 60.0, 37 * mph, [(0, "cruise", 37 * mph)])
E.take(bus, "CORRECT", PB, s_bus, 0.0, [(0, "hold", None), (3.4, "cruise", 6.0)])
E.take(teal, "CORRECT", P1, s_behind - 22.0, 25 * mph, [(0, "stop", s_behind), (3.4, "cruise", 6.0)])
E.take(pick, "CORRECT", PS, s_pick_stop - 25.0, 30 * mph, [(0, "stop", s_pick_stop), (3.4, "cruise", 8.0)])
red_on = [(E.t("HOOK", 1.2), E.t("CORRECT", 3.0))]          # lamps and arm stay out through RULE (all lanes stop)
E.bake(beacon={"school_bus": red_on, "patrol": [(E.t("COST", 1.0), E.t("COST", 6.8))]})

# amber lamps, stop arm, door (keyed on the bus instance's children)
amber = bpy.data.materials["bus_amber"].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
arm_lamp = W.principled("bus_arm_lamp", (0.5, 0.02, 0.02), 0.2, emit=(1.0, 0.04, 0.02), estr=0.0)
arm, door = K.bus_parts(bus, env, arm_lamp)
al = arm_lamp.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
f0 = int(E.t("HOOK", 0.4) * 30)
for f in range(1, E.N + 1):
    t = (f - 1) / 30.0
    on = any(a <= t < b for a, b in red_on)
    amb = E.t("HOOK", 0.4) <= t < E.t("HOOK", 1.2)
    blink = int(t / 0.33) % 2 == 0
    if f == 1 or f % 10 == 0 or f == f0:
        pass
    amber.default_value = 20.0 if (amb and blink) else 0.0
    amber.keyframe_insert("default_value", frame=f)
    al.default_value = 14.0 if (on and blink) else 0.0
    al.keyframe_insert("default_value", frame=f)
    ext = 1.0 if on else 0.0
    if E.t("HOOK", 1.2) <= t < E.t("HOOK", 1.7):
        ext = (t - E.t("HOOK", 1.2)) / 0.5
    arm.rotation_euler = (0, 0, (1.0 - ext) * math.pi / 2)
    arm.keyframe_insert("rotation_euler", frame=f)
    door.scale = (1.0, 1.0 - 0.7 * ext, 1.0)
    door.keyframe_insert("scale", frame=f)

# RULE: all four lanes behind and ahead of the bus glow red (stop) for the whole segment, so the overlay never turns
# "go" under "Without a raised median: all lanes stop" (r3 review); no green glow anywhere in this episode
red = jx.flat_mat("fl_stop_red", (1.0, 0.06, 0.04), emit=1.6, alpha=0.55)
for nm, m_, a, b in (("glow_red", red, 0.0, 8.0),):
    g = K.rects(nm, [(-art.edge + 0.2, -0.3, -45.0, 45.0), (0.3, art.edge - 0.2, -45.0, -7.0),
                     (0.3, art.edge - 0.2, 7.0, 45.0)], 0.03, m_, env)
    for f, h in ((1, True), (int(E.t("RULE", a) * 30), False), (int(E.t("RULE", b) * 30), True)):
        g.hide_render = h
        g.keyframe_insert("hide_render", frame=f)
xm = jx.flat_mat("fl_red_mark", (1.0, 0.08, 0.05), emit=2.0)
for k, xc in enumerate((art.lane_x(0), art.lane_x(0, nb=False))):
    for sgn in (1, -1):
        q = K.poly(f"mark_x{k}", [(xc - 2.2 * sgn - 0.45, -4.0), (xc - 2.2 * sgn + 0.45, -4.0),
                                  (xc + 2.2 * sgn + 0.45, 4.0), (xc + 2.2 * sgn - 0.45, 4.0)], 0.03, xm, env, uv=False)
        for f, h in ((1, True), (int(E.t("SITUATION", 5.5) * 30), False), (int(E.t("SITUATION", 8.0) * 30), True)):
            q.hide_render = h
            q.keyframe_insert("hide_render", frame=f)

UP = Vector((0, 1, 0))
E.chase("H_chase", teal, "HOOK", 0.0, 1.7, back=8.0, up=2.2, side=-0.8, ahead=60.0)
E.shot("H_close", 30, "HOOK", 1.7, 3.0, lambda t: (Vector((x_bus - 5.2, 1.0, 2.0)), Vector((x_bus - 1.2, 2.6, 1.7))))
E.shot("S_drone", 24, "SITUATION", 0.0, 2.7, lambda t: (Vector((-28.0, -60.0 + 3 * t, 32.0)), Vector((2.0, -8.0, 0))))
E.chase("S_chase", teal, "SITUATION", 2.7, 5.4, back=9.0, up=2.6, side=-0.4)
E.shot("S_top", 30, "SITUATION", 5.4, 8.0, lambda t: (Vector((0.0, 0.0, 46.0)), Vector((0.0, 0.1, 0.0))), up=UP)
E.shot("R_drone", 24, "RULE", 0.0, 3.5, lambda t: (Vector((-30.0 + 4 * t, -55.0, 26.0)), Vector((1.0, 0.0, 0.0))))
E.shot("R_top", 30, "RULE", 3.5, 8.0, lambda t: (Vector((0.0, 0.0, 50.0 + t)), Vector((0.0, 0.1, 0.0))), up=UP)
E.chase("C_chase", cop, "COST", 0.0, 6.8, back=9.0, up=2.4)
E.shot("K_drone", 26, "CORRECT", 0.0, 2.7, lambda t: (Vector((-26.0, -48.0, 20.0)), Vector((1.0, -4.0, 1.0))))
E.chase("K_chase", teal, "CORRECT", 2.7, 5.7, back=8.0, up=2.2, side=-0.8, ahead=40.0)
E.card(sg)
E.run(o, o["assets"], haze_skip=("fl_stop_red", "fl_red_mark"))
