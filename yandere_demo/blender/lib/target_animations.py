"""The target's animation library: fifteen in-place clips at 30 fps.

Every clip is a function of the frame that fills a `BodySpec`; `compose` turns the spec into a pose
(IK feet, IK or FK arms, skirt follow) and `build_target_actions` keys each frame. Standing clips share
the idle stance and seated clips share the seated stance, so the 0.3 s crossfades in Godot meet
matching poses. Feet are solved with IK against fixed ground placements, so they never slide.
"""

import math
from dataclasses import dataclass, field

from mathutils import Quaternion, Vector

from . import animation
from .animation import (
    FORWARD, SIDES, UP, Curve, FootGeometry, FootPlacement, GaitParams, Pose, Skeleton, WalkCycle, aligning_rotation,
    bend, curl_fingers, degrees, follow_skirt, forward_kinematics, idle_breathing, lerp, mirrored_degrees,
    palm_normal, place_leg, reach_arm, set_world_rotation, share_twist, side_sign, sit_pose, smoothstep,
)

# Seat surface height of benches and chairs; the buttocks rest on it.
SEAT_HEIGHT = 0.45
# Height of the hip joints above the seat contact when seated (measured on the posed body mesh).
SEAT_CLEARANCE = 0.085
WALK = GaitParams(speed=1.3, frame_count=32)

IDLE_FEET = {
    ".L": FootPlacement(0.074, 0.004, 7.0),
    ".R": FootPlacement(-0.082, -0.036, -12.0),
}
IDLE_HIPS_OFFSET = Vector((0.011, 0.0, -0.017))
IDLE_HIPS = (0.0, -2.5, 1.5)
IDLE_SPINE = (1.0, 1.8, -0.8)
IDLE_CHEST = (0.5, 1.6, -0.5)
IDLE_NECK = (1.0, -0.8, 0.0)
IDLE_HEAD = (2.0, -2.5, 0.0)
SEATED_PELVIS_TILT = -7.0
SEATED_SPINE = (4.0, 0.0, 0.0)
SEATED_CHEST = (3.0, 0.0, 0.0)


def _add(first: tuple, second: tuple) -> tuple:
    return tuple(a + b for a, b in zip(first, second))


@dataclass
class ArmSpec:
    """One arm. FK by default (degrees); a `wrist` target (chest space unless `world_space`) switches to IK."""

    adduct: float = 23.0
    swing: float = 5.0
    elbow: float = 20.0
    wrist: Vector | None = None
    pole: Vector | None = None
    world_space: bool = False
    hand: tuple = (0.0, -2.0, 0.0)
    aim: tuple | None = None
    aim_weight: float = 1.0
    fingers: float = 18.0
    thumb: float = 10.0
    shoulder: tuple = (0.0, 0.0, 0.0)


@dataclass
class BodySpec:
    hips_offset: Vector = field(default_factory=lambda: IDLE_HIPS_OFFSET.copy())
    hips: tuple = IDLE_HIPS
    feet: dict = field(default_factory=lambda: dict(IDLE_FEET))
    spine: tuple = IDLE_SPINE
    chest: tuple = IDLE_CHEST
    neck: tuple = IDLE_NECK
    head: tuple = IDLE_HEAD
    arms: dict = field(default_factory=lambda: {side: ArmSpec() for side in SIDES})
    breath_phase: float = 0.0
    breath_amount: float = 1.0
    skirt_sway: float = 0.0
    braid: dict = field(default_factory=dict)
    gait: WalkCycle | None = None
    gait_frame: float = 0.0


class TargetRig:
    def __init__(self, armature):
        self.armature = armature
        self.skeleton = Skeleton(armature)
        self.feet = {side: FootGeometry(self.skeleton, side, heel_back=0.025) for side in SIDES}
        idle = compose(self, BodySpec())
        self.idle_wrists, self.idle_poles = self.arm_targets(idle)
        seated_spec = seated_body()
        seated_spec.hips_offset = seated_hips_offset(self)
        self.seated_offset = seated_spec.hips_offset.copy()
        seated = compose(self, seated_spec)
        self.lap_wrists = {side: self.to_chest_space(seated, self.lap_point(seated, side)) for side in SIDES}
        self.seated_wrists, self.seated_poles = self.arm_targets(seated)

    def chest_frame(self, pose: Pose) -> tuple[Vector, Quaternion]:
        world, heads = forward_kinematics(self.skeleton, pose)
        return heads["chest"], world["chest"]

    def to_chest_space(self, pose: Pose, point: Vector) -> Vector:
        origin, rotation = self.chest_frame(pose)
        return rotation.inverted() @ (point - origin)

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
        """Resting wrist on top of the thigh, a little past mid-thigh."""
        world, heads = forward_kinematics(self.skeleton, pose)
        hip = heads[f"thigh{side}"]
        knee = heads[f"shin{side}"]
        return hip.lerp(knee, 0.52) + Vector((-side_sign(side) * 0.012, 0.0, 0.088))


def compose(rig: TargetRig, spec: BodySpec) -> Pose:
    skeleton = rig.skeleton
    pose = Pose()
    pose.rotations["hips"] = degrees(*spec.hips)
    if spec.gait is not None:
        spec.gait.apply_lower_body(pose, spec.gait_frame)
    else:
        pose.offsets["hips"] = spec.hips_offset.copy()
        for side in SIDES:
            place_leg(skeleton, pose, side, rig.feet[side], spec.feet[side])
    pose.rotations["spine"] = degrees(*spec.spine)
    pose.rotations["chest"] = degrees(*spec.chest)
    pose.rotations["neck"] = degrees(*spec.neck)
    pose.rotations["head"] = degrees(*spec.head)
    idle_breathing(pose, spec.breath_phase, spec.breath_amount)
    for side in SIDES:
        arm = spec.arms[side]
        pose.turn(f"shoulder{side}", mirrored_degrees(side, *arm.shoulder))
        _pose_arm(rig, pose, side, arm)
    for bone, rotation in spec.braid.items():
        pose.rotations[bone] = degrees(*rotation)
    # The skirt only drapes over the lap once she is actually down on the seat, not while crouching.
    seated = 0.0 if spec.gait is not None else smoothstep(-0.27, -0.336, spec.hips_offset.z)
    follow_skirt(skeleton, pose, spec.skirt_sway, seated)
    return pose


def _pose_arm(rig: TargetRig, pose: Pose, side: str, arm: ArmSpec) -> None:
    skeleton = rig.skeleton
    if arm.wrist is None:
        pose.rotations[f"upper_arm{side}"] = Quaternion()
        bend(skeleton, pose, f"upper_arm{side}", arm.adduct, -UP)
        pose.turn(f"upper_arm{side}", degrees(x=-arm.swing))
        pose.rotations[f"forearm{side}"] = Quaternion()
        bend(skeleton, pose, f"forearm{side}", arm.elbow, FORWARD)
    else:
        origin, rotation = rig.chest_frame(pose)
        target = arm.wrist if arm.world_space else origin + rotation @ arm.wrist
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
    pose.rotations[f"fingers{side}"] = Quaternion()
    pose.rotations[f"thumb{side}"] = Quaternion()
    curl_fingers(skeleton, pose, side, arm.fingers, arm.thumb)


# ---------------------------------------------------------------------------------------------------
# Shared stances

def idle_body(frame: float, period: float) -> BodySpec:
    """The idle stance with breathing and a slow weight shift; one cycle per `period` frames."""
    phase = frame / period
    wave = math.sin(2.0 * math.pi * phase)
    slow = math.sin(2.0 * math.pi * (phase - 0.15))
    spec = BodySpec()
    spec.breath_phase = phase * max(1, round(period / 90.0))
    spec.hips_offset = IDLE_HIPS_OFFSET + Vector((0.004 * wave, 0.0, -0.002 * (0.5 + 0.5 * wave)))
    spec.hips = _add(IDLE_HIPS, (0.0, -0.8 * wave, 0.6 * slow))
    spec.spine = _add(IDLE_SPINE, (0.0, 0.5 * wave, -0.4 * slow))
    spec.chest = _add(IDLE_CHEST, (0.0, 0.3 * wave, -0.3 * slow))
    spec.head = _add(IDLE_HEAD, (0.8 * math.sin(4.0 * math.pi * phase), 0.6 * slow, 2.5 * math.sin(2.0 * math.pi * (phase - 0.3))))
    for side in SIDES:
        lag = 0.08 if side == ".L" else 0.12
        arm = spec.arms[side]
        arm.swing += 0.8 * math.sin(2.0 * math.pi * (phase - lag))
        arm.elbow += 1.2 * math.sin(2.0 * math.pi * (phase - lag - 0.05))
    spec.skirt_sway = -0.6 * math.cos(2.0 * math.pi * (phase - 0.1))
    return spec


def seated_hips_offset(rig: TargetRig) -> Vector:
    pose = Pose()
    sit_pose(rig.skeleton, pose, SEAT_HEIGHT, SEAT_CLEARANCE, IDLE_FEET, 0.0)
    return pose.offset("hips")


def seated_body() -> BodySpec:
    spec = BodySpec()
    spec.hips = (SEATED_PELVIS_TILT, 0.0, 0.0)
    spec.spine = SEATED_SPINE
    spec.chest = SEATED_CHEST
    spec.neck = (2.0, 0.0, 0.0)
    spec.head = (3.0, -2.0, 0.0)
    return spec


def seated_hands(rig: TargetRig, spec: BodySpec) -> None:
    """Hands resting palm-down on the thighs."""
    for side in SIDES:
        arm = spec.arms[side]
        arm.wrist = rig.lap_wrists[side].copy()
        arm.pole = Vector((side_sign(side) * 0.6, 0.6, -0.3))
        arm.aim = ((0.0, -0.85, -0.35), (-side_sign(side) * 0.15, 0.1, -1.0))
        arm.fingers = 22.0
        arm.thumb = 14.0


def seated_idle(rig: TargetRig, frame: float, period: float) -> BodySpec:
    phase = frame / period
    spec = seated_body()
    spec.hips_offset = rig.seated_offset.copy()
    spec.breath_phase = phase * max(1, round(period / 90.0))
    sway = math.sin(2.0 * math.pi * phase)
    spec.spine = _add(spec.spine, (0.0, 0.6 * sway, 0.5 * math.sin(2.0 * math.pi * (phase - 0.2))))
    spec.head = _add(spec.head, (0.8 * math.sin(4.0 * math.pi * phase), 0.8 * sway, 3.0 * math.sin(2.0 * math.pi * (phase - 0.35))))
    seated_hands(rig, spec)
    return spec


# ---------------------------------------------------------------------------------------------------
# Clips

def clip_idle(rig: TargetRig, frame: float) -> BodySpec:
    return idle_body(frame, 90.0)


def clip_walk(rig: TargetRig, frame: float, cycle: WalkCycle) -> BodySpec:
    phase = cycle.phase(frame)
    turn = math.cos(2.0 * math.pi * phase)
    roll = math.sin(2.0 * math.pi * (phase - 0.05))
    bob = math.cos(4.0 * math.pi * (phase - 0.06))
    spec = BodySpec()
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
        arm.hand = (4.0 * math.cos(2.0 * math.pi * (side_phase - 0.12)), -9.0, 0.0)
        arm.fingers = 20.0
        arm.thumb = 12.0
        arm.shoulder = (0.0, -2.0 + 1.5 * bob, 2.0 * math.cos(2.0 * math.pi * (side_phase - 0.05)))
    spec.skirt_sway = -2.5 * math.cos(2.0 * math.pi * (phase - 0.12))
    return spec


NOTICE_KEYS = {
    "hips_yaw": [(0, 0), (7, 6), (12, 9.5), (20, 8.5), (30, 8.5)],
    "spine_yaw": [(0, 0), (6, 5), (11, 8), (19, 7), (30, 7)],
    "chest_yaw": [(0, 0), (5, 5), (10, 7.5), (18, 6.5), (30, 6.5)],
    "neck_yaw": [(0, 0), (4, 4), (9, 6), (30, 5)],
    "chest_pitch": [(0, 0), (5, -3.5), (13, -1), (30, -1)],
    "shoulders": [(0, 0), (4, 7), (10, 4), (30, 1.5)],
    "elbow": [(0, 0), (6, 18), (13, 13), (30, 11)],
    "swing": [(0, 0), (6, 9), (30, 6)],
    "drop": [(0, 0), (6, -0.012), (16, -0.005), (30, -0.006)],
    "weight": [(0, 0), (10, 0.006), (30, 0.005)],
}


def clip_notice_player(rig: TargetRig, frame: float, curves: dict) -> BodySpec:
    spec = idle_body(frame, 90.0)
    value = {name: curve.scalar(frame) for name, curve in curves.items()}
    spec.hips_offset += Vector((value["weight"], 0.0, value["drop"]))
    spec.hips = _add(spec.hips, (0.0, 0.0, value["hips_yaw"]))
    spec.spine = _add(spec.spine, (0.0, 0.0, value["spine_yaw"]))
    spec.chest = _add(spec.chest, (value["chest_pitch"], 0.0, value["chest_yaw"]))
    spec.neck = _add(spec.neck, (0.0, 0.0, value["neck_yaw"]))
    for side in SIDES:
        arm = spec.arms[side]
        arm.shoulder = _add(arm.shoulder, (0.0, value["shoulders"], 0.0))
        arm.elbow += value["elbow"] * (1.0 if side == ".R" else 0.7)
        arm.swing += value["swing"]
        arm.fingers += value["elbow"] * 0.6
    return spec


def startled_curves(rig: TargetRig) -> dict:
    chest_left = Vector((0.065, -0.155, -0.02))
    chest_right = Vector((-0.045, -0.165, 0.03))
    curves = {
        "drop": Curve([(0, 0.0), (3, -0.026), (7, -0.036), (12, -0.028), (20, -0.03)]),
        "back": Curve([(0, 0.0), (4, 0.03), (9, 0.026), (20, 0.024)]),
        "spine_pitch": Curve([(0, 0.0), (3, -3.0), (8, -1.5), (20, -0.5)]),
        "chest_pitch": Curve([(0, 0.0), (3, -8.0), (7, -3.0), (12, -4.5), (20, -3.5)]),
        "head_pitch": Curve([(0, 0.0), (3, -6.0), (8, -1.0), (20, -2.0)]),
        "shoulders": Curve([(0, 0.0), (3, 12.0), (8, 9.0), (20, 8.0)]),
        "fingers": Curve([(0, 18.0), (4, 55.0), (20, 60.0)]),
        "hips_yaw": Curve([(0, 0.0), (4, -3.0), (20, -2.0)]),
    }
    for side, target in ((".L", chest_left), (".R", chest_right)):
        idle_wrist = rig.idle_wrists[side]
        lift = idle_wrist.lerp(target, 0.6) + Vector((0.0, -0.08, 0.0))
        curves[f"wrist{side}"] = Curve([(0, idle_wrist), (4, lift), (7, target), (12, target + Vector((0.0, 0.006, -0.01))), (20, target)])
        idle_pole = rig.idle_poles[side]
        tucked = Vector((side_sign(side) * 0.5, 0.6, -0.6))
        curves[f"pole{side}"] = Curve([(0, idle_pole), (6, tucked), (20, tucked)])
        curves[f"aim{side}"] = Curve([(0, 0.0), (6, 1.0), (20, 1.0)])
    return curves


def clip_startled(rig: TargetRig, frame: float, curves: dict) -> BodySpec:
    spec = idle_body(frame, 90.0)
    spec.breath_amount = 0.4
    spec.hips_offset += Vector((0.0, curves["back"].scalar(frame), curves["drop"].scalar(frame)))
    spec.hips = _add(spec.hips, (0.0, 0.0, curves["hips_yaw"].scalar(frame)))
    spec.spine = _add(spec.spine, (curves["spine_pitch"].scalar(frame), 0.0, 0.0))
    spec.chest = _add(spec.chest, (curves["chest_pitch"].scalar(frame), 0.0, 0.0))
    spec.head = _add(spec.head, (curves["head_pitch"].scalar(frame), 0.0, 0.0))
    for side in SIDES:
        arm = spec.arms[side]
        arm.shoulder = _add(arm.shoulder, (0.0, curves["shoulders"].scalar(frame), 0.0))
        arm.wrist = curves[f"wrist{side}"].vector(frame)
        arm.pole = curves[f"pole{side}"].vector(frame)
        arm.aim = ((side_sign(side) * -0.2, -0.3, 0.9), (-side_sign(side) * 0.3, 0.9, 0.0))
        arm.aim_weight = curves[f"aim{side}"].scalar(frame)
        arm.fingers = curves["fingers"].scalar(frame)
        arm.thumb = 30.0
    return spec


LOOK_AROUND = Curve([(0, 0.0), (10, 0.0), (30, 34.0), (46, 38.0), (56, 30.0), (72, -30.0), (88, -38.0), (100, -33.0),
                     (114, -4.0), (120, 0.0)], period=120.0)
LOOK_UP = Curve([(0, 0.0), (30, -4.0), (46, -1.0), (60, 0.0), (80, -5.0), (100, -2.0), (120, 0.0)], period=120.0)


def clip_look_around(rig: TargetRig, frame: float) -> BodySpec:
    spec = idle_body(frame, 120.0)
    hips_look = LOOK_AROUND.scalar(frame - 5.0)
    body_look = LOOK_AROUND.scalar(frame - 2.0)
    head_look = LOOK_AROUND.scalar(frame + 2.0)
    spec.hips_offset += Vector((0.006 * hips_look / 38.0, 0.0, 0.0))
    spec.hips = _add(spec.hips, (0.0, 0.0, 0.12 * hips_look))
    spec.spine = _add(spec.spine, (0.0, 0.0, 0.17 * body_look))
    spec.chest = _add(spec.chest, (0.0, 0.0, 0.2 * body_look))
    spec.neck = _add(spec.neck, (LOOK_UP.scalar(frame) * 0.4, 0.0, 0.22 * head_look))
    spec.head = _add(spec.head, (LOOK_UP.scalar(frame) * 0.6, 0.04 * head_look, 0.29 * head_look))
    for side in SIDES:
        spec.arms[side].swing += 0.05 * body_look * side_sign(side)
    return spec


def sit_down_curves(rig: TargetRig) -> dict:
    seated = rig.seated_offset
    start = IDLE_HIPS_OFFSET
    curves = {
        "hips_y": Curve([(0, start.y), (6, 0.05), (14, 0.2), (21, 0.33), (26, seated.y - 0.005), (30, seated.y)]),
        "hips_z": Curve([(0, start.z), (6, -0.045), (14, -0.15), (21, -0.27), (25, seated.z + 0.008), (27, seated.z - 0.004), (30, seated.z)]),
        "hips_x": Curve([(0, start.x), (14, 0.004), (30, 0.0)]),
        "hips_pitch": Curve([(0, IDLE_HIPS[0]), (8, 12.0), (15, 18.0), (22, 8.0), (27, SEATED_PELVIS_TILT - 1.0), (30, SEATED_PELVIS_TILT)]),
        "hips_roll": Curve([(0, IDLE_HIPS[1]), (14, -1.0), (30, 0.0)]),
        "hips_yaw": Curve([(0, IDLE_HIPS[2]), (16, 0.5), (30, 0.0)]),
        "spine_pitch": Curve([(0, IDLE_SPINE[0]), (8, 7.0), (15, 12.0), (22, 10.0), (27, SEATED_SPINE[0] + 1.0), (30, SEATED_SPINE[0])]),
        "chest_pitch": Curve([(0, IDLE_CHEST[0]), (8, 5.0), (15, 9.0), (22, 7.0), (28, SEATED_CHEST[0]), (30, SEATED_CHEST[0])]),
        "spine_roll": Curve([(0, IDLE_SPINE[1]), (16, 0.5), (30, 0.0)]),
        "chest_roll": Curve([(0, IDLE_CHEST[1]), (16, 0.5), (30, 0.0)]),
        "neck_pitch": Curve([(0, IDLE_NECK[0]), (12, -6.0), (22, -4.0), (30, 2.0)]),
        "head_pitch": Curve([(0, IDLE_HEAD[0]), (12, -4.0), (22, -2.0), (30, 3.0)]),
        "aim": Curve([(0, 0.0), (14, 0.3), (26, 1.0), (30, 1.0)]),
    }
    for side in SIDES:
        idle_wrist = rig.idle_wrists[side]
        lap = rig.lap_wrists[side]
        reach_out = idle_wrist.lerp(lap, 0.45) + Vector((side_sign(side) * 0.03, -0.05, 0.02))
        curves[f"wrist{side}"] = Curve([(0, idle_wrist), (13, reach_out), (24, lap + Vector((0.0, 0.0, 0.015))), (30, lap)])
        curves[f"pole{side}"] = Curve([(0, rig.idle_poles[side]), (30, Vector((side_sign(side) * 0.6, 0.6, -0.3)))])
    return curves


def clip_sit_transition(rig: TargetRig, frame: float, curves: dict) -> BodySpec:
    spec = seated_body()
    spec.breath_phase = frame / 90.0
    spec.hips_offset = Vector((curves["hips_x"].scalar(frame), curves["hips_y"].scalar(frame), curves["hips_z"].scalar(frame)))
    spec.hips = (curves["hips_pitch"].scalar(frame), curves["hips_roll"].scalar(frame), curves["hips_yaw"].scalar(frame))
    spec.spine = (curves["spine_pitch"].scalar(frame), curves["spine_roll"].scalar(frame), 0.0)
    spec.chest = (curves["chest_pitch"].scalar(frame), curves["chest_roll"].scalar(frame), 0.0)
    spec.neck = (curves["neck_pitch"].scalar(frame), lerp(IDLE_NECK[1], 0.0, frame / 30.0), 0.0)
    spec.head = (curves["head_pitch"].scalar(frame), lerp(IDLE_HEAD[1], -2.0, frame / 30.0), 0.0)
    seated_hands(rig, spec)
    for side in SIDES:
        arm = spec.arms[side]
        arm.wrist = curves[f"wrist{side}"].vector(frame)
        arm.pole = curves[f"pole{side}"].vector(frame)
        arm.aim_weight = curves["aim"].scalar(frame)
        arm.fingers = lerp(18.0, 22.0, frame / 30.0)
    return spec


def stand_up_curves(rig: TargetRig) -> dict:
    """Not a mirror of sitting down: she leans forward first, then rises over her feet."""
    seated = rig.seated_offset
    end = IDLE_HIPS_OFFSET
    curves = {
        "hips_y": Curve([(0, seated.y), (5, seated.y - 0.01), (11, 0.33), (18, 0.17), (24, 0.04), (30, end.y)]),
        "hips_z": Curve([(0, seated.z), (6, seated.z + 0.004), (11, -0.30), (18, -0.15), (24, -0.04), (30, end.z)]),
        "hips_x": Curve([(0, 0.0), (18, 0.005), (30, end.x)]),
        "hips_pitch": Curve([(0, SEATED_PELVIS_TILT), (6, 2.0), (11, 15.0), (18, 12.0), (25, 2.0), (30, IDLE_HIPS[0])]),
        "hips_roll": Curve([(0, 0.0), (18, -1.0), (30, IDLE_HIPS[1])]),
        "hips_yaw": Curve([(0, 0.0), (18, 0.5), (30, IDLE_HIPS[2])]),
        "spine_pitch": Curve([(0, SEATED_SPINE[0]), (6, 14.0), (11, 17.0), (18, 9.0), (25, 3.0), (30, IDLE_SPINE[0])]),
        "chest_pitch": Curve([(0, SEATED_CHEST[0]), (6, 11.0), (11, 12.0), (18, 6.0), (25, 1.5), (30, IDLE_CHEST[0])]),
        "spine_roll": Curve([(0, 0.0), (18, 0.8), (30, IDLE_SPINE[1])]),
        "chest_roll": Curve([(0, 0.0), (18, 0.8), (30, IDLE_CHEST[1])]),
        "neck_pitch": Curve([(0, 2.0), (8, -5.0), (18, -4.0), (30, IDLE_NECK[0])]),
        "head_pitch": Curve([(0, 3.0), (8, -3.0), (18, -2.0), (30, IDLE_HEAD[0])]),
        "aim": Curve([(0, 1.0), (6, 1.0), (16, 0.4), (28, 0.0), (30, 0.0)]),
    }
    for side in SIDES:
        idle_wrist = rig.idle_wrists[side]
        lap = rig.lap_wrists[side]
        push = lap + Vector((0.0, -0.02, -0.01))
        curves[f"wrist{side}"] = Curve([(0, lap), (7, push), (14, lap.lerp(idle_wrist, 0.4) + Vector((0.0, -0.04, 0.0))), (30, idle_wrist)])
        curves[f"pole{side}"] = Curve([(0, Vector((side_sign(side) * 0.6, 0.6, -0.3))), (30, rig.idle_poles[side])])
    return curves


def clip_stand_up(rig: TargetRig, frame: float, curves: dict) -> BodySpec:
    spec = clip_sit_transition(rig, frame, curves)
    spec.neck = (curves["neck_pitch"].scalar(frame), lerp(0.0, IDLE_NECK[1], frame / 30.0), 0.0)
    spec.head = (curves["head_pitch"].scalar(frame), lerp(-2.0, IDLE_HEAD[1], frame / 30.0), 0.0)
    for side in SIDES:
        spec.arms[side].fingers = lerp(22.0, 18.0, frame / 30.0)
        spec.arms[side].hand = (0.0, -2.0 * frame / 30.0, 0.0)
    return spec


def clip_sit(rig: TargetRig, frame: float) -> BodySpec:
    spec = seated_idle(rig, frame, 90.0)
    phase = frame / 90.0
    for side in SIDES:
        drift = 0.006 * math.sin(2.0 * math.pi * (phase - (0.1 if side == ".L" else 0.4)))
        spec.arms[side].wrist = spec.arms[side].wrist + Vector((0.0, drift, 0.0))
    return spec


READ_PAGE_TURN = Curve([(0, 0.0), (66, 0.0), (76, 1.0), (82, 1.0), (94, 0.0), (120, 0.0)], period=120.0)
READ_HEAD = Curve([(0, 0.0), (20, 1.5), (45, -0.5), (66, 0.5), (80, 3.0), (100, 0.0), (120, 0.0)], period=120.0)


def clip_sit_read(rig: TargetRig, frame: float) -> BodySpec:
    spec = seated_idle(rig, frame, 120.0)
    phase = frame / 120.0
    page = READ_PAGE_TURN.scalar(frame)
    spec.spine = _add(spec.spine, (3.0, 0.0, 0.0))
    spec.chest = _add(spec.chest, (4.0, 0.0, 0.0))
    spec.neck = _add(spec.neck, (9.0, 0.0, 0.0))
    spec.head = _add(spec.head, (13.0 + 0.8 * math.sin(2.0 * math.pi * phase * 2.0), 1.0, 2.0 * READ_HEAD.scalar(frame)))
    book_center = Vector((0.0, -0.24, -0.03))
    left = spec.arms[".L"]
    left.wrist = book_center + Vector((0.085, 0.015, -0.01))
    left.pole = Vector((0.7, 0.5, -0.5))
    left.aim = ((-0.25, -0.35, 0.9), (-0.85, 0.35, 0.3))
    left.fingers, left.thumb = 30.0, 25.0
    right = spec.arms[".R"]
    turn_target = book_center + Vector((0.035, -0.025, 0.035))
    right.wrist = (book_center + Vector((-0.085, 0.015, -0.01))).lerp(turn_target, page)
    right.wrist.z += 0.03 * math.sin(math.pi * page)
    right.pole = Vector((-0.7, 0.5, -0.5))
    right.aim = ((0.25 + 0.4 * page, -0.35, 0.9 - 0.3 * page), (0.85, 0.35, 0.3))
    right.fingers, right.thumb = 30.0 - 12.0 * page, 25.0
    return spec


PHONE_SCROLL = Curve([(0, 0.0), (18, 0.0), (22, 1.0), (26, 0.0), (48, 0.0), (52, 1.0), (56, 0.0), (90, 0.0), (94, 1.0),
                      (98, 0.0), (120, 0.0)], period=120.0)
PHONE_LIFT = Curve([(0, 0.0), (58, 0.0), (70, 1.0), (84, 1.0), (98, 0.0), (120, 0.0)], period=120.0)


def clip_phone(rig: TargetRig, frame: float) -> BodySpec:
    spec = seated_idle(rig, frame, 120.0)
    lift = PHONE_LIFT.scalar(frame)
    spec.spine = _add(spec.spine, (2.0, 0.0, 0.0))
    spec.chest = _add(spec.chest, (3.0 - 1.5 * lift, 0.0, 0.0))
    spec.neck = _add(spec.neck, (10.0 - 3.0 * lift, 0.0, -2.0))
    spec.head = _add(spec.head, (14.0 - 5.0 * lift, -3.0 * lift, -3.0))
    right = spec.arms[".R"]
    right.wrist = Vector((-0.06, -0.22, -0.02)) + Vector((0.01, -0.02, 0.05)) * lift
    right.pole = Vector((-0.8, 0.4, -0.5))
    right.aim = ((0.35, -0.3, 0.9), (0.25, 0.9, -0.2))
    right.fingers = 40.0
    right.thumb = 12.0 + 22.0 * PHONE_SCROLL.scalar(frame)
    left = spec.arms[".L"]
    left.wrist = Vector((0.03, -0.21, -0.06)) + Vector((-0.01, -0.02, 0.05)) * lift
    left.pole = Vector((0.8, 0.4, -0.5))
    left.aim = ((-0.4, -0.4, 0.8), (-0.4, 0.8, -0.3))
    left.fingers = 35.0
    left.thumb = 20.0
    return spec


DRINK_RAISE = Curve([(0, 0.0), (18, 0.0), (36, 1.0), (72, 1.0), (90, 0.0), (120, 0.0)], period=120.0)
DRINK_TILT = Curve([(0, 0.0), (30, 0.0), (42, 1.0), (62, 1.0), (76, 0.0), (120, 0.0)], period=120.0)
DRINK_GLANCE = Curve([(0, 0.0), (94, 0.0), (104, 6.0), (114, 2.0), (120, 0.0)], period=120.0)


def clip_drink(rig: TargetRig, frame: float) -> BodySpec:
    spec = idle_body(frame, 120.0)
    raise_amount = DRINK_RAISE.scalar(frame)
    tilt = DRINK_TILT.scalar(frame)
    spec.chest = _add(spec.chest, (-2.0 * tilt, 0.0, -2.0 * raise_amount))
    spec.neck = _add(spec.neck, (-5.0 * tilt, 0.0, 0.0))
    spec.head = _add(spec.head, (-10.0 * tilt, 1.5 * tilt, DRINK_GLANCE.scalar(frame)))
    right = spec.arms[".R"]
    hold = Vector((-0.07, -0.17, -0.2))
    mouth = Vector((-0.035, -0.155, 0.105))
    right.wrist = hold.lerp(mouth, raise_amount) + Vector((0.0, -0.025, 0.02)) * math.sin(math.pi * raise_amount)
    right.wrist.z -= 0.02 * tilt
    right.pole = Vector((-0.7, 0.55, -0.6))
    tip = Quaternion(Vector((1.0, 0.0, 0.0)), math.radians(-55.0 * tilt))
    right.aim = (tip @ Vector((0.35, -0.85, 0.1)), tip @ Vector((0.9, 0.3, 0.0)))
    right.fingers = 48.0
    right.thumb = 30.0
    return spec


BRAID_HOLD_LIFT = Curve([(0, 0.0), (22, 1.0), (112, 1.0), (136, 0.0), (150, 0.0)], period=150.0)
BRAID_REACH = Curve([(0, 0.0), (14, 0.0), (30, 1.0), (124, 1.0), (140, 0.0), (150, 0.0)], period=150.0)


def fix_braid_curves(rig: TargetRig) -> dict:
    # Chest-space braid landmarks: where the right hand cradles it and where the left hand strokes.
    hold = Vector((-0.115, -0.165, -0.16))
    top = Vector((-0.08, -0.15, 0.08))
    bottom = Vector((-0.085, -0.165, -0.08))
    away = Vector((0.0, -0.05, 0.0))
    idle_left = rig.idle_wrists[".L"]
    left_path = Curve([
        (0, idle_left), (14, idle_left), (22, idle_left.lerp(top, 0.55) + away), (30, top),
        (60, bottom), (68, top.lerp(bottom, 0.5) + away), (76, top),
        (106, bottom), (122, bottom), (131, bottom.lerp(idle_left, 0.5) + away), (140, idle_left), (150, idle_left),
    ], period=150.0)
    right_path = Curve([(0, rig.idle_wrists[".R"]), (22, hold), (60, hold + Vector((0.0, -0.01, 0.012))),
                        (106, hold + Vector((0.0, -0.01, 0.012))), (112, hold), (136, rig.idle_wrists[".R"]),
                        (150, rig.idle_wrists[".R"])], period=150.0)
    return {"left": left_path, "right": right_path}


def clip_fix_braid(rig: TargetRig, frame: float, curves: dict) -> BodySpec:
    spec = idle_body(frame, 150.0)
    lift = BRAID_HOLD_LIFT.scalar(frame)
    reach = BRAID_REACH.scalar(frame)
    spec.chest = _add(spec.chest, (2.0 * lift, -1.5 * lift, -4.0 * lift))
    spec.neck = _add(spec.neck, (3.0 * lift, -3.0 * lift, -3.0 * lift))
    spec.head = _add(spec.head, (4.0 * lift, -7.0 * lift, -5.0 * lift))
    right = spec.arms[".R"]
    right.wrist = curves["right"].vector(frame)
    right.pole = rig.idle_poles[".R"].lerp(Vector((-0.8, 0.5, -0.4)), lift)
    right.aim = ((0.8, 0.45, 0.1), (0.0, 0.4, 0.9))
    right.aim_weight = lift
    right.fingers = 18.0 + 30.0 * lift
    right.thumb = 10.0 + 20.0 * lift
    left = spec.arms[".L"]
    left.wrist = curves["left"].vector(frame)
    left.pole = rig.idle_poles[".L"].lerp(Vector((0.85, -0.2, -0.5)), reach)
    left.aim = ((-0.8, 0.35, -0.45), (-0.3, 0.9, 0.2))
    left.aim_weight = reach
    left.fingers = 18.0 + 10.0 * reach
    left.thumb = 10.0 + 25.0 * reach
    held = lift * 0.7
    spec.braid = {
        "braid_03": (-3.0 * held, 0.0, 0.0),
        "braid_04": (-6.0 * held, -2.0 * held, 0.0),
        "braid_05": (-3.0 * held, 0.0, 0.0),
    }
    return spec


CHAT_GESTURE = Curve([(0, 0.0), (10, 0.0), (22, 1.0), (30, 0.8), (36, 1.0), (48, 0.0), (120, 0.0)], period=120.0)
CHAT_LAUGH = Curve([(0, 0.0), (52, 0.0), (66, 1.0), (82, 1.0), (96, 0.0), (120, 0.0)], period=120.0)
CHAT_NOD = Curve([(0, 0.0), (98, 0.0), (102, 1.0), (106, 0.0), (110, 1.0), (114, 0.0), (120, 0.0)], period=120.0)
CHAT_FEET = {
    ".L": FootPlacement(0.095, -0.06, 16.0),
    ".R": FootPlacement(-0.07, 0.01, -8.0),
}


def clip_lean_chat(rig: TargetRig, frame: float) -> BodySpec:
    spec = idle_body(frame, 120.0)
    phase = frame / 120.0
    gesture = CHAT_GESTURE.scalar(frame)
    laugh = CHAT_LAUGH.scalar(frame)
    nod = CHAT_NOD.scalar(frame)
    giggle = laugh * math.sin(2.0 * math.pi * (frame - 64.0) / 6.0) if 64 <= frame <= 82 else 0.0
    spec.feet = dict(CHAT_FEET)
    spec.hips_offset = Vector((-0.02 + 0.003 * math.sin(2.0 * math.pi * phase), -0.01, -0.02))
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
    left.fingers, left.thumb = 12.0, 25.0
    left.shoulder = (0.0, 2.0 + 2.0 * giggle, 0.0)
    right = spec.arms[".R"]
    rest = Vector((-0.12, -0.13, -0.27))
    talk = Vector((-0.14, -0.23, -0.1))
    mouth = Vector((-0.03, -0.175, 0.13))
    right.wrist = rest.lerp(talk, gesture).lerp(mouth, laugh)
    right.wrist.z += 0.012 * math.sin(2.0 * math.pi * (frame - 22.0) / 10.0) * gesture
    right.pole = Vector((-0.8, 0.5, -0.4))
    open_palm = ((0.2, -0.9, 0.2), (0.0, 0.0, 1.0))
    cover = ((0.45, -0.2, 0.85), (0.1, 0.9, 0.1))
    idle_aim = ((-0.1, -0.4, -0.9), (0.9, 0.2, 0.0))
    right.aim = _blend_aim(_blend_aim(idle_aim, open_palm, gesture), cover, laugh)
    right.fingers = 15.0 - 8.0 * gesture + 20.0 * laugh
    right.thumb = 12.0
    right.shoulder = (0.0, 2.0 * giggle, 0.0)
    spec.skirt_sway = 1.5
    return spec


def _blend_aim(first: tuple, second: tuple, weight: float) -> tuple:
    return (Vector(first[0]).lerp(Vector(second[0]), weight), Vector(first[1]).lerp(Vector(second[1]), weight))


SWEEP_FEET = {
    ".L": FootPlacement(0.12, -0.08, 14.0),
    ".R": FootPlacement(-0.11, 0.07, -18.0),
}


def clip_sweep(rig: TargetRig, frame: float) -> BodySpec:
    spec = idle_body(frame, 60.0)
    phase = frame / 60.0
    stroke = math.sin(2.0 * math.pi * phase)
    lagged = math.sin(2.0 * math.pi * (phase - 0.06))
    spec.feet = dict(SWEEP_FEET)
    spec.breath_amount = 0.5
    spec.hips_offset = Vector((0.012 * lagged, 0.012, -0.045 + 0.006 * math.cos(4.0 * math.pi * phase)))
    spec.hips = (8.0, -2.0 * lagged, -4.0 + 5.0 * lagged)
    spec.spine = (6.0, 1.0 * lagged, 4.0 * stroke)
    spec.chest = (5.0, 0.0, 5.0 * stroke)
    spec.neck = (6.0, 0.0, -4.0 * stroke)
    spec.head = (6.0, -2.0, -5.0 * stroke)
    top = Vector((-0.05, -0.2, -0.02))
    bottom = Vector((-0.15, -0.3, -0.26))
    sweep = Vector((0.11, 0.0, 0.0)) * stroke + Vector((0.0, 0.025, 0.0)) * math.cos(2.0 * math.pi * phase)
    left = spec.arms[".L"]
    left.wrist = top + sweep * 0.6
    left.pole = Vector((0.8, 0.4, -0.5))
    left.aim = ((-0.85, -0.3, -0.3), (-0.2, 0.3, -0.9))
    left.fingers, left.thumb = 65.0, 40.0
    right = spec.arms[".R"]
    right.wrist = bottom + sweep
    right.pole = Vector((-0.8, 0.5, -0.3))
    right.aim = ((0.9, -0.3, -0.2), (0.2, -0.3, 0.9))
    right.fingers, right.thumb = 65.0, 40.0
    spec.skirt_sway = 2.0 * math.cos(2.0 * math.pi * (phase - 0.1))
    return spec


def clip_wave(rig: TargetRig, frame: float) -> BodySpec:
    spec = idle_body(frame, 45.0)
    phase = frame / 45.0
    wave = math.sin(2.0 * math.pi * 3.0 * phase)
    bounce = math.cos(2.0 * math.pi * 3.0 * phase)
    spec.breath_amount = 0.6
    spec.hips_offset += Vector((0.008, 0.0, -0.004 + 0.002 * bounce))
    spec.spine = _add(spec.spine, (0.0, 2.0, 2.0))
    spec.chest = _add(spec.chest, (-1.0, 2.5 + 0.6 * wave, 3.0))
    spec.head = _add(spec.head, (-1.0, -3.0 - 1.5 * wave, 3.0))
    right = spec.arms[".R"]
    skeleton = rig.skeleton
    pose = compose(rig, spec)
    world, heads = forward_kinematics(skeleton, pose)
    chest_inverse = world["chest"].inverted()
    shoulder = chest_inverse @ (heads["upper_arm.R"] - heads["chest"])
    elbow = shoulder + Vector((-0.92, -0.3, 0.12)).normalized() * skeleton.length("upper_arm.R")
    forearm = Quaternion(Vector((0.0, -1.0, 0.0)), math.radians(-20.0 * wave)) @ Vector((-0.15, -0.15, 0.97)).normalized()
    right.wrist = elbow + forearm * skeleton.length("forearm.R")
    right.pole = Vector((-0.4, 0.3, -0.85))
    palm_tilt = Quaternion(Vector((0.0, -1.0, 0.0)), math.radians(-12.0 * wave))
    right.aim = (palm_tilt @ forearm, palm_tilt @ Vector((-0.1, -1.0, 0.05)))
    right.fingers, right.thumb = 4.0, 6.0
    right.shoulder = (0.0, 6.0, 0.0)
    left = spec.arms[".L"]
    left.wrist = Vector((0.06, -0.15, -0.16))
    left.pole = Vector((0.8, 0.5, -0.4))
    left.aim = ((-0.5, -0.4, 0.6), (-0.5, 0.8, 0.2))
    left.aim_weight = 0.8
    left.fingers, left.thumb = 35.0, 25.0
    return spec


# ---------------------------------------------------------------------------------------------------

def _poses(rig: TargetRig, frame_count: int, body) -> list:
    return [compose(rig, body(frame)) for frame in range(frame_count + 1)]


def target_clips(rig: TargetRig) -> list:
    """(name, frame count, loops, poses) for every target clip."""
    walk = WalkCycle(rig.skeleton, WALK)
    notice = {name: Curve(keys) for name, keys in NOTICE_KEYS.items()}
    startled = startled_curves(rig)
    sit_down = sit_down_curves(rig)
    braid = fix_braid_curves(rig)
    stand_up = stand_up_curves(rig)
    clips = [
        ("target_idle", 90, True, lambda frame: clip_idle(rig, frame)),
        ("target_walk_routine", WALK.frame_count, True, lambda frame: clip_walk(rig, frame, walk)),
        ("target_notice_player", 30, False, lambda frame: clip_notice_player(rig, frame, notice)),
        ("target_startled", 20, False, lambda frame: clip_startled(rig, frame, startled)),
        ("target_look_around", 120, True, lambda frame: clip_look_around(rig, frame)),
        ("target_sit_down", 30, False, lambda frame: clip_sit_transition(rig, frame, sit_down)),
        ("target_stand_up", 30, False, lambda frame: clip_stand_up(rig, frame, stand_up)),
        ("target_sit", 90, True, lambda frame: clip_sit(rig, frame)),
        ("target_sit_read", 120, True, lambda frame: clip_sit_read(rig, frame)),
        ("target_phone", 120, True, lambda frame: clip_phone(rig, frame)),
        ("target_drink", 120, True, lambda frame: clip_drink(rig, frame)),
        ("target_fix_braid", 150, True, lambda frame: clip_fix_braid(rig, frame, braid)),
        ("target_lean_chat", 120, True, lambda frame: clip_lean_chat(rig, frame)),
        ("target_sweep", 60, True, lambda frame: clip_sweep(rig, frame)),
        ("target_wave", 45, True, lambda frame: clip_wave(rig, frame)),
    ]
    return [(name, frame_count, loops, _poses(rig, frame_count, body)) for name, frame_count, loops, body in clips]


def build_target_actions(armature) -> list:
    """Key every target clip onto `armature` (one muted NLA track each) and leave it in its rest pose."""
    rig = TargetRig(armature)
    actions = []
    for name, frame_count, loops, poses in target_clips(rig):
        actions.append(animation.build_clip(armature, rig.skeleton, name, frame_count, loops, poses))
    armature.animation_data.action = None
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pose_bone.location = (0.0, 0.0, 0.0)
    return actions
