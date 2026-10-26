"""Look-dev stills for the interchange kit (kit/interchange.py) with SUMO traffic (traffic/interchange_day.json.gz),
late-afternoon light.
  --shot drone   the whole northbound on-ramp from above: loop, acceleration lane, merging cars, bridge (frame 300)
  --shot driver  driver eye level about 500 m before the exit: Vorwegweiser 449, the Baken further on, a car
                 ahead moving back to the right lane (frame 220)
  --shot gore    driver eye in the exit lane where it splits: Abfahrtslinie, 0.50 m edge strip, hatched gore, exit
                 boards 333 and 332, orange reflectors, a car leaving with its indicator on (frame 1456)
Frames are track frames (30 fps); traffic is baked from 30 frames before the still so lamps and steering settle.
Run: python lookdev/ld_interchange.py OUT --stills 300 --res 720 --samples 48 --assets ASSETS --shot drone
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import interchange as IC  # noqa: E402
import stage  # noqa: E402
import traffic as TR  # noqa: E402

OUT, RES, SAMPLES, ASSETS, STILLS, SHOT = "frames", 720, 48, "assets", None, "drone"
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
    if x == "--shot":
        SHOT = a[i + 1]
LAND = "--no-land" not in a
TRACK = os.path.join(HERE, "..", "traffic", "interchange_day.json.gz")

# shot: camera position, target, lens (mm), light direction (where the sunlight travels), sun elevation, f-stop,
# focus distance (m; None: no depth of field), default frame
SHOTS = {
    "drone": dict(pos=(88.0, -395.0, 78.0), tgt=(28.0, -85.0, 0.0), lens=24.0, light=(0.55, 0.8, -0.3), elev=17.0,
                  fstop=None, focus=None, frame=300),
    "driver": dict(pos=(12.1, -1478.0, 1.22), tgt=(14.5, -1100.0, 1.8), lens=45.0, light=(0.45, 0.88, -0.25),
                   elev=13.0, fstop=None, focus=None, frame=220, tufts=((26.0, -1440.0), 60.0)),
    "gore": dict(pos=(16.2, -634.0, 1.35), tgt=(17.6, -560.0, 1.9), lens=40.0, light=(0.45, 0.88, -0.25), elev=12.0,
                 fstop=2.8, focus=72.0, frame=1456, tufts=((26.0, -592.0), 60.0)),
}


def golden(sun_color=(1.0, 0.68, 0.42), energy=4.4, ambient=0.66):
    """Late-afternoon light on top of stage.sky: a warm low sun and a slightly warmer fill. The sky picture the
    camera sees stays as in the approved Autobahn episodes (no tint), and the distance haze stays cool and light."""
    sc = bpy.context.scene
    sun = bpy.data.objects["sun"].data
    sun.color, sun.energy = sun_color, energy
    sun.angle = math.radians(1.0)
    nt = sc.world.node_tree
    bg = nt.nodes["Background"]
    amb = [n for n in nt.nodes if n.type == "BACKGROUND" and n != bg][0]
    amb.inputs["Strength"].default_value = ambient
    g = next(n for n in nt.nodes if n.type == "VALTORGB")
    els = sorted(g.color_ramp.elements, key=lambda e: e.position)
    for el, col in zip(els, ((0.18, 0.15, 0.12, 1), (0.88, 0.8, 0.72, 1), (0.36, 0.48, 0.76, 1))):
        el.color = col


def main():
    sh = SHOTS[SHOT]
    frames = STILLS or [sh["frame"]]
    S = IC.build(ASSETS, fleet=True, landscape=LAND)
    if sh.get("tufts") and LAND:
        IC.verge_tufts(S["ground"], S["lib"], S["env"], *sh["tufts"])
    sc = bpy.context.scene
    sc.render.fps = 30
    sc.frame_start, sc.frame_end = 1, 1800
    cam = stage.camera("cam_" + SHOT, sh["lens"])
    cam.location = sh["pos"]
    cam.rotation_euler = stage.look_rot(Vector(sh["pos"]), Vector(sh["tgt"]))
    if sh["fstop"]:
        cam.data.dof.use_dof = True
        cam.data.dof.aperture_fstop = sh["fstop"]
        cam.data.dof.focus_distance = sh["focus"]
    sc.camera = cam
    stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))     # portrait frame first: TR.in_view uses it
    bpy.context.view_layer.update()
    data = TR.load(TRACK)
    keep = TR.in_view(cam, margin=0.2, max_dist=1400.0 if SHOT != "drone" else 900.0)
    lo, hi = max(1, min(frames) - 30), min(data["frames"], max(frames) + 4)
    rigs = TR.play(data, S["fleet"], S["traffic"], frames=(lo, hi), keep=keep)
    print("traffic", len(rigs), "vehicles", flush=True)
    stage.sky(S["road"], Vector(sh["light"]).normalized(), ASSETS, sun_elev_deg=sh["elev"], sun_energy=4.6)
    golden()
    stage.hazify_all(dist=3200.0 if SHOT == "drone" else 2600.0)       # episode 1 haze: cool and light
    sc.view_settings.exposure = 0.1
    os.makedirs(OUT, exist_ok=True)
    for f in frames:
        sc.frame_set(f)
        sc.render.filepath = os.path.join(OUT, f"f_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("Saved", sc.render.filepath, flush=True)
    print("signs:", sorted({v.get("title", k[1]) for k, v in IC_sources().items()}), flush=True)


def IC_sources():
    import signs as SG
    return SG.sources_used()


if __name__ == "__main__":
    main()
    print("RENDER_DONE", flush=True)
