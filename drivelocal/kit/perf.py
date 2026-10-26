"""Render speed for Drive Like a Local on CPU runners (Cycles, 4 vCPU, no GPU), without changing the approved look.

apply(profile) sets the render levers of one profile and returns the settings it used:
  "final"    episode finals: 720p, 12 samples, motion blur as the scene asks (upscaled to 1080x1920 later)
  "preview"  QA previews: 360p, 6 samples, every 2nd frame, no motion blur
  "still"    look-dev stills (24 to 48 samples): only levers that leave every pixel's meaning alone
  "off"      exactly what stage.render_setup() gave before this module existed (the A/B baseline)
stage.render_setup() calls apply(auto(samples, res_x, res_y)) last; "--perf PROFILE" on the command line or DL_PERF
in the environment overrides the choice. Per-object and per-material levers (culling flags, deformation blur, haze
emission sampling) are applied again just before every render (only where a value differs, so persistent data is
kept), so objects and materials made after render_setup() are covered too. Every render prints one "PERF" line with
seconds per phase (DL_PERF_QUIET=1 silences it). Measurements and A/B frames: reports/perf.md.
"""
import os
import re
import sys
import time

import bpy

# what stage.render_setup() set before perf existed; every lever has its baseline value here
BASE = {
    "motion_blur": None,          # None: as the scene asked; False: off
    "deform_blur": True,          # Cycles per-object deformation blur (armature figures re-read at every step)
    "light_tree": True,
    "haze_emission": "AUTO",      # emission sampling of materials whose only emission is stage.hazify_all's haze
    "cull": None,                 # (camera_cull_margin, distance_cull_margin m): culled when outside the widened
                                  # frustum AND farther than the distance (near objects keep shadows and reflections)
    "adaptive": (0.02, 0),        # (threshold, min samples)
    "denoise": ("RGB_ALBEDO_NORMAL", "ACCURATE", "HIGH"),     # (input passes, prefilter, quality)
    "png": 15,                    # PNG compression
    "seed": 0,
    "subdiv": None,               # None: render levels as built; n: Simplify caps render subdivision at n
}
LEVERS = {
    "cull": {"cull": (0.25, 150.0)},
    "haze": {"haze_emission": "NONE"},
    "lt": {"light_tree": False},
    "deform": {"deform_blur": False},
    "dnfast": {"denoise": ("RGB_ALBEDO_NORMAL", "FAST", "HIGH")},
    "dnbal": {"denoise": ("RGB_ALBEDO_NORMAL", "ACCURATE", "BALANCED")},
    "noadapt": {"adaptive": (None, 0)},
    "png": {"png": 0},
    "mboff": {"motion_blur": False},
    "subdiv1": {"subdiv": 1},
    "seed": {"seed": 1},          # same settings, other noise: the noise floor for the A/B comparisons
}
PROFILES = {
    "off": {},
    "final": {"haze_emission": "NONE", "cull": (0.25, 150.0), "deform_blur": False, "png": 0},
    "preview": {"motion_blur": False, "haze_emission": "NONE", "cull": (0.25, 150.0), "deform_blur": False, "png": 0},
    "still": {"haze_emission": "NONE", "cull": (0.25, 150.0), "png": 0},
}

_S = {"cfg": None, "key": None, "hazed": set(), "tag": "", "handlers": False, "t_pre": None, "t_post": None,
      "last": None, "acc": {}, "n": 0, "prep": 0.0, "save": 0.0, "log": []}


def override():
    """Profile named by --perf or DL_PERF, else None."""
    a = sys.argv
    for i, x in enumerate(a[:-1]):
        if x == "--perf":
            return a[i + 1]
    return os.environ.get("DL_PERF") or None


def auto(samples, res_x, res_y):
    """The profile a render_setup() call stands for: 360p is a preview, 12 to 16 samples a final, more a still."""
    o = override()
    if o:
        return o
    if min(res_x, res_y) <= 400:
        return "preview"
    return "final" if samples <= 16 else "still"


def config(profile="final", **extra):
    cfg = dict(BASE)
    for part in str(profile).split("+"):
        if part in PROFILES:
            cfg.update(PROFILES[part])
        elif part in LEVERS:
            cfg.update(LEVERS[part])
        elif part not in ("", "base"):
            raise ValueError("perf: unknown profile or lever " + part)
    cfg.update(extra)
    return cfg


def _set(obj, attr, val):
    """Set only when different: an RNA write tags the datablock and would make Cycles re-sync it."""
    if getattr(obj, attr) != val:
        setattr(obj, attr, val)


def apply(profile="final", **extra):
    """Set the scene-wide levers of `profile` ("final", "preview", "still", "off"; levers can be added with "+",
    e.g. "off+haze") and arm the per-render pass for object and material levers. Returns the settings dict."""
    sc = bpy.context.scene
    cfg = config(profile, **extra)
    c, r = sc.cycles, sc.render
    _set(c, "use_light_tree", cfg["light_tree"])
    thr, mins = cfg["adaptive"]
    _set(c, "use_adaptive_sampling", thr is not None)
    if thr is not None:
        _set(c, "adaptive_threshold", thr)
    _set(c, "adaptive_min_samples", mins)
    inp, pre, qual = cfg["denoise"]
    _set(c, "denoising_input_passes", inp)
    _set(c, "denoising_prefilter", pre)
    _set(c, "denoising_quality", qual)
    _set(r.image_settings, "compression", cfg["png"])
    _set(c, "seed", cfg["seed"])
    cull = cfg["cull"]
    _set(c, "use_camera_cull", cull is not None)
    _set(c, "use_distance_cull", cull is not None)
    if cull is not None:
        _set(c, "camera_cull_margin", cull[0])
        _set(c, "distance_cull_margin", cull[1])
    _set(r, "use_simplify", cfg["subdiv"] is not None)
    if cfg["subdiv"] is not None:
        _set(r, "simplify_subdivision_render", cfg["subdiv"])
    cfg["profile"] = profile
    _S["cfg"], _S["key"] = cfg, None
    _hooks()
    prepare()
    return cfg


def _haze_only(m):
    """True when the material's only emitter is the haze mix stage.hazify_all() put in front of its output."""
    nt = m.node_tree
    if not m.use_nodes or nt is None:
        return False
    ems = [n for n in nt.nodes if n.type == "EMISSION"]
    if len(ems) != 1:
        return False
    em = ems[0]
    outs = [lk.to_node for lk in em.outputs[0].links]
    if len(outs) != 1 or outs[0].type != "MIX_SHADER" or not outs[0].inputs[0].links:
        return False
    fac = outs[0].inputs[0].links[0].from_node
    if fac.type != "MATH" or fac.operation != "SUBTRACT":
        return False
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            s = n.inputs.get("Emission Strength")
            col = n.inputs.get("Emission Color")
            if s is not None and (s.is_linked or s.default_value > 0) and col is not None and \
                    (col.is_linked or max(col.default_value[:3]) > 0):
                return False
        if n.type in ("BACKGROUND", "GROUP"):
            return False
    return True


def prepare():
    """Per-object and per-material levers; cheap when nothing changed since the last call."""
    cfg = _S["cfg"]
    if cfg is None:
        return
    t0 = time.perf_counter()
    sc = bpy.context.scene
    key = (tuple(sorted((k, str(v)) for k, v in cfg.items())), len(bpy.data.objects), len(bpy.data.materials))
    if cfg["motion_blur"] is False:
        _set(sc.render, "use_motion_blur", False)
    if key != _S["key"]:
        cull = cfg["cull"] is not None
        for o in bpy.data.objects:
            if o.type in ("CAMERA", "LIGHT", "LIGHT_PROBE", "SPEAKER", "ARMATURE"):
                continue
            oc = o.cycles
            _set(oc, "use_camera_cull", cull)
            _set(oc, "use_distance_cull", cull)
            _set(oc, "use_deform_motion", cfg["deform_blur"])
        want = cfg["haze_emission"]
        for m in bpy.data.materials:
            if want != "AUTO":
                if m.cycles.emission_sampling == "AUTO" and _haze_only(m):
                    m.cycles.emission_sampling = want
                    _S["hazed"].add(m.name)
            elif m.name in _S["hazed"]:
                _set(m.cycles, "emission_sampling", "AUTO")
        if want == "AUTO":
            _S["hazed"].clear()
        _S["key"] = key
    _S["prep"] += time.perf_counter() - t0


# ------------------------------------------------------------------ timing
_PHASES = (("sync", ("Synchroniz",)), ("bvh", ("BVH",)), ("light", ("Light", "Lookup", "Background")),
           ("trace", ("Sample", "Rendering", "Path Trac")), ("denoise", ("Denois",)),
           ("geom", ("Meshes", "Geometry", "Objects", "Particle", "Primitive", "Attributes", "Displacement",
                     "Hair", "Curves", "Points", "Volume", "Images", "Shaders")))


def _label(s):
    parts = [p.strip() for p in s.split("|")]
    keep = [p for p in parts if p and not p.startswith(("Fra:", "Mem:", "Remaining:", "Time:", "Peak", "Scene"))]
    lab = keep[0] if keep else (parts[-1] if parts else "")
    m = re.match(r"Sample (\d+)/(\d+)", lab)
    if m and m.group(1) == m.group(2):
        return "Denoise (after the last sample)"       # Cycles shows "Sample N/N" while OIDN runs
    return re.sub(r"\s*\d+/\d+.*$", "", lab)[:48]


def _phase(lab):
    for name, keys in _PHASES:
        if any(k in lab for k in keys):
            return name
    return "other"


def tag(text):
    """Label the next renders' PERF lines (ld_perf.py names the variant and frame)."""
    _S["tag"] = text


def _close(now):
    if _S["last"] is not None:
        lab, t = _S["last"]
        _S["acc"][lab] = _S["acc"].get(lab, 0.0) + now - t


def _on_pre(*_a):
    now = time.perf_counter()
    gap = now - _S["t_post"] if _S["t_post"] else None
    _S["prep"] = 0.0
    prepare()
    _S.update(t_pre=now, gap=gap, last=("(blender pre)", time.perf_counter()), acc={}, save=0.0)


def _on_stats(*a):
    if _S["t_pre"] is None or not a:
        return
    s = str(a[0])
    now = time.perf_counter()
    if os.environ.get("DL_PERF_DEBUG"):
        print("PERF_STAT", round(now - _S["t_pre"], 3), s[:150], flush=True)
    m = re.search(r"Saving:\s*(\d+):(\d+\.\d+)", s)
    if m:
        _S["save"] = int(m.group(1)) * 60 + float(m.group(2))
    lab = _label(s)
    if _S["last"] and lab == _S["last"][0]:
        return
    _close(now)
    _S["last"] = (lab, now)


def _on_post(*_a):
    if _S["t_pre"] is None:
        return
    now = time.perf_counter()
    _close(now)
    total = now - _S["t_pre"]
    ph = {}
    for lab, d in _S["acc"].items():
        k = "pre" if lab == "(blender pre)" else ("save" if lab in ("Finished", "") else _phase(lab))
        ph[k] = ph.get(k, 0.0) + d
    sc = bpy.context.scene
    rec = {"tag": _S["tag"], "frame": sc.frame_current, "total": total, "gap": _S.get("gap"), "prep": _S["prep"],
           "save": _S["save"], "phases": ph, "raw": dict(_S["acc"])}
    _S["log"].append(rec)
    _S["n"] += 1
    _S["t_post"], _S["t_pre"], _S["last"] = now, None, None
    if not os.environ.get("DL_PERF_QUIET"):
        print(line(rec), flush=True)
        if _S["n"] <= 2 or os.environ.get("DL_PERF_RAW"):
            top = sorted(rec["raw"].items(), key=lambda kv: -kv[1])[:9]
            print("PERF_RAW " + "; ".join(f"{k} {v:.2f}" for k, v in top), flush=True)


def line(rec):
    ph = rec["phases"]
    order = ("pre", "sync", "geom", "bvh", "light", "trace", "denoise", "save", "other")
    body = " ".join(f"{k}={ph[k]:.2f}" for k in order if ph.get(k, 0) >= 0.005)
    gap = f" gap={rec['gap']:.2f}" if rec.get("gap") is not None else ""
    return f"PERF {rec['tag'] or '-'} f={rec['frame']} total={rec['total']:.2f}{gap} prep={rec['prep']:.2f} | {body}"


def records():
    return list(_S["log"])


def _hooks():
    if _S["handlers"]:
        return
    H = bpy.app.handlers
    for fn, lst in ((_on_pre, H.render_pre), (_on_stats, H.render_stats), (_on_post, H.render_post)):
        fn = bpy.app.handlers.persistent(fn)
        lst.append(fn)
    _S["handlers"] = True
