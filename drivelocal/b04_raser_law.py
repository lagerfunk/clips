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
import inserts as IN  # noqa: E402
import parking as PK  # noqa: E402
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
CY.blank_plates([hero["coll"]])          # the story never says the driver came from Germany: blank like the locals
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

# ------------------------------------------------------------------ inserts (look pass 27 Oct: no flat studio panels)
ins = S.ins
IN.setup(ASSETS)
# the speedometer is the saloon's own instrument cluster behind the wheel, needle from the hero's real speed
PK.see_through(hero)
IN.cluster(hero, lambda t: 3.6 * ht[max(0, min(N - 1, int(round(t * FPS))))]["v"])
TOP, BOT, KD = IN.windscreen(hero)
cab = IN.cabin_cam(hero["obj"], hero)
IN.body_off_camera(hero, [(H0, H0 + 1.1), (S0 + 2.4, S0 + 5.1), (K0 + 3.0, E0)])
CEYE, CLOOK, CFOC = IN.cluster_view(hero)      # dials above the middle, wheel rim and hub below, road on top
ec_pos, ec_tgt, ec_scale = CY.end_card(ins, "ch", ["autobahn"], x0=-9000.0)

# ------------------------------------------------------------------ cameras
shots = jx.Shots(N)
V3 = Vector
shots.add("H_dial", 30, H0, H0 + 1.1, lambda t: cab(t, CEYE, CLOOK))
shots.add("H_chase", 30, H0 + 1.1, SEG["HOOK"][1], lambda t: S.chase(ht, t, back=9.0, up=2.2, side=1.5))
# SITUATION cut on its captions: empty lane (chase), the needle (cluster), "A grey column. A flash." on the column
# mid-size from the verge as the saloon flashes past at S0 + 7.0, "Police." on the police estate waiting on the overpass
shots.add("S_chase", 26, S0, S0 + 2.4, lambda t: S.chase(ht, t, back=10.0 + 2.0 * (t - S0), up=2.6, side=2.0,
                                                           ahead=40.0, look_up=3.0))
shots.add("S_dial", 30, S0 + 2.4, S0 + 5.1, lambda t: cab(t, CEYE + V3((0.0, 0.02 * (t - S0 - 2.4), 0.0)), CLOOK))
shots.add("S_column", 30, S0 + 5.1, S0 + 7.3, lambda t: (S.pt(s_col - 9.0 + 0.3 * (t - S0 - 5.1), S.x_sh + 3.8, 1.5),
                                                          S.pt(s_col + 2.0, S.x_sh + 0.5, 1.9)))
shots.add("S_police", 35, S0 + 7.3, SEG["SITUATION"][1],
          lambda t: (S.pt(s_ov - 9.5 + 0.3 * (t - S0 - 7.3), -3.5, 7.9), V3(po) + V3((0.0, 0.0, 0.5))))
# RULE in the world: the enforcement column with traffic passing, then the column, overpass and the police estate
# waiting with blue lights from above
shots.add("R_bar", 30, R0, R0 + 4.0, lambda t: (S.pt(s_col - 34.0 + 1.5 * (t - R0), S.x_sh + 1.2, 1.7),
                                                S.pt(s_col + 6.0, S.x_sh + 1.0, 2.4)))
shots.add("R_icons", 26, R0 + 4.0, SEG["RULE"][1], lambda t: (S.pt(s_col - 60.0 + 2.0 * (t - R0 - 4.0), S.x_sh + 14.0,
                                                                   20.0), S.pt(s_col + 170.0, 0.0, 2.0)))
shots.add("C_chase", 26, C0, C0 + 2.2, lambda t: S.chase(ht, t, back=13.0, up=4.0, side=-3.0, ahead=25.0))
shots.add("C_window", 30, C0 + 2.2, SEG["COST"][1],          # police estate leading the saloon onto the shoulder
          lambda t: S.chase(ht, t, back=12.0, up=5.0, side=-4.0, ahead=14.0, look_up=0.5))
shots.add("K_chase", 28, K0, K0 + 3.0, lambda t: S.chase(ht, t, back=9.0, up=2.4))
shots.add("K_dial", 30, K0 + 3.0, SEG["CORRECT"][1], lambda t: cab(t, CEYE, CLOOK))
cam_e = shots.add("E_card", 50, E0, T_END, lambda t: (V3(ec_pos), V3(ec_tgt)))
cam_e.data.type, cam_e.data.ortho_scale = "ORTHO", ec_scale
for nm in ("H_dial", "S_dial", "K_dial"):
    cd = bpy.data.objects[nm].data
    cd.clip_start = 0.02
    cd.dof.use_dof, cd.dof.focus_distance, cd.dof.aperture_fstop = True, CFOC, 2.8

CY.sun_light(ASSETS, az_deg=150.0, elev_deg=34.0, energy=4.4)
MW.render(shots, OUT, RES, SAMPLES, FR, STILLS, N, haze=(0.66, 0.74, 0.86), haze_dist=3800.0, first="H_dial")
print("RENDER_DONE", FR, "signs", SG.sources_used().keys())
