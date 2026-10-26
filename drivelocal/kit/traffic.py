"""Play a SUMO traffic track (traffic/<name>.json.gz, CONTRACTS.md format) into Blender through kit/motion.py.

    import traffic as TR
    data = TR.load("traffic/interchange_day.json.gz")
    models = TR.models(lib)                         # stage.fleet: 10 cars, 1 van, 4 lorries (build before the world)
    rigs = TR.play(data, models, traffic_coll, frames=(880, 920), keep=TR.near(cam_xy, 900.0))

Track rows: [f, x, y, yaw, v, ind] (vehicle centre on the ground, yaw 0 = +x, v in m/s, ind None | "L" | "R" | "H");
an optional per-vehicle "z" list holds one height per row (ramps and the crossing road). Each vehicle becomes an
instance of its fleet model (the "model" key; else picked by kind), rigged by motion.rig and baked by motion.bake:
wheels spin, front wheels steer, brake lights follow the deceleration, the indicator blinks on every lane change.
Outside its rows a vehicle is parked 1 km below the ground (constant keys), so vehicles enter and leave cleanly.
If kit/motion.py is missing (older checkout) it falls back to stage.bake_motion (transform only).
The plate in the track is informational: instances share their model's plate (a fictional code, vehicles.py)."""
import gzip
import json
import math
import os

import bpy

try:
    import motion
except ImportError:          # motion.py not merged yet: transform keys only
    motion = None
import stage

HIDE_Z = -1000.0


def load(path):
    if not os.path.isabs(path) and not os.path.exists(path):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def models(lib):
    cars, vans, trucks = stage.fleet(lib)
    return {**cars, **vans, **trucks}


def near(xy, radius):
    """keep-filter: vehicles that come within `radius` metres of the point xy during the played frames."""
    x0, y0 = xy
    r2 = radius * radius
    return lambda x, y: (x - x0) ** 2 + (y - y0) ** 2 < r2


def in_view(cam, margin=0.15, max_dist=1500.0):
    """keep-filter: vehicles inside the camera frustum (plus a margin), up to max_dist (uses the camera now)."""
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector
    sc = bpy.context.scene

    def f(x, y):
        p = Vector((x, y, 1.0))
        if (p - cam.matrix_world.translation).length > max_dist:
            return False
        q = world_to_camera_view(sc, cam, p)
        return q.z > 0 and -margin <= q.x <= 1 + margin and -margin <= q.y <= 1 + margin
    return f


def _pitch(zs, xs, ys, i):
    a, b = max(0, i - 3), min(len(zs) - 1, i + 3)
    d = math.hypot(xs[b] - xs[a], ys[b] - ys[a])
    return math.atan2(zs[b] - zs[a], d) if d > 0.5 else 0.0


def play(data, fleet, coll, frames=None, keep=None, night=False, max_vehicles=None, offset=0, z_fn=None):
    """Instance, rig and bake the vehicles of `data` into the collection `coll`.
    frames: (f0, f1) track frames to bake (default all); they land on scene frames f + offset.
    keep(x, y) -> bool: a vehicle is played if any of its rows in the window passes. Returns the rigs."""
    f0, f1 = frames or (1, data["frames"])
    by_kind = {}
    for name, c in fleet.items():
        kind = "truck" if name.startswith("t_") else ("van" if name.startswith("van") else "car")
        by_kind.setdefault(kind, []).append(name)
    out = []
    for k, v in enumerate(data["vehicles"]):
        rows = [r for r in v["track"] if f0 <= r[0] <= f1]
        if len(rows) < 2:
            continue
        if keep and not any(keep(r[1], r[2]) for r in rows):
            continue
        name = v.get("model") if v.get("model") in fleet else by_kind[v["kind"]][k % len(by_kind[v["kind"]])]
        zs_all = v.get("z")
        idx0 = v["track"].index(rows[0])
        zs = zs_all[idx0:idx0 + len(rows)] if zs_all else [z_fn(r[1], r[2]) if z_fn else 0.0 for r in rows]
        xs, ys = [r[1] for r in rows], [r[2] for r in rows]
        track = [dict(x=r[1], y=r[2], z=z, yaw=r[3], v=r[4], ind=r[5], pitch=_pitch(zs, xs, ys, i))
                 for i, (r, z) in enumerate(zip(rows, zs))]
        first, last = rows[0][0] + offset, rows[-1][0] + offset
        if motion:
            r = motion.rig(fleet[name], c=coll)
            r.obj.name = f"tr_{v['id']}"
            motion.bake(r, track, night=night, frame0=first)
            obj = r.obj
        else:
            obj = bpy.data.objects.new(f"tr_{v['id']}", None)
            obj.instance_type = "COLLECTION"
            obj.instance_collection = fleet[name]
            coll.objects.link(obj)
            stage.bake_motion(obj, list(range(first, last + 1)), [(t["x"], t["y"], t["z"]) for t in track],
                              [(t["pitch"], 0.0, t["yaw"] - math.pi / 2) for t in track])
            r = obj
        _hide_outside(obj, first, last, f0 + offset, f1 + offset)
        obj["track_id"] = v["id"]
        out.append(r)
        if max_vehicles and len(out) >= max_vehicles:
            break
    return out


def _hide_outside(obj, first, last, w0, w1):
    """Park the vehicle 1 km below ground before its first and after its last row. The jump sits between
    sub-frame keys (0.3 frames outside the track), so motion blur (shutter 0.5) never smears a car down to the
    hiding place: on the rendered frames next to the jump the car is either fully there or fully gone."""
    fc = None
    for c in stage.fcurves(obj):
        if c.data_path == "location" and c.array_index == 2:
            fc = c
    if fc is None:
        return
    pts = fc.keyframe_points
    z_first, z_last = fc.evaluate(first), fc.evaluate(last)
    add = []
    if first > w0:
        add += [(first - 1, HIDE_Z), (first - 0.3, z_first)]
    if last < w1:
        add += [(last + 0.3, z_last), (last + 1, HIDE_Z)]
    for f, z in add:
        k = pts.insert(f, z)
        k.interpolation = "CONSTANT"
    for k in pts:
        if abs(k.co.x - last) < 1e-6 and last < w1:
            k.interpolation = "CONSTANT"
    fc.update()


def stats(data):
    """Counts the exported data carries (computed by rnd/run_traffic.py)."""
    return data.get("stats", {})
