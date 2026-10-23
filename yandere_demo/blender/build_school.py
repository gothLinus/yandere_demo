"""Build the school environment, save blender/school.blend and export assets/models/school.glb.

CLI:  Blender --background --factory-startup --python yandere_demo/blender/build_school.py
MCP:  exec(open(path).read(), {"__file__": path})
"""

import importlib
import os
import sys

BLENDER_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIRECTORY = os.path.dirname(BLENDER_DIRECTORY)
if BLENDER_DIRECTORY not in sys.path:
    sys.path.insert(0, BLENDER_DIRECTORY)

from lib import export, materials, mesh_utils, scene, school  # noqa: E402

# A live Blender session keeps modules cached between runs; reload so edits take effect.
for module in (materials, mesh_utils, export, scene, school):
    importlib.reload(module)

BLEND_PATH = os.path.join(BLENDER_DIRECTORY, "school.blend")
GLB_PATH = os.path.join(PROJECT_DIRECTORY, "assets", "models", "school.glb")
CHAIN_LINK_TEXTURE_PATH = os.path.join(PROJECT_DIRECTORY, "assets", "textures", "chain_link.png")


def main() -> None:
    scene.reset_scene()
    root = school.build_school(CHAIN_LINK_TEXTURE_PATH)
    scene.save_and_export(root, BLEND_PATH, GLB_PATH)


# blender-mcp's exec(source, {"__file__": path}) leaves __name__ as "builtins".
if __name__ in ("__main__", "builtins"):
    main()
