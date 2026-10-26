"""Look-dev stills for the figures kit (kit/figures.py), 9:16.
  --shot zebra     a pedestrian on a zebra crossing (Zeichen 293, townplus) with a car stopped before it, a second
                   pedestrian waiting on the far kerb, everyday light
  --shot cyclist   a cyclist in a yellow rain jacket on a residential street at golden hour, low tracking camera,
                   motion blur on the wheels; a second city bike with a front basket further up the street
  --shot enforce   a parking attendant writing a ticket at a parked car, a police officer with a handheld speed
                   laser at the roadside, the patrol car behind him
Run: python ld_figures.py OUTDIR --stills 30 --res 720 --samples 48 --assets ASSETS --shot zebra
     (--res is the width; the height is 16/9 of it. --frames 1-60 renders a range.)"""
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "kit"), os.path.join(HERE, "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import figures as F  # noqa: E402
import jx  # noqa: E402
import signs as SG  # noqa: E402
import stage  # noqa: E402
import town as TN  # noqa: E402
import townplus as TP  # noqa: E402
import townstage as TS  # noqa: E402

try:
    import motion  # noqa: E402
except ImportError:          # until kit/motion.py is on the branch
    motion = None

OUT, RES, SAMPLES, ASSETS, FR, STILLS, SHOT = "frames", 720, 32, "assets", None, None, "zebra"
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
    if x == "--shot":
        SHOT = a[i + 1]
N = 60
FPS = 30
FRAMES = list(range(1, N + 1))
STILL = 30


def golden(sun_az=203.0, elev=15.0, energy=5.0, sun_col=(1.0, 0.66, 0.4), sky_tint=(1.0, 0.84, 0.7), amb=0.75):
    """Low warm sun (late October), warm tint on the sky the camera sees."""
    TS.light(sun_az_deg=sun_az, sun_elev_deg=elev, assets=ASSETS)
    sun = bpy.data.objects["sun"]
    sun.data.color = sun_col
    sun.data.energy = energy
    sun.data.angle = math.radians(1.0)
    nt = bpy.context.scene.world.node_tree
    env = next(n for n in nt.nodes if n.type == "TEX_ENVIRONMENT")
    bg = nt.nodes["Background"]
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    mul.inputs["B"].default_value = (*sky_tint, 1)
    nt.links.new(env.outputs["Color"], mul.inputs["A"])
    nt.links.new(mul.outputs["Result"], bg.inputs["Color"])
    for n in nt.nodes:
        if n.type == "BACKGROUND" and n != bg:
            n.inputs["Strength"].default_value = amb


def instance(coll, loc, yaw, c, name):
    e = bpy.data.objects.new(name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = coll
    e.location = loc
    e.rotation_euler = (0, 0, yaw - math.pi / 2)
    c.objects.link(e)
    return e


def look(cam, pos, tgt, lens):
    cam.location = pos
    cam.rotation_euler = stage.look_rot(Vector(pos), Vector(tgt))
    cam.data.lens = lens


def stopping_car(src, c, x, y_stop, yaw, name, v0=4.0, f_stop=22):
    """A car that brakes to a stop at y_stop (frame f_stop) and stands: brake lights lit (kit/motion.py)."""
    e = instance(src, (x, y_stop, 0), yaw, c, name)
    if motion is None:
        return e
    r = motion.rig(e)
    d = Vector((math.cos(yaw), math.sin(yaw)))
    tr = []
    dec = v0 / (f_stop / FPS)
    for f in FRAMES:
        t = min(f - 1, f_stop) / FPS
        v = max(0.0, v0 - dec * t)
        back = (v0 * v0 - v * v) / (2 * dec)
        rem = v0 * v0 / (2 * dec) - back
        p = Vector((x, y_stop)) - d * rem
        tr.append(dict(x=p.x, y=p.y, z=0.0, yaw=yaw, v=v, ind=None))
    motion.bake(r, tr)
    return e


def parked(src, x, y, yaw, name, c=None):
    e = instance(src, (x, y, 0), yaw, c or bpy.data.collections["env"], name)
    if motion is not None:
        motion.park(e, x, y, yaw)
    return e


# ------------------------------------------------------------------ shot 1: pedestrian on the zebra, car stopped
def shot_zebra():
    hx, hy = 3.5, 3.0
    S = TS.build(ASSETS, "plain", seed=5, hx=hx, hy=hy, parked=False)
    SG.setup(ASSETS)
    T, env, J, fleet = S["T"], S["env"], S["J"], S["fleet"]
    st = TP.through(J, "NS")
    zc = -30.0
    TP.rects("centre_broken", st, TP.dashes(-95.0, zc - 33.0, 3.0, 6.0, -0.06, 0.06) +
             TP.dashes(zc + 33.0, -12.0, 3.0, 6.0, -0.06, 0.06), TP.PAINT_Z, T.paint, env, kind="leitlinie")
    TP.zebra(T, env, st, zc, centre=30.0)
    trees = list(S["groups"]["decid"].children)
    import world as W_
    for k, y in enumerate((-22.0, -44.0, -58.0)):
        W_.instance(trees[k % 2], (hx + TN.KERB_W + TN.FOOT + 1.8, y, TN.KERB_H), rz=k * 1.7, s=1.1, c=env)
    for k, y in enumerate((-12.0, -64.0)):
        W_.instance(trees[(k + 1) % 2], (-(hx + TN.KERB_W + TN.FOOT + 1.8), y, TN.KERB_H), rz=k, s=1.05, c=env)
    keys = ["estate_grey", "suv_white", "saloon_black", "estate_blue", "hatch_silver", "suv_dark"]
    k = iter(keys * 3)
    for y in (-39.6, -45.4, -51.5, -58.0):          # east side, the last one ends 5 m before the crossing
        parked(fleet[next(k)], hx - 1.0, y, math.pi / 2, "parked")
    for y in (-16.0, -9.5, -40.5, -46.6):
        parked(fleet[next(k)], -(hx - 1.0), y, -math.pi / 2, "parked")
    # the car that stopped for the pedestrian: northbound, 2.5 m before the zebra
    L = 4.28
    stopping_car(fleet["hatch_red"], env, 1.75, zc - 2.0 - 2.5 - L / 2, math.pi / 2, "stopped")
    ground = F.kerb_ground("x", hx, TN.KERB_H)
    # hero pedestrian: crossing from the east kerb to the west, mid-crossing in front of the car at the still
    p1 = F.person(env, "ped_a", sex="f", height=1.68, skin=1, hair="bob", hair_color="brown",
                  jacket=F.srgb(150, 38, 34), trousers=F.srgb(36, 44, 66), shoes=F.srgb(40, 30, 26), bag="shoulder",
                  bag_color=F.srgb(110, 72, 42), seed=21)
    path = jx.Path([(hx + 2.0, zc + 0.2), (-(hx + 2.0), zc + 0.2)])
    v = 1.35
    s_still = (hx + 2.0) - 0.9
    sv = [(s_still + v * (f - STILL) / FPS, v) for f in FRAMES]
    car_eye = (1.75 - 0.35, zc - 2.0 - 2.5 - 1.6, 1.2)
    F.walk(p1, path, sv, ground=ground, look=[(0.0, 2.0, car_eye)])
    # second pedestrian waits on the west kerb, checking the traffic
    p2 = F.person(env, "ped_b", sex="m", height=1.81, skin=5, hair="short", jacket=F.srgb(40, 70, 50),
                  trousers=F.srgb(60, 60, 62), shoes=F.srgb(226, 224, 220), seed=22)
    F.stand(p2, (-(hx + 0.7), zc - 0.4), 0.0, N, ground=ground, look=[(0.0, 0.7, -65), (0.7, 2.0, 60)])
    # someone walking away on the east footway
    p3 = F.person(env, "ped_c", sex="m", height=1.74, skin=2, hair="short", hair_color="grey",
                  jacket=F.srgb(176, 138, 96), seed=23)
    path3 = jx.Path([(hx + 1.6, zc + 9.0), (hx + 1.6, zc + 40.0)])
    F.walk(p3, path3, [(1.0 + 1.25 * (f - 1) / FPS, 1.25) for f in FRAMES], ground=ground)
    TP.leaves(env, st, -90.0, 20.0, seed=5)
    golden(sun_az=236.0, elev=24.0, energy=4.6, sun_col=(1.0, 0.8, 0.62), sky_tint=(1.0, 0.93, 0.85), amb=0.8)
    cam = stage.camera("cam", 40)
    look(cam, (0.40, zc + 5.4, 1.18), (1.05, zc - 0.8, 1.16), 40)
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 5.4
    cam.data.dof.aperture_fstop = 4.0
    return cam, True


# ------------------------------------------------------------------ shot 2: cyclist, yellow jacket, golden hour
def shot_cyclist():
    hx, hy = 3.0, 3.0
    S = TS.build(ASSETS, "plain", seed=4, hx=hx, hy=hy, parked=True)
    SG.setup(ASSETS)
    env, fleet = S["env"], S["fleet"]
    cy = F.cyclist(env, "cy", rider=dict(sex="f", height=1.70, skin=2, hair="ponytail", hair_color="dark",
                                         jacket=F.YELLOW, trousers=F.srgb(36, 48, 74), shoes=F.srgb(226, 224, 220),
                                         seed=31),
                   bike=dict(frame="step", basket=False, color=F.srgb(36, 92, 112), guards="silver", seed=31))
    x = hx - 0.95
    path = jx.Path([(x, -120.0), (x, 60.0)])
    v = 5.2
    y_still = -26.0
    s_still = y_still + 120.0
    sv = [(s_still + v * (f - STILL) / FPS, v) for f in FRAMES]
    F.ride(cy, path, sv)
    cy2 = F.cyclist(env, "cy2", rider=dict(sex="m", height=1.80, skin=4, hair="short", jacket=F.srgb(40, 42, 46),
                                           seed=32),
                    bike=dict(frame="diamond", basket=True, color=F.srgb(110, 20, 24), seed=32))
    path2 = jx.Path([(-(hx - 1.0), 80.0), (-(hx - 1.0), -120.0)])
    F.ride(cy2, path2, [(70.0 + 4.2 * (f - 1) / FPS, 4.2) for f in FRAMES])
    golden(sun_az=198.0, elev=8.0, energy=9.0, sun_col=(1.0, 0.52, 0.22), sky_tint=(1.0, 0.62, 0.38), amb=0.6)
    bpy.context.scene.view_settings.exposure = 0.5
    # low tracking camera: moves with the bike, so the rider is sharp and the wheels and street blur
    cam = stage.camera("cam", 30)
    locs, rots = [], []
    for f in FRAMES:
        yy = y_still + v * (f - STILL) / FPS
        pos = Vector((x - 1.25, yy + 2.7, 0.36))
        tgt = Vector((x - 0.05, yy - 0.1, 0.92))
        locs.append(tuple(pos))
        rots.append(tuple(stage.look_rot(pos, tgt)))
    stage.bake_motion(cam, FRAMES, locs, rots)
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 2.95
    cam.data.dof.aperture_fstop = 2.8
    bpy.context.scene["shutter"] = 0.8         # a longer shutter for this still: the spokes smear
    return cam, True


# ------------------------------------------------------------------ shot 3: parking attendant and police laser
def shot_enforce():
    hx, hy = 3.5, 3.0
    S = TS.build(ASSETS, "plain", seed=7, hx=hx, hy=hy, parked=False)
    SG.setup(ASSETS)
    T, env, fleet = S["T"], S["env"], S["fleet"]
    import vehicles as V
    pol = V.make("police", "polcar", plate="QX PO 110", c=S["lib"])
    ground = F.kerb_ground("x", hx, TN.KERB_H)
    xp = hx - 1.0
    # parked on the east side, all more than 5 m from the junction; the ticketed car first
    parked(fleet["hatch_blue"], xp, -23.5, math.pi / 2, "ticketed")
    parked(pol, xp, -32.6, math.pi / 2, "patrol")
    parked(fleet["estate_grey"], xp, -15.0, math.pi / 2, "p2")
    parked(fleet["suv_white"], -(hx - 1.0), -18.0, -math.pi / 2, "p3")
    parked(fleet["saloon_white"], -(hx - 1.0), -46.0, -math.pi / 2, "p4")
    stopping_car(fleet["estate_blue"], env, 1.75, -46.0, math.pi / 2, "approach", v0=8.0, f_stop=200)
    # the attendant at the front of the ticketed car, reading the windscreen, device in hand (faces the camera)
    pa = F.parking_attendant(env, "attendant", sex="f", skin=3)
    F.stand(pa, (hx + 0.62, -20.7), (xp - 0.3, -22.2), N, ground=ground, gesture=[("write", 0.0, 3.0)])
    # the officer at the kerb just in front of his patrol car, aiming the laser down the street at oncoming traffic
    po = F.police_officer(env, "officer", sex="m", skin=1)
    F.stand(po, (hx + 0.45, -27.6), -math.pi / 2 - 0.20, N, ground=ground, gesture=[("laser", 0.0, 3.0)])
    trees = list(S["groups"]["decid"].children)
    import world as W_
    for k, y in enumerate((-12.0, -30.0)):
        W_.instance(trees[k % 2], (hx + TN.KERB_W + TN.FOOT + 1.8, y, TN.KERB_H), rz=k * 1.3, s=1.1, c=env)
    golden(sun_az=235.0, elev=26.0, energy=4.6, sun_col=(1.0, 0.84, 0.66), sky_tint=(1.0, 0.94, 0.88), amb=0.85)
    cam = stage.camera("cam", 58)
    look(cam, (hx + 1.55, -38.6, 1.55), (hx - 0.25, -24.0, 1.32), 58)
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 11.0
    cam.data.dof.aperture_fstop = 5.6
    return cam, False


t0 = time.time()
cam, blur = {"zebra": shot_zebra, "cyclist": shot_cyclist, "enforce": shot_enforce}[SHOT]()
print("scene built in", round(time.time() - t0, 1), "s", flush=True)
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, N
sc.camera = cam
stage.hazify_all(dist=900.0)
stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)), motion_blur=blur)
if "shutter" in sc:
    sc.render.motion_blur_shutter = sc["shutter"]


def figure_objects():
    figs = [o for o in bpy.data.objects if o.get("dl_figure") or (o.type == "EMPTY" and o.name.endswith("_bike"))]
    for o in list(figs):
        figs += list(o.children_recursive)
    return figs


todo = STILLS or (list(range(FR[0], FR[1] + 1)) if FR else [STILL])
os.makedirs(OUT, exist_ok=True)
for f in todo:
    sc.frame_set(f)
    sc.render.filepath = os.path.join(OUT, f"f_{f:04d}.png")
    t1 = time.time()
    bpy.ops.render.render(write_still=True)
    print("Saved", sc.render.filepath, round(time.time() - t1, 1), "s", flush=True)
if "--cost" in sys.argv:                  # cost measurement: the same frame again without the figures
    figs = figure_objects()
    for o in figs:
        o.hide_render = True
    sc.frame_set(todo[0])
    sc.render.filepath = os.path.join(OUT, f"nofig_{todo[0]:04d}.png")
    t1 = time.time()
    bpy.ops.render.render(write_still=True)
    print("COST without", len(figs), "figure objects:", round(time.time() - t1, 1), "s", flush=True)
print("RENDER_DONE")
