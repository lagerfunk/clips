"""Drive Like a Local #2, Germany: rechts vor links (who goes first at a junction with no signs). 9:16, 30 fps,
735 frames (24.5 s).
0 to 9.8 s   top view quiz: A from the south, B from the east, both stop; 3, 2, 1; B goes first, then A.
9.8 to 15.4  replay behind A at driving height: B appears from behind the hedge on the right, A lets it pass.
15.4 to 21.5 drone over the junction while the fines come in. 21.5 to 24.5 end card.
Run: python ep02_rechts_vor_links.py OUTDIR --frames 1-735 --res 720 --samples 16 --assets ASSETS [--stills 60,300]
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
N = int(T_END * FPS)
FONT_DIR = next((d for d in (os.path.join(HERE, "fonts"), os.path.join(HERE, "..", "fonts"),
                             "/home/claude/sf2/fonts") if os.path.isdir(d)), None)

S = TS.build(ASSETS, "plain", seed=4, heroes=[
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
STOP_B = 95.0 - (3.0 + 1.2 + B["L"] / 2)

# segment 1 (0 to 9.8 s): both stop at the junction, B goes at 6.7 s, A at 9.0 s
seg1 = int(9.8 * FPS)
a1 = jx.kinematics(STOP_A - 21.0, 8.3, [(0, "cruise", 8.3), (0.7, "stop", STOP_A), (9.0, "cruise", 8.3)], seg1, a_acc=2.8)
b1 = jx.kinematics(STOP_B - 22.0, 8.0, [(0, "cruise", 8.0), (0.6, "stop", STOP_B), (6.7, "cruise", 8.3)], seg1, a_acc=2.8)
# segment 2 (9.8 to 15.4 s): replay at driving height. A slows to 10 km/h, B comes through at 25 km/h.
seg2 = int(5.6 * FPS)
a2 = jx.kinematics(60.0, 8.3, [(0, "cruise", 8.3), (0.8, "cruise", 2.6), (3.5, "cruise", 7.0)], seg2)
b2 = jx.kinematics(93.5 - 7.0 * 2.75, 7.0, [(0, "cruise", 7.0)], seg2)
# segment 3 and 4 (15.4 to 24.5 s): A drives on north, B is long gone; restart both further out
seg3 = N - seg1 - seg2
a3 = jx.kinematics(70.0, 6.5, [(0, "cruise", 6.5), (1.6, "stop", STOP_A), (5.2, "cruise", 7.0)], seg3)
b3 = jx.kinematics(60.0, 7.0, [(0, "cruise", 7.0), (2.2, "stop", STOP_B), (3.4, "cruise", 7.0)], seg3)
frames = list(range(1, N + 1))
SV_A, SV_B = a1 + a2 + a3, b1 + b2 + b3
jx.drive(A, PA, SV_A, frames)
jx.drive(B, PB, SV_B, frames)
jx.brake_lights(A, SV_A)
jx.brake_lights(B, SV_B)

# quiz layer
bA = jx.badge("A", A, traffic, font, 0.25, 9.6)
bB = jx.badge("B", B, traffic, font, 0.45, 9.6)
for f, s_ in ((int(6.6 * FPS), 1.0), (int(6.6 * FPS) + 5, 1.4), (int(6.6 * FPS) + 11, 1.0)):
    bB.scale = (s_, s_, s_)
    bB.keyframe_insert("scale", frame=f)
jx.ribbon(PA, STOP_A + A["L"] / 2 + 0.6, STOP_A + 16.5, jx.BADGE_COLOURS["A"], S["env"], 1.4, 6.4, name="ribA")
jx.ribbon(PB, STOP_B + B["L"] / 2 + 0.6, STOP_B + 16.5, jx.BADGE_COLOURS["B"], S["env"], 1.7, 9.2, name="ribB")

# extra life: a neighbour's car drives along the east-west street during the drone shot
PX = jx.lane_path("W", "straight")
x_sv = [(-500.0, 0.0)] * (seg1 + seg2) + jx.kinematics(64.0, 7.5, [(0, "cruise", 7.5)], seg3)
jx.drive(X, PX, x_sv, frames)

# cameras
shots = jx.Shots(N)
UP = Vector((0, 1, 0))
shots.add("Q_top", 30, 0.0, 9.8, lambda t: (Vector((0.6, -6.5 + 0.2 * t, 33.0 - 0.3 * t)), Vector((0.6, 0.2, 0.0))),
          up_fn=lambda t: UP)


def chase(t):
    i = min(len(A["track"]) - 1, int(t * FPS))
    x, y, _ = A["track"][i]
    return Vector((x - 0.4, y - 7.5, 2.3)), Vector((x + 3.0, y + 20.0, 0.9))


shots.add("R_chase", 24, 9.8, 15.4, chase)


def drone(t):
    u = (t - 15.4) / 6.1
    return Vector((-6.0 + 12.0 * u, -31.0 + 3.0 * u, 21.0)), Vector((0.0, 1.5, 0.5))


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
