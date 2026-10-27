"""Drive Like a Local #15, Germany: merging early is the mistake, the zipper merge (Reissverschluss, StVO section 7
Abs. 4). 9:16, 30 fps, 1056 frames (35.2 s), golden hour. Canonical order HOOK 0-2.2, SITUATION 2.2-12.2,
RULE 12.2-19.7, COST 19.7-25.1, CORRECT 25.1-31.6, END 31.6-35.2 (the per-language cuts reorder the segments, see
post_ep15.py).
World: the episode 1 Autobahn on a 4 km road with a roadworks lane drop: the LEFT lane ends (Zeichen 531-21, Leitbaken
605-20 "Aufstellung links", Commons pictures; no mobile barrier because the Commons 616 picture points the other way),
1:20 taper, yellow lines, the 120, 100, 80 funnel. A jam stands in front of the lane drop.
Traffic is simulated (ep13_zkit.Sim with a zipper controller: the lane that ends is used to its end, then one car from
each lane in turn, indicators on, a driver leaves the gap):
  A (the mistake): most drivers merged early, so the queue stands in the two right lanes and the left lane is empty
    for a long stretch; the teal hatchback squeezes into the queue far too early;
  B (the right move): both lanes are used to the end and the queue is about half as long; the hatchback rolls to the
    end of its lane and zips in.
Run: python ep15_zipper_merge.py OUTDIR --frames 1-1056 --res 540 --samples 8 --assets ASSETS
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit"), os.path.join(HERE, "..", "ep13")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import ep13_zkit as Z  # noqa: E402
import lanemgmt as LM  # noqa: E402
import motion  # noqa: E402
import roadworks as RW  # noqa: E402
import stage  # noqa: E402
import vehicles as V  # noqa: E402

O = Z.cli()
C = Z.Canon([("HOOK", 2.2), ("SITUATION", 10.0), ("RULE", 7.5), ("COST", 5.4), ("CORRECT", 6.5), ("END", 3.6)])
ST = 2300.0
TEAL = (0.006, 0.26, 0.27)
HERO_L = V.KINDS["hatch"]["L"]

MODELS = {}


def prebuild(lib):
    allm, models = Z.fleet_models(lib)
    allm["hero"] = V.car("hatch", TEAL, "hero", "JX DL 15", metal=0.45, c=lib)
    MODELS.update(allm)
    MODELS["_sim"] = models


Z.prebuild(prebuild)
S = Z.world(O["ASSETS"], length=4000.0, s0=40.0, s1=3960.0, gantry_s=0, bridge_s=3100.0, phone_s=1100.0)
road, lib, env, traffic, M = S["road"], S["lib"], S["env"], S["traffic"], S["M"]
sc = bpy.context.scene
sc.render.fps = Z.FPS
sc.frame_start, sc.frame_end = 1, C.N
LM.setup(O["ASSETS"])

rw = RW.RoadWorks(road, M, env, lib, s_taper=ST, side="left", road_s0=40.0, strict=False)
rw.flash(1, C.N)
SM = rw.s_merge - 10.0             # the end of the left lane: the zip point

# ---------------------------------------------------------------- traffic: two worlds
SIMS = MODELS["_sim"]
LIM = [(ST - 1200.0, ST - 600.0, Z.kmh(120)), (ST - 600.0, ST - 200.0, Z.kmh(100)), (ST - 200.0, 3960.0, Z.kmh(80))]


def xfun(lanef, s):
    l0 = max(0, min(2, int(math.floor(lanef))))
    l1 = min(2, l0 + 1)
    u = lanef - l0
    return rw.lane_x(l0, s) + (rw.lane_x(l1, s) - rw.lane_x(l0, s)) * u


def build(world, seed):
    sim = Z.Sim(0.0, 3960.0, seed=seed)
    sim.set_models(SIMS)
    sim.zipper = (0, 1, SM)
    sim.limits.extend(LIM)
    if world == "A":
        q = 650.0
        pol0 = lambda s: {"late": s.rnd.random() < 0.25, "early_at": s.rnd.uniform(450.0, 800.0)}  # noqa: E731
    else:
        q = 330.0
        pol0 = lambda s: {"late": True}  # noqa: E731
    jam = lambda: 2.3 + sim.rnd.random() * 2.2  # noqa: E731
    sim.fill(1, SM - q, SM - 3.0, 1.0, 1.5, [("car", 6), ("van", 1)], v0_range=(26.0, 33.0), jam_gap=jam)
    sim.fill(2, SM - q, SM - 3.0, 1.0, 1.5, [("car", 3), ("truck", 3)], v0_range=(22.0, 26.0), jam_gap=jam)
    if world == "A":
        sim.fill(0, SM - q, SM - 3.0, 1.0, 2.0, [("car", 1)], v0_range=(26.0, 33.0),
                 jam_gap=lambda: 45.0 + 50.0 * sim.rnd.random(), policy={"late": True})
    else:
        sim.fill(0, SM - q, SM - 3.0, 1.0, 1.5, [("car", 1)], v0_range=(26.0, 33.0), jam_gap=jam, policy={"late": True})
    for lane, kinds in ((0, [("car", 1)]), (1, [("car", 6), ("van", 1)]), (2, [("car", 3), ("truck", 3)])):
        sim.fill(lane, 40.0, SM - q - 60.0, 2.2, 27.0, kinds, v0_range=(26.0, 34.0) if lane < 2 else (22.0, 26.0),
                 policy=pol0 if lane == 0 else None)
        sim.inflow.append((lane, 2.4, kinds, 26.0, 33.0))
    target = SM - (850.0 if world == "A" else 45.0)
    h = min((c for c in sim.vs if c.lane == 0), key=lambda c: abs(c.s - target))
    h.id, h.model, h.L = "hero", "hero", HERO_L
    h.policy = {"late": False, "early_at": 620.0} if world == "A" else {"late": True}
    return sim


simA = build("A", 15)
LOCAL_T0 = 30.0


def local(k):
    """Three local drivers rolling past the standing queue in the free left lane at about 8 km/h."""
    def fn(T):
        h = simA.sample("hero", LOCAL_T0)
        s0 = (h["s"] if h else SM - 600.0) - 18.0 - 16.0 * k
        return dict(s=s0 + 2.3 * (T - LOCAL_T0), lane=0.0, v=2.3, ind=None)
    return fn


simA.run(0.0, 75.0)
for k in range(3):
    simA.script(f"local{k}", SIMS["car"][(3 * k + 1) % len(SIMS["car"])][0], 4.7, local(k))
simA.drop_conflicts()
lcA = simA.lane_changes("hero")[0]
simB = build("B", 15)
simB.run(0.0, 75.0)
lcB = simB.lane_changes("hero")[0]
print("hero A lane change", [round(x, 2) for x in lcA], "hero B", [round(x, 2) for x in lcB], flush=True)
print("zip SM", round(SM, 1), "taper", [round(getattr(rw, k), 1) for k in ("s_t0", "s_t1", "s_merge") if hasattr(rw, k)],
      "hero B s at lane change", [round(simB.sample("hero", x)["s"], 1) for x in lcB[:2]], flush=True)

D = Z.Director(C, road, xfun)
D.variant("A", simA)
D.variant("B", simB)
D.variant("_card", None)
t = C.t
HA, HB = "A:hero", "B:hero"
D.protect |= {"local0", "local1", "local2"}


def hero_s(key, f):
    return D.st(key, f)["s"]


def queue_tail(sim, T, lane=1):
    tail = SM
    for c in sim.vs:
        x = sim.sample(c.id, T)
        if x and x["v"] < 3.0 and x["s"] < SM and abs(x["lane"] - lane) < 0.3:
            tail = min(tail, x["s"])
    return tail


# ---------------------------------------------------------------- shots
# HOOK: drone straight down the lane: the queue on the right, the left lane empty, he squeezes in far too early
D.shot("H_drone", t("HOOK", 0.0), t("HOOK", 2.2), "A", lcA[0] - 1.0, lens=28,
       cam=lambda tt, f: (road.point(hero_s(HA, f) - 24.0, 2.2, 20.0), road.point(hero_s(HA, f) + 140.0, 6.8, 0.0)))
# SITUATION 0.0-3.0: 60 m up, the lane-end board far ahead, he joins the queue early
D.shot("S_drone", t("SITUATION", 0.0), t("SITUATION", 3.0), "A", lcA[0] - 2.0, lens=28,
       cam=lambda tt, f: (road.point(hero_s(HA, f) - 50.0, -10.0, 60.0), road.point(SM - 60.0, 8.0, 0.0)))
# SITUATION 3.0-7.0: behind him in the queue; locals roll past in the free left lane
D.shot("S_chase", t("SITUATION", 3.0), t("SITUATION", 7.0), "A", LOCAL_T0 - 0.5, lens=30,
       cam=D.chase(HA, back=8.5, side=-2.4, up=2.3, ahead=40.0, ahead_up=1.0, ahead_side=-1.5))
TQ = lcA[1] + 12.0
QA = queue_tail(simA, TQ)
# SITUATION 7.0-10.0: from above, a red bar grows over the queue; the left lane lies empty
D.shot("S_top", t("SITUATION", 7.0), t("SITUATION", 10.0), "A", TQ, lens=26,
       cam=lambda tt, f: (road.point(QA - 70.0 + 6.0 * tt, -4.0, 85.0 - 2.0 * tt), road.point(SM - 40.0, 8.5, 0.0)))
# RULE 0.0-3.5: drone, both lanes glow green to the end, the alternating arrows at the end
D.shot("R_drone", t("RULE", 0.0), t("RULE", 3.5), "B", 20.0, lens=28,
       cam=lambda tt, f: (road.point(SM - 230.0 + 8.0 * tt, -5.0, 44.0), road.point(SM + 15.0, 8.0, 0.0)))
# RULE 3.5-7.5: straight down on the end of the lane: one from the left, one from the right, like a zip
D.shot("R_zip", t("RULE", 3.5), t("RULE", 7.5), "B", 33.0, lens=32,
       cam=lambda tt, f: (road.point(SM - 6.0, 8.2, 34.0), road.point(SM - 6.0, 8.2, 0.0), road.frame(SM)[2]))
# COST 0.0-1.35 and 1.35-2.7: the same stretch from above: early merging (long red queue), zipping (short green)
TB = 50.0
QB = queue_tail(simB, TB)
QA2 = queue_tail(simA, TB)
mid = SM - 330.0
D.shot("K_topA", t("COST", 0.0), t("COST", 1.35), "A", TB, lens=26,
       cam=lambda tt, f: (road.point(SM + 40.0, 9.0, 62.0), road.point(SM - 420.0, 9.5, 0.0)))
D.shot("K_topB", t("COST", 1.35), t("COST", 2.7), "B", TB, lens=26,
       cam=lambda tt, f: (road.point(SM + 40.0, 9.0, 62.0), road.point(SM - 420.0, 9.5, 0.0)))
# COST 2.7-5.4: the driver he cut in front of flashes his headlights
TF = lcA[1] + 1.5
fol = None
best = 1e9
hs = simA.sample("hero", TF)
for c in simA.vs:
    x = simA.sample(c.id, TF)
    if c.id != "hero" and x and abs(x["lane"] - 1.0) < 0.2 and x["s"] < hs["s"]:
        if hs["s"] - x["s"] < best:
            best, fol = hs["s"] - x["s"], c.id
FK = "A:" + (fol or "hero")
D.protect.add(fol or "hero")
D.shot("K_flash", t("COST", 2.7), t("COST", 5.4), "A", TF, lens=32,      # over his shoulder, back at the follower
       cam=lambda tt, f: (road.point(hero_s(HA, f) - 1.0, xfun(1.0, hero_s(HA, f)) - 1.8, 2.4),
                          road.point(hero_s(FK, f) + 1.8, xfun(1.0, hero_s(FK, f)) + 0.3, 0.9)))
# CORRECT 0.0-3.0: drone, he stays in the left lane to its end, rolling slowly
D.shot("C_drone", t("CORRECT", 0.0), t("CORRECT", 3.0), "B", lcB[0] - 4.0, lens=28,
       cam=D.chase(HB, back=30.0, side=-6.0, up=18.0, ahead=40.0, ahead_up=0.0, ahead_side=4.0))
# CORRECT 3.0-6.5: crane high on the left, the whole closing taper in frame: indicator right, a driver lets him in,
# he slots in where the Baken squeeze the lane, the next one follows (QA r3: from behind at car height the merge
# looked early, with the left lane running on ahead; hero B merges 35 to 45 m before the zip point, inside the taper)
SZ = simB.sample("hero", lcB[0])["s"]
D.shot("C_chase", t("CORRECT", 3.0), t("CORRECT", 6.5), "B", lcB[0] - 1.0, lens=28,
       cam=lambda tt, f: (road.point(SZ - 24.0 + 1.6 * tt, 0.6, 10.5 - 0.3 * tt),
                          road.point(SZ + 24.0 + 1.6 * tt, 7.6, 0.0)))

Z.end_card(D, "E_card", t("END", 0.0), C.T, [("de-core", "123"), ("de-core", "531-21")], O["ASSETS"])

# ---------------------------------------------------------------- vehicles, cameras, graphics
D.build_tracks()
D.cull(500.0, {"S_top": 900.0, "K_topA": 900.0, "K_topB": 900.0, "S_drone": 800.0, "R_drone": 700.0})
D.cast(traffic, MODELS)
D.cameras()
# the follower flashes his headlights twice (Lichthupe)
if FK in D.objs:
    e, r = D.objs[FK]
    f0 = C.frame(t("COST", 3.0))
    vals = []
    for f in range(1, C.N + 1):
        on = (f0 <= f < f0 + 5) or (f0 + 10 <= f < f0 + 15)
        vals.append(1.0 if on else 0.0)
    for o in r.units.values():
        motion.keys(o, '["head"]', 0, list(range(1, C.N + 1)), vals, interp=0, compress=True)

# call-out: the lane-end board in the SITUATION drone
Z.hud_sign(D.cam_obj("S_drone"), ("de-core", "531-21"), t("SITUATION", 0.5), t("SITUATION", 2.95), u=0.76, v=0.72,
           wfrac=0.28, name="call_531")


def glow_strip(name, x0, x1, s0, s1, rgb, keys, pieces=1, grow=None):
    """Translucent glow over lanes on the road. grow=(t0, t1): pieces appear one by one from s1 back to s0."""
    m = Z.fade_mat(name + "_m", rgb, 2.0)
    out = []
    step = (s1 - s0) / pieces
    for k in range(pieces):
        a, b = s1 - (k + 1) * step, s1 - k * step
        o = road.strip(f"{name}_{k}", x0, x1, a, b, m, env, dz0=0.03)
        o.visible_shadow = False
        if grow:
            tk = grow[0] + (grow[1] - grow[0]) * k / max(1, pieces - 1)
            kk = [(1, 0.0), (C.frame(tk) - 1, 0.0), (C.frame(tk) + 2, keys[0][1])] + [(C.frame(tt), v) for tt, v in keys[1:]]
        else:   # hold at zero until the first key (a ramp from frame 1 tinted every earlier shot)
            kk = [(1, 0.0), (C.frame(keys[0][0]) - 1, 0.0)] + [(C.frame(tt), v) for tt, v in keys]
        Z.key_alpha(o, sorted(kk))
        out.append(o)
    return out


L1 = (rw.lane_x(1, SM - 50.0) - 1.6, rw.lane_x(1, SM - 50.0) + 1.6)
L0 = (rw.lane_x(0, SM - 300.0) - 1.6, rw.lane_x(0, SM - 300.0) + 1.6)
L12 = (rw.lane_x(1, SM - 50.0) - 1.6, rw.lane_x(2, SM - 50.0) + 1.6)
t7 = t("SITUATION", 7.0)
glow_strip("a4_q_red", L12[0], L12[1], QA, SM, (1.0, 0.08, 0.04),
           [(t7, 0.5), (t7 + 2.95, 0.5), (t7 + 3.0, 0.0)], pieces=24, grow=(t7 + 0.4, t7 + 2.2))
r0 = t("RULE", 0.0)
for nm, (a, b) in (("a4_g0", L0), ("a4_g1", L1)):
    glow_strip(nm, a, b, SM - 330.0, SM - 4.0, (0.15, 1.0, 0.3), [(r0 + 0.3, 0.0), (r0 + 0.9, 0.45), (r0 + 3.45, 0.45),
                                                                  (r0 + 3.5, 0.0)])
k0 = t("COST", 0.0)
glow_strip("a4_k_red", L12[0], L12[1], QA2, SM, (1.0, 0.08, 0.04), [(k0, 0.5), (k0 + 1.3, 0.5), (k0 + 1.35, 0.0)])
glow_strip("a4_k_green", L0[0], L12[1], QB, SM, (0.15, 1.0, 0.3), [(k0 + 1.35, 0.5), (k0 + 2.65, 0.5), (k0 + 2.7, 0.0)])
# alternating arrows at the end of the lane: one from the left lane into the right one, one straight on, blinking
arr_m = Z.fade_mat("a4_zip_arrow", (1.0, 1.0, 1.0), 2.4)


def arrow(name, s, x, ang):
    pts = [(-0.35, -2.4), (0.35, -2.4), (0.35, 0.6), (1.0, 0.6), (0.0, 2.2), (-1.0, 0.6), (-0.35, 0.6)]
    ca, sa = math.cos(ang), math.sin(ang)
    vs = [tuple(road.point(s + py * ca - px * sa, x + px * ca + py * sa, 0.05)) for px, py in pts]
    o = Z._mesh(name, vs, [tuple(range(len(vs)))], arr_m, env)
    o.visible_shadow = False
    return o


a_left = arrow("a4_arrow_left", SM - 16.0, rw.lane_x(0, SM - 40.0) + 1.2, math.radians(-28))
a_right = arrow("a4_arrow_right", SM - 16.0, rw.lane_x(1, SM - 16.0), 0.0)
for o, ph in ((a_left, 0), (a_right, 1)):
    kk = [(1, 0.0)]
    tt = r0 + 0.8
    k = 0
    while tt < r0 + 3.45:
        kk += [(C.frame(tt), 0.9 if (k % 2) == ph else 0.0)]
        tt += 0.45
        k += 1
    kk.append((C.frame(r0 + 3.5), 0.0))
    Z.key_alpha(o, kk, interp="CONSTANT")

# ---------------------------------------------------------------- light and render
c0, th, fwd, right, _ = road.frame(SM - 200.0)
stage.sky(road, (-fwd * 0.7 + right * 0.71).normalized(), O["ASSETS"], sun_elev_deg=12.0, sun_energy=4.6)
Z.golden(energy=4.7, ambient=0.62)
Z.finish(D, O)
