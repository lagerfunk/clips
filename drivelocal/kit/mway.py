"""Track B motorway stage (dl/trackb-motorway, episodes B01 AT, B03 FR, B04 CH, B07 FR): the episode 1 motorway kit
(world.py Road, materials, guardrails, Leitpfosten, terrain, flora) rebuilt with a lane count and the country's
lane-line rhythm, plus the small props these four episodes need. No German procedural signs (owner rule), no text,
no brands; signs only as unaltered Commons files through kit/signs.py.

    import mway as MW
    S = MW.Stage(ASSETS, "fr", lanes=3)          # factory-fresh scene, road, carriageways, verge, terrain, flora
    trk = S.track([(0, 36)], [(0, S.lane_x(1))], N, s0=300)   # per-frame motion.bake track along the road
    S.drive(S.hero, trk)                          # hero (jx.hero dict) or a fleet collection
    S.chase(trk, t, back=8, up=2.2)               # (camera position, target) behind a car

Country specs (smallest fixes from scripts/trackb/*.md): France lane lines 3 m dash / 10 m gap (T1 on autoroutes),
white edge lines; Austria and Switzerland white markings as Germany (6 m / 12 m). Lane 3.75 m, left strip 0.75 m,
hard shoulder 2.65 m, Bankett 1.5 m (episode 1 cross-section)."""
import math
import random

import bpy
from mathutils import Vector

import country as CY
import flora
import jx
import motion
import stage
import town as TN
import vehicles as V
import world as W

FPS = 30
LANE = 3.75
SPEC = {
    "at": dict(dash=6.0, gap=12.0, lw=0.15, ew=0.30),
    "ch": dict(dash=6.0, gap=12.0, lw=0.15, ew=0.30),
    "fr": dict(dash=3.0, gap=10.0, lw=0.15, ew=0.30),
}


def mat(name, color, rough=0.5, metal=0.0, emit=None, estr=0.0):
    return W.principled(name, color, rough, metal=metal, emit=emit, estr=estr)


def key_emit(m, pairs):
    """Constant keys on a material's emission strength: pairs [(frame, strength)]."""
    jx.key_emission(m, pairs, constant=True)


def blink_pairs(t0, t1, period=0.66, on=8.0, fps=FPS):
    out, t = [(1, 0.0)], t0
    while t < t1:
        out += [(int(t * fps) + 1, on), (int((t + period / 2) * fps) + 1, 0.0)]
        t += period
    return out


def interp(keys, t, smooth=False):
    if t <= keys[0][0]:
        return keys[0][1]
    for (ta, a), (tb, b) in zip(keys, keys[1:]):
        if t <= tb:
            u = (t - ta) / max(1e-6, tb - ta)
            if smooth:
                u = u * u * (3 - 2 * u)
            return a + (b - a) * u
    return keys[-1][1]


class Stage:
    def __init__(self, assets, cc, lanes=3, length=2400.0, s0=40.0, s1=2300.0, mountains=False, seed=3,
                 bends=((500, 1100, 1 / 2600.0), (1400, 2000, -1 / 3000.0)), crest=((0, 1400, 3.0), (900, 2600, 2.0))):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        W.setup(assets, None)
        self.assets, self.cc, self.lanes, self.s0, self.s1 = assets, cc, lanes, s0, s1
        self.lib, self.env, self.traffic = W.coll("lib"), W.coll("env"), W.coll("traffic")
        self.ins = W.coll("inserts")
        self.cars, self.vans, self.trucks = stage.fleet(self.lib)
        CY.blank_plates([self.lib.children[k] for k in list(self.cars) + list(self.vans) + list(self.trucks)])
        self.road = W.Road(length=length, bends=bends, crest=crest)
        self.M = W.Mats()
        self.x_end = 2.75 + LANE * lanes          # outer edge of the right lane (edge line outside it)
        self.x_sh = self.x_end + 2.65             # outer edge of the hard shoulder
        self.carriageways()
        self.dress(seed)
        if mountains:
            self.mountains(seed)
        self.tracks = {}

    # ---------------------------------------------------------- geometry
    def lane_x(self, i):
        """Centre of lane i (0 = left lane), right of the median centre line."""
        return 2.75 + LANE * (i + 0.5)

    def shoulder_x(self):
        return self.x_end + 0.3 + (self.x_sh - self.x_end - 0.3) / 2

    def carriageways(self):
        r, M, c, s0, s1 = self.road, self.M, self.env, self.s0, self.s1
        sp = SPEC[self.cc]
        for side in (1, -1):
            sg = "R" if side == 1 else "L"
            r.strip(f"lanes{sg}", side * 2.0, side * (self.x_end + 0.15), s0, s1, M.asph, c)
            r.strip(f"shoulder{sg}", side * (self.x_end + 0.15), side * self.x_sh, s0, s1, M.asph_sh, c, dz0=-0.002)
            r.strip(f"bankett{sg}", side * self.x_sh, side * (self.x_sh + 1.5), s0, s1, M.gravel, c, dz0=-0.02,
                    dz1=-0.12)
            r.strip(f"edgeL{sg}", side * (2.75 - sp["ew"]), side * 2.75, s0, s1, M.paint, c, dz0=0.006)
            r.strip(f"edgeR{sg}", side * self.x_end, side * (self.x_end + sp["ew"]), s0, s1, M.paint, c, dz0=0.006)
            for k in range(1, self.lanes):
                r.dashes(f"dash{sg}{k}", side * (2.75 + LANE * k), sp["lw"], s0, s1, M.paint, c, dash=sp["dash"],
                         gap=sp["gap"])
            r.strip(f"verge{sg}", side * (self.x_sh + 1.5), side * (self.x_sh + 10.0), s0, s1, M.grass, c, step=4.0,
                    dz0=-0.12, dz1=-0.79)
        r.strip("median", -2.0, 2.0, s0, s1, M.grass, c, dz0=0.0)
        wb = [(0.0, 0.0), (0.03, 0.08), (0.0, 0.155), (0.03, 0.23), (0.0, 0.31)]
        for side in (1, -1):
            r.sweep("rail", [(side * (0.12 + dx), 0.45 + h) for dx, h in wb], s0, s1, M.steel, c, step=2.0)
            r.sweep("rail_back", [(side * 0.105, 0.45), (side * 0.105, 0.76)], s0, s1, M.steel_dark, c, step=4.0)
            # outer guardrail beyond the Bankett, beam facing the road
            xo = side * (self.x_sh + 1.25)
            r.sweep("rail_out", [(xo + side * -dx, 0.33 + h) for dx, h in wb], s0, s1, M.steel, c, step=2.0)
        post = TN.box("rail_post_src", self.lib, (0, 0, 0), (0.1, 0.1, 0.8), M.steel_dark)
        s = s0
        while s < s1:
            r.place(post, s, 0.0, 0.4, c=c, name="rp")
            r.place(post, s, self.x_sh + 1.35, 0.3, c=c, name="rpo")
            r.place(post, s + 1.0, -(self.x_sh + 1.35), 0.3, c=c, name="rpo")
            s += 4.0
        post.hide_render = True
        post.hide_viewport = True

    def dress(self, seed):
        r, M = self.road, self.M
        W.terrain(r, M, self.env)
        LP = W.leitpfosten(M, self.lib)
        RD = W.rail_delineator(M, self.lib)
        s = self.s0 + 10
        while s < self.s1:
            r.place(LP, s, self.x_sh + 0.5, -0.053, c=self.env, name="lp")
            r.place(LP, s + 25, -(self.x_sh + 0.5), -0.053, yaw=math.pi, c=self.env, name="lp")
            r.place(RD, s, 0.0, c=self.env, name="rd")
            s += 50.0
        groups = flora.library(self.lib)
        mid = (r.X[r.n // 2], r.Y[r.n // 2])
        flora.vegetation(r, groups, self.env, max(0.0, self.s0 - 40), self.s1, half=1500.0, center=mid, spacing=8.0,
                         seed=seed)

    def mountains(self, seed=3):
        """A ring of Alpine ridges 4.5 to 8 km out: forest-green foot, grey rock, snow above about 1,500 m (colour
        from height, no texture). The haze of stage.hazify_all fades them into the sky."""
        rnd = random.Random(seed)
        r = self.road
        cx, cy = r.X[r.n // 2], r.Y[r.n // 2]
        n, rows = 540, 7
        ph = [rnd.uniform(0, 6.3) for _ in range(6)]
        verts, faces = [], []
        for i in range(n):
            a = 2 * math.pi * i / n
            h = (1000 + 380 * math.sin(3 * a + ph[0]) + 260 * math.sin(7 * a + ph[1]) + 140 * math.sin(17 * a + ph[2])
                 + 80 * math.sin(41 * a + ph[3]) + 45 * math.sin(97 * a + ph[4]))
            R = 9500 + 1800 * math.sin(2 * a + ph[5])
            for j in range(rows):
                u = j / (rows - 1)
                rr = R + 3800 * (1 - u) + 160 * math.sin(53 * a + 9 * u)
                z = -30 + (h + 30) * (u ** 1.35) + (35 * math.sin(29 * a + 7 * j) if 0 < j < rows - 1 else 0)
                verts.append((cx + rr * math.cos(a), cy + rr * math.sin(a), z))
        for i in range(n):
            i2 = (i + 1) % n
            for j in range(rows - 1):
                faces.append((i * rows + j, i2 * rows + j, i2 * rows + j + 1, i * rows + j + 1))
        m = bpy.data.materials.new("mw_mountain")
        m.use_nodes = True
        nt = m.node_tree
        b = nt.nodes["Principled BSDF"]
        b.inputs["Roughness"].default_value = 0.9
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 0.002
        add = nt.nodes.new("ShaderNodeMath")
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation, mul.inputs[1].default_value = "MULTIPLY", 380.0
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.0, 1700.0
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        cr = ramp.color_ramp
        # colours carry their own aerial blue (the stage haze skips mw_ materials: at 10 km it would flatten them)
        cr.elements[0].position, cr.elements[0].color = 0.0, (0.1, 0.15, 0.16, 1)
        cr.elements[1].position, cr.elements[1].color = 0.74, (0.86, 0.9, 0.97, 1)
        for p, col in ((0.3, (0.13, 0.17, 0.19, 1)), (0.42, (0.27, 0.3, 0.36, 1)), (0.66, (0.36, 0.39, 0.45, 1))):
            e = cr.elements.new(p)
            e.color = col
        L = nt.links
        L.new(geo.outputs["Position"], sep.inputs[0])
        L.new(geo.outputs["Position"], nz.inputs["Vector"])
        L.new(nz.outputs["Fac"], mul.inputs[0])
        L.new(sep.outputs["Z"], add.inputs[0])
        L.new(mul.outputs[0], add.inputs[1])
        L.new(add.outputs[0], mr.inputs["Value"])
        L.new(mr.outputs["Result"], ramp.inputs["Fac"])
        L.new(ramp.outputs["Color"], b.inputs["Base Color"])
        W.mesh_obj("mw_mountains", verts, faces, m, self.env, smooth=True)

    # ---------------------------------------------------------- motion
    def track(self, keys_v, keys_x, n, s0, inds=(), beacon=None, rev=False):
        """Per-frame track for motion.bake. keys_v [(t, v m/s)] linear; keys_x [(t, lateral x)] smoothstep;
        inds [(t0, t1, "L" | "R" | "H")]; beacon (t0, t1) for blue lights. Stores the arc length per frame."""
        out, s, ss = [], s0, []
        prev_x = interp(keys_x, 0.0, True)
        for f in range(n):
            t = f / FPS
            v = interp(keys_v, t)
            x = interp(keys_x, t, True)
            c, th, fwd, right, _sl = self.road.frame(s)
            p = c + right * x
            dx = (x - prev_x) * FPS
            prev_x = x
            yaw = math.pi / 2 - th - math.atan2(dx, max(v, 0.5)) + (math.pi if rev else 0.0)
            ind = None
            for a, b, k in inds:
                if a <= t < b:
                    ind = k
            row = dict(x=p.x, y=p.y, z=p.z, yaw=yaw, v=v, ind=ind)
            if beacon:
                row["beacon"] = beacon[0] <= t < beacon[1]
            out.append(row)
            ss.append(s)
            s += (-v if rev else v) / FPS
        self.last_s = ss
        return out

    def traffic_flow(self, n, spec, rnd_seed=1):
        """Background cars: spec [(collection, lane index or -1 - index for the other carriageway, s0, v)]."""
        out = []
        for col, lane, s0, v in spec:
            if lane >= 0:
                trk = self.track([(0, v)], [(0, self.lane_x(lane))], n, s0)
            else:
                trk = self.track([(0, v)], [(0, -self.lane_x(-1 - lane))], n, s0, rev=True)
            out.append((self.drive(col, trk), trk))
        return out

    def drive(self, car, trk, night=False):
        """car: a jx.hero dict or a vehicle collection (instanced into traffic). Returns the rig."""
        if isinstance(car, dict):
            rg = motion.rig(car)
        else:
            inst = W.instance(car, (0, 0, 0), c=self.traffic)
            rg = motion.rig(inst)
        motion.bake(rg, trk, night=night)
        return rg

    @staticmethod
    def at(trk, t):
        r = trk[max(0, min(len(trk) - 1, int(round(t * FPS))))]
        return Vector((r["x"], r["y"], r["z"])), r["yaw"]

    def chase(self, trk, t, back=8.0, up=2.2, ahead=22.0, side=0.0, look_up=1.2):
        p, yaw = self.at(trk, t)
        f = Vector((math.cos(yaw), math.sin(yaw), 0))
        rgt = Vector((math.sin(yaw), -math.cos(yaw), 0))
        return p - f * back + rgt * side + Vector((0, 0, up)), p + f * ahead + Vector((0, 0, look_up))

    def pt(self, s, x, h=0.0):
        return self.road.point(s, x, h)

    def yaw_at(self, s):
        return math.pi / 2 - self.road.frame(s)[1]

    # ---------------------------------------------------------- props
    def sign(self, stack, s, x, set_=None, bottom=2.0):
        import signs as SG
        p = self.pt(s, x)
        return SG.assembly(stack, self.env, (p.x, p.y, p.z - 0.05), rz=-self.road.frame(s)[1], bottom=bottom,
                           set_=set_ or self.cc)

    def column(self, s, x=None, name="en_column"):
        """Grey fixed enforcement column (kit/enforcement.py, no brand) on the right verge; returns the device."""
        import enforcement as EN
        return EN.CameraColumn(self.road, self.env, s, x=x or (self.x_sh + 2.2), name=name)

    def police(self, name="police_generic"):
        """vehicles' police estate with every lettering removed (no POLIZEI, no emblem) and a blank plate: a
        generic silver car with a blue band and a blue roof bar."""
        col = V.car("estate", (0.75, 0.76, 0.78), name, "QX PO 11", police=True, c=self.lib)
        for o in list(col.all_objects):
            if o.name.startswith("polizei") or o.type == "FONT":
                bpy.data.objects.remove(o)
        CY.blank_plates([col])
        return col


def dash_set(c, loc, red_zone=False, wiper=False, name="dash"):
    """Instrument close-up (no numerals anywhere): a dark dashboard, a round speedometer with tick marks only (a red
    zone on request), a needle on a pivot, an amber warning lamp, a red hazard button, a small rain icon lamp and,
    with wiper=True, a sloped windscreen with a wiper arm. Faces -y; returns dict of the animated parts."""
    L = Vector(loc)
    dk = mat(name + "_dark", (0.025, 0.026, 0.03), 0.55)
    tick = mat(name + "_tick", (0.9, 0.9, 0.88), 0.4, emit=(0.9, 0.9, 0.88), estr=1.2)
    redm = mat(name + "_red", (0.8, 0.05, 0.03), 0.4, emit=(0.9, 0.05, 0.03), estr=1.5)
    ndl = mat(name + "_needle", (1.0, 0.25, 0.05), 0.3, emit=(1.0, 0.3, 0.05), estr=3.0)
    TN.box(name + "_board", c, tuple(L + Vector((0, 0.06, -0.02))), (0.9, 0.08, 0.36), dk, bevel=0.02)
    TN.box(name + "_hood", c, tuple(L + Vector((0, 0.0, 0.17))), (0.9, 0.2, 0.04), dk, bevel=0.015)
    CY.flat(c, name + "_dial", CY.disc_pts(0.095, 64), (0.012, 0.012, 0.015), loc=tuple(L + Vector((0, 0.015, 0))),
            emit=0.0)
    ring = CY.flat(c, name + "_ring", CY.disc_pts(0.1, 64), (0.5, 0.5, 0.52), loc=tuple(L + Vector((0, 0.016, 0))),
                   emit=0.1)
    for k in range(25):
        a = math.radians(210 - 240 * k / 24)
        r0, r1 = (0.072 if k % 4 == 0 else 0.08), 0.09
        col = (0.85, 0.06, 0.04) if (red_zone and k >= 19) else (0.9, 0.9, 0.88)
        CY.flat(c, f"{name}_tick{k}", CY.bar_pts(r0 * math.cos(a), r0 * math.sin(a), r1 * math.cos(a), r1 * math.sin(a),
                                                  0.006 if k % 4 else 0.009), col, loc=tuple(L + Vector((0, 0.013, 0))),
                emit=1.2)
    piv = bpy.data.objects.new(name + "_pivot", None)
    c.objects.link(piv)
    piv.location = L + Vector((0, 0.011, 0))
    CY.flat(c, name + "_ndl", CY.bar_pts(-0.012, 0, 0.082, 0, 0.005), (1.0, 0.3, 0.05), emit=3.0, parent=piv)
    CY.flat(c, name + "_hub", CY.disc_pts(0.011, 20), (0.05, 0.05, 0.05), emit=0.0, parent=piv, z=0.002)
    lamp = mat(name + "_lamp", (0.9, 0.5, 0.02), 0.4, emit=(1.0, 0.55, 0.02), estr=0.0)
    TN.box(name + "_lamp", c, tuple(L + Vector((0.16, 0.012, 0.05))), (0.035, 0.004, 0.025), lamp)
    haz = mat(name + "_haz", (0.7, 0.03, 0.02), 0.4, emit=(1.0, 0.1, 0.05), estr=0.0)
    hb = TN.box(name + "_hazbtn", c, tuple(L + Vector((0.0, -0.02, -0.14))), (0.06, 0.03, 0.035), haz, bevel=0.006)
    rain = mat(name + "_rain", (0.1, 0.5, 1.0), 0.4, emit=(0.2, 0.6, 1.0), estr=0.0)
    TN.box(name + "_rainlamp", c, tuple(L + Vector((-0.16, 0.012, 0.05))), (0.03, 0.004, 0.022), rain)
    out = dict(pivot=piv, lamp=lamp, haz=haz, hazbtn=hb, rain=rain, red=redm, tick=tick, needle=ndl, cam=L)
    if wiper:
        glass = bpy.data.materials.new(name + "_glass")
        glass.use_nodes = True
        gb = glass.node_tree.nodes["Principled BSDF"]
        gb.inputs["Base Color"].default_value = (0.6, 0.7, 0.75, 1)
        gb.inputs["Roughness"].default_value = 0.05
        gb.inputs["Alpha"].default_value = 0.18
        ws = TN.box(name + "_screen", c, tuple(L + Vector((0, 0.42, 0.32))), (1.4, 0.006, 0.7), glass)
        ws.rotation_euler = (math.radians(-35), 0, 0)
        wp = bpy.data.objects.new(name + "_wpivot", None)
        c.objects.link(wp)
        wp.location = L + Vector((-0.35, 0.33, 0.06))
        wp.rotation_euler = (math.radians(-35), 0, 0)
        arm = TN.box(name + "_wiper", c, (0.0, -0.01, 0.3), (0.014, 0.012, 0.62), mat(name + "_wblade", (0.02, 0.02,
                                                                                                         0.02), 0.6),
                     parent=wp)
        out.update(wpivot=wp, wiper=arm, screen=ws)
        drops = []
        rnd = random.Random(5)
        dm = mat(name + "_drop", (0.75, 0.8, 0.85), 0.02)
        for k in range(70):
            d = TN.box(f"{name}_drop{k}", c, (rnd.uniform(-0.6, 0.6), -0.006, rnd.uniform(-0.3, 0.3)),
                       (0.012, 0.004, 0.016), dm, parent=ws)
            drops.append(d)
        out["drops"] = drops
    return out


def needle(d, keys):
    """keys [(t, fraction 0..1 of the 240-degree arc)]: keys the needle (linear between keys)."""
    piv = d["pivot"]
    for t, u in keys:
        piv.rotation_euler = (0, -math.radians(210 - 240 * u), 0)
        piv.keyframe_insert("rotation_euler", frame=int(t * FPS) + 1)


def wipe(d, t0, t1, period=1.1):
    wp = d["wpivot"]
    t = t0
    wp.rotation_euler[1] = 0.0
    wp.keyframe_insert("rotation_euler", frame=int(t0 * FPS) + 1)
    while t < t1:
        for dt, ang in ((period / 2, -1.9), (period, 0.0)):
            wp.rotation_euler[1] = ang
            wp.keyframe_insert("rotation_euler", frame=int((t + dt) * FPS) + 1)
        t += period


def screen_builder(fn):
    """Wrap a phone screen builder fn(c, parent) for CY.phone."""
    return fn


def lock_icon(c, name, loc, size, color, parent=None, rot=(math.pi / 2, 0, 0)):
    g = bpy.data.objects.new(name, None)
    c.objects.link(g)
    g.location, g.rotation_euler, g.scale = loc, rot, (size, size, size)
    if parent:
        g.parent = parent
    # children lie in the empty's plane (rot 0): the empty carries the facing
    CY.flat(c, name + "_body", [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.15), (-0.5, 0.15)], color, emit=0.8, parent=g,
            rot=(0, 0, 0))
    pts = [(0.32 * math.cos(math.radians(a)), 0.15 + 0.38 * math.sin(math.radians(a))) for a in range(0, 181, 15)]
    inner = [(0.2 * math.cos(math.radians(a)), 0.15 + 0.26 * math.sin(math.radians(a))) for a in range(180, -1, -15)]
    CY.flat(c, name + "_shackle", pts + inner, color, emit=0.8, parent=g, rot=(0, 0, 0))
    return g


def rect(w, h, cx=0.0, cy=0.0):
    return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]


def tick_pts(s=1.0):
    return [CY.bar_pts(-0.6 * s, 0.05 * s, -0.15 * s, -0.45 * s, 0.26 * s), CY.bar_pts(-0.15 * s, -0.45 * s, 0.8 * s,
                                                                                         0.95 * s, 0.26 * s)]


def cross_pts(s=1.0):
    return [CY.bar_pts(-0.8 * s, -0.8 * s, 0.8 * s, 0.8 * s, 0.26 * s), CY.bar_pts(-0.8 * s, 0.8 * s, 0.8 * s, -0.8 * s,
                                                                                    0.26 * s)]


def badge(c, name, kind, loc, size=1.0, parent=None, rot=(math.pi / 2, 0, 0)):
    """Round white disc with a green tick ('yes') or a red cross ('no')."""
    g = bpy.data.objects.new(name, None)
    c.objects.link(g)
    g.location, g.rotation_euler, g.scale = loc, rot, (size, size, size)
    if parent:
        g.parent = parent
    CY.flat(c, name + "_disc", CY.disc_pts(1.2, 40), (0.97, 0.97, 0.95), emit=0.6, parent=g, z=-0.01, rot=(0, 0, 0))
    col = (0.1, 0.75, 0.2) if kind == "yes" else (0.9, 0.05, 0.05)
    for k, p in enumerate(tick_pts(1.0) if kind == "yes" else cross_pts(0.75)):
        CY.flat(c, f"{name}_m{k}", p, col, emit=1.2, parent=g, z=0.01, rot=(0, 0, 0))
    return g


def finish(shots, OUT, todo, N, haze=(0.7, 0.76, 0.86), haze_dist=2400.0, first="", skip_prefix=()):
    """Scene frame range, first camera, haze (haze=None leaves it to weather.apply), render loop."""
    sc = bpy.context.scene
    for o in bpy.data.objects:              # the Alpine ridges stand 9 to 13 km out (stage.camera clips at 6 km)
        if o.type == "CAMERA" and o.data.type != "ORTHO":
            o.data.clip_end = max(o.data.clip_end, 16000.0)
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, N
    if first:
        sc.camera = bpy.data.objects[first]
    if haze is None:
        jx.render_frames(shots, OUT, todo)
        return
    stage.hazify_all(color=haze, dist=haze_dist,
                     skip=[m.name for m in bpy.data.materials if m.name.startswith(
                         ("phone", "sign_", "dash", "ic_", "cal_", "end_", "kiosk", "lt_", "mw_")) or
                           m.name.endswith("_m") or any(m.name.startswith(p) for p in skip_prefix)])
    jx.render_frames(shots, OUT, todo)


def cli(argv):
    """The episode CLI: OUT --frames a-b | --stills a,b --res --samples --assets."""
    OUT, RES, SAMPLES, ASSETS, FR, STILLS = "frames", 540, 8, "assets", None, None
    for i, x in enumerate(argv):
        if i == 1 and not x.startswith("--"):
            OUT = x
        if x == "--res":
            RES = int(argv[i + 1])
        if x == "--samples":
            SAMPLES = int(argv[i + 1])
        if x == "--assets":
            ASSETS = argv[i + 1]
        if x == "--frames":
            p, q = argv[i + 1].split("-")
            FR = (int(p), int(q))
        if x == "--stills":
            STILLS = [int(v) for v in argv[i + 1].split(",")]
    return OUT, RES, SAMPLES, ASSETS, FR, STILLS


def render(shots, OUT, RES, SAMPLES, FR, STILLS, N, **kw):
    stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
    todo = STILLS or list(range(FR[0], FR[1] + 1) if FR else range(1, N + 1))
    finish(shots, OUT, todo, N, **kw)
