"""Generic modern low-floor tram for Drive Like a Local (no operator, no logo, no brand).

About 30 m long in 3 to 5 sections, 2.40 m wide (BOStrab section 34: at most 2.65 m up to 3.4 m above the rail),
2.65 m wide is allowed but 2.30 to 2.40 m is what most German city networks run (UNVERIFIED typical). Floor about
0.35 m above the rail (low floor, UNVERIFIED typical), roof 3.40 m, roof equipment and a single-arm pantograph that
reaches the contact wire. Bidirectional: a cab at both ends, doors on both sides.
Sections alternate between bogie sections (ends and middle) and short suspended sections, joined by dark bellows.
Each section is its own object, so drive() can articulate the train along a jx.Path (each section's ends sit on the
path). Lights: headlights and daytime LED strip, tail and brake lights, indicators, destination display (route
number and a generic destination).

    import tram as TR
    t = TR.build(c, name="tram1", sections=5)
    TR.drive(t, path, sv, frames)              # sv from jx.kinematics, s = arc length of the tram's middle
    TR.lights(t, frames)                        # head/tail by direction, brake lights from deceleration
"""
import math

import bmesh
import bpy
from mathutils import Vector

import world as W

WIDTH = 2.40
ROOF = 3.40
SKIRT = 0.30
FLOOR = 0.35
GAUGE = 1.435
LAYOUTS = {
    3: [("cab", 11.0), ("mid", 8.0), ("cab", 11.0)],
    5: [("cab", 7.6), ("float", 4.6), ("mid", 5.6), ("float", 4.6), ("cab", 7.6)],
    4: [("cab", 8.4), ("float", 6.6), ("float", 6.6), ("cab", 8.4)],
}
JOINT = 0.12            # gap between sections (filled by bellows)


def _mats(name, body, accent):
    m = {}
    m["body"] = W.principled(name + "_body", body, 0.32, coat=0.6)
    m["accent"] = W.principled(name + "_accent", accent, 0.35, coat=0.6)
    m["glass"] = W.principled(name + "_glass", (0.015, 0.02, 0.025), 0.03, spec=0.9, coat=1.0)
    m["roof"] = W.principled(name + "_roof", (0.36, 0.37, 0.38), 0.55, metal=0.3)
    m["dark"] = W.principled(name + "_dark", (0.03, 0.03, 0.032), 0.6)
    m["bellows"] = W.principled(name + "_bellows", (0.02, 0.02, 0.022), 0.85)
    m["metal"] = W.principled(name + "_metal", (0.55, 0.56, 0.57), 0.3, metal=0.9)
    m["door"] = W.principled(name + "_door", tuple(0.92 * x for x in body), 0.3, coat=0.6)
    for k, col, base in (("head", (1.0, 0.97, 0.9), (0.9, 0.9, 0.88)), ("drl", (1.0, 1.0, 1.0), (0.85, 0.85, 0.85)),
                         ("tail", (1.0, 0.03, 0.02), (0.4, 0.01, 0.01)), ("brake", (1.0, 0.02, 0.01), (0.4, 0.01, 0.01)),
                         ("ind_L", (1.0, 0.45, 0.0), (0.7, 0.3, 0.0)), ("ind_R", (1.0, 0.45, 0.0), (0.7, 0.3, 0.0)),
                         ("dest", (1.0, 0.62, 0.12), (0.2, 0.12, 0.02))):
        mm = W.principled(f"{name}_{k}", base, 0.15, emit=col, estr=0.0)
        m[k] = mm
    # each cab gets its own head / tail materials so the leading end shows white and the trailing end red
    for end in ("A", "B"):
        for k in ("head", "drl", "tail", "brake"):
            mm = m[k].copy()
            mm.name = f"{name}_{k}_{end}"
            m[f"{k}_{end}"] = mm
    return m


BANDS = (0.95, 1.05, 1.6, 2.1, 2.5, 2.62)      # side profile breaks: skirt, window bottom, window top, roof band


def _ring(w2, zb=SKIRT, zt=ROOF, rb=0.06, rt=0.42, n=6):
    """Cross-section (x, z) around the car body with a fixed point count: bottom centre, rounded lower corner, side
    breaks at the material bands, rounded roof corner, roof centre, and the mirror image."""
    pts = [(0.0, zb)]
    for k in range(n + 1):
        a = -math.pi / 2 + (math.pi / 2) * k / n
        pts.append((w2 - rb + rb * math.cos(a), zb + rb + rb * math.sin(a)))
    for z in BANDS:
        pts.append((w2, z))
    for k in range(n + 1):
        a = (math.pi / 2) * k / n
        pts.append((w2 - rt + rt * math.cos(a), zt - rt + rt * math.sin(a)))
    right = pts[1:]
    left = [(-x, z) for x, z in reversed(right)]
    return pts[:1] + right + [(0.0, zt)] + left


def _rake(z):
    """How far the nose surface leans back at height z (the windscreen rakes, the lower front is upright)."""
    return 0.0 if z < 0.9 else 0.55 * ((z - 0.9) / (ROOF - 0.9)) ** 1.3


def _section_mesh(name, L, cab_front, cab_back, m):
    """Loft of fixed-profile rings along y (front = +y). A cab end narrows in four stations to a flat, raked nose
    (the last ring is collapsed to x = 0, so the nose surface is made of horizontal bands that take the material of
    their height: lower body, windscreen, roof band)."""
    w2 = WIDTH / 2

    def cab(y_end, sgn):
        # (y, x scale, rake factor), from the inside out to the nose
        return [(y_end - sgn * 1.2, 1.0, 0.0), (y_end - sgn * 0.5, 0.99, 0.5), (y_end - sgn * 0.16, 0.95, 0.85),
                (y_end - sgn * 0.05, 0.86, 0.96), (y_end, 0.0, 1.0)]
    st = []
    if cab_back:
        st += [(y, k, r, -1) for (y, k, r) in reversed(cab(-L / 2, -1))]
    else:
        st.append((-L / 2, 1.0, 0.0, 0))
    lo = st[-1][0]
    hi = (L / 2 - 1.2) if cab_front else L / 2
    for y in (-L / 4, 0.0, L / 4):
        if lo + 0.3 < y < hi - 0.3:
            st.append((y, 1.0, 0.0, 0))
    if cab_front:
        st += [(y, k, r, 1) for (y, k, r) in cab(L / 2, 1)]
    else:
        st.append((L / 2, 1.0, 0.0, 0))
    bm = bmesh.new()
    rings = []
    prof = _ring(w2)
    for (y, k, r, sgn) in st:
        rings.append([bm.verts.new((x * k, y - sgn * _rake(z) * r, z)) for x, z in prof])
    n = len(prof)
    for i in range(len(rings) - 1):
        for j in range(n):
            j2 = (j + 1) % n
            q = (rings[i][j], rings[i][j2], rings[i + 1][j2], rings[i + 1][j])
            if len({v.co.to_tuple(5) for v in q}) >= 3:
                bm.faces.new(q)
    if not cab_back:
        bm.faces.new(rings[0])
    if not cab_front:
        bm.faces.new(list(reversed(rings[-1])))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # material per face: 0 body, 1 glass band, 2 accent skirt band, 3 roof
    for f in bm.faces:
        cz = f.calc_center_median()
        nrm = f.normal
        nose = abs(nrm.y) > 0.5
        if nrm.z > 0.6 and cz.z > ROOF - 0.3:
            f.material_index = 3
        elif cz.z < 1.0:
            f.material_index = 2
        elif nose and 1.05 <= cz.z <= 2.62:
            f.material_index = 1                      # windscreen
        elif 1.05 <= cz.z <= 2.5 and abs(nrm.z) < 0.6:
            f.material_index = 1                      # side windows
        else:
            f.material_index = 0
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for mat_ in (m["body"], m["glass"], m["accent"], m["roof"]):
        me.materials.append(mat_)
    me.shade_smooth()
    try:
        me.set_sharp_from_angle(angle=math.radians(40))
    except (AttributeError, TypeError):
        pass
    return me


def _box(name, c, parent, loc, size, mat, bevel=0.0, rot=(0, 0, 0)):
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    v = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
         (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    o = W.mesh_obj(name, v, f, mat, c)
    o.location = loc
    o.rotation_euler = rot
    if bevel:
        b = o.modifiers.new("b", "BEVEL")
        b.width, b.segments = bevel, 2
    o.parent = parent
    return o


def _cyl(name, c, parent, loc, r, h, mat, rot=(0, 0, 0), seg=16):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r, radius2=r, depth=h)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    me.materials.append(mat)
    o.location = loc
    o.rotation_euler = rot
    o.parent = parent
    return o


def _doors(name, c, g, L, m, ys):
    """Double sliding-plug doors (1.30 m) on both sides at local y positions."""
    for y in ys:
        for sx in (-1, 1):
            x = sx * (WIDTH / 2 + 0.006)
            for k in (-1, 1):
                _box(name + "_door", c, g, (x, y + k * 0.33, 1.2), (0.012, 0.64, 2.05), m["door"], bevel=0.01)
                _box(name + "_doorglass", c, g, (x + sx * 0.004, y + k * 0.33, 1.55), (0.008, 0.46, 1.1),
                     m["glass"])
            _box(name + "_doorgap", c, g, (x + sx * 0.005, y, 1.2), (0.008, 0.02, 2.05), m["dark"])
            _box(name + "_doorbtn", c, g, (x + sx * 0.007, y + 0.75, 1.15), (0.006, 0.07, 0.11), m["ind_L"])


def _pillars(name, c, g, L, m, y0, y1, avoid, step=1.25):
    """Black window pillars along the glass band, skipping door openings."""
    y = y0
    while y <= y1 + 1e-6:
        if all(abs(y - a) > 0.85 for a in avoid):
            for sx in (-1, 1):
                _box(name + "_pillar", c, g, (sx * (WIDTH / 2 + 0.004), y, 1.8), (0.01, 0.09, 1.5), m["dark"])
        y += step


def _cab_details(name, c, g, L, m, end, sgn, route, dest):
    """Lights, display and coupler cover on a cab end. sgn = +1 front end (+y), -1 back end."""
    y_tip = sgn * L / 2
    for sx in (-1, 1):
        # headlight cluster low on the nose, tail light above it, indicator outboard
        _box(f"{name}_head_{end}", c, g, (sx * 0.78, y_tip - sgn * 0.02, 0.88), (0.34, 0.06, 0.12),
             m[f"head_{end}"], bevel=0.02)
        _box(f"{name}_tail_{end}", c, g, (sx * 0.86, y_tip - sgn * 0.04, 1.06), (0.16, 0.06, 0.08),
             m[f"tail_{end}"], bevel=0.015)
        _box(f"{name}_brake_{end}", c, g, (sx * 0.62, y_tip - sgn * 0.03, 1.06), (0.12, 0.06, 0.07),
             m[f"brake_{end}"], bevel=0.012)
        side = "R" if sx * sgn > 0 else "L"
        _box(f"{name}_ind_{end}", c, g, (sx * 0.95, y_tip - sgn * 0.06, 0.88), (0.1, 0.06, 0.08), m["ind_" + side],
             bevel=0.01)
    _box(f"{name}_drl_{end}", c, g, (0, y_tip - sgn * 0.005, 0.74), (1.1, 0.05, 0.035), m[f"drl_{end}"])
    _box(f"{name}_coupler_{end}", c, g, (0, y_tip + sgn * 0.02, 0.55), (0.7, 0.12, 0.28), m["dark"], bevel=0.04)
    # destination display above the windscreen: black panel, route number and destination in LED amber
    yd = y_tip - sgn * 0.42
    zd = ROOF - 0.42
    panel = _box(f"{name}_destpanel_{end}", c, g, (0, yd, zd), (1.7, 0.03, 0.26), m["dark"])
    panel.rotation_euler.x = sgn * math.radians(-28)
    rot = (math.radians(90) - sgn * math.radians(28), 0, 0 if sgn > 0 else math.pi)
    for txt, x, size in ((route, -0.66, 0.2), (dest, 0.12, 0.13)):
        t = W.text_obj(f"{name}_dest_{end}", txt, size, m["dest"], c, "CENTER", "CENTER", 0.0)
        t.parent = g
        t.rotation_euler = (math.radians(90) + sgn * math.radians(28) * 0 - math.radians(28) * 0, 0,
                            0 if sgn < 0 else math.pi)
        # text faces outward along sgn*y; tilt back with the panel
        t.rotation_euler = (math.radians(90) - math.radians(28), 0, math.pi) if sgn > 0 else \
            (math.radians(90) - math.radians(28), 0, 0)
        if sgn > 0:
            t.location = (-x, yd + sgn * 0.02, zd)
        else:
            t.location = (x, yd + sgn * 0.02, zd)
    # wipers
    for sx in (-0.35, 0.35):
        w = _box(f"{name}_wiper_{end}", c, g, (sx, y_tip - sgn * 0.2, 1.35), (0.02, 0.02, 0.75), m["dark"])
        w.rotation_euler = (sgn * math.radians(-20), math.radians(10 if sx > 0 else -10), 0)
    # small mirror camera pods (modern trams use camera arms or mirrors)
    for sx in (-1, 1):
        _box(f"{name}_mirror_{end}", c, g, (sx * (WIDTH / 2 + 0.12), y_tip - sgn * 0.5, 2.25), (0.22, 0.1, 0.2),
             m["dark"], bevel=0.03)


def _pantograph(name, c, g, m, wire_h, y=0.0):
    """Single-arm pantograph on the roof, head at the contact wire height (relative to the rail top)."""
    base_z = ROOF + 0.18
    _box(name + "_panto_base", c, g, (0, y, ROOF + 0.09), (1.2, 1.4, 0.12), m["roof"], bevel=0.02)
    for sx in (-0.45, 0.45):
        _cyl(name + "_insul", c, g, (sx, y - 0.45, ROOF + 0.17), 0.05, 0.16, m["dark"])
        _cyl(name + "_insul", c, g, (sx, y + 0.45, ROOF + 0.17), 0.05, 0.16, m["dark"])
    head_z = wire_h - 0.02
    reach = head_z - base_z
    # lower arm from the hinge (back) up to the knee (forward), upper arm back to the head
    hinge = Vector((0, y - 0.6, base_z + 0.05))
    head = Vector((0, y - 0.15, head_z - 0.06))
    knee = Vector((0, y + 0.75, base_z + reach * 0.48))
    for (a, b, r) in ((hinge, knee, 0.035), (knee, head, 0.022)):
        for sx in ((-0.12, 0.12) if r > 0.03 else (0.0,)):
            d = b - a
            o = _cyl(name + "_arm", c, g, ((a + b) / 2) + Vector((sx, 0, 0)), r, d.length, m["metal"], seg=10)
            o.rotation_euler = d.normalized().to_track_quat("Z", "Y").to_euler()
    _box(name + "_panhead", c, g, (0, head.y, head_z - 0.03), (1.6, 0.06, 0.04), m["metal"], bevel=0.01)
    for sx in (-0.85, 0.85):
        h = _box(name + "_panhorn", c, g, (sx, head.y, head_z - 0.08), (0.2, 0.05, 0.03), m["metal"])
        h.rotation_euler.y = math.radians(-35 if sx > 0 else 35)
    _box(name + "_panstrip", c, g, (0, head.y, head_z - 0.005), (1.2, 0.04, 0.012), m["dark"])


def build(c, name="tram", sections=5, body=(0.86, 0.86, 0.84), accent=(0.55, 0.04, 0.035), route="4",
          dest="Hauptbahnhof", wire_h=5.60):
    """Build the tram. Each section is an empty (local +y = forward, z = 0 on the rail top) with its parts.
    Returns dict(name, sections=[dict(obj, L, kind)], length, mats, wire_h)."""
    layout = LAYOUTS.get(sections, LAYOUTS[5])
    m = _mats(name, body, accent)
    secs = []
    total = sum(L for _k, L in layout) + JOINT * (len(layout) - 1)
    for i, (kind, L) in enumerate(layout):
        g = bpy.data.objects.new(f"{name}_sec{i}", None)
        c.objects.link(g)
        front = (i == 0 and kind == "cab")
        back = (i == len(layout) - 1 and kind == "cab")
        me = _section_mesh(f"{name}_shell{i}", L, front, back, m)
        sh = bpy.data.objects.new(f"{name}_shell{i}", me)
        c.objects.link(sh)
        sh.parent = g
        # doors: one pair per section (two on long cab sections)
        if kind == "cab":
            ys = [-sgn * 0.0 for sgn in (1,)]
            ys = [(-L / 2 + 3.1) if front else (L / 2 - 3.1)]
        elif kind == "float":
            ys = [0.0]
        else:
            ys = []
        _doors(f"{name}_s{i}", c, sh, L, m, ys)
        y0 = -L / 2 + (1.6 if back else 0.4)
        y1 = L / 2 - (1.6 if front else 0.4)
        _pillars(f"{name}_s{i}", c, sh, L, m, y0, y1, ys)
        # bellows halves at the joints
        if i > 0:
            _box(f"{name}_bellows", c, sh, (0, -L / 2 - JOINT / 2 + 0.02, (ROOF + SKIRT) / 2 + 0.05),
                 (WIDTH - 0.16, JOINT + 0.06, ROOF - SKIRT - 0.25), m["bellows"], bevel=0.04)
        # roof equipment
        if kind in ("cab", "mid"):
            _box(f"{name}_roofbox", c, sh, (0, 0.0 if kind == "mid" else (-1 if front else 1) * L * 0.12,
                                            ROOF + 0.16), (1.7, min(3.2, L * 0.4), 0.3), m["roof"], bevel=0.06)
        if kind in ("mid", "float") and (sections == 3 or kind == "mid"):
            _pantograph(f"{name}_s{i}", c, sh, m, wire_h, y=0.0)
        # bogie and wheels under bogie sections (visible below the skirt)
        if kind in ("cab", "mid"):
            yb = 0.0 if kind == "mid" else ((-L / 2 + 2.6) if front else (L / 2 - 2.6))
            yb = -yb if front else yb
            yb = (L / 2 - 2.4) if front else ((-L / 2 + 2.4) if back else 0.0)
            _box(f"{name}_bogie", c, sh, (0, yb, 0.36), (WIDTH - 0.3, 2.4, 0.3), m["dark"], bevel=0.03)
            for dy in (-0.9, 0.9):
                for sx in (-1, 1):
                    _cyl(f"{name}_wheel", c, sh, (sx * GAUGE / 2, yb + dy, 0.31), 0.31, 0.12, m["metal"],
                         rot=(0, math.pi / 2, 0), seg=24)
        if front:
            _cab_details(f"{name}_s{i}", c, sh, L, m, "A", +1, route, dest)
        if back:
            _cab_details(f"{name}_s{i}", c, sh, L, m, "B", -1, route, dest)
        # side destination display on the first section
        if i == 0:
            for sx in (-1, 1):
                t = W.text_obj(f"{name}_sidedest", f"{route}  {dest}", 0.11, m["dest"], c, "CENTER", "CENTER", 0.0)
                t.parent = sh
                t.rotation_euler = (math.radians(90), 0, math.radians(90) * sx)
                t.location = (sx * (WIDTH / 2 + 0.008), -L / 2 + 1.5 if front else 0.0, 2.38)
                _box(f"{name}_sidedestpanel", c, sh, (sx * (WIDTH / 2 + 0.004), -L / 2 + 1.5, 2.38),
                     (0.006, 1.6, 0.2), m["dark"])
        secs.append(dict(obj=g, L=L, kind=kind))
    t = dict(name=name, sections=secs, length=total, mats=m, wire_h=wire_h, layout=layout)
    lights_static(t, forward=True)
    return t


# ------------------------------------------------------------------ motion
def offsets(t):
    """Distance from the tram's front end to the front of each section."""
    out, acc = [], 0.0
    for s in t["sections"]:
        out.append(acc)
        acc += s["L"] + JOINT
    return out


def poses(t, path, s_mid):
    """[(x, y, yaw), ...] per section for the tram's middle at arc length s_mid (sections follow the path; each
    section's two ends sit on it, the chord gives its heading)."""
    out = []
    s_front = s_mid + t["length"] / 2
    for off, sec in zip(offsets(t), t["sections"]):
        a = s_front - off
        b = a - sec["L"]
        pa, _ = path.at(a)
        pb, _ = path.at(b)
        mid = (pa + pb) / 2
        d = pa - pb
        out.append((mid.x, mid.y, math.atan2(d.y, d.x)))
    return out


def place(t, path, s_mid):
    for sec, (x, y, yaw) in zip(t["sections"], poses(t, path, s_mid)):
        sec["obj"].location = (x, y, 0.0)
        sec["obj"].rotation_euler = (0, 0, yaw - math.pi / 2)


def drive(t, path, sv, frames):
    """Bake every section along the path; sv = [(s_mid, v)] per frame (jx.kinematics)."""
    import stage
    per = [[] for _ in t["sections"]]
    for (s, v) in sv:
        for k, (x, y, yaw) in enumerate(poses(t, path, s)):
            per[k].append((x, y, yaw - math.pi / 2))
    for sec, track in zip(t["sections"], per):
        locs = [(x, y, 0.0) for x, y, _ in track]
        rots = [(0.0, 0.0, a) for _x, _y, a in track]
        for i in range(1, len(rots)):
            a = rots[i][2]
            while a - rots[i - 1][2] > math.pi:
                a -= 2 * math.pi
            while a - rots[i - 1][2] < -math.pi:
                a += 2 * math.pi
            rots[i] = (0.0, 0.0, a)
        stage.bake_motion(sec["obj"], frames, locs, rots)
    t["sv"] = sv


def _emit(mat, val, frame=None):
    inp = mat.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    inp.default_value = val
    if frame is not None:
        inp.keyframe_insert("default_value", frame=frame)


def lights_static(t, forward=True, night=False, brake=False):
    """Leading cab: headlights and LED strip; trailing cab: tail lights. forward=True: cab A leads."""
    m = t["mats"]
    lead, trail = ("A", "B") if forward else ("B", "A")
    _emit(m[f"head_{lead}"], 6.0 if night else 2.5)
    _emit(m[f"drl_{lead}"], 8.0)
    _emit(m[f"tail_{lead}"], 0.0)
    _emit(m[f"brake_{lead}"], 0.0)
    _emit(m[f"head_{trail}"], 0.0)
    _emit(m[f"drl_{trail}"], 0.0)
    _emit(m[f"tail_{trail}"], 2.0)
    _emit(m[f"brake_{trail}"], 7.0 if brake else 0.0)
    _emit(m["dest"], 3.0)
    for k in ("ind_L", "ind_R"):
        _emit(m[k], 0.0)


def lights(t, frames=None, forward=True, night=False):
    """Brake lights of the trailing cab keyed from the baked (s, v) (on while decelerating or standing)."""
    import jx
    import stage
    lights_static(t, forward, night)
    sv = t.get("sv")
    if not sv:
        return
    m = t["mats"]
    trail = "B" if forward else "A"
    mat = m[f"brake_{trail}"]
    state = None
    for i in range(len(sv)):
        v = sv[i][1]
        v_prev = sv[i - 1][1] if i else v
        on = (v_prev - v) > 0.004 or v < 0.05
        if on != state:
            _emit(mat, 7.0 if on else 0.0, i + 1)
            state = on
    for fc in stage.fcurves(mat.node_tree):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"


def blink(t, side, t0, t1, period=0.66, fps=30):
    import jx
    jx.blink(dict(ind={side: t["mats"]["ind_" + side]}), side, t0, t1, period)
