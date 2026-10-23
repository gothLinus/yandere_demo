"""Principled BSDF materials named M_<Part>, with colors given in sRGB."""

import os

import bpy

DEFINITION_PROPERTY = "principled_definition"
ALPHA_RENDER_METHOD = "DITHERED"
BLEND_RENDER_METHOD = "BLENDED"


def hex_to_srgb(hex_color: str) -> tuple:
    value = hex_color.lstrip("#")
    return tuple(int(value[index:index + 2], 16) / 255.0 for index in (0, 2, 4))


def srgb_to_linear(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def principled(name: str, color: tuple, roughness: float = 0.6, texture_path: str | None = None,
               alpha: float = 1.0, texture_alpha: bool = True, emission_strength: float = 0.0) -> bpy.types.Material:
    """Return the material `name`, creating it once. `color` is sRGB (r, g, b) or a hex string.

    Asking for an existing name with a different color, roughness or texture raises instead of silently
    returning the first definition. A positive `emission_strength` makes the surface glow in its own color.
    """
    if isinstance(color, str):
        color = hex_to_srgb(color)
    linear = tuple(srgb_to_linear(channel) for channel in color[:3]) + (1.0,)
    definition = _definition(linear, roughness, texture_path, alpha, emission_strength)
    existing = bpy.data.materials.get(name)
    if existing is not None:
        if existing.get(DEFINITION_PROPERTY) != definition:
            raise ValueError(f"material {name} is already defined as {existing.get(DEFINITION_PROPERTY)}, not {definition}")
        return existing
    material = bpy.data.materials.new(name)
    material[DEFINITION_PROPERTY] = definition
    material.use_nodes = True
    nodes = material.node_tree.nodes
    shader = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = linear
    shader.inputs["Roughness"].default_value = roughness
    material.diffuse_color = linear
    material.roughness = roughness
    if emission_strength > 0.0:
        shader.inputs["Emission Color"].default_value = linear
        shader.inputs["Emission Strength"].default_value = emission_strength
    if texture_path:
        _attach_texture(material, shader, texture_path, texture_alpha)
    if alpha < 1.0:
        # Exported as glTF alphaMode BLEND.
        shader.inputs["Alpha"].default_value = alpha
        _set_render_method(material, BLEND_RENDER_METHOD)
    return material


def _definition(linear: tuple, roughness: float, texture_path: str | None, alpha: float,
                emission_strength: float) -> str:
    rounded = ", ".join(f"{channel:.4f}" for channel in linear[:3])
    texture = os.path.abspath(texture_path) if texture_path else ""
    suffix = f" alpha={alpha:.3f}" if alpha < 1.0 else ""
    if emission_strength > 0.0:
        suffix += f" emission={emission_strength:.3f}"
    return f"color=({rounded}) roughness={roughness:.3f} texture={texture}{suffix}"


def _set_render_method(material, wanted: str) -> None:
    render_methods = [item.identifier for item in bpy.types.Material.bl_rna.properties["surface_render_method"].enum_items]
    if wanted not in render_methods:
        raise ValueError(f"surface_render_method has no {wanted}; available: {render_methods}")
    material.surface_render_method = wanted


def _attach_texture(material, shader, texture_path: str, texture_alpha: bool) -> None:
    image = bpy.data.images.load(os.path.abspath(texture_path), check_existing=True)
    texture_node = material.node_tree.nodes.new("ShaderNodeTexImage")
    texture_node.image = image
    texture_node.location = (shader.location.x - 320, shader.location.y)
    links = material.node_tree.links
    links.new(texture_node.outputs["Color"], shader.inputs["Base Color"])
    if not texture_alpha:
        return
    links.new(texture_node.outputs["Alpha"], shader.inputs["Alpha"])
    render_methods = [item.identifier for item in bpy.types.Material.bl_rna.properties["surface_render_method"].enum_items]
    if ALPHA_RENDER_METHOD in render_methods:
        material.surface_render_method = ALPHA_RENDER_METHOD
