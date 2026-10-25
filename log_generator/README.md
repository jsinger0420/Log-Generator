# Log Generator

A Blender 4.5+ add-on that builds model railroad logs: sawn to length with the limbs trimmed off, realistic bark for 20 North American lumber species, taper from butt to top, an optional flared butt where the trunk widens into the roots, and end grain (growth rings, heartwood and sapwood) on the cut faces. Make one log for the sawmill carriage or a batch of logs that each look a little different, a stacked load for a log car or mill deck, or half logs cut at the waterline to stand on a surface painted as water. Logs are closed meshes, so they export as STL in millimetres for 3D printing.

## Requirements

- Blender 4.5 or later. Nothing else.

## Install

1. In Blender, open Edit > Preferences > Get Extensions, choose "Install from Disk" in the menu at the top right, and pick `log_generator-0.3.2.zip`.
2. Open the 3D Viewport sidebar (N) and the **Logs** tab.

## Use

1. **Species and Size:** pick a species (softwoods: Douglas fir, ponderosa, eastern white and southern yellow pine, coast redwood, western red cedar, Sitka spruce, western hemlock, bald cypress; hardwoods: red and white oak, sugar maple, white ash, yellow poplar, black cherry, American chestnut, shagbark hickory, beech, paper birch, black walnut). **Use Typical Size** fills in a typical steam-era log of that species. Pick the scale (T through 1.5 in scale, including HO, N, S, O, On30, Sn3, G and Fn3, or a custom ratio). Then either:
   - **Prototype Size**: the real log's length (feet or metres) and butt diameter (inches or cm); the scale makes the model, or
   - **Model Size**: the model log's own length and diameter in mm or inches. The scale still sets how big the bark detail is.
   **Top Diameter** sets the taper (85 % means the small end is 85 % of the butt).
2. **Shape:** **Butt Flare** is the chance a log is a butt log with a flared, buttressed base (100 % = every log). Out of Round, Bow, Cut Limbs (sawn-off limbs with a raised collar and end grain on the stub), Limb Stub length, and how far the sawn ends are off square. **Carved Growth Rings** cuts the rings into the sawn ends as shallow grooves, like weathered end grain, so they show on a print and catch a drybrush; set how many rings and how deep (0.03 mm shows on resin, FDM needs about 0.1 mm).
3. **Bark:** the species' bark style or another one, furrow depth, feature size, and how much bark has been knocked off in handling.
4. **Arrangement** and **Number of Logs**. With more than one log, each is a little different: length and diameter within the variation percentages, taper, bark, limbs, bow, end cuts, and its own chance of a flared butt.
   - **Separate Logs** lie side by side along Y on the 3D cursor. Several logs are held by an empty ("Logs"), but each log is its own object (Logs 01, Logs 02, ...).
   - **Car Load** makes a pyramid on an empty at the 3D cursor (the car deck): logs side by side across the **Car Width**, each row resting in the row below, the **longest logs on the bottom**, alternate butts turned end for end, ends staggered. Give the car width at real size (feet or metres) or as the model car's width (mm or inches). **Join for Printing** unions the load into one solid (logs sink into each other by **Overlap**); otherwise each log is its own object.
   - **Floating Half Logs** cuts each log flat at its waterline and closes the cut, so the flat face stands on the 3D cursor, ready to glue onto a flat surface painted as water. The **Waterline** is the species' own (a green Douglas fir shows about 40 % of its diameter, cedar more, oak barely floats; every log keeps at least 15 % so it prints), **Half Log**, or a **Custom** percentage. Each half log is its own object.
5. **Hollow** (on by default) leaves the inside of each log empty to save resin or filament. **Wall Thickness** (default 1 mm) is the least thickness of wood and bark anywhere: under the deepest bark furrow, and behind each sawn end (plus any carved rings and saw roughness). Full logs get a **Drain Hole** (default 1.5 mm, 0 for none) on the underside halfway along, so resin drains out; in a car load each log's hole faces down. Half logs need none: the waterline cut leaves their bottom open into the hollow. Logs too thin for the wall are made solid, and the summary and a warning say so. The summary also shows about how much material hollowing saves.
6. **Generate Logs.** Every Generate adds new logs with a new random seed (shown in Build Options; lock it to repeat). Check the summary: model and prototype size, taper, board feet (Doyle and Scribner), bark relief in the model, carved ring spacing, triangle count, how many logs fit on the car, and how much of a half log shows above the water.
7. **Export STL** writes the selected logs in millimetres. Select a group's empty to export all its logs, or click single logs to export just those. **One File per Log** (on by default) writes each log to its own file, named after the file name plus the log's name.

**Changing logs you made:** select them and press **Load Settings From Selected**, adjust, then **Regenerate Selected**. Lock the seed first to keep the same look. Whole setups can be saved as presets from the menu at the top.

**Detail:** Coarse (0.4 mm) for previews and big loads, Medium (0.15 mm) for renders and FDM, Fine (0.08 mm) for resin. Bark is drawn as finely as the detail allows; where real bark is finer than the mesh can show (small scales), its features are enlarged a little so it still reads as that species' bark rather than noise. Max Triangles per Log caps big logs at large scales.

## Materials

- **Log Bark**: one shared material; each log's bark colour (ridges, furrows, missing bark) is baked into its `Col` colour attribute, so it looks right at every scale and exports with colour-capable formats.
- **Log End Grain - species**: procedural growth rings (`Rings` UV map), heartwood and sapwood (`EndGrain` UV map), on sawn ends and limb stubs. Real rings are far too fine to see at model scale, so at most 22 are drawn across the radius (or the carved ring count, so drawn and carved rings line up).

**Seeing the rings:** Blender's Solid view shows each material as one flat colour, so the rings don't show there. Switch the viewport to Material Preview or Rendered (Z key), or in Solid view set Viewport Shading > Color to **Attribute**: the ring colours are also baked into the mesh colours, and show clearly when the rings are carved.

Both are made on first use and reused, so you can edit them.

## Files

| File | What it does |
| --- | --- |
| `species.py` | The species table: bark, colours, typical sizes, flare, limbs, float. Plain Python |
| `scales.py` | Scales, unit conversion, log rules. Plain Python |
| `noise.py` | Seeded gradient, fBm and Worley noise in numpy |
| `bark.py` | The bark styles, resolution-aware |
| `logmesh.py` | One log as a closed mesh: taper, flare, bark, limbs, sawn ends, hollow inside. Plain Python + numpy |
| `arrange.py` | Car loads, rows, how high logs float. Plain Python |
| `design.py` | Panel settings to per-log specs, summary. Plain Python |
| `build.py` | Makes the Blender objects, joins loads, cuts half logs and drain holes, stores settings, exports STL |
| `materials.py` | Bark and end grain materials |
| `properties.py`, `operators.py`, `ui.py` | Settings, buttons and the sidebar panel |
| `preset_store.py` | Saved log presets (JSON) |
| `tests/` | Unit tests for the plain-Python parts |

Run the tests without Blender from the folder that contains `log_generator`:

```
python -m unittest discover -s log_generator/tests -t .
```
