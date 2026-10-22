"""Drive Like a Local #3, Germany: three cars, no signs. Who goes first? 9:16, 30 fps, 768 frames (25.6 s).
A comes from the south, B from the west, C from the east, all straight on. Everyone gives way to the right:
A waits for C, B waits for A, C has nobody on its right. Order: C, A, B.
0 to 12.6 s  top view quiz and the reveal in order. 12.6 to 16.6 drone, the rule in one line.
16.6 to 22.6 fines. 22.6 to 25.6 end card.
Run: python ep03_three_cars.py OUTDIR --frames 1-768 --res 720 --samples 16 --assets ASSETS [--stills 60,300]
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
T_END = 25.6
N = int(round(T_END * FPS))
FONT_DIR = next((d for d in (os.path.join(HERE, "fonts"), os.path.join(HERE, "..", "fonts"),
                             "/home/claude/sf2/fonts") if os.path.isdir(d)), None)

S = TS.build(ASSETS, "plain", seed=7, heroes=[
    ("hatch", (0.55, 0.035, 0.025), "carA", "WI LK 204", 0.3), ("estate", (0.02, 0.1, 0.36), "carB", "KA RS 41", 0.45),
    ("suv", (0.82, 0.83, 0.84), "carC", "F SB 902", 0.1)])
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, N
lib, traffic = S["lib"], S["traffic"]
font = bpy.data.fonts.load(os.path.join(FONT_DIR, "Montserrat-Black.ttf"), check_existing=True)
A, B, C = S["heroes"]["carA"], S["heroes"]["carB"], S["heroes"]["carC"]
PA, PB, PC = jx.lane_path("S", "straight"), jx.lane_path("W", "straight"), jx.lane_path("E", "straight")
STOP = {k: 95.0 - (3.0 + 1.2 + car["L"] / 2) for k, car in (("A", A), ("B", B), ("C", C))}

seg1 = int(round(12.6 * FPS))
a1 = jx.kinematics(STOP["A"] - 21.0, 8.3, [(0, "cruise", 8.3), (0.7, "stop", STOP["A"]), (8.9, "cruise", 8.3)], seg1, a_acc=2.8)
b1 = jx.kinematics(STOP["B"] - 23.0, 8.3, [(0, "cruise", 8.3), (0.8, "stop", STOP["B"]), (10.8, "cruise", 8.3)], seg1, a_acc=2.8)
c1 = jx.kinematics(STOP["C"] - 22.0, 8.0, [(0, "cruise", 8.0), (0.6, "stop", STOP["C"]), (6.7, "cruise", 8.3)], seg1, a_acc=2.8)
rest = N - seg1
# afterwards: a second, calm round for the drone shot (same order, different start distances)
a2 = jx.kinematics(52.0, 7.0, [(0, "cruise", 7.0), (2.4, "stop", STOP["A"]), (6.1, "cruise", 7.5)], rest)
b2 = jx.kinematics(48.0, 7.0, [(0, "cruise", 7.0), (2.6, "stop", STOP["B"]), (7.6, "cruise", 7.5)], rest)
c2 = jx.kinematics(50.0, 7.0, [(0, "cruise", 7.0), (2.5, "stop", STOP["C"]), (4.6, "cruise", 7.5)], rest)
frames = list(range(1, N + 1))
for car, path, sv in ((A, PA, a1 + a2), (B, PB, b1 + b2), (C, PC, c1 + c2)):
    jx.drive(car, path, sv, frames)
    jx.brake_lights(car, sv)

bA = jx.badge("A", A, traffic, font, 0.25, T_END)
bB = jx.badge("B", B, traffic, font, 0.4, T_END)
bC = jx.badge("C", C, traffic, font, 0.55, T_END)
for bd, t in ((bC, 6.6), (bA, 8.8), (bB, 10.7)):
    for f, s_ in ((int(t * FPS), 1.0), (int(t * FPS) + 5, 1.4), (int(t * FPS) + 11, 1.0)):
        bd.scale = (s_, s_, s_)
        bd.keyframe_insert("scale", frame=f)
for letter, car, path, t_off in (("A", A, PA, 10.6), ("B", B, PB, 12.4), ("C", C, PC, 8.7)):
    s0 = STOP[letter] + car["L"] / 2 + 0.6
    jx.ribbon(path, s0, STOP[letter] + 16.5, jx.BADGE_COLOURS[letter], S["env"], 1.4, t_off, name="rib" + letter)

shots = jx.Shots(N)
UP = Vector((0, 1, 0))
shots.add("Q_top", 30, 0.0, 12.6, lambda t: (Vector((0.0, -6.5 + 0.15 * t, 33.0 - 0.25 * t)), Vector((0.0, 0.2, 0.0))),
          up_fn=lambda t: UP)


def drone(t):
    u = (t - 12.6) / 10.0
    return Vector((-31.0 + 3.0 * u, -7.0 + 14.0 * u, 22.0)), Vector((1.5, 0.0, 0.5))


shots.add("F_drone", 26, 12.6, 22.6, drone)
shots.add("E_top", 30, 22.6, T_END, lambda t: (Vector((0.0, -6.0, 32.0 + 0.8 * (t - 22.6))), Vector((0.0, 1.0, 0.0))),
          up_fn=lambda t: UP)
sc.camera = bpy.data.objects["Q_top"]

TS.light(assets=ASSETS)
stage.hazify_all(dist=900.0, skip=("ribA", "ribB", "ribC"))
stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
todo = STILLS or list(range(FR[0], FR[1] + 1) if FR else range(1, N + 1))
jx.render_frames(shots, OUT, todo)
print("RENDER_DONE", FR)
