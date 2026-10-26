extends IntegrationTest
## A planned anchor sealed inside a solid box: the target walks into the box, stalls and skips that activity.
## With a next activity he starts it within 12 s. With nothing left he goes to Anchor_<first activity>_00 and waits
## there without starting it.

const SCHOOL_ENV_PATH: String = "res://scenes/school_env.tscn"
const TARGET_SCENE_PATH: String = "res://scenes/target.tscn"
const POOL_PATH: String = "res://data/activity_pool.tres"
const SEALED_ACTIVITY: StringName = &"vending_drink"
const NEXT_ACTIVITY: StringName = &"chat_students"
const BOX_OFFSET: Vector3 = Vector3(3.0, 0.0, 0.0)
const BOX_SIZE: Vector3 = Vector3(2.0, 2.0, 2.0)
const START_OFFSET: Vector3 = Vector3(1.0, 0.0, 0.0)
const NEXT_DEADLINE_SECONDS: float = 12.0
const FALLBACK_DEADLINE_SECONDS: float = 16.0
const ANCHOR_TOLERANCE: float = 0.35
const PLANNED_MINUTES: float = 5.0

var _school_env: SchoolEnv
var _target: TargetAI
var _pool: ActivityPool
var _started_ids: Array[StringName] = []


func _ready() -> void:
	timeout_seconds = 90.0
	_school_env = (load(SCHOOL_ENV_PATH) as PackedScene).instantiate() as SchoolEnv
	add_child(_school_env)
	await _school_env.navigation_ready
	_pool = load(POOL_PATH) as ActivityPool
	_target = (load(TARGET_SCENE_PATH) as PackedScene).instantiate() as TargetAI
	add_child(_target)
	_target.activity_started.connect(func(activity: ActivityDefinition) -> void: _started_ids.append(activity.id))
	_target.setup(_school_env, 1, ActivityHistory.new())
	var failure: String = await _skips_to_next_activity()
	if failure.is_empty():
		failure = await _falls_back_when_nothing_is_left()
	if failure.is_empty():
		pass_test()
	else:
		fail_test(failure)


func _skips_to_next_activity() -> String:
	var next_anchor: Node3D = _school_env.anchors_for(NEXT_ACTIVITY)[0]
	var sealed_anchor: Node3D = _school_env.anchors_for(SEALED_ACTIVITY)[0]
	sealed_anchor.global_position = next_anchor.global_position + BOX_OFFSET
	_add_sealed_box(sealed_anchor.global_position)
	await _start([_planned(SEALED_ACTIVITY, 0), _planned(NEXT_ACTIVITY, 0)], next_anchor.global_position + START_OFFSET)
	var seconds: float = await _wait_until(func() -> bool: return not _started_ids.is_empty(), NEXT_DEADLINE_SECONDS)
	if _started_ids.size() != 1 or _started_ids[0] != NEXT_ACTIVITY:
		return "expected only %s to start within %.0f s, started %s" % [NEXT_ACTIVITY, NEXT_DEADLINE_SECONDS, _started_ids]
	print("%s started after %.1f s" % [NEXT_ACTIVITY, seconds])
	return ""


func _falls_back_when_nothing_is_left() -> String:
	_started_ids.clear()
	var fallback_anchor: Node3D = _school_env.anchors_for(SEALED_ACTIVITY)[0]
	fallback_anchor.global_position = _school_env.anchors_for(NEXT_ACTIVITY)[0].global_position
	# The first scenario's box is still there, east of this spot.
	var sealed_anchor: Node3D = _school_env.anchors_for(SEALED_ACTIVITY)[1]
	sealed_anchor.global_position = fallback_anchor.global_position + BOX_OFFSET
	await _start([_planned(SEALED_ACTIVITY, 1)], fallback_anchor.global_position + START_OFFSET)
	var waiting_at_fallback: Callable = func() -> bool:
		return _target.state == TargetAI.State.ACTIVITY \
			and _target.global_position.distance_to(fallback_anchor.global_position) <= ANCHOR_TOLERANCE
	var seconds: float = await _wait_until(waiting_at_fallback, FALLBACK_DEADLINE_SECONDS)
	if not waiting_at_fallback.call():
		return "did not reach Anchor_%s_00 within %.0f s (state %s, %.2f m away)" % [SEALED_ACTIVITY, FALLBACK_DEADLINE_SECONDS,
				TargetAI.State.keys()[_target.state], _target.global_position.distance_to(fallback_anchor.global_position)]
	if not _started_ids.is_empty() or _target.current_activity() != null:
		return "the fallback started an activity: %s" % [_started_ids]
	print("waiting at Anchor_%s_00 after %.1f s" % [SEALED_ACTIVITY, seconds])
	return ""


func _start(plan: Array[PlannedActivity], at: Vector3) -> void:
	_target.global_position = at
	await get_tree().physics_frame
	_target.start_plan(plan)


## Waits physics frames until `condition` holds or `limit` seconds pass; returns the seconds waited.
func _wait_until(condition: Callable, limit: float) -> float:
	var seconds: float = 0.0
	while not condition.call() and seconds <= limit:
		await get_tree().physics_frame
		seconds += get_physics_process_delta_time()
	return seconds


func _planned(activity_id: StringName, anchor_index: int) -> PlannedActivity:
	var planned: PlannedActivity = PlannedActivity.new()
	planned.activity = _pool.find(activity_id)
	planned.anchor_index = anchor_index
	planned.duration_minutes = PLANNED_MINUTES
	return planned


func _add_sealed_box(center: Vector3) -> void:
	var body: StaticBody3D = StaticBody3D.new()
	body.collision_layer = PhysicsLayers.WORLD
	var shape: CollisionShape3D = CollisionShape3D.new()
	var box: BoxShape3D = BoxShape3D.new()
	box.size = BOX_SIZE
	shape.shape = box
	body.add_child(shape)
	add_child(body)
	body.global_position = center + Vector3.UP * BOX_SIZE.y * 0.5
