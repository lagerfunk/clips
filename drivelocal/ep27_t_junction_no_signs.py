"""Drive Like a Local #27, Germany: T-junction with no signs, who goes first? (quiz). 9:16, 30 fps, segments in
canonical order (post_ep27.py cuts them per language). Unsigned Einmuendung (kit/junctions.py kind 't', the approved
town streets), low warm October sun, people on the footways.
  SETUP     drone, then top: A (red) on the stem turning left, B (blue) from the west, C (silver) from the east,
            all three slowing at the mouth; no signs, no lines
  QUESTION  top, slow motion, badges and coloured paths
  TIMER     10 s hold
  ANSWER    C (nothing on its right) goes, A (C was on its right) turns left, B (A was on its right) goes last;
            low chase behind B at the end
  RULE      top: an arrow points to each car's right side in turn; drone over the empty junction
  COST      B treats the wider street as the main road and drives on, A pulls out from its right; both stop a hand
            apart (solved); top with the cards
  END       road-grey card (no signs in this episode)
Rule: StVO section 8 (1) (rechts vor links at Einmuendungen without signs; facts t_junction_rvl, rvl_hinder,
rvl_danger).
Run: python ep27_t_junction_no_signs.py OUTDIR --frames 1-1044 --res 540 --samples 8 --assets ASSETS
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit"), os.path.join(HERE, "..", "ep06")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import ep06_zshared as Z  # noqa: E402
import junctions as JN  # noqa: E402
import jx  # noqa: E402

SEGS = [("SETUP", 3.0), ("QUESTION", 2.0), ("TIMER", 10.0), ("ANSWER", 5.6), ("RULE", 5.0), ("COST", 6.0),
        ("END", 3.2)]
o = Z.cli()
tl = Z.Timeline(SEGS)
N, FPS, t = tl.N, Z.FPS, tl.t

HEROES = [("hatch", (0.62, 0.05, 0.03), "carA", "QX LK 271", 0.3),
          ("estate", (0.03, 0.12, 0.42), "carB", "JX RS 27", 0.45),
          ("saloon", (0.62, 0.63, 0.65), "carC", "QZ SB 727", 0.5)]
S = JN.build(o["ASSETS"], "t", seed=7, heroes=HEROES)
env, traffic = S["env"], S["traffic"]
fnt = Z.font(HERE)
cA, cB, cC = (S["heroes"][k] for k in ("carA", "carB", "carC"))
A, B, C = Z.Actor(cA, tl), Z.Actor(cB, tl), Z.Actor(cC, tl)

PA = S["lane_path"]("S", "W")          # stem, turning left
PB = S["lane_path"]("W", "E")          # from the west, straight on
PC = S["lane_path"]("E", "W")          # from the east, straight on
MOUTH = PA.s_mouth                      # 86: the front reaches the start of the kerb radius
sA_f = MOUTH - cA["L"] / 2 + 0.4
sB_f = MOUTH - cB["L"] / 2 - 0.6
sC_f = MOUTH - cC["L"] / 2 - 0.6
indA = lambda s, tt: "L" if s < PA.s_mouth + 18.0 else None  # noqa: E731

# ---------------------------------------------------------------- SETUP .. TIMER
nS, nQ, nT = tl.nf("SETUP"), tl.nf("QUESTION"), tl.nf("TIMER")
svA_s = Z.anchor(jx.kinematics(0.0, 6.0, [(0, "cruise", 6.0), (0.9, "cruise", 2.0)], nS + 1, a_brake=2.4), 3.0, sA_f)
svB_s = Z.anchor(jx.kinematics(0.0, 7.0, [(0, "cruise", 7.0), (1.2, "cruise", 5.0)], nS + 1, a_brake=2.4), 3.0, sB_f)
svC_s = Z.anchor(jx.kinematics(0.0, 7.0, [(0, "cruise", 7.0), (1.1, "cruise", 5.0)], nS + 1, a_brake=2.4), 3.0, sC_f)
A.drive("SETUP", PA, svA_s[:nS], lambda s, tt: "L" if tt >= 1.0 else None)
B.drive("SETUP", PB, svB_s[:nS])
C.drive("SETUP", PC, svC_s[:nS])
A.drive("QUESTION", PA, Z.slow(sA_f, 0.2, nQ), "L", v_nom=2.0)
B.drive("QUESTION", PB, Z.slow(sB_f, 0.5, nQ), None, v_nom=5.0)
C.drive("QUESTION", PC, Z.slow(sC_f, 0.5, nQ), None, v_nom=5.0)
qA, qB, qC = sA_f + 0.2 * nQ / FPS, sB_f + 0.5 * nQ / FPS, sC_f + 0.5 * nQ / FPS
A.drive("TIMER", PA, Z.slow(qA, 0.04, nT), "L", v_nom=2.0)
B.drive("TIMER", PB, Z.slow(qB, 0.1, nT), None, v_nom=5.0)
C.drive("TIMER", PC, Z.slow(qC, 0.1, nT), None, v_nom=5.0)
fA, fB, fC = qA + 0.04 * nT / FPS, qB + 0.1 * nT / FPS, qC + 0.1 * nT / FPS

# ---------------------------------------------------------------- ANSWER: C, then A, then B
nA = tl.nf("ANSWER")
svC = jx.kinematics(fC, 5.0, [(0, "cruise", 6.5)], nA)
C.drive("ANSWER", PC, svC)
# A waits until C's tail has passed the stem (x below -2), then turns left
xC_clear = PA.at(fA)[0].x - 3.5
t_C = next(k / FPS for k, (s, v) in enumerate(svC) if PC.at(s)[0].x + cC["L"] / 2 < xC_clear)
# A creeps at walking pace while C passes in front, then turns as C clears
T_A_GO = max(1.4, t_C - 0.8)
svA = jx.kinematics(fA, 2.0, [(0, "cruise", 1.0), (T_A_GO, "cruise", 6.0)], nA, a_acc=3.2)
A.drive("ANSWER", PA, svA, indA)
# B stops short of A's path and goes when A's tail has cleared its lane
sB_stop = fB + (-4.2 - (PB.at(fB)[0].x + cB["L"] / 2))     # front stops 4.2 m short of the stem's centre line
svA_xy = [PA.at(s)[0] for s, _v in svA]
# B moves off once A has crossed its lane (A is long gone when B gets there)
t_A = next((k / FPS for k, p in enumerate(svA_xy) if k / FPS > T_A_GO and p.y > -1.5), 3.4)
T_B_GO = max(3.4, t_A + 0.1)
svB = jx.kinematics(fB, 5.0, [(0, "stop", sB_stop), (T_B_GO, "cruise", 6.0)], nA, a_acc=2.6)
B.drive("ANSWER", PB, svB)

# ---------------------------------------------------------------- RULE: the frozen moment again
nR = tl.nf("RULE")
A.drive("RULE", PA, [(fA, 0.0)] * nR, "L")
B.drive("RULE", PB, [(fB, 0.0)] * nR)
C.drive("RULE", PC, [(fC, 0.0)] * nR)

# ---------------------------------------------------------------- COST: B drives on, A pulls out from its right
nCo = tl.nf("COST")
# A pulls out far enough to block B's lane (its front crosses the centre line of the through street)
svA_c = jx.kinematics(fA - 0.3, 0.0, [(0, "hold", None), (0.3, "cruise", 5.0), (1.4, "stop", fA + 6.3)], nCo,
                      a_acc=3.5)
A.drive("COST", PA, svA_c, indA)
svB_c = Z.solve_stop(PB, cB, fB - 7.0 * 1.0, 7.0, 6.8, nCo, tl.f0("COST"), [(A, cA["W"] + 0.04)], target=0.3)
pB_c = Z.dive(svB_c)
B.drive("COST", PB, svB_c, None, pitch=lambda k: pB_c[k])
C.drive("COST", PC, [(-60.0, 0.0)] * nCo)
for X in (A, B, C):
    X.bake()

# ---------------------------------------------------------------- traffic, people, leaves
amb = [Z.Actor(Z.fleet_car(S, "suv_white", "amb0"), tl), Z.Actor(Z.fleet_car(S, "hatch_blue", "amb1"), tl)]
amb[0].whole(Z.line_path(JN.arm_pt("W", 52, -1.5), JN.arm_pt("W", 240, -1.5)), Z.cruise(0.0, 8.5, N))
amb[1].whole(Z.line_path(JN.arm_pt("S", 52, -1.5), JN.arm_pt("S", 240, -1.5)), Z.cruise(0.0, 8.0, N))
for X in amb:
    X.bake()
FOOT = 3.0 + 0.16 + 1.25
Z.walkers(S, tl, [(Z.line_path((-40.0, FOOT), (40.0, FOOT)), 0.0, 1.15, 14),
                  (Z.line_path((-12.0, -FOOT), (-90.0, -FOOT)), 0.0, 1.25, 15),
                  (Z.line_path((FOOT, -13.0), (FOOT, -90.0)), 0.0, 1.2, 16),
                  (Z.line_path((30.0, FOOT + 0.4), (90.0, FOOT + 0.4)), 0.0, 1.05, 17)])
Z.cyclists(S, tl, [(Z.line_path((50.0, -2.2), (240.0, -2.2)), 0.0, 4.6, 5)])
Z.leaves(S, [((-1, 0), 3.0, 12, 120), ((1, 0), 3.0, 12, 120), ((0, -1), 3.0, 12, 120)])

# ---------------------------------------------------------------- quiz layer
BC = jx.BADGE_COLOURS
T_CHASE = 4.5                          # badges go before the low chase (they would fill the frame)
Z.letter_badge("A", A, traffic, fnt, t("QUESTION", 0.2), t("ANSWER", 2.0), size=2.6)
Z.letter_badge("B", B, traffic, fnt, t("QUESTION", 0.3), t("ANSWER", 3.8), size=2.6)
Z.letter_badge("C", C, traffic, fnt, t("QUESTION", 0.5), t("ANSWER", 0.2), size=2.6)
Z.number_badge(1, C, traffic, fnt, t("ANSWER", 0.3), t("ANSWER", T_CHASE - 0.2), size=2.6)
Z.number_badge(2, A, traffic, fnt, t("ANSWER", 2.1), t("ANSWER", T_CHASE - 0.2), size=2.6)
Z.number_badge(3, B, traffic, fnt, t("ANSWER", 3.9), t("ANSWER", T_CHASE - 0.2), size=2.6)
rA = (qA + cA["L"] / 2 + 0.6, MOUTH + 26.0)
rB = (qB + cB["L"] / 2 + 0.6, MOUTH + 30.0)
rC = (qC + cC["L"] / 2 + 0.6, MOUTH + 30.0)
jx.ribbon(PA, *rA, BC["A"], env, t("QUESTION", 0.4), t("ANSWER", 0.0), width=1.1, z=0.04, name="ribA")
jx.ribbon(PB, *rB, BC["B"], env, t("QUESTION", 0.45), t("ANSWER", 0.0), width=1.1, z=0.05, name="ribB")
jx.ribbon(PC, *rC, BC["C"], env, t("QUESTION", 0.5), t("ANSWER", 0.0), width=1.1, z=0.06, name="ribC")
jx.ribbon(PC, *rC, Z.GREEN, env, t("ANSWER", 0.2), t("ANSWER", 5.2), width=1.1, z=0.065, name="ribC_go")
jx.ribbon(PA, *rA, Z.GREEN, env, t("ANSWER", 2.0), t("ANSWER", 5.2), width=1.1, z=0.045, name="ribA_go")
jx.ribbon(PB, *rB, Z.GREEN, env, t("ANSWER", 3.8), t("ANSWER", 5.2), width=1.1, z=0.055, name="ribB_go")
# RULE: what each driver sees on the right (C: nothing, A: C, B: A)
WHITE = (1.0, 0.95, 0.85)
for k, (X, ang, t_on) in enumerate(((C, 90.0, 0.3), (A, 0.0, 1.2), (B, -90.0, 2.0))):
    p = X.poses[tl.f0("RULE") - 1]
    d = Vector((math.cos(math.radians(ang)), math.sin(math.radians(ang)), 0.0))
    Z.arrow_icon(f"right{k}", traffic, t("RULE", t_on), t("RULE", 4.9), angle=ang, color=WHITE,
                 loc=Vector((p[0], p[1], 2.4)) + d * 3.6, size=2.2, blink=False)

# ---------------------------------------------------------------- cameras
UP = Z.UP
shots = jx.Shots(N)
TOP = Z.top(0.0, -3.0, 50.0, tilt=3.0)
shots.add("S_drone", 30, t("SETUP"), t("SETUP", 1.5),
          Z.orbit((0, -2, 0), 30.0, 34.0, -118.0, -100.0, t("SETUP"), t("SETUP", 1.5), tgt=(0.0, -1.0, 0.0)))
shots.add("Q_top", 30, t("SETUP", 1.5), t("TIMER", 10.0),
          Z.top(0.0, -3.0, 50.0, tilt=3.0, drift=(0, 0, -2.0), t0=t("SETUP", 1.5), t1=t("TIMER", 10.0)),
          up_fn=lambda tt: UP)
shots.add("A_top", 30, t("ANSWER"), t("ANSWER", T_CHASE), TOP, up_fn=lambda tt: UP)
shots.add("A_chase", 24, t("ANSWER", T_CHASE), t("ANSWER", 5.6),
          lambda tt: Z.follow(B, int(round(tt * FPS)) + 1, back=6.5, up=1.3, side=-1.2, ahead=14.0, look_z=0.9))
shots.add("R_top", 30, t("RULE"), t("RULE", 2.5), TOP, up_fn=lambda tt: UP)
shots.add("R_drone", 30, t("RULE", 2.5), t("RULE", 5.0),
          Z.orbit((0, -2, 0), 36.0, 30.0, -60.0, -40.0, t("RULE", 2.5), t("RULE", 5.0), tgt=(0.0, -1.0, 0.0)))
# low, east of the junction on the far side of the through street: B drives towards the camera, A pulls out
# in front of it from the stem
pA9, pB9 = A.track[tl.f("COST", 1.9) - 1], B.track[tl.f("COST", 1.9) - 1]
MID9 = Vector(((pA9["x"] + pB9["x"]) / 2, (pA9["y"] + pB9["y"]) / 2, 0.75))
shots.add("C_close", 30, t("COST"), t("COST", 2.2),
          lambda tt: (Vector((7.5, 2.3, 1.15)) - Vector((1.2, 0.0, 0.0)) * jx.ease((tt - t("COST")) / 2.2),
                      MID9))
pA2, pB2 = A.track[tl.f("COST", 2.5) - 1], B.track[tl.f("COST", 2.5) - 1]
shots.add("C_top", 30, t("COST", 2.2), t("COST", 6.0),
          Z.top((pA2["x"] + pB2["x"]) / 2, (pA2["y"] + pB2["y"]) / 2 - 3.0, 30.0, tilt=2.0), up_fn=lambda tt: UP)


def t_diagram(c, z):
    """No signs in this episode: the card shows the T-junction itself as a flat white outline."""
    paint = bpy.data.materials.get("card_paint")
    road = jx.flat_mat("card_road", (0.025, 0.026, 0.03), emit=1.0)
    y0 = -0.9
    for name, q, m in (("card_t_bar", [(-3.6, y0 - 0.55), (3.6, y0 - 0.55), (3.6, y0 + 0.55), (-3.6, y0 + 0.55)], road),
                       ("card_t_stem", [(-0.55, y0 - 2.6), (0.55, y0 - 2.6), (0.55, y0 - 0.5), (-0.55, y0 - 0.5)],
                        road)):
        Z.W.mesh_obj(name, [(x, y, z + 0.004) for x, y in q], [(0, 1, 2, 3)], m, c)
    for k, (x0, x1, y_) in enumerate(((-3.6, 3.6, y0 + 0.6), (-3.6, -0.6, y0 - 0.6), (0.6, 3.6, y0 - 0.6))):
        Z.W.mesh_obj(f"card_t_edge{k}", [(x0, y_ - 0.035, z + 0.006), (x1, y_ - 0.035, z + 0.006),
                                         (x1, y_ + 0.035, z + 0.006), (x0, y_ + 0.035, z + 0.006)], [(0, 1, 2, 3)],
                     paint, c)
    for k, x_ in enumerate((-0.6, 0.6)):
        Z.W.mesh_obj(f"card_t_stemedge{k}", [(x_ - 0.035, y0 - 2.6, z + 0.006), (x_ + 0.035, y0 - 2.6, z + 0.006),
                                             (x_ + 0.035, y0 - 0.6, z + 0.006), (x_ - 0.035, y0 - 0.6, z + 0.006)],
                     [(0, 1, 2, 3)], paint, c)


Z.end_card(tl, "END", shots, [], env, diagram=t_diagram)
bpy.context.scene.camera = bpy.data.objects["S_drone"]

Z.sun(o["ASSETS"], 228.0, 12.0, 5.4)
print("EP27 C clear", round(t_C, 2), "A goes", round(T_A_GO, 2), "B goes", round(T_B_GO, 2), "frames", N, flush=True)
if "--probe" in sys.argv:
    Z.probe([int(v) for v in sys.argv[sys.argv.index("--probe") + 1].split(",")])
if o["DRY"]:
    print("DRY_OK", len(bpy.data.objects), "objects", flush=True)
    raise SystemExit(0)
Z.setup_render(o, tl)
no_blur = tl.cut_frames()
for X in [A, B, C] + amb:
    no_blur |= X.jumps()
Z.render(shots, o["OUT"], Z.todo_frames(o, tl), no_blur)
print("RENDER_DONE", o["FR"])
