"""Drive Like a Local #26, Germany (standard): the parking disc. Set the arrival time rounded UP to the next half
hour (12:03 becomes 12:30) and put the disc behind the windscreen (StVO 13 (2), Zeichen 314 with Zusatzzeichen
1040-32). 9:16, 30 fps, no voice.
Set: the plain town stage with a 9 m high street (north arm), marked parallel bays on both kerbs (kit/parking.py),
Zeichen 314 + 1040-32 and 283 from Commons at the row start. Silver rental hatchback (hero, see-through glass and a
cabin, seen through the windscreen from above the bonnet), the parking disc as the kit's model of Bild 318
(parking.parkscheibe source="model", the dial turns: 12:03 and 12:30) on the dashboard and as a close-up prop on a
dark dashboard, a parking attendant (kit/figures.py, no crest), her notepad on the bonnet, a plain yellow ticket.
Teaching marks are ASS drawings (post_ep26.py). Day.
Canonical timeline (English order; finish_ep cuts each language's order from ep26_edit.json):
HOOK 0-2.2, SITUATION 2.2-12.2, RULE 12.2-19.7, COST 19.7-24.2, CORRECT 24.2-30.7, END 30.7-33.4.
Run: python ep26_parking_disc.py OUTDIR --frames 1-1002 --res 540 --samples 8 --assets ASSETS [--stills 30,400]
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "ep10")]
import ep10_za5kit as K  # noqa: E402
from ep10_za5kit import bpy, Vector, SG, TN, TP, TS, FPS, UP_N  # noqa: E402
import parking as PK  # noqa: E402

TL = K.Timeline([("HOOK", 2.2), ("SITUATION", 10.0), ("RULE", 7.5), ("COST", 4.5), ("CORRECT", 6.5), ("END", 2.7)])
N = TL.N
HX = 4.5
S = TS.build(K.ASSETS, "plain", seed=26, hx=HX, hy=3.0, parked=False, heroes=[
    ("hatch", (0.62, 0.64, 0.67), "hero", "JX PS 318", 0.5)])
SG.setup(K.ASSETS)
T, env, lib, traf, fleet, J = S["T"], S["env"], S["lib"], S["traffic"], S["fleet"], S["J"]
H = S["heroes"]["hero"]
cars = {k: v for k, v in fleet.items() if not k.startswith("van")}
stN = TP.arm(J, "N")
NB = 7
LEN = 2 * PK.BAY_L_END + (NB - 2) * PK.BAY_L
PS = PK.street(T, env, stN, cars, n=NB, sides=(+1, -1), s0={+1: 14.0, -1: 14.0 + LEN}, skip={(+1, 3)}, seed=11,
               signs=True)
rowR = PS["rows"][+1]
pB, yawB = PK.bay_pose(rowR, 3)
H["yaw0"] = yawB
# SITUATION: the last seconds of a reverse parallel parking manoeuvre (parked at 2.0 s), then he stays
full = PK.parallel_track(PK.parallel_paths(rowR, 3, approach=10.0), 600, v_app=3.4, t_stop=0.5, v_rev=1.5, a=1.6)
e = max(i for i, d in enumerate(full) if abs(d["v"]) > 0.01)
sit = full[max(0, e - 60): e + 1]
park = [dict(x=pB.x, y=pB.y, yaw=yawB, v=0.0, ind=None)]
K.bake(H, K.track(TL, {"HOOK": park, "SITUATION": sit, "RULE": park, "COST": park, "CORRECT": park}, H["L"]))

# ------------------------------------------------------------------ the discs: on the dashboard and the close-up prop
# Both discs are the kit's model of Bild 318 (parking.parkscheibe source="model": card, window, pointer and the
# Commons Zeichen 314 in the P field; the dial turns). The Commons file of Zeichen 318 can only show 18:00, which
# contradicted "Arrive 12:03? Set 12:30" in rev 2 (orchestrator, 27 Oct: the turning model for every shot that shows
# the dial). Dial times: the dash disc 11:36 turning to 12:03 while "he sets the exact arrival minute", 12:30 from the
# RULE on; the close-up 12:03 turning UP to 12:30 in RULE and again in CORRECT.
EXACT, SET = 12 + 3 / 60, PK.round_up_half_hour(12 + 3 / 60)        # 12:03 -> 12:30
f = TL.f
PK.see_through(H)
dash = PK.parkscheibe(lib, EXACT, name="disc_dash", source="model")
PK.windscreen_mount(H, dash)
print("ADOPTED", K.adopt(H))      # the cabin parts and the disc join the instanced body collection (else unseen)
for fr, h in ((1, 11.6), (f("SITUATION", 3.6), 11.6), (f("SITUATION", 4.5), EXACT), (f("RULE") - 1, EXACT),
              (f("RULE"), SET), (f("COST") - 1, SET), (f("COST"), EXACT), (f("CORRECT") - 1, EXACT),
              (f("CORRECT"), SET)):
    dash["set_time"](fr, h)                     # the ticketed car shows 12:03 (HOOK to SITUATION, COST)
DZ = Vector((40.0, 0.0, 300.0))
big = PK.parkscheibe(env, EXACT, name="disc_big", source="model")
big["root"].location, big["root"].scale = tuple(DZ), (6.0, 6.0, 6.0)
big["root"].rotation_euler = (math.radians(-10), 0, 0)              # leaning back against the windscreen
for fr, h in ((1, EXACT), (f("RULE", 1.5), EXACT), (f("RULE", 2.5), SET), (f("CORRECT", 3.0) - 1, SET),
              (f("CORRECT", 3.0), EXACT), (f("CORRECT", 3.25), EXACT), (f("CORRECT", 3.95), SET)):
    big["set_time"](fr, h)
print("DISC_SOURCE", dash["source"], big["source"])


def glow(root, k):
    """The dash disc sits in the shade of the roof behind the glass: a faint emission of its own colours (copies of
    the shared pd_* materials, so the close-up disc is unchanged) keeps it reading blue and white."""
    done = {}
    for o in root.children_recursive:
        if o.type not in ("MESH", "FONT"):
            continue
        for i, m in enumerate(o.data.materials):
            if m is None or not m.name.startswith("pd_"):
                continue
            if m.name not in done:
                cp = m.copy()
                cp.name = m.name + "_dash"
                bs = next(n for n in cp.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
                bs.inputs["Emission Color"].default_value = bs.inputs["Base Color"].default_value
                bs.inputs["Emission Strength"].default_value = k
                done[m.name] = cp
            o.data.materials[i] = done[m.name]


glow(dash["root"], 0.5)
cabin = K.W.principled("car_plastic_cabin", (0.025, 0.026, 0.03), 0.62)
K.quad("disc_dashtop", [(DZ.x - 3.0, DZ.y - 1.2), (DZ.x + 3.0, DZ.y - 1.2), (DZ.x + 3.0, DZ.y + 0.6),
                        (DZ.x - 3.0, DZ.y + 0.6)], cabin, env, z=DZ.z - 0.005, shadow=True)
back = K.W.mesh_obj("disc_cabin", [(DZ.x - 4.0, DZ.y + 0.6, DZ.z - 0.1), (DZ.x + 4.0, DZ.y + 0.6, DZ.z - 0.1),
                                   (DZ.x + 4.0, DZ.y + 1.6, DZ.z + 3.5), (DZ.x - 4.0, DZ.y + 1.6, DZ.z + 3.5)],
                    [(0, 1, 2, 3)], K.W.principled("car_plastic_roof", (0.05, 0.05, 0.055), 0.8), env)
K.area("disc_key", env, (DZ.x - 0.8, DZ.y - 1.6, DZ.z + 1.6), 150.0, 1.6, (math.radians(45), 0, math.radians(-20)))
K.area("disc_fill", env, (DZ.x + 1.2, DZ.y - 1.0, DZ.z + 0.6), 35.0, 1.2, (math.radians(80), 0, math.radians(50)))

# ------------------------------------------------------------------ the attendant (kit/figures.py) and the ticket
XF = HX + TN.KERB_W + 1.1
sv_a = []
for k in TL.order:
    m = TL.n(k)
    if k == "SITUATION":
        sv_a += [(min(3.2, max(0.0, 1.3 * (i / FPS - 6.5))), 1.3 if 6.5 < i / FPS < 6.5 + 3.2 / 1.3 else 0.0)
                 for i in range(m)]
    elif k in ("RULE", "COST"):
        sv_a += [(3.2, 0.0)] * m
    else:
        sv_a += [(0.0, 0.0)] * m
K.walker(env, "attendant", 23, [(XF, pB.y - 3.0), (XF, pB.y + 0.2)], sv_a, role="attendant",
         gesture=[("write", TL.a("SITUATION", 9.1), TL.a("RULE"))],
         look=[(TL.a("SITUATION", 9.0), TL.a("COST"), (pB.x, pB.y + 1.0, 1.0))])
ws, _ = K.windscreen_point(H, TL.a("RULE"))
K.slip("slip_hook", env, ws, yawB, TL.a("HOOK", 1.0), t_off=TL.a("SITUATION"))
K.slip("slip_cost", env, ws, yawB, TL.a("COST", 2.1), t_off=TL.a("CORRECT"))   # after the notepad shot
for k, (x, y) in enumerate(((-HX - 1.6, 70.0), (HX + 1.4, 20.0))):
    K.walker(env, f"ped{k}", 6 + 3 * k, [(x, y), (x, y + (-40.0 if k == 0 else 40.0))],
             [(min(40.0, 1.1 * i / FPS), 1.1) for i in range(N)], coat=((0.5, 0.12, 0.1), (0.3, 0.3, 0.32))[k])
sg = PS["signs"][0].location                     # Zeichen 314 over 1040-32 on its post at the row start

# ------------------------------------------------------------------ where the dash disc is (world), the pad on the bonnet
side = Vector((math.sin(yawB), -math.cos(yawB), 0.0))         # the car's right, towards the kerb
fwd = Vector((math.cos(yawB), math.sin(yawB), 0.0))
UPZ = Vector((0.0, 0.0, 1.0))
bpy.context.view_layer.update()
Mh = K.car_matrix(H, pB.x, pB.y, yawB)
rd = dash["root"]
cd = Mh @ (rd.matrix_world @ Vector((0.0, 0.0, 0.075)))                      # middle of the disc
nw = (Mh.to_3x3() @ (rd.matrix_world.to_3x3() @ Vector((0.0, -1.0, 0.0)))).normalized()   # out through the glass
print("DISC_AT", tuple(round(v, 3) for v in cd), "normal", tuple(round(v, 3) for v in nw), "ws", tuple(ws))
li = bpy.data.lights.new("disc_sun", "SPOT")            # daylight through the windscreen onto the disc (the roof
li.spot_size, li.spot_blend, li.energy = math.radians(22), 0.5, 18.0   # shades the dashboard from the low sun)
sun_d = bpy.data.objects.new("disc_sun", li)
env.objects.link(sun_d)
sun_d.location = cd + nw * 1.1 - side * 0.7 + UPZ * 0.3       # off the camera axis: no hot spot on the glass
sun_d.rotation_euler = K.stage.look_rot(Vector(sun_d.location), cd)
sun_d.visible_glossy = False                                   # rev 3 test: its highlight showed on the glass
# COST: the attendant's notepad lies on the bonnet in front of the windscreen, kerb side, the pen writing
pp, pn = K.on_body(H, Mh, 1.34, 0.30)
pad_c = pp + pn * 0.012
K.show_between(K.pad(env, tuple(pad_c), TL.a("COST", 0.3), TL.a("COST", 2.1), rot=K.lay_rot(pn, -fwd + side * 0.25)),
               TL.a("COST"), TL.a("CORRECT"))

# ------------------------------------------------------------------ cameras (a5gfx.py projects the ASS marks with
# the R_disc / K_disc numbers: camera DZ + (0, -2.4, 0.42), target DZ + (0, 0, 0.62), lens 40)
sh = K.Shots(N)                  # frame-exact cuts (ep10_za5kit.Shots)
disc_cam = lambda t: (Vector((DZ.x, DZ.y - 2.4, DZ.z + 0.42)), Vector((DZ.x, DZ.y, DZ.z + 0.62)))  # noqa: E731


def through(d0, d1, lat0, lat1, ta, tb, aim=Vector((0.0, 0.0, 0.0))):
    """Looking through the windscreen onto the dashboard along the glass normal, from above the bonnet, so the front
    of the car stays out of the frame (rev 2: the low-poly front and its indicator block read as a concept car).
    Distance d0 -> d1 and offset towards the kerb lat0 -> lat1 between the absolute times ta and tb."""
    def fn(t):
        u = K.ease(max(0.0, min(1.0, (t - ta) / max(1e-6, tb - ta))))
        tg = cd + aim
        return tg + nw * (d0 + (d1 - d0) * u) + side * (lat0 + (lat1 - lat0) * u), tg
    return fn


sign_cam = lambda t: (Vector((sg.x - 1.3, sg.y - 6.5 + 0.25 * (t - t0), 1.55)), Vector((sg.x - 0.2, sg.y, 2.35)))  # noqa: E731
mid = (ws - cd) * 0.45                                        # between the disc and the ticket on the glass
t0 = TL.a("HOOK")
sh.add("H_glass", 30, t0, TL.a("SITUATION"), through(1.75, 1.6, 0.35, 0.3, t0, TL.a("SITUATION"), mid))
t0 = TL.a("SITUATION")
sh.add("S_sign", 32, t0, t0 + 3.0, sign_cam)
sh.add("S_glass", 36, t0 + 3.0, t0 + 6.5, through(0.95, 0.72, 0.1, 0.06, t0 + 3.0, t0 + 6.5))
sh.add("S_top", 30, t0 + 6.5, TL.a("RULE"), lambda t: (Vector((HX - 0.5, pB.y, 20.0)), Vector((HX - 0.5, pB.y, 0.0))),
       up_fn=lambda t: UP_N)
t0 = TL.a("RULE")
sh.add("R_disc", 40, t0, t0 + 5.5, disc_cam)
sh.add("R_glass", 30, t0 + 5.5, TL.a("COST"), through(1.6, 1.45, 0.55, 0.45, t0 + 5.5, TL.a("COST")))
t0 = TL.a("COST")
sh.add("C_pad", 34, t0, t0 + 2.2, lambda t: (pad_c + side * 0.42 + fwd * (0.34 - 0.03 * (t - t0)) + UPZ * 0.5,
                                             pad_c - fwd * 0.06))
sh.add("C_top", 30, t0 + 2.2, TL.a("CORRECT"), lambda t: (Vector((pB.x, pB.y, 16.0)), Vector((pB.x, pB.y, 0.0))),
       up_fn=lambda t: UP_N)
t0 = TL.a("CORRECT")
sh.add("K_sign", 32, t0, t0 + 3.0, sign_cam)
sh.add("K_disc", 40, t0 + 3.0, t0 + 4.8, disc_cam)
sh.add("K_glass", 32, t0 + 4.8, TL.a("END"), through(1.45, 1.2, 0.2, 0.5, t0 + 4.8, TL.a("END")))
K.end_card(T, env, sh, TL.a("END"), TL.T, signs_=(("314", 0.6), ("1040-32", 0.6)))
K.light(az=240.0, elev=28.0, energy=5.0, exposure=0.3)
K.finish(sh, TL)

