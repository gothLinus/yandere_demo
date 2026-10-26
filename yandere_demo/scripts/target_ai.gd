class_name TargetAI
extends CharacterBody3D
## The target: runs the day's schedule as a state machine and keeps every move seamless (spec §4.4). He walks the
## navmesh with eased speed and capped turning, slows on arrival, glides onto the anchor, and every animation change
## is a state-machine crossfade.

enum State { TRAVEL, ARRIVING, ENTERING, ACTIVITY, LEAVING, MICRO_STOP, NOTICE, SUSPICIOUS, STARTLED, REPORTING, GONE }

signal state_changed(state: State)
signal activity_started(activity: ActivityDefinition)
signal activity_completed(activity: ActivityDefinition)
signal item_dropped(item_id: StringName, position: Vector3)
signal reported()

const STATE_LOCOMOTION: StringName = &"locomotion"
const STATE_CHECK_PHONE: StringName = &"check_phone"
const ANIMATION_IDLE: StringName = &"target_idle"
const ANIMATION_SIT: StringName = &"target_sit"
const ANIMATION_SIT_DOWN: StringName = &"target_sit_down"
const ANIMATION_STAND_UP: StringName = &"target_stand_up"
const ANIMATION_NOTICE: StringName = &"target_notice_player"
const ANIMATION_STARTLED: StringName = &"target_startled"
const IDLE_VARIANTS: Array[StringName] = [
	&"target_idle", &"target_idle_shy", &"target_idle_playful", &"target_idle_confident",
]
const PLAYBACK_PARAMETER: StringName = &"parameters/playback"
const LOCOMOTION_BLEND_PARAMETER: StringName = &"parameters/locomotion/blend_position"
const WALK_TIME_SCALE_PARAMETER: StringName = &"parameters/locomotion/walk/time_scale/scale"
## target_walk_routine is keyed for this speed, so its playback rate follows his actual speed.
const WALK_CLIP_SPEED: float = 1.3

const MICRO_STOP_CHECK_PHONE: StringName = &"check_phone"
const MICRO_STOP_LOOK_WINDOW: StringName = &"look_window"
const MICRO_STOP_GLANCE_BACK: StringName = &"glance_back"
const COURTYARD_STROLL: StringName = &"courtyard_stroll"
const GO_HOME: StringName = &"go_home"
const EXPRESSION_NEUTRAL: StringName = &"neutral"
const EXPRESSION_SUSPICIOUS: StringName = &"suspicious"
const EXPRESSION_STARTLED: StringName = &"startled"
const SPAWN_MARKER: String = "TargetSpawn"
const CLASS_SEAT_MARKER: String = "TargetSeat"
const WINDOW_PREFIX: String = "Window_"
const LOCKER_ITEM_PREFIX: String = "ItemSpawn_target_locker_"
const TEACHER_PATROL_PREFIX: String = "TeacherPatrol_"
const CLOCK_AUTOLOAD_PATH: NodePath = ^"/root/SchoolClock"
const RANDOM_SALT: StringName = &"target_ai"

const HEAD_BONE: StringName = &"head"
## Eye midpoint in the head bone's space (+Y up the bone, +Z the way the face looks).
const EYE_OFFSET: Vector3 = Vector3(0.0, 0.06, 0.08)
const LOOK_DISTANCE: float = 2.0
const STROLL_REACHED_DISTANCE: float = 0.5
const PATH_END_TOLERANCE: float = 0.1
const FLOOR_SNAP_LENGTH: float = 0.4
const PROGRESS_SAMPLE_SECONDS: float = 1.0
const MINIMUM_DIRECTION_LENGTH: float = 0.001
const SAME_SPOT_DISTANCE: float = 0.05
const REACTION_STATES: Array[State] = [State.NOTICE, State.SUSPICIOUS, State.STARTLED]

enum Phase { GLIDE, POSE }

@export var walk_speed: float = 1.3
@export var tuning: TargetTuning = preload("res://data/target_tuning.tres")
@export var activity_pool: ActivityPool = preload("res://data/activity_pool.tres")

var school: SchoolEnv
var scheduler: TargetScheduler
var plan: Array[PlannedActivity] = []
var state: State = State.ACTIVITY
## Injected (tests, GameManager); setup() falls back to the SchoolClock autoload's model.
var clock: SchoolClockModel

var _day_seed: int = 0
var _history: ActivityHistory
var _block: ScheduleBlock
var _random: RandomNumberGenerator = RandomNumberGenerator.new()
var _plan_index: int = -1
var _planned: PlannedActivity
## The activity whose anchor he is heading for; for the unreachable fallback it is never started.
var _destination_activity: ActivityDefinition
var _destination: Node3D
var _lingering: bool = false
## True only while the planned activity is being performed, from its start until it completes.
var _performing: bool = false
var _seated: bool = false
var _minutes_left: float = 0.0
var _last_clock_minute: float = 0.0
var _speed: float = 0.0
var _move_yaw: float = 0.0
var _measured_speed: float = 0.0
var _last_position: Vector3 = Vector3.ZERO
var _path_length: float = 0.0
var _path_travelled: float = 0.0
var _micro_stop_index: int = 0
var _progress_samples: Array[float] = []
var _progress_seconds: float = 0.0
var _phase: Phase = Phase.GLIDE
var _phase_seconds: float = 0.0
var _glide_from: Vector3 = Vector3.ZERO
var _glide_to: Vector3 = Vector3.ZERO
var _glide_from_yaw: float = 0.0
var _glide_to_yaw: float = 0.0
var _glide_seconds: float = 0.0
var _after_leaving: Callable
var _micro_stop: StringName = &""
var _micro_stop_posed: bool = false
var _micro_stop_yaw: float = 0.0
var _stroll_spots: Array[Node3D] = []
var _resume_state: State = State.ACTIVITY
var _resume_animation: StringName = STATE_LOCOMOTION
var _current_animation: StringName = STATE_LOCOMOTION
var _playback: AnimationNodeStateMachinePlayback
var _look_tween: Tween
var _head_bone: int = -1
## Modifier output (the LookAt head turn) is only in the bone poses during the skeleton's update, so it is kept here.
var _head_pose: Transform3D = Transform3D.IDENTITY
var _head_turn_goal: float = 0.0
var _reaction_seconds: float = 0.0
var _calm_seconds_left: float = 0.0
var _glance_seconds_left: float = 0.0
var _reporting_walk: bool = false
## Ids of the items he dropped or that turned up in his locker today, as a set.
var _own_item_ids: Dictionary = {}

@onready var _model: Node3D = $Model
@onready var _skeleton: Skeleton3D = $Model/TargetChar/Skeleton3D
@onready var _animation_player: AnimationPlayer = $Model/AnimationPlayer
@onready var _look_at: LookAtModifier3D = $Model/TargetChar/Skeleton3D/LookAtModifier3D
@onready var _body_shape: CharacterBodyShape = $CharacterBodyShape
@onready var _agent: NavigationAgent3D = $NavigationAgent3D
@onready var _animation_tree: AnimationTree = $AnimationTree
@onready var _expression: ExpressionController = $ExpressionController
@onready var _secondary_motion: SecondaryMotion = $SecondaryMotion
@onready var _eye_point: Marker3D = $EyePoint
@onready var _look_target: Marker3D = $LookTarget
@onready var _props: TargetProps = $TargetProps
@onready var perception: TargetPerception = $TargetPerception


func _init() -> void:
	collision_layer = PhysicsLayers.CHARACTERS
	collision_mask = PhysicsLayers.WORLD
	# The agent turns toward the next waypoint before the corner, so at door jambs he must slide, not stop.
	wall_min_slide_angle = 0.0
	# Stair colliders are ramps: stay glued to them going down and keep the walking speed along the slope.
	floor_snap_length = FLOOR_SNAP_LENGTH
	floor_constant_speed = true


func _ready() -> void:
	_head_bone = _skeleton.find_bone(HEAD_BONE)
	_head_pose = _skeleton.get_bone_global_pose(_head_bone)
	_skeleton.skeleton_updated.connect(_on_skeleton_updated)
	_playback = _animation_tree.get(PLAYBACK_PARAMETER) as AnimationNodeStateMachinePlayback
	_agent.max_speed = walk_speed * TargetScheduler.MAX_WALK_SPEED_SCALE
	_agent.velocity_computed.connect(_on_velocity_computed)
	activity_started.connect(_record_history)
	_look_at.influence = 0.0
	_last_position = global_position
	_move_yaw = rotation.y


func _physics_process(delta: float) -> void:
	if school == null or state == State.GONE:
		return
	_feed_clock()
	var displacement: Vector3 = global_position - _last_position
	displacement.y = 0.0
	_measured_speed = displacement.length() / delta
	_path_travelled += displacement.length()
	_last_position = global_position
	_calm_seconds_left = maxf(0.0, _calm_seconds_left - delta)
	_step_glance(delta)
	match state:
		State.TRAVEL, State.ARRIVING:
			_step_travel(delta)
		State.MICRO_STOP:
			_step_micro_stop(delta)
		State.ENTERING:
			_step_entering(delta)
		State.ACTIVITY:
			_step_activity(delta)
		State.LEAVING:
			_step_leaving(delta)
		State.NOTICE:
			_step_reaction(delta, tuning.notice_pause_seconds)
		State.STARTLED:
			_step_reaction(delta, _animation_length(ANIMATION_STARTLED))
		State.REPORTING:
			_step_reporting(delta)
		_:
			_step_halt(delta)
	_update_locomotion_blend()
	_eye_point.global_position = head_position()


func setup(school_env: SchoolEnv, day_seed: int, history: ActivityHistory) -> void:
	school = school_env
	_day_seed = day_seed
	_history = history
	scheduler = TargetScheduler.new(activity_pool, school.anchor_counts())
	_agent.set_navigation_map(school.navigation_map())
	_agent.avoidance_enabled = true
	_model.visible = true
	_set_seated(false)
	_planned = null
	_performing = false
	_destination = null
	_own_item_ids.clear()
	_calm_seconds_left = 0.0
	_reporting_walk = false
	_end_head_turn()
	perception.reset()
	_set_state(State.ACTIVITY)
	var spawn: Node3D = school.marker(SPAWN_MARKER)
	if spawn != null:
		global_position = spawn.global_position
		rotation.y = spawn.global_rotation.y
	_last_position = global_position
	_move_yaw = rotation.y
	_speed = 0.0
	if clock == null:
		clock = _autoload_clock()
	if clock == null:
		_stop_in_place()
		return
	if not clock.block_changed.is_connected(on_block_changed):
		clock.block_changed.connect(on_block_changed)
	on_block_changed(clock.current_block())


func on_block_changed(block: ScheduleBlock) -> void:
	if school == null:
		return
	_block = block
	_random.seed = hash([_day_seed, block.id, RANDOM_SALT])
	if clock != null:
		_last_clock_minute = clock.current_minute
	if block.kind == GameTypes.BlockKind.CLASS:
		_spawn_locker_items()
	if state == State.GONE or state == State.REPORTING:
		return
	start_plan(scheduler.plan_block(block, hash([_day_seed, block.id]), _history))


## Follows `new_plan` from its first activity; if he is sitting, he stands up first.
func start_plan(new_plan: Array[PlannedActivity]) -> void:
	plan = new_plan
	_plan_index = -1
	_lingering = false
	_performing = false
	_end_head_turn()
	if state == State.LEAVING:
		_after_leaving = _start_next.bind(false)
		return
	_begin_leaving(_start_next.bind(false))


func snap_to_class_seat() -> void:
	var seat: Node3D = school.marker(CLASS_SEAT_MARKER)
	if seat == null:
		return
	global_position = seat.global_position
	rotation.y = seat.global_rotation.y
	_move_yaw = rotation.y
	_last_position = global_position
	velocity = Vector3.ZERO
	_speed = 0.0
	_set_seated(true)
	_destination = null
	_end_head_turn()
	_glance_seconds_left = 0.0
	var animation_name: StringName = ANIMATION_SIT
	var seat_planned: bool = _is_planned_at(seat)
	if seat_planned:
		animation_name = _planned.activity.animation
	var starts_now: bool = seat_planned and (state != State.ACTIVITY or _lingering)
	if not seat_planned:
		_planned = null
		_lingering = true
	_set_state(State.ACTIVITY)
	_performing = seat_planned
	if starts_now:
		_lingering = false
		_start_activity_timer()
		_expression.set_expression(_planned.activity.expression)
		activity_started.emit(_planned.activity)
	_current_animation = animation_name
	_playback.start(animation_name)
	_secondary_motion.on_animation_changed(animation_name)
	_props.show_for(animation_name)
	_secondary_motion.reset()


func head_position() -> Vector3:
	return _head_transform() * EYE_OFFSET


## The way his eyes look: the head bone's +Z, which is the face's forward axis on this rig.
func eye_forward() -> Vector3:
	return (_head_transform().basis * Vector3.BACK).normalized()


## The activity he is performing right now, or null while he travels, enters, leaves or idles.
func current_activity() -> ActivityDefinition:
	return _planned.activity if _performing else null


## The planned activity he is heading for or performing, or null while he idles.
func planned_destination() -> ActivityDefinition:
	return _planned.activity if _planned != null else null


func elapsed_activity_fraction() -> float:
	if not _performing or _planned.duration_minutes <= 0.0:
		return 0.0
	return clampf(1.0 - _minutes_left / _planned.duration_minutes, 0.0, 1.0)


## Head toward `toward`, `suspicious` face and the notice clip; after `notice_pause_seconds` he turns SUSPICIOUS.
func notice(toward: Vector3) -> void:
	if state == State.GONE or state == State.REPORTING:
		return
	look_toward(toward)
	if is_reacting():
		return
	_expression.set_expression(EXPRESSION_SUSPICIOUS)
	_begin_reaction(State.NOTICE, ANIMATION_NOTICE)


## The flash or the player right next to him: `startled` face and clip, then SUSPICIOUS.
func startle(toward: Vector3) -> void:
	if state == State.GONE or state == State.REPORTING:
		return
	look_toward(toward)
	_expression.set_expression(EXPRESSION_STARTLED)
	_begin_reaction(State.STARTLED, ANIMATION_STARTLED)


## Resumes what he was doing before he noticed, walking at `calm_speed_scale` for `calm_slow_seconds`.
func calm_down() -> void:
	if state != State.NOTICE and state != State.SUSPICIOUS:
		return
	_end_head_turn()
	_expression.set_expression(_planned.activity.expression if _performing else EXPRESSION_NEUTRAL)
	_calm_seconds_left = tuning.calm_slow_seconds
	_set_state(_resume_state)
	_play(_resume_animation)
	_reset_progress()


## Suspicion reached 100: startled, then he walks to the nearest teacher patrol point.
func report() -> void:
	if state == State.GONE or state == State.REPORTING:
		return
	_performing = false
	_lingering = false
	_reaction_seconds = 0.0
	_reporting_walk = false
	_glance_seconds_left = 0.0
	_expression.set_expression(EXPRESSION_STARTLED)
	_set_state(State.REPORTING)
	if not _seated:
		_play(ANIMATION_STARTLED)
	reported.emit()


## Flash reaction for photo mode (ruling R21): he only startles. Photo mode checks `perception.can_see` first and
## owns the `flash_spike`.
func on_flash(flash_position: Vector3) -> void:
	startle(flash_position)


## Turns his head toward `point` (LookAtModifier influence to 1 over `head_turn_seconds`).
func look_toward(point: Vector3) -> void:
	_look_target.global_position = point
	if _head_turn_goal < 1.0:
		_tween_head_turn(1.0)


## A heard footstep: his head turns toward it for `hearing_turn_seconds`, and he keeps doing what he does.
func glance_at(point: Vector3) -> void:
	if state == State.GONE or state == State.REPORTING or is_reacting():
		return
	look_toward(point)
	_glance_seconds_left = tuning.hearing_turn_seconds


func is_reacting() -> bool:
	return REACTION_STATES.has(state)


func is_own_item(item_id: StringName) -> bool:
	return _own_item_ids.has(item_id)


## Fed every physics frame from the clock's minute delta, so durations follow fast-forward and the block's rate.
func activity_minutes_elapsed(game_minutes_delta: float) -> void:
	if state != State.ACTIVITY or _planned == null or _lingering:
		return
	_minutes_left -= game_minutes_delta
	if _minutes_left <= 0.0:
		_complete_activity()


func _start_next(after_skip: bool) -> void:
	var skipped: bool = after_skip
	_plan_index += 1
	while _plan_index < plan.size():
		if _begin_planned(plan[_plan_index]):
			return
		skipped = true
		_plan_index += 1
	if skipped and not plan.is_empty():
		_begin_fallback()
	else:
		_stop_in_place()


func _begin_planned(planned: PlannedActivity) -> bool:
	if planned == null or planned.activity == null:
		return false
	var anchors: Array[Node3D] = school.anchors_for(planned.activity.id)
	if planned.anchor_index >= anchors.size():
		push_warning("TargetAI: no anchor %d for %s" % [planned.anchor_index, planned.activity.id])
		return false
	_planned = planned
	_lingering = false
	_destination_activity = planned.activity
	_destination = anchors[planned.anchor_index]
	_micro_stop_index = 0
	return _begin_travel()


## Every planned anchor failed: he heads for the first activity's first anchor and just waits there.
func _begin_fallback() -> void:
	var anchors: Array[Node3D] = school.anchors_for(plan[0].activity.id)
	if anchors.is_empty():
		_stop_in_place()
		return
	_planned = null
	_lingering = true
	_destination_activity = plan[0].activity
	_destination = anchors[0]
	if not _begin_travel():
		_stop_in_place()


func _begin_travel() -> bool:
	_performing = false
	_agent.target_position = _destination.global_position
	_agent.get_next_path_position()
	var path: PackedVector3Array = _agent.get_current_navigation_path()
	if path.is_empty():
		return false
	_path_length = 0.0
	for index: int in range(1, path.size()):
		_path_length += path[index - 1].distance_to(path[index])
	_path_travelled = 0.0
	_reset_progress()
	_expression.set_expression(EXPRESSION_NEUTRAL)
	_set_state(State.TRAVEL)
	_play(STATE_LOCOMOTION)
	return true


func _on_unreachable() -> void:
	if _planned == null:
		_stop_in_place()
		return
	_start_next(true)


func _stop_in_place() -> void:
	_planned = null
	_performing = false
	_destination = null
	_lingering = true
	_set_state(State.ACTIVITY)
	if not _seated:
		_play(_random_idle())


func _complete_activity() -> void:
	var finished: PlannedActivity = _planned
	_performing = false
	activity_completed.emit(finished.activity)
	_maybe_drop_item(finished)
	_begin_leaving(_start_next.bind(false))


func _is_planned_at(seat: Node3D) -> bool:
	if _planned == null or _planned.activity.posture != GameTypes.Posture.SITTING:
		return false
	var anchors: Array[Node3D] = school.anchors_for(_planned.activity.id)
	return _planned.anchor_index < anchors.size() \
		and anchors[_planned.anchor_index].global_position.distance_to(seat.global_position) < SAME_SPOT_DISTANCE


func _record_history(activity: ActivityDefinition) -> void:
	if _history != null:
		_history.record(_block.id if _block != null else &"", activity.id)


func _step_travel(delta: float) -> void:
	var distance: float = global_position.distance_to(_destination.global_position)
	if _has_arrived(distance):
		_begin_entering()
		return
	# The agent finishes up to target_desired_distance short of the path end; walk the rest before judging the anchor.
	var at_path_end: bool = _agent.is_navigation_finished() \
		and _flat_distance(global_position, _agent.get_final_position()) <= PATH_END_TOLERANCE
	if at_path_end or _is_stalled(delta):
		_on_unreachable()
		return
	var wanted: float = walk_speed * _speed_scale()
	if distance <= tuning.arriving_radius:
		_set_state(State.ARRIVING)
		wanted *= lerpf(tuning.arriving_speed_ratio, 1.0, distance / tuning.arriving_radius)
	elif state == State.TRAVEL and _begin_due_micro_stop():
		return
	_steer(wanted, delta)


func _has_arrived(distance: float) -> bool:
	return distance <= tuning.entering_distance \
		or (_agent.is_navigation_finished() and distance <= tuning.seated_entering_distance)


## Speed eases toward `wanted`; the walking direction turns toward the path at the capped turn rate, so corners are
## rounded instead of snapped, and the body faces where he walks.
func _steer(wanted: float, delta: float) -> void:
	_speed = move_toward(_speed, wanted, tuning.acceleration * delta)
	var finished: bool = _agent.is_navigation_finished()
	var waypoint: Vector3 = _agent.get_final_position() if finished else _agent.get_next_path_position()
	var toward: Vector3 = waypoint - global_position
	toward.y = 0.0
	if toward.length() > MINIMUM_DIRECTION_LENGTH:
		_move_yaw = _yaw_step(_move_yaw, _yaw_of(toward), delta)
	_turn_toward(_move_yaw, delta)
	var wanted_velocity: Vector3 = Vector3.FORWARD.rotated(Vector3.UP, _move_yaw) * _speed
	# A finished agent no longer avoids (its safe velocity is zero), so the last stretch to the path end moves directly.
	if finished:
		_on_velocity_computed(wanted_velocity)
	else:
		_agent.velocity = wanted_velocity


func _step_halt(delta: float) -> void:
	_speed = move_toward(_speed, 0.0, tuning.acceleration * delta)
	_agent.velocity = Vector3.FORWARD.rotated(Vector3.UP, _move_yaw) * _speed


func _on_velocity_computed(safe_velocity: Vector3) -> void:
	if not _is_moving():
		return
	velocity.x = safe_velocity.x
	velocity.z = safe_velocity.z
	if is_on_floor():
		velocity.y = 0.0
	else:
		velocity.y -= float(ProjectSettings.get_setting("physics/3d/default_gravity")) * get_physics_process_delta_time()
	move_and_slide()


func _is_moving() -> bool:
	if _seated:
		return false
	match state:
		State.TRAVEL, State.ARRIVING, State.MICRO_STOP, State.NOTICE, State.SUSPICIOUS, State.STARTLED, State.REPORTING:
			return true
		State.ACTIVITY:
			return _speed > 0.0
	return false


## Path progress, sampled once a second; over a full window he must gain `unreachable_min_progress` m/s.
func _is_stalled(delta: float) -> bool:
	_progress_seconds += delta
	if _progress_seconds < PROGRESS_SAMPLE_SECONDS:
		return false
	_progress_seconds -= PROGRESS_SAMPLE_SECONDS
	_progress_samples.append(_remaining_path_length())
	var window: int = roundi(tuning.unreachable_seconds / PROGRESS_SAMPLE_SECONDS)
	if _progress_samples.size() <= window:
		return false
	_progress_samples.pop_front()
	var progress: float = _progress_samples[0] - _progress_samples[_progress_samples.size() - 1]
	return progress < tuning.unreachable_min_progress * tuning.unreachable_seconds


func _reset_progress() -> void:
	_progress_seconds = 0.0
	_progress_samples = [_remaining_path_length()]


func _remaining_path_length() -> float:
	var path: PackedVector3Array = _agent.get_current_navigation_path()
	var index: int = _agent.get_current_navigation_path_index()
	if path.is_empty() or index >= path.size() or _destination == null:
		return global_position.distance_to(_destination.global_position) if _destination != null else 0.0
	var remaining: float = global_position.distance_to(path[index])
	for following: int in range(index + 1, path.size()):
		remaining += path[following - 1].distance_to(path[following])
	return remaining


func _speed_scale() -> float:
	var planned_scale: float = _planned.walk_speed_scale if _planned != null else 1.0
	return planned_scale * tuning.calm_speed_scale if _calm_seconds_left > 0.0 else planned_scale


func _begin_due_micro_stop() -> bool:
	if _planned == null or _path_length <= 0.0:
		return false
	var fractions: Array[float] = tuning.micro_stop_path_fractions
	if _micro_stop_index >= _planned.micro_stops.size() or _micro_stop_index >= fractions.size():
		return false
	if _path_travelled / _path_length < fractions[_micro_stop_index]:
		return false
	var stop: StringName = _planned.micro_stops[_micro_stop_index]
	_micro_stop_index += 1
	if stop == MICRO_STOP_LOOK_WINDOW:
		var window: Node3D = _nearest_window()
		if window == null:
			return false
		_micro_stop_yaw = _yaw_of(window.global_position - global_position)
	_micro_stop = stop
	_micro_stop_posed = false
	_phase_seconds = 0.0
	_set_state(State.MICRO_STOP)
	return true


func _step_micro_stop(delta: float) -> void:
	_step_halt(delta)
	if _speed > 0.0:
		return
	if not _micro_stop_posed:
		_micro_stop_posed = true
		_pose_micro_stop()
	if _micro_stop == MICRO_STOP_LOOK_WINDOW:
		_turn_toward(_micro_stop_yaw, delta)
		_move_yaw = rotation.y
	_phase_seconds += delta
	if _phase_seconds >= tuning.micro_stop_seconds:
		_end_head_turn()
		_reset_progress()
		_set_state(State.TRAVEL)
		_play(STATE_LOCOMOTION)


func _pose_micro_stop() -> void:
	match _micro_stop:
		MICRO_STOP_CHECK_PHONE:
			_play(STATE_CHECK_PHONE)
		MICRO_STOP_GLANCE_BACK:
			var behind: Vector3 = Vector3.FORWARD.rotated(Vector3.UP, rotation.y + deg_to_rad(tuning.glance_back_degrees))
			_look_target.global_position = head_position() + behind * LOOK_DISTANCE
			_tween_head_turn(1.0)
			_play(_random_idle())
		_:
			_play(_random_idle())


func _nearest_window() -> Node3D:
	var nearest: Node3D = null
	var nearest_distance: float = tuning.window_search_radius
	for window: Node3D in school.markers_with_prefix(WINDOW_PREFIX):
		var distance: float = window.global_position.distance_to(global_position)
		if distance <= nearest_distance:
			nearest = window
			nearest_distance = distance
	return nearest


func _begin_entering() -> void:
	_speed = 0.0
	_agent.velocity = Vector3.ZERO
	_begin_glide(_destination.global_position, _destination.global_rotation.y)
	if _destination_activity.posture == GameTypes.Posture.SITTING:
		_set_seated(true)
	_set_state(State.ENTERING)


## Linear in position and yaw, so the speed never exceeds `entering_max_speed` (ruling R12).
func _begin_glide(to: Vector3, to_yaw: float) -> void:
	_glide_from = global_position
	_glide_to = to
	_glide_from_yaw = rotation.y
	_glide_to_yaw = to_yaw
	_glide_seconds = maxf(tuning.entering_min_seconds, _glide_from.distance_to(_glide_to) / tuning.entering_max_speed)
	_phase = Phase.GLIDE
	_phase_seconds = 0.0


## Returns true once the glide has reached its end.
func _step_glide(delta: float) -> bool:
	_phase_seconds += delta
	var weight: float = clampf(_phase_seconds / _glide_seconds, 0.0, 1.0)
	global_position = _glide_from.lerp(_glide_to, weight)
	rotation.y = _glide_from_yaw + angle_difference(_glide_from_yaw, _glide_to_yaw) * weight
	_move_yaw = rotation.y
	return weight >= 1.0


func _step_entering(delta: float) -> void:
	if _phase == Phase.GLIDE:
		if not _step_glide(delta):
			return
		if not _seated:
			_begin_activity()
			return
		_phase = Phase.POSE
		_phase_seconds = 0.0
		_play(ANIMATION_SIT_DOWN)
		return
	_phase_seconds += delta
	if _phase_seconds >= _animation_length(ANIMATION_SIT_DOWN):
		_begin_activity()


func _begin_activity() -> void:
	_set_state(State.ACTIVITY)
	if _lingering:
		_play(_destination_activity.animation if _seated else _random_idle())
		return
	_start_activity_timer()
	_performing = true
	_expression.set_expression(_planned.activity.expression)
	activity_started.emit(_planned.activity)
	if _planned.activity.id == GO_HOME:
		_go_home()
		return
	if _planned.activity.id == COURTYARD_STROLL:
		_begin_stroll()
		return
	var animation_name: StringName = _planned.activity.animation
	_play(_random_idle() if animation_name == ANIMATION_IDLE else animation_name)


func _start_activity_timer() -> void:
	_minutes_left = _planned.duration_minutes if _planned != null else 0.0


func _begin_stroll() -> void:
	var spots: Array[Node3D] = []
	for spot_name: StringName in tuning.courtyard_spots:
		var spot: Node3D = school.marker(spot_name)
		if spot != null:
			spots.append(spot)
	_shuffle(spots)
	_stroll_spots = spots.slice(0, tuning.stroll_spot_count)
	_play(STATE_LOCOMOTION)
	_next_stroll_spot()


func _next_stroll_spot() -> void:
	while not _stroll_spots.is_empty():
		_destination = _stroll_spots.pop_front()
		_agent.target_position = _destination.global_position
		_agent.get_next_path_position()
		if not _agent.get_current_navigation_path().is_empty():
			_reset_progress()
			return
	_destination = null


func _step_activity(delta: float) -> void:
	if _destination == null or _planned == null or _planned.activity.id != COURTYARD_STROLL:
		_step_halt(delta)
		return
	var distance: float = global_position.distance_to(_destination.global_position)
	var reached: bool = distance <= STROLL_REACHED_DISTANCE or _agent.is_navigation_finished()
	if reached or _is_stalled(delta):
		_next_stroll_spot()
		if _destination == null:
			_play(_random_idle())
			return
		distance = global_position.distance_to(_destination.global_position)
	var wanted: float = walk_speed * _speed_scale()
	if distance <= tuning.arriving_radius:
		wanted *= lerpf(tuning.arriving_speed_ratio, 1.0, distance / tuning.arriving_radius)
	_steer(wanted, delta)


## Stands him up first when he is sitting, then calls `then`.
func _begin_leaving(then: Callable) -> void:
	_destination = null
	if not _seated:
		then.call()
		return
	_set_state(State.LEAVING)
	_begin_stand_up(then)


func _begin_stand_up(then: Callable) -> void:
	_after_leaving = then
	_phase = Phase.POSE
	_phase_seconds = 0.0
	_play(ANIMATION_STAND_UP)


func _step_leaving(delta: float) -> void:
	if _phase == Phase.POSE:
		_phase_seconds += delta
		if _phase_seconds < _animation_length(ANIMATION_STAND_UP):
			return
		var aisle: Vector3 = NavigationServer3D.map_get_closest_point(school.navigation_map(), global_position)
		aisle.y = global_position.y
		_begin_glide(aisle, rotation.y)
		_play(STATE_LOCOMOTION)
		return
	if not _step_glide(delta):
		return
	_set_seated(false)
	_last_position = global_position
	_after_leaving.call()


func _begin_reaction(reaction: State, animation_name: StringName) -> void:
	if not is_reacting():
		_resume_state = state
		_resume_animation = _current_animation
	_reaction_seconds = 0.0
	_glance_seconds_left = 0.0
	_set_state(reaction)
	if not _seated:
		_play(animation_name)


## NOTICE and STARTLED hold for `seconds`, then he watches the player as SUSPICIOUS.
func _step_reaction(delta: float, seconds: float) -> void:
	_step_halt(delta)
	_reaction_seconds += delta
	if _reaction_seconds < seconds:
		return
	_expression.set_expression(EXPRESSION_SUSPICIOUS)
	_set_state(State.SUSPICIOUS)


func _step_reporting(delta: float) -> void:
	if not _reporting_walk:
		_step_halt(delta)
		_reaction_seconds += delta
		if _reaction_seconds >= _animation_length(ANIMATION_STARTLED):
			_reporting_walk = true
			if _seated:
				_begin_stand_up(_walk_to_teacher)
			else:
				_walk_to_teacher()
		return
	if _seated:
		_step_leaving(delta)
		return
	if _destination == null or _agent.is_navigation_finished() \
			or global_position.distance_to(_destination.global_position) <= STROLL_REACHED_DISTANCE:
		_step_halt(delta)
		return
	_steer(walk_speed, delta)


func _walk_to_teacher() -> void:
	_destination = null
	var nearest_distance: float = INF
	for patrol_point: Node3D in school.markers_with_prefix(TEACHER_PATROL_PREFIX):
		var distance: float = patrol_point.global_position.distance_to(global_position)
		if distance < nearest_distance:
			_destination = patrol_point
			nearest_distance = distance
	if _destination == null:
		return
	_agent.target_position = _destination.global_position
	_agent.get_next_path_position()
	_play(STATE_LOCOMOTION)


func _step_glance(delta: float) -> void:
	if _glance_seconds_left <= 0.0:
		return
	_glance_seconds_left -= delta
	if _glance_seconds_left <= 0.0 and not is_reacting():
		_end_head_turn()


func _go_home() -> void:
	_performing = false
	_set_state(State.GONE)
	_model.visible = false
	_body_shape.set_enabled(false)
	_agent.velocity = Vector3.ZERO
	_agent.avoidance_enabled = false


func _set_seated(seated: bool) -> void:
	_seated = seated
	_body_shape.set_enabled(not seated)


func _maybe_drop_item(finished: PlannedActivity) -> void:
	var activity: ActivityDefinition = finished.activity
	if activity.item_ids.is_empty() or _random.randf() >= activity.item_drop_chance:
		return
	var item_id: StringName = activity.item_ids[_random.randi_range(0, activity.item_ids.size() - 1)]
	var spawn: Node3D = school.item_spawn_for(activity.id, finished.anchor_index)
	if spawn == null or not _is_spot_free(spawn.global_position):
		return
	ItemPickup.spawn(_props_root(), item_id, spawn.global_position)
	_own_item_ids[item_id] = true
	item_dropped.emit(item_id, spawn.global_position)


func _spawn_locker_items() -> void:
	var spots: Array[Node3D] = school.markers_with_prefix(LOCKER_ITEM_PREFIX)
	var items: Array[StringName] = tuning.class_locker_items.duplicate()
	_shuffle(items)
	var count: int = _random.randi_range(tuning.class_locker_min_items, tuning.class_locker_max_items)
	for index: int in mini(count, mini(items.size(), spots.size())):
		if _is_spot_free(spots[index].global_position):
			ItemPickup.spawn(_props_root(), items[index], spots[index].global_position)
			_own_item_ids[items[index]] = true


func _is_spot_free(at: Vector3) -> bool:
	for node: Node in get_tree().get_nodes_in_group(ItemPickup.YANDERE_ITEMS_GROUP):
		if (node as Node3D).global_position.distance_to(at) < SAME_SPOT_DISTANCE:
			return false
	return true


func _props_root() -> Node3D:
	var props: Node3D = school.get_node_or_null("Props") as Node3D
	return props if props != null else school


func _play(animation_state: StringName) -> void:
	_current_animation = animation_state
	_playback.travel(animation_state)
	_secondary_motion.on_animation_changed(animation_state)
	_props.show_for(animation_state)


func _update_locomotion_blend() -> void:
	var moving_speed: float = _measured_speed if _is_moving() or state == State.ENTERING or state == State.LEAVING else 0.0
	_animation_tree.set(LOCOMOTION_BLEND_PARAMETER, clampf(moving_speed / walk_speed, 0.0, 1.0))
	_animation_tree.set(WALK_TIME_SCALE_PARAMETER, moving_speed / WALK_CLIP_SPEED)


func _turn_toward(target_yaw: float, delta: float) -> void:
	rotation.y = _yaw_step(rotation.y, target_yaw, delta)


## lerp_angle at the turn rate, capped at the same rate in radians per second so a big turn never snaps.
func _yaw_step(from_yaw: float, target_yaw: float, delta: float) -> float:
	var step: float = angle_difference(from_yaw, lerp_angle(from_yaw, target_yaw, minf(1.0, tuning.turn_rate * delta)))
	return wrapf(from_yaw + clampf(step, -tuning.turn_rate * delta, tuning.turn_rate * delta), -PI, PI)


func _flat_distance(from: Vector3, to: Vector3) -> float:
	return Vector2(to.x - from.x, to.z - from.z).length()


## The body faces its -Z axis.
func _yaw_of(direction: Vector3) -> float:
	return atan2(-direction.x, -direction.z)


func _tween_head_turn(influence: float) -> void:
	_head_turn_goal = influence
	if _look_tween != null:
		_look_tween.kill()
	_look_tween = create_tween()
	_look_tween.tween_property(_look_at, "influence", influence, tuning.head_turn_seconds)


func _end_head_turn() -> void:
	if _look_at.influence > 0.0 or _look_tween != null:
		_tween_head_turn(0.0)


func _head_transform() -> Transform3D:
	return _skeleton.global_transform * _head_pose


func _on_skeleton_updated() -> void:
	_head_pose = _skeleton.get_bone_global_pose(_head_bone)


func _random_idle() -> StringName:
	return IDLE_VARIANTS[_random.randi_range(0, IDLE_VARIANTS.size() - 1)]


func _animation_length(animation_name: StringName) -> float:
	return _animation_player.get_animation(animation_name).length


func _shuffle(items: Array) -> void:
	for index: int in range(items.size() - 1, 0, -1):
		var other: int = _random.randi_range(0, index)
		var swapped: Variant = items[index]
		items[index] = items[other]
		items[other] = swapped


func _set_state(new_state: State) -> void:
	if new_state == state:
		return
	state = new_state
	state_changed.emit(state)


func _feed_clock() -> void:
	if clock == null:
		return
	var minutes: float = clock.current_minute - _last_clock_minute
	_last_clock_minute = clock.current_minute
	if minutes > 0.0:
		activity_minutes_elapsed(minutes)


func _autoload_clock() -> SchoolClockModel:
	var autoload: Node = get_node_or_null(CLOCK_AUTOLOAD_PATH)
	return autoload.get("model") as SchoolClockModel if autoload != null else null
