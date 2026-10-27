"""Drive Like a Local #23, Germany: roundabouts, when do you indicate? 9:16, 30 fps, segments in canonical order
(post_ep23.py cuts them per language). Single-lane Kreisverkehr (kit/roundabout.py), low warm October sun.
  HOOK       top: the teal rental hatchback H enters with its LEFT indicator on; the silver saloon W waits at the
             north entry
  SITUATION  drone (H enters, left indicator), chase round the island (H leaves north with no signal), top on the
             north entry: W still waiting, a car queues behind it, question marks, a toot from behind
  RULE       raised view from behind H at the south entry (give-way line, signs, the circle, W waiting across it):
             H rolls in with no indicator (the crossed indicator badge is a flat caption overlay, post_ep23.py),
             then drone: H indicates right before its exit, a right arrow pulses there, W goes as soon as it sees it
  COST       H heads for its exit with no signal, W edges out unsure, both brake
  CORRECT    drone, then a low chase: no signal in, right indicator after the exit before its own, W enters at once
  END        road-grey card with Zeichen 205 and 215
Rules: StVO section 8 (1a) (no indicator when entering), section 9 (1) (indicate when leaving); BKatV row 29 (10 EUR).
Run: python ep23_roundabout_indicate.py OUTDIR --frames 1-1032 --res 540 --samples 8 --assets ASSETS
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

SEGS = [("HOOK", 2.2), ("SITUATION", 10.0), ("RULE", 7.5), ("COST", 4.5), ("CORRECT", 7.0), ("END", 3.2)]
o = Z.cli()
tl = Z.Timeline(SEGS)
N, FPS, t = tl.N, Z.FPS, tl.t

HEROES = [("hatch", (0.0, 0.36, 0.38), "carH", "QX MR 23", 0.35),
          ("saloon", (0.62, 0.63, 0.65), "carW", "JJ KL 714", 0.5),
          ("hatch", (0.55, 0.42, 0.1), "carQ", "QZ EN 58", 0.3)]
S = RB.build(o["ASSETS"], "single", seed=8, heroes=HEROES)
env, traffic = S["env"], S["traffic"]
fnt = Z.font(HERE)
cH, cW, cQ = (S["heroes"][k] for k in ("carH", "carW", "carQ"))
H, Wt, Q = Z.Actor(cH, tl), Z.Actor(cW, tl), Z.Actor(cQ, tl)

PH = S["lane_path"]("S", "N")          # the visitor: south entry, out at the north exit
PW = S["lane_path"]("N", "S")          # the waiting saloon at the north entry (the next entry after H's exit)
sH_line = PH.stop_s(cH["L"], PH.s_yield, 0.0)
sW = PW.stop_s(cW["L"], PW.s_yield, 0.5)
sQ = sW - cW["L"] / 2 - 1.8 - cQ["L"] / 2
indH_ok = Z.ind_window(PH.s_indicate, PH.s_cross_out + 3.0)
indW = Z.ind_window(PW.s_indicate, PW.s_cross_out + 3.0)


def wrong_left(t0, t1):
    return lambda s, tt: "L" if t0 <= tt <= t1 else None


# ---------------------------------------------------------------- HOOK: left indicator on the way in
nHk = tl.nf("HOOK")
H.drive("HOOK", PH, Z.cruise(sH_line - 5.5 * 0.4, 5.5, nHk), "L")
Wt.hold("HOOK", PW, sW)

# ---------------------------------------------------------------- SITUATION
nSi = tl.nf("SITUATION")
svH_si = Z.cruise(sH_line - 6.0 * 0.4, 6.0, nSi)
H.drive("SITUATION", PH, svH_si, wrong_left(0.2, 3.0))
T_H_OUT = Z.t_when(svH_si, PH.s_circle_out)
Wt.drive("SITUATION", PW, jx.kinematics(sW, 0.0, [(0, "hold", None), (8.5, "cruise", 2.0)], nSi, a_acc=1.6), indW)
Q.drive("SITUATION", PW, jx.kinematics(sQ - 39.0, 6.0, [(0, "cruise", 6.0), (5.5, "stop", sQ)], nSi))

# ---------------------------------------------------------------- RULE: no signal in, right signal out
nR = tl.nf("RULE")
# H starts 8 m before the give-way line and crosses it at about 1.1 s, under 'Entering: no indicator.' (1.3 s)
svH_rule = jx.kinematics(73.0, 5.0, [(0, "cruise", 5.0), (1.0, "cruise", 7.5)], nR)
H.drive("RULE", PH, svH_rule, indH_ok)
T_IND_RULE = Z.t_when(svH_rule, PH.s_indicate)
T_W_RULE = Z.t_when(svH_rule, PH.s_circle_out - 3.0)
Wt.drive("RULE", PW, jx.kinematics(sW, 0.0, [(0, "hold", None), (T_W_RULE, "cruise", 5.0)], nR, a_acc=2.5), indW)
Q.hold("RULE", PW, sQ)

# ---------------------------------------------------------------- COST: no signal, W edges out, both brake
nCo = tl.nf("COST")
svW_cost = jx.kinematics(sW, 0.0, [(0, "hold", None), (0.6, "cruise", 2.5), (1.0, "stop", sW + 1.6)], nCo,
                         a_acc=3.0)
Wt.drive("COST", PW, svW_cost, None)
svH_cost = Z.stop_profile(PH.s_indicate - 9.0, 6.0, PH.s_indicate + 1.5, 6.0, nCo)
pH_cost = Z.dive(svH_cost)
H.drive("COST", PH, svH_cost, None, pitch=lambda k: pH_cost[k])
Q.hold("COST", PW, sQ)

# ---------------------------------------------------------------- CORRECT
nCr = tl.nf("CORRECT")
svH_cor = Z.cruise(78.0, 7.0, nCr)
H.drive("CORRECT", PH, svH_cor, indH_ok)
T_IND_COR = Z.t_when(svH_cor, PH.s_indicate)
T_W_COR = max(T_IND_COR + 0.8, Z.t_when(svH_cor, PH.s_circle_out - 4.0))
Wt.drive("CORRECT", PW, jx.kinematics(sW, 0.0, [(0, "hold", None), (T_W_COR, "cruise", 5.5)], nCr, a_acc=2.6),
         indW)
Q.drive("CORRECT", PW, jx.kinematics(sQ, 0.0, [(0, "hold", None), (T_W_COR + 1.2, "cruise", 5.0)], nCr,
                                     a_acc=2.4))

for X in (H, Wt, Q):
    X.bake()

# ---------------------------------------------------------------- traffic, people, leaves
amb = [Z.Actor(Z.fleet_car(S, "estate_green", "amb0"), tl), Z.Actor(Z.fleet_car(S, "suv_dark", "amb1"), tl)]
amb[0].whole(Z.line_path(JN.arm_pt("E", 112, -1.625), JN.arm_pt("E", 240, -1.625)), Z.cruise(0.0, 8.5, N))
amb[1].whole(Z.line_path(JN.arm_pt("W", 118, -1.625), JN.arm_pt("W", 240, -1.625)), Z.cruise(0.0, 9.0, N))
for X in amb:
    X.bake()
FOOT = 3.25 + 0.16 + 1.25
Z.walkers(S, tl, [(Z.line_path(JN.arm_pt("S", 47, FOOT), JN.arm_pt("S", 140, FOOT)), 0.0, 1.2, 6),
                  (Z.line_path(JN.arm_pt("N", 46, FOOT), JN.arm_pt("N", 140, FOOT)), 0.0, 1.3, 7),
                  (Z.line_path(JN.arm_pt("E", 50, FOOT), JN.arm_pt("E", 140, FOOT)), 0.0, 1.15, 8),
                  (Z.line_path(JN.arm_pt("W", 46, -FOOT), JN.arm_pt("W", 140, -FOOT)), 0.0, 1.25, 9)])
Z.cyclists(S, tl, [(Z.line_path(JN.arm_pt("S", 84, -2.5), JN.arm_pt("S", 240, -2.5)), 0.0, 4.4, 3)])
Z.leaves(S, [((0, -1), 3.25, 46, 160), ((1, 0), 3.25, 46, 160), ((0, 1), 3.25, 46, 160), ((-1, 0), 3.25, 46, 160)])

# ---------------------------------------------------------------- overlays
Z.question(Wt, traffic, fnt, t("SITUATION", 7.2), t("SITUATION", 9.8))
p_exit = PH.at(PH.s_circle_out)[0]
Z.arrow_icon("out_r", traffic, t("RULE", T_IND_RULE), t("RULE", 7.3), side="R", loc=(p_exit.x + 2.5, p_exit.y + 2.0,
                                                                                     4.0), size=3.2)
jx.ribbon(PH, PH.s_indicate, PH.s_cross_out + 6.0, Z.AMBER, env, t("RULE", T_IND_RULE), t("RULE", 7.3), width=1.3,
          z=0.05, name="rib_exit")

# ---------------------------------------------------------------- cameras
UP = Z.UP
shots = jx.Shots(N)
shots.add("H_top", 30, t("HOOK"), t("HOOK", 2.2), Z.top(1.0, 5.0, 60.0, tilt=4.0), up_fn=lambda tt: UP)
shots.add("S_drone", 30, t("SITUATION"), t("SITUATION", 3.5),
          Z.orbit((0, -2, 0), 44.0, 34.0, -60.0, -82.0, t("SITUATION"), t("SITUATION", 3.5), tgt=(0.0, -3.0, 0.0)))
shots.add("S_chase", 26, t("SITUATION", 3.5), t("SITUATION", 7.0),
          lambda tt: Z.follow(H, int(round(tt * FPS)) + 1, back=7.0, up=2.3, side=-0.6, ahead=12.0, look_z=0.9))
shots.add("S_top", 30, t("SITUATION", 7.0), t("SITUATION", 10.0), Z.top(0.0, 14.0, 46.0, tilt=3.0),
          up_fn=lambda tt: UP)


# 'The rule:' opens on the entry itself (QA r3: the driver's eye showed an empty road): over H's lane, behind and
# above it, looking at the give-way line and the circle; H drives in and round the east side
pH0 = PH.at(73.0)[0]
P_ENT0 = Vector((pH0.x + 1.3, pH0.y - 9.5, 4.6))
P_ENT1 = Vector((pH0.x + 1.1, pH0.y - 7.0, 4.4))
T_ENT = Vector((3.5, -6.0, 0.8))


def entry_view(tt):
    u = jx.ease((tt - t("RULE")) / 3.5)
    return P_ENT0.lerp(P_ENT1, u), T_ENT


shots.add("R_entry", 24, t("RULE"), t("RULE", 3.5), entry_view)
shots.add("R_drone", 30, t("RULE", 3.5), t("RULE", 7.5),
          Z.orbit((0, 4, 0), 40.0, 36.0, -70.0, -58.0, t("RULE", 3.5), t("RULE", 7.5), tgt=(0.0, 6.0, 0.0)))
shots.add("C_top", 30, t("COST"), t("COST", 2.2), Z.top(0.0, 8.0, 48.0, tilt=3.0), up_fn=lambda tt: UP)
# raised three-quarter view from the east that holds both cars (they stop about 15 m apart)
fC = tl.f("COST", 2.4)
MID = (Vector((Wt.track[fC - 1]["x"], Wt.track[fC - 1]["y"], 0.0)) +
       Vector((H.track[fC - 1]["x"], H.track[fC - 1]["y"], 0.0))) / 2
shots.add("C_close", 26, t("COST", 2.2), t("COST", 4.5),
          Z.orbit((MID.x, MID.y, 0.0), 21.0, 11.0, 5.0, 18.0, t("COST", 2.2), t("COST", 4.5),
                  tgt=(MID.x, MID.y, 0.6)))
shots.add("K_drone", 30, t("CORRECT"), t("CORRECT", 3.0),
          Z.orbit((0, -2, 0), 42.0, 32.0, -100.0, -80.0, t("CORRECT"), t("CORRECT", 3.0), tgt=(0.0, 0.0, 0.0)))
shots.add("K_chase", 24, t("CORRECT", 3.0), t("CORRECT", 7.0),
          lambda tt: Z.follow(H, int(round(tt * FPS)) + 1, back=6.5, up=1.35, side=0.9, ahead=14.0, look_z=0.9))
Z.end_card(tl, "END", shots, [[("de-core", "205", 2.6)], [("de-core", "215", 2.2)]], env)
bpy.context.scene.camera = bpy.data.objects["H_top"]

Z.sun(o["ASSETS"], 215.0, 12.0, 5.4)
stubs = [ob.name for ob in bpy.data.objects if ob.get("stub")]
if stubs:
    raise SystemExit("placeholder signs: " + ", ".join(stubs[:5]))
print("EP23 H out of the circle at", round(T_H_OUT, 2), "rule indicator", round(T_IND_RULE, 2), "W goes",
      round(T_W_RULE, 2), "correct indicator", round(T_IND_COR, 2), "W", round(T_W_COR, 2), "frames", N, flush=True)
if "--probe" in sys.argv:
    Z.probe([int(v) for v in sys.argv[sys.argv.index("--probe") + 1].split(",")])
if o["DRY"]:
    print("DRY_OK", len(bpy.data.objects), "objects", flush=True)
    raise SystemExit(0)
Z.setup_render(o, tl)
no_blur = tl.cut_frames()
for X in [H, Wt, Q] + amb:
    no_blur |= X.jumps()
Z.render(shots, o["OUT"], Z.todo_frames(o, tl), no_blur)
print("RENDER_DONE", o["FR"])
