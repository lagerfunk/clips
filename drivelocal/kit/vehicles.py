"""Stylised but correctly proportioned European traffic: hatchback, estate, saloon, SUV, panel van, German police
estate, 40 t articulated lorry. Bodies are subdivision cages built from cross-section stations, wheel arches cut with
booleans, lights and plates placed by ray casting onto the body. Front is +y, ground is z = 0, centre x = 0."""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

import world as W


def S(y, zb, zs, zbelt, w, zr, wr, zwin=None, wwin=None):
    if zwin is None:
        if zr - zbelt > 0.25:
            zwin, wwin = zr - 0.05, wr + 0.03
        else:
            zwin, wwin = (zbelt + zr) / 2, (w + wr) / 2
    return (y, zb, zs, zbelt, w, zwin, wwin, zr, wr)


# half-widths are fractions of the car's half width; heights in metres
KINDS = {
    "hatch": dict(L=4.28, W=0.90, r=0.32, axles=(0.76, 3.40), stations=[
        S(0.00, 0.44, 0.58, 0.86, 0.80, 0.98, 0.62),
        S(0.07, 0.30, 0.52, 0.92, 0.92, 1.00, 0.74),
        S(0.24, 0.26, 0.50, 0.94, 0.94, 1.42, 0.68),
        S(0.80, 0.24, 0.50, 0.95, 0.96, 1.50, 0.72),
        S(1.80, 0.24, 0.50, 0.96, 0.97, 1.51, 0.73),
        S(1.90, 0.24, 0.50, 0.96, 0.97, 1.51, 0.73),
        S(2.50, 0.24, 0.50, 0.96, 0.97, 1.48, 0.72),
        S(3.18, 0.25, 0.50, 0.94, 0.96, 1.00, 0.82),
        S(3.72, 0.26, 0.50, 0.86, 0.94, 0.90, 0.82),
        S(4.13, 0.30, 0.50, 0.76, 0.90, 0.79, 0.74),
        S(4.28, 0.36, 0.52, 0.66, 0.78, 0.70, 0.56)],
        spans="bfbgbgfbbb"),
    "estate": dict(L=4.77, W=0.92, r=0.33, axles=(1.06, 3.85), stations=[
        S(0.00, 0.44, 0.58, 0.84, 0.82, 1.00, 0.62),
        S(0.07, 0.30, 0.52, 0.92, 0.92, 1.02, 0.74),
        S(0.22, 0.26, 0.50, 0.94, 0.94, 1.44, 0.68),
        S(0.55, 0.25, 0.50, 0.95, 0.96, 1.49, 0.71),
        S(1.30, 0.25, 0.50, 0.95, 0.97, 1.50, 0.72),
        S(1.42, 0.25, 0.50, 0.95, 0.97, 1.50, 0.72),
        S(2.22, 0.25, 0.50, 0.96, 0.97, 1.50, 0.73),
        S(2.32, 0.25, 0.50, 0.96, 0.97, 1.50, 0.73),
        S(2.95, 0.25, 0.50, 0.96, 0.97, 1.47, 0.72),
        S(3.62, 0.26, 0.50, 0.93, 0.96, 0.99, 0.82),
        S(4.18, 0.27, 0.50, 0.85, 0.94, 0.89, 0.82),
        S(4.62, 0.30, 0.50, 0.75, 0.90, 0.78, 0.74),
        S(4.77, 0.36, 0.52, 0.65, 0.78, 0.69, 0.56)],
        spans="bfbgbgbgfbbb"),
    "saloon": dict(L=4.71, W=0.915, r=0.33, axles=(1.04, 3.89), stations=[
        S(0.00, 0.44, 0.58, 0.84, 0.82, 0.90, 0.64),
        S(0.10, 0.32, 0.52, 0.90, 0.92, 0.98, 0.76),
        S(0.55, 0.28, 0.50, 0.93, 0.95, 1.00, 0.76),
        S(1.22, 0.26, 0.50, 0.95, 0.96, 1.42, 0.68),
        S(1.38, 0.25, 0.50, 0.95, 0.97, 1.44, 0.70),
        S(2.20, 0.25, 0.50, 0.96, 0.97, 1.45, 0.72),
        S(2.30, 0.25, 0.50, 0.96, 0.97, 1.45, 0.72),
        S(2.95, 0.25, 0.50, 0.96, 0.97, 1.42, 0.71),
        S(3.66, 0.26, 0.50, 0.92, 0.96, 0.98, 0.82),
        S(4.20, 0.27, 0.50, 0.84, 0.94, 0.88, 0.82),
        S(4.56, 0.30, 0.50, 0.74, 0.90, 0.77, 0.74),
        S(4.71, 0.36, 0.52, 0.64, 0.78, 0.68, 0.56)],
        spans="bbfbgbgfbbb"),
    "suv": dict(L=4.60, W=0.93, r=0.36, axles=(0.95, 3.70), stations=[
        S(0.00, 0.50, 0.66, 1.02, 0.84, 1.16, 0.66),
        S(0.08, 0.36, 0.60, 1.06, 0.93, 1.16, 0.77),
        S(0.24, 0.32, 0.58, 1.08, 0.95, 1.62, 0.72),
        S(0.62, 0.32, 0.58, 1.09, 0.97, 1.68, 0.76),
        S(1.30, 0.32, 0.58, 1.09, 0.98, 1.69, 0.77),
        S(1.42, 0.32, 0.58, 1.09, 0.98, 1.69, 0.77),
        S(2.20, 0.32, 0.58, 1.10, 0.98, 1.69, 0.77),
        S(2.30, 0.32, 0.58, 1.10, 0.98, 1.69, 0.77),
        S(2.90, 0.32, 0.58, 1.10, 0.98, 1.66, 0.76),
        S(3.48, 0.33, 0.58, 1.07, 0.97, 1.13, 0.84),
        S(4.05, 0.34, 0.58, 1.00, 0.95, 1.04, 0.84),
        S(4.46, 0.38, 0.60, 0.90, 0.91, 0.93, 0.76),
        S(4.60, 0.44, 0.62, 0.80, 0.80, 0.84, 0.58)],
        spans="bfbgbgbgfbbb"),
    "van": dict(L=5.93, W=1.01, r=0.36, axles=(1.29, 4.95), stations=[
        S(0.00, 0.42, 0.62, 1.20, 0.94, 2.56, 0.86, 2.20, 0.92),
        S(0.06, 0.36, 0.60, 1.20, 0.99, 2.62, 0.93, 2.25, 0.97),
        S(4.12, 0.36, 0.60, 1.20, 1.00, 2.64, 0.94, 2.25, 0.98),
        S(4.22, 0.36, 0.60, 1.20, 1.00, 2.64, 0.94, 2.25, 0.98),
        S(4.86, 0.36, 0.60, 1.16, 1.00, 2.58, 0.93, 2.05, 0.97),
        S(5.46, 0.38, 0.60, 1.14, 0.99, 1.22, 0.86, 1.18, 0.92),
        S(5.84, 0.42, 0.62, 1.00, 0.96, 1.07, 0.82, 1.04, 0.88),
        S(5.93, 0.46, 0.64, 0.90, 0.86, 0.95, 0.66, 0.93, 0.76)],
        spans="bbbgfbb", crease=1.3),
}

_mats = {}


def mat(key, *a, **k):
    if key not in _mats:
        _mats[key] = W.principled(key, *a, **k)
    return _mats[key]


def common():
    return dict(
        glass=mat("car_glass", (0.012, 0.016, 0.02), 0.04, spec=0.8, coat=1.0),
        tyre=mat("car_tyre", (0.025, 0.025, 0.025), 0.75),
        rim=mat("car_rim", (0.72, 0.73, 0.75), 0.28, metal=1.0),
        plastic=mat("car_plastic", (0.03, 0.03, 0.032), 0.55),
        head=mat("car_head", (0.9, 0.9, 0.88), 0.1, emit=(1, 0.97, 0.9), estr=1.5),
        tail=mat("car_tail", (0.5, 0.01, 0.01), 0.15, emit=(1, 0.03, 0.02), estr=0.8),
        plate=mat("car_plate", (0.88, 0.88, 0.86), 0.35),
        euband=mat("car_euband", (0.0, 0.05, 0.35), 0.4),
        plate_txt=mat("car_plate_txt", (0.01, 0.01, 0.01), 0.5),
        arch=mat("car_arch", (0.012, 0.012, 0.012), 0.8),
    )


def paint(name, color, metal=0.45):
    return mat("paint_" + name, color, 0.28, metal=metal, coat=1.0)


CREASE_LONG = {1: 0.7, 8: 0.7, 2: 0.55, 7: 0.55, 3: 0.75, 6: 0.75, 4: 0.6, 5: 0.6}


def body_mesh(kind, body_mat, glass_mat, trim_mat, band=None):
    """Material slots: 0 paint, 1 glass, 2 dark lower trim, 3 police band."""
    k = KINDS[kind]
    Wh = k["W"]
    st = k["stations"]
    spans = k["spans"]
    bm = bmesh.new()
    cl = bm.edges.layers.float.new("crease_edge")
    rings = []
    for (y, zb, zs, zbelt, w, zwin, wwin, zr, wr) in st:
        pts = [(-0.9 * w, zb), (-w, zs), (-0.985 * w, zbelt), (-wwin, zwin), (-wr, zr),
               (wr, zr), (wwin, zwin), (0.985 * w, zbelt), (w, zs), (0.9 * w, zb)]
        rings.append([bm.verts.new((px * Wh, y, pz)) for px, pz in pts])
    n = 10
    glass_edges = set()
    for i in range(len(rings) - 1):
        t = spans[i]
        for j in range(n):
            j2 = (j + 1) % n
            f = bm.faces.new((rings[i][j], rings[i][j2], rings[i + 1][j2], rings[i + 1][j]))
            idx = 0
            if t == "g" and j in (2, 6):
                idx = 1
            elif t == "f" and j == 4:
                idx = 1
            elif j in (0, 8, 9):
                idx = 2
            elif band and j in (1, 7) and band[0] <= rings[i][0].co.y <= band[1]:
                idx = 3
            f.material_index = idx
            if idx == 1:
                glass_edges.update(((i, j), (i + 1, j)))
    # end caps as a strip of quads across the car: bumper (trim), lower panel, upper panel, top
    for ring_, flip in ((rings[0], True), (rings[-1], False)):
        for (a1, a2, b2, b1), idx in (((0, 1, 8, 9), 2), ((1, 2, 7, 8), 0), ((2, 3, 6, 7), 0), ((3, 4, 5, 6), 0)):
            q = [ring_[a1], ring_[a2], ring_[b2], ring_[b1]]
            f = bm.faces.new(list(reversed(q)) if flip else q)
            f.material_index = idx
    bm.edges.ensure_lookup_table()
    for e in bm.edges:
        a_, b_ = e.verts
        ia = next((ii, jj) for ii, r in enumerate(rings) for jj, v in enumerate(r) if v is a_)
        ib = next((ii, jj) for ii, r in enumerate(rings) for jj, v in enumerate(r) if v is b_)
        if ia[1] == ib[1] and abs(ia[0] - ib[0]) == 1:          # along the car
            e[cl] = min(1.0, CREASE_LONG.get(ia[1], 0.0) * k.get("crease", 1.0))
        elif ia[0] == ib[0]:                                     # around a station, or across an end cap
            lo = min(ia, ib, key=lambda q: q[1])
            if (lo[0], lo[1]) in glass_edges and abs(ia[1] - ib[1]) == 1:
                e[cl] = 0.7
            if ia[0] in (0, len(rings) - 1) and {ia[1], ib[1]} == {1, 8}:
                e[cl] = 0.9
            elif ia[0] in (0, len(rings) - 1) and {ia[1], ib[1]} in ({1, 2}, {7, 8}, {0, 1}, {8, 9}):
                e[cl] = 0.7
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(kind + "_cage")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(body_mat)
    me.materials.append(glass_mat)
    me.materials.append(trim_mat)
    if band:
        me.materials.append(band[2])
    return me


def bake(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    bpy.data.meshes.remove(old)
    return obj


def stick(root_coll, parent, body, origin, direction, size, m, up=(0, 0, 1), embed=0.01, bevel=0.02, name="part"):
    """Ray-cast from origin along direction onto the body and place a small bevelled box there, aligned to the hit
    normal (local +y along the normal)."""
    hit, loc, nrm, _i = body.ray_cast(Vector(origin), Vector(direction).normalized(), distance=5.0)
    if not hit:
        return None
    bpy.ops.mesh.primitive_cube_add()
    o = W.link(bpy.context.active_object, root_coll)
    o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        b = o.modifiers.new("b", "BEVEL")
        b.width, b.segments = bevel, 2
    o.data.materials.append(m)
    q = nrm.to_track_quat("Y", "Z")
    o.matrix_world = Matrix.Translation(loc + nrm * (size[1] / 2 - embed)) @ q.to_matrix().to_4x4()
    o.parent = parent
    o.matrix_parent_inverse = parent.matrix_world.inverted()
    return o


def plate_text(root_coll, parent, body, origin, direction, text, C, name="plate"):
    """German plate: white, EU band on the viewer's left. A sticker's local +y is the outward normal, so the viewer's
    right is local -x."""
    p = stick(root_coll, parent, body, origin, direction, (0.52, 0.012, 0.11), C["plate"], bevel=0.004, name=name)
    if not p:
        return
    band = stick(root_coll, parent, body, origin, direction, (0.045, 0.014, 0.105), C["euband"], bevel=0.0,
                 name=name + "_eu")
    if band:
        band.matrix_world = p.matrix_world @ Matrix.Translation((0.235, 0.001, 0))
    t = W.text_obj(name + "_txt", text, 0.075, C["plate_txt"], root_coll, "CENTER", "CENTER", 0.001)
    t.matrix_world = (p.matrix_world @ Matrix.Translation((-0.02, 0.0065, 0)) @ Matrix.Rotation(math.pi, 4, "Z")
                      @ Matrix.Rotation(math.radians(90), 4, "X"))
    t.parent = parent
    t.matrix_parent_inverse = parent.matrix_world.inverted()


def car(kind, color, name, plate_txt="F LK 202", metal=0.45, police=False, c=None):
    """Returns a collection holding a complete car, origin on the ground at the middle of the car."""
    C = common()
    k = KINDS[kind]
    L, Wh, r = k["L"], k["W"], k["r"]
    root = bpy.data.collections.new(name)
    (c or bpy.context.scene.collection).children.link(root)
    g = bpy.data.objects.new(name, None)
    root.objects.link(g)
    if police:
        body_m = mat("paint_police_silver", (0.82, 0.83, 0.85), 0.3, metal=0.5, coat=1.0)
        band = (k["axles"][0] - 0.3, k["axles"][1] + 0.1, mat("police_blue", (0.0, 0.03, 0.22), 0.3, coat=1.0))
    else:
        body_m = paint(name, color, metal)
        band = None
    me = body_mesh(kind, body_m, C["glass"], C["plastic"], band)
    body = bpy.data.objects.new(name + "_body", me)
    root.objects.link(body)
    sub = body.modifiers.new("sub", "SUBSURF")
    sub.levels = sub.render_levels = 2
    cutters = []
    for ay in k["axles"]:
        bpy.ops.mesh.primitive_cylinder_add(vertices=40, radius=r + 0.055, depth=Wh * 2 + 0.4, location=(0, ay, r),
                                            rotation=(0, math.pi / 2, 0))
        cu = bpy.context.active_object
        cu.data.materials.append(C["arch"])
        cutters.append(cu)
        bo = body.modifiers.new("arch", "BOOLEAN")
        bo.object = cu
        bo.operation = "DIFFERENCE"
        bo.solver = "EXACT"
        bo.material_mode = "TRANSFER"
    bake(body)
    for cu in cutters:
        bpy.data.objects.remove(cu)
    for p in body.data.polygons:
        p.use_smooth = True
    body.parent = g
    zbelt = k["stations"][len(k["stations"]) // 2][3]
    # wheels
    for ay in k["axles"]:
        for sx in (-1, 1):
            x = sx * (Wh - 0.14)
            bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=r, depth=0.23, location=(x, ay, r),
                                                rotation=(0, math.pi / 2, 0))
            ty = W.link(bpy.context.active_object, root)
            b = ty.modifiers.new("b", "BEVEL")
            b.width, b.segments = 0.06, 3
            ty.data.materials.append(C["tyre"])
            bpy.ops.object.shade_smooth()
            ty.parent = g
            bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=r * 0.62, depth=0.02,
                                                location=(x + sx * 0.112, ay, r), rotation=(0, math.pi / 2, 0))
            rm = W.link(bpy.context.active_object, root)
            rm.data.materials.append(C["rim"])
            rm.parent = g
    # lights, grille, plates, mirrors (ray cast onto the baked body)
    front_z = k["stations"][-2][3] - 0.08
    rear_z = k["stations"][1][3] - 0.02
    for sx in (-1, 1):
        stick(root, g, body, (sx * Wh * 0.62, L + 1.0, front_z), (0, -1, 0), (0.36, 0.04, 0.11), C["head"],
              name="headlight", embed=0.028, bevel=0.012)
        stick(root, g, body, (sx * Wh * 0.72, -1.0, rear_z), (0, 1, 0), (0.34, 0.04, 0.1), C["tail"],
              name="taillight", embed=0.028, bevel=0.012)
        stick(root, g, body, (sx * (Wh + 1.0), 0.16, rear_z), (-sx, 0, 0), (0.2, 0.04, 0.09), C["tail"],
              name="taillight_side", embed=0.028, bevel=0.012)
        mz = zbelt + 0.12
        cab = [i for i, s in enumerate(k["stations"]) if s[7] - s[3] > 0.25]
        my = k["stations"][cab[-1] + 1][0] - 0.3
        stick(root, g, body, (sx * (Wh + 1.0), my, mz), (-sx, 0, 0), (0.1, 0.17, 0.12), body_m, name="mirror",
              bevel=0.03, embed=0.02)
    stick(root, g, body, (0, L + 1.0, front_z - 0.17), (0, -1, 0), (Wh * 0.85, 0.05, 0.16), C["plastic"],
          name="grille")
    plate_text(root, g, body, (0, L + 1.0, front_z - 0.32), (0, -1, 0), plate_txt, C, "plate_f")
    plate_text(root, g, body, (0, -1.0, rear_z - 0.22), (0, 1, 0), plate_txt, C, "plate_r")
    # small details that sell it up close: badge, third brake light, rear wiper, reflectors, exhausts, roof rails
    chrome = mat("car_chrome", (0.8, 0.8, 0.82), 0.15, metal=1.0)
    stick(root, g, body, (0, -1.0, rear_z - 0.06), (0, 1, 0), (0.12, 0.02, 0.06), chrome, name="badge", bevel=0.008,
          embed=0.006)
    rg = [s_ for s_ in k["stations"][:4] if s_[7] - s_[3] > 0.25]
    if rg and kind != "saloon":
        zt = rg[0][7] - 0.06
        stick(root, g, body, (0, -1.0, zt), (0, 1, 0), (0.3, 0.02, 0.035), C["tail"], name="brake3", bevel=0.006,
              embed=0.004)
        stick(root, g, body, (0.12, -1.0, zt - 0.32), (0, 1, 0), (0.42, 0.015, 0.02), C["plastic"], name="wiper",
              bevel=0.0, embed=0.002)
    for sx in (-1, 1):
        stick(root, g, body, (sx * Wh * 0.72, -1.0, k["stations"][0][2] - 0.05), (0, 1, 0), (0.16, 0.012, 0.04),
              C["tail"], name="reflector", bevel=0.0, embed=0.003)
    if kind != "van":
        bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.04, depth=0.2, location=(-Wh * 0.55, 0.13, 0.27),
                                            rotation=(math.pi / 2, 0, 0))
        ex = W.link(bpy.context.active_object, root)
        ex.data.materials.append(chrome)
        ex.parent = g
    if False:  # roof rails read as antennas at this scale
        roof_z = max(s_[7] for s_ in k["stations"])
        ys = [s_[0] for s_ in k["stations"] if s_[7] > roof_z - 0.04]
        y0, y1 = min(ys) + 0.1, max(ys) - 0.1
        for sx in (-1, 1):
            hit, loc, nrm, _i = body.ray_cast(Vector((sx * Wh * 0.6, (y0 + y1) / 2, roof_z + 1)), Vector((0, 0, -1)))
            if hit:
                bpy.ops.mesh.primitive_cube_add(location=(sx * Wh * 0.6, (y0 + y1) / 2, loc.z + 0.025))
                rr = W.link(bpy.context.active_object, root)
                rr.scale = (0.022, (y1 - y0) * 0.36, 0.022)
                bv = rr.modifiers.new("b", "BEVEL")
                bv.width, bv.segments = 0.012, 2
                rr.data.materials.append(chrome if kind == "estate" else C["plastic"])
                rr.parent = g
    if police:
        roof_z = max(s[7] for s in k["stations"])
        bar_m = mat("police_bar", (0.05, 0.2, 1.0), 0.2, emit=(0.1, 0.3, 1.0), estr=4.0)
        stick(root, g, body, (0, L * 0.45, roof_z + 1.0), (0, 0, -1), (1.1, 0.16, 0.3), bar_m, name="lightbar",
              bevel=0.05)
        white = mat("police_text", (0.95, 0.95, 0.95), 0.3)
        for sx in (-1, 1):
            hit, loc, nrm, _i = body.ray_cast(Vector((sx * 2.0, (k["axles"][0] + k["axles"][1]) / 2, 0.68)),
                                              Vector((-sx, 0, 0)))
            if hit:
                t = W.text_obj("polizei", "POLIZEI", 0.2, white, root, "CENTER", "CENTER", 0.002)
                t.rotation_euler = (math.radians(90), 0, math.radians(90 if sx > 0 else -90))
                t.location = loc + nrm * 0.006
                t.parent = g
    # put the origin at the middle of the car
    for o in root.objects:
        if o.parent is g:
            o.location.y -= L / 2
    return root


def truck(name, cab_color, trailer_color, label="", label_color=(0.05, 0.12, 0.4), c=None, reefer=False):
    """Cab-over tractor (Actros-like proportions) and 13.6 m semi trailer. Origin at the middle, front +y."""
    C = common()
    root = bpy.data.collections.new(name)
    (c or bpy.context.scene.collection).children.link(root)
    g = bpy.data.objects.new(name, None)
    root.objects.link(g)
    cab_m = mat(name + "_cab", cab_color, 0.3, metal=0.2, coat=1.0)
    tr_m = mat(name + "_trailer", trailer_color, 0.5)
    dark = mat("truck_chassis", (0.035, 0.035, 0.035), 0.6)
    grey = mat("truck_grey", (0.25, 0.26, 0.27), 0.5)

    def bx(n_, loc, size, m, bev=0.0, seg=3):
        bpy.ops.mesh.primitive_cube_add(location=loc)
        o = W.link(bpy.context.active_object, root)
        o.name = n_
        o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
        bpy.ops.object.transform_apply(scale=True)
        if bev:
            b = o.modifiers.new("b", "BEVEL")
            b.width, b.segments = bev, seg
        o.data.materials.append(m)
        o.parent = g
        return o

    # tractor: cab 5.3 .. 7.6, floor at 1.15
    bx("cab", (0, 6.45, 2.45), (2.49, 2.25, 2.7), cab_m, 0.22, 4)
    bx("cab_roof", (0, 6.3, 3.95), (2.42, 1.95, 0.45), cab_m, 0.2, 4)
    bx("windscreen", (0, 7.565, 2.95), (2.18, 0.04, 1.05), C["glass"], 0.05)
    for sx in (-1, 1):
        bx("side_window", (sx * 1.246, 7.05, 2.95), (0.03, 0.75, 0.8), C["glass"], 0.04)
        bx("mirror_arm", (sx * 1.33, 7.45, 3.0), (0.2, 0.06, 0.06), dark)
        bx("mirror", (sx * 1.45, 7.48, 2.75), (0.08, 0.16, 0.6), dark, 0.03)
        bx("step", (sx * 1.1, 6.9, 0.85), (0.32, 0.6, 0.12), grey, 0.02)
        bx("headlight", (sx * 0.95, 7.59, 1.42), (0.42, 0.04, 0.18), C["head"], 0.03)
        bx("tank", (sx * 0.95, 3.9, 0.95), (0.55, 1.4, 0.6), mat("truck_alu", (0.7, 0.72, 0.74), 0.3, metal=1.0), 0.2)
    bx("grille", (0, 7.585, 1.85), (1.6, 0.04, 0.55), dark, 0.03)
    bx("bumper", (0, 7.55, 1.05), (2.45, 0.2, 0.42), grey, 0.06)
    bx("chassis", (0, 4.6, 0.95), (0.95, 6.2, 0.3), dark)
    # trailer -9.2 .. 4.4 (13.6 m), deck at 1.2, roof at 4.0
    tl = 13.6
    tc = 4.4 - tl / 2
    bx("trailer", (0, tc, 2.62), (2.55, tl, 2.76), tr_m, 0.05)
    bx("trailer_floor", (0, tc, 1.17), (2.52, tl, 0.16), dark)
    bx("skirt_l", (-1.2, tc - 1.0, 0.85), (0.04, 7.2, 0.5), grey)
    bx("skirt_r", (1.2, tc - 1.0, 0.85), (0.04, 7.2, 0.5), grey)
    if reefer:
        bx("reefer", (0, 4.44, 3.1), (2.1, 0.3, 1.3), grey, 0.08)
    for sx in (-1, 1):
        bx("taillight", (sx * 1.0, -9.215, 1.0), (0.38, 0.04, 0.14), C["tail"], 0.02)
    bx("underrun", (0, -9.0, 0.6), (2.3, 0.12, 0.14), grey)
    # rear doors: centre seam, lock bars, contour tape (ECE 104: red at the rear, white/yellow on the sides)
    bx("door_seam", (0, -9.205, 2.62), (0.02, 0.01, 2.6), dark)
    for x in (-0.95, -0.35, 0.35, 0.95):
        bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.022, depth=2.55, location=(x, -9.235, 2.62))
        o = W.link(bpy.context.active_object, root)
        o.data.materials.append(grey)
        o.parent = g
    tape_r = mat("tape_red", (0.6, 0.02, 0.01), 0.3, emit=(1, 0.05, 0.02), estr=0.15)
    tape_w = mat("tape_white", (0.85, 0.75, 0.2), 0.3, emit=(1, 0.85, 0.2), estr=0.1)
    for z in (1.3, 3.93):
        bx("tape_rear", (0, -9.215, z), (2.45, 0.006, 0.05), tape_r)
    for x in (-1.21, 1.21):
        bx("tape_rear_v", (x, -9.215, 2.62), (0.05, 0.006, 2.6), tape_r)
    for sx in (-1, 1):
        k_ = 0
        y = 3.9
        while y > -9.0:
            bx("tape_side", (sx * 1.279, y - 0.3, 1.32), (0.006, 0.6, 0.05), tape_w)
            if k_ % 2 == 0:
                bx("marker", (sx * 1.281, y, 1.05), (0.01, 0.12, 0.06), mat("marker_amber", (1, 0.45, 0.02), 0.2,
                                                                             emit=(1, 0.45, 0.02), estr=1.0))
            y -= 1.6
            k_ += 1
    bx("rear_plate", (0, -9.23, 0.85), (0.52, 0.02, 0.11), C["plate"], 0.004)
    if label:
        lm = mat(name + "_label", label_color, 0.4)
        for sx in (-1, 1):
            t = W.text_obj("truck_label", label, 0.85, lm, root, "CENTER", "CENTER", 0.003)
            t.rotation_euler = (math.radians(90), 0, math.radians(90 if sx > 0 else -90))
            t.location = (sx * 1.279, tc, 2.75)
            t.parent = g
    # wheels: tractor front 6.2, drive 2.5; trailer -5.1, -6.4, -7.7
    for y, dual in ((6.2, False), (2.5, True), (-5.1, False), (-6.4, False), (-7.7, False)):
        for sx in (-1, 1):
            x = sx * (1.0 if dual else 1.03)
            bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.5, depth=0.5 if dual else 0.36, location=(x, y, 0.5),
                                                rotation=(0, math.pi / 2, 0))
            ty = W.link(bpy.context.active_object, root)
            b = ty.modifiers.new("b", "BEVEL")
            b.width, b.segments = 0.07, 3
            ty.data.materials.append(C["tyre"])
            bpy.ops.object.shade_smooth()
            ty.parent = g
            bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.3, depth=0.02,
                                                location=(x + sx * (0.255 if dual else 0.185), y, 0.5),
                                                rotation=(0, math.pi / 2, 0))
            rm = W.link(bpy.context.active_object, root)
            rm.data.materials.append(C["rim"])
            rm.parent = g
    for o in root.objects:
        if o.parent is g:
            o.location.y += 0.8  # centre the 16.8 m rig on the origin
    return root


# ------------------------------------------------------------------ emergency vehicles
def flash_mats():
    """Two blue flasher materials (phase A and B) whose emission the episode script animates."""
    return (mat("blue_flash_a", (0.02, 0.08, 0.6), 0.2, emit=(0.0, 0.1, 1.0), estr=0.3),
            mat("blue_flash_b", (0.02, 0.08, 0.6), 0.2, emit=(0.0, 0.1, 1.0), estr=0.3))


def _box(root, g, name, loc, size, m, bev=0.0, seg=3):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = W.link(bpy.context.active_object, root)
    o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    if bev:
        b = o.modifiers.new("b", "BEVEL")
        b.width, b.segments = bev, seg
    o.data.materials.append(m)
    o.parent = g
    return o


def _side_text(root, g, body, x, y, z, size, m, extrude=0.003):
    for sx in (-1, 1):
        t = W.text_obj("txt", body, size, m, root, "CENTER", "CENTER", extrude)
        t.rotation_euler = (math.radians(90), 0, math.radians(90 if sx > 0 else -90))
        t.location = (sx * x, y, z)
        t.parent = g


def rtw(name="rtw", c=None):
    """German Rettungswagen: panel-van cab with a box module, white with luminous red bands, blue flashers."""
    root = car("van", (0.9, 0.9, 0.9), name, "F RK 112", metal=0.0, c=c)
    g = next(o for o in root.objects if o.type == "EMPTY")
    white = mat("rtw_white", (0.9, 0.9, 0.88), 0.35, coat=0.5)
    red = mat("rtw_red", (0.75, 0.03, 0.02), 0.35, emit=(1, 0.05, 0.02), estr=0.05)
    yel = mat("rtw_yellow", (0.95, 0.75, 0.05), 0.35)
    fa, fb = flash_mats()
    L = KINDS["van"]["L"]
    y0, y1 = -L / 2 - 0.08, 1.2
    yc, ly = (y0 + y1) / 2, y1 - y0
    _box(root, g, "module", (0, yc, 1.8), (2.24, ly, 2.4), white, 0.07)
    for z, h_, m_ in ((1.05, 0.28, red), (1.27, 0.08, yel), (2.72, 0.16, red)):
        _box(root, g, "band", (0, yc, z), (2.25, ly + 0.01, h_), m_)
    _side_text(root, g, "RETTUNGSDIENST", 1.127, yc, 1.75, 0.26, red)
    _box(root, g, "rear_door_seam", (0, y0 - 0.005, 1.8), (0.02, 0.01, 2.2), mat("rtw_seam", (0.3, 0.3, 0.3), 0.5))
    # flashers: cab roof bar (two halves on alternate phases), rear top corners, front grille
    _box(root, g, "bar_l", (-0.45, 1.75, 2.72), (0.8, 0.28, 0.16), fa, 0.04)
    _box(root, g, "bar_r", (0.45, 1.75, 2.72), (0.8, 0.28, 0.16), fb, 0.04)
    for sx, m_ in ((-1, fb), (1, fa)):
        _box(root, g, "rear_flash", (sx * 0.95, y0 - 0.02, 2.95), (0.22, 0.12, 0.16), m_, 0.03)
        _box(root, g, "front_flash", (sx * 0.55, L / 2 + 0.01, 0.62), (0.18, 0.04, 0.07), m_, 0.01)
    return root


def fire_engine(name="hlf", c=None):
    """German HLF 20: crew cab and equipment body in RAL 3000, white band, roller shutters, ladder, blue flashers."""
    C = common()
    root = bpy.data.collections.new(name)
    (c or bpy.context.scene.collection).children.link(root)
    g = bpy.data.objects.new(name, None)
    root.objects.link(g)
    red = mat("fire_red", (0.5, 0.015, 0.01), 0.3, metal=0.1, coat=1.0)
    white = mat("fire_white", (0.9, 0.9, 0.88), 0.35)
    grey = mat("fire_shutter", (0.55, 0.56, 0.57), 0.35, metal=0.7)
    dark = mat("truck_chassis", (0.035, 0.035, 0.035), 0.6)
    fa, fb = flash_mats()
    _box(root, g, "cab", (0, 3.0, 2.15), (2.5, 2.8, 2.1), red, 0.16, 4)
    _box(root, g, "windscreen", (0, 4.4, 2.6), (2.2, 0.04, 0.9), C["glass"], 0.04)
    for sx in (-1, 1):
        for yy in (3.75, 2.45):
            _box(root, g, "cab_window", (sx * 1.252, yy, 2.55), (0.03, 0.9, 0.7), C["glass"], 0.03)
        _box(root, g, "mirror", (sx * 1.45, 4.3, 2.5), (0.08, 0.16, 0.5), dark, 0.03)
        _box(root, g, "headlight", (sx * 0.9, 4.42, 1.45), (0.36, 0.04, 0.16), C["head"], 0.03)
    _box(root, g, "grille", (0, 4.42, 1.75), (1.5, 0.04, 0.4), dark, 0.02)
    _box(root, g, "bumper", (0, 4.4, 1.0), (2.45, 0.2, 0.36), dark, 0.05)
    _box(root, g, "body", (0, -1.55, 2.05), (2.5, 6.0, 2.3), red, 0.08)
    _box(root, g, "chassis", (0, 0.0, 0.85), (1.0, 8.6, 0.35), dark)
    for z, h_, m_ in ((1.12, 0.14, white),):
        _box(root, g, "band", (0, 0.4, z), (2.52, 8.0, h_), m_)
    for sx in (-1, 1):
        for k, yy in enumerate((0.55, -1.55, -3.6)):
            _box(root, g, "shutter", (sx * 1.252, yy, 2.15), (0.02, 1.85, 1.65), grey, 0.01)
            for zz in (1.5, 1.8, 2.1, 2.4, 2.7):
                _box(root, g, "slat", (sx * 1.262, yy, zz), (0.01, 1.8, 0.015), mat("slat", (0.35, 0.36, 0.37), 0.5))
    _box(root, g, "ladder_l", (-0.35, -1.0, 3.3), (0.06, 6.0, 0.08), grey)
    _box(root, g, "ladder_r", (0.35, -1.0, 3.3), (0.06, 6.0, 0.08), grey)
    for k in range(13):
        _box(root, g, "rung", (0, -3.9 + k * 0.48, 3.3), (0.7, 0.04, 0.04), grey)
    t = W.text_obj("feuerwehr", "FEUERWEHR", 0.18, white, root, "CENTER", "CENTER", 0.002)
    t.rotation_euler = (math.radians(90), 0, math.pi)
    t.location = (0, 4.43, 3.05)
    t.rotation_euler = (math.radians(90), 0, math.pi)
    t.parent = g
    _side_text(root, g, "FEUERWEHR", 1.257, 3.0, 1.55, 0.2, white)
    # chevrons at the rear
    for k in range(6):
        m_ = mat("chev_red", (0.7, 0.02, 0.01), 0.3) if k % 2 else mat("chev_yellow", (0.95, 0.8, 0.05), 0.3)
        _box(root, g, "chev", (-1.05 + k * 0.42, -4.56, 1.3), (0.4, 0.01, 0.5), m_)
    _box(root, g, "bar_l", (-0.5, 3.6, 3.28), (0.85, 0.3, 0.16), fa, 0.04)
    _box(root, g, "bar_r", (0.5, 3.6, 3.28), (0.85, 0.3, 0.16), fb, 0.04)
    for sx, m_ in ((-1, fb), (1, fa)):
        _box(root, g, "rear_flash", (sx * 1.0, -4.58, 3.1), (0.22, 0.1, 0.16), m_, 0.03)
        _box(root, g, "front_flash", (sx * 0.4, 4.44, 1.75), (0.16, 0.04, 0.08), m_, 0.01)
        _box(root, g, "taillight", (sx * 1.0, -4.57, 0.95), (0.3, 0.04, 0.12), C["tail"], 0.02)
    for y, r_ in ((3.3, 0.55), (-2.0, 0.55)):
        for sx in (-1, 1):
            bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=r_, depth=0.42, location=(sx * 1.0, y, r_),
                                                rotation=(0, math.pi / 2, 0))
            ty = W.link(bpy.context.active_object, root)
            b = ty.modifiers.new("b", "BEVEL")
            b.width, b.segments = 0.07, 3
            ty.data.materials.append(C["tyre"])
            bpy.ops.object.shade_smooth()
            ty.parent = g
            bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.32, depth=0.02,
                                                location=(sx * 1.22, y, r_), rotation=(0, math.pi / 2, 0))
            rm = W.link(bpy.context.active_object, root)
            rm.data.materials.append(C["rim"])
            rm.parent = g
    return root
