"""Shared stage for the junction episodes: a German residential X junction with houses, gardens, street furniture
and one of three rule set-ups.
variant: "plain"    no signs, no markings (rechts vor links, the usual Tempo 30 street)
         "priority" north-south is the priority road (Zeichen 306), east and west give way (205 + shark teeth)
         "signal"   traffic lights on all four approaches, stop lines, Zeichen 720 on the south approach
"""
import math
import random

import bpy
from mathutils import Vector

import flora
import stage
import town as TN
import vehicles as V
import world as W

HX, HY = 3.0, 3.0          # half carriageway widths (6.0 m streets)
R = 6.0
PL = TN.KERB_W + TN.FOOT   # property line offset from the kerb


def house_depth(sd):
    """Depth of TN.house(seed=sd) without building it (same random draws)."""
    r = random.Random(sd)
    r.uniform(9.0, 11.5)
    return r.uniform(8.5, 10.5)


def build(assets, variant="plain", seed=4, hx=HX, hy=HY, parked=True, extra_trees=True, heroes=()):
    """heroes: [(kind, colour, name, plate, metal)] built first (operators are slow once the town exists)."""
    import jx
    bpy.ops.wm.read_factory_settings(use_empty=True)
    W.setup(assets, None)
    lib = W.coll("lib")
    env = W.coll("env")
    traffic = W.coll("traffic")
    cars, vans, trucks = stage.fleet(lib)
    hero_cars = {h[2]: jx.hero(h[0], h[1], h[2], h[3], lib, traffic, metal=h[4]) for h in heroes}
    M = W.Mats()
    T = TN.TownMats(M)
    J = TN.Junction(T, env, hw_ns=hx, hw_ew=hy, R=R, L=240.0)
    rnd = random.Random(seed)
    groups = flora.library(lib)
    autumn = [flora.leaf_mat("leaf_autumn_a", (0.42, 0.2, 0.02), (0.62, 0.38, 0.05)),
              flora.leaf_mat("leaf_autumn_b", (0.35, 0.28, 0.03), (0.55, 0.45, 0.08))]
    trees = list(groups["decid"].children)
    # two autumn variants of the deciduous trees (it is October)
    for k, t in enumerate(trees[:2]):
        for o in t.objects:
            if o.name.startswith("crown"):
                o.data.materials[0] = autumn[k]
    conifers = list(groups["conif"].children)
    bushes = list(groups["bush"].children)

    houses = []
    seeds = iter(range(100 + seed * 50, 200 + seed * 50))

    def put_house(cx, cy, rz, sd):
        hc = TN.house(T, lib, f"house{sd}", sd)
        e = TN.place(hc, (cx, cy, TN.KERB_H), rz, env, name=f"h{sd}")
        g = hc.objects[f"house{sd}_root"]
        houses.append((e, g))
        return e, g

    def local_to_world(cx, cy, rz, lx, ly):
        c_, s_ = math.cos(rz), math.sin(rz)
        return Vector((cx + lx * c_ - ly * s_, cy + lx * s_ + ly * c_))

    def garden(cx, cy, rz, g, setback):
        w, d = g["w"], g["d"]
        gx, dx_ = g["garage_x"], g["door_x"]
        y_pl = -(d / 2 + setback)                       # local y of the property line
        x_lo, x_hi = -10.0, 10.0
        gaps = sorted([(dx_ - 0.75, dx_ + 0.75)] + ([(gx - 1.7, gx + 1.7)] if g["garage"] else []))
        segs, x = [], x_lo
        for a, b in gaps:
            if a > x:
                segs.append((x, a))
            x = max(x, b)
        if x < x_hi:
            segs.append((x, x_hi))
        kind = rnd.choice(("hedge", "hedge", "fence", "low"))
        for a, b in segs:
            if b - a < 0.4:
                continue
            pa = local_to_world(cx, cy, rz, a, y_pl + 0.45)
            pb = local_to_world(cx, cy, rz, b, y_pl + 0.45)
            if kind == "hedge":
                TN.hedge(T, env, pa, pb, h=rnd.uniform(0.9, 1.5))
            elif kind == "fence":
                TN.fence(T, env, pa, pb)
            else:
                TN.hedge(T, env, pa, pb, h=0.55, t=0.5)
        # front path and driveway
        for (a, b, m) in [(dx_ - 0.6, dx_ + 0.6, T.pavers)] + ([(gx - 1.5, gx + 1.5, T.drive)] if g["garage"] else []):
            q = [local_to_world(cx, cy, rz, a, y_pl), local_to_world(cx, cy, rz, b, y_pl),
                 local_to_world(cx, cy, rz, b, -d / 2), local_to_world(cx, cy, rz, a, -d / 2)]
            o = W.mesh_obj("path", [(p.x, p.y, TN.KERB_H + 0.01) for p in q], [(0, 1, 2, 3)], m, env)
            if o.data.polygons[0].normal.z < 0:
                o.data.flip_normals()
            TN.uv_world(o)
        # bins by the gate
        if rnd.random() < 0.7:
            for k, kind_ in enumerate(rnd.sample(["grey", "blue", "brown", "yellow"], rnd.randint(1, 3))):
                p = local_to_world(cx, cy, rz, dx_ + 1.2 + k * 0.7, y_pl + 1.1)
                TN.wheelie_bin(T, env, (p.x, p.y), kind_, rz)
        # garden trees and bushes (behind and beside the house)
        for k in range(rnd.randint(1, 3)):
            lx = rnd.choice((-1, 1)) * rnd.uniform(w / 2 + 2.5, w / 2 + 5)
            ly = rnd.uniform(-d / 2, d / 2 + 8)
            p = local_to_world(cx, cy, rz, lx, ly)
            if abs(p.x) < 17 and abs(p.y) < 17:     # keep tree shadows off the junction
                continue
            src = rnd.choice(trees if rnd.random() < 0.75 else conifers)
            W.instance(src, (p.x, p.y, TN.KERB_H), rz=rnd.uniform(0, 6.3), s=rnd.uniform(0.8, 1.15), c=env)
        for k in range(rnd.randint(1, 3)):
            lx = rnd.uniform(-w / 2, w / 2)
            ly = rnd.uniform(y_pl + 1.5, -d / 2 - 1.2)
            if abs(lx - dx_) < 1.2 or (g["garage"] and abs(lx - gx) < 2):
                continue
            p = local_to_world(cx, cy, rz, lx, ly)
            W.instance(rnd.choice(bushes), (p.x, p.y, TN.KERB_H - 0.1), rz=rnd.uniform(0, 6.3),
                       s=rnd.uniform(0.35, 0.55), c=env)

    for sx in (-1, 1):
        for sy in (-1, 1):
            # houses facing the north-south street
            for k in range(6):
                sd = next(seeds)
                setback = rnd.uniform(4.5, 6.5)
                d = house_depth(sd)
                cx = sx * (hx + PL + setback + d / 2)
                cy = sy * (hy + 16.0 + 21.0 * k)
                rz = -sx * math.pi / 2
                e, g = put_house(cx, cy, rz, sd)
                garden(cx, cy, rz, g, setback)
            # houses facing the east-west street
            for k in range(5):
                sd = next(seeds)
                setback = rnd.uniform(4.5, 6.5)
                d = house_depth(sd)
                cx = sx * (hx + 36.0 + 21.0 * k)
                cy = sy * (hy + PL + setback + d / 2)
                rz = 0.0 if sy > 0 else math.pi
                e, g = put_house(cx, cy, rz, sd)
                garden(cx, cy, rz, g, setback)

    # beyond the houses: farmland and tree belts out to the horizon (seen from the drone shots)
    big, inner = 2600.0, 240.0
    fm = W.fields_material(M)
    for sx_, sy_ in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        e_ = hx + 1.0
        q = [(sx_ * inner, sy_ * e_), (sx_ * big, sy_ * e_), (sx_ * big, sy_ * big), (sx_ * e_, sy_ * big),
             (sx_ * e_, sy_ * inner), (sx_ * inner, sy_ * inner)]
        o = W.mesh_obj("farmland", [(x, y, TN.KERB_H - 0.03) for x, y in q], [tuple(range(len(q)))], fm, env)
        if o.data.polygons[0].normal.z < 0:
            o.data.flip_normals()
    # roads go on into the fields
    w_ = hx + 1.0
    for (x0, y0, x1, y1) in ((-w_, inner - 1, w_, big), (-w_, -big, w_, -inner + 1), (inner - 1, -w_, big, w_),
                             (-big, -w_, -inner + 1, w_)):
        o = W.mesh_obj("country_road", [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0)], [(0, 1, 2, 3)],
                       T.asph, env, uvs=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    trng = random.Random(seed + 77)
    for k in range(260):
        r_ = trng.uniform(150, 900)
        a_ = trng.uniform(0, 2 * math.pi)
        x, y = r_ * math.cos(a_), r_ * math.sin(a_)
        if min(abs(x), abs(y)) < 12:
            continue
        W.instance(trng.choice(trees + conifers), (x, y, TN.KERB_H), rz=trng.uniform(0, 6.3), s=trng.uniform(1.0, 1.6),
                   c=env)
    # street lamps on the footway, 0.6 m from the kerb, arm over the road
    for y in (-58, -24, 22, 56):
        TN.street_lamp(T, env, (hx + TN.KERB_W + 0.6, y), rz=math.pi)
    for x in (-60, -26, 24, 58):
        TN.street_lamp(T, env, (x, hy + TN.KERB_W + 0.6), rz=-math.pi / 2)
    # drains at the kerbs, manholes in the street
    for sx in (-1, 1):
        for sy in (-1, 1):
            TN.gully(T, env, sx * (hx - 0.18), sy * (hy + R + 3), rz=math.pi / 2)
            TN.gully(T, env, sx * (hx + R + 3), sy * (hy - 0.18))
    for p in ((0.4, 14), (-0.5, -31), (18, -0.3), (-27, 0.5), (0.2, 52), (49, 0.3)):
        TN.manhole(T, env, *p)

    furniture = dict(signals={})
    if variant == "priority":
        S306 = TN.sign_306(T, lib)
        S205 = TN.sign_205(T, lib)
        off = TN.KERB_W + 0.6
        TN.place(S306, (hx + off, -(hy + R + 4), 0.0), TN.facing((0, 1)), env, "z306_s")
        TN.place(S306, (-(hx + off), hy + R + 4, 0.0), TN.facing((0, -1)), env, "z306_n")
        TN.place(S205, (hx + R + 1.5, hy + off, 0.0), TN.facing((-1, 0)), env, "z205_e")
        TN.place(S205, (-(hx + R + 1.5), -(hy + off), 0.0), TN.facing((1, 0)), env, "z205_w")
        for sxe in (1, -1):
            # approach from the east (driving west) uses the north half, from the west the south half
            TN.haifisch(T, env, (sxe * (hx + 0.6), sxe * hy / 2), (0, 1), (sxe, 0), hy - 0.5)
        # the priority road keeps a broken centre line through town (not in the junction)
        for sy in (-1, 1):
            y = hy + R
            while y < 90:
                TN.bar(T, env, -0.06, 0.06, sy * y, sy * (y + 3.0), name="centre")
                y += 9.0
    if variant == "signal":
        groups_ = {"NS": TN.SignalGroup("sg_ns"), "EW": TN.SignalGroup("sg_ew")}
        furniture["signals"] = groups_
        off = TN.KERB_W + 0.55
        stop_back = R + 1.0
        for name, (dx, dy) in (("S", (0, 1)), ("N", (0, -1)), ("W", (1, 0)), ("E", (-1, 0))):
            grp = groups_["NS" if dx == 0 else "EW"]
            lc = TN.traffic_light(T, lib, grp, name=f"ampel_{name}", gruenpfeil=(name == "S"))
            right = Vector((dy, -dx))          # right-hand side of the approach
            back = Vector((-dx, -dy))
            hw_lat, hw_long = (hx, hy) if dx == 0 else (hy, hx)
            pos = right * (hw_lat + off) + back * (hw_long + stop_back - 0.6)
            TN.place(lc, (pos.x, pos.y, TN.KERB_H), TN.facing((dx, dy)), env, f"ampel_{name}")
            # stop line, 0.50 m, across the approach lane (centre line to kerb)
            a = back * (hw_long + stop_back) + right * 0.15
            b = back * (hw_long + stop_back) + right * (hw_lat - 0.3)
            fwd = Vector((dx, dy))
            q = [a - fwd * 0.25, b - fwd * 0.25, b + fwd * 0.25, a + fwd * 0.25]
            o = W.mesh_obj("stopline", [(p.x, p.y, 0.008) for p in q], [(0, 1, 2, 3)], T.paint, env,
                           uvs=[(0, 0)] * 4)
            if o.data.polygons[0].normal.z < 0:
                o.data.flip_normals()
            # short solid centre line before the stop line (Sperrlinie, 0.12 m), 20 m
            for k in range(1):
                c0 = back * (hw_long + stop_back)
                c1 = back * (hw_long + stop_back + 20.0)
                q = [c0 + right * 0.06, c1 + right * 0.06, c1 - right * 0.06, c0 - right * 0.06]
                o = W.mesh_obj("sperrlinie", [(p.x, p.y, 0.008) for p in q], [(0, 1, 2, 3)], T.paint, env,
                               uvs=[(0, 0)] * 4)
                if o.data.polygons[0].normal.z < 0:
                    o.data.flip_normals()
    fleet_all = {**cars, **vans}
    parked_objs = []
    if parked:
        spots = [((hx - 1.05, 34.0), (0, 1)), ((hx - 1.05, 40.5), (0, 1)), ((-(hx - 1.05), -38.0), (0, -1)),
                 ((-(hx - 1.05), 58.0), (0, -1)), ((44.0, -(hy - 1.05)), (1, 0)), ((-41.0, hy - 1.05), (-1, 0)),
                 ((-47.5, hy - 1.05), (-1, 0)), ((hx - 1.05, -52.0), (0, 1))]
        keys = list(fleet_all)
        for (x, y), (dx, dy) in spots:
            k = rnd.choice(keys)
            e = bpy.data.objects.new("parked_" + k, None)
            e.instance_type = "COLLECTION"
            e.instance_collection = fleet_all[k]
            e.location = (x, y, 0)
            e.rotation_euler = (0, 0, math.atan2(dy, dx) - math.pi / 2)
            env.objects.link(e)
            parked_objs.append(e)
    return dict(T=T, M=M, J=J, lib=lib, env=env, traffic=traffic, cars=cars, vans=vans, fleet=fleet_all,
                furniture=furniture, groups=groups, houses=houses, parked=parked_objs, heroes=hero_cars)


def light(sun_az_deg=235.0, sun_elev_deg=50.0, assets="assets"):
    """Sun from the south-west by default (az measured from +x, counter-clockwise)."""
    a = math.radians(sun_az_deg)
    to_sun = Vector((math.cos(a), math.sin(a), 0))
    stage.sky(None, -to_sun, assets, sun_elev_deg=sun_elev_deg, sun_energy=4.0)
