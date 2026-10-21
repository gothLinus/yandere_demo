"""Principled BSDF materials named M_<Part>, with colors given in sRGB."""

import os

import bpy


def hex_to_srgb(hex_color: str) -> tuple:
    value = hex_color.lstrip("#")
    return tuple(int(value[index:index + 2], 16) / 255.0 for index in (0, 2, 4))


def srgb_to_linear(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def principled(name: str, color: tuple, roughness: float = 0.6, texture_path: str | None = None) -> bpy.types.Material:
    """Return the material `name`, creating it once. `color` is sRGB (r, g, b) or a hex string."""
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    if isinstance(color, str):
        color = hex_to_srgb(color)
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    shader = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    linear = tuple(srgb_to_linear(channel) for channel in color[:3]) + (1.0,)
    shader.inputs["Base Color"].default_value = linear
    shader.inputs["Roughness"].default_value = roughness
    material.diffuse_color = linear
    material.roughness = roughness
    if texture_path:
        _attach_texture(material, shader, texture_path)
    return material


def _attach_texture(material, shader, texture_path: str) -> None:
    image = bpy.data.images.load(os.path.abspath(texture_path), check_existing=True)
    texture_node = material.node_tree.nodes.new("ShaderNodeTexImage")
    texture_node.image = image
    texture_node.location = (shader.location.x - 320, shader.location.y)
    links = material.node_tree.links
    links.new(texture_node.outputs["Color"], shader.inputs["Base Color"])
    links.new(texture_node.outputs["Alpha"], shader.inputs["Alpha"])
    render_methods = [item.identifier for item in bpy.types.Material.bl_rna.properties["surface_render_method"].enum_items]
    if render_methods:
        material.surface_render_method = render_methods[0]
