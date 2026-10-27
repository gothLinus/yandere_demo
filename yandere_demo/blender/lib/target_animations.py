"""The target's animation library: eighteen in-place clips at 30 fps (fifteen activities plus three idles).

Each clip is a function of the frame that fills a `BodySpec`; the shared `character_animation.compose`
turns it into a pose (IK feet, IK or FK arms, skirt follow) and `build_target_actions` keys each frame.
Standing clips start from the target's idle stance and seated clips from his seated stance, so the
0.3 s crossfades in Godot meet matching poses. Feet are IK-planted, so they never slide.
"""

import math
from dataclasses import dataclass, replace

import bpy
from mathutils import Matrix, Quaternion, Vector

from . import animation
from .animation import (
    SIDES, Curve, FootPlacement, GaitParams, Pose, WalkCycle, curl_fingers, forward_kinematics, palm_normal, side_sign,
    tail_position,
)
from .character_animation import (
    ArmSpec, BodySpec, CharacterRig, Stance, add_degrees, compose, lap_pole, palm_on, poses_for, sit_down_curves,
    sit_transition_body, stand_up_curves,
)

# A light, narrow-tracking step with a fuller hip sway; the steeper swing lift lets the toe leave and the heel meet
# the floor without skimming it.
WALK = GaitParams(speed=1.3, frame_count=32, feet_x=0.052, swing_lift=0.036, swing_lift_exponent=0.85,
                  hips_bob=0.015, hips_sway=0.019, pelvis_yaw_degrees=5.5, pelvis_roll_degrees=4.5)

SEATED_KNEE_SPLAY = -0.05
# Standing, his knees point straight ahead, so they stay together all the way down into the seat and back up.
STANDING_KNEE_SPLAY = 0.0
SEATED_FRONT_DROP = 1.0
# Foot placements as (x, y, yaw, heel pitch) offsets from the rest ankles, so they fit any build of legs.
IDLE_FEET = {".L": (-0.006, -0.008, 7.0, 0.0), ".R": (0.006, -0.048, -12.0, 0.0)}
# The cradling hand is this far down the braid (fraction of its length); the stroking hand runs between the next two.
BRAID_CRADLE_FRACTION = 0.54
BRAID_STROKE_FRACTIONS = (0.32, 0.51)
# The braid bones the cradling hand lifts forward off the chest lie between these fractions of its length.
BRAID_HELD_FRACTIONS = (0.2, 0.5)


def rest_relative_feet(rest_ankles: dict, offsets: dict) -> dict:
    return {side: FootPlacement(rest_ankles[side].x + x, rest_ankles[side].y + y, yaw, pitch)
            for side, (x, y, yaw, pitch) in offsets.items()}


def rig_feet(rig: CharacterRig, offsets: dict) -> dict:
    return rest_relative_feet({side: rig.feet[side].ankle for side in SIDES}, offsets)


def target_stance(rest_ankles: dict, mouth: Vector, hanging_bones: tuple, seat_clearance: float, heel_back: float,
                  lap_offset: Vector, leg_radii: tuple, seated_leg_radii: tuple) -> Stance:
    """The target's idle and seated acting; every landmark argument is measured on the model."""
    return Stance(
        idle_feet=rest_relative_feet(rest_ankles, IDLE_FEET),
        idle_hips_offset=Vector((0.011, 0.0, -0.017)),
        idle_hips=(0.0, -2.5, 1.5),
        idle_spine=(1.0, 1.8, -0.8),
        idle_chest=(0.5, 1.6, -0.5),
        idle_neck=(1.0, -0.8, 0.0),
        idle_head=(2.0, -2.5, 0.0),
        idle_arm=ArmSpec(adduct=23.0, swing=5.0, elbow=20.0, hand=(0.0, -2.0, 0.0), fingers=18.0, thumb=10.0),
        seat_height=0.45,
        seat_clearance=seat_clearance,
        heel_back=heel_back,
        lap_offset=lap_offset,
        leg_radii=leg_radii,
        seated_leg_radii=seated_leg_radii,
        skirt_sample_allowances=True,
        # Seated with the short skirt, the knees come together (addendum §3.6).
        seated_knee_splay=SEATED_KNEE_SPLAY,
        standing_knee_splay=STANDING_KNEE_SPLAY,
        seated_front_drop=SEATED_FRONT_DROP,
        mouth=mouth,
        hanging_bones=hanging_bones,
    )


@dataclass
class BraidLayout:
    """The target's braid as the clips use it: its bones root first, and the meshes that carry its hair and bow."""

    bones: tuple
    bow_bones: tuple
    meshes: tuple
    # Bones at skirt height: they swing out so the braid and its bow rest on the skirt instead of sinking into it.
    resting_bones: tuple

    def point(self, fraction: float) -> tuple:
        """(bone, fraction along that bone) at a fraction of the braid's length, counted bone by bone."""
        position = min(max(fraction, 0.0), 1.0) * len(self.bones)
        index = min(int(position), len(self.bones) - 1)
        return self.bones[index], position - index

    def held_bones(self) -> tuple:
        first = int(BRAID_HELD_FRACTIONS[0] * len(self.bones))
        last = int(BRAID_HELD_FRACTIONS[1] * len(self.bones))
        return self.bones[first:last]


# ---------------------------------------------------------------------------------------------------
# Acting helpers

FINGERS = ("index", "middle", "ring", "pinky")


def wave(frame: float, period: float, offset: float = 0.0, cycles: float = 1.0) -> float:
    return math.sin(2.0 * math.pi * (frame / period * cycles - offset))


def finger_fan(base: float, gradient: float, ripple: float = 0.0, phase: float = 0.0, lag: float = 0.05) -> dict:
    """Curls rising from the index to the pinky by `gradient` per finger; `ripple` rolls a wave across them, the index
    first, so a resting hand never reads as a mitten."""
    return {name: base + gradient * index + ripple * math.sin(2.0 * math.pi * (phase - lag * index))
            for index, name in enumerate(FINGERS)}


def graceful_hand(arm: ArmSpec, phase: float = 0.0, ripple: float = 2.0) -> None:
    """The relaxed anime hand: the index nearly straight, each finger after it a little more curled, a slight fan."""
    arm.finger_curls = finger_fan(9.0, 6.0, ripple, phase)
    arm.thumb = 14.0
    arm.splay = 4.0


def acting_idle(rig: CharacterRig, frame: float, period: float) -> BodySpec:
    """The idle stance with a fuller weight shift: the hips lead it, the chest follows and the head trails and
    counter-tilts, so the body settles in a wave instead of swaying as one block."""
    spec = rig.idle_body(frame, period)
    shift = wave(frame, period)
    spec.hips_offset += Vector((0.003 * shift, 0.0, -0.0015 * (0.5 - 0.5 * wave(frame, period, 0.25, 2.0))))
    spec.chest = add_degrees(spec.chest, (0.0, 0.6 * wave(frame, period, 0.08), 0.0))
    spec.head = add_degrees(spec.head, (0.0, -0.9 * wave(frame, period, 0.16), 0.0))
    for side in SIDES:
        graceful_hand(spec.arms[side], frame / period + (0.0 if side == ".L" else 0.4))
    return spec


# ---------------------------------------------------------------------------------------------------
# Props (ruling R9). Each grip is a holding hand's palm frame in the prop's own frame, the frame TargetProps builds the
# prop's meshes in (+Y up its length, +Z out of a book's pages or a phone's screen, a can's or a handle's axis on Y).
# A palm frame is (across, fingers, normal) about the palm skin point; the fingers run from the wrist to the knuckles
# and the normal leaves the palm. The attachment hand's grip gives the prop's placement on that hand bone
# (`prop_placements`), and the clips pose the hands from the prop's frame (`hold`).

PALM_CENTRE_SHARE = 0.6
PALM_SKIN_DEPTH = 0.017
# A wrapping finger lies on the prop: its joints (bone centrelines) sit about half a finger's thickness off the surface.
FINGER_CENTRE_DEPTH = 0.008
FINGER_CURL_STEP = 3.0
FINGER_JOINT_LIMIT = 100.0

BOOK_LEAF_SIZE = Vector((0.14, 0.2, 0.012))
# Each leaf of the open book turns this far toward the reader from the flat spread.
BOOK_OPEN_DEGREES = 12.0
PHONE_SIZE = Vector((0.07, 0.14, 0.009))
CAN_RADIUS = 0.033
CAN_HEIGHT = 0.12
BROOM_HANDLE_RADIUS = 0.012
BROOM_HANDLE_LENGTH = 1.25
BROOM_HEAD_HEIGHT = 0.12
# The left hand grips the handle this far below its top, the right hand this far further down.
BROOM_TOP_GRIP = 0.15
BROOM_GRIP_SPACING = 0.2


def oriented_frame(origin: Vector, fingers: Vector, normal: Vector) -> Matrix:
    """A palm frame: columns (across, fingers, normal) at `origin`; `fingers` is made square to `normal`."""
    normal = Vector(normal).normalized()
    fingers = Vector(fingers)
    fingers = (fingers - normal * fingers.dot(normal)).normalized()
    matrix = Matrix((fingers.cross(normal), fingers, normal)).transposed().to_4x4()
    matrix.translation = origin
    return matrix


def bone_matrix(skeleton, bone: str) -> Matrix:
    matrix = skeleton.rest_rotations[bone].to_matrix().to_4x4()
    matrix.translation = skeleton.heads[bone]
    return matrix


def palm_local(skeleton, side: str) -> Matrix:
    """The palm frame in the hand bone's frame (the same in Blender and Godot)."""
    hand = f"hand{side}"
    head = skeleton.heads[hand]
    knuckles = sum((skeleton.heads[f"{finger}_01{side}"] for finger in FINGERS), Vector()) / len(FINGERS)
    along = (knuckles - head).normalized()
    inward = Vector((-side_sign(side), 0.0, 0.0))
    normal = (inward - along * inward.dot(along)).normalized()
    palm = oriented_frame(head.lerp(knuckles, PALM_CENTRE_SHARE) + normal * PALM_SKIN_DEPTH, along, normal)
    return bone_matrix(skeleton, hand).inverted() @ palm


def book_leaf(sign: float) -> Matrix:
    """A leaf of the open book in the book's frame; sign +1 is the leaf on the reader's right."""
    leaf = Matrix.Rotation(math.radians(-sign * BOOK_OPEN_DEGREES), 4, "Y")
    leaf.translation = leaf.to_3x3() @ Vector((sign * BOOK_LEAF_SIZE.x * 0.5, 0.0, 0.0))
    return leaf


def _book_grip(sign: float) -> Matrix:
    """The palm under the outer half of a leaf, against its back, fingers fanning up and out over the cover."""
    leaf = book_leaf(sign)
    point = leaf @ Vector((sign * 0.035, -0.04, -BOOK_LEAF_SIZE.z * 0.5))
    rotation = leaf.to_3x3()
    return oriented_frame(point, rotation @ Vector((sign * 0.4, 0.92, 0.0)), rotation @ Vector((0.0, 0.0, 1.0)))


BACK_TO_FRONT = Vector((0.0, 0.0, 1.0))
GRIPS = {
    "book": {".R": _book_grip(1.0), ".L": _book_grip(-1.0)},
    "phone": {".R": oriented_frame(Vector((0.0, -0.012, -PHONE_SIZE.z * 0.5)), Vector((-0.3, 0.95, 0.0)), BACK_TO_FRONT)},
    # The can sits toward the finger roots, so the fingers have room to wrap it.
    "can": {".R": oriented_frame(Vector((0.012, 0.004, -math.sqrt(CAN_RADIUS ** 2 - 0.012 ** 2))), Vector((-1.0, 0.0, 0.0)),
                                 BACK_TO_FRONT)},
    "broom": {
        ".L": oriented_frame(Vector((0.0, -BROOM_TOP_GRIP, -BROOM_HANDLE_RADIUS)), Vector((1.0, 0.0, 0.0)), BACK_TO_FRONT),
        ".R": oriented_frame(Vector((0.0, -BROOM_TOP_GRIP - BROOM_GRIP_SPACING, BROOM_HANDLE_RADIUS)),
                             Vector((1.0, 0.0, 0.0)), -BACK_TO_FRONT),
    },
}
# The bone each prop hangs from in Godot (TargetProps.PROP_BONES).
PROP_HANDS = {"book": ".R", "phone": ".R", "can": ".R", "broom": ".L"}


def prop_placements(skeleton) -> dict:
    """Each prop's frame in its attachment hand bone's frame: TargetProps.PROP_PLACEMENTS."""
    return {prop: palm_local(skeleton, side) @ GRIPS[prop][side].inverted() for prop, side in PROP_HANDS.items()}


def godot_prop_placements(skeleton) -> str:
    """PROP_PLACEMENTS for scripts/target_props.gd: a hand bone's frame is the same in Blender and Godot."""
    lines = []
    for prop, placement in prop_placements(skeleton).items():
        columns = [placement.col[index].xyz for index in range(3)]
        vectors = ", ".join("Vector3(%s)" % ", ".join(f"{value:.4f}" for value in column) for column in columns)
        origin = ", ".join(f"{value:.4f}" for value in placement.translation)
        lines.append(f"\t{prop.upper()}: Transform3D(Basis({vectors}),\n\t\t\tVector3({origin})),")
    return "\n".join(lines)


def hand_for_palm(skeleton, side: str, palm: Matrix) -> tuple[Vector, tuple]:
    """Armature-space wrist and aim that put the palm frame at `palm`."""
    hand = f"hand{side}"
    hand_frame = palm @ palm_local(skeleton, side).inverted()
    delta = hand_frame.to_quaternion() @ skeleton.rest_rotations[hand].inverted()
    return hand_frame.translation.copy(), (delta @ skeleton.direction(hand), delta @ palm_normal(skeleton, side))


def hold(rig: CharacterRig, arm: ArmSpec, side: str, palm: Matrix, pole: Vector) -> None:
    """Pose an arm (world space) so its palm frame lands on `palm`."""
    arm.wrist, arm.aim = hand_for_palm(rig.skeleton, side, palm)
    arm.pole = pole
    arm.aim_weight = 1.0
    arm.world_space = True


def hold_prop(rig: CharacterRig, arm: ArmSpec, side: str, prop: str, prop_frame: Matrix, pole: Vector) -> None:
    hold(rig, arm, side, prop_frame @ GRIPS[prop][side], pole)


def _cylinder_distance(point: Vector, radius: float, low: float, high: float) -> float:
    radial = Vector((point.x, point.z)).length - radius
    vertical = max(low - point.y, point.y - high)
    return Vector((max(radial, 0.0), max(vertical, 0.0))).length + min(max(radial, vertical), 0.0)


def _box_distance(point: Vector, half_size: Vector) -> float:
    outside = Vector((abs(point.x) - half_size.x, abs(point.y) - half_size.y, abs(point.z) - half_size.z))
    return Vector((max(outside.x, 0.0), max(outside.y, 0.0), max(outside.z, 0.0))).length + min(max(outside), 0.0)


def prop_distance(prop: str, point: Vector) -> float:
    """Signed distance from a point in the prop's frame to its surface (negative inside)."""
    if prop == "can":
        return _cylinder_distance(point, CAN_RADIUS, -CAN_HEIGHT * 0.5, CAN_HEIGHT * 0.5)
    if prop == "broom":
        return _cylinder_distance(point, BROOM_HANDLE_RADIUS, -BROOM_HANDLE_LENGTH, 0.0)
    if prop == "phone":
        return _box_distance(point, PHONE_SIZE * 0.5)
    return min(_box_distance(book_leaf(sign).inverted() @ point, BOOK_LEAF_SIZE * 0.5) for sign in (1.0, -1.0))


def wrap_curls(skeleton, side: str, prop: str) -> dict:
    """Per-finger curls that lay each finger round the prop: index..pinky -> (knuckle, middle, end joint) degrees.
    Each finger takes the bend at its knuckle and the even bend of its two outer joints that lay its outer segments
    closest to the surface (least squares), without any of them sinking into it."""
    hand_to_prop = GRIPS[prop][side] @ palm_local(skeleton, side).inverted() @ bone_matrix(skeleton, f"hand{side}").inverted()
    curls = {}
    for finger in FINGERS:
        chain = [f"{finger}_0{index}{side}" for index in (1, 2, 3)]
        best = (math.inf, (0.0, 0.0, 0.0))
        for knuckle_step in range(int(FINGER_JOINT_LIMIT / FINGER_CURL_STEP) + 1):
            for outer_step in range(int(FINGER_JOINT_LIMIT / FINGER_CURL_STEP) + 1):
                angles = (knuckle_step * FINGER_CURL_STEP,) + (outer_step * FINGER_CURL_STEP,) * 2
                pose = Pose()
                curl_fingers(skeleton, pose, side, 0.0, 0.0, {finger: angles})
                world, heads = forward_kinematics(skeleton, pose)
                tip = tail_position(skeleton, world, heads, chain[2])
                points = (heads[chain[1]], heads[chain[1]].lerp(heads[chain[2]], 0.5), heads[chain[2]],
                          heads[chain[2]].lerp(tip, 0.5), tip)
                distances = [prop_distance(prop, hand_to_prop @ point) for point in points]
                if min(distances) >= FINGER_CENTRE_DEPTH * 0.5:
                    best = min(best, (sum((distance - FINGER_CENTRE_DEPTH) ** 2 for distance in distances), angles))
        curls[finger] = best[1]
    return curls


def eyes(rig: CharacterRig, pose) -> Vector:
    """Armature-space point between the eyes (a little above the measured mouth)."""
    world, heads = forward_kinematics(rig.skeleton, pose)
    origin, rotation = heads["chest"], world["chest"]
    return origin + rotation @ (rig.mouth(pose) + Vector((0.0, 0.0, 0.06)))


def axis_frame(origin: Vector, axis: Vector, facing: Vector) -> Matrix:
    """A prop frame at `origin` with +Y along `axis` and +Z turned as close to `facing` as it allows."""
    axis = axis.normalized()
    normal = (facing - axis * facing.dot(axis)).normalized()
    matrix = Matrix((axis.cross(normal), axis, normal)).transposed().to_4x4()
    matrix.translation = origin
    return matrix


def to_world(rig: CharacterRig, pose, chest_point: Vector) -> Vector:
    origin, rotation = rig.chest_frame(pose)
    return origin + rotation @ chest_point


def facing_frame(origin: Vector, up: Vector, toward: Vector) -> Matrix:
    """A prop frame at `origin` whose +Z faces `toward` and +Y leans to `up`."""
    normal = (toward - origin).normalized()
    up = (up - normal * up.dot(normal)).normalized()
    matrix = Matrix((up.cross(normal), up, normal)).transposed().to_4x4()
    matrix.translation = origin
    return matrix


def blend_frames(first: Matrix, second: Matrix, weight: float) -> Matrix:
    rotation = first.to_quaternion().slerp(second.to_quaternion(), weight).to_matrix().to_4x4()
    rotation.translation = first.translation.lerp(second.translation, weight)
    return rotation


def hand_palm(rig: CharacterRig, pose, side: str) -> Matrix:
    """Where a pose puts a hand's palm frame (armature space)."""
    world, heads = forward_kinematics(rig.skeleton, pose)
    hand = f"hand{side}"
    matrix = (world[hand] @ rig.skeleton.rest_rotations[hand]).to_matrix().to_4x4()
    matrix.translation = heads[hand]
    return matrix @ palm_local(rig.skeleton, side)


# The palm rides this far out from the thigh's axis (thigh radius forward, plus the skirt over it).
THIGH_PALM_CLEARANCE = 0.012


def thigh_palm(rig: CharacterRig, pose, side: str, fraction: float, inward: float, turn_in: float) -> Matrix:
    """A palm lying on the front of the thigh (its top when seated), `fraction` of the way to the knee, fingers along
    the thigh and turned `turn_in` toward the middle (0..1)."""
    _, heads = forward_kinematics(rig.skeleton, pose)
    hip, knee = heads[f"thigh{side}"], heads[f"shin{side}"]
    along = (knee - hip).normalized()
    front = along.cross(Vector((1.0, 0.0, 0.0))).normalized()
    radii = rig.stance.seated_leg_radii or rig.stance.leg_radii
    radius = radii[0] + (radii[1] - radii[0]) * fraction + THIGH_PALM_CLEARANCE
    middle = Vector((-side_sign(side), 0.0, 0.0))
    point = hip.lerp(knee, fraction) + front * radius + middle * inward
    return oriented_frame(point, along.lerp(middle, turn_in * 0.4), -front + middle * 0.12)


def acting_seated(rig: CharacterRig, frame_number: float, period: float) -> BodySpec:
    """The seated idle with a slow weight shift from one buttock to the other that the chest and head follow late,
    and a breath that rocks the pelvis."""
    spec = rig.seated_idle(frame_number, period)
    shift = wave(frame_number, period)
    spec.hips_offset += Vector((0.0035 * shift, 0.0015 * wave(frame_number, period, 0.25, 2.0), 0.0))
    spec.hips = add_degrees(spec.hips, (0.6 * wave(frame_number, period, 0.25, 2.0), -1.0 * shift, 0.0))
    spec.chest = add_degrees(spec.chest, (0.0, 0.8 * wave(frame_number, period, 0.08), 0.0))
    spec.head = add_degrees(spec.head, (0.0, -0.9 * wave(frame_number, period, 0.16), 0.0))
    return spec


LAP_FRACTION = 0.55
LAP_INWARD = 0.03
LAP_TURN_IN = 0.5


def lap_hands(rig: CharacterRig, spec: BodySpec, sides: tuple = SIDES, phase: float = 0.0) -> None:
    """Both palms resting on the thighs near the middle, fingers toward the knees, holding the skirt down."""
    pose = compose(rig, spec)
    for side in sides:
        arm = spec.arms[side]
        hold(rig, arm, side, thigh_palm(rig, pose, side, LAP_FRACTION, LAP_INWARD, LAP_TURN_IN), lap_pole(side))
        arm.finger_curls = finger_fan(12.0, 5.0, 3.0, phase + (0.0 if side == ".L" else 0.3))
        arm.thumb = 16.0
        arm.splay = -2.0


def idle_palm(rig: CharacterRig, spec: BodySpec, side: str) -> Matrix:
    """Where the idle arm would put the palm on this frame's body."""
    hanging = replace(spec, arms={other: replace(rig.stance.idle_arm) for other in SIDES})
    return hand_palm(rig, compose(rig, hanging), side)


# Sitting down, the hands come forward to the front of the skirt (holding it down over the thighs) as the knees bend,
# then ride the thighs onto the lap. Standing up they push off the lap, slide back up the thighs and let go.
SIT_DOWN_HANDS = Curve([(0, 0.0), (5, 0.0), (13, 1.0), (30, 1.0)])
SIT_DOWN_SLIDE = Curve([(0, 0.25), (13, 0.25), (24, LAP_FRACTION - 0.02), (30, LAP_FRACTION)])
SIT_DOWN_GLANCE = Curve([(0, 0.0), (3, 1.0), (9, 1.0), (15, 0.0), (30, 0.0)])
STAND_UP_HANDS = Curve([(0, 1.0), (16, 1.0), (25, 0.0), (30, 0.0)])
STAND_UP_SLIDE = Curve([(0, LAP_FRACTION), (6, LAP_FRACTION - 0.08), (16, 0.3), (30, 0.25)])


def clip_sit_transition(rig: CharacterRig, frame_number: float, curves: dict, hands: Curve, slide: Curve,
                        glance: Curve | None = None) -> BodySpec:
    spec = sit_transition_body(rig, frame_number, curves)
    if glance is not None:
        # Before sitting he glances back over his shoulder at the seat: the head leads, the neck and chest follow.
        spec.head = add_degrees(spec.head, (6.0 * glance.scalar(frame_number), -4.0 * glance.scalar(frame_number),
                                            -24.0 * glance.scalar(frame_number)))
        spec.neck = add_degrees(spec.neck, (0.0, 0.0, -9.0 * glance.scalar(frame_number - 2.0)))
        spec.chest = add_degrees(spec.chest, (0.0, 0.0, -4.0 * glance.scalar(frame_number - 4.0)))
    reach = hands.scalar(frame_number)
    fraction = slide.scalar(frame_number)
    pose = compose(rig, spec)
    for side in SIDES:
        on_thigh = thigh_palm(rig, pose, side, fraction, LAP_INWARD * reach, LAP_TURN_IN * reach)
        palm = blend_frames(idle_palm(rig, spec, side), on_thigh, reach)
        arm = spec.arms[side]
        hold(rig, arm, side, palm, Vector((side_sign(side) * 0.7, 0.5, -0.4)).lerp(lap_pole(side), reach))
        arm.finger_curls = finger_fan(12.0 + 4.0 * (1.0 - reach), 5.0, 3.0 * reach, frame_number / 30.0)
        arm.thumb = 16.0 - 2.0 * (1.0 - reach)
        arm.splay = -2.0 * reach
    return spec


# ---------------------------------------------------------------------------------------------------
# Clips

# Mid-idle the right fingers roll and the head tips with a small "hm?", led by the head and followed by the neck.
IDLE_FIDGET = Curve([(0, 0.0), (38, 0.0), (48, 1.0), (58, 0.3), (66, 0.0), (90, 0.0)], period=90.0)
IDLE_TILT = Curve([(0, 0.0), (50, 0.0), (58, 1.0), (72, 0.8), (84, 0.0), (90, 0.0)], period=90.0)


def clip_idle(rig: CharacterRig, frame: float) -> BodySpec:
    spec = acting_idle(rig, frame, 90.0)
    fidget = IDLE_FIDGET.scalar(frame)
    right = spec.arms[".R"]
    right.finger_curls = {name: curl + 18.0 * IDLE_FIDGET.scalar(frame - 2.0 * index)
                          for index, (name, curl) in enumerate(right.finger_curls.items())}
    right.hand = add_degrees(right.hand, (6.0 * fidget, 0.0, 0.0))
    spec.head = add_degrees(spec.head, (-1.5 * IDLE_TILT.scalar(frame), 4.0 * IDLE_TILT.scalar(frame),
                                        3.0 * IDLE_TILT.scalar(frame)))
    spec.neck = add_degrees(spec.neck, (0.0, 1.5 * IDLE_TILT.scalar(frame - 3.0), 1.5 * IDLE_TILT.scalar(frame - 3.0)))
    return spec


def clip_walk(rig: CharacterRig, frame: float, cycle: WalkCycle) -> BodySpec:
    phase = cycle.phase(frame)
    turn = math.cos(2.0 * math.pi * phase)
    roll = math.sin(2.0 * math.pi * (phase - 0.05))
    bob = math.cos(4.0 * math.pi * (phase - 0.06))
    spec = rig.standing_body()
    spec.gait = cycle
    spec.gait_frame = frame
    spec.hips = (2.0, 0.0, 0.0)
    spec.spine = (2.0, 2.0 * roll, 3.5 * turn)
    spec.chest = (1.0, 1.5 * roll, 3.0 * math.cos(2.0 * math.pi * (phase - 0.03)))
    spec.neck = (1.0 + 0.6 * bob, -0.8 * roll, -2.0 * turn)
    spec.head = (1.5 + 0.8 * bob, -2.0 - 0.6 * roll, -2.0 * math.cos(2.0 * math.pi * (phase - 0.05)))
    spec.breath_amount = 0.0
    for side in SIDES:
        side_phase = phase + (0.0 if side == ".L" else 0.5)
        swing = -13.0 * math.cos(2.0 * math.pi * (side_phase - 0.06)) + 3.0
        arm = spec.arms[side]
        arm.adduct = 21.0
        arm.swing = swing
        arm.elbow = 16.0 + 9.0 * max(0.0, swing) / 16.0 + 3.0 * math.cos(2.0 * math.pi * (side_phase - 0.14))
        # The hand trails the forearm's swing and flips over at each end of it.
        arm.hand = (8.0 * math.cos(2.0 * math.pi * (side_phase - 0.16)), -10.0, 3.0 * math.sin(2.0 * math.pi * (side_phase - 0.2)))
        graceful_hand(arm, side_phase - 0.2, 3.0)
        arm.shoulder = (0.0, -2.0 + 1.5 * bob, 2.0 * math.cos(2.0 * math.pi * (side_phase - 0.05)))
    spec.skirt_sway = -2.5 * math.cos(2.0 * math.pi * (phase - 0.12))
    return spec


NOTICE_KEYS = {
    # A beat of stillness with a caught breath, then the head turns first and the body follows it round.
    "head_yaw": [(0, 0), (3, 0), (7, 7), (11, 9), (16, 7.5), (30, 7)],
    "neck_yaw": [(0, 0), (4, 0), (9, 5), (14, 6.5), (30, 5)],
    "chest_yaw": [(0, 0), (6, 0), (11, 5), (17, 7.5), (22, 6.5), (30, 6.5)],
    "spine_yaw": [(0, 0), (7, 0), (13, 5), (19, 8), (30, 7)],
    "hips_yaw": [(0, 0), (9, 0), (15, 6), (21, 9.5), (30, 8.5)],
    "chest_pitch": [(0, 0), (3, -3.5), (8, -2), (14, -1), (30, -1)],
    "shoulders": [(0, 0), (3, 6), (9, 4), (30, 1.5)],
    "drop": [(0, 0), (3, -0.004), (10, -0.012), (18, -0.005), (30, -0.006)],
    "weight": [(0, 0), (12, 0.006), (30, 0.005)],
    "back": [(0, 0), (4, 0.006), (14, 0.004), (30, 0.003)],
    # The right hand drifts up toward the chest, the fingers curling as it comes.
    "hand": [(0, 0), (5, 0), (16, 1), (30, 1)],
}
NOTICE_HAND_AT_CHEST = Vector((-0.04, -0.165, -0.04))


def clip_notice_player(rig: CharacterRig, frame: float, curves: dict) -> BodySpec:
    spec = acting_idle(rig, frame, 90.0)
    value = {name: curve.scalar(frame) for name, curve in curves.items()}
    spec.hips_offset += Vector((value["weight"], value["back"], value["drop"]))
    spec.hips = add_degrees(spec.hips, (0.0, 0.0, value["hips_yaw"]))
    spec.spine = add_degrees(spec.spine, (0.0, 0.0, value["spine_yaw"]))
    spec.chest = add_degrees(spec.chest, (value["chest_pitch"], 0.0, value["chest_yaw"]))
    spec.neck = add_degrees(spec.neck, (0.0, 0.0, value["neck_yaw"]))
    spec.head = add_degrees(spec.head, (0.0, 0.0, value["head_yaw"]))
    for side in SIDES:
        spec.arms[side].shoulder = add_degrees(spec.arms[side].shoulder, (0.0, value["shoulders"], 0.0))
    hand = value["hand"]
    right = spec.arms[".R"]
    right.wrist = rig.idle_wrists[".R"].lerp(NOTICE_HAND_AT_CHEST, hand) + Vector((0.0, -0.025, 0.0)) * math.sin(math.pi * hand)
    right.pole = rig.idle_poles[".R"].lerp(Vector((-0.6, 0.6, -0.5)), hand)
    right.aim = ((0.2, -0.3, 0.9), (0.3, 0.9, 0.0))
    right.aim_weight = hand
    right.finger_curls = finger_fan(9.0 + 30.0 * hand, 6.0 + 4.0 * hand, 2.0, frame / 30.0)
    right.thumb = 14.0 + 20.0 * hand
    left = spec.arms[".L"]
    left.elbow += 8.0 * hand
    left.finger_curls = finger_fan(9.0 + 14.0 * hand, 6.0, 2.0, frame / 30.0 + 0.3)
    return spec


def startled_curves(rig: CharacterRig) -> dict:
    """"Eek!": a flinch down (anticipation), a hop up onto the toes with the shoulders up and both hands snapping to
    the chest, then a landing into bent knees and a quick, settling breath."""
    chest_left = Vector((0.065, -0.155, -0.02))
    chest_right = Vector((-0.045, -0.165, 0.03))
    curves = {
        "drop": Curve([(0, 0.0), (2, -0.008), (5, 0.012), (8, -0.022), (11, -0.034), (15, -0.026), (20, -0.028)]),
        "back": Curve([(0, 0.0), (2, 0.004), (5, 0.022), (9, 0.028), (20, 0.024)]),
        "heels": Curve([(0, 0.0), (2, 0.0), (4, 14.0), (6, 12.0), (9, 0.0), (20, 0.0)]),
        "spine_pitch": Curve([(0, 0.0), (2, 2.0), (5, -4.0), (9, -1.0), (13, 1.5), (20, 0.5)]),
        "chest_pitch": Curve([(0, 0.0), (2, 2.0), (5, -9.0), (8, -3.0), (12, -5.0), (20, -3.5)]),
        "head_pitch": Curve([(0, 0.0), (2, 2.0), (5, -7.0), (9, -1.0), (13, 1.0), (20, -1.0)]),
        "head_roll": Curve([(0, 0.0), (4, 0.0), (8, 4.0), (14, 3.0), (20, 3.0)]),
        "shoulders": Curve([(0, 0.0), (2, -2.0), (5, 14.0), (9, 8.0), (13, 10.0), (20, 8.0)]),
        "fingers": Curve([(0, 18.0), (3, 18.0), (6, 62.0), (11, 52.0), (20, 58.0)]),
        "hips_yaw": Curve([(0, 0.0), (5, -3.0), (20, -2.0)]),
    }
    for side, target in ((".L", chest_left), (".R", chest_right)):
        idle_wrist = rig.idle_wrists[side]
        lift = idle_wrist.lerp(target, 0.6) + Vector((0.0, -0.08, 0.0))
        curves[f"wrist{side}"] = Curve([(0, idle_wrist), (2, idle_wrist + Vector((0.0, 0.0, -0.01))), (4, lift), (6, target),
                                        (10, target + Vector((0.0, 0.008, -0.012))), (14, target + Vector((0.0, -0.003, 0.004))),
                                        (20, target)])
        idle_pole = rig.idle_poles[side]
        tucked = Vector((side_sign(side) * 0.5, 0.6, -0.6))
        curves[f"pole{side}"] = Curve([(0, idle_pole), (2, idle_pole), (6, tucked), (20, tucked)])
        curves[f"aim{side}"] = Curve([(0, 0.0), (2, 0.0), (6, 1.0), (20, 1.0)])
    return curves


def clip_startled(rig: CharacterRig, frame: float, curves: dict) -> BodySpec:
    spec = acting_idle(rig, frame, 90.0)
    # A fast, shallow breath after the fright.
    spec.breath_phase = 0.0 if frame < 9.0 else (frame - 9.0) / 11.0
    spec.breath_amount = 1.6
    spec.hips_offset += Vector((0.0, curves["back"].scalar(frame), curves["drop"].scalar(frame)))
    spec.hips = add_degrees(spec.hips, (0.0, 0.0, curves["hips_yaw"].scalar(frame)))
    heels = curves["heels"].scalar(frame)
    spec.feet = rig_feet(rig, {side: (x, y, yaw, pitch + heels) for side, (x, y, yaw, pitch) in IDLE_FEET.items()})
    spec.spine = add_degrees(spec.spine, (curves["spine_pitch"].scalar(frame), 0.0, 0.0))
    spec.chest = add_degrees(spec.chest, (curves["chest_pitch"].scalar(frame), 0.0, 0.0))
    spec.neck = add_degrees(spec.neck, (curves["head_pitch"].scalar(frame - 1.0) * 0.5, 0.0, 0.0))
    spec.head = add_degrees(spec.head, (curves["head_pitch"].scalar(frame), curves["head_roll"].scalar(frame), 0.0))
    for side in SIDES:
        arm = spec.arms[side]
        arm.shoulder = add_degrees(arm.shoulder, (0.0, curves["shoulders"].scalar(frame), 0.0))
        arm.wrist = curves[f"wrist{side}"].vector(frame)
        arm.pole = curves[f"pole{side}"].vector(frame)
        arm.aim = ((side_sign(side) * -0.2, -0.3, 0.9), (-side_sign(side) * 0.3, 0.9, 0.0))
        arm.aim_weight = curves[f"aim{side}"].scalar(frame)
        # The fingers snap shut a frame after the hands arrive, the pinky last.
        arm.finger_curls = {name: curves["fingers"].scalar(frame - 0.7 * index) + 4.0 * index
                            for index, name in enumerate(FINGERS)}
        arm.thumb = 30.0
        arm.splay = -3.0
    return spec


# Before each turn a small counter-move (anticipation), then the head leads, overshoots and settles.
LOOK_AROUND = Curve([(0, 0.0), (8, -4.0), (14, -3.0), (30, 36.0), (36, 40.0), (46, 35.0), (56, 30.0), (62, 34.0),
                     (78, -34.0), (84, -40.0), (96, -35.0), (102, -31.0), (116, -2.0), (120, 0.0)], period=120.0)
LOOK_UP = Curve([(0, 0.0), (30, -4.0), (46, -1.0), (60, 0.0), (80, -5.0), (100, -2.0), (120, 0.0)], period=120.0)
# The right hand comes up to the chest while he scans, a wary little gesture, and drops back as he settles.
LOOK_HAND = Curve([(0, 0.0), (12, 0.0), (26, 1.0), (100, 1.0), (116, 0.0), (120, 0.0)], period=120.0)
LOOK_HAND_AT_CHEST = Vector((-0.035, -0.16, -0.015))


def clip_look_around(rig: CharacterRig, frame: float) -> BodySpec:
    spec = acting_idle(rig, frame, 120.0)
    hips_look = LOOK_AROUND.scalar(frame - 6.0)
    body_look = LOOK_AROUND.scalar(frame - 3.0)
    head_look = LOOK_AROUND.scalar(frame + 2.0)
    spec.hips_offset += Vector((0.008 * hips_look / 40.0, 0.0, 0.0))
    spec.hips = add_degrees(spec.hips, (0.0, 0.0, 0.12 * hips_look))
    spec.spine = add_degrees(spec.spine, (0.0, 0.03 * body_look, 0.17 * body_look))
    spec.chest = add_degrees(spec.chest, (0.0, 0.0, 0.2 * body_look))
    spec.neck = add_degrees(spec.neck, (LOOK_UP.scalar(frame) * 0.4, 0.0, 0.22 * head_look))
    spec.head = add_degrees(spec.head, (LOOK_UP.scalar(frame) * 0.6, 0.06 * head_look, 0.29 * head_look))
    for side in SIDES:
        spec.arms[side].swing += 0.05 * body_look * side_sign(side)
    hand = LOOK_HAND.scalar(frame)
    right = spec.arms[".R"]
    idle_right = rig.idle_wrists[".R"]
    right.wrist = idle_right.lerp(LOOK_HAND_AT_CHEST, hand) + Vector((0.0, -0.03, 0.0)) * math.sin(math.pi * hand)
    right.pole = rig.idle_poles[".R"].lerp(Vector((-0.6, 0.6, -0.5)), hand)
    right.aim = ((0.2, -0.3, 0.9), (0.3, 0.9, 0.0))
    right.aim_weight = hand
    right.finger_curls = finger_fan(9.0 + 22.0 * hand, 6.0 + 4.0 * hand, 2.0, frame / 120.0)
    right.thumb = 14.0 + 16.0 * hand
    return spec


SIT_GLANCE = Curve([(0, 0.0), (28, 0.0), (36, 1.0), (52, 1.0), (60, 0.0), (90, 0.0)], period=90.0)
# The right heel lifts off the floor twice, a small restless tap.
SIT_TAP = Curve([(0, 0.0), (62, 0.0), (66, 1.0), (70, 0.2), (74, 1.0), (80, 0.0), (90, 0.0)], period=90.0)


def clip_sit(rig: CharacterRig, frame_number: float) -> BodySpec:
    spec = acting_seated(rig, frame_number, 90.0)
    look = SIT_GLANCE.scalar(frame_number + 1.0)
    spec.head = add_degrees(spec.head, (-2.0 * look, 3.0 * look, 16.0 * look))
    spec.neck = add_degrees(spec.neck, (0.0, 0.0, 6.0 * SIT_GLANCE.scalar(frame_number - 2.0)))
    spec.chest = add_degrees(spec.chest, (0.0, 0.0, 3.0 * SIT_GLANCE.scalar(frame_number - 5.0)))
    x, y, yaw, pitch = IDLE_FEET[".R"]
    spec.feet = rig_feet(rig, {**IDLE_FEET, ".R": (x, y, yaw, pitch + 8.0 * SIT_TAP.scalar(frame_number))})
    lap_hands(rig, spec, phase=frame_number / 90.0)
    return spec


# The left hand leaves its leaf, crosses to the right leaf's top corner and turns the page back over.
READ_PAGE = Curve([(0, 0.0), (72, 0.0), (82, 1.0), (86, 1.0), (98, 0.0), (120, 0.0)], period=120.0)
READ_GLANCE = Curve([(0, 0.0), (20, 1.5), (45, -0.5), (66, 0.5), (80, 3.0), (100, 0.0), (120, 0.0)], period=120.0)
# The open book's centre: above the middle of the lap and toward the knees, its pages turned up to the eyes.
BOOK_FROM_LAP = Vector((0.0, -0.05, 0.11))
PAGE_PICK = Vector((0.12, 0.07, 0.03))


def clip_sit_read(rig: CharacterRig, frame_number: float) -> BodySpec:
    spec = acting_seated(rig, frame_number, 120.0)
    phase = frame_number / 120.0
    page = READ_PAGE.scalar(frame_number)
    # Reading along the lines: the head drifts across a line and flicks back, looks after the turning hand.
    line = (phase * 6.0) % 1.0
    scan = 2.0 * (line - 0.5) if line < 0.85 else 2.0 * (0.35 - (line - 0.85) / 0.15 * 0.85)
    spec.spine = add_degrees(spec.spine, (3.0, 0.0, 0.0))
    spec.chest = add_degrees(spec.chest, (4.0, 0.0, 0.0))
    spec.neck = add_degrees(spec.neck, (9.0, 0.0, 0.0))
    spec.head = add_degrees(spec.head, (13.0 + 0.8 * wave(frame_number, 120.0, 0.0, 2.0), 1.0,
                                        -1.5 * scan * (1.0 - page) + 2.0 * READ_GLANCE.scalar(frame_number) - 4.0 * page))
    pose = compose(rig, spec)
    lap = (rig.lap_point(pose, ".L") + rig.lap_point(pose, ".R")) * 0.5
    book = facing_frame(lap + BOOK_FROM_LAP, Vector((0.0, 0.0, 1.0)), eyes(rig, pose))
    right = spec.arms[".R"]
    hold_prop(rig, right, ".R", "book", book, Vector((-0.8, 0.4, -0.5)))
    right.finger_curls = finger_fan(6.0, 3.0, 1.5, phase)
    right.thumb = 40.0
    left = spec.arms[".L"]
    held = book @ GRIPS["book"][".L"]
    pick = book @ oriented_frame(PAGE_PICK, Vector((0.3, 0.9, -0.2)), Vector((0.0, 0.0, -1.0)))
    turning = blend_frames(held, pick, page)
    turning.translation += book.to_3x3() @ Vector((0.0, 0.0, 0.04 * math.sin(math.pi * page)))
    hold(rig, left, ".L", turning, Vector((0.8, 0.4, -0.5)))
    left.finger_curls = finger_fan(6.0 + 10.0 * page, 3.0, 1.5, phase + 0.3)
    left.thumb = 40.0 - 25.0 * page
    left.splay = -2.0 * page
    return spec


PHONE_SCROLL = Curve([(0, 0.0), (18, 0.0), (22, 1.0), (26, 0.0), (48, 0.0), (52, 1.0), (56, 0.0), (90, 0.0), (94, 1.0),
                      (98, 0.0), (120, 0.0)], period=120.0)
# Something on the screen: he lifts the phone closer, then giggles at it (the shoulders bounce) and lowers it again.
PHONE_LIFT = Curve([(0, 0.0), (58, 0.0), (68, 1.0), (86, 1.0), (98, 0.0), (120, 0.0)], period=120.0)
PHONE_GIGGLE = Curve([(0, 0.0), (70, 0.0), (73, 1.0), (84, 1.0), (88, 0.0), (120, 0.0)], period=120.0)
PHONE_FROM_LAP = Vector((-0.035, -0.06, 0.17))
# The fingers curl round the phone's far edge.
PHONE_CURLS = {"index": 48.0, "middle": 54.0, "ring": 58.0, "pinky": 62.0}
PHONE_TOWARD_EYES = 0.3


def clip_phone(rig: CharacterRig, frame_number: float) -> BodySpec:
    spec = acting_seated(rig, frame_number, 120.0)
    phase = frame_number / 120.0
    lift = PHONE_LIFT.scalar(frame_number)
    giggle = PHONE_GIGGLE.scalar(frame_number) * (0.5 + 0.5 * math.sin(2.0 * math.pi * (frame_number - 70.0) / 5.0))
    spec.spine = add_degrees(spec.spine, (2.0, 0.0, 0.0))
    spec.chest = add_degrees(spec.chest, (3.0 - 1.5 * lift + 1.5 * giggle, 0.0, 0.0))
    spec.neck = add_degrees(spec.neck, (10.0 - 3.0 * lift, 0.0, -2.0))
    spec.head = add_degrees(spec.head, (14.0 - 5.0 * lift + 1.5 * giggle, -3.0 * lift, -3.0))
    for side in SIDES:
        spec.arms[side].shoulder = (0.0, 3.0 * giggle, 0.0)
    lap_hands(rig, spec, (".L",), phase)
    pose = compose(rig, spec)
    lap = (rig.lap_point(pose, ".L") + rig.lap_point(pose, ".R")) * 0.5
    look = eyes(rig, pose)
    centre = (lap + PHONE_FROM_LAP).lerp(look, PHONE_TOWARD_EYES * lift)
    phone = facing_frame(centre, Vector((0.0, 0.0, 1.0)), look)
    right = spec.arms[".R"]
    hold_prop(rig, right, ".R", "phone", phone, Vector((-0.8, 0.4, -0.5)))
    right.finger_curls = PHONE_CURLS
    right.thumb = 20.0 + 25.0 * PHONE_SCROLL.scalar(frame_number)
    return spec


# The can comes up after a little dip of the hand, tips to the lips while the head tilts back for three swallows, and
# comes down with a satisfied breath out; then he glances aside and taps the can.
DRINK_RAISE = Curve([(0, 0.0), (14, 0.0), (17, -0.08), (32, 1.0), (64, 1.0), (80, 0.0), (120, 0.0)], period=120.0)
DRINK_TILT = Curve([(0, 0.0), (28, 0.0), (38, 1.0), (60, 1.0), (70, 0.0), (120, 0.0)], period=120.0)
DRINK_SWALLOW = Curve([(0, 0.0), (40, 0.0), (42, 1.0), (45, 0.0), (48, 1.0), (51, 0.0), (55, 1.0), (58, 0.0), (120, 0.0)],
                      period=120.0)
DRINK_SIGH = Curve([(0, 0.0), (68, 0.0), (76, 1.0), (88, 0.0), (120, 0.0)], period=120.0)
DRINK_GLANCE = Curve([(0, 0.0), (92, 0.0), (100, 7.0), (112, 2.0), (120, 0.0)], period=120.0)
DRINK_TAP = Curve([(0, 0.0), (96, 0.0), (98, 1.0), (100, 0.0), (102, 1.0), (104, 0.0), (120, 0.0)], period=120.0)
# The held can in front of the waist (chest space), and how far it tips back at the lips.
CAN_AT_WAIST = Vector((-0.07, -0.2, -0.17))
CAN_DRINK_DEGREES = 72.0
CAN_HOLD_DEGREES = 8.0
# The can's top rim sits this far in front of the mouth landmark (forward, up) while he drinks.
CAN_RIM_FROM_MOUTH = Vector((0.0, -0.025, -0.005))


def clip_drink(rig: CharacterRig, frame: float, can_curls: dict) -> BodySpec:
    spec = acting_idle(rig, frame, 120.0)
    raise_amount = DRINK_RAISE.scalar(frame)
    tilt = DRINK_TILT.scalar(frame)
    swallow = DRINK_SWALLOW.scalar(frame)
    sigh = DRINK_SIGH.scalar(frame)
    spec.chest = add_degrees(spec.chest, (-2.0 * tilt + 2.0 * sigh, 0.0, -2.0 * max(0.0, raise_amount)))
    spec.neck = add_degrees(spec.neck, (-5.0 * tilt + 1.5 * swallow, 0.0, 0.0))
    spec.head = add_degrees(spec.head, (-10.0 * tilt + 3.0 * sigh, 1.5 * tilt, DRINK_GLANCE.scalar(frame)))
    for side in SIDES:
        spec.arms[side].shoulder = add_degrees(spec.arms[side].shoulder, (0.0, -2.5 * sigh, 0.0))
    left = spec.arms[".L"]
    left.elbow += 10.0 * tilt
    left.swing += 4.0 * tilt
    pose = compose(rig, spec)
    origin, rotation = rig.chest_frame(pose)
    forward = rotation @ Vector((0.0, -1.0, 0.0))
    up = rotation @ Vector((0.0, 0.0, 1.0))
    outward = rotation @ Vector((1.0, 0.0, 0.0))
    angle = math.radians(CAN_HOLD_DEGREES + (CAN_DRINK_DEGREES - CAN_HOLD_DEGREES) * tilt)
    axis = up * math.cos(angle) - forward * math.sin(angle)
    at_waist = to_world(rig, pose, CAN_AT_WAIST)
    at_lips = to_world(rig, pose, rig.mouth(pose) + CAN_RIM_FROM_MOUTH) - axis * (CAN_HEIGHT * 0.5)
    centre = at_waist.lerp(at_lips, max(0.0, raise_amount)) + up * 0.02 * min(0.0, raise_amount) / 0.08
    centre += forward * 0.03 * math.sin(math.pi * max(0.0, raise_amount))
    can = axis_frame(centre, axis, outward)
    right = spec.arms[".R"]
    hold_prop(rig, right, ".R", "can", can, Vector((-0.7, 0.55, -0.6)))
    # The index lifts off the can at its knuckle to tap it.
    tap = 14.0 * DRINK_TAP.scalar(frame)
    right.finger_curls = {**can_curls, "index": (can_curls["index"][0] - tap,) + can_curls["index"][1:]}
    right.thumb = 40.0
    return spec


BRAID_HOLD_LIFT = Curve([(0, 0.0), (22, 1.0), (112, 1.0), (136, 0.0), (150, 0.0)], period=150.0)
BRAID_REACH = Curve([(0, 0.0), (14, 0.0), (30, 1.0), (124, 1.0), (140, 0.0), (150, 0.0)], period=150.0)
# The cradling hand lifts the held braid bones forward off the chest by this much in total (pitch, roll).
BRAID_HELD_LIFT = (-12.0, -2.0)
RIGHT_BRAID_AIM = ((0.75, 0.40, 0.25), (0.15, 0.45, 0.88))
LEFT_BRAID_AIM = ((-0.8, 0.30, -0.45), (-0.30, 0.90, 0.20))


def _braid_landmark(rig: CharacterRig, pose, location: tuple) -> Vector:
    bone, fraction = location
    skeleton = rig.skeleton
    point = skeleton.heads[bone].lerp(skeleton.tails[bone], fraction)
    return rig.landmark(pose, bone, point)


STROKE = Curve([(0, 0.0), (30, 0.0), (60, 1.0), (68, 0.5), (76, 0.0), (106, 1.0), (131, 1.0), (150, 0.0)], period=150.0)
# The left hand leaves the braid between strokes (an arc away from it) and on the way back to idle.
STROKE_AWAY = Curve([(0, 1.0), (14, 1.0), (22, 0.5), (30, 0.0), (60, 0.0), (68, 0.6), (76, 0.0), (106, 0.0),
                     (122, 0.0), (131, 0.5), (140, 1.0), (150, 1.0)], period=150.0)


def fix_braid_curves(rig: CharacterRig) -> dict:
    return {"stroke": STROKE, "away": STROKE_AWAY}


def held_braid_rotations(braid: BraidLayout, amount: float) -> dict:
    """The held bones bend in a bump that peaks mid-way, summing to BRAID_HELD_LIFT at full `amount`."""
    held = braid.held_bones()
    shares = [math.sin(math.pi * (index + 1) / (len(held) + 1)) for index in range(len(held))]
    total = sum(shares)
    pitch, roll = BRAID_HELD_LIFT
    return {bone: (pitch * amount * share / total, roll * amount * share / total, 0.0) for bone, share in zip(held, shares)}


def clip_fix_braid(rig: CharacterRig, frame: float, curves: dict, braid: BraidLayout) -> BodySpec:
    spec = acting_idle(rig, frame, 150.0)
    lift = BRAID_HOLD_LIFT.scalar(frame)
    reach = BRAID_REACH.scalar(frame)
    stroke = curves["stroke"].scalar(frame)
    away = curves["away"].scalar(frame)
    spec.chest = add_degrees(spec.chest, (2.0 * lift, -1.5 * lift, -4.0 * lift))
    spec.neck = add_degrees(spec.neck, (3.0 * lift, -3.0 * lift, -3.0 * lift))
    spec.head = add_degrees(spec.head, (4.0 * lift, -7.0 * lift, -5.0 * lift))
    spec.extra_rotations = held_braid_rotations(braid, lift * 0.7)
    cradle = braid.point(BRAID_CRADLE_FRACTION)
    stroke_top, stroke_bottom = (braid.point(fraction) for fraction in BRAID_STROKE_FRACTIONS)
    idle_right = rig.idle_wrists[".R"]
    idle_left = rig.idle_wrists[".L"]

    def right_wrist(pose) -> Vector:
        return idle_right.lerp(palm_on(_braid_landmark(rig, pose, cradle), RIGHT_BRAID_AIM), lift)

    def left_wrist(pose) -> Vector:
        top = _braid_landmark(rig, pose, stroke_top)
        bottom = _braid_landmark(rig, pose, stroke_bottom)
        on_braid = palm_on(top.lerp(bottom, stroke), LEFT_BRAID_AIM)
        lifted_off = on_braid + Vector((0.03, -0.05, 0.0)) * math.sin(math.pi * min(1.0, away * 2.0))
        homeward = max(0.0, away * 2.0 - 1.0)
        return lifted_off.lerp(idle_left, homeward * homeward * (3.0 - 2.0 * homeward))

    right = spec.arms[".R"]
    right.wrist = right_wrist
    right.pole = rig.idle_poles[".R"].lerp(Vector((-0.8, 0.5, -0.4)), lift)
    right.aim = RIGHT_BRAID_AIM
    right.aim_weight = lift
    right.finger_curls = finger_fan(9.0 + 44.0 * lift, 6.0, 2.0, frame / 150.0)
    right.thumb = 14.0 + 21.0 * lift
    left = spec.arms[".L"]
    left.wrist = left_wrist
    left.pole = rig.idle_poles[".L"].lerp(Vector((0.85, -0.2, -0.5)), reach)
    left.aim = LEFT_BRAID_AIM
    left.aim_weight = reach
    # The stroking fingers close on the way down the braid and open as the hand lifts off it.
    left.finger_curls = finger_fan(9.0 + 26.0 * reach - 12.0 * away * reach, 6.0, 4.0 * reach, stroke, 0.06)
    left.thumb = 14.0 + 26.0 * reach
    return spec


CHAT_GESTURE = Curve([(0, 0.0), (10, 0.0), (22, 1.0), (30, 0.8), (36, 1.0), (48, 0.0), (120, 0.0)], period=120.0)
CHAT_LAUGH = Curve([(0, 0.0), (52, 0.0), (66, 1.0), (82, 1.0), (96, 0.0), (120, 0.0)], period=120.0)
CHAT_NOD = Curve([(0, 0.0), (98, 0.0), (102, 1.0), (106, 0.0), (110, 1.0), (114, 0.0), (120, 0.0)], period=120.0)
# The giggling hand covers the mouth from just in front of it, fingertips up around the nose.
CHAT_HAND_FROM_MOUTH = Vector((-0.035, -0.03, -0.105))
CHAT_FEET = {".L": (0.022, -0.072, 16.0, 0.0), ".R": (0.003, -0.002, -8.0, 0.0)}


def clip_lean_chat(rig: CharacterRig, frame: float) -> BodySpec:
    spec = acting_idle(rig, frame, 120.0)
    phase = frame / 120.0
    gesture = CHAT_GESTURE.scalar(frame)
    laugh = CHAT_LAUGH.scalar(frame)
    nod = CHAT_NOD.scalar(frame)
    giggle = laugh * math.sin(2.0 * math.pi * (frame - 64.0) / 6.0) if 64 <= frame <= 82 else 0.0
    spec.feet = rig_feet(rig, CHAT_FEET)
    spec.hips_offset = Vector((-0.02 + 0.006 * math.sin(2.0 * math.pi * phase), -0.01,
                               -0.02 - 0.002 * math.sin(2.0 * math.pi * (phase - 0.2))))
    spec.hips = (1.0, 4.0, -4.0)
    spec.spine = (3.0, -2.5, 3.0 + 2.0 * gesture)
    spec.chest = (4.0 + 2.0 * giggle + 2.0 * laugh, -2.0, 3.0 + 2.0 * gesture)
    spec.neck = (2.0 + 4.0 * nod - 2.0 * laugh, 1.0, 2.0)
    spec.head = (3.0 + 5.0 * nod - 3.0 * laugh, 6.0 - 3.0 * laugh, 4.0 + 3.0 * gesture)
    spec.breath_amount = 1.2
    left = spec.arms[".L"]
    left.wrist = Vector((0.155, 0.01, -0.235))
    left.pole = Vector((0.9, 0.35, 0.1))
    left.aim = ((-0.25, -0.5, -0.8), (-0.9, 0.2, 0.0))
    left.finger_curls = finger_fan(8.0, 4.0, 2.0, phase)
    left.thumb = 25.0
    left.shoulder = (0.0, 2.0 + 2.0 * giggle, 0.0)
    right = spec.arms[".R"]
    rest = Vector((-0.12, -0.13, -0.27))
    talk = Vector((-0.14, -0.23, -0.1))
    talk_bob = Vector((0.0, 0.0, 0.012 * math.sin(2.0 * math.pi * (frame - 22.0) / 10.0) * gesture))

    def wrist_to_mouth(pose) -> Vector:
        return rest.lerp(talk, gesture).lerp(rig.mouth(pose) + CHAT_HAND_FROM_MOUTH, laugh) + talk_bob

    right.wrist = wrist_to_mouth
    right.pole = Vector((-0.8, 0.5, -0.4))
    open_palm = ((0.2, -0.9, 0.2), (0.0, 0.0, 1.0))
    cover = ((0.4, 0.05, 0.9), (0.1, 0.95, -0.05))
    idle_aim = ((-0.1, -0.4, -0.9), (0.9, 0.2, 0.0))
    right.aim = _blend_aim(_blend_aim(idle_aim, open_palm, gesture), cover, laugh)
    # The talking hand opens and fans as it turns up, then the fingers trail the beat; the laughing hand closes.
    right.finger_curls = finger_fan(12.0 - 9.0 * gesture + 10.0 * laugh, 6.0 - 2.0 * gesture, 4.0 * gesture,
                                    (frame - 22.0) / 10.0, 0.08)
    right.splay = 9.0 * gesture * (1.0 - laugh)
    right.thumb = 12.0
    right.shoulder = (0.0, 2.0 * giggle, 0.0)
    spec.skirt_sway = 1.5
    return spec


def _blend_aim(first: tuple, second: tuple, weight: float) -> tuple:
    return (Vector(first[0]).lerp(Vector(second[0]), weight), Vector(first[1]).lerp(Vector(second[1]), weight))


SWEEP_FEET = {".L": (0.047, -0.092, 14.0, 0.0), ".R": (-0.037, 0.058, -18.0, 0.0)}
# The top hand rides in front of the waist; the broom's head sweeps an arc on the floor in front of his right foot,
# its bristles leading each stroke and trailing behind the turn of the body.
SWEEP_TOP_HAND = Vector((-0.08, -0.22, 0.03))
SWEEP_AZIMUTH = -22.0
SWEEP_ARC = 26.0


def clip_sweep(rig: CharacterRig, frame: float, broom_curls: dict) -> BodySpec:
    spec = acting_idle(rig, frame, 60.0)
    phase = frame / 60.0
    stroke = math.sin(2.0 * math.pi * phase)
    lagged = math.sin(2.0 * math.pi * (phase - 0.06))
    spec.feet = rig_feet(rig, SWEEP_FEET)
    spec.breath_amount = 0.5
    spec.hips_offset = Vector((0.012 * lagged, 0.012, -0.045 + 0.006 * math.cos(4.0 * math.pi * phase)))
    spec.hips = (8.0, -2.0 * lagged, -4.0 + 5.0 * lagged)
    spec.spine = (6.0, 1.0 * lagged, 4.0 * stroke)
    spec.chest = (5.0, 0.0, 5.0 * stroke)
    spec.neck = (6.0, 0.0, -4.0 * stroke)
    spec.head = (8.0, -2.0, -5.0 * math.sin(2.0 * math.pi * (phase - 0.1)))
    pose = compose(rig, spec)
    grip_on_axis = to_world(rig, pose, SWEEP_TOP_HAND + Vector((0.05 * stroke, 0.015 * math.cos(2.0 * math.pi * phase), 0.0)))
    reach = BROOM_HANDLE_LENGTH + BROOM_HEAD_HEIGHT * 0.5 - BROOM_TOP_GRIP
    azimuth = math.radians(SWEEP_AZIMUTH + SWEEP_ARC * math.sin(2.0 * math.pi * (phase - 0.08)))
    across = math.sqrt(max(0.0, reach * reach - grip_on_axis.z * grip_on_axis.z))
    head = Vector((grip_on_axis.x - math.sin(azimuth) * across, grip_on_axis.y - math.cos(azimuth) * across, 0.0))
    axis = (grip_on_axis - head).normalized()
    top = grip_on_axis + axis * BROOM_TOP_GRIP
    broom = axis_frame(top, axis, Vector((-1.0, 0.0, -0.3)))
    left = spec.arms[".L"]
    hold_prop(rig, left, ".L", "broom", broom, Vector((0.8, 0.4, -0.5)))
    left.finger_curls = broom_curls[".L"]
    left.thumb = 50.0
    right = spec.arms[".R"]
    hold_prop(rig, right, ".R", "broom", broom, Vector((-0.8, 0.5, -0.3)))
    right.finger_curls = broom_curls[".R"]
    right.thumb = 50.0
    spec.skirt_sway = 2.0 * math.cos(2.0 * math.pi * (phase - 0.1))
    return spec


def clip_wave(rig: CharacterRig, frame: float) -> BodySpec:
    """A bright wave from the elbow: the hand trails each swing of the forearm and flicks over at its end, the body
    bobs on the beats and leans into the greeting, and the head tilts against the hand."""
    spec = acting_idle(rig, frame, 45.0)
    phase = frame / 45.0
    swing = math.sin(2.0 * math.pi * 3.0 * phase)
    trail = math.sin(2.0 * math.pi * (3.0 * phase - 0.1))
    bounce = 0.5 - 0.5 * math.cos(2.0 * math.pi * 6.0 * (phase - 0.03))
    spec.breath_amount = 0.6
    spec.hips_offset += Vector((0.008, -0.004, -0.006 + 0.004 * bounce))
    spec.spine = add_degrees(spec.spine, (2.0, 2.0, 2.0))
    spec.chest = add_degrees(spec.chest, (1.5, 2.5 + 0.8 * trail, 3.0))
    spec.neck = add_degrees(spec.neck, (0.0, -1.0 - 0.8 * trail, 1.0))
    spec.head = add_degrees(spec.head, (-1.0 + 1.0 * bounce, -5.0 - 2.0 * math.sin(2.0 * math.pi * (3.0 * phase - 0.18)), 3.0))
    right = spec.arms[".R"]
    skeleton = rig.skeleton
    pose = compose(rig, spec)
    world, heads = forward_kinematics(skeleton, pose)
    chest_inverse = world["chest"].inverted()
    shoulder = chest_inverse @ (heads["upper_arm.R"] - heads["chest"])
    elbow = shoulder + Vector((-0.92, -0.3, 0.12 + 0.03 * bounce)).normalized() * skeleton.length("upper_arm.R")
    forearm = Quaternion(Vector((0.0, -1.0, 0.0)), math.radians(-22.0 * swing)) @ Vector((-0.15, -0.15, 0.97)).normalized()
    right.wrist = elbow + forearm * skeleton.length("forearm.R")
    right.pole = Vector((-0.4, 0.3, -0.85))
    palm_tilt = Quaternion(Vector((0.0, -1.0, 0.0)), math.radians(-16.0 * trail))
    right.aim = (palm_tilt @ forearm, palm_tilt @ Vector((-0.1, -1.0, 0.05)))
    right.finger_curls = finger_fan(2.0, 3.0, 4.0, 3.0 * phase - 0.15, 0.06)
    right.splay = 10.0
    right.thumb = 6.0
    right.shoulder = (0.0, 6.0 + 1.5 * bounce, 0.0)
    left = spec.arms[".L"]
    left.wrist = Vector((0.06, -0.15, -0.16 + 0.008 * bounce))
    left.pole = Vector((0.8, 0.5, -0.4))
    left.aim = ((-0.5, -0.4, 0.6), (-0.5, 0.8, 0.2))
    left.aim_weight = 0.8
    left.finger_curls = finger_fan(22.0, 8.0, 3.0, phase)
    left.thumb = 25.0
    return spec


SHY_FEET = {".L": (-0.023, -0.012, -6.0, 0.0), ".R": (0.018, -0.032, 10.0, 0.0)}


SHY_GLANCE = Curve([(0, 0.0), (52, 0.0), (60, 1.0), (74, 1.0), (82, 0.0), (120, 0.0)], period=120.0)


def clip_idle_shy(rig: CharacterRig, frame: float) -> BodySpec:
    """Weight on the left leg, knees drawn together, the right toe turned in and rocking, the fingers twiddling in the
    clasped hands, the head down; once a loop he peeks up and ducks back."""
    phase = frame / 120.0
    sway = math.sin(2.0 * math.pi * phase)
    fidget = math.sin(2.0 * math.pi * 2.0 * phase)
    glance = SHY_GLANCE.scalar(frame)
    spec = acting_idle(rig, frame, 120.0)
    x, y, yaw, pitch = SHY_FEET[".R"]
    rock = 0.5 - 0.5 * math.cos(2.0 * math.pi * 3.0 * phase)
    spec.feet = rig_feet(rig, {**SHY_FEET, ".R": (x, y, yaw + 4.0 * rock, pitch + 9.0 * rock)})
    spec.hips_offset = Vector((0.016 + 0.005 * sway, 0.004, -0.022 - 0.002 * rock))
    spec.hips = (1.0, -3.0 + 0.8 * sway, 2.0)
    spec.spine = (2.0, 2.0, -1.5)
    spec.chest = (3.0 - 1.0 * glance, 1.5 + 0.5 * math.sin(2.0 * math.pi * (phase - 0.08)), -1.0)
    spec.neck = (3.0 - 3.0 * SHY_GLANCE.scalar(frame - 2.0), 2.0, 2.0)
    spec.head = (5.0 + 0.8 * fidget - 9.0 * glance, 6.0 + 0.8 * math.sin(2.0 * math.pi * (phase - 0.16)) - 2.0 * glance,
                 6.0 + 1.5 * math.sin(2.0 * math.pi * (phase - 0.2)))
    for side in SIDES:
        arm = spec.arms[side]
        arm.shoulder = (0.0, 4.0 + 1.0 * glance, -4.0)
        arm.wrist = Vector((side_sign(side) * 0.018, -0.14 + 0.004 * fidget, -0.265 + side_sign(side) * 0.008))
        arm.pole = Vector((side_sign(side) * 0.8, 0.5, -0.3))
        arm.aim = ((-side_sign(side) * 0.55, -0.35, -0.75), (-side_sign(side) * 0.75, 0.55, -0.2))
        twiddle = 3.0 * phase * 2.0 + (0.0 if side == ".L" else 0.5)
        arm.finger_curls = finger_fan(30.0, 5.0, 10.0, twiddle, 0.1)
        arm.thumb = 25.0 + 12.0 * math.sin(2.0 * math.pi * twiddle)
    spec.skirt_sway = 0.8 * sway
    return spec


PLAYFUL_FEET = {".L": (-0.013, -0.012, 8.0, 0.0), ".R": (0.023, 0.058, -14.0, 30.0)}


def clip_idle_playful(rig: CharacterRig, frame: float) -> BodySpec:
    """Hips tilted, the right heel up, hands behind the back, a light bounce and a tilted head."""
    phase = frame / 90.0
    bounce = 0.5 - 0.5 * math.cos(2.0 * math.pi * 3.0 * phase)
    sway = math.sin(2.0 * math.pi * phase)
    spec = acting_idle(rig, frame, 90.0)
    x, y, yaw, pitch = PLAYFUL_FEET[".R"]
    spec.feet = rig_feet(rig, {**PLAYFUL_FEET, ".R": (x, y, yaw, pitch + 6.0 * bounce)})
    spec.hips_offset = Vector((0.020 + 0.004 * sway, 0.006, -0.018 - 0.008 * bounce))
    spec.hips = (0.0, 6.0, 3.0 + 2.0 * sway)
    spec.spine = (-1.0, -3.0, -2.0)
    spec.chest = (-2.0, -2.0 + 0.8 * math.sin(2.0 * math.pi * (phase - 0.06)), -2.0 * math.sin(2.0 * math.pi * (phase - 0.06)))
    spec.neck = (0.0, -3.0, 2.0)
    # The head rides the bounce a beat late and swings its tilt against the hips.
    late_bounce = 0.5 - 0.5 * math.cos(2.0 * math.pi * 3.0 * (phase - 0.04))
    spec.head = (1.5 - 1.5 * late_bounce, -10.0 + 2.0 * math.sin(2.0 * math.pi * (phase - 0.15)),
                 4.0 + 2.5 * math.sin(2.0 * math.pi * (phase - 0.12)))
    for side in SIDES:
        arm = spec.arms[side]
        arm.wrist = Vector((side_sign(side) * 0.03, 0.16, -0.275 + 0.006 * bounce))
        arm.pole = Vector((side_sign(side) * 0.9, 0.2, 0.3))
        arm.aim = ((-side_sign(side) * 0.6, 0.25, -0.75), (-side_sign(side) * 0.3, 0.9, 0.2))
        arm.finger_curls = finger_fan(40.0, 6.0, 4.0, 3.0 * phase, 0.08)
        arm.thumb = 20.0
        arm.shoulder = (0.0, 2.0 * late_bounce, 3.0)
    spec.skirt_sway = 2.0 * sway
    return spec


CONFIDENT_POP = Curve([(0, 0.0), (48, 0.0), (58, 1.0), (70, 0.8), (88, 0.0), (120, 0.0)], period=120.0)
CONFIDENT_FEET = {".L": (0.037, -0.087, 18.0, 0.0), ".R": (0.028, -0.007, -9.0, 0.0)}


def clip_idle_confident(rig: CharacterRig, frame: float) -> BodySpec:
    """Weight on the right leg, the left hand on the hip, the chin up."""
    phase = frame / 120.0
    sway = math.sin(2.0 * math.pi * phase)
    spec = acting_idle(rig, frame, 120.0)
    spec.feet = rig_feet(rig, CONFIDENT_FEET)
    # A slow rock onto the standing leg with a small hip pop at its far end.
    pop = CONFIDENT_POP.scalar(frame)
    spec.hips_offset = Vector((-0.024 + 0.004 * sway - 0.006 * pop, 0.0, -0.02 - 0.002 * pop))
    spec.hips = (0.0, 4.5 + 1.5 * pop, -5.0)
    spec.spine = (-1.5, -2.5 - 1.0 * CONFIDENT_POP.scalar(frame - 3.0), 3.0)
    spec.chest = (-2.0, -2.0 + 0.5 * sway, 2.0)
    spec.neck = (-2.0, 1.0, -1.0)
    spec.head = (-6.0 + 1.0 * sway, 3.0, -4.0 + 2.0 * math.sin(2.0 * math.pi * (phase - 0.3)))
    left = spec.arms[".L"]
    left.wrist = Vector((0.150, 0.012, -0.200))
    left.pole = Vector((0.9, 0.35, 0.1))
    left.aim = ((-0.25, -0.5, -0.8), (-0.9, 0.2, 0.0))
    left.finger_curls = finger_fan(6.0, 5.0, 2.0, phase)
    left.thumb = 25.0
    left.splay = 3.0
    right = spec.arms[".R"]
    right.adduct = 18.0
    right.swing = 3.0 + 1.0 * sway
    right.elbow = 12.0
    spec.skirt_sway = -1.0 + 0.6 * sway
    return spec


# ---------------------------------------------------------------------------------------------------

def target_clips(rig: CharacterRig, braid: BraidLayout, braid_resting: animation.SkirtResting | None = None) -> list:
    """(name, frame count, loops, poses) for every target clip."""
    walk = WalkCycle(rig.skeleton, WALK)
    notice = {name: Curve(keys) for name, keys in NOTICE_KEYS.items()}
    startled = startled_curves(rig)
    sit_down = sit_down_curves(rig)
    braid_curves = fix_braid_curves(rig)
    stand_up = stand_up_curves(rig)
    can_curls = wrap_curls(rig.skeleton, ".R", "can")
    broom_curls = {side: wrap_curls(rig.skeleton, side, "broom") for side in SIDES}
    print(f"wrapping curls: can {can_curls}, broom {broom_curls}")
    clips = [
        ("target_idle", 90, True, lambda frame: clip_idle(rig, frame)),
        ("target_walk_routine", WALK.frame_count, True, lambda frame: clip_walk(rig, frame, walk)),
        ("target_notice_player", 30, False, lambda frame: clip_notice_player(rig, frame, notice)),
        ("target_startled", 20, False, lambda frame: clip_startled(rig, frame, startled)),
        ("target_look_around", 120, True, lambda frame: clip_look_around(rig, frame)),
        ("target_sit_down", 30, False,
         lambda frame: clip_sit_transition(rig, frame, sit_down, SIT_DOWN_HANDS, SIT_DOWN_SLIDE, SIT_DOWN_GLANCE)),
        ("target_stand_up", 30, False,
         lambda frame: clip_sit_transition(rig, frame, stand_up, STAND_UP_HANDS, STAND_UP_SLIDE)),
        ("target_sit", 90, True, lambda frame: clip_sit(rig, frame)),
        ("target_sit_read", 120, True, lambda frame: clip_sit_read(rig, frame)),
        ("target_phone", 120, True, lambda frame: clip_phone(rig, frame)),
        ("target_drink", 120, True, lambda frame: clip_drink(rig, frame, can_curls)),
        ("target_fix_braid", 150, True, lambda frame: clip_fix_braid(rig, frame, braid_curves, braid)),
        ("target_lean_chat", 120, True, lambda frame: clip_lean_chat(rig, frame)),
        ("target_sweep", 60, True, lambda frame: clip_sweep(rig, frame, broom_curls)),
        ("target_wave", 45, True, lambda frame: clip_wave(rig, frame)),
        ("target_idle_shy", 120, True, lambda frame: clip_idle_shy(rig, frame)),
        ("target_idle_playful", 90, True, lambda frame: clip_idle_playful(rig, frame)),
        ("target_idle_confident", 120, True, lambda frame: clip_idle_confident(rig, frame)),
    ]
    skirt_bones = [bone for chain in rig.skeleton.chains(animation.SKIRT_PREFIX) for bone in chain]
    composed = []
    for name, frame_count, loops, body in clips:
        poses = poses_for(rig, frame_count, body)
        animation.smooth_rotations(poses, skirt_bones, loops)
        if braid_resting is not None:
            braid_resting.apply(poses, loops)
        composed.append((name, frame_count, loops, poses))
    return composed


def build_target_actions(armature, stance: Stance, braid: BraidLayout) -> list:
    """Key every target clip onto `armature` (one muted NLA track each) and leave it in its rest pose."""
    rig = CharacterRig(armature, stance)
    prefix = armature.name.removesuffix("Char")
    # The braid's lower bones swing out so the plait and its bow rest on the skirt; samples cover the hair hanging at
    # skirt height and the bow.
    braid_resting = animation.SkirtResting(
        armature, rig.skeleton, bpy.data.objects[f"{prefix}Skirt"], [bpy.data.objects[name] for name in braid.meshes],
        braid.resting_bones + braid.bow_bones, braid.resting_bones)
    actions = []
    for name, frame_count, loops, poses in target_clips(rig, braid, braid_resting):
        actions.append(animation.build_clip(armature, rig.skeleton, name, frame_count, loops, poses))
    armature.animation_data.action = None
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pose_bone.location = (0.0, 0.0, 0.0)
    return actions
