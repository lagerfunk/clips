"""Drive Like a Local #5, Germany: right on red only with the green arrow sign (Zeichen 720), and only after a full
stop. 9:16, 30 fps, 774 frames (25.8 s).
0 to 3.2 s   the signal: red light, the small green arrow plate beside it.
3.2 to 9.8   top view quiz: A (indicating right) arrives at red; C crosses on green from the left. Options 1, 2, 3.
             Answer 2: stop at the line, let C pass, then turn.
9.8 to 15.4  behind A: full stop at the line, C passes, A turns.
15.4 to 20.3 drone, under the fine cards: A rolls over the line without stopping and pulls out in front of the black
             car X, which brakes hard (fix15b). 20.3 to 22.8 own camera: the correct take, A stops, X passes, A turns.
22.8 to 25.8 end card.
Run: python ep05_gruenpfeil.py OUTDIR --frames 1-774 --res 720 --samples 16 --assets ASSETS [--stills 60,300]
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import jx  # noqa: E402
import stage  # noqa: E402
import townstage as TS  # noqa: E402

OUT, RES, SAMPLES, ASSETS, FR, STILLS = "frames", 720, 16, "assets", None, None
a = sys.argv
for i, x in enumerate(a):
    if i == 1 and not x.startswith("--"):
        OUT = x
    if x == "--res":
        RES = int(a[i + 1])
    if x == "--samples":
        SAMPLES = int(a[i + 1])
    if x == "--assets":
        ASSETS = a[i + 1]
    if x == "--frames":
        p, q = a[i + 1].split("-")
        FR = (int(p), int(q))
    if x == "--stills":
        STILLS = [int(v) for v in a[i + 1].split(",")]

FPS = jx.FPS
T_END = 25.8
N = int(round(T_END * FPS))
FONT_DIR = next((d for d in (os.path.join(HERE, "fonts"), os.path.join(HERE, "..", "fonts"),
                             "/home/claude/sf2/fonts") if os.path.isdir(d)), None)

# fix15c (QA r4 #2): A was always one object, the kit "hatch" (same kind, colour, plate and seed in every take). From
# behind (quiz, RULE chase, drone approach) it reads as an SUV; the new front and side views of fix15b (drone after the
# turn, correct take) showed its compact-hatchback front. A is now the kit "suv" in every re-rendered take (RULE and
# COST, frames 295-684), so it reads as the same red SUV from every side. STOP_A keeps the hatch length (4.28 m), so
# every take moves exactly as before; the approved quiz top view (frames 1-294, 33 m up) is not re-rendered.
A_KIND = "suv"
S = TS.build(ASSETS, "signal", seed=9, heroes=[
    (A_KIND, (0.55, 0.035, 0.025), "carA", "WI LK 204", 0.3), ("suv", (0.82, 0.83, 0.84), "carC", "F SB 902", 0.1),
    ("saloon", (0.015, 0.016, 0.018), "carX", "DA KE 9", 0.45)])
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, N
lib, traffic = S["lib"], S["traffic"]
font = bpy.data.fonts.load(os.path.join(FONT_DIR, "Montserrat-Black.ttf"), check_existing=True)
A, C, X = S["heroes"]["carA"], S["heroes"]["carC"], S["heroes"]["carX"]
sig = S["furniture"]["signals"]
sig["NS"].key(1, "red")
sig["EW"].key(1, "green")
for g in sig.values():
    g.constant()

PA = jx.lane_path("S", "right")
PC = jx.lane_path("W", "straight")
STOP_LINE_Y = 3.0 + 7.0                       # townstage: stop line R + 1 m behind the kerb line of the cross street
STOP_A = 95.0 - (STOP_LINE_Y + 0.3 + 4.28 / 2)  # fix15c: the approved hatch length, so the kinematics are unchanged

seg1 = int(round(9.8 * FPS))
a1 = jx.kinematics(STOP_A - 11.6 - 8.3 * 3.4, 8.3, [(0, "cruise", 8.3), (3.4, "stop", STOP_A), (9.2, "cruise", 5.0)],
                   seg1, a_acc=1.8)
c1 = jx.kinematics(95.0 - 1.5 - 8.3 * 8.05, 8.3, [(0, "cruise", 8.3)], seg1)
seg2 = int(round(5.6 * FPS))
a2 = jx.kinematics(STOP_A - 6.5, 4.5, [(0, "cruise", 4.5), (0.2, "stop", STOP_A), (4.8, "cruise", 5.0)], seg2, a_acc=1.8)
c2 = jx.kinematics(95.0 - 1.5 - 8.3 * 4.0, 8.3, [(0, "cruise", 8.3)], seg2)
seg3 = N - seg1 - seg2
# fix15b (QA r2 #1): the cost shot shows the mistake the fine cards name. 15.4 to 20.3 (drone): A rolls over the line
# at about 2 m/s without stopping (front over the line at 16.8, under "No full stop: 70"), turns and pulls out in front
# of the black car X, which has green and comes from the left on the lane A turns into; X brakes hard and stops about
# 4 m behind A (18.45 to 19.5, under "Endangering traffic: 100"). 20.3 to 22.8 (own camera, so no jump inside one
# shot): the correct take for "Stop, look, then turn.": A stands at the line, X passes, A turns. END continues it.
seg3w = int(round((20.3 - 15.4) * FPS))
seg3r = seg3 - seg3w
a3 = (jx.kinematics(STOP_A - 3.0, 2.8, [(0, "cruise", 1.9), (0.9, "cruise", 5.5)], seg3w, a_acc=2.2, a_brake=1.2) +
      jx.kinematics(STOP_A, 0.0, [(0, "hold", None), (0.45, "cruise", 5.0)], seg3r, a_acc=3.2))
c3 = [(-500.0, 0.0)] * seg3
frames = list(range(1, N + 1))
SV_A, SV_C = a1 + a2 + a3, c1 + c2 + c3
jx.drive(A, PA, SV_A, frames)
jx.drive(C, PC, SV_C, frames)
jx.brake_lights(A, SV_A)
jx.brake_lights(C, SV_C)
x_sv = ([(-500.0, 0.0)] * (seg1 + seg2) +
        jx.kinematics(62.0, 8.3, [(0, "cruise", 8.3), (3.05, "cruise", 0.0), (4.15, "cruise", 3.0)], seg3w,
                      a_acc=1.5, a_brake=7.0) +
        jx.kinematics(94.0, 8.3, [(0, "cruise", 8.3)], seg3r))
jx.drive(X, PC, x_sv, frames)
jx.brake_lights(X, x_sv)
# indicator right: A signals from its approach until the turn is done, in every segment
jx.blink(A, "R", 3.4, 25.0)


def amber_indicators(gain=0.3, colour=(1.0, 0.3, 0.0)):
    """fix15b (QA r2 #4): the indicator lenses lit at strength 12 in (1, 0.45, 0) and AgX rendered them pale
    pink-white. Here (this episode only) the lit emission is a deeper amber at 0.3 of the strength, so it stays amber."""
    for m in bpy.data.materials:
        if not m.name.startswith("dl_ind_") or not m.use_nodes:
            continue
        for nd in m.node_tree.nodes:
            if nd.type == "EMISSION":
                nd.inputs["Color"].default_value = (*colour, 1.0)
            if nd.type == "MATH" and nd.operation == "MULTIPLY" and not nd.inputs[1].is_linked:
                nd.inputs[1].default_value = gain


def clean_jump(objs, f_cut):
    """A car that jumps between two takes (frame f_cut - 1 to f_cut) would be smeared across the junction by the
    motion blur (linear keys, shutter 0.5). Hold the old pose up to f_cut - 0.5 and the new pose from there."""
    import motion
    for o in objs:
        loc = [fc for fc in motion._fcurves(o) if fc.data_path == "location"]
        if not loc or sum((fc.evaluate(f_cut) - fc.evaluate(f_cut - 1)) ** 2 for fc in loc) < 1.0:
            continue                       # no jump at this cut (a moving car covers at most 0.3 m a frame)
        for fc in motion._fcurves(o):
            if not fc.data_path.startswith(("location", "rotation")):
                continue
            new = fc.evaluate(f_cut)
            for kp in fc.keyframe_points:
                if abs(kp.co[0] - (f_cut - 1)) < 1e-3:
                    kp.interpolation = "CONSTANT"
            k = fc.keyframe_points.insert(f_cut - 0.5, new, options={"FAST"})
            k.interpolation = "LINEAR"
            fc.update()


amber_indicators()
for fcut in (seg1 + 1, seg1 + seg2 + 1, seg1 + seg2 + seg3w + 1):
    clean_jump([car["rig"].obj for car in (A, C, X)], fcut)

bA = jx.badge("A", A, traffic, font, 3.3, 9.6)
bC = jx.badge("C", C, traffic, font, 3.5, 9.6)
jx.ribbon(PA, STOP_A + A["L"] / 2 + 0.6, STOP_A + 24.0, jx.BADGE_COLOURS["A"], S["env"], 4.0, 9.6, name="ribA")
jx.ribbon(PC, 95.0 - 12.0, 95.0 + 10.0, jx.BADGE_COLOURS["C"], S["env"], 4.3, 8.8, name="ribC")

# red light and green arrow plate as a flat icon beside A's signal for the top view
jx.signal_callout(S["T"], lib, S["env"], "call_sig", (7.0, -11.0), 3.3, 9.6, scale=3.1)

shots = jx.Shots(N)
UP = Vector((0, 1, 0))
SIG = Vector((3.0 + 0.71, -(3.0 + 7.0 - 0.6), 0.15 + 2.9 + 0.45))
shots.add("S_sign", 38, 0.0, 3.2, lambda t: (Vector((1.3 + 0.05 * t, -17.5 + 0.5 * t, 1.55)),
                                             SIG + Vector((0.25, 0.0, -0.1))))
shots.add("Q_top", 30, 3.2, 9.8, lambda t: (Vector((2.0, -8.5 + 0.2 * (t - 3.2), 33.0 - 0.3 * (t - 3.2))),
                                            Vector((2.0, -1.8, 0.0))), up_fn=lambda t: UP)


def chase(t):
    # fix15c: Shots keys a camera 2 frames beyond its shot; A jumps between takes at frames 295 and 463, so the chase
    # camera jumped with it and the motion blur smeared A in the first and last RULE frames. Clamp to the RULE take.
    i = max(seg1, min(seg1 + seg2 - 1, int(t * FPS)))
    x, y, _ = A["track"][i]
    return Vector((x - 1.2, y - 7.0, 2.4)), Vector((x + 1.5, y + 14.0, 1.6))


shots.add("R_chase", 26, 9.8, 15.4, chase)


def drone(t):
    u = (t - 15.4) / 7.4
    return Vector((-4.0 + 10.0 * u, -33.0 + 4.0 * u, 22.0)), Vector((2.5, -1.5, 0.5))


shots.add("F_drone", 26, 15.4, 20.3, drone)
# fix15b: the correct take gets its own camera, across the junction from A (north-west corner, 4 m up), so the cut
# from the drone is a cut between two shots; X crosses between the camera and A, then A turns.
shots.add("M_turn", 35, 20.3, 22.8, lambda t: (Vector((-7.0 + 0.4 * (t - 20.3), 4.0, 4.0)),
                                              Vector((2.0, -11.0, 0.8))))
shots.add("E_sign", 34, 22.8, T_END, lambda t: (Vector((1.6, -16.5 - 0.3 * (t - 22.8), 1.7)),
                                               SIG + Vector((0.2, 0.0, -0.2))))
sc.camera = bpy.data.objects["S_sign"]

TS.light(assets=ASSETS)
stage.hazify_all(dist=900.0, skip=("ribA", "ribC") + tuple(m.name for g in sig.values() for m in g.mats.values()))
stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
todo = STILLS or list(range(FR[0], FR[1] + 1) if FR else range(1, N + 1))
jx.render_frames(shots, OUT, todo)
print("RENDER_DONE", FR)
