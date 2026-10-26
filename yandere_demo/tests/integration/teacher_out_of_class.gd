extends IntegrationTest
## Morning class, 40 s in (past the grace period): the patrolling teacher sees the player in the hallway and School
## Alert rises within 1 s. Seen inside Class 1A instead, there is no out-of-class gain.

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"
const TEACHER_SCENE_PATH: String = "res://scenes/teacher.tscn"
const PLAYER_SCENE_PATH: String = "res://scenes/player.tscn"
const SCHEDULE_PATH: String = "res://data/schedule_table.tres"
const STEALTH_TUNING: StealthTuning = preload("res://data/stealth_tuning.tres")
const CLASS_BLOCK_ID: StringName = &"morning_class"
const SECONDS_INTO_BLOCK: float = 40.0
const PATROL_START: String = "TeacherPatrol_01"
const HALL_PLAYER_OFFSET: Vector3 = Vector3(0.0, 0.0, -5.0)
const CLASS_VOLUME: String = "Volume_Class1A"
const CLASS_PLAYER_POINT: Vector3 = Vector3(-3.0, 0.0, -20.0)
const CLASS_TEACHER_POINT: Vector3 = Vector3(-3.0, 0.0, -26.5)
const MEASURE_SECONDS: float = 1.0
const SETTLE_FRAMES: int = 3

var _school_env: SchoolEnv
var _teacher: TeacherAI
var _player: StealthPlayer
var _meters: StealthMeters


func _ready() -> void:
	timeout_seconds = 60.0
	_school_env = (load(SCHOOL_ENV_PATH) as PackedScene).instantiate() as SchoolEnv
	add_child(_school_env)
	await _school_env.navigation_ready
	var table: ScheduleTable = load(SCHEDULE_PATH) as ScheduleTable
	var clock: SchoolClockModel = SchoolClockModel.new(table)
	clock.skip_to_block_end()
	clock.advance(SECONDS_INTO_BLOCK)
	var attendance: AttendanceTracker = AttendanceTracker.new(table.class_grace_real_seconds)
	attendance.on_block_started(clock.current_block())
	_player = (load(PLAYER_SCENE_PATH) as PackedScene).instantiate() as StealthPlayer
	add_child(_player)
	_meters = StealthMeters.new(STEALTH_TUNING)
	_teacher = (load(TEACHER_SCENE_PATH) as PackedScene).instantiate() as TeacherAI
	add_child(_teacher)
	_teacher.clock = clock
	_teacher.set_attendance(attendance)
	var failure: String = ""
	if clock.current_block().id != CLASS_BLOCK_ID or not is_equal_approx(clock.seconds_into_block(), SECONDS_INTO_BLOCK):
		failure = "the clock is not %.0f s into %s" % [SECONDS_INTO_BLOCK, CLASS_BLOCK_ID]
	if failure.is_empty():
		failure = await _seen_in_hallway()
	if failure.is_empty():
		failure = await _seen_in_class()
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _seen_in_hallway() -> String:
	var patrol_start: Node3D = _school_env.marker(PATROL_START)
	_teacher.global_transform = patrol_start.global_transform
	await _place_player(patrol_start.global_position + HALL_PLAYER_OFFSET)
	_teacher.watch(_player, _meters)
	_teacher.setup(_school_env)
	_meters.reset()
	await _wait_seconds(MEASURE_SECONDS)
	print("school alert after 1 s in the hallway: %.2f" % _meters.school_alert)
	if _meters.school_alert <= 0.0:
		return "no school alert after 1 s out of class in front of the teacher"
	return ""


func _seen_in_class() -> String:
	_teacher.patrols = false
	_teacher.global_position = _navigation_point(CLASS_TEACHER_POINT)
	await _place_player(_navigation_point(CLASS_PLAYER_POINT))
	var toward_player: Vector3 = _player.global_position - _teacher.global_position
	_teacher.rotation.y = atan2(-toward_player.x, -toward_player.z)
	_teacher.setup(_school_env)
	if not _school_env.volume_contains(CLASS_VOLUME, _player.head_position()):
		return "the player is not inside %s" % CLASS_VOLUME
	_meters.reset()
	await _wait_seconds(MEASURE_SECONDS)
	if not _teacher.sees_player:
		return "the teacher does not see the player in class, so the check proves nothing"
	if _meters.school_alert > 0.0:
		return "school alert rose to %.2f with the player inside %s" % [_meters.school_alert, CLASS_VOLUME]
	return ""


func _navigation_point(point: Vector3) -> Vector3:
	return NavigationServer3D.map_get_closest_point(_school_env.navigation_map(), point)


func _place_player(at: Vector3) -> void:
	_player.global_position = at
	_player.velocity = Vector3.ZERO
	for frame: int in SETTLE_FRAMES:
		await get_tree().physics_frame


func _wait_seconds(seconds: float) -> void:
	var waited: float = 0.0
	while waited < seconds - 0.0001:
		await get_tree().physics_frame
		waited += get_physics_process_delta_time()
