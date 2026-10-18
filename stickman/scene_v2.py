"""Stick Facts #1 v2: out of fuel on the German Autobahn. 9:16, 30 fps, 600 frames (20 s), Cycles.
Assets (CC0 Poly Haven, CC-BY Khronos CarConcept) come from the stickman-assets branch.
Run: python scene_v2.py OUTDIR --frames 1-600 --res 1080 --samples 48 --assets ASSETS [--still]
"""
import math
import os
import random
import sys

import bpy
from mathutils import Matrix, Vector

# ---------------------------------------------------------------- arguments
OUT, RES, SAMPLES, ASSETS, FR = "frames", 540, 32, "assets", (1, 600)
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
a = sys.argv
for i, x in enumerate(a):
    if i == 1 and not x.startswith("--"):
        OUT = x
    if x == "--res":
        RES = int(a[i + 1])
    if x == "--samples":
        SAMPLES = int(a[i + 1])
    if x == "--assets":
        ASSETS = a[i + 1]
    if x == "--frames":
        p, q = a[i + 1].split("-")
        FR = (int(p), int(q))
    if x == "--fonts":
        FONTS = a[i + 1]

random.seed(11)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps = 30
sc.frame_start, sc.frame_end = 1, 600
PREF = bpy.context.preferences.edit
PREF.keyframe_new_interpolation_type = "BEZIER"
FPS = 30
KMH = 1000 / 3600


def font(name):
    return bpy.data.fonts.load(os.path.join(FONTS, name), check_existing=True)


F_SIGN = font("BarlowSemiCondensed-Medium.ttf")
F_SIGNB = font("BarlowSemiCondensed-Bold.ttf")


def coll(name, hide=False):
    c = bpy.data.collections.new(name)
    sc.collection.children.link(c)
    if hide:
        c.hide_render = True
        c.hide_viewport = True
    return c


def link(o, c=None):
    for u in list(o.users_collection):
        u.objects.unlink(o)
    (c or sc.collection).objects.link(o)
    return o


# ---------------------------------------------------------------- materials
def principled(name, color=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, emit=None, estr=0.0, coat=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    p.inputs["Coat Weight"].default_value = coat
    if emit:
        p.inputs["Emission Color"].default_value = (*emit, 1)
        p.inputs["Emission Strength"].default_value = estr
    if alpha < 1:
        p.inputs["Alpha"].default_value = alpha
    return m


def pbr(name, folder, scale=1.0, tint=None, rough_mul=1.0, bump=1.0):
    """Poly Haven texture set mapped in object space, scale = metres per tile."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / scale, 1 / scale, 1 / scale)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    def tex(fname, noncolor):
        path = os.path.join(ASSETS, "textures", folder, fname)
        if not os.path.exists(path):
            return None
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(path, check_existing=True)
        if noncolor:
            t.image.colorspace_settings.name = "Non-Color"
        t.projection = "BOX"
        t.projection_blend = 0.2
        nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        return t

    d = tex("Diffuse.jpg", False)
    if d:
        if tint:
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            mix.inputs["B"].default_value = (*tint, 1)
            nt.links.new(d.outputs["Color"], mix.inputs["A"])
            nt.links.new(mix.outputs["Result"], p.inputs["Base Color"])
        else:
            nt.links.new(d.outputs["Color"], p.inputs["Base Color"])
    r = tex("Rough.jpg", True)
    if r:
        if rough_mul != 1.0:
            mm = nt.nodes.new("ShaderNodeMath")
            mm.operation = "MULTIPLY"
            mm.inputs[1].default_value = rough_mul
            nt.links.new(r.outputs["Color"], mm.inputs[0])
            nt.links.new(mm.outputs["Value"], p.inputs["Roughness"])
        else:
            nt.links.new(r.outputs["Color"], p.inputs["Roughness"])
    n = tex("nor_gl.jpg", True)
    if n:
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = bump
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], p.inputs["Normal"])
    return m


def box(name, loc, size, mat, c=None, bevel=0.0, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        b = o.modifiers.new("bev", "BEVEL")
        b.width, b.segments = bevel, 2
    o.data.materials.append(mat)
    return link(o, c)


def cyl(name, loc, r, depth, mat, c=None, rot=(0, 0, 0), verts=24, smooth=True):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    if smooth:
        try:
            bpy.ops.object.shade_auto_smooth()
        except Exception:
            bpy.ops.object.shade_smooth()
    o.data.materials.append(mat)
    return link(o, c)


def sph(name, loc, r, mat, c=None, seg=32):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=seg, ring_count=seg // 2)
    o = bpy.context.active_object
    o.name = name
    bpy.ops.object.shade_smooth()
    o.data.materials.append(mat)
    return link(o, c)


def empty(name, loc=(0, 0, 0), parent=None, c=None):
    o = bpy.data.objects.new(name, None)
    o.empty_display_size = 0.2
    (c or sc.collection).objects.link(o)
    o.location = loc
    if parent:
        o.parent = parent
    return o


def text(name, body, size, mat, fnt=F_SIGN, align="LEFT", valign="CENTER", extrude=0.0, c=None):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.font = fnt
    cu.size = size
    cu.align_x = align
    cu.align_y = valign
    cu.extrude = extrude
    o = bpy.data.objects.new(name, cu)
    (c or sc.collection).objects.link(o)
    o.data.materials.append(mat)
    return o


def key(o, f, loc=None, rot=None, scale=None, interp=None):
    if interp:
        PREF.keyframe_new_interpolation_type = interp
    if loc is not None:
        o.location = loc
        o.keyframe_insert("location", frame=f)
    if rot is not None:
        o.rotation_euler = rot
        o.keyframe_insert("rotation_euler", frame=f)
    if scale is not None:
        o.scale = scale if isinstance(scale, (tuple, list)) else (scale, scale, scale)
        o.keyframe_insert("scale", frame=f)
    if interp:
        PREF.keyframe_new_interpolation_type = "BEZIER"


def key_value(sock, f, v, interp="CONSTANT"):
    PREF.keyframe_new_interpolation_type = interp
    sock.default_value = v
    sock.keyframe_insert("default_value", frame=f)
    PREF.keyframe_new_interpolation_type = "BEZIER"


def key_hide(o, f, hidden):
    PREF.keyframe_new_interpolation_type = "CONSTANT"
    o.hide_render = hidden
    o.keyframe_insert("hide_render", frame=f)
    PREF.keyframe_new_interpolation_type = "BEZIER"


# ---------------------------------------------------------------- world and light
w = bpy.data.worlds.new("sky")
sc.world = w
w.use_nodes = True
nt = w.node_tree
env = nt.nodes.new("ShaderNodeTexEnvironment")
hdr = os.path.join(ASSETS, "hdri", "kloofendal_48d_partly_cloudy_puresky.hdr")
env.image = bpy.data.images.load(hdr)
tc = nt.nodes.new("ShaderNodeTexCoord")
mp = nt.nodes.new("ShaderNodeMapping")
mp.inputs["Rotation"].default_value = (0, 0, math.radians(110))
nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
nt.links.new(env.outputs["Color"], nt.nodes["Background"].inputs["Color"])
nt.nodes["Background"].inputs["Strength"].default_value = 1.0
bpy.ops.object.light_add(type="SUN", rotation=(math.radians(52), 0, math.radians(-145)))
sun = bpy.context.active_object
sun.data.energy = 3.2
sun.data.angle = math.radians(1.5)
sun.data.color = (1.0, 0.96, 0.9)

# ---------------------------------------------------------------- Autobahn (driving +Y, our carriageway x 0..14.5)
ENV = coll("env")
Y0, Y1 = -150.0, 900.0
LEN, YM = Y1 - Y0, (Y0 + Y1) / 2
M_ASPH = pbr("asphalt", "asphalt_01", scale=3.0, tint=(0.62, 0.62, 0.64), bump=0.6)
M_ASPH2 = pbr("asphalt_shoulder", "asphalt_track", scale=3.0, tint=(0.7, 0.7, 0.7), bump=0.5)
M_GRASS = pbr("grass", "aerial_grass_rock", scale=5.0, tint=(0.75, 0.9, 0.6), bump=0.8)
M_LINE = principled("paint", (0.92, 0.92, 0.9), 0.55)
M_STEEL = principled("galvanised", (0.72, 0.73, 0.74), 0.32, metal=1.0)
M_POST = principled("post_white", (0.9, 0.9, 0.88), 0.4)
M_BLACK = principled("matte_black", (0.02, 0.02, 0.02), 0.6)
M_REFL = principled("reflector", (1.0, 0.55, 0.05), 0.2, emit=(1.0, 0.5, 0.05), estr=0.4)
M_SIGNBLUE = principled("sign_blue", (0.0, 0.11, 0.33), 0.45)  # RAL 5017
M_SIGNWHITE = principled("sign_white", (0.95, 0.95, 0.95), 0.4, emit=(1, 1, 1), estr=0.15)
M_CONCRETE = principled("concrete", (0.55, 0.55, 0.53), 0.85)

box("road", (7.25, YM, -0.05), (14.5, LEN, 0.1), M_ASPH, ENV)
box("road_opp", (-11.0, YM, -0.05), (14.0, LEN, 0.1), M_ASPH, ENV)
box("median", (-2.0, YM, -0.06), (4.0, LEN, 0.1), M_GRASS, ENV)
box("verge", (24.0, YM, -0.07), (19.0, LEN, 0.1), M_GRASS, ENV)
# embankment rising to the right
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
emb = bpy.context.active_object
emb.name = "embankment"
me = emb.data
import bmesh  # noqa: E402

bm = bmesh.new()
bm.from_mesh(me)
bm.clear()
xs = [33.5, 40, 50, 70]
zs = [-0.07, 2.8, 5.0, 6.0]
vs = [[bm.verts.new((x, y, z)) for x, z in zip(xs, zs)] for y in (Y0, Y1)]
for i in range(len(xs) - 1):
    bm.faces.new((vs[0][i], vs[0][i + 1], vs[1][i + 1], vs[1][i]))
bm.to_mesh(me)
bm.free()
emb.data.materials.append(M_GRASS)
link(emb, ENV)
box("far_left", (-40.0, YM, -0.07), (44.0, LEN, 0.1), M_GRASS, ENV)

# markings: edge lines solid, lane lines 6 m dash 12 m gap (German Autobahn)
for x, wdt in ((0.75, 0.30), (12.0, 0.25)):
    box("edge", (x, YM, 0.003), (wdt, LEN, 0.004), M_LINE, ENV)
for x, wdt in ((-4.75, 0.30), (-17.25, 0.25)):
    box("edge_opp", (x, YM, 0.003), (wdt, LEN, 0.004), M_LINE, ENV)
dash = box("dash", (4.5, Y0, 0.003), (0.15, 6.0, 0.004), M_LINE, ENV)
for x in (4.5, 8.25, -8.5, -12.75):
    y = Y0
    while y < Y1:
        d = dash.copy()
        d.location = (x, y, 0.003)
        ENV.objects.link(d)
        y += 18.0
# median guard rails (both sides) and posts
for x in (-0.45, -3.55):
    rail = box("rail", (x, YM, 0.6), (0.06, LEN, 0.32), M_STEEL, ENV, bevel=0.01)
post = cyl("rpost", (-0.5, Y0, 0.35), 0.05, 0.7, M_STEEL, ENV, verts=8)
y = Y0
while y < Y1:
    for x in (-0.55, -3.45):
        p = post.copy()
        p.location = (x, y, 0.35)
        ENV.objects.link(p)
    y += 4.0
# delineator posts (Leitpfosten) every 50 m on the right edge
lp = box("leitpfosten", (15.0, Y0, 0.5), (0.12, 0.12, 1.0), M_POST, ENV, bevel=0.02)
band = box("lp_band", (15.0, Y0, 0.85), (0.125, 0.125, 0.2), M_BLACK, ENV)
refl = box("lp_refl", (14.93, Y0, 0.85), (0.01, 0.06, 0.13), M_REFL, ENV)
for y in range(int(Y0), int(Y1), 50):
    for o in (lp, band, refl):
        n = o.copy()
        n.location.y = y
        ENV.objects.link(n)
# emergency phone (Notrufsaeule) near the stop
M_ORANGE = principled("phone_orange", (0.95, 0.35, 0.02), 0.45)
box("notruf", (15.3, 232.0, 0.75), (0.45, 0.35, 1.5), M_ORANGE, ENV, bevel=0.06)

# overhead gantry with signs at y = 80
GY = 80.0
for x in (-0.9, 15.6):
    cyl("gantry_leg", (x, GY, 3.6), 0.22, 7.2, M_STEEL, ENV, verts=16)
box("gantry_beam", (7.35, GY, 6.9), (16.8, 0.5, 0.7), M_STEEL, ENV)


def panel(x0, x1, z0, z1, y):
    box("sign_border", ((x0 + x1) / 2, y + 0.02, (z0 + z1) / 2), (x1 - x0, 0.06, z1 - z0), M_SIGNWHITE, ENV, bevel=0.08)
    box("sign_face", ((x0 + x1) / 2, y - 0.02, (z0 + z1) / 2), (x1 - x0 - 0.24, 0.06, z1 - z0 - 0.24), M_SIGNBLUE, ENV,
        bevel=0.06)


def sign_text(body, x, z, size, y, fnt=F_SIGN, align="LEFT"):
    t = text("st", body, size, M_SIGNWHITE, fnt, align, "CENTER", extrude=0.004, c=ENV)
    t.rotation_euler = (math.radians(90), 0, 0)
    t.location = (x, y - 0.06, z)
    return t


def arrow(x, z, y, angle=0.0, s=1.0):
    a_ = empty("arrow", (x, y - 0.07, z), c=ENV)
    a_.rotation_euler = (0, math.radians(angle), 0)
    shaft = box("arrow_shaft", (0, 0, 0.35 * s), (0.22 * s, 0.03, 0.75 * s), M_SIGNWHITE, ENV)
    shaft.parent = a_
    hm = bpy.data.meshes.new("arrow_head")
    hm.from_pydata([(-0.42 * s, 0, 0), (0.42 * s, 0, 0), (0, 0, -0.5 * s)], [], [(0, 1, 2)])
    head = bpy.data.objects.new("arrow_head", hm)
    ENV.objects.link(head)
    head.data.materials.append(M_SIGNWHITE)
    head.parent = a_
    return a_


# panel 1 over lanes 1 and 2: A 4 / Dresden, Bautzen, two lane arrows (text faces -Y towards drivers)
panel(0.9, 8.1, 4.2, 6.6, GY - 0.3)
box("a4_border", (1.85, GY - 0.36, 6.05), (1.2, 0.04, 0.62), M_SIGNWHITE, ENV, bevel=0.1)
box("a4_face", (1.85, GY - 0.39, 6.05), (1.06, 0.04, 0.5), M_SIGNBLUE, ENV, bevel=0.08)
sign_text("A 4", 1.85, 6.05, 0.42, GY - 0.36, F_SIGNB, "CENTER")
sign_text("Dresden", 2.8, 6.05, 0.52, GY - 0.3)
sign_text("Bautzen", 2.8, 5.35, 0.52, GY - 0.3)
arrow(6.4, 4.75, GY - 0.3, 0, 0.75)
arrow(2.6, 4.75, GY - 0.3, 0, 0.75)
# panel 2 over lane 3: next services with fuel pump pictogram, 25 km
panel(8.5, 12.9, 4.2, 6.6, GY - 0.3)
sign_text("Rastanlage", 10.05, 5.95, 0.46, GY - 0.3)
sign_text("25 km", 10.05, 5.2, 0.62, GY - 0.3, F_SIGNB)
pump = empty("pump_icon", (9.3, GY - 0.37, 5.55), c=ENV)
box("pump_body", (0, 0, 0), (0.42, 0.03, 0.72), M_SIGNWHITE, ENV).parent = pump
box("pump_win", (0, -0.01, 0.17), (0.28, 0.03, 0.2), M_SIGNBLUE, ENV).parent = pump
box("pump_hose", (-0.3, 0, 0.05), (0.06, 0.03, 0.5), M_SIGNWHITE, ENV).parent = pump
box("pump_nozzle", (-0.24, 0, 0.3), (0.16, 0.03, 0.06), M_SIGNWHITE, ENV).parent = pump
box("pump_base", (0, 0, -0.42), (0.55, 0.03, 0.1), M_SIGNWHITE, ENV).parent = pump

# ---------------------------------------------------------------- vegetation (Poly Haven instances)
SRC = coll("src", hide=True)


def import_gltf(path, c):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        link(o, c)
    return new


def src_collection(name, path):
    c = bpy.data.collections.new(name)
    SRC.children.link(c)
    objs = import_gltf(path, c)
    for o in objs:
        if o.parent is None:
            o.location = (0, 0, 0)
    return c


def instance(c, loc, rot_z=0.0, scale=1.0, into=ENV):
    e = bpy.data.objects.new("inst", None)
    e.instance_type = "COLLECTION"
    e.instance_collection = c
    e.location = loc
    e.rotation_euler = (0, 0, rot_z)
    e.scale = (scale, scale, scale)
    into.objects.link(e)
    return e


MOD = os.path.join(ASSETS, "models")
c_tree = src_collection("tree", os.path.join(MOD, "fir_sapling_medium", "fir_sapling_medium_1k.gltf"))
c_grass1 = src_collection("grass1", os.path.join(MOD, "grass_medium_01", "grass_medium_01_1k.gltf"))
c_grass2 = src_collection("grass2", os.path.join(MOD, "grass_medium_02", "grass_medium_02_1k.gltf"))
c_flower = src_collection("flower", os.path.join(MOD, "dandelion_01", "dandelion_01_1k.gltf"))


def emb_z(x):
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return zs[i] + t * (zs[i + 1] - zs[i])
    return 0.0 if x < xs[0] else zs[-1]


VEG = coll("veg")
# trees: a forest edge on the embankment and behind the median, denser where the cameras look
for y in range(int(Y0), int(Y1), 3):
    for _ in range(2):
        x = random.uniform(36, 68)
        instance(c_tree, (x, y + random.uniform(-1.5, 1.5), emb_z(x) - 0.2), random.uniform(0, 6.28),
                 random.uniform(4.0, 7.5), VEG)
    if random.random() < 0.6:
        x = random.uniform(-60, -22)
        instance(c_tree, (x, y + random.uniform(-1.5, 1.5), -0.2), random.uniform(0, 6.28), random.uniform(4.0, 7.0), VEG)
# grass clumps on the verge near the stop and near the gantry (where the camera is close)
for y0, y1, n in ((160, 260, 2600), (40, 120, 900), (192, 236, 2600)):
    for _ in range(n):
        x = random.uniform(14.6, 34)
        y = random.uniform(y0, y1)
        cg = c_grass1 if random.random() < 0.5 else c_grass2
        instance(cg, (x, y, emb_z(x) - 0.02), random.uniform(0, 6.28), random.uniform(0.6, 1.3), VEG)
    for _ in range(n // 12):
        x = random.uniform(15.5, 30)
        instance(c_flower, (x, random.uniform(y0, y1), emb_z(x)), random.uniform(0, 6.28), random.uniform(0.8, 1.2), VEG)
for _ in range(700):
    instance(c_grass1, (random.uniform(-3.3, -0.7), random.uniform(150, 260), -0.02), random.uniform(0, 6.28),
             random.uniform(0.5, 0.9), VEG)

# ---------------------------------------------------------------- cars (Khronos CarConcept, CC-BY 4.0)
CARS = coll("cars")
CAR_GLB = os.path.join(ASSETS, "cars", "CarConcept.glb")
M_PLATE = principled("plate", (0.95, 0.95, 0.95), 0.35)
M_PLATETXT = principled("plate_txt", (0.01, 0.01, 0.01), 0.5)
M_PLATEEU = principled("plate_eu", (0.0, 0.12, 0.6), 0.4)


def make_car(name, paint1=None, paint2=None, lights=True):
    objs = import_gltf(CAR_GLB, CARS)
    root = [o for o in objs if o.parent is None][0]  # keeps the importer's Y-up to Z-up rotation
    bpy.context.view_layer.update()
    inv = root.matrix_world.inverted()
    spins = []
    for o in objs:
        if o.type == "EMPTY" and o.name.startswith("Wheel") and o.parent == root:
            mw = o.matrix_world.copy()
            s_ = empty(o.name + "_spin", (0, 0, 0), c=CARS)
            s_.parent = root
            s_.matrix_parent_inverse = Matrix.Identity(4)
            s_.location = inv @ mw.translation
            s_.rotation_mode = "XYZ"
            bpy.context.view_layer.update()
            o.parent = s_
            o.matrix_parent_inverse = Matrix.Identity(4)
            o.matrix_world = mw
            spins.append(s_)
    bpy.context.view_layer.update()
    steer = [o for o in objs if o.name.startswith("InteriorSteeringCylinder")]
    steer_pos = steer[0].matrix_world.translation.copy() if steer else Vector((0.45, -0.6, 0.75))
    rig = empty(name, (0, 0, 0), c=CARS)
    turn = empty(name + "_turn", (0, 0, 0), rig, CARS)
    turn.rotation_euler = (0, 0, math.pi)  # model front is -Y; turn it to +Y. Children of turn use model space.
    root.parent = turn
    root.matrix_parent_inverse = Matrix.Identity(4)
    mats = {}
    for o in objs:
        if o.type != "MESH":
            continue
        for i, slot in enumerate(o.material_slots):
            m = slot.material
            if m is None:
                continue
            base = m.name.split(".")[0]
            new = None
            if base.startswith("Paint 1") and paint1:
                new = paint1
            elif base.startswith("Paint 2") and paint2:
                new = paint2
            elif base == "License":
                new = M_PLATE
            elif base in ("Headlight", "Brakelight", "Signallight"):
                if base not in mats:
                    mats[base] = m.copy()
                    mats[base].name = f"{name}_{base}"
                new = mats[base]
            if new is not None:
                slot.link = "OBJECT"
                slot.material = new
    # light materials
    if "Headlight" in mats:
        p = mats["Headlight"].node_tree.nodes.get("Principled BSDF")
        if p:
            p.inputs["Emission Color"].default_value = (1, 0.98, 0.92, 1)
            p.inputs["Emission Strength"].default_value = 6.0 if lights else 0.0
    if "Brakelight" in mats:
        p = mats["Brakelight"].node_tree.nodes.get("Principled BSDF")
        if p:
            p.inputs["Emission Color"].default_value = (1, 0.02, 0.01, 1)
            p.inputs["Emission Strength"].default_value = 1.5 if lights else 0.0
    if "Signallight" in mats:
        p = mats["Signallight"].node_tree.nodes.get("Principled BSDF")
        if p:
            p.inputs["Emission Color"].default_value = (1, 0.45, 0.0, 1)
            p.inputs["Emission Strength"].default_value = 0.0
    return {"rig": rig, "root": turn, "glroot": root, "spins": spins, "mats": mats, "objs": objs, "steer": steer_pos}


def plate(car, txt):
    """German plate on the rear (model rear is +Y in model space, i.e. -Y after the turn)."""
    pl = text("plate_txt", txt, 0.075, M_PLATETXT, F_SIGNB, "CENTER", "CENTER", 0.002, CARS)
    pl.parent = car["root"]
    pl.location = (0.02, 1.925, 0.315)
    pl.rotation_euler = (math.radians(90), 0, 0)


M_RED = principled("paint_red", (0.55, 0.02, 0.02), 0.22, coat=1.0)
M_RED2 = principled("paint_red_dark", (0.1, 0.1, 0.11), 0.3, coat=1.0)
hero = make_car("hero", M_RED, M_RED2)
plate(hero, "C · SF 26")
M_POLWHITE = principled("pol_white", (0.82, 0.84, 0.86), 0.25, metal=0.6, coat=1.0)
M_POLBLUE = principled("pol_blue", (0.01, 0.07, 0.3), 0.25, coat=1.0)
police = make_car("police", M_POLWHITE, M_POLBLUE)
plate(police, "C · 3456")
traffic = []
for i, (c1, c2) in enumerate((((0.05, 0.05, 0.06), (0.05, 0.05, 0.06)), ((0.7, 0.72, 0.75), (0.1, 0.1, 0.1)),
                               ((0.02, 0.1, 0.25), (0.05, 0.05, 0.05)), ((0.9, 0.9, 0.9), (0.1, 0.1, 0.1)),
                               ((0.35, 0.36, 0.38), (0.05, 0.05, 0.05)), ((0.9, 0.9, 0.92), (0.1, 0.1, 0.1)))):
    m1 = principled(f"traffic_paint_{i}", c1, 0.25, metal=0.4, coat=1.0)
    m2 = principled(f"traffic_paint2_{i}", c2, 0.3, coat=1.0)
    traffic.append(make_car(f"traffic{i}", m1, m2))

# police livery: POLIZEI on both front doors and the bonnet, neon stripe, light bar
M_POLTXT = principled("pol_text", (0.01, 0.07, 0.3), 0.3)
M_NEON = principled("pol_neon", (0.75, 1.0, 0.0), 0.35, emit=(0.6, 0.9, 0.0), estr=0.3)
door_objs = {o.name.split(".")[0]: o for o in police["objs"] if o.type == "MESH"}


def decal_text(body, size, loc, rot, target, offset):
    t = text("POLIZEI", body, size, M_POLTXT, F_SIGNB, "CENTER", "CENTER", 0.0, CARS)
    t.parent = police["root"]
    t.location = loc
    t.rotation_euler = rot
    bpy.context.view_layer.objects.active = t
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    t.select_set(True)
    bpy.ops.object.convert(target="MESH")
    sw = t.modifiers.new("wrap", "SHRINKWRAP")
    sw.target = target
    sw.wrap_method = "NEAREST_SURFACEPOINT"
    sw.offset = offset
    return t


# model space: driver door (L) at +x, passenger (R) at -x, front -y
decal_text("POLIZEI", 0.26, (1.13, -0.25, 0.62), (math.radians(90), 0, math.radians(90)),
           door_objs.get("BodyDoorLColor1"), 0.006)
decal_text("POLIZEI", 0.26, (-1.13, -0.25, 0.62), (math.radians(90), 0, math.radians(-90)),
           door_objs.get("BodyDoorRColor1"), 0.006)
decal_text("POLIZEI", 0.24, (0.0, -1.75, 0.86), (math.radians(-12), 0, 0), door_objs.get("BodyHood"), 0.006)
# light bar on the roof
lb = empty("lightbar", (0, 0.08, 1.16), police["root"], CARS)
box("lb_base", (0, 0, 0.04), (1.1, 0.26, 0.08), M_BLACK, CARS, bevel=0.03).parent = lb
M_BLUE_L = principled("blue_l", (0.05, 0.15, 1.0), 0.2, emit=(0.1, 0.3, 1.0), estr=0.0)
M_BLUE_R = principled("blue_r", (0.05, 0.15, 1.0), 0.2, emit=(0.1, 0.3, 1.0), estr=0.0)
lensL = box("lb_lens_l", (0.33, 0, 0.12), (0.42, 0.24, 0.1), M_BLUE_L, CARS, bevel=0.03)
lensR = box("lb_lens_r", (-0.33, 0, 0.12), (0.42, 0.24, 0.1), M_BLUE_R, CARS, bevel=0.03)
lensL.parent = lb
lensR.parent = lb
M_LBTXT = principled("lb_txt", (1, 1, 1), 0.3, emit=(1, 1, 1), estr=2.0)
for side, rz in ((-0.131, 0), (0.131, math.pi)):
    t = text("lb_polizei", "POLIZEI", 0.07, M_LBTXT, F_SIGNB, "CENTER", "CENTER", 0.0, CARS)
    t.parent = lb
    t.location = (0, side, 0.12)
    t.rotation_euler = (math.radians(90), 0, rz)
bl = []
for xx in (0.5, -0.5):
    bpy.ops.object.light_add(type="POINT", location=(0, 0, 0))
    L = link(bpy.context.active_object, CARS)
    L.parent = lb
    L.location = (xx * 0.66, 0, 0.3)
    L.data.color = (0.15, 0.35, 1.0)
    L.data.energy = 0.0
    L.data.shadow_soft_size = 0.15
    bl.append(L)


def flash_police(f0, f1):
    """Double flash, alternating sides, about 2.5 Hz."""
    for f in range(f0, f1, 12):
        for k, (sock, lamp) in enumerate(((M_BLUE_L.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"], bl[0]),
                                          (M_BLUE_R.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"], bl[1]))):
            base = f + k * 6
            for j, on in ((0, 1), (2, 0), (3, 1), (5, 0)):
                key_value(sock, base + j, 60.0 if on else 0.0)
                lamp.data.energy = 900.0 if on else 0.0
                PREF.keyframe_new_interpolation_type = "CONSTANT"
                lamp.data.keyframe_insert("energy", frame=base + j)
                PREF.keyframe_new_interpolation_type = "BEZIER"


key_value(M_BLUE_L.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"], 1, 0.0)
key_value(M_BLUE_R.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"], 1, 0.0)
flash_police(300, 601)


def hazards(car, f0, f1, period=24):
    sock = car["mats"]["Signallight"].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    key_value(sock, 1, 0.0)
    for f in range(f0, f1, period):
        key_value(sock, f, 25.0)
        key_value(sock, f + period // 2, 0.0)


# front amber indicators on the hero car (model space front corners)
M_AMB = hero["mats"]["Signallight"]
for xx in (0.72, -0.72):
    ind = box("front_ind", (xx, -2.2, 0.6), (0.18, 0.04, 0.05), M_AMB, CARS, bevel=0.01)
    ind.parent = hero["root"]


def drive(car, keys, wheel_r=0.37, dist=0.0):
    """keys: [(frame, y, x)]; wheels spin from the distance travelled. Returns the distance."""
    prev = None
    for f, y, x in keys:
        key(car["rig"], f, loc=(x, y, 0.0))
        if prev:
            dist += math.hypot(y - prev[1], x - prev[2])
        for s in car["spins"]:
            key(s, f, rot=(dist / wheel_r, 0, 0))
        prev = (f, y, x)
    return dist


def speed_keys(f0, f1, y0, v_ms, x):
    return [(f0, y0, x), (f1, y0 + v_ms * (f1 - f0) / FPS, x)]


# hero: shot A cruising lane 2 (x 6.4) at 120 km/h from y=0; shots C: sputters, indicates, rolls onto the shoulder
V = 120 * KMH
hero_keys = [(1, 0.0, 6.4), (75, 0.0 + V * 74 / FPS, 6.4)]
# shot B (dashboard) is elsewhere; car keeps cruising through 150
yb = hero_keys[-1][1] + V * 75 / FPS
hero_keys.append((150, yb, 6.4))
# 151 to 235: decelerate to a stop on the hard shoulder (x 13.3) at y = 215
STOP_Y = 215.0
hero_keys += [(165, yb + 9.5, 6.6), (185, yb + 25.0, 8.6), (205, yb + 35.5, 11.6), (222, yb + 40.5, 13.0),
              (235, STOP_Y, 13.3)]
PREF.keyframe_new_interpolation_type = "LINEAR"
d_ = drive(hero, hero_keys[:3])
PREF.keyframe_new_interpolation_type = "BEZIER"
drive(hero, hero_keys[2:], dist=d_)
# keep the car still after it stops
key(hero["rig"], 600, loc=(13.3, STOP_Y, 0))
# yaw a little while changing lanes
key(hero["rig"], 160, rot=(0, 0, 0))
key(hero["rig"], 190, rot=(0, 0, math.radians(-7)))
key(hero["rig"], 225, rot=(0, 0, math.radians(-2)))
key(hero["rig"], 236, rot=(0, 0, 0))
hazards(hero, 200, 601)
# brake light on while slowing
bsock = hero["mats"]["Brakelight"].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
key_value(bsock, 1, 1.5)
key_value(bsock, 175, 9.0)
key_value(bsock, 236, 1.5)

# police: arrives on the shoulder behind (from y = 120 at 70 km/h), stops at y = 205 by frame 380
PY = STOP_Y - 11.0
PREF.keyframe_new_interpolation_type = "CONSTANT"
key(police["rig"], 1, loc=(13.3, PY - 40, -30))
key(police["rig"], 299, loc=(13.3, PY - 40, -30))
PREF.keyframe_new_interpolation_type = "BEZIER"
drive(police, [(300, PY - 40, 10.1), (330, PY - 17, 11.0), (360, PY - 4, 12.9), (380, PY, 13.3)])
key(police["rig"], 600, loc=(13.3, PY, 0))
key(police["rig"], 300, rot=(0, 0, 0))
key(police["rig"], 335, rot=(0, 0, math.radians(-6)))
key(police["rig"], 375, rot=(0, 0, 0))

# traffic: lanes 1 and 2, 130 to 160 km/h, spread so cars pass in every shot
for i, car in enumerate(traffic):
    lane_x = 2.6 if i % 2 == 0 else 6.4
    v = (150 if i % 2 == 0 else 130) * KMH
    y0 = -160 + i * 95 if i < 4 else (200 - v * (450 if i == 4 else 560) / FPS)
    PREF.keyframe_new_interpolation_type = "LINEAR"
    drive(car, [(1, y0, lane_x), (600, y0 + v * 599 / FPS, lane_x)])
    PREF.keyframe_new_interpolation_type = "BEZIER"

# ---------------------------------------------------------------- stickman v2
M_SKIN = principled("stick_black", (0.012, 0.012, 0.014), 0.28, coat=0.6)
M_HEAD = principled("stick_head", (0.95, 0.95, 0.93), 0.45)
M_EYEW = principled("eye_white", (1, 1, 1), 0.2)
M_PUPIL = principled("pupil", (0.0, 0.0, 0.0), 0.15, coat=1.0)
M_VEST = principled("vest", (0.85, 1.0, 0.0), 0.5, emit=(0.5, 0.65, 0.0), estr=0.15)
M_VESTSTRIP = principled("vest_strip", (0.8, 0.8, 0.8), 0.15, metal=1.0)
M_CAP = principled("cap_blue", (0.02, 0.04, 0.12), 0.5)
M_BADGE = principled("badge", (0.9, 0.75, 0.2), 0.2, metal=1.0)
CH = coll("characters")


def capsule(name, length, r, mat, parent):
    """Limb hanging down from its parent joint (-Z)."""
    c = cyl(name, (0, 0, -length / 2), r, length, mat, CH, verts=16)
    c.parent = parent
    e = sph(name + "_end", (0, 0, -length), r * 1.02, mat, CH, seg=16)
    e.parent = parent
    return c


def stickman(name, police_officer=False):
    root = empty(name, (0, 0, 0), c=CH)
    hips = empty(name + "_hips", (0, 0, 0.92), root, CH)
    torso = cyl(name + "_torso", (0, 0, 0.29), 0.05, 0.58, M_SKIN, CH, verts=20)
    torso.parent = hips
    sph(name + "_pelvis", (0, 0, 0), 0.052, M_SKIN, CH, 16).parent = hips
    chest = empty(name + "_chest", (0, 0, 0.58), hips, CH)
    neck = empty(name + "_neck", (0, 0, 0.04), chest, CH)
    head = sph(name + "_head", (0, 0, 0.22), 0.21, M_HEAD, CH, 48)
    head.parent = neck
    head.scale = (1, 0.95, 1.05)
    face = {}
    for side, sx in (("L", 1), ("R", -1)):
        ew = sph(f"{name}_eyew{side}", (sx * 0.075, 0.17, 0.26), 0.06, M_EYEW, CH, 24)
        ew.parent = neck
        ew.scale = (1, 0.55, 1.15)
        pu = sph(f"{name}_pupil{side}", (sx * 0.072, 0.21, 0.255), 0.032, M_PUPIL, CH, 16)
        pu.parent = neck
        brow = box(f"{name}_brow{side}", (sx * 0.077, 0.19, 0.355), (0.085, 0.02, 0.018), M_SKIN, CH, bevel=0.006)
        brow.parent = neck
        face["eye" + side], face["pupil" + side], face["brow" + side] = ew, pu, brow
    bpy.ops.mesh.primitive_torus_add(major_radius=0.05, minor_radius=0.008, location=(0, 0, 0))
    mouth = link(bpy.context.active_object, CH)
    mouth.name = name + "_mouth"
    mouth.data.materials.append(M_SKIN)
    # keep the lower half only (a smile); rotate 180 deg about Y for a frown
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for v in mouth.data.vertices:
        v.select = v.co.y > 0.004
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.delete(type="VERT")
    bpy.ops.object.mode_set(mode="OBJECT")
    mouth.parent = neck
    mouth.location = (0, 0.195, 0.15)
    mouth.rotation_euler = (math.radians(90), 0, 0)
    face["mouth"] = mouth
    limbs = {}
    for side, sx in (("L", 1), ("R", -1)):
        sh = empty(f"{name}_sh{side}", (sx * 0.08, 0, 0.53), hips, CH)
        sph(f"{name}_shj{side}", (0, 0, 0), 0.04, M_SKIN, CH, 16).parent = sh
        capsule(f"{name}_upper{side}", 0.3, 0.034, M_SKIN, sh)
        el = empty(f"{name}_el{side}", (0, 0, -0.3), sh, CH)
        capsule(f"{name}_fore{side}", 0.28, 0.032, M_SKIN, el)
        hand = sph(f"{name}_hand{side}", (0, 0, -0.31), 0.045, M_SKIN, CH, 16)
        hand.parent = el
        hp = empty(f"{name}_hip{side}", (sx * 0.06, 0, -0.02), hips, CH)
        capsule(f"{name}_thigh{side}", 0.44, 0.038, M_SKIN, hp)
        kn = empty(f"{name}_knee{side}", (0, 0, -0.44), hp, CH)
        capsule(f"{name}_shin{side}", 0.42, 0.036, M_SKIN, kn)
        foot = box(f"{name}_foot{side}", (0, 0.05, -0.445), (0.08, 0.17, 0.05), M_SKIN, CH, bevel=0.02)
        foot.parent = kn
        limbs.update({"sh" + side: sh, "el" + side: el, "hip" + side: hp, "knee" + side: kn, "hand" + side: hand})
    # high-visibility vest
    vest = cyl(name + "_vest", (0, 0, 0.36), 0.105, 0.34, M_VEST, CH, verts=32)
    vest.parent = hips
    for zz in (0.27, 0.43):
        s = cyl(name + "_vstrip", (0, 0, zz), 0.107, 0.035, M_VESTSTRIP, CH, verts=32)
        s.parent = hips
    if police_officer:
        cap = cyl(name + "_cap", (0, 0, 0.37), 0.17, 0.09, M_CAP, CH, verts=32)
        cap.parent = neck
        crown = cyl(name + "_crown", (0, 0.015, 0.43), 0.19, 0.05, M_CAP, CH, verts=32)
        crown.parent = neck
        visor = box(name + "_visor", (0, 0.15, 0.335), (0.22, 0.12, 0.012), M_BLACK, CH, bevel=0.01)
        visor.parent = neck
        visor.rotation_euler = (math.radians(-10), 0, 0)
        badge = sph(name + "_badge", (0, 0.18, 0.4), 0.022, M_BADGE, CH, 12)
        badge.parent = neck
        badge.scale = (1, 0.3, 1)
        vt = text(name + "_vesttxt", "POLIZEI", 0.05, M_POLTXT, F_SIGNB, "CENTER", "CENTER", 0.0, CH)
        vt.parent = hips
        vt.location = (0, -0.108, 0.36)
        vt.rotation_euler = (math.radians(90), 0, math.radians(180))
    return {"root": root, "hips": hips, "neck": neck, "chest": chest, "face": face, **limbs}


def pose(r, f, **kw):
    """Joint rotations in degrees: shL=(x,y,z) etc."""
    for k, v in kw.items():
        key(r[k], f, rot=tuple(math.radians(a_) for a_ in v))


def walk(r, f0, f1, p0, p1, heading, step=14):
    """Walk from p0 to p1 (x, y), heading in degrees (0 = +Y)."""
    PREF.keyframe_new_interpolation_type = "LINEAR"
    key(r["root"], f0, loc=(p0[0], p0[1], 0), rot=(0, 0, math.radians(heading)))
    key(r["root"], f1, loc=(p1[0], p1[1], 0), rot=(0, 0, math.radians(heading)))
    PREF.keyframe_new_interpolation_type = "BEZIER"
    n = 0
    for f in range(f0, f1 + 1, step // 2):
        s = 1 if n % 2 == 0 else -1
        pose(r, f, hipL=(28 * s, 0, 0), hipR=(-28 * s, 0, 0), kneeL=(-25 if s < 0 else -5, 0, 0),
             kneeR=(-25 if s > 0 else -5, 0, 0), shL=(-22 * s, 0, 4), shR=(22 * s, 0, -4), elL=(15, 0, 0), elR=(15, 0, 0))
        key(r["hips"], f, loc=(0, 0, 0.92 + (0.0 if n % 2 else 0.025)))
        n += 1


def stand(r, f):
    pose(r, f, hipL=(0, 0, 0), hipR=(0, 0, 0), kneeL=(0, 0, 0), kneeR=(0, 0, 0), shL=(0, 0, 6), shR=(0, 0, -6),
         elL=(8, 0, 0), elR=(8, 0, 0))
    key(r["hips"], f, loc=(0, 0, 0.92))


def face_mood(r, f, mood):
    fa = r["face"]
    if mood == "happy":
        key(fa["mouth"], f, rot=(math.radians(90), 0, 0))
        key(fa["browL"], f, rot=(0, math.radians(-8), 0))
        key(fa["browR"], f, rot=(0, math.radians(8), 0))
    elif mood == "worried":
        key(fa["mouth"], f, rot=(math.radians(90), math.radians(180), 0))
        key(fa["browL"], f, rot=(0, math.radians(18), 0))
        key(fa["browR"], f, rot=(0, math.radians(-18), 0))
    elif mood == "stern":
        key(fa["mouth"], f, rot=(math.radians(90), math.radians(180), 0), scale=(1.2, 1, 0.4))
        key(fa["browL"], f, rot=(0, math.radians(-20), 0))
        key(fa["browR"], f, rot=(0, math.radians(20), 0))


def blink(r, f):
    for side in "LR":
        e = r["face"]["eye" + side]
        key(e, f - 2, scale=(1, 0.55, 1.15))
        key(e, f, scale=(1, 0.55, 0.12))
        key(e, f + 2, scale=(1, 0.55, 1.15))


driver = stickman("driver")
cop = stickman("cop", police_officer=True)
# the driver seated in the hero car for shots A to C (model space: front is -Y)
seat = empty("seated", (0, 0, 0), hero["root"], CH)
sp = hero["steer"]
seat.location = (sp.x, sp.y + 0.55, sp.z - 0.42)
st = cyl("seated_torso", (0, 0, 0.25), 0.05, 0.5, M_SKIN, CH, verts=16)
st.parent = seat
sh_ = sph("seated_head", (0, 0, 0.58), 0.16, M_HEAD, CH, 32)
sh_.parent = seat
for sx in (1, -1):
    e_ = sph("seated_eye", (sx * 0.06, -0.13, 0.62), 0.045, M_EYEW, CH, 16)
    e_.parent = seat
    e_.scale = (1, 0.55, 1.15)
    p_ = sph("seated_pupil", (sx * 0.058, -0.158, 0.615), 0.024, M_PUPIL, CH, 12)
    p_.parent = seat
    arm = cyl("seated_arm", (sx * 0.12, -0.25, 0.42), 0.03, 0.5, M_SKIN, CH, rot=(math.radians(-70), 0, 0), verts=12)
    arm.parent = seat
for o in [seat] + list(seat.children_recursive):
    key_hide(o, 1, False)
    key_hide(o, 241, True)
# the driver is in the car until shot D (hidden), then by the rear of the car
key_hide(driver["root"], 1, True)
for o in driver["root"].children_recursive:
    key_hide(o, 1, True)
    key_hide(o, 241, False)
key_hide(driver["root"], 241, False)
# shot D (241-315): walks back from the rear of the car carrying the warning triangle, puts it down
REAR = STOP_Y - 2.6
stand(driver, 241)
face_mood(driver, 241, "worried")
walk(driver, 243, 290, (14.0, REAR), (13.6, REAR - 9.0), 180)
stand(driver, 296)
pose(driver, 296, shR=(70, 0, -10), elR=(20, 0, 0))
pose(driver, 306, shR=(40, 0, -10), elR=(10, 0, 0))
key(driver["hips"], 300, loc=(0, 0, 0.92))
key(driver["hips"], 304, loc=(0, 0, 0.8))
key(driver["hips"], 310, loc=(0, 0, 0.92))
blink(driver, 270)
# warning triangle: carried in the right hand, then stands on the road
M_TRI = principled("triangle", (0.9, 0.02, 0.02), 0.25, emit=(1, 0.0, 0.0), estr=0.6)
tri = empty("triangle", (0, 0, 0), c=ENV)
for k in range(3):
    ang = math.radians(90 + 120 * k)
    bar = box("tri_bar", (0, 0, 0), (0.44, 0.02, 0.05), M_TRI, ENV, bevel=0.005)
    bar.parent = tri
    mid = math.radians(90 + 120 * k + 60)
    bar.location = (0.127 * math.cos(mid), 0, 0.127 * math.sin(mid) + 0.25)
    bar.rotation_euler = (0, -(mid + math.pi / 2), 0)
box("tri_foot", (0, 0, 0.01), (0.3, 0.12, 0.02), M_BLACK, ENV).parent = tri
PREF.keyframe_new_interpolation_type = "CONSTANT"
tri.parent = None
key(tri, 1, loc=(0, 0, -50))
PREF.keyframe_new_interpolation_type = "BEZIER"
# carried: follow the driver's path roughly at hand height, then placed
PREF.keyframe_new_interpolation_type = "LINEAR"
key(tri, 241, loc=(14.25, REAR + 0.1, 0.55), rot=(0, 0, math.radians(180)))
key(tri, 290, loc=(13.85, REAR - 8.9, 0.55), rot=(0, 0, math.radians(180)))
PREF.keyframe_new_interpolation_type = "BEZIER"
key(tri, 304, loc=(13.4, REAR - 9.6, 0.0), rot=(0, 0, math.radians(180)))
key(tri, 600, loc=(13.4, REAR - 9.6, 0.0), rot=(0, 0, math.radians(180)))
# after the triangle, back to the car side (shots E to H)
walk(driver, 312, 355, (13.6, REAR - 9.0), (16.0, STOP_Y - 0.5), 0)
stand(driver, 360)
key(driver["root"], 380, rot=(0, 0, math.radians(200)))
face_mood(driver, 380, "worried")
blink(driver, 420)
# cop: gets out of the police car (passenger side, +x) at 395, walks to the driver
key_hide(cop["root"], 1, True)
for o in cop["root"].children_recursive:
    key_hide(o, 1, True)
    key_hide(o, 392, False)
key_hide(cop["root"], 392, False)
walk(cop, 392, 440, (15.0, PY + 1.0), (16.3, STOP_Y - 1.6), 0)
stand(cop, 446)
face_mood(cop, 446, "stern")
key(cop["root"], 452, rot=(0, 0, math.radians(-100)))
# cop explains: points at the car (fuel), then writes
pose(cop, 456, shR=(80, 0, -35), elR=(5, 0, 0))
pose(cop, 470, shR=(80, 0, -50), elR=(5, 0, 0))
pose(cop, 482, shR=(0, 0, -6), elR=(8, 0, 0))
pose(cop, 486, shL=(55, 0, 20), elL=(60, 0, 0), shR=(50, 0, -20), elR=(70, 0, 0))
blink(cop, 500)
# driver reacts: hand to head
pose(driver, 452, shR=(0, 0, -6), elR=(8, 0, 0))
pose(driver, 462, shR=(150, 0, -30), elR=(80, 0, 0))
pose(driver, 476, shR=(150, 0, -25), elR=(85, 0, 0))
pose(driver, 488, shR=(0, 0, -6), elR=(8, 0, 0))
# end (541-600): driver holds the ticket, head down; cop walks back
pose(driver, 541, shR=(60, 0, -10), elR=(40, 0, 0))
key(driver["neck"], 545, rot=(0, 0, 0))
key(driver["neck"], 560, rot=(math.radians(25), 0, 0))
face_mood(driver, 545, "worried")
M_PAPER = principled("paper", (0.96, 0.96, 0.94), 0.6)
held = box("ticket_held", (0, 0.06, -0.33), (0.11, 0.003, 0.15), M_PAPER, CH)
held.parent = driver["elR"]
key_hide(held, 1, True)
key_hide(held, 541, False)
walk(cop, 550, 600, (16.3, STOP_Y - 1.6), (15.0, PY + 3.0), 180)
# place both characters for shots before they appear
key(driver["root"], 1, loc=(14.0, REAR, 0))
key(cop["root"], 1, loc=(15.0, PY + 1.0, 0))

# ---------------------------------------------------------------- dashboard close-up set (shot B), far away
DASH = coll("dash")
DX, DY = 2000.0, 0.0
M_DASHPANEL = principled("dash_panel", (0.015, 0.015, 0.017), 0.35, coat=0.4)
M_CHROME = principled("chrome", (0.9, 0.9, 0.9), 0.08, metal=1.0)
M_TICK = principled("tick", (1, 1, 1), 0.3, emit=(1, 1, 1), estr=2.5)
M_RED_N = principled("needle", (1, 0.05, 0.0), 0.3, emit=(1, 0.08, 0.0), estr=6.0)
M_FUEL = principled("fuel_icon", (1, 0.55, 0.0), 0.3, emit=(1, 0.5, 0.0), estr=0.0)
M_LCD = principled("lcd", (1, 0.6, 0.1), 0.3, emit=(1, 0.55, 0.1), estr=3.0)
box("dash_back", (DX, DY + 0.02, 0), (1.2, 0.02, 1.6), M_DASHPANEL, DASH, bevel=0.01)
g = empty("gauge", (DX, DY, 0), c=DASH)
bpy.ops.mesh.primitive_torus_add(major_radius=0.085, minor_radius=0.006, location=(DX, DY - 0.004, 0),
                                 rotation=(math.radians(90), 0, 0))
ring = link(bpy.context.active_object, DASH)
ring.data.materials.append(M_CHROME)
bpy.ops.object.shade_smooth()
cyl("dial", (DX, DY + 0.002, 0), 0.084, 0.004, M_DASHPANEL, DASH, rot=(math.radians(90), 0, 0), verts=64)
# ticks from E (-120 deg) to F (-60 deg) across the top arc: angle measured from +Z, clockwise positive towards F
for k in range(9):
    ang = math.radians(-60 + 120 * k / 8)
    big = k % 4 == 0
    tk = box("tick", (DX + 0.064 * math.sin(ang), DY - 0.002, 0.064 * math.cos(ang)),
             (0.004, 0.003, 0.018 if big else 0.01), M_TICK, DASH)
    tk.rotation_euler = (0, ang, 0)
for lbl, ang in (("E", -60), ("F", 60)):
    t = text("lbl", lbl, 0.022, M_TICK, F_SIGNB, "CENTER", "CENTER", 0.0, DASH)
    t.location = (DX + 0.042 * math.sin(math.radians(ang)), DY - 0.003, 0.042 * math.cos(math.radians(ang)))
    t.rotation_euler = (math.radians(90), 0, 0)
# fuel pump icon (amber), blinking
fi = empty("fuel_icon", (DX, DY - 0.003, -0.03), c=DASH)
box("fi_body", (0, 0, 0), (0.014, 0.002, 0.024), M_FUEL, DASH).parent = fi
box("fi_win", (0, -0.0012, 0.006), (0.009, 0.001, 0.006), M_DASHPANEL, DASH).parent = fi
box("fi_base", (0, 0, -0.013), (0.019, 0.002, 0.003), M_FUEL, DASH).parent = fi
box("fi_arm", (0.0095, 0, 0.007), (0.005, 0.002, 0.0022), M_FUEL, DASH).parent = fi
box("fi_hose", (0.0122, 0, 0.0), (0.0022, 0.002, 0.016), M_FUEL, DASH).parent = fi
nz = box("fi_nozzle", (0.0105, 0, 0.0095), (0.0022, 0.002, 0.007), M_FUEL, DASH)
nz.parent = fi
nz.rotation_euler = (0, math.radians(35), 0)
lcd_on = text("lcd", "Reichweite   0 km", 0.011, M_LCD, F_SIGNB, "CENTER", "CENTER", 0.0, DASH)
lcd_on.location = (DX, DY - 0.003, -0.058)
lcd_on.rotation_euler = (math.radians(90), 0, 0)
nd = empty("needle_pivot", (DX, DY - 0.006, 0), c=DASH)
needle = box("needle", (0, 0, 0.03), (0.003, 0.002, 0.06), M_RED_N, DASH)
needle.parent = nd
cyl("needle_cap", (DX, DY - 0.007, 0), 0.007, 0.004, M_DASHPANEL, DASH, rot=(math.radians(90), 0, 0))
key(nd, 76, rot=(0, math.radians(-50), 0))
key(nd, 120, rot=(0, math.radians(-60), 0))
key(nd, 128, rot=(0, math.radians(-63), 0))
key(nd, 150, rot=(0, math.radians(-62), 0))
fsock = M_FUEL.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
key_value(fsock, 1, 0.0)
for f in range(76, 152, 16):
    key_value(fsock, f, 12.0)
    key_value(fsock, f + 8, 0.6)
bpy.ops.object.light_add(type="AREA", location=(DX + 0.15, DY - 0.25, 0.2))
dl = link(bpy.context.active_object, DASH)
dl.data.energy = 3.0
dl.data.size = 0.3
dl.rotation_euler = (math.radians(70), 0, math.radians(30))

# ---------------------------------------------------------------- ticket close-up (shot G), in the scene near the cars
TK = coll("ticket")
tick = empty("ticket_set", (0, 0, 0), c=TK)
paper = box("ticket_paper", (0, 0, 0), (0.15, 0.002, 0.21), M_PAPER, TK, bevel=0.002)
paper.parent = tick
M_INK = principled("ink", (0.02, 0.02, 0.05), 0.5)
M_INKBLUE = principled("ink_blue", (0.0, 0.08, 0.35), 0.5)
lines = [("POLIZEI", 0.016, 0.085, F_SIGNB, M_INKBLUE), ("Bußgeld", 0.012, 0.062, F_SIGNB, M_INK),
         ("Parken auf der Autobahn", 0.0085, 0.040, F_SIGN, M_INK), ("§ 18 Abs. 8 StVO", 0.0085, 0.026, F_SIGN, M_INK),
         ("Grund: Kraftstoffmangel", 0.0085, 0.006, F_SIGN, M_INK), ("Betrag", 0.0085, -0.030, F_SIGN, M_INK),
         ("70,00 €", 0.03, -0.058, F_SIGNB, M_INK)]
for body, size, z, fnt, mt in lines:
    t = text("tk_line", body, size, mt, fnt, "LEFT", "CENTER", 0.0, TK)
    t.parent = tick
    t.location = (-0.062, -0.0015, z)
    t.rotation_euler = (math.radians(90), 0, 0)
box("tk_rule", (0, -0.0013, 0.074), (0.124, 0.0005, 0.0012), M_INKBLUE, TK).parent = tick
box("tk_rule2", (0, -0.0013, -0.04), (0.124, 0.0005, 0.0008), M_INK, TK).parent = tick
# a stick hand holding it
TKPOS = Vector((15.4, STOP_Y - 3.2, 1.3))
key_hide(tick, 1, True)
for o in tick.children:
    key_hide(o, 1, True)
    key_hide(o, 466, False)
    key_hide(o, 541, True)
key_hide(tick, 466, False)
key_hide(tick, 541, True)
key(tick, 466, loc=tuple(TKPOS), rot=(math.radians(-8), 0, math.radians(200)))
key(tick, 540, loc=tuple(TKPOS + Vector((0, 0, 0.02))), rot=(math.radians(-4), 0, math.radians(205)))

# ---------------------------------------------------------------- cameras per shot (bound with markers)
CAMS = coll("cams")


def camera(name, lens=35, dof_target=None, fstop=4.0):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_width = 36
    c = bpy.data.objects.new(name, cd)
    CAMS.objects.link(c)
    if dof_target is not None:
        cd.dof.use_dof = True
        cd.dof.focus_object = dof_target
        cd.dof.aperture_fstop = fstop
    return c


def look(cam, f, pos, target, interp=None):
    d = Vector(target) - Vector(pos)
    rot = d.to_track_quat("-Z", "Y").to_euler()
    key(cam, f, loc=pos, rot=rot, interp=interp)


def hero_pos(f):
    sc.frame_set(f)
    return hero["rig"].matrix_world.translation.copy()


# A: drone chase, high behind-left, gantry ahead
camA = camera("camA", 24)
for f in list(range(1, 76, 5)) + [75]:
    p = hero_pos(f)
    look(camA, f, (p.x - 3.0, p.y - 9.0 + f * 0.012, 3.2 - f * 0.01), (p.x + 0.3, p.y + 9.0, 1.1), "LINEAR")
# B: dashboard
camB = camera("camB", 50, dof_target=nd, fstop=2.0)
look(camB, 76, (DX - 0.05, DY - 0.32, 0.04), (DX, DY, -0.005))
look(camB, 150, (DX - 0.02, DY - 0.22, 0.02), (DX, DY, -0.01))
# C: on the shoulder ahead, low, car approaches and rolls to a stop
camC = camera("camC", 32, dof_target=hero["rig"], fstop=5.6)
look(camC, 151, (15.2, STOP_Y + 13.0, 0.9), (8.0, STOP_Y - 30.0, 1.0))
look(camC, 200, (15.4, STOP_Y + 11.0, 0.95), (11.5, STOP_Y - 6.0, 0.9))
look(camC, 240, (15.6, STOP_Y + 9.5, 1.0), (13.3, STOP_Y, 0.9))
# D: behind the car on the verge, driver walks back with the triangle
camD = camera("camD", 28)
look(camD, 241, (17.5, REAR - 14.0, 1.5), (13.8, REAR - 2.0, 0.9))
look(camD, 315, (17.8, REAR - 15.0, 1.4), (13.6, REAR - 6.5, 0.7))
# E: in front of the hero car looking back, police arrives with blue lights
camE = camera("camE", 45, dof_target=police["rig"], fstop=4.0)
look(camE, 316, (10.4, STOP_Y + 9.5, 1.5), (11.0, PY - 30.0, 1.0))
look(camE, 390, (10.5, STOP_Y + 8.5, 1.45), (13.3, PY, 0.9))
# F: two-shot of driver and cop from the verge
camF = camera("camF", 35, dof_target=cop["root"], fstop=3.2)
look(camF, 391, (20.0, STOP_Y - 4.8, 1.5), (16.0, STOP_Y - 1.0, 1.1))
look(camF, 465, (19.4, STOP_Y - 4.0, 1.45), (16.1, STOP_Y - 1.1, 1.15))
# G: ticket close-up with the blue lights behind
camG = camera("camG", 50, dof_target=paper, fstop=1.8)
look(camG, 466, tuple(TKPOS + Vector((0.06, 0.62, 0.03))), tuple(TKPOS))
look(camG, 540, tuple(TKPOS + Vector((0.04, 0.48, 0.02))), tuple(TKPOS))
# H: wide closing shot from the verge, traffic passing
camH = camera("camH", 24)
look(camH, 541, (22.0, STOP_Y - 14.0, 2.6), (13.5, STOP_Y - 3.0, 1.0))
look(camH, 600, (22.5, STOP_Y - 16.0, 3.0), (13.5, STOP_Y - 4.0, 1.0))
for f, c in ((1, camA), (76, camB), (151, camC), (241, camD), (316, camE), (391, camF), (466, camG), (541, camH)):
    m = sc.timeline_markers.new(c.name, frame=f)
    m.camera = c
sc.camera = camA

# ---------------------------------------------------------------- render settings
r = sc.render
r.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = SAMPLES
sc.cycles.use_adaptive_sampling = True
sc.cycles.adaptive_threshold = 0.03
sc.cycles.use_denoising = True
sc.cycles.denoiser = "OPENIMAGEDENOISE"
sc.cycles.max_bounces = 6
sc.cycles.diffuse_bounces = 2
sc.cycles.glossy_bounces = 3
sc.cycles.transmission_bounces = 4
sc.cycles.caustics_reflective = False
sc.cycles.caustics_refractive = False
sc.cycles.blur_glossy = 1.0
r.use_motion_blur = True
r.use_persistent_data = True
r.motion_blur_shutter = 0.4
r.resolution_x, r.resolution_y = RES, int(round(RES * 16 / 9))
r.resolution_percentage = 100
r.film_transparent = False
sc.view_settings.view_transform = "AgX"
try:
    sc.view_settings.look = "AgX - Medium High Contrast"
except TypeError:
    pass
r.image_settings.file_format = "PNG"
r.image_settings.color_depth = "8"
os.makedirs(OUT, exist_ok=True)
r.filepath = os.path.join(OUT, "f_")
sc.frame_start, sc.frame_end = FR
def cam_for(f):
    ms = sorted((m for m in sc.timeline_markers if m.camera), key=lambda m: m.frame)
    cam = ms[0].camera
    for m in ms:
        if m.frame <= f:
            cam = m.camera
    return cam


if "--still" in a:
    for f in [int(x) for x in a[a.index("--still") + 1].split(",")]:
        sc.frame_set(f)
        sc.camera = cam_for(f)
        r.filepath = os.path.join(OUT, f"f_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("Saved", r.filepath)
else:
    bpy.ops.render.render(animation=True)
print("RENDER_DONE", FR)
