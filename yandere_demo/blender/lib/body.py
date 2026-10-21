"""Character parameters and the smooth skinned body (Skin modifier over a vertex skeleton)."""

from dataclasses import dataclass, field

import bpy
from mathutils import Vector

from . import mesh_utils
from .materials import principled
from .rig import bone_world_points


@dataclass
class CharacterParams:
    prefix: str = "Target"
    height: float = 1.58
    skin_color: str = "#f8d9c9"
    hair_color: str = "#f4a7c0"
    hair_shade_color: str = "#e58aa8"
    hair_streak_color: str = "#fbf3f5"
    eye_color: str = "#9b6bd6"
    uniform: str = "sailor_red"
    hair_style: str = "target"
    body_type: str = "female"
    sock_top_fraction: float = 0.405
    extra: dict = field(default_factory=dict)


# Per-body-type multipliers for (torso width, shoulder width, limb thickness, hip width).
BODY_TYPE_SCALES = {
    "female": (1.0, 1.0, 1.0, 1.0),
    "male": (1.08, 1.15, 1.1, 0.92),
    "adult": (1.12, 1.12, 1.12, 1.05),
}

BODY_PROPORTIONS = {
    "female": {},
    "male": {"shoulder_x": 0.095, "hip_x": 0.05, "arm_drop_degrees": 64.0},
    "adult": {"head_z": 0.875, "neck_z": 0.83, "shoulder_z": 0.815, "shoulder_x": 0.1, "chest_z": 0.72},
}

LEG_LABEL = "leg"


def body_proportions(params: CharacterParams) -> dict:
    return dict(BODY_PROPORTIONS.get(params.body_type, {}))


def build_body(armature, params: CharacterParams) -> bpy.types.Object:
    points, edges, radii, labels = _skeleton(armature, params)
    mesh = bpy.data.meshes.new(f"{params.prefix}Body")
    mesh.from_pydata(points, edges, [])
    body = mesh_utils.link_object(f"{params.prefix}Body", mesh)
    mesh_utils.add_modifier(body, "SKIN", use_smooth_shade=True, branch_smoothing=0.6)
    skin_vertices = mesh.skin_vertices[0].data
    for index, radius in enumerate(radii):
        skin_vertices[index].radius = radius
    skin_vertices[0].use_root = True
    mesh_utils.add_modifier(body, "SUBSURF", levels=2, render_levels=2)
    mesh_utils.apply_modifiers(body)
    _smooth(body, iterations=2)
    mesh_utils.shade_smooth(body)

    body.data.materials.append(principled("M_Skin", params.skin_color, 0.55))
    body.data.materials.append(principled("M_Sock", "#f7f5f7", 0.7))
    segments = [(points[start], points[end], labels[(start, end)]) for start, end in edges]
    material_indices = []
    for polygon in body.data.polygons:
        center = polygon.center
        label = _nearest_label(center, segments)
        is_sock = label == LEG_LABEL and center.z < params.sock_top_fraction * params.height
        material_indices.append(1 if is_sock else 0)
    body.data.polygons.foreach_set("material_index", material_indices)

    if not mesh_utils.parent_with_automatic_weights(body, armature):
        print(f"{body.name}: heat weighting failed, used nearest-bone weights")
    return body


def _nearest_label(point: Vector, segments: list) -> str:
    return min(segments, key=lambda segment: mesh_utils.point_segment_distance(point, segment[0], segment[1]))[2]


def _smooth(body, iterations: int) -> None:
    modifier = mesh_utils.add_modifier(body, "SMOOTH", factor=0.5, iterations=iterations)
    modifier.name = "Smooth"
    mesh_utils.apply_modifiers(body)


def _skeleton(armature, params: CharacterParams):
    torso, shoulders, limbs, hips = BODY_TYPE_SCALES.get(params.body_type, BODY_TYPE_SCALES["female"])
    points: list[Vector] = []
    radii: list[tuple] = []
    edges: list[tuple] = []
    labels: dict = {}

    def add(point: Vector, radius_x: float, radius_y: float) -> int:
        points.append(Vector(point))
        radii.append((radius_x, radius_y))
        return len(points) - 1

    def connect(start: int, end: int, label: str) -> None:
        edges.append((start, end))
        labels[(start, end)] = label

    def bone(name: str) -> tuple:
        return bone_world_points(armature, name)

    hips_head, _ = bone("hips")
    neck_head, neck_tail = bone("neck")
    _, chest_tail = bone("chest")
    pelvis_z = hips_head.z
    neck_z = neck_head.z

    def torso_z(fraction: float) -> float:
        return pelvis_z + (neck_z - pelvis_z) * fraction

    pelvis = add(Vector((0, 0.006, pelvis_z - 0.02)), 0.098 * hips, 0.078 * hips)
    belly = add(Vector((0, 0.002, torso_z(0.20))), 0.085 * torso, 0.066 * torso)
    waist = add(Vector((0, 0.004, torso_z(0.36))), 0.074 * torso, 0.060 * torso)
    ribs = add(Vector((0, 0.004, torso_z(0.55))), 0.084 * torso, 0.066 * torso)
    chest = add(Vector((0, 0.002, torso_z(0.74))), 0.088 * torso, 0.068 * torso)
    upper_chest = add(Vector((0, 0.008, torso_z(0.90))), 0.082 * shoulders, 0.060 * torso)
    neck_base = add(Vector((0, neck_head.y + 0.006, neck_z + 0.012)), 0.036 * limbs, 0.034 * limbs)
    neck_top = add(Vector((0, neck_tail.y + 0.006, neck_tail.z + 0.03)), 0.030 * limbs, 0.030 * limbs)
    for start, end in ((pelvis, belly), (belly, waist), (waist, ribs), (ribs, chest), (chest, upper_chest)):
        connect(start, end, "torso")
    connect(upper_chest, neck_base, "neck")
    connect(neck_base, neck_top, "neck")

    for side in (".L", ".R"):
        shoulder_head, shoulder_tail = bone(f"shoulder{side}")
        upper_arm_head, elbow = bone(f"upper_arm{side}")
        _, wrist = bone(f"forearm{side}")
        _, hand_tip = bone(f"fingers{side}")
        thumb_head, thumb_tail = bone(f"thumb{side}")
        shoulder_joint = add(upper_arm_head + Vector((0, 0, -0.008)), 0.040 * limbs, 0.038 * limbs)
        clavicle = add(shoulder_head.lerp(upper_arm_head, 0.55) + Vector((0, 0, -0.012)), 0.046 * shoulders, 0.044 * torso)
        upper_mid = add(upper_arm_head.lerp(elbow, 0.5), 0.035 * limbs, 0.034 * limbs)
        elbow_point = add(elbow, 0.028 * limbs, 0.027 * limbs)
        forearm_mid = add(elbow.lerp(wrist, 0.42), 0.030 * limbs, 0.027 * limbs)
        wrist_point = add(wrist, 0.021 * limbs, 0.017 * limbs)
        palm = add(wrist.lerp(hand_tip, 0.42), 0.030 * limbs, 0.014 * limbs)
        finger_tip = add(hand_tip, 0.016 * limbs, 0.009 * limbs)
        thumb_tip = add(thumb_tail, 0.008 * limbs, 0.008 * limbs)
        connect(upper_chest, clavicle, "torso")
        connect(clavicle, shoulder_joint, "arm")
        connect(shoulder_joint, upper_mid, "arm")
        connect(upper_mid, elbow_point, "arm")
        connect(elbow_point, forearm_mid, "arm")
        connect(forearm_mid, wrist_point, "arm")
        connect(wrist_point, palm, "hand")
        connect(palm, finger_tip, "hand")
        connect(wrist_point, thumb_tip, "hand")

        hip_head, knee = bone(f"thigh{side}")
        _, ankle = bone(f"shin{side}")
        _, ball = bone(f"foot{side}")
        _, toe_tip = bone(f"toe{side}")
        hip_point = add(hip_head + Vector((0, 0.004, 0.0)), 0.074 * hips, 0.072 * hips)
        thigh_mid = add(hip_head.lerp(knee, 0.45) + Vector((0, 0.0, 0)), 0.066 * limbs, 0.064 * limbs)
        knee_point = add(knee, 0.045 * limbs, 0.046 * limbs)
        calf = add(knee.lerp(ankle, 0.32) + Vector((0, 0.008, 0)), 0.048 * limbs, 0.050 * limbs)
        ankle_point = add(ankle, 0.027 * limbs, 0.028 * limbs)
        ball_point = add(ball + Vector((0, 0, 0.004)), 0.030 * limbs, 0.018 * limbs)
        toe_point = add(toe_tip + Vector((0, 0.01, 0.002)), 0.024 * limbs, 0.014 * limbs)
        connect(pelvis, hip_point, LEG_LABEL)
        connect(hip_point, thigh_mid, LEG_LABEL)
        connect(thigh_mid, knee_point, LEG_LABEL)
        connect(knee_point, calf, LEG_LABEL)
        connect(calf, ankle_point, LEG_LABEL)
        connect(ankle_point, ball_point, LEG_LABEL)
        connect(ball_point, toe_point, LEG_LABEL)
    return points, edges, radii, labels
