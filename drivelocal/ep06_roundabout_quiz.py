"""Drive Like a Local #6, Germany: roundabout quiz (who goes first?). 9:16, 30 fps, segments in canonical order
(post_ep06.py cuts them per language). Single-lane Kreisverkehr (kit/roundabout.py, D 30 m), Zeichen 205 over 215
at every entry, low warm October sun, people on the footways.
  SETUP     drone orbit, then top: A (red) brakes to the give-way line at the south entry, B (blue) circulates from
            the west, C (silver) waits at the east entry
  QUESTION  top, 10 % slow motion, badges A B C and coloured paths
  TIMER     10 s hold, B creeps at 2 %
  ANSWER    B passes (1), A enters behind it (2), C waits for A, then goes (3); low angle at C's entry at the end
  RULE      raised view from behind A, waiting at the give-way line, while B comes round the circle from the left
            and passes in front of it; then top: the circulating lane glows
  COST      A pulls out in front of B; B brakes hard, stops a hand's width from A (solved, not guessed)
  END       road-grey card with Zeichen 205 and 215
Rule: StVO section 8 (1a): with Zeichen 215 under 205 the traffic on the circle has priority (facts: roundabout_priority).
Run: python ep06_roundabout_quiz.py OUTDIR --frames 1-1044 --res 540 --samples 8 --assets ASSETS [--stills 60,300]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit"), os.path.join(HERE, "..", "ep06")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import ep06_zshared as Z  # noqa: E402
import junctions as JN  # noqa: E402
import jx  # noqa: E402
import roundabout as RB  # noqa: E402

SEGS = [("SETUP", 3.0), ("QUESTION", 2.0), ("TIMER", 10.0), ("ANSWER", 6.0), ("RULE", 5.6), ("COST", 5.0),
        ("END", 3.2)]
o = Z.cli()
tl = Z.Timeline(SEGS)
N, FPS, t = tl.N, Z.FPS, tl.t

HEROES = [("hatch", (0.62, 0.05, 0.03), "carA", "QX LK 206", 0.3),
          ("estate", (0.03, 0.12, 0.42), "carB", "JX RS 41", 0.45),
          ("saloon", (0.62, 0.63, 0.65), "carC", "QZ SB 902", 0.5)]
S = RB.build(o["ASSETS"], "single", seed=6, heroes=HEROES)
env, traffic = S["env"], S["traffic"]
fnt = Z.font(HERE)
cA, cB, cC = (S["heroes"][k] for k in ("carA", "carB", "carC"))
A, B, C = Z.Actor(cA, tl), Z.Actor(cB, tl), Z.Actor(cC, tl)

PA = S["lane_path"]("S", "N")          # A: south entry, straight on to the north exit
PB = S["lane_path"]("W", "E")          # B: from the west, round the south side, out at the east
PC = S["lane_path"]("E", "W")          # C: east entry, round the north side, out at the west
sA = PA.stop_s(cA["L"], PA.s_yield, 0.5)
sC = PC.stop_s(cC["L"], PC.s_yield, 0.5)
xA = PA.at(sA)[0].x
yC = PC.at(sC)[0].y
sB_conf = PB.s_first(lambda p: p.y < 0 and p.x >= xA, start=PB.s_circle_in)      # B crosses A's entry
sA_confC = PA.s_first(lambda p: p.x > 0 and p.y >= yC, start=PA.s_circle_in)     # A crosses C's entry
indA = Z.ind_window(PA.s_indicate, PA.s_cross_out + 3.0)
indB = Z.ind_window(PB.s_indicate, PB.s_cross_out + 3.0)
indC = Z.ind_window(PC.s_indicate, PC.s_cross_out + 3.0)
hB = cB["L"] / 2

# ---------------------------------------------------------------- SETUP .. TIMER (one continuous moment)
nS, nQ, nT = tl.nf("SETUP"), tl.nf("QUESTION"), tl.nf("TIMER")
sB_freeze = sB_conf - hB - 5.0                 # B's front 5 m before A's entry when the clock stops
A.drive("SETUP", PA, jx.kinematics(sA - 11.6, 8.0, [(0, "cruise", 8.0), (0.3, "stop", sA)], nS), indA)
B.drive("SETUP", PB, Z.cruise(sB_freeze - 6.0 * nS / FPS, 6.0, nS), indB)
C.hold("SETUP", PC, sC)
A.hold("QUESTION", PA, sA)
C.hold("QUESTION", PC, sC)
B.drive("QUESTION", PB, Z.slow(sB_freeze, 0.6, nQ), indB, v_nom=6.0)
A.hold("TIMER", PA, sA)
C.hold("TIMER", PC, sC)
B.drive("TIMER", PB, Z.slow(sB_freeze + 0.6 * nQ / FPS, 0.12, nT), indB, v_nom=6.0)

# ---------------------------------------------------------------- ANSWER
nA = tl.nf("ANSWER")
sB_ans = sB_freeze + 0.6 * nQ / FPS + 0.12 * nT / FPS
svB_ans = jx.kinematics(sB_ans, 6.0, [(0, "cruise", 7.0)], nA)
B.drive("ANSWER", PB, svB_ans, indB)
svA_ans = jx.kinematics(sA, 0.0, [(0, "hold", None), (1.0, "cruise", 8.0)], nA, a_acc=3.5)
A.drive("ANSWER", PA, svA_ans, indA)
t_clear = Z.t_when(svA_ans, sA_confC + cA["L"] / 2 + 1.0)        # A's tail past C's entry
T_C_GO = max(4.2, t_clear - 0.4)
svC_ans = jx.kinematics(sC, 0.0, [(0, "hold", None), (T_C_GO, "cruise", 6.0)], nA, a_acc=2.5)
C.drive("ANSWER", PC, svC_ans, indC)

# ---------------------------------------------------------------- RULE
nR = tl.nf("RULE")
# A waits at the give-way line for the whole segment ('Cars in the circle go first.' needs a circulating car and a
# waiting one in the same frame, QA r3)
A.hold("RULE", PA, sA)
B.drive("RULE", PB, Z.cruise(sB_conf - hB - 6.5 * 2.3, 6.5, nR), indB)
C.hold("RULE", PC, sC)

# ---------------------------------------------------------------- COST: A pulls out in front of B
nCo = tl.nf("COST")
svA_cost = jx.kinematics(sA, 0.0, [(0, "hold", None), (0.4, "cruise", 4.0), (1.0, "stop", sA + 3.4)], nCo,
                         a_acc=3.0)
A.drive("COST", PA, svA_cost, indA)
C.hold("COST", PC, sC)
f0_cost = tl.f0("COST")
svB_cost = Z.solve_stop(PB, cB, sB_conf - hB - 6.5 * 1.45, 6.5, 6.5, nCo, f0_cost, [(A, cA["W"] + 0.04)],
                        target=0.3)
pB_cost = Z.dive(svB_cost)
B.drive("COST", PB, svB_cost, None, pitch=lambda k: pB_cost[k])
T_HORN = next((k / FPS for k in range(1, nCo) if svB_cost[k][1] < svB_cost[k - 1][1] - 1e-3), 0.8)

for X in (A, B, C):
    X.bake()

# ---------------------------------------------------------------- traffic, people, leaves
amb = [Z.Actor(Z.fleet_car(S, "estate_grey", "amb0"), tl), Z.Actor(Z.fleet_car(S, "suv_white", "amb1"), tl)]
amb[0].whole(Z.line_path(JN.arm_pt("W", 112, -1.625), JN.arm_pt("W", 240, -1.625)), Z.cruise(0.0, 8.5, N))
amb[1].whole(Z.line_path(JN.arm_pt("E", 116, -1.625), JN.arm_pt("E", 240, -1.625)), Z.cruise(0.0, 9.0, N))
for X in amb:
    X.bake()
FOOT = 3.25 + 0.16 + 1.25
Z.walkers(S, tl, [(Z.line_path(JN.arm_pt("S", 46, -FOOT), JN.arm_pt("S", 140, -FOOT)), 0.0, 1.25, 1),
                  (Z.line_path(JN.arm_pt("E", 47, FOOT), JN.arm_pt("E", 140, FOOT)), 0.0, 1.1, 2),
                  (Z.line_path(JN.arm_pt("N", 50, -FOOT), JN.arm_pt("N", 140, -FOOT)), 0.0, 1.35, 3),
                  (Z.line_path(JN.arm_pt("W", 48, FOOT + 0.5), JN.arm_pt("W", 140, FOOT + 0.5)), 0.0, 1.2, 4),
                  (Z.line_path(JN.arm_pt("W", 48.6, FOOT - 0.3), JN.arm_pt("W", 140, FOOT - 0.3)), 0.0, 1.2, 5)])
Z.cyclists(S, tl, [(Z.line_path(JN.arm_pt("N", 84, -2.5), JN.arm_pt("N", 240, -2.5)), 0.0, 4.6, 2)])
Z.leaves(S, [((0, -1), 3.25, 46, 160), ((1, 0), 3.25, 46, 160), ((0, 1), 3.25, 46, 160), ((-1, 0), 3.25, 46, 160)])

# ---------------------------------------------------------------- quiz layer
BC = jx.BADGE_COLOURS
Z.letter_badge("A", A, traffic, fnt, t("QUESTION", 0.2), t("ANSWER", 2.1))
Z.letter_badge("B", B, traffic, fnt, t("QUESTION", 0.3), t("ANSWER", 0.2))
Z.letter_badge("C", C, traffic, fnt, t("QUESTION", 0.5), t("ANSWER", 4.0))
T_LOW = 4.7                            # badges go before the low reveal (they would fill the frame)
Z.number_badge(1, B, traffic, fnt, t("ANSWER", 0.3), t("ANSWER", T_LOW - 0.2))
Z.number_badge(2, A, traffic, fnt, t("ANSWER", 2.2), t("ANSWER", T_LOW - 0.2))
Z.number_badge(3, C, traffic, fnt, t("ANSWER", 4.1), t("ANSWER", T_LOW - 0.2))
rA = (sA + cA["L"] / 2 + 0.6, PA.s_circle_out + 9.0)
rB = (sB_freeze + 0.6 * nQ / FPS + hB + 0.6, PB.s_circle_out + 9.0)
rC = (sC + cC["L"] / 2 + 0.6, PC.s_circle_out + 9.0)
jx.ribbon(PA, *rA, BC["A"], env, t("QUESTION", 0.4), t("ANSWER", 0.0), width=1.2, z=0.04, name="ribA")
jx.ribbon(PB, *rB, BC["B"], env, t("QUESTION", 0.45), t("ANSWER", 0.0), width=1.2, z=0.05, name="ribB")
jx.ribbon(PC, *rC, BC["C"], env, t("QUESTION", 0.5), t("ANSWER", 0.0), width=1.2, z=0.06, name="ribC")
jx.ribbon(PB, rB[0], rB[1], Z.GREEN, env, t("ANSWER", 0.2), t("ANSWER", 5.6), width=1.2, z=0.055, name="ribB_go")
jx.ribbon(PA, *rA, Z.GREEN, env, t("ANSWER", 2.1), t("ANSWER", 5.6), width=1.2, z=0.045, name="ribA_go")
jx.ribbon(PC, *rC, Z.GREEN, env, t("ANSWER", 4.0), t("ANSWER", 5.6), width=1.2, z=0.065, name="ribC_go")
# RULE: the circulating lane glows (arrow head = anticlockwise), the entry signs float over the island
T_RTOP = 2.75                          # cut to the top view with the second rule line
jx.ribbon(Z.circle_path(11.75, -95.0, 235.0), 0.0, 69.0, (1.0, 0.86, 0.36), env, t("RULE", T_RTOP + 0.05),
          t("RULE", 5.4), width=2.4, z=0.07, name="glow_ring")
Z.sign_icon("205", env, t("RULE", T_RTOP + 0.15), t("RULE", 5.4), width=3.8, loc=(0.0, 3.1, 4.5))
Z.sign_icon("215", env, t("RULE", T_RTOP + 0.3), t("RULE", 5.4), width=3.0, loc=(0.0, -2.9, 4.5))

# ---------------------------------------------------------------- cameras
UP = Z.UP
shots = jx.Shots(N)
TOP = Z.top(2.5, 0.0, 55.0, tilt=4.0)
shots.add("S_drone", 30, t("SETUP"), t("SETUP", 1.6),
          Z.orbit((0, -3, 0), 46.0, 33.0, -58.0, -80.0, t("SETUP"), t("SETUP", 1.6), tgt=(0.0, -5.0, 0.0)))
shots.add("Q_top", 30, t("SETUP", 1.6), t("TIMER", 10.0),
          Z.top(2.5, 0.0, 55.0, tilt=4.0, drift=(0, 0, -2.5), t0=t("SETUP", 1.6), t1=t("TIMER", 10.0)),
          up_fn=lambda tt: UP)
shots.add("A_top", 30, t("ANSWER"), t("ANSWER", T_LOW), TOP, up_fn=lambda tt: UP)
P_LOW = Vector((5.2, -4.6, 1.05))
shots.add("A_low", 24, t("ANSWER", T_LOW), t("ANSWER", 6.0),
          lambda tt: (P_LOW + Vector((0.5, -0.3, 0.0)) * jx.ease((tt - t("ANSWER", T_LOW)) / 1.3),
                      Vector((16.0, 3.8, 1.25))))


pA_wait = PA.at(sA)[0]
P_WAIT0 = Vector((pA_wait.x + 1.2, pA_wait.y - 14.5, 4.6))       # over A's lane, behind it, raised
P_WAIT1 = Vector((pA_wait.x + 1.0, pA_wait.y - 12.5, 4.3))
T_WAIT = Vector((-3.0, -7.0, 0.6))                               # the south-west quarter B comes round


def wait_view(tt):
    u = jx.ease((tt - t("RULE")) / T_RTOP)
    return P_WAIT0.lerp(P_WAIT1, u), T_WAIT


shots.add("R_wait", 26, t("RULE"), t("RULE", T_RTOP), wait_view)
shots.add("R_top", 30, t("RULE", T_RTOP), t("RULE", 5.6), TOP, up_fn=lambda tt: UP)
shots.add("C_top", 30, t("COST"), t("COST", 2.2), TOP, up_fn=lambda tt: UP)
shots.add("C_close", 30, t("COST", 2.2), t("COST", 5.0),
          Z.two_shot(B, A, tl.f("COST", 2.4), extra=4.0, t0=t("COST", 2.2), t1=t("COST", 5.0)))
Z.end_card(tl, "END", shots, [[("de-core", "205", 2.6)], [("de-core", "215", 2.2)]], env)
bpy.context.scene.camera = bpy.data.objects["S_drone"]

Z.sun(o["ASSETS"], 220.0, 13.0, 5.4)
stubs = [ob.name for ob in bpy.data.objects if ob.get("stub")]
if stubs:
    raise SystemExit("placeholder signs: " + ", ".join(stubs[:5]))
print("EP06 B horn at", round(T_HORN, 2), "C goes at", round(T_C_GO, 2), "frames", N, flush=True)
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
