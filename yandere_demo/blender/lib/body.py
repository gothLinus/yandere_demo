"""Character parameters and the smooth skinned body (Skin modifier over a vertex skeleton)."""

from dataclasses import dataclass, field

import bmesh
import bpy
from mathutils import Vector

from . import mesh_utils
from .materials import principled
from .rig import FINGERS, bone_world_points


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
    sock_thickness: float = 0.0014
    sock_color: str = "#f7f5f7"
    # Subdivision levels of the body and the skull; background characters use fewer.
    subdivision_levels: int = 2
    extra: dict = field(default_factory=dict)


# Per-body-type multipliers for (torso width, shoulder width, limb thickness, hip width).
BODY_TYPE_SCALES = {
    "female": (1.0, 1.0, 1.0, 1.0),
    "male": (1.08, 1.15, 1.1, 0.92),
    "adult": (1.12, 1.12, 1.12, 1.05),
    # Spec 4.1b: narrow shoulders, slender neck and limbs, a flat chest, a narrow waist and modest hips.
    "femboy": (0.93, 0.80, 0.90, 1.06),
}

BODY_PROPORTIONS = {
    "female": {},
    "male": {"shoulder_x": 0.095, "hip_x": 0.05, "arm_drop_degrees": 64.0},
    "adult": {"head_z": 0.875, "neck_z": 0.83, "shoulder_z": 0.815, "shoulder_x": 0.1, "chest_z": 0.72},
    # Long slim legs (higher hips and knees), narrow shoulders, slightly wider hip joints.
    "femboy": {"pelvis_z": 0.600, "spine_z": 0.648, "hip_z": 0.565, "knee_z": 0.303, "shoulder_x": 0.074,
               "clavicle_x": 0.013, "hip_x": 0.056, "upper_arm_length": 0.150, "forearm_length": 0.136},
}

# Finger radii at the knuckle and the tip, in metres, before the limb scale.
FINGER_RADII = {"thumb": (0.0105, 0.0062), "index": (0.0071, 0.0054), "middle": (0.0073, 0.0055),
                "ring": (0.0069, 0.0052), "pinky": (0.0062, 0.0047)}
# The Skin modifier drops a junction (leaving loose islands) when branch frames overlap; these were searched
# so the hand stays one piece with the arm.
KNUCKLE_HUB_FRACTION = 0.92
THUMB_BRANCH = "hub"
HAND_BONE_PREFIXES = ("hand", "forearm") + tuple(f"{finger}_" for finger in FINGERS)

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
    mesh_utils.add_modifier(body, "SUBSURF", levels=params.subdivision_levels, render_levels=params.subdivision_levels)
    mesh_utils.apply_modifiers(body)
    _smooth(body, iterations=2)
    mesh_utils.shade_smooth(body)

    body.data.materials.append(principled("M_Skin", params.skin_color, 0.55))
    body.data.materials.append(principled("M_Sock", params.sock_color, 0.7))
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
    _reweight_hands(body, armature)
    return body


def _reweight_hands(body, armature) -> None:
    """Heat weighting smears small fingers into each other; give every hand vertex clean nearest-bone weights."""
    hand_bones = [bone.name for bone in armature.data.bones if bone.name.startswith(HAND_BONE_PREFIXES)]
    segments = {name: bone_world_points(armature, name) for name in hand_bones + ["upper_arm.L", "upper_arm.R"]}
    groups = {group.name: group for group in body.vertex_groups}
    for name in hand_bones:
        if name not in groups:
            groups[name] = body.vertex_groups.new(name=name)
    for vertex in body.data.vertices:
        point = body.matrix_world @ vertex.co
        distances = sorted((mesh_utils.point_segment_distance(point, *segments[name]), name) for name in segments)
        nearest_distance, nearest = distances[0]
        if not nearest.startswith(("hand",) + tuple(f"{finger}_" for finger in FINGERS)) or nearest_distance > 0.03:
            continue
        blend = 0.006
        weights = {}
        for distance, name in distances[:3]:
            if distance - nearest_distance > blend or name.startswith("upper_arm"):
                continue
            weights[name] = 1.0 - (distance - nearest_distance) / blend
        total = sum(weights.values())
        for group in body.vertex_groups:
            group.remove([vertex.index])
        for name, weight in weights.items():
            groups[name].add([vertex.index], weight / total, "REPLACE")


def build_socks(body, params: CharacterParams) -> bpy.types.Object:
    """Split the sock faces off the body into their own slightly thicker mesh; the skin under them is removed,
    keeping a short overlap band below the sock top so no gap shows."""
    socks = body.copy()
    socks.data = body.data.copy()
    socks.name = f"{params.prefix}Socks"
    socks.data.name = socks.name
    bpy.context.scene.collection.objects.link(socks)
    sock_index = body.data.materials.find("M_Sock")
    overlap_z = params.sock_top_fraction * params.height - 0.03 * params.height / 1.58
    bm = bmesh.new()
    bm.from_mesh(socks.data)
    bmesh.ops.delete(bm, geom=[face for face in bm.faces if face.material_index != sock_index], context="FACES")
    bm.normal_update()
    for vertex in bm.verts:
        vertex.co += vertex.normal * params.sock_thickness
    for face in bm.faces:
        face.material_index = 0
    bm.to_mesh(socks.data)
    bm.free()
    socks.data.materials.clear()
    socks.data.materials.append(principled("M_Sock", params.sock_color, 0.7))
    mesh_utils.shade_smooth(socks)

    bm = bmesh.new()
    bm.from_mesh(body.data)
    covered = [face for face in bm.faces if face.material_index == sock_index and max(vertex.co.z for vertex in face.verts) < overlap_z]
    bmesh.ops.delete(bm, geom=covered, context="FACES")
    for face in bm.faces:
        face.material_index = 0
    bm.to_mesh(body.data)
    bm.free()
    body.data.materials.pop(index=sock_index)
    body.data.update()
    return socks


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
        _, knuckles = bone(f"hand{side}")
        shoulder_joint = add(upper_arm_head + Vector((0, 0, -0.008)), 0.040 * limbs, 0.038 * limbs)
        clavicle = add(shoulder_head.lerp(upper_arm_head, 0.55) + Vector((0, 0, -0.012)), 0.046 * shoulders, 0.044 * torso)
        upper_mid = add(upper_arm_head.lerp(elbow, 0.5), 0.035 * limbs, 0.034 * limbs)
        elbow_point = add(elbow, 0.028 * limbs, 0.027 * limbs)
        forearm_mid = add(elbow.lerp(wrist, 0.42), 0.030 * limbs, 0.027 * limbs)
        wrist_point = add(wrist, 0.019 * limbs, 0.016 * limbs)
        palm = add(wrist.lerp(knuckles, 0.45), 0.021 * limbs, 0.012 * limbs)
        knuckle_hub = add(wrist.lerp(knuckles, KNUCKLE_HUB_FRACTION), 0.021 * limbs, 0.0105 * limbs)
        connect(upper_chest, clavicle, "torso")
        connect(clavicle, shoulder_joint, "arm")
        connect(shoulder_joint, upper_mid, "arm")
        connect(upper_mid, elbow_point, "arm")
        connect(elbow_point, forearm_mid, "arm")
        connect(forearm_mid, wrist_point, "arm")
        connect(wrist_point, palm, "hand")
        connect(palm, knuckle_hub, "hand")
        for finger in FINGERS:
            base_radius, tip_radius = FINGER_RADII[finger]
            previous = {"palm": palm, "wrist": wrist_point, "hub": knuckle_hub}[THUMB_BRANCH] if finger == "thumb" else knuckle_hub
            for segment in range(1, 4):
                head, tail = bone(f"{finger}_{segment:02d}{side}")
                fraction = (segment - 1) / 3
                radius = (base_radius + (tip_radius - base_radius) * fraction) * limbs
                joint = add(head, radius, radius)
                connect(previous, joint, "hand")
                previous = joint
                if segment == 3:
                    tip = add(tail, tip_radius * limbs, tip_radius * limbs)
                    connect(previous, tip, "hand")

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
