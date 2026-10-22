"""Junction episode toolkit: lane paths through the X junction, simple kinematics (cruise, stop at a line, hold),
hero cars with their own brake lights and indicators, quiz badges (A, B, C) that float above the roof, path ribbons,
camera shots switched by markers, and the frame render loop. Right-hand traffic."""
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

import stage
import vehicles as V
import world as W

FPS = 30
LANE = 1.5            # centre of the right lane of a 6.0 m street


# ------------------------------------------------------------------ paths
class Path:
    def __init__(self, pts):
        self.p = [Vector((x, y)) for x, y in pts]
        self.acc = [0.0]
        for i in range(1, len(self.p)):
            self.acc.append(self.acc[-1] + (self.p[i] - self.p[i - 1]).length)
        self.length = self.acc[-1]

    def at(self, s):
        """Position (Vector 2D) and heading (radians, 0 = +x) at arc length s; extrapolates past both ends."""
        p, acc = self.p, self.acc
        if s <= 0:
            t = (p[1] - p[0]).normalized()
            return p[0] + t * s, math.atan2(t.y, t.x)
        if s >= self.length:
            t = (p[-1] - p[-2]).normalized()
            return p[-1] + t * (s - self.length), math.atan2(t.y, t.x)
        lo, hi = 0, len(acc) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if acc[mid] <= s:
                lo = mid
            else:
                hi = mid
        seg = acc[hi] - acc[lo]
        u = (s - acc[lo]) / seg if seg > 0 else 0.0
        t = (p[hi] - p[lo]).normalized()
        return p[lo].lerp(p[hi], u), math.atan2(t.y, t.x)

    def s_of_y(self, y, approx_from=0.0):
        """First arc length where the path reaches coordinate y (for straight northbound paths)."""
        best = min(range(len(self.p)), key=lambda i: abs(self.p[i].y - y))
        return self.acc[best]


def _rot(pts, ang):
    c, s = math.cos(ang), math.sin(ang)
    return [(x * c - y * s, x * s + y * c) for x, y in pts]


APPROACH_ROT = {"S": 0.0, "W": -math.pi / 2, "N": math.pi, "E": math.pi / 2}


def lane_path(frm, turn="straight", L=95.0, r_right=6.0, r_left=9.0, lane=LANE, n=24):
    """Path for a car that comes FROM arm frm ('S' means it drives north) and goes straight, right or left.
    The path starts L metres out on the approach. Arc length 0 is the start."""
    pts = [(lane, -L)]
    if turn == "straight":
        pts += [(lane, -10.0), (lane, 0.0), (lane, 10.0), (lane, L)]
    elif turn == "right":
        cx, cy, r = lane + r_right, -(lane + r_right), r_right
        pts += [(lane, cy)]
        pts += [(cx + r * math.cos(math.pi - (math.pi / 2) * k / n), cy + r * math.sin(math.pi - (math.pi / 2) * k / n))
                for k in range(1, n + 1)]
        pts += [(L, -lane)]
    elif turn == "left":
        cx, cy, r = lane - r_left, lane - r_left, r_left
        pts += [(lane, cy)]
        pts += [(cx + r * math.cos((math.pi / 2) * k / n), cy + r * math.sin((math.pi / 2) * k / n))
                for k in range(1, n + 1)]
        pts += [(-L, lane)]
    return Path(_rot(pts, APPROACH_ROT[frm]))


def dist_to_line(frm, line_offset, L=95.0):
    """Arc length (from the path start) of a line `line_offset` metres before the junction centre on arm frm."""
    return L - line_offset


# ------------------------------------------------------------------ kinematics
def kinematics(s0, v0, plan, n_frames, fps=FPS, a_acc=2.2, a_brake=3.0):
    """plan: list of (t, cmd, arg) sorted by t. cmd: 'cruise' (target m/s), 'stop' (stop line arc length),
    'hold' (None). Returns (s, v) per frame."""
    s, v = s0, v0
    out = []
    dt = 1.0 / fps
    sub = 8
    for f in range(n_frames):
        t = f / fps
        for _k in range(sub):
            tt = t + _k * dt / sub
            cmd, arg = "cruise", v0
            for (tp, c_, a_) in plan:
                if tp <= tt:
                    cmd, arg = c_, a_
            h = dt / sub
            if cmd == "cruise":
                if v < arg:
                    v = min(arg, v + a_acc * h)
                else:
                    v = max(arg, v - a_brake * h)
            elif cmd == "stop":
                rem = arg - s
                if rem <= 0.02 or v <= 0.05:
                    v = 0.0 if rem <= 0.6 or v <= 0.05 else v
                    if rem <= 0.02:
                        v = 0.0
                else:
                    need = v * v / (2 * rem)
                    v = max(0.0, v - need * h)
            elif cmd == "hold":
                v = 0.0
            s += v * h
        out.append((s, v))
    return out


# ------------------------------------------------------------------ hero cars
def amber():
    m = bpy.data.materials.new("indicator")
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.9, 0.35, 0.0, 1)
    p.inputs["Emission Color"].default_value = (1.0, 0.45, 0.0, 1)
    p.inputs["Emission Strength"].default_value = 0.0
    p.inputs["Roughness"].default_value = 0.15
    return m


def hero(kind, color, name, plate, lib, traffic, metal=0.45):
    """A car built only for this episode (own brake-light and indicator materials). Returns a dict."""
    coll = V.car(kind, color, name, plate, metal=metal, c=lib)
    bpy.context.view_layer.update()
    body = coll.objects[name + "_body"]
    g = coll.objects[name]
    tail = bpy.data.materials["car_tail"].copy()
    tail.name = name + "_tail"
    for o in coll.objects:
        if o.name.startswith(("taillight", "brake3")) and o.data and o.data.materials:
            o.data = o.data.copy()
            o.data.materials[0] = tail
    ind_l, ind_r = amber(), amber()
    ind_l.name, ind_r.name = name + "_ind_L", name + "_ind_R"
    k = V.KINDS[kind]
    L, Wh = k["L"], k["W"]
    mw = body.matrix_world
    bb = [mw @ Vector(c_) for c_ in body.bound_box]
    roof = max(v.z for v in bb)
    zf = k["stations"][-2][3] - 0.02
    zr = k["stations"][1][3] + 0.04
    for side, m in ((-1, ind_l), (1, ind_r)):
        for (y, z, sz) in ((L / 2 - 0.12, zf, (0.16, 0.08, 0.06)), (-L / 2 + 0.1, zr, (0.14, 0.06, 0.06)),
                           (L * 0.16, (k["stations"][len(k["stations"]) // 2][3]) + 0.14, (0.1, 0.03, 0.03))):
            # ray cast inwards from outside the corner to sit on the body
            origin = Vector((side * (Wh + 1.0), y, z))
            loc_local = body.matrix_world.inverted() @ origin
            dir_local = body.matrix_world.inverted().to_3x3() @ Vector((-side, 0, 0))
            hit, loc, nrm, _i = body.ray_cast(loc_local, dir_local, distance=5.0)
            if not hit:
                continue
            wl = body.matrix_world @ loc
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=1.0)
            for v in bm.verts:
                v.co.x *= sz[1]
                v.co.y *= sz[0]
                v.co.z *= sz[2]
            me = bpy.data.meshes.new(name + "_ind")
            bm.to_mesh(me)
            bm.free()
            o = bpy.data.objects.new(name + "_ind", me)
            coll.objects.link(o)
            me.materials.append(m)
            o.location = wl + Vector((side * 0.01, 0, 0))
            o.parent = g
    e = bpy.data.objects.new(name + "_inst", None)
    e.instance_type = "COLLECTION"
    e.instance_collection = coll
    traffic.objects.link(e)
    return dict(name=name, kind=kind, obj=e, coll=coll, tail=tail, ind={"L": ind_l, "R": ind_r}, L=L, W=Wh,
                roof=roof)


def drive(car, path, sv, frames, z=0.0):
    """Bake the car along `path` with the (s, v) list (one per frame, frames 1..N)."""
    locs, rots = [], []
    wb = 0.55 * car["L"]
    for (s, v) in sv:
        # heading from the rear axle to the front axle (a car pivots around its rear axle)
        pf, _ = path.at(s + wb / 2)
        pr, _ = path.at(s - wb / 2)
        d = pf - pr
        yaw = math.atan2(d.y, d.x) - math.pi / 2
        p, _ = path.at(s)
        locs.append((p.x, p.y, z))
        rots.append((0.0, 0.0, yaw))
    # unwrap yaw
    for i in range(1, len(rots)):
        a = rots[i][2]
        while a - rots[i - 1][2] > math.pi:
            a -= 2 * math.pi
        while a - rots[i - 1][2] < -math.pi:
            a += 2 * math.pi
        rots[i] = (0.0, 0.0, a)
    stage.bake_motion(car["obj"], frames, locs, rots)
    car["track"] = locs


def key_emission(m, pairs, constant=True):
    inp = m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    for f, val in pairs:
        inp.default_value = val
        inp.keyframe_insert("default_value", frame=f)
    if constant:
        for fc in stage.fcurves(m.node_tree):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


def brake_lights(car, sv, base=0.8, braking=6.0):
    """Brake lights on while decelerating or standing."""
    pairs = []
    state = None
    for i in range(len(sv)):
        v = sv[i][1]
        v_prev = sv[i - 1][1] if i else v
        on = (v_prev - v) > 0.004 or v < 0.05
        if on != state:
            pairs.append((i + 1, braking if on else base))
            state = on
    key_emission(car["tail"], pairs)


def blink(car, side, t0, t1, period=0.66):
    """German indicators flash at 1.5 Hz (90 a minute): on half the period."""
    m = car["ind"][side]
    pairs = [(1, 0.0)]
    t = t0
    while t < t1:
        pairs.append((int(t * FPS) + 1, 12.0))
        pairs.append((int((t + period / 2) * FPS) + 1, 0.0))
        t += period
    key_emission(m, pairs)


# ------------------------------------------------------------------ quiz layer
BADGE_COLOURS = {"A": (1.0, 0.75, 0.0), "B": (0.0, 0.75, 1.0), "C": (1.0, 0.2, 0.6)}


def flat_mat(name, color, emit=0.8, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Emission Color"].default_value = (*color, 1)
    p.inputs["Emission Strength"].default_value = emit
    p.inputs["Roughness"].default_value = 0.4
    p.inputs["Alpha"].default_value = alpha
    return m


def badge(letter, car, c, font, t_on, t_off, size=1.9, color=None):
    """A round letter badge floating above the car's roof, upright on screen in the top view (+y up)."""
    color = color or BADGE_COLOURS[letter]
    root = bpy.data.objects.new("badge_" + letter, None)
    c.objects.link(root)
    disc_m = flat_mat("badge_" + letter, color, emit=1.2)
    white = flat_mat("badge_white", (1, 1, 1), emit=1.5)
    dark = flat_mat("badge_ink", (0.02, 0.02, 0.03), emit=0.0)
    r = size / 2
    for name, rr, m, z in (("ring", r, white, 0.0), ("disc", r * 0.86, disc_m, 0.01)):
        bm = bmesh.new()
        bmesh.ops.create_circle(bm, cap_ends=True, segments=48, radius=rr)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new("badge_" + name, me)
        c.objects.link(o)
        me.materials.append(m)
        o.location = (0, 0, z)
        o.parent = root
    t = W.text_obj("badge_txt", letter, size * 0.86, dark, c, "CENTER", "CENTER", 0.0, font=font)
    t.location = (0, -size * 0.03, 0.02)
    t.parent = root
    for o in root.children:
        o.visible_shadow = False
    # follow the car (location only), pop in and out
    track = car["track"]
    z = car["roof"] + 0.9
    locs = [(x, y, z) for (x, y, _z) in track]
    rots = [(0, 0, 0)] * len(locs)
    stage.bake_motion(root, list(range(1, len(locs) + 1)), locs, rots)
    f_on, f_off = int(t_on * FPS) + 1, int(t_off * FPS) + 1
    for f, s in ((1, 0.0), (f_on, 0.0), (f_on + 4, 1.18), (f_on + 7, 1.0), (f_off, 1.0), (f_off + 5, 0.0)):
        root.scale = (s, s, s)
        root.keyframe_insert("scale", frame=f)
    return root


def ribbon(path, s0, s1, color, c, t_on, t_off, width=1.0, z=0.035, name="ribbon", head=2.0):
    """Translucent glowing band along the path from s0 to s1 with an arrow head; fades in and out."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n_ in list(nt.nodes):
        if n_.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n_)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = 3.2
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    fac = mx.inputs[0]
    f_on, f_off = int(t_on * FPS) + 1, int(t_off * FPS) + 1
    for f, val in ((1, 0.0), (f_on, 0.0), (f_on + 8, 0.88), (f_off, 0.88), (f_off + 8, 0.0)):
        fac.default_value = val
        fac.keyframe_insert("default_value", frame=f)
    verts, faces = [], []
    n = max(2, int((s1 - head - s0) / 0.5))
    for k in range(n + 1):
        s = s0 + (s1 - head - s0) * k / n
        p, _ = path.at(s)
        p2, _ = path.at(s + 0.05)
        t = (p2 - p).normalized()
        nrm = Vector((-t.y, t.x))
        a, b = p + nrm * width / 2, p - nrm * width / 2
        verts += [(a.x, a.y, z), (b.x, b.y, z)]
        if k:
            i = 2 * k
            faces.append((i - 2, i - 1, i + 1, i))
    p, _ = path.at(s1 - head)
    p2, _ = path.at(s1 - head + 0.05)
    t = (p2 - p).normalized()
    nrm = Vector((-t.y, t.x))
    tip = path.at(s1)[0]
    base = len(verts)
    for q in (p + nrm * width * 1.05, p - nrm * width * 1.05, tip):
        verts.append((q.x, q.y, z))
    faces.append((base, base + 1, base + 2))
    o = W.mesh_obj(name, verts, faces, m, c)
    for poly in o.data.polygons:
        if poly.normal.z < 0:
            poly.flip()
    o.visible_shadow = False
    return o


# ------------------------------------------------------------------ shots and rendering
class Shots:
    def __init__(self, n_frames):
        self.N = n_frames
        self.list = []

    def add(self, name, lens, t0, t1, fn, up_fn=None):
        sc = bpy.context.scene
        f0, f1 = int(t0 * FPS) + 1, int(t1 * FPS)
        co = stage.camera(name, lens)
        fr = list(range(max(1, f0 - 2), min(self.N, f1 + 2) + 1))
        locs, rots = [], []
        for f in fr:
            t = (f - 1) / FPS
            pos, tgt = fn(t)
            locs.append(tuple(pos))
            rots.append(tuple(stage.look_rot(Vector(pos), Vector(tgt), up_fn(t) if up_fn else None)))
        # unwrap
        for i in range(1, len(rots)):
            r = list(rots[i])
            for j in range(3):
                while r[j] - rots[i - 1][j] > math.pi:
                    r[j] -= 2 * math.pi
                while r[j] - rots[i - 1][j] < -math.pi:
                    r[j] += 2 * math.pi
            rots[i] = tuple(r)
        stage.bake_motion(co, fr, locs, rots)
        m = sc.timeline_markers.new(name, frame=f0)
        m.camera = co
        self.list.append((name, f0, f1))
        return co

    def camera_at(self, f):
        cam = None
        for name, f0, f1 in self.list:
            if f0 <= f <= f1:
                cam = bpy.data.objects[name]
        return cam


def render_frames(shots, out, todo):
    sc = bpy.context.scene
    os.makedirs(out, exist_ok=True)
    for f in todo:
        sc.frame_set(f)
        sc.camera = shots.camera_at(f) or sc.camera
        sc.render.filepath = os.path.join(out, f"f_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("Saved", sc.render.filepath, flush=True)


def ease(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def lerp3(a, b, u):
    return Vector(a).lerp(Vector(b), u)


# ------------------------------------------------------------------ sign call-outs for the top view
def callout_from(sign_coll, name, c, loc, t_on, t_off, scale=2.6, height=2.3, z=3.2):
    """Lay a copy of a sign (built by town.sign_*) flat and big above the road so the top view can read it.
    The post is dropped; the sign's up points north (screen up)."""
    lib = sign_coll
    for o in list(lib.objects):
        if o.name.startswith("post"):
            bpy.data.objects.remove(o)
    for o in lib.all_objects:
        o.visible_shadow = False
    e = bpy.data.objects.new(name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = lib
    c.objects.link(e)
    e.visible_shadow = False
    e.rotation_euler = (-math.pi / 2, 0, 0)
    base = Vector((loc[0], loc[1] - height * scale, z))
    f_on, f_off = int(t_on * FPS) + 1, int(t_off * FPS) + 1
    for f, s in ((1, 0.0), (f_on, 0.0), (f_on + 4, 1.15), (f_on + 7, 1.0), (f_off, 1.0), (f_off + 5, 0.0)):
        k = s * scale
        e.scale = (k, k, k)
        e.location = Vector((loc[0], loc[1] - height * k, z))
        e.keyframe_insert("scale", frame=f)
        e.keyframe_insert("location", frame=f)
    return e


def signal_callout(T, lib, c, name, loc, t_on, t_off, scale=2.4, z=3.2, red=True, arrow=True):
    """Flat icon of a red signal head with the green arrow plate beside it, for the top view."""
    import town as TN
    root = bpy.data.collections.new(name)
    lib.children.link(root)
    housing = W.principled("icon_housing", (0.02, 0.02, 0.022), 0.45)
    lit = flat_mat("icon_red", (1.0, 0.05, 0.02), emit=6.0)
    dark = flat_mat("icon_dark", (0.06, 0.06, 0.06), emit=0.0)
    white = flat_mat("icon_white", (1, 1, 1), emit=1.2)
    parts = [W.plate("icon_rim", W.rounded_rect(0.5, 1.12, 0.07), 0.01, white, root, 0.0),
             W.plate("icon_box", W.rounded_rect(0.42, 1.04, 0.06), 0.01, housing, root, 0.012)]
    for k, dz in enumerate((0.3, 0.0, -0.3)):
        parts.append(W.disc(f"icon_lamp{k}", 0.11, 0.004, lit if (k == 0 and red) else dark, root, 0.025))
        parts[-1].location.z += dz
    if arrow:
        parts.append(W.plate("icon_720", W.rounded_rect(0.3, 0.3, 0.03), 0.01, T.M.sblack, root, 0.012))
        parts[-1].location = (0.45, 0, 0.3)
        parts.append(W.plate("icon_720r", W.rounded_rect(0.34, 0.34, 0.04), 0.01, white, root, 0.0))
        parts[-1].location = (0.45, 0, 0.3)
        s = 0.3
        arrow_pts = [(-0.38 * s, -0.06 * s), (0.08 * s, -0.06 * s), (0.08 * s, -0.19 * s), (0.38 * s, 0.0),
                     (0.08 * s, 0.19 * s), (0.08 * s, 0.06 * s), (-0.38 * s, 0.06 * s)]
        parts.append(W.plate("icon_arrow", arrow_pts, 0.004, T.sgreen_arrow, root, 0.025))
        parts[-1].location = (0.45, 0, 0.3)
    return callout_from(root, name + "_inst", c, loc, t_on, t_off, scale=scale, height=0.0, z=z)
