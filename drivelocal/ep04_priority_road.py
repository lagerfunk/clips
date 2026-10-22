"""Drive Like a Local #4, Germany: same junction as #2, now with signs. 9:16, 30 fps, 735 frames (24.5 s).
A drives north on the priority road (Zeichen 306); B comes from the east (A's right) and has Zeichen 205 and shark
teeth (Zeichen 342). The signs beat rechts vor links: A goes first.
0 to 9.8 s   top view quiz, reveal: A first, then B.  9.8 to 15.4 behind A at driving height: A passes the yellow
diamond and drives through while B waits at the shark teeth.  15.4 to 21.5 drone and fines.  21.5 to 24.5 end card.
Run: python ep04_priority_road.py OUTDIR --frames 1-735 --res 720 --samples 16 --assets ASSETS [--stills 60,300]
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
T_END = 24.5
N = int(round(T_END * FPS))
FONT_DIR = next((d for d in (os.path.join(HERE, "fonts"), os.path.join(HERE, "..", "fonts"),
                             "/home/claude/sf2/fonts") if os.path.isdir(d)), None)

S = TS.build(ASSETS, "priority", seed=4, heroes=[
    ("hatch", (0.55, 0.035, 0.025), "carA", "WI LK 204", 0.3), ("estate", (0.02, 0.1, 0.36), "carB", "KA RS 41", 0.45),
    ("suv", (0.82, 0.83, 0.84), "carX", "F SB 902", 0.1)])
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, N
lib, traffic = S["lib"], S["traffic"]
font = bpy.data.fonts.load(os.path.join(FONT_DIR, "Montserrat-Black.ttf"), check_existing=True)
A, B, X = S["heroes"]["carA"], S["heroes"]["carB"], S["heroes"]["carX"]
PA = jx.lane_path("S", "straight")
PB = jx.lane_path("E", "straight")
STOP_A = 95.0 - (3.0 + 1.2 + A["L"] / 2)
STOP_B = 95.0 - (3.0 + 1.6 + B["L"] / 2)        # waits behind the shark teeth (they end 4.2 m from the centre)

seg1 = int(round(9.8 * FPS))
a1 = jx.kinematics(STOP_A - 21.0, 8.3, [(0, "cruise", 8.3), (0.7, "stop", STOP_A), (6.7, "cruise", 8.3)], seg1, a_acc=2.8)
b1 = jx.kinematics(STOP_B - 22.0, 8.0, [(0, "cruise", 8.0), (0.6, "stop", STOP_B), (9.3, "cruise", 8.3)], seg1, a_acc=2.8)
seg2 = int(round(5.6 * FPS))
# replay: A at 30 km/h straight through without slowing; B arrives first, stops at the teeth, goes after A
a2 = jx.kinematics(58.0, 8.3, [(0, "cruise", 8.3)], seg2)
b2 = jx.kinematics(STOP_B - 17.0, 7.0, [(0, "cruise", 7.0), (0.3, "stop", STOP_B), (4.9, "cruise", 7.0)], seg2)
seg3 = N - seg1 - seg2
a3 = jx.kinematics(66.0, 8.3, [(0, "cruise", 8.3)], seg3)
b3 = jx.kinematics(64.0, 7.0, [(0, "cruise", 7.0), (1.5, "stop", STOP_B), (5.6, "cruise", 7.0)], seg3)
frames = list(range(1, N + 1))
SV_A, SV_B = a1 + a2 + a3, b1 + b2 + b3
jx.drive(A, PA, SV_A, frames)
jx.drive(B, PB, SV_B, frames)
jx.brake_lights(A, SV_A)
jx.brake_lights(B, SV_B)
PX = jx.lane_path("N", "straight")
x_sv = [(-500.0, 0.0)] * (seg1 + seg2) + jx.kinematics(40.0, 8.0, [(0, "cruise", 8.0)], seg3)
jx.drive(X, PX, x_sv, frames)

bA = jx.badge("A", A, traffic, font, 0.25, 9.6)
bB = jx.badge("B", B, traffic, font, 0.45, 9.6)
for f, s_ in ((int(6.6 * FPS), 1.0), (int(6.6 * FPS) + 5, 1.4), (int(6.6 * FPS) + 11, 1.0)):
    bA.scale = (s_, s_, s_)
    bA.keyframe_insert("scale", frame=f)
jx.ribbon(PA, STOP_A + A["L"] / 2 + 0.6, STOP_A + 16.5, jx.BADGE_COLOURS["A"], S["env"], 1.4, 9.4, name="ribA")
jx.ribbon(PB, STOP_B + B["L"] / 2 + 0.6, STOP_B + 17.0, jx.BADGE_COLOURS["B"], S["env"], 1.7, 6.4, name="ribB")

# the signs, laid flat and big for the top view (the real ones stand on the footway)
import town as TN  # noqa: E402
jx.callout_from(TN.sign_306(S["T"], lib), "call306", S["env"], (6.4, -12.0), 0.6, 9.6)
jx.callout_from(TN.sign_205(S["T"], lib), "call205", S["env"], (9.6, 6.2), 0.9, 9.6)

shots = jx.Shots(N)
UP = Vector((0, 1, 0))
shots.add("Q_top", 30, 0.0, 9.8, lambda t: (Vector((0.6, -6.5 + 0.2 * t, 33.0 - 0.3 * t)), Vector((0.6, 0.2, 0.0))),
          up_fn=lambda t: UP)


def chase(t):
    i = min(len(A["track"]) - 1, int(t * FPS))
    x, y, _ = A["track"][i]
    return Vector((x - 0.6, y - 7.5, 2.3)), Vector((x + 2.5, y + 20.0, 0.9))


shots.add("R_chase", 24, 9.8, 15.4, chase)


def drone(t):
    u = (t - 15.4) / 6.1
    return Vector((31.0 - 3.0 * u, 6.0 - 12.0 * u, 21.0)), Vector((-1.5, 0.0, 0.5))


shots.add("F_drone", 26, 15.4, 21.5, drone)
shots.add("E_top", 30, 21.5, T_END, lambda t: (Vector((0.6, -6.0, 32.0 + 0.8 * (t - 21.5))), Vector((0.6, 1.0, 0.0))),
          up_fn=lambda t: UP)
sc.camera = bpy.data.objects["Q_top"]

TS.light(assets=ASSETS)
stage.hazify_all(dist=900.0, skip=("ribA", "ribB"))
stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
todo = STILLS or list(range(FR[0], FR[1] + 1) if FR else range(1, N + 1))
jx.render_frames(shots, OUT, todo)
print("RENDER_DONE", FR)
