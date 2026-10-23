"""Shared body composition for every character: stance settings, body specs and the pose composer.

A clip fills a `BodySpec` per frame, and `compose` turns it into a `Pose`: IK-planted feet, IK or FK
arms, hand aiming, finger curls and the skirt follow. Everything that depends on a character's build
lives in its `Stance` (foot placement, seat clearance, idle angles, lap offset, mouth). Every landmark
(idle wrists, seated hips, lap) is measured on the character's own rig, so the same clip code animates
characters of other heights. IK wrist targets are in chest space: they ride along with the torso.
"""

import math
from dataclasses import dataclass, field, replace
from typing import Callable

from mathutils import Quaternion, Vector

from .animation import (
    FORWARD, SIDES, UP, Curve, FootGeometry, Pose, Skeleton, WalkCycle, aligning_rotation, bend,
    curl_fingers, degrees, follow_skirt, forward_kinematics, hang, idle_breathing, lerp, mirrored_degrees, palm_normal,
    place_leg, reach_arm, set_world_rotation, share_twist, side_sign, sit_pose, smoothstep, world_point,
)

LAP_POLE = Vector((0.6, 0.6, -0.3))


def add_degrees(first_rotation: tuple, second_rotation: tuple) -> tuple:
    return tuple(first_value + second_value for first_value, second_value in zip(first_rotation, second_rotation))


@dataclass
class ArmSpec:
    """One arm. FK by default (degrees). A `wrist` target switches to IK.

    `wrist` is a chest-space point (world space with `world_space`), or a callable that receives the pose
    being composed and returns one; use the callable for targets tied to a moving landmark such as the mouth.
    """

    adduct: float = 23.0
    swing: float = 5.0
    elbow: float = 20.0
    wrist: Vector | Callable[[Pose], Vector] | None = None
    pole: Vector | None = None
    world_space: bool = False
    hand: tuple = (0.0, -2.0, 0.0)
    aim: tuple | None = None
    aim_weight: float = 1.0
    fingers: float = 18.0
    thumb: float = 10.0
    shoulder: tuple = (0.0, 0.0, 0.0)


@dataclass
class Stance:
    """Per-character settings for the shared standing and seated stances."""

    idle_feet: dict
    # Rest-pose armature-space mouth position, measured on the face mesh (it differs per head and height).
    mouth: Vector
    # Free-hanging chain bones (the lower braid) that keep hanging straight down however the torso and head turn.
    hanging_bones: tuple = ()
    idle_hips_offset: Vector = field(default_factory=Vector)
    idle_hips: tuple = (0.0, 0.0, 0.0)
    idle_spine: tuple = (0.0, 0.0, 0.0)
    idle_chest: tuple = (0.0, 0.0, 0.0)
    idle_neck: tuple = (0.0, 0.0, 0.0)
    idle_head: tuple = (0.0, 0.0, 0.0)
    idle_arm: ArmSpec = field(default_factory=ArmSpec)
    # The buttocks rest on a seat this high; the hip joints sit `seat_clearance` above the contact.
    seat_height: float = 0.45
    seat_clearance: float = 0.085
    seated_pelvis_tilt: float = -7.0
    seated_spine: tuple = (4.0, 0.0, 0.0)
    seated_chest: tuple = (3.0, 0.0, 0.0)
    seated_neck: tuple = (2.0, 0.0, 0.0)
    seated_head: tuple = (3.0, -2.0, 0.0)
    heel_back: float = 0.025
    # Resting wrist on the thigh: fraction along the thigh, then (inward, forward, up) metres.
    lap_fraction: float = 0.52
    lap_offset: Vector = field(default_factory=lambda: Vector((0.012, 0.0, 0.088)))


@dataclass
class BodySpec:
    hips_offset: Vector = field(default_factory=Vector)
    hips: tuple = (0.0, 0.0, 0.0)
    feet: dict | None = None
    spine: tuple = (0.0, 0.0, 0.0)
    chest: tuple = (0.0, 0.0, 0.0)
    neck: tuple = (0.0, 0.0, 0.0)
    head: tuple = (0.0, 0.0, 0.0)
    arms: dict = field(default_factory=lambda: {side: ArmSpec() for side in SIDES})
    breath_phase: float = 0.0
    breath_amount: float = 1.0
    skirt_sway: float = 0.0
    # Extra rest-axis rotations in degrees, for hair chains and similar secondary bones.
    extra_rotations: dict = field(default_factory=dict)
    gait: WalkCycle | None = None
    gait_frame: float = 0.0
    # Overrides the seated drape of the skirt (0..1); by default it follows the hips height.
    seated: float | None = None


class CharacterRig:
    def __init__(self, armature, stance: Stance):
        self.armature = armature
        self.stance = stance
        self.skeleton = Skeleton(armature)
        self.feet = {side: FootGeometry(self.skeleton, side, stance.heel_back) for side in SIDES}
        seated_reference = Pose()
        sit_pose(self.skeleton, seated_reference, stance.seat_height, stance.seat_clearance, stance.idle_feet, 0.0)
        self.seated_offset = seated_reference.offset("hips")
        idle = compose(self, self.standing_body())
        self.idle_wrists, self.idle_poles = self.arm_targets(idle)
        seated = compose(self, self.seated_body())
        self.lap_wrists = {side: self.to_chest_space(seated, self.lap_point(seated, side)) for side in SIDES}

    # Stances ----------------------------------------------------------------------------------------

    def standing_body(self) -> BodySpec:
        stance = self.stance
        return BodySpec(
            hips_offset=stance.idle_hips_offset.copy(), hips=stance.idle_hips, feet=dict(stance.idle_feet),
            spine=stance.idle_spine, chest=stance.idle_chest, neck=stance.idle_neck, head=stance.idle_head,
            arms={side: replace(stance.idle_arm) for side in SIDES},
        )

    def seated_body(self) -> BodySpec:
        stance = self.stance
        spec = self.standing_body()
        spec.hips_offset = self.seated_offset.copy()
        spec.hips = (stance.seated_pelvis_tilt, 0.0, 0.0)
        spec.spine, spec.chest = stance.seated_spine, stance.seated_chest
        spec.neck, spec.head = stance.seated_neck, stance.seated_head
        return spec

    def seated_hands(self, spec: BodySpec) -> None:
        """Hands resting palm-down on the thighs."""
        for side in SIDES:
            arm = spec.arms[side]
            arm.wrist = self.lap_wrists[side].copy()
            arm.pole = lap_pole(side)
            arm.aim = ((0.0, -0.85, -0.35), (-side_sign(side) * 0.15, 0.1, -1.0))
            arm.fingers = 22.0
            arm.thumb = 14.0

    def idle_body(self, frame: float, period: float) -> BodySpec:
        """The idle stance with breathing and a slow weight shift; one cycle per `period` frames."""
        stance = self.stance
        phase = frame / period
        wave = math.sin(2.0 * math.pi * phase)
        slow = math.sin(2.0 * math.pi * (phase - 0.15))
        spec = self.standing_body()
        spec.breath_phase = phase * max(1, round(period / 90.0))
        spec.hips_offset = stance.idle_hips_offset + Vector((0.004 * wave, 0.0, -0.002 * (0.5 + 0.5 * wave)))
        spec.hips = add_degrees(stance.idle_hips, (0.0, -0.8 * wave, 0.6 * slow))
        spec.spine = add_degrees(stance.idle_spine, (0.0, 0.5 * wave, -0.4 * slow))
        spec.chest = add_degrees(stance.idle_chest, (0.0, 0.3 * wave, -0.3 * slow))
        spec.head = add_degrees(stance.idle_head, (0.8 * math.sin(4.0 * math.pi * phase), 0.6 * slow,
                                                   2.5 * math.sin(2.0 * math.pi * (phase - 0.3))))
        for side in SIDES:
            lag = 0.08 if side == ".L" else 0.12
            arm = spec.arms[side]
            arm.swing += 0.8 * math.sin(2.0 * math.pi * (phase - lag))
            arm.elbow += 1.2 * math.sin(2.0 * math.pi * (phase - lag - 0.05))
        spec.skirt_sway = -0.6 * math.cos(2.0 * math.pi * (phase - 0.1))
        return spec

    def seated_idle(self, frame: float, period: float) -> BodySpec:
        phase = frame / period
        spec = self.seated_body()
        spec.breath_phase = phase * max(1, round(period / 90.0))
        sway = math.sin(2.0 * math.pi * phase)
        spec.spine = add_degrees(spec.spine, (0.0, 0.6 * sway, 0.5 * math.sin(2.0 * math.pi * (phase - 0.2))))
        spec.head = add_degrees(spec.head, (0.8 * math.sin(4.0 * math.pi * phase), 0.8 * sway,
                                            3.0 * math.sin(2.0 * math.pi * (phase - 0.35))))
        self.seated_hands(spec)
        return spec

    def seated_factor(self, hips_height: float) -> float:
        """0 standing, 1 once the hips are actually down on the seat (not while crouching above it)."""
        idle_height = self.stance.idle_hips_offset.z
        seated_height = self.seated_offset.z
        return smoothstep(lerp(idle_height, seated_height, 0.8), seated_height, hips_height)

    # Landmarks --------------------------------------------------------------------------------------

    def chest_frame(self, pose: Pose) -> tuple[Vector, Quaternion]:
        world, heads = forward_kinematics(self.skeleton, pose)
        return heads["chest"], world["chest"]

    def to_chest_space(self, pose: Pose, point: Vector) -> Vector:
        origin, rotation = self.chest_frame(pose)
        return rotation.inverted() @ (point - origin)

    def landmark(self, pose: Pose, bone: str, rest_point: Vector) -> Vector:
        """A rest-pose point carried by `bone` in `pose`, in chest space."""
        world, heads = forward_kinematics(self.skeleton, pose)
        return world["chest"].inverted() @ (world_point(self.skeleton, world, heads, bone, rest_point) - heads["chest"])

    def mouth(self, pose: Pose) -> Vector:
        return self.landmark(pose, "head", self.stance.mouth)

    def arm_targets(self, pose: Pose) -> tuple[dict, dict]:
        """Wrist positions and elbow poles of a pose, in chest space."""
        world, heads = forward_kinematics(self.skeleton, pose)
        origin, rotation = heads["chest"], world["chest"]
        inverse = rotation.inverted()
        wrists, poles = {}, {}
        for side in SIDES:
            shoulder = heads[f"upper_arm{side}"]
            elbow = heads[f"forearm{side}"]
            wrist = heads[f"hand{side}"]
            line = (wrist - shoulder).normalized()
            pole = elbow - shoulder - line * (elbow - shoulder).dot(line)
            wrists[side] = inverse @ (wrist - origin)
            poles[side] = inverse @ pole.normalized()
        return wrists, poles

    def lap_point(self, pose: Pose, side: str) -> Vector:
        _, heads = forward_kinematics(self.skeleton, pose)
        hip = heads[f"thigh{side}"]
        knee = heads[f"shin{side}"]
        offset = self.stance.lap_offset
        return hip.lerp(knee, self.stance.lap_fraction) + Vector((-side_sign(side) * offset.x, offset.y, offset.z))


def lap_pole(side: str) -> Vector:
    return Vector((side_sign(side) * LAP_POLE.x, LAP_POLE.y, LAP_POLE.z))


def compose(rig: CharacterRig, spec: BodySpec) -> Pose:
    skeleton = rig.skeleton
    pose = Pose()
    pose.rotations["hips"] = degrees(*spec.hips)
    if spec.gait is not None:
        spec.gait.apply_lower_body(pose, spec.gait_frame)
    else:
        pose.offsets["hips"] = spec.hips_offset.copy()
        feet = spec.feet or rig.stance.idle_feet
        for side in SIDES:
            place_leg(skeleton, pose, side, rig.feet[side], feet[side])
    pose.rotations["spine"] = degrees(*spec.spine)
    pose.rotations["chest"] = degrees(*spec.chest)
    pose.rotations["neck"] = degrees(*spec.neck)
    pose.rotations["head"] = degrees(*spec.head)
    idle_breathing(pose, spec.breath_phase, spec.breath_amount)
    # Secondary bones first, so hand targets carried by them (the braid) see their final pose.
    for bone, rotation in spec.extra_rotations.items():
        pose.rotations[bone] = degrees(*rotation)
    hang(skeleton, pose, tuple(bone for bone in rig.stance.hanging_bones if bone not in spec.extra_rotations))
    for side in SIDES:
        arm = spec.arms[side]
        pose.turn(f"shoulder{side}", mirrored_degrees(side, *arm.shoulder))
        _pose_arm(rig, pose, side, arm)
    if spec.seated is not None:
        seated = spec.seated
    else:
        seated = 0.0 if spec.gait is not None else rig.seated_factor(spec.hips_offset.z)
    follow_skirt(skeleton, pose, spec.skirt_sway, seated)
    return pose


def _pose_arm(rig: CharacterRig, pose: Pose, side: str, arm: ArmSpec) -> None:
    skeleton = rig.skeleton
    if arm.wrist is None:
        pose.rotations[f"upper_arm{side}"] = Quaternion()
        bend(skeleton, pose, f"upper_arm{side}", arm.adduct, -UP)
        pose.turn(f"upper_arm{side}", degrees(x=-arm.swing))
        pose.rotations[f"forearm{side}"] = Quaternion()
        bend(skeleton, pose, f"forearm{side}", arm.elbow, FORWARD)
    else:
        wrist = arm.wrist(pose) if callable(arm.wrist) else arm.wrist
        origin, rotation = rig.chest_frame(pose)
        target = wrist if arm.world_space else origin + rotation @ wrist
        pole = arm.pole if arm.world_space else rotation @ arm.pole
        reach_arm(skeleton, pose, side, target, pole)
    pose.rotations[f"hand{side}"] = mirrored_degrees(side, *arm.hand)
    if arm.aim is not None and arm.aim_weight > 0.0:
        world, _ = forward_kinematics(skeleton, pose)
        _, chest_rotation = rig.chest_frame(pose)
        fingers, palm = (Vector(arm.aim[0]), Vector(arm.aim[1]))
        if not arm.world_space:
            fingers, palm = chest_rotation @ fingers, chest_rotation @ palm
        aimed = aligning_rotation(skeleton.direction(f"hand{side}"), palm_normal(skeleton, side), fingers, palm)
        current = world[f"forearm{side}"] @ pose.rotation(f"hand{side}")
        if current.dot(aimed) < 0.0:
            aimed.negate()
        set_world_rotation(skeleton, pose, f"hand{side}", current.slerp(aimed, arm.aim_weight))
        share_twist(skeleton, pose, f"forearm{side}", f"hand{side}", 0.5)
    curl_fingers(skeleton, pose, side, arm.fingers, arm.thumb)


# ---------------------------------------------------------------------------------------------------
# Sitting down and standing up: keyed as fractions of the way from the idle hips to the seated hips,
# so the arc fits any character's height and seat.

def _toward_seat(rig: CharacterRig, keys: list, axis: int) -> Curve:
    start = rig.stance.idle_hips_offset[axis]
    seated = rig.seated_offset[axis]
    return Curve([(frame, start + (seated - start) * fraction) for frame, fraction in keys])


def sit_down_curves(rig: CharacterRig) -> dict:
    stance = rig.stance
    idle_x = stance.idle_hips_offset.x
    curves = {
        "hips_y": _toward_seat(rig, [(0, 0.0), (6, 0.132), (14, 0.528), (21, 0.87), (26, 0.987), (30, 1.0)], 1),
        "hips_z": _toward_seat(rig, [(0, 0.0), (6, 0.088), (14, 0.417), (21, 0.794), (25, 0.975), (27, 1.013), (30, 1.0)], 2),
        "hips_x": Curve([(0, idle_x), (14, 0.36 * idle_x), (30, 0.0)]),
        "hips_pitch": Curve([(0, stance.idle_hips[0]), (8, 12.0), (15, 18.0), (22, 8.0),
                             (27, stance.seated_pelvis_tilt - 1.0), (30, stance.seated_pelvis_tilt)]),
        "hips_roll": Curve([(0, stance.idle_hips[1]), (14, -1.0), (30, 0.0)]),
        "hips_yaw": Curve([(0, stance.idle_hips[2]), (16, 0.5), (30, 0.0)]),
        "spine_pitch": Curve([(0, stance.idle_spine[0]), (8, 7.0), (15, 12.0), (22, 10.0),
                              (27, stance.seated_spine[0] + 1.0), (30, stance.seated_spine[0])]),
        "chest_pitch": Curve([(0, stance.idle_chest[0]), (8, 5.0), (15, 9.0), (22, 7.0), (28, stance.seated_chest[0]),
                              (30, stance.seated_chest[0])]),
        "spine_roll": Curve([(0, stance.idle_spine[1]), (16, 0.5), (30, stance.seated_spine[1])]),
        "chest_roll": Curve([(0, stance.idle_chest[1]), (16, 0.5), (30, stance.seated_chest[1])]),
        "neck_pitch": Curve([(0, stance.idle_neck[0]), (12, -6.0), (22, -4.0), (30, stance.seated_neck[0])]),
        "head_pitch": Curve([(0, stance.idle_head[0]), (12, -4.0), (22, -2.0), (30, stance.seated_head[0])]),
        "neck_roll": Curve([(0, stance.idle_neck[1]), (30, stance.seated_neck[1])]),
        "head_roll": Curve([(0, stance.idle_head[1]), (30, stance.seated_head[1])]),
        "aim": Curve([(0, 0.0), (14, 0.3), (26, 1.0), (30, 1.0)]),
        "fingers": Curve([(0, stance.idle_arm.fingers), (30, 22.0)]),
    }
    for side in SIDES:
        idle_wrist = rig.idle_wrists[side]
        lap = rig.lap_wrists[side]
        reach_out = idle_wrist.lerp(lap, 0.45) + Vector((side_sign(side) * 0.03, -0.05, 0.02))
        curves[f"wrist{side}"] = Curve([(0, idle_wrist), (13, reach_out), (24, lap + Vector((0.0, 0.0, 0.015))), (30, lap)])
        curves[f"pole{side}"] = Curve([(0, rig.idle_poles[side]), (30, lap_pole(side))])
    return curves


def stand_up_curves(rig: CharacterRig) -> dict:
    """Not a mirror of sitting down: the trunk leans forward first, then the body rises over the feet."""
    stance = rig.stance
    idle_x = stance.idle_hips_offset.x
    curves = {
        "hips_y": _toward_seat(rig, [(0, 1.0), (5, 0.974), (11, 0.87), (18, 0.448), (24, 0.106), (30, 0.0)], 1),
        "hips_z": _toward_seat(rig, [(0, 1.0), (6, 0.987), (11, 0.888), (18, 0.417), (24, 0.072), (30, 0.0)], 2),
        "hips_x": Curve([(0, 0.0), (18, 0.45 * idle_x), (30, idle_x)]),
        # The lean comes mostly from spine and chest, so the pelvis does not lift the skirt off the seat.
        "hips_pitch": Curve([(0, stance.seated_pelvis_tilt), (6, 2.0), (11, 15.0), (18, 12.0), (25, 2.0),
                             (30, stance.idle_hips[0])]),
        "hips_roll": Curve([(0, 0.0), (18, -1.0), (30, stance.idle_hips[1])]),
        "hips_yaw": Curve([(0, 0.0), (18, 0.5), (30, stance.idle_hips[2])]),
        "spine_pitch": Curve([(0, stance.seated_spine[0]), (6, 14.0), (11, 17.0), (18, 9.0), (25, 3.0),
                              (30, stance.idle_spine[0])]),
        "chest_pitch": Curve([(0, stance.seated_chest[0]), (6, 11.0), (11, 12.0), (18, 6.0), (25, 1.5),
                              (30, stance.idle_chest[0])]),
        "spine_roll": Curve([(0, stance.seated_spine[1]), (18, 0.8), (30, stance.idle_spine[1])]),
        "chest_roll": Curve([(0, stance.seated_chest[1]), (18, 0.8), (30, stance.idle_chest[1])]),
        "neck_pitch": Curve([(0, stance.seated_neck[0]), (8, -5.0), (18, -4.0), (30, stance.idle_neck[0])]),
        "head_pitch": Curve([(0, stance.seated_head[0]), (8, -3.0), (18, -2.0), (30, stance.idle_head[0])]),
        "neck_roll": Curve([(0, stance.seated_neck[1]), (30, stance.idle_neck[1])]),
        "head_roll": Curve([(0, stance.seated_head[1]), (30, stance.idle_head[1])]),
        "aim": Curve([(0, 1.0), (6, 1.0), (16, 0.4), (28, 0.0), (30, 0.0)]),
        "fingers": Curve([(0, 22.0), (30, stance.idle_arm.fingers)]),
    }
    for side in SIDES:
        idle_wrist = rig.idle_wrists[side]
        lap = rig.lap_wrists[side]
        push = lap + Vector((0.0, -0.02, -0.01))
        curves[f"wrist{side}"] = Curve([(0, lap), (7, push), (14, lap.lerp(idle_wrist, 0.4) + Vector((0.0, -0.04, 0.0))),
                                        (30, idle_wrist)])
        curves[f"pole{side}"] = Curve([(0, lap_pole(side)), (30, rig.idle_poles[side])])
    return curves


def sit_transition_body(rig: CharacterRig, frame: float, curves: dict) -> BodySpec:
    """One frame of `sit_down_curves` or `stand_up_curves`; the feet stay planted throughout."""
    spec = rig.seated_body()
    spec.breath_phase = frame / 90.0
    spec.hips_offset = Vector((curves["hips_x"].scalar(frame), curves["hips_y"].scalar(frame), curves["hips_z"].scalar(frame)))
    spec.hips = (curves["hips_pitch"].scalar(frame), curves["hips_roll"].scalar(frame), curves["hips_yaw"].scalar(frame))
    spec.spine = (curves["spine_pitch"].scalar(frame), curves["spine_roll"].scalar(frame), 0.0)
    spec.chest = (curves["chest_pitch"].scalar(frame), curves["chest_roll"].scalar(frame), 0.0)
    spec.neck = (curves["neck_pitch"].scalar(frame), curves["neck_roll"].scalar(frame), 0.0)
    spec.head = (curves["head_pitch"].scalar(frame), curves["head_roll"].scalar(frame), 0.0)
    rig.seated_hands(spec)
    for side in SIDES:
        arm = spec.arms[side]
        arm.wrist = curves[f"wrist{side}"].vector(frame)
        arm.pole = curves[f"pole{side}"].vector(frame)
        arm.aim_weight = curves["aim"].scalar(frame)
        arm.fingers = curves["fingers"].scalar(frame)
    return spec


def poses_for(rig: CharacterRig, frame_count: int, body: Callable[[float], BodySpec]) -> list:
    return [compose(rig, body(frame)) for frame in range(frame_count + 1)]
