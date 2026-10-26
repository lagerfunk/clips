"""Parking kit (Drive Like a Local, batch 2): marked parallel bays on a town street, the parking signs, parked cars
facing the right way (and one facing the wrong way for the parking-direction episode), the blue parking disc
(Parkscheibe, StVO Bild 318) as a close-up prop with a settable dial, and parallel-parking manoeuvres as jx.Paths.

Numbers (sources in reports/townplus.md):
- bay width 2.00 m (Regelbreite Laengsparken, EAR 23 / RASt 06 as quoted by the Bremen E-LIS guidance), bay length
  5.70 m between bays and 5.20 m for an end bay (EAR values, UNVERIFIED: the EAR itself was not opened);
  bay lines 0.12 m (Schmalstrich outside the Autobahn, road_spec.md).
- parking needs a 3.00 m lane left over (StVO Anlage 2); no parking within 5 m of a junction (section 12 (3) StVO)
  or before a zebra.
- signs (kit/signs.py, Commons files unaltered): Zeichen 314 with Zusatzzeichen 1040-32 (parking disc, 2 hours) at
  the start of a bay row, Zeichen 283 (no stopping) or 286 (no parking) where useful.
- Parkscheibe: 110 x 150 mm, blue with white print, "ANKUNFTSZEIT" above a window (a ring sector, radii 20 and
  45 mm, 50 degrees either side of straight down) under a fixed white pointer; the dial turns about a pivot 50 mm
  below the top edge, hours 1 to 12 large and 13 to 24 small, a tick every half hour; Zeichen 314 in the lower part.
  Layout measured from the Bild 318 picture inside the Commons file of Zusatzzeichen 1040-32; the Commons file of
  Zeichen 318 itself goes in through the library (set de-townplus, id 318) for a static view (parkscheibe(...,
  source="commons")), since an unaltered picture cannot show a chosen time.
Street frames come from townplus.Street (x positive to the right of +u).
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector, geometry

import town as TN
import townplus as TP
import world as W

BAY_W = 2.00
BAY_L = 5.70
BAY_L_END = 5.20
BAY_LINE = 0.12
MIN_LANE = 3.00
JUNCTION_CLEAR = 5.0

DISC_W, DISC_H = 0.110, 0.150
PIVOT_FROM_TOP = 0.050
WIN_R0, WIN_R1, WIN_HALF = 0.020, 0.045, math.radians(50.0)
BLUE = (0.0075, 0.065, 0.25)        # linear, from the Commons picture (sRGB 21, 72, 137)


# ------------------------------------------------------------------ bays
def bays(T, c, st, side=+1, s0=None, n=6, length=BAY_L, end_length=BAY_L_END, width=BAY_W, line=BAY_LINE,
         name="bays"):
    """A row of n marked parallel bays on kerb side `side` of street st, starting at s0 in the direction of the
    traffic that uses them (side +1: traffic along +u, bays from s0 upwards; side -1: from s0 downwards).
    The first and last bays are end bays (shorter, a car can pull straight in or out over the open end).
    Lines: one continuous longitudinal line at the bay's road edge, transverse lines from it to the gutter.
    Returns dict(bays=[(s_a, s_b)], x_kerb, x_line, side, objs)."""
    d = side
    s0 = (st.s0 + 3.0) if s0 is None and d > 0 else ((st.s1 - 3.0) if s0 is None else s0)
    lens = [end_length] + [length] * max(0, n - 2) + ([end_length] if n > 1 else [])
    out_bays = []
    s = s0
    for L in lens:
        a, b = sorted((s, s + d * L))
        out_bays.append((a, b))
        s += d * L
    x_kerb = side * st.hw
    x_edge = side * (st.hw - width)
    gx = side * (st.hw - TN.GUTTER)
    x_line = sorted((x_edge, x_edge + side * line))
    lo = min(a for a, b in out_bays)
    hi = max(b for a, b in out_bays)
    items = [(lo, hi, x_line[0], x_line[1])]
    cuts = sorted({a for a, b in out_bays} | {b for a, b in out_bays})
    for k, sc in enumerate(cuts):
        # lines at the ends sit inside the row, the ones between bays are centred on the joint
        if k == 0:
            s_a, s_b = sc, sc + line
        elif k == len(cuts) - 1:
            s_a, s_b = sc - line, sc
        else:
            s_a, s_b = sc - line / 2, sc + line / 2
        items.append((s_a, s_b, *sorted((x_edge, gx))))
    o = TP.rects(name, st, items, TP.PAINT_Z, T.paint, c, kind="bays")
    o["bay_len"], o["bay_end_len"], o["bay_w"], o["line"], o["side"] = length, end_length, width, line, side
    o["bays"] = [v for ab in out_bays for v in ab]
    return dict(bays=out_bays, x_kerb=x_kerb, x_line=x_line, side=side, objs=[o], width=width, street=st)


def bay_pose(row, i, wrong_way=False, inset=0.0):
    """World position (Vector 2D) and yaw (0 = +x, the car's nose) of a car parked in bay i of a row from bays().
    The car stands 1.00 m from the kerb face (its centre), nose with the traffic unless wrong_way."""
    st, side = row["street"], row["side"]
    a, b = row["bays"][i]
    x = side * (st.hw - row["width"] / 2 - inset)
    p = st.p((a + b) / 2, x)
    yaw = st.heading(side if not wrong_way else -side)
    return p, yaw


def park(src, c, row, i, wrong_way=False, name="parked", shift=0.0):
    """Instance a car collection (stage.fleet / jx.hero coll) in bay i. Car models face +y, so rz = yaw - pi/2."""
    p, yaw = bay_pose(row, i, wrong_way)
    st = row["street"]
    p = p + st.u * shift
    e = bpy.data.objects.new(name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = src
    e.location = (p.x, p.y, 0.0)
    e.rotation_euler = (0, 0, yaw - math.pi / 2)
    c.objects.link(e)
    e["bay"], e["wrong_way"] = i, bool(wrong_way)
    return e


def place_hero(hero, row, i, wrong_way=False):
    """Put a jx.hero car (its instance empty) into bay i, no animation."""
    p, yaw = bay_pose(row, i, wrong_way)
    o = hero["obj"]
    o.location = (p.x, p.y, 0.0)
    o.rotation_euler = (0, 0, yaw - math.pi / 2)
    return o


def row_signs(c, row, disc=True, extra=None, name="p314"):
    """Zeichen 314 (with 1040-32 when disc) at the start of the row, facing the traffic that uses it, on the
    footway 0.6 m behind the kerb. extra: more Zusatzzeichen ids under it."""
    st, side = row["street"], row["side"]
    a, b = row["bays"][0] if side > 0 else row["bays"][0]
    s = a - 0.4 if side > 0 else b + 0.4
    stack = [((TP.SIGN_SET, "314"), 0.6)]
    if disc:
        stack.append(((TP.SIGN_SET, "1040-32"), 0.6))
    for z in (extra or []):
        stack.append(((TP.SIGN_SET, z), 0.6))
    return TP.sign_post(c, st, s, side, stack, sign=side, name=name)


def no_stopping(c, st, side, s, kind="283", name="haltverbot"):
    """Zeichen 283 (absolute no stopping) or 286 (no parking) on the footway at s, facing traffic on that side."""
    return TP.sign_post(c, st, s, side, [((TP.SIGN_SET, kind), 0.6)], sign=side, name=name)


def street(T, c, st, fleet, n=6, sides=(+1, -1), s0=None, wrong_way=None, empty=(), seed=3, signs=True,
           skip=None):
    """A full parking street on frame st: bay rows on the given sides, parked cars from `fleet` (dict of car
    collections, e.g. townstage.build()["fleet"]), the 314 + 1040-32 signs and Zeichen 283 over the 5 m before the
    first bay. wrong_way: (side, bay index) of the one car parked against the traffic. empty: {(side, i)} left free.
    skip: {(side, i)} left for hero cars. Returns dict(rows={side: row}, cars=[...], signs=[...])."""
    import random
    rnd = random.Random(seed)
    keys = sorted(fleet)
    rows, cars, sg = {}, [], []
    for side in sides:
        s_start = s0[side] if isinstance(s0, dict) else s0
        row = bays(T, c, st, side, s_start, n, name=f"bays_{'r' if side > 0 else 'l'}")
        rows[side] = row
        for i in range(n):
            if (side, i) in set(empty) | set(skip or ()):
                continue
            ww = wrong_way is not None and tuple(wrong_way) == (side, i)
            k = rnd.choice(keys)
            cars.append(park(fleet[k], c, row, i, ww, name=f"parked_{k}", shift=rnd.uniform(-0.25, 0.25)))
        if signs:
            sg.append(row_signs(c, row, name=f"p314_{'r' if side > 0 else 'l'}"))
            first = row["bays"][0]
            s_n = first[0] - 6.0 if side > 0 else first[1] + 6.0
            sg.append(no_stopping(c, st, side, s_n, "283", name=f"z283_{'r' if side > 0 else 'l'}"))
    return dict(rows=rows, cars=cars, signs=sg)


def remaining_lane(st, rows):
    """Carriageway width left between the bay rows (must be at least 3.00 m)."""
    w = 2 * st.hw
    for row in rows.values():
        w -= row["width"]
    return w


# ------------------------------------------------------------------ parallel parking
def parallel_paths(row, i, lane_x=None, R=5.6, approach=30.0, beside=1.0):
    """Reverse parallel parking into bay i of `row`.
    approach: jx.Path in the driving direction from `approach` m before the gap to the stop point, beside the car
    ahead of the gap (the car's centre `beside` m ahead of the gap's front end, in the lane).
    reverse: jx.Path ordered the way the car's NOSE points (from the parked position up to the stop point), so a
    reversing car runs it with s DEcreasing from reverse.length to 0 (see parallel_track).
    The S-curve is two circular arcs of radius R (centre path), tangent to the lane and to the bay."""
    import jx
    st, side = row["street"], row["side"]
    d = side
    a, b = row["bays"][i]
    end_p, yaw = bay_pose(row, i)
    s_end, x_end = st.local(end_p)
    # lane line of the parking car: alongside the parked cars with about 0.7 m between the bodies
    lane_x = lane_x if lane_x is not None else side * (st.hw - row["width"] - 1.5)
    dx = abs(x_end - lane_x)
    th = math.acos(max(-1.0, min(1.0, 1 - dx / (2 * R))))
    run = 2 * R * math.sin(th)
    s_stop = s_end + d * run
    # the stop point is beside the car ahead (front of the gap + beside); any extra is a straight reverse in the lane
    front = b if d > 0 else a
    s_stop = max(s_stop, front + beside) if d > 0 else min(s_stop, front - beside)
    pts_ap = []
    n = 16
    for k in range(n + 1):
        q = st.p(s_stop - d * approach + d * approach * k / n, lane_x)
        pts_ap.append((q.x, q.y))
    # reverse path in nose order: bay centre -> S (two arcs) -> straight in the lane -> stop point
    pts = []
    m = 24
    sgn_x = 1 if lane_x > x_end else -1
    for k in range(0, m + 1):
        u = k / m
        if u <= 0.5:
            t = th * (u / 0.5)
            ds = R * math.sin(t)
            dx_ = R * (1 - math.cos(t))
        else:
            t = th * ((1 - u) / 0.5)
            ds = run - R * math.sin(t)
            dx_ = dx - R * (1 - math.cos(t))
        q = st.p(s_end + d * ds, x_end + sgn_x * dx_)
        pts.append((q.x, q.y))
    if abs(s_stop - (s_end + d * run)) > 0.05:
        q = st.p(s_stop, lane_x)
        pts.append((q.x, q.y))
    return dict(approach=jx.Path(pts_ap), reverse=jx.Path(pts), s_stop=s_stop, lane_x=lane_x, theta=th, run=run,
                end=(end_p, yaw))


def parallel_track(paths, n_frames, fps=30, v_app=4.0, t_stop=0.8, v_rev=1.1, a=1.2, a_brake=1.6, ind="R"):
    """Per-frame track (motion.bake contract: x, y, yaw (nose, 0 = +x), v, ind) for the whole manoeuvre: approach
    with the indicator on, stop beside the car ahead, pause, reverse along the S into the bay, settle.
    v is signed (negative while reversing). Frames run from 1; the list has n_frames entries (the car holds at
    the end). Approach takes about approach / v_app + v_app / (2 a_brake) seconds."""
    ap, rv = paths["approach"], paths["reverse"]
    out = []
    dt = 1.0 / fps
    s, v = 0.0, v_app
    phase, hold = 1, 0.0
    sr = rv.length
    while len(out) < n_frames:
        if phase == 1:
            rem = ap.length - s
            if rem <= 0.01:
                v, phase, s = 0.0, 2, ap.length
            else:
                v = min(v_app, max(0.12, math.sqrt(2 * a_brake * rem)))
                s = min(ap.length, s + v * dt)
            p, yaw = ap.at(s)
            out.append(dict(x=p.x, y=p.y, yaw=yaw, v=v, ind=ind))
        elif phase == 2:
            hold += dt
            p, yaw = ap.at(ap.length)
            out.append(dict(x=p.x, y=p.y, yaw=yaw, v=0.0, ind=ind))
            if hold >= t_stop:
                phase, v = 3, 0.0
        else:
            if sr > 0.005:
                v = min(v_rev, v + a * dt, max(0.08, math.sqrt(2 * 0.8 * sr)))
                sr = max(0.0, sr - v * dt)
            else:
                v, sr = 0.0, 0.0
            p, yaw = _nose_pose(rv, sr)
            out.append(dict(x=p.x, y=p.y, yaw=yaw, v=-v, ind=None))
    return out


def _nose_pose(path, s, wb=2.6):
    pf, _ = path.at(s + wb / 2)
    pr, _ = path.at(s - wb / 2)
    dd = pf - pr
    p, _ = path.at(s)
    return p, math.atan2(dd.y, dd.x)


def bake_track(car, track, night=False):
    """Bake a per-frame track onto a car: kit/motion.py when it exists (wheels, steering, brake lights, indicators),
    else stage.bake_motion for position and heading (plus jx brake lights and indicators for jx.hero cars)."""
    try:
        import motion
        rig = motion.rig(car["obj"] if isinstance(car, dict) else car)
        return motion.bake(rig, track, night=night)
    except ImportError:
        pass
    import stage
    obj = car["obj"] if isinstance(car, dict) else car
    frames = list(range(1, len(track) + 1))
    locs = [(t["x"], t["y"], 0.0) for t in track]
    rots = [(0.0, 0.0, t["yaw"] - math.pi / 2) for t in track]
    for i in range(1, len(rots)):
        a = rots[i][2]
        while a - rots[i - 1][2] > math.pi:
            a -= 2 * math.pi
        while a - rots[i - 1][2] < -math.pi:
            a += 2 * math.pi
        rots[i] = (0.0, 0.0, a)
    stage.bake_motion(obj, frames, locs, rots)
    if isinstance(car, dict) and "tail" in car:
        import jx
        jx.brake_lights(car, [(0.0, abs(t["v"])) for t in track])
        on = [i for i, t in enumerate(track) if t["ind"] in ("R", "L")]
        if on:
            side = track[on[0]]["ind"]
            jx.blink(car, side, on[0] / 30.0, (on[-1] + 1) / 30.0)
        car["track"] = locs
    return None


# ------------------------------------------------------------------ the parking disc (Bild 318)
def _disc_mats():
    if "pd_blue" in bpy.data.materials:
        g = bpy.data.materials
        return g["pd_blue"], g["pd_white"], g["pd_black"]
    blue = W.principled("pd_blue", BLUE, 0.38, coat=0.35)
    white = W.principled("pd_white", (0.86, 0.87, 0.88), 0.45)
    black = W.principled("pd_black", (0.012, 0.012, 0.014), 0.5)
    return blue, white, black


def _plate_xz(name, outline, y, mat, c, holes=None, parent=None):
    """Flat polygon in the XZ plane at depth y, facing -Y, optional holes (lists of (x, z)). Triangulated."""
    loops = [[Vector((x, z, 0)) for x, z in outline]] + [[Vector((x, z, 0)) for x, z in h] for h in (holes or [])]
    flat = [p for lp in loops for p in lp]
    tris = geometry.tessellate_polygon(loops)
    verts = [(p.x, y, p.y) for p in flat]
    o = W.mesh_obj(name, verts, [tuple(t) for t in tris], mat, c,
                   uvs=[(p.x, p.y) for p in flat])
    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    for f in bm.faces:
        f.normal_update()
        if f.normal.y > 0:
            f.normal_flip()
    bm.to_mesh(me)
    bm.free()
    if parent:
        o.parent = parent
    return o


def _text(name, body, size, mat, c, parent, loc, width=None, height=None):
    t = W.text_obj(name, body, size, mat, c, "CENTER", "CENTER", 0.0)
    t.rotation_euler = (math.radians(90), 0, 0)
    t.location = loc
    t.parent = parent
    if width or height:
        bpy.context.view_layer.update()
        dims = t.dimensions
        k = (width / dims.x) if width else (height / dims.y)
        t.scale = (k, k, k)
    return t


COMMONS_TIME = 18.0     # the time the Commons file of Zeichen 318 shows (pointer on 6 / 18)


def parkscheibe(c, time_h=None, name="parkscheibe", source="auto"):
    """The blue parking disc as a prop, 110 x 150 mm. Local frame like a sign: the face looks along -Y, x to the
    viewer's right, z up, origin at the bottom centre of the card.
    source="commons": the Commons file of Zeichen 318 (set de-townplus), unaltered, on a card of the official size;
    it shows 18:00 and cannot be changed. source="model": a disc built to the Bild 318 layout with a dial that turns
    (set_time). source="auto" (default): the Commons file when no time or 18:00 is asked for, else the model.
    Returns dict(root, dial, set_time(frame, hours), source)."""
    import signs as SG
    if source == "auto":
        want = time_h is None or abs((time_h % 12) - (COMMONS_TIME % 12)) < 1e-6
        source = "commons" if (want and TP.has_sign("318", "de-townplus")) else "model"
    time_h = COMMONS_TIME if time_h is None else time_h
    root = bpy.data.objects.new(name, None)
    c.objects.link(root)
    root["parkscheibe"] = source
    blue, white, black = _disc_mats()
    if source == "commons" and TP.has_sign("318", "de-townplus"):
        f = SG.face("318", c, DISC_W, "de-townplus", name=name + "_commons", back=False)
        f.parent = root
        f.location = (0, 0.0, 0.0)
        # card back (printed side faces the driver; plain blue here)
        _plate_xz(name + "_card_back", [(-DISC_W / 2, 0), (DISC_W / 2, 0), (DISC_W / 2, f["height"]),
                                        (-DISC_W / 2, f["height"])], 0.0008, blue, c, parent=root)
        root["source"] = "Commons de-townplus/318"
        root["time_h"] = COMMONS_TIME
        return dict(root=root, dial=None, set_time=lambda frame, h: None, source="commons")
    pz = DISC_H - PIVOT_FROM_TOP
    # front card with the window cut out
    r_c = 0.004
    outer = W.rounded_rect(DISC_W, DISC_H, r_c, seg=4)
    outer = [(x, z + DISC_H / 2) for x, z in outer]
    hole = []
    n = 36
    for k in range(n + 1):
        a = -WIN_HALF + 2 * WIN_HALF * k / n
        hole.append((WIN_R1 * math.sin(a), pz - WIN_R1 * math.cos(a)))
    for k in range(n + 1):
        a = WIN_HALF - 2 * WIN_HALF * k / n
        hole.append((WIN_R0 * math.sin(a), pz - WIN_R0 * math.cos(a)))
    _plate_xz(name + "_card", outer, 0.0, blue, c, holes=[hole], parent=root)
    _plate_xz(name + "_card_back", list(reversed(outer)), 0.0012, blue, c, parent=root)
    # pointer (white wedge), fixed, tip 12.4 mm below the pivot
    ptr = [(-0.00815, pz + 0.0173), (0.00815, pz + 0.0173), (0.0, pz - 0.0124)]
    _plate_xz(name + "_pointer", ptr, -0.0002, white, c, parent=root)
    _text(name + "_ankunft", "ANKUNFTSZEIT", 0.007, white, c, root, (0, -0.0002, DISC_H - 0.0177), width=0.048)
    # Zeichen 314 from the library for the P field (39.4 mm square, lower edge 10.8 mm above the bottom)
    if TP.has_sign("314"):
        pf = SG.face("314", c, 0.0394, TP.SIGN_SET, name=name + "_p314", back=False)
        pf.parent = root
        pf.location = (0, -0.0002 + 0.003, 0.0108)
    # the dial: a white disc behind the card turning about the pivot, numbers and half-hour ticks
    dial = bpy.data.objects.new(name + "_dial", None)
    c.objects.link(dial)
    dial.parent = root
    dial.location = (0, 0.0006, pz)
    dial.rotation_mode = "XYZ"
    circ = [(0.047 * math.cos(2 * math.pi * k / 72), 0.047 * math.sin(2 * math.pi * k / 72)) for k in range(72)]
    _plate_xz(name + "_dialdisc", circ, 0.0002, white, c, parent=dial)
    for h in range(12):
        hh = 12 if h == 0 else h
        slot = bpy.data.objects.new(f"{name}_slot{hh}", None)
        c.objects.link(slot)
        slot.parent = dial
        slot.rotation_mode = "XYZ"
        slot.rotation_euler = (0, -math.radians(30 * hh), 0)
        _text(f"{name}_h{hh}", str(hh), 0.014, black, c, slot, (0, -0.0001, -0.0315), height=0.0125)
        _text(f"{name}_h{hh + 12}", str(hh + 12), 0.005, black, c, slot, (0, -0.0001, -0.0412), height=0.0034)
        tick = [(-0.0003, -0.0208), (0.0003, -0.0208), (0.0003, -0.0248), (-0.0003, -0.0248)]
        _plate_xz(f"{name}_tick{hh}", tick, -0.0001, black, c, parent=slot)
        half = bpy.data.objects.new(f"{name}_halfslot{hh}", None)
        c.objects.link(half)
        half.parent = dial
        half.rotation_mode = "XYZ"
        half.rotation_euler = (0, -math.radians(30 * hh + 15), 0)
        tick = [(-0.00025, -0.0208), (0.00025, -0.0208), (0.00025, -0.0232), (-0.00025, -0.0232)]
        _plate_xz(f"{name}_htick{hh}", tick, -0.0001, black, c, parent=half)

    def set_time(frame, hours):
        dial.rotation_euler = (0, math.radians(30 * (hours % 12)), 0)
        if frame is not None:
            dial.keyframe_insert("rotation_euler", frame=frame)

    set_time(None, time_h)
    root["time_h"] = time_h
    for o in [root] + list(root.children_recursive):
        if o.type in ("MESH", "FONT"):
            o.visible_shadow = True
    return dict(root=root, dial=dial, set_time=set_time, source="model")


def round_up_half_hour(hours):
    """German rule: set the arrival time rounded UP to the next half hour (12:03 -> 12:30, 12:30 -> 12:30)."""
    return math.ceil(hours * 2 - 1e-9) / 2


# ------------------------------------------------------------------ behind a windscreen
def _windscreen(kind):
    import vehicles as V
    k = V.KINDS[kind]
    L = k["L"]
    st_ = k["stations"]
    idx = [i for i, t in enumerate(k["spans"]) if t == "f"][-1]
    a, b = st_[idx], st_[idx + 1]
    top = Vector((0, a[0] - L / 2, a[7]))
    bot = Vector((0, b[0] - L / 2, b[7]))
    return top, bot, k


def see_through(hero, interior=(0.03, 0.03, 0.032)):
    """Make a jx.hero car's glass see-through (thin glass: Fresnel mix of transparent and glossy), give the body a
    dark inside, and add a dashboard, seats and a steering wheel so a camera can look in."""
    coll, name, kind = hero["coll"], hero["name"], hero["kind"]
    body = coll.objects[name + "_body"]
    g = bpy.data.materials.new(name + "_thin_glass")
    g.use_nodes = True
    nt = g.node_tree
    for n_ in list(nt.nodes):
        if n_.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n_)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    tr.inputs["Color"].default_value = (0.78, 0.84, 0.82, 1)
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = 0.02
    fr = nt.nodes.new("ShaderNodeFresnel")
    fr.inputs["IOR"].default_value = 1.52
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fr.outputs[0], mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(gl.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    body.data = body.data.copy()
    body.data.materials[1] = g
    # dark inside of the shell: backfacing faces of the paint read as the cabin lining
    paint = body.data.materials[0].copy()
    paint.name = name + "_paint_in"
    pnt = paint.node_tree
    out = next(n_ for n_ in pnt.nodes if n_.type == "OUTPUT_MATERIAL")
    src = out.inputs["Surface"].links[0].from_socket
    geo = pnt.nodes.new("ShaderNodeNewGeometry")
    dark = pnt.nodes.new("ShaderNodeBsdfPrincipled")
    dark.inputs["Base Color"].default_value = (*interior, 1)
    dark.inputs["Roughness"].default_value = 0.8
    mx2 = pnt.nodes.new("ShaderNodeMixShader")
    pnt.links.new(geo.outputs["Backfacing"], mx2.inputs[0])
    pnt.links.new(src, mx2.inputs[1])
    pnt.links.new(dark.outputs[0], mx2.inputs[2])
    pnt.links.new(mx2.outputs[0], out.inputs["Surface"])
    body.data.materials[0] = paint
    top, bot, k = _windscreen(kind)
    Wh = k["W"]
    dash_m = W.principled(name + "_dash", (0.025, 0.025, 0.028), 0.6)
    seat_m = W.principled(name + "_seat", (0.05, 0.05, 0.055), 0.85)
    g_root = coll.objects[name]
    parts = []
    parts.append(TN.box(name + "_dash", coll, (0, bot.y - 0.3, bot.z - 0.1), (2 * Wh * 0.86, 0.5, 0.14), dash_m,
                        bevel=0.04))
    parts.append(TN.box(name + "_dash_lower", coll, (0, bot.y - 0.45, bot.z - 0.32), (2 * Wh * 0.8, 0.3, 0.3),
                        dash_m, bevel=0.04))
    for sx in (-1, 1):
        parts.append(TN.box(name + "_seat", coll, (sx * Wh * 0.42, bot.y - 1.25, 0.55), (0.5, 0.55, 0.14), seat_m,
                            bevel=0.05))
        bk = TN.box(name + "_seatback", coll, (sx * Wh * 0.42, bot.y - 1.55, 0.9), (0.5, 0.12, 0.65), seat_m,
                    bevel=0.05)
        bk.rotation_euler.x = math.radians(-14)
        parts.append(bk)
        parts.append(TN.box(name + "_headrest", coll, (sx * Wh * 0.42, bot.y - 1.63, 1.3), (0.26, 0.1, 0.18),
                            seat_m, bevel=0.04))
    me = bpy.data.meshes.new(name + "_wheel")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=24, radius1=0.19, radius2=0.19, depth=0.03)
    bm.to_mesh(me)
    bm.free()
    wh = bpy.data.objects.new(name + "_wheel", me)
    coll.objects.link(wh)
    me.materials.append(dash_m)
    wh.location = (-Wh * 0.42, bot.y - 0.62, bot.z - 0.02)
    wh.rotation_euler = (math.radians(70), 0, 0)
    sol = wh.modifiers.new("s", "SOLIDIFY")
    sol.thickness = 0.03
    parts.append(wh)
    for p in parts:
        p.parent = g_root
    return dict(glass=g, parts=parts)


def windscreen_mount(hero, disc, side=+1, along=0.86, x=0.32):
    """Lean the disc against the inside of the windscreen on the dashboard, its face readable from outside.
    side +1: right (passenger) side of the car. Ray-casts the car body for the glass surface."""
    coll, name, kind = hero["coll"], hero["name"], hero["kind"]
    body = coll.objects[name + "_body"]
    top, bot, k = _windscreen(kind)
    t = (bot - top).normalized()                 # down the glass
    nrm = Vector((0, -t.z, t.y)).normalized()    # outward (up and forward)
    p = top.lerp(bot, along) + Vector((side * x, 0, 0))
    origin = p + nrm * 1.0
    # the body mesh is offset inside the car (car() moves its parts by -L/2): cast in the body's own space
    mw = body.matrix_local
    inv = mw.inverted()
    hit, loc, n_hit, _i = body.ray_cast(inv @ origin, (inv.to_3x3() @ -nrm).normalized(), distance=3.0)
    if hit:
        loc = mw @ loc
        n_hit = (mw.to_3x3() @ n_hit).normalized()
    else:
        loc, n_hit = p, nrm
    n_out = n_hit.normalized() if n_hit.dot(nrm) > 0 else -n_hit.normalized()
    up = (-t - n_out * (-t).dot(n_out)).normalized()
    ydir = -n_out
    xdir = ydir.cross(up).normalized()
    m = Matrix((xdir, ydir, up)).transposed().to_4x4()
    m.translation = loc - n_out * 0.014
    root = disc["root"]
    for cc in list(root.users_collection):
        cc.objects.unlink(root)
    coll.objects.link(root)
    for ch in root.children_recursive:
        for cc in list(ch.users_collection):
            cc.objects.unlink(ch)
        coll.objects.link(ch)
    root.matrix_world = m
    root.parent = coll.objects[name]
    root.matrix_parent_inverse = coll.objects[name].matrix_world.inverted()
    root["mounted_on"] = name
    return root
