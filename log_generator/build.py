"""Building log objects in the scene, and exporting them.

1. Turn the panel's settings into one LogSpec per log (design.py), each
   varied by its own random draw.
2. Build each log's mesh (logmesh.py) and make it a Blender object with
   its bark colours, end grain UV maps and two materials (materials.py).
3. Arrange them:
   - Single Log: one log lying on the 3D cursor.
   - Stacked Load: a pyramid of logs on an empty at the 3D cursor (the
     deck of the car), optionally joined into one printable solid.
   - Log Pond: logs floating at the 3D cursor's height, scattered over the
     area, each as deep as its species floats, optionally with a water
     surface.

The generated object (the log, or the empty holding a load or a pond) is
the "root". It stores the settings it was built with (``SETTINGS_KEY``),
so Load Settings From Selected can bring them back and Regenerate Selected
can rebuild it in place, as in Tie Strip Generator.

Every Generate adds new objects to the active collection and leaves earlier
ones alone, and uses a new random seed unless Lock Seed is on. The seed
used is written back to the panel, so locking it repeats the last logs.
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, field

import bmesh
import bpy
import numpy as np

from . import arrange, design, logmesh, materials, scales

TAG = "log_generator"  # custom property marking a root (a log, load or pond)
PART_TAG = "log_generator_part"  # on logs and water belonging to a load or pond: "LOG" or "WATER"
SETTINGS_KEY = "log_generator_settings"
SETTINGS_META_KEY = "log_generator_settings_meta"
SETTINGS_FORMAT = 1
SEED_LIMIT = 2**31

NAMES = {"SINGLE": "Log", "STACK": "LogLoad", "POND": "LogPond"}


class BuildError(RuntimeError):
    """The logs can't be built; the message says why and how to fix it."""


@dataclass
class BuildResult:
    """The root object, warnings to show, and statistics for the report."""

    obj: bpy.types.Object
    warnings: list[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)


def set_scene_millimetres(scene) -> None:
    """1 Blender unit = 1 mm, so the STL comes out in millimetres."""
    us = scene.unit_settings
    us.system = "METRIC"
    us.length_unit = "MILLIMETERS"
    us.scale_length = 0.001


# ---- finding generated objects ----

def is_root(obj) -> bool:
    """True when ``obj`` is a log, load or pond made by Generate."""
    return obj is not None and bool(obj.get(TAG))


def is_part(obj) -> bool:
    """True when ``obj`` is a log or water surface belonging to a load or pond."""
    return obj is not None and bool(obj.get(PART_TAG))


def root_of(obj):
    """The root ``obj`` is or belongs to; None for anything else."""
    if is_part(obj) and is_root(obj.parent):
        return obj.parent
    return obj if is_root(obj) else None


def selected_roots(context) -> list:
    """The selected roots (a selected part counts as its root), in order, each once."""
    out = []
    for o in context.selected_objects:
        r = root_of(o)
        if r is not None and r not in out:
            out.append(r)
    return out


def parts_of(root) -> list:
    """The objects a root is made of: itself for a single log, else its parts."""
    if root.type == "MESH" and not any(is_part(c) for c in root.children):
        return [root]
    return [c for c in root.children if is_part(c)]


def stored_settings(root) -> tuple[dict, dict]:
    """The settings ``root`` was built with, and the panel's preset state at the time."""
    raw = root.get(SETTINGS_KEY)
    if not raw:
        raise BuildError(f"{root.name} has no stored settings.")
    try:
        values = json.loads(raw)
        meta = json.loads(root.get(SETTINGS_META_KEY) or "{}")
    except (TypeError, ValueError) as err:
        raise BuildError(f"{root.name}'s stored settings can't be read: {err}") from err
    if not isinstance(values, dict) or not isinstance(meta, dict):
        raise BuildError(f"{root.name}'s stored settings can't be read.")
    return values, meta


# ---- meshes ----

def mesh_from_arrays(name: str, verts: np.ndarray, tris: np.ndarray) -> bpy.types.Mesh:
    """A new Blender mesh from vertex and triangle arrays."""
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(verts))
    mesh.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    mesh.loops.add(len(tris) * 3)
    mesh.loops.foreach_set("vertex_index", tris.astype(np.int32).ravel())
    mesh.polygons.add(len(tris))
    mesh.polygons.foreach_set("loop_start", np.arange(0, len(tris) * 3, 3, dtype=np.int32))
    mesh.update()
    mesh.validate()
    return mesh


def log_mesh(name: str, lm: logmesh.LogMesh, key: str) -> bpy.types.Mesh:
    """A Blender mesh for a built log, with materials, colours and UV maps."""
    mesh = mesh_from_arrays(name, lm.vertices, lm.triangles)
    mesh.materials.append(materials.bark_material())
    mesh.materials.append(materials.end_grain_material(key))
    mesh.polygons.foreach_set("material_index", lm.material.astype(np.int32))
    col = mesh.color_attributes.new(materials.COLOUR_ATTR, "FLOAT_COLOR", "POINT")
    col.data.foreach_set("color", lm.colours.astype(np.float32).ravel())
    mesh.color_attributes.active_color = col
    mesh.color_attributes.render_color_index = mesh.color_attributes.find(col.name)
    loop_verts = lm.triangles.ravel()
    for uv_name, uv in ((materials.UV_NORM, lm.uv_norm), (materials.UV_RINGS, lm.uv_rings)):
        layer = mesh.uv_layers.new(name=uv_name)
        layer.data.foreach_set("uv", uv[loop_verts].astype(np.float32).ravel())
    mesh.shade_smooth()
    try:
        mesh.set_sharp_from_angle(angle=math.radians(50))
    except (AttributeError, TypeError):
        pass
    return mesh


def _new_object(name, mesh, coll) -> bpy.types.Object:
    """A new object for ``mesh`` linked to ``coll``."""
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    return obj


def _centre_along(lm: logmesh.LogMesh, length: float) -> None:
    """Move the log so its middle is at x = 0 (in place)."""
    lm.vertices[:, 0] -= 0.5 * length


def _clean(mesh) -> int:
    """Merge duplicate points and fix normals after a Boolean; returns the open-edge count."""
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        open_edges = sum(1 for e in bm.edges if not e.is_manifold)
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
    return open_edges


def _union(base, others) -> tuple[str, int]:
    """Union ``others`` into ``base`` with Boolean modifiers (Manifold, else Exact) and apply.

    The other objects are deleted. Returns (solver used, open edges).
    """
    def run(solver):
        base.modifiers.clear()
        for o in others:
            mod = base.modifiers.new(f"Union {o.name}", "BOOLEAN")
            mod.operation = "UNION"
            mod.operand_type = "OBJECT"
            mod.object = o
            mod.solver = solver
        depsgraph = bpy.context.evaluated_depsgraph_get()
        depsgraph.update()
        ev = base.evaluated_get(depsgraph)
        return bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True,
                                               depsgraph=depsgraph)

    solver = "MANIFOLD"
    try:
        new = run(solver)
    except TypeError:
        solver, new = "EXACT", run("EXACT")
    if len(new.polygons) == 0:
        bpy.data.meshes.remove(new)
        solver, new = "EXACT", run("EXACT")
    base.modifiers.clear()
    old = base.data
    base.data = new
    bpy.data.meshes.remove(old)
    for o in others:
        m = o.data
        bpy.data.objects.remove(o)
        if m.users == 0:
            bpy.data.meshes.remove(m)
    return solver, _clean(base.data)


# ---- generate ----

def generate(context, progress=None) -> BuildResult:
    """Build logs from the scene's Log Generator settings.

    ``progress(done, total)``, if given, is called as each log is ready.
    """
    started = time.perf_counter()
    scene = context.scene
    s = scene.log_generator
    d = s.design()
    errs = design.errors(d)
    if errs:
        raise BuildError("\n".join(errs))
    seed = s.seed if s.lock_seed else random.randrange(1, SEED_LIMIT)
    specs = design.log_specs(d, seed)
    warnings: list[str] = []
    set_scene_millimetres(scene)
    coll = context.collection or scene.collection
    sp = d.sp

    # ---- arrangement first, so logs that don't fit aren't built ----
    radii = [design.mid_radius(spec) for spec in specs]
    lengths = [spec.length for spec in specs]
    rng = random.Random(seed + 77)
    places: dict[int, arrange.Placement] = {}
    if d.arrangement == "STACK":
        overlap = s.overlap if s.join_load else 0.0
        centres, left = arrange.stack(radii, s.model_mm("load_width"), s.max_rows, overlap)
        for k, i in enumerate(sorted(centres, key=lambda i: (centres[i][1], centres[i][0]))):
            y, z = centres[i]
            dx = rng.uniform(-1, 1) * s.end_stagger / 100.0 * lengths[i]
            places[i] = arrange.Placement(dx, y, z, roll=rng.uniform(0, 2 * math.pi),
                                          flip=s.alternate_butts and k % 2 == 1)
        if left:
            warnings.append(f"{len(left)} of {len(specs)} logs didn't fit the load; widen the "
                            "load or allow more rows.")
    elif d.arrangement == "POND":
        spots, left = arrange.pond(lengths, radii, s.model_mm("pond_length"),
                                   s.model_mm("pond_width"), seed)
        for i, (x, y, yaw) in spots.items():
            z = arrange.float_depth(radii[i], sp.specific_gravity)
            places[i] = arrange.Placement(x, y, z, yaw=yaw, roll=rng.uniform(0, 2 * math.pi),
                                          flip=rng.random() < 0.5)
        if left:
            warnings.append(f"{len(left)} of {len(specs)} logs didn't fit in the pond area; make "
                            "the area bigger or use fewer logs.")
    else:
        places[0] = arrange.Placement(0.0, 0.0, 0.0)

    # ---- build the logs ----
    logs = []
    total = len(places)
    tri_count = 0
    for done, i in enumerate(sorted(places)):
        spec = specs[i]
        lm = logmesh.build(spec)
        _centre_along(lm, spec.length)
        tri_count += len(lm.triangles)
        mesh = log_mesh(NAMES["SINGLE"], lm, d.species)
        obj = _new_object(NAMES["SINGLE"], mesh, coll)
        obj["log_length_mm"] = round(spec.length, 3)
        obj["log_diameter_mm"] = round(spec.d_butt, 3)
        obj["log_flared"] = spec.flare > 0
        logs.append((i, obj, lm))
        if progress:
            progress(done + 1, total + 1)

    # ---- place them ----
    cursor = scene.cursor.location.copy()
    info = {"logs": len(logs), "triangles": tri_count, "seed": seed}
    if d.arrangement == "SINGLE":
        _i, root, lm = logs[0]
        root.location = (cursor.x, cursor.y, cursor.z - float(lm.vertices[:, 2].min()))
    else:
        root = bpy.data.objects.new(NAMES[d.arrangement], None)
        root.empty_display_type = "PLAIN_AXES"
        root.empty_display_size = max(radii) * 2 if radii else 5.0
        coll.objects.link(root)
        root.location = cursor
        for i, obj, _lm in logs:
            p = places[i]
            obj.parent = root
            obj.location = (p.x, p.y, p.z)
            obj.rotation_euler = (p.roll, 0.0, p.yaw + (math.pi if p.flip else 0.0))
            obj[PART_TAG] = "LOG"
            obj.name = f"{root.name} Log"
        if d.arrangement == "STACK" and s.join_load and len(logs) > 1:
            context.view_layer.update()
            base = logs[0][1]
            for _i, o, _lm in logs[1:]:
                o.parent = None
                o.matrix_world = root.matrix_world @ o.matrix_basis
            mw = base.matrix_world.copy()
            base.parent = None
            base.matrix_world = mw
            solver, open_edges = _union(base, [o for _i, o, _lm in logs[1:]])
            base.parent = root
            base.matrix_parent_inverse = root.matrix_world.inverted()
            base.name = f"{root.name} Joined"
            info["solver"] = solver
            if open_edges:
                warnings.append(f"The joined load has {open_edges} open edges and may not "
                                "slice cleanly.")
            tri_count = len(base.data.polygons)
            info["triangles"] = tri_count
        if d.arrangement == "POND" and s.water_plane:
            w, l = s.model_mm("pond_width"), s.model_mm("pond_length")
            verts = np.array([[-l / 2, -w / 2, 0], [l / 2, -w / 2, 0], [l / 2, w / 2, 0],
                              [-l / 2, w / 2, 0]], dtype=np.float64)
            wm = mesh_from_arrays("Water", verts, np.array([[0, 1, 2], [0, 2, 3]]))
            wm.materials.append(materials.water_material())
            water = _new_object(f"{root.name} Water", wm, coll)
            water.parent = root
            water[PART_TAG] = "WATER"

    # ---- record and report ----
    if s.seed != seed:
        from .properties import quiet
        with quiet():  # record the seed used without marking a preset modified
            s.seed = seed
    root[TAG] = True
    root[SETTINGS_KEY] = json.dumps(s.preset_values(), default=str)
    root[SETTINGS_META_KEY] = json.dumps({"format": SETTINGS_FORMAT, "log_preset": s.log_preset,
                                          "log_modified": bool(s.log_modified)})
    info["seconds"] = time.perf_counter() - started
    what = f"{len(logs)} {sp.name} log" + ("s" if len(logs) != 1 else "")
    s.last_report = (f"{root.name} (seed {seed}): {what}, {tri_count:,} triangles, "
                     f"{info['seconds']:.1f} s.")
    for o in context.selected_objects:
        o.select_set(False)
    root.select_set(True)
    context.view_layer.objects.active = root
    return BuildResult(root, warnings, info)


def _remove_tree(obj) -> None:
    """Delete ``obj`` and its generated parts, and their meshes when unused."""
    for child in list(obj.children):
        if is_part(child):
            _remove_tree(child)
    mesh = obj.data if obj.type == "MESH" else None
    bpy.data.objects.remove(obj)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def regenerate(context, old, progress=None) -> BuildResult:
    """Rebuild the root ``old`` in place from the scene's current settings.

    The new logs take over ``old``'s name, parent, transform and
    collections; other objects parented to ``old`` move to the new root.
    ``old`` is deleted last, so if the build fails it is left untouched.
    """
    name = old.name
    result = generate(context, progress)
    new = result.obj
    s = context.scene.log_generator
    temp_name = new.name
    new.parent = old.parent
    new.matrix_parent_inverse = old.matrix_parent_inverse.copy()
    if old.type == new.type == "EMPTY" or (old.type == "MESH" and new.type == "MESH"):
        new.matrix_basis = old.matrix_basis.copy()
    else:
        new.location = old.location.copy()
    targets = list(old.users_collection)
    if targets:
        for obj in [new] + [c for c in new.children if is_part(c)]:
            for coll in list(obj.users_collection):
                coll.objects.unlink(obj)
            for coll in targets:
                coll.objects.link(obj)
    for child in list(old.children):
        if not is_part(child):
            child.parent = new
    _remove_tree(old)
    new.name = name
    for child in new.children:
        if is_part(child):
            child.name = f"{new.name} {'Water' if child.get(PART_TAG) == 'WATER' else 'Log'}"
    if s.last_report.startswith(temp_name):
        s.last_report = new.name + s.last_report[len(temp_name):]
    return result


# ---- export ----

def file_name(s) -> str:
    """The default STL file name from the settings' template."""
    sp = s.design().sp
    name = s.export_template.format(species=sp.name.lower().replace(" ", "_"),
                                    scale=scales.scale_label(s.scale, s.scale_custom))
    return name if name.lower().endswith(".stl") else name + ".stl"


def export_objects(root) -> list:
    """The log meshes to export for a root (never the water surface)."""
    return [o for o in parts_of(root) if o.get(PART_TAG) != "WATER" and o.type == "MESH"]


def export_stl(context, objects, path: str) -> None:
    """Write exactly ``objects`` to one STL file in millimetres, restoring the selection after."""
    before = list(context.selected_objects)
    active = context.view_layer.objects.active
    for o in before:
        o.select_set(False)
    for o in objects:
        o.select_set(True)
    try:
        bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, global_scale=1.0,
                              use_scene_unit=False, ascii_format=False, apply_modifiers=True)
    finally:
        for o in objects:
            o.select_set(False)
        for o in before:
            o.select_set(True)
        context.view_layer.objects.active = active
