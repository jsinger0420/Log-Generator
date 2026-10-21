"""All Log Generator settings, kept on the scene so they save with the .blend file.

Prototype (full-size) lengths are in feet or metres and diameters in
inches or centimetres, as chosen by ``proto_units``. Model sizes are in
model inches or millimetres, as chosen by ``model_units``. Changing either
converts the values. Lengths are plain numbers rather than Blender length
units, so they read the same whatever the scene units are.
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from . import scales, species
from .design import Design

PROTO_LENGTH_KEYS = ("proto_length", "load_width", "pond_length", "pond_width")
PROTO_DIAMETER_KEYS = ("proto_diameter", "stub_length")
MODEL_KEYS = ("model_length", "model_diameter")

# Set while a preset or unit change writes many values, so updates don't fire.
_quiet = False


class quiet:
    """Context manager: suppress update callbacks while writing settings."""

    def __enter__(self):
        """Turn updates off, remembering the previous state so blocks can nest."""
        global _quiet
        self._prev, _quiet = _quiet, True

    def __exit__(self, *exc):
        """Put updates back as they were."""
        global _quiet
        _quiet = self._prev


def _changed(self, context):
    """Mark the chosen log preset as modified when any setting is edited."""
    if not _quiet and self.log_preset:
        self.log_modified = True


def _proto_units_update(self, context):
    """Convert every prototype length and diameter when the units change."""
    if _quiet or self.proto_units == self.proto_units_prev:
        return
    old, new = self.proto_units_prev, self.proto_units
    with quiet():
        for key in PROTO_LENGTH_KEYS:
            setattr(self, key, scales.length_from_mm(scales.length_to_mm(getattr(self, key), old), new))
        for key in PROTO_DIAMETER_KEYS:
            setattr(self, key,
                    scales.diameter_from_mm(scales.diameter_to_mm(getattr(self, key), old), new))
        self.proto_units_prev = new
    _changed(self, context)


def _model_units_update(self, context):
    """Convert the model length and diameter when the model units change."""
    if _quiet or self.model_units == self.model_units_prev:
        return
    old, new = self.model_units_prev, self.model_units
    with quiet():
        for key in MODEL_KEYS:
            setattr(self, key, scales.model_from_mm(scales.model_to_mm(getattr(self, key), old), new))
        self.model_units_prev = new
    _changed(self, context)


def _size_mode_update(self, context):
    """Carry the size across when switching between prototype size and model size.

    So switching shows the same log: the model size is worked out from
    the prototype size and scale, or the other way round.
    """
    if _quiet:
        return
    n = self.scale_n()
    with quiet():
        if self.size_mode == "MODEL":
            self.model_length = scales.model_from_mm(
                scales.length_to_mm(self.proto_length, self.proto_units) / n, self.model_units)
            self.model_diameter = scales.model_from_mm(
                scales.diameter_to_mm(self.proto_diameter, self.proto_units) / n, self.model_units)
        else:
            self.proto_length = scales.length_from_mm(
                scales.model_to_mm(self.model_length, self.model_units) * n, self.proto_units)
            self.proto_diameter = scales.diameter_from_mm(
                scales.model_to_mm(self.model_diameter, self.model_units) * n, self.proto_units)
    _changed(self, context)


def _species_items():
    """Species menu items, softwoods then hardwoods under headings."""
    items = []
    for kind, title in (("SOFTWOOD", "Softwoods"), ("HARDWOOD", "Hardwoods")):
        items.append(("", title, ""))
        for sp in species.SPECIES:
            if sp.kind == kind:
                items.append((sp.key, sp.name, sp.description))
    return items


_SPECIES_ITEMS = _species_items()


def _f(name, default, desc, mn=0.0, mx=None, soft_max=None, precision=2, step=10, subtype="NONE"):
    """A float setting that marks the preset modified."""
    kw = dict(name=name, description=desc, default=default, min=mn, precision=precision,
              step=step, update=_changed, subtype=subtype)
    if mx is not None:
        kw["max"] = mx
    if soft_max is not None:
        kw["soft_max"] = soft_max
    return FloatProperty(**kw)


class LOGGEN_Settings(bpy.types.PropertyGroup):
    """Every Log Generator setting, stored on the scene as ``scene.log_generator``."""

    # ---- species ----
    species: EnumProperty(name="Species", items=_SPECIES_ITEMS, default="DOUGLAS_FIR",
                          update=_changed,
                          description="Tree species: sets the bark, wood colours, flare, limbs "
                                      "and how the log floats")
    bark_style: EnumProperty(
        name="Bark Style", default="SPECIES", update=_changed,
        description="The bark pattern; normally the species' own",
        items=[("SPECIES", "Species Default", "Use the species' own bark")]
        + [(k, v[0], v[1]) for k, v in species.STYLE_LABELS.items()])

    # ---- scale and size ----
    scale: EnumProperty(
        name="Scale", default="HO", update=_changed,
        description="Model railroad scale. Sets the model size from the prototype size, and "
                    "the size of the bark detail",
        items=[(k, v[0], v[2] + f" (1:{v[1]:g})") for k, v in scales.SCALES.items()]
        + [(scales.CUSTOM, "Custom", "Enter your own ratio")])
    scale_custom: FloatProperty(name="Ratio 1:", default=87.1, min=1.0, soft_max=500.0,
                                description="N in 1:N for a custom scale", update=_changed)
    size_mode: EnumProperty(
        name="Size By", default="PROTOTYPE", update=_size_mode_update,
        description="Enter the log's real-world size and let the scale make the model, or "
                    "enter the model log's size directly",
        items=[("PROTOTYPE", "Prototype Size", "Real-world length and diameter, scaled down"),
               ("MODEL", "Model Size", "The model log's own length and diameter")])
    proto_units: EnumProperty(
        name="Prototype Units", default="IMPERIAL", update=_proto_units_update,
        description="Units for real-world sizes. Changing it converts the values",
        items=[("IMPERIAL", "Feet / Inches", "Lengths in feet, diameters in inches"),
               ("METRIC", "Metres / cm", "Lengths in metres, diameters in centimetres")])
    proto_units_prev: StringProperty(default="IMPERIAL", options={"HIDDEN"})
    model_units: EnumProperty(
        name="Model Units", default="MM", update=_model_units_update,
        description="Units for model sizes. Changing it converts the values",
        items=[("MM", "mm", "Model sizes in millimetres"),
               ("IN", "in", "Model sizes in inches")])
    model_units_prev: StringProperty(default="MM", options={"HIDDEN"})
    proto_length: _f("Length", 32.0, "Real-world log length (feet or metres)", soft_max=100.0)
    proto_diameter: _f("Diameter", 36.0, "Real-world diameter at the large (butt) end, outside "
                                         "the bark, not counting any flare (inches or cm)",
                       soft_max=200.0)
    model_length: _f("Length", 112.0, "Model log length (model mm or inches)", soft_max=500.0,
                     precision=3)
    model_diameter: _f("Diameter", 10.5, "Model diameter at the large end, outside the bark, "
                                         "not counting any flare (model mm or inches)",
                       soft_max=100.0, precision=3)
    top_pct: _f("Top Diameter", 85.0, "Small-end diameter as a percentage of the large end: "
                                      "how much the log tapers", mn=10.0, mx=100.0, precision=0,
                step=100, subtype="PERCENTAGE")

    # ---- shape ----
    flare_chance: _f("Butt Flare", 0.0, "Chance that a log is a butt log, cut from the base of "
                                        "the tree, where it widens into the roots. 100% flares "
                                        "every log, 0% none", mn=0.0, mx=100.0, precision=0,
                     step=500, subtype="PERCENTAGE")
    flare_amount: _f("Flare Amount", 1.0, "How much a butt log widens, times the species' "
                                          "typical flare", mn=0.0, soft_max=3.0)
    ovality: _f("Out of Round", 4.0, "How oval the log is, as a percentage of its diameter",
                mn=0.0, mx=30.0, precision=1, step=50, subtype="PERCENTAGE")
    bow: _f("Bow", 1.0, "How much the log bends along its length, times the species' typical "
                        "bow; 0 is dead straight", mn=0.0, soft_max=5.0)
    knots: _f("Cut Limbs", 1.0, "How many sawn-off limbs, times the species' typical number; "
                                "0 for none", mn=0.0, soft_max=5.0)
    stub_length: _f("Limb Stub", 1.0, "Longest stub left where a limb was cut off (inches or "
                                      "cm, real-world); 0 cuts them flush", mn=0.0,
                    soft_max=12.0)
    end_tilt: _f("End Cut Angle", 3.0, "Largest angle a sawn end is off square, in degrees",
                 mn=0.0, mx=30.0, precision=1, step=50)
    end_rough: BoolProperty(name="Rough Saw Cut", default=True, update=_changed,
                            description="Give the sawn ends a slightly uneven surface")

    # ---- bark ----
    bark_depth: _f("Bark Depth", 1.0, "Depth of the bark furrows, times the species' typical "
                                      "depth", mn=0.0, soft_max=3.0)
    bark_scale: _f("Bark Scale", 1.0, "Size of the bark ridges or plates, times the species' "
                                      "typical size", mn=0.1, soft_max=3.0)
    damage: _f("Missing Bark", 5.0, "Share of the bark knocked off in handling, showing the "
                                    "wood", mn=0.0, mx=90.0, precision=0, step=100,
               subtype="PERCENTAGE")

    # ---- arrangement ----
    arrangement: EnumProperty(
        name="Arrangement", default="SINGLE", update=_changed,
        description="One log, a stacked load for a log car or mill deck, or logs floating "
                    "in a pond",
        items=[("SINGLE", "Single Log", "One log, lying at the 3D cursor"),
               ("STACK", "Stacked Load", "Logs stacked in a pyramid, for a log car or a "
                                         "log deck at the mill"),
               ("POND", "Log Pond", "Logs floating at the 3D cursor's height, scattered "
                                    "over an area")])
    log_count: IntProperty(name="Number of Logs", default=12, min=1, soft_max=100,
                           update=_changed, description="How many logs to make")
    length_var: _f("Length Variation", 10.0, "Logs vary in length by up to this, plus or minus",
                   mn=0.0, mx=50.0, precision=0, step=100, subtype="PERCENTAGE")
    diameter_var: _f("Diameter Variation", 20.0, "Logs vary in diameter by up to this, plus or "
                                                 "minus", mn=0.0, mx=60.0, precision=0, step=100,
                     subtype="PERCENTAGE")
    load_width: _f("Load Width", 9.0, "Width of the load across the car or deck (feet or "
                                      "metres, real-world)", mn=0.1, soft_max=40.0)
    max_rows: IntProperty(name="Max Rows", default=4, min=1, soft_max=10, update=_changed,
                          description="Most rows of logs in the stack")
    end_stagger: _f("End Stagger", 5.0, "Logs slide along the load by up to this share of "
                                        "their length, so the ends don't line up", mn=0.0,
                    mx=50.0, precision=0, step=100, subtype="PERCENTAGE")
    alternate_butts: BoolProperty(name="Alternate Butts", default=True, update=_changed,
                                  description="Turn every other log end for end, as loaders "
                                              "did to balance the load")
    join_load: BoolProperty(
        name="Join for Printing", default=False, update=_changed,
        description="Join the stacked logs into one solid object for 3D printing. The logs "
                    "sink into each other slightly (Overlap) so they print as one piece")
    overlap: _f("Overlap", 0.15, "How far neighbouring logs sink into each other when joined "
                                 "(model mm)", mn=0.0, soft_max=2.0, precision=3, step=1)
    pond_length: _f("Pond Length", 120.0, "Length of the area the logs float in (feet or "
                                          "metres, real-world)", mn=1.0, soft_max=1000.0)
    pond_width: _f("Pond Width", 60.0, "Width of the area the logs float in (feet or metres, "
                                       "real-world)", mn=1.0, soft_max=1000.0)
    water_plane: BoolProperty(name="Add Water Surface", default=False, update=_changed,
                              description="Add a flat water surface the size of the area, at "
                                          "the waterline, for renders")

    # ---- build ----
    detail: EnumProperty(
        name="Detail", default="MEDIUM", update=_changed,
        description="Finest mesh detail. Bark is resolved as finely as this allows",
        items=[("COARSE", "Coarse", "Quick previews and big loads: 0.4 mm"),
               ("MEDIUM", "Medium", "Good for renders and FDM printing: 0.15 mm"),
               ("FINE", "Fine", "Resin printing: 0.08 mm")])
    max_triangles: IntProperty(
        name="Max Triangles per Log", default=400_000, min=5_000, soft_max=2_000_000,
        update=_changed,
        description="Each log is kept under about this many triangles; big logs at large "
                    "scales are made coarser to fit")
    seed: IntProperty(name="Seed", default=1, min=0, update=_changed,
                      description="Number that picks the random bark, limbs and variation. "
                                  "Generate shows the seed it used here; the same seed and "
                                  "settings always give the same logs")
    lock_seed: BoolProperty(name="Lock Seed", default=False,
                            description="Use the seed above instead of a random one, to "
                                        "repeat logs you liked")

    # ---- presets and output ----
    log_preset: StringProperty(default="", options={"HIDDEN"})
    log_modified: BoolProperty(default=False, options={"HIDDEN"})
    export_template: StringProperty(
        name="File Name", default="log_{species}_{scale}.stl",
        description="Default STL file name; {species} and {scale} are filled in")
    last_report: StringProperty(default="", options={"HIDDEN"})

    # ------------------------------------------------------------------

    def scale_n(self) -> float:
        """N in 1:N for the chosen scale."""
        return scales.scale_n(self.scale, self.scale_custom)

    def design(self) -> Design:
        """The settings as a Design, in fixed units."""
        u = self.proto_units
        return Design(
            species=self.species, bark_style=self.bark_style, scale_n=self.scale_n(),
            size_mode=self.size_mode,
            length_real=scales.length_to_mm(self.proto_length, u),
            diameter_real=scales.diameter_to_mm(self.proto_diameter, u),
            length_model=scales.model_to_mm(self.model_length, self.model_units),
            diameter_model=scales.model_to_mm(self.model_diameter, self.model_units),
            top_pct=self.top_pct, flare_chance=self.flare_chance / 100.0,
            flare_amount=self.flare_amount, ovality=self.ovality / 100.0, bow=self.bow,
            knots=self.knots, stub_real=scales.diameter_to_mm(self.stub_length, u),
            bark_depth=self.bark_depth, bark_scale=self.bark_scale, damage=self.damage / 100.0,
            end_tilt=self.end_tilt, end_rough=self.end_rough, detail=self.detail,
            max_triangles=self.max_triangles, arrangement=self.arrangement,
            count=self.log_count, length_var=self.length_var / 100.0,
            diameter_var=self.diameter_var / 100.0,
        )

    def model_mm(self, key: str) -> float:
        """A prototype length setting (load width, pond size) as model mm."""
        return scales.length_to_mm(getattr(self, key), self.proto_units) / self.scale_n()

    def apply_typical_size(self) -> None:
        """Fill the size fields with the species' typical log, in the current units."""
        sp = species.get(self.species)
        length_mm = sp.length_ft * scales.MM_PER_FOOT
        dia_mm = sp.diameter_in * scales.MM_PER_INCH
        n = self.scale_n()
        with quiet():
            self.proto_length = round(scales.length_from_mm(length_mm, self.proto_units), 2)
            self.proto_diameter = round(scales.diameter_from_mm(dia_mm, self.proto_units), 1)
            self.model_length = scales.model_from_mm(length_mm / n, self.model_units)
            self.model_diameter = scales.model_from_mm(dia_mm / n, self.model_units)
            self.top_pct = sp.top_pct
        _changed(self, None)

    # ---- presets ----

    def preset_values(self) -> dict:
        """Every setting, for a log preset."""
        skip = {"rna_type", "name", "proto_units_prev", "model_units_prev", "log_preset",
                "log_modified", "last_report"}
        return {p.identifier: getattr(self, p.identifier)
                for p in self.bl_rna.properties if p.identifier not in skip}

    def apply_values(self, values: dict, name: str) -> None:
        """Load preset values and select the preset as ``name``.

        Units are set first so saved sizes aren't converted. Unknown keys
        and values this version rejects are skipped, so older presets load.
        """
        names = {p.identifier for p in self.bl_rna.properties}
        units = ("proto_units", "model_units")
        with quiet():
            for key in units:
                if key in values:
                    setattr(self, key, values[key])
                    setattr(self, key + "_prev", values[key])
            for key, value in values.items():
                if key in names and key not in units:
                    try:
                        setattr(self, key, value)
                    except (TypeError, ValueError):
                        pass  # a setting this version no longer accepts
            self.log_preset = name
            self.log_modified = False

    def apply_built_values(self, values: dict, meta: dict) -> None:
        """Load the settings logs were built with (Load Settings From Selected).

        Lock Seed is left as it is: it says how the panel is used, not how
        the logs look.
        """
        self.apply_values({k: v for k, v in values.items() if k != "lock_seed"},
                          str(meta.get("log_preset", "")))
        with quiet():
            self.log_modified = bool(meta.get("log_modified", False))


def register():
    """Add ``scene.log_generator``. LOGGEN_Settings must already be registered."""
    bpy.types.Scene.log_generator = bpy.props.PointerProperty(type=LOGGEN_Settings)


def unregister():
    """Remove ``scene.log_generator``."""
    del bpy.types.Scene.log_generator
