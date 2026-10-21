"""The Logs tab in the 3D Viewport sidebar (N panel)."""

import bpy

from . import arrange, design, operators, preset_store, scales


def _s(context):
    """The scene's Log Generator settings."""
    return context.scene.log_generator


def _lu(s):
    """Prototype length unit label: "ft" or "m"."""
    return "ft" if s.proto_units == "IMPERIAL" else "m"


def _du(s):
    """Prototype diameter unit label: "in" or "cm"."""
    return "in" if s.proto_units == "IMPERIAL" else "cm"


def _proto_text(mm: float, s) -> str:
    """A full-size size in the panel's prototype units, e.g. 32' 6\" or 9.75 m."""
    if s.proto_units == "IMPERIAL":
        return scales.feet_inches(mm)
    return f"{mm / 1000:.2f} m" if mm >= 1000 else f"{mm / 10:.1f} cm"


class LOGGEN_MT_presets(bpy.types.Menu):
    """Your saved log presets"""

    bl_label = "Log Presets"
    bl_idname = "LOGGEN_MT_presets"

    def draw(self, context):
        """Saved log presets, each with a delete button."""
        saved = preset_store.saved_names()
        if not saved:
            self.layout.label(text="No log presets saved yet")
        for name in saved:
            row = self.layout.row(align=True)
            row.operator("log_generator.apply_preset", text=name).name = name
            row.operator("log_generator.remove_preset", text="", icon="X").name = name


class _Panel:
    """Shared placement: the Logs tab in the 3D Viewport sidebar."""

    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Logs"


class LOGGEN_PT_main(_Panel, bpy.types.Panel):
    """Generate and export logs, and check their size"""

    bl_label = "Log Generator"

    def draw(self, context):
        """Presets, Generate and Export, then a live summary or the errors."""
        s = _s(context)
        col = self.layout.column()
        row = col.row(align=True)
        text = (s.log_preset or "Log Presets") + (" (modified)" if s.log_preset and s.log_modified else "")
        row.menu("LOGGEN_MT_presets", text=text)
        row.operator("log_generator.save_preset", text="", icon="ADD")
        row = col.row(align=True)
        row.scale_y = 1.4
        if operators.is_busy():
            row.alert = True
            row.label(text="Generating logs, please wait...", icon="SORTTIME")
        else:
            row.operator("log_generator.generate", icon="MESH_CYLINDER")
            sub = col.column(align=True)
            sub.operator("log_generator.regenerate", icon="FILE_REFRESH")
            sub.operator("log_generator.load_settings", icon="IMPORT")
        col.operator("log_generator.export_stl", icon="EXPORT")
        if s.last_report:
            col.label(text=s.last_report)

        d = s.design()
        box = col.box()
        errs = design.errors(d)
        if errs:
            box.alert = True
            for e in errs:
                box.label(text=e, icon="ERROR")
            return
        m = design.summary(d)
        box.label(text=f"{d.sp.name}, {scales.SCALES.get(s.scale, ('Custom',))[0]}"
                  if s.scale in scales.SCALES else f"{d.sp.name}, 1:{s.scale_custom:g}",
                  icon="INFO")
        box.label(text=f"Model: {m['length']:.1f} mm long ({m['length'] / 25.4:.2f} in)")
        box.label(text=f"Diameter {m['diameter']:.2f} mm butt, {m['top']:.2f} mm top")
        box.label(text=f"Prototype: {_proto_text(m['real_length'], s)} x "
                       f"{_proto_text(m['real_diameter'], s)} to {_proto_text(m['real_top'], s)}")
        box.label(text=f"Taper {m['taper_in_per_ft']:.2f} in per ft; "
                       f"{m['doyle']:,.0f} bd ft (Doyle), {m['scribner']:,.0f} (Scribner)")
        if m["flare_real"]:
            box.label(text=f"Flared butts up to {_proto_text(m['flare_real'], s)} across")
        box.label(text=f"Bark relief {m['bark_depth_model']:.3f} mm in the model")
        box.label(text=f"About {m['triangles']:,} triangles per log")
        if s.carve_rings:
            row = box.row()
            row.alert = m["carve_pitch"] < 0.15
            row.label(text=f"Carved rings {m['carve_pitch']:.2f} mm apart, "
                           f"{s.carve_depth:.3f} mm deep",
                      icon="ERROR" if m["carve_pitch"] < 0.15 else "NONE")
        if s.hollow:
            if m["hollow_ok"]:
                box.label(text=f"Hollow, {s.wall:g} mm walls: about "
                               f"{m['hollow_saving'] * 100:.0f}% less material")
            else:
                row = box.row()
                row.alert = True
                row.label(text=f"Too thin for {s.wall:g} mm walls: printed solid", icon="ERROR")
        r = 0.25 * (m["diameter"] + m["top"])
        if s.arrangement == "STACK":
            width = s.car_width_mm()
            cap = arrange.capacity(width, r, s.max_rows)
            row = box.row()
            row.alert = s.log_count > cap
            row.label(text=f"Car {width:.1f} mm wide holds about {cap} logs of this size",
                      icon="ERROR" if s.log_count > cap else "NONE")
        elif s.arrangement == "FLOAT":
            f = s.above_water(r)
            note = ""
            if s.float_mode == "SPECIES" and d.sp.specific_gravity >= 1.0:
                note = " (green logs of this species barely float)"
            box.label(text=f"Half log stands {2 * r * f:.2f} mm of {2 * r:.2f} mm "
                           f"({f * 100:.0f}%) above the water{note}")
        if m["bark_depth_model"] < 0.03 and d.style() not in ("SMOOTH", "BIRCH"):
            box.label(text="Bark relief is too fine to print; it shows in colour only.",
                      icon="ERROR")


class LOGGEN_PT_species(_Panel, bpy.types.Panel):
    """Species, scale and the log's size"""

    bl_label = "Species and Size"
    bl_parent_id = "LOGGEN_PT_main"

    def draw(self, context):
        """Species, scale, size mode and size fields, taper."""
        s = _s(context)
        col = self.layout.column()
        col.prop(s, "species")
        col.operator("log_generator.typical_size", icon="TRIA_DOWN_BAR")
        col.separator()
        col.prop(s, "scale")
        if s.scale == scales.CUSTOM:
            col.prop(s, "scale_custom")
        col.prop(s, "size_mode", expand=True)
        if s.size_mode == "PROTOTYPE":
            col.prop(s, "proto_units", text="Units")
            col.prop(s, "proto_length", text=f"Length ({_lu(s)})")
            col.prop(s, "proto_diameter", text=f"Butt Diameter ({_du(s)})")
        else:
            row = col.row(align=True)
            row.prop(s, "model_units", expand=True)
            u = "mm" if s.model_units == "MM" else "in"
            col.prop(s, "model_length", text=f"Length ({u})")
            col.prop(s, "model_diameter", text=f"Butt Diameter ({u})")
            hint = col.column()
            hint.scale_y = 0.8
            hint.label(text="The scale still sets the bark size.", icon="INFO")
        col.prop(s, "top_pct")


class LOGGEN_PT_shape(_Panel, bpy.types.Panel):
    """Butt flare, roundness, bow, cut limbs and the sawn ends"""

    bl_label = "Shape"
    bl_parent_id = "LOGGEN_PT_main"

    def draw(self, context):
        """Flare, out of round, bow, limbs and end cuts."""
        s = _s(context)
        col = self.layout.column()
        col.prop(s, "flare_chance")
        sub = col.column()
        sub.enabled = s.flare_chance > 0
        sub.prop(s, "flare_amount")
        col.prop(s, "ovality")
        col.prop(s, "bow")
        col.separator()
        col.prop(s, "knots")
        col.prop(s, "stub_length", text=f"Limb Stub ({_du(s)})")
        col.separator()
        col.prop(s, "end_tilt")
        col.prop(s, "end_rough")
        col.separator()
        col.prop(s, "carve_rings")
        sub = col.column()
        sub.enabled = s.carve_rings
        sub.prop(s, "carve_count")
        sub.prop(s, "carve_depth", text="Groove Depth (mm)")
        hint = col.column()
        hint.scale_y = 0.8
        hint.label(text="Rings show in Material Preview and Rendered", icon="INFO")
        hint.label(text="view, or Solid view with Color: Attribute.")


class LOGGEN_PT_bark(_Panel, bpy.types.Panel):
    """The bark pattern, its depth and size, and missing bark"""

    bl_label = "Bark"
    bl_parent_id = "LOGGEN_PT_main"

    def draw(self, context):
        """Bark style, depth, scale and damage."""
        s = _s(context)
        col = self.layout.column()
        col.prop(s, "bark_style", text="Style")
        col.prop(s, "bark_depth")
        col.prop(s, "bark_scale")
        col.prop(s, "damage")


class LOGGEN_PT_arrange(_Panel, bpy.types.Panel):
    """Separate logs, a car load, or floating half logs"""

    bl_label = "Arrangement"
    bl_parent_id = "LOGGEN_PT_main"

    def draw(self, context):
        """Arrangement, how many logs and how they vary, then the arrangement's settings."""
        s = _s(context)
        col = self.layout.column()
        col.prop(s, "arrangement", text="")
        col.prop(s, "log_count")
        sub = col.column()
        sub.enabled = s.log_count > 1
        sub.prop(s, "length_var")
        sub.prop(s, "diameter_var")
        if s.arrangement == "STACK":
            col.separator()
            row = col.row(align=True)
            row.prop(s, "load_width_mode", expand=True)
            if s.load_width_mode == "PROTOTYPE":
                col.prop(s, "load_width", text=f"Car Width ({_lu(s)})")
            else:
                u = "mm" if s.model_units == "MM" else "in"
                row = col.row(align=True)
                row.prop(s, "load_width_model", text=f"Car Width ({u})")
                row.prop(s, "model_units", expand=True)
            col.prop(s, "max_rows")
            col.prop(s, "end_stagger")
            col.prop(s, "alternate_butts")
            col.prop(s, "join_load")
            sub = col.column()
            sub.enabled = s.join_load
            sub.prop(s, "overlap", text="Overlap (mm)")
            hint = col.column()
            hint.scale_y = 0.8
            hint.label(text="Longest logs go on the bottom.", icon="INFO")
        elif s.arrangement == "FLOAT":
            col.separator()
            col.prop(s, "float_mode", expand=True)
            sub = col.column()
            sub.enabled = s.float_mode == "CUSTOM"
            sub.prop(s, "float_above")
            hint = col.column()
            hint.scale_y = 0.8
            hint.label(text="Flat bottom stands on the 3D cursor;", icon="INFO")
            hint.label(text="glue it to water painted on a flat surface.")
        else:
            hint = col.column()
            hint.scale_y = 0.8
            hint.label(text="Side by side along Y, resting on the 3D cursor.", icon="INFO")
        if s.log_count > 1 and s.arrangement != "STACK" or (s.arrangement == "STACK"
                                                             and not s.join_load):
            hint.label(text="Each log is its own object.")


class LOGGEN_PT_hollow(_Panel, bpy.types.Panel):
    """Hollow logs: wall thickness and a drain hole"""

    bl_label = "Hollow"
    bl_parent_id = "LOGGEN_PT_main"

    def draw_header(self, context):
        """The on/off checkbox in the panel header."""
        self.layout.prop(_s(context), "hollow", text="")

    def draw(self, context):
        """Wall thickness and drain hole (greyed out when solid)."""
        s = _s(context)
        col = self.layout.column()
        col.enabled = s.hollow
        col.prop(s, "wall", text="Wall Thickness (mm)")
        sub = col.column()
        sub.enabled = s.arrangement != "FLOAT"
        sub.prop(s, "drain_hole", text="Drain Hole (mm)")
        hint = col.column()
        hint.scale_y = 0.8
        if s.arrangement == "FLOAT":
            hint.label(text="Half logs are left open underneath.", icon="INFO")
        else:
            hint.label(text="The drain hole is on the underside,", icon="INFO")
            hint.label(text="halfway along the log.")


class LOGGEN_PT_build(_Panel, bpy.types.Panel):
    """Mesh detail, triangle budget and the random seed"""

    bl_label = "Build Options"
    bl_parent_id = "LOGGEN_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        """Detail, triangle limit and seed."""
        s = _s(context)
        col = self.layout.column()
        col.prop(s, "detail", expand=True)
        col.prop(s, "max_triangles")
        row = col.row(align=True)
        row.prop(s, "seed")
        row.prop(s, "lock_seed", text="", icon="LOCKED" if s.lock_seed else "UNLOCKED")
        row.operator("log_generator.new_seed", text="", icon="FILE_REFRESH")


classes = (
    LOGGEN_MT_presets,
    LOGGEN_PT_main, LOGGEN_PT_species, LOGGEN_PT_shape, LOGGEN_PT_bark, LOGGEN_PT_arrange,
    LOGGEN_PT_hollow, LOGGEN_PT_build,
)
