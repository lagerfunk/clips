"""Drive Like a Local B1, Austria: a digital vignette bought online starts only on the 18th day. 9:16, 30 fps,
canonical timeline from kit/country.py TIMELINE["B01"] (HOOK 2.6, SITUATION 9.0, RULE 7.5, COST 5.5, CORRECT 6.5,
END 4.2 = 35.3 s).
Set: a two-lane Austrian Autobahn with hard shoulder in an Alpine valley (kit/mway.py, white markings as Germany),
the Austrian Autobahn sign (signs/at.json, Hinweiszeichen 8a, unaltered Commons file), a toll-check gantry (the
lanemgmt gantry frame only: no lane panels, no boards, no text) with a grey camera box. Inserts (look pass 27 Oct) are lit props in real settings: the vignette app on a phone in a
dashboard mount inside the estate, a wall calendar in a living room, a fuel-station shop counter with a card terminal,
the Ersatzmaut letter on a kitchen table; in-world text in German, no brands, every number from NUMBERS (VERIFIED
facts). at vignette-pflicht is missing on Commons: not shown.
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
import inserts as IN  # noqa: E402
import jx  # noqa: E402
import lanemgmt as LM  # noqa: E402
import motion  # noqa: E402
import mway as MW  # noqa: E402
import parking as PK  # noqa: E402
import signs as SG  # noqa: E402
import town as TN  # noqa: E402
import world as W  # noqa: E402

OUT, RES, SAMPLES, ASSETS, FR, STILLS = MW.cli(sys.argv)
FPS = MW.FPS
SEG, T_END = CY.spans("B01")
N = int(round(T_END * FPS))
H0, S0, R0, C0, K0, E0 = (SEG[k][0] for k in ("HOOK", "SITUATION", "RULE", "COST", "CORRECT", "END"))
SG.setup(ASSETS)
PLATE = "QX VG 118"
# every number on an insert comes from a VERIFIED key of facts/at.json (tests/test_trackb_motorway.py checks them)
NUMBERS = {"at_vignette_online_18_days": "Gültig ab dem 18. Tag", "at_ersatzmaut_car": "€ 200,00",
           "at_ersatzmaut_unpaid_penalty": "von € 300 bis € 3.000", "at_ersatzmaut_four_weeks": "vier Wochen"}

S = MW.Stage(ASSETS, "at", lanes=2, mountains=True, seed=11)
L0, L1 = S.lane_x(0), S.lane_x(1)
SH = S.shoulder_x()
hero = jx.hero("estate", (0.04, 0.12, 0.42), "hero", PLATE, S.lib, S.traffic, metal=0.5)
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

# ------------------------------------------------------------------ inserts (owner rule 27 Oct: lit props in real
# settings, readable unbranded text, no flat primitive scenes)
ins = S.ins
IN.setup(ASSETS)
PK.see_through(hero)
GL = 2.4                       # phone screen glow inside the cabin (daylight outside)


def scr_hook(c, p, e):
    IN.header(c, p, e, "Vignette", sub="Digital · Jahresvignette")
    IN.tick(c, p, 0.0, 0.016, 0.012, 0.0006, e)
    IN.text(c, "Bezahlt", 0.0075, IN.INK, (0.0, -0.004, 0.0006), p, align="CENTER", kind="bold", emit=e)
    IN.row(c, p, e, -0.022, "Kennzeichen", PLATE)
    IN.banner(c, p, e, -0.036, [NUMBERS["at_vignette_online_18_days"], "nach dem Online-Kauf"])


def scr_buy(t_tap, t_tick, t_end):
    def b(c, p, e):
        IN.header(c, p, e, "Vignette", sub="Digital · Jahresvignette")
        IN.row(c, p, e, 0.026, "Kennzeichen", PLATE)
        IN.row(c, p, e, 0.008, "Zulassungsland", "D")
        IN.row(c, p, e, -0.010, "Fahrzeug", "Pkw")
        IN.button(c, p, e, -0.045, "Jetzt bezahlen")
        rip = CY.flat(c, "ripple", CY.disc_pts(0.007, 32, 0.006, -0.045), (1, 1, 1), e * 1.5, rot=(0, 0, 0),
                      parent=p, z=0.0009)
        CY.show(rip, [(t_tap, t_tap + 0.35)])
        ov = CY.bpy_empty(c, "paid", p)
        IN.rrect(c, ov, -IN.SW / 2, -0.066, IN.SW / 2, 0.041, (0.96, 0.965, 0.97), e, 0.0012, r=0.0001)
        IN.tick(c, ov, 0.0, 0.016, 0.014, 0.0014, e)
        IN.text(c, "Bezahlt", 0.0078, IN.INK, (0.0, -0.007, 0.0014), ov, align="CENTER", kind="bold", emit=e)
        IN.text(c, "Beleg per E-Mail gesendet", 0.0043, IN.GREY_T, (0.0, -0.017, 0.0014), ov, align="CENTER", emit=e)
        IN.text(c, NUMBERS["at_vignette_online_18_days"], 0.0036, IN.GREY_T, (0.0, -0.056, 0.0014), ov,
                align="CENTER", emit=e)
        CY.show(ov, [(t_tick, t_end)])
    return b


def scr_check(t_hl, t_tick, t_end):
    def b(c, p, e):
        IN.header(c, p, e, "Vignette", sub="Kauf prüfen")
        IN.banner(c, p, e, 0.037, ["Online gekauft?", NUMBERS["at_vignette_online_18_days"]])
        IN.row(c, p, e, 0.006, "Kennzeichen", PLATE, hl=IN.AMBER, spans_hl=[(t_hl, t_end)])
        IN.row(c, p, e, -0.013, "Zulassungsland", "D", hl=IN.AMBER, spans_hl=[(t_hl, t_end)])
        btn = IN.button(c, p, e, -0.045, "Weiter")
        CY.show(btn, [(K0, t_tick)])
        ok = CY.bpy_empty(c, "ok", p)
        IN.tick(c, ok, -0.02, -0.045, 0.0075, 0.0006, e)
        IN.text(c, "Angaben korrekt", 0.0052, IN.GREEN, (-0.0105, -0.045, 0.0006), ok, kind="bold", emit=e)
        CY.show(ok, [(t_tick, t_end)])
    return b


def scr_lock(c, p, e):
    IN.header(c, p, e, "Vignette", sub="Online gekauft")
    IN.lock(c, p, 0.0, 0.018, 0.022, 0.0006, e, color=IN.GREY_T)
    IN.text(c, "Noch nicht gültig", 0.0062, IN.INK, (0.0, -0.006, 0.0006), p, align="CENTER", kind="bold", emit=e)
    IN.banner(c, p, e, -0.016, [NUMBERS["at_vignette_online_18_days"], "nach dem Kauf"])
    IN.row(c, p, e, -0.05, "Kennzeichen", PLATE)


ph = IN.phone(ins, "phone_dash", (0, 0, 0), (0, 0, 0),
              {"hook": ([(H0, H0 + 1.1)], scr_hook),
               "buy": ([(S0, S0 + 3.0)], scr_buy(S0 + 0.8, S0 + 1.1, S0 + 3.0)),
               "lock": ([(R0 + 3.8, R0 + 5.75)], scr_lock),
               "check": ([(K0, E0)], scr_check(K0 + 4.9, K0 + 5.6, E0))}, glow=GL)
IN.dash_mount(hero, ph)
TOP, BOT, KD = IN.windscreen(hero)
cab = IN.cabin_cam(hero["obj"], hero)
IN.body_off_camera(hero, [(H0, H0 + 1.1), (S0, S0 + 3.0), (R0 + 3.8, R0 + 5.75), (K0 + 3.2, E0)])
PHL = Vector((-0.06, BOT.y - 0.36, BOT.z + 0.045))           # phone centre in the car's frame
EYE = PHL + Vector((-0.16, -0.36, 0.105))

# RULE 1: wall calendar in a living room (real day numbers, German month; days 1 to 17 crossed, the 18th ringed)
CR = Vector((9300.0, 0.0, 0.0))
IN.room(ins, "cal_room", CR, w=4.0, d=3.4, h=2.6)
# kitchen run under the calendar: base cabinets, worktop, tiled splashback, an upper cabinet and a shelf with jars
front_m = IN._noise_mat("kit_front", (0.86, 0.87, 0.84), 0.03, 40.0, 0.35)
top_m = IN._wood_mat("kit_worktop", (0.5, 0.33, 0.19), 0.3, 0.35, plank=0.04, length=0.9)
tile_m = IN._wood_mat("kit_tiles", (0.8, 0.84, 0.82), 0.04, 0.15, plank=0.1, length=0.1)
WY = CR.y + 1.7
TN.box("kit_base", ins, (CR.x, WY - 0.3, 0.44), (2.6, 0.6, 0.88), front_m, bevel=0.005)
for k in range(5):
    TN.box("kit_door_gap", ins, (CR.x - 1.04 + 0.52 * k, WY - 0.602, 0.44), (0.006, 0.004, 0.8), IN._mat((0.3, 0.3, 0.3)))
    TN.box("kit_knob", ins, (CR.x - 0.83 + 0.52 * k, WY - 0.615, 0.74), (0.12, 0.02, 0.014), IN.TN_steel(), bevel=0.005)
TN.box("kit_worktop", ins, (CR.x, WY - 0.31, 0.9), (2.65, 0.64, 0.04), top_m, bevel=0.004)
TN.box("kit_splash", ins, (CR.x, WY - 0.006, 1.1), (2.6, 0.012, 0.36), tile_m)
TN.box("kit_upper", ins, (CR.x + 0.72, WY - 0.18, 1.9), (0.7, 0.36, 0.72), front_m, bevel=0.005)
TN.box("kit_upper_knob", ins, (CR.x + 0.44, WY - 0.37, 1.62), (0.016, 0.02, 0.1), IN.TN_steel(), bevel=0.005)
TN.box("kit_shelf", ins, (CR.x - 0.72, WY - 0.12, 1.55), (0.6, 0.24, 0.03), top_m)
for k, (jh, jc) in enumerate(((0.16, (0.85, 0.55, 0.2)), (0.12, (0.9, 0.88, 0.8)), (0.18, (0.55, 0.3, 0.15)),
                              (0.1, (0.3, 0.5, 0.3)))):
    TN.box("kit_jar", ins, (CR.x - 0.92 + 0.13 * k, WY - 0.12, 1.565 + jh / 2), (0.09, 0.09, jh),
           IN._mat(jc, None, 0.2), bevel=0.02)
kettle = IN.mug(ins, "kit_kettle", (CR.x - 0.3, WY - 0.3, 0.92), color=(0.75, 0.76, 0.78))
kettle.scale = (2.2, 2.2, 2.4)
TN.box("kit_board", ins, (CR.x + 0.25, WY - 0.05, 1.08), (0.36, 0.02, 0.28), top_m, bevel=0.01).rotation_euler.x = \
    math.radians(-8)
IN.mug(ins, "cal_mug", (CR.x + 0.5, WY - 0.35, 0.92), color=(0.15, 0.45, 0.6))
CAL = CR + Vector((0.0, 1.7 - 0.012, 1.62))
calg, cpos, cgw, crh = IN.wall_calendar(ins, "wcal", tuple(CAL), "FEBRUAR", 0, 28,
                                        ["MO", "DI", "MI", "DO", "FR", "SA", "SO"])
r1 = IN.pen_ring(ins, calg, cpos[1][0], cpos[1][1], 0.022, 0.0016, color=(0.1, 0.3, 0.8), name="buy_ring")
CY.show(r1, [(R0, 999)])
for d in range(1, 18):
    x_ = IN.pen_cross(ins, calg, cpos[d][0], cpos[d][1], 0.012, 0.0018, name=f"cross{d}")
    CY.show(x_, [(R0 + 0.15 * d + 0.1, 999)])
g18 = IN.pen_ring(ins, calg, cpos[18][0], cpos[18][1], 0.024, 0.0016, color=IN.GREEN, name="ring18", width=0.006)
CY.show(g18, [(R0 + 2.9, 999)])
for t, sc in ((R0 + 2.9, 1.0), (R0 + 3.15, 1.3), (R0 + 3.4, 1.0), (R0 + 3.65, 1.25), (R0 + 3.8, 1.0)):
    g18.scale = (sc, sc, sc)
    g18.keyframe_insert("scale", frame=int(t * FPS) + 1)

# RULE 2: fuel-station shop counter: the phone bought online lies locked, the card terminal says valid now
SP = Vector((9500.0, 0.0, 0.0))
shp = IN.shop(ins, "shop", SP, glow=1.8)
CT = shp["counter_top"]


ts = shp["terminal"]
IN.text(ins, "Vignette", 0.009, IN.INK, (0.0, 0.024, 0.0004), ts, align="CENTER", kind="bold", emit=1.8)
tk = IN.tick(ins, ts, 0.0, 0.003, 0.011, 0.0004, 1.8)
IN.text(ins, "Gültig ab sofort", 0.0068, IN.GREEN, (0.0, -0.022, 0.0004), ts, align="CENTER", kind="bold", emit=1.8)
CY.show(tk, [(R0 + 5.9, 999)])
tl = shp["till"]
IN.rrect(ins, tl, -0.17, 0.075, 0.17, 0.11, IN.TEAL, 1.8, 0.0005, r=0.0001)
IN.text(ins, "Digitale Vignette", 0.02, (1, 1, 1), (-0.155, 0.0925, 0.0007), tl, kind="bold", emit=2.0)
IN.text(ins, "Kennzeichen  " + PLATE, 0.017, IN.INK, (-0.155, 0.045, 0.0007), tl, emit=1.8)
IN.text(ins, "Gültig ab sofort", 0.024, IN.GREEN, (-0.155, -0.01, 0.0007), tl, kind="bold", emit=1.8)

# COST: the replacement-toll letter on the kitchen table, envelope beside it, a mug
LR = Vector((9700.0, 0.0, 0.0))
IN.room(ins, "kit_room", LR, w=4.0, d=3.6, h=2.6, wall=(0.84, 0.8, 0.7))
TT = IN.table(ins, "kit_table", tuple(LR + Vector((0.1, 0.5, 0.75))))
CL = Vector(TT)
INK = IN.INK
IN.letter(ins, "letter", tuple(CL), math.radians(6), [
    ("Mautaufsicht · Autobahnen und Schnellstraßen", 0.0058, "din", IN.GREY_T, 0.0),
    ("An den Zulassungsbesitzer", 0.0072, "din", INK, 0.012),
    ("Kennzeichen " + PLATE + " (D)", 0.0072, "din", INK, 0.004),
    ("Aufforderung zur Zahlung", 0.0115, "bold", INK, 0.024),
    ("der Ersatzmaut", 0.0115, "bold", INK, 0.004),
    ("Bei der Kontrolle war für das Fahrzeug", 0.0072, "din", INK, 0.014),
    ("keine gültige Vignette registriert.", 0.0072, "din", INK, 0.004),
    ("Ersatzmaut:  " + NUMBERS["at_ersatzmaut_car"], 0.0135, "bold", IN.RED, 0.018),
    ("Zahlbar binnen " + NUMBERS["at_ersatzmaut_four_weeks"] + " ab Briefdatum.", 0.0072, "din", INK, 0.014),
    ("Bei Nichtzahlung droht eine Verwaltungsstrafe", 0.0072, "din", INK, 0.012),
    (NUMBERS["at_ersatzmaut_unpaid_penalty"] + ".", 0.0095, "bold", INK, 0.004),
    ("Zahlung per Überweisung oder online.", 0.0058, "din", IN.GREY_T, 0.022),
    ("Dieses Schreiben wurde maschinell erstellt.", 0.0058, "din", IN.GREY_T, 0.004),
])
IN.mug(ins, "kit_mug", tuple(TT + Vector((-0.3, 0.2, 0.0))))
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
TN.box("ps_shop", ins, tuple(PS + Vector((-12.0, 30.0, 2.0))), (12.0, 9.0, 4.0), MW.mat("kiosk_wall", (0.86, 0.84, 0.78),
                                                                                    0.7), bevel=0.05)
TN.box("ps_glass", ins, tuple(PS + Vector((-5.95, 30.0, 1.7))), (0.05, 7.0, 2.6), MW.mat("kiosk_glass2", (0.3, 0.38,
                                                                                                         0.42), 0.1))
# a copy of the hero drives in, indicating right, and stops at the pump
car2 = W.instance(hero["coll"], tuple(PS), c=S.traffic)
r2 = motion.rig(car2)
rows = []
for f in range(N):
    t = f / FPS
    u = 1.0 if t < C0 else min(1.0, max(0.0, (t - K0) / 2.0))
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
LOOK = PHL + V3((0.04, 0.0, -0.005))
cab2 = IN.cabin_cam(car2, hero)
shots.add("H_phone", 45, H0, H0 + 1.1, lambda t: cab(t, EYE, LOOK))
shots.add("H_chase", 28, H0 + 1.1, SEG["HOOK"][1], lambda t: S.chase(ta, t, back=9.0, up=2.0, side=1.0))
shots.add("S_phone", 45, S0, S0 + 3.0, lambda t: cab(t, EYE + V3((0.0, 0.025 * (t - S0), 0.0)), LOOK))
shots.add("S_chase", 28, S0 + 3.0, S0 + 6.0, lambda t: S.chase(ta, t, back=10.0, up=2.6, side=2.0))
gq = S.pt(s_g, S.x_sh + 2.0)
shots.add("S_drone", 26, S0 + 6.0, SEG["SITUATION"][1],
          lambda t: (gq + V3((8.0, -42.0 + 3.0 * (t - S0 - 6.0), 16.0)), gq + V3((-6.0, 10.0, 3.0))))
shots.add("R_cal", 40, R0, R0 + 3.8, lambda t: (CAL + V3((0.05, -1.4 + 0.04 * (t - R0), -0.07)),
                                                CAL + V3((0.0, 0.0, -0.12))))
shots.add("R_phone", 45, R0 + 3.8, R0 + 5.75, lambda t: cab2(t, EYE + V3((0.0, 0.02 * (t - R0 - 3.8), 0.0)), LOOK))
TM = shp["term"].location.copy()
shots.add("R_term", 35, R0 + 5.75, SEG["RULE"][1], lambda t: (TM + V3((-0.1, -0.42 + 0.02 * (t - R0 - 5.75), 0.2)),
                                                              TM + V3((0.0, 0.1, 0.03))))
shots.add("C_car", 30, C0, C0 + 2.0, lambda t: S.chase(ht, C0, back=7.0, up=3.4, side=-2.5, ahead=3.0, look_up=0.8))
shots.add("C_letter", 40, C0 + 2.0, SEG["COST"][1],
          lambda t: (CL + V3((0.0, -0.36 + 0.02 * (t - C0 - 2.0), 0.46 - 0.02 * (t - C0 - 2.0))), CL + V3((0, 0.05, 0))))
shots.add("K_drone", 26, K0, K0 + 3.2, lambda t: (PS + V3((15.0 - 1.0 * (t - K0), -13.0, 8.5)), PS + V3((1.0, 9.0, 1.0))))
shots.add("K_phone", 45, K0 + 3.2, SEG["CORRECT"][1], lambda t: cab2(t, EYE, LOOK))
cam_e = shots.add("E_card", 50, E0, T_END, lambda t: (V3(ec_pos), V3(ec_tgt)))
cam_e.data.type, cam_e.data.ortho_scale = "ORTHO", ec_scale
for nm in ("H_phone", "S_phone", "K_phone", "R_cal", "R_phone", "R_term", "C_letter"):
    bpy.data.objects[nm].data.clip_start = 0.02
for nm in ("H_phone", "S_phone", "K_phone", "R_phone"):
    cd = bpy.data.objects[nm].data
    cd.dof.use_dof, cd.dof.focus_distance, cd.dof.aperture_fstop = True, 0.41, 4.0

CY.sun_light(ASSETS, az_deg=160.0, elev_deg=36.0, energy=4.4)
MW.render(shots, OUT, RES, SAMPLES, FR, STILLS, N, haze=(0.68, 0.76, 0.88), haze_dist=3800.0, first="H_phone")
print("RENDER_DONE", FR, "signs", SG.sources_used().keys())
