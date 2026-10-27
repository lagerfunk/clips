"""Drive Like a Local #18, Germany: priority road that bends, who gives way? (quiz). 9:16, 30 fps, segments in
canonical order (post_ep18.py cuts them per language). The approved X junction with a bending priority road from the
west to the south (kit/junctions.py kind 'bend'): Zeichen 306 over the Zusatzzeichen 1002 on the priority arms,
Zeichen 205 over the plate on the side arms (Commons files via kit/signs.py). Low warm October sun.
  SETUP     drone, then top: A (red) from the west follows the bend (right indicator), C (silver) from the south
            follows it the other way (left indicator), B (blue) on the east side road stops at its mouth
  QUESTION  top, slow motion, badges and coloured paths
  TIMER     10 s hold
  ANSWER    the priority diamond (306) floats over A and C, the give-way triangle (205) over B; A and C go, B waits
            and crosses last; low chase behind B
  RULE      A's eye on the approach, 306 over the bend plate on the right; close on the sign with an indicator icon
  COST      A follows the bend without indicating; B, turning left into the same street, pulls out; both stop
            about a metre apart (solved, a visible gap); raised two-shot with the cards
  END       road-grey card with the signs on the west and east arms (306 and 205, each over its plate)
The broken wide line the kit paints along the bend is not verified: no caption names it and nothing points at it.
Rules: StVO section 8 (Zeichen 306 with Zusatzzeichen 1002, 205), section 9 (1) (indicate when following the bend);
facts bending_priority_indicate, bending_priority_fine, rvl_danger.
Run: python ep18_bending_priority.py OUTDIR --frames 1-1044 --res 540 --samples 8 --assets ASSETS
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

HEROES = [("hatch", (0.62, 0.05, 0.03), "carA", "QX LK 181", 0.3),
          ("estate", (0.03, 0.12, 0.42), "carB", "JX RS 18", 0.45),
          ("saloon", (0.62, 0.63, 0.65), "carC", "QZ SB 818", 0.5)]
PRIORITY = ("S", "W")
S = JN.build(o["ASSETS"], "bend", seed=5, heroes=HEROES, priority=PRIORITY)
env, traffic = S["env"], S["traffic"]
fnt = Z.font(HERE)
cA, cB, cC = (S["heroes"][k] for k in ("carA", "carB", "carC"))
A, B, C = Z.Actor(cA, tl), Z.Actor(cB, tl), Z.Actor(cC, tl)

PA = S["lane_path"]("W", "S")          # A: priority road from the west, follows the bend (right)
PC = S["lane_path"]("S", "W")          # C: priority road from the south, follows the bend (left)
PB = S["lane_path"]("E", "W")          # B: side road from the east, straight across
PB2 = S["lane_path"]("E", "S")         # B in the COST replay: turning left into the south arm
assert PA.follows_priority and PC.follows_priority and not PB.on_priority
L95 = 95.0
sA_f = L95 - 9.8 - cA["L"] / 2
sC_f = L95 - 9.8 - cC["L"] / 2
sB = L95 - 9.3 - cB["L"] / 2           # B waits with its front at its mouth
indA = lambda s, tt: "R" if s < L95 + 14.0 else None  # noqa: E731
indC = lambda s, tt: "L" if s < L95 + 16.0 else None  # noqa: E731

# ---------------------------------------------------------------- SETUP .. TIMER
nS, nQ, nT = tl.nf("SETUP"), tl.nf("QUESTION"), tl.nf("TIMER")
svA_s = Z.anchor(jx.kinematics(0.0, 8.0, [(0, "cruise", 8.0), (0.8, "cruise", 6.0)], nS + 1, a_brake=2.4), 3.0, sA_f)
svC_s = Z.anchor(jx.kinematics(0.0, 7.0, [(0, "cruise", 7.0), (1.0, "cruise", 5.0)], nS + 1, a_brake=2.4), 3.0, sC_f)
A.drive("SETUP", PA, svA_s[:nS], lambda s, tt: "R" if tt >= 1.5 else None)
C.drive("SETUP", PC, svC_s[:nS], lambda s, tt: "L" if tt >= 1.8 else None)
B.drive("SETUP", PB, Z.stop_profile(sB - 5.83, 5.0, sB, 3.0, nS))
A.drive("QUESTION", PA, Z.slow(sA_f, 0.6, nQ), "R", v_nom=6.0)
C.drive("QUESTION", PC, Z.slow(sC_f, 0.5, nQ), "L", v_nom=5.0)
B.hold("QUESTION", PB, sB)
qA, qC = sA_f + 0.6 * nQ / FPS, sC_f + 0.5 * nQ / FPS
A.drive("TIMER", PA, Z.slow(qA, 0.12, nT), "R", v_nom=6.0)
C.drive("TIMER", PC, Z.slow(qC, 0.1, nT), "L", v_nom=5.0)
B.hold("TIMER", PB, sB)
fA, fC = qA + 0.12 * nT / FPS, qC + 0.1 * nT / FPS

# ---------------------------------------------------------------- ANSWER: A and C follow the bend, B waits
nA = tl.nf("ANSWER")
svA = jx.kinematics(fA, 6.0, [(0, "cruise", 6.5)], nA)
svC = jx.kinematics(fC, 5.0, [(0, "cruise", 6.0)], nA)
A.drive("ANSWER", PA, svA, indA)
C.drive("ANSWER", PC, svC, indC)
t_C = next((k / FPS for k, (s, v) in enumerate(svC) if PC.at(s)[0].x + cC["L"] / 2 < -14.0), 3.2)
T_B_GO = max(3.2, t_C)
svB = jx.kinematics(sB, 0.0, [(0, "hold", None), (T_B_GO, "cruise", 6.0)], nA, a_acc=2.8)
B.drive("ANSWER", PB, svB)

# ---------------------------------------------------------------- RULE: A's eye, then the sign
nR = tl.nf("RULE")
A.drive("RULE", PA, Z.cruise(L95 - 46.0, 7.0, nR), "R")
B.hold("RULE", PB, sB)

# ---------------------------------------------------------------- COST: no indicator, B pulls out to the left
nCo = tl.nf("COST")
sB2 = L95 - 9.3 - cB["L"] / 2
# B has pulled out to turn left into the south arm, the street A is about to follow the bend into; the two paths
# meet at the mouth of the south arm, so A (no indicator, B read it as going straight on) has to brake hard.
svB_c = jx.kinematics(sB2 + 6.0, 4.5, [(0, "cruise", 5.5), (2.0, "stop", sB2 + 18.5)], nCo, a_acc=2.5)
B.drive("COST", PB2, svB_c, "L")
s_mergeA = PA.s_first(lambda p: p.y < -8.0 and p.x > -3.0)
# near miss with a visible gap (QA r3: at 0.35 m the two bodies read as one from the close-up camera): every corner
# of A stays GAP_COST metres from B's body (half width plus mirrors)
GAP_COST = 1.1
svA_c = Z.solve_stop(PA, cA, s_mergeA - cA["L"] / 2 - 6.0 * 1.9, 6.0, 6.5, nCo, tl.f0("COST"),
                     [(B, cB["W"] + 0.12)], target=GAP_COST)
GAP_SEEN = Z.min_gap(PA, cA["L"], cA["W"] + 0.12, svA_c, tl.f0("COST"), [(B, cB["W"] + 0.12)])
pA_c = Z.dive(svA_c)
A.drive("COST", PA, svA_c, None, pitch=lambda k: pA_c[k])
T_A_BRAKE = next((k / FPS for k in range(1, nCo) if svA_c[k][1] < svA_c[k - 1][1] - 1e-3), 1.2)
for X in (A, B, C):
    X.bake()

# ---------------------------------------------------------------- traffic, people, leaves
amb = [Z.Actor(Z.fleet_car(S, "estate_grey", "amb0"), tl), Z.Actor(Z.fleet_car(S, "suv_dark", "amb1"), tl)]
amb[0].whole(Z.line_path((1.5, 45.0), (1.5, 240.0)), Z.cruise(0.0, 8.5, N))
amb[1].whole(Z.line_path((-55.0, 1.5), (-240.0, 1.5)), Z.cruise(0.0, 9.0, N))
for X in amb:
    X.bake()
FOOT = 3.0 + 0.16 + 1.25
Z.walkers(S, tl, [(Z.line_path((FOOT, -12.0), (FOOT, -90.0)), 0.0, 1.2, 18),
                  (Z.line_path((-FOOT, 12.0), (-FOOT, 90.0)), 0.0, 1.25, 19),
                  (Z.line_path((12.0, FOOT), (90.0, FOOT)), 0.0, 1.1, 20),
                  (Z.line_path((-12.0, -FOOT), (-90.0, -FOOT)), 0.0, 1.3, 21)])
Z.cyclists(S, tl, [(Z.line_path((-2.2, -42.0), (-2.2, -240.0)), 0.0, 4.5, 6)])
Z.leaves(S, [((-1, 0), 3.0, 12, 120), ((1, 0), 3.0, 12, 120), ((0, -1), 3.0, 12, 120), ((0, 1), 3.0, 12, 120)])

# ---------------------------------------------------------------- quiz layer
BC = jx.BADGE_COLOURS
Z.letter_badge("A", A, traffic, fnt, t("QUESTION", 0.2), t("ANSWER", 0.2), size=2.6)
Z.letter_badge("B", B, traffic, fnt, t("QUESTION", 0.3), t("ANSWER", 0.2), size=2.6)
Z.letter_badge("C", C, traffic, fnt, t("QUESTION", 0.5), t("ANSWER", 0.2), size=2.6)
T_CHASE = 4.1                          # icons go before the low chase (they would fill the frame)
Z.sign_icon("306", traffic, t("ANSWER", 0.35), t("ANSWER", T_CHASE - 0.2), width=2.2, actor=A, dz=3.4)
Z.sign_icon("306", traffic, t("ANSWER", 0.45), t("ANSWER", T_CHASE - 0.2), width=2.2, actor=C, dz=3.4)
Z.sign_icon("205", traffic, t("ANSWER", 0.25), t("ANSWER", T_CHASE - 0.2), width=2.6, actor=B, dz=3.6)
rA = (qA + cA["L"] / 2 + 0.6, L95 + 22.0)
rB = (sB + cB["L"] / 2 + 0.6, L95 + 30.0)
rC = (qC + cC["L"] / 2 + 0.6, L95 + 24.0)
jx.ribbon(PA, *rA, BC["A"], env, t("QUESTION", 0.4), t("ANSWER", 0.3), width=1.1, z=0.04, name="ribA")
jx.ribbon(PB, *rB, BC["B"], env, t("QUESTION", 0.45), t("ANSWER", 3.2), width=1.1, z=0.05, name="ribB")
jx.ribbon(PC, *rC, BC["C"], env, t("QUESTION", 0.5), t("ANSWER", 0.3), width=1.1, z=0.06, name="ribC")
jx.ribbon(PA, *rA, Z.GREEN, env, t("ANSWER", 0.3), t("ANSWER", 5.2), width=1.1, z=0.045, name="ribA_go")
jx.ribbon(PC, *rC, Z.GREEN, env, t("ANSWER", 0.4), t("ANSWER", 5.2), width=1.1, z=0.065, name="ribC_go")
jx.ribbon(PB, *rB, Z.GREEN, env, t("ANSWER", T_B_GO), t("ANSWER", 5.2), width=1.1, z=0.055, name="ribB_go")
west = next(r for r in S["signs"] if r.get("arm") == "W")
east = next(r for r in S["signs"] if r.get("arm") == "E")
SIGN_W = Vector((west["loc"][0], west["loc"][1], 0.0))
Z.arrow_icon("bend_r", traffic, t("RULE", 2.7), t("RULE", 4.9), side="R", loc=SIGN_W + Vector((0.2, 1.25, 2.85)),
             size=0.75)

# ---------------------------------------------------------------- cameras
UP = Z.UP
shots = jx.Shots(N)
TOP = Z.top(-2.5, -3.5, 50.0, tilt=3.0)
shots.add("S_drone", 30, t("SETUP"), t("SETUP", 1.5),
          Z.orbit((-3, -3, 0), 30.0, 35.0, -125.0, -105.0, t("SETUP"), t("SETUP", 1.5), tgt=(-2.0, -2.0, 0.0)))
shots.add("Q_top", 30, t("SETUP", 1.5), t("TIMER", 10.0),
          Z.top(-2.5, -3.5, 50.0, tilt=3.0, drift=(0, 0, -2.0), t0=t("SETUP", 1.5), t1=t("TIMER", 10.0)),
          up_fn=lambda tt: UP)
shots.add("A_top", 30, t("ANSWER"), t("ANSWER", T_CHASE), TOP, up_fn=lambda tt: UP)
shots.add("A_chase", 24, t("ANSWER", T_CHASE), t("ANSWER", 5.6),
          lambda tt: Z.follow(B, int(round(tt * FPS)) + 1, back=6.5, up=1.3, side=-1.2, ahead=14.0, look_z=0.9))


def pov(tt):
    f = int(round(tt * FPS)) + 1
    u = (tt - t("RULE")) / 2.5
    return Z.driver_eye(A, f, look=24.0, pan=-0.12 - 0.1 * jx.ease(u))


shots.add("R_pov", 30, t("RULE"), t("RULE", 2.5), pov)
A.hide_during([(tl.f0("RULE"), tl.f("RULE", 2.5))])
SIGN_TGT = SIGN_W + Vector((0.0, 0.0, 2.85))
shots.add("R_sign", 38, t("RULE", 2.5), t("RULE", 5.0),
          lambda tt: (SIGN_TGT + Vector((-5.2, 1.9, -0.25)) + Vector((1.0, -0.3, 0.0)) *
                      jx.ease((tt - t("RULE", 2.5)) / 2.5), SIGN_TGT + Vector((0.0, 0.5, 0.0))))
shots.add("C_top", 30, t("COST"), t("COST", 2.2), TOP, up_fn=lambda tt: UP)
# raised view across the gap (QA r3: the low two-shot stood behind the verge and the two bodies overlapped on
# screen): the camera looks at right angles to A's heading, from the junction side (over the carriageway, not the
# gardens), so the asphalt between A's bonnet and B's flank runs across the frame; the cars sit in the lower third,
# under the fine cards
fCC = tl.f("COST", 2.6)
MID_C = (A.at(fCC) + B.at(fCC)) / 2
yA = A.yaw_at(fCC)
N_C = Vector((math.sin(yA), -math.cos(yA), 0.0))
if N_C.dot(-MID_C) < 0:
    N_C = -N_C
P_C0, P_C1 = MID_C + N_C * 13.5 + Vector((0, 0, 5.0)), MID_C + N_C * 12.5 + Vector((0, 0, 4.7))
for P_ in (P_C0, P_C1):            # keep the camera over the east arm's carriageway (|y| < 3), clear of the footway
    P_.y = max(-2.2, min(2.2, P_.y))
T_C = MID_C + Vector((0, 0, 3.4))


def cost_view(tt):
    return P_C0.lerp(P_C1, jx.ease((tt - t("COST", 2.2)) / 3.8)), T_C


shots.add("C_close", 20, t("COST", 2.2), t("COST", 6.0), cost_view)


def stack(rec):
    return [(s_, i_, 2.2 if i_ in ("306", "205") else 2.0) for s_, i_ in zip(rec["sets"], rec["ids"])]


Z.end_card(tl, "END", shots, [stack(west), stack(east)], env)
bpy.context.scene.camera = bpy.data.objects["S_drone"]

Z.sun(o["ASSETS"], 222.0, 12.0, 5.4)
stubs = [ob.name for ob in bpy.data.objects if ob.get("stub")]
if stubs:
    raise SystemExit("placeholder signs: " + ", ".join(stubs[:5]))
print("EP18 plates W", west["ids"], "E", east["ids"], "B goes", round(T_B_GO, 2), "A brakes in COST",
      round(T_A_BRAKE, 2), "cost gap", round(GAP_SEEN, 2), "A", tuple(round(v, 1) for v in A.at(fCC)), "B",
      tuple(round(v, 1) for v in B.at(fCC)), "cost camera", tuple(round(v, 1) for v in P_C0), "frames", N, flush=True)
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
