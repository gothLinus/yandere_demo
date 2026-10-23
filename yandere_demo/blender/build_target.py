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

from lib import (  # noqa: E402
    animation, body, character_animation, clothing, export, face, hair, materials, mesh_utils, pleats, rig, scene,
    target_animations,
)

# A live Blender session keeps modules cached between runs; reload so edits take effect.
for module in (materials, mesh_utils, rig, body, face, pleats, hair, clothing, export, animation, character_animation,
               target_animations, scene):
    importlib.reload(module)

BLEND_PATH = os.path.join(BLENDER_DIRECTORY, "target.blend")
GLB_PATH = os.path.join(PROJECT_DIRECTORY, "assets", "models", "target.glb")
EYE_TEXTURE_PATH = os.path.join(PROJECT_DIRECTORY, "assets", "textures", "target_eye.png")
HAIR_TEXTURE_PATH = os.path.join(PROJECT_DIRECTORY, "assets", "textures", "target_hair.png")

TARGET_PARAMS = body.CharacterParams(
    prefix="Target",
    height=1.62,
    hair_color="#f4a7c0",
    hair_shade_color="#e58aa8",
    hair_streak_color="#fbf3f5",
    eye_color="#9b6bd6",
    uniform="sailor_red",
    hair_style="target",
    body_type="femboy",
    sock_top_fraction=0.47,
    extra={"hair_texture": HAIR_TEXTURE_PATH},
)


def build_target(params: body.CharacterParams) -> bpy.types.Object:
    armature = rig.build_armature(f"{params.prefix}Char", params.height, body.body_proportions(params))
    # Heat weighting runs before the secondary chains exist, so those bones never claim body skin.
    body_object = body.build_body(armature, params)
    body.build_socks(body_object, params)
    hair.add_braid_chain(armature, params)
    hair.add_hair_chains(armature, params)
    pleats.add_skirt_bones(armature, params, clothing.HEM_FLARE)
    clothing.add_sleeve_bones(armature)
    head = face.build_head(armature, params)
    face.paint_eye_texture(EYE_TEXTURE_PATH, materials.hex_to_srgb(params.eye_color), highlight=False, pupil=False)
    face_object = face.build_face_features(head, params, EYE_TEXTURE_PATH)
    face.build_blush(face_object, params)
    hair.paint_hair_texture(HAIR_TEXTURE_PATH, params)
    hair.build_hair(face_object, armature, params)
    hair.build_braid(armature, params)
    uniform = clothing.build_sailor_uniform(body_object, params, armature)
    clothing.build_accessories(params, armature, uniform["collar_pin"])
    clothing.build_collision_proxy(armature, params)
    for child in armature.children:
        if child.type == "MESH" and child.vertex_groups:
            mesh_utils.limit_influences(child)
    return armature


def main() -> None:
    scene.start_character_scene()
    armature = build_target(TARGET_PARAMS)
    target_animations.build_target_actions(armature)
    scene.save_and_export(armature, BLEND_PATH, GLB_PATH)


# blender-mcp's exec(source, {"__file__": path}) leaves __name__ as "builtins".
if __name__ in ("__main__", "builtins"):
    main()
