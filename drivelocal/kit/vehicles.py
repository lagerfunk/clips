"""Stylised but correctly proportioned European traffic: hatchback, estate, saloon, SUV, panel van, German police
estate, 40 t articulated lorry. Bodies are subdivision cages built from cross-section stations, wheel arches cut with
booleans, lights and plates placed by ray casting onto the body. Front is +y, ground is z = 0, centre x = 0."""
import json
import math

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.interpolate import poly_3d_calc

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
        S(3.72, 0.26, 0.50, 0.88, 0.94, 0.94, 0.84),     # bonnet and an upright nose, not a wedge
        S(4.13, 0.30, 0.50, 0.76, 0.86, 0.85, 0.78),
        S(4.28, 0.36, 0.52, 0.70, 0.70, 0.80, 0.58)],
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
        S(4.18, 0.27, 0.50, 0.87, 0.94, 0.93, 0.84),
        S(4.62, 0.30, 0.50, 0.75, 0.86, 0.84, 0.78),
        S(4.77, 0.36, 0.52, 0.69, 0.70, 0.79, 0.58)],
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
        S(4.20, 0.27, 0.50, 0.86, 0.94, 0.92, 0.84),
        S(4.56, 0.30, 0.50, 0.74, 0.86, 0.83, 0.78),
        S(4.71, 0.36, 0.52, 0.68, 0.70, 0.78, 0.58)],
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


def _alive(idb):
    try:
        idb.name
        return True
    except (ReferenceError, AttributeError):
        return False


def mat(key, *a, **k):
    if key not in _mats or not _alive(_mats[key]):
        _mats[key] = W.principled(key, *a, **k)
    return _mats[key]


# Lit lamp colours and levels. The scenes render through AgX (Punchy), which walks any light brighter than about
# 1.0 (linear) towards white: the old brake level (0.8 + 5.2) came out pink, the old indicator (12) cream. So the lit
# colours are fully saturated and the lit levels sit where AgX still shows them saturated, with a small brighter core
# in the middle of each lens. Through AgX Punchy (display hue / saturation): LIT_RED at 0.5 to 1.2 is hue 0 to 5 deg,
# saturation 0.90 to 1.0; LIT_AMBER at 0.5 to 1.0 is hue 35 to 37 deg, saturation 0.95 to 1.0.
LIT_RED = (1.0, 0.0, 0.02)     # brake, tail, third brake light (a touch of blue: pure red drifts to orange in AgX)
LIT_AMBER = (1.0, 0.33, 0.0)   # indicators
TAIL_REST = 0.25    # car_tail's own glow (Principled Emission Strength; weather scales it for tail lights at dusk)
BRAKE_GAIN = 0.85   # x instance property "brake" (0 or 1): the lit brake lens
TAIL_GAIN = 0.3     # x instance property "tail" (motion.bake night flag)
IND_ON_REF = 12.0   # motion.IND_ON, the value motion keys on ind_l / ind_r when an indicator is lit
IND_LIT = 0.75      # emission of a lit indicator lens
IND_OFF = (0.30, 0.10, 0.0)   # unlit indicator lens: a dark amber, so a lit lens (LIT_AMBER) reads clearly brighter in sun
HEAD_GAIN = 6.0     # x "head": low beams (white, unchanged)
# hot core: emission x (1 + k) inside r_in of the lens centre (object origin), back to x 1 at r_out (metres)
BRAKE_CORE = (0.8, 0.012, 0.036)
IND_CORE = (0.35, 0.01, 0.03)
# a lit lens is lit from behind: its sunlit diffuse and its rest glow (car_tail's, which weather turns up for tail
# lights at dusk and night) drop to (1 - LIT_DIM) while the main term is on, so the lamp's own light plus sun or tail
# glow stays under the level where AgX bleaches it. Unlit lenses keep their colour exactly.
LIT_DIM = 0.7


def lamp(key, color, rough, emit, estr, terms, core=None, lit_ref=None):
    """A lamp material: the usual Principled (its Emission Strength stays a plain value that scripts may set) plus an
    Emission of the same colour whose strength is the sum of per-instance custom properties read with an Attribute
    node of type Instancer, each times a gain: terms = [("brake", 0.85), ("tail", 0.3)]. One material serves every
    car; motion.bake keys the properties on each car instance. A car without them reads 0 and looks unchanged.
    core = (k, r_in, r_out): the property terms are k times brighter at the lens centre (the part's object origin),
    fading back to 1 x between r_in and r_out metres: a small hot core instead of a lens that blows out to white.
    lit_ref: the first term's value when the lamp is fully lit (brake for car_tail, ind_l / ind_r for the indicators);
    as that term reaches it, the base colour and the Principled emission colour (the rest glow) fade to (1 - LIT_DIM)
    of themselves. Both stay as given while the lamp is off."""
    if key in _mats and _alive(_mats[key]):
        return _mats[key]
    m = W.principled(key, color, rough, emit=emit, estr=estr)
    nt = m.node_tree
    out = nt.nodes["Material Output"]
    p = nt.nodes["Principled BSDF"]
    acc = None
    first = None
    for attr, gain in terms:
        a = nt.nodes.new("ShaderNodeAttribute")
        a.attribute_type = "INSTANCER"
        a.attribute_name = attr
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = gain
        nt.links.new(a.outputs["Fac"], mul.inputs[0])
        # per-part opt-out: an object with the custom property dl_no_<attr> = 1 ignores this term (the third brake
        # light ignores "tail", reflectors ignore everything), so one material still serves all those parts
        ma = nt.nodes.new("ShaderNodeAttribute")
        ma.attribute_type = "OBJECT"
        ma.attribute_name = "dl_no_" + attr
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        nt.links.new(ma.outputs["Fac"], inv.inputs[1])
        mul2 = nt.nodes.new("ShaderNodeMath")
        mul2.operation = "MULTIPLY"
        nt.links.new(mul.outputs[0], mul2.inputs[0])
        nt.links.new(inv.outputs[0], mul2.inputs[1])
        mul = mul2
        if acc is None:
            acc = first = mul
        else:
            add = nt.nodes.new("ShaderNodeMath")
            add.operation = "ADD"
            nt.links.new(acc.outputs[0], add.inputs[0])
            nt.links.new(mul.outputs[0], add.inputs[1])
            acc = add
    if lit_ref:
        lf = nt.nodes.new("ShaderNodeMath")              # 1 - LIT_DIM * min(1, first term / lit_ref)
        lf.operation = "DIVIDE"
        lf.use_clamp = True
        nt.links.new(first.outputs[0], lf.inputs[0])
        lf.inputs[1].default_value = lit_ref
        fd = nt.nodes.new("ShaderNodeMath")
        fd.operation = "MULTIPLY_ADD"
        nt.links.new(lf.outputs[0], fd.inputs[0])
        fd.inputs[1].default_value = -LIT_DIM
        fd.inputs[2].default_value = 1.0
        bc = nt.nodes.new("ShaderNodeVectorMath")
        bc.operation = "SCALE"
        bc.label = "dl_lit_dim"
        bc.inputs[0].default_value = color
        nt.links.new(fd.outputs[0], bc.inputs["Scale"])
        nt.links.new(bc.outputs[0], p.inputs["Base Color"])
        if estr:      # the rest glow (weather carries this link into its tail-light group and scales it)
            ec = nt.nodes.new("ShaderNodeVectorMath")
            ec.operation = "SCALE"
            ec.label = "dl_lit_rest"
            ec.inputs[0].default_value = emit
            nt.links.new(fd.outputs[0], ec.inputs["Scale"])
            nt.links.new(ec.outputs[0], p.inputs["Emission Color"])
    if core:
        k, r_in, r_out = core
        tc = nt.nodes.new("ShaderNodeTexCoord")
        ln = nt.nodes.new("ShaderNodeVectorMath")
        ln.operation = "LENGTH"
        nt.links.new(tc.outputs["Object"], ln.inputs[0])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.interpolation_type = "SMOOTHSTEP"
        mr.clamp = True
        mr.inputs["From Min"].default_value = r_in
        mr.inputs["From Max"].default_value = r_out
        mr.inputs["To Min"].default_value = 1.0 + k
        mr.inputs["To Max"].default_value = 1.0
        nt.links.new(ln.outputs["Value"], mr.inputs["Value"])
        hot = nt.nodes.new("ShaderNodeMath")
        hot.operation = "MULTIPLY"
        hot.label = "dl_core"
        nt.links.new(acc.outputs[0], hot.inputs[0])
        nt.links.new(mr.outputs["Result"], hot.inputs[1])
        acc = hot
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*emit, 1)
    nt.links.new(acc.outputs[0], em.inputs["Strength"])
    sh = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(p.outputs[0], sh.inputs[0])
    nt.links.new(em.outputs[0], sh.inputs[1])
    nt.links.new(sh.outputs[0], out.inputs["Surface"])
    _mats[key] = m
    return m


def lamp_mats():
    """Amber indicator lenses, left and right (properties ind_l, ind_r: 0 or motion.IND_ON = 12, scaled so a lit lens
    emits IND_LIT in LIT_AMBER, with a hot core)."""
    g = IND_LIT / IND_ON_REF
    return (lamp("dl_ind_L", IND_OFF, 0.15, LIT_AMBER, 0.0, [("ind_l", g)], core=IND_CORE, lit_ref=IND_LIT),
            lamp("dl_ind_R", IND_OFF, 0.15, LIT_AMBER, 0.0, [("ind_r", g)], core=IND_CORE, lit_ref=IND_LIT))


def common():
    return dict(
        glass=mat("car_glass", (0.012, 0.016, 0.02), 0.04, spec=0.8, coat=1.0),
        tyre=mat("car_tyre", (0.025, 0.025, 0.025), 0.75),
        rim=mat("car_rim", (0.72, 0.73, 0.75), 0.28, metal=1.0),
        plastic=mat("car_plastic", (0.03, 0.03, 0.032), 0.55),
        head=lamp("car_head", (0.9, 0.9, 0.88), 0.1, (1, 0.97, 0.9), 1.5, [("head", HEAD_GAIN)]),
        tail=lamp("car_tail", (0.5, 0.01, 0.012), 0.15, LIT_RED, TAIL_REST,
                  [("brake", BRAKE_GAIN), ("tail", TAIL_GAIN)], core=BRAKE_CORE, lit_ref=BRAKE_GAIN),

        plate=mat("car_plate", (0.88, 0.88, 0.86), 0.35),
        euband=mat("car_euband", (0.0, 0.05, 0.35), 0.4),
        plate_d=mat("car_plate_d", (0.95, 0.95, 0.95), 0.5),
        plate_txt=mat("car_plate_txt", (0.01, 0.01, 0.01), 0.5),
        arch=mat("car_arch", (0.012, 0.012, 0.012), 0.8),
    )


def paint(name, color, metal=0.45):
    return mat("paint_" + name, color, 0.28, metal=metal, coat=1.0)


def rim(root, g, x, y, z, R, sx, style="alloy", name="rim"):
    """Wheel face on the outer side of a tyre (axle along x, sx = +1 right, -1 left), so a turning wheel reads as
    turning: alloy = five spokes over a dark barrel with a lip and a centre cap; steel = a lorry or bus disc wheel
    with ten hand holes and a hub. R is the rim radius; the face sits at x."""
    C = common()
    dark = mat("car_rim_dark", (0.025, 0.025, 0.028), 0.55)
    bm = bmesh.new()

    def ring(rr, xo, n=32, a0=0.0):
        return [bm.verts.new((xo, y + rr * math.cos(a0 + 2 * math.pi * k / n),
                              z + rr * math.sin(a0 + 2 * math.pi * k / n))) for k in range(n)]

    def disc(rr, xo, mi, n=32):
        f = bm.faces.new(ring(rr, xo, n) if sx > 0 else list(reversed(ring(rr, xo, n))))
        f.material_index = mi

    def tube(r0, r1, xo, mi, n=32):
        a, b = ring(r0, xo, n), ring(r1, xo, n)
        for k in range(n):
            k2 = (k + 1) % n
            q = [a[k], a[k2], b[k2], b[k]]
            f = bm.faces.new(q if sx < 0 else list(reversed(q)))
            f.material_index = mi

    def block(ri, ro, a, hw_i, hw_o, x0, x1, mi):
        ca, sa = math.cos(a), math.sin(a)
        pts = []
        for xx in (x0, x1):
            for rr, hw in ((ri, -hw_i), (ri, hw_i), (ro, hw_o), (ro, -hw_o)):
                pts.append(bm.verts.new((xx, y + rr * ca - hw * sa, z + rr * sa + hw * ca)))
        for q, flip in (((0, 1, 2, 3), True), ((4, 5, 6, 7), False), ((0, 1, 5, 4), False), ((1, 2, 6, 5), False),
                        ((2, 3, 7, 6), False), ((3, 0, 4, 7), False)):
            vv = [pts[i] for i in q]
            try:
                f = bm.faces.new(vv)
                f.material_index = mi
            except ValueError:
                pass

    f0 = x                                    # outer face
    d = sx * 0.035                            # dish depth
    if style == "alloy":
        disc(R * 0.93, f0 - d, 1)             # dark barrel behind the spokes
        tube(R * 0.93, R, f0, 0)              # lip
        for k in range(5):
            block(R * 0.17, R * 0.93, math.pi / 2 + 2 * math.pi * k / 5, R * 0.13, R * 0.075, f0 - d, f0 - sx * 0.004, 0)
        disc(R * 0.24, f0 + sx * 0.002, 0, 20)
        disc(R * 0.1, f0 + sx * 0.004, 1, 12)
    else:                                     # steel disc wheel
        disc(R, f0 - sx * 0.01, 0)
        for k in range(10):
            a = 2 * math.pi * (k + 0.5) / 10
            block(R * 0.6, R * 0.78, a, R * 0.07, R * 0.09, f0 - sx * 0.008, f0 - sx * 0.006, 1)
        disc(R * 0.4, f0 + sx * 0.012, 0, 24)
        for k in range(10):
            a = 2 * math.pi * k / 10
            block(R * 0.3, R * 0.34, a, R * 0.025, R * 0.025, f0 + sx * 0.012, f0 + sx * 0.03, 0)
        disc(R * 0.2, f0 + sx * 0.05, 1, 16)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(C["rim"])
    me.materials.append(dark)
    o = bpy.data.objects.new(name, me)
    root.objects.link(o)
    o.parent = g
    return o


CREASE_LONG = {1: 0.7, 8: 0.7, 2: 0.55, 7: 0.55, 3: 0.75, 6: 0.75, 4: 0.6, 5: 0.6}
C_PILLAR_CREASE = 0.0
CAP_INSET = 0.05      # flat front and rear faces of the cars out to this far from their corners (m)


def body_mesh(kind, body_mat, glass_mat, trim_mat, band=None):
    """Material slots: 0 paint, 1 glass, 2 dark lower trim, 3 police band."""
    kind_in = kind
    k = KINDS[kind] if isinstance(kind, str) else kind
    kind = kind if isinstance(kind, str) else k.get("name", "shell")
    Wh = k["W"]
    st = k["stations"]
    spans = k["spans"]
    bm = bmesh.new()
    cl = bm.edges.layers.float.new("crease_edge")
    rings = []
    for (y, zb, zs, zbelt, w, zwin, wwin, zr, wr) in st:
        tk = k.get("tuck", 0.9)
        pts = [(-tk * w, zb), (-w, zs), (-0.985 * w, zbelt), (-wwin, zwin), (-wr, zr),
               (wr, zr), (wwin, zwin), (0.985 * w, zbelt), (w, zs), (tk * w, zb)]
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
    # end caps as a strip of quads across the car: bumper (trim), lower panel, upper panel, top. Cars get two extra
    # columns `cap` metres in from each side, so the front and rear faces stay flat out to near their corners (the
    # lamp units sit on them as flat plates) and the corners round off within that margin
    cap = k.get("cap", CAP_INSET) if isinstance(kind_in, str) else k.get("cap", 0.0)
    cap_crease = {}
    for ring_, flip, glass in ((rings[0], True, k.get("rear_glass")), (rings[-1], False, k.get("front_glass"))):
        inner = {}
        if cap:
            for lv in range(5):
                a, b = ring_[lv].co, ring_[9 - lv].co
                t = min(0.3, cap / max(1e-6, (b - a).length))
                inner[lv] = (bm.verts.new(a.lerp(b, t)), bm.verts.new(a.lerp(b, 1 - t)))
        for (a1, a2, b2, b1), idx in (((0, 1, 8, 9), 2), ((1, 2, 7, 8), 0), ((2, 3, 6, 7), 1 if glass else 0),
                                      ((3, 4, 5, 6), 0)):
            if cap:
                (l1, r1), (l2, r2) = inner[a1], inner[a2]
                qs = [[ring_[a1], ring_[a2], l2, l1], [l1, l2, r2, r1], [r1, r2, ring_[b2], ring_[b1]]]
                if a1 == 1:                      # the bumper's top line, across the whole cap
                    for e_ in ((ring_[1], l1), (l1, r1), (r1, ring_[8])):
                        cap_crease[frozenset(e_)] = 0.9
            else:
                qs = [[ring_[a1], ring_[a2], ring_[b2], ring_[b1]]]
            for q in qs:
                f = bm.faces.new(list(reversed(q)) if flip else q)
                f.material_index = idx
    bm.edges.ensure_lookup_table()
    pos = {v: (ii, jj) for ii, r in enumerate(rings) for jj, v in enumerate(r)}
    # a short, steep tailgate span (hatch, estate, SUV): the roof-edge creases stop at the top of the C-pillar instead
    # of bending down it (a creased edge turning through 70 degrees pinches the surface at the rear roof corner)
    soft = {i for i, t in enumerate(spans) if t == "f" and i < len(spans) // 2
            and abs(st[i + 1][7] - st[i][7]) > 0.25 and st[i + 1][0] - st[i][0] < 0.3}
    for e in bm.edges:
        a_, b_ = e.verts
        ia, ib = pos.get(a_), pos.get(b_)
        if ia is None or ib is None:
            e[cl] = cap_crease.get(frozenset((a_, b_)), 0.0)
            continue
        if ia[1] == ib[1] and abs(ia[0] - ib[0]) == 1:          # along the car
            e[cl] = min(1.0, CREASE_LONG.get(ia[1], 0.0) * k.get("crease", 1.0))
            if min(ia[0], ib[0]) in soft and ia[1] in (3, 4, 5, 6):
                e[cl] = C_PILLAR_CREASE
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


# ------------------------------------------------------------------ parts moulded onto the body (lamps, trim)
_TREES = {}


def _tree(body):
    """BVH of the body mesh in its own coordinates (cached per mesh; car() drops it when the car is done)."""
    key = body.data.as_pointer()
    if key not in _TREES:
        me = body.data
        _TREES[key] = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    return _TREES[key]


def rrect(w, h, r, n=7):
    """Rounded rectangle outline w x h (corner radius r), counter-clockwise, centred on 0."""
    r = max(0.002, min(r, w / 2 - 1e-4, h / 2 - 1e-4))
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180),
                       (w / 2 - r, -h / 2 + r, 270)):
        for i in range(n):
            a = math.radians(a0 + 90.0 * i / (n - 1))
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def rpoly(pts, r, n=6):
    """Counter-clockwise polygon with every corner rounded (radius about r)."""
    out = []
    m = len(pts)
    for i in range(m):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % m])
        d0, d1 = p0 - p1, p2 - p1
        rr = min(r, d0.length * 0.45, d1.length * 0.45)
        a, b = p1 + d0.normalized() * rr, p1 + d1.normalized() * rr
        for k in range(n):
            t = k / (n - 1)
            q = a * (1 - t) ** 2 + p1 * (2 * t * (1 - t)) + b * (t * t)
            out.append((q.x, q.y))
    return out


def conform(root_coll, parent, body, origin, direction, size, m, offset=0.002, skirt=0.0025, corner=0.3, shape=None,
            side=0, name="lamp", rings=3, shift=(0.0, 0.0)):
    """A lens or trim panel moulded onto the body, so it sits flush instead of standing off it as a box: ray cast from
    origin along direction (as stick), then an outline in the tangent plane at the hit (a rounded rectangle
    size[0] x size[1], or shape = counter-clockwise (u, v) points in metres) filled with rings, every point snapped to
    the nearest body surface and lifted by `offset` along its normal, with a skirt that dips `skirt` under the surface
    so no gap shows at grazing angles. u is horizontal (outwards when side = -1/+1 on a front or rear face, forwards
    on a side face), v points up the surface. The object origin is the lens centre (headlight spot lamps and
    weather read it). Returns the object or None."""
    bmw = _mw(body)
    inv = bmw.inverted()
    hit, loc, nrm, _i = body.ray_cast(inv @ Vector(origin), (inv.to_3x3() @ Vector(direction)).normalized(),
                                      distance=5.0)
    if not hit:
        return None
    tree = _tree(body)
    n0 = nrm.normalized()
    u = Vector((0, 0, 1)).cross(n0)
    if u.length < 0.2:
        u = Vector((1, 0, 0)) if abs(n0.x) < 0.9 else Vector((0, 1, 0))
    u.normalize()
    if side and abs(u.x) > 0.5 and u.x * side < 0:
        u = -u
    if side and abs(u.x) <= 0.5 and u.y < 0:
        u = -u
    v = n0.cross(u).normalized()
    loc = loc + u * shift[0] + v * shift[1]
    P = [Vector(p) for p in (shape or rrect(size[0], size[1], corner * min(size[0], size[1])))]
    c2 = sum(P, Vector((0.0, 0.0))) / len(P)

    def snap(p2):
        # project along the lamp axis from well outside the body (a decal: the outline keeps its shape as seen
        # head-on); where the surface turns away, the nearest surface point from outside (wraps, never folds)
        p = loc + u * p2.x + v * p2.y + n0 * 0.3
        q, fn, _fi, _d = tree.ray_cast(p, -n0, 0.6)
        if q is None or fn.dot(n0) < 0.35:
            q, fn, _fi, _d = tree.find_nearest(p)
        if q is None:
            return p - n0 * 0.3, n0
        return q, (fn if fn.dot(n0) > -0.2 else n0)

    q0, f0 = snap(c2)
    cen = q0 + f0 * offset
    bm = bmesh.new()
    top = []
    for k in range(rings):
        s = (rings - k) / rings
        ring = []
        for p in P:
            q, fn = snap(c2 + (p - c2) * s)
            ring.append(bm.verts.new(q + fn * offset - cen))
        top.append(ring)
    cv = bm.verts.new((0.0, 0.0, 0.0))
    N = len(P)
    for k in range(rings - 1):
        for i in range(N):
            i2 = (i + 1) % N
            bm.faces.new((top[k][i], top[k][i2], top[k + 1][i2], top[k + 1][i])).smooth = True
    for i in range(N):
        bm.faces.new((top[-1][i], top[-1][(i + 1) % N], cv)).smooth = True
    sk = []
    for p in P:
        q, fn = snap(p)
        sk.append(bm.verts.new(q - fn * skirt - cen))
    for i in range(N):
        i2 = (i + 1) % N
        bm.faces.new((sk[i], sk[i2], top[0][i2], top[0][i])).smooth = False
    for i in range(N):                    # the lens edge is sharp: the skirt does not bend the lens shading
        e = bm.edges.get((top[0][i], top[0][(i + 1) % N]))
        if e:
            e.smooth = False
    bm.normal_update()
    if sum((f.normal.dot(n0) for f in bm.faces), 0.0) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    root_coll.objects.link(o)
    o.parent = parent
    o.matrix_basis = _mw(parent).inverted() @ bmw @ Matrix.Translation(cen)
    return o


def _mw(o):
    """World matrix from the parent chain (valid before a depsgraph update and outside the view layer)."""
    return (_mw(o.parent) @ o.matrix_parent_inverse if o.parent else Matrix.Identity(4)) @ o.matrix_basis


def seam(root_coll, parent, body, rays, m, width=0.005, offset=0.0015, name="seam"):
    """A shut line (or any thin line) drawn on the body through the hits of `rays` [(origin, direction)], each point
    snapped to the surface: bumper line, door gaps. Rays that miss are skipped."""
    inv = _mw(body).inverted()
    pts = []
    for o_, d_ in rays:
        hit, loc, nrm, _i = body.ray_cast(inv @ Vector(o_), (inv.to_3x3() @ Vector(d_)).normalized(), distance=5.0)
        if hit:
            pts.append((loc, nrm.normalized()))
    if len(pts) < 2:
        return None
    bm = bmesh.new()
    prev = None
    for i, (q, n) in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)][0] - pts[max(i - 1, 0)][0]).normalized()
        b = n.cross(t).normalized() * (width / 2)
        cur = (bm.verts.new(q + n * offset - b), bm.verts.new(q + n * offset + b))
        if prev:
            bm.faces.new((prev[0], cur[0], cur[1], prev[1]))
        prev = cur
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    root_coll.objects.link(o)
    o.parent = parent
    o.matrix_basis = _mw(parent).inverted() @ _mw(body)
    return o


def smooth_normals(body, cage_me, levels=3):
    """Custom split normals for a baked subdivision body from the same cage subdivided one level finer (without the
    wheel-arch booleans): the long, uneven faces of the level-2 body and the boolean's triangle fans no longer show as
    waves and dents in the reflections. Faces of the arch cut keep their own flat normals."""
    ref = bpy.data.objects.new("_ref_normals", cage_me)
    bpy.context.scene.collection.objects.link(ref)
    sub = ref.modifiers.new("sub", "SUBSURF")
    sub.levels = sub.render_levels = levels
    ev = ref.evaluated_get(bpy.context.evaluated_depsgraph_get())
    rm = ev.to_mesh()
    rv = [v.co.copy() for v in rm.vertices]
    rn = [v.normal.copy() for v in rm.vertices]
    rp = [tuple(p.vertices) for p in rm.polygons]
    ev.to_mesh_clear()
    bpy.data.objects.remove(ref)
    tree = BVHTree.FromPolygons(rv, rp)
    me = body.data
    arch = {i for i, m_ in enumerate(me.materials) if m_ and m_.name.startswith("car_arch")}
    vn = []
    for v in me.vertices:
        q, _fn, fi, d = tree.find_nearest(v.co)
        if q is None or d > 0.03:
            vn.append(None)
            continue
        ids = rp[fi]
        w = poly_3d_calc([rv[j] for j in ids], q)
        n = sum((rn[j] * w_ for j, w_ in zip(ids, w)), Vector()).normalized()
        vn.append(n)
    out = [None] * len(me.loops)
    for p in me.polygons:
        for li in p.loop_indices:
            n = vn[me.loops[li].vertex_index]
            out[li] = tuple(p.normal) if (p.material_index in arch or n is None) else tuple(n)
    me.normals_split_custom_set(out)
    bpy.data.meshes.remove(cage_me)
    return body


# District codes that are not assigned anywhere in Germany (ADAC list of all Unterscheidungszeichen, read
# 26 Oct 2026: the only Q codes are QFT and QLB, the only J codes are J, JB, JE, JEV, JL, JUEL). Every plate in the
# series uses one of these, so no combination can belong to a real car.
FICTIONAL_CODES = ("QX", "QZ", "JX", "JJ")
# Owner rule "no brand badges or logos": no company wordmarks on trucks, fictional names included (26 Oct 2026).
LABELS = False


def fictional(text):
    """Swap the district code of a plate text for an unassigned one (stable per plate): 'WI LK 204' -> 'QX LK 204'."""
    parts = text.split(" ")
    if len(parts) < 2 or parts[0] in FICTIONAL_CODES:
        return text
    k = sum(ord(ch) for ch in text) % len(FICTIONAL_CODES)
    return " ".join([FICTIONAL_CODES[k]] + parts[1:])


def plate_text(root_coll, parent, body, origin, direction, text, C, name="plate"):
    """German plate: white, EU band with a white D on the viewer's left. A sticker's local +y is the outward normal,
    so the viewer's right is local -x. The district code is always a fictional one (FICTIONAL_CODES)."""
    text = fictional(text)
    p = stick(root_coll, parent, body, origin, direction, (0.52, 0.012, 0.11), C["plate"], bevel=0.004, name=name)
    if not p:
        return
    band = stick(root_coll, parent, body, origin, direction, (0.045, 0.014, 0.105), C["euband"], bevel=0.0,
                 name=name + "_eu")
    if band:
        band.matrix_world = p.matrix_world @ Matrix.Translation((0.235, 0.001, 0))
        d = W.text_obj(name + "_d", "D", 0.034, C["plate_d"], root_coll, "CENTER", "CENTER", 0.001)
        d.matrix_world = (p.matrix_world @ Matrix.Translation((0.235, 0.0085, -0.024)) @ Matrix.Rotation(math.pi, 4, "Z")
                          @ Matrix.Rotation(math.radians(90), 4, "X"))
        d.parent = parent
        d.matrix_parent_inverse = parent.matrix_world.inverted()
    t = W.text_obj(name + "_txt", text, 0.075, C["plate_txt"], root_coll, "CENTER", "CENTER", 0.001)
    t.matrix_world = (p.matrix_world @ Matrix.Translation((-0.02, 0.0065, 0)) @ Matrix.Rotation(math.pi, 4, "Z")
                      @ Matrix.Rotation(math.radians(90), 4, "X"))
    t.parent = parent
    t.matrix_parent_inverse = parent.matrix_world.inverted()


def plate_on(root, g, centre, normal, text, C, name="plate"):
    """German plate (plate_text) on a flat part of a box-built vehicle: a temporary backing quad at `centre` facing
    `normal` gives the ray cast something to hit, then goes away."""
    n = Vector(normal).normalized()
    u = Vector((0, 0, 1)).cross(n).normalized()
    c0 = Vector(centre)
    vs = [c0 + u * a + Vector((0, 0, b)) for a, b in ((-0.4, -0.15), (0.4, -0.15), (0.4, 0.15), (-0.4, 0.15))]
    me = bpy.data.meshes.new("plate_backing")
    me.from_pydata([tuple(v) for v in vs], [], [(0, 1, 2, 3)])
    tmp = bpy.data.objects.new("plate_backing", me)
    root.objects.link(tmp)
    plate_text(root, g, tmp, tuple(c0 + n * 1.0), tuple(-n), text, C, name)
    bpy.data.objects.remove(tmp)
    bpy.data.meshes.remove(me)


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
    cage = me.copy()
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
    smooth_normals(body, cage)
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
            rim(root, g, x + sx * 0.118, ay, r, r * 0.64, sx)
    # lights, grille, plates, mirrors (ray cast onto the baked body)
    front_z = k["stations"][-2][3] - 0.08
    rear_z = k["stations"][1][3] - 0.02
    # lamp units are flat plates on the flat front and rear faces (lamp_units); grille and trim are moulded (conform)
    seam_m = mat("car_seam", (0.006, 0.006, 0.007), 0.6)
    chrome = mat("car_chrome", (0.8, 0.8, 0.82), 0.15, metal=1.0)
    lamp_units(root, g, body, k, C)
    for sx in (-1, 1):
        mz = zbelt + 0.12
        cab = [i for i, s in enumerate(k["stations"]) if s[7] - s[3] > 0.25]
        my = k["stations"][cab[-1] + 1][0] - 0.3
        stick(root, g, body, (sx * (Wh + 1.0), my, mz), (-sx, 0, 0), (0.1, 0.17, 0.12), body_m, name="mirror",
              bevel=0.03, embed=0.02)
    # front of an ordinary small car: slim upper grille between the headlights, a wider lower intake in the bumper,
    # the bumper line running from wheel arch to wheel arch under the headlights (no badge anywhere)
    conform(root, g, body, (0, L + 1.0, front_z - 0.03), (0, -1, 0), None, C["plastic"], 0.0015, name="grille",
            shape=rpoly([(-0.3, -0.045), (0.3, -0.045), (0.34, 0.035), (-0.34, 0.035)], 0.03))
    conform(root, g, body, (0, L + 1.0, front_z - 0.25), (0, -1, 0), None, C["plastic"], 0.0015, name="intake",
            shape=rpoly([(-0.44, -0.06), (0.44, -0.06), (0.37, 0.06), (-0.37, 0.06)], 0.04))
    yb = k["axles"][1] + r + 0.12
    zb_ = front_z - 0.115
    ang = [math.radians(a_ * 0.5) for a_ in range(-180, 181, 3)]
    seam(root, g, body, [((0, yb, zb_), (math.sin(a_), math.cos(a_), 0)) for a_ in ang], seam_m, name="bumper_line")
    plate_text(root, g, body, (0, L + 1.0, front_z - 0.32), (0, -1, 0), plate_txt, C, "plate_f")
    plate_text(root, g, body, (0, -1.0, rear_z - 0.22), (0, 1, 0), plate_txt, C, "plate_r")
    # door gaps and handles (cars with side glass in two spans: four doors), tailgate shut line
    gl = [(k["stations"][i][0], k["stations"][i + 1][0]) for i, t_ in enumerate(k["spans"]) if t_ == "g"]
    zs_ = k["stations"][len(k["stations"]) // 2][2]
    if len(gl) >= 2 and kind != "van":
        y_a = min(gl[-1][1] + 0.45, k["axles"][1] - r - 0.1)
        y_b = (gl[-2][1] + gl[-1][0]) / 2
        y_c = max(gl[-2][0] + 0.2, k["axles"][0] + r + 0.12)
        for sx in (-1, 1):
            for y_ in (y_a, y_b, y_c):
                zz = [zs_ - 0.06 + (zbelt - zs_ + 0.04) * i_ / 7 for i_ in range(8)]
                seam(root, g, body, [((sx * (Wh + 1.0), y_, z_), (-sx, 0, 0)) for z_ in zz], seam_m,
                     name="door_gap")
            for y_ in (y_b, y_c):
                conform(root, g, body, (sx * (Wh + 1.0), y_ + 0.16, zbelt - 0.08), (-sx, 0, 0), (0.13, 0.028),
                        C["plastic"], 0.002, corner=0.5, side=sx, name="handle", rings=2)
    # third brake light, rear wiper, reflectors, exhausts
    rg = [s_ for s_ in k["stations"][:4] if s_[7] - s_[3] > 0.25]
    if rg and kind != "saloon":
        zt = rg[0][7] - 0.06
        fr = face_frame(body, (0, -1.0, zt), (0, 1, 0), 0.3, 0.03)       # a flat strip on the top of the glass
        b3 = fr and plate(root, g, body, fr, [rrect(0.3, 0.03, 0.012)], C["tail"], -0.0015, LIFT_LENS, 0.0008,
                          name="brake3", bend=True)
        if b3:
            b3["dl_no_tail"] = 1.0
        stick(root, g, body, (0.12, -1.0, zt - 0.32), (0, 1, 0), (0.42, 0.015, 0.02), C["plastic"], name="wiper",
              bevel=0.0, embed=0.002)
    for sx in (-1, 1):
        # rear reflectors: small flat plates on the bumper's rear face, well inside its corners
        fr = face_frame(body, (sx * Wh * 0.5, -1.0, k["stations"][0][2] - 0.045), (0, 1, 0), 0.11, 0.026, sx)
        if fr:
            rf = plate(root, g, body, fr, [rrect(0.11, 0.026, 0.011)], C["tail"], _skirt(fr), LIFT_LENS, name="reflector")
            rf["dl_no_tail"] = rf["dl_no_brake"] = 1.0
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
        police_livery(root, g, body, k, L, Wh, C)
    # put the origin at the middle of the car
    for o in root.objects:
        if o.parent is g:
            o.location.y -= L / 2
    lamp_spots(root, body, kind)
    indicator_lenses(root, g, body)
    _TREES.clear()
    return root


def indicator_lenses(root, g, body):
    """Tag the amber indicator sections of the lamp units (lamp_units: front in the headlight unit, rear in the rear
    cluster, side repeater on the front wing) with their dl_lamps record index (object property dl_lamp). They are
    objects "indicator" with material dl_ind_L / dl_ind_R, unlit on a parked car (the instance has no ind_l / ind_r);
    motion.rig moves them into the per-vehicle lamp instances that blink."""
    for o in root.objects:
        if "dl_spot" in o:
            o["dl_lamp"] = int(o["dl_spot"])


# ------------------------------------------------------------------ lamp units: flat plates on the flat faces
DEBUG = bool(__import__("os").environ.get("DL_LAMP_DEBUG"))
LIFT_HOUSING = 0.0010      # housing top above the face plane (m); the plane already clears every body point under it
LIFT_LENS = 0.0014         # lens sections
LIFT_INNER = 0.0018        # the white inner shape of the headlight, over the clear lens


def _tangent(n, side=0):
    """Horizontal u (outwards for side -1/+1 on a front or rear face, forwards on a side face) and v up the face."""
    u = Vector((0, 0, 1)).cross(n)
    if u.length < 0.2:
        u = Vector((1, 0, 0)) if abs(n.x) < 0.9 else Vector((0, 1, 0))
    u.normalize()
    if side and abs(u.x) > 0.5 and u.x * side < 0:
        u = -u
    if side and abs(u.x) <= 0.5 and u.y < 0:
        u = -u
    return u, n.cross(u).normalized()


def _inside(P, p):
    return all((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-9 for a, b in zip(P, P[1:] + P[:1]))


def face_frame(body, origin, direction, w, h, side=0, grid=(13, 7), outline=None):
    """Local plane of the flat body face under a w x h rectangle: ray cast from origin along direction onto the body,
    then a grid of rays over the rectangle and a least-squares plane through the hits (twice, the second time on the
    fitted plane), moved out to the highest hit so no body point under the rectangle stands above it. Returns
    (centre, u, v, n, spread) in body coordinates (u horizontal, outwards for side -1/+1 on a front or rear face; v up
    the face; n out of the body; spread = how far the body under the rectangle falls away from the plane) or None.
    outline: a convex counter-clockwise [(u, v)] inside the rectangle; only the body under it counts."""
    import numpy as np
    bmw = _mw(body)
    inv = bmw.inverted()
    hit, loc, nrm, _i = body.ray_cast(inv @ Vector(origin), (inv.to_3x3() @ Vector(direction)).normalized(),
                                      distance=5.0)
    if not hit:
        return None
    tree = _tree(body)
    n = nrm.normalized()
    c = loc.copy()
    for _ in range(2):
        u, v = _tangent(n, side)
        pts = []
        for i in range(grid[0]):
            for j in range(grid[1]):
                du, dv = w * (i / (grid[0] - 1) - 0.5), h * (j / (grid[1] - 1) - 0.5)
                if outline and not _inside(outline, (du * 0.999, dv * 0.999)):
                    continue
                p = c + u * du + v * dv
                q, _fn, _fi, _d = tree.ray_cast(p + n * 0.15, -n, 0.3)
                if q is not None:
                    pts.append(q)
        if len(pts) < 6:
            return None
        P = np.array([tuple(q) for q in pts])
        m0 = P.mean(0)
        nn = Vector(np.linalg.svd(P - m0)[2][2])
        n = nn if nn.dot(n) > 0 else -nn
        d = [(q - Vector(m0)).dot(n) for q in pts]
        c = c - n * (c - Vector(m0)).dot(n)
    u, v = _tangent(n, side)
    if DEBUG:
        print("face_frame", tuple(round(x_, 3) for x_ in origin), "w %.3f h %.3f spread %.2f mm n %s"
              % (w, h, (max(d) - min(d)) * 1000, tuple(round(x_, 2) for x_ in n)), flush=True)
    return c + n * max(d), u, v, n, max(d) - min(d)


def _skirt(fr):
    """Base of a plate's edge: just under the lowest body point under it (so no gap shows at grazing angles)."""
    return -min(0.0025, fr[4] + 0.0005)


def _dedupe(P, eps=1e-5):
    out = []
    for p in P:
        if not out or (p - out[-1]).length > eps:
            out.append(p)
    while len(out) > 2 and (out[0] - out[-1]).length <= eps:
        out.pop()
    return out


def _inset(P, d):
    """Convex counter-clockwise outline moved inwards by d."""
    out = []
    m = len(P)
    for i in range(m):
        a, b, c = P[i - 1], P[i], P[(i + 1) % m]
        e0, e1 = (b - a).normalized(), (c - b).normalized()
        n0, n1 = Vector((-e0.y, e0.x)), Vector((-e1.y, e1.x))
        bis = n0 + n1
        bis = bis.normalized() if bis.length > 1e-6 else n0
        out.append(b + bis * (d / max(0.35, bis.dot(n0))))
    return out


def clip(P, u0, u1, v0=-9.0, v1=9.0):
    """Convex outline [(u, v)] clipped to the box u0..u1, v0..v1 (Sutherland-Hodgman), counter-clockwise."""
    P = [Vector(p) for p in P]
    for ax, lim, keep_lo in ((0, u0, True), (0, u1, False), (1, v0, True), (1, v1, False)):
        inside = (lambda p: p[ax] >= lim) if keep_lo else (lambda p: p[ax] <= lim)  # noqa: E731
        out = []
        for i in range(len(P)):
            p, q = P[i - 1], P[i]
            if inside(q):
                if not inside(p):
                    out.append(p + (q - p) * ((lim - p[ax]) / (q[ax] - p[ax])))
                out.append(q)
            elif inside(p):
                out.append(p + (q - p) * ((lim - p[ax]) / (q[ax] - p[ax])))
        P = out
    return [(p.x, p.y) for p in _dedupe(P)]


def ellipse(w, h, n=24, c=(0.0, 0.0)):
    return [(c[0] + w / 2 * math.cos(2 * math.pi * i / n), c[1] + h / 2 * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def plate(root_coll, parent, body, fr, outlines, m, z0, z1, bevel=0.0012, name="lamp", bend=False):
    """A flat lens or housing on a face frame fr (face_frame): each convex counter-clockwise outline [(u, v)] (metres,
    from the frame centre) becomes a slab from z0 to z1 along the face normal (metres above the fitted plane), its
    top inset by `bevel` (a small chamfer), flat shaded, so the outline stays crisp. One object for all outlines, its
    origin at their centre on the top face (headlight spot lamps and weather read it). bend=True: a long thin strip
    (the third brake light) follows the body along u (each cross-section stays flat), for a crowned surface."""
    c, u, v, n = fr[:4]
    tree = _tree(body)

    def lift(p):
        if not bend:
            return 0.0
        q, _fn, _fi, _d = tree.ray_cast(c + u * p.x + n * 0.15, -n, 0.3)
        return 0.0 if q is None else (q - c).dot(n)
    Ps = [_dedupe([Vector(p) for p in P]) for P in outlines]
    allp = [p for P in Ps for p in P]
    m2 = sum(allp, Vector((0.0, 0.0))) / len(allp)
    cen = c + u * m2.x + v * m2.y + n * z1
    bm = bmesh.new()
    for P in Ps:
        if bend:                          # points every centimetre along the long edges, so they can follow the body
            P = [a.lerp(b, t / k_) for a, b in zip(P, P[1:] + P[:1])
                 for k_ in [max(1, int((b - a).length / 0.01))] for t in range(k_)]
        T = _inset(P, bevel) if bevel else P
        lo = [bm.verts.new(c + u * p.x + v * p.y + n * (z0 + lift(p)) - cen) for p in P]
        hi = [bm.verts.new(c + u * p.x + v * p.y + n * (z1 + lift(p)) - cen) for p in T]
        for i in range(len(P)):
            i2 = (i + 1) % len(P)
            bm.faces.new((lo[i], lo[i2], hi[i2], hi[i]))
        f_ = bm.faces.new(hi)
        if bend:
            bmesh.ops.triangulate(bm, faces=[f_], quad_method="BEAUTY", ngon_method="BEAUTY")
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    root_coll.objects.link(o)
    o.parent = parent
    o.matrix_basis = _mw(parent).inverted() @ _mw(body) @ Matrix.Translation(cen)
    return o


def lamp_units(root, g, body, k, C):
    """Lamp units as on a production car, each a flat plate on a flat face (never wrapping a corner):
    - a headlight unit per side on the front face: dark housing rim, clear lens with two white reflector discs
      (object "headlight", car_head), amber indicator section at the outer end ("indicator");
    - a rear cluster per side on the rear face: dark housing rim, red tail and brake section on the outer side
      ("taillight", car_tail), amber indicator ("indicator") over a small white reversing section ("tl_reverse");
    - a small amber oval side repeater on each front wing ("indicator").
    The indicator sections carry dl_spot = their dl_lamps record (per side: front, rear, side repeater; left first).
    Returns the number of indicator sections."""
    L, Wh, st = k["L"], k["W"], k["stations"]
    ml, mr = lamp_mats()
    clear = mat("car_lens_clear", (0.78, 0.78, 0.8), 0.2)
    rev = mat("car_lens_reverse", (0.86, 0.86, 0.87), 0.12)
    rim = 0.007
    gap = 0.003
    n = 0
    # front face: the flat panel of the nose between the grille and the rounding of the corner
    wf = st[-1][4] * Wh
    zf = st[-2][3] - 0.08
    hw, hh = min(HEAD_W, HEAD_OUT * wf - HEAD_IN), 0.11
    hx = HEAD_IN + hw / 2
    zf = min(zf + HEAD_DZ, st[-1][3] - 0.01 - hh / 2)       # top just under the nose's beltline (still flat)
    hshape = rpoly([(-hw / 2, -hh / 2), (hw / 2, -hh / 2), (hw / 2, hh / 2 - HEAD_CUT[1]),
                    (hw / 2 - HEAD_CUT[0], hh / 2), (-hw / 2, hh / 2)], 0.022)
    # rear face: the flat panel between the bumper and the tailgate glass
    wr = st[0][4] * Wh
    tw, th = TAIL_W * wr, 0.14
    tx = TAIL_OUT * wr - tw / 2
    tz = st[0][3] + 0.01 - th / 2
    for side in (-1, 1):
        mi = ml if side < 0 else mr
        # headlight unit
        fr = face_frame(body, (side * hx, L + 1.0, zf), (0, -1, 0), hw, hh, side, outline=hshape)
        if fr:
            plate(root, g, body, fr, [hshape], C["plastic"], _skirt(fr), LIFT_HOUSING, name="hl_housing")
            iw, ih = hw - 2 * rim, hh - 2 * rim
            inner = [tuple(p) for p in _inset(_dedupe([Vector(p) for p in hshape]), rim)]
            ua = iw / 2 - 0.2 * iw
            plate(root, g, body, fr, [clip(inner, -iw / 2, ua - gap / 2)], clear, LIFT_HOUSING, LIFT_LENS, 0.0008,
                  name="hl_lens")
            dc = ih * 0.62
            cw = ua - gap / 2 + iw / 2
            plate(root, g, body, fr, [ellipse(dc, dc, 24, (-iw / 2 + cw * f_, 0.0)) for f_ in (0.3, 0.72)],
                  C["head"], LIFT_LENS, LIFT_INNER, 0.0008, name="headlight")
            o = plate(root, g, body, fr, [clip(inner, ua + gap / 2, iw / 2)], mi, LIFT_HOUSING, LIFT_LENS, 0.0008,
                      name="indicator")
            o["dl_spot"] = n
        n += 1
        # rear cluster
        fr = face_frame(body, (side * tx, -1.0, tz), (0, 1, 0), tw, th, side)
        if fr:
            plate(root, g, body, fr, [rrect(tw, th, 0.022)], C["plastic"], _skirt(fr), LIFT_HOUSING, name="tl_housing")
            iw, ih = tw - 2 * rim, th - 2 * rim
            inner = rrect(iw, ih, 0.022 - rim)
            ua = -iw / 2 + 0.4 * iw
            vb = -ih / 2 + 0.4 * ih
            plate(root, g, body, fr, [clip(inner, ua + gap / 2, iw / 2)], C["tail"], LIFT_HOUSING, LIFT_LENS, 0.0008,
                  name="taillight")
            o = plate(root, g, body, fr, [clip(inner, -iw / 2, ua - gap / 2, vb + gap / 2)], mi, LIFT_HOUSING,
                      LIFT_LENS, 0.0008, name="indicator")
            o["dl_spot"] = n
            plate(root, g, body, fr, [clip(inner, -iw / 2, ua - gap / 2, -9.0, vb - gap / 2)], rev, LIFT_HOUSING,
                  LIFT_LENS, 0.0008, name="tl_reverse")
        n += 1
        # side repeater: a small amber oval on the front wing, above the rear of the wheel arch
        ya = k["axles"][1] - 0.2
        za = 2 * k["r"] + 0.1
        fr = face_frame(body, (side * (Wh + 1.0), ya, za), (-side, 0, 0), 0.07, 0.026, side)
        if fr:
            o = plate(root, g, body, fr, [ellipse(0.07, 0.026)], mi, _skirt(fr), LIFT_LENS, 0.0008, name="indicator")
            o["dl_spot"] = n
        n += 1
    return n


HEAD_IN = 0.352    # headlight unit inner edge (m from the centre line; the grille ends at 0.34)
HEAD_W = 0.26      # headlight unit width at most (m)
HEAD_OUT = 0.86    # its outer edge at most this far out (fraction of the front face half width)
HEAD_CUT = (0.05, 0.04)   # outer top corner cut back along the wing line (u, v in m): the nose rounds off there
HEAD_DZ = -0.012   # headlight centre relative to the old spot (m)
TAIL_W = 0.45      # rear cluster width, fraction of the rear face half width
TAIL_OUT = 0.86    # its outer edge (fraction of the rear face half width)


def police_livery(root, g, body, k, L, Wh, C):
    """Generic German police estate: silver body, blue lower doors (the band in body_mesh), a thin blue stripe along
    the beltline, plain POLIZEI (u_DIN, white on blue on the sides, blue on the bonnet and the tailgate), a roof bar
    with two blue domes on a white base (dark until a track sets "beacon"; motion.bake flashes them per car), no
    crest, no maker's badge."""
    blue = mat("police_blue", (0.0, 0.03, 0.22), 0.3, coat=1.0)
    white = mat("police_text", (0.95, 0.95, 0.95), 0.3)
    base = mat("police_bar_base", (0.85, 0.86, 0.88), 0.35)
    dome_a, dome_b = beacon_mats()
    roof_z = max(s_[7] for s_ in k["stations"])
    ym = (k["axles"][0] + k["axles"][1]) / 2
    hit, loc, nrm, _i = body.ray_cast(Vector((0, ym - 0.35, roof_z + 1.0)), Vector((0, 0, -1)))
    if hit:
        def part(name, dx, sz, m_, bev):
            bpy.ops.mesh.primitive_cube_add(location=(dx, loc.y, loc.z + 0.04 + sz[2] / 2))
            o = W.link(bpy.context.active_object, root)
            o.name = name
            o.scale = (sz[0] / 2, sz[1] / 2, sz[2] / 2)
            bpy.ops.object.transform_apply(scale=True)
            b = o.modifiers.new("b", "BEVEL")
            b.width, b.segments = bev, 3
            o.data.materials.append(m_)
            o.parent = g
        part("lightbar", 0.0, (1.18, 0.3, 0.07), base, 0.025)
        part("beacon_l", -0.38, (0.36, 0.24, 0.13), dome_a, 0.05)
        part("beacon_r", 0.38, (0.36, 0.24, 0.13), dome_b, 0.05)
        part("lightbar_mid", 0.0, (0.34, 0.22, 0.09), C["plastic"], 0.02)
    zbelt = k["stations"][len(k["stations"]) // 2][3]
    for sx in (-1, 1):
        hit, loc, nrm, _i = body.ray_cast(Vector((sx * 2.0, ym, 0.68)), Vector((-sx, 0, 0)))
        if hit:
            t = W.text_obj("polizei", "POLIZEI", 0.2, white, root, "CENTER", "CENTER", 0.002)
            t.rotation_euler = (math.radians(90), 0, math.radians(90 if sx > 0 else -90))
            t.location = loc + nrm * 0.006
            t.parent = g
        # beltline stripe from the headlights to the tail lights
        y0, y1 = k["axles"][0] - 0.75, k["axles"][1] + 0.55
        n = 12
        for j in range(n):
            y = y0 + (y1 - y0) * (j + 0.5) / n
            stick(root, g, body, (sx * (Wh + 1.0), y, zbelt - 0.06), (-sx, 0, 0), ((y1 - y0) / n + 0.01, 0.01, 0.06),
                  blue, name="police_stripe", bevel=0.0, embed=0.004)
    # bonnet (reads from the front) and tailgate
    hood = [s_ for s_ in k["stations"] if s_[7] - s_[3] < 0.25]
    yh = (k["L"] - 0.5) if not hood else (hood[0][0] + k["L"]) / 2
    hit, loc, nrm, _i = body.ray_cast(Vector((0, yh - 0.1, 3.0)), Vector((0, 0, -1)))
    if hit:
        t = W.text_obj("polizei_hood", "POLIZEI", 0.16, blue, root, "CENTER", "CENTER", 0.002)
        t.matrix_world = (Matrix.Translation(loc + nrm * 0.004) @ nrm.to_track_quat("Z", "Y").to_matrix().to_4x4()
                          @ Matrix.Rotation(math.pi, 4, "Z"))
        t.parent = g
    rear_z = k["stations"][1][3] + 0.12
    hit, loc, nrm, _i = body.ray_cast(Vector((0, -1.0, rear_z)), Vector((0, 1, 0)))
    if hit:
        t = W.text_obj("polizei_rear", "POLIZEI", 0.12, blue, root, "CENTER", "CENTER", 0.002)
        t.matrix_world = Matrix.Translation(loc + nrm * 0.004) @ Matrix.Rotation(math.radians(90), 4, "X")
        t.parent = g


def beacon_mats():
    """Blue beacon domes, phase A and B: plain blue plastic until the instance properties beacon_a / beacon_b are
    keyed (motion.bake with "beacon": True in the track)."""
    return (lamp("police_beacon_a", (0.03, 0.12, 0.7), 0.15, (0.05, 0.25, 1.0), 0.15, [("beacon_a", 18.0)]),
            lamp("police_beacon_b", (0.03, 0.12, 0.7), 0.15, (0.05, 0.25, 1.0), 0.15, [("beacon_b", 18.0)]))


def lamp_spots(root, body, kind):
    """Indicator lens positions (front corner, rear corner, side repeater on each side), ray cast onto the body and
    stored on the collection as root["dl_lamps"] = [x, y, z, size_x, size_y, size_z, side, part, ...] in car
    coordinates, side -1 = left, part 0 (the unit itself; 1 trailer, 2 drawbar dolly for lorries). motion.rig builds the lenses from it (jx.hero places its own at the same spots); nothing is
    added to the car collection itself, so parked cars stay as they were. Also root["dl_heads"]: headlight centres.
    Cars built by car() take the spots from the indicator sections of their lamp units (objects with dl_spot)."""
    k = KINDS[kind]
    L, Wh = k["L"], k["W"]
    zf = k["stations"][-2][3] - 0.02
    zr = k["stations"][1][3] + 0.04
    bw = body.parent.matrix_basis @ body.matrix_parent_inverse @ body.matrix_basis
    inv = bw.inverted()
    spec = []
    secs = sorted((o for o in root.objects if "dl_spot" in o), key=lambda o: int(o["dl_spot"]))
    for o in secs:
        # the indicator sections of the lamp units (lamp_units): centre on the lens, size of its bounding box
        mw = o.parent.matrix_basis @ o.matrix_parent_inverse @ o.matrix_basis
        ps = [mw @ v.co for v in o.data.vertices]
        lo = Vector(map(min, *ps)) if len(ps) > 1 else ps[0]
        hi = Vector(map(max, *ps)) if len(ps) > 1 else ps[0]
        c = mw.translation
        spec += [round(c.x, 5), round(c.y, 5), round(c.z, 5), max(0.01, hi.x - lo.x), max(0.01, hi.y - lo.y),
                 max(0.01, hi.z - lo.z), -1.0 if c.x < 0 else 1.0, 0.0]
    for side in (() if secs else (-1, 1)):
        for (y, z, sz) in ((L / 2 - 0.12, zf, (0.16, 0.08, 0.06)), (-L / 2 + 0.1, zr, (0.14, 0.06, 0.06)),
                           (L * 0.16, k["stations"][len(k["stations"]) // 2][3] + 0.14, (0.1, 0.03, 0.03))):
            origin = Vector((side * (Wh + 1.0), y, z))
            hit, loc, nrm, _i = body.ray_cast(inv @ origin, inv.to_3x3() @ Vector((-side, 0, 0)), distance=5.0)
            if not hit:
                continue
            wl = bw @ loc + Vector((side * 0.01, 0, 0))
            spec += [wl.x, wl.y, wl.z, sz[1], sz[0], sz[2], float(side), 0.0]
    root["dl_lamps"] = spec
    heads = []
    for o in root.objects:
        if o.name.startswith("headlight"):
            heads += list((o.parent.matrix_basis @ o.matrix_parent_inverse @ o.matrix_basis).translation)
    root["dl_heads"] = heads


def truck(name, cab_color, trailer_color, label="", label_color=(0.05, 0.12, 0.4), c=None, reefer=False,
          plate="F TR 401"):
    """Cab-over tractor and 13.6 m semitrailer (40 t artic), 16.45 m overall (EU limit 16.50 m: kingpin to rear
    12.0 m, kingpin to front 4.4 m), German plates front and rear (fictional codes). Front +y. The origin is 0.2 m
    behind the middle, so the rear sits where it always did (episode 1 spaces the jam with it). The trailer
    articulates about the kingpin under motion.bake."""
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

    # tractor: cab 4.84 .. 7.09, floor at 1.15; front 7.2, kingpin 2.8 (4.4 m, legal max 4.5); 16.48 m overall
    F = -0.46
    bx("cab", (0, 6.45 + F, 2.45), (2.49, 2.25, 2.7), cab_m, 0.22, 4)
    bx("cab_roof", (0, 6.3 + F, 3.775), (2.42, 1.95, 0.45), cab_m, 0.2, 4)    # top at 4.00 m, the legal height
    bx("windscreen", (0, 7.565 + F, 2.95), (2.18, 0.04, 1.05), C["glass"], 0.05)
    for sx in (-1, 1):
        bx("side_window", (sx * 1.246, 7.05 + F, 2.95), (0.03, 0.75, 0.8), C["glass"], 0.04)
        bx("mirror_arm", (sx * 1.33, 7.45 + F, 3.0), (0.2, 0.06, 0.06), dark)
        bx("mirror", (sx * 1.45, 7.48 + F, 2.75), (0.08, 0.16, 0.6), dark, 0.03)
        bx("step", (sx * 1.1, 6.9 + F, 0.85), (0.32, 0.6, 0.12), grey, 0.02)
        bx("headlight", (sx * 0.95, 7.59 + F, 1.42), (0.42, 0.04, 0.18), C["head"], 0.03)
        bx("tank", (sx * 0.95, 3.85, 0.95), (0.55, 1.4, 0.6), mat("truck_alu", (0.7, 0.72, 0.74), 0.3, metal=1.0), 0.2)
    bx("grille", (0, 7.585 + F, 1.85), (1.6, 0.04, 0.55), dark, 0.03)
    bx("bumper", (0, 7.55 + F, 1.05), (2.45, 0.2, 0.42), grey, 0.06)
    bx("chassis", (0, 4.3, 0.95), (0.95, 5.6, 0.3), dark)
    plate_on(root, g, (0, 7.651 + F, 1.0), (0, 1, 0), plate, C, "plate_f")
    tractor = set(root.objects)
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
        while y - 0.6 > -9.2:       # last segment ends inside the trailer (it used to hang 0.3 m off the back)
            bx("tape_side", (sx * 1.279, y - 0.3, 1.32), (0.006, 0.6, 0.05), tape_w)
            if k_ % 2 == 0:
                bx("marker", (sx * 1.281, y, 1.05), (0.01, 0.12, 0.06), mat("marker_amber", (1, 0.45, 0.02), 0.2,
                                                                             emit=(1, 0.45, 0.02), estr=1.0))
            y -= 1.6
            k_ += 1
    bx("plate_board", (0, -9.215, 0.85), (0.6, 0.03, 0.2), dark)
    plate_on(root, g, (0, -9.231, 0.85), (0, -1, 0), plate, C, "plate_r")
    if label and LABELS:
        lm = mat(name + "_label", label_color, 0.4)
        for sx in (-1, 1):
            t = W.text_obj("truck_label", label, 0.85, lm, root, "CENTER", "CENTER", 0.003)
            t.rotation_euler = (math.radians(90), 0, math.radians(90 if sx > 0 else -90))
            t.location = (sx * 1.279, tc, 2.75)
            t.parent = g
    # wheels: tractor front 5.9, drive 2.3 (wheelbase 3.6, kingpin 0.5 ahead of the drive axle); trailer -5.1, -6.4,
    # -7.7 (12.0 m from the kingpin to the rear, the legal maximum)
    for y, dual in ((5.9, False), (2.3, True), (-5.1, False), (-6.4, False), (-7.7, False)):
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
            rim(root, g, x + sx * (0.255 if dual else 0.185), y, 0.5, 0.3, sx, "steel")
    for o in root.objects:
        if o.parent is g:
            o.location.y += 0.8  # centre the 16.8 m rig on the origin
            if o not in tractor and not (o.type == "MESH" and o.location.y > 0.8 and o.location.z < 0.6):
                o["dl_part"] = "trailer"    # motion.rig articulates the semitrailer about the kingpin
    lamps = []
    for sx in (-1, 1):
        lamps += [sx * 1.0, 7.935, 1.2, 0.2, 0.04, 0.09, sx, 0, sx * 1.246, 6.55, 1.5, 0.02, 0.16, 0.06, sx, 0,
                  sx * 0.62, -8.43, 1.0, 0.18, 0.04, 0.12, sx, 1, sx * 1.285, 0.8, 1.05, 0.02, 0.14, 0.05, sx, 1]
    root["dl_lamps"] = lamps
    root["dl_heads"] = [-0.95, 7.95, 1.42, 0.95, 7.95, 1.42]
    # kingpin 0.3 m ahead of the drive axle (1.6 m behind the trailer front); the trailer follows it (motion.rig)
    root["dl_units"] = json.dumps([{"part": "trailer", "hitch": 2.8 + 0.8, "axle": -6.4 + 0.8}])
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
    front = [v for i in range(0, len(root["dl_lamps"]), 8) for v in root["dl_lamps"][i:i + 8]
             if root["dl_lamps"][i + 1] > 0]
    keep = [i // 8 for i in range(0, len(root["dl_lamps"]), 8) if root["dl_lamps"][i + 1] > 0]
    for o in list(root.objects):          # moulded lenses follow their records (the rear ones are under the module)
        if "dl_lamp" in o:
            if int(o["dl_lamp"]) in keep:
                o["dl_lamp"] = keep.index(int(o["dl_lamp"]))
            else:
                bpy.data.objects.remove(o)
    for sx in (-1, 1):
        front += [sx * 0.95, y0 - 0.015, 0.95, 0.2, 0.04, 0.1, sx, 0]
    root["dl_lamps"] = front
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
            rim(root, g, sx * 1.215, y, r_, 0.32, sx, "steel")
    plate_on(root, g, (0, 4.501, 1.0), (0, 1, 0), "F FW 112", C, "plate_f")
    plate_on(root, g, (0, -4.551, 0.97), (0, -1, 0), "F FW 112", C, "plate_r")
    lamps = []
    for sx in (-1, 1):
        lamps += [sx * 1.15, 4.43, 1.2, 0.18, 0.04, 0.09, sx, 0, sx * 0.62, -4.58, 0.95, 0.18, 0.04, 0.12, sx, 0]
    root["dl_lamps"] = lamps
    root["dl_heads"] = [-0.9, 4.45, 1.45, 0.9, 4.45, 1.45]
    return root


# ------------------------------------------------------------------ bus and lorry with drawbar trailer
def shell(root, g, spec, body_m, C, band=None, arches=(), name="shell"):
    """Subdivision-cage body from a station spec (as KINDS, W = half width), wheel arches (y, radius, z) cut with
    booleans, baked, smooth, parented to g. Returns the body object (also the ray-cast target for stickers)."""
    me = body_mesh(dict(spec, name=name), body_m, C["glass"], C["plastic"], band)
    cage = me.copy()
    body = bpy.data.objects.new(name + "_body", me)
    root.objects.link(body)
    sub = body.modifiers.new("sub", "SUBSURF")
    sub.levels = sub.render_levels = 2
    cutters = []
    for ay, rr, zc in arches:
        bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=rr, depth=spec["W"] * 2 + 0.4, location=(0, ay, zc),
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
    for p_ in body.data.polygons:
        p_.use_smooth = True
    smooth_normals(body, cage)
    body.parent = g
    return body


def wheel(root, g, x, y, r, depth, sx, style="steel", rim_r=None, name="tyre"):
    """Tyre (bevelled cylinder, axle along x) plus a rim face on its outer side."""
    C = common()
    bpy.ops.mesh.primitive_cylinder_add(vertices=36, radius=r, depth=depth, location=(x, y, r),
                                        rotation=(0, math.pi / 2, 0))
    ty = W.link(bpy.context.active_object, root)
    ty.name = name
    b = ty.modifiers.new("b", "BEVEL")
    b.width, b.segments = min(0.07, depth * 0.25), 3
    ty.data.materials.append(C["tyre"])
    for p_ in ty.data.polygons:
        p_.use_smooth = True
    ty.parent = g
    rm = rim(root, g, x + sx * (depth / 2 + 0.003), y, r, rim_r or r * 0.6, sx, style)
    return ty, rm


def _bx(root, g, name, loc, size, m, bev=0.0, seg=3, part=None):
    o = _box(root, g, name, loc, size, m, bev, seg)
    if part:
        o["dl_part"] = part
    return o


def _shift(root, g, dy):
    for o in root.objects:
        if o.parent is g:
            o.location.y += dy


BUS = dict(L=12.0, W=1.275, r=0.48, axles=(3.4, 9.3), crease=1.6, tuck=0.97, front_glass=True, rear_glass=True,
           stations=[S(0.00, 0.46, 0.62, 1.62, 0.93, 2.86, 0.86, 2.62, 0.91),
                     S(0.07, 0.30, 0.52, 1.18, 0.995, 2.96, 0.935, 2.76, 0.975),
                     S(11.90, 0.30, 0.52, 1.02, 1.00, 2.98, 0.94, 2.78, 0.98),
                     S(12.00, 0.36, 0.56, 0.92, 0.955, 2.90, 0.87, 2.70, 0.925)],
           spans="bgb")


def bus(name="bus", color=(0.86, 0.84, 0.76), band_color=(0.62, 0.06, 0.04), plate="F VB 112",
        dest="12 Marktplatz", c=None):
    """Generic 12 m low-floor city bus: 2.55 m wide, about 3.1 m high with the roof pod, wheelbase 5.9 m, three
    double doors on the right (ahead of the front axle, between the axles, behind the rear axle), floor 0.34 m at the
    doors, LED destination displays, mirrors on arms, rear engine grilles. No maker's marks. Origin at the middle,
    front +y."""
    C = common()
    k = BUS
    L, Wh, r = k["L"], k["W"], k["r"]
    root = bpy.data.collections.new(name)
    (c or bpy.context.scene.collection).children.link(root)
    g = bpy.data.objects.new(name, None)
    root.objects.link(g)
    body_m = mat("bus_paint_" + name, color, 0.32, metal=0.05, coat=1.0)
    band = (0.4, 11.7, mat("bus_band_" + name, band_color, 0.35, coat=1.0))
    body = shell(root, g, k, body_m, C, band, [(ay, r + 0.07, r) for ay in k["axles"]], name)
    dark = mat("bus_frame", (0.02, 0.02, 0.022), 0.45)
    rubber = mat("bus_rubber", (0.015, 0.015, 0.015), 0.7)
    grey = mat("truck_grey", (0.25, 0.26, 0.27), 0.5)
    led = mat("bus_led", (0.15, 0.08, 0.0), 0.4, emit=(1.0, 0.55, 0.05), estr=3.0)
    zbelt, zwin = 1.18, 2.76
    # window pillars (both sides), door frames and glass leaves (right side)
    doors = [(10.0, 11.25), (5.35, 6.6), (1.45, 2.7)]
    for sx in (-1, 1):
        ys = ([0.5, 1.45, 2.7, 3.95, 5.35, 6.6, 7.95, 9.3, 10.0, 11.25] if sx > 0 else
              [0.5, 1.9, 3.3, 4.7, 6.1, 7.5, 8.9, 10.3, 11.25])
        for y in ys:
            stick(root, g, body, (sx * 3.0, y, (zbelt + zwin) / 2), (-sx, 0, 0), (0.09, 0.012, zwin - zbelt + 0.02),
                  dark, name="pillar", bevel=0.0, embed=0.003)
    for y0, y1 in doors:
        yc, wd = (y0 + y1) / 2, y1 - y0
        x = Wh - 0.012                       # doors sit flush in the 2.55 m body
        _bx(root, g, "door_frame", (x, yc, 1.5), (0.03, wd + 0.06, 2.4), dark, 0.01)
        for sgn in (-1, 1):
            _bx(root, g, "door_glass", (x + 0.01, yc + sgn * wd / 4, 1.55), (0.012, wd / 2 - 0.07, 2.12),
                C["glass"], 0.006)
            _bx(root, g, "door_rail", (x + 0.014, yc + sgn * wd / 4, 1.1), (0.008, wd / 2 - 0.12, 0.035), grey)
        _bx(root, g, "door_seal", (x + 0.012, yc, 1.5), (0.014, 0.03, 2.3), rubber)
        _bx(root, g, "door_step", (x - 0.05, yc, 0.33), (0.12, wd, 0.04), grey)
    # roof: air-conditioning pod and two hatches
    _bx(root, g, "roof_ac", (0, 8.3, 3.06), (1.9, 3.4, 0.2), body_m, 0.09, 4)
    _bx(root, g, "roof_ac_grille", (0, 8.3, 3.165), (1.5, 2.6, 0.012), grey)
    for y in (5.2, 2.6):
        _bx(root, g, "roof_hatch", (0, y, 3.0), (0.9, 0.9, 0.06), grey, 0.02)
    # front: destination display over the windscreen, headlights, grille, wipers, mirrors on arms, plate
    _bx(root, g, "dest_panel", (0, L + 0.004, 2.82), (2.0, 0.02, 0.22), dark, 0.01)
    t = W.text_obj("dest_front", dest, 0.15, led, root, "CENTER", "CENTER", 0.001)
    t.rotation_euler = (math.radians(90), 0, math.pi)
    t.location = (0, L + 0.017, 2.82)
    t.parent = g
    # front: dark lower panel with the headlight clusters, black frame around the windscreen
    _bx(root, g, "front_panel", (0, L - 0.012, 0.66), (2.36, 0.04, 0.42), dark, 0.04)
    _bx(root, g, "screen_frame", (0, L - 0.006, 0.93), (2.3, 0.04, 0.07), dark, 0.02)
    for sx in (-1, 1):
        _bx(root, g, "screen_frame_v", (sx * 1.16, L - 0.03, 1.85), (0.07, 0.06, 1.85), dark, 0.02)
        _bx(root, g, "headlight_bezel", (sx * 0.86, L + 0.006, 0.74), (0.56, 0.03, 0.22), C["plastic"], 0.03)
        _bx(root, g, "headlight", (sx * 0.86, L + 0.012, 0.76), (0.48, 0.03, 0.15), C["head"], 0.03)
        _bx(root, g, "drl", (sx * 0.86, L + 0.014, 0.64), (0.42, 0.02, 0.025), C["head"], 0.0)
        _bx(root, g, "mirror_arm", (sx * 1.18, L + 0.2, 2.72), (0.05, 0.45, 0.05), dark, 0.02)
        _bx(root, g, "mirror_arm2", (sx * 1.18, L + 0.41, 2.42), (0.05, 0.05, 0.6), dark, 0.02)
        _bx(root, g, "mirror", (sx * 1.18, L + 0.42, 2.0), (0.2, 0.08, 0.38), dark, 0.03)
        _bx(root, g, "wiper", (sx * 0.45, L + 0.03, 1.02), (0.85, 0.015, 0.025), dark)
    plate_on(root, g, (0, L + 0.012, 0.52), (0, 1, 0), plate, C, "plate_f")
    # side destination display by the front door, side marker lamps
    _bx(root, g, "dest_side", (Wh - 0.006, 8.7, 2.55), (0.02, 1.2, 0.2), dark, 0.01)
    t = W.text_obj("dest_side_txt", dest, 0.12, led, root, "CENTER", "CENTER", 0.001)
    t.rotation_euler = (math.radians(90), 0, math.radians(90))
    t.location = (Wh + 0.0045, 8.7, 2.55)
    t.parent = g
    amber_m = mat("marker_amber", (1, 0.45, 0.02), 0.2, emit=(1, 0.45, 0.02), estr=1.0)
    for sx in (-1, 1):
        for y in (2.0, 6.0, 10.0):
            _bx(root, g, "marker", (sx * (Wh - 0.002), y, 0.42), (0.012, 0.1, 0.05), amber_m)
    # rear: window over the engine bay (glass end cap), line-number display, light clusters, engine grilles, plate
    _bx(root, g, "dest_rear", (0, -0.005, 2.5), (0.7, 0.02, 0.2), dark, 0.01)
    t = W.text_obj("dest_rear_txt", dest.split(" ")[0], 0.15, led, root, "CENTER", "CENTER", 0.001)
    t.rotation_euler = (math.radians(90), 0, 0)
    t.location = (0, -0.017, 2.5)
    t.parent = g
    for sx in (-1, 1):
        for z, h_ in ((1.0, 0.36), (1.42, 0.14)):
            _bx(root, g, "taillight", (sx * 1.06, 0.004, z), (0.22, 0.04, h_), C["tail"], 0.02)
        _bx(root, g, "reverse", (sx * 1.06, 0.004, 0.72), (0.22, 0.04, 0.1), C["head"], 0.02)
    b3 = _bx(root, g, "brake3", (0, 0.004, 2.66), (0.5, 0.03, 0.04), C["tail"], 0.01)
    b3["dl_no_tail"] = 1.0
    for z in (0.8, 0.95, 1.1, 1.25):
        _bx(root, g, "engine_slat", (0, -0.002, z), (1.2, 0.03, 0.05), dark, 0.01)
        _bx(root, g, "engine_slat_side", (-Wh + 0.004, 1.3, z + 0.2), (0.012, 1.4, 0.05), dark, 0.004)
    _bx(root, g, "bumper_r", (0, 0.03, 0.42), (2.4, 0.12, 0.2), C["plastic"], 0.04)
    plate_text(root, g, body, (0, -1.0, 0.68), (0, 1, 0), plate, C, "plate_r")
    # wheels: 275/70 R22.5 (r 0.48), front singles, rear duals
    for ay, dual in ((k["axles"][1], False), (k["axles"][0], True)):
        for sx in (-1, 1):
            if dual:
                wheel(root, g, sx * 0.94, ay, r, 0.56, sx, "steel", 0.29)
            else:
                wheel(root, g, sx * 1.07, ay, r, 0.29, sx, "steel", 0.29)
    _shift(root, g, -L / 2)
    spec = []
    for sx in (-1, 1):
        spec += [sx * 1.0, L / 2 - 0.005, 0.95, 0.28, 0.04, 0.09, sx, 0,
                 sx * (Wh + 0.008), L / 2 - 1.2, 1.0, 0.02, 0.18, 0.06, sx, 0,
                 sx * (Wh + 0.008), -0.3, 0.42, 0.02, 0.14, 0.05, sx, 0,
                 sx * 1.06, -L / 2 - 0.006, 1.22, 0.22, 0.04, 0.1, sx, 0]
    root["dl_lamps"] = spec
    root["dl_heads"] = [-0.86, L / 2 + 0.02, 0.76, 0.86, L / 2 + 0.02, 0.76]
    return root


# cab-over cab of the rigid lorry, stations already at their place (front at y = 0), door windows over the front axle
CAB = dict(L=2.3, W=1.25, r=0.5, axles=(), crease=1.6, tuck=0.96, front_glass=True,
           stations=[S(-2.30, 0.98, 1.28, 2.02, 0.97, 3.22, 0.9, 3.0, 0.94),
                     S(-2.24, 0.95, 1.25, 2.0, 1.00, 3.30, 0.95, 3.06, 0.98),
                     S(-1.95, 0.95, 1.25, 1.98, 1.00, 3.30, 0.95, 3.06, 0.98),
                     S(-0.18, 0.95, 1.22, 1.9, 1.00, 3.28, 0.95, 3.04, 0.98),
                     S(0.00, 0.78, 1.18, 1.86, 0.975, 3.18, 0.90, 2.96, 0.94)],
           spans="bbgb")


def drawbar(name="gliederzug", cab_color=(0.86, 0.87, 0.88), box_color=(0.88, 0.89, 0.9), label="",
            label_color=(0.05, 0.12, 0.4), plate="F GZ 260", trailer_plate="F GZ 261", c=None):
    """Rigid three-axle lorry (cab-over cab, 7.3 m box) with a two-axle drawbar trailer (turntable front axle,
    A-frame drawbar, 7.82 m box): 18.75 m overall, 2.55 m wide, 4.0 m high, ECE 104 contour tape, side and rear
    underrun guards, German plates on the lorry and its own plate on the trailer. Under motion.bake the dolly follows
    the coupling and the trailer follows the turntable. Origin at the middle, front +y."""
    C = common()
    root = bpy.data.collections.new(name)
    (c or bpy.context.scene.collection).children.link(root)
    g = bpy.data.objects.new(name, None)
    root.objects.link(g)
    cab_m = mat(name + "_cab", cab_color, 0.3, metal=0.2, coat=1.0)
    box_m = mat(name + "_box", box_color, 0.45)
    dark = mat("truck_chassis", (0.035, 0.035, 0.035), 0.6)
    grey = mat("truck_grey", (0.25, 0.26, 0.27), 0.5)
    alu = mat("truck_alu", (0.7, 0.72, 0.74), 0.3, metal=1.0)
    tape_r = mat("tape_red", (0.6, 0.02, 0.01), 0.3, emit=(1, 0.05, 0.02), estr=0.15)
    tape_w = mat("tape_white", (0.85, 0.75, 0.2), 0.3, emit=(1, 0.85, 0.2), estr=0.1)
    amber_m = mat("marker_amber", (1, 0.45, 0.02), 0.2, emit=(1, 0.45, 0.02), estr=1.0)
    r = 0.5
    # lorry: front at y = 0, cab 0 .. -2.3, box -2.45 .. -9.75, axles -1.4 (steered), -6.1, -7.45; coupling -10.05
    cab = shell(root, g, CAB, cab_m, C, None, [(-1.4, r + 0.06, r)], name + "_cab")
    for sx in (-1, 1):
        stick(root, g, cab, (sx * 0.9, 1.0, 1.05), (0, -1, 0), (0.4, 0.04, 0.15), C["head"], name="headlight",
              embed=0.02, bevel=0.012)
        stick(root, g, cab, (sx * 0.5, 1.0, 1.95), (0, -1, 0), (0.8, 0.015, 0.025), dark, name="wiper", bevel=0.0,
              embed=0.004)
        _bx(root, g, "mirror_arm", (sx * 1.32, -0.3, 2.85), (0.2, 0.06, 0.06), dark)
        _bx(root, g, "mirror", (sx * 1.44, -0.27, 2.55), (0.08, 0.16, 0.55), dark, 0.03)
        _bx(root, g, "step", (sx * 1.08, -0.9, 0.7), (0.3, 0.55, 0.1), grey, 0.02)
    stick(root, g, cab, (0, 1.0, 1.55), (0, -1, 0), (1.6, 0.04, 0.42), dark, name="grille", embed=0.02, bevel=0.02)
    _bx(root, g, "bumper", (0, -0.12, 0.82), (2.45, 0.2, 0.4), grey, 0.06)
    _bx(root, g, "roof_deflector", (0, -1.2, 3.42), (2.3, 1.6, 0.2), cab_m, 0.08, 4)
    plate_on(root, g, (0, -0.019, 0.82), (0, 1, 0), plate, C, "plate_f")
    _bx(root, g, "chassis", (0, -5.6, 0.92), (0.9, 9.0, 0.28), dark)
    for sx in (-1, 1):
        _bx(root, g, "tank", (sx * 0.95, -3.7, 0.88), (0.5, 1.2, 0.55), alu, 0.18)
        _bx(root, g, "side_guard", (sx * 1.2, -4.6, 0.62), (0.04, 2.6, 0.1), grey)
        _bx(root, g, "side_guard2", (sx * 1.2, -4.6, 0.38), (0.04, 2.6, 0.1), grey)
        _bx(root, g, "mudguard", (sx * 0.96, -6.78, 1.08), (0.56, 2.9, 0.06), dark, 0.02)
    lbox_y0, lbox_y1 = -2.45, -9.75
    _bx(root, g, "box", (0, (lbox_y0 + lbox_y1) / 2, 2.6), (2.55, lbox_y0 - lbox_y1, 2.8), box_m, 0.05)
    _bx(root, g, "box_floor", (0, (lbox_y0 + lbox_y1) / 2, 1.15), (2.52, lbox_y0 - lbox_y1, 0.14), dark)
    _bx(root, g, "underrun", (0, -9.7, 0.55), (2.3, 0.12, 0.14), grey)
    for sx in (-1, 1):
        _bx(root, g, "taillight", (sx * 0.95, -9.78, 0.75), (0.36, 0.04, 0.13), C["tail"], 0.02)
    plate_on(root, g, (0, -9.771, 0.92), (0, -1, 0), plate, C, "plate_r")
    _bx(root, g, "coupling", (0, -9.95, 0.72), (0.3, 0.35, 0.25), dark, 0.03)
    # drawbar trailer, box -10.93 .. -18.75; dolly (drawbar, turntable, front axle -12.55) and trailer (axle -17.25)
    tb_y0, tb_y1 = -10.93, -18.68
    ta_front, ta_rear = -12.55, -17.25
    _bx(root, g, "drawbar", (0, (-10.05 + ta_front) / 2, 0.7), (0.12, -10.05 - ta_front, 0.12), dark, part="dolly")
    for sx in (-1, 1):
        o = _bx(root, g, "drawbar_arm", (sx * 0.4, ta_front + 0.75, 0.72), (0.1, 1.7, 0.1), dark, part="dolly")
        piv = Vector((sx * 0.4, ta_front + 0.75, 0.72))      # _box applies the location to the mesh
        o.matrix_basis = Matrix.Translation(piv) @ Matrix.Rotation(-sx * 0.45, 4, "Z") @ Matrix.Translation(-piv)
    _bx(root, g, "turntable", (0, ta_front, 1.02), (2.0, 1.6, 0.14), dark, 0.05, part="dolly")
    _bx(root, g, "dolly_guard", (0, ta_front - 0.7, 0.6), (2.2, 0.08, 0.12), grey, part="dolly")
    _bx(root, g, "tbox", (0, (tb_y0 + tb_y1) / 2, 2.6), (2.55, tb_y0 - tb_y1, 2.8), box_m, 0.05, part="trailer")
    _bx(root, g, "tbox_floor", (0, (tb_y0 + tb_y1) / 2, 1.15), (2.52, tb_y0 - tb_y1, 0.14), dark, part="trailer")
    _bx(root, g, "tchassis", (0, -15.6, 0.98), (0.9, 5.4, 0.22), dark, part="trailer")
    _bx(root, g, "tunderrun", (0, -18.48, 0.55), (2.3, 0.12, 0.14), grey, part="trailer")
    for sx in (-1, 1):
        _bx(root, g, "tmudguard", (sx * 0.97, ta_rear, 1.08), (0.5, 1.3, 0.06), dark, 0.02, part="trailer")
        _bx(root, g, "tside_guard", (sx * 1.2, -14.9, 0.62), (0.04, 3.4, 0.1), grey, part="trailer")
        _bx(root, g, "taillight", (sx * 0.95, -18.70, 0.98), (0.38, 0.04, 0.14), C["tail"], 0.02, part="trailer")
    _bx(root, g, "plate_board", (0, -18.695, 0.85), (0.6, 0.03, 0.2), dark, part="trailer")
    before = set(root.objects)
    plate_on(root, g, (0, -18.711, 0.85), (0, -1, 0), trailer_plate, C, "plate_t")
    for o in set(root.objects) - before:
        o["dl_part"] = "trailer"
    # boxes: rear doors on both, contour tape (red at the rear, yellow on the sides), side markers, labels
    for (y0, y1), part in (((lbox_y0, lbox_y1), None), ((tb_y0, tb_y1), "trailer")):
        yc, ly = (y0 + y1) / 2, y0 - y1
        _bx(root, g, "door_seam", (0, y1 - 0.005, 2.6), (0.02, 0.01, 2.6), dark, part=part)
        for x in (-0.95, -0.35, 0.35, 0.95):
            _bx(root, g, "lock_bar", (x, y1 - 0.025, 2.6), (0.04, 0.04, 2.55), grey, part=part)
        for z in (1.3, 3.93):
            _bx(root, g, "tape_rear", (0, y1 - 0.015, z), (2.45, 0.006, 0.05), tape_r, part=part)
        for x in (-1.21, 1.21):
            _bx(root, g, "tape_rear_v", (x, y1 - 0.015, 2.6), (0.05, 0.006, 2.6), tape_r, part=part)
        for sx in (-1, 1):
            _bx(root, g, "tape_side", (sx * 1.279, yc, 1.32), (0.006, ly - 0.3, 0.05), tape_w, part=part)
            _bx(root, g, "tape_top", (sx * 1.279, yc, 3.93), (0.006, ly - 0.3, 0.05), tape_w, part=part)
            for kk in range(4):
                _bx(root, g, "marker", (sx * 1.281, y0 - 0.6 - kk * (ly - 1.2) / 3, 1.05), (0.01, 0.12, 0.06),
                    amber_m, part=part)
        if label and LABELS:
            lm = mat(name + "_label", label_color, 0.4)
            for sx in (-1, 1):
                t = W.text_obj("truck_label", label, 0.62, lm, root, "CENTER", "CENTER", 0.003)
                t.rotation_euler = (math.radians(90), 0, math.radians(90 if sx > 0 else -90))
                t.location = (sx * 1.279, yc, 2.75)
                t.parent = g
                if part:
                    t["dl_part"] = part
    # wheels: 315/70 R22.5 (r 0.5); lorry front single, two dual rear axles; trailer singles
    for y, dual, part in ((-1.4, False, None), (-6.1, True, None), (-7.45, True, None), (ta_front, False, "dolly"),
                          (ta_rear, False, "trailer")):
        for sx in (-1, 1):
            ty, rm = wheel(root, g, sx * (0.96 if dual else 1.02), y, r, 0.5 if dual else 0.36, sx, "steel", 0.3)
            if part:
                ty["dl_part"] = rm["dl_part"] = part
    D = 18.72 / 2
    _shift(root, g, D)
    root["dl_units"] = json.dumps([{"part": "dolly", "parent": "main", "hitch": -10.05 + D, "axle": ta_front + D},
                                   {"part": "trailer", "parent": "dolly", "hitch": ta_front + D, "axle": ta_rear + D}])
    spec = []
    for sx in (-1, 1):
        spec += [sx * 1.12, D + 0.006, 1.0, 0.2, 0.04, 0.09, sx, 0,
                 sx * 1.255, D - 1.9, 1.35, 0.02, 0.16, 0.06, sx, 0,
                 sx * 0.55, -9.8 + D, 0.75, 0.16, 0.04, 0.12, sx, 0,
                 sx * 0.55, -18.72 + D, 0.98, 0.18, 0.04, 0.12, sx, 1]
    root["dl_lamps"] = spec
    root["dl_heads"] = [-0.92, D, 1.0, 0.92, D, 1.0]
    return root


# ------------------------------------------------------------------ every kind by name
ALL_KINDS = ("hatch", "estate", "saloon", "suv", "van", "police", "artic", "bus", "drawbar")


def make(kind, name=None, color=(0.5, 0.5, 0.52), plate="F LK 202", c=None, **kw):
    """Any vehicle kind by name (ALL_KINDS). Returns its collection (origin at the middle, front +y)."""
    name = name or kind
    if kind in KINDS:
        return car(kind, color, name, plate, c=c, **kw)
    if kind == "police":
        return car("estate", None, name, plate, police=True, c=c)
    if kind == "artic":
        return truck(name, color, kw.pop("trailer_color", (0.86, 0.87, 0.88)), kw.pop("label", ""), c=c, plate=plate,
                     **kw)
    if kind == "bus":
        return bus(name, color, plate=plate, c=c, **kw)
    if kind == "drawbar":
        return drawbar(name, color, plate=plate, c=c, **kw)
    raise KeyError(kind)
