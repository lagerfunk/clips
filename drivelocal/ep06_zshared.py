"""Shared scene code for the batch-2 episodes 06, 23, 28, 27 and 18 (episode assembler a2). Not a scene itself.
The build copies every ep[0-9][0-9]_*.py flat into drivelocal/ of the public repo, so on the runners this file sits
next to the scene files; locally the scenes put ../ep06 on sys.path. The name sorts after ep06_roundabout_quiz.py so
kit/finish_ep.py still takes the episode slug from the scene file.

- cli(): the ep02 command line (OUT --frames a-b | --stills a,b --res --samples --assets, plus --dry)
- Timeline: named segments, each a standalone shot, on one canonical timeline (post_epNN.py cuts them per language)
- Actor: per-segment driving on any jx.Path through kit/motion.py (wheel spin, steering, brake lights from v,
  indicators per frame); a nominal v can be given for slow-motion holds so brake lights do not flash
- sun(): low warm October sun, warm sky and haze
- life: pedestrians and a cyclist (kit/figures.py), outbound fleet cars, autumn leaves in the gutters
- icons that face the camera: Commons sign faces (kit/signs.py, unaltered), indicator arrows, number badges
- end_card(): road-grey card with the episode's signs, emissive, ortho camera under the ground
- render(): the jx loop with motion blur off on the frames either side of a cut or a teleport
"""
import math
import os
import sys

import bpy
from mathutils import Vector

import jx
import motion as MO
import stage
import world as W

try:
    import signs as SG
except Exception:  # noqa: BLE001
    SG = None
try:
    import townplus as TP
except Exception:  # noqa: BLE001
    TP = None
try:
    import figures as F
except Exception:  # noqa: BLE001
    F = None
KERB_H = 0.15  # town.KERB_H: footways stand at the kerb height

FPS = jx.FPS
GREEN = (0.12, 0.85, 0.28)
AMBER = (1.0, 0.5, 0.0)
YELLOW = (1.0, 0.82, 0.05)
UP = Vector((0, 1, 0))
OVERLAY = ("rib", "badge", "icon", "card", "glow")


# ------------------------------------------------------------------ command line, fonts
def cli(argv=None):
    a = argv or sys.argv
    o = dict(OUT="frames", RES=720, SAMPLES=16, ASSETS="assets", FR=None, STILLS=None, DRY="--dry" in a)
    for i, x in enumerate(a):
        if i == 1 and not x.startswith("--"):
            o["OUT"] = x
        if x == "--res":
            o["RES"] = int(a[i + 1])
        if x == "--samples":
            o["SAMPLES"] = int(a[i + 1])
        if x == "--assets":
            o["ASSETS"] = a[i + 1]
        if x == "--frames":
            p, q = a[i + 1].split("-")
            o["FR"] = (int(p), int(q))
        if x == "--stills":
            o["STILLS"] = [int(v) for v in a[i + 1].split(",")]
    return o


def font(here):
    d = next((p for p in (os.path.join(here, "fonts"), os.path.join(here, "..", "fonts"), "/home/claude/sf2/fonts")
              if os.path.isdir(p)), None)
    return bpy.data.fonts.load(os.path.join(d, "Montserrat-Black.ttf"), check_existing=True)


# ------------------------------------------------------------------ timeline
class Timeline:
    def __init__(self, segs):
        self.segs = [(n, float(d)) for n, d in segs]
        self.start, self.dur = {}, {}
        t = 0.0
        for n, d in self.segs:
            self.start[n], self.dur[n] = t, d
            t = round(t + d, 4)
        self.T = t
        self.N = int(round(t * FPS))

    def t(self, seg, dt=0.0):
        return self.start[seg] + dt

    def f0(self, seg):
        return int(round(self.start[seg] * FPS)) + 1

    def f1(self, seg):
        return int(round((self.start[seg] + self.dur[seg]) * FPS))

    def nf(self, seg):
        return self.f1(seg) - self.f0(seg) + 1

    def f(self, seg, dt):
        return self.f0(seg) + int(round(dt * FPS))

    def cut_frames(self):
        out = set()
        for n, _d in self.segs:
            out |= {self.f0(n) - 1, self.f0(n)}
        return out


# ------------------------------------------------------------------ cars
def fleet_car(S, key, name):
    """A moving fleet car (collection instance) in the traffic collection, as an Actor-ready dict."""
    e = bpy.data.objects.new(name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = S["fleet"][key]
    S["traffic"].objects.link(e)
    return dict(obj=e, L=4.5, name=name)


def pose(path, s, L):
    wb = 0.55 * L
    pf = path.at(s + wb / 2)[0]
    pr = path.at(s - wb / 2)[0]
    p = path.at(s)[0]
    d = pf - pr
    return p.x, p.y, math.atan2(d.y, d.x)


class Actor:
    """One car over the whole canonical timeline: drive() fills frames segment by segment; frames left empty park
    the car under the ground (invisible). bake() writes motion.bake keys and car['track'] (for jx badges)."""

    def __init__(self, car, tl, hidden=(0.0, -3000.0, -80.0)):
        self.car, self.tl = car, tl
        self.L = car.get("L", 4.5)
        self.poses = [None] * tl.N
        self.hidden = hidden
        self.track = None

    def drive(self, seg, path, sv, ind=None, t0=0.0, v_nom=None, pitch=None):
        """sv: [(s, v)] one per frame from segment time t0. ind: None, 'L', 'R', 'H' or fn(s, t_seg). v_nom: number
        or fn(k) written as the speed (slow-motion holds). pitch: fn(k) in radians (nose dive)."""
        f0 = self.tl.f(seg, t0)
        f_end = self.tl.f1(seg)
        for k, (s, v) in enumerate(sv):
            f = f0 + k
            if f > f_end:
                break
            x, y, yaw = pose(path, s, self.L)
            t = t0 + k / FPS
            i = ind(s, t) if callable(ind) else ind
            vv = v if v_nom is None else (v_nom(k) if callable(v_nom) else v_nom)
            pt = pitch(k) if callable(pitch) else (pitch or 0.0)
            self.poses[f - 1] = (x, y, 0.0, yaw, vv, i, pt)
        return self

    def hold(self, seg, path, s, ind=None, t0=0.0, t1=None):
        t1 = self.tl.dur[seg] if t1 is None else t1
        n = int(round((t1 - t0) * FPS)) + 1
        return self.drive(seg, path, [(s, 0.0)] * n, ind, t0)

    def whole(self, path, sv, ind=None):
        """Continuous canonical-time drive over every frame (background traffic)."""
        for k, (s, v) in enumerate(sv[:self.tl.N]):
            x, y, yaw = pose(path, s, self.L)
            i = ind(s, k / FPS) if callable(ind) else ind
            self.poses[k] = (x, y, 0.0, yaw, v, i, 0.0)
        return self

    def at(self, f):
        p = self.poses[f - 1]
        return None if p is None else Vector((p[0], p[1], 0.0))

    def bake(self):
        track, last = [], 0.0
        for p in self.poses:
            if p is None:
                x, y, z = self.hidden
                track.append(dict(x=x, y=y, z=z, yaw=last, v=0.0, ind=None))
            else:
                x, y, z, yaw, v, i, pt = p
                last = yaw
                track.append(dict(x=x, y=y, z=z, yaw=yaw, v=v, ind=i, pitch=pt))
        r = MO.rig(self.car)
        MO.bake(r, track)
        self.car["track"] = [(t["x"], t["y"], t["z"]) for t in track]
        self.track = track
        return self

    def jumps(self):
        out = set()
        for i in range(1, len(self.track)):
            a, b = self.track[i - 1], self.track[i]
            d = math.hypot(b["x"] - a["x"], b["y"] - a["y"]) + abs(b["z"] - a["z"])
            if d > max(1.0, 3.0 * max(abs(a["v"]), abs(b["v"])) / FPS + 0.5):
                out |= {i, i + 1}
        return out

    def objects(self):
        r = MO.rig(self.car)
        objs = [r.obj] + [w["obj"] for w in r.wheels] + list(r.lamps.values()) + list(r.units.values())
        return list(dict.fromkeys(objs))

    def hide_during(self, spans):
        """Hide the car from the render during [(f0, f1)] (driver point-of-view shots)."""
        for o in self.objects():
            o.hide_render = False
            o.keyframe_insert("hide_render", frame=1)
            for f0, f1 in spans:
                o.hide_render = True
                o.keyframe_insert("hide_render", frame=f0)
                o.hide_render = False
                o.keyframe_insert("hide_render", frame=f1 + 1)
            for fc in stage.fcurves(o):
                if fc.data_path == "hide_render":
                    for kp in fc.keyframe_points:
                        kp.interpolation = "CONSTANT"

    def yaw_at(self, f):
        return self.track[f - 1]["yaw"]


def ind_window(s0, s1, side="R"):
    return lambda s, t: side if s0 <= s <= s1 else None


def cruise(s0, v, n):
    return [(s0 + v * k / FPS, v) for k in range(n)]


def slow(s0, v_real, n):
    """A slow-motion hold: the car moves v_real m/s on screen (s, v_real per frame)."""
    return [(s0 + v_real * k / FPS, v_real) for k in range(n)]


def stop_at(s0, v0, s_stop, n, t_brake=0.0, a_acc=2.2):
    return jx.kinematics(s0, v0, [(0, "cruise", v0), (t_brake, "stop", s_stop)], n, a_acc=a_acc)


def s_at_time(sv, t):
    return sv[min(len(sv) - 1, max(0, int(round(t * FPS))))][0]


def anchor(sv, t, s_target):
    """Shift a speed plan (built from s = 0) so that it is at s_target at time t."""
    off = s_target - s_at_time(sv, t)
    return [(s + off, v) for s, v in sv]


def t_when(sv, s_target):
    for k, (s, _v) in enumerate(sv):
        if s >= s_target:
            return k / FPS
    return len(sv) / FPS


# ------------------------------------------------------------------ near misses
def _corners(x, y, yaw, L, hw):
    c, s = math.cos(yaw), math.sin(yaw)
    out = []
    for u, v in ((L / 2, hw), (L / 2, -hw), (-L / 2, -hw), (-L / 2, hw), (L / 2, 0.0)):
        out.append((x + u * c - v * s, y + u * s + v * c))
    return out


def _gap(px, py, x, y, yaw, L, hw):
    c, s = math.cos(yaw), math.sin(yaw)
    dx, dy = px - x, py - y
    u, v = dx * c + dy * s, -dx * s + dy * c
    return math.hypot(max(abs(u) - L / 2, 0.0), max(abs(v) - hw, 0.0))


def stop_profile(s0, v0, s_stop, a, n):
    s_b = s_stop - v0 * v0 / (2 * a)
    if s_b < s0:
        a = v0 * v0 / (2 * max(0.05, s_stop - s0))
        s_b = s0
    t_b = (s_b - s0) / max(0.01, v0)
    out = []
    for k in range(n):
        t = k / FPS
        if t <= t_b:
            out.append((s0 + v0 * t, v0))
        else:
            tau = t - t_b
            v = v0 - a * tau
            out.append((s_b + v0 * tau - a * tau * tau / 2, v) if v > 0 else (s_stop, 0.0))
    return out


def min_gap(path, L, hw, sv, f0, others):
    g = 99.0
    for k, (s, _v) in enumerate(sv):
        x, y, yaw = pose(path, s, L)
        mine = _corners(x, y, yaw, L, hw)
        for act, ohw in others:
            p = act.poses[f0 + k - 1] if 0 <= f0 + k - 1 < len(act.poses) else None
            if p is None:
                continue
            ox, oy, oyaw = p[0], p[1], p[3]
            for qx, qy in mine:
                g = min(g, _gap(qx, qy, ox, oy, oyaw, act.L, ohw))
            for qx, qy in _corners(ox, oy, oyaw, act.L, ohw):
                g = min(g, _gap(qx, qy, x, y, yaw, L, hw))
    return g


def solve_stop(path, car, s0, v0, a, n, f0, others, target=0.35):
    """Brake profile (cruise at v0, then a m/s2) that stops as late as possible while every corner stays at least
    `target` metres from the other cars (others = [(actor, half width)]) on frames f0 .. f0 + n - 1."""
    L, hw = car["L"], car["W"] + 0.04
    s_free = s0 + v0 * n / FPS
    lo, hi = s0 + v0 * v0 / (2 * a) * 0.3, s_free
    if min_gap(path, L, hw, stop_profile(s0, v0, hi, a, n), f0, others) >= target:
        return stop_profile(s0, v0, hi, a, n)
    for _ in range(22):
        mid = (lo + hi) / 2
        if min_gap(path, L, hw, stop_profile(s0, v0, mid, a, n), f0, others) >= target:
            lo = mid
        else:
            hi = mid
    return stop_profile(s0, v0, lo, a, n)


def dive(sv, k_pitch=0.0055, tau=0.12):
    """Nose dive under braking (and a small lift on pulling away): pitch per frame from the speed list."""
    out, p = [], 0.0
    alpha = 1.0 - math.exp(-1.0 / (FPS * tau))
    prev = sv[0][1]
    for _s, v in sv:
        acc = (v - prev) * FPS
        prev = v
        p += (max(-0.05, min(0.03, k_pitch * acc)) - p) * alpha
        out.append(p)
    return out


# ------------------------------------------------------------------ cameras
def follow(actor, f, back, up, side=0.0, ahead=10.0, look_z=0.8, lag=5):
    """Chase position from the actor's smoothed pose at frame f: `back` metres behind, `side` to its right."""
    tr = actor.track
    lo, hi = max(1, f - lag), min(len(tr), f + lag)
    xs = [tr[i - 1]["x"] for i in range(lo, hi + 1) if tr[i - 1]["z"] > -1]
    ys = [tr[i - 1]["y"] for i in range(lo, hi + 1) if tr[i - 1]["z"] > -1]
    yaws = [tr[i - 1]["yaw"] for i in range(lo, hi + 1) if tr[i - 1]["z"] > -1]
    if not xs:
        p = tr[f - 1]
        xs, ys, yaws = [p["x"]], [p["y"]], [p["yaw"]]
    base = yaws[0]
    yw = [base + ((y - base + math.pi) % (2 * math.pi) - math.pi) for y in yaws]
    x, y, yaw = sum(xs) / len(xs), sum(ys) / len(ys), sum(yw) / len(yw)
    fwd = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    right = Vector((math.sin(yaw), -math.cos(yaw), 0.0))
    p = Vector((x, y, 0.0))
    return p - fwd * back + right * side + Vector((0, 0, up)), p + fwd * ahead + Vector((0, 0, look_z))


def driver_eye(actor, f, look=20.0, pan=0.0, z=1.22):
    """Driver's eye (left seat) and a target `look` metres ahead, turned by `pan` radians (+ left)."""
    p = actor.track[f - 1]
    yaw = p["yaw"]
    fwd = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    left = Vector((-math.sin(yaw), math.cos(yaw), 0.0))
    eye = Vector((p["x"], p["y"], z)) + left * 0.37 - fwd * 0.2
    d = Vector((math.cos(yaw + pan), math.sin(yaw + pan), 0.0))
    return eye, eye + d * look + Vector((0, 0, -0.35))


def two_shot(a, b, f, h=1.25, extra=4.5, push=0.12, t0=0.0, t1=1.0, swing=0.0):
    """Low camera that frames two actors as they stand at frame f, from the side of the line between them that
    faces away from the junction centre (houses behind them, not the island); pushes in by `push` over t0..t1."""
    pa = Vector((a.track[f - 1]["x"], a.track[f - 1]["y"], 0.0))
    pb = Vector((b.track[f - 1]["x"], b.track[f - 1]["y"], 0.0))
    mid = (pa + pb) / 2
    d = pb - pa
    n = Vector((-d.y, d.x, 0.0)).normalized() if d.length > 1e-3 else Vector((0, -1, 0))
    if n.dot(mid) < 0:
        n = -n
    if swing:
        c, s = math.cos(swing), math.sin(swing)
        n = Vector((n.x * c - n.y * s, n.x * s + n.y * c, 0.0))
    dist = max(6.5, 0.9 * d.length + extra)

    def fn(t):
        u = jx.ease((t - t0) / max(1e-6, t1 - t0))
        return mid + n * dist * (1.0 - push * u) + Vector((0, 0, h)), mid + Vector((0, 0, 0.75))
    return fn


def lerp(a, b, u):
    return Vector(a).lerp(Vector(b), jx.ease(u))


def orbit(center, r, h, a0, a1, t0, t1, tgt_z=0.0, tgt=None):
    def fn(t):
        u = jx.ease((t - t0) / max(1e-6, t1 - t0))
        a = math.radians(a0 + (a1 - a0) * u)
        c = Vector(center)
        pos = c + Vector((r * math.cos(a), r * math.sin(a), h))
        return pos, Vector(tgt) if tgt is not None else c + Vector((0, 0, tgt_z))
    return fn


def top(cx, cy, h, tilt=6.0, drift=(0.0, 0.0, 0.0), t0=0.0, t1=1.0):
    """Near-top view: camera above (cx, cy - tilt) looking at (cx, cy); drift moves it over the shot."""
    def fn(t):
        u = (t - t0) / max(1e-6, t1 - t0)
        d = Vector(drift) * u
        return Vector((cx + d.x, cy - tilt + d.y, h + d.z)), Vector((cx + d.x, cy + d.y, 0.0))
    return fn


# ------------------------------------------------------------------ look
def sun(assets, az_deg, elev_deg, energy=5.0, warm=(1.0, 0.8, 0.58), sky=0.7, cast=0.5):
    """Low warm late-afternoon sun (az from +x, anticlockwise) and a warm cast on the sky seen by the camera."""
    a = math.radians(az_deg)
    to_sun = Vector((math.cos(a), math.sin(a), 0))
    stage.sky(None, -to_sun, assets, sun_elev_deg=elev_deg, sun_energy=energy)
    s = bpy.data.objects["sun"]
    s.data.color = warm
    s.data.angle = math.radians(0.8)
    nt = bpy.context.scene.world.node_tree
    for n_ in nt.nodes:
        if n_.type == "BACKGROUND" and n_.name != "Background":
            n_.inputs["Strength"].default_value = sky
    env_n = next(n_ for n_ in nt.nodes if n_.type == "TEX_ENVIRONMENT")
    bg = nt.nodes["Background"]
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = cast
    mix.inputs["B"].default_value = (1.0, 0.8, 0.62, 1.0)
    nt.links.new(env_n.outputs["Color"], mix.inputs["A"])
    nt.links.new(mix.outputs["Result"], bg.inputs["Color"])


def finish_look(dist=950.0):
    skip = tuple(m.name for m in bpy.data.materials if m.name.startswith(OVERLAY))
    stage.hazify_all(dist=dist, color=(0.86, 0.76, 0.64), skip=skip)


# ------------------------------------------------------------------ life in the street
def walkers(S, tl, specs):
    """specs: [(path, s0, speed, seed)]: people (kit/figures.py) walking along a footway all the time. The paths
    run on footways only, so the ground is the kerb height everywhere on them."""
    out = []
    if F is None:
        return out
    try:
        import town as TN
        kh = TN.KERB_H
    except Exception:  # noqa: BLE001
        kh = KERB_H
    for k, (path, s0, v, seed) in enumerate(specs):
        sv = [(s0 + v * i / FPS, v) for i in range(tl.N)]  # jx.Path extrapolates past the end: straight on
        ped = F.person(S["env"], f"ped{k}", seed=seed, height=1.62 + 0.06 * (seed % 4),
                       bag=(None, "shoulder", "backpack", "tote")[seed % 4])
        F.walk(ped, path, sv, ground=lambda x, y, z=kh: z, look=[(2.0 + seed % 5, 3.2 + seed % 5, 35)])
        out.append(ped)
    return out


def cyclists(S, tl, specs):
    """specs: [(path, s0, speed, seed)]: a rider on a city bike (kit/figures.py) on the carriageway."""
    out = []
    if F is None:
        return out
    for k, (path, s0, v, seed) in enumerate(specs):
        sv = [(s0 + v * i / FPS, v) for i in range(tl.N)]  # jx.Path extrapolates past the end: straight on
        cy = F.cyclist(S["env"], f"cyc{k}", rider=dict(jacket=F.JACKETS[seed % len(F.JACKETS)]),
                       bike=dict(frame=("step", "diamond")[seed % 2], basket=seed % 2 == 0), helmet=seed % 3 == 0,
                       seed=seed)
        F.ride(cy, path, sv)
        out.append(cy)
    return out


def leaves(S, arms_frames):
    """arms_frames: [(direction (dx, dy), half width, s0, s1)] straight street pieces measured from the centre."""
    if TP is None:
        return
    for k, (d, hw, s0, s1) in enumerate(arms_frames):
        TP.leaves(S["env"], TP.Street((0, 0), d, hw, s0, s1, name=f"lv{k}"), s0, s1, seed=11 + k, n_per_m=4.0,
                  name=f"leaves{k}")


def line_path(a, b, n=40):
    a, b = Vector(a), Vector(b)
    return jx.Path([((a + (b - a) * k / n).x, (a + (b - a) * k / n).y) for k in range(n + 1)])


# ------------------------------------------------------------------ overlays
def _flat(name, pts, z, mat, c, parent):
    o = W.mesh_obj(name, [(x, y, z) for x, y in pts], [tuple(range(len(pts)))], mat, c)
    o.data.update()
    if o.data.polygons[0].normal.z < 0:
        o.data.flip_normals()
    o.parent = parent
    o.visible_shadow = False
    return o


def _pop(root, t_on, t_off, size=1.0):
    f_on, f_off = int(t_on * FPS) + 1, int(t_off * FPS) + 1
    for f, s in ((1, 0.0), (f_on, 0.0), (f_on + 4, 1.18), (f_on + 7, 1.0), (f_off, 1.0), (f_off + 5, 0.0)):
        root.scale = (s * size,) * 3
        root.keyframe_insert("scale", frame=f)


def icon_root(name, c, t_on, t_off, actor=None, loc=None, dz=2.4, size=1.0, ahead=0.0):
    """Camera-facing root (named badge_* so jx's loop turns it to the camera) that follows an actor (optionally
    `ahead` metres in front of it) or stands at loc."""
    root = bpy.data.objects.new("badge_icon_" + name, None)
    c.objects.link(root)
    if actor is not None:
        locs = []
        for tr in actor.track:
            ok = tr["z"] > -1
            locs.append((tr["x"] + math.cos(tr["yaw"]) * ahead, tr["y"] + math.sin(tr["yaw"]) * ahead,
                         (0.0 if ok else -80.0) + dz))
        stage.bake_motion(root, list(range(1, len(locs) + 1)), locs, [(0, 0, 0)] * len(locs))
        # rotation belongs to the render loop (face_camera keys it per frame): a baked (0, 0, 0) key on the next
        # frame would smear the icon round under motion blur
        ad = root.animation_data
        try:
            bag = ad.action.layers[0].strips[0].channelbag(ad.action_slot).fcurves
        except AttributeError:
            bag = ad.action.fcurves
        for fc in [fc for fc in bag if fc.data_path == "rotation_euler"]:
            bag.remove(fc)
    else:
        root.location = loc
    _pop(root, t_on, t_off, size)
    return root


def sign_icon(sign, c, t_on, t_off, width=1.6, actor=None, loc=None, dz=2.6, set_="de-core"):
    """A Commons sign face (unaltered, kit/signs.py) floating over a car, facing the camera."""
    root = icon_root(f"sign_{sign}", c, t_on, t_off, actor, loc, dz)
    f = SG.face(sign, c, width, set_, name=f"icon_sign_{sign}", emit=0.7)
    h = f["height"]
    f.rotation_euler = (-math.pi / 2, 0, 0)
    f.location = (0, -h / 2, 0)
    f.parent = root
    for o in [f] + list(f.children):
        o.visible_shadow = False
    return root


def arrow_icon(name, c, t_on, t_off, side="R", crossed=False, actor=None, loc=None, dz=2.6, size=1.7,
               blink=True, ahead=0.0, angle=None, color=AMBER):
    """Indicator icon: an amber arrow on a dark rounded plate, blinking at 1.5 Hz; crossed = red ring and bar.
    angle (degrees, top views only): point the arrow in that world direction instead of left or right."""
    root = icon_root(name, c, t_on, t_off, actor, loc, dz, size, ahead)
    plate = jx.flat_mat("icon_plate_" + name, (0.03, 0.03, 0.035), emit=0.0)
    white = jx.flat_mat("icon_rim_" + name, (1, 1, 1), emit=1.4)
    amber = jx.flat_mat("icon_amber_" + name, color, emit=6.0)
    _flat(name + "_rim", W.rounded_rect(1.0, 1.0, 0.2), 0.0, white, c, root)
    _flat(name + "_plate", W.rounded_rect(0.9, 0.9, 0.16), 0.01, plate, c, root)
    sx = 1 if side == "R" else -1
    arrow = [(-0.32, -0.08), (0.06, -0.08), (0.06, -0.22), (0.34, 0.0), (0.06, 0.22), (0.06, 0.08), (-0.32, 0.08)]
    if angle is not None:
        ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        arrow = [(x * ca - y * sa, x * sa + y * ca) for x, y in arrow]
        sx = 1
    _flat(name + "_arrow", [(sx * x, y) for x, y in arrow], 0.02, amber, c, root)
    if crossed:
        red = jx.flat_mat("icon_red_" + name, (0.95, 0.06, 0.04), emit=3.0)
        n = 48
        ring = [(0.47 * math.cos(2 * math.pi * k / n), 0.47 * math.sin(2 * math.pi * k / n)) for k in range(n)]
        inner = [(0.39 * math.cos(2 * math.pi * k / n), 0.39 * math.sin(2 * math.pi * k / n)) for k in range(n)]
        verts = [(x, y, 0.03) for x, y in ring] + [(x, y, 0.03) for x, y in inner]
        faces = [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
        o = W.mesh_obj(name + "_ring", verts, faces, red, c)
        for p in o.data.polygons:
            if p.normal.z < 0:
                p.flip()
        o.parent = root
        o.visible_shadow = False
        a = math.radians(45)
        d, w = Vector((math.cos(a), math.sin(a))), 0.05
        nrm = Vector((-d.y, d.x))
        q = [d * -0.4 + nrm * w, d * 0.4 + nrm * w, d * 0.4 - nrm * w, d * -0.4 - nrm * w]
        _flat(name + "_bar", [(v.x, v.y) for v in q], 0.04, red, c, root)
        blink = False
    if blink:
        inp = amber.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
        f_on, f_off = int(t_on * FPS) + 1, int(t_off * FPS) + 1
        f = f_on
        while f < f_off:
            for df, val in ((0, 6.0), (10, 0.4)):
                inp.default_value = val
                inp.keyframe_insert("default_value", frame=f + df)
            f += 20
        for fc in stage.fcurves(amber.node_tree):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
    return root


def number_badge(n, actor, c, fnt, t_on, t_off, size=3.0):
    return jx.badge(str(n), actor.car, c, fnt, t_on, t_off, size=size, color=GREEN)


def letter_badge(letter, actor, c, fnt, t_on, t_off, size=3.0):
    return jx.badge(letter, actor.car, c, fnt, t_on, t_off, size=size)


def question(actor, c, fnt, t_on, t_off, size=2.4):
    return jx.badge("?", actor.car, c, fnt, t_on, t_off, size=size, color=YELLOW)


def ribbon(path, s0, s1, color, c, t_on, t_off, width=1.1, name="rib"):
    return jx.ribbon(path, s0, s1, color, c, t_on, t_off, width=width, name=name)


def circle_path(r, a0_deg, a1_deg, n=180):
    """Anticlockwise arc of radius r from a0 to a1 (degrees) as a jx.Path."""
    pts = []
    for k in range(n + 1):
        a = math.radians(a0_deg + (a1_deg - a0_deg) * k / n)
        pts.append((r * math.cos(a), r * math.sin(a)))
    return jx.Path(pts)


# ------------------------------------------------------------------ end card
def end_card(tl, seg, shots, stacks, c, z=-300.0, diagram=None):
    """Road-grey card for the END segment: the episode's signs as flat call-outs (Commons files, unaltered) side by
    side (stacks = [[(set, id, width), ...], ...], each stack top to bottom), a broken edge line at the foot. Emissive
    materials, under the ground, seen by an orthographic camera that slowly closes in. diagram: optional fn(c, z) for
    episodes without signs."""
    card = jx.flat_mat("card_grey", (0.06, 0.062, 0.068), emit=1.0)
    paint = jx.flat_mat("card_paint", (0.92, 0.92, 0.9), emit=1.4)
    W.mesh_obj("card", [(-6, -10, z), (6, -10, z), (6, 10, z), (-6, 10, z)], [(0, 1, 2, 3)], card, c)
    for k in range(-5, 6):
        x0 = k * 1.2
        q = [(x0, -6.55, z + 0.002), (x0 + 0.7, -6.55, z + 0.002), (x0 + 0.7, -6.4, z + 0.002),
             (x0, -6.4, z + 0.002)]
        W.mesh_obj("card_dash", q, [(0, 1, 2, 3)], paint, c)
    n = len(stacks)
    gap = 0.5
    faces = [[(SG.face(id_, c, w, set_, name=f"card_sign_{id_}", emit=1.2, back=False), w) for set_, id_, w in st]
             for st in stacks]
    # the signs sit between the end lines (above y -0.55) and the two-line source footer (a2post.foot_lines, first
    # line's ink from caption y 1414 of 1920, y -3.7 here at the closing ortho scale): a tall stack (a sign with its
    # plate) is scaled down to fit 2.6 units (bottom at y -3.15, caption y about 1350)
    tallest = max([sum(f["height"] + 0.12 for f, _w in st) - 0.12 for st in faces] or [0.0])
    k = min(1.0, 2.6 / tallest) if tallest > 0 else 1.0
    widths = [max(w for _f, w in st) * k for st in faces]
    total = sum(widths) + gap * (n - 1)
    x = -total / 2
    for st, wmax in zip(faces, widths):
        y = -0.55
        cx = x + wmax / 2
        for f, _w in st:
            h = f["height"] * k
            f.scale = (k, k, k)
            f.rotation_euler = (-math.pi / 2, 0, 0)
            f.location = (cx, y - h, z + 0.01)
            y -= h + 0.12
        x += wmax + gap
    if diagram:
        diagram(c, z)
    cam = bpy.data.cameras.new("cam_end")
    cam.type = "ORTHO"
    cam.sensor_fit = "VERTICAL"
    cam.ortho_scale = 16.0
    cam.clip_start, cam.clip_end = 1.0, 50.0
    co = bpy.data.objects.new("cam_end", cam)
    bpy.context.scene.collection.objects.link(co)
    co.location = (0, 0, z + 20)
    co.rotation_euler = (0, 0, 0)
    f0, f1 = tl.f0(seg), tl.f1(seg)
    for f, s in ((f0, 16.4), (f1, 15.6)):
        cam.ortho_scale = s
        cam.keyframe_insert("ortho_scale", frame=f)
    shots.list.append((co.name, f0, f1))
    m = bpy.context.scene.timeline_markers.new(co.name, frame=f0)     # jx binds cameras to markers too
    m.camera = co
    return co


# ------------------------------------------------------------------ render
def render(shots, out, todo, no_blur):
    sc = bpy.context.scene
    os.makedirs(out, exist_ok=True)
    badges = jx.badge_roots()
    mb = sc.render.use_motion_blur  # after render_setup: kit/perf.py turns it off for previews
    for f in todo:
        sc.frame_set(f)
        cam = shots.camera_at(f) or sc.camera
        if sc.camera != cam:  # as jx.render_frames: a camera assignment rebuilds the depsgraph relations
            sc.camera = cam
        sc.render.use_motion_blur = mb and f not in no_blur
        if badges and sc.camera:  # keyed at f: the render evaluates its own depsgraph, no 2nd frame_set
            jx.face_camera(badges, sc.camera, f)
        sc.render.filepath = os.path.join(out, f"f_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("Saved", sc.render.filepath, flush=True)


def probe(frames):
    """Debug: overlay ribbon factors and object visibility at the given frames."""
    sc = bpy.context.scene
    for f in frames:
        sc.frame_set(f)
        for m in bpy.data.materials:
            if m.name.startswith("rib") and m.node_tree:
                mx = [n for n in m.node_tree.nodes if n.type == "MIX_SHADER"]
                o_ = bpy.data.objects.get(m.name)
                print("PROBE", f, m.name, [round(n.inputs[0].default_value, 3) for n in mx],
                      None if o_ is None else (o_.hide_render, tuple(round(v, 2) for v in o_.matrix_world.translation),
                                               len(o_.data.polygons), o_.data.materials[0].name), flush=True)


def hide_idle_ribbons(n):
    """jx.ribbon fades to a fully transparent material but stays in the scene. Where five ribbons overlap (the
    circulating lane of a quiz roundabout) a camera ray passes more transparent layers than Cycles allows
    (stage: transparent_max_bounces 4) and the road under them renders black. Hide each ribbon on every frame
    where its fade factor is zero (keyed hide_render, constant)."""
    for ob in bpy.data.objects:
        if ob.type != "MESH" or not ob.data.materials or ob.data.materials[0] is None:
            continue
        m = ob.data.materials[0]
        ad = m.node_tree.animation_data if m.node_tree else None
        if not m.name.startswith(("rib", "glow")) or not ad or not ad.action:
            continue
        fcs = [fc for fc in stage.fcurves(m.node_tree) if "inputs[0]" in fc.data_path]
        if not fcs:
            continue
        fc, prev = fcs[0], None
        for f in range(1, n + 1):
            off = max(fc.evaluate(f - 0.5), fc.evaluate(f), fc.evaluate(f + 0.5)) < 1e-3
            if off != prev:
                ob.hide_render = off
                ob.keyframe_insert("hide_render", frame=f)
                prev = off


def setup_render(o, tl):
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, tl.N
    hide_idle_ribbons(tl.N)
    finish_look()
    stage.render_setup(o["SAMPLES"], o["RES"], int(round(o["RES"] * 16 / 9)), motion_blur=True)
    sc.render.motion_blur_shutter = 0.5


def todo_frames(o, tl):
    if o["STILLS"]:
        return o["STILLS"]
    if o["FR"]:
        return list(range(o["FR"][0], o["FR"][1] + 1))
    return list(range(1, tl.N + 1))
