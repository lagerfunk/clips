"""Drive Like a Local B4, Switzerland: far over the limit is the criminal Raser offence. 9:16, 30 fps, canonical
timeline from kit/country.py TIMELINE["B04"] (HOOK 2.6, SITUATION 9.5, RULE 8.0, COST 6.5, CORRECT 6.0, END 4.2).
Set: a three-lane Swiss motorway in an Alpine valley (kit/mway.py, white markings, ridges with snow), the green Swiss
motorway sign (signs/ch.json, unaltered Commons file), a grey fixed enforcement column, an overpass with a generic
police estate (lettering removed, no emblem). The ch limit-120 sign is missing on Commons, so no limit disc is shown:
the 120 is in the caption only. Hero: dark grey saloon with a fictional German plate; locals with blank plates.
Run: python b04_raser_law.py OUTDIR --frames 1-1104 --res 540 --samples 8 --assets ASSETS [--stills 40,300]
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
import mway as MW  # noqa: E402
import signs as SG  # noqa: E402
import town as TN  # noqa: E402
import world as W  # noqa: E402

OUT, RES, SAMPLES, ASSETS, FR, STILLS = MW.cli(sys.argv)
FPS = MW.FPS
SEG, T_END = CY.spans("B04")
N = int(round(T_END * FPS))
H0, S0, R0, C0, K0, E0 = (SEG[k][0] for k in ("HOOK", "SITUATION", "RULE", "COST", "CORRECT", "END"))
SG.setup(ASSETS)

S = MW.Stage(ASSETS, "ch", lanes=3, mountains=True, seed=7)
L0, L1, L2 = (S.lane_x(i) for i in range(3))
SH = S.shoulder_x()
hero = jx.hero("saloon", (0.09, 0.095, 0.1), "hero", "JX RS 480", S.lib, S.traffic, metal=0.6)
HS = 200.0
# part A (HOOK..COST): left lane 33 -> 55 m/s, passes the column at S0 + 7.0, slows during RULE (off screen), is in the
# right lane at 25 m/s when COST opens, follows the police onto the hard shoulder and stops
va = [(0, 33.0), (H0 + 1.1, 33.0), (S0, 55.0), (R0 + 1.0, 55.0), (C0 - 1.0, 25.0), (C0 + 0.8, 25.0), (C0 + 2.4, 0.0)]
xa = [(0, L0), (R0 + 3.0, L0), (C0 - 1.5, L2), (C0 + 0.9, L2), (C0 + 2.2, SH)]
ta = S.track(va, xa, N, HS, inds=[(R0 + 2.5, C0 - 1.5, "R"), (C0 + 0.6, C0 + 2.4, "R"), (C0 + 2.4, E0, "H")])
sa = S.last_s
# part B (CORRECT): back on the road later, middle lane at an even 33 m/s, one brake tap
SB = sa[int(C0 * FPS)] + 700.0
tb = S.track([(0, 33.0), (K0 + 1.4, 33.0), (K0 + 1.7, 31.0), (T_END, 31.0)], [(0, L1)], N, SB - 33.0 * K0)
ht = ta[:int(K0 * FPS)] + tb[int(K0 * FPS):]
S.drive(hero, ht)
c, tr = S.cars, S.trucks
S.traffic_flow(N, [(c["hatch_silver"], 1, HS + 25, 33.0), (c["suv_white"], 1, HS + 60, 33.0),
                   (c["estate_green"], 1, HS + 100, 33.0), (tr["t_white"], 2, HS + 70, 24.0),
                   (c["hatch_red"], 2, HS + 30, 31.0), (S.vans["van_white"], 2, HS + 180, 27.0),
                   (tr["t_blue"], 2, SB - 33.0 * K0 + 260, 24.0), (c["saloon_white"], 1, SB - 33.0 * K0 + 60, 33.0),
                   (c["estate_grey"], -2, HS + 800, 33.0), (tr["t_alpen"], -1, HS + 1100, 24.0),
                   (c["suv_dark"], -3, HS + 1500, 36.0)])
# enforcement column where the saloon passes at S0 + 7.0; overpass just beyond it with the police estate
f_col = int((S0 + 7.0) * FPS)
s_col = sa[f_col] + 8.0
col = S.column(s_col)
col.flash(f_col + 1)
s_ov = s_col + 260.0
W.overpass(S.road, S.M, S.env, s_ov)
pol = S.police()
po = S.pt(s_ov, -12.0, 6.75)
yaw_ov = S.yaw_at(s_ov) + math.pi / 2
rows_a = [dict(x=po.x, y=po.y, z=po.z, yaw=yaw_ov, v=0.0, ind=None, beacon=(t / FPS) >= S0 + 7.5)
          for t in range(int(C0 * FPS))]
# COST: the police estate overtakes in the middle lane, cuts in onto the shoulder ahead and stops
f_c = int(C0 * FPS)
pv = [(0, 25.0), (C0, 33.0), (C0 + 0.9, 33.0), (C0 + 2.0, 0.0)]
px = [(0, L1), (C0 + 0.7, L1), (C0 + 1.6, SH)]
S.track(pv, px, N, 0.0)
off = sa[f_c] - S.last_s[f_c] - 9.0
pb = S.track(pv, px, N, off, inds=[(C0 + 0.3, C0 + 1.6, "R")], beacon=(0.0, E0))
S.drive(pol, rows_a + pb[f_c:])
S.sign([("autobahn", 1.3)], HS + 40, S.x_sh + 2.2)

# ------------------------------------------------------------------ inserts
ins = S.ins
D = MW.dash_set(ins, (9000.0, 0.0, 1.5), red_zone=True, name="dash")
MW.needle(D, [(0, 0.5), (H0 + 0.9, 0.93), (S0 + 3.0, 0.9), (S0 + 4.0, 0.96), (S0 + 6.0, 0.94), (K0, 0.5),
              (T_END, 0.5)])
DC = D["cam"]
RX = 9100.0
ink = (0.08, 0.09, 0.1)
TN.box("rule_back", ins, (RX, 0.6, 2.0), (8.0, 0.1, 12.0), MW.mat("lt_back", (0.16, 0.17, 0.19), 0.8))
# speed bar: green (the limit), thin yellow, red with a prison window; a car icon slides into the red
for nm, x0, x1, colr in (("bar_g", -2.6, -0.4, (0.15, 0.7, 0.25)), ("bar_y", -0.4, 0.0, (0.95, 0.8, 0.1)),
                         ("bar_r", 0.0, 2.6, (0.85, 0.08, 0.06))):
    CY.flat(ins, nm, MW.rect(x1 - x0, 0.7, (x0 + x1) / 2, 0.0), colr, loc=(RX, 0.5, 2.5), emit=0.9)
win = bpy.data.objects.new("prison", None)
ins.objects.link(win)
win.location = (RX + 1.6, 0.48, 3.6)
CY.flat(ins, "pr_frame", MW.rect(1.0, 1.0), (0.95, 0.95, 0.93), emit=0.7, parent=win)
CY.flat(ins, "pr_in", MW.rect(0.8, 0.8), (0.12, 0.14, 0.18), emit=0.2, parent=win, z=0.005)
for k in range(4):
    CY.flat(ins, f"pr_bar{k}", MW.rect(0.07, 0.8, -0.3 + 0.2 * k, 0.0), (0.7, 0.72, 0.75), emit=0.6, parent=win,
            z=0.01)
car_i = bpy.data.objects.new("car_icon", None)
ins.objects.link(car_i)
CY.flat(ins, "ci_disc", CY.disc_pts(0.55, 32, 0, 0.2), (0.97, 0.97, 0.95), emit=0.6, parent=car_i)
CY.flat(ins, "ci_car", CY.car_icon_pts(0.38), ink, emit=0.0, parent=car_i, z=0.005)
for t, x in ((R0, -2.0), (R0 + 0.8, -2.0), (R0 + 2.4, 1.5), (R0 + 4.0, 1.5)):
    car_i.location = (RX + x, 0.46, 1.4)
    car_i.keyframe_insert("location", frame=int(t * FPS) + 1)
# three icons snap in: courthouse, a cut licence card, a car with a chain
icons = []
for k, x in enumerate((-2.2, 0.0, 2.2)):
    g = bpy.data.objects.new(f"icon{k}", None)
    ins.objects.link(g)
    g.location = (RX + x, 0.45, -0.6)
    CY.flat(ins, f"icon{k}_disc", CY.disc_pts(0.95, 48), (0.97, 0.97, 0.95), emit=0.6, parent=g)
    icons.append(g)
CY.flat(ins, "ct_roof", [(-0.62, 0.22), (0.62, 0.22), (0.0, 0.6)], ink, emit=0.0, parent=icons[0], z=0.005)
for k in range(4):
    CY.flat(ins, f"ct_col{k}", MW.rect(0.13, 0.62, -0.42 + 0.28 * k, -0.15), ink, emit=0.0, parent=icons[0], z=0.005)
CY.flat(ins, "ct_base", MW.rect(1.2, 0.14, 0, -0.52), ink, emit=0.0, parent=icons[0], z=0.005)
CY.flat(ins, "lc_card", MW.rect(1.2, 0.78), (0.75, 0.82, 0.9), emit=0.4, parent=icons[1], z=0.005)
CY.flat(ins, "lc_photo", MW.rect(0.3, 0.38, -0.33, 0.0), (0.4, 0.45, 0.55), emit=0.2, parent=icons[1], z=0.008)
for k in range(3):
    CY.flat(ins, f"lc_line{k}", MW.rect(0.48, 0.06, 0.2, 0.17 - 0.16 * k), (0.4, 0.45, 0.55), emit=0.2,
            parent=icons[1], z=0.008)
CY.flat(ins, "lc_cut", CY.bar_pts(-0.7, -0.55, 0.7, 0.55, 0.12), (0.9, 0.05, 0.05), emit=1.2, parent=icons[1],
        z=0.012)
CY.flat(ins, "ch_car", CY.car_icon_pts(0.6), ink, emit=0.0, parent=icons[2], z=0.005)
for k in range(5):
    a = (-0.75 + 0.3 * k, -0.45)
    ring = [(a[0] + 0.12 * math.cos(math.radians(d)), a[1] + 0.07 * math.sin(math.radians(d))) for d in range(0, 361, 30)]
    inner = [(a[0] + 0.07 * math.cos(math.radians(d)), a[1] + 0.03 * math.sin(math.radians(d))) for d in range(360, -1, -30)]
    CY.flat(ins, f"ch_link{k}", ring + inner, (0.55, 0.57, 0.6), emit=0.3, parent=icons[2], z=0.01)
for k, g in enumerate(icons):
    t_in = R0 + 4.3 + 0.9 * k
    for t, sc in ((0.0, 0.001), (t_in, 0.001), (t_in + 0.15, 1.15), (t_in + 0.3, 1.0)):
        g.scale = (sc, sc, sc)
        g.keyframe_insert("scale", frame=int(t * FPS) + 1)
ec_pos, ec_tgt, ec_scale = CY.end_card(ins, "ch", ["autobahn"], x0=-9000.0)

# ------------------------------------------------------------------ cameras
shots = jx.Shots(N)
V3 = Vector
shots.add("H_dial", 45, H0, H0 + 1.1, lambda t: (DC + V3((0.02, -0.45, 0.04)), DC + V3((0.0, 0.0, 0.0))))
shots.add("H_chase", 30, H0 + 1.1, SEG["HOOK"][1], lambda t: S.chase(ht, t, back=9.0, up=2.2, side=1.5))
shots.add("S_chase", 26, S0, S0 + 3.5, lambda t: S.chase(ht, t, back=10.0 + 2.0 * (t - S0), up=2.6, side=2.0,
                                                           ahead=40.0, look_up=3.0))
shots.add("S_dial", 45, S0 + 3.5, S0 + 6.5, lambda t: (DC + V3((0.0, -0.42, 0.03)), DC))
cp = S.pt(s_col, S.x_sh + 2.2)
shots.add("S_drone", 24, S0 + 6.5, SEG["SITUATION"][1],
          lambda t: (cp + V3((-6.0, -38.0 + 3 * (t - S0 - 6.5), 13.0)), cp + V3((-12.0, 110.0, 1.0))))
shots.add("R_bar", 40, R0, R0 + 4.0, lambda t: (V3((RX, -12.0, 2.6)), V3((RX, 0.0, 2.6))))
shots.add("R_icons", 40, R0 + 4.0, SEG["RULE"][1], lambda t: (V3((RX, -10.0, -0.6)), V3((RX, 0.0, -0.6))))
shots.add("C_chase", 26, C0, C0 + 2.2, lambda t: S.chase(ht, t, back=13.0, up=4.0, side=-3.0, ahead=25.0))
shots.add("C_window", 35, C0 + 2.2, SEG["COST"][1],
          lambda t: S.chase(ht, C0 + 2.2, back=0.6, up=1.25, side=-3.2, ahead=1.2, look_up=1.05))
shots.add("K_chase", 28, K0, K0 + 3.0, lambda t: S.chase(ht, t, back=9.0, up=2.4))
shots.add("K_dial", 45, K0 + 3.0, SEG["CORRECT"][1], lambda t: (DC + V3((0.0, -0.42, 0.03)), DC))
cam_e = shots.add("E_card", 50, E0, T_END, lambda t: (V3(ec_pos), V3(ec_tgt)))
cam_e.data.type, cam_e.data.ortho_scale = "ORTHO", ec_scale
for nm in ("H_dial", "S_dial", "K_dial"):
    cd = bpy.data.objects[nm].data
    cd.clip_start = 0.02
    cd.dof.use_dof, cd.dof.focus_distance, cd.dof.aperture_fstop = True, 0.45, 2.8

CY.sun_light(ASSETS, az_deg=150.0, elev_deg=34.0, energy=4.4)
MW.render(shots, OUT, RES, SAMPLES, FR, STILLS, N, haze=(0.66, 0.74, 0.86), haze_dist=3800.0, first="H_dial")
print("RENDER_DONE", FR, "signs", SG.sources_used().keys())
