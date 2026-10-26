"""Town-plus kit (Drive Like a Local, batch 2): zebra crossing, bike lanes, tram street, pedestrians.

Built on the approved town kit (town.py, townstage.py, frozen) and placed with straight street frames, so every piece
works on an arm of the X junction or on any straight street. Signs only through kit/signs.py (Commons files,
unaltered). Numbers and their sources: reports/townplus.md.

- Zebra, Zeichen 293: white strips 0.50 m with 0.50 m gaps, 4.00 m long (never under 3.00 m) in the direction of
  travel, across the carriageway; Zeichen 350 on both sides for each direction (350-10 on the right, 350-20 on the
  left when the library has it, else 350-10); a lighting mast for each direction standing BEFORE the crossing in
  that direction, with the sign repeated on the arm (Saxony FGUe guidance 2021); no parking within 5 m before it.
- Radfahrstreifen: 1.85 m from the kerb including the 0.25 m solid line (Zeichen 295, Breitstrich), Zeichen 237 at
  the start; at junctions the line becomes a broken wide line (Radwegfurt).
- Schutzstreifen: 1.50 m from the kerb including the broken narrow line (0.12 m, 1 m dash, 1 m gap).
- Bike pictogram every 50 m: the Commons file (set de-townplus, id rad-marking) laid on the road unaltered when the
  library has it, else a modelled marking (MODELLED_PICTO = True in the scene's sign sources).
- Tram street: grooved rails (60R1 / Ri 60 profile: head 55 mm, groove 36 mm) at 1,435 mm gauge between the running
  edges, embedded flush in the road, two tracks 3.20 m apart; overhead line on poles with cross-span wires, contact
  wire 5.60 m above the road (BOStrab section 25: at least 4.70 m), zig-zag stagger.

Frames: a Street is a straight carriageway with centre line from origin o along unit u. x is lateral, positive to
the RIGHT of travel along u, so right-hand traffic along +u drives at x > 0 and its kerb is x = +hw.
"""
import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

import town as TN
import world as W

PAINT_Z = 0.008          # paint sits 8 mm above the asphalt, like town.py
NARROW = 0.12            # Schmalstrich outside the Autobahn
WIDE = 0.25              # Breitstrich outside the Autobahn
ZEBRA_STRIP, ZEBRA_GAP, ZEBRA_LEN = 0.50, 0.50, 4.00
RAD_W, RAD_LINE = 1.85, 0.25
SCHUTZ_W, SCHUTZ_DASH, SCHUTZ_GAP = 1.50, 1.00, 1.00
FURT_DASH, FURT_GAP = 0.50, 0.20         # Radwegfurt broken wide line: UNVERIFIED (RMS not opened)
PICTO_SPACING = 50.0
GAUGE = 1.435
RAIL_HEAD, RAIL_GROOVE, RAIL_GUARD = 0.055, 0.036, 0.022
TRACK_SPACING = 3.20     # UNVERIFIED typical, leaves 0.55 m between two 2.65 m trams
WIRE_H = 5.60            # contact wire above the road
SPAN_H = 7.10            # cross-span wire at the poles
POLE_H = 8.20
SIGN_OFF = 0.60          # sign post from the kerb face (townstage uses the same)
SIGN_BOTTOM = 2.00       # lower plate edge above the footway (2.15 m above the road)
OVERHEAD_BOTTOM = 4.50   # lower edge of a sign over the carriageway

PICTO_SET = "de-townplus"
PICTO_ID = "rad-marking"
SIGN_SET = "de-core"


# ------------------------------------------------------------------ street frames
class Street:
    def __init__(self, o, u, hw, s0, s1, name="street"):
        self.o = Vector((o[0], o[1]))
        self.u = Vector((u[0], u[1])).normalized()
        self.r = Vector((self.u.y, -self.u.x))
        self.hw, self.s0, self.s1, self.name = hw, s0, s1, name

    def p(self, s, x):
        return self.o + self.u * s + self.r * x

    def p3(self, s, x, z=0.0):
        q = self.p(s, x)
        return (q.x, q.y, z)

    def heading(self, sign=1):
        """Yaw (0 = +x) of travel along sign * u."""
        d = self.u * sign
        return math.atan2(d.y, d.x)

    def facing(self, sign=1):
        """rz for a sign (face along -Y) readable by traffic travelling along sign * u (town.facing convention)."""
        d = self.u * sign
        return TN.facing((d.x, d.y))

    def local(self, xy):
        """(s, x) of a world point."""
        v = Vector((xy[0], xy[1])) - self.o
        return v.dot(self.u), v.dot(self.r)


def arm(J, name, hw=None, s1=None):
    """Street frame of one arm of a town.Junction, s measured from the junction centre outwards. Travel along +u
    leaves the junction. s0 is where the kerb curve ends."""
    if name in ("N", "S"):
        hw_, cross = J.hw_ns, J.hw_ew
    else:
        hw_, cross = J.hw_ew, J.hw_ns
    u = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}[name]
    return Street((0, 0), u, hw if hw is not None else hw_, cross + J.R, s1 if s1 is not None else J.L, name)


def through(J, axis="NS", hw=None):
    """Street frame straight through the junction (s from -L to L), +u = north (NS) or east (EW)."""
    if axis == "NS":
        return Street((0, 0), (0, 1), hw or J.hw_ns, -J.L, J.L, "NS")
    return Street((0, 0), (1, 0), hw or J.hw_ew, -J.L, J.L, "EW")


# ------------------------------------------------------------------ flat geometry
def rects(name, st, items, z, mat, c, kind=None):
    """One mesh of flat rectangles in a street frame: items = [(s0, s1, x0, x1), ...]. Faces point up. UV in metres.
    The object keeps its rectangles (street-frame numbers) as custom properties for tests and episode code."""
    verts, faces, uvs = [], [], []
    for (s0, s1, x0, x1) in items:
        b = len(verts)
        for (s, x) in ((s0, x0), (s1, x0), (s1, x1), (s0, x1)):
            q = st.p(s, x)
            verts.append((q.x, q.y, z))
            uvs.append((s, x))
        faces.append((b, b + 1, b + 2, b + 3))
    o = W.mesh_obj(name, verts, faces, mat, c, uvs=uvs)
    up(o)
    o["rects"] = [v for it in items for v in it]
    o["street"] = [st.o.x, st.o.y, st.u.x, st.u.y]
    if kind:
        o["kind"] = kind
    o.visible_shadow = False
    return o


def up(o):
    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    for f in bm.faces:
        f.normal_update()
        if f.normal.z < 0:
            f.normal_flip()
    bm.to_mesh(me)
    bm.free()


def poly(name, pts, z, mat, c):
    """Flat polygon (world xy points), face up."""
    o = W.mesh_obj(name, [(p[0], p[1], z) for p in pts], [tuple(range(len(pts)))], mat, c,
                   uvs=[(p[0], p[1]) for p in pts])
    up(o)
    return o


def dashes(s0, s1, dash, gap, x0, x1, phase=0.0):
    out = []
    s = s0 + phase
    while s < s1 - 1e-6:
        out.append((s, min(s1, s + dash), x0, x1))
        s += dash + gap
    return out


def tubes(name, segs, r, mat, c, sides=6):
    """Many thin round tubes (wires, rods) in one mesh: segs = [(p0, p1), ...] in world coordinates."""
    bm = bmesh.new()
    for p0, p1 in segs:
        a, b = Vector(p0), Vector(p1)
        d = b - a
        if d.length < 1e-6:
            continue
        q = d.normalized().to_track_quat("Z", "Y")
        ring_a, ring_b = [], []
        for k in range(sides):
            ang = 2 * math.pi * k / sides
            off = q @ Vector((r * math.cos(ang), r * math.sin(ang), 0))
            ring_a.append(bm.verts.new(a + off))
            ring_b.append(bm.verts.new(b + off))
        for k in range(sides):
            k2 = (k + 1) % sides
            bm.faces.new((ring_a[k], ring_a[k2], ring_b[k2], ring_b[k]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p_ in me.polygons:
        p_.use_smooth = True
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    me.materials.append(mat)
    return o


def mats(T):
    """Extra materials of this kit (made once per scene)."""
    if "tp_steel_rail" in bpy.data.materials:
        g = bpy.data.materials
        return dict(rail=g["tp_steel_rail"], groove=g["tp_groove"], seal=g["tp_seal"], wire=g["tp_wire"],
                    mast=g["tp_mast"], insul=g["tp_insulator"], lamp_house=g["tp_lamp_house"])
    rail = W.principled("tp_steel_rail", (0.62, 0.6, 0.58), 0.22, metal=1.0)
    groove = W.principled("tp_groove", (0.02, 0.018, 0.016), 0.7)
    seal = W.principled("tp_seal", (0.012, 0.012, 0.013), 0.45)
    wire = W.principled("tp_wire", (0.28, 0.2, 0.14), 0.35, metal=0.9)        # bronze/copper contact wire
    mast = W.principled("tp_mast", (0.33, 0.36, 0.35), 0.45, metal=0.5)
    insul = W.principled("tp_insulator", (0.08, 0.06, 0.05), 0.3)
    lamp_house = W.principled("tp_lamp_house", (0.22, 0.23, 0.24), 0.4, metal=0.6)
    return dict(rail=rail, groove=groove, seal=seal, wire=wire, mast=mast, insul=insul, lamp_house=lamp_house)


# ------------------------------------------------------------------ signs (kit/signs.py only)
def has_sign(id_, set_=SIGN_SET):
    import signs as SG
    return SG.SIGN_DIR is not None and os.path.exists(os.path.join(SG.SIGN_DIR, set_, f"{id_}.png"))


def sign_post(c, st, s, side, stack, sign=1, bottom=SIGN_BOTTOM, off=SIGN_OFF, name="tp_sign", z=TN.KERB_H):
    """A post on the footway at street position s, on the kerb side `side` (+1 right of u, -1 left), with the faces
    readable by traffic travelling along sign * u. stack = [(id or (set, id), width), ...]."""
    import signs as SG
    q = st.p(s, side * (st.hw + off))
    a = SG.assembly(stack, c, (q.x, q.y, z), rz=st.facing(sign), bottom=bottom, name=name)
    a["tp_sign"] = ",".join(sid if isinstance(sid, str) else sid[1] for sid, _w in stack)
    a["tp_s"], a["tp_side"], a["tp_dir"] = s, side, sign
    return a


# ------------------------------------------------------------------ zebra crossing (Zeichen 293)
def zebra(T, c, st, s, length=ZEBRA_LEN, strip=ZEBRA_STRIP, gap=ZEBRA_GAP, margin=0.30, signs=True, lights=True,
          overhead=True, centre=0.0, name="zebra"):
    """Zebra across street `st` centred at street position s. The strips run in the direction of travel
    (`length` long), 0.50 m wide with 0.50 m gaps across the road, the pattern centred between the gutters.
    centre > 0: a solid centre line (Zeichen 295, 0.12 m) over that distance on both sides of the crossing (the
    Saxony guidance turns a centre line into a lane boundary 30 to 50 m before a zebra); remove any broken centre
    line there first (clear_marks).
    Returns dict(strips, signs, masts, spots, s, length, no_parking=(s_a, s_b) per direction)."""
    assert length >= 3.0, "Zeichen 293: at least 3.00 m"
    avail = 2 * (st.hw - margin)
    n = int((avail + gap) // (strip + gap))
    tot = n * strip + (n - 1) * gap
    x = -tot / 2
    items = []
    for k in range(n):
        items.append((s - length / 2, s + length / 2, x, x + strip))
        x += strip + gap
    o = rects(name + "_strips", st, items, PAINT_Z, T.paint, c, kind="zebra")
    o["strip"], o["gap"], o["length"] = strip, gap, length
    out = dict(strips=o, signs=[], masts=[], spots=[], s=s, length=length,
               no_parking={+1: (s - length / 2 - 5.0, s - length / 2), -1: (s + length / 2, s + length / 2 + 5.0)})
    if centre > 0:
        e = length / 2 + 1.0
        out["centre"] = rects(name + "_centre", st, [(s - e - centre, s - e, -NARROW / 2, NARROW / 2),
                                                     (s + e, s + e + centre, -NARROW / 2, NARROW / 2)],
                              PAINT_Z, T.paint, c, kind="sperrlinie")
    left_id = "350-20" if has_sign("350-20") else "350-10"
    left = (SIGN_SET, left_id)
    for d in (+1, -1):
        # the mast for traffic along d*u stands on that traffic's right kerb, just BEFORE the crossing
        s_m = s - d * (length / 2 + 0.6)
        side = d
        if signs:
            # one post, two faces: 350-10 for this direction (on their right), 350-20 (or 350-10) behind the post
            # for the other direction (on their left)
            import signs as SG
            a = sign_post(c, st, s_m, side, [((SIGN_SET, "350-10"), 0.6)], sign=d,
                          name=f"{name}_350_{'a' if d > 0 else 'b'}")
            f = SG.face(left_id, c, 0.6, SIGN_SET, name=f"{name}_350l_{'a' if d > 0 else 'b'}")
            f.parent = a
            f.location = (0, 0.10, SIGN_BOTTOM)
            f.rotation_euler = (0, 0, math.pi)
            f["tp_sign"], f["tp_dir"] = left_id, -d
            a["tp_sign_back"] = left_id
            out["signs"].append(a)
        if lights:
            m, spot = zebra_mast(T, c, st, s_m, side, d, s, overhead=overhead and signs, name=f"{name}_mast")
            out["masts"].append(m)
            out["spots"].append(spot)
    return out


def zebra_mast(T, c, st, s_m, side, d, s_cross, h=6.2, reach=None, overhead=True, name="zebra_mast"):
    """Lighting mast for a zebra: pole on the footway behind the sign post, an arm over the near half of the road,
    a flat luminaire at its tip and a spot light aimed at the crossing (energy 0 by day; lights(on) switches it).
    With overhead=True the 350-10 sign hangs under the arm, lower edge 4.50 m above the road."""
    X = mats(T)
    reach = reach if reach is not None else st.hw * 0.9
    base = st.p(s_m - d * 0.35, side * (st.hw + SIGN_OFF + 0.15))
    tip = st.p(s_m - d * 0.35, side * (st.hw + SIGN_OFF + 0.15 - reach - 0.3))
    parts = []
    parts.append(TN.cyl(name + "_pole", c, (base.x, base.y, TN.KERB_H + h / 2), 0.085, h, X["mast"], 16))
    mid = (base + tip) / 2
    ang = math.atan2(tip.y - base.y, tip.x - base.x)
    L = (tip - base).length
    parts.append(TN.box(name + "_arm", c, (mid.x, mid.y, TN.KERB_H + h - 0.12), (L, 0.09, 0.09), X["mast"],
                        rot_z=ang, bevel=0.02))
    hd = st.p(s_m - d * 0.35, side * (st.hw + SIGN_OFF + 0.15 - reach))
    parts.append(TN.box(name + "_head", c, (hd.x, hd.y, TN.KERB_H + h - 0.25), (0.75, 0.42, 0.16), X["lamp_house"],
                        rot_z=ang, bevel=0.04))
    lens = TN.box(name + "_lens", c, (hd.x, hd.y, TN.KERB_H + h - 0.335), (0.62, 0.32, 0.02), T.lamp_glass,
                  rot_z=ang)
    parts.append(lens)
    # spot light at the head, aimed at the middle of this direction's half of the crossing
    li = bpy.data.lights.new(name + "_spot", "SPOT")
    li.energy = 0.0
    li.spot_size = math.radians(75)
    li.spot_blend = 0.6
    li.shadow_soft_size = 0.2
    li.color = (1.0, 0.95, 0.88)
    so = bpy.data.objects.new(name + "_spot", li)
    c.objects.link(so)
    so.location = (hd.x, hd.y, TN.KERB_H + h - 0.36)
    tgt = st.p(s_cross, side * st.hw * 0.5)
    dirv = Vector((tgt.x, tgt.y, 0.9)) - Vector(so.location)
    so.rotation_euler = dirv.to_track_quat("-Z", "Y").to_euler()
    if overhead:
        import signs as SG
        q = st.p(s_m - d * 0.35 + d * 0.06, side * (st.hw * 0.5))
        f = SG.face("350-10", c, 0.6, SIGN_SET, name=name + "_over350")
        f.location = (q.x, q.y, OVERHEAD_BOTTOM)
        f.rotation_euler = (0, 0, st.facing(d))
        f["tp_overhead"] = True
        hang_z = TN.KERB_H + h - 0.12
        top = OVERHEAD_BOTTOM + f["height"]
        for dx in (-0.22, 0.22):
            e = st.p(s_m - d * 0.35 + d * 0.06, side * (st.hw * 0.5) + dx)
            parts.append(tubes(name + "_hanger", [((e.x, e.y, top), (e.x, e.y, hang_z))], 0.012, X["mast"], c))
        parts.append(f)
    return parts, so


def clear_marks(st, s0, s1, prefixes=("centre",), xmax=0.5):
    """Delete markings (objects whose name starts with one of `prefixes`, e.g. townstage's broken centre line)
    whose centre lies on street st between s0 and s1 and within xmax of the centre line."""
    gone = 0
    for o in list(bpy.data.objects):
        if o.type != "MESH" or not o.name.startswith(prefixes):
            continue
        vs = [o.matrix_world @ v.co for v in o.data.vertices]
        cx = sum(v.x for v in vs) / len(vs)
        cy = sum(v.y for v in vs) / len(vs)
        s, x = st.local((cx, cy))
        if s0 <= s <= s1 and abs(x) <= xmax:
            bpy.data.objects.remove(o)
            gone += 1
    return gone


def lights(spots, on=True, energy=450.0):
    for so in spots:
        so.data.energy = energy if on else 0.0


# ------------------------------------------------------------------ bike lanes
def picto_material():
    """Material for the Commons file 'Markierung Radfahrer.svg' (white bicycle on a dark grey field). The file's
    pixels are used as they are: the white marking shows in the file's own white, and the dark grey field, which
    stands for the road surface, is left transparent so the real asphalt shows through (luminance mask)."""
    import signs as SG
    key = "tp_picto_" + PICTO_ID
    if key in bpy.data.materials:
        m = bpy.data.materials[key]
        return m, m["img_w"], m["img_h"]
    _m, img = SG._material(PICTO_SET, PICTO_ID, 0.0)      # registers the source for the description
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img
    t.interpolation = "Cubic"
    t.extension = "CLIP"
    nt.links.new(t.outputs["Color"], p.inputs["Base Color"])
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(t.outputs["Color"], bw.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[1].position = 0.55
    nt.links.new(bw.outputs[0], ramp.inputs["Fac"])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    nt.links.new(ramp.outputs["Color"], mul.inputs[0])
    nt.links.new(t.outputs["Alpha"], mul.inputs[1])
    nt.links.new(mul.outputs[0], p.inputs["Alpha"])
    p.inputs["Roughness"].default_value = 0.45
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "DITHERED"
    m["img_w"], m["img_h"] = img.size[0], img.size[1]
    return m, img.size[0], img.size[1]


def picto(T, c, st, s, x, sign=1, name="bike_picto", length=1.6, width=1.3):
    """Bike pictogram on the road at (s, x), reading upright for traffic along sign * u (picture top = direction of
    travel). Uses the Commons file de-townplus/rad-marking (uniform scale, never stretched) when the library has
    it; else a modelled marking (flagged in o['picto'])."""
    if has_sign(PICTO_ID, PICTO_SET):
        m, iw, ih = picto_material()
        aspect = ih / max(1, iw)
        w = width
        h = w * aspect
        q = st.p(s, x)
        ang = st.heading(sign)
        # picture up = travel direction, picture right = traffic's right
        fwd = Vector((math.cos(ang), math.sin(ang)))
        rgt = Vector((fwd.y, -fwd.x))
        verts = [q - rgt * w / 2 - fwd * h / 2, q + rgt * w / 2 - fwd * h / 2, q + rgt * w / 2 + fwd * h / 2,
                 q - rgt * w / 2 + fwd * h / 2]
        o = W.mesh_obj(name, [(v.x, v.y, PAINT_Z + 0.001) for v in verts], [(0, 1, 2, 3)], m, c,
                       uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
        up(o)
        o["picto"] = "commons"
        o.visible_shadow = False
        return o
    return picto_model(T, c, st, s, x, sign, name, length, width)


def picto_model(T, c, st, s, x, sign=1, name="bike_picto", length=1.6, width=0.9):
    """Modelled bicycle marking (two wheels, diamond frame, saddle, bars), stretched along the lane like painted
    road symbols. Used only until the Commons file is in the library."""
    ang = st.heading(sign)
    fwd = Vector((math.cos(ang), math.sin(ang)))
    rgt = Vector((fwd.y, -fwd.x))
    q0 = st.p(s, x)
    k = length / 1.6           # design units: 1.6 m long along travel, 0.9 m across

    def P(a, b):               # a across (right +), b along travel (forward +)
        v = q0 + rgt * a * (width / 0.9) + fwd * b * k
        return (v.x, v.y, PAINT_Z + 0.001)

    bm = bmesh.new()

    def ring(cb, r0, r1, n=28):
        vs0 = [bm.verts.new(P(r0 * math.cos(2 * math.pi * i / n) * 0.62, cb + r0 * math.sin(2 * math.pi * i / n)))
               for i in range(n)]
        vs1 = [bm.verts.new(P(r1 * math.cos(2 * math.pi * i / n) * 0.62, cb + r1 * math.sin(2 * math.pi * i / n)))
               for i in range(n)]
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((vs0[i], vs0[j], vs1[j], vs1[i]))

    def bar(a0, b0, a1, b1, w=0.06):
        d = Vector((a1 - a0, (b1 - b0)))
        nrm = Vector((-d.y, d.x)).normalized() * (w / 2)
        vs = [bm.verts.new(P(a0 + nrm.x, b0 + nrm.y)), bm.verts.new(P(a1 + nrm.x, b1 + nrm.y)),
              bm.verts.new(P(a1 - nrm.x, b1 - nrm.y)), bm.verts.new(P(a0 - nrm.x, b0 - nrm.y))]
        bm.faces.new(vs)

    # the bicycle lies along the lane: rear wheel behind, front wheel ahead; the frame is drawn in the a-b plane
    # as seen from the side and "laid down" (a = height of the side view, scaled)
    ring(-0.5, 0.24, 0.3)
    ring(0.5, 0.24, 0.3)
    hgt = 0.62
    bb = (0.0, -0.08)          # bottom bracket (a, b)
    seat = (0.34 * hgt / 0.62 * 0.0 + 0.36, -0.2)
    head = (0.33, 0.33)
    bar(0.0, -0.5, bb[0], bb[1])                  # chain stay
    bar(0.0, -0.5, seat[0] * 0.92, seat[1])       # seat stay
    bar(bb[0], bb[1], seat[0], seat[1])           # seat tube
    bar(seat[0] * 0.92, seat[1] + 0.02, head[0] * 0.95, head[1])   # top tube
    bar(bb[0], bb[1], head[0] * 0.8, head[1] - 0.04)                # down tube
    bar(head[0] * 1.1, head[1] + 0.02, 0.0, 0.5)                    # fork
    bar(seat[0] + 0.06, seat[1] - 0.12, seat[0] + 0.06, seat[1] + 0.1, w=0.07)   # saddle
    bar(head[0] * 1.15, head[1] - 0.04, head[0] * 1.15 + 0.1, head[1] - 0.16, w=0.06)  # handlebar
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    me.materials.append(T.paint)
    up(o)
    o["picto"] = "modelled"
    o.visible_shadow = False
    return o


def radfahrstreifen(T, c, st, side=+1, s0=None, s1=None, width=RAD_W, line=RAD_LINE, sign=True, pictos=True,
                    furt=None, name="radfahrstreifen", sign_s=None, picto_from=None):
    """Radfahrstreifen along street st on kerb side `side` (+1: right of u, used by traffic along +u; -1: the other
    direction). Solid 0.25 m line at the lane's inner edge, the lane 1.85 m from the kerb including the line.
    furt: list of (s_a, s_b) stretches (junction mouths) where the line becomes a broken wide line.
    Returns dict(line, pictos, sign, x_in, x_out)."""
    s0 = st.s0 if s0 is None else s0
    s1 = st.s1 if s1 is None else s1
    d = side                      # traffic direction along u for this lane
    x_out = side * st.hw
    x_in = side * (st.hw - width)
    x_line = sorted((x_in, side * (st.hw - width + line)))
    items = [(s0, s1, x_line[0], x_line[1])]
    o = rects(name + "_line", st, items, PAINT_Z, T.paint, c, kind="radfahrstreifen")
    o["width"], o["line"], o["side"] = width, line, side
    out = dict(line=o, pictos=[], sign=None, x_in=x_in, x_out=x_out, furt=[])
    for (sa, sb) in (furt or []):
        f = rects(name + "_furt", st, dashes(sa, sb, FURT_DASH, FURT_GAP, x_line[0], x_line[1]), PAINT_Z, T.paint,
                  c, kind="radfurt")
        out["furt"].append(f)
    if pictos:
        mid_x = side * (st.hw - (width - line) / 2 - 0.15)
        p0 = max(s0, picto_from) if picto_from is not None else s0
        s = (p0 + 8.0) if d > 0 else (s1 - 8.0)
        while p0 + 4 < s < s1 - 4:
            out["pictos"].append(picto(T, c, st, s, mid_x, d, name=name + "_picto"))
            s += d * PICTO_SPACING
    if sign:
        s_sign = sign_s if sign_s is not None else ((s0 + 2.0) if d > 0 else (s1 - 2.0))
        out["sign"] = sign_post(c, st, s_sign, side, [((SIGN_SET, "237"), 0.6)], sign=d, bottom=SIGN_BOTTOM,
                                name=name + "_237")
    return out


def schutzstreifen(T, c, st, side=+1, s0=None, s1=None, width=SCHUTZ_W, line=NARROW, dash=SCHUTZ_DASH,
                   gap=SCHUTZ_GAP, pictos=True, name="schutzstreifen"):
    """Schutzstreifen (advisory lane): broken narrow line, lane 1.50 m from the kerb including the line. No sign."""
    s0 = st.s0 if s0 is None else s0
    s1 = st.s1 if s1 is None else s1
    d = side
    x_line = sorted((side * (st.hw - width), side * (st.hw - width + line)))
    o = rects(name + "_line", st, dashes(s0, s1, dash, gap, x_line[0], x_line[1]), PAINT_Z, T.paint, c,
              kind="schutzstreifen")
    o["width"], o["line"], o["side"], o["dash"], o["gap"] = width, line, side, dash, gap
    out = dict(line=o, pictos=[])
    if pictos:
        mid_x = side * (st.hw - (width - line) / 2 - 0.15)
        s = (s0 + 8.0) if d > 0 else (s1 - 8.0)
        while s0 + 4 < s < s1 - 4:
            out["pictos"].append(picto(T, c, st, s, mid_x, d, name=name + "_picto", length=1.4, width=0.8))
            s += d * PICTO_SPACING
    return out


def bike_lanes_x(T, c, J, axis="EW", kind="radfahrstreifen", sides=(+1, -1)):
    """Bike lanes on both arms of one axis of a town.Junction, with Radwegfurt markings across the junction."""
    out = []
    names = ("E", "W") if axis == "EW" else ("N", "S")
    cross = J.hw_ns if axis == "EW" else J.hw_ew
    for nm in names:
        st = arm(J, nm)
        for side in sides:
            if kind == "radfahrstreifen":
                # the line runs straight on to the junction mouth (the kerb rounds away from it)
                out.append(radfahrstreifen(T, c, st, side, cross + 0.5, st.s1 - 4, picto_from=st.s0,
                                           sign_s=(st.s0 + 1.0) if side > 0 else (st.s1 - 6.0)))
            else:
                out.append(schutzstreifen(T, c, st, side, cross + 0.5, st.s1 - 4))
    if kind == "radfahrstreifen":
        thr = through(J, axis)
        for side in sides:
            x_line = sorted((side * (thr.hw - RAD_W), side * (thr.hw - RAD_W + RAD_LINE)))
            o = rects("radfurt", thr, dashes(-(cross + 0.5), cross + 0.5, FURT_DASH, FURT_GAP, x_line[0],
                                             x_line[1]), PAINT_Z, T.paint, c, kind="radfurt")
            out.append(dict(furt=[o]))
    return out


# ------------------------------------------------------------------ tram street
def tracks(T, c, st, centres=None, s0=None, s1=None, bed="asphalt", name="track"):
    """Embedded grooved rails (flush with the road) along street st. centres: lateral track centre lines (default
    two tracks 3.20 m apart). Gauge 1,435 mm between the running edges (inner faces of the rail heads).
    bed: 'asphalt' (sealing strips only) or 'setts' (stone setts between and beside the rails)."""
    X = mats(T)
    s0 = st.s0 if s0 is None else s0
    s1 = st.s1 if s1 is None else s1
    centres = centres if centres is not None else (-TRACK_SPACING / 2, TRACK_SPACING / 2)
    head, groove, guard, seal = [], [], [], []
    for xc in centres:
        for sgn in (-1, 1):
            e = xc + sgn * GAUGE / 2                # running edge (inner face of the head)
            # head outward of the running edge, groove and guard inward
            head.append((s0, s1, *sorted((e, e + sgn * RAIL_HEAD))))
            groove.append((s0, s1, *sorted((e, e - sgn * RAIL_GROOVE))))
            g0 = e - sgn * RAIL_GROOVE
            head.append((s0, s1, *sorted((g0, g0 - sgn * RAIL_GUARD))))
            seal.append((s0, s1, *sorted((e + sgn * RAIL_HEAD, e + sgn * (RAIL_HEAD + 0.025)))))
            seal.append((s0, s1, *sorted((g0 - sgn * RAIL_GUARD, g0 - sgn * (RAIL_GUARD + 0.025)))))
    out = {}
    if bed == "setts":
        bed_items = [(s0, s1, xc - GAUGE / 2 - 0.35, xc + GAUGE / 2 + 0.35) for xc in centres]
        out["bed"] = rects(name + "_bed", st, bed_items, 0.003, T.cobble, c, kind="trackbed")
    out["seal"] = rects(name + "_seal", st, seal, 0.0035, X["seal"], c)
    out["groove"] = rects(name + "_groove", st, groove, 0.0038, X["groove"], c, kind="groove")
    out["rails"] = rects(name + "_rails", st, head, 0.0045, X["rail"], c, kind="rail")
    out["rails"]["gauge"] = GAUGE
    out["rails"]["centres"] = list(centres)
    out["centres"] = list(centres)
    out["street"] = st
    return out


def overhead(T, c, st, centres=None, stations=None, span=32.0, s0=None, s1=None, skip=(), wire_h=WIRE_H,
             span_h=SPAN_H, pole_h=POLE_H, stagger=0.2, name="ocs"):
    """Overhead contact line with cross-span wires (Querverspannung) between two poles on the footways.
    stations: street positions of the pole pairs (default every `span` m from s0 to s1, leaving out any s inside
    a (a, b) range of `skip`). Contact wires run straight between stations, zig-zag +-stagger."""
    X = mats(T)
    s0 = st.s0 if s0 is None else s0
    s1 = st.s1 if s1 is None else s1
    centres = centres if centres is not None else (-TRACK_SPACING / 2, TRACK_SPACING / 2)
    if stations is None:
        stations = []
        s = s0
        while s <= s1 + 1e-6:
            if not any(a <= s <= b for a, b in skip):
                stations.append(s)
            s += span
    stations = sorted(stations)
    x_pole = st.hw + TN.KERB_W + 0.55
    wires, spans, hangers, insul = [], [], [], []
    poles = []
    zg = TN.KERB_H
    for i, s in enumerate(stations):
        for side in (-1, 1):
            q = st.p(s, side * x_pole)
            p = TN.cyl(name + "_pole", c, (q.x, q.y, zg + pole_h / 2), 0.13, pole_h, X["mast"], 20)
            # taper the pole a little and give it a cap
            for v in p.data.vertices:
                if v.co.z > 0:
                    v.co.x *= 0.7
                    v.co.y *= 0.7
            TN.cyl(name + "_cap", c, (q.x, q.y, zg + pole_h + 0.03), 0.1, 0.06, X["mast"], 20)
            TN.cyl(name + "_foot", c, (q.x, q.y, zg + 0.25), 0.17, 0.5, X["mast"], 20)
            poles.append(p)
        # cross-span wire with a gentle sag, from pole to pole
        n = 12
        pts = []
        for k in range(n + 1):
            x = -x_pole + 2 * x_pole * k / n
            sag = 0.35 * (1 - (x / x_pole) ** 2)
            pts.append(st.p3(s, x, span_h - sag))
        for k in range(n):
            spans.append((pts[k], pts[k + 1]))
        for side in (-1, 1):
            a = st.p3(s, side * (x_pole - 0.6), span_h - 0.35 * (1 - ((x_pole - 0.6) / x_pole) ** 2))
            b = st.p3(s, side * (x_pole - 0.95), span_h - 0.35 * (1 - ((x_pole - 0.95) / x_pole) ** 2))
            insul.append((a, b))
        zz = stagger * (1 if i % 2 == 0 else -1)
        for xc in centres:
            x = xc + zz
            sag = 0.35 * (1 - (x / x_pole) ** 2)
            hangers.append((st.p3(s, x, span_h - sag), st.p3(s, x, wire_h)))
            # short pull-off arm at the contact wire
            hangers.append((st.p3(s, x - 0.25, wire_h + 0.15), st.p3(s, x + 0.25, wire_h + 0.15)))
    for i in range(len(stations) - 1):
        za = stagger * (1 if i % 2 == 0 else -1)
        zb = -za
        for xc in centres:
            wires.append((st.p3(stations[i], xc + za, wire_h), st.p3(stations[i + 1], xc + zb, wire_h)))
    # the wires go on beyond the last station so the line does not stop in mid-air in a wide shot
    for (sa, sb) in ((stations[0], stations[0] - span), (stations[-1], stations[-1] + span)):
        i = 0 if sa == stations[0] else len(stations) - 1
        za = stagger * (1 if i % 2 == 0 else -1)
        for xc in centres:
            wires.append((st.p3(sa, xc + za, wire_h), st.p3(sb, xc - za, wire_h)))
    out = dict(poles=poles, stations=stations, wire_h=wire_h, centres=list(centres))
    out["contact"] = tubes(name + "_contact", wires, 0.0065, X["wire"], c, 6)
    out["contact"]["wire_h"] = wire_h
    out["span"] = tubes(name + "_span", spans, 0.006, X["mast"], c, 6)
    out["hangers"] = tubes(name + "_hangers", hangers, 0.008, X["mast"], c, 6)
    out["insulators"] = tubes(name + "_insul", insul, 0.035, X["insul"], c, 10)
    for k in ("contact", "span", "hangers"):
        out[k].visible_shadow = True
    return out


def tram_street_x(T, c, J, axis="NS", spacing=TRACK_SPACING, bed="asphalt", span=30.0):
    """Turn the approved X junction into a tram junction: two tracks straight through along `axis` and the overhead
    line, with poles kept off the junction mouth. Returns dict(street, tracks, ocs)."""
    st = through(J, axis)
    cross = J.hw_ew if axis == "NS" else J.hw_ns
    centres = (-spacing / 2, spacing / 2)
    tr = tracks(T, c, st, centres, -J.L + 2, J.L - 2, bed=bed)
    first = cross + J.R + 2.5
    stations = [-first, first]
    s = first + span
    while s < J.L - 20:
        stations += [s, -s]
        s += span
    ocs = overhead(T, c, st, centres, stations=stations)
    return dict(street=st, tracks=tr, ocs=ocs)


def tram_street(T, c, st, spacing=TRACK_SPACING, bed="asphalt", span=30.0, s0=None, s1=None):
    """Tracks and overhead line along a straight street frame."""
    s0 = st.s0 if s0 is None else s0
    s1 = st.s1 if s1 is None else s1
    centres = (-spacing / 2, spacing / 2)
    tr = tracks(T, c, st, centres, s0, s1, bed=bed)
    ocs = overhead(T, c, st, centres, span=span, s0=s0 + 4, s1=s1 - 4)
    return dict(street=st, tracks=tr, ocs=ocs)


def tram_path(street_frame, centre_x, sign=1, s0=None, s1=None):
    """jx.Path along a track centre line for a tram travelling along sign * u (right-hand running: the tram travelling
    along +u uses the track at x > 0)."""
    import jx
    st = street_frame
    s0 = st.s0 if s0 is None else s0
    s1 = st.s1 if s1 is None else s1
    a, b = (s0, s1) if sign > 0 else (s1, s0)
    pts = []
    n = max(2, int(abs(b - a) / 2.0))
    for k in range(n + 1):
        q = st.p(a + (b - a) * k / n, centre_x)
        pts.append((q.x, q.y))
    return jx.Path(pts)


def tram_stop(T, c, st, s, side=+1, length=32.0, height=0.24, name="tram_stop"):
    """Simple kerbside tram stop (Haltestellenkap): the footway raised to `height` over `length` (UNVERIFIED
    typical low-floor platform height), a glass shelter and Zeichen 224 when the library has it."""
    X = mats(T)
    xs = side * st.hw
    x0, x1 = sorted((xs, side * (st.hw + TN.KERB_W + 2.4)))
    items = [(s - length / 2, s + length / 2, x0, x1)]
    plat = rects(name + "_platform", st, items, height, T.pavers, c, kind="tram_stop")
    plat.visible_shadow = True
    # platform edge (kerb face) and a tactile strip
    q = st.p(s, side * (st.hw + 0.08))
    ang = st.heading(1)
    TN.box(name + "_edge", c, (q.x, q.y, height / 2), (length, 0.16, height), T.curb, rot_z=ang)
    q = st.p(s, side * (st.hw + 0.65))
    TN.box(name + "_tactile", c, (q.x, q.y, height + 0.004), (length - 1, 0.3, 0.008),
           W.principled("tp_tactile", (0.75, 0.75, 0.72), 0.7), rot_z=ang)
    # shelter: glass box with a dark frame and roof
    qs = st.p(s, side * (st.hw + TN.KERB_W + 1.8))
    glass = W.principled("tp_shelter_glass", (0.6, 0.7, 0.72), 0.05, spec=0.8)
    for dx in (-2.0, 2.0):
        e = st.p(s + dx, side * (st.hw + TN.KERB_W + 1.8))
        TN.box(name + "_post", c, (e.x, e.y, height + 1.25), (0.08, 0.08, 2.5), X["mast"], rot_z=ang)
    TN.box(name + "_roof", c, (qs.x, qs.y, height + 2.55), (4.4, 1.6, 0.1), X["mast"], rot_z=ang, bevel=0.02)
    eb = st.p(s, side * (st.hw + TN.KERB_W + 2.3))
    TN.box(name + "_back", c, (eb.x, eb.y, height + 1.25), (4.0, 0.03, 2.2), glass, rot_z=ang)
    if has_sign("224") or has_sign("224", "de-townplus"):
        set_ = SIGN_SET if has_sign("224") else "de-townplus"
        sign_post(c, st, s + length / 2 - 1.0, side, [((set_, "224"), 0.6)], sign=side, z=height,
                  name=name + "_224")
    return plat


# ------------------------------------------------------------------ pedestrians
def _skin(seed):
    tones = [(0.62, 0.42, 0.32), (0.45, 0.28, 0.18), (0.75, 0.55, 0.43), (0.3, 0.18, 0.11)]
    return tones[seed % len(tones)]


def _blob(name, c, loc, scale, mat, parent=None, seg=16, rings=10, rot=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=1.0)
    for v in bm.verts:
        v.co.x *= scale[0]
        v.co.y *= scale[1]
        v.co.z *= scale[2]
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    me.materials.append(mat)
    if parent:
        o.parent = parent
    return o


def _limb(name, c, top, bottom, r0, r1, mat, parent=None, seg=14):
    """Tapered rounded limb from top (radius r0) to bottom (radius r1), in the parent's space."""
    a, b = Vector(top), Vector(bottom)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r1, radius2=r0,
                          depth=(a - b).length)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    me.materials.append(mat)
    o.location = (a + b) / 2
    o.rotation_euler = (b - a).normalized().to_track_quat("-Z", "Y").to_euler()
    if parent:
        o.parent = parent
    sub = o.modifiers.new("s", "SUBSURF")
    sub.levels, sub.render_levels = 1, 2
    return o


def pedestrian(c, name="ped", seed=0, coat=None, trousers=None, height=1.76):
    """A stylised pedestrian (realistic proportions, soft shapes): coat, trousers, shoes, scarf, hair. Faces +y,
    feet at z = 0 on the origin. Legs and arms hang from pivots (hip_L/R, sh_L/R) so walk() can swing them.
    Returns dict(root, legs, arms)."""
    rnd = random.Random(seed)
    k = height / 1.76
    coats = [(0.08, 0.1, 0.16), (0.32, 0.12, 0.06), (0.22, 0.24, 0.2), (0.5, 0.38, 0.22), (0.05, 0.05, 0.05),
             (0.45, 0.06, 0.05)]
    coat_m = W.principled(name + "_coat", coat or rnd.choice(coats), 0.75)
    trou_m = W.principled(name + "_trousers", trousers or rnd.choice([(0.03, 0.035, 0.05), (0.12, 0.11, 0.1),
                                                                      (0.05, 0.08, 0.14)]), 0.8)
    skin_m = W.principled(name + "_skin", _skin(seed), 0.55)
    hair_m = W.principled(name + "_hair", rnd.choice([(0.02, 0.015, 0.01), (0.18, 0.1, 0.04), (0.4, 0.3, 0.15),
                                                      (0.35, 0.35, 0.33)]), 0.6)
    shoe_m = W.principled(name + "_shoe", (0.02, 0.02, 0.02), 0.4)
    scarf_m = W.principled(name + "_scarf", rnd.choice([(0.6, 0.45, 0.08), (0.55, 0.05, 0.08), (0.7, 0.68, 0.62),
                                                        (0.1, 0.3, 0.25)]), 0.9)
    root = bpy.data.objects.new(name, None)
    c.objects.link(root)
    legs, arms = [], []
    hip_z = 0.9 * k
    for sx in (-1, 1):
        hip = bpy.data.objects.new(f"{name}_hip_{'L' if sx < 0 else 'R'}", None)
        c.objects.link(hip)
        hip.parent = root
        hip.location = (sx * 0.095 * k, 0, hip_z)
        _limb(name + "_leg", c, (0, 0, 0), (0, 0, -hip_z + 0.07 * k), 0.075 * k, 0.05 * k, trou_m, hip)
        _blob(name + "_shoe", c, (0, 0.045 * k, -hip_z + 0.045 * k), (0.055 * k, 0.13 * k, 0.05 * k), shoe_m, hip)
        legs.append(hip)
    # coat: a soft tapered body from the shoulders to mid-thigh
    body = _limb(name + "_coat", c, (0, 0, 1.47 * k), (0, 0, 0.62 * k), 0.2 * k, 0.215 * k, coat_m, root, seg=18)
    body.scale = (1.0, 0.68, 1.0)
    _blob(name + "_shoulders", c, (0, 0, 1.43 * k), (0.215 * k, 0.14 * k, 0.08 * k), coat_m, root)
    _blob(name + "_scarf", c, (0, 0.0, 1.5 * k), (0.105 * k, 0.1 * k, 0.06 * k), scarf_m, root)
    _limb(name + "_neck", c, (0, 0, 1.58 * k), (0, 0, 1.48 * k), 0.05 * k, 0.055 * k, skin_m, root)
    _blob(name + "_head", c, (0, 0.01 * k, 1.66 * k), (0.085 * k, 0.1 * k, 0.115 * k), skin_m, root)
    _blob(name + "_hair", c, (0, -0.012 * k, 1.705 * k), (0.092 * k, 0.104 * k, 0.085 * k), hair_m, root)
    _blob(name + "_nose", c, (0, 0.105 * k, 1.65 * k), (0.016 * k, 0.02 * k, 0.022 * k), skin_m, root)
    for sx in (-1, 1):
        sh = bpy.data.objects.new(f"{name}_sh_{'L' if sx < 0 else 'R'}", None)
        c.objects.link(sh)
        sh.parent = root
        sh.location = (sx * 0.215 * k, 0, 1.42 * k)
        _limb(name + "_arm", c, (0, 0, 0), (sx * 0.035 * k, 0.02 * k, -0.58 * k), 0.055 * k, 0.045 * k, coat_m, sh)
        _blob(name + "_hand", c, (sx * 0.04 * k, 0.025 * k, -0.64 * k), (0.035 * k, 0.03 * k, 0.06 * k), skin_m, sh)
        arms.append(sh)
    return dict(root=root, legs=legs, arms=arms, name=name)


def leaves(c, st, s0, s1, sides=(-1, 1), n_per_m=6.0, seed=1, spread=0.55, name="leaves"):
    """Autumn leaves (October) gathered in the gutters of street st and a few on the footway edge: one mesh of
    small curled quads in four leaf colours."""
    rnd = random.Random(seed)
    cols = [(0.45, 0.16, 0.02), (0.6, 0.35, 0.03), (0.3, 0.12, 0.03), (0.52, 0.42, 0.08)]
    mats_ = []
    for k, col in enumerate(cols):
        nm = f"tp_leaf{k}"
        mats_.append(bpy.data.materials.get(nm) or W.principled(nm, col, 0.7))
    bm = bmesh.new()
    idx = []
    n = int(abs(s1 - s0) * n_per_m)
    for side in sides:
        for _ in range(n):
            s = rnd.uniform(s0, s1)
            # dense at the kerb, thinning out towards the road
            x = side * (st.hw - abs(rnd.gauss(0, spread * 0.45)))
            z = PAINT_Z + 0.004 + rnd.uniform(0, 0.01)
            if rnd.random() < 0.12:
                x = side * (st.hw + TN.KERB_W + rnd.uniform(0.0, 0.6))
                z = TN.KERB_H + 0.005
            q = st.p(s, x)
            a = rnd.uniform(0, 2 * math.pi)
            L, Wd = rnd.uniform(0.06, 0.11), rnd.uniform(0.04, 0.07)
            ca, sa = math.cos(a), math.sin(a)
            pts = [(-L / 2, 0, 0.0), (0, -Wd / 2, 0.006), (L / 2, 0, 0.0), (0, Wd / 2, 0.006)]
            vs = [bm.verts.new((q.x + px * ca - py * sa, q.y + px * sa + py * ca, z + pz)) for px, py, pz in pts]
            f = bm.faces.new(vs)
            f.material_index = rnd.randrange(len(cols))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats_:
        me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    up(o)
    return o


def _ring_segs(cy, cz, r, n=28, x=0.0):
    pts = [(x, cy + r * math.cos(2 * math.pi * k / n), cz + r * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]
    return [(pts[k], pts[k + 1]) for k in range(n)]


def cyclist(c, name="cyclist", seed=0, crank=0.6, frame_col=None):
    """A city bike (28 inch wheels, 1.08 m wheelbase) with a seated rider, forward +y, ground z = 0. The wheels are
    separate objects (wheel_F, wheel_R) that ride() spins; the legs are posed for the crank angle `crank`
    (radians). No logos. Returns dict(root, wheels, name)."""
    rnd = random.Random(seed)
    frame_m = W.principled(name + "_frame", frame_col or rnd.choice([(0.05, 0.12, 0.3), (0.4, 0.05, 0.04),
                                                                     (0.1, 0.1, 0.1), (0.12, 0.25, 0.15)]), 0.3,
                           metal=0.4, coat=0.5)
    tyre_m = W.principled(name + "_tyre", (0.02, 0.02, 0.02), 0.7)
    alu_m = W.principled(name + "_alu", (0.7, 0.71, 0.72), 0.25, metal=1.0)
    dark_m = W.principled(name + "_dark", (0.03, 0.03, 0.03), 0.5)
    root = bpy.data.objects.new(name, None)
    c.objects.link(root)
    R_ = 0.35
    ra, fa = Vector((0, -0.54, R_)), Vector((0, 0.54, R_))
    bb = Vector((0, -0.07, 0.29))
    st_top = Vector((0, -0.25, 0.86))
    ht_top, ht_bot = Vector((0, 0.37, 0.98)), Vector((0, 0.42, 0.80))
    segs = [(bb, st_top), (st_top, ht_top + Vector((0, 0, -0.04))), (bb, ht_bot), (ht_top, ht_bot)]
    for sx in (-0.05, 0.05):
        segs += [(bb + Vector((sx, 0, 0)), ra + Vector((sx, 0, 0))),
                 (st_top + Vector((sx * 0.5, 0, -0.03)), ra + Vector((sx, 0, 0))),
                 (ht_bot + Vector((sx * 0.6, 0, 0)), fa + Vector((sx, 0, 0)))]
    fr = tubes(name + "_frametubes", segs, 0.018, frame_m, c, 8)
    fr.parent = root
    # stem, bars (swept back city bars), seat post, saddle, mudguards, rack, chainring
    bar_c = ht_top + Vector((0, -0.04, 0.08))
    segs = [(ht_top, bar_c), (Vector((-0.3, -0.12, 1.06)), Vector((-0.12, 0.0, 1.07))),
            (Vector((-0.12, 0.0, 1.07)), Vector((0.12, 0.0, 1.07))), (Vector((0.12, 0.0, 1.07)), Vector((0.3, -0.12, 1.06))),
            (st_top, st_top + Vector((0, -0.03, 0.1)))]
    segs = [(a + Vector((0, 0.36, 0)) if i in (1, 2, 3) else a, b + Vector((0, 0.36, 0)) if i in (1, 2, 3) else b)
            for i, (a, b) in enumerate(segs)]
    o = tubes(name + "_bars", segs, 0.012, alu_m, c, 8)
    o.parent = root
    sad = _blob(name + "_saddle", c, (0, -0.27, 0.99), (0.08, 0.14, 0.035), dark_m, root)
    for wy, a0, a1 in ((ra.y, 0.15, 2.4), (fa.y, 0.75, 3.0)):
        arc_pts = [(0, wy + (R_ + 0.04) * math.cos(a), R_ + (R_ + 0.04) * math.sin(a))
                   for a in [a0 + (a1 - a0) * k / 14 for k in range(15)]]
        g = tubes(name + "_guard", [(arc_pts[k], arc_pts[k + 1]) for k in range(14)], 0.022, frame_m, c, 6)
        g.scale.x = 1.0
        g.parent = root
    rack = tubes(name + "_rack", [(Vector((-0.08, -0.85, 0.78)), Vector((-0.08, -0.4, 0.8))),
                                  (Vector((0.08, -0.85, 0.78)), Vector((0.08, -0.4, 0.8))),
                                  (Vector((-0.08, -0.85, 0.78)), ra + Vector((-0.06, 0, 0))),
                                  (Vector((0.08, -0.85, 0.78)), ra + Vector((0.06, 0, 0)))], 0.008, alu_m, c, 6)
    rack.parent = root
    ring = TN.cyl(name + "_chainring", c, (0.07, bb.y, bb.z), 0.1, 0.006, alu_m, 24, (0, math.pi / 2, 0))
    ring.parent = root
    # rear light and front lamp
    TN.box(name + "_rearlight", c, (0, -0.9, 0.78), (0.06, 0.03, 0.04),
           W.principled(name + "_red", (0.5, 0.01, 0.01), 0.2, emit=(1, 0.02, 0.01), estr=1.5)).parent = root
    TN.box(name + "_lamp", c, (0, 0.62, 0.92), (0.07, 0.06, 0.06),
           W.principled(name + "_lampm", (0.9, 0.9, 0.85), 0.2, emit=(1, 0.97, 0.9), estr=1.0)).parent = root
    wheels = []
    for nm, ax in (("R", ra), ("F", fa)):
        wh = bpy.data.objects.new(f"{name}_wheel_{nm}", None)
        c.objects.link(wh)
        wh.parent = root
        wh.location = ax
        wh.rotation_mode = "XYZ"
        t = tubes(name + "_tyre", _ring_segs(0, 0, R_ - 0.02, 36), 0.02, tyre_m, c, 8)
        t.parent = wh
        rim = tubes(name + "_rim", _ring_segs(0, 0, R_ - 0.045, 36), 0.008, alu_m, c, 6)
        rim.parent = wh
        sp = []
        for k in range(18):
            a = 2 * math.pi * k / 18
            sp.append(((0.02 if k % 2 else -0.02, 0, 0),
                       (0, (R_ - 0.05) * math.cos(a + 0.2), (R_ - 0.05) * math.sin(a + 0.2))))
        s_ = tubes(name + "_spokes", sp, 0.0022, alu_m, c, 4)
        s_.parent = wh
        TN.cyl(name + "_hub", c, (0, 0, 0), 0.03, 0.1, alu_m, 12, (0, math.pi / 2, 0)).parent = wh
        wheels.append(wh)
    # rider: hips over the saddle, torso leaning to the bars, legs to the pedals (2-bone IK in the side plane)
    k = 1.0
    coat = W.principled(name + "_coat", rnd.choice([(0.55, 0.4, 0.12), (0.1, 0.2, 0.35), (0.6, 0.12, 0.08),
                                                     (0.15, 0.15, 0.17)]), 0.75)
    trou = W.principled(name + "_trousers", (0.04, 0.045, 0.06), 0.8)
    skin = W.principled(name + "_skin", _skin(seed + 1), 0.55)
    helmet = W.principled(name + "_helmet", rnd.choice([(0.9, 0.9, 0.88), (0.05, 0.05, 0.06), (0.1, 0.35, 0.6)]),
                          0.35, coat=0.6)
    shoe = W.principled(name + "_shoe", (0.03, 0.03, 0.03), 0.5)
    hip = Vector((0, -0.25, 1.04))
    sh = Vector((0, 0.05, 1.5))
    body = _limb(name + "_torso", c, tuple(sh + Vector((0, -0.04, 0.02))), tuple(hip), 0.17, 0.17, coat, root, 16)
    body.scale.x = 1.0
    _blob(name + "_hips", c, tuple(hip + Vector((0, 0, 0.02))), (0.16, 0.13, 0.1), trou, root)
    _blob(name + "_neck", c, tuple(sh + Vector((0, 0.04, 0.08))), (0.05, 0.05, 0.06), skin, root)
    head = sh + Vector((0, 0.1, 0.22))
    _blob(name + "_head", c, tuple(head), (0.085, 0.1, 0.11), skin, root)
    _blob(name + "_helmet", c, tuple(head + Vector((0, -0.01, 0.055))), (0.105, 0.135, 0.085), helmet, root)
    for sx in (-1, 1):
        s0 = sh + Vector((sx * 0.19, 0, 0))
        hand = Vector((sx * 0.28, 0.25, 1.07))
        elbow = (s0 + hand) / 2 + Vector((sx * 0.06, -0.05, -0.04))
        _limb(name + "_uarm", c, tuple(s0), tuple(elbow), 0.05, 0.045, coat, root)
        _limb(name + "_farm", c, tuple(elbow), tuple(hand), 0.045, 0.04, coat, root)
        _blob(name + "_hand", c, tuple(hand), (0.035, 0.045, 0.03), skin, root)
        a = crank + (0 if sx > 0 else math.pi)
        ped = bb + Vector((sx * 0.13, 0.17 * math.cos(a), 0.17 * math.sin(a)))
        hp = hip + Vector((sx * 0.1, 0, 0))
        d = Vector((0, ped.y - hp.y, ped.z - hp.z))
        L1, L2 = 0.44, 0.45
        dist = min(d.length, L1 + L2 - 0.01)
        cos_a = (L1 * L1 + dist * dist - L2 * L2) / (2 * L1 * dist)
        ang = math.acos(max(-1, min(1, cos_a)))
        base = math.atan2(d.z, d.y)
        kn_a = base + ang                      # knee forward and up
        knee = hp + Vector((0, L1 * math.cos(kn_a), L1 * math.sin(kn_a)))
        knee.x = hp.x + sx * 0.02
        _limb(name + "_thigh", c, tuple(hp), tuple(knee), 0.075, 0.055, trou, root)
        _limb(name + "_shin", c, tuple(knee), tuple(ped + Vector((0, 0, 0.05))), 0.052, 0.042, trou, root)
        _blob(name + "_shoe", c, tuple(ped + Vector((0, 0.04, 0.02))), (0.045, 0.12, 0.045), shoe, root)
        cr = tubes(name + "_crank", [(bb + Vector((sx * 0.09, 0, 0)), ped)], 0.012, alu_m, c, 6)
        cr.parent = root
    return dict(root=root, wheels=wheels, name=name, R=R_)


def ride(cy, path, sv, frames):
    """Bake a cyclist along a jx.Path with (s, v) per frame; the wheels spin with the distance travelled."""
    import stage
    locs, rots = [], []
    for (s, v) in sv:
        p, yaw = path.at(s)
        locs.append((p.x, p.y, 0.0))
        rots.append((0.0, 0.0, yaw - math.pi / 2))
    for i in range(1, len(rots)):
        a = rots[i][2]
        while a - rots[i - 1][2] > math.pi:
            a -= 2 * math.pi
        while a - rots[i - 1][2] < -math.pi:
            a += 2 * math.pi
        rots[i] = (0.0, 0.0, a)
    stage.bake_motion(cy["root"], frames, locs, rots)
    for wh in cy["wheels"]:
        stage.bake_motion(wh, frames, [tuple(wh.location)] * len(frames),
                          [(-s / cy["R"], 0.0, 0.0) for (s, v) in sv])
    return cy


def walk(ped, path, sv, frames, fps=30, stride=1.4):
    """Bake a pedestrian along a jx.Path with (s, v) per frame (jx.kinematics); legs and arms swing with the
    distance walked (one stride = two steps)."""
    import stage
    locs, rots = [], []
    for (s, v) in sv:
        p, yaw = path.at(s)
        locs.append((p.x, p.y, 0.0))
        rots.append((0.0, 0.0, yaw - math.pi / 2))
    for i in range(1, len(rots)):
        a = rots[i][2]
        while a - rots[i - 1][2] > math.pi:
            a -= 2 * math.pi
        while a - rots[i - 1][2] < -math.pi:
            a += 2 * math.pi
        rots[i] = (0.0, 0.0, a)
    stage.bake_motion(ped["root"], frames, locs, rots)
    zero = [(0.0, 0.0, 0.0)] * len(frames)
    for limb, base, amp in [(ped["legs"][0], 0.0, 0.42), (ped["legs"][1], math.pi, 0.42),
                            (ped["arms"][0], math.pi, 0.32), (ped["arms"][1], 0.0, 0.32)]:
        rr = []
        for (s, v) in sv:
            ph = 2 * math.pi * s / stride + base
            a = amp * math.sin(ph) * min(1.0, v / 0.8)
            rr.append((a, 0.0, 0.0))
        stage.bake_motion(limb, frames, [tuple(limb.location)] * len(frames), rr)
    return ped
