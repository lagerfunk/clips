"""Look-dev stills for the vehicle kit and kit/motion.py, golden hour.
  --shot lineup    every kind in the town street, fronts and rears, low three-quarter view, 50 mm (frame 1)
  --shot brake     estate braking for a right turn, right indicator on, wheels blurred by their spin; the camera
                   travels with the car (frame 70)
  --shot autobahn  the bus overtaking the lorry with drawbar trailer, tracking shot from the left lane (frame 60)
Run: python lookdev/ld_vehicles.py OUT --stills 70 --res 720 --samples 48 --assets ASSETS --shot brake
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import jx  # noqa: E402
import motion  # noqa: E402
import stage  # noqa: E402
import vehicles as V  # noqa: E402

OUT, RES, SAMPLES, ASSETS, STILLS, SHOT = "frames", 720, 48, "assets", None, "lineup"
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
FPS = 30
N = 120


def golden(sun_color=(1.0, 0.6, 0.34), energy=4.4, ambient=0.6, exposure=0.0):
    """Late-afternoon grade on top of stage.sky: warm low sun, the HDRI tinted warm at the horizon and cooler at the
    zenith (camera rays only), a weaker and warmer fill."""
    sc = bpy.context.scene
    sun = bpy.data.objects["sun"].data
    sun.color, sun.energy = sun_color, energy
    sun.angle = math.radians(1.0)
    nt = sc.world.node_tree
    env = next(n for n in nt.nodes if n.type == "TEX_ENVIRONMENT")
    bg = nt.nodes["Background"]
    tc = next(n for n in nt.nodes if n.type == "TEX_COORD")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (1.0, 0.66, 0.42, 1)
    ramp.color_ramp.elements[1].position = 0.45
    ramp.color_ramp.elements[1].color = (0.78, 0.84, 1.0, 1)
    ramp.color_ramp.elements.new(0.12).color = (1.0, 0.8, 0.62, 1)
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    ins = [s for s in mix.inputs if s.type == "RGBA"]
    nt.links.new(env.outputs["Color"], ins[0])
    nt.links.new(ramp.outputs["Color"], ins[1])
    nt.links.new([s for s in mix.outputs if s.type == "RGBA"][0], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.85
    amb = [n for n in nt.nodes if n.type == "BACKGROUND" and n != bg][0]
    amb.inputs["Strength"].default_value = ambient
    g = next(n for n in nt.nodes if n.type == "VALTORGB" and n != ramp)
    els = sorted(g.color_ramp.elements, key=lambda e: e.position)      # ground, horizon, zenith
    for el, col in zip(els, ((0.2, 0.15, 0.11, 1), (0.95, 0.76, 0.6, 1), (0.42, 0.5, 0.72, 1))):
        el.color = col
    sc.view_settings.exposure = exposure


def finish(cam, frames, haze=(0.86, 0.72, 0.58), dist=900.0, skip=()):
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, N
    stage.hazify_all(color=haze, dist=dist, skip=skip)
    stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
    os.makedirs(OUT, exist_ok=True)
    for f in frames:
        sc.frame_set(f)
        sc.render.filepath = os.path.join(OUT, f"f_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("Saved", sc.render.filepath, flush=True)


def prebuild(specs, built):
    """Build vehicles right after the empty scene and its "lib" collection exist, before the town or motorway:
    operators and depsgraph bakes get slow in a big scene. specs: [(key, kind, colour, plate, kwargs)]."""
    import world as W
    orig = W.coll

    def coll(name, parent=None, hide=False):
        c = orig(name, parent, hide)
        if name == "traffic" and not built:
            lib = bpy.data.collections["lib"]
            for key, kind, col, plate, kw in specs:
                built[key] = V.make(kind, key, col, plate, c=lib, **dict(kw))
        return c
    W.coll = coll


def still_cam(name, lens, pos, tgt):
    co = stage.camera(name, lens)
    co.location = pos
    co.rotation_euler = stage.look_rot(Vector(pos), Vector(tgt))
    return co


# ---------------------------------------------------------------------------------------------------- line-up
def lineup():
    import townstage as TS
    # east arm of the east-west street: westbound (north lane, y = +1.5) face the camera, eastbound show their rears
    # and wait with the brake lights on
    # tall vehicles at the far end and in alternate lanes, so the raised camera sees every one of them whole
    north = [("hatch", (0.5, 0.035, 0.02), "WI LK 204", 13.5, 0.3), ("police", None, "F 3318", 20.5, 0.0),
             ("suv", (0.82, 0.83, 0.84), "F SB 902", 27.5, 0.1), ("artic", (0.04, 0.12, 0.35), "F TR 401", 49.0, 0.2)]
    south = [("estate", (0.02, 0.07, 0.2), "KA RS 41", 15.5, 0.5), ("saloon", (0.015, 0.016, 0.018), "DA KE 9", 22.5, 0.45),
             ("van", (0.86, 0.87, 0.88), "HU BB 330", 30.0, 0.0), ("bus", (0.86, 0.84, 0.76), "F VB 112", 41.0, 0.0),
             ("drawbar", (0.85, 0.86, 0.87), "F GZ 260", 69.0, 0.0)]
    specs, place = [], []
    for side, lst in ((1, north), (-1, south)):
        for kind, col, plate, x, metal in lst:
            kw = {}
            if kind in V.KINDS:
                kw["metal"] = metal
            if kind == "artic":
                kw["trailer_color"] = (0.04, 0.12, 0.35)
            if kind == "drawbar":
                kw["label"] = "NORDFRACHT"
            specs.append((f"lu_{kind}", kind, col or (0.5, 0.5, 0.5), plate, tuple(kw.items())))
            place.append((f"lu_{kind}", kind, side, x))
    built = {}
    prebuild(specs, built)
    S = TS.build(ASSETS, "plain", seed=6, parked=False)
    traffic = S["traffic"]
    for key, kind, side, x in place:
        r = motion.rig(built[key], c=traffic)
        yaw = math.pi if side > 0 else 0.0
        # each vehicle stands on its middle x, 1.5 m from the centre line; the rears wait with the brake lights on,
        # the police car with its blue lights going
        tr = [dict(x=x, y=side * 1.5, z=0.0, yaw=yaw, v=0.0, ind=None, beacon=kind == "police") for _ in range(N)]
        if side < 0 or kind == "police":
            motion.bake(r, tr)
        else:
            motion.park(r.obj, x, side * 1.5, yaw)
        print("lineup", kind, round(r.md["length"], 2), flush=True)
    # sun low in the south: it lights the south sides the camera sees and throws long shadows across the street
    TS.light(sun_az_deg=252.0, sun_elev_deg=9.0, assets=ASSETS)
    golden(energy=5.0, ambient=0.55)
    # raised three-quarter view over the junction (first-floor window height and up): the street runs up the
    # portrait frame, near cars big at the bottom, lorries and bus further up, golden sky at the top
    cam = still_cam("cam_lineup", 32, (5.0, -5.5, 6.0), (30.0, 0.5, 0.0))
    finish(cam, STILLS or [1])


# ---------------------------------------------------------------------------------------------------- braking
def brake():
    import townstage as TS
    S = TS.build(ASSETS, "plain", seed=4, parked=False,
                 heroes=[("estate", (0.02, 0.07, 0.2), "hero", "KA RS 41", 0.6)])
    car = S["heroes"]["hero"]
    path = jx.lane_path("S", "right")
    # 50 km/h, braking from 1.4 s for the right turn (3 m/s2); at frame 70 about 40 km/h: the spokes smear
    sv = jx.kinematics(20.0, 13.9, [(0, "cruise", 13.9), (1.4, "cruise", 4.0)], N)
    jx.blink(car, "R", 0.2, 6.0)
    jx.drive(car, path, sv, list(range(1, N + 1)))
    st = car["rig"].states
    f = (STILLS or [70])[0]
    print("frame", f, "v %.2f" % sv[f - 1][1], "brake", st["brake"][f - 1], "ind R", st["right"][f - 1], flush=True)
    co = stage.camera("cam_brake", 35)
    locs, rots = [], []
    for i in range(N):
        x, y, _z = car["track"][i]
        pos = Vector((x + 2.3, y - 7.4, 0.85))          # low, behind the right rear corner, travelling with the car
        locs.append(tuple(pos))
        rots.append(tuple(stage.look_rot(pos, Vector((x - 0.25, y + 1.0, 0.8)))))
    stage.bake_motion(co, list(range(1, N + 1)), locs, rots)
    TS.light(sun_az_deg=60.0, sun_elev_deg=7.0, assets=ASSETS)
    golden(sun_color=(1.0, 0.55, 0.3), energy=5.2, ambient=0.7, exposure=0.4)
    finish(co, STILLS or [70])


# ---------------------------------------------------------------------------------------------------- Autobahn
def autobahn():
    specs = [("ab_drawbar", "drawbar", (0.85, 0.86, 0.87), "F GZ 260", (("label", "NORDFRACHT"),)),
             ("ab_bus", "bus", (0.86, 0.84, 0.76), "F VB 112", ()),
             ("ab_estate", "estate", (0.5, 0.035, 0.02), "OF LE 45", (("metal", 0.3),)),
             ("ab_artic", "artic", (0.04, 0.12, 0.35), "F TR 401", (("trailer_color", (0.04, 0.12, 0.35)),)),
             ("ab_hatch", "hatch", (0.55, 0.57, 0.6), "MZ AK 77", ()),
             ("ab_van", "van", (0.86, 0.87, 0.88), "HU BB 330", (("metal", 0.0),)),
             ("opp_suv", "suv", (0.06, 0.08, 0.07), "MA XY 5", ()),
             ("opp_saloon", "saloon", (0.82, 0.83, 0.84), "HD UL 66", (("metal", 0.1),)),
             ("opp_artic", "artic", (0.85, 0.86, 0.87), "F AK 77", (("label", "ALPENKURIER"),))]
    built = {}
    prebuild(specs, built)
    W_ = stage.build_world(ASSETS, s0=60.0, s1=2400.0, gantry_s=430.0, bridge_s=610.0, phone_s=238.0)
    road, traffic = W_["road"], W_["traffic"]

    def track(s0, x, v, n=N, ind=None):
        out = []
        for i in range(n):
            s = s0 + v * i / FPS
            c, th, fwd, right, sl = road.frame(s)
            p = road.point(s, x)
            out.append(dict(x=p.x, y=p.y, z=p.z, yaw=math.pi / 2 - th, pitch=math.atan(sl), v=v,
                            ind=ind(i) if callable(ind) else ind))
        return out

    F = 60
    vt, vb, vc = 22.2, 27.8, 33.0              # lorry 80 km/h, bus 100 km/h (Tempo 100 approval), cars 120 km/h
    # lanes from the motorway centre: 4.625 left, 8.375 middle, 12.125 right; lorries keep right
    for key, x, v, s_at_f in (("ab_drawbar", 12.125, vt, 474.0), ("ab_bus", 8.375, vb, 480.5),
                              ("ab_estate", 4.625, vc, 446.0), ("ab_artic", 12.125, vt, 440.0),
                              ("ab_hatch", 8.375, 30.0, 452.0), ("ab_van", 12.125, vt, 416.0)):
        r = motion.rig(built[key], c=traffic)
        motion.bake(r, track(s_at_f - v * (F - 1) / FPS, x, v))
    # oncoming carriageway
    for key, x, s_at_f in (("opp_suv", -8.375, 470.0), ("opp_saloon", -4.625, 420.0), ("opp_artic", -12.125, 440.0)):
        kind = key[4:]
        r = motion.rig(built[key], c=traffic)
        v = 30.0 if kind != "artic" else 22.2
        tr = []
        for i in range(N):
            s = s_at_f - v * (i - F + 1) / FPS
            c, th, fwd, right, sl = road.frame(s)
            p = road.point(s, x)
            tr.append(dict(x=p.x, y=p.y, z=p.z, yaw=-math.pi / 2 - th, pitch=-math.atan(sl), v=v, ind=None))
        motion.bake(r, tr)
    # tracking camera over the left lane, ahead of the bus and moving with it, looking back: the bus overtaking in
    # the middle lane close to camera, the lorry with its drawbar trailer beside and behind it in the right lane
    co = stage.camera("cam_ab", 35)
    locs, rots = [], []
    for i in range(N):
        s_cam = 480.5 + 6.0 + 13.5 + vb * (i - F + 1) / FPS
        s_tgt = 478.0 + vb * (i - F + 1) / FPS
        pos = road.point(s_cam, 3.0, 2.3)
        tgt = road.point(s_tgt, 10.2, 1.5)
        locs.append(tuple(pos))
        rots.append(tuple(stage.look_rot(pos, tgt)))
    stage.bake_motion(co, list(range(1, N + 1)), locs, rots)
    c, th, fwd, right, sl = road.frame(490.0)
    # sun low on the left of the traffic and a little ahead: fronts and the left sides the camera sees are lit,
    # the shadows fall back across the lanes to the right
    stage.sky(road, (-fwd * 0.4 + right * 0.92).normalized(), ASSETS, sun_elev_deg=8.0, sun_energy=4.6)
    golden(energy=4.8, ambient=0.6)
    finish(co, STILLS or [F], dist=2400.0)


{"lineup": lineup, "brake": brake, "autobahn": autobahn}[SHOT]()
print("RENDER_DONE")
