"""Humanoid armature shared by every character, plus helper bone chains."""

import math

import bpy
from mathutils import Vector

HUMANOID_BONES = [
    "root", "hips", "spine", "chest", "neck", "head",
    "shoulder.L", "shoulder.R", "upper_arm.L", "upper_arm.R",
    "forearm.L", "forearm.R", "hand.L", "hand.R",
    "thumb.L", "thumb.R", "fingers.L", "fingers.R",
    "thigh.L", "thigh.R", "shin.L", "shin.R",
    "foot.L", "foot.R", "toe.L", "toe.R",
]
BRAID_BONES = [f"braid_{index:02d}" for index in range(1, 7)]
SKIRT_SIDES = ["front", "back", "left", "right"]
SKIRT_BONES = [f"skirt_{side}_{index:02d}" for side in SKIRT_SIDES for index in (1, 2)]
PONYTAIL_BONES = [f"ponytail_{index:02d}" for index in range(1, 5)]

# Landmarks as fractions of the character height. The character faces -Y, so its left side is +X.
DEFAULT_PROPORTIONS = {
    "pelvis_z": 0.589,
    "spine_z": 0.639,
    "chest_z": 0.715,
    "neck_z": 0.816,
    "head_z": 0.864,
    "shoulder_x": 0.085,
    "shoulder_z": 0.800,
    "clavicle_x": 0.014,
    "upper_arm_length": 0.155,
    "forearm_length": 0.140,
    "hand_length": 0.085,
    "arm_drop_degrees": 62.0,
    "hip_x": 0.053,
    "hip_z": 0.551,
    "knee_z": 0.297,
    "ankle_z": 0.047,
    "foot_length": 0.140,
}


def build_armature(name: str, height: float, proportions: dict) -> bpy.types.Object:
    landmarks = dict(DEFAULT_PROPORTIONS)
    landmarks.update(proportions or {})
    armature_data = bpy.data.armatures.new(name)
    armature = bpy.data.objects.new(name, armature_data)
    bpy.context.scene.collection.objects.link(armature)
    armature.show_in_front = True

    with _EditMode(armature):
        for bone_name, head, tail, parent, deform in _humanoid_layout(height, landmarks):
            _new_bone(armature, bone_name, head, tail, parent, deform)
    return armature


def bone_world_points(armature, bone_name: str) -> tuple[Vector, Vector]:
    bone = armature.data.bones[bone_name]
    matrix = armature.matrix_world
    return matrix @ bone.head_local, matrix @ bone.tail_local


def add_chain(armature, prefix: str, parent: str, points: list[Vector]) -> list[str]:
    names: list[str] = []
    with _EditMode(armature):
        previous = parent
        for index in range(len(points) - 1):
            bone_name = f"{prefix}_{index + 1:02d}"
            _new_bone(armature, bone_name, points[index], points[index + 1], previous, True)
            names.append(bone_name)
            previous = bone_name
    return names


def add_skirt_chains(armature, waist_z: float, hem_z: float, radius_x: float, radius_y: float) -> list[str]:
    directions = {"front": Vector((0, -1, 0)), "back": Vector((0, 1, 0)), "left": Vector((1, 0, 0)), "right": Vector((-1, 0, 0))}
    names: list[str] = []
    for side in SKIRT_SIDES:
        direction = directions[side]
        points = []
        for fraction, flare in ((0.0, 1.0), (0.5, 1.35), (1.0, 1.75)):
            z = waist_z + (hem_z - waist_z) * fraction
            points.append(Vector((direction.x * radius_x * flare, direction.y * radius_y * flare, z)))
        names += add_chain(armature, f"skirt_{side}", "hips", points)
    return names


def _humanoid_layout(height: float, landmarks: dict) -> list[tuple]:
    def scaled(key: str) -> float:
        return landmarks[key] * height

    pelvis = Vector((0, 0, scaled("pelvis_z")))
    spine = Vector((0, 0.004, scaled("spine_z")))
    chest = Vector((0, 0.006, scaled("chest_z")))
    neck = Vector((0, 0.008, scaled("neck_z")))
    head = Vector((0, 0.004, scaled("head_z")))
    head_top = Vector((0, 0.004, height))
    layout = [
        ("root", Vector((0, 0, 0)), Vector((0, 0.15, 0)), None, False),
        ("hips", pelvis, spine, "root", True),
        ("spine", spine, chest, "hips", True),
        ("chest", chest, neck, "spine", True),
        ("neck", neck, head, "chest", True),
        ("head", head, head_top, "neck", True),
    ]
    drop = math.radians(landmarks["arm_drop_degrees"])
    for side, sign in ((".L", 1.0), (".R", -1.0)):
        clavicle = Vector((sign * scaled("clavicle_x"), 0.006, scaled("shoulder_z")))
        shoulder = Vector((sign * scaled("shoulder_x"), 0.008, scaled("shoulder_z")))
        arm_direction = Vector((sign * math.cos(drop), 0.02, -math.sin(drop))).normalized()
        elbow = shoulder + arm_direction * scaled("upper_arm_length") + Vector((0, 0.012, 0))
        wrist = elbow + arm_direction * scaled("forearm_length") + Vector((0, -0.02, 0))
        hand_end = wrist + arm_direction * scaled("hand_length") * 0.45
        finger_end = wrist + arm_direction * scaled("hand_length")
        thumb_base = wrist + Vector((0, -0.018, -0.008))
        thumb_end = thumb_base + arm_direction * scaled("hand_length") * 0.4 + Vector((0, -0.02, 0))
        hip = Vector((sign * scaled("hip_x"), 0, scaled("hip_z")))
        knee = Vector((sign * scaled("hip_x") * 0.92, -0.008, scaled("knee_z")))
        ankle = Vector((sign * scaled("hip_x") * 0.85, 0.012, scaled("ankle_z")))
        ball = Vector((sign * scaled("hip_x") * 0.85, ankle.y - scaled("foot_length") * 0.6, 0.022))
        toe_tip = Vector((sign * scaled("hip_x") * 0.85, ankle.y - scaled("foot_length"), 0.018))
        layout += [
            (f"shoulder{side}", clavicle, shoulder, "chest", True),
            (f"upper_arm{side}", shoulder, elbow, f"shoulder{side}", True),
            (f"forearm{side}", elbow, wrist, f"upper_arm{side}", True),
            (f"hand{side}", wrist, hand_end, f"forearm{side}", True),
            (f"thumb{side}", thumb_base, thumb_end, f"hand{side}", True),
            (f"fingers{side}", hand_end, finger_end, f"hand{side}", True),
            (f"thigh{side}", hip, knee, "hips", True),
            (f"shin{side}", knee, ankle, f"thigh{side}", True),
            (f"foot{side}", ankle, ball, f"shin{side}", True),
            (f"toe{side}", ball, toe_tip, f"foot{side}", True),
        ]
    order = {name: index for index, name in enumerate(HUMANOID_BONES)}
    return sorted(layout, key=lambda entry: order[entry[0]])


def _new_bone(armature, bone_name: str, head: Vector, tail: Vector, parent: str | None, deform: bool) -> None:
    bone = armature.data.edit_bones.new(bone_name)
    bone.head = head
    bone.tail = tail
    bone.use_deform = deform
    if parent:
        bone.parent = armature.data.edit_bones[parent]
        bone.use_connect = (bone.parent.tail - head).length < 1e-4


class _EditMode:
    def __init__(self, armature):
        self.armature = armature

    def __enter__(self):
        bpy.context.view_layer.objects.active = self.armature
        bpy.ops.object.mode_set(mode="EDIT")
        return self.armature

    def __exit__(self, *exception):
        bpy.ops.object.mode_set(mode="OBJECT")
        return False
