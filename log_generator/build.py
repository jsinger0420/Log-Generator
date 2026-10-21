"""Building log objects in the scene, and exporting them.

1. Turn the panel's settings into one LogSpec per log (design.py), each
   log varied by its own random draw.
2. Build each log's mesh (logmesh.py) and make it a Blender object with
   its bark colours, end grain UV maps and two materials (materials.py).
3. Arrange them:
   - Separate Logs: side by side in a row at the 3D cursor, resting on it,
     each its own object.
   - Car Load: a pyramid on an empty at the 3D cursor (the car deck),
     longest logs at the bottom, optionally joined into one printable solid.
   - Floating Half Logs: each log cut flat at its waterline and closed, the
     flat face standing on the 3D cursor, so it can be glued to a surface
     painted as water. Side by side, each its own object.

The generated object (a lone log, or the empty holding several) is the
"root". It stores the settings it was built with (``SETTINGS_KEY``), so
Load Settings From Selected can bring them back and Regenerate Selected
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

TAG = "log_generator"  # custom property marking a root (a log, or the empty holding several)
PART_TAG = "log_generator_part"  # on each log under a root: "LOG"
SETTINGS_KEY = "log_generator_settings"
SETTINGS_META_KEY = "log_generator_settings_meta"
SETTINGS_FORMAT = 1
SEED_LIMIT = 2**31
TEMP_NAME = "_log_generator_new"  # logs are named this until they are placed

# (name of a lone log, name of the empty holding several)
NAMES = {"LOGS": ("Log", "Logs"), "STACK": ("LogLoad", "LogLoad"),
         "FLOAT": ("HalfLog", "FloatingLogs")}


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
    """True when ``obj`` is a log, or the empty holding several, made by Generate."""
    return obj is not None and bool(obj.get(TAG))


def is_part(obj) -> bool:
    """True when ``obj`` is one of several logs held by a root."""
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


def selected_logs(context) -> list:
    """The log meshes to export: selected logs, and every log of a selected group's empty."""
    out = []
    for o in context.selected_objects:
        if is_part(o) and is_root(o.parent):
            objs = [o] if o.type == "MESH" and o.get(PART_TAG) != "WATER" else []
        elif is_root(o):
            objs = export_objects(o)
        else:
            objs = []
        for obj in objs:
            if obj not in out:
                out.append(obj)
    return out


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


def _clean(mesh, merge: bool = True) -> int:
    """Tidy a Boolean result, merging duplicate points if ``merge``; returns open edges.

    Merging can pinch the walls of a small drain hole, so cuts don't merge.
    Normals are left as the Boolean made them: recalculating would turn a
    closed hollow inside outward, filling it.
    """
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        if merge:
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
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


def cut_at_waterline(mesh, z: float) -> int:
    """Cut a log mesh flat at height ``z``, keep the part above and close the cut.

    The flat face gets the bark material (it stands on the painted water
    and is never seen). Returns the open-edge count (0 when closed).
    """
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-7, plane_co=(0.0, 0.0, z),
                               plane_no=(0.0, 0.0, 1.0), clear_inner=True)
        boundary = [e for e in bm.edges if e.is_boundary]
        filled = bmesh.ops.holes_fill(bm, edges=boundary, sides=0)["faces"]
        if filled:
            tri = bmesh.ops.triangulate(bm, faces=filled, quad_method="BEAUTY",
                                        ngon_method="BEAUTY")["faces"]
            for f in tri:
                f.material_index = logmesh.BARK
                f.smooth = False
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        open_edges = sum(1 for e in bm.edges if not e.is_manifold)
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
    return open_edges


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
    arrangement = d.arrangement if d.arrangement in NAMES else "LOGS"

    # ---- arrangement first, so logs that don't fit aren't built ----
    radii = [design.mid_radius(spec) for spec in specs]
    lengths = [spec.length for spec in specs]
    rng = random.Random(seed + 77)
    places: dict[int, arrange.Placement] = {}
    if arrangement == "STACK":
        overlap = s.overlap if s.join_load else 0.0
        centres, left = arrange.stack(radii, s.car_width_mm(), s.max_rows, overlap, lengths)
        for k, i in enumerate(sorted(centres, key=lambda i: (centres[i][1], centres[i][0]))):
            y, z = centres[i]
            dx = rng.uniform(-1, 1) * s.end_stagger / 100.0 * lengths[i]
            places[i] = arrange.Placement(dx, y, z, roll=rng.uniform(0, 2 * math.pi),
                                          flip=s.alternate_butts and k % 2 == 1)
        if left:
            warnings.append(f"{len(left)} of {len(specs)} logs didn't fit on the car; widen it "
                            "or allow more rows.")
    else:
        # Side by side, a gap of about half a log between them.
        gap = max(0.5 * max(radii), 1.0)
        for i, y in enumerate(arrange.row(radii, gap)):
            places[i] = arrange.Placement(0.0, y, 0.0)

    # ---- build the logs ----
    logs = []
    total = len(places)
    tri_count = 0
    lone, group = NAMES[arrangement]
    above_pct = []
    too_thin = 0
    for done, i in enumerate(sorted(places)):
        spec = specs[i]
        lm = logmesh.build(spec)
        _centre_along(lm, spec.length)
        mesh = log_mesh(TEMP_NAME, lm, d.species)
        hollow = bool(lm.info.get("hollow"))
        if spec.hollow and not hollow:
            too_thin += 1
        ay, az = lm.info["axis_mid"]
        r_out = float(np.hypot(lm.vertices[:, 1], lm.vertices[:, 2]).max())
        roll = places[i].roll
        if roll:
            # Turn the log on its axis in the mesh itself, so its underside (and
            # drain hole) faces down in the load.
            mesh.transform(_rotation_x(roll))
            ay, az = (ay * math.cos(roll) - az * math.sin(roll),
                      ay * math.sin(roll) + az * math.cos(roll))
            places[i].roll = 0.0
        open_edges = 0
        if arrangement == "FLOAT":
            f = s.above_water(radii[i])
            above_pct.append(f)
            cut_z = radii[i] * (1.0 - 2.0 * f)
            k = lm.info.get("cavity_vertices", 0)
            cavity_low = float(lm.vertices[-k:, 2].min()) if hollow else 0.0
            if hollow:
                # Cut away everything below the waterline; the cut opens the hollow
                # inside, leaving an open bottom that drains and saves material.
                big = 2.0 * r_out + spec.length
                open_edges = cut_away(mesh, _box(-big, big, -big, big, cut_z - big, cut_z))
                if cut_z < cavity_low and d.drain_hole > 0:
                    # So much shows above water that the cut misses the hollow inside.
                    open_edges = cut_away(mesh, _cylinder(0.0, ay, cut_z - 1.0, az,
                                                          d.drain_hole / 2))
            else:
                open_edges = cut_at_waterline(mesh, cut_z)
            mesh.transform(_translation(0.0, 0.0, -cut_z))
            base_z = 0.0
        else:
            if hollow and d.drain_hole > 0:
                open_edges = cut_away(mesh, _cylinder(0.0, ay, -r_out - 1.0, az,
                                                      d.drain_hole / 2))
            base_z = -min(v.co.z for v in mesh.vertices)  # rest on the ground
        if open_edges:
            warnings.append(f"Log {done + 1} has {open_edges} open edges and may not "
                            "slice cleanly.")
        tri_count += len(mesh.polygons)
        obj = _new_object(TEMP_NAME, mesh, coll)  # named once it's placed
        obj["log_length_mm"] = round(spec.length, 3)
        obj["log_diameter_mm"] = round(spec.d_butt, 3)
        obj["log_flared"] = spec.flare > 0
        logs.append((i, obj, base_z))
        if progress:
            progress(done + 1, total + 1)

    # ---- place them ----
    cursor = scene.cursor.location.copy()
    info = {"logs": len(logs), "triangles": tri_count, "seed": seed}
    if len(logs) == 1 and arrangement != "STACK":
        _i, root, base_z = logs[0]
        root.name = root.data.name = lone
        root.location = (cursor.x, cursor.y, cursor.z + base_z)
    else:
        root = bpy.data.objects.new(group, None)
        root.empty_display_type = "PLAIN_AXES"
        root.empty_display_size = max(radii) * 2 if radii else 5.0
        coll.objects.link(root)
        root.location = cursor
        for n, (i, obj, base_z) in enumerate(logs):
            p = places[i]
            obj.parent = root
            if arrangement == "STACK":
                obj.location = (p.x, p.y, p.z)
                obj.rotation_euler = (0.0, 0.0, math.pi if p.flip else 0.0)  # roll is in the mesh
            else:
                obj.location = (p.x, p.y, base_z)
            obj[PART_TAG] = "LOG"
            obj.name = obj.data.name = f"{root.name} {n + 1:02d}"
        if arrangement == "STACK" and s.join_load and len(logs) > 1:
            context.view_layer.update()
            base = logs[0][1]
            for _i, o, _z in logs[1:]:
                o.parent = None
                o.matrix_world = root.matrix_world @ o.matrix_basis
            mw = base.matrix_world.copy()
            base.parent = None
            base.matrix_world = mw
            solver, open_edges = _union(base, [o for _i, o, _z in logs[1:]])
            base.parent = root
            base.matrix_parent_inverse = root.matrix_world.inverted()
            base.name = f"{root.name} Joined"
            info["solver"] = solver
            if open_edges:
                warnings.append(f"The joined load has {open_edges} open edges and may not "
                                "slice cleanly.")
            tri_count = len(base.data.polygons)
            info["triangles"] = tri_count
    if above_pct:
        info["above_water"] = (min(above_pct), max(above_pct))
    if too_thin:
        warnings.append(f"{too_thin} of {len(logs)} logs are too thin for {d.wall:g} mm walls "
                        "and were made solid.")

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
    what = f"{len(logs)} {sp.name} " + ("half log" if arrangement == "FLOAT" else "log") \
        + ("s" if len(logs) != 1 else "")
    s.last_report = (f"{root.name} (seed {seed}): {what}, {tri_count:,} triangles, "
                     f"{info['seconds']:.1f} s.")
    for o in context.selected_objects:
        o.select_set(False)
    root.select_set(True)
    context.view_layer.objects.active = root
    return BuildResult(root, warnings, info)


def _translation(x: float, y: float, z: float):
    """A translation matrix."""
    from mathutils import Matrix
    return Matrix.Translation((x, y, z))


def _rotation_x(angle: float):
    """A rotation matrix about the X axis (the log's own axis)."""
    from mathutils import Matrix
    return Matrix.Rotation(angle, 4, "X")


def _box(x0, x1, y0, y1, z0, z1):
    """A closed box as (vertices, triangles)."""
    v = np.array([[x, y, z] for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)], dtype=float)
    q = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    t = [(a, b, c) for a, b, c, d_ in q for a, b, c in ((a, b, c), (a, c, d_))]
    return v, np.array(t, dtype=np.int64)


def _cylinder(x, y, z0, z1, r, n=24):
    """A closed upright cylinder as (vertices, triangles)."""
    a = np.arange(n) * 2 * math.pi / n
    ring = np.column_stack((x + r * np.cos(a), y + r * np.sin(a)))
    v = np.concatenate((np.column_stack((ring, np.full(n, z0))),
                        np.column_stack((ring, np.full(n, z1))),
                        [[x, y, z0], [x, y, z1]]))
    j = np.arange(n)
    jn = (j + 1) % n
    side = np.concatenate((np.stack((j, jn, jn + n), -1), np.stack((j, jn + n, j + n), -1)))
    bottom = np.stack((jn, j, np.full(n, 2 * n)), -1)
    top = np.stack((j + n, jn + n, np.full(n, 2 * n + 1)), -1)
    return v, np.concatenate((side, bottom, top)).astype(np.int64)


def cut_away(mesh, cutter) -> int:
    """Subtract a closed (vertices, triangles) shape from ``mesh`` in place.

    Uses a Boolean modifier (Manifold, else Exact) on a temporary object.
    Returns the open-edge count after (0 when closed).
    """
    coll = bpy.context.scene.collection
    obj = bpy.data.objects.new("_log_generator_cut", mesh)
    cut_mesh = mesh_from_arrays("_log_generator_cutter", *cutter)
    cut_obj = bpy.data.objects.new("_log_generator_cutter", cut_mesh)
    coll.objects.link(obj)
    coll.objects.link(cut_obj)
    try:
        def run(solver):
            obj.modifiers.clear()
            mod = obj.modifiers.new("Cut", "BOOLEAN")
            mod.operation = "DIFFERENCE"
            mod.operand_type = "OBJECT"
            mod.object = cut_obj
            mod.solver = solver
            depsgraph = bpy.context.evaluated_depsgraph_get()
            depsgraph.update()
            ev = obj.evaluated_get(depsgraph)
            return bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True,
                                                   depsgraph=depsgraph)
        try:
            new = run("MANIFOLD")
        except TypeError:
            new = run("EXACT")
        if len(new.polygons) == 0:
            bpy.data.meshes.remove(new)
            new = run("EXACT")
        obj.modifiers.clear()
        # Copy the result back into ``mesh`` so callers keep their reference.
        bm = bmesh.new()
        try:
            bm.from_mesh(new)
            bm.to_mesh(mesh)
        finally:
            bm.free()
        bpy.data.meshes.remove(new)
    finally:
        bpy.data.objects.remove(obj)
        bpy.data.objects.remove(cut_obj)
        bpy.data.meshes.remove(cut_mesh)
    return _clean(mesh, merge=False)


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
    parts = sorted((c for c in new.children if is_part(c)), key=lambda c: c.name)
    for n, child in enumerate(parts):
        joined = child.name.endswith(" Joined")
        child.name = f"{new.name} Joined" if joined else f"{new.name} {n + 1:02d}"
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
    """The log meshes to export for a root (never a water surface made by version 0.1)."""
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
