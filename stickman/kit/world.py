"""Stylised German Autobahn world kit for the "Drive like a local" series.

Clearly cartoon, but built to the real specs (RAA/RMS, StVO sign catalogue):
- cross-section (one carriageway, metres from the motorway centre line, positive = right of our direction):
  median 0..2 (double guardrail at 0), left paved strip 2.0..2.75, three lanes of 3.75 m (2.75..14.0),
  hard shoulder 14.0..16.8, gravel verge (Bankett) 16.8..18.3, delineator posts 0.5 m beyond the paved edge.
- markings: edge lines 0.30 m solid (Breitstrich), lane lines 0.15 m, 6 m dash / 12 m gap.
- delineator posts (Leitpfosten, Zeichen 620): 1.0 m, triangular, slanted top towards the road, 25 cm black band
  parallel to the top, one white rectangular reflector facing traffic, every 50 m, right side only.
- sign font: u_DIN 1451 Mittelschrift (OFL), the face of German road signs.
The road follows an analytic curve (gentle bends and crests); everything is placed with road coordinates (s, x).
"""
import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector, kdtree, noise

PREF = bpy.context.preferences.edit
SIGN_FONT = None


def setup(assets, fonts):
    global SIGN_FONT, ASSETS
    ASSETS = assets
    SIGN_FONT = bpy.data.fonts.load(os.path.join(assets, "fonts", "udin", "uDIN1451Mittelschrift.ttf"),
                                    check_existing=True)


# ------------------------------------------------------------------ helpers
def coll(name, parent=None, hide=False):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    if hide:
        c.hide_render = True
        c.hide_viewport = True
    return c


def link(o, c):
    for u in list(o.users_collection):
        u.objects.unlink(o)
    c.objects.link(o)
    return o


def mesh_obj(name, verts, faces, mat, c, uvs=None, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    if uvs is not None:
        uvl = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li, vi in zip(poly.loop_indices, poly.vertices):
                uvl.data[li].uv = uvs[vi]
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    me.validate()
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    if mat:
        o.data.materials.append(mat)
    return o


def principled(name, color, rough=0.5, metal=0.0, emit=None, estr=0.0, coat=0.0, spec=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    p.inputs["Coat Weight"].default_value = coat
    p.inputs["Specular IOR Level"].default_value = spec
    if emit:
        p.inputs["Emission Color"].default_value = (*emit, 1)
        p.inputs["Emission Strength"].default_value = estr
    return m


def noisy(name, c1, c2, scale, rough=0.7, detail=3.0, coord="Object", bump=0.0, rough2=None):
    """Two-colour stylised material driven by noise."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = detail
    nt.links.new(tc.outputs[coord], nz.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (*c1, 1)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = (*c2, 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = rough
    if rough2 is not None:
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = rough
        mr.inputs["To Max"].default_value = rough2
        nt.links.new(nz.outputs["Fac"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], p.inputs["Roughness"])
    if bump:
        bn = nt.nodes.new("ShaderNodeBump")
        bn.inputs["Strength"].default_value = bump
        nz2 = nt.nodes.new("ShaderNodeTexNoise")
        nz2.inputs["Scale"].default_value = scale * 40
        nt.links.new(tc.outputs[coord], nz2.inputs["Vector"])
        nt.links.new(nz2.outputs["Fac"], bn.inputs["Height"])
        nt.links.new(bn.outputs["Normal"], p.inputs["Normal"])
    return m


def asphalt(name, base=(0.03, 0.032, 0.035), tracks=True):
    """Dark Autobahn asphalt: fine grain, darker smoother wheel tracks (UV u = lateral metres, v = along)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs["Vector"])
    grain = nt.nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 3.0
    grain.inputs["Detail"].default_value = 8.0
    nt.links.new(tc.outputs["UV"], grain.inputs["Vector"])
    patch = nt.nodes.new("ShaderNodeTexNoise")
    patch.inputs["Scale"].default_value = 0.04
    nt.links.new(tc.outputs["UV"], patch.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.3
    ramp.color_ramp.elements[0].color = (base[0] * 0.8, base[1] * 0.8, base[2] * 0.8, 1)
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[1].color = (base[0] * 1.35, base[1] * 1.35, base[2] * 1.35, 1)
    mixn = nt.nodes.new("ShaderNodeMath")
    mixn.operation = "MULTIPLY_ADD"
    mixn.inputs[1].default_value = 0.6
    nt.links.new(grain.outputs["Fac"], mixn.inputs[0])
    pm = nt.nodes.new("ShaderNodeMath")
    pm.operation = "MULTIPLY"
    pm.inputs[1].default_value = 0.4
    nt.links.new(patch.outputs["Fac"], pm.inputs[0])
    nt.links.new(pm.outputs["Value"], mixn.inputs[2])
    nt.links.new(mixn.outputs["Value"], ramp.inputs["Fac"])
    col = ramp.outputs["Color"]
    rough_out = None
    if tracks:
        # tracks: cos peaks every 1.875 m, offset so the peaks sit 0.94 m either side of each lane centre
        sub = nt.nodes.new("ShaderNodeMath")
        sub.operation = "SUBTRACT"
        sub.inputs[1].default_value = 4.625 - 0.9375
        nt.links.new(sep.outputs["X"], sub.inputs[0])
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = 2 * math.pi / 1.875
        nt.links.new(sub.outputs["Value"], mul.inputs[0])
        cs = nt.nodes.new("ShaderNodeMath")
        cs.operation = "COSINE"
        nt.links.new(mul.outputs["Value"], cs.inputs[0])
        half = nt.nodes.new("ShaderNodeMath")
        half.operation = "MULTIPLY_ADD"
        half.inputs[1].default_value = 0.5
        half.inputs[2].default_value = 0.5
        nt.links.new(cs.outputs["Value"], half.inputs[0])
        pw = nt.nodes.new("ShaderNodeMath")
        pw.operation = "POWER"
        pw.inputs[1].default_value = 8.0
        nt.links.new(half.outputs["Value"], pw.inputs[0])
        # only on the lanes (2.75 .. 14.0)
        lo = nt.nodes.new("ShaderNodeMath")
        lo.operation = "GREATER_THAN"
        lo.inputs[1].default_value = 2.75
        nt.links.new(sep.outputs["X"], lo.inputs[0])
        hi = nt.nodes.new("ShaderNodeMath")
        hi.operation = "LESS_THAN"
        hi.inputs[1].default_value = 14.0
        nt.links.new(sep.outputs["X"], hi.inputs[0])
        m1 = nt.nodes.new("ShaderNodeMath")
        m1.operation = "MULTIPLY"
        nt.links.new(lo.outputs["Value"], m1.inputs[0])
        nt.links.new(hi.outputs["Value"], m1.inputs[1])
        m2 = nt.nodes.new("ShaderNodeMath")
        m2.operation = "MULTIPLY"
        nt.links.new(pw.outputs["Value"], m2.inputs[0])
        nt.links.new(m1.outputs["Value"], m2.inputs[1])
        mixc = nt.nodes.new("ShaderNodeMix")
        mixc.data_type = "RGBA"
        mixc.blend_type = "MULTIPLY"
        mixc.inputs["B"].default_value = (0.72, 0.72, 0.72, 1)
        nt.links.new(m2.outputs["Value"], mixc.inputs["Factor"])
        nt.links.new(col, mixc.inputs["A"])
        col = mixc.outputs["Result"]
        rr = nt.nodes.new("ShaderNodeMapRange")
        rr.inputs["To Min"].default_value = 0.78
        rr.inputs["To Max"].default_value = 0.55
        nt.links.new(m2.outputs["Value"], rr.inputs["Value"])
        rough_out = rr.outputs["Result"]
    # repair patches: long rectangles of fresher, darker asphalt here and there
    mp_ = nt.nodes.new("ShaderNodeMapping")
    mp_.inputs["Scale"].default_value = (0.26, 0.045, 1.0)
    nt.links.new(tc.outputs["UV"], mp_.inputs["Vector"])
    vo = nt.nodes.new("ShaderNodeTexVoronoi")
    nt.links.new(mp_.outputs["Vector"], vo.inputs["Vector"])
    sp = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(vo.outputs["Color"], sp.inputs["Color"])
    gt = nt.nodes.new("ShaderNodeMath")
    gt.operation = "GREATER_THAN"
    gt.inputs[1].default_value = 0.88
    nt.links.new(sp.outputs[0], gt.inputs[0])
    pmix = nt.nodes.new("ShaderNodeMix")
    pmix.data_type = "RGBA"
    pmix.blend_type = "MULTIPLY"
    pmix.inputs["B"].default_value = (0.7, 0.7, 0.72, 1)
    nt.links.new(gt.outputs[0], pmix.inputs["Factor"])
    nt.links.new(col, pmix.inputs["A"])
    col = pmix.outputs["Result"]
    nt.links.new(col, p.inputs["Base Color"])
    if rough_out:
        nt.links.new(rough_out, p.inputs["Roughness"])
    else:
        p.inputs["Roughness"].default_value = 0.8
    bn = nt.nodes.new("ShaderNodeBump")
    bn.inputs["Strength"].default_value = 0.15
    nt.links.new(grain.outputs["Fac"], bn.inputs["Height"])
    nt.links.new(bn.outputs["Normal"], p.inputs["Normal"])
    return m


def text_obj(name, body, size, mat, c, align="LEFT", valign="CENTER", extrude=0.0, font=None):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.font = font or SIGN_FONT
    cu.size = size
    cu.align_x = align
    cu.align_y = valign
    cu.extrude = extrude
    o = bpy.data.objects.new(name, cu)
    c.objects.link(o)
    o.data.materials.append(mat)
    return o


def rounded_rect(w, h, r, seg=8):
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180),
                       (w / 2 - r, -h / 2 + r, 270)):
        for k in range(seg + 1):
            a = math.radians(a0 + 90 * k / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def plate(name, outline, depth, mat, c, z_off=0.0):
    """Flat plate in the XZ plane facing -Y (towards drivers when the sign stands across +Y travel)."""
    n = len(outline)
    verts = [(x, -z_off, y) for x, y in outline] + [(x, -z_off + depth, y) for x, y in outline]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    return mesh_obj(name, verts, faces, mat, c)


def disc(name, r, depth, mat, c, z_off=0.0, seg=64):
    return plate(name, [(r * math.cos(2 * math.pi * k / seg), r * math.sin(2 * math.pi * k / seg)) for k in range(seg)],
                 depth, mat, c, z_off)


def ring(name, r0, r1, mat, c, z_off=0.0, seg=64):
    verts, faces = [], []
    for k in range(seg):
        a = 2 * math.pi * k / seg
        verts += [(r0 * math.cos(a), -z_off, r0 * math.sin(a)), (r1 * math.cos(a), -z_off, r1 * math.sin(a))]
    for k in range(seg):
        a, b = 2 * k, 2 * ((k + 1) % seg)
        faces.append((a, b, b + 1, a + 1))
    return mesh_obj(name, verts, faces, mat, c)


# ------------------------------------------------------------------ the road path
class Road:
    def __init__(self, length=2400.0, ds=1.0, bends=((350, 950, 1 / 1800.0), (1250, 1900, -1 / 2200.0)),
                 crest=((0, 1400, 4.5), (900, 2600, 3.0)), origin=(0, 0, 0)):
        self.L, self.ds = length, ds
        n = int(length / ds) + 1
        self.n = n
        th, x, y = 0.0, origin[0], origin[1]
        self.X, self.Y, self.Z, self.T = [], [], [], []
        for i in range(n):
            s = i * ds
            k = 0.0
            for a, b, kmax in bends:  # smooth curvature bumps (clothoid-like in and out)
                if a < s < b:
                    u = (s - a) / (b - a)
                    k += kmax * math.sin(math.pi * u) ** 2
            z = origin[2]
            for a, b, h in crest:
                if a < s < b:
                    u = (s - a) / (b - a)
                    z += h * math.sin(math.pi * u) ** 2
            self.X.append(x)
            self.Y.append(y)
            self.Z.append(z)
            self.T.append(th)
            x += math.sin(th) * ds
            y += math.cos(th) * ds
            th += k * ds
        kd = kdtree.KDTree(n)
        for i in range(n):
            kd.insert((self.X[i], self.Y[i], 0), i)
        kd.balance()
        self.kd = kd

    def _i(self, s):
        f = max(0.0, min(self.L, s)) / self.ds
        i = min(int(f), self.n - 2)
        return i, f - i

    def frame(self, s):
        i, t = self._i(s)
        lerp = lambda A: A[i] + (A[i + 1] - A[i]) * t  # noqa: E731
        th = lerp(self.T)
        c = Vector((lerp(self.X), lerp(self.Y), lerp(self.Z)))
        fwd = Vector((math.sin(th), math.cos(th), 0))
        right = Vector((math.cos(th), -math.sin(th), 0))
        slope = (self.Z[i + 1] - self.Z[i]) / self.ds
        return c, th, fwd, right, slope

    def point(self, s, x, h=0.0):
        c, th, f, r, sl = self.frame(s)
        return c + r * x + Vector((0, 0, h))

    def matrix(self, s, x, h=0.0, yaw=0.0):
        c, th, f, r, sl = self.frame(s)
        p = c + r * x + Vector((0, 0, h))
        rot = Matrix.Rotation(-th + yaw, 4, "Z") @ Matrix.Rotation(math.atan(sl), 4, "X")
        return Matrix.Translation(p) @ rot

    def nearest(self, x, y):
        co, i, d = self.kd.find((x, y, 0))
        return i * self.ds, d, self.Z[i]

    # ---- geometry along the road
    def strip(self, name, x0, x1, s0, s1, mat, c, step=2.0, dz0=0.0, dz1=None):
        dz1 = dz0 if dz1 is None else dz1
        verts, faces, uvs = [], [], []
        k = 0
        s = s0
        while True:
            verts += [tuple(self.point(s, x0, dz0)), tuple(self.point(s, x1, dz1))]
            uvs += [(abs(x0), s), (abs(x1), s)]
            if k:
                a = 2 * (k - 1)
                faces.append((a, a + 1, a + 3, a + 2) if x1 > x0 else (a, a + 2, a + 3, a + 1))
            k += 1
            if s >= s1:
                break
            s = min(s1, s + step)
        return mesh_obj(name, verts, faces, mat, c, uvs)

    def dashes(self, name, x, w, s0, s1, mat, c, dash=6.0, gap=12.0, dz=0.006):
        verts, faces, uvs = [], [], []
        s = s0
        while s < s1:
            e = min(s + dash, s1)
            base = len(verts)
            for ss in (s, (s + e) / 2, e):
                verts += [tuple(self.point(ss, x - w / 2, dz)), tuple(self.point(ss, x + w / 2, dz))]
                uvs += [(abs(x - w / 2), ss), (abs(x + w / 2), ss)]
            for j in range(2):
                a = base + 2 * j
                faces.append((a, a + 1, a + 3, a + 2))
            s += dash + gap
        return mesh_obj(name, verts, faces, mat, c, uvs)

    def sweep(self, name, profile, s0, s1, mat, c, step=2.0, closed=False):
        """profile: [(x, h)] in road coordinates, swept along s."""
        verts, faces = [], []
        m = len(profile)
        k = 0
        s = s0
        while True:
            for px, ph in profile:
                verts.append(tuple(self.point(s, px, ph)))
            if k:
                a, b = (k - 1) * m, k * m
                for j in range(m - (0 if closed else 1)):
                    j2 = (j + 1) % m
                    faces.append((a + j, a + j2, b + j2, b + j))
            k += 1
            if s >= s1:
                break
            s = min(s1, s + step)
        return mesh_obj(name, verts, faces, mat, c, smooth=False)

    def place(self, obj_or_coll, s, x, h=0.0, yaw=0.0, scale=1.0, c=None, name="inst"):
        if isinstance(obj_or_coll, bpy.types.Collection):
            e = bpy.data.objects.new(name, None)
            e.instance_type = "COLLECTION"
            e.instance_collection = obj_or_coll
        else:
            e = obj_or_coll.copy()
        (c or bpy.context.scene.collection).objects.link(e)
        e.matrix_world = self.matrix(s, x, h, yaw) @ Matrix.Scale(scale, 4)
        return e


# ------------------------------------------------------------------ materials (shared)
class Mats:
    def __init__(self):
        self.asph = asphalt("asphalt")
        self.asph_sh = asphalt("asphalt_shoulder", base=(0.042, 0.043, 0.045), tracks=False)
        self.paint = noisy("paint", (0.78, 0.78, 0.75), (0.9, 0.9, 0.87), 6.0, rough=0.42, coord="UV")
        self.gravel = noisy("gravel", (0.12, 0.13, 0.09), (0.24, 0.23, 0.19), 18.0, rough=0.95, bump=0.25)
        self.grass = noisy("grass", (0.12, 0.27, 0.05), (0.22, 0.4, 0.09), 0.15, rough=0.9, detail=5)
        self.steel = principled("steel", (0.62, 0.64, 0.66), 0.32, metal=0.9)
        self.steel_dark = principled("steel_dark", (0.42, 0.44, 0.46), 0.4, metal=0.85)
        self.white = principled("post_white", (0.92, 0.92, 0.9), 0.35)
        self.black = principled("black", (0.015, 0.015, 0.015), 0.5)
        self.refl = principled("reflector", (1, 1, 1), 0.08, emit=(1, 1, 1), estr=0.35, spec=1.0)
        self.refl_amber = principled("reflector_amber", (1, 0.55, 0.05), 0.1, emit=(1, 0.5, 0.05), estr=1.0)
        self.sblue = principled("sign_blue", (0.002, 0.04, 0.17), 0.4)        # RAL 5017
        self.swhite = principled("sign_white", (0.88, 0.88, 0.88), 0.35, emit=(1, 1, 1), estr=0.08)
        self.sred = principled("sign_red", (0.6, 0.004, 0.003), 0.35)          # RAL 3020
        self.sblack = principled("sign_black", (0.01, 0.01, 0.01), 0.4)
        self.sgreen = principled("sign_green", (0.0, 0.16, 0.05), 0.4)         # E-route green
        self.sback = principled("sign_back", (0.45, 0.46, 0.47), 0.5, metal=0.6)
        self.concrete = noisy("concrete", (0.45, 0.45, 0.43), (0.6, 0.6, 0.57), 0.6, rough=0.85, bump=0.2)
        self.orange = principled("phone_orange", (0.9, 0.3, 0.02), 0.45)


# ------------------------------------------------------------------ build the motorway
def build_motorway(road, M, c, s0, s1):
    """Both carriageways between s0 and s1."""
    for side in (1, -1):
        def X(x):
            return x * side

        sg = "R" if side == 1 else "L"
        # paved: left strip + lanes, shoulder separate (slightly lighter, older surface)
        road.strip(f"lanes{sg}", X(2.0), X(14.15), s0, s1, M.asph, c)
        road.strip(f"shoulder{sg}", X(14.15), X(16.8), s0, s1, M.asph_sh, c, dz0=-0.002)
        road.strip(f"bankett{sg}", X(16.8), X(18.3), s0, s1, M.gravel, c, dz0=-0.02, dz1=-0.12)
        # markings
        road.strip(f"edgeL{sg}", X(2.45), X(2.75), s0, s1, M.paint, c, dz0=0.006)
        road.strip(f"edgeR{sg}", X(14.0), X(14.3), s0, s1, M.paint, c, dz0=0.006)
        for x in (6.5, 10.25):
            road.dashes(f"dash{sg}{x}", X(x), 0.15, s0, s1, M.paint, c)
    road.strip("median", -2.0, 2.0, s0, s1, M.grass, c, dz0=0.0)
    # double W-beam guardrail in the median: posts every 2 m, beams on both faces
    w = [(0.0, 0.0), (0.03, 0.08), (0.0, 0.155), (0.03, 0.23), (0.0, 0.31)]
    for side in (1, -1):
        prof = [(side * (0.12 + dx), 0.45 + h) for dx, h in w]
        road.sweep("rail", prof, s0, s1, M.steel, c, step=2.0)
        road.sweep("rail_back", [(side * 0.105, 0.45), (side * 0.105, 0.76)], s0, s1, M.steel_dark, c, step=4.0)
    bpy.ops.mesh.primitive_cube_add()
    post = link(bpy.context.active_object, c)
    post.name = "rail_post"
    post.scale = (0.05, 0.05, 0.4)
    bpy.ops.object.transform_apply(scale=True)
    post.location = (0, 0, 0.4)
    bpy.ops.object.transform_apply(location=True)
    post.data.materials.append(M.steel_dark)
    s = s0
    while s < s1:
        road.place(post, s, 0.0, c=c)
        s += 2.0
    bpy.data.objects.remove(post)


def leitpfosten(M, c):
    """Zeichen 620 for the right-hand side: 1.0 m white post, triangular section (flat face to traffic, which arrives
    from -y), top slanted down towards the road (road is at -x), 25 cm black band parallel to the top, one white
    rectangular reflector in the band."""
    tri = [(-0.06, -0.035), (0.06, -0.035), (0.0, 0.07)]

    def top(x):
        return 0.96 + (x / 0.06) * 0.04

    def prism(name, z0f, z1f, mat, k=1.0):
        verts = [(x * k, y * k, z0f(x)) for x, y in tri] + [(x * k, y * k, z1f(x)) for x, y in tri]
        faces = [(2, 1, 0), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)]
        return mesh_obj(name, verts, faces, mat, root)

    root = bpy.data.collections.new("leitpfosten")
    c.children.link(root)
    prism("lp_body", lambda x: 0.0, top, M.white)
    prism("lp_band", lambda x: top(x) - 0.31, lambda x: top(x) - 0.06, M.black, 1.03)
    r = [(-0.024, -0.0375, 0.705), (0.024, -0.0375, 0.705), (0.024, -0.0375, 0.845), (-0.024, -0.0375, 0.845)]
    mesh_obj("lp_refl", r, [(0, 1, 2, 3)], M.refl, root)
    return root


def rail_delineator(M, c):
    """Reflector cap on the median guardrail post: white, two round reflectors each way (left-side pattern)."""
    root = bpy.data.collections.new("rail_delin")
    c.children.link(root)
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0.92))
    o = link(bpy.context.active_object, root)
    o.scale = (0.05, 0.04, 0.16)
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(M.white)
    for yy, sgn in ((-0.041, -1), (0.041, 1)):
        for z in (0.88, 0.98):
            bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.017, depth=0.004, location=(0, yy, z),
                                                rotation=(math.pi / 2, 0, 0))
            r = link(bpy.context.active_object, root)
            r.data.materials.append(M.refl)
    return root


def sign_post(M, c, h, r=0.038):
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=r, depth=h, location=(0, 0.05, h / 2))
    p = link(bpy.context.active_object, c)
    p.data.materials.append(M.steel)
    return p


def sign_282(M, c, d=0.9, height=2.2):
    """Ende saemtlicher Streckenverbote: white disc, thin black rim, five thin black diagonal lines (up to the right)."""
    root = bpy.data.collections.new("sign282")
    c.children.link(root)
    r = d / 2
    g = bpy.data.objects.new("s282", None)
    root.objects.link(g)
    parts = [disc("s282_white", r, 0.01, M.swhite, root), ring("s282_rim", r * 0.955, r, M.sblack, root, 0.001),
             disc("s282_back", r, 0.004, M.sback, root, -0.012)]
    for k in range(5):
        off = (k - 2) * r * 0.105
        L_ = math.sqrt(max(0.0, (r * 0.93) ** 2 - off ** 2)) * 2 * 0.93
        wdt = r * 0.035
        pts = [(-L_ / 2, -wdt / 2), (L_ / 2, -wdt / 2), (L_ / 2, wdt / 2), (-L_ / 2, wdt / 2)]
        rot = math.radians(45)
        pts = [(x * math.cos(rot) - (y + off) * math.sin(rot), x * math.sin(rot) + (y + off) * math.cos(rot))
               for x, y in pts]
        parts.append(plate("s282_line", pts, 0.001, M.sblack, root, 0.0015))
    for p in parts:
        p.parent = g
        p.location.z += height
    sign_post(M, root, height).parent = g
    return root


def sign_274(M, c, value="120", d=0.9, height=2.2):
    root = bpy.data.collections.new(f"sign274_{value}")
    c.children.link(root)
    r = d / 2
    g = bpy.data.objects.new("s274", None)
    root.objects.link(g)
    parts = [disc("s274_white", r, 0.01, M.swhite, root), ring("s274_red", r * 0.8, r, M.sred, root, 0.001),
             disc("s274_back", r, 0.004, M.sback, root, -0.012)]
    t = text_obj("s274_txt", value, r * 0.78, M.sblack, root, "CENTER", "CENTER", 0.001)
    t.rotation_euler = (math.radians(90), 0, 0)
    t.location = (0, -0.0035, 0)
    t.scale = (0.82 if len(value) == 3 else 1.0, 1, 1)
    parts.append(t)
    for p in parts:
        p.parent = g
        p.location.z += height
    sign_post(M, root, height).parent = g
    return root


def a_shield(M, c, text, x, z, h=0.5, green=False):
    """Autobahn number shield (white on blue, white border) or E-route shield (white on green)."""
    w = 0.42 * h * (len(text) + 0.6)
    b = plate("shield_b", rounded_rect(w, h, h * 0.18), 0.004, M.swhite, c, 0.003)
    f = plate("shield_f", rounded_rect(w - 0.06, h - 0.06, h * 0.15), 0.004, M.sgreen if green else M.sblue, c, 0.006)
    t = text_obj("shield_t", text, h * 0.72, M.swhite, c, "CENTER", "CENTER", 0.001)
    t.rotation_euler = (math.radians(90), 0, 0)
    for o, dy in ((b, 0), (f, 0), (t, -0.0075)):
        o.location = (x, dy, z)
    return [b, f, t], w


def gantry(M, c, span_x0, span_x1, panels):
    """Overhead sign bridge. panels: list of dicts {x0, x1, z0, z1, lines:[(text, size, x, z)], shields:[(text, x, z,
    green)], arrows:[x]} in local coordinates (x across the road, z up, sign face towards -y)."""
    root = bpy.data.collections.new("gantry")
    c.children.link(root)
    g = bpy.data.objects.new("gantry", None)
    root.objects.link(g)
    objs = []
    for x in (span_x0, span_x1):
        bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.25, depth=8.2, location=(x, 0.4, 4.1))
        o = link(bpy.context.active_object, root)
        o.data.materials.append(M.steel)
        objs.append(o)
    for z in (7.2, 8.0):  # truss chords
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.09, depth=span_x1 - span_x0,
                                            location=((span_x0 + span_x1) / 2, 0.4, z), rotation=(0, math.pi / 2, 0))
        o = link(bpy.context.active_object, root)
        o.data.materials.append(M.steel)
        objs.append(o)
    k = 0
    x = span_x0
    while x < span_x1 - 0.5:  # diagonals
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.04, depth=1.13, location=(x + 0.4, 0.4, 7.6),
                                            rotation=(0, math.radians(45 if k % 2 else -45), 0))
        o = link(bpy.context.active_object, root)
        o.data.materials.append(M.steel)
        objs.append(o)
        x += 0.8
        k += 1
    for p in panels:
        x0, x1, z0, z1 = p["x0"], p["x1"], p["z0"], p["z1"]
        objs.append(plate("panel_border", rounded_rect(x1 - x0, z1 - z0, 0.12), 0.06, M.swhite, root, 0.0))
        objs[-1].location = ((x0 + x1) / 2, 0, (z0 + z1) / 2)
        objs.append(plate("panel_face", rounded_rect(x1 - x0 - 0.16, z1 - z0 - 0.16, 0.09), 0.004, M.sblue, root,
                          0.004))
        objs[-1].location = ((x0 + x1) / 2, 0, (z0 + z1) / 2)
        objs.append(plate("panel_back", rounded_rect(x1 - x0, z1 - z0, 0.12), 0.004, M.sback, root, -0.064))
        objs[-1].location = ((x0 + x1) / 2, 0, (z0 + z1) / 2)
        for body, size, tx, tz in p.get("lines", []):
            t = text_obj("panel_txt", body, size, M.swhite, root, "LEFT", "CENTER", 0.001)
            t.rotation_euler = (math.radians(90), 0, 0)
            t.location = (tx, -0.009, tz)
            objs.append(t)
        for body, sx, sz, green in p.get("shields", []):
            parts, _w = a_shield(M, root, body, sx, sz, 0.55, green)
            for o in parts:
                o.location.y -= 0.004
            objs += parts
        for ax in p.get("arrows", []):  # German lane arrow pointing down
            s_ = 0.62
            pts = [(-0.07, 0.45), (0.07, 0.45), (0.07, -0.05), (0.2, -0.05), (0.0, -0.32), (-0.2, -0.05),
                   (-0.07, -0.05)]
            a_ = plate("arrow", [(ax + x * s_ / 0.62, z0 + 0.62 + y * s_ / 0.62) for x, y in pts], 0.001, M.swhite, root,
                       0.009)
            objs.append(a_)
    for o in objs:
        if o.parent is None:
            o.parent = g
    return root


def rest_area_sign(M, c, dist="25 km", name_="Rastanlage", height=1.9):
    """Roadside blue sign: fuel pump, cutlery and WC pictograms, name and distance."""
    root = bpy.data.collections.new("restsign")
    c.children.link(root)
    g = bpy.data.objects.new("restsign", None)
    root.objects.link(g)
    W, H = 2.6, 1.5
    objs = [plate("rs_border", rounded_rect(W, H, 0.08), 0.04, M.swhite, root, 0.0),
            plate("rs_face", rounded_rect(W - 0.1, H - 0.1, 0.06), 0.004, M.sblue, root, 0.004)]
    # three white pictogram tiles
    for k, kind in enumerate(("fuel", "food", "wc")):
        cx = -W / 2 + 0.38 + k * 0.62
        objs.append(plate("rs_tile", rounded_rect(0.52, 0.52, 0.04), 0.002, M.swhite, root, 0.006))
        objs[-1].location = (cx, 0, 0.28)
        if kind == "fuel":
            pts = [(-0.12, -0.17), (0.07, -0.17), (0.07, 0.17), (-0.12, 0.17)]
            objs.append(plate("rs_pump", [(cx + x, 0.28 + y) for x, y in pts], 0.001, M.sblack, root, 0.008))
            objs.append(plate("rs_hose", [(cx + x, 0.28 + y) for x, y in
                                          ((0.09, 0.08), (0.15, 0.04), (0.15, -0.12), (0.12, -0.12), (0.12, 0.02),
                                           (0.08, 0.05))], 0.001, M.sblack, root, 0.008))
        elif kind == "food":
            for dx in (-0.07, 0.07):
                objs.append(plate("rs_cut", [(cx + dx + x, 0.28 + y) for x, y in
                                             ((-0.018, -0.18), (0.018, -0.18), (0.018, 0.18), (-0.018, 0.18))],
                                  0.001, M.sblack, root, 0.008))
        else:
            t = text_obj("rs_wc", "WC", 0.24, M.sblack, root, "CENTER", "CENTER", 0.001)
            t.rotation_euler = (math.radians(90), 0, 0)
            t.location = (cx, -0.009, 0.28)
            objs.append(t)
    for body, size, z in ((name_, 0.28, -0.22), (dist, 0.36, -0.52)):
        t = text_obj("rs_txt", body, size, M.swhite, root, "LEFT", "CENTER", 0.001)
        t.rotation_euler = (math.radians(90), 0, 0)
        t.location = (-W / 2 + 0.18, -0.009, z)
        objs.append(t)
    for o in objs:
        o.parent = g
        o.location.z += height + H / 2
    for x in (-0.9, 0.9):
        p = sign_post(M, root, height + 0.4)
        p.location.x = x
        p.parent = g
    return root


def emergency_phone(M, c):
    root = bpy.data.collections.new("notruf")
    c.children.link(root)
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0.7))
    o = link(bpy.context.active_object, root)
    o.scale = (0.22, 0.18, 0.7)
    bpy.ops.object.transform_apply(scale=True)
    bev = o.modifiers.new("b", "BEVEL")
    bev.width, bev.segments = 0.04, 3
    o.data.materials.append(M.orange)
    t = text_obj("notruf_t", "NOTRUF", 0.07, M.sblack, root, "CENTER", "CENTER", 0.001)
    t.rotation_euler = (math.radians(90), 0, 0)
    t.location = (0, -0.185, 1.2)
    return root


def phone_arrow(M, c):
    """Small black arrow plate on a delineator post pointing to the nearest emergency phone."""
    root = bpy.data.collections.new("phone_arrow")
    c.children.link(root)
    pts = [(-0.045, -0.012), (0.02, -0.012), (0.02, -0.03), (0.05, 0.0), (0.02, 0.03), (0.02, 0.012), (-0.045, 0.012)]
    plate("arrow_plate", pts, 0.002, M.sblack, root, 0.039).location = (0, 0, 0.55)
    return root


# ------------------------------------------------------------------ terrain and landscape
def terrain(road, M, c, size=4000.0, res=12.5, center=None):
    cx, cy = center or (road.X[road.n // 2], road.Y[road.n // 2])
    n = int(size / res)
    verts, faces, far = [], [], []
    for j in range(n + 1):
        for i in range(n + 1):
            x = cx - size / 2 + i * res
            y = cy - size / 2 + j * res
            s, d, rz = road.nearest(x, y)
            verts.append((x, y, ground_z(road, x, y)))
            far.append(min(1.0, max(0.0, (d - 27) / 12)))
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            faces.append((a, a + 1, a + n + 2, a + n + 1))
    o = mesh_obj("terrain", verts, faces, None, c)
    attr = o.data.color_attributes.new("far", "FLOAT_COLOR", "POINT")
    for k, v in enumerate(far):
        attr.data[k].color = (v, v, v, 1)
    for p in o.data.polygons:
        p.use_smooth = True
    o.data.materials.append(fields_material(M))
    return o


def fields_material(M):
    m = bpy.data.materials.new("landscape")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = 0.92
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 1.0
    vor.feature = "F1"
    vor.voronoi_dimensions = "2D"
    vor.distance = "CHEBYCHEV"
    vor.inputs["Randomness"].default_value = 0.85
    fmap = nt.nodes.new("ShaderNodeMapping")
    fmap.inputs["Scale"].default_value = (0.011, 0.0045, 1.0)
    fmap.inputs["Rotation"].default_value = (0, 0, 0.35)
    nt.links.new(tc.outputs["Object"], fmap.inputs["Vector"])
    nt.links.new(fmap.outputs["Vector"], vor.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    # October farmland: ploughed soil, stubble, winter wheat, meadow, maize stubble, fallow
    cols = [(0.0, (0.2, 0.12, 0.06)), (0.18, (0.5, 0.42, 0.22)), (0.34, (0.13, 0.3, 0.05)),
            (0.5, (0.28, 0.18, 0.08)), (0.64, (0.2, 0.38, 0.08)), (0.78, (0.42, 0.36, 0.16)),
            (0.9, (0.09, 0.22, 0.04))]
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = cols[0][0], (*cols[0][1], 1)
    ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = cols[1][0], (*cols[1][1], 1)
    for pos, col in cols[2:]:
        e = ramp.color_ramp.elements.new(pos)
        e.color = (*col, 1)
    sep_ = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(vor.outputs["Color"], sep_.inputs["Color"])
    nt.links.new(sep_.outputs[0], ramp.inputs["Fac"])
    # rows inside the fields
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.inputs["Scale"].default_value = 0.08
    wave.inputs["Distortion"].default_value = 0.0
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
    rowmix = nt.nodes.new("ShaderNodeMix")
    rowmix.data_type = "RGBA"
    rowmix.blend_type = "MULTIPLY"
    rowmix.inputs["Factor"].default_value = 0.2
    nt.links.new(ramp.outputs["Color"], rowmix.inputs["A"])
    nt.links.new(wave.outputs["Color"], rowmix.inputs["B"])
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "far"
    gnz = nt.nodes.new("ShaderNodeTexNoise")
    gnz.inputs["Scale"].default_value = 0.05
    nt.links.new(tc.outputs["Object"], gnz.inputs["Vector"])
    gr = nt.nodes.new("ShaderNodeValToRGB")
    gr.color_ramp.elements[0].color = (0.1, 0.25, 0.045, 1)
    gr.color_ramp.elements[1].color = (0.2, 0.4, 0.08, 1)
    nt.links.new(gnz.outputs["Fac"], gr.inputs["Fac"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    nt.links.new(attr.outputs["Fac"], mix.inputs["Factor"])
    nt.links.new(gr.outputs["Color"], mix.inputs["A"])
    nt.links.new(rowmix.outputs["Result"], mix.inputs["B"])
    nt.links.new(mix.outputs["Result"], p.inputs["Base Color"])
    return m


def wind_turbine(M, c, name="turbine", hub=110.0, blade=55.0):
    root = bpy.data.collections.new(name)
    c.children.link(root)
    white = principled("turbine_white", (0.85, 0.86, 0.87), 0.35)
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=2.6, radius2=1.4, depth=hub, location=(0, 0, hub / 2))
    t = link(bpy.context.active_object, root)
    t.data.materials.append(white)
    bpy.ops.object.shade_smooth()
    bpy.ops.mesh.primitive_cube_add(location=(0, 2.0, hub + 1.2))
    na = link(bpy.context.active_object, root)
    na.scale = (1.8, 5.5, 2.0)
    bpy.ops.object.transform_apply(scale=True)
    bv = na.modifiers.new("b", "BEVEL")
    bv.width, bv.segments = 0.6, 3
    na.data.materials.append(white)
    rotor = bpy.data.objects.new(name + "_rotor", None)
    root.objects.link(rotor)
    rotor.location = (0, -3.8, hub + 1.2)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.6, location=(0, 0, 0))
    hb = link(bpy.context.active_object, root)
    hb.scale = (1, 1.6, 1)
    hb.data.materials.append(white)
    hb.parent = rotor
    for k in range(3):
        a = math.radians(120 * k)
        pts = [(-0.9, 0.0, 1.0), (0.9, 0.0, 1.0), (0.25, 0.0, blade), (-0.15, 0.0, blade)]
        verts = [(x, y - 0.25, z) for x, y, z in pts] + [(x, y + 0.25, z) for x, y, z in pts]
        faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
        bl = mesh_obj("blade", verts, faces, white, root)
        bl.parent = rotor
        bl.rotation_euler = (0, a, 0)
    return root, rotor


def import_glb(path, c):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        link(o, c)
        if o.parent is None:
            o.location = (0, 0, 0)
    return new


def kenney(name, c):
    sub = bpy.data.collections.new(name)
    c.children.link(sub)
    path = None
    for root_, _d, files in os.walk(os.path.join(ASSETS, "nature", "kenney")):
        if name + ".glb" in files:
            path = os.path.join(root_, name + ".glb")
            break
    import_glb(path, sub)
    return sub


def instance(coll_, loc, rz=0.0, s=1.0, c=None):
    e = bpy.data.objects.new("inst", None)
    e.instance_type = "COLLECTION"
    e.instance_collection = coll_
    e.location = loc
    e.rotation_euler = (0, 0, rz)
    e.scale = (s, s, s)
    (c or bpy.context.scene.collection).objects.link(e)
    return e


def ground_z(road, x, y):
    """Landscape height: flat and just below the road near the motorway, rolling farmland and hills further out,
    rising towards the horizon. Terrain mesh and scattered objects both use this."""
    s, d, rz = road.nearest(x, y)
    hill = 60 * noise.noise(Vector((x / 900, y / 900, 0.3))) + 14 * noise.noise(Vector((x / 260, y / 260, 1.7)))
    base = rz - 0.8
    if d < 26:
        return base
    t = min(1.0, (d - 26) / 130)
    t = t * t * (3 - 2 * t)
    return base + t * (hill + 0.8) + 60.0 * min(1.0, max(0.0, (d - 500) / 1200))


# ------------------------------------------------------------------ vehicles
def truck(M, c, cab_color=(0.6, 0.02, 0.02), trailer_color=(0.85, 0.86, 0.87), name="truck", label=""):
    """Stylised 40 t semi: cab-over tractor and a 13.6 m curtain-side trailer. Front is +y, ground z = 0."""
    root = bpy.data.collections.new(name)
    c.children.link(root)
    g = bpy.data.objects.new(name, None)
    root.objects.link(g)
    cab_m = principled(name + "_cab", cab_color, 0.3, coat=1.0)
    tr_m = principled(name + "_trailer", trailer_color, 0.55)
    glass = principled(name + "_glass", (0.02, 0.03, 0.04), 0.05, metal=0.2)
    tyre = principled(name + "_tyre", (0.02, 0.02, 0.02), 0.8)
    rim = principled(name + "_rim", (0.7, 0.7, 0.72), 0.3, metal=1.0)
    chassis = principled(name + "_chassis", (0.05, 0.05, 0.05), 0.6)
    lights = principled(name + "_lights", (1, 0.9, 0.7), 0.2, emit=(1, 0.95, 0.85), estr=3.0)
    tail = principled(name + "_tail", (1, 0.02, 0.01), 0.2, emit=(1, 0.02, 0.01), estr=2.0)

    def bx(n_, loc, size, mat, bev=0.0):
        bpy.ops.mesh.primitive_cube_add(location=loc)
        o = link(bpy.context.active_object, root)
        o.name = n_
        o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
        bpy.ops.object.transform_apply(scale=True)
        if bev:
            b = o.modifiers.new("b", "BEVEL")
            b.width, b.segments = bev, 3
        o.data.materials.append(mat)
        o.parent = g
        return o

    bx("cab", (0, 6.6, 2.05), (2.5, 2.3, 2.6), cab_m, 0.18)
    bx("cab_top", (0, 6.45, 3.55), (2.4, 1.9, 0.6), cab_m, 0.2)
    bx("windscreen", (0, 7.76, 2.55), (2.2, 0.05, 1.05), glass, 0.04)
    bx("grille", (0, 7.76, 1.35), (1.6, 0.05, 0.6), chassis, 0.02)
    for x in (-0.95, 0.95):
        bx("headlight", (x, 7.77, 1.0), (0.35, 0.04, 0.16), lights, 0.02)
        bx("mirror", (x * 1.42, 7.6, 2.6), (0.12, 0.2, 0.55), chassis, 0.03)
    bx("chassis", (0, 2.0, 0.85), (1.0, 13.5, 0.35), chassis)
    bx("trailer", (0, -0.9, 2.55), (2.55, 13.6, 2.75), tr_m, 0.06)
    bx("trailer_floor", (0, -0.9, 1.12), (2.5, 13.6, 0.15), chassis)
    for x in (-1.0, 1.0):
        bx("taillight", (x, -7.72, 1.15), (0.3, 0.04, 0.12), tail, 0.02)
    if label:
        lm = principled(name + "_label", (0.05, 0.15, 0.45), 0.4)
        for side, rz in ((1.28, math.radians(90)), (-1.28, math.radians(-90))):
            t = text_obj("truck_label", label, 0.75, lm, root, "CENTER", "CENTER", 0.002)
            t.rotation_euler = (math.radians(90), 0, rz)
            t.location = (side, -0.9, 2.65)
            t.parent = g
    for y in (6.5, 2.2, 1.0, -5.6, -6.9, -8.2 + 1.0):
        for x in (-1.05, 1.05):
            bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.5, depth=0.32, location=(x, y, 0.5),
                                                rotation=(0, math.pi / 2, 0))
            w_ = link(bpy.context.active_object, root)
            w_.data.materials.append(tyre)
            bpy.ops.object.shade_smooth()
            w_.parent = g
            bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.28, depth=0.34, location=(x, y, 0.5),
                                                rotation=(0, math.pi / 2, 0))
            r_ = link(bpy.context.active_object, root)
            r_.data.materials.append(rim)
            r_.parent = g
    return root


# ------------------------------------------------------------------ overpass bridge and villages
def overpass(road, M, c, s, height=6.6, half=33.0, ramp=110.0, width=11.0):
    """Concrete beam bridge carrying a two-lane road across the motorway at right angles, with grass ramps."""
    c0, th, fwd, right, sl = road.frame(s)
    rz = c0.z
    deck_z = rz + height

    def P(x, along, z):
        q = c0 + right * x + fwd * along
        return (q.x, q.y, z)

    root = bpy.data.collections.new("overpass")
    c.children.link(root)
    asph = asphalt("bridge_asphalt", tracks=False)
    # deck body and road surface
    xs = [-half - ramp, -half, half, half + ramp]

    def gz(x):
        q = c0 + right * x
        return ground_z(road, q.x, q.y)

    verts, faces = [], []
    w2 = width / 2
    for x in (-half, half):
        pass
    deck = [P(x, a, z) for x in (-half, half) for a, z in ((-w2, deck_z), (w2, deck_z))]
    # box deck
    v = []
    for x in (-half, half):
        for a in (-w2, w2):
            for z in (deck_z - 1.3, deck_z):
                v.append(P(x, a, z))
    f = [(0, 2, 6, 4), (1, 5, 7, 3), (0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6)]
    mesh_obj("deck", v, f, M.concrete, root)
    mesh_obj("deck_road", [P(-half, -w2 + 1.0, deck_z + 0.02), P(half, -w2 + 1.0, deck_z + 0.02),
                           P(half, w2 - 1.0, deck_z + 0.02), P(-half, w2 - 1.0, deck_z + 0.02)],
             [(0, 1, 2, 3)], asph, root, uvs=[(0, 0), (2 * half, 0), (2 * half, 9), (0, 9)])
    for a in (-w2, w2 - 1.0):  # walkways / caps
        mesh_obj("cap", [P(-half, a, deck_z + 0.15), P(half, a, deck_z + 0.15), P(half, a + 1.0, deck_z + 0.15),
                         P(-half, a + 1.0, deck_z + 0.15)], [(0, 1, 2, 3)], M.concrete, root)
    # railings
    for a in (-w2 + 0.1, w2 - 0.1):
        for x0, x1 in ((-half, half),):
            n = int((x1 - x0) / 2.0)
            for k in range(n + 1):
                x = x0 + k * (x1 - x0) / n
                bpy.ops.mesh.primitive_cube_add(location=P(x, a, deck_z + 0.65))
                o = link(bpy.context.active_object, root)
                o.scale = (0.04, 0.04, 0.5)
                o.data.materials.append(M.steel)
            bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.04, depth=x1 - x0, location=P(0, a, deck_z + 1.15))
            o = link(bpy.context.active_object, root)
            o.rotation_euler = (0, math.pi / 2, -th)
            o.data.materials.append(M.steel)
    # piers: median wall and two outer columns rows
    for x, sx, sa in ((0.0, 0.5, 4.0), (-20.0, 0.9, 4.5), (20.0, 0.9, 4.5)):
        z0 = rz - 0.8
        h = deck_z - 1.3 - z0
        bpy.ops.mesh.primitive_cube_add(location=P(x, 0, z0 + h / 2))
        o = link(bpy.context.active_object, root)
        o.scale = (sx / 2, sa / 2, h / 2)
        o.rotation_euler = (0, 0, -th)
        o.data.materials.append(M.concrete)
    # ramps (embankments) on both sides
    for sgn in (-1, 1):
        verts, faces = [], []
        steps = 24
        for k in range(steps + 1):
            t = k / steps
            x = sgn * (half + ramp * t)
            top = deck_z + (gz(sgn * (half + ramp)) + 0.3 - deck_z) * (t * t * (3 - 2 * t))
            g_ = gz(x) - 0.5
            hgt = max(0.0, top - g_)
            wb = w2 + 1.5 * hgt
            prof = [(-wb, g_), (-w2, top), (w2, top), (wb, g_)]
            verts += [P(x, a, z) for a, z in prof]
            if k:
                b0, b1 = 4 * (k - 1), 4 * k
                for j in range(3):
                    faces.append((b0 + j, b0 + j + 1, b1 + j + 1, b1 + j) if sgn > 0 else
                                 (b0 + j, b1 + j, b1 + j + 1, b0 + j + 1))
        o = mesh_obj("ramp", verts, faces, M.grass, root)
        # road on the ramp
        rv, rf, ru = [], [], []
        for k in range(steps + 1):
            t = k / steps
            x = sgn * (half + ramp * t)
            top = deck_z + (gz(sgn * (half + ramp)) + 0.3 - deck_z) * (t * t * (3 - 2 * t))
            rv += [P(x, -w2 + 1.0, top + 0.03), P(x, w2 - 1.0, top + 0.03)]
            ru += [(ramp * t, 0), (ramp * t, 9)]
            if k:
                b0, b1 = 2 * (k - 1), 2 * k
                rf.append((b0, b1, b1 + 1, b0 + 1) if sgn > 0 else (b0, b0 + 1, b1 + 1, b1))
        mesh_obj("ramp_road", rv, rf, asph, root, uvs=ru)
        # abutment wall
        bpy.ops.mesh.primitive_cube_add(location=P(sgn * (half + 0.3), 0, (deck_z + rz - 0.8) / 2))
        o = link(bpy.context.active_object, root)
        o.scale = (0.6, w2 + 2.0, (deck_z - rz + 0.8) / 2)
        o.rotation_euler = (0, 0, -th)
        o.data.materials.append(M.concrete)
    return root


def house_library(lib, M):
    """A few German village house types: white or cream render, red or anthracite gable roofs."""
    walls = [principled("wall_white", (0.82, 0.8, 0.74), 0.8), principled("wall_cream", (0.8, 0.7, 0.52), 0.8),
             principled("wall_grey", (0.62, 0.62, 0.6), 0.8)]
    roofs = [principled("roof_red", (0.42, 0.09, 0.04), 0.7), principled("roof_brown", (0.25, 0.08, 0.04), 0.7),
             principled("roof_anthracite", (0.06, 0.065, 0.07), 0.6)]
    win = principled("house_window", (0.03, 0.035, 0.04), 0.2)
    g = bpy.data.collections.new("lib_houses")
    lib.children.link(g)
    rnd = random.Random(3)
    for k in range(7):
        sub = bpy.data.collections.new(f"house{k}")
        g.children.link(sub)
        W_, D_, H_ = rnd.uniform(8, 12), rnd.uniform(9, 14), rnd.uniform(5.5, 7.5)
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, H_ / 2))
        o = link(bpy.context.active_object, sub)
        o.scale = (W_ / 2, D_ / 2, H_ / 2)
        o.data.materials.append(walls[k % 3])
        rh = W_ * rnd.uniform(0.38, 0.55)
        ov = 0.5
        v = [(-W_ / 2 - ov, -D_ / 2 - ov, H_), (W_ / 2 + ov, -D_ / 2 - ov, H_), (0, -D_ / 2 - ov, H_ + rh),
             (-W_ / 2 - ov, D_ / 2 + ov, H_), (W_ / 2 + ov, D_ / 2 + ov, H_), (0, D_ / 2 + ov, H_ + rh)]
        f = [(0, 1, 2), (5, 4, 3), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)]
        mesh_obj("roof", v, f, roofs[(k * 2) % 3], sub)
        # gable wall triangles
        v2 = [(-W_ / 2, -D_ / 2, H_), (W_ / 2, -D_ / 2, H_), (0, -D_ / 2, H_ + rh - 0.3),
              (-W_ / 2, D_ / 2, H_), (W_ / 2, D_ / 2, H_), (0, D_ / 2, H_ + rh - 0.3)]
        mesh_obj("gable", v2, [(0, 1, 2), (5, 4, 3)], walls[k % 3], sub)
        for side in (-1, 1):
            for z in (1.6, 4.3):
                for xx in (-W_ / 4, W_ / 4):
                    mesh_obj("win", [(xx - 0.6, side * (D_ / 2 + 0.01), z), (xx + 0.6, side * (D_ / 2 + 0.01), z),
                                     (xx + 0.6, side * (D_ / 2 + 0.01), z + 1.3), (xx - 0.6, side * (D_ / 2 + 0.01), z + 1.3)],
                             [(0, 1, 2, 3) if side < 0 else (3, 2, 1, 0)], win, sub)
    church = bpy.data.collections.new("church")
    lib.children.link(church)
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 6))
    o = link(bpy.context.active_object, church)
    o.scale = (6, 13, 6)
    o.data.materials.append(walls[0])
    v = [(-6.5, -13.5, 12), (6.5, -13.5, 12), (0, -13.5, 19), (-6.5, 13.5, 12), (6.5, 13.5, 12), (0, 13.5, 19)]
    mesh_obj("church_roof", v, [(0, 1, 2), (5, 4, 3), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)], roofs[0], church)
    bpy.ops.mesh.primitive_cube_add(location=(0, -17, 14))
    o = link(bpy.context.active_object, church)
    o.scale = (3.5, 3.5, 14)
    o.data.materials.append(walls[0])
    bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=4.4, radius2=0.05, depth=16, location=(0, -17, 36))
    o = link(bpy.context.active_object, church)
    o.rotation_euler = (0, 0, math.pi / 8)
    o.data.materials.append(principled("spire", (0.12, 0.2, 0.18), 0.5, metal=0.4))
    return g, church


def village(road, groups_houses, church, c, s, x, n=36, radius=140.0, seed=1):
    rnd = random.Random(seed)
    cp = road.point(s, x)
    pts = []
    rot0 = rnd.uniform(0, math.pi)
    for k in range(n):
        a = rnd.uniform(0, 2 * math.pi)
        r = radius * math.sqrt(rnd.random())
        px, py = cp.x + math.cos(a) * r, cp.y + math.sin(a) * r
        pts.append((px, py))
    out = []
    kids = list(groups_houses.children)
    for px, py in pts:
        z = ground_z(road, px, py)
        e = instance(rnd.choice(kids), (px, py, z - 0.4), rz=rot0 + rnd.choice((0, math.pi / 2)) + rnd.uniform(-0.15, 0.15),
                     c=c)
        out.append(e)
    z = ground_z(road, cp.x, cp.y)
    out.append(instance(church, (cp.x, cp.y, z - 0.4), rz=rot0, c=c))
    return out
