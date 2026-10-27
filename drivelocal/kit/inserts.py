"""Lit insert props for the Track B Shorts (owner rule 27 Oct 2026: no flat primitive scenes): a phone with a readable,
unbranded UI (real text and icons, no grey bars) in a dashboard mount inside a jx.hero car or lying on a counter, a
room (walls, floor, window light), a typeset letter with a window envelope on a table, a wall calendar with real day
numbers, a fuel-station shop counter with a card terminal, and an instrument cluster behind the steering wheel.
No brands, no logos, no traffic signs or sign look-alikes. In-world text is in the country's language (the captions
explain it); every number on it is passed in by the episode from a VERIFIED fact (tests check the episode's NUMBERS).
import inserts as IN
IN.setup(ASSETS)
ph = IN.phone(c, "ph", loc, rot, {"buy": (spans, IN.scr_form(...))}, glow=2.5)
IN.dash_mount(hero, ph)                     # phone into the hero collection, on the dashboard
cam = IN.cabin_cam(hero["obj"], hero)       # cam(t, eye, look) -> world (pos, target) at time t
"""
import math
import os
import random

import bpy
from mathutils import Euler, Matrix, Vector

import country as CY
import jx
import stage
import town as TN
import world as W

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "..", "fonts")
FPS = 30
_F, _M = {}, {}
ASSETS = "assets"

INK = (0.04, 0.045, 0.05)
GREY_T = (0.38, 0.4, 0.43)
GREEN = (0.08, 0.62, 0.3)
AMBER = (1.0, 0.62, 0.05)
RED = (0.82, 0.08, 0.06)
TEAL = (0.0, 0.3, 0.38)


def setup(assets):
    global ASSETS
    ASSETS = assets


def font(kind="din"):
    if kind not in _F:
        if kind == "din":
            f = W.SIGN_FONT or bpy.data.fonts.load(os.path.join(ASSETS, "fonts", "udin", "uDIN1451Mittelschrift.ttf"),
                                                   check_existing=True)
        else:
            f = bpy.data.fonts.load(os.path.join(FONTS, {"bold": "Montserrat-ExtraBold.ttf",
                                                         "black": "Montserrat-Black.ttf"}[kind]), check_existing=True)
        _F[kind] = f
    return _F[kind]


def _mat(color, emit=None, rough=0.55):
    key = (tuple(round(v, 3) for v in color), emit, rough)
    if key not in _M:
        _M[key] = jx.flat_mat("ui_%d" % len(_M), color, emit) if emit else W.principled("ink_%d" % len(_M), color,
                                                                                        rough)
    return _M[key]


def text(c, body, size, color, loc, parent=None, align="LEFT", kind="din", emit=None, rot=(0, 0, 0), name="txt"):
    """Text lying in the parent's xy plane (facing +z). emit: emissive (screens), else ink on paper."""
    o = W.text_obj(name, body, size, _mat(color, emit), c, align=align, valign="CENTER", font=font(kind))
    o.location, o.rotation_euler = loc, rot
    if parent:
        o.parent = parent
    return o


def rrect(c, p, x0, y0, x1, y1, color, emit, z, r=0.0025, name="rr"):
    pts = [(x + (x0 + x1) / 2, y + (y0 + y1) / 2) for x, y in W.rounded_rect(x1 - x0, y1 - y0, min(r, (y1 - y0) / 2.01,
                                                                                                     (x1 - x0) / 2.01), 4)]
    return CY.flat(c, name, pts, color, emit, rot=(0, 0, 0), parent=p, z=z)


def tick(c, p, x, y, r, z, emit, color=GREEN, name="tk"):
    g = CY.bpy_empty(c, name, p)
    CY.flat(c, name + "_d", CY.disc_pts(r, 40, x, y), color, emit, rot=(0, 0, 0), parent=g, z=z)
    for a, b in (((x - 0.5 * r, y), (x - 0.12 * r, y - 0.38 * r)), ((x - 0.12 * r, y - 0.38 * r), (x + 0.52 * r,
                                                                                                    y + 0.4 * r))):
        CY.flat(c, name + "_v", CY.bar_pts(a[0], a[1], b[0], b[1], 0.19 * r), (1, 1, 1), emit * 1.3, rot=(0, 0, 0),
                parent=g, z=z + 0.0002)
    return g


def lock(c, p, x, y, s, z, emit, color=GREY_T, name="lk"):
    """Padlock icon: shackle (three bars) over a rounded body."""
    g = CY.bpy_empty(c, name, p)
    rrect(c, g, x - 0.5 * s, y - 0.55 * s, x + 0.5 * s, y + 0.15 * s, color, emit, z, r=0.12 * s, name=name + "_b")
    w = 0.13 * s
    for a, b in (((x - 0.32 * s, y + 0.1 * s), (x - 0.32 * s, y + 0.42 * s)),
                 ((x + 0.32 * s, y + 0.1 * s), (x + 0.32 * s, y + 0.42 * s)),
                 ((x - 0.38 * s, y + 0.5 * s), (x + 0.38 * s, y + 0.5 * s))):
        CY.flat(c, name + "_s", CY.bar_pts(a[0], a[1], b[0], b[1], w), color, emit, rot=(0, 0, 0), parent=g, z=z)
    CY.flat(c, name + "_h", CY.disc_pts(0.09 * s, 16, x, y - 0.2 * s), (1, 1, 1), emit, rot=(0, 0, 0), parent=g,
            z=z + 0.0002)
    return g


# ------------------------------------------------------------------ phone
SW, SH = 0.068, 0.146


def _prism(c, name, outline, h, mat, z0=0.0, parent=None):
    n = len(outline)
    v = [(x, y, z0) for x, y in outline] + [(x, y, z0 + h) for x, y in outline]
    f = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i)
                                                                  for i in range(n)]
    o = W.mesh_obj(name, v, f, mat, c)
    if parent:
        o.parent = parent
    return o


def phone(c, name, loc, rot, screens, glow=1.6):
    """A modern phone (no brand, no logo): rounded black case, glass bezel, a screen per key shown inside its time
    spans. screens = {key: (spans, builder)}; builder(c, parent, glow) adds UI in screen coordinates (metres, x right,
    y up, screen SW x SH centred on the origin, content at z >= 0.0004). Local +z is the screen normal."""
    g = bpy.data.objects.new(name, None)
    c.objects.link(g)
    g.location, g.rotation_euler = loc, rot
    body = W.principled(name + "_case", (0.02, 0.02, 0.024), 0.3, metal=0.6, coat=0.8)
    _prism(c, name + "_case", W.rounded_rect(0.0745, 0.1545, 0.009, 6), 0.0078, body, z0=-0.0079, parent=g)
    CY.flat(c, name + "_bezel", W.rounded_rect(0.0725, 0.1525, 0.008, 6), (0.005, 0.005, 0.006), 0.0, rot=(0, 0, 0),
            parent=g, z=0.0)
    for k, (key, (spans_, build)) in enumerate(screens.items()):
        sg = bpy.data.objects.new(f"{name}_{key}", None)
        c.objects.link(sg)
        sg.parent = g
        sg.location.z = 0.00005 * k
        rrect(c, sg, -SW / 2, -SH / 2, SW / 2, SH / 2, (0.96, 0.965, 0.97), glow, 0.0002, r=0.006, name=name + "_bg")
        _status(c, sg, glow)
        build(c, sg, glow)
        CY.show(sg, spans_)
    return g


def _status(c, p, e):
    """Status bar: signal bars and a battery (no clock: no numbers that are not facts)."""
    z = 0.0004
    for k in range(4):
        CY.flat(c, "sb", MW_rect(0.0018, 0.0016 + 0.0009 * k, -0.026 + 0.0026 * k, 0.0675 + 0.00045 * k),
                INK, e, rot=(0, 0, 0), parent=p, z=z)
    rrect(c, p, 0.019, 0.0662, 0.0275, 0.0698, INK, e, z, r=0.0008)
    CY.flat(c, "sb_cap", MW_rect(0.0009, 0.0016, 0.0283, 0.068), INK, e, rot=(0, 0, 0), parent=p, z=z)


def MW_rect(w, h, cx=0.0, cy=0.0):
    return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]


def header(c, p, e, title, color=TEAL, sub=None):
    z = 0.0004
    rrect(c, p, -SW / 2, 0.042, SW / 2, 0.064, color, e, z, r=0.0001)
    text(c, title, 0.0064, (1, 1, 1), (-0.029, 0.0545, z + 0.0002), p, kind="bold", emit=e * 1.2)
    if sub:
        text(c, sub, 0.0042, (0.85, 0.93, 0.95), (-0.029, 0.0462, z + 0.0002), p, emit=e)


def row(c, p, e, y, label, value, hl=None, vkind="bold", vcol=INK, spans_hl=None):
    """A form row: small grey label, bold value in a white field; hl = colour of a highlight frame (shown in
    spans_hl)."""
    z = 0.0004
    text(c, label, 0.0038, GREY_T, (-0.029, y + 0.0058, z), p, emit=e)
    rrect(c, p, -0.03, y - 0.0055, 0.03, y + 0.0028, (1, 1, 1), e, z, r=0.0015)
    rrect(c, p, -0.0302, y - 0.0057, 0.0302, y + 0.003, (0.82, 0.83, 0.85), e, z - 0.0001, r=0.0016)
    text(c, value, 0.0056, vcol, (-0.0275, y - 0.0013, z + 0.0002), p, kind=vkind, emit=e)
    if hl:
        f = rrect(c, p, -0.0312, y - 0.0067, 0.0312, y + 0.004, hl, e * 1.3, z - 0.00005, r=0.002)
        CY.show(f, spans_hl or [(0, 999)])


def button(c, p, e, y, label, color=GREEN):
    z = 0.0004
    b = CY.bpy_empty(c, "btn", p)
    rrect(c, b, -0.03, y - 0.0065, 0.03, y + 0.0065, color, e, z, r=0.0065)
    text(c, label, 0.0058, (1, 1, 1), (0.0, y - 0.0003, z + 0.0002), b, align="CENTER", kind="bold", emit=e * 1.2)
    return b


def banner(c, p, e, y, lines, color=AMBER, ink=INK):
    z = 0.0004
    h = 0.0052 * len(lines) + 0.004
    g = CY.bpy_empty(c, "ban", p)
    rrect(c, g, -0.03, y - h, 0.03, y, color, e, z, r=0.002)
    for k, ln in enumerate(lines):
        text(c, ln, 0.0047, ink, (-0.0272, y - 0.0046 - 0.0052 * k, z + 0.0002), g, kind="bold" if k == 0 else "din",
             emit=e)
    return g


def scr_nav(street, dest, turn="left"):
    """Navigation screen: a green instruction bar with a turn arrow and the street name, a map (blocks, streets,
    the blue route turning, the car's position) and the destination at the bottom."""
    def b(c, p, e):
        z = 0.0004
        rrect(c, p, -SW / 2, -SH / 2, SW / 2, 0.064, (0.93, 0.91, 0.86), e, z - 0.0001, r=0.0001)
        for k, (x0, y0, x1, y1) in enumerate([(-0.034, -0.06, -0.008, -0.02), (0.008, -0.06, 0.034, -0.02),
                                             (-0.034, -0.008, -0.008, 0.03), (0.008, -0.008, 0.034, 0.03)]):
            rrect(c, p, x0, y0, x1, y1, (0.86, 0.83, 0.76), e, z, r=0.002)
        sg = -1 if turn == "left" else 1
        route = [(0.0, -0.06), (0.0, -0.014), (sg * 0.03, -0.014)]
        for (x0, y0), (x1, y1) in zip(route, route[1:]):
            CY.flat(c, "route", CY.bar_pts(x0, y0, x1, y1, 0.0055), (0.1, 0.4, 1.0), e * 1.2, rot=(0, 0, 0), parent=p,
                    z=z + 0.0002)
        CY.flat(c, "me", CY.disc_pts(0.0042, 24, 0.0, -0.046), (1, 1, 1), e, rot=(0, 0, 0), parent=p, z=z + 0.0003)
        CY.flat(c, "me2", CY.disc_pts(0.0032, 24, 0.0, -0.046), (0.1, 0.4, 1.0), e * 1.4, rot=(0, 0, 0), parent=p,
                z=z + 0.0004)
        rrect(c, p, -SW / 2, 0.034, SW / 2, 0.064, (0.05, 0.45, 0.25), e, z + 0.0001, r=0.0001)
        CY.flat(c, "arr1", CY.bar_pts(-0.02, 0.039, -0.02, 0.05, 0.0035), (1, 1, 1), e * 1.4, rot=(0, 0, 0), parent=p,
                z=z + 0.0003)
        CY.flat(c, "arr2", CY.bar_pts(-0.02, 0.049, -0.02 + sg * 0.007, 0.049, 0.0035), (1, 1, 1), e * 1.4,
                rot=(0, 0, 0), parent=p, z=z + 0.0003)
        CY.flat(c, "arr3", [(-0.02 + sg * 0.007, 0.0445), (-0.02 + sg * 0.0125, 0.049), (-0.02 + sg * 0.007, 0.0535)],
                (1, 1, 1), e * 1.4, rot=(0, 0, 0), parent=p, z=z + 0.0003)
        text(c, street, 0.0056, (1, 1, 1), (-0.009, 0.0485, z + 0.0003), p, kind="bold", emit=e * 1.2)
        rrect(c, p, -SW / 2, -SH / 2, SW / 2, -0.062, (1, 1, 1), e, z + 0.0001, r=0.0001)
        text(c, dest, 0.0048, INK, (-0.028, -0.0675, z + 0.0003), p, kind="bold", emit=e)
    return b


def scr_pay(title, sub, lines, btn, done, t_tap, t_tick, t_end, color=TEAL):
    """Payment screen: header, a white card of (label, value) rows, a green button that is tapped, then a full
    tick panel with `done`."""
    def b(c, p, e):
        header(c, p, e, title, color=color, sub=sub)
        y = 0.028
        for lab, val in lines:
            row(c, p, e, y, lab, val)
            y -= 0.019
        button(c, p, e, -0.045, btn)
        rip = CY.flat(c, "ripple", CY.disc_pts(0.007, 32, 0.006, -0.045), (1, 1, 1), e * 1.5, rot=(0, 0, 0), parent=p,
                      z=0.0009)
        CY.show(rip, [(t_tap, t_tap + 0.35)])
        ov = CY.bpy_empty(c, "paid", p)
        rrect(c, ov, -SW / 2, -0.066, SW / 2, 0.041, (0.96, 0.965, 0.97), e, 0.0012, r=0.0001)
        tick(c, ov, 0.0, 0.012, 0.014, 0.0014, e)
        text(c, done, 0.0072, INK, (0.0, -0.011, 0.0014), ov, align="CENTER", kind="bold", emit=e)
        CY.show(ov, [(t_tick, t_end)])
    return b


# ------------------------------------------------------------------ cars
def _root(hero):
    return hero["coll"].objects[hero["name"]]


def windscreen(hero):
    import parking as PK
    return PK._windscreen(hero["kind"])


def dash_mount(hero, ph, x=-0.06, back=0.36, up=0.075, tilt=14.0, turn=-14.0):
    """Clip the phone (root from phone()) into a mount on top of the dashboard, screen to the driver (left-hand drive).
    The phone moves into the hero collection, so every instance of the car carries it."""
    top, bot, k = windscreen(hero)
    coll, root = hero["coll"], _root(hero)
    cabin(hero)
    objs = [ph] + list(ph.children_recursive)
    for o in objs:
        for cc in list(o.users_collection):
            cc.objects.unlink(o)
        coll.objects.link(o)
    ph.parent = root
    ph.location = (x, bot.y - back, bot.z - 0.03 + up)
    ph.rotation_euler = (math.radians(90 - tilt), 0, math.radians(turn))
    m = W.principled("mount_black", (0.015, 0.015, 0.017), 0.6)
    TN.box("mount_cradle", coll, (0, 0, -0.012), (0.08, 0.016, 0.012), m, bevel=0.003, parent=ph)
    TN.box("mount_arm", coll, (x, bot.y - back + 0.03, bot.z - 0.03 + 0.012), (0.025, 0.06, 0.024), m, bevel=0.006,
           parent=root)
    adopt(hero)
    return ph


def adopt(hero):
    """motion.rig splits a rigged car into its own collections, so objects added to hero["coll"] after S.drive (the
    see_through cabin, the phone, the cluster, the fill light) are not instanced. Link every such object into the
    collection the instance really shows (skipping copies of objects it already has)."""
    tgt = hero["obj"].instance_collection
    if tgt is None or tgt == hero["coll"]:
        return
    have = set(o.name for o in tgt.all_objects)
    datas = set(id(o.data) for o in tgt.all_objects if o.data is not None)
    for o in hero["coll"].all_objects:
        if o.name in have or (o.data is not None and id(o.data) in datas):
            continue
        tgt.objects.link(o)


def cabin_light(hero, energy=9.0):
    """Soft daylight inside the car (the shell shades the cabin from the sun): a fill under the roof behind the
    driver's head and a cool sky fill at the top of the windscreen aimed back at the dashboard and the wheel. They
    keep the cabin readable in the in-car shots without lighting the scene outside. Made once per hero."""
    coll, root = hero["coll"], _root(hero)
    if coll.objects.get(hero["name"] + "_cabin_fill"):
        return
    top, bot, k = windscreen(hero)
    for nm, loc, rx, size, e, col in (("_cabin_fill", (0.0, bot.y - 0.75, top.z - 0.06), 25, (0.9, 0.6), energy,
                                       (1.0, 0.97, 0.92)),
                                      ("_cabin_sky", (0.0, top.y - 0.12, top.z - 0.04), -42, (1.1, 0.3), energy * 1.2,
                                       (0.93, 0.96, 1.0))):
        li = bpy.data.lights.new(hero["name"] + nm, "AREA")
        li.shape, li.size, li.size_y, li.energy, li.color = "RECTANGLE", size[0], size[1], e, col
        o = bpy.data.objects.new(hero["name"] + nm, li)
        coll.objects.link(o)
        o.parent = root
        o.location = loc
        o.rotation_euler = (math.radians(rx), 0, 0)


def _beam(c, name, p0, p1, w, d, mat, parent=None, bevel=None):
    """A straight bar of cross-section w x d from p0 to p1 (coordinates in the parent's frame)."""
    p0, p1 = Vector(p0), Vector(p1)
    ax = p1 - p0
    o = TN.box(name, c, (0, 0, 0), (w, d, ax.length), mat, bevel=min(w, d) * 0.3 if bevel is None else bevel)
    if parent:
        o.parent = parent
    o.location = (p0 + p1) / 2
    o.rotation_euler = ax.to_track_quat("Z", "Y").to_euler()
    return o


def _torus(c, name, R, r, mat, parent=None, nu=64, nv=14):
    verts, faces = [], []
    for i in range(nu):
        a = 2 * math.pi * i / nu
        for j in range(nv):
            b = 2 * math.pi * j / nv
            verts.append(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b)))
    for i in range(nu):
        for j in range(nv):
            i2, j2 = (i + 1) % nu, (j + 1) % nv
            faces.append((i * nv + j, i2 * nv + j, i2 * nv + j2, i * nv + j2))
    o = W.mesh_obj(name, verts, faces, mat, c, smooth=True)
    if parent:
        o.parent = parent
    return o


def wheel_frame(hero):
    """Steering wheel centre and tilt in the car's frame (left-hand drive): (centre, tilt_deg, rim radius)."""
    top, bot, k = windscreen(hero)
    return Vector((-k["W"] * 0.42, bot.y - 0.66, bot.z - 0.22)), 65.0, 0.18


def cabin(hero, dash=(0.13, 0.125, 0.12), trim=(0.2, 0.195, 0.19), lining=(0.66, 0.64, 0.6)):
    """A visible cabin for the in-car shots (body_off_camera hides the shell, so without it the phone and the
    cluster stood on the road surface, which read as a black void): dashboard top with a binnacle cowl, fascia with
    vents and a dark centre screen, A-pillars, roof header and lining, rear-view mirror, door trims and a three-spoke
    steering wheel on its column. Plain plastics, no brand, no badge. Hides parking.see_through's dark dash and wheel.
    Made once per hero; every instance of the car carries it."""
    coll, root, name = hero["coll"], _root(hero), hero["name"]
    if coll.objects.get(name + "_cab_dash"):
        return
    cabin_light(hero)
    for o in list(coll.all_objects):
        if o.name.split(".")[0] in (name + "_dash", name + "_dash_lower", name + "_wheel"):
            o.hide_render = True
    top, bot, k = windscreen(hero)
    Wh, yb, zb = k["W"], bot.y, bot.z
    DX = -Wh * 0.42
    dm = _noise_mat(name + "_cab_dashm", dash, 0.1, 260.0, 0.72, bump=0.08)
    tm = _noise_mat(name + "_cab_trim", trim, 0.06, 180.0, 0.6, bump=0.05)
    lm = _noise_mat(name + "_cab_lining", lining, 0.05, 140.0, 0.92)
    blk = W.principled(name + "_cab_black", (0.025, 0.025, 0.028), 0.42)
    vent = W.principled(name + "_cab_vent", (0.012, 0.012, 0.014), 0.6)

    def bx(nm, loc, size, m, bevel=0.0, parent=root):
        o = TN.box(name + nm, coll, (0, 0, 0), size, m, bevel=bevel)
        o.parent = parent
        o.location = loc
        return o
    # dashboard: the top from the windscreen foot back to the cluster, deeper on the centre and passenger side
    bx("_cab_dash", (0, yb - 0.17, zb - 0.07), (2 * Wh * 0.92, 0.42, 0.08), dm, 0.03)
    for x0, x1 in ((DX + 0.23, Wh * 0.92), (-Wh * 0.92, DX - 0.23)):
        bx("_cab_dash_b", ((x0 + x1) / 2, yb - 0.42, zb - 0.075), (x1 - x0, 0.15, 0.09), dm, 0.03)
    bx("_cab_cowl", (DX, yb - 0.39, zb + 0.07), (0.44, 0.17, 0.026), dm, 0.012)
    for sx in (-1, 1):
        bx("_cab_cowl_side", (DX + sx * 0.215, yb - 0.41, zb + 0.015), (0.025, 0.13, 0.11), dm, 0.008)
    bx("_cab_fascia", (0, yb - 0.50, zb - 0.27), (2 * Wh * 0.9, 0.08, 0.34), tm, 0.02)
    # centre stack: two vents, a dark screen, a row of plain buttons; outer vents left and right
    fy = yb - 0.545
    for cx, wv in ((0.0, 0.2), (DX - 0.30, 0.12), (Wh * 0.62, 0.12)):
        bx("_cab_vent", (cx, fy, zb - 0.15), (wv, 0.012, 0.06), vent, 0.006)
        for kz in range(4):
            bx("_cab_slat", (cx, fy - 0.007, zb - 0.172 + 0.0145 * kz), (wv * 0.94, 0.006, 0.004), tm)
    scr = W.principled(name + "_cab_screen", (0.01, 0.012, 0.016), 0.12, emit=(0.08, 0.12, 0.16), estr=0.6)
    bx("_cab_screen", (0.0, fy, zb - 0.26), (0.19, 0.01, 0.11), scr, 0.004)
    for kb in range(5):
        bx("_cab_btn", (-0.072 + 0.036 * kb, fy - 0.002, zb - 0.34), (0.026, 0.012, 0.014), blk, 0.003)
    # A-pillars, header, roof lining, rear-view mirror
    for sx in (-1, 1):
        _beam(coll, name + "_cab_pillar", (sx * Wh * 0.9, yb + 0.03, zb - 0.04), (sx * Wh * 0.76, top.y + 0.02,
                                                                                   top.z + 0.03), 0.1, 0.07, tm, root)
    bx("_cab_header", (0, top.y - 0.07, top.z + 0.015), (2 * Wh * 0.84, 0.17, 0.06), lm, 0.02)
    bx("_cab_roof", (0, top.y - 0.9, top.z + 0.05), (2 * Wh * 0.88, 1.6, 0.03), lm)
    bx("_cab_mirror_stalk", (0, top.y - 0.08, top.z - 0.03), (0.02, 0.02, 0.07), blk)
    mir = bx("_cab_mirror", (0, top.y - 0.1, top.z - 0.09), (0.25, 0.035, 0.07), blk, 0.015)
    bx("_cab_mirror_glass", (0, -0.0185, 0), (0.23, 0.003, 0.055), W.principled(name + "_cab_mglass",
                                                                                 (0.8, 0.82, 0.85), 0.04, metal=1.0),
       parent=mir)
    # door trims with a sill along the side windows
    for sx in (-1, 1):
        bx("_cab_door", (sx * Wh * 0.95, yb - 0.9, (0.3 + zb) / 2 - 0.02), (0.06, 1.4, zb - 0.34), tm, 0.02)
        bx("_cab_sill", (sx * Wh * 0.93, yb - 0.9, zb - 0.02), (0.09, 1.4, 0.045), dm, 0.015)
    # steering wheel: rim, hub with a padded centre, three spokes, column shroud
    wc, tilt, R = wheel_frame(hero)
    wg = CY.bpy_empty(coll, name + "_cab_wheel", root, loc=tuple(wc))
    wg.rotation_euler = (math.radians(tilt), 0, 0)
    rim_m = W.principled(name + "_cab_rim", (0.03, 0.03, 0.032), 0.38, coat=0.15)
    _torus(coll, name + "_cab_rim", R, 0.017, rim_m, wg)
    _prism(coll, name + "_cab_hub", CY.disc_pts(0.068, 40), 0.045, blk, z0=-0.025, parent=wg)
    _prism(coll, name + "_cab_pad", W.rounded_rect(0.15, 0.11, 0.035, 6), 0.03, dm, z0=0.015, parent=wg)
    for a in (180.0, 0.0, 270.0):
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        _beam(coll, name + "_cab_spoke", (0.06 * ca, 0.06 * sa, 0.0), (0.172 * ca, 0.172 * sa, -0.004),
              0.045 if a != 270.0 else 0.035, 0.016, blk, wg)
    _beam(coll, name + "_cab_column", (0.0, 0.0, -0.03), (0.0, 0.0, -0.2), 0.085, 0.085, blk, wg, bevel=0.02)
    adopt(hero)


def cluster_view(hero):
    """Driver's view of the cluster for a 9:16 frame with a 30 mm lens: the dials just above the middle, the wheel's
    rim under them and the hub in the lower fifth, the road through the windscreen at the top. Returns (eye, look,
    focus distance) in the car's frame, for cabin_cam."""
    top, bot, k = windscreen(hero)
    DX = -k["W"] * 0.42
    eye = Vector((DX + 0.02, bot.y - 1.15, bot.z + 0.2))
    a = math.radians(19.9)
    look = eye + Vector((0.0, math.cos(a), -math.sin(a))) * 0.75
    return eye, look, 0.76


def body_off_camera(hero, spans, fps=FPS):
    """The car's shell (and its glass) is invisible to camera rays inside `spans` (in-car shots look past the roof
    pillars at the dashboard, the phone or the cluster and the road); it still casts shadows and shows in mirrors of
    nothing. Outside the spans everything is as before."""
    body = hero["coll"].objects.get(hero["name"] + "_body")
    if body is None:
        return
    body.visible_camera = True
    body.keyframe_insert("visible_camera", frame=1)
    for t0, t1 in spans:
        body.visible_camera = False
        body.keyframe_insert("visible_camera", frame=max(1, int(round(t0 * fps)) + 1))
        body.visible_camera = True
        body.keyframe_insert("visible_camera", frame=int(round(t1 * fps)) + 1)
    for fc in stage.fcurves(body):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"


def anim_matrix(o, frame):
    loc, rot = list(o.location), list(o.rotation_euler)
    for fc in stage.fcurves(o):
        if fc.data_path == "location":
            loc[fc.array_index] = fc.evaluate(frame)
        elif fc.data_path == "rotation_euler":
            rot[fc.array_index] = fc.evaluate(frame)
    return Matrix.Translation(loc) @ Euler(rot).to_matrix().to_4x4()


def cabin_cam(inst, hero):
    """cam(t, eye, look): world camera position and target at time t for points given in the car's own frame
    (x right, y forward, z up, as the hero collection), following the baked instance `inst`."""
    rm = Matrix.Translation(-Vector(hero["coll"].instance_offset)) @ _root(hero).matrix_world.copy()

    def cam(t, eye, look):
        m = anim_matrix(inst, int(round(t * FPS)) + 1) @ rm
        return m @ Vector(eye), m @ Vector(look)
    return cam


def cluster(hero, speed_kmh_fn=None, limit=None, glow=2.0):
    """Instrument cluster behind the steering wheel: a dark hood, a lit speedometer dial with real scale numbers
    (0 to 260 in 20s) and a needle keyed from speed_kmh_fn(t). Returns the needle pivot."""
    top, bot, k = windscreen(hero)
    coll, root = hero["coll"], _root(hero)
    cabin(hero)
    Wh = k["W"]
    g = bpy.data.objects.new("cluster", None)
    coll.objects.link(g)
    g.parent = root
    g.location = (-Wh * 0.42, bot.y - 0.42, bot.z - 0.02)
    g.rotation_euler = (math.radians(72), 0, 0)
    hood = W.principled("cl_hood", (0.02, 0.02, 0.022), 0.7)
    TN.box("cl_hood", coll, (0, 0.074, 0.03), (0.35, 0.012, 0.065), hood, bevel=0.004, parent=g)
    CY.flat(coll, "cl_face", W.rounded_rect(0.32, 0.13, 0.03, 6), (0.01, 0.012, 0.016), 0.0, rot=(0, 0, 0),
            parent=g, z=0.0)
    piv = None
    for cx, kind in ((-0.075, "speed"), (0.075, "info")):
        CY.flat(coll, "cl_ring", CY.disc_pts(0.058, 64, cx, 0.0), (0.75, 0.78, 0.82), glow * 0.4, rot=(0, 0, 0),
                parent=g, z=0.0003)
        CY.flat(coll, "cl_dial", CY.disc_pts(0.055, 64, cx, 0.0), (0.02, 0.025, 0.03), 0.0, rot=(0, 0, 0), parent=g,
                z=0.0005)
        if kind == "speed":
            for v in range(0, 261, 10):
                a = math.radians(225 - 270 * v / 260)
                r0, r1 = (0.043, 0.052) if v % 20 == 0 else (0.047, 0.052)
                CY.flat(coll, "cl_tk", CY.bar_pts(cx + r0 * math.cos(a), r0 * math.sin(a), cx + r1 * math.cos(a),
                                                   r1 * math.sin(a), 0.0016 if v % 20 == 0 else 0.0009),
                        (0.95, 0.95, 0.95), glow, rot=(0, 0, 0), parent=g, z=0.0007)
                if v % 40 == 0:
                    text(coll, str(v), 0.0085, (0.95, 0.95, 0.95), (cx + 0.034 * math.cos(a), 0.034 * math.sin(a),
                                                                    0.0007), g, align="CENTER", emit=glow)
            text(coll, "km/h", 0.0065, (0.7, 0.72, 0.75), (cx, -0.024, 0.0007), g, align="CENTER", emit=glow * 0.7)
            piv = CY.bpy_empty(coll, "cl_needle", g, loc=(cx, 0.0, 0.0011))
            CY.flat(coll, "cl_n", [(-0.004, -0.0022), (0.05, -0.0007), (0.05, 0.0007), (-0.004, 0.0022)],
                    (1.0, 0.25, 0.05), glow * 1.5, rot=(0, 0, 0), parent=piv, z=0.0)
            CY.flat(coll, "cl_hub", CY.disc_pts(0.006, 24), (0.08, 0.08, 0.09), 0.0, rot=(0, 0, 0), parent=piv,
                    z=0.0002)
            if speed_kmh_fn:
                for f in range(1, 1300, 3):
                    v = max(0.0, min(260.0, speed_kmh_fn((f - 1) / FPS)))
                    piv.rotation_euler = (0, 0, math.radians(225 - 270 * v / 260))
                    piv.keyframe_insert("rotation_euler", frame=f)
        else:
            for v in range(0, 9):
                a = math.radians(225 - 270 * v / 8)
                CY.flat(coll, "cl_tk2", CY.bar_pts(cx + 0.044 * math.cos(a), 0.044 * math.sin(a),
                                                    cx + 0.052 * math.cos(a), 0.052 * math.sin(a), 0.0014),
                        (0.95, 0.95, 0.95), glow, rot=(0, 0, 0), parent=g, z=0.0007)
            CY.flat(coll, "cl_n2", CY.bar_pts(cx, 0.0, cx + 0.045 * math.cos(math.radians(150)),
                                               0.045 * math.sin(math.radians(150)), 0.0014), (1.0, 0.25, 0.05),
                    glow * 1.5, rot=(0, 0, 0), parent=g, z=0.001)
    adopt(hero)
    return piv


# ------------------------------------------------------------------ rooms and props
def _noise_mat(name, base, var=0.08, scale=6.0, rough=0.6, wood=False, bump=0.0):
    """Noise-tinted surface (object coordinates in metres: scale 6 gives features of about 15 cm). wood=True gives
    planks with a fine grain (_wood_mat; the old wave texture read as sand ripples). bump: relief strength."""
    if wood:
        return _wood_mat(name, base, var, rough)
    m = W.principled(name, base, rough)
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tx = nt.nodes.new("ShaderNodeTexNoise")
    tx.inputs["Scale"].default_value = scale
    nt.links.new(tc.outputs["Object"], tx.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*[max(0.0, v * (1 - var)) for v in base], 1)
    ramp.color_ramp.elements[1].color = (*[min(1.0, v * (1 + var)) for v in base], 1)
    nt.links.new(tx.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    if bump:
        bn = nt.nodes.new("ShaderNodeBump")
        bn.inputs["Strength"].default_value = bump
        bn.inputs["Distance"].default_value = 0.002
        nt.links.new(tx.outputs["Fac"], bn.inputs["Height"])
        nt.links.new(bn.outputs["Normal"], p.inputs["Normal"])
    return m


def _wood_mat(name, base, var=0.3, rough=0.4, plank=0.12, length=1.9):
    """Wood at a believable scale: planks `plank` m wide and up to `length` m long (thin dark joints, each plank a
    slightly different shade) with a fine streaky grain along x (streaks a few mm across, tens of cm long)."""
    m = W.principled(name, base, rough)
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (2.2, 60.0, 60.0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 9.0
    nz.inputs["Roughness"].default_value = 0.62
    nz.inputs["Distortion"].default_value = 0.35
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.32, 0.68
    ramp.color_ramp.elements[0].color = (*[max(0.0, v * (1 - 0.8 * var)) for v in base], 1)
    ramp.color_ramp.elements[1].color = (*[min(1.0, v * (1 + 0.4 * var)) for v in base], 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset, br.offset_frequency = 0.37, 1
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.0015
    br.inputs["Brick Width"].default_value = length
    br.inputs["Row Height"].default_value = plank
    br.inputs["Bias"].default_value = 0.0
    br.inputs["Color1"].default_value = (1.0, 1.0, 1.0, 1)
    br.inputs["Color2"].default_value = (0.8, 0.8, 0.8, 1)
    br.inputs["Mortar"].default_value = (0.3, 0.3, 0.3, 1)
    nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    nt.links.new(ramp.outputs["Color"], mix.inputs["A"])
    nt.links.new(br.outputs["Color"], mix.inputs["B"])
    nt.links.new(mix.outputs["Result"], p.inputs["Base Color"])
    bn = nt.nodes.new("ShaderNodeBump")
    bn.invert = True
    bn.inputs["Strength"].default_value = 0.25
    bn.inputs["Distance"].default_value = 0.0008
    nt.links.new(br.outputs["Fac"], bn.inputs["Height"])
    nt.links.new(bn.outputs["Normal"], p.inputs["Normal"])
    return m


def area(c, name, loc, rot, size, energy, color=(1.0, 0.96, 0.9), size_y=None):
    li = bpy.data.lights.new(name, "AREA")
    li.shape = "RECTANGLE"
    li.size, li.size_y = size, size_y or size
    li.energy, li.color = energy, color
    o = bpy.data.objects.new(name, li)
    c.objects.link(o)
    o.location, o.rotation_euler = loc, rot
    return o


def room(c, name, o, w=5.0, d=4.0, h=2.7, wall=(0.78, 0.72, 0.62), floor=(0.36, 0.22, 0.12), window=True,
         light=45.0):
    """A room with its back wall at y = o.y + d/2 (facing -y), side walls, wooden floor and ceiling; a window in the
    left wall with daylight (an area light just outside and a bright pane). The camera stands inside, looking +y."""
    o = Vector(o)
    wm = _noise_mat(name + "_wall", wall, 0.05, 3.0, 0.9)
    fm = _noise_mat(name + "_floor", floor, 0.35, 2.5, 0.45, wood=True)
    TN.box(name + "_back", c, tuple(o + Vector((0, d / 2 + 0.05, h / 2))), (w, 0.1, h), wm)
    TN.box(name + "_front", c, tuple(o + Vector((0, -d / 2 - 0.05, h / 2))), (w, 0.1, h), wm)
    TN.box(name + "_right", c, tuple(o + Vector((w / 2 + 0.05, 0, h / 2))), (0.1, d, h), wm)
    TN.box(name + "_floor", c, tuple(o + Vector((0, 0, -0.05))), (w, d, 0.1), fm)
    TN.box(name + "_ceil", c, tuple(o + Vector((0, 0, h + 0.05))), (w, d, 0.1), W.principled(name + "_ceil",
                                                                                            (0.9, 0.9, 0.88), 0.9))
    TN.box(name + "_skirt", c, tuple(o + Vector((0, d / 2 - 0.006, 0.05))), (w, 0.012, 0.1),
           W.principled(name + "_sk", (0.92, 0.92, 0.9), 0.5))
    lx = o.x - w / 2 - 0.05
    if window:
        wy0, wy1, wz0, wz1 = o.y - 0.2, o.y + 1.2, 0.9, 2.3
        for y0, y1, z0, z1 in ((o.y - d / 2, wy0, 0, h), (wy1, o.y + d / 2, 0, h), (wy0, wy1, 0, wz0),
                               (wy0, wy1, wz1, h)):
            TN.box(name + "_left", c, (lx, (y0 + y1) / 2, (z0 + z1) / 2), (0.1, y1 - y0, z1 - z0), wm)
        frm = W.principled(name + "_frame", (0.93, 0.93, 0.92), 0.4)
        for yy in (wy0, (wy0 + wy1) / 2, wy1):
            TN.box(name + "_mull", c, (lx + 0.02, yy, (wz0 + wz1) / 2), (0.08, 0.06, wz1 - wz0), frm)
        for zz in (wz0, wz1):
            TN.box(name + "_rail", c, (lx + 0.02, (wy0 + wy1) / 2, zz), (0.08, wy1 - wy0, 0.06), frm)
        CY.flat(c, name + "_sky", MW_rect(wy1 - wy0, wz1 - wz0), (0.75, 0.85, 1.0), 1.2,
                loc=(lx - 0.6, (wy0 + wy1) / 2, (wz0 + wz1) / 2), rot=(math.pi / 2, 0, -math.pi / 2))
        area(c, name + "_sun", (lx - 0.3, (wy0 + wy1) / 2, (wz0 + wz1) / 2), (0, -math.pi / 2, 0), wy1 - wy0, light * 6,
             (1.0, 0.95, 0.86), size_y=wz1 - wz0)
    else:
        TN.box(name + "_left", c, (lx, o.y, h / 2), (0.1, d, h), wm)
    area(c, name + "_fill", tuple(o + Vector((0, -0.4, h - 0.05))), (0, 0, 0), 1.2, light, (1.0, 0.94, 0.85))
    return o


def table(c, name, top_c, w=1.4, d=0.85, h=0.75):
    m = _noise_mat(name + "_top", (0.55, 0.36, 0.2), 0.3, 3.0, 0.35, wood=True)
    top_c = Vector(top_c)
    TN.box(name + "_top", c, tuple(top_c + Vector((0, 0, -0.02))), (w, d, 0.04), m, bevel=0.006)
    for sx in (-1, 1):
        for sy in (-1, 1):
            TN.box(name + "_leg", c, tuple(top_c + Vector((sx * (w / 2 - 0.06), sy * (d / 2 - 0.06), -h / 2))),
                   (0.05, 0.05, h - 0.04), m)
    return top_c


def mug(c, name, loc, color=(0.85, 0.2, 0.15)):
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=0.04, radius2=0.042, depth=0.095)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    me.materials.append(W.principled(name + "_m", color, 0.25, coat=0.5))
    o.location = Vector(loc) + Vector((0, 0, 0.0475))
    for p in me.polygons:
        p.use_smooth = True
    CY.flat(c, name + "_coffee", CY.disc_pts(0.037, 32), (0.12, 0.06, 0.03), 0.0, rot=(0, 0, 0), parent=o, z=0.035)
    return o


def letter(c, name, loc, rz, blocks, envelope=True):
    """An A4 sheet lying on a surface at loc (its top surface), turned rz about z, with typeset text.
    blocks: [(text, size, kind, colour, gap_before)] from the top margin down (x from the left margin)."""
    g = bpy.data.objects.new(name, None)
    c.objects.link(g)
    g.location, g.rotation_euler = loc, (0, 0, rz)
    paper = _noise_mat(name + "_paper", (0.93, 0.93, 0.9), 0.02, 40.0, 0.85)
    TN.box(name + "_sheet", c, (0, 0, 0.0004), (0.21, 0.297, 0.0008), paper, parent=g)
    y = 0.297 / 2 - 0.028
    for body, size, kind, col, gap in blocks:
        y -= gap + size * 0.75
        text(c, body, size, col, (-0.21 / 2 + 0.022, y, 0.0009), g, kind=kind)
    if envelope:
        e = bpy.data.objects.new(name + "_env", None)
        c.objects.link(e)
        e.parent = g
        e.location, e.rotation_euler = (0.215, 0.165, 0.0), (0, 0, math.radians(-12))
        TN.box(name + "_envb", c, (0, 0, 0.0012), (0.229, 0.114, 0.0024), paper, parent=e)
        TN.box(name + "_envw", c, (-0.045, 0.006, 0.0025), (0.09, 0.045, 0.0003),
               W.principled(name + "_win", (0.85, 0.87, 0.88), 0.2), parent=e)
    return g


def wall_calendar(c, name, loc, month, first_weekday, ndays, weekdays, marks=None, w=0.42):
    """A hanging wall calendar on the wall plane (face -y) at loc (centre of the sheet): a coloured top with the
    month name and a mountain picture, a day grid with real numbers (weekends red). Returns {day: (x, z) world-ish
    local position} and the root, so the episode can add pen marks."""
    g = bpy.data.objects.new(name, None)
    c.objects.link(g)
    g.location, g.rotation_euler = loc, (math.pi / 2, 0, 0)
    h = w * 1.42
    paper = _noise_mat(name + "_p", (0.95, 0.95, 0.93), 0.02, 30.0, 0.8)
    TN.box(name + "_sheet", c, (0, 0, -0.001), (w, h, 0.002), paper, parent=g)
    TN.box(name + "_back", c, (0, -0.004, -0.004), (w + 0.01, h + 0.008, 0.003),
           W.principled(name + "_card", (0.3, 0.3, 0.32), 0.7), parent=g)
    for k in range(14):
        x = -w / 2 + 0.03 + k * (w - 0.06) / 13
        TN.box(name + "_ring", c, (x, h / 2 - 0.005, 0.002), (0.004, 0.02, 0.006), TN_steel(), parent=g)
    TN.box(name + "_nail", c, (0, h / 2 + 0.02, 0.0), (0.008, 0.008, 0.02), TN_steel(), parent=g)
    pt, pb = h / 2 - 0.02, h / 2 - 0.02 - w * 0.62
    alpine_picture(c, g, name, -w / 2 + 0.015, w / 2 - 0.015, pb, pt)
    text(c, month, 0.04, (0.12, 0.13, 0.15), (0.0, pb - 0.035, 0.0003), g, align="CENTER", kind="bold")
    gx0, gw = -w / 2 + 0.03, (w - 0.06) / 7
    yh = pb - 0.075
    for k, wd in enumerate(weekdays):
        text(c, wd, 0.017, RED if k >= 5 else GREY_T, (gx0 + gw * (k + 0.5), yh, 0.0003), g, align="CENTER",
             kind="bold")
    rh = 0.052
    pos = {}
    for d in range(1, ndays + 1):
        i = first_weekday + d - 1
        col, rw = i % 7, i // 7
        x, y = gx0 + gw * (col + 0.5), yh - 0.04 - rh * rw
        text(c, str(d), 0.03, RED if col >= 5 else (0.1, 0.1, 0.12), (x, y, 0.0003), g, align="CENTER",
             kind="din")
        pos[d] = (x, y)
        if rw:
            CY.flat(c, name + "_rule", MW_rect(w - 0.06, 0.0012, 0.0, y + rh / 2), (0.75, 0.75, 0.75), 0.0,
                    rot=(0, 0, 0), parent=g, z=0.0002)
    return g, pos, gw, rh


def alpine_picture(c, g, name, x0, x1, y0, y1, seed=11):
    """A printed mountain photo made of shaded geometry (no photo file, no brand): sky gradient with clouds, a pale
    far range and a craggy near range, each with lit and shaded flanks, snow caps (lit and blue-grey in shade) and
    rock ribs, two bands of conifer forest, a meadow with a path and a small chalet. Lies in g's xy plane."""
    rnd = random.Random(seed)
    W_, H_ = x1 - x0, y1 - y0
    zz = [0.0003]

    def P(u, v):
        return (x0 + u * W_, y0 + v * H_)

    def poly(nm, pts, col, e=0.1):
        zz[0] += 0.00005
        CY.flat(c, name + nm, pts, col, e, rot=(0, 0, 0), parent=g, z=zz[0])
    top_c, hor_c = (0.12, 0.32, 0.7), (0.75, 0.85, 0.94)
    for i in range(9):
        v0, v1, f = 0.4 + 0.6 * i / 9, 0.4 + 0.6 * (i + 1) / 9, (i + 0.5) / 9
        poly("_sky", [P(0, v0), P(1, v0), P(1, v1), P(0, v1)],
             tuple(hor_c[j] + (top_c[j] - hor_c[j]) * f ** 0.8 for j in range(3)), 0.12)
    for cu, cv, rx, ry in ((0.16, 0.9, 0.12, 0.035), (0.26, 0.92, 0.09, 0.03), (0.7, 0.83, 0.13, 0.03),
                           (0.8, 0.85, 0.08, 0.028)):
        poly("_cloud", [P(cu + rx * math.cos(a), cv + ry * math.sin(a) * (0.6 if math.sin(a) < 0 else 1.0))
                        for a in [2 * math.pi * k / 28 for k in range(28)]], (0.97, 0.97, 0.98), 0.15)

    def mountains(tag, peaks, base, rock, shade, snow, snow_sh, snowline, ribs=0, n=110, jit=0.014):
        xs = [k / (n - 1) for k in range(n)]
        top = max(p[1] for p in peaks) - base
        ys0 = [max([base] + [base + (pv - base) * max(0.0, 1 - abs(u - pu) / sp) ** 1.15 for pu, pv, sp in peaks])
               for u in xs]
        ys = [v + rnd.uniform(-jit, jit) * (v - base) / top for v in ys0]
        poly(tag + "_rock", [P(0, base - 0.05)] + [P(u, v) for u, v in zip(xs, ys)] + [P(1, base - 0.05)], rock)
        for pu, pv, sp in peaks:
            i = min(range(n), key=lambda k: abs(xs[k] - pu))
            j = i
            while j + 1 < n and ys0[j + 1] < ys0[j] + 1e-9:
                j += 1
            if j - i >= 2:
                poly(tag + "_shade", [P(xs[k], ys[k]) for k in range(i, j + 1)] +
                     [P(xs[j], base - 0.05), P(xs[i] + 0.3 * (xs[j] - xs[i]), base - 0.05)], shade)
        low = [min(ys[k], max(snowline + rnd.uniform(0.0, 0.03), ys[k] - (0.3 + rnd.uniform(0.0, 0.3)) *
                              (max(p[1] for p in peaks) - snowline))) for k in range(n)]
        for pu, pv, sp in peaks:
            if pv <= snowline + 0.02:
                continue
            i = min(range(n), key=lambda k: abs(xs[k] - pu))
            a = b = i
            while a - 1 >= 0 and ys[a - 1] > snowline:
                a -= 1
            while b + 1 < n and ys[b + 1] > snowline:
                b += 1
            for s0, s1, col in ((a, i, snow), (i, b, snow_sh)):
                if s1 - s0 >= 1:
                    poly(tag + "_snow", [P(xs[k], ys[k]) for k in range(s0, s1 + 1)] +
                         [P(xs[k], low[k]) for k in range(s1, s0 - 1, -1)], col, 0.14)
        for r in range(ribs):
            k = rnd.randrange(3, n - 3)
            if ys[k] - base < 0.35 * top:
                continue
            ln = rnd.uniform(0.06, 0.16)
            dx = rnd.choice((-1, 1)) * rnd.uniform(0.01, 0.04)
            xa, ya = P(xs[k], ys[k] - 0.012)
            xb, yb_ = P(xs[k] + dx, ys[k] - 0.012 - ln)
            poly(tag + "_rib", CY.bar_pts(xa, ya, xb, yb_, rnd.uniform(0.0012, 0.0022)),
                 tuple(v * 0.75 for v in shade))
    mountains("_far", [(0.12, 0.6, 0.2), (0.4, 0.68, 0.2), (0.86, 0.63, 0.24)], 0.4, (0.56, 0.61, 0.73),
              (0.43, 0.48, 0.61), (0.95, 0.96, 0.99), (0.75, 0.8, 0.9), 0.56)
    mountains("_near", [(0.3, 0.86, 0.28), (0.6, 0.95, 0.25), (0.9, 0.74, 0.2)], 0.3, (0.43, 0.41, 0.41),
              (0.27, 0.27, 0.31), (0.96, 0.97, 1.0), (0.7, 0.76, 0.88), 0.68, ribs=16)
    for k, (hill, amp, col, th0) in enumerate(((0.3, 0.04, (0.09, 0.24, 0.14), 0.06), (0.21, 0.05, (0.05, 0.17, 0.1),
                                                                                       0.08))):
        pts, u = [P(0, 0.05)], 0.0
        while u < 1.0:
            tw = rnd.uniform(0.016, 0.028)
            hv = hill + amp * math.sin(u * 5.0 + 1.3 * k)
            pts += [P(u, hv), P(min(1.0, u + tw / 2), hv + rnd.uniform(th0 * 0.6, th0 * 1.3))]
            u += tw
        pts += [P(1.0, hill + amp * math.sin(5.0 + 1.3 * k)), P(1.0, 0.05)]
        poly("_forest", pts, col, 0.08)
    poly("_meadow", [P(0, 0)] + [P(k / 20, 0.17 + 0.03 * math.sin(k / 20 * 4.0)) for k in range(21)] + [P(1, 0)],
         (0.33, 0.55, 0.18), 0.12)
    poly("_sunlit", [P(0.55 + 0.3 * math.cos(a), 0.1 + 0.06 * math.sin(a)) for a in
                     [2 * math.pi * k / 24 for k in range(24)]], (0.45, 0.66, 0.24), 0.12)
    poly("_path", [P(0.42, 0.0), P(0.56, 0.0), P(0.5, 0.08), P(0.4, 0.15), P(0.37, 0.15), P(0.45, 0.08)],
         (0.78, 0.7, 0.55), 0.1)
    poly("_chalet", [P(0.66, 0.13), P(0.74, 0.13), P(0.74, 0.19), P(0.66, 0.19)], (0.45, 0.27, 0.13), 0.1)
    poly("_roof", [P(0.645, 0.185), P(0.755, 0.185), P(0.735, 0.225), P(0.665, 0.225)], (0.22, 0.12, 0.08), 0.1)
    for wu in (0.675, 0.715):
        poly("_win", [P(wu, 0.15), P(wu + 0.016, 0.15), P(wu + 0.016, 0.17), P(wu, 0.17)], (0.95, 0.93, 0.85), 0.15)


def TN_steel():
    if "steel" not in _M:
        _M["steel"] = W.principled("ins_steel", (0.6, 0.62, 0.64), 0.3, metal=1.0)
    return _M["steel"]


def pen_cross(c, g, x, y, s, z, color=RED, name="x"):
    e = CY.bpy_empty(c, name, g)
    for a, b in (((x - s, y - s), (x + s, y + s)), ((x - s, y + s), (x + s, y - s))):
        CY.flat(c, name + "_s", CY.bar_pts(a[0], a[1], b[0], b[1], 0.0045), color, 0.15, rot=(0, 0, 0), parent=e, z=z)
    return e


def pen_ring(c, g, x, y, r, z, color=GREEN, name="ring", width=0.005):
    e = CY.bpy_empty(c, name, g, loc=(x, y, z))
    n = 36
    for k in range(n):
        a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1.15) / n
        CY.flat(c, name + "_s", CY.bar_pts(r * math.cos(a0), r * 0.85 * math.sin(a0), r * math.cos(a1),
                                           r * 0.85 * math.sin(a1), width), color, 0.2, rot=(0, 0, 0), parent=e,
                z=0.0)
    return e


def shop(c, name, o, glow=1.6):
    """Fuel-station shop interior around o (floor level, counter front edge at o.y, customer side -y): a counter with
    a card terminal and a till screen facing the customer, shelves with plain packs behind, ceiling light panels,
    a drinks fridge. No brand, no prices. Returns dict(counter_top=Vector, terminal=screen parent, till=screen parent)."""
    o = Vector(o)
    room(c, name + "_rm", o + Vector((0, 1.2, 0)), w=7.0, d=6.0, h=3.0, wall=(0.86, 0.86, 0.84), floor=(0.6, 0.58,
                                                                                                       0.55),
         window=True, light=30.0)
    top_m = _noise_mat(name + "_ctop", (0.75, 0.73, 0.7), 0.06, 8.0, 0.3)
    front_m = W.principled(name + "_cfront", (0.06, 0.24, 0.3), 0.45)
    ct = o + Vector((0, 0.35, 1.02))
    TN.box(name + "_ctop", c, tuple(ct), (2.6, 0.7, 0.04), top_m, bevel=0.008)
    TN.box(name + "_cbody", c, tuple(o + Vector((0, 0.38, 0.5))), (2.5, 0.62, 1.0), front_m, bevel=0.01)
    # shelves behind the counter
    sh_m = W.principled(name + "_shelf", (0.85, 0.85, 0.86), 0.4, metal=0.4)
    rnd = random.Random(7)
    rnd.random()
    by = o.y + 1.2 + 3.0 - 0.25
    for z in (0.5, 0.95, 1.4, 1.85):
        TN.box(name + "_shelf", c, (o.x, by, z), (4.2, 0.4, 0.025), sh_m)
        x = o.x - 2.0
        while x < o.x + 2.0:
            bw = rnd.uniform(0.07, 0.16)
            bh = rnd.uniform(0.12, 0.3)
            col = rnd.choice([(0.8, 0.15, 0.1), (0.1, 0.35, 0.7), (0.95, 0.75, 0.1), (0.15, 0.55, 0.25),
                              (0.9, 0.9, 0.88), (0.35, 0.15, 0.45), (0.95, 0.45, 0.1)])
            TN.box(name + "_pack", c, (x + bw / 2, by - 0.05, z + 0.0125 + bh / 2), (bw * 0.92, 0.22, bh),
                   _mat(col, None, 0.35))
            x += bw
    # drinks fridge on the right, lit
    TN.box(name + "_fridge", c, (o.x + 2.9, o.y + 2.2, 1.0), (0.9, 0.7, 2.0), W.principled(name + "_fr", (0.1, 0.1,
                                                                                                        0.11), 0.4))
    CY.flat(c, name + "_frglow", MW_rect(0.7, 1.7), (0.85, 0.92, 1.0), 1.2, loc=(o.x + 2.44, o.y + 2.2, 1.05),
            rot=(math.pi / 2, 0, -math.pi / 2))
    for k in range(3):
        CY.flat(c, name + "_ceil", MW_rect(1.2, 0.3), (1.0, 0.98, 0.94), 1.5, loc=(o.x - 1.5 + 1.5 * k, o.y + 1.0, 2.94),
                rot=(math.pi, 0, 0))
    area(c, name + "_key", tuple(o + Vector((0.3, -0.6, 2.6))), (math.radians(20), 0, 0), 1.6, 55.0,
         (1.0, 0.97, 0.92))
    # card terminal, standing on the counter, screen up and towards the customer
    term = bpy.data.objects.new(name + "_term", None)
    c.objects.link(term)
    term.location = ct + Vector((0.35, -0.12, 0.02))
    term.rotation_euler = (math.radians(35), 0, math.radians(-8))
    tb = W.principled(name + "_tb", (0.05, 0.05, 0.055), 0.4, coat=0.4)
    TN.box(name + "_tbody", c, (0, 0, -0.012), (0.085, 0.17, 0.024), tb, bevel=0.006, parent=term)
    for r in range(4):
        for k in range(3):
            TN.box(name + "_key", c, (-0.024 + 0.024 * k, -0.068 + 0.016 * r, 0.0005), (0.018, 0.011, 0.003),
                   _mat((0.75, 0.76, 0.78), None, 0.4), parent=term)
    scr = CY.bpy_empty(c, name + "_tscr", term, loc=(0, 0.035, 0.0006))
    CY.flat(c, name + "_tscr_bg", W.rounded_rect(0.066, 0.07, 0.004, 4), (0.96, 0.97, 0.97), glow, rot=(0, 0, 0),
            parent=scr, z=0.0)
    # till monitor on a stand, screen towards the customer
    till = bpy.data.objects.new(name + "_till", None)
    c.objects.link(till)
    till.location = ct + Vector((-0.55, 0.15, 0.32))
    till.rotation_euler = (math.radians(80), 0, math.radians(10))
    TN.box(name + "_tillb", c, (0, 0, -0.012), (0.36, 0.24, 0.02), tb, bevel=0.006, parent=till)
    TN.box(name + "_tills", c, tuple(ct + Vector((-0.55, 0.2, 0.12))), (0.05, 0.05, 0.24), tb)
    tscr = CY.bpy_empty(c, name + "_tillscr", till, loc=(0, 0, 0.0))
    CY.flat(c, name + "_till_bg", W.rounded_rect(0.34, 0.22, 0.006, 4), (0.95, 0.96, 0.97), glow, rot=(0, 0, 0),
            parent=tscr, z=0.0003)
    return dict(counter_top=ct, terminal=scr, term=term, till=tscr)
