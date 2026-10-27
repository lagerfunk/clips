"""Per-vehicle motion for Drive Like a Local: wheel spin from distance travelled, steering from yaw rate and
wheelbase, brake lights from deceleration, indicators at 1.5 Hz, low beams and tail lights at night, trailers that
follow their hitch. Works for hero cars (jx.hero) and for any number of traffic vehicles sharing one collection per
model.

    import motion
    rig = motion.rig(obj)                    # collection instance (Object), vehicle collection, or jx.hero dict
    motion.bake(rig, track, night=False)     # track: one dict per frame, from frame 1
    track[i] = {"x", "y", "z", "yaw" (radians, 0 = +x), "v" (m/s), "ind": None | "L" | "R" | "H"}
    optional per frame: "pitch", "roll" (radians), "beacon" (True: blue lights flash, police and rescue models)

Why the split: a collection instance cannot spin its own wheels or light its own lamps, because everything inside
the collection is shared by every vehicle of that model. So rig() splits each model once (cached per collection):
    <model>__body       everything except the wheels (the vehicle instance now shows this one)
    <model>__trailer    and __dolly: articulated units of lorries (objects tagged dl_part in vehicles.py)
    <model>__w<k>       one collection per distinct wheel (tyre and rim, centred on the hub)
    <model>__lamps<p>   amber indicator lenses of unit p (positions from vehicles.py dl_lamps)
and gives every vehicle its own wheel, unit and lamp instances, parented to it. Lamp materials (vehicles.lamp) read
per-instance custom properties through an Attribute node of type Instancer: "brake", "tail", "head" on the vehicle
and unit instances (car_tail, car_head), "ind_l", "ind_r" on the lamp instances (dl_ind_L, dl_ind_R), "beacon_a",
"beacon_b" (police domes). One material serves every vehicle; an un-rigged vehicle reads 0 and looks as before.
"""
import json
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

FPS = 30
BRAKE_DECEL = -0.8          # m/s2: brake lights on below this
STAND_V = 0.05              # m/s: standing (brake held)
BLINK_PERIOD = 2.0 / 3.0    # 1.5 Hz: on 0.33 s, off 0.33 s
STEER_MAX = math.radians(35.0)
STEER_SMOOTH = 7            # frames, centred moving average of the steering angle
IND_ON = 12.0               # emission of a lit indicator (as jx.hero had it)
HEAD_W = 220.0              # W per low-beam spot at night
HEAD_SPOT = math.radians(64.0)
BEACON_FRAMES = 6           # blue lights: phase A and B alternate every 0.2 s
ARTIC_MAX = math.radians(80.0)
PARTS = ("main", "trailer", "dolly")

_models = {}
_rigs = {}


# ------------------------------------------------------------------ small helpers
def _alive(idb):
    try:
        idb.name
        return True
    except (ReferenceError, AttributeError):
        return False


def _fcurves(idb):
    ad = idb.animation_data
    act = ad.action
    try:
        return list(act.fcurves)
    except AttributeError:
        return list(act.layers[0].strips[0].channelbag(ad.action_slot).fcurves)


def _fcurve(idb, path, index=0):
    if idb.animation_data and idb.animation_data.action:
        for fc in _fcurves(idb):
            if fc.data_path == path and fc.array_index == index:
                return fc
    if path.startswith('["'):
        idb.keyframe_insert(path, frame=1)
    else:
        idb.keyframe_insert(path, index=index, frame=1)
    for fc in _fcurves(idb):
        if fc.data_path == path and fc.array_index == index:
            return fc
    raise RuntimeError(f"no fcurve {path}[{index}] on {idb.name}")


def keys(idb, path, index, frames, values, interp=1, compress=False):
    """Replace the keys of one channel with (frame, value) pairs, fast (foreach_set). interp 0 constant, 1 linear.
    compress: keep only the frames where the value changes (for constant channels such as lamps)."""
    if compress:
        fr, vs = [frames[0]], [values[0]]
        for f, v in zip(frames[1:], values[1:]):
            if v != vs[-1]:
                fr.append(f)
                vs.append(v)
        frames, values = fr, vs
    if path.startswith('["'):
        idb[path[2:-2]] = float(values[0])
    fc = _fcurve(idb, path, index)
    kp = fc.keyframe_points
    kp.clear()
    kp.add(len(frames))
    co = []
    for f, v in zip(frames, values):
        co += [float(f), float(v)]
    kp.foreach_set("co", co)
    kp.foreach_set("interpolation", [interp] * len(frames))
    fc.update()
    return fc


def _world(o):
    """Matrix from the parent chain (valid for objects in excluded library collections, which the depsgraph does
    not evaluate)."""
    m = Matrix.Identity(4)
    chain = []
    while o is not None:
        chain.append(o)
        o = o.parent
    for q in reversed(chain):
        m = m @ q.matrix_parent_inverse @ q.matrix_basis
    return m


def _mat_names(o):
    if o.type != "MESH":
        return ()
    return tuple(m.name for m in o.data.materials if m)


def _is_tyre(o):
    return o.type == "MESH" and (o.get("dl_tyre") or any(n.startswith("car_tyre") for n in _mat_names(o)))


def _is_rim(o):
    return o.type == "MESH" and (o.get("dl_rim") or any(n.startswith("car_rim") for n in _mat_names(o)))


def _bbox(o, m):
    pts = [m @ Vector(c) for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def _hidden_lib(src):
    """Collection for the derived model collections: next to the source (inside "lib" when the source is there) and
    excluded from every view layer, so only instances of it render."""
    parent = next((c for c in bpy.data.collections if src.name in c.children), None)
    lib = bpy.data.collections.get("motion_lib")
    if lib is None:
        lib = bpy.data.collections.new("motion_lib")
        (parent or bpy.context.scene.collection).children.link(lib)
    for sc in bpy.data.scenes:
        for vl in sc.view_layers:
            stack = [vl.layer_collection]
            while stack:
                lc = stack.pop()
                if lc.collection == lib:
                    lc.exclude = True
                stack.extend(lc.children)
    return lib


def _box_mesh(name, size):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def _part(o):
    p = o.get("dl_part", "main")
    return p if p in PARTS else "main"


# ------------------------------------------------------------------ model split (once per collection)
def model(src):
    """Split a vehicle collection into unit, wheel and lamp collections (cached). Returns a dict with the wheels
    (hub centre c, radius r, unit, steer), the main wheelbase wb, the units and the body extents in model
    coordinates (front +y, ground z = 0)."""
    md = _models.get(src.name)
    if md and _alive(md["body"]) and md["src"] == src:
        return md
    off = Vector(src.instance_offset)
    objs = list(src.all_objects)
    tyres = [o for o in objs if _is_tyre(o)]
    rims = [o for o in objs if _is_rim(o) and o not in tyres]
    lib = _hidden_lib(src)
    units = [dict(part="main", parent=None, hitch=0.0, axle=0.0)]
    if "dl_units" in src:
        for u in json.loads(src["dl_units"]):
            units.append(dict(part=u["part"], parent=u.get("parent", "main"), hitch=float(u["hitch"]),
                              axle=float(u["axle"])))
    pivot = {u["part"]: u["hitch"] for u in units}
    colls = {}
    for u in units:
        name = src.name + ("__body" if u["part"] == "main" else "__" + u["part"])
        cc = bpy.data.collections.new(name)
        lib.children.link(cc)
        cc.instance_offset = off + Vector((0.0, pivot[u["part"]], 0.0))
        cc["dl_src"] = src.name
        colls[u["part"]] = cc
    lens = {int(o["dl_lamp"]): o for o in objs if "dl_lamp" in o}     # moulded indicator lenses (vehicles.py)
    for o in objs:
        if o not in tyres and o not in rims and "dl_lamp" not in o:
            colls.get(_part(o), colls["main"]).objects.link(o)
    # wheels: hub centre, radius, width; rims go to the nearest tyre on the same side
    wheels = []
    for t in tyres:
        mw = Matrix.Translation(-off) @ _world(t)
        lo, hi = _bbox(t, mw)
        c = (lo + hi) / 2
        wheels.append(dict(tyre=t, mw=mw, c=c, r=(hi.z - lo.z) / 2, w=hi.x - lo.x, rims=[],
                           part=_part(t) if _part(t) in colls else "main"))
    for rm in rims:
        mw = Matrix.Translation(-off) @ _world(rm)
        lo, hi = _bbox(rm, mw)
        c = (lo + hi) / 2
        best = min(wheels, key=lambda w: (Vector((0, c.y, c.z)) - Vector((0, w["c"].y, w["c"].z))).length
                   + (0 if c.x * w["c"].x > 0 else 9), default=None)
        if best and abs(c.y - best["c"].y) < 0.3 and abs(c.z - best["c"].z) < 0.3 and c.x * best["c"].x > 0:
            best["rims"].append((rm, mw))
    protos = {}
    out = []
    for w in wheels:
        # wheels with the same side, size and rim share one collection (rims are built from the same parameters)
        sig = (w["c"].x > 0, round(w["r"], 3), round(w["w"], 3),
               tuple(sorted((round(((lambda b: (b[0] + b[1]) / 2)(_bbox(r_, m_))).x - w["c"].x, 3),
                             len(r_.data.vertices), tuple(m.name for m in r_.data.materials if m))
                            for r_, m_ in w["rims"])))
        if sig not in protos:
            wc = bpy.data.collections.new(f"{src.name}__w{len(protos)}")
            lib.children.link(wc)
            to_hub = Matrix.Translation(-w["c"])
            for ob, mw in [(w["tyre"], w["mw"])] + w["rims"]:
                cp = ob.copy()
                cp.parent = None
                cp.matrix_parent_inverse = Matrix.Identity(4)
                cp.matrix_basis = to_hub @ mw
                wc.objects.link(cp)
            protos[sig] = wc
        out.append(dict(coll=protos[sig], c=w["c"].copy(), r=w["r"], part=w["part"]))
    # axle groups of the main unit (front first): a gap over 1.8 m starts a new group; the front group steers
    ys = sorted({round(w["c"].y, 2) for w in out if w["part"] == "main"}, reverse=True)
    groups = []
    for y in ys:
        if groups and groups[-1][-1] - y < 1.8:
            groups[-1].append(y)
        else:
            groups.append([y])
    front = groups[0] if len(groups) > 1 else []
    for w in out:
        w["steer"] = w["part"] == "main" and round(w["c"].y, 2) in front
    wb = (sum(front) / len(front) - sum(groups[1]) / len(groups[1])) if len(groups) > 1 else 2.6
    rear_axle = sum(groups[1]) / len(groups[1]) if len(groups) > 1 else 0.0
    # body extents (all units, without wheels) and headlights
    lo = Vector((1e9, 1e9, 1e9))
    hi = -lo
    for o in objs:
        # vehicle length and width are measured without the mirrors (as in type approval)
        # (and without side marker lamps, which type approval also leaves out)
        if (o.type in ("MESH", "CURVE", "FONT") and o not in tyres and o not in rims
                and not o.name.startswith(("mirror", "marker"))):
            a, b = _bbox(o, Matrix.Translation(-off) @ _world(o))
            lo = Vector(map(min, lo, a))
            hi = Vector(map(max, hi, b))
    for w in out:
        lo.y = min(lo.y, w["c"].y - w["r"])
        hi.y = max(hi.y, w["c"].y + w["r"])
    heads = [list(Matrix.Translation(-off) @ _world(o).translation) for o in objs if o.name.startswith("headlight")]
    if "dl_heads" in src:
        h = list(src["dl_heads"])
        heads = [h[i:i + 3] for i in range(0, len(h), 3)]
    lamps = _lamps(src, lib, lo, hi, heads, pivot, lens, off)
    md = dict(src=src, body=colls["main"], colls=colls, units=units, pivot=pivot, wheels=out, wb=wb,
              rear_axle=rear_axle, lo=lo, hi=hi, heads=heads, lamps=lamps, length=hi.y - lo.y, width=hi.x - lo.x,
              height=hi.z)
    _models[src.name] = md
    return md


def _lamps(src, lib, lo, hi, heads, pivot, lens=None, off=Vector()):
    """Indicator lenses per unit from dl_lamps ([x, y, z, size_x, size_y, size_z, side, unit] records; side -1 is
    the left, -x when the vehicle faces +y; unit 0 main, 1 trailer, 2 dolly), else bounding-box corners. A record
    with a moulded lens in the model (object tagged dl_lamp = record index) uses that lens, else a small box."""
    if "dl_lamps" in src:
        v = list(src["dl_lamps"])
        spec = [v[i:i + 8] for i in range(0, len(v) - 7, 8)]
    else:
        zf = sum(h[2] for h in heads) / len(heads) if heads else lo.z + 0.4 * (hi.z - lo.z)
        spec = []
        for s in (-1, 1):
            x = s * (hi.x - 0.06)
            spec += [[x, hi.y - 0.02, zf, 0.1, 0.06, 0.07, s, 0], [x, lo.y + 0.02, zf + 0.1, 0.1, 0.06, 0.07, s, 0]]
    import vehicles as V
    ml, mr = V.lamp_mats()
    out = {}
    for k, (x, y, z, sx, sy, sz, side, unit) in enumerate(spec):
        part = PARTS[int(unit)] if int(unit) < len(PARTS) and PARTS[int(unit)] in pivot else "main"
        if part not in out:
            lc = bpy.data.collections.new(f"{src.name}__lamps_{part}")
            lib.children.link(lc)
            out[part] = lc
        pr = (lens or {}).get(k)
        if pr is not None and pr.type == "MESH":
            me = pr.data.copy()
            me.name = f"{src.name}_ind{k}"
            me.transform(Matrix.Translation(-Vector((x, y, z))) @ Matrix.Translation(-off) @ _world(pr))
            me.materials.clear()
        else:
            me = _box_mesh(f"{src.name}_ind{k}", (sx, sy, sz))
        me.materials.append(ml if side < 0 else mr)
        o = bpy.data.objects.new(f"{src.name}_ind{k}", me)
        o.location = (x, y - pivot[part], z)
        out[part].objects.link(o)
    return out


# ------------------------------------------------------------------ rig (once per vehicle)
class Rig:
    def __init__(self, obj, md):
        self.obj, self.md = obj, md
        self.wheels, self.lamps, self.lights, self.units = [], {}, [], {"main": obj}
        self.track, self.night, self.frame0 = None, False, 1
        self.wb = md["wb"] if md else 2.6
        self.states = {}


def rig(obj, c=None):
    """Rig a vehicle for motion.bake. obj: a collection-instance Object, a vehicle Collection (an instance is made in
    c, the scene's "traffic" collection or the scene) or a jx.hero dict. A plain object gets transform keys only.
    Rigging alone does not move anything: an un-baked rigged vehicle looks exactly like its collection."""
    hero = None
    if isinstance(obj, dict):
        hero = obj
        if hero.get("rig"):
            return hero["rig"]
        obj = hero["obj"]
    if isinstance(obj, bpy.types.Collection):
        e = bpy.data.objects.new(obj.name + "_car", None)
        e.instance_type = "COLLECTION"
        e.instance_collection = obj
        (c or bpy.data.collections.get("traffic") or bpy.context.scene.collection).objects.link(e)
        obj = e
    r = _rigs.get(obj.name)
    if r is not None and _alive(r.obj) and r.obj == obj:
        return r
    md = None
    if obj.instance_type == "COLLECTION" and obj.instance_collection is not None:
        src = obj.instance_collection
        if "dl_src" in src:
            src = bpy.data.collections[src["dl_src"]]
        md = model(src)
        obj.instance_collection = md["body"]
    r = Rig(obj, md)
    users = list(obj.users_collection) or [bpy.context.scene.collection]

    def child(name, coll, parent, loc):
        e = bpy.data.objects.new(name, None)
        e.instance_type = "COLLECTION"
        e.instance_collection = coll
        for u in users:
            u.objects.link(e)
        e.parent = parent
        e.location = loc
        e.rotation_mode = "XYZ"
        return e

    if md:
        for u in md["units"][1:]:
            par = r.units[u["parent"]]
            loc = (0.0, md["pivot"][u["part"]] - md["pivot"][u["parent"]], 0.0)
            r.units[u["part"]] = child(f"{obj.name}_{u['part']}", md["colls"][u["part"]], par, loc)
        for k, w in enumerate(md["wheels"]):
            par = r.units[w["part"]]
            e = child(f"{obj.name}_wheel{k}", w["coll"], par, w["c"] - Vector((0, md["pivot"][w["part"]], 0)))
            r.wheels.append(dict(obj=e, r=w["r"], steer=w["steer"], c=w["c"], part=w["part"]))
        for part, lc in md["lamps"].items():
            r.lamps[part] = child(f"{obj.name}_lamps_{part}", lc, r.units[part], (0, 0, 0))
    for o in list(r.units.values()) + list(r.lamps.values()):
        for p in ("brake", "tail", "head", "ind_l", "ind_r", "beacon_a", "beacon_b"):
            o[p] = 0.0
    _rigs[obj.name] = r
    if hero is not None:
        hero["rig"] = r
    return r


# ------------------------------------------------------------------ kinematics (pure python, used by the tests)
def _unwrap(a):
    out = [a[0]]
    for x in a[1:]:
        p = out[-1]
        while x - p > math.pi:
            x -= 2 * math.pi
        while x - p < -math.pi:
            x += 2 * math.pi
        out.append(x)
    return out


def _smooth(vals, win):
    if win <= 1:
        return list(vals)
    h = win // 2
    n = len(vals)
    return [sum(vals[max(0, i - h):min(n, i + h + 1)]) / (min(n, i + h + 1) - max(0, i - h)) for i in range(n)]


def kinematic(track, fps=FPS, wb=2.6):
    """Per-frame derived values: signed distance travelled ds (a teleport counts as v*dt), steering angle (radians,
    + is left), acceleration (m/s2), jump flags."""
    n = len(track)
    yaw = _unwrap([float(t["yaw"]) for t in track])
    v = [float(t.get("v", 0.0)) for t in track]
    ds = [0.0] * n
    jump = [False] * n
    for i in range(1, n):
        a, b = track[i - 1], track[i]
        d = Vector((b["x"] - a["x"], b["y"] - a["y"], b.get("z", 0.0) - a.get("z", 0.0)))
        lim = max(1.0, 2.5 * max(v[i], v[i - 1]) / fps + 0.5)
        if d.length > lim:
            jump[i] = True
            ds[i] = (v[i] + v[i - 1]) / 2 / fps
            continue
        hd = Vector((math.cos(yaw[i]), math.sin(yaw[i]), 0.0))
        ds[i] = d.length if d.dot(hd) >= 0 else -d.length
    steer = [0.0] * n
    for i in range(1, n):
        if jump[i] or abs(ds[i]) < 1e-3:
            steer[i] = steer[i - 1]
            continue
        k = (yaw[i] - yaw[i - 1]) / ds[i]
        steer[i] = max(-STEER_MAX, min(STEER_MAX, math.atan(wb * k)))
    if n > 1:
        steer[0] = steer[1]
    steer = [max(-STEER_MAX, min(STEER_MAX, s)) for s in _smooth(steer, STEER_SMOOTH)]
    acc = [0.0] * n
    for i in range(1, n):
        acc[i] = 0.0 if jump[i] else (v[i] - v[i - 1]) * fps
    if n > 1:
        acc[0] = acc[1]
    acc = _smooth(acc, 3)
    return dict(yaw=yaw, v=v, ds=ds, steer=steer, acc=acc, jump=jump)


def follow(hitch, parent_yaw, d, jump):
    """A trailer (or dolly) hitched at the points `hitch` (per frame, world 2D) with its axle d metres behind the
    hitch: the axle is dragged towards the hitch (tractrix). Returns the unit's world yaw and the signed distance its
    axle travels, per frame. Starts (and restarts after a jump) in line with the parent."""
    n = len(hitch)
    yaw, ds = [parent_yaw[0]] * n, [0.0] * n
    q = hitch[0] - d * Vector((math.cos(yaw[0]), math.sin(yaw[0])))
    for i in range(1, n):
        if jump[i]:
            yaw[i] = parent_yaw[i]
            q = hitch[i] - d * Vector((math.cos(yaw[i]), math.sin(yaw[i])))
            continue
        dv = hitch[i] - q
        if dv.length < 1e-6:
            yaw[i] = yaw[i - 1]
        else:
            y = math.atan2(dv.y, dv.x)
            while y - yaw[i - 1] > math.pi:
                y -= 2 * math.pi
            while y - yaw[i - 1] < -math.pi:
                y += 2 * math.pi
            rel = max(-ARTIC_MAX, min(ARTIC_MAX, y - parent_yaw[i]))
            yaw[i] = parent_yaw[i] + rel
        q2 = hitch[i] - d * Vector((math.cos(yaw[i]), math.sin(yaw[i])))
        step = q2 - q
        hd = Vector((math.cos(yaw[i]), math.sin(yaw[i])))
        ds[i] = step.length if step.dot(hd) >= 0 else -step.length
        q = q2
    return yaw, ds


def brake_states(track, fps=FPS):
    """Brake lamps per frame: deceleration below -0.8 m/s2, or standing (a driver holds the brake at a stop, which
    covers the standstill after braking). Off-gaps under 0.2 s are filled so the lamps never flicker."""
    kin = kinematic(track, fps)
    on = [(a < BRAKE_DECEL) or (v < STAND_V) for a, v in zip(kin["acc"], kin["v"])]
    gap = int(0.2 * fps)
    i, n = 0, len(on)
    while i < n:
        if not on[i]:
            j = i
            while j < n and not on[j]:
                j += 1
            if 0 < i and j < n and j - i < gap:
                for k in range(i, j):
                    on[k] = True
            i = j
        else:
            i += 1
    return on


def blink_states(inds, fps=FPS):
    """(left, right) lamps per frame from the "ind" field: blinking at 1.5 Hz from the start of each run (lit first),
    "H" (hazards) both sides."""
    n = len(inds)
    left, right = [False] * n, [False] * n
    start = 0
    for i in range(n):
        if i == 0 or inds[i] != inds[i - 1]:
            start = i
        s = inds[i]
        if not s:
            continue
        lit = ((i - start) / fps) % BLINK_PERIOD < BLINK_PERIOD / 2 - 1e-6
        if s in ("L", "H"):
            left[i] = lit
        if s in ("R", "H"):
            right[i] = lit
    return left, right


# ------------------------------------------------------------------ bake
def bake(r, track, night=False, frame0=1):
    """Write transform, wheel, steering, trailer and lamp keys for frames frame0 .. frame0 + len(track) - 1."""
    if not isinstance(r, Rig):
        r = rig(r)
    n = len(track)
    frames = list(range(frame0, frame0 + n))
    kin = kinematic(track, FPS, r.wb)
    o = r.obj
    o.rotation_mode = "XYZ"
    for i, key in enumerate(("x", "y", "z")):
        keys(o, "location", i, frames, [float(t.get(key, 0.0)) for t in track])
    keys(o, "rotation_euler", 0, frames, [float(t.get("pitch", 0.0)) for t in track])
    keys(o, "rotation_euler", 1, frames, [float(t.get("roll", 0.0)) for t in track])
    keys(o, "rotation_euler", 2, frames, [y - math.pi / 2 for y in kin["yaw"]])
    # articulated units: world pose of each unit's pivot, its yaw from the tractrix, local yaw relative to its parent
    pose = {"main": ([Vector((t["x"], t["y"])) for t in track], kin["yaw"], 0.0)}
    unit_ds = {"main": kin["ds"]}
    r.unit_yaw = {"main": kin["yaw"]}
    if r.md:
        for u in r.md["units"][1:]:
            pp, pyaw, ppiv = pose[u["parent"]]
            off = u["hitch"] - ppiv
            hitch = [p + off * Vector((math.cos(a), math.sin(a))) for p, a in zip(pp, pyaw)]
            yaw, ds = follow(hitch, pyaw, u["hitch"] - u["axle"], kin["jump"])
            pose[u["part"]] = (hitch, yaw, u["hitch"])
            unit_ds[u["part"]] = ds
            r.unit_yaw[u["part"]] = yaw
            keys(r.units[u["part"]], "rotation_euler", 2, frames, [a - b for a, b in zip(yaw, pyaw)])
    for w in r.wheels:
        spin, a = [], 0.0
        for d in unit_ds.get(w["part"], kin["ds"]):
            a -= d / w["r"]           # rolling forward (+y) is a negative turn about +x
            spin.append(a)
        w["obj"].rotation_mode = "XYZ"
        keys(w["obj"], "rotation_euler", 0, frames, spin)
        if w["steer"]:
            keys(w["obj"], "rotation_euler", 2, frames, kin["steer"])
    r.track, r.night, r.frame0 = [dict(t) for t in track], night, frame0
    r.kin = kin
    relight(r)
    return r


def relight(r):
    """(Re)write the lamp keys from r.track (after changing "ind" or "beacon" entries, e.g. jx.blink)."""
    track, n = r.track, len(r.track)
    frames = list(range(r.frame0, r.frame0 + n))
    brake = brake_states(track)
    left, right = blink_states([t.get("ind") for t in track])
    night = 1.0 if r.night else 0.0
    vals = dict(brake=[1.0 if b else 0.0 for b in brake], tail=[night] * n, head=[night] * n)
    for o in r.units.values():
        for p, vs in vals.items():
            keys(o, f'["{p}"]', 0, frames, vs, interp=0, compress=True)
    ind = dict(ind_l=[IND_ON if x else 0.0 for x in left], ind_r=[IND_ON if x else 0.0 for x in right])
    for o in r.lamps.values():
        for p, vs in ind.items():
            keys(o, f'["{p}"]', 0, frames, vs, interp=0, compress=True)
    if any(t.get("beacon") for t in track):
        ba, bb = [], []
        for i, t in enumerate(track):
            ph = ((frames[i] - 1) // BEACON_FRAMES) % 2
            on = bool(t.get("beacon"))
            ba.append(1.0 if on and ph == 0 else 0.0)
            bb.append(1.0 if on and ph == 1 else 0.0)
        keys(r.obj, '["beacon_a"]', 0, frames, ba, interp=0, compress=True)
        keys(r.obj, '["beacon_b"]', 0, frames, bb, interp=0, compress=True)
    r.states = dict(brake=brake, brake_l=list(brake), brake_r=list(brake), left=left, right=right)
    _night_lights(r)


def _night_lights(r):
    for lo in r.lights:
        if _alive(lo):
            bpy.data.objects.remove(lo)
    r.lights = []
    if not r.night or not r.md:
        return
    users = list(r.obj.users_collection) or [bpy.context.scene.collection]
    for k, h in enumerate(r.md["heads"][:2]):
        ld = bpy.data.lights.new(f"{r.obj.name}_beam{k}", "SPOT")
        ld.energy = HEAD_W
        ld.spot_size = HEAD_SPOT
        ld.spot_blend = 0.45
        ld.color = (1.0, 0.94, 0.84)
        ld.shadow_soft_size = 0.06
        lo = bpy.data.objects.new(ld.name, ld)
        for u in users:
            u.objects.link(lo)
        lo.parent = r.obj
        lo.location = (h[0], h[1] + 0.05, h[2])
        lo.rotation_euler = (math.radians(84.0), 0.0, 0.0)    # spot axis -Z turned to +y, 6 degrees down
        r.lights.append(lo)


def track_from(locs, yaws, speeds, inds=None):
    """Build a track from parallel lists (locs as (x, y[, z]), yaw in radians with 0 = +x, v in m/s)."""
    inds = inds or [None] * len(locs)
    return [dict(x=p[0], y=p[1], z=p[2] if len(p) > 2 else 0.0, yaw=y, v=v, ind=i)
            for p, y, v, i in zip(locs, yaws, speeds, inds)]


def park(obj, x, y, yaw, z=0.0):
    """Rig and place a standing vehicle (no keys): wheels and lamps work, nothing moves."""
    r = rig(obj)
    r.obj.location = (x, y, z)
    r.obj.rotation_euler = (0.0, 0.0, yaw - math.pi / 2)
    return r
