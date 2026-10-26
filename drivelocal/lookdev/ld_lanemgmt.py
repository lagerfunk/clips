"""Look-dev stills for lane management, roadworks and enforcement on the approved episode 1 Autobahn stage.
One world holds all three features; --shot picks the camera and the traffic for that still.
  gantry   driver eye level 29 m before an LED gantry: 80 on two lanes, red X over the left lane, Zeichen 123 above
  taper    drone over the roadworks taper: yellow lines, Leitbaken with chase lamps, the left lane drop (zipper
           merge) and the mobile barrier with its flashing arrow
  trailer  low three-quarter view of the speed trailer on the verge, traffic passing, a subtle flash
Run: python ld_lanemgmt.py OUTDIR --stills 30 --res 720 --samples 48 --assets ASSETS --shot gantry [--stub]
--stub (local previews only): signs missing from ASSETS/signs become TEST STUB pictures. Never for stills.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "kit"), os.path.join(HERE, "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import enforcement as EN  # noqa: E402
import jx  # noqa: E402
import lanemgmt as LM  # noqa: E402
import roadworks as RW  # noqa: E402
import stage  # noqa: E402

OUT, RES, SAMPLES, ASSETS, FR, STILLS, SHOT, STUB, BLEND = "frames", 720, 48, "assets", None, None, "gantry", False, None
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
    if x == "--stub":
        STUB = True
    if x == "--blend":            # also save the built scene (camera iterations without a rebuild)
        BLEND = a[i + 1]

FPS, F = 30, 30                # the still is frame 30 (1 s into the motion)
N = 60
G_S = 560.0                    # LED gantry (next one 1,750 m on)
BRIDGE_S = 860.0
TRAILER_S = 1170.0
RW_S = 1500.0                  # taper start
LANE = {1: 4.625, 2: 8.375, 3: 12.125}

S = stage.build_world(ASSETS, s0=40.0, s1=2400.0, gantry_s=0, bridge_s=BRIDGE_S, phone_s=0)
road, lib, env, traffic, M = S["road"], S["lib"], S["env"], S["traffic"], S["M"]
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, N
LM.setup(ASSETS, allow_stub=STUB)

# ---------------------------------------------------------------- lane management, roadworks, enforcement
gantries = LM.gantry_series(road, M, env, lib, G_S, 2400.0, spacing=1750.0)
for g in gantries:
    g.show(1, speed=80, signals={0: "X"}, warn={1: "123", 2: "123"})
plan = [(800.0, [("123", 1.26), ("1004-800", 0.84)]), (400.0, [("531-11", 1.6)]), (200.0, [("274-80", 0.75)])]
rw = RW.RoadWorks(road, M, env, lib, s_taper=RW_S, road_s0=40.0, strict=False, signs=plan)   # right lane closed
rw.flash(1, N)
trailer = EN.SpeedTrailer(road, env, TRAILER_S)
trailer.flash(F)
EN.assert_no_section_control()

# ---------------------------------------------------------------- traffic
cars, vans, trucks = stage.fleet(lib)
POOL = dict(cars, **vans, **trucks)


def put(key, sv, xfun, reverse=False, ind=None, name=None):
    e = LM.instance(POOL[key], traffic, name or ("tr_" + key))
    tr = LM.road_track(road, sv, xfun, ind=ind, reverse=reverse)
    LM.bake(e, tr)
    return e


def sv_at(s_f, v, n=N, f=F):
    """(s, v) for frames 1..n so that the vehicle is at s_f on frame f (v in m/s, negative = towards -s)."""
    return [(s_f + v * (i + 1 - f) / FPS, abs(v)) for i in range(n)]


HERO = {"hatch_blue": ("hatch", (0.08, 0.22, 0.45)), "estate_green": ("estate", (0.05, 0.16, 0.1)),
        "saloon_black": ("saloon", (0.015, 0.016, 0.018)), "hatch_red": ("hatch", (0.5, 0.03, 0.02))}


def hero_merge(kind, color, name, plate, s_f, v, x0, x1, side):
    """A car changing lanes with its indicator on (blink phase chosen so the still frame shows it lit)."""
    h = jx.hero(kind, color, name, plate, lib, traffic)
    sv = sv_at(s_f, v)
    xf = (lambda s_: x0 + (x1 - x0) * LM.smoother((s_ - (s_f - v * 1.0)) / (v * 3.0)))
    LM.bake(h["obj"], LM.road_track(road, sv, xf))
    jx.blink(h, side, 0.3, 2.0)
    return h


c0, th0, fwd, right, _ = road.frame({"gantry": G_S, "taper": RW_S, "trailer": TRAILER_S}.get(SHOT, G_S))
if SHOT == "gantry":
    v = 22.2
    put("hatch_red", sv_at(G_S + 4.0, v), lambda s_: LANE[2])
    put("t_white", sv_at(G_S + 14.0, 21.5), lambda s_: LANE[3] + 0.1)
    put("suv_white", sv_at(G_S + 55.0, 22.6), lambda s_: LANE[3])
    put("estate_blue", sv_at(G_S + 75.0, 23.0), lambda s_: LANE[2])
    put("hatch_silver", sv_at(G_S + 140.0, 23.0), lambda s_: LANE[2] - 0.1)
    put("estate_green", sv_at(G_S + 190.0, 22.0), lambda s_: LANE[3])
    hero_merge("estate", (0.5, 0.52, 0.55), "merger", "QX MR 81", G_S - 15.0, 21.2, LANE[1], LANE[2] - 0.2, "R")
    put("suv_dark", sv_at(G_S - 21.5, 22.6), lambda s_: LANE[3] - 0.15)
    for key, s_f, x, vv in (("saloon_black", G_S + 40, -LANE[2], -33.0), ("estate_grey", G_S + 120, -LANE[1], -36.0),
                            ("van_white", G_S + 95, -LANE[3], -25.0), ("t_blue", G_S + 210, -LANE[3], -23.0)):
        put(key, sv_at(s_f, vv), lambda s_, x=x: x, reverse=True)
elif SHOT == "taper":
    # zipper merge at the end of the closed right lane: the merging cars (heroes, indicating left) slot in between
    # the cars of the middle lane one by one; the left lane flows past; trucks keep right until the zip
    sm = rw.s_merge
    order = [  # lane, s on the still frame, key
        (1, sm + 14.0, "estate_blue"), (1, sm - 8.0, "suv_white"), (1, sm - 30.0, "hatch_silver"),
        (1, sm - 52.0, "estate_grey"), (1, sm - 74.0, "saloon_white"),
        (2, sm - 18.0, "hatch_blue"), (2, sm - 41.0, "t_nord"), (2, sm - 66.0, "estate_green"),
        (2, sm - 88.0, "hatch_red"),
        (0, sm + 30.0, "suv_dark"), (0, sm - 20.0, "estate_blue"), (0, sm - 70.0, "van_white")]
    vz = 12.5                 # the queue rolls at about 45 km/h through the merge
    zc = [{"lane": ln, "s0": s_f - vz * (F - 1) / FPS, "v": vz} for ln, s_f, _k in order]
    tracks = rw.zipper(zc, n=N, v_zone=vz)
    for k, ((ln, s_f, key), tr) in enumerate(zip(order, tracks)):
        if ln == rw.closing and key in HERO:     # merging cars are heroes with their own indicators
            kind, col = HERO[key]
            h = jx.hero(kind, col, f"zip{k}", f"JX ZP {10 + k}", lib, traffic)
            LM.bake(h["obj"], tr)
            jx.blink(h, "L", 0.25, 2.0)
        else:
            LM.bake(LM.instance(POOL[key], traffic, f"tr{k}_{key}"), tr)
    for key, s_f, x, vv in (("t_alpen", 1560, -LANE[3], -23.0), ("hatch_red", 1620, -LANE[2], -33.0),
                            ("estate_blue", 1500, -LANE[1], -36.0)):
        put(key, sv_at(s_f, vv), lambda s_, x=x: x, reverse=True, name=f"opp_{key}")
elif SHOT == "trailer":
    for key, s_f, ln, vv in (("t_nord", TRAILER_S - 4.0, 3, 22.0), ("hatch_red", TRAILER_S + 22.0, 2, 26.0),
                             ("estate_blue", TRAILER_S + 6.0, 1, 33.0), ("suv_white", TRAILER_S + 48.0, 2, 25.0),
                             ("saloon_black", TRAILER_S + 70.0, 1, 34.0), ("van_white", TRAILER_S + 95.0, 3, 23.0)):
        put(key, sv_at(s_f, vv), lambda s_, ln=ln: LANE[ln])
    for key, s_f, x, vv in (("estate_grey", TRAILER_S + 60, -LANE[2], -30.0),
                            ("hatch_silver", TRAILER_S + 130, -LANE[1], -36.0),
                            ("t_blue", TRAILER_S + 110, -LANE[3], -23.0)):
        put(key, sv_at(s_f, vv), lambda s_, x=x: x, reverse=True)



def verge_grass(s0, s1, x0, x1, n=900, seed=3):
    """Foreground tufts of tall autumn grass on the verge (blade fans, two tones), for low camera shots."""
    import random
    rnd = random.Random(seed)
    mats = [LM.mat("ld_grass_a", (0.16, 0.24, 0.05), 0.8), LM.mat("ld_grass_b", (0.38, 0.33, 0.13), 0.85)]
    for mi, m_ in enumerate(mats):
        b_ = LM.MB()
        for _k in range(n // 2):
            s_, x_ = rnd.uniform(s0, s1), rnd.uniform(x0, x1)
            base = road.point(s_, x_, -0.13)
            for _j in range(rnd.randint(5, 9)):
                a_ = rnd.uniform(0, 2 * math.pi)
                h = rnd.uniform(0.12, 0.3) * (1.25 if mi else 1.0)
                lean = rnd.uniform(0.05, 0.3) * h
                w = 0.012
                tip = base + Vector((math.cos(a_) * lean, math.sin(a_) * lean, h))
                side = Vector((-math.sin(a_) * w, math.cos(a_) * w, 0))
                b_.poly([tuple(base - side), tuple(base + side), tuple(tip)])
        b_.obj(f"ld_verge_grass_{mi}", m_, env)


# ---------------------------------------------------------------- camera
UP = Vector((0, 0, 1))
if SHOT == "trailer":
    verge_grass(TRAILER_S - 15.0, TRAILER_S - 7.0, 19.6, 23.5, n=500)


def cam_keys(lens, pos_fn, tgt_fn, dof=None):
    co = stage.camera("cam_" + SHOT, lens)
    fr = list(range(1, N + 1))
    locs, rots = [], []
    for f in fr:
        p, t = pos_fn(f), tgt_fn(f)
        locs.append(tuple(p))
        rots.append(tuple(stage.look_rot(p, t)))
    stage.bake_motion(co, fr, locs, rots)
    if dof:
        co.data.dof.use_dof = True
        co.data.dof.focus_distance, co.data.dof.aperture_fstop = dof
    sc.camera = co
    return co


if SHOT == "gantry":
    vc = 22.2
    cam_keys(35, lambda f: road.point(G_S - 22.0 + vc * (f - F) / FPS, LANE[2] - 0.45, 1.2),
             lambda f: road.point(G_S + 170.0 + vc * (f - F) / FPS, LANE[2] - 0.75, 5.0))
    light = -(fwd * 0.93 + right * 0.37)     # low sun ahead-right: the gantry's shadow lies across the lanes
    elev = 18.0
elif SHOT == "taper":
    cam_keys(35, lambda f: road.point(RW_S - 26.0, 23.0, 12.0), lambda f: road.point(RW_S + 46.0, 10.8, 0.0))
    light = -(-fwd * 0.25 - right * 0.97)    # low sun from the left: Baken and cars cast long shadows to the right
    elev = 16.0
else:
    cam_keys(50, lambda f: road.point(TRAILER_S - 10.5, 21.4, 0.55), lambda f: road.point(TRAILER_S + 6.0, 14.2, 1.2),
             dof=(10.6, 4.0))
    light = -(fwd * 0.976 + right * 0.204)   # low sun ahead of the camera: rim light on the trailer, long shadows
    elev = 12.0

# ---------------------------------------------------------------- look and render
stage.sky(road, light, ASSETS, sun_elev_deg=elev, sun_energy=4.6)
stage.hazify_all(skip=tuple(m.name for m in bpy.data.materials if m.name.startswith(("lm_led", "en_flash", "rw_lamp"))))
stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))


def bloom():
    """Soft bloom so the LED units, lamps and the flash glow (Blender 5 compositor node group)."""
    ng = bpy.data.node_groups.new("ld_bloom", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    gl = ng.nodes.new("CompositorNodeGlare")
    for k, val in (("Type", "Bloom"), ("Quality", "High"), ("Threshold", 1.4), ("Strength", 0.28), ("Size", 0.55)):
        try:
            gl.inputs[k].default_value = val
        except (KeyError, TypeError, ValueError) as e:
            print("WARN bloom", k, e)
    out = ng.nodes.new("NodeGroupOutput")
    ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
    ng.links.new(gl.outputs["Image"], out.inputs[0])
    sc.compositing_node_group = ng
    sc.render.use_compositing = True


bloom()
if BLEND:
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(BLEND))
os.makedirs(OUT, exist_ok=True)
todo = STILLS or list(range(FR[0], FR[1] + 1)) if (STILLS or FR) else [F]
for f in todo:
    sc.frame_set(f)
    sc.render.filepath = os.path.join(OUT, f"f_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    print("Saved", sc.render.filepath, flush=True)
print("RENDER_DONE", SHOT, todo)
