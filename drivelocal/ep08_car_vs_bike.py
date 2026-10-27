"""Drive Like a Local #8, Germany (quiz): car or bike, who goes first? At a crossroads with no signs (inside a Tempo 30
zone, Zeichen 274.1) right before left applies to bikes too: the cyclist coming from the right goes first. 9:16, 30 fps.
Set: residential crossroads, no signs or lights at the junction. A (black SUV) comes from the south, B (cyclist in a
yellow jacket) from the east, C (green hatchback) from the west, all straight on. B has nobody on its right and goes
first; B is on A's right, so A goes second; A is on C's right, so C goes last. Signs: Commons files via kit/signs.py.
Canonical timeline (English order; per-language order is cut at compose time, ep08_edit.json):
SETUP 0-3, QUESTION 3-5, TIMER 5-15, ANSWER 15-20, RULE 20-25, COST 25-31.2, END 31.2-34.7.
Run: python ep08_car_vs_bike.py OUTDIR --frames 1-1041 --res 540 --samples 8 --assets ASSETS [--stills 60,300]
"""
# ==== a1 common: the same block in ep08, ep12, ep14, ep22 and ep25 (kept identical; a kit module would remove it) ====
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "kit"), os.path.join(HERE, "..", "kit")]

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import jx  # noqa: E402
import motion  # noqa: E402
import signs as SG  # noqa: E402
import stage  # noqa: E402
import town as TN  # noqa: E402
import townplus as TP  # noqa: E402
import townstage as TS  # noqa: E402
import world as W  # noqa: E402
try:
    import figures as FG  # proper people and a city bike (built on another branch); placeholders until it lands
except ImportError:
    FG = None

OUT, RES, SAMPLES, ASSETS, FR, STILLS = "frames", 540, 8, "assets", None, None
_a = sys.argv
for _i, _x in enumerate(_a):
    if _i == 1 and not _x.startswith("--"):
        OUT = _x
    if _x == "--res":
        RES = int(_a[_i + 1])
    if _x == "--samples":
        SAMPLES = int(_a[_i + 1])
    if _x == "--assets":
        ASSETS = _a[_i + 1]
    if _x == "--frames":
        _p, _q = _a[_i + 1].split("-")
        FR = (int(_p), int(_q))
    if _x == "--stills":
        STILLS = [int(v) for v in _a[_i + 1].split(",")]
FPS = jx.FPS
FONT_DIR = next((d for d in (os.path.join(HERE, "fonts"), os.path.join(HERE, "..", "fonts"),
                             "/home/claude/sf2/fonts") if os.path.isdir(d)), None)
UP_N = Vector((0, 1, 0))
HIDE = -600.0


class Timeline:
    """Segments back to back on the canonical (English) timeline. sv() joins per-segment (s, v) runs into one list
    for frames 1..N; a car that is not in a segment waits far out of sight."""

    def __init__(self, segs):
        self.order, self.span, t = [], {}, 0.0
        for k, d in segs:
            self.order.append(k)
            self.span[k] = (t, t + d)
            t += d
        self.T = t
        self.N = int(round(t * FPS))
        N_ALL[0] = self.N

    def a(self, seg, rel=0.0):
        return self.span[seg][0] + rel

    def n(self, seg):
        return int(round(self.span[seg][1] * FPS)) - int(round(self.span[seg][0] * FPS))

    def f(self, seg, rel=0.0):
        return int(round((self.span[seg][0] + rel) * FPS)) + 1

    def sv(self, parts):
        out = []
        for k in self.order:
            n, p = self.n(k), parts.get(k)
            if p is None:
                out += [(HIDE, 0.0)] * n
            elif isinstance(p, list):
                out += (p + [p[-1]] * n)[:n]
            else:
                s0, v0, plan = p[:3]
                out += jx.kinematics(s0, v0, plan, n, **(p[3] if len(p) > 3 else {}))
        return out


def hold(s, n=1):
    return [(s, 0.0)] * n


def creep(s0, v, n):
    return [(s0 + v * i / FPS, v) for i in range(n)]


def ending(s_end, v0, plan, n, **kw):
    """jx.kinematics shifted so that the run ends at s_end (for plans without a 'stop')."""
    sv = jx.kinematics(0.0, v0, plan, n, **kw)
    d = s_end - sv[-1][0]
    return [(s + d, v) for s, v in sv]


def light(az, elev, energy=5.0, col=(1.0, 0.64, 0.4), tint=(1.0, 0.84, 0.7), amb=0.75, exposure=0.3):
    """Low warm late-October sun (azimuth from +x, counter-clockwise, towards the sun), long shadows, warm sky."""
    TS.light(sun_az_deg=az, sun_elev_deg=elev, assets=ASSETS)
    sun = bpy.data.objects["sun"]
    sun.data.color, sun.data.energy, sun.data.angle = col, energy, math.radians(1.0)
    nt = bpy.context.scene.world.node_tree
    env = next(n for n in nt.nodes if n.type == "TEX_ENVIRONMENT")
    bg = nt.nodes["Background"]
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    mul.inputs["B"].default_value = (*tint, 1)
    nt.links.new(env.outputs["Color"], mul.inputs["A"])
    nt.links.new(mul.outputs["Result"], bg.inputs["Color"])
    for nd in nt.nodes:
        if nd.type == "BACKGROUND" and nd != bg:
            nd.inputs["Strength"].default_value = amb
    bpy.context.scene.view_settings.exposure = exposure


def pop(root, windows, size=1.0):
    """Scale keys: hidden, then popping in and out for each (t_on, t_off) window (absolute seconds)."""
    keys = [(1, 0.0)]
    for t_on, t_off in windows:
        f_on, f_off = int(t_on * FPS) + 1, int(t_off * FPS) + 1
        keys += [(f_on, 0.0), (f_on + 4, 1.18 * size), (f_on + 7, size), (f_off, size), (f_off + 5, 0.0)]
    for f, s in keys:
        root.scale = (s, s, s)
        root.keyframe_insert("scale", frame=f)


def badge(letter, who, c, font, windows, size=1.9, lift=0.9):
    """jx.badge (faces the camera in every shot) shown in several windows."""
    b = jx.badge(letter, dict(track=who["track"], roof=who["roof"] + lift - 0.9), c, font, windows[0][0],
                 windows[0][1], size=size)
    if len(windows) > 1:
        pop(b, windows[1:], 1.0)
    return b


def callout(sid, loc, windows, c, width=2.6, set_="de-core", emit=0.9, name=None):
    """A Commons sign (signs.py, unaltered) floating flat above its real position, facing the camera like a badge."""
    root = bpy.data.objects.new(name or f"badge_sign_{sid}", None)
    c.objects.link(root)
    root.location = loc
    plate = SG.face(sid, c, width, set_, name=f"call_{sid}_{len(bpy.data.objects)}", emit=emit)
    plate.parent = root
    plate.rotation_euler = (-math.pi / 2, 0, 0)
    plate.location = (0, -plate["height"] / 2, 0)
    for o in [plate] + list(plate.children):
        o.visible_shadow = False
    pop(root, windows)
    return root


def flat_sign(sid, loc, c, width, rz=0.0, set_="de-core", emit=0.0):
    """A Commons sign lying flat (face up), its top towards +y rotated by rz (end card)."""
    root = bpy.data.objects.new(f"flat_{sid}", None)
    c.objects.link(root)
    root.location = loc
    root.rotation_euler = (0, 0, rz)
    plate = SG.face(sid, c, width, set_, name=f"flat_{sid}_{len(bpy.data.objects)}", emit=emit)
    plate.parent = root
    plate.rotation_euler = (-math.pi / 2, 0, 0)
    plate.location = (0, -plate["height"] / 2, 0)
    return root


def corner_spot(sx, sy, x=None, y=None, off=0.76, hx=3.0, hy=3.0, R=6.0):
    """A point on the footway around the kerb radius of quadrant (sx, sy), `off` behind the kerb face, at the given
    x (or y)."""
    cx, cy = sx * (hx + R), sy * (hy + R)
    r = R - off
    if x is not None:
        u = max(-1.0, min(1.0, (x - cx) / r))
        return Vector((x, cy - sy * r * math.sqrt(1 - u * u)))
    u = max(-1.0, min(1.0, (y - cy) / r))
    return Vector((cx - sx * r * math.sqrt(1 - u * u), y))


def quad(name, pts, mat, c, z=0.008):
    o = W.mesh_obj(name, [(p[0], p[1], z) for p in pts], [(0, 1, 2, 3)], mat, c, uvs=[(p[0], p[1]) for p in pts])
    TP.up(o)
    o.visible_shadow = False
    return o


GROUND = [None]                        # ground(x, y) -> z of the junction (footways 0.15 m up); set per episode
N_ALL = [0]                            # frames of the whole timeline (set by Timeline)


def junction_ground(hx, hy, R=6.0, kerb=TN.KERB_H):
    """z of the ground at (x, y) on the approved X junction: carriageway 0 (including the kerb radii), footways and
    gardens at kerb height. For figures.walk / ride / stand."""
    def g(x, y):
        ax, ay = abs(x), abs(y)
        if ax <= hx or ay <= hy:
            return 0.0
        if ax < hx + R and ay < hy + R and math.hypot(ax - hx - R, ay - hy - R) > R:
            return 0.0
        return kerb
    return g


def person(c, name, seed, coat=None, **kw):
    """A person from kit/figures.py (armature, planted-foot walking); townplus placeholder only without it."""
    if FG is not None:
        args = dict(seed=seed)
        if coat is not None:
            args["jacket"] = coat
        args.update(kw)
        return FG.person(c, name, **args)
    return TP.pedestrian(c, name, seed=seed, coat=coat)


def walk_person(p, path, sv, frames=None, frame0=1, look=(), gesture=(), ground=None):
    if FG is not None and "arm" in p:
        return FG.walk(p, path, sv, frames=frames, ground=ground or GROUND[0], look=look, gesture=gesture,
                       frame0=frame0)
    out = TP.walk(p, path, sv, frames or list(range(frame0, frame0 + len(sv))))
    on_footway(p)
    return out


def bike(c, name, seed, jacket=None, basket=False, frame_col=None):
    if FG is not None:
        rider = dict(seed=seed)
        if jacket is not None:
            rider["jacket"] = jacket
        bk = dict(frame="step", basket=basket)
        if frame_col is not None:
            bk["color"] = frame_col
        return FG.cyclist(c, name, rider=rider, bike=bk, seed=seed)
    cy = TP.cyclist(c, name, seed=seed, frame_col=frame_col)
    if jacket is not None and bpy.data.materials.get(name + "_coat"):
        bpy.data.materials[name + "_coat"].node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = \
            (*jacket, 1)
    return cy


def ride_bike(cy, path, sv, frames=None, frame0=1, foot="L", look=(), signal=(), ground=None):
    if FG is not None and "rider" in cy:
        return FG.ride(cy, path, sv, frames=frames, ground=ground, signal=signal, foot=foot, look=look, frame0=frame0)
    return TP.ride(cy, path, sv, frames or list(range(frame0, frame0 + len(sv))))


def stand_person(p, pos, heading, n, frame0=1, look=(), gesture=(), ground=None):
    if FG is not None and "arm" in p:
        return FG.stand(p, pos, heading, n, ground=ground or GROUND[0], look=look, gesture=gesture, frame0=frame0)
    p["root"].location = (pos[0], pos[1], (ground or GROUND[0] or (lambda x, y: 0.0))(pos[0], pos[1]))
    p["root"].rotation_euler = (0, 0, heading - math.pi / 2)


def block(tl, seg0, seg1=None):
    """First and last frame of the segments seg0 .. seg1 on the canonical timeline."""
    seg1 = seg1 or seg0
    return tl.f(seg0), tl.f(seg1) + tl.n(seg1) - 1


def on_footway(p, z=TN.KERB_H):
    """Lift a placeholder figure onto the footway (its walk bakes z = 0, the road level)."""
    lift = bpy.data.objects.new(p["root"].name + "_lift", None)
    p["root"].users_collection[0].objects.link(lift)
    lift.location = (0, 0, z)
    p["root"].parent = lift
    return p


def walker(c, name, seed, pts, v, s0, N, coat=None):
    """A pedestrian walking along a footway (pts) at v m/s for the whole timeline (stops at the end of the path)."""
    p = person(c, name, seed, coat)
    path = jx.Path(pts)
    sv = [(min(path.length, s0 + v * i / FPS), v if s0 + v * i / FPS < path.length else 0.0) for i in range(N)]
    walk_person(p, path, sv)
    return p


def stander(c, name, seed, xy, yaw, coat=None, look=()):
    """Someone standing on the footway for the whole timeline (weight shift, breathing, head turns)."""
    p = person(c, name, seed, coat)
    if FG is not None and "arm" in p:
        FG.stand(p, xy, yaw, N_ALL[0], ground=GROUND[0], look=look)
        return p
    p["root"].location = (xy[0], xy[1], TN.KERB_H)
    p["root"].rotation_euler = (0, 0, yaw - math.pi / 2)
    return p


def shown(build, f0, f1):
    """Run build() and show what it created only from frame f0 to f1 (one figure per continuous motion block: a
    figure's walk or ride cannot jump back to the start of another shot)."""
    before = set(bpy.data.objects)
    out = build()
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        for f, h in ((1, f0 > 1), (f0, False), (f1 + 1, True)):
            o.hide_render = h
            o.keyframe_insert("hide_render", frame=f)
    return out


def parked(env, fleet, key, x, y, yaw):
    e = bpy.data.objects.new("parked_" + key, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = fleet[key]
    e.location = (x, y, 0)
    e.rotation_euler = (0, 0, yaw - math.pi / 2)
    env.objects.link(e)
    return e


def traffic(c, fleet, key, path, sv, N, L=4.6):
    """A background car from the parked fleet, rigged (turning wheels, brake lights) and driven along a path."""
    e = bpy.data.objects.new("trf_" + key, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = fleet[key]
    c.objects.link(e)
    car = dict(obj=e, L=L, name="trf_" + key)
    car["rig"] = motion.rig(e)
    jx.drive(car, path, sv, list(range(1, N + 1)))
    return car


def fix_jumps(thresh=2.5):
    """Hold every baked transform constant across a teleport (a cut to another shot), so motion blur never smears a
    car from one segment's position to the next. Used with motion_blur_position START."""
    n = 0
    for o in bpy.data.objects:
        ad = o.animation_data
        if not ad or not ad.action:
            continue
        try:
            fcs = stage.fcurves(o)
        except Exception:
            continue
        loc = [fc for fc in fcs if fc.data_path == "location"]
        if len(loc) < 2 or len(loc[0].keyframe_points) < 3:
            continue
        cols = [[kp.co[1] for kp in fc.keyframe_points] for fc in loc]
        frames = [kp.co[0] for kp in loc[0].keyframe_points]
        jumps = set()
        for i in range(len(frames) - 1):
            if frames[i + 1] - frames[i] > 1.5:
                continue
            d = math.sqrt(sum((cv[i + 1] - cv[i]) ** 2 for cv in cols if len(cv) == len(frames)))
            if d > thresh:
                jumps.add(frames[i])
        if not jumps:
            continue
        for fc in fcs:
            for kp in fc.keyframe_points:
                if kp.co[0] in jumps:
                    kp.interpolation = "CONSTANT"
                    n += 1
        for ch in o.children_recursive:
            if ch.animation_data and ch.animation_data.action:
                try:
                    for fc in stage.fcurves(ch):
                        for kp in fc.keyframe_points:
                            if kp.co[0] in jumps:
                                kp.interpolation = "CONSTANT"
                except Exception:
                    pass
    return n


def end_card(T, c, shots, t0, t1, signs_=(), z=400.0, title="DRIVE LIKE A LOCAL", letters=()):
    """Series end card: a road-grey card (town asphalt with a white edge line), the episode's Commons signs laid on
    it and the series title painted on it like a road marking; its own soft key light; no live action."""
    w, h = 26.0, 48.0
    quad("endcard", [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)], T.asph, c, z=z)
    for sx in (-1, 1):
        quad("endcard_line", [(sx * 9.6 - 0.15, -h / 2), (sx * 9.6 + 0.15, -h / 2), (sx * 9.6 + 0.15, h / 2),
                              (sx * 9.6 - 0.15, h / 2)], T.paint, c, z=z + 0.01)
    k = len(signs_)
    for i, (sid, width) in enumerate(signs_):
        x = (i - (k - 1) / 2) * 5.6
        flat_sign(sid, (x, -4.6, z + 0.03), c, width, emit=0.15)
    for i, letter in enumerate(letters):
        x = (i - (len(letters) - 1) / 2) * 4.2
        for nm, r, m_, dz in (("ring", 1.7, jx.flat_mat("endcard_ring", (1, 1, 1), emit=0.6), 0.02),
                              ("disc", 1.46, jx.flat_mat("endcard_" + letter, jx.BADGE_COLOURS[letter], emit=0.6),
                               0.03)):
            o = W.mesh_obj(f"endcard_{nm}", [(x + r * math.cos(2 * math.pi * k / 40), -4.6 + r * math.sin(2 * math.pi * k / 40),
                                              z + dz) for k in range(40)], [tuple(range(40))], m_, c)
            o.visible_shadow = False
        lt = W.text_obj("endcard_l" + letter, letter, 2.4, jx.flat_mat("endcard_ink", (0.02, 0.02, 0.03), emit=0.0), c,
                        "CENTER", "CENTER", 0.0, font=bpy.data.fonts.load(os.path.join(FONT_DIR, "Montserrat-Black.ttf"),
                                                                           check_existing=True))
        lt.location = (x, -4.65, z + 0.04)
    font = W.SIGN_FONT
    t = W.text_obj("endcard_title", title, 1.25, T.paint, c, "CENTER", "CENTER", 0.0, font=font)
    t.location = (0, -10.0, z + 0.02)
    li = bpy.data.lights.new("endcard_key", "AREA")
    li.size, li.energy, li.color = 34.0, 5200.0, (1.0, 0.95, 0.88)
    lo = bpy.data.objects.new("endcard_key", li)
    c.objects.link(lo)
    lo.location = (3.0, -6.0, z + 14.0)
    lo.rotation_euler = (math.radians(8), math.radians(-6), 0)
    cam = shots.add("E_card", 30, t0, t1, lambda t: (Vector((0.0, -1.2 - 0.25 * (t - t0), z + 34.0 - 0.9 * (t - t0))),
                                                    Vector((0.0, -1.2 - 0.25 * (t - t0), z))), up_fn=lambda t: UP_N)
    return cam


def finish(shots, timeline, skip=()):
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, timeline.N
    fix_jumps()
    stage.hazify_all(color=(0.8, 0.74, 0.68), dist=900.0, skip=tuple(skip))
    stage.render_setup(SAMPLES, RES, int(round(RES * 16 / 9)))
    sc.render.motion_blur_position = "START"
    print("SIGN_SOURCES", sorted(SG.sources_used()))
    todo = STILLS or list(range(FR[0], FR[1] + 1) if FR else range(1, timeline.N + 1))
    jx.render_frames(shots, OUT, todo)
    print("RENDER_DONE", FR)
# ==== end of a1 common ====


TL = Timeline([("SETUP", 3.0), ("QUESTION", 2.0), ("TIMER", 10.0), ("ANSWER", 5.0), ("RULE", 5.0), ("COST", 6.2),
               ("END", 3.5)])
N = TL.N
HX = HY = 3.0
S = TS.build(ASSETS, "plain", seed=21, hx=HX, hy=HY, parked=False, heroes=[
    ("suv", (0.015, 0.016, 0.018), "carA", "QX AR 318", 0.5), ("hatch", (0.04, 0.26, 0.12), "carC", "JJ KL 77", 0.35)])
SG.setup(ASSETS)
GROUND[0] = junction_ground(HX, HY)
T, env, lib, traf, fleet = S["T"], S["env"], S["lib"], S["traffic"], S["fleet"]
font = bpy.data.fonts.load(os.path.join(FONT_DIR, "Montserrat-Black.ttf"), check_existing=True)
A, C = S["heroes"]["carA"], S["heroes"]["carC"]
frames = list(range(1, N + 1))

# ------------------------------------------------------------------ the zone: Tempo 30 zone signs at the entrances
off = TN.KERB_W + 0.6
z_s = Vector((HX + off, -46.0))
SG.assembly([("274.1", 0.75)], env, (z_s.x, z_s.y, TN.KERB_H), TN.facing((0, 1)), name="z274_s")
SG.assembly([("274.1", 0.75)], env, (46.0, HY + off, TN.KERB_H), TN.facing((-1, 0)), name="z274_e")
SG.assembly([("274.1", 0.75)], env, (-46.0, -(HY + off), TN.KERB_H), TN.facing((1, 0)), name="z274_w")

# ------------------------------------------------------------------ paths and positions
PA = jx.lane_path("S", "straight")                  # A drives north
PC = jx.lane_path("W", "straight")                  # C drives east
YB = HY - 0.9                                       # the cyclist keeps about 0.9 m from the kerb
PB = jx.Path([(95.0, YB), (0.0, YB), (-95.0, YB)])  # B rides west
LA, LC = A["L"], C["L"]
sA = 95.0 - (HY + 1.2) - LA / 2
sC = 95.0 - (HX + 1.2) - LC / 2
sB = 95.0 - (HX + 1.0) - 0.9                        # front wheel 1 m before the junction (bike centre 0.9 m behind)
parts_A = {
    "SETUP": (sA - 9.0, 6.0, [(0, "stop", sA)]),
    "QUESTION": hold(sA, TL.n("QUESTION")),
    "TIMER": creep(sA, 0.02, TL.n("TIMER")),
    "ANSWER": (sA + 0.2, 0.0, [(0, "hold", None), (1.3, "cruise", 6.0)], {"a_acc": 2.2}),
    "RULE": hold(sA, TL.n("RULE")),
    "COST": (sA - 3.0, 3.0, [(0, "cruise", 3.2), (1.0, "stop", sA + 3.4)], {"a_brake": 4.0}),
}
parts_C = {
    "SETUP": (sC - 9.8, 6.0, [(0, "stop", sC)]),
    "QUESTION": hold(sC, TL.n("QUESTION")),
    "TIMER": creep(sC, 0.015, TL.n("TIMER")),
    "ANSWER": (sC + 0.15, 0.0, [(0, "hold", None), (3.2, "cruise", 6.0)], {"a_acc": 2.2}),
    "COST": hold(sC, TL.n("COST")),
}
parts_B = {
    "SETUP": (sB - 13.2, 5.0, [(0, "cruise", 5.0), (1.9, "cruise", 1.0)], {"a_brake": 5.0}),
    "QUESTION": creep(sB - 0.4, 0.2, TL.n("QUESTION")),
    "TIMER": creep(sB, 0.04, TL.n("TIMER")),
    "ANSWER": (sB + 0.4, 1.5, [(0, "cruise", 5.0)], {"a_acc": 3.0}),
    "RULE": (sB - 9.0, 4.0, [(0, "cruise", 4.0)]),
    "COST": (sB - 3.2, 4.5, [(0, "cruise", 4.5), (0.55, "stop", sB + 2.2)], {"a_brake": 5.5}),
}
SV_A, SV_C, SV_B = TL.sv(parts_A), TL.sv(parts_C), TL.sv(parts_B)
jx.drive(A, PA, SV_A, frames)
jx.drive(C, PC, SV_C, frames)
YELLOW = FG.YELLOW if FG is not None else (0.95, 0.72, 0.02)
# the cost replay: B brakes hard and swerves towards the kerb as A rolls in (a path of its own)
PBc = jx.Path([(95.0, YB), (8.4, YB), (6.0, YB + 0.15), (4.5, YB + 0.38), (3.0, YB + 0.52), (1.0, YB + 0.55),
               (-95.0, YB + 0.55)])
B_track = [None] * N
for (seg0, seg1), path in ((("SETUP", "ANSWER"), PB), (("RULE", "RULE"), PB), (("COST", "COST"), PBc)):
    f0, f1 = block(TL, seg0, seg1)
    sv_ = SV_B[f0 - 1:f1]
    cyB = shown(lambda: bike(env, f"cycB_{seg0}", 4, jacket=YELLOW, basket=True, frame_col=(0.05, 0.1, 0.28)),
                f0, f1)
    ride_bike(cyB, path, sv_, list(range(f0, f1 + 1)), frame0=f0, foot="L", ground=GROUND[0],
              look=[(0.2, 1.4, -60)] if seg0 == "SETUP" else ())
    for i, (s_, v_) in enumerate(sv_):
        p_, _ = path.at(s_)
        B_track[f0 - 1 + i] = (p_.x, p_.y, 0.0)
B_track = [q if q is not None else (0.0, -800.0, 0.0) for q in B_track]
BH = dict(track=B_track, roof=1.75)

# ------------------------------------------------------------------ life
for key, x, y, yaw in (("estate_grey", -1.95, 18.0, -math.pi / 2), ("hatch_red", -1.95, 24.5, -math.pi / 2),
                       ("van_white", -1.95, 33.0, -math.pi / 2), ("saloon_white", -1.95, -17.0, -math.pi / 2),
                       ("hatch_blue", -1.95, -23.5, -math.pi / 2), ("estate_blue", 24.0, -1.95, 0.0),
                       ("suv_white", 31.0, -1.95, 0.0), ("saloon_black", 34.0, 1.95, math.pi),
                       ("estate_green", -30.0, 1.95, math.pi), ("hatch_silver", -36.5, 1.95, math.pi)):
    parked(env, fleet, key, x, y, yaw)
walker(env, "ped1", 6, [(4.4, 50.0), (4.4, 10.5)], 1.2, 0.0, N, coat=(0.5, 0.38, 0.22))
walker(env, "ped2", 14, [(-10.5, 4.4), (-50.0, 4.4)], 1.05, 0.0, N, coat=(0.08, 0.1, 0.2))
walker(env, "ped3", 3, [(4.4, -12.0), (4.4, -60.0)], 1.3, 0.0, N)
walker(env, "ped4", 9, [(12.0, -4.4), (55.0, -4.4)], 1.15, 0.0, N, coat=(0.45, 0.06, 0.05))
stander(env, "ped5", 11, (-5.5, -11.5), 0.6, coat=(0.22, 0.24, 0.2))
stander(env, "ped6", 2, (-5.2, -12.3), 0.2)
stander(env, "ped7", 15, (11.5, 5.0), -math.pi / 2, coat=(0.62, 0.42, 0.12))
TP.leaves(env, TP.through(S["J"], "NS"), -80.0, 80.0, seed=3)
TP.leaves(env, TP.through(S["J"], "EW"), -80.0, 80.0, seed=8)
traffic(traf, fleet, "estate_grey", jx.lane_path("S", "straight"),
        [(-120.0 + 8.0 * i / FPS, 8.0) if i < TL.f("RULE") else (HIDE, 0.0) for i in range(N)], N)

# ------------------------------------------------------------------ quiz layer
WQ = [(TL.a("QUESTION", 0.2), TL.a("ANSWER", -0.2)), (TL.a("ANSWER", 1.7), TL.a("ANSWER", 3.2))]
badge("A", A, traf, font, WQ)
# B's badge floats 1.4 m north of the rider (up the screen in the top views), so it does not hide the cyclist
badge("B", dict(track=[(x, y + 1.4, z) for x, y, z in B_track], roof=1.75), traf, font, WQ, size=1.7)
badge("C", C, traf, font, WQ)
jx.ribbon(PA, sA + LA / 2 + 0.6, sA + 20.0, jx.BADGE_COLOURS["A"], env, TL.a("QUESTION", 0.4), TL.a("ANSWER", 0.2),
          name="ribA")
jx.ribbon(PB, sB + 1.2, sB + 18.0, jx.BADGE_COLOURS["B"], env, TL.a("QUESTION", 0.55), TL.a("ANSWER", 0.2),
          width=0.8, name="ribB")
jx.ribbon(PC, sC + LC / 2 + 0.6, sC + 20.0, jx.BADGE_COLOURS["C"], env, TL.a("QUESTION", 0.7), TL.a("ANSWER", 0.2),
          name="ribC")
# the rule: a soft green arrow along the cyclist's way into the junction ("from the right")
jx.ribbon(PB, sB - 12.0, sB + 8.0, (0.25, 1.0, 0.45), env, TL.a("RULE", 0.2), TL.a("RULE", 2.4), width=1.2,
          name="ribRight")
callout("274.1", (z_s.x + 1.4, z_s.y + 1.0, 5.4), [(TL.a("SETUP", 0.3), TL.a("SETUP", 1.6))], env, width=3.0)

# ------------------------------------------------------------------ cameras
shots = jx.Shots(N)


def at(track, t):
    i = max(0, min(len(track) - 1, int(t * FPS)))
    x, y, _ = track[i]
    return Vector((x, y, 0.0))


t0 = TL.a("SETUP")
shots.add("S_drone", 26, t0, t0 + 1.6, lambda t: (Vector((7.5 - 1.5 * (t - t0), -58.0 + 9.0 * (t - t0),
                                                          6.5 + 6.0 * (t - t0))), Vector((0.0, -8.0, 0.0))))
shots.add("S_top", 30, t0 + 1.6, TL.a("QUESTION"),
          lambda t: (Vector((0.0, -11.5, 33.5 - 0.8 * (t - t0 - 1.6))), Vector((0.0, -0.4, 0.0))), up_fn=lambda t: UP_N)
tq = TL.a("QUESTION")
shots.add("Q_top", 30, tq, TL.a("ANSWER"),
          lambda t: (Vector((0.0, -11.0 + 0.05 * (t - tq), 32.4 - 0.2 * (t - tq))), Vector((0.0, -0.4, 0.0))),
          up_fn=lambda t: UP_N)
ta = TL.a("ANSWER")


# QA r5 #2: the answer opens on the top view, where "First: B / From the right." can be read off the picture (the
# street-level chase of the cyclist could not show where B comes from); the top view now carries the first two beats
shots.add("A_top", 30, ta, ta + 3.4,
          lambda t: (Vector((0.0, -10.0, 28.85 - 0.5 * (t - ta))), Vector((0.0, 0.0, 0.0))), up_fn=lambda t: UP_N)


def chase_c(t):
    p = at(C["track"], t)
    return p + Vector((-6.6, -0.6, 1.3)), p + Vector((9.0, 0.6, 0.6))


shots.add("A_chaseC", 24, ta + 3.4, TL.a("RULE"), chase_c)
tr = TL.a("RULE")
pA = at(A["track"], tr + 0.1)
# driver's view (QA r3: the black SUV bonnet filled the lower quarter like a mirror): camera higher and forward, just
# behind the nose, near-level look to the right where the cyclist comes from, 26 mm; the bonnet stays below the frame
pov = shots.add("R_pov", 26, tr, tr + 2.5, lambda t: (pA + Vector((-0.36, LA / 2 - 0.6, 1.66)),
                                                    pA + Vector((-0.36 + 40.0 * math.sin(math.radians(26)),
                                                                 LA / 2 - 0.6 + 40.0 * math.cos(math.radians(26)),
                                                                 1.2))))
cl = shots.add("R_close", 30, tr + 2.5, TL.a("COST"),
               lambda t: (Vector((4.7, -10.0 + 0.1 * (t - tr - 2.5), 0.7)), Vector((0.8, 2.0, 0.75))))
cl.data.dof.use_dof, cl.data.dof.focus_distance, cl.data.dof.aperture_fstop = True, 8.5, 2.8
tc = TL.a("COST")
cc = shots.add("C_close", 26, tc, tc + 2.2,
               lambda t: (Vector((-4.8, 5.5 - 0.2 * (t - tc), 1.2)), Vector((1.6, 0.7, 0.7))))
cc.data.lens = 22
cc.data.dof.use_dof, cc.data.dof.focus_distance, cc.data.dof.aperture_fstop = True, 9.0, 4.0
shots.add("C_top", 30, tc + 2.2, TL.a("END"), lambda t: (Vector((0.5, -7.0, 24.0)), Vector((0.5, 0.0, 0.0))),
          up_fn=lambda t: UP_N)
end_card(T, env, shots, TL.a("END"), TL.T, signs_=(("274.1", 4.4),))
light(az=232.0, elev=15.0, energy=5.4, exposure=0.35)
finish(shots, TL, skip=("ribA", "ribB", "ribC", "ribRight"))
