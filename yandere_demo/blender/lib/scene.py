"""Scene setup and output shared by the character build scripts."""

import os

import bpy

from . import export
from .animation import FPS


def reset_scene() -> None:
    """Remove every datablock a character build creates, so `principled` never meets another build's materials."""
    # Right after open_mainfile in the same MCP call the context has no `object`; the view layer always does.
    active = bpy.context.view_layer.objects.active
    if active is not None and active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for collection in (bpy.data.objects, bpy.data.meshes, bpy.data.armatures, bpy.data.materials,
                       bpy.data.images, bpy.data.actions, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for block in list(collection):
            collection.remove(block)


def start_character_scene() -> None:
    reset_scene()
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.render.fps_base = 1.0


def save_and_export(armature, blend_path: str, glb_path: str) -> None:
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    export.export_glb(glb_path, [armature])
    print(f"built {armature.name}: {os.path.basename(blend_path)}, {os.path.basename(glb_path)}")
