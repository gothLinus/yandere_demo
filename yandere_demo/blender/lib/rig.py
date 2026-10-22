"""Humanoid armature shared by every character, plus helper bone chains."""

import math

import bpy
from mathutils import Quaternion, Vector

FINGERS = ["thumb", "index", "middle", "ring", "pinky"]
FINGER_SEGMENTS = 3
FINGER_BONES = [f"{finger}_{segment:02d}{side}" for side in (".L", ".R") for finger in FINGERS
                for segment in range(1, FINGER_SEGMENTS + 1)]
HUMANOID_BONES = [
    "root", "hips", "spine", "chest", "neck", "head",
    "shoulder.L", "shoulder.R", "upper_arm.L", "upper_arm.R",
    "forearm.L", "forearm.R", "hand.L", "hand.R",
    "thigh.L", "thigh.R", "shin.L", "shin.R",
    "foot.L", "foot.R", "toe.L", "toe.R",
] + FINGER_BONES


def chain_names(prefix: str, count: int) -> list[str]:
    return [f"{prefix}_{index:02d}" for index in range(1, count + 1)]


BRAID_BONES = chain_names("braid", 10)
BRAID_BOW_BONE = "braid_bow"
AHOGE_BONES = chain_names("ahoge", 3)
HAIR_FRONT_BONES = [name for cluster in ("L", "C", "R") for name in chain_names(f"hair_front_{cluster}", 2)]
HAIR_SIDE_BONES = [name for side in ("L", "R") for name in chain_names(f"hair_side_{side}", 3)]
NECKERCHIEF_BONES = [name for side in ("L", "R") for name in chain_names(f"neckerchief_{side}", 2)]
SLEEVE_BONES = ["sleeve_L_01", "sleeve_R_01"]
# Eight chains around the waist: 00 at the front centre, then clockwise seen from above
# (01 toward the character's right, 04 at the back, 06 on the character's left).
SKIRT_CHAIN_COUNT = 8
SKIRT_SEGMENTS = 3
SKIRT_CHAINS = [f"skirt_{chain:02d}" for chain in range(SKIRT_CHAIN_COUNT)]
SKIRT_BONES = [name for chain in SKIRT_CHAINS for name in chain_names(chain, SKIRT_SEGMENTS)]
SECONDARY_BONES = (BRAID_BONES + [BRAID_BOW_BONE] + AHOGE_BONES + HAIR_FRONT_BONES + HAIR_SIDE_BONES
                   + NECKERCHIEF_BONES + SLEEVE_BONES + SKIRT_BONES)
PONYTAIL_BONES = chain_names("ponytail", 4)

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


def add_chain(armature, prefix: str, parent: str, points: list[Vector], suffix: str = "") -> list[str]:
    names: list[str] = []
    with _EditMode(armature):
        previous = parent
        for index in range(len(points) - 1):
            bone_name = f"{prefix}_{index + 1:02d}{suffix}"
            _new_bone(armature, bone_name, points[index], points[index + 1], previous, True)
            names.append(bone_name)
            previous = bone_name
    return names


def add_bone(armature, bone_name: str, head: Vector, tail: Vector, parent: str) -> str:
    with _EditMode(armature):
        _new_bone(armature, bone_name, head, tail, parent, True)
    return bone_name


def skirt_chain_azimuth(chain_index: int) -> float:
    """Azimuth (atan2(y, x), radians) of a skirt chain: 00 faces front (-Y), then clockwise seen from above."""
    return -math.pi / 2 - chain_index * 2 * math.pi / SKIRT_CHAIN_COUNT


def add_skirt_chains(armature, waist_z: float, hem_z: float, waist_radius: tuple, hem_radius: tuple,
                     center_y: float = 0.004) -> list[str]:
    """Eight chains of three bones from the waistband to the hem, each on its pleat group's centre line."""
    names: list[str] = []
    for chain_index, prefix in enumerate(SKIRT_CHAINS):
        angle = skirt_chain_azimuth(chain_index)
        points = []
        for segment in range(SKIRT_SEGMENTS + 1):
            fraction = segment / SKIRT_SEGMENTS
            radius_x = waist_radius[0] + (hem_radius[0] - waist_radius[0]) * fraction ** 0.85
            radius_y = waist_radius[1] + (hem_radius[1] - waist_radius[1]) * fraction ** 0.85
            z = waist_z + (hem_z - waist_z) * fraction
            points.append(Vector((math.cos(angle) * radius_x, math.sin(angle) * radius_y + center_y, z)))
        names += add_chain(armature, prefix, "hips", points)
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
        hand_end = wrist + arm_direction * scaled("hand_length") * KNUCKLE_FRACTION
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
            (f"thigh{side}", hip, knee, "hips", True),
            (f"shin{side}", knee, ankle, f"thigh{side}", True),
            (f"foot{side}", ankle, ball, f"shin{side}", True),
            (f"toe{side}", ball, toe_tip, f"foot{side}", True),
        ]
        layout += _finger_layout(side, sign, wrist, arm_direction, scaled("hand_length"))
    order = {name: index for index, name in enumerate(HUMANOID_BONES)}
    return sorted(layout, key=lambda entry: order[entry[0]])


# Per finger: (offset toward the thumb side, offset along the hand, length, splay toward the thumb in degrees),
# all lengths as fractions of the hand length.
FINGER_LAYOUT = {
    "index": (0.118, -0.006, 0.41, 3.0),
    "middle": (0.040, 0.008, 0.45, 0.0),
    "ring": (-0.040, 0.0, 0.42, -3.0),
    "pinky": (-0.114, -0.04, 0.34, -7.0),
}
# The palm ends (and the fingers start) this far along the hand.
KNUCKLE_FRACTION = 0.55
PHALANX_FRACTIONS = (0.42, 0.32, 0.26)
# A relaxed hand: every finger joint is bent this far toward the palm at rest.
REST_FINGER_CURL_DEGREES = 7.0
# Thumb root as (along, toward the thumb side, toward the palm) fractions of the hand length, and its direction.
THUMB_BASE = (0.16, 0.03, 0.05)
THUMB_DIRECTION = (0.62, 0.45, 0.50)


def _finger_layout(side: str, sign: float, wrist: Vector, along: Vector, hand_length: float) -> list[tuple]:
    """Three-bone chains for the thumb and four fingers. At rest the palm faces the body and the thumb points forward."""
    inward = Vector((-sign, 0.0, 0.0))
    palm = (inward - along * inward.dot(along)).normalized()
    thumb_side = Vector((0.0, -1.0, 0.0))
    thumb_side = (thumb_side - along * thumb_side.dot(along) - palm * thumb_side.dot(palm)).normalized()
    layout = []
    knuckles = wrist + along * hand_length * KNUCKLE_FRACTION
    curl = math.radians(REST_FINGER_CURL_DEGREES)
    for finger, (across, forward, length, splay) in FINGER_LAYOUT.items():
        splay_rotation = Quaternion(palm, math.radians(splay) * (1.0 if along.cross(thumb_side).dot(palm) > 0 else -1.0))
        direction = (splay_rotation @ along).normalized()
        head = knuckles + thumb_side * across * hand_length + along * forward * hand_length
        parent = f"hand{side}"
        for segment, fraction in enumerate(PHALANX_FRACTIONS, start=1):
            direction = (direction * math.cos(curl) + palm * math.sin(curl)).normalized()
            tail = head + direction * length * fraction * hand_length
            bone_name = f"{finger}_{segment:02d}{side}"
            layout.append((bone_name, head, tail, parent, True))
            parent, head = bone_name, tail
    base_along, base_side, base_palm = THUMB_BASE
    thumb_head = wrist + (along * base_along + thumb_side * base_side + palm * base_palm) * hand_length
    direction = (along * THUMB_DIRECTION[0] + thumb_side * THUMB_DIRECTION[1] + palm * THUMB_DIRECTION[2]).normalized()
    parent = f"hand{side}"
    for segment, length in enumerate((0.19, 0.15, 0.13), start=1):
        tail = thumb_head + direction * length * hand_length
        bone_name = f"thumb_{segment:02d}{side}"
        layout.append((bone_name, thumb_head, tail, parent, True))
        parent, thumb_head = bone_name, tail
        direction = (direction + along * 0.35 + palm * 0.12).normalized()
    return layout


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
