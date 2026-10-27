"""Drive Like a Local #17, Germany: out of fuel on the Autobahn is not a breakdown. Stopping is banned, also on the
hard shoulder (StVO §18 Abs. 8); standing more than three minutes or leaving the car is parking (§12 Abs. 2).
9:16, 30 fps, dusk. Set: the interchange stage (RQ 36) around the northbound exit, SUMO day traffic kept clear of the
heroes (ep09/ep09_zab.py). Heroes: orange hatchback (hero), police estate (beacons, no siren picture), silver estate
(the safe example, hazards on). Indicator on every lane change, hazards where the script asks.
The correct move is shown completed twice: in RULE (from 4.6 s, under "Out of fuel is not a breakdown.", so every
language order shows it before the cost) and in CORRECT under step 2, the hatchback each time going from the exit
lane past the diverge onto the exit ramp (pieces with ramp=True follow interchange.ramp_exit_xy() past DIVERGE).
Step 3 (hazards, vest, barrier) plays over the stuck estate only, captioned as the fallback when the exit is too far.
Canonical timeline (English order; other languages are cut from it, ep17_edit.json):
HOOK 0-2.2, SITUATION 2.2-12.2, RULE 12.2-20.2, COST 20.2-25.8, CORRECT 25.8-33.8, END 33.8-36.5.
Run: python ep17_out_of_fuel.py OUTDIR --frames 1-1095 --res 540 --samples 8 --assets ASSETS [--stills 140,300]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "ep09")]
import ep09_zab as Z  # noqa: E402
import math  # noqa: E402

IC = Z.IC
RAMP = IC.ramp_exit_xy()
RS = [0.0]
for (xa, ya), (xb, yb) in zip(RAMP, RAMP[1:]):
    RS.append(RS[-1] + math.hypot(xb - xa, yb - ya))


def ramp_xy(s):
    """Exit ramp centreline at arc length s from the diverge (northbound coordinates)."""
    for k in range(1, len(RS)):
        if RS[k] >= s:
            u = (s - RS[k - 1]) / max(1e-6, RS[k] - RS[k - 1])
            return (RAMP[k - 1][0] + u * (RAMP[k][0] - RAMP[k - 1][0]),
                    RAMP[k - 1][1] + u * (RAMP[k][1] - RAMP[k - 1][1]))
    return RAMP[-1]


_piece = Z.piece


def piece_exit(n, ramp=False, **kw):
    """Z.piece, plus ramp=True: past DIVERGE the driver follows the exit ramp (arc length = distance driven, height
    from interchange.exit_z), heading taken over +-3 frames so the cameras do not shake on the polyline's corners."""
    rows = _piece(n, **kw)
    if not ramp:
        return rows
    for r in rows:
        s = r["y"] - IC.DIVERGE
        if s > 0.0:
            x, y = ramp_xy(s)
            r["x"] = x + (r["x"] - IC.RAMP_X0) * (1.0 - Z.smooth(s / 20.0))
            r["y"], r["z"] = y, IC.exit_z(s, RS[-1])
    prev = rows[0]["yaw"] if rows else Z.NORTH
    for i, r in enumerate(rows):
        a, b = rows[max(0, i - 3)], rows[min(n - 1, i + 3)]
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        r["yaw"] = prev = math.atan2(dy, dx) if math.hypot(dx, dy) > 0.05 else prev
    return rows


Z.piece = piece_exit                                   # Hero.build looks piece up in ep09_zab at call time

A = Z.cli()
X = Z.X
TL = Z.Timeline([("HOOK", 2.2), ("SITUATION", 10.0), ("RULE", 8.0), ("COST", 5.6), ("CORRECT", 8.0), ("END", 2.7)])
S = Z.build(A, light=(-0.55, 0.8, -0.18), elev=9.0, energy=4.0)
env, traf = S["env"], S["traffic"]
lib = Z.heroes_lib(S["lib"], {"hatch": ("hatch", (0.85, 0.28, 0.02), "QZ RT 418"),
                              "police": ("police", (0.75, 0.76, 0.78), "JX PO 110"),
                              "estate": ("estate", (0.6, 0.62, 0.64), "JJ AB 270")})
hat, pol, est = (Z.Hero(lib[k], k) for k in ("hatch", "police", "estate"))
YS = -460.0                                            # where the hatchback stands on the hard shoulder
YK = 1200.0                                            # where the stuck estate stands (CORRECT, the fallback)


def flag(t0=0.0, **kv):
    return lambda t, r: r.update(**kv) if t >= t0 else None


# ---- HOOK: the last metres onto the hard shoulder, hazards on
hat.at("HOOK", 0.0, y0=YS - 16.3, x0=X["R"], v0=14.0, speed=[(0.0, 0.0, 6.0)], moves=[(0.0, 1.4, X["HS"])],
       inds=[(0.0, 1.4, "R"), (1.4, 9.0, "H")])
# ---- SITUATION: fuel light on, past the exit signs, past the exit, engine dies, onto the shoulder
hat.at("SITUATION", 0.0, y0=-1500.0, x0=X["R"], v0=30.6)
hat.at("SITUATION", 3.0, y0=-714.0, x0=X["R"], v0=30.6, speed=[(0.5, 23.6, 2.0)])
hat.at("SITUATION", 7.0, y0=YS - 10.0, x0=X["R"], v0=10.0, speed=[(0.0, 0.0, 5.0)], moves=[(0.0, 1.6, X["HS"])],
       inds=[(0.0, 0.6, "R"), (0.6, 9.0, "H")])
# ---- RULE and COST: standing on the shoulder, hazards; the police estate pulls up behind. RULE from 4.6 s: the
# right way, the hatchback leaves at the exit (exit lane, past the diverge, onto the ramp; ramp s 62 m by 8.0 s)
hat.at("RULE", 0.0, y0=YS, x0=X["HS"], v0=0.0, inds=[(0.0, 9.0, "H")])
hat.at("RULE", 4.6, y0=-628.0, x0=X["EXIT"], v0=26.0, speed=[(1.0, 20.0, 2.0)], moves=[(0.0, 0.8, IC.RAMP_X0)],
       inds=[(0.0, 2.2, "R")], ramp=True)
hat.at("COST", 0.0, y0=YS, x0=X["HS"], v0=0.0, inds=[(0.0, 9.0, "H")])
pol.at("COST", 0.0, y0=YS - 72.5, x0=X["R"], v0=25.0, speed=[(1.0, 0.0, 9.6)], moves=[(0.3, 1.4, X["HS"])],
       inds=[(0.0, 1.8, "R")], extra=flag(beacon=True))
# ---- CORRECT: takes the exit (right indicator, into the exit lane, at the diverge by 2.85 s, step 2 on, and 60 m
# along the ramp by 5.45 s, all in the K_drone shot); from 5.5 s the fallback: a stuck estate done right
hat.at("CORRECT", 0.0, y0=-696.0, x0=X["R"], v0=30.6, speed=[(0.6, 26.0, 2.0), (4.0, 21.0, 2.0)],
       moves=[(0.5, 1.6, X["EXIT"]), (2.2, 0.8, IC.RAMP_X0)], inds=[(0.2, 3.4, "R")], ramp=True)
est.at("CORRECT", 5.5, y0=YK, x0=X["HS"], v0=0.0, inds=[(0.0, 9.0, "H")])

for h in (hat, pol, est):
    h.bake(TL, traf)

# ---- signs and props: a real 283 on a post at the verge just past the hatchback (kit/signs.py, Commons file);
# a W-beam guardrail on the verge by the stuck estate and its driver in a hi-vis vest standing behind it
Z.sign_post(S, "283", YS + 8.0, env, width=0.9)


def guardrail(y0, y1, x=18.2, step=2.0):
    import world as W
    w = [(0.0, 0.0), (0.03, 0.08), (0.0, 0.155), (0.03, 0.23), (0.0, 0.31)]
    n = int((y1 - y0) / step) + 1
    verts, faces = [], []
    for i in range(n):
        y = y0 + i * step
        g = Z.ground(S, x, y)
        verts += [(x - dx, y, g + 0.45 + hh) for dx, hh in w]
        if i:
            a, b = (i - 1) * len(w), i * len(w)
            faces += [(a + j, b + j, b + j + 1, a + j + 1) for j in range(len(w) - 1)]
    W.mesh_obj("rail_verge", verts, faces, S["M"].steel, env)
    pv, pf = [], []
    for i in range(n):
        y, k = y0 + i * step, len(pv)
        g = Z.ground(S, x, y)
        pv += [(x + 0.05 + sx, y + sy, g + sz) for sz in (-0.3, 0.78) for sx, sy in
               ((-0.05, -0.05), (0.05, -0.05), (0.05, 0.05), (-0.05, 0.05))]
        pf += [(k, k + 1, k + 2, k + 3), (k + 4, k + 7, k + 6, k + 5)] + \
              [(k + j, k + 4 + j, k + 4 + (j + 1) % 4, k + (j + 1) % 4) for j in range(4)]
    W.mesh_obj("rail_verge_posts", pv, pf, S["M"].steel, env)


guardrail(YK - 60.0, YK + 70.0)
try:
    import figures as F
    driver = F.person(env, "hivis_driver", height=1.78, sex="m", hiviz=True, seed=17)
    F.stand(driver, (19.4, YK - 5.0), (15.6, YK - 9.0), TL.N, ground=lambda x, y: Z.ground(S, x, y),
            look=[(TL.a("CORRECT", 5.9), TL.a("CORRECT", 7.0), -55), (TL.a("CORRECT", 7.0), TL.a("CORRECT", 7.9), 40)])
except Exception as e:                                  # figures kit missing: the estate alone shows the safe way
    print("figures not available:", e)
Z.traffic(S, [hat, pol, est], TL, excl=lambda f: (3.0, 48.0))

# ---- cameras
shots = Z.jx.Shots(TL.N)
t = TL.a("HOOK")
shots.add("H_rear", 30, t, t + 1.2, Z.chase(hat, back=4.6, up=0.75, side=0.6, ahead=12.0, look_up=0.7))
shots.add("H_chase", 26, t + 1.2, TL.a("SITUATION"), Z.chase(hat, back=10.0, up=2.6, side=-1.5, ahead=20.0))
t = TL.a("SITUATION")
shots.add("S_pov", 26, t, t + 3.0, Z.pov(hat, L=4.1, ahead=60.0))
shots.add("S_chase", 28, t + 3.0, t + 7.0, Z.chase(hat, back=9.5, up=2.2, side=-0.8, ahead=40.0))
shots.add("S_drone", 26, t + 7.0, TL.a("RULE"), Z.fixed((-6.0, YS - 48.0, 17.0), (14.0, YS + 2.0, 0.0),
                                                       drift=(0.0, 1.5, 0.0), t0=t + 7.0))
t = TL.a("RULE")
# low on the verge behind the hatchback: the real 283 on its post beyond it, traffic passing on the left
shots.add("R_verge", 32, t, t + 2.6, Z.fixed((20.6, YS - 14.0, 2.6), (16.2, YS + 6.0, 1.9), drift=(0.0, 1.0, 0.0),
                                           t0=t))
cr = shots.add("R_rear", 40, t + 2.6, t + 4.6, Z.fixed((14.2, YS - 9.0, 1.05), (15.55, YS, 0.95),
                                                     drift=(0.0, 0.5, 0.0), t0=t + 2.6))
cr.data.dof.use_dof, cr.data.dof.focus_distance, cr.data.dof.aperture_fstop = True, 9.0, 3.2
# the right way, before the cost: high chase behind and left of the hatchback, so the through lanes run on at the
# left while it crosses the diverge and peels off onto the ramp past the gore
shots.add("R_exit", 28, t + 4.6, TL.a("COST"), Z.chase(hat, back=14.0, up=6.5, side=-2.0, ahead=28.0, look_up=0.0))
t = TL.a("COST")
shots.add("C_verge", 32, t, t + 2.2, Z.fixed((19.6, YS + 14.0, 2.3), (14.0, YS - 45.0, 0.9)))
cc = shots.add("C_close", 40, t + 2.2, TL.a("CORRECT"), Z.fixed((14.4, YS - 7.5, 1.25), (15.55, YS - 1.5, 1.05)))
cc.data.dof.use_dof, cc.data.dof.focus_distance, cc.data.dof.aperture_fstop = True, 6.5, 2.8
t = TL.a("CORRECT")
shots.add("K_drone", 26, t, t + 5.5, Z.drone(hat, off=(-22.0, -30.0, 20.0), tgt=(3.0, 18.0, 0.0)))
shots.add("K_stuck", 30, t + 5.5, TL.a("END"), Z.fixed((26.0, YK - 24.0, 5.5), (16.5, YK - 1.0, 1.0),
                                                       drift=(-0.4, 0.8, -0.1), t0=t + 5.5))
Z.end_card(S, env, shots, TL.a("END"), TL.T, signs_=(("330.1", 4.6), ("283", 4.6)))
Z.light(S, A, exposure=0.0)
try:
    import weather as WX
    WX.apply("dusk")
except Exception as e:                                  # weather kit missing: plain low sun
    print("weather dusk not applied:", e)
Z.finish(A, shots, TL)
