"""Shared stage for the Drive Like a Local episodes: German motorway world, sky, haze, render settings, fleet."""
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector

import flora
import vehicles as V
import world as W


def build_world(assets, s0=60.0, s1=2400.0, gantry_s=430.0, bridge_s=610.0, phone_s=238.0, signs282=None):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    W.setup(assets, None)
    lib = W.coll("lib")
    env = W.coll("env")
    traffic = W.coll("traffic")
    road = W.Road(length=2400.0)
    M = W.Mats()
    W.build_motorway(road, M, env, s0, s1)
    for side in (1, -1):
        road.strip("verge", side * 18.3, side * 27.0, s0, s1, M.grass, env, step=4.0, dz0=-0.12, dz1=-0.79)
    W.terrain(road, M, env)
    LP = W.leitpfosten(M, lib)
    RD = W.rail_delineator(M, lib)
    s = s0 + 10
    while s < s1:
        road.place(LP, s, 17.3, -0.053, c=env, name="lp")
        road.place(LP, s + 25, -17.3, -0.053, yaw=math.pi, c=env, name="lp")
        road.place(RD, s, 0.0, c=env, name="rd")
        s += 50.0
    if signs282:
        S282 = W.sign_282(M, lib)
        for ss in signs282:
            road.place(S282, ss, 18.4, -0.06, c=env, name="z282")
            road.place(S282, ss, 1.35, 0.0, c=env, name="z282m")
    if gantry_s:
        G = W.gantry(M, lib, 1.0, 18.6, [
            dict(x0=2.9, x1=10.1, z0=5.4, z1=8.4,
                 lines=[("Karlsruhe", 0.5, 3.3, 7.3), ("Basel", 0.5, 3.3, 6.72)],
                 shields=[("A 5", 3.85, 7.95, False), ("E 35", 5.3, 7.95, True)], arrows=[4.625, 8.375]),
            dict(x0=10.4, x1=13.9, z0=5.4, z1=8.4,
                 lines=[("Darmstadt", 0.44, 10.7, 7.3), ("Frankfurt", 0.44, 10.7, 6.75)],
                 shields=[("A 67", 11.45, 7.95, False)], arrows=[12.125]),
        ])
        road.place(G, gantry_s, 0.0, c=env, name="gantry")
    if phone_s:
        NR = W.emergency_phone(M, lib)
        road.place(NR, phone_s, 19.4, -0.3, c=env, name="notruf")
    excl = []
    if bridge_s:
        W.overpass(road, M, env, bridge_s)
        for sgn in (-1, 1):
            for t in range(0, 150, 20):
                q = road.point(bridge_s, sgn * (33 + t))
                excl.append((q.x, q.y, 22))
    HG, CH = W.house_library(lib, M)
    for vs, vx, vr, seed in [(520, -420, 150, 2), (980, 560, 130, 5), (1500, -650, 160, 8)]:
        W.village(road, HG, CH, env, vs, vx, n=int(vr / 4), radius=vr, seed=seed)
        q = road.point(vs, vx)
        excl.append((q.x, q.y, vr + 25))
    groups = flora.library(lib)
    mid = (road.X[road.n // 2], road.Y[road.n // 2])
    flora.vegetation(road, groups, env, max(0.0, s0 - 40), s1, half=1900.0, center=mid, spacing=7.0, exclude=excl)
    TB, _rot = W.wind_turbine(M, lib)
    for k, (ts, tx) in enumerate(((620, 520), (760, 690), (900, 470), (1150, -620), (1350, -820), (1500, 760),
                                  (1700, 980), (520, -900))):
        p = road.point(ts, tx)
        W.instance(TB, (p.x, p.y, W.ground_z(road, p.x, p.y) - 1.0), rz=math.radians(200 + k * 3), c=env)
    return dict(road=road, M=M, lib=lib, env=env, traffic=traffic)


def fleet(lib):
    cars = {
        "estate_blue": V.car("estate", (0.02, 0.06, 0.2), "estate_blue", "F SF 101", c=lib),
        "hatch_silver": V.car("hatch", (0.55, 0.57, 0.6), "hatch_silver", "MZ AK 77", c=lib),
        "suv_white": V.car("suv", (0.85, 0.86, 0.87), "suv_white", "WI TR 312", metal=0.1, c=lib),
        "saloon_black": V.car("saloon", (0.015, 0.016, 0.018), "saloon_black", "DA KE 9", c=lib),
        "hatch_red": V.car("hatch", (0.5, 0.03, 0.02), "hatch_red", "OF LE 45", metal=0.2, c=lib),
        "estate_grey": V.car("estate", (0.2, 0.21, 0.22), "estate_grey", "GG MO 18", c=lib),
        "saloon_white": V.car("saloon", (0.82, 0.83, 0.84), "saloon_white", "HD UL 66", metal=0.1, c=lib),
        "hatch_blue": V.car("hatch", (0.08, 0.22, 0.45), "hatch_blue", "KA RS 41", c=lib),
        "suv_dark": V.car("suv", (0.06, 0.08, 0.07), "suv_dark", "MA XY 5", c=lib),
        "estate_green": V.car("estate", (0.05, 0.16, 0.1), "estate_green", "WÜ PT 72", c=lib),
    }
    vans = {"van_white": V.car("van", (0.86, 0.87, 0.88), "van_white", "HU BB 330", metal=0.0, c=lib)}
    trucks = {
        "t_nord": V.truck("t_nord", (0.85, 0.86, 0.87), (0.86, 0.87, 0.88), "NORDFRACHT", c=lib),
        "t_blue": V.truck("t_blue", (0.04, 0.12, 0.35), (0.04, 0.12, 0.35), "", c=lib),
        "t_alpen": V.truck("t_alpen", (0.55, 0.03, 0.02), (0.8, 0.81, 0.8), "ALPENKURIER", (0.55, 0.03, 0.02),
                           c=lib, reefer=True),
        "t_white": V.truck("t_white", (0.9, 0.9, 0.9), (0.62, 0.64, 0.66), "", c=lib),
    }
    return cars, vans, trucks


def sky(road, light_dir, assets, sun_elev_deg=30.0, sun_energy=4.2):
    sc = bpy.context.scene
    img = bpy.data.images.load(os.path.join(assets, "hdri", "kloofendal_48d_partly_cloudy_puresky.hdr"))
    px = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(img.size[1], img.size[0], 4)
    lum = px[..., 0] * 0.2 + px[..., 1] * 0.7 + px[..., 2] * 0.1
    vi, ui = np.unravel_index(np.argmax(lum), lum.shape)
    u = (ui + 0.5) / img.size[0]
    phi_img = (u - 0.5) * 2 * math.pi
    to_sun = -light_dir
    rz = phi_img - math.atan2(to_sun.y, -to_sun.x)
    w = bpy.data.worlds.new("sky")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    env_n = nt.nodes.new("ShaderNodeTexEnvironment")
    env_n.image = img
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, rz)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], env_n.inputs["Vector"])
    nt.links.new(env_n.outputs["Color"], bg.inputs["Color"])
    amb = nt.nodes.new("ShaderNodeBackground")
    sepz = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sepz.inputs["Vector"])
    zmap = nt.nodes.new("ShaderNodeMath")
    zmap.operation = "MULTIPLY_ADD"
    zmap.inputs[1].default_value = 0.5
    zmap.inputs[2].default_value = 0.5
    nt.links.new(sepz.outputs["Z"], zmap.inputs[0])
    gramp = nt.nodes.new("ShaderNodeValToRGB")
    gramp.color_ramp.elements[0].position = 0.45
    gramp.color_ramp.elements[0].color = (0.16, 0.15, 0.13, 1)
    gramp.color_ramp.elements[1].position = 1.0
    gramp.color_ramp.elements[1].color = (0.32, 0.46, 0.78, 1)
    gramp.color_ramp.elements.new(0.52).color = (0.78, 0.8, 0.85, 1)
    nt.links.new(zmap.outputs[0], gramp.inputs["Fac"])
    nt.links.new(gramp.outputs["Color"], amb.inputs["Color"])
    amb.inputs["Strength"].default_value = 0.9
    lp_ = nt.nodes.new("ShaderNodeLightPath")
    mixw = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp_.outputs["Is Camera Ray"], mixw.inputs[0])
    nt.links.new(amb.outputs[0], mixw.inputs[1])
    nt.links.new(bg.outputs[0], mixw.inputs[2])
    nt.links.new(mixw.outputs[0], nt.nodes["World Output"].inputs["Surface"])
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = sun_energy
    sun.angle = math.radians(1.5)
    sun.color = (1.0, 0.9, 0.76)
    so = bpy.data.objects.new("sun", sun)
    sc.collection.objects.link(so)
    e = math.radians(sun_elev_deg)
    hz = Vector((to_sun.x, to_sun.y, 0)).normalized()
    d = Vector((hz.x * math.cos(e), hz.y * math.cos(e), math.sin(e)))
    so.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()


def hazify_all(color=(0.62, 0.72, 0.86), dist=2600.0, skip=()):
    for m in list(bpy.data.materials):
        if m.name in skip or not m.use_nodes:
            continue
        nt_ = m.node_tree
        out = next((n for n in nt_.nodes if n.type == "OUTPUT_MATERIAL"), None)
        if not out or not out.inputs["Surface"].links:
            continue
        src = out.inputs["Surface"].links[0].from_socket
        cd = nt_.nodes.new("ShaderNodeCameraData")
        dv = nt_.nodes.new("ShaderNodeMath")
        dv.operation = "DIVIDE"
        dv.inputs[1].default_value = -dist
        nt_.links.new(cd.outputs["View Distance"], dv.inputs[0])
        ex = nt_.nodes.new("ShaderNodeMath")
        ex.operation = "EXPONENT"
        nt_.links.new(dv.outputs[0], ex.inputs[0])
        inv = nt_.nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        nt_.links.new(ex.outputs[0], inv.inputs[1])
        em = nt_.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*color, 1)
        mx = nt_.nodes.new("ShaderNodeMixShader")
        nt_.links.new(inv.outputs[0], mx.inputs[0])
        nt_.links.new(src, mx.inputs[1])
        nt_.links.new(em.outputs[0], mx.inputs[2])
        nt_.links.new(mx.outputs[0], out.inputs["Surface"])


def render_setup(samples, res_x, res_y, motion_blur=True):
    sc = bpy.context.scene
    bpy.context.view_layer.layer_collection.children["lib"].exclude = True
    r = sc.render
    r.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.max_bounces = 6
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 2
    sc.cycles.transmission_bounces = 2
    sc.cycles.transparent_max_bounces = 4
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.blur_glossy = 1.0
    r.resolution_x, r.resolution_y = res_x, res_y
    r.resolution_percentage = 100
    r.film_transparent = False
    r.use_motion_blur = motion_blur
    r.motion_blur_shutter = 0.5
    r.use_persistent_data = True
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Punchy"
    except TypeError:
        pass
    r.image_settings.file_format = "PNG"


def camera(name, lens):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    cam.sensor_fit = "VERTICAL"
    cam.sensor_height = 36.0
    cam.clip_start = 0.1
    cam.clip_end = 6000
    co = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(co)
    return co


def look_rot(pos, tgt, up=None):
    d = (tgt - pos).normalized()
    if up is None:
        return d.to_track_quat("-Z", "Y").to_euler()
    z = -d
    x = up.cross(z).normalized()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed()
    return m.to_euler()


def fcurves(obj_or_id):
    ad = obj_or_id.animation_data
    act = ad.action
    try:
        return list(act.fcurves)
    except AttributeError:
        return list(act.layers[0].strips[0].channelbag(ad.action_slot).fcurves)


def bake_motion(obj, frames, locs, rots, interp=1):
    """Write per-frame location and rotation keys fast (foreach_set). interp: 0 constant, 1 linear, 2 bezier."""
    obj.location = locs[0]
    obj.rotation_euler = rots[0]
    obj.keyframe_insert("location", frame=frames[0])
    obj.keyframe_insert("rotation_euler", frame=frames[0])
    n = len(frames)
    for fc in fcurves(obj):
        i = fc.array_index
        src = locs if fc.data_path == "location" else rots
        kp = fc.keyframe_points
        kp.add(n - len(kp))
        co = []
        for f, v in zip(frames, src):
            co += [f, v[i]]
        kp.foreach_set("co", co)
        kp.foreach_set("interpolation", [interp] * n)
        fc.update()
