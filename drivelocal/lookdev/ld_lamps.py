"""Look-dev for the lit lamp colours (kit/vehicles.py LIT_RED, LIT_AMBER and the levels next to them): hatch, saloon
and estate with their lamps lit, at noon or at dusk (weather.apply("dusk"), the cars counted as moving, so tail
lights and low beams are on as in a dusk episode). Frames (n = number of kinds, i = index in --kinds):
  frame 2i+1  rear three-quarter from the left rear, brake lights and the left indicator lit
  frame 2i+2  front three-quarter from the right front, the right indicator lit
  frame 2n+1  traffic at 30 m (rear views braking, one left and one right indicator; two oncoming cars, one
              indicating right)
Every frame logs "LAMP f=<frame> car=<name> part=<taillight|brake3|indicator|headlight> mat=<material>
box=x0,y0,x1,y1 facing=<cos>" (pixels, top left origin) for the lamp parts the camera sees, so the stills can be
measured without guessing where the lamps are.
  --light noon|dusk   (default noon)
  --before            build with main's kit (lookdev/vehicles_main.py, a byte copy of main's kit/vehicles.py), which
                      also stands in for "vehicles" inside motion.py, so the indicator lenses are main's too
Run: python lookdev/ld_lamps.py OUT --stills 1,2 --res 720 --samples 16 --assets ASSETS --light dusk
"""
import hashlib
import importlib.util
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "kit")]

import bpy  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
from mathutils import Vector  # noqa: E402

if "--before" in sys.argv:
    _f = os.path.join(HERE, "vehicles_main.py")
    _spec = importlib.util.spec_from_file_location("vehicles", _f)
    V = importlib.util.module_from_spec(_spec)
    sys.modules["vehicles"] = V          # motion.py's own "import vehicles" gets main's kit as well
    _spec.loader.exec_module(V)
else:
    import vehicles as V  # noqa: E402
import motion  # noqa: E402
import stage  # noqa: E402
import weather  # noqa: E402
import world as W  # noqa: E402

print("KIT", V.__name__, os.path.realpath(V.__file__), "sha1",
      hashlib.sha1(open(V.__file__, "rb").read()).hexdigest(), flush=True)

OUT, RES, SAMPLES, ASSETS, STILLS, LIGHT = "frames", 720, 16, "assets", None, "noon"
KINDS = ["hatch", "saloon", "estate"]
COLORS = {"hatch": (0.62, 0.62, 0.64), "saloon": (0.02, 0.32, 0.33), "estate": (0.05, 0.09, 0.22)}
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
    if x == "--kinds":
        KINDS = a[i + 1].split(",")
    if x == "--light":
        LIGHT = a[i + 1]

PARTS = ("taillight", "brake3", "indicator", "headlight")


def key(idb, path, f, val):
    idb[path] = val
    idb.keyframe_insert(f'["{path}"]', frame=f)


def constant(idb):
    ad = idb.animation_data
    if ad and ad.action:
        for fc in stage.fcurves(idb):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


def set_lamps(r, f, brake=0.0, left=False, right=False):
    for u in r.units.values():
        key(u, "brake", f, brake)
    for lp in r.lamps.values():
        key(lp, "ind_l", f, motion.IND_ON if left else 0.0)
        key(lp, "ind_r", f, motion.IND_ON if right else 0.0)


def place(r, x, y, yaw):
    r.obj.location = (x, y, 0.0)
    r.obj.rotation_euler = (0.0, 0.0, yaw)


def part_of(o):
    n = o.name
    if "_ind" in n and n.split("_ind")[-1].split(".")[0].isdigit():
        return "indicator"
    return next((p for p in PARTS if n.startswith(p)), None)


def log_lamps(f, cars):
    """Screen boxes of the lamp parts the camera sees (instanced through the vehicle and lamp instances)."""
    sc = bpy.context.scene
    cam = sc.camera
    dg = bpy.context.evaluated_depsgraph_get()
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    cpos = cam.matrix_world.translation
    for inst in dg.object_instances:
        if not inst.is_instance or inst.object.type != "MESH":
            continue
        part = part_of(inst.object)
        if part is None:
            continue
        mw = inst.matrix_world.copy()
        me = inst.object.data
        if not me.polygons:
            continue
        pts = [mw @ v.co for v in me.vertices]
        cen = sum(pts, Vector()) / len(pts)
        big = max(me.polygons, key=lambda p: p.area)
        nrm = (mw.to_3x3() @ big.normal).normalized()
        facing = abs(nrm.dot((cpos - cen).normalized()))     # a mirrored plate's top face may wind inwards
        uv = [world_to_camera_view(sc, cam, p) for p in pts]
        if min(q.z for q in uv) <= 0 or facing < 0.2:
            continue
        xs = [q.x * rx for q in uv]
        ys = [(1 - q.y) * ry for q in uv]
        if max(xs) < 0 or min(xs) > rx or max(ys) < 0 or min(ys) > ry:
            continue
        dist = (cen - cpos).length          # hidden behind the body (or another car): skip
        hit, loc, _n, _i, _o, _m = sc.ray_cast(dg, cpos, (cen - cpos).normalized(), distance=dist + 0.05)
        if hit and (loc - cpos).length < dist - 0.03:
            continue
        car = min(cars, key=lambda c: (Vector(c[1].obj.location) - cen).length)[0]
        mat = me.materials[0].name if me.materials else "-"
        print(f"LAMP f={f} car={car} part={part} mat={mat} box={min(xs):.0f},{min(ys):.0f},{max(xs):.0f},"
              f"{max(ys):.0f} facing={facing:.2f} dist={(cpos - cen).length:.1f}", flush=True)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    W.setup(ASSETS, None)
    lib = W.coll("lib")
    traffic = W.coll("traffic")
    sc = bpy.context.scene
    # noon: the HDRI sky of the episodes, sun high behind the cars' left (it lights the rear faces: the hardest case
    # for a lit lamp to read); dusk: weather.apply("dusk") on top (low sun, exposure +0.5, bloom, tail lights)
    stage.sky(None, -Vector((-0.5, -1.0, 0.0)).normalized(), ASSETS, sun_elev_deg=58.0, sun_energy=4.2)
    bpy.ops.mesh.primitive_plane_add(size=600, location=(60, 0, 0))
    gnd = bpy.context.active_object
    gnd.data.materials.append(W.principled("ld_asphalt", (0.07, 0.07, 0.075), 0.85))
    cam = stage.camera("cam", 28)
    sc.camera = cam
    n = len(KINDS)
    colls = {kind: V.make(kind, "ld_" + kind, COLORS.get(kind) or (0.5, 0.5, 0.52), "F LD %d" % (100 + i), c=lib)
             for i, kind in enumerate(KINDS)}
    cars = []
    nf = 2 * n + 1
    for i, kind in enumerate(KINDS):
        r = motion.rig(colls[kind], c=traffic)
        x0 = i * 14.0
        place(r, x0, 0.0, 0.0)
        cars.append((kind, r))
        md = r.md
        lo, hi = md["lo"], md["hi"]
        Lv, Wv, Hv = hi.y - lo.y, hi.x - lo.x, hi.z
        d = 1.9 * Hv + 1.6
        views = [(Vector((x0 - 0.25 * Wv, lo.y + 0.9 + 0.08 * Lv, 0.45 * Hv)), Vector((-0.75, -1.0, 0.2))),
                 (Vector((x0 + 0.25 * Wv, hi.y - 0.9 - 0.08 * Lv, 0.45 * Hv)), Vector((0.75, 1.0, 0.18)))]
        for f in range(1, nf + 1):
            v = f - 1 - 2 * i
            set_lamps(r, f, brake=1.0 if v == 0 else 0.0, left=v == 0, right=v == 1)
        for v, (tgt, dirn) in enumerate(views):
            f = 2 * i + 1 + v
            pos = tgt + dirn.normalized() * d
            cam.location = pos
            cam.rotation_euler = stage.look_rot(pos, tgt)
            cam.keyframe_insert("location", frame=f)
            cam.keyframe_insert("rotation_euler", frame=f)
            cam.data.lens = 28
            cam.data.keyframe_insert("lens", frame=f)
        print("built", kind, "L %.2f W %.2f H %.2f" % (Lv, Wv, Hv), flush=True)
    # traffic at 30 m: three cars driving away in two lanes (all braking; left and right indicators), two oncoming
    xt = 120.0
    lanes = [(-1.9, 30.0, "hatch", 0.0, True, False), (1.9, 31.5, "saloon", 0.0, False, True),
             (5.7, 34.0, "estate", 0.0, False, False), (-6.0, 27.0, "estate", math.pi, False, True),
             (-9.6, 36.0, "saloon", math.pi, False, False)]
    for j, (dx, dy, kind, yaw, lft, rgt) in enumerate(lanes):
        if kind not in colls:
            continue
        r = motion.rig(colls[kind], c=traffic)
        place(r, xt + dx, dy, yaw)
        cars.append((f"t{j}_{kind}", r))
        for f in range(1, nf + 1):
            set_lamps(r, f, brake=1.0 if yaw == 0.0 else 0.0, left=lft, right=rgt)
    pos, tgt = Vector((xt + 0.2, 0.0, 2.2)), Vector((xt - 1.0, 30.0, -1.2))
    cam.location = pos
    cam.rotation_euler = stage.look_rot(pos, tgt)
    cam.keyframe_insert("location", frame=nf)
    cam.keyframe_insert("rotation_euler", frame=nf)
    cam.data.lens = 35
    cam.data.keyframe_insert("lens", frame=nf)
    for o in [cam, cam.data] + [o for o in bpy.data.objects if o.animation_data]:
        constant(o)
    sc.frame_start, sc.frame_end = 1, nf
    stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)), motion_blur=False)
    if LIGHT == "dusk":
        for _k, r in cars:
            for u in [r.obj] + list(r.units.values()):
                u["wx_moving"] = 1.0
        P = weather.apply("dusk")
        print("WEATHER dusk exposure", P.get("exposure"), "bloom", P.get("bloom"), flush=True)
    print("VIEW", sc.view_settings.view_transform, sc.view_settings.look, "exposure", sc.view_settings.exposure,
          flush=True)
    os.makedirs(OUT, exist_ok=True)
    for f in STILLS or list(range(1, nf + 1)):
        sc.frame_set(f)
        log_lamps(f, cars)
        sc.render.filepath = os.path.join(OUT, f"f_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("Saved", sc.render.filepath, flush=True)


main()
print("RENDER_DONE")
