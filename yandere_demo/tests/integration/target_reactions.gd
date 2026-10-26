extends IntegrationTest
## The target's other senses and reactions: a footstep turns his head for 1.5 s without a reaction state, the player
## right next to him startles him with a Suspicion spike, a flash startles him without one (ruling R21), he calms back
## into his activity after each, an item of his seen in the player's hands counts once, and at 100 Suspicion he
## reports and walks off toward a teacher.

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"
const TARGET_SCENE_PATH: String = "res://scenes/target.tscn"
const PLAYER_SCENE_PATH: String = "res://scenes/player.tscn"
const POOL_PATH: String = "res://data/activity_pool.tres"
const SCHEDULE_PATH: String = "res://data/schedule_table.tres"
const STEALTH_TUNING: StealthTuning = preload("res://data/stealth_tuning.tres")
const TARGET_TUNING: TargetTuning = preload("res://data/target_tuning.tres")
const ACTIVITY_ID: StringName = &"read_bench"
const PLANNED_MINUTES: float = 60.0
const DAY_SEED: int = 16
const START_DEADLINE_SECONDS: float = 10.0
const POSE_SETTLE_SECONDS: float = 0.8
const HEARING_DISTANCE: float = 2.0
const STARTLE_DISTANCE: float = 1.1
const SEEN_DISTANCE: float = 3.0
const HEAD_TURNED_INFLUENCE: float = 0.9
const HEAD_SETTLE_SECONDS: float = 0.5
const SPIKE_TOLERANCE: float = 2.0
const CALM_DEADLINE_SECONDS: float = 8.0
const REPORT_DEADLINE_SECONDS: float = 25.0
const REPORT_ARRIVAL_DISTANCE: float = 1.0

var _school_env: SchoolEnv
var _target: TargetAI
var _player: StealthPlayer
var _meters: StealthMeters
var _look_at: LookAtModifier3D
var _anchor: Node3D
var _forward: Vector3
var _reported_count: int = 0


func _ready() -> void:
	timeout_seconds = 90.0
	_school_env = (load(SCHOOL_ENV_PATH) as PackedScene).instantiate() as SchoolEnv
	add_child(_school_env)
	await _school_env.navigation_ready
	_target = (load(TARGET_SCENE_PATH) as PackedScene).instantiate() as TargetAI
	add_child(_target)
	_target.setup(_school_env, DAY_SEED, null)
	_target.reported.connect(func() -> void: _reported_count += 1)
	_look_at = _target.get_node("Model/TargetChar/Skeleton3D/LookAtModifier3D") as LookAtModifier3D
	_player = (load(PLAYER_SCENE_PATH) as PackedScene).instantiate() as StealthPlayer
	add_child(_player)
	_player.global_transform = _school_env.marker("PlayerSpawn").global_transform
	_meters = StealthMeters.new(STEALTH_TUNING)
	var failure: String = await _run_scenario()
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _run_scenario() -> String:
	for step: Callable in [_start_reading, _hears_footstep, _startles_up_close, _startles_at_flash, _counts_own_item_once, _reports]:
		var failure: String = await step.call()
		if not failure.is_empty():
			return failure
	return ""


func _start_reading() -> String:
	_anchor = _school_env.anchors_for(ACTIVITY_ID)[0]
	_forward = -_anchor.global_basis.z
	_forward.y = 0.0
	_forward = _forward.normalized()
	_target.global_position = _anchor.global_position
	_target.rotation.y = _anchor.global_rotation.y
	await get_tree().physics_frame
	var planned: PlannedActivity = PlannedActivity.new()
	planned.activity = (load(POOL_PATH) as ActivityPool).find(ACTIVITY_ID)
	planned.duration_minutes = PLANNED_MINUTES
	_target.start_plan([planned] as Array[PlannedActivity])
	await _wait_until(func() -> bool: return _target.current_activity() != null, START_DEADLINE_SECONDS)
	if _target.current_activity() == null:
		return "he did not start %s" % ACTIVITY_ID
	await _wait_seconds(POSE_SETTLE_SECONDS)
	_target.perception.watch(_player, _meters)
	return ""


func _hears_footstep() -> String:
	await _place_player(_anchor.global_position - _forward * HEARING_DISTANCE)
	_meters.reset()
	_player.noise_made.emit(_player.global_position, GameTypes.Stance.WALK)
	await _wait_seconds(HEAD_SETTLE_SECONDS)
	if _look_at.influence < HEAD_TURNED_INFLUENCE or _target.state != TargetAI.State.ACTIVITY:
		return "a footstep did not turn his head alone (influence %.2f, state %s)" % [_look_at.influence, _state_name()]
	await _send_player_away()
	await _wait_seconds(TARGET_TUNING.hearing_turn_seconds + TARGET_TUNING.head_turn_seconds)
	if _look_at.influence > 0.0:
		return "his head still turns %.2f after the hearing glance" % _look_at.influence
	_player.noise_made.emit(_player.global_position, GameTypes.Stance.WALK)
	await _wait_seconds(HEAD_SETTLE_SECONDS)
	if _look_at.influence > 0.0:
		return "he heard a walking footstep from the player spawn"
	return ""


func _startles_up_close() -> String:
	_meters.reset()
	await _place_player(_anchor.global_position + _forward * STARTLE_DISTANCE)
	if _target.state != TargetAI.State.STARTLED or _meters.suspicion < STEALTH_TUNING.startle_spike:
		return "the player right in front did not startle him (state %s, suspicion %.1f)" % [_state_name(), _meters.suspicion]
	var after_spike: float = _meters.suspicion
	await _wait_seconds(HEAD_SETTLE_SECONDS)
	if _meters.suspicion - after_spike > STEALTH_TUNING.startle_spike - SPIKE_TOLERANCE:
		return "standing next to him startled him again (%.1f -> %.1f)" % [after_spike, _meters.suspicion]
	return await _calms_down()


func _startles_at_flash() -> String:
	_meters.reset()
	await _send_player_away()
	_target.on_flash(_player.head_position())
	if _target.state != TargetAI.State.STARTLED or _meters.suspicion != 0.0:
		return "the flash did not only startle him (state %s, suspicion %.1f)" % [_state_name(), _meters.suspicion]
	return await _calms_down()


## Out of sight he goes STARTLED -> SUSPICIOUS -> back to reading, then walks slower for `calm_slow_seconds`.
func _calms_down() -> String:
	await _send_player_away()
	_meters.reset()
	await _wait_until(func() -> bool: return _target.state == TargetAI.State.ACTIVITY, CALM_DEADLINE_SECONDS)
	if _target.state != TargetAI.State.ACTIVITY or _target.current_activity() == null:
		return "he did not calm down back into %s (state %s)" % [ACTIVITY_ID, _state_name()]
	return ""


func _counts_own_item_once() -> String:
	var class_block: ScheduleBlock = (load(SCHEDULE_PATH) as ScheduleTable).blocks[1]
	_target.on_block_changed(class_block)
	await get_tree().physics_frame
	_target.snap_to_class_seat()
	var own_item: StringName = &""
	for node: Node in get_tree().get_nodes_in_group(ItemPickup.YANDERE_ITEMS_GROUP):
		own_item = (node as ItemPickup).item_id
	if own_item == &"" or not _target.is_own_item(own_item):
		return "no locker item of his spawned at the start of class"
	var seat: Node3D = _school_env.marker("TargetSeat")
	var front: Vector3 = seat.global_position - seat.global_basis.z * SEEN_DISTANCE
	await _place_player(NavigationServer3D.map_get_closest_point(_school_env.navigation_map(), front))
	await _wait_seconds(HEAD_SETTLE_SECONDS)
	if not _target.perception.sees_player:
		return "he does not see the player in front of his seat"
	_meters.reset()
	_player.pick_up(own_item)
	await get_tree().physics_frame
	if _meters.suspicion < STEALTH_TUNING.carrying_seen_spike:
		return "seeing his %s carried added only %.1f" % [own_item, _meters.suspicion]
	var after_spike: float = _meters.suspicion
	_player.drop_carried()
	_player.pick_up(own_item)
	await _wait_seconds(HEAD_SETTLE_SECONDS)
	if _meters.suspicion - after_spike > STEALTH_TUNING.carrying_seen_spike - SPIKE_TOLERANCE:
		return "the same item counted twice (%.1f -> %.1f)" % [after_spike, _meters.suspicion]
	_player.drop_carried()
	return ""


func _reports() -> String:
	_meters.add_suspicion_spike(StealthMeters.METER_MAXIMUM)
	await get_tree().physics_frame
	if _target.state != TargetAI.State.REPORTING or _reported_count != 1:
		return "at 100 suspicion: state %s, reported %d times" % [_state_name(), _reported_count]
	var start: float = _nearest_patrol_distance()
	var seconds: float = await _wait_until(func() -> bool: return _nearest_patrol_distance() <= REPORT_ARRIVAL_DISTANCE, REPORT_DEADLINE_SECONDS)
	if _nearest_patrol_distance() > REPORT_ARRIVAL_DISTANCE or _target.state != TargetAI.State.REPORTING:
		return "reporting, he did not reach a teacher patrol point (%.2f -> %.2f m, state %s)" % [start, _nearest_patrol_distance(), _state_name()]
	print("reported, stood up and reached a teacher patrol point in %.1f s" % seconds)
	return ""


func _nearest_patrol_distance() -> float:
	var nearest: float = INF
	for point: Node3D in _school_env.markers_with_prefix("TeacherPatrol_"):
		nearest = minf(nearest, point.global_position.distance_to(_target.global_position))
	return nearest


func _send_player_away() -> void:
	await _place_player(_school_env.marker("PlayerSpawn").global_position)


func _place_player(at: Vector3) -> void:
	_player.global_position = at
	_player.velocity = Vector3.ZERO
	await get_tree().physics_frame
	await get_tree().physics_frame


func _state_name() -> String:
	return TargetAI.State.keys()[_target.state]


func _wait_seconds(seconds: float) -> void:
	await _wait_until(func() -> bool: return false, seconds)


## Waits physics frames until `condition` holds or `limit` seconds pass; returns the seconds waited.
func _wait_until(condition: Callable, limit: float) -> float:
	var seconds: float = 0.0
	while not condition.call() and seconds <= limit:
		await get_tree().physics_frame
		seconds += get_physics_process_delta_time()
	return seconds
