"""Drive Like a Local #9, Germany: no speed limit on the Autobahn? Not so fast. Zeichen 282 ends every limit, 130 km/h
is only the recommended speed (Zeichen 380), and legal is not the same as safe. 9:16, 30 fps, day.
Set: the interchange stage (RQ 36) north of the junction, SUMO day traffic kept clear of the heroes (ep09_zab.py).
A 120 limit (274-120) before the stretch, 282 at y 900, 380 at y 1500. Heroes: dark saloon, white van, 40 t artic,
silver saloon (fast car). Keep right, overtake on the left only, no lorry in the left lane, indicator on every change.
Canonical timeline (English order; other languages are cut from it, ep09_edit.json):
HOOK 0-2.2, SITUATION 2.2-12.2, RULE 12.2-20.2, COST 20.2-25.7, CORRECT 25.7-32.2, END 32.2-34.9.
Run: python ep09_no_speed_limit.py OUTDIR --frames 1-1047 --res 540 --samples 8 --assets ASSETS [--stills 82,322]
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "ep09")]
import ep09_zab as Z  # noqa: E402
from mathutils import Vector  # noqa: E402

A = Z.cli()
X, FPS = Z.X, Z.FPS
TL = Z.Timeline([("HOOK", 2.2), ("SITUATION", 10.0), ("RULE", 8.0), ("COST", 5.5), ("CORRECT", 6.5), ("END", 2.7)])
S = Z.build(A, light=(0.35, 0.9, -0.5), elev=30.0, energy=4.4)
env, traf = S["env"], S["traffic"]
lib = Z.heroes_lib(S["lib"], {"saloon": ("saloon", (0.03, 0.04, 0.06), "QX DL 909"),
                              "van": ("van", (0.86, 0.87, 0.88), "JJ VK 31"),
                              "artic": ("artic", (0.04, 0.12, 0.35), "QZ TR 480"),
                              "fast": ("saloon", (0.62, 0.64, 0.67), "JX FS 72")})
sal, van, art, fast = (Z.Hero(lib[k], k) for k in ("saloon", "van", "artic", "fast"))

# ---- signs (Commons, kit/signs.py): 120 limit, then 282 ends it; 380 recommended speed further on
Y282, Y380 = 900.0, 1500.0
Z.sign_post(S, "274-120", 330.0, env, width=0.9)
Z.sign_post(S, "282", Y282, env, width=0.9)
# no Zeichen 380: the only Commons drawing (StVO 1988) shows 80, which would contradict "Recommended: 130 km/h"

# ---- HOOK: flat out in the left lane
sal.at("HOOK", 0.0, y0=1560.0, x0=X["L"], v0=56.0)
art.at("HOOK", 0.0, y0=1600.0, x0=X["R"], v0=22.2)
# ---- SITUATION: 120 limit ends, he accelerates to 200, the van pulls out, hard braking
sal.at("SITUATION", 0.0, y0=880.0, x0=X["L"], v0=33.3, speed=[(0.6, 56.0, 5.0), (8.0, 30.6, 9.0)])
van.at("SITUATION", 0.0, y0=1068.0, x0=X["M"], v0=30.6, inds=[(6.0, 8.8, "L")], moves=[(7.0, 1.7, X["L"])])
art.at("SITUATION", 0.0, y0=1150.0, x0=X["R"], v0=22.2)
# ---- RULE: cruising past 282, then past 380 (middle lane, 130 km/h)
sal.at("RULE", 0.0, y0=860.0, x0=X["M"], v0=36.1).at("RULE", 3.5, y0=1430.0, x0=X["M"], v0=36.1)
art.at("RULE", 3.5, y0=1470.0, x0=X["R"], v0=22.2)


# ---- COST: he swerves too late, clips the van's rear corner, spins onto the hard shoulder
def haz_from(t0):
    return lambda t, r: r.update(ind="H") if t >= t0 else None


sal.at("COST", 0.0, y0=1715.0, x0=X["L"], v0=45.0, speed=[(0.0, 36.0, 9.0), (1.0, 0.0, 16.0)],
       moves=[(0.5, 0.6, 6.4), (1.05, 1.7, X["HS"])], yaw_off=[(1.0, 1.7, 2.4)], extra=haz_from(2.6))
van.at("COST", 0.0, y0=1730.0, x0=X["L"], v0=30.6, speed=[(1.0, 0.0, 17.0)], moves=[(1.0, 0.9, 3.7)],
       yaw_off=[(1.0, 1.0, -0.42)], extra=haz_from(2.6))
# ---- CORRECT: right lane at 130, artic ahead: indicate, pass in the middle lane, back right; fast car on the left
sal.at("CORRECT", 0.0, y0=-1900.0, x0=X["R"], v0=36.1, inds=[(1.5, 3.1, "L"), (5.0, 6.5, "R")],
       moves=[(2.0, 1.5, X["M"]), (5.6, 1.4, X["R"])])
art.at("CORRECT", 0.0, y0=-1845.0, x0=X["R"], v0=22.2)
fast.at("CORRECT", 0.0, y0=-1964.0, x0=X["L"], v0=52.8)

for h in (sal, van, art, fast):
    h.bake(TL, traf)
CF = (TL.f0("COST"), TL.f0("CORRECT"))
Z.traffic(S, [sal, van, art, fast], TL, excl=lambda f: (14.0, 170.0) if CF[0] <= f <= CF[1] else (3.4, 48.0))

# ---- cameras
shots = Z.jx.Shots(TL.N)
t = TL.a("HOOK")
shots.add("H_chase", 24, t, t + 1.5, Z.chase(sal, back=6.2, up=0.85, side=0.5, ahead=30.0, look_up=0.9))


def wheel(h, t0):
    def fn(tt):
        p, yaw = h.pos(tt)
        return p + Vector((-2.3, 2.6, 0.45)), p + Vector((-0.6, 0.9, 0.4))
    return fn


shots.add("H_wheel", 30, t + 1.5, TL.a("SITUATION"), wheel(sal, t + 1.5))
t = TL.a("SITUATION")
# the real 282 on its post in the right foreground, the saloon passing it in the left lane (no floating call-out:
# the sign is named in the caption)
shots.add("S_drone", 26, t, t + 2.5, Z.fixed((20.6, Y282 - 14.0, 2.6), (8.0, Y282 + 30.0, 1.2), drift=(-0.2, 1.5, 0.0),
                                            t0=t))
shots.add("S_chase", 28, t + 2.5, t + 7.0, Z.chase(sal, back=9.0, up=1.9, side=0.4, ahead=60.0))
shots.add("S_pov", 24, t + 7.0, TL.a("RULE"), Z.pov(sal, L=4.8, ahead=50.0))
t = TL.a("RULE")
cr = shots.add("R_282", 40, t, t + 3.5, Z.fixed((16.6, Y282 - 16.0, 1.7), (18.6, Y282, 2.45), drift=(0.25, 2.2, 0.05), t0=t))
cr.data.dof.use_dof, cr.data.dof.focus_distance, cr.data.dof.aperture_fstop = True, 15.0, 4.0
shots.add("R_380", 30, t + 3.5, TL.a("COST"), Z.fixed((32.0, Y380 - 44.0, 10.0), (17.0, Y380 + 4.0, 2.0),
                                                     drift=(-0.6, 3.0, -0.3), t0=t + 3.5))
t = TL.a("COST")
shots.add("C_drone", 26, t, t + 2.8, Z.drone(van, off=(26.0, -34.0, 15.0), tgt=(4.0, 10.0, 0.0)))
shots.add("C_top", 30, t + 2.8, TL.a("CORRECT"), Z.fixed((9.5, 1768.0, 58.0), (9.5, 1768.01, 0.0)),
          up_fn=lambda tt: Z.UP_N)
t = TL.a("CORRECT")
shots.add("K_chase", 28, t, t + 3.0, Z.chase(sal, back=9.0, up=2.0, side=-0.6, ahead=50.0))
shots.add("K_drone", 26, t + 3.0, TL.a("END"), Z.drone(sal, off=(-20.0, -30.0, 16.0), tgt=(2.0, 14.0, 0.0)))
Z.end_card(S, env, shots, TL.a("END"), TL.T, signs_=(("282", 4.6),))
Z.light(S, A)
Z.finish(A, shots, TL)
