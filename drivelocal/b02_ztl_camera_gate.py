"""Drive Like a Local B2, Italy: the ZTL gate with the red panel. 9:16, 30 fps, canonical timeline from
kit/country.py TIMELINE["B02"] (HOOK 2.6, SITUATION 9.5, RULE 7.5, COST 6.5, CORRECT 6.5, END 4.2 = 36.8 s).
Set: an Italian old town (kit/country.py terraces in ochre and terracotta, shutters, setts, no pavements), a small
piazza with a car park outside the town wall, a round-arched gate with the ZTL sign (signs/it.json, unaltered Commons
file), a red/green lamp panel without digits and a grey camera box. Hero: white rental hatchback with a fictional
German plate; locals with blank plates; a cyclist overtakes (the kit has no scooter model).
Run: python b02_ztl_camera_gate.py OUTDIR --frames 1-1104 --res 540 --samples 8 --assets ASSETS [--stills 40,200]
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import country as CY  # noqa: E402
import jx  # noqa: E402
import signs as SG  # noqa: E402
import stage  # noqa: E402
import town as TN  # noqa: E402
import townplus as TP  # noqa: E402
import world as W  # noqa: E402

OUT, RES, SAMPLES, ASSETS, FR, STILLS = "frames", 540, 8, "assets", None, None
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

FPS = jx.FPS
SEG, T_END = CY.spans("B02")
N = int(round(T_END * FPS))
H0, S0, R0, C0, K0, E0 = (SEG[k][0] for k in ("HOOK", "SITUATION", "RULE", "COST", "CORRECT", "END"))
HW = CY.SPEC["it"]["street"] / 2
SG.setup(ASSETS)
ZTL = "ztl-a" if os.path.exists(os.path.join(ASSETS, "signs", "it", "ztl-a.png")) else "ztl"
SIGNS = ["ztl", "ztl-end", "no-vehicles", "pedestrian-area"]

# ------------------------------------------------------------------ scene
bpy.ops.wm.read_factory_settings(use_empty=True)
W.setup(ASSETS, None)
lib, env, traffic = W.coll("lib"), W.coll("env"), W.coll("traffic")
cars, vans, trucks = stage.fleet(lib)
hero = jx.hero("hatch", (0.86, 0.87, 0.88), "rental", "QX RT 418", lib, traffic, metal=0.1)
CY.blank_plates([lib.children[k] for k in list(cars) + list(vans)])
M = W.Mats()
T = TN.TownMats(M)
CM = CY.Mats("it")
rnd = random.Random(2)

# ground: setts everywhere (old town, kerbless), darker gutter line along the facades
CY.ground(env, "setts", [(-60, -160), (60, -160), (60, 110), (-60, 110)], CM.setts)
for x in (-HW + 0.25, HW - 0.25):
    CY.ground(env, "gutter", [(x - 0.2, -150), (x + 0.2, -150), (x + 0.2, 100), (x - 0.2, 100)], T.cobble, z=0.004)
# approach street (y -150..-18), piazza (y -18..-0.6, x -26..14), inner street beyond the wall (y 0.6..100)
CY.terrace(env, CM, (-HW, -150), (-HW, -18), seed=11)
CY.terrace(env, CM, (HW, -18), (HW, -150), seed=12)
CY.terrace(env, CM, (-HW, -18), (-26, -18), seed=13, ground_floor="shop")
CY.terrace(env, CM, (14, -18), (HW, -18), seed=14, ground_floor="shop")
CY.terrace(env, CM, (-26, -18), (-26, -0.6), seed=15)
CY.terrace(env, CM, (14, -0.6), (14, -18), seed=16)
CY.terrace(env, CM, (-HW, 0.6), (-HW, 100), seed=17)
CY.terrace(env, CM, (HW, 100), (HW, 0.6), seed=18)
# back rows so the drone sees a town, not a stage
for k, (p0, p1) in enumerate((((-24, -150), (-24, -20)), ((24, -20), (24, -150)), ((-24, 2), (-24, 100)),
                              ((24, 100), (24, 2)))):
    CY.terrace(env, CM, p0, p1, seed=30 + k, depth=11.0)
    CY.terrace(env, CM, (p1[0] + (12 if p0[0] < 0 else -12), p1[1]), (p0[0] + (12 if p0[0] < 0 else -12), p0[1]),
               seed=40 + k, depth=9.0)
wall = CY.arch_wall(env, CM.stone, half_open=2.6, spring=3.6, half_w=30.0, h=9.0, thick=1.4)
# washing line across the approach street
for y in (-70.0, -44.0):
    TN.cyl("wline", env, (0, y, 6.6), 0.008, 2 * HW, CM.iron, verts=6, rot=(0, math.pi / 2, 0))
    for k in range(5):
        TN.box("cloth", env, (-1.4 + k * 0.7, y, 6.3), (0.5, 0.01, 0.6),
               W.principled(f"cloth{k}", rnd.choice([(0.8, 0.8, 0.78), (0.2, 0.3, 0.6), (0.7, 0.2, 0.15)]), 0.9))
# flower pots and benches in the piazza
plant = W.noisy("plant", (0.05, 0.16, 0.04), (0.1, 0.26, 0.06), 6.0, rough=0.9, bump=0.5)
for k in range(4):
    p = (-22 + 10 * k, -16.8)
    TN.cyl("pot", env, (p[0], p[1], 0.35), 0.45, 0.7, CM.pot, verts=20)
    TN.cyl("plant", env, (p[0], p[1], 0.95), 0.4, 0.5, plant, verts=12)

# car park outside the wall (west half of the piazza): painted bays, parked local cars
for k in range(7):
    x = -24.5 + k * 2.6
    TN.bar(T, env, x - 0.06, x + 0.06, -15.5, -10.5, name="bay")
fleet = list(cars.values()) + list(vans.values())
for k in range(6):
    if k == 3:
        continue                         # the hero's bay
    e = bpy.data.objects.new(f"parked{k}", None)
    e.instance_type, e.instance_collection = "COLLECTION", rnd.choice(fleet)
    e.location = (-23.2 + k * 2.6, -13.0, 0.0)
    e.rotation_euler = (0, 0, 0.0)
    env.objects.link(e)

# the gate: ZTL sign on the wall right of the arch, the lamp panel under it, the camera box on the left
face = SG.face(ZTL, env, 0.9, "it", name="ztl_sign")
face.location = (3.9, -0.72, 2.0)
pan = TN.box("panel", env, (3.9, -0.78, 1.5), (0.9, 0.1, 0.42), W.principled("panel_body", (0.08, 0.08, 0.09), 0.4))
red = W.principled("lamp_red", (0.3, 0.02, 0.02), 0.3, emit=(1.0, 0.05, 0.03), estr=0.0)
grn = W.principled("lamp_green", (0.02, 0.2, 0.05), 0.3, emit=(0.1, 1.0, 0.2), estr=0.0)
TN.cyl("lamp_r", env, (3.66, -0.84, 1.5), 0.14, 0.03, red, verts=24, rot=(math.pi / 2, 0, 0))
TN.cyl("lamp_g", env, (4.14, -0.84, 1.5), 0.14, 0.03, grn, verts=24, rot=(math.pi / 2, 0, 0))
cam_body = W.principled("cambox", (0.42, 0.43, 0.44), 0.45, metal=0.4)
TN.box("cambox", env, (-3.6, -1.0, 4.6), (0.32, 0.5, 0.26), cam_body, bevel=0.02)
TN.box("cambox_arm", env, (-3.6, -0.78, 4.45), (0.08, 0.2, 0.08), cam_body)
flash_m = W.principled("cam_flash", (0.1, 0.1, 0.1), 0.2, emit=(1.0, 0.97, 0.9), estr=0.0)
TN.cyl("cam_lens", env, (-3.6, -1.26, 4.6), 0.07, 0.03, flash_m, verts=20, rot=(math.pi / 2, 0, 0))
fl = bpy.data.lights.new("flash", "POINT")
fl.energy = 0.0
flo = bpy.data.objects.new("flash", fl)
flo.location = (-3.6, -1.5, 4.6)
env.objects.link(flo)


def lamp_keys(m, pairs):
    jx.key_emission(m, [(int(round(t * FPS)) + 1, v) for t, v in pairs])


GREEN = (R0 + 3.6, R0 + 5.6)
lamp_keys(red, [(0, 6.0), (GREEN[0], 0.0), (GREEN[1], 6.0)])
lamp_keys(grn, [(0, 0.0), (GREEN[0], 6.0), (GREEN[1], 0.0)])
FLASHES = [S0 + 7.0, R0 + 5.9]
pairs = [(0, 0.0)]
for t in FLASHES:
    pairs += [(t, 40.0), (t + 0.12, 0.0)]
lamp_keys(flash_m, pairs)
fl.keyframe_insert("energy", frame=1)
for t in FLASHES:
    for f, v in ((int(round(t * FPS)), 0.0), (int(round(t * FPS)) + 1, 900.0), (int(round(t * FPS)) + 4, 0.0)):
        fl.energy = v
        fl.keyframe_insert("energy", frame=f)

# rule icons in front of the arch
ico_no = CY.icon(env, "ico_no", "no", (0.0, -2.5, 2.4), 0.55)
ico_yes = CY.icon(env, "ico_yes", "yes", (0.0, -2.5, 2.4), 0.55)
CY.show(ico_no, [(R0 + 0.3, GREEN[0]), (GREEN[1], C0)])
CY.show(ico_yes, [GREEN])

# ------------------------------------------------------------------ cars and people
MAIN = jx.Path([(0.0, -400.0), (0.0, 400.0)])            # s = y + 400
# PARK: north up the approach, a left turn (radius 4) into the car park, a parallel spot along the aisle
PARK = jx.Path([(0.0, -60.0), (0.0, -12.5)] + [(-4.0 + 4.0 * math.cos(math.pi * k / 16),
                                                 -12.5 + 4.0 * math.sin(math.pi * k / 16)) for k in range(1, 9)] +
               [(-12.0, -8.5)])
n_h, n_s, n_r, n_c, n_k, n_e = (int(round((SEG[k][1] - SEG[k][0]) * FPS)) for k in
                                ("HOOK", "SITUATION", "RULE", "COST", "CORRECT", "END"))
n_k = N - (n_h + n_s + n_r + n_c + n_e)
hook_sv = jx.kinematics(400.0 - 27.0, 5.0, [(0, "cruise", 5.0)], n_h)
sit_sv = jx.kinematics(400.0 - 35.0, 5.0, [(0, "cruise", 5.0)], n_s)
away = CY.hold(-2000.0, n_r + n_c)
s_turn = 60.0 - 12.5
cor_sv = jx.kinematics(s_turn - 4.0, 5.0, [(0, "cruise", 5.0), (0.8, "cruise", 3.0), (1.5, "stop", s_turn + 7.3)], n_k)
jx.blink(hero, "L", 0.3, H0 + SEG["HOOK"][1])
jx.blink(hero, "L", K0 + 0.2, K0 + 2.4)
CY.drive_pieces(hero, [(MAIN, hook_sv), (MAIN, sit_sv), (MAIN, away), (PARK, cor_sv), (MAIN, CY.hold(-2000.0, n_e))])

# a cyclist overtakes in SITUATION at 2.0 s (stands in for the scripted scooter)
bike = TP.cyclist(traffic, "bike1", seed=3)
bike_sv = [(-2000.0, 0.0)] * n_h + jx.kinematics(400.0 - 44.0, 7.2, [(0, "cruise", 7.2)], n_s) + \
    [(-2000.0, 0.0)] * (N - n_h - n_s)
TP.ride(bike, jx.Path([(-0.9, -400.0), (-0.9, 400.0)]), bike_sv, list(range(1, N + 1)))
# a delivery van parked at the piazza's east side, pedestrians in the piazza
dv = bpy.data.objects.new("van_parked", None)
dv.instance_type, dv.instance_collection = "COLLECTION", vans["van_white"]
dv.location, dv.rotation_euler = (10.5, -9.0, 0.0), (0, 0, 0.0)
env.objects.link(dv)
for k, (p0, p1, sd) in enumerate((((-8, -16), (9, -3), 1), ((11, -16), (3, -2.5), 2), ((2.4, -17), (2.4, -3), 5))):
    ped = TP.pedestrian(traffic, f"ped{k}", seed=sd)
    L_ = math.dist(p0, p1)
    TP.walk(ped, jx.Path([p0, p1]), jx.kinematics(0.0, 0.8, [(0, "cruise", 0.8), (0, "stop", L_)], N),
            list(range(1, N + 1)))
driver = TP.pedestrian(traffic, "driver", seed=9, coat=(0.15, 0.2, 0.35))
k0 = int(round((K0 + 2.5) * FPS))
drv_sv = [(-80.0, 0.0)] * k0 + jx.kinematics(0.0, 1.4, [(0, "cruise", 1.4)], N - k0)
TP.walk(driver, jx.Path([(-5.0, -9.9), (-1.2, -6.0), (-0.6, 8.0)]), drv_sv, list(range(1, N + 1)))

# ------------------------------------------------------------------ inserts: phone, letterbox, end card
ins = W.coll("inserts")
PH_CAM = Vector((0.0, -95.0, 1.25))
nav = CY.phone(ins, "phone", (0.11, -95.0 + 0.42, 1.12), (math.radians(78), 0, math.radians(-8)),
               {"nav": ([(0, H0 + 1.2)], CY.screen_nav("left")),
                "pay": ([(K0 + 2.9, E0)], CY.screen_pay(K0 + 4.2, K0 + 4.4))})
TN.box("dash", ins, (0.0, -95.0 + 0.6, 0.86), (2.0, 0.6, 0.12), W.principled("dash", (0.04, 0.04, 0.045), 0.6))
# letterbox set far away (x = 9000): wall, letterbox, flip calendar, a letter that drops in, then the letter close-up
LX = 9000.0
wallm = CM.walls[2]
TN.box("lb_wall", ins, (LX, 0.6, 1.5), (6.0, 0.4, 4.0), wallm)
lbm = W.principled("letterbox", (0.12, 0.2, 0.14), 0.35, metal=0.5, coat=0.5)
TN.box("letterbox", ins, (LX + 0.35, 0.2, 1.25), (0.42, 0.24, 0.5), lbm, bevel=0.015)
TN.box("lb_slot", ins, (LX + 0.35, 0.075, 1.42), (0.3, 0.01, 0.025), W.principled("slot", (0.01, 0.01, 0.01), 0.8))
paper = W.principled("paper", (0.92, 0.92, 0.9), 0.7)
redband = W.principled("cal_red", (0.65, 0.05, 0.05), 0.5)
TN.box("cal_back", ins, (LX - 0.5, 0.36, 1.55), (0.5, 0.02, 0.62), W.principled("card", (0.4, 0.3, 0.2), 0.8))
for k in range(9):
    pg = bpy.data.objects.new(f"page{k}", None)
    ins.objects.link(pg)
    pg.location = (LX - 0.5, 0.34 - 0.002 * k, 1.84)
    TN.box("pg", ins, (0, 0, -0.29), (0.46, 0.002, 0.56), paper, parent=pg)
    TN.box("pg_band", ins, (0, -0.002, -0.06), (0.46, 0.002, 0.1), redband, parent=pg)
    for r in range(4):
        TN.box("pg_row", ins, (0, -0.002, -0.2 - 0.09 * r), (0.38, 0.002, 0.012),
               W.principled("pg_grid", (0.7, 0.7, 0.68), 0.8), parent=pg)
    t0 = C0 + 0.2 + 0.17 * (8 - k)
    if k > 0:
        pg.rotation_euler = (0, 0, 0)
        pg.keyframe_insert("rotation_euler", frame=int(t0 * FPS) + 1)
        pg.rotation_euler = (math.radians(-178), 0, 0)
        pg.keyframe_insert("rotation_euler", frame=int((t0 + 0.25) * FPS) + 1)
env_m = W.principled("envelope", (0.95, 0.95, 0.93), 0.6)
letter = TN.box("letter", ins, (LX + 0.35, 0.12, 2.3), (0.24, 0.006, 0.12), env_m)
for f, z in ((int((C0 + 1.3) * FPS), 2.3), (int((C0 + 1.8) * FPS), 1.44), (int((C0 + 1.85) * FPS), 1.40)):
    letter.location.z = z
    letter.keyframe_insert("location", frame=f)
# the letter close-up: an envelope with a window, a red border and grey address lines (no text)
CL = Vector((LX + 40.0, 0.0, 1.5))
TN.box("env_big", ins, tuple(CL), (0.23, 0.004, 0.33), env_m)
TN.box("env_win", ins, tuple(CL + Vector((0.02, -0.003, 0.05))), (0.13, 0.002, 0.06), W.principled("win", (0.8, 0.82, 0.85), 0.3))
for r in range(3):
    TN.box("env_line", ins, tuple(CL + Vector((0.01, -0.004, 0.065 - 0.016 * r))), (0.1 - 0.02 * r, 0.001, 0.006),
           W.principled("ink", (0.25, 0.26, 0.28), 0.6))
TN.box("env_stripe", ins, tuple(CL + Vector((0.0, -0.003, -0.13))), (0.23, 0.002, 0.02), redband)
# end card
ec_pos, ec_tgt, ec_scale = CY.end_card(ins, "it", SIGNS, x0=-9000.0)

# ------------------------------------------------------------------ cameras
shots = jx.Shots(N)


def follow(t):
    i = min(len(hero["track"]) - 1, int(t * FPS))
    x, y, _ = hero["track"][i]
    return x, y


shots.add("H_phone", 40, H0, H0 + 1.1, lambda t: (PH_CAM, PH_CAM + Vector((0.11, 0.42, -0.13))))
shots.add("H_chase", 26, H0 + 1.1, SEG["HOOK"][1],
          lambda t: (Vector((0.5, follow(t)[1] - 7.5, 2.0)), Vector((0.0, follow(t)[1] + 20.0, 2.4))))
shots.add("S_chase", 26, S0, S0 + 3.2,
          lambda t: (Vector((-0.4, follow(t)[1] - 8.0, 2.1)), Vector((0.2, follow(t)[1] + 22.0, 2.6))))
shots.add("S_sign", 45, S0 + 3.2, S0 + 6.4,
          lambda t: (Vector((6.0 - 0.3 * (t - S0 - 3.2), -9.0, 1.3)), Vector((3.2, -0.7, 2.3))))
shots.add("S_drone", 24, S0 + 6.4, SEG["SITUATION"][1],
          lambda t: (Vector((-9.0 + 1.2 * (t - S0 - 6.4), -22.0, 13.0)), Vector((0.0, -1.0, 2.0))))
shots.add("R_close", 38, R0, SEG["RULE"][1],
          lambda t: (Vector((1.6 + 0.1 * (t - R0), -10.5, 1.9)), Vector((1.8, -0.8, 2.6))))
shots.add("C_cal", 30, C0, C0 + 2.2, lambda t: (Vector((LX, -2.3, 1.6)), Vector((LX - 0.05, 0.3, 1.6))))
shots.add("C_letter", 50, C0 + 2.2, SEG["COST"][1],
          lambda t: (CL + Vector((0.0, -0.55 + 0.03 * (t - C0 - 2.2), 0.0)), CL))
shots.add("K_drone", 24, K0, K0 + 2.9,
          lambda t: (Vector((6.0, -30.0 + 0.5 * (t - K0), 16.0)), Vector((-6.0, -8.0, 0.5))))
shots.add("K_phone", 40, K0 + 2.9, SEG["CORRECT"][1], lambda t: (PH_CAM, PH_CAM + Vector((0.11, 0.42, -0.13))))
cam_e = shots.add("E_card", 50, E0, T_END, lambda t: (Vector(ec_pos), Vector(ec_tgt)))
cam_e.data.type = "ORTHO"
cam_e.data.ortho_scale = ec_scale
for nm in ("H_phone", "K_phone"):
    cd = bpy.data.objects[nm].data
    cd.dof.use_dof = True
    cd.dof.focus_distance = 0.45
    cd.dof.aperture_fstop = 2.8
    cd.clip_start = 0.02
for nm in ("C_cal", "C_letter"):
    bpy.data.objects[nm].data.clip_start = 0.02
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, N
sc.camera = bpy.data.objects["H_phone"]

CY.sun_light(ASSETS, az_deg=215.0, elev_deg=32.0, energy=4.4, warm=True)
stage.hazify_all(color=(0.78, 0.74, 0.68), dist=700.0,
                 skip=[m.name for m in bpy.data.materials if m.name.endswith("_m") or m.name.startswith(
                     ("phone", "sign_", "lamp_", "cam_flash"))])
stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
todo = STILLS or list(range(FR[0], FR[1] + 1) if FR else range(1, N + 1))
jx.render_frames(shots, OUT, todo)
print("RENDER_DONE", FR, "signs", SG.sources_used().keys())
