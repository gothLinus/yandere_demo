extends IntegrationTest
## The background crowd: deterministic looks per day seed, seats assigned round-robin, wandering in a free block,
## walking to and gliding into their seats in class (ruling R12), the class-fade snap, the flash witness with its
## cooldown, and leaving the seats when class ends.

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"
const SCHEDULE_PATH: String = "res://data/schedule_table.tres"
const STEALTH_TUNING: StealthTuning = preload("res://data/stealth_tuning.tres")
const CAST_TUNING: CastTuning = preload("res://data/cast_tuning.tres")
const DAY_SEED: int = 7
const OTHER_DAY_SEED: int = 8
const WANDER_SECONDS: float = 3.0
const MIN_WANDER_DISTANCE: float = 0.5
const TIME_SCALE: float = 8.0
const PHYSICS_STEPS_PER_TIME_SCALE: int = 8
const SEATING_DEADLINE_SECONDS: float = 90.0
const SEAT_TOLERANCE: float = 0.01
const FLASH_DISTANCE: float = 5.0
const LEAVE_DEADLINE_SECONDS: float = 3.0

var _school_env: SchoolEnv
var _clock: SchoolClockModel
var _meters: StealthMeters
var _spawner: CrowdSpawner
var _finished_scenario: bool = false
var _previous_time_scale: float
var _previous_max_steps: int


func _ready() -> void:
	timeout_seconds = 90.0
	_previous_time_scale = Engine.time_scale
	_previous_max_steps = Engine.max_physics_steps_per_frame
	_school_env = (load(SCHOOL_ENV_PATH) as PackedScene).instantiate() as SchoolEnv
	add_child(_school_env)
	await _school_env.navigation_ready
	_clock = SchoolClockModel.new(load(SCHEDULE_PATH) as ScheduleTable)
	_meters = StealthMeters.new(STEALTH_TUNING)
	var failure: String = await _run_scenario()
	_restore_time_scale()
	if failure.is_empty() and not _finished_scenario:
		failure = "the scenario stopped on a script error"
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _run_scenario() -> String:
	for step: Callable in [_spawns_deterministically, _wanders_in_free_block, _sits_in_class, _witnesses_flash, _leaves_seat]:
		var failure: String = await step.call()
		if not failure.is_empty():
			return failure
	_finished_scenario = true
	return ""


func _spawns_deterministically() -> String:
	_spawner = _make_spawner()
	var variants: Array[int] = _spawn_variants(DAY_SEED)
	if variants != _spawn_variants(DAY_SEED):
		return "the same day seed gave different variants"
	if variants == _spawn_variants(OTHER_DAY_SEED):
		return "another day seed gave the same variants"
	_spawner.spawn(_school_env, DAY_SEED)
	await get_tree().physics_frame
	var seats: Array[Node3D] = _school_env.markers_with_prefix("StudentSeat_")
	if get_tree().get_nodes_in_group(StudentAI.GROUP).size() != _spawner.student_count:
		return "%d nodes in group students, expected %d" % [get_tree().get_nodes_in_group(StudentAI.GROUP).size(), _spawner.student_count]
	var looks: Dictionary = {}
	for index: int in _spawner.students.size():
		var student: StudentAI = _spawner.students[index]
		if student.seat != seats[index % seats.size()]:
			return "%s has seat %s, not %s" % [student.name, student.seat.name, seats[index % seats.size()].name]
		looks[[student.is_female(), _visible_hair(student)]] = true
	if looks.size() < 3:
		return "only %d distinct sex and hair combinations among %d students" % [looks.size(), _spawner.students.size()]
	return ""


func _wanders_in_free_block() -> String:
	var starts: Array[Vector3] = []
	for student: StudentAI in _spawner.students:
		starts.append(student.global_position)
	await _wait_seconds(WANDER_SECONDS)
	var moved: int = 0
	for index: int in _spawner.students.size():
		var student: StudentAI = _spawner.students[index]
		if student.mode != StudentAI.Mode.TO_SPOT and student.mode != StudentAI.Mode.AT_SPOT:
			return "%s is in mode %s during a free block" % [student.name, StudentAI.Mode.keys()[student.mode]]
		if student.global_position.distance_to(starts[index]) >= MIN_WANDER_DISTANCE:
			moved += 1
	if moved < _spawner.students.size() / 2:
		return "only %d of %d students wandered" % [moved, _spawner.students.size()]
	return ""


func _sits_in_class() -> String:
	_clock.skip_to_block_end()
	Engine.time_scale = TIME_SCALE
	Engine.max_physics_steps_per_frame = maxi(_previous_max_steps, int(PHYSICS_STEPS_PER_TIME_SCALE * TIME_SCALE))
	var all_seated: Callable = func() -> bool:
		for student: StudentAI in _spawner.students:
			if student.mode != StudentAI.Mode.SEATED:
				return false
		return true
	var seconds: float = await _wait_until(all_seated, SEATING_DEADLINE_SECONDS)
	_restore_time_scale()
	if not all_seated.call():
		var unseated: Array[String] = []
		for student: StudentAI in _spawner.students:
			if student.mode != StudentAI.Mode.SEATED:
				unseated.append("%s %s %.2f m" % [student.name, StudentAI.Mode.keys()[student.mode], student.global_position.distance_to(student.seat.global_position)])
		return "not every student sat within %.0f s: %s" % [SEATING_DEADLINE_SECONDS, unseated]
	print("all %d students walked to their seats in %.1f s" % [_spawner.students.size(), seconds])
	for student: StudentAI in _spawner.students:
		student.global_position += Vector3.BACK
	_spawner.snap_all_to_seats()
	await get_tree().physics_frame
	for student: StudentAI in _spawner.students:
		if student.global_position.distance_to(student.seat.global_position) > SEAT_TOLERANCE or student.mode != StudentAI.Mode.SEATED:
			return "snap_all_to_seats left %s %.2f m from its seat" % [student.name, student.global_position.distance_to(student.seat.global_position)]
	return ""


func _witnesses_flash() -> String:
	var witness: StudentAI = _spawner.students[0]
	var in_view: Vector3 = witness.head_position() + witness.body_forward() * FLASH_DISTANCE
	_meters.reset()
	witness.on_flash(in_view)
	var spike: float = STEALTH_TUNING.alert_spikes[&"student_witness"]
	if not is_equal_approx(_meters.school_alert, spike):
		return "a flash in view added %.1f school alert, expected %.1f" % [_meters.school_alert, spike]
	witness.on_flash(in_view)
	if not is_equal_approx(_meters.school_alert, spike):
		return "a second flash within %.0f s counted again" % CAST_TUNING.witness_cooldown_seconds
	var other: StudentAI = _spawner.students[1]
	other.on_flash(other.head_position() - other.body_forward() * FLASH_DISTANCE)
	other.on_flash(other.head_position() + other.body_forward() * (CAST_TUNING.witness_range + 1.0))
	if not is_equal_approx(_meters.school_alert, spike):
		return "a flash behind or out of range counted"
	return ""


func _leaves_seat() -> String:
	_clock.skip_to_block_end()
	var left: Callable = func() -> bool:
		for student: StudentAI in _spawner.students:
			if student.mode != StudentAI.Mode.TO_SPOT and student.mode != StudentAI.Mode.AT_SPOT:
				return false
		return true
	await _wait_until(left, LEAVE_DEADLINE_SECONDS)
	if not left.call():
		return "not every student left the seat when %s began" % _clock.current_block().id
	return ""


func _make_spawner() -> CrowdSpawner:
	var spawner: CrowdSpawner = CrowdSpawner.new()
	spawner.meters = _meters
	spawner.clock = _clock
	add_child(spawner)
	return spawner


func _spawn_variants(day_seed: int) -> Array[int]:
	var variants: Array[int] = []
	for index: int in _spawner.student_count:
		variants.append(CrowdSpawner.variant_for(day_seed, index))
	return variants


func _visible_hair(student: StudentAI) -> StringName:
	for node: Node in student.find_children("Hair_*", "MeshInstance3D", true, false):
		if (node as MeshInstance3D).visible:
			return node.name
	return &""


func _wait_seconds(seconds: float) -> void:
	await _wait_until(func() -> bool: return false, seconds)


## Waits physics frames until `condition` holds or `limit` seconds pass; returns the seconds waited.
func _wait_until(condition: Callable, limit: float) -> float:
	var seconds: float = 0.0
	while not condition.call() and seconds <= limit:
		await get_tree().physics_frame
		seconds += get_physics_process_delta_time()
	return seconds


func _restore_time_scale() -> void:
	Engine.time_scale = _previous_time_scale
	Engine.max_physics_steps_per_frame = _previous_max_steps


func _exit_tree() -> void:
	_restore_time_scale()
