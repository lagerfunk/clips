"""Autobahn roadworks zone (Arbeitsstelle laengerer Dauer) on the frozen world.Road: yellow temporary markings that
override the white ones, narrowed lanes, Leitbaken (Zeichen 605, Commons picture) on feet at most 10 m apart, a 1:20
taper with a lane drop (zipper merge), the advance signs at 2 km and 800 m, the speed funnel down to 274-80, the
lane-reduction sign (Zeichen 531) and a mobile barrier (Zeichen 616, Commons picture) with flashing lamps at the head
of the closure. Everything that moves or flashes is keyable, so the zipper merge can be choreographed.

side="right" (default): the right lane is closed and merges left. This matches the Commons pictures in de-core:
Zeichen 605 and 616 both send traffic past on the left. side="left": the left lane is closed (Zeichen 531-21,
605-20); the barrier then needs a 616 picture that sends traffic right (barrier_sign=...), else it is left out.
Pictures are never mirrored or edited.

Lane widths follow world.py's convention: lane line centre to lane line centre, and to the inner edge of an edge
line (world.py: 3 x 3.75 m between the 0.30 m edge lines). In the works zone the two remaining lanes are 3.00 m
(left, 2.60 to 3.25) and 3.50 m (right, 3.25 to 3.50).
  before s_t        3 lanes of 3.75 m; yellow lines lie exactly over the white ones from s_t - yellow_lead
  s_t .. s_t1       taper: the closure (yellow edge line plus Baken) sweeps across at 1:20; the closed lane's width
                    reaches zero at s_merge (the end of the lane: zip there); the surviving lane line shifts
  after s_t1        2 lanes 3.00 m + 3.50 m; white lane lines masked
  s_end (optional)  reverse taper back to the normal layout
Lane indices: 0 left, 1 middle, 2 right. rw.closing is the closed lane (2 or 0); it merges into lane 1.

    import roadworks as RW
    rw = RW.RoadWorks(road, M, env, lib, s_taper=2080.0)          # signs from s_taper - 2000
    x = rw.lane_x(1, s)                                         # lane centre at s for choreography
    tracks = rw.zipper([{"lane": 2, "s0": 1900.0, "v": 22.0}, ...])   # per-car tracks for lanemgmt.bake
    rw.flash(1, 900)                                            # barrier and chase lamps between these frames
"""
import math

import bpy

import lanemgmt as LM
import world as W

TAPER_RATIO = 20.0                 # 1:20
BAKE_GAP = 9.0                     # m between Baken (spec: at most 10 m; RSA 21: 9 m)
BAKE_GAP_MAX = 10.0
RW_SPEED = 80                      # km/h in the zone
LEFT_LANE_W = 3.00                 # remaining left lane (2.60 .. 3.25 m)
RIGHT_LANE_W = 3.50                # remaining right lane (3.25 .. 3.50 m)
LEFT_RANGE, RIGHT_RANGE = (2.60, 3.25), (3.25, 3.50)
EDGE_W = 0.30                      # yellow edge line, as wide as the white one
EDGE_TO_BAKE = 0.40                # edge line centre to the Baken
BARRIER_BEFORE = 8.0               # m from the barrier trailer (on the shoulder) to the taper start
YELLOW = (0.95, 0.66, 0.02)        # signal-yellow paint, linear base colour
X_EDGE_L, X_EDGE_R = 2.60, 14.15   # white edge line centres in world.py
X_L12, X_L23 = 6.50, 10.25         # white lane line centres
IN_L, IN_R = X_EDGE_L + EDGE_W / 2, X_EDGE_R - EDGE_W / 2      # 2.75, 14.00: inner edges of the edge lines
SIGN_IDS = {  # per closed side: lane-reduction sign, Leitbake pictures (first one in the library wins), barrier
    "right": {"lane_drop": "531-11", "bake": ("605",), "barrier": ("616",)},
    "left": {"lane_drop": "531-21", "bake": ("605-20",), "barrier": ()},
}


def sign_plan(s_t, side="right"):
    """Advance signs: (distance before the taper start, stack). 2 km and 800 m announce the works (Zeichen 123 with a
    distance plate that already carries its distance), the limit steps down 120, 100, 80 at least 200 m apart, the
    lane-reduction sign stands 10 m after the 800 m post and again at 400 m."""
    drop = SIGN_IDS[side]["lane_drop"]
    return [
        (2000.0, [("123", 1.26), ("1004-35", 0.84)]),
        (1200.0, [("274-120", 0.75)]),
        (800.0, [("123", 1.26), ("1004-800", 0.84)]),
        (790.0, [(drop, 1.6)]),
        (600.0, [("274-100", 0.75)]),
        (400.0, [(drop, 1.6)]),
        (200.0, [("274-80", 0.75)]),
    ]


def yellow_mat():
    if "rw_yellow" in bpy.data.materials:
        return bpy.data.materials["rw_yellow"]
    return W.noisy("rw_yellow", (YELLOW[0] * 0.88, YELLOW[1] * 0.86, YELLOW[2]), YELLOW, 6.0, rough=0.4, coord="UV")


def mask_mat():
    if "rw_mask" in bpy.data.materials:
        return bpy.data.materials["rw_mask"]
    return W.noisy("rw_mask", (0.016, 0.017, 0.019), (0.026, 0.027, 0.03), 4.0, rough=0.85, coord="UV")


class RoadWorks:
    def __init__(self, road, M, c, lib, s_taper=2080.0, s_end=None, side="right", yellow_lead=150.0, road_s0=0.0,
                 strict=True, both_sides=True, dress=True, barrier=True, mask_white=True, signs=None,
                 barrier_sign=None, name="rw"):
        """road_s0: where the stage's road (and its white dashes) starts, so the yellow dashes lie exactly over the
        white ones; signs: list of (distance before the taper, stack) to replace sign_plan(); strict=False skips
        signs missing from the library with a WARN instead of failing."""
        if side not in SIGN_IDS:
            raise ValueError("side is 'right' or 'left'")
        self.road, self.M, self.c, self.lib, self.name, self.side = road, M, c, lib, name, side
        self.closing = 2 if side == "right" else 0
        self.s_t = float(s_taper)
        if side == "right":
            self.x_close0 = X_EDGE_R
            self.x_close1 = IN_L + LEFT_LANE_W + RIGHT_LANE_W + EDGE_W / 2           # 9.40
            self.x_line0, self.x_line1 = X_L12, IN_L + LEFT_LANE_W                   # 6.50 -> 5.75
            self.x_drop = X_L23
            x_zero = X_L23 + EDGE_W / 2                                              # closed lane width 0
        else:
            self.x_close0 = X_EDGE_L
            self.x_close1 = IN_R - RIGHT_LANE_W - LEFT_LANE_W - EDGE_W / 2           # 7.35
            self.x_line0, self.x_line1 = X_L23, IN_R - RIGHT_LANE_W                  # 10.25 -> 10.50
            self.x_drop = X_L12
            x_zero = X_L12 - EDGE_W / 2
        self.taper_len = TAPER_RATIO * abs(self.x_close1 - self.x_close0)    # 1:20 over the full lateral shift
        self.s_t1 = self.s_t + self.taper_len
        self.s_merge = self.s_t + TAPER_RATIO * abs(x_zero - self.x_close0)
        self.s_e = float(s_end) if s_end else None
        self.s_e1 = self.s_e + self.taper_len if self.s_e else None
        self.s_y0 = self.s_t - yellow_lead
        self.s_last = min(road.L, self.s_e1 + 30.0 if self.s_e else road.L)
        self.road_s0, self.strict, self.barrier_sign = road_s0, strict, barrier_sign
        self.baken, self.signs, self.lamps, self.taper_lamps = [], [], [], []
        self.placed = {}
        self.objects = []
        self.barrier = self.barrier_face = None
        self.barrier_lamps = []
        yel = yellow_mat()
        # --- yellow markings (lie over the white ones, then take over)
        self.objects.append(LM.ribbon(road, f"{name}_yellow_edgeL", self.edge_left, EDGE_W, self.s_y0, self.s_last,
                                      yel, c, dz=0.010, step=1.0))
        self.objects.append(LM.ribbon(road, f"{name}_yellow_edgeR", self.edge_right, EDGE_W, self.s_y0, self.s_last,
                                      yel, c, dz=0.010, step=1.0))
        d0 = road_s0 + 18.0 * math.ceil((self.s_y0 - road_s0) / 18.0)    # in phase with world.py's 6 m / 12 m
        self.dash0 = d0
        self.objects.append(LM.ribbon_dashes(road, f"{name}_yellow_drop", lambda s_: self.x_drop, 0.15, d0,
                                             self.s_merge - 6.0, yel, c, dz=0.010))
        self.objects.append(LM.ribbon_dashes(road, f"{name}_yellow_lane", self.lane_line, 0.15, d0,
                                             self.s_last, yel, c, dz=0.010))
        if mask_white:
            m = mask_mat()
            s1 = self.s_e1 if self.s_e else self.s_last
            for x in (X_L12, X_L23):
                self.objects.append(road.strip(f"{name}_mask_{x}", x - 0.13, x + 0.13, self.s_t + 2.0, s1, m, c,
                                               dz0=0.008))
        self._baken()
        for d, stack in (signs if signs is not None else sign_plan(self.s_t, side)):
            self._sign(stack, self.s_t - d, f"{name}_sign_{int(d)}", both_sides)
        if barrier:
            self.barrier = self._barrier()
        if dress:
            self._dress()

    # ---------------------------------------------------------------- geometry along s
    def closure(self, s):
        """0 before the taper, 1 when the closed lane is fully covered (lateral progress of the closure)."""
        if s <= self.s_t:
            u = 0.0
        elif s < self.s_t1:
            u = (s - self.s_t) / self.taper_len
        else:
            u = 1.0
        if self.s_e:
            if s >= self.s_e1:
                return 0.0
            if s > self.s_e:
                u = min(u, 1.0 - (s - self.s_e) / self.taper_len)
        return u

    def x_closure(self, s):
        return self.x_close0 + (self.x_close1 - self.x_close0) * self.closure(s)

    def edge_left(self, s):
        return self.x_closure(s) if self.side == "left" else X_EDGE_L

    def edge_right(self, s):
        return self.x_closure(s) if self.side == "right" else X_EDGE_R

    def lane_line(self, s):
        """The lane line that survives (between the two remaining lanes)."""
        return self.x_line0 + (self.x_line1 - self.x_line0) * self.closure(s)

    def bake_x(self, s):
        return self.x_closure(s) + (EDGE_TO_BAKE if self.side == "right" else -EDGE_TO_BAKE)

    def bounds(self, s):
        """Lane boundaries from left to right at s: inner edges of the edge lines and lane line centres (3 lanes before
        the closed lane's width reaches zero, 2 after)."""
        el, er, ll = self.edge_left(s) + EDGE_W / 2, self.edge_right(s) - EDGE_W / 2, self.lane_line(s)
        if s < self.s_merge:
            return [el, ll, self.x_drop, er] if self.side == "right" else [el, self.x_drop, ll, er]
        return [el, ll, er]

    def widths(self, s):
        b = self.bounds(s)
        return [round(b[i + 1] - b[i], 4) for i in range(len(b) - 1)]

    def lane_x(self, lane, s):
        """Centre of lane 0 (left), 1 (middle) or 2 (right) at s. The closed lane's centre runs between the dropped
        line and the closure until its width is zero, then joins lane 1."""
        el, er, ll = self.edge_left(s) + EDGE_W / 2, self.edge_right(s) - EDGE_W / 2, self.lane_line(s)
        if self.side == "right":
            d = min(self.x_drop, er)
            return ((el + ll) / 2, (ll + d) / 2, (d + max(er, d)) / 2)[lane]
        d = max(self.x_drop, el)
        return ((min(el, d) + d) / 2, (d + ll) / 2, (ll + er) / 2)[lane]

    # ---------------------------------------------------------------- parts
    def _bake_coll(self):
        key = "rw_bake_unit"
        if key in bpy.data.collections:
            return bpy.data.collections[key]
        root = bpy.data.collections.new(key)
        self.lib.children.link(root)
        foot = W.noisy("rw_foot", (0.03, 0.03, 0.03), (0.06, 0.06, 0.06), 9.0, rough=0.9, bump=0.3)
        b = LM.MB()
        b.box((0, 0.0, 0.05), (0.42, 0.78, 0.10))      # recycled-rubber foot plate
        b.box((0, 0.0, 0.11), (0.16, 0.30, 0.04))
        b.obj("rw_bake_foot", foot, root)
        p = LM.MB()
        p.box((0, 0.02, 0.62), (0.06, 0.03, 1.04))     # upright behind the plate, up to the lamp
        p.obj("rw_bake_post", LM.mat("rw_bake_plastic", (0.6, 0.6, 0.58), 0.6), root)
        return root

    def _bake_face(self, which):
        """The Commons picture of the Leitbake (250 mm wide), unchanged, 0.22 m above the foot."""
        key = f"rw_bake_face_{which}"
        if key in bpy.data.collections:
            return bpy.data.collections[key]
        root = bpy.data.collections.new(key)
        self.lib.children.link(root)
        f = LM.face(which, root, 0.25, emit=0.04, name="rw_bake_plate")
        f.location.z = 0.18
        return root

    def _lamp(self, s, x, z, name, r=0.09):
        """Round amber warning lamp (lens facing traffic) in a black housing; brightness = obj.color (key_flash)."""
        lm = LM.flash_mat("rw_lamp", (1.0, 0.55, 0.03), 16.0)
        b = LM.MB()
        seg = 20
        b.poly([(r * math.cos(2 * math.pi * k / seg), -0.03, r * math.sin(2 * math.pi * k / seg))
                for k in range(seg)], smooth=False)
        o = b.obj(name, lm, self.c)
        o.matrix_world = self.road.matrix(s, x, z)
        o.color = (0.0, 0.0, 0.0, 1.0)
        hs = LM.MB()
        hs.tube((0, -0.028, 0), (0, 0.05, 0), r + 0.015, seg)
        hs.box((0, 0.05, 0), (2 * r + 0.03, 0.01, 2 * r + 0.03))
        hs.box((0, 0.03, -r - 0.07), (0.035, 0.035, 0.14))
        h = hs.obj(name + "_housing", LM.mat("rw_lamp_housing", (0.02, 0.02, 0.02), 0.5), self.c)
        h.parent = o
        return o

    def _baken(self):
        which = LM.pick(*SIGN_IDS[self.side]["bake"])
        if which is None:
            if self.strict:
                raise FileNotFoundError("Leitbake picture not in the sign library")
            print("WARN roadworks: no Leitbake picture, Baken skipped")
            return
        self.bake_sign = which
        unit, face = self._bake_coll(), self._bake_face(which)
        s_to = self.s_e1 if self.s_e else self.s_last - 1.0
        s, k = self.s_t, 0
        while s <= s_to + 1e-6:
            x = self.bake_x(s)
            self.road.place(unit, s, x, 0.0, c=self.c, name=f"{self.name}_bake_foot")
            o = self.road.place(face, s, x, 0.0, c=self.c, name=f"{self.name}_bake")
            o["road_s"], o["road_x"], o["sign"] = float(s), float(x), which
            self.baken.append(o)
            if s <= self.s_t1 + 1e-6 or (self.s_e and s >= self.s_e - 1e-6):
                lamp = self._lamp(s, x, 1.26, f"{self.name}_bake_lamp")
                self.lamps.append(lamp)
                self.taper_lamps.append((k, lamp))
            s += BAKE_GAP
            k += 1

    def _sign(self, stack, s, name, both_sides):
        if s < self.road_s0:
            print(f"WARN roadworks: sign {name} at s = {s:.0f} is before the built road (from {self.road_s0}); skipped")
            return
        ok = [(i, w) for i, w in stack if LM.available(i) or LM.STUB]
        missing = [i for i, w in stack if (i, w) not in ok]
        if missing:
            if self.strict:
                raise FileNotFoundError(f"signs {missing} not in the library (signs/de-lanemgmt.json lists them)")
            print(f"WARN roadworks: {name} without {missing} (not in the sign library)")
        if not ok:
            return
        for side, x in ((1, 18.4), (-1, 1.35)) if both_sides else ((1, 18.4),):
            o = LM.road_sign(self.road, ok, s, x, self.c, f"{name}_{'r' if side > 0 else 'm'}",
                             h=-0.06 if side > 0 else 0.0, bottom=1.6)
            o["dist_before_taper"] = self.s_t - s
            self.signs.append(o)
        self.placed[round(self.s_t - s)] = [i for i, _w in ok]

    def _barrier(self):
        """Mobile barrier trailer (fahrbare Absperrtafel) at the head of the closure, face to traffic: it stands on the
        hard shoulder BARRIER_BEFORE m before the taper start, beside the closed lane, so the lane stays open to its
        end for the zipper. The Commons 616 picture unchanged, two flashing lamps on top. (left closure: in the
        median strip side, only with a barrier_sign that points right.)"""
        ids = (self.barrier_sign,) if self.barrier_sign else SIGN_IDS[self.side]["barrier"]
        which = LM.pick(*ids) if ids else None
        if which is None:
            print(f"WARN roadworks: no barrier picture for a {self.side} closure, barrier left out")
            return None
        out = 1.0 if self.side == "right" else -1.0
        s = self.s_t - BARRIER_BEFORE
        x = self.x_close0 + out * 1.45
        self.barrier_s, self.barrier_x = s, x
        root = LM.root_at(self.road, s, x, self.c, f"{self.name}_barrier")
        root["sign"] = which
        dark = LM.mat("rw_trailer_frame", (0.05, 0.05, 0.055), 0.5, metal=0.4)
        b = LM.MB()
        b.box((0, 0.9, 0.62), (1.9, 2.6, 0.12))            # chassis
        b.box((0, 2.5, 0.55), (0.12, 1.2, 0.08))           # drawbar
        for sx in (-1, 1):
            b.box((sx * 0.78, 0.15, 1.6), (0.1, 0.1, 2.0))  # panel frame posts
        b.obj(f"{self.name}_barrier_frame", dark, self.c, root)
        tyre = LM.mat("rw_tyre", (0.025, 0.025, 0.025), 0.8)
        t = LM.MB()
        for sx in (-1, 1):
            t.tube((sx * 0.95, 0.9, 0.33), (sx * 1.15, 0.9, 0.33), 0.33, 20)
        t.obj(f"{self.name}_barrier_wheels", tyre, self.c, root)
        f = LM.face(which, self.c, 1.6, emit=0.05, name=f"{self.name}_barrier_616")
        f.parent = root
        f.location = (0, 0.0, 0.72)
        self.barrier_face = f
        self._lamp_mask(f)
        top = 0.72 + f["height"]
        for sx in (-1, 1):
            lp = self._lamp(s, x + sx * 0.62, top + 0.14, f"{self.name}_barrier_lamp", r=0.12)
            self.barrier_lamps.append(lp)
            self.lamps.append(lp)
        return root

    def _lamp_mask(self, f):
        """The panel's lamp positions (the yellow discs of the Commons picture) glow when the arrow flashes: the
        picture is unchanged, only its emission strength follows the object's colour (keyed by flash())."""
        m = f.data.materials[0].copy()
        m.name = "rw_616_flash"
        nt = m.node_tree
        p = nt.nodes["Principled BSDF"]
        tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(tex.outputs["Color"], sep.inputs["Color"])
        rg = nt.nodes.new("ShaderNodeMath")          # yellow = high red and green, low blue
        rg.operation = "MINIMUM"
        nt.links.new(sep.outputs[0], rg.inputs[0])
        nt.links.new(sep.outputs[1], rg.inputs[1])
        yb = nt.nodes.new("ShaderNodeMath")
        yb.operation = "SUBTRACT"
        nt.links.new(rg.outputs[0], yb.inputs[0])
        nt.links.new(sep.outputs[2], yb.inputs[1])
        th = nt.nodes.new("ShaderNodeMath")
        th.operation = "GREATER_THAN"
        th.inputs[1].default_value = 0.35
        nt.links.new(yb.outputs[0], th.inputs[0])
        oi = nt.nodes.new("ShaderNodeObjectInfo")
        so = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(oi.outputs["Color"], so.inputs["Color"])
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        nt.links.new(th.outputs[0], mul.inputs[0])
        nt.links.new(so.outputs[0], mul.inputs[1])
        mul2 = nt.nodes.new("ShaderNodeMath")
        mul2.operation = "MULTIPLY_ADD"
        mul2.inputs[1].default_value = 10.0
        mul2.inputs[2].default_value = 0.05
        nt.links.new(mul.outputs[0], mul2.inputs[0])
        nt.links.new(tex.outputs["Color"], p.inputs["Emission Color"])
        nt.links.new(mul2.outputs[0], p.inputs["Emission Strength"])
        f.data = f.data.copy()
        f.data.materials[0] = m
        f.color = (0, 0, 0, 1)
        self.lamps.append(f)

    def _dress(self):
        """Works area behind the closure: milled asphalt and a row of cones along the closed lane."""
        if not self.baken:
            return
        s0, s1 = self.s_t1 + 12.0, min(self.s_last - 5.0, self.s_t1 + 300.0)
        if s1 <= s0:
            return
        milled = W.noisy("rw_milled", (0.05, 0.05, 0.052), (0.1, 0.1, 0.1), 2.5, rough=0.95, bump=0.6)
        if self.side == "right":
            a, b_ = self.x_close1 + 0.9, IN_R - 0.2
        else:
            a, b_ = IN_L + 0.2, self.x_close1 - 0.9
        self.road.strip(f"{self.name}_milled", a, b_, s0, s1, milled, self.c, dz0=0.012)
        cone_m = LM.mat("rw_cone", (0.9, 0.18, 0.02), 0.45)
        white = LM.mat("rw_cone_white", (0.9, 0.9, 0.88), 0.4)
        xc = b_ - 0.4 if self.side == "right" else a + 0.4
        s = s0 + 8.0
        while s < s1:
            for r0, r1, z0, z1, m_ in ((0.16, 0.12, 0.03, 0.25, cone_m), (0.12, 0.09, 0.25, 0.38, white),
                                       (0.09, 0.03, 0.38, 0.62, cone_m)):
                cb = LM.MB()
                seg = 14
                for z, r in ((z0, r0), (z1, r1)):
                    for j in range(seg):
                        a_ = 2 * math.pi * j / seg
                        cb.V.append((r * math.cos(a_), r * math.sin(a_), z))
                for j in range(seg):
                    j2 = (j + 1) % seg
                    cb.F.append((j, j2, seg + j2, seg + j))
                    cb.S.append(True)
                o = cb.obj(f"{self.name}_cone", m_, self.c)
                o.matrix_world = self.road.matrix(s, xc, 0.0)
            s += 30.0

    # ---------------------------------------------------------------- keys
    def flash(self, f0, f1, period=24, chase=2):
        """Lamps on between frames f0 and f1: the barrier lamps and the 616 lamp positions flash together (period
        frames, half on), the taper lamps run as a chase light towards the closure (chase frames apart)."""
        taper = {id(lp) for _k, lp in self.taper_lamps}
        for lamp in self.lamps:
            if id(lamp) in taper:
                continue
            pairs = [(min(f0 - 1, 0), 0.0)]
            f = f0
            while f < f1:
                pairs += [(f, 1.0), (f + period // 2, 0.0)]
                f += period
            pairs.append((f1, 0.0))
            LM.key_flash(lamp, pairs)
        n = len(self.taper_lamps)
        cyc = max(period, n * chase + 6)
        for k, lamp in self.taper_lamps:
            pairs = [(min(f0 - 1, 0), 0.0)]
            f = f0 + k * chase
            while f < f1:
                pairs += [(f, 1.0), (f + 3, 0.0)]
                f += cyc
            pairs.append((f1, 0.0))
            LM.key_flash(lamp, pairs)

    def zipper(self, cars, fps=LM.FPS, n=None, v_zone=RW_SPEED / 3.6, merge_at=None, merge_len=40.0):
        """Tracks for a zipper merge. cars: list of dicts {"lane": 0|1|2, "s0": s at frame 1, "v": m/s}. Cars in the
        closed lane drive to its end and move into lane 1 over merge_len metres ending at merge_at (default 8 m
        before s_merge), indicating from 60 m before the move. Returns per-frame track dicts in the same order
        (CONTRACTS motion format plus "pitch") for lanemgmt.bake(). Gaps between cars are the caller's choreography."""
        n = n or bpy.context.scene.frame_end
        m_end = merge_at or (self.s_merge - 8.0)
        m0 = m_end - merge_len
        side = "L" if self.side == "right" else "R"
        out = []
        for car in cars:
            lane = car["lane"]
            v0 = car.get("v", v_zone)
            sv, s, v = [], car["s0"], v0
            for i in range(n):
                sv.append((s, v))
                target = min(v0, v_zone) if s > self.s_t - 300 else v0
                v += max(-2.5 / fps, min(1.5 / fps, target - v))
                s += v / fps
            if lane == self.closing:
                def xf(s_):
                    u = LM.smoother((s_ - m0) / merge_len)
                    xa = self.lane_x(lane, min(s_, m0))
                    return xa + (self.lane_x(1, s_) - xa) * u
                ind_frames = {i for i, (s_, _v) in enumerate(sv) if m0 - 60.0 < s_ < m_end + 10.0}
            else:
                def xf(s_, lane=lane):
                    return self.lane_x(lane, s_)
                ind_frames = set()
            out.append(LM.road_track(self.road, sv, xf, ind=(lambda i, fr=ind_frames: side if i in fr else None)))
        return out
