"""Drive Like a Local #1, Germany: the Rettungsgasse (emergency corridor). 9:16, 30 fps, 840 frames (28 s).
Story: traffic brakes into a jam, everyone waits for the siren (wrong), top-down: left lane goes left, everyone else
goes right, the corridor opens, an ambulance and a fire engine drive through it.
Run: python ep01_rettungsgasse.py OUTDIR --frames 1-840 --res 720 --samples 24 --assets ASSETS [--stills 60,300]
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import stage  # noqa: E402
import vehicles as V  # noqa: E402
import world as W  # noqa: E402

OUT, RES, SAMPLES, ASSETS, FR, STILLS = "frames", 720, 24, "assets", (1, 840), None
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

FPS, N = 30, 840
T_FORM = 9.6          # corridor starts forming
RTW_T0, RTW_S0, RTW_V = 14.0, 120.0, 12.0
GAP_X = 6.45          # centre of the corridor
LANE = {1: 4.625, 2: 8.375, 3: 12.125}

S = stage.build_world(ASSETS, s0=40.0, s1=2400.0, gantry_s=470.0, bridge_s=690.0, phone_s=238.0)
road, lib, traffic = S["road"], S["lib"], S["traffic"]
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, N
cars, vans, trucks = stage.fleet(lib)
RTW = V.rtw(c=lib)
HLF = V.fire_engine(c=lib)
LEN = {k: V.KINDS[k]["L"] for k in V.KINDS}


def kind_len(key):
    if key.startswith("t_"):
        return 16.8
    if key.startswith("van"):
        return LEN["van"]
    for k in ("estate", "hatch", "saloon", "suv"):
        if key.startswith(k):
            return LEN[k]
    return 4.7


def smooth(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def smoother(u):
    u = min(1.0, max(0.0, u))
    return u * u * u * (u * (u * 6 - 15) + 10)


# ---------------------------------------------------------------- the jam
rnd = random.Random(7)
car_keys = list(cars)
jam = []
for lane in (1, 2, 3):
    s = 650.0
    rank = 0
    while s > 150.0:
        if lane == 3:
            key = rnd.choice(list(trucks)) if rnd.random() < 0.8 else ("van_white" if rnd.random() < 0.5 else rnd.choice(car_keys))
        else:
            key = "van_white" if rnd.random() < 0.08 else rnd.choice(car_keys)
        L = kind_len(key)
        sc_ = s - L / 2
        jam.append(dict(key=key, lane=lane, s=sc_, L=L, rank=rank))
        rank += 1
        gap = rnd.uniform(3.6, 5.0) if key.startswith("t_") else rnd.uniform(2.8, 3.8)
        s = sc_ - L / 2 - gap

V0 = {1: 31.0, 2: 27.0, 3: 22.0}
ACC = {1: 3.2, 2: 3.0, 3: 2.4}
for lane in (1, 2, 3):
    row = sorted([v for v in jam if v["lane"] == lane], key=lambda v: -v["s"])
    t_prev, f_prev = -1e9, -1e9
    for v in row:
        if v["s"] > 430:
            v["T"] = -1e9
        else:
            T = 1.8 + (430 - v["s"]) / 280 * 5.0 + rnd.uniform(-0.15, 0.15)
            v["T"] = max(T, t_prev + 0.06)
            t_prev = v["T"]
        f0 = T_FORM + 0.03 * v["rank"] + rnd.uniform(0, 0.15)
        v["F"] = max(f0, f_prev + 0.02)
        f_prev = v["F"]
        v["v0"] = V0[lane] * (22.0 / V0[lane] if v["key"].startswith("t_") else 1.0)
        v["a"] = 2.4 if v["key"].startswith("t_") else ACC[lane]
        tx = {1: 3.55, 2: 9.35, 3: 13.1}[lane]
        if v["key"].startswith("t_"):
            tx = 12.95
        elif v["key"].startswith("van") and lane == 2:
            tx = 9.3
        v["x1"] = tx

CREEP, DUR = 4.5, 2.2


def jam_state(v, t):
    """Road coordinate (s, x) and heading offset of a jam vehicle at time t."""
    sf, T, v0, acc = v["s"], v["T"], v["v0"], v["a"]
    if t >= T:
        s_ = sf
    else:
        dt = T - t
        tb = v0 / acc
        s_ = sf - 0.5 * acc * dt * dt if dt <= tb else sf - v0 * v0 / (2 * acc) - v0 * (dt - tb)
    tau = (t - v["F"]) / DUR
    x0 = LANE[v["lane"]]
    s_ += CREEP * smooth(tau)
    x_ = x0 + (v["x1"] - x0) * smoother(tau)
    return s_, x_


def rtw_s(t):
    return RTW_S0 + RTW_V * (t - RTW_T0)


def hlf_s(t):
    return rtw_s(t) - 26.0


def pose(s_, x_, yaw_off=0.0, flip=False):
    c, th, f, r, sl = road.frame(s_)
    p = c + r * x_
    yaw = -th + yaw_off + (math.pi if flip else 0.0)
    pitch = math.atan(sl) * (-1 if flip else 1)
    return (p.x, p.y, p.z), (pitch, 0.0, yaw)


frames = list(range(1, N + 1))
times = [(f - 1) / FPS for f in frames]


def animate(obj, state_fn, flip=False, max_yaw=0.2):
    locs, rots = [], []
    prev = None
    for t in times:
        s_, x_ = state_fn(t)
        if prev is None:
            s2, x2 = state_fn(t + 1 / FPS)
            ds, dx = s2 - s_, x2 - x_
        else:
            ds, dx = s_ - prev[0], x_ - prev[1]
        yaw_off = 0.0
        if abs(ds) + abs(dx) > 1e-4:
            yaw_off = -math.atan2(dx, max(abs(ds), 1e-4)) * (1 if not flip else -1)
            yaw_off = max(-max_yaw, min(max_yaw, yaw_off))
        prev = (s_, x_)
        l_, r_ = pose(s_, x_, yaw_off, flip)
        locs.append(l_)
        rots.append(r_)
    # smooth the heading a little (finite differences of eased paths are jumpy at rest)
    for k in range(1, len(rots) - 1):
        rots[k] = (rots[k][0], 0.0, (rots[k - 1][2] + rots[k][2] + rots[k + 1][2]) / 3)
    stage.bake_motion(obj, frames, locs, rots)


fleet_all = {**cars, **vans, **trucks}
for v in jam:
    e = bpy.data.objects.new(v["key"], None)
    e.instance_type = "COLLECTION"
    e.instance_collection = fleet_all[v["key"]]
    traffic.objects.link(e)
    animate(e, lambda t, v=v: jam_state(v, t), max_yaw=min(0.2, 0.9 / v["L"]))
print("jam vehicles", len(jam))

# opposite carriageway: free flow the other way
opp = []
for k in range(26):
    lane = rnd.choice((1, 2, 2, 3, 3, 3))
    key = rnd.choice(list(trucks)) if lane == 3 and rnd.random() < 0.7 else rnd.choice(car_keys)
    sp = {1: 38.0, 2: 33.0, 3: 24.0}[lane] * (24 / 33 if key.startswith("t_") else 1)
    s0 = 160 + k * 62 + rnd.uniform(-15, 15)
    e = bpy.data.objects.new("opp_" + key, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = fleet_all[key]
    traffic.objects.link(e)
    animate(e, lambda t, s0=s0, sp=sp, lane=lane: (s0 - sp * t, -LANE[lane]), flip=True)

for coll_, fn in ((RTW, rtw_s), (HLF, hlf_s)):
    e = bpy.data.objects.new(coll_.name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = coll_
    traffic.objects.link(e)
    animate(e, lambda t, fn=fn: (fn(t), GAP_X))

# ---------------------------------------------------------------- blue lights, brake lights
fa, fb = V.flash_mats()


def key_strength(m, pairs):
    inp = m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    for f, val in pairs:
        inp.default_value = val
        inp.keyframe_insert("default_value", frame=f)
    for fc in stage.fcurves(m.node_tree):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"


pa, pb = [(1, 0.3)], [(1, 0.3)]
f = int(12.0 * FPS)
on = True
while f <= N:
    pa.append((f, 14.0 if on else 0.3))
    pb.append((f, 0.3 if on else 14.0))
    on = not on
    f += 6
key_strength(fa, pa)
key_strength(fb, pb)
tail = bpy.data.materials["car_tail"]
tail.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 3.0

# ---------------------------------------------------------------- arrows and the corridor glow (top-down shot)
glow_m = bpy.data.materials.new("corridor_glow")
glow_m.use_nodes = True
nt = glow_m.node_tree
for n in list(nt.nodes):
    if n.type != "OUTPUT_MATERIAL":
        nt.nodes.remove(n)
em = nt.nodes.new("ShaderNodeEmission")
em.inputs["Color"].default_value = (1.0, 0.42, 0.04, 1)
em.inputs["Strength"].default_value = 2.0
tr = nt.nodes.new("ShaderNodeBsdfTransparent")
mx = nt.nodes.new("ShaderNodeMixShader")
nt.links.new(tr.outputs[0], mx.inputs[1])
nt.links.new(em.outputs[0], mx.inputs[2])
nt.links.new(mx.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
fac = mx.inputs[0]
# glow only where it explains (top-down and the final drone), off for the low shots
for f, val in ((1, 0.0), (int(12.9 * FPS), 0.0), (int(13.9 * FPS), 0.3), (450, 0.3), (451, 0.0), (630, 0.0),
               (631, 0.26)):
    fac.default_value = val
    fac.keyframe_insert("default_value", frame=f)
for fc in stage.fcurves(glow_m.node_tree):
    for kp in fc.keyframe_points:
        kp.interpolation = "LINEAR"
road.strip("corridor_glow", 4.85, 8.05, 130, 660, glow_m, S["env"], step=4.0, dz0=0.03)

arrow_y = bpy.data.materials.new("arrow_yellow")
arrow_y.use_nodes = True
ay = arrow_y.node_tree.nodes["Principled BSDF"]
ay.inputs["Base Color"].default_value = (1.0, 0.62, 0.0, 1)
ay.inputs["Emission Color"].default_value = (1.0, 0.5, 0.0, 1)
ay.inputs["Emission Strength"].default_value = 1.6
arrow_k = W.principled("arrow_outline", (0.0, 0.0, 0.0), 0.6)


def arrow_mesh(name, m, grow=0.0):
    pts = [(-1.6, -0.35), (0.4, -0.35), (0.4, -0.9), (1.6, 0.0), (0.4, 0.9), (0.4, 0.35), (-1.6, 0.35)]
    g_ = grow
    pts = [(x * (1 + g_ / 1.6), y * (1 + g_ / 0.9)) for x, y in pts]
    verts = [(x, y, 0.0) for x, y in pts]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], [list(range(len(verts)))])
    o = bpy.data.objects.new(name, me)
    S["env"].objects.link(o)
    o.data.materials.append(m)
    return o


TOP_S = 247.0
for lane, direction, t_in, ds_ in ((1, -1, 10.0, 0.0), (2, 1, 11.3, 7.0), (3, 1, 11.5, -7.0)):
    root = bpy.data.objects.new(f"arrow{lane}", None)
    S["env"].objects.link(root)
    a1 = arrow_mesh(f"arrow{lane}_fill", arrow_y)
    a2 = arrow_mesh(f"arrow{lane}_line", arrow_k, grow=0.18)
    a1.parent = root
    a2.parent = root
    a2.location.z = -0.03
    c, th, fw, rt, sl = road.frame(TOP_S + ds_)
    base = c + rt * LANE[lane] + Vector((0, 0, 4.6))
    root.rotation_euler = (0, 0, -th + (math.pi if direction < 0 else 0.0))
    f_in = int(t_in * FPS)
    for f, sc_v, off in ((1, 0.0, 0.0), (f_in, 0.0, 0.0), (f_in + 5, 1.5, 0.0), (f_in + 8, 1.3, 0.2),
                         (int(14.4 * FPS), 1.3, 1.4), (int(14.4 * FPS) + 6, 0.0, 1.4)):
        root.scale = (sc_v, sc_v, sc_v)
        root.location = base + rt * (direction * off)
        root.keyframe_insert("scale", frame=f)
        root.keyframe_insert("location", frame=f)

# ---------------------------------------------------------------- cameras (one per shot, switched by markers)
UPF = lambda s_: road.frame(s_)[2]  # noqa: E731
shots = []


def shot(name, lens, f0, f1, fn, up_fn=None):
    co = stage.camera(name, lens)
    locs, rots = [], []
    fr = list(range(max(1, f0 - 2), min(N, f1 + 2) + 1))
    for f in fr:
        t = (f - 1) / FPS
        pos, tgt = fn(t)
        locs.append(tuple(pos))
        rots.append(tuple(stage.look_rot(pos, tgt, up_fn(t) if up_fn else None)))
    stage.bake_motion(co, fr, locs, rots, interp=1)
    m = sc.timeline_markers.new(name, frame=f0)
    m.camera = co
    shots.append((name, f0, f1))
    return co


# A 0 to 3.5 s: drone behind the traffic, everyone braking
shot("A_drone", 24, 1, 105, lambda t: (road.point(160 + 4 * t, 11.0, 24.0), road.point(330, 7.0, 0.0)))


def chase_target():
    best = min((v for v in jam if v["lane"] == 2), key=lambda v: abs(v["s"] - 232))
    return best


CH = chase_target()
# B 3.5 to 7.5 s: behind a car in the middle lane as it stops
shot("B_chase", 28, 106, 225, lambda t: (road.point(jam_state(CH, t)[0] - 12.0, 9.2, 4.8),
                                          road.point(jam_state(CH, t)[0] + 26, 7.9, 1.0)))
# C 7.5 to 15 s: straight down over the jam, the corridor forms
shot("C_top", 30, 226, 450, lambda t: (road.point(TOP_S, 8.6, 36.0 - 0.25 * (t - 7.5)), road.point(TOP_S, 8.6, 0.0)),
     up_fn=lambda t: UPF(TOP_S))
# D 15 to 18 s: low in the corridor, the ambulance comes towards us
shot("D_front", 30, 451, 540, lambda t: (road.point(185 + 3.3 * (t - 15), GAP_X + 0.4, 2.6),
                                         road.point(185 + 3.3 * (t - 15) - 40, GAP_X, 1.2)))
# E 18 to 21 s: high behind the ambulance and the fire engine
shot("E_chase", 26, 541, 630, lambda t: (road.point(hlf_s(t) - 22, GAP_X, 11.0), road.point(rtw_s(t) + 30, GAP_X, 0.5)))
# F 21 to 28 s: drone over the open corridor
shot("F_drone", 24, 631, 840, lambda t: (road.point(150 + 1.5 * (t - 21), GAP_X, 27.0), road.point(330, GAP_X, 0.0)))
sc.camera = bpy.data.objects["A_drone"]

# ---------------------------------------------------------------- look and render
c0, th0, fwd, right, _ = road.frame(260)
stage.sky(road, fwd * 0.3 + right * 0.9, ASSETS, sun_elev_deg=34.0)
stage.hazify_all(skip=("corridor_glow",))
stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
os.makedirs(OUT, exist_ok=True)
todo = STILLS or list(range(FR[0], FR[1] + 1))
for f in todo:
    sc.frame_set(f)
    cam = None
    for name, f0, f1 in shots:
        if f0 <= f <= f1:
            cam = bpy.data.objects[name]
    sc.camera = cam
    sc.render.filepath = os.path.join(OUT, f"f_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    print("Saved", sc.render.filepath)
print("RENDER_DONE", FR)
