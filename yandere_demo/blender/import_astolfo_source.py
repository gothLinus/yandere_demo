"""One-time import of the Astolfo Source model into blender/source/astolfo/astolfo_source.blend.

Needs SourceIO (REDxEYE/SourceIO 5.5.4, MIT) from an isolated scripts directory, never the user's Blender:

    BLENDER_USER_SCRIPTS=<dir with addons/SourceIO> Blender --background --factory-startup \
        --python yandere_demo/blender/import_astolfo_source.py

The .vtf textures are written as PNG to blender/source/astolfo/textures/ and the saved .blend points at them, so
build_target.py works without SourceIO. See blender/source/README.md.
"""

import os
import sys

import addon_utils
import bpy

BLENDER_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIRECTORY = os.path.join(BLENDER_DIRECTORY, "source", "astolfo")
MODEL_PATH = os.path.join(SOURCE_DIRECTORY, "Models", "tobycrack", "astolfo", "astolfo.mdl")
TEXTURE_DIRECTORY = os.path.join(SOURCE_DIRECTORY, "textures")
BLEND_PATH = os.path.join(SOURCE_DIRECTORY, "astolfo_source.blend")
ADDON_NAME = "SourceIO"
FACE_MESH_NAME = "astolfo_head_reference.smd"
PNG_FORMAT = "PNG"


def _enum_identifier(struct, property_name: str, wanted: str) -> str:
    identifiers = [item.identifier for item in struct.bl_rna.properties[property_name].enum_items]
    if wanted not in identifiers:
        raise ValueError(f"{property_name} has no {wanted}; available: {identifiers}")
    return wanted


def import_model() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _, loaded = addon_utils.check(ADDON_NAME)
    if not loaded:
        addon_utils.enable(ADDON_NAME, default_set=False)
    # The animation import crashes on this model, and the ragdoll's physics meshes are not used.
    bpy.ops.sourceio.mdl(filepath=MODEL_PATH, directory=os.path.dirname(MODEL_PATH) + os.sep,
                         files=[{"name": os.path.basename(MODEL_PATH)}], import_animations=False,
                         import_physics=False, create_flex_drivers=False)


def bake_attachments() -> None:
    """SourceIO pins the attachment empties to bones with constraints; keep only their world placement."""
    bpy.context.view_layer.update()
    for empty in [candidate for candidate in bpy.data.objects if candidate.type == "EMPTY"]:
        world = empty.matrix_world.copy()
        for constraint in list(empty.constraints):
            empty.constraints.remove(constraint)
        empty.parent = None
        empty.matrix_world = world


def textures_to_png() -> list[str]:
    os.makedirs(TEXTURE_DIRECTORY, exist_ok=True)
    used = {node.image for mesh_object in bpy.data.objects if mesh_object.type == "MESH"
            for slot in mesh_object.material_slots if slot.material and slot.material.node_tree
            for node in slot.material.node_tree.nodes if node.type == "TEX_IMAGE" and node.image}
    written = []
    for image in sorted(used, key=lambda candidate: candidate.name):
        path = os.path.join(TEXTURE_DIRECTORY, f"{image.name.lower()}.png")
        image.file_format = _enum_identifier(bpy.types.Image, "file_format", PNG_FORMAT)
        image.save(filepath=path)
        converted = bpy.data.images.load(path, check_existing=False)
        converted.colorspace_settings.name = image.colorspace_settings.name
        image.user_remap(converted)
        bpy.data.images.remove(image)
        converted.name = os.path.splitext(os.path.basename(path))[0]
        written.append(path)
    return written


def remove_unused() -> None:
    for material in list(bpy.data.materials):
        if material.users == 0 or material.name.startswith("SIO"):
            bpy.data.materials.remove(material)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)


def report(textures: list[str]) -> None:
    armature = next(candidate for candidate in bpy.data.objects if candidate.type == "ARMATURE")
    face = bpy.data.objects[FACE_MESH_NAME]
    flexes = [block.name for block in face.data.shape_keys.key_blocks[1:]]
    print(f"armature {armature.name}: {len(armature.data.bones)} bones")
    print(f"{FACE_MESH_NAME}: {len(flexes)} face flexes")
    for mesh_object in sorted((candidate for candidate in bpy.data.objects if candidate.type == "MESH"),
                              key=lambda candidate: candidate.name):
        triangles = sum(len(polygon.vertices) - 2 for polygon in mesh_object.data.polygons)
        materials = [slot.material.name for slot in mesh_object.material_slots if slot.material]
        print(f"mesh {mesh_object.name}: {triangles} triangles, materials {materials}")
    for empty in sorted((candidate for candidate in bpy.data.objects if candidate.type == "EMPTY"),
                        key=lambda candidate: candidate.name):
        print(f"empty {empty.name} at {tuple(round(value, 4) for value in empty.matrix_world.translation)}")
    print(f"textures: {', '.join(os.path.basename(path) for path in textures)}")


def main() -> None:
    import_model()
    bake_attachments()
    textures = textures_to_png()
    remove_unused()
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH, relative_remap=True, compress=True)
    report(textures)


if __name__ in ("__main__", "builtins"):
    main()
    if bpy.app.background:
        sys.exit(0)
