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
from bpy_extras import anim_utils
from mathutils import Euler, Matrix, Quaternion, Vector

FPS = 30
SIDES = (".L", ".R")
UP = Vector((0.0, 0.0, 1.0))
FORWARD = Vector((0.0, -1.0, 0.0))
# Joint bend directions at rest: knees point forward, elbows point back.
LEG_REST_POLE = Vector((0.0, -1.0, 0.0))
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

    def length(self, name: str) -> float:
        return (self.tails[name] - self.heads[name]).length

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
              toe_bend_degrees: float = 0.0) -> float:
    """Solve thigh and shin so the foot sits at `placement`; the toe stays flat on the ground when asked."""
    ankle, foot_world = geometry.placement_transform(placement)
    yaw = Quaternion(UP, math.radians(placement.yaw_degrees))
    pole = yaw @ Vector((side_sign(side) * 0.12, -1.0, 0.0))
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


def curl_fingers(skeleton: Skeleton, pose: Pose, side: str, fingers_degrees: float, thumb_degrees: float) -> None:
    palm = palm_normal(skeleton, side)
    bend(skeleton, pose, f"fingers{side}", fingers_degrees, palm)
    bend(skeleton, pose, f"thumb{side}", thumb_degrees, palm + skeleton.direction(f"hand{side}") * 0.5)


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


def follow_skirt(skeleton: Skeleton, pose: Pose, sway_degrees: float = 0.0, seated: float | None = None) -> None:
    """Swing the skirt bones with the thighs so the hem rides over the legs instead of through them.

    Front and back follow the forward/backward thigh swing, the sides follow the side sway (degrees about
    the forward axis, positive swings the hem toward +X) and the thigh spread. `seated` (0..1) drapes the
    skirt over the lap; by default it is derived from the thigh lift.
    """
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
    pose.rotations["skirt_front_01"] = degrees(x=-front * (1.0 - 0.15 * seated), y=-sway_degrees)
    pose.rotations["skirt_front_02"] = degrees(x=(droop - front * 0.18) * (1.0 - seated) + 24.0 * seated)
    # Seated, the back panel angles down past the buttocks and then lies flat on the seat.
    pose.rotations["skirt_back_01"] = degrees(x=back + 34.0 * seated + hang, y=-sway_degrees)
    pose.rotations["skirt_back_02"] = degrees(x=back * 0.25 + 30.0 * seated)
    # Sat-on fabric bunches up instead of trailing far behind the seat.
    pose.scales["skirt_back_01"] = Vector((1.0, 1.0 - 0.25 * seated, 1.0))
    pose.scales["skirt_back_02"] = Vector((1.0, 1.0 - 0.35 * seated, 1.0))
    for side in SIDES:
        sign = side_sign(side)
        spread = max(0.0, spread_angles[side]) * 0.7
        lift = max(0.0, forward_angles[side]) * 0.3 * (1.0 - seated)
        side_bone = "left" if side == ".L" else "right"
        pose.rotations[f"skirt_{side_bone}_01"] = degrees(x=-lift - 12.0 * seated + side_hang, y=-sign * (spread - 6.0 * seated) - sway_degrees)
        pose.rotations[f"skirt_{side_bone}_02"] = degrees(x=-6.0 * seated, y=-sign * spread * 0.2 - sway_degrees * 0.4)


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
            pole = yaw @ Vector((side_sign(side) * 0.12, -1.0, 0.0))
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
