extends IntegrationTest
## The teacher walks TeacherPatrol_01..08 in order and back to _01, looking around for 4 s at every third point. Then,
## standing in the hallway, each alert reason applies on its own and the "!" shows while he raises School Alert.

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"
const TEACHER_SCENE_PATH: String = "res://scenes/teacher.tscn"
const PLAYER_SCENE_PATH: String = "res://scenes/player.tscn"
const STUDENT_SCENE_PATH: String = "res://scenes/student.tscn"
const STEALTH_TUNING: StealthTuning = preload("res://data/stealth_tuning.tres")
const CAST_TUNING: CastTuning = preload("res://data/cast_tuning.tres")
const EXPECTED_ORDER: Array[String] = [
	"TeacherPatrol_01", "TeacherPatrol_02", "TeacherPatrol_03", "TeacherPatrol_04", "TeacherPatrol_05",
	"TeacherPatrol_06", "TeacherPatrol_07", "TeacherPatrol_08", "TeacherPatrol_01",
]
const LOOK_AROUND_POINTS: Array[String] = ["TeacherPatrol_03", "TeacherPatrol_06"]
const TIME_SCALE: float = 8.0
const PHYSICS_STEPS_PER_TIME_SCALE: int = 8
const PATROL_DEADLINE_SECONDS: float = 260.0
const LEAVE_DISTANCE: float = 0.5
const LOOK_AROUND_TOLERANCE: float = 0.1
const HALL_TEACHER_POINT: Vector3 = Vector3(0.6, 0.0, -30.0)
const HALL_PLAYER_POINT: Vector3 = Vector3(0.6, 0.0, -35.0)
const STUDENT_AHEAD: Vector3 = Vector3(0.0, 0.0, -5.0)
const SETTLE_FRAMES: int = 3

var _school_env: SchoolEnv
var _teacher: TeacherAI
var _player: StealthPlayer
var _meters: StealthMeters
var _reached: Array[String] = []
var _reached_seconds: Dictionary = {}
var _left_seconds: Dictionary = {}
var _seconds: float = 0.0
var _previous_time_scale: float
var _previous_max_steps: int


func _ready() -> void:
	timeout_seconds = 90.0
	_previous_time_scale = Engine.time_scale
	_previous_max_steps = Engine.max_physics_steps_per_frame
	_school_env = (load(SCHOOL_ENV_PATH) as PackedScene).instantiate() as SchoolEnv
	add_child(_school_env)
	await _school_env.navigation_ready
	_player = (load(PLAYER_SCENE_PATH) as PackedScene).instantiate() as StealthPlayer
	add_child(_player)
	_player.global_transform = _school_env.marker("PlayerSpawn").global_transform
	_meters = StealthMeters.new(STEALTH_TUNING)
	_teacher = (load(TEACHER_SCENE_PATH) as PackedScene).instantiate() as TeacherAI
	add_child(_teacher)
	_teacher.patrol_point_reached.connect(_on_patrol_point_reached)
	var failure: String = await _patrols_in_order()
	if failure.is_empty():
		failure = await _alert_reasons_apply()
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _physics_process(delta: float) -> void:
	_seconds += delta
	if _reached.is_empty() or _left_seconds.has(_reached.size()):
		return
	var last_point: Node3D = _school_env.marker(_reached[-1])
	if _teacher.global_position.distance_to(last_point.global_position) > LEAVE_DISTANCE:
		_left_seconds[_reached.size()] = _seconds


func _patrols_in_order() -> String:
	_teacher.global_transform = _school_env.marker(EXPECTED_ORDER[0]).global_transform
	_teacher.setup(_school_env)
	Engine.time_scale = TIME_SCALE
	Engine.max_physics_steps_per_frame = maxi(_previous_max_steps, int(PHYSICS_STEPS_PER_TIME_SCALE * TIME_SCALE))
	var start_seconds: float = _seconds
	while _reached.size() < EXPECTED_ORDER.size() and _seconds - start_seconds <= PATROL_DEADLINE_SECONDS:
		await get_tree().physics_frame
	_restore_time_scale()
	if _reached != EXPECTED_ORDER:
		return "patrol order %s, expected %s" % [_reached, EXPECTED_ORDER]
	print("patrol loop in %.1f s" % (_seconds - start_seconds))
	for index: int in _reached.size() - 1:
		var stop_seconds: float = _left_seconds.get(index + 1, INF) - _reached_seconds[index + 1]
		var looks_around: bool = LOOK_AROUND_POINTS.has(_reached[index])
		if looks_around and stop_seconds < CAST_TUNING.teacher_look_around_seconds - LOOK_AROUND_TOLERANCE:
			return "he stood %.2f s at %s, expected a %.0f s look-around" % [stop_seconds, _reached[index], CAST_TUNING.teacher_look_around_seconds]
		if not looks_around and stop_seconds >= CAST_TUNING.teacher_look_around_seconds - LOOK_AROUND_TOLERANCE:
			return "he stopped %.2f s at %s, which is not a look-around point" % [stop_seconds, _reached[index]]
	return ""


func _alert_reasons_apply() -> String:
	_teacher.patrols = false
	_teacher.global_position = HALL_TEACHER_POINT
	_teacher.rotation.y = 0.0
	_teacher.setup(_school_env)
	_teacher.watch(_player, _meters)
	await _place_player(HALL_PLAYER_POINT)
	if not _teacher.sees_player:
		return "the teacher does not see the player 5 m in front of him"
	if not _teacher.alert_reasons().is_empty() or _alert_label().visible:
		return "reasons %s with nothing wrong (label visible %s)" % [_teacher.alert_reasons(), _alert_label().visible]
	_player.pick_up(&"pen")
	_meters.reset()
	await _settle()
	if _teacher.alert_reasons() != [TeacherAI.REASON_CARRYING_STOLEN_ITEM] or _meters.school_alert <= 0.0 or not _alert_label().visible:
		return "carrying: reasons %s, alert %.2f, label %s" % [_teacher.alert_reasons(), _meters.school_alert, _alert_label().visible]
	_player.drop_carried()
	_player.stance = GameTypes.Stance.RUN
	if _teacher.alert_reasons() != [TeacherAI.REASON_RUNNING_IN_HALL]:
		return "running in the hall: reasons %s" % [_teacher.alert_reasons()]
	var student: StudentAI = (load(STUDENT_SCENE_PATH) as PackedScene).instantiate() as StudentAI
	add_child(student)
	student.global_position = _player.global_position + STUDENT_AHEAD
	_player.enter_camera_mode()
	await _settle()
	if _teacher.alert_reasons() != [TeacherAI.REASON_CAMERA_AT_STUDENT]:
		return "camera at a student: reasons %s" % [_teacher.alert_reasons()]
	return ""


func _on_patrol_point_reached(point: Node3D) -> void:
	_reached.append(String(point.name))
	_reached_seconds[_reached.size()] = _seconds


func _alert_label() -> Label3D:
	return _teacher.get_node("AlertLabel") as Label3D


func _place_player(at: Vector3) -> void:
	_player.global_position = at
	_player.velocity = Vector3.ZERO
	await _settle()


func _settle() -> void:
	for frame: int in SETTLE_FRAMES:
		await get_tree().physics_frame
	await get_tree().process_frame


func _restore_time_scale() -> void:
	Engine.time_scale = _previous_time_scale
	Engine.max_physics_steps_per_frame = _previous_max_steps


func _exit_tree() -> void:
	_restore_time_scale()
