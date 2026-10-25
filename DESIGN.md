# Log Generator — Design

Blender add-on (extension) that generates 3D models of logs for model railroads: logs for log cars, half logs to float on painted water, and logs for the sawmill. Owner: John Singer (john@singerlinks.com).

- **Current version:** 0.3.2
- **Source and Git repo:** `C:\Users\Jsing\BLENDERWORKBENCHES\LOG` (branch `main`). The package is in `log_generator\`; installable zips (`log_generator-0.x.0.zip`) are committed at the repo root; sample renders are in `samples\`.
- **Install:** Blender → Edit → Preferences → Get Extensions → Install from Disk → the latest zip. Panel: 3D Viewport sidebar (N) → **Logs** tab.
- **Blender:** manifest minimum 4.5.0. Tested with Blender 5.1 run as a Python module (`pip install bpy`), headless; not yet tried in a normal Blender window or in 4.5.
- **Model:** follows the conventions of John's Tie Strip Generator (`C:\Users\Jsing\BLENDERWORKBENCHES\TIESTRIP`): sidebar panel, Generate / Regenerate Selected / Load Settings From Selected / Export STL, saved presets, lockable seed, busy cursor while building, pure-Python core with unit tests, docstring on everything, zips committed to the repo.

## Requirements (from John)

1. Generate 3D logs for model railroads: loads on log cars, floating in a log pond, on the sawmill.
2. Size in real-world dimensions plus a scale; the scale picker includes all the usual model railroad scales. Alternatively the user enters the model log's actual size.
3. A variety of lumber species (oak, pine, etc.).
4. Realistic bark; both ends sawn off; limbs cut off so it's just a log.
5. Some logs have part of the tree's base where it widens out (butt flare).
6. Logs taper from end to end.
7. *(v0.2)* The log pond scatter doesn't work for modellers: they need a **half log** to place on a flat surface painted as water.
8. *(v0.2)* Generate **multiple logs**, each somewhat unique within the settings; **each log a separate object** for export.
9. *(v0.2)* Car loads: user sets the **log car width** (real-world or model size); **longest logs on the bottom** of the pile.
10. *(v0.2)* Growth ring detail on the ends must be visible.
11. *(v0.3)* Logs are **hollow**, user sets the **wall thickness**, default **1 mm**.

## Architecture

Pure-Python core (numpy, no `bpy`, unit-tested outside Blender) plus a thin Blender layer.

| Module | Role |
| --- | --- |
| `scales.py` | Scale table (T 1:450 to 1.5 in 1:8, incl. N, HO/HOn3, OO, S/Sn3, O/On3/On30 1:48, O 1:43.5/1:45, Gauge 1, G 1:22.5, Fn3 1:20.3, 7/8 in, custom), unit conversion (ft/in, m/cm, model mm/in), Doyle and Scribner log rules |
| `species.py` | 20 species: bark style, feature size, stretch, furrow depth, bark thickness, colours (ridge, furrow, inner bark, sapwood, heartwood), heartwood share, ring width, flare and lobes, limbs per metre, limb size, bow, green specific gravity, typical size |
| `noise.py` | Seeded 3D gradient noise, fBm, Worley (F1, F2, cell id) in numpy |
| `bark.py` | One function per bark style; resolution-aware (see below) |
| `logmesh.py` | `LogSpec` → `LogMesh`: one closed log mesh with materials per face, vertex colours, two UV maps, optional hollow inside |
| `arrange.py` | Car-load pyramid, row layout, float depth / share above water |
| `design.py` | `Design` (panel settings in fixed units) → one `LogSpec` per log with per-log variation; panel summary; hollow estimate |
| `materials.py` | "Log Bark" (vertex-colour driven, shared) and "Log End Grain - <species>" (procedural rings) |
| `build.py` | Blender objects, arrangements, Boolean cuts (half logs, drain holes, joined loads), stored settings, regenerate, STL export |
| `properties.py` | All settings on `scene.log_generator`, unit conversion on change, presets, legacy mapping |
| `operators.py`, `ui.py` | Buttons and panels (Log Generator, Species and Size, Shape, Bark, Arrangement, Hollow, Build Options) |
| `preset_store.py` | Log presets as JSON in the extension's user folder |
| `tests/test_logs.py` | 34 unit tests for the pure-Python parts |

Run tests from the repo root: `python -m unittest discover -s log_generator/tests -t .`

## How a log is built (`logmesh.build`)

Log lies along +X from x = 0 (butt) to x = length, axis on X. All sizes are model mm unless suffixed `_real`.

1. **Grid**: rings along × points round (`resolution()`), within the triangle budget (Max Triangles per Log, default 400k).
2. **Outer bark envelope**: linear taper butt → top (`Top Diameter %`); flared butt = exponential swell over about 1.5 diameters with root-buttress lobes (`(0.5+0.5cos kθ)^1.5`, uneven); ovality; low-frequency lumpiness.
3. **Bark relief**: `bark.surface()` returns height 0–1 and tone; radius = envelope − depth·(1−h). Depth is capped at 0.85 × bark thickness. Bark is sampled on a cylinder in **full-size mm** (seamless and scale-independent), stretched along the log by the species' `bark_stretch`.
4. **Missing bark**: noise mask at an exact quantile (the Missing Bark %) drops to the wood; weathered sapwood colour.
5. **Cut limbs**: Poisson count by limbs/m (fewer on a flared butt, none near the ends). Each is a raised bark collar round a flat sawn stub face (end-grain material, its own rings).
6. **Bow**: sine-shaped offset of the axis in a random direction.
7. **Sawn ends**: planes tilted up to End Cut Angle; optional saw roughness. Each end face is a polar disc: outer ring = bark outline (bark material band), wood-edge ring, rings in to an off-centre pith (end grain).
8. **Growth rings**: years from the pith, wobbled by noise, stored in the `Rings` UV map (length = rings) and baked into vertex colours (heartwood/sapwood + darker latewood). `EndGrain` UV = offset as a share of the wood radius (heartwood boundary). Drawn ring count is capped at 22 across the radius (real rings are invisible at model scale). **Carved Growth Rings** option: end-face grooves (earlywood worn down, latewood ridges), count and depth set by the user, 8 face rings per carved ring; drawn and baked rings follow the carved ones.
9. **Hollow** (default on): a coarse inner cavity surface (`_cavity`) kept at least `wall` inside the wood surface everywhere (local minimum over neighbouring points and rows) and `wall` + carve depth + roughness behind each tilted sawn end, following the bow. Faces point into the cavity. If the cavity radius would be under 0.3 mm or too short, the log stays solid (`info["skipped"]`).

Output faces: material 0 = bark, 1 = end grain. Vertex colour attribute `Col` (linear RGBA). Mesh is closed (watertight), outward-facing.

### Resolution-aware bark (important)

A mesh can only show detail a few points wide; finer noise aliases into horizontal ledges (seen in early renders). So:
- Point spacing is chosen from the bark feature size (`design.spacing`: round = feature/8, along = feature × stretch/12, floored by Detail: Coarse 0.4 / Medium 0.15 / Fine 0.08 mm).
- `bark.surface()` gets the actual spacing; it drops fBm octaves and fine details the mesh can't show (`octaves()`, `shown()`), widens edges to ≥ 2 points, and if one feature is still under-resolved (res > 0.15) it **enlarges the bark features** so they read as that species' bark. At N/HO on Medium, bark is therefore somewhat larger than true scale; Fine detail is closer.

## Arrangements (`build.generate`)

- **Separate Logs** (`LOGS`): N logs side by side along Y (gap ½ the biggest radius) resting on the 3D cursor. One log → the log object is the root; several → an empty "Logs" holds "Logs 01", "Logs 02", … each its own object.
- **Car Load** (`STACK`): pyramid on an empty at the cursor (the car deck). Logs sorted **longest first** into the bottom row across the **Car Width** (real-world ft/m or model mm/in), each upper log resting tangent on two below. Alternate butts flipped, ends staggered, each log's roll baked into its mesh (so its drain hole faces down). **Join for Printing** unions them (logs overlap by Overlap, default 0.15 mm) with a Manifold Boolean.
- **Floating Half Logs** (`FLOAT`): each log cut flat at its waterline, flat face on the cursor, each its own object. Waterline = species (share above water from green specific gravity, min 15 %, max 85 %), Half Log, or Custom %. Solid logs: `bmesh.bisect_plane` + `holes_fill` + triangulate. Hollow logs: Boolean difference with a box, which **opens the cavity**, so the bottom is open (no drain needed); if the cut misses the cavity, a drain hole is cut through the flat bottom.
- With more than one log, each varies: length ± Length Variation, diameter ± Diameter Variation, taper ± 3 points, its own seed (bark, limbs, bow, ends), its own roll for butt flare.

**Drain hole**: hollow full logs get a vertical cylinder (default 1.5 mm, 0 = none) cut from the underside up to the cavity centre, halfway along.

**Booleans**: Manifold solver, falling back to Exact. After a Boolean, normals are **not** recalculated (that turned a closed cavity outward = filled) and cut results aren't vertex-merged (that pinched drain holes).

## Settings and storage

- Prototype sizes in ft/in or m/cm (`proto_units`), model sizes in mm/in (`model_units`); switching converts values; switching Size By carries the size across through the scale.
- **Use Typical Size** fills a species' typical steam-era log.
- Each generated root stores its settings as JSON (`log_generator_settings`) plus preset state; **Load Settings From Selected** / **Regenerate Selected** work as in Tie Strip (regenerate keeps name, transform, parent, collections; Lock Seed to keep the look).
- Presets: every setting, JSON files in the extension user folder. Presets from 0.1.0 map `SINGLE` → `LOGS` (count 1) and `POND` → `FLOAT`.
- **Export STL** (mm): select a group's empty for all its logs or individual logs; **One File per Log** on by default.
- Summary box: model and prototype size, taper (in/ft), board feet (Doyle, Scribner), bark relief in model mm, triangles per log, carved ring spacing, hollow saving or "too thin", car capacity, half-log height above water.

## Materials and viewing

- Bark colour is baked per vertex → one shared "Log Bark" material for all species and scales; exports with colour-capable formats.
- End grain is procedural per species. Rings show in **Material Preview / Rendered**; in **Solid** view set Color → Attribute (baked ring colours; clearest with carved rings). A .blend used with 0.1.0 has older end-grain materials with shader-side wobble; delete them once so rings line up with carved rings.

## Version history

- **0.1.0** — Initial add-on: 20 species, scales, prototype/model size, bark styles, flare, taper, limbs, sawn ends with rings, single log / stacked load / log pond scatter (with water plane), STL export, presets, regenerate/load settings.
- **0.2.0** — Pond scatter replaced by floating half logs; separate multi-log batches (each its own object, per-log variation); car width real or model; longest logs at the bottom; carved growth rings; ring colours baked into vertex colours; export per log.
- **0.3.0** — Hollow logs (default on, wall 1 mm), drain holes, open-bottomed hollow half logs; fix for normals being recalculated after Booleans.
- **0.3.1** — Packaging fix: the manifest tagline was 71 characters and Blender's extension installer allows 64, so 0.2.0 and 0.3.0 zips are rejected by Install from Disk. The zip is now built and validated with Blender's own extension tool (`blender_ext.py build` / `validate`, the same as `blender --command extension build`) and test-installed as an extension. No feature changes.
- **0.3.2** — Extensions platform review: removed the `Import-Export` tag (the add-on generates meshes; STL export alone doesn't make it an import/export add-on). Tags are now just `Add Mesh`. No feature changes.

## Packaging

Build the zip with Blender's extension tool from the repo root: `blender --command extension build --source-dir log_generator --output-dir .`, then `blender --command extension validate log_generator-<version>.zip`. It honours the manifest's `paths_exclude_pattern` (no tests, no `__pycache__`) and names the zip `log_generator-<version>.zip`. Manifest rules to remember: `tagline` at most 64 characters and not ending in punctuation; `tags` from Blender's list, and only ones that describe what the add-on is for (reviewers rejected `Import-Export`).

## Known limitations / ideas

- Not yet run in an interactive Blender window or in Blender 4.5.
- At small scales on Medium detail, bark features are enlarged to stay readable.
- A joined car load seals tiny internal pockets where neighbouring logs' bark touches (pre-existing; harmless for FDM, may hold drops of resin).
- Possible next steps: felling-cut step/hinge on butt ends, chains/binders and stakes on car loads, a GitHub remote for the repo.
