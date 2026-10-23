"""Build the two background students, save blender/student_female.blend and student_male.blend and export
assets/models/student_female.glb and student_male.glb.

Each carries every hair style of its kind as a separate `Hair_<style>` mesh; Godot shows one of them and tints
`M_UniformTint` per student.

CLI:  Blender --background --factory-startup --python yandere_demo/blender/build_students.py
MCP:  exec(open(path).read(), {"__file__": path})
"""

import importlib
import os
import sys
from dataclasses import replace

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

MODELS_DIRECTORY = os.path.join(PROJECT_DIRECTORY, "assets", "models")
EYE_TEXTURE_PATH = os.path.join(PROJECT_DIRECTORY, "assets", "textures", "student_eye.png")
SHAPE_KEYS = ["neutral", "blink"]
# The pleat generator's minimum: a crowd of 6-10 stays lighter than the target's 20.
STUDENT_PLEAT_COUNT = 16
STUDENT_EYE_COLOR = "#6b4a3a"

FEMALE_PARAMS = body.CharacterParams(
    prefix="StudentFemale",
    height=1.56,
    hair_color="#5a3d2e",
    hair_shade_color="#3d281e",
    hair_streak_color="#6e4c3a",
    eye_color=STUDENT_EYE_COLOR,
    uniform="sailor_tint",
    hair_style="bob",
    body_type="female",
    sock_top_fraction=0.27,
    sock_color="#2b2f45",
    subdivision_levels=1,
)
# `Hair_<name>` mesh name -> generator hair style.
FEMALE_HAIR_STYLES = {"bob": "bob", "long": "long", "twintails": "twintails"}

MALE_PARAMS = body.CharacterParams(
    prefix="StudentMale",
    height=1.68,
    skin_color="#f3d2bf",
    hair_color="#2b2420",
    hair_shade_color="#1a1513",
    hair_streak_color="#3a312b",
    eye_color=STUDENT_EYE_COLOR,
    uniform="gakuran",
    hair_style="short_male",
    body_type="male",
    sock_top_fraction=0.075,
    sock_color="#1d1e26",
    subdivision_levels=1,
)
MALE_HAIR_STYLES = {"short": "short_male", "messy": "messy_male"}


def build_hair_variants(face_object, armature, params: body.CharacterParams, styles: dict) -> list:
    """One `Hair_<name>` mesh per entry of `styles`."""
    return [hair.build_hair(face_object, armature, replace(params, hair_style=style), name=f"Hair_{name}")
            for name, style in styles.items()]


def build_student_female(params: body.CharacterParams) -> bpy.types.Object:
    armature, body_object = cast.build_figure(params)
    pleats.add_skirt_bones(armature, params, clothing.HEM_FLARE)
    face_object = cast.build_face(armature, params, EYE_TEXTURE_PATH, SHAPE_KEYS)
    build_hair_variants(face_object, armature, params, FEMALE_HAIR_STYLES)
    clothing.build_sailor_uniform(body_object, params, armature, STUDENT_PLEAT_COUNT, neckerchief_chains=False)
    clothing.build_collision_proxy(armature, params)
    cast.finish(armature)
    return armature


def build_student_male(params: body.CharacterParams) -> bpy.types.Object:
    armature, body_object = cast.build_figure(params)
    face_object = cast.build_face(armature, params, EYE_TEXTURE_PATH, SHAPE_KEYS)
    build_hair_variants(face_object, armature, params, MALE_HAIR_STYLES)
    clothing.build_gakuran(body_object, params, armature)
    clothing.build_collision_proxy(armature, params)
    cast.finish(armature)
    return armature


def build_and_export(name: str, build, params: body.CharacterParams, stance_for) -> None:
    scene.start_character_scene()
    armature = build(params)
    stance = stance_for(cast_animations.face_landmarks(armature))
    cast_animations.build_cast_actions(armature, stance, cast_animations.student_clips)
    scene.save_and_export(armature, os.path.join(BLENDER_DIRECTORY, f"{name}.blend"),
                          os.path.join(MODELS_DIRECTORY, f"{name}.glb"))


def main() -> None:
    build_and_export("student_female", build_student_female, FEMALE_PARAMS, cast_animations.student_female_stance)
    build_and_export("student_male", build_student_male, MALE_PARAMS, cast_animations.student_male_stance)


# blender-mcp's exec(source, {"__file__": path}) leaves __name__ as "builtins".
if __name__ in ("__main__", "builtins"):
    main()
