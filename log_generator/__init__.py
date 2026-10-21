"""Log Generator: 3D models of logs for model railroads.

Builds sawn logs of a chosen species, cut to length with the limbs
trimmed off, with realistic bark, taper, an optional flared butt, and end
grain on the cut faces. Sizes are real-world dimensions plus a model
railroad scale, or the model's own size. Logs come singly, as a stacked
load for a log car or mill deck, or floating in a log pond, and export as
STL in millimetres for 3D printing.

The shapes, bark, species and arrangements (scales.py, species.py,
noise.py, bark.py, logmesh.py, arrange.py, design.py) are plain Python
with numpy and no bpy, so they can be tested outside Blender. Blender
modules are only imported in ``register``.
"""

_modules = None


def _load():
    """Import the Blender-only modules; returns (properties, operators, ui)."""
    from . import build, operators, properties, ui  # noqa: F401
    return properties, operators, ui


def _classes():
    """Every Blender class to register, in registration order."""
    properties, operators, ui = _load()
    return (properties.LOGGEN_Settings,) + operators.classes + ui.classes


def register():
    """Register the classes and add the Log Generator settings to every scene."""
    import bpy
    for cls in _classes():
        bpy.utils.register_class(cls)
    _load()[0].register()


def unregister():
    """Remove the scene settings and unregister the classes."""
    import bpy
    _load()[0].unregister()
    for cls in reversed(_classes()):
        bpy.utils.unregister_class(cls)
