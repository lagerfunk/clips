"""Drive Like a Local #10, Germany (standard): winter tyres. There is no date: ice, snow and slush decide, and only
tyres with the Alpine symbol count (M+S alone no longer does). StVO 2 (3a), BKatV 5a. 9:16, 30 fps, no voice.
Set: the plain town stage (6 m residential streets, October trees and leaves). Day for the parking beat, then
weather.apply('ice', 0.9), a snow flurry (snow+ice) in the last beat of SITUATION, day again for the end card.
White rental hatchback (hero, summer tyres), grey estate parked at the kerb, silver hatchback on winter tyres (CORRECT),
a white van, a police estate. Zeichen 101-51 (snow or ice slipperiness; the script's "113" is the pre-2013 number) from Commons
(set de-core) on a post at the junction approach (its own shot, never floating). The tyre is a modelled winter tyre
(tread blocks with sipes, moulded size, M+S and Alpine symbol, no brand); ticks and crosses are ASS drawings.
Canonical timeline (English order; finish_ep cuts each language's order from ep10_edit.json):
HOOK 0-2.2, SITUATION 2.2-12.2, RULE 12.2-20.2, COST 20.2-25.8, CORRECT 25.8-32.3, END 32.3-35.0.
Run: python ep10_winter_tyres.py OUTDIR --frames 1-1050 --res 540 --samples 8 --assets ASSETS [--stills 30,400]
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "ep10")]
import ep10_za5kit as K  # noqa: E402
from ep10_za5kit import bpy, Vector, SG, TN, TP, TS, W, FPS  # noqa: E402

TL = K.Timeline([("HOOK", 2.2), ("SITUATION", 10.0), ("RULE", 8.0), ("COST", 5.6), ("CORRECT", 6.5), ("END", 2.7)])
N = TL.N
HX = 3.0
S = TS.build(K.ASSETS, "plain", seed=12, hx=HX, hy=3.0, parked=False, heroes=[
    ("hatch", (0.86, 0.87, 0.86), "hero", "QX WR 210", 0.35), ("hatch", (0.62, 0.64, 0.67), "good", "JJ WT 26", 0.5)])
SG.setup(K.ASSETS)
T, env, lib, traf, fleet = S["T"], S["env"], S["lib"], S["traffic"], S["fleet"]
H, G = S["heroes"]["hero"], S["heroes"]["good"]
LN, KB = HX / 2, HX - 1.05                      # lane centre, kerb parking line (car centre)
st = TP.through(S["J"], "NS")
TP.leaves(env, st, -95.0, 60.0, seed=10)

# ------------------------------------------------------------------ the hero
EST_Y = 40.0                                     # the grey estate parked at the right kerb (HOOK, north arm)
Y_PARK = -17.5                                   # where the hero parks for the night (south arm)
K.parked(env, fleet["estate_grey"], "estate_hook", KB, EST_Y, math.pi / 2)
P_hook = K.line((LN - 0.4, 0.0), (LN - 0.4, 26.0), (KB - 0.2, 33.0), (KB - 0.2, 60.0))
# K.s_of_y interpolates (jx.Path.s_of_y snapped to the nearest vertex: the hook stop was 2.3 m short, the parking
# spot 2.5 m, COST 14 m, the CORRECT line 68 m). The hook slide ends 0.45 m short of the estate's rear (EST_Y - 2.4):
# at the 0.3 rad yaw it ends on, the hatch's front corner sits 2.35 m ahead of its middle.
s_hook = K.s_of_y(P_hook, EST_Y - 2.4 - 0.45 - 2.35)
P_sit = K.line((LN, -80.0), (LN, -27.0), (KB, -22.0), (KB, -15.0), (LN, -9.0), (LN, 60.0))
s_park = K.s_of_y(P_sit, Y_PARK)
n = TL.n("SITUATION")
sv_sit = (K.kin(s_park - 8.4, 5.0, [(0, "stop", s_park)], int(2.5 * FPS)) + K.hold(s_park, int(3.7 * FPS)) +
          K.kin(s_park, 0.0, [(0, "cruise", 5.6)], int(1.8 * FPS)))
sv_sit += K.brake(sv_sit[-1][0] + 3.6, sv_sit[-1][1], 0.0, 1.8, n - len(sv_sit))
P_cost = K.line((LN - 0.3, -90.0), (LN - 0.3, -30.0))
Y_COST = -44.0                                   # the hero comes to rest across the lane here (COST)
s_cost = K.s_of_y(P_cost, Y_COST)
parts = {
    "HOOK": (P_hook, K.brake(s_hook, 4.2, 0.4, 2.2, TL.n("HOOK")), dict(yaw=lambda t: 0.3 * K.ease((t - 0.4) / 1.3))),
    "SITUATION": (P_sit, sv_sit, dict(ind=[("R", 0.0, 2.4), ("L", 6.0, 7.4)],
                                      yaw=lambda t: 0.22 * K.ease((t - 8.1) / 1.4) if t > 8.0 else 0.0)),
    "COST": (P_cost, K.brake(s_cost, 5.0, 0.2, 1.5, TL.n("COST")),
             dict(yaw=lambda t: 0.95 * K.ease((t - 0.2) / 1.3), ind=[("H", 1.8, 9.0)])),
}
K.bake(H, K.track(TL, parts, H["L"]))

# ------------------------------------------------------------------ the van behind (COST) and the police estate
van = K.vehicle(fleet["van_white"], traf, "trf_van", 5.2)
K.bake(van, K.track(TL, {"COST": (P_cost, K.brake(s_cost - 7.0, 6.5, 0.5, 2.6, TL.n("COST")))}, 5.2))
pol = K.vehicle(K.V.car("estate", (0.8, 0.81, 0.82), "police", "QX PD 110", police=True, c=lib), traf, "trf_police")
P_pol = K.line((-LN, 20.0), (-LN, -36.0), (-KB, -42.0), (-KB, -60.0))
# The police estate comes down the other lane and brakes hard (1.0-3.0 s), stopping 4.9 m short of where the hero's
# nose crosses into its lane (y -42.8). With the hero at its real stop it used to roll on to y -46, beside the hero.
Y_PSTOP = -35.5
K.bake(pol, K.track(TL, {"COST": (P_pol, K.brake(K.s_of_y(P_pol, Y_PSTOP), 6.0, 1.0, 3.0, TL.n("COST")),
                                  dict(ind=[("H", 2.6, 9.0)]))}))
# the silver hatchback on winter tyres (CORRECT) and a car well ahead of it: slow on the ice (4.5 m/s), braking early
# and gently (4.2-6.1 s, 2.4 m/s2, brake lamps on from 4.2 s), standing at the junction line to the end of CORRECT.
P_ok = K.line((LN, -80.0), (LN, 80.0))
s_line = K.s_of_y(P_ok, -9.6 - G["L"] / 2)
n = TL.n("CORRECT")
K.bake(G, K.track(TL, {"CORRECT": (P_ok, K.brake(s_line, 4.5, 4.2, 6.1, n))}, G["L"]))
print("EP10_POS", "L", H["L"], G["L"], "hook", round(s_hook, 2), "park", round(s_park, 2), "cost", round(s_cost, 2),
      "line", round(s_line, 2), "line_y", round(P_ok.at(s_line)[0].y, 2))
ahead = K.vehicle(fleet["estate_blue"], traf, "trf_ahead")
K.bake(ahead, K.track(TL, {"CORRECT": (P_ok, K.kin(s_line + 6.0, 4.0, [(0, "cruise", 4.5)], n))}))

# ------------------------------------------------------------------ street life, Zeichen 101-51 at the approach
# (the dark SUV stood at -KB, -30, in the police estate's lane: it parks on the north arm now)
for key, x, y, yaw in (("hatch_blue", KB, -75.0, math.pi / 2), ("suv_dark", -KB, 50.0, -math.pi / 2),
                       ("saloon_white", -KB, -64.0, -math.pi / 2), ("hatch_red", -KB, 30.0, -math.pi / 2),
                       ("estate_green", KB, 72.0, math.pi / 2)):
    K.parked(env, fleet[key], key, x, y, yaw)
K.walker(env, "ped1", 4, [(HX + 1.6, -70.0), (HX + 1.6, -20.0)], [(1.1 * i / FPS, 1.1) for i in range(N)],
         coat=(0.2, 0.25, 0.32))
S101 = (HX + TN.KERB_W + 0.6, -25.5)   # 1.5 m before the lamp mast at -24 so the mast is behind the plate (QA r19)
if K.have("101-51", "de-core"):
    SG.assembly([("101-51", 0.9)], env, (S101[0], S101[1], TN.KERB_H), rz=0.0, bottom=2.0, set_="de-core")  # rz 0: face to the car driving +Y towards it (QA r17: rz pi showed the hero the back)
else:
    print("SIGN_MISSING de-core 101-51")
# The ice itself is weather.apply("ice") (glaze over frosty asphalt); no glowing patches on the road.

# ------------------------------------------------------------------ the tyre (close-up prop, studio)
# A 205/55 R16 winter tyre standing on a workshop floor: a revolved rubber carcass (rounded shoulders, sidewall
# bulge), 72 pitches x 4 rows of tread blocks with sipes, moulded sidewall markings in the same rubber (size, M+S and
# the Alpine symbol: three peaks with a snowflake), a plain five-spoke alloy. No brand, no maker's name. Materials
# are named car_tyre* / car_rim* / overlay* so the ice preset leaves them alone (weather.SKIP_PREFIX).
TY = Vector((60.0, 0.0, 300.0))
RC, AR, AY = 0.2555, 0.0525, 0.1025               # carcass: r from 0.203 to 0.308, half width 0.1025
rub = W.principled("car_tyre_studio", (0.028, 0.028, 0.03), 0.86, spec=0.22)
rel = W.principled("car_tyre_relief", (0.06, 0.06, 0.064), 0.55, spec=0.35)
slit = W.principled("car_tyre_slit", (0.008, 0.008, 0.009), 0.9)


def tp(r, y, phi):
    return (TY.x + r * math.cos(phi), TY.y + y, TY.z + r * math.sin(phi))


NP, NA = 64, 144
prof = []
for i in range(NP):
    th = 2 * math.pi * i / NP
    c_, s_ = math.cos(th), math.sin(th)
    prof.append((RC + AR * math.copysign(abs(c_) ** 0.5, c_), AY * math.copysign(abs(s_) ** 0.5, s_)))
vs = [tp(r, y, 2 * math.pi * j / NA) for j in range(NA) for (r, y) in prof]
fs = [(j * NP + i, j * NP + (i + 1) % NP, ((j + 1) % NA) * NP + (i + 1) % NP, ((j + 1) % NA) * NP + i)
      for j in range(NA) for i in range(NP)]
carcass = W.mesh_obj("tyre", vs, fs, rub, env, smooth=True)
vs, fs = [], []
R0, DEPTH, PITCH = 0.3075, 0.0075, 2 * math.pi / 72


def rb(y):
    """Carcass radius at the lateral position y (the blocks sit on the rounded shoulder, no gap)."""
    return RC + AR * max(0.0, 1.0 - (abs(y) / AY) ** 4) ** 0.25 - 0.002



for row, (y0, y1) in enumerate(((-0.086, -0.050), (-0.040, -0.006), (0.006, 0.040), (0.050, 0.086))):
    off = 0.5 * PITCH if row in (0, 3) else 0.0
    for j in range(72):
        for k in range(3):                       # three slices per block: the gaps read as sipes
            a0 = off + j * PITCH + k * 0.0072 / R0
            a1 = a0 + 0.0060 / R0
            sk = 0.004 * (1 if row < 2 else -1)  # a slight V (directional winter pattern)
            base = len(vs)
            for (aa, yy) in ((a0, y0), (a1, y0), (a1 + sk, y1), (a0 + sk, y1)):
                vs.append(tp(rb(yy), yy, aa))
            for (aa, yy) in ((a0, y0), (a1, y0), (a1 + sk, y1), (a0 + sk, y1)):
                vs.append(tp(rb(yy) + DEPTH + 0.002, yy, aa))
            fs += [(base + q, base + (q + 1) % 4, base + 4 + (q + 1) % 4, base + 4 + q) for q in range(4)]
            fs.append((base + 4, base + 5, base + 6, base + 7))
W.mesh_obj("tyre_tread", vs, fs, rub, env)
YF = -AY                                          # the outer sidewall face (towards the camera, -Y)


PHI_MS = 35.0


def mould(name, body, phi, r=0.258, size=0.018):
    """Moulded sidewall text, its up pointing out from the axle at angle phi."""
    t = W.text_obj(name, body, size, rel, env, "CENTER", "CENTER", 0.0009)
    t.location = tp(r, YF - 0.0008, phi)
    t.rotation_euler = (math.pi / 2, math.pi / 2 - phi, 0)
    return t


mould("tyre_size", "205/55 R16 91H", math.radians(95), size=0.022)
mould("tyre_ms", "M+S", math.radians(PHI_MS), size=0.036)
PHI_A, R_A, SA = math.radians(155), 0.258, 1.7      # the Alpine symbol (SA: scale, larger than life to read)
ca, rad = Vector(tp(R_A, 0.0, PHI_A)), Vector((math.cos(PHI_A), 0.0, math.sin(PHI_A)))
tan = Vector((math.sin(PHI_A), 0.0, -math.cos(PHI_A)))


def sym(u, v, y):
    q = ca + tan * u + rad * v
    return (q.x, TY.y + y, q.z)


peaks = [(-0.024, -0.012), (-0.014, 0.004), (-0.008, -0.002), (0.0, 0.015), (0.008, -0.002), (0.014, 0.004),
         (0.024, -0.012)]
n = len(peaks)
vs = [sym(SA * u, SA * v, YF + 0.0002) for u, v in peaks] + [sym(SA * u, SA * v, YF - 0.0018) for u, v in peaks]
fs = [tuple(range(n, 2 * n))] + [(q, (q + 1) % n, n + (q + 1) % n, n + q) for q in range(n)]
W.mesh_obj("tyre_alpine", vs, fs, rel, env)
for k in range(3):                                # the snowflake inside the middle peak, moulded as fine slits
    a = math.pi / 2 + k * math.pi / 3
    p0, p1 = (0.0045 * math.cos(a), 0.0025 + 0.0045 * math.sin(a)), (-0.0045 * math.cos(a), 0.0025 - 0.0045 * math.sin(a))
    d = Vector((p1[0] - p0[0], p1[1] - p0[1])).normalized() * 0.0007
    quad_ = [(p0[0] - d.y, p0[1] + d.x), (p1[0] - d.y, p1[1] + d.x), (p1[0] + d.y, p1[1] - d.x), (p0[0] + d.y, p0[1] - d.x)]
    W.mesh_obj(f"tyre_flake{k}", [sym(SA * u, SA * v, YF - 0.0019) for u, v in quad_], [(0, 1, 2, 3)], slit, env)
# the rim: barrel, outer lip, five spokes, centre cap (plain silver alloy, no badge)
silver = W.principled("car_rim_studio", (0.62, 0.63, 0.66), 0.28, 0.9)
TN.cyl("tyre_barrel", env, (TY.x, TY.y, TY.z), 0.2, 0.17, W.principled("car_rim_barrel", (0.08, 0.08, 0.09), 0.5, 0.6),
       verts=64, rot=(math.pi / 2, 0, 0))
bpy.ops.mesh.primitive_torus_add(major_radius=0.196, minor_radius=0.009, major_segments=96, minor_segments=12,
                                 location=(TY.x, TY.y - 0.088, TY.z), rotation=(math.pi / 2, 0, 0))
lip = bpy.context.active_object
lip.data.materials.append(silver)
bpy.ops.object.shade_smooth()
for k in range(5):
    a = math.pi / 2 + 2 * math.pi * k / 5
    sp = TN.box(f"tyre_spoke{k}", env, (TY.x + 0.115 * math.cos(a), TY.y - 0.086, TY.z + 0.115 * math.sin(a)),
                (0.15, 0.022, 0.034), silver, bevel=0.006)
    sp.rotation_euler = (0, -a, 0)
TN.cyl("tyre_cap", env, (TY.x, TY.y - 0.092, TY.z), 0.036, 0.02, silver, verts=40, rot=(math.pi / 2, 0, 0))
floor = W.principled("overlay_floor", (0.30, 0.30, 0.31), 0.85)
K.quad("tyre_floor", [(TY.x - 4, TY.y - 4), (TY.x + 4, TY.y - 4), (TY.x + 4, TY.y + 1.6), (TY.x - 4, TY.y + 1.6)], floor,
       env, z=TY.z - R0 - DEPTH, shadow=True)
W.mesh_obj("tyre_wall", [(TY.x - 4, TY.y + 1.6, TY.z - 0.4), (TY.x + 4, TY.y + 1.6, TY.z - 0.4),
                         (TY.x + 4, TY.y + 1.6, TY.z + 3), (TY.x - 4, TY.y + 1.6, TY.z + 3)], [(0, 1, 2, 3)],
           W.principled("overlay_wall", (0.16, 0.17, 0.19), 0.9), env)
K.area("tyre_key", env, (TY.x - 1.3, TY.y - 0.9, TY.z + 1.1), 90.0, 1.0, (math.radians(50), 0, math.radians(-55)))
K.area("tyre_rake", env, (TY.x + 0.9, TY.y - 0.6, TY.z + 0.2), 70.0, 0.4, (0, math.radians(80), math.radians(-30)))
K.area("tyre_rim_l", env, (TY.x + 0.6, TY.y + 1.0, TY.z + 0.9), 90.0, 0.8, (math.radians(-40), 0, math.radians(150)))
TYRE_CAM = (TY + Vector((-0.62, -0.80, 0.36)), TY + Vector((0.0, -0.05, 0.08)))   # a5gfx numbers in post_ep10.py

# ------------------------------------------------------------------ cameras
sh = K.Shots(N)                  # frame-exact cuts (ep10_za5kit.Shots)


def chase(car, back=6.2, up=1.1, side=-0.6, ahead=9.0, dz=0.6):
    def fn(t):
        p, y = K.at(car, t), K.heading(car, t)
        f, r = Vector((math.cos(y), math.sin(y), 0)), Vector((math.sin(y), -math.cos(y), 0))
        return p - f * back + r * side + Vector((0, 0, up)), p + f * ahead + Vector((0, 0, dz))
    return fn


t0 = TL.a("HOOK")
sh.add("H_chase", 24, t0, t0 + 1.6, chase(H, 5.6, 0.75, -0.4, 10.0, 0.5))
sh.add("H_close", 30, t0 + 1.6, TL.a("SITUATION"),
       lambda t: (Vector((HX + 2.2, EST_Y - 0.8, 0.9)), Vector((KB - 0.3, EST_Y - 2.5, 0.6))))
t0 = TL.a("SITUATION")
sh.add("S_drone", 24, t0, t0 + 2.2, lambda t: (Vector((-14.0 + 2.0 * (t - t0), -36.0 + 1.5 * (t - t0), 17.0)),
                                               Vector((KB, -19.0, 0.0))))
# "Next morning: ice.": low on the frosty footway just behind the parked hero, along its flank at the rear wheel and
# the kerb (the side glass is seen at a grazing angle, no flat window plane). Rear axle 1.38 m behind the middle.
Y_RW = Y_PARK - 1.38
sh.add("S_tread", 35, t0 + 2.2, t0 + 6.0,   # cut on "Next morning: ice." (QA r9)
       lambda t: (Vector((HX + 0.45, Y_RW - 1.85 + 0.12 * (t - t0 - 2.2), 0.40)),
                  Vector((KB + 0.93, Y_RW, 0.26))))
sh.add("S_sign", 30, t0 + 6.0, t0 + 8.0, lambda t: (Vector((S101[0] - 0.9, S101[1] - 5.5 + 0.2 * (t - t0 - 6.0), 1.5)),
                                                   Vector((S101[0] - 0.6, S101[1], 2.3))))
sh.add("S_chase", 22, t0 + 8.0, TL.a("RULE"), chase(H, 7.0, 1.6, -0.9, 10.0, 0.6))
t0 = TL.a("RULE")
sh.add("R_drone", 22, t0, t0 + 5.6, lambda t: (Vector((-9.0, -66.0 + 1.2 * (t - t0), 21.0)), Vector((0.0, -36.0, 0.0))))
sh.add("R_tyre", 32, t0 + 5.6, TL.a("COST"), lambda t: TYRE_CAM)
t0 = TL.a("COST")
# C_chase: the old framing (behind the van, the hero ahead), kept relative to the real stop at Y_COST.
sh.add("C_chase", 22, t0, t0 + 2.2, lambda t: (Vector((LN - 1.2, Y_COST - 28.0, 1.7)),
                                              Vector((LN - 0.3, Y_COST - 13.0, 0.7))))
# C_top under the cards: straight down with west at the top, so the street runs across the frame in one band above
# the card (f 0.19-0.31): the van stopped behind the hero (left), the hero across the lane (middle), the police
# estate stopped short of it (right).
sh.add("C_top", 26, t0 + 2.2, TL.a("CORRECT"), lambda t: (Vector((12.5, Y_COST + 0.5, 36.0 + 0.6 * (t - t0 - 2.2))),
                                                        Vector((12.5, Y_COST + 0.5, 0.0))),
       up_fn=lambda t: Vector((-1.0, 0.0, 0.0)))
t0 = TL.a("CORRECT")
sh.add("K_tyre", 32, t0, t0 + 3.0, lambda t: TYRE_CAM)


def follow(car, back, side, up, ahead, aside, dz):
    """A camera that keeps pace with a car on the straight northbound P_ok (no heading lookup at the stop)."""
    def fn(t):
        p = K.at(car, t)
        return p + Vector((side, -back, up)), p + Vector((aside, ahead, dz))
    return fn


# step 2 ("Rental car? Ask first"): high behind and left of the silver hatchback, the icy street and junction ahead;
# step 3 ("Slow down. Brake early"): a low rear three-quarter from its right, brake lamps on as it slows and stands at
# the junction line. The cut (4.85 s) falls between the two captions.
sh.add("K_street", 26, t0 + 3.0, t0 + 4.85, follow(G, 10.5, -2.6, 4.6, 8.0, 0.0, 0.0))
sh.add("K_chase", 28, t0 + 4.85, TL.a("END"), follow(G, 6.5, 1.3, 0.9, 2.0, -0.9, 0.5))
K.end_card(T, env, sh, TL.a("END"), TL.T, signs_=(("101-51", 0.9),))
K.light(az=245.0, elev=16.0, energy=5.0, exposure=0.3)
a = TL.a
K.finish(sh, TL, wx=[(0.0, a("SITUATION"), "ice", 0.9),
                     (a("SITUATION", 2.2), a("SITUATION", 8.4), "ice", 0.9),
                     (a("SITUATION", 8.4), a("RULE"), "snow+ice", 0.6),
                     (a("RULE"), a("END"), "ice", 0.9)])
