"""Stylised vegetation: soft blob deciduous trees, layered conifers, bushes; scattered with geometry nodes."""
import math
import random

import bpy
from mathutils import Vector, noise

import world as W


def leaf_mat(name, c1, c2, scale=0.6):
    m = W.noisy(name, c1, c2, scale, rough=0.85, detail=4, coord="Object")
    return m


def _join(objs, name):
    ctx = bpy.context
    for o in ctx.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    ctx.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    o = ctx.active_object
    o.name = name
    return o


def deciduous(c, seed, mats):
    rnd = random.Random(seed)
    sub = bpy.data.collections.new(f"tree_d{seed}")
    c.children.link(sub)
    h = rnd.uniform(3.2, 4.5)
    bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=0.24, radius2=0.12, depth=h + 1.0, location=(0, 0, (h + 1) / 2))
    trunk = W.link(bpy.context.active_object, sub)
    trunk.data.materials.append(mats["bark"])
    blobs = []
    cr = rnd.uniform(2.3, 3.2)
    for k in range(rnd.randint(5, 8)):
        a = rnd.uniform(0, 2 * math.pi)
        rr = rnd.uniform(0.3, 1.0) * cr * 0.7
        z = h + cr * rnd.uniform(0.5, 1.4)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=cr * rnd.uniform(0.55, 0.85),
                                              location=(math.cos(a) * rr, math.sin(a) * rr, z))
        blobs.append(bpy.context.active_object)
    crown = _join(blobs, f"crown{seed}")
    W.link(crown, sub)
    crown.data.materials.append(mats["leaf"][seed % len(mats["leaf"])])
    tex = bpy.data.textures.new(f"crown_noise{seed}", "CLOUDS")
    tex.noise_scale = 0.9
    d = crown.modifiers.new("disp", "DISPLACE")
    d.texture = tex
    d.strength = 0.7
    d.texture_coords = "OBJECT"
    sm = crown.modifiers.new("smooth", "SMOOTH")
    sm.iterations = 4
    sm.factor = 0.6
    for p in crown.data.polygons:
        p.use_smooth = True
    return sub


def conifer(c, seed, mats):
    rnd = random.Random(seed)
    sub = bpy.data.collections.new(f"tree_c{seed}")
    c.children.link(sub)
    H = rnd.uniform(11, 17)
    bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.25, radius2=0.08, depth=H * 0.5, location=(0, 0, H * 0.25))
    trunk = W.link(bpy.context.active_object, sub)
    trunk.data.materials.append(mats["bark"])
    tiers = []
    n = rnd.randint(5, 7)
    for k in range(n):
        t = k / (n - 1)
        r = (1 - t) * rnd.uniform(2.0, 2.6) + 0.5
        z = H * (0.22 + 0.68 * t)
        bpy.ops.mesh.primitive_cone_add(vertices=14, radius1=r, radius2=r * 0.15, depth=H * 0.28,
                                        location=(rnd.uniform(-0.1, 0.1), rnd.uniform(-0.1, 0.1), z))
        tiers.append(bpy.context.active_object)
    crown = _join(tiers, f"needles{seed}")
    W.link(crown, sub)
    crown.data.materials.append(mats["needle"])
    bev = crown.modifiers.new("b", "BEVEL")
    bev.width, bev.segments = 0.15, 2
    for p in crown.data.polygons:
        p.use_smooth = True
    return sub


def bush(c, seed, mats):
    rnd = random.Random(seed)
    sub = bpy.data.collections.new(f"bush{seed}")
    c.children.link(sub)
    blobs = []
    for k in range(rnd.randint(3, 5)):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=rnd.uniform(0.8, 1.4),
                                              location=(rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(0.4, 0.9)))
        o = bpy.context.active_object
        o.scale.z = 0.75
        blobs.append(o)
    b = _join(blobs, f"bushmesh{seed}")
    W.link(b, sub)
    b.data.materials.append(mats["leaf"][(seed + 1) % len(mats["leaf"])])
    tex = bpy.data.textures.get("bush_noise") or bpy.data.textures.new("bush_noise", "CLOUDS")
    d = b.modifiers.new("disp", "DISPLACE")
    d.texture = tex
    d.strength = 0.35
    for p in b.data.polygons:
        p.use_smooth = True
    return sub


def library(lib):
    mats = {
        "bark": W.principled("bark", (0.09, 0.06, 0.04), 0.85),
        "leaf": [leaf_mat("leaf_a", (0.07, 0.2, 0.03), (0.16, 0.36, 0.06)),
                 leaf_mat("leaf_b", (0.1, 0.24, 0.04), (0.22, 0.42, 0.08)),
                 leaf_mat("leaf_c", (0.06, 0.17, 0.035), (0.13, 0.3, 0.05))],
        "needle": leaf_mat("needle", (0.025, 0.08, 0.03), (0.06, 0.16, 0.05), 0.4),
    }
    groups = {}
    for name, fn, seeds in (("decid", deciduous, range(1, 7)), ("conif", conifer, range(11, 15)),
                            ("bush", bush, range(21, 25))):
        g = bpy.data.collections.new("lib_" + name)
        lib.children.link(g)
        for s in seeds:
            fn(g, s, mats)
        groups[name] = g
    return groups


def sock(sockets, name):
    """The enabled socket called `name` (nodes like Random Value keep one hidden socket per data type)."""
    for x in sockets:
        if x.name == name and x.enabled:
            return x
    return sockets[name]


def scatter(name, points, group, c, smin=0.8, smax=1.25, seed=0):
    """Instance the child collections of `group` on points [(x, y, z)] with random pick, yaw and scale."""
    me = bpy.data.meshes.new(name + "_pts")
    me.from_pydata(points, [], [])
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    ng = bpy.data.node_groups.new(name + "_gn", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N = ng.nodes
    gi = N.new("NodeGroupInput")
    go = N.new("NodeGroupOutput")
    ci = N.new("GeometryNodeCollectionInfo")
    ci.inputs["Collection"].default_value = group
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True
    ip = N.new("GeometryNodeInstanceOnPoints")
    ip.inputs["Pick Instance"].default_value = True
    ri = N.new("FunctionNodeRandomValue")
    ri.data_type = "INT"
    sock(ri.inputs, "Min").default_value = 0
    sock(ri.inputs, "Max").default_value = len(group.children) - 1
    ri.inputs["Seed"].default_value = seed
    rr = N.new("FunctionNodeRandomValue")
    rr.data_type = "FLOAT_VECTOR"
    sock(rr.inputs, "Min").default_value = (0, 0, 0)
    sock(rr.inputs, "Max").default_value = (0, 0, 2 * math.pi)
    rr.inputs["Seed"].default_value = seed + 1
    rs = N.new("FunctionNodeRandomValue")
    rs.data_type = "FLOAT"
    sock(rs.inputs, "Min").default_value = smin
    sock(rs.inputs, "Max").default_value = smax
    rs.inputs["Seed"].default_value = seed + 2
    L = ng.links
    L.new(gi.outputs[0], ip.inputs["Points"])
    L.new(ci.outputs[0], ip.inputs["Instance"])
    L.new(sock(ri.outputs, "Value"), ip.inputs["Instance Index"])
    L.new(sock(rr.outputs, "Value"), ip.inputs["Rotation"])
    L.new(sock(rs.outputs, "Value"), ip.inputs["Scale"])
    L.new(ip.outputs[0], go.inputs[0])
    mod = o.modifiers.new("scatter", "NODES")
    mod.node_group = ng
    return o


def vegetation(road, groups, c, s_lo, s_hi, half=1900.0, center=(0, 0), spacing=7.0, seed=5, exclude=()):
    rnd = random.Random(seed)
    forest, conif, bushes, roadside = [], [], [], []
    cx, cy = center
    nx = int(2 * half / spacing)
    for j in range(nx):
        for i in range(nx):
            x = cx - half + (i + rnd.random()) * spacing
            y = cy - half + (j + rnd.random()) * spacing
            s, d, rz = road.nearest(x, y)
            if s < s_lo or s > s_hi or d < 24:
                continue
            if any((x - ex) ** 2 + (y - ey) ** 2 < er * er for ex, ey, er in exclude):
                continue
            n1 = noise.noise(Vector((x / 380, y / 380, 4.2)))
            n2 = noise.noise(Vector((x / 90, y / 90, 7.1)))
            z = W.ground_z(road, x, y) - 0.3
            if d < 60:  # planted groups along the motorway, with open grass between them
                if n2 > 0.22 and rnd.random() < 0.8:
                    (bushes if (rnd.random() < 0.55 or d < 34) else roadside).append((x, y, z))
                continue
            if n1 > 0.18:
                (conif if n1 > 0.32 else forest).append((x, y, z))
            elif n1 > 0.1 and rnd.random() < 0.25:
                forest.append((x, y, z))
            elif rnd.random() < 0.004:
                forest.append((x, y, z))
    out = [scatter("forest", forest, groups["decid"], c, 0.9, 1.5, seed=1),
           scatter("conifers", conif, groups["conif"], c, 0.8, 1.2, seed=4),
           scatter("roadside", roadside, groups["decid"], c, 0.7, 1.1, seed=7),
           scatter("bushes", bushes, groups["bush"], c, 0.7, 1.3, seed=9)]
    print("vegetation", len(forest), len(conif), len(roadside), len(bushes))
    return out
