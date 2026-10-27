"""Build the target character from the Astolfo source, save blender/target.blend and export assets/models/target.glb.

The source is blender/source/astolfo/astolfo_source.blend (written once by import_astolfo_source.py), so this build
needs no SourceIO. lib/astolfo.py converts the model to the target contract; lib/target_animations.py keys the clips.

CLI:  Blender --background --factory-startup --python yandere_demo/blender/build_target.py
MCP:  exec(open(path).read(), {"__file__": path})
"""

import importlib
import os
import sys

BLENDER_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIRECTORY = os.path.dirname(BLENDER_DIRECTORY)
if BLENDER_DIRECTORY not in sys.path:
    sys.path.insert(0, BLENDER_DIRECTORY)

from lib import (  # noqa: E402
    animation, astolfo, body, character_animation, clothing, export, materials, mesh_utils, pleats, rig, scene,
    target_animations,
)

# A live Blender session keeps modules cached between runs; reload so edits take effect.
for module in (materials, mesh_utils, rig, body, pleats, clothing, export, animation, character_animation,
               target_animations, astolfo, scene):
    importlib.reload(module)

SOURCE_DIRECTORY = os.path.join(BLENDER_DIRECTORY, "source", "astolfo")
SOURCE_BLEND_PATH = os.path.join(SOURCE_DIRECTORY, "astolfo_source.blend")
TEXTURE_DIRECTORY = os.path.join(SOURCE_DIRECTORY, "textures")
BLEND_PATH = os.path.join(BLENDER_DIRECTORY, "target.blend")
GLB_PATH = os.path.join(PROJECT_DIRECTORY, "assets", "models", "target.glb")


def main() -> None:
    scene.start_character_scene()
    source_armature, meshes = astolfo.load_source(SOURCE_BLEND_PATH)
    armature, landmarks = astolfo.convert(source_armature, meshes, TEXTURE_DIRECTORY)
    stance = astolfo.measure_stance(armature, meshes, landmarks)
    target_animations.build_target_actions(armature, stance, astolfo.braid_layout(armature))
    scene.save_and_export(armature, BLEND_PATH, GLB_PATH)
    print(astolfo.secondary_motion_report(armature, meshes))
    print("TargetProps.PROP_PLACEMENTS:\n" + target_animations.godot_prop_placements(animation.Skeleton(armature)))
    print(f"eyes at {tuple(round(value, 4) for value in landmarks.eyes)}, mouth at "
          f"{tuple(round(value, 4) for value in landmarks.mouth)}, seat clearance {stance.seat_clearance:.4f}, "
          f"heel back {stance.heel_back:.4f}, lap offset {tuple(round(value, 4) for value in stance.lap_offset)}, "
          f"leg radii {tuple(round(value, 4) for value in stance.leg_radii)}, seated leg radii "
          f"{tuple(round(value, 4) for value in stance.seated_leg_radii)}")


# blender-mcp's exec(source, {"__file__": path}) leaves __name__ as "builtins".
if __name__ in ("__main__", "builtins"):
    main()
