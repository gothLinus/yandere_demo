extends IntegrationTest
## The target's sight while he reads on the bench: a walking player 3 m in front raises Suspicion and is noticed
## within 4 s, the same player behind him lets it fall, and two students next to the player halve the gain.

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"
const TARGET_SCENE_PATH: String = "res://scenes/target.tscn"
const PLAYER_SCENE_PATH: String = "res://scenes/player.tscn"
const STUDENT_SCENE_PATH: String = "res://scenes/student.tscn"
const POOL_PATH: String = "res://data/activity_pool.tres"
const STEALTH_TUNING: StealthTuning = preload("res://data/stealth_tuning.tres")
const ACTIVITY_ID: StringName = &"read_bench"
const PLANNED_MINUTES: float = 60.0
const DAY_SEED: int = 16
const PLAYER_DISTANCE: float = 3.0
const STUDENT_SIDE_OFFSET: float = 1.0
const START_DEADLINE_SECONDS: float = 10.0
const POSE_SETTLE_SECONDS: float = 0.8
const MEASURE_SECONDS: float = 1.0
const NOTICE_DEADLINE_SECONDS: float = 4.0
const CALM_DEADLINE_SECONDS: float = 4.0
const CROWD_RATIO_TOLERANCE: float = 0.15

var _school_env: SchoolEnv
var _target: TargetAI
var _player: StealthPlayer
var _meters: StealthMeters
var _anchor: Node3D
var _forward: Vector3
var _noticed_after: float = -1.0
var _gain_alone: float = 0.0
var _finished_scenario: bool = false
var _clock_seconds: float = 0.0


func _ready() -> void:
	timeout_seconds = 60.0
	_school_env = (load(SCHOOL_ENV_PATH) as PackedScene).instantiate() as SchoolEnv
	add_child(_school_env)
	await _school_env.navigation_ready
	_target = (load(TARGET_SCENE_PATH) as PackedScene).instantiate() as TargetAI
	add_child(_target)
	_target.setup(_school_env, DAY_SEED, ActivityHistory.new())
	_player = (load(PLAYER_SCENE_PATH) as PackedScene).instantiate() as StealthPlayer
	add_child(_player)
	_meters = StealthMeters.new(STEALTH_TUNING)
	_meters.noticed.connect(func() -> void: _noticed_after = _clock_seconds)
	var failure: String = await _run_scenario()
	if failure.is_empty() and not _finished_scenario:
		failure = "the scenario stopped on a script error"
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _physics_process(delta: float) -> void:
	_clock_seconds += delta


func _run_scenario() -> String:
	for step: Callable in [_start_reading, _seen_in_front, _unseen_behind, _crowd_halves_gain]:
		var failure: String = await step.call()
		if not failure.is_empty():
			return failure
	_finished_scenario = true
	return ""


func _start_reading() -> String:
	_anchor = _school_env.anchors_for(ACTIVITY_ID)[0]
	_forward = -_anchor.global_basis.z
	_forward.y = 0.0
	_forward = _forward.normalized()
	_target.global_position = _anchor.global_position
	_target.rotation.y = _anchor.global_rotation.y
	_player.global_transform = _school_env.marker("PlayerSpawn").global_transform
	await get_tree().physics_frame
	var planned: PlannedActivity = PlannedActivity.new()
	planned.activity = (load(POOL_PATH) as ActivityPool).find(ACTIVITY_ID)
	planned.duration_minutes = PLANNED_MINUTES
	_target.start_plan([planned] as Array[PlannedActivity])
	await _wait_until(func() -> bool: return _target.current_activity() != null, START_DEADLINE_SECONDS)
	if _target.current_activity() == null or _target.current_activity().id != ACTIVITY_ID:
		return "he did not start %s (state %s)" % [ACTIVITY_ID, TargetAI.State.keys()[_target.state]]
	await _wait_seconds(POSE_SETTLE_SECONDS)
	return ""


func _seen_in_front() -> String:
	await _place_player(_anchor.global_position + _forward * PLAYER_DISTANCE)
	_target.perception.watch(_player, _meters)
	_meters.reset()
	var start_seconds: float = _clock_seconds
	await _wait_seconds(MEASURE_SECONDS)
	var gain: float = _meters.suspicion
	if gain <= 0.0:
		return "suspicion is %.2f after 1 s in front of him, walking" % gain
	_gain_alone = gain
	await _wait_until(func() -> bool: return _noticed_after >= 0.0, NOTICE_DEADLINE_SECONDS - MEASURE_SECONDS)
	if _noticed_after < 0.0 or _noticed_after - start_seconds > NOTICE_DEADLINE_SECONDS:
		return "noticed did not fire within %.0f s (suspicion %.1f)" % [NOTICE_DEADLINE_SECONDS, _meters.suspicion]
	print("gain alone %.2f in 1 s; noticed after %.2f s" % [gain, _noticed_after - start_seconds])
	return ""


func _unseen_behind() -> String:
	await _place_player(_anchor.global_position - _forward * PLAYER_DISTANCE)
	var before: float = _meters.suspicion
	await _wait_seconds(MEASURE_SECONDS)
	if _meters.suspicion >= before:
		return "suspicion did not fall behind him: %.2f -> %.2f" % [before, _meters.suspicion]
	return ""


func _crowd_halves_gain() -> String:
	await _place_player(_anchor.global_position + _forward * PLAYER_DISTANCE)
	var side: Vector3 = _forward.cross(Vector3.UP).normalized()
	for direction: float in [-1.0, 1.0]:
		var student: StudentAI = (load(STUDENT_SCENE_PATH) as PackedScene).instantiate() as StudentAI
		add_child(student)
		student.global_position = _player.global_position + side * STUDENT_SIDE_OFFSET * direction
	_meters.reset()
	await _wait_until(func() -> bool: return _target.state == TargetAI.State.ACTIVITY, CALM_DEADLINE_SECONDS)
	await _wait_seconds(POSE_SETTLE_SECONDS)
	_meters.reset()
	await _wait_seconds(MEASURE_SECONDS)
	var expected: float = _gain_alone * 0.5
	print("gain with two students %.2f in 1 s (expected %.2f)" % [_meters.suspicion, expected])
	if absf(_meters.suspicion - expected) > expected * CROWD_RATIO_TOLERANCE:
		return "crowd gain %.2f is not about half of %.2f" % [_meters.suspicion, _gain_alone]
	return ""


func _place_player(at: Vector3) -> void:
	_player.global_position = at
	_player.velocity = Vector3.ZERO
	await get_tree().physics_frame
	await get_tree().physics_frame


func _wait_seconds(seconds: float) -> void:
	var end_seconds: float = _clock_seconds + seconds
	while _clock_seconds < end_seconds - 0.0001:
		await get_tree().physics_frame


func _wait_until(condition: Callable, limit: float) -> void:
	var end_seconds: float = _clock_seconds + limit
	while not condition.call() and _clock_seconds < end_seconds:
		await get_tree().physics_frame
