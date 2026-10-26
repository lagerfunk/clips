"""Drive Like a Local B1, Austria: a digital vignette bought online starts only on the 18th day. 9:16, 30 fps,
canonical timeline from kit/country.py TIMELINE["B01"] (HOOK 2.6, SITUATION 9.0, RULE 7.5, COST 5.5, CORRECT 6.5,
END 4.2 = 35.3 s).
Set: a two-lane Austrian Autobahn with hard shoulder in an Alpine valley (kit/mway.py, white markings as Germany),
the Austrian Autobahn sign (signs/at.json, Hinweiszeichen 8a, unaltered Commons file), a toll-check gantry (the
lanemgmt gantry frame only: no lane panels, no boards, no text) with a grey camera box; phone, calendar, kiosk, letter
and petrol-station inserts without text, numerals or brands. at vignette-pflicht is missing on Commons: not shown.
Hero: blue estate with a fictional German plate; locals with blank plates.
Run: python b01_vignette_18_days.py OUTDIR --frames 1-1059 --res 540 --samples 8 --assets ASSETS [--stills 40,300]
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import country as CY  # noqa: E402
import jx  # noqa: E402
import lanemgmt as LM  # noqa: E402
import motion  # noqa: E402
import mway as MW  # noqa: E402
import signs as SG  # noqa: E402
import town as TN  # noqa: E402
import world as W  # noqa: E402

OUT, RES, SAMPLES, ASSETS, FR, STILLS = MW.cli(sys.argv)
FPS = MW.FPS
SEG, T_END = CY.spans("B01")
N = int(round(T_END * FPS))
H0, S0, R0, C0, K0, E0 = (SEG[k][0] for k in ("HOOK", "SITUATION", "RULE", "COST", "CORRECT", "END"))
SG.setup(ASSETS)

S = MW.Stage(ASSETS, "at", lanes=2, mountains=True, seed=11)
L0, L1 = S.lane_x(0), S.lane_x(1)
SH = S.shoulder_x()
hero = jx.hero("estate", (0.04, 0.12, 0.42), "hero", "QX VG 118", S.lib, S.traffic, metal=0.5)
HS = 150.0
ta = S.track([(0, 18.0), (H0 + 1.1, 18.0), (S0 + 0.5, 27.0), (T_END, 27.0)], [(0, L1)], N, HS)
sa = S.last_s
# COST: the estate stands on the hard shoulder further on, hazards on
s_park = sa[int(R0 * FPS)] + 300.0
tb = S.track([(0, 0.0)], [(0, SH)], N, s_park, inds=[(0, T_END, "H")])
ht = ta[:int(C0 * FPS)] + tb[int(C0 * FPS):]
S.drive(hero, ht)
c, tr = S.cars, S.trucks
S.traffic_flow(N, [(c["saloon_white"], 1, HS + 60, 25.0), (S.vans["van_white"], 1, HS + 130, 24.0),
                   (c["hatch_silver"], 0, HS - 90, 34.0), (tr["t_white"], 1, HS + 300, 23.0),
                   (c["saloon_black"], 1, HS + 420, 25.0), (c["suv_white"], -1, HS + 700, 30.0),
                   (tr["t_blue"], -2, HS + 1000, 23.0), (c["estate_green"], -1, HS + 1300, 31.0)])
S.sign([("autobahn", 1.2)], HS + 75, S.x_sh + 2.2)
# toll-check gantry where the hero passes at S0 + 7.0: the lanemgmt frame only, plus a grey camera box
f_g = int((S0 + 7.0) * FPS)
s_g = sa[f_g] + 4.0
fr = LM.gantry_frame(S.M, S.lib, 0.95, S.x_sh + 2.4, name="toll_frame")
gp = S.pt(s_g, 0.0)
W.instance(fr, (gp.x, gp.y, gp.z), rz=-S.road.frame(s_g)[1], c=S.env)
grey = MW.mat("toll_grey", (0.42, 0.44, 0.46), 0.45, metal=0.3)
flash = MW.mat("toll_flash", (0.9, 0.1, 0.05), 0.3, emit=(1.0, 0.08, 0.04), estr=0.0)
cb = S.pt(s_g, L1, 5.15)
box = TN.box("toll_cam", S.env, (cb.x, cb.y, cb.z), (0.55, 0.7, 0.45), grey, bevel=0.03)
box.rotation_euler[2] = -S.road.frame(s_g)[1]
TN.box("toll_lens", S.env, (0.0, -0.36, -0.05), (0.2, 0.04, 0.2), MW.mat("toll_lens", (0.01, 0.01, 0.015), 0.1),
       parent=box)
TN.box("toll_lamp", S.env, (0.0, -0.36, 0.15), (0.3, 0.03, 0.06), flash, parent=box)
MW.key_emit(flash, [(1, 0.0), (f_g - 2, 25.0), (f_g + 4, 0.0)])
xb = MW.badge(S.ins, "red_x", "no", (0.0, -2.6, 1.9), size=0.45, parent=hero["obj"], rot=(math.pi / 2, 0, 0))
CY.show(xb, [(S0 + 7.2, S0 + 9.0)])
# envelope on the windscreen in COST
env_m = MW.mat("lt_env", (0.95, 0.95, 0.93), 0.6)
envl = TN.box("lt_env_car", S.ins, (0.0, 0.6, 2.4), (0.34, 0.24, 0.006), env_m, parent=hero["obj"])
for t, loc, rx in ((C0, (0.0, 0.6, 2.6), 0.0), (C0 + 0.8, (0.0, 0.55, 1.42), -0.45)):
    envl.location, envl.rotation_euler = loc, (rx, 0, 0)
    envl.keyframe_insert("location", frame=int(t * FPS) + 1)
    envl.keyframe_insert("rotation_euler", frame=int(t * FPS) + 1)
CY.show(envl, [(C0, K0)])
stamp = CY.flat(S.ins, "lt_stamp", CY.disc_pts(0.06, 32), (0.8, 0.06, 0.05), emit=1.0, parent=envl,
                rot=(0, 0, 0), z=0.004)
CY.show(stamp, [(C0 + 1.3, K0)])

# ------------------------------------------------------------------ inserts (far from the road)
ins = S.ins
PH = Vector((9300.0, 0.0, 1.2))
CY.phone(ins, "phone_a", tuple(PH), (math.pi / 2, 0, 0),
         {"pay": ([(H0, S0 + 3.0)], CY.screen_pay(S0 + 0.6, S0 + 0.9))})


def screen_plate(c, p):
    """Plate form: empty letter boxes (no characters), the country-code box highlighted, then a green tick."""
    z = 0.0004
    for k in range(6):
        CY.flat(c, "pf_box", MW.rect(0.0075, 0.011, -0.012 + 0.0095 * k, 0.012), (0.93, 0.94, 0.95), 1.0,
                rot=(0, 0, 0), parent=p, z=z)
    cc = CY.flat(c, "pf_cc", MW.rect(0.012, 0.013, -0.025, 0.012), (1.0, 0.75, 0.05), 1.3, rot=(0, 0, 0), parent=p,
                 z=z + 0.0002)
    CY.flat(c, "pf_band", MW.rect(0.056, 0.02, 0.0, 0.012), (0.3, 0.32, 0.36), 0.8, rot=(0, 0, 0), parent=p, z=z - 0.0002)
    tick = CY.bpy_empty(c, "pf_tick", p)
    CY.flat(c, "pf_tick_bg", CY.disc_pts(0.012, 32, 0.0, -0.03), (0.1, 0.7, 0.3), 1.2, rot=(0, 0, 0), parent=tick,
            z=z + 0.0005)
    CY.show(tick, [(K0 + 4.6, 999)])
    CY.show(cc, [(K0 + 3.8, 999)])


CY.phone(ins, "phone_b", tuple(PH + Vector((0.5, 0, 0))), (math.pi / 2, 0, 0),
         {"plate": ([(K0, E0)], screen_plate)})
# calendar of blank tiles (no numerals): first tile green in SITUATION; in RULE the tiles turn green one by one with a
# lock on days 1 to 17, the 18th pulses with a tick
CAL = Vector((9300.25, 0.02, 1.2))
TN.box("cal_board", ins, tuple(CAL + Vector((0, 0.01, 0))), (0.2, 0.004, 0.11), MW.mat("cal_board", (0.95, 0.95, 0.94),
                                                                                          0.6))
TN.box("cal_head", ins, tuple(CAL + Vector((0, 0.008, 0.047))), (0.2, 0.004, 0.016), MW.mat("cal_head", (0.75, 0.1,
                                                                                                         0.1), 0.5))
tiles = []
for k in range(21):
    col, row = k % 7, k // 7
    loc = CAL + Vector((-0.081 + 0.027 * col, 0.0, 0.025 - 0.028 * row))
    CY.flat(ins, f"cal_t{k}", MW.rect(0.023, 0.023), (0.72, 0.73, 0.75), emit=0.4, loc=tuple(loc))
    g = CY.flat(ins, f"cal_g{k}", MW.rect(0.023, 0.023), (0.15, 0.72, 0.3), emit=0.9,
                loc=tuple(loc + Vector((0, -0.001, 0))))
    t_on = S0 if k == 0 else (R0 + 0.15 * k if k < 18 else R0 + 2.9)
    CY.show(g, [(t_on, 999)])
    tiles.append((loc, g))
    if k < 17:
        lk = MW.lock_icon(ins, f"cal_l{k}", tuple(loc + Vector((0, -0.002, 0))), 0.012, (0.25, 0.27, 0.3))
        CY.show(lk, [(R0 + 0.15 * k + 0.1, S0 + 999)])
g18 = tiles[17][1]
for t, sc in ((R0 + 2.9, 1.0), (R0 + 3.15, 1.35), (R0 + 3.4, 1.0), (R0 + 3.65, 1.3), (R0 + 3.8, 1.0)):
    g18.scale = (sc, sc, sc)
    g18.keyframe_insert("scale", frame=int(t * FPS) + 1)
# kiosk (valid now) beside a phone with a grey lock (not yet)
KX = Vector((9500.0, 0.0, 0.0))
kio = MW.mat("kiosk_wall", (0.86, 0.84, 0.78), 0.7)
TN.box("kiosk", ins, tuple(KX + Vector((-1.6, 0.6, 1.3))), (2.2, 1.6, 2.6), kio, bevel=0.05)
TN.box("kiosk_roof", ins, tuple(KX + Vector((-1.6, 0.5, 2.7))), (2.6, 2.0, 0.18), MW.mat("kiosk_roof", (0.2, 0.3,
                                                                                                    0.25), 0.6))
TN.box("kiosk_win", ins, tuple(KX + Vector((-1.6, -0.21, 1.55))), (1.5, 0.02, 0.9), MW.mat("kiosk_glass", (0.3, 0.38,
                                                                                                       0.42), 0.1))
vig = bpy.data.objects.new("kiosk_vignette", None)
ins.objects.link(vig)
vig.location = KX + Vector((-1.6, -0.24, 1.55))
CY.flat(ins, "kv_card", MW.rect(0.5, 0.36), (0.95, 0.55, 0.65), emit=0.8, parent=vig)
CY.flat(ins, "kv_band", CY.bar_pts(-0.25, -0.18, 0.25, 0.18, 0.08), (0.95, 0.95, 0.95), emit=0.8, parent=vig, z=0.003)
MW.badge(ins, "kiosk_ok", "yes", tuple(KX + Vector((-1.6, -0.3, 2.35))), size=0.22)
TN.box("kiosk_ground", ins, tuple(KX + Vector((0, 1.0, -0.05))), (8.0, 6.0, 0.1), S.M.asph_sh)


def screen_lock(c, p):
    MW.lock_icon(c, "pl_lock", (0.0, 0.01, 0.0005), 0.03, (0.45, 0.47, 0.5), parent=p, rot=(0, 0, 0))


bigp = CY.phone(ins, "phone_lock", tuple(KX + Vector((1.4, -0.1, 1.3))), (math.pi / 2, 0, 0),
                {"lock": ([(0, 999)], screen_lock)})
bigp.scale = (12, 12, 12)
# letter close-up (no text): envelope with window, grey lines, red stripe
CL = Vector((9700.0, 0.0, 1.5))
TN.box("lt_big", ins, tuple(CL), (0.23, 0.004, 0.33), env_m)
TN.box("lt_win", ins, tuple(CL + Vector((0.02, -0.003, 0.05))), (0.13, 0.002, 0.06), MW.mat("lt_win", (0.8, 0.82,
                                                                                                      0.85), 0.3))
for r in range(3):
    TN.box("lt_line", ins, tuple(CL + Vector((0.01, -0.004, 0.065 - 0.016 * r))), (0.1 - 0.02 * r, 0.001, 0.006),
           MW.mat("lt_ink", (0.25, 0.26, 0.28), 0.6))
TN.box("lt_stripe", ins, tuple(CL + Vector((0.0, -0.003, -0.13))), (0.23, 0.002, 0.02), MW.mat("lt_red", (0.65, 0.05,
                                                                                                          0.05), 0.5))
# petrol station (no brand, no text): forecourt, canopy on four columns, two pump islands, shop with a till screen
PS = Vector((10000.0, 0.0, 0.0))
TN.box("ps_ground", ins, tuple(PS + Vector((0, 20.0, -0.05))), (60.0, 90.0, 0.1), S.M.asph_sh)
TN.box("ps_grass", ins, tuple(PS + Vector((0, 20.0, -0.12))), (300.0, 300.0, 0.1), S.M.grass)
can = MW.mat("ps_canopy", (0.9, 0.9, 0.88), 0.5)
TN.box("ps_canopy", ins, tuple(PS + Vector((6.0, 20.0, 5.2))), (14.0, 16.0, 0.7), can, bevel=0.05)
for dx in (0.5, 11.5):
    for dy in (14.0, 26.0):
        TN.box("ps_col", ins, tuple(PS + Vector((dx, dy, 2.45))), (0.4, 0.4, 4.9), S.M.steel)
pm = MW.mat("ps_pump", (0.25, 0.45, 0.35), 0.5)
for dx in (3.0, 9.0):
    TN.box("ps_island", ins, tuple(PS + Vector((dx, 20.0, 0.1))), (1.2, 8.0, 0.2), S.M.concrete)
    for dy in (17.5, 22.5):
        TN.box("ps_pumpbox", ins, tuple(PS + Vector((dx, dy, 1.0))), (0.7, 0.5, 1.8), pm, bevel=0.04)
TN.box("ps_shop", ins, tuple(PS + Vector((-12.0, 30.0, 2.0))), (12.0, 9.0, 4.0), kio, bevel=0.05)
TN.box("ps_glass", ins, tuple(PS + Vector((-5.95, 30.0, 1.7))), (0.05, 7.0, 2.6), MW.mat("kiosk_glass2", (0.3, 0.38,
                                                                                                         0.42), 0.1))
till = MW.badge(ins, "ps_till", "yes", tuple(PS + Vector((-5.85, 28.0, 2.6))), size=0.35, rot=(math.pi / 2, 0, math.pi / 2))
CY.show(till, [(K0 + 2.2, E0)])
# a copy of the hero drives in, indicating right, and stops at the pump
car2 = W.instance(hero["coll"], tuple(PS), c=S.traffic)
r2 = motion.rig(car2)
rows = []
for f in range(N):
    t = f / FPS
    u = min(1.0, max(0.0, (t - K0) / 2.0))
    e = 1 - (1 - u) ** 2
    y = -30.0 + 47.5 * e
    x = 6.0 + 3.0 * (1 - u) - 3.0 * (1 - abs(1 - 2 * u)) * 0.2
    rows.append(dict(x=PS.x + x, y=PS.y + y, z=0.0, yaw=math.pi / 2, v=max(0.0, 47.5 * 2 * (1 - u) / 2.0),
                     ind="R" if K0 <= t < K0 + 1.6 else None))
motion.bake(r2, rows)
ec_pos, ec_tgt, ec_scale = CY.end_card(ins, "at", ["autobahn"], x0=-9000.0)

# ------------------------------------------------------------------ cameras
shots = jx.Shots(N)
V3 = Vector
shots.add("H_phone", 40, H0, H0 + 1.1, lambda t: (PH + V3((0.0, -0.3, 0.0)), PH))
shots.add("H_chase", 28, H0 + 1.1, SEG["HOOK"][1], lambda t: S.chase(ta, t, back=9.0, up=2.0, side=1.0))
shots.add("S_phone", 40, S0, S0 + 3.0, lambda t: (PH + V3((0.12, -0.42, 0.0)), PH + V3((0.12, 0, 0))))
shots.add("S_chase", 28, S0 + 3.0, S0 + 6.0, lambda t: S.chase(ta, t, back=10.0, up=2.6, side=2.0))
gq = S.pt(s_g, S.x_sh + 2.0)
shots.add("S_drone", 26, S0 + 6.0, SEG["SITUATION"][1],
          lambda t: (gq + V3((8.0, -42.0 + 3.0 * (t - S0 - 6.0), 16.0)), gq + V3((-6.0, 10.0, 3.0))))
shots.add("R_cal", 40, R0, R0 + 3.8, lambda t: (CAL + V3((0.0, -0.46, 0.0)), CAL))
shots.add("R_split", 30, R0 + 3.8, SEG["RULE"][1], lambda t: (KX + V3((0.0, -9.0, 1.6)), KX + V3((0.0, 0.0, 1.4))))
shots.add("C_car", 30, C0, C0 + 2.0, lambda t: S.chase(ht, C0, back=7.0, up=3.4, side=-2.5, ahead=3.0, look_up=0.8))
shots.add("C_letter", 50, C0 + 2.0, SEG["COST"][1],
          lambda t: (CL + V3((0.0, -0.55 + 0.03 * (t - C0 - 2.0), 0.0)), CL))
shots.add("K_drone", 24, K0, K0 + 3.2, lambda t: (PS + V3((26.0, -24.0, 18.0)), PS + V3((2.0, 18.0, 0.5))))
shots.add("K_phone", 40, K0 + 3.2, SEG["CORRECT"][1], lambda t: (PH + V3((0.5, -0.3, 0.0)), PH + V3((0.5, 0, 0))))
cam_e = shots.add("E_card", 50, E0, T_END, lambda t: (V3(ec_pos), V3(ec_tgt)))
cam_e.data.type, cam_e.data.ortho_scale = "ORTHO", ec_scale
for nm in ("H_phone", "S_phone", "K_phone", "R_cal", "C_letter"):
    bpy.data.objects[nm].data.clip_start = 0.02

CY.sun_light(ASSETS, az_deg=160.0, elev_deg=36.0, energy=4.4)
MW.render(shots, OUT, RES, SAMPLES, FR, STILLS, N, haze=(0.68, 0.76, 0.88), haze_dist=3800.0, first="H_phone")
print("RENDER_DONE", FR, "signs", SG.sources_used().keys())
