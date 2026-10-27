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
import figures as F  # noqa: E402
import inserts as IN  # noqa: E402
import jx  # noqa: E402
import motion  # noqa: E402
import mway as MW  # noqa: E402
import parking as PK  # noqa: E402
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
# every number on an insert comes from a VERIFIED key of facts/fr.json (tests/test_trackb_motorway.py checks them)
NUMBERS = {"fr_motorway_breakdown_price_weekday": "151,00 € TTC",
           "fr_motorway_breakdown_price_evening_weekend": "226,50 € TTC"}

S = MW.Stage(ASSETS, "fr", lanes=2, seed=9, crest=())   # flat: the walkers bake at z = 0
L0, L1 = S.lane_x(0), S.lane_x(1)
SH = S.shoulder_x()
XG = S.x_sh + 2.1                      # footpath behind the outer guardrail
hero = jx.hero("estate", (0.62, 0.64, 0.67), "hero", "QZ PN 707", S.lib, S.traffic, metal=0.5)
CY.blank_plates([hero["coll"]])          # the story never says the driver came from Germany: blank like the locals
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
peds = [F.person(S.env, "driver", seed=2, hiviz=True), F.person(S.env, "passenger", seed=5, hiviz=True)]
P0, P1 = S.pt(s_e - 3.0, XG), S.pt(s_post - 1.0, XG)
pth = jx.Path([(P0.x, P0.y), (P1.x, P1.y)])
Lp = (P1 - P0).length
sv = []
for f in range(N):
    t = f / FPS
    if R0 <= t < K0:
        u = min(1.0, (t - R0) * 1.45 / Lp)             # a real walk (1.45 m/s): 3.4 s for 11 m read as a stretched run
        sv.append((Lp * u, 1.45 if u < 1 else 0.0))
    else:
        sv.append((0.0, 0.0))
F.walk(peds[0], pth, sv, ground=lambda x, y: P0.z)
P2 = S.pt(s_e - 5.0, XG + 0.6)
F.stand(peds[1], (P2.x, P2.y), (P1.x, P1.y), N, ground=lambda x, y: P2.z)
CY.show(peds[0]["arm"], [(R0, E0)])
CY.show(peds[1]["arm"], [(K0, E0)])

# ------------------------------------------------------------------ inserts (look pass 27 Oct: no flat studio panels)
ins = S.ins
IN.setup(ASSETS)
PK.see_through(hero)
# HOOK: the estate's own instrument cluster behind the wheel: needle from the track, an amber fault lamp, the two green
# hazard arrows blinking
IN.cluster(hero, lambda t: 3.6 * ta[max(0, min(N - 1, int(round(t * FPS))))]["v"])
hc = hero["coll"]
CLG = bpy.data.objects["cluster"]
warn = CY.flat(hc, "cl_warn", CY.disc_pts(0.0075, 24, 0.0, -0.03), (1.0, 0.55, 0.05), 3.0, rot=(0, 0, 0), parent=CLG,
               z=0.0009)
IN.text(hc, "!", 0.0105, (0.06, 0.03, 0.0), (0.0, -0.0345, 0.0011), CLG, align="CENTER", kind="bold")
CY.show(warn, [(H0 + 0.05, T_END)])
blink = [(t0, t0 + 0.33) for t0 in [H0 + 0.3 + 0.66 * k for k in range(60)] if t0 < T_END]
for sg in (-1, 1):
    a = CY.flat(hc, "cl_haz", [(sg * 0.016, 0.042), (sg * 0.008, 0.048), (sg * 0.008, 0.036)], (0.1, 1.0, 0.35), 3.0,
                rot=(0, 0, 0), parent=CLG, z=0.0009)
    CY.show(a, blink)
TOP, BOT, KD = IN.windscreen(hero)
CEYE, CLOOK, CFOC = IN.cluster_view(hero)      # dials above the middle, wheel rim and hub below, road on top
GL = 1.6                       # phone screen glow inside the cabin at dusk


def scr_call(c, p, e):
    """Call screen (French, no brand, no digits): caller disc with a person glyph, name, 'call in progress', three
    round controls and the red hang-up button."""
    z = 0.0004
    IN.rrect(c, p, -IN.SW / 2, -IN.SH / 2, IN.SW / 2, IN.SH / 2 - 0.006, (0.11, 0.13, 0.16), e * 0.6, z - 0.0001,
             r=0.0001)
    CY.flat(c, "av", CY.disc_pts(0.014, 40, 0.0, 0.038), (0.25, 0.45, 0.7), e, rot=(0, 0, 0), parent=p, z=z)
    CY.flat(c, "av_h", CY.disc_pts(0.0045, 24, 0.0, 0.043), (0.92, 0.94, 0.96), e, rot=(0, 0, 0), parent=p, z=z + 0.0001)
    CY.flat(c, "av_b", [(0.0085 * math.cos(math.pi * k / 16), 0.03 + 0.0075 * math.sin(math.pi * k / 16))
                        for k in range(17)], (0.92, 0.94, 0.96), e, rot=(0, 0, 0), parent=p, z=z + 0.0001)
    IN.text(c, "Mon assistance", 0.0068, (1, 1, 1), (0.0, 0.0125, z), p, align="CENTER", kind="bold", emit=e * 1.2)
    IN.text(c, "Appel en cours…", 0.0046, (0.7, 0.74, 0.8), (0.0, 0.004, z), p, align="CENTER", emit=e)
    for lab, x in (("Muet", -0.02), ("Clavier", 0.0), ("Haut-parleur", 0.02)):
        CY.flat(c, "ctl", CY.disc_pts(0.0068, 32, x, -0.022), (0.3, 0.33, 0.38), e, rot=(0, 0, 0), parent=p, z=z)
        IN.text(c, lab, 0.0027, (0.8, 0.82, 0.86), (x, -0.0335, z), p, align="CENTER", emit=e)
    CY.flat(c, "mic", CY.bar_pts(-0.02, -0.0245, -0.02, -0.0185, 0.0022), (1, 1, 1), e, rot=(0, 0, 0), parent=p,
            z=z + 0.0001)
    for i in range(3):
        for j in range(3):
            CY.flat(c, "kp", CY.disc_pts(0.0008, 8, -0.0026 + 0.0026 * i, -0.0194 - 0.0026 * j), (1, 1, 1), e,
                    rot=(0, 0, 0), parent=p, z=z + 0.0001)
    CY.flat(c, "spk", [(0.0168, -0.0235), (0.0188, -0.0235), (0.0222, -0.0262), (0.0222, -0.0178), (0.0188, -0.0205),
                       (0.0168, -0.0205)], (1, 1, 1), e, rot=(0, 0, 0), parent=p, z=z + 0.0001)
    CY.flat(c, "hang", CY.disc_pts(0.0095, 40, 0.0, -0.052), (0.86, 0.14, 0.12), e * 1.2, rot=(0, 0, 0), parent=p, z=z)
    CY.flat(c, "hang_h", CY.bar_pts(-0.0055, -0.0515, 0.0055, -0.0515, 0.0032), (1, 1, 1), e * 1.2, rot=(0, 0, 0),
            parent=p, z=z + 0.0001)


ph = IN.phone(ins, "phone_dash", (0, 0, 0), (0, 0, 0), {"call": ([(S0, S0 + 2.4)], scr_call)}, glow=GL)
IN.dash_mount(hero, ph)
IN.adopt(hero)
cab = IN.cabin_cam(hero["obj"], hero)
IN.body_off_camera(hero, [(H0, H0 + 1.1), (S0, S0 + 2.4)])
PHL = Vector((-0.06, BOT.y - 0.36, BOT.z + 0.045))           # phone centre in the car's frame
EYE = PHL + Vector((-0.16, -0.36, 0.105))
LOOK = PHL + Vector((0.04, 0.0, -0.005))

# SITUATION: the assistance van comes up the service track to the motorway fence and stops at the closed gate; trucks
# pass behind the fence and the guardrail
s_g = s_e + 70.0
XF = S.x_sh + 9.0                                           # fence line


def gp(xp, along=0.0, h=0.0):
    return S.pt(s_g + along, xp, h)


uo = gp(XF + 1.0) - gp(XF)
RZ = math.atan2(uo.y, uo.x)                                 # outward, away from the motorway
for nm, xp, ln, wd, zc, m in (("svc_field", XF + 60.0, 120.0, 180.0, -0.11, S.M.grass),
                              ("svc_kerb", XF + 30.0, 60.6, 5.2, -0.04, S.M.gravel),
                              ("svc_track", XF + 30.0, 60.6, 4.4, -0.02, S.M.asph_sh)):
    o = TN.box(nm, S.env, tuple(gp(xp, 0.0, zc)), (ln, wd, 0.1), m)
    o.rotation_euler[2] = RZ
steel = MW.mat("fence_steel", (0.32, 0.4, 0.34), 0.5, metal=0.5)
galv = MW.mat("gate_galv", (0.62, 0.64, 0.66), 0.35, metal=0.8)
for k in range(-16, 17):
    al = 2.5 * k
    if abs(al) < 2.6:
        continue
    o = TN.box("fence_post", S.env, tuple(gp(XF, al, 0.9)), (0.06, 0.06, 1.8), steel)
    o.rotation_euler[2] = RZ
for sg in (-1, 1):
    for zh in (0.25, 0.7, 1.15, 1.6):
        o = TN.box("fence_wire", S.env, tuple(gp(XF, sg * 21.3, zh)), (0.015, 37.4, 0.015), steel)
        o.rotation_euler[2] = RZ
    o = TN.box("gate_pillar", S.env, tuple(gp(XF, sg * 2.6, 1.0)), (0.16, 0.16, 2.0), galv, bevel=0.01)
    o.rotation_euler[2] = RZ
for zh in (0.35, 1.0, 1.65):                                 # the closed two-leaf gate: rails and bars
    o = TN.box("gate_rail", S.env, tuple(gp(XF, 0.0, zh)), (0.05, 5.04, 0.05), galv)
    o.rotation_euler[2] = RZ
for k in range(21):
    o = TN.box("gate_bar", S.env, tuple(gp(XF, -2.5 + 0.25 * k, 1.0)), (0.025, 0.025, 1.3), galv)
    o.rotation_euler[2] = RZ
van = W.instance(S.vans["van_white"], tuple(gp(XF + 20.0)), c=S.traffic)
rv = motion.rig(van)
vrows = []
for f in range(N):
    t = f / FPS
    u = min(1.0, max(0.0, (t - S0 - 2.4) / 2.6))
    e = 1 - (1 - u) ** 2
    p = gp(XF + 4.0 + 16.0 * (1 - e))
    vrows.append(dict(x=p.x, y=p.y, z=p.z, yaw=RZ + math.pi, v=16.0 * 2 * (1 - u) / 2.6, ind=None))
motion.bake(rv, vrows)

# COST: the regulated tariff on the table of the operator's office, the two rows marked as the captions name them
LR = Vector((9300.0, 0.0, 0.0))
IN.room(ins, "off_room", LR, w=4.0, d=3.6, h=2.6, wall=(0.72, 0.75, 0.74), floor=(0.3, 0.3, 0.32))
TT = IN.table(ins, "off_table", tuple(LR + Vector((0.1, 0.5, 0.75))))
CL = Vector(TT)
INK = IN.INK
BLK = [("Dépanneur agréé · Autoroute", 0.0062, "din", IN.GREY_T, 0.0),
       ("Tarifs réglementés", 0.013, "bold", INK, 0.016),
       ("Dépannage ou remorquage, véhicule léger", 0.0068, "din", INK, 0.006),
       ("Jour ouvré, en journée", 0.0078, "din", IN.GREY_T, 0.022),
       (NUMBERS["fr_motorway_breakdown_price_weekday"], 0.0145, "bold", INK, 0.006),
       ("Le soir, le week-end, les jours fériés", 0.0078, "din", IN.GREY_T, 0.02),
       (NUMBERS["fr_motorway_breakdown_price_evening_weekend"], 0.0145, "bold", INK, 0.006),
       ("Prix fixés par arrêté ministériel.", 0.0062, "din", IN.GREY_T, 0.026),
       ("Prix TTC, déplacement compris.", 0.0062, "din", IN.GREY_T, 0.004)]
lg = IN.letter(ins, "tariff", tuple(CL), math.radians(4), BLK, envelope=False)
IN.mug(ins, "off_mug", tuple(TT + Vector((-0.32, 0.18, 0.0))), color=(0.1, 0.25, 0.55))
ys, y = [], 0.297 / 2 - 0.028
for _, size, _, _, gap in BLK:
    y -= gap + size * 0.75
    ys.append(y)
for k, (ta0, ta1) in ((4, (C0 + 2.2, C0 + 3.75)), (6, (C0 + 3.8, SEG["COST"][1]))):
    hg = CY.bpy_empty(ins, "mark", lg, loc=(-0.087, ys[k] + 0.0045, 0.00085))
    CY.flat(ins, "mark_m", MW.rect(0.11, 0.0175, 0.055, 0.0), (1.0, 0.86, 0.15), 0.0, rot=(0, 0, 0), parent=hg, z=0.0)
    for t_, sx in ((ta0, 0.02), (ta0 + 0.3, 1.0)):
        hg.scale = (sx, 1.0, 1.0)
        hg.keyframe_insert("scale", frame=int(t_ * FPS) + 1)
    CY.show(hg, [(ta0, ta1)])
ec_pos, ec_tgt, ec_scale = CY.end_card(ins, "fr", ["autoroute"], x0=-9000.0)

# ------------------------------------------------------------------ cameras
shots = jx.Shots(N)
V3 = Vector
shots.add("H_dash", 30, H0, H0 + 1.1, lambda t: cab(t, CEYE, CLOOK))
shots.add("H_chase", 28, H0 + 1.1, SEG["HOOK"][1], lambda t: S.chase(ta, t, back=9.0, up=2.2, side=-1.0))
shots.add("S_phone", 45, S0, S0 + 2.4, lambda t: cab(t, EYE + V3((0.0, 0.02 * (t - S0), 0.0)), LOOK))
shots.add("S_gate", 26, S0 + 2.4, S0 + 5.4, lambda t: (gp(XF + 15.0, -6.5 + 0.3 * (t - S0 - 2.4), 3.0),
                                                       gp(XF - 2.0, 1.0, 1.0)))
ep = S.pt(s_e, SH)
shots.add("S_chase", 28, S0 + 5.4, SEG["SITUATION"][1],
          lambda t: (S.pt(s_e - 12.0, SH + 0.8, 1.7), S.pt(s_e + 30.0, L1 - 1.0, 1.2)))
shots.add("R_walk", 32, R0, R0 + 4.0, lambda t: (S.pt(s_e - 5.0 + 1.2 * (t - R0), XG + 4.5, 1.7),
                                                  S.pt(s_e + 1.0 + 1.6 * (t - R0), XG, 1.1)))
shots.add("R_drone", 24, R0 + 4.0, SEG["RULE"][1],
          lambda t: (S.pt(s_e + 1.0 + 0.4 * (t - R0 - 4.0), XG + 13.0, 10.0 + 0.5 * (t - R0 - 4.0)),
                     S.pt(s_post - 2.5, XG - 1.5, 0.6)))
shots.add("C_sheet", 40, C0, SEG["COST"][1],
          lambda t: (CL + V3((0.0, -0.44 + 0.022 * (t - C0), 0.5 - 0.022 * (t - C0))), CL + V3((0.0, 0.035, 0.0))))
shots.add("K_drone", 26, K0, K0 + 3.0, lambda t: (ep + V3((-14.0, -26.0, 14.0)), ep + V3((2.0, 0.0, 0.5))))
shots.add("K_chase", 28, K0 + 3.0, SEG["CORRECT"][1],
          lambda t: (S.pt(s_e - 14.0, SH - 1.5, 2.6), S.pt(s_e + 10.0, SH, 1.0)))
cam_e = shots.add("E_card", 50, E0, T_END, lambda t: (V3(ec_pos), V3(ec_tgt)))
cam_e.data.type, cam_e.data.ortho_scale = "ORTHO", ec_scale
for nm in ("H_dash", "S_phone", "C_sheet"):
    bpy.data.objects[nm].data.clip_start = 0.02
for nm, fd in (("H_dash", CFOC), ("S_phone", 0.41)):
    cd = bpy.data.objects[nm].data
    cd.dof.use_dof, cd.dof.focus_distance, cd.dof.aperture_fstop = True, fd, 3.2

CY.sun_light(ASSETS, az_deg=250.0, elev_deg=7.0, energy=3.2, warm=True)
WX.apply("dusk", strength=1.0, seed=2)
MW.render(shots, OUT, RES, SAMPLES, FR, STILLS, N, haze=None, first="H_dash")
print("RENDER_DONE", FR, "signs", SG.sources_used().keys())
