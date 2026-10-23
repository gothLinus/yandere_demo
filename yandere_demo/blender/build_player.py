"""Build the player, save blender/player.blend and export assets/models/player.glb.

CLI:  Blender --background --factory-startup --python yandere_demo/blender/build_player.py
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
    animation, body, cast, cast_animations, character_animation, clothing, export, face, hair, materials, mesh_utils,
    pleats, rig, scene,
)

# A live Blender session keeps modules cached between runs; reload so edits take effect.
for module in (materials, mesh_utils, rig, body, face, pleats, hair, clothing, export, animation, character_animation,
               cast, cast_animations, scene):
    importlib.reload(module)

BLEND_PATH = os.path.join(BLENDER_DIRECTORY, "player.blend")
GLB_PATH = os.path.join(PROJECT_DIRECTORY, "assets", "models", "player.glb")
EYE_TEXTURE_PATH = os.path.join(PROJECT_DIRECTORY, "assets", "textures", "player_eye.png")

PLAYER_PARAMS = body.CharacterParams(
    prefix="Player",
    height=1.58,
    hair_color="#26232d",
    hair_shade_color="#131118",
    hair_streak_color="#3a3644",
    eye_color="#8a8f9c",
    uniform="sailor_navy",
    hair_style="ponytail",
    body_type="female",
    sock_color="#25232b",
    extra={"hair_tie_color": "#b8243a"},
)


def build_player(params: body.CharacterParams) -> bpy.types.Object:
    armature, body_object = cast.build_figure(params)
    hair.add_hair_chains(armature, params)
    hair.add_ponytail_chain(armature)
    pleats.add_skirt_bones(armature, params, clothing.HEM_FLARE)
    clothing.add_sleeve_bones(armature)
    face_object = cast.build_face(armature, params, EYE_TEXTURE_PATH, face.FACE_SHAPE_KEYS)
    face.build_blush(face_object, params)
    hair.build_hair(face_object, armature, params)
    hair.build_ponytail(armature, params)
    clothing.build_sailor_uniform(body_object, params, armature)
    clothing.build_collision_proxy(armature, params, name="Player-convcol")
    cast.finish(armature)
    return armature


def main() -> None:
    scene.start_character_scene()
    armature = build_player(PLAYER_PARAMS)
    landmarks = cast_animations.face_landmarks(armature)
    cast_animations.build_cast_actions(armature, cast_animations.player_stance(landmarks),
                                       lambda character_rig: cast_animations.player_clips(character_rig, landmarks))
    scene.save_and_export(armature, BLEND_PATH, GLB_PATH)


# blender-mcp's exec(source, {"__file__": path}) leaves __name__ as "builtins".
if __name__ in ("__main__", "builtins"):
    main()
