"""Drive Like a Local B7, France: breakdown on the autoroute, only the approved operator may tow. 9:16, 30 fps,
canonical timeline from kit/country.py TIMELINE["B07"] (HOOK 2.6, SITUATION 9.0, RULE 8.0, COST 6.0, CORRECT 7.0,
END 4.2 = 36.8 s).
Set: a two-lane autoroute with hard shoulder at dusk (kit/mway.py: French lane lines 3 m dash / 10 m gap, white edge
lines; weather.apply("dusk")), an outer guardrail, the kit's orange emergency post with its lettering removed and no
arrows on the guide posts, the C207 autoroute sign (signs/fr.json). fr emergency-call is missing on Commons: not shown.
Assistance van and tow vehicle are generic (vehicles' van body, no brand, no text, blank plates); the tow vehicle
carries an amber beacon and a flat-deck trailer. Hero: silver estate with a fictional German plate.
Run: python b07_motorway_breakdown.py OUTDIR --frames 1-1104 --res 540 --samples 8 --assets ASSETS [--stills 40,300]
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
import motion  # noqa: E402
import mway as MW  # noqa: E402
import signs as SG  # noqa: E402
import town as TN  # noqa: E402
import townplus as TP  # noqa: E402
import vehicles as V  # noqa: E402
import weather as WX  # noqa: E402
import world as W  # noqa: E402

OUT, RES, SAMPLES, ASSETS, FR, STILLS = MW.cli(sys.argv)
FPS = MW.FPS
SEG, T_END = CY.spans("B07")
N = int(round(T_END * FPS))
H0, S0, R0, C0, K0, E0 = (SEG[k][0] for k in ("HOOK", "SITUATION", "RULE", "COST", "CORRECT", "END"))
SG.setup(ASSETS)

S = MW.Stage(ASSETS, "fr", lanes=2, seed=9, crest=())   # flat: the walkers bake at z = 0
L0, L1 = S.lane_x(0), S.lane_x(1)
SH = S.shoulder_x()
XG = S.x_sh + 2.1                      # footpath behind the outer guardrail
hero = jx.hero("estate", (0.62, 0.64, 0.67), "hero", "QZ PN 707", S.lib, S.traffic, metal=0.5)
HS = 400.0
ta = S.track([(0, 33.0), (H0 + 0.3, 33.0), (H0 + 2.4, 10.0), (H0 + 4.2, 0.0)], [(0, L1), (H0 + 1.0, L1),
                                                                                  (H0 + 2.2, SH)], N, HS,
             inds=[(H0 + 0.3, T_END, "H")])
s_e = S.last_s[-1]
# CORRECT: winched forward onto the trailer deck (0.5 m up) from K0 + 5.0
rows = ta[:int((K0 + 5.0) * FPS)]
for f in range(int((K0 + 5.0) * FPS), N):
    u = min(1.0, (f / FPS - K0 - 5.0) / 1.8)
    p = S.pt(s_e + 6.2 * u, SH, 0.5 * min(1.0, u * 1.6))
    r = dict(ta[f])
    r.update(x=p.x, y=p.y, z=p.z, v=1.2 if u < 1 else 0.0)
    rows.append(r)
S.drive(hero, rows)
c, tr = S.cars, S.trucks
S.traffic_flow(N, [(tr["t_white"], 1, HS + 20, 24.0), (tr["t_blue"], 1, HS - 120, 25.0),
                   (c["hatch_red"], 0, HS - 60, 35.0), (tr["t_nord"], 1, HS - 300, 24.0),
                   (c["suv_white"], 0, HS - 260, 36.0), (tr["t_alpen"], 1, HS - 520, 25.0),
                   (c["saloon_black"], 0, HS - 600, 35.0), (c["estate_grey"], -1, HS + 900, 33.0),
                   (tr["t_white"], -2, HS + 1100, 24.0)])
for k in range(3):
    S.traffic_flow(N, [(c["hatch_blue"], 1, HS - 700 - 400 * k, 30.0)])
# orange emergency post 9 m ahead of the estate, behind the guardrail, its lettering removed
NR = W.emergency_phone(S.M, S.lib)
for o in list(NR.all_objects):
    if o.name.startswith("notruf_t") or o.type == "FONT":
        bpy.data.objects.remove(o)
s_post = s_e + 9.0
S.road.place(NR, s_post, XG + 0.5, -0.3, c=S.env, name="post_fr")
S.sign([("autoroute", 1.4)], HS - 150, S.x_sh + 2.2)
# tow vehicle: van body, amber beacon, flat-deck trailer; passes the estate on the shoulder and stops ahead of it
tow_c = V.car("van", (0.93, 0.93, 0.92), "tow", "QX TW 22", metal=0.0, c=S.lib)
CY.blank_plates([tow_c])
amber = MW.mat("tow_beacon", (1.0, 0.45, 0.02), 0.3, emit=(1.0, 0.45, 0.02), estr=0.0)
MW.key_emit(amber, MW.blink_pairs(K0 + 2.0, E0, period=0.5, on=14.0))
TN.box("tow_bar", tow_c, (0.0, 0.6, 2.55), (1.3, 0.25, 0.12), amber, bevel=0.03)
deck_m = MW.mat("tow_deck", (0.3, 0.31, 0.33), 0.5, metal=0.6)
TN.box("tow_deck", tow_c, (0.0, -5.3, 0.62), (2.1, 4.8, 0.12), deck_m, bevel=0.02)
TN.box("tow_ramp", tow_c, (0.0, -8.0, 0.32), (1.9, 0.9, 0.06), deck_m)
TN.box("tow_bar_hitch", tow_c, (0.0, -2.55, 0.45), (0.15, 1.2, 0.12), deck_m)
for y in (-4.7, -5.6):
    for x in (-0.95, 0.95):
        TN.box("tow_wheel", tow_c, (x, y, 0.32), (0.22, 0.62, 0.62), MW.mat("tow_tyre", (0.02, 0.02, 0.02), 0.8),
               bevel=0.1)
s_tow = s_e + 14.5
tk = [(0, 22.0), (K0 + 1.6, 22.0), (K0 + 3.6, 0.0)]
S.track(tk, [(0, L1)], N, 0.0)
off = s_tow - S.last_s[-1]
tt = S.track(tk, [(0, L1), (K0 + 1.0, L1), (K0 + 2.6, SH)], N, off, inds=[(K0 + 0.8, K0 + 2.4, "R")])
S.drive(tow_c, tt)
# winch line from the deck to the estate's nose while winching
wl = TN.box("winch", S.env, (0, 0, 0), (0.02, 1.0, 0.02), MW.mat("winch_m", (0.1, 0.1, 0.1), 0.5))
pa, pb = S.pt(s_tow - 8.2, SH, 0.6), S.pt(s_e + 2.4, SH, 0.5)
wl.location = (pa + pb) / 2
wl.scale.y = (pa - pb).length
wl.rotation_euler[2] = math.atan2(pb.x - pa.x, pa.y - pb.y)
CY.show(wl, [(K0 + 4.6, K0 + 6.8)])
# driver walks behind the guardrail to the post in RULE; driver and passenger in yellow vests stand there in CORRECT
vest = (0.95, 0.85, 0.05)
peds = [TP.pedestrian(S.env, "driver", seed=2, coat=vest), TP.pedestrian(S.env, "passenger", seed=5, coat=vest)]
P0, P1 = S.pt(s_e - 3.0, XG), S.pt(s_post - 1.0, XG)
pth = jx.Path([(P0.x, P0.y), (P1.x, P1.y)])
Lp = (P1 - P0).length
sv = []
for f in range(N):
    t = f / FPS
    if R0 <= t < K0:
        u = min(1.0, (t - R0) / 3.4)
        sv.append((Lp * u, 1.4 if u < 1 else 0.0))
    else:
        sv.append((0.0, 0.0))
TP.walk(peds[0], pth, sv, list(range(1, N + 1)))
P2 = S.pt(s_e - 5.0, XG + 0.6)
peds[1]["root"].location = (P2.x, P2.y, P2.z)
peds[1]["root"].rotation_euler[2] = S.yaw_at(s_e) - math.pi / 2 + 0.5
CY.show(peds[0]["root"], [(R0, E0)])
CY.show(peds[1]["root"], [(K0, E0)])

# ------------------------------------------------------------------ inserts
ins = S.ins
D = MW.dash_set(ins, (9000.0, 0.0, 1.5), name="dash")
MW.needle(D, [(0, 0.62), (H0 + 0.3, 0.62), (H0 + 2.4, 0.2), (H0 + 3.6, 0.0)])
MW.key_emit(D["lamp"], [(1, 0.0), (int(H0 * FPS) + 3, 9.0)])
MW.key_emit(D["haz"], MW.blink_pairs(H0 + 0.3, T_END, on=10.0))
hb = D["hazbtn"]
for t, y in ((H0 + 0.25, hb.location.y), (H0 + 0.33, hb.location.y + 0.012), (H0 + 0.45, hb.location.y)):
    hb.location.y = y
    hb.keyframe_insert("location", frame=int(t * FPS) + 1)
DC = D["cam"]
rc = bpy.data.objects.new("receipt", None)
ins.objects.link(rc)
CY.flat(ins, "rc_paper", MW.rect(0.16, 0.26), (0.96, 0.96, 0.94), emit=0.5, parent=rc)
for k in range(7):
    CY.flat(ins, f"rc_line{k}", MW.rect(0.11 - 0.03 * (k % 2), 0.008, -0.01, 0.09 - 0.03 * k), (0.5, 0.52, 0.55),
            emit=0.3, parent=rc, z=0.002)
for t, z in ((C0, 0.9), (C0 + 0.7, 1.5)):
    rc.location = (DC.x, DC.y - 0.12, z)
    rc.keyframe_insert("location", frame=int(t * FPS) + 1)
PH = Vector((9300.0, 0.0, 1.2))


def screen_call(c, p):
    """Call screen: a shield icon (no brand), signal bars and a green call button; no text."""
    z = 0.0004
    CY.flat(c, "call_shield", [(-0.016, 0.03), (0.016, 0.03), (0.016, 0.01), (0.0, -0.008), (-0.016, 0.01)],
            (0.2, 0.45, 0.85), 1.1, rot=(0, 0, 0), parent=p, z=z)
    for k in range(3):
        CY.flat(c, "call_bar", MW.rect(0.004, 0.006 + 0.004 * k, -0.008 + 0.008 * k, -0.025 + 0.002 * k),
                (0.85, 0.87, 0.9), 1.0, rot=(0, 0, 0), parent=p, z=z)
    CY.flat(c, "call_btn", CY.disc_pts(0.009, 32, 0.0, -0.05), (0.1, 0.7, 0.3), 1.2, rot=(0, 0, 0), parent=p, z=z)


ph = CY.phone(ins, "phone_call", tuple(PH), (math.pi / 2, 0, 0), {"call": ([(0, 999)], screen_call)})
for t, rz in ((S0, 0.0), (S0 + 1.0, 0.06), (S0 + 1.5, -0.04), (S0 + 2.0, 0.05), (S0 + 3.0, 0.0)):
    ph.rotation_euler = (math.pi / 2 + rz, 0, 0)
    ph.keyframe_insert("rotation_euler", frame=int(t * FPS) + 1)
# the motorway entrance gate: ramp end with a barrier; the white assistance van stops there
GX = Vector((9600.0, 0.0, 0.0))
TN.box("gate_road", ins, tuple(GX + Vector((0, 0, -0.05))), (7.0, 80.0, 0.1), S.M.asph)
TN.box("gate_grass", ins, tuple(GX + Vector((0, 0, -0.12))), (200.0, 200.0, 0.1), S.M.grass)
TN.box("gate_post", ins, tuple(GX + Vector((3.8, 20.0, 0.6))), (0.4, 0.4, 1.2), S.M.concrete)
for k in range(6):
    TN.box("gate_boom", ins, tuple(GX + Vector((3.3 - 0.6 * k, 20.0, 1.0))), (0.6, 0.1, 0.1),
           MW.mat("boom_r" if k % 2 else "boom_w", (0.75, 0.05, 0.04) if k % 2 else (0.92, 0.92, 0.9), 0.5))
van = W.instance(S.vans["van_white"], tuple(GX), c=S.traffic)
rv = motion.rig(van)
vrows = []
for f in range(N):
    t = f / FPS
    u = min(1.0, max(0.0, (t - S0 - 3.0) / 1.6))
    e = 1 - (1 - u) ** 2
    vrows.append(dict(x=GX.x + 1.6, y=GX.y - 20.0 + 35.0 * e, z=0.0, yaw=math.pi / 2, v=35.0 / 1.6 * 2 * (1 - u) / 2,
                      ind=None))
motion.bake(rv, vrows)
nb = MW.badge(ins, "gate_no", "no", tuple(GX + Vector((1.6, 13.0, 4.2))), size=0.9)
CY.show(nb, [(S0 + 4.2, R0)])
# RULE top view: the tow vehicle (glows green) beside the plain van (stays grey)
TX = Vector((9800.0, 0.0, 0.0))
TN.box("top_ground", ins, tuple(TX + Vector((0, 0, -0.05))), (30.0, 40.0, 0.1), S.M.asph_sh)
W.instance(tow_c, tuple(TX + Vector((-2.2, 2.5, 0.0))), rz=0.0, c=ins)
W.instance(S.vans["van_white"], tuple(TX + Vector((2.2, 0.0, 0.0))), c=ins)
glow = CY.flat(ins, "top_glow", MW.rect(3.2, 13.5, 0.0, 0.0), (0.1, 0.9, 0.3), emit=2.0,
               loc=tuple(TX + Vector((-2.2, -0.2, 0.01))), rot=(0, 0, 0))
CY.show(glow, [(R0 + 4.5, C0)])
ec_pos, ec_tgt, ec_scale = CY.end_card(ins, "fr", ["autoroute"], x0=-9000.0)

# ------------------------------------------------------------------ cameras
shots = jx.Shots(N)
V3 = Vector
shots.add("H_dash", 40, H0, H0 + 1.1, lambda t: (DC + V3((0.08, -0.5, 0.0)), DC + V3((0.04, 0.0, -0.05))))
shots.add("H_chase", 28, H0 + 1.1, SEG["HOOK"][1], lambda t: S.chase(ta, t, back=9.0, up=2.2, side=-1.0))
shots.add("S_phone", 40, S0, S0 + 3.0, lambda t: (PH + V3((0.0, -0.32, 0.02)), PH))
shots.add("S_gate", 26, S0 + 3.0, S0 + 6.0, lambda t: (GX + V3((14.0, -24.0, 12.0)), GX + V3((0.0, 12.0, 1.0))))
ep = S.pt(s_e, SH)
shots.add("S_chase", 28, S0 + 6.0, SEG["SITUATION"][1],
          lambda t: (S.pt(s_e - 12.0, SH + 0.8, 1.7), S.pt(s_e + 30.0, L1 - 1.0, 1.2)))
shots.add("R_walk", 32, R0, R0 + 4.0, lambda t: (S.pt(s_e - 5.0 + 1.2 * (t - R0), XG + 4.5, 1.7),
                                                  S.pt(s_e + 1.0 + 1.6 * (t - R0), XG, 1.1)))
cam_t = shots.add("R_top", 50, R0 + 4.0, SEG["RULE"][1], lambda t: (TX + V3((0, -0.01, 40.0)), TX))
cam_t.data.type, cam_t.data.ortho_scale = "ORTHO", 16.0
shots.add("C_receipt", 40, C0, SEG["COST"][1], lambda t: (DC + V3((0.0, -0.55, 0.05)), DC + V3((0, 0, 0.02))))
shots.add("K_drone", 26, K0, K0 + 3.0, lambda t: (ep + V3((-14.0, -26.0, 14.0)), ep + V3((2.0, 0.0, 0.5))))
shots.add("K_chase", 28, K0 + 3.0, SEG["CORRECT"][1],
          lambda t: (S.pt(s_e - 14.0, SH - 1.5, 2.6), S.pt(s_e + 10.0, SH, 1.0)))
cam_e = shots.add("E_card", 50, E0, T_END, lambda t: (V3(ec_pos), V3(ec_tgt)))
cam_e.data.type, cam_e.data.ortho_scale = "ORTHO", ec_scale
for nm in ("H_dash", "S_phone", "C_receipt"):
    bpy.data.objects[nm].data.clip_start = 0.02

CY.sun_light(ASSETS, az_deg=250.0, elev_deg=7.0, energy=3.2, warm=True)
WX.apply("dusk", strength=1.0, seed=2)
MW.render(shots, OUT, RES, SAMPLES, FR, STILLS, N, haze=None, first="H_dash")
print("RENDER_DONE", FR, "signs", SG.sources_used().keys())
