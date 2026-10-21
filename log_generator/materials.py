"""Materials for the logs: bark (from the vertex colours), end grain per species, and water.

Bark colour is baked into each log's "Col" colour attribute by logmesh.py,
so one shared "Log Bark" material serves every species and scale. The
end grain material is procedural: growth rings from the "Rings" UV map
and heartwood from the "EndGrain" UV map (see logmesh.py), one material
per species for its wood colours. Materials are made on first use and
reused after that, so you can edit them and later logs pick up your
changes.
"""

from __future__ import annotations

import bpy

from . import species
from .logmesh import srgb_to_linear

BARK_NAME = "Log Bark"
WATER_NAME = "Log Pond Water"
COLOUR_ATTR = "Col"
UV_NORM = "EndGrain"
UV_RINGS = "Rings"


def _lin(rgb, k: float = 1.0) -> tuple:
    """An sRGB triple (times ``k``) as a linear RGBA tuple for node colour inputs."""
    c = srgb_to_linear([v * k for v in rgb])
    return (float(c[0]), float(c[1]), float(c[2]), 1.0)


def _socket(sockets, name: str, kind: str | None = None):
    """The socket called ``name`` (of type ``kind``, e.g. "RGBA", if given)."""
    for s in sockets:
        if s.name == name and (kind is None or s.type == kind) and s.enabled:
            return s
    for s in sockets:
        if s.name == name and (kind is None or s.type == kind):
            return s
    raise KeyError(name)


def _principled(mat):
    """The material's Principled BSDF node, after turning nodes on."""
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        out = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None) or nodes.new(
            "ShaderNodeOutputMaterial")
        mat.node_tree.links.new(bsdf.outputs[0], out.inputs[0])
    return bsdf


def bark_material() -> bpy.types.Material:
    """The shared bark material: base colour from the log's colour attribute."""
    mat = bpy.data.materials.get(BARK_NAME)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(BARK_NAME)
    mat.diffuse_color = (0.25, 0.18, 0.13, 1.0)
    bsdf = _principled(mat)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    attr = nodes.new("ShaderNodeVertexColor")
    attr.layer_name = COLOUR_ATTR
    attr.location = (bsdf.location.x - 300, bsdf.location.y)
    links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.92
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.2
    return mat


def end_grain_material(key: str) -> bpy.types.Material:
    """The end grain material for a species: rings, heartwood and sapwood."""
    sp = species.get(key)
    name = f"Log End Grain - {sp.name}"
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = _lin(sp.heartwood)
    bsdf = _principled(mat)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    x0, y0 = bsdf.location.x - 1400, bsdf.location.y

    def node(kind, x, y, **props):
        n = nodes.new(kind)
        n.location = (x0 + x, y0 + y)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    uv_rings = node("ShaderNodeUVMap", 0, 0, uv_map=UV_RINGS)
    uv_norm = node("ShaderNodeUVMap", 0, -300, uv_map=UV_NORM)
    years = node("ShaderNodeVectorMath", 200, 0, operation="LENGTH")
    links.new(uv_rings.outputs["UV"], years.inputs[0])
    radius = node("ShaderNodeVectorMath", 200, -300, operation="LENGTH")
    links.new(uv_norm.outputs["UV"], radius.inputs[0])

    # Wobble the rings a little so they aren't perfect circles.
    scale = node("ShaderNodeVectorMath", 200, 200, operation="SCALE")
    links.new(uv_rings.outputs["UV"], scale.inputs[0])
    _socket(scale.inputs, "Scale").default_value = 0.06
    wobble = node("ShaderNodeTexNoise", 400, 200)
    links.new(scale.outputs["Vector"], wobble.inputs["Vector"])
    wobble.inputs["Scale"].default_value = 1.5
    wobble.inputs["Detail"].default_value = 3.0
    centre = node("ShaderNodeMath", 600, 200, operation="SUBTRACT")
    links.new(wobble.outputs["Fac"], centre.inputs[0])
    centre.inputs[1].default_value = 0.5
    amount = node("ShaderNodeMath", 800, 200, operation="MULTIPLY")
    links.new(centre.outputs[0], amount.inputs[0])
    amount.inputs[1].default_value = 2.4
    wobbly = node("ShaderNodeMath", 800, 0, operation="ADD")
    links.new(years.outputs["Value"], wobbly.inputs[0])
    links.new(amount.outputs[0], wobbly.inputs[1])
    frac = node("ShaderNodeMath", 1000, 0, operation="FRACT")
    links.new(wobbly.outputs[0], frac.inputs[0])
    late = node("ShaderNodeMapRange", 1150, 0, interpolation_type="SMOOTHSTEP")
    links.new(frac.outputs[0], late.inputs["Value"])
    late.inputs["From Min"].default_value = 0.5
    late.inputs["From Max"].default_value = 0.92

    heart = node("ShaderNodeMapRange", 400, -300, interpolation_type="SMOOTHSTEP")
    links.new(radius.outputs["Value"], heart.inputs["Value"])
    heart.inputs["From Min"].default_value = max(sp.heart_frac - 0.04, 0.0)
    heart.inputs["From Max"].default_value = min(sp.heart_frac + 0.04, 1.0)

    wood = node("ShaderNodeMix", 700, -300, data_type="RGBA")
    links.new(heart.outputs["Result"], _socket(wood.inputs, "Factor", "VALUE"))
    _socket(wood.inputs, "A", "RGBA").default_value = _lin(sp.heartwood, 0.92)
    _socket(wood.inputs, "B", "RGBA").default_value = _lin(sp.sapwood, 0.9)
    rings = node("ShaderNodeMix", 1300, -150, data_type="RGBA", blend_type="MULTIPLY")
    links.new(late.outputs["Result"], _socket(rings.inputs, "Factor", "VALUE"))
    links.new(_socket(wood.outputs, "Result", "RGBA"), _socket(rings.inputs, "A", "RGBA"))
    _socket(rings.inputs, "B", "RGBA").default_value = (0.72, 0.64, 0.58, 1.0)
    links.new(_socket(rings.outputs, "Result", "RGBA"), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.75
    return mat


def water_material() -> bpy.types.Material:
    """A dark, glossy pond water material."""
    mat = bpy.data.materials.get(WATER_NAME)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(WATER_NAME)
    mat.diffuse_color = (0.03, 0.05, 0.04, 1.0)
    bsdf = _principled(mat)
    bsdf.inputs["Base Color"].default_value = (0.02, 0.04, 0.03, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.06
    return mat
