"""The Astolfo Source model (blender/source/astolfo/astolfo_source.blend) converted to the target contract.

The ValveBiped rig becomes one armature `TargetChar` with the project's humanoid names (`rig.HUMANOID_BONES`), its
bones on the model's own joints, its arms lowered to the project's rest angle and its fingers relaxed, so every clip
generator applies unchanged. The model's helper, hair, bow and ribbon bones keep their weights under project names,
the forefeet move onto the toe bones, and the skirt gains eight three-bone chains. Meshes become `Target<Part>` with `M_<Part>` materials on the model's own textures,
the face's flexes are baked into the game's expression shape keys, and `Target-col` is a capsule fitted to the body.
"""

import math
import os
from dataclasses import dataclass

import bpy
import numpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

from . import body, clothing, mesh_utils, pleats, target_animations
from .animation import SIDES, side_sign
from .character_animation import Stance
from .materials import principled
from .rig import (
    DEFAULT_PROPORTIONS, FINGER_SEGMENTS, FINGERS, REST_FINGER_CURL_DEGREES, SKIRT_CHAINS, SKIRT_SEGMENTS, chain_names,
    skirt_chain_azimuth,
)

PREFIX = "Target"
ARMATURE_NAME = f"{PREFIX}Char"
SOURCE_ARMATURE = "tobycrack\\astolfo\\Astolfo_ARM"
# The top of the skull (the head mesh's highest point) after the uniform scale; the soles stand on z = 0.
CROWN_HEIGHT = 1.62
ARM_REST_DROP_DEGREES = DEFAULT_PROPORTIONS["arm_drop_degrees"]

VALVE_PREFIX = "ValveBiped.Bip01_"
# Spine1 and Spine4 fold into their neighbours: the clips key one lumbar and one thoracic joint.
TORSO_BONES = {
    "Pelvis": "hips", "Spine": "spine", "Spine1": "spine", "Spine2": "chest", "Spine4": "chest",
    "Neck1": "neck", "Head1": "head",
}
MERGED_BONES = {f"{VALVE_PREFIX}Spine1", f"{VALVE_PREFIX}Spine4"}
# The model has a shoulder helper on the left arm only.
ABSENT_SOURCE_BONES = {f"{VALVE_PREFIX}R_Shoulder"}
LIMB_BONES = {
    "Clavicle": "shoulder", "UpperArm": "upper_arm", "Forearm": "forearm", "Hand": "hand",
    "Thigh": "thigh", "Calf": "shin", "Foot": "foot", "Toe0": "toe",
}
# Plain deformation helpers that follow their parents: no keys and no springs (addendum §5 and §6).
HELPER_BONES = {
    "Shoulder": "shoulder_helper", "Elbow": "elbow_helper", "Wrist": "wrist_helper", "Ulna": "ulna_helper",
    "Knee": "knee_helper", "Ankle": "ankle_helper", "Pectoral": "chest_helper", "Glute": "glute_helper",
}
HELPER_SUFFIX = "_helper"
# The model's hair, bow and ribbon bones. Front, side and back are by where each lock grows around the head; the
# numbers run from the face backwards. Each hair lock and bow loop is one bone; the braid and ribbons are chains.
SECONDARY_BONES = {
    "Hair": "hair_front_C_01",
    "Hair.002": "hair_front_L_01", "Hair.003": "hair_front_L_02", "Hair.007": "hair_front_L_03",
    "Hair.001": "hair_front_R_01", "Hair.004": "hair_front_R_02", "Hair.008": "hair_front_R_03",
    "Hair.006": "hair_side_L_01", "Hair.040": "hair_side_L_02", "Hair.028": "hair_side_L_03", "Hair.017": "hair_side_L_04",
    "Hair.005": "hair_side_R_01", "Hair.041": "hair_side_R_02", "Hair.029": "hair_side_R_03", "Hair.024": "hair_side_R_04",
    "Hair.023": "hair_back_L_01", "Hair.018": "hair_back_L_02", "Hair.019": "hair_back_L_03", "Hair.021": "hair_back_L_04",
    "Hair.020": "hair_back_C_01",
    "Hair.027": "hair_back_R_01", "Hair.025": "hair_back_R_02", "Hair.026": "hair_back_R_03", "Hair.022": "hair_back_R_04",
    "Hair.030": "braid_01", "Hair.031": "braid_02", "Hair.032": "braid_03", "Hair.033": "braid_04",
    "Hair.034": "braid_05", "Hair.035": "braid_06",
    "Bow.008": "braid_bow_01", "Bow.009": "braid_bow_02", "Bow.010": "braid_bow_03", "Bow.011": "braid_bow_04",
    "Bow": "head_bow_L_01", "Bow.001": "head_bow_L_02", "Bow.002": "head_bow_L_03", "Bow.003": "head_bow_L_04",
    "Bow.004": "head_bow_R_01", "Bow.005": "head_bow_R_02", "Bow.006": "head_bow_R_03", "Bow.007": "head_bow_R_04",
    "ribbon_L_1": "ribbon_L_01", "ribbon_L_2": "ribbon_L_02", "ribbon_R_1": "ribbon_R_01", "ribbon_R_2": "ribbon_R_02",
}
BRAID_PREFIX = "braid_"
BRAID_BOW_PREFIX = "braid_bow_"

# Source mesh -> part, so the objects become Target<Part>.
MESH_PARTS = {
    "astolfo_body_reference.smd": "Body",
    "astolfo_head_reference.smd": "Face",
    "astolfo_hair_reference.smd": "Hair",
    "astolfo_schoolshirt_reference.smd": "Top",
    "astolfo_schoolskirt_reference.smd": "Skirt",
    "astolfo_socks_reference.smd": "Socks",
    "astolfo_schoolshoes_reference.smd": "Shoes",
}
# Source material -> (M_<Part>, texture written by import_astolfo_source.py). The head's skin keeps an outline, so it
# is not an M_Face* material (ToonConverter leaves those without one); the pupils are M_Eye.
MATERIAL_PARTS = {
    "body": ("M_Skin", "body.png"),
    "Face": ("M_Head", "face.png"),
    "Pupils": ("M_Eye", "pupils.png"),
    "UpperHair": ("M_HairUpper", "upperhair.png"),
    "PonyTail": ("M_HairBraid", "ponytail.png"),
    "FrontHair": ("M_HairFront", "fronthair.png"),
    "LowerHair": ("M_HairLower", "lowerhair.png"),
    "VeryLowerHair": ("M_HairNape", "verylowerhair.png"),
    "shirt": ("M_Top", "shirt.png"),
    "skirt": ("M_Skirt", "skirt.png"),
    "socks": ("M_Sock", "socks.png"),
    "shoes2": ("M_Shoe", "shoes2.png"),
}
MATERIAL_ROUGHNESS = 0.6

# Every expression the game drives, baked on TargetFace as a weighted sum of the model's flexes (shape-key name ->
# {flex: weight}). `neutral` is the rest face. `blush` is a shy face until Task 23d adds the blush layer. Left and
# right are the character's own (the model's `Left*` flexes move the +X eye).
EXPRESSION_FLEXES = {
    "neutral": {},
    "startled": {"EyesSuprise": 1.0, "BrowsUp": 1.0, "LipSuprise": 0.7, "PupilsSmall": 0.4},
    "suspicious": {"EyesSquint": 0.8, "BrowsAngry": 0.35, "BrowsDown": 0.4, "LipIndifference": 0.7},
    "happy": {"MounthOpenCute": 0.8, "EyesRaised": 0.6, "BrowsUp": 0.2},
    "blink": {"EyesClosed": 1.0},
    "smile": {"Smile": 1.0, "EyesRaised": 0.3},
    "sad": {"LipSad": 1.0, "BrowsTenderness": 1.0, "EyesSleepy": 0.3},
    "blush": {"LipShame": 0.6, "BrowsTenderness": 0.4, "EyesRaised": 0.2},
    "wink_L": {"LeftHappy": 1.0},
    "wink_R": {"RightHappy": 1.0},
    "mouth_A": {"MouthOpenCute2": 1.0},
    "mouth_I": {"MouthEEWW": 0.8},
    "mouth_U": {"LipSuprise": 1.0},
    "mouth_E": {"LipYeee": 1.0},
    "mouth_O": {"LipSuprise2": 1.0},
    "pupil_small": {"PupilsSmall": 0.7},
    "pupil_large": {"PupilsBigger": 1.0},
}
MOUTH_FLEX = "MouthOpne"
EYE_MATERIAL = "Pupils"
# Vertices moving more than this share of the flex's largest offset mark the mouth.
LANDMARK_MOVE_FRACTION = 0.5

# Skirt chains lie this far inside the skirt's outer surface; samples within these windows find that surface.
SKIRT_CHAIN_INSET = 0.004
SKIRT_SAMPLE_DEGREES = 12.0
SKIRT_SAMPLE_HEIGHT = 0.02
SKIRT_SEAM_DISTANCE = 0.015
COLLISION_PROXY = f"{PREFIX}-col"
PROXY_RADIUS_STEP = 0.01
PROXY_BONE_PREFIXES = ("hips", "spine", "chest", "thigh", "shin", "glute", "skirt_")


@dataclass
class FaceLandmarks:
    """Rest-pose landmarks measured on the face before its flexes are baked away (armature space)."""

    mouth: Vector
    eyes: Vector


def bone_rename_map() -> dict[str, str]:
    """Source bone -> target bone for every bone of the model (merged spine bones share a target)."""
    renames = {f"{VALVE_PREFIX}{source}": target for source, target in TORSO_BONES.items()}
    for source_side, side in (("L_", ".L"), ("R_", ".R")):
        for source, target in {**LIMB_BONES, **HELPER_BONES}.items():
            renames[f"{VALVE_PREFIX}{source_side}{source}"] = f"{target}{side}"
        for finger_index, finger in enumerate(FINGERS):
            for segment in range(FINGER_SEGMENTS):
                suffix = str(segment) if segment else ""
                renames[f"{VALVE_PREFIX}{source_side}Finger{finger_index}{suffix}"] = f"{finger}_{segment + 1:02d}{side}"
    renames.update(SECONDARY_BONES)
    return {source: target for source, target in renames.items() if source not in ABSENT_SOURCE_BONES}


def load_source(blend_path: str) -> tuple:
    """Append the source armature and meshes into the current scene; returns (armature, meshes by part)."""
    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        data_to.objects = [name for name in data_from.objects if name == SOURCE_ARMATURE or name in MESH_PARTS]
    for loaded in data_to.objects:
        bpy.context.scene.collection.objects.link(loaded)
    armature = bpy.data.objects[SOURCE_ARMATURE]
    meshes = {part: bpy.data.objects[name] for name, part in MESH_PARTS.items()}
    return armature, meshes


def convert(source_armature, meshes: dict, texture_directory: str) -> tuple:
    """Build `TargetChar` from the appended source; returns (armature, FaceLandmarks)."""
    matrix = _normalizing_matrix(meshes)
    for mesh_object in meshes.values():
        mesh_object.parent = None
        mesh_object.modifiers.clear()
        mesh_object.data.transform(matrix @ mesh_object.matrix_world, shape_keys=True)
        mesh_object.matrix_world = Matrix.Identity(4)
    armature = _build_armature(source_armature, matrix, meshes)
    bpy.data.objects.remove(source_armature)
    for part, mesh_object in meshes.items():
        _rename_vertex_groups(mesh_object, armature)
        mesh_object.name = mesh_object.data.name = f"{PREFIX}{part}"
        mesh_utils.parent_to_armature(mesh_object, armature)
    _lower_arms(armature, meshes)
    _relax_fingers(armature, meshes)
    weight_toes(armature, meshes)
    add_skirt_chains(armature, meshes["Skirt"])
    _assign_materials(meshes, texture_directory)
    landmarks = _face_landmarks(meshes["Face"])
    bake_expressions(meshes["Face"])
    for mesh_object in meshes.values():
        mesh_utils.limit_influences(mesh_object)
    build_collision_proxy(armature, meshes)
    return armature, landmarks


def _normalizing_matrix(meshes: dict) -> Matrix:
    """Uniform scale that puts the crown at CROWN_HEIGHT, and a drop that stands the soles on the floor."""
    sole = min((meshes["Shoes"].matrix_world @ vertex.co).z for vertex in meshes["Shoes"].data.vertices)
    crown = max((meshes["Face"].matrix_world @ vertex.co).z for vertex in meshes["Face"].data.vertices)
    scale = CROWN_HEIGHT / (crown - sole)
    return Matrix.Translation((0.0, 0.0, -sole * scale)) @ Matrix.Scale(scale, 4)


# ---------------------------------------------------------------------------------------------------
# Armature

def _build_armature(source_armature, matrix: Matrix, meshes: dict) -> bpy.types.Object:
    renames = bone_rename_map()
    source_bones = source_armature.data.bones
    unmapped = [bone.name for bone in source_bones if bone.name not in renames]
    if unmapped:
        raise ValueError(f"source bones without a target name: {unmapped}")
    to_target = matrix @ source_armature.matrix_world
    heads, parents, source_tails = {"root": Vector()}, {"root": None}, {}
    for bone in source_bones:
        if bone.name in MERGED_BONES:
            continue
        target = renames[bone.name]
        heads[target] = to_target @ bone.head_local
        source_tails[target] = to_target @ bone.tail_local
        parent = bone.parent
        parents[target] = renames[parent.name] if parent is not None else "root"
    dominant = _dominant_points(meshes, renames)
    tails = {name: _tail(name, heads, parents, source_tails, dominant) for name in heads}

    armature_data = bpy.data.armatures.new(ARMATURE_NAME)
    armature = bpy.data.objects.new(ARMATURE_NAME, armature_data)
    bpy.context.scene.collection.objects.link(armature)
    armature.show_in_front = True
    with _EditMode(armature):
        edit_bones = armature_data.edit_bones
        for name in _parents_first(parents):
            edit_bone = edit_bones.new(name)
            edit_bone.head = heads[name]
            edit_bone.tail = tails[name]
            edit_bone.use_deform = name != "root"
            if parents[name] is not None:
                edit_bone.parent = edit_bones[parents[name]]
                edit_bone.use_connect = (edit_bone.parent.tail - edit_bone.head).length < 1e-5
    return armature


def _parents_first(parents: dict) -> list:
    ordered = []
    pending = list(parents)
    while pending:
        for name in list(pending):
            if parents[name] is None or parents[name] in ordered:
                ordered.append(name)
                pending.remove(name)
    return ordered


def _continuations() -> dict:
    """Bone -> the bone whose head is its tail (the next joint along a limb, finger or chain)."""
    following = {"spine": "chest", "chest": "neck", "neck": "head"}
    for side in SIDES:
        for first, second in (("shoulder", "upper_arm"), ("upper_arm", "forearm"), ("forearm", "hand"),
                              ("thigh", "shin"), ("shin", "foot"), ("foot", "toe")):
            following[f"{first}{side}"] = f"{second}{side}"
        for finger in FINGERS:
            for segment in range(1, FINGER_SEGMENTS):
                following[f"{finger}_{segment:02d}{side}"] = f"{finger}_{segment + 1:02d}{side}"
        following[f"ribbon{side.replace('.', '_')}_01"] = f"ribbon{side.replace('.', '_')}_02"
    braid = [name for name in SECONDARY_BONES.values() if name.startswith(BRAID_PREFIX) and not name.startswith(BRAID_BOW_PREFIX)]
    following.update(zip(braid, braid[1:]))
    return following


def _tail(name: str, heads: dict, parents: dict, source_tails: dict, dominant: dict) -> Vector:
    head = heads[name]
    following = _continuations()
    if name == "root":
        return Vector((0.0, 0.15, 0.0))
    if name in following:
        return heads[following[name]].copy()
    if name == "head":
        return Vector((head.x, head.y, CROWN_HEIGHT))
    if name == "hips":
        # The model's spine starts behind the pelvis; the hips point straight up so their +Y is the body's up axis.
        return head + Vector((0.0, 0.0, (heads["spine"] - head).length))
    if name.startswith("hand"):
        side = name[-2:]
        knuckles = [heads[f"{finger}_01{side}"] for finger in FINGERS[1:]]
        return sum(knuckles, Vector()) / len(knuckles)
    if name.endswith(HELPER_SUFFIX + name[-2:]) or name not in dominant:
        return source_tails[name]
    points = dominant[name]
    parent = parents[name]
    if name.startswith(("toe",) + tuple(FINGERS)):
        # Toes and finger tips continue their parent's direction to the end of the skin they carry.
        direction = (head - heads[parent]).normalized()
        reach = max(float((point - head).dot(direction)) for point in points)
        return head + direction * max(reach, 0.01)
    # A free lock, bow loop or chain end points at the farthest skin it carries.
    return max(points, key=lambda point: (point - head).length).copy()


def _dominant_points(meshes: dict, renames: dict) -> dict:
    """Target bone -> rest positions of the vertices it dominates, over every mesh."""
    points: dict = {}
    for mesh_object in meshes.values():
        names = {group.index: renames.get(group.name, group.name) for group in mesh_object.vertex_groups}
        for vertex in mesh_object.data.vertices:
            strongest = max(vertex.groups, key=lambda element: element.weight, default=None)
            if strongest is not None and strongest.weight > 0.0:
                points.setdefault(names[strongest.group], []).append(mesh_object.matrix_world @ vertex.co)
    return points


def _rename_vertex_groups(mesh_object, armature) -> None:
    """Rename every bone group to its target bone; merged bones add their weights to the bone they fold into."""
    renames = bone_rename_map()
    source_names = {group.index: group.name for group in mesh_object.vertex_groups}
    weights: dict = {}
    for vertex in mesh_object.data.vertices:
        for element in vertex.groups:
            if element.weight <= 0.0:
                continue
            target = renames[source_names[element.group]]
            per_vertex = weights.setdefault(target, {})
            per_vertex[vertex.index] = per_vertex.get(vertex.index, 0.0) + element.weight
    mesh_object.vertex_groups.clear()
    bone_names = {bone.name for bone in armature.data.bones}
    for target, per_vertex in sorted(weights.items()):
        if target not in bone_names:
            raise ValueError(f"{mesh_object.name} is weighted to {target}, which is not a bone of {armature.name}")
        group = mesh_object.vertex_groups.new(name=target)
        for vertex_index, weight in per_vertex.items():
            group.add([vertex_index], weight, "REPLACE")


def _lower_arms(armature, meshes: dict) -> None:
    """Swing each arm down about the forward axis to the project's rest angle and make that the rest pose.

    The clips' FK arms are rest-relative, so the rest arm angle must match the one they were written for.
    """
    rotations = {}
    for side in SIDES:
        bones = armature.data.bones
        shoulder = bones[f"upper_arm{side}"].head_local.copy()
        arm = bones[f"hand{side}"].head_local - shoulder
        drop = math.degrees(math.atan2(-arm.z, abs(arm.x)))
        angle = math.radians(ARM_REST_DROP_DEGREES - drop) * side_sign(side)
        rotations[side] = Matrix.Translation(shoulder) @ Matrix.Rotation(angle, 4, "Y") @ Matrix.Translation(-shoulder)
        pose_bone = armature.pose.bones[f"upper_arm{side}"]
        pose_bone.matrix = rotations[side] @ pose_bone.bone.matrix_local
    bpy.context.view_layer.update()
    _bake_posed_meshes(armature, meshes, {f"{name}{side}" for side in SIDES for name in ("upper_arm", "forearm", "hand")})
    with _EditMode(armature):
        for side in SIDES:
            upper_arm = armature.data.edit_bones[f"upper_arm{side}"]
            arm_bones = [upper_arm] + list(upper_arm.children_recursive)
            # Connected heads follow their parents' tails, so every new joint is taken from the old pose first.
            moved = [(edit_bone, rotations[side] @ edit_bone.head, rotations[side] @ edit_bone.tail) for edit_bone in arm_bones]
            for edit_bone, head, tail in moved:
                edit_bone.head, edit_bone.tail, edit_bone.roll = head, tail, 0.0


def _bake_posed_meshes(armature, meshes: dict, moved_groups: set) -> None:
    """Write the current pose into every mesh weighted to `moved_groups` as its rest shape, then clear the pose."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for mesh_object in meshes.values():
        if not moved_groups & {group.name for group in mesh_object.vertex_groups}:
            continue
        if mesh_object.data.shape_keys is not None:
            raise ValueError(f"{mesh_object.name} has shape keys and weights on {sorted(moved_groups)}; "
                             f"its rest pose cannot be changed")
        evaluated = mesh_object.evaluated_get(depsgraph)
        posed = evaluated.to_mesh()
        coordinates = numpy.empty(len(posed.vertices) * 3)
        posed.vertices.foreach_get("co", coordinates)
        evaluated.to_mesh_clear()
        mesh_object.data.vertices.foreach_set("co", coordinates)
        mesh_object.data.update()
    for pose_bone in armature.pose.bones:
        pose_bone.matrix_basis = Matrix.Identity(4)


# The model's fingers are straight at rest; the clips' curls are rest-relative and were written for the procedural
# rig's relaxed hand, so each finger joint is bent this far toward the palm at rest.
RELAXED_FINGERS = ("index", "middle", "ring", "pinky")


def _relax_fingers(armature, meshes: dict) -> None:
    """Bend every joint of the four fingers by REST_FINGER_CURL_DEGREES toward the palm and make that the rest pose."""
    angle = math.radians(REST_FINGER_CURL_DEGREES)
    finger_bones = []
    for side in SIDES:
        hand = armature.data.bones[f"hand{side}"]
        direction = (hand.tail_local - hand.head_local).normalized()
        inward = Vector((-side_sign(side), 0.0, 0.0))
        palm = (inward - direction * inward.dot(direction)).normalized()
        for finger in RELAXED_FINGERS:
            for segment in range(1, FINGER_SEGMENTS + 1):
                bpy.context.view_layer.update()
                pose_bone = armature.pose.bones[f"{finger}_{segment:02d}{side}"]
                head = pose_bone.head.copy()
                axis = (pose_bone.tail - head).normalized().cross(palm).normalized()
                turn = Matrix.Translation(head) @ Matrix.Rotation(angle, 4, axis) @ Matrix.Translation(-head)
                pose_bone.matrix = turn @ pose_bone.matrix
                finger_bones.append(pose_bone.name)
    bpy.context.view_layer.update()
    posed = {name: (armature.pose.bones[name].head.copy(), armature.pose.bones[name].tail.copy()) for name in finger_bones}
    _bake_posed_meshes(armature, meshes, set(finger_bones))
    with _EditMode(armature):
        for name in finger_bones:
            armature.data.edit_bones[name].head, armature.data.edit_bones[name].tail = posed[name]


# ---------------------------------------------------------------------------------------------------
# Toes

# The model's feet and shoes are weighted to the foot only, so a heel lift would swing the toe box into the floor.
# The forefoot ahead of the ball joint moves to the toe bone, blended over this band centred on the ball.
TOE_BLEND = 0.03
FOOT_MESH_PARTS = ("Body", "Socks", "Shoes")


def weight_toes(armature, meshes: dict) -> None:
    """Hand the forefoot of the body, socks and shoes to the toe bones, and point each toe bone along its forefoot."""
    tips = {}
    for side in SIDES:
        ball = armature.data.bones[f"toe{side}"].head_local.copy()
        ankle = armature.data.bones[f"foot{side}"].head_local
        forward = Vector((ball.x - ankle.x, ball.y - ankle.y, 0.0)).normalized()
        reach = 0.0
        for part in FOOT_MESH_PARTS:
            mesh_object = meshes[part]
            foot_group = mesh_object.vertex_groups.get(f"foot{side}")
            if foot_group is None:
                continue
            toe_group = mesh_object.vertex_groups.get(f"toe{side}") or mesh_object.vertex_groups.new(name=f"toe{side}")
            for vertex in mesh_object.data.vertices:
                foot_weight = next((element.weight for element in vertex.groups if element.group == foot_group.index), 0.0)
                along = (mesh_object.matrix_world @ vertex.co - ball).dot(forward)
                share = max(0.0, min(1.0, along / TOE_BLEND + 0.5))
                if foot_weight <= 0.0 or share <= 0.0:
                    continue
                reach = max(reach, along)
                foot_group.add([vertex.index], foot_weight * (1.0 - share), "REPLACE")
                toe_group.add([vertex.index], foot_weight * share, "REPLACE")
        tips[side] = ball + forward * reach
    with _EditMode(armature):
        for side in SIDES:
            armature.data.edit_bones[f"toe{side}"].tail = tips[side]


# ---------------------------------------------------------------------------------------------------
# Skirt

class SkirtFrame:
    """The skirt's axis, waist and hem in the rest pose, and its outer surface by azimuth and height."""

    def __init__(self, skirt):
        points = numpy.array([tuple(skirt.matrix_world @ vertex.co) for vertex in skirt.data.vertices])
        self.points = points
        self.waist_z = float(points[:, 2].max())
        self.hem_z = float(points[:, 2].min())
        top = points[points[:, 2] > self.waist_z - SKIRT_SAMPLE_HEIGHT]
        self.center = Vector((0.0, float(top[:, 1].min() + top[:, 1].max()) * 0.5))
        self.azimuths = numpy.arctan2(points[:, 1] - self.center.y, points[:, 0] - self.center.x)
        self.radii = numpy.hypot(points[:, 0] - self.center.x, points[:, 1] - self.center.y)

    def fraction(self, z: float) -> float:
        return (self.waist_z - z) / (self.waist_z - self.hem_z)

    def height(self, fraction: float) -> float:
        return self.waist_z + (self.hem_z - self.waist_z) * fraction

    def outer_radius(self, azimuth: float, z: float) -> float:
        offsets = numpy.abs((self.azimuths - azimuth + math.pi) % (2.0 * math.pi) - math.pi)
        around = offsets < math.radians(SKIRT_SAMPLE_DEGREES)
        heights = numpy.abs(self.points[around, 2] - z)
        return float(self.radii[around][heights <= heights.min() + SKIRT_SAMPLE_HEIGHT].max())


def add_skirt_chains(armature, skirt) -> None:
    """Eight three-bone chains on the skirt's outer surface from waist to hem, and the skirt re-weighted to them."""
    frame = SkirtFrame(skirt)
    with _EditMode(armature):
        edit_bones = armature.data.edit_bones
        for chain_index, chain in enumerate(SKIRT_CHAINS):
            azimuth = skirt_chain_azimuth(chain_index)
            points = []
            for segment in range(SKIRT_SEGMENTS + 1):
                z = frame.height(segment / SKIRT_SEGMENTS)
                radius = frame.outer_radius(azimuth, z) - SKIRT_CHAIN_INSET
                points.append(Vector((frame.center.x + math.cos(azimuth) * radius,
                                      frame.center.y + math.sin(azimuth) * radius, z)))
            parent = edit_bones["hips"]
            for bone_name, head, tail in zip(chain_names(chain, SKIRT_SEGMENTS), points, points[1:]):
                edit_bone = edit_bones.new(bone_name)
                edit_bone.head, edit_bone.tail = head, tail
                edit_bone.parent = parent
                edit_bone.use_connect = parent.name != "hips"
                parent = edit_bone
    _weight_skirt(skirt, frame)


def _weight_skirt(skirt, frame: SkirtFrame) -> None:
    """The hips hold the waistband; below it azimuth blends the two nearest chains and height their segments.

    Open pleat edges that overlap at rest share one averaged weighting, so swinging chains never pull them apart.
    """
    weights = [_skirt_weights(Vector(point), frame) for point in frame.points]
    for cluster in _overlapping_edge_vertices(skirt):
        shared: dict = {}
        for index in cluster:
            for name, weight in weights[index].items():
                shared[name] = shared.get(name, 0.0) + weight / len(cluster)
        for index in cluster:
            weights[index] = shared
    skirt.vertex_groups.clear()
    groups = {}
    for vertex_index, vertex_weights in enumerate(weights):
        for name, weight in vertex_weights.items():
            if name not in groups:
                groups[name] = skirt.vertex_groups.new(name=name)
            groups[name].add([vertex_index], weight, "REPLACE")


def _overlapping_edge_vertices(skirt) -> list:
    """Groups of open-edge vertices lying within SKIRT_SEAM_DISTANCE of each other (both sides of a pleat overlap)."""
    edge_counts: dict = {}
    for polygon in skirt.data.polygons:
        for key in polygon.edge_keys:
            edge_counts[key] = edge_counts.get(key, 0) + 1
    open_vertices = sorted({index for key, count in edge_counts.items() if count == 1 for index in key})
    tree = KDTree(len(open_vertices))
    for index in open_vertices:
        tree.insert(skirt.data.vertices[index].co, index)
    tree.balance()
    parents = {index: index for index in open_vertices}

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for index in open_vertices:
        for _, other, _ in tree.find_range(skirt.data.vertices[index].co, SKIRT_SEAM_DISTANCE):
            parents[root(other)] = root(index)
    clusters: dict = {}
    for index in open_vertices:
        clusters.setdefault(root(index), []).append(index)
    return [cluster for cluster in clusters.values() if len(cluster) > 1]


def _skirt_weights(point: Vector, frame: SkirtFrame) -> dict:
    fraction = max(0.0, min(1.0, frame.fraction(point.z)))
    azimuth = math.atan2(point.y - frame.center.y, point.x - frame.center.x)
    position = ((-math.pi / 2 - azimuth) / (2 * math.pi) * len(SKIRT_CHAINS)) % len(SKIRT_CHAINS)
    first = int(position) % len(SKIRT_CHAINS)
    second = (first + 1) % len(SKIRT_CHAINS)
    chain_blend = position - int(position)
    segment_weights = {SKIRT_SEGMENTS - 1: 1.0}
    for (low, low_key), (high, high_key) in zip(pleats.SEGMENT_KEYS, pleats.SEGMENT_KEYS[1:]):
        if low <= fraction <= high:
            blend = (fraction - low) / (high - low)
            segment_weights = {low_key: 1.0 - blend}
            segment_weights[high_key] = segment_weights.get(high_key, 0.0) + blend
            break
    weights: dict = {}
    for key, segment_weight in segment_weights.items():
        if key == "hips":
            weights["hips"] = weights.get("hips", 0.0) + segment_weight
            continue
        for chain, chain_weight in ((first, 1.0 - chain_blend), (second, chain_blend)):
            name = chain_names(SKIRT_CHAINS[chain], SKIRT_SEGMENTS)[key]
            weights[name] = weights.get(name, 0.0) + segment_weight * chain_weight
    return {name: weight for name, weight in weights.items() if weight > 1e-4}


# ---------------------------------------------------------------------------------------------------
# Materials and face

def _assign_materials(meshes: dict, texture_directory: str) -> None:
    for mesh_object in meshes.values():
        for slot in mesh_object.material_slots:
            source = slot.material
            name, texture = MATERIAL_PARTS[source.name]
            slot.material = principled(name, (1.0, 1.0, 1.0), MATERIAL_ROUGHNESS,
                                       texture_path=os.path.join(texture_directory, texture), texture_alpha=False)
            if source.users == 0:
                bpy.data.materials.remove(source)


def _face_landmarks(face) -> FaceLandmarks:
    keys = face.data.shape_keys.key_blocks
    basis = _key_coordinates(keys[0])
    offsets = numpy.linalg.norm(_key_coordinates(keys[MOUTH_FLEX]) - basis, axis=1)
    mouth = basis[offsets > offsets.max() * LANDMARK_MOVE_FRACTION].mean(axis=0)
    eye_index = face.data.materials.find(MATERIAL_PARTS[EYE_MATERIAL][0])
    eye_vertices = sorted({index for polygon in face.data.polygons if polygon.material_index == eye_index
                           for index in polygon.vertices})
    eyes = basis[eye_vertices].mean(axis=0)
    return FaceLandmarks(Vector(mouth), Vector(eyes))


def bake_expressions(face) -> None:
    """Replace the model's flexes by the game's expression keys, each a weighted sum of flexes (EXPRESSION_FLEXES)."""
    keys = face.data.shape_keys.key_blocks
    basis_block = keys[0]
    basis_block.name = "Basis"
    basis = _key_coordinates(basis_block)
    flexes = {block.name: _key_coordinates(block) - basis for block in keys[1:]}
    for block in list(keys[1:]):
        face.shape_key_remove(block)
    for expression, weights in EXPRESSION_FLEXES.items():
        coordinates = basis.copy()
        for flex, weight in weights.items():
            coordinates += flexes[flex] * weight
        block = face.shape_key_add(name=expression, from_mix=False)
        block.data.foreach_set("co", coordinates.ravel())
        block.value = 0.0
    face.active_shape_key_index = 0


def _key_coordinates(block) -> numpy.ndarray:
    coordinates = numpy.empty(len(block.data) * 3)
    block.data.foreach_get("co", coordinates)
    return coordinates.reshape(-1, 3)


# ---------------------------------------------------------------------------------------------------
# Landmarks for the clips

def braid_layout(armature) -> target_animations.BraidLayout:
    names = [bone.name for bone in armature.data.bones]
    braid = tuple(name for name in names if name.startswith(BRAID_PREFIX) and not name.startswith(BRAID_BOW_PREFIX))
    bows = tuple(name for name in names if name.startswith(BRAID_BOW_PREFIX))
    waist = SkirtFrame(bpy.data.objects[f"{PREFIX}Skirt"]).waist_z
    resting = tuple(name for name in braid if armature.data.bones[name].tail_local.z < waist)
    return target_animations.BraidLayout(braid, bows, (f"{PREFIX}Hair",), resting)


def measure_stance(armature, meshes: dict, landmarks: FaceLandmarks) -> Stance:
    """The target's stance with every landmark measured on this model."""
    bones = armature.data.bones
    rest_ankles = {side: bones[f"foot{side}"].head_local.copy() for side in SIDES}
    chest_z = bones["chest"].head_local.z
    hanging = tuple(name for name in braid_layout(armature).bones if bones[name].head_local.z < chest_z)
    return target_animations.target_stance(
        rest_ankles, landmarks.mouth, hanging, _seat_clearance(armature, meshes), _heel_back(meshes["Shoes"], rest_ankles),
        _lap_offset(armature, meshes), _leg_radii(armature, meshes, True), _leg_radii(armature, meshes, False))


SEATED_SKIN_BONES = ("hips", "thigh", "glute_helper")
# The palm rests on the lap this far above the thigh's skin (palm depth plus the fabric under it).
LAP_HAND_CLEARANCE = 0.024
LAP_INWARD = 0.012
LAP_FRACTION = 0.52
LAP_SAMPLE_LENGTH = 0.03
SOLE_CONTACT_HEIGHT = 0.02


def _seat_clearance(armature, meshes: dict) -> float:
    """Height of the hip joints above the lowest skin under them when the thighs are raised level, as when seated."""
    hip_z = armature.data.bones["thigh.L"].head_local.z
    for side in SIDES:
        pose_bone = armature.pose.bones[f"thigh{side}"]
        rest = pose_bone.bone
        turn = (rest.tail_local - rest.head_local).rotation_difference(Vector((0.0, -1.0, 0.0))).to_matrix().to_4x4()
        pose_bone.matrix = Matrix.Translation(rest.head_local) @ turn @ Matrix.Translation(-rest.head_local) @ rest.matrix_local
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lowest = hip_z
    for mesh_object in (meshes["Body"], meshes["Socks"]):
        names = {group.index: group.name for group in mesh_object.vertex_groups}
        evaluated = mesh_object.evaluated_get(depsgraph)
        posed = evaluated.to_mesh()
        for vertex, posed_vertex in zip(mesh_object.data.vertices, posed.vertices):
            strongest = max(vertex.groups, key=lambda element: element.weight, default=None)
            if strongest is not None and names[strongest.group].startswith(SEATED_SKIN_BONES):
                lowest = min(lowest, (mesh_object.matrix_world @ posed_vertex.co).z)
        evaluated.to_mesh_clear()
    for side in SIDES:
        armature.pose.bones[f"thigh{side}"].matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    return hip_z - lowest


def _heel_back(shoes, rest_ankles: dict) -> float:
    """How far behind the ankle joint the shoe's heel meets the floor."""
    ankle = rest_ankles[".L"]
    heels = [(shoes.matrix_world @ vertex.co).y for vertex in shoes.data.vertices
             if (shoes.matrix_world @ vertex.co).z < SOLE_CONTACT_HEIGHT and (shoes.matrix_world @ vertex.co).x > 0.0]
    return max(heels) - ankle.y


def _lap_offset(armature, meshes: dict) -> Vector:
    """Where the resting palm sits relative to the thigh line: inward, and above the thigh's front skin when seated."""
    bones = armature.data.bones
    hip = bones["thigh.L"].head_local
    knee = bones["shin.L"].head_local
    axis = (knee - hip).normalized()
    lap = hip.lerp(knee, LAP_FRACTION)
    front = 0.0
    for mesh_object in (meshes["Body"], meshes["Socks"]):
        names = {group.index: group.name for group in mesh_object.vertex_groups}
        for vertex in mesh_object.data.vertices:
            strongest = max(vertex.groups, key=lambda element: element.weight, default=None)
            point = mesh_object.matrix_world @ vertex.co
            if (strongest is not None and names[strongest.group] == "thigh.L"
                    and abs((point - lap).dot(axis)) < LAP_SAMPLE_LENGTH):
                front = max(front, lap.y - point.y)
    return Vector((LAP_INWARD, 0.0, front + LAP_HAND_CLEARANCE))


# Rings of the thigh (fractions along hip to knee) whose radius sizes the skirt's leg capsules, and how far from the
# knee joint its skin counts as the knee.
THIGH_TOP_RING = (0.15, 0.4)
THIGH_BOTTOM_RING = (0.85, 0.95)
KNEE_REACH = 0.04


def _leg_radii(armature, meshes: dict, all_round: bool) -> tuple:
    """(thigh radius at its top, thigh radius at the knee, knee radius) of the left leg's skin.

    Standing (`all_round`), the thigh rings are measured all round, since a stride pushes the front and the side of
    the thigh into the skirt (where a ring already reaches the hanging skirt at rest, clear_legs keeps only that rest
    clearance). Seated, the thigh's front becomes its top, under the lap of the skirt, so it is measured forward. The
    knee is always measured forward: only the bent knee's front juts out.
    """
    bones = armature.data.bones
    hip = bones["thigh.L"].head_local
    knee = bones["shin.L"].head_local
    axis = knee - hip
    forward = Vector((0.0, -1.0, 0.0))
    top = bottom = knee_radius = 0.0
    for mesh_object in (meshes["Body"], meshes["Socks"]):
        names = {group.index: group.name for group in mesh_object.vertex_groups}
        for vertex in mesh_object.data.vertices:
            strongest = max(vertex.groups, key=lambda element: element.weight, default=None)
            if strongest is None or names[strongest.group] not in ("thigh.L", "shin.L"):
                continue
            point = mesh_object.matrix_world @ vertex.co
            fraction = (point - hip).dot(axis) / axis.length_squared
            offset = point - (hip + axis * fraction)
            reach = offset.length if all_round else offset.dot(forward)
            if (point - knee).length < KNEE_REACH:
                knee_radius = max(knee_radius, (point - knee).dot(forward))
            if names[strongest.group] != "thigh.L":
                continue
            if THIGH_TOP_RING[0] <= fraction <= THIGH_TOP_RING[1]:
                top = max(top, reach)
            elif THIGH_BOTTOM_RING[0] <= fraction <= THIGH_BOTTOM_RING[1]:
                bottom = max(bottom, reach)
    return top, bottom, knee_radius


# ---------------------------------------------------------------------------------------------------
# Spring chains (data/secondary_motion.tres)

# Family -> (chain bone prefixes, joint radius, collider bones). The *_helper bones are never in a family.
SPRING_FAMILIES = {
    "braid": (("braid_0",), 0.03, ("chest", "hips")),
    "hair_front": (("hair_front_",), 0.015, ("head",)),
    "hair_side": (("hair_side_",), 0.02, ("head",)),
    "hair_back": (("hair_back_",), 0.02, ("head",)),
    "head_bow": (("head_bow_",), 0.015, ("head",)),
    "ribbon": (("ribbon_",), 0.015, ("chest",)),
    "skirt": (("skirt_",), 0.025, ("thigh.L", "thigh.R", "hips")),
    "braid_bow": ((BRAID_BOW_PREFIX,), 0.02, ("hips", "thigh.L", "thigh.R")),
}
# Capsule radius wanted per collider bone; a capsule shrinks where a chain joint would start inside it.
COLLIDER_RADII = {"thigh.L": 0.065, "thigh.R": 0.065, "hips": 0.12, "chest": 0.11, "head": 0.085}
COLLIDER_SKIN_BONES = {"thigh.L": ("thigh.L",), "thigh.R": ("thigh.R",), "hips": ("hips", "glute_helper"),
                       "chest": ("chest", "spine", "chest_helper"), "head": ("head",)}
COLLIDER_CLEARANCE = 0.002


def spring_chains(armature, prefixes: tuple) -> list:
    """(root, end) of every chain whose bones start with one of `prefixes`: each root follows its first matching child."""
    bones = armature.data.bones
    chains = []
    for bone in bones:
        if not bone.name.startswith(prefixes) or (bone.parent is not None and bone.parent.name.startswith(prefixes)):
            continue
        end = bone
        while True:
            following = sorted((child for child in end.children if child.name.startswith(prefixes)), key=lambda child: child.name)
            if not following:
                break
            end = following[0]
        chains.append((bone.name, end.name))
    return sorted(chains)


def _chain_joints(armature, root: str, end: str) -> list:
    """Rest positions of the simulated joints: the heads below the root and the end bone's tip."""
    bones = armature.data.bones
    joints = [bones[end].tail_local.copy()]
    walker = bones[end]
    while walker.name != root:
        joints.append(walker.head_local.copy())
        walker = walker.parent
    return joints


def fit_colliders(armature, meshes: dict) -> dict:
    """Bone -> (radius, height, local centre): a capsule along the bone covering its skin, clear of every chain joint."""
    joints_by_collider: dict = {}
    for prefixes, joint_radius, colliders in SPRING_FAMILIES.values():
        for root, end in spring_chains(armature, prefixes):
            for collider in colliders:
                joints_by_collider.setdefault(collider, []).extend(
                    (joint, joint_radius) for joint in _chain_joints(armature, root, end))
    fitted = {}
    for bone_name, wanted_radius in COLLIDER_RADII.items():
        to_local = armature.data.bones[bone_name].matrix_local.inverted()
        skin = [to_local @ point for point in _skin_points(meshes, COLLIDER_SKIN_BONES[bone_name])]
        joints = [(to_local @ joint, joint_radius) for joint, joint_radius in joints_by_collider.get(bone_name, [])]
        fitted[bone_name] = max((_clear_capsule(start, end, wanted_radius, joints) for start, end in _capsule_candidates(skin)),
                                key=lambda capsule: capsule[0] ** 2 * capsule[1])
    return fitted


def _capsule_candidates(skin: list) -> list:
    """Axis segments along the bone: the whole skin's span, or a sphere at the middle of the skin, its upper or its
    lower half (the head's cranium, the pelvis below a hugging waistband). The one covering the most volume wins."""
    center = _box_center(skin)
    middle = center.y
    candidates = [(Vector((center.x, min(point.y for point in skin), center.z)),
                   Vector((center.x, max(point.y for point in skin), center.z))), (center, center)]
    for half in ([point for point in skin if point.y >= middle], [point for point in skin if point.y < middle]):
        half_center = _box_center(half)
        candidates.append((half_center, half_center))
    return candidates


def _box_center(points: list) -> Vector:
    """Middle of the points' bounding box (dense detail such as the eyes would pull a mean off centre)."""
    return Vector(tuple((min(point[axis] for point in points) + max(point[axis] for point in points)) * 0.5
                        for axis in range(3)))


def _clear_capsule(start: Vector, end: Vector, wanted_radius: float, joints: list) -> tuple:
    """(radius, height, centre) of the capsule on `start`..`end`, shrunk until every chain joint is outside it."""
    radius = wanted_radius
    for local, joint_radius in joints:
        radius = min(radius, (local - mesh_utils.closest_point_on_segment(local, start, end)).length
                     - joint_radius - COLLIDER_CLEARANCE)
    return radius, (end - start).length + 2.0 * radius, (start + end) * 0.5


def _skin_points(meshes: dict, bone_names: tuple) -> list:
    points = []
    for mesh_object in (meshes["Body"], meshes["Face"]):
        names = {group.index: group.name for group in mesh_object.vertex_groups}
        for vertex in mesh_object.data.vertices:
            strongest = max(vertex.groups, key=lambda element: element.weight, default=None)
            if strongest is not None and names[strongest.group].startswith(bone_names):
                points.append(mesh_object.matrix_world @ vertex.co)
    return points


def secondary_motion_report(armature, meshes: dict) -> str:
    """The chains, leaf lengths and fitted capsules that data/secondary_motion.tres is written from."""
    lines = []
    for family, (prefixes, joint_radius, colliders) in SPRING_FAMILIES.items():
        chains = spring_chains(armature, prefixes)
        lengths = [round(armature.data.bones[end].length, 4) for _, end in chains]
        lines.append(f"chain {family} radius {joint_radius} colliders {list(colliders)}")
        lines.append(f"  roots {[root for root, _ in chains]}")
        lines.append(f"  ends {[end for _, end in chains]}")
        lines.append(f"  end lengths {lengths}")
    for bone_name, (radius, height, center) in fit_colliders(armature, meshes).items():
        lines.append(f"collider {bone_name} radius {radius:.4f} height {height:.4f} "
                     f"offset ({center.x:.4f}, {center.y:.4f}, {center.z:.4f})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------------
# Collision proxy

def build_collision_proxy(armature, meshes: dict) -> bpy.types.Object:
    """A standing capsule around the torso, skirt and legs (Ruling R4); the arms and hair stay outside it."""
    radius = 0.0
    for mesh_object in (meshes["Body"], meshes["Top"], meshes["Skirt"], meshes["Socks"], meshes["Shoes"]):
        names = {group.index: group.name for group in mesh_object.vertex_groups}
        for vertex in mesh_object.data.vertices:
            strongest = max(vertex.groups, key=lambda element: element.weight, default=None)
            if strongest is not None and names[strongest.group].startswith(PROXY_BONE_PREFIXES):
                point = mesh_object.matrix_world @ vertex.co
                radius = max(radius, math.hypot(point.x, point.y))
    radius = math.ceil(radius / PROXY_RADIUS_STEP) * PROXY_RADIUS_STEP
    return clothing.build_collision_proxy(armature, body.CharacterParams(prefix=PREFIX, height=CROWN_HEIGHT),
                                          radius, COLLISION_PROXY)


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
