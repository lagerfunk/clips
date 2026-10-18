"""Download the CC0 / CC-BY assets for the Stick Facts videos into assets/ (runs on a GitHub runner, which can reach
Poly Haven; the Claude workspace cannot). Writes assets/LICENSES.md."""
import json
import os
import pathlib
import urllib.request

OUT = pathlib.Path("assets")
UA = {"User-Agent": "lagerfunk-stickfacts/1.0 (github.com/lagerfunk/clips)"}
CONF = json.load(open("stickman/assets.json"))


def get(url, dest):
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())
    print("got", dest, dest.stat().st_size)


def api(path):
    req = urllib.request.Request("https://api.polyhaven.com" + path, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


lic = ["# Asset licenses", "", "Poly Haven assets: CC0 (polyhaven.com/license).", ""]
for h in CONF["hdris"]:
    f = api(f"/files/{h}")["hdri"][CONF["hdri_res"]]["hdr"]
    get(f["url"], OUT / "hdri" / f"{h}.hdr")
    lic.append(f"- HDRI {h}: CC0, Poly Haven")
for t in CONF["textures"]:
    files = api(f"/files/{t}")
    for m in ("Diffuse", "nor_gl", "Rough", "AO", "Displacement"):
        if m in files and CONF["tex_res"] in files[m]:
            fm = files[m][CONF["tex_res"]]
            fmt = "jpg" if "jpg" in fm else ("png" if "png" in fm else list(fm)[0])
            get(fm[fmt]["url"], OUT / "textures" / t / f"{m}.{fmt}")
    lic.append(f"- Texture {t}: CC0, Poly Haven")
for cat in CONF.get("texture_categories", []):
    found = api(f"/assets?type=textures&categories={cat}")
    (OUT / "textures").mkdir(parents=True, exist_ok=True)
    json.dump(sorted(found), open(OUT / "textures" / f"_list_{cat}.json", "w"), indent=0)
for m in CONF["models"]:
    files = api(f"/files/{m}")
    g = files["gltf"][CONF["model_res"]]["gltf"]
    get(g["url"], OUT / "models" / m / os.path.basename(g["url"]))
    for rel, inc in g.get("include", {}).items():
        get(inc["url"], OUT / "models" / m / rel)
    lic.append(f"- Model {m}: CC0, Poly Haven")
for name, url, note in CONF["direct"]:
    get(url, OUT / name)
    lic.append(f"- {name}: {note}")
open(OUT / "LICENSES.md", "w").write("\n".join(lic) + "\n")
print("done")
