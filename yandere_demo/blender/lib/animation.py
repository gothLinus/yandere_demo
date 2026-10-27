"""Procedural keyframed animation: rest-pose maths, two-bone IK, gait and pose helpers, and the action writer.

Every rotation in this module is a *rest-axis delta*: it turns a bone about its head, relative to its
parent, expressed in the armature's rest frame (+X is the character's left, -Y is forward, +Z is up).
Deltas compose like forward kinematics, so a child's delta rides on its parent's. Positive X bends a
bone's tip toward +Y for a bone hanging down, and tips the spine forward for a bone pointing up.
`make_action` converts the deltas into Blender's bone-local quaternions. Locations are armature-space
offsets of a bone head. Scales are bone-local (Y runs along the bone) and only gather cloth.
"""

import math
from dataclasses import dataclass, field
from typing import Callable

import bpy
import numpy
from bpy_extras import anim_utils
from mathutils import Euler, Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

FPS = 30
SIDES = (".L", ".R")
UP = Vector((0.0, 0.0, 1.0))
FORWARD = Vector((0.0, -1.0, 0.0))
# Joint bend directions at rest: knees point forward, elbows point back.
LEG_REST_POLE = Vector((0.0, -1.0, 0.0))
# The knee pole's outward share: the knees point a little outward over the toes.
KNEE_SPLAY = 0.12
ARM_REST_POLE = Vector((0.0, 1.0, 0.0))
# A straight two-bone chain flips its bend unpredictably, so reach stops short of full extension.
MAX_REACH = 0.996


def side_sign(side: str) -> float:
    return 1.0 if side == ".L" else -1.0


def degrees(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Quaternion:
    """Rest-axis rotation applied X first, then Y, then Z."""
    return Euler((math.radians(x), math.radians(y), math.radians(z)), "XYZ").to_quaternion()


def mirrored_degrees(side: str, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Quaternion:
    """Rotation authored for the left side; the right side mirrors it across the X = 0 plane."""
    sign = side_sign(side)
    return degrees(x, y * sign, z * sign)


def mirrored_point(side: str, point) -> Vector:
    return Vector((point[0] * side_sign(side), point[1], point[2]))


def smoothstep(edge_start: float, edge_end: float, value: float) -> float:
    if edge_end == edge_start:
        return 1.0 if value >= edge_end else 0.0
    fraction = min(1.0, max(0.0, (value - edge_start) / (edge_end - edge_start)))
    return fraction * fraction * (3.0 - 2.0 * fraction)


def lerp(start, end, fraction: float):
    return start + (end - start) * fraction


def canonical(rotation: Quaternion) -> Quaternion:
    """Keep w >= 0 so consecutive keys never flip hemispheres (all deltas here stay below 180 degrees)."""
    return -rotation if rotation.w < 0.0 else rotation.copy()


class Skeleton:
    """Rest-pose data of an armature in armature space."""

    def __init__(self, armature):
        bones = list(armature.data.bones)
        self.names = [bone.name for bone in sorted(bones, key=lambda bone: len(bone.parent_recursive))]
        self.parents = {bone.name: bone.parent.name if bone.parent else None for bone in bones}
        self.heads = {bone.name: bone.head_local.copy() for bone in bones}
        self.tails = {bone.name: bone.tail_local.copy() for bone in bones}
        self.rest_rotations = {bone.name: bone.matrix_local.to_quaternion() for bone in bones}

        self.children = {bone.name: [child.name for child in bone.children] for bone in bones}
        self._chains: dict = {}

    def length(self, name: str) -> float:
        return (self.tails[name] - self.heads[name]).length

    def _follow_chain(self, root: str, prefix: str) -> list:
        chain = [root]
        while True:
            next_bones = [child for child in self.children[chain[-1]] if child.startswith(prefix)]
            if not next_bones:
                return chain
            chain.append(sorted(next_bones)[0])

    def chains(self, prefix: str) -> list:
        """Bone chains whose names start with `prefix`, root first, in name order."""
        key = ("prefix", prefix)
        if key not in self._chains:
            roots = [name for name in sorted(self.names) if name.startswith(prefix)
                     and not (self.parents[name] or "").startswith(prefix)]
            self._chains[key] = [self._follow_chain(root, prefix) for root in roots]
        return self._chains[key]

    def chains_under(self, parent: str) -> list:
        """One chain per child of `parent` (e.g. the fingers of a hand), each followed down its first child."""
        key = ("parent", parent)
        if key not in self._chains:
            self._chains[key] = [self._follow_chain(child, "") for child in sorted(self.children[parent])]
        return self._chains[key]

    def direction(self, name: str) -> Vector:
        return (self.tails[name] - self.heads[name]).normalized()


@dataclass
class Pose:
    rotations: dict = field(default_factory=dict)
    offsets: dict = field(default_factory=dict)
    scales: dict = field(default_factory=dict)

    def copy(self) -> "Pose":
        return Pose({name: rotation.copy() for name, rotation in self.rotations.items()},
                    {name: offset.copy() for name, offset in self.offsets.items()},
                    {name: scale.copy() for name, scale in self.scales.items()})

    def rotation(self, bone: str) -> Quaternion:
        return self.rotations.get(bone, Quaternion())

    def offset(self, bone: str) -> Vector:
        return self.offsets.get(bone, Vector())

    def turn(self, bone: str, rotation: Quaternion) -> None:
        """Apply `rotation` after the bone's current delta (both in rest axes)."""
        self.rotations[bone] = rotation @ self.rotation(bone)

    def turn_degrees(self, bone: str, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.turn(bone, degrees(x, y, z))

    def turn_side(self, bone: str, side: str, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.turn(bone + side, mirrored_degrees(side, x, y, z))

    def move(self, bone: str, offset) -> None:
        self.offsets[bone] = self.offset(bone) + Vector(offset)


def bend(skeleton: Skeleton, pose: Pose, bone: str, angle_degrees: float, toward) -> None:
    """Swing a bone's rest direction toward `toward` by an angle, as a rest-axis delta."""
    direction = skeleton.direction(bone)
    axis = direction.cross(Vector(toward))
    if axis.length < 1e-8:
        return
    pose.turn(bone, Quaternion(axis.normalized(), math.radians(angle_degrees)))


def forward_kinematics(skeleton: Skeleton, pose: Pose) -> tuple[dict, dict]:
    """World rotation deltas and head positions of every bone."""
    world: dict = {}
    heads: dict = {}
    for name in skeleton.names:
        parent = skeleton.parents[name]
        local = pose.rotation(name)
        if parent is None:
            world[name] = local
            heads[name] = skeleton.heads[name] + pose.offset(name)
            continue
        relative = skeleton.heads[name] - skeleton.heads[parent] + pose.offset(name)
        world[name] = world[parent] @ local
        heads[name] = heads[parent] + world[parent] @ relative
    return world, heads


def tail_position(skeleton: Skeleton, world: dict, heads: dict, bone: str) -> Vector:
    return heads[bone] + world[bone] @ (skeleton.tails[bone] - skeleton.heads[bone])


def world_point(skeleton: Skeleton, world: dict, heads: dict, bone: str, rest_point) -> Vector:
    """Where a rest-pose point rigidly attached to `bone` ends up."""
    return heads[bone] + world[bone] @ (Vector(rest_point) - skeleton.heads[bone])


def set_world_rotation(skeleton: Skeleton, pose: Pose, bone: str, world_rotation: Quaternion) -> None:
    world, _ = forward_kinematics(skeleton, pose)
    parent = skeleton.parents[bone]
    parent_world = world[parent] if parent else Quaternion()
    pose.rotations[bone] = parent_world.inverted() @ world_rotation


def _frame(direction: Vector, reference: Vector) -> Matrix:
    axis_y = direction.normalized()
    axis_x = reference - axis_y * reference.dot(axis_y)
    if axis_x.length < 1e-8:
        axis_x = axis_y.orthogonal()
    axis_x.normalize()
    axis_z = axis_x.cross(axis_y)
    return Matrix((axis_x, axis_y, axis_z)).transposed()


def aligning_rotation(rest_direction: Vector, rest_reference: Vector, direction: Vector, reference: Vector) -> Quaternion:
    """Rotation taking a rest direction (with a perpendicular reference) onto a new one."""
    return (_frame(direction, reference) @ _frame(rest_direction, rest_reference).transposed()).to_quaternion()


def solve_two_bone(skeleton: Skeleton, pose: Pose, upper: str, lower: str, target, pole, rest_pole: Vector) -> float:
    """Aim `upper`/`lower` so the tail of `lower` reaches `target`, bending toward `pole`. Returns reach used (0..1)."""
    world, heads = forward_kinematics(skeleton, pose)
    parent_world = world[skeleton.parents[upper]]
    root = heads[upper]
    upper_length = skeleton.length(upper)
    lower_length = skeleton.length(lower)
    offset = Vector(target) - root
    full_reach = upper_length + lower_length
    distance = min(max(offset.length, abs(upper_length - lower_length) + 1e-4), full_reach * MAX_REACH)
    toward = offset.normalized()
    bend_direction = Vector(pole) - toward * Vector(pole).dot(toward)
    if bend_direction.length < 1e-8:
        bend_direction = toward.orthogonal()
    bend_direction.normalize()
    cosine = (upper_length ** 2 + distance ** 2 - lower_length ** 2) / (2.0 * upper_length * distance)
    cosine = min(1.0, max(-1.0, cosine))
    joint = root + (toward * cosine + bend_direction * math.sqrt(1.0 - cosine * cosine)) * upper_length
    end = root + toward * distance
    upper_world = aligning_rotation(skeleton.direction(upper), rest_pole, joint - root, bend_direction)
    lower_world = aligning_rotation(skeleton.direction(lower), rest_pole, end - joint, bend_direction)
    pose.rotations[upper] = parent_world.inverted() @ upper_world
    pose.rotations[lower] = upper_world.inverted() @ lower_world
    return offset.length / full_reach


def share_twist(skeleton: Skeleton, pose: Pose, forearm: str, hand: str, fraction: float) -> None:
    """Move part of the hand's twist about the arm axis into the forearm, so the wrist does not candy-wrap."""
    axis = skeleton.direction(forearm)
    hand_delta = pose.rotation(hand)
    projection = axis * Vector(hand_delta[1:]).dot(axis)
    twist = Quaternion((hand_delta.w, projection.x, projection.y, projection.z))
    if twist.magnitude < 1e-8:
        return
    twist.normalize()
    angle = twist.angle if Vector(twist[1:]).dot(axis) >= 0.0 else -twist.angle
    if angle > math.pi:
        angle -= 2.0 * math.pi
    shared = Quaternion(axis, angle * fraction)
    pose.rotations[forearm] = pose.rotation(forearm) @ shared
    pose.rotations[hand] = shared.inverted() @ hand_delta


class Curve:
    """Monotone cubic (PCHIP) interpolation through keyed tuples.

    It never overshoots, eases into holds and reversals, and keeps moving through monotone keys,
    much like Blender's auto-clamped handles. With `period` it wraps, so the loop seam is as smooth
    as any other key.
    """

    def __init__(self, keys: list, period: float | None = None):
        keys = sorted((float(frame), tuple(float(value) for value in _as_tuple(values))) for frame, values in keys)
        self.period = period
        if period is not None:
            if keys[-1][0] >= period - 1e-6:
                first_frame, first_values = keys[0]
                if abs(first_frame) > 1e-6 or any(abs(last - first) > 1e-9 for last, first in zip(keys[-1][1], first_values)):
                    raise ValueError(f"periodic curve: key at frame {period} must repeat the key at frame 0")
                keys = keys[:-1]
            body = keys
            before = [(frame - period, values) for frame, values in body[-2:]]
            after = [(frame + period, values) for frame, values in body[:2]]
            keys = before + body + after
        self.frames = [frame for frame, _ in keys]
        self.values = [values for _, values in keys]
        self.slopes = self._slopes()

    def _slopes(self) -> list:
        count = len(self.frames)
        dimension = len(self.values[0])
        slopes = [[0.0] * dimension for _ in range(count)]
        for index in range(1, count - 1):
            before = self.frames[index] - self.frames[index - 1]
            after = self.frames[index + 1] - self.frames[index]
            for component in range(dimension):
                secant_before = (self.values[index][component] - self.values[index - 1][component]) / before
                secant_after = (self.values[index + 1][component] - self.values[index][component]) / after
                if secant_before * secant_after <= 0.0:
                    continue
                weight_before = 2.0 * after + before
                weight_after = after + 2.0 * before
                slopes[index][component] = (weight_before + weight_after) / (
                    weight_before / secant_before + weight_after / secant_after)
        return slopes

    def __call__(self, frame: float) -> tuple:
        if self.period is not None:
            frame = frame % self.period
        if frame <= self.frames[0]:
            return self.values[0]
        if frame >= self.frames[-1]:
            return self.values[-1]
        index = max(index for index, key_frame in enumerate(self.frames) if key_frame <= frame)
        index = min(index, len(self.frames) - 2)
        width = self.frames[index + 1] - self.frames[index]
        fraction = (frame - self.frames[index]) / width
        square = fraction * fraction
        cube = square * fraction
        start_weight = 2 * cube - 3 * square + 1
        start_slope_weight = (cube - 2 * square + fraction) * width
        end_weight = -2 * cube + 3 * square
        end_slope_weight = (cube - square) * width
        start, end = self.values[index], self.values[index + 1]
        start_slope, end_slope = self.slopes[index], self.slopes[index + 1]
        return tuple(start_weight * start[component] + start_slope_weight * start_slope[component]
                     + end_weight * end[component] + end_slope_weight * end_slope[component]
                     for component in range(len(start)))

    def scalar(self, frame: float) -> float:
        return self(frame)[0]

    def vector(self, frame: float) -> Vector:
        return Vector(self(frame))


def _as_tuple(values) -> tuple:
    if isinstance(values, (int, float)):
        return (values,)
    return tuple(values)


def hermite(start: Vector, start_tangent: Vector, end: Vector, end_tangent: Vector, fraction: float) -> Vector:
    square = fraction * fraction
    cube = square * fraction
    return (start * (2 * cube - 3 * square + 1) + start_tangent * (cube - 2 * square + fraction)
            + end * (-2 * cube + 3 * square) + end_tangent * (cube - square))


# ---------------------------------------------------------------------------------------------------
# Feet

@dataclass
class FootPlacement:
    """A foot on the ground: ankle x/y, toe-out yaw and heel-up pitch about the heel or ball contact."""

    x: float
    y: float
    yaw_degrees: float = 0.0
    pitch_degrees: float = 0.0
    toe_flat: bool = True


class FootGeometry:
    """Ground contact points of one foot, taken from the rest pose."""

    def __init__(self, skeleton: Skeleton, side: str, heel_back: float = 0.025):
        self.ankle = skeleton.heads[f"foot{side}"].copy()
        # The heel rocks on the ground; the forefoot rolls over the ball joint, so the toes stay at rest height.
        self.heel = Vector((self.ankle.x, self.ankle.y + heel_back, 0.0))
        self.ball = skeleton.heads[f"toe{side}"].copy()

    def placement_transform(self, placement: FootPlacement) -> tuple[Vector, Quaternion]:
        """Ankle position and world rotation of the foot for a placement."""
        yaw = Quaternion(UP, math.radians(placement.yaw_degrees))
        pitch = Quaternion(Vector((1.0, 0.0, 0.0)), math.radians(placement.pitch_degrees))
        flat_origin = Vector((placement.x, placement.y, self.ankle.z))
        pivot = self.heel if placement.pitch_degrees < 0.0 else self.ball
        pivot_world = flat_origin + yaw @ (pivot - self.ankle)
        ankle = pivot_world + yaw @ (pitch @ (self.ankle - pivot))
        return ankle, yaw @ pitch


def place_leg(skeleton: Skeleton, pose: Pose, side: str, geometry: FootGeometry, placement: FootPlacement,
              toe_bend_degrees: float = 0.0, knee_splay: float = KNEE_SPLAY) -> float:
    """Solve thigh and shin so the foot sits at `placement`; the toe stays flat on the ground when asked.

    `knee_splay` is the knee pole's outward share (negative turns the knees inward)."""
    ankle, foot_world = geometry.placement_transform(placement)
    yaw = Quaternion(UP, math.radians(placement.yaw_degrees))
    pole = yaw @ Vector((side_sign(side) * knee_splay, -1.0, 0.0))
    reach = solve_two_bone(skeleton, pose, f"thigh{side}", f"shin{side}", ankle, pole, LEG_REST_POLE)
    set_world_rotation(skeleton, pose, f"foot{side}", foot_world)
    if placement.toe_flat and placement.pitch_degrees > 0.0:
        set_world_rotation(skeleton, pose, f"toe{side}", yaw)
    else:
        pose.rotations[f"toe{side}"] = degrees(-toe_bend_degrees)
    return reach


def hip_joint_height_limit(skeleton: Skeleton, pose: Pose, side: str, ankle: Vector, reach: float) -> float:
    """Highest hips offset z that still lets this leg reach `ankle` at the given reach fraction."""
    _, heads = forward_kinematics(skeleton, pose)
    hip = heads[f"thigh{side}"]
    horizontal = Vector((ankle.x - hip.x, ankle.y - hip.y, 0.0)).length
    length = (skeleton.length(f"thigh{side}") + skeleton.length(f"shin{side}")) * reach
    vertical = math.sqrt(max(0.0, length * length - horizontal * horizontal))
    return pose.offset("hips").z + ankle.z + vertical - hip.z


# ---------------------------------------------------------------------------------------------------
# Arms and hands

def palm_normal(skeleton: Skeleton, side: str) -> Vector:
    """Rest palm direction: the hand faces the body."""
    direction = skeleton.direction(f"hand{side}")
    inward = Vector((-side_sign(side), 0.0, 0.0))
    return (inward - direction * inward.dot(direction)).normalized()


def reach_arm(skeleton: Skeleton, pose: Pose, side: str, wrist_target, elbow_pole) -> float:
    return solve_two_bone(skeleton, pose, f"upper_arm{side}", f"forearm{side}", wrist_target, elbow_pole, ARM_REST_POLE)


def aim_hand(skeleton: Skeleton, pose: Pose, side: str, finger_direction, palm_direction, twist_share: float = 0.5) -> None:
    """Point the hand's fingers along `finger_direction` with the palm facing `palm_direction` (world)."""
    rotation = aligning_rotation(skeleton.direction(f"hand{side}"), palm_normal(skeleton, side),
                                 Vector(finger_direction), Vector(palm_direction))
    set_world_rotation(skeleton, pose, f"hand{side}", rotation)
    share_twist(skeleton, pose, f"forearm{side}", f"hand{side}", twist_share)


FINGER_CHAIN_PREFIXES = ("thumb_", "index_", "middle_", "ring_", "pinky_")


def curl_fingers(skeleton: Skeleton, pose: Pose, side: str, fingers_degrees: float, thumb_degrees: float) -> None:
    """Curl the finger chains under the hand toward the palm, sharing the angle evenly over their segments.

    Only chains named like fingers (`FINGER_CHAIN_PREFIXES`) curl, so props or attachment bones parented to
    the hand are left alone. The thumb takes `thumb_degrees` and curls across the palm; the others take
    `fingers_degrees`.
    """
    hand = f"hand{side}"
    palm = palm_normal(skeleton, side)
    across_palm = palm + skeleton.direction(hand) * 0.5
    for chain in skeleton.chains_under(hand):
        if not chain[0].startswith(FINGER_CHAIN_PREFIXES):
            continue
        is_thumb = chain[0].startswith("thumb_")
        angle = (thumb_degrees if is_thumb else fingers_degrees) / len(chain)
        for bone in chain:
            pose.rotations[bone] = Quaternion()
            bend(skeleton, pose, bone, angle, across_palm if is_thumb else palm)


# ---------------------------------------------------------------------------------------------------
# Secondary motion helpers

def idle_breathing(pose: Pose, phase: float, amount: float = 1.0) -> None:
    """Additive breathing for one breath per unit of `phase` (inhale peaks at phase 0.4)."""
    breath = 0.5 - 0.5 * math.cos(2.0 * math.pi * (phase - 0.4) + math.pi)
    pose.turn_degrees("spine", x=-0.6 * amount * breath)
    pose.turn_degrees("chest", x=-1.4 * amount * breath)
    pose.turn_degrees("neck", x=1.2 * amount * breath)
    pose.turn_degrees("head", x=0.6 * amount * breath)
    for side in SIDES:
        pose.turn_side("shoulder", side, y=1.2 * amount * breath)
        pose.turn_side("upper_arm", side, y=-1.0 * amount * breath)


SKIRT_PREFIX = "skirt_"


def _skirt_facing(skeleton: Skeleton, chain: list) -> tuple[Vector, dict]:
    """Outward azimuth of a skirt chain around the hips, and its share of front, back, left and right."""
    root = chain[0]
    parent = skeleton.parents[root]
    center = skeleton.heads[parent] if parent else Vector()
    outward = (skeleton.heads[root] - center) + skeleton.direction(root)
    azimuth = Vector((outward.x, outward.y, 0.0))
    azimuth = azimuth.normalized() if azimuth.length > 1e-6 else Vector((0.0, -1.0, 0.0))
    facing = {"front": max(0.0, -azimuth.y), "back": max(0.0, azimuth.y),
              ".L": max(0.0, azimuth.x), ".R": max(0.0, -azimuth.x)}
    total = sum(facing.values())
    return azimuth, {name: share / total for name, share in facing.items()}


def _tip_swing(toward_back: float, toward_left: float) -> Quaternion:
    """Rest-axis rotation that swings a hanging bone's tip by degrees toward +Y and toward +X."""
    return degrees(x=toward_back, y=-toward_left)


# Seated, the sat-on back panels hang just past the buttocks and their lower segments fold forward under them
# (hidden between body and seat) instead of trailing behind the seat.
SEATED_BACK_HANG = 12.0
SEATED_BACK_TUCK = 70.0


def follow_skirt(skeleton: Skeleton, pose: Pose, sway_degrees: float = 0.0, seated: float | None = None,
                 leg_radii: tuple | None = None, sample_allowances: bool = False,
                 front_drop: float = 0.0) -> None:
    """Swing every skirt chain with the thighs so the hem rides over the legs instead of through them.

    Chains are found by the `skirt_` prefix, so any number of chains with any number of segments works.
    Each chain gets an azimuth from its rest direction and blends four behaviours by how much it faces
    front, back, left or right: front panels follow the forward thigh swing, back panels the backward
    swing, side panels their own thigh's lift and spread. `sway_degrees` swings every hem toward +X.
    The root segment takes the main swing; the remaining segments share the follow-through (hem droop,
    seated drape). `seated` (0..1) drapes the skirt over the lap; by default it is derived from the
    thigh lift. `leg_radii` (thigh top, thigh at the knee, knee) sizes the legs the skirt keeps clear of;
    `sample_allowances` is passed on to `clear_legs`. `front_drop` (0..1) lets the lower segments of the front
    panel fall that far toward hanging straight down, into the gap between thighs held together.
    """
    chains = skeleton.chains(SKIRT_PREFIX)
    if not chains:
        return
    world, _ = forward_kinematics(skeleton, pose)
    hips_inverse = world["hips"].inverted()
    forward_angles = {}
    spread_angles = {}
    for side in SIDES:
        direction = hips_inverse @ (world[f"thigh{side}"] @ skeleton.direction(f"thigh{side}"))
        forward_angles[side] = math.degrees(math.atan2(-direction.y, -direction.z))
        spread_angles[side] = math.degrees(math.atan2(side_sign(side) * direction.x, -direction.z)) - 2.0
    if seated is None:
        seated = smoothstep(35.0, 80.0, min(forward_angles.values()))

    def soft_max(first: float, second: float) -> float:
        return 0.5 * (first + second + math.sqrt((first - second) ** 2 + 16.0))

    forward = max(0.0, soft_max(forward_angles[".L"], forward_angles[".R"]))
    backward = max(0.0, soft_max(-forward_angles[".L"], -forward_angles[".R"]))
    hips_up = world["hips"] @ UP
    # Positive when the pelvis tips forward; the loose back and side panels keep hanging toward the floor.
    pelvis_pitch = math.degrees(math.atan2(-hips_up.y, hips_up.z))
    # Seated, the back panel lies on the seat, so leaning forward must not lift it off.
    hang = -pelvis_pitch * lerp(0.6, 1.0, seated)
    side_hang = -pelvis_pitch * 0.6 * (1.0 - seated)
    front = forward * 0.72 if forward < 28.0 else forward - 7.8
    # Past the knees the hem droops instead of sticking out like a shelf.
    droop = max(0.0, front - 25.0) * 0.9
    back = backward * 0.6
    spreads = {side: max(0.0, spread_angles[side]) * 0.7 for side in SIDES}
    lifts = {side: max(0.0, forward_angles[side]) * 0.3 * (1.0 - seated) for side in SIDES}

    for chain in chains:
        _, share = _skirt_facing(skeleton, chain)
        sides = share[".L"] + share[".R"]
        # Seated, the back panel angles down past the buttocks and the sides drape forward over the thighs.
        root_back = (share["back"] * (back + SEATED_BACK_HANG * seated + hang)
                     - share["front"] * front * (1.0 - 0.15 * seated)
                     + sum(share[side] * (side_hang - lifts[side] - 12.0 * seated) for side in SIDES))
        root_left = sway_degrees + sum(share[side] * side_sign(side) * (spreads[side] - 6.0 * seated) for side in SIDES)
        follow_back = (share["front"] * ((droop - front * 0.18) * (1.0 - seated) + 24.0 * seated)
                       + share["back"] * (back * 0.25 - SEATED_BACK_TUCK * seated) - sides * 6.0 * seated)
        follow_left = sum(share[side] * (side_sign(side) * spreads[side] * 0.2 + sway_degrees * 0.4) for side in SIDES)
        segments = len(chain) - 1
        pose.rotations[chain[0]] = _tip_swing(root_back, root_left)
        for bone in chain[1:]:
            pose.rotations[bone] = _tip_swing(follow_back / segments, follow_left / segments)
        if share["back"] > 1e-3:
            # Sat-on fabric bunches up instead of trailing far behind the seat.
            pose.scales[chain[0]] = Vector((1.0, 1.0 - 0.25 * seated * share["back"], 1.0))
            follow_scale = (1.0 - 0.35 * seated * share["back"]) ** (1.0 / max(1, segments))
            for bone in chain[1:]:
                pose.scales[bone] = Vector((1.0, follow_scale, 1.0))
    clear_legs(skeleton, pose, chains, leg_radii or DEFAULT_LEG_RADII, sample_allowances, sample_allowances)
    if front_drop > 0.0:
        _drop_front(skeleton, pose, chains, front_drop)


def _drop_front(skeleton: Skeleton, pose: Pose, chains: list, amount: float) -> None:
    """Turn the lower segments of the front-facing chains `amount` (0..1) of the way to hanging straight down; a
    chain at 45 degrees from the front or further keeps its shape."""
    for chain in chains:
        _, share = _skirt_facing(skeleton, chain)
        weight = max(0.0, 2.0 * share["front"] - 1.0) * amount
        if weight <= 0.0:
            continue
        for bone in chain[1:]:
            world, heads = forward_kinematics(skeleton, pose)
            along = tail_position(skeleton, world, heads, bone) - heads[bone]
            turn = Quaternion().slerp(along.rotation_difference(-UP), weight)
            set_world_rotation(skeleton, pose, bone, turn @ world[bone])


# Leg capsules the skirt keeps clear of: radius at the hip, at the knee, and how far down the shin the knee cap
# reaches (fraction of the shin). The margin covers the pleat depth and the fabric thickness.
THIGH_RADII = (0.064, 0.044)
THIGH_START = 0.2
# A bent knee juts out (kneecap and the skin bulge over the joint) past the straight-leg thigh radius.
KNEE_RADIUS = 0.062
SHIN_REACH = 0.25
DEFAULT_LEG_RADII = (THIGH_RADII[0], THIGH_RADII[1], KNEE_RADIUS)
SKIRT_LEG_MARGIN = 0.012
# Each chain carries the fabric halfway to its neighbours, so it checks that whole sector.
SKIRT_SECTOR_SHARES = (0.0, 0.25, 0.5)
MAX_CLEARANCE_DEGREES = 80.0
SKIRT_SMOOTHING_PASSES = 3


def _leg_capsules(skeleton: Skeleton, world: dict, heads: dict, leg_radii: tuple) -> list:
    thigh_top, thigh_bottom, knee_radius = leg_radii
    capsules = []
    for side in SIDES:
        hip = heads[f"thigh{side}"]
        knee = heads[f"shin{side}"]
        ankle = heads[f"foot{side}"]
        # The top of the thigh sits inside the pelvis, under the waistband the chains pivot on.
        capsules.append((hip.lerp(knee, THIGH_START), knee, thigh_top, thigh_bottom))
        capsules.append((knee, knee, knee_radius, knee_radius))
        capsules.append((knee, knee.lerp(ankle, SHIN_REACH), thigh_bottom, thigh_bottom * 0.9))
    return capsules


def _capsule_clearance(point: Vector, capsule: tuple) -> float:
    start, end, start_radius, end_radius = capsule
    segment = end - start
    fraction = max(0.0, min(1.0, (point - start).dot(segment) / max(segment.length_squared, 1e-12)))
    return (point - (start + segment * fraction)).length - lerp(start_radius, end_radius, fraction)


def _chain_points(skeleton: Skeleton, world: dict, heads: dict, chain: list) -> list:
    """Joints and segment midpoints of a chain, skipping the pinned waistband."""
    joints = [heads[bone] for bone in chain[1:]] + [tail_position(skeleton, world, heads, chain[-1])]
    points = [joints[0]]
    for previous, point in zip(joints, joints[1:]):
        points += [previous.lerp(point, 0.5), point]
    return points


def _sector_pairs(skeleton: Skeleton, world: dict, heads: dict, chains: list, index: int,
                  shares: tuple = SKIRT_SECTOR_SHARES) -> list:
    """(own point, neighbour point, share of the neighbour) samples across a chain's sector.

    Vertices between two chains are skinned to both by azimuth, so a point halfway to a neighbour moves half as
    far as the chain does; the samples model exactly that.
    """
    own = _chain_points(skeleton, world, heads, chains[index])
    pairs = []
    for neighbour_index in ((index - 1) % len(chains), (index + 1) % len(chains)):
        neighbour = _chain_points(skeleton, world, heads, chains[neighbour_index])
        for share in shares:
            pairs += [(point, other, share) for point, other in zip(own, neighbour)]
    return pairs


def _sector_clearance(pairs: list, pivot: Vector, turn: Quaternion, capsules: list, allowances: list | None = None) -> float:
    """Smallest clearance of the sector's samples from the legs, each less the clearance it may keep (`allowances`)."""
    worst = math.inf
    for sample_index, (point, other, share) in enumerate(pairs):
        moved = pivot + turn @ (point - pivot)
        sample = moved.lerp(other, share)
        allowance = allowances[sample_index] if allowances is not None else 0.0
        for capsule in capsules:
            worst = min(worst, _capsule_clearance(sample, capsule) - allowance)
    return worst


def _rest_allowances(skeleton: Skeleton, chains: list, leg_radii: tuple, per_sample: bool) -> dict:
    """Per chain, the clearance each sector sample must keep: the margin, or less where it hangs closer at rest.

    `per_sample` measures that rest clearance sample by sample; otherwise every sample of a chain gets the chain's
    smallest one.
    """
    key = ("rest_allowances", tuple(chain[0] for chain in chains), leg_radii, per_sample)
    if key not in skeleton._chains:
        world, heads = forward_kinematics(skeleton, Pose())
        capsules = _leg_capsules(skeleton, world, heads, leg_radii)
        allowances = {}
        for index, chain in enumerate(chains):
            pairs = _sector_pairs(skeleton, world, heads, chains, index)
            sample_allowances = [min(SKIRT_LEG_MARGIN, _sector_clearance([pair], heads[chain[0]], Quaternion(), capsules))
                                 for pair in pairs]
            allowances[chain[0]] = sample_allowances if per_sample else [min(sample_allowances)] * len(pairs)
        skeleton._chains[key] = allowances
    return skeleton._chains[key]


def _drape_segments(skeleton: Skeleton, pose: Pose, chains: list, index: int, axis: Vector, lifted: float,
                    allowances: list, capsules: list) -> None:
    """After the root lifted a chain by `lifted` degrees, let each lower segment fall back toward hanging as far
    as the legs allow, so the fabric drapes over a thigh and down its side instead of sticking out like a shelf."""
    chain = chains[index]
    remaining = lifted
    for segment_index in range(1, len(chain)):
        world, heads = forward_kinematics(skeleton, pose)
        bone = chain[segment_index]
        pivot = heads[bone]
        kept = [(pair, allowance) for pair, allowance in zip(_sector_pairs(skeleton, world, heads, chains, index), allowances)
                if (pair[0] - heads[chain[0]]).length >= (pivot - heads[chain[0]]).length - 1e-6]
        pairs = [pair for pair, _ in kept]
        kept_allowances = [allowance for _, allowance in kept]

        def clearance(angle: float) -> float:
            return _sector_clearance(pairs, pivot, Quaternion(axis, math.radians(-angle)), capsules, kept_allowances)

        if remaining <= 0.0 or clearance(0.0) < 0.0:
            break
        low, high = 0.0, remaining
        if clearance(high) >= 0.0:
            low = high
        else:
            for _ in range(12):
                middle = 0.5 * (low + high)
                if clearance(middle) >= 0.0:
                    low = middle
                else:
                    high = middle
        if low <= 0.0:
            break
        set_world_rotation(skeleton, pose, bone, Quaternion(axis, math.radians(-low)) @ world[bone])
        remaining -= low


def _share_allowances(allowances: list, shares: tuple) -> list:
    """The allowances of the samples whose neighbour share is in `shares` (the list follows `_sector_pairs`)."""
    per_share = len(allowances) // (2 * len(SKIRT_SECTOR_SHARES))
    return [allowance for index, allowance in enumerate(allowances)
            if SKIRT_SECTOR_SHARES[index // per_share % len(SKIRT_SECTOR_SHARES)] in shares]


def clear_legs(skeleton: Skeleton, pose: Pose, chains: list, leg_radii: tuple = DEFAULT_LEG_RADII,
               sample_allowances: bool = False, own_chains_first: bool = False) -> None:
    """Swing each skirt chain outward just far enough that its whole sector stays outside the legs.

    This bakes into the keys what the spring-bone colliders do at runtime: a striding or raised thigh lifts the
    panels in front of it instead of pushing through them. Chains that already clear are left untouched. A sector
    keeps SKIRT_LEG_MARGIN, or the smaller clearance it has hanging at rest: per sample with `sample_allowances`,
    else the chain's smallest. `own_chains_first` first lifts every chain clear on its own, so a chain's sector is
    then measured against neighbours already off the legs (seated, the panels over each thigh would otherwise lever
    the centre panel up toward the chest).
    """
    rest_allowances = _rest_allowances(skeleton, chains, leg_radii, sample_allowances)
    order = list(range(len(chains)))
    if own_chains_first:
        lifts = _lift_chains(skeleton, pose, chains, leg_radii, rest_allowances, (0.0,), order)
        # Chains that hang free settle first, so the ones lying on a thigh see their neighbours already in place.
        order.sort(key=lambda index: lifts[index])
    _lift_chains(skeleton, pose, chains, leg_radii, rest_allowances, SKIRT_SECTOR_SHARES, order)


def _lift_chains(skeleton: Skeleton, pose: Pose, chains: list, leg_radii: tuple, rest_allowances: dict,
                 shares: tuple, order: list) -> dict:
    """One clearing pass over the chains in `order`, measuring the sector samples at `shares`; the full pass also
    drapes. Returns each chain's lift in degrees."""
    world, heads = forward_kinematics(skeleton, pose)
    capsules = _leg_capsules(skeleton, world, heads, leg_radii)
    up = world["hips"] @ UP
    center = heads["hips"]
    lifts = {index: 0.0 for index in order}
    for index in order:
        chain = chains[index]
        pivot = heads[chain[0]]
        pairs = _sector_pairs(skeleton, world, heads, chains, index, shares)
        allowances = _share_allowances(rest_allowances[chain[0]], shares)
        hem = tail_position(skeleton, world, heads, chain[-1]) - center
        outward = hem - up * hem.dot(up)
        if outward.length < 1e-6:
            continue
        axis = outward.normalized().cross(up)

        def worst(angle: float) -> float:
            return _sector_clearance(pairs, pivot, Quaternion(axis, math.radians(angle)), capsules, allowances)

        if worst(0.0) >= 0.0:
            continue
        low, high = 0.0, MAX_CLEARANCE_DEGREES
        if worst(high) < 0.0:
            low = high
        else:
            for _ in range(14):
                middle = 0.5 * (low + high)
                if worst(middle) >= 0.0:
                    high = middle
                else:
                    low = middle
            low = high
        lifts[index] = low
        set_world_rotation(skeleton, pose, chain[0], Quaternion(axis, math.radians(low)) @ world[chain[0]])
        world, heads = forward_kinematics(skeleton, pose)
        if shares == SKIRT_SECTOR_SHARES:
            _drape_segments(skeleton, pose, chains, index, axis, low, allowances, capsules)
            world, heads = forward_kinematics(skeleton, pose)
    return lifts


def smooth_rotations(poses: list, bones: list, loop: bool, passes: int = SKIRT_SMOOTHING_PASSES) -> None:
    """Low-pass the rotation keys of `bones` over time ([1, 2, 1] per pass, wrapping for loops).

    The skirt follow and the leg clearance switch on and off with the legs, which leaves velocity kinks that
    read as pops (and kick the spring bones at runtime); a light temporal blur removes them.
    """
    count = len(poses) - 1 if loop else len(poses)
    for _ in range(passes):
        for bone in bones:
            current = [poses[frame].rotation(bone) for frame in range(count)]
            smoothed = []
            for frame in range(count):
                if loop:
                    before, after = current[frame - 1], current[(frame + 1) % count]
                else:
                    before, after = current[max(0, frame - 1)], current[min(count - 1, frame + 1)]
                middle = current[frame]
                total = Quaternion((0.0, 0.0, 0.0, 0.0))
                for weight, rotation in ((1.0, before), (2.0, middle), (1.0, after)):
                    aligned = rotation if rotation.dot(middle) >= 0.0 else -rotation
                    total = Quaternion([total[index] + weight * aligned[index] for index in range(4)])
                smoothed.append(total.normalized())
            for frame in range(count):
                poses[frame].rotations[bone] = smoothed[frame]
    if loop:
        for bone in bones:
            poses[-1].rotations[bone] = poses[0].rotation(bone).copy()


# ---------------------------------------------------------------------------------------------------
# Keeping hanging accessories (the braid and its bow) on top of the skirt

# Air kept between the plait or bow and the skirt's outer pleat faces.
SKIRT_RESTING_MARGIN = 0.007
MAX_LIFT_DEGREES = 80.0
LIFT_SCAN_DEGREES = 2.5
# How far out a ray from a sample looks for fabric that still covers it.
SKIRT_RESTING_DEPTH = 0.12
LIFT_SAMPLE_COUNT = 160
# Only the skirt within this azimuth of the hanging chain can reach it.
SKIRT_REGION_DEGREES = 80.0
# The per-frame lift is widened by this many frames on each side, then blurred with the same passes as the skirt,
# so the blurred lift never drops below what any frame needs.
LIFT_WIDENING_FRAMES = SKIRT_SMOOTHING_PASSES


def _dominant_group(mesh_object, vertex) -> str | None:
    dominant = max(vertex.groups, key=lambda element: element.weight, default=None)
    return mesh_object.vertex_groups[dominant.group].name if dominant is not None else None


def _farthest_points(points: numpy.ndarray, count: int, first: int) -> list:
    chosen = [first]
    distances = numpy.linalg.norm(points - points[first], axis=1)
    while len(chosen) < min(count, len(points)):
        index = int(numpy.argmax(distances))
        chosen.append(index)
        distances = numpy.minimum(distances, numpy.linalg.norm(points - points[index], axis=1))
    return chosen


def hang(skeleton: Skeleton, pose: Pose, bones: tuple) -> None:
    """Let a free-hanging chain keep its rest direction in the world (gravity) however the body above it turns."""
    for bone in bones:
        set_world_rotation(skeleton, pose, bone, Quaternion())


class SkirtResting:
    """Bakes a hanging chain (the braid and its bow) so it rests on the posed skirt instead of sinking into it.

    The skirt is the real skinned mesh near the chain, posed by linear blend skinning from the composed bone
    poses; the chain is sampled from its own meshes. Where a sample would sink into the skirt, the lift bones
    swing the lower chain out along the skirt's outward normal by the smallest angle that clears it.
    """

    def __init__(self, armature, skeleton: Skeleton, skirt, chain_meshes: list, sample_bones: tuple, lift_bones: tuple):
        self.skeleton = skeleton
        self.lift_bones = lift_bones
        to_armature = armature.matrix_world.inverted()
        samples, sample_bones_of = [], []
        for mesh_object in chain_meshes:
            matrix = to_armature @ mesh_object.matrix_world
            for vertex in mesh_object.data.vertices:
                bone = _dominant_group(mesh_object, vertex)
                if bone in sample_bones:
                    samples.append(tuple(matrix @ vertex.co))
                    sample_bones_of.append(bone)
        points = numpy.array(samples)
        lowest = int(numpy.argmin(points[:, 2]))
        chosen = _farthest_points(points, LIFT_SAMPLE_COUNT, lowest)
        self.sample_groups = {}
        for index in chosen:
            self.sample_groups.setdefault(sample_bones_of[index], []).append(points[index])
        self.sample_groups = {bone: numpy.array(group) for bone, group in sorted(self.sample_groups.items())}
        self._prepare_skirt(to_armature @ skirt.matrix_world, skirt, points.mean(axis=0))

    def _prepare_skirt(self, matrix: Matrix, skirt, chain_center: numpy.ndarray) -> None:
        center = self.skeleton.heads["hips"]
        chain_azimuth = math.atan2(chain_center[1] - center.y, chain_center[0] - center.x)
        rest = [matrix @ vertex.co for vertex in skirt.data.vertices]

        def in_region(point: Vector) -> bool:
            azimuth = math.atan2(point.y - center.y, point.x - center.x)
            offset = (azimuth - chain_azimuth + math.pi) % (2.0 * math.pi) - math.pi
            return abs(math.degrees(offset)) <= SKIRT_REGION_DEGREES

        normal_matrix = matrix.to_3x3().inverted().transposed()
        faces = []
        for polygon in skirt.data.polygons:
            radial = Vector((polygon.center.x - center.x, polygon.center.y - center.y, 0.0))
            # Only the outer shell: the solidified inner shell faces the body.
            if (normal_matrix @ polygon.normal).dot(radial) <= 0.0:
                continue
            if all(in_region(rest[index]) for index in polygon.vertices):
                faces.append(tuple(polygon.vertices))
        used = sorted({index for face in faces for index in face})
        remap = {index: position for position, index in enumerate(used)}
        self.skirt_faces = [tuple(remap[index] for index in face) for face in faces]
        self.skirt_rest = numpy.array([tuple(rest[index]) for index in used])
        bones = sorted({skirt.vertex_groups[element.group].name for index in used
                        for element in skirt.data.vertices[index].groups if element.weight > 0.0})
        self.skirt_bones = [bone for bone in bones if bone in self.skeleton.heads]
        weights = numpy.zeros((len(used), len(self.skirt_bones)))
        columns = {bone: column for column, bone in enumerate(self.skirt_bones)}
        for row, index in enumerate(used):
            for element in skirt.data.vertices[index].groups:
                name = skirt.vertex_groups[element.group].name
                if name in columns:
                    weights[row, columns[name]] = element.weight
        self.skirt_weights = weights / numpy.maximum(weights.sum(axis=1, keepdims=True), 1e-9)

    def _skirt_tree(self, world: dict, heads: dict) -> BVHTree:
        posed = numpy.zeros_like(self.skirt_rest)
        for column, bone in enumerate(self.skirt_bones):
            rotation = numpy.array(world[bone].to_matrix())
            moved = (self.skirt_rest - numpy.array(self.skeleton.heads[bone])) @ rotation.T + numpy.array(heads[bone])
            posed += self.skirt_weights[:, column:column + 1] * moved
        return BVHTree.FromPolygons([Vector(point) for point in posed], self.skirt_faces)

    def _samples(self, world: dict, heads: dict) -> list:
        positions = []
        for bone, points in self.sample_groups.items():
            rotation = numpy.array(world[bone].to_matrix())
            moved = (points - numpy.array(self.skeleton.heads[bone])) @ rotation.T + numpy.array(heads[bone])
            positions += [Vector(point) for point in moved]
        return positions

    def _clearances(self, tree: BVHTree, pose: Pose) -> list:
        """(signed distance outside the skirt, outward normal) of every sample.

        A sample is inside when the skirt still lies further out along the ray pointing away from the hips' axis;
        its depth is how far that ray travels to the fabric.
        """
        world, heads = forward_kinematics(self.skeleton, pose)
        up = world["hips"] @ UP
        center = heads["hips"]
        result = []
        for point in self._samples(world, heads):
            radial = point - center
            radial -= up * radial.dot(up)
            if radial.length > 1e-6:
                location, normal, _, distance = tree.ray_cast(point, radial.normalized(), SKIRT_RESTING_DEPTH)
                if location is not None:
                    result.append((-distance, normal if normal.dot(radial) > 0.0 else -normal))
                    continue
            location, normal, _, distance = tree.find_nearest(point)
            if location is not None:
                result.append((distance, normal if normal.dot(radial) > 0.0 else -normal))
        return result

    def _lifted(self, pose: Pose, axis: Vector, angle: float) -> Pose:
        lifted = pose.copy()
        step = math.radians(angle) / len(self.lift_bones)
        for bone in self.lift_bones:
            world, _ = forward_kinematics(self.skeleton, lifted)
            set_world_rotation(self.skeleton, lifted, bone, Quaternion(axis, step) @ world[bone])
        return lifted

    def _required_lift(self, pose: Pose) -> tuple[float, Vector | None]:
        world, heads = forward_kinematics(self.skeleton, pose)
        tree = self._skirt_tree(world, heads)
        clearances = self._clearances(tree, pose)
        if not clearances:
            return 0.0, None
        pivot = heads[self.lift_bones[0]]
        samples = self._samples(world, heads)
        hanging = sum(samples, Vector()) / len(samples) - pivot
        # Swing away from the hips' axis: out over a standing skirt, forward along the lap when seated.
        up = world["hips"] @ UP
        outward = hanging + pivot - heads["hips"]
        outward -= up * outward.dot(up)
        axis = hanging.cross(outward)
        if axis.length < 1e-6:
            return 0.0, None
        axis.normalize()

        def worst(angle: float) -> float:
            return min(distance for distance, _ in self._clearances(tree, self._lifted(pose, axis, angle)))

        if worst(0.0) >= SKIRT_RESTING_MARGIN:
            return 0.0, axis
        # Scan up first (a swing can clear one part of the skirt and meet another), then refine the first clear step.
        low = 0.0
        for step in range(1, int(MAX_LIFT_DEGREES / LIFT_SCAN_DEGREES) + 1):
            high = step * LIFT_SCAN_DEGREES
            if worst(high) >= SKIRT_RESTING_MARGIN:
                break
            low = high
        else:
            return MAX_LIFT_DEGREES, axis
        for _ in range(8):
            middle = 0.5 * (low + high)
            if worst(middle) >= SKIRT_RESTING_MARGIN:
                high = middle
            else:
                low = middle
        return high, axis

    def apply(self, poses: list, loop: bool) -> float:
        """Lift the chain in every pose (after the skirt keys are final); returns the largest lift in degrees."""
        count = len(poses) - 1 if loop else len(poses)
        needs = [self._required_lift(poses[frame]) for frame in range(count)]
        lifts = [angle for angle, _ in needs]
        if max(lifts) <= 0.0:
            return 0.0

        def neighbour(frame: int, offset: int) -> int:
            return (frame + offset) % count if loop else max(0, min(count - 1, frame + offset))

        widened = [max(lifts[neighbour(frame, offset)] for offset in range(-LIFT_WIDENING_FRAMES, LIFT_WIDENING_FRAMES + 1))
                   for frame in range(count)]
        for _ in range(SKIRT_SMOOTHING_PASSES):
            widened = [(widened[neighbour(frame, -1)] + 2.0 * widened[frame] + widened[neighbour(frame, 1)]) / 4.0
                       for frame in range(count)]
        for frame in range(count):
            angle, axis = widened[frame], needs[frame][1]
            if angle > 0.0 and axis is not None:
                lifted = self._lifted(poses[frame], axis, angle)
                for bone in self.lift_bones:
                    poses[frame].rotations[bone] = lifted.rotation(bone)
        if loop:
            for bone in self.lift_bones:
                poses[-1].rotations[bone] = poses[0].rotation(bone).copy()
        return max(widened)


# ---------------------------------------------------------------------------------------------------
# Gait

@dataclass
class GaitParams:
    speed: float = 1.3
    frame_count: int = 32
    duty: float = 0.57
    heel_strike_ahead: float = 0.24
    feet_x: float = 0.058
    toe_out_degrees: float = 4.0
    heel_strike_degrees: float = 16.0
    toe_off_degrees: float = 58.0
    swing_lift: float = 0.03
    hips_height: float = -0.012
    hips_bob: float = 0.013
    hips_sway: float = 0.016
    pelvis_yaw_degrees: float = 5.0
    pelvis_roll_degrees: float = 3.5
    reach: float = 0.992


class WalkCycle:
    """In-place walk: the ground slides back under planted feet at exactly `speed`.

    Each foot is planted for `duty` of the cycle (heel strike, flat foot, roll over the ball) and swings
    forward on a C1 Hermite path for the rest. The hips bob, sway and rotate, and drop wherever a leg
    would otherwise have to over-stretch, so no planted foot ever slides.
    """

    def __init__(self, skeleton: Skeleton, params: GaitParams):
        self.skeleton = skeleton
        self.params = params
        self.stride = params.speed * params.frame_count / FPS
        self.geometry = {side: FootGeometry(skeleton, side) for side in SIDES}
        params_pitch = [
            (0.0, -params.heel_strike_degrees),
            (0.11, 0.0),
            (0.30, 0.0),
            (params.duty, params.toe_off_degrees),
            (params.duty + 0.12, 22.0),
            (0.86, -4.0),
            (1.0, -params.heel_strike_degrees),
        ]
        self.pitch_curve = Curve(params_pitch, period=1.0)
        heel_offset = self.geometry[".L"].heel.y - self.geometry[".L"].ankle.y
        # Flat-foot ankle y at heel strike, so that the heel lands `heel_strike_ahead` in front of the hip.
        self.strike_y = -params.heel_strike_ahead - heel_offset
        self._hips_heights = self._solve_hips_heights()

    def phase(self, frame: float) -> float:
        return (frame / self.params.frame_count) % 1.0

    def _stance_placement(self, side: str, phase: float) -> FootPlacement:
        params = self.params
        flat_y = self.strike_y + self.stride * phase
        pitch = self.pitch_curve.scalar(phase)
        return FootPlacement(side_sign(side) * params.feet_x, flat_y, side_sign(side) * params.toe_out_degrees, pitch)

    def _stance_ankle(self, side: str, phase: float) -> Vector:
        ankle, _ = self.geometry[side].placement_transform(self._stance_placement(side, phase))
        return ankle

    def foot(self, side: str, frame: float) -> tuple[Vector, Quaternion, float]:
        """Ankle target, foot world rotation and toe bend (degrees) for one foot."""
        params = self.params
        phase = (self.phase(frame) + (0.0 if side == ".L" else 0.5)) % 1.0
        if phase < params.duty:
            placement = self._stance_placement(side, phase)
            ankle, rotation = self.geometry[side].placement_transform(placement)
            toe_bend = max(0.0, placement.pitch_degrees)
            return ankle, rotation, toe_bend
        swing = (phase - params.duty) / (1.0 - params.duty)
        epsilon = 1e-3
        start = self._stance_ankle(side, params.duty)
        start_velocity = (start - self._stance_ankle(side, params.duty - epsilon)) / epsilon
        end = self._stance_ankle(side, 0.0)
        end_velocity = (self._stance_ankle(side, epsilon) - end) / epsilon
        span = 1.0 - params.duty
        ankle = hermite(start, start_velocity * span, end, end_velocity * span, swing)
        ankle.z += params.swing_lift * math.sin(math.pi * swing) ** 2
        pitch = self.pitch_curve.scalar(phase)
        yaw = Quaternion(UP, math.radians(side_sign(side) * params.toe_out_degrees))
        rotation = yaw @ Quaternion(Vector((1.0, 0.0, 0.0)), math.radians(pitch))
        toe_bend = params.toe_off_degrees * (1.0 - smoothstep(0.0, 0.45, swing))
        return ankle, rotation, toe_bend

    def _hips_motion(self, phase: float, height: float) -> tuple[Vector, Quaternion]:
        params = self.params
        sway = params.hips_sway * math.sin(2.0 * math.pi * (phase - 0.04))
        offset = Vector((sway, 0.0, height))
        yaw = -params.pelvis_yaw_degrees * math.cos(2.0 * math.pi * phase)
        roll = -params.pelvis_roll_degrees * math.sin(2.0 * math.pi * (phase - 0.05))
        return offset, degrees(y=roll, z=yaw)

    def _desired_height(self, phase: float) -> float:
        params = self.params
        return params.hips_height - params.hips_bob * 0.5 * (1.0 + math.cos(4.0 * math.pi * phase))

    def _solve_hips_heights(self) -> list:
        """Per-frame hips height: the desired bob, lowered where a leg needs it, then smoothed."""
        count = self.params.frame_count
        desired = []
        limits = []
        for frame in range(count):
            phase = frame / count
            pose = Pose()
            offset, rotation = self._hips_motion(phase, 0.0)
            pose.offsets["hips"] = offset
            pose.rotations["hips"] = rotation
            limit = min(hip_joint_height_limit(self.skeleton, pose, side, self.foot(side, frame)[0], self.params.reach)
                        for side in SIDES)
            limits.append(limit)
            desired.append(self._desired_height(phase))
        heights = [min(value, limit) for value, limit in zip(desired, limits)]
        for _ in range(12):
            smoothed = [(heights[index - 1] + 2.0 * heights[index] + heights[(index + 1) % count]) / 4.0
                        for index in range(count)]
            heights = [min(value, limit) for value, limit in zip(smoothed, limits)]
        return heights

    def hips_height(self, frame: float) -> float:
        count = self.params.frame_count
        position = frame % count
        index = int(math.floor(position))
        fraction = position - index
        return lerp(self._hips_heights[index % count], self._hips_heights[(index + 1) % count], fraction)

    def apply_lower_body(self, pose: Pose, frame: float) -> dict:
        """Hips and legs for a frame; returns the reach fraction per leg."""
        phase = self.phase(frame)
        offset, rotation = self._hips_motion(phase, self.hips_height(frame))
        pose.offsets["hips"] = offset
        pose.rotations["hips"] = rotation @ pose.rotation("hips")
        reaches = {}
        for side in SIDES:
            ankle, foot_rotation, toe_bend = self.foot(side, frame)
            yaw = Quaternion(UP, math.radians(side_sign(side) * self.params.toe_out_degrees))
            pole = yaw @ Vector((side_sign(side) * KNEE_SPLAY, -1.0, 0.0))
            reaches[side] = solve_two_bone(self.skeleton, pose, f"thigh{side}", f"shin{side}", ankle, pole, LEG_REST_POLE)
            set_world_rotation(self.skeleton, pose, f"foot{side}", foot_rotation)
            if toe_bend > 0.0 and self._in_stance(side, frame):
                set_world_rotation(self.skeleton, pose, f"toe{side}", yaw)
            else:
                pose.rotations[f"toe{side}"] = degrees(x=-toe_bend)
        return reaches

    def _in_stance(self, side: str, frame: float) -> bool:
        phase = (self.phase(frame) + (0.0 if side == ".L" else 0.5)) % 1.0
        return phase < self.params.duty


def walk_cycle(skeleton: Skeleton, params: GaitParams, upper_body: Callable[[Pose, float, float], None]) -> list:
    """Poses for frames 0..frame_count of an in-place walk; `upper_body(pose, frame, phase)` adds the rest."""
    cycle = WalkCycle(skeleton, params)
    poses = []
    for frame in range(params.frame_count):
        pose = Pose()
        cycle.apply_lower_body(pose, frame)
        upper_body(pose, frame, cycle.phase(frame))
        poses.append(pose)
    poses.append(poses[0].copy())
    return poses


def sit_pose(skeleton: Skeleton, pose: Pose, seat_height: float, seat_clearance: float,
             feet: dict, pelvis_tilt_degrees: float = -8.0) -> None:
    """Seat the hips so the buttocks rest at `seat_height` with the feet flat at `feet` placements.

    `seat_clearance` is the height of the hip joints above the seat contact. The hips slide back until
    the shins stand upright over the planted ankles.
    """
    hip_height = seat_height + seat_clearance
    rest_hip = skeleton.heads["thigh.L"]
    thigh = skeleton.length("thigh.L")
    shin = skeleton.length("shin.L")
    ankle_z = skeleton.heads["foot.L"].z
    knee_z = ankle_z + shin * 0.985
    horizontal = math.sqrt(max(0.0, thigh * thigh - (hip_height - knee_z) ** 2))
    feet_y = sum(placement.y for placement in feet.values()) / len(feet)
    pose.offsets["hips"] = Vector((0.0, feet_y + horizontal - rest_hip.y, hip_height - rest_hip.z))
    pose.rotations["hips"] = degrees(x=pelvis_tilt_degrees) @ pose.rotation("hips")


# ---------------------------------------------------------------------------------------------------
# Writing actions

def poses_to_keyframes(poses: list, bones: list) -> dict:
    """Frame-by-frame keys for the given bones; bones moved or scaled in any pose also key those."""
    moved = {bone for pose in poses for bone in pose.offsets}
    scaled = {bone for pose in poses for bone in pose.scales}
    keyframes: dict = {bone: [] for bone in bones}
    for frame, pose in enumerate(poses):
        for bone in bones:
            values = {"rotation": pose.rotation(bone)}
            if bone in moved:
                values["location"] = pose.offset(bone)
            if bone in scaled:
                values["scale"] = pose.scales.get(bone, Vector((1.0, 1.0, 1.0)))
            keyframes[bone].append((frame, values))
    return keyframes


def _enum_value(struct, property_name: str, wanted: str) -> str:
    identifiers = [item.identifier for item in struct.bl_rna.properties[property_name].enum_items]
    if wanted not in identifiers:
        raise ValueError(f"{property_name} has no {wanted}; available: {identifiers}")
    return wanted


def make_action(armature, name: str, frame_count: int, keyframes: dict, loop: bool) -> bpy.types.Action:
    """Create an action from rest-axis keys and give it its own NLA track.

    `keyframes` maps bone -> [(frame, {"rotation": Euler | Quaternion, "location": Vector, "scale": Vector})]:
    rotations are rest-axis deltas, locations armature-space head offsets, scales bone-local (optional). Looping actions must key frame 0 and
    `frame_count` identically and get a Cycles modifier, so Blender scrubs across the seam as Godot plays it.
    """
    skeleton_rest = {bone.name: bone.matrix_local.to_quaternion() for bone in armature.data.bones}
    existing = bpy.data.actions.get(name)
    if existing is not None:
        bpy.data.actions.remove(existing)
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    slot = action.slots.new(id_type=_enum_value(bpy.types.ActionSlot, "target_id_type", "OBJECT"), name=armature.name)
    channelbag = anim_utils.action_ensure_channelbag_for_slot(action, slot)
    linear = _enum_value(bpy.types.Keyframe, "interpolation", "LINEAR")
    cycles = _enum_value(bpy.types.FModifier, "type", "CYCLES")

    for bone, keys in keyframes.items():
        rest = skeleton_rest[bone]
        rest_inverse = rest.inverted()
        rotations = []
        locations = []
        scales = []
        for frame, values in keys:
            rotation = values["rotation"]
            if isinstance(rotation, Euler):
                rotation = rotation.to_quaternion()
            rotations.append((frame, canonical(rest_inverse @ rotation @ rest)))
            if "location" in values:
                locations.append((frame, rest_inverse @ Vector(values["location"])))
            if "scale" in values:
                scales.append((frame, Vector(values["scale"])))
        channels = [("rotation_quaternion", rotations, 4)]
        if locations:
            channels.append(("location", locations, 3))
        if scales:
            channels.append(("scale", scales, 3))
        for property_name, samples, size in channels:
            for index in range(size):
                fcurve = channelbag.fcurves.new(f'pose.bones["{bone}"].{property_name}', index=index, group_name=bone)
                fcurve.keyframe_points.add(len(samples))
                coordinates = []
                for frame, value in samples:
                    coordinates += [float(frame), float(value[index])]
                fcurve.keyframe_points.foreach_set("co", coordinates)
                fcurve.keyframe_points.foreach_set("interpolation", [_interpolation_index(linear)] * len(samples))
                if loop:
                    fcurve.modifiers.new(cycles)
                fcurve.update()

    action.use_frame_range = True
    action.frame_start = 0
    action.frame_end = frame_count
    action.use_cyclic = loop

    animation_data = armature.animation_data_create()
    for track in list(animation_data.nla_tracks):
        if track.name == name:
            animation_data.nla_tracks.remove(track)
    track = animation_data.nla_tracks.new()
    track.name = name
    strip = track.strips.new(name, 0, action)
    if hasattr(strip, "action_slot"):
        strip.action_slot = slot
    track.mute = True
    return action


def _interpolation_index(identifier: str) -> int:
    identifiers = [item.identifier for item in bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items]
    return identifiers.index(identifier)


def build_clip(armature, skeleton: Skeleton, name: str, frame_count: int, loop: bool, poses: list,
               bones: list | None = None) -> bpy.types.Action:
    if len(poses) != frame_count + 1:
        raise ValueError(f"{name}: expected {frame_count + 1} poses, got {len(poses)}")
    if loop:
        poses = poses[:-1] + [poses[0].copy()]
    keyed_bones = bones or [name for name in skeleton.names if skeleton.parents[name] is not None]
    return make_action(armature, name, frame_count, poses_to_keyframes(poses, keyed_bones), loop)
