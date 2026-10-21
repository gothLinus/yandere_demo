"""Build the target character, save blender/target.blend and export assets/models/target.glb.

CLI:  Blender --background --factory-startup --python yandere_demo/blender/build_target.py
MCP:  exec(open(path).read(), {"__file__": path})
"""

import importlib
import os
import sys

import bpy

BLENDER_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIRECTORY = os.path.dirname(BLENDER_DIRECTORY)
if BLENDER_DIRECTORY not in sys.path:
    sys.path.insert(0, BLENDER_DIRECTORY)

from lib import body, clothing, export, face, hair, materials, mesh_utils, rig  # noqa: E402

# A live Blender session keeps modules cached between runs; reload so edits take effect.
for module in (materials, mesh_utils, rig, body, face, hair, clothing, export):
    importlib.reload(module)

BLEND_PATH = os.path.join(BLENDER_DIRECTORY, "target.blend")
GLB_PATH = os.path.join(PROJECT_DIRECTORY, "assets", "models", "target.glb")
EYE_TEXTURE_PATH = os.path.join(PROJECT_DIRECTORY, "assets", "textures", "target_eye.png")

TARGET_PARAMS = body.CharacterParams(
    prefix="Target",
    height=1.58,
    hair_color="#f4a7c0",
    hair_shade_color="#e58aa8",
    hair_streak_color="#fbf3f5",
    eye_color="#9b6bd6",
    uniform="sailor_red",
    hair_style="target",
    body_type="female",
)


def reset_scene() -> None:
    # Right after open_mainfile in the same MCP call the context has no `object`; the view layer always does.
    active = bpy.context.view_layer.objects.active
    if active is not None and active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for collection in (bpy.data.objects, bpy.data.meshes, bpy.data.armatures, bpy.data.materials,
                       bpy.data.images, bpy.data.actions, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for block in list(collection):
            collection.remove(block)


def build_target(params: body.CharacterParams) -> bpy.types.Object:
    armature = rig.build_armature(f"{params.prefix}Char", params.height, body.body_proportions(params))
    # Heat weighting runs before the braid and skirt chains exist, so those bones never claim body skin.
    body_object = body.build_body(armature, params)
    hair.add_braid_chain(armature, params)
    clothing.add_skirt_bones(armature, params)
    head = face.build_head(armature, params)
    face.paint_eye_texture(EYE_TEXTURE_PATH, materials.hex_to_srgb(params.eye_color), highlight=True)
    face.build_face_features(head, params, EYE_TEXTURE_PATH)
    hair.build_hair(head, armature, params)
    hair.build_braid(armature, params)
    hair.build_bows(params, armature)
    clothing.build_sailor_uniform(body_object, params, armature)
    clothing.build_collision_proxy(armature, params)
    for child in armature.children:
        if child.type == "MESH" and child.vertex_groups:
            mesh_utils.limit_influences(child)
    return armature


def main() -> None:
    reset_scene()
    armature = build_target(TARGET_PARAMS)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    export.export_glb(GLB_PATH, [armature])
    print(f"built {armature.name}: {BLEND_PATH}, {GLB_PATH}")


# blender-mcp's exec(source, {"__file__": path}) leaves __name__ as "builtins".
if __name__ in ("__main__", "builtins"):
    main()
