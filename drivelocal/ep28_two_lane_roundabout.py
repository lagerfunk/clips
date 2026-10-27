"""Drive Like a Local #28, Germany: two-lane roundabout, which lane? 9:16, 30 fps, segments in canonical order
(post_ep28.py cuts them per language). Two-lane Kreisverkehr (kit/roundabout.py, D 50 m, circulating lanes not
marked as the Merkblatt has it), low warm October sun.
  HOOK       top then close: the teal hatchback H leaves from the inner lane straight across the outer lane; the
             silver saloon W in the outer lane brakes a hand's width from H's door (solved, not guessed)
  SITUATION  drone (H takes the inner lane for the third exit), chase (W follows in the outer lane), top: H cuts
             across without looking or indicating, W and the van behind it brake
  RULE       drone: two cars at the two-lane entry, the outer lane glows for the first exits, the inner lane for the
             later ones; top: H on the inner lane, the outer lane beside it lights up (look), then its indicator
  COST       close replay: H cuts across, both stop a hand apart; top with the card
  CORRECT    drone, then a low chase: H slows, lets W pass in the outer lane, indicates right, moves out behind it
  END        road-grey card with Zeichen 205 and 215
H uses the inner lane only for the third exit; W (from the east to the west, the next-but-one exit) uses the outer
lane (facts: roundabout_two_lane_rule). The inner-lane car gives way to the outer lane when it leaves.
Run: python ep28_two_lane_roundabout.py OUTDIR --frames 1-1041 --res 540 --samples 8 --assets ASSETS
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit"), os.path.join(HERE, "..", "ep06")]

import bpy  # noqa: E402

import ep06_zshared as Z  # noqa: E402
import junctions as JN  # noqa: E402
import jx  # noqa: E402
import roundabout as RB  # noqa: E402

SEGS = [("HOOK", 2.2), ("SITUATION", 9.8), ("RULE", 7.5), ("COST", 4.5), ("CORRECT", 7.5), ("END", 3.2)]
o = Z.cli()
tl = Z.Timeline(SEGS)
N, FPS, t = tl.N, Z.FPS, tl.t

HEROES = [("hatch", (0.0, 0.36, 0.38), "carH", "QX MR 28", 0.35),
          ("saloon", (0.62, 0.63, 0.65), "carW", "JJ KL 288", 0.5),
          ("van", (0.86, 0.87, 0.88), "carV", "QZ TR 330", 0.0)]
S = RB.build(o["ASSETS"], "two_lane", seed=9, heroes=HEROES)
env, traffic = S["env"], S["traffic"]
fnt = Z.font(HERE)
cH, cW, cV = (S["heroes"][k] for k in ("carH", "carW", "carV"))
H, Wt, V = Z.Actor(cH, tl), Z.Actor(cW, tl), Z.Actor(cV, tl)
G = RB.Geo("two_lane")
R_IN, R_OUT = G.tracks[1], G.tracks[0]

PHx = S["lane_path"]("S", "W", 1, exit_from="inner")    # the mistake: straight out of the inner lane
PHo = S["lane_path"]("S", "W", 1)                       # the right way: moves to the outer lane before the exit
PW = S["lane_path"]("E", "W", 0)                        # W: east to west, outer lane (next-but-one exit)
indW = Z.ind_window(PW.s_indicate, PW.s_cross_out + 3.0)


def ang(P, s):
    p = P.at(s)[0]
    return math.degrees(math.atan2(p.y, p.x))


def s_at_angle(P, a_deg, s_from):
    """First arc length after s_from where the path reaches polar angle a_deg (anticlockwise, unwrapped)."""
    s, a_prev = s_from, ang(P, s_from)
    acc = a_prev
    while s < P.length:
        s += 0.1
        a = ang(P, s)
        acc += (a - a_prev + 180.0) % 360.0 - 180.0
        a_prev = a
        if acc >= a_deg:
            return s
    return P.length


def unwrap_from(P, s_ref, s):
    """Polar angle at s, unwrapped relative to the angle at s_ref."""
    a0 = ang(P, s_ref)
    return a0 + (ang(P, s) - a0 + 180.0) % 360.0 - 180.0


s_hx = PHx.s_first(lambda p: p.length > (R_IN + R_OUT) / 2 + 0.6, start=PHx.s_circle_in + 40.0)
s_drift = PHo.s_first(lambda p: p.length > R_IN + 0.15, start=PHo.s_circle_in + 40.0)
X_PT = PHx.at(s_hx + 1.0)[0]
s_wx = min((PW.s_circle_in + 0.2 * k for k in range(int((PW.s_circle_out - PW.s_circle_in) / 0.2))),
           key=lambda s: (PW.at(s)[0] - X_PT).length)
hW = cW["L"] / 2


def climax(seg, t0, t1, t_cross, h_stops=False):
    """H crosses the outer lane at t_cross (segment time); W, cruising in the outer lane, brakes to stop as late as
    possible with 0.3 m to spare; the van behind W brakes too."""
    n = int(round((t1 - t0) * FPS)) + 1
    s0 = s_hx - 7.0 * (t_cross - t0)
    plan = [(0, "cruise", 7.0)] + ([(t_cross - t0 + 0.55, "stop", s_hx + 6.5)] if h_stops else [])
    svH = jx.kinematics(s0, 7.0, plan, n, a_brake=6.0)
    pH = Z.dive(svH)
    H.drive(seg, PHx, svH, None, t0=t0, pitch=lambda k: pH[k])
    f0 = tl.f(seg, t0)
    sW0 = s_wx - hW - 6.5 * (t_cross + 0.3 - t0)
    svW = Z.solve_stop(PW, cW, sW0, 6.5, 7.0, n, f0, [(H, cH["W"] + 0.04)], target=0.3)
    pW = Z.dive(svW)
    Wt.drive(seg, PW, svW, indW, t0=t0, pitch=lambda k: pW[k])
    svV = Z.solve_stop(PW, cV, sW0 - hW - 9.0 - cV["L"] / 2, 6.5, 5.5, n, f0, [(Wt, cW["W"] + 0.04)], target=1.6)
    V.drive(seg, PW, svV, None, t0=t0)
    return svH, svW


# ---------------------------------------------------------------- HOOK: the climax first
climax("HOOK", 0.0, 2.2, 0.9)

# ---------------------------------------------------------------- SITUATION (three shots, time elided at the cuts)
n1 = int(round(3.5 * FPS))
H.drive("SITUATION", PHx, Z.cruise(PHx.s_yield - cH["L"] / 2 - 7.0 * 0.6, 7.0, n1), None)
sW_wait = PW.stop_s(cW["L"], PW.s_yield, 0.5)
Wt.drive("SITUATION", PW, [(sW_wait, 0.0)] * n1, None)
V.drive("SITUATION", PW, [(sW_wait - hW - 1.8 - cV["L"] / 2, 0.0)] * n1, None)
n2 = int(round(3.5 * FPS))
sH2 = PHx.s_circle_in + 40.0
svH2 = Z.cruise(sH2, 6.0, n2)
H.drive("SITUATION", PHx, svH2, None, t0=3.5)
aH2 = unwrap_from(PHx, PHx.s_circle_in + 30.0, sH2)
sW2 = s_at_angle(PW, aH2 - 22.0 if aH2 - 22.0 > ang(PW, PW.s_circle_in) else ang(PW, PW.s_circle_in) + 1.0,
                 PW.s_circle_in)
Wt.drive("SITUATION", PW, Z.cruise(sW2, 9.0, n2), indW, t0=3.5)
V.drive("SITUATION", PW, Z.cruise(sW2 - hW - 10.0 - cV["L"] / 2, 9.0, n2), None, t0=3.5)
climax("SITUATION", 7.0, 9.8, 7.7)

# ---------------------------------------------------------------- RULE
nR1 = int(round(3.5 * FPS))
PH_wait = S["lane_path"]("S", "W", 1)
PW_first = S["lane_path"]("S", "E", 0)
H.drive("RULE", PH_wait, [(PH_wait.stop_s(cH["L"], PH_wait.s_yield, 0.5), 0.0)] * nR1, None)
Wt.drive("RULE", PW_first, [(PW_first.stop_s(cW["L"], PW_first.s_yield, 0.5), 0.0)] * nR1, None)
nR2 = tl.nf("RULE") - nR1
s_ind_ok = s_drift - 5.0
sH_r2 = s_ind_ok - 6.0 * 2.2
svH_r2 = Z.cruise(sH_r2, 6.0, nR2)
H.drive("RULE", PHo, svH_r2, Z.ind_window(s_ind_ok, PHo.s_cross_out + 3.0), t0=3.5)

# ---------------------------------------------------------------- COST: the replay, both stop
climax("COST", 0.0, 4.5, 0.8, h_stops=True)

# ---------------------------------------------------------------- CORRECT: H lets W pass, then moves out behind it
nC = tl.nf("CORRECT")
planH = [(0, "cruise", 6.5), (1.6, "cruise", 4.0), (5.4, "cruise", 6.0)]
probe = jx.kinematics(0.0, 6.5, planH, nC, a_acc=2.0, a_brake=2.5)
T_DRIFT = 5.7
sH_c0 = s_drift - Z.s_at_time(probe, T_DRIFT)
svH_c = [(sH_c0 + s, v) for s, v in probe]
H.drive("CORRECT", PHo, svH_c, Z.ind_window(s_drift - 4.0, PHo.s_cross_out + 3.0))
T_IND_COR = Z.t_when(svH_c, s_drift - 4.0)
aH_c0 = unwrap_from(PHo, PHo.s_circle_in + 30.0, sH_c0)
sW_c0 = s_at_angle(PW, aH_c0 - 14.0, PW.s_circle_in)
svW_c = Z.cruise(sW_c0, 8.0, nC)
Wt.drive("CORRECT", PW, svW_c, indW)
V.drive("CORRECT", PW, Z.cruise(sW_c0 - hW - 42.0 - cV["L"] / 2, 8.0, nC), None)   # far enough back to pass later
gap_c = Z.min_gap(PHo, cH["L"], cH["W"] + 0.04, svH_c, tl.f0("CORRECT"), [(Wt, cW["W"] + 0.04), (V, cV["W"] + 0.04)])

for X in (H, Wt, V):
    X.bake()

# ---------------------------------------------------------------- traffic, people, leaves
amb = [Z.Actor(Z.fleet_car(S, "hatch_red", "amb0"), tl), Z.Actor(Z.fleet_car(S, "estate_blue", "amb1"), tl)]
amb[0].whole(Z.line_path(JN.arm_pt("N", 108, -1.625), JN.arm_pt("N", 240, -1.625)), Z.cruise(0.0, 8.5, N))
amb[1].whole(Z.line_path(JN.arm_pt("S", 112, -1.625), JN.arm_pt("S", 240, -1.625)), Z.cruise(0.0, 9.0, N))
for X in amb:
    X.bake()
FOOT = 3.25 + 0.16 + 1.25
Z.walkers(S, tl, [(Z.line_path(JN.arm_pt("S", 72, FOOT), JN.arm_pt("S", 160, FOOT)), 0.0, 1.2, 10),
                  (Z.line_path(JN.arm_pt("W", 73, FOOT), JN.arm_pt("W", 160, FOOT)), 0.0, 1.3, 11),
                  (Z.line_path(JN.arm_pt("E", 74, -FOOT), JN.arm_pt("E", 160, -FOOT)), 0.0, 1.15, 12),
                  (Z.line_path(JN.arm_pt("N", 72, FOOT), JN.arm_pt("N", 160, FOOT)), 0.0, 1.25, 13)])
Z.cyclists(S, tl, [(Z.line_path(JN.arm_pt("W", 134, -2.5), JN.arm_pt("W", 240, -2.5)), 0.0, 4.4, 4)])
Z.leaves(S, [((0, -1), 3.25, 72, 180), ((1, 0), 3.25, 72, 180), ((0, 1), 3.25, 72, 180), ((-1, 0), 3.25, 72, 180)])

# ---------------------------------------------------------------- overlays (RULE)
for k, ex in enumerate(("E", "N")):
    P_ = S["lane_path"]("S", ex, 0)
    jx.ribbon(P_, P_.s_yield + 1.0, P_.s_circle_out + 8.0, (1.0, 0.75, 0.0), env, t("RULE", 0.3 + 0.2 * k),
              t("RULE", 3.4), width=1.6, z=0.04 + 0.01 * k, name=f"rib_outer{k}")
jx.ribbon(PH_wait, PH_wait.s_yield + 1.0, PH_wait.s_circle_out + 8.0, (0.0, 0.75, 1.0), env, t("RULE", 1.8),
          t("RULE", 3.4), width=1.6, z=0.06, name="rib_inner")
fR = tl.f("RULE", 4.6)
a_look = math.degrees(math.atan2(H.track[fR - 1]["y"], H.track[fR - 1]["x"]))
jx.ribbon(Z.circle_path(R_OUT, a_look - 4.0, a_look + 46.0), 0.0, 999.0, (1.0, 0.86, 0.36), env, t("RULE", 4.6),
          t("RULE", 6.3), width=2.6, z=0.075, name="glow_look")
Z.arrow_icon("out_r", traffic, t("RULE", 5.7), t("RULE", 7.3), side="R", actor=H, dz=3.0, size=2.4)
Z.arrow_icon("cor_r", traffic, t("CORRECT", T_IND_COR), t("CORRECT", 7.3), side="R", actor=H, dz=2.5, size=1.15)

# ---------------------------------------------------------------- cameras
UP = Z.UP
shots = jx.Shots(N)
TOPW = Z.top(-18.0, 3.0, 42.0, tilt=3.0)
shots.add("H_top", 30, t("HOOK"), t("HOOK", 1.3), TOPW, up_fn=lambda tt: UP)
shots.add("H_close", 30, t("HOOK", 1.3), t("HOOK", 2.2),
          Z.two_shot(Wt, H, tl.f("HOOK", 1.6), extra=5.0, t0=t("HOOK", 1.3), t1=t("HOOK", 2.2)))
shots.add("S_drone", 30, t("SITUATION"), t("SITUATION", 3.5),
          Z.orbit((0, -6, 0), 62.0, 44.0, -62.0, -84.0, t("SITUATION"), t("SITUATION", 3.5), tgt=(0.0, -4.0, 0.0)))
shots.add("S_chase", 26, t("SITUATION", 3.5), t("SITUATION", 7.0),
          lambda tt: Z.follow(H, int(round(tt * FPS)) + 1, back=7.5, up=2.6, side=-1.4, ahead=12.0, look_z=0.9))
shots.add("S_top", 30, t("SITUATION", 7.0), t("SITUATION", 9.8), TOPW, up_fn=lambda tt: UP)
shots.add("R_drone", 30, t("RULE"), t("RULE", 3.5),
          Z.orbit((0, -10, 0), 58.0, 46.0, -75.0, -95.0, t("RULE"), t("RULE", 3.5), tgt=(0.0, -2.0, 0.0)))
shots.add("R_top", 30, t("RULE", 3.5), t("RULE", 7.5), Z.top(-8.0, 10.0, 58.0, tilt=3.0), up_fn=lambda tt: UP)
shots.add("C_close", 30, t("COST"), t("COST", 2.2),
          Z.two_shot(Wt, H, tl.f("COST", 1.3), extra=5.0, t0=t("COST"), t1=t("COST", 2.2)))
shots.add("C_top", 30, t("COST", 2.2), t("COST", 4.5), TOPW, up_fn=lambda tt: UP)
shots.add("K_drone", 30, t("CORRECT"), t("CORRECT", 3.0),
          Z.orbit((0, 2, 0), 58.0, 44.0, 20.0, 40.0, t("CORRECT"), t("CORRECT", 3.0), tgt=(-4.0, 8.0, 0.0)))
shots.add("K_chase", 24, t("CORRECT", 3.0), t("CORRECT", 7.5),
          lambda tt: Z.follow(H, int(round(tt * FPS)) + 1, back=6.8, up=1.4, side=-1.0, ahead=14.0, look_z=0.9))
Z.end_card(tl, "END", shots, [[("de-core", "205", 2.6)], [("de-core", "215", 2.2)]], env)
bpy.context.scene.camera = bpy.data.objects["H_top"]

Z.sun(o["ASSETS"], 212.0, 12.0, 5.4)
stubs = [ob.name for ob in bpy.data.objects if ob.get("stub")]
if stubs:
    raise SystemExit("placeholder signs: " + ", ".join(stubs[:5]))
print("EP28 crossing s", round(s_hx, 1), "drift s", round(s_drift, 1), "correct indicator", round(T_IND_COR, 2),
      "correct min gap H-W", round(gap_c, 2), "frames", N, flush=True)
if "--probe" in sys.argv:
    Z.probe([int(v) for v in sys.argv[sys.argv.index("--probe") + 1].split(",")])
if o["DRY"]:
    print("DRY_OK", len(bpy.data.objects), "objects", flush=True)
    raise SystemExit(0)
Z.setup_render(o, tl)
no_blur = tl.cut_frames() | {tl.f("SITUATION", 3.5) - 1, tl.f("SITUATION", 3.5), tl.f("SITUATION", 7.0) - 1,
                             tl.f("SITUATION", 7.0), tl.f("RULE", 3.5) - 1, tl.f("RULE", 3.5)}
for X in [H, Wt, V] + amb:
    no_blur |= X.jumps()
Z.render(shots, o["OUT"], Z.todo_frames(o, tl), no_blur)
print("RENDER_DONE", o["FR"])
