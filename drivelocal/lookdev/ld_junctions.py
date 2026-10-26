"""Look-dev stills for the junction kit (batch 2). 9:16, rendered on the lookdev workflow.
Run: python lookdev/ld_junctions.py OUTDIR --stills 1 --res 720 --samples 48 --assets ASSETS --shot rb1|rb2|bend
  rb1   single-lane roundabout from a high three-quarter drone angle, low warm sun, two cars circulating (motion blur)
        plus traffic waiting at the give-way lines.
  rb2   two-lane roundabout top view, quiz cars A, B, C with roof badges and coloured paths (jx.badge, jx.ribbon).
  bend  bending priority road at driver eye level: Zeichen 306 over Zusatzzeichen 1002 ahead on the right, the
        broken Breitstrich showing the bend, a car turning with the road.
The still number picks the frame (1 = the posed frame of the shot).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "kit"), os.path.join(HERE, "kit"), os.path.join(HERE, "..")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import jx  # noqa: E402
import junctions as JN  # noqa: E402
import roundabout as RB  # noqa: E402
import stage  # noqa: E402

OUT, RES, SAMPLES, ASSETS, STILLS, FR, SHOT = "frames", 720, 32, "assets", [1], None, "rb1"
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
    if x == "--stills":
        STILLS = [int(v) for v in a[i + 1].split(",")]
    if x == "--frames":
        p, q = a[i + 1].split("-")
        FR = (int(p), int(q))
    if x == "--shot":
        SHOT = a[i + 1]

FPS = jx.FPS
N = 150
POSE = 90                         # the posed frame
FONT_DIR = next((d for d in (os.path.join(HERE, "..", "fonts"), os.path.join(HERE, "fonts")) if os.path.isdir(d)), None)
HEROES = [("hatch", (0.62, 0.05, 0.03), "carA", "WI LK 204", 0.3),
          ("estate", (0.03, 0.12, 0.42), "carB", "KA RS 41", 0.45),
          ("suv", (0.85, 0.86, 0.87), "carC", "F SB 902", 0.1),
          ("saloon", (0.05, 0.055, 0.06), "carD", "DA MO 77", 0.5),
          ("hatch", (0.72, 0.6, 0.12), "carE", "GI TR 31", 0.25),
          ("estate", (0.32, 0.34, 0.36), "carF", "HD UL 66", 0.5),
          ("van", (0.86, 0.87, 0.88), "carG", "HU BB 330", 0.0)]


def sun(az_deg, elev_deg, energy=4.0, warm=(1.0, 0.78, 0.55)):
    """Low warm late-afternoon sun (az from +x, anticlockwise) and a matching warm cast on the sky light."""
    a_ = math.radians(az_deg)
    to_sun = Vector((math.cos(a_), math.sin(a_), 0))
    stage.sky(None, -to_sun, ASSETS, sun_elev_deg=elev_deg, sun_energy=energy)
    s = bpy.data.objects["sun"]
    s.data.color = warm
    s.data.angle = math.radians(0.8)
    w = bpy.context.scene.world
    nt = w.node_tree
    for n_ in nt.nodes:
        if n_.type == "BACKGROUND" and n_.name != "Background":
            n_.inputs["Strength"].default_value = 0.7
    # golden-hour sky for camera rays: warm the HDRI towards the horizon
    env_n = next(n_ for n_ in nt.nodes if n_.type == "TEX_ENVIRONMENT")
    bg = nt.nodes["Background"]
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.55
    mix.inputs["B"].default_value = (1.0, 0.8, 0.62, 1.0)
    nt.links.new(env_n.outputs["Color"], mix.inputs["A"])
    nt.links.new(mix.outputs["Result"], bg.inputs["Color"])


def ambient_traffic(S, paths, n=N):
    """Parked and moving fleet cars (collection instances) along extra paths: [(path, s_at_pose, v, ind)]."""
    keys = list(S["fleet"])
    out = []
    for k, (path, s_pose, v, ind) in enumerate(paths):
        e = bpy.data.objects.new(f"amb{k}", None)
        e.instance_type = "COLLECTION"
        e.instance_collection = S["fleet"][keys[(k * 3 + 1) % len(keys)]]
        S["traffic"].objects.link(e)
        car = dict(obj=e, L=4.5, name=f"amb{k}")
        sv = cruise_to(path, s_pose, v, n) if v > 0 else waiting(path, s_pose, n)
        if JN.MO is not None:
            JN.animate(car, path, sv, list(range(1, n + 1)), ind=ind)
        else:
            jx.drive(car, path, sv, list(range(1, n + 1)))
        out.append(car)
    return out


def cruise_to(path, s_at_pose, v, n=N, pose=POSE):
    """Constant speed so that the car is at arc length s_at_pose on the posed frame."""
    s0 = s_at_pose - v * (pose - 1) / FPS
    return [(s0 + v * f / FPS, v) for f in range(n)]


def waiting(path, s_stop, n=N):
    return [(s_stop, 0.0)] * n


def drive(car, path, sv, ind=None):
    JN.animate(car, path, sv, list(range(1, len(sv) + 1)), ind=ind)


def cam_at(name, lens, pos, tgt, up=None, dof=None):
    cam = stage.camera(name, lens)
    cam.location = pos
    cam.rotation_euler = stage.look_rot(Vector(pos), Vector(tgt), up)
    if dof:
        cam.data.dof.use_dof = True
        cam.data.dof.focus_distance = dof[0]
        cam.data.dof.aperture_fstop = dof[1]
    bpy.context.scene.camera = cam
    return cam


def keep_clear(cam_pos, tgt, radius=2.5):
    """Hide garden trees and bushes that stand between the camera and the subject (instances only)."""
    a, b = Vector(cam_pos), Vector(tgt)
    ab = b - a
    for o in list(bpy.data.objects):
        if o.type != "EMPTY" or o.instance_type != "COLLECTION" or not o.instance_collection:
            continue
        cn = o.instance_collection.name
        if not any(cn.startswith(p) for p in ("tree_d", "tree_c", "bush")):
            continue
        p = Vector(o.location)
        t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
        if (a + ab * t - p).length < radius + 2.0 * o.scale[0] and t < 0.8:
            o.hide_render = True


sc = None
if SHOT == "rb1":
    # single-lane roundabout, high three-quarter drone at golden hour, the low sun behind the camera's left shoulder
    # rakes long shadows across the circle. Red A and blue B circulate (motion blur), white C waits at the give-way
    # line in the foreground with yellow E queued behind, black D leaves, grey F crosses the far arm.
    S = RB.build(ASSETS, "single", seed=6, heroes=HEROES)
    A, B, C, D, E, F, G = (S["heroes"][k] for k in ("carA", "carB", "carC", "carD", "carE", "carF", "carG"))
    PA = S["lane_path"]("E", "W")
    drive(A, PA, cruise_to(PA, PA.s_circle_in + 15.0, 6.5))
    PB = S["lane_path"]("N", "E")
    drive(B, PB, cruise_to(PB, PB.s_circle_out - 5.0, 6.0), ind=("R", 0, 99))
    PC = S["lane_path"]("S", "N")
    sC = PC.stop_s(C["L"], PC.s_yield, 0.4)
    drive(C, PC, waiting(PC, sC))
    PE = S["lane_path"]("S", "E")
    drive(E, PE, waiting(PE, sC - C["L"] / 2 - E["L"] / 2 - 2.0))
    PD = S["lane_path"]("W", "N")
    drive(D, PD, cruise_to(PD, PD.s_circle_out + 10.0, 7.0), ind=("R", 0, 99))
    PF = S["lane_path"]("N", "S")
    drive(F, PF, cruise_to(PF, PF.s_yield - 30.0, 8.0))
    PG = S["lane_path"]("W", "E")
    drive(G, PG, cruise_to(PG, PG.s_yield - 38.0, 8.0))
    sun(205.0, 8.0, 5.6)
    pos, tgt = (8.5, -35.0, 6.8), (-0.5, 1.5, 0.0)
    keep_clear(pos, tgt, 3.5)
    cam_at("cam_rb1", 35, pos, tgt)
elif SHOT == "rb2":
    # two-lane roundabout, top view quiz: A waits on the south entry (left lane, going left), B circulates on the
    # inner track, C waits on the west entry (right lane, first exit). Late sun from the south-west for long shadows.
    S = RB.build(ASSETS, "two_lane", seed=8, heroes=HEROES)
    A, B, C, D, E, F, G = (S["heroes"][k] for k in ("carA", "carB", "carC", "carD", "carE", "carF", "carG"))
    font = bpy.data.fonts.load(os.path.join(FONT_DIR, "Montserrat-Black.ttf"), check_existing=True)
    PA = S["lane_path"]("S", "W", 1)
    drive(A, PA, waiting(PA, PA.stop_s(A["L"], PA.s_yield, 0.5)))
    PB = S["lane_path"]("E", "S", 1)
    s_b = PB.s_circle_in + 24.0
    drive(B, PB, cruise_to(PB, s_b, 6.5))
    PC = S["lane_path"]("W", "S", 0)
    drive(C, PC, waiting(PC, PC.stop_s(C["L"], PC.s_yield, 0.5)), ind=("R", 0, 99))
    PD = S["lane_path"]("N", "E", 0)
    drive(D, PD, cruise_to(PD, PD.s_circle_out + 10.0, 8.0), ind=("R", 0, 99))
    PE = S["lane_path"]("E", "N", 0)
    drive(E, PE, waiting(PE, PE.stop_s(E["L"], PE.s_yield, 0.5)))
    PF = S["lane_path"]("S", "N", 0)
    drive(F, PF, waiting(PF, PF.stop_s(F["L"], PF.s_yield, 0.5) - A["L"] - 3.5))
    PG = S["lane_path"]("N", "S", 0)
    drive(G, PG, cruise_to(PG, PG.s_yield - 16.0, 7.0))
    t_on, t_off = 0.0, N / FPS + 1
    for letter, car in (("A", A), ("B", B), ("C", C)):
        jx.badge(letter, car, S["traffic"], font, t_on, t_off, size=3.6)
    jx.ribbon(PA, PA.s_yield - 0.2, PA.s_circle_out + 10.0, jx.BADGE_COLOURS["A"], S["env"], t_on, t_off, width=1.3,
              name="ribA")
    jx.ribbon(PB, s_b + B["L"] / 2 + 0.8, PB.s_circle_out + 11.0, jx.BADGE_COLOURS["B"], S["env"], t_on, t_off,
              width=1.3, name="ribB")
    jx.ribbon(PC, PC.s_yield - 0.2, PC.s_circle_out + 10.0, jx.BADGE_COLOURS["C"], S["env"], t_on, t_off, width=1.3,
              name="ribC")
    sun(212.0, 16.0, 6.2)
    cam_at("cam_rb2", 32, (0.0, -6.0, 92.0), (0.0, -6.0, 0.0), up=Vector((0, 1, 0)))
elif SHOT == "bend":
    # driver's eye on the priority road from the south, golden hour: the road bends left (west); 306 over 1002-10
    # stands on the right, the broken Breitstrich sweeps round the far side of the bend. A ahead follows the bend
    # with its left indicator; B waits at its 205 on the north arm; C comes round the bend towards us.
    S = JN.build(ASSETS, "bend", seed=5, heroes=HEROES[:4], priority=("S", "W"))
    A, B, C, D = (S["heroes"][k] for k in ("carA", "carB", "carC", "carD"))
    PA = S["lane_path"]("S", "W")
    drive(A, PA, cruise_to(PA, 95.0 - 4.0, 5.0), ind=("L", 0, 99))
    PB = S["lane_path"]("N", "S")
    drive(B, PB, waiting(PB, PB.stop_s(B["L"], 95.0 - 3.6, 0.3)))
    PC = S["lane_path"]("W", "S")
    drive(C, PC, cruise_to(PC, 95.0 - 24.0, 6.0))
    PD = S["lane_path"]("E", "W")
    drive(D, PD, waiting(PD, PD.stop_s(D["L"], 95.0 - 3.6, 0.3)))
    sun(234.0, 6.5, 5.8)
    pos, tgt = (1.1, -21.5, 1.28), (1.6, 4.0, 1.85)
    keep_clear(pos, tgt, 1.5)
    cam_at("cam_bend", 26, pos, tgt, dof=(9.0, 6.0))
else:
    raise SystemExit("--shot rb1|rb2|bend")

sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, N
stubs = [o.name for o in bpy.data.objects if o.get("stub")]
if stubs:
    raise SystemExit("placeholder signs in a look-dev still: " + ", ".join(stubs[:5]))
if "--dry" in sys.argv:
    print("DRY_OK", SHOT, len(bpy.data.objects), "objects", flush=True)
    raise SystemExit(0)
stage.hazify_all(dist=950.0, color=(0.86, 0.76, 0.64), skip=("ribA", "ribB", "ribC"))
stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)), motion_blur=True)
sc.render.motion_blur_shutter = 0.5
shots = jx.Shots(N)
shots.list.append((sc.camera.name, 1, N))
todo = [POSE + (k - 1) * 10 for k in STILLS] if not FR else list(range(FR[0], FR[1] + 1))
jx.render_frames(shots, OUT, todo)
print("RENDER_DONE", SHOT, todo)
