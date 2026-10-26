"""Traffic signs for every new module: the Wikimedia Commons file, unaltered, on an aluminium plate.

Owner rule (26 Oct 2026): signs come from Wikimedia Commons SVGs, unaltered (section 5(2) UrhG), with the source
named in the description; never copy the Verkehrsblatt catalogue; never redraw a sign by hand. The fetch workflow
(lagerfunk/clips signs.yml, list files drivelocal/signs/<set>.json) puts each sign on the branch drivelocal-signs as
<set>/<id>.svg plus Commons' own PNG rendering <set>/<id>.png and <set>/sources.json. The render workflow checks that
branch out as ASSETS/signs. This module only maps that picture onto a plate: no recolouring, cropping or editing.

    import signs as SG
    SG.setup(ASSETS)                                   # once, after the scene is created
    o = SG.face("205", c, width=0.9)                   # plate in the XZ plane facing -Y, bottom edge at z = 0
    a = SG.assembly([("205", 0.9), ("1040-32", 0.6)], c, loc=(x, y, 0), rz=0.0, bottom=2.0)   # post + stack
    SG.sources_used()                                  # {(set, id): sources.json entry} for the description

Sizes (VwV-StVO, road_spec.md): round 420 / 600 / 750 mm, triangles 630 / 900 / 1,260 mm (size 1, 2, 3). Town:
size 2. Autobahn first announcement: size 3. Lower sign edge 2.0 to 2.2 m in town, 1.5 m or more outside town."""
import json
import os

import bpy

SIGN_DIR = None
DEFAULT_SET = "de-core"
_used = {}
_mats = {}
SIZE = {"round": (0.42, 0.60, 0.75), "triangle": (0.63, 0.90, 1.26), "square": (0.42, 0.60, 0.84)}


def setup(assets):
    global SIGN_DIR
    SIGN_DIR = os.path.join(assets, "signs")
    if not os.path.isdir(SIGN_DIR):
        raise FileNotFoundError(f"{SIGN_DIR} is missing: check out the branch drivelocal-signs as ASSETS/signs")


def _png(set_, id_):
    if SIGN_DIR is None:
        raise RuntimeError("signs.setup(assets) first")
    p = os.path.join(SIGN_DIR, set_, f"{id_}.png")
    if not os.path.exists(p):
        raise FileNotFoundError(f"sign {set_}/{id_} not in the library: add it to drivelocal/signs/{set_}.json")
    src = os.path.join(SIGN_DIR, set_, "sources.json")
    if os.path.exists(src):
        _used[(set_, id_)] = json.load(open(src, encoding="utf-8")).get(id_, {})
    return p


def sources_used():
    """Every sign placed in this scene with its Commons file page, author and licence (for the description)."""
    return dict(_used)


def _material(set_, id_, emit):
    key = (set_, id_, round(emit, 3))
    if key in _mats:
        return _mats[key]
    img = bpy.data.images.load(_png(set_, id_), check_existing=True)
    img.alpha_mode = "STRAIGHT"
    m = bpy.data.materials.new(f"sign_{set_}_{id_}")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img
    t.interpolation = "Cubic"
    t.extension = "CLIP"
    nt.links.new(t.outputs["Color"], p.inputs["Base Color"])
    nt.links.new(t.outputs["Alpha"], p.inputs["Alpha"])
    p.inputs["Roughness"].default_value = 0.42
    if emit > 0:
        # retroreflective sheeting: a faint glow of the sign's own colours (night and headlight scenes)
        nt.links.new(t.outputs["Color"], p.inputs["Emission Color"])
        p.inputs["Emission Strength"].default_value = emit
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "DITHERED"
    _mats[key] = (m, img)
    return m, img


def _back_material(img):
    key = ("back", img.name)
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new("sign_back_" + img.name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img
    t.extension = "CLIP"
    nt.links.new(t.outputs["Alpha"], p.inputs["Alpha"])
    p.inputs["Base Color"].default_value = (0.52, 0.54, 0.56, 1)
    p.inputs["Metallic"].default_value = 0.7
    p.inputs["Roughness"].default_value = 0.45
    _mats[key] = m
    return m


def _quad(name, w, h, y, mat, c, flip=False, uv_rect=(0.0, 0.0, 1.0, 1.0)):
    """Rectangle in the XZ plane at depth y; UV (0,0) bottom left to (1,1) top right in world space, so the back
    plate's alpha mask lines up with the front picture. flip reverses the winding (normal +Y for the back)."""
    me = bpy.data.meshes.new(name)
    vs = [(-w / 2, y, 0.0), (w / 2, y, 0.0), (w / 2, y, h), (-w / 2, y, h)]
    face_ = (3, 2, 1, 0) if flip else (0, 1, 2, 3)
    me.from_pydata(vs, [], [face_])
    uv = me.uv_layers.new(name="UVMap")
    u0, v0, u1, v1 = uv_rect
    per_vertex = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    for li, vi in enumerate(face_):
        uv.data[li].uv = per_vertex[vi]
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    return o


def plate_rect(set_, id_):
    """Some Commons files are construction drawings: the sign itself is clean, but dimension lines and labels sit on
    the transparent margin around it. The list entry may give "plate": [u0, v0, u1, v1] (fractions of the picture,
    origin bottom left) and only that rectangle is shown: the sign is untouched, the drawer's annotations stay off
    screen. Never use it to cut into a sign."""
    return tuple(_used.get((set_, id_), {}).get("plate") or (0.0, 0.0, 1.0, 1.0))


def face(id_, c, width=0.6, set_=DEFAULT_SET, name=None, emit=0.0, back=True):
    """One sign plate, width in metres, in the XZ plane facing -Y, bottom edge at z = 0, centred on x = 0.
    Returns the front object (the back plate is parented to it). Height follows the picture's aspect ratio (of the
    plate rectangle when the file is a construction drawing, see plate_rect)."""
    m, img = _material(set_, id_, emit)
    rect = plate_rect(set_, id_)
    w_px, h_px = img.size
    h = width * (h_px * (rect[3] - rect[1])) / max(1, w_px * (rect[2] - rect[0]))
    nm = name or f"sign_{id_}"
    fr = _quad(nm, width, h, -0.003, m, c, uv_rect=rect)
    if back:
        bk = _quad(nm + "_back", width, h, 0.003, _back_material(img), c, flip=True, uv_rect=rect)
        bk.parent = fr
    fr["sign"] = f"{set_}/{id_}"
    fr["height"] = h
    return fr


def post(c, height, r=0.03, name="sign_post"):
    """Galvanised round post from the ground to `height`, with a cap."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=r, depth=height, location=(0, 0.03 + r, height / 2))
    o = bpy.context.active_object
    o.name = name
    for col in o.users_collection:
        col.objects.unlink(o)
    c.objects.link(o)
    key = "sign_post_mat"
    if key not in _mats:
        mm = bpy.data.materials.new(key)
        mm.use_nodes = True
        pb = mm.node_tree.nodes["Principled BSDF"]
        pb.inputs["Base Color"].default_value = (0.6, 0.62, 0.64, 1)
        pb.inputs["Metallic"].default_value = 0.85
        pb.inputs["Roughness"].default_value = 0.4
        _mats[key] = mm
    o.data.materials.append(_mats[key])
    return o


def assembly(stack, c, loc, rz=0.0, bottom=2.0, gap=0.06, set_=DEFAULT_SET, emit=0.0, name="signs"):
    """A post with signs stacked top to bottom: stack = [(id, width), ...] (main sign first, then Zusatzzeichen).
    `bottom` is the lower edge of the lowest plate. loc is the foot of the post; the faces look along -Y rotated by rz
    (rz = 0: readable by traffic driving towards +Y). Returns the root empty."""
    root = bpy.data.objects.new(name, None)
    c.objects.link(root)
    root.location = loc
    root.rotation_euler = (0, 0, rz)
    heights = []
    for sid, w in stack:
        s = set_ if isinstance(sid, str) else sid[0]
        i = sid if isinstance(sid, str) else sid[1]
        m, img = _material(s, i, emit)
        r = plate_rect(s, i)
        heights.append(w * (img.size[1] * (r[3] - r[1])) / max(1, img.size[0] * (r[2] - r[0])))
    z = bottom + sum(heights) + gap * (len(stack) - 1)
    for (sid, w), h in zip(stack, heights):
        s = set_ if isinstance(sid, str) else sid[0]
        i = sid if isinstance(sid, str) else sid[1]
        z -= h
        f = face(i, c, w, s, name=f"{name}_{i}", emit=emit)
        f.location = (0, 0, z)
        f.parent = root
        z -= gap
    p = post(c, bottom + sum(heights) + gap * (len(stack) - 1) + 0.05, name=name + "_post")
    p.parent = root
    return root
