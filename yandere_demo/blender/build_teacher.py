"""Build the teacher, save blender/teacher.blend and export assets/models/teacher.glb.

CLI:  Blender --background --factory-startup --python yandere_demo/blender/build_teacher.py
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

BLEND_PATH = os.path.join(BLENDER_DIRECTORY, "teacher.blend")
GLB_PATH = os.path.join(PROJECT_DIRECTORY, "assets", "models", "teacher.glb")
# The background cast shares one eye texture.
EYE_TEXTURE_PATH = os.path.join(PROJECT_DIRECTORY, "assets", "textures", "student_eye.png")

TEACHER_PARAMS = body.CharacterParams(
    prefix="Teacher",
    height=1.75,
    skin_color="#f1cfbb",
    hair_color="#3a3430",
    hair_shade_color="#241f1c",
    hair_streak_color="#4a433e",
    eye_color="#6b4a3a",
    uniform="suit",
    hair_style="short_male",
    body_type="adult",
    sock_top_fraction=0.075,
    sock_color="#1d1e26",
    subdivision_levels=1,
)


def build_teacher(params: body.CharacterParams) -> bpy.types.Object:
    armature, body_object = cast.build_figure(params)
    face_object = cast.build_face(armature, params, EYE_TEXTURE_PATH, ["neutral", "blink"])
    hair.build_hair(face_object, armature, params)
    clothing.build_suit(body_object, params, armature)
    clothing.build_collision_proxy(armature, params, radius=0.24)
    cast.finish(armature)
    return armature


def main() -> None:
    scene.start_character_scene()
    armature = build_teacher(TEACHER_PARAMS)
    stance = cast_animations.teacher_stance(cast_animations.face_landmarks(armature))
    cast_animations.build_cast_actions(armature, stance, cast_animations.teacher_clips)
    scene.save_and_export(armature, BLEND_PATH, GLB_PATH)


# blender-mcp's exec(source, {"__file__": path}) leaves __name__ as "builtins".
if __name__ in ("__main__", "builtins"):
    main()
