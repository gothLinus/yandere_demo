class_name TeacherAI
extends CastCharacter
## The patrolling teacher (spec §4.5): walks TeacherPatrol_01..08 in order, looks around at every third point, and
## while he sees the player raises School Alert for each reason that applies, with a "!" above his head.

signal patrol_point_reached(point: Node3D)

const PATROL_PREFIX: String = "TeacherPatrol_"
const ANIMATION_IDLE: StringName = &"teacher_idle"
const ANIMATION_WALK: StringName = &"teacher_walk"
const ANIMATION_LOOK_AROUND: StringName = &"teacher_look_around"
const CLASS_VOLUME: String = "Volume_Class1A"
const HALL_VOLUME: String = "Volume_Halls"
const REASON_OUT_OF_CLASS: StringName = &"out_of_class"
const REASON_RUNNING_IN_HALL: StringName = &"running_in_hall"
const REASON_CAMERA_AT_STUDENT: StringName = &"camera_at_student"
const REASON_CARRYING_STOLEN_ITEM: StringName = &"carrying_stolen_item"

@export var stealth_tuning: StealthTuning = preload("res://data/stealth_tuning.tres")
## With patrols off he stands where he is and watches.
@export var patrols: bool = true

var player: StealthPlayer
## Injected (tests, GameManager); setup() falls back to the SanitySystem autoload's meters.
var meters: StealthMeters
## Optional: counts with the students for `camera_at_student`.
var target: TargetAI
var sees_player: bool = false

var _attendance: AttendanceTracker
var _patrol_points: Array[Node3D] = []
var _patrol_index: int = 0
var _is_walking: bool = false
var _look_around_seconds_left: float = 0.0

@onready var _model: Node3D = $Model
@onready var _character_body_shape: CharacterBodyShape = $CharacterBodyShape
@onready var _alert_label: Label3D = $AlertLabel


func _ready() -> void:
	_attach_model(_model, _character_body_shape, ANIMATION_IDLE, ANIMATION_WALK)
	_alert_label.visible = false


func setup(school_env: SchoolEnv) -> void:
	school = school_env
	_agent.set_navigation_map(school.navigation_map())
	_reset_motion()
	if clock == null:
		clock = _autoload_clock()
	if meters == null:
		meters = _autoload_meters()
	_patrol_points = school.markers_with_prefix(PATROL_PREFIX)
	_look_around_seconds_left = 0.0
	_is_walking = false
	if not patrols or _patrol_points.is_empty():
		_play(STATE_LOCOMOTION)
		return
	_patrol_index = _nearest_patrol_index()
	_walk_to_patrol_point()


func watch(watched_player: StealthPlayer, stealth_meters: StealthMeters) -> void:
	player = watched_player
	meters = stealth_meters


func set_attendance(tracker: AttendanceTracker) -> void:
	_attendance = tracker


## Every reason the player gives him right now, whether or not he sees the player.
func alert_reasons() -> Array[StringName]:
	var reasons: Array[StringName] = []
	var player_head: Vector3 = player.head_position()
	if _is_class_in_session() and not school.volume_contains(CLASS_VOLUME, player_head):
		reasons.append(REASON_OUT_OF_CLASS)
	if player.stance == GameTypes.Stance.RUN and school.volume_contains(HALL_VOLUME, player_head):
		reasons.append(REASON_RUNNING_IN_HALL)
	if player.mode == StealthPlayer.MODE_CAMERA and _is_camera_on_a_student():
		reasons.append(REASON_CAMERA_AT_STUDENT)
	if player.carried_item != &"":
		reasons.append(REASON_CARRYING_STOLEN_ITEM)
	return reasons


func _step_behaviour(delta: float) -> void:
	if school == null:
		return
	if _look_around_seconds_left > 0.0:
		_step_halt(delta)
		_look_around_seconds_left -= delta
		if _look_around_seconds_left <= 0.0:
			_walk_to_patrol_point()
	elif _is_walking:
		if _step_walk(delta):
			_arrive_at_patrol_point()
	else:
		_step_halt(delta)
	_watch_player(delta)


func _watch_player(delta: float) -> void:
	sees_player = player != null and player.mode != StealthPlayer.MODE_HIDDEN and _can_see(player.head_position())
	var is_gaining: bool = false
	if sees_player and meters != null:
		for reason: StringName in alert_reasons():
			meters.add_alert_rate(delta, reason)
			is_gaining = true
	_alert_label.visible = is_gaining


func _can_see(point: Vector3) -> bool:
	var eye: Vector3 = head_position()
	if not Detection.is_in_view_cone(eye, body_forward(), point, stealth_tuning.teacher_fov_degrees, stealth_tuning.teacher_sight_range):
		return false
	return Detection.has_line_of_sight(get_world_3d().direct_space_state, eye, point, [])


func _is_class_in_session() -> bool:
	return _attendance != null and clock != null and _attendance.is_class_in_session(clock.seconds_into_block())


func _is_camera_on_a_student() -> bool:
	var space: PhysicsDirectSpaceState3D = get_world_3d().direct_space_state
	var range_limit: float = tuning.camera_at_student_range
	if target != null and target.state != TargetAI.State.GONE and player.is_watching(target.head_position(), space, range_limit):
		return true
	for node: Node in get_tree().get_nodes_in_group(StudentAI.GROUP):
		if player.is_watching((node as StudentAI).head_position(), space, range_limit):
			return true
	return false


func _walk_to_patrol_point() -> void:
	_is_walking = _walk_to(_patrol_points[_patrol_index].global_position)
	if not _is_walking:
		_play(STATE_LOCOMOTION)


## Every `teacher_look_around_every`-th point (TeacherPatrol_03, _06, ...) he stops and looks around.
func _arrive_at_patrol_point() -> void:
	patrol_point_reached.emit(_patrol_points[_patrol_index])
	var point_number: int = _patrol_index + 1
	_patrol_index = (_patrol_index + 1) % _patrol_points.size()
	if point_number % tuning.teacher_look_around_every == 0:
		_is_walking = false
		_look_around_seconds_left = tuning.teacher_look_around_seconds
		_play(ANIMATION_LOOK_AROUND)
		return
	_walk_to_patrol_point()


func _nearest_patrol_index() -> int:
	var nearest_index: int = 0
	var nearest_distance: float = INF
	for index: int in _patrol_points.size():
		var distance: float = _patrol_points[index].global_position.distance_to(global_position)
		if distance < nearest_distance:
			nearest_index = index
			nearest_distance = distance
	return nearest_index
