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

# ------------------------------------------------------------------ inserts (far from the road)
ins = S.ins
D = MW.dash_set(ins, (9000.0, 0.0, 1.5), wiper=True, name="dash")
MW.needle(D, [(0, 0.78), (K0, 0.78), (K0 + 3.0, 0.65), (T_END, 0.65)])
MW.wipe(D, H0 + 0.6, K0, period=0.9)
MW.wipe(D, K0 + 0.01, E0, period=1.3)
for k, d in enumerate(D["drops"]):
    CY.show(d, [(H0 + 0.05 * (k % 30), H0 + 0.6 + 0.9 * (k % 4) + 0.3), (H0 + 2.0 + 0.04 * k, E0)])
MW.key_emit(D["rain"], [(1, 0.0), (int((K0 + 3.2) * FPS), 6.0)])
DC = D["cam"]

# RULE close-up: a rain cloud drops onto the 130 disc, which gives way to the 110 disc (digits only when VERIFIED)
RX = 9100.0
TN.box("rule_back", ins, (RX, 0.6, 2.0), (6.0, 0.1, 9.0), MW.mat("lt_back", (0.16, 0.17, 0.19), 0.8))
cloud = bpy.data.objects.new("cloud", None)
ins.objects.link(cloud)
for k, (x, z, r) in enumerate(((-0.45, 0.0, 0.42), (0.05, 0.22, 0.55), (0.55, 0.0, 0.4), (0.0, -0.12, 0.38))):
    CY.flat(ins, f"cloud{k}", CY.disc_pts(r, 40, x, z), (0.78, 0.8, 0.84), emit=0.5, parent=cloud)
for k in range(4):
    CY.flat(ins, f"cdrop{k}", CY.bar_pts(-0.45 + 0.3 * k, -0.6, -0.5 + 0.3 * k, -0.85, 0.07), (0.2, 0.55, 1.0),
            emit=1.5, parent=cloud, z=0.01)
for t, z in ((R0, 4.2), (R0 + 0.9, 3.15)):
    cloud.location = (RX, 0.2, z)
    cloud.keyframe_insert("location", frame=int(t * FPS) + 1)
if NUMERAL_OK["b14-130"] and NUMERAL_OK["b14-110"]:
    d130 = SG.face("b14-130", ins, 1.6, "fr", name="r_130", back=False)
    d110 = SG.face("b14-110", ins, 1.6, "fr", name="r_110", back=False)
    for d in (d130, d110):
        d.location = (RX, 0.3, 0.9)
    CY.show(d130, [(R0, R0 + 1.6)])
    CY.show(d110, [(R0 + 1.6, R0 + 4.0)])
    for t, sc in ((R0 + 1.6, 0.7), (R0 + 1.85, 1.08), (R0 + 2.0, 1.0)):
        d110.scale = (sc, sc, sc)
        d110.keyframe_insert("scale", frame=int(t * FPS) + 1)
else:
    CY.flat(ins, "r_arrow", CY.arrow_pts(1.2, 0.4, 0.6, 0.5), (0.95, 0.75, 0.1), loc=(RX, 0.3, 1.6),
            rot=(math.pi / 2, math.radians(90), 0))
# road cards: motorway, divided road, ordinary road; rain icon, dry disc, arrow, wet disc
CX = 9200.0
cards = [("autoroute", "b14-130", "b14-110"), (None, "b14-110", "b14-100"), (None, "b14-80", "b14-80")]
for k, (top, dry, wet) in enumerate(cards):
    x = CX + (k - 1) * 2.3
    TN.box(f"card{k}", ins, (x, 0.5, 2.0), (2.1, 0.08, 6.6), S.M.asph)
    for dz in (-2.6, -1.0, 0.6, 2.2):
        TN.box(f"card{k}_dash", ins, (x, 0.45, 2.0 + dz), (0.08, 0.02, 0.9), S.M.paint)
    if top:
        f = SG.face(top, ins, 1.3, "fr", name=f"card{k}_top", back=False)
        f.location = (x, 0.35, 4.4)
    rc = bpy.data.objects.new(f"card{k}_rain", None)
    ins.objects.link(rc)
    rc.location, rc.scale = (x, 0.3, 4.05), (0.45, 0.45, 0.45)
    for j, (cx_, cz, r) in enumerate(((-0.45, 0.0, 0.42), (0.05, 0.22, 0.55), (0.55, 0.0, 0.4))):
        CY.flat(ins, f"card{k}_c{j}", CY.disc_pts(r, 32, cx_, cz), (0.85, 0.87, 0.9), emit=0.6, parent=rc)
    if NUMERAL_OK[dry] and NUMERAL_OK[wet]:
        for nm, z in ((dry, 2.6), (wet, 0.25)):
            f = SG.face(nm, ins, 1.05, "fr", name=f"card{k}_{nm}", back=False)
            f.location = (x, 0.35, z)
    col_a = (0.95, 0.75, 0.1) if dry != wet else (0.3, 0.8, 0.35)
    CY.flat(ins, f"card{k}_arrow", CY.arrow_pts(0.8, 0.22, 0.4, 0.34), col_a, loc=(x, 0.33, 2.15),
            rot=(math.pi / 2, math.radians(90), 0))
ec_pos, ec_tgt, ec_scale = CY.end_card(ins, "fr", ["autoroute"] + [k for k in ("b14-130", "b14-110", "b14-100", "b14-80")
                                                                   if NUMERAL_OK[k]], x0=-9000.0)

# ------------------------------------------------------------------ cameras
shots = jx.Shots(N)
V3 = Vector
shots.add("H_wind", 30, H0, H0 + 1.1, lambda t: (DC + V3((0.05, -0.62, 0.22)), DC + V3((0.0, 0.5, 0.42))))
shots.add("H_chase", 30, H0 + 1.1, SEG["HOOK"][1], lambda t: S.chase(ht, t, back=9.0, up=2.4))
shots.add("S_chase", 28, S0, S0 + 3.0, lambda t: S.chase(ht, t, back=10.0 - 0.6 * (t - S0), up=2.0, side=-1.2))
shots.add("S_dash", 45, S0 + 3.0, S0 + 6.0, lambda t: (DC + V3((0.0, -0.5, 0.05)), DC + V3((0.0, 0.0, 0.02))))
cp = S.pt(s_col, S.x_sh + 2.2)
shots.add("S_drone", 26, S0 + 6.0, SEG["SITUATION"][1],
          lambda t: (cp + V3((-26.0, -40.0 + 3 * (t - S0 - 6.0), 24.0)), cp + V3((-10.0, -5.0, 0.0))))
shots.add("R_cloud", 40, R0, R0 + 4.0, lambda t: (V3((RX, -9.0, 1.9)), V3((RX, 0.0, 1.9))))
cam_rc = shots.add("R_cards", 50, R0 + 4.0, SEG["RULE"][1], lambda t: (V3((CX, -30.0, 2.2)), V3((CX, 0.0, 2.2))))
cam_rc.data.type, cam_rc.data.ortho_scale = "ORTHO", 13.0   # three cards, 6.9 m wide, in a 9:16 frame
shots.add("C_chase", 28, C0, C0 + 2.0, lambda t: S.chase(ht, t, back=11.0, up=3.0, side=-3.0))
shots.add("C_close", 35, C0 + 2.0, SEG["COST"][1],
          lambda t: (S.chase(ht, t, back=2.6, up=1.5, side=-1.9, ahead=0.4, look_up=0.9)))
shots.add("K_chase", 28, K0, K0 + 3.2, lambda t: S.chase(ht, t, back=9.0, up=2.6, ahead=30.0))
shots.add("K_dash", 45, K0 + 3.2, SEG["CORRECT"][1], lambda t: (DC + V3((0.0, -0.5, 0.05)), DC + V3((0, 0, 0.02))))
cam_e = shots.add("E_card", 50, E0, T_END, lambda t: (V3(ec_pos), V3(ec_tgt)))
cam_e.data.type, cam_e.data.ortho_scale = "ORTHO", ec_scale
for nm in ("H_wind", "S_dash", "K_dash"):
    cd = bpy.data.objects[nm].data
    cd.clip_start = 0.02
    cd.dof.use_dof, cd.dof.focus_distance, cd.dof.aperture_fstop = True, 0.5, 2.8

CY.sun_light(ASSETS, az_deg=200.0, elev_deg=28.0, energy=3.0, overcast=0.9)
WX.apply("rain", strength=1.0, seed=3)
MW.render(shots, OUT, RES, SAMPLES, FR, STILLS, N, haze=None, first="H_wind")
print("RENDER_DONE", FR, "signs", SG.sources_used().keys())
