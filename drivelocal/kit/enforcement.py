"""Speed enforcement for the Drive Like a Local Autobahn kit, all generic (no maker, no brand, no logo):
- SpeedTrailer: a mobile enforcement trailer, body 3.15 m long, 1.52 m wide, 1.84 m high (1.62 m lowered): rounded
  armoured shell with panel seams, service door and battery hatch, lens and flash windows towards traffic, wheels in
  arches, four screw-jack legs, A-frame drawbar with hitch head and jockey wheel.
- CameraColumn: a fixed speed camera column (grey tower with dark windows), about 3 m, on a concrete plinth.
- LaserCheck: a Polizei estate (vehicles.car police=True) parked off the carriageway with a handheld laser gun on a
  tripod and its operator's table.
Each has a subtle flash: flash(frame) keys a short pulse (2 frames) of a soft white lamp and the emitter window.

Germany has no section control in operation: the only system (B6 Gleidingen to Rethen) was switched off at the end
of 2023. This module never builds one, and assert_no_section_control() fails if anything in the scene is named or
labelled as one.

    import enforcement as EN
    tr = EN.SpeedTrailer(road, env, s=900.0, x=17.9)          # on the verge, facing oncoming traffic
    tr.flash(212)
    col = EN.CameraColumn(road, env, s=1400.0, x=19.0)
    lc = EN.LaserCheck(road, env, lib, s=1800.0, x=19.5)
"""
import math
import re

import bmesh
import bpy
from mathutils import Vector

import lanemgmt as LM
import world as W

try:
    import vehicles as V
except Exception:  # noqa: BLE001
    V = None

TRAILER_L, TRAILER_W, TRAILER_H, TRAILER_H_LOW = 3.15, 1.52, 1.84, 1.62
COLUMN_H = 3.0          # modelling default only (no source states a height)
FLASH_FRAMES = 2
BANNED = re.compile(r"section[\s_-]*control|abschnitts[\s_-]*kontrolle|streckenradar|average[\s_-]*speed|"
                    r"trajectory[\s_-]*control|tutor", re.I)


def assert_no_section_control():
    """Raise if any object, collection, material, text body or custom property names a section control."""
    hits = []
    for coll in (bpy.data.objects, bpy.data.collections, bpy.data.materials, bpy.data.meshes, bpy.data.curves):
        for idb in coll:
            if BANNED.search(idb.name):
                hits.append(idb.name)
            for k in idb.keys():
                v = idb.get(k)
                if BANNED.search(k) or (isinstance(v, str) and BANNED.search(v)):
                    hits.append(f"{idb.name}[{k}]")
    for cu in bpy.data.curves:
        body = getattr(cu, "body", "")
        if body and BANNED.search(body):
            hits.append(f"text {cu.name}: {body}")
    if hits:
        raise AssertionError("section control must not appear (B6 system off since the end of 2023): " + ", ".join(hits))
    return True


def _flash_parts(c, parent, loc, name, size=(0.22, 0.24), strength=40.0, light_energy=1600.0):
    """Emitter window (emission keyed via obj.color) plus a small area light for the soft spill on the cars."""
    m = LM.flash_mat("en_flash", (1.0, 0.97, 0.92), strength)
    b = LM.MB()
    w, h = size
    b.poly([(-w / 2, 0, h / 2), (w / 2, 0, h / 2), (w / 2, 0, -h / 2), (-w / 2, 0, -h / 2)])   # faces +Y
    win = b.obj(name + "_flashwin", m, c, parent)
    win.location = loc
    win.color = (0, 0, 0, 1)
    ld = bpy.data.lights.new(name + "_flashlight", "AREA")
    ld.shape = "RECTANGLE"
    ld.size, ld.size_y = w, h
    ld.energy = 0.0
    ld.color = (1.0, 0.97, 0.92)
    lo = bpy.data.objects.new(name + "_flashlight", ld)
    c.objects.link(lo)
    lo.parent = parent
    lo.location = (loc[0], loc[1] - 0.02, loc[2])
    lo.rotation_euler = (math.radians(90), 0, 0)      # area light faces -Z: rotated to face +Y (towards traffic)
    lo["peak"] = light_energy
    return win, lo


def _key_flash(win, lo, frames):
    pairs = [(1, 0.0)]
    for f in sorted(frames):
        pairs += [(f, 1.0), (f + FLASH_FRAMES, 0.0)]
    LM.key_flash(win, pairs)
    ld = lo.data
    for f, v in pairs:
        ld.energy = v * lo["peak"]
        ld.keyframe_insert("energy", frame=f)
    if ld.animation_data and ld.animation_data.action:
        for fc in LM.stage.fcurves(ld):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


class _Device:
    def __init__(self, road, c, s, x, name, facing="oncoming", h=0.0):
        """facing: "oncoming" = the sensor looks against our travel direction (towards approaching traffic)."""
        self.road, self.c = road, c
        yaw = math.pi if facing == "oncoming" else 0.0
        self.root = LM.root_at(road, s, x, c, name, h=h, yaw=yaw)
        self.root["enforcement"] = type(self).__name__
        self.flashes = []
        self.win = self.light = None

    def flash(self, frame):
        """A subtle flash pulse at this frame (2 frames long). Call again for more pulses."""
        self.flashes.append(int(frame))
        _key_flash(self.win, self.light, self.flashes)
        return self


class SpeedTrailer(_Device):
    """Generic mobile enforcement trailer on the verge. Origin at the middle of the body footprint on the ground; the
    sensor nose faces approaching traffic (local +y after the yaw). Body: 3.15 x 1.52 x 1.84 m (lowered=True: 1.62 m).
    Details: armoured shell of flat panels with rounded edges, panel seams and a recessed service door, a
    battery hatch with hinges and a lock on the flank, lens window and flash window on the nose, wheels in arches
    with mudguards, four screw-jack support legs on pads, and the A-frame drawbar with hitch head and jockey wheel
    (it stays on when deployed; it is outside the 3.15 m body length). No maker, no logo."""

    def __init__(self, road, c, s, x=17.9, h=-0.08, lowered=False, color=(0.22, 0.23, 0.24), name="en_trailer",
                 facing="oncoming", drawbar=True):
        super().__init__(road, c, s, x, name, facing, h)
        L, Wd = TRAILER_L, TRAILER_W
        H = TRAILER_H_LOW if lowered else TRAILER_H
        self.dims = (L, Wd, H)
        body_m = LM.mat("en_trailer_paint", color, 0.36, metal=0.55, coat=0.35)
        seam_m = LM.mat("en_trailer_seam", (0.03, 0.03, 0.032), 0.6)
        dark = LM.mat("en_trailer_dark", (0.025, 0.025, 0.027), 0.55)
        steel = LM.mat("en_trailer_steel", (0.5, 0.51, 0.52), 0.32, metal=0.95)
        glass = LM.mat("en_trailer_window", (0.004, 0.005, 0.007), 0.03, spec=1.0, coat=1.0)
        lens_m = LM.mat("en_trailer_lens", (0.01, 0.015, 0.03), 0.02, metal=0.6, coat=1.0)
        tyre = LM.mat("en_tyre", (0.025, 0.025, 0.025), 0.8)
        rim = LM.mat("en_rim", (0.55, 0.56, 0.57), 0.3, metal=0.95)
        g = self.root
        zb = 0.30
        y0, y1 = -L / 2, L / 2
        hw = Wd / 2
        self.zb = zb

        # ---- shell: angular wedge (stations along y) with every edge rounded by a bevel, like pressed and welded
        # armour panels
        z_nose = 1.0
        st = [(y1, z_nose, 0.90), (y1 - 0.12, z_nose + 0.12, 0.97), (y1 - 0.62, H, 1.0), (y1 - 1.15, H, 1.0),
              (y0 + 0.12, H - 0.26, 1.0), (y0, H - 0.34, 0.95)]
        verts, faces = [], []
        for y, zt, k in st:
            zbelt = min(zt - 0.24, 1.25)
            for xx, zz in ((-0.90, zb), (-1.0, zb + 0.14), (-1.0, zbelt), (-0.86, zt - 0.05), (-0.55, zt),
                           (0.55, zt), (0.86, zt - 0.05), (1.0, zbelt), (1.0, zb + 0.14), (0.90, zb)):
                verts.append((xx * hw * k, y, zz))
        n = 10
        for i in range(len(st) - 1):
            for j in range(n):
                j2 = (j + 1) % n
                faces.append((i * n + j, (i + 1) * n + j, (i + 1) * n + j2, i * n + j2))
        faces.append(tuple(range(n)))
        faces.append(tuple(range((len(st) - 1) * n + n - 1, (len(st) - 1) * n - 1, -1)))
        body = W.mesh_obj(name + "_body", verts, faces, body_m, c)
        body.parent = g
        bm = bmesh.new()
        bm.from_mesh(body.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(body.data)
        bm.free()
        me = body.data
        bv = body.modifiers.new("round", "BEVEL")          # flat armour panels, every edge rounded
        bv.width, bv.segments, bv.limit_method = 0.055, 4, "ANGLE"
        bv.angle_limit = math.radians(20)
        bv.harden_normals = True
        for p in me.polygons:
            p.use_smooth = True
        self.body = body

        def surf(x, y, z, nrm_dir):
            """Ray-cast onto the evaluated shell from outside (local coords); returns (hit point, normal)."""
            bpy.context.view_layer.update()
            dg = bpy.context.evaluated_depsgraph_get()
            ev = body.evaluated_get(dg)
            o_ = Vector((x, y, z)) + Vector(nrm_dir) * 2.0
            hit, loc, nrm, _i = ev.ray_cast(o_, -Vector(nrm_dir), distance=4.0)
            return (loc, nrm) if hit else (Vector((x, y, z)), Vector(nrm_dir))

        def plate(nm, mat_, centre_dir, w, hgt, off=0.004, axis_u=None):
            """Flat panel conforming to the shell at a point: centre + direction (outward)."""
            (x, y, z), dirv = centre_dir
            loc, nrm = surf(x, y, z, dirv)
            nrm = nrm.normalized()
            u = (axis_u or Vector((0, 0, 1)).cross(nrm)).normalized()
            if u.length < 1e-6:
                u = Vector((1, 0, 0))
            v = nrm.cross(u).normalized()
            cpt = loc + nrm * off
            pts = [cpt - u * w / 2 - v * hgt / 2, cpt + u * w / 2 - v * hgt / 2, cpt + u * w / 2 + v * hgt / 2,
                   cpt - u * w / 2 + v * hgt / 2]
            mb = LM.MB()
            mb.poly([tuple(p) for p in pts])
            o = mb.obj(nm, mat_, c, g)
            if o.data.polygons[0].normal.dot(nrm) < 0:
                o.data.flip_normals()
            return o, cpt, nrm, u, v

        # ---- nose: lens window (large, dark), flash window (white, emissive when keyed), a small sensor port
        rake_n = Vector((0.0, 0.62, 0.42)).normalized()
        self.rake = math.atan2(rake_n.z, rake_n.y)
        plate(name + "_lens_window", glass, ((0.0, y1 - 0.30, 1.30), rake_n), 0.98, 0.34, axis_u=Vector((1, 0, 0)))
        for k, xx in enumerate((-0.28, 0.0, 0.28)):
            plate(f"{name}_lens{k}", lens_m, ((xx, y1 - 0.30, 1.30), rake_n), 0.13, 0.13, off=0.007,
                  axis_u=Vector((1, 0, 0)))
        _o, fpt, fn, fu, fv = plate(name + "_flash_frame", dark, ((0.0, y1 - 0.06, 0.82), (0, 1, 0.05)), 0.62, 0.17,
                                    axis_u=Vector((1, 0, 0)))
        # ---- panel seams: two vertical seams round the shell and the outline of a service door on the flank
        seams = LM.MB()
        for yy in (y1 - 0.62, y1 - 1.62):
            prev = None
            for t in range(0, 21):
                ang = math.pi * t / 20
                dirv = Vector((math.cos(ang), 0, math.sin(ang)))
                loc, nrm = surf(0, yy, 1.0 if t not in (0, 20) else 0.8, dirv) if 0 < t < 20 else surf(
                    math.cos(ang) * hw, yy, 0.8, dirv)
                p = loc + nrm * 0.003
                if prev is not None:
                    seams.tube(tuple(prev), tuple(p), 0.007, 4)
                prev = p
        seams.obj(name + "_seams", seam_m, c, g)
        door = LM.MB()
        for sx in (-1, 1):
            loc0, n0 = surf(sx * hw, -0.55, 0.62, (sx, 0, 0))
            xw = loc0.x + sx * 0.004
            corners = [(-1.30, 0.58), (-0.20, 0.58), (-0.20, 1.38), (-1.30, 1.38)]
            pts = [Vector((xw, y_, z_)) for y_, z_ in corners]
            for a_, b_ in zip(pts, pts[1:] + pts[:1]):
                door.tube(tuple(a_), tuple(b_), 0.007, 4)
            for zz in (0.72, 1.24):                                              # hinges
                door.box((xw + sx * 0.012, -1.31, zz), (0.025, 0.05, 0.11))
            door.box((xw + sx * 0.012, -0.27, 0.98), (0.02, 0.04, 0.12))       # lock
            # battery hatch low at the front of the flank, with a grille
            hp = [Vector((xw, y_, z_)) for y_, z_ in ((0.05, 0.42), (0.75, 0.42), (0.75, 0.82), (0.05, 0.82))]
            for a_, b_ in zip(hp, hp[1:] + hp[:1]):
                door.tube(tuple(a_), tuple(b_), 0.006, 4)
            for k in range(6):
                door.box((xw + sx * 0.004, 0.40 + k * 0.012 * 4, 0.62), (0.006, 0.026, 0.24))
            door.box((xw + sx * 0.01, 0.40, 0.88), (0.015, 0.16, 0.02))         # rain lip
        door.obj(name + "_door", seam_m, c, g)
        # ---- wheel arches, mudguards, wheels under the shell
        arch = LM.MB()
        tb = LM.MB()
        rb = LM.MB()
        yw = -0.25
        for sx in (-1, 1):
            xo = sx * (hw - 0.02)
            prev = None
            for t in range(0, 13):
                ang = math.pi * t / 12
                p = (xo, yw + math.cos(ang) * 0.36, 0.30 + math.sin(ang) * 0.36)
                if prev:
                    arch.box(((prev[0] + p[0]) / 2, (prev[1] + p[1]) / 2, (prev[2] + p[2]) / 2), (0.06, 0.1, 0.05))
                prev = p
            tb.tube((sx * (hw - 0.30), yw, 0.27), (sx * (hw - 0.08), yw, 0.27), 0.27, 28)
            rb.tube((sx * (hw - 0.079), yw, 0.27), (sx * (hw - 0.077), yw, 0.27), 0.16, 20)
            for k in range(5):                                                   # wheel nuts
                a_ = 2 * math.pi * k / 5
                rb.tube((sx * (hw - 0.077), yw + 0.07 * math.cos(a_), 0.27 + 0.07 * math.sin(a_)),
                        (sx * (hw - 0.06), yw + 0.07 * math.cos(a_), 0.27 + 0.07 * math.sin(a_)), 0.012, 6)
        arch.obj(name + "_arches", dark, c, g)
        tb.obj(name + "_tyres", tyre, c, g)
        rb.obj(name + "_rims", rim, c, g)
        # ---- chassis rails and four screw-jack support legs on pads
        ch_ = LM.MB()
        for sx in (-1, 1):
            ch_.box((sx * 0.42, -0.15, 0.24), (0.07, L - 0.4, 0.09))
        for sy in (y0 + 0.28, y1 - 0.32):
            for sx in (-1, 1):
                xl = sx * (hw - 0.05)
                ch_.box((xl, sy, 0.27), (0.11, 0.11, 0.16))                      # outer tube
                ch_.box((xl, sy, 0.38), (0.16, 0.06, 0.03))                      # crank boss
                ch_.box((xl, sy, 0.012), (0.24, 0.24, 0.024))                    # foot pad
        ch_.obj(name + "_chassis", dark, c, g)
        leg = LM.MB()
        for sy in (y0 + 0.28, y1 - 0.32):
            for sx in (-1, 1):
                xl = sx * (hw - 0.05)
                leg.tube((xl, sy, 0.024), (xl, sy, 0.2), 0.03, 10)               # inner screw tube
                leg.tube((xl, sy, 0.40), (xl + sx * 0.12, sy, 0.40), 0.008, 6)  # crank handle
        leg.obj(name + "_legs", steel, c, g)
        # ---- A-frame drawbar with hitch head and jockey wheel, at the rear (away from traffic)
        self.drawbar = None
        if drawbar:
            db = LM.MB()
            yb0, yb1 = y0 + 0.15, y0 - 1.15
            for sx in (-1, 1):
                db.tube((sx * 0.42, yb0, 0.33), (0.0, yb1, 0.40), 0.035, 10)
            db.tube((0.0, yb1, 0.40), (0.0, yb1 - 0.25, 0.40), 0.04, 12)
            db.tube((-0.42, yb0 - 0.02, 0.33), (0.42, yb0 - 0.02, 0.33), 0.03, 8)
            db.obj(name + "_drawbar", dark, c, g)
            hk = LM.MB()
            hk.box((0.0, yb1 - 0.33, 0.43), (0.11, 0.2, 0.09))                    # hitch head
            hk.tube((0.0, yb1 - 0.36, 0.48), (0.0, yb1 - 0.2, 0.50), 0.018, 8)   # handle
            hk.tube((0.0, yb1 + 0.25, 0.08), (0.0, yb1 + 0.25, 0.42), 0.028, 10)  # jockey wheel post
            hk.tube((0.0, yb1 + 0.25, 0.42), (0.0, yb1 + 0.25, 0.47), 0.02, 8)
            hk.obj(name + "_hitch", steel, c, g)
            jw = LM.MB()
            jw.tube((-0.03, yb1 + 0.25, 0.08), (0.03, yb1 + 0.25, 0.08), 0.08, 16)
            jw.obj(name + "_jockey", tyre, c, g)
            self.drawbar = db
        # ---- generic markings: red and white retroreflective strips at the rear corners, side reflectors
        refl_r = LM.mat("en_refl_red", (0.6, 0.02, 0.02), 0.2, emit=(1, 0.05, 0.03), estr=0.15)
        refl_w = LM.mat("en_refl_white", (0.9, 0.9, 0.9), 0.2, emit=(1, 1, 1), estr=0.1)
        refl_a = LM.mat("en_refl_amber", (0.9, 0.45, 0.02), 0.2, emit=(1, 0.5, 0.03), estr=0.2)
        for k, m_ in enumerate((refl_r, refl_w, refl_r, refl_w)):
            for sx in (-1, 1):
                plate(f"{name}_strip{k}_{sx}", m_, ((sx * hw * 0.62, y0, 0.50 + k * 0.1), (0, -1, 0)), 0.32, 0.08)
        for sx in (-1, 1):
            plate(f"{name}_sidemark_{sx}", refl_a, ((sx * hw, 0.95, 0.55), (sx, 0, 0)), 0.09, 0.05)
        # ---- flash: emitter in the flash frame plus a small area light
        self.win, self.light = _flash_parts(c, g, tuple(fpt + fn * 0.004), name, size=(0.5, 0.09),
                                            light_energy=900.0)
        self.win.rotation_euler = (math.atan2(fn.z, fn.y), 0, 0)
        self.light.rotation_euler = (math.radians(90) + math.atan2(fn.z, fn.y), 0, 0)

    def footprint(self):
        """World-space dimensions measured from the body mesh (for tests): length along road, width, height."""
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        objs = [self.body] + [o for o in self.root.children_recursive if o.name.startswith(self.root.name + "_")
                              and o.type == "MESH"]
        inv = self.root.matrix_world.inverted()
        xs, ys, zs = [], [], []
        for o in objs:
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            mw = inv @ o.matrix_world
            for v in me.vertices:
                p = mw @ v.co
                xs.append(p.x)
                ys.append(p.y)
                zs.append(p.z)
            ev.to_mesh_clear()
        return dict(body=self._dims(self.body, dg, inv), all=(max(ys) - min(ys), max(xs) - min(xs), max(zs) - min(zs)))

    @staticmethod
    def _dims(o, dg, inv):
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = inv @ o.matrix_world
        ps = [mw @ v.co for v in me.vertices]
        ev.to_mesh_clear()
        return (max(p.y for p in ps) - min(p.y for p in ps), max(p.x for p in ps) - min(p.x for p in ps),
                max(p.z for p in ps))


class CameraColumn(_Device):
    """Generic fixed speed camera column: grey tower with two dark windows towards traffic, cap, concrete plinth."""

    def __init__(self, road, c, s, x=19.0, h=-0.12, height=COLUMN_H, name="en_column", facing="oncoming"):
        super().__init__(road, c, s, x, name, facing, h)
        grey = LM.mat("en_column_grey", (0.42, 0.44, 0.45), 0.4, metal=0.5)
        glass = LM.mat("en_trailer_window", (0.005, 0.006, 0.008), 0.03, spec=1.0, coat=1.0)
        g = self.root
        b = LM.MB()
        seg = 6
        r = 0.32
        for z0, z1, rr in ((0.25, height, r), (height, height + 0.14, r + 0.06)):
            ring0 = [(rr * math.cos(2 * math.pi * k / seg), rr * math.sin(2 * math.pi * k / seg)) for k in range(seg)]
            base = len(b.V)
            for z in (z0, z1):
                for px, py in ring0:
                    b.V.append((px, py, z))
            for k in range(seg):
                k2 = (k + 1) % seg
                b.F.append((base + k, base + k2, base + seg + k2, base + seg + k))
                b.S.append(False)
            b.F.append(tuple(base + seg + k for k in range(seg)))
            b.S.append(False)
        self.body = b.obj(name + "_body", grey, c, g)
        p = LM.MB()
        p.box((0, 0, 0.12), (0.95, 0.95, 0.24))
        p.obj(name + "_plinth", bpy.data.materials.get("concrete") or grey, c, g)
        w = LM.MB()
        fy = r * math.cos(math.pi / 6) + 0.004        # flat face of the hexagon towards traffic (+Y)
        for z0, z1 in ((height - 1.05, height - 0.55), (height - 0.45, height - 0.2)):
            w.poly([(-0.12, fy, z1), (0.12, fy, z1), (0.12, fy, z0), (-0.12, fy, z0)])
        w.obj(name + "_windows", glass, c, g)
        self.win, self.light = _flash_parts(c, g, (0.0, fy + 0.002, height - 1.4), name, size=(0.22, 0.18))
        self.height = height


class LaserCheck(_Device):
    """Police laser check: a Polizei estate parked on the verge or a hard-standing, a tripod with a handheld laser gun
    aimed at approaching traffic, a small folding table. The flash is the laser's sighting lamp (subtle)."""

    def __init__(self, road, c, lib, s, x=19.0, h=-0.14, name="en_laser", facing="oncoming", car_coll=None):
        super().__init__(road, c, s, x, name, facing, h)
        g = self.root
        pad = LM.MB()                                  # gravel hard-standing beside the verge (local -x = outwards)
        pad.box((-1.9, 3.0, -0.45), (6.2, 11.0, 0.9))
        gravel = bpy.data.materials.get("gravel") or LM.mat("en_gravel", (0.2, 0.19, 0.16), 0.95)
        pad.obj(name + "_pad", gravel, c, g)
        if car_coll is None and V is not None:
            car_coll = bpy.data.collections.get("en_polizei") or V.car("estate", (0.8, 0.8, 0.8), "en_polizei",
                                                                         "JX PO 110", police=True, c=lib)
        self.car = None
        if car_coll is not None:
            e = LM.instance(car_coll, c, name + "_car")
            e.parent = g
            e.location = (-2.6, 3.4, 0.0)
            e.rotation_euler = (0, 0, math.radians(-6))
            self.car = e
        steel = LM.mat("en_tripod", (0.08, 0.08, 0.085), 0.45, metal=0.6)
        body = LM.mat("en_laser_body", (0.12, 0.13, 0.14), 0.4, metal=0.3)
        glass = LM.mat("en_trailer_window", (0.005, 0.006, 0.008), 0.03, spec=1.0, coat=1.0)
        t = LM.MB()
        top = Vector((0.0, 0.0, 1.42))
        for k in range(3):
            a = 2 * math.pi * k / 3 + 0.3
            t.tube((0.42 * math.cos(a), 0.42 * math.sin(a), 0.0), tuple(top), 0.014, 6)
        t.tube((0, 0, 1.25), tuple(top + Vector((0, 0, 0.08))), 0.022, 8)
        t.obj(name + "_tripod", steel, c, g)
        d = LM.MB()
        d.box((0, 0.05, 1.6), (0.12, 0.3, 0.16))           # gun body, lens towards +y (traffic after the yaw)
        d.box((0, -0.04, 1.47), (0.05, 0.08, 0.16))        # grip
        d.box((0, -0.05, 1.71), (0.06, 0.12, 0.05))        # sight
        d.obj(name + "_device", body, c, g)
        lens = LM.MB()
        lens.poly([(-0.035, 0.201, 1.635), (0.035, 0.201, 1.635), (0.035, 0.201, 1.565), (-0.035, 0.201, 1.565)])
        lens.obj(name + "_lens", glass, c, g)
        tb = LM.MB()
        tb.box((-0.9, 0.3, 0.72), (0.6, 0.45, 0.03))
        for sx in (-1, 1):
            for sy in (-1, 1):
                tb.tube((-0.9 + sx * 0.26, 0.3 + sy * 0.18, 0.0), (-0.9 + sx * 0.26, 0.3 + sy * 0.18, 0.71), 0.012, 6)
        tb.obj(name + "_table", steel, c, g)
        self.win, self.light = _flash_parts(c, g, (0.045, 0.203, 1.665), name, size=(0.03, 0.03), strength=25.0,
                                            light_energy=30.0)
