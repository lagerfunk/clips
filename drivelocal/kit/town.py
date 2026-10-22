"""Stylised German town junction kit (Module A of Drive Like a Local).

Realistic cartoony, built to German specs where a source exists (road_spec.md):
- residential street 6.0 m carriageway, main street 7.0 m; kerb 0.15 m high (Hochbord), granite kerb stone 0.16 m wide;
  a 0.30 m cobble gutter (Rinne) on the road side of every kerb; footway 2.50 m (concrete pavers); kerb radius 6 m.
- markings: Haifischzaehne (Zeichen 342) white triangles pointing at the waiting driver; stop line 0.50 m (urban);
  no centre line on residential streets (the usual German Tempo 30 street).
- signs: Zeichen 205 (give way), 206 (stop), 301 (priority at the next junction), 306 (priority road),
  102 (junction, priority from the right), 720 (green arrow plate, 250 x 250 mm, right of the red lamp), drawn as
  shapes; u_DIN 1451 for the lettering. Sign sizes: size 2 (triangle 900 mm, disc 600 mm).
- houses: rendered gable houses with white PVC windows, roller shutters, plinth, tiled roofs, gutters, chimneys,
  some solar panels; garages, hedges, fences, wheelie bins, street lamps.
Junction centre is the origin; the north-south street runs along y, the east-west street along x; traffic drives on
the right. Everything is built from simple, exact geometry so it renders fast on CPU runners.
"""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

import world as W

KERB_H = 0.15
KERB_W = 0.16
GUTTER = 0.30
FOOT = 2.50


# ------------------------------------------------------------------ materials
def brick(name, c1, c2, mortar, scale, mortar_size=0.02, rough=0.8, bump=0.3, row_h=0.25, brick_w=0.5,
          offset=0.5, coord="UV", rot=0.0, var=0.25):
    """Running-bond pattern (pavers, roof tiles, cobbles). UV in metres."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, rot)
    nt.links.new(tc.outputs[coord], mp.inputs["Vector"])
    b = nt.nodes.new("ShaderNodeTexBrick")
    b.offset = offset
    b.inputs["Scale"].default_value = scale
    b.inputs["Mortar Size"].default_value = mortar_size
    b.inputs["Brick Width"].default_value = brick_w
    b.inputs["Row Height"].default_value = row_h
    b.inputs["Bias"].default_value = 0.0
    b.inputs["Color1"].default_value = (*c1, 1)
    b.inputs["Color2"].default_value = (*c2, 1)
    b.inputs["Mortar"].default_value = (*mortar, 1)
    nt.links.new(mp.outputs["Vector"], b.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.8
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "OVERLAY"
    mix.inputs["Factor"].default_value = var
    nt.links.new(b.outputs["Color"], mix.inputs["A"])
    nt.links.new(nz.outputs["Color"], mix.inputs["B"])
    nt.links.new(mix.outputs["Result"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = rough
    if bump:
        bn = nt.nodes.new("ShaderNodeBump")
        bn.inputs["Strength"].default_value = bump
        bn.invert = True
        nt.links.new(b.outputs["Fac"], bn.inputs["Height"])
        nt.links.new(bn.outputs["Normal"], p.inputs["Normal"])
    return m


def emissive(name, color, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*color, 1)
    e.inputs["Strength"].default_value = strength
    nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


def town_asphalt():
    """Residential asphalt: dark grey, fine grain, broad tonal variation, a few square repair patches."""
    m = bpy.data.materials.new("town_asphalt")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    grain = nt.nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 9.0
    grain.inputs["Detail"].default_value = 8.0
    nt.links.new(tc.outputs["UV"], grain.inputs["Vector"])
    broad = nt.nodes.new("ShaderNodeTexNoise")
    broad.inputs["Scale"].default_value = 0.05
    broad.inputs["Detail"].default_value = 2.0
    nt.links.new(tc.outputs["UV"], broad.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMath")
    mix.operation = "MULTIPLY_ADD"
    mix.inputs[1].default_value = 0.35
    nt.links.new(grain.outputs["Fac"], mix.inputs[0])
    nt.links.new(broad.outputs["Fac"], mix.inputs[2])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (0.036, 0.037, 0.04, 1)
    ramp.color_ramp.elements[1].position = 0.85
    ramp.color_ramp.elements[1].color = (0.07, 0.071, 0.074, 1)
    nt.links.new(mix.outputs[0], ramp.inputs["Fac"])
    # repair patches: 3 m squares of darker, newer asphalt here and there
    vo = nt.nodes.new("ShaderNodeTexVoronoi")
    vo.feature = "F1"
    vo.distance = "CHEBYCHEV"
    vo.inputs["Scale"].default_value = 0.11
    nt.links.new(tc.outputs["UV"], vo.inputs["Vector"])
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(vo.outputs["Color"], sep.inputs["Color"])
    sel = nt.nodes.new("ShaderNodeMath")
    sel.operation = "GREATER_THAN"
    sel.inputs[1].default_value = 0.93
    nt.links.new(sep.outputs[0], sel.inputs[0])
    small = nt.nodes.new("ShaderNodeMath")
    small.operation = "LESS_THAN"
    small.inputs[1].default_value = 0.17
    nt.links.new(vo.outputs["Distance"], small.inputs[0])
    both = nt.nodes.new("ShaderNodeMath")
    both.operation = "MULTIPLY"
    nt.links.new(sel.outputs[0], both.inputs[0])
    nt.links.new(small.outputs[0], both.inputs[1])
    pm = nt.nodes.new("ShaderNodeMix")
    pm.data_type = "RGBA"
    pm.blend_type = "MULTIPLY"
    pm.inputs["B"].default_value = (0.72, 0.72, 0.74, 1)
    nt.links.new(both.outputs[0], pm.inputs["Factor"])
    nt.links.new(ramp.outputs["Color"], pm.inputs["A"])
    nt.links.new(pm.outputs["Result"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.82
    bn = nt.nodes.new("ShaderNodeBump")
    bn.inputs["Strength"].default_value = 0.12
    nt.links.new(grain.outputs["Fac"], bn.inputs["Height"])
    nt.links.new(bn.outputs["Normal"], p.inputs["Normal"])
    return m


class TownMats:
    def __init__(self, M):
        self.M = M
        self.asph = town_asphalt()
        self.curb = W.noisy("kerb_granite", (0.5, 0.5, 0.48), (0.66, 0.66, 0.63), 9.0, rough=0.75, bump=0.2,
                            coord="UV")
        self.pavers = brick("footway_pavers", (0.38, 0.37, 0.355), (0.44, 0.43, 0.41), (0.25, 0.25, 0.24), 1.0,
                            mortar_size=0.008, row_h=0.1, brick_w=0.2, bump=0.15)
        self.cobble = brick("gutter_cobbles", (0.3, 0.3, 0.29), (0.4, 0.39, 0.37), (0.12, 0.12, 0.12), 1.0,
                            mortar_size=0.012, row_h=0.1, brick_w=0.1, bump=0.3, var=0.4)
        self.lawn = W.noisy("lawn", (0.1, 0.24, 0.05), (0.2, 0.36, 0.09), 0.35, rough=0.95, detail=6, coord="UV",
                            bump=0.15)
        self.bed = W.noisy("garden_bed", (0.09, 0.06, 0.035), (0.16, 0.11, 0.06), 2.0, rough=0.95, coord="UV")
        self.drive = brick("drive_pavers", (0.5, 0.42, 0.36), (0.42, 0.36, 0.31), (0.25, 0.23, 0.21), 1.0,
                           mortar_size=0.01, row_h=0.1, brick_w=0.2, bump=0.15, rot=math.pi / 2)
        self.hedge = W.noisy("hedge", (0.035, 0.1, 0.025), (0.08, 0.2, 0.04), 2.5, rough=0.9, detail=5, bump=0.6,
                             coord="Object")
        self.walls = [W.noisy(f"plaster{k}", c1, c2, 1.5, rough=0.85, bump=0.05) for k, (c1, c2) in enumerate((
            ((0.8, 0.79, 0.74), (0.86, 0.85, 0.8)), ((0.83, 0.74, 0.55), (0.88, 0.8, 0.62)),
            ((0.72, 0.73, 0.71), (0.78, 0.79, 0.77)), ((0.86, 0.79, 0.68), (0.9, 0.84, 0.74)),
            ((0.8, 0.66, 0.58), (0.85, 0.72, 0.64)), ((0.74, 0.78, 0.74), (0.8, 0.83, 0.79))))]
        self.plinth = W.noisy("plinth", (0.24, 0.24, 0.23), (0.3, 0.3, 0.29), 3.0, rough=0.85, bump=0.1)
        self.roofs = [
            brick("roof_red", (0.42, 0.11, 0.05), (0.36, 0.09, 0.04), (0.12, 0.03, 0.015), 1.0, mortar_size=0.015,
                  row_h=0.36, brick_w=0.3, bump=0.5, rough=0.6, var=0.3),
            brick("roof_anthracite", (0.07, 0.075, 0.08), (0.1, 0.105, 0.11), (0.02, 0.02, 0.02), 1.0,
                  mortar_size=0.015, row_h=0.36, brick_w=0.3, bump=0.5, rough=0.45, var=0.2),
            brick("roof_brown", (0.24, 0.1, 0.05), (0.2, 0.08, 0.04), (0.07, 0.03, 0.015), 1.0, mortar_size=0.015,
                  row_h=0.36, brick_w=0.3, bump=0.5, rough=0.6, var=0.3),
        ]
        self.frame = W.principled("pvc_white", (0.9, 0.9, 0.88), 0.35)
        self.glass = W.principled("window_glass", (0.02, 0.03, 0.04), 0.03, spec=0.9, coat=1.0)
        self.sill = W.principled("sill_stone", (0.55, 0.55, 0.53), 0.6)
        self.shutter = brick("roller_shutter", (0.55, 0.56, 0.56), (0.55, 0.56, 0.56), (0.35, 0.36, 0.36), 1.0,
                             mortar_size=0.06, row_h=0.05, brick_w=10.0, bump=0.2, offset=0.0, var=0.05)
        self.doors = [W.principled("door_anthracite", (0.06, 0.065, 0.07), 0.4),
                      W.principled("door_wood", (0.22, 0.11, 0.05), 0.55),
                      W.principled("door_white", (0.85, 0.85, 0.83), 0.4)]
        self.garage = brick("garage_door", (0.82, 0.82, 0.8), (0.82, 0.82, 0.8), (0.6, 0.6, 0.58), 1.0,
                            mortar_size=0.04, row_h=0.5, brick_w=10.0, bump=0.3, offset=0.0, var=0.03)
        self.metal = W.principled("anodised", (0.45, 0.46, 0.47), 0.35, metal=0.8)
        self.zinc = W.principled("zinc_gutter", (0.5, 0.52, 0.53), 0.4, metal=0.9)
        self.solar = brick("solar_panel", (0.02, 0.03, 0.07), (0.02, 0.035, 0.08), (0.5, 0.52, 0.55), 1.0,
                           mortar_size=0.01, row_h=1.0, brick_w=1.7, bump=0.0, offset=0.0, rough=0.15, var=0.05)
        self.wood = W.noisy("fence_wood", (0.3, 0.2, 0.11), (0.38, 0.26, 0.15), 6.0, rough=0.8)
        self.bins = {"grey": W.principled("bin_grey", (0.12, 0.12, 0.13), 0.5),
                     "blue": W.principled("bin_blue", (0.02, 0.08, 0.35), 0.5),
                     "brown": W.principled("bin_brown", (0.18, 0.09, 0.03), 0.5),
                     "yellow": W.principled("bin_yellow", (0.8, 0.6, 0.02), 0.5)}
        self.pole = W.principled("pole_grey", (0.42, 0.44, 0.45), 0.4, metal=0.6)
        self.lamp_glass = W.principled("lamp_glass", (0.85, 0.85, 0.8), 0.2, emit=(1, 0.95, 0.85), estr=0.2)
        self.manhole = brick("manhole_iron", (0.06, 0.06, 0.06), (0.08, 0.075, 0.07), (0.03, 0.03, 0.03), 1.0,
                             mortar_size=0.15, row_h=0.08, brick_w=0.08, bump=0.6, rough=0.55)
        self.paint = M.paint
        self.yellow = W.principled("sign_yellow", (0.95, 0.62, 0.0), 0.35)      # RAL 1023 traffic yellow
        self.sgreen_arrow = W.principled("arrow_green", (0.02, 0.45, 0.12), 0.3, emit=(0.05, 0.6, 0.15), estr=0.3)


# ------------------------------------------------------------------ polyline helpers
def offset_poly(P, d):
    """Offset an open 2D polyline to its LEFT by d (mitred)."""
    out = []
    n = len(P)
    for i in range(n):
        if i == 0:
            t = (P[1] - P[0]).normalized()
        elif i == n - 1:
            t = (P[-1] - P[-2]).normalized()
        else:
            t1 = (P[i] - P[i - 1]).normalized()
            t2 = (P[i + 1] - P[i]).normalized()
            t = (t1 + t2).normalized()
        nrm = Vector((-t.y, t.x))
        if 0 < i < n - 1:
            t1 = (P[i] - P[i - 1]).normalized()
            cosh = max(0.3, nrm.dot(Vector((-t1.y, t1.x))))
            out.append(P[i] + nrm * (d / cosh))
        else:
            out.append(P[i] + nrm * d)
    return out


def poly_len(P):
    acc = [0.0]
    for i in range(1, len(P)):
        acc.append(acc[-1] + (P[i] - P[i - 1]).length)
    return acc


def strip(name, P, d0, d1, z0, z1, mat, c, uv_scale=1.0):
    """A band between the left offsets d0 and d1 of polyline P, at heights z0 (inner) and z1 (outer).
    UV: u along the band in metres, v across in metres."""
    A = offset_poly(P, d0)
    B = offset_poly(P, d1)
    acc = poly_len(P)
    verts, faces, uvs = [], [], []
    for i in range(len(P)):
        verts += [(A[i].x, A[i].y, z0), (B[i].x, B[i].y, z1)]
        uvs += [(acc[i] * uv_scale, d0 * uv_scale), (acc[i] * uv_scale, d1 * uv_scale)]
    for i in range(len(P) - 1):
        a, b = 2 * i, 2 * (i + 1)
        faces.append((a, b, b + 1, a + 1) if d1 > d0 else (a + 1, b + 1, b, a))
    o = W.mesh_obj(name, verts, faces, mat, c, uvs=uvs)
    return o


def sweep(name, P, profile, mat, c, closed=False, smooth=False):
    """Sweep a 2D profile [(left offset, z)] along polyline P."""
    rings = [offset_poly(P, d) for d, _z in profile]
    acc = poly_len(P)
    verts, faces, uvs = [], [], []
    m = len(profile)
    for i in range(len(P)):
        for j, (_d, z) in enumerate(profile):
            q = rings[j][i]
            verts.append((q.x, q.y, z))
            uvs.append((acc[i], j * 0.1))
    for i in range(len(P) - 1):
        for j in range(m - 1 if not closed else m):
            j2 = (j + 1) % m
            faces.append((i * m + j, (i + 1) * m + j, (i + 1) * m + j2, i * m + j2))
    return W.mesh_obj(name, verts, faces, mat, c, uvs=uvs, smooth=smooth)


def arc(cx, cy, r, a0, a1, n):
    return [Vector((cx + r * math.cos(a0 + (a1 - a0) * k / n), cy + r * math.sin(a0 + (a1 - a0) * k / n)))
            for k in range(n + 1)]


_BOX_FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def box(name, c, loc, size, mat, rot_z=0.0, bevel=0.0, parent=None):
    """Axis box built straight from data (no operators, fast). UVs are planar per face, in metres."""
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    v = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
         (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(v, [], _BOX_FACES)
    uvl = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        nrm = poly.normal
        ax = max(range(3), key=lambda i: abs(nrm[i]))
        a, b = [(1, 2), (0, 2), (0, 1)][ax]
        for li in poly.loop_indices:
            co = v[me.loops[li].vertex_index]
            uvl.data[li].uv = (co[a] + 50.0, co[b] + 50.0)
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    o.location = loc
    o.rotation_euler = (0, 0, rot_z)
    if bevel:
        b_ = o.modifiers.new("b", "BEVEL")
        b_.width, b_.segments = bevel, 2
    me.materials.append(mat)
    if parent:
        o.parent = parent
    return o


def cyl(name, c, loc, r, h, mat, verts=16, rot=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts, radius1=r, radius2=r, depth=h,
                          calc_uvs=True)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    me.materials.append(mat)
    return o


def uv_world(o, scale=1.0):
    """Planar world-xy UVs (metres) for ground pieces."""
    me = o.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uvl = me.uv_layers.active
    mw = o.matrix_world
    for poly in me.polygons:
        for li in poly.loop_indices:
            v = mw @ me.vertices[me.loops[li].vertex_index].co
            uvl.data[li].uv = (v.x * scale, v.y * scale)


# ------------------------------------------------------------------ the junction
class Junction:
    """X junction. hw_ns / hw_ew: half carriageway widths. R: kerb radius. L: arm length from the centre."""

    def __init__(self, T, c, hw_ns=3.0, hw_ew=3.0, R=6.0, L=95.0):
        self.T, self.c = T, c
        self.hw_ns, self.hw_ew, self.R, self.L = hw_ns, hw_ew, R, L
        self.kerbs = {}
        self.build()

    def kerb_line(self, sx, sy, n_arc=16):
        """Kerb line of quadrant (sx, sy), ordered so the road is on the RIGHT when walking along it."""
        hx, hy, R, L = self.hw_ns, self.hw_ew, self.R, self.L
        cx, cy = sx * (hx + R), sy * (hy + R)
        a_ns = math.atan2(0, -sx)              # from the arc centre towards the NS street edge
        a_ew = math.atan2(-sy, 0)              # towards the EW street edge
        # go the short way round
        da = (a_ew - a_ns + math.pi) % (2 * math.pi) - math.pi
        P = [Vector((sx * hx, sy * L))]
        for y in (sy * (hy + R + 30.0), sy * (hy + R + 10.0)):
            P.append(Vector((sx * hx, y)))
        P += arc(cx, cy, R, a_ns, a_ns + da, n_arc)
        for x in (sx * (hx + R + 10.0), sx * (hx + R + 30.0), sx * L):
            P.append(Vector((x, sy * hy)))
        # orientation: road must be on the right of the walking direction
        mid = P[len(P) // 2]
        t = (P[len(P) // 2 + 1] - P[len(P) // 2 - 1]).normalized()
        left = Vector((-t.y, t.x))
        if (mid + left).length < mid.length:   # left points towards the centre (the road): reverse
            P.reverse()
        return P

    def build(self):
        T, c, L = self.T, self.c, self.L
        # asphalt under everything
        a = W.mesh_obj("asphalt", [(-L, -L, 0), (L, -L, 0), (L, L, 0), (-L, L, 0)], [(0, 1, 2, 3)], T.asph, c,
                       uvs=[(-L, -L), (L, -L), (L, L), (-L, L)])
        a.name = "asphalt"
        for sx in (-1, 1):
            for sy in (-1, 1):
                P = self.kerb_line(sx, sy)
                self.kerbs[(sx, sy)] = P
                self.block(P, sx, sy)

    def block(self, P, sx, sy):
        T, c, L = self.T, self.c, self.L
        # gutter cobbles on the road side (right of P = negative left offset)
        strip("gutter", P, -GUTTER, 0.0, 0.004, 0.004, T.cobble, c)
        # kerb: vertical face and top
        sweep("kerb", P, [(0.0, 0.0), (0.0, KERB_H - 0.02), (0.02, KERB_H), (KERB_W, KERB_H)], T.curb, c)
        strip("footway", P, KERB_W, KERB_W + FOOT, KERB_H, KERB_H, T.pavers, c)
        # the garden ground: polygon between the back of the footway and the far corner
        Q = offset_poly(P, KERB_W + FOOT)
        corner = Vector((sx * L, sy * L))
        pts = Q + [corner]
        verts = [(p.x, p.y, KERB_H) for p in pts]
        o = W.mesh_obj(f"ground{sx}{sy}", verts, [tuple(range(len(verts)))], T.lawn, c)
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        for f in bm.faces:
            if f.normal.z < 0:
                f.normal_flip()
        bm.to_mesh(o.data)
        bm.free()
        uv_world(o, 1.0)

    # -------------------------------------------------------------- frames along the streets
    def footway_point(self, arm, dist, off):
        """Point on the footway of an arm. arm: 'N','S','E','W'; side: right-hand side when driving AWAY from the
        centre is +off... Simpler: off is the signed lateral coordinate measured from the street centre line
        (positive = east for N/S arms, north for E/W arms). dist from the centre along the arm."""
        if arm == "N":
            return Vector((off, dist))
        if arm == "S":
            return Vector((off, -dist))
        if arm == "E":
            return Vector((dist, off))
        return Vector((-dist, off))


# ------------------------------------------------------------------ houses
def window(T, c, parent, x, z, w, h, depth_face, rnd, side="front"):
    """Window on the wall plane y = depth_face (the wall's outside face; outside is -y). Dark glass just in front of
    the wall, a white PVC frame standing 4 cm proud with a mullion, a stone sill, sometimes a roller shutter."""
    g = []
    y0 = depth_face
    fr = 0.085
    g.append(box("wglass", c, (x, y0 - 0.006, z), (w - 0.02, 0.012, h - 0.02), T.glass, parent=parent))
    for (cx, cz, sw, sh) in ((x, z + h / 2 - fr / 2, w, fr), (x, z - h / 2 + fr / 2, w, fr),
                             (x - w / 2 + fr / 2, z, fr, h), (x + w / 2 - fr / 2, z, fr, h), (x, z, fr * 0.8, h)):
        g.append(box("wframe", c, (cx, y0 - 0.03, cz), (sw, 0.05, sh), T.frame, parent=parent))
    g.append(box("wsill", c, (x, y0 - 0.08, z - h / 2 - 0.03), (w + 0.14, 0.17, 0.05), T.sill, parent=parent))
    down = rnd.choice((0.15, 0.3, 0.55, 1.0)) if rnd.random() < 0.35 else 0.0
    if down > 0:
        sh = (h - fr) * down
        g.append(box("shutter", c, (x, y0 - 0.06, z + (h - fr) / 2 - sh / 2), (w - fr * 0.6, 0.02, sh), T.shutter,
                     parent=parent))
    return g


def house(T, c, name, seed, w=None, d=None, storeys=None, gable_to_street=None, garage=None):
    """A German detached house. Local frame: street side faces -y, origin at the middle of the footprint on the
    ground (z = 0 is garden level). Returns the collection."""
    rnd = random.Random(seed)
    root = bpy.data.collections.new(name)
    c.children.link(root)
    g = bpy.data.objects.new(name + "_root", None)
    root.objects.link(g)
    w = w or rnd.uniform(9.0, 11.5)
    d = d or rnd.uniform(8.5, 10.5)
    storeys = storeys or rnd.choice((1, 2, 2))
    gable_to_street = rnd.random() < 0.4 if gable_to_street is None else gable_to_street
    sh = 2.75
    He = 0.45 + storeys * sh if storeys == 2 else 0.45 + sh + 0.9   # 1 storey houses have a knee wall in the attic
    wall = rnd.choice(T.walls)
    roof_m = rnd.choice(T.roofs)
    pitch = math.radians(rnd.uniform(38, 46))
    box("plinth", root, (0, 0, 0.25), (w + 0.04, d + 0.04, 0.5), T.plinth, parent=g)
    body = box("walls", root, (0, 0, (He + 0.5) / 2), (w, d, He - 0.5), wall, parent=g)
    body.location.z = 0.5 + (He - 0.5) / 2
    # roof: ridge along x (eaves to the street) or along y (gable to the street)
    span, length = (d, w) if not gable_to_street else (w, d)
    ov_e, ov_g, th = 0.45, 0.3, 0.16
    rh = (span / 2 + ov_e) * math.tan(pitch)
    half = span / 2 + ov_e
    ridge_z = He + (span / 2) * math.tan(pitch)
    eave_z = He - ov_e * math.tan(pitch)
    Lr = length / 2 + ov_g
    # two roof planes as thin slabs; local coords (a along ridge, b across, z)
    def P(a, b, z):
        return (a, b, z) if not gable_to_street else (b, a, z)

    verts, faces, uvs = [], [], []
    slope_len = math.hypot(half, rh)
    for side in (-1, 1):
        base = len(verts)
        quad = [P(-Lr, side * half, eave_z), P(Lr, side * half, eave_z), P(Lr, 0, ridge_z), P(-Lr, 0, ridge_z)]
        top = [(x, y, z + th) for x, y, z in quad]
        verts += quad + top
        uvs += [(-Lr, slope_len), (Lr, slope_len), (Lr, 0), (-Lr, 0)] * 2
        if (side > 0) != gable_to_street:
            faces += [(base + 4, base + 5, base + 6, base + 7), (base + 3, base + 2, base + 1, base + 0)]
        else:
            faces += [(base + 7, base + 6, base + 5, base + 4), (base + 0, base + 1, base + 2, base + 3)]
        faces += [(base + 0, base + 1, base + 5, base + 4), (base + 1, base + 2, base + 6, base + 5),
                  (base + 2, base + 3, base + 7, base + 6), (base + 3, base + 0, base + 4, base + 7)]
    ro = W.mesh_obj("roof", verts, faces, roof_m, root, uvs=uvs)
    bm = bmesh.new()
    bm.from_mesh(ro.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ro.data)
    bm.free()
    ro.parent = g
    # ridge cap
    rc = box("ridge", root, (0, 0, ridge_z + th + 0.04), (2 * Lr, 0.22, 0.12), roof_m, parent=g)
    if gable_to_street:
        rc.rotation_euler.z = math.pi / 2
    # gable walls
    for e in (-1, 1):
        if not gable_to_street:
            v = [(e * w / 2, -d / 2, He), (e * w / 2, d / 2, He), (e * w / 2, 0, ridge_z)]
        else:
            v = [(-w / 2, e * d / 2, He), (w / 2, e * d / 2, He), (0, e * d / 2, ridge_z)]
        gw = W.mesh_obj("gable", v, [(0, 1, 2)], wall, root)
        bm = bmesh.new()
        bm.from_mesh(gw.data)
        bm.faces.ensure_lookup_table()
        f = bm.faces[0]
        f.normal_update()
        outward = Vector((e, 0, 0)) if not gable_to_street else Vector((0, e, 0))
        if f.normal.dot(outward) < 0:
            f.normal_flip()
        bm.to_mesh(gw.data)
        bm.free()
        gw.parent = g
    # gutters along the eaves and a downpipe
    for side in (-1, 1):
        if not gable_to_street:
            gu = cyl("gutter", root, (0, side * (half + 0.03), eave_z + 0.02), 0.07, 2 * Lr, T.zinc, 12,
                     (0, math.pi / 2, 0))
        else:
            gu = cyl("gutter", root, (side * (half + 0.03), 0, eave_z + 0.02), 0.07, 2 * Lr, T.zinc, 12,
                     (math.pi / 2, 0, 0))
        gu.parent = g
    cyl("downpipe", root, (w / 2 - 0.15, -d / 2 - 0.08, eave_z / 2), 0.045, eave_z, T.zinc, 10).parent = g
    # chimney
    if rnd.random() < 0.7:
        cx = rnd.uniform(-length / 4, length / 4)
        ch = box("chimney", root, (0, 0, ridge_z), (0.55, 0.55, 1.6), rnd.choice((T.plinth, wall)), parent=g)
        ch.location = (cx, 0.6, ridge_z + 0.25) if not gable_to_street else (0.6, cx, ridge_z + 0.25)
        cap = box("chimney_cap", root, (0, 0, 0), (0.7, 0.7, 0.06), T.zinc, parent=g)
        cap.location = ch.location + Vector((0, 0, 0.83))
    # solar panels on the street-facing or side slope
    if rnd.random() < 0.45:
        nx, ny = (3, 2) if storeys == 2 else (4, 2)
        side = rnd.choice((-1, 1))
        for i in range(nx):
            for j in range(ny):
                a = (i - (nx - 1) / 2) * 1.75
                bb = 0.6 + j * 1.08
                frac = bb / slope_len
                zz = ridge_z + (eave_z - ridge_z) * frac + th + 0.08
                pos = P(a, side * half * frac, zz)
                sp = box("solar", root, pos, (1.7, 1.02, 0.04), T.solar, parent=g)
                tilt = math.atan2(rh, half) * (-side)
                if not gable_to_street:
                    sp.rotation_euler = (tilt, 0, 0)
                else:
                    sp.rotation_euler = (0, -tilt, 0)
    # windows and door on the street front (y = -d/2), the back and the side walls
    zs = [1.45] if storeys == 1 else [1.45, 1.45 + sh]
    if storeys == 1:
        zs.append(He + 0.9 if gable_to_street else None)
    door_x = rnd.choice((-1, 1)) * (w / 2 - 1.6) if not gable_to_street else rnd.uniform(-1, 1)
    for face_sign in (-1, 1):
        y_face = face_sign * d / 2
        # mirror for the back: build windows on the -y face and rotate copies? simpler: place with y = -d/2 and
        # a parent rotated by pi for the back
        holder = bpy.data.objects.new("face", None)
        root.objects.link(holder)
        holder.parent = g
        holder.rotation_euler.z = 0 if face_sign < 0 else math.pi
        xs = [-w / 2 + 1.6 + k * ((w - 3.2) / 2) for k in range(3)]
        for zi, zc in enumerate(zs):
            if zc is None:
                continue
            for x in xs:
                if face_sign < 0 and zi == 0 and abs(x - door_x) < 1.0:
                    continue
                window(T, root, holder, x, zc, 1.3 if zi == 0 else 1.2, 1.45 if zi == 0 else 1.35, -d / 2, rnd)
        if face_sign < 0:
            dm = rnd.choice(T.doors)
            box("door", root, (door_x, -d / 2 - 0.01, 0.5 + 1.05), (1.05, 0.06, 2.1), dm, parent=holder)
            box("door_frame", root, (door_x, -d / 2 - 0.005, 0.5 + 1.1), (1.25, 0.04, 2.25), T.frame, parent=holder)
            box("canopy", root, (door_x, -d / 2 - 0.55, 2.95), (1.8, 1.1, 0.08), T.glass, parent=holder)
            box("step", root, (door_x, -d / 2 - 0.45, 0.2), (1.6, 0.9, 0.4), T.sill, parent=holder)
    for e in (-1, 1):
        holder = bpy.data.objects.new("side", None)
        root.objects.link(holder)
        holder.parent = g
        holder.rotation_euler.z = e * math.pi / 2
        for zi, zc in enumerate(zs):
            if zc is None:
                continue
            for x in ((-d / 4, d / 4) if zi < 1 else (0.0,)):
                window(T, root, holder, x, zc, 1.0, 1.25, -w / 2, rnd)
    # garage beside the house
    gar = garage if garage is not None else rnd.random() < 0.6
    if gar:
        gs = -1 if door_x > 0 else 1
        gx = gs * (w / 2 + 1.8)
        box("garage", root, (gx, -d / 2 + 3.0, 1.35), (3.4, 6.0, 2.7), wall, parent=g)
        box("garage_roof", root, (gx, -d / 2 + 3.0, 2.75), (3.6, 6.2, 0.14), T.zinc, parent=g)
        box("garage_door", root, (gx, -d / 2 - 0.01, 1.1), (2.5, 0.05, 2.15), T.garage, parent=g)
    g["w"], g["d"], g["garage"] = w, d, bool(gar)
    g["garage_x"] = (-1 if door_x > 0 else 1) * (w / 2 + 1.8) if gar else 0.0
    g["door_x"] = door_x
    return root


# ------------------------------------------------------------------ garden things
def hedge(T, c, a, b, h=1.2, t=0.7):
    a, b = Vector(a), Vector(b)
    mid = (a + b) / 2
    L = (b - a).length
    o = box("hedge", c, (mid.x, mid.y, KERB_H + h / 2), (L, t, h), T.hedge, rot_z=math.atan2(b.y - a.y, b.x - a.x),
            bevel=0.18)
    d = o.modifiers.new("d", "DISPLACE")
    d.texture = bpy.data.textures.get("hedge_tex") or bpy.data.textures.new("hedge_tex", "CLOUDS")
    d.texture.noise_scale = 0.4
    d.strength = 0.12
    o.modifiers["b"].segments = 3
    sub = o.modifiers.new("s", "SUBSURF")
    sub.levels = sub.render_levels = 2
    o.modifiers.move(2, 1)
    return o


def fence(T, c, a, b, h=0.9):
    """Wooden picket fence (pickets every 0.12 m on two rails)."""
    a, b = Vector(a), Vector(b)
    L = (b - a).length
    t = (b - a).normalized()
    ang = math.atan2(t.y, t.x)
    objs = []
    for z in (KERB_H + 0.25, KERB_H + h - 0.2):
        m = (a + b) / 2
        objs.append(box("rail", c, (m.x, m.y, z), (L, 0.03, 0.06), T.wood, rot_z=ang))
    n = int(L / 0.12)
    for k in range(n):
        p = a + t * (k + 0.5) * (L / n)
        objs.append(box("picket", c, (p.x, p.y, KERB_H + h / 2), (0.07, 0.02, h), T.wood, rot_z=ang))
    return objs


def wheelie_bin(T, c, loc, kind="grey", rz=0.0):
    m = T.bins[kind]
    o = box("bin", c, (loc[0], loc[1], KERB_H + 0.52), (0.58, 0.72, 1.04), m, rot_z=rz, bevel=0.03)
    lid = box("bin_lid", c, (loc[0], loc[1], KERB_H + 1.07), (0.62, 0.78, 0.05), m, rot_z=rz, bevel=0.015)
    return [o, lid]


def street_lamp(T, c, loc, rz=0.0, h=5.0):
    """Residential street light: grey pole, short arm over the road, flat LED head."""
    x, y = loc
    p = cyl("lamp_pole", c, (x, y, KERB_H + h / 2), 0.06, h, T.pole, 12)
    arm_dir = Vector((math.cos(rz), math.sin(rz)))
    am = Vector((x, y)) + arm_dir * 0.55
    a = box("lamp_arm", c, (am.x, am.y, KERB_H + h - 0.05), (1.1, 0.08, 0.08), T.pole, rot_z=rz)
    hd = Vector((x, y)) + arm_dir * 1.15
    head = box("lamp_head", c, (hd.x, hd.y, KERB_H + h - 0.12), (0.7, 0.32, 0.12), T.pole, rot_z=rz, bevel=0.03)
    gl = box("lamp_lens", c, (hd.x, hd.y, KERB_H + h - 0.19), (0.6, 0.26, 0.02), T.lamp_glass, rot_z=rz)
    return [p, a, head, gl]


def manhole(T, c, x, y):
    return cyl("manhole", c, (x, y, 0.006), 0.32, 0.012, T.manhole, 32)


def gully(T, c, x, y, rz=0.0):
    return box("gully", c, (x, y, 0.006), (0.5, 0.32, 0.012), T.manhole, rot_z=rz)


# ------------------------------------------------------------------ road markings
def haifisch(T, c, p, u, n, width, size=0.6, gap=0.25):
    """Zeichen 342 shark teeth: a row centred on p (2D), running along unit vector u over `width`, each triangle
    pointing along n (towards the driver who must wait)."""
    p, u, n = Vector(p), Vector(u).normalized(), Vector(n).normalized()
    objs = []
    k_ = int((width + gap) / (size + gap))
    tot = k_ * size + (k_ - 1) * gap
    for k in range(k_):
        a = p + u * (-tot / 2 + k * (size + gap))
        b = a + u * size
        tip = (a + b) / 2 + n * size * 1.35
        v = [(a.x, a.y, 0.008), (b.x, b.y, 0.008), (tip.x, tip.y, 0.008)]
        o = W.mesh_obj("zahn", v, [(0, 1, 2)], T.paint, c, uvs=[(0, 0), (1, 0), (0.5, 1)])
        if o.data.polygons[0].normal.z < 0:
            o.data.flip_normals()
        objs.append(o)
    return objs


def bar(T, c, x0, x1, y0, y1, z=0.008, name="line"):
    return W.mesh_obj(name, [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [(0, 1, 2, 3)], T.paint, c,
                      uvs=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


# ------------------------------------------------------------------ signs (all face -y; post at the origin)
def _parts_to(root_obj, parts, z):
    for p in parts:
        p.parent = root_obj
        p.location.z += z


def tri_outline(side, up=True):
    h = side * math.sqrt(3) / 2
    if up:
        return [(-side / 2, -h / 3), (side / 2, -h / 3), (0, 2 * h / 3)]
    return [(side / 2, h / 3), (-side / 2, h / 3), (0, -2 * h / 3)]


def rounded_poly(pts, r, seg=4):
    """Round the corners of a convex polygon (2D) by r."""
    out = []
    n = len(pts)
    for i in range(n):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % n])
        a = (p0 - p1).normalized()
        b = (p2 - p1).normalized()
        ang = math.acos(max(-1, min(1, a.dot(b))))
        dist = r / math.tan(ang / 2)
        c_ = p1 + (a + b).normalized() * (r / math.sin(ang / 2))
        s = p1 + a * dist
        e = p1 + b * dist
        a0 = math.atan2(s.y - c_.y, s.x - c_.x)
        a1 = math.atan2(e.y - c_.y, e.x - c_.x)
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        for k in range(seg + 1):
            t = a0 + da * k / seg
            out.append((c_.x + r * math.cos(t), c_.y + r * math.sin(t)))
    return out


def scale_poly(pts, k):
    return [(x * k, y * k) for x, y in pts]


def sign_triangle(T, c, name, up, inner_fn=None, side=0.9, height=2.3):
    """Danger / priority triangles: red border, white field, thin white outer edge, grey back."""
    M = T.M
    root = bpy.data.collections.new(name)
    c.children.link(root)
    g = bpy.data.objects.new(name, None)
    root.objects.link(g)
    outer = rounded_poly(tri_outline(side, up), side * 0.045)
    parts = [W.plate(name + "_rim", outer, 0.004, M.swhite, root, 0.0),
             W.plate(name + "_red", rounded_poly(tri_outline(side * 0.955, up), side * 0.04), 0.002, M.sred, root,
                     0.0025),
             W.plate(name + "_field", rounded_poly(tri_outline(side * 0.62, up), side * 0.02), 0.002, M.swhite,
                     root, 0.0045),
             W.plate(name + "_back", outer, 0.004, M.sback, root, -0.006)]
    if inner_fn:
        parts += inner_fn(root, side)
    _parts_to(g, parts, height)
    cyl("post", root, (0, 0.05, (height + 0.3) / 2), 0.038, height + 0.3, M.steel).parent = g
    return root


def sign_205(T, c, height=2.3):
    return sign_triangle(T, c, "z205", up=False, height=height)


def sign_102(T, c, height=2.3):
    M = T.M

    def inner(root, side):
        parts = []
        h = side * math.sqrt(3) / 2
        cy = h * 0.04
        L, w = side * 0.34, side * 0.07
        for ang in (45, -45):
            a = math.radians(ang)
            pts = [(-L / 2, -w / 2), (L / 2, -w / 2), (L / 2, w / 2), (-L / 2, w / 2)]
            pts = [(x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a) + cy) for x, y in pts]
            parts.append(W.plate("z102_x", pts, 0.001, M.sblack, root, 0.0075))
        return parts
    return sign_triangle(T, c, "z102", up=True, inner_fn=inner, height=height)


def sign_301(T, c, height=2.3):
    """Priority at the next junction: black upright bar (wider at the foot) crossed by a thin bar."""
    M = T.M

    def inner(root, side):
        h = side * math.sqrt(3) / 2
        y0, y1 = -h / 3 + side * 0.13, -h / 3 + side * 0.55
        bw0, bw1 = side * 0.075, side * 0.04
        pts = [(-bw0 / 2, y0), (bw0 / 2, y0), (bw1 / 2, y1), (0, y1 + side * 0.03), (-bw1 / 2, y1)]
        a = W.plate("z301_bar", pts, 0.001, M.sblack, root, 0.0075)
        yc = y0 + (y1 - y0) * 0.55
        ww = side * 0.26
        b = W.plate("z301_cross", [(-ww / 2, yc - side * 0.014), (ww / 2, yc - side * 0.014),
                                   (ww / 2, yc + side * 0.014), (-ww / 2, yc + side * 0.014)], 0.001, M.sblack,
                    root, 0.0075)
        return [a, b]
    return sign_triangle(T, c, "z301", up=True, inner_fn=inner, height=height)


def sign_306(T, c, height=2.3, size=0.6):
    """Priority road: yellow square on its point, white border, thin black edge."""
    M = T.M
    root = bpy.data.collections.new("z306")
    c.children.link(root)
    g = bpy.data.objects.new("z306", None)
    root.objects.link(g)
    d = size / 2 * math.sqrt(2)

    def diamond(k):
        return rounded_poly([(0, -d * k), (d * k, 0), (0, d * k), (-d * k, 0)], size * 0.03 * k)
    parts = [W.plate("z306_edge", diamond(1.0), 0.004, M.sblack, root, 0.0),
             W.plate("z306_white", diamond(0.97), 0.002, M.swhite, root, 0.0025),
             W.plate("z306_yellow", diamond(0.7), 0.002, T.yellow, root, 0.0045),
             W.plate("z306_back", diamond(1.0), 0.004, M.sback, root, -0.006)]
    _parts_to(g, parts, height)
    cyl("post", root, (0, 0.05, (height + 0.2) / 2), 0.038, height + 0.2, M.steel).parent = g
    return root


def sign_206(T, c, height=2.3, size=0.6):
    M = T.M
    root = bpy.data.collections.new("z206")
    c.children.link(root)
    g = bpy.data.objects.new("z206", None)
    root.objects.link(g)

    def octa(r):
        return [(r * math.cos(math.radians(22.5 + 45 * k)), r * math.sin(math.radians(22.5 + 45 * k)))
                for k in range(8)]
    r = size / 2 / math.cos(math.radians(22.5))
    parts = [W.plate("z206_rim", octa(r), 0.004, M.swhite, root, 0.0),
             W.plate("z206_red", octa(r * 0.93), 0.002, M.sred, root, 0.0025),
             W.plate("z206_back", octa(r), 0.004, M.sback, root, -0.006)]
    t = W.text_obj("z206_txt", "STOP", size * 0.3, M.swhite, root, "CENTER", "CENTER", 0.001)
    t.rotation_euler = (math.radians(90), 0, 0)
    t.location = (0, -0.006, 0)
    parts.append(t)
    _parts_to(g, parts, height)
    cyl("post", root, (0, 0.05, (height + 0.2) / 2), 0.038, height + 0.2, M.steel).parent = g
    return root


def place(coll_, loc, rz, c, name=None):
    e = bpy.data.objects.new(name or coll_.name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = coll_
    e.location = loc
    e.rotation_euler = (0, 0, rz)
    c.objects.link(e)
    return e


def facing(direction_of_traffic):
    """Rotation for a sign (front faces -y) so that drivers travelling in direction (dx, dy) see its face."""
    dx, dy = direction_of_traffic
    return math.atan2(dy, dx) - math.pi / 2


# ------------------------------------------------------------------ traffic lights
class SignalGroup:
    """Three lamp materials (red, yellow, green) shared by all heads of one signal group, keyable."""

    def __init__(self, name):
        self.name = name
        self.mats = {}
        for k, col in (("red", (1.0, 0.01, 0.005)), ("yellow", (1.0, 0.42, 0.0)), ("green", (0.0, 1.0, 0.3))):
            m = bpy.data.materials.new(f"{name}_{k}")
            m.use_nodes = True
            p = m.node_tree.nodes["Principled BSDF"]
            p.inputs["Base Color"].default_value = (col[0] * 0.08, col[1] * 0.08, col[2] * 0.08, 1)
            p.inputs["Emission Color"].default_value = (*col, 1)
            p.inputs["Emission Strength"].default_value = 0.0
            p.inputs["Roughness"].default_value = 0.15
            p.inputs["Coat Weight"].default_value = 1.0
            self.mats[k] = m

    def key(self, frame, state):
        """state: 'red', 'redyellow', 'green', 'yellow', 'off'."""
        on = {"red": ("red",), "redyellow": ("red", "yellow"), "green": ("green",), "yellow": ("yellow",),
              "off": ()}[state]
        for k, m in self.mats.items():
            inp = m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
            inp.default_value = 3.5 if k in on else 0.0
            inp.keyframe_insert("default_value", frame=frame)

    def constant(self):
        import stage
        for m in self.mats.values():
            for fc in stage.fcurves(m.node_tree):
                for kp in fc.keyframe_points:
                    kp.interpolation = "CONSTANT"


def traffic_light(T, c, group, name="ampel", height=2.9, gruenpfeil=False, arm=0.0):
    """German 3-aspect signal (200 mm lamps), black housing with visors, white contrast plate with red border,
    on a grey pole. Faces -y. Optional Zeichen 720 green arrow plate right of the red lamp."""
    M = T.M
    root = bpy.data.collections.new(name)
    c.children.link(root)
    g = bpy.data.objects.new(name, None)
    root.objects.link(g)
    housing = W.principled("signal_housing", (0.02, 0.02, 0.022), 0.45)
    cyl("pole", root, (0, 0.0, (height + 0.9) / 2), 0.07, height + 0.9, T.pole, 16).parent = g
    hx = arm
    zc = height + 0.45
    plate = W.plate("contrast_red", W.rounded_rect(0.62, 1.22, 0.05), 0.01, M.sred, root, 0.11)
    plate2 = W.plate("contrast_white", W.rounded_rect(0.54, 1.14, 0.04), 0.008, M.swhite, root, 0.122)
    for p in (plate, plate2):
        p.location = (hx, 0.0, zc)
        p.parent = g
    box("housing", root, (hx, -0.04, zc), (0.3, 0.24, 0.96), housing, bevel=0.03, parent=g)
    for k, (key, dz) in enumerate((("red", 0.3), ("yellow", 0.0), ("green", -0.3))):
        lamp = cyl("lamp_" + key, root, (hx, -0.165, zc + dz), 0.1, 0.02, group.mats[key], 32,
                   (math.pi / 2, 0, 0))
        lamp.parent = g
        # visor: upper half of a short tube in front of the lamp
        me = bpy.data.meshes.new("visor")
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=False, segments=24, radius1=0.125, radius2=0.125, depth=0.2)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y < -0.02], context="VERTS")
        bm.to_mesh(me)
        bm.free()
        v = bpy.data.objects.new("visor", me)
        root.objects.link(v)
        v.location = (hx, -0.27, zc + dz)
        v.rotation_euler = (math.pi / 2, 0, 0)
        sol = v.modifiers.new("s", "SOLIDIFY")
        sol.thickness = 0.01
        me.materials.append(housing)
        v.parent = g
    if gruenpfeil:
        # Zeichen 720: black plate 250 x 250 mm with a green arrow pointing right, right of the red lamp
        px, pz = hx + 0.31 + 0.13, zc + 0.3
        bp = W.plate("z720", W.rounded_rect(0.25, 0.25, 0.015), 0.01, M.sblack, root, 0.0)
        bp.location = (px, -0.2, pz)
        bp.parent = g
        s = 0.25
        arrow = [(-0.38 * s, -0.06 * s), (0.08 * s, -0.06 * s), (0.08 * s, -0.19 * s), (0.38 * s, 0.0),
                 (0.08 * s, 0.19 * s), (0.08 * s, 0.06 * s), (-0.38 * s, 0.06 * s)]
        ar = W.plate("z720_arrow", arrow, 0.002, T.sgreen_arrow, root, 0.003)
        ar.location = (px, -0.2, pz)
        ar.parent = g
        box("z720_bracket", root, (px - 0.12, -0.12, pz), (0.06, 0.12, 0.04), T.pole, parent=g)
    return root
