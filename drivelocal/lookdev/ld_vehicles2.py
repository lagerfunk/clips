"""Look-dev for vehicles2 (moulded lamps, smooth body shading, an ordinary hatchback front): every body kind in
close-up at day light, three stills per kind on consecutive frames:
  frame 3i+1  front three-quarter (left front corner, lenses unlit)
  frame 3i+2  rear three-quarter
  frame 3i+3  rear corner close-up, brake lights and the left indicator lit
  frame 3n+i+1  front corner close-up (headlight unit), the left indicator lit (n = number of kinds)
i is the index in --kinds (default: hatch,saloon,estate,suv,van,police,bus,artic,drawbar).
  --before   build the cars with main's kit: lookdev/vehicles_main.py (a copy of main's kit/vehicles.py, made with
             `git show origin/main:projects/drivelocal/kit/vehicles.py`), loaded from that file under its own module
             name "vehicles_main", so a kit module imported earlier in the process cannot stand in for it. The log
             line "KIT <module> <file> sha1 <hash>" proves which file each job built from.
The cameras depend only on the car's size (not on lamp positions), so the before and after frames match.
Run: python lookdev/ld_vehicles2.py OUT --stills 1,2,3 --res 720 --samples 16 --kinds hatch
"""
import hashlib
import importlib.util
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import motion  # noqa: E402
import stage  # noqa: E402
import world as W  # noqa: E402

if "--before" in sys.argv:
    _f = os.path.join(HERE, "vehicles_main.py")
    _spec = importlib.util.spec_from_file_location("vehicles_main", _f)
    V = importlib.util.module_from_spec(_spec)
    sys.modules["vehicles_main"] = V
    _spec.loader.exec_module(V)
else:
    import vehicles as V  # noqa: E402
print("KIT", V.__name__, os.path.realpath(V.__file__), "sha1",
      hashlib.sha1(open(V.__file__, "rb").read()).hexdigest(), flush=True)

OUT, RES, SAMPLES, ASSETS, STILLS = "frames", 720, 16, "assets", None
KINDS = ["hatch", "saloon", "estate", "suv", "van", "police", "bus", "artic", "drawbar"]
COLORS = {"hatch": (0.62, 0.62, 0.64), "saloon": (0.02, 0.32, 0.33), "estate": (0.05, 0.09, 0.22),
          "suv": (0.35, 0.03, 0.03), "van": (0.85, 0.85, 0.84), "police": None, "bus": (0.86, 0.84, 0.76),
          "artic": (0.75, 0.76, 0.78), "drawbar": (0.86, 0.87, 0.88)}
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


def key(idb, path, f, val):
    idb[path] = val
    idb.keyframe_insert(f'["{path}"]', frame=f)


def constant(idb):
    ad = idb.animation_data
    if ad and ad.action:
        for fc in stage.fcurves(idb):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    W.setup(ASSETS, None)
    lib = W.coll("lib")
    traffic = W.coll("traffic")
    sc = bpy.context.scene
    # day light: sun high on the left front, a blue sky dome, plain asphalt
    world = sc.world or bpy.data.worlds.new("w")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background") or world.node_tree.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (0.5, 0.62, 0.85, 1)
    bg.inputs["Strength"].default_value = 0.9
    out = next(n for n in world.node_tree.nodes if n.type == "OUTPUT_WORLD")
    world.node_tree.links.new(bg.outputs[0], out.inputs["Surface"])
    sun = bpy.data.objects.get("sun")
    if sun is None:
        sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
        sc.collection.objects.link(sun)
    sun.data.energy, sun.data.angle, sun.data.color = 3.6, math.radians(1.5), (1.0, 0.97, 0.92)
    sun.rotation_euler = stage.look_rot(Vector((-6.0, 4.0, 7.0)), Vector((0, 0, 0)))
    bpy.ops.mesh.primitive_plane_add(size=400, location=(40, 0, 0))
    gnd = bpy.context.active_object
    gnd.data.materials.append(W.principled("ld_asphalt", (0.07, 0.07, 0.075), 0.85))
    cam = stage.camera("cam", 28)
    sc.collection.objects.link(cam) if cam.name not in sc.collection.objects else None
    sc.camera = cam
    for i, kind in enumerate(KINDS):
        cc = V.make(kind, "ld_" + kind, COLORS.get(kind) or (0.5, 0.5, 0.52), "F LD %d" % (100 + i), c=lib)
        r = motion.rig(cc, c=traffic)
        x0 = i * 14.0
        r.obj.location = (x0, 0.0, 0.0)
        md = r.md
        lo, hi = md["lo"], md["hi"]
        Lv, Wv, Hv = hi.y - lo.y, hi.x - lo.x, hi.z
        d = 1.9 * Hv + 1.6
        # rear corner close-up: the left rear corner at tail-lamp height (same frame for either kit)
        zt = V.KINDS[kind]["stations"][0][3] - 0.06 if kind in V.KINDS else 0.3 * Hv
        views = [
            (Vector((x0 - 0.25 * Wv, hi.y - 0.9 - 0.08 * Lv, 0.45 * Hv)), Vector((-0.75, 1.0, 0.18)), d, 28),
            (Vector((x0 - 0.25 * Wv, lo.y + 0.9 + 0.08 * Lv, 0.45 * Hv)), Vector((-0.75, -1.0, 0.2)), d, 28),
            (Vector((x0 - 0.36 * Wv, lo.y + 0.16, zt)), Vector((-0.9, -1.0, 0.35)), 1.9, 35),
            (Vector((x0 - 0.3 * Wv, hi.y - 0.16, 0.45 * Hv)), Vector((-0.8, 1.0, 0.3)), 1.9, 35)]
        for v, (tgt, dirn, dist, lens) in enumerate(views):
            f = 1 + 3 * i + v if v < 3 else 1 + 3 * len(KINDS) + i
            pos = tgt + dirn.normalized() * dist
            cam.location = pos
            cam.rotation_euler = stage.look_rot(pos, tgt)
            cam.keyframe_insert("location", frame=f)
            cam.keyframe_insert("rotation_euler", frame=f)
            cam.data.lens = lens
            cam.data.keyframe_insert("lens", frame=f)
            lit = v >= 2
            for u in r.units.values():
                key(u, "brake", f, 1.0 if v == 2 else 0.0)
            for lp in r.lamps.values():
                key(lp, "ind_l", f, motion.IND_ON if lit else 0.0)
        print("built", kind, "L %.2f W %.2f H %.2f" % (Lv, Wv, Hv), flush=True)
    for o in [cam, cam.data] + [o for o in bpy.data.objects if o.animation_data]:
        constant(o)
    sc.frame_start, sc.frame_end = 1, 4 * len(KINDS)
    stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)), motion_blur=False)
    os.makedirs(OUT, exist_ok=True)
    for f in STILLS or list(range(1, 4 * len(KINDS) + 1)):
        sc.frame_set(f)
        sc.render.filepath = os.path.join(OUT, f"f_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("Saved", sc.render.filepath, flush=True)


main()
print("RENDER_DONE")
