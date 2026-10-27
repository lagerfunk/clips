"""Weather and time of day for both Drive Like a Local stages (stage.py Autobahn, townstage.py junction).

    import weather
    weather.apply("rain")                     # day, dusk, night, rain, fog, snow, ice; combine with "+": "rain+night"
    weather.apply("fog", strength=1.2)        # fog: visibility 50 m / strength (the 50 m rule)
    weather.spray(truck_obj, frames=range(1, 751))   # wheel spray keyed per frame from the vehicle's own speed
    weather.apply("day")                      # puts every value back exactly as the stage built it

Call apply() after the stage is built and lit (TS.light / stage.sky) and after stage.hazify_all, right before the
render setup; call it again to switch (every call first restores the original scene). Nothing in the frozen kit files
is edited: the module works on the world, the sun and the materials by name. It never changes an existing node value;
it only adds nodes named wx_* and links them over existing inputs, so restoring is: delete wx_* and re-link.

What each preset does
- day   the stage as built (sunny October afternoon).
- dusk  low warm sun (3.5 deg), procedural dusk sky, street lamps and low beams on, some windows lit.
- night moon light, dark sky with stars and moon, street lamps (town) with real spot lights, low beams on moving
        vehicles (spot lights + glowing lenses), lit windows, retroreflective signs, Leitpfosten, plates and markings
        catching the light, bloom.
- rain  overcast, wet asphalt (darker, glossy, puddles in the wheel ruts and along the edge line, rippling), wet
        markings, wet grass, falling rain streaks around the camera, wheel spray behind moving vehicles, low beams.
- fog   distance haze tuned to the visibility: 50 m at strength 1 (5 % contrast left at 50 m, so the next
        Leitpfosten is just visible), fog glow on lights, damp roads. No volumetrics (cost).
- snow  snow on fields, roofs, verges, trees and the road edges, slush between the wheel tracks, icy sheen in the
        tracks, falling snow, 300 m visibility, low beams, snow on parked cars.
- ice   clear cold morning, hoarfrost on the ground, black-ice glaze on the road (mirror patches over a frosty grey
        road), low sun for a readable sheen.

Vehicles: an instance empty whose collection holds "headlight" objects is a vehicle. It counts as moving (lights on,
spray, no snow on the roof) when it sits in the "traffic" collection or has an action, unless its name starts with
"parked"; set obj["wx_moving"] = 1 or 0 to decide yourself. If kit/motion.py offers lights(obj, on), it is called too.
"""
import json
import math

import bpy
from mathutils import Vector

PRESETS = ("day", "dusk", "night", "rain", "fog", "snow", "ice")
# render budget: falling rain streaks, snow flakes, spray volumes (nearest vehicles to the camera)
BUDGET = {"rain": 30000, "snow": 20000, "spray_boxes": 2}
# Ray marching for the spray mist. spray() sets it for every box (also when an episode calls spray() itself with
# auto_spray=False); Cycles 5.0's unbiased default is 40-50x slower on these procedural volumes (reports/perf2.md).
SPRAY_VOLUME = {"volume_biased": True, "volume_step_rate": 4.0, "volume_max_steps": 24}
RAIN_COUNT = 18000
SNOW_COUNT = 19000
CONTRAST = 0.05            # meteorological visibility: distance where 5 % contrast is left, so haze D = V / 3.0

# lane layout per stage for wheel ruts and road edges (lateral metres): Autobahn from the motorway centre (UV u),
# town from the street centre line (world x or y)
ROAD_LAYOUT = {"autobahn": dict(mode=0.0, P=1.875, off=3.6875, lo=2.75, hi=14.0, edge_in=2.85, edge_out=13.95),
               "town": dict(mode=1.0, P=1.5, off=0.75, lo=0.0, hi=2.8, edge_in=-9.0, edge_out=2.6)}
ROAD_MATS = {"asphalt": 0.55, "asphalt_shoulder": 0.55, "bridge_asphalt": 0.55, "town_asphalt": 0.55, "paint": 0.2,
             "manhole_iron": 0.3}     # covers and gullies get wet, icy and slushy with the road (else: a matte black disc)
# generic surfaces: (porosity = how much darker when wet, snow cover 0..1, kind) kind: 0 plain, 1 leaf, 2 vehicle paint
SURF = {
    "grass": (0.7, 1.0, 0), "landscape": (0.6, 1.0, 0), "gravel": (0.6, 0.95, 0), "lawn": (0.7, 1.0, 0),
    "garden_bed": (0.8, 1.0, 0), "concrete": (0.55, 0.75, 0), "kerb_granite": (0.45, 0.8, 0),
    "footway_pavers": (0.55, 0.8, 0), "gutter_cobbles": (0.55, 0.95, 0), "drive_pavers": (0.55, 0.75, 0),
    "hedge": (0.35, 0.9, 1), "fence_wood": (0.6, 0.7, 0), "roof_red": (0.35, 1.0, 0),
    "roof_brown": (0.35, 1.0, 0), "roof_anthracite": (0.35, 1.0, 0), "solar_panel": (0.0, 0.8, 0),
    "plinth": (0.45, 0.6, 0), "sill_stone": (0.45, 0.8, 0), "bark": (0.5, 0.6, 0), "leaf_a": (0.35, 0.85, 1),
    "leaf_b": (0.35, 0.85, 1), "leaf_c": (0.35, 0.85, 1), "leaf_autumn_a": (0.35, 0.85, 1),
    "leaf_autumn_b": (0.35, 0.85, 1), "needle": (0.3, 0.9, 0), "post_white": (0.05, 0.9, 0), "steel": (0.0, 0.5, 0),
    "steel_dark": (0.0, 0.5, 0), "turbine_white": (0.05, 0.6, 0), "wall_white": (0.3, 0.5, 0),
    "wall_cream": (0.3, 0.5, 0), "wall_grey": (0.3, 0.5, 0), "spire": (0.1, 0.9, 0), "zinc_gutter": (0.0, 0.8, 0),
    "anodised": (0.0, 0.6, 0), "pole_grey": (0.05, 0.7, 0), "bin_grey": (0.05, 0.9, 0), "bin_blue": (0.05, 0.9, 0),
    "bin_brown": (0.05, 0.9, 0), "bin_yellow": (0.05, 0.9, 0), "pvc_white": (0.05, 0.7, 0),
    "garage_door": (0.05, 0.4, 0), "roller_shutter": (0.05, 0.5, 0), "sign_back": (0.0, 0.5, 0),
    "sign_post_mat": (0.0, 0.6, 0), "signal_housing": (0.05, 0.8, 0), "truck_chassis": (0.1, 0.0, 0),
}
SURF_PREFIX = (("plaster", (0.3, 0.5, 0)), ("paint_", (0.0, 0.85, 2)), ("t_", (0.05, 0.85, 2)))
RETRO = {"reflector": 3.0, "reflector_amber": 3.0, "sign_white": 1.4, "sign_blue": 1.4, "sign_red": 1.4,
         "sign_green": 1.4, "sign_yellow": 1.4, "tape_red": 2.5, "tape_white": 2.5, "car_plate": 0.9, "paint": 0.45}
SKIP_PREFIX = ("wx_", "badge", "rib", "icon_", "arrow", "corridor", "indicator", "blue_flash", "police_bar", "sg_",
               "flash", "callout", "timer", "end_", "overlay", "ink", "car_glass", "window_glass", "house_window",
               "lamp_glass", "car_head", "car_tail", "marker_amber", "car_rim", "car_chrome", "car_tyre", "car_arch",
               "car_plastic", "car_euband", "car_plate", "reflector", "sign_", "tape_")

# ------------------------------------------------------------------ preset tables
# sky colours: (ground, horizon, mid, zenith)
TOD = {
    "dusk": dict(sun_elev=3.5, sun_az=0.0, sun_col=(1.0, 0.5, 0.26), sun_energy=2.6, sun_angle=2.5, amb=0.9,
                 sky=((0.05, 0.04, 0.045), (1.0, 0.5, 0.24), (0.36, 0.28, 0.4), (0.035, 0.07, 0.2)), clouds=0.15,
                 glow=1.6, glow_col=(1.0, 0.42, 0.14), stars=0.0, moon=0.0, haze=(0.4, 0.29, 0.27), V=3000.0,
                 lamps=0.85, windows=0.45, lights=1.0, head=16.0, tail=2.8, retro=0.6, exposure=0.5, bloom=0.45,
                 beam_w=1800.0, lamp_w=1400.0, wet=0.2),
    "night": dict(sun_elev=34.0, sun_az=70.0, sun_col=(0.55, 0.66, 1.0), sun_energy=0.09, sun_angle=0.6, amb=1.6,
                  sky=((0.003, 0.003, 0.004), (0.036, 0.03, 0.034), (0.008, 0.011, 0.024), (0.0015, 0.003, 0.009)),
                  clouds=0.1, glow=0.0, glow_col=(1, 1, 1), stars=1.0, moon=1.0, haze=(0.007, 0.009, 0.016),
                  V=4500.0, lamps=1.0, windows=0.8, lights=1.0, head=30.0, tail=3.8, retro=1.0, exposure=1.3,
                  bloom=0.7, beam_w=2600.0, lamp_w=3600.0, wet=0.6),
}
WX = {
    "rain": dict(over=True, sun_energy=0.25, sun_angle=30.0, sun_col=(0.85, 0.9, 1.0), amb=1.25,
                 sky=((0.08, 0.08, 0.08), (0.37, 0.39, 0.42), (0.27, 0.29, 0.32), (0.14, 0.155, 0.18)), clouds=0.6,
                 haze=(0.34, 0.36, 0.39), V=1000.0, wet=1.0, rain=1.0, lights=1.0, head=9.0, tail=2.4, retro=0.35,
                 exposure=0.25, bloom=0.3),
    "fog": dict(over=True, sun_energy=0.05, sun_angle=40.0, sun_col=(0.9, 0.92, 0.95), amb=1.2,
                sky=((0.6, 0.62, 0.645),) * 4, clouds=0.04, haze=(0.6, 0.62, 0.645), V=50.0, wet=0.35, lights=1.0,
                head=8.0, tail=2.6, retro=0.45, exposure=0.0, bloom=0.75),     # Fog Glow glare: +75 % time
    "snow": dict(over=True, sun_energy=0.35, sun_angle=25.0, sun_col=(0.92, 0.95, 1.0), amb=1.15,
                 sky=((0.5, 0.52, 0.56), (0.67, 0.7, 0.75), (0.6, 0.63, 0.68), (0.5, 0.53, 0.58)), clouds=0.3,
                 haze=(0.6, 0.63, 0.68), V=500.0, snow=1.0, wet=0.35, snowfall=1.0, leafless=1.0, lights=1.0,
                 head=10.0, tail=2.6, retro=0.35, exposure=-0.35, bloom=0.3),
    "ice": dict(over=False, sun_elev=9.0, sun_az=0.0, sun_energy=3.6, sun_col=(1.0, 0.86, 0.7), sun_angle=1.5,
                amb=0.75, sky=((0.25, 0.24, 0.24), (0.86, 0.85, 0.84), (0.55, 0.66, 0.82), (0.16, 0.3, 0.6)),
                clouds=0.1, glow=0.7, glow_col=(1.0, 0.75, 0.45), haze=(0.72, 0.77, 0.85), V=3500.0, ice=1.0,
                frost=1.0, leafless=0.6, lights=1.0, head=6.0, tail=2.0, retro=0.2, exposure=0.0, bloom=0.25),
}
DEFAULTS = dict(over=False, sun_glossy=True, sun_elev=None, sun_az=0.0, sun_azimuth=None, sun_col=None, sun_energy=None, sun_angle=None, amb=1.0,
                clouds=0.0, glow=0.0, glow_col=(1, 1, 1), stars=0.0, moon=0.0, V=None, wet=0.0, rain=0.0, snow=0.0,
                snowfall=0.0, ice=0.0, frost=0.0, leafless=0.0, lamps=0.0, windows=0.0, lights=0.0, head=1.5,
                tail=1.0, retro=0.0, exposure=0.0, bloom=0.0, glare="Bloom", beam_w=0.0, lamp_w=0.0)

_S = None                  # restore record of the current preset (mirrored in scene["wx_state"])


def params(preset, strength=1.0, **kw):
    """The flat parameter dict for a preset name such as "rain", "night" or "rain+night"."""
    parts = [p.strip().lower() for p in preset.split("+") if p.strip()]
    for p in parts:
        if p not in PRESETS:
            raise ValueError(f"unknown weather preset {p!r}; use one of {PRESETS}")
    tod = next((p for p in parts if p in TOD), None)
    wxs = [p for p in parts if p in WX]
    wx = wxs[0] if wxs else None
    P = dict(DEFAULTS)
    if wx:
        P.update(WX[wx])
        for extra in wxs[1:]:              # "snow+ice": the first sets the sky, the others add their ground effects
            for k in ("wet", "rain", "snow", "snowfall", "ice", "frost", "leafless"):
                P[k] = max(P[k], WX[extra].get(k, 0.0) * (0.7 if k in ("ice", "frost") else 1.0))
            P["V"] = min(P["V"], WX[extra]["V"])
            if extra == "ice":                 # thin overcast with the low sun glowing through: the ice sheen reads
                P["glow"] = max(P["glow"], 0.45)
                P["glow_col"] = WX["ice"]["glow_col"]
                P["sun_elev"] = WX["ice"]["sun_elev"]
                P["sun_energy"] = max(P["sun_energy"], 1.1)
                P["sun_col"] = WX["ice"]["sun_col"]
                P["sun_angle"] = 2.5           # a real (small) sun: a glare streak along the tracks, not a disc
                P["sun_glossy"] = True
    if tod and not wx:
        P.update(TOD[tod])
    elif tod and wx:
        T = TOD[tod]
        for k in ("sun_elev", "sun_az", "sun_col", "sun_angle", "glow_col", "lamps", "windows", "head", "tail",
                  "exposure", "beam_w", "lamp_w"):
            P[k] = T[k]
        P["sun_energy"] = T["sun_energy"] * (0.35 if P["over"] else 1.0)
        P["amb"] = T["amb"]
        dark = 0.9 if tod == "dusk" else 0.035
        P["sky"] = tuple(tuple(c * dark for c in col) for col in P["sky"]) if tod == "night" else T["sky"]
        if tod == "night":
            P["haze"] = tuple(c * (0.05 if wx != "fog" else 0.06) for c in P["haze"])
        else:
            P["haze"] = tuple(0.5 * a + 0.5 * b for a, b in zip(P["haze"], T["haze"]))
        P["glow"] = T["glow"] * (0.3 if P["over"] else 1.0)
        P["stars"] = 0.0 if P["over"] else T["stars"]
        P["moon"] = 0.0 if P["over"] else T["moon"]
        P["lights"] = 1.0
        P["retro"] = max(P["retro"], T["retro"])
        P["bloom"] = max(P["bloom"], T["bloom"])
    s = max(0.0, float(strength))
    for k in ("wet", "rain", "snow", "snowfall", "ice", "frost"):
        P[k] = min(1.5, P[k] * s)
    if P["V"]:
        P["V"] = P["V"] / max(0.05, s) if wx else P["V"]
    if kw.get("visibility"):
        P["V"] = float(kw["visibility"])
    if P["over"] and wx != "ice" and "ice" not in wxs[1:]:
        P["sun_glossy"] = False            # overcast: no sun disc mirrored in wet or icy roads (it showed as a blob)
    for k in ("exposure", "sun_elev", "wet", "glow", "sun_azimuth", "bloom"):
        if kw.get(k) is not None:
            P[k] = kw[k]
    P["preset"] = "+".join(parts)
    P["tod"] = tod or "day"
    P["wx"] = wx
    P["strength"] = s
    P["night"] = 1.0 if tod == "night" else (0.5 if tod == "dusk" else 0.0)
    return P


def visibility(preset=None, strength=1.0):
    """Meteorological visibility in metres (None for the plain day stage)."""
    if preset is None:
        return _S["P"]["V"] if _S else None
    return params(preset, strength)["V"]


def haze_distance(V):
    """Exponential haze scale D for a visibility V: exp(-V / D) = 5 % contrast."""
    return V / -math.log(CONTRAST)


# ------------------------------------------------------------------ node building helpers
class _B:
    """Small node builder. Sockets or plain values are accepted wherever an input is expected."""

    def __init__(self, nt, prefix=""):
        self.nt = nt
        self.prefix = prefix

    def new(self, t, name=None, **props):
        n = self.nt.nodes.new(t)
        if name:
            n.name = n.label = self.prefix + name
        elif self.prefix:
            n.name = self.prefix + n.name
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def put(self, sock, v):
        if v is None:
            return
        if isinstance(v, bpy.types.NodeSocket):
            self.nt.links.new(v, sock)
            return
        dv = sock.default_value
        try:
            n = len(dv)
        except TypeError:
            n = 0
        if n and not isinstance(v, (tuple, list)):
            v = (v,) * n
        elif n and len(v) != n:
            v = tuple(v)[:n] + (1.0,) * (n - len(v))
        sock.default_value = v

    def m(self, op, a, b=None, c=None, clamp=False):
        n = self.new("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.put(n.inputs[0], a)
        if b is not None:
            self.put(n.inputs[1], b)
        if c is not None:
            self.put(n.inputs[2], c)
        return n.outputs[0]

    def v(self, op, a, b=None, c=None, scale=None):
        n = self.new("ShaderNodeVectorMath", operation=op)
        self.put(n.inputs[0], a)
        if b is not None:
            self.put(n.inputs[1], b)
        if c is not None:
            self.put(n.inputs[2], c)
        if scale is not None:
            self.put(n.inputs[3], scale)
        return n.outputs["Value"] if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else n.outputs["Vector"]

    def mix(self, kind, f, a, b, blend="MIX"):
        n = self.new("ShaderNodeMix", data_type=kind)
        if kind == "RGBA":
            n.blend_type = blend
        sfx = {"FLOAT": "Float", "VECTOR": "Vector", "RGBA": "Color"}[kind]

        def by_id(socks, ident):
            return next(s for s in socks if s.identifier == ident)
        self.put(by_id(n.inputs, "Factor_Float"), f)
        self.put(by_id(n.inputs, "A_" + sfx), a)
        self.put(by_id(n.inputs, "B_" + sfx), b)
        return by_id(n.outputs, "Result_" + sfx)

    def mixf(self, f, a, b):
        return self.mix("FLOAT", f, a, b)

    def mixc(self, f, a, b, blend="MIX"):
        return self.mix("RGBA", f, a, b, blend)

    def mixv(self, f, a, b):
        return self.mix("VECTOR", f, a, b)

    def smooth(self, x, e0, e1):
        n = self.new("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP", clamp=True)
        self.put(n.inputs["Value"], x)
        self.put(n.inputs["From Min"], e0)
        self.put(n.inputs["From Max"], e1)
        return n.outputs["Result"]

    def remap(self, x, a0, a1, b0, b1):
        n = self.new("ShaderNodeMapRange", clamp=True)
        self.put(n.inputs["Value"], x)
        self.put(n.inputs["From Min"], a0)
        self.put(n.inputs["From Max"], a1)
        self.put(n.inputs["To Min"], b0)
        self.put(n.inputs["To Max"], b1)
        return n.outputs["Result"]

    def noise(self, vec, scale, detail=2.0, w=None, rough=0.5, out="Fac"):
        n = self.new("ShaderNodeTexNoise")
        if w is not None:
            n.noise_dimensions = "4D"
            self.put(n.inputs["W"], w)
        self.put(n.inputs["Vector"], vec)
        self.put(n.inputs["Scale"], scale)
        self.put(n.inputs["Detail"], detail)
        self.put(n.inputs["Roughness"], rough)
        return n.outputs[out]

    def xyz(self, x, y, z):
        n = self.new("ShaderNodeCombineXYZ")
        self.put(n.inputs[0], x)
        self.put(n.inputs[1], y)
        self.put(n.inputs[2], z)
        return n.outputs[0]

    def sep(self, vec):
        n = self.new("ShaderNodeSeparateXYZ")
        self.put(n.inputs[0], vec)
        return n.outputs

    def rgb(self, col):
        n = self.new("ShaderNodeRGB")
        n.outputs[0].default_value = (*col[:3], 1.0)
        return n.outputs[0]

    def val(self, x):
        n = self.new("ShaderNodeValue")
        n.outputs[0].default_value = x
        return n.outputs[0]

    def group(self, ng, name=None):
        n = self.new("ShaderNodeGroup" if ng.bl_idname == "ShaderNodeTree" else "GeometryNodeGroup", name=name)
        n.node_tree = ng
        return n


def _id(socks, ident):
    """Socket by identifier (several sockets of a node can share a name, e.g. Random Value Min / Min_001)."""
    return next(s for s in socks if s.identifier == ident)


def _iface(ng, spec):
    """spec: [(in_out, name, socket_type, default)]"""
    for io, name, st, d in spec:
        it = ng.interface.new_socket(name, in_out=io, socket_type=st)
        if d is not None and hasattr(it, "default_value"):
            it.default_value = d


def _fcurves(idb):
    ad = idb.animation_data
    act = ad.action
    try:
        return list(act.fcurves)
    except AttributeError:
        return list(act.layers[0].strips[0].channelbag(ad.action_slot).fcurves)


# ------------------------------------------------------------------ shared control group (global weather values)
CTL_FLOATS = ("Wet", "Rain", "Snow", "Ice", "Frost", "Leafless", "Retro", "Lamps", "Windows", "WinFrac", "Lights",
              "HeadGain", "TailGain", "HazeNegDist", "Time", "SeedOff", "WetRough", "RainAlpha", "SnowAlpha")


def _ctl_group():
    ng = bpy.data.node_groups.get("wx_ctl")
    if ng:
        return ng
    ng = bpy.data.node_groups.new("wx_ctl", "ShaderNodeTree")
    _iface(ng, [("OUTPUT", k, "NodeSocketFloat", None) for k in CTL_FLOATS] +
           [("OUTPUT", "HazeColor", "NodeSocketColor", None)])
    b = _B(ng)
    go = b.new("NodeGroupOutput")
    for k in CTL_FLOATS:
        n = b.new("ShaderNodeValue", name=k)
        n.outputs[0].default_value = 0.0
        ng.links.new(n.outputs[0], go.inputs[k])
    n = b.new("ShaderNodeRGB", name="HazeColor")
    n.outputs[0].default_value = (0.6, 0.7, 0.8, 1)
    ng.links.new(n.outputs[0], go.inputs["HazeColor"])
    ng.nodes["HazeNegDist"].outputs[0].default_value = -2600.0
    # Time in seconds, linear in the frame number (shader ripples, flicker-free)
    fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    t = ng.nodes["Time"].outputs[0]
    for f, v in ((1, 0.0), (1 + fps, 1.0)):
        t.default_value = v
        t.keyframe_insert("default_value", frame=f)
    for fc in _fcurves(ng):
        fc.extrapolation = "LINEAR"
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    return ng


def _ctl_set(**vals):
    ng = _ctl_group()
    for k, v in vals.items():
        if k == "HazeColor":
            ng.nodes[k].outputs[0].default_value = (*v[:3], 1.0)
        else:
            ng.nodes[k].outputs[0].default_value = float(v)


def ctl(name):
    """Current value of a global weather control (tests, episode scripts)."""
    ng = bpy.data.node_groups.get("wx_ctl")
    if not ng:
        return None
    o = ng.nodes[name].outputs[0].default_value
    return tuple(o) if name == "HazeColor" else float(o)


# ------------------------------------------------------------------ surface groups
def _road_group():
    ng = bpy.data.node_groups.get("wx_road")
    if ng:
        return ng
    ng = bpy.data.node_groups.new("wx_road", "ShaderNodeTree")
    _iface(ng, [("INPUT", "Base", "NodeSocketColor", (0.05, 0.05, 0.05, 1)), ("INPUT", "Rough", "NodeSocketFloat", 0.7),
                ("INPUT", "Normal", "NodeSocketVector", (0, 0, 0)), ("INPUT", "Mode", "NodeSocketFloat", 0.0),
                ("INPUT", "P", "NodeSocketFloat", 1.875), ("INPUT", "Off", "NodeSocketFloat", 3.6875),
                ("INPUT", "Lo", "NodeSocketFloat", 2.75), ("INPUT", "Hi", "NodeSocketFloat", 14.0),
                ("INPUT", "EdgeIn", "NodeSocketFloat", 2.85), ("INPUT", "EdgeOut", "NodeSocketFloat", 13.95),
                ("INPUT", "Darken", "NodeSocketFloat", 0.55),
                ("OUTPUT", "Base", "NodeSocketColor", None), ("OUTPUT", "Rough", "NodeSocketFloat", None),
                ("OUTPUT", "Normal", "NodeSocketVector", None)])
    b = _B(ng)
    gi = b.new("NodeGroupInput")
    go = b.new("NodeGroupOutput")
    C = b.group(_ctl_group()).outputs
    I = gi.outputs
    geo = b.new("ShaderNodeNewGeometry")
    tc = b.new("ShaderNodeTexCoord")
    pos = b.v("ADD", geo.outputs["Position"], b.xyz(C["SeedOff"], b.m("MULTIPLY", C["SeedOff"], 0.7), 0.0))
    # normal: the material's own (bump) normal, or the shading normal when the material had none
    has_n = b.m("GREATER_THAN", b.v("LENGTH", I["Normal"]), 0.5)
    nrm0 = b.mixv(has_n, geo.outputs["Normal"], I["Normal"])
    # lateral position: Autobahn = UV u (metres from the centre), town = distance from the nearer street centre line
    uv = b.sep(tc.outputs["UV"])
    wp = b.sep(geo.outputs["Position"])
    lat_town = b.m("MINIMUM", b.m("ABSOLUTE", wp[0]), b.m("ABSOLUTE", wp[1]))
    lat = b.mixf(I["Mode"], uv[0], lat_town)
    along = b.mixf(I["Mode"], uv[1], b.m("MAXIMUM", b.m("ABSOLUTE", wp[0]), b.m("ABSOLUTE", wp[1])))
    nA = b.noise(pos, 0.22, 3.0)
    nB = b.noise(pos, 2.6, 2.0)
    latj = b.m("ADD", lat, b.m("MULTIPLY", b.m("SUBTRACT", b.noise(pos, 0.9, 2.0), 0.5), 0.55))
    inlane = b.m("MULTIPLY", b.m("GREATER_THAN", lat, I["Lo"]), b.m("LESS_THAN", lat, I["Hi"]))
    ph = b.m("DIVIDE", b.m("MULTIPLY", b.m("SUBTRACT", lat, I["Off"]), 2 * math.pi), I["P"])
    track = b.m("MULTIPLY", b.m("POWER", b.m("MULTIPLY_ADD", b.m("COSINE", ph), 0.5, 0.5), 5.0), inlane)
    edge_l = b.m("SUBTRACT", 1.0, b.smooth(latj, b.m("SUBTRACT", I["EdgeIn"], 0.35), b.m("ADD", I["EdgeIn"], 0.15)))
    edge_r = b.smooth(latj, b.m("SUBTRACT", I["EdgeOut"], 0.2), b.m("ADD", I["EdgeOut"], 0.45))
    edge = b.m("MAXIMUM", edge_l, edge_r)
    # ---- wet: darker, glossy, puddles in the ruts and along the right edge, raindrop ripples in the puddles
    wet = C["Wet"]
    base = I["Base"]
    b1 = b.mixc(b.m("MULTIPLY", wet, I["Darken"]), base, (0, 0, 0, 1))
    wr = b.m("ADD", C["WetRough"], b.m("ADD", b.m("MULTIPLY", b.m("SUBTRACT", nA, 0.5), 0.34), b.m("MULTIPLY", nB, 0.07)))
    r1 = b.mixf(wet, I["Rough"], b.m("MAXIMUM", wr, 0.03))
    water = b.m("ADD", b.m("ADD", b.m("MULTIPLY", track, 0.42), b.m("MULTIPLY", edge_r, 0.45)),
                b.m("MULTIPLY", b.m("SUBTRACT", nA, 0.5), 1.7))
    puddle = b.m("MULTIPLY", b.smooth(water, 0.36, 0.5), b.smooth(wet, 0.7, 1.0))   # damp streets: no pools
    b2 = b.mixc(b.m("MULTIPLY", puddle, 0.45), b1, (0, 0, 0, 1))
    r2 = b.mixf(puddle, r1, 0.02)
    n1 = b.mixv(b.m("MAXIMUM", b.m("MULTIPLY", wet, 0.75), puddle), nrm0, geo.outputs["Normal"])
    rip = b.noise(b.v("SCALE", pos, scale=9.0), 1.0, 1.0, w=b.m("MULTIPLY", C["Time"], 2.2))
    bump = b.new("ShaderNodeBump")
    b.put(bump.inputs["Strength"], b.m("MULTIPLY", b.m("MULTIPLY", puddle, C["Rain"]), 0.12))
    b.put(bump.inputs["Distance"], 0.02)
    b.put(bump.inputs["Height"], rip)
    b.put(bump.inputs["Normal"], n1)
    n2 = bump.outputs["Normal"]
    # ---- snow: snowy edges and shoulder, streaky slush between the wheel tracks, dark wet tracks (high contrast)
    S = C["Snow"]
    between = b.m("MULTIPLY", inlane, b.m("SUBTRACT", 1.0, b.smooth(track, 0.1, 0.45)))
    streak = b.noise(b.xyz(b.m("MULTIPLY", lat, 3.0), b.m("MULTIPLY", along, 0.08), C["SeedOff"]), 1.0, 3.0)
    sl = b.m("ADD", b.m("MULTIPLY", streak, 0.75), b.m("MULTIPLY", nA, 0.45))
    slush = b.m("MULTIPLY", b.m("MULTIPLY", between, S), b.smooth(sl, 0.5, 0.64), clamp=True)
    full = b.m("MULTIPLY", b.m("MULTIPLY", edge, S), b.remap(nB, 0.2, 0.8, 0.8, 1.0), clamp=True)
    trackm = b.m("MULTIPLY", b.m("MULTIPLY", track, S), 0.9, clamp=True)
    b3 = b.mixc(b.m("MULTIPLY", slush, 0.9), b2, b.mixc(nB, (0.2, 0.195, 0.19, 1), (0.32, 0.315, 0.31, 1)))
    # wet dark tracks, not black: seen steeply (near the camera) the glaze reflects little, so the base shows
    b3 = b.mixc(b.m("MULTIPLY", trackm, 0.5), b3, (0.024, 0.026, 0.03, 1))
    b4 = b.mixc(full, b3, (0.8, 0.83, 0.88, 1))
    r3 = b.mixf(slush, r2, 0.5)
    r3 = b.mixf(trackm, r3, 0.045)
    glint = b.m("GREATER_THAN", b.noise(b.v("SCALE", pos, scale=60.0), 1.0, 0.0), 0.74)
    r4 = b.mixf(full, r3, b.mixf(glint, 0.68, 0.06))
    sb = b.new("ShaderNodeBump")
    b.put(sb.inputs["Strength"], b.m("MULTIPLY", b.m("MAXIMUM", full, b.m("MULTIPLY", slush, 0.6)), 0.35))
    b.put(sb.inputs["Distance"], 0.05)
    b.put(sb.inputs["Height"], b.noise(pos, 5.0, 3.0))
    b.put(sb.inputs["Normal"], n2)
    n3 = b.mixv(trackm, sb.outputs["Normal"], geo.outputs["Normal"])
    # ---- black ice: on a bare road large glazed patches over frosted grey asphalt; under snow the ice is in the
    # polished wheel tracks (the sheen the winter-tyre episode needs)
    Ice = C["Ice"]
    S1 = b.m("MINIMUM", S, 1.0)
    patch = b.smooth(b.noise(pos, 0.045, 2.0), 0.44, 0.54)
    zone = b.mixf(S1, b.m("ADD", 0.25, b.m("MULTIPLY", patch, 0.75)), track)
    glaze = b.m("MULTIPLY", b.m("MULTIPLY", Ice, zone), b.m("SUBTRACT", 1.0, b.m("MAXIMUM", full, slush)), clamp=True)
    frost_road = b.m("MULTIPLY", b.m("MULTIPLY", b.m("MULTIPLY", Ice, b.m("SUBTRACT", 1.0, patch)),
                                      b.m("SUBTRACT", 1.0, S1)), b.remap(nB, 0.3, 0.7, 0.25, 0.55))
    b5 = b.mixc(frost_road, b4, (0.42, 0.44, 0.47, 1))
    b5 = b.mixc(b.m("MULTIPLY", glaze, 0.5), b5, b.mixc(1.0, b5, (0.75, 0.8, 0.9, 1), "MULTIPLY"))
    r5 = b.mixf(b.m("MULTIPLY", frost_road, 1.2), r4, 0.75)
    r5 = b.mixf(glaze, r5, 0.025)
    n5 = b.mixv(glaze, n3, geo.outputs["Normal"])
    hoar = b.m("MULTIPLY", b.m("MULTIPLY", edge, C["Frost"]), 0.85)
    b6 = b.mixc(hoar, b5, (0.68, 0.71, 0.76, 1))
    r6 = b.mixf(hoar, r5, 0.85)
    ng.links.new(b6, go.inputs["Base"])
    ng.links.new(r6, go.inputs["Rough"])
    ng.links.new(n5, go.inputs["Normal"])
    return ng


def _surf_group():
    ng = bpy.data.node_groups.get("wx_surf")
    if ng:
        return ng
    ng = bpy.data.node_groups.new("wx_surf", "ShaderNodeTree")
    _iface(ng, [("INPUT", "Base", "NodeSocketColor", (0.5, 0.5, 0.5, 1)), ("INPUT", "Rough", "NodeSocketFloat", 0.5),
                ("INPUT", "Normal", "NodeSocketVector", (0, 0, 0)), ("INPUT", "Porosity", "NodeSocketFloat", 0.3),
                ("INPUT", "Cover", "NodeSocketFloat", 0.6), ("INPUT", "Leaf", "NodeSocketFloat", 0.0),
                ("INPUT", "Vehicle", "NodeSocketFloat", 0.0),
                ("OUTPUT", "Base", "NodeSocketColor", None), ("OUTPUT", "Rough", "NodeSocketFloat", None),
                ("OUTPUT", "Normal", "NodeSocketVector", None)])
    b = _B(ng)
    gi = b.new("NodeGroupInput")
    go = b.new("NodeGroupOutput")
    C = b.group(_ctl_group()).outputs
    I = gi.outputs
    geo = b.new("ShaderNodeNewGeometry")
    pos = b.v("ADD", geo.outputs["Position"], b.xyz(C["SeedOff"], 0.0, b.m("MULTIPLY", C["SeedOff"], 0.3)))
    has_n = b.m("GREATER_THAN", b.v("LENGTH", I["Normal"]), 0.5)
    nrm0 = b.mixv(has_n, geo.outputs["Normal"], I["Normal"])
    nz = b.sep(geo.outputs["Normal"])[2]
    up = b.smooth(nz, 0.3, 0.78)
    nP = b.noise(pos, 0.7, 4.0)
    nF = b.noise(pos, 3.5, 2.0)
    # wet: porous surfaces darken, everything gets glossier
    b1 = b.mixc(b.m("MULTIPLY", C["Wet"], b.m("MULTIPLY", I["Porosity"], 0.55)), I["Base"], (0, 0, 0, 1))
    r1 = b.mixf(b.m("MULTIPLY", C["Wet"], 0.8), I["Rough"], b.m("MULTIPLY_ADD", I["Rough"], 0.35, 0.04))
    # leafless (snow, frost): crowns turn to bare twig brown-grey
    b2 = b.mixc(b.m("MULTIPLY", b.m("MULTIPLY", I["Leaf"], C["Leafless"]), 0.78), b1, (0.15, 0.115, 0.085, 1))
    # snow on everything facing up, patchy where the cover is thin; moving vehicles stay clear
    moving = b.new("ShaderNodeAttribute", attribute_type="INSTANCER", attribute_name="wx_moving").outputs["Fac"]
    cover = b.m("MULTIPLY", I["Cover"], b.m("SUBTRACT", 1.0, b.m("MULTIPLY", I["Vehicle"], moving)))
    amt = b.m("MULTIPLY", cover, C["Snow"])
    thr = b.m("SUBTRACT", 1.0, amt)
    sv = b.m("ADD", b.m("MULTIPLY", up, 0.8), b.m("MULTIPLY", nP, 0.3))
    snowm = b.m("MULTIPLY", b.smooth(sv, b.m("SUBTRACT", thr, 0.06), b.m("ADD", thr, 0.08)),
                b.m("GREATER_THAN", nz, 0.12))
    snowm = b.m("MULTIPLY", snowm, b.m("GREATER_THAN", amt, 0.001))
    b3 = b.mixc(snowm, b2, b.mixc(nF, (0.8, 0.83, 0.88, 1), (0.88, 0.9, 0.94, 1)))
    glint = b.m("GREATER_THAN", b.noise(b.v("SCALE", pos, scale=60.0), 1.0, 0.0), 0.74)
    r3 = b.mixf(snowm, r1, b.mixf(glint, 0.62, 0.06))
    sb = b.new("ShaderNodeBump")
    b.put(sb.inputs["Strength"], b.m("MULTIPLY", snowm, 0.45))
    b.put(sb.inputs["Distance"], 0.05)
    b.put(sb.inputs["Height"], b.m("ADD", b.noise(pos, 4.0, 3.0), b.m("MULTIPLY", b.noise(pos, 0.6, 2.0), 1.5)))
    b.put(sb.inputs["Normal"], nrm0)
    # hoarfrost (ice preset): a white-grey crust on upward faces
    fr = b.m("MULTIPLY", b.m("MULTIPLY", C["Frost"], I["Cover"]),
             b.m("MULTIPLY", b.smooth(nz, 0.05, 0.6), b.remap(nF, 0.2, 0.8, 0.45, 0.85)), clamp=True)
    b4 = b.mixc(fr, b3, (0.7, 0.74, 0.8, 1))
    r4 = b.mixf(fr, r3, 0.85)
    ng.links.new(b4, go.inputs["Base"])
    ng.links.new(r4, go.inputs["Rough"])
    ng.links.new(sb.outputs["Normal"], go.inputs["Normal"])
    return ng


def _emit_group(name):
    """Emission groups. retro: signs, reflectors, plates, markings light up towards the camera (headlights sit near
    it). lamp: street lamp lenses. win: lit windows on a random share of window objects. vhead / vtail: vehicle low
    beams and tail lights, only on moving vehicles (instancer property wx_moving)."""
    ng = bpy.data.node_groups.get("wx_" + name)
    if ng:
        return ng
    ng = bpy.data.node_groups.new("wx_" + name, "ShaderNodeTree")
    _iface(ng, [("INPUT", "Color", "NodeSocketColor", (1, 1, 1, 1)), ("INPUT", "Strength", "NodeSocketFloat", 0.0),
                ("INPUT", "K", "NodeSocketFloat", 1.0),
                ("OUTPUT", "Color", "NodeSocketColor", None), ("OUTPUT", "Strength", "NodeSocketFloat", None)])
    b = _B(ng)
    gi = b.new("NodeGroupInput")
    go = b.new("NodeGroupOutput")
    C = b.group(_ctl_group()).outputs
    I = gi.outputs
    col, st = I["Color"], I["Strength"]
    if name == "retro":
        geo = b.new("ShaderNodeNewGeometry")
        cam = b.new("ShaderNodeCameraData")
        facing = b.m("ABSOLUTE", b.v("DOT_PRODUCT", geo.outputs["Normal"], geo.outputs["Incoming"]))
        d = b.m("DIVIDE", cam.outputs["View Distance"], 38.0)
        g = b.m("DIVIDE", b.m("MULTIPLY_ADD", b.m("POWER", facing, 2.0), 0.75, 0.25), b.m("MULTIPLY_ADD", d, d, 1.0))
        st = b.m("ADD", st, b.m("MULTIPLY", b.m("MULTIPLY", C["Retro"], I["K"]), g))
    elif name == "lamp":
        st = b.m("ADD", st, b.m("MULTIPLY", C["Lamps"], 38.0))
        col = b.mixc(b.m("MINIMUM", C["Lamps"], 1.0), col, (1.0, 0.8, 0.56, 1))
    elif name == "win":
        oi = b.new("ShaderNodeObjectInfo")
        r = oi.outputs["Random"]
        on = b.m("LESS_THAN", r, C["WinFrac"])
        r2 = b.m("FRACT", b.m("MULTIPLY", r, 7.31))
        st = b.m("ADD", st, b.m("MULTIPLY", b.m("MULTIPLY", C["Windows"], on), b.m("MULTIPLY_ADD", r2, 2.0, 2.2)))
        col = b.mixc(b.m("MINIMUM", C["Windows"], 1.0), col,
                     b.mixc(r2, (1.0, 0.55, 0.24, 1), (1.0, 0.78, 0.5, 1)))
    elif name in ("vhead", "vtail"):
        mv = b.new("ShaderNodeAttribute", attribute_type="INSTANCER", attribute_name="wx_moving").outputs["Fac"]
        L = C["Lights"]
        if name == "vhead":
            on = b.mixf(mv, 0.1, C["HeadGain"])
            st = b.mixf(L, st, on)
        else:
            gain = b.mixf(L, 1.0, b.mixf(mv, 0.15, C["TailGain"]))
            col = b.mixc(1.0, col, b.xyz(gain, gain, gain), "MULTIPLY")
    ng.links.new(col, go.inputs["Color"])
    ng.links.new(st, go.inputs["Strength"])
    return ng


def _haze_group():
    ng = bpy.data.node_groups.get("wx_haze")
    if ng:
        return ng
    ng = bpy.data.node_groups.new("wx_haze", "ShaderNodeTree")
    _iface(ng, [("INPUT", "Shader", "NodeSocketShader", None), ("OUTPUT", "Shader", "NodeSocketShader", None)])
    b = _B(ng)
    gi = b.new("NodeGroupInput")
    go = b.new("NodeGroupOutput")
    C = b.group(_ctl_group()).outputs
    cam = b.new("ShaderNodeCameraData")
    h = b.m("SUBTRACT", 1.0, b.m("EXPONENT", b.m("DIVIDE", cam.outputs["View Distance"], C["HazeNegDist"])))
    em = b.new("ShaderNodeEmission")
    b.put(em.inputs["Color"], C["HazeColor"])
    mx = b.new("ShaderNodeMixShader")
    b.put(mx.inputs[0], h)
    ng.links.new(gi.outputs[0], mx.inputs[1])
    ng.links.new(em.outputs[0], mx.inputs[2])
    ng.links.new(mx.outputs[0], go.inputs[0])
    return ng


# ------------------------------------------------------------------ material passes
def _principled(nt):
    return next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)


def _src(sock):
    return sock.links[0].from_socket if sock.is_linked else None


def _feed(m, nt, tgt, out):
    """Link out -> tgt, remembering the link it replaces."""
    if tgt.is_linked:
        lk = tgt.links[0]
        _S["links"].append([m.name, tgt.node.name, tgt.identifier, lk.from_node.name, lk.from_socket.identifier])
    nt.links.new(out, tgt)


def _carry(nt, b, gin, sock):
    """Group input takes what fed the Principled input (link or value)."""
    s = _src(sock)
    if s is not None:
        nt.links.new(s, gin)
    elif sock.type in ("RGBA", "VALUE"):
        b.put(gin, tuple(sock.default_value) if sock.type == "RGBA" else sock.default_value)


def _hazify_layers(nt):
    """The (emission, divide) node pairs that stage.hazify_all / lookdev hazify inserted."""
    out = []
    for n in nt.nodes:
        if n.type != "MIX_SHADER" or n.name.startswith("wx_"):
            continue
        a, e = n.inputs[0], n.inputs[2]
        if not (a.is_linked and e.is_linked) or e.links[0].from_node.type != "EMISSION":
            continue
        sub = a.links[0].from_node
        if sub.type != "MATH" or sub.operation != "SUBTRACT" or not sub.inputs[1].is_linked:
            continue
        ex = sub.inputs[1].links[0].from_node
        if ex.type != "MATH" or ex.operation != "EXPONENT" or not ex.inputs[0].is_linked:
            continue
        dv = ex.inputs[0].links[0].from_node
        if dv.type != "MATH" or dv.operation != "DIVIDE" or not dv.inputs[0].is_linked:
            continue
        if dv.inputs[0].links[0].from_node.type != "CAMERA":
            continue
        out.append((e.links[0].from_node, dv))
    return out


def _skip(name):
    return any(name.startswith(p) for p in SKIP_PREFIX)


def _surf_spec(name):
    if name in SURF:
        return SURF[name]
    for p, spec in SURF_PREFIX:
        if name.startswith(p):
            return spec
    return None


def _treat_materials(stage_kind):
    road = _road_group()
    surf = _surf_group()
    lay = ROAD_LAYOUT[stage_kind]
    any_haze = any(_hazify_layers(m.node_tree) for m in bpy.data.materials if m.node_tree)
    veh_mats = _vehicle_materials()
    counts = {"road": 0, "surf": 0, "retro": 0, "lamp": 0, "win": 0, "vlight": 0, "haze": 0}
    for m in list(bpy.data.materials):
        nt = m.node_tree
        if nt is None or m.name.startswith("wx_"):
            continue
        b = _B(nt, prefix="wx_")
        name = m.name
        base_name = name.split(".")[0]
        p = _principled(nt)
        animated = bool(nt.animation_data and nt.animation_data.action)
        # ---- distance haze: re-colour the existing hazify layers, or add one where the scene has none
        layers = _hazify_layers(nt)
        if layers:
            c = b.group(_ctl_group(), name="ctl").outputs
            for em, dv in layers:
                nt.links.new(c["HazeColor"], em.inputs["Color"])
                nt.links.new(c["HazeNegDist"], dv.inputs[1])
            counts["haze"] += 1
        elif not any_haze and not _skip(name):
            out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.inputs["Surface"].is_linked), None)
            if out:
                g = b.group(_haze_group(), name="haze")
                nt.links.new(out.inputs["Surface"].links[0].from_socket, g.inputs[0])
                _feed(m, nt, out.inputs["Surface"], g.outputs[0])
                counts["haze"] += 1
        if p is None:
            continue
        # ---- surfaces
        if base_name in ROAD_MATS:
            g = b.group(road, name="road")
            vals = (("Mode", lay["mode"]), ("P", lay["P"]), ("Off", lay["off"]), ("Lo", lay["lo"]),
                    ("Hi", lay["hi"]), ("EdgeIn", lay["edge_in"]), ("EdgeOut", lay["edge_out"]),
                    ("Darken", ROAD_MATS[base_name]))
            if base_name == "paint":       # markings: wet and icy, but no slush or snow banks on them
                vals += (("Lo", 0.0), ("Hi", 0.0), ("EdgeIn", -99.0), ("EdgeOut", 99.0))
            for k, v in vals:
                g.inputs[k].default_value = v
            _carry(nt, b, g.inputs["Base"], p.inputs["Base Color"])
            _carry(nt, b, g.inputs["Rough"], p.inputs["Roughness"])
            if p.inputs["Normal"].is_linked:
                nt.links.new(_src(p.inputs["Normal"]), g.inputs["Normal"])
            _feed(m, nt, p.inputs["Base Color"], g.outputs["Base"])
            _feed(m, nt, p.inputs["Roughness"], g.outputs["Rough"])
            _feed(m, nt, p.inputs["Normal"], g.outputs["Normal"])
            counts["road"] += 1
        else:
            spec = _surf_spec(base_name)
            if name in veh_mats and not _skip(name) and spec is None:
                spec = (0.05, 0.85, 2)
            plain = (spec is None and not _skip(name) and not animated
                     and p.inputs["Emission Strength"].default_value == 0.0
                     and not p.inputs["Emission Strength"].is_linked)
            if spec or plain:
                por, cov, kind = spec or (0.3, 0.6, 0)
                g = b.group(surf, name="surf")
                g.inputs["Porosity"].default_value = por
                g.inputs["Cover"].default_value = cov
                g.inputs["Leaf"].default_value = 1.0 if kind == 1 else 0.0
                g.inputs["Vehicle"].default_value = 1.0 if kind == 2 else 0.0
                _carry(nt, b, g.inputs["Base"], p.inputs["Base Color"])
                _carry(nt, b, g.inputs["Rough"], p.inputs["Roughness"])
                if p.inputs["Normal"].is_linked:
                    nt.links.new(_src(p.inputs["Normal"]), g.inputs["Normal"])
                _feed(m, nt, p.inputs["Base Color"], g.outputs["Base"])
                _feed(m, nt, p.inputs["Roughness"], g.outputs["Rough"])
                _feed(m, nt, p.inputs["Normal"], g.outputs["Normal"])
                counts["surf"] += 1
        # ---- emission
        kind = None
        k_retro = RETRO.get(base_name)
        if k_retro is None and name.startswith("sign_") and not name.startswith(("sign_back", "sign_black",
                                                                                  "sign_post")):
            if any(n.type == "TEX_IMAGE" for n in nt.nodes):
                k_retro = 1.4
        if k_retro is not None:
            kind = "retro"
        elif base_name == "lamp_glass":
            kind = "lamp"
        elif base_name in ("window_glass", "house_window"):
            kind = "win"
        elif base_name == "car_head" or (name.endswith("_head") and min(p.inputs["Emission Color"].default_value[:3])
                                         > 0.6 and not name.startswith("lamp")):
            kind = "vhead"                  # shared car_head, or per-car copies (motion.py, jx heroes)
        elif base_name == "car_tail" or (name.endswith("_tail") and p.inputs["Emission Color"].default_value[1] < 0.2
                                         and p.inputs["Emission Color"].default_value[0] > 0.5):
            kind = "vtail"
        if kind is None:
            continue
        g = b.group(_emit_group(kind), name=kind)
        g.inputs["K"].default_value = k_retro or 1.0
        ec, es = p.inputs["Emission Color"], p.inputs["Emission Strength"]
        if kind == "retro":
            src = _src(ec) or _src(p.inputs["Base Color"])
            if src is not None:
                nt.links.new(src, g.inputs["Color"])
            else:
                b.put(g.inputs["Color"], tuple(p.inputs["Base Color"].default_value))
        else:
            _carry(nt, b, g.inputs["Color"], ec)
        if es.is_linked:
            nt.links.new(_src(es), g.inputs["Strength"])
        else:
            g.inputs["Strength"].default_value = es.default_value
        _feed(m, nt, ec, g.outputs["Color"])
        if kind != "vtail":      # tail strength stays free: brake-light keys live on it
            _feed(m, nt, es, g.outputs["Strength"])
        if kind in ("retro", "win", "lamp"):
            _S["emission_sampling"][m.name] = m.cycles.emission_sampling
            m.cycles.emission_sampling = "NONE"
        counts["retro" if kind == "retro" else ("vlight" if kind[0] == "v" else kind)] += 1
    return counts


# ------------------------------------------------------------------ world, sun, compositor
def _sun():
    o = bpy.data.objects.get("sun")
    if o and o.type == "LIGHT" and o.data.type == "SUN":
        return o
    return next((o for o in bpy.context.scene.objects if o.type == "LIGHT" and o.data.type == "SUN"), None)


def _to_sun(o):
    """Direction towards the sun from its rotation (matrix_world can be stale until the depsgraph updates)."""
    d = o.rotation_euler.to_matrix() @ Vector((0, 0, -1))
    return -d.normalized()


def _build_world(P, to_sun, to_moon):
    w = bpy.data.worlds.new("wx_world")
    w.use_nodes = True
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    b = _B(nt)
    out = b.new("ShaderNodeOutputWorld")
    tc = b.new("ShaderNodeTexCoord")
    d = b.v("NORMALIZE", tc.outputs["Generated"])
    e = b.sep(d)[2]
    f = b.m("MULTIPLY_ADD", e, 0.5, 0.5)
    g_, h_, m_, z_ = P["sky"]

    def ramp(name):
        r = b.new("ShaderNodeValToRGB", name=name)
        els = r.color_ramp.elements
        els[0].position, els[0].color = 0.46, (*g_, 1)
        els[1].position, els[1].color = 1.0, (*z_, 1)
        els.new(0.5).color = (*h_, 1)
        els.new(0.585).color = (*m_, 1)
        b.put(r.inputs["Fac"], f)
        return r.outputs["Color"]

    above = b.smooth(f, 0.48, 0.56)
    col = ramp("sky_cam")
    # clouds: soft noise on the direction, only above the horizon
    cn = b.noise(b.v("MULTIPLY", d, (3.0, 3.0, 10.0)), 1.0, 7.0, rough=0.62)
    cn2 = b.noise(b.v("MULTIPLY", d, (0.8, 0.8, 2.6)), 1.0, 2.0)
    cv = b.m("ADD", b.m("MULTIPLY", b.m("SUBTRACT", cn, 0.5), 1.0), b.m("MULTIPLY", b.m("SUBTRACT", cn2, 0.5), 1.4))
    hz = b.smooth(f, 0.5, 0.66)             # cloud contrast fades into the haze at the horizon
    cf = b.m("MULTIPLY_ADD", cv, b.m("MULTIPLY", b.m("MULTIPLY", above, hz), 2.0 * P["clouds"]), 1.0)
    col = b.mixc(1.0, col, b.xyz(cf, cf, cf), "MULTIPLY")
    # sun glow (dusk, ice)
    if P["glow"] > 0:
        s = b.m("MAXIMUM", b.v("DOT_PRODUCT", d, tuple(to_sun)), 0.0)
        gl = b.m("ADD", b.m("MULTIPLY", b.m("POWER", s, 5.0), P["glow"]),
                 b.m("MULTIPLY", b.m("POWER", s, 90.0), P["glow"] * 3.0))
        col = b.mixc(gl, col, (*P["glow_col"], 1), "ADD")
    if P["stars"] > 0:
        vo = b.new("ShaderNodeTexVoronoi")
        b.put(vo.inputs["Vector"], d)
        b.put(vo.inputs["Scale"], 240.0)
        star = b.m("SUBTRACT", 1.0, b.smooth(vo.outputs["Distance"], 0.0, 0.07))
        pick = b.m("GREATER_THAN", b.sep(vo.outputs["Color"])[0], 0.82)
        sv = b.m("MULTIPLY", b.m("MULTIPLY", star, pick), b.m("MULTIPLY", b.smooth(f, 0.53, 0.66), 0.45 * P["stars"]))
        col = b.mixc(sv, col, (0.85, 0.9, 1.0, 1), "ADD")
    if P["moon"] > 0:
        md = b.v("DOT_PRODUCT", d, tuple(to_moon))
        disc = b.smooth(md, math.cos(math.radians(1.25)), math.cos(math.radians(1.05)))
        halo = b.m("MULTIPLY", b.m("POWER", b.m("MAXIMUM", md, 0.0), 300.0), 0.05)
        col = b.mixc(b.m("ADD", b.m("MULTIPLY", disc, 2.2 * P["moon"]), halo), col, (0.95, 0.96, 1.0, 1), "ADD")
    bg_cam = b.new("ShaderNodeBackground", name="sky_cam_bg")
    b.put(bg_cam.inputs["Color"], col)
    bg_cam.inputs["Strength"].default_value = 1.0
    bg_amb = b.new("ShaderNodeBackground", name="sky_amb")
    b.put(bg_amb.inputs["Color"], ramp("sky_light"))
    bg_amb.inputs["Strength"].default_value = P["amb"]
    lp = b.new("ShaderNodeLightPath")
    mx = b.new("ShaderNodeMixShader")
    b.put(mx.inputs[0], lp.outputs["Is Camera Ray"])
    nt.links.new(bg_amb.outputs[0], mx.inputs[1])
    nt.links.new(bg_cam.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return w


def _compositor(P):
    if P["bloom"] <= 0:
        return None
    ng = bpy.data.node_groups.new("wx_comp", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    gl = ng.nodes.new("CompositorNodeGlare")
    gl.name = "wx_glare"
    gl.inputs["Type"].default_value = P["glare"]
    gl.inputs["Quality"].default_value = "Medium"
    gl.inputs["Highlights Threshold"].default_value = 1.0
    gl.inputs["Strength"].default_value = P["bloom"]
    if P["wx"] == "fog":
        gl.inputs["Size"].default_value = 1.0          # wide halo round every light, as fog glow does
    go = ng.nodes.new("NodeGroupOutput")
    ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
    ng.links.new(gl.outputs["Image"], go.inputs[0])
    return ng


# ------------------------------------------------------------------ vehicles
def _vehicle_colls():
    out = set()
    for c in bpy.data.collections:
        if any(o.name.startswith("headlight") for o in c.objects):     # own objects only (not "lib" itself)
            out.add(c.name)
    return out


def vehicles():
    """[(instance object, moving)] for every vehicle in the scene."""
    vc = _vehicle_colls()
    res = []
    for o in bpy.context.scene.objects:
        if o.type != "EMPTY" or o.instance_type != "COLLECTION" or not o.instance_collection:
            continue
        if o.instance_collection.name not in vc:
            continue
        if "wx_moving" in o.keys() and o.name not in (_S or {}).get("props", []):
            mv = bool(o["wx_moving"])
        elif o.name.startswith("parked"):
            mv = False
        elif o.animation_data and o.animation_data.action:
            mv = _moves(o)
        else:
            r = _motion_rig(o)
            mv = (r.track is not None) if r is not None else any(c.name == "traffic" for c in o.users_collection)
        res.append((o, mv))
    return res


def _moves(o):
    """True when the object's location keys actually change (a keyed but standing car is parked)."""
    try:
        fcs = [fc for fc in _fcurves(o) if fc.data_path == "location"]
    except Exception:
        return True
    for fc in fcs:
        vals = [kp.co[1] for kp in fc.keyframe_points]
        if vals and max(vals) - min(vals) > 0.5:
            return True
    return False


def _motion_rig(o):
    try:
        import motion
        return motion._rigs.get(o.name)
    except Exception:
        return None


def _mw(o):
    """World matrix from the parent chain (the library collection is excluded from the view layer, so the stored
    matrix_world of its objects can be stale)."""
    if o.parent is None:
        return o.matrix_basis.copy()
    return _mw(o.parent) @ o.matrix_parent_inverse @ o.matrix_basis


def _src_coll(coll):
    """The full vehicle collection: motion.rig swaps an instance to <model>__body (no wheels); dl_src names the
    original."""
    if "dl_src" in coll.keys() and bpy.data.collections.get(coll["dl_src"]):
        return bpy.data.collections[coll["dl_src"]]
    return coll


def _lamp_parts(coll):
    """Headlight centres (collection space) of a vehicle: [(x, y, z)] and its front y, rear y, half width, height."""
    coll = _src_coll(coll)
    pts = [_mw(o).translation.copy() for o in coll.all_objects if o.name.startswith("headlight")]
    ys, xs, zs = [], [], []
    for o in coll.all_objects:
        if o.type == "MESH":
            mw = _mw(o)
            for c in o.bound_box:
                v = mw @ Vector(c)
                ys.append(v.y)
                xs.append(abs(v.x))
                zs.append(v.z)
    return pts, (max(ys) if ys else 2.0), (min(ys) if ys else -2.0), (max(xs) if xs else 0.9), (max(zs) if zs else 1.5)


def _wheels(coll):
    coll = _src_coll(coll)
    out = []
    for o in coll.all_objects:
        if o.type == "MESH" and o.data.materials and o.data.materials[0] and \
                o.data.materials[0].name.startswith("car_tyre"):
            p = _mw(o).translation
            r = max(o.dimensions) / 2
            out.append((p.x, p.y, r))
    return out


def _vehicle_materials():
    names = set()
    vc = _vehicle_colls()
    for c in bpy.data.collections:
        if c.name in vc:
            for o in c.all_objects:
                if o.type in ("MESH", "FONT", "CURVE"):
                    names.update(m.name for m in o.data.materials if m)
    return names


def headlights(obj, on=True, power=400.0, tail_glow=0.0):
    """Low beams on one vehicle instance: two spot lights at its headlights (and a faint red glow light at the rear
    when tail_glow > 0, which lights rain spray). Marks the instance as moving for the emission groups."""
    coll = obj.instance_collection
    if coll is None:
        return []
    if "wx_moving" not in obj.keys():
        obj["wx_moving"] = 1.0
        if _S is not None:
            _S["props"].append(obj.name)
    if not on:
        return []
    beams = [ch for ch in o_children(obj) if ch.type == "LIGHT" and "_beam" in ch.name]
    if beams:                              # motion.bake(night=True) already gave this vehicle its low beams
        for ch in beams:
            if _S is not None and ch.name not in _S["beam_energy"]:
                _S["beam_energy"][ch.name] = ch.data.energy
            ch.data.energy = power
        return []
    pts, yf, yr, hw, ht = _lamp_parts(coll)
    col = _wx_coll()
    made = []
    for k, p in enumerate(pts[:2] if len(pts) >= 2 else pts):
        ld = bpy.data.lights.new(f"wx_head_{obj.name}_{k}", "SPOT")
        ld.energy = power
        ld.color = (1.0, 0.94, 0.84)
        ld.spot_size = math.radians(48)          # low beam: a tight cone, so the lit asphalt ahead reads
        ld.spot_blend = 0.35
        ld.shadow_soft_size = 0.06
        lo = bpy.data.objects.new(ld.name, ld)
        col.objects.link(lo)
        lo.parent = obj
        lo.location = (p.x, p.y + 0.05, p.z)
        lo.rotation_euler = (math.radians(90 - 6.0), 0, 0)     # spot points along local +y, 6 deg down
        made.append(lo)
    if tail_glow > 0:
        made.append(globals()["tail_glow"](obj, tail_glow))
    return made


def tail_glow(obj, watts=40.0):
    """A soft red point light behind a vehicle: tail lights bleeding into spray, fog or falling snow."""
    coll = obj.instance_collection
    if coll is None:
        return None
    pts, yf, yr, hw, ht = _lamp_parts(coll)
    ld = bpy.data.lights.new(f"wx_tailglow_{obj.name}", "POINT")
    ld.energy = watts
    ld.color = (1.0, 0.06, 0.02)
    ld.shadow_soft_size = 0.4
    lo = bpy.data.objects.new(ld.name, ld)
    _wx_coll().objects.link(lo)
    lo.parent = obj
    lo.location = (0.0, yr - 0.7, 1.0)
    return lo


def o_children(obj):
    return [o for o in bpy.data.objects if o.parent == obj]


def _motion_lights(obj, on):
    try:
        import motion  # noqa: F401  (vehicles agent, batch 2)
    except Exception:
        return False
    fn = getattr(motion, "lights", None) or getattr(motion, "set_lights", None)
    if fn is None:
        return False
    try:
        fn(obj, on)
        return True
    except Exception:
        return False


def _wx_coll():
    c = bpy.data.collections.get("wx")
    if c is None:
        c = bpy.data.collections.new("wx")
        bpy.context.scene.collection.children.link(c)
    return c


# ------------------------------------------------------------------ precipitation (geometry nodes, camera-relative)
def _precip_group(kind):
    name = f"wx_{kind}_gn"
    ng = bpy.data.node_groups.get(name)
    if ng:
        return ng
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    _iface(ng, [("INPUT", "Geometry", "NodeSocketGeometry", None), ("INPUT", "Count", "NodeSocketInt", 1000),
                ("INPUT", "Strength", "NodeSocketFloat", 1.0), ("INPUT", "Seed", "NodeSocketInt", 0),
                ("INPUT", "Fall", "NodeSocketFloat", 9.0), ("INPUT", "Wind", "NodeSocketVector", (0.8, 0.4, 0.0)),
                ("INPUT", "Box", "NodeSocketFloat", 36.0), ("INPUT", "Height", "NodeSocketFloat", 14.0),
                ("INPUT", "Near", "NodeSocketFloat", 1.0), ("INPUT", "Length", "NodeSocketFloat", 0.4),
                ("INPUT", "Radius", "NodeSocketFloat", 0.004), ("INPUT", "Wobble", "NodeSocketFloat", 0.0),
                ("INPUT", "Material", "NodeSocketMaterial", None),
                ("OUTPUT", "Geometry", "NodeSocketGeometry", None)])
    b = _B(ng)
    gi = b.new("NodeGroupInput")
    go = b.new("NodeGroupOutput")
    I = gi.outputs
    rnd = b.new("FunctionNodeRandomValue", data_type="FLOAT_VECTOR")
    _id(rnd.inputs, "Min").default_value = (0, 0, 0)
    _id(rnd.inputs, "Max").default_value = (1, 1, 1)
    ng.links.new(I["Seed"], rnd.inputs["Seed"])
    box = b.xyz(I["Box"], I["Box"], I["Height"])
    p0 = b.v("MULTIPLY", _id(rnd.outputs, "Value"), box)
    pts = b.new("GeometryNodePoints")
    ng.links.new(I["Count"], pts.inputs["Count"])
    ng.links.new(p0, pts.inputs["Position"])
    t = b.new("GeometryNodeInputSceneTime").outputs["Seconds"]
    vel = b.v("ADD", I["Wind"], b.xyz(0.0, 0.0, b.m("MULTIPLY", I["Fall"], -1.0)))
    pos = b.v("ADD", b.new("GeometryNodeInputPosition").outputs[0], b.v("SCALE", vel, scale=t))
    # snow: each flake sways on its own phase
    ph = b.new("FunctionNodeRandomValue", data_type="FLOAT")
    _id(ph.inputs, "Min_001").default_value = 0.0
    _id(ph.inputs, "Max_001").default_value = 2 * math.pi
    b.put(ph.inputs["Seed"], 17)
    phase = _id(ph.outputs, "Value_001")
    sw = b.xyz(b.m("SINE", b.m("MULTIPLY_ADD", t, 1.3, phase)), b.m("COSINE", b.m("MULTIPLY_ADD", t, 0.9, phase)), 0.0)
    pos = b.v("ADD", pos, b.v("SCALE", sw, scale=I["Wobble"]))
    # the box follows the camera (centre ahead of the lens), drops are world-stable inside it (wrap)
    ci = b.new("GeometryNodeObjectInfo", transform_space="ORIGINAL")
    ng.links.new(b.new("GeometryNodeInputActiveCamera").outputs[0], ci.inputs["Object"])
    rv = b.new("FunctionNodeRotateVector")
    rv.inputs["Vector"].default_value = (0, 0, -1)
    ng.links.new(ci.outputs["Rotation"], rv.inputs["Rotation"])
    fwd = rv.outputs[0]
    ahead = b.m("ADD", I["Near"], b.m("MULTIPLY", I["Box"], 0.5))
    centre = b.v("ADD", ci.outputs["Location"], b.v("SCALE", fwd, scale=ahead))
    centre = b.v("ADD", centre, b.xyz(0.0, 0.0, b.m("MULTIPLY", I["Height"], 0.22)))
    half = b.v("SCALE", box, scale=0.5)
    wrapped = b.v("WRAP", pos, b.v("ADD", centre, half), b.v("SUBTRACT", centre, half))
    sp = b.new("GeometryNodeSetPosition")
    ng.links.new(pts.outputs[0], sp.inputs["Geometry"])
    ng.links.new(wrapped, sp.inputs["Position"])
    # strength thins the drops out
    keep = b.new("FunctionNodeRandomValue", data_type="FLOAT")
    b.put(keep.inputs["Seed"], 31)
    dl = b.new("GeometryNodeDeleteGeometry", domain="POINT")
    ng.links.new(sp.outputs[0], dl.inputs["Geometry"])
    ng.links.new(b.m("GREATER_THAN", _id(keep.outputs, "Value_001"), I["Strength"]), dl.inputs["Selection"])
    geo = dl.outputs[0]
    if kind == "rain":
        ln = b.new("GeometryNodeCurvePrimitiveLine")
        ln.inputs["Start"].default_value = (0, 0, 0)
        ng.links.new(b.v("SCALE", b.v("NORMALIZE", vel), scale=b.m("MULTIPLY", I["Length"], -1.0)), ln.inputs["End"])
        ip = b.new("GeometryNodeInstanceOnPoints")
        ng.links.new(geo, ip.inputs["Points"])
        ng.links.new(ln.outputs[0], ip.inputs["Instance"])
        rl = b.new("GeometryNodeRealizeInstances")
        ng.links.new(ip.outputs[0], rl.inputs["Geometry"])
        rad = b.new("GeometryNodeSetCurveRadius")
        ng.links.new(rl.outputs[0], rad.inputs["Curve"])
        ng.links.new(I["Radius"], rad.inputs["Radius"])
        geo = rad.outputs[0]
    else:
        rr = b.new("FunctionNodeRandomValue", data_type="FLOAT")
        _id(rr.inputs, "Min_001").default_value = 0.55
        _id(rr.inputs, "Max_001").default_value = 1.45
        b.put(rr.inputs["Seed"], 5)
        rad = b.new("GeometryNodeSetPointRadius")
        ng.links.new(geo, rad.inputs["Points"])
        dcam = b.v("DISTANCE", b.new("GeometryNodeInputPosition").outputs[0], ci.outputs["Location"])
        near = b.smooth(dcam, 1.2, 4.5)
        ng.links.new(b.m("MULTIPLY", b.m("MULTIPLY", _id(rr.outputs, "Value_001"), I["Radius"]), near),
                     rad.inputs["Radius"])
        geo = rad.outputs[0]
    sm = b.new("GeometryNodeSetMaterial")
    ng.links.new(geo, sm.inputs["Geometry"])
    ng.links.new(I["Material"], sm.inputs["Material"])
    ng.links.new(sm.outputs[0], go.inputs[0])
    return ng


def _precip_material(kind):
    m = bpy.data.materials.new(f"wx_{kind}_mat")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    b = _B(nt)
    C = b.group(_ctl_group()).outputs
    p = b.new("ShaderNodeBsdfPrincipled")
    tr = b.new("ShaderNodeBsdfTransparent")
    mx = b.new("ShaderNodeMixShader")
    if kind == "rain":
        hi = b.new("ShaderNodeHairInfo")
        fade = b.m("SINE", b.m("MULTIPLY", hi.outputs["Intercept"], math.pi))
        a = b.m("MULTIPLY", fade, C["RainAlpha"])
        p.inputs["Base Color"].default_value = (0.82, 0.86, 0.9, 1)
        p.inputs["Roughness"].default_value = 0.3
        b.put(p.inputs["Emission Color"], C["HazeColor"])
        b.put(p.inputs["Emission Strength"], b.m("MULTIPLY", C["RainAlpha"], 1.1))
    else:
        # opaque flakes (no transparent bounces), lit a little brighter than the haze so they read on sky and road
        a = C["SnowAlpha"]
        p.inputs["Base Color"].default_value = (0.93, 0.95, 0.98, 1)
        p.inputs["Roughness"].default_value = 0.7
        hc = b.sep(C["HazeColor"])
        lum = b.m("ADD", b.m("MULTIPLY", hc[1], 0.7), b.m("MULTIPLY", b.m("ADD", hc[0], hc[2]), 0.15))
        b.put(p.inputs["Emission Color"], (0.95, 0.97, 1.0, 1))
        b.put(p.inputs["Emission Strength"], b.m("MULTIPLY", lum, 1.25))
    b.put(mx.inputs[0], a)
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(p.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    m.cycles.emission_sampling = "NONE"
    return m


def _camera_only(o):
    for k in ("visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter", "visible_shadow"):
        setattr(o, k, False)
    o.cycles.use_motion_blur = False      # drops wrap around the camera box; their streak is modelled instead


def _precip(kind, P, seed):
    me = bpy.data.meshes.new(f"wx_{kind}")
    o = bpy.data.objects.new(f"wx_{kind}", me)
    _wx_coll().objects.link(o)
    mod = o.modifiers.new("wx", "NODES")
    mod.node_group = _precip_group(kind)
    s = P["strength"]
    if kind == "rain":
        vals = dict(Count=RAIN_COUNT, Strength=min(1.0, P["rain"]), Seed=seed, Fall=9.0, Wind=(0.9, 0.5, 0.0),
                    Box=24.0, Height=10.0, Near=0.4, Length=0.8, Radius=0.008, Wobble=0.0)
    else:
        vals = dict(Count=SNOW_COUNT, Strength=min(1.0, P["snowfall"]), Seed=seed, Fall=1.25, Wind=(1.1, 0.6, 0.0),
                    Box=26.0, Height=10.0, Near=0.3, Length=0.0, Radius=0.008, Wobble=0.35)
    vals["Material"] = _precip_material(kind)
    for it in mod.node_group.interface.items_tree:
        if it.item_type == "SOCKET" and it.in_out == "INPUT" and it.name in vals:
            mod[it.identifier] = vals[it.name]
    _camera_only(o)
    o["wx_count"] = vals["Count"]
    del s
    return o


# ------------------------------------------------------------------ wheel spray
def _spray_material(scatter=None):
    """Volume mist behind a vehicle, shaped analytically in vehicle space and read from the spray box's own custom
    properties (wx_int intensity, wx_odo odometer in m, wx_L decay length, wx_yr rear y, wx_yw first spraying wheel y,
    wx_hw half width, wx_ht height), so one material serves every vehicle. The noise is advected with the odometer, so
    the mist hangs in the air while the vehicle drives through it."""
    m = bpy.data.materials.get("wx_spray_mat")
    if m:
        return m
    if scatter is None:
        scatter = bool(_S and _S["P"].get("night", 0) >= 1)
    m = bpy.data.materials.new("wx_spray_mat")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    b = _B(nt)
    C = b.group(_ctl_group()).outputs

    def prop(k):
        return b.new("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name=k).outputs["Fac"]
    inten, odo, L = prop("wx_int"), prop("wx_odo"), prop("wx_L")
    yr, yw, hw, ht = prop("wx_yr"), prop("wx_yw"), prop("wx_hw"), prop("wx_ht")
    p = b.new("ShaderNodeTexCoord").outputs["Object"]
    x, y, z = b.sep(p)
    dr = b.m("SUBTRACT", yr, y)
    dw = b.m("SUBTRACT", yw, y)
    drp = b.m("MAXIMUM", dr, 0.0)
    rx = b.m("ADD", b.m("MULTIPLY", hw, 1.15), b.m("MULTIPLY", drp, 0.16))
    fx = b.m("SUBTRACT", 1.0, b.smooth(b.m("ABSOLUTE", x), b.m("MULTIPLY", rx, 0.45), rx))
    h = b.m("ADD", b.mixf(b.smooth(dr, -1.0, 5.0), 1.0, b.m("MULTIPLY", ht, 1.0)), b.m("MULTIPLY", drp, 0.04))
    fz = b.m("POWER", b.m("SUBTRACT", 1.0, b.smooth(z, 0.0, h)), 1.3)
    fy = b.m("MULTIPLY", b.smooth(dw, -0.3, 1.2), b.m("EXPONENT", b.m("DIVIDE", b.m("MULTIPLY", drp, -1.0), L)))
    t = C["Time"]
    # 3D noise (cheaper than 4D at every ray-march step), boiling upwards and sideways with time
    q = b.v("ADD", p, b.xyz(b.m("MULTIPLY", t, 0.25), odo, b.m("MULTIPLY", t, -0.6)))
    n1 = b.noise(b.v("MULTIPLY", q, (0.55, 0.32, 0.6)), 1.0, 2.0, rough=0.55)
    n2 = b.noise(q, 2.2, 1.0)
    cl = b.m("MULTIPLY_ADD", n1, 2.4, -0.62)
    cl = b.m("MAXIMUM", b.m("ADD", cl, b.m("MULTIPLY", b.m("SUBTRACT", n2, 0.5), 0.5)), 0.0)
    dens = b.m("MULTIPLY", b.m("MULTIPLY", b.m("MULTIPLY", fx, fy), b.m("MULTIPLY", fz, cl)),
               b.m("MULTIPLY", inten, 4.0))
    # mist = scattering (catches head and tail lights) + absorption + a self-lit part in the haze colour, so it reads
    # as bright spray against the wet road in flat overcast light, like the distance haze does
    ab = b.new("ShaderNodeVolumeAbsorption")
    ab.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    b.put(ab.inputs["Density"], b.m("MULTIPLY", dens, 0.3))
    em = b.new("ShaderNodeEmission")
    b.put(em.inputs["Color"], C["HazeColor"])
    b.put(em.inputs["Strength"], b.m("MULTIPLY", dens, 0.9))
    a1 = b.new("ShaderNodeAddShader")
    nt.links.new(ab.outputs[0], a1.inputs[0])
    if scatter:
        # night: real scattering, so head and tail lights glow in the mist (light sampling per step: costly)
        sca = b.new("ShaderNodeVolumeScatter")
        sca.inputs["Color"].default_value = (0.9, 0.92, 0.95, 1)
        sca.inputs["Anisotropy"].default_value = 0.5
        b.put(sca.inputs["Density"], b.m("MULTIPLY", dens, 0.35))
        nt.links.new(sca.outputs[0], a1.inputs[1])
    vol = b.new("ShaderNodeAddShader")
    nt.links.new(a1.outputs[0], vol.inputs[0])
    nt.links.new(em.outputs[0], vol.inputs[1])
    nt.links.new(vol.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    return m


def _box_mesh(name, x0, x1, y0, y1, z0, z1):
    me = bpy.data.meshes.new(name)
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    me.from_pydata(v, [], [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    return me


def _speed_track(obj, frames):
    """Speed in m/s per frame from the object's location keys (or by stepping the scene when it has none)."""
    sc = bpy.context.scene
    fps = sc.render.fps / sc.render.fps_base
    frames = list(frames)
    locs = []
    fcs = []
    if obj.animation_data and obj.animation_data.action:
        try:
            fcs = [fc for fc in _fcurves(obj) if fc.data_path == "location"]
        except Exception:
            fcs = []
    if len(fcs) == 3 and obj.parent is None:
        fcs.sort(key=lambda fc: fc.array_index)
        for f in frames:
            locs.append(Vector([fc.evaluate(f) for fc in fcs]))
    else:
        keep = sc.frame_current
        for f in frames:
            sc.frame_set(f)
            locs.append(obj.matrix_world.translation.copy())
        sc.frame_set(keep)
    sp = []
    for i in range(len(frames)):
        a, b_ = max(0, i - 1), min(len(frames) - 1, i + 1)
        dt = (frames[b_] - frames[a]) / fps
        sp.append(((locs[b_] - locs[a]).length / dt) if dt > 0 else 0.0)
    return frames, sp


def spray(obj, frames=None, speed=None, strength=1.0, seed=0):
    """Wheel spray and wake mist behind a vehicle instance in the wet: a volume box parented to the vehicle.
    frames: key the mist per frame from the vehicle's own speed (none below 4 m/s, full from 22 m/s, trail length
    0.45 s x speed); speed: a constant speed in m/s instead (stills). Returns the spray object (removed by
    apply("day"))."""
    coll = obj.instance_collection
    if coll is None:
        raise ValueError(f"{obj.name} is not a vehicle instance")
    wheels = _wheels(coll)
    pts, yf, yr, hw, ht = _lamp_parts(coll)
    big = (yf - yr) > 8.0
    ys = [y for (x, y, r) in wheels if not (big and y > yf - 2.5)]
    yw = (max(ys) if ys else yr) + 0.3
    sc = bpy.context.scene
    fps = sc.render.fps / sc.render.fps_base

    def inten(v):
        return max(0.0, min(1.0, (v - 4.0) / 18.0)) * strength * (1.25 if big else 0.9)

    def decay(v):
        return max(2.0, 0.5 * v * (1.4 if big else 1.0))

    if frames is not None and speed is None:
        fr, sp = _speed_track(obj, frames)
    else:
        v = 25.0 if speed is None else float(speed)
        fr, sp = [sc.frame_current], [v]
    Lmax = max(decay(v) for v in sp)
    span = min(60.0, 3.2 * Lmax)
    wmax = hw * 1.15 + 0.16 * span + 0.3
    hmax = max(1.2, ht) + 0.04 * span + 0.3
    me = _box_mesh(f"wx_spray_{obj.name}", -wmax, wmax, yr - span, yw + 0.2, 0.0, hmax)
    me.materials.append(_spray_material())
    o = bpy.data.objects.new(f"wx_spray_{obj.name}", me)
    _wx_coll().objects.link(o)
    o.parent = obj
    o["wx_yr"], o["wx_yw"], o["wx_hw"], o["wx_ht"] = yr, yw, hw, ht
    o["wx_int"], o["wx_L"], o["wx_odo"] = inten(sp[0]), decay(sp[0]), 0.0
    if len(fr) > 1:
        odo = 0.0
        last = None
        for i, (f, v) in enumerate(zip(fr, sp)):
            if i:
                odo += v * (f - fr[i - 1]) / fps
            o["wx_odo"] = odo
            o.keyframe_insert('["wx_odo"]', frame=f)
            key = (round(inten(v), 3), round(decay(v), 1))
            if key != last:
                o["wx_int"], o["wx_L"] = key
                o.keyframe_insert('["wx_int"]', frame=f)
                o.keyframe_insert('["wx_L"]', frame=f)
                last = key
        for fc in _fcurves(o):
            lin = fc.data_path == '["wx_odo"]'
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR" if lin else "CONSTANT"
    else:
        o["wx_odo"] = (sc.frame_current / fps) * sp[0]
    # camera rays only: wet-road reflections and bounce light would march through the volume again (3x the cost)
    for k in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission"):
        setattr(o, k, False)
    o["wx_count"] = 0
    _spray_volumes()
    return o


def _spray_volumes():
    """Biased ray marching for the spray boxes (apply("day") puts the scene's own values back)."""
    c = bpy.context.scene.cycles
    for k, v in SPRAY_VOLUME.items():
        if getattr(c, k) != v:
            setattr(c, k, v)


# ------------------------------------------------------------------ state, restore
def _stage_kind():
    if bpy.data.objects.get("lanesR") or bpy.data.objects.get("lanesL"):
        return "autobahn"
    return "town"


def _save():
    try:
        bpy.context.scene["wx_state"] = json.dumps({k: v for k, v in _S.items() if k != "P"} |
                                                   {"preset": _S["P"]["preset"]})
    except Exception:
        pass


def _load():
    global _S
    if _S is None:
        raw = bpy.context.scene.get("wx_state")
        if raw:
            try:
                _S = json.loads(raw)
                _S.setdefault("P", {"preset": _S.get("preset", "?")})
            except Exception:
                _S = None
    return _S


def restore():
    """Back to the stage exactly as built: removes every wx_* node, object, light, group and material."""
    global _S
    _load()
    sc = bpy.context.scene
    c = bpy.data.collections.get("wx")
    if c:
        for o in list(c.objects):
            data = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if data is not None and data.users == 0:
                if isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.Light):
                    bpy.data.lights.remove(data)
        bpy.data.collections.remove(c)
    for m in bpy.data.materials:
        nt = m.node_tree
        if nt is None:
            continue
        for n in [n for n in nt.nodes if n.name.startswith("wx_")]:
            nt.nodes.remove(n)
    if _S:
        for mat, tn, ts, fn, fs in _S.get("links", []):
            m = bpy.data.materials.get(mat)
            if not m or not m.node_tree:
                continue
            nt = m.node_tree
            to_n, fr_n = nt.nodes.get(tn), nt.nodes.get(fn)
            if not to_n or not fr_n:
                continue
            to_s = next((s for s in to_n.inputs if s.identifier == ts), None)
            fr_s = next((s for s in fr_n.outputs if s.identifier == fs), None)
            if to_s and fr_s:
                nt.links.new(fr_s, to_s)
        for mat, v in _S.get("emission_sampling", {}).items():
            m = bpy.data.materials.get(mat)
            if m:
                m.cycles.emission_sampling = v
        if _S.get("world") and bpy.data.worlds.get(_S["world"]):
            sc.world = bpy.data.worlds[_S["world"]]
        su = _S.get("sun")
        if su and bpy.data.objects.get(su["name"]):
            o = bpy.data.objects[su["name"]]
            o.data.energy = su["energy"]
            o.data.color = su["color"]
            o.data.angle = su["angle"]
            o.rotation_euler = su["rot"]
            o.visible_glossy = su.get("glossy", True)
        v = _S.get("view", {})
        if v:
            sc.view_settings.exposure = v["exposure"]
        cy = _S.get("cycles", {})
        for k, val in cy.items():
            setattr(sc.cycles, k, val)
        sc.compositing_node_group = bpy.data.node_groups.get(_S["comp"]) if _S.get("comp") else None
        for name, e in _S.get("beam_energy", {}).items():
            o = bpy.data.objects.get(name)
            if o and o.type == "LIGHT":
                o.data.energy = e
        for name in _S.get("props", []):
            o = bpy.data.objects.get(name)
            if o and "wx_moving" in o.keys():
                del o["wx_moving"]
    for w in [w for w in bpy.data.worlds if w.name.startswith("wx_")]:
        bpy.data.worlds.remove(w)
    for m in [m for m in bpy.data.materials if m.name.startswith("wx_")]:
        bpy.data.materials.remove(m)
    for g in [g for g in bpy.data.node_groups if g.name.startswith("wx_")]:
        bpy.data.node_groups.remove(g)
    for a in [a for a in bpy.data.actions if a.name.startswith("wx_") and a.users == 0]:
        bpy.data.actions.remove(a)
    if "wx_state" in sc.keys():
        del sc["wx_state"]
    _S = None


def current():
    """The active preset name ("day" when nothing is applied)."""
    _load()
    return _S["P"]["preset"] if _S else "day"


# ------------------------------------------------------------------ apply
def apply(preset, strength=1.0, seed=0, auto_spray=True, **kw):
    """Switch the scene to a preset (see the module doc). Returns the parameter dict that was applied, with counts.
    Optional keywords: visibility (m, overrides the preset), exposure, sun_elev (deg)."""
    global _S
    P = params(preset, strength, **kw)
    restore()
    if P["preset"] == "day":
        return P
    sc = bpy.context.scene
    sun = _sun()
    _S = {"P": P, "links": [], "emission_sampling": {}, "props": [], "beam_energy": {},
          "world": sc.world.name if sc.world else None,
          "sun": ({"name": sun.name, "energy": sun.data.energy, "color": tuple(sun.data.color),
                   "angle": sun.data.angle, "rot": tuple(sun.rotation_euler), "glossy": sun.visible_glossy}
                  if sun else None),
          "view": {"exposure": sc.view_settings.exposure},
          "cycles": {"transparent_max_bounces": sc.cycles.transparent_max_bounces,
                     "sample_clamp_indirect": sc.cycles.sample_clamp_indirect,
                     "volume_biased": sc.cycles.volume_biased, "volume_step_rate": sc.cycles.volume_step_rate,
                     "volume_max_steps": sc.cycles.volume_max_steps},
          "comp": sc.compositing_node_group.name if sc.compositing_node_group else None}
    kind = _stage_kind()
    # ---- sun / moon
    to_sun = Vector((0.4, -0.6, 0.5)).normalized()
    if sun:
        to_sun = _to_sun(sun)
        az = math.atan2(to_sun.y, to_sun.x)
        if P["sun_azimuth"] is not None and P["sun_elev"] is None:
            P["sun_elev"] = math.degrees(math.asin(max(-1.0, min(1.0, to_sun.z))))
        if P["sun_elev"] is not None:
            e = math.radians(P["sun_elev"])
            a = az + math.radians(P["sun_az"])
            if P["sun_azimuth"] is not None:
                a = math.radians(P["sun_azimuth"])
            to_sun = Vector((math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)))
            sun.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler()
        if P["sun_energy"] is not None:
            sun.data.energy = P["sun_energy"]
        if P["sun_col"] is not None:
            sun.data.color = P["sun_col"]
        if P["sun_angle"] is not None:
            sun.data.angle = math.radians(P["sun_angle"])
        sun.visible_glossy = bool(P["sun_glossy"])
    # ---- sky
    sc.world = _build_world(P, to_sun, to_sun)
    # ---- global controls
    V = P["V"] or 7800.0
    _ctl_set(Wet=P["wet"], Rain=min(1.0, P["rain"]), Snow=min(1.0, P["snow"]), Ice=min(1.0, P["ice"]),
             Frost=min(1.0, P["frost"]), Leafless=P["leafless"], Retro=P["retro"], Lamps=P["lamps"],
             Windows=P["windows"], WinFrac=0.42 if P["night"] >= 1 else 0.3, Lights=P["lights"],
             HeadGain=P["head"], TailGain=P["tail"], HazeNegDist=-haze_distance(V), SeedOff=seed * 37.1,
             WetRough=0.13, RainAlpha=0.6 if P["night"] < 1 else 0.45, SnowAlpha=1.0, HazeColor=P["haze"])
    counts = _treat_materials(kind)
    # ---- render settings that weather needs
    sc.view_settings.exposure = _S["view"]["exposure"] + P["exposure"]
    if P["rain"] > 0 or P["snowfall"] > 0 or P["wet"] >= 0.5:
        sc.cycles.transparent_max_bounces = max(sc.cycles.transparent_max_bounces, 24)
    if P["night"] > 0 or P["lights"] > 0:
        sc.cycles.sample_clamp_indirect = 8.0 if sc.cycles.sample_clamp_indirect in (0.0,) else min(
            sc.cycles.sample_clamp_indirect, 8.0)
    comp = _compositor(P)
    if comp:
        sc.compositing_node_group = comp
    # ---- lamps
    lamps = []
    if P["lamps"] > 0:
        col = _wx_coll()
        for o in list(sc.objects):
            if o.name.startswith("lamp_lens"):
                ld = bpy.data.lights.new(f"wx_lamp_{len(lamps)}", "SPOT")
                ld.energy = P["lamp_w"] * P["lamps"]
                ld.color = (1.0, 0.8, 0.58)
                ld.spot_size = math.radians(118)
                ld.spot_blend = 0.45
                ld.shadow_soft_size = 0.25
                lo = bpy.data.objects.new(ld.name, ld)
                col.objects.link(lo)
                lo.location = o.matrix_world.translation - Vector((0, 0, 0.06))
                lamps.append(lo)
    # ---- vehicles: lights, spray
    veh = vehicles()
    lit, sprays = 0, []
    for o, moving in veh:
        if not moving:
            continue
        if "wx_moving" not in o.keys():
            o["wx_moving"] = 1.0
            _S["props"].append(o.name)
        _motion_lights(o, P["lights"] > 0)
        glow = (10.0 if P["night"] >= 1 else 45.0) if (P["rain"] > 0 or P["V"] and P["V"] < 400) else 0.0
        if P["lights"] > 0 and P["beam_w"] > 0:
            headlights(o, True, power=P["beam_w"], tail_glow=glow)
            lit += 1
        elif glow:
            tail_glow(o, glow)
        wet_spray = P["wet"] >= 0.5 and P["rain"] > 0
        if auto_spray and wet_spray:      # snow: powder plume only on request (spray(obj, strength=0.45)), cost
            anim = bool(o.animation_data and o.animation_data.action)
            fr = range(sc.frame_start, sc.frame_end + 1) if anim else None
            sp = 25.0 if (kind == "autobahn" and not anim) else (12.0 if not anim else None)
            sprays.append(spray(o, frames=fr, speed=sp, strength=min(1.0, P["wet"]), seed=seed))
    if len(sprays) > BUDGET["spray_boxes"]:          # keep the nearest ones to the camera (render cost)
        cam = sc.camera
        if cam:
            sprays.sort(key=lambda o: (o.parent.matrix_world.translation - cam.matrix_world.translation).length)
        for o in sprays[BUDGET["spray_boxes"]:]:
            me = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.meshes.remove(me)
        sprays = sprays[:BUDGET["spray_boxes"]]
    if sprays:
        # biased ray-marched volumes: 50x cheaper than the unbiased default for this soft mist (measured 0.6 s vs 32 s)
        _spray_volumes()
    # ---- falling rain / snow
    pre = []
    if P["rain"] > 0:
        pre.append(_precip("rain", P, seed))
    if P["snowfall"] > 0:
        pre.append(_precip("snow", P, seed))
    P["counts"] = dict(counts, lamps=len(lamps), vehicles=len(veh), lit=lit, sprays=len(sprays),
                       precip={o.name: o["wx_count"] for o in pre})
    P["stage"] = kind
    _save()
    return P
