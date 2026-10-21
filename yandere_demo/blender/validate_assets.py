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

from lib.rig import BRAID_BONES, HUMANOID_BONES, SKIRT_BONES  # noqa: E402
from lib.validate import validate_character  # noqa: E402

FACE_SHAPE_KEYS = ["neutral", "startled", "suspicious", "happy", "blink"]
TARGET_MESHES = ["Body", "Head", "Face", "Hair", "Braid", "Bows", "Uniform"]
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
}

CHECKS = {
    "target": {
        "blend": "target.blend",
        "prefix": "Target",
        "shape_keys": FACE_SHAPE_KEYS,
        "actions": TARGET_ACTIONS,
        "bones": HUMANOID_BONES + BRAID_BONES + SKIRT_BONES,
        "meshes": TARGET_MESHES,
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
    return validate_character(check["prefix"], check["shape_keys"], check["actions"], check["bones"], check["meshes"])


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
