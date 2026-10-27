"""Drive Like a Local #19, Germany: tailgating on the Autobahn, in the rain. Keep about half the speedometer reading in
metres (StVO §4 Abs. 1, BKatV table 2); flash the headlights only to warn, never to push (§16). 9:16, 30 fps, rain
(weather.apply("rain"), wheel spray on the heroes). Heroes at 140 km/h, so the over-130 tier of the fine applies.
Set: the interchange stage (RQ 36), SUMO day traffic kept clear of the heroes (ep09/ep09_zab.py). Heroes: dark red
saloon (tailgater), blue hatchback, silver estate (pulls out ahead: a car, never a lorry in the left lane), silver
saloon (fast car), 40 t artic in the right lane, police estate. Gap bars: flat graphics on the road, no numerals.
Canonical timeline (English order; other languages are cut from it, ep19_edit.json):
HOOK 0-2.2, SITUATION 2.2-12.2, RULE 12.2-20.2, COST 20.2-24.7, CORRECT 24.7-31.2, END 31.2-33.9.
Run: python ep19_tailgating.py OUTDIR --frames 1-1017 --res 540 --samples 8 --assets ASSETS [--stills 120,400]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "ep09")]
import ep09_zab as Z  # noqa: E402
from mathutils import Vector  # noqa: E402

A = Z.cli()
X, FPS = Z.X, Z.FPS
TL = Z.Timeline([("HOOK", 2.2), ("SITUATION", 10.0), ("RULE", 8.0), ("COST", 4.5), ("CORRECT", 6.5), ("END", 2.7)])
S = Z.build(A, light=(0.3, 0.9, -0.6), elev=35.0, energy=3.0)
env, traf = S["env"], S["traffic"]
lib = Z.heroes_lib(S["lib"], {"sal": ("saloon", (0.32, 0.02, 0.03), "QX RD 140"),
                              "hat": ("hatch", (0.06, 0.2, 0.5), "JJ BL 25"),
                              "est": ("estate", (0.62, 0.64, 0.66), "QZ ES 77"),
                              "fast": ("saloon", (0.7, 0.71, 0.72), "JX FS 19"),
                              "art": ("artic", (0.85, 0.86, 0.87), "QZ TR 62"),
                              "pol": ("police", (0.75, 0.76, 0.78), "JX PO 19")})
sal, hat, est, fast, art, pol = (Z.Hero(lib[k], k) for k in ("sal", "hat", "est", "fast", "art", "pol"))
V, HG = 38.9, 4.45                      # 140 km/h; centre gap = bumper gap + 4.45 (saloon 2.4 + hatchback 2.05)


def dive(t0, t1, p=-0.035):
    return lambda t, r: r.update(pitch=p * Z.smooth((t - t0) / 0.25)) if t0 <= t < t1 else None


def beacon(t, r):
    r["beacon"] = True


# ---- HOOK: on the hatchback's bumper in the left lane, two flashes
hat.at("HOOK", 0.0, y0=600.0, x0=X["L"], v0=V)
sal.at("HOOK", 0.0, y0=600.0 - 6.0 - HG, x0=X["L"], v0=V)
# ---- SITUATION: closes from 30 m to 6 m, flashes, the estate pulls out ahead, both brake hard
H0 = 950.0
hat.at("SITUATION", 0.0, y0=H0, x0=X["L"], v0=V, speed=[(7.4, 30.6, 7.0)], extra=dive(7.4, 8.6, -0.025))
sal.at("SITUATION", 0.0, y0=H0 - 30.0 - HG, x0=X["L"], v0=54.9, speed=[(0.0, V, 5.33), (7.6, 30.6, 9.0)],
       extra=dive(7.6, 8.8))
est.at("SITUATION", 0.0, y0=H0 + 96.5, x0=X["M"], v0=30.6, inds=[(5.4, 7.8, "L")], moves=[(6.2, 1.4, X["L"])])
# ---- RULE: the short red bar against the green half-speed bar; then the right gap
R2 = -1500.0
sal.at("RULE", 0.0, y0=-1900.0, x0=X["L"], v0=V).at("RULE", 3.5, y0=R2, x0=X["L"], v0=V)
hat.at("RULE", 0.0, y0=-1900.0 + 6.0 + HG, x0=X["L"], v0=V).at("RULE", 3.5, y0=R2 + 70.0 + HG, x0=X["L"], v0=V)
# ---- COST: police estate behind him, then both on the hard shoulder
YC = 1700.0
sal.at("COST", 0.0, y0=-1300.0, x0=X["M"], v0=33.0).at("COST", 2.2, y0=YC, x0=X["HS"], v0=0.0)
pol.at("COST", 0.0, y0=-1300.0 - 18.0, x0=X["M"], v0=33.0, extra=beacon) \
   .at("COST", 2.2, y0=YC - 14.5, x0=X["HS"], v0=0.0, extra=beacon)
# ---- CORRECT: long gap behind the slower hatchback; wait for the fast car; indicate, pass, indicate, back right
S1, S2, H3 = 300.0, 1100.0, 1650.0
sal.at("CORRECT", 0.0, y0=S1, x0=X["M"], v0=30.6)
hat.at("CORRECT", 0.0, y0=S1 + 70.0 + HG, x0=X["M"], v0=30.6)
art.at("CORRECT", 0.0, y0=S1 + 50.0, x0=X["R"], v0=22.2)
sal.at("CORRECT", 3.0, y0=S2, x0=X["M"], v0=30.6, inds=[(0.6, 2.0, "L")], moves=[(0.8, 1.2, X["L"])],
       speed=[(1.2, V, 3.0)])
hat.at("CORRECT", 3.0, y0=S2 + 50.0 + HG, x0=X["M"], v0=30.6)
fast.at("CORRECT", 3.0, y0=S2 - 8.0, x0=X["L"], v0=45.0)
sal.at("CORRECT", 5.0, y0=H3 + 22.0, x0=X["L"], v0=V, inds=[(0.4, 1.6, "R")], moves=[(0.8, 1.2, X["M"])])
hat.at("CORRECT", 5.0, y0=H3, x0=X["M"], v0=30.6)

heroes = (sal, hat, est, fast, art, pol)
for h in heroes:
    h.bake(TL, traf)
RF = (TL.f0("RULE"), TL.f0("COST"))
Z.traffic(S, list(heroes), TL, excl=lambda f: (3.4, 95.0) if RF[0] <= f <= RF[1] else (3.4, 50.0))


# ---- gap bars (flat graphics on the road, no numerals)
def gap(f):
    a, b = sal.track[f - 1], hat.track[f - 1]
    if a["z"] < -100 or b["z"] < -100 or abs(a["x"] - b["x"]) > 0.5:
        return None
    return a["x"], a["y"] + 2.4, b["y"] - 2.05, 0.0


def window(ranges):
    return lambda f: any(TL.a(s, r0) * FPS + 1 <= f <= TL.a(s, r1) * FPS + 1 for s, r0, r1 in ranges)


frames = list(range(1, TL.N + 1))
# one graphic language in every shot: red = his gap, green = the gap he needs; both centred in the lane, 1.6 m wide,
# translucent, unlit, with a cross bar at each end (a measured distance, not a lane marking); red drawn over green
red, green = Z.bar("gap_red", (0.95, 0.05, 0.03), env), Z.bar("gap_green", (0.05, 0.78, 0.22), env)
w_red = window([("SITUATION", 0.3, 7.0), ("RULE", 0.2, 3.5)])
Z.key_bar(red, frames, lambda f: gap(f) if w_red(f) else None, dz=0.075)
w_green = window([("RULE", 0.6, 3.5), ("RULE", 3.6, 8.0), ("CORRECT", 0.2, 3.0)])


def green_fn(f):
    if not w_green(f):
        return None
    g = gap(f)
    if g is None:
        return None
    x, y0, y1, z = g
    if TL.f0("RULE") + 1 <= f <= TL.a("RULE", 3.5) * FPS:          # the safe length beside the short gap
        return x, y0, y0 + 70.0, z
    return x, y0, y1, z


Z.key_bar(green, frames, green_fn, dz=0.06)

# ---- cameras
shots = Z.jx.Shots(TL.N)
t = TL.a("HOOK")


def rev(tt):
    ph, _ = hat.pos(tt)
    ps, _ = sal.pos(tt)
    return ph + Vector((1.45, -3.1, 0.8)), ps + Vector((0.0, 1.9, 0.75))


shots.add("H_rev", 32, t, t + 1.4, rev)
shots.add("H_chase", 26, t + 1.4, TL.a("SITUATION"), Z.chase(sal, back=13.0, up=2.8, side=-1.0, ahead=20.0))
t = TL.a("SITUATION")
shots.add("S_drone", 26, t, t + 3.0, Z.drone(sal, off=(14.0, -20.0, 17.0), tgt=(-0.5, 9.0, 0.0)))
shots.add("S_chase", 28, t + 3.0, t + 7.0, Z.chase(sal, back=9.0, up=1.9, side=0.3, ahead=40.0))


def close(tt):
    """Three-quarter view from the middle lane: his bonnet, the short gap and the hatchback's brake lights in one
    frame (the old eye sat between the two cars, inside the hatchback's spray, and saw only glare)."""
    p, _ = sal.pos(tt)
    return p + Vector((5.2, 1.0, 1.7)), p + Vector((-0.3, 7.5, 0.7))


shots.add("S_close", 30, t + 7.0, TL.a("RULE"), close)
t = TL.a("RULE")
shots.add("R_top", 30, t, t + 3.5, Z.top(sal, height=74.0, ahead=38.0, side=-0.6), up_fn=lambda tt: Z.UP_N)
shots.add("R_chase", 26, t + 3.5, TL.a("COST"), Z.chase(sal, back=11.0, up=3.4, side=-0.4, ahead=45.0))
t = TL.a("COST")


def front(tt):
    p, _ = sal.pos(tt)
    return p + Vector((-1.6, 9.0, 1.5)), p + Vector((0.3, -8.0, 0.8))


shots.add("C_front", 30, t, t + 2.2, front)
shots.add("C_top", 30, t + 2.2, TL.a("CORRECT"), Z.fixed((X["HS"] - 1.0, YC - 7.0, 36.0), (X["HS"] - 1.0, YC - 6.99, 0.0)),
          up_fn=lambda tt: Z.UP_N)
t = TL.a("CORRECT")
shots.add("K_top", 30, t, t + 3.0, Z.top(sal, height=76.0, ahead=38.0, side=0.0), up_fn=lambda tt: Z.UP_N)
shots.add("K_chase", 28, t + 3.0, t + 5.0, Z.chase(sal, back=9.0, up=2.2, side=0.8, ahead=40.0))
shots.add("K_drone", 26, t + 5.0, TL.a("END"), Z.drone(sal, off=(-16.0, -22.0, 13.0), tgt=(4.0, 8.0, 0.0)))
Z.end_card(S, env, shots, TL.a("END"), TL.T, signs_=())
Z.light(S, A, exposure=0.0, haze=1800.0)
try:
    import weather as WX
    # toned down so the cars and the gap read: less glare, lighter spray, red tail glow at a quarter, 1.5 km sight
    WX.apply("rain", auto_spray=False, bloom=0.1, visibility=1500.0)
    for h in heroes:
        WX.spray(h.rig.obj, frames=range(1, TL.N + 1), strength=0.45)
    for o in Z.bpy.data.objects:
        if o.name.startswith("wx_tailglow_"):
            o.data.energy *= 0.25
except Exception as e:
    print("weather rain not applied:", e)
Z.key_head(sal, [(TL.a("HOOK", a), TL.a("HOOK", a + 0.15)) for a in (0.3, 0.8)] +
           [(TL.a("SITUATION", a), TL.a("SITUATION", a + 0.15)) for a in (3.2, 3.8)], level=6.0)
Z.finish(A, shots, TL)
