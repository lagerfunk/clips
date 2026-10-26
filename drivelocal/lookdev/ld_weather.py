"""Look-dev stills for the weather module (kit/weather.py).
    python ld_weather.py OUT --stills 30 --res 720 --samples 48 --assets ASSETS --shot rain|night|snow [--preset P]
    --shot rain   Autobahn in rain, camera tracking low behind a truck at 80 km/h: wheel spray, wet road, lights
    --shot night  town junction at night from the corner footway: street lamps, low beams, lit windows
    --shot snow   Autobahn in snow from the hard shoulder, traffic coming towards the camera: falling snow, slush,
                  icy wheel tracks, 300 m visibility
    --timing      still k renders preset weather.PRESETS[(k - 1) % 7] at frame 30 (render-time table); use
                  1..8: still 8 renders day again once the scene is warm, the fair baseline
    --cache F     (local only) save the built stage to F and reuse it on the next run
"""
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "kit"), os.path.join(HERE, "kit"), HERE]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import stage  # noqa: E402
import weather  # noqa: E402

OUT, RES, SAMPLES, ASSETS, STILLS = "frames", 720, 16, "assets", [30]
SHOT, PRESET, TIMING, CACHE = "rain", None, False, None
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
        STILLS = list(range(int(p), int(q) + 1))
    if x == "--shot":
        SHOT = a[i + 1]
    if x == "--preset":
        PRESET = a[i + 1]
    if x == "--timing":
        TIMING = True
    if x == "--cache":
        CACHE = a[i + 1]

FPS = 30
N = 45
TOWN = SHOT == "night"
DEFAULT_PRESET = {"rain": "rain", "night": "night", "snow": "snow+ice"}[SHOT]


def unwrap(rots):
    out = [tuple(rots[0])]
    for r in rots[1:]:
        r = list(r)
        for j in range(3):
            while r[j] - out[-1][j] > math.pi:
                r[j] -= 2 * math.pi
            while r[j] - out[-1][j] < -math.pi:
                r[j] += 2 * math.pi
        out.append(tuple(r))
    return out


def put(coll, name, c):
    e = bpy.data.objects.new(name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = coll
    c.objects.link(e)
    return e


def build_autobahn():
    S = stage.build_world(ASSETS, s0=60.0, s1=2400.0, gantry_s=470.0, bridge_s=700.0, phone_s=238.0)
    road = S["road"]
    cars, vans, trucks = stage.fleet(S["lib"])
    S["fleet"] = {**cars, **vans, **trucks}
    c0, th, fwd, right, _ = road.frame(300)
    stage.sky(road, fwd * 0.3 + right * 0.9, ASSETS, sun_elev_deg=34.0)
    return S


def build_town():
    import townstage as TS
    S = TS.build(ASSETS, "plain", seed=4)
    TS.light(assets=ASSETS)
    S["fleet"] = {**S["cars"], **S["vans"]}
    return S


def scene_autobahn(S):
    road, F, tr = S["road"], S["fleet"], S["traffic"]
    frames = list(range(1, N + 1))

    def drive(key, s0, x, v, name):
        o = put(F[key], name, tr)
        locs, rots = [], []
        for f in frames:
            t = (f - 1) / FPS
            s = s0 + v * t
            yaw = 0.0 if v >= 0 else math.pi
            M = road.matrix(s, x, 0.0, yaw)
            locs.append(tuple(M.translation))
            rots.append(tuple(M.to_euler()))
        stage.bake_motion(o, frames, locs, unwrap(rots))
        return o

    def cam_track(fn, lens):
        cam = stage.camera("cam", lens)
        locs, rots = [], []
        for f in frames:
            pos, tgt = fn((f - 1) / FPS)
            locs.append(tuple(pos))
            rots.append(tuple(stage.look_rot(pos, tgt)))
        stage.bake_motion(cam, frames, locs, unwrap(rots))
        bpy.context.scene.camera = cam
        return cam

    if SHOT == "rain":
        # low chase camera in the middle lane, a lorry ahead on the right throwing spray, oncoming lights across
        # the median, the wet lane mirroring tail lights back at us
        v = 22.2                                      # 80 km/h
        s_t = 300.0                                   # lorry centre at frame 1
        drive("t_nord", s_t, 12.125, v, "truck")
        drive("hatch_red", s_t + 34, 12.125, v, "car_right")
        drive("estate_grey", s_t + 52, 8.375, 24.0, "car_mid")
        drive("t_blue", s_t + 110, 12.125, v, "truck2")
        drive("saloon_black", s_t + 140, 4.625, 31.0, "car_left")
        drive("suv_white", s_t + 30, -8.375, -30.0, "onc1")
        drive("estate_blue", s_t + 75, -4.625, -34.0, "onc2")
        drive("t_white", s_t + 120, -12.125, -24.0, "onc3")

        def fn(t):
            s = s_t + v * t
            return road.point(s - 21.0, 7.2, 0.85), road.point(s + 14.0, 9.6, 1.6)
        cam_track(fn, 35)
    else:
        # snow: low camera on the hard shoulder, traffic comes towards it through the falling snow; the low sun
        # sits behind the traffic, so the glazed wheel tracks flare up (the black-ice sheen of the episode)
        s_c = 330.0                                   # camera station; at frame 30 (1 s):
        drive("estate_blue", s_c - 58, 8.375, 22.0, "car_mid")       # 36 m away in the middle lane
        drive("t_alpen", s_c - 90, 12.125, 19.0, "truck")            # lorry 71 m away on the right
        drive("hatch_silver", s_c - 125, 8.375, 22.0, "car_mid2")
        drive("suv_dark", s_c - 175, 4.625, 25.0, "car_left")
        drive("van_white", s_c - 210, 12.125, 20.0, "van")
        drive("saloon_white", s_c - 40, -8.375, -22.0, "onc1")

        def fn(t):
            return road.point(s_c, 14.1, 1.7), road.point(s_c - 70.0, 6.4, 0.3)
        cam_track(fn, 45)
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, N


def scene_town(S):
    F, tr = S["fleet"], S["traffic"]
    frames = list(range(1, N + 1))

    def drive(key, p0, d, v, name):
        o = put(F[key], name, tr)
        rz = math.atan2(d[1], d[0]) - math.pi / 2
        locs = [(p0[0] + d[0] * v * (f - 1) / FPS, p0[1] + d[1] * v * (f - 1) / FPS, 0.0) for f in frames]
        stage.bake_motion(o, frames, locs, [(0.0, 0.0, rz)] * len(frames))
        return o

    # low view up the north-south street behind a car: its low beams on the damp asphalt ahead, two lamp pools,
    # an oncoming car with its lights in our eyes, a car crossing at the junction, lit windows on both sides
    drive("suv_white", (1.5, -27.0), (0, 1), 6.0, "car_n")          # northbound ahead of the camera
    drive("estate_blue", (-1.5, 30.0), (0, -1), 6.5, "car_s")       # southbound, headlights towards the camera
    drive("hatch_red", (14.0, 1.5), (-1, 0), 6.0, "car_w")          # westbound across the junction
    cam = stage.camera("cam", 35)
    pos, tgt = Vector((1.3, -36.5, 1.3)), Vector((0.9, 0.0, 1.9))   # in the lane (manhole at -0.5, -31 out of frame)
    cam.location = pos
    cam.rotation_euler = stage.look_rot(pos, tgt)
    bpy.context.scene.camera = cam
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, N


t0 = time.time()
if CACHE and os.path.exists(CACHE):
    # the cache holds the built, lit, hazed stage only; the shot (traffic, camera) is set up fresh every run
    bpy.ops.wm.open_mainfile(filepath=CACHE)
    import world as W
    names = bpy.context.scene["ld_fleet"].split(",")
    S = dict(fleet={n: bpy.data.collections[n] for n in names}, traffic=bpy.data.collections["traffic"])
    if not TOWN:
        S["road"] = W.Road(length=2400.0)
else:
    S = build_town() if TOWN else build_autobahn()
    stage.hazify_all(dist=900.0 if TOWN else 2600.0)
    stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
    bpy.context.scene.render.fps = FPS
    bpy.context.scene["ld_fleet"] = ",".join(S["fleet"])
    if CACHE:
        bpy.ops.wm.save_as_mainfile(filepath=CACHE)
(scene_town if TOWN else scene_autobahn)(S)
sc = bpy.context.scene
sc.cycles.samples = SAMPLES
sc.render.resolution_x, sc.render.resolution_y = RES, int(round(RES * 16 / 9))
sc.render.use_stamp_render_time = True
print(f"BUILD {time.time() - t0:.1f}s", flush=True)

if os.environ.get("LD_SETUP_ONLY"):           # profiling scripts set the shot up and render variants themselves
    STILLS = []
else:
    os.makedirs(OUT, exist_ok=True)
for k in STILLS:
    preset = weather.PRESETS[(k - 1) % len(weather.PRESETS)] if TIMING else (PRESET or DEFAULT_PRESET)
    f = 30 if TIMING else k
    sc.frame_set(f)
    t1 = time.time()
    kw = {}
    if SHOT == "snow" and not TIMING:
        # sun low and straight down the carriageway behind the oncoming traffic: the glare on the ice faces us
        c0, th, fwd, right, _ = S["road"].frame(270.0)
        kw["sun_azimuth"] = math.degrees(math.atan2(-fwd.y, -fwd.x))
        kw["visibility"] = 650.0             # snowing, but lanes, posts and the next lorry still read on a phone
    P = weather.apply(preset, seed=3, **kw)
    ta = time.time() - t1
    sc.frame_set(f)
    sc.render.filepath = os.path.join(OUT, f"f_{k:04d}.png")
    t2 = time.time()
    bpy.ops.render.render(write_still=True)
    tr_ = time.time() - t2
    print(f"RENDER_DONE {SHOT} {preset} frame {f} apply {ta:.1f}s render {tr_:.1f}s counts {P.get('counts')}",
          flush=True)
    print("Saved", sc.render.filepath, flush=True)
