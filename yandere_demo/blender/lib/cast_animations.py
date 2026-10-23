"""Clips of the supporting cast: the player, the background students and the teacher.

Like the target's library, a clip fills a `BodySpec` per frame and `character_animation.compose` turns it into a
pose. Standing clips start from the character's idle stance and seated clips from its seated stance, so Godot's
crossfades meet matching poses. Face landmarks (mouth, right eye) are measured on each character's own meshes.
"""

import math
from typing import Callable

import bpy
from mathutils import Vector

from . import animation, mesh_utils
from .animation import SIDES, Curve, FootPlacement, GaitParams, WalkCycle, side_sign, smoothstep
from .character_animation import (
    ArmSpec, BodySpec, CharacterRig, Stance, add_degrees, palm_on, poses_for, sit_down_curves, sit_transition_body,
    stand_up_curves,
)


def face_landmarks(armature) -> dict:
    """Rest-pose `mouth` (centre of the mouth line) and `right_eye` (centre of the right eye card)."""
    prefix = armature.name.removesuffix("Char")
    return {
        "mouth": mesh_utils.material_center(bpy.data.objects[f"{prefix}Face"], "M_Mouth"),
        "right_eye": mesh_utils.material_center(bpy.data.objects[f"{prefix}Eyes"], "M_Eye", lambda point: point.x < 0.0),
    }


# ---------------------------------------------------------------------------------------------------
# Stances

def player_stance(landmarks: dict) -> Stance:
    return Stance(
        idle_feet={".L": FootPlacement(0.07, 0.0, 8.0), ".R": FootPlacement(-0.075, -0.02, -9.0)},
        mouth=landmarks["mouth"],
        # The tail below the tie keeps hanging however the head turns.
        hanging_bones=("ponytail_02", "ponytail_03", "ponytail_04"),
        idle_hips_offset=Vector((0.008, 0.0, -0.014)),
        idle_hips=(0.0, -2.0, 1.0),
        idle_spine=(1.5, 1.5, -0.5),
        idle_chest=(1.0, 1.0, -0.5),
        idle_neck=(1.5, -0.5, 0.0),
        idle_head=(3.0, -2.0, 0.0),
        idle_arm=ArmSpec(adduct=22.0, swing=4.0, elbow=18.0, fingers=20.0, thumb=12.0),
    )


def student_female_stance(landmarks: dict) -> Stance:
    return Stance(
        idle_feet={".L": FootPlacement(0.068, 0.0, 6.0), ".R": FootPlacement(-0.07, -0.01, -7.0)},
        mouth=landmarks["mouth"],
        idle_hips_offset=Vector((-0.006, 0.0, -0.01)),
        idle_hips=(0.0, 1.5, -1.0),
        idle_spine=(0.5, -1.0, 0.5),
        idle_head=(1.5, 1.5, 0.0),
        idle_arm=ArmSpec(adduct=21.0, swing=4.0, elbow=16.0, fingers=18.0, thumb=10.0),
    )


def student_male_stance(landmarks: dict) -> Stance:
    return Stance(
        idle_feet={".L": FootPlacement(0.1, 0.0, 10.0), ".R": FootPlacement(-0.1, 0.01, -10.0)},
        mouth=landmarks["mouth"],
        idle_hips_offset=Vector((0.0, 0.0, -0.008)),
        idle_spine=(-0.5, 0.0, 0.0),
        idle_chest=(-1.0, 0.0, 0.0),
        idle_head=(1.0, 0.0, 0.0),
        idle_arm=ArmSpec(adduct=19.0, swing=2.0, elbow=12.0, fingers=24.0, thumb=12.0),
        seat_clearance=0.09,
    )


def teacher_stance(landmarks: dict) -> Stance:
    return Stance(
        idle_feet={".L": FootPlacement(0.1, 0.0, 9.0), ".R": FootPlacement(-0.1, 0.0, -9.0)},
        mouth=landmarks["mouth"],
        idle_spine=(-1.0, 0.0, 0.0),
        idle_chest=(-2.0, 0.0, 0.0),
        idle_neck=(1.0, 0.0, 0.0),
        idle_head=(2.0, 0.0, 0.0),
        idle_arm=ArmSpec(adduct=18.0, swing=2.0, elbow=10.0, fingers=20.0, thumb=10.0),
    )


# ---------------------------------------------------------------------------------------------------
# Walking and running

def walk_body(rig: CharacterRig, frame: float, cycle: WalkCycle, arm_swing: float = 13.0, lean: float = 2.0,
              skirt_sway: float = 2.5) -> BodySpec:
    """An upright walk: counter-rotating shoulders, arms swinging against the legs, a light head bob."""
    phase = cycle.phase(frame)
    turn = math.cos(2.0 * math.pi * phase)
    roll = math.sin(2.0 * math.pi * (phase - 0.05))
    bob = math.cos(4.0 * math.pi * (phase - 0.06))
    spec = rig.standing_body()
    spec.gait = cycle
    spec.gait_frame = frame
    spec.hips = (lean, 0.0, 0.0)
    spec.spine = (lean, 2.0 * roll, 3.5 * turn)
    spec.chest = (lean * 0.5, 1.5 * roll, 3.0 * math.cos(2.0 * math.pi * (phase - 0.03)))
    spec.neck = (1.0 + 0.6 * bob, -0.8 * roll, -2.0 * turn)
    spec.head = (1.0 + 0.8 * bob, -0.6 * roll, -2.0 * math.cos(2.0 * math.pi * (phase - 0.05)))
    spec.breath_amount = 0.0
    for side in SIDES:
        side_phase = phase + (0.0 if side == ".L" else 0.5)
        swing = -arm_swing * math.cos(2.0 * math.pi * (side_phase - 0.06)) + 3.0
        arm = spec.arms[side]
        arm.adduct = rig.stance.idle_arm.adduct - 1.0
        arm.swing = swing
        arm.elbow = 14.0 + 9.0 * max(0.0, swing) / 16.0 + 3.0 * math.cos(2.0 * math.pi * (side_phase - 0.14))
        arm.hand = (4.0 * math.cos(2.0 * math.pi * (side_phase - 0.12)), -6.0, 0.0)
        arm.fingers = 22.0
        arm.thumb = 12.0
        arm.shoulder = (0.0, -1.5 + 1.0 * bob, 2.0 * math.cos(2.0 * math.pi * (side_phase - 0.05)))
    spec.skirt_sway = -skirt_sway * math.cos(2.0 * math.pi * (phase - 0.12))
    return spec


PLAYER_WALK = GaitParams(speed=1.4, frame_count=24, heel_strike_ahead=0.25)
PLAYER_RUN = GaitParams(speed=3.0, frame_count=20, duty=0.36, heel_strike_ahead=0.18, toe_off_degrees=45.0,
                        swing_lift=0.15, hips_height=-0.05, hips_bob=0.025, hips_sway=0.012, pelvis_yaw_degrees=8.0,
                        pelvis_roll_degrees=3.0)
PLAYER_SNEAK = GaitParams(speed=0.8, frame_count=32, duty=0.62, heel_strike_ahead=0.2, swing_lift=0.05,
                          hips_height=-0.22, hips_bob=0.008, hips_sway=0.012, pelvis_yaw_degrees=4.0,
                          pelvis_roll_degrees=2.0, toe_out_degrees=8.0)
STUDENT_WALK = GaitParams(speed=1.2, frame_count=32)
TEACHER_WALK = GaitParams(speed=1.2, frame_count=32, heel_strike_ahead=0.22, hips_bob=0.01, pelvis_yaw_degrees=4.0,
                          pelvis_roll_degrees=2.0, feet_x=0.075)


def clip_run(rig: CharacterRig, frame: float, cycle: WalkCycle) -> BodySpec:
    phase = cycle.phase(frame)
    turn = math.cos(2.0 * math.pi * phase)
    spec = rig.standing_body()
    spec.gait = cycle
    spec.gait_frame = frame
    spec.hips = (5.0, 0.0, 0.0)
    spec.spine = (8.0, 0.0, 6.0 * turn)
    spec.chest = (4.0, 0.0, 5.0 * turn)
    spec.neck = (-4.0, 0.0, -4.0 * turn)
    spec.head = (-3.0, 0.0, -4.0 * turn)
    spec.breath_amount = 0.0
    for side in SIDES:
        side_phase = phase + (0.0 if side == ".L" else 0.5)
        arm = spec.arms[side]
        arm.adduct = 14.0
        arm.swing = 8.0 - 32.0 * math.cos(2.0 * math.pi * (side_phase - 0.04))
        arm.elbow = 80.0 + 10.0 * math.cos(2.0 * math.pi * (side_phase - 0.04))
        arm.hand = (0.0, -10.0, 0.0)
        arm.fingers = 45.0
        arm.thumb = 25.0
    spec.skirt_sway = -3.0 * math.cos(2.0 * math.pi * (phase - 0.12))
    return spec


# ---------------------------------------------------------------------------------------------------
# Crouching (player)

CROUCH_DROP_FRACTION = 0.19
CROUCH_FEET = {".L": FootPlacement(0.1, -0.02, 14.0), ".R": FootPlacement(-0.1, 0.03, -14.0)}


def crouch_body(rig: CharacterRig, frame: float, period: float, depth: float) -> BodySpec:
    """The idle stance sunk `depth` (0..1) of the way into a low, forward-leaning crouch with the hands near the knees."""
    spec = rig.idle_body(frame, period)
    drop = CROUCH_DROP_FRACTION * rig.skeleton.tails["head"].z
    spec.feet = {}
    for side in SIDES:
        idle, crouched = rig.stance.idle_feet[side], CROUCH_FEET[side]
        spec.feet[side] = FootPlacement(animation.lerp(idle.x, crouched.x, depth), animation.lerp(idle.y, crouched.y, depth),
                                        animation.lerp(idle.yaw_degrees, crouched.yaw_degrees, depth))
    spec.hips_offset = spec.hips_offset.lerp(Vector((0.0, 0.05, -drop)), depth)
    spec.hips = add_degrees(spec.hips, (10.0 * depth, 0.0, 0.0))
    spec.spine = add_degrees(spec.spine, (14.0 * depth, 0.0, 0.0))
    spec.chest = add_degrees(spec.chest, (8.0 * depth, 0.0, 0.0))
    # Nothing to sit on: the back panels hang over the buttocks instead of tucking under them.
    spec.seated = 0.0
    spec.neck = add_degrees(spec.neck, (-14.0 * depth, 0.0, 0.0))
    spec.head = add_degrees(spec.head, (-10.0 * depth, 0.0, 0.0))
    for side in SIDES:
        arm = spec.arms[side]
        arm.adduct = animation.lerp(arm.adduct, 16.0, depth)
        arm.swing = animation.lerp(arm.swing, 28.0, depth)
        arm.elbow = animation.lerp(arm.elbow, 62.0, depth)
        arm.fingers = animation.lerp(arm.fingers, 32.0, depth)
    return spec


def clip_sneak(rig: CharacterRig, frame: float, cycle: WalkCycle) -> BodySpec:
    phase = cycle.phase(frame)
    turn = math.cos(2.0 * math.pi * phase)
    spec = rig.standing_body()
    spec.gait = cycle
    spec.gait_frame = frame
    spec.hips = (9.0, 0.0, 0.0)
    spec.spine = (13.0, 0.0, 2.5 * turn)
    spec.chest = (7.0, 0.0, 2.0 * turn)
    spec.neck = (-12.0, 0.0, -1.5 * turn)
    spec.head = (-8.0, 0.0, -1.5 * turn)
    spec.breath_amount = 0.5
    for side in SIDES:
        side_phase = phase + (0.0 if side == ".L" else 0.5)
        arm = spec.arms[side]
        arm.adduct = 16.0
        arm.swing = 20.0 - 6.0 * math.cos(2.0 * math.pi * (side_phase - 0.06))
        arm.elbow = 58.0
        arm.fingers = 32.0
        arm.thumb = 18.0
    spec.skirt_sway = -1.5 * math.cos(2.0 * math.pi * (phase - 0.12))
    return spec


# ---------------------------------------------------------------------------------------------------
# Photo (player)

# Chest-space offsets: the camera body sits in front of the right eye (viewfinder at the eye), the right palm
# grips its right end and the left palm cradles the lens from below.
CAMERA_FROM_EYE = Vector((0.03, -0.12, -0.02))
RIGHT_GRIP = Vector((-0.065, 0.0, 0.0))
RIGHT_GRIP_AIM = ((0.0, -0.35, 0.94), (1.0, 0.0, 0.0))
LEFT_CRADLE = Vector((0.015, -0.01, -0.045))
LEFT_CRADLE_AIM = ((-0.4, -0.9, 0.1), (0.0, 0.0, 1.0))


def clip_take_photo(rig: CharacterRig, frame: float, right_eye: Vector) -> BodySpec:
    spec = rig.idle_body(frame, 90.0)
    phase = frame / 90.0
    spec.breath_amount = 0.5
    spec.chest = add_degrees(spec.chest, (2.0, 0.0, 0.0))
    spec.neck = add_degrees(spec.neck, (2.0, -2.0, 0.0))
    spec.head = add_degrees(spec.head, (2.0 + 0.5 * math.sin(2.0 * math.pi * phase), -5.0, -2.0))

    def camera(pose) -> Vector:
        return rig.landmark(pose, "head", right_eye) + CAMERA_FROM_EYE

    right = spec.arms[".R"]
    right.wrist = lambda pose: palm_on(camera(pose) + RIGHT_GRIP, RIGHT_GRIP_AIM)
    right.pole = Vector((-0.6, 0.3, -0.75))
    right.aim = RIGHT_GRIP_AIM
    right.fingers, right.thumb = 40.0, 30.0
    left = spec.arms[".L"]
    left.wrist = lambda pose: palm_on(camera(pose) + LEFT_CRADLE, LEFT_CRADLE_AIM)
    left.pole = Vector((0.35, 0.3, -0.9))
    left.aim = LEFT_CRADLE_AIM
    left.fingers, left.thumb = 30.0, 20.0
    return spec


# ---------------------------------------------------------------------------------------------------
# Students and teacher

CHAT_GESTURE = Curve([(0, 0.0), (12, 0.0), (24, 1.0), (34, 0.7), (42, 1.0), (56, 0.0), (120, 0.0)], period=120.0)
CHAT_LAUGH = Curve([(0, 0.0), (64, 0.0), (74, 1.0), (88, 1.0), (100, 0.0), (120, 0.0)], period=120.0)
CHAT_NOD = Curve([(0, 0.0), (102, 0.0), (106, 1.0), (110, 0.0), (114, 1.0), (118, 0.0), (120, 0.0)], period=120.0)


def clip_chat(rig: CharacterRig, frame: float) -> BodySpec:
    """Talking to a friend: an open-palm gesture, a laugh that rocks the shoulders back, and a double nod."""
    spec = rig.idle_body(frame, 120.0)
    gesture = CHAT_GESTURE.scalar(frame)
    laugh = CHAT_LAUGH.scalar(frame)
    nod = CHAT_NOD.scalar(frame)
    shake = laugh * math.sin(2.0 * math.pi * (frame - 74.0) / 7.0) if 74 <= frame <= 88 else 0.0
    spec.breath_amount = 1.2
    spec.spine = add_degrees(spec.spine, (0.0, 0.0, 3.0 * gesture))
    spec.chest = add_degrees(spec.chest, (-3.0 * laugh + 1.5 * shake, 0.0, 2.0 * gesture))
    spec.neck = add_degrees(spec.neck, (4.0 * nod - 3.0 * laugh, 0.0, 0.0))
    spec.head = add_degrees(spec.head, (5.0 * nod - 4.0 * laugh, 3.0 * gesture, 4.0 * gesture))
    right = spec.arms[".R"]
    rest = rig.idle_wrists[".R"]
    talk = Vector((-0.12, -0.24, -0.05))
    talk_bob = Vector((0.0, 0.0, 0.012 * math.sin(2.0 * math.pi * (frame - 24.0) / 10.0) * gesture))
    right.wrist = rest.lerp(talk, gesture) + talk_bob
    right.pole = rig.idle_poles[".R"].lerp(Vector((-0.8, 0.5, -0.4)), gesture)
    right.aim = ((0.2, -0.9, 0.2), (0.0, 0.0, 1.0))
    right.aim_weight = gesture
    right.fingers = 18.0 - 10.0 * gesture
    right.shoulder = (0.0, 1.5 * shake, 0.0)
    left = spec.arms[".L"]
    left.shoulder = (0.0, 1.5 * shake, 0.0)
    left.elbow += 6.0 * laugh
    return spec


BEHIND_BACK_WRIST = Vector((0.035, 0.17, -0.3))


def hands_behind_back(spec: BodySpec) -> None:
    for side in SIDES:
        arm = spec.arms[side]
        arm.wrist = Vector((side_sign(side) * BEHIND_BACK_WRIST.x, BEHIND_BACK_WRIST.y, BEHIND_BACK_WRIST.z))
        arm.pole = Vector((side_sign(side) * 0.9, 0.25, 0.25))
        arm.aim = ((-side_sign(side) * 0.6, 0.2, -0.75), (-side_sign(side) * 0.3, 0.9, 0.2))
        arm.fingers = 30.0
        arm.thumb = 20.0


def clip_teacher_idle(rig: CharacterRig, frame: float) -> BodySpec:
    spec = rig.idle_body(frame, 90.0)
    hands_behind_back(spec)
    return spec


LOOK_AROUND = Curve([(0, 0.0), (12, 0.0), (32, 32.0), (48, 36.0), (58, 28.0), (74, -28.0), (90, -36.0), (102, -30.0),
                     (114, -4.0), (120, 0.0)], period=120.0)


def clip_teacher_look_around(rig: CharacterRig, frame: float) -> BodySpec:
    """Scanning the hallway with the hands behind the back: hips, chest and head turn in a lagged chain."""
    spec = rig.idle_body(frame, 120.0)
    hands_behind_back(spec)
    hips_look = LOOK_AROUND.scalar(frame - 5.0)
    body_look = LOOK_AROUND.scalar(frame - 2.0)
    head_look = LOOK_AROUND.scalar(frame + 2.0)
    spec.hips = add_degrees(spec.hips, (0.0, 0.0, 0.1 * hips_look))
    spec.spine = add_degrees(spec.spine, (0.0, 0.0, 0.15 * body_look))
    spec.chest = add_degrees(spec.chest, (0.0, 0.0, 0.2 * body_look))
    spec.neck = add_degrees(spec.neck, (0.0, 0.0, 0.24 * head_look))
    spec.head = add_degrees(spec.head, (-2.0 * smoothstep(0.0, 30.0, abs(head_look)), 0.03 * head_look, 0.3 * head_look))
    return spec


def clip_teacher_walk(rig: CharacterRig, frame: float, cycle: WalkCycle) -> BodySpec:
    spec = walk_body(rig, frame, cycle, arm_swing=6.0, lean=0.5, skirt_sway=0.0)
    spec.chest = add_degrees(spec.chest, (-2.0, 0.0, 0.0))
    return spec


# ---------------------------------------------------------------------------------------------------
# Clip lists and keying

def player_clips(rig: CharacterRig, landmarks: dict) -> list:
    """(name, frame count, loops, body) for every player clip."""
    walk = WalkCycle(rig.skeleton, PLAYER_WALK)
    run = WalkCycle(rig.skeleton, PLAYER_RUN)
    sneak = WalkCycle(rig.skeleton, PLAYER_SNEAK)
    sit_down = sit_down_curves(rig)
    stand_up = stand_up_curves(rig)
    return [
        ("player_idle", 90, True, lambda frame: rig.idle_body(frame, 90.0)),
        ("player_walk", PLAYER_WALK.frame_count, True, lambda frame: walk_body(rig, frame, walk, arm_swing=15.0)),
        ("player_run", PLAYER_RUN.frame_count, True, lambda frame: clip_run(rig, frame, run)),
        ("player_crouch_idle", 90, True, lambda frame: crouch_body(rig, frame, 90.0, 1.0)),
        ("player_sneak", PLAYER_SNEAK.frame_count, True, lambda frame: clip_sneak(rig, frame, sneak)),
        ("player_take_photo", 90, True, lambda frame: clip_take_photo(rig, frame, landmarks["right_eye"])),
        # Starts on the idle's first frame and ends on the crouch idle's first frame.
        ("player_hide", 20, False, lambda frame: crouch_body(rig, 0.0, 90.0, smoothstep(0.0, 20.0, frame))),
        ("player_sit", 90, True, lambda frame: rig.seated_idle(frame, 90.0)),
        ("player_sit_down", 30, False, lambda frame: sit_transition_body(rig, frame, sit_down)),
        ("player_stand_up", 30, False, lambda frame: sit_transition_body(rig, frame, stand_up)),
    ]


def student_clips(rig: CharacterRig) -> list:
    walk = WalkCycle(rig.skeleton, STUDENT_WALK)
    return [
        ("student_idle", 90, True, lambda frame: rig.idle_body(frame, 90.0)),
        ("student_walk", STUDENT_WALK.frame_count, True, lambda frame: walk_body(rig, frame, walk, arm_swing=12.0)),
        ("student_sit", 90, True, lambda frame: rig.seated_idle(frame, 90.0)),
        ("student_chat", 120, True, lambda frame: clip_chat(rig, frame)),
    ]


def teacher_clips(rig: CharacterRig) -> list:
    walk = WalkCycle(rig.skeleton, TEACHER_WALK)
    return [
        ("teacher_idle", 90, True, lambda frame: clip_teacher_idle(rig, frame)),
        ("teacher_walk", TEACHER_WALK.frame_count, True, lambda frame: clip_teacher_walk(rig, frame, walk)),
        ("teacher_look_around", 120, True, lambda frame: clip_teacher_look_around(rig, frame)),
    ]


# The run's leg swing peaks within a few frames; any skirt blur shaves the baked knee clearance off those peaks.
SKIRT_SMOOTHING_PASSES = {"player_run": 0}


def build_cast_actions(armature, stance: Stance, clips_for: Callable[[CharacterRig], list]) -> list:
    """Key every clip of `clips_for(rig)` onto `armature` and leave it in its rest pose."""
    rig = CharacterRig(armature, stance)
    skirt_bones = [bone for chain in rig.skeleton.chains(animation.SKIRT_PREFIX) for bone in chain]
    actions = []
    for name, frame_count, loops, body in clips_for(rig):
        poses = poses_for(rig, frame_count, body)
        animation.smooth_rotations(poses, skirt_bones, loops,
                                   SKIRT_SMOOTHING_PASSES.get(name, animation.SKIRT_SMOOTHING_PASSES))
        actions.append(animation.build_clip(armature, rig.skeleton, name, frame_count, loops, poses))
    armature.animation_data.action = None
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pose_bone.location = (0.0, 0.0, 0.0)
    return actions
