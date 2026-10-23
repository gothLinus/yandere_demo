"""Run every character build script in sequence: the target, the player, the students and the teacher.

CLI:  Blender --background --factory-startup --python yandere_demo/blender/build_all.py
"""

import os
import runpy

BLENDER_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
BUILD_SCRIPTS = ["build_target.py", "build_player.py", "build_students.py", "build_teacher.py"]


def main() -> None:
    for script in BUILD_SCRIPTS:
        runpy.run_path(os.path.join(BLENDER_DIRECTORY, script), run_name="__main__")


if __name__ in ("__main__", "builtins"):
    main()
