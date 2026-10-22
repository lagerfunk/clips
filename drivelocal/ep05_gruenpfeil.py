"""Drive Like a Local #5, Germany: right on red only with the green arrow sign (Zeichen 720), and only after a full
stop. 9:16, 30 fps, 774 frames (25.8 s).
0 to 3.2 s   the signal: red light, the small green arrow plate beside it.
3.2 to 9.8   top view quiz: A (indicating right) arrives at red; C crosses on green from the left. Options 1, 2, 3.
             Answer 2: stop at the line, let C pass, then turn.
9.8 to 15.4  behind A: full stop at the line, C passes, A turns.
15.4 to 22.8 fines, then "no sign, no turn on red". 22.8 to 25.8 end card.
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

S = TS.build(ASSETS, "signal", seed=9, heroes=[
    ("hatch", (0.55, 0.035, 0.025), "carA", "WI LK 204", 0.3), ("suv", (0.82, 0.83, 0.84), "carC", "F SB 902", 0.1),
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
STOP_A = 95.0 - (STOP_LINE_Y + 0.3 + A["L"] / 2)

seg1 = int(round(9.8 * FPS))
a1 = jx.kinematics(STOP_A - 11.6 - 8.3 * 3.4, 8.3, [(0, "cruise", 8.3), (3.4, "stop", STOP_A), (9.2, "cruise", 5.0)],
                   seg1, a_acc=1.8)
c1 = jx.kinematics(95.0 - 1.5 - 8.3 * 8.05, 8.3, [(0, "cruise", 8.3)], seg1)
seg2 = int(round(5.6 * FPS))
a2 = jx.kinematics(STOP_A - 9.5, 5.5, [(0, "cruise", 5.5), (0.2, "stop", STOP_A), (4.8, "cruise", 5.0)], seg2, a_acc=1.8)
c2 = jx.kinematics(95.0 - 1.5 - 8.3 * 4.0, 8.3, [(0, "cruise", 8.3)], seg2)
seg3 = N - seg1 - seg2
a3 = jx.kinematics(STOP_A, 0.0, [(0, "hold", None), (2.0, "cruise", 5.0)], seg3, a_acc=1.8)
c3 = [(-500.0, 0.0)] * seg3
frames = list(range(1, N + 1))
SV_A, SV_C = a1 + a2 + a3, c1 + c2 + c3
jx.drive(A, PA, SV_A, frames)
jx.drive(C, PC, SV_C, frames)
jx.brake_lights(A, SV_A)
jx.brake_lights(C, SV_C)
PX = jx.lane_path("E", "straight")
x_sv = [(-500.0, 0.0)] * (seg1 + seg2) + jx.kinematics(50.0, 8.3, [(0, "cruise", 8.3)], seg3)
jx.drive(X, PX, x_sv, frames)
# indicator right: A signals from its approach until the turn is done, in every segment
jx.blink(A, "R", 3.4, 25.0)

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
    i = min(len(A["track"]) - 1, int(t * FPS))
    x, y, _ = A["track"][i]
    return Vector((x - 1.2, y - 7.0, 2.4)), Vector((x + 1.5, y + 14.0, 1.6))


shots.add("R_chase", 26, 9.8, 15.4, chase)


def drone(t):
    u = (t - 15.4) / 7.4
    return Vector((-4.0 + 10.0 * u, -33.0 + 4.0 * u, 22.0)), Vector((2.5, -1.5, 0.5))


shots.add("F_drone", 26, 15.4, 22.8, drone)
shots.add("E_sign", 34, 22.8, T_END, lambda t: (Vector((1.6, -16.5 - 0.3 * (t - 22.8), 1.7)),
                                               SIG + Vector((0.2, 0.0, -0.2))))
sc.camera = bpy.data.objects["S_sign"]

TS.light(assets=ASSETS)
stage.hazify_all(dist=900.0, skip=("ribA", "ribC") + tuple(m.name for g in sig.values() for m in g.mats.values()))
stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
todo = STILLS or list(range(FR[0], FR[1] + 1) if FR else range(1, N + 1))
jx.render_frames(shots, OUT, todo)
print("RENDER_DONE", FR)
