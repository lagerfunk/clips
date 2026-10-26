"""Look-dev stills for the town-plus kit (zebra, bike lanes, tram, parking), 9:16, golden hour.
  --shot zebra    the zebra crossing (Zeichen 293) at driver eye level: signs 350 on both sides, lighting masts,
                  pedestrians on the crossing, parked cars ending 5 m before it
  --shot tram     a tram crossing the X junction from a drone angle, Radfahrstreifen on the cross street
  --shot disc     the parking street (bays, 314 + 1040-32) with the parking disc behind a windscreen, close up
Run: python ld_townplus.py OUTDIR --stills 30 --res 720 --samples 48 --assets ASSETS --shot zebra
     (--res is the width; the height is 16/9 of it. --frames 1-60 renders a range.)"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "kit"), os.path.join(HERE, "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import jx  # noqa: E402
import parking as PK  # noqa: E402
import signs as SG  # noqa: E402
import stage  # noqa: E402
import town as TN  # noqa: E402
import townplus as TP  # noqa: E402
import townstage as TS  # noqa: E402
import tram as TR  # noqa: E402

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
FRAMES = list(range(1, N + 1))


def golden(sun_az=203.0, elev=15.0, energy=5.0, sun_col=(1.0, 0.66, 0.4), sky_tint=(1.0, 0.84, 0.7), amb=0.75):
    """Low warm sun from the west-south-west (late October), warm tint on the sky the camera sees."""
    TS.light(sun_az_deg=sun_az, sun_elev_deg=elev, assets=ASSETS)
    sun = bpy.data.objects["sun"]
    sun.data.color = sun_col
    sun.data.energy = energy
    sun.data.angle = math.radians(1.0)
    w = bpy.context.scene.world
    nt = w.node_tree
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


def walker(env, name, seed, pts, v, s_at_still, coat=None):
    ped = TP.pedestrian(env, name, seed=seed, coat=coat)
    path = jx.Path(pts)
    sv = [(s_at_still + v * (f - 30) / 30.0, v) for f in FRAMES]
    TP.walk(ped, path, sv, FRAMES)
    return ped


def standing(env, name, seed, xy, yaw, coat=None):
    ped = TP.pedestrian(env, name, seed=seed, coat=coat)
    ped["root"].location = (xy[0], xy[1], TN.KERB_H)
    ped["root"].rotation_euler = (0, 0, yaw - math.pi / 2)
    return ped


# ------------------------------------------------------------------ shot 1: zebra at driver eye level
def shot_zebra():
    hx, hy = 3.5, 3.0
    S = TS.build(ASSETS, "plain", seed=5, hx=hx, hy=hy, parked=False)
    SG.setup(ASSETS)
    T, env, J, fleet = S["T"], S["env"], S["J"], S["fleet"]
    st = TP.through(J, "NS")
    zc = -38.0
    # a 7.0 m collector street: broken centre line (Leitlinie 3 m / 6 m), solid for 30 m on both sides of the zebra
    TP.rects("centre_broken", st, TP.dashes(-95.0, zc - 33.0, 3.0, 6.0, -0.06, 0.06) +
             TP.dashes(zc + 33.0, -12.0, 3.0, 6.0, -0.06, 0.06), TP.PAINT_Z, T.paint, env, kind="leitlinie")
    z = TP.zebra(T, env, st, zc, centre=30.0)
    # street trees in the front gardens on the west side: shadows across the street, depth in the frame
    trees = list(S["groups"]["decid"].children)
    import world as W_
    for k, y in enumerate((-28.0, -18.0, -66.0, -84.0)):
        W_.instance(trees[k % 2], (-(hx + TN.KERB_W + TN.FOOT + 1.6), y, TN.KERB_H), rz=k * 1.7, s=1.15, c=env)
    # parked cars on the right (east) up to 5 m before the crossing, and on the far side outside its 5 m
    keys = ["estate_grey", "hatch_red", "suv_white", "saloon_black", "estate_blue", "hatch_silver", "suv_dark"]
    k = iter(keys * 3)
    # right side: the last car ends 5 m before the crossing (zc - 2 - 5 = -45 m)
    for y in (-47.6, -53.4, -59.5, -66.0, -72.3):
        instance(fleet[next(k)], (hx - 1.0, y, 0), math.pi / 2, env, "parked")
    for y in (-26.0, -20.0, -48.5, -54.6, -61.0):
        instance(fleet[next(k)], (-(hx - 1.0), y, 0), -math.pi / 2, env, "parked")
    # pedestrians: one crossing from the right, one waiting to cross on the left, one on the footway
    walker(env, "ped_a", 3, [(hx + 1.2, zc - 0.6), (-(hx + 1.2), zc - 0.6)], 1.3, 3.4, coat=(0.62, 0.45, 0.12))
    standing(env, "ped_b", 7, (-(hx + 0.55), zc + 0.9), 0.0, coat=(0.08, 0.1, 0.2))
    walker(env, "ped_c", 11, [(hx + 1.6, -20.0), (hx + 1.6, -70.0)], 1.2, 9.0)
    TP.leaves(env, st, -90.0, 20.0, seed=5)
    # our car waits 2.5 m before the crossing; the camera sits at the driver's eye height just in front of the
    # windscreen, so the bonnet frames the bottom of the picture
    ego = instance(fleet["estate_blue"], (0.2, zc - 2.0 - 8.5 - 4.77 / 2, 0), math.pi / 2, env, "ego")
    # low sun from the west-north-west, in front and to the left: warm glow in the sky, tree and house shadows
    # raking across the street towards the camera's right
    golden(sun_az=166.0, elev=9.0, energy=6.5, sun_col=(1.0, 0.58, 0.3), sky_tint=(1.0, 0.8, 0.62))
    bpy.context.scene.view_settings.exposure = 0.45
    cam = stage.camera("cam", 35)
    eye = (ego.location.x - 0.36, ego.location.y + 4.77 / 2 - 1.12, 1.24)
    look(cam, eye, (0.5, zc + 6.0, 2.35), 35)
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = abs(zc - eye[1])
    cam.data.dof.aperture_fstop = 4.0
    return cam


# ------------------------------------------------------------------ shot 2: tram over the X junction, drone
def shot_tram():
    hx, hy = 4.5, 5.0
    S = TS.build(ASSETS, "plain", seed=6, hx=hx, hy=hy, parked=False)
    SG.setup(ASSETS)
    T, env, J, fleet = S["T"], S["env"], S["J"], S["fleet"]
    ts = TP.tram_street_x(T, env, J, "NS", bed="asphalt")
    TP.bike_lanes_x(T, env, J, "EW", "radfahrstreifen")
    # the tram street is the priority road: 306 on it, 205 and shark teeth on the cross street (Commons signs)
    off = TN.KERB_W + TP.SIGN_OFF
    SG.assembly([("306", 0.6)], env, (hx + off, -(hy + 6.0 + 4.0), TN.KERB_H), TN.facing((0, 1)), name="z306_s")
    SG.assembly([("306", 0.6)], env, (-(hx + off), hy + 6.0 + 4.0, TN.KERB_H), TN.facing((0, -1)), name="z306_n")
    SG.assembly([("205", 0.9)], env, (hx + 6.0 + 1.5, hy + off, TN.KERB_H), TN.facing((-1, 0)), name="z205_e")
    SG.assembly([("205", 0.9)], env, (-(hx + 6.0 + 1.5), -(hy + off), TN.KERB_H), TN.facing((1, 0)), name="z205_w")
    for sxe in (1, -1):
        TN.haifisch(T, env, (sxe * (hx + 0.6), sxe * (hy - TP.RAD_W) / 2), (0, 1), (sxe, 0), hy - TP.RAD_W - 0.5)
    tram = TR.build(env, "tram", sections=5, route="4", dest="Hauptbahnhof")
    path = TP.tram_path(ts["street"], ts["tracks"]["centres"][1], +1)
    s_mid = path.length / 2 - 2.0
    sv = [(s_mid + 7.0 * (f - 30) / 30.0, 7.0) for f in FRAMES]
    TR.drive(tram, path, sv, FRAMES)
    TR.lights(tram)
    # cars wait for the tram on both side streets, more traffic further out
    instance(fleet["hatch_red"], (hx + 6.8 + 2.2, 1.55, 0), math.pi, env, "wait_e")
    instance(fleet["estate_grey"], (hx + 6.8 + 8.2, 1.55, 0), math.pi, env, "wait_e2")
    instance(fleet["suv_white"], (-(hx + 6.8 + 2.3), -1.55, 0), 0.0, env, "wait_w")
    instance(fleet["saloon_black"], (-1.4, 38.0, 0), -math.pi / 2, env, "nb_car")
    instance(fleet["estate_blue"], (2.2, -44.0, 0), math.pi / 2, env, "behind_tram")
    # cyclists on the Radfahrstreifen
    # one cyclist waits at the west mouth (eastbound lane, y < 0), one rides west on the north lane
    cy1 = TP.cyclist(env, "cy1", seed=2, crank=0.4)
    p1 = jx.Path([(-60.0, -(hy - 0.95)), (-(hx + 1.2), -(hy - 0.95))])
    TP.ride(cy1, p1, [(p1.length, 0.0)] * N, FRAMES)
    cy2 = TP.cyclist(env, "cy2", seed=5, crank=1.9)
    p2 = jx.Path([(60.0, hy - 0.95), (hx + 1.2, hy - 0.95)])
    TP.ride(cy2, p2, [(36.0 + 4.5 * (f - 30) / 30.0, 4.5) for f in FRAMES], FRAMES)
    for nm, sd, xy, yaw in (("pa", 4, (hx + 1.5, -12.5), math.pi / 2), ("pb", 9, (-(hx + 1.2), 11.0), -0.3),
                            ("pc", 13, (13.0, -(hy + 1.4)), math.pi)):
        standing(env, nm, sd, xy, yaw)
    golden(sun_az=196.0, elev=14.0, energy=5.5, sun_col=(1.0, 0.62, 0.36), sky_tint=(1.0, 0.82, 0.66))
    bpy.context.scene.view_settings.exposure = 0.25
    # drone above the south-east corner, over the footway and front gardens, looking north-west across the junction
    cam = stage.camera("cam", 30)
    look(cam, (9.5, -27.0, 19.0), (-1.0, 4.0, 0.0), 30)
    return cam


# ------------------------------------------------------------------ shot 3: parking street, disc behind glass
def shot_disc():
    hx, hy = 4.0, 3.0
    S = TS.build(ASSETS, "plain", seed=8, hx=hx, hy=hy, parked=False,
                 heroes=[("estate", (0.02, 0.07, 0.16), "hero", "WI PS 318", 0.55)])
    SG.setup(ASSETS)
    T, env, J, fleet, lib = S["T"], S["env"], S["J"], S["fleet"], S["lib"]
    st = TP.through(J, "NS")
    # west row (side -1) serves southbound traffic; the hero parks in its first bay, nose south, so the low
    # west-south-west sun lights the windscreen; the 314 + 1040-32 sign and the 283 stand just behind it
    P = PK.street(T, env, st, fleet, n=6, sides=(+1, -1), s0={+1: 20.0, -1: 60.0}, wrong_way=(+1, 4),
                  skip={(-1, 0)}, seed=4)
    hero = S["heroes"]["hero"]
    PK.place_hero(hero, P["rows"][-1], 0)
    PK.see_through(hero)
    disc = PK.parkscheibe(lib, None, name="pd")           # Commons file (shows 18:00) when the library has it
    PK.windscreen_mount(hero, disc, side=+1, along=0.9, x=0.3)
    TP.leaves(env, st, 20.0, 80.0, seed=9)
    standing(env, "pw", 6, (-(hx + 1.9), 66.5), -math.pi / 2 + 0.5)
    # low sun from the south-west, onto the windscreen (the car's nose points south)
    golden(sun_az=238.0, elev=17.0, energy=6.0, sun_col=(1.0, 0.62, 0.36), sky_tint=(1.0, 0.82, 0.66))
    bpy.context.scene.view_settings.exposure = 0.55
    bpy.context.view_layer.update()
    dw = disc["root"]
    m = hero["obj"].matrix_world @ dw.matrix_world       # the hero instance places the collection
    c = m @ Vector((0, 0, 0.075))
    car_fwd = Vector((0, -1, 0))                           # the hero's nose points south
    car_right = Vector((-1, 0, 0))                         # its right side is the kerb (west)
    up = Vector((0, 0, 1))
    # a warden's view from the footway in front of the car: the disc low in the frame behind the glass, the
    # bonnet and the far side of the street (sunlit house fronts, the parked row) soft above it
    pos = c + car_fwd * 0.7 + car_right * 0.3 + up * 0.3
    d = (c - pos).normalized()
    side_ax = d.cross(up).normalized()
    from mathutils import Matrix
    # aim at the disc, then pitch up 12 degrees and turn 4 degrees towards the street: the disc sits in the lower
    # third, the far side of the street fills the top of the frame
    d2 = Matrix.Rotation(math.radians(-4), 3, up) @ (Matrix.Rotation(math.radians(12), 3, side_ax) @ d)
    cam = stage.camera("cam", 45)
    look(cam, tuple(pos), tuple(pos + d2 * 3.0), 45)
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = (pos - c).length
    cam.data.dof.aperture_fstop = 3.2
    # soft fill from the footway side (a bounce off the house fronts behind the camera)
    li = bpy.data.lights.new("fill", "AREA")
    li.energy = 260.0
    li.size = 2.0
    li.color = (1.0, 0.86, 0.72)
    fo = bpy.data.objects.new("fill", li)
    env.objects.link(fo)
    fo.location = c + car_fwd * 1.8 + car_right * 1.2 + up * 1.1
    fo.rotation_euler = (c - fo.location).to_track_quat("-Z", "Y").to_euler()
    # sky light falling through the windscreen onto the dashboard (soft, from above the glass)
    li2 = bpy.data.lights.new("dash_sky", "AREA")
    li2.energy = 40.0
    li2.size = 1.2
    li2.color = (0.85, 0.9, 1.0)
    fo2 = bpy.data.objects.new("dash_sky", li2)
    env.objects.link(fo2)
    fo2.location = c + car_fwd * 0.5 + up * 0.75
    fo2.rotation_euler = (c - fo2.location).to_track_quat("-Z", "Y").to_euler()
    return cam


cam = {"zebra": shot_zebra, "tram": shot_tram, "disc": shot_disc}[SHOT]()
sc = bpy.context.scene
sc.render.fps = 30
sc.frame_start, sc.frame_end = 1, N
sc.camera = cam
stage.hazify_all(color=(0.8, 0.74, 0.68), dist=900.0)
stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
print("SIGN_SOURCES", sorted(SG.sources_used()))
os.makedirs(OUT, exist_ok=True)
todo = STILLS or list(range(FR[0], FR[1] + 1) if FR else [30])
for f in todo:
    sc.frame_set(f)
    sc.render.filepath = os.path.join(OUT, f"f_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    print("Saved", sc.render.filepath, flush=True)
print("RENDER_DONE")
