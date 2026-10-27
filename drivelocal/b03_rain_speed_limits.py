"""Drive Like a Local B3, France: rain lowers the motorway limit. 9:16, 30 fps, canonical timeline from kit/country.py
TIMELINE["B03"] (HOOK 2.6, SITUATION 9.0, RULE 8.0, COST 5.0, CORRECT 7.5, END 4.2 = 36.3 s).
Set: a three-lane autoroute (kit/mway.py: French lane lines 3 m dash / 10 m gap, white edge lines), rain through
weather.apply("rain") with wheel spray, a grey fixed radar column (kit/enforcement.py, no brand), Commons B14 discs
and the C207 autoroute sign (signs/fr.json, unaltered). Hero: silver estate with a fictional German plate; locals and
the police estate (lettering removed, no emblem) with blank plates.
Run: python b03_rain_speed_limits.py OUTDIR --frames 1-1089 --res 540 --samples 8 --assets ASSETS [--stills 40,300]
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
import weather as WX  # noqa: E402

OUT, RES, SAMPLES, ASSETS, FR, STILLS = MW.cli(sys.argv)
FPS = MW.FPS
SEG, T_END = CY.spans("B03")
N = int(round(T_END * FPS))
H0, S0, R0, C0, K0, E0 = (SEG[k][0] for k in ("HOOK", "SITUATION", "RULE", "COST", "CORRECT", "END"))
# numeral signs only for VERIFIED keys (facts/fr.json, 26 Oct 2026: all three VERIFIED; tests/test_trackb_motorway.py
# checks this table against the facts file, because facts/ is not copied to the runners)
NUMERAL_OK = {"b14-130": True, "b14-110": True, "b14-100": True, "b14-80": True}
SG.setup(ASSETS)

S = MW.Stage(ASSETS, "fr", lanes=3, seed=4)
L0, L1, L2 = (S.lane_x(i) for i in range(3))
hero = jx.hero("estate", (0.62, 0.64, 0.67), "hero", "QZ RG 207", S.lib, S.traffic, metal=0.5)
CY.blank_plates([hero["coll"]])          # the story never says the driver came from Germany: blank like the locals
HS = 300.0
ht = S.track([(0, 36.0), (K0, 36.0), (K0 + 3.0, 30.0)], [(0, L1)], N, HS)
hs = S.last_s
S.drive(hero, ht)
c, tr = S.cars, S.trucks
lead = S.track([(0, 33.0)], [(0, L1)], N, HS + 99.0)
S.drive(c["saloon_white"], lead)
flow = S.traffic_flow(N, [(S.trucks["t_white"], 2, HS + 120, 25.0), (tr["t_blue"], 2, HS + 260, 25.0),
                          (tr["t_nord"], 2, HS + 430, 24.0), (c["hatch_red"], 0, HS - 70, 40.0),
                          (c["suv_dark"], 0, HS - 160, 41.0), (c["hatch_blue"], 2, HS + 40, 27.0),
                          (c["estate_grey"], -2, HS + 700, 33.0), (tr["t_alpen"], -1, HS + 900, 25.0),
                          (c["suv_white"], -3, HS + 1200, 36.0), (c["saloon_black"], -2, HS + 1500, 34.0)])
# police estate: catches up in the left lane and pulls alongside 1.0 s into COST, blue lights from COST
pol = S.police()
pk = [(0, 36.0), (C0 - 2.2, 36.0), (C0 - 1.4, 50.0), (C0 + 0.5, 50.0), (C0 + 1.1, 36.0), (K0, 36.0), (K0 + 3, 30.0)]
S.track(pk, [(0, L0)], N, 0.0)
f_al = int((C0 + 1.0) * FPS)
off = hs[f_al] - S.last_s[f_al] - 1.0
pt = S.track(pk, [(0, L0)], N, off, beacon=(C0, E0))
S.drive(pol, pt)
# radar column on the right verge where the hero passes at S0 + 7.0
s_col = hs[int((S0 + 7.0) * FPS)] + 6.0
col = S.column(s_col)
col.flash(int((S0 + 7.0) * FPS) + 1)
# signs: autoroute sign at the start, wet/dry discs along the way (B14 discs only when VERIFIED)
S.sign([("autoroute", 1.4)], HS + 60, S.x_sh + 2.0)
if NUMERAL_OK["b14-130"]:
    S.sign([("b14-130", 0.9)], hs[int((S0 + 4.2) * FPS)] + 40, S.x_sh + 2.0)

# ------------------------------------------------------------------ inserts (look pass 27 Oct: no flat studio panels)
ins = S.ins
IN.setup(ASSETS)
# the speedometer is the estate's own instrument cluster behind the wheel, seen from the driver's seat in the rain
PK.see_through(hero)
IN.cluster(hero, lambda t: 3.6 * ht[max(0, min(N - 1, int(round(t * FPS))))]["v"])
TOP, BOT, KD = IN.windscreen(hero)
cab = IN.cabin_cam(hero["obj"], hero)
IN.body_off_camera(hero, [(H0, H0 + 1.1), (S0 + 3.0, S0 + 6.0), (K0 + 3.2, E0)])
CEYE, CLOOK, CFOC = IN.cluster_view(hero)      # dials above the middle, wheel rim and hub below, road on top
# RULE: the 110, 100 and 80 discs stand in the world, in the rain (unaltered Commons files, B14 discs only when
# VERIFIED), far ahead where the hero never gets (s 1900 to 2140; the hero ends near s 1600), each dressed with the
# verge's trees and bushes, white marker posts and the delineators, so no empty plane fills the frame
import flora  # noqa: E402
R_SIGNS = [(k, s_) for k, s_ in (("b14-110", 1900.0), ("b14-100", 2020.0), ("b14-80", 2140.0)) if NUMERAL_OK[k]]
post_m, cap_m = MW.mat("rp_white", (0.88, 0.88, 0.86), 0.5), MW.mat("rp_red", (0.7, 0.06, 0.05), 0.5)
for k, s_ in R_SIGNS:
    S.sign([(k, 0.9)], s_, S.x_sh + 2.0)
    for ds in range(-40, 90, 20):
        q = S.pt(s_ + ds, S.x_sh + 1.7)
        TN.box("rp_post", ins, tuple(q + Vector((0, 0, 0.42))), (0.12, 0.12, 0.84), post_m, bevel=0.02)
        TN.box("rp_cap", ins, tuple(q + Vector((0, 0, 0.88))), (0.125, 0.125, 0.08), cap_m, bevel=0.02)
    pts = []
    for j in range(36):
        ds = -30.0 + 4.0 * j + (j * 7 % 3)
        for xo in (7.0 + (j * 13 % 5), 13.0 + (j * 11 % 7)):
            q = S.pt(s_ + ds, S.x_sh + xo)
            pts.append((q.x, q.y, q.z - 0.75))
    flora.scatter(f"r_trees{k}", pts, bpy.data.collections["lib_decid"], ins, smin=0.9, smax=1.4, seed=7 + len(k))
    bpts = [tuple(S.pt(s_ + ds, S.x_sh + 3.4 + (ds % 3)) - Vector((0, 0, 0.35))) for ds in range(-24, 70, 6)]
    if "lib_bush" in bpy.data.collections:
        flora.scatter(f"r_bush{k}", bpts, bpy.data.collections["lib_bush"], ins, smin=0.7, smax=1.1, seed=3)
ec_pos, ec_tgt, ec_scale = CY.end_card(ins, "fr", ["autoroute"] + [k for k in ("b14-130", "b14-110", "b14-100", "b14-80")
                                                                   if NUMERAL_OK[k]], x0=-9000.0)

# ------------------------------------------------------------------ cameras
shots = jx.Shots(N)
V3 = Vector
shots.add("H_wind", 30, H0, H0 + 1.1, lambda t: cab(t, CEYE, CLOOK))
shots.add("H_chase", 30, H0 + 1.1, SEG["HOOK"][1], lambda t: S.chase(ht, t, back=9.0, up=2.4))
shots.add("S_chase", 28, S0, S0 + 3.0, lambda t: S.chase(ht, t, back=10.0 - 0.6 * (t - S0), up=2.0, side=-1.2))
shots.add("S_dash", 30, S0 + 3.0, S0 + 6.0, lambda t: cab(t, CEYE + V3((0.0, 0.02 * (t - S0 - 3.0), 0.0)), CLOOK))
cp = S.pt(s_col, S.x_sh + 2.2)
shots.add("S_drone", 26, S0 + 6.0, SEG["SITUATION"][1],
          lambda t: (cp + V3((-26.0, -40.0 + 3 * (t - S0 - 6.0), 24.0)), cp + V3((-10.0, -5.0, 0.0))))
R_CUTS = [R0, R0 + 3.25, R0 + 4.95, SEG["RULE"][1]]


def sign_cam(s_, k):
    """Behind the outer guardrail, about 5 m before the disc: the sign mid-size on the right, the wet carriageway
    and its traffic receding on the left."""
    def f(t):
        u = t - R_CUTS[k]
        return (S.pt(s_ - 5.6 + 0.25 * u, S.x_sh + 2.3, 1.9), S.pt(s_ + 20.0, S.x_sh - 3.0, 1.5))
    return f


for k, (sid, s_) in enumerate(R_SIGNS):
    shots.add(f"R_sign{k}", 35, R_CUTS[k], R_CUTS[k + 1] if k < len(R_SIGNS) - 1 else SEG["RULE"][1], sign_cam(s_, k))
shots.add("C_chase", 28, C0, C0 + 2.0, lambda t: S.chase(ht, t, back=11.0, up=3.0, side=-3.0))
shots.add("C_close", 35, C0 + 2.0, SEG["COST"][1],
          lambda t: (S.chase(ht, t, back=9.0, up=3.4, side=-3.6, ahead=4.0, look_up=0.5)))
shots.add("K_chase", 28, K0, K0 + 3.2, lambda t: S.chase(ht, t, back=9.0, up=2.6, ahead=30.0))
shots.add("K_dash", 30, K0 + 3.2, SEG["CORRECT"][1], lambda t: cab(t, CEYE, CLOOK))
cam_e = shots.add("E_card", 50, E0, T_END, lambda t: (V3(ec_pos), V3(ec_tgt)))
cam_e.data.type, cam_e.data.ortho_scale = "ORTHO", ec_scale
for nm in ("H_wind", "S_dash", "K_dash"):
    cd = bpy.data.objects[nm].data
    cd.clip_start = 0.02
    cd.dof.use_dof, cd.dof.focus_distance, cd.dof.aperture_fstop = True, CFOC, 2.8

CY.sun_light(ASSETS, az_deg=200.0, elev_deg=28.0, energy=3.0, overcast=0.9)
WX.apply("rain", strength=1.0, seed=3)
MW.render(shots, OUT, RES, SAMPLES, FR, STILLS, N, haze=None, first="H_wind")
print("RENDER_DONE", FR, "signs", SG.sources_used().keys())
