"""Render-time profiling for any Drive Like a Local scene on the lookdev runners (kit/perf.py levers).
Runs the scene script unchanged; every render the scene asks for is replaced by a sweep: for each variant, `--span`
consecutive frames from that frame on, each timed per phase (one "PERF" line per render, a "SWEEP" table at the end).
The middle frame of every variant is kept as f_NNNN_<variant>.png for the A/B comparison; the others go to a temp dir.
Variants are kit/perf.py profiles and levers joined with "+": "off" (the old settings), "off+haze", "final", ...
Run: python lookdev/ld_perf.py OUT --stills 30 --res 720 --samples 12 --assets ASSETS --scene lookdev/ld_figures.py
     --sweep off,off+seed,off+haze,final --span 3 [scene args such as --shot zebra]
"""
import os
import runpy
import statistics
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path[:0] = [os.path.join(ROOT, "kit")]

import bpy  # noqa: E402

import perf  # noqa: E402


def arg(name, default=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a[:-1] else default


SCENE = os.path.join(ROOT, arg("--scene"))
SWEEP = arg("--sweep", "off,final").split(",")
SPAN = int(arg("--span", "3"))
OUT = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "frames"
TMP = tempfile.mkdtemp(prefix="perf_")
_real = bpy.ops.render
RESULTS = {}
T_START = time.time()


def scene_stats():
    dg = bpy.context.evaluated_depsgraph_get()
    n_inst = sum(1 for _ in dg.object_instances)
    anim = sum(1 for o in bpy.data.objects if o.animation_data and o.animation_data.action)
    emis = sum(1 for m in bpy.data.materials if m.cycles.emission_sampling != "NONE")
    haze = sum(1 for m in bpy.data.materials if perf._haze_only(m))
    sc = bpy.context.scene
    print(f"PERF_SCENE objects={len(bpy.data.objects)} instances={n_inst} animated={anim} materials="
          f"{len(bpy.data.materials)} emissive_sampled={emis} haze_only={haze} meshes={len(bpy.data.meshes)} "
          f"res={sc.render.resolution_x}x{sc.render.resolution_y} samples={sc.cycles.samples} "
          f"blur={sc.render.use_motion_blur} shutter={sc.render.motion_blur_shutter:.2f} "
          f"threads={sc.render.threads} built_at={time.time() - T_START:.1f}s", flush=True)


def render(*_a, **_kw):
    sc = bpy.context.scene
    f0 = sc.frame_current
    blur0 = sc.render.use_motion_blur
    if not RESULTS:
        scene_stats()
    for v in SWEEP:
        sc.render.use_motion_blur = blur0
        perf.apply(v)
        for k in range(SPAN):
            f = f0 + k
            t = time.perf_counter()
            sc.frame_set(f)
            fs = time.perf_counter() - t
            keep = k == SPAN // 2
            sc.render.filepath = os.path.join(OUT if keep else TMP, f"f_{f:04d}_{v.replace('+', '-')}.png")
            perf.tag(f"{v} k={k} fs={fs:.2f}")
            _real.render(write_still=True)
            rec = perf.records()[-1]
            RESULTS.setdefault(v, []).append((k, rec["total"] + fs, rec))
    sc.render.use_motion_blur = blur0
    sc.frame_set(f0)
    summary()
    return {"FINISHED"}


def summary():
    print("SWEEP variant | first | steady (frames 2+) | trace | sync+geom+bvh+light | denoise | save | pre", flush=True)
    for v, rows in RESULTS.items():
        st = [r for r in rows if r[0] > 0] or rows

        def m(key):
            return statistics.mean(r[2]["phases"].get(key, 0.0) for r in st)
        upd = sum(m(k) for k in ("sync", "geom", "bvh", "light", "other"))
        print(f"SWEEP {v} | {rows[0][1]:.2f} | {statistics.mean(r[1] for r in st):.2f} | {m('trace'):.2f} | "
              f"{upd:.2f} | {m('denoise'):.2f} | {m('save'):.2f} | {m('pre'):.2f}", flush=True)


class _RenderOps:
    def __getattr__(self, name):
        return render if name == "render" else getattr(_real, name)


bpy.ops.render = _RenderOps()
sys.argv = [SCENE] + sys.argv[1:]
os.environ["DL_PERF"] = "off"        # render_setup keeps the scene's own settings; every variant applies its own
t0 = time.time()
runpy.run_path(SCENE, run_name="__main__")
print("PERF_DONE wall", round(time.time() - t0, 1), "s", flush=True)
