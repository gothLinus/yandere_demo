extends IntegrationTest
## Suspicion at 90 while the player hides in a locker: it drains to 0 within 5 s, he never reports, and after his
## notice he calms down and goes back to his plan within 25 s.

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"
const TARGET_SCENE_PATH: String = "res://scenes/target.tscn"
const PLAYER_SCENE_PATH: String = "res://scenes/player.tscn"
const POOL_PATH: String = "res://data/activity_pool.tres"
const STEALTH_TUNING: StealthTuning = preload("res://data/stealth_tuning.tres")
const ACTIVITY_ID: StringName = &"chat_students"
const ANCHOR_INDEX: int = 1
const HIDE_SPOT_NAME: String = "Interactable_HideLocker_02"
const PLANNED_MINUTES: float = 60.0
const DAY_SEED: int = 16
const START_SUSPICION: float = 90.0
const START_DEADLINE_SECONDS: float = 15.0
const DRAIN_DEADLINE_SECONDS: float = 5.0
const RESUME_DEADLINE_SECONDS: float = 25.0
const RESUMED_STATES: Array[TargetAI.State] = [TargetAI.State.ACTIVITY, TargetAI.State.TRAVEL]

var _school_env: SchoolEnv
var _target: TargetAI
var _player: StealthPlayer
var _meters: StealthMeters
var _reported: bool = false
var _reacted: bool = false
var _finished_scenario: bool = false


func _ready() -> void:
	timeout_seconds = 60.0
	_school_env = (load(SCHOOL_ENV_PATH) as PackedScene).instantiate() as SchoolEnv
	add_child(_school_env)
	await _school_env.navigation_ready
	_target = (load(TARGET_SCENE_PATH) as PackedScene).instantiate() as TargetAI
	add_child(_target)
	_target.setup(_school_env, DAY_SEED, ActivityHistory.new())
	_target.reported.connect(func() -> void: _reported = true)
	_target.state_changed.connect(_on_state_changed)
	_player = (load(PLAYER_SCENE_PATH) as PackedScene).instantiate() as StealthPlayer
	add_child(_player)
	_player.global_transform = _school_env.marker("PlayerSpawn").global_transform
	_meters = StealthMeters.new(STEALTH_TUNING)
	var failure: String = await _run_scenario()
	if failure.is_empty() and not _finished_scenario:
		failure = "the scenario stopped on a script error"
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _run_scenario() -> String:
	var anchor: Node3D = _school_env.anchors_for(ACTIVITY_ID)[ANCHOR_INDEX]
	_target.global_position = anchor.global_position
	await get_tree().physics_frame
	var planned: PlannedActivity = PlannedActivity.new()
	planned.activity = (load(POOL_PATH) as ActivityPool).find(ACTIVITY_ID)
	planned.anchor_index = ANCHOR_INDEX
	planned.duration_minutes = PLANNED_MINUTES
	_target.start_plan([planned] as Array[PlannedActivity])
	await _wait_until(func() -> bool: return _target.current_activity() != null, START_DEADLINE_SECONDS)
	if _target.current_activity() == null:
		return "he did not start %s (state %s)" % [ACTIVITY_ID, _state_name()]
	var hide_spot: HideSpot = _school_env.get_node(HIDE_SPOT_NAME) as HideSpot
	hide_spot.interact(_player)
	if _player.mode != StealthPlayer.MODE_HIDDEN:
		return "the player did not hide (mode %s)" % _player.mode
	_target.perception.watch(_player, _meters)
	_meters.add_suspicion_spike(START_SUSPICION)
	var drained_after: float = await _wait_until(func() -> bool: return _meters.suspicion <= 0.0, DRAIN_DEADLINE_SECONDS)
	if _meters.suspicion > 0.0:
		return "suspicion is still %.1f after %.0f s hidden" % [_meters.suspicion, DRAIN_DEADLINE_SECONDS]
	if not _reacted:
		return "he never reacted to suspicion %.0f (state %s)" % [START_SUSPICION, _state_name()]
	var resumed: Callable = func() -> bool: return _reacted and RESUMED_STATES.has(_target.state) and not _is_reacting()
	var resumed_after: float = drained_after + await _wait_until(resumed, RESUME_DEADLINE_SECONDS - drained_after)
	if not resumed.call():
		return "he did not resume within %.0f s (state %s)" % [RESUME_DEADLINE_SECONDS, _state_name()]
	if _reported:
		return "he reported while the player hid"
	print("suspicion 0 after %.2f s; resumed %s after %.2f s" % [drained_after, _state_name(), resumed_after])
	_finished_scenario = true
	return ""


func _on_state_changed(state: TargetAI.State) -> void:
	if state == TargetAI.State.NOTICE:
		_reacted = true


func _is_reacting() -> bool:
	return [TargetAI.State.NOTICE, TargetAI.State.SUSPICIOUS, TargetAI.State.STARTLED].has(_target.state)


func _state_name() -> String:
	return TargetAI.State.keys()[_target.state]


## Waits physics frames until `condition` holds or `limit` seconds pass; returns the seconds waited.
func _wait_until(condition: Callable, limit: float) -> float:
	var seconds: float = 0.0
	while not condition.call() and seconds <= limit:
		await get_tree().physics_frame
		seconds += get_physics_process_delta_time()
	return seconds
