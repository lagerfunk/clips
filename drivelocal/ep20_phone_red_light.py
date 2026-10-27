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
sv_k = K.hold(s_stop - 20.0, int(2.6 * FPS))
sv_k += K.brake(s_stop, 5.0, 0.0, 0.6, int(1.4 * FPS)) + K.hold(s_stop, int(1.5 * FPS))
sv_k += K.kin(s_stop, 0.0, [(0, "cruise", 6.0)], nC - len(sv_k), a_acc=2.0)
K.bake(H, K.track(TL, {"HOOK": (P_r, stop(TL.n("HOOK"))), "SITUATION": (P_r, K.brake(s_stop, 11.1, 0.0, 2.5, nS)),
                       "COST": (P_r, stop(TL.n("COST"))), "CORRECT": (P_r, sv_k)}, H["L"]), night=True)
pol = K.vehicle(K.V.car("estate", (0.8, 0.81, 0.82), "police", "QX PD 120", police=True, c=lib), traf, "trf_police")
s_pol = s_stop + 0.3
nH = TL.n("HOOK")
K.bake(pol, K.track(TL, {"HOOK": (P_l, K.brake(s_pol, 6.0, 1.3, 2.1, nH)),
                         "SITUATION": (P_l, K.brake(s_pol, 8.0, 3.4, 6.8, nS), dict(ind=[("R", 0.0, 2.0)])),
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

# ------------------------------------------------------------------ the studio: dashboard, wheel, phones, button
D0 = Vector((80.0, 0.0, 300.0))
dark = K.F.material("car_plastic_dash", (0.03, 0.03, 0.035), rough=0.62, var=0.08, scale=60.0)
TN.box("dash_board", env, (D0.x, D0.y + 0.3, D0.z - 0.25), (1.7, 0.7, 0.2), dark, bevel=0.03)
TN.box("dash_hood", env, (D0.x, D0.y + 0.12, D0.z - 0.015), (0.62, 0.22, 0.05), dark, bevel=0.02)
TN.box("dash_cluster", env, (D0.x, D0.y + 0.04, D0.z - 0.12), (0.52, 0.04, 0.2),
       K.F.material("car_plastic_bezel", (0.012, 0.012, 0.016), rough=0.35, var=0.03), bevel=0.012)
glow = [jx.flat_mat(f"dash_glow{k}", c, emit=2.0) for k, c in enumerate(((0.9, 0.95, 1.0), (0.15, 0.95, 0.35)))]
for k, x in enumerate((-0.13, 0.13)):
    TN.cyl(f"dial{k}", env, (D0.x + x, D0.y + 0.018, D0.z - 0.12), 0.075, 0.004, W.principled(f"dialf{k}", (0.02, 0.02, 0.03), 0.4),
           verts=40, rot=(math.pi / 2, 0, 0))
    K.bar(f"needle{k}", env, (D0.x + x, D0.z - 0.12), (D0.x + x - 0.055, D0.z - 0.155 if k == 0 else D0.z - 0.08), 0.006,
          glow[0], z=D0.y + 0.014, plane="xz")
A = W.text_obj("autostop_A", "A", 0.034, glow[1], env, "CENTER", "CENTER", 0.0)
A.location, A.rotation_euler = (D0.x, D0.y + 0.015, D0.z - 0.12), (math.pi / 2, 0, 0)
for k in range(24):
    a0, a1 = 2 * math.pi * k / 24, 2 * math.pi * (k + 0.7) / 24
    K.bar(f"autostop_ring{k}", env, (D0.x + 0.028 * math.cos(a0), D0.z - 0.12 + 0.028 * math.sin(a0)),
          (D0.x + 0.028 * math.cos(a1), D0.z - 0.12 + 0.028 * math.sin(a1)), 0.004, glow[1], z=D0.y + 0.015, plane="xz")
off = f("RULE", 3.9)
for m in glow:
    jx.key_emission(m, [(1, 2.0), (off - 1, 2.0), (off, 0.0), (f("COST"), 2.0)])
bpy.ops.mesh.primitive_torus_add(major_radius=0.19, minor_radius=0.019, major_segments=72, minor_segments=18,
                                 location=(D0.x, D0.y - 0.2, D0.z - 0.16), rotation=(math.radians(72), 0, 0))
wheel = bpy.context.active_object
wheel.data.materials.append(K.F.material("car_plastic_wheel", (0.02, 0.02, 0.022), rough=0.5, var=0.05, scale=90.0))
bpy.ops.object.shade_smooth()
hub = TN.cyl("wheel_hub", env, (0, 0, 0), 0.055, 0.04, dark, verts=40, rot=(0, 0, 0))
hub.parent = wheel
for k, a in enumerate((math.pi / 2, math.pi * 7 / 6, -math.pi / 6)):
    sp = TN.box(f"wheel_spoke{k}", env, (0.12 * math.cos(a), 0.12 * math.sin(a), 0.0), (0.14, 0.03, 0.012), dark, bevel=0.005)
    sp.rotation_euler = (0, 0, a)
    sp.parent = wheel
btn = TN.cyl("engine_btn", env, (D0.x + 0.33, D0.y + 0.02, D0.z - 0.17), 0.022, 0.02, W.principled("btn", (0.6, 0.06, 0.04), 0.3),
             rot=(math.pi / 2, 0, 0))
for fr, dy in ((1, 0.0), (off - 3, 0.0), (off, 0.008), (off + 4, 0.0)):
    btn.location.y = D0.y + 0.02 + dy
    btn.keyframe_insert("location", frame=fr)


def ui(name, root, x, z, w, h, col, emit=1.0, y=-0.0064):
    """One flat element of the phone's screen (simple shapes only: no brand, no real app UI)."""
    o = TN.box(name, env, (x, y, z), (w, 0.0004, h), jx.flat_mat("ink_" + name, col, emit=emit))
    o.parent = root
    return o


def phone(name, loc, rot, windows, mount=False, new_msg=None):
    """A plain phone (no brand): dark case, a screen with a status line, a header with a round avatar and message
    bubbles in grey and blue (a messenger-like layout of plain shapes). new_msg: (t_on, t_off) a new blue bubble pops
    in. mount: a map-like screen with a green route line and the dash clamp."""
    root = K.empty(name, env, loc, rot)
    TN.box(name + "_body", env, (0, 0, 0), (0.075, 0.009, 0.155), W.principled(name + "_case", (0.05, 0.05, 0.06), 0.4)).parent = root
    TN.box(name + "_scr", env, (0, -0.005, 0.0), (0.066, 0.002, 0.142),
           jx.flat_mat("ink_" + name + "_screen", (0.02, 0.03, 0.06) if not mount else (0.06, 0.09, 0.08), emit=0.5)).parent = root
    ui(name + "_status", root, 0.0, 0.066, 0.056, 0.003, (0.55, 0.6, 0.7), 0.6)
    if mount:
        for k, (x0, z0, x1, z1) in enumerate(((-0.03, -0.02, 0.03, -0.01), (-0.02, 0.03, 0.025, 0.045),
                                               (0.01, -0.06, 0.02, 0.06))):
            K.bar(f"{name}_street{k}", env, (x0, z0), (x1, z1), 0.004, jx.flat_mat(f"ink_{name}_st{k}", (0.35, 0.38, 0.4), 0.7),
                  z=-0.0064, plane="xz", parent=root)
        K.bar(name + "_route", env, (-0.02, -0.05), (0.015, 0.05), 0.006, jx.flat_mat("ink_" + name + "_r", (0.1, 1.0, 0.3), 1.6),
              z=-0.0068, plane="xz", parent=root)
        TN.box(name + "_clamp", env, (0, 0.012, -0.06), (0.09, 0.02, 0.025), W.principled(name + "_cl", (0.1, 0.1, 0.1), 0.5)).parent = root
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
    K.pop(root, windows)
    return root


phone("phone_hand", (D0.x + 0.06, D0.y - 0.36, D0.z - 0.05), (math.radians(-18), 0, math.radians(8)),
      [(TL.a("HOOK", 0.0), TL.a("HOOK", 1.4)), (TL.a("SITUATION", 3.0), TL.a("SITUATION", 6.5))],
      new_msg=(TL.a("SITUATION", 3.9), TL.a("SITUATION", 6.5)))
phone("phone_mount", (D0.x - 0.36, D0.y + 0.02, D0.z - 0.02), (0, 0, 0), [(TL.a("CORRECT", 0.0), TL.a("CORRECT", 3.0))], True)
K.area("dash_key", env, (D0.x - 0.4, D0.y - 0.9, D0.z + 0.5), 60.0, 1.0, (math.radians(55), 0, math.radians(-20)),
       col=(0.75, 0.82, 1.0))
yH = Y_LINE - 0.4 - H["L"] / 2
# COST: the officer's notepad lies on the hero's roof on the driver's side (the police estate stands in the next lane),
# lit by the officer's torch (rev 2: a white sheet floating in a studio under its own key light came out pure white)
FWD, RIGHT, UPZ = Vector((0.0, 1.0, 0.0)), Vector((1.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0))
Mh = K.car_matrix(H, XR, yH, math.pi / 2)
pp, pn = K.on_body(H, Mh, -0.15, -0.36)
pad_c = pp + pn * 0.012
K.show_between(K.pad(env, tuple(pad_c), TL.a("COST", 0.4), TL.a("COST", 2.1), rot=K.lay_rot(pn, RIGHT + FWD * 0.3)),
               TL.a("COST"), TL.a("CORRECT"))
tl = bpy.data.lights.new("pad_torch", "SPOT")
tl.spot_size, tl.spot_blend, tl.color, tl.shadow_soft_size = math.radians(34), 0.6, (1.0, 0.93, 0.8), 0.03
pt = bpy.data.objects.new("pad_torch", tl)
env.objects.link(pt)
pt.location = pad_c - RIGHT * 0.55 - FWD * 0.25 + UPZ * 0.75
pt.rotation_euler = K.stage.look_rot(Vector(pt.location), pad_c)
for fr, e in ((1, 0.0), (f("COST") - 1, 0.0), (f("COST"), 14.0), (f("COST", 2.2), 14.0), (f("COST", 2.2) + 1, 0.0)):
    tl.energy = e
    tl.keyframe_insert("energy", frame=fr)

# ------------------------------------------------------------------ cameras
sh = K.Shots(N)                  # frame-exact cuts (ep10_za5kit.Shots)
eye = lambda t: (Vector((D0.x + 0.02, D0.y - 0.62, D0.z + 0.06)), Vector((D0.x + 0.03, D0.y, D0.z - 0.12)))  # noqa: E731
ph = lambda t: (Vector((D0.x + 0.03, D0.y - 0.72, D0.z + 0.05)), Vector((D0.x + 0.06, D0.y - 0.36, D0.z - 0.05)))  # noqa: E731
t0 = TL.a("HOOK")
sh.add("H_phone", 32, t0, t0 + 1.4, ph)
sh.add("H_drone", 24, t0 + 1.4, TL.a("SITUATION"), lambda t: (Vector((-8.0, yH - 14.0, 9.0 + 6.0 * (t - t0 - 1.4))),
                                                            Vector((3.0, yH + 2.0, 0.0))))
t0 = TL.a("SITUATION")
sh.add("S_chase", 24, t0, t0 + 3.0, lambda t: (K.at(H, t) + Vector((-0.6, -6.5, 1.6)), K.at(H, t) + Vector((0.3, 10.0, 0.8))))
sh.add("S_phone", 40, t0 + 3.0, t0 + 6.5, ph)
sh.add("S_drone", 24, t0 + 6.5, TL.a("RULE"), lambda t: (Vector((-9.0, yH - 11.0, 8.0)), Vector((3.0, yH + 1.0, 0.6))))
t0 = TL.a("RULE")
sh.add("R_dash", 34, t0, TL.a("COST"), eye)
t0 = TL.a("COST")
sh.add("C_pad", 34, t0, t0 + 2.2, lambda t: (pad_c - RIGHT * 0.42 - FWD * (0.36 - 0.03 * (t - t0)) + UPZ * 0.46,
                                             pad_c + FWD * 0.05))
# the fine over the two cars at the red light, seen from behind between the lanes (rev 2: a top view of the dark street)
sh.add("C_rear", 28, t0 + 2.2, TL.a("CORRECT"), lambda t: (Vector((0.2, yH - 8.6 + 0.25 * (t - t0 - 2.2), 2.3)),
                                                         Vector((3.3, yH + 2.5, 0.9))))
t0 = TL.a("CORRECT")
sh.add("K_mount", 36, t0, t0 + 3.0, lambda t: (Vector((D0.x - 0.2, D0.y - 0.55, D0.z + 0.05)), Vector((D0.x - 0.34, D0.y, D0.z - 0.03))))
sh.add("K_drone", 24, t0 + 3.0, TL.a("END"), lambda t: (Vector((-10.0, yH - 16.0, 11.0)), Vector((3.0, yH + 6.0, 0.0))))
K.end_card(T, env, sh, TL.a("END"), TL.T)
K.light(az=230.0, elev=20.0, energy=4.0, exposure=0.3)
K.finish(sh, TL, wx=[(0.0, TL.a("END"), "night", 1.0)], haze=(0.25, 0.28, 0.36))
