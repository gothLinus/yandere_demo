"""The target's animation library: eighteen in-place clips at 30 fps (fifteen activities plus three idles).

Each clip is a function of the frame that fills a `BodySpec`; the shared `character_animation.compose`
turns it into a pose (IK feet, IK or FK arms, skirt follow) and `build_target_actions` keys each frame.
Standing clips start from the target's idle stance and seated clips from his seated stance, so the
0.3 s crossfades in Godot meet matching poses. Feet are IK-planted, so they never slide.
"""

import math

import bpy
from mathutils import Quaternion, Vector

from . import animation
from .animation import SIDES, Curve, FootPlacement, GaitParams, WalkCycle, forward_kinematics, side_sign
from .character_animation import (
    ArmSpec, BodySpec, CharacterRig, Stance, add_degrees, compose, palm_on, poses_for, sit_down_curves,
    sit_transition_body, stand_up_curves,
)

WALK = GaitParams(speed=1.3, frame_count=32)

TARGET_STANCE = Stance(
    idle_feet={
        ".L": FootPlacement(0.074, 0.004, 7.0),
        ".R": FootPlacement(-0.082, -0.036, -12.0),
    },
    idle_hips_offset=Vector((0.011, 0.0, -0.017)),
    idle_hips=(0.0, -2.5, 1.5),
    idle_spine=(1.0, 1.8, -0.8),
    idle_chest=(0.5, 1.6, -0.5),
    idle_neck=(1.0, -0.8, 0.0),
    idle_head=(2.0, -2.5, 0.0),
    idle_arm=ArmSpec(adduct=23.0, swing=5.0, elbow=20.0, hand=(0.0, -2.0, 0.0), fingers=18.0, thumb=10.0),
    seat_height=0.45,
    seat_clearance=0.085,
    # Centre of the M_Mouth strip on TargetFace in the rest pose.
    mouth=Vector((0.0, -0.0738, 1.3968)),
    # Below the chest the braid hangs free over the waist and skirt.
    hanging_bones=("braid_06", "braid_07", "braid_08", "braid_09", "braid_10"),
)


# ---------------------------------------------------------------------------------------------------
# Clips

def clip_idle(rig: CharacterRig, frame: float) -> BodySpec:
    return rig.idle_body(frame, 90.0)


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


def clip_notice_player(rig: CharacterRig, frame: float, curves: dict) -> BodySpec:
    spec = rig.idle_body(frame, 90.0)
    value = {name: curve.scalar(frame) for name, curve in curves.items()}
    spec.hips_offset += Vector((value["weight"], 0.0, value["drop"]))
    spec.hips = add_degrees(spec.hips, (0.0, 0.0, value["hips_yaw"]))
    spec.spine = add_degrees(spec.spine, (0.0, 0.0, value["spine_yaw"]))
    spec.chest = add_degrees(spec.chest, (value["chest_pitch"], 0.0, value["chest_yaw"]))
    spec.neck = add_degrees(spec.neck, (0.0, 0.0, value["neck_yaw"]))
    for side in SIDES:
        arm = spec.arms[side]
        arm.shoulder = add_degrees(arm.shoulder, (0.0, value["shoulders"], 0.0))
        arm.elbow += value["elbow"] * (1.0 if side == ".R" else 0.7)
        arm.swing += value["swing"]
        arm.fingers += value["elbow"] * 0.6
    return spec


def startled_curves(rig: CharacterRig) -> dict:
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


def clip_startled(rig: CharacterRig, frame: float, curves: dict) -> BodySpec:
    spec = rig.idle_body(frame, 90.0)
    spec.breath_amount = 0.4
    spec.hips_offset += Vector((0.0, curves["back"].scalar(frame), curves["drop"].scalar(frame)))
    spec.hips = add_degrees(spec.hips, (0.0, 0.0, curves["hips_yaw"].scalar(frame)))
    spec.spine = add_degrees(spec.spine, (curves["spine_pitch"].scalar(frame), 0.0, 0.0))
    spec.chest = add_degrees(spec.chest, (curves["chest_pitch"].scalar(frame), 0.0, 0.0))
    spec.head = add_degrees(spec.head, (curves["head_pitch"].scalar(frame), 0.0, 0.0))
    for side in SIDES:
        arm = spec.arms[side]
        arm.shoulder = add_degrees(arm.shoulder, (0.0, curves["shoulders"].scalar(frame), 0.0))
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


def clip_look_around(rig: CharacterRig, frame: float) -> BodySpec:
    spec = rig.idle_body(frame, 120.0)
    hips_look = LOOK_AROUND.scalar(frame - 5.0)
    body_look = LOOK_AROUND.scalar(frame - 2.0)
    head_look = LOOK_AROUND.scalar(frame + 2.0)
    spec.hips_offset += Vector((0.006 * hips_look / 38.0, 0.0, 0.0))
    spec.hips = add_degrees(spec.hips, (0.0, 0.0, 0.12 * hips_look))
    spec.spine = add_degrees(spec.spine, (0.0, 0.0, 0.17 * body_look))
    spec.chest = add_degrees(spec.chest, (0.0, 0.0, 0.2 * body_look))
    spec.neck = add_degrees(spec.neck, (LOOK_UP.scalar(frame) * 0.4, 0.0, 0.22 * head_look))
    spec.head = add_degrees(spec.head, (LOOK_UP.scalar(frame) * 0.6, 0.04 * head_look, 0.29 * head_look))
    for side in SIDES:
        spec.arms[side].swing += 0.05 * body_look * side_sign(side)
    return spec


def clip_sit(rig: CharacterRig, frame: float) -> BodySpec:
    spec = rig.seated_idle(frame, 90.0)
    phase = frame / 90.0
    for side in SIDES:
        drift = 0.006 * math.sin(2.0 * math.pi * (phase - (0.1 if side == ".L" else 0.4)))
        spec.arms[side].wrist = spec.arms[side].wrist + Vector((0.0, drift, 0.0))
    return spec


READ_PAGE_TURN = Curve([(0, 0.0), (66, 0.0), (76, 1.0), (82, 1.0), (94, 0.0), (120, 0.0)], period=120.0)
READ_HEAD = Curve([(0, 0.0), (20, 1.5), (45, -0.5), (66, 0.5), (80, 3.0), (100, 0.0), (120, 0.0)], period=120.0)


def clip_sit_read(rig: CharacterRig, frame: float) -> BodySpec:
    spec = rig.seated_idle(frame, 120.0)
    phase = frame / 120.0
    page = READ_PAGE_TURN.scalar(frame)
    spec.spine = add_degrees(spec.spine, (3.0, 0.0, 0.0))
    spec.chest = add_degrees(spec.chest, (4.0, 0.0, 0.0))
    spec.neck = add_degrees(spec.neck, (9.0, 0.0, 0.0))
    spec.head = add_degrees(spec.head, (13.0 + 0.8 * math.sin(2.0 * math.pi * phase * 2.0), 1.0, 2.0 * READ_HEAD.scalar(frame)))
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


def clip_phone(rig: CharacterRig, frame: float) -> BodySpec:
    spec = rig.seated_idle(frame, 120.0)
    lift = PHONE_LIFT.scalar(frame)
    spec.spine = add_degrees(spec.spine, (2.0, 0.0, 0.0))
    spec.chest = add_degrees(spec.chest, (3.0 - 1.5 * lift, 0.0, 0.0))
    spec.neck = add_degrees(spec.neck, (10.0 - 3.0 * lift, 0.0, -2.0))
    spec.head = add_degrees(spec.head, (14.0 - 5.0 * lift, -3.0 * lift, -3.0))
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
# The fist sits below and in front of the mouth (where a held can's rim meets the lips), medial enough
# to clear the braid over his right shoulder. Chest-space offset from the head-carried mouth landmark.
DRINK_HAND_FROM_MOUTH = Vector((-0.02, -0.075, -0.075))
DRINK_GLANCE = Curve([(0, 0.0), (94, 0.0), (104, 6.0), (114, 2.0), (120, 0.0)], period=120.0)


def clip_drink(rig: CharacterRig, frame: float) -> BodySpec:
    spec = rig.idle_body(frame, 120.0)
    raise_amount = DRINK_RAISE.scalar(frame)
    tilt = DRINK_TILT.scalar(frame)
    spec.chest = add_degrees(spec.chest, (-2.0 * tilt, 0.0, -2.0 * raise_amount))
    spec.neck = add_degrees(spec.neck, (-5.0 * tilt, 0.0, 0.0))
    spec.head = add_degrees(spec.head, (-10.0 * tilt, 1.5 * tilt, DRINK_GLANCE.scalar(frame)))
    right = spec.arms[".R"]
    hold = Vector((-0.07, -0.17, -0.2))
    arc = Vector((0.0, -0.025, 0.02)) * math.sin(math.pi * raise_amount) - Vector((0.0, 0.0, 0.02)) * tilt

    def wrist_to_mouth(pose) -> Vector:
        return hold.lerp(rig.mouth(pose) + DRINK_HAND_FROM_MOUTH, raise_amount) + arc

    right.wrist = wrist_to_mouth
    right.pole = Vector((-0.7, 0.55, -0.6))
    tip = Quaternion(Vector((1.0, 0.0, 0.0)), math.radians(-55.0 * tilt))
    right.aim = (tip @ Vector((0.35, -0.85, 0.1)), tip @ Vector((0.9, 0.3, 0.0)))
    right.fingers = 48.0
    right.thumb = 30.0
    return spec


BRAID_HOLD_LIFT = Curve([(0, 0.0), (22, 1.0), (112, 1.0), (136, 0.0), (150, 0.0)], period=150.0)
BRAID_REACH = Curve([(0, 0.0), (14, 0.0), (30, 1.0), (124, 1.0), (140, 0.0), (150, 0.0)], period=150.0)
# Where along the braid (bone index, fraction along that bone) the hands work: the braid lies in the hand.
BRAID_CRADLE = ("braid_06", 0.4)
BRAID_STROKE_TOP = ("braid_04", 0.2)
BRAID_STROKE_BOTTOM = ("braid_06", 0.1)
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


def clip_fix_braid(rig: CharacterRig, frame: float, curves: dict) -> BodySpec:
    spec = rig.idle_body(frame, 150.0)
    lift = BRAID_HOLD_LIFT.scalar(frame)
    reach = BRAID_REACH.scalar(frame)
    stroke = curves["stroke"].scalar(frame)
    away = curves["away"].scalar(frame)
    spec.chest = add_degrees(spec.chest, (2.0 * lift, -1.5 * lift, -4.0 * lift))
    spec.neck = add_degrees(spec.neck, (3.0 * lift, -3.0 * lift, -3.0 * lift))
    spec.head = add_degrees(spec.head, (4.0 * lift, -7.0 * lift, -5.0 * lift))
    held = lift * 0.7
    # The cradling hand lifts the braid forward off the chest.
    spec.extra_rotations = {
        "braid_03": (-3.0 * held, 0.0, 0.0),
        "braid_04": (-6.0 * held, -2.0 * held, 0.0),
        "braid_05": (-3.0 * held, 0.0, 0.0),
    }
    idle_right = rig.idle_wrists[".R"]
    idle_left = rig.idle_wrists[".L"]

    def right_wrist(pose) -> Vector:
        return idle_right.lerp(palm_on(_braid_landmark(rig, pose, BRAID_CRADLE), RIGHT_BRAID_AIM), lift)

    def left_wrist(pose) -> Vector:
        top = _braid_landmark(rig, pose, BRAID_STROKE_TOP)
        bottom = _braid_landmark(rig, pose, BRAID_STROKE_BOTTOM)
        on_braid = palm_on(top.lerp(bottom, stroke), LEFT_BRAID_AIM)
        lifted_off = on_braid + Vector((0.03, -0.05, 0.0)) * math.sin(math.pi * min(1.0, away * 2.0))
        homeward = max(0.0, away * 2.0 - 1.0)
        return lifted_off.lerp(idle_left, homeward * homeward * (3.0 - 2.0 * homeward))

    right = spec.arms[".R"]
    right.wrist = right_wrist
    right.pole = rig.idle_poles[".R"].lerp(Vector((-0.8, 0.5, -0.4)), lift)
    right.aim = RIGHT_BRAID_AIM
    right.aim_weight = lift
    right.fingers = 18.0 + 40.0 * lift
    right.thumb = 10.0 + 25.0 * lift
    left = spec.arms[".L"]
    left.wrist = left_wrist
    left.pole = rig.idle_poles[".L"].lerp(Vector((0.85, -0.2, -0.5)), reach)
    left.aim = LEFT_BRAID_AIM
    left.aim_weight = reach
    left.fingers = 18.0 + 30.0 * reach
    left.thumb = 10.0 + 30.0 * reach
    return spec


CHAT_GESTURE = Curve([(0, 0.0), (10, 0.0), (22, 1.0), (30, 0.8), (36, 1.0), (48, 0.0), (120, 0.0)], period=120.0)
CHAT_LAUGH = Curve([(0, 0.0), (52, 0.0), (66, 1.0), (82, 1.0), (96, 0.0), (120, 0.0)], period=120.0)
CHAT_NOD = Curve([(0, 0.0), (98, 0.0), (102, 1.0), (106, 0.0), (110, 1.0), (114, 0.0), (120, 0.0)], period=120.0)
# The giggling hand covers the mouth from just in front of it, fingertips up around the nose.
CHAT_HAND_FROM_MOUTH = Vector((-0.035, -0.03, -0.105))
CHAT_FEET = {
    ".L": FootPlacement(0.095, -0.06, 16.0),
    ".R": FootPlacement(-0.07, 0.01, -8.0),
}


def clip_lean_chat(rig: CharacterRig, frame: float) -> BodySpec:
    spec = rig.idle_body(frame, 120.0)
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
    talk_bob = Vector((0.0, 0.0, 0.012 * math.sin(2.0 * math.pi * (frame - 22.0) / 10.0) * gesture))

    def wrist_to_mouth(pose) -> Vector:
        return rest.lerp(talk, gesture).lerp(rig.mouth(pose) + CHAT_HAND_FROM_MOUTH, laugh) + talk_bob

    right.wrist = wrist_to_mouth
    right.pole = Vector((-0.8, 0.5, -0.4))
    open_palm = ((0.2, -0.9, 0.2), (0.0, 0.0, 1.0))
    cover = ((0.4, 0.05, 0.9), (0.1, 0.95, -0.05))
    idle_aim = ((-0.1, -0.4, -0.9), (0.9, 0.2, 0.0))
    right.aim = _blend_aim(_blend_aim(idle_aim, open_palm, gesture), cover, laugh)
    right.fingers = 15.0 - 8.0 * gesture + 5.0 * laugh
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


def clip_sweep(rig: CharacterRig, frame: float) -> BodySpec:
    spec = rig.idle_body(frame, 60.0)
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


def clip_wave(rig: CharacterRig, frame: float) -> BodySpec:
    spec = rig.idle_body(frame, 45.0)
    phase = frame / 45.0
    wave = math.sin(2.0 * math.pi * 3.0 * phase)
    bounce = math.cos(2.0 * math.pi * 3.0 * phase)
    spec.breath_amount = 0.6
    spec.hips_offset += Vector((0.008, 0.0, -0.004 + 0.002 * bounce))
    spec.spine = add_degrees(spec.spine, (0.0, 2.0, 2.0))
    spec.chest = add_degrees(spec.chest, (-1.0, 2.5 + 0.6 * wave, 3.0))
    spec.head = add_degrees(spec.head, (-1.0, -3.0 - 1.5 * wave, 3.0))
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


SHY_FEET = {
    ".L": FootPlacement(0.050, 0.000, -6.0),
    ".R": FootPlacement(-0.055, -0.020, 10.0),
}


def clip_idle_shy(rig: CharacterRig, frame: float) -> BodySpec:
    """Weight on the left leg, knees drawn together, hands clasped low, head down and tilted aside."""
    phase = frame / 120.0
    sway = math.sin(2.0 * math.pi * phase)
    fidget = math.sin(2.0 * math.pi * 2.0 * phase)
    spec = rig.idle_body(frame, 120.0)
    spec.feet = dict(SHY_FEET)
    spec.hips_offset = Vector((0.016 + 0.003 * sway, 0.004, -0.022))
    spec.hips = (1.0, -3.0 + 0.6 * sway, 2.0)
    spec.spine = (2.0, 2.0, -1.5)
    spec.chest = (3.0, 1.5 + 0.4 * sway, -1.0)
    spec.neck = (3.0, 2.0, 2.0)
    spec.head = (5.0 + 0.8 * fidget, 6.0 + 0.8 * sway, 6.0 + 1.5 * math.sin(2.0 * math.pi * (phase - 0.2)))
    for side in SIDES:
        arm = spec.arms[side]
        arm.shoulder = (0.0, 4.0, -4.0)
        arm.wrist = Vector((side_sign(side) * 0.018, -0.14 + 0.004 * fidget, -0.265 + side_sign(side) * 0.008))
        arm.pole = Vector((side_sign(side) * 0.8, 0.5, -0.3))
        arm.aim = ((-side_sign(side) * 0.55, -0.35, -0.75), (-side_sign(side) * 0.75, 0.55, -0.2))
        arm.fingers = 35.0 + 4.0 * fidget * side_sign(side)
        arm.thumb = 25.0
    spec.skirt_sway = 0.8 * sway
    return spec


PLAYFUL_FEET = {
    ".L": FootPlacement(0.060, 0.000, 8.0),
    ".R": FootPlacement(-0.050, 0.070, -14.0, pitch_degrees=30.0),
}


def clip_idle_playful(rig: CharacterRig, frame: float) -> BodySpec:
    """Hips tilted, the right heel up, hands behind the back, a light bounce and a tilted head."""
    phase = frame / 90.0
    bounce = 0.5 - 0.5 * math.cos(2.0 * math.pi * 3.0 * phase)
    sway = math.sin(2.0 * math.pi * phase)
    spec = rig.idle_body(frame, 90.0)
    spec.feet = dict(PLAYFUL_FEET)
    spec.feet[".R"] = FootPlacement(-0.050, 0.070, -14.0, pitch_degrees=30.0 + 6.0 * bounce)
    spec.hips_offset = Vector((0.020 + 0.004 * sway, 0.006, -0.018 - 0.008 * bounce))
    spec.hips = (0.0, 6.0, 3.0 + 2.0 * sway)
    spec.spine = (-1.0, -3.0, -2.0)
    spec.chest = (-2.0, -2.0 + 0.8 * sway, -2.0 * sway)
    spec.neck = (0.0, -3.0, 2.0)
    spec.head = (1.5 - 1.5 * bounce, -10.0 + 1.5 * sway, 4.0 + 2.0 * sway)
    for side in SIDES:
        arm = spec.arms[side]
        arm.wrist = Vector((side_sign(side) * 0.03, 0.16, -0.275 + 0.006 * bounce))
        arm.pole = Vector((side_sign(side) * 0.9, 0.2, 0.3))
        arm.aim = ((-side_sign(side) * 0.6, 0.25, -0.75), (-side_sign(side) * 0.3, 0.9, 0.2))
        arm.fingers = 30.0
        arm.thumb = 20.0
        arm.shoulder = (0.0, 2.0 * bounce, 3.0)
    spec.skirt_sway = 2.0 * sway
    return spec


CONFIDENT_FEET = {
    ".L": FootPlacement(0.110, -0.075, 18.0),
    ".R": FootPlacement(-0.045, 0.005, -9.0),
}


def clip_idle_confident(rig: CharacterRig, frame: float) -> BodySpec:
    """Weight on the right leg, the left hand on the hip, the chin up."""
    phase = frame / 120.0
    sway = math.sin(2.0 * math.pi * phase)
    spec = rig.idle_body(frame, 120.0)
    spec.feet = dict(CONFIDENT_FEET)
    spec.hips_offset = Vector((-0.024 + 0.003 * sway, 0.0, -0.02))
    spec.hips = (0.0, 4.5, -5.0)
    spec.spine = (-1.5, -2.5, 3.0)
    spec.chest = (-2.0, -2.0 + 0.5 * sway, 2.0)
    spec.neck = (-2.0, 1.0, -1.0)
    spec.head = (-6.0 + 1.0 * sway, 3.0, -4.0 + 2.0 * math.sin(2.0 * math.pi * (phase - 0.3)))
    left = spec.arms[".L"]
    left.wrist = Vector((0.150, 0.012, -0.200))
    left.pole = Vector((0.9, 0.35, 0.1))
    left.aim = ((-0.25, -0.5, -0.8), (-0.9, 0.2, 0.0))
    left.fingers, left.thumb = 14.0, 25.0
    right = spec.arms[".R"]
    right.adduct = 18.0
    right.swing = 3.0 + 1.0 * sway
    right.elbow = 12.0
    spec.skirt_sway = -1.0 + 0.6 * sway
    return spec


# ---------------------------------------------------------------------------------------------------

# The braid's lower bones swing out so the plait and its bow rest on the skirt; samples cover the hair hanging at
# skirt height and the bow.
BRAID_RESTING_SAMPLE_BONES = ("braid_07", "braid_08", "braid_09", "braid_10", "braid_bow")
BRAID_RESTING_LIFT_BONES = ("braid_07", "braid_08", "braid_09", "braid_10")


def target_clips(rig: CharacterRig, braid_resting: animation.SkirtResting | None = None) -> list:
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
        ("target_sit_down", 30, False, lambda frame: sit_transition_body(rig, frame, sit_down)),
        ("target_stand_up", 30, False, lambda frame: sit_transition_body(rig, frame, stand_up)),
        ("target_sit", 90, True, lambda frame: clip_sit(rig, frame)),
        ("target_sit_read", 120, True, lambda frame: clip_sit_read(rig, frame)),
        ("target_phone", 120, True, lambda frame: clip_phone(rig, frame)),
        ("target_drink", 120, True, lambda frame: clip_drink(rig, frame)),
        ("target_fix_braid", 150, True, lambda frame: clip_fix_braid(rig, frame, braid)),
        ("target_lean_chat", 120, True, lambda frame: clip_lean_chat(rig, frame)),
        ("target_sweep", 60, True, lambda frame: clip_sweep(rig, frame)),
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


def build_target_actions(armature) -> list:
    """Key every target clip onto `armature` (one muted NLA track each) and leave it in its rest pose."""
    rig = CharacterRig(armature, TARGET_STANCE)
    prefix = armature.name.removesuffix("Char")
    braid_resting = animation.SkirtResting(
        armature, rig.skeleton, bpy.data.objects[f"{prefix}Skirt"],
        [bpy.data.objects[f"{prefix}Braid"], bpy.data.objects[f"{prefix}Accessories"]],
        BRAID_RESTING_SAMPLE_BONES, BRAID_RESTING_LIFT_BONES)
    actions = []
    for name, frame_count, loops, poses in target_clips(rig, braid_resting):
        actions.append(animation.build_clip(armature, rig.skeleton, name, frame_count, loops, poses))
    armature.animation_data.action = None
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pose_bone.location = (0.0, 0.0, 0.0)
    return actions
