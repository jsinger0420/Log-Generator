# Log Generator

A Blender 4.5+ add-on that builds model railroad logs: sawn to length with the limbs trimmed off, realistic bark for 20 North American lumber species, taper from butt to top, an optional flared butt where the trunk widens into the roots, and end grain (growth rings, heartwood and sapwood) on the cut faces. Make one log for the sawmill carriage, a stacked load for a log car or mill deck, or a pond full of floating logs. Logs are closed meshes, so they export as STL in millimetres for 3D printing.

## Requirements

- Blender 4.5 or later. Nothing else.

## Install

1. In Blender, open Edit > Preferences > Get Extensions, choose "Install from Disk" in the menu at the top right, and pick `log_generator-0.1.0.zip`.
2. Open the 3D Viewport sidebar (N) and the **Logs** tab.

## Use

1. **Species and Size:** pick a species (softwoods: Douglas fir, ponderosa, eastern white and southern yellow pine, coast redwood, western red cedar, Sitka spruce, western hemlock, bald cypress; hardwoods: red and white oak, sugar maple, white ash, yellow poplar, black cherry, American chestnut, shagbark hickory, beech, paper birch, black walnut). **Use Typical Size** fills in a typical steam-era log of that species. Pick the scale (T through 1.5 in scale, including HO, N, S, O, On30, Sn3, G and Fn3, or a custom ratio). Then either:
   - **Prototype Size**: the real log's length (feet or metres) and butt diameter (inches or cm); the scale makes the model, or
   - **Model Size**: the model log's own length and diameter in mm or inches. The scale still sets how big the bark detail is.
   **Top Diameter** sets the taper (85 % means the small end is 85 % of the butt).
2. **Shape:** **Butt Flare** is the chance a log is a butt log with a flared, buttressed base (100 % = every log). Out of Round, Bow, Cut Limbs (sawn-off limbs with a raised collar and end grain on the stub), Limb Stub length, and how far the sawn ends are off square.
3. **Bark:** the species' bark style or another one, furrow depth, feature size, and how much bark has been knocked off in handling.
4. **Arrangement:**
   - **Single Log** lies along X, resting on the 3D cursor.
   - **Stacked Load** makes a pyramid on an empty at the 3D cursor (the car deck): logs side by side across the **Load Width**, each row resting in the row below, biggest at the bottom, alternate butts turned end for end, ends staggered. **Join for Printing** unions the load into one solid (logs sink into each other by **Overlap**).
   - **Log Pond** scatters logs over an area at the 3D cursor's height (the waterline), each floating as deep as its species' green weight says. Oak, maple, hickory and walnut are heavier than water and ride just awash. **Add Water Surface** adds a plane for renders.
   Loads and ponds vary each log's length and diameter by the percentages given.
5. **Generate Logs.** Every Generate adds new logs with a new random seed (shown in Build Options; lock it to repeat). Check the summary: model and prototype size, taper, board feet (Doyle and Scribner), bark relief in the model, triangle count, how many logs a load holds, and how high logs float.
6. **Export STL** writes the selected logs, loads or ponds (water left out) in millimetres, in one file or one each.

**Changing logs you made:** select them and press **Load Settings From Selected**, adjust, then **Regenerate Selected**. Lock the seed first to keep the same look. Whole setups can be saved as presets from the menu at the top.

**Detail:** Coarse (0.4 mm) for previews and big loads, Medium (0.15 mm) for renders and FDM, Fine (0.08 mm) for resin. Bark is drawn as finely as the detail allows; where real bark is finer than the mesh can show (small scales), its features are enlarged a little so it still reads as that species' bark rather than noise. Max Triangles per Log caps big logs at large scales.

## Materials

- **Log Bark**: one shared material; each log's bark colour (ridges, furrows, missing bark) is baked into its `Col` colour attribute, so it looks right at every scale and exports with colour-capable formats.
- **Log End Grain - species**: procedural growth rings (`Rings` UV map), heartwood and sapwood (`EndGrain` UV map), on sawn ends and limb stubs. Real rings are far too fine to see at model scale, so at most 22 are drawn across the radius.

Both are made on first use and reused, so you can edit them.

## Files

| File | What it does |
| --- | --- |
| `species.py` | The species table: bark, colours, typical sizes, flare, limbs, float. Plain Python |
| `scales.py` | Scales, unit conversion, log rules. Plain Python |
| `noise.py` | Seeded gradient, fBm and Worley noise in numpy |
| `bark.py` | The bark styles, resolution-aware |
| `logmesh.py` | One log as a closed mesh: taper, flare, bark, limbs, sawn ends. Plain Python + numpy |
| `arrange.py` | Stacked loads, pond scatter, float depth. Plain Python |
| `design.py` | Panel settings to per-log specs, summary. Plain Python |
| `build.py` | Makes the Blender objects, joins loads, stores settings, exports STL |
| `materials.py` | Bark, end grain and water materials |
| `properties.py`, `operators.py`, `ui.py` | Settings, buttons and the sidebar panel |
| `preset_store.py` | Saved log presets (JSON) |
| `tests/` | Unit tests for the plain-Python parts |

Run the tests without Blender from the folder that contains `log_generator`:

```
python -m unittest discover -s log_generator/tests -t .
```
