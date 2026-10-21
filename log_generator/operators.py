"""Operators: the buttons in the Log Generator panel. Each docstring is its tooltip."""

import os

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper

from . import build, preset_store
from .preset_store import PresetError


def _settings(context):
    """The scene's Log Generator settings."""
    return context.scene.log_generator


_busy = False


def is_busy() -> bool:
    """True while logs are being generated (the panel shows a wait message)."""
    return _busy


def _redraw(context):
    """Ask every area on the screen to redraw, so the panel shows the busy state."""
    screen = context.screen
    if screen:
        for area in screen.areas:
            area.tag_redraw()


class _BuildOperator:
    """Shared running of a build: busy cursor, wait message, progress bar and reports.

    Subclasses set ``wait_text`` and implement ``_build``. Blender doesn't
    redraw while an operator runs, so ``invoke`` shows the wait message
    first and the build starts on the next timer tick.
    """

    wait_text = "Generating logs, please wait..."
    _timer = None

    def _build(self, context, progress):
        """Build and return a list of build.BuildResult. Raise BuildError to stop."""
        raise NotImplementedError

    def _run(self, context, progress=None):
        """Build, then report errors, warnings and the summary line."""
        try:
            results = self._build(context, progress)
        except build.BuildError as err:
            for line in str(err).splitlines():
                self.report({"ERROR"}, line)
            _settings(context).last_report = str(err).splitlines()[0]
            return {"CANCELLED"}
        for result in results:
            for w in result.warnings:
                self.report({"WARNING"}, w)
        self.report({"INFO"}, _settings(context).last_report)
        return {"FINISHED"}

    def execute(self, context):
        """Build straight away, with no wait message (scripts and the redo panel)."""
        return self._run(context)

    def invoke(self, context, event):
        """Show the wait message and busy cursor first, then build on the next timer tick."""
        global _busy
        if _busy:
            return {"CANCELLED"}
        _busy = True
        wm = context.window_manager
        context.window.cursor_modal_set("WAIT")
        if context.workspace:
            context.workspace.status_text_set(self.wait_text)
        _redraw(context)
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        """On the first timer tick, build with a progress bar, then restore the cursor."""
        global _busy
        if event.type != "TIMER":
            return {"RUNNING_MODAL"}  # ignore clicks and keys until the build is done
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        wm.progress_begin(0, 1)
        try:
            return self._run(context, lambda done, total: wm.progress_update(done / total))
        finally:
            wm.progress_end()
            context.window.cursor_modal_restore()
            if context.workspace:
                context.workspace.status_text_set(None)
            _busy = False
            _redraw(context)


class LOGGEN_OT_generate(_BuildOperator, bpy.types.Operator):
    """Add new logs at the 3D cursor from these settings, with a random seed unless Lock Seed is on. Logs made earlier are kept"""

    bl_idname = "log_generator.generate"
    bl_label = "Generate Logs"
    bl_options = {"REGISTER", "UNDO"}

    def _build(self, context, progress):
        """Add new logs, a car load or half logs."""
        return [build.generate(context, progress)]


class LOGGEN_OT_regenerate(_BuildOperator, bpy.types.Operator):
    """Rebuild the selected logs or car loads in place with the panel's current settings. Each keeps its name, place and collection. Uses a new random seed unless Lock Seed is on"""

    bl_idname = "log_generator.regenerate"
    bl_label = "Regenerate Selected"
    bl_options = {"REGISTER", "UNDO"}
    wait_text = "Regenerating logs, please wait..."

    @classmethod
    def poll(cls, context):
        """Needs selected logs made by Log Generator."""
        if not build.selected_roots(context):
            cls.poll_message_set("Select logs made by Log Generator first")
            return False
        return True

    def _build(self, context, progress):
        """Rebuild each selected root in turn; stop at the first that fails."""
        roots = build.selected_roots(context)
        results = []
        for i, old in enumerate(roots):
            def step(done, total, i=i):
                """Progress across all the roots, not just this one."""
                if progress:
                    progress(i * total + done, len(roots) * total)
            try:
                results.append(build.regenerate(context, old, step))
            except build.BuildError as err:
                if results:
                    raise build.BuildError(f"Rebuilt {len(results)} of {len(roots)}, "
                                           f"then: {err}") from err
                raise
        if len(results) > 1:
            _settings(context).last_report = (
                f"Regenerated {len(results)}. Last: {_settings(context).last_report}")
        for r in results:
            r.obj.select_set(True)
        return results


class LOGGEN_OT_load_settings(bpy.types.Operator):
    """Set the panel to the settings the selected logs were built with, including the seed, so you can adjust them and Regenerate Selected, or make more like them. Lock Seed is left as it is"""

    bl_idname = "log_generator.load_settings"
    bl_label = "Load Settings From Selected"
    bl_options = {"REGISTER", "UNDO"}

    @staticmethod
    def _source(context):
        """The root to read: the active object's, else the first selected one."""
        root = build.root_of(context.view_layer.objects.active)
        if root is None:
            roots = build.selected_roots(context)
            root = roots[0] if roots else None
        return root

    @classmethod
    def poll(cls, context):
        """Needs selected logs made by Log Generator."""
        if cls._source(context) is None:
            cls.poll_message_set("Select logs made by Log Generator first")
            return False
        return True

    def execute(self, context):
        """Copy the stored settings into the panel."""
        root = self._source(context)
        try:
            values, meta = build.stored_settings(root)
        except build.BuildError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        s = _settings(context)
        s.apply_built_values(values, meta)
        if s.log_preset and s.log_preset not in preset_store.saved_names():
            self.report({"WARNING"}, f"Preset '{s.log_preset}' no longer exists; its settings "
                                     "were loaded as stored.")
        self.report({"INFO"}, f"Loaded the settings {root.name} was built with (seed {s.seed}).")
        return {"FINISHED"}


class LOGGEN_OT_new_seed(bpy.types.Operator):
    """Pick a new random seed for different-looking logs"""

    bl_idname = "log_generator.new_seed"
    bl_label = "New Seed"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        """Set a random seed."""
        import random
        _settings(context).seed = random.randrange(1, 2**31 - 1)
        return {"FINISHED"}


class LOGGEN_OT_typical_size(bpy.types.Operator):
    """Fill in the length, diameter and taper of a typical log of this species"""

    bl_idname = "log_generator.typical_size"
    bl_label = "Use Typical Size"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        """Copy the species' typical size into the size fields."""
        _settings(context).apply_typical_size()
        return {"FINISHED"}


class LOGGEN_OT_export_stl(bpy.types.Operator, ExportHelper):
    """Export the selected logs as STL files in millimetres. Selecting a group (its empty) exports all its logs; selecting single logs in a group exports just those"""

    bl_idname = "log_generator.export_stl"
    bl_label = "Export STL"
    filename_ext = ".stl"
    filter_glob: StringProperty(default="*.stl", options={"HIDDEN"})
    one_file_per_log: BoolProperty(
        name="One File per Log",
        description="Write each log to its own file, named after the file name chosen plus "
                    "the log's name. A joined car load is one log here",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        """Only available when logs made by Log Generator are selected."""
        return bool(build.selected_logs(context))

    def invoke(self, context, event):
        """Open the file browser on the default file name, next to the .blend file."""
        folder = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~")
        self.filepath = os.path.join(folder, build.file_name(_settings(context)))
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        """Write the selected logs to the file, or each log to its own file."""
        logs = build.selected_logs(context)
        if not logs:
            self.report({"ERROR"}, "Nothing to export: select logs made by Log Generator.")
            return {"CANCELLED"}
        try:
            if not self.one_file_per_log or len(logs) == 1:
                build.export_stl(context, logs, self.filepath)
                written = os.path.basename(self.filepath)
            else:
                stem, ext = os.path.splitext(self.filepath)
                for obj in logs:
                    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in obj.name)
                    build.export_stl(context, [obj], f"{stem}_{safe}{ext}")
                written = f"{len(logs)} files next to {os.path.basename(self.filepath)}"
        except RuntimeError as err:
            self.report({"ERROR"}, f"Export failed: {err}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {len(logs)} log(s) to {written}")
        return {"FINISHED"}


# ---- log presets ----

class LOGGEN_OT_apply_preset(bpy.types.Operator):
    """Fill in every setting from this saved log preset"""

    bl_idname = "log_generator.apply_preset"
    bl_label = "Apply Log Preset"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}
    name: StringProperty()

    def execute(self, context):
        """Load the saved preset's values into the settings."""
        try:
            values = preset_store.load(self.name)
        except PresetError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        _settings(context).apply_values(values, self.name)
        return {"FINISHED"}


class LOGGEN_OT_save_preset(bpy.types.Operator):
    """Save every current setting as a log preset, for example 'HO Douglas fir car load'"""

    bl_idname = "log_generator.save_preset"
    bl_label = "Save Log Preset"
    name: StringProperty(name="Name", description="Saving under an existing name replaces it")

    def invoke(self, context, event):
        """Ask for a name, suggesting the current preset."""
        self.name = _settings(context).log_preset
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        """Save every setting under the name."""
        name = preset_store.clean_name(self.name)
        if not name:
            self.report({"ERROR"}, "Give the preset a name.")
            return {"CANCELLED"}
        s = _settings(context)
        try:
            preset_store.save(name, s.preset_values())
        except PresetError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        s.log_preset, s.log_modified = name, False
        self.report({"INFO"}, f"Saved log preset '{name}'.")
        return {"FINISHED"}


class LOGGEN_OT_remove_preset(bpy.types.Operator):
    """Delete one of your saved log presets"""

    bl_idname = "log_generator.remove_preset"
    bl_label = "Delete Log Preset"
    bl_options = {"INTERNAL"}
    name: StringProperty()

    def invoke(self, context, event):
        """Ask before deleting."""
        return context.window_manager.invoke_confirm(
            self, event, title=f"Delete log preset '{self.name}'?", confirm_text="Delete")

    def execute(self, context):
        """Delete the preset file, and clear the panel's preset name if it was this one."""
        try:
            preset_store.remove(self.name)
        except (PresetError, OSError) as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        s = _settings(context)
        if s.log_preset == self.name:
            s.log_preset = ""
        return {"FINISHED"}


classes = (
    LOGGEN_OT_generate, LOGGEN_OT_regenerate, LOGGEN_OT_load_settings, LOGGEN_OT_new_seed,
    LOGGEN_OT_typical_size, LOGGEN_OT_export_stl,
    LOGGEN_OT_apply_preset, LOGGEN_OT_save_preset, LOGGEN_OT_remove_preset,
)
