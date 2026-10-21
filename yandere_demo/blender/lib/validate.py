"""Structural checks for generated character assets, run inside Blender."""

import bpy

PROXY_MATERIAL_NAME = "M_CollisionProxy"
IDENTITY_TOLERANCE = 1e-5


def validate_character(
    prefix: str,
    required_shape_keys: list[str],
    required_actions: list[str],
    required_bones: list[str],
    required_meshes: list[str] | None = None,
) -> list[str]:
    """Return error strings. `required_meshes` are part names, checked as f"{prefix}{part}" mesh children."""
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

    for action_name in required_actions:
        if bpy.data.actions.get(action_name) is None:
            errors.append(f"action {action_name} is missing")
    return errors


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
