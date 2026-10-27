"""Shared scene helpers for the A4 Autobahn episodes (13 speed trailer, 15 zipper merge, 24 red X, 29 roadworks lines).
Not an episode: the public build copies every ep[0-9][0-9]_*.py flat into drivelocal/, so the four scenes import this
file as `ep13_zkit` there (locally they add ../ep13 to sys.path). Candidate for kit/ (suggested name kit/autoshots.py).

- cli(): the episode CLI (OUT --frames a-b | --stills a,b --res --samples --assets)
- Canon: the canonical segment timeline (the per-language cuts reorder these segments at compose time)
- prebuild(fn): build vehicles right after the empty scene exists (operators are slow in the full world)
- world(): the approved episode 1 stage on a longer road (4 km), unchanged kit code
- Sim: small lane traffic simulator: IDM car following, keep right, overtake on the left only, no passing on the right
  above 60 km/h, trucks never in the left lane, mandatory merges for closed lanes, zipper turn-taking at a lane end,
  courtesy gaps, an indicator on every lane change (1 s before the move, during it, and a moment after)
- Director: shots map canonical time to a world time of one simulated variant (a cut may jump in place and time);
  every vehicle of every variant becomes one rigged instance baked through kit/motion.py (wheels, steering, brake
  lights from deceleration, indicators, police beacons); cameras are baked per shot
- cockpit(): dashboard, gauge (ticks and a limit mark, no numerals), needle from the hero's speed, steering wheel,
  bonnet: the driver POV
- hud_sign / hud_bar / hud_flash / hud_icon: camera-space call-outs (signs only through signs.py, unaltered pictures)
- end_card(): road-grey card with the episode's signs as flat call-outs
- golden(), bloom(), render()
Pure-python parts (Sim) import without bpy, for tests."""
import math
import os
import random
import sys
from bisect import bisect_right

try:
    import bpy
    from mathutils import Matrix, Vector
except ImportError:          # the traffic simulator runs without Blender (tests)
    bpy = None

FPS = 30
DT = 1.0 / FPS
PROBE = "--probe" in sys.argv     # light world for quick local framing checks (never for previews or finals)
T_START = __import__("time").time()


def tick(label):
    print(f"[{__import__('time').time() - T_START:6.1f}s] {label}", flush=True)
LANES = (4.625, 8.375, 12.125)


def smooth(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def smoother(u):
    u = min(1.0, max(0.0, u))
    return u * u * u * (u * (u * 6 - 15) + 10)


def kmh(v):
    return v / 3.6


# ---------------------------------------------------------------------------------------------------------- CLI
def cli(res=540, samples=8):
    o = dict(OUT="frames", RES=res, SAMPLES=samples, ASSETS="assets", FR=None, STILLS=None, BLEND=None)
    a = sys.argv
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
        if x == "--blend":
            o["BLEND"] = a[i + 1]
    return o


class Canon:
    """Segments in canonical (English) order: [(name, seconds)]. start[name] in seconds, frame() 1-based."""

    def __init__(self, segs):
        self.segs = list(segs)
        self.start, t = {}, 0.0
        for n, d in segs:
            self.start[n] = round(t, 4)
            t += d
        self.T = round(t, 4)
        self.N = int(round(self.T * FPS))
        self.dur = dict(segs)

    def t(self, seg, rel=0.0):
        return round(self.start[seg] + rel, 4)

    @staticmethod
    def frame(t):
        return int(round(t * FPS)) + 1

    def spans(self):
        return {n: [self.start[n], round(self.start[n] + d, 4)] for n, d in self.segs}


# ------------------------------------------------------------------------------------------- traffic simulator
KIND = {
    "car": dict(a=1.7, b=3.0, T=1.05, s0=2.2),
    "van": dict(a=1.3, b=2.6, T=1.25, s0=2.4),
    "truck": dict(a=0.7, b=2.2, T=1.6, s0=3.0),
}
MIN_LANE = {"car": 0, "van": 0, "truck": 1}


def idm(v, v0, gap, dv, a, b, T, s0):
    ss = s0 + max(0.0, v * T + v * dv / (2.0 * math.sqrt(a * b)))
    free = a * (1.0 - (v / max(v0, 0.1)) ** 4)
    return max(-9.0, free - a * (ss / max(gap, 0.05)) ** 2)


class Veh:
    def __init__(self, vid, kind, model, L, lane, s, v, v0, phase, policy=None):
        k = KIND[kind]
        self.id, self.kind, self.model, self.L = vid, kind, model, L
        self.lane, self.tgt, self.p = lane, None, 0.0
        self.s, self.v, self.v0 = s, v, v0
        self.a, self.b, self.T, self.s0 = k["a"], k["b"], k["T"], k["s0"]
        self.plan, self.plan_t, self.plan_age, self.mand = None, 0.0, 0.0, False
        self.ind, self.ind_tail = None, 0.0
        self.phase = phase
        self.policy = dict(policy or {})
        self.alive = True
        self.lc_dur = 3.0
        self.scripted = False

    def lanes(self):
        return (self.lane,) if self.tgt is None else (self.lane, self.tgt)

    def lanef(self):
        if self.tgt is None:
            return float(self.lane)
        return self.lane + (self.tgt - self.lane) * smoother(self.p)


class Script:
    """A choreographed vehicle inside a simulation: fn(T) -> dict(s, lane (float), v, ind, beacon, x) or None (absent).
    Simulated traffic reacts to it (follows it, gives way when it indicates and moves over)."""

    def __init__(self, vid, model, L, fn, kind="car"):
        self.id, self.model, self.L, self.fn, self.kind = vid, model, L, fn, kind
        self.scripted = True
        self.st = None

    def lanes_at(self, st):
        lf = st["lane"]
        r = int(round(lf))
        out = [r]
        if abs(lf - r) > 0.12:
            out.append(r + (1 if lf > r else -1))
        return out


class Sim:
    """lanes 0 (left) .. nl-1 (right). closures: (lane, s_warn, s_block, s_end): from s_warn vehicles in that lane must
    move out, the lane is blocked from s_block (a virtual standing obstacle) to s_end. zipper: (lane_c, lane_t, s_m):
    lane_c ends at s_m; drivers with policy late=True use it to the end and take turns with lane_t (one car each).
    limits: (s_from, s_to, m/s), anticipated 150 m ahead. Trucks keep to lanes >= 1."""

    def __init__(self, s_lo, s_hi, nl=3, seed=1, T0=0.0):
        self.s_lo, self.s_hi, self.nl = s_lo, s_hi, nl
        self.rnd = random.Random(seed)
        self.vs, self.scripts = [], []
        self.closures, self.limits = [], []
        self.zipper = None
        self.zip_turn = "c"
        self.T = T0
        self.rec_T0 = None
        self.rec = {}            # id -> list of (s, lanef, v, ind) or None (absent)
        self.n_steps = 0
        self.inflow = []         # (lane, headway s, [(kind, model, L, weight)], v_lo, v_hi)
        self._next_spawn = {}
        self._uid = 0
        self.models = {}
        self.events = []
        self.max_v0 = {}
        self._yield_prev, self._yield_now = set(), set()

    # ---------------------------------------------------------------- setup
    def set_models(self, models):
        """models: {"car": [(model, L), ...], "van": [...], "truck": [...]}"""
        self.models = models

    def pick(self, kind):
        return self.rnd.choice(self.models[kind])

    def add(self, kind, lane, s, v, v0=None, model=None, policy=None, vid=None, L=None):
        if model is None:
            model, L = self.pick(kind)
        elif L is None:
            L = dict(self.models[kind])[model]
        self._uid += 1
        vid = vid or f"v{self._uid}"
        v0 = v0 or v
        car = Veh(vid, kind, model, L, lane, s, v, v0, self.rnd.random() * 0.5, policy)
        self.vs.append(car)
        return car

    def script(self, vid, model, L, fn, kind="car"):
        sc = Script(vid, model, L, fn, kind)
        self.scripts.append(sc)
        return sc

    def fill(self, lane, s_from, s_to, headway, v, kinds, v0_range=None, jam_gap=None, policy=None):
        """Seed a lane with vehicles from s_to back to s_from. headway in s at speed v (or a fixed gap jam_gap)."""
        s = s_to
        while s > s_from:
            kind = self._kind(kinds)
            model, L = self.pick(kind)
            v0 = self.rnd.uniform(*v0_range) if v0_range else v
            if kind == "truck":
                v0 = min(v0, kmh(self.rnd.uniform(80, 88)))
            pol = policy(self) if callable(policy) else policy
            # never seed a car inside a closed lane (or just before its block point): the random draws stay the same
            if not any(l == lane and sb - 150.0 <= s - L / 2 <= se for (l, _sw, sb, se) in self.closures):
                self.add(kind, lane, s - L / 2, min(v, v0), v0, model, pol)
            gap = jam_gap() if callable(jam_gap) else (jam_gap if jam_gap is not None else
                                                       max(8.0, v * headway * self.rnd.uniform(0.7, 1.6)))
            s -= L + gap

    def _kind(self, kinds):
        tot = sum(w for _k, w in kinds)
        r = self.rnd.random() * tot
        for k, w in kinds:
            r -= w
            if r <= 0:
                return k
        return kinds[-1][0]

    # ---------------------------------------------------------------- road rules
    def blocked(self, lane, s):
        for (l, sw, sb, se) in self.closures:
            if l == lane and sw <= s <= se:
                return True
        if self.zipper and lane == self.zipper[0] and s >= self.zipper[2] - 1.0:
            return True
        return lane < 0 or lane >= self.nl

    def open_ahead(self, lane, s, dist):
        for (l, sw, sb, se) in self.closures:
            if l == lane and s - 20 <= se and sw <= s + dist:
                return False
        if self.zipper and lane == self.zipper[0] and self.zipper[2] - 400 <= s + dist and s < self.zipper[2]:
            return False
        return 0 <= lane < self.nl

    def v0_eff(self, car):
        v0 = car.v0
        front = car.s + car.L / 2
        for (a, b, vl) in self.limits:
            if a - 150.0 <= front <= b:
                v0 = min(v0, vl * car.policy.get("speeding", 1.0))
        return v0

    # ---------------------------------------------------------------- neighbours
    def _build_occ(self):
        occ = {l: [] for l in range(-1, self.nl + 1)}
        for c in self.vs:
            if c.alive:
                for l in c.lanes():
                    occ[l].append((c.s, c.L, c.v, c))
        for sc in self.scripts:
            st = sc.fn(self.T)
            sc.st = st
            if st is None or st.get("ghost"):
                continue
            for l in sc.lanes_at(st):
                if l in occ:
                    occ[l].append((st["s"], sc.L, st["v"], sc))
        for l in occ:
            occ[l].sort(key=lambda e: e[0])
        self.occ = occ
        self.keys = {l: [e[0] for e in occ[l]] for l in occ}

    def leader(self, car, lane, s=None):
        s = car.s if s is None else s
        lst = self.occ.get(lane, [])
        i = bisect_right(self.keys[lane], s)
        for j in range(max(0, i - 2), len(lst)):
            so, Lo, vo, o = lst[j]
            if o is car or so < s or (so == s and id(o) <= id(car)):
                continue
            return (so - Lo / 2 - (s + car.L / 2), vo, o)
        return None

    def follower(self, car, lane, s=None):
        s = car.s if s is None else s
        lst = self.occ.get(lane, [])
        i = bisect_right(self.keys[lane], s)
        for j in range(min(len(lst) - 1, i + 1), -1, -1):
            so, Lo, vo, o = lst[j]
            if o is car or so > s or (so == s and id(o) >= id(car)):
                continue
            return (s - car.L / 2 - (so + Lo / 2), vo, o)
        return None

    # ---------------------------------------------------------------- behaviour
    def accel(self, c):
        v0 = self.v0_eff(c)
        # no passing on the right above 60 km/h: hold behind a slower car in the lane to the left
        if c.lane > 0 and c.v > 16.7:
            ld = self.leader(c, c.lane - 1, c.s - c.L / 2 - 4.0)
            if ld and ld[0] < 25.0 and ld[1] < c.v:
                v0 = min(v0, ld[1] + 0.4)
        acc = c.a * (1 - (c.v / max(v0, 0.1)) ** 4)
        cands = []
        for l in c.lanes():
            ld = self.leader(c, l)
            if ld:
                cands.append((ld[0], ld[1]))
        z = self.zipper
        front = c.s + c.L / 2
        # beside a standing queue the free lane rolls at walking pace plus a little (no racing past the jam)
        if z and c.lane == z[0] and z[2] - 900.0 < front < z[2]:
            adj = self.leader(c, z[1], c.s - 12.0)
            if adj and adj[0] < 30.0:
                v0 = min(v0, adj[1] + 5.0)
        # a car that must merge lines up behind the car it will slot in behind (it does not race past the gap);
        # early mergers beside a jam keep rolling instead and take the gap a driver leaves them
        squeeze = z and c.lane == z[0] and not c.policy.get("late", True)
        if c.plan is not None and c.mand and c.tgt is None and c.plan_t > 0.5 and \
                (not squeeze or c.id in self._yield_prev):
            ld = self.leader(c, c.plan, c.s - 0.3 * c.L)
            if ld:
                cands.append((ld[0] - 0.3 * c.L, ld[1]))
        for (l, sw, sb, se) in self.closures:
            if l in c.lanes() and front < sb + 1.0 and not (c.tgt is not None and c.tgt != l and c.p > 0.45):
                if not (c.tgt is not None and c.tgt == l):
                    cands.append((sb - front, 0.0))
        if z and c.lane == z[0] and not (c.tgt is not None and c.p > 0.45):
            cands.append((z[2] - front, 0.0))
        # courtesy: give way to a car that indicates into this lane and is alongside or ahead
        y = self.yield_to(c)
        if y is not None:
            cands.append(y)
        for gap, vl in cands:
            acc = min(acc, idm(c.v, v0, gap, c.v - vl, c.a, c.b, c.T, c.s0))
        return acc

    def yield_to(self, c):
        """A car indicating into c's lane, alongside or ahead of c, gets a gap: only from the car right behind the
        spot it will take (c's own leader is ahead of the merger). At speed only when the merger is fully ahead."""
        if c.tgt is not None or c.scripted:
            return None
        best = None
        z = self.zipper
        ld_c = self.leader(c, c.lane)
        for o in self.vs:
            if not o.alive or o is c or o.plan != c.lane or o.plan_t < 0.6 or o.tgt is not None:
                continue
            if o.lane == c.lane:
                continue
            if not o.mand and c.v > 12.0:
                continue
            if z and o.lane == z[0] and c.lane == z[1] and o.policy.get("late", True) and self.zip_turn != "c":
                continue
            d = o.s - c.s
            if not (0.3 * min(c.L, 5.0) < d < 35.0):
                continue
            if ld_c is not None and ld_c[2] is not o:
                lo = ld_c[2]
                lo_s = lo.st["s"] if getattr(lo, "scripted", False) else lo.s
                if lo_s < o.s:
                    continue
            gap = o.s - o.L / 2 - (c.s + c.L / 2)
            if c.v > 12.0 and gap < 0.5:
                continue
            if best is None or gap < best[0]:
                best = (max(0.3, gap), o.v)
                self._yield_now.add(o.id)
        for sc in self.scripts:
            st = sc.st
            if st is None or st.get("ghost") or not st.get("ind") or st["ind"] == "H":
                continue
            want = int(round(st["lane"])) + (1 if st["ind"] == "R" else -1)
            if c.lane not in (want, int(round(st["lane"]))) or st.get("no_yield"):
                continue
            d = st["s"] - c.s
            if -0.2 * c.L < d < 40.0:
                gap = st["s"] - sc.L / 2 - (c.s + c.L / 2)
                if best is None or gap < best[0]:
                    best = (max(0.3, gap), st["v"])
        return best

    def gap_ok(self, c, lane, mand):
        if self.blocked(lane, c.s + c.L / 2) and not (self.zipper and lane == self.zipper[1]):
            return False
        ld = self.leader(c, lane)
        fl = self.follower(c, lane)
        slow = c.v < 8.0
        if ld:
            need = (1.2 if slow else max(3.0, 0.35 * c.v)) if mand else max(5.0, 0.6 * c.v)
            if ld[0] < need:
                return False
        if fl:
            vf = fl[1]
            need = (1.0 if (slow and vf < 8.0) else max(3.0, 0.45 * vf)) if mand else max(6.0, 0.8 * vf)
            if fl[0] < need:
                return False
            o = fl[2]
            if not getattr(o, "scripted", False) and o.v > 3.0:
                if idm(o.v, o.v0, fl[0], o.v - c.v, o.a, o.b, o.T, o.s0) < (-4.5 if mand else -2.0):
                    return False
        return True

    def desire(self, c):
        """(target lane, mandatory) or (None, False)."""
        l = c.lane
        front = c.s + c.L / 2
        lo = MIN_LANE[c.kind]
        if l < lo:
            return l + 1, True
        z = self.zipper
        if z and l == z[0]:
            late = c.policy.get("late", True)
            start = z[2] - (70.0 if late else c.policy.get("early_at", 500.0))
            if front >= start:
                return z[1], True
            return None, False
        for (cl, sw, sb, se) in self.closures:
            if cl == l and sw <= front <= se:
                for t in ((l + 1, l - 1) if l < self.nl - 1 else (l - 1, l + 1)):
                    if lo <= t < self.nl and not self.blocked(t, front):
                        return t, True
        if c.policy.get("stay"):
            return None, False
        # keep right
        if l + 1 < self.nl and self.open_ahead(l + 1, front, 350.0):
            ld = self.leader(c, l + 1)
            v0 = self.v0_eff(c)
            if ld is None or ld[0] > max(70.0, c.v * 5.0) or ld[1] >= v0 - 1.0:
                if self.gap_ok(c, l + 1, False):
                    return l + 1, False
        # overtake on the left
        if l - 1 >= lo and self.open_ahead(l - 1, front, 300.0) and c.v > 6.0:
            ld = self.leader(c, l)
            v0 = self.v0_eff(c)
            slower = 3.0 if c.kind != "truck" else 5.0
            if ld and ld[0] < max(25.0, c.v * 3.2) and ld[1] < v0 - slower:
                l2 = self.leader(c, l - 1)
                if l2 is None or l2[0] > c.v * 2.5 or l2[1] > ld[1] + 4.0:
                    return l - 1, False
        return None, False

    def decide(self, c):
        if c.tgt is not None:
            return
        want, mand = self.desire(c)
        if want is None:
            if c.plan is not None and not c.mand:
                c.plan, c.plan_t = None, 0.0
            return
        if c.plan != want:
            c.plan, c.plan_t, c.plan_age, c.mand = want, 0.0, 0.0, mand
        c.mand = mand
        if c.plan_t >= 1.0 and self.gap_ok(c, want, mand):
            if self.zipper and c.lane == self.zipper[0] and want == self.zipper[1] and c.policy.get("late", True):
                if self.zip_turn != "c":
                    return
            c.tgt, c.p = want, 0.0
            c.lc_dur = 1.9 if c.v < 3 else (2.2 if c.v < 6 else (2.6 if c.v < 15 else 3.4))
        elif not mand and c.plan_age > 5.0:
            c.plan, c.plan_t = None, 0.0

    # ---------------------------------------------------------------- run
    def spawn(self):
        for (lane, headway, kinds, vlo, vhi) in self.inflow:
            nxt = self._next_spawn.get(lane, self.T)
            if self.T < nxt:
                continue
            lst = self.occ.get(lane, [])
            first = lst[0] if lst else None
            kind = self._kind(kinds)
            model, L = self.pick(kind)
            v0 = self.rnd.uniform(vlo, vhi)
            if kind == "truck":
                v0 = min(v0, kmh(self.rnd.uniform(80, 88)))
            s = self.s_lo
            if first is not None:
                gap = first[0] - first[1] / 2 - (s + L / 2)
                v = min(v0, first[2] + 2.0)
                if gap < max(10.0, v * 1.2):
                    self._next_spawn[lane] = self.T + 0.5
                    continue
            else:
                v = v0
            self.add(kind, lane, s, v, v0, model)
            self._next_spawn[lane] = self.T + headway * self.rnd.uniform(0.6, 1.5)

    def step(self, record=True):
        self._build_occ()
        live = [c for c in self.vs if c.alive]
        self._yield_prev = getattr(self, "_yield_now", set())
        self._yield_now = set()
        acc = {c.id: self.accel(c) for c in live}
        for c in live:
            if int((self.T + c.phase) * 2.0) != int((self.T + c.phase - DT) * 2.0):
                self.decide(c)
        z = self.zipper
        for c in live:
            a = acc[c.id]
            v_old = c.v
            c.v = max(0.0, c.v + a * DT)
            c.s += 0.5 * (v_old + c.v) * DT
            if c.plan is not None:
                c.plan_t += DT
                c.plan_age += DT
            if c.tgt is not None:
                c.p += DT / c.lc_dur
                if c.p >= 1.0:
                    if z and c.lane == z[0] and c.tgt == z[1]:
                        self.zip_turn = "t"
                        self.events.append((self.T, "zip", c.id))
                    c.lane, c.tgt, c.p = c.tgt, None, 0.0
                    c.plan, c.plan_t = None, 0.0
                    c.ind_tail = 0.5
            if c.plan is not None:
                c.ind = "L" if c.plan < c.lane else "R"
            elif c.ind_tail > 0:
                c.ind_tail -= DT
            else:
                c.ind = None
            if z and c.lane == z[1] and c.tgt is None and c.s + c.L / 2 >= z[2] > c.s + c.L / 2 - c.v * DT - 1e-6:
                if self.zip_turn == "t":
                    self.zip_turn = "c"
            if c.s - c.L / 2 > self.s_hi:
                c.alive = False
        self.spawn()
        if record:
            if self.rec_T0 is None:
                self.rec_T0 = self.T
            k = self.n_steps
            for c in self.vs:
                r = self.rec.setdefault(c.id, [])
                if len(r) < k:
                    r.extend([None] * (k - len(r)))
                r.append((c.s, c.lanef(), c.v, c.ind) if c.alive else None)
            self.n_steps += 1
        self.T += DT

    def run(self, T_warm, T_end, verbose=False):
        """Warm up (not recorded) until T_warm, then record until T_end."""
        while self.T < T_warm - 1e-9:
            self.step(record=False)
        while self.T < T_end - 1e-9:
            self.step(record=True)
        for r in self.rec.values():
            if len(r) < self.n_steps:
                r.extend([None] * (self.n_steps - len(r)))
        if verbose or bpy is not None:
            tick(f"sim {len(self.vs)} vehicles, {self.n_steps} steps")
        return self

    def sample(self, vid, T):
        """State of a simulated vehicle at world time T (nearest recorded step), or None."""
        r = self.rec.get(vid)
        if r is None or self.rec_T0 is None:
            return None
        i = int(round((T - self.rec_T0) / DT))
        if i < 0 or i >= len(r) or r[i] is None:
            return None
        s, lf, v, ind = r[i]
        return dict(s=s, lane=lf, v=v, ind=ind)

    def lane_changes(self, vid):
        """[(T_start, T_end, from_lane, to_lane, T_indicator_on)] of a simulated vehicle, from the record."""
        r = self.rec.get(vid) or []
        out, i = [], 0
        while i < len(r):
            if r[i] is not None and abs(r[i][1] - round(r[i][1])) > 1e-3:
                j = i
                while j < len(r) and r[j] is not None and abs(r[j][1] - round(r[j][1])) > 1e-3:
                    j += 1
                k = i
                while k > 0 and r[k - 1] is not None and r[k - 1][3] is not None:
                    k -= 1
                frm = round(r[i - 1][1]) if i > 0 and r[i - 1] else round(r[i][1])
                to = round(r[j][1]) if j < len(r) and r[j] else frm
                out.append((self.rec_T0 + i * DT, self.rec_T0 + j * DT, frm, to, self.rec_T0 + k * DT))
                i = j
            i += 1
        return out

    def find(self, vid):
        for c in self.vs:
            if c.id == vid:
                return c
        return None

    def drop_conflicts(self, margin=2.0, keep=("hero",)):
        """Scripted vehicles do not react to simulated ones: drop every simulated vehicle that would come closer than
        `margin` metres (bumper to bumper) to a scripted one in the same lane at any recorded step."""
        drop = set()
        for sc in self.scripts:
            for i in range(self.n_steps):
                T = self.rec_T0 + i * DT
                st = sc.fn(T)
                if st is None or st.get("ghost"):
                    continue
                for c in self.vs:
                    if c.id in drop or c.id in keep:
                        continue
                    r = self.rec[c.id][i]
                    if r is None:
                        continue
                    if abs(r[1] - st["lane"]) > 0.75:
                        continue
                    d = abs(r[0] - st["s"]) - (c.L + sc.L) / 2
                    if d < margin:
                        drop.add(c.id)
        self.dropped = drop
        print("dropped", len(drop), "vehicles in conflict with scripted ones", flush=True)
        return drop

    def ids(self):
        dr = getattr(self, "dropped", set())
        return [c.id for c in self.vs if c.id not in dr] + [sc.id for sc in self.scripts]

    def model_of(self, vid):
        for c in self.vs:
            if c.id == vid:
                return c.model, c.kind
        for sc in self.scripts:
            if sc.id == vid:
                return sc.model, sc.kind
        return None, None


def lane_change(t, t0, dur, l0, l1):
    """Lane position for a scripted change that starts at t0 and takes dur seconds (smoother step)."""
    return l0 + (l1 - l0) * smoother((t - t0) / dur)


class Kin:
    """Scripted longitudinal motion: pieces [(t, cmd, arg)] with cmd 'v' (target speed m/s, at accel/decel limits)
    or 'stop' (stop with the front at arg). integrate from s0, v0 at t0, step DT; then s(t), v(t)."""

    def __init__(self, t0, s0, v0, plan, t1, acc=2.0, dec=3.0, L=4.3):
        self.t0, self.ts, self.ss, self.vs = t0, [], [], []
        s, v = s0, v0
        t = t0
        sub = 4
        while t <= t1 + 1e-9:
            self.ts.append(t)
            self.ss.append(s)
            self.vs.append(v)
            for _k in range(sub):
                tt = t + _k * DT / sub
                cmd, arg, a_, d_ = "v", v0, acc, dec
                for item in plan:
                    if item[0] <= tt + 1e-9:
                        cmd, arg = item[1], item[2]
                        a_ = item[3] if len(item) > 3 else acc
                        d_ = item[4] if len(item) > 4 else dec
                h = DT / sub
                if cmd == "v":
                    v = min(arg, v + a_ * h) if v < arg else max(arg, v - d_ * h)
                elif cmd == "stop":
                    rem = arg - (s + L / 2)
                    if rem <= 0.01 or v <= 0.02:
                        v = 0.0
                    else:
                        need = v * v / (2 * rem)
                        v = max(0.0, v - max(need, 0.0) * h)
                s += v * h
            t += DT

    def at(self, t):
        if t <= self.ts[0]:
            dt = t - self.ts[0]
            return self.ss[0] + self.vs[0] * dt, self.vs[0]
        i = min(len(self.ts) - 1, int((t - self.t0) / DT))
        dt = t - self.ts[i]
        return self.ss[i] + self.vs[i] * dt, self.vs[i]


# ------------------------------------------------------------------------------------------------ Blender side
def prebuild(fn):
    """Call fn(lib) as soon as stage.build_world has made its "lib" collection (vehicles are built before the
    motorway geometry, where operators and depsgraph bakes are fast)."""
    import world as W
    orig = W.coll
    state = {"done": False}

    def coll(name, parent=None, hide=False):
        c = orig(name, parent, hide)
        if name == "traffic" and not state["done"]:
            state["done"] = True
            fn(bpy.data.collections["lib"])
            W.coll = orig
        return c
    W.coll = coll
    return state


def world(assets, length=4000.0, s0=40.0, s1=None, **kw):
    """stage.build_world (the approved episode 1 Autobahn) on a road `length` metres long instead of 2.4 km. The
    kit is not changed: the Road class is swapped only while the stage is built."""
    import stage
    import world as W
    s1 = s1 or length - 40.0
    orig = W.Road
    if PROBE:
        # local framing probe only (the shared machine allows about 3 minutes): no vegetation, no villages
        import flora
        flora.vegetation = lambda *a, **k: []
        W.village = lambda *a, **k: None

    class LongRoad(orig):
        def __init__(self, length=2400.0, **k):
            orig.__init__(self, length=LEN, **k)
    LEN = length
    W.Road = LongRoad
    try:
        S = stage.build_world(assets, s0=s0, s1=s1, **kw)
    finally:
        W.Road = orig
    far_ring(S["road"], S["env"])
    tick("world built")
    return S


def _ring_axis(inner, outer):
    """Grid lines for the far ring: the inner square at 200 m, then 100 m, 300 m, 1,000 m cells outwards."""
    out, v = [], inner - 30.0
    while v < outer:
        out.append(v)
        v += 100.0 if v < 3000.0 else (300.0 if v < 6000.0 else 1000.0)
    out.append(outer)
    mid = [-inner + 30.0 + k * (2 * inner - 60.0) / 20 for k in range(1, 20)]
    return [-x for x in reversed(out)] + mid + out


def far_ring(road, c, inner=2000.0, outer=16000.0):
    """Farmland from the edge of world.terrain (a 4 km square) out to 16 km, on world.ground_z, so the horizon is hills
    in a cool haze (as kit/interchange.py), not the bare sky below the clouds. Same fields material, all 'far'."""
    import world as W
    if "terrain" not in bpy.data.objects:
        return None
    cx, cy = road.X[road.n // 2], road.Y[road.n // 2]
    ax = _ring_axis(inner, outer)
    n = len(ax)
    verts = []
    for v in ax:
        for u in ax:
            x, y = cx + u, cy + v
            d = max(abs(u), abs(v))
            dz = -0.6 if d <= inner else -0.6 * max(0.0, 1.0 - (d - inner) / 120.0)
            verts.append((x, y, W.ground_z(road, x, y) + dz))
    lim = inner - 30.0 + 1e-3
    faces = []
    for j in range(n - 1):
        for i in range(n - 1):
            if max(abs(ax[i]), abs(ax[i + 1])) < lim and max(abs(ax[j]), abs(ax[j + 1])) < lim:
                continue
            faces.append((j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i))
    o = W.mesh_obj("terrain_far", verts, faces, None, c)
    attr = o.data.color_attributes.new("far", "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", [1.0] * (4 * len(verts)))
    o.data.polygons.foreach_set("use_smooth", [True] * len(faces))
    o.data.materials.append(bpy.data.objects["terrain"].data.materials[0])
    return o


def fleet_models(lib, extra=True):
    """stage.fleet plus a few more colours and kinds, all built into lib. Returns ({key: collection}, sim models)."""
    import stage
    import vehicles as V
    cars, vans, trucks = stage.fleet(lib)
    allm = dict(cars, **vans, **trucks)
    if extra and not PROBE:
        for key, kind, col, plate, metal in (
                ("hatch_white", "hatch", (0.85, 0.85, 0.84), "JJ KR 23", 0.1),
                ("estate_silver", "estate", (0.5, 0.52, 0.55), "QZ ST 518", 0.6),
                ("saloon_blue", "saloon", (0.03, 0.08, 0.22), "QX BN 77", 0.5),
                ("suv_red", "suv", (0.35, 0.02, 0.02), "JX RT 64", 0.4),
                ("hatch_yellow", "hatch", (0.75, 0.55, 0.05), "QZ GE 9", 0.2),
                ("estate_brown", "estate", (0.16, 0.09, 0.05), "JJ BR 330", 0.5),
                ("saloon_grey", "saloon", (0.28, 0.29, 0.3), "QX GR 412", 0.6),
                ("van_silver", "van", (0.55, 0.56, 0.58), "JX VN 120", 0.3)):
            allm[key] = V.car(kind, col, key, plate, metal=metal, c=lib)
    lens = {k: V.KINDS[k]["L"] for k in V.KINDS}
    models = {"car": [], "van": [], "truck": []}
    for k in allm:
        if k.startswith("t_"):
            models["truck"].append((k, 16.45))
        elif k.startswith("van"):
            models["van"].append((k, lens["van"]))
        else:
            kind = next(kk for kk in ("hatch", "estate", "saloon", "suv") if k.startswith(kk))
            models["car"].append((k, lens[kind]))
    return allm, models


class Director:
    """Shots on the canonical timeline, each sampling one variant (a Sim) at world time W = w0 + (t - t0).
    xfun(lanef, s) gives the lateral offset of a lane position at s (lane centres change in roadworks)."""

    def __init__(self, canon, road, xfun):
        self.C, self.road, self.xfun = canon, road, xfun
        self.var = {}
        self.shots = []
        self.tracks = {}
        self.objs = {}
        self.cams = {}
        self.frame_shot = {}
        self.protect = {"hero"}

    def variant(self, name, sim):
        self.var[name] = sim
        return sim

    def shot(self, name, t0, t1, var, w0, lens=35, cam=None, up=None, dof=None, roll=0.0):
        self.shots.append(dict(name=name, t0=t0, t1=t1, var=var, w0=w0, lens=lens, cam=cam, up=up, dof=dof,
                               roll=roll))

    def _frames(self, sh):
        f0 = Canon.frame(sh["t0"])
        f1 = Canon.frame(sh["t1"]) - 1
        return f0, f1

    def plan(self):
        for sh in self.shots:
            f0, f1 = self._frames(sh)
            for f in range(f0, f1 + 1):
                self.frame_shot[f] = sh
        missing = [f for f in range(1, self.C.N + 1) if f not in self.frame_shot]
        if missing:
            raise ValueError(f"frames without a shot: {missing[:5]} ... ({len(missing)})")

    def W(self, f):
        sh = self.frame_shot[f]
        return sh["var"], sh["w0"] + ((f - 1) / FPS - sh["t0"])

    def _state(self, var, vid, T):
        sim = self.var[var]
        for sc in sim.scripts:
            if sc.id == vid:
                st = sc.fn(T)
                return None if st is None else dict(st)
        return sim.sample(vid, T)

    def pose(self, st, st2):
        """World position, yaw (0 = +x), pitch from a state and the state 0.1 s later."""
        road = self.road
        x = st.get("x")
        if x is None:
            x = self.xfun(st["lane"], st["s"])
        c, th, fwd, right, sl = road.frame(st["s"])
        p = road.point(st["s"], x, st.get("z", 0.0))
        lat = 0.0
        if st2 is not None:
            x2 = st2.get("x")
            if x2 is None:
                x2 = self.xfun(st2["lane"], st2["s"])
            ds = st2["s"] - st["s"]
            if ds > 0.03:
                lat = math.atan2(x2 - x, ds)
        yaw = (math.pi / 2 - th) - lat + st.get("yaw_off", 0.0)
        return p, yaw, math.atan(sl)

    def build_tracks(self):
        """Per-frame states of every vehicle that appears in a shot."""
        self.plan()
        N = self.C.N
        used = {}
        for f in range(1, N + 1):
            var, T = self.W(f)
            used.setdefault(var, []).append((f, T))
        for var, fts in used.items():
            sim = self.var.get(var)
            if sim is None:
                continue
            for vid in sim.ids():
                key = f"{var}:{vid}"
                tr = [None] * N
                any_ = False
                for f, T in fts:
                    st = self._state(var, vid, T)
                    if st is None:
                        continue
                    st2 = self._state(var, vid, T + 0.1)
                    p, yaw, pitch = self.pose(st, st2)
                    st.update(px=p.x, py=p.y, pz=p.z, yaw=yaw, pitch=pitch)
                    tr[f - 1] = st
                    any_ = True
                if any_:
                    self.tracks[key] = tr
        tick(f"tracks {len(self.tracks)}")

    def cull(self, radius=700.0, per_shot=None):
        """Keep a vehicle in a shot only if it comes within `radius` metres of that shot's camera (checked every
        third frame); elsewhere it is parked out of sight. Whole shots at a time, so nothing pops in on screen."""
        per_shot = per_shot or {}
        campos = {}
        for sh in self.shots:
            f0, f1 = self._frames(sh)
            pts = []
            for f in range(f0, f1 + 1, 3):
                out = sh["cam"]((f - 1) / FPS - sh["t0"], f)
                pts.append(Vector(out[0]))
            campos[sh["name"]] = pts
        keep = {}
        for key, tr in list(self.tracks.items()):
            if key.split(":", 1)[1] in self.protect:
                continue
            any_ = False
            for sh in self.shots:
                f0, f1 = self._frames(sh)
                r = per_shot.get(sh["name"], radius)
                near = False
                for f in range(f0, f1 + 1, 3):
                    s = tr[f - 1]
                    if s is None:
                        continue
                    p = Vector((s["px"], s["py"], s["pz"]))
                    if min((p - c).length for c in campos[sh["name"]]) < r:
                        near = True
                        break
                if not near:
                    for f in range(f0, f1 + 1):
                        tr[f - 1] = None
                else:
                    any_ = True
            if not any_:
                del self.tracks[key]
        tick(f"tracks after cull {len(self.tracks)}")
        self.audit()
        if "--audit-only" in sys.argv:
            raise SystemExit(0)

    def audit(self, exempt=("hero", "police", "police2", "crash", "local0", "local1", "local2")):
        """Traffic rules on every frame a vehicle is on screen (after cull), printed as AUDIT lines for the logs:
        no lorry in the left lane, an indicator during every lane change and in the second before it, nobody but the
        exempt (heroes, police, the crash) inside a closed lane (each Sim closure from s_block) or past the zipper
        point in the ending lane. Zipper lane changes are listed with their distance to the lane end."""
        bad, zips = {}, {}
        for key, tr in self.tracks.items():
            var, vid = key.split(":", 1)
            sim = self.var.get(var)
            if sim is None:
                continue
            kind = sim.model_of(vid)[1]
            free = vid in exempt
            for f, st in enumerate(tr, 1):
                if st is None:
                    continue
                lf, s = st.get("lane"), st["s"]
                msgs = []
                if kind == "truck" and lf is not None and lf < 0.98:
                    msgs.append("lorry in the left lane")
                p1 = tr[f - 2] if f > 1 else None
                n1 = tr[f] if f < len(tr) else None
                sideways = any(q is not None and abs(q.get("lane", lf) - lf) > 1e-4 for q in (p1, n1)) \
                    if lf is not None else False      # parked on the hard shoulder is not a lane change
                if lf is not None and abs(lf - round(lf)) > 1e-3 and sideways and st.get("ind") not in ("L", "R"):
                    msgs.append("lane change without indicator")
                if lf is not None and abs(lf - round(lf)) > 1e-3 and p1 is not None \
                        and self.frame_shot.get(f - 1) is self.frame_shot.get(f) \
                        and abs(p1.get("lane", lf) - round(p1.get("lane", lf))) < 1e-3:
                    prev = [tr[g - 1] for g in range(max(1, f - 21), f)
                            if tr[g - 1] is not None and self.frame_shot.get(g) is self.frame_shot.get(f)]
                    if prev and not all(p.get("ind") in ("L", "R") for p in prev):
                        msgs.append("indicator less than 0.7 s before a lane change")
                    z = sim.zipper
                    if z and round(p1.get("lane", lf)) == z[0]:
                        zips.setdefault(var, []).append((vid, round(z[2] - s, 1)))
                if not free and lf is not None:
                    for (l, sw, sb, se) in sim.closures:
                        if abs(lf - l) < 0.5 and sb <= s <= se:
                            msgs.append(f"in closed lane {l}")
                    z = sim.zipper
                    if z and abs(lf - z[0]) < 0.5 and s > z[2] + 1.0:
                        msgs.append("past the end of the ending lane")
                for m in msgs:
                    bad.setdefault(m, []).append((key, f))
        for m, lst in sorted(bad.items()):
            print(f"AUDIT FAIL {m}: {len(lst)} frames, {sorted({k for k, _f in lst})[:6]} e.g. frame {lst[0][1]}",
                  flush=True)
        for var, lst in sorted(zips.items()):
            print(f"AUDIT zipper merges variant {var} (vehicle, metres before the lane end): {lst}", flush=True)
        print("AUDIT", "ok" if not bad else f"{len(bad)} failure kinds", flush=True)
        self.audit_result = bad
        return bad

    def st(self, key, f):
        """State of track `key` at frame f. While cameras are baked, frames just outside the current shot are
        evaluated in that shot's own variant and world time (motion blur and the padding keys need them)."""
        sh = getattr(self, "_cur", None)
        if sh is not None:
            var, vid = key.split(":", 1)
            if var == sh["var"] and not (self._frames(sh)[0] <= f <= self._frames(sh)[1]):
                T = sh["w0"] + ((f - 1) / FPS - sh["t0"])
                st = self._state(var, vid, T)
                if st is not None:
                    p, yaw, pitch = self.pose(st, self._state(var, vid, T + 0.1))
                    st.update(px=p.x, py=p.y, pz=p.z, yaw=yaw, pitch=pitch)
                    return st
        tr = self.tracks.get(key)
        if tr is None:
            return None
        return tr[max(0, min(len(tr) - 1, f - 1))]

    def matrix(self, key, f):
        s = self.st(key, f)
        if s is None:
            return Matrix.Identity(4)
        return (Matrix.Translation((s["px"], s["py"], s["pz"])) @ Matrix.Rotation(s["yaw"] - math.pi / 2, 4, "Z")
                @ Matrix.Rotation(s["pitch"], 4, "X"))

    def cast(self, coll, models, night=False):
        """One rigged instance per track, baked through motion.bake (hidden far below the road when absent)."""
        import motion
        N = self.C.N
        for key, tr in self.tracks.items():
            var, vid = key.split(":", 1)
            model, kind = self.var[var].model_of(vid)
            e = bpy.data.objects.new("veh_" + key.replace(":", "_"), None)
            e.instance_type = "COLLECTION"
            e.instance_collection = models[model]
            coll.objects.link(e)
            track, last = [], None
            for i in range(N):
                s = tr[i]
                if s is None:
                    y = last["yaw"] if last else 0.0
                    track.append(dict(x=0.0, y=-3000.0 - 40.0 * len(self.objs), z=-200.0, yaw=y, v=0.0, ind=None))
                    continue
                track.append(dict(x=s["px"], y=s["py"], z=s["pz"], yaw=s["yaw"], pitch=s["pitch"], v=s["v"],
                                  ind=s.get("ind"), beacon=bool(s.get("beacon"))))
                last = s
            r = motion.rig(e)
            motion.bake(r, track, night=night)
            self.objs[key] = (e, r)
        tick(f"cast {len(self.objs)}")

    def cameras(self):
        import stage
        sc = bpy.context.scene
        for sh in self.shots:
            f0, f1 = self._frames(sh)
            co = stage.camera("cam_" + sh["name"], sh["lens"])
            if sh["dof"]:
                co.data.dof.use_dof = True
                co.data.dof.focus_distance, co.data.dof.aperture_fstop = sh["dof"]
            fr = list(range(max(1, f0 - 1), min(self.C.N, f1 + 1) + 1))
            locs, rots = [], []
            self._cur = sh
            for f in fr:
                t = (f - 1) / FPS
                out = sh["cam"](t - sh["t0"], f)
                pos, tgt = Vector(out[0]), Vector(out[1])
                up = Vector(out[2]) if len(out) > 2 and out[2] is not None else None
                if up is None:
                    rot = stage.look_rot(pos, tgt)
                else:
                    rot = stage.look_rot(pos, tgt, up)
                if sh["roll"]:
                    q = rot.to_quaternion() @ Matrix.Rotation(math.radians(sh["roll"]), 4, "Z").to_quaternion()
                    rot = q.to_euler()
                locs.append(tuple(pos))
                rots.append(tuple(rot))
            for i in range(1, len(rots)):
                r = list(rots[i])
                for j in range(3):
                    while r[j] - rots[i - 1][j] > math.pi:
                        r[j] -= 2 * math.pi
                    while r[j] - rots[i - 1][j] < -math.pi:
                        r[j] += 2 * math.pi
                rots[i] = tuple(r)
            self._cur = None
            stage.bake_motion(co, fr, locs, rots)
            self.cams[sh["name"]] = (co, f0, f1)
        sc.camera = self.cams[self.shots[0]["name"]][0]
        tick("cameras")

    def cam_at(self, f):
        for name, (co, f0, f1) in self.cams.items():
            if f0 <= f <= f1:
                return co
        return None

    def cam_obj(self, name):
        return self.cams[name][0]

    # ---------------------------------------------------------------- camera helpers (return fn(t_rel, f))
    def chase(self, key, back=8.0, side=0.0, up=2.2, ahead=30.0, ahead_up=1.0, ahead_side=None, drift=None):
        road = self.road

        def fn(t, f):
            s = self.st(key, f)
            x = s.get("x") if s.get("x") is not None else self.xfun(s["lane"], s["s"])
            b = back(t) if callable(back) else back
            sd = side(t) if callable(side) else side
            u = up(t) if callable(up) else up
            a = ahead(t) if callable(ahead) else ahead
            au = ahead_up(t) if callable(ahead_up) else ahead_up
            asd = sd if ahead_side is None else (ahead_side(t) if callable(ahead_side) else ahead_side)
            pos = road.point(s["s"] - b, x + sd, u)
            tgt = road.point(s["s"] + a, x + asd, au)
            return pos, tgt
        return fn

    def pov(self, key, eye=(-0.37, -0.12, 1.17), pitch_deg=-5.0, yaw_deg=0.0):
        def fn(t, f):
            M = self.matrix(key, f)
            e = Vector(eye)
            d = Vector((math.sin(math.radians(yaw_deg)), 1.0, math.tan(math.radians(pitch_deg + (yaw_deg * 0)))))
            pos = M @ e
            tgt = M @ (e + d * 20.0)
            up = M.to_3x3() @ Vector((0, 0, 1))
            return pos, tgt, up
        return fn

    def fixed(self, pos, tgt):
        return lambda t, f: (pos(t) if callable(pos) else pos, tgt(t) if callable(tgt) else tgt)

    def road_cam(self, s_fn, x_fn, h_fn, st_fn, xt_fn, ht_fn):
        road = self.road

        def fn(t, f):
            v = lambda q: q(t) if callable(q) else q  # noqa: E731
            return road.point(v(s_fn), v(x_fn), v(h_fn)), road.point(v(st_fn), v(xt_fn), v(ht_fn))
        return fn


# --------------------------------------------------------------------------------------------------- cockpit
def _mat(name, color, rough=0.5, metal=0.0, emit=None, estr=0.0):
    import world as W
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    return W.principled(name, color, rough, metal=metal, emit=emit, estr=estr)


def _mesh(name, verts, faces, m, c, smooth_=False):
    import world as W
    return W.mesh_obj(name, verts, faces, m, c, smooth=smooth_)


def _box(c, name, center, size, m, parent):
    x, y, z = center
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    vs = [(x + dx, y + dy, z + dz) for dz in (-hz, hz) for dx, dy in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))]
    fs = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    o = _mesh(name, vs, fs, m, c)
    o.parent = parent
    return o


def cockpit(D, key, paint_mat, frames_on, limit_kmh=None, vmax_kmh=240.0, name="cockpit", fill_w=4.0):
    """Driver's view parts for the hero `key` (a Director track): bonnet in the hero's paint, dashboard, gauge with
    ticks every 20 km/h and a yellow limit mark (no numerals), a needle driven by the hero's speed, steering wheel,
    A-pillars. Shown only on frames_on; the hero's own body is hidden on those frames (camera inside the car)."""
    import world as W
    e, r = D.objs[key]
    c = e.users_collection[0]
    root = bpy.data.objects.new(name, None)
    c.objects.link(root)
    root.parent = e
    # mid-dark interior greys (the first preview's near-black 0.02 albedo read as a black bar in the frame)
    dark = _mat("ck_dash", (0.075, 0.075, 0.08), 0.7)
    trim = _mat("ck_trim", (0.13, 0.13, 0.135), 0.55)
    leather = _mat("ck_leather", (0.06, 0.052, 0.046), 0.42)
    dial_m = _mat("ck_dial", (0.004, 0.004, 0.005), 0.35)
    tick_m = _mat("ck_tick", (0.9, 0.9, 0.9), 0.3, emit=(1, 1, 1), estr=1.6)
    lim_m = _mat("ck_limit", (1.0, 0.7, 0.0), 0.3, emit=(1.0, 0.65, 0.0), estr=4.0)
    needle_m = _mat("ck_needle", (1.0, 0.25, 0.02), 0.3, emit=(1.0, 0.22, 0.02), estr=5.0)
    ring_m = _mat("ck_ring", (0.6, 0.62, 0.65), 0.25, metal=1.0)
    parts = []
    # bonnet: from the windscreen base forward, crowned, in the hero's paint
    vs, fs = [], []
    ys = [0.80, 1.05, 1.35, 1.65, 1.95, 2.08]
    xs = [-1.0, -0.7, -0.35, 0.0, 0.35, 0.7, 1.0]
    for y in ys:
        u = (y - 0.8) / 1.28
        hw = 0.84 - 0.1 * u * u
        zc = 0.985 - 0.17 * u - 0.05 * u * u
        for xx in xs:
            vs.append((xx * hw, y, zc - 0.045 * xx * xx))
    nx = len(xs)
    for j in range(len(ys) - 1):
        for i in range(nx - 1):
            fs.append((j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i))
    bon = _mesh(name + "_bonnet", vs, fs, paint_mat, c, smooth_=True)
    bon.parent = root
    parts.append(bon)
    # dashboard: a wide soft block under the windscreen, the cluster hood in front of the driver
    vs, fs = [], []
    prof = [(0.30, 0.70), (0.36, 0.93), (0.50, 0.985), (0.70, 0.99), (0.82, 0.975), (0.84, 0.90)]
    for xx in (-0.86, 0.86):
        for y, z in prof:
            vs.append((xx, y, z))
    n = len(prof)
    for i in range(n - 1):
        fs.append((i, i + 1, n + i + 1, n + i))
    fs.append(tuple(range(n - 1, -1, -1)))
    fs.append(tuple(range(n, 2 * n)))
    dash = _mesh(name + "_dash", vs, fs, dark, c)
    dash.parent = root
    parts.append(dash)
    hood = _box(c, name + "_hood", (-0.37, 0.47, 1.0), (0.46, 0.2, 0.06), dark, root)
    parts.append(hood)
    # gauge: dial facing the eye
    eye = Vector((-0.37, -0.12, 1.17))
    dc = Vector((-0.37, 0.40, 0.955))
    nrm = (eye - dc).normalized()
    g = bpy.data.objects.new(name + "_gauge", None)
    c.objects.link(g)
    g.parent = root
    g.location = dc
    g.rotation_euler = (-math.atan2(nrm.z, -nrm.y), 0, 0)
    R = 0.078
    seg = 48
    vs = [(0, 0, 0)] + [(R * math.cos(2 * math.pi * k / seg), 0, R * math.sin(2 * math.pi * k / seg))
                        for k in range(seg)]
    fs = [(0, 1 + (k + 1) % seg, 1 + k) for k in range(seg)]
    dial = _mesh(name + "_dial", vs, fs, dial_m, c)
    dial.parent = g
    parts.append(dial)
    rv = []
    for k in range(seg):
        a = 2 * math.pi * k / seg
        rv += [(R * math.cos(a), 0.0, R * math.sin(a)), (1.1 * R * math.cos(a), -0.004, 1.1 * R * math.sin(a))]
    rf = [(2 * k, 2 * ((k + 1) % seg), 2 * ((k + 1) % seg) + 1, 2 * k + 1) for k in range(seg)]
    ring = _mesh(name + "_ring", rv, rf, ring_m, c)
    ring.parent = g
    parts.append(ring)

    def ang(v_kmh):
        return math.radians(225.0 - 270.0 * min(1.0, max(0.0, v_kmh / vmax_kmh)))

    tv, tf = [], []
    for k in range(int(vmax_kmh // 20) + 1):
        a = ang(k * 20)
        l0 = 0.80 if k % 2 == 0 else 0.86
        p0 = (l0 * R * math.cos(a), -0.002, l0 * R * math.sin(a))
        p1 = (0.95 * R * math.cos(a), -0.002, 0.95 * R * math.sin(a))
        w = 0.0025 if k % 2 == 0 else 0.0016
        nxp, nzp = -math.sin(a) * w, math.cos(a) * w
        b = len(tv)
        tv += [(p0[0] - nxp, -0.002, p0[2] - nzp), (p0[0] + nxp, -0.002, p0[2] + nzp),
               (p1[0] + nxp, -0.002, p1[2] + nzp), (p1[0] - nxp, -0.002, p1[2] - nzp)]
        tf.append((b, b + 1, b + 2, b + 3))
    ticks = _mesh(name + "_ticks", tv, tf, tick_m, c)
    ticks.parent = g
    parts.append(ticks)
    if limit_kmh:
        a0, a1 = ang(limit_kmh - 2.5), ang(limit_kmh + 2.5)
        lv = []
        for a in (a0, a1):
            lv += [(0.70 * R * math.cos(a), -0.003, 0.70 * R * math.sin(a)),
                   (1.02 * R * math.cos(a), -0.003, 1.02 * R * math.sin(a))]
        lm = _mesh(name + "_limit", lv, [(0, 1, 3, 2)], lim_m, c)
        lm.parent = g
        parts.append(lm)
    nd = _mesh(name + "_needle", [(-0.012, -0.006, -0.0022), (0.072, -0.006, -0.0008), (0.072, -0.006, 0.0008),
                                  (-0.012, -0.006, 0.0022)], [(0, 1, 2, 3)], needle_m, c)
    nd.parent = g
    parts.append(nd)
    cap = _mesh(name + "_cap", [(0.009 * math.cos(2 * math.pi * k / 12), -0.007, 0.009 * math.sin(2 * math.pi * k / 12))
                                for k in range(12)], [tuple(range(11, -1, -1))], ring_m, c)
    cap.parent = g
    parts.append(cap)
    # steering wheel (rim, three spokes, hub), tilted towards the driver
    sw = bpy.data.objects.new(name + "_wheel", None)
    c.objects.link(sw)
    sw.parent = root
    sw.location = (-0.37, 0.17, 0.86)
    sw.rotation_euler = (math.radians(-68), 0, 0)
    rv, rf = [], []
    M_, m_ = 24, 8
    Rr, rr = 0.185, 0.017
    for i in range(M_):
        a = 2 * math.pi * i / M_
        for j in range(m_):
            b = 2 * math.pi * j / m_
            rad = Rr + rr * math.cos(b)
            rv.append((rad * math.cos(a), rad * math.sin(a), rr * math.sin(b)))
    for i in range(M_):
        for j in range(m_):
            a = i * m_ + j
            b2 = ((i + 1) % M_) * m_ + j
            c2 = ((i + 1) % M_) * m_ + (j + 1) % m_
            d2 = i * m_ + (j + 1) % m_
            rf.append((a, b2, c2, d2))
    rim = _mesh(name + "_rim", rv, rf, leather, c, smooth_=True)
    rim.parent = sw
    parts.append(rim)
    for a in (0.0, math.pi, -math.pi / 2):
        size = (0.15, 0.03, 0.02) if abs(math.cos(a)) > 0.5 else (0.03, 0.15, 0.02)
        sp = _box(c, name + "_spoke", (0.095 * math.cos(a), 0.095 * math.sin(a), -0.01), size, trim, sw)
        parts.append(sp)
    hub = _box(c, name + "_hub", (0, 0, -0.012), (0.11, 0.09, 0.04), trim, sw)
    parts.append(hub)
    # A-pillars and the roof edge
    for sx in (-1, 1):
        p0, p1 = Vector((sx * 0.80, 0.80, 0.98)), Vector((sx * 0.66, 0.02, 1.42))
        d = p1 - p0
        o = _box(c, name + "_pillar", (0.0, 0.0, 0.0), (0.09, d.length, 0.07), trim, root)
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = Vector((0, 1, 0)).rotation_difference(d.normalized())
        o.location = (p0 + p1) / 2
        parts.append(o)
    parts.append(_box(c, name + "_header", (0, 0.0, 1.44), (1.4, 0.12, 0.06), trim, root))
    # cabin light: a soft area light above and behind the driver's eye (daylight through the roof and side windows),
    # so the wheel and the dashboard read; invisible to the camera and in reflections, on the POV frames only
    ld = bpy.data.lights.new(name + "_fill", "AREA")
    ld.shape, ld.size, ld.size_y = "RECTANGLE", 1.1, 0.7
    ld.energy = fill_w
    ld.color = (1.0, 0.95, 0.88)
    fill = bpy.data.objects.new(name + "_fill", ld)
    c.objects.link(fill)
    fill.parent = root
    fill.location = (-0.25, -0.35, 1.48)
    fill.rotation_mode = "QUATERNION"
    fill.rotation_quaternion = Vector((0, 0, -1)).rotation_difference(
        (Vector((-0.3, 0.45, 0.9)) - Vector(fill.location)).normalized())
    for k in ("visible_camera", "visible_glossy", "visible_transmission"):
        if hasattr(fill, k):
            setattr(fill, k, False)
    # visibility: only on the POV frames; the hero's body hides there
    on = set(frames_on)
    N = bpy.context.scene.frame_end
    for o in parts + [e, fill]:
        vis_on = (o is not e)
        prev = None
        for f in range(1, N + 1):
            val = (f not in on) if vis_on else (f in on)
            if val != prev:
                o.hide_render = val
                o.keyframe_insert("hide_render", frame=f)
                prev = val
    for o in parts:
        o.visible_shadow = False
    # needle from the hero's speed
    nd.rotation_mode = "XYZ"
    prev = None
    for f in range(1, N + 1):
        s = D.st(key, f)
        v = s["v"] * 3.6 if s else 0.0
        a = ang(v)
        nd.rotation_euler = (0, -a, 0)
        nd.keyframe_insert("rotation_euler", index=1, frame=f)
    return parts


# ---------------------------------------------------------------------------------------- camera-space graphics
def _cam_plane(cam, d=1.0):
    h = 36.0 / cam.data.lens * d
    return h * 9.0 / 16.0, h


def hud_root(cam, name, u, v, d=1.0):
    """Empty in camera space at screen position u (0 left .. 1 right), v (0 top .. 1 bottom), d metres ahead."""
    w, h = _cam_plane(cam, d)
    e = bpy.data.objects.new(name, None)
    cam.users_collection[0].objects.link(e)
    e.parent = cam
    e.location = ((u - 0.5) * w, (0.5 - v) * h, -d)
    return e, w, h


def pop_keys(o, t_on, t_off, scale=1.0, overshoot=1.15):
    f_on, f_off = Canon.frame(t_on), Canon.frame(t_off)
    for f, s in ((1, 0.0), (f_on - 1, 0.0), (f_on + 3, overshoot * scale), (f_on + 6, scale), (f_off - 5, scale),
                 (f_off, 0.0)):
        o.scale = (s, s, s)
        o.keyframe_insert("scale", frame=max(1, f))


def hud_sign(cam, ref, t_on, t_off, u=0.78, v=0.68, wfrac=0.24, d=1.0, emit=0.7, name="hud_sign"):
    """A sign picture (signs.py, unaltered Commons file) popping up in camera space. ref = (set, id)."""
    import signs as SG
    e, w, h = hud_root(cam, name, u, v, d)
    width = w * wfrac
    o = SG.face(ref[1], e.users_collection[0], width, set_=ref[0], name=name + "_face", emit=emit, back=False)
    o.parent = e
    o.rotation_euler = (-math.pi / 2, 0, 0)
    o.location = (0, -(o["height"] / 2), 0)
    o.visible_shadow = False
    o.visible_diffuse = False
    pop_keys(e, t_on, t_off)
    return e


def flat_mat(name, rgb, strength=1.0, alpha=1.0):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1)
    em.inputs["Strength"].default_value = strength
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    if alpha < 1.0:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mx = nt.nodes.new("ShaderNodeMixShader")
        mx.inputs[0].default_value = alpha
        nt.links.new(tr.outputs[0], mx.inputs[1])
        nt.links.new(em.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], out.inputs["Surface"])
    else:
        nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def fade_mat(name, rgb, strength=1.0):
    """Emission mixed with transparency by the object's colour (red channel = opacity): key obj.color to fade."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1)
    em.inputs["Strength"].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(oi.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs[0], mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"
    return m


def key_alpha(o, pairs, interp="LINEAR"):
    import stage
    for f, a in pairs:
        o.color = (a, a, a, 1.0)
        o.keyframe_insert("color", frame=max(1, f))
    for fc in stage.fcurves(o):
        if fc.data_path == "color":
            for kp in fc.keyframe_points:
                kp.interpolation = interp


def rect(name, w, h, m, c, x0=0.0, y0=0.0, anchor="left"):
    """Rectangle in a camera-space XY plane (z = 0), facing the camera (+Z). anchor left: grows to +x."""
    xa = 0.0 if anchor == "left" else -w / 2
    vs = [(x0 + xa, y0 - h / 2, 0), (x0 + xa + w, y0 - h / 2, 0), (x0 + xa + w, y0 + h / 2, 0),
          (x0 + xa, y0 + h / 2, 0)]
    return _mesh(name, vs, [(0, 1, 2, 3)], m, c)


def hud_flash(cam, frames, strength=1.6, peak=0.85, name="hud_flash"):
    """Full-frame white flash (photo flash) at the given frames: one bright frame, then a 4-frame fade."""
    e, w, h = hud_root(cam, name, 0.5, 0.5, 0.3)
    m = fade_mat("a4_flash_white", (1.0, 0.98, 0.95), strength)
    o = rect(name + "_plane", w * 1.2, h * 1.2, m, e.users_collection[0], anchor="center")
    o.parent = e
    o.visible_shadow = False
    pairs = [(1, 0.0)]
    for f in frames:
        pairs += [(f - 1, 0.0), (f, peak), (f + 1, peak * 0.55), (f + 4, 0.0)]
    key_alpha(o, sorted(pairs))
    return o


def hud_bar(cam, name, u0, v, frac_w, frac_h, rgb, keys, d=1.0, strength=2.0):
    """Horizontal bar from screen x u0 growing to the right: keys [(t, length fraction of the frame width)]."""
    e, w, h = hud_root(cam, name, u0, v, d)
    m = flat_mat(name + "_m", rgb, strength)
    o = rect(name + "_bar", w * frac_w, h * frac_h, m, e.users_collection[0])
    o.parent = e
    o.visible_shadow = False
    for t, s in keys:
        o.scale = (max(1e-4, s / frac_w), 1.0, 1.0)
        o.keyframe_insert("scale", index=0, frame=Canon.frame(t))
    return o


def show_keys(o, t_on, t_off):
    import stage
    for f, hide in ((1, True), (Canon.frame(t_on), False), (Canon.frame(t_off), True)):
        o.hide_render = hide
        o.keyframe_insert("hide_render", frame=f)


# ----------------------------------------------------------------------------------------------- end card
def end_card(D, name, t0, t1, refs, assets, lens=40, location=(-7000.0, 0.0, 400.0), leds=None):
    """Road-grey card filling the frame with the episode's signs as flat call-outs (a row in the lower half, below the
    captions), a dashed lane line and edge line motif, a slow push-in. refs: [(set, id)], leds: [pred names]."""
    import signs as SG
    import world as W
    sc = bpy.context.scene
    c = W.coll("endcard")
    x0, y0, z0 = location
    m = W.noisy("ec_grey", (0.075, 0.078, 0.085), (0.11, 0.115, 0.125), 9.0, rough=0.85, bump=0.08)
    em = m.node_tree.nodes["Principled BSDF"]
    em.inputs["Emission Color"].default_value = (0.11, 0.115, 0.125, 1)
    em.inputs["Emission Strength"].default_value = 0.9
    card = _mesh("ec_card", [(x0 - 6, y0, z0 - 10), (x0 + 6, y0, z0 - 10), (x0 + 6, y0, z0 + 10), (x0 - 6, y0, z0 + 10)],
                 [(0, 1, 2, 3)], m, c)
    paint = flat_mat("ec_paint", (0.85, 0.85, 0.82), 1.4)
    yel = flat_mat("ec_yellow", (1.0, 0.62, 0.02), 2.2)
    # lane motif: a solid edge line and a dashed lane line low on the card
    for xx, dashed, mm in ((-1.15, False, paint), (1.15, True, yel)):
        if dashed:
            z = z0 - 3.6
            while z < z0 + 3.6:
                _mesh("ec_dash", [(x0 + xx - 0.03, y0 - 0.01, z), (x0 + xx + 0.03, y0 - 0.01, z),
                                  (x0 + xx + 0.03, y0 - 0.01, z + 0.36), (x0 + xx - 0.03, y0 - 0.01, z + 0.36)],
                      [(0, 1, 2, 3)], mm, c)
                z += 0.72
        else:
            _mesh("ec_edge", [(x0 + xx - 0.04, y0 - 0.01, z0 - 3.6), (x0 + xx + 0.04, y0 - 0.01, z0 - 3.6),
                              (x0 + xx + 0.04, y0 - 0.01, z0 + 3.6), (x0 + xx - 0.04, y0 - 0.01, z0 + 3.6)],
                  [(0, 1, 2, 3)], mm, c)
    items = list(refs) + [("led", p) for p in (leds or [])]
    n = max(1, len(items))
    width = min(0.95, 3.0 / n - 0.25)
    zc = z0 - 1.05
    for k, (st, i) in enumerate(items):
        xc = x0 + (k - (n - 1) / 2) * (width + 0.25)
        if st == "led":
            import lanemgmt as LM
            pred, rgb, strength = LM.SIGNALS[i]
            mm = flat_mat(f"ec_led_{i}", rgb, 3.0)
            box = _mesh(f"ec_led_box_{i}", [(-0.36, 0.004, -0.36), (0.36, 0.004, -0.36), (0.36, 0.004, 0.36),
                                            (-0.36, 0.004, 0.36)], [(0, 1, 2, 3)],
                        _mat("ec_led_black", (0.004, 0.004, 0.005), 0.4), c)
            o = LM.dot_matrix(f"ec_led_{i}", pred, c, mm, size=0.6, r=0.009, y=-0.002)
            box.parent = o
            box.location = (0, 0.002, 0)
            o.location = (xc, y0 - 0.02, zc)
            o.scale = (width / 0.72,) * 3
        else:
            o = SG.face(i, c, width, set_=st, name=f"ec_sign_{i}", emit=0.55, back=False)
            o.location = (xc, y0 - 0.02, zc - o["height"] / 2)
    cam_fn = lambda t, f: (Vector((x0, y0 - 9.0 + 0.35 * t, z0 + 0.2)), Vector((x0, y0, z0 + 0.2 - 0.05 * t)))  # noqa
    D.shot(name, t0, t1, "_card", 0.0, lens=lens, cam=cam_fn)
    return c


# ------------------------------------------------------------------------------------------------- look
def golden(sun_color=(1.0, 0.68, 0.42), energy=4.4, ambient=0.66, exposure=0.1):
    """Late-afternoon light on top of stage.sky, as kit/interchange's look-dev: a warm low sun and a slightly warmer
    fill. The sky picture the camera sees stays as in the approved Autobahn episodes (no tint: the old warm multiply
    made a brown band above the horizon), and the distance haze stays cool and light (finish())."""
    sc = bpy.context.scene
    sun = bpy.data.objects["sun"].data
    sun.color, sun.energy = sun_color, energy
    sun.angle = math.radians(1.0)
    nt = sc.world.node_tree
    bg = nt.nodes["Background"]
    amb = [n for n in nt.nodes if n.type == "BACKGROUND" and n != bg][0]
    amb.inputs["Strength"].default_value = ambient
    g = next(n for n in nt.nodes if n.type == "VALTORGB")
    els = sorted(g.color_ramp.elements, key=lambda e: e.position)
    for el, col in zip(els, ((0.18, 0.15, 0.12, 1), (0.88, 0.8, 0.72, 1), (0.36, 0.48, 0.76, 1))):
        el.color = col
    sc.view_settings.exposure = exposure


def bloom(threshold=1.3, strength=0.3, size=0.55):
    sc = bpy.context.scene
    ng = bpy.data.node_groups.new("a4_bloom", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    gl = ng.nodes.new("CompositorNodeGlare")
    for k, val in (("Type", "Bloom"), ("Quality", "High"), ("Threshold", threshold), ("Strength", strength),
                   ("Size", size)):
        try:
            gl.inputs[k].default_value = val
        except (KeyError, TypeError, ValueError) as e:
            print("WARN bloom", k, e)
    out = ng.nodes.new("NodeGroupOutput")
    ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
    ng.links.new(gl.outputs["Image"], out.inputs[0])
    sc.compositing_node_group = ng
    sc.render.use_compositing = True


def finish(D, o, haze=(0.62, 0.72, 0.86), dist=2600.0, skip_prefix=()):
    """Haze (episode 1: cool and light, 2.6 km), render settings, bloom, then the frames (or stills)."""
    import stage
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, D.C.N
    skip = tuple(m.name for m in bpy.data.materials
                 if m.name.startswith(("lm_led", "en_flash", "rw_lamp", "a4_", "hud", "ec_", "ck_") + tuple(skip_prefix)))
    stage.hazify_all(color=haze, dist=dist, skip=skip)
    stage.render_setup(o["SAMPLES"], o["RES"], int(round(o["RES"] * 16 / 9)))
    bloom()
    if o.get("BLEND"):
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(o["BLEND"]))
    os.makedirs(o["OUT"], exist_ok=True)
    todo = o["STILLS"] or (list(range(o["FR"][0], o["FR"][1] + 1)) if o["FR"] else list(range(1, D.C.N + 1)))
    for f in todo:
        sc.frame_set(f)
        sc.camera = D.cam_at(f) or sc.camera
        sc.render.filepath = os.path.join(o["OUT"], f"f_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("Saved", sc.render.filepath, flush=True)
        tick(f"frame {f}")
    print("RENDER_DONE", o["FR"] or o["STILLS"])
