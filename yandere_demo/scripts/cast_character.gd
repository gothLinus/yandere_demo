class_name CastCharacter
extends CharacterBody3D
## Shared body of the teacher and the background students: walks the navmesh with eased speed and capped turning,
## glides onto and off seats (ruling R12), and plays its model's clips through a crossfading state machine.

const STATE_LOCOMOTION: StringName = &"locomotion"
const PLAYBACK_PARAMETER: StringName = &"parameters/playback"
const LOCOMOTION_BLEND_PARAMETER: StringName = &"parameters/locomotion/blend_position"
const WALK_TIME_SCALE_PARAMETER: StringName = &"parameters/locomotion/walk/time_scale/scale"
const CROSSFADE_SECONDS: float = 0.3
const HEAD_BONE: StringName = &"head"
## Eye midpoint in the head bone's space (+Y up the bone, +Z the way the face looks).
const EYE_OFFSET: Vector3 = Vector3(0.0, 0.06, 0.08)
const FLOOR_SNAP_LENGTH: float = 0.4
const MINIMUM_DIRECTION_LENGTH: float = 0.001
const PATH_END_TOLERANCE: float = 0.1
const CLOCK_AUTOLOAD_PATH: NodePath = ^"/root/SchoolClock"
const SANITY_AUTOLOAD_PATH: NodePath = ^"/root/SanitySystem"

@export var tuning: CastTuning = preload("res://data/cast_tuning.tres")

var school: SchoolEnv
## Injected (tests, GameManager); setup() falls back to the SchoolClock autoload's model.
var clock: SchoolClockModel

var _speed: float = 0.0
var _move_yaw: float = 0.0
var _measured_speed: float = 0.0
var _last_position: Vector3 = Vector3.ZERO
var _stuck_seconds: float = 0.0
var _seated: bool = false
var _gliding: bool = false
var _glide_from: Vector3 = Vector3.ZERO
var _glide_to: Vector3 = Vector3.ZERO
var _glide_from_yaw: float = 0.0
var _glide_to_yaw: float = 0.0
var _glide_seconds: float = 0.0
var _glide_elapsed: float = 0.0
var _playback: AnimationNodeStateMachinePlayback
var _animation_tree: AnimationTree
var _skeleton: Skeleton3D
var _head_bone: int = -1
var _body_shape: CharacterBodyShape

@onready var _agent: NavigationAgent3D = $NavigationAgent3D


func _init() -> void:
	collision_layer = PhysicsLayers.CHARACTERS
	collision_mask = PhysicsLayers.WORLD
	# The agent turns toward the next waypoint before the corner, so at door jambs the body must slide, not stop.
	wall_min_slide_angle = 0.0
	floor_snap_length = FLOOR_SNAP_LENGTH
	floor_constant_speed = true


func _physics_process(delta: float) -> void:
	var displacement: Vector3 = global_position - _last_position
	displacement.y = 0.0
	_measured_speed = displacement.length() / delta
	_last_position = global_position
	_step_behaviour(delta)
	_update_locomotion_blend()


func head_position() -> Vector3:
	if _skeleton == null:
		return global_position
	return _skeleton.global_transform * _skeleton.get_bone_global_pose(_head_bone) * EYE_OFFSET


## The body faces its -Z axis.
func body_forward() -> Vector3:
	return Vector3.FORWARD.rotated(Vector3.UP, rotation.y)


## Overridden by the teacher and the students; runs every physics frame.
func _step_behaviour(_delta: float) -> void:
	pass


func _attach_model(model: Node3D, body_shape: CharacterBodyShape, idle_clip: StringName, walk_clip: StringName) -> void:
	_body_shape = body_shape
	_skeleton = model.find_child("Skeleton3D", true, false) as Skeleton3D
	_head_bone = _skeleton.find_bone(HEAD_BONE)
	var animation_player: AnimationPlayer = model.get_node("AnimationPlayer") as AnimationPlayer
	_animation_tree = AnimationTree.new()
	_animation_tree.name = "AnimationTree"
	add_child(_animation_tree)
	_animation_tree.anim_player = _animation_tree.get_path_to(animation_player)
	_animation_tree.root_node = _animation_tree.get_path_to(model)
	_animation_tree.tree_root = _state_machine(animation_player, idle_clip, walk_clip)
	_animation_tree.active = true
	_playback = _animation_tree.get(PLAYBACK_PARAMETER) as AnimationNodeStateMachinePlayback
	_agent.max_speed = tuning.walk_speed
	_agent.velocity_computed.connect(_on_velocity_computed)
	_reset_motion()


## Call after placing the body, so speed measurement and steering start from where it stands.
func _reset_motion() -> void:
	_last_position = global_position
	_move_yaw = rotation.y
	_speed = 0.0
	_stuck_seconds = 0.0


func _autoload_clock() -> SchoolClockModel:
	var autoload: Node = get_node_or_null(CLOCK_AUTOLOAD_PATH)
	return autoload.get("model") as SchoolClockModel if autoload != null else null


func _autoload_meters() -> StealthMeters:
	var autoload: Node = get_node_or_null(SANITY_AUTOLOAD_PATH)
	return autoload.get("meters") as StealthMeters if autoload != null else null


## Returns false when the navmesh has no path there.
func _walk_to(point: Vector3) -> bool:
	_agent.target_position = point
	_agent.get_next_path_position()
	if _agent.get_current_navigation_path().is_empty():
		return false
	_stuck_seconds = 0.0
	_play(STATE_LOCOMOTION)
	return true


## Steps along the agent's path; returns true at the path end, or once the body is stuck.
func _step_walk(delta: float) -> bool:
	var finished: bool = _agent.is_navigation_finished()
	var waypoint: Vector3 = _agent.get_final_position() if finished else _agent.get_next_path_position()
	var toward: Vector3 = waypoint - global_position
	toward.y = 0.0
	_stuck_seconds = _stuck_seconds + delta if _measured_speed < tuning.stuck_speed else 0.0
	if (finished and toward.length() <= PATH_END_TOLERANCE) or _stuck_seconds >= tuning.stuck_seconds:
		_step_halt(delta)
		return true
	_speed = move_toward(_speed, tuning.walk_speed, tuning.acceleration * delta)
	if finished:
		# The agent stops target_desired_distance short of the path end and no longer avoids (its safe velocity is
		# zero), so the last stretch goes straight there.
		_turn_toward(_yaw_of(toward), delta)
		_on_velocity_computed(toward.normalized() * minf(_speed, toward.length() / delta))
		return false
	if toward.length() > MINIMUM_DIRECTION_LENGTH:
		_move_yaw = _yaw_step(_move_yaw, _yaw_of(toward), delta)
	rotation.y = _yaw_step(rotation.y, _move_yaw, delta)
	_agent.velocity = Vector3.FORWARD.rotated(Vector3.UP, _move_yaw) * _speed
	return false


func _step_halt(delta: float) -> void:
	_speed = move_toward(_speed, 0.0, tuning.acceleration * delta)
	if school != null:
		_agent.velocity = Vector3.FORWARD.rotated(Vector3.UP, _move_yaw) * _speed


func _turn_toward(target_yaw: float, delta: float) -> void:
	rotation.y = _yaw_step(rotation.y, target_yaw, delta)
	_move_yaw = rotation.y


func _on_velocity_computed(safe_velocity: Vector3) -> void:
	if _seated or _gliding:
		return
	velocity.x = safe_velocity.x
	velocity.z = safe_velocity.z
	if is_on_floor():
		velocity.y = 0.0
	else:
		velocity.y -= float(ProjectSettings.get_setting("physics/3d/default_gravity")) * get_physics_process_delta_time()
	move_and_slide()


## Linear in position and yaw, so the speed never exceeds `glide_max_speed` (ruling R12).
func _begin_glide(to: Vector3, to_yaw: float) -> void:
	_speed = 0.0
	_agent.velocity = Vector3.ZERO
	_glide_from = global_position
	_glide_to = to
	_glide_from_yaw = rotation.y
	_glide_to_yaw = to_yaw
	_glide_seconds = maxf(tuning.glide_min_seconds, _glide_from.distance_to(_glide_to) / tuning.glide_max_speed)
	_glide_elapsed = 0.0
	_gliding = true


## Returns true once the glide has reached its end.
func _step_glide(delta: float) -> bool:
	_glide_elapsed += delta
	var weight: float = clampf(_glide_elapsed / _glide_seconds, 0.0, 1.0)
	global_position = _glide_from.lerp(_glide_to, weight)
	rotation.y = _glide_from_yaw + angle_difference(_glide_from_yaw, _glide_to_yaw) * weight
	_move_yaw = rotation.y
	_gliding = weight < 1.0
	return not _gliding


func _set_seated(seated: bool) -> void:
	_seated = seated
	_body_shape.set_enabled(not seated)


func _play(state_name: StringName) -> void:
	_playback.travel(state_name)


func _update_locomotion_blend() -> void:
	if _animation_tree == null:
		return
	var moving_speed: float = 0.0 if _seated else _measured_speed
	_animation_tree.set(LOCOMOTION_BLEND_PARAMETER, clampf(moving_speed / tuning.walk_speed, 0.0, 1.0))
	_animation_tree.set(WALK_TIME_SCALE_PARAMETER, moving_speed / tuning.walk_speed)


## lerp_angle at the turn rate, capped at the same rate in radians per second so a big turn never snaps.
func _yaw_step(from_yaw: float, target_yaw: float, delta: float) -> float:
	var step: float = angle_difference(from_yaw, lerp_angle(from_yaw, target_yaw, minf(1.0, tuning.turn_rate * delta)))
	return wrapf(from_yaw + clampf(step, -tuning.turn_rate * delta, tuning.turn_rate * delta), -PI, PI)


func _yaw_of(direction: Vector3) -> float:
	return atan2(-direction.x, -direction.z)


## `locomotion` blends idle into the walk (its playback rate following the speed); every other clip is its own state,
## and all states are joined by one shared crossfade.
func _state_machine(animation_player: AnimationPlayer, idle_clip: StringName, walk_clip: StringName) -> AnimationNodeStateMachine:
	var walk: AnimationNodeBlendTree = AnimationNodeBlendTree.new()
	walk.add_node(&"animation", _animation_node(walk_clip), Vector2.ZERO)
	walk.add_node(&"time_scale", AnimationNodeTimeScale.new(), Vector2(200.0, 0.0))
	walk.connect_node(&"time_scale", 0, &"animation")
	walk.connect_node(&"output", 0, &"time_scale")
	var locomotion: AnimationNodeBlendSpace1D = AnimationNodeBlendSpace1D.new()
	locomotion.min_space = 0.0
	locomotion.max_space = 1.0
	locomotion.add_blend_point(_animation_node(idle_clip), 0.0, -1, &"idle")
	locomotion.add_blend_point(walk, 1.0, -1, &"walk")
	var machine: AnimationNodeStateMachine = AnimationNodeStateMachine.new()
	machine.add_node(STATE_LOCOMOTION, locomotion, Vector2.ZERO)
	var states: Array[StringName] = [STATE_LOCOMOTION]
	for clip_name: String in animation_player.get_animation_list():
		var clip: StringName = StringName(clip_name)
		if clip != walk_clip:
			machine.add_node(clip, _animation_node(clip), Vector2(250.0, 80.0 * states.size()))
			states.append(clip)
	machine.add_transition(&"Start", STATE_LOCOMOTION, AnimationNodeStateMachineTransition.new())
	var crossfade: AnimationNodeStateMachineTransition = AnimationNodeStateMachineTransition.new()
	crossfade.xfade_time = CROSSFADE_SECONDS
	for from_state: StringName in states:
		for to_state: StringName in states:
			if from_state != to_state:
				machine.add_transition(from_state, to_state, crossfade)
	return machine


func _animation_node(clip: StringName) -> AnimationNodeAnimation:
	var node: AnimationNodeAnimation = AnimationNodeAnimation.new()
	node.animation = clip
	return node
