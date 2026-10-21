"""GLB export of a character hierarchy (meshes are already applied, so no modifiers are applied)."""

import os

import bpy

PREFERRED_FORMAT = "GLB"


def _enum_identifier(properties, name: str, wanted: str) -> str:
    identifiers = [item.identifier for item in properties[name].enum_items]
    if not identifiers:
        # Dynamic enums report no static items; the wanted identifier is then passed through.
        return wanted
    if wanted not in identifiers:
        raise ValueError(f"{name} has no {wanted}; available: {identifiers}")
    return wanted


def export_glb(path: str, root_objects: list) -> None:
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    hidden = []
    for root in root_objects:
        for exported in [root] + list(root.children_recursive):
            if exported.hide_get():
                exported.hide_set(False)
                hidden.append(exported)
            exported.select_set(True)
    bpy.context.view_layer.objects.active = root_objects[0]
    properties = bpy.ops.export_scene.gltf.get_rna_type().properties
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format=_enum_identifier(properties, "export_format", PREFERRED_FORMAT),
        use_selection=True,
        export_yup=True,
        export_apply=False,
        export_skins=True,
        export_morph=True,
        export_morph_normal=False,
        export_animations=True,
        export_animation_mode=_enum_identifier(properties, "export_animation_mode", "ACTIONS"),
        export_materials=_enum_identifier(properties, "export_materials", "EXPORT"),
        export_image_format=_enum_identifier(properties, "export_image_format", "AUTO"),
    )
    for exported in hidden:
        exported.hide_set(True)
