"""Drive Like a Local #20, Germany (standard): the phone at a red light. The start-stop system switching the engine off
does not count as engine off; only a fully switched-off engine allows the phone in hand (StVO 23 (1a), (1b)).
9:16, 30 fps, no voice. Set: the signal town stage (traffic lights on all approaches, stop lines) with a 12 m main
street (two lanes each way, lane lines added), weather.apply('night') for every live-action shot (lamps, lit windows,
low beams), day for the end card. White rental hatchback (hero), a police estate (vehicles.car police=True: plain
POLIZEI, no crest), close-up props in a small studio: dashboard with an auto-stop symbol (the letter A in a ring),
steering wheel, engine button, a phone held over the wheel and a phone in a dash mount; the officer's notepad on the
hero's roof under a torch (COST), then the two cars at the red light from behind with the fine.
No sign in this rule (none exists); the end card shows the series title only. Teaching marks (cross, tick) are ASS
drawings (post_ep20.py).
Canonical timeline (English order; finish_ep cuts each language's order from ep20_edit.json):
HOOK 0-2.2, SITUATION 2.2-12.2, RULE 12.2-20.2, COST 20.2-24.7, CORRECT 24.7-31.2, END 31.2-33.9.
Run: python ep20_phone_red_light.py OUTDIR --frames 1-1017 --res 540 --samples 8 --assets ASSETS [--stills 20,300]
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "ep10")]
import ep10_za5kit as K  # noqa: E402
from ep10_za5kit import bpy, Vector, jx, SG, TN, TP, TS, W, FPS  # noqa: E402
from mathutils import Matrix  # noqa: E402

TL = K.Timeline([("HOOK", 2.2), ("SITUATION", 10.0), ("RULE", 8.0), ("COST", 4.5), ("CORRECT", 6.5), ("END", 2.7)])
N = TL.N
HX, HY = 6.0, 3.0
S = TS.build(K.ASSETS, "signal", seed=20, hx=HX, hy=HY, parked=False, heroes=[
    ("hatch", (0.86, 0.87, 0.86), "hero", "QX HY 230", 0.35)])
SG.setup(K.ASSETS)
T, env, lib, traf, fleet, J = S["T"], S["env"], S["lib"], S["traffic"], S["fleet"], S["J"]
H = S["heroes"]["hero"]
st = TP.through(J, "NS")
Y_LINE = -(HY + 6.0 + 1.0)                       # the south stop line (townstage: R + 1 m behind the kerb line)
TP.rects("lane_div", st, TP.dashes(-150.0, Y_LINE - 0.5, 3.0, 6.0, 2.94, 3.06) +
         TP.dashes(-Y_LINE + 0.5, 150.0, 3.0, 6.0, -3.06, -2.94), TP.PAINT_Z, T.paint, env, kind="leitlinie")
XR, XL = 4.5, 1.5                                # northbound right and left lanes
# ------------------------------------------------------------------ signals: NS red, then red-yellow, then green
NS, EW = S["furniture"]["signals"]["NS"], S["furniture"]["signals"]["EW"]
f = TL.f
# COST stays red for the hero's approach (rev 3: C_rear shows the signal under "Phone at the red light", it turned green)
for fr, s_ns in ((1, "red"), (f("SITUATION", 9.0), "redyellow"), (f("SITUATION", 9.8), "green"), (f("RULE"), "red"),
                 (f("CORRECT"), "red"), (f("CORRECT", 4.0), "redyellow"), (f("CORRECT", 5.0), "green")):
    NS.key(fr, s_ns)
for fr, s_ew in ((1, "green"), (f("SITUATION", 7.5), "yellow"), (f("SITUATION", 8.5), "red"), (f("RULE"), "green"),
                 (f("CORRECT"), "green"), (f("CORRECT", 2.6), "yellow"), (f("CORRECT", 3.6), "red")):
    EW.key(fr, s_ew)
NS.constant()
EW.constant()

# ------------------------------------------------------------------ the hero and the police estate
P_r = K.line((XR, -200.0), (XR, 200.0))
P_l = K.line((XL, -200.0), (XL, 200.0))
s_stop = K.s_of_y(P_r, Y_LINE - 0.4 - H["L"] / 2)     # (jx.Path.s_of_y gave 0 here: the cars stood at y = -200)
stop = lambda n, a=0.0: K.hold(s_stop + a, n)   # noqa: E731
nS, nC = TL.n("SITUATION"), TL.n("CORRECT")
# CORRECT (a5cockpit): K_mount is filmed from the driver's seat, so the hero rolls up to the red light continuously
# (8 m/s, an even stop at the line at 3.6 s) instead of standing 20 m back and jumping forward at 2.6 s; it stands
# until 5.5 s and pulls away on green as before. RULE: the hero stands at the line (R_dash is filmed inside it).
sv_k = K.brake(s_stop, 8.0, 0.0, 3.6, int(3.6 * FPS)) + K.hold(s_stop, int(1.9 * FPS))
sv_k += K.kin(s_stop, 0.0, [(0, "cruise", 6.0)], nC - len(sv_k), a_acc=2.0)
K.bake(H, K.track(TL, {"HOOK": (P_r, stop(TL.n("HOOK"))), "SITUATION": (P_r, K.brake(s_stop, 11.1, 0.0, 2.5, nS)),
                       "RULE": (P_r, stop(TL.n("RULE"))), "COST": (P_r, stop(TL.n("COST"))),
                       "CORRECT": (P_r, sv_k)}, H["L"]), night=True)
pol = K.vehicle(K.V.car("estate", (0.8, 0.81, 0.82), "police", "QX PD 120", police=True, c=lib), traf, "trf_police")
s_pol = s_stop + 0.3
nH = TL.n("HOOK")
K.bake(pol, K.track(TL, {"HOOK": (P_l, K.brake(s_pol, 6.0, 1.3, 2.1, nH)),
                         "SITUATION": (P_l, K.brake(s_pol, 8.0, 3.4, 6.8, nS), dict(ind=[("R", 0.0, 2.0)])),
                         "RULE": (P_l, K.hold(s_pol, TL.n("RULE"))),
                         "COST": (P_l, K.hold(s_pol, TL.n("COST")))}, 4.6), night=True)
cross = K.vehicle(fleet["saloon_black"], traf, "trf_cross")
P_x = K.line((-150.0, -HY / 2), (150.0, -HY / 2))
K.bake(cross, K.track(TL, {"SITUATION": (P_x, K.kin(120.0, 12.0, [(0, "cruise", 12.0)], nS)),
                           "CORRECT": (P_x, K.kin(125.0, 12.0, [(0, "cruise", 12.0)], nC))}), night=True)
# the torch beam (SITUATION 8.0 s to the end of the segment) from the police estate onto the windscreen
ws, _ = K.windscreen_point(H, TL.a("SITUATION", 9.0))
li = bpy.data.lights.new("torch", "SPOT")
li.spot_size, li.spot_blend, li.color = math.radians(14), 0.3, (1.0, 0.95, 0.85)
torch = bpy.data.objects.new("torch", li)
env.objects.link(torch)
torch.location = (XL + 0.4, ws.y - 0.3, 1.45)
torch.rotation_euler = K.stage.look_rot(Vector(torch.location), ws)
for fr, e in ((1, 0.0), (f("SITUATION", 7.95), 0.0), (f("SITUATION", 8.0), 160.0), (f("SITUATION", 9.95), 160.0),
              (f("SITUATION", 10.0), 0.0)):
    li.energy = e
    li.keyframe_insert("energy", frame=fr)

# ------------------------------------------------------------------ the cockpit: the hero's own modelled interior
# a5cockpit (QA r14 #1): the studio cockpit (torus wheel, box dash, blank dials) is gone. Every in-car shot is filmed
# inside the hero at the red light: kit/inserts.py cabin (dashboard with the binnacle cowl, fascia with vents and the
# centre stack, A-pillars, roof lining, mirror, door trims, three-spoke wheel with the airbag pad, no badge), a real
# instrument cluster (rev counter and speedometer with numerals, ticks and needles, the start-stop lamp between them),
# the street and the signal through the windscreen. The shell is invisible to the camera in those shots only.
import inserts as IN  # noqa: E402
import stage  # noqa: E402

IN.setup(K.ASSETS)
CAB = [(TL.a("HOOK"), TL.a("HOOK", 1.4)), (TL.a("SITUATION", 3.0), TL.a("SITUATION", 6.5)),
       (TL.a("RULE"), TL.a("COST")), (TL.a("CORRECT"), TL.a("CORRECT", 3.0))]
WS_TOP, WS_BOT, KH = IN.windscreen(H)
YB, ZB = WS_BOT.y, WS_BOT.z
DX = -KH["W"] * 0.42                                 # the driver's axis (left-hand drive)
CC, ROOT = H["coll"], H["coll"].objects[H["name"]]
OFF_T = TL.a("RULE", 5.55)        # ignition off (QA r14 #2): dark before "Only when you switch it fully off" (5.7)
IN.body_off_camera(H, CAB)
IN.cabin_light(H, energy=1.0)     # made before cabin() so it keeps these lights; re-tinted for the night below
IN.cabin(H, dash=(0.075, 0.073, 0.072), trim=(0.11, 0.108, 0.105))   # rev 2: darker plastics at night
_scr = bpy.data.materials.get(H["name"] + "_cab_screen")
if _scr is not None:                                   # rev 2: the blank centre screen glowed light blue
    _scr.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 0.12


def in_cab(t):
    return any(a - 1e-6 <= t < b - 1e-6 for a, b in CAB)


def ns_red(t):
    """The hero's signal shows red (or red and yellow) at time t (the NS keys above)."""
    return t < TL.a("SITUATION", 9.8) or TL.a("RULE") <= t < TL.a("CORRECT", 5.0)


def key_steps(idb, path, fn, interp="CONSTANT"):
    """Key idb.path to fn(t) at every frame where the value changes."""
    prev = None
    for fr in range(1, N + 1):
        v = fn((fr - 1) / FPS)
        if v != prev:
            if prev is not None and interp == "LINEAR":
                setattr(idb, path, prev)
                idb.keyframe_insert(path, frame=fr - 1)
            setattr(idb, path, v)
            idb.keyframe_insert(path, frame=fr)
            prev = v
    for fc in stage.fcurves(idb):
        for kp in fc.keyframe_points:
            kp.interpolation = interp


# night light in the cabin, only while the camera is inside (no glowing car in the exterior shots): a dim warm-white
# street-lamp spill under the roof behind the driver and through the driver's window, a cool night-sky fill from the
# top of the windscreen, and the red of the signal from the upper right of the windscreen while it shows red
for nm, col, e in (("_cabin_fill", (1.0, 0.9, 0.78), 0.7), ("_cabin_sky", (0.55, 0.65, 1.0), 0.9)):
    li = CC.objects[H["name"] + nm].data
    li.color = col
    key_steps(li, "energy", lambda t, e=e: e if in_cab(t) else 0.0)


def cab_light(name, loc, aim, size, col, fn):
    li = bpy.data.lights.new(name, "AREA")
    li.shape, li.size, li.size_y, li.color = "RECTANGLE", size[0], size[1], col
    o = bpy.data.objects.new(name, li)
    CC.objects.link(o)
    o.parent = ROOT
    o.location = loc
    o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    key_steps(li, "energy", fn)


cab_light("cab_signal_red", (KH["W"] * 0.62, YB - 0.5, WS_TOP.z - 0.12), (DX, YB - 0.75, ZB - 0.12), (0.35, 0.12),
          (1.0, 0.05, 0.025), lambda t: (0.0 if not (in_cab(t) and ns_red(t)) else
                                         (1.5 if t >= TL.a("CORRECT") else 3.5)))
cab_light("cab_street", (-KH["W"] * 0.86, YB - 1.1, ZB + 0.22), (DX + 0.2, YB - 0.7, ZB - 0.2), (0.5, 0.3),
          (0.92, 0.9, 0.84), lambda t: 0.7 if in_cab(t) else 0.0)


# ------------------------------------------------------------------ instrument cluster
def lit_mat(name, base, glow, rough=0.45):
    """Printed or lamp surface: base colour unlit, glowing only through the keyed emission strength (QA r14 #2: the
    old dial print was its own bright base colour, so switching the emission off changed nothing on screen)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*base, 1)
    p.inputs["Emission Color"].default_value = (*glow, 1)
    p.inputs["Emission Strength"].default_value = 0.0
    p.inputs["Roughness"].default_value = rough
    return m


def flat(name, polys, mat, parent, z):
    verts, faces = [], []
    for pts in polys:
        b = len(verts)
        verts += [(x, y, z) for x, y in pts]
        faces.append(tuple(range(b, b + len(pts))))
    o = W.mesh_obj(name, verts, faces, mat, CC)
    o.parent = parent
    return o


def disc(cx, cy, r, n=48):
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def arc(cx, cy, r0, r1, a0, a1, n):
    out = []
    for k in range(n):
        u0, u1 = a0 + (a1 - a0) * k / n, a0 + (a1 - a0) * (k + 1) / n
        out.append([(cx + r0 * math.cos(u0), cy + r0 * math.sin(u0)), (cx + r1 * math.cos(u0), cy + r1 * math.sin(u0)),
                    (cx + r1 * math.cos(u1), cy + r1 * math.sin(u1)), (cx + r0 * math.cos(u1), cy + r0 * math.sin(u1))])
    return out


def radial(cx, a, r0, r1, w):
    c, s, nx, ny = math.cos(a), math.sin(a), -math.sin(a) * w / 2, math.cos(a) * w / 2
    return [(cx + r0 * c + nx, r0 * s + ny), (cx + r0 * c - nx, r0 * s - ny), (cx + r1 * c - nx, r1 * s - ny),
            (cx + r1 * c + nx, r1 * s + ny)]


def txt(name, body, size, mat, parent, x, y, z):
    o = W.text_obj(name, body, size, mat, CC, "CENTER", "CENTER", 0.0, font=IN.font("din"))
    o.parent = parent
    o.location = (x, y, z)
    return o


def bx(name, loc, size, mat, parent, bevel=0.0):
    o = TN.box(name, CC, (0, 0, 0), size, mat, bevel=bevel)
    o.parent = parent
    o.location = loc
    return o


G0 = Vector((DX, YB - 0.42, ZB - 0.02))
G_ROT = math.radians(72)               # the dial faces lean back towards the driver (as inserts.cluster)
cl = K.empty("cl20", CC)
cl.parent = ROOT
cl.location, cl.rotation_euler = G0, (G_ROT, 0, 0)
dash_m = bpy.data.materials.get(H["name"] + "_cab_dashm") or W.principled("cl20_hoodm", (0.13, 0.125, 0.12), 0.7)
chrome = W.principled("cl20_chrome", (0.72, 0.73, 0.75), 0.22, metal=1.0)
dark = W.principled("cl20_dark", (0.05, 0.05, 0.055), 0.35, metal=0.6)
M = dict(ink=lit_mat("cl20_ink", (0.2, 0.2, 0.21), (0.95, 0.96, 1.0)),
         label=lit_mat("cl20_label", (0.12, 0.12, 0.13), (0.7, 0.76, 0.85)),
         redz=lit_mat("cl20_red", (0.12, 0.02, 0.02), (1.0, 0.1, 0.04)),
         ring=lit_mat("cl20_ring", (0.04, 0.045, 0.05), (0.45, 0.68, 1.0)),
         needle=lit_mat("cl20_needle", (0.2, 0.05, 0.02), (1.0, 0.28, 0.03), 0.3),
         lcd=lit_mat("cl20_lcd", (0.006, 0.007, 0.01), (0.05, 0.09, 0.15), 0.15),
         seg=lit_mat("cl20_seg", (0.1, 0.1, 0.11), (0.85, 0.9, 1.0)),
         btn=lit_mat("cl20_btn", (0.08, 0.05, 0.01), (1.0, 0.5, 0.08)))
ON = dict(ink=2.4, label=1.3, redz=2.6, ring=0.9, needle=3.4, lcd=0.12, seg=2.0, btn=2.2)
lamp_m = lit_mat("cl20_autostop", (0.01, 0.025, 0.012), (0.15, 1.0, 0.35))
# face and binnacle: a black D-shaped panel in a curved tunnel hood (soft-touch dark plastic) that replaces the
# cabin's flat cowl, a trim strip under it; the wheel gets a padded leather rim and a dark airbag pad
for o in CC.objects:
    if o.name.split(".")[0] in (H["name"] + "_cab_cowl", H["name"] + "_cab_cowl_side", H["name"] + "_cab_rim"):
        o.hide_render = True
soft = K.F.material("cab20_soft", (0.022, 0.022, 0.024), rough=0.62, var=0.12, scale=220.0)
FA, FB, FY = 0.205, 0.165, -0.07                       # face: half-ellipse over the dials, flat bottom at FY
face = [(FA * math.cos(math.pi * k / 48), FY + FB * math.sin(math.pi * k / 48)) for k in range(49)]
flat("cl20_face", [face], W.principled("cl20_facem", (0.006, 0.006, 0.008), 0.4), cl, 0.0)
hv, hf = [], []
NH = 48
for k in range(NH + 1):
    th = math.pi * k / NH
    c_, s_ = math.cos(th), math.sin(th)
    d = 0.018 + 0.06 * s_ ** 1.5                       # deeper over the top, shallow at the ends
    for rr, z in ((0.006, -0.004), (0.006 + 0.012 * s_, d)):
        hv.append(((FA + rr) * c_, FY + (FB + rr) * s_, z))
for k in range(NH):
    hf.append((2 * k, 2 * k + 2, 2 * k + 3, 2 * k + 1))
hood = W.mesh_obj("cl20_hood", hv, hf, soft, CC, smooth=True)
hood.parent = cl
so = hood.modifiers.new("shell", "SOLIDIFY")
so.thickness, so.offset = 0.007, 1.0
bx("cl20_lip", (0, FY - 0.006, 0.01), (2 * FA + 0.03, 0.012, 0.028), soft, cl, 0.005)
# rev 2: the fascia top under the binnacle caught the window light as a pale shelf between the cluster and the wheel
bx("cab20_shelf", (DX, YB - 0.47, ZB - 0.094), (0.46, 0.14, 0.012), soft, ROOT, 0.004)
wg = CC.objects.get(H["name"] + "_cab_wheel")
if wg is not None:
    IN._torus(CC, "cab20_rim", 0.18, 0.0215, K.F.material("cab20_leather", (0.016, 0.016, 0.018), rough=0.5, var=0.15,
                                                           scale=420.0, sheen=0.3), wg, nu=96, nv=18)
    for o in CC.objects:
        if o.name.split(".")[0] == H["name"] + "_cab_pad":
            o.data.materials.clear()
            o.data.materials.append(soft)
NEEDLE = {}
for cx, kind in ((-0.095, "rpm"), (0.095, "kmh")):
    flat("cl20_dial_" + kind, [disc(cx, 0.0, 0.06, 64)], W.principled("cl20_dialm", (0.012, 0.013, 0.016), 0.5),
         cl, 0.0006)
    bz = IN._torus(CC, "cl20_bezel_" + kind, 0.0625, 0.0032, chrome, cl, nu=72, nv=12)
    bz.location = (cx, 0.0, 0.002)
    flat("cl20_glow_" + kind, arc(cx, 0.0, 0.0566, 0.0584, 0.0, 2 * math.pi, 72), M["ring"], cl, 0.0009)
    vmax, minor, major, num, red_from, rn, size = ((8.0, 0.5, 1.0, 1, 6.5, 0.0375, 0.0115) if kind == "rpm" else
                                                   (240.0, 10.0, 20.0, 40, None, 0.0362, 0.0094))
    white, reds = [], []
    v = 0.0
    while v <= vmax + 1e-6:
        a = math.radians(225 - 270 * v / vmax)
        big = abs(v / major - round(v / major)) < 1e-6
        q = radial(cx, a, 0.0455 if big else 0.0495, 0.0548, 0.0019 if big else 0.0011)
        (reds if red_from is not None and v >= red_from - 1e-6 else white).append(q)
        v += minor
    flat("cl20_ticks_" + kind, white, M["ink"], cl, 0.0011)
    if reds:
        flat("cl20_redticks_" + kind, reds, M["redz"], cl, 0.0011)
        flat("cl20_redband_" + kind, arc(cx, 0.0, 0.0512, 0.0548, math.radians(225 - 270 * red_from / vmax),
                                         math.radians(225 - 270), 16), M["redz"], cl, 0.001)
    for vv in range(0, int(vmax) + 1, num):
        a = math.radians(225 - 270 * vv / vmax)
        txt("cl20_num_" + kind, str(vv), size, M["ink"], cl, cx + rn * math.cos(a), rn * math.sin(a), 0.0011)
    txt("cl20_unit_" + kind, "1/min x1000" if kind == "rpm" else "km/h", 0.0046 if kind == "rpm" else 0.0058,
        M["label"], cl, cx, -0.024, 0.0011)
    piv = K.empty("cl20_needle_" + kind, CC)
    piv.parent = cl
    piv.location = (cx, 0.0, 0.0024)
    flat("cl20_n_" + kind, [[(-0.012, -0.0017), (0.0525, -0.0005), (0.0525, 0.0005), (-0.012, 0.0017)]], M["needle"],
         piv, 0.0)
    flat("cl20_cap_" + kind, [disc(0.0, 0.0, 0.0078, 32)], dark, piv, 0.0012)
    NEEDLE[kind] = (piv, vmax)
# centre: a small dark display with the start-stop lamp (a plain letter A in a circular arrow, generic, no brand)
# and a fuel bar under it
flat("cl20_lcd", [W.rounded_rect(0.05, 0.088, 0.006, 4)], M["lcd"], cl, 0.0006)
A_LOC = (0.0, 0.019)
flat("cl20_auto_ring", arc(A_LOC[0], A_LOC[1], 0.0114, 0.0138, math.radians(118), math.radians(412), 40), lamp_m, cl,
     0.0012)
ae = math.radians(412)
flat("cl20_auto_head", [[(A_LOC[0] + 0.0094 * math.cos(ae), A_LOC[1] + 0.0094 * math.sin(ae)),
                         (A_LOC[0] + 0.0158 * math.cos(ae), A_LOC[1] + 0.0158 * math.sin(ae)),
                         (A_LOC[0] + 0.0126 * math.cos(ae + 0.42), A_LOC[1] + 0.0126 * math.sin(ae + 0.42))]],
     lamp_m, cl, 0.0012)
txt("cl20_auto_A", "A", 0.0158, lamp_m, cl, A_LOC[0], A_LOC[1] - 0.0004, 0.0012)
flat("cl20_fuel", [[(-0.02 + 0.0068 * k, -0.031), (-0.0152 + 0.0068 * k, -0.031), (-0.0152 + 0.0068 * k, -0.026),
                    (-0.02 + 0.0068 * k, -0.026)] for k in range(5)], M["seg"], cl, 0.0011)
flat("cl20_fuel_end", [[(-0.02 + 0.0068 * 5, -0.031), (-0.0152 + 0.0068 * 5, -0.031),
                        (-0.0152 + 0.0068 * 5, -0.026), (-0.02 + 0.0068 * 5, -0.026)]], M["label"], cl, 0.0011)
# engine start/stop button on the fascia right of the column: chrome ring, dark cap, amber ring while the ignition is on
bt = K.empty("cab20_btn", CC)
bt.parent = ROOT
bt.location, bt.rotation_euler = (DX + 0.23, YB - 0.546, ZB - 0.16), (math.radians(90), 0, 0)
IN._torus(CC, "cab20_btn_ring", 0.0195, 0.0026, chrome, bt, nu=48, nv=10)
cap = TN.cyl("cab20_btn_cap", CC, (0, 0, 0), 0.0165, 0.012, dark, verts=40, rot=(0, 0, 0))
cap.parent = bt
cap.location = (0, 0, 0.004)
flat("cab20_btn_led", arc(0.0, 0.0, 0.0118, 0.0132, 0.0, 2 * math.pi, 40), M["btn"], cap, 0.0062)
for fr, dz in ((1, 0.004), (TL.f("RULE", 5.3), 0.004), (TL.f("RULE", 5.45), 0.0), (TL.f("RULE", 5.7), 0.004)):
    cap.location.z = dz
    cap.keyframe_insert("location", index=2, frame=fr)


# the cluster tells the rule (QA r14 #2): engine running -> rev needle at idle or above, A lamp dark; auto stop (the
# car stands, start-stop switched the engine off) -> rev needle at 0, cluster lit, green A lamp; ignition fully off
# (RULE 5.55 s to the end of RULE) -> everything dark, both needles at 0
def speed_kmh(t):
    tr = H["track"]
    i = max(0, min(len(tr) - 2, int(round(t * FPS))))
    d = math.hypot(tr[i + 1][0] - tr[i][0], tr[i + 1][1] - tr[i][1])
    return 0.0 if d > 1.0 else d * FPS * 3.6


SPD = [speed_kmh((fr - 1) / FPS) for fr in range(1, N + 2)]


def standing(t, back=0.5, ahead=0.3):
    """The car has stood for `back` s and will stand for `ahead` s more (the engine restarts as the brake comes
    off). Before the first frame the hero is taken as already standing (HOOK opens at the red light)."""
    f = int(round(t * FPS))
    return all(SPD[max(0, min(N, k))] < 0.5 for k in range(f - int(back * FPS), f + int(ahead * FPS) + 1))


ign = lambda t: not (OFF_T <= t < TL.a("COST"))                     # noqa: E731
auto = lambda t: ign(t) and standing(t)                             # noqa: E731
rpm = lambda t: 0.0 if (not ign(t) or auto(t)) else round(min(3.0, 0.85 + 0.045 * SPD[int(round(t * FPS))]), 2)  # noqa
for kind, fn in (("rpm", rpm), ("kmh", lambda t: 0.0 if not ign(t) else round(SPD[int(round(t * FPS))], 1))):
    piv, vmax = NEEDLE[kind]
    cur, last = fn(0.0), None
    for fr in range(1, N + 1):
        cur += (fn((fr - 1) / FPS) - cur) * 0.3          # needle inertia: about 0.3 s to settle
        a = round(math.radians(225 - 270 * min(cur, vmax) / vmax), 4)
        if a != last:
            if last is not None and fr > 1:
                piv.rotation_euler = (0, 0, last)
                piv.keyframe_insert("rotation_euler", index=2, frame=fr - 1)
            piv.rotation_euler = (0, 0, a)
            piv.keyframe_insert("rotation_euler", index=2, frame=fr)
            last = a
    for fc in stage.fcurves(piv):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
ign_on = TL.f("COST")
f_off = int(round(OFF_T * FPS)) + 1
for k, m in M.items():
    inp = m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    for fr, v in ((1, ON[k]), (f_off, ON[k]), (f_off + 5, 0.0), (ign_on - 1, 0.0), (ign_on, ON[k])):
        inp.default_value = v
        inp.keyframe_insert("default_value", frame=fr)
    for fc in stage.fcurves(m.node_tree):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
lamp_in = lamp_m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
prev = None
for fr in range(1, N + 1):
    v = 4.2 if auto((fr - 1) / FPS) else 0.0
    if v != prev:
        lamp_in.default_value = v
        lamp_in.keyframe_insert("default_value", frame=fr)
        prev = v
for fc in stage.fcurves(lamp_m.node_tree):
    for kp in fc.keyframe_points:
        kp.interpolation = "CONSTANT"
A_CAR = G0 + Matrix.Rotation(G_ROT, 3, "X") @ Vector((A_LOC[0], A_LOC[1], 0.0012))    # the A lamp, car frame


def ui(name, root, x, z, w, h, col, emit=1.0, y=-0.0064):
    """One flat element of the phone's screen (simple shapes only: no brand, no real app UI)."""
    o = TN.box(name, env, (x, y, z), (w, 0.0004, h), jx.flat_mat("ink_" + name, col, emit=emit))
    o.parent = root
    return o


def phone(name, loc, rot, windows, mount=False, new_msg=None):
    """A plain phone (no brand): dark case, a screen with a status line, a header with a round avatar and message
    bubbles in grey and blue (a messenger-like layout of plain shapes). new_msg: (t_on, t_off) a new blue bubble pops
    in. mount: a map-like screen with a green route line and a position arrow. Screen towards -y."""
    root = K.empty(name, env, loc, rot)
    TN.box(name + "_body", env, (0, 0, 0), (0.075, 0.009, 0.155), W.principled(name + "_case", (0.05, 0.05, 0.06), 0.4),
           bevel=0.004).parent = root
    TN.box(name + "_scr", env, (0, -0.005, 0.0), (0.066, 0.002, 0.142),
           jx.flat_mat("ink_" + name + "_screen", (0.02, 0.03, 0.06) if not mount else (0.03, 0.045, 0.04), emit=0.5)).parent = root
    ui(name + "_status", root, 0.0, 0.066, 0.056, 0.003, (0.55, 0.6, 0.7), 0.6)
    if mount:
        for k, (x0, z0, x1, z1) in enumerate(((-0.033, -0.02, 0.033, -0.01), (-0.033, 0.03, 0.033, 0.045),
                                               (0.012, -0.065, 0.02, 0.062), (-0.025, -0.065, -0.012, 0.062),
                                               (-0.033, -0.045, 0.033, -0.05))):
            K.bar(f"{name}_street{k}", env, (x0, z0), (x1, z1), 0.004, jx.flat_mat(f"ink_{name}_st{k}", (0.35, 0.38, 0.4), 0.7),
                  z=-0.0064, plane="xz", parent=root)
        K.bar(name + "_route", env, (0.016, -0.05), (0.016, 0.0), 0.006, jx.flat_mat("ink_" + name + "_r", (0.1, 1.0, 0.3), 1.6),
              z=-0.0068, plane="xz", parent=root)
        K.bar(name + "_route2", env, (0.016, 0.0), (-0.0185, 0.037), 0.006, jx.flat_mat("ink_" + name + "_r", (0.1, 1.0, 0.3), 1.6),
              z=-0.0068, plane="xz", parent=root)
        ui(name + "_me", root, 0.016, -0.05, 0.008, 0.008, (0.95, 0.97, 1.0), 1.4, y=-0.0072)
        ui(name + "_turn", root, 0.0, 0.058, 0.066, 0.014, (0.08, 0.35, 0.2), 0.9, y=-0.0068)
    else:
        ui(name + "_head", root, 0.0, 0.054, 0.066, 0.016, (0.12, 0.16, 0.26), 0.8)
        av = TN.cyl(name + "_avatar", env, (-0.022, -0.0066, 0.054), 0.005, 0.0004, jx.flat_mat("ink_" + name + "_av", (0.85, 0.55, 0.3), 0.9),
                    rot=(math.pi / 2, 0, 0))
        av.parent = root
        ui(name + "_title", root, 0.004, 0.054, 0.03, 0.003, (0.75, 0.78, 0.85), 0.8, y=-0.0068)
        for k, (x, z, w, h, col) in enumerate(((-0.01, 0.028, 0.038, 0.014, (0.62, 0.65, 0.7)),
                                               (0.011, 0.006, 0.034, 0.012, (0.2, 0.48, 0.95)),
                                               (-0.008, -0.018, 0.042, 0.02, (0.62, 0.65, 0.7)))):
            ui(f"{name}_bubble{k}", root, x, z, w, h, col, 0.9)
        ui(name + "_input", root, 0.0, -0.064, 0.058, 0.007, (0.16, 0.18, 0.22), 0.7)
        if new_msg:
            nb = K.empty(name + "_newmsg", env, (0.012, 0.0, -0.043))
            nb.parent = root
            ui(name + "_bubble_new", nb, 0.0, 0.0, 0.032, 0.014, (0.2, 0.48, 0.95), 1.0)
            K.pop(nb, [new_msg])
    if windows:
        K.pop(root, windows)
    return root


def into_car(root, loc, rot):
    """Move a prop (root and children) into the hero's collection, placed in the car's frame."""
    for o in [root] + list(root.children_recursive):
        for cc in list(o.users_collection):
            cc.objects.unlink(o)
        CC.objects.link(o)
    root.parent = ROOT
    root.location, root.rotation_euler = loc, rot


def hand(ph, name):
    """The driver's right hand holding the phone (phone frame, screen to -y): the palm behind it, four fingers round
    its left edge with the tips on the bezel, the thumb up the right edge onto the screen, the wrist and the jacket
    sleeve running down towards the driver out of frame. Smooth subdivided tubes in a skin material."""
    Fg = K.F
    skin = Fg.material("drv_skin", Fg.SKIN[2], rough=0.5, sheen=0.4, var=0.06, scale=60.0)
    sleeve = Fg.material("drv_sleeve", Fg.JACKETS[2], rough=0.85, var=0.07, scale=40.0)
    cg = Fg.Cage()

    def tube(pts, r, mat, s0=1.0, s1=1.0, rv=None, n=10):
        pts = Fg.bezier_chain(pts, 4) if len(pts) > 2 else [Vector(p) for p in pts]
        sc = [s0 + (s1 - s0) * i / (len(pts) - 1) for i in range(len(pts))]
        Fg.sweep(cg, pts, Fg.circle(r, n, rv), mat, scale=sc, n0=(1, 0, 0))
    # palm hidden behind the right half of the phone, the heel showing under its bottom edge (rev 2: the rev 1 palm
    # stuck out below the phone like a flat tongue and the forearm ended in a bare skin blob)
    tube([(0.012, 0.016, -0.02), (0.015, 0.017, -0.06), (0.02, 0.012, -0.092)], 0.03, skin, 1.0, 0.92, rv=0.0125)
    tube([(0.02, 0.012, -0.085), (0.028, 0.0, -0.118), (0.042, -0.03, -0.165), (0.06, -0.075, -0.235)], 0.024, skin,
         1.0, 1.12, rv=0.019)
    for z0, r in ((-0.009, 0.0088), (-0.027, 0.0092), (-0.045, 0.0088), (-0.062, 0.0077)):
        tube([(0.006, 0.022, z0 - 0.003), (-0.028, 0.0165, z0), (-0.0445, 0.0095, z0 + 0.001), (-0.0472, -0.0015, z0 + 0.0015),
              (-0.0405, -0.0078, z0 + 0.0015)], r, skin, 1.08, 0.86, rv=r * 0.9)
    tube([(0.032, 0.016, -0.086), (0.0465, 0.006, -0.068), (0.046, -0.0045, -0.05), (0.0385, -0.0094, -0.038)], 0.0102,
         skin, 1.15, 0.85)
    tube([(0.046, -0.04, -0.18), (0.064, -0.085, -0.25), (0.09, -0.15, -0.36)], 0.032, sleeve, 1.0, 1.2, rv=0.03)
    o = cg.build("drv_hand_" + name, CC)
    o.parent = ph
    sub = o.modifiers.new("smooth", "SUBSURF")
    sub.levels, sub.render_levels = 1, 2
    return o


# the phone in his right hand over the wheel (HOOK and SITUATION; put away before RULE)
P_HAND = Vector((DX + 0.075, YB - 0.87, ZB - 0.035))
ph_hand = phone("phone_hand", (0, 0, 0), (0, 0, 0), None, new_msg=(TL.a("SITUATION", 3.9), TL.a("SITUATION", 6.5)))
hand(ph_hand, "hand")
into_car(ph_hand, P_HAND, (math.radians(-34), 0, math.radians(-7)))
K.show_between(ph_hand, TL.a("HOOK"), TL.a("RULE"))
# the phone in a dash mount (CORRECT): a cradle with side grips and a lip on a short arm, suction foot on the dash top
P_MOUNT = Vector((-0.06, YB - 0.36, ZB + 0.068))
ph_mount = phone("phone_mount", (0, 0, 0), (0, 0, 0), None, mount=True)
into_car(ph_mount, P_MOUNT, (math.radians(-14), 0, math.radians(-14)))
K.show_between(ph_mount, TL.a("COST"), TL.a("END"))
mount_m = W.principled("mount20_black", (0.015, 0.015, 0.017), 0.55)
mt = K.empty("mount20", CC)
mt.parent = ROOT
mt.location, mt.rotation_euler = P_MOUNT, (math.radians(-14), 0, math.radians(-14))
bx("mount20_back", (0, 0.0075, -0.01), (0.062, 0.006, 0.11), mount_m, mt, 0.003)
bx("mount20_lip", (0, -0.002, -0.083), (0.07, 0.022, 0.008), mount_m, mt, 0.003)
for sx in (-1, 1):
    bx("mount20_grip", (sx * 0.0415, -0.001, 0.012), (0.008, 0.02, 0.034), mount_m, mt, 0.003)
    bx("mount20_arm_x", (sx * 0.02, 0.0075, 0.012), (0.04, 0.005, 0.008), mount_m, mt, 0.002)
foot = Vector((P_MOUNT.x + 0.004, P_MOUNT.y + 0.06, ZB - 0.03))
IN._beam(CC, "mount20_arm", tuple(P_MOUNT + Vector((0.0, 0.016, -0.01))), tuple(foot + Vector((0, 0, 0.012))), 0.014,
         0.014, mount_m, ROOT, bevel=0.005)
fo = TN.cyl("mount20_foot", CC, (0, 0, 0), 0.03, 0.012, mount_m, verts=40, rot=(0, 0, 0))
fo.parent = ROOT
fo.location = tuple(foot + Vector((0, 0, 0.006)))
for o in (mt, CC.objects["mount20_arm"], fo):
    K.show_between(o, TL.a("COST"), TL.a("END"))       # rev 2: no empty cradle on the dash while he holds the phone
IN.adopt(H)
yH = Y_LINE - 0.4 - H["L"] / 2
# COST opens on the street shot of the two cars at the red light (QA r18: the notepad close-up on the roof read as a
# primitive prop scene, so it is gone, with its torch)
FWD, RIGHT, UPZ = Vector((0.0, 1.0, 0.0)), Vector((1.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0))

# ------------------------------------------------------------------ cameras
sh = K.Shots(N)                  # frame-exact cuts (ep10_za5kit.Shots)
cab = IN.cabin_cam(H["obj"], H)          # (t, eye, look) in the car's frame -> world, following the baked hero
# HOOK / SITUATION: the driver's view down at the phone in his hand, the lit cluster (green A, rev needle at 0) above
# it and the street through the windscreen at the top
ph = lambda t: cab(t, (DX + 0.03, YB - 1.17, ZB + 0.2), (DX + 0.05, YB - 0.73, ZB - 0.025))  # noqa: E731
ph2 = lambda t: cab(t, (DX + 0.04, YB - 1.13, ZB + 0.18), (DX + 0.065, YB - 0.79, ZB - 0.03))  # noqa: E731
# RULE: the cluster from the driver's seat, a slow push straight at the start-stop lamp (it keeps its pixel, so the
# ring drawn round it in post_ep20.py stays on it: A_PIXEL below)
E_RULE = Vector((DX + 0.02, YB - 1.15, ZB + 0.2))
eye = lambda t: cab(t, A_CAR + (E_RULE - A_CAR) * (1.0 - 0.07 * (t - TL.a("RULE")) / 8.0), A_CAR)  # noqa: E731
# CORRECT: the phone in the dash mount, the red signal ahead through the windscreen while the hero rolls up to it
mnt = lambda t: cab(t, (DX + 0.06, YB - 1.16, ZB + 0.21), tuple(P_MOUNT + Vector((0.0, 0.0, -0.005))))  # noqa: E731
t0 = TL.a("HOOK")
sh.add("H_phone", 28, t0, t0 + 1.4, ph)
sh.add("H_drone", 24, t0 + 1.4, TL.a("SITUATION"), lambda t: (Vector((-8.0, yH - 14.0, 9.0 + 6.0 * (t - t0 - 1.4))),
                                                            Vector((3.0, yH + 2.0, 0.0))))
t0 = TL.a("SITUATION")
sh.add("S_chase", 24, t0, t0 + 3.0, lambda t: (K.at(H, t) + Vector((-0.6, -6.5, 1.6)), K.at(H, t) + Vector((0.3, 10.0, 0.8))))
sh.add("S_phone", 34, t0 + 3.0, t0 + 6.5, ph2)
sh.add("S_drone", 24, t0 + 6.5, TL.a("RULE"), lambda t: (Vector((-9.0, yH - 11.0, 8.0)), Vector((3.0, yH + 1.0, 0.6))))
t0 = TL.a("RULE")
sh.add("R_dash", 34, t0, TL.a("COST"), eye)
t0 = TL.a("COST")
# the fine over the two cars at the red light, seen from behind between the lanes (rev 2: a top view of the dark street)
sh.add("C_rear", 28, t0, TL.a("CORRECT"), lambda t: (Vector((0.2, yH - 8.6 + 0.25 * (t - t0 - 2.2), 2.3)),
                                                         Vector((3.3, yH + 2.5, 0.9))))
t0 = TL.a("CORRECT")
sh.add("K_mount", 34, t0, t0 + 3.0, mnt)
sh.add("K_drone", 24, t0 + 3.0, TL.a("END"), lambda t: (Vector((-10.0, yH - 16.0, 11.0)), Vector((3.0, yH + 6.0, 0.0))))
K.end_card(T, env, sh, TL.a("END"), TL.T)
# pixel of the start-stop lamp in R_dash (1080 x 1920, for post_ep20.gfx)
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
for _t in (TL.a("RULE", 0.3), TL.a("RULE", 7.9)):
    _f = int(round(_t * FPS)) + 1
    _c = sh.camera_at(_f)
    bpy.context.scene.frame_set(_f)
    bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y = 1080, 1920
    _p, _ = cab(_t, A_CAR, A_CAR)
    _v = world_to_camera_view(bpy.context.scene, _c, _p)
    print("A_PIXEL", _f, _c.name, round(_v.x * 1080, 1), round((1 - _v.y) * 1920, 1), flush=True)
K.light(az=230.0, elev=20.0, energy=4.0, exposure=0.3)
K.finish(sh, TL, wx=[(0.0, TL.a("END"), "night", 1.0)], haze=(0.25, 0.28, 0.36))
