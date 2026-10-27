"""Validate generated character .blend files.

Usage:
    Blender --background --factory-startup --python yandere_demo/blender/validate_assets.py -- --only target
"""

import argparse
import os
import sys

import bpy

BLENDER_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
if BLENDER_DIRECTORY not in sys.path:
    sys.path.insert(0, BLENDER_DIRECTORY)

from lib import astolfo  # noqa: E402
from lib.rig import (  # noqa: E402
    AHOGE_BONES, BRAID_BONES, HAIR_FRONT_BONES, HAIR_SIDE_BONES, HUMANOID_BONES, NECKERCHIEF_BONES, PONYTAIL_BONES,
    SKIRT_BONES, SLEEVE_BONES,
)
from lib.validate import validate_cast_extras, validate_character, validate_target_extras  # noqa: E402

# The game's five, the ten from spec 4.1b, and the two eye controls.
FACE_SHAPE_KEYS = [
    "neutral", "startled", "suspicious", "happy", "blink",
    "smile", "sad", "blush", "wink_L", "wink_R", "mouth_A", "mouth_I", "mouth_U", "mouth_E", "mouth_O",
    "pupil_small", "pupil_large",
]
# The Astolfo model's own mesh split (Task 23a).
TARGET_MESHES = list(astolfo.MESH_PARTS.values())
# Every humanoid bone, every renamed model bone (helpers, hair, bows, ribbons) and the added skirt chains.
TARGET_BONES = sorted(set(HUMANOID_BONES) | set(astolfo.bone_rename_map().values()) | set(SKIRT_BONES))
TARGET_HEIGHT = astolfo.CROWN_HEIGHT
TARGET_TRIANGLE_BUDGET = 100000
# Standing clips whose every frame must keep the thighs inside the skirt (full walk stride included).
SKIRT_CLEAR_ACTIONS = ["target_walk_routine", "target_idle", "target_idle_shy", "target_idle_playful", "target_idle_confident"]
# Standing clips whose braid and bow must rest on the skirt in every frame. Seated clips are left out: the bow lies
# on the lap there, where "further out from the hips' axis" no longer means "on top of the fabric".
BRAID_CLEAR_ACTIONS = ["target_idle", "target_walk_routine", "target_notice_player", "target_startled",
                       "target_look_around", "target_drink", "target_fix_braid", "target_lean_chat", "target_sweep",
                       "target_wave", "target_idle_shy", "target_idle_playful", "target_idle_confident"]
# Action name -> (frame count at 30 fps, loops).
TARGET_ACTIONS = {
    "target_idle": (90, True),
    "target_walk_routine": (32, True),
    "target_notice_player": (30, False),
    "target_startled": (20, False),
    "target_look_around": (120, True),
    "target_sit_down": (30, False),
    "target_stand_up": (30, False),
    "target_sit": (90, True),
    "target_sit_read": (120, True),
    "target_phone": (120, True),
    "target_drink": (120, True),
    "target_fix_braid": (150, True),
    "target_lean_chat": (120, True),
    "target_sweep": (60, True),
    "target_wave": (45, True),
    "target_idle_shy": (120, True),
    "target_idle_playful": (90, True),
    "target_idle_confident": (120, True),
}

PLAYER_ACTIONS = {
    "player_idle": (90, True),
    "player_walk": (24, True),
    "player_run": (20, True),
    "player_crouch_idle": (90, True),
    "player_sneak": (32, True),
    "player_take_photo": (90, True),
    "player_hide": (20, False),
    "player_sit": (90, True),
    "player_sit_down": (30, False),
    "player_stand_up": (30, False),
}
PLAYER_MESHES = ["Body", "Face", "Eyes", "Lashes", "Hair", "Ponytail", "Top", "Neckerchief", "Skirt", "Socks", "Shoes",
                 "Blush"]
PLAYER_SKIRT_CLEAR_ACTIONS = ["player_idle", "player_walk", "player_run", "player_sneak", "player_crouch_idle",
                              "player_take_photo"]
STUDENT_ACTIONS = {
    "student_idle": (90, True),
    "student_walk": (32, True),
    "student_sit": (90, True),
    "student_chat": (120, True),
}
TEACHER_ACTIONS = {
    "teacher_idle": (90, True),
    "teacher_walk": (32, True),
    "teacher_look_around": (120, True),
}
CAST_SHAPE_KEYS = ["neutral", "blink"]
# 6-10 students are on screen at once; one student with one hair style stays well under the target's ~91k.
STUDENT_TRIANGLE_BUDGET = 45000
TEACHER_TRIANGLE_BUDGET = 50000
STUDENT_ABSENT_BONES = [BRAID_BONES[0], AHOGE_BONES[0], NECKERCHIEF_BONES[0], PONYTAIL_BONES[0]]

CHECKS = {
    "target": {
        "blend": "target.blend",
        "prefix": "Target",
        "shape_keys": FACE_SHAPE_KEYS,
        "actions": TARGET_ACTIONS,
        "bones": TARGET_BONES,
        "meshes": TARGET_MESHES,
        "target_extras": {
            "height": TARGET_HEIGHT,
            "triangle_budget": TARGET_TRIANGLE_BUDGET,
            "skirt_clear_actions": SKIRT_CLEAR_ACTIONS,
            "braid_clear_actions": BRAID_CLEAR_ACTIONS,
        },
    },
    "player": {
        "blend": "player.blend",
        "prefix": "Player",
        "proxy": "Player-convcol",
        "shape_keys": FACE_SHAPE_KEYS,
        "actions": PLAYER_ACTIONS,
        "bones": (HUMANOID_BONES + PONYTAIL_BONES + HAIR_FRONT_BONES + HAIR_SIDE_BONES + NECKERCHIEF_BONES + SLEEVE_BONES
                  + SKIRT_BONES),
        "meshes": PLAYER_MESHES,
        "cast_extras": {
            "hair_variants": [],
            "absent_bones": [BRAID_BONES[0], AHOGE_BONES[0]],
            "tinted_meshes": [],
            "required_materials": ["M_UniformNavy", "M_Neckerchief", "M_Hair"],
            "height": 1.58,
            "skirt_clear_actions": PLAYER_SKIRT_CLEAR_ACTIONS,
        },
    },
    "student_female": {
        "blend": "student_female.blend",
        "prefix": "StudentFemale",
        "shape_keys": CAST_SHAPE_KEYS,
        "actions": STUDENT_ACTIONS,
        "bones": HUMANOID_BONES + SKIRT_BONES,
        "meshes": ["Body", "Face", "Eyes", "Lashes", "Top", "Neckerchief", "Skirt", "Socks", "Shoes"],
        "cast_extras": {
            "hair_variants": ["Hair_bob", "Hair_long", "Hair_twintails"],
            "absent_bones": STUDENT_ABSENT_BONES,
            "tinted_meshes": ["Top", "Skirt"],
            "required_materials": ["M_UniformTint", "M_UniformWhite"],
            "height": 1.56,
            "triangle_budget": STUDENT_TRIANGLE_BUDGET,
            "skirt_clear_actions": ["student_idle", "student_walk", "student_chat"],
        },
    },
    "student_male": {
        "blend": "student_male.blend",
        "prefix": "StudentMale",
        "shape_keys": CAST_SHAPE_KEYS,
        "actions": STUDENT_ACTIONS,
        "bones": HUMANOID_BONES,
        "meshes": ["Body", "Face", "Eyes", "Lashes", "Jacket", "Trousers", "Socks", "Shoes"],
        "cast_extras": {
            "hair_variants": ["Hair_short", "Hair_messy"],
            "absent_bones": STUDENT_ABSENT_BONES + [SKIRT_BONES[0]],
            "tinted_meshes": ["Jacket", "Trousers"],
            "required_materials": ["M_UniformTint", "M_UniformButton"],
            "height": 1.68,
            "triangle_budget": STUDENT_TRIANGLE_BUDGET,
        },
    },
    "teacher": {
        "blend": "teacher.blend",
        "prefix": "Teacher",
        "shape_keys": CAST_SHAPE_KEYS,
        "actions": TEACHER_ACTIONS,
        "bones": HUMANOID_BONES,
        "meshes": ["Body", "Face", "Eyes", "Lashes", "Hair", "Jacket", "Shirt", "Trousers", "Socks", "Shoes"],
        "cast_extras": {
            "hair_variants": [],
            "absent_bones": STUDENT_ABSENT_BONES + [SKIRT_BONES[0]],
            "tinted_meshes": [],
            "required_materials": ["M_Suit", "M_Shirt", "M_Tie"],
            "height": 1.75,
            "triangle_budget": TEACHER_TRIANGLE_BUDGET,
        },
    },
}


def parse_arguments() -> argparse.Namespace:
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Validate generated character assets.")
    parser.add_argument("--only", choices=sorted(CHECKS), help="validate a single asset")
    return parser.parse_args(arguments)


def run_check(check_name: str) -> list[str]:
    check = CHECKS[check_name]
    blend_path = os.path.join(BLENDER_DIRECTORY, check["blend"])
    if not os.path.exists(blend_path):
        return [f"{check['blend']} does not exist"]
    bpy.ops.wm.open_mainfile(filepath=blend_path)
    errors = validate_character(check["prefix"], check["shape_keys"], check["actions"], check["bones"], check["meshes"],
                                check.get("proxy"))
    if "target_extras" in check:
        extras = check["target_extras"]
        braid = astolfo.braid_layout(bpy.data.objects[f"{check['prefix']}Char"])
        errors += validate_target_extras(check["prefix"], extras["height"], extras["triangle_budget"], check["bones"],
                                         braid.resting_bones + braid.bow_bones, braid.meshes,
                                         extras["skirt_clear_actions"], extras["braid_clear_actions"])
    if "cast_extras" in check:
        errors += validate_cast_extras(check["prefix"], check["shape_keys"], **check["cast_extras"])
    return errors


def main() -> int:
    options = parse_arguments()
    check_names = [options.only] if options.only else sorted(CHECKS)
    failed = False
    for check_name in check_names:
        errors = run_check(check_name)
        for error in errors:
            print(f"FAIL {check_name}: {error}")
        if errors:
            failed = True
        else:
            print(f"PASS {check_name}")
    return 1 if failed else 0


# blender-mcp's exec(source, {"__file__": path}) leaves __name__ as "builtins".
if __name__ in ("__main__", "builtins"):
    exit_code = main()
    if bpy.app.background:
        sys.exit(exit_code)
