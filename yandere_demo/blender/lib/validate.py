"""Structural checks for generated character assets, run inside Blender."""

import bpy

PROXY_MATERIAL_NAME = "M_CollisionProxy"
IDENTITY_TOLERANCE = 1e-5
LOOP_SEAM_TOLERANCE = 1e-4
ANIMATION_FPS = 30


def validate_character(
    prefix: str,
    required_shape_keys: list[str],
    required_actions: dict[str, tuple[int, bool]],
    required_bones: list[str],
    required_meshes: list[str] | None = None,
) -> list[str]:
    """Return error strings.

    `required_actions` maps action name to (frame count, loops). `required_meshes` are part names,
    checked as f"{prefix}{part}" mesh children.
    """
    errors: list[str] = []
    armature = bpy.data.objects.get(f"{prefix}Char")
    if armature is None or armature.type != "ARMATURE":
        return [f"armature {prefix}Char is missing"]

    bone_names = {bone.name for bone in armature.data.bones}
    for bone_name in required_bones:
        if bone_name not in bone_names:
            errors.append(f"bone {bone_name} is missing from {armature.name}")

    for part in required_meshes or []:
        mesh_object = bpy.data.objects.get(f"{prefix}{part}")
        if mesh_object is None or mesh_object.type != "MESH" or mesh_object.parent != armature:
            errors.append(f"mesh {prefix}{part} is missing or not parented to {armature.name}")

    errors.extend(_validate_face(prefix, required_shape_keys))
    errors.extend(_validate_collision_proxy(prefix, armature))
    errors.extend(_validate_meshes(armature))

    errors.extend(_validate_actions(armature, required_actions))
    return errors


def _validate_actions(armature, required_actions: dict[str, tuple[int, bool]]) -> list[str]:
    errors: list[str] = []
    if required_actions and bpy.context.scene.render.fps != ANIMATION_FPS:
        errors.append(f"scene runs at {bpy.context.scene.render.fps} fps, expected {ANIMATION_FPS}")
    animation_data = armature.animation_data
    strip_actions = set()
    if animation_data is not None:
        strip_actions = {strip.action.name for track in animation_data.nla_tracks for strip in track.strips if strip.action}
    for action_name, (frame_count, loops) in required_actions.items():
        action = bpy.data.actions.get(action_name)
        if action is None:
            errors.append(f"action {action_name} is missing")
            continue
        if action_name not in strip_actions:
            errors.append(f"action {action_name} has no NLA strip on {armature.name}")
        frame_range = tuple(round(value) for value in action.frame_range)
        if frame_range != (0, frame_count):
            errors.append(f"action {action_name} spans frames {frame_range}, expected (0, {frame_count})")
        if loops:
            for fcurve in action_fcurves(action):
                points = fcurve.keyframe_points
                if len(points) and abs(points[0].co[1] - points[-1].co[1]) > LOOP_SEAM_TOLERANCE:
                    errors.append(f"action {action_name} loops but {fcurve.data_path}[{fcurve.array_index}] differs at the seam")
                    break
    return errors


def action_fcurves(action) -> list:
    """F-curves of every layer, strip and slot (Blender 4.4+ layered actions)."""
    fcurves = []
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                fcurves.extend(channelbag.fcurves)
    return fcurves


def _validate_face(prefix: str, required_shape_keys: list[str]) -> list[str]:
    face = bpy.data.objects.get(f"{prefix}Face")
    if face is None:
        return [f"face mesh {prefix}Face is missing"] if required_shape_keys else []
    keys = face.data.shape_keys
    names = sorted(block.name for block in keys.key_blocks) if keys else []
    expected = sorted(["Basis"] + list(required_shape_keys))
    if names != expected:
        return [f"{face.name} shape keys are {names}, expected exactly {expected}"]
    return []


def _validate_collision_proxy(prefix: str, armature) -> list[str]:
    errors: list[str] = []
    proxy = bpy.data.objects.get(f"{prefix}-col")
    if proxy is None:
        return [f"collision proxy {prefix}-col is missing"]
    if proxy.parent != armature:
        errors.append(f"{proxy.name} must be parented to {armature.name}")
    if proxy.parent_bone:
        errors.append(f"{proxy.name} must not be parented to a bone")
    material_names = [slot.material.name for slot in proxy.material_slots if slot.material]
    if material_names != [PROXY_MATERIAL_NAME]:
        errors.append(f"{proxy.name} must use only {PROXY_MATERIAL_NAME}, has {material_names}")
    if not _is_identity(proxy.matrix_local):
        errors.append(f"{proxy.name} must sit at an identity transform under {armature.name}")
    return errors


def _validate_meshes(armature) -> list[str]:
    errors: list[str] = []
    meshes = [child for child in armature.children_recursive if child.type == "MESH"]
    if not meshes:
        errors.append(f"{armature.name} has no mesh children")
    for mesh_object in meshes:
        if not mesh_object.material_slots:
            errors.append(f"{mesh_object.name} has no material")
        for slot in mesh_object.material_slots:
            if slot.material is None or not slot.material.name.startswith("M_"):
                errors.append(f"{mesh_object.name} has a material not named M_<Part>")
        unapplied = [modifier.name for modifier in mesh_object.modifiers if modifier.type != "ARMATURE"]
        if unapplied:
            errors.append(f"{mesh_object.name} has unapplied modifiers {unapplied}")
        if mesh_object.name.endswith("-col"):
            continue
        if not any(modifier.type == "ARMATURE" for modifier in mesh_object.modifiers):
            errors.append(f"{mesh_object.name} is not skinned to {armature.name}")
        if not mesh_object.vertex_groups:
            errors.append(f"{mesh_object.name} has no vertex groups")
    return errors


def _is_identity(matrix) -> bool:
    for row in range(4):
        for column in range(4):
            expected = 1.0 if row == column else 0.0
            if abs(matrix[row][column] - expected) > IDENTITY_TOLERANCE:
                return False
    return True
